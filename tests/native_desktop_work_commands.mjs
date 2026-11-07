// Actual React + synthetic scoped SDK/REST only. No live job/model/provider/host.
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { webcrypto } from 'node:crypto';
import vm from 'node:vm';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer'), { act } = React;
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const commandName='crm-assignment-'+ 'a'.repeat(32);
const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
assert.doesNotMatch(source, /ask_choice|clarify\.response|prompt\.submit|openSession\s*\(|refreshInPlace|host\.composer\.|localStorage|sessionStorage/);
const flat = n => typeof n === 'string' || typeof n === 'number' ? String(n) : Array.isArray(n) ? n.map(flat).join(' ') : n?.children ? flat(n.children) : '';
const clone = x => structuredClone(x);
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
function atom(value) { const listeners=new Set(); return {get:()=>value,set(v){if(Object.is(v,value))return;value=v;for(const f of [...listeners])f();},listen(f){listeners.add(f);return()=>listeners.delete(f);},subscribe(f){listeners.add(f);return()=>listeners.delete(f);},listeners}; }
async function fixture() {
  const state={profile:atom('display-alias'),connectionId:atom('source-a'),gateway:atom('open'),cwd:atom('/synthetic'),activeSessionId:atom('chat-a'),focusedSessionId:atom('chat-a'),focusedStoredSessionId:atom('chat-a'),focusedSessionOwner:atom({connectionId:'source-a',profile:'display-alias'})};
  const epoch=atom(1), disposers=[], intervals=new Set(), timers=new Set(), mainVisible=atom(true), companionVisible=atom(true);
  const e={state,mainVisible,companionVisible,catalog:null,catalogReads:0,events:[],commands:[],posts:[],gates:{},ops:new Map(),token:'workspace-secret',profile:'work',retains:0,releases:0,viewRequest:{current:0},focus:[],unknown:false,historyFailure:false,historyTotal:null,overrides:{},task:{id:'t1',version:3,status:'open',title:'Synthetic follow-up',due_at:'2030-12-01T12:00:00+00:00'}};
  e.work={id:'a1',task_id:'t1',version:2,generation:1,state:'pending',reason:'not_scheduled',job_id:null,idempotency_key:'saved-intent-key',source_task_current:true,
    workspace:e.token,profile:e.profile,payload:{task_id:'t1',task_version:3,profile:e.profile,workspace:e.token,human_owner:'Synthetic owner',prompt:'Review CRM facts',success_criteria:'Cite saved evidence',run_at:'2030-12-01T13:30:41.123456+00:00',enabled_toolsets:['crm_read','crm_work_read','crm_work_report','no_mcp'],execution_source:'cron'},events:[],reports:[]};
  e.runtime={instance_id:'runtime-one',profile_id:'profile-home-work',authority_epoch:7};
  const route={connectionId:'source-a',profile:'display-alias',targetProfile:'work',mode:'remote'};
  const step=async(name,value)=>{e.events.push(name);if(e.gates[name])await e.gates[name].promise;return typeof value==='function'?value():value;};
  const host={state,composer:new Proxy({}, {get(){throw Error('Never access composer');}}),navigate(){e.events.push('navigate');},revealPane(){},paneVisibility:id=>id==='workspace'?mainVisible:companionVisible,openWorkspace(){return()=>{};},
    profileRoutes:()=>step('routes',()=>[clone(route)]), retainProfile:async(r,options)=>{assert.deepEqual(clone(r),route);assert.equal(options.spawnPriority,'foreground');e.retains++;await step('retain');return()=>{e.releases++;};},
    requestProfile:async(r,method,params,timeout)=>{
      assert.deepEqual(clone(r),route);
      if(method==='runtime.describe')return step('runtime',()=>clone(e.runtime));
      if(method==='session.info'){assert.deepEqual(clone(params),{session_id:'chat-a',profile:'work'});return step('info',()=>({source:'gui',desktop_protocol:'hermes-gateway-v1',profile_id:e.runtime.profile_id,profile_name:'work',...e.overrides.info}));}
      if(method==='commands.catalog'){await step('catalog:'+ (++e.catalogReads));return step('catalog',()=>e.catalog||{warning:'',plugin_discovery_error:'',pairs:[[ '/'+commandName,'CRM command']],categories:[{name:'Plugin commands',pairs:[['/'+commandName,'CRM command']]}],plugin_commands:{[commandName]:'CRM command'},canon:{['/'+commandName]:'/'+commandName},commands:{['/'+commandName]:{argument_mode:'text',desktop:null}},skills:{}});}
      assert.equal(method,'command.dispatch');assert.equal(timeout,30000);assert.deepEqual(Object.keys(params).sort(),['arg','name','profile','session_id']);assert.equal(params.name,commandName);assert.equal(params.profile,'work');assert.equal(params.session_id,'chat-a');
      e.commands.push(clone(params));await step('command');
      if(e.unknown)throw Error('Lost native command reply');
      const op=e.ops.get(params.arg);assert.ok(op);
      if(op.state==='prepared'){
        if(op.expected_assignment_version!==e.work.version || (op.verb==='schedule' && op.snapshot.task.version!==e.task.version)){op.state='stale';op.reason='source_changed';}
        else {op.state='finished';op.reason='native_operation_returned';if(op.verb==='schedule'){e.work.state='scheduled';e.work.reason='schedule_registered';e.work.job_id='synthetic-job';e.work.version++;}if(op.verb==='cancel'){e.work.state='cancelled';e.work.reason='future_schedule_paused';e.work.version++;}op.result=clone(e.work);}
        op.version++;op.actual_session_id='chat-a';op.mutation_slot_held=false;
      }
      return {type:'exec',output:JSON.stringify({schema_version:1,ok:true,operation:clone(op)})};
    }};
  const ctx={registerMany(){},onDispose(f){disposers.push(f);},setInterval(f){intervals.add(f);return()=>intervals.delete(f);},setTimeout(f){const t=setTimeout(()=>{timers.delete(t);f();},1);timers.add(t);return()=>{clearTimeout(t);timers.delete(t);};},rest:async(path,options)=>{
    const params=new URLSearchParams(path.split('?')[1]);
    if(path==='/work-operations'&&options?.method==='POST'){
      const b=clone(options.body);e.posts.push(b);assert.equal(b.workspace_token,e.token);assert.deepEqual(Object.keys(b).sort(),['assignment_id','expected_assignment_version','idempotency_key','intended_session_id','verb','workspace_token']);
      let op=[...e.ops.values()].find(x=>x.idempotency_key===b.idempotency_key);
      if(!op){op={schema_version:1,command_name:commandName,id:webcrypto.randomUUID(),profile:'work',workspace_token:e.token,task_id:'t1',idempotency_key:b.idempotency_key,verb:b.verb,state:'prepared',version:1,reason:'awaiting_explicit_command',assignment_id:b.assignment_id,expected_assignment_version:b.expected_assignment_version,intended_session_id:b.intended_session_id,actual_session_id:null,expires_at:new Date(Date.now()+300000).toISOString(),deadline_elapsed:false,mutation_slot_held:b.verb!=='check',snapshot:{assignment:{id:e.work.id,version:e.work.version,generation:1,digest:'frozen-digest',state:e.work.state,job_id:e.work.job_id,payload:clone(e.work.payload)},task:clone(e.task)},result:null};e.ops.set(op.id,op);}
      return step('prepare',()=>({...clone(op),...e.overrides.prepare}));
    }
    if(path.startsWith('/work-operations/')&&options?.method==='POST'){
      assert.ok(path.endsWith('/withdraw'));assert.deepEqual(clone(options.body),{workspace_token:e.token});const op=e.ops.get(path.split('/')[2]);await step('withdraw');if(op.state!=='prepared')throw Error('Already claimed');op.state='withdrawn';op.version++;op.mutation_slot_held=false;return clone(op);
    }
    assert.equal(options,undefined);assert.equal(params.get('workspace_token'),e.token);
    if(path.startsWith('/work-operations?'))return step('history',()=>{if(e.historyFailure)throw Error('Untrusted backend error');const rows=[...e.ops.values()].reverse(),offset=+params.get('offset');return{workspace_token:e.token,profile:'work',task_id:'t1',items:rows.slice(offset,offset+25).map(clone),total:e.historyTotal??rows.length,limit:25,offset,observed_at:'2026-11-07T15:00:00Z',...e.overrides.history};});
    if(path.startsWith('/work-operations/'))return step('get',()=>clone(e.ops.get(path.split('?')[0].split('/')[2])));
    if(path.startsWith('/reports/work?'))return{items:[clone(e.work)],total:1,offset:0,observed_at:'2026-11-07T15:00:00Z'};
    throw Error(`Unexpected route ${path}`);
  }};
  const useValue=a=>React.useSyncExternalStore(a.subscribe,a.get,a.get);
  const sdk={host,atom,useValue,gatewayActivationEpoch:epoch.get,useGatewayActivationEpoch:()=>useValue(epoch),PANES_AREA:'panes',ROUTES_AREA:'routes',SIDEBAR_NAV_AREA:'sidebar.nav',PALETTE_AREA:'palette'};
  const context=vm.createContext({console,Intl,URLSearchParams,crypto:webcrypto});const mod=new vm.SourceTextModule(source,{context});
  await mod.link(name=>{const values=name==='react'?React:name==='@hermes/plugin-sdk'?sdk:null;assert.ok(values);return new vm.SyntheticModule(Object.keys(values),function(){for(const[k,v]of Object.entries(values))this.setExport(k,v);},{context});});await mod.evaluate();const api=mod.namespace;api.default.register(ctx);
  let root,props;const clients=[];
  e.flush=async()=>act(async()=>{await new Promise(r=>setTimeout(r,4));});e.change=async f=>{await act(async()=>{f();});await e.flush();};
  e.mount=async extra=>{const identity=api.routeIdentity(ctx),client=api.createRouteClient(ctx,identity);clients.push(client);props={ctx,identity,client,task:e.task,workspaceToken:e.token,workspaceProfile:e.profile,workCommandName:commandName,snapshotGeneration:1,disabled:false,viewRequest:e.viewRequest,companion:true,openNativeChat(){e.events.push('openChat');},taskHeadingRef:{current:{focus(){e.focus.push('task-heading');}}},...extra};await act(async()=>{root=Renderer.create(React.createElement(React.StrictMode,null,React.createElement(api.TaskWork,props)),{createNodeMock:elem=>({isConnected:false,focus(){e.focus.push(flat(elem.props.children));},ownerDocument:{activeElement:null},querySelector(){return null;},querySelectorAll(){return[];}})});});await e.flush();};
  e.rerender=async extra=>{props={...props,...extra};await act(async()=>root.update(React.createElement(React.StrictMode,null,React.createElement(api.TaskWork,props))));await e.flush();};
  e.button=name=>root.root.findAllByType('button').find(n=>flat(n.children)===name);e.click=async name=>{const b=e.button(name);assert.ok(b,`Missing ${name}`);assert.notEqual(b.props.disabled,true,`Disabled ${name}`);await e.change(()=>b.props.onClick());};e.text=()=>flat(root.toJSON());e.field=name=>root.root.findByProps({'aria-label':name});
  e.unmount=async()=>{if(root){await act(async()=>root.unmount());root=null;}};e.finish=async()=>{await e.unmount();for(const c of clients)c.dispose();for(const d of disposers)d();for(const a of [...Object.values(state),mainVisible,companionVisible])assert.equal(a.listeners.size,0);assert.equal(intervals.size,0);assert.equal(timers.size,0);};
  Object.assign(e,{api,host,ctx,route});Object.defineProperty(e,'props',{get:()=>props});return e;
}
// Review is local intent only; exact explicit confirmation produces one authenticated command.
{
  const e=await fixture();await e.mount();assert.equal(e.commands.length,0);assert.equal(e.posts.length,0);
  await e.click('Review CRM scheduling');assert.equal(e.posts.length,1);assert.equal(e.commands.length,0);
  const preview=e.field('Server-derived operation preview').props.value;assert.match(preview,/123456/);assert.match(preview,/Synthetic owner/);assert.match(preview,/frozen-digest/);assert.doesNotMatch(preview,/workspace-secret/);assert.equal(e.field('Server-derived operation preview').props.readOnly,true);
  const confirm=e.button('Confirm schedule in CRM').props.onClick;await e.change(()=>{confirm();confirm();});assert.equal(e.commands.length,1);assert.equal(e.retains,1);assert.equal(e.releases,1);
  assert.match(e.text(),/Native command returned/);assert.match(e.text(),/Recorded assignment result: a1 · Version 3 · Scheduled/);assert.equal(e.task.status,'open');assert.equal(e.button('Confirm schedule in CRM'),undefined);
  await e.click('Read local operation status');assert.equal(e.commands.length,1);await e.finish();
}
// Cancellation of a done source is explicit; native status check needs no second confirmation.
for(const verb of ['cancel','check']){
  const e=await fixture();e.task.status='done';e.work.source_task_current=false;await e.mount();
  await e.click(verb==='cancel'?'Review CRM cancellation':'Check native status');
  if(verb==='cancel'){assert.equal(e.commands.length,0);assert.match(e.text(),/does not stop an agent already running/);await e.click('Confirm cancellation in CRM');}
  assert.equal(e.commands.length,1);assert.equal([...e.ops.values()][0].verb,verb);assert.equal(e.task.status,'done');await e.finish();
}
// No late command at any await when its panel, selection, route, epoch, session or enabled state changes.
for(const stage of ['retain','routes','runtime','info','catalog','get'])for(const change of ['close','profile-aba','chat-aba','pane-aba','selection','disabled','unmount']){
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');const gate=deferred();e.gates[stage]=gate;
  await e.click('Confirm schedule in CRM');
  if(change==='close')await e.click('Close operation review');
  if(change==='profile-aba')await e.change(()=>{e.state.profile.set('other');e.state.profile.set('display-alias');});
  if(change==='chat-aba')await e.change(()=>{e.state.focusedStoredSessionId.set('other');e.state.focusedStoredSessionId.set('chat-a');});
  if(change==='pane-aba')await e.change(()=>{e.companionVisible.set(false);e.companionVisible.set(true);});
  if(change==='selection')e.viewRequest.current++;
  if(change==='disabled')await e.rerender({disabled:true});
  if(change==='unmount')await e.unmount();
  await e.change(()=>gate.resolve());assert.equal(e.commands.length,0,`${stage} ${change}`);assert.equal(e.retains,e.releases);await e.finish();
}
// A failed/late command never becomes permission to repeat; prepared history is recovery-only.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');e.unknown=true;await e.click('Confirm schedule in CRM');
  assert.equal(e.commands.length,1);assert.match(e.text(),/Do not resend/);assert.equal(e.button('Confirm schedule in CRM'),undefined);
  await e.click('Close operation review');await e.unmount();await e.mount();await e.click('Open operation recovery');
  assert.equal(e.button('Confirm schedule in CRM'),undefined);await e.click('Read local operation status');assert.equal(e.commands.length,1);
  await e.click('Withdraw unclaimed operation');assert.equal([...e.ops.values()][0].state,'withdrawn');assert.match(e.text(),/No existing schedule or running agent was cancelled/);
  await e.click('Close operation review');e.unknown=false;await e.click('Review CRM scheduling');assert.equal(e.posts.length,2);assert.notEqual(e.posts[0].idempotency_key,e.posts[1].idempotency_key);await e.finish();
}
// Once dispatched, Close cannot cancel it or move its result into another review.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');const gate=deferred();e.gates.command=gate;await e.click('Confirm schedule in CRM');assert.equal(e.commands.length,1);
  await e.click('Close operation review');await e.change(()=>gate.resolve());assert.doesNotMatch(e.text(),/Native command returned/);assert.equal(e.releases,1);
  await e.click('Refresh local operation history');await e.click('Open operation recovery');assert.match(e.text(),/Finished/);assert.equal(e.button('Confirm schedule in CRM'),undefined);assert.equal(e.commands.length,1);await e.finish();
}
// Malformed profile/session/snapshot, expired review, old SDK and ordinary CRM fail closed.
for(const fault of ['alias','session','snapshot','expired','sdk','companion']){
  const e=await fixture();if(fault==='session')e.overrides.info={source:'telegram'};if(fault==='alias')e.overrides.info={profile_name:'foreign'};if(fault==='snapshot')e.overrides.prepare={workspace_token:'foreign'};if(fault==='expired')e.overrides.prepare={deadline_elapsed:true};if(fault==='sdk')delete e.host.requestProfile;
  await e.mount({companion:fault!=='companion'});await e.click('Review CRM scheduling');
  if(e.button('Confirm schedule in CRM'))await e.click('Confirm schedule in CRM');assert.equal(e.commands.length,0,fault);await e.finish();
}
// Server pages expose unresolved rows and total beyond one page; local refresh never dispatches.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');await e.click('Close operation review');const original=[...e.ops.values()][0];
  for(let i=0;i<30;i++){const row=clone(original);row.id=webcrypto.randomUUID();row.state=i===0?'unknown':'finished';e.ops.set(row.id,row);}
  await e.click('Refresh local operation history');assert.match(e.text(),/31 operations/);await e.click('Next operations');assert.match(e.text(),/26–31 shown/);assert.match(e.text(),/Unknown/);
  e.historyFailure=true;await e.click('Refresh local operation history');assert.match(e.text(),/could not be refreshed/);assert.match(e.text(),/31 operations/);assert.equal(e.commands.length,0);await e.finish();
}
console.log('PASS CRM-confirmed user commands: server-only preview, exact UUID command, profile aliases, one-use confirmation, native read-only check, no model/question/composer/session writes, await/ABA/close guards, frozen unknown recovery, prepared-only withdraw, paged unresolved history. Synthetic SDK/REST; no real jobs/models or native window QA.');
// Preparation freezes caller arguments before reads, and confirmation freezes target/snapshot before awaits.
{
  const e=await fixture();await e.mount();const gate=deferred();e.gates.routes=gate;
  const controller=e.api.createWorkCommandController({client:e.props.client,binding:{sessionId:'chat-a',connection:'source-a',profile:'display-alias',current:()=>true},workspaceToken:e.token,workspaceProfile:'work',taskId:'t1',workCommandName:commandName,isCurrent:()=>true,hostAPI:e.host});
  const body={verb:'schedule',assignment_id:'a1',expected_assignment_version:2,idempotency_key:'frozen-direct'};
  const pending=controller.prepare(body);body.verb='cancel';body.assignment_id='foreign';gate.resolve();const prepared=await pending;
  assert.equal(e.posts[0].verb,'schedule');assert.equal(e.posts[0].assignment_id,'a1');delete e.gates.routes;
  const retain=deferred();e.gates.retain=retain;const supplied=clone(prepared),id=prepared.row.id;
  const confirmation=controller.confirm(supplied);supplied.target.route.targetProfile='foreign';supplied.row.id='foreign';supplied.row.snapshot.assignment.payload.prompt='Changed';retain.resolve();await confirmation;
  assert.equal(e.commands[0].arg,id);assert.equal(e.commands[0].profile,'work');await e.finish();
}
// Lost preparation response is reconciled by scoped key through history, enabling deliberate new work after Withdraw.
{
  const e=await fixture();await e.mount();const gate=deferred();e.gates.prepare=gate;await e.click('Review CRM scheduling');await e.change(()=>gate.reject(Error('Lost preparation reply')));
  assert.equal(e.commands.length,0);assert.equal(e.button('Confirm schedule in CRM'),undefined);await e.click('Close operation review');delete e.gates.prepare;
  await e.click('Refresh local operation history');await e.click('Open operation recovery');await e.click('Withdraw unclaimed operation');await e.click('Close operation review');
  await e.click('Review CRM scheduling');assert.equal(e.posts.length,2);assert.notEqual(e.posts[0].idempotency_key,e.posts[1].idempotency_key);assert.ok(e.button('Confirm schedule in CRM'));await e.finish();
}
for(const stage of ['routes','runtime','info','catalog','prepare'])for(const change of ['close','pane-aba','unmount']){
  const e=await fixture();await e.mount();const gate=deferred();e.gates[stage]=gate;await e.click('Review CRM scheduling');
  if(change==='close')await e.click('Close operation review');
  if(change==='pane-aba')await e.change(()=>{e.mainVisible.set(false);e.mainVisible.set(true);});
  if(change==='unmount')await e.unmount();await e.change(()=>gate.resolve());
  assert.equal(e.commands.length,0);if(stage!=='prepare')assert.equal(e.posts.length,0);if(change!=='unmount')assert.equal(e.button('Confirm schedule in CRM'),undefined);await e.finish();
}
// Task changes after review are rejected by the command, not displayed as scheduling success.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');e.task.version++;await e.click('Confirm schedule in CRM');
  assert.equal([...e.ops.values()][0].state,'stale');assert.equal(e.work.state,'pending');assert.equal(e.work.job_id,null);assert.doesNotMatch(e.text(),/Recorded assignment result:.*Scheduled/);await e.finish();
}
// Visibility changes between review and click invalidate the affordance, without silent return.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');assert.match(e.text(),/configured model provider, which may receive CRM data/);
  await e.change(()=>{e.mainVisible.set(false);e.mainVisible.set(true);});await e.click('Confirm schedule in CRM');assert.match(e.text(),/pane visibility changed/);assert.equal(e.commands.length,0);await e.finish();
}
// Copied workspace tokens never merge retained operations across distinct Desktop connections.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');await e.click('Close operation review');await e.unmount();
  e.state.connectionId.set('source-b');e.state.focusedSessionOwner.set({connectionId:'source-b',profile:'display-alias'});e.route.connectionId='source-b';e.ops.clear();
  await e.mount();await e.click('Review CRM scheduling');assert.equal(e.posts.length,2);assert.notEqual(e.posts[0].idempotency_key,e.posts[1].idempotency_key);await e.finish();
}
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');await e.click('Close operation review');const original=new Map([...e.ops].map(([k,v])=>[k,clone(v)]));await e.unmount();
  e.state.connectionId.set('source-b');e.state.focusedSessionOwner.set({connectionId:'source-b',profile:'display-alias'});e.route.connectionId='source-b';
  await e.mount();await e.click('Open operation recovery');await e.click('Withdraw unclaimed operation');await e.click('Close operation review');await e.unmount();
  e.state.connectionId.set('source-a');e.state.focusedSessionOwner.set({connectionId:'source-a',profile:'display-alias'});e.route.connectionId='source-a';e.ops=original;
  await e.mount();await e.click('Review CRM scheduling');assert.equal(e.posts.length,1);assert.equal(e.button('Confirm schedule in CRM'),undefined);assert.match(e.text(),/Recover this existing preparation/);await e.finish();
}
// A released, returned unknown result permits a deliberately new Cancel. Crash-held slots remain recovery-only.
for(const held of [false,true]){
  const e=await fixture();await e.mount();await e.click('Review CRM cancellation');const op=[...e.ops.values()][0];
  e.work.state='cancelled';e.work.reason='pause_outcome_unknown';e.work.version++;op.state='unknown';op.version++;op.mutation_slot_held=held;op.result=clone(e.work);
  await e.click('Read local operation status');await e.click('Close operation review');await e.click('Review CRM cancellation');
  assert.equal(e.posts.length,held?1:2);if(held)assert.equal(e.button('Confirm cancellation in CRM'),undefined);else assert.ok(e.button('Confirm cancellation in CRM'));await e.finish();
}
// Local recovery needs no native command SDK, and a claimed operation cannot be withdrawn from a stale panel.
{
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');await e.click('Close operation review');delete e.host.requestProfile;
  await e.click('Open operation recovery');const op=[...e.ops.values()][0];op.state='dispatching';op.version++;
  await e.click('Withdraw unclaimed operation');assert.equal(op.state,'dispatching');assert.match(e.text(),/Local operation status was not confirmed/);assert.equal(e.commands.length,0);await e.finish();
}
// Exact initiating button or task heading receives focus only after the review has actually closed.
for(const connected of [true,false]){
  const e=await fixture();await e.mount();const node={isConnected:connected,focus(){e.focus.push('original-launcher');}};
  await e.change(()=>e.button('Review CRM scheduling').props.onClick({currentTarget:node}));await e.click('Close operation review');
  assert.equal(e.focus.at(-1),connected?'original-launcher':'task-heading');await e.finish();
}
console.log('PASS command recovery refinements: immutable caller snapshots, copied-token connection separation, lost prepare/key reconciliation, unknown slot release, visibility lifecycle, unavailable SDK local recovery and focus restoration.');
// Current catalog must prove an exact plugin row, not just membership in plugin_commands.
for(const stage of ['prepare','confirm'])for(const fault of ['user-exec','builtin','skill','warning','plugin-error','missing','wrong-name','duplicate']){
  const e=await fixture();await e.mount();
  if(stage==='confirm')await e.click('Review CRM scheduling');
  const key='/'+commandName;e.catalog={warning:'',plugin_discovery_error:'',pairs:[[key,'CRM']],categories:[{name:'Plugin commands',pairs:[[key,'CRM']]}],plugin_commands:{[commandName]:'CRM'},canon:{[key]:key},commands:{[key]:{argument_mode:'text',desktop:null}},skills:{}};
  if(fault==='user-exec')e.catalog.categories[0].name='User commands';if(fault==='builtin')e.catalog.categories[0].name='System';if(fault==='skill')e.catalog.skills[key]={};if(fault==='warning')e.catalog.warning='Discovery failed';if(fault==='plugin-error')e.catalog.plugin_discovery_error='Unavailable';if(fault==='missing')e.catalog.categories=[];if(fault==='wrong-name')e.catalog.canon[key]='/unrelated';if(fault==='duplicate')e.catalog.pairs.push([key,'Collision']);
  await e.click(stage==='prepare'?'Review CRM scheduling':'Confirm schedule in CRM');assert.equal(e.commands.length,0,`${stage} ${fault}`);assert.equal(e.posts.length,stage==='prepare'?0:1);await e.finish();
}
console.log('PASS workspace-specific command name and current complete catalog guards reject user/builtin/skill collisions, missing/ambiguous entries and discovery errors at preparation and confirmation.');

