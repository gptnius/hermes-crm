import { createElement as h, useEffect, useRef, useState } from "react";

// Only memory, scoped to plugin lifetime + connection/profile/workspace/task.
// Frozen attempted bodies survive Close and view remount; no unknown save can
// mint a replacement key. Private task notes are never copied into the draft.
const scheduledResearchStores = new WeakMap(), scheduledResearchListeners = new WeakMap();
function srSubscribe(memory,listener) {
  if(!scheduledResearchListeners.has(memory))scheduledResearchListeners.set(memory,new Set());
  const listeners=scheduledResearchListeners.get(memory);listeners.add(listener);
  return ()=>listeners.delete(listener);
}
function srPublish(memory) {for(const listener of scheduledResearchListeners.get(memory)||[])listener();}
export function scheduledResearchMemory(owner, scope) {
  if (!scheduledResearchStores.has(owner)) scheduledResearchStores.set(owner,new Map());
  const store=scheduledResearchStores.get(owner);
  if (!store.has(scope)) store.set(scope,{draft:null,attempt:null,receipt:null,busy:false});
  return store.get(scope);
}
const srClone = value => JSON.parse(JSON.stringify(value));
const srId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const srVersion = value => Number.isSafeInteger(value) && value>0;
const srInstant = value => {
  if(typeof value!=='string'||!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d{1,6})?)?(?:Z|[+-]\d\d:\d\d)$/.test(value)||!Number.isFinite(Date.parse(value)))throw new Error('Use an ISO run time with Z or an explicit UTC offset.');
  return BigInt(Date.parse(value))*1000n+BigInt((/\.(\d{1,6})/.exec(value)?.[1]||'').padEnd(6,'0').slice(3));
};
const srObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const srText = (value,max=10000) => typeof value==='string' && value.trim().length>0 && [...value].length<=max;
const srDigest = value => typeof value==='string' && /^[a-f0-9]{64}$/.test(value);
const srTime = value => {try{srInstant(value);return true;}catch{return false;}};
const srSameTarget = (value,payload) => srObject(value) && ['target_kind','target_id','target_version'].every(key=>value[key]===payload[key]);
function srOperation(receipt,row) {
  if(!srObject(receipt)||!['evidence','proposal','report'].includes(receipt.kind)||typeof receipt.operation_key!=='string'||!/^run:[a-f0-9]{64}$/.test(receipt.operation_key)||!srObject(receipt.result))return false;
  const value=receipt.result,p=row.payload;
  if(receipt.kind==='report') {
    const identity=value.identity;
    return value.assignment_id===row.id&&value.generation===1&&srText(value.summary)&&['completed','blocked','failed'].includes(value.outcome)&&
      value.provenance==='native_run_reported'&&value.awaiting_human_review===true&&value.host_terminal_success_verified===false&&
      srObject(identity)&&identity.job_id===row.job_id&&srText(identity.job_id,160)&&identity.execution_id===row.execution_id&&srText(identity.execution_id,160)&&identity.profile===p.profile&&identity.job_name===row.job_name&&identity.source==='builtin'&&srTime(identity.scheduled_instant)&&srInstant(identity.scheduled_instant)===srInstant(p.run_at)&&(identity.started_at===null||srTime(identity.started_at))&&
      ((value.source_current===true&&value.source_reason===null)||(value.source_current===false&&['blocked','failed'].includes(value.outcome)&&['source_task_changed_or_closed','research_target_changed_or_archived','source_record_missing'].includes(value.source_reason)));
  }
  if(!srSameTarget(value,p)||!srId(value.id))return false;
  if(receipt.kind==='evidence')return srDigest(value.digest)&&value.lifecycle_version===1&&value.archived_at===null&&srTime(value.recorded_at)&&value.recorded_actor==='scheduled_research:'+row.id&&
    srSource(value.source_url)!==null&&srText(value.source_title,200)&&srTime(value.observed_at)&&(value.published_on===null||/^\d{4}-\d\d-\d\d$/.test(value.published_on))&&
    Number.isSafeInteger(value.claims_count)&&value.claims_count>=1&&value.claims_count<=10&&Number.isSafeInteger(value.hypotheses_count)&&value.hypotheses_count>=0&&value.hypotheses_count<=10;
  return p.propose_note===true&&srId(value.evidence_id)&&srDigest(value.evidence_digest)&&value.evidence_lifecycle_version===1&&value.proposal_version===1&&value.status==='pending'&&
    srDigest(value.proposal_digest)&&srDigest(value.before_hash)&&srDigest(value.after_hash)&&srText(value.addition)&&srTime(value.created_at)&&value.created_actor==='scheduled_research:'+row.id;
}
export function scheduledResearchRow(row,taskId,profile) {
  try {
    if(!srObject(row)||!srId(row.id)||!srVersion(row.version)||!srDigest(row.digest)||!srObject(row.payload)||!srTime(row.created_at)||!srTime(row.updated_at)||!srText(row.reason,160)||!['pending','create_unknown','resume_unknown','scheduled','result_reported','cancelled'].includes(row.state)||!(row.job_id===null||srText(row.job_id,160))||!(row.execution_id===null||srText(row.execution_id,160)))return false;
    const p=row.payload,keys=['target_kind','target_id','target_version','task_id','task_version','human_owner','public_question','run_at','research','propose_note','max_sources','mode','generation','profile','host_sha','task_due_at'];
    if(Object.keys(p).length!==keys.length||keys.some(key=>!Object.hasOwn(p,key))||p.mode!=='scheduled_research_v1'||p.generation!==1||p.profile!==profile||p.task_id!==taskId||!srId(p.task_id)||!srVersion(p.task_version)||!['contacts','companies'].includes(p.target_kind)||!srId(p.target_id)||!srVersion(p.target_version)||!srText(p.human_owner,160)||!srText(p.public_question,2000)||!srTime(p.run_at)||!(p.task_due_at===null||srTime(p.task_due_at))||!['search','web'].includes(p.research)||typeof p.propose_note!=='boolean'||!Number.isSafeInteger(p.max_sources)||p.max_sources<1||p.max_sources>10||!(typeof p.host_sha==='string'&&/^[a-f0-9]{40}$/.test(p.host_sha)))return false;
    if(row.job_name!==`CRM research ${row.id} g1`||JSON.stringify(row.enabled_toolsets)!==JSON.stringify([p.research,'crm_scheduled_research_run_v1','no_mcp'])||!Array.isArray(row.receipts)||row.receipts.length>p.max_sources+2||row.receipts.some(receipt=>!srOperation(receipt,row)))return false;
    if(new Set(row.receipts.map(r=>r.operation_key)).size!==row.receipts.length)return false;
    const reports=row.receipts.filter(r=>r.kind==='report'),proposals=row.receipts.filter(r=>r.kind==='proposal'),evidence=row.receipts.filter(r=>r.kind==='evidence');
    if(row.receipts.length&&(row.job_id===null||row.execution_id===null))return false;
    if(reports.length>1||proposals.length>1||evidence.length>p.max_sources||proposals.some(r=>!evidence.some(e=>e.result.id===r.result.evidence_id&&e.result.digest===r.result.evidence_digest)))return false;
    if(row.state==='pending'&&(row.job_id!==null||row.execution_id!==null||row.receipts.length!==0||row.reason!=='intent_saved_not_scheduled'))return false;
    if(['resume_unknown','scheduled','result_reported'].includes(row.state)&&row.job_id===null)return false;
    if(row.state==='result_reported'&&reports.length!==1)return false;
    if(reports.length&& !['result_reported','cancelled'].includes(row.state))return false;
    return true;
  }catch{return false;}
}
export function scheduledResearchReceipt(row, body, profile) {
  try {return scheduledResearchRow(row,body.data.task_id,profile)&&Object.entries(body.data).every(([key,value])=>key==='run_at'?srInstant(row.payload[key])===srInstant(value):row.payload[key]===value);}
  catch{return false;}
}
export function scheduledResearchRequest(row, action, binding) {
  const tool={schedule:'crm_scheduled_research_schedule',check:'crm_scheduled_research_reconcile',cancel:'crm_scheduled_research_cancel'}[action];
  if(!tool||!scheduledResearchRow(row,row?.payload?.task_id,row?.payload?.profile))throw new Error('Select a verified assignment.');
  const args={assignment_id:row.id,...(action==='cancel'?{expected_version:row.version}:{})};
  return `In this verified Hermes chat (${binding.connection} / ${binding.profile}, conversation ${binding.sessionId}), ${action} only the existing scheduled public research assignment below.\nCall ${tool} with ${JSON.stringify(args)}. First read crm_scheduled_research_get and verify version ${row.version}, digest ${row.digest}, task ${row.payload.task_id}, target ${row.payload.target_kind}/${row.payload.target_id} and profile ${row.payload.profile}. Stop if anything changed.\n${action==='schedule'?'I request the reviewed future one-shot public research, with the saved public question and preset only. Scheduling uses unattended cron approval policy, not an interactive prompt; preserve host safeguards.':action==='cancel'?'Invalidate this reviewed version and pause its exact future job. This does not stop an already running agent.':'Read and report exact saved and host state only. Do not resume, recreate or retry a schedule.'}\nNever create a replacement on an unknown outcome, change global cron settings or grants, contact people, apply notes, or complete the business task. If unavailable or approval is required, report that truthfully.\nSaved public question: ${row.payload.public_question}\nRun time: ${row.payload.run_at}; business due time: ${row.payload.task_due_at||'not set'}. Human owner: ${row.payload.human_owner}. Preset: ${row.payload.research}. Maximum saved sources: ${row.payload.max_sources}. Research tool-call and network budgets remain host-owned. Cited note proposal permitted: ${row.payload.propose_note?'yes':'no'}.`;
}
function srStatus(row) {
  if(row.state==='pending'&&!row.job_id)return 'Saved, not scheduled';
  if(row.state==='scheduled')return 'Scheduled registration observed; execution not confirmed';
  if(row.state==='result_reported')return 'Agent reported a result';
  if(row.state==='cancelled')return 'Locally invalidated; inspect pause receipt (running work is not stopped)';
  return 'Scheduling state requires review; do not create a replacement';
}
function srSource(value) {
  try {const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password&&!/[\s\x00-\x1f\\]/.test(value)?value:null;}catch{return null;}
}
export function ScheduledResearchPanel({client,task,workspaceToken,profile,memory,current,captureBinding,copyText,openNativeChat,companion,disabled=false,navigateTarget,timeHelpers,renderReview}) {
  const [opened,setOpened]=useState(false),[draft,setDraft]=useState(()=>memory.draft?{...memory.draft,run_wall:memory.draft.run_wall??(memory.draft.run_at?timeHelpers.wall(memory.draft.run_at,memory.draft.run_zone||'UTC'):'')}:{human_owner:'',public_question:'',run_at:'',research:'search',propose_note:false,max_sources:3,target_kind:'contacts',target_id:'',target_version:0}),[pageOffset,setPageOffset]=useState(0),[query,setQuery]=useState(''),[choices,setChoices]=useState([]),[history,setHistory]=useState(null),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[preview,setPreview]=useState(null),[,redraw]=useState(0);
  const mounted=useRef(false),epoch=useRef(0),searchEpoch=useRef(0),lock=useRef(false),launch=useRef(null),heading=useRef(null),latest=useRef(null),returnFocus=useRef(false);
  const [capture]=useState(()=>({task:task.id,version:task.version,workspace:workspaceToken,profile}));
  latest.current={task,workspaceToken,profile,disabled,current,opened,draft,preview};
  const valid=()=>mounted.current&&client.current()&&current()&&latest.current.current()&&!latest.current.disabled&&capture.task===latest.current.task.id&&capture.version===latest.current.task.version&&capture.workspace===latest.current.workspaceToken&&capture.profile===latest.current.profile;
  const active=()=>valid()&&latest.current.opened;
  const scoped=()=>`workspace_token=${encodeURIComponent(workspaceToken)}`;
  const read=path=>client.request(path+(path.includes('?')?'&':'?')+scoped());
  const button=(text,fn,extra={})=>h('button',{type:'button',onClick:fn,disabled:busy||disabled||!client.current(),...extra},text);
  async function load(offset=pageOffset){
    if(!Number.isSafeInteger(offset)||offset<0)offset=pageOffset;
    if(!active()||lock.current)return;const ticket=++epoch.current;lock.current=true;setBusy(true);setNotice('');
    try{const value=await read(`/scheduled-research?task_id=${encodeURIComponent(task.id)}&limit=25&offset=${offset}`);if(!active()||ticket!==epoch.current)return;
      if(!['present','absent'].includes(value?.storage)||!Array.isArray(value.items)||value.offset!==offset||value.limit!==25||(value.storage==='present'&&(value.initialized!==true||!Number.isSafeInteger(value.total)||value.total<0||value.items.length!==Math.min(25,Math.max(0,value.total-offset))))||(value.storage==='absent'&&(value.initialized!==false||value.total!==null||value.items.length!==0))||value.items.some(row=>!scheduledResearchRow(row,task.id,profile))||new Set(value.items.map(row=>row.id)).size!==value.items.length)throw new Error('Unverified history response.');
      setHistory(value);setPageOffset(offset);
      const refreshed=value.items.find(row=>row.id===memory.receipt?.id);if(refreshed){memory.receipt=srClone(refreshed);srPublish(memory);}
    }catch{if(active()&&ticket===epoch.current){setHistory(null);setNotice('Research status unavailable. This is not an empty history or proof that work was not scheduled.');}}
    finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  useEffect(()=>{mounted.current=true;const unsubscribe=srSubscribe(memory,()=>{if(valid()){setPreview(null);redraw(n=>n+1);}});return()=>{unsubscribe();mounted.current=false;epoch.current++;searchEpoch.current++;};},[memory]);
  useEffect(()=>{if(opened){heading.current?.focus();void load();}else if(returnFocus.current&&valid()){returnFocus.current=false;launch.current?.focus();}},[opened]);
  function edit(key,value){if(!active()||lock.current||memory.busy||memory.attempt)return;const next={...draft,[key]:value,...(key==='target_kind'?{target_id:'',target_version:0}:['run_wall','run_zone'].includes(key)?{run_choice:''}:{})};memory.draft=srClone(next);setDraft(next);setPreview(null);if(key==='target_kind'){searchEpoch.current++;setChoices([]);}}
  function close(){latest.current.opened=false;returnFocus.current=true;epoch.current++;searchEpoch.current++;setPreview(null);setOpened(false);setNotice('');if(valid()&&launch.current?.isConnected!==false)launch.current?.focus();}
  async function search(){
    if(!active()||lock.current||memory.busy||memory.attempt)return;const ticket=++searchEpoch.current,kind=draft.target_kind;setChoices([]);setNotice('');
    try{const value=await read(kind==='contacts'?`/reports/contacts?q=${encodeURIComponent(query)}&limit=50`:`/companies?q=${encodeURIComponent(query)}&limit=50`);if(!active()||ticket!==searchEpoch.current)return;
      if(!Array.isArray(value?.items))throw new Error('Invalid results');setChoices(value.items.filter(row=>srId(row.id)&&srVersion(row.version)&&!row.archived_at));
    }catch{if(active()&&ticket===searchEpoch.current)setNotice('Target search failed. No target was selected.');}
  }
  async function save(){
    if(!active()||lock.current||memory.busy||(!memory.attempt&&draft!==latest.current.draft))return;
    lock.current=true;memory.busy=true;srPublish(memory);setBusy(true);setNotice('');const ticket=++epoch.current;
    try{
      if(!memory.attempt){
        if(task.status!=='open'||!srId(draft.target_id)||!srVersion(draft.target_version)||!draft.human_owner.trim()||!draft.public_question.trim())throw new Error('Choose a current target, explicit human owner and public question.');
        if(!Number.isSafeInteger(draft.max_sources)||draft.max_sources<1||draft.max_sources>10||!['search','web'].includes(draft.research))throw new Error('Choose a supported preset and a source limit from 1 to 10.');
        const runAt=timeHelpers.resolve(draft.run_wall||'',draft.run_zone||'UTC',draft.run_at||'',draft.run_original_zone||'UTC',draft.run_choice||'');
        srInstant(runAt);if(Date.parse(runAt)<Date.now()+300000)throw new Error('Research run time must be at least five minutes ahead.');
        const fresh=await read(`/tasks/${encodeURIComponent(task.id)}`);if(!active()||ticket!==epoch.current)return;
        if(fresh.id!==task.id||fresh.version!==task.version||fresh.status!=='open')throw new Error('The task changed. Close and reopen this task before saving.');
        const detail=await read(`/${draft.target_kind}/${encodeURIComponent(draft.target_id)}`);if(!active()||ticket!==epoch.current)return;
        const target=detail.contact||detail.company;
        if(target?.id!==draft.target_id||target.version!==draft.target_version||target.archived_at)throw new Error('Target changed. Search and select its current version before saving.');
        const {target_name,run_wall,run_zone,run_choice,run_original_zone,...fields}=draft;
        memory.attempt=srClone({workspace_token:workspaceToken,idempotency_key:crypto.randomUUID(),data:{...fields,run_at:runAt,task_id:task.id,task_version:task.version}});srPublish(memory);
      }
      const body=srClone(memory.attempt),result=await client.request('/scheduled-research',{method:'POST',body});
      // Retain an exact verified receipt even after Close/navigation. Never attach
      // it to a different workspace or unlock a replacement on uncertainty.
      if(!scheduledResearchReceipt(result,body,profile))throw new Error('Receipt could not be verified.');
      memory.receipt=srClone(result);
      if(active()&&ticket===epoch.current){setNotice(`Saved intent verified. ${srStatus(result)}. Preparation and copying never dispatch work.`);redraw(n=>n+1);}
    }catch(error){if(active()&&ticket===epoch.current)setNotice(memory.attempt?'Save outcome unconfirmed. Retry the exact frozen request; do not create another assignment.':error.message);}
    finally{lock.current=false;memory.busy=false;srPublish(memory);if(mounted.current)setBusy(false);}
  }
  async function prepare(row,action,copy=false){
    if(!active()||lock.current||(copy&&(!preview||preview!==latest.current.preview)))return;
    if(!companion){openNativeChat();setNotice('Native chat opened if available. Choose this action again in the companion workspace; no request was prepared or sent.');return;}
    lock.current=true;setBusy(true);const ticket=++epoch.current;
    try{
      const binding=copy?preview?.binding:captureBinding();if(!binding?.current())throw new Error('Select a matching current native conversation and prepare again.');
      const fresh=await read(`/scheduled-research/${encodeURIComponent(row.id)}`);if(!active()||ticket!==epoch.current||!binding.current())return;
      if(!scheduledResearchRow(fresh,task.id,profile)||fresh.id!==row.id||fresh.version!==row.version||fresh.digest!==row.digest||fresh.payload?.task_id!==task.id||fresh.payload?.profile!==profile)throw new Error('Assignment changed. Refresh research status before preparing.');
      if(action==='schedule'){
        if(Date.parse(fresh.payload.run_at)<=Date.now())throw new Error('Research run time has passed. Check the existing assignment before preparing new work.');
        const freshTask=await read(`/tasks/${encodeURIComponent(task.id)}`);if(!active()||ticket!==epoch.current||!binding.current())return;
        if(fresh.state!=='pending'||fresh.reason!=='intent_saved_not_scheduled'||fresh.job_id||freshTask.version!==fresh.payload.task_version||freshTask.status!=='open')throw new Error('Not a current unscheduled intent. Check its status; do not recreate it.');
        const targetDetail=await read(`/${fresh.payload.target_kind}/${encodeURIComponent(fresh.payload.target_id)}`);if(!active()||ticket!==epoch.current||!binding.current())return;
        const target=targetDetail.contact||targetDetail.company;
        if(target?.id!==fresh.payload.target_id||target.version!==fresh.payload.target_version||target.archived_at)throw new Error('Research target changed. Do not schedule the stale assignment.');
      }
      const text=scheduledResearchRequest(fresh,action,binding);
      if(copy){if(text!==preview.text)throw new Error('Preview changed. Prepare again.');if(!copyText)throw new Error('Clipboard unavailable. Select the preview manually and review before native Send.');const ok=await copyText(text);if(active()&&ticket===epoch.current&&binding.current())setNotice(ok===true?'Copied, not sent or scheduled. Paste into this matching native chat, review, then use Send.':'Copy unconfirmed. No message was sent.');}
      else{setPreview({row:fresh,action,binding,text});setNotice('Prepared only. No scheduling, cancellation or message send occurred.');}
    }catch(error){if(active()&&ticket===epoch.current){setPreview(null);setNotice(error.message);}}
    finally{lock.current=false;if(mounted.current)setBusy(false);}
  }
  function timePreview(){
    if(!draft.run_wall)return h('p',null,'Choose a research date, time and timezone.');
    try {
      const zone=draft.run_zone||'UTC',original=draft.run_at||'',originalZone=draft.run_original_zone||'UTC',choice=draft.run_choice||'';
      const candidates=timeHelpers.candidates(draft.run_wall,zone,original,originalZone,choice);
      let resolved;try{resolved=timeHelpers.resolve(draft.run_wall,zone,original,originalZone,choice);}catch(error){return h('div',null,h('p',{role:'status'},error.message),candidates.length>1&&h('label',null,'Repeated time occurrence',h('select',{'aria-label':'Repeated time occurrence',value:choice,onChange:e=>edit('run_choice',e.target.value)},h('option',{value:''},'Choose the intended occurrence'),candidates.map(value=>h('option',{key:value,value},`${timeHelpers.readable(value,zone)} · ${value}`)))));}
      return h('p',null,`Research run preview: ${timeHelpers.readable(resolved,zone)} · exact instant ${resolved}`);
    }catch(error){return h('p',{role:'status'},error.message);}
  }
  const field=(name,title,options={})=>h('label',null,title,h('input',{'aria-label':title,value:draft[name],disabled:busy||memory.busy||!!memory.attempt,onChange:e=>edit(name,e.target.value),...options}));
  const rows=[...new Map([...(memory.previous||[]),...(memory.receipt?[memory.receipt]:[]),...(history?.items||[])].filter(row=>scheduledResearchRow(row,task.id,profile)).map(row=>[row.id,row])).values()];
  return h('section',{className:'hc-card hc-stack','aria-label':'Scheduled public research'},
    h('h3',null,'Scheduled public research'),h('p',null,'Opt-in public research for one Contact or Company. Saving is not scheduling. No automatic note application or task completion.'),
    !opened&&button(memory.attempt?'Review / recover research intent':'Set up public research',()=>{if(valid()){setOpened(true);}},{ref:launch}),
    opened&&h('div',{className:'hc-stack'},h('h4',{ref:heading,tabIndex:-1},'Review public research'),button('Close research',close,{disabled:false}),
      !valid()&&h('p',{role:'alert'},'Task, workspace or view changed. Close and reopen the task; no new action is allowed.'),
      h('p',null,`Task owner: ${task.owner_label||'not recorded'} · Business due: ${timeHelpers.readable(task.due_at,'UTC')}`),h('details',null,h('summary',null,'Task reference'),h('p',null,`Task ${task.id} · selected version ${capture.version}`)),
      !memory.attempt&&h('fieldset',{className:'hc-settings-section hc-stack',disabled:busy||memory.busy||!valid()},h('legend',null,'Public research intent'),
        h('label',null,'Target type',h('select',{'aria-label':'Target type',value:draft.target_kind,onChange:e=>edit('target_kind',e.target.value)},h('option',{value:'contacts'},'Contact'),h('option',{value:'companies'},'Company'))),
        h('label',null,'Search targets',h('input',{'aria-label':'Search targets',value:query,maxLength:200,onChange:e=>{searchEpoch.current++;setQuery(e.target.value);setChoices([]);}})),button('Find targets',search),
        h('p',null,'Search returns up to 50 matches. Refine the search if needed.'),
        h('label',null,'Research target',h('select',{'aria-label':'Research target',value:draft.target_id,onChange:e=>{const row=choices.find(r=>r.id===e.target.value);if(active()&&!memory.attempt){const next={...draft,target_id:row?.id||'',target_version:row?.version||0,target_name:row?.name||''};memory.draft=srClone(next);setDraft(next);}}},h('option',{value:''},'Choose a target'),draft.target_id&&!choices.some(r=>r.id===draft.target_id)&&h('option',{value:draft.target_id},draft.target_name||draft.target_id),choices.map(row=>h('option',{key:row.id,value:row.id},`${row.name} · v${row.version} · ${row.id}`)))),
        field('human_owner','Research human owner',{maxLength:160}),h('label',null,'Research run date and time',h('input',{'aria-label':'Research run date and time',type:'datetime-local',step:1,value:draft.run_wall||'',onChange:e=>edit('run_wall',e.target.value)})),
        h('label',null,'Research timezone',h('input',{'aria-label':'Research timezone',value:draft.run_zone||'UTC',placeholder:'America/New_York',onChange:e=>edit('run_zone',e.target.value)})),
        h('p',null,'Changing the timezone reinterprets the entered date and time. Run time must be at least five minutes ahead and is separate from the task due date.'),
        timePreview(),
        h('label',null,'Reviewed public question',h('textarea',{'aria-label':'Reviewed public question',maxLength:2000,value:draft.public_question,onChange:e=>edit('public_question',e.target.value)})),
        h('p',null,'Write only approved public research input. This question goes to external research tools and the configured model provider. Private task and CRM notes are never inserted here.'),
        h('label',null,'Research preset',h('select',{'aria-label':'Research preset',value:draft.research,onChange:e=>edit('research',e.target.value)},h('option',{value:'search'},'Search only'),h('option',{value:'web'},'Search and web extraction'))),
        field('max_sources','Maximum saved sources',{type:'number',min:1,max:10,onChange:e=>edit('max_sources',Number(e.target.value))}),
        h('p',null,'This caps saved evidence packets, not searches or fetched URLs. Research tool-call and network budgets remain host-owned.'),
        h('label',null,h('input',{type:'checkbox',checked:draft.propose_note,onChange:e=>edit('propose_note',e.target.checked)}),'Allow one cited note proposal for later review')),
      memory.attempt&&h('div',{className:'hc-settings-section hc-stack'},h('p',{role:'status'},memory.receipt?'Exact saved intent':memory.busy?'Saving the exact frozen intent. Close does not cancel it.':'Unconfirmed save: frozen request retained; Close does not cancel it.'),
        h('p',null,memory.attempt.data.public_question),h('p',null,`Research owner: ${memory.attempt.data.human_owner} · Run: ${timeHelpers.readable(memory.attempt.data.run_at,'UTC')}`),h('p',null,`${memory.attempt.data.research==='web'?'Search and web extraction':'Search only'} · up to ${memory.attempt.data.max_sources} saved sources · ${memory.attempt.data.propose_note?'Cited note proposal permitted':'No note proposal'}`),h('details',null,h('summary',null,'Exact submitted intent'),h('pre',null,JSON.stringify(memory.attempt.data,null,2)))),
      memory.receipt&&button('Prepare another research intent',()=>{if(active()&&!lock.current&&!memory.busy){
        memory.previous=[...(memory.previous||[]).filter(row=>row.id!==memory.receipt.id),memory.receipt];
        memory.attempt=null;memory.receipt=null;memory.draft=null;srPublish(memory);
        setDraft({human_owner:'',public_question:'',run_at:'',research:'search',propose_note:false,max_sources:3,target_kind:'contacts',target_id:'',target_version:0});setPreview(null);
        setNotice('This prepares additional work. Earlier assignments are not cancelled. Review their status before saving another.');
      }}),
      !memory.receipt&&button(memory.attempt?'Retry exact research save':'Save research intent',save,{disabled:busy||!valid()||memory.busy}),
      !memory.attempt&&button('Cancel draft',()=>{if(active()&&!lock.current){memory.draft=null;setDraft({human_owner:'',public_question:'',run_at:'',research:'search',propose_note:false,max_sources:3,target_kind:'contacts',target_id:'',target_version:0});close();}}),
      button('Refresh research status',load,{disabled:busy||!valid()}),
      history?.storage==='absent'&&h('p',{role:'status'},'Research storage is absent. No verified history is available; this is not proof that no prior work exists.'),
      history?.storage==='present'&&history.items.length===0&&h('p',null,'No saved research returned for this task.'),
      history?.storage==='present'&&h('div',{className:'hc-actions'},
        h('p',null,`${history.total} saved assignments · ${history.items.length?history.offset+1:0}–${history.offset+history.items.length} shown${memory.receipt?' · latest saved intent also pinned above':''}`),
        button('Previous research assignments',()=>load(Math.max(0,history.offset-25)),{disabled:busy||!valid()||history.offset===0}),
        button('Next research assignments',()=>load(history.offset+25),{disabled:busy||!valid()||history.offset+history.items.length>=history.total})),
      rows.length>0&&h('p',null,'Last observed saved state is shown below. Refresh after sending a native request; a prepared or copied request does not change this state.'),
      rows.map(row=>h('article',{key:row.id,className:'hc-settings-section hc-stack'},
        h('h4',null,srStatus(row)),h('p',null,row.payload.public_question),
        h('p',null,`${row.payload.target_kind==='contacts'?'Contact':'Company'} research · Owner: ${row.payload.human_owner} · ${row.payload.research==='web'?'Search and web extraction':'Search only'} · up to ${row.payload.max_sources} saved sources`),
        h('p',null,`Research run: ${timeHelpers.readable(row.payload.run_at,'UTC')} · Business due: ${timeHelpers.readable(row.payload.task_due_at,'UTC')}`),
        !['pending','scheduled','result_reported'].includes(row.state)&&h('p',{role:'status'},`Recorded reason: ${row.reason}. Check this exact assignment before creating replacement work.`),
        h('div',{className:'hc-actions'},row.state==='pending'&&!row.job_id&&button('Prepare research scheduling',()=>prepare(row,'schedule'),{disabled:busy||!valid()}),button('Prepare research check',()=>prepare(row,'check'),{disabled:busy||!valid()}),button('Prepare research cancellation',()=>prepare(row,'cancel'),{disabled:busy||!valid()}),
          navigateTarget&&button('Open target record',()=>{if(active())navigateTarget(row.payload.target_kind,row.payload.target_id);})),
        row.receipts.map((receipt,index)=>h('div',{key:index,className:'hc-stack'},
          receipt.kind==='report'&&h('div',{className:'hc-stack'},h('strong',null,`Agent report: ${receipt.result.outcome}`),h('p',null,receipt.result.summary),renderReview&&renderReview(row,receipt),receipt.result.source_current===false&&h('p',{role:'alert'},`Source changed: ${receipt.result.source_reason}. This is a blocked or failed agent report, not completed work.`)),
          receipt.kind==='evidence'&&h('div',null,h('a',{href:srSource(receipt.result.source_url),target:'_blank',rel:'noopener noreferrer'},receipt.result.source_title),h('p',null,`${receipt.result.claims_count} cited claims · observed ${timeHelpers.readable(receipt.result.observed_at,'UTC')}`)),
          receipt.kind==='proposal'&&h('div',null,h('strong',null,'Cited note proposal · not applied'),h('p',null,receipt.result.addition)),
          h('details',null,h('summary',null,`${receipt.kind} receipt details`),h('p',null,`Operation ${receipt.operation_key}`),h('pre',null,JSON.stringify(receipt.result,null,2))))),
        h('details',null,h('summary',null,'Assignment technical details'),h('p',null,`Assignment ${row.id} · version ${row.version} · ${row.state} / ${row.reason} · host job ${row.job_id||'not bound'}`),h('p',null,`Digest ${row.digest} · record update ${row.updated_at}`),h('pre',null,JSON.stringify(row.payload,null,2))))),
      preview&&(valid()&&preview.binding.current()?h('div',{className:'hc-stack'},h('p',null,`Review for conversation ${preview.binding.sessionId} · ${preview.binding.connection} / ${preview.binding.profile}. Paste and send yourself in native chat. No composer API or automatic send is used.`),h('textarea',{'aria-label':'Exact research request',readOnly:true,value:preview.text,rows:14}),button('Copy research request',()=>prepare(preview.row,preview.action,true),{disabled:busy||!copyText}),!copyText&&h('p',null,'Clipboard unavailable. Select and copy the preview manually.'),button('Discard research request',()=>{epoch.current++;latest.current.preview=null;setPreview(null);setNotice('Request discarded here only. Any previously copied or sent request is not cancelled.');heading.current?.focus();})):
        h('p',{role:'status'},'Native conversation or view changed. Prepare a new request before copying.')),
      notice&&h('p',{role:'status'},notice)));
}
