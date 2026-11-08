// Synthetic-only executable standalone Research UI contract and interrupted-flow checks.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const nodes=new Map();
function node(){return {dataset:{},innerHTML:'',open:false,disabled:false,hidden:false,addEventListener(k,f){this[k]=f},querySelector(){return null},querySelectorAll(){return []},focus(){},reportValidity(){return true},close(){this.open=false},showModal(){this.open=true},append(){},prepend(){},classList:{toggle(){}}};}
const c={console,crypto:crypto.webcrypto,TextEncoder,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#contacts'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s)},querySelectorAll(){return []},createElement:node,addEventListener(){},contains(){return true}},FormData:class{constructor(){return Object.entries(c.values||{})}},fetch(){throw Error('Network forbidden in synthetic QA')}};
vm.createContext(c);const run=s=>vm.runInContext(s,c);
run(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''));
if(process.argv.includes('--validate-receipt')) {
 c.input=JSON.parse(fs.readFileSync(0,'utf8')); console.log(run('researchReceipt({kind:input.kind,id:input.id,path:input.request.path,body:input.request.body},input.result)'));process.exit();
}
const id='11111111-1111-4111-8111-111111111111',eid='22222222-2222-4222-8222-222222222222',pid='33333333-3333-4333-8333-333333333333',hash='a'.repeat(64);
Object.assign(c,{id,eid,pid,hash});
run(`relationshipWorkspace='SYNTHETIC_SCOPE';var calls=[],ctx=researchContext('contacts',id,()=>{});var data={target_kind:'contacts',target_id:id,target_version:1,question:'Synthetic question',source_url:'https://example.invalid/source',source_title:'Synthetic source',observed_at:'2030-01-01T12:00:00Z',published_on:null,claims:['Synthetic claim'],hypotheses:['Synthetic hypothesis']};var evidence={...data,id:eid,digest:hash,lifecycle_version:1,archived_at:null,recorded_at:'2030-01-01T12:00:00Z',claims_count:1,hypotheses_count:1};var proposal={id:pid,target_kind:'contacts',target_id:id,evidence_id:eid,evidence_digest:hash,evidence_lifecycle_version:1,target_version:1,addition:'  Synthetic addition\\n',proposal_version:1,proposal_digest:hash,before_hash:hash,after_hash:hash,status:'pending',created_at:'2030-01-01T12:00:00Z'};var receipt={evidence_id:eid,evidence_digest:hash,evidence_lifecycle_version:1,actor:'web',recorded_at:'2030-01-01T12:00:00Z',proposal_id:pid,proposal_digest:hash,proposal_version:2,target_kind:'contacts',target_id:id,target_version:1,before_hash:hash,after_hash:hash,status:'applied',applied_target_version:2};api=async(path,method='GET',body)=>{calls.push({path,method,body});if(method==='POST'){if(path==='research/evidence')return evidence;if(path==='research/proposals')return {...proposal,...body.data};if(path.endsWith('/archive'))return {...evidence,lifecycle_version:2,archived_at:'2030-01-01T12:00:00Z'};if(path.endsWith('/restore'))return {...evidence,lifecycle_version:3};if(path.endsWith('/dismiss'))return {...receipt,status:'dismissed'};return receipt;}if(path.startsWith('contacts/'))return {contact:{id,version:1,name:'Synthetic contact',notes:''}};if(path.startsWith('research/evidence/'))return evidence;if(path.startsWith('research/proposals/'))return {...proposal,stale:false,current_notes:'',proposed_notes:proposal.addition};return {items:[],total:0,offset:0,limit:10};};`);
(async()=>{
 if(process.argv.includes('--emit-transport')){
  await run("relationshipRead('research/evidence',{target_kind:'contacts',target_id:id,limit:10,offset:0})");
  await run("researchWrite(ctx,'research/evidence',data)");
  await run("researchWrite(ctx,'research/proposals',{evidence_id:eid,evidence_digest:hash,evidence_lifecycle_version:1,target_version:1,addition:proposal.addition})");
  await run("relationshipRead('research/proposals/'+pid+'/preview')");
  await run("researchWrite(ctx,'research/proposals/'+pid+'/apply',{proposal_version:1,proposal_digest:hash,target_version:1,before_hash:hash,after_hash:hash})");
  await run("researchWrite(ctx,'research/evidence/'+eid+'/archive',{lifecycle_version:1})");
  await run("researchWrite(ctx,'research/evidence/'+eid+'/restore',{lifecycle_version:2})");
  console.log(run('JSON.stringify(calls)'));return;
 }
 await run("researchWrite(ctx,'research/evidence',data)");assert.equal(run('researchAttempts.size'),0);assert.equal(run('calls[0].body.workspace_token'),'SYNTHETIC_SCOPE');
 // Malformed receipts freeze the immutable original request, and explicit lookup/replay cannot change it.
 run("var originalApi=api;api=async()=>({wrong:true})");
 await assert.rejects(run("researchWrite(ctx,'research/evidence',data)"),/Unverified/);
 const frozen=run("JSON.stringify(researchAttempts.get(ctx.scope).body)");
 await assert.rejects(run("researchWrite(ctx,'research/evidence',{...data,question:'changed'})"),/earlier/);
 run("api=async()=>({state:'unknown'})");await run('researchRecover()');assert.equal(run('researchAttempts.size'),1);
 run("api=async(path,method,body)=>{calls.push({path,method,body});return evidence}");await run('researchRecover(true)');assert.equal(run('researchAttempts.size'),0);assert.equal(run('JSON.stringify(calls.at(-1).body)'),frozen);
 // Conflicts release a rejected operation; next explicit save gets a new key.
 run("api=async()=>{let e=Error('Target changed');e.status=409;throw e}");await assert.rejects(run("researchWrite(ctx,'research/evidence',data)"),/Target changed/);assert.equal(run('researchAttempts.size'),0);
 // Newer view and A -> B -> A invalidate callbacks, even when the token returns to A.
 run("api=originalApi;adoptCatalog({workspace_token:'B'});adoptCatalog({workspace_token:'SYNTHETIC_SCOPE'})");assert.equal(run('researchCurrent(ctx)'),false);await assert.rejects(run("researchWrite(ctx,'research/evidence',data)"),/no longer/);
 run("ctx=researchContext('contacts',id,()=>{});var release;api=async()=>{await new Promise(r=>release=r);return evidence}");const pending=run("researchWrite(ctx,'research/evidence',data)");await assert.rejects(run("researchWrite(ctx,'research/evidence',data)"),/earlier/);run('modalEpoch++;release()');await pending;assert.equal(run('researchCurrent(ctx)'),false);assert.equal(run('researchAttempts.size'),0);
 // Detail output remains escaped; URLs have no automatic resource tags or clickable target.
 run("api=originalApi;ctx=researchContext('contacts',id,()=>{});evidence.source_title='<img src=x onerror=alert(1)>';evidence.claims=['<script>evil()</script>'];evidence.hypotheses=['<b>guess</b>'];");await run('researchEvidence(ctx,eid)');let html=nodes.get('#modal-body').innerHTML;assert(html.includes('&lt;script&gt;'));assert(!html.includes('<img'));assert(!html.includes('<a '));assert(html.includes('Hypotheses'));assert(html.includes('Server-derived channel:'));assert(html.includes('not a verified person'));assert(html.includes('Entered offset: Z'));assert(html.includes('Raw observation timestamp:'));
 // Full-note preview exact append and wrong-target guards.
 assert.equal(run("researchPreviewValid({...proposal,stale:false,current_notes:'',proposed_notes:proposal.addition},ctx,pid)"),true);
 assert.equal(run("researchPreviewValid({...proposal,stale:false,current_notes:'before',proposed_notes:'truncated'},ctx,pid)"),false);
 assert.equal(run("researchPreviewValid({...proposal,target_id:'wrong',stale:true},ctx,pid)"),false);
 assert.equal(run("researchPreviewValid({...proposal,addition:'😀'.repeat(10000),stale:false,current_notes:'',proposed_notes:'😀'.repeat(10000)},ctx,pid)"),true,'API limits count code points, not UTF-16 units');
 assert.equal(run("researchPreviewValid({...proposal,addition:'😀'.repeat(10001),stale:false,current_notes:'',proposed_notes:'😀'.repeat(10001)},ctx,pid)"),false);
 // Actual paged list handler uses exact target and preserves offset.
 run("document.querySelector('#relationship-form').dataset={}");await run("openResearch('contacts',id,null,'proposals',20)");assert(run("calls.at(-1).path.includes('target_id='+id)"));assert(run("calls.at(-1).path.includes('offset=20')"));
 // Actual preview checks hashes before enabling Apply and sends only the reviewed identifiers.
 c.beforeHash=crypto.createHash('sha256').update('').digest('hex');c.afterHash=crypto.createHash('sha256').update('  Synthetic addition\n').digest('hex');
 run("ctx=researchContext('contacts',id,()=>{});var fresh={...proposal,before_hash:beforeHash,after_hash:afterHash,stale:false,current_notes:'',proposed_notes:proposal.addition};api=async(path,method='GET',body)=>{if(path.includes('/preview'))return fresh;if(method==='POST'){calls.push({path,method,body});return {...receipt,before_hash:beforeHash,after_hash:afterHash};}return originalApi(path,method,body)};calls=[]");
 await run('researchPreview(ctx,pid)');assert.equal(run("calls.filter(c=>c.method==='POST').length"),0);assert(nodes.get('#modal-body').innerHTML.includes('Apply reviewed append'));assert(nodes.get('#modal-body').innerHTML.includes('Server-derived channel:'));
 await nodes.get('#research-apply').onclick();assert.equal(run("calls.filter(c=>c.method==='POST').length"),1);assert.equal(run("Object.hasOwn(calls.find(c=>c.method==='POST').body.data,'current_notes')"),false);assert.equal(run('researchAttempts.size'),0);
 run("ctx=researchContext('contacts',id,()=>{});fresh={...fresh,stale:true,stale_reason:'target_changed'}");await run('researchPreview(ctx,pid)');assert(nodes.get('#modal-body').innerHTML.includes('id=\"research-apply\" disabled'));assert(!nodes.get('#modal-body').innerHTML.includes('<h3>Current notes</h3>'));
 run("ctx=researchContext('contacts',id,()=>{});fresh={...fresh,stale:false,before_hash:hash}");await run('researchPreview(ctx,pid)');assert(nodes.get('#toast').textContent.includes('hashes do not match'));
 // Actual evidence form submission preserves corrected draft on conflict and requires explicit refresh.
 run("ctx=researchContext('contacts',id,()=>{});api=originalApi");await run('researchEvidenceForm(ctx)');
 assert(nodes.get('#modal-body').innerHTML.includes('name="observed_at" type="text" value=""'),'Observation time must not default silently');
 assert(run("researchObservedPreview('').includes('No observation time supplied')"));
 assert(run("researchObservedPreview('2030-01-01T12:00:00+05:30').includes('Entered offset: +05:30')"));
 assert(run("researchObservedPreview('2030-01-01T12:00:00').includes('Enter a valid')"));
 assert(run("researchObservedPreview('2030-02-30T12:00:00Z').includes('Enter a valid')"));
 await nodes.get('#research-observed-now').onclick();assert(/Z$/.test(nodes.get('[name="observed_at"]').value));assert.equal(nodes.get('#relationship-form').dataset.dirty,'true');assert(nodes.get('#research-observed-preview').textContent.includes('not verified'));
 c.values={question:'Question',source_url:'https://example.invalid/synthetic',source_title:'Title',observed_at:'2030-01-01T12:00:00Z',published_on:'',claims:' A claim ',hypotheses:' A hypothesis '};
 run("api=async(path,method)=>{if(method==='POST'){let e=Error('Conflict');e.status=409;throw e;}return {contact:{id,version:9}}}");await nodes.get('#relationship-form').submit({preventDefault(){}});
 assert.equal(run('researchDrafts.size'),1);assert.equal(run('researchAttempts.size'),0);assert.equal(nodes.get('#relationship-form').dataset.dirty,'true');assert.equal(run('closeModal(false)'),false);
 await nodes.get('#research-refresh').onclick();assert(nodes.get('#relationship-error').textContent.includes('version 9'));
 // Reviewer regression: unknown saves keep Keep/Discard usable; committed recovery exits the frozen form.
 nodes.get('#relationship-form').dataset={};
 run("researchAttempts.clear();researchDrafts.clear();ctx=researchContext('contacts',id,()=>{});researchForm(ctx,'Synthetic recovery','','evidence',()=>researchWrite(ctx,'research/evidence',data));api=async()=>{throw Error('Lost response')}");
 const form=nodes.get('#relationship-form'), keepButton=nodes.get('#relationship-keep'), discardButton=nodes.get('#relationship-discard-confirm'), saveButton=node(), input=node();
 keepButton.id='relationship-keep';discardButton.id='relationship-discard-confirm';saveButton.id='save';input.id='field';
 const controls=[keepButton,discardButton,saveButton,input];form.querySelectorAll=()=>controls;
 await form.submit({preventDefault(){}});assert.equal(input.disabled,true);assert.equal(saveButton.disabled,true);assert.equal(keepButton.disabled,false);assert.equal(discardButton.disabled,false);assert.equal(run('closeModal(false)'),false);
 keepButton.onclick();assert.equal(nodes.get('#relationship-discard').hidden,true);run("researchDrafts.set('unrelated-draft',{addition:'Keep this draft'})");
 run("api=async(path,method='GET',body)=>path.startsWith('research/operations/')?{state:'committed',receipt:{...evidence,...data}}:originalApi(path,method,body)");await run('researchRecover()');assert.equal(run('researchAttempts.size'),0);assert.equal(form.dataset.dirty,undefined);assert.equal(run('researchDrafts.size'),1);assert(run("researchDrafts.has('unrelated-draft')"));assert.equal(keepButton.disabled,false);assert(nodes.get('#modal-body').innerHTML.includes('Note proposals'));
 // An unknown request can also be explicitly discarded/closed without losing its immutable attempt.
 form.dataset={};run("ctx=researchContext('contacts',id,()=>{});researchForm(ctx,'Synthetic recovery','','evidence',()=>researchWrite(ctx,'research/evidence',data));api=async()=>{throw Error('Lost response')}");await form.submit({preventDefault(){}});assert.equal(discardButton.disabled,false);discardButton.onclick();assert.equal(nodes.get('#modal').open,false);assert.equal(run('researchAttempts.size'),1);run('researchAttempts.clear()');form.dataset={};form.querySelectorAll=()=>[];
 // Reviewer regression: failed Next leaves the prior modal and working Previous handler intact.
 run("api=async(path,method='GET',body)=>{calls.push({path,method,body});if(path.startsWith('contacts/'))return {contact:{id,version:1,name:'Synthetic'}};if(path.includes('offset=30'))throw Error('Page failed');return {items:[],total:100,offset:Number(new URLSearchParams(path.split('?')[1]).get('offset')||0),limit:10}}");
 await run("openResearch('contacts',id,null,'evidence',20)");const previous=nodes.get('#research-prev').onclick;const pageHTML=nodes.get('#modal-body').innerHTML;await nodes.get('#research-next').onclick();assert.equal(nodes.get('#modal').open,true);assert.equal(nodes.get('#modal-body').innerHTML,pageHTML);await previous();assert(run("calls.at(-1).path.includes('offset=10')"));
 // Reviewer regression: malformed newly-created proposal identity stays unknown under its original key.
 run("ctx=researchContext('contacts',id,()=>{});api=async()=>({...proposal,id:''})");await assert.rejects(run("researchWrite(ctx,'research/proposals',{evidence_id:eid,evidence_digest:hash,evidence_lifecycle_version:1,target_version:1,addition:proposal.addition})"),/Unverified/);assert.equal(run('researchAttempts.size'),1);const malformedKey=run('researchAttempts.get(ctx.scope).key');await assert.rejects(run("researchWrite(ctx,'research/proposals',{})"),/earlier/);assert.equal(run('researchAttempts.get(ctx.scope).key'),malformedKey);
 console.log('PASS standalone Research: exact-target transport, manual evidence escaping, pagination, immutable unknown recovery/retry, conflicts/draft/dirty guard, duplicate writes, stale context and workspace ABA, exact append preview checks. Synthetic fixtures only.');
})().catch(e=>{console.error(e);process.exitCode=1});
