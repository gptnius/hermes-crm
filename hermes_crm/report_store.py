"""Workspace-scoped, lazy, versioned report and dashboard storage."""
from __future__ import annotations
import hashlib
import json
import threading
import uuid
from contextlib import contextmanager
from typing import Literal
from pydantic import Field, model_validator
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, inspect, select, update, text
from sqlalchemy.exc import IntegrityError
from .domain import CRMError, StrictModel, now, settings

metadata = MetaData()
reports = Table('crm_saved_reports', metadata,
    Column('scope', String(64), primary_key=True), Column('id', String(36), primary_key=True),
    Column('version', Integer, nullable=False), Column('title', String(160), nullable=False),
    Column('definition', Text, nullable=False), Column('created_at', String(40), nullable=False),
    Column('updated_at', String(40), nullable=False), Column('archived_at', String(40)))
revisions = Table('crm_saved_report_versions', metadata,
    Column('scope', String(64), primary_key=True), Column('id', String(36), primary_key=True),
    Column('version', Integer, primary_key=True), Column('record', Text, nullable=False))
dashboards = Table('crm_saved_dashboards', metadata,
    Column('scope', String(64), primary_key=True), Column('id', String(36), nullable=False),
    Column('version', Integer, nullable=False), Column('cards', Text, nullable=False),
    Column('created_at', String(40), nullable=False), Column('updated_at', String(40), nullable=False))
operations = Table('crm_report_operations', metadata,
    Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True),
    Column('digest', String(64), nullable=False), Column('response', Text, nullable=False))
_LOCK = threading.RLock()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)

def scope_for(crm, write=False, connection=None):
    if write:
        token = crm.workspace_token()
    elif connection is not None:
        token = connection.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
    else:
        with crm.engine.connect() as conn:
            token = conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
    return hashlib.sha256(canonical([token, crm.profile]).encode()).hexdigest() if token else None

def schema_name(crm):
    return (crm.engine.get_execution_options().get('schema_translate_map') or {}).get(None)

def advisory_lock(conn, identity):
    # Stable signed bigint, scoped by schema/workspace or operation key.
    number = int.from_bytes(hashlib.sha256(canonical(identity).encode()).digest()[:8], 'big', signed=True)
    conn.execute(text('SELECT pg_advisory_xact_lock(:number)'), {'number': number})

def check_tables(crm, tables, write=False, connection=None):
    """Never silently repair an existing/partial or incompatible schema."""
    if write:
        with transaction(crm) as conn:
            if crm.backend == 'postgres':
                advisory_lock(conn, ['crm-report-schema', schema_name(crm)])
            return _check_tables(crm, tables, True, conn)
    if connection is not None:
        return _check_tables(crm, tables, False, connection)
    with crm.engine.connect() as conn:
        return _check_tables(crm, tables, False, conn)

def _check_tables(crm, tables, write, conn):
    inspector = inspect(conn)
    schema = schema_name(crm)
    present = [inspector.has_table(t.name, schema=schema) for t in tables]
    if any(present) and not all(present):
        raise CRMError('Report storage schema is incomplete; explicit migration required', 503)
    if not any(present):
        if not write: return False
        tables[0].metadata.create_all(conn, tables=tables)
        inspector = inspect(conn)
    for table in tables:
        actual = {c['name']: c for c in inspector.get_columns(table.name, schema=schema)}
        if set(actual) != set(table.c.keys()):
            raise CRMError('Report storage schema is incompatible; explicit migration required', 503)
        for c in table.c:
            a = actual[c.name]
            if (a['type']._type_affinity is not c.type._type_affinity
                    or a['nullable'] != c.nullable
                    or getattr(a['type'], 'length', None) != getattr(c.type, 'length', None)):
                raise CRMError('Report storage column is incompatible', 503)
        pk = inspector.get_pk_constraint(table.name, schema=schema)['constrained_columns']
        if set(pk) != {c.name for c in table.primary_key}:
            raise CRMError('Report storage key is incompatible', 503)
    return True

@contextmanager
def transaction(crm):
    with _LOCK, crm.engine.connect() as conn:
        try:
            if crm.backend == 'sqlite': conn.exec_driver_sql('BEGIN IMMEDIATE')
            else: conn.begin()
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

