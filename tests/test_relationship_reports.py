"""Scoped typed sources preserve legacy reporting and exact Company identities."""
import os
import uuid
import pytest
from sqlalchemy import inspect, select
from hermes_crm.domain import CRM, contacts, settings, TABLES
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.reports import ReportEngine
from hermes_crm.report_store import schema_name

@pytest.fixture(params=['sqlite','postgres'])
def crm(request):
    url = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
    if request.param == 'postgres' and not url:
        pytest.skip('Requires explicit disposable PostgreSQL URL')
    schema = 'crm_rel_report_' + uuid.uuid4().hex if request.param == 'postgres' else None
    crm = CRM(url if schema else 'sqlite:///:memory:', **({'schema':schema} if schema else {}))
    try:
        yield crm
    finally:
        crm.close()
        if schema:
            from sqlalchemy import create_engine
            from sqlalchemy.schema import DropSchema
            engine=create_engine(url)
            try:
                with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
            finally: engine.dispose()


def company(crm, key, name='Duplicate'):
    return CompanyStore(crm).create({'name':name,'notes':'PRIVATE'},actor='test',key=key)


def event(crm, key, **extra):
    return EventStore(crm).create(dict(title='Consultation',kind='call',starts_at='2020-01-01T10:00:00Z',ends_at='2020-01-01T11:00:00Z',timezone='UTC',notes='PRIVATE',**extra),actor='test',key=key)


def test_absent_typed_sources_never_initialize(crm):
    before=set(inspect(crm.engine).get_table_names(schema=schema_name(crm)))
    for entity in ('companies','events'):
        engine=ReportEngine(crm)
        result=engine.run({'entity':entity,'columns':['id'],'measure':{'op':'count'}})
        assert result['total']==result['metric']==0
        assert 'notes' not in engine.catalog()['entities'][entity]['fields']
    assert set(inspect(crm.engine).get_table_names(schema=schema_name(crm)))==before
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar() is None
    assert set(TABLES)=={'contacts','deals','tasks'}


def test_company_identity_groups_and_legacy_text(crm):
    a,b=company(crm,'a'),company(crm,'b')
    for index,co in enumerate((a,b,a)):
        contact=crm.create('contacts',{'name':str(index),'company':'Legacy unchanged'})
        CompanyStore(crm).set_contact_company(contact['id'],co['id'],expected_contact_version=1,actor='test',key='link'+str(index))
        deal=crm.create('deals',{'title':'Deal','contact_id':contact['id']})
        crm.create('tasks',{'title':'Direct and indirect','due_at':'2020-01-01T09:00:00Z','contact_id':contact['id'],'deal_id':deal['id']})
    engine=ReportEngine(crm)
    for entity in ('contacts','deals','tasks'):
        result=engine.run({'entity':entity,'columns':['id','company_id','company_name'],'group_by':{'field':'company_id'}})
        assert result['total']==3
        assert {g['key']:g['count'] for g in result['groups']}=={a['id']:2,b['id']:1}
        for group in result['groups']:
            detail=engine.run(group['detail_definition'])
            assert detail['total']==group['count']
            assert {r['company_id'] for r in detail['items']}=={group['key']}
    assert {r['company'] for r in engine.run({'entity':'contacts','columns':['company']})['items']}=={'Legacy unchanged'}


def test_event_source_scoped_before_aggregation(crm):
    co=company(crm,'company'); ev=event(crm,'event',company_id=co['id'])
    result=ReportEngine(crm).run({'entity':'events','columns':['id','company_id','company_name','starts_at'],'group_by':{'field':'company_id'}})
    assert result['total']==1 and result['groups'][0]['key']==co['id']
    old_profile=crm.profile; crm.profile='other'
    try:
        assert ReportEngine(crm).run({'entity':'events','columns':['id']})['total']==0
        assert ReportEngine(crm).run({'entity':'companies','columns':['id']})['total']==0
    finally: crm.profile=old_profile
    assert ReportEngine(crm).run({'entity':'events','columns':['id']})['items']==[{'id':ev['id']}]


def test_relationship_filter_applied_before_page_cap(crm):
    co=company(crm,'company')
    from hermes_crm.relationship_schema import companies
    from hermes_crm.report_store import scope_for
    with crm.engine.begin() as conn:
        base=conn.execute(select(companies)).mappings().one()
        conn.execute(companies.insert(), [dict(base,id=f'company-{i:04}',name='Needle' if i==602 else 'Noise') for i in range(603)])
    result=ReportEngine(crm).run({'entity':'companies','columns':['id','name'],'filter':{'field':'name','op':'eq','value':'Needle'}})
    assert result['total']==1 and result['items'][0]['id']=='company-0602'


def test_postgres_empty_relation_has_explicit_types(crm):
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql
    from hermes_crm.reports import report_source
    with crm.engine.connect() as conn:
        source=report_source(crm,conn,'events')
        sql=str(select(source.c.id).where(source.c.starts_at.is_(None)).compile(dialect=postgresql.dialect()))
        assert 'CAST(' in sql and 'crm_events' not in sql


def test_company_report_alias_does_not_leak_unscoped_table(crm):
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql
    from hermes_crm.reports import report_source
    company(crm,'one')
    with crm.engine.connect() as conn:
        source=report_source(crm,conn,'events')
        expressions=ReportEngine(crm)._expressions('events','2026-01-01T00:00:00Z',conn,crm.catalog(conn=conn),source)
        sql=str(select(expressions['company_name']).select_from(source).compile(dialect=postgresql.dialect()))
        assert sql.count('FROM crm_events') == 1
        assert 'FROM crm_companies, crm_events' not in sql
        assert 'crm_events.scope =' in sql and 'crm_companies.scope =' in sql
