"""Explicit task accountability. Labels are not identities, grants or executors.

Supported writers share the catalog transaction lock. Older binaries and direct
SQL are unsupported when a policy is configured; this is not a database ACL.
"""
import hashlib
import json
import uuid
from contextlib import nullcontext
from sqlalchemy import Column, Integer, String, Text, Table, MetaData, ForeignKey, select, update
from pydantic import Field
from .domain import CRMError, StrictModel, metadata as legacy_metadata, settings, now
from .report_store import canonical, scope_for, transaction

metadata = MetaData()
legacy_metadata.tables['crm_tasks'].to_metadata(metadata)
schema_state = Table('crm_task_owner_schema', metadata, Column('id', Integer, primary_key=True), Column('version', Integer, nullable=False))
policies = Table('crm_task_owner_policies', metadata, Column('scope', String(64), primary_key=True), Column('version', Integer, nullable=False), Column('required', Integer, nullable=False), Column('default_owner_label', String(160)))
owners = Table('crm_task_owners', metadata, Column('scope', String(64), primary_key=True), Column('task_id', String(36), ForeignKey('crm_tasks.id'), primary_key=True), Column('owner_label', String(160)), Column('owner_source', String(20), nullable=False), Column('policy_version', Integer, nullable=False), Column('updated_at', String(40), nullable=False))
operations = Table('crm_task_owner_operations', metadata, Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True), Column('digest', String(64), nullable=False), Column('response', Text, nullable=False))
OWNED_TABLES = (schema_state, policies, owners, operations)
SCHEMA_VERSION = 1

# Same strict, read-only structural validation used by relationship storage.
from sqlalchemy import inspect
from .report_store import schema_name, advisory_lock

