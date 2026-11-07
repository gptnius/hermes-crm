import { createElement as h, useEffect, useRef, useState } from 'react';

const contactLogAttempts = new WeakMap();
export function contactLogDate(value) {
  // Require an explicit offset; never silently reinterpret an existing UTC time.
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d(?:\.\d{1,3})?)?(?:Z|[+-]\d\d:\d\d)$/.test(value.trim())) throw new Error('Enter an ISO date and time with Z or an explicit timezone offset.');
  const [year, month, day] = value.trim().slice(0, 10).split('-').map(Number);
  if (month < 1 || month > 12 || day < 1 || day > new Date(Date.UTC(year, month, 0)).getUTCDate()) throw new Error('Contact date is not a valid calendar date.');
  const date = new Date(value.trim());
  if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) throw new Error('Contact time must be valid and cannot be in the future.');
  return date.toISOString();
}
export function contactLogSession(client, workspaceToken, contact, isCurrent = () => true, operationStore = null) {
  let alive = true, readSequence = 0;
  const scope = JSON.stringify([workspaceToken, contact.id]);
  const attempts = operationStore || contactLogAttempts.get(client) || new Map();
  contactLogAttempts.set(client, attempts);
  const current = () => alive && client.current() && isCurrent();
  async function perform(attempt) {
    attempt.state = 'running';
    try {
      const result = await client.request(attempt.path, { method: 'POST', body: JSON.parse(attempt.payload) });
      if (!result || typeof result.id !== 'string' || !Number.isSafeInteger(result.version)) throw new Error('Unconfirmed receipt');
      if (attempts.get(scope) === attempt) attempts.delete(scope);
      return current() ? result : null;
    } catch (error) {
      // Only explicit API rejection statuses prove this request did not commit.
      // Transport failures, server failures and malformed receipts stay locked.
      if ([400, 404, 409, 422].includes(Number(error?.status ?? error?.statusCode))) {
        if (attempts.get(scope) === attempt) attempts.delete(scope);
        throw new Error('Write rejected. Refresh the contact and contact log, review the current version, then save your claim or correction again.');
      }
      attempt.state = 'unknown';
      throw new Error('Outcome unknown or conflicted. New writes are blocked. Retry sends only the original request with the same key; refresh does not clear this pending claim.');
    }
  }
  function submit(path, body) {
    if (!current() || attempts.has(scope)) return Promise.resolve(null);
    const attempt = { path, payload: JSON.stringify({ ...body, workspace_token: workspaceToken, idempotency_key: crypto.randomUUID() }), state: 'running' };
    attempts.set(scope, attempt);
    return perform(attempt);
  }
  return {
    current, close() { alive = false; readSequence++; }, pending: () => attempts.get(scope),
    async load(offset = 0) {
      if (!current()) return null;
      const ticket = ++readSequence;
      const result = await client.request(`/interactions?${new URLSearchParams({ workspace_token: workspaceToken, contact_id: contact.id, limit: '25', offset: String(offset), include_voided: 'true' })}`);
      if (!current() || ticket !== readSequence) return null;
      if (!result || !Array.isArray(result.items) || !Number.isSafeInteger(result.total) || result.total < 0) throw new Error('Invalid contact log response');
      return result;
    },
    create(values) {
      if (!current() || attempts.has(scope)) return Promise.resolve(null);
      const summary = String(values.summary || '').trim();
      if (!summary || summary.length > 2000) throw new Error('Summary is required and must be at most 2,000 characters.');
      if (!['meeting', 'call', 'email', 'chat', 'other'].includes(values.kind) || !['inbound', 'outbound', 'other'].includes(values.direction)) throw new Error('Choose a valid kind and direction.');
      return submit('/interactions', { data: { contact_id: contact.id, happened_at: contactLogDate(values.happened_at), kind: values.kind, direction: values.direction, summary }, expected_contact_version: contact.version });
    },
    void(item, reason) {
      if (!current() || attempts.has(scope)) return Promise.resolve(null);
      reason = String(reason || '').trim();
      if (!reason || reason.length > 500 || item.voided_at) throw new Error('Provide a correction reason of 1–500 characters for an active entry.');
      return submit(`/interactions/${encodeURIComponent(item.id)}/void`, { expected_version: item.version, reason });
    },
    retry() {
      const attempt = attempts.get(scope);
      return current() && attempt?.state === 'unknown' ? perform(attempt) : Promise.resolve(null);
    },
  };
}
const contactLogBlank = () => ({ happened_at: new Date().toISOString(), kind: 'meeting', direction: 'other', summary: '' });
export function ContactLogPanel({ client, contact, workspaceToken, routeKey, disabled = false, operationStore = null }) {
  const target = JSON.stringify([routeKey, workspaceToken, contact.id, contact.version]);
  const renderToken = {}, renderRef = useRef(renderToken); renderRef.current = renderToken;
  const actionLock = useRef(false);
  const latest = useRef(null); latest.current = { target, client, disabled };
  const session = useRef(null);
  const [view, setView] = useState(null), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const [form, setForm] = useState(null), [correction, setCorrection] = useState(null), [reason, setReason] = useState('');
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    const own = contactLogSession(client, workspaceToken, contact, () => latest.current.target === target && latest.current.client === client, operationStore);
    session.current = own; actionLock.current = false;
    setView(null); setNotice(''); setBusy(false); setForm(null); setCorrection(null); setReason(''); setOffset(0);
    own.load().then(data => { if (data) setView({ target, data, offset: 0 }); }).catch(() => { if (own.current()) setNotice('Contact log could not be loaded.'); });
    return () => own.close();
  }, [client, target, operationStore]);
  const own = session.current;
  const current = () => own && own.current() && latest.current.target === target && latest.current.client === client;
  const valid = () => current() && renderRef.current === renderToken && !latest.current.disabled && !actionLock.current;
  const pending = own?.pending();
  const locked = disabled || busy || !!pending || !current();
  const visible = view?.target === target && client.current() ? view : null;
  async function load(page, internal = false) {
    if (!current() || latest.current.disabled || (!internal && !valid())) return;
    try { const data = await own.load(page); if (data) { setView({ target, data, offset: page }); setOffset(page); } }
    catch { if (current()) setNotice('Contact log could not be loaded.'); }
  }
  async function write(action, retry = false) {
    if (!valid() || busy || (own.pending() && !retry)) return;
    actionLock.current = true; setBusy(true); setNotice('');
    try {
      const result = await action();
      if (result && current()) { setForm(null); setCorrection(null); setReason(''); setNotice('Contact log saved. This is a self-reported claim.'); await load(0, true); }
    } catch (error) { if (current()) setNotice(error.message); }
    finally { if (current()) { actionLock.current = false; setBusy(false); } }
  }
  function field(name, value) { if (valid() && !locked) setForm({ ...form, [name]: value }); }
  return h('section', { className: 'hc-card hc-contact-log', 'aria-label': 'Logged contact' },
    h('h3', null, 'Logged contact'),
    h('p', { className: 'hc-contact-log-help' }, 'Records your claim only; does not send mail, make calls or prove delivery. Last logged contact in reports uses active self-reported entries.'),
    h('p', { role: 'status', 'aria-live': 'polite', className: notice || pending ? 'hc-contact-log-notice' : 'hc-contact-log-status' }, notice || (pending ? 'A claim is pending. New writes are blocked.' : '')),
    !visible && !notice && h('p', { role: 'status', className: 'hc-contact-log-empty' }, 'Loading contact log…'),
    h('div', { className: 'hc-contact-log-actions' }, pending?.state === 'unknown' && h('button', { type: 'button', disabled: disabled || busy || !current(), onClick: () => write(() => own.retry(), true) }, 'Retry original request'),
    h('button', { type: 'button', disabled: disabled || busy || !current(), onClick: () => load(offset) }, 'Refresh contact log'),
    h('button', { type: 'button', className: 'hc-primary', disabled: locked || !!form || !!correction, onClick: () => { if (valid() && !locked) setForm(contactLogBlank()); } }, 'Log contact')),
    form && h('form', { className: 'hc-contact-log-form', 'aria-label': 'Log contact', onSubmit: event => { event.preventDefault(); write(() => own.create(form)); } },
      h('label', null, 'Contact time (ISO, explicit timezone; Z means UTC)', h('input', { required: true, value: form.happened_at, disabled: locked, onChange: event => field('happened_at', event.target.value) })),
      h('label', null, 'Kind', h('select', { value: form.kind, disabled: locked, onChange: event => field('kind', event.target.value) }, ['meeting', 'call', 'email', 'chat', 'other'].map(value => h('option', { key: value }, value)))),
      h('label', null, 'Direction', h('select', { value: form.direction, disabled: locked, onChange: event => field('direction', event.target.value) }, ['inbound', 'outbound', 'other'].map(value => h('option', { key: value }, value)))),
      h('label', { className: 'hc-contact-log-summary' }, 'Summary (your claim)', h('textarea', { required: true, maxLength: 2000, value: form.summary, disabled: locked, onChange: event => field('summary', event.target.value) })),
      h('button', { type: 'submit', className: 'hc-primary', disabled: locked }, busy ? 'Saving contact log…' : 'Save contact log'), h('button', { type: 'button', disabled: locked, onClick: () => { if (valid() && !locked) setForm(null); } }, 'Cancel')),
    correction && h('form', { className: 'hc-contact-log-correction', 'aria-label': 'Correct contact log', onSubmit: event => { event.preventDefault(); write(() => own.void(correction, reason)); } },
      h('p', null, 'Void this claim as a correction. The original entry and reason remain visible.'),
      h('label', null, 'Correction reason', h('textarea', { required: true, maxLength: 500, disabled: locked, value: reason, onChange: event => { if (valid() && !locked) setReason(event.target.value); } })),
      h('button', { type: 'submit', disabled: locked }, 'Confirm void'), h('button', { type: 'button', disabled: locked, onClick: () => { if (valid() && !locked) { setCorrection(null); setReason(''); } } }, 'Cancel correction')),
    visible && h('div', { className: 'hc-contact-log-history' },
      h('p', { className: visible.data.total ? 'hc-contact-log-help' : 'hc-contact-log-empty' }, visible.data.total ? `Showing ${visible.offset + 1}–${visible.offset + visible.data.items.length} of ${visible.data.total} entries (including voided).` : 'No logged contact.'),
      h('ul', { className: 'hc-contact-log-list', 'aria-label': 'Contact log entries' }, visible.data.items.map(item => h('li', { key: item.id, className: item.voided_at ? 'hc-contact-log-entry is-voided' : 'hc-contact-log-entry' },
        h('time', { dateTime: item.happened_at, title: item.happened_at }, item.happened_at),
        h('span', { className: 'hc-contact-log-meta' }, ` · ${item.kind} · ${item.direction} · Self-reported · Author: ${typeof item.actor === 'string' ? item.actor : 'Unknown'}`),
        h('p', null, item.summary),
        item.voided_at ? h('p', { className: 'hc-contact-log-voided' }, `Voided ${item.voided_at} by ${item.void_actor || 'Unknown'}: ${item.void_reason}`) : h('button', { type: 'button', disabled: locked || !!form || !!correction, onClick: () => { if (valid() && !locked) { setCorrection(item); setReason(''); } } }, 'Void entry')))),
      h('button', { type: 'button', disabled: disabled || busy || visible.offset === 0, onClick: () => load(Math.max(0, visible.offset - 25)) }, 'Previous entries'),
      h('button', { type: 'button', disabled: disabled || busy || visible.offset + 25 >= visible.data.total, onClick: () => load(visible.offset + 25) }, 'Next entries')));
}
