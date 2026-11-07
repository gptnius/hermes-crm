"""Opt-in contracts against an explicitly supplied disposable PostgreSQL URL.

Only randomized crm_test_* schemas are created and dropped; no production data.
"""
import os
import uuid
from concurrent.futures import ProcessPoolExecutor
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM, CRMError
from hermes_crm.report_store import ReportStore, schema_name
import test_report_store as saved
import test_report_interactions as ledger

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def crm(monkeypatch):
    schema = 'crm_test_' + uuid.uuid4().hex
    instance = CRM(URL, schema=schema)
    monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
    yield instance
    instance.close()
    engine = create_engine(URL)
    try:
        with engine.begin() as conn: conn.execute(DropSchema(schema, cascade=True, if_exists=True))
    finally: engine.dispose()

# Reuse portable behavior contracts unchanged. Schema-introspection tests below
# explicitly name the randomized schema rather than relying on public search_path.
REPLACED = {'test_partial_schema_not_repaired','test_schema_column_mismatch_not_repaired',
            'test_partial_schema_refused_by_report_read'}
for prefix, contract in [('saved',saved),('ledger',ledger)]:
    for name, check in vars(contract).items():
        if name.startswith('test_') and callable(check) and name not in REPLACED:
            globals()['test_postgres_'+prefix+'_'+name[5:]] = check

@pytest.mark.parametrize('defect',['partial','column','type','nullable','primary_key'])
def test_explicit_schema_validation(crm,defect):
    from sqlalchemy import MetaData, String
    from hermes_crm.report_store import reports, revisions, dashboards, operations
    cloned = MetaData()
    tables = [table.to_metadata(cloned) for table in (reports,revisions,dashboards,operations)]
    if defect == 'type': tables[0].c.title.type = String(2)
    if defect == 'nullable': tables[0].c.title.nullable = True
    if defect == 'column':
        from sqlalchemy import Column, Text
        tables[0].append_column(Column('surprise',Text))
    if defect == 'primary_key':
        from sqlalchemy import PrimaryKeyConstraint
        tables[0].append_constraint(PrimaryKeyConstraint('id'))
    cloned.create_all(crm.engine, tables=tables[:1] if defect=='partial' else tables)
    before = set(inspect(crm.engine).get_table_names(schema=schema_name(crm)))
    with pytest.raises(CRMError): ReportStore(crm).create('Synthetic',saved.definition(),'bad')
    assert set(inspect(crm.engine).get_table_names(schema=schema_name(crm))) == before

def test_actual_schema_lazy_reads(crm):
    from hermes_crm.report_interactions import InteractionStore
    contact = crm.create('contacts',{'name':'Synthetic'})
    before = set(inspect(crm.engine).get_table_names(schema=schema_name(crm)))
    assert ReportStore(crm).list()['items'] == []
    assert ReportStore(crm).get_dashboard()['version'] == 0
    assert InteractionStore(crm).list(contact['id'])['items'] == []
    assert set(inspect(crm.engine).get_table_names(schema=schema_name(crm))) == before

def _process_write(args):
    url,schema,action,record_id = args
    instance = CRM(url,schema=schema)
    try:
        store = ReportStore(instance)
        if action=='create': return store.create('Concurrent',{'entity':'contacts'},'same-create')
        return store.update(record_id,'Updated',{'entity':'contacts'},1,'same-update')
    finally: instance.close()

def test_cross_process_initialization_and_same_key_replay(crm):
    args=(URL,schema_name(crm),'create',None)
    with ProcessPoolExecutor(max_workers=4) as pool: rows=list(pool.map(_process_write,[args]*4))
    assert all(row==rows[0] for row in rows)
    args=(URL,schema_name(crm),'update',rows[0]['id'])
    with ProcessPoolExecutor(max_workers=4) as pool: updates=list(pool.map(_process_write,[args]*4))
    assert all(row==updates[0] for row in updates)
    assert updates[0]['version']==2
