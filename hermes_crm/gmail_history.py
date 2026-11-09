"""Legacy Gmail table definitions for encrypted export and quarantined recovery only.

Core CRM never connects, reads, polls, clears or migrates provider state. Retain
these exact table names and columns so existing pilot metadata is not lost.
"""
from sqlalchemy import BigInteger, Column, Integer, MetaData, String, Table, Text, UniqueConstraint

metadata = MetaData()
connections = Table('crm_gmail_connections', metadata,
    Column('scope', String(64), primary_key=True), Column('revision', Integer, nullable=False),
    Column('connected', Integer, nullable=False), Column('subject', String(255)),
    Column('mailbox', String(254)), Column('issuer', String(255)), Column('active_operation', String(36)))
operations = Table('crm_gmail_operations', metadata,
    Column('id', String(36), primary_key=True), Column('scope', String(64), nullable=False),
    Column('digest', String(64), nullable=False), Column('kind', String(16), nullable=False),
    Column('state', String(16), nullable=False), Column('reason', String(160), nullable=False),
    Column('contact_id', String(36)), Column('created_at', String(40), nullable=False),
    Column('finished_at', String(40)), Column('days', Integer),
    Column('start_ms', BigInteger), Column('end_ms', BigInteger), Column('coverage', String(32)))
snapshots = Table('crm_gmail_snapshots', metadata,
    Column('key', String(64), primary_key=True), Column('scope', String(64), nullable=False),
    Column('subject', String(255), nullable=False), Column('message_id', String(255), nullable=False),
    Column('payload', Text, nullable=False), Column('observed_at', String(40), nullable=False))
observations = Table('crm_gmail_observations', metadata,
    Column('id', String(36), primary_key=True), Column('scope', String(64), nullable=False),
    Column('snapshot_key', String(64), nullable=False), Column('operation_id', String(36), nullable=False),
    Column('payload', Text, nullable=False), Column('provenance', Text, nullable=False),
    Column('observed_at', String(40), nullable=False),
    UniqueConstraint('operation_id', 'snapshot_key'))
links = Table('crm_gmail_contact_links', metadata,
    Column('scope', String(64), primary_key=True), Column('contact_id', String(36), primary_key=True),
    Column('snapshot_key', String(64), primary_key=True))


def check_schema(crm, conn):
    """Reject partial/incompatible legacy evidence without creating or altering it."""
    from sqlalchemy import inspect
    from .domain import CRMError
    from .report_store import schema_name

    inspector = inspect(conn)
    schema = schema_name(crm)
    tables = tuple(metadata.sorted_tables)
    found = [inspector.has_table(table.name, schema=schema) for table in tables]
    if not any(found):
        return False
    if not all(found):
        raise CRMError('Incomplete legacy Gmail history schema; explicit repair required', 503)
    for table in tables:
        columns = {column['name']: column for column in inspector.get_columns(table.name, schema=schema)}
        if set(columns) != set(table.c.keys()):
            raise CRMError('Incompatible legacy Gmail history schema', 503)
        for column in table.c:
            actual = columns[column.name]
            if (actual['type']._type_affinity is not column.type._type_affinity or
                    actual['nullable'] != column.nullable or
                    getattr(actual['type'], 'length', None) != getattr(column.type, 'length', None)):
                raise CRMError('Incompatible legacy Gmail history column', 503)
        expected_unique = {tuple(column.name for column in constraint.columns)
                           for constraint in table.constraints if isinstance(constraint, UniqueConstraint)}
        actual_unique = {tuple(constraint['column_names'])
                         for constraint in inspector.get_unique_constraints(table.name, schema=schema)}
        # PostgreSQL reflects unique constraints as duplicate backing indexes.
        independent_unique = [index for index in inspector.get_indexes(table.name, schema=schema)
                              if index.get('unique') and not index.get('duplicates_constraint')]
        if (inspector.get_pk_constraint(table.name, schema=schema)['constrained_columns'] !=
                [column.name for column in table.primary_key] or
                expected_unique != actual_unique or independent_unique or
                inspector.get_foreign_keys(table.name, schema=schema) or
                inspector.get_check_constraints(table.name, schema=schema)):
            raise CRMError('Incompatible legacy Gmail history constraints', 503)
    return True
