"""Typed custom field reports, preserved definitions, and exact live drilldowns."""
import copy
import os
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
from hermes_crm.reports import FIELDS, ReportEngine
from hermes_crm.report_store import ReportStore

@pytest.fixture(params=['sqlite','postgres'])
def setup(request):
    url = 'sqlite:///:memory:' if request.param == 'sqlite' else os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
    if not url: pytest.skip('Requires explicit disposable PostgreSQL URL')
    schema = 'crm_custom_reports_' + uuid.uuid4().hex if request.param == 'postgres' else None
    crm = CRM(url, **({'schema':schema} if schema else {}))
    try: yield crm, ReportEngine(crm)
    finally:
        crm.close()
        if schema:
            engine = create_engine(url)
            with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
            engine.dispose()

def define(crm, kind='contacts'):
    for key, typ in [('score','number'),('consent','boolean'),('renewal','date'),('segment','single-select'),('memo','text')]:
        crm.create_field(kind,dict(key=key,label=key.title(),type=typ,**({'choices':['A','B']} if typ=='single-select' else {})))

def test_custom_types_nulls_aggregates_drilldowns(setup):
    crm, engine = setup; define(crm)
    for index, values in enumerate([{'score':0,'consent':False,'renewal':'2026-01-01','segment':'A','memo':'50%_safe'}, {'score':2.5,'consent':True,'renewal':'2026-01-02','segment':'B'}, {}]):
        crm.create('contacts',dict(name=str(index),custom_fields=values))
    for field, value in [('score',0),('consent',False),('renewal','2026-01-01'),('segment','A')]:
        assert engine.run(dict(entity='contacts',filter=dict(field='custom.'+field,op='eq',value=value)))['total']==1
    assert engine.run(dict(entity='contacts',filter=dict(field='custom.score',op='is_null',value=None)))['total']==1
    assert engine.run(dict(entity='contacts',filter=dict(field='custom.memo',op='contains',value='%_')))['total']==1
    for field in ['custom.consent','custom.renewal','custom.segment','custom.score']:
        report=engine.run(dict(entity='contacts',columns=['name','custom.score','custom.consent'],group_by={'field':field},measure={'op':'sum','field':'custom.score'}))
        assert report['metric']==2.5 and sum(b['count'] for b in report['groups'])==3
        for bucket in report['groups']:
            detail=engine.run(dict(bucket['detail_definition'],measure={'op':'sum','field':'custom.score'}))
            assert detail['total']==bucket['count'] and detail['metric']==bucket['value']
    rows=engine.run(dict(entity='contacts',columns=['custom.score','custom.consent'],sort=[{'field':'custom.score'}]))['items']
    assert rows==[{'custom.score':0,'custom.consent':False},{'custom.score':2.5,'custom.consent':True},{'custom.score':None,'custom.consent':None}]
    boundary=engine.run(dict(entity='contacts',group_by={'field':'custom.renewal','interval':'day'}))
    assert all(engine.run(b['detail_definition'])['total']==b['count'] for b in boundary['groups'])

@pytest.mark.parametrize('field,value',[('score',True),('score',float('nan')),('score',10**400),('score','2'),('consent',0),('consent','false'),('renewal','2026-1-1'),('segment','C')])
def test_custom_filter_validation(setup,field,value):
    crm, engine=setup; define(crm)
    with pytest.raises(ValidationError): engine.run(dict(entity='contacts',filter=dict(field='custom.'+field,op='eq',value=value)))

def test_dynamic_stage_labels_and_outcomes(setup):
    crm, engine=setup
    crm.create_stage(dict(key='paid',label='Paid customer',outcome='won',probability=100,order=9))
    c=crm.create('contacts',{'name':'Customer'})
    for i in range(2): crm.create('deals',dict(title=str(i),contact_id=c['id'],stage='paid',value=100))
    result=engine.run(dict(entity='deals',columns=['stage','stage_outcome'],filter=dict(field='stage_outcome',op='eq',value='won'),measure={'op':'sum','field':'value'},group_by={'field':'stage'}))
    assert result['metric']==200 and result['groups'][0]['key']=='paid'
    assert result['choice_labels']['stage']['paid']=='Paid customer'
    assert engine.run(result['groups'][0]['detail_definition'])['total']==2
    linked=engine.run(dict(entity='contacts',columns=['linked_stages','deal_count'],filter=dict(field='linked_stages',op='has_all',value=['paid'])))
    assert linked['items']==[{'linked_stages':['paid'],'deal_count':2}]
    crm.update_stage('paid',dict(version=1,label='Won and paid'))
    assert engine.run(result['groups'][0]['detail_definition'])['total']==2
    assert engine.catalog()['entities']['deals']['fields']['stage']['choice_labels']['paid']=='Won and paid'
    crm.create_stage(dict(key='unused',label='Unused',outcome='open'))
    crm.update_stage('unused',dict(version=1,archived=True))
    assert engine.run(dict(entity='deals',filter=dict(field='stage',op='eq',value='unused')))['total']==0

