"""Private additive relationship registry. Legacy clones are never owned/exported."""
from sqlalchemy import Column, Integer, String, Text, MetaData, Table, ForeignKey, ForeignKeyConstraint, inspect, select
from .domain import metadata as legacy_metadata, CRMError
from .report_store import schema_name, advisory_lock
metadata = MetaData()
for _name in ('crm_contacts', 'crm_deals', 'crm_tasks'):
    legacy_metadata.tables[_name].to_metadata(metadata)

def base():
    return [Column('scope',String(64),primary_key=True),Column('id',String(36),primary_key=True),Column('version',Integer,nullable=False),Column('created_at',String(40),nullable=False),Column('updated_at',String(40),nullable=False)]
companies = Table('crm_companies',metadata,*base(),Column('name',String(160),nullable=False),Column('domain',String(254)),Column('notes',Text,nullable=False),Column('archived_at',String(40)))
contact_companies = Table('crm_contact_companies',metadata,Column('scope',String(64),primary_key=True),Column('contact_id',String(36),ForeignKey('crm_contacts.id'),primary_key=True),Column('company_id',String(36),nullable=False),Column('created_at',String(40),nullable=False),Column('updated_at',String(40),nullable=False),ForeignKeyConstraint(['scope','company_id'],['crm_companies.scope','crm_companies.id']))
events = Table('crm_events',metadata,*base(),Column('title',String(200),nullable=False),Column('kind',String(20),nullable=False),Column('starts_at',String(40),nullable=False),Column('ends_at',String(40),nullable=False),Column('timezone',String(100),nullable=False),Column('contact_id',String(36),ForeignKey('crm_contacts.id')),Column('deal_id',String(36),ForeignKey('crm_deals.id')),Column('company_id',String(36)),Column('notes',Text,nullable=False),Column('status',String(20),nullable=False),Column('outcome_happened_at',String(40)),Column('recorded_at',String(40)),Column('outcome_summary',Text),Column('source',String(20),nullable=False),Column('outcome_provenance',String(20)),ForeignKeyConstraint(['scope','company_id'],['crm_companies.scope','crm_companies.id']))
event_revisions = Table('crm_event_revisions',metadata,Column('scope',String(64),primary_key=True),Column('event_id',String(36),primary_key=True),Column('version',Integer,primary_key=True),Column('record',Text,nullable=False),Column('reason',Text,nullable=False),Column('actor',String(160),nullable=False),Column('created_at',String(40),nullable=False),ForeignKeyConstraint(['scope','event_id'],['crm_events.scope','crm_events.id']))
operations = Table('crm_relationship_operations',metadata,Column('scope',String(64),primary_key=True),Column('key',String(160),primary_key=True),Column('digest',String(64),nullable=False),Column('response',Text,nullable=False))
schema_state = Table('crm_relationship_schema',metadata,Column('id',Integer,primary_key=True),Column('version',Integer,nullable=False))
event_tasks = Table('crm_event_tasks',metadata,Column('scope',String(64),primary_key=True),Column('task_id',String(36),ForeignKey('crm_tasks.id'),primary_key=True),Column('event_id',String(36),nullable=False),Column('created_at',String(40),nullable=False),Column('updated_at',String(40),nullable=False),ForeignKeyConstraint(['scope','event_id'],['crm_events.scope','crm_events.id']))
OWNED_TABLES = (companies,contact_companies,events,event_revisions,event_tasks,operations,schema_state)
SCHEMA_VERSION = 1

def check_schema(crm,conn,write=False):
    if write and crm.backend == 'postgres': advisory_lock(conn,['crm-relationship-schema',schema_name(crm)])
    inspector=inspect(conn); schema=schema_name(crm)
    present=[inspector.has_table(t.name,schema=schema) for t in OWNED_TABLES]
    if any(present) and not all(present): raise CRMError('Relationship schema is incomplete; explicit migration required',503)
    if not any(present):
        if not write: return False
        metadata.create_all(conn,tables=OWNED_TABLES)
        conn.execute(schema_state.insert().values(id=1,version=SCHEMA_VERSION))
        inspector=inspect(conn)
    for table in OWNED_TABLES:
        actual={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
        if set(actual)!=set(table.c.keys()): raise CRMError('Incompatible relationship columns',503)
        for col in table.c:
            found=actual[col.name]
            if (found['type']._type_affinity is not col.type._type_affinity or found['nullable']!=col.nullable or getattr(found['type'],'length',None)!=getattr(col.type,'length',None)): raise CRMError('Incompatible relationship column',503)
        if inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns'] != [c.name for c in table.primary_key]: raise CRMError('Incompatible relationship primary key',503)
        expected={(tuple(f.column_keys),tuple(e.column.table.name for e in f.elements),tuple(e.column.name for e in f.elements)) for f in table.foreign_key_constraints}
        reflected_fks=inspector.get_foreign_keys(table.name,schema=schema)
        allowed_schemas = (schema,) if crm.backend == 'postgres' and schema is not None else (None, schema)
        if any(f.get('options') or f.get('referred_schema') not in allowed_schemas for f in reflected_fks): raise CRMError('Incompatible relationship foreign key options or target schema',503)
        actual_fk={(tuple(f['constrained_columns']),tuple([f['referred_table']]*len(f['referred_columns'])),tuple(f['referred_columns'])) for f in reflected_fks}
        if expected != actual_fk: raise CRMError('Incompatible relationship foreign keys',503)
        if inspector.get_unique_constraints(table.name,schema=schema) or any(i.get('unique') for i in inspector.get_indexes(table.name,schema=schema)): raise CRMError('Unexpected relationship unique constraints',503)
    rows=conn.execute(select(schema_state)).mappings().all()
    if len(rows)!=1 or rows[0]['id']!=1 or rows[0]['version']!=SCHEMA_VERSION: raise CRMError('Unsupported relationship schema version',503)
    return True
