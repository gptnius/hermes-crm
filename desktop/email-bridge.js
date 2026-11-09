import { createElement as h, useEffect, useRef, useState } from "react";

// Lifetime-owned memory survives contact remounts and route ABA, not browser storage.
export function emailBridgeMemory(owner) {
  return owner.emailBridgeMemory || (owner.emailBridgeMemory = { attempts: new Map(), pollers: new Map(), listeners: new Set(), receipts: new Map() });
}
const bridgeNotify = memory => { for (const listener of memory.listeners) listener(); };
export function bridgeValidStatus(v) {
  return !!v && Number.isSafeInteger(v.revision) && v.revision >= 0 && typeof v.enabled === 'boolean' &&
    typeof v.polling_enabled === 'boolean' && (v.mailbox === null || typeof v.mailbox === 'string') &&
    (v.account_namespace === null || typeof v.account_namespace === 'string') && (!v.enabled || (!!v.account_namespace && !!v.mailbox));
}
export function bridgeTerminal(v, kind) {
  if (!v || ['running', 'unknown'].includes(v.status)) return false;
  if (['cancelled','failed'].includes(v.status)) return true;
  if (kind === 'sync') return ['complete','partial','requires_resync','failed','cancelled'].includes(v.outcome?.status);
  return Number.isSafeInteger(v.revision) && (kind !== 'verify' || typeof v.account_namespace === 'string');
}
export function createBridgeSession({client, workspaceToken, memory, current = () => true}) {
  let alive = true;
  const active = () => alive && client.current() && current();
  const query = new URLSearchParams({workspace_token:workspaceToken});
  const safetyScope = JSON.stringify([workspaceToken,'safety-control']);
  const pending = () => memory.attempts.get(safetyScope) || memory.attempts.get(workspaceToken);
  const get = async path => { const value = await client.request(`/email-bridge/${path}${path.includes('?')?'&':'?'}${query}`); return active() ? value : null; };
  return { active, pending, get, close(){alive=false;},
    async status() {
      const status = await get('status');
      if (!active()) return null;
      if (!bridgeValidStatus(status)) throw Error('Local status unavailable.');
      for (const attemptScope of [workspaceToken,safetyScope]) {
        const attempt = memory.attempts.get(attemptScope);
        if (!attempt) continue;
        const receipt = await get(`operations/${encodeURIComponent(attempt.body.operation_key)}`);
        if (!active()) return null;
        if (memory.attempts.get(attemptScope) === attempt && bridgeTerminal(receipt, attempt.kind)) {
          memory.receipts?.set(workspaceToken, {kind:attempt.kind, result:receipt});
          memory.attempts.delete(attemptScope); bridgeNotify(memory);
        }
      }
      return status;
    },
    async submit(kind, status, values={}) {
      const previous = pending();
      const safety = kind==='control' && ['pause','disconnect','stop_polling'].includes(values.action) &&
        previous && ['verify','sync'].includes(previous.kind) && !memory.attempts.has(safetyScope);
      if (!active() || (previous && !safety) || !bridgeValidStatus(status)) return null;
      const attemptScope = safety ? safetyScope : workspaceToken;
      if (!['verify','sync','control','aliases'].includes(kind)) throw Error('Unsupported operation');
      const body = { ...values, workspace_token:workspaceToken, expected_revision:status.revision, operation_key:crypto.randomUUID() };
      if (kind === 'verify' || kind === 'sync') body.consent = true;
      const attempt = {kind, body:JSON.parse(JSON.stringify(body)), state:'running'};
      memory.attempts.set(attemptScope, attempt); bridgeNotify(memory);
      let dispatched=false;
      try {
        if(safety){
          const fresh=await get('status');
          if(!active()){memory.attempts.delete(attemptScope);bridgeNotify(memory);return null;}
          if(!bridgeValidStatus(fresh)||fresh.account_namespace!==status.account_namespace||fresh.mailbox!==status.mailbox)throw Error('Account changed');
          attempt.body.expected_revision=fresh.revision;
        }
        if(!active()){memory.attempts.delete(attemptScope);bridgeNotify(memory);return null;}
        dispatched=true;
        const result = await client.request(`/email-bridge/${kind}`,{method:'POST',body:attempt.body});
        if (!active() || memory.attempts.get(attemptScope) !== attempt) return null;
        if (!bridgeTerminal(result, kind)) throw Error('Unconfirmed receipt');
        memory.receipts?.set(workspaceToken, {kind, result});
        memory.attempts.delete(attemptScope); bridgeNotify(memory);
        return result;
      } catch {
        if(!dispatched){memory.attempts.delete(attemptScope);bridgeNotify(memory);throw Error('No action was sent. Refresh local history and review the current account again.');}
        if (memory.attempts.get(attemptScope) === attempt) { attempt.state='unknown'; bridgeNotify(memory); }
        throw Error('Outcome unknown. Refresh the recorded receipt; this request will not be resent. Sync is paused until resolved.');
      }
    },
  };
}

