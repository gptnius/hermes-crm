import { createElement as h, useEffect, useRef, useState } from "react";

// The caller's store is scoped to a native connection/profile. Tokens partition
// workspaces inside it. Never persist these operations in browser/global storage.
const taskOwnerPolicyStores = new WeakMap();
const taskOwnerPolicyStoreMeta = new WeakMap();
const taskOwnerPolicyObjectIds = new WeakMap();
let taskOwnerPolicyObjectSequence = 0;
function taskOwnerPolicyObjectId(object) {
  if (!object) return 0;
  if (!taskOwnerPolicyObjectIds.has(object)) taskOwnerPolicyObjectIds.set(object, ++taskOwnerPolicyObjectSequence);
  return taskOwnerPolicyObjectIds.get(object);
}
function taskOwnerPolicyValue(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      !Number.isSafeInteger(value.version) || value.version < 0 ||
      typeof value.required !== 'boolean' ||
      !(value.default_owner_label === null || (typeof value.default_owner_label === 'string' && value.default_owner_label.trim() && value.default_owner_label.length <= 160)) ||
      value.legacy_edit_rule !== 'owner_required_on_edit') throw new Error('The current task owner policy could not be verified. Refresh before editing.');
  return Object.freeze({ version: value.version, required: value.required, default_owner_label: value.default_owner_label, legacy_edit_rule: value.legacy_edit_rule });
}
function taskOwnerPolicyDraft(value) {
  if (!value || typeof value.required !== 'boolean' || !(value.default_owner_label == null || typeof value.default_owner_label === 'string')) throw new Error('Choose whether task owners are required and enter a valid default owner label.');
  const label = (value.default_owner_label || '').trim();
  if (label.length > 160) throw new Error('The default owner label must be 160 characters or fewer.');
  return Object.freeze({ required: value.required, default_owner_label: label || null });
}
function taskOwnerPolicySame(left, right) {
  return !!left && !!right && left.version === right.version && left.required === right.required && left.default_owner_label === right.default_owner_label && left.legacy_edit_rule === right.legacy_edit_rule;
}

