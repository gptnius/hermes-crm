"""One shared authenticated relationship router, isolated from providers."""
from contextlib import contextmanager
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM, CRMError
from hermes_crm.relationship_api import build_router
from hermes_crm.relationship_tools import register_relationship_tools

@pytest.fixture
def adapter():
    crm=CRM('sqlite:///:memory:'); token=crm.workspace_token()
    @contextmanager
    def service(): yield crm
    def check(crm,value):
        if value!=token: raise CRMError('Stale workspace',409)
    app=FastAPI()
    @app.exception_handler(CRMError)
    def error(request,exc): return JSONResponse({'error':str(exc)},status_code=exc.status)
    app.include_router(build_router(service,check,actor='test-adapter'))
    yield crm,TestClient(app),token
    crm.close()


def test_strict_api_versions_query_and_actor(adapter):
    crm,client,token=adapter
    body=dict(workspace_token=token,idempotency_key='create',data={'name':'Company'})
    response=client.post('/companies',json=body); assert response.status_code==201,response.text
    company=response.json()
    assert client.post('/companies',json=body).json()==company
    assert client.get('/companies',params=[('workspace_token',token),('q','one'),('q','two')]).status_code==400
    assert client.get('/companies',params={'workspace_token':token,'unknown':'x'}).status_code==400
    assert client.get('/companies',params={'workspace_token':'stale'}).status_code==409
    assert client.post('/companies',json=dict(body,actor='forged')).status_code==422
    assert client.patch('/companies/'+company['id'],json=dict(body,expected_version=True)).status_code==422
    contact=crm.create('contacts',{'name':'Person'})
    result=client.put('/contacts/'+contact['id']+'/company',json=dict(workspace_token=token,idempotency_key='link',expected_contact_version=1,company_id=company['id']))
    assert result.status_code==200,result.text
    detail=client.get('/companies/'+company['id'],params={'workspace_token':token}).json()
    assert detail['counts']['contacts']==1


def test_event_lifecycle_and_tasks(adapter):
    crm,client,token=adapter
    def write(path,version=None,**extra):
        body=dict(workspace_token=token,idempotency_key=path+str(version),**extra)
        if version is not None: body['expected_version']=version
        response=client.post(path,json=body)
        assert response.status_code in (200,201),response.text
        return response.json()
    event=write('/events',data=dict(title='Consult',kind='appointment',starts_at='2020-01-01T10:00:00Z',ends_at='2020-01-01T11:00:00Z',timezone='UTC'))
    path='/events/'+event['id']
    receipt=write(path+'/tasks',1,data={'title':'Prepare','due_at':'2020-01-01T09:00:00Z'})
    tasks=client.get(path+'/tasks',params={'workspace_token':token}); assert tasks.status_code==200,tasks.text
    assert tasks.json()['total']==1
    v=receipt['event']['version']
    changed=write(path+'/needs-rescheduling',v,reason='Moved')
    assert changed['status']=='needs_rescheduling'
    changed=write(path+'/reschedule',changed['version'],data={'starts_at':'2020-02-01T10:00:00Z','ends_at':'2020-02-01T11:00:00Z','timezone':'UTC'})
    completed=write(path+'/complete',changed['version'],data={'outcome_happened_at':'2020-02-01T11:00:00Z','outcome_summary':'Self reported'})
    assert completed['status']=='completed'
    assert client.get('/relationship-activities',params={'workspace_token':token}).json()['total']==1


def test_tools_strict_minimized_separate_authority(adapter):
    crm,client,token=adapter; registered={}
    def register(name,description,properties,required,handler,**kw): registered[name]=(handler,kw)
    register_relationship_tools(register)
    assert {v[1]['toolset'] for v in registered.values()}=={'crm_company_read','crm_company_write','crm_event_read','crm_event_write'}
    for handler,opts in registered.values():
        assert opts['argument_model'].model_json_schema()['additionalProperties'] is False
    handler,opts=registered['crm_company_create']
    args=opts['argument_model'].model_validate({'data':{'name':'Org','notes':'SECRET'},'idempotency_key':'tool-create'}).model_dump()
    created=handler(crm,args,None)
    assert 'notes' not in created and 'scope' not in created
    get=registered['crm_company_get'][0](crm,{'record_id':created['id']},None)
    assert 'notes' not in get['company']