class ScopedStore:
    tables = []
    def __init__(self, crm): self.crm = crm
    def exists(self): return check_tables(self.crm, self.tables)
    def _write(self, key, payload, action):
        if not isinstance(key, str) or not key.strip() or len(key) > 160:
            raise CRMError('A nonempty idempotency key of at most 160 characters is required')
        digest = hashlib.sha256(canonical(payload).encode()).hexdigest()
        with _LOCK:
            check_tables(self.crm, self.tables, write=True)
            scope = scope_for(self.crm, True)
        try:
            with transaction(self.crm) as conn:
                if self.crm.backend == 'postgres':
                    advisory_lock(conn, ['crm-report-operation', schema_name(self.crm), self.operation_table.name, scope, key])
                old = conn.execute(select(self.operation_table).where(self.operation_table.c.scope == scope, self.operation_table.c.key == key)).mappings().first()
                if old:
                    if old['digest'] != digest: raise CRMError('Idempotency key already used for different data', 409)
                    return json.loads(old['response'])
                result = action(conn, scope)
                conn.execute(self.operation_table.insert().values(scope=scope,key=key,digest=digest,response=canonical(result)))
                return result
        except IntegrityError:
            with self.crm.engine.connect() as conn:
                old = conn.execute(select(self.operation_table).where(self.operation_table.c.scope == scope, self.operation_table.c.key == key)).mappings().first()
                if old and old['digest'] == digest: return json.loads(old['response'])
            raise CRMError('Concurrent write conflict; refresh and retry', 409)
    @staticmethod
    def _version(value, minimum=1):
        if type(value) is not int or value < minimum: raise CRMError('A current integer version is required', 409)

class ReportInput(StrictModel):
    title: str = Field(min_length=1, max_length=160)

class DashboardCard(StrictModel):
    id: str
    report_id: str
    report_version: int = Field(strict=True, ge=1)
    visualization: Literal['metric', 'table', 'bar', 'line', 'donut']
    title: str | None = Field(default=None, max_length=160)
    @model_validator(mode='after')
    def identifiers(self):
        for value in (self.id, self.report_id):
            if str(uuid.UUID(value)) != value: raise ValueError('Use canonical UUID identifiers')
        return self

class DashboardInput(StrictModel):
    cards: list[DashboardCard] = Field(max_length=12)
    @model_validator(mode='after')
    def unique_cards(self):
        if len({c.id for c in self.cards}) != len(self.cards): raise ValueError('Card identifiers must be unique')
        return self