export function taskOwnerPolicySession(client, workspaceToken, current = () => true, operationStore = null) {
  const store = operationStore || taskOwnerPolicyStores.get(client) || new Map();
  if (!operationStore) taskOwnerPolicyStores.set(client, store);
  if (!taskOwnerPolicyStoreMeta.has(store)) taskOwnerPolicyStoreMeta.set(store, { listeners: new Set(), scopes: new Map() });
  const shared = taskOwnerPolicyStoreMeta.get(store);
  if (!shared.scopes.has(workspaceToken)) shared.scopes.set(workspaceToken, { epoch: 0, draft: null, receipt: null, rejection: null });
  const meta = shared.scopes.get(workspaceToken);
  let alive = true, revoked = false, lifetime = 0, readSequence = 0, reviewed = null;
  const valid = () => {
    if (!alive || revoked) return false;
    if (!client.current() || !current()) { revoked = true; reviewed = null; return false; }
    return typeof workspaceToken === 'string' && workspaceToken.length > 0;
  };
  const notify = () => {
    meta.epoch++;
    for (const listener of shared.listeners) {
      // An observer cannot turn a confirmed write into an unknown outcome.
      try { listener(); } catch { /* Each panel owns its rendering errors. */ }
    }
  };
  const invalidateReview = () => { reviewed = null; readSequence++; };
  async function read() {
    if (!valid()) return null;
    const sequence = ++readSequence, generation = lifetime, epoch = meta.epoch;
    reviewed = null;
    try {
      const value = await client.request(`/task-owner-policy?${new URLSearchParams({ workspace_token: workspaceToken })}`);
      if (!valid() || generation !== lifetime || sequence !== readSequence || epoch !== meta.epoch) return null;
      return taskOwnerPolicyValue(value);
    } catch (error) {
      if (!valid() || generation !== lifetime || sequence !== readSequence || epoch !== meta.epoch) return null;
      throw error;
    }
  }
  async function perform(attempt) {
    const generation = lifetime;
    attempt.state = 'running';
    notify();
    let result;
    try {
      const response = await client.request(attempt.path, { method: 'PATCH', body: JSON.parse(attempt.payload) });
      result = taskOwnerPolicyValue(response);
      const sent = JSON.parse(attempt.payload).data;
      if (result.version !== sent.version + 1 || result.required !== sent.required || result.default_owner_label !== sent.default_owner_label) throw new Error('The save receipt did not match the reviewed policy.');
    } catch (error) {
      if (store.get(workspaceToken) !== attempt) return null;
      const status = Number(error.status ?? error.statusCode);
      if ([400, 404, 409, 422].includes(status)) {
        store.delete(workspaceToken);
        meta.draft = taskOwnerPolicyDraft(JSON.parse(attempt.payload).data);
        meta.rejection = Object.freeze({ status, message: 'The policy save was rejected. Your draft is retained. Refresh the current policy, then review your changes again before saving.' });
        notify();
        if (valid() && generation === lifetime) throw Object.assign(new Error(meta.rejection.message), { status, rejected: true });
        return null;
      }
      attempt.state = 'unknown';
      notify();
      if (valid() && generation === lifetime) throw new Error('Save outcome unknown. The original request is retained. Retry only that exact request before making another policy change.');
      return null;
    }
    if (store.get(workspaceToken) === attempt) {
      store.delete(workspaceToken);
      meta.receipt = result;
      meta.draft = null;
      meta.rejection = null;
      notify();
    }
    return valid() && generation === lifetime ? result : null;
  }
  return {
    valid,
    activate() { alive = true; lifetime++; invalidateReview(); },
    close() { alive = false; lifetime++; invalidateReview(); },
    subscribe(listener) { shared.listeners.add(listener); return () => shared.listeners.delete(listener); },
    pending: () => store.get(workspaceToken) || null,
    snapshot: () => ({ ...meta }),
    invalidateReview,
    read,
    async review(draft, expectedPolicy) {
      if (!valid() || store.has(workspaceToken)) return null;
      const values = taskOwnerPolicyDraft(draft);
      const policy = await read();
      if (!policy || store.has(workspaceToken)) return null;
      if (!expectedPolicy || !taskOwnerPolicySame(policy, expectedPolicy)) return Object.freeze({ changed: true, policy });
      if (policy.version >= Number.MAX_SAFE_INTEGER) throw new Error('This policy version cannot be safely updated.');
      reviewed = Object.freeze({ policy, data: Object.freeze({ version: policy.version, ...values }), epoch: meta.epoch, lifetime });
      return reviewed;
    },
    write(review) {
      if (!valid() || store.has(workspaceToken) || !review || review !== reviewed || review.epoch !== meta.epoch || review.lifetime !== lifetime) return Promise.resolve(null);
      const payload = JSON.stringify({ workspace_token: workspaceToken, idempotency_key: crypto.randomUUID(), data: review.data });
      const attempt = { state: 'running' };
      Object.defineProperties(attempt, { path: { value: '/task-owner-policy', enumerable: true }, payload: { value: payload, enumerable: true } });
      Object.seal(attempt);
      reviewed = null;
      meta.draft = taskOwnerPolicyDraft(review.data);
      meta.rejection = null;
      store.set(workspaceToken, attempt);
      return perform(attempt);
    },
    retry() {
      const attempt = store.get(workspaceToken);
      return valid() && attempt?.state === 'unknown' ? perform(attempt) : Promise.resolve(null);
    },
    discardDraft() {
      if (store.has(workspaceToken)) return;
      meta.draft = null; meta.rejection = null; reviewed = null;
    },
  };
}

