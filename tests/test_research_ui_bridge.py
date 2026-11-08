"""Execute standalone-generated transport against the shared real SQLite adapter."""
import json
import subprocess
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from hermes_crm.domain import CRM,CRMError
from hermes_crm.research_api import build_router

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tests/standalone_research_review.cjs'
NATIVE=ROOT/'tests/native_research_contract.mjs'
def test_standalone_real_transport():
    crm=CRM('sqlite:///:memory:')
    try:
        target=crm.create('contacts',{'name':'Synthetic bridge contact','notes':'Prior private note'})
        token=crm.workspace_token()
        @contextmanager
        def service():yield crm
        def require(crm,value):
            if value!=token:raise CRMError('Workspace changed',409)
        app=FastAPI()
        @app.exception_handler(CRMError)
        def error(request,exc):return JSONResponse({'error':str(exc)},status_code=exc.status)
        @app.exception_handler(ValidationError)
        def invalid(request,exc):return JSONResponse({'error':'Invalid input'},status_code=422)
        app.include_router(build_router(service,require,actor='web'));client=TestClient(app)
        raw=subprocess.check_output(['node',str(SCRIPT),'--emit-transport'],cwd=ROOT,text=True)
        calls=json.loads(raw.replace('SYNTHETIC_SCOPE',token).replace('11111111-1111-4111-8111-111111111111',target['id']))
        evidence=proposal=None
        for call in calls:
            path=call['path'];body=call.get('body')
            if evidence:
                path=path.replace('22222222-2222-4222-8222-222222222222',evidence['id'])
            if proposal:
                path=path.replace('33333333-3333-4333-8333-333333333333',proposal['id'])
            if path=='research/proposals':
                body['data'].update(evidence_id=evidence['id'],evidence_digest=evidence['digest'],evidence_lifecycle_version=evidence['lifecycle_version'])
            if path.endswith('/apply'):
                body['data'].update({k:proposal[k] for k in ('proposal_version','proposal_digest','target_version','before_hash','after_hash')})
            response=client.request(call['method'],'/'+path,json=body) if body else client.get('/'+path)
            assert response.status_code in (200,201),response.text
            result=response.json()
            if call['method']=='POST':
                validation=dict(kind='contacts',id=target['id'],request=dict(path=path,body=body),result=result)
                accepted=subprocess.check_output(['node',str(SCRIPT),'--validate-receipt'],input=json.dumps(validation),cwd=ROOT,text=True)
                assert accepted.strip()=='true',(path,result)
                native=subprocess.check_output(['node','--experimental-vm-modules',str(NATIVE),'--validate-receipt'],input=json.dumps(validation),cwd=ROOT,text=True)
                assert native.strip()=='true',(path,result)
                # Retry returns the original committed receipt, with no second append.
                assert client.post('/'+path,json=body).json()==result
                receipt=client.get('/research/operations/'+body['idempotency_key'],params={'workspace_token':token}).json()
                assert receipt==dict(state='committed',receipt=result)
            if '/preview?' in path:
                full_evidence=client.get('/research/evidence/'+evidence['id'],params={'workspace_token':token}).json()
                preview_input=dict(kind='contacts',id=target['id'],evidence=full_evidence,preview=result)
                native=subprocess.check_output(['node','--experimental-vm-modules',str(NATIVE),'--validate-preview'],input=json.dumps(preview_input),cwd=ROOT,text=True)
                assert native.strip()=='true',result
            if path=='research/evidence' and body:evidence=result
            if path=='research/proposals' and body:proposal=result
        current=crm.get('contacts',target['id'])
        assert current['notes']=='Prior private note\n\n  Synthetic addition\n'
        assert current['version']==2
    finally:crm.close()
