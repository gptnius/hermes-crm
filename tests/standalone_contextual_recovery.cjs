// Synthetic DOM actual-handler regression for definitive rejected retries.
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map();function n(){return {dataset:{},value:'',innerHTML:'',open:false,hidden:false,disabled:false,classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(k,v){this[k]=v},querySelector(){return null},querySelectorAll(){return []},reportValidity(){return true},focus(){},close(){this.open=false},showModal(){this.open=true},append(){},prepend(){}}}
const c={console,crypto:require('crypto').webcrypto,structuredClone,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#contacts'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,n());return nodes.get(s)},querySelectorAll(){return []},createElement:n,addEventListener(){},contains(){return true}},FormData:class{constructor(){return Object.entries(c.values)}},fetch(){throw Error('unexpected network')}};vm.createContext(c);const run=x=>vm.runInContext(x,c);run(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''));

(async()=>{
run("relationshipWorkspace='W'; var calls=[],mode='unknown',renders=0;render=async()=>{renders++};exactSearch=async()=>{};api=async(path,method,body)=>{if(method==='POST'){calls.push({path,body});const e=Error(mode==='unknown'?'lost response':'Record changed; review');if(mode!=='unknown')e.status=Number(mode);throw e}if(path==='meta')return {workspace_token:'W'};if(path.startsWith('companies/')){if(path.includes('/records/'))return {items:[],total:0,offset:0,limit:25};const id=path.split('/')[1].split('?')[0];return {company:{id,name:'Company '+id,version:7},counts:{}}}throw Error('Unexpected read')};");
for(const kind of ['contact','event'])for(const origin of ['A',null])for(const status of [409,422]){
 run("relationshipAttempts.clear();relationshipDrafts.clear();calls=[];renders=0;mode='unknown'");if(nodes.has('#relationship-form'))nodes.get('#relationship-form').dataset={};
 c.kind=kind;c.origin=origin;c.source=origin?{kind:'companies',id:'A',scope:'W',tab:'events',offset:25}:null;
 c.values=kind==='contact'?{name:'Recover Me',email:'recover@example.com',company:'Legacy text',company_id:origin||'',title:'Role',lifecycle:'partner',notes:'Keep notes'}:{title:'Recover Event',kind:'call',starts_at:'2026-11-12T10:00:00.123456Z',ends_at:'2026-11-12T11:00:00.123456Z',timezone:'UTC',contact_id:null,deal_id:null,company_id:origin,notes:'Keep Event notes'};
 if(kind==='contact')await run("openForm('contact',{company_id:origin,expected_company_version:origin?7:null,custom_fields:{zero:0,off:false,empty:null}},source)");else run("relationshipEditor('events',{},'',values,source)");
 await nodes.get('#relationship-form').submit({preventDefault(){}});assert.equal(run('relationshipAttempts.size'),1);const first=run('JSON.stringify(calls[0])');
 assert(nodes.get('#relationship-notices').innerHTML.includes('data-action="relationship-retry"'),'Unknown outcome immediately exposes recovery without rerender');
 assert.equal(run('renders'),0);
 nodes.get('#relationship-form').dataset.dirty='true';assert.equal(run('closeModal()'),false);
 nodes.get('#relationship-discard-confirm').onclick();await new Promise(resolve=>setImmediate(resolve));
 run('closeModal(false)');await run("relationshipDetail('companies','B')");run('closeModal(false)');
 assert(nodes.get('#relationship-notices').innerHTML.includes('data-action="relationship-retry"'),'Retry remains reachable after source A → B → close on unchanged list');
 assert.equal(run('renders'),0,'Closing parent details does not depend on list rerender');
 c.status=status;run('mode=String(status)');await run("relationshipClick({target:{closest:()=>({dataset:{action:'relationship-retry'}})}})");
 assert.equal(run('JSON.stringify(calls[1])'),first);assert.equal(run('calls.length'),2,'Recovery never auto-posts');assert.equal(run('relationshipAttempts.size'),0);
 assert(!nodes.get('#relationship-notices').innerHTML.includes('data-action="relationship-retry"'),'Rejected original retry removes obsolete unknown control');
 assert.equal(nodes.get('#modal').open,true);assert(nodes.get('#modal-body').innerHTML.includes(kind==='contact'?'Recover Me':'Recover Event'));assert(nodes.get('#modal-body').innerHTML.includes(kind==='contact'?'Keep notes':'Keep Event notes'));
 const restoredSource=nodes.get('#relationship-form').returnContext;assert.equal(restoredSource?.id??null,origin);if(origin)assert.equal(restoredSource.offset,25);
 assert.equal(nodes.get('#relationship-form').dataset.dirty,'true');assert.equal(run('relationshipDrafts.size'),0);assert(run('renders')>0,'Rejected retry rerenders obsolete unknown banner');
 if(kind==='contact'){
  assert.equal(nodes.get('[name="company_id"]').dataset.reviewedVersion,'','Old Company version is not silently reapproved');
  if(origin){await nodes.get('#relationship-form').submit({preventDefault(){}});assert.equal(run('calls.length'),2,'Save requires explicit Company re-review');}
  nodes.get('[name="company_id"]').dataset={reviewedId:origin||'',reviewedVersion:origin?'9':''};
  await nodes.get('#relationship-form').submit({preventDefault(){}});
  assert.equal(run('calls.length'),3);assert.notEqual(run('calls[2].body.idempotency_key'),run('calls[0].body.idempotency_key'));
  assert.equal(run('JSON.stringify(calls[2].body.data.custom_fields)'),JSON.stringify({zero:0,off:false,empty:null}));
 }else assert(nodes.get('#modal-body').innerHTML.includes('2026-11-12T10:00:00.123456Z'),'Event precise times retained');
}
// Late known failures retain reachable drafts without opening over newer context.
for(const change of ['workspace','navigation']){
 run("relationshipWorkspace='W';relationshipAttempts.clear();relationshipDrafts.clear();calls=[];mode='unknown'");nodes.get('#relationship-form').dataset={};
 c.values={name:'Late Draft',company_id:'A'};await run("openForm('contact',{company_id:'A',expected_company_version:7}, {kind:'companies',id:'A',scope:'W'})");await nodes.get('#relationship-form').submit({preventDefault(){}});
 nodes.get('#relationship-form').dataset.discard='true';run('closeModal(false)');run("mode='409';var priorApi=api,release;api=async(path,method,body)=>{if(method==='POST')await new Promise(resolve=>{release=resolve});return priorApi(path,method,body)}");
 const pending=run("relationshipClick({target:{closest:()=>({dataset:{action:'relationship-retry'}})}})");
 if(change==='workspace')run("relationshipWorkspace='different'");else run("showModal('Unrelated newer detail')");
 run('release()');await pending;assert.equal(run('relationshipDrafts.has("W")'),true);assert(!nodes.get('#modal-body').innerHTML.includes('Original draft restored'));
 if(change==='navigation')assert.equal(nodes.get('#modal-body').innerHTML,'Unrelated newer detail');
 run("api=priorApi;relationshipWorkspace='W'");nodes.get('#relationship-form').dataset={};run("closeModal(false);recoverRelationshipDraft()");assert(nodes.get('#modal-body').innerHTML.includes('Late Draft'));assert.equal(nodes.get('#relationship-form').returnContext.id,'A');
}
console.log('PASS actual rejected-retry recovery: Contact/Event original source or list, unknown→409/422, custom zero/false/null, precise times, fresh Company review, no automatic writes, new key only after explicit corrected Save, late scope/navigation retained recovery. Synthetic DOM only.');
})().catch(e=>{console.error(e);process.exitCode=1});