def test_search_and_contact_task_pages(adapter):
    crm,client,token=adapter
    contact=crm.create('contacts',{'name':'Exact %_ match'})
    response=client.get('/relationship-selectors/contacts',params={'workspace_token':token,'q':'%_'})
    assert response.status_code==200,response.text
    assert response.json()['items'][0]['id']==contact['id']
    assert response.json()['total']==1
    assert client.get('/relationship-selectors/contacts',params={'workspace_token':token,'q':'not found'}).json()['total']==0
    assert client.get('/contacts/'+contact['id']+'/relationship-tasks',params={'workspace_token':token}).json()['total']==0
    assert client.put('/contacts/'+contact['id']+'/company',json={'workspace_token':token,'idempotency_key':'missing','expected_contact_version':1}).status_code==422


def test_all_tool_models_forbid_injected_actor_scope(adapter):
    from pydantic import ValidationError
    registered={}
    register_relationship_tools(lambda name,description,properties,required,handler,**kw: registered.update({name:kw}))
    assert len(registered)==24
    for options in registered.values():
        for field in ('actor','scope','profile','source'):
            with pytest.raises(ValidationError):
                options['argument_model'].model_validate({field:'forged'})


def test_event_tool_writes_and_revisions_minimize_plaintext(adapter):
    crm,client,token=adapter; registered={}
    def register(name,description,properties,required,handler,**kw): registered[name]=(handler,kw['argument_model'])
    register_relationship_tools(register)
    def invoke(name,**args):
        handler,model=registered[name]
        return handler(crm,model.model_validate(args).model_dump(),None)
    event=invoke('crm_event_create',data={'title':'Consult','kind':'call','starts_at':'2020-01-01T10:00:00Z','ends_at':'2020-01-01T11:00:00Z','timezone':'UTC','notes':'SECRET'},idempotency_key='ev-tool')
    assert 'notes' not in event
    receipt=invoke('crm_event_task_create',record_id=event['id'],expected_version=1,data={'title':'Prepare','due_at':'2020-01-01T09:00:00Z','notes':'SECRET'},idempotency_key='task-tool')
    assert 'notes' not in receipt['task'] and 'notes' not in receipt['event']
    done=invoke('crm_event_complete',record_id=event['id'],expected_version=receipt['event']['version'],data={'outcome_happened_at':'2020-01-01T11:00:00Z','outcome_summary':'SECRET'},idempotency_key='done-tool')
    assert done['status']=='completed' and 'outcome_summary' not in done
    revisions=invoke('crm_event_revisions',record_id=event['id'])
    assert revisions['total']==3
    for row in revisions['items']:
        assert 'reason' not in row and 'scope' not in row
        assert 'notes' not in row['record'] and 'outcome_summary' not in row['record']


def test_unlink_requires_exact_event_and_handles_noop_replay(adapter):
    from hermes_crm.events import EventStore
    crm,client,token=adapter
    event=EventStore(crm).create({'title':'Consult','kind':'call','starts_at':'2020-01-01T10:00:00Z','ends_at':'2020-01-01T11:00:00Z','timezone':'UTC'},actor='test',key='unlink-event')
    task=crm.create('tasks',{'title':'Unlinked','due_at':'2020-01-01T09:00:00Z','notes':'SECRET'})
    path='/tasks/'+task['id']+'/event/unlink'
    body={'workspace_token':token,'expected_task_version':1,'idempotency_key':'api-noop'}
    assert client.post(path,json=body).status_code==422
    body.update(event_id=event['id'],expected_version=1)
    first=client.post(path,json=body)
    assert first.status_code==200,first.text
    assert first.json()['event'] is None
    assert client.post(path,json=body).json()==first.json()
    tools={}
    register_relationship_tools(lambda name,description,properties,required,handler,**kw: tools.update({name:(handler,kw['argument_model'])}))
    handler,model=tools['crm_event_task_unlink']
    args=model.model_validate({'record_id':task['id'],'event_id':event['id'],'expected_version':1,'expected_task_version':1,'idempotency_key':'tool-noop'}).model_dump()
    result=handler(crm,args,None)
    assert result['event'] is None and 'notes' not in result['task']
    assert handler(crm,args,None)==result


def test_absent_workspace_read_does_not_bootstrap():
    from sqlalchemy import inspect,select
    from hermes_crm.domain import settings
    crm=CRM('sqlite:///:memory:')
    @contextmanager
    def service(): yield crm
    def bootstrapping_host(crm,token):
        assert token==crm.workspace_token()
    app=FastAPI()
    @app.exception_handler(CRMError)
    def error(request,exc): return JSONResponse({'error':str(exc)},status_code=exc.status)
    app.include_router(build_router(service,bootstrapping_host))
    try:
        before=set(inspect(crm.engine).get_table_names())
        response=TestClient(app).get('/companies',params={'workspace_token':'forged'})
        assert response.status_code==409
        with crm.engine.connect() as conn:
            assert conn.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar() is None
        assert set(inspect(crm.engine).get_table_names())==before
    finally: crm.close()
