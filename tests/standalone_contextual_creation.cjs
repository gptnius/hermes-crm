// Synthetic DOM/transport contract tests; no claim of rendered-browser coverage.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const nodes=new Map(),requests=[];
function node(){return {innerHTML:'',textContent:'',dataset:{},open:false,hidden:false,value:'',classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(k,v){this[k]=v;},querySelector(){return node();},querySelectorAll(){return [];},focus(){},close(){this.open=false;},showModal(){this.open=true;},append(){},prepend(){}};}
let response={},failure=null;
const context={console,crypto,structuredClone,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#overview'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},querySelectorAll(){return [];},createElement:node,addEventListener(){},contains(){return true;}},fetch:async(url,options)=>{requests.push({url,options});if(failure)throw failure;return {ok:true,status:200,json:async()=>response};}};
vm.createContext(context);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''),context);
const run=s=>vm.runInContext(s,context),plain=x=>JSON.parse(JSON.stringify(x));
(async()=>{
 run("relationshipWorkspace='workspace-a'");
 context.selected={dataset:{reviewedId:'company-b',reviewedVersion:'7'}};
 context.values={name:'Ada',company:'Independent text',company_id:'company-b'};
 context.record={custom_fields:{zero:0,off:false,empty:null}};
 const payload=run('contactCreatePayload(values,record,selected)');
 assert.deepEqual(plain(payload),{data:{name:'Ada',company:'Independent text',custom_fields:{zero:0,off:false,empty:null}},company_id:'company-b',expected_company_version:7});
 context.body=payload;
 assert.throws(()=>run("contactCreatePayload({...values,company_id:'other'},record,selected)"),/review/);
 assert.deepEqual(plain(run("contactCreatePayload({...values,company_id:''},record,selected)")).company_id,null);
 for(const version of ['0','-1','NaN','1.5','']){context.bad={dataset:{reviewedId:'company-b',reviewedVersion:version}};assert.throws(()=>run('contactCreatePayload(values,record,bad)'),/review/);}
 const receipt={contact:{id:'contact-new',version:1},company_link:{contact_id:'contact-new',contact_version:1,company_id:'company-b',company_link_basis:'explicit'}};
 context.receipt=receipt;assert(run("confirmedRelationshipReceipt('relationship-contacts','POST',body,receipt)"));
 for(const wrong of [{},receipt.contact,{...receipt,company_link:null},{...receipt,contact:{id:'',version:1}},{...receipt,company_link:{...receipt.company_link,contact_version:2}},{...receipt,company_link:{...receipt.company_link,company_id:'other'}},{...receipt,company_link:{...receipt.company_link,company_link_basis:'unlinked'}}]){
  response=wrong;await assert.rejects(run("relationshipWrite('relationship-contacts','POST',body)"),/Outcome unknown/);
  const original=JSON.parse(requests.at(-1).options.body);run('closeModal()');
  await assert.rejects(run("relationshipWrite('relationship-contacts','POST',{...body,company_id:null})"),/earlier write/);
  run("relationshipWorkspace='workspace-b'");assert.equal(run('relationshipAttempts.has(relationshipWorkspace)'),false);
  run("relationshipWorkspace='workspace-a'"); response=receipt;await run("relationshipWrite('relationship-contacts','POST',body)");
  assert.equal(JSON.parse(requests.at(-1).options.body).idempotency_key,original.idempotency_key);
 }
 context.eventBody={data:{contact_id:null,deal_id:'deal-one',company_id:null}};
 for(const result of [{id:'event',version:1},{id:'event',version:1,contact_id:'inferred',deal_id:'deal-one',company_id:null}]){context.result=result;assert(!run("confirmedRelationshipReceipt('events','POST',eventBody,result)"));}
 context.result={id:'event',version:1,contact_id:null,deal_id:'deal-one',company_id:null};assert(run("confirmedRelationshipReceipt('events','POST',eventBody,result)"));
 // A source row is never the edit row. No request happens until Save.
 run("var originalForm=relationshipForm,captured; relationshipForm=(title,fields,submit,done,source)=>{captured={title,fields,submit,source};};");
 const before=requests.length;
 for(const [kind,key] of [['companies','company_id'],['contacts','contact_id'],['deals','deal_id']]){
  context.kind=kind;run("startRelatedCreate('events',kind,{id:'source',version:9,company_id:'must-not-infer',contact_id:'must-not-infer',title:'Not the Event'})");
  assert.equal(run('captured.title'),'Add Event');assert(!run('captured.fields').includes('must-not-infer'));
  assert(run('captured.fields').includes(`name="${key}" value="source"`));assert.equal(run('captured.source.id'),'source');
 }
 assert.equal(requests.length,before);
 run("relationshipForm=originalForm");
 // Paged search is independent of the selected exact ID/version, including duplicate names.
 const search={dataset:{exactSearch:'companies',exactName:'company_id'},value:''};context.search=search;
 const selected=nodes.get('[name="company_id"]')||node();nodes.set('[name="company_id"]',selected);selected.value='company-b';selected.dataset={reviewedId:'company-b',reviewedVersion:'7'};
 for(const offset of [0,25,50,75,100]){
  response={items:Array.from({length:25},(_,i)=>({id:'company-'+(offset+i),name:'Duplicate',version:offset+i+1})),total:125,offset,limit:25};
  await run(`exactSearch(search,${offset})`);assert(requests.at(-1).url.includes('offset='+offset));assert(requests.at(-1).url.includes('limit=25'));
  assert.equal(selected.value,'company-b');assert.equal(selected.dataset.reviewedVersion,'7');
 }
 const results=nodes.get('[data-exact-results="company_id"]');
 results.querySelectorAll=()=>[...results.innerHTML.matchAll(/data-exact-id="([^"]+)" data-exact-version="([^"]*)"/g)].map(match=>({dataset:{exactId:match[1],exactVersion:match[2]},addEventListener(type,handler){this[type]=handler;}}));
 // Capture actual click handlers bound to a later-page duplicate record.
 const bound=[];results.querySelectorAll=()=>[...results.innerHTML.matchAll(/data-exact-id="([^"]+)" data-exact-version="([^"]*)"/g)].map(match=>{const button={dataset:{exactId:match[1],exactVersion:match[2]},addEventListener(type,handler){this[type]=handler;}};bound.push(button);return button;});
 response={items:[{id:'duplicate-later',name:'Duplicate',version:17}],total:125};await run('exactSearch(search,100)');bound[0].click();
 assert.equal(selected.value,'duplicate-later');assert.equal(selected.dataset.reviewedId,'duplicate-later');assert.equal(selected.dataset.reviewedVersion,'17');
 assert(results.textContent.includes('Reviewed version 17'));
 search.value='Renamed';response={items:[],total:0};await run('exactSearch(search)');assert(requests.at(-1).url.includes('q=Renamed'));assert(requests.at(-1).url.includes('offset=0'));
 // Dirty cancel returns to the exact source only after explicit discard.
 run("var savedRestore=restoreRelatedSource,restored=[]; restoreRelatedSource=source=>restored.push(source); relationshipForm('Create', '', ()=>{}, null, {kind:'companies',id:'exact-parent',scope:relationshipWorkspace,tab:'events',offset:100});");
 const form=nodes.get('#relationship-form');form.dataset.dirty='true';
 assert.equal(run('closeModal()'),false);assert.equal(run('restored.length'),0);
 nodes.get('#relationship-keep').onclick();assert.equal(run('restored.length'),0);
 nodes.get('#relationship-discard-confirm').onclick();assert.equal(run('restored[0].id'),'exact-parent');assert.equal(run('restored[0].offset'),100);
 run('restoreRelatedSource=savedRestore');delete form.dataset.dirty;delete form.dataset.discard;
 // Unknown attempt stores its original source with its immutable payload/key.
 failure=new Error('timeout');
 await assert.rejects(run("relationshipWrite('relationship-contacts','POST',body,{kind:'companies',id:'original-parent',scope:relationshipWorkspace})"),/Outcome unknown/);
 assert.equal(run('relationshipAttempts.get(relationshipWorkspace).returnContext.id'),'original-parent');
 const frozen=run('relationshipAttempts.get(relationshipWorkspace).payload');
 await assert.rejects(run("relationshipWrite('relationship-contacts','POST',{...body,expected_company_version:8},{id:'changed-parent'})"),/earlier write/);
 assert.equal(run('relationshipAttempts.get(relationshipWorkspace).payload'),frozen);
 failure=null;response=receipt;await run("relationshipWrite('relationship-contacts','POST',body)");
 // A pending successful response is reconciled only in its initiating workspace.
 run("var oldApi=api,resolveLate; api=()=>new Promise(resolve=>{resolveLate=resolve;}); var pendingWrite=relationshipWrite('relationship-contacts','POST',body);");
 run("relationshipWorkspace='workspace-b'; resolveLate(receipt)");await run('pendingWrite');
 assert.equal(run('relationshipWorkspace'),'workspace-b');assert.equal(run('relationshipAttempts.has("workspace-a")'),false);
 run("relationshipWorkspace='workspace-a'; api=oldApi");
 // Definitive stale/archive rejects release the key while preserving caller draft.
 run("api=async()=>{const error=new Error('stale or archived');error.status=409;throw error;}");
 await assert.rejects(run("relationshipWrite('relationship-contacts','POST',body)"),/stale/);assert.equal(run('relationshipAttempts.size'),0);assert.equal(context.values.company,'Independent text');
 console.log('PASS standalone contextual creation: atomic payload/custom values, reviewed exact versions, >100 paged duplicate names/search/offpage selection, source-only prefills, no pre-save writes, nested receipts, unknown retries across close/workspaces, stale/archive release. Synthetic fixtures only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
