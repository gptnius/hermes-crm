// Dependency-free contract/lifecycle tests. Fixtures are synthetic, not browser rendering.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const nodes=new Map(),handlers={},requests=[];
function node(){return {innerHTML:'',textContent:'',dataset:{},open:false,hidden:false,classList:{toggle(){}},setAttribute(){},removeAttribute(){},addEventListener(k,v){this[k]=v;},querySelector(){return node();},querySelectorAll(){return [];},focus(){},close(){this.open=false;},showModal(){this.open=true;}};}
let response={id:'saved',version:2},failure=null,waiting=null;
const context={console,crypto,URLSearchParams,Intl,Date,setTimeout,clearTimeout,location:{hash:'#overview'},window:{addEventListener(){}},document:{querySelector(s){if(!nodes.has(s))nodes.set(s,node());return nodes.get(s);},querySelectorAll(){return [];},addEventListener(k,v){handlers[k]=v;},contains(){return true;}},fetch:async(url,options)=>{requests.push({url,options});if(waiting)await waiting;if(failure)throw failure;return {ok:true,status:200,json:async()=>response};}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8').replace(/initialize\(\);\s*$/,''),context);
const run=s=>vm.runInContext(s,context);
(async()=>{
 run("relationshipWorkspace='workspace-a'");
 assert.equal(run("relationshipPath('events',{offset:25})"),'events?offset=25&workspace_token=workspace-a');
 const exact='2026-11-12T10:00:00.123456-05:00';
 context.exact=exact;
 assert.equal(run("eventPayload({starts_at:exact,ends_at:'2026-11-12T11:00:00.123456-05:00',timezone:'America/New_York'}).starts_at"),exact);
 assert.throws(()=>run("eventPayload({starts_at:'2026-11-12T10:00',ends_at:'2026-11-12T11:00',timezone:'Etc/UTC'})"),/explicit offset/);
 assert.throws(()=>run("eventPayload({starts_at:exact,ends_at:exact,timezone:'Etc/UTC'})"),/End must follow/);
 assert.equal(run("eventPayload({starts_at:exact,ends_at:'2026-11-12T15:00:00.123457Z',timezone:'Etc/UTC'}).starts_at"),exact);
 assert.throws(()=>run("eventPayload({starts_at:exact,ends_at:'2026-11-12T15:00:00.123455Z',timezone:'Etc/UTC'})"),/End must follow/);
 assert.throws(()=>run("eventPayload({starts_at:exact,ends_at:'2026-11-12T15:00:00.123456Z',timezone:'Etc/UTC'})"),/End must follow/);
 assert.throws(()=>run("eventPayload({starts_at:exact,ends_at:'2026-11-12T17:00:00Z',timezone:'Invalid/Zone'})"),/IANA/);
 const dual=run("taskRelationshipContext({company_id:'company-a',company_name:'A <current>',company_link_basis:'current_contact_relationships',event_id:'event-b',event_company_id:'company-b',event_company_name:'B <explicit>',event_link_basis:'explicit_event_tasks'})");
 assert(dual.includes('Current-contact Company:') && dual.includes('Explicit Event Company:'));
 assert(dual.includes('data-id="company-a"') && dual.includes('data-id="company-b"') && dual.includes('A &lt;current&gt;') && dual.includes('B &lt;explicit&gt;'));
 assert(dual.includes('current_contact_relationships') && dual.includes('explicit_event_tasks'));
 run("eventTaskForm({id:'event',version:1,contact_id:'review-contact',deal_id:'review-deal'})");
 const taskForm=nodes.get('#modal-body').innerHTML;
 assert(taskForm.includes('name="contact_id" value="review-contact"') && taskForm.includes('name="deal_id" value="review-deal"'));
 assert(taskForm.includes('Clear either ID for no direct context'));
 run('closeModal()');
 const links=run("eventRelatedLinks({contact_id:'contact-a',deal_id:'deal-a',company_id:'company-a'})");
 assert(links.includes('class="event-related-links"') && links.includes('aria-label="Related Event records"'));
 assert.equal((links.match(/class="name-button"/g)||[]).length,3);
 for(const id of ['contact-a','deal-a','company-a']) assert(links.includes(`data-id="${id}"`));
 const css=fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.css'),'utf8');
 assert(/\.event-related-links \{[^}]*display:flex;[^}]*flex-wrap:wrap;[^}]*gap:8px 16px;/.test(css));
 assert(/\.event-related-links > \.name-button \{[^}]*min-height:44px;[^}]*min-width:44px;/.test(css));
 const appSource=fs.readFileSync(require('node:path').join(__dirname,'../hermes_crm/static/app.js'),'utf8');
 assert.equal((appSource.match(/filterInput\("company","Legacy company text"\)/g)||[]).length,2);
 assert(run('filterInput("company","Legacy company text")').includes('data-filter="company"'));
 const html=run("relationshipRows({items:[{id:'one',name:'<Same>',domain:'first.test'},{id:'two',name:'<Same>',domain:'second.test'}]},'companies')");
 assert(html.includes('&lt;Same&gt;')&&html.includes('data-id="one"')&&html.includes('data-id="two"')&&html.includes('first.test'));
 assert(!run("exactSelector('company_id','companies')").includes('selected'));
 assert(run("eventFields({starts_at:exact})").includes(exact));
 run("var originalRelationshipForm=relationshipForm; var capturedSubmit; relationshipForm=(title,fields,submit)=>{capturedSubmit=submit;}; relationshipEditor('events',{id:'needs',version:4,status:'needs_rescheduling',title:'Existing',kind:'call',starts_at:exact,ends_at:'2026-11-12T17:00:00Z',timezone:'Etc/UTC',notes:'Before'}); relationshipForm=originalRelationshipForm;");
 response={id:'needs',version:5};
 await run("capturedSubmit({title:'Existing',kind:'call',starts_at:exact,ends_at:'2026-11-12T17:00:00Z',timezone:'Etc/UTC',notes:'After'})");
 const editRequest=requests.at(-1);
 assert.equal(editRequest.options.method,'PATCH');
 assert.equal(editRequest.url,'/api/events/needs');
 assert.equal(JSON.parse(editRequest.options.body).expected_version,4);
 assert.equal(JSON.parse(editRequest.options.body).data.notes,'After');
 assert(!Object.hasOwn(JSON.parse(editRequest.options.body).data,'status'),'notes edit must not reset needs_rescheduling');
 failure=new Error('network unavailable');
 await assert.rejects(run("relationshipWrite('companies','POST',{data:{name:'A'}})"),/Outcome unknown/);
 const first=JSON.parse(requests.at(-1).options.body);
 run('closeModal()');
 await assert.rejects(run("relationshipWrite('companies','POST',{data:{name:'B'}})"),/earlier write/);
 failure=null;
 await run("relationshipWrite('companies','POST',{data:{name:'A'}})");
 assert.equal(JSON.parse(requests.at(-1).options.body).idempotency_key,first.idempotency_key);
 assert.equal(run('relationshipAttempts.size'),0);
 for (const [path,bad] of [['events',{id:'event'}],['companies',{id:'company',version:0}],['contacts/contact/company',{contact_id:'contact'}],['events/event/tasks',{task_id:'task',task:{id:'task'}}],['tasks/task/event',{task_id:'task',task:{id:'other',version:2}}]]) {
   response=bad; context.receiptPath=path;
   await assert.rejects(run("relationshipWrite(receiptPath,'POST',{data:{title:'A'}})"),/Unconfirmed/);
   assert.equal(run('relationshipAttempts.size'),1);
   run('relationshipAttempts.clear()');
 }
 const receiptCases = [
  {path:'/companies',method:'POST',body:{data:{name:'Fixture'}},good:{id:'new-company',version:1},bad:[{}, {version:0}, {version:1}, {id:'',version:1}, {id:'new-company',version:0}]},
  {path:'/companies/company-a',method:'PATCH',body:{data:{name:'Fixture'},expected_version:3},good:{id:'company-a',version:4},bad:[{id:'company-b',version:4},{id:'company-a',version:0},{id:'company-a',version:2}]},
  {path:'/events/event-a/complete',method:'POST',body:{expected_version:2,data:{}},good:{id:'event-a',version:3},bad:[{version:3},{id:'event-b',version:3},{id:'event-a',version:0}]},
  {path:'/contacts/contact-a/company',method:'PUT',body:{company_id:'company-a',expected_contact_version:2},good:{contact_id:'contact-a',contact_version:3,company_id:'company-a'},bad:[{contact_id:'contact-b',contact_version:3,company_id:'company-a'},{contact_id:'contact-a',contact_version:3,company_id:'company-b'},{contact_id:'contact-a',contact_version:0,company_id:'company-a'},{contact_id:'contact-a',contact_version:3}]},
  {path:'/contacts/contact-a/company',method:'PUT',body:{company_id:null,expected_contact_version:2},good:{contact_id:'contact-a',contact_version:2,company_id:null},bad:[{contact_id:'contact-a',contact_version:3,company_id:'company-a'},{contact_id:'contact-a',contact_version:3}]},
  {path:'/events/event-a/tasks',method:'POST',body:{expected_version:2,data:{}},good:{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},bad:[{event:null,event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-b',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-a',version:3},event_id:'event-b',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'other-task'}]},
  {path:'/tasks/task-a/event',method:'PUT',body:{event_id:'event-a',expected_version:2,expected_task_version:4},good:{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'},bad:[{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'task-b',version:5},task_id:'task-b'},{event:{id:'event-b',version:3},event_id:'event-b',task:{id:'task-a',version:5},task_id:'task-a'},{event:null,event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'},{event:{id:'event-a',version:0},event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'}]},
  {path:'/tasks/task-a/event/unlink',method:'POST',body:{event_id:'event-a',expected_version:2,expected_task_version:4},good:{event:null,event_id:null,task:{id:'task-a',version:4},task_id:'task-a'},bad:[{event:null,event_id:'event-a',task:{id:'task-a',version:4},task_id:'task-a'},{event:{id:'event-b',version:3},event_id:null,task:{id:'task-a',version:5},task_id:'task-a'},{event:null,event_id:null,task:{id:'task-b',version:5},task_id:'task-b'},{event:null,event_id:null,task:{id:'task-a',version:0},task_id:'task-a'},{event_id:null,task:{id:'task-a',version:4},task_id:'task-a'}]},
];
 let checkedReceipts=0;
 for (const scenario of receiptCases) for (const bad of scenario.bad) {
   context.scenario={...scenario,path:scenario.path.slice(1)}; response=bad;
   const before=requests.length;
   await assert.rejects(run("relationshipWrite(scenario.path,scenario.method,scenario.body)"),/Unconfirmed/);
   assert.equal(run('relationshipAttempts.size'),1);
   await assert.rejects(run("relationshipWrite('companies','POST',{data:{name:'Blocked'}})"),/earlier write/);
   assert.equal(requests.length,before+1,'wrong-target receipt must block changed intent');
   response=scenario.good;
   await run("relationshipWrite(scenario.path,scenario.method,scenario.body)");
   assert.equal(run('relationshipAttempts.size'),0);
   assert.deepEqual(requests[before],requests[before+1],'retry must retain original path/method/payload/key');
   checkedReceipts++;
 }
 assert.equal(checkedReceipts,30);
 assert.equal(run("confirmedRelationshipReceipt('tasks/task-a/event/unlink','POST',{event_id:'event-a',expected_version:2,expected_task_version:4},{event:{id:'event-a',version:3},event_id:null,task:{id:'task-a',version:5},task_id:'task-a'})"),true);
 assert.equal(run("confirmedRelationshipReceipt('tasks/task-a/event/unlink','POST',{event_id:'event-a',expected_version:2,expected_task_version:4},{event:null,event_id:null,task:{id:'task-a',version:5},task_id:'task-a'})"),false,'null Event only confirms unchanged task/no-op');
 for (const [path,method] of [['companies','PATCH'],['events/e','POST'],['companies/c/unsupported','POST'],['contacts/contact-a/company','POST'],['tasks/task-a/event','POST']]) {
   context.invalidPath=path;context.invalidMethod=method;
   assert.equal(run("confirmedRelationshipReceipt(invalidPath,invalidMethod,{}, {id:'c',version:1})"),false);
 }
 console.log('PASS: 30 operation-specific wrong-target/malformed receipts retain identical retries; exact unlink/no-op semantics and unsupported methods rejected.');
 response={};
 await assert.rejects(run("relationshipWrite('events','POST',{data:{title:'A'}})"),/Unconfirmed/);
 assert.equal(run('relationshipAttempts.size'),1);
 run('relationshipAttempts.clear()');
 response={company:{id:'co',version:1,name:'Company'},counts:{contacts:0,deals:0,tasks:0,events:0}};
 let resolve;waiting=new Promise(r=>resolve=r);
 const detail=run("relationshipDetail('companies','co')");run('closeModal()');resolve();waiting=null;await detail;
 assert.equal(nodes.get('#modal').open,false,'dismissed detail must not reopen');
 console.log('PASS: standalone exact IDs, escaping, explicit offsets/microseconds/IANA validation, workspace-scoped reads, unknown receipt lock, identical retry key across dismissal, stale detail dismissal. Fixture logic only; no layout claim.');
})().catch(e=>{console.error(e);process.exitCode=1;});
