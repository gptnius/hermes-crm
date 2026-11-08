import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM
from hermes_crm.web import create_app
from hermes_crm import native_api, plugin

@pytest.mark.parametrize('native',[False,True])
def test_policy_api_and_all_task_writers(native,monkeypatch):
    crm=CRM('sqlite:///:memory:'); close=crm.close
    monkeypatch.setattr(crm,'close',lambda:None)
    monkeypatch.setattr(native_api,'open_profile_crm',lambda:crm)
    monkeypatch.setattr(plugin,'open_profile_crm',lambda **kw:crm)
    app=FastAPI();app.include_router(native_api.router)
    client=TestClient(app if native else create_app(crm));prefix='' if native else '/api'
    token=crm.workspace_token()
    try:
        url=prefix+'/task-owner-policy'
        assert client.get(url,params={'workspace_token':'wrong'}).status_code==409
        assert client.get(url,params={'workspace_token':token}).json()['version']==0
        body=dict(workspace_token=token,idempotency_key='policy',data=dict(version=0,required=True,default_owner_label='Alice'))
        assert client.patch(url,json=body).json()['version']==1
        assert client.patch(url,json=body).json()['version']==1
        task=dict(title='T',due_at='2030-01-01T10:00:00Z')
        wrap=lambda d:dict(workspace_token=token,data=d,idempotency_key='create') if native else d
        assert client.post(prefix+'/tasks',json=wrap(task)).status_code==409
        task.update(owner_label='Alice',owner_policy_version=1,owner_source='default')
        response=client.post(prefix+'/tasks',json=wrap(task)); assert response.status_code==201,response.text
        saved=response.json()
        patch=dict(version=1,owner_label='Bob',owner_policy_version=1)
        payload=dict(workspace_token=token,idempotency_key='patch',data=patch) if native else patch
        headers={} if native else {'Idempotency-Key':'patch'}
        first=client.patch(prefix+'/tasks/'+saved['id'],json=payload,headers=headers)
        assert first.status_code==200,first.text
        assert client.patch(prefix+'/tasks/'+saved['id'],json=payload,headers=headers).json()==first.json()
        assert len(client.get(prefix+'/tasks',params={'owner':'present','owner_label':'Bob'}).json())==1
        class Context:
            profile_name='default'
            def __init__(self): self.tools={}
            def get_config(self,k,default=None): return default
            def register_tool(self,**kw): self.tools[kw['name']]=kw
        ctx=Context();plugin.register(ctx)
        invoke=lambda name,args:json.loads(ctx.tools[name]['handler'](args))
        assert ctx.tools['crm_task_owner_policy']['toolset']=='crm_detail_read'
        assert invoke('crm_task_owner_policy',{})['data']['version']==1
        assert not invoke('crm_task_create',dict(title='Missing',due_at=task['due_at']))['ok']
        owned=invoke('crm_task_create',dict(task,idempotency_key='tool'))
        assert owned['ok'] and owned['data']['owner_label']=='Alice'
        assert invoke('crm_task_create',dict(task,idempotency_key='tool'))==owned
        changed=dict(id=owned['data']['id'],version=1,owner_label='Bob',owner_policy_version=1,idempotency_key='tool-edit')
        result=invoke('crm_task_update',changed)
        assert result['ok'] and invoke('crm_task_update',changed)==result
    finally: close()
