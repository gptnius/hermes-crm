"""Lazy additive Gmail bridge schema, deliberately outside legacy metadata.

Recovery must quarantine every crm_gmail_bridge_* table: state contains mailbox,
explicit aliases, local account UUIDs, selector fingerprints, cursors, metadata,
leases and observation provenance; receipts contain operation outcomes/digests.
No credentials, provider subject, body, snippet or Bcc is stored. Scoped encrypted
backups include this metadata; restore quarantines it and initializes only the
schema marker. Ambiguity review never infers a record association.
"""
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, inspect, select
from .domain import CRMError
from .report_store import advisory_lock, schema_name

metadata = MetaData()
state = Table('crm_gmail_bridge_state', metadata,
    Column('scope', String(64), primary_key=True), Column('payload', Text, nullable=False))
receipts = Table('crm_gmail_bridge_receipts', metadata,
    Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True),
    Column('digest', String(64), nullable=False), Column('response', Text, nullable=False),
    Column('revision', Integer, nullable=False), Column('protected', Integer, nullable=False))
version = Table('crm_gmail_bridge_schema', metadata,
    Column('id', Integer, primary_key=True), Column('version', Integer, nullable=False))
messages = Table('crm_gmail_bridge_messages', metadata,
    Column('scope', String(64), primary_key=True),
    Column('account_namespace', String(36), primary_key=True),
    Column('message_id', String(255), primary_key=True),
    Column('payload', Text, nullable=False))
aliases = Table('crm_gmail_bridge_aliases', metadata,
    Column('scope', String(64), primary_key=True),
    Column('contact_id', String(36), primary_key=True),
    Column('contact_version', Integer, nullable=False),
    Column('addresses', Text, nullable=False))
control_receipts = Table('crm_gmail_bridge_control_receipts', metadata,
    Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True),
    Column('digest', String(64), nullable=False), Column('response', Text, nullable=False),
    Column('revision', Integer, nullable=False))
OWNED_TABLES = (state, receipts, version, messages, aliases, control_receipts)

def check_schema(crm, conn, write=False):
    if write and crm.backend == 'postgres':
        advisory_lock(conn, ['crm-gmail-bridge-schema', schema_name(crm)])
    inspector = inspect(conn)
    schema = schema_name(crm)
    found = [inspector.has_table(t.name, schema=schema) for t in OWNED_TABLES]
    if any(found) and not all(found):
        raise CRMError('Incomplete Gmail bridge schema; explicit migration required', 503)
    if not any(found):
        if not write:
            return False
        metadata.create_all(conn, tables=OWNED_TABLES)
        conn.execute(version.insert().values(id=1, version=1))
        inspector = inspect(conn)
    for table in OWNED_TABLES:
        columns = {c['name']: c for c in inspector.get_columns(table.name, schema=schema)}
        if set(columns) != set(table.c.keys()):
            raise CRMError('Incompatible Gmail bridge schema', 503)
        for col in table.c:
            actual = columns[col.name]
            if (actual['type']._type_affinity is not col.type._type_affinity or
                    actual['nullable'] != col.nullable or
                    getattr(actual['type'], 'length', None) != getattr(col.type, 'length', None)):
                raise CRMError('Incompatible Gmail bridge column', 503)
        if (inspector.get_pk_constraint(table.name, schema=schema)['constrained_columns'] !=
                [c.name for c in table.primary_key] or
                inspector.get_foreign_keys(table.name, schema=schema) or
                inspector.get_unique_constraints(table.name, schema=schema) or
                inspector.get_check_constraints(table.name, schema=schema) or
                any(i.get('unique') for i in inspector.get_indexes(table.name, schema=schema))):
            raise CRMError('Incompatible Gmail bridge constraints', 503)
    rows = conn.execute(select(version)).mappings().all()
    if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['version'] != 1:
        raise CRMError('Unsupported Gmail bridge schema version', 503)
    return True
