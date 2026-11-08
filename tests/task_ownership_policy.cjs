// Dependency-free session tests; set HERMES_CRM_REACT_TEST_ROOT for real React UI coverage.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const source = fs.readFileSync(path.join(__dirname, '../desktop/task-ownership.js'), 'utf8')
  .replace(/^import[^\n]+\n/, '').replace(/export function /g, 'function ');
function load(React = {}) {
  const context = vm.createContext({ URLSearchParams, crypto: require('node:crypto').webcrypto,
    h: React.createElement, useEffect: React.useEffect, useRef: React.useRef, useState: React.useState });
  vm.runInContext(source + '\nglobalThis.api = {taskOwnerPolicySession,TaskOwnerPolicyPanel};', context);
  return context.api;
}
const { taskOwnerPolicySession } = load();
const initial = { version: 0, required: false, default_owner_label: null, legacy_edit_rule: 'owner_required_on_edit' };
const draft = { required: true, default_owner_label: '  Alice  ' };
const copy = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const receipt = body => ({ ...body.data, version: body.data.version + 1, legacy_edit_rule: 'owner_required_on_edit' });

async function sessions() {
  let policy = { ...initial }, calls = [], mode = 'success', pendingRequest;
  const client = { current: () => true, request: async (url, options) => {
    calls.push({ url, options: options && copy(options) });
    if (!options) return copy(policy);
    if (mode === 'deferred') { pendingRequest = deferred(); return pendingRequest.promise; }
    if (mode === 'unknown') throw new Error('Lost response');
    if (mode === 'rejected') throw Object.assign(new Error('Conflict'), { status: 409 });
    if (mode === 'bad') return { ...receipt(options.body), required: !options.body.data.required };
    policy = receipt(options.body); return copy(policy);
  } };
  const store = new Map(), session = taskOwnerPolicySession(client, 'workspace & one', () => true, store);
  assert.deepEqual(copy(await session.read()), initial);
  assert.equal(calls[0].url, '/task-owner-policy?workspace_token=workspace+%26+one');
  assert.equal(await session.write({ data: { version: 0, ...draft } }), null, 'an unreviewed object cannot save');
  const noBase = await session.review(draft);
  assert.equal(noBase.changed, true, 'review requires a known current-policy baseline');
  assert.equal(await session.write(noBase), null);
  await assert.rejects(() => session.review({ ...draft, default_owner_label: 'x'.repeat(161) }, initial), /160/);
  const reviewed = await session.review(draft, initial);
  assert.deepEqual(copy(reviewed.data), { version: 0, required: true, default_owner_label: 'Alice' });
  session.invalidateReview();
  assert.equal(await session.write(reviewed), null, 'editing invalidates the preview synchronously');
  policy = { ...initial, version: 1, required: true };
  const changed = await session.review(draft, initial);
  assert.equal(changed.changed, true);
  assert.equal(await session.write(changed), null, 'newly discovered policy needs another review gesture');
  let fresh = await session.review(draft, changed.policy);
  mode = 'deferred';
  const submitted = session.write(fresh), frozen = copy(calls.at(-1));
  const sibling = taskOwnerPolicySession(client, 'workspace & one', () => true, store);
  assert.equal(sibling.pending().state, 'running');
  assert.equal(await sibling.review(draft, policy), null);
  assert.equal(await session.write(fresh), null, 'double-click does not repeat a write');
  assert.equal(await sibling.retry(), null, 'running request cannot be retried from another panel');
  assert.equal(frozen.options.method, 'PATCH');
  assert.equal(frozen.options.body.workspace_token, 'workspace & one');
  assert.ok(frozen.options.body.idempotency_key);
  const immutablePayload = sibling.pending().payload;
  try { sibling.pending().payload = '{}'; } catch {}
  assert.equal(sibling.pending().payload, immutablePayload);
  session.close();
  pendingRequest.reject(new Error('Lost reply after dismissal'));
  assert.equal(await submitted, null);
  assert.equal(sibling.pending().state, 'unknown');
  mode = 'bad';
  await assert.rejects(() => sibling.retry(), /unknown/);
  assert.deepEqual(calls.at(-1), frozen, 'a mismatched receipt keeps the original key and body');
  mode = 'rejected';
  await assert.rejects(() => sibling.retry(), /rejected/);
  assert.deepEqual(calls.at(-1), frozen);
  assert.equal(store.size, 0, 'confirmed conflict releases the pending operation');
  assert.deepEqual(copy(sibling.snapshot().draft), { required: true, default_owner_label: 'Alice' });
  assert.equal(await sibling.write(fresh), null, 'old preview cannot be reused after rejection');
  fresh = await sibling.review(sibling.snapshot().draft, policy);
  mode = 'success';
  sibling.subscribe(() => { throw new Error('Broken UI observer'); });
  const saved = await sibling.write(fresh);
  assert.equal(saved.version, 2);
  assert.equal(store.size, 0);
  assert.notEqual(calls.at(-1).options.body.idempotency_key, frozen.options.body.idempotency_key, 'fresh review after rejection creates a fresh intent');
  assert.equal(sibling.snapshot().draft, null);
  assert.equal(sibling.snapshot().rejection, null);
  fresh = await sibling.review({ required: false, default_owner_label: '   ' }, policy);
  assert.equal(fresh.data.default_owner_label, null);
  await sibling.write(fresh);
  assert.equal(policy.default_owner_label, null);

  // Read sequencing, mount ABA, client/profile revocation, and strict responses.
  const reads = [];
  let current = true;
  const reader = taskOwnerPolicySession({ current: () => true, request: () => { const d = deferred(); reads.push(d); return d.promise; } }, 'W', () => current);
  const first = reader.read(), second = reader.read();
  reads[1].resolve(initial); assert.equal((await second).version, 0);
  reads[0].resolve({ ...initial, version: 99 }); assert.equal(await first, null);
  const beforeClose = reader.read(); reader.close(); reader.activate();
  reads[2].resolve(initial); assert.equal(await beforeClose, null, 'unmount/remount cannot revive an earlier read');
  const beforeProfile = reader.read(); current = false; assert.equal(reader.valid(), false); current = true;
  reads[3].resolve(initial); assert.equal(await beforeProfile, null); assert.equal(reader.valid(), false, 'observed profile invalidation is permanent for a session');
  for (const value of [null, {}, { ...initial, version: true }, { ...initial, required: 0 }, { ...initial, default_owner_label: undefined }, { ...initial, legacy_edit_rule: 'backfill' }]) {
    const invalid = taskOwnerPolicySession({ current: () => true, request: async () => value }, 'W');
    await assert.rejects(() => invalid.read(), /verified/);
  }

  // Late confirmed receipts retire only their original scope without returning
  // data into a dismissed panel. A remounted observer is notified immediately.
  const lateStore = new Map(); let release; let notifications = 0;
  const lateClient = { current: () => true, request: async (_url, options) => options ? new Promise(resolve => { release = () => resolve(receipt(options.body)); }) : initial };
  const oldPanel = taskOwnerPolicySession(lateClient, 'late', () => true, lateStore);
  const later = oldPanel.write(await oldPanel.review(draft, initial)); oldPanel.close();
  const newPanel = taskOwnerPolicySession(lateClient, 'late', () => true, lateStore);
  newPanel.subscribe(() => notifications++); release();
  assert.equal(await later, null); assert.equal(newPanel.pending(), null); assert.equal(notifications, 1);
  assert.equal(newPanel.snapshot().receipt.default_owner_label, 'Alice');
  console.log('PASS task owner policy sessions: exact review/receipt, frozen scoped retries, double-click and shared locks, conflict draft recovery, read ordering, stale profile and lifecycle guards.');
}

