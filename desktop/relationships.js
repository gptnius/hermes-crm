import { createElement as h, useEffect, useRef, useState } from "react";
// BEGIN GENERATED RELATIONSHIP TIME
// Shared, dependency-free wall-time conversion. Never use the host's implicit zone.
function relZone(zone) {
  if (typeof zone !== 'string' || !zone.trim() || /^[+-]/.test(zone)) throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.');
  try { return new Intl.DateTimeFormat('en-US', {timeZone: zone}).resolvedOptions().timeZone; }
  catch { throw new Error('Choose a valid IANA timezone, such as America/New_York or UTC.'); }
}
function relWall(instant, zone) {
  relZone(zone);
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone: zone, year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'}).formatToParts(new Date(instant));
  const p = Object.fromEntries(parts.map(p => [p.type,p.value]));
  return `${p.year.padStart(4,'0')}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}
function relInstant(value) {
  const text = String(value || '').trim();
  const m = /^(\d{4}-\d\d-\d\d)T(\d\d):(\d\d)(?::(\d\d)(?:\.(\d{1,6}))?)?(Z|[+-](\d\d):(\d\d))$/.exec(text);
  if (!m || +m[2]>23 || +m[3]>59 || +(m[4]||0)>59 || +(m[7]||0)>23 || +(m[8]||0)>59 || !Number.isFinite(Date.parse(text))) throw new Error('Enter a valid date and time with an explicit offset.');
  const date = new Date(m[1]+'T00:00:00Z');
  if (date.toISOString().slice(0,10)!==m[1]) throw new Error('Enter a valid calendar date.');
  return text;
}
function relMicros(value) {
  relInstant(value);
  return BigInt(Math.floor(Date.parse(value)/1000))*1000000n + BigInt((value.match(/\.(\d+)/)?.[1] || '').padEnd(6,'0'));
}
function relCandidates(wall, zone) {
  relZone(zone);
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?$/.test(wall)) throw new Error('Enter both a date and a time.');
  const normalized = wall.length === 16 ? wall+':00' : wall;
  relInstant(normalized+'Z');
  // Restrict interactive editing to a tested modern timezone-data range.
  const year = +wall.slice(0,4);
  if (year < 1900 || year > 2100) throw new Error('Choose a year from 1900 through 2100.');
  const base = Date.parse(normalized+'Z'), offsets = new Set();
  // Obtain offsets around the target day, including both sides of DST and date-line shifts.
  for (let hour=-48; hour<=48; hour+=3) {
    const time = base+hour*3600000;
    offsets.add(Date.parse(relWall(time,zone)+'Z')-time);
  }
  return [...offsets].map(offset=>base-offset).filter(time=>relWall(time,zone)===normalized).sort((a,b)=>a-b).map(time=>new Date(time).toISOString());
}
function relUnchanged(wall, zone, original, originalZone, choice = '') {
  return !choice && !!original && zone===originalZone && relWall(original,zone)===(wall.length===16 ? wall+':00' : wall);
}
function relEditorCandidates(wall, zone, original = '', originalZone = zone, choice = '') {
  // Existing precise instants may predate or exceed the interactive editing range.
  // They are already unambiguous and must not block unrelated record edits.
  if ((+wall.slice(0,4)<1900 || +wall.slice(0,4)>2100) && relUnchanged(wall,zone,original,originalZone,choice)) return [];
  return relCandidates(wall,zone);
}
function relResolve(wall, zone, original = '', originalZone = zone, choice = '') {
  relZone(zone);
  // Preserve exact offset, seconds and microseconds even if the control normalized :00.
  if (relUnchanged(wall,zone,original,originalZone,choice)) return relInstant(original);
  const candidates=relCandidates(wall,zone);
  if (!candidates.length) throw new Error('This local time does not exist in this timezone. Choose another time.');
  if (candidates.length>1 && !candidates.includes(choice)) throw new Error('This local time occurs twice. Choose the intended occurrence.');
  return candidates.length===1 ? candidates[0] : choice;
}
function relReadable(value, zone = 'UTC') {
  if (!value) return 'Not recorded';
  try { relInstant(value); relZone(zone); return new Intl.DateTimeFormat('en', {timeZone:zone, year:'numeric',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',second:'2-digit',timeZoneName:'short'}).format(new Date(value)); }
  catch { return String(value); }
}
// END GENERATED RELATIONSHIP TIME

// Retained across panel navigation so an uncertain write cannot become a new intent.
const relationshipAttempts = new WeakMap();
const relationshipListeners = new WeakMap();
// A receipt confirms only the captured operation and exact identities, never a
// merely record-shaped object. Invalid receipts keep the original retry key.
export function confirmedRelationshipReceipt(path, method, body, result) {
  const version = value => Number.isSafeInteger(value) && value > 0;
  const id = value => typeof value === 'string' && value.trim().length > 0;
  const record = value => !!value && id(value.id) && version(value.version);
  const atLeast = (actual, expected) => version(actual) && (!version(expected) || actual >= expected);
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  if (!result || typeof result !== 'object') return false;
  if (parts[0] === 'relationship-contacts' && parts.length === 1 && method === 'POST') {
    const contact = result.contact, link = result.company_link;
    return record(contact) && !!link && link.contact_id === contact.id && link.contact_version === contact.version &&
      Object.hasOwn(link, 'company_id') && link.company_id === body.company_id &&
      link.company_link_basis === (body.company_id === null ? 'unlinked' : 'explicit');
  }
  if (parts[0] === 'contacts' && parts.length === 3 && parts[2] === 'company' && method === 'PUT')
    return result.contact_id === parts[1] && atLeast(result.contact_version, body.expected_contact_version) && Object.hasOwn(result, 'company_id') && result.company_id === body.company_id;
  if (parts[0] === 'events' && parts.length === 3 && parts[2] === 'tasks' && method === 'POST')
    return record(result.task) && (!Object.hasOwn(body.data || {}, 'owner_label') || result.task.owner_label === body.data.owner_label) && result.task_id === result.task.id && record(result.event) && result.event.id === parts[1] && result.event_id === parts[1] && atLeast(result.event.version, body.expected_version);
  if (parts[0] === 'tasks' && parts[2] === 'event') {
    if (!record(result.task) || result.task_id !== parts[1] || result.task.id !== parts[1] || !atLeast(result.task.version, body.expected_task_version)) return false;
    if (parts.length === 4 && parts[3] === 'unlink' && method === 'POST')
      return result.event_id === null && Object.hasOwn(result, 'event') && ((result.event === null && result.task.version === body.expected_task_version) || (record(result.event) && result.event.id === body.event_id && atLeast(result.event.version, body.expected_version)));
    if (parts.length === 3 && method === 'PUT')
      return record(result.event) && result.event.id === body.event_id && result.event_id === body.event_id && atLeast(result.event.version, body.expected_version);
    return false;
  }
  if (!['companies', 'events'].includes(parts[0]) || !record(result)) return false;
  if (parts.length === 1) return method === 'POST' && (parts[0] !== 'events' || ['contact_id','deal_id','company_id'].every(key => Object.hasOwn(result, key) && result[key] === (body.data?.[key] || null)));
  return result.id === parts[1] && atLeast(result.version, body.expected_version) &&
    ((parts.length === 2 && method === 'PATCH') || (parts.length === 3 && method === 'POST' &&
      (parts[0] === 'companies' ? ['archive', 'restore'] : ['complete', 'cancel', 'reopen', 'needs-rescheduling', 'reschedule']).includes(parts[2])));
}
export function relationshipSession(client, token, current = () => true, operationStore = null) {
  let alive = true;
  const store = operationStore || relationshipAttempts.get(client) || new Map();
  relationshipAttempts.set(client, store);
  if (!relationshipListeners.has(store)) relationshipListeners.set(store, new Set());
  const listeners = relationshipListeners.get(store);
  const notify = () => { for (const listener of listeners) listener(); };
  const valid = () => alive && client.current() && current();
  async function perform(attempt) {
    attempt.state = 'running'; notify();
    try {
      const result = await client.request(attempt.path, { method: attempt.method, body: JSON.parse(attempt.payload) });
      if (!confirmedRelationshipReceipt(attempt.path, attempt.method, JSON.parse(attempt.payload), result)) throw new Error('Unconfirmed receipt');
      store.delete(token); notify();
      return valid() ? result : null;
    } catch (error) {
      if ([400, 404, 409, 422].includes(Number(error.status ?? error.statusCode))) {
        store.delete(token); notify();
        throw new Error(`${error.message} Refresh the record and review its current version before trying again. Your form is retained.`);
      }
      attempt.state = 'unknown'; notify();
      throw new Error('Outcome unknown. Retry the original request with its original key before making another change.');
    }
  }
  return {
    subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    valid, activate() { alive = true; }, close() { alive = false; }, pending: () => store.get(token),
    async read(path, params = {}) {
      const separator = path.includes('?') ? '&' : '?';
      const result = await client.request(`${path}${separator}${new URLSearchParams({ ...params, workspace_token: token })}`);
      return valid() ? result : null;
    },
    write(path, method, body, context = null) {
      if (!valid() || store.has(token)) return Promise.resolve(null);
      const attempt = { path, method, state: 'running', context: context ? JSON.parse(JSON.stringify(context)) : null, payload: JSON.stringify({ ...body, workspace_token: token, idempotency_key: crypto.randomUUID() }) };
      store.set(token, attempt);
      return perform(attempt);
    },
    retry() { const attempt = store.get(token); return valid() && attempt?.state === 'unknown' ? perform(attempt) : Promise.resolve(null); },
  };
}
// Retained write context is local-only navigation metadata; never sent to the API.
export function RelationshipPendingCreate({ attempt }) {
  if (!attempt || !['/relationship-contacts','/events','/companies'].includes(attempt.path) || attempt.method !== 'POST') return null;
  const body = JSON.parse(attempt.payload), source = attempt.context?.trail?.at(-1);
  return h('section', {className:'hc-notice', 'aria-label':'Original pending creation'},
    h('h3', null, 'Original pending creation'),
    h('p', null, 'Retry sends only this original frozen request. The current page does not change its destination or associations.'),
    h('p', null, source ? `Original source: ${source.kind} · ${source.id}` : 'Original source: list (no parent record)'),
    attempt.path === '/relationship-contacts' && h('p', null, body.company_id ? `Primary Company: ${body.company_id} · Reviewed version ${body.expected_company_version}` : 'Primary Company: Not linked'),
    h('dl', null, Object.entries(body.data || {}).map(([key,value]) => h('div', {key}, h('dt', null, key === 'company' ? 'Legacy company text (unlinked)' : relLabel(key)), h('dd', null, value === null || value === '' ? 'Not set' : typeof value === 'object' ? JSON.stringify(value) : String(value))))));
}
export function useRelationshipStatus(session) {
  const [generation, setGeneration] = useState(0);
  useEffect(() => session.subscribe(() => setGeneration(value => value + 1)), [session]);
  return generation;
}
const relName = row => row.name || row.title || row.summary || row.id;
const relLabel = text => String(text || '').replaceAll('_', ' ');
const relButton = (text, onClick, disabled = false, props = {}) => h('button', { type: 'button', onClick, disabled, ...props }, text);
export function relationshipInstant(value) { return relInstant(value); }
function RelationshipTime({ name, value, zone, original, originalZone, choice, change, choose, disabled }) {
  let preview = '', candidates = [];
  try { candidates = relEditorCandidates(value, zone, original, originalZone, choice); preview = relReadable(relResolve(value, zone, original, originalZone, choice), zone); } catch (error) { preview = error.message; }
  return h('div', { className: 'hc-time-field' }, h('label', null, relLabel(name), h('input', { type:'datetime-local', step:1, required:true, value, disabled, onChange:e=>change(e.target.value) })),
    candidates.length>1 && h('label', null, 'Repeated time: choose an occurrence', h('select', {value:choice, disabled, onChange:e=>choose(e.target.value)}, h('option', {value:''}, 'Choose occurrence'), candidates.map((instant,index)=>h('option', {key:instant,value:instant}, `${index+1 === 1 ? 'First' : 'Second'} · ${relReadable(instant,zone)} · ${instant}`)))),
    h('small', {role:'status'}, preview), original && h('details', null, h('summary', null, 'Original precise time'), h('small', null, original)));
}
function RelationshipPager({ page, offset, change, disabled }) {
  return h('div', { className: 'hc-actions' }, h('span', null, `${page.total} total · ${page.items.length ? offset + 1 : 0}–${offset + page.items.length} shown`), relButton('Previous page', () => change(Math.max(0, offset - 25)), disabled || offset === 0), relButton('Next page', () => change(offset + 25), disabled || offset + page.items.length >= page.total));
}
export function RelationshipRows({ session, path, params = {}, open, revision = 0, title, kind, disabled, offset: controlledOffset, onOffsetChange }) {
  const [localOffset, setLocalOffset] = useState(0);
  const offset = controlledOffset ?? localOffset, setOffset = onOffsetChange || setLocalOffset;
  const [page, setPage] = useState(null), [error, setError] = useState('');
  const key = JSON.stringify([path, params, offset, revision]);
  useEffect(() => { let live = true; setPage(null); setError(''); session.read(path, { ...params, limit: 25, offset }).then(value => { if (live && value) { if (!Array.isArray(value.items) || !Number.isSafeInteger(value.total)) throw new Error('Invalid paged response'); setPage({ key, ...value }); } }).catch(error => { if (live) setError(error.message); }); return () => { live = false; }; }, [session, key]);
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, title), error && h('p', { role: 'alert' }, error), !page && !error && h('p', { role: 'status' }, 'Loading…'), page?.key === key && h('div', null,
    !page.items.length && h('p', null, 'No records on this page.'),
    h('ul', { className: 'hc-relationship-list' }, page.items.map(row => h('li', { key: row.id },
      relButton(relName(row), () => open(row.entity || kind || (row.record_type === 'event' ? 'events' : 'contacts'), row.entity_id || (row.record_type === 'event' ? row.record_id : !kind ? row.contact_id : null) || row.id), disabled || !open),
      h('small', null, [row.email, row.domain, row.status && relLabel(row.status), row.starts_at && relReadable(row.starts_at,row.timezone), row.happened_at && relReadable(row.happened_at), relLabel(row.timestamp_basis), relLabel(row.relationship_basis || row.association_basis)].filter(Boolean).join(' · ')),
      h('details', null, h('summary', null, 'Record details'), h('small', null, `ID: ${row.id}`), ...['starts_at','ends_at','happened_at'].filter(key=>row[key]).map(key=>h('small',{key},`${relLabel(key)}: ${row[key]}`))),
      (kind === 'tasks' || row.event_id) && h('div', { className: 'hc-relationship-bases' }, h('small', null, `Current-contact Company: ${row.company_name || 'None'}${row.company_id ? ' · ' + row.company_id : ''} · Basis: ${relLabel(row.company_link_basis) || 'not linked'}`), h('small', null, `Explicit Event Company: ${row.event_company_name || 'None'}${row.event_company_id ? ' · ' + row.event_company_id : ''} · Event: ${row.event_title || row.event_id || 'not linked'} · Basis: ${relLabel(row.event_link_basis) || 'not linked'}`)),
      kind === 'tasks' && h('small', null, `Task owner (human): ${row.owner_label || 'Not recorded'} · Due: ${relReadable(row.due_at)}`),
      row.provenance && h('small', null, `Provenance: ${row.provenance}`),
      row.source && h('small', null, `Source: ${row.source} · Self-reported; not verified attendance or delivery`)))),
    h(RelationshipPager, { page, offset, change: setOffset, disabled })));
}
export function RelationshipSelector({ session, kind, value, onChange, disabled, label: caption, reviewedVersion }) {
  const [query, setQuery] = useState(''), [offset, setOffset] = useState(0), [page, setPage] = useState(null), [error, setError] = useState('');
  useEffect(() => { let live = true; setPage(null); setError('');
    const path = ['contacts', 'deals', 'tasks'].includes(kind) ? `/relationship-selectors/${kind}` : `/${kind}`;
    session.read(path, { q: query, limit: 25, offset }).then(result => { if (live && result) setPage(Array.isArray(result) ? { items: result, total: result.length } : result); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; };
  }, [session, kind, query, offset]);
  const [review, setReview] = useState(null), [reviewing, setReviewing] = useState(false);
  const reviewGeneration = useRef(0);
  useEffect(() => { reviewGeneration.current++; setReview(null); setReviewing(false); return () => { reviewGeneration.current++; }; }, [value]);
  async function refreshSelected() {
    if (disabled || reviewing || !value) return;
    const ticket = ++reviewGeneration.current; setReviewing(true); setError('');
    try { const result = await session.read(`/companies/${encodeURIComponent(value)}`); const row = result?.company || result;
      if (ticket !== reviewGeneration.current) return;
      if (!row || row.id !== value || !Number.isSafeInteger(row.version) || row.version < 1) throw new Error('Selected Company is unavailable. Clear or choose another Company.');
      setReview(row);
    } catch (error) { if (ticket === reviewGeneration.current) setError(error.message); }
    finally { if (ticket === reviewGeneration.current) setReviewing(false); }
  }
  return h('fieldset', { className: 'hc-relationship-selector', disabled }, h('legend', null, caption), h('label', null, 'Search', h('input', { value: query, onChange: e => { setQuery(e.target.value); setOffset(0); } })),
    h('p', null, value ? `Selected exact ID: ${value}` : 'Not linked'), value && relButton('Clear selection', () => onChange(null), disabled), error && h('p', { role: 'alert' }, error),
    kind === 'companies' && value && reviewedVersion !== undefined && h('div', null,
      relButton('Refresh selected Company', refreshSelected, disabled || reviewing),
      review && h('p', null, `${relName(review)} · ${review.id} · Version ${review.version}${review.archived_at ? ' · archived; choose another Company' : ''}`),
      review && relButton('Use reviewed Company version', () => onChange(review.id, review), disabled || !!review.archived_at)),
    page && h('div', null, h('ul', null, page.items.map(row => h('li', { key: row.id }, relButton(`${relName(row)} · ${row.email || row.domain || row.status || ''} · ${row.id}${row.archived_at ? ' · archived' : ''}`, () => onChange(row.id, row), disabled || !!row.archived_at, { 'aria-pressed': value === row.id })))), h(RelationshipPager, { page, offset, change: setOffset, disabled })));
}
export function RelationshipForm({ kind, row, initialValues = null, action, session, submit, cancel, cancelRef, busy, pending }) {
  const fields = kind === 'companies' ? ['name', 'domain', 'notes'] : action === 'task' ? ['title', 'due_at', 'notes'] : action === 'complete' ? ['outcome_happened_at', 'outcome_summary'] : ['cancel', 'reopen', 'needs-rescheduling'].includes(action) ? ['reason'] : ['title', 'kind', 'starts_at', 'ends_at', 'timezone', 'notes'];
  const [values, setValues] = useState(() => Object.fromEntries([...fields, ...(kind === 'events' && !action ? ['contact_id', 'deal_id', 'company_id'] : action === 'task' ? ['contact_id', 'deal_id'] : [])].map(key => [key, (action === 'task' && !['contact_id', 'deal_id'].includes(key) ? undefined : (row || initialValues)?.[key]) ?? (key === 'kind' ? 'appointment' : key === 'timezone' ? 'UTC' : '')])));
  const original = useRef(values).current;
  const originalZone = useRef((row || initialValues)?.timezone || 'UTC').current;
  const [zone, setZone] = useState(originalZone), [walls, setWalls] = useState(()=>Object.fromEntries(fields.filter(key=>key.endsWith('_at')).map(key=>[key, values[key] ? relWall(values[key],originalZone) : '']))), [choices,setChoices] = useState({});
  const [discard,setDiscard] = useState(false);
  const [ownerPolicy,setOwnerPolicy] = useState(null), [ownerLabel,setOwnerLabel] = useState(''), [ownerSource,setOwnerSource] = useState('explicit'), [ownerPolicyError,setOwnerPolicyError] = useState('');
  useEffect(() => {
    if (action !== 'task') return;
    let live = true;
    session.read('/task-owner-policy').then(policy => {
      if (!live) return;
      if (!policy || !Number.isSafeInteger(policy.version) || policy.version < 0 || typeof policy.required !== 'boolean' || !(policy.default_owner_label === null || (typeof policy.default_owner_label === 'string' && policy.default_owner_label.trim() && policy.default_owner_label.length <= 160))) throw new Error('Task ownership policy could not be verified. Close and reopen the task form.');
      setOwnerPolicy(policy);
    }).catch(error => {if(live) setOwnerPolicyError(error.message);});
    return () => {live = false;};
  }, [session,action]);
  const dirty = !!ownerLabel || JSON.stringify(values)!==JSON.stringify(original) || zone!==originalZone || Object.entries(walls).some(([key,value])=>value!==(original[key] ? relWall(original[key],originalZone) : '')) || Object.values(choices).some(Boolean);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  const requestCancel = () => { if (!active.current || busy) return; if (dirty) setDiscard(true); else cancel(); };
  if (cancelRef) cancelRef.current = requestCancel;
  const [error, setError] = useState(''); const first = useRef(null);
  useEffect(() => { first.current?.focus(); }, []);
  const change = (key, value) => setValues(previous => ({ ...previous, [key]: value }));
  return h('form', { className: 'hc-relationship-form', 'aria-label': `${action || (row ? 'Edit' : 'Create')} ${kind}`, onSubmit: e => { e.preventDefault(); if (!active.current || busy || pending) return; setError(''); try {
    const data = { ...values }; for (const key of ['contact_id', 'deal_id', 'company_id']) if (data[key] === '') data[key] = null;
    for (const field of ['starts_at', 'ends_at', 'outcome_happened_at', 'due_at']) if (Object.hasOwn(data, field)) data[field] = relResolve(walls[field], zone, original[field], originalZone, choices[field]);
    if (data.timezone) new Intl.DateTimeFormat('en', { timeZone: data.timezone }).format();
    if (data.starts_at && data.ends_at && relMicros(data.ends_at) <= relMicros(data.starts_at)) throw new Error('End must follow start.');
    if (data.outcome_happened_at && relMicros(data.outcome_happened_at) > BigInt(Date.now()) * 1000n) throw new Error('Claimed occurrence cannot be in the future.');
    if (action === 'task') {
      if (!ownerPolicy) throw new Error('Task ownership policy is not available. Close and reopen this form before saving.');
      data.owner_label = ownerLabel.trim() || null;
      if (ownerPolicy.required && !data.owner_label) throw new Error('Choose a human task owner before saving.');
      data.owner_source = ownerSource;
      data.owner_policy_version = ownerPolicy.version;
    }
    submit(data);
  } catch (error) { setError(error.message); } }, onKeyDown: e => { if (e.key === 'Escape' && !busy) { e.preventDefault(); e.stopPropagation?.(); requestCancel(); } } },
    h('h3', null, `${relLabel(action || (row ? 'Edit' : 'Create'))} ${action === 'task' ? 'associated task' : kind === 'companies' ? 'Company' : 'Event'}`),
    kind === 'events' && h('p', { className: 'hc-muted' }, 'Local CRM record only. Saving does not invite, call, send, schedule a reminder, research, attach files or sync a calendar. Completion is your self-reported claim. Related records are context, not verified attendees. Notes are ordinary plaintext.'),
    action === 'task' && h('p', { className: 'hc-muted' }, 'Review the exact contact and deal context prefilled from this Event below, or clear each selection for an Event-only task. No Company is inferred. The explicit Event link remains separate from the task’s direct contact or deal context.'),
    fields.some(key=>key.endsWith('_at')) && h('label', null, 'Timezone for entered times', h('input', {value:zone, required:true, disabled:busy || pending, placeholder:'America/New_York', onChange:e=>{setZone(e.target.value); setChoices({}); if(fields.includes('timezone')) change('timezone',e.target.value);}}), h('small', null, 'Changing the zone reinterprets the entered wall times. New or changed times must use years 1900–2100; unchanged original times are preserved. Review each preview before saving.')),
    fields.filter(key=>key!=='timezone').map((key, index) => key.endsWith('_at') ? h(RelationshipTime, {key,name:key,value:walls[key],zone,original:original[key],originalZone,choice:choices[key] || '',change:value=>{setWalls(previous=>({...previous,[key]:value}));setChoices(previous=>({...previous,[key]:''}));},choose:value=>setChoices(previous=>({...previous,[key]:value})),disabled:busy || pending}) : h('label', { key }, relLabel(key), key === 'kind' ? h('select', { value: values[key], disabled: busy || pending, onChange: e => change(key, e.target.value) }, h('option', { value: 'appointment' }, 'Appointment'), h('option', { value: 'call' }, 'Call')) : h(['notes', 'reason', 'outcome_summary'].includes(key) ? 'textarea' : 'input', { ref: index === 0 ? first : undefined, value: values[key], disabled: busy || pending, required: !['domain', 'notes'].includes(key), onChange: e => change(key, e.target.value) }))),
    action === 'task' && h('fieldset', {className:'hc-form-section',disabled:busy || pending}, h('legend',null,'Task accountability'),
      h('label',null,'Task owner (human)',h('input',{name:'owner_label',value:ownerLabel,maxLength:160,required:ownerPolicy?.required || false,disabled:busy || pending || !ownerPolicy,onChange:e=>{if(active.current && !busy && !pending){setOwnerLabel(e.target.value);setOwnerSource('explicit');}}})),
      ownerPolicy?.default_owner_label && relButton(`Use configured default: ${ownerPolicy.default_owner_label}`,()=>{if(active.current && !busy && !pending){setOwnerLabel(ownerPolicy.default_owner_label);setOwnerSource('default');}},busy || pending),
      h('p',null,ownerPolicy ? `Reviewed policy version ${ownerPolicy.version} · ${ownerPolicy.required ? 'Owner required' : 'Owner optional'}${ownerSource === 'default' ? ' · Configured default selected' : ''}` : ownerPolicyError || 'Loading ownership policy…'),
      h('small',null,'Human accountability label, not verified identity or access permission. Separate from Hermes executor and assignment owners. Saving this task does not schedule execution.')),
    action === 'task' && !values.contact_id && !values.deal_id && h('p', {className:'hc-notice'}, 'An Event-only task does not count as a contact follow-up. Link a contact or deal if this task is intended for contact follow-up.'),
    kind === 'events' && (!action || action === 'task') && (action === 'task' ? ['contacts', 'deals'] : ['contacts', 'deals', 'companies']).map(entity => { const key = entity === 'companies' ? 'company_id' : `${entity.slice(0, -1)}_id`; return h(RelationshipSelector, { key, session, kind: entity, label: `Related ${entity}`, value: values[key], disabled: busy || pending, onChange: id => change(key, id) }); }),
    error && h('p', { role: 'alert' }, error), h('div', { className: 'hc-actions' }, h('button', { type: 'submit', disabled: busy || pending || (action === 'task' && !ownerPolicy), className: 'hc-primary' }, busy ? 'Saving…' : 'Save'), relButton('Cancel', requestCancel, busy)), discard && h('div', {className:'hc-discard-choice',role:'alert'}, h('p', null, 'Discard unsaved changes?'), relButton('Keep editing', ()=>setDiscard(false)), relButton('Discard changes', cancel, busy)));
}
export function Relationships({ onResearch, client, workspaceToken, page = 'companies', initial = null, startRelatedCreate, onCreated, onCreateRejected, createContext = null, open, onSaved, onEditingChange, navigateRecord, onBack, initialListState = {}, onListStateChange, disabled = false, operationStore = null }) {
  const sessionRef = useRef(null);
  if (!sessionRef.current) sessionRef.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = sessionRef.current;
  const operationGeneration = useRelationshipStatus(session);
  const [selected, setSelected] = useState(initial), [record, setRecord] = useState(null), [form, setForm] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0), [taskChoice, setTaskChoice] = useState(null), [query, setQuery] = useState(initialListState.query || ''), [archived, setArchived] = useState(initialListState.archived || false), [eventStatus, setEventStatus] = useState(initialListState.eventStatus || ''), [eventKind, setEventKind] = useState(initialListState.eventKind || ''), [offsets, setOffsets] = useState(initialListState.offsets || {});
  // Only query/filter/page positions cross record navigation; rows are always reread.
  useEffect(() => { onListStateChange?.({ query, archived, eventStatus, eventKind, offsets }); }, [query, archived, eventStatus, eventKind, offsets, onListStateChange]);
  function pagination(key) { return { offset: offsets[key] || 0, onOffsetChange: value => setOffsets(previous => Object.fromEntries([...Object.entries(previous).filter(([name]) => name !== key), [key, value]].slice(-50))) }; }
  function filter(setter, value) { setter(value); setOffsets(previous => ({ ...previous, list: 0 })); }
  useEffect(() => { onEditingChange?.(!!form); return () => onEditingChange?.(false); }, [!!form, onEditingChange]);
  const mutationLock = useRef(false);
  const root = useRef(null);
  const sequence = useRef(0), heading = useRef(null), returnFocus = useRef(null);
  useEffect(() => { session.activate(); return () => { session.close(); sequence.current++; }; }, [session]);
  const kind = selected?.kind || (page === 'companies' ? 'companies' : 'events');
  useEffect(() => { let live = true; if (selected) session.read(`/${selected.kind}/${encodeURIComponent(selected.id)}`).then(value => { if (live && value) { const row = value.company || value.event || value; if (row.id !== selected.id) throw new Error('The exact record could not be verified. Refresh before continuing.'); setRecord(row); heading.current?.focus(); } }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [session, selected, revision, operationGeneration]);
  function select(entity, id) { if (busy || disabled || form) return; sequence.current++; setError(''); if (navigateRecord) { navigateRecord(entity, id); return; } if (['companies', 'events'].includes(entity)) { setRecord(null); setSelected({ kind: entity, id }); } else open(entity, id); }
  useEffect(() => { if (!form) { if (returnFocus.current?.isConnected) returnFocus.current.focus(); else (heading.current || root.current)?.focus(); } }, [record?.id, form]);
  function cancel() { setForm(null); }
  function edit(action = '') { returnFocus.current = root.current?.ownerDocument.activeElement; setForm({ action, expectedVersion: record?.version }); setError(''); }
  async function write(path, method, body, retry = false) {
    if (mutationLock.current || disabled) return; mutationLock.current = true; const ticket = ++sequence.current; const attemptPath = retry ? session.pending()?.path : path; const attemptMethod = retry ? session.pending()?.method : method; const rejectedAttempt = retry ? session.pending() : null; const attemptContext = retry ? session.pending()?.context : createContext; setBusy(true); setError('');
    try { const result = await (retry ? session.retry() : session.write(path, method, body, createContext)); if (result && session.valid() && ticket === sequence.current) { setForm(null); setRevision(v => v + 1); onSaved?.(); if (attemptMethod === 'POST' && ['/relationship-contacts','/events','/companies'].includes(attemptPath)) onCreated?.(attemptPath === '/relationship-contacts' ? 'contacts' : attemptPath.slice(1), result.contact?.id || result.id, attemptContext); returnFocus.current?.focus(); } } catch (error) { if (session.valid() && ticket === sequence.current) { setError(error.message); if (rejectedAttempt && !session.pending() && rejectedAttempt.method === 'POST' && ['/relationship-contacts','/events'].includes(rejectedAttempt.path)) onCreateRejected?.(rejectedAttempt, error.message); } } finally { mutationLock.current = false; if (session.valid() && ticket === sequence.current) setBusy(false); }
  }
  function save(values) {
    const action = form.action; const base = `/${kind}${record ? '/' + encodeURIComponent(record.id) : ''}`;
    const body = record ? { expected_version: form.expectedVersion } : {};
    if (['cancel', 'reopen', 'needs-rescheduling'].includes(action)) body.reason = values.reason; else body.data = values;

    write(`${base}${action ? '/' + (action === 'task' ? 'tasks' : action) : ''}`, record && !action ? 'PATCH' : 'POST', body);
  }
  const pending = session.pending(), locked = busy || disabled || !!pending;
  const recoveringCreate = pending?.state === 'unknown' && ['/relationship-contacts','/events'].includes(pending.path);
  return h('section', { ref: root, tabIndex: -1, className: 'hc-relationships', 'aria-label': 'Companies and relationship events' },
    h(RelationshipPendingCreate, {attempt: pending}),
    error && h('div', null, h('p', { role: 'alert', className: 'hc-notice' }, error), selected && relButton('Refresh current record (keep draft)', () => setRevision(v => v + 1), busy)), pending?.state === 'unknown' && relButton('Retry original request', () => write('', '', {}, true), busy || disabled),
    form?.action === 'link-task' ? h('section', null, h(RelationshipSelector, { session, kind: 'tasks', label: 'Select exact existing task', value: taskChoice?.id, onChange: (id, row) => setTaskChoice(id ? row : null), disabled: locked }), relButton('Link selected task', () => write(`/tasks/${encodeURIComponent(taskChoice.id)}/event`, 'PUT', { event_id: record.id, expected_version: record.version, expected_task_version: taskChoice.version }), locked || !taskChoice), relButton('Cancel', cancel, busy)) : form ? h('div', null, form.expectedVersion !== record?.version && record && h('div', null, h('p', null, `Record is now version ${record.version}. Review current values before using this draft.`), h('dl', null, Object.entries(record).filter(([key, value]) => ['name','title','domain','notes','starts_at','ends_at','timezone','status'].includes(key) && value != null).map(([key, value]) => h('div', { key }, h('dt', null, relLabel(key)), h('dd', null, String(value))))), relButton('Use refreshed version for this draft', () => setForm({ ...form, expectedVersion: record.version }), locked)), h(RelationshipForm, { key: `${kind}:${record?.id || 'new'}:${form.action}`, kind, row: record, action: form.action, session, submit: save, cancel, busy, pending: !!pending })) : selected ? h('div', null,
      relButton(onBack ? 'Close' : 'Back to list', () => { if (busy || disabled || form) return; sequence.current++; if (onBack) onBack(); else { setSelected(null); setRecord(null); } }, busy || disabled),
      !record ? h('p', { role: 'status' }, 'Loading record…') : h('section', { className: 'hc-record' },
        h('h2', { ref: heading, tabIndex: -1 }, relName(record)), h('details', {className:'hc-record-meta'}, h('summary', null, 'Record details'), h('p', null, `${record.id} · Version ${record.version}`), ...['starts_at','ends_at','outcome_happened_at','recorded_at'].filter(key=>record[key]).map(key=>h('p',{key},`${relLabel(key)}: ${record[key]}`))),
        kind === 'companies' ? h('div', null, h('p', null, `${record.domain || 'No domain'}${record.archived_at ? ' · Archived' : ''}`), h('p', null, record.notes), h('div', { className: 'hc-actions' }, relButton('Edit Company', () => edit(), locked, {className:'hc-primary'}), relButton('Research', () => onResearch?.(record), locked || !onResearch, {'aria-haspopup':'dialog'}), relButton('Create contact', () => startRelatedCreate?.('contacts', 'companies', record), busy || disabled || (!!pending && !recoveringCreate) || !!record.archived_at || !startRelatedCreate), relButton('Create Event', () => startRelatedCreate?.('events', 'companies', record), busy || disabled || (!!pending && !recoveringCreate) || !!record.archived_at || !startRelatedCreate), relButton(record.archived_at ? 'Restore Company' : 'Archive Company', () => write(`/companies/${encodeURIComponent(record.id)}/${record.archived_at ? 'restore' : 'archive'}`, 'POST', { expected_version: record.version }), locked)), h('p', { className: 'hc-muted' }, 'Current explicit relationships. Contacts have one primary Company. Deals follow their contact. Tasks follow their direct contact or deal contact; Event-linked tasks also show their Event basis. Events retain their own explicit Company. Domain is unverified text.'), ['contacts', 'deals', 'tasks', 'events'].map(entity => h(RelationshipRows, { key: entity, ...pagination(`company:${record.id}:${entity}`), session, path: `/companies/${encodeURIComponent(record.id)}/records/${entity}`, title: relLabel(entity), kind: entity, open: select, revision: revision + operationGeneration, disabled: locked })), h(RelationshipRows, { ...pagination(`company:${record.id}:activities`), session, path: '/relationship-activities', params: { company_id: record.id }, title: 'Company Activities · current relationship membership', open: select, revision: revision + operationGeneration, disabled: locked })) : h('div', null,
          h('p', null, `${relLabel(record.kind)} · ${relLabel(record.status)} · Local`), h('p', null, `${relReadable(record.starts_at,record.timezone)} → ${relReadable(record.ends_at,record.timezone)} · Display timezone: ${record.timezone}`), h('p', null, record.notes),
          record.status === 'completed' && h('p', null, `Self-reported completion: ${relReadable(record.outcome_happened_at,record.timezone)} · ${record.outcome_summary}. Recorded ${relReadable(record.recorded_at || record.updated_at,record.timezone)}. Not verified attendance or call.`),
          h('div', { className: 'hc-actions' }, ['contact', 'deal', 'company'].map(entity => record[`${entity}_id`] && relButton(`Open ${entity} · ${record[`${entity}_id`]}`, () => select(entity === 'company' ? 'companies' : `${entity}s`, record[`${entity}_id`]), locked, { key: entity }))),
          h('div', { className: 'hc-actions' }, ['scheduled', 'needs_rescheduling'].includes(record.status) && relButton('Edit Event', () => edit(), locked, {className:'hc-primary'}), ['scheduled', 'needs_rescheduling'].includes(record.status) && [ ['reschedule', 'Reschedule'], ['complete', 'Complete (self-reported)'] ].map(([action, caption]) => relButton(caption, () => edit(action), locked, { key: action })), ['completed', 'cancelled'].includes(record.status) && relButton('Reopen Event', () => edit('reopen'), locked), relButton('Create associated task', () => edit('task'), locked), relButton('Link existing task', () => { setTaskChoice(null); edit('link-task'); }, locked)),
          ['scheduled', 'needs_rescheduling'].includes(record.status) && h('details', null, h('summary', null, 'More Event actions'), h('div', {className:'hc-actions'}, relButton('Cancel Event', ()=>edit('cancel'),locked), record.status==='scheduled' && relButton('Needs rescheduling', ()=>edit('needs-rescheduling'),locked))),
          h(RelationshipRows, { ...pagination(`event:${record.id}:tasks`), session, path: `/events/${encodeURIComponent(record.id)}/tasks`, title: 'Associated tasks', kind: 'tasks', open: select, revision: revision + operationGeneration, disabled: locked }),
          h('p', { className: 'hc-muted' }, 'Open a task to use its genuine agent-assignment workflow. Creating or completing an Event does not assign work, perform research or complete its tasks.')))) : h('div', null,
      page !== 'activities' && h('div', { className: 'hc-actions' }, relButton(`Create ${page === 'companies' ? 'Company' : 'Event'}`, () => { setRecord(null); edit(); }, locked), h('label', null, 'Search', h('input', { value: query, disabled: busy, onChange: e => filter(setQuery, e.target.value) })), page === 'companies' && h('label', null, h('input', { type: 'checkbox', checked: archived, onChange: e => filter(setArchived, e.target.checked) }), 'Include archived')),
      page === 'events' && h('div', { className: 'hc-actions' }, h('label', null, 'Event status', h('select', { value: eventStatus, onChange: e => filter(setEventStatus, e.target.value) }, ['', 'scheduled', 'needs_rescheduling', 'completed', 'cancelled'].map(value => h('option', { key: value, value }, value ? relLabel(value) : 'All statuses')))), h('label', null, 'Event kind', h('select', { value: eventKind, onChange: e => filter(setEventKind, e.target.value) }, ['', 'appointment', 'call'].map(value => h('option', { key: value, value }, value || 'All kinds'))))),
      h(RelationshipRows, { key: `${page}:${query}:${archived}:${eventStatus}:${eventKind}`, ...pagination('list'), session, path: page === 'activities' ? '/relationship-activities' : `/${page}`, params: page === 'activities' ? {} : { q: query, ...(page === 'companies' ? { include_archived: archived } : { ...(eventStatus ? { status: eventStatus } : {}), ...(eventKind ? { kind: eventKind } : {}) }) }, title: page === 'activities' ? 'Relationship Activities · self-reported' : relLabel(page), kind: page === 'activities' ? undefined : page, open: select, revision: revision + operationGeneration, disabled: locked })));
}

export function ContactCompany({ client, workspaceToken, contact, open, disabled, onSaved, operationStore = null }) {
  const sessionRef = useRef(null); if (!sessionRef.current) sessionRef.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = sessionRef.current; const operationGeneration = useRelationshipStatus(session); const [link, setLink] = useState(null), [editing, setEditing] = useState(false), [choice, setChoice] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0);
  useEffect(() => { session.activate(); return () => session.close(); }, [session]);
  useEffect(() => { let live = true; session.read(`/contacts/${encodeURIComponent(contact.id)}/company`).then(row => { if (live && row) setLink(row); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [session, contact.id, revision, operationGeneration]);
  const mutationLock = useRef(false);
  const company = link?.company_id ? { id: link.company_id, name: link.company_name, archived_at: link.company_archived } : null;
  async function save(retry = false) { if (retry && session.pending()?.path !== `/contacts/${encodeURIComponent(contact.id)}/company`) return; if (mutationLock.current || disabled) return; mutationLock.current = true; setBusy(true); setError(''); try { const result = await (retry ? session.retry() : session.write(`/contacts/${encodeURIComponent(contact.id)}/company`, 'PUT', { company_id: choice, expected_contact_version: link?.contact_version ?? contact.version })); if (result) { setEditing(false); setRevision(v => v + 1); onSaved?.(); } } catch (e) { if (session.valid()) setError(e.message); } finally { mutationLock.current = false; if (session.valid()) setBusy(false); } }
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, 'Primary Company'), company ? relButton(`${company.name} · ${company.id}${company.archived_at ? ' · archived' : ''}`, () => open('companies', company.id), disabled) : h('p', null, 'No explicit Company link.'), h('p', { className: 'hc-muted' }, `Legacy company text (unlinked): ${contact.company || 'Not set'}. No automatic name matching.`), error && h('p', { role: 'alert' }, error),
    session.pending()?.state === 'unknown' && session.pending()?.path === `/contacts/${encodeURIComponent(contact.id)}/company` && relButton('Retry original request', () => save(true), busy || disabled),
    editing ? h('div', null, h(RelationshipSelector, { session, kind: 'companies', label: 'Select exact Company', value: choice, onChange: setChoice, disabled: busy || !!session.pending() }), relButton(choice ? 'Save explicit link' : 'Unlink Company', () => save(), busy || disabled || !!session.pending()), relButton('Cancel', () => setEditing(false), busy)) : relButton('Change Company link', () => { setChoice(company?.id || null); setEditing(true); }, disabled || busy || !!session.pending()));
}

export function ContactRelationships({ client, workspaceToken, contact, open, disabled, operationStore = null }) {
  const ref = useRef(null); if (!ref.current) ref.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = ref.current;
  useEffect(() => { session.activate(); return () => session.close(); }, [session]);
  return h('div', null,
    h(RelationshipRows, { session, path: `/contacts/${encodeURIComponent(contact.id)}/relationship-tasks`, title: 'All associated tasks · contact and Event relationships', kind: 'tasks', open, disabled }),
    h(RelationshipRows, { session, path: '/events', params: { contact_id: contact.id }, title: 'Related local Events', kind: 'events', open, disabled }),
    h(RelationshipRows, { session, path: '/relationship-activities', params: { contact_id: contact.id }, title: 'Relationship Activities · self-reported', open, disabled }));
}

export function TaskEventRelationship({ client, workspaceToken, task, open, disabled, onSaved, operationStore = null }) {
  const ref = useRef(null); if (!ref.current) ref.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = ref.current; useRelationshipStatus(session); const [event, setEvent] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => { session.activate(); return () => session.close(); }, [session]);
  async function review() { setBusy(true); setError(''); try { const value = await session.read(`/events/${encodeURIComponent(task.event_id)}`); if (value?.id !== task.event_id) throw new Error('Event identity could not be verified'); setEvent(value); } catch (e) { if (session.valid()) setError(e.message); } finally { mutationLock.current = false; if (session.valid()) setBusy(false); } }
  async function unlink(retry = false) { if (retry && session.pending()?.path !== `/tasks/${encodeURIComponent(task.id)}/event/unlink`) return; if (mutationLock.current || disabled) return; mutationLock.current = true; setBusy(true); setError(''); try { const result = await (retry ? session.retry() : session.write(`/tasks/${encodeURIComponent(task.id)}/event/unlink`, 'POST', { event_id: event.id, expected_version: event.version, expected_task_version: task.version })); if (result) onSaved?.(); } catch (e) { if (session.valid()) setError(e.message); } finally { mutationLock.current = false; if (session.valid()) setBusy(false); } }
  const mutationLock = useRef(false);
  const locked = busy || disabled || !!session.pending();
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, 'Linked Event'), relButton(`${task.event_title || 'Event'} · ${task.event_id}`, () => open('events', task.event_id), disabled || busy), h('p', null, 'Association basis: explicit Event task link. Agent-work ownership is separate.'), error && h('p', { role: 'alert' }, error),
    session.pending()?.state === 'unknown' && session.pending()?.path === `/tasks/${encodeURIComponent(task.id)}/event/unlink` && relButton('Retry original request', () => unlink(true), busy || disabled),
    event ? h('div', null, h('p', null, `Unlink from ${event.title} · ${event.id} · Event version ${event.version} · Task version ${task.version}? This keeps both records.`), relButton('Unlink from reviewed Event', () => unlink(), locked), relButton('Cancel unlink', () => setEvent(null), busy)) : relButton('Review Event unlink', review, locked));
}
