import { createElement as h, useEffect, useRef, useState } from "react";

// Retained across panel navigation so an uncertain write cannot become a new intent.
const relationshipAttempts = new WeakMap();
const relationshipListeners = new WeakMap();
// A receipt confirms only the captured operation and exact identities, never a
// merely record-shaped object. Invalid receipts keep the original retry key.
export function confirmedRelationshipReceipt(path, method, body, result) {
  const version = value => Number.isSafeInteger(value) && value > 0;
  const id = value => typeof value === 'string' && value.trim().length > 0;
  const record = value => value && id(value.id) && version(value.version);
  const atLeast = (actual, expected) => version(actual) && (!version(expected) || actual >= expected);
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  if (!result || typeof result !== 'object') return false;
  if (parts[0] === 'contacts' && parts.length === 3 && parts[2] === 'company' && method === 'PUT')
    return result.contact_id === parts[1] && atLeast(result.contact_version, body.expected_contact_version) && Object.hasOwn(result, 'company_id') && result.company_id === body.company_id;
  if (parts[0] === 'events' && parts.length === 3 && parts[2] === 'tasks' && method === 'POST')
    return record(result.task) && result.task_id === result.task.id && record(result.event) && result.event.id === parts[1] && result.event_id === parts[1] && atLeast(result.event.version, body.expected_version);
  if (parts[0] === 'tasks' && parts[2] === 'event') {
    if (!record(result.task) || result.task_id !== parts[1] || result.task.id !== parts[1] || !atLeast(result.task.version, body.expected_task_version)) return false;
    if (parts.length === 4 && parts[3] === 'unlink' && method === 'POST')
      return result.event_id === null && Object.hasOwn(result, 'event') && ((result.event === null && result.task.version === body.expected_task_version) || (record(result.event) && result.event.id === body.event_id && atLeast(result.event.version, body.expected_version)));
    if (parts.length === 3 && method === 'PUT')
      return record(result.event) && result.event.id === body.event_id && result.event_id === body.event_id && atLeast(result.event.version, body.expected_version);
    return false;
  }
  if (!['companies', 'events'].includes(parts[0]) || !record(result)) return false;
  if (parts.length === 1) return method === 'POST';
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
    write(path, method, body) {
      if (!valid() || store.has(token)) return Promise.resolve(null);
      const attempt = { path, method, state: 'running', payload: JSON.stringify({ ...body, workspace_token: token, idempotency_key: crypto.randomUUID() }) };
      store.set(token, attempt);
      return perform(attempt);
    },
    retry() { const attempt = store.get(token); return valid() && attempt?.state === 'unknown' ? perform(attempt) : Promise.resolve(null); },
  };
}
function useRelationshipStatus(session) {
  const [generation, setGeneration] = useState(0);
  useEffect(() => session.subscribe(() => setGeneration(value => value + 1)), [session]);
  return generation;
}
const relName = row => row.name || row.title || row.summary || row.id;
const relLabel = text => String(text || '').replaceAll('_', ' ');
const relButton = (text, onClick, disabled = false, props = {}) => h('button', { type: 'button', onClick, disabled, ...props }, text);
export function relationshipInstant(value) {
  const text = String(value || '').trim();
  if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d{1,6})?)?(Z|[+-]\d\d:\d\d)$/.test(text) || !Number.isFinite(Date.parse(text))) throw new Error('Use an ISO instant with an explicit offset, such as 2026-11-09T14:00:00-05:00.');
  const [year, month, day] = text.slice(0, 10).split('-').map(Number);
  if (month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) throw new Error('Enter a valid calendar date.');
  return text; // Preserve seconds, fractional precision, and the user's explicit offset.
}
function RelationshipPager({ page, offset, change, disabled }) {
  return h('div', { className: 'hc-actions' }, h('span', null, `${page.total} total · ${page.items.length ? offset + 1 : 0}–${offset + page.items.length} shown`), relButton('Previous page', () => change(Math.max(0, offset - 25)), disabled || offset === 0), relButton('Next page', () => change(offset + 25), disabled || offset + page.items.length >= page.total));
}
export function RelationshipRows({ session, path, params = {}, open, revision = 0, title, kind, disabled }) {
  const [offset, setOffset] = useState(0), [page, setPage] = useState(null), [error, setError] = useState('');
  const key = JSON.stringify([path, params, offset, revision]);
  useEffect(() => { let live = true; setPage(null); setError(''); session.read(path, { ...params, limit: 25, offset }).then(value => { if (live && value) { if (!Array.isArray(value.items) || !Number.isSafeInteger(value.total)) throw new Error('Invalid paged response'); setPage({ key, ...value }); } }).catch(error => { if (live) setError(error.message); }); return () => { live = false; }; }, [session, key]);
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, title), error && h('p', { role: 'alert' }, error), !page && !error && h('p', { role: 'status' }, 'Loading…'), page?.key === key && h('div', null,
    !page.items.length && h('p', null, 'No records on this page.'),
    h('ul', { className: 'hc-relationship-list' }, page.items.map(row => h('li', { key: row.id },
      relButton(relName(row), () => open(row.entity || kind || (row.record_type === 'event' ? 'events' : 'contacts'), row.entity_id || (row.record_type === 'event' ? row.record_id : !kind ? row.contact_id : null) || row.id), disabled || !open),
      h('small', null, [row.id, row.email, row.domain, row.status && relLabel(row.status), row.starts_at, row.happened_at, row.timestamp_basis, row.relationship_basis || row.association_basis].filter(Boolean).join(' · ')),
      (kind === 'tasks' || row.event_id) && h('div', { className: 'hc-relationship-bases' }, h('small', null, `Current-contact Company: ${row.company_name || 'None'}${row.company_id ? ' · ' + row.company_id : ''} · Basis: ${row.company_link_basis || 'not linked'}`), h('small', null, `Explicit Event Company: ${row.event_company_name || 'None'}${row.event_company_id ? ' · ' + row.event_company_id : ''} · Event: ${row.event_title || row.event_id || 'not linked'} · Basis: ${row.event_link_basis || 'not linked'}`)),
      row.provenance && h('small', null, `Provenance: ${row.provenance}`),
      row.source && h('small', null, `Source: ${row.source} · Self-reported; not verified attendance or delivery`)))),
    h(RelationshipPager, { page, offset, change: setOffset, disabled })));
}
export function RelationshipSelector({ session, kind, value, onChange, disabled, label: caption }) {
  const [query, setQuery] = useState(''), [offset, setOffset] = useState(0), [page, setPage] = useState(null), [error, setError] = useState('');
  useEffect(() => { let live = true; setPage(null); setError('');
    const path = ['contacts', 'deals', 'tasks'].includes(kind) ? `/relationship-selectors/${kind}` : `/${kind}`;
    session.read(path, { q: query, limit: 25, offset }).then(result => { if (live && result) setPage(Array.isArray(result) ? { items: result, total: result.length } : result); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; };
  }, [session, kind, query, offset]);
  return h('fieldset', { className: 'hc-relationship-selector', disabled }, h('legend', null, caption), h('label', null, 'Search', h('input', { value: query, onChange: e => { setQuery(e.target.value); setOffset(0); } })),
    h('p', null, value ? `Selected exact ID: ${value}` : 'Not linked'), value && relButton('Clear selection', () => onChange(null), disabled), error && h('p', { role: 'alert' }, error),
    page && h('div', null, h('ul', null, page.items.map(row => h('li', { key: row.id }, relButton(`${relName(row)} · ${row.email || row.domain || row.status || ''} · ${row.id}${row.archived_at ? ' · archived' : ''}`, () => onChange(row.id, row), disabled || !!row.archived_at, { 'aria-pressed': value === row.id })))), h(RelationshipPager, { page, offset, change: setOffset, disabled })));
}
export function RelationshipForm({ kind, row, action, session, submit, cancel, busy, pending }) {
  const fields = kind === 'companies' ? ['name', 'domain', 'notes'] : action === 'task' ? ['title', 'due_at', 'notes'] : action === 'complete' ? ['outcome_happened_at', 'outcome_summary'] : ['cancel', 'reopen', 'needs-rescheduling'].includes(action) ? ['reason'] : ['title', 'kind', 'starts_at', 'ends_at', 'timezone', 'notes'];
  const [values, setValues] = useState(() => Object.fromEntries([...fields, ...(kind === 'events' && !action ? ['contact_id', 'deal_id', 'company_id'] : action === 'task' ? ['contact_id', 'deal_id'] : [])].map(key => [key, (action === 'task' && !['contact_id', 'deal_id'].includes(key) ? undefined : row?.[key]) ?? (key === 'kind' ? 'appointment' : key === 'timezone' ? 'UTC' : '')])));
  const [error, setError] = useState(''); const first = useRef(null);
  useEffect(() => { first.current?.focus(); }, []);
  const change = (key, value) => setValues(previous => ({ ...previous, [key]: value }));
  return h('form', { className: 'hc-relationship-form', 'aria-label': `${action || (row ? 'Edit' : 'Create')} ${kind}`, onSubmit: e => { e.preventDefault(); setError(''); try {
    const data = { ...values }; for (const key of ['contact_id', 'deal_id', 'company_id']) if (data[key] === '') data[key] = null;
    for (const field of ['starts_at', 'ends_at', 'outcome_happened_at', 'due_at']) if (Object.hasOwn(data, field)) data[field] = relationshipInstant(data[field]);
    if (data.timezone) new Intl.DateTimeFormat('en', { timeZone: data.timezone }).format();
    if (data.starts_at && data.ends_at && Date.parse(data.ends_at) < Date.parse(data.starts_at)) throw new Error('End must follow start.');
    if (data.outcome_happened_at && Date.parse(data.outcome_happened_at) > Date.now()) throw new Error('Claimed occurrence cannot be in the future.');
    submit(data);
  } catch (error) { setError(error.message); } }, onKeyDown: e => { if (e.key === 'Escape' && !busy) { e.preventDefault(); cancel(); } } },
    h('h3', null, `${relLabel(action || (row ? 'Edit' : 'Create'))} ${action === 'task' ? 'associated task' : kind === 'companies' ? 'Company' : 'Event'}`),
    kind === 'events' && h('p', { className: 'hc-muted' }, 'Local CRM record only. Saving does not invite, call, send, schedule a reminder, research, attach files or sync a calendar. Completion is your self-reported claim. Related records are context, not verified attendees. Notes are ordinary plaintext.'),
    action === 'task' && h('p', { className: 'hc-muted' }, 'Review the exact contact and deal context prefilled from this Event below, or clear each selection for an Event-only task. No Company is inferred. The explicit Event link remains separate from the task’s direct contact or deal context.'),
    fields.map((key, index) => h('label', { key }, relLabel(key), key === 'kind' ? h('select', { value: values[key], disabled: busy || pending, onChange: e => change(key, e.target.value) }, h('option', { value: 'appointment' }, 'Appointment'), h('option', { value: 'call' }, 'Call')) : h(['notes', 'reason', 'outcome_summary'].includes(key) ? 'textarea' : 'input', { ref: index === 0 ? first : undefined, value: values[key], disabled: busy || pending, required: !['domain', 'notes'].includes(key), placeholder: key.endsWith('_at') ? '2026-11-09T14:00:00-05:00' : key === 'timezone' ? 'America/New_York' : undefined, onChange: e => change(key, e.target.value) }))),
    kind === 'events' && (!action || action === 'task') && (action === 'task' ? ['contacts', 'deals'] : ['contacts', 'deals', 'companies']).map(entity => { const key = entity === 'companies' ? 'company_id' : `${entity.slice(0, -1)}_id`; return h(RelationshipSelector, { key, session, kind: entity, label: `Related ${entity}`, value: values[key], disabled: busy || pending, onChange: id => change(key, id) }); }),
    error && h('p', { role: 'alert' }, error), h('div', { className: 'hc-actions' }, h('button', { type: 'submit', disabled: busy || pending, className: 'hc-primary' }, busy ? 'Saving…' : 'Save'), relButton('Cancel', cancel, busy)));
}
export function Relationships({ client, workspaceToken, page = 'companies', initial = null, open, onSaved, disabled = false, operationStore = null }) {
  const sessionRef = useRef(null);
  if (!sessionRef.current) sessionRef.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = sessionRef.current;
  const operationGeneration = useRelationshipStatus(session);
  const [selected, setSelected] = useState(initial), [record, setRecord] = useState(null), [form, setForm] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0), [taskChoice, setTaskChoice] = useState(null), [query, setQuery] = useState(''), [archived, setArchived] = useState(false), [eventStatus, setEventStatus] = useState(''), [eventKind, setEventKind] = useState('');
  const mutationLock = useRef(false);
  const root = useRef(null);
  const sequence = useRef(0), heading = useRef(null), returnFocus = useRef(null);
  useEffect(() => { session.activate(); return () => { session.close(); sequence.current++; }; }, [session]);
  const kind = selected?.kind || (page === 'companies' ? 'companies' : 'events');
  useEffect(() => { let live = true; if (selected) session.read(`/${selected.kind}/${encodeURIComponent(selected.id)}`).then(value => { if (live && value) { setRecord(value.company || value.event || value); heading.current?.focus(); } }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [session, selected, revision, operationGeneration]);
  function select(entity, id) { if (busy) return; sequence.current++; setForm(null); setError(''); if (['companies', 'events'].includes(entity)) { setRecord(null); setSelected({ kind: entity, id }); } else open(entity, id); }
  useEffect(() => { if (!form) { if (returnFocus.current?.isConnected) returnFocus.current.focus(); else (heading.current || root.current)?.focus(); } }, [record?.id, form]);
  function cancel() { setForm(null); }
  function edit(action = '') { returnFocus.current = root.current?.ownerDocument.activeElement; setForm({ action, expectedVersion: record?.version }); setError(''); }
  async function write(path, method, body, retry = false) {
    if (mutationLock.current || disabled) return; mutationLock.current = true; const ticket = ++sequence.current; setBusy(true); setError('');
    try { const result = await (retry ? session.retry() : session.write(path, method, body)); if (result && session.valid() && ticket === sequence.current) { setForm(null); setRevision(v => v + 1); onSaved?.(); returnFocus.current?.focus(); } } catch (error) { if (session.valid() && ticket === sequence.current) setError(error.message); } finally { mutationLock.current = false; if (session.valid() && ticket === sequence.current) setBusy(false); }
  }
  function save(values) {
    const action = form.action; const base = `/${kind}${record ? '/' + encodeURIComponent(record.id) : ''}`;
    const body = record ? { expected_version: form.expectedVersion } : {};
    if (['cancel', 'reopen', 'needs-rescheduling'].includes(action)) body.reason = values.reason; else body.data = values;

    write(`${base}${action ? '/' + (action === 'task' ? 'tasks' : action) : ''}`, record && !action ? 'PATCH' : 'POST', body);
  }
  const pending = session.pending(), locked = busy || disabled || !!pending;
  return h('section', { ref: root, tabIndex: -1, className: 'hc-relationships', 'aria-label': 'Companies and relationship events' },
    error && h('div', null, h('p', { role: 'alert', className: 'hc-notice' }, error), selected && relButton('Refresh current record (keep draft)', () => setRevision(v => v + 1), busy)), pending?.state === 'unknown' && relButton('Retry original request', () => write('', '', {}, true), busy || disabled),
    form?.action === 'link-task' ? h('section', null, h(RelationshipSelector, { session, kind: 'tasks', label: 'Select exact existing task', value: taskChoice?.id, onChange: (id, row) => setTaskChoice(id ? row : null), disabled: locked }), relButton('Link selected task', () => write(`/tasks/${encodeURIComponent(taskChoice.id)}/event`, 'PUT', { event_id: record.id, expected_version: record.version, expected_task_version: taskChoice.version }), locked || !taskChoice), relButton('Cancel', cancel, busy)) : form ? h('div', null, form.expectedVersion !== record?.version && record && h('div', null, h('p', null, `Record is now version ${record.version}. Review current values before using this draft.`), h('dl', null, Object.entries(record).filter(([key, value]) => ['name','title','domain','notes','starts_at','ends_at','timezone','status'].includes(key) && value != null).map(([key, value]) => h('div', { key }, h('dt', null, relLabel(key)), h('dd', null, String(value))))), relButton('Use refreshed version for this draft', () => setForm({ ...form, expectedVersion: record.version }), locked)), h(RelationshipForm, { key: `${kind}:${record?.id || 'new'}:${form.action}`, kind, row: record, action: form.action, session, submit: save, cancel, busy, pending: !!pending })) : selected ? h('div', null,
      relButton('Back to list', () => { sequence.current++; setSelected(null); setRecord(null); }, busy),
      !record ? h('p', { role: 'status' }, 'Loading record…') : h('section', { className: 'hc-record' },
        h('h2', { ref: heading, tabIndex: -1 }, relName(record)), h('p', { className: 'hc-record-meta' }, `${record.id} · Version ${record.version}`),
        kind === 'companies' ? h('div', null, h('p', null, `${record.domain || 'No domain'}${record.archived_at ? ' · Archived' : ''}`), h('p', null, record.notes), h('div', { className: 'hc-actions' }, relButton('Edit Company', () => edit(), locked), relButton(record.archived_at ? 'Restore Company' : 'Archive Company', () => write(`/companies/${encodeURIComponent(record.id)}/${record.archived_at ? 'restore' : 'archive'}`, 'POST', { expected_version: record.version }), locked)), h('p', { className: 'hc-muted' }, 'Current explicit relationships. Contacts have one primary Company. Deals follow their contact. Tasks follow their direct contact or deal contact; Event-linked tasks also show their Event basis. Events retain their own explicit Company. Domain is unverified text.'), ['contacts', 'deals', 'tasks', 'events'].map(entity => h(RelationshipRows, { key: entity, session, path: `/companies/${encodeURIComponent(record.id)}/records/${entity}`, title: relLabel(entity), kind: entity, open: select, revision: revision + operationGeneration, disabled: locked })), h(RelationshipRows, { session, path: '/relationship-activities', params: { company_id: record.id }, title: 'Company Activities · current relationship membership', open: select, revision: revision + operationGeneration, disabled: locked })) : h('div', null,
          h('p', null, `${relLabel(record.kind)} · ${relLabel(record.status)} · Local`), h('p', null, `${record.starts_at} → ${record.ends_at} · Display timezone: ${record.timezone}`), h('p', null, record.notes),
          record.status === 'completed' && h('p', null, `Self-reported completion: ${record.outcome_happened_at} · ${record.outcome_summary}. Recorded ${record.recorded_at || record.updated_at}. Not verified attendance or call.`),
          h('div', { className: 'hc-actions' }, ['contact', 'deal', 'company'].map(entity => record[`${entity}_id`] && relButton(`Open ${entity} · ${record[`${entity}_id`]}`, () => select(entity === 'company' ? 'companies' : `${entity}s`, record[`${entity}_id`]), locked, { key: entity }))),
          h('div', { className: 'hc-actions' }, ['scheduled', 'needs_rescheduling'].includes(record.status) && relButton('Edit Event', () => edit(), locked), ['scheduled', 'needs_rescheduling'].includes(record.status) && [ ['reschedule', 'Reschedule'], ['complete', 'Complete (self-reported)'], ['cancel', 'Cancel Event'], ...(record.status === 'scheduled' ? [['needs-rescheduling', 'Needs rescheduling']] : []) ].map(([action, caption]) => relButton(caption, () => edit(action), locked, { key: action })), ['completed', 'cancelled'].includes(record.status) && relButton('Reopen Event', () => edit('reopen'), locked), relButton('Create associated task', () => edit('task'), locked), relButton('Link existing task', () => { setTaskChoice(null); edit('link-task'); }, locked)),
          h(RelationshipRows, { session, path: `/events/${encodeURIComponent(record.id)}/tasks`, title: 'Associated tasks', kind: 'tasks', open: select, revision: revision + operationGeneration, disabled: locked }),
          h('p', { className: 'hc-muted' }, 'Open a task to use its genuine agent-assignment workflow. Creating or completing an Event does not assign work, perform research or complete its tasks.')))) : h('div', null,
      page !== 'activities' && h('div', { className: 'hc-actions' }, relButton(`Create ${page === 'companies' ? 'Company' : 'Event'}`, () => { setRecord(null); edit(); }, locked), h('label', null, 'Search', h('input', { value: query, disabled: busy, onChange: e => setQuery(e.target.value) })), page === 'companies' && h('label', null, h('input', { type: 'checkbox', checked: archived, onChange: e => setArchived(e.target.checked) }), 'Include archived')),
      page === 'events' && h('div', { className: 'hc-actions' }, h('label', null, 'Event status', h('select', { value: eventStatus, onChange: e => setEventStatus(e.target.value) }, ['', 'scheduled', 'needs_rescheduling', 'completed', 'cancelled'].map(value => h('option', { key: value, value }, value ? relLabel(value) : 'All statuses')))), h('label', null, 'Event kind', h('select', { value: eventKind, onChange: e => setEventKind(e.target.value) }, ['', 'appointment', 'call'].map(value => h('option', { key: value, value }, value || 'All kinds'))))),
      h(RelationshipRows, { key: `${page}:${query}:${archived}:${eventStatus}:${eventKind}`, session, path: page === 'activities' ? '/relationship-activities' : `/${page}`, params: page === 'activities' ? {} : { q: query, ...(page === 'companies' ? { include_archived: archived } : { ...(eventStatus ? { status: eventStatus } : {}), ...(eventKind ? { kind: eventKind } : {}) }) }, title: page === 'activities' ? 'Relationship Activities · self-reported' : relLabel(page), kind: page === 'activities' ? undefined : page, open: select, revision: revision + operationGeneration, disabled: locked })));
}

export function ContactCompany({ client, workspaceToken, contact, open, disabled, onSaved, operationStore = null }) {
  const sessionRef = useRef(null); if (!sessionRef.current) sessionRef.current = relationshipSession(client, workspaceToken, () => true, operationStore);
  const session = sessionRef.current; const operationGeneration = useRelationshipStatus(session); const [link, setLink] = useState(null), [editing, setEditing] = useState(false), [choice, setChoice] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [revision, setRevision] = useState(0);
  useEffect(() => { session.activate(); return () => session.close(); }, [session]);
  useEffect(() => { let live = true; session.read(`/contacts/${encodeURIComponent(contact.id)}/company`).then(row => { if (live && row) setLink(row); }).catch(e => { if (live) setError(e.message); }); return () => { live = false; }; }, [session, contact.id, revision, operationGeneration]);
  const mutationLock = useRef(false);
  const company = link?.company_id ? { id: link.company_id, name: link.company_name, archived_at: link.company_archived } : null;
  async function save(retry = false) { if (mutationLock.current || disabled) return; mutationLock.current = true; setBusy(true); setError(''); try { const result = await (retry ? session.retry() : session.write(`/contacts/${encodeURIComponent(contact.id)}/company`, 'PUT', { company_id: choice, expected_contact_version: link?.contact_version ?? contact.version })); if (result) { setEditing(false); setRevision(v => v + 1); onSaved?.(); } } catch (e) { if (session.valid()) setError(e.message); } finally { mutationLock.current = false; if (session.valid()) setBusy(false); } }
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, 'Primary Company'), company ? relButton(`${company.name} · ${company.id}${company.archived_at ? ' · archived' : ''}`, () => open('companies', company.id), disabled) : h('p', null, 'No explicit Company link.'), h('p', { className: 'hc-muted' }, `Legacy company text (unlinked): ${contact.company || 'Not set'}. No automatic name matching.`), error && h('p', { role: 'alert' }, error),
    session.pending()?.state === 'unknown' && relButton('Retry original request', () => save(true), busy || disabled),
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
  async function unlink(retry = false) { if (mutationLock.current || disabled) return; mutationLock.current = true; setBusy(true); setError(''); try { const result = await (retry ? session.retry() : session.write(`/tasks/${encodeURIComponent(task.id)}/event/unlink`, 'POST', { event_id: event.id, expected_version: event.version, expected_task_version: task.version })); if (result) onSaved?.(); } catch (e) { if (session.valid()) setError(e.message); } finally { mutationLock.current = false; if (session.valid()) setBusy(false); } }
  const mutationLock = useRef(false);
  const locked = busy || disabled || !!session.pending();
  return h('section', { className: 'hc-card hc-relationships' }, h('h3', null, 'Linked Event'), relButton(`${task.event_title || 'Event'} · ${task.event_id}`, () => open('events', task.event_id), disabled || busy), h('p', null, 'Association basis: explicit Event task link. Agent-work ownership is separate.'), error && h('p', { role: 'alert' }, error),
    session.pending()?.state === 'unknown' && relButton('Retry original request', () => unlink(true), busy || disabled),
    event ? h('div', null, h('p', null, `Unlink from ${event.title} · ${event.id} · Event version ${event.version} · Task version ${task.version}? This keeps both records.`), relButton('Unlink from reviewed Event', () => unlink(), locked), relButton('Cancel unlink', () => setEvent(null), busy)) : relButton('Review Event unlink', review, locked));
}
