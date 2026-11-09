import { createElement as h, useEffect, useRef, useState } from "react";

// Plugin-lifetime only. Caller supplies a connection/profile/workspace/report key.
const rrStores = new WeakMap();
export function reportReviewMemory(owner, scope) {
  if (!rrStores.has(owner)) rrStores.set(owner, new Map());
  const store = rrStores.get(owner);
  if (!store.has(scope)) store.set(scope, { attempt: null, receipt: null, busy: false, listeners: new Set() });
  return store.get(scope);
}
const rrPublish = memory => { for (const fn of memory.listeners) fn(); };
const rrClone = value => JSON.parse(JSON.stringify(value));
const rrObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const rrText = value => typeof value === 'string' && value.trim().length > 0;
const rrId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
const rrDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const rrVersion = value => Number.isSafeInteger(value) && value > 0;
const rrTime = value => {
  if (typeof value !== 'string') return false;
  const m=/^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.\d{1,6})?(Z|[+-](\d\d):(\d\d))$/.exec(value);
  if (!m || +m[1]<1 || +m[2]<1 || +m[2]>12 || +m[3]<1 || +m[3]>new Date(Date.UTC(+m[1],+m[2],0)).getUTCDate() || +m[4]>23 || +m[5]>59 || +m[6]>59 || (m[7]!=='Z' && (+m[8]>14 || +m[9]>59 || (+m[8]===14 && +m[9]!==0)))) return false;
  return Number.isFinite(Date.parse(value));
};
const rrKeys = (value, keys) => rrObject(value) && Object.keys(value).sort().join('|') === keys.split(' ').sort().join('|');
const rrCanonical = value => JSON.stringify(value, (_, v) => rrObject(v) ? Object.fromEntries(Object.keys(v).sort().map(k => [k, v[k]])) : v);
const rrEqual = (a, b) => rrCanonical(a) === rrCanonical(b);
function rrBinding(b, expected) {
  if (!rrKeys(b, 'family assignment_id report_id assignment_digest generation report_digest identity summary outcome task_id task_version target') || !['native','scheduled_research'].includes(b.family) || !rrId(b.assignment_id) || !rrId(b.task_id) || !rrDigest(b.assignment_digest) || !rrDigest(b.report_digest) || !rrVersion(b.generation) || !rrVersion(b.task_version) || !rrText(b.summary) || [...b.summary].length > 10000 || !['completed','blocked','failed'].includes(b.outcome)) return false;
  if (b.family === 'native' ? !rrId(b.report_id) || b.target !== null : !/^run:[a-f0-9]{64}$/.test(b.report_id) || b.generation !== 1 || !rrKeys(b.target,'target_kind target_id target_version') || !['contacts','companies'].includes(b.target.target_kind) || !rrId(b.target.target_id) || !rrVersion(b.target.target_version)) return false;
  const i = b.identity;
  if (!rrKeys(i,'job_id job_name execution_id source scheduled_instant started_at profile') || !['job_id','execution_id','profile'].every(k => rrText(i[k]) && i[k].length <= 160) || i.job_name !== `CRM ${b.family === 'native' ? 'work' : 'research'} ${b.assignment_id} g${b.generation}` || i.source !== 'builtin' || !rrTime(i.scheduled_instant) || !(i.started_at === null || rrTime(i.started_at))) return false;
  return Object.entries(expected).every(([key, value]) => rrEqual(b[key],value));
}
function rrContext(c, binding) {
  if (!rrKeys(c,'report assignment_version assignment_state task target source_current source_reason') || !rrEqual(c.report,binding) || !rrVersion(c.assignment_version) || !['pending','create_unknown','resume_unknown','unknown','bound_paused','scheduled','result_reported','cancelled','superseded'].includes(c.assignment_state)) return false;
  const t=c.task, r=c.target;
  if (!rrKeys(t,'id assigned_version current_version current_status') || t.id!==binding.task_id || t.assigned_version!==binding.task_version || !(t.current_version===null ? t.current_status===null : rrVersion(t.current_version) && ['open','done'].includes(t.current_status))) return false;
  if (binding.target===null ? r!==null : !rrKeys(r,'kind id assigned_version current_version archived') || r.kind!==binding.target.target_kind || r.id!==binding.target.target_id || r.assigned_version!==binding.target.target_version || !(r.current_version===null || rrVersion(r.current_version)) || typeof r.archived!=='boolean') return false;
  if(r && (r.current_version===null || r.kind==='contacts') && r.archived)return false;
  const reason=t.current_version===null || (r && r.current_version===null) ? 'source_record_missing' : t.current_version!==t.assigned_version || t.current_status!=='open' ? 'source_task_changed_or_closed' : r && (r.current_version!==r.assigned_version || r.archived) ? 'research_target_changed_or_archived' : null;
  return c.source_current===(reason===null) && c.source_reason===reason;
}
function rrEvent(e,binding) {
  return rrKeys(e,'id family assignment_id report_id version action context context_digest actor created_at') && rrId(e.id) && ['family','assignment_id','report_id'].every(k=>e[k]===binding[k]) && rrVersion(e.version) && e.action===(e.version%2 ? 'acknowledge' : 'revoke') && rrContext(e.context,binding) && rrDigest(e.context_digest) && e.actor==='desktop' && rrTime(e.created_at);
}
export function reportReviewPreview(value,expected) {
  try {
    if (!rrObject(value)) return false;
    const {context,context_digest,review,...binding}=value;
    if (!rrBinding(binding,expected) || !rrContext(context,binding) || !rrDigest(context_digest) || !rrKeys(review,'status version latest_event history history_total history_truncated') || !Number.isSafeInteger(review.version) || review.version<0 || review.status!==(review.version%2 ? 'reviewed_in_crm' : 'awaiting_review') || review.history_total!==review.version || review.history_truncated!==(review.version>50) || !Array.isArray(review.history) || review.history.length!==Math.min(50,review.version)) return false;
    if (review.history.some((e,n)=>!rrEvent(e,binding) || e.version!==review.version-review.history.length+n+1) || new Set(review.history.map(e=>e.id)).size!==review.history.length || !rrEqual(review.latest_event,review.history.at(-1)||null)) return false;
    return true;
  } catch { return false; }
}
export function reportReviewReceipt(value,attempt) {
  try {
    return rrKeys(value,'event review') && rrEvent(value.event,attempt.preview.context.report) && value.event.action===attempt.action && value.event.version===attempt.body.expected_review_version+1 && value.event.context_digest===attempt.body.context_digest && rrEqual(value.event.context,attempt.preview.context) && rrKeys(value.review,'status version') && value.review.version===value.event.version && value.review.status===(attempt.action==='acknowledge' ? 'reviewed_in_crm' : 'awaiting_review');
  } catch { return false; }
}