// Untrusted metadata cannot redirect the exact operation or misbind an empty history page.
for(const fault of [{task_id:'foreign'},{command_name:'crm-assignment'},{command_name:'crm-assignment-'+ 'b'.repeat(32)}]){
  const e=await fixture();e.overrides.prepare=fault;await e.mount();await e.click('Review CRM scheduling');assert.equal(e.button('Confirm schedule in CRM'),undefined);assert.equal(e.commands.length,0);await e.finish();
}
for(const fault of [{task_id:'foreign'},{limit:100},{observed_at:'invalid'}]){
  const e=await fixture();e.overrides.history=fault;await e.mount();assert.match(e.text(),/Operation history could not be refreshed/);assert.equal(e.button('Open operation recovery'),undefined);assert.equal(e.commands.length,0);await e.finish();
}
console.log('PASS strict backend task/command identity and page binding, including empty-page mismatch, fail closed.');

// Independently fence the LAST await: fresh catalog read after exact operation GET.
for(const change of ['close','main-aba','companion-aba','collision']){
  const e=await fixture();await e.mount();await e.click('Review CRM scheduling');const gate=deferred();e.gates['catalog:3']=gate;
  await e.click('Confirm schedule in CRM');assert.ok(e.events.indexOf('get')<e.events.indexOf('catalog:3'));assert.equal(e.catalogReads,3);assert.equal(e.commands.length,0);
  if(change==='close')await e.click('Close operation review');
  if(change==='main-aba')await e.change(()=>{e.mainVisible.set(false);e.mainVisible.set(true);});
  if(change==='companion-aba')await e.change(()=>{e.companionVisible.set(false);e.companionVisible.set(true);});
  if(change==='collision'){const key='/'+commandName;e.catalog={warning:'',plugin_discovery_error:'',pairs:[[key,'User collision']],categories:[{name:'User commands',pairs:[[key,'User collision']]}],plugin_commands:{[commandName]:'Hidden CRM'},canon:{[key]:key},commands:{[key]:{argument_mode:'text',desktop:null}},skills:{}};}
  await e.change(()=>gate.resolve());assert.equal(e.commands.length,0,change);assert.equal(e.retains,e.releases);await e.finish();
}
console.log('PASS final catalog immediately after exact REST read: separate deferred close/hide-show ABA and newly introduced command collision all stop dispatch.');

