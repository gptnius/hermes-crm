// Executable actual handler tests with synthetic DOM/transport, not a browser audit.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map();function n(){return {dataset:{},value:'',innerHTML:'',open:false,hidden:false,disabled:false,classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(k,v){this[k]=v},querySelector(){return null},querySelectorAll(){return []},reportValidity(){return true},focus(){},close(){this.open=false},showModal(){this.open=true},append(){},prepend(){}}}
const c={console,crypto:require('crypto').webcrypto,structuredClone,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#tasks'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,n());return nodes.get(s)},querySelectorAll(){return []},createElement:n,addEventListener(){},contains(){return true}},FormData:class{constructor(){return Object.entries(c.values)}},fetch(){throw Error('unexpected network')}};
vm.createContext(c);const run=x=>vm.runInContext(x,c);run(fs.readFileSync(require('path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''));
(async()=>{
run("relationshipWorkspace='W';var policy={version:2,required:true,default_owner_label:'Alex'}, calls=[],fail=false,bad=false;render=async()=>{};taskDetail=async()=>{};api=async(path,method='GET',body,key)=>{calls.push({path,method,body,key});if(method==='GET')return {...policy};if(fail)throw Error('network lost');if(bad)return {};if(path.startsWith('task-owner-policy'))return {...body.data,version:body.data.version+1};return {owner_label:null,owner_source:null,title:'Follow up',due_at:'2026-11-08T12:00:00Z',status:'open',...body,id:'T',version:(body.version || 0)+1};};");
assert.equal(run('checkedOwnerPolicy(undefined,true).required'),false); for(const value of ['null','undefined','{}','[]']) assert.throws(()=>run('checkedOwnerPolicy('+value+')'),/could not be verified/);
assert(run("sameOwnerDue('2026-11-08T12:00:00.123456+00:00','2026-11-08T14:00:00.123456+02:00')"));assert(!run("sameOwnerDue('2026-11-08T12:00:00.123457Z','2026-11-08T12:00:00.123456Z')"));
assert.throws(()=>run("ownerTaskData({owner_label:'',owner_choice:'explicit'},policy)"),/required/);
assert.equal(run("ownerTaskData({owner_label:'',owner_choice:'explicit'},{version:0,required:false}).owner_label"),null);
assert.equal(run("ownerTaskData({owner_label:'Alex',owner_choice:'default'},policy).owner_source"),'default');
assert.equal(run("ownerTaskData({owner_label:'Alex',owner_choice:'explicit'},policy).owner_source"),'explicit');
assert.throws(()=>run("ownerTaskData({owner_label:'Other',owner_choice:'default'},policy)"),/exact label/);
assert(run("ownerFields(policy,{}).includes('value=\"Alex\"')"));
assert(run("ownerFields(policy,{id:'legacy'}).includes('value=\"\"')"));
assert(run("ownerFields(policy,{id:'legacy'}).includes('No default is applied automatically')"));
run("var original={id:'T',version:3,title:'Follow up',due_at:'2026-11-08T12:34:56.123456+02:00',status:'open',owner_label:null};taskOwnerEditor(original,[],[],policy)");
c.values={title:'Follow up',due_at:run('localTime(original.due_at)'),status:'done',priority:'normal',owner_label:'Alex',owner_choice:'explicit',contact_id:'',deal_id:'',notes:''};
await nodes.get('#relationship-form').submit({preventDefault(){}});
assert.equal(run("calls.find(c=>c.method==='PATCH').body.due_at"),run('original.due_at'));
assert.equal(run("calls.find(c=>c.method==='PATCH').body.owner_policy_version"),2);
assert(run("calls.find(c=>c.method==='PATCH').key"));
// A later policy cannot silently change draft owner or write with fresh policy.
run('calls=[];taskOwnerEditor(original,[],[],policy);policy={...policy,version:3}');
await nodes.get('#relationship-form').submit({preventDefault(){}});
assert.equal(run("calls.filter(c=>c.method!=='GET').length"),0);assert.match(nodes.get('#relationship-error').textContent,/policy changed/);
// Policy display performs one GET and no automatic save.
run('calls=[]');await run('openTaskOwnerPolicy()');assert.equal(run("calls.filter(c=>c.method!=='GET').length"),0);
c.values={required:'false',default_owner_label:'Sam'};await nodes.get('#relationship-form').submit({preventDefault(){}});
assert.equal(run("calls.find(c=>c.method==='PATCH').body.data.version"),3);
// Unknown task save retains exact serialized data/key across navigation and blocks changed intent.
run("calls=[];fail=true;ownerAttempts.clear()");
await assert.rejects(run("ownerWrite('tasks/T','PATCH',{version:3,owner_label:'Alex',owner_source:'explicit',owner_policy_version:3})"),/Outcome unknown/);
const originalBody=run('JSON.stringify(calls[0].body)'),key=run('calls[0].key');
await assert.rejects(run("ownerWrite('tasks/T','PATCH',{version:3,owner_label:'Other'})"),/earlier save/);
run("relationshipWorkspace='other'");assert.equal(run('ownerNotices()'),'');run("relationshipWorkspace='W';fail=false");await run('retryOwnerWrite()');
assert.equal(run('JSON.stringify(calls.at(-1).body)'),originalBody);assert.equal(run('calls.at(-1).key'),key);assert.equal(run('ownerAttempts.size'),0);
run('bad=true');await assert.rejects(run("ownerWrite('tasks/T','PATCH',{version:3,owner_label:null,owner_source:'explicit'})"),/receipt/);assert.equal(run('ownerAttempts.size'),1);run('bad=false;ownerAttempts.clear()');
// Policy recovery also freezes reviewed policy version and key; no policy refresh resubmits.
run('calls=[];fail=true');await assert.rejects(run("ownerWrite('task-owner-policy','PATCH',{data:{version:3,required:true,default_owner_label:'Alex'}})"),/Outcome unknown/);
const frozenPolicy=run('JSON.stringify(calls[0].body)'),policyKey=run('calls[0].key');run('fail=false');await run('retryOwnerWrite()');assert.equal(run('JSON.stringify(calls.at(-1).body)'),frozenPolicy);assert.equal(run('calls.at(-1).key'),policyKey);
// Stale scope must reject before writing after policy read returns.
run("var oldApi=api;api=async(...args)=>{const result=await oldApi(...args);relationshipWorkspace='other';return result};relationshipWorkspace='W';calls=[]");
await assert.rejects(run("verifyOwnerPolicy(policy,'W',modalEpoch)"),/no longer current/);assert.equal(run("calls.filter(c=>c.method!=='GET').length"),0);run("api=oldApi;relationshipWorkspace='W'");
// Event-created tasks use same explicit/default rules and scoped policy check.
run('calls=[]');await run("eventTaskForm({id:'E',version:4})");assert(nodes.get('#modal-body').innerHTML.includes('Human accountability only'));
run("var eventBody;relationshipWrite=async(path,method,body)=>{eventBody=body;return {}};relationshipDetail=async()=>{}");
c.values={title:'Event task',owner_label:'Alex',owner_choice:'default',due_at:'2026-11-10T12:00:00Z',priority:'normal',contact_id:'',deal_id:'',notes:''};
await nodes.get('#relationship-form').submit({preventDefault(){}});assert.equal(run('eventBody.data.owner_source'),'default');assert.equal(run('eventBody.data.owner_policy_version'),3);
// Rejected original saves retain drafts across close, fresh review, and explicit corrected Save.
for(const kind of ['tasks/T','task-owner-policy']) for(const status of [409,422]) {
 run("ownerAttempts.clear();ownerDrafts.clear();relationshipWorkspace='W';calls=[];fail=true;policy={version:4,required:true,default_owner_label:'Current default'}");
 c.kind=kind; c.rejection=status;
 const payload=kind==='tasks/T' ? "{version:3,title:'Retained draft',due_at:'2026-11-08T12:34:56.123456+02:00',status:'done',owner_label:'Original owner',owner_source:'explicit',owner_policy_version:3}" : "{data:{version:3,required:false,default_owner_label:'Original default'}}";
 await assert.rejects(run(`ownerWrite(kind,'PATCH',${payload})`),/Outcome unknown/);
 run("var recoveryApi=api;fail=false;api=async(path,method='GET',body,key)=>{if(method!=='GET'){const error=new Error('Version rejected');error.status=rejection;throw error;}return recoveryApi(path,method,body,key)}");
 await run('retryOwnerWrite()'); assert.equal(run('ownerAttempts.size'),0);assert.equal(run('ownerDrafts.size'),1);
 run("api=async(path,method='GET',body,key)=>{if(method!=='GET')return recoveryApi(path,method,body,key);calls.push({path,method});if(path.startsWith('task-owner-policy'))return policy;if(path.startsWith('tasks/'))return {...original,version:8,title:'Fresh title'};return []};document.querySelector('#relationship-form').dataset={};document.querySelector('#modal').open=false");
 const before=run('calls.length');await run('recoverOwnerDraft()');assert.equal(run('ownerDrafts.size'),1);assert.equal(run('calls.slice('+before+').filter(c=>c.method!=="GET").length'),0);
 const html=nodes.get('#modal-body').innerHTML;assert(html.includes(kind==='tasks/T' ? 'Retained draft' : 'Original default'));assert(html.includes(kind==='tasks/T' ? 'Reviewed policy version 4' : 'Current policy version 4'));
 // Dismissal retains authority-scoped recovery; another scope cannot see it.
 run("document.querySelector('#relationship-form').dataset.discard='true';closeModal(false);relationshipWorkspace='Other'");assert(!run('ownerNotices().includes("Review rejected draft")'));run("relationshipWorkspace='W';document.querySelector('#relationship-form').dataset={}");await run('recoverOwnerDraft()');
 c.values=kind==='tasks/T' ? {title:'Retained draft',due_at:run("localTime('2026-11-08T12:34:56.123456+02:00')"),status:'done',priority:'normal',owner_label:'Original owner',owner_choice:'explicit',contact_id:'',deal_id:'',notes:''} : {required:'false',default_owner_label:'Original default'};
 await nodes.get('#relationship-form').submit({preventDefault(){}});assert.equal(run('ownerDrafts.size'),0);assert.equal(run('ownerAttempts.size'),0);
 const last=run("calls.filter(c=>c.method==='PATCH').at(-1).body");assert.equal(kind==='tasks/T' ? last.version : last.data.version,kind==='tasks/T' ? 8 : 4);
 run('api=recoveryApi');
}
run("policy={version:3,required:true,default_owner_label:'Alex'}");
// Complete/Reopen always leads to fresh explicit review, never quick hidden backfill.
run("var opened;api=async path=>path.startsWith('task-owner-policy') ? policy : ({...original});openForm=async(type,row)=>{opened=row};calls=[]");await run("toggleTask('T',{disabled:false})");assert.equal(run('opened.status'),'done');assert.equal(run('opened.owner_label'),null);
run("var statusBody;ownerWrite=async(path,method,body)=>{statusBody=body;return {}};policy={...policy,required:false}");await run("toggleTask('T',{disabled:false})");assert.equal(run('statusBody.status'),'done');assert.equal(run('statusBody.owner_policy_version'),3);assert.equal(run("Object.hasOwn(statusBody,'owner_label')"),false);
console.log('PASS standalone ownership: optional/required/default, legacy review, exact timestamps, policy display/save, Event create, fixed-body/key recovery, malformed receipts, stale policy/scope, explicit Complete review. Synthetic DOM.');
})().catch(e=>{console.error(e);process.exitCode=1});
