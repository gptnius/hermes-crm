import json
import importlib.util
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, func

from hermes_crm.domain import CRM, CRMError, contacts, deals, tasks, activity
from hermes_crm.demo import seed
from hermes_crm import native_api


@pytest.fixture
def native(tmp_path, monkeypatch):
    state = {'profile':'alpha'}
    def factory():
        return CRM(f'sqlite:///{tmp_path}/{state["profile"]}.db', profile=state['profile'])
    monkeypatch.setattr(native_api, 'open_profile_crm', factory)
    app = FastAPI()
    app.include_router(native_api.router, prefix='/api/plugins/hermes-crm')
    return TestClient(app), state, factory


def test_native_routes_share_domain_and_require_workspace_scope(native):
    client, state, factory = native
    prefix = '/api/plugins/hermes-crm'
    meta = client.get(prefix+'/meta').json()
    assert meta['profile']=='alpha' and meta['native_desktop']
    token = meta['workspace_token']
    created = client.post(prefix+'/contacts', json={'data':{'name':'Native demo'},'workspace_token':token,'idempotency_key':'native-create'})
    assert created.status_code==201
    record = created.json()
    assert client.post(prefix+'/contacts', json={'data':{'name':'Native demo'},'workspace_token':token,'idempotency_key':'native-create'}).json()['id']==record['id']
    crm = factory()
    assert crm.get('contacts',record['id'])['name']=='Native demo'
    crm.update('contacts',record['id'],{'version':1,'company':'Shared service'},actor='hermes')
    crm.close()
    assert client.get(prefix+'/contacts/'+record['id']).json()['contact']['company']=='Shared service'
    assert client.patch(prefix+'/contacts/'+record['id'],json={'data':{'version':1,'name':'stale'},'workspace_token':token}).status_code==409
    state['profile']='beta'
    assert client.get(prefix+'/contacts').json()==[]
    assert client.post(prefix+'/contacts',json={'data':{'name':'Wrong workspace'},'workspace_token':token}).status_code==409
    assert client.get(prefix+'/contacts').json()==[]
    assert client.get(prefix+'/meta').json()['workspace_token']!=token


def test_native_validation_and_explicit_demo(native):
    client, state, _ = native
    prefix='/api/plugins/hermes-crm'
    token=client.get(prefix+'/meta').json()['workspace_token']
    assert client.get(prefix+'/overview').json()['contacts']==0
    assert client.post(prefix+'/demo',json={'confirm':False,'workspace_token':token}).status_code==422
    assert client.post(prefix+'/demo',json={'confirm':True,'workspace_token':'stale'}).status_code==409
    result=client.post(prefix+'/demo',json={'confirm':True,'workspace_token':token})
    assert result.status_code==200 and result.json()['demo']
    assert client.get(prefix+'/overview').json()['contacts']==8
    assert client.post(prefix+'/demo',json={'confirm':True,'workspace_token':token}).status_code==409
    assert client.post(prefix+'/contacts',json={'data':{'name':''},'workspace_token':token}).status_code==422
    assert client.post(prefix+'/contacts',json={'data':{'name':'missing token'}}).status_code==422
    assert client.get(prefix+'/tasks?status=open').status_code==200
    assert client.get(prefix+'/tasks?status=invalid').status_code==400
    assert client.post(prefix+'/followup_schedule',json={}).status_code==422


def test_backend_error_does_not_echo_secret(native,monkeypatch):
    client, _, _ = native
    def fail(): raise RuntimeError('postgresql://user:secret-password@private.example/db')
    monkeypatch.setattr(native_api,'open_profile_crm',fail)
    response=client.get('/api/plugins/hermes-crm/meta')
    assert response.status_code==503
    assert 'secret-password' not in response.text and 'private.example' not in response.text


def test_workspace_token_persists_and_is_concurrency_safe(tmp_path):
    url=f'sqlite:///{tmp_path}/scope.db'
    crm=CRM(url)
    def read(_):
        other=CRM(url)
        try: return other.workspace_token()
        finally: other.close()
    with ThreadPoolExecutor(max_workers=4) as pool: values=list(pool.map(read,range(4)))
    assert len(set(values))==1
    assert crm.workspace_token()==values[0]
    crm.close()


def test_demo_seed_rolls_back_whole_workspace(tmp_path,monkeypatch):
    crm=CRM(f'sqlite:///{tmp_path}/demo.db')
    original=CRM.create
    count=0
    def fail_after_some(self,*args,**kwargs):
        nonlocal count
        count+=1
        if count==4: raise RuntimeError('Injected seed failure')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(CRM,'create',fail_after_some)
    with pytest.raises(RuntimeError,match='Injected'): seed(crm)
    with crm.engine.connect() as conn:
        for table in (contacts,deals,tasks,activity):
            assert conn.execute(select(func.count()).select_from(table)).scalar()==0
    monkeypatch.setattr(CRM,'create',original)
    seed(crm)
    assert crm.overview()['contacts']==8
    crm.close()