// One owner per selected workspace, shared across companion panes. There is no
// provider call on mount, and a generic enabled/connected flag is insufficient.
export function EmailBridgePolling({ctx,client,workspaceToken,memory}) {
  const [enabled,setEnabled]=useState(false),[revision,update]=useState(0);
  useEffect(()=>{const change=()=>update(n=>n+1);memory.listeners.add(change);return()=>memory.listeners.delete(change);},[memory]);
  useEffect(()=>{
    const session=createBridgeSession({client,workspaceToken,memory});
    session.get('status').then(status=>{if(session.active())setEnabled(bridgeValidStatus(status)&&status.polling_enabled===true&&status.enabled&&!!status.checkpoint&&!status.requires_resync&&!status.polling_blocked_reason&&session.pending()?.state!=='unknown'&&status.runtime?.available===true);}).catch(()=>{if(session.active())setEnabled(false);});
    return()=>session.close();
  },[client,workspaceToken,memory,revision]);
  useEffect(() => {
    if(!enabled)return;
    const session = createBridgeSession({client,workspaceToken,memory});
    let group=memory.pollers.get(workspaceToken);
    if(!group){
      group={sessions:new Set(),busy:false,stopped:false};
      memory.pollers.set(workspaceToken,group);
      const tick=async()=>{
        if(group.stopped||group.busy)return;
        const own=[...group.sessions].find(value=>value.active());
        if(!own)return;
        group.busy=true;
        try{
          const status=await own.status();
          if(!status||group.stopped||!own.active()||own.pending()||!status.enabled||status.polling_enabled!==true||
            !status.checkpoint||status.lease_state||status.requires_resync||status.polling_blocked_reason||status.runtime?.available!==true)return;
          await own.submit('sync',status,{mode:'incremental',trigger:'poll'});
        }catch{/* Retain the exact unknown request; never resend. */}
        finally{group.busy=false;}
      };
      group.stop=ctx.setInterval(tick,300000);
    }
    group.sessions.add(session);
    return()=>{
      session.close();group.sessions.delete(session);
      if(!group.sessions.size){group.stopped=true;group.stop();if(memory.pollers.get(workspaceToken)===group)memory.pollers.delete(workspaceToken);}
    };
  },[ctx,client,workspaceToken,memory,enabled]);
  return null;
}
const bridgeText = value => typeof value==='string' ? value.slice(0,2000) : 'Unavailable';
const bridgeLabel = value => bridgeText(value).replaceAll('_',' ');
const bridgeHeaders = (item,name) => (item.raw_headers || []).filter(pair=>Array.isArray(pair)&&String(pair[0]).toLowerCase()===name.toLowerCase()).map(pair=>bridgeText(pair[1])).join('; ') || 'Unavailable';
const bridgeDate = value => typeof value==='number'&&Number.isFinite(value)&&Number.isFinite(new Date(value).getTime()) ? new Date(value).toISOString().replace('T',' ').replace('.000Z',' UTC') : 'Unavailable';
const bridgeButton=(text,click,disabled=false,extra={})=>h('button',{type:'button',onClick:click,disabled,...extra},text);
export const bridgeCSS=`
.hermes-crm-native .hc-bridge{padding:20px;border:1px solid var(--hc-border);border-radius:4px;background:var(--hc-panel);color:var(--hc-ink);min-width:0;overflow-wrap:anywhere}
.hermes-crm-native .hc-bridge h3{margin:0;font-size:18px}.hermes-crm-native .hc-bridge p{font-size:13px;line-height:20px;margin:8px 0}
.hermes-crm-native .hc-bridge-actions{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.hermes-crm-native .hc-bridge summary{cursor:pointer;padding:10px 0;font-weight:600}
.hermes-crm-native .hc-bridge summary:focus-visible{outline:2px solid var(--hc-link);outline-offset:2px}.hermes-crm-native .hc-bridge-list{list-style:none;padding:0;margin:12px 0;display:grid;gap:8px}
.hermes-crm-native .hc-bridge-list>li,.hermes-crm-native .hc-bridge-review{border:1px solid var(--hc-border);border-radius:4px;padding:12px;background:var(--hc-bg)}
.hermes-crm-native .hc-bridge-review{display:grid;gap:12px}.hermes-crm-native .hc-bridge label{display:grid;gap:6px;font-size:13px}.hermes-crm-native .hc-bridge .hc-bridge-consent{display:flex;flex-direction:row;gap:8px;align-items:flex-start}.hermes-crm-native .hc-bridge input[type=checkbox]{width:16px;height:16px;flex-shrink:0}
.hermes-crm-native .hc-bridge small{display:block;color:var(--hc-secondary);line-height:18px}.hermes-crm-native .hc-bridge input,.hermes-crm-native .hc-bridge textarea{width:100%;box-sizing:border-box}.hermes-crm-native .hc-bridge dl{margin:8px 0;font-size:13px}.hermes-crm-native .hc-bridge dt{color:var(--hc-secondary)}.hermes-crm-native .hc-bridge dd{margin:0 0 8px;white-space:pre-wrap}
`;
export function EmailBridgePanel(props) {
  return h(BridgePanelView,{...props,key:JSON.stringify([props.routeKey,props.workspaceToken,props.contact?.id,props.contact?.version])});
}
export function EmailBridgeConnections(props) {
  return h(EmailBridgePanel, {...props, contact:null});
}
function BridgePanelView({client,workspaceToken,contact,memory,open,storageBackend,disabled=false}) {
  const [localReadFailed,setLocalReadFailed]=useState(false);
  const [view,setView]=useState(null),[notice,setNotice]=useState(''),[review,setReview]=useState(null),[approved,setApproved]=useState(false);
  const [mailbox,setMailbox]=useState(''),[ownAliases,setOwnAliases]=useState(''),[aliases,setAliases]=useState(''),[busy,setBusy]=useState(false),[page,setPage]=useState(0),[reviewPage,setReviewPage]=useState(0),[reviewRevision,setReviewRevision]=useState(null);
  const [operationGeneration,render]=useState(0), session=useRef(null),latest=useRef(null),approveRef=useRef(null),reviewRef=useRef(null),mailboxRef=useRef(null),returnRef=useRef(null),readSequence=useRef(0),actionSequence=useRef(0);
  latest.current={disabled,page,reviewPage};
  useEffect(()=>{const update=()=>render(n=>n+1);memory.listeners.add(update);return()=>memory.listeners.delete(update);},[memory]);
  useEffect(()=>{
    const own=createBridgeSession({client,workspaceToken,memory});session.current=own;
    return()=>{readSequence.current++;own.close();};
  },[client,workspaceToken,memory]);
  // Pagination invalidates only local reads, never the in-flight action session.
  useEffect(()=>{if(session.current?.active())load();},[client,workspaceToken,memory,page,reviewPage]);
  useEffect(()=>{if(review){reviewRef.current?.scrollIntoView?.({block:"nearest"});(review==='verify'?mailboxRef.current:approveRef.current)?.focus();}},[review]);
  useEffect(()=>{if(operationGeneration&&session.current?.active())load();},[operationGeneration]);
  const current=()=>session.current?.active()&&!latest.current.disabled;
  async function load(own=session.current) {
    const ticket=++readSequence.current;
    const selectedPage=latest.current.page, selectedReviewPage=latest.current.reviewPage;
    try {
      const status=await own.status();if(!status)return;
      const [history,unresolved]=contact?await Promise.all([own.get(`contacts/${encodeURIComponent(contact.id)}?limit=25&offset=${selectedPage*25}`),own.get(`unresolved?limit=25&offset=${selectedReviewPage*25}`)]):[{items:[],total:0},{items:[],total:0}];
      if(!own.active()||ticket!==readSequence.current)return;
      if(!Array.isArray(history?.items)||!Array.isArray(unresolved?.items)||!Number.isSafeInteger(history.total)||!Number.isSafeInteger(unresolved.total))throw Error();
      setLocalReadFailed(false);setNotice(previous=>previous==='Local email history is unavailable. No provider read was started. Pending requests remain locked.'?'':previous);setView({status,history,unresolved});
    }catch{if(own.active()&&ticket===readSequence.current){setLocalReadFailed(true);setNotice('Local email history is unavailable. No provider read was started. Pending requests remain locked.');}}
  }
  const status=view?.status,pending=session.current?.pending(),receipt=memory.receipts?.get(workspaceToken);
  const outcome=receipt?.result;
  const outcomeText=outcome?.status==='failed'?`Last ${bridgeLabel(receipt.kind)} action failed. No success was confirmed.`:outcome?.status==='cancelled'?`Last ${bridgeLabel(receipt.kind)} action cancelled.`:receipt?.kind==='verify'&&outcome?.account_namespace&&outcome.account_namespace===status?.account_namespace?'Verification succeeded: provider identity and profile checkpoint checked. No messages read.':null;
  const blocked=disabled||busy||!client.current()||!status||!!pending||!!status.lease_state;
  const safetyAvailable=(!!status?.lease_state||(!!pending&&['verify','sync'].includes(pending.kind)))&&!disabled&&client.current()&&!!status;
  const reviewBusy=busy&&!(safetyAvailable&&['pause','disconnect','stop_polling'].includes(review));
  const reviewBlocked=(blocked&&!(safetyAvailable&&['pause','disconnect','stop_polling'].includes(review)))||reviewRevision!==status?.revision;
  const storageKnown=['sqlite','postgresql','postgres'].includes(storageBackend);
  const destination=storageBackend==='sqlite'?'selected CRM SQLite database':['postgres','postgresql'].includes(storageBackend)?'selected CRM PostgreSQL database':'unconfirmed CRM backend';
  function choose(kind,event){if(!current())return;returnRef.current=event?.currentTarget;setReview(kind);setReviewRevision(status?.revision);setApproved(false);setNotice('');if(kind==='aliases')setAliases((view.history.explicit_aliases||[]).join('\n'));}
  function cancel(){setReview(null);setApproved(false);returnRef.current?.focus();}
  async function submit(event){
    event.preventDefault();if(reviewBlocked||!approved||!current())return;
    const own=session.current,kind=review,ticket=++actionSequence.current;const active=()=>own.active()&&ticket===actionSequence.current;setBusy(true);
    const split=text=>text.split(/[\n,]/).map(s=>s.trim()).filter(Boolean);
    try{
      let result;
      if(kind==='verify')result=await own.submit('verify',status,{own_mailbox:mailbox.trim(),own_aliases:split(ownAliases)});
      else if(['incremental','7days','30days'].includes(kind))result=await own.submit('sync',status,{mode:kind,trigger:'manual'});
      else if(kind==='aliases')result=await own.submit('aliases',status,{contact_id:contact.id,contact_version:contact.version,aliases:split(aliases)});
      else result=await own.submit('control',status,{action:kind,...(kind==='clear'?{confirm:true}:{})});
      if(result&&active()){cancel();setNotice(result.status==='failed'?'Action failed. No success was confirmed.':result.status==='cancelled'?'Action cancelled. No success was confirmed.':result.outcome?`Recorded read: ${bridgeLabel(result.outcome.status)}. Coverage is bounded; absence is not evidence of no correspondence.`:kind==='verify'?'Verification receipt recorded. Check the refreshed verified mailbox status above.':`Action recorded: ${bridgeLabel(kind)}. Local status refreshed.`);await load(own);}
    }catch(error){if(active())setNotice(error.message);}
    finally{if(active())setBusy(false);}
  }
  function action(text,kind,extraBlocked=false){return bridgeButton(text,e=>choose(kind,e),(blocked&&!(safetyAvailable&&['pause','disconnect','stop_polling'].includes(kind)))||extraBlocked);}
  const providerAction=review==='verify'||['incremental','7days','30days','start_polling'].includes(review);
  return h('section',{className:'hc-bridge','aria-label':contact?'Existing Hermes email history':'Gmail connection'},h('style',null,bridgeCSS),h('h3',null,contact?'Email history':'Gmail · existing Hermes connection'),
    h('p',{className:'hc-muted'},'Read-only metadata from your existing Hermes Gmail connection. No bodies, attachments, Bcc, sends, drafts or mailbox changes.'),
    h('p',{role:'status'},status?.mailbox?`Verified mailbox: ${bridgeText(status.mailbox)} · ${status.enabled?'Enabled':'Paused'}`:status?'Not verified · existing connection not in use':localReadFailed?'Local status unavailable · refresh to try again':'Loading local status…'),
    status&&h('small',null,`Sync while CRM is open: ${status.polling_enabled?'enabled, at least 5 minutes between checks':'off'}. ${status.lease_state?`Operation: ${bridgeLabel(status.lease_state)}.`:''}`),
    pending&&h('p',{role:'status'},`${pending.kind==='verify'?'Verification':'Operation'} ${pending.state==='running'?'in progress':pending.state}. Refresh the recorded receipt. No automatic resend; polling is paused.`),
    localReadFailed&&status&&h('p',{role:'status'},'Showing last known account status. Refresh failed; current state could not be checked.'),
    outcomeText&&h('p',{role:'status'},outcomeText),
    h('div',{className:'hc-bridge-actions'},bridgeButton(contact?'Refresh local history':'Refresh local status',()=>load(),disabled||!client.current()),
      action('Sync new metadata','incremental',!storageKnown||!status?.enabled||!status?.checkpoint||!!status?.requires_resync||!status?.runtime?.available)),
    review&&h('form',{className:'hc-bridge-review',ref:reviewRef,'aria-label':'Review Gmail bridge action',onSubmit:submit,onKeyDown:e=>{if(e.key==='Escape'&&!reviewBusy){e.preventDefault();cancel();}}},
      h('strong',null,`Review: ${bridgeLabel(review)}`),h('p',null,`Storage destination: ${destination}. Read the action below, then select the approval checkbox and confirm.`),
      reviewRevision!==status?.revision&&h('p',{role:'status'},'The account state changed. Cancel and review the action again.'),
      review==='verify'&&h('div',null,h('label',null,'Exact own mailbox',h('input',{type:'email',ref:mailboxRef,required:true,value:mailbox,disabled:reviewBusy,autoComplete:'off',onChange:e=>{setMailbox(e.target.value);setApproved(false);}})),h('label',null,'Own aliases, one per line (user supplied)',h('textarea',{value:ownAliases,disabled:reviewBusy,onChange:e=>{setOwnAliases(e.target.value);setApproved(false);}})),h('p',null,'Use the existing selected Hermes connection for provider account verification only. This does not authorize reading message history. No new sign-in or Google grant is created.')),
      review==='aliases'&&h('div',null,h('label',null,'Exact contact aliases, one per line',h('textarea',{value:aliases,disabled:reviewBusy,onChange:e=>{setAliases(e.target.value);setApproved(false);}})),h('p',null,`Saved alias record version: ${view.history.alias_record_version ?? 'none'}. Replace the saved aliases for this contact version ${contact.version}. Exact values only; no dot, plus-tag or local-part case folding. These are user supplied, not provider verified.`)),
      ['incremental','7days','30days','start_polling'].includes(review)&&h('p',null,`Read selected Subject, From, To, Cc, Date, labels, provider IDs and ordering timestamps for ${bridgeText(status?.mailbox)}. ${review==='start_polling'?'Repeat incremental metadata reads while CRM is open, at least every five minutes. No always-on service.':review==='incremental'?'Read new metadata from the saved checkpoint.':`Bounded read: last ${review==='7days'?7:30} days.`} Reads may examine unrelated metadata in memory. Store only matched or reviewable candidates in the ${destination}.`),
      providerAction&&h('p',null,'Existing Google permissions may be broader than these metadata requests. Header text is untrusted. An approved request can finish and save in this workspace after navigation; navigation does not cancel a dispatched provider read.'),
      ['pause','resume','disconnect','stop_polling','clear'].includes(review)&&h('p',null,review==='clear'?'Remove all retained bridge observations in this workspace and reset the checkpoint. Identity, audit receipts and backups may remain; Google mail and grant are unchanged.':review==='resume'?'Resume local use of this verified connection. This does not enable polling or read metadata by itself.':'Stop this local use. Previously retained metadata remains. This does not revoke the Google grant or recall provider requests already dispatched.'),
      h('label',{className:'hc-bridge-consent'},h('input',{type:'checkbox',ref:approveRef,checked:approved,disabled:reviewBusy,onChange:e=>setApproved(e.target.checked)}),'I approve this specific action and its stated storage destination.'),
      h('div',{className:'hc-bridge-actions'},h('button',{type:'submit',disabled:reviewBlocked||!approved},review==='verify'?'Confirm verification (no messages read)':'Confirm action'),bridgeButton('Cancel',cancel,reviewBusy))),
    status?.polling_blocked_reason&&status.polling_blocked_reason!=='resync_required'&&h('p',{role:'status'},`Sync paused: ${bridgeLabel(status.polling_blocked_reason)}. Refresh local status and resolve outstanding operations.`),
    status?.requires_resync&&h('p',{role:'status'},'The history checkpoint expired. Choose and approve a bounded 7-day or 30-day resync below. No silent reset.'),
    contact&&view&&h(BridgeObservationCards,{items:view.history.items,current,open,disabled}),contact&&view&&!view.history.items.length&&h('p',null,'No retained observations for this contact. This does not prove there is no correspondence.'),
    contact&&view&&h('div',{className:'hc-bridge-actions'},bridgeButton('Previous history',()=>setPage(n=>n-1),page===0||disabled),h('small',null,`${view.history.total} retained observations`),bridgeButton('Next history',()=>setPage(n=>n+1),(page+1)*25>=view.history.total||disabled)),
    h(contact?'details':'section',null,h(contact?'summary':'h4',null,'Account & sync settings'),h('p',null,`Storage: ${destination}. Metadata is ordinary CRM data, not protected notes. Backups may retain previously stored data.`),
      h('p',null,'The host must enable this optional bridge and configure its trusted existing connection. This panel does not sign in, create an account or request a new Google grant. Credentials remain outside CRM. Keep the selected connection unchanged while a read is running.'),
      status&&!status.runtime?.available&&h('p',null,'Bridge unavailable. Host configuration and installation checks are required before verification.'),
      status?.account_namespace&&h('p',null,'This workspace already has a verified binding. To change accounts, disconnect locally first, then verify the intended existing Hermes connection. Retained history stays until you explicitly clear it.'),
      !storageKnown&&h('p',null,'Actions unavailable: CRM storage destination is not confirmed.'),
      status?.mailbox&&h('p',null,`Own aliases (user supplied, not provider verified): ${(status.own_aliases||[]).join(', ')||'None'}`),
      h('div',{className:'hc-bridge-actions'},action('Verify existing connection','verify',!storageKnown||!status?.runtime?.available||!!status?.account_namespace),
        action('Read last 7 days','7days',!storageKnown||!status?.enabled||!status?.runtime?.available),action('Read last 30 days','30days',!storageKnown||!status?.enabled||!status?.runtime?.available),
        action(status?.polling_enabled?'Stop app-open sync':'Sync while CRM is open',status?.polling_enabled?'stop_polling':'start_polling',!status?.enabled||!storageKnown||!status?.checkpoint||!!status?.requires_resync),
        action(status?.enabled||safetyAvailable?'Pause sync':'Resume sync',status?.enabled||safetyAvailable?'pause':'resume',!status?.account_namespace&&!safetyAvailable),action('Disconnect locally','disconnect',!status?.account_namespace&&!safetyAvailable),action('Clear retained metadata','clear'),
        contact&&action('Edit contact email aliases','aliases',!Array.isArray(view?.history?.explicit_aliases)||view?.history?.contact_version!==contact.version)),
      h('p',null,'Disconnect and pause stop local use, not the Google grant. Disconnect retains metadata. Clear deletes retained observations in this workspace and resets its checkpoint; identity, audit receipts and backups may remain. Google messages are unaffected.')),
    contact&&view&&h('details',null,h('summary',null,`Needs review across workspace (${view.unresolved.total})`),h('p',null,'Ambiguous addresses stay unlinked for that address. Review candidates individually; other unambiguous participants may link to several Contacts.'),h(BridgeObservationCards,{items:view.unresolved.items,current,open,disabled}),h('div',{className:'hc-bridge-actions'},bridgeButton('Previous review',()=>setReviewPage(n=>n-1),reviewPage===0||disabled),bridgeButton('Next review',()=>setReviewPage(n=>n+1),(reviewPage+1)*25>=view.unresolved.total||disabled))),
    notice&&h('p',{role:'status'},notice));
}

