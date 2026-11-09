import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql, sqlite

from hermes_crm.domain import CRM, CRMError, metadata, database_url, resolve_data_dir
from hermes_crm.demo import seed
from hermes_crm.web import create_app

@pytest.fixture
def crm(tmp_path):
    instance=CRM(f'sqlite:///{tmp_path}/test.db')
    yield instance
    instance.close()

def contact(crm): return crm.create('contacts',{'name':'Demo Person','email':'demo@example.com'})
def future(): return (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
def task(crm): return crm.create('tasks',{'title':'Internal follow-up','due_at':future()})

def test_vertical_slice_and_audit(crm):
    c=contact(crm)
    d=crm.create('deals',{'title':'Demo opportunity','contact_id':c['id'],'value':120000,'stage':'qualified'})
    t=crm.create('tasks',{'title':'Review proposal','contact_id':c['id'],'deal_id':d['id'],'due_at':future()})
    assert crm.overview()['pipeline_value']==120000
    assert crm.overview()['weighted_value']==30000
    d=crm.update('deals',d['id'],{'version':1,'stage':'won'})
    assert d['probability']==100
    assert crm.overview()['won_value']==120000
    assert crm.overview()['pipeline_value']==0
    crm.update('tasks',t['id'],{'version':1,'status':'done'})
    detail=crm.contact_detail(c['id'])
    assert len(detail['activity'])==5
    assert detail['deals'][0]['stage']=='won'
    assert crm.overview()['open_tasks']==0

def test_stale_edit_rejected_and_audited_once(crm):
    c=contact(crm)
    crm.update('contacts',c['id'],{'version':1,'company':'Demo Co'})
    with pytest.raises(CRMError,match='changed'): crm.update('contacts',c['id'],{'version':1,'name':'Lost update'})
    assert crm.get('contacts',c['id'])['name']=='Demo Person'
    assert len(crm.activities())==2

def test_create_idempotency_and_conflicts(crm):
    first=crm.create('contacts',{'name':'Demo'},key='request-123')
    assert crm.create('contacts',{'name':'Demo'},key='request-123')==first
    with pytest.raises(CRMError,match='different'): crm.create('contacts',{'name':'Other'},key='request-123')
    assert len(crm.list('contacts'))==1
    assert len(crm.activities())==1

def test_concurrent_create_idempotency(crm):
    def run(_): return crm.create('contacts',{'name':'Demo'},key='simultaneous')
    with ThreadPoolExecutor(max_workers=4) as executor: results=list(executor.map(run,range(4)))
    assert len({r['id'] for r in results})==1
    assert len(crm.activities())==1

def test_validation_and_rollback(crm):
    with pytest.raises(ValidationError): crm.create('contacts',{'name':' ','admin':True})
    with pytest.raises(ValidationError): crm.create('tasks',{'title':'Missing timezone','due_at':'2026-11-10T09:00'})
    with pytest.raises(CRMError,match='not found'): crm.create('deals',{'title':'Missing contact','contact_id':'missing'})
    assert crm.activities()==[]
    c=contact(crm)
    with pytest.raises(ValidationError): crm.create('deals',{'title':'Bad amount','contact_id':c['id'],'value':1.23})
    with pytest.raises(ValidationError): crm.create('deals',{'title':'Bad currency','contact_id':c['id'],'currency':'EUR'})
    with pytest.raises(CRMError): crm.update('contacts',c['id'],{'version':1,'id':'other'})

def test_task_links_cannot_mismatch(crm):
    a=contact(crm); b=crm.create('contacts',{'name':'Other demo'})
    d=crm.create('deals',{'title':'Demo deal','contact_id':a['id']})
    with pytest.raises(CRMError,match='match'): crm.create('tasks',{'title':'Mismatch','contact_id':b['id'],'deal_id':d['id'],'due_at':future()})

def test_literal_search_and_filter(crm):
    contact(crm)
    assert crm.list('contacts',q='DEMO')
    assert crm.list('contacts',q='%')==[]
    assert crm.list('contacts',q="' OR 1=1--")==[]
    with pytest.raises(CRMError): crm.list('deals',stage='invalid')

def test_utc_normalization(crm):
    t=crm.create('tasks',{'title':'Zone-aware','due_at':'2026-11-09T10:00:00+05:30'})
    assert t['due_at']=='2026-11-09T04:30:00.000000+00:00'

def test_profile_isolation_and_explicit_backend(monkeypatch,tmp_path):
    monkeypatch.delenv('HERMES_CRM_DATA_DIR',raising=False)
    monkeypatch.delenv('HERMES_CRM_DATABASE_URL',raising=False)
    monkeypatch.setenv('HERMES_CRM_BACKEND','sqlite')
    monkeypatch.setenv('HERMES_HOME',str(tmp_path/'profile-a'))
    first=CRM(); contact(first); first.close()
    monkeypatch.setenv('HERMES_HOME',str(tmp_path/'profile-b'))
    second=CRM(); assert second.list('contacts')==[]; second.close()
    monkeypatch.setenv('HERMES_CRM_BACKEND','postgres')
    with pytest.raises(CRMError,match='requires'): database_url()
    monkeypatch.setenv('HERMES_CRM_BACKEND','invalid')
    with pytest.raises(CRMError,match='Unsupported'): database_url()
    monkeypatch.setenv('HERMES_CRM_BACKEND','sqlite')
    monkeypatch.setenv('HERMES_CRM_DATABASE_URL','postgresql://example.invalid/test')
    with pytest.raises(CRMError,match='explicit'): database_url()

def test_demo_is_explicit_and_refuses_existing(crm):
    assert crm.info()['demo'] is False
    seed(crm)
    assert crm.info()['demo'] is True
    assert crm.overview()['contacts']==8
    assert all(c['email'].endswith('@example.com') for c in crm.list('contacts'))
    with pytest.raises(CRMError,match='non-empty'): seed(crm)

def test_scheduler_payload_and_retry(crm):
    t=task(crm); calls=[]
    def dispatch(name,args,**context):
        calls.append((name,args,context))
        return json.dumps({'success':True,'job':{'id':'demo-job'}})
    result=crm.schedule_followup(t['id'],dispatch,session_id='demo-session')
    assert result['task']['schedule_status']=='scheduled'
    assert result['execution_verified'] is False
    assert calls[0][0]=='cronjob_manage'
    assert calls[0][1]['deliver']=='local'
    assert calls[0][1]['enabled_toolsets']==['crm_read', 'no_mcp']
    assert calls[0][1]['schedule']==t['due_at']
    assert calls[0][2]['session_id']=='demo-session'
    crm.schedule_followup(t['id'],dispatch)
    assert len(calls)==1
    with pytest.raises(CRMError,match='schedule'): crm.update('tasks',t['id'],{'version':result['task']['version'],'due_at':future()})

def test_scheduler_uncertainty_blocks_duplicates(crm):
    t=task(crm)
    def dispatch(*args,**kwargs): raise TimeoutError('unknown')
    result=crm.schedule_followup(t['id'],dispatch)
    assert result['task']['schedule_status']=='uncertain'
    with pytest.raises(CRMError,match='uncertain'): crm.schedule_followup(t['id'],dispatch)

def test_scheduler_rejection_is_visible(crm):
    t=task(crm)
    result=crm.schedule_followup(t['id'],lambda *a,**k:json.dumps({'success':False,'error':'tool disabled'}))
    assert result['task']['schedule_status']=='uncertain'
    assert result['task']['scheduler_job_id'] is None

def test_closed_or_past_task_not_scheduled(crm):
    t=task(crm)
    crm.update('tasks',t['id'],{'version':1,'status':'done'})
    with pytest.raises(CRMError,match='open'): crm.schedule_followup(t['id'],lambda *a:None)
    t=crm.create('tasks',{'title':'Old','due_at':'2020-01-01T00:00:00Z'})
    with pytest.raises(CRMError,match='future'): crm.schedule_followup(t['id'],lambda *a:None)

@pytest.mark.parametrize('dialect',[sqlite.dialect(),postgresql.dialect()])
def test_schema_compiles_for_both_backends(dialect):
    for table in metadata.sorted_tables: assert str(CreateTable(table).compile(dialect=dialect))

def test_api_and_security_boundaries(crm):
    client=TestClient(create_app(crm))
    result=client.post('/api/contacts',json={'name':'API demo'},headers={'Idempotency-Key':'api-request'})
    assert result.status_code==201
    assert client.post('/api/contacts',json={'name':'API demo'},headers={'Idempotency-Key':'api-request'}).json()['id']==result.json()['id']
    assert client.get('/api/contacts').json()[0]['name']=='API demo'
    assert client.post('/api/contacts',json={'name':'Bad origin'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/contacts',data='name=bad').status_code==415
    assert client.get('/api/meta',headers={'Host':'evil.example'}).status_code==400
    assert client.patch('/api/contacts/'+result.json()['id'],json={'version':1,'name':'Updated'}).status_code==200
    assert client.patch('/api/contacts/'+result.json()['id'],json={'version':1,'name':'Stale'}).status_code==409
    assert client.get('/api/contacts/missing').status_code==404
    assert client.post('/api/contacts',json={'name':''}).status_code==422
    assert "frame-ancestors 'none'" in client.get('/api/meta').headers['content-security-policy']

def test_plugin_registers_and_uses_profile_data(monkeypatch,tmp_path):
    from hermes_crm.plugin import register
    monkeypatch.setenv('HERMES_CRM_DATA_DIR',str(tmp_path/'plugin'))
    monkeypatch.setenv('HERMES_CRM_BACKEND','sqlite')
    monkeypatch.delenv('HERMES_CRM_DATABASE_URL',raising=False)
    class Context:
        profile_name='test-profile'
        def __init__(self): self.tools={}
        def register_tool(self,**kw): self.tools[kw['name']]=kw
        def dispatch_tool(self,*a,**k): return json.dumps({'success':True,'job':{'id':'demo'}})
        def get_config(self, key, default=None): return default
    # Mock only public host storage: native loader is tested separately from this contract.
    import sys, types, sqlite3
    parent=types.ModuleType('plugins'); storage=types.ModuleType('plugins.plugin_storage')
    data_dir=tmp_path/'plugin'; data_dir.mkdir()
    storage.plugin_data_dir=lambda name:data_dir
    storage.plugin_db=lambda name:sqlite3.connect(data_dir/'data.db',check_same_thread=False)
    monkeypatch.setitem(sys.modules,'plugins',parent)
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',storage)
    ctx=Context(); register(ctx)
    assert len(ctx.tools)==83
    assert ctx.tools['crm_task_get']['toolset']=='crm_read'
    create=ctx.tools['crm_contact_create']['handler']
    result=json.loads(create({'name':'Agent demo','idempotency_key':'agent-demo'}))
    assert result['ok']
    assert not json.loads(create({'name':'Bad','extra':True}))['ok']
    overview=json.loads(ctx.tools['crm_overview']['handler']({}))
    assert overview['data']['contacts']==1
    assert 'profile' not in overview['data']
    task_create=ctx.tools['crm_task_create']['handler']
    opened=json.loads(task_create({'title':'Open agent task','due_at':future()}))['data']
    task_create({'title':'Completed agent task','due_at':'2020-01-01T00:00:00Z','status':'done'})
    task_list=ctx.tools['crm_task_list']['handler']
    assert [t['id'] for t in json.loads(task_list({'status':'open'}))['data']]==[opened['id']]
    assert len(json.loads(task_list({'status':'done'}))['data'])==1
    assert not json.loads(task_list({'status':'invalid'}))['ok']
    assert 'status' in ctx.tools['crm_task_list']['schema']['parameters']['properties']


def test_saved_scheduler_failure_preserves_id_and_blocks_retry(crm):
    t=task(crm)
    response={'success':False,'error':'registration unavailable','job_id':'saved-job','job_saved':True,'scheduler_registered':False,'retry_create':False}
    result=crm.schedule_followup(t['id'],lambda *a,**k:json.dumps(response))
    assert result['task']['scheduler_job_id']=='saved-job'
    assert result['task']['schedule_status']=='uncertain'
    with pytest.raises(CRMError,match='uncertain'): crm.schedule_followup(t['id'],lambda *a:None)


def test_deal_reassignment_updates_linked_tasks_atomically(crm):
    first=contact(crm)
    second=crm.create('contacts',{'name':'Second demo contact'})
    deal=crm.create('deals',{'title':'Reassigned demo deal','contact_id':first['id']})
    linked=crm.create('tasks',{'title':'Linked follow-up','contact_id':first['id'],'deal_id':deal['id'],'due_at':future()})
    inherited=crm.create('tasks',{'title':'Inherited follow-up','deal_id':deal['id'],'due_at':future()})
    crm.update('deals',deal['id'],{'version':1,'contact_id':second['id']})
    moved=crm.get('tasks',linked['id'])
    assert moved['contact_id']==second['id']
    assert moved['version']==2
    assert crm.get('tasks',inherited['id'])['contact_id'] is None
    assert crm.contact_detail(first['id'])['tasks']==[]
    assert len(crm.contact_detail(second['id'])['tasks'])==2
    with pytest.raises(CRMError,match='changed'): crm.update('tasks',linked['id'],{'version':1,'status':'done'})
    assert crm.update('tasks',linked['id'],{'version':2,'status':'done'})['status']=='done'
    assert any(a['action']=='contact_reassigned' for a in crm.activities())


def test_open_followups_filtered_before_list_limit(crm):
    import uuid
    from hermes_crm.domain import tasks, now
    timestamp=now()
    # More than one page of completed history must not hide the only open task.
    rows=[dict(id=str(uuid.uuid4()),version=1,created_at=timestamp,updated_at=timestamp,
        title=f'Completed {i}',due_at='2020-01-01T00:00:00.000000+00:00',
        priority='normal',status='done',notes='',schedule_status='none') for i in range(501)]
    with crm.engine.begin() as conn: conn.execute(tasks.insert(),rows)
    upcoming=task(crm)
    assert crm.overview()['open_tasks']==1
    assert [t['id'] for t in crm.overview()['tasks']]==[upcoming['id']]
    client=TestClient(create_app(crm))
    assert [t['id'] for t in client.get('/api/tasks?status=open').json()]==[upcoming['id']]

def test_money_tool_schema_declares_minor_units():
    from hermes_crm.domain import DealInput
    value=DealInput.model_json_schema()['properties']['value']
    assert 'integer cents' in value['description']
    assert value['examples']==[1200000]


def test_related_contact_search_applies_before_limit(crm):
    c=crm.create('contacts',{'name':'Unique buyer name'})
    d=crm.create('deals',{'title':'Opportunity','contact_id':c['id']})
    t=crm.create('tasks',{'title':'Follow-up','contact_id':c['id'],'due_at':future()})
    assert [row['id'] for row in crm.list('deals',q='Unique buyer')]==[d['id']]
    assert [row['id'] for row in crm.list('tasks',q='Unique buyer',status='open')]==[t['id']]
    assert crm.list('tasks',q='%buyer')==[]
