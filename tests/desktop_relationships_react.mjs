import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { webcrypto } from 'node:crypto';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-navigation-react'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer'), { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const context = vm.createContext({ URLSearchParams, crypto: webcrypto });
const module = new vm.SourceTextModule(await readFile(new URL('../desktop/relationships.js', import.meta.url), 'utf8'), { context });
await module.link(() => new vm.SyntheticModule(['createElement','useEffect','useRef','useState'], function() { for (const key of ['createElement','useEffect','useRef','useState']) this.setExport(key, React[key]); }, { context })); await module.evaluate();
const { relationshipSession, relationshipInstant, Relationships, ContactCompany, RelationshipForm } = module.namespace;
assert.equal(relationshipInstant('2026-10-01T12:30:59.123456-04:00'), '2026-10-01T12:30:59.123456-04:00');
assert.throws(() => relationshipInstant('2026-10-01T12:30'));
let calls = [], fail = true;
const client = { current: () => true, request: async (path, options) => { calls.push({path, options}); if (options && fail) throw new Error('offline'); return options ? {id:'company-one',version:1} : {items:[],total:0}; } };
let session = relationshipSession(client, 'captured-workspace');
await assert.rejects(session.write('/companies','POST',{data:{name:'Fixture'}}), /Outcome unknown/);
assert.equal(await session.write('/companies','POST',{data:{name:'Other'}}), null);
session.close(); session = relationshipSession(client, 'captured-workspace'); fail = false;
await session.retry(); assert.equal(calls[0].options.body.idempotency_key,calls[1].options.body.idempotency_key);
assert.deepEqual(calls[0].options.body,calls[1].options.body);
await session.read('/companies',{offset:25}); assert.match(calls.at(-1).path,/workspace_token=captured-workspace/);
let tree, writes = []; const event = {id:'event-one',version:3,title:'Fixture consultation',kind:'appointment',status:'scheduled',starts_at:'2026-10-01T12:30:59.123456Z',ends_at:'2026-10-01T13:30:59.123456Z',timezone:'UTC',notes:'Fixture note'};
const native = { current: () => true, request: async (path, options) => { if (options) { writes.push({path,...options}); return {...event,version:4}; } if (path.startsWith('/events/event-one?')) return event; return {items:[],total:0,limit:25,offset:0}; } };
const h = React.createElement;
await act(async () => { tree = Renderer.create(h(Relationships,{client:native,workspaceToken:'ws',page:'events',initial:{kind:'events',id:'event-one'},open:()=>{}})); });
const button = name => tree.root.findAllByType('button').find(n=>n.children.join('')===name);
await act(async () => button('Edit Event').props.onClick());
let inputs = tree.root.findAllByType('input'); assert.ok(inputs.some(n=>n.props.type==='datetime-local' && n.props.value==='2026-10-01T12:30:59'));
await act(async () => tree.root.findByType('form').props.onSubmit({preventDefault(){}}));
assert.equal(writes[0].body.data.starts_at,event.starts_at);assert.equal(writes[0].body.expected_version,3);
await act(async () => button('Create associated task').props.onClick());
assert.ok(tree.root.findAllByType('input').some(n=>n.props.required && n.props.type==='datetime-local'));
assert.ok(!tree.root.findAllByType('input').some(n=>n.props.value===event.title));
await act(async () => button('Cancel').props.onClick());
await act(async () => button('Needs rescheduling').props.onClick());
await act(async () => tree.root.findByType('textarea').props.onChange({target:{value:'Fixture reason'}}));
await act(async () => tree.root.findByType('form').props.onSubmit({preventDefault(){}}));
assert.equal(writes.at(-1).path,'/events/event-one/needs-rescheduling');assert.equal(writes.at(-1).body.reason,'Fixture reason');
await act(async()=>tree.unmount());
let contactWrites=[]; const cc={current:()=>true,request:async(path,options)=>{if(options){contactWrites.push(options.body);return {contact_id:'contact-one',contact_version:8,company_id:options.body.company_id};}if(path.includes('/contacts/'))return {contact_id:'contact-one',contact_version:7,company_id:'company-one',company_name:'Fixture organization',company_archived:false};return {items:[{id:'company-two',name:'Fixture organization',domain:'other.test'}],total:1};}};
await act(async()=>{tree=Renderer.create(h(ContactCompany,{client:cc,workspaceToken:'ws',contact:{id:'contact-one',version:6,company:'Old text'},open:()=>{}}));});
assert.match(JSON.stringify(tree.toJSON()),/unlinked/);
await act(async()=>button('Change Company link').props.onClick());await act(async()=>button('Clear selection').props.onClick());await act(async()=>button('Unlink Company').props.onClick());
assert.equal(contactWrites[0].company_id,null);assert.equal(contactWrites[0].expected_contact_version,7);assert.equal(contactWrites[0].workspace_token,'ws');
await act(async()=>tree.unmount());
console.log('Native relationship fixture tests passed: exact identity, paging transport, preserved instants, uncertain retry, status reason and atomic task form. These are fixture tests, not a physical Desktop run.');
// Reviewed unlink never invents an Event version and sends exact prior identities.
const unlinkCalls=[]; const unlinkClient={current:()=>true,request:async(path,options)=>{unlinkCalls.push({path,options});return options?{task:{id:'task-one',version:5},event:null,event_id:null,task_id:'task-one'}:{...event,version:11};}};
await act(async()=>{tree=Renderer.create(h(module.namespace.TaskEventRelationship,{client:unlinkClient,workspaceToken:'unlink-ws',task:{id:'task-one',version:5,event_id:'event-one',event_title:'Fixture event'},open:()=>{}}));});
assert.equal(unlinkCalls.length,0);await act(async()=>button('Review Event unlink').props.onClick());assert.equal(unlinkCalls.length,1);assert.match(JSON.stringify(tree.toJSON()),/Event version 11/);
await act(async()=>{const click=button('Unlink from reviewed Event').props.onClick;click();click();});
assert.equal(unlinkCalls.length,2);assert.deepEqual({...unlinkCalls[1].options.body},{event_id:'event-one',expected_version:11,expected_task_version:5,workspace_token:'unlink-ws',idempotency_key:unlinkCalls[1].options.body.idempotency_key});await act(async()=>tree.unmount());
// Unknown outcomes survive a new route client through the explicit scoped store.
const store=new Map();let original;
const old=relationshipSession({current:()=>true,request:async(path,options)=>{original=options.body;throw new Error('lost');}},'workspace',()=>true,store);
await assert.rejects(old.write('/events','POST',{data:{title:'Fixture'}}));old.close();
const fresh=relationshipSession({current:()=>true,request:async(path,options)=>{assert.deepEqual(options.body,original);return {id:'event-one',version:1};}},'workspace',()=>true,store);
await fresh.retry();assert.equal(store.size,0);
// Malformed receipts remain uncertain rather than silently clearing retry protection.
const malformed=relationshipSession({current:()=>true,request:async()=>({})},'malformed');await assert.rejects(malformed.write('/companies','POST',{data:{name:'Fixture'}}),/Outcome unknown/);assert.equal(malformed.pending().state,'unknown');
assert.throws(()=>relationshipInstant('2026-02-30T12:00:00Z'),/calendar/);
// Late detail requests cannot repopulate a dismissed panel.
let resolveLate;const lateClient={current:()=>true,request:()=>new Promise(resolve=>resolveLate=resolve)};
await act(async()=>{tree=Renderer.create(h(Relationships,{client:lateClient,workspaceToken:'late',page:'events',initial:{kind:'events',id:'event-one'},open:()=>{}}));});await act(async()=>tree.unmount());await act(async()=>resolveLate(event));
console.log('Reviewed unlink, duplicate-submit exclusion, retained retry across clients, malformed receipts, invalid calendar dates and late-unmount responses: passed.');
// New mounts observe an old in-flight receipt settling, without unrelated rerenders.
for (const outcome of ['success','unknown']) {
  const operations=new Map();let settle;
  const delayed={current:()=>true,request:async(path,options)=>options?new Promise((resolve,reject)=>{settle=()=>outcome==='success'?resolve({id:'company-one',version:1}):reject(new Error('lost response'));}):{items:[],total:0}};
  const origin=relationshipSession(delayed,'receipt-scope',()=>true,operations);
  const mutation=origin.write('/companies','POST',{data:{name:'Fixture'}}).catch(()=>null);origin.close();
  await act(async()=>{tree=Renderer.create(h(Relationships,{client:delayed,workspaceToken:'receipt-scope',operationStore:operations,page:'companies',open:()=>{}}));});
  assert.equal(button('Create Company').props.disabled,true);
  await act(async()=>{settle();await mutation;});
  if(outcome==='success')assert.equal(button('Create Company').props.disabled,false);
  else {assert.ok(button('Retry original request'));assert.equal(button('Retry original request').props.disabled,false);}
  await act(async()=>tree.unmount());
}
// Context is visible and independently clearable when creating an Event task.
const contextEvent={...event,status:'needs_rescheduling',contact_id:'contact-review',deal_id:'deal-review'};
let capturedTask;
await act(async()=>{tree=Renderer.create(h(RelationshipForm,{kind:'events',row:contextEvent,action:'task',session:relationshipSession(native,'review'),submit:data=>capturedTask=data,cancel:()=>{}}));});
assert.match(JSON.stringify(tree.toJSON()),/contact-review/);assert.match(JSON.stringify(tree.toJSON()),/deal-review/);assert.equal(tree.root.findAllByType('fieldset').length,2);
await act(async()=>{tree.root.findAllByType('button').filter(n=>n.children.join('')==='Clear selection')[0].props.onClick();});assert.ok(!JSON.stringify(tree.toJSON()).includes('Selected exact ID: contact-review'));
await act(async()=>tree.unmount());
// Both independently relevant Companies remain intelligible in task rollups.
const dual={id:'dual-task',title:'Fixture task',company_id:'company-a',company_name:'Company A',company_link_basis:'current_contact_relationships',event_id:'event-b',event_title:'Event B',event_company_id:'company-b',event_company_name:'Company B',event_link_basis:'explicit_event_tasks'};
await act(async()=>{tree=Renderer.create(h(module.namespace.RelationshipRows,{session:relationshipSession({current:()=>true,request:async()=>({items:[dual],total:1})},'dual'),path:'/companies/company-a/records/tasks',title:'Tasks',kind:'tasks',open:()=>{}}));});
const dualText=JSON.stringify(tree.toJSON());assert.match(dualText,/Current-contact Company: Company A · company-a/);assert.match(dualText,/Explicit Event Company: Company B · company-b/);await act(async()=>tree.unmount());
// Notes-only editing a needs-rescheduling Event must not trigger reschedule or send status.
const edits=[];const reschedulingClient={current:()=>true,request:async(path,options)=>{if(options){edits.push({path,...options});return {...contextEvent,version:4};}return path.startsWith('/events/event-one?')?contextEvent:{items:[],total:0};}};
await act(async()=>{tree=Renderer.create(h(Relationships,{client:reschedulingClient,workspaceToken:'notes',page:'events',initial:{kind:'events',id:'event-one'},open:()=>{}}));});await act(async()=>button('Edit Event').props.onClick());await act(async()=>tree.root.findByType('textarea').props.onChange({target:{value:'Updated notes only'}}));await act(async()=>tree.root.findByType('form').props.onSubmit({preventDefault(){}}));assert.equal(edits[0].method,'PATCH');assert.equal(edits[0].path,'/events/event-one');assert.equal(edits[0].body.data.notes,'Updated notes only');assert.ok(!Object.hasOwn(edits[0].body.data,'status'));await act(async()=>tree.unmount());
console.log('Observable in-flight remount success/unknown, reviewed task context, dual Company basis and needs-rescheduling notes-only PATCH: passed.');
// Every malformed/wrong-target receipt retains the original payload and key.
const receiptCases = [
  {path:'/companies',method:'POST',body:{data:{name:'Fixture'}},good:{id:'new-company',version:1},bad:[{}, {version:0}, {version:1}, {id:'',version:1}, {id:'new-company',version:0}]},
  {path:'/companies/company-a',method:'PATCH',body:{data:{name:'Fixture'},expected_version:3},good:{id:'company-a',version:4},bad:[{id:'company-b',version:4},{id:'company-a',version:0},{id:'company-a',version:2}]},
  {path:'/events/event-a/complete',method:'POST',body:{expected_version:2,data:{}},good:{id:'event-a',version:3},bad:[{version:3},{id:'event-b',version:3},{id:'event-a',version:0}]},
  {path:'/contacts/contact-a/company',method:'PUT',body:{company_id:'company-a',expected_contact_version:2},good:{contact_id:'contact-a',contact_version:3,company_id:'company-a'},bad:[{contact_id:'contact-b',contact_version:3,company_id:'company-a'},{contact_id:'contact-a',contact_version:3,company_id:'company-b'},{contact_id:'contact-a',contact_version:0,company_id:'company-a'},{contact_id:'contact-a',contact_version:3}]},
  {path:'/contacts/contact-a/company',method:'PUT',body:{company_id:null,expected_contact_version:2},good:{contact_id:'contact-a',contact_version:2,company_id:null},bad:[{contact_id:'contact-a',contact_version:3,company_id:'company-a'},{contact_id:'contact-a',contact_version:3}]},
  {path:'/events/event-a/tasks',method:'POST',body:{expected_version:2,data:{}},good:{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},bad:[{event:null,event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-b',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-a',version:3},event_id:'event-b',task:{id:'new-task',version:1},task_id:'new-task'},{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'new-task',version:1},task_id:'other-task'}]},
  {path:'/tasks/task-a/event',method:'PUT',body:{event_id:'event-a',expected_version:2,expected_task_version:4},good:{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'},bad:[{event:{id:'event-a',version:3},event_id:'event-a',task:{id:'task-b',version:5},task_id:'task-b'},{event:{id:'event-b',version:3},event_id:'event-b',task:{id:'task-a',version:5},task_id:'task-a'},{event:null,event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'},{event:{id:'event-a',version:0},event_id:'event-a',task:{id:'task-a',version:5},task_id:'task-a'}]},
  {path:'/tasks/task-a/event/unlink',method:'POST',body:{event_id:'event-a',expected_version:2,expected_task_version:4},good:{event:null,event_id:null,task:{id:'task-a',version:4},task_id:'task-a'},bad:[{event:null,event_id:null,task:{id:'task-a',version:5},task_id:'task-a'},{event:null,event_id:'event-a',task:{id:'task-a',version:4},task_id:'task-a'},{event:{id:'event-b',version:3},event_id:null,task:{id:'task-a',version:5},task_id:'task-a'},{event:null,event_id:null,task:{id:'task-b',version:5},task_id:'task-b'},{event:null,event_id:null,task:{id:'task-a',version:0},task_id:'task-a'},{event_id:null,task:{id:'task-a',version:4},task_id:'task-a'}]},
];
let checkedReceipts=0;
for(const scenario of receiptCases) for(const bad of scenario.bad) {
  const requests=[];let malformed=true;
  const scoped=relationshipSession({current:()=>true,request:async(path,options)=>{requests.push({path,body:options.body});return malformed?bad:scenario.good;}},'receipt-target');
  await assert.rejects(scoped.write(scenario.path,scenario.method,scenario.body),/Outcome unknown/);
  assert.equal(scoped.pending().state,'unknown');
  assert.equal(await scoped.write('/companies','POST',{data:{name:'Must remain blocked'}}),null);
  malformed=false;await scoped.retry();assert.equal(scoped.pending(),undefined);
  assert.equal(requests.length,2);assert.deepEqual(requests[0],requests[1]);checkedReceipts++;
}
assert.ok(module.namespace.confirmedRelationshipReceipt('/tasks/task-a/event/unlink','POST',{event_id:'event-a',expected_version:2,expected_task_version:4},{event:{id:'event-a',version:3},event_id:null,task:{id:'task-a',version:5},task_id:'task-a'}));
console.log(`Operation-specific receipt identities and positive versions: ${checkedReceipts} malformed cases retain original retry protection; valid unlink/no-op receipts accepted.`);
// Practical time inputs preserve exact originals, require fold choices and protect dirty cancellation.
let submitted=[],cancelled=0;
const formSession={read:async()=>({items:[],total:0})};
await act(async()=>{tree=Renderer.create(h(RelationshipForm,{kind:'events',row:{...event,starts_at:'2026-11-01T01:30:00.123456-04:00',ends_at:'2026-11-01T02:30:00.123456-05:00',timezone:'America/New_York'},session:formSession,submit:v=>submitted.push(v),cancel:()=>cancelled++,busy:false,pending:false}));});
const formSubmit=()=>tree.root.findByType('form').props.onSubmit({preventDefault(){}});
await act(async()=>formSubmit());
assert.equal(submitted.at(-1).starts_at,'2026-11-01T01:30:00.123456-04:00');
let wallInputs=tree.root.findAllByType('input').filter(n=>n.props.type==='datetime-local');
await act(async()=>wallInputs[0].props.onChange({target:{value:'2026-11-01T01:45'}}));
await act(async()=>formSubmit());assert.equal(submitted.length,1);assert.match(JSON.stringify(tree.toJSON()),/occurs twice/);
const foldSelect=tree.root.findAllByType('select').find(n=>n.children.some(c=>c.children?.includes('Choose occurrence')));
await act(async()=>foldSelect.props.onChange({target:{value:'2026-11-01T06:45:00.000Z'}}));
await act(async()=>formSubmit());assert.equal(submitted.at(-1).starts_at,'2026-11-01T06:45:00.000Z');
await act(async()=>button('Cancel').props.onClick());assert.equal(cancelled,0);assert.ok(button('Keep editing'));assert.ok(button('Discard changes'));
await act(async()=>button('Keep editing').props.onClick());assert.equal(cancelled,0);
await act(async()=>tree.root.findByType('form').props.onKeyDown({key:'Escape',preventDefault(){}}));
await act(async()=>button('Discard changes').props.onClick());assert.equal(cancelled,1);
await act(async()=>tree.unmount());
submitted=[];
await act(async()=>{tree=Renderer.create(h(RelationshipForm,{kind:'events',row:event,session:formSession,submit:v=>submitted.push(v),cancel:()=>{},busy:false,pending:false}));});
const zoneInput=tree.root.findAllByType('input').find(n=>n.props.placeholder==='America/New_York');
await act(async()=>zoneInput.props.onChange({target:{value:'Asia/Kathmandu'}}));await act(async()=>formSubmit());
assert.equal(submitted[0].timezone,'Asia/Kathmandu');assert.equal(submitted[0].starts_at,'2026-10-01T06:45:59.000Z');
await act(async()=>tree.unmount());
let editing=[];
await act(async()=>{tree=Renderer.create(h(Relationships,{client:native,workspaceToken:'draft-test',page:'events',open:()=>{},onEditingChange:v=>editing.push(v)}));});
await act(async()=>button('Create Event').props.onClick());assert.equal(editing.at(-1),true);
await act(async()=>button('Cancel').props.onClick());assert.equal(editing.at(-1),false);
await act(async()=>tree.unmount());assert.equal(editing.at(-1),false);
console.log('Practical native datetime controls: exact unchanged fold, required changed fold choice, changed zone, dirty Cancel/Escape keep/discard and parent editor lock passed.');
for (const year of ['0099','1899','2101','9998']) {
 submitted=[];
 const old={...event,starts_at:`${year}-01-01T12:00:00.123456Z`,ends_at:`${year}-01-01T13:00:00.123456Z`};
 await act(async()=>{tree=Renderer.create(h(RelationshipForm,{kind:'events',row:old,session:formSession,submit:v=>submitted.push(v),cancel:()=>{},busy:false,pending:false}));});
 const fields=tree.root.findAllByType('input').filter(n=>n.props.type==='datetime-local');
 // Browser range validation must not preempt the unchanged-original preservation path.
 for(const field of fields){assert.equal(field.props.min,undefined);assert.equal(field.props.max,undefined);assert.equal(field.props.step,1);}
 assert(!JSON.stringify(tree.toJSON()).includes('Choose a year from 1900 through 2100.'));
 await act(async()=>formSubmit());assert.equal(submitted.at(-1).starts_at,old.starts_at);
 await act(async()=>fields[0].props.onChange({target:{value:`${year}-01-01T12:01`}}));
 await act(async()=>formSubmit());assert.equal(submitted.length,1);assert.match(JSON.stringify(tree.toJSON()),/Choose a year from 1900 through 2100/);
 await act(async()=>tree.unmount());
}
console.log('Unchanged out-of-range originals: browser range attributes absent, readable preview, exact submit retained and changed wall time rejected.');