class ReportStore(ScopedStore):
    tables = [reports, revisions, dashboards, operations]
    operation_table = operations
    def _definition(self, definition):
        from .reports import ReportDefinition
        return ReportDefinition.model_validate(definition).model_dump(mode="json", exclude_none=True)
    @staticmethod
    def _decode(row):
        record = dict(row)
        record.pop('scope', None)
        record['definition'] = json.loads(record['definition'])
        return record
    def _get(self, conn, scope, record_id, version=None):
        if version is not None:
            self._version(version)
            row = conn.execute(select(revisions.c.record).where(revisions.c.scope == scope, revisions.c.id == record_id, revisions.c.version == version)).scalar()
            if row is None: raise CRMError('Saved report version not found', 404)
            return json.loads(row)
        row = conn.execute(select(reports).where(reports.c.scope == scope, reports.c.id == record_id)).mappings().first()
        if row is None: raise CRMError('Saved report not found', 404)
        return self._decode(row)
    def get(self, record_id, version=None):
        if not self.exists(): raise CRMError('Saved report not found', 404)
        with self.crm.engine.connect() as conn: return self._get(conn, scope_for(self.crm), record_id, version)
    def list(self, include_archived=False, limit=50, offset=0):
        self.crm._integer(limit, 'limit', 1, 100); self.crm._integer(offset, 'offset')
        if type(include_archived) is not bool: raise CRMError('include_archived must be boolean')
        if not self.exists(): return dict(items=[], total=0, limit=limit, offset=offset)
        from sqlalchemy import func
        stmt = select(reports).where(reports.c.scope == scope_for(self.crm))
        if not include_archived: stmt = stmt.where(reports.c.archived_at.is_(None))
        with self.crm.engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
            items = [self._decode(r) for r in conn.execute(stmt.order_by(reports.c.created_at, reports.c.id).limit(limit).offset(offset)).mappings()]
        return dict(items=items,total=total,limit=limit,offset=offset)
    def _revision(self, conn, scope, record):
        conn.execute(revisions.insert().values(scope=scope,id=record['id'],version=record['version'],record=canonical(record)))
    def create(self, title, definition, key):
        title = ReportInput(title=title).title
        definition = self._definition(definition)
        def action(conn, scope):
            stamp = now()
            result = dict(id=str(uuid.uuid4()),version=1,title=title,definition=definition,created_at=stamp,updated_at=stamp,archived_at=None)
            conn.execute(reports.insert().values(scope=scope, **dict(result, definition=canonical(definition))))
            self._revision(conn,scope,result)
            return result
        return self._write(key,['create',title,definition],action)
    def _change(self, record_id, expected_version, key, changes, operation):
        self._version(expected_version)
        def action(conn, scope):
            old = self._get(conn,scope,record_id)
            if old['version'] != expected_version: raise CRMError('Saved report changed; refresh before editing',409)
            values = dict(changes)
            if operation == 'archive': values['archived_at'] = now()
            if operation == 'restore': values['archived_at'] = None
            result = dict(old, **values, version=expected_version+1, updated_at=now())
            db_values = dict(result); db_values.pop('id'); db_values['definition'] = canonical(result['definition'])
            changed = conn.execute(update(reports).where(reports.c.scope == scope,reports.c.id == record_id,reports.c.version == expected_version).values(**db_values))
            if changed.rowcount != 1: raise CRMError('Saved report changed; refresh before editing',409)
            self._revision(conn,scope,result)
            return result
        return self._write(key,[operation,record_id,expected_version,changes],action)
    def update(self, record_id, title, definition, expected_version, key):
        return self._change(record_id,expected_version,key,dict(title=ReportInput(title=title).title,definition=self._definition(definition)),'update')
    def archive(self, record_id, expected_version, key): return self._change(record_id,expected_version,key,{},'archive')
    def restore(self, record_id, expected_version, key): return self._change(record_id,expected_version,key,{},'restore')
    def get_dashboard(self):
        empty = dict(id=None,version=0,cards=[],created_at=None,updated_at=None)
        if not self.exists(): return empty
        scope = scope_for(self.crm)
        with self.crm.engine.connect() as conn:
            row = conn.execute(select(dashboards).where(dashboards.c.scope == scope)).mappings().first()
            if row is None: return empty
            result = dict(row); result.pop('scope'); result['cards'] = json.loads(result['cards'])
            for card in result['cards']:
                try:
                    latest = self._get(conn,scope,card['report_id'])
                    pinned = self._get(conn,scope,card['report_id'],card['report_version'])
                    card['reference_status'] = 'archived' if latest['archived_at'] else ('outdated' if latest['version'] != pinned['version'] else 'active')
                    card['report'] = pinned
                except CRMError as error:
                    if error.status != 404: raise
                    card['reference_status'] = 'missing'
            return result
    def save_dashboard(self, cards, expected_version, key):
        self._version(expected_version,0)
        cards = DashboardInput(cards=cards).model_dump(mode='json')['cards']
        def action(conn,scope):
            old = conn.execute(select(dashboards).where(dashboards.c.scope == scope)).mappings().first()
            if (old['version'] if old else 0) != expected_version: raise CRMError('Dashboard changed; refresh before editing',409)
            previous = json.loads(old['cards']) if old else []
            previous_refs = {(c['report_id'],c['report_version']) for c in previous}
            for card in cards:
                # Existing broken references remain visible, but new references must resolve.
                if (card['report_id'],card['report_version']) not in previous_refs:
                    latest = self._get(conn,scope,card['report_id'])
                    pinned = self._get(conn,scope,card['report_id'],card['report_version'])
                    if latest['archived_at']: raise CRMError('Cannot add an archived report to a dashboard',409)
            from .reports import FIELDS
            for card in cards:
                try: definition = self._get(conn,scope,card['report_id'],card['report_version'])['definition']
                except CRMError as error:
                    if error.status != 404: raise
                    continue
                visual = card['visualization']
                group = definition.get('group_by')
                if visual != 'table' and not definition.get('measure'):
                    raise CRMError('Charts require a measure')
                if visual == 'metric' and group:
                    raise CRMError('A metric requires an ungrouped measure')
                if visual in ('bar','line','donut') and not group:
                    raise CRMError('This chart requires a grouping')
                if visual == 'line' and FIELDS[definition['entity']][group['field']]['type'] not in ('date','datetime'):
                    raise CRMError('Line charts require date grouping')
            stamp = now()
            result = dict(id=old['id'] if old else str(uuid.uuid4()),version=expected_version+1,cards=cards,created_at=old['created_at'] if old else stamp,updated_at=stamp)
            values = dict(result,cards=canonical(cards))
            if old:
                changed = conn.execute(update(dashboards).where(dashboards.c.scope == scope,dashboards.c.version == expected_version).values(**values))
                if changed.rowcount != 1: raise CRMError('Dashboard changed; refresh before editing',409)
            else: conn.execute(dashboards.insert().values(scope=scope,**values))
            return result
        return self._write(key,['dashboard',expected_version,cards],action)
