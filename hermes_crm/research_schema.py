"""Additive research storage. Read paths never initialize storage."""
from sqlalchemy import Column, Integer, String, Text, Table, MetaData
metadata = MetaData()
schema_state = Table('crm_research_schema', metadata, Column('id',Integer,primary_key=True),Column('version',Integer,nullable=False))
def scoped(name, *columns):
    return Table(name,metadata,Column('scope',String(64),primary_key=True),Column('id',String(36),primary_key=True),*columns)
def s(name,length=64): return Column(name,String(length),nullable=False)
evidence=scoped('crm_research_evidence',s('target_kind',20),s('target_id',36),Column('packet',Text,nullable=False),s('digest'),Column('lifecycle_version',Integer,nullable=False),Column('archived_at',String(40)),s('recorded_at',40),s('recorded_actor',160))
proposals=scoped('crm_research_proposals',s('target_kind',20),s('target_id',36),s('evidence_id',36),s('evidence_digest'),Column('evidence_lifecycle_version',Integer,nullable=False),Column('proposal_version',Integer,nullable=False),s('status',20),Column('target_version',Integer,nullable=False),s('before_hash'),s('after_hash'),Column('addition',Text,nullable=False),s('proposal_digest'),s('created_at',40),s('created_actor',160),Column('receipt',Text))
operations=Table('crm_research_operations',metadata,Column('scope',String(64),primary_key=True),Column('key',String(160),primary_key=True),s('digest'),Column('response',Text,nullable=False))
OWNED_TABLES=(schema_state,evidence,proposals,operations)
SCHEMA_VERSION=1

from sqlalchemy import select
from .domain import CRMError
from sqlalchemy import inspect
from .report_store import schema_name, advisory_lock

def check_schema(crm,conn,write=False):
    if write and crm.backend == 'postgres': advisory_lock(conn,['crm-research-schema',schema_name(crm)])
    inspector=inspect(conn); schema=(conn.get_execution_options().get('schema_translate_map') or {}).get(None)
    present=[inspector.has_table(t.name,schema=schema) for t in OWNED_TABLES]
    if any(present) and not all(present): raise CRMError('Research schema is incomplete; explicit migration required',503)
    if not any(present):
        if not write: return False
        metadata.create_all(conn,tables=OWNED_TABLES)
        conn.execute(schema_state.insert().values(id=1,version=SCHEMA_VERSION))
        inspector=inspect(conn)
    for table in OWNED_TABLES:
        actual={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
        if set(actual)!=set(table.c.keys()): raise CRMError('Incompatible research columns',503)
        for col in table.c:
            found=actual[col.name]
            if (found['type']._type_affinity is not col.type._type_affinity or found['nullable']!=col.nullable or getattr(found['type'],'length',None)!=getattr(col.type,'length',None)): raise CRMError('Incompatible research column',503)
        if inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns'] != [c.name for c in table.primary_key]: raise CRMError('Incompatible research primary key',503)
        expected={(tuple(f.column_keys),tuple(e.column.table.name for e in f.elements),tuple(e.column.name for e in f.elements)) for f in table.foreign_key_constraints}
        reflected_fks=inspector.get_foreign_keys(table.name,schema=schema)
        allowed_schemas = (schema,) if crm.backend == 'postgres' and schema is not None else (None, schema)
        if any(f.get('options') or f.get('referred_schema') not in allowed_schemas for f in reflected_fks): raise CRMError('Incompatible research foreign key options or target schema',503)
        actual_fk={(tuple(f['constrained_columns']),tuple([f['referred_table']]*len(f['referred_columns'])),tuple(f['referred_columns'])) for f in reflected_fks}
        if expected != actual_fk: raise CRMError('Incompatible research foreign keys',503)
        if inspector.get_unique_constraints(table.name,schema=schema) or any(i.get('unique') for i in inspector.get_indexes(table.name,schema=schema)): raise CRMError('Unexpected research unique constraints',503)
    rows=conn.execute(select(schema_state)).mappings().all()
    if len(rows)!=1 or rows[0]['id']!=1 or rows[0]['version']!=SCHEMA_VERSION: raise CRMError('Unsupported research schema version',503)
    return True
