// Synthetic local-only contract tests. No browser, account, OAuth or provider calls.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { webcrypto } from 'node:crypto';
const source = await readFile(new URL('../desktop/email-history.js', import.meta.url), 'utf8');
const context = vm.createContext({ URLSearchParams, crypto: webcrypto });
const module = new vm.SourceTextModule(source, { context });
await module.link(() => new vm.SyntheticModule(['createElement','useEffect','useRef','useState'], function () {
  for (const name of ['createElement','useEffect','useRef','useState']) this.setExport(name, () => {});
}, { context }));
await module.evaluate();
const { createEmailHistorySession, emailEvidenceLabel } = module.namespace;
assert.equal(emailEvidenceLabel({ labels: ['SENT'] }), 'Observed in Gmail Sent');
assert.equal(emailEvidenceLabel({ labels: ['INBOX'] }), 'Mailbox item observed');
assert.doesNotMatch(source, /dangerouslySetInnerHTML|\bfetch\s*\(|href:|src:|setInterval|localStorage/);
assert.match(source, /gmail.readonly scope can read message bodies/);
assert.match(source, /expected_contact_version: contact.version/);
const calls = [];
let status = { enabled: false, connected: false, mailbox: null, revision: 1 };
let current = true, fail = false;
const client = { current: () => current, async request(path, options) {
  calls.push({ path, options });
  if (fail && options) throw new Error('synthetic transport failure');
  return path.startsWith('/email/contacts/') ? { items: [], total: 0 } : options ? { ...status, operation: { id: options.body.operation_id, kind: path.split('/').at(-1), state: 'finished' } } : status;
} };
const contact = { id: 'contact /one', version: 4, email: 'person@example.test' };
let session = createEmailHistorySession(client, 'workspace', contact);
assert.ok(await session.load());
assert.equal(calls.length, 2);
assert.ok(calls.every(call => !call.options));
assert.ok(calls[1].path.includes('contact%20%2Fone'));
await session.submit('sync', status, { days: 7 });
const body = calls.at(-1).options.body;
assert.equal(body.days, 7); assert.equal(body.expected_contact_version, 4);
assert.equal(body.contact_id, contact.id); assert.equal(body.consent, true);
assert.match(body.operation_id, /^[a-f0-9-]{36}$/);
fail = true;
await assert.rejects(session.submit('verify', status, { mailbox: 'me@example.test' }), /Outcome unknown/);
const before = calls.length;
assert.equal(await session.submit('verify', status, { mailbox: 'me@example.test' }), null);
assert.equal(calls.length, before);
const pending = session.pending();
session.close();
session = createEmailHistorySession(client, 'workspace', contact);
assert.equal(session.pending().state, 'unknown', 'remount must not unlock uncertain writes');
await session.load(); assert.ok(session.pending());
status = { ...status, operation: { id: pending.id, kind: 'verify', state: 'finished' } };
await session.load(); assert.equal(session.pending(), undefined);
current = false;
assert.equal(await session.load(), null);
assert.equal(await session.submit('sync', status, { days: 30 }), null);
let resolve;
const delayed = { current: () => true, request: () => new Promise(r => { resolve = r; }) };
const stale = createEmailHistorySession(delayed, 'workspace', contact);
const promise = stale.submit('sync', status, { days: 7 });
stale.close(); resolve(status); assert.equal(await promise, null);
assert.ok(stale.pending(), 'discarded write response must not silently unlock another panel');
console.log('Email history synthetic local-only contract tests passed.');

// Actual React lifecycle tests, with local injected client and existing test-only dependencies.
const { createRequire } = await import('node:module');
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const ui = new vm.SourceTextModule(source, { context });
await ui.link(() => new vm.SyntheticModule(Object.keys(React), function () {
  for (const [key, value] of Object.entries(React)) this.setExport(key, value);
}, { context }));
await ui.evaluate();
const uiCalls = [];
let uiStatus = { enabled: true, connected: true, mailbox: 'me@example.test', revision: 1 };
const uiClient = { current: () => true, async request(path, options) {
  uiCalls.push({ path, options });
  if (path.startsWith('/email/contacts/')) return { items: [{ message_id: 'm1', labels: ['SENT'], display_headers: [['Subject', '<img src=x onerror=bad()>']] }], total: 1 };
  return options ? { ...uiStatus, operation: { id: options.body.operation_id, kind: path.split('/').at(-1), state: 'finished' } } : uiStatus;
} };
let tree;
const props = { client: uiClient, contact, workspaceToken: 'workspace', routeKey: 'route', storageBackend: 'sqlite' };
await React.act(async () => { tree = Renderer.create(React.createElement(ui.namespace.EmailHistoryPanel, props)); });
assert.ok(uiCalls.every(call => !call.options), 'mount is local GETs only');
const findButton = label => tree.root.findAllByType('button').find(node => node.children.join('') === label);
assert.ok(JSON.stringify(tree.toJSON()).includes('<img src=x onerror=bad()>'));
assert.equal(tree.root.findAllByType('img').length, 0);
await React.act(async () => findButton('Read Gmail history').props.onClick());
assert.equal(tree.root.findByProps({ type: 'submit' }).props.disabled, true);
await React.act(async () => tree.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: true } }));
assert.equal(tree.root.findByProps({ type: 'submit' }).props.disabled, false);
await React.act(async () => {
  const submit = tree.root.findByType('form').props.onSubmit;
  await Promise.all([submit({ preventDefault() {} }), submit({ preventDefault() {} })]);
});
assert.equal(uiCalls.filter(call => call.options).length, 1, 'rapid double submit only dispatches once');
const beforeRefresh = uiCalls.filter(call => call.options).length;
await React.act(async () => findButton('Refresh local status').props.onClick());
assert.equal(uiCalls.filter(call => call.options).length, beforeRefresh);
await React.act(async () => findButton('Read Gmail history').props.onClick());
await React.act(async () => tree.update(React.createElement(ui.namespace.EmailHistoryPanel, { ...props, contact: { ...contact, id: 'other', version: 5 } })));
assert.equal(tree.root.findAllByType('form').length, 0, 'contact switch removes prior approval');
await React.act(async () => tree.unmount());
console.log('Email history React rendering and lifecycle tests passed (synthetic client only).');

