"""Demo must not populate existing relationship-only workspaces."""
import os
import uuid
import pytest
from sqlalchemy import create_engine, inspect, select, update
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM, CRMError, contacts, deals, tasks, settings
from hermes_crm.demo import seed
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.relationship_schema import companies, OWNED_TABLES, schema_state, check_schema
from hermes_crm.customization import state
from hermes_crm.report_store import schema_name

URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
@pytest.fixture(params=['sqlite','postgres'])
def crm(request,tmp_path):
    if request.param=='postgres' and not URL: pytest.skip('Requires explicit disposable PostgreSQL URL')
    schema='crm_demo_guard_'+uuid.uuid4().hex if request.param=='postgres' else None
    instance=CRM(URL if schema else 'sqlite:///'+str(tmp_path/'demo.db'),schema=schema)
    try: yield instance
    finally:
        instance.close()
        if schema:
            engine=create_engine(URL)
            try:
                with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
            finally: engine.dispose()

def snapshot(crm):
    """Include every existing table, rows, receipts, settings and catalog revision."""
    from sqlalchemy import MetaData, Table
    with crm.engine.connect() as conn:
        schema=schema_name(crm);inspector=inspect(conn);result={}
        for name in inspector.get_table_names(schema=schema):
            table=Table(name,MetaData(),schema=schema,autoload_with=conn)
            result[name]=sorted((tuple(row) for row in conn.execute(select(table))),key=repr)
        return result

@pytest.mark.parametrize('existing',['company','archived_company','event','foreign_profile_company','foreign_profile_event'])
def test_relationship_only_workspace_refused_unchanged(crm,existing):
    if existing.startswith('foreign_profile'): crm.profile='other-profile'
    if existing.endswith('company'):
        store=CompanyStore(crm);record=store.create(dict(name='Existing organization'),actor='test',key='company')
        if existing=='archived_company': store.archive(record['id'],expected_version=1,actor='test',key='archive')
    else:
        EventStore(crm).create(dict(title='Existing appointment',kind='appointment',starts_at='2020-01-01T00:00:00Z',ends_at='2020-01-01T01:00:00Z',timezone='UTC'),actor='test',key='event')
    crm.profile='default'
    before=snapshot(crm)
    with pytest.raises(CRMError,match='non-empty workspace') as error: seed(crm)
    assert error.value.status==409 and snapshot(crm)==before

@pytest.mark.parametrize('initialized',[False,True])
def test_truly_empty_workspace_seeds_without_lazy_schema(crm,initialized):
    if initialized:
        with crm.engine.begin() as conn: check_schema(crm,conn,write=True)
    seed(crm)
    assert len(crm.list('contacts'))==8 and len(crm.list('deals'))==8 and len(crm.list('tasks'))==5
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings.c.value).where(settings.c.key=='demo')).scalar_one()=='true'
        assert conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar() is None
        assert all(inspect(conn).has_table(t.name,schema=schema_name(crm))==initialized for t in OWNED_TABLES)

@pytest.mark.parametrize('invalid',['partial','newer'])
def test_invalid_relationship_schema_fails_closed_unchanged(crm,invalid):
    with crm.engine.begin() as conn:
        if invalid=='partial': companies.create(conn)
        else:
            check_schema(crm,conn,write=True)
            conn.execute(update(schema_state).values(version=2))
    before=snapshot(crm)
    with pytest.raises(CRMError) as error: seed(crm)
    assert error.value.status==503 and snapshot(crm)==before

def test_seed_acquires_catalog_before_postgres_tables_and_relationship_read(crm,monkeypatch):
    import hermes_crm.relationship_schema as relationship_schema
    from sqlalchemy import event
    ordered=[]
    original_lock=crm._catalog_lock;original_check=relationship_schema.check_schema
    def lock(conn): ordered.append('catalog');return original_lock(conn)
    def check(*args,**kwargs): ordered.append('schema');return original_check(*args,**kwargs)
    def statement(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('LOCK TABLE'): ordered.append('tables')
    monkeypatch.setattr(crm,'_catalog_lock',lock);monkeypatch.setattr(relationship_schema,'check_schema',check)
    event.listen(crm.engine,'before_cursor_execute',statement)
    try: seed(crm)
    finally: event.remove(crm.engine,'before_cursor_execute',statement)
    assert ordered[0]=='catalog' and ordered.index('catalog')<ordered.index('schema')
    if crm.backend=='postgres': assert ordered.index('catalog')<ordered.index('tables')<ordered.index('schema')

def test_seed_failure_remains_atomic(crm,monkeypatch):
    before=snapshot(crm)
    original=CRM._insert_created;calls=[]
    def fail_after_first(self,*args,**kwargs):
        calls.append(1)
        if len(calls)>1: raise RuntimeError('Injected second record failure')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(CRM,'_insert_created',fail_after_first)
    with pytest.raises(RuntimeError,match='second record'): seed(crm)
    assert snapshot(crm)==before
