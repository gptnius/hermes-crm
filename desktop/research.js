import { createElement as h, useEffect, useRef, useState } from "react";

// Recovery is native-profile scoped by the caller, then partitioned by exact target.
// Only submitted additions/evidence and immutable receipts survive a panel lifetime.
// Before/after note text is held solely in the transient preview.
const researchStores = new WeakMap(), researchMeta = new WeakMap(), researchIds = new WeakMap();
let researchId = 0;
const researchObjectId = object => { if (!object) return 0; if (!researchIds.has(object)) researchIds.set(object, ++researchId); return researchIds.get(object); };
const researchVersion = value => Number.isSafeInteger(value) && value > 0;
const researchDigest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
async function researchHash(value) { return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value)))].map(byte=>byte.toString(16).padStart(2,'0')).join(''); }
const researchText = value => typeof value === 'string' && value.trim().length > 0;
export function researchSourceURL(value) {
  if (typeof value !== 'string' || value.length > 2048 || /[\s\x00-\x1f\x7f\\]/.test(value)) throw new Error('Enter one HTTPS source URL without credentials or whitespace.');
  let url; try { url = new URL(value); } catch { throw new Error('Enter one valid HTTPS source URL.'); }
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) throw new Error('Enter one HTTPS source URL without credentials.');
  let decoded;try{decoded=decodeURIComponent(value);}catch{throw new Error('Invalid HTTPS source encoding.');}
  if(/[\p{Cc}\p{Cf}\p{Cs}]/u.test(decoded))throw new Error('Control characters are not allowed in source references.');
  const secrets=new Set(['token','access_token','refresh_token','api_key','apikey','secret','password','signature','sig','x-amz-signature','x-amz-credential','x-goog-signature','key']);
  if([...url.searchParams,...new URLSearchParams(url.hash.slice(1))].some(([key])=>secrets.has(key.toLowerCase())))throw new Error('Remove secret-bearing parameters from source references.');
  return value;
}
export function researchEvidenceDraft(draft) {
  for (const [field, limit] of [['question',1000],['source_title',200]]) if (!researchText(draft[field]) || [...draft[field]].length > limit) throw new Error(`${field === 'question' ? 'Question' : 'Source title'} is required (maximum ${limit} characters).`);
  researchSourceURL(draft.source_url);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d{1,6})?)?(?:Z|[+-]\d\d:\d\d)$/.test(draft.observed_at) || !Number.isFinite(Date.parse(draft.observed_at))) throw new Error('Observation time requires an ISO timestamp with Z or an explicit offset.');
  if (draft.published_on && (!/^\d{4}-\d\d-\d\d$/.test(draft.published_on) || !Number.isFinite(Date.parse(draft.published_on)) || new Date(draft.published_on).toISOString().slice(0,10) !== draft.published_on)) throw new Error('Publication date must be a valid YYYY-MM-DD date, or blank when unknown.');
  const result = {question:draft.question,source_url:draft.source_url,source_title:draft.source_title,observed_at:draft.observed_at,published_on:draft.published_on || null};
  for (const field of ['claims','hypotheses']) {
    const values = Array.isArray(draft[field]) ? draft[field] : String(draft[field] || '').split('\n').filter(value=>value.trim());
    if ((field === 'claims' && !values.length) || values.length > 10 || values.some(value=>!researchText(value) || [...value].length > 2000)) throw new Error('Use at least one source claim and at most 10 entries per section, each 1–2,000 characters.');
    result[field] = values.slice();
  }
  if (new TextEncoder().encode(JSON.stringify(result)).length > 32768) throw new Error('Evidence packet exceeds 32 KiB.');
  return result;
}
function researchSameTarget(value, target) { return value?.target_kind === target.kind && value?.target_id === target.id; }
function researchEvidence(value, target, full = false) {
  if (!researchSameTarget(value,target) || !researchText(value.id) || !researchVersion(value.target_version) || !researchVersion(value.lifecycle_version) || !researchDigest(value.digest) || typeof value.recorded_at !== 'string' || !(value.archived_at === null || typeof value.archived_at === 'string')) throw new Error('Evidence identity could not be verified.');
  researchSourceURL(value.source_url);
  if(!researchText(value.source_title)||typeof value.observed_at!=='string'||!(value.published_on===null||typeof value.published_on==='string')||!Number.isSafeInteger(value.claims_count)||value.claims_count<1||value.claims_count>10||!Number.isSafeInteger(value.hypotheses_count)||value.hypotheses_count<0||value.hypotheses_count>10)throw new Error('Evidence metadata could not be verified.');
  if (full) { if(!Array.isArray(value.claims)||!Array.isArray(value.hypotheses)||value.claims.length!==value.claims_count||value.hypotheses.length!==value.hypotheses_count)throw new Error('Evidence claims could not be verified.');researchEvidenceDraft(value); }
  return value;
}
function researchProposal(value, target) {
  if (!researchSameTarget(value,target) || !researchText(value.id) || !researchText(value.evidence_id) || !researchDigest(value.evidence_digest) || !researchVersion(value.evidence_lifecycle_version) || !researchVersion(value.proposal_version) || !researchVersion(value.target_version) || !researchDigest(value.proposal_digest) || !researchDigest(value.before_hash) || !researchDigest(value.after_hash) || !['pending','applied','dismissed'].includes(value.status)) throw new Error('Proposal identity could not be verified.');
  return value;
}
export function confirmedResearchReceipt(path, data, value, target, expected = null) {
  try {
    if (expected && Object.entries(expected).some(([key,valueExpected])=>value?.[key]!==valueExpected)) return false;
    if (path === '/research/evidence') {
      researchEvidence(value,target);
      return value.target_version === data.target_version && value.lifecycle_version === 1 && value.archived_at === null && ['source_url','source_title','observed_at','published_on'].every(key=>value[key] === data[key]) && value.claims_count === data.claims.length && value.hypotheses_count === data.hypotheses.length;
    }
    if (path === '/research/proposals') {
      researchProposal(value,target);
      return value.proposal_version === 1 && value.status === 'pending' && ['evidence_id','evidence_digest','evidence_lifecycle_version','target_version','addition'].every(key=>value[key] === data[key]);
    }
    const parts = path.split('/').filter(Boolean).map(decodeURIComponent), action = parts[3];
    if (parts[1] === 'evidence' && ['archive','restore'].includes(action)) {
      researchEvidence(value,target);
      return value.id === parts[2] && value.lifecycle_version === data.lifecycle_version+1 && (action === 'archive' ? researchText(value.archived_at) : value.archived_at === null);
    }
    if (parts[1] === 'proposals' && ['apply','dismiss'].includes(action)) {
      return researchSameTarget(value,target) && value.proposal_id === parts[2] && value.proposal_digest === data.proposal_digest && value.proposal_version === data.proposal_version+1 && value.status === (action==='apply'?'applied':'dismissed') && researchText(value.actor) && researchText(value.recorded_at) && researchText(value.evidence_id) && researchDigest(value.evidence_digest) && researchVersion(value.evidence_lifecycle_version) && researchVersion(value.target_version) && researchDigest(value.before_hash) && researchDigest(value.after_hash) && (action!=='apply' || (['target_version','before_hash','after_hash'].every(key=>value[key]===data[key]) && researchVersion(value.applied_target_version) && value.applied_target_version===data.target_version+1));
    }
  } catch { return false; }
  return false;
}
function researchRetainedReceipt(path,value) {
  // Never retain arbitrary response fields, embedded objects or before/after Notes.
  const keys=path.startsWith('/research/evidence') ? ['id','target_kind','target_id','target_version','digest','lifecycle_version','archived_at','recorded_at','recorded_actor','source_url','source_title','observed_at','published_on','claims_count','hypotheses_count'] : path==='/research/proposals' ? ['id','target_kind','target_id','target_version','evidence_id','evidence_digest','evidence_lifecycle_version','addition','proposal_version','status','before_hash','after_hash','proposal_digest','created_at','created_actor'] : ['proposal_id','proposal_digest','proposal_version','evidence_id','evidence_digest','evidence_lifecycle_version','target_kind','target_id','target_version','before_hash','after_hash','status','actor','recorded_at','applied_target_version'];
  return Object.fromEntries(keys.filter(key=>Object.hasOwn(value,key)&&(['string','number','boolean'].includes(typeof value[key])||value[key]===null)).map(key=>[key,value[key]]));
}
export function researchSession(client, workspaceToken, target, current = () => true, operationStore = null) {
  const store = operationStore || researchStores.get(client) || new Map();
  if (!operationStore) researchStores.set(client,store);
  if (!researchMeta.has(store)) researchMeta.set(store,new Map());
  const scope = JSON.stringify([workspaceToken,target.kind,target.id]), metadata = researchMeta.get(store);
  if (!metadata.has(scope)) metadata.set(scope,{epoch:0,draft:null,rejection:null,receipt:null,listeners:new Set()});
  const meta = metadata.get(scope);
  let alive = true, revoked = false, generation = 0, review = null, evidence = null, record = null;
  const valid = () => { if (!alive || revoked) return false; if (!client.current() || !current()) { revoked=true; review=null; evidence=null; record=null; return false; } return researchText(workspaceToken) && ['contacts','companies'].includes(target.kind) && researchText(target.id); };
  const notify = () => { meta.epoch++; review=null; evidence=null; record=null; for (const fn of meta.listeners) { try { fn(); } catch {} } };
  const invalidate = () => { generation++; review=null; evidence=null; record=null; };
  async function read(path, params = {}) {
    if (!valid()) return null;
    const ticket=generation, epoch=meta.epoch;
    const value=await client.request(`${path}?${new URLSearchParams({...params,workspace_token:workspaceToken})}`);
    return valid() && ticket===generation && epoch===meta.epoch ? value : null;
  }
  async function perform(attempt, recover = false) {
    if (!valid() || attempt.state==='running') return null;
    attempt.state='running'; notify();
    const ticket=generation, body=JSON.parse(attempt.payload);
    let value;
    try {
      if (recover) {
        const result=await client.request(`/research/operations/${encodeURIComponent(body.idempotency_key)}?${new URLSearchParams({workspace_token:workspaceToken})}`);
        if (result?.state==='unknown') { attempt.state='unknown'; notify(); return valid() && ticket===generation ? {unknown:true} : null; }
        if (result?.state!=='committed') throw new Error('Malformed operation state');
        value=result.receipt;
      } else value=await client.request(attempt.path,{method:'POST',body});
      if (!confirmedResearchReceipt(attempt.path,body.data,value,target,attempt.expected)) throw new Error('Unconfirmed receipt');
      value=researchRetainedReceipt(attempt.path,value);
    } catch (error) {
      if (store.get(scope)!==attempt) return null;
      const status=Number(error.status ?? error.statusCode);
      if (!recover && [400,404,409,422].includes(status)) {
        store.delete(scope); meta.rejection='Request rejected. Your draft is retained. Refresh the record and review again before creating a corrected request.'; notify();
      } else { attempt.state='unknown'; notify(); }
      if (valid() && ticket===generation) throw new Error(meta.rejection || 'Outcome unknown. Check the original operation or replay the exact request. No new writes are allowed.');
      return null;
    }
    if (store.get(scope)===attempt) { store.delete(scope); meta.receipt=Object.freeze(JSON.parse(JSON.stringify(value))); meta.draft=null; meta.rejection=null; notify(); }
    return valid() && ticket===generation ? value : null;
  }
  function write(path,data,expected = null) {
    if (!valid() || store.has(scope)) return Promise.resolve(null);
    const attempt={state:'ready'};
    Object.defineProperties(attempt,{expected:{value:expected ? Object.freeze({...expected}) : null,enumerable:true},path:{value:path,enumerable:true},payload:{value:JSON.stringify({workspace_token:workspaceToken,idempotency_key:crypto.randomUUID(),data}),enumerable:true}});
    Object.seal(attempt); store.set(scope,attempt); meta.rejection=null;
    return perform(attempt);
  }
  return {
    valid, activate(){alive=true;invalidate();},close(){alive=false;invalidate();},invalidate,
    subscribe(fn){meta.listeners.add(fn);return()=>meta.listeners.delete(fn);},pending:()=>store.get(scope),snapshot:()=>({...meta}),
    saveDraft(draft){if(valid()&&!store.has(scope))meta.draft=JSON.parse(JSON.stringify(draft));},discardDraft(){if(!store.has(scope)){meta.draft=null;meta.rejection=null;}},
    async load(offset = 0) {
      invalidate(); const values=await Promise.all([read(`/${target.kind}/${encodeURIComponent(target.id)}`),read('/research/evidence',{target_kind:target.kind,target_id:target.id,limit:25,offset}),read('/research/proposals',{target_kind:target.kind,target_id:target.id,limit:25,offset})]);
      if (values.some(value=>!value)) return null;
      const row=values[0].contact || values[0].company || values[0];
      if (row.id!==target.id || !researchVersion(row.version)) throw new Error('Current record identity could not be verified.');
      for (let i=1;i<3;i++) {const page=values[i]; if(!Array.isArray(page.items)||!Number.isSafeInteger(page.total)||page.total<0)throw new Error('Invalid research list.');for(const item of page.items)(i===1?researchEvidence:researchProposal)(item,target);}
      record=Object.freeze({id:row.id,version:row.version,name:row.name,archived_at:row.archived_at});
      return {record,evidence:values[1],proposals:values[2]};
    },
    async evidence(id){ review=null; const value=await read(`/research/evidence/${encodeURIComponent(id)}`);if(!value)return null;researchEvidence(value,target,true);if(value.id!==id)throw new Error('Wrong evidence identity.');evidence=Object.freeze(value);return evidence; },
    async preview(id){review=null;const ticket=generation,epoch=meta.epoch;const value=await read(`/research/proposals/${encodeURIComponent(id)}/preview`);if(!value)return null;researchProposal(value,target);if(value.id!==id || typeof value.stale!=='boolean'||!researchText(value.addition)||[...value.addition].length>10000)throw new Error('Invalid proposal preview.');if(!value.stale && value.status==='pending') {if(typeof value.current_notes!=='string'||typeof value.proposed_notes!=='string'||!researchText(value.addition)||value.proposed_notes!==value.current_notes+(value.current_notes?'\n\n':'')+value.addition||[...value.proposed_notes].length>10000)throw new Error('Exact note preview could not be verified.');const hashes=await Promise.all([researchHash(value.current_notes),researchHash(value.proposed_notes)]);if(!valid()||ticket!==generation||epoch!==meta.epoch)return null;if(hashes[0]!==value.before_hash||hashes[1]!==value.after_hash)throw new Error('Note preview hashes did not match. Refresh before reviewing.');}review=Object.freeze(value);return review;},
    createEvidence(draft){if(!record || record.archived_at)return Promise.resolve(null);const data=researchEvidenceDraft(draft);return write('/research/evidence',{target_kind:target.kind,target_id:target.id,target_version:record.version,...data});},
    propose(selected,addition){if(!record||record.archived_at||!evidence||selected!==evidence||evidence.archived_at)return Promise.resolve(null);if(!researchText(addition)||[...addition].length>10000)throw new Error('Addition must contain 1–10,000 characters.');return write('/research/proposals',{evidence_id:evidence.id,evidence_digest:evidence.digest,evidence_lifecycle_version:evidence.lifecycle_version,target_version:record.version,addition});},
    lifecycle(selected){if(!evidence||selected!==evidence)return Promise.resolve(null);return write(`/research/evidence/${encodeURIComponent(evidence.id)}/${evidence.archived_at?'restore':'archive'}`,{lifecycle_version:evidence.lifecycle_version},{digest:evidence.digest,target_version:evidence.target_version});},
    apply(selected){if(!review||selected!==review||review.stale||review.status!=='pending'||!evidence||evidence.id!==review.evidence_id||evidence.digest!==review.evidence_digest||evidence.lifecycle_version!==review.evidence_lifecycle_version||evidence.archived_at)return Promise.resolve(null);return write(`/research/proposals/${encodeURIComponent(review.id)}/apply`,Object.fromEntries(['proposal_version','proposal_digest','target_version','before_hash','after_hash'].map(key=>[key,review[key]])),Object.fromEntries(['evidence_id','evidence_digest','evidence_lifecycle_version'].map(key=>[key,review[key]])));},
    dismiss(selected){if(!review||selected!==review||review.status!=='pending')return Promise.resolve(null);return write(`/research/proposals/${encodeURIComponent(review.id)}/dismiss`,{proposal_version:review.proposal_version,proposal_digest:review.proposal_digest},Object.fromEntries(['evidence_id','evidence_digest','evidence_lifecycle_version','target_version','before_hash','after_hash'].map(key=>[key,review[key]])));},
    recover(){const attempt=store.get(scope);return valid()&&attempt?.state==='unknown'?perform(attempt,true):Promise.resolve(null);},
    retry(){const attempt=store.get(scope);return valid()&&attempt?.state==='unknown'?perform(attempt):Promise.resolve(null);},
  };
}
const researchBlank = () => ({question:'',source_url:'',source_title:'',observed_at:'',published_on:'',claims:'',hypotheses:''});
export function ResearchPanel(props) {
  return h(ResearchView,{...props,key:JSON.stringify([researchObjectId(props.client),researchObjectId(props.operationStore),props.workspaceToken,props.target.kind,props.target.id,props.target.version])});
}
function ResearchView({Drawer,client,workspaceToken,target,current=()=>true,operationStore,cancel,returnFocus}) {
  const currentRef=useRef(current);currentRef.current=current;
  const sessionRef=useRef(null);if(!sessionRef.current)sessionRef.current=researchSession(client,workspaceToken,target,()=>currentRef.current(),operationStore);
  const session=sessionRef.current, mounted=useRef(false), lock=useRef(false), uiEpoch=useRef(0);
  const renderToken={}, latestRender=useRef(renderToken);latestRender.current=renderToken;
  const handlerCurrent=()=>latestRender.current===renderToken;
  const [view,setView]=useState(null),[selected,setSelected]=useState(null),[preview,setPreview]=useState(null),[source,setSource]=useState(null);
  const [draft,setDraft]=useState(()=>session.snapshot().draft),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[discard,setDiscard]=useState(false),[offset,setOffset]=useState(0),[,render]=useState(0);
  const active=()=>mounted.current&&session.valid();
  const pending=session.pending(), blocked=busy||!!pending||!active();
  function clearReview(){setSelected(null);setPreview(null);setSource(null);}
  async function run(fn){if(!active()||lock.current||!handlerCurrent())return;lock.current=true;const epoch=uiEpoch.current;setBusy(true);setError('');try{const result=await fn();return active()&&epoch===uiEpoch.current?result:null;}catch(e){if(active()&&epoch===uiEpoch.current)setError(e.message);}finally{if(epoch===uiEpoch.current){lock.current=false;if(active())setBusy(false);}}}
  async function load(next=offset){clearReview();const result=await session.load(next);if(active()&&result){setView(result);setOffset(next);}return result;}
  function edit(next){if(!active()||session.pending()||!handlerCurrent())return;setDraft(next);session.saveDraft(next);setDiscard(false);}
  function close(){if(!mounted.current||!handlerCurrent())return;if(!active())return cancel();if(draft&&!session.pending()){setDiscard(true);return;}session.close();uiEpoch.current++;cancel();}
  async function mutate(fn){const result=await fn();if(!active())return;if(result?.unknown){setNotice('No committed receipt found. This does not prove nonexecution. You may replay only the original request.');return;}if(result){setDraft(null);clearReview();setNotice('Operation confirmed. Receipts are historical, not proof that current notes remain unchanged. Refresh record lists after closing.');await load();}}
  useEffect(()=>{mounted.current=true;session.activate();const unsub=session.subscribe(()=>{if(active()){clearReview();setDraft(session.snapshot().draft);render(n=>n+1);if(session.snapshot().rejection){setError(session.snapshot().rejection);setView(null);}}});void run(()=>load(0));return()=>{mounted.current=false;uiEpoch.current++;lock.current=false;session.close();unsub();};},[session]);
  const button=(text,fn,disabled=blocked,primary=false)=>h('button',{key:text,type:'button',disabled,className:primary?'hc-primary':undefined,onClick:()=>{if(!active()||lock.current||disabled)return;return run(fn);}},text);
  const plain=(title,text)=>h('section',{className:'hc-card'},h('h4',null,title),h('p',{className:'hc-details',style:{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}},text));
  const evidenceView=value=>h('section',{className:'hc-stack'},h('h3',null,value.source_title),h('p',null,`Evidence ${value.id} · Lifecycle ${value.lifecycle_version}${value.archived_at?' · Archived':' · Active'}`),h('p',null,`Captured record version ${value.target_version}`),plain('Question',value.question),h('p',null,'Supplied HTTPS URL, not verified public or accurate. Private or signed links may expose access tokens. Nothing is fetched.'),h('a',{tabIndex:0,href:researchSourceURL(value.source_url),target:'_blank',rel:'noopener noreferrer',referrerPolicy:'no-referrer'},value.source_url),h('p',null,`Observed (supplied): ${value.observed_at}`),h('p',null,`Published (supplied): ${value.published_on || 'Unknown'}`),h('p',null,`Recorded by server: ${value.recorded_at} · Channel: ${value.recorded_actor || 'Not supplied'} (not a verified person)`),plain('Source claims',value.claims.join('\n\n')||'None supplied'),plain('Hypotheses',value.hypotheses.join('\n\n')||'None supplied'));
  return h(Drawer,{title:'Research evidence',subtitle:`${target.kind==='companies'?'Company':'Contact'} · ${target.name || target.id} · ${target.id}`,busy:false,cancel:close,returnFocus,closeLabel:'Close research'},h('div',{className:'hc-protection-body hc-stack'},
    h('p',null,`Exact record: ${target.kind}/${target.id} · ${view?`Current version ${view.record.version}`:'Refresh required'}`),
    h('p',{className:'hc-muted'},'Save supplied evidence, then review a separate note proposal. No research, source fetching, sync, outreach or automatic application. Claims and hypotheses are untrusted plain text. Applying changes ordinary Notes and last edit only, not last contact or task completion.'),
    error&&h('p',{role:'alert'},error),notice&&h('p',{role:'status'},notice),
    session.snapshot().receipt&&h('p',{className:'hc-muted'},`Historical operation: ${session.snapshot().receipt.status || 'evidence saved'} · ${session.snapshot().receipt.proposal_id || session.snapshot().receipt.id}`),
    pending&&h('section',{className:'hc-notice',role:'status'},h('p',null,pending.state==='running'?'Request in progress. Closing retains the original operation.':'Outcome unknown. New writes are locked. Closing retains the original request and key.'),button('Check original operation',()=>mutate(()=>session.recover()),busy||pending.state!=='unknown'),button('Replay exact original request',()=>mutate(()=>session.retry()),busy||pending.state!=='unknown')),
    discard&&h('section',{role:'alert'},h('p',null,'Discard this unsent draft and close?'),button('Keep editing',()=>setDiscard(false),busy),button('Discard draft and close',()=>{session.discardDraft();session.close();uiEpoch.current++;cancel();},busy)),
    button('Refresh research',()=>load(),blocked),
    !draft&&button('Add evidence',()=>{edit({type:'evidence',values:researchBlank()});clearReview();},blocked||!view||!!view.record.archived_at,true),
    draft?.type==='evidence'&&h('form',{onSubmit:e=>{e.preventDefault();if(!blocked&&view)void run(()=>mutate(()=>session.createEvidence(draft.values)));},className:'hc-protection-controls'},h('h3',null,'Add supplied evidence'),h('p',null,'One source per immutable packet. Corrections require a new packet. Source claims and hypotheses: one entry per line, up to 10 each. Observation time is supplied by you; server recorded time is separate.'),Object.entries({question:'Question',source_url:'HTTPS source URL',source_title:'Source title',observed_at:'Observed at (ISO timestamp with offset)',published_on:'Publication date (optional YYYY-MM-DD)',claims:'Source claims',hypotheses:'Hypotheses'}).map(([field,caption])=>h('label',{key:field},caption,h(['claims','hypotheses','question'].includes(field)?'textarea':'input',{name:field,value:draft.values[field],disabled:blocked,maxLength:{question:1000,source_url:2048,source_title:200,observed_at:40,published_on:10}[field],onChange:e=>edit({...draft,values:{...draft.values,[field]:e.target.value}})}))),button('Use current time as supplied observation',()=>edit({...draft,values:{...draft.values,observed_at:new Date().toISOString()}}),blocked),h('p',{className:'hc-muted'},draft.values.observed_at && Number.isFinite(Date.parse(draft.values.observed_at)) ? `Observation preview (UTC): ${new Intl.DateTimeFormat('en',{timeZone:'UTC',dateStyle:'full',timeStyle:'long'}).format(new Date(draft.values.observed_at))}. The supplied timestamp and offset are preserved.` : 'Enter an ISO timestamp such as 2026-11-08T14:30:00+00:00, or explicitly select the current time. This is your observation claim, not the publication date.'),h('button',{type:'submit',disabled:blocked||!view,className:'hc-primary'},'Save supplied evidence')),
    draft?.type==='addition'&&h('section',{className:'hc-protection-controls'},!selected&&button('Review draft evidence',async()=>{const result=await session.evidence(draft.evidence_id);if(active())setSelected(result);},blocked||!view),h('h3',null,'Prepare a separate note proposal'),h('p',null,'Preserves whitespace and appends two newlines after nonempty existing Notes. Nothing is applied yet. A total above 10,000 characters is rejected, never truncated.'),h('label',null,'Exact addition',h('textarea',{name:'addition',value:draft.addition,disabled:blocked,maxLength:10000,onChange:e=>edit({...draft,addition:e.target.value})})),button('Prepare note proposal',()=>mutate(()=>session.propose(selected,draft.addition)),blocked||!selected||!view,true)),
    draft&&button('Cancel draft',()=>{session.discardDraft();setDraft(null);clearReview();return load();},blocked),
    !draft&&view&&h('section',null,h('h3',null,`Evidence · ${view.evidence.total}`),view.evidence.items.map(item=>button(`${item.source_title} · ${item.archived_at?'Archived':'Active'} · ${item.id}`,async()=>{setPreview(null);setSource(null);const result=await session.evidence(item.id);if(active())setSelected(result);},blocked)),h('h3',null,`Note proposals · ${view.proposals.total}`),view.proposals.items.map(item=>button(`${item.status}${item.stale ? ' · stale' : ''} · ${item.id}`,async()=>{setSelected(null);setSource(null);const result=await session.preview(item.id);if(!active()||!result)return;const ev=await session.evidence(result.evidence_id);if(!active()||!ev)return;/* Evidence reads invalidate older proposal review. Read preview last. */const fresh=await session.preview(item.id);if(active()&&fresh){if(!fresh.stale && fresh.status==='pending' && (ev.id!==fresh.evidence_id||ev.digest!==fresh.evidence_digest||ev.lifecycle_version!==fresh.evidence_lifecycle_version||ev.archived_at))throw new Error('Evidence no longer matches this proposal. Refresh and review again.');setSource(ev);setPreview(fresh);}},blocked)),button('Previous research page',()=>load(Math.max(0,offset-25)),blocked||offset===0),button('Next research page',()=>load(offset+25),blocked||offset+25>=Math.max(view.evidence.total,view.proposals.total))),
    selected&&evidenceView(selected),selected&&!draft&&h('div',{className:'hc-actions'},h('p',null,'Archive keeps this immutable packet. Archive and restore both change its lifecycle version and invalidate older pending reviews.'),button(selected.archived_at?'Restore evidence':'Archive evidence (reversible)',()=>mutate(()=>session.lifecycle(selected))),button('Prepare addition',()=>edit({type:'addition',addition:'',evidence_id:selected.id}),blocked||!!selected.archived_at||!view||!!view.record.archived_at)),
    preview&&h('section',{className:'hc-stack'},h('h3',null,'Review exact note proposal'),h('p',null,`Proposal ${preview.id} · ${preview.status} · Version ${preview.proposal_version} · Record version ${preview.target_version} · Created via ${preview.created_actor || 'unspecified channel'} (not a verified person)`),source&&evidenceView(source),preview.stale&&h('p',{role:'alert'},`Stale: ${preview.stale_reason || 'Record or evidence changed'}. No current note diff is available. Prepare a new proposal after reviewing current evidence and Notes.`),plain('Exact proposed addition',preview.addition),!preview.stale&&preview.status==='pending'&&h('div',null,plain(`Current Notes · ${[...preview.current_notes].length} characters`,preview.current_notes||'(empty)'),plain(`Proposed Notes · ${[...preview.proposed_notes].length}/10,000 characters`,preview.proposed_notes),h('p',null,'Check every claim, source and hypothesis before applying. This is ordinary plaintext CRM Notes, not a protected note. No automatic rebase. This review action records the UI adapter, not a verified human identity.'),button('Apply exact addition to Notes',()=>mutate(()=>session.apply(preview)),blocked,true)),preview.status==='pending'&&button('Dismiss proposal',()=>mutate(()=>session.dismiss(preview))))));
}