export function BridgeObservationCards({items,current,open,disabled}){return h('ul',{className:'hc-bridge-list'},items.map(item=>h('li',{key:JSON.stringify([item.account_namespace,item.message_id])},
    h('strong',null,bridgeHeaders(item,'Subject')),h('small',null,`Header direction: ${bridgeLabel(item.current_match?.direction)} · ${bridgeLabel(item.last_observation?.status || item.status)} · Provider ordering date: ${bridgeDate(item.internal_date_ms)}`),
    Array.isArray(item.labels)&&item.labels.includes('SENT')&&h('small',null,'Observed in Gmail Sent · not proof of delivery'),
    Array.isArray(item.header_issues)&&item.header_issues.length>0&&h('p',null,`Header issues: ${item.header_issues.map(bridgeLabel).join(', ')}`),
    (item.needs_review||item.currently_linked===false)&&h('p',null,'Needs review · current identities may differ from the original observation.'),
    h('details',null,h('summary',null,'Participants & match evidence'),h('dl',null,['From','To','Cc'].map(name=>h('div',{key:name},h('dt',null,name),h('dd',null,bridgeHeaders(item,name))))),
      h('p',null,'Association basis: exact visible email address. Aliases are user supplied. Header direction and Sent labels do not prove delivery, reading or authenticated identity.'),
      (item.current_match?.participants||[]).map((p,index)=>h('div',{key:index},h('small',null,`${bridgeText(p.address)} · ${(p.roles||[]).join(', ')} · ${bridgeLabel(p.status)}`),
        (p.matches||[]).map(match=>bridgeButton(`${p.status==='ambiguous'?'Review candidate':'Contact'} ${match.contact_id}`,()=>{if(current())open('contacts',match.contact_id);},disabled,{key:match.contact_id})))),
      h('small',null,`Account namespace: ${bridgeText(item.account_namespace)} · Provider message ID: ${bridgeText(item.message_id)}`),h('small',null,'No Company association is inferred from a domain. Deals, Tasks and Events are not linked automatically.')))));}

