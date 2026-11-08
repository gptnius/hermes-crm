"""Optional protected notes and portable encrypted exports. No key persistence.

Protects stored data without its keys, not a compromised running host. Plain CRM
notes remain ordinary data. There is deliberately no live restore operation.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, UniqueConstraint, inspect, select, update
from .domain import CRMError, TABLES, activity, now

metadata = MetaData()
notes = Table('crm_protected_notes', metadata,
    Column('kind', String(20), primary_key=True), Column('record_id', String(36), primary_key=True),
    Column('version', Integer, nullable=False), Column('envelope', Text, nullable=False))
operations = Table('crm_protected_operations', metadata,
    Column('id', String(36), primary_key=True), Column('key_id', String(64), nullable=False),
    Column('workspace', String(80), nullable=False), Column('kind', String(20), nullable=False),
    Column('record_id', String(36), nullable=False),
    Column('request_mac', String(64), nullable=False), Column('response', Text, nullable=False))
state = Table('crm_protection_schema', metadata,
    Column('id', Integer, primary_key=True), Column('version', Integer, nullable=False))
exports = Table('crm_protected_exports', metadata,
    Column('id', String(36), primary_key=True), Column('workspace', String(80), nullable=False),
    Column('profile', String(160), nullable=False), Column('state', String(20), nullable=False))
MAX_NOTE = 64000
MAX_EXPORT = 32 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def unb64(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid encoding')
    result = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    if b64(result) != value: raise ValueError('Noncanonical encoding')
    return result


@dataclass(frozen=True, repr=False)
class Keyring:
    active: str
    keys: dict

    @classmethod
    def parse(cls, raw):
        try:
            if not isinstance(raw, str) or len(raw) > 4096: raise ValueError()
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result: raise ValueError()
                    result[key] = value
                return result
            data = json.loads(raw, object_pairs_hook=pairs)
            if set(data) != {'active', 'keys'} or not isinstance(data['keys'], dict) or not 1 <= len(data['keys']) <= 8: raise ValueError()
            keys = {}
            for key_id, value in data['keys'].items():
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key_id): raise ValueError()
                key = unb64(value)
                if len(key) != 32: raise ValueError()
                keys[key_id] = key
            if data['active'] not in keys: raise ValueError()
            return cls(data['active'], keys)
        except Exception:
            raise CRMError('Protection key configuration is missing or invalid', 503) from None

    def derive(self, key_id, purpose):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        if key_id not in self.keys: raise CRMError('Required protection key is unavailable', 503)
        return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                    info=('hermes-crm/v1/' + purpose).encode()).derive(self.keys[key_id])


def seal(plaintext, ring, purpose, context):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    header = dict(format='hermes-crm-encrypted', version=1, purpose=purpose, key_id=ring.active, context=context)
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(ring.derive(ring.active, purpose)).encrypt(nonce, plaintext, canonical(header))
    return dict(header, nonce=b64(nonce), ciphertext=b64(ciphertext))


def unseal(envelope, ring, purpose, context, maximum=MAX_EXPORT):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    try:
        if not isinstance(envelope, dict) or set(envelope) != {'format','version','purpose','key_id','context','nonce','ciphertext'}: raise ValueError()
        if envelope['format'] != 'hermes-crm-encrypted' or type(envelope['version']) is not int or envelope['version'] != 1 or envelope['purpose'] != purpose or envelope['context'] != context: raise ValueError()
        if not isinstance(envelope['key_id'], str) or len(envelope['key_id']) > 64: raise ValueError()
        if not isinstance(envelope['ciphertext'], str) or len(envelope['ciphertext']) > (maximum + 16) * 4 // 3 + 4: raise ValueError()
        if not isinstance(envelope['nonce'], str) or len(envelope['nonce']) != 16: raise ValueError()
        nonce = unb64(envelope['nonce'])
        if len(nonce) != 12: raise ValueError()
        ciphertext = unb64(envelope['ciphertext'])
        header = {k:v for k,v in envelope.items() if k not in ('nonce','ciphertext')}
        result = AESGCM(ring.derive(envelope['key_id'], purpose)).decrypt(nonce, ciphertext, canonical(header))
        if len(result) > maximum: raise ValueError()
        return result
    except CRMError: raise
    except Exception:
        raise CRMError('Protected data could not be authenticated', 422) from None


def owned_tables():
    # Explicit module allowlist; never reflect arbitrary tables or export files.
    from . import domain, customization, execution, gmail_history, native_work, native_work_operations, report_interactions, report_store
    from .relationship_schema import OWNED_TABLES
    from .task_ownership import OWNED_TABLES as OWNER_TABLES
    return {t.name:t for module in (domain, customization, execution, gmail_history,
        native_work, native_work_operations, report_interactions, report_store)
        for t in module.metadata.tables.values()} | {t.name:t for t in metadata.tables.values()} | {
            t.name:t for t in (*OWNED_TABLES, *OWNER_TABLES)}  # Never export the private registry's legacy FK clones.


def _native_export_predicates(crm, conn, workspace, exported_tables):
    """Scope native history within this export snapshot, without creating stores.

    Profile-specific datastore selection is the normal boundary. Copied/mixed datastores
    must still honor the same row ownership as native-work reads. FK metadata
    clones do not make shared CRM tables native-owned.
    """
    from .native_work import NativeWorkStore, assignments, events, reports
    from .native_work_operations import operations as work_operations
    work = NativeWorkStore(crm, initialize=False, connection=conn, workspace=workspace)
    schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
    inspector = inspect(conn)
    if inspector.has_table(work_operations.name, schema=schema):
        if not work.available:
            raise CRMError('Native operation storage has no native-work schema', 503)
        # WorkOperationStore's constructor uses another connection. Validate its
        # exact table contract here so export keeps one read-only snapshot.
        table = work_operations
        columns = {c['name']: c for c in inspector.get_columns(table.name, schema=schema)}
        compatible = set(columns) == set(table.c.keys())
        if compatible:
            compatible = all(columns[c.name]['nullable'] == c.nullable and
                columns[c.name]['type']._type_affinity is c.type._type_affinity and
                getattr(columns[c.name]['type'], 'length', None) == getattr(c.type, 'length', None)
                for c in table.c)
        unique = {tuple(c['column_names']) for c in inspector.get_unique_constraints(table.name, schema=schema)}
        expected_unique = {tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)}
        foreign = {(tuple(c['constrained_columns']), c['referred_table'], tuple(c['referred_columns']))
                   for c in inspector.get_foreign_keys(table.name, schema=schema)}
        expected_foreign = {(tuple(c.parent.name for c in constraint.elements), constraint.referred_table.name,
            tuple(c.column.name for c in constraint.elements)) for constraint in table.foreign_key_constraints}
        compatible = compatible and unique == expected_unique and foreign == expected_foreign
        compatible = compatible and inspector.get_pk_constraint(table.name, schema=schema).get('constrained_columns') == ['id']
        if not compatible:
            raise CRMError('Native operation schema is incompatible; explicit migration required', 503)
    # The legacy registry can contain FK clones from another module. Predicates
    # must use the exact selected Table object, not introduce a duplicate FROM.
    assignments, events, reports, work_operations = (exported_tables[t.name]
        for t in (assignments, events, reports, work_operations))
    scope = (assignments.c.workspace == workspace, assignments.c.profile == crm.profile)
    scoped_ids = select(assignments.c.id).where(*scope)
    return {
        assignments.name: scope,
        events.name: (events.c.assignment_id.in_(scoped_ids),),
        reports.name: (reports.c.workspace == workspace, reports.c.profile == crm.profile,
                       reports.c.assignment_id.in_(scoped_ids)),
        work_operations.name: (work_operations.c.workspace == workspace, work_operations.c.profile == crm.profile,
                               work_operations.c.assignment_id.in_(scoped_ids)),
    }


class ProtectionStore:
    def __init__(self, crm):
        self.crm = crm
        self.workspace = crm.workspace_token()

    def _context(self, kind, record_id, version):
        return dict(workspace=self.workspace, profile=self.crm.profile, kind=kind, record_id=record_id, note_version=version)

    def _exists(self, conn):
        schema = self.crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
        inspector = inspect(conn)
        tables = tuple(metadata.tables.values())
        present = [inspector.has_table(t.name, schema=schema) for t in tables]
        if not any(present): return False
        if not all(present): raise CRMError('Incomplete protection storage', 503)
        for table in tables:
            columns = {c['name']:c for c in inspector.get_columns(table.name, schema=schema)}
            if set(columns) != set(table.c.keys()): raise CRMError('Incompatible protection storage', 503)
            for column in table.c:
                actual = columns[column.name]
                if (actual['type']._type_affinity is not column.type._type_affinity
                    or getattr(actual['type'],'length',None) != getattr(column.type,'length',None)
                    or actual['nullable'] != column.nullable):
                    raise CRMError('Incompatible protection storage', 503)
            if set(inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns']) != {c.name for c in table.primary_key}:
                raise CRMError('Incompatible protection primary key',503)
        rows = conn.execute(select(state)).mappings().all()
        if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['version'] != 1:
            raise CRMError('Unsupported protection schema version',503)
        return True

    def initialize(self, conn):
        if not self._exists(conn):
            metadata.create_all(conn)
            conn.execute(state.insert().values(id=1,version=1))
        self._exists(conn)

    def _record(self, conn, kind, record_id):
        if kind not in TABLES or not isinstance(record_id, str) or not 1 <= len(record_id) <= 36: raise CRMError('Invalid record reference')
        # Do not load ordinary notes/custom fields into this sensitive operation.
        record = conn.execute(select(TABLES[kind].c.version).where(TABLES[kind].c.id == record_id)).scalar()
        if record is None: raise CRMError('Record not found', 404)
        return record

    def _note(self, conn, kind, record_id):
        return conn.execute(select(notes).where(notes.c.kind == kind, notes.c.record_id == record_id)).mappings().first() if self._exists(conn) else None

    def status(self, kind, record_id):
        with self.crm._read_connection() as conn:
            version = self._record(conn, kind, record_id)
            note = self._note(conn, kind, record_id)
            return dict(record_version=version, note_version=note['version'] if note else 0, has_note=bool(note))

    def reveal(self, kind, record_id, ring):
        with self.crm._read_connection() as conn:
            version = self._record(conn, kind, record_id)
            note = self._note(conn, kind, record_id)
            plaintext = unseal(json.loads(note['envelope']), ring, 'notes', self._context(kind, record_id, note['version']), MAX_NOTE).decode() if note else ''
            return dict(record_version=version, note_version=note['version'] if note else 0, has_note=bool(note), plaintext=plaintext)

    def save(self, kind, record_id, *, ring, operation_id, expected_record_version, expected_note_version, plaintext):
        try:
            if str(uuid.UUID(operation_id)) != operation_id: raise ValueError()
        except Exception: raise CRMError('Invalid operation identifier') from None
        if type(expected_record_version) is not int or expected_record_version < 1 or type(expected_note_version) is not int or expected_note_version < 0: raise CRMError('Invalid expected versions')
        if not isinstance(plaintext, str) or len(plaintext) > 16000 or len(plaintext.encode()) > MAX_NOTE: raise CRMError('Protected note exceeds limit')
        request = canonical([self._context(kind,record_id,expected_note_version), expected_record_version, plaintext])
        with self.crm.engine.begin() as conn:
            self.crm._catalog_lock(conn)
            # Initialize additively inside the serialized write transaction.
            self.initialize(conn)
            retry = conn.execute(select(operations).where(operations.c.id == operation_id)).mappings().first()
            key_id = retry['key_id'] if retry else ring.active
            mac = hmac.new(ring.derive(key_id, 'notes-request-mac'), request, hashlib.sha256).hexdigest()
            if retry:
                if not hmac.compare_digest(retry['request_mac'], mac): raise CRMError('Operation identifier already used', 409)
                return json.loads(retry['response'])
            version = self._record(conn, kind, record_id)
            note = self._note(conn, kind, record_id)
            note_version = note['version'] if note else 0
            if version != expected_record_version or note_version != expected_note_version: raise CRMError('Record or protected note changed; refresh before editing', 409)
            next_version = note_version + 1
            envelope = seal(plaintext.encode(), ring, 'notes', self._context(kind,record_id,next_version))
            values = dict(version=next_version, envelope=canonical(envelope).decode())
            if note: conn.execute(update(notes).where(notes.c.kind == kind, notes.c.record_id == record_id, notes.c.version == note_version).values(**values))
            else: conn.execute(notes.insert().values(kind=kind, record_id=record_id, **values))
            changed = conn.execute(update(TABLES[kind]).where(TABLES[kind].c.id == record_id, TABLES[kind].c.version == version).values(version=version+1, updated_at=now()))
            if changed.rowcount != 1: raise CRMError('Record changed; refresh before editing', 409)
            response = dict(record_version=version+1, note_version=next_version, has_note=True)
            conn.execute(operations.insert().values(id=operation_id, key_id=key_id, workspace=self.workspace, kind=kind, record_id=record_id, request_mac=mac, response=canonical(response).decode()))
            conn.execute(activity.insert().values(id=str(uuid.uuid4()), entity_type=kind, entity_id=record_id, action='protected_note_updated', actor='desktop', summary='Protected note updated', created_at=now()))
            return response

    def operation(self, kind, record_id, operation_id):
        try:
            if str(uuid.UUID(operation_id)) != operation_id: raise ValueError()
        except Exception: raise CRMError('Invalid operation identifier') from None
        with self.crm._read_connection() as conn:
            self._record(conn, kind, record_id)
            receipt = conn.execute(select(operations.c.response).where(
                operations.c.id == operation_id, operations.c.workspace == self.workspace,
                operations.c.kind == kind, operations.c.record_id == record_id)).scalar() if self._exists(conn) else None
            if receipt is None: return dict(operation_id=operation_id, state='unknown')
            return dict(json.loads(receipt), operation_id=operation_id, state='committed')

    def export(self, ring, *, connection=None):
        tables = owned_tables()
        snapshot = dict(format='hermes-crm-export', version=1, workspace=self.workspace, profile=self.crm.profile, tables={})
        size = 0
        with (nullcontext(connection) if connection is not None else self.crm._read_connection()) as conn:
            schema = self.crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
            self._exists(conn)
            inspector = inspect(conn)
            from .relationship_schema import OWNED_TABLES, check_schema
            from .relationship_queries import audit_scope_predicate
            from .report_store import scope_for
            from .task_ownership import OWNED_TABLES as OWNER_TABLES, check_schema as check_owner_schema
            check_owner_schema(self.crm, conn)
            relationship_names = {table.name for table in (*OWNED_TABLES, *OWNER_TABLES)}
            check_schema(self.crm, conn)  # Reject partial/incompatible additive stores.
            relationship_scope = scope_for(self.crm, connection=conn)
            native_predicates = _native_export_predicates(self.crm, conn, self.workspace, tables)
            for name, table in sorted(tables.items()):
                if not inspector.has_table(name, schema=schema): continue
                rows = []
                query = select(table)
                if name in relationship_names and 'scope' in table.c:
                    query = query.where(table.c.scope == relationship_scope)
                elif name in native_predicates:
                    query = query.where(*native_predicates[name])
                elif name == 'crm_activity':
                    query = query.where(audit_scope_predicate(self.crm, conn))
                for row in conn.execute(query).mappings():
                    data = dict(row)
                    size += len(canonical(data)) + 1
                    if size > MAX_EXPORT - 65536: raise CRMError('Encrypted export exceeds size limit', 413)
                    rows.append(data)
                snapshot['tables'][name] = rows
        payload = canonical(snapshot)
        if len(payload) > MAX_EXPORT: raise CRMError('Encrypted export exceeds size limit', 413)
        return seal(payload, ring, 'backup', dict(workspace=self.workspace, profile=self.crm.profile))


def decrypt_export(envelope, ring, *, workspace, profile):
    """Offline authenticated inspection only. Never writes any live database."""
    value = json.loads(unseal(envelope, ring, 'backup', dict(workspace=workspace, profile=profile)))
    registry = owned_tables()
    if set(value) != {'format','version','workspace','profile','tables'} or value['format'] != 'hermes-crm-export' or value['version'] != 1 or value['workspace'] != workspace or value['profile'] != profile or not isinstance(value['tables'], dict) or set(value['tables']) - set(registry):
        raise CRMError('Invalid encrypted export payload', 422)
    for name, rows in value['tables'].items():
        if not isinstance(rows, list) or any(not isinstance(row,dict) or set(row) != set(registry[name].c.keys()) for row in rows): raise CRMError('Invalid encrypted export table', 422)
    return value


def decrypt_export_artifact(artifact, ring, *, workspace, profile, export_id=None):
    """Validate a downloaded JSON artifact and return its CRM table snapshot."""
    try:
        if not isinstance(artifact, dict) or set(artifact) != {'export_id','envelope','operation_mac'}: raise ValueError()
        if str(uuid.UUID(artifact['export_id'])) != artifact['export_id']: raise ValueError()
        if export_id is not None and artifact['export_id'] != export_id: raise ValueError()
        key_id = artifact['envelope']['key_id']
        if not isinstance(key_id,str) or len(key_id)>64: raise ValueError()
        expected = hmac.new(ring.derive(key_id, 'export-operation'), canonical({k:v for k,v in artifact.items() if k != 'operation_mac'}), hashlib.sha256).hexdigest()
        if not isinstance(artifact['operation_mac'],str) or not hmac.compare_digest(expected,artifact['operation_mac']): raise ValueError()
    except CRMError: raise
    except Exception: raise CRMError('Export could not be authenticated', 422) from None
    return decrypt_export(artifact['envelope'], ring, workspace=workspace, profile=profile)