// Local invalidation may supersede an unresolved provider read. No read retries.
let finishProvider;
const cancellationCalls = [];
const cancellationStatus = { enabled: true, connected: true, mailbox: 'me@example.test', revision: 8, operation: null };
const cancellingClient = { current: () => true, async request(path, options) {
  cancellationCalls.push({ path, options });
  if (path === '/email/sync') return new Promise(resolve => { finishProvider = () => resolve({ ...cancellationStatus, operation: { id: options.body.operation_id, kind: 'sync', state: 'finished' } }); });
  if (path === '/email/disconnect') return { ...cancellationStatus, connected: false, revision: 9, operation: { id: options.body.operation_id, kind: 'disconnect', state: 'finished' } };
  return cancellationStatus;
} };
const cancellable = createEmailHistorySession(cancellingClient, 'workspace', contact);
const inFlight = cancellable.submit('sync', cancellationStatus, { days: 7 });
const disconnected = await cancellable.submit('disconnect', { ...cancellationStatus, revision: 7 });
assert.equal(disconnected.connected, false);
assert.equal(cancellationCalls.find(call => call.path === '/email/disconnect').options.body.expected_revision, 8, 'disconnect uses fresh local revision');
finishProvider(); assert.equal(await inFlight, null, 'late provider reply cannot overwrite cancellation');
assert.equal(cancellable.pending(), undefined);
let malformed = true, savedID;
const reconciliationClient = { current: () => true, async request(path, options) {
  if (options) { savedID = options.body.operation_id; return malformed ? {} : cancellationStatus; }
  if (path.startsWith('/email/operations/')) return { id: savedID, kind: 'clear', state: 'finished' };
  if (path.startsWith('/email/contacts/')) return { items: [], total: 0 };
  return cancellationStatus;
} };
const reconcile = createEmailHistorySession(reconciliationClient, 'workspace', contact);
await assert.rejects(reconcile.submit('clear', cancellationStatus), /Outcome unknown/);
assert.equal(reconcile.pending().state, 'unknown', 'malformed success must remain unknown');
await reconcile.load(); assert.equal(reconcile.pending(), undefined, 'durable receipt reconciles a local action without retry');
console.log('Email history cancellation, validation and durable-receipt tests passed.');
// The rendered cancellation control remains usable while the provider read hangs.
let resolveUIRead;
const liveUICalls = [];
const hangingUIClient = { current: () => true, async request(path, options) {
  liveUICalls.push({ path, options });
  if (path.startsWith('/email/contacts/')) return { items: [], total: 0 };
  if (path === '/email/sync') return new Promise(resolve => { resolveUIRead = () => resolve({ ...uiStatus, operation: { id: options.body.operation_id, kind: 'sync', state: 'finished' } }); });
  if (options) return { ...uiStatus, connected: false, revision: 2, operation: { id: options.body.operation_id, kind: 'disconnect', state: 'finished' } };
  return uiStatus;
} };
await React.act(async () => { tree = Renderer.create(React.createElement(ui.namespace.EmailHistoryPanel, { ...props, client: hangingUIClient })); });
await React.act(async () => findButton('Read Gmail history').props.onClick());
await React.act(async () => tree.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: true } }));
let uiRead;
await React.act(async () => { uiRead = tree.root.findByType('form').props.onSubmit({ preventDefault() {} }); });
assert.equal(findButton('Disconnect locally').props.disabled, false);
await React.act(async () => findButton('Disconnect locally').props.onClick());
assert.equal(tree.root.findByProps({ type: 'checkbox' }).props.disabled, false);
await React.act(async () => tree.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: true } }));
await React.act(async () => tree.root.findByType('form').props.onSubmit({ preventDefault() {} }));
assert.equal(liveUICalls.filter(call => call.path === '/email/disconnect').length, 1);
await React.act(async () => { resolveUIRead(); await uiRead; });
await React.act(async () => tree.unmount());
console.log('Email history rendered pending-read cancellation test passed.');
// Storage consent must distinguish SQLite from a potentially remote PostgreSQL schema.
await React.act(async () => { tree = Renderer.create(React.createElement(ui.namespace.EmailHistoryPanel, { ...props, storageBackend: undefined })); });
assert.equal(findButton('Read Gmail history').props.disabled, true);
assert.equal(findButton('Verify own mailbox').props.disabled, true);
assert.ok(JSON.stringify(tree.toJSON()).includes('Unknown storage destination'));
await React.act(async () => tree.update(React.createElement(ui.namespace.EmailHistoryPanel, { ...props, storageBackend: 'postgres' })));
await React.act(async () => findButton('Read Gmail history').props.onClick());
assert.ok(tree.root.findByType('form').findAllByType('p').some(node => node.children.join('').includes('Selected PostgreSQL schema (may be remote)')));
await React.act(async () => tree.root.findByProps({ type: 'checkbox' }).props.onChange({ target: { checked: true } }));
await React.act(async () => tree.update(React.createElement(ui.namespace.EmailHistoryPanel, { ...props, storageBackend: 'sqlite' })));
assert.equal(tree.root.findAllByType('form').length, 0, 'storage change invalidates prior read consent');
assert.ok(JSON.stringify(tree.toJSON()).includes('SQLite in this Hermes profile'));
await React.act(async () => tree.unmount());
console.log('Email history storage destination consent tests passed.');
