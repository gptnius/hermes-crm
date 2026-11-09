// Local synthetic clients only. No provider, host application or credential access.
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
const require=createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT||'/tmp/hermes-crm-desktop-test'}/package.json`);
const React=require('react'),Renderer=require('react-test-renderer'),{act}=React,h=React.createElement;
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const source=await readFile(new URL('../desktop/email-bridge.js',import.meta.url),'utf8');
assert.match(source,/\.hc-bridge-consent\{display:flex;flex-direction:row;gap:8px;align-items:flex-start\}/,'consent checkbox must stay beside text despite global label column layout');
const context=vm.createContext({crypto:webcrypto,URLSearchParams,console});
const module=new vm.SourceTextModule(source,{context});
await module.link(()=>new vm.SyntheticModule(['createElement','useEffect','useRef','useState'],function(){for(const k of ['createElement','useEffect','useRef','useState'])this.setExport(k,React[k]);},{context}));await module.evaluate();
const {createBridgeSession,emailBridgeMemory,EmailBridgePanel,EmailBridgePolling,CompanyEmailBridgePanel}=module.namespace;
const clone=x=>JSON.parse(JSON.stringify(x));
assert.doesNotMatch(source,/dangerouslySetInnerHTML|\bfetch\s*\(|localStorage|window\.|child_process|\.send\(|\.draft\(/);
const base=()=>({revision:0,enabled:false,polling_enabled:false,mailbox:null,account_namespace:null,checkpoint:null,lease_state:null,runtime:{available:false}});
function fixture(){
 const state={status:base(),posts:[],gets:[],receipts:new Map(),current:true,history:{items:[],total:0,explicit_aliases:[],contact_version:2},unresolved:{items:[],total:0},focus:[],timers:[]};
 const memory=emailBridgeMemory({});
 const client={current:()=>state.current,async request(path,options){
  if(!options){state.gets.push(path);if(path.includes('/operations/'))return clone(state.receipts.get(path.split('/operations/')[1].split('?')[0])||null);if(path.includes('/contacts/'))return clone(state.history);if(path.includes('/unresolved'))return clone(state.unresolved);return clone(state.status);}
  state.posts.push({path,body:clone(options.body)});if(state.delay)await new Promise(resolve=>state.resolve=resolve);if(state.fail)throw Error('synthetic network failure');
  const body=options.body;let result;state.status.revision++;
  if(path.endsWith('/verify')){Object.assign(state.status,{mailbox:body.own_mailbox,account_namespace:'account',own_aliases:body.own_aliases,enabled:true,checkpoint:'123'});result={revision:state.status.revision,account_namespace:'account'};}
  else if(path.endsWith('/sync'))result={outcome:{status:state.outcome||'complete',coverage:'incremental',revision:state.status.revision}};
  else if(path.endsWith('/control')){if(body.action==='start_polling')state.status.polling_enabled=true;if(body.action==='stop_polling')state.status.polling_enabled=false;result={revision:state.status.revision,enabled:state.status.enabled};}
  else {state.history.explicit_aliases=body.aliases;result={revision:state.status.revision};}
  state.receipts.set(body.operation_key,result);return clone(result);
 }};
 const ctx={setInterval(fn,delay){const timer={fn,delay,stopped:false};state.timers.push(timer);return()=>{timer.stopped=true;};}};
 return {state,client,memory,ctx};
}
// Scope retention, unknown outcomes, identical request retention and concurrent submissions.
{
 const {state,client,memory}=fixture();const args={client,memory,workspaceToken:'workspace'};
 let s=createBridgeSession(args);await s.status();assert.equal(state.posts.length,0);
 state.fail=true;await assert.rejects(s.submit('verify',state.status,{own_mailbox:'me@example.test',own_aliases:[]}),/Outcome unknown/);
 const pending=s.pending(),body=JSON.stringify(pending.body);assert.equal(pending.state,'unknown');s.close();s=createBridgeSession(args);
 await s.submit('verify',state.status,{own_mailbox:'other@example.test'});assert.equal(state.posts.length,1);await s.status();assert.equal(JSON.stringify(s.pending().body),body);
 state.receipts.set(pending.body.operation_key,{revision:1,account_namespace:'account'});await s.status();assert.equal(s.pending(),undefined);
 state.fail=false;state.delay=true;const promise=s.submit('sync',state.status,{mode:'7days',trigger:'manual'});await s.submit('sync',state.status,{mode:'30days'});assert.equal(state.posts.length,2);
 state.current=false;state.current=true;s.close();state.resolve();assert.equal(await promise,null);assert.ok(s.pending(),'discarded route response retains receipt lock');
}
// A local disconnect can fence an unknown provider attempt using a fresh local revision.
{
 const {state,client,memory}=fixture();const s=createBridgeSession({client,memory,workspaceToken:'ws'});
 state.fail=true;await assert.rejects(s.submit('verify',state.status,{own_mailbox:'me@example.test'}));
 const original=s.pending(),originalBody=JSON.stringify(original.body),stale=clone(state.status);state.status.revision=9;state.fail=false;
 const result=await s.submit('control',stale,{action:'disconnect'});assert.ok(result);
 assert.equal(state.posts[1].body.expected_revision,9);assert.equal(JSON.stringify(original.body),originalBody);
 assert.equal(s.pending(),original);state.receipts.set(original.body.operation_key,{status:'cancelled'});await s.status();assert.equal(s.pending(),undefined);
}
// Timer ownership, opt-in separate from enabled, no overlapping dispatch and cleanup.
{
 const {state,client,memory,ctx}=fixture();let tree;
 const element=()=>h('div',null,h(EmailBridgePolling,{ctx,client,memory,workspaceToken:'ws'}),h(EmailBridgePolling,{ctx,client,memory,workspaceToken:'ws'}));
 await act(async()=>{tree=Renderer.create(element());});
 assert.equal(state.posts.length,0);assert.equal(state.timers.length,0,'default off allocates no polling timer');
 Object.assign(state.status,{enabled:true,mailbox:'me@example.test',account_namespace:'a',checkpoint:'123',runtime:{available:true}});
 await act(async()=>{for(const cb of memory.listeners)cb();});assert.equal(state.timers.length,0,'generic enabled must not start polling');
 state.status.polling_enabled=true;await act(async()=>{for(const cb of memory.listeners)cb();});assert.equal(state.timers.length,1,'companion panes share one timer');assert.ok(state.timers.every(t=>t.delay>=300000));
 state.delay=true;
 let poll;await act(async()=>{poll=state.timers[0].fn();await Promise.resolve();await Promise.resolve();});
 await state.timers[0].fn();assert.equal(state.posts.length,1);assert.equal(state.posts[0].body.trigger,'poll');
 state.fail=true;await act(async()=>{state.resolve();await poll;});await state.timers[0].fn();assert.equal(state.posts.length,1,'unknown pauses polling');
 assert.ok(state.timers.every(t=>t.stopped),'unknown stops polling timers');
 await act(async()=>tree.unmount());assert.ok(state.timers.every(t=>t.stopped));assert.equal(memory.pollers.size,0);
}
let tree,f,props;
const text=()=>JSON.stringify(tree.toJSON());
const button=label=>{const b=tree.root.findAllByType('button').find(n=>n.children.join('')===label);assert.ok(b,`Missing ${label}: ${text()}`);return b;};
const click=async label=>{const b=button(label);assert.equal(!!b.props.disabled,false,label+' disabled');await act(async()=>b.props.onClick({currentTarget:{focus:()=>f.state.focus.push('return')}}));};
const approve=async()=>act(async()=>tree.root.findByProps({type:'checkbox'}).props.onChange({target:{checked:true}}));
const confirm=async()=>act(async()=>tree.root.findByType('form').props.onSubmit({preventDefault(){}}));
async function mount(){f=fixture();props={...f,workspaceToken:'ws',contact:{id:'contact-one',version:2},routeKey:'routeA',storageBackend:'sqlite',open:(...args)=>f.state.opened=args};await act(async()=>{tree=Renderer.create(h(EmailBridgePanel,props),{createNodeMock:()=>({focus:()=>f.state.focus.push('approve')})});});}
await mount();assert.equal(f.state.posts.length,0);assert.equal(button('Verify existing connection').props.disabled,true);assert.match(text(),/Not verified/);
f.state.status.runtime.available=true;await click('Refresh local history');await click('Verify existing connection');assert.equal(f.state.focus.at(-1),'approve');assert.equal(button('Confirm action').props.disabled,true);
await act(async()=>tree.root.findByProps({type:'email'}).props.onChange({target:{value:'me@example.test'}}));
await act(async()=>tree.root.findByType('textarea').props.onChange({target:{value:'alias@example.test'}}));await approve();await confirm();
assert.equal(f.state.posts.length,1);assert.ok(f.state.posts[0].path.endsWith('/verify'));assert.deepEqual(f.state.posts[0].body.own_aliases,['alias@example.test']);assert.match(text(),/Verified mailbox/);assert.equal(f.state.status.polling_enabled,false);
await click('Read last 7 days');assert.match(text(),/unrelated metadata/);await approve();await confirm();assert.equal(f.state.posts[1].body.mode,'7days');assert.equal(f.state.posts[1].body.trigger,'manual');
await click('Sync while CRM is open');await approve();await confirm();assert.equal(f.state.posts[2].body.action,'start_polling');assert.equal(f.state.posts.length,3,'enabling polling does not immediately read provider');
await click('Edit contact email aliases');await act(async()=>tree.root.findByType('textarea').props.onChange({target:{value:'Person+sales@example.test\nSecond@example.test'}}));await approve();await confirm();assert.equal(f.state.posts[3].body.contact_version,2);assert.deepEqual(f.state.posts[3].body.aliases,['Person+sales@example.test','Second@example.test']);
await click('Read last 30 days');await act(async()=>tree.root.findByType('form').props.onKeyDown({key:'Escape',preventDefault(){}}));assert.equal(tree.root.findAllByType('form').length,0);assert.equal(f.state.focus.at(-1),'return');
f.state.status.requires_resync=true;await click('Refresh local history');assert.equal(button('Sync new metadata').props.disabled,true);assert.match(text(),/No silent reset/);
const item={account_namespace:'account',message_id:'m1',raw_headers:[['Subject','<script>untrusted</script>'],['From','sender@example.test'],['To','one@example.test, two@example.test']],internal_date_ms:1770000000000,current_match:{direction:'inbound_observed',participants:[{address:'one@example.test',roles:['to'],status:'ambiguous',matches:[{contact_id:'a'},{contact_id:'b'}]},{address:'two@example.test',roles:['to'],status:'matched',matches:[{contact_id:'c'}]}]},currently_linked:true,needs_review:true,last_observation:{status:'eligible'}};
f.state.history.items=[item];f.state.history.total=1;f.state.unresolved={items:[item],total:1};await click('Refresh local history');assert.match(text(),/untrusted/);assert.match(text(),/inbound observed/);assert.match(text(),/Needs review/);assert.match(text(),/No Company association/);await click('Review candidate a');assert.deepEqual(f.state.opened,['contacts','a']);
await act(async()=>tree.unmount());
// Closed over callbacks after unmount or profile replacement cannot submit.
await mount();f.state.status.runtime.available=true;await click('Refresh local history');await click('Verify existing connection');await approve();const handler=tree.root.findByType('form').props.onSubmit;await act(async()=>tree.unmount());await handler({preventDefault(){}});assert.equal(f.state.posts.length,0);
// Paging is a local read, not an action-session lifetime boundary. Cover both
// pagers, verification/sync, and known/unknown POST outcomes without resend.
for(const pager of ['Next history','Next review']) for(const kind of ['verify','sync']) for(const unknown of [false,true]) {
 await mount();f.state.status.runtime.available=true;
 if(kind==='sync')Object.assign(f.state.status,{enabled:true,mailbox:'me@example.test',account_namespace:'a',checkpoint:'123'});
 f.state.history.total=30;f.state.unresolved.total=30;await click('Refresh local history');
 await click(kind==='verify'?'Verify existing connection':'Read last 7 days');
 if(kind==='verify')await act(async()=>tree.root.findByProps({type:'email'}).props.onChange({target:{value:'me@example.test'}}));
 await approve();f.state.delay=true;f.state.fail=unknown;
 let submitted;await act(async()=>{submitted=tree.root.findByType('form').props.onSubmit({preventDefault(){}});await Promise.resolve();});
 await click(pager);assert.equal(f.state.posts.length,1);
 await act(async()=>{f.state.resolve();await submitted;});
 if(unknown){
   assert.equal(button('Cancel').props.disabled,false,'unknown outcome must release busy while preserving the operation lock');
   assert.equal(f.memory.attempts.size,1);await click('Refresh local history');assert.equal(f.memory.attempts.size,1);
   const sent=f.state.posts[0];f.state.receipts.set(sent.body.operation_key,kind==='verify'?{revision:1,account_namespace:'a'}:{outcome:{status:'complete',revision:1}});
   Object.assign(f.state.status,{revision:1,enabled:true,mailbox:'me@example.test',account_namespace:'a',checkpoint:'123'});
 }
 await click('Refresh local history');
 assert.equal(button('Read last 7 days').props.disabled,false,'pagination must not strand the mounted panel busy after the receipt is known');
 const reads=f.state.gets.filter(path=>path.includes(pager==='Next history'?'/contacts/':'/unresolved'));
 assert.match(reads.at(-1),/offset=25/,'late action completion must retain the latest selected page');
 assert.equal(f.state.posts.length,1);assert.equal(f.memory.attempts.size,0);await act(async()=>tree.unmount());
}
// Company grouping is a read-only projection through explicit relationships.
{
 const calls=[];let active=true,resolve;
 const client={current:()=>active,request:async(path,options)=>{calls.push({path,options});return {items:[item],total:1,association_basis:'current_explicit_company_contacts'};}};
 let opened;await act(async()=>{tree=Renderer.create(h(CompanyEmailBridgePanel,{client,workspaceToken:'company-ws',routeKey:'A',company:{id:'company-id',version:3},open:(...args)=>{opened=args;}}));});
 assert.match(text(),/Through explicitly linked Contacts/);assert.match(text(),/not direct provider evidence/);assert.equal(tree.root.findAllByType('textarea').length,0);assert.equal(tree.root.findAllByType('form').length,0);
 assert.equal(calls.length,1);assert.match(calls[0].path,/companies\/company-id\?workspace_token=company-ws/);assert.equal(calls[0].options,undefined);
 await click('Contact c');assert.deepEqual(opened,['contacts','c']);await act(async()=>tree.unmount());
 const staleClient={current:()=>active,request:()=>new Promise(r=>{resolve=r;})};
 await act(async()=>{tree=Renderer.create(h(CompanyEmailBridgePanel,{client:staleClient,workspaceToken:'old',routeKey:'A',company:{id:'company-id',version:3},open(){}}));});
 await act(async()=>tree.unmount());active=false;resolve({items:[item],total:1,association_basis:'current_explicit_company_contacts'});
 assert.equal(tree.toJSON(),null);
}
console.log('Gmail bridge React/VM synthetic safety contracts passed.');