async function react() {
  if (!process.env.HERMES_CRM_REACT_TEST_ROOT) {
    console.log('SKIP real React lifecycle tests: set HERMES_CRM_REACT_TEST_ROOT to installed React/react-test-renderer dependencies.'); return;
  }
  const requireReact = createRequire(path.join(process.env.HERMES_CRM_REACT_TEST_ROOT, 'package.json'));
  const React = requireReact('react'), Renderer = requireReact('react-test-renderer');
  const { act, createElement: h } = React;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const { TaskOwnerPolicyPanel } = load(React);
  const Drawer = ({ children, cancel }) => h('section', null, h('button', { onClick: cancel }, 'Drawer close'), children);
  let policy = { ...initial }, mode = 'success', calls = [], closed = 0, refreshes = 0, finish, tree;
  const client = { current: () => true, request: async (url, options) => {
    calls.push({ url, options: options && copy(options) });
    if (!options) return copy(policy);
    if (mode === 'deferred') return new Promise((resolve, reject) => { finish = { resolve, reject }; });
    if (mode === 'unknown') throw new Error('Lost reply');
    if (mode === 'rejected') throw Object.assign(new Error('Conflict'), { status: 409 });
    policy = receipt(options.body); return copy(policy);
  } };
  let valid = true, refreshFails = false;
  let props = { Drawer, client, workspaceToken: 'ui', current: () => valid, operationStore: new Map(), cancel: () => closed++, onSaved: async () => { refreshes++; return !refreshFails; } };
  const text = node => typeof node === 'string' ? node : node?.children?.map(text).join('') || '';
  const button = name => tree.root.findAllByType('button').find(node => text(node) === name);
  const click = async name => { await act(async () => { const found = button(name); assert.ok(found, name); assert.ok(!found.props.disabled, name); found.props.onClick(); }); };
  const form = () => tree.root.findByType('form');
  const edit = async (name, value) => { await act(async () => tree.root.findByProps({ name }).props.onChange({ target: { value, checked: value } })); };
  const review = async () => { await act(async () => form().props.onSubmit({ preventDefault() {} })); };
  const render = async () => { await act(async () => { if (tree) tree.update(h(TaskOwnerPolicyPanel, props)); else tree = Renderer.create(h(TaskOwnerPolicyPanel, props)); }); };
  const unmount = async () => { await act(async () => tree.unmount()); tree = null; };
  const writes = () => calls.filter(call => call.options);
  await render();
  assert.equal(writes().length, 0); assert.equal(calls.length, 1);
  assert.match(JSON.stringify(tree.toJSON()), /Version 0/);
  await edit('owner_required', true); await edit('default_owner_label', ' Alice ');
  await click('Drawer close'); assert.equal(closed, 0); assert.ok(button('Discard changes'));
  await click('Keep editing');
  policy = { ...initial, version: 1 };
  await review(); assert.equal(button('Save reviewed policy'), undefined, 'changed policy requires another explicit review');
  assert.equal(tree.root.findByProps({ name: 'default_owner_label' }).props.value, ' Alice ');
  await review(); assert.ok(button('Save reviewed policy')); assert.equal(writes().length, 0, 'review is read-only');
  await edit('default_owner_label', 'Bob'); assert.equal(button('Save reviewed policy'), undefined);
  await review();
  mode = 'deferred';
  await act(async () => { const save = button('Save reviewed policy').props.onClick; save(); save(); });
  assert.equal(writes().length, 1);
  const original = copy(writes()[0]);
  assert.equal(tree.root.findByProps({ name: 'default_owner_label' }).props.disabled, true);
  await click('Drawer close'); await click('Close and keep pending request'); assert.equal(closed, 1);
  await unmount(); await render();
  assert.equal(button('Retry exact policy save'), undefined, 'remount never retries a running write automatically');
  await act(async () => finish.reject(new Error('Late transport failure')));
  assert.ok(button('Retry exact policy save'), 'remounted panel observes late unknown state');
  mode = 'unknown'; await click('Retry exact policy save');
  assert.deepEqual(writes()[1], original);
  mode = 'rejected'; await click('Retry exact policy save');
  assert.deepEqual(writes()[2], original);
  assert.equal(button('Retry exact policy save'), undefined);
  assert.equal(tree.root.findByProps({ name: 'default_owner_label' }).props.value, 'Bob');
  assert.ok(button('Review changes').props.disabled, 'conflict needs current-policy refresh');
  policy = { ...policy, version: 2, required: true, default_owner_label: 'Another owner' };
  await click('Refresh current policy'); await review();
  mode = 'success'; refreshFails = true; await click('Save reviewed policy');
  assert.equal(writes().length, 4); assert.equal(refreshes, 1);
  assert.notEqual(writes()[3].options.body.idempotency_key, original.options.body.idempotency_key);
  assert.ok(button('Refresh saved view')); assert.ok(button('Review changes').props.disabled);
  refreshFails = false; await click('Refresh saved view');
  assert.equal(writes().length, 4, 'refresh after saved receipt does not repeat PATCH');
  assert.equal(refreshes, 2);
  await edit('default_owner_label', 'Stale preview'); await review();
  const staleSave = button('Save reviewed policy').props.onClick;
  valid = false;
  await act(async () => staleSave()); assert.equal(writes().length, 4);
  await click('Drawer close'); await click('Discard changes');
  await unmount(); valid = true;

  // A prop change replaces the inner session even when React reuses the outer
  // panel. A deferred old read cannot appear in the new workspace's form.
  let releaseRead;
  const firstClient = { current: () => true, request: async () => new Promise(resolve => { releaseRead = resolve; }) };
  props = { ...props, client: firstClient, workspaceToken: 'old' }; await render();
  props = { ...props, client, workspaceToken: 'new' }; await render();
  await act(async () => releaseRead({ ...initial, default_owner_label: 'OLD SECRET' }));
  assert.ok(!JSON.stringify(tree.toJSON()).includes('OLD SECRET'));
  assert.equal(tree.root.findByProps({ name: 'default_owner_label' }).props.value, 'Bob');
  await unmount();
  console.log('PASS real React policy panel: read-only opening/review, changed-version review, dirty close, duplicate save, late unknown across remount, exact recovery, rejected draft retention, saved-refresh failure, stale handlers and scope replacement.');
}

(async () => { await sessions(); await react(); })().catch(error => { console.error(error); process.exitCode = 1; });
