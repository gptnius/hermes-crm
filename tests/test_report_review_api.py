"""Native authenticated routing only; all host work is a synthetic fixture."""
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from hermes_crm import native_api
from hermes_crm.domain import CRM
from test_report_reviews import make_setup,body,get

@pytest.fixture(params=['native','scheduled_research'])
def api(tmp_path,monkeypatch,request):
    state={'profile':'synthetic'}
    def factory():return CRM(f'sqlite:///{tmp_path}/api.db',profile=state['profile'])
    monkeypatch.setattr(native_api,'open_profile_crm',factory)
    crm=factory();s=make_setup(crm,request.param)
    app=FastAPI();app.include_router(native_api.router)
    yield TestClient(app),state,s
    crm.close()


def test_exact_get_write_scope_strictness_and_no_agent_tool(api):
    client,state,s=api
    url=f"/report-reviews/{s['family']}/{s['assignment']['id']}/{s['report_id']}"
    params={'workspace_token':s['crm'].workspace_token()}
    result=client.get(url,params=params);assert result.status_code==200,result.text
    preview=result.json();assert preview==get(s)
    request={**params,'idempotency_key':'api',**body(preview)}
    assert client.get(url).status_code==422
    assert client.get(url,params={**params,'actor':'owner'}).status_code==400
    for extra in ({'actor':'owner'},{'expected_review_version':True},{'acknowledge_stale':'yes'},{'context':{}},{'profile':'foreign'}):
        assert client.post(url+'/acknowledge',json={**request,**extra}).status_code==422
    wrong={**request,'workspace_token':'wrong'}
    assert client.post(url+'/acknowledge',json=wrong).status_code==409
    assert client.post(url+'/accept',json=request).status_code==422
    duplicate=json.dumps(request)[:-1]+',"expected_review_version":0}'
    assert client.post(url+'/acknowledge',content=duplicate,headers={'content-type':'application/json'}).status_code==422
    response=client.post(url+'/acknowledge',json=request);assert response.status_code==200,response.text
    assert client.post(url+'/acknowledge',json=request).json()==response.json()
    assert client.get(url,params=params).json()['review']['status']=='reviewed_in_crm'
    state['profile']='foreign'
    assert client.get(url,params=params).status_code in (404,503)
    assert client.post(url+'/acknowledge',json=request).status_code in (404,503)