export function ReportReviewPanel({client,workspaceToken,task,profile,expected,memory,current,disabled=false,onChanged}) {
  const [observed,setObserved]=useState(null),[preview,setPreview]=useState(null),[notice,setNotice]=useState(''),[staleOK,setStaleOK]=useState(false),[,redraw]=useState(0);
  const life=useRef({ mounted:false, epoch:0, read:0 }), latest=useRef(null), trigger=useRef(null), heading=useRef(null);
  const signature=rrCanonical([workspaceToken,profile,task.id,task.version,task.status,expected,disabled]);
  if (!latest.current || latest.current.signature!==signature || latest.current.client!==client || latest.current.memory!==memory) { life.current.epoch++; latest.current={signature,client,memory,current,disabled}; }
  latest.current.current=current; latest.current.disabled=disabled;
  const epoch=life.current.epoch;
  const bindingKey=rrCanonical([workspaceToken,profile,task.id,expected]);
  const handlers=useRef(null);
  const valid=()=>life.current.mounted && life.current.epoch===epoch && client.current() && current() && latest.current.current() && !latest.current.disabled;
  const path=`/report-reviews/${expected.family}/${encodeURIComponent(expected.assignment_id)}/${encodeURIComponent(expected.report_id)}`;
  const observedNow=observed?.signature===signature && client.current() && current() ? observed.value : null;
  const previewNow=preview?.signature===signature && preview.epoch===epoch && client.current() && current() ? preview.value : null;
  async function read(forAction=false) {
    if (!valid() || (forAction && (memory.busy || memory.attempt))) return;
    const ticket=++life.current.read;
    life.current.preview=null;life.current.staleOK=false;setObserved(null);setPreview(null);setStaleOK(false);setNotice('Reading review status…');
    try {
      const value=await client.request(`${path}?workspace_token=${encodeURIComponent(workspaceToken)}`);
      if (!valid() || ticket!==life.current.read) return;
      if (!reportReviewPreview(value,expected) || value.identity.profile!==profile) throw Error('Unverified review');
      setObserved({signature,value});setNotice('');
      if(forAction){life.current.preview=value;setPreview({signature,epoch,value});}
    } catch { if(valid() && ticket===life.current.read){setObserved(null);setPreview(null);setNotice('Review status unavailable. Refresh to retry; no review state is assumed.');} }
  }
  useEffect(()=>{
    life.current.mounted=true;
    const update=()=>handlers.current?.update();
    memory.listeners.add(update);
    return()=>{memory.listeners.delete(update);life.current.mounted=false;life.current.epoch++;life.current.read++;};
  },[client,memory,signature]);
  function notifyChanged(){
    if(valid() && onChanged && !memory.busy && memory.receipt && memory.receiptBindingKey===bindingKey && memory.notifiedReceipt!==memory.receipt.event.id){
      memory.notifiedReceipt=memory.receipt.event.id;onChanged();
    }
  }
  handlers.current={update:()=>{if(valid()){redraw(n=>n+1);life.current.preview=null;setPreview(null);if(!memory.busy && !memory.attempt){void read();notifyChanged();}}}};
  useEffect(()=>{if(valid() && life.current.loaded!==epoch){life.current.loaded=epoch;void read();notifyChanged();}});
  // StrictMode effect replay invalidates prior callbacks, then renders fresh closures.
  useEffect(()=>{redraw(n=>n+1);},[client,memory,signature]);
  useEffect(()=>{if(previewNow)heading.current?.focus();},[previewNow]);
  function close(){if(!valid())return;life.current.preview=null;life.current.read++;life.current.staleOK=false;setPreview(null);setStaleOK(false);trigger.current?.focus();}
  async function write(retry=false) {
    if(!valid() || memory.busy)return;
    let attempt=memory.attempt;
    if(retry){if(!attempt || attempt.bindingKey!==bindingKey)return;}
    else {
      if(attempt || !previewNow || life.current.preview!==previewNow || (!previewNow.context.source_current && !life.current.staleOK))return;
      const action=previewNow.review.status==='reviewed_in_crm'?'revoke':'acknowledge';
      attempt={bindingKey,action,path:`${path}/${action}`,preview:rrClone(previewNow),body:{workspace_token:workspaceToken,idempotency_key:crypto.randomUUID(),context_digest:previewNow.context_digest,expected_review_version:previewNow.review.version,acknowledge_stale:life.current.staleOK===true}};
      memory.attempt=attempt;
    }
    memory.busy=true;rrPublish(memory);setPreview(null);setObserved(null);setNotice('Saving acknowledgement…');
    try {
      const value=await client.request(attempt.path,{method:'POST',body:rrClone(attempt.body)});
      if(!reportReviewReceipt(value,attempt))throw Error('Unverified receipt');
      // Retain only in the original scope, including when its panel unmounted.
      // This receipt is historical. Never project it as the current review state.
      memory.receipt=rrClone(value);memory.receiptBindingKey=attempt.bindingKey;memory.attempt=null;
      if(valid())setNotice('Acknowledgement recorded. Reading current review status…');
    } catch { if(valid())setNotice('Acknowledgement outcome unconfirmed. Only retry the exact attempt; do not create a replacement.'); }
    finally {memory.busy=false;rrPublish(memory);}
  }
  const button=(label,fn,props={})=>h('button',{type:'button',style:{minHeight:44},onClick:fn,disabled:disabled || memory.busy || !client.current(),...props},label);
  return h('section',{className:'hc-stack','aria-label':'Result acknowledgement',onKeyDown:e=>{if(e.key==='Escape' && previewNow){e.preventDefault();close();}}},
    h('div',{className:'hc-actions'},h('span',{role:'status'},memory.busy?'Saving acknowledgement…':observedNow?(observedNow.review.status==='reviewed_in_crm'?'Reviewed in CRM':'Not reviewed in CRM'):'Review status unavailable'),
      !memory.attempt && button(observedNow?.review.status==='reviewed_in_crm'?'Undo acknowledgement':'Mark result reviewed',()=>read(true),{ref:trigger,disabled:disabled || memory.busy || !observedNow || !client.current()}),
      button('Refresh review status',()=>read())),
    observedNow && !observedNow.context.source_current && h('p',{role:'status',className:'hc-notice'},`Source changed: ${observedNow.context.source_reason}. This historical result is not current; acknowledgement does not restore source freshness.`),
    memory.attempt && h('div',{className:'hc-notice'},h('p',null,'An acknowledgement attempt is unconfirmed. Its exact request is retained; no replacement is permitted.'),button('Retry exact acknowledgement',()=>write(true),{disabled:disabled || memory.busy || memory.attempt.bindingKey!==bindingKey || !client.current()})),
    previewNow && h('div',{className:'hc-notice hc-stack'},h('h4',{ref:heading,tabIndex:-1},previewNow.review.status==='reviewed_in_crm'?'Undo this acknowledgement?':'Mark this result reviewed?'),h('strong',null,`Agent reported: ${previewNow.outcome}`),h('p',{className:'hc-details'},previewNow.summary),h('p',null,'Records a desktop acknowledgement only. It does not verify host success, complete the task, apply a note or change scheduling. The human owner is not identified as the reviewer.'),
      !previewNow.context.source_current && h('label',{className:'hc-stack',style:{minHeight:44}},h('strong',{role:'alert'},`Source changed: ${previewNow.context.source_reason}. This historical result is not current.`),h('span',null,h('input',{type:'checkbox',checked:staleOK,'aria-label':'Acknowledge changed source',onChange:e=>{if(valid() && life.current.preview===previewNow){life.current.staleOK=e.target.checked;setStaleOK(e.target.checked);}}}),' I understand this acknowledgement concerns a historical result with changed or missing source records.')),
      button(previewNow.review.status==='reviewed_in_crm'?'Confirm undo acknowledgement':'Confirm mark reviewed',()=>write(),{disabled:disabled || memory.busy || (!previewNow.context.source_current && !staleOK)}),button('Cancel acknowledgement',close)),
    notice && h('p',{role:'status'},notice),
    observedNow && h('details',null,h('summary',null,'Acknowledgement history & technical details'),h('p',null,`${observedNow.review.history_total} acknowledgement events${observedNow.review.history_truncated?'; latest 50 shown':''}. Recorded by desktop; no authenticated person is claimed.`),h('ol',null,observedNow.review.history.map(event=>h('li',{key:event.id},`${event.action==='acknowledge'?'Reviewed in CRM':'Acknowledgement undone'} · ${event.created_at} · desktop`))),h('pre',null,JSON.stringify(observedNow.context,null,2))));
}