def test_dashboard_entrypoint_is_standalone_and_not_global_import():
    path=Path(__file__).resolve().parents[1]/'dashboard'/'plugin_api.py'
    spec=importlib.util.spec_from_file_location('hermes_dashboard_plugin_hermes_crm_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.router.routes
    assert module.router.routes[0].endpoint.__module__.startswith('_hermes_crm_api_')
    manifest=json.loads((path.parent/'manifest.json').read_text())
    assert manifest['name']=='hermes-crm' and manifest['api']=='plugin_api.py'


def test_snapshot_uses_one_workspace_and_stale_reads_rejected(native,monkeypatch):
    client,state,factory=native
    calls=[]
    def observed():
        calls.append(state['profile'])
        return factory()
    monkeypatch.setattr(native_api,'open_profile_crm',observed)
    prefix='/api/plugins/hermes-crm'
    snapshot=client.get(prefix+'/snapshot').json()
    assert calls==['alpha']
    token=snapshot['meta']['workspace_token']
    assert snapshot['overview']['profile']=='alpha'
    state['profile']='beta'
    assert client.get(prefix+'/contacts?workspace_token='+token).status_code==409
    assert client.get(prefix+'/tasks/unknown?workspace_token='+token).status_code==409
    assert client.get(prefix+'/contacts/unknown?workspace_token='+token).status_code==409


def test_report_profile_switch_rejects_stale_workspace(native):
    client, state, factory = native
    prefix = '/api/plugins/hermes-crm'
    token = client.get(prefix+'/meta').json()['workspace_token']
    with native_api.service() as crm:
        crm.create('contacts', {'name':'Alpha only'})
    assert client.get(prefix+'/reports/contacts',params={'workspace_token':token}).json()['total']==1
    state['profile']='beta'
    assert client.get(prefix+'/reports/contacts',params={'workspace_token':token}).status_code==409
    new_token=client.get(prefix+'/meta').json()['workspace_token']
    assert client.get(prefix+'/reports/contacts',params={'workspace_token':new_token}).json()['total']==0


def work_save_body(client, factory, *, key='reviewed-local-intent'):
    prefix = '/api/plugins/hermes-crm'
    token = client.get(prefix + '/meta').json()['workspace_token']
    crm = factory()
    try:
        task = crm.create('tasks', {'title': 'Synthetic internal analysis', 'due_at': '2099-12-01T00:00:00Z'})
    finally:
        crm.close()
    return dict(workspace_token=token, task_id=task['id'], expected_task_version=task['version'],
                human_owner='Synthetic owner', prompt='Summarize existing CRM facts only.',
                success_criteria='Separate known facts from unknowns.',
                run_at='2099-12-01T14:00:00.123456-05:00', idempotency_key=key)


def test_native_rest_saves_only_exact_local_intent_and_replays(native, monkeypatch):
    from hermes_crm.native_work import NativeWorkStore, TOOLSETS
    client, _, factory = native
    body = work_save_body(client, factory)
    def forbidden(*args, **kwargs):
        pytest.fail('REST local save must never obtain a host context or dispatch')
    for name in ('_host', 'schedule', 'reconcile', 'cancel', 'report'):
        monkeypatch.setattr(NativeWorkStore, name, forbidden)
    assert set(TOOLSETS) == {'crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp'}
    response = client.post('/api/plugins/hermes-crm/work', json=body)
    assert response.status_code == 201, response.text
    work = response.json()
    assert work['state'] == 'pending' and work['reason'] == 'not_scheduled' and work['job_id'] is None
    assert work['version'] == work['generation'] == 1
    assert work['payload']['run_at'] == '2099-12-01T19:00:00.123456+00:00'
    assert work['payload']['expected_task_version'] == work['payload']['task_version'] == body['expected_task_version']
    assert [event['kind'] for event in work['events']] == ['intent_saved']
    assert work['reports'] == [] and not work['business_task_completed']
    crm = factory()
    try:
        assert NativeWorkStore(crm, initialize=False).get(work['id']) == work
        crm.update('tasks', body['task_id'], {'version': body['expected_task_version'], 'status': 'done'})
    finally:
        crm.close()
    # A lost reply can recover the exact original intent after the task changes.
    replay = client.post('/api/plugins/hermes-crm/work', json=body)
    assert replay.status_code == 201
    assert replay.json()['id'] == work['id'] and replay.json()['payload'] == work['payload']
    assert not replay.json()['source_task_current'] and replay.json()['business_task_completed']
    for change in ({'expected_task_version': 2}, {'prompt': 'Different intent'}, {'run_at': '2099-12-01T19:00:00.123457Z'}):
        assert client.post('/api/plugins/hermes-crm/work', json={**body, **change}).status_code == 409
    page = client.get('/api/plugins/hermes-crm/reports/work', params={'workspace_token': body['workspace_token']}).json()
    assert page['total'] == 1 and page['items'][0]['id'] == work['id']


def test_native_rest_save_schema_and_source_are_fail_closed(native):
    client, _, factory = native
    body = work_save_body(client, factory)
    path = '/api/plugins/hermes-crm/work'
    for missing in body:
        assert client.post(path, json={k: v for k, v in body.items() if k != missing}).status_code == 422
    for value in (None, True, False, '1', 1.0, 0, -1):
        assert client.post(path, json={**body, 'expected_task_version': value}).status_code == 422
    for extra in ({'approved': True}, {'profile': 'foreign'}, {'backend': 'sqlite'}, {'ctx': {}}, {'schedule': True}, {'job_id': 'fake'}):
        assert client.post(path, json={**body, **extra}).status_code == 422
    for name in ('human_owner', 'prompt', 'success_criteria', 'run_at', 'idempotency_key', 'workspace_token', 'task_id'):
        assert client.post(path, json={**body, name: 3}).status_code == 422
    for value in ('2099-02-30T12:00:00Z', '2099-12-01T14:00:00'):
        assert client.post(path, json={**body, 'run_at': value}).status_code == 400
    assert client.post(path, json={**body, 'run_at': '2020-01-01T00:00:00Z'}).status_code == 409
    assert client.post(path, json={**body, 'workspace_token': 'foreign'}).status_code == 409
    assert client.post(path + '?approved=true', json=body).status_code == 400
    assert client.post(path, json={**body, 'expected_task_version': 2}).status_code == 409
    crm = factory()
    try:
        crm.update('tasks', body['task_id'], {'version': 1, 'status': 'done'})
    finally:
        crm.close()
    assert client.post(path, json={**body, 'expected_task_version': 2}).status_code == 409
    assert client.get('/api/plugins/hermes-crm/reports/work', params={'workspace_token': body['workspace_token']}).json()['total'] == 0


def test_native_rest_save_profile_backend_and_token_are_per_call(native, monkeypatch):
    client, state, factory = native
    body = work_save_body(client, factory)
    calls = []
    def observed():
        calls.append(state['profile'])
        return factory()
    monkeypatch.setattr(native_api, 'open_profile_crm', observed)
    path = '/api/plugins/hermes-crm/work'
    first = client.post(path, json=body)
    assert first.status_code == 201 and calls == ['alpha']
    state['profile'] = 'beta'
    assert client.post(path, json=body).status_code == 409
    assert calls == ['alpha', 'beta']
    beta_body = work_save_body(client, factory, key=body['idempotency_key'])
    beta = client.post(path, json=beta_body)
    assert beta.status_code == 201 and beta.json()['profile'] == 'beta'
    assert beta.json()['id'] != first.json()['id']
    state['profile'] = 'alpha'
    assert client.post(path, json=body).json()['id'] == first.json()['id']
    def unavailable(): raise RuntimeError('postgresql://private:secret@invalid/database')
    monkeypatch.setattr(native_api, 'open_profile_crm', unavailable)
    error = client.post(path, json=body)
    assert error.status_code == 503 and 'secret' not in error.text and 'No fallback' in error.text


def test_native_rest_save_atomic_task_guard_and_duplicate_clicks(native, monkeypatch):
    from hermes_crm.native_work import NativeWorkStore
    from sqlalchemy import update
    client, _, factory = native
    body = work_save_body(client, factory)
    path = '/api/plugins/hermes-crm/work'
    original = NativeWorkStore._guard_task
    def source_changed(self, conn, row):
        conn.execute(update(tasks).where(tasks.c.id == row['task_id']).values(version=2))
        original(self, conn, row)
    monkeypatch.setattr(NativeWorkStore, '_guard_task', source_changed)
    assert client.post(path, json=body).status_code == 409
    assert client.get('/api/plugins/hermes-crm/reports/work', params={'workspace_token': body['workspace_token']}).json()['total'] == 0
    monkeypatch.setattr(NativeWorkStore, '_guard_task', original)
    # Initialize tables before the concurrent request race; schema creation is
    # independently tested by the first write above.
    with ThreadPoolExecutor(max_workers=4) as pool:
        replies = list(pool.map(lambda _: client.post(path, json=body), range(4)))
    assert all(reply.status_code == 201 for reply in replies)
    assert len({reply.json()['id'] for reply in replies}) == 1
    assert all(len(reply.json()['events']) == 1 for reply in replies)
