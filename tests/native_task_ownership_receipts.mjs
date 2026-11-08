// Real isolated native HTTP receipts are fed into the shipped JavaScript verifier.
// Run with project dependencies installed in HERMES_CRM_TEST_PYTHON (default python).
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {readFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import vm from 'node:vm';
const root=fileURLToPath(new URL('..',import.meta.url));
const fixtures=JSON.parse(execFileSync(process.env.HERMES_CRM_TEST_PYTHON || 'python',['-c',`
import json
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM
from hermes_crm import native_api
crm=CRM('sqlite:///:memory:'); close=crm.close; crm.close=lambda:None
app=FastAPI(); app.include_router(native_api.router)
client=TestClient(app); token=crm.workspace_token(); rows=[]
def request(path,method,data,key):
    body=dict(workspace_token=token,idempotency_key=key,data=data)
    r=client.request(method,path,json=body); assert r.status_code in (200,201),r.text
    rows.append(dict(path=path,options=dict(method=method,body=body),result=r.json()))
    return r.json()
try:
  with patch.object(native_api,'open_profile_crm',lambda:crm):
    request('/tasks','POST',dict(title='  Optional task  ',due_at='2030-06-12T10:23:56.123456-04:00',owner_label=None,owner_source='explicit',owner_policy_version=0,contact_id=None,deal_id=None,priority='normal',status='open',notes='  Exact note  '),'empty-create')
    owned=request('/tasks','POST',dict(title='Owned',due_at='2030-06-12T10:23:56.123456-04:00',owner_label='Accountable human',owner_source='explicit',owner_policy_version=0),'owned-create')
    request('/tasks/'+owned['id'],'PATCH',dict(version=1,owner_label=None,owner_source='explicit',owner_policy_version=0),'clear-owner')
    request('/tasks/'+owned['id'],'PATCH',dict(version=1,owner_label=None,owner_source='explicit',owner_policy_version=0),'clear-owner')
    request('/tasks/'+owned['id'],'PATCH',dict(version=2,status='done',owner_policy_version=0),'complete')
finally: close()
print(json.dumps(rows))
`],{cwd:root,encoding:'utf8'}));
const context=vm.createContext({console,URLSearchParams});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/plugin.js',import.meta.url),'utf8'),{context});
await module.link(name=>new vm.SyntheticModule(name==='react'?['createElement','useEffect','useRef','useState']:[],function(){if(name==='react') for(const key of ['createElement','useEffect','useRef','useState'])this.setExport(key,()=>{});},{context}));await module.evaluate();
for(const {path,options,result} of fixtures){
 assert.equal(module.namespace.confirmedTaskReceipt(path,options,result),true,JSON.stringify({options,result}));
 if(Object.hasOwn(options.body.data,'owner_label') && options.body.data.owner_label===null) assert.equal(result.owner_source,'explicit');
 assert.equal(module.namespace.confirmedTaskReceipt(path,options,{...result,version:result.version+1}),false);
 for(const patch of [{title:null},{title:' '},{due_at:null},{due_at:'2030-02-31T10:00:00Z'},{status:'unknown'},{owner_label:{}},{owner_source:'Hermes'}]) assert.equal(module.namespace.confirmedTaskReceipt(path,options,{...result,...patch}),false,JSON.stringify(patch));
 if(options.body.data.due_at){assert.equal(module.namespace.confirmedTaskReceipt(path,options,{...result,due_at:null}),false);assert.equal(module.namespace.confirmedTaskReceipt(path,options,{...result,due_at:'2030-06-12T14:23:56.123457Z'}),false);}
}
console.log('PASS real native HTTP → shipped JS receipt bridge: ownerless creation, owned creation, explicit clear, idempotent clear replay, canonical timestamps and strict versions.');
