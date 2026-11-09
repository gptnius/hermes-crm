"""Synthetic native API tests: never creates a host context or schedule."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
import pytest
from hermes_crm.domain import CRM
from hermes_crm import native_api
from hermes_crm.scheduled_research import ScheduledResearchStore, TABLES

@pytest.fixture
def api(tmp_path, monkeypatch):
    state={'profile':'alpha'}
    def factory(): return CRM(f'sqlite:///{tmp_path}/{state["profile"]}.db',profile=state['profile'])
    monkeypatch.setattr(native_api,'open_profile_crm',factory)
    app=FastAPI();app.include_router(native_api.router)
    client=TestClient(app)
    token=client.get('/meta').json()['workspace_token']
    with closing(factory()) as crm:
        contact=crm.create('contacts',{'name':'Public fixture'})
        task=crm.create('tasks',{'title':'Private task title','notes':'PRIVATE NEVER INSERT','due_at':'2030-11-11T12:00:00Z'})
    body={'workspace_token':token,'idempotency_key':'exact-key','data':dict(task_id=task['id'],task_version=task['version'],human_owner='Reviewer',target_kind='contacts',target_id=contact['id'],target_version=contact['version'],public_question='Public product launches?',run_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),research='search',propose_note=True,max_sources=3)}
    return client,state,factory,body

def test_absent_history_is_explicit_read_only(api):
    client,_,factory,body=api
    with closing(factory()) as crm: before=set(inspect(crm.engine).get_table_names())
    response=client.get('/scheduled-research',params={'workspace_token':body['workspace_token'],'task_id':body['data']['task_id']})
    assert response.status_code==200 and response.json()['storage']=='absent' and response.json()['items']==[]
    with closing(factory()) as crm: assert set(inspect(crm.engine).get_table_names())==before

def test_save_exact_replay_and_read_scope(api):
    client,state,factory,body=api
    result=client.post('/scheduled-research',json=body)
    assert result.status_code==201, result.text
    row=result.json(); assert row['state']=='pending' and row['job_id'] is None
    assert row['payload']['task_due_at']=='2030-11-11T12:00:00.000000+00:00'
    assert 'PRIVATE' not in result.text
    assert client.post('/scheduled-research',json=body).json()['id']==row['id']
    params={'workspace_token':body['workspace_token']}
    assert client.get('/scheduled-research/'+row['id'],params=params).json()==row
    assert client.get('/scheduled-research',params=params).json()['items']==[row]
    assert client.post('/scheduled-research',json={**body,'data':{**body['data'],'public_question':'Other?'}}).status_code==409
    with closing(factory()) as crm: crm.update('tasks',body['data']['task_id'],{'version':1,'title':'Changed'})
    # Replay recovers same identity after task changes, never creates a replacement.
    assert client.post('/scheduled-research',json=body).json()['id']==row['id']
    assert client.post('/scheduled-research',json={**body,'idempotency_key':'new'}).status_code==409
    state['profile']='beta';client.get('/meta')
    assert client.get('/scheduled-research',params=params).status_code==409
    assert client.post('/scheduled-research',json=body).status_code==409
    assert client.get('/scheduled-research/'+row['id'],params=params).status_code==409

@pytest.mark.parametrize('extra',[{'profile':'other'},{'dispatch_tool':'fake'},{'context':{}},{'run_now':True}])
def test_no_host_dispatch_or_context(api,extra):
    client,_,_,body=api
    assert client.post('/scheduled-research',json={**body,**extra}).status_code==422
    assert client.post('/scheduled-research',json={**body,'data':{**body['data'],**extra}}).status_code==422
    assert client.post('/scheduled-research/id/schedule',json=body).status_code==404

def test_partial_schema_fails_without_repair(api):
    client,_,factory,body=api
    with closing(factory()) as crm:
        TABLES[0].create(crm.engine)
        before=set(inspect(crm.engine).get_table_names())
    params={'workspace_token':body['workspace_token']}
    assert client.get('/scheduled-research',params=params).status_code==503
    assert client.post('/scheduled-research',json=body).status_code==503
    with closing(factory()) as crm: assert set(inspect(crm.engine).get_table_names())==before

def test_unknown_query_and_stale_target_rejected(api):
    client,_,factory,body=api
    assert client.get('/scheduled-research',params={'workspace_token':body['workspace_token'],'host_context':'bad'}).status_code==400
    with closing(factory()) as crm: crm.update('contacts',body['data']['target_id'],{'version':1,'name':'New'})
    assert client.post('/scheduled-research',json=body).status_code==409

def test_status_pagination_and_malformed_schema(api):
    client,_,factory,body=api
    assert client.post('/scheduled-research',json=body).status_code==201
    assert client.post('/scheduled-research',json={**body,'idempotency_key':'second'}).status_code==201
    params={'workspace_token':body['workspace_token'],'task_id':body['data']['task_id'],'limit':1,'offset':1}
    page=client.get('/scheduled-research',params=params).json()
    assert page['initialized'] is True and page['storage']=='present' and page['total']==2 and len(page['items'])==1
    with closing(factory()) as crm:
        with crm.engine.begin() as conn:
            conn.execute(text('ALTER TABLE crm_scheduled_research_v1 RENAME COLUMN digest TO broken_digest'))
    assert client.get('/scheduled-research',params=params).status_code==503

def test_ui_accepts_authoritative_saved_and_result_receipts(api):
    """Run the real JS validator on real synthetic-store snapshots, no host/network."""
    import json
    import shutil
    import subprocess
    from pathlib import Path
    from types import SimpleNamespace
    from test_native_work import Host
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the Python/JS receipt contract check')
    client, _, factory, body = api
    with closing(factory()) as crm:
        store = ScheduledResearchStore(crm)
        saved = store.create(body['data'], idempotency_key=body['idempotency_key'])
        host = Host(); host.profile_name = 'alpha'
        scheduled = store.schedule(host, saved['id'])
        host.identity = SimpleNamespace(job_id=scheduled['job_id'], job_name=scheduled['job_name'], execution_id='fixture-execution',
            source='builtin', profile='alpha', scheduled_instant=scheduled['payload']['run_at'], started_at=None)
        source = store.evidence(host, saved['id'], generation=1, operation_id='source', data={
            **{key:body['data'][key] for key in ('target_kind','target_id','target_version')},
            'question':'Public products?', 'source_url':'https://example.com/products', 'source_title':'Products',
            'observed_at':scheduled['payload']['run_at'], 'claims':['Source says widgets.'], 'hypotheses':[]})
        with_evidence = store.get(saved['id'])
        store.propose(host, saved['id'], generation=1, operation_id='proposal', data={
            'evidence_id':source['id'], 'evidence_digest':source['digest'], 'evidence_lifecycle_version':1,
            'target_version':body['data']['target_version'], 'addition':'Widgets (https://example.com/products).'})
        with_proposal = store.get(saved['id'])
        store.report(host, saved['id'], generation=1, summary='Cited proposal ready.')
        reported = store.get(saved['id'])
        host.identity = None
        cancelled = store.cancel(host, saved['id'], expected_version=reported['version'])
    code = r"""
import vm from 'node:vm';import fs from 'node:fs';import assert from 'node:assert/strict';
const input=JSON.parse(fs.readFileSync(0,'utf8')),context=vm.createContext({URL});
const module=new vm.SourceTextModule(fs.readFileSync('desktop/scheduled-research.js','utf8'),{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const key of ['createElement','useEffect','useRef','useState'])this.setExport(key,()=>{});},{context}));await module.evaluate();
for(const row of input.rows){assert.equal(module.namespace.scheduledResearchRow(row,input.body.data.task_id,'alpha'),true,row.state+': '+JSON.stringify(row));assert.equal(module.namespace.scheduledResearchReceipt(row,input.body,'alpha'),true);}
"""
    result = subprocess.run([node, '--experimental-vm-modules', '--input-type=module', '-e', code],
        input=json.dumps({'body':body, 'rows':[saved,scheduled,with_evidence,with_proposal,reported,cancelled]}),
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1], timeout=30)
    assert result.returncode == 0, result.stderr