def test_saved_archived_fields_and_workspace_isolation(setup):
    crm, engine=setup; original=copy.deepcopy(FIELDS); define(crm)
    crm.create('contacts',dict(name='Current',custom_fields={'score':4,'renewal':'2026-01-01'}))
    store=ReportStore(crm)
    definition=dict(entity='contacts',group_by={'field':'custom.renewal','interval':'day'},measure={'op':'sum','field':'custom.score'})
    saved=store.create('Custom report',definition,'custom-report-create')
    crm.update_field('contacts','score',dict(version=1,archived=True,label='Archived score'))
    assert engine.run(saved['definition'])['metric']==4
    store.save_dashboard([dict(id=str(uuid.uuid4()),report_id=saved['id'],report_version=1,visualization='line')],0,'custom-dashboard')
    catalog=engine.catalog(); assert catalog['entities']['contacts']['fields']['custom.score']['archived']
    catalog['entities']['contacts']['fields']['name']['label']='Changed externally'
    assert engine.catalog()['entities']['contacts']['fields']['name']['label']=='Name'
    other=CRM('sqlite:///:memory:')
    try:
        assert 'custom.score' not in ReportEngine(other).catalog()['entities']['contacts']['fields']
        with pytest.raises(ValidationError): ReportEngine(other).run(saved['definition'])
    finally: other.close()
    assert FIELDS==original

@pytest.mark.parametrize('kind',['deals','tasks'])
def test_custom_fields_other_entities_and_no_fanout(setup,kind):
    crm, engine=setup; define(crm,kind)
    c=crm.create('contacts',{'name':'Shared'})
    for value in [0,1.25]:
        crm.create(kind,dict(title='Record',contact_id=c['id'],**({'due_at':'2026-01-01T00:00:00Z'} if kind=='tasks' else {}),custom_fields={'score':value,'consent':False,'segment':'A'}))
    result=engine.run(dict(entity=kind,columns=['id','custom.score'],filter=dict(field='custom.consent',op='eq',value=False),group_by={'field':'custom.segment'},measure={'op':'sum','field':'custom.score'}))
    assert result['total']==2 and result['metric']==1.25 and len(result['groups'])==1
    assert engine.run(result['groups'][0]['detail_definition'])['total']==2


def test_long_text_group_drilldown(setup):
    crm, engine=setup; define(crm)
    crm.create('contacts',dict(name='Long text',custom_fields={'memo':'x'*10000}))
    result=engine.run(dict(entity='contacts',group_by={'field':'custom.memo'}))
    assert engine.run(result['groups'][0]['detail_definition'])['total']==1

def test_postgres_custom_sql_compiles_without_fanout():
    from types import SimpleNamespace
    from sqlalchemy import select
    from sqlalchemy.dialects import postgresql
    crm=CRM('sqlite:///:memory:')
    try:
        define(crm,'deals')
        engine=ReportEngine(crm)
        schema=crm.catalog()
        expressions=engine._expressions('deals','2026-01-01T00:00:00Z',SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),schema)
        query=select(expressions['custom.score'],expressions['custom.consent'],expressions['custom.renewal'],expressions['stage_outcome'])
        sql=str(query.compile(dialect=postgresql.dialect()))
        assert '->>' in sql and 'AS FLOAT' in sql and 'AS BOOLEAN' in sql
        assert 'json_extract' not in sql and ' JOIN ' not in sql
    finally: crm.close()


def test_maximum_length_custom_keys_do_not_collide(setup):
    crm, engine=setup
    keys=['a'*57+'suffix1','a'*57+'suffix2']
    assert all(len(key)==64 for key in keys)
    columns=['custom.'+key for key in keys]
    for key in keys: crm.create_field('contacts',dict(key=key,label=key,type='number'))
    for first,second in [(1,20),(2,10),(1,30)]:
        crm.create('contacts',dict(name='Long keys',custom_fields=dict(zip(keys,[first,second]))))
    result=engine.run(dict(entity='contacts',columns=columns,sort=[{'field':columns[1]}]))
    assert result['items']==[dict(zip(columns,[2,10])),dict(zip(columns,[1,20])),dict(zip(columns,[1,30]))]
    result=engine.run(dict(entity='contacts',columns=columns,group_by={'field':columns[0]},measure={'op':'sum','field':columns[1]}))
    assert result['metric']==60
    assert [(bucket['key'],bucket['value'],bucket['count']) for bucket in result['groups']]==[(1,50,2),(2,10,1)]
    for bucket in result['groups']:
        detail=engine.run(dict(bucket['detail_definition'],measure={'op':'sum','field':columns[1]}))
        assert detail['metric']==bucket['value'] and detail['total']==bucket['count']