// A changed connection, profile store, or workspace gets a fresh React lifetime.
// Old event handlers and async work still reference the closed original session.
export function TaskOwnerPolicyPanel(props) {
  const key = JSON.stringify([taskOwnerPolicyObjectId(props.client), taskOwnerPolicyObjectId(props.operationStore), props.workspaceToken]);
  return h(TaskOwnerPolicyView, { ...props, key });
}
function TaskOwnerPolicyView({ Drawer, client, workspaceToken, current = () => true, operationStore, cancel, onSaved, returnFocus }) {
  const currentRef = useRef(current), savedRef = useRef(onSaved);
  currentRef.current = current; savedRef.current = onSaved;
  const sessionRef = useRef(null);
  if (!sessionRef.current) sessionRef.current = taskOwnerPolicySession(client, workspaceToken, () => currentRef.current(), operationStore);
  const session = sessionRef.current;
  const [policy, setPolicy] = useState(null), [draft, setDraft] = useState(() => session.snapshot().draft);
  const [review, setReview] = useState(null), [loading, setLoading] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [discard, setDiscard] = useState(false);
  const [refreshNeeded, setRefreshNeeded] = useState(false), [, setGeneration] = useState(0);
  const localLock = useRef(false), mounted = useRef(false), loadId = useRef(0);
  const seen = useRef(session.snapshot()), refreshLock = useRef(false);
  const active = () => mounted.current && session.valid();
  async function refreshSaved(receipt) {
    if (!active() || refreshLock.current) return;
    refreshLock.current = true;
    try {
      const refreshed = savedRef.current ? await savedRef.current(receipt) : true;
      if (!active() || session.snapshot().receipt !== receipt) return;
      if (refreshed === false) throw new Error('Record refresh failed.');
      setRefreshNeeded(false);
      setNotice(`Task owner policy saved as version ${receipt.version}.`);
    } catch {
      if (active() && session.snapshot().receipt === receipt) {
        setRefreshNeeded(true);
        setNotice('The policy was saved, but the CRM view could not be refreshed. Refresh the saved view. This does not resend the policy change.');
      }
    } finally { refreshLock.current = false; }
  }
  async function load() {
    if (!active() || localLock.current || session.pending()) return;
    localLock.current = true;
    const id = ++loadId.current;
    setLoading(true); setReview(null); setError('');
    try {
      const value = await session.read();
      if (!active() || id !== loadId.current) return;
      if (!value) { setError('The policy changed while loading. Refresh it before reviewing your changes.'); return; }
      setPolicy(value);
      setDraft(old => old || taskOwnerPolicyDraft(value));
      if (policy && !taskOwnerPolicySame(policy, value)) setNotice('The policy changed. Your draft is retained. Review it against the current policy before saving.');
    } catch {
      if (active() && id === loadId.current) setError('The current policy could not be loaded. No changes were sent. Refresh the policy to try again.');
    } finally {
      if (id === loadId.current) { localLock.current = false; if (active()) setLoading(false); }
    }
  }
  useEffect(() => {
    mounted.current = true; session.activate();
    const unsubscribe = session.subscribe(() => {
      if (!active()) return;
      const state = session.snapshot();
      setGeneration(value => value + 1);
      if (state.epoch !== seen.current.epoch) { setReview(null); session.invalidateReview(); }
      if (state.receipt && state.receipt !== seen.current.receipt) {
        setPolicy(state.receipt); setDraft(taskOwnerPolicyDraft(state.receipt)); setError('');
        setNotice(`Task owner policy saved as version ${state.receipt.version}.`);
        void refreshSaved(state.receipt);
      }
      if (state.rejection && state.rejection !== seen.current.rejection) {
        setPolicy(null); setDraft(state.draft); setError(state.rejection.message); setNotice('');
      }
      seen.current = state;
    });
    if (session.snapshot().rejection) setError(session.snapshot().rejection.message);
    if (!session.pending()) void load();
    return () => { mounted.current = false; loadId.current++; localLock.current = false; session.close(); unsubscribe(); };
  }, [session]);
  function change(key, value) {
    if (!active() || localLock.current || session.pending() || refreshNeeded) return;
    session.invalidateReview(); setReview(null); setError(''); setNotice('');
    setDraft(old => ({ ...old, [key]: value }));
  }
  async function prepare(event) {
    event?.preventDefault();
    if (!active() || localLock.current || session.pending() || !policy || !draft || refreshNeeded) return;
    localLock.current = true; setLoading(true); setReview(null); setError(''); setNotice('');
    try {
      const value = await session.review(draft, policy);
      if (!active()) return;
      if (!value) { setError('The policy changed while reviewing. Refresh and review it again.'); return; }
      setPolicy(value.policy);
      if (value.changed) setNotice('The current policy changed since it was loaded. Your draft is retained. Review changes again against this version.');
      else setReview(value);
    } catch (cause) { if (active()) setError(cause.message); }
    finally { localLock.current = false; if (active()) setLoading(false); }
  }
  async function save() {
    if (!active() || localLock.current || session.pending() || !review || refreshNeeded) return;
    setError(''); setNotice('');
    try { await session.write(review); }
    catch (cause) { if (active()) setError(cause.message); }
  }
  async function retry() {
    if (!active() || localLock.current) return;
    setError('');
    try { await session.retry(); }
    catch (cause) { if (active()) setError(cause.message); }
  }
  const pending = session.pending(), valid = active();
  const locked = !valid || loading || !!pending || refreshNeeded;
  const dirty = !!draft && (!policy || draft.required !== policy.required || (draft.default_owner_label || '') !== (policy.default_owner_label || ''));
  function dismiss() {
    if (pending || dirty) { setDiscard(true); return; }
    close();
  }
  function close() {
    session.discardDraft(); mounted.current = false; session.close(); cancel();
  }
  const button = (text, action, disabled = false, props = {}) => h('button', { type: 'button', onClick: action, disabled, ...props }, text);
  const frozen = pending ? JSON.parse(pending.payload).data : null;
  const preview = review?.data || frozen;
  return h(Drawer, { title: 'Task owner policy', subtitle: 'Set human accountability for tasks in this workspace.', busy: false, cancel: dismiss, returnFocus },
    h('div', { className: 'hc-editor-body' },
      h('p', { className: 'hc-muted' }, 'An owner label records human accountability. It is not an access-control permission, verified identity, or agent executor.'),
      h('p', { className: 'hc-notice' }, 'When owners are required, new tasks and task-detail edits need an owner, including completion and reopening. Existing ownerless tasks require a deliberate owner choice for those edits. Scheduler bookkeeping and relationship-only maintenance do not require owners. This policy does not backfill tasks or apply a default silently.'),
      policy && h('section', { className: 'hc-form-section', 'aria-label': 'Current task owner policy' },
        h('h3', null, `Current policy · Version ${policy.version}`),
        h('p', null, `Owners: ${policy.required ? 'Required' : 'Optional'} · Default owner: ${policy.default_owner_label || 'Not set'}`)),
      !policy && !pending && h('p', { role: 'status' }, loading ? 'Loading current policy…' : 'Load the current policy before reviewing changes.'),
      draft && h('form', { onSubmit: prepare, 'aria-label': 'Task owner policy editor' },
        h('fieldset', { className: 'hc-form-section', disabled: locked },
          h('legend', null, 'Workspace task ownership'),
          h('div', { className: 'hc-fields' },
            h('label', { className: 'hc-wide' }, h('span', null, 'Require an owner for new tasks and task-detail edits'),
              h('input', { type: 'checkbox', name: 'owner_required', checked: draft.required, disabled: locked, onChange: event => change('required', event.target.checked) })),
            h('label', { className: 'hc-wide' }, h('span', null, 'Default human owner label (optional)'),
              h('input', { type: 'text', name: 'default_owner_label', value: draft.default_owner_label || '', maxLength: 160, disabled: locked, onChange: event => change('default_owner_label', event.target.value) }),
              h('small', { className: 'hc-field-hint' }, 'Up to 160 characters. Leave blank to remove the default. Task forms must explicitly review and choose the default.')))),
        h('div', { className: 'hc-actions' }, h('button', { type: 'submit', disabled: locked || !policy }, loading ? 'Checking current policy…' : 'Review changes'))),
      preview && h('section', { className: 'hc-notice', 'aria-label': 'Reviewed policy changes' },
        h('h3', null, frozen ? 'Original pending policy change' : 'Review before saving'),
        h('p', null, `Policy version ${preview.version} → ${preview.version + 1}`),
        h('p', null, `Owners will be ${preview.required ? 'required' : 'optional'}. Default owner: ${preview.default_owner_label || 'Not set'}.`),
        h('p', null, 'Existing task owners stay unchanged. When this policy is required, ownerless legacy tasks need a deliberate owner choice on their next task-detail edit, completion, or reopening. Scheduler bookkeeping and relationship-only maintenance remain unaffected.'),
        frozen ? h('p', null, pending.state === 'running' ? 'The original save is still running. Closing does not cancel it.' : 'The save outcome is unknown. The original key and reviewed fields are retained across closing and reopening.')
          : button('Save reviewed policy', save, locked, { className: 'hc-primary' })),
      error && h('p', { className: 'hc-notice', role: 'alert' }, error),
      notice && h('p', { className: 'hc-notice', role: 'status' }, notice),
      h('div', { className: 'hc-actions' },
        button('Refresh current policy', load, !valid || loading || !!pending),
        pending?.state === 'unknown' && button('Retry exact policy save', retry, !valid || loading),
        refreshNeeded && button('Refresh saved view', () => refreshSaved(session.snapshot().receipt), !valid),
        button('Close', dismiss)),
      discard && h('section', { className: 'hc-notice', role: 'alert', 'aria-label': 'Confirm policy dismissal' },
        h('p', null, pending ? 'Close this panel and keep the original pending request? Reopen Task owner policy to recover it. Closing does not cancel or repeat the save.' : 'Discard unsaved policy changes?'),
        h('div', { className: 'hc-actions' }, button('Keep editing', () => setDiscard(false)), button(pending ? 'Close and keep pending request' : 'Discard changes', close)))));
}
