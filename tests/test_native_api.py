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