// Proven pre-POST failures can retry only the same frozen preparation/key, by an explicit click.
for(const failure of ['catalog','runtime','info','route']){
  const e=await fixture();
  if(failure==='catalog')e.catalog={warning:'Synthetic discovery failure'};
  if(failure==='runtime')e.runtime.instance_id='';
  if(failure==='info')e.overrides.info={source:'telegram'};
  if(failure==='route')e.route.targetProfile='wrong';
  await e.mount();await e.click('Review CRM scheduling');assert.equal(e.posts.length,0);assert.equal(e.ops.size,0);assert.match(e.text(),/before any save request was attempted/);
  const key=e.text().match(/Preparation request key: ([0-9a-f-]{36})/)[1];assert.ok(e.button('Retry same preparation'));
  await e.click('Close operation review');await e.click('Review CRM scheduling');assert.equal(e.posts.length,0);assert.ok(e.text().includes(key));
  e.catalog=null;e.runtime.instance_id='runtime-one';e.overrides.info={};e.route.targetProfile='work';
  const retry=e.button('Retry same preparation').props.onClick;await e.change(()=>{retry();retry();});
  assert.equal(e.posts.length,1);assert.equal(e.posts[0].idempotency_key,key);assert.equal(e.posts[0].intended_session_id,'chat-a');assert.equal(e.posts[0].expected_assignment_version,2);assert.equal(e.commands.length,0);assert.ok(e.button('Confirm schedule in CRM'));await e.finish();
}
// Once POST is attempted, even an immediate throw/lost response irreversibly removes safe preparation retry.
{
  const e=await fixture();e.catalog={warning:'Preflight failure'};await e.mount();await e.click('Review CRM scheduling');const retry=e.button('Retry same preparation').props.onClick;
  e.catalog=null;const gate=deferred();e.gates.prepare=gate;await e.click('Retry same preparation');assert.equal(e.posts.length,1);assert.equal(Boolean(e.button('Retry same preparation')),false);
  await e.change(()=>gate.reject(Error('Lost POST reply')));await e.change(()=>retry());assert.equal(e.posts.length,1);assert.equal(e.commands.length,0);assert.equal(Boolean(e.button('Retry same preparation')),false);
  await e.click('Close operation review');await e.click('Review CRM scheduling');assert.equal(Boolean(e.button('Retry same preparation')),false);assert.equal(e.posts.length,1);await e.finish();
}
// Retry must stay in the original intended conversation; even read-only Check retries only prepare a review.
{
  const e=await fixture();e.catalog={warning:'Preflight failure'};await e.mount();await e.click('Check native status');e.catalog=null;
  await e.change(()=>{e.state.focusedStoredSessionId.set('chat-b');e.state.focusedSessionId.set('chat-b');e.state.activeSessionId.set('chat-b');});await e.click('Retry same preparation');assert.equal(e.posts.length,0);assert.match(e.text(),/original intended main native conversation/);
  await e.change(()=>{e.state.focusedStoredSessionId.set('chat-a');e.state.focusedSessionId.set('chat-a');e.state.activeSessionId.set('chat-a');});await e.click('Retry same preparation');assert.equal(e.posts.length,1);assert.equal(e.commands.length,0);
  await e.click('Check native status');assert.equal(e.commands.length,1);await e.finish();
}
console.log('PASS explicit frozen-key preparation recovery after proven pre-POST failure; duplicate clicks, POST uncertainty, original-session binding and review-only Check retry fenced.');
