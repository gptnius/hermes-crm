"""Optional independent acknowledgement ledger; reads never initialize storage."""
from sqlalchemy import Column, Integer, MetaData, String, Table, Text, UniqueConstraint, inspect
from .domain import CRMError
from .report_store import advisory_lock, schema_name

metadata = MetaData()
events = Table('crm_report_review_events_v1', metadata,
    Column('scope', String(64), primary_key=True), Column('id', String(36), primary_key=True),
    Column('family', String(24), nullable=False), Column('assignment_id', String(36), nullable=False),
    Column('report_id', String(160), nullable=False), Column('version', Integer, nullable=False),
    Column('action', String(20), nullable=False), Column('context', Text, nullable=False),
    Column('context_digest', String(64), nullable=False), Column('actor', String(32), nullable=False),
    Column('created_at', String(40), nullable=False),
    UniqueConstraint('scope', 'family', 'assignment_id', 'report_id', 'version'))
operations = Table('crm_report_review_ops_v1', metadata,
    Column('scope', String(64), primary_key=True), Column('key', String(160), primary_key=True),
    Column('request', Text, nullable=False), Column('digest', String(64), nullable=False),
    Column('response', Text, nullable=False))
TABLES = (events, operations)


def check_schema(crm, conn, write=False):
    if write and crm.backend == 'postgres':
        advisory_lock(conn, ['crm-report-review-schema', schema_name(crm)])
    schema = schema_name(crm)
    inspector = inspect(conn)
    present = [inspector.has_table(t.name, schema=schema) for t in TABLES]
    if any(present) and not all(present):
        raise CRMError('Report review schema is incomplete; explicit migration required', 503)
    if not any(present):
        if not write: return False
        metadata.create_all(conn, tables=TABLES)
        inspector = inspect(conn)
    for table in TABLES:
        columns = {c['name']: c for c in inspector.get_columns(table.name, schema=schema)}
        valid = set(columns) == set(table.c.keys())
        if valid:
            valid = all(columns[c.name]['nullable'] == c.nullable
                and columns[c.name]['type']._type_affinity is c.type._type_affinity
                and getattr(columns[c.name]['type'], 'length', None) == getattr(c.type, 'length', None)
                for c in table.c)
        valid = valid and inspector.get_pk_constraint(table.name, schema=schema)['constrained_columns'] == [c.name for c in table.primary_key]
        expected = {tuple(x.columns.keys()) for x in table.constraints if isinstance(x, UniqueConstraint)}
        actual = {tuple(x['column_names']) for x in inspector.get_unique_constraints(table.name, schema=schema)}
        valid = valid and actual == expected and not inspector.get_foreign_keys(table.name, schema=schema)
        # Unique indexes backing the declared constraints are reflected separately
        # on PostgreSQL; unrelated unique indexes change the supported contract.
        valid = valid and all(not x.get('unique') or x.get('duplicates_constraint')
                              for x in inspector.get_indexes(table.name, schema=schema))
        if not valid: raise CRMError('Report review schema is incompatible; explicit migration required', 503)
    return True
