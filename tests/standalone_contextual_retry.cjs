// Actual standalone creation/submit/detail/Back handlers with synthetic DOM and transport.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map();function n(){return {dataset:{},value:'',innerHTML:'',open:false,hidden:false,disabled:false,classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(k,v){this[k]=v},querySelector(){return null},querySelectorAll(){return []},reportValidity(){return true},focus(){},close(){this.open=false},showModal(){this.open=true},append(){},prepend(){}}}
const c={console,crypto:require('crypto').webcrypto,structuredClone,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#contacts'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,n());return nodes.get(s)},querySelectorAll(){return []},createElement:n,addEventListener(){},contains(){return true}},FormData:class{constructor(){return Object.entries(c.values)}},fetch(){throw Error('unexpected network')}};vm.createContext(c);const run=x=>vm.runInContext(x,c);run(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''));

(async()=>{
run("relationshipWorkspace='W'; var calls=[],fail=true,appended=[];render=async()=>{};exactSearch=async()=>{};document.querySelector('#modal-body').append=b=>appended.push(b);api=async(path,method,body)=>{if(method==='POST'){calls.push({path,method,body});if(fail)throw Error('lost response');return {contact:{id:'new',version:1},company_link:{contact_id:'new',contact_version:1,company_id:body.company_id,company_link_basis:body.company_id?'explicit':'unlinked'}};}if(path==='meta')return {workspace_token:'W'};if(path==='contacts/new')return {contact:{id:'new',version:1,name:'Original',lifecycle:'lead'},activity:[],deals:[],tasks:[]};throw Error('unexpected read '+path)};");
for(const origin of ['A',null]){
 for(const retry of ['banner','same-payload-save']){
  run('relationshipAttempts.clear();calls=[];appended=[];fail=true');nodes.get('#relationship-form')&&(nodes.get('#relationship-form').dataset={});
  c.original=origin;c.values={name:'Original',email:'',company:'Legacy',title:'',lifecycle:'lead',notes:'',company_id:origin||''};
  await run("original ? startRelatedCreate('contacts','companies',{id:original,version:7}) : openForm('contact')");
  await nodes.get('#relationship-form').submit({preventDefault(){}});assert.equal(run('calls.length'),1);const frozen=run('JSON.stringify(calls[0].body)');
  nodes.get('#relationship-form').dataset.discard='true';run('closeModal(false)');
  nodes.get('#relationship-form').dataset={};await run("startRelatedCreate('contacts','companies',{id:'B',version:3})");assert.equal(nodes.get('[name="company_id"]').dataset.reviewedId,'B');
  assert(nodes.get('#relationship-error').textContent.includes(origin ? 'companies record A' : 'the list (no source record)'));
  run('fail=false');
  if(retry==='banner'){
   nodes.get('#relationship-form').dataset.discard='true';run('closeModal(false)');
   await run("relationshipClick({target:{closest:()=>({dataset:{action:'relationship-retry'}})}})");
  }else{
   // User selects original A (or clears B) and fills exactly the original values; actual Save retries matching payload.
   nodes.get('[name="company_id"]').dataset={reviewedId:origin||'',reviewedVersion:origin?'7':''};
   await nodes.get('#relationship-form').submit({preventDefault(){}});
  }
  assert.equal(run('calls.length'),2,'Only original attempt and one replay are transmitted');
  assert.equal(run('JSON.stringify(calls.at(-1).body)'),frozen);
  assert.equal(run('new Set(calls.map(call=>call.body.idempotency_key)).size'),1,'Replays never acquire a new key');
  const backs=run('appended.length');run("var restored;restoreRelatedSource=s=>{restored=s}");if(backs)run('appended.at(-1).onclick()');
  const actual=backs?run('restored.id'):null;
  assert.equal(actual,origin,`${retry} must retain original source including explicit null`);
 }
}
for(const change of ['workspace','navigation']){
 run("relationshipWorkspace='W';relationshipAttempts.clear();calls=[];appended=[];fail=false");
 nodes.get('#relationship-form').dataset={};c.values={name:'Original',email:'',company:'Legacy',title:'',lifecycle:'lead',notes:'',company_id:'A'};
 await run("startRelatedCreate('contacts','companies',{id:'A',version:7})");
 run("var priorApi=api,releaseResponse;api=async(path,method,body)=>{if(method==='POST')await new Promise(resolve=>{releaseResponse=resolve});return priorApi(path,method,body)}");
 const pending=nodes.get('#relationship-form').submit({preventDefault(){}});
 if(change==='workspace')run("relationshipWorkspace='other'");else run("showModal('Unrelated navigation')");
 run('releaseResponse()');await pending;assert.equal(run('appended.length'),0,'Late completion cannot navigate another context');
 run('api=priorApi');
}
console.log('PASS actual standalone submit/detail/Back handlers: original Company/list ownership across banner and alternate Save replays, identical body/key, no duplicate create keys, honest unknown-context notice, late workspace/navigation suppression. Synthetic DOM only.');
})().catch(e=>{console.error(e);process.exitCode=1});