export function CompanyEmailBridgePanel(props){
  return h(CompanyBridgeView,{...props,key:JSON.stringify([props.routeKey,props.workspaceToken,props.company.id,props.company.version])});
}
function CompanyBridgeView({client,workspaceToken,company,open,disabled=false}){
  const [page,setPage]=useState(null),[offset,setOffset]=useState(0),[revision,refresh]=useState(0),[error,setError]=useState('');
  const alive=useRef(false),sequence=useRef(0),latest=useRef(null);latest.current={disabled};
  useEffect(()=>{
    alive.current=true;let live=true;const ticket=++sequence.current;setPage(null);setError('');
    const query=new URLSearchParams({workspace_token:workspaceToken,limit:'25',offset:String(offset)});
    client.request(`/email-bridge/companies/${encodeURIComponent(company.id)}?${query}`).then(value=>{
      if(!live||!client.current()||ticket!==sequence.current)return;
      if(!Array.isArray(value?.items)||!Number.isSafeInteger(value.total)||value.total<0||value.association_basis!=='current_explicit_company_contacts')throw Error();
      setPage(value);
    }).catch(()=>{if(live&&client.current()&&ticket===sequence.current)setError('Company email history is unavailable. No provider read was started.');});
    return()=>{live=false;alive.current=false;};
  },[client,workspaceToken,company.id,company.version,offset,revision]);
  const current=()=>alive.current&&client.current()&&!latest.current.disabled;
  return h('section',{className:'hc-bridge','aria-label':'Company email history'},h('style',null,bridgeCSS),h('h3',null,'Email history'),
    h('p',null,'Through explicitly linked Contacts'),h('p',{className:'hc-muted'},'Current Contact–Company relationships group these retained observations. This is not direct provider evidence about the Company. Names and domains are never used to infer this association.'),
    h('p',null,'Read-only view. Manage the existing connection and workspace sync in Settings → Connections, or a Contact’s Account & sync settings.'),
    bridgeButton('Refresh Company email history',()=>{if(current())refresh(n=>n+1);},disabled||!client.current()),
    page&&h(BridgeObservationCards,{items:page.items,current,open,disabled}),
    page&&!page.items.length&&h('p',null,'No retained observations through currently linked Contacts. This does not prove there is no correspondence.'),
    page&&h('div',{className:'hc-bridge-actions'},bridgeButton('Previous Company history',()=>setOffset(n=>n-25),disabled||offset===0),h('small',null,`${page.total} retained observations`),bridgeButton('Next Company history',()=>setOffset(n=>n+25),disabled||offset+25>=page.total)),
    error&&h('p',{role:'status'},error));
}
