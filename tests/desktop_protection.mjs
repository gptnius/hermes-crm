// Synthetic, local-only fixtures. No keys, credentials, profiles or downloads.
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { webcrypto } from 'node:crypto';
const source = await readFile(new URL('../desktop/protection.js', import.meta.url), 'utf8');
const context = vm.createContext({ URLSearchParams, crypto: webcrypto });
const module = new vm.SourceTextModule(source, { context });
await module.link(() => new vm.SyntheticModule(['createElement','useEffect','useRef','useState'], function () {
  for (const name of ['createElement','useEffect','useRef','useState']) this.setExport(name, () => {});
}, { context }));
await module.evaluate();
const { createProtectionSession } = module.namespace;
const meta = { record_version: 3, note_version: 0, has_note: false };
const record = { kind: 'contacts', id: 'one / two' };
let available = true, enabled = true, fail = null, pending = null;
const calls = [], order = [];
const client = { current: () => available, request: async (path, options) => {
  calls.push({path,options});
  if (options && fail) throw fail;
  if (pending) return new Promise(resolve => { pending.resolve = resolve; });
  if (path.startsWith('/protection/status')) return { notes_enabled: enabled, backup_enabled: enabled };
  if (path.endsWith('/reveal')) return { ...meta, plaintext: 'private fixture' };
  if (path === '/protection/export') { order.push('request'); return { export_id: 'fixture', stored_path: '/fixture/export.enc', suggested_name: 'crm.enc' }; }
  return options ? { ...meta, note_version: 1, has_note: true } : meta;
} };
const store = new Map();
let session = createProtectionSession(client, 'workspace', record, () => true, undefined, store);
await session.load(); assert.equal(calls.length, 2); assert.ok(calls.every(c => !c.options));
assert.match(calls[1].path, /one%20%2F%20two/);
enabled = false; calls.length = 0; await session.load(); assert.equal(calls.length, 1); enabled = true;
assert.equal((await session.reveal()).plaintext, 'private fixture');
pending = {}; const saving = session.save(meta, 'secret fixture');
assert.equal(await session.save(meta, 'replacement'), null);
pending.resolve({ ...meta, note_version: 1 }); pending = null;
await saving;
assert.equal(calls.at(-1).options.body.expected_record_version, 3);
fail = new Error('transport contains private info');
await assert.rejects(session.save(meta, 'secret fixture'), /Save outcome unknown/);
const original = session.pending().operation_id;
assert.ok(!JSON.stringify([...store.values()]).includes('secret fixture'));
session.close(); session = createProtectionSession(client, 'workspace', record, () => true, undefined, store);
assert.equal(session.pending().operation_id, original);
assert.equal(await session.save(meta, 'replacement'), null);
fail = null;
const normalRequest = client.request;
client.request = async path => path.includes('/operations/') ? { operation_id: original, state: 'unknown' } : normalRequest(path);
assert.equal(await session.checkSave(), null); assert.ok(session.pending());
client.request = async path => path.includes('/operations/') ? { ...meta, operation_id: original, state: 'committed' } : normalRequest(path);
assert.ok(await session.checkSave()); assert.equal(session.pending(), null);
client.request = normalRequest;
available = false; assert.equal(await session.load(), null); available = true;
let late = createProtectionSession(client, 'workspace2', record); pending = {};
const reveal = late.reveal(); late.close(); pending.resolve({ ...meta, plaintext: 'do not show' }); pending = null;
assert.equal(await reveal, null);
const conflict = createProtectionSession(client, 'workspace3', record);
fail = Object.assign(new Error('unsafe server message'), { status: 409 });
await assert.rejects(conflict.save(meta, 'fixture'), /Close and reopen/);
assert.equal(await conflict.save(meta, 'replacement'), null); fail = null;
let downloads = 0;
const exp = createProtectionSession(client, 'workspace', null, () => true, () => {
  order.push('capture'); return async (path, name) => { downloads++; assert.equal(path, '/fixture/export.enc'); assert.equal(name, 'crm.enc'); };
});
await exp.load(); assert.equal(downloads, 0);
const artifact = await exp.prepareExport(); assert.deepEqual(order, ['capture','request']); assert.equal(downloads, 0);
await artifact.download(); await artifact.download(); assert.equal(downloads, 2, 'cancelled dialog leaves export available');
exp.close(); assert.equal(await artifact.download(), false); assert.equal(downloads, 2);
const absent = createProtectionSession(client, 'workspace', null);
await assert.rejects(absent.prepareExport(), /Update Hermes Desktop/);
// A server or proxy may emit 503 after a successful commit. Never unlock or
// create a replacement operation based on a 5xx, for either write endpoint.
for (const status of [500, 502, 503, 504]) {
  const error = Object.assign(new Error('post-commit proxy fixture'), { status });
  const attempts = [], scopedStore = new Map();
  let exportState = 'unknown', recoveredDownloads = 0;
  const postCommit = { current: () => true, async request(path, options) {
    if (options) { attempts.push(options.body); throw error; }
    if (path.includes('/export/operations/')) return { operation_id: attempts.at(-1).operation_id, state: exportState, export_id: 'original-artifact', stored_path: '/fixture/original.enc', suggested_name: 'original.enc' };
    return { ...meta, operation_id: attempts[0].operation_id, state: 'committed' };
  } };
  let note = createProtectionSession(postCommit, 'postcommit', record, () => true, undefined, scopedStore);
  await assert.rejects(note.save(meta, 'never retained'), /Save outcome unknown/);
  const noteId = note.pending().operation_id;
  note.close(); note = createProtectionSession(postCommit, 'postcommit', record, () => true, undefined, scopedStore);
  assert.equal(note.pending().operation_id, noteId); assert.equal(note.pending().state, 'unknown');
  assert.equal(await note.save(meta, 'replacement'), null); assert.equal(attempts.length, 1);
  assert.ok(await note.checkSave()); assert.equal(note.pending(), null);
  let exported = createProtectionSession(postCommit, 'postcommit', null, () => true, () => async (path, name) => { assert.equal(path, '/fixture/original.enc'); assert.equal(name, 'original.enc'); recoveredDownloads++; }, scopedStore);
  await assert.rejects(exported.prepareExport(), /Export could not be confirmed/);
  const exportId = exported.pending().operation_id;
  exported.close(); exported = createProtectionSession(postCommit, 'postcommit', null, () => true, () => async () => {}, scopedStore);
  assert.equal(exported.pending().operation_id, exportId); assert.equal(exported.pending().state, 'unknown');
  assert.equal(await exported.prepareExport(), null); assert.equal(attempts.length, 2);
  assert.equal(await exported.checkExport(), null); assert.equal(exported.pending().operation_id, exportId);
  exportState = 'missing_artifact'; assert.equal(await exported.checkExport(), null); assert.ok(exported.pending());
  exportState = 'committed'; const recovered = await exported.checkExport(); assert.ok(recovered); assert.equal(exported.pending(), null);
  assert.equal(recoveredDownloads, 0); await recovered.download(); assert.equal(recoveredDownloads, 1, 'recovery uses original captured download binding');
  assert.equal(attempts.length, 2, 'receipt recovery must never POST or create a replacement snapshot');
}
assert.doesNotMatch(source, /localStorage|sessionStorage|writeClipboard|console\.|\bBlob\b|createObjectURL/);
console.log('PASS protected note metadata/reveal/write isolation, conflicts, unknown locks, stale responses, export capture/download separation.');