def check_schema(crm,conn,write=False):
    if write and crm.backend == 'postgres': advisory_lock(conn,['crm-task-owner-schema',schema_name(crm)])
    inspector=inspect(conn); schema=(conn.get_execution_options().get('schema_translate_map') or {}).get(None)
    present=[inspector.has_table(t.name,schema=schema) for t in OWNED_TABLES]
    if any(present) and not all(present): raise CRMError('Task owner schema is incomplete; explicit migration required',503)
    if not any(present):
        if not write: return False
        metadata.create_all(conn,tables=OWNED_TABLES)
        conn.execute(schema_state.insert().values(id=1,version=SCHEMA_VERSION))
        inspector=inspect(conn)
    for table in OWNED_TABLES:
        actual={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
        if set(actual)!=set(table.c.keys()): raise CRMError('Incompatible task owner columns',503)
        for col in table.c:
            found=actual[col.name]
            if (found['type']._type_affinity is not col.type._type_affinity or found['nullable']!=col.nullable or getattr(found['type'],'length',None)!=getattr(col.type,'length',None)): raise CRMError('Incompatible task owner column',503)
        if inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns'] != [c.name for c in table.primary_key]: raise CRMError('Incompatible task owner primary key',503)
        expected={(tuple(f.column_keys),tuple(e.column.table.name for e in f.elements),tuple(e.column.name for e in f.elements)) for f in table.foreign_key_constraints}
        reflected_fks=inspector.get_foreign_keys(table.name,schema=schema)
        allowed_schemas = (schema,) if crm.backend == 'postgres' and schema is not None else (None, schema)
        if any(f.get('options') or f.get('referred_schema') not in allowed_schemas for f in reflected_fks): raise CRMError('Incompatible task owner foreign key options or target schema',503)
        actual_fk={(tuple(f['constrained_columns']),tuple([f['referred_table']]*len(f['referred_columns'])),tuple(f['referred_columns'])) for f in reflected_fks}
        if expected != actual_fk: raise CRMError('Incompatible task owner foreign keys',503)
        if inspector.get_unique_constraints(table.name,schema=schema) or any(i.get('unique') for i in inspector.get_indexes(table.name,schema=schema)): raise CRMError('Unexpected task owner unique constraints',503)
    rows=conn.execute(select(schema_state)).mappings().all()
    if len(rows)!=1 or rows[0]['id']!=1 or rows[0]['version']!=SCHEMA_VERSION: raise CRMError('Unsupported task owner schema version',503)
    return True

CONTROL_FIELDS = ('owner_label', 'owner_policy_version', 'owner_source')

def strip_unsupplied(values, raw):
    for key in CONTROL_FIELDS:
        if key not in raw: values.pop(key, None)
    return values

class PolicyInput(StrictModel):
    version: int = Field(strict=True, ge=0)
    required: bool = Field(strict=True)
    default_owner_label: str | None = Field(default=None, min_length=1, max_length=160)

class TaskOwnership:
    def __init__(self, crm): self.crm = crm

    def policy(self, conn=None):
        with (nullcontext(conn) if conn is not None else self.crm._read_connection()) as c:
            result = dict(version=0, required=False, default_owner_label=None,
                          legacy_edit_rule='owner_required_on_edit')
            if check_schema(self.crm, c):
                row = c.execute(select(policies).where(policies.c.scope == scope_for(self.crm, connection=c))).mappings().first()
                if row: result.update(version=row['version'], required=bool(row['required']), default_owner_label=row['default_owner_label'])
            return result

    def enrich(self, conn, records):
        available = check_schema(self.crm, conn)
        scope = scope_for(self.crm, connection=conn) if available else None
        found = {}
        if records and scope:
            found = {r['task_id']: r for r in conn.execute(select(owners).where(owners.c.scope == scope, owners.c.task_id.in_([r['id'] for r in records]))).mappings()}
        for record in records:
            row = found.get(record['id'])
            record.update(owner_label=row['owner_label'] if row else None,
                          owner_source=row['owner_source'] if row else None)
        return records

    def prepare(self, conn, values, old=None):
        controls = {k: values.pop(k) for k in CONTROL_FIELDS if k in values}
        policy = self.policy(conn)
        supplied = controls.get('owner_policy_version')
        if supplied is not None and (type(supplied) is not int or supplied < 0):
            raise CRMError('A current owner policy version is required', 409)
        if (policy['version'] > 0 or controls) and supplied != policy['version']:
            raise CRMError('Task owner policy changed or was not reviewed. Refresh and review the current policy.', 409)
        label = controls.get('owner_label', old.get('owner_label') if old else None)
        source = controls.get('owner_source', 'explicit')
        if source == 'default' and ('owner_label' not in controls or not label or label != policy['default_owner_label']):
            raise CRMError('Review the current default owner and send its exact label')
        if 'owner_source' in controls and 'owner_label' not in controls:
            raise CRMError('owner_source requires an explicit owner_label')
        if policy['required'] and not label:
            raise CRMError('A human owner is required for every new or edited task, including existing ownerless tasks')
        if 'owner_label' not in controls: return None
        return dict(owner_label=label, owner_source=source, policy_version=policy['version'])

    def save(self, conn, task_id, value):
        if value is None: return
        check_schema(self.crm, conn, write=True)
        token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        if token is None: conn.execute(settings.insert().values(key='workspace_id', value=str(uuid.uuid4())))
        scope = scope_for(self.crm, connection=conn)
        clause = (owners.c.scope == scope, owners.c.task_id == task_id)
        row = conn.execute(select(owners.c.task_id).where(*clause)).first()
        values = dict(value, updated_at=now())
        if row: conn.execute(update(owners).where(*clause).values(**values))
        else: conn.execute(owners.insert().values(scope=scope, task_id=task_id, **values))

    def set_policy(self, data, *, key, actor='local'):
        policy = PolicyInput.model_validate(data).model_dump()
        if not isinstance(key, str) or not key.strip() or len(key) > 160: raise CRMError('A nonempty idempotency key of at most 160 characters is required')
        digest = hashlib.sha256(canonical(['policy', policy]).encode()).hexdigest()
        with transaction(self.crm) as conn:
            self.crm._catalog_lock(conn)
            check_schema(self.crm, conn, write=True)
            token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
            if token is None: conn.execute(settings.insert().values(key='workspace_id', value=str(uuid.uuid4())))
            scope = scope_for(self.crm, connection=conn)
            receipt = conn.execute(select(operations).where(operations.c.scope == scope, operations.c.key == key)).mappings().first()
            if receipt:
                if receipt['digest'] != digest: raise CRMError('Idempotency key already used for different data', 409)
                return json.loads(receipt['response'])
            old = self.policy(conn)
            if old['version'] != policy['version']: raise CRMError('Task owner policy changed. Refresh before editing.', 409)
            values = dict(policy, version=old['version']+1, required=int(policy['required']))
            if old['version']: conn.execute(update(policies).where(policies.c.scope == scope).values(**values))
            else: conn.execute(policies.insert().values(scope=scope, **values))
            result = self.policy(conn)
            conn.execute(operations.insert().values(scope=scope, key=key, digest=digest, response=canonical(result)))
            self.crm._audit(conn, 'task_owner_policy', dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, 'task-owner-policy:'+scope)), title='Task owner policy'), 'updated', actor)
            return result

    def receipt(self, conn, key, payload):
        if not isinstance(key, str) or not key.strip() or len(key) > 160: raise CRMError('A nonempty idempotency key of at most 160 characters is required')
        check_schema(self.crm, conn, write=True)
        token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
        if token is None: conn.execute(settings.insert().values(key='workspace_id', value=str(uuid.uuid4())))
        scope = scope_for(self.crm, connection=conn)
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        old = conn.execute(select(operations).where(operations.c.scope == scope, operations.c.key == key)).mappings().first()
        if old and old['digest'] != digest: raise CRMError('Idempotency key already used for different data', 409)
        return scope, digest, json.loads(old['response']) if old else None

    def record_receipt(self, conn, key, scope, digest, result):
        conn.execute(operations.insert().values(scope=scope, key=key, digest=digest, response=canonical(result)))

    def expression(self, conn):
        from sqlalchemy import cast, literal
        if not check_schema(self.crm, conn): return cast(literal(None), String(160))
        from .domain import tasks
        return select(owners.c.owner_label).where(owners.c.scope == scope_for(self.crm, connection=conn), owners.c.task_id == tasks.c.id).correlate(tasks).scalar_subquery()
