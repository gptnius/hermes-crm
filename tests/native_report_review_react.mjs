import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
const require=createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT||'/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'),Renderer=require('react-test-renderer'),{act}=React,h=React.createElement;
assert.equal(React.version,'19.3.0');globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const context=vm.createContext({crypto:webcrypto,console});
const module=new vm.SourceTextModule(await readFile(new URL('../desktop/report-review.js',import.meta.url),'utf8'),{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const k of ['createElement','useEffect','useRef','useState'])this.setExport(k,React[k]);},{context}));await module.evaluate();
const {ReportReviewPanel,reportReviewMemory,reportReviewPreview,reportReviewReceipt}=module.namespace;
const clone=x=>JSON.parse(JSON.stringify(x)), id=n=>`10000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
function fixture(family='native',stale=false) {
 const assignment=id(1),report=family==='native'?id(2):'run:'+'a'.repeat(64);
 const binding={family,assignment_id:assignment,report_id:report,assignment_digest:'b'.repeat(64),generation:1,report_digest:'c'.repeat(64),identity:{job_id:'job',job_name:`CRM ${family==='native'?'work':'research'} ${assignment} g1`,execution_id:'execution',source:'builtin',scheduled_instant:'2030-01-01T00:00:00Z',started_at:null,profile:'alpha'},summary:'Exact immutable result',outcome:'completed',task_id:id(3),task_version:2,target:family==='native'?null:{target_kind:'contacts',target_id:id(4),target_version:3}};
 const context={report:clone(binding),assignment_version:4,assignment_state:'result_reported',task:{id:id(3),assigned_version:2,current_version:stale?3:2,current_status:'open'},target:binding.target?{kind:'contacts',id:id(4),assigned_version:3,current_version:3,archived:false}:null,source_current:!stale,source_reason:stale?'source_task_changed_or_closed':null};
 return {...binding,context,context_digest:'d'.repeat(64),review:{status:'awaiting_review',version:0,latest_event:null,history:[],history_total:0,history_truncated:false}};
}
let tree,props,state,strict;
const text=()=>JSON.stringify(tree.toJSON());
const buttons=label=>tree.root.findAllByType('button').filter(b=>b.children.join('')===label);
const button=label=>{assert.ok(buttons(label).length,label+' absent: '+text());return buttons(label)[0];};
const click=async label=>{const b=button(label);assert.equal(b.props.disabled,false,label+' disabled');await act(async()=>b.props.onClick());};
const unmount=async()=>act(async()=>tree.unmount());
function receipt(path,body) {
 const event={id:id(20+body.expected_review_version),family:state.value.family,assignment_id:state.value.assignment_id,report_id:state.value.report_id,version:body.expected_review_version+1,action:path.endsWith('/revoke')?'revoke':'acknowledge',context:clone(state.value.context),context_digest:body.context_digest,actor:'desktop',created_at:'2030-01-02T00:00:00Z'};
 const result={event,review:{status:event.action==='acknowledge'?'reviewed_in_crm':'awaiting_review',version:event.version}};
 state.value.review={...clone(result.review),latest_event:clone(event),history:[...state.value.review.history,clone(event)],history_total:event.version,history_truncated:false};
 return result;
}
async function mount({family='native',stale=false,strictMode=false,reset=true,pairs=false}={}) {
 strict=strictMode;
 if(reset){state={value:fixture(family,stale),alive:true,current:true,posts:[],reads:[],failRead:false,failWrite:false,delay:false,malformed:false,receipts:new Map(),changed:0,focus:[]};
 const {context,context_digest,review,...expected}=clone(state.value);
 props={workspaceToken:'ws',profile:'alpha',expected,task:{id:id(3),version:stale?3:2,status:'open'},memory:reportReviewMemory({},family),current:()=>state.current,onChanged:()=>state.changed++,client:{current:()=>state.alive,request:async(path,options)=>{
 if(!options){state.reads.push(path);if(state.failRead)throw Error('read failed');const value=clone(state.value);if(state.delayRead)await new Promise(r=>state.resolveRead=r);return value;}
 state.posts.push({path,body:clone(options.body)});
 if(state.delay)await new Promise(r=>state.resolve=r);
 if(state.failWrite)throw Error('unknown');
 let result=state.receipts.get(options.body.idempotency_key);
 if(!result){result=receipt(path,options.body);state.receipts.set(options.body.idempotency_key,clone(result));}
 return state.malformed?{...result,event:{...result.event,actor:'owner'}}:clone(result);
 }}};}
 await act(async()=>{const child=pairs?h('div',null,h(ReportReviewPanel,props),h(ReportReviewPanel,props)):h(ReportReviewPanel,props);tree=Renderer.create(strict?h(React.StrictMode,null,child):child,{createNodeMock:e=>({focus:()=>state.focus.push(e.type),isConnected:true})});});
}
for(const strictMode of [false,true])for(const family of ['native','scheduled_research']) {
 await mount({strictMode,family});assert.match(text(),/Not reviewed in CRM/);assert.equal(state.posts.length,0);
 assert.ok(state.reads[0].includes(encodeURIComponent(props.expected.report_id)));
 await click('Mark result reviewed');assert.match(text(),/Exact immutable result/);assert.match(text(),/Agent reported: completed/);assert.equal(state.posts.length,0);await click('Cancel acknowledgement');assert.equal(state.focus.at(-1),'button');
 await click('Mark result reviewed');await click('Confirm mark reviewed');assert.equal(state.posts.length,1);assert.match(text(),/Reviewed in CRM/);assert.equal(state.changed,1);assert.deepEqual(Object.keys(state.posts[0].body).sort(),['acknowledge_stale','context_digest','expected_review_version','idempotency_key','workspace_token']);
 await click('Undo acknowledgement');await click('Confirm undo acknowledgement');assert.match(text(),/Not reviewed in CRM/);assert.equal(state.posts.length,2);assert.equal(state.value.review.version,2);await unmount();
}
// Historical source requires an explicit checkbox, for acknowledgement and undo.
for(const family of ['native','scheduled_research']) {await mount({family,stale:true});await click('Mark result reviewed');assert.match(text(),/historical result is not current/);assert.equal(button('Confirm mark reviewed').props.disabled,true);await act(async()=>tree.root.findByProps({'aria-label':'Acknowledge changed source'}).props.onChange({target:{checked:true}}));await click('Confirm mark reviewed');assert.equal(state.posts[0].body.acknowledge_stale,true);assert.equal(state.changed,1);await click('Undo acknowledgement');assert.equal(button('Confirm undo acknowledgement').props.disabled,true);await unmount();}
// Unknown attempts survive remount and only exact same key/body/endpoint is replayed.
await mount();await click('Mark result reviewed');state.failWrite=true;await click('Confirm mark reviewed');const attempted=clone(state.posts[0]);assert.match(text(),/unconfirmed/);assert.equal(buttons('Mark result reviewed').length,0);await unmount();state.failWrite=false;await mount({reset:false});await click('Retry exact acknowledgement');assert.deepEqual(state.posts[1],attempted);assert.match(text(),/Reviewed in CRM/);await unmount();
// A delayed receipt survives remount, wakes the new panel, and reads current status.
await mount();await click('Mark result reviewed');state.delay=true;await act(async()=>{void button('Confirm mark reviewed').props.onClick();});await unmount();await mount({reset:false});assert.match(text(),/Saving acknowledgement/);await act(async()=>state.resolve());assert.equal(props.memory.attempt,null);assert.match(text(),/Reviewed in CRM/);assert.equal(state.changed,1);await unmount();
// Two simultaneous panels share the write lock, including retained same-tick callbacks.
await mount({pairs:true});await act(async()=>Promise.all(buttons('Mark result reviewed').map(b=>b.props.onClick())));const confirms=buttons('Confirm mark reviewed').map(b=>b.props.onClick);state.delay=true;await act(async()=>{for(const confirm of confirms)void confirm();});assert.equal(state.posts.length,1);await act(async()=>state.resolve());assert.equal(buttons('Undo acknowledgement').length,2);await unmount();
// A historical exact receipt after another actor revoked never restores reviewed status.
await mount();await click('Mark result reviewed');state.malformed=true;await click('Confirm mark reviewed');const oldAttempt=props.memory.attempt;assert.ok(oldAttempt);receipt('/revoke',{expected_review_version:1,context_digest:state.value.context_digest});state.malformed=false;await click('Retry exact acknowledgement');assert.match(text(),/Not reviewed in CRM/);assert.equal(state.value.review.version,2);assert.equal(props.memory.receipt.review.version,1);assert.equal(reportReviewReceipt(props.memory.receipt,oldAttempt),true);await unmount();
// Failed fresh status fetch never substitutes the POST projection.
await mount();await click('Mark result reviewed');state.failRead=true;await click('Confirm mark reviewed');assert.match(text(),/Review status unavailable/);assert.equal(button('Mark result reviewed').props.disabled,true);assert.equal(buttons('Undo acknowledgement').length,0);await unmount();
// Captured actions fail closed after task/profile/workspace/client change and unmount.
for(const patch of [{profile:'beta'},{workspaceToken:'other'},{task:{id:id(5),version:2,status:'open'}},{task:{id:id(3),version:3,status:'open'}}]) {
 await mount();await click('Mark result reviewed');const confirm=button('Confirm mark reviewed').props.onClick;await act(async()=>tree.update(h(ReportReviewPanel,{...props,...patch})));await act(async()=>confirm());assert.equal(state.posts.length,0);await unmount();await confirm();assert.equal(state.posts.length,0);
}
await mount();await click('Mark result reviewed');const off=button('Confirm mark reviewed').props.onClick;state.alive=false;await act(async()=>off());assert.equal(state.posts.length,0);await unmount();
// Cancelled and Escape-dismissed confirmation cannot be resurrected by a saved callback.
await mount();await click('Mark result reviewed');const cancelled=button('Confirm mark reviewed').props.onClick;await click('Cancel acknowledgement');await act(async()=>cancelled());assert.equal(state.posts.length,0);await unmount();
// Deep malformed previews fail closed (not empty/unreviewed success).
const original=fixture();const expected=clone(original.context.report);
assert.equal(reportReviewPreview(original,expected),true);
for(const mutate of [v=>v.identity.profile='wrong',v=>v.context.report.summary='altered',v=>v.context.task.id=id(9),v=>v.context.source_current=false,v=>v.review.history_total=1,v=>v.review.history=[{}],v=>v.review.status='reviewed_in_crm',v=>v.report_id='run:unsafe/segment',v=>v.outcome='accepted',v=>v.target={}]){const value=clone(original);mutate(value);assert.equal(reportReviewPreview(value,expected),false);}
await mount();state.value.context.task.id=id(9);await click('Refresh review status');assert.match(text(),/Review status unavailable/);assert.equal(button('Mark result reviewed').props.disabled,true);await unmount();
console.log('Report acknowledgement React 19.3 tests passed (normal and StrictMode, both families)');

// Captured actual SQLite store/API shapes, including native, Contact and Company research.
const backendFixtures=JSON.parse(await readFile(new URL('./fixtures/report_review_backend.json',import.meta.url),'utf8'));
for(const [name,fixture] of Object.entries(backendFixtures)) {
 const expected=fixture.preview.context.report;
 assert.equal(reportReviewPreview(fixture.preview,expected),true,name+' initial backend preview');
 assert.equal(reportReviewPreview(fixture.reviewed,expected),true,name+' backend history');
 assert.equal(reportReviewReceipt(fixture.receipt,{preview:fixture.preview,action:'acknowledge',body:{expected_review_version:0,context_digest:fixture.preview.context_digest}}),true,name+' backend receipt');
 await mount();state.value=clone(fixture.reviewed);
 props={...props,expected:clone(expected),profile:expected.identity.profile,task:{id:expected.task_id,version:fixture.reviewed.context.task.current_version,status:fixture.reviewed.context.task.current_status}};
 await act(async()=>tree.update(h(ReportReviewPanel,props)));assert.match(text(),/Reviewed in CRM/);await click('Undo acknowledgement');assert.match(text(),new RegExp(expected.summary));await unmount();
}
console.log('PASS actual backend native, Contact research and Company research preview/receipt/history contracts.');

// An in-flight preview cannot land after the task scope changes.
await mount();state.delayRead=true;await act(async()=>{void button('Mark result reviewed').props.onClick();});const resolveOld=state.resolveRead;state.delayRead=false;
await act(async()=>tree.update(h(ReportReviewPanel,{...props,task:{...props.task,version:4}})));await act(async()=>resolveOld());assert.equal(buttons('Confirm mark reviewed').length,0);assert.equal(state.posts.length,0);await unmount();
// Escape and an old checkbox callback cannot grant consent to a newer preview.
await mount({stale:true});await click('Mark result reviewed');const oldCheckbox=tree.root.findByProps({'aria-label':'Acknowledge changed source'}).props.onChange;
await act(async()=>tree.root.findByProps({'aria-label':'Result acknowledgement'}).props.onKeyDown({key:'Escape',preventDefault(){}}));assert.equal(buttons('Confirm mark reviewed').length,0);await click('Mark result reviewed');await act(async()=>oldCheckbox({target:{checked:true}}));assert.equal(button('Confirm mark reviewed').props.disabled,true);await unmount();
console.log('PASS interrupted preview and stale checkbox/keyboard cancellation guards.');
// Fresh source changes stay visible after acknowledgement, independently of immutable report state.
for(const strictMode of [false,true])for(const family of ['native','scheduled_research']) {
 await mount({strictMode,family});await click('Mark result reviewed');await click('Confirm mark reviewed');
 state.value.context.task.current_version++;state.value.context.source_current=false;state.value.context.source_reason='source_task_changed_or_closed';await click('Refresh review status');
 assert.match(text(),/Reviewed in CRM/);assert.match(text(),/This historical result is not current; acknowledgement does not restore source freshness/);assert.equal(buttons('Confirm mark reviewed').length,0);
 await click('Undo acknowledgement');await act(async()=>tree.root.findByProps({'aria-label':'Acknowledge changed source'}).props.onChange({target:{checked:true}}));await click('Confirm undo acknowledgement');assert.equal(state.changed,2);assert.match(text(),/Not reviewed in CRM/);assert.match(text(),/historical result is not current/);await unmount();
}
for(const missing of [false,true]) {
 const value=fixture('scheduled_research');value.context.target.archived=true;
 if(missing)value.context.target.current_version=null;
 value.context.source_current=false;value.context.source_reason=missing?'source_record_missing':'research_target_changed_or_archived';
 assert.equal(reportReviewPreview(value,value.context.report),false);
}
console.log('PASS fresh-source warnings, stale undo refresh in normal/StrictMode, and impossible archived target rejection.');
