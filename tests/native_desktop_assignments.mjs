// Real React lifecycle tests; SDK/REST/clipboard are synthetic. No host execution.
// node --experimental-vm-modules tests/native_desktop_assignments.mjs
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { webcrypto } from 'node:crypto';
import vm from 'node:vm';
const require = createRequire(`${process.env.HERMES_CRM_REACT_TEST_ROOT || '/tmp/hermes-crm-desktop-test'}/package.json`);
const React = require('react'), Renderer = require('react-test-renderer'), { act } = React;
assert.equal(React.version, '19.3.0');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const source = await readFile(new URL('../desktop/plugin.js', import.meta.url), 'utf8');
assert.doesNotMatch(source, /host\.composer\.|host\.(?:request|requestProfile|openSession|newChat)\s*\(|\bfetch\s*\(|execution.bridge|localStorage|sessionStorage/);
assert.match(source, /@container\(max-width:480px\)/);
const flatten = n => typeof n === 'string' || typeof n === 'number' ? String(n) : Array.isArray(n) ? n.map(flatten).join(' ') : n?.children ? flatten(n.children) : '';
const clone = value => structuredClone(value);
function atom(value) { const listeners = new Set(); return { get: () => value, set(v) { if (Object.is(value, v)) return; value = v; for (const f of [...listeners]) f(); }, listen(f) { listeners.add(f); return () => listeners.delete(f); }, subscribe(f) { listeners.add(f); return () => listeners.delete(f); }, listeners }; }
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
const originalTask = { id: 't1', version: 3, status: 'open', title: 'Synthetic follow-up', due_at: '2030-12-01T12:00:00+00:00', priority: 'normal', schedule_status: 'not_scheduled', notes: 'PRIVATE HIDDEN NOTES', contact_id: 'c1', email: 'private@example.test' };
const originalWork = { id: 'a1', task_id: 't1', version: 2, generation: 1, state: 'pending', reason: 'not_scheduled', job_id: null, idempotency_key: 'prior-saved-key', source_task_current: true,
  payload: { task_id: 't1', task_version: 3, task_status: 'open', human_owner: 'Synthetic owner', prompt: 'Review saved CRM only', success_criteria: 'Cite CRM evidence', run_at: '2030-12-01T13:30:41.000000+00:00' }, events: [], reports: [] };
async function fixture(options = {}) {
  const state = { profile: atom('work'), connectionId: atom('source-a'), gateway: atom('open'), cwd: atom('/synthetic'), activeSessionId: atom('runtime-A'), focusedSessionId: atom('runtime-A'), focusedStoredSessionId: atom('stored-A'), focusedSessionOwner: atom({ connectionId: 'source-a', profile: 'work' }) };
  const epoch = atom(1), disposers = [], intervals = new Set(), timers = new Set(), calls = [], copies = [], opened = [], navigation = [], focus = [];
  const e = { state, epoch, disposers, calls, copies, opened, navigation, focus, task: clone(originalTask), work: clone(originalWork), token: 'workspace-secret', taskGate: null, workGate: null, copyGate: null, taskError: false, coverageError: false, historyError: false, copyResult: true, closed: false, viewRequest: { current: 0 }, coveragePages: null, historyPages: null, writes: [], savedWorks: new Map(), saveGate: null, saveError: false, readonly: false, focusTargets: [], nodeMocks: [] };
  const host = { state, composer: new Proxy({}, { get() { throw Error('Composer must never be accessed'); } }), navigate(path) { navigation.push(path); }, revealPane() {}, paneVisibility: () => ({ get: () => true }), openWorkspace(id, value) { opened.push({ id, ...value }); return () => {}; } };
  const useValue = a => React.useSyncExternalStore(a.subscribe, a.get, a.get);
  const sdk = { host, atom, useValue, gatewayActivationEpoch: epoch.get, useGatewayActivationEpoch: () => useValue(epoch), PANES_AREA: 'panes', ROUTES_AREA: 'routes', SIDEBAR_NAV_AREA: 'sidebar.nav', PALETTE_AREA: 'palette' };
  const ctx = { registerMany() {}, onDispose(f) { disposers.push(f); }, os: options.noClipboard ? {} : { async writeClipboard(text) { copies.push(text); if (e.copyGate) return e.copyGate.promise; return e.copyResult; } },
    setInterval(f) { intervals.add(f); return () => intervals.delete(f); },
    setTimeout(f) { const timer = setTimeout(() => { timers.delete(timer); f(); }, 1); timers.add(timer); return () => { clearTimeout(timer); timers.delete(timer); }; },
    async rest(path, requestOptions) {
      calls.push(path);
      if (path === '/work' && requestOptions?.method === 'POST') {
        const body = clone(requestOptions.body); e.writes.push(body);
        assert.equal(body.workspace_token, e.token);
        assert.equal(Object.keys(body).sort().join(','), 'expected_task_version,human_owner,idempotency_key,prompt,run_at,success_criteria,task_id,workspace_token');
        if (e.saveError) throw Error('Secret backend failure must not be echoed');
        let saved = e.savedWorks.get(body.idempotency_key);
        if (!saved) {
          if (body.expected_task_version !== e.task.version || e.task.status !== 'open') throw Error('Source task changed');
          const fraction = /\.(\d{1,6})/.exec(body.run_at)?.[1] || '';
          const run_at = new Date(body.run_at).toISOString().replace(/\.\d{3}Z$/, `.${fraction.padEnd(6, '0')}+00:00`);
          saved = { ...clone(originalWork), id: `saved-work-${e.savedWorks.size + 1}`, version: 1, workspace: e.token, profile: 'work', idempotency_key: body.idempotency_key,
            payload: { task_id: body.task_id, task_version: body.expected_task_version, expected_task_version: body.expected_task_version, task_status: 'open',
              human_owner: body.human_owner, prompt: body.prompt, success_criteria: body.success_criteria, run_at } };
          e.savedWorks.set(body.idempotency_key, saved);
        }
        return e.saveGate ? e.saveGate.promise : e.saveReply ? e.saveReply(clone(saved)) : clone(saved);
      }
      assert.equal(requestOptions, undefined, 'Only explicit local assignment Save may write');
      const params = new URLSearchParams(path.split('?')[1]);
      if (path !== '/snapshot') assert.equal(params.get('workspace_token'), e.token);
      if (path.startsWith('/tasks/t1?')) { if (e.taskError) throw Error('Synthetic task read failure'); return e.taskGate ? e.taskGate.promise : clone(e.task); }
      if (path.startsWith('/work/a1?')) return e.workGate ? e.workGate.promise : clone(e.work);
      if (path.startsWith('/work/saved-work-')) return clone([...e.savedWorks.values()].find(w => path.startsWith(`/work/${w.id}?`)));
      if (path.startsWith('/reports/work?')) { if (e.historyError) throw Error('Untrusted provider detail must not be shown'); return e.historyPages?.(params) || { items: [clone(e.work)], total: 1, limit: 25, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00' }; }
      if (path.startsWith('/reports/coverage?')) { if (e.coverageError) throw Error('Private raw provider error'); return e.coveragePages?.(params) || { items: [], total: 0, limit: 50, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00', workspace_token: e.token }; }
      if (path.startsWith('/tasks?')) return [clone(e.task)];
      if (path === '/snapshot') return { meta: { workspace_token: e.token, profile: 'work', backend: 'sqlite' }, contacts: [], deals: [], tasks: [clone(e.task)], activity: [], overview: { contacts: 0, open_tasks: 1, overdue_tasks: 0, open_deals: 0, stages: [], tasks: [clone(e.task)], activity: [] } };
      throw Error(`Unexpected route ${path}`);
    } };
  const context = vm.createContext({ console, Intl, URLSearchParams, crypto: webcrypto });
  const mod = new vm.SourceTextModule(source, { context });
  await mod.link(name => { const exports = name === 'react' ? React : name === '@hermes/plugin-sdk' ? sdk : null; assert.ok(exports); return new vm.SyntheticModule(Object.keys(exports), function () { for (const [k, v] of Object.entries(exports)) this.setExport(k, v); }, { context }); }); await mod.evaluate();
  const api = mod.namespace; api.default.register(ctx);
  const identity = api.routeIdentity(ctx), client = api.createRouteClient(ctx, identity);
  const props = { ctx, identity, client, task: clone(e.task), workspaceToken: e.token, workspaceProfile: 'work', disabled: false, viewRequest: e.viewRequest, close() { e.closed = true; }, openNativeChat() {}, ...(options.mode ? { mode: options.mode } : {}), ...(options.work ? { work: clone(e.work) } : {}) };
  let root;
  e.flush = async () => act(async () => { await new Promise(r => setTimeout(r, 4)); });
  e.mount = async (name = 'AgentRequest', extra = {}) => { await act(async () => { root = Renderer.create(React.createElement(React.StrictMode, null, React.createElement(api[name], { ...props, ...extra })), { createNodeMock: elem => { const node = { name: flatten(elem.props.children), isConnected: true, focus() { focus.push(elem.type); e.focusTargets.push(node); }, ownerDocument: { activeElement: null }, querySelector() { return null; }, querySelectorAll() { return []; } }; e.nodeMocks.push(node); return node; } }); }); await e.flush(); };
  e.change = async fn => { await act(async () => { fn(); }); await e.flush(); };
  e.button = name => root.root.findAllByType('button').find(n => flatten(n.children) === name);
  e.click = async name => { const b = e.button(name); assert.ok(b, `Missing ${name}`); assert.notEqual(b.props.disabled, true, `Disabled ${name}`); await e.change(() => b.props.onClick()); };
  e.field = name => root.root.findByProps({ 'aria-label': name });
  e.input = async (name, value) => e.change(() => e.field(name).props.onChange({ target: { value } }));
  e.text = () => flatten(root.toJSON()); e.root = () => root;
  e.preview = () => e.field('Exact request preview').props.value;
  e.fill = async () => { await e.input('Human owner', 'Reviewed human'); await e.input('Reviewed instructions', 'Summarize known CRM facts'); await e.input('Success criteria', 'Separate facts from unknowns'); await e.input('Future run time with UTC offset', '2030-11-10T14:00:00-05:00'); };
  e.unmount = async () => { if (root) await act(async () => { root.unmount(); root = null; }); };
  e.finish = async () => { await e.unmount(); client.dispose(); for (const f of disposers) f(); for (const a of Object.values(state)) assert.equal(a.listeners.size, 0); assert.equal(intervals.size, 0); assert.equal(timers.size, 0); };
  Object.assign(e, { api, ctx, host, props, client, identity }); return e;
}
// Exact timestamp parsing rejects rollover/local ambiguity, accepts persisted microseconds.
{
  const e = await fixture();
  for (const value of ['2030-02-30T12:00:00Z', '2030-11-10T24:00Z', '2030-11-10T12:60Z', '2030-11-10T12:00', '2030-11-10T12:00:00+14:30', '2030-11-10T12:00:00+25:00', '2020-01-01T00:00:00Z']) assert.throws(() => e.api.requestInstant(value), undefined, value);
  assert.equal(e.api.requestInstant(originalWork.payload.run_at, 0), originalWork.payload.run_at);
  assert.equal(e.api.requestInstant('2030-11-10T14:00:00.123456-05:00'), '2030-11-10T14:00:00.123456-05:00');
  await e.finish();
}
// Preview/Copy re-read task, keep exact immutable text/key, and never save/send.
{
  const e = await fixture(); await e.mount(); await e.fill(); await e.click('Preview request');
  const text = e.preview(); assert.match(text, /"expected_task_version": 3/); assert.match(text, /crm_work_create/); assert.match(text, /Do not schedule it yet/); assert.match(text, /Existing CRM data only: no web research, outreach, business-record changes or task completion/); assert.doesNotMatch(text, /Make only CRM record changes/);
  assert.match(text, /2030-11-10T14:00:00-05:00/);
  assert.doesNotMatch(text, /workspace-secret|PRIVATE HIDDEN|private@example|Synthetic follow-up|runtime-A/);
  assert.equal(e.calls.length, 1); assert.equal(e.copies.length, 0);
  await e.click('Preview request'); assert.equal(e.preview(), text);
  await e.click('Copy request'); await e.click('Copy request'); assert.deepEqual(e.copies, [text, text]);
  assert.equal(e.calls.length, 4); assert.match(e.text(), /copied, not saved, scheduled or sent/); assert.deepEqual(e.work, originalWork);
  assert.equal(e.field('Exact request preview').props.readOnly, true); assert.ok(e.focus.includes('h3'));
  await e.input('Reviewed instructions', 'Revised reviewed instructions'); assert.match(e.text(), /earlier preview may already have been copied or sent/);
  await e.click('Preview request'); const next = e.preview(); assert.notEqual(next, text); assert.match(next, /Earlier reviewed request keys/); assert.match(next, /Inspect them before creating/);
  assert.equal(e.navigation.length, 0); await e.finish();
}
// Record edits before Preview/Copy fail closed; done source can't prepare new work.
for (const when of ['before-preview', 'before-copy']) {
  const e = await fixture(); await e.mount(); await e.fill();
  if (when === 'before-copy') await e.click('Preview request');
  e.task.version++; await e.click(when === 'before-copy' ? 'Copy request' : 'Preview request');
  assert.match(e.text(), /source task changed/); assert.equal(e.copies.length, 0); await e.finish();
}
{
  const e = await fixture({ mode: 'help' }); await e.mount(); await e.input('Reviewed instructions', 'Find what is known'); await e.click('Preview request');
  assert.match(e.preview(), /interactive request, not an authenticated scheduled-work report/); assert.match(e.preview(), /Make only CRM record changes specifically requested/); assert.match(e.preview(), /permitted by normal host approval; otherwise provide analysis or draft text only/); assert.doesNotMatch(e.preview(), /crm_work_create/);
  e.task.status = 'done'; await e.click('Copy request'); assert.equal(e.copies.length, 0); assert.match(e.text(), /no longer open/); await e.finish();
}
// Backend-shaped saved payloads schedule only exact current pending intent.
{
  const e = await fixture({ mode: 'schedule', work: true }); await e.mount(); await e.click('Preview request');
  assert.match(e.preview(), /crm_work_schedule with assignment_id only/); assert.match(e.preview(), /2030-12-01T13:30:41.000000\+00:00/);
  assert.match(e.preview(), /"assignment_version": 2/); assert.equal(e.calls.length, 2); await e.click('Copy request'); assert.equal(e.copies.length, 1); assert.equal(e.calls.length, 4); await e.finish();
}
for (const mutation of [w => w.version++, w => w.generation++, w => w.state = 'cancelled', w => w.payload.prompt = 'Changed frozen instructions', w => w.task_id = 'other-task', w => w.id = 'other-assignment', w => w.source_task_current = false]) {
  const e = await fixture({ mode: 'schedule', work: true }); await e.mount(); await e.click('Preview request'); mutation(e.work); await e.click('Copy request'); assert.equal(e.copies.length, 0); assert.match(e.text(), /assignment changed|not a current/); await e.finish();
}
// A changed/done task and locally cancelled assignment still support check/cancel.
for (const mode of ['check', 'cancel']) {
  const e = await fixture({ mode, work: true });
  e.work.state = e.props.work.state = 'cancelled'; e.work.reason = e.props.work.reason = 'pause_outcome_unknown_running_run_not_cancelled';
  e.work.source_task_current = e.props.work.source_task_current = false;
  e.task.version = 9; e.task.status = 'done';
  await e.mount(); await e.click('Preview request'); await e.click('Copy request'); assert.equal(e.copies.length, 1);
  assert.match(e.preview(), /"expected_task_version": 9/); assert.match(e.preview(), /"frozen_task_version": 3/); assert.match(e.preview(), /"assignment_id": "a1"/);
  assert.match(e.preview(), mode === 'cancel' ? /version equal to the reviewed assignment_version/ : /crm_work_reconcile/); assert.doesNotMatch(e.preview(), /crm_work_create/);
  await e.finish();
}
// Synchronous ABA, selection/editor invalidation and each async read boundary.
for (const phase of ['preview-task', 'copy-task', 'copy-work']) for (const change of ['profile-aba', 'source-aba', 'chat-aba', 'reconnect', 'selection', 'fields', 'unmount']) {
  const e = await fixture(phase === 'copy-work' ? { mode: 'schedule', work: true } : {}); await e.mount(); if (phase !== 'copy-work') await e.fill();
  if (phase !== 'preview-task') await e.click('Preview request');
  const gate = deferred(); if (phase === 'copy-work') e.workGate = gate; else e.taskGate = gate;
  await e.click(phase === 'preview-task' ? 'Preview request' : 'Copy request');
  if (change === 'fields' && phase === 'copy-work') { await e.click('Discard prepared request'); }
  else if (change === 'fields') await e.input('Reviewed instructions', 'Changed during read');
  else if (change === 'profile-aba') await e.change(() => { e.state.profile.set('other'); e.state.profile.set('work'); });
  else if (change === 'source-aba') await e.change(() => { e.state.connectionId.set('other'); e.state.connectionId.set('source-a'); });
  else if (change === 'chat-aba') await e.change(() => { e.state.focusedStoredSessionId.set('stored-B'); e.state.focusedStoredSessionId.set('stored-A'); });
  else if (change === 'reconnect') await e.change(() => { e.state.gateway.set('closed'); e.state.gateway.set('open'); });
  else if (change === 'selection') e.viewRequest.current++;
  else if (change === 'unmount') await e.unmount();
  await e.change(() => gate.resolve(clone(phase === 'copy-work' ? e.work : e.task)));
  assert.equal(e.copies.length, 0, `${phase} ${change}`); await e.finish();
}
// Duplicate click lock, late clipboard result, uncertain/failed clipboard and manual fallback.
{
  const e = await fixture(); await e.mount(); await e.fill(); await e.click('Preview request'); e.taskGate = deferred();
  const copy = e.button('Copy request').props.onClick, before = e.calls.length;
  await e.change(() => { copy(); copy(); }); assert.equal(e.calls.length, before + 1);
  e.copyGate = deferred(); await e.change(() => e.taskGate.resolve(clone(e.task))); assert.equal(e.copies.length, 1);
  await e.change(() => { e.state.focusedSessionId.set('other'); e.state.focusedSessionId.set('runtime-A'); });
  await e.change(() => e.copyGate.resolve(true)); assert.doesNotMatch(e.text(), /Request copied,/); assert.equal(e.copies.length, 1); await e.finish();
}
for (const result of [false, undefined]) {
  const e = await fixture(); e.copyResult = result; await e.mount(); await e.fill(); await e.click('Preview request'); await e.click('Copy request'); assert.match(e.text(), /Copy was not confirmed/); assert.match(e.text(), /copy manually/); await e.finish();
}
{
  const e = await fixture(); await e.mount(); await e.fill(); await e.click('Preview request'); e.copyGate = deferred(); await e.click('Copy request'); await e.change(() => e.copyGate.reject(Error('Clipboard unavailable'))); assert.match(e.text(), /Copy was not confirmed/); assert.doesNotMatch(e.text(), /Request copied,/); await e.finish();
}
{
  const e = await fixture({ noClipboard: true }); await e.mount(); await e.fill(); await e.click('Preview request'); assert.equal(e.button('Copy request').props.disabled, true); assert.match(e.text(), /copy manually/); assert.equal(e.field('Exact request preview').props.readOnly, true); await e.finish();
}
for (const change of [s => s.focusedSessionId.set('secondary'), s => s.focusedSessionOwner.set(null), s => s.activeSessionId.set(null), s => s.focusedSessionOwner.set({ connectionId: 'other', profile: 'work' })]) {
  const e = await fixture(); change(e.state); await e.mount(); await e.fill(); await e.click('Preview request'); assert.equal(e.calls.length, 0); assert.equal(e.copies.length, 0); assert.match(e.text(), /main Hermes chat|same verified/); await e.finish();
}
// Queue count/filter/page come from the endpoint, not a first-500 snapshot. All risks remain separate.
{
  const e = await fixture();
  const row = (id, state, flags) => ({ id, kind: 'assignment', row_kind: 'assignment', task: { ...originalTask, notes: undefined }, contacts: [], risk_flags: flags, next_action: 'check_assignment', assignment: { ...originalWork, id, state, task_version: 3, run_at: originalWork.payload.run_at, human_owner: 'Reviewer', latest_host_observation: { state: 'running', observed_at: '2026-11-05T12:00:00+00:00', age_seconds: 90000, job_id: 'job1' }, latest_report: null } });
  e.coveragePages = params => ({ items: Number(params.get('offset')) ? [row('last', 'pending', ['agent_not_scheduled'])] : [row('unknown-old', 'unknown', ['needs_scheduling_review']), row('new-scheduled', 'scheduled', []), row('report-blocked', 'result_reported', ['reported_blocked_failed'])], total: params.get('status') === 'any' ? 1001 : 601, limit: 50, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00', workspace_token: e.token });
  await e.mount('CoverageQueue', { snapshotGeneration: 1, open() {} });
  assert.match(e.text(), /1001 matching evidence items \(not unique contacts or tasks\)/); assert.match(e.text(), /unknown-old/); assert.match(e.text(), /new-scheduled/); assert.match(e.text(), /report-blocked/); assert.match(e.text(), /90000 seconds old/);
  assert.match(e.text(), /not a live scheduler check/); assert.doesNotMatch(e.text(), /PRIVATE HIDDEN|private@example/);
  await e.click('Next coverage page'); assert.match(e.calls.at(-1), /offset=50/); assert.match(e.text(), /51–51 shown/);
  await e.input('Coverage filter', 'reported_blocked_failed'); assert.match(e.calls.at(-1), /status=reported_blocked_failed/); assert.match(e.calls.at(-1), /offset=0/); assert.match(e.text(), /601 matching evidence/);
  e.coverageError = true; await e.click('Refresh coverage evidence'); assert.match(e.text(), /Coverage refresh failed/); assert.match(e.text(), /unknown-old/); assert.doesNotMatch(e.text(), /Private raw provider error|No matching coverage/);
  await e.finish();
}
{
  const e = await fixture(); e.coverageError = true; await e.mount('CoverageQueue', { snapshotGeneration: 1 }); assert.match(e.text(), /Coverage is unavailable/); assert.doesNotMatch(e.text(), /No matching coverage/); await e.finish();
}
// Paginated history is honest about errors, independent host/report/task facts and does no writes.
{
  const e = await fixture(); e.work.state = 'cancelled'; e.work.source_task_current = false; e.work.business_task_completed = true;
  e.work.reason = 'pause_outcome_unknown_running_run_not_cancelled'; e.work.job_id = 'job1';
  e.work.reports = [{ id: 'r1', outcome: 'blocked', summary: 'Missing current evidence', provenance: 'native_run_reported', created_at: '2026-11-05T10:00:00+00:00', identity: { job_id: 'job1', execution_id: 'run1' } }];
  e.historyPages = params => ({ items: [clone(e.work)], total: 701, limit: 25, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00' });
  await e.mount('AssignedWork', { snapshotGeneration: 1, onPrepare() {} }); assert.match(e.text(), /701 saved assignments/); assert.match(e.text(), /pause is unverified/); assert.match(e.text(), /Stale Source Task/); assert.match(e.text(), /Execution run1/); assert.match(e.text(), /Done; completion does not cancel/);
  assert.ok(e.button('Ask to cancel future assignment')); assert.equal(e.button('Ask to schedule saved assignment'), undefined);
  await e.click('Next assignments'); assert.match(e.calls.at(-1), /offset=25/);
  e.historyError = true; await e.click('Refresh saved status'); assert.match(e.text(), /history could not be refreshed/); assert.match(e.text(), /Missing current evidence/); assert.doesNotMatch(e.text(), /Untrusted provider detail|No native assignments/); await e.finish();
}
// Existing record editor stays intact; Prepare opens split before constructing a mutable draft.
{
  const e = await fixture(); await e.mount('CRMRoot', { ctx: e.ctx }); await e.click('Tasks');
  const taskButton = e.root().root.findAllByType('button').find(n => flatten(n.children).includes('Synthetic follow-up'));
  await e.change(() => taskButton.props.onClick()); assert.ok(e.button('Prepare agent request'));
  await e.click('Edit'); const title = e.root().root.findAllByType('input').find(n => n.props.name === 'title');
  await e.change(() => title.props.onChange({ target: { value: 'Unsaved task change' } }));
  const prepare = e.button('Prepare agent request'); assert.equal(prepare.props.disabled, true); await e.change(() => prepare.props.onClick()); assert.equal(e.opened.length, 0); assert.equal(title.props.value, 'Unsaved task change');
  await e.click('Cancel'); await e.click('Prepare agent request'); assert.equal(e.opened.length, 1); assert.equal(e.navigation.at(-1), '/stored-A'); assert.equal(e.root().root.findAllByProps({ 'aria-label': 'Reviewed instructions' }).length, 0);
  const pane = e.opened[0]; await e.unmount(); await act(async () => { /* The companion is independently mounted by the real host. */ });
  await e.mount('CRMRoot', { ctx: e.ctx, boundIdentity: e.identity }); await e.click('Prepare agent request'); await e.fill(); await e.click('Open native chat');
  assert.equal(e.opened.length, 1, 'Existing split is reused'); assert.equal(e.field('Reviewed instructions').props.value, 'Summarize known CRM facts');
  await e.click('Discard prepared request'); assert.equal(e.root().root.findAllByProps({ 'aria-label': 'Reviewed instructions' }).length, 0); await e.finish();
}
// Draft construction pins its original conversation, including ABA before Preview.
for (const aba of [false, true]) {
  const e = await fixture(); await e.mount(); await e.fill();
  await e.change(() => { e.state.focusedStoredSessionId.set('stored-B'); if (aba) e.state.focusedStoredSessionId.set('stored-A'); });
  await e.click('Preview request'); assert.equal(e.calls.length, 0); assert.match(e.text(), /Discard this preparation/); await e.finish();
}
// Never silently round sub-millisecond reviewed input during creation.
{
  const e = await fixture(); await e.mount(); await e.fill(); await e.input('Future run time with UTC offset', '2030-11-10T14:00:00.123456-05:00');
  await e.click('Preview request'); assert.match(e.preview(), /"run_at": "2030-11-10T14:00:00.123456-05:00"/); await e.finish();
}
// Later contradictory or failed observations supersede a historical cancellation reason.
{
  const e = await fixture(); const work = clone(originalWork); work.job_id = 'job1'; work.reason = 'future_schedule_paused_running_run_not_cancelled';
  const paused = { kind: 'pause_observed', created_at: '2026-11-05T10:00:00+00:00', evidence: { job_id: 'job1', future_schedule_paused: true } };
  work.events = [paused]; assert.match(e.api.pauseEvidence(work), /historical observation is not a live check/);
  for (const event of [{ kind: 'job_observed', created_at: '2026-11-06T12:00:00+00:00', evidence: { job_id: 'job1', state: 'running', enabled: true } }, { kind: 'reconcile_unknown', created_at: '2026-11-06T12:00:00+00:00', evidence: {} }]) {
    work.events = [paused, event]; assert.match(e.api.pauseEvidence(work), /pause is unverified/); assert.doesNotMatch(e.api.pauseEvidence(work), /pause observed/);
  }
  await e.finish();
}
// Pause evidence must be for this exact job and at/after local invalidation.
{
  const e = await fixture(), work = clone(originalWork);
  work.job_id = 'job1'; work.state = 'cancelled';
  const oldPaused = { kind: 'job_observed', version: 7, created_at: '2026-11-05T10:00:00+00:00', evidence: { job_id: 'job1', state: 'paused', enabled: false } };
  const invalidated = { kind: 'intent_invalidated', version: 8, created_at: '2026-11-06T11:00:00+00:00', evidence: { reason: 'cancelled', host_cancelled: false } };
  const currentPaused = { ...clone(oldPaused), version: 8, created_at: '2026-11-06T12:00:00+00:00' };
  work.events = [oldPaused, invalidated];
  assert.match(e.api.pauseEvidence(work), /pause is unverified/, 'Pre-invalidation pause cannot prove a current future-schedule pause');
  assert.doesNotMatch(e.api.pauseEvidence(work), /pause observed/);
  work.events = [oldPaused, invalidated, currentPaused];
  assert.match(e.api.pauseEvidence(work), /pause observed at/);
  assert.match(e.api.pauseEvidence(work), /2026-11-06T12:00:00\+00:00/);
  assert.match(e.api.pauseEvidence(work), /historical observation is not a live check/);
  work.events = [oldPaused, invalidated, { ...currentPaused, evidence: { ...currentPaused.evidence, job_id: 'other-job' } }];
  assert.match(e.api.pauseEvidence(work), /pause is unverified/, 'A different job cannot satisfy the invalidation fence');
  assert.doesNotMatch(e.api.pauseEvidence(work), /pause observed/);
  await e.finish();
}
// Same-batch filter/query ABA restarts an invalidated pending report instead of loading forever.
for (const field of ['Coverage filter', 'Search coverage']) {
  const e = await fixture(), gates = [];
  e.coveragePages = () => { const gate = deferred(); gates.push(gate); return gate.promise; };
  await e.mount('CoverageQueue', { snapshotGeneration: 1, open() {} });
  const before = gates.length, handler = e.field(field).props.onChange;
  await e.change(() => { handler({ target: { value: field === 'Coverage filter' ? 'overdue' : 'temporary' } }); handler({ target: { value: field === 'Coverage filter' ? 'any' : '' } }); });
  assert.ok(gates.length > before, 'ABA must issue a replacement report read');
  await e.change(() => gates.at(-1).resolve({ items: [], total: 0, limit: 50, offset: 0, observed_at: '2026-11-06T13:00:00+00:00', workspace_token: e.token }));
  assert.match(e.text(), /No matching coverage evidence/); assert.equal(e.button('Refresh coverage evidence').props.disabled, false);
  for (const gate of gates.slice(0, -1)) await e.change(() => gate.resolve({ items: [], total: 999, limit: 50, offset: 0, observed_at: '2026-11-05T13:00:00+00:00', workspace_token: e.token }));
  assert.doesNotMatch(e.text(), /999 matching/); await e.finish();
}
// Assignment pagination also recovers from same-batch page ABA while a refresh waits.
{
  const e = await fixture(), gates = []; let gateReads = false;
  const page = offset => ({ items: [clone(e.work)], total: 701, limit: 25, offset, observed_at: '2026-11-06T13:00:00+00:00' });
  e.historyPages = params => { if (!gateReads) return page(Number(params.get('offset'))); const gate = deferred(); gates.push(gate); return gate.promise; };
  await e.mount('AssignedWork', { snapshotGeneration: 1 }); await e.click('Next assignments');
  const previous = e.button('Previous assignments').props.onClick, next = e.button('Next assignments').props.onClick;
  gateReads = true; await e.click('Refresh saved status'); const before = gates.length;
  await e.change(() => { previous(); next(); }); assert.ok(gates.length > before, 'Same final page must restart invalidated history read');
  await e.change(() => gates.at(-1).resolve(page(25))); assert.match(e.text(), /26–26 shown/); assert.equal(e.button('Refresh saved status').props.disabled, false);
  for (const gate of gates.slice(0, -1)) await e.change(() => gate.resolve({ ...page(25), items: [] }));
  assert.match(e.text(), /26–26 shown/); await e.finish();
}
// An assignment outside the first 100 history rows has an exact, fresh drillthrough.
{
  const e = await fixture(); e.work.id = 'a1'; e.work.version = 91; e.work.state = 'unknown'; e.work.reason = 'resume_outcome_unknown';
  e.coveragePages = params => ({ items: [{ id: 'assignment:a1', row_kind: 'assignment', kind: 'assignment', task: clone(e.task), contacts: [], risk_flags: ['needs_scheduling_review'], next_action: 'check_assignment', assignment: { ...clone(e.work), task_version: 3, human_owner: 'Reviewer', run_at: e.work.payload.run_at } }], total: 900, limit: 50, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00', workspace_token: e.token });
  e.historyPages = params => ({ items: [], total: 700, limit: 25, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00' });
  await e.mount('CRMRoot', { ctx: e.ctx, boundIdentity: e.identity }); await e.click('Tasks'); await e.click('Open exact assignment');
  assert.ok(e.calls.some(path => path.startsWith('/work/a1?'))); assert.match(e.text(), /Selected assignment from coverage/); assert.match(e.text(), /Version 91/);
  await e.click('Prepare check for selected assignment'); await e.click('Preview request'); assert.match(e.preview(), /"assignment_id": "a1"/); assert.match(e.preview(), /"assignment_version": 91/); await e.finish();
}

console.log('PASS assignment Preview/Copy read-only contracts; exact version/key/time/tool text; stale task/assignment/form/view/profile/chat ABA guards; async locks and clipboard uncertainty; paginated evidence queue/history; distinct report/host/task states; editor-safe native split and local discard. Real native clipboard/layout/Send and provider execution are not tested.');

// Explicit Save is a real local intent write, independent of chat; Review never writes.
{
  const e = await fixture({ noClipboard: true });
  for (const name of ['activeSessionId', 'focusedSessionId', 'focusedStoredSessionId', 'focusedSessionOwner']) e.state[name].set(null);
  await e.mount('SaveAssignment'); await e.fill();
  await e.input('Future run time with UTC offset', '2030-11-10T14:00:00.123456-05:00');
  await e.click('Review assignment'); assert.equal(e.writes.length, 0);
  const preview = JSON.parse(e.field('Exact assignment to save').props.value);
  assert.equal(preview.expected_task_version, 3); assert.equal(preview.run_at, '2030-11-10T14:00:00.123456-05:00');
  assert.equal(preview.workspace_token, undefined); assert.ok(preview.idempotency_key);
  assert.equal(e.field('Exact assignment to save').props.readOnly, true);
  const save = e.button('Save assignment').props.onClick;
  await e.change(() => { save(); save(); }); assert.equal(e.writes.length, 1);
  assert.equal(e.writes[0].idempotency_key, preview.idempotency_key);
  const saved = [...e.savedWorks.values()][0];
  assert.equal(saved.payload.run_at, '2030-11-10T19:00:00.123456+00:00');
  assert.match(e.text(), /Saved, not scheduled\. Assignment saved-work-1 · Version 1/);
  assert.equal(saved.state, 'pending'); assert.equal(saved.job_id, null);
  assert.equal(e.copies.length, 0); assert.equal(e.opened.length, 0); assert.equal(e.navigation.length, 0);
  await e.finish();
}
// The exact save receipt is independent of unrelated or failed oldest history pages.
for (const failedHistory of [false, true]) {
  const e = await fixture();
  e.historyPages = params => ({ items: [clone(originalWork)], total: 701, offset: Number(params.get('offset')), observed_at: '2026-11-06T13:00:00+00:00' });
  await e.mount('TaskWork', { snapshotGeneration: 1, companion: true });
  await e.click('Save future assignment'); await e.fill(); await e.click('Review assignment');
  const before = e.calls.filter(p => p.startsWith('/reports/work')).length; e.historyError = failedHistory;
  await e.click('Save assignment');
  assert.ok(e.calls.filter(p => p.startsWith('/reports/work')).length > before);
  assert.match(e.text(), /Saved, not scheduled/); assert.match(e.text(), /Assignment saved-work-1 · Version 1/);
  assert.match(e.text(), /701 saved assignments/); assert.match(e.text(), /a1/);
  if (failedHistory) assert.match(e.text(), /history could not be refreshed/);
  await e.click('Close assignment form'); await e.click('Prepare scheduling for saved assignment'); await e.click('Preview request');
  assert.match(e.preview(), /"assignment_id": "saved-work-1"/); assert.match(e.preview(), /"assignment_version": 1/);
  assert.equal(e.writes.length, 1); await e.finish();
}
// Failed or lost writes freeze the request, including across remounts and source changes.
for (const failure of ['rejected', 'lost', 'malformed']) {
  const e = await fixture(); await e.mount('SaveAssignment'); await e.fill(); await e.click('Review assignment');
  if (failure === 'rejected') e.saveError = true;
  if (failure === 'lost') e.saveGate = deferred();
  if (failure === 'malformed') e.saveReply = row => ({ ...row, payload: { ...row.payload, run_at: '2030-11-10T19:00:00.000001+00:00' } });
  await e.click('Save assignment');
  if (failure === 'lost') await e.change(() => e.saveGate.reject(Error('Lost response')));
  assert.match(e.text(), /Save was not confirmed/); assert.doesNotMatch(e.text(), /Saved, not scheduled|Secret backend/);
  const frozen = e.field('Exact assignment to save').props.value;
  assert.equal(e.root().root.findAllByProps({ 'aria-label': 'Reviewed instructions' }).length, 0);
  await e.unmount(); await e.mount('SaveAssignment');
  assert.equal(e.field('Exact assignment to save').props.value, frozen); assert.equal(e.button('Save assignment'), undefined);
  if (failure !== 'rejected') { e.task.version = 4; e.task.status = 'done'; }
  e.saveError = false; e.saveGate = null; e.saveReply = null;
  await e.click('Retry same save'); assert.deepEqual(e.writes[1], e.writes[0]);
  assert.equal(e.savedWorks.size, 1); assert.match(e.text(), /Saved, not scheduled/); await e.finish();
}
// Stale task, edited form, closed form and disabled snapshot callbacks never write.
for (const change of ['source', 'fields', 'selection', 'close']) {
  const e = await fixture(); await e.mount('SaveAssignment'); await e.fill();
  if (change === 'source') e.task.version++;
  await e.click('Review assignment');
  if (change === 'source') { assert.match(e.text(), /source task changed/); assert.equal(e.button('Save assignment'), undefined); }
  else {
    const save = e.button('Save assignment').props.onClick;
    if (change === 'fields') await e.input('Reviewed instructions', 'Changed before save');
    if (change === 'selection') e.viewRequest.current++;
    if (change === 'close') await e.click('Close assignment form');
    await e.change(save);
  }
  assert.equal(e.writes.length, 0); await e.finish();
}
{
  const e = await fixture(); await e.mount('SaveAssignment', { disabled: true });
  await e.change(() => e.button('Review assignment').props.onClick()); assert.equal(e.calls.length, 0); await e.finish();
}
// ABA prevents a late save response being shown as current, but preserves exact recovery.
for (const boundary of ['review', 'write']) for (const change of ['profile', 'connection', 'reconnect', 'selection', 'unmount']) {
  const e = await fixture(); await e.mount('SaveAssignment'); await e.fill();
  const gate = deferred();
  if (boundary === 'write') { await e.click('Review assignment'); e.saveGate = gate; await e.click('Save assignment'); }
  else { e.taskGate = gate; await e.click('Review assignment'); }
  if (change === 'profile') await e.change(() => { e.state.profile.set('other'); e.state.profile.set('work'); });
  if (change === 'connection') await e.change(() => { e.state.connectionId.set('other'); e.state.connectionId.set('source-a'); });
  if (change === 'reconnect') await e.change(() => { e.state.gateway.set('closed'); e.state.gateway.set('open'); });
  if (change === 'selection') e.viewRequest.current++;
  if (change === 'unmount') await e.unmount();
  await e.change(() => gate.resolve(boundary === 'write' ? clone([...e.savedWorks.values()][0]) : clone(e.task)));
  if (boundary === 'review') assert.equal(e.writes.length, 0);
  else if (['profile', 'connection', 'reconnect'].includes(change)) {
    assert.doesNotMatch(e.text(), /Saved, not scheduled/);
    await e.unmount(); const identity = e.api.routeIdentity(e.ctx), client = e.api.createRouteClient(e.ctx, identity);
    e.saveGate = null; await e.mount('SaveAssignment', { identity, client });
    await e.click('Retry same save'); assert.deepEqual(e.writes[1], e.writes[0]); assert.equal(e.savedWorks.size, 1);
    assert.match(e.text(), /Saved, not scheduled/); client.dispose();
  }
  await e.finish();
}
// An unresolved save survives normal record navigation; another create cannot be prepared blindly.
{
  const e = await fixture(); await e.mount('TaskWork', { snapshotGeneration: 1, companion: true });
  await e.click('Save future assignment'); await e.fill(); await e.click('Review assignment'); e.saveError = true; await e.click('Save assignment');
  await e.click('Close assignment form'); assert.equal(e.button('Prepare agent request').props.disabled, true);
  await e.click('Recover unconfirmed save'); assert.ok(e.button('Retry same save')); assert.equal(e.button('Review assignment'), undefined);
  await e.finish();
}
console.log('PASS explicit local Save: actual reviewed POST, no chat requirement/dispatch, exact microseconds/key/version, history refresh and exact receipt, stale/readonly/duplicate guards, frozen failure/lost-response replay and profile/connection/reconnect ABA recovery.');
// Only a confirmed receipt unlocks an explicit additional assignment, never a replacement.
{
  const e = await fixture(); await e.mount('TaskWork', { snapshotGeneration: 1, companion: true });
  await e.click('Save future assignment'); await e.fill(); await e.click('Review assignment'); await e.click('Save assignment'); await e.click('Close assignment form');
  const first = clone(e.writes[0]); await e.click('Save another future assignment');
  assert.match(e.text(), /Earlier saved assignment saved-work-1 remains unchanged/);
  await e.fill(); await e.click('Review assignment'); await e.click('Save assignment');
  assert.notEqual(e.writes[1].idempotency_key, first.idempotency_key); assert.equal(e.savedWorks.size, 2);
  assert.equal(e.savedWorks.get(first.idempotency_key).state, 'pending'); assert.equal(e.savedWorks.get(first.idempotency_key).job_id, null);
  assert.match(e.text(), /Assignment saved-work-2 · Version 1/); await e.finish();
}
// A Desktop route/display alias is not the backend profile. Only snapshot metadata binds it.
{
  const e = await fixture(); e.state.profile.set('display-alias');
  const identity = e.api.routeIdentity(e.ctx), client = e.api.createRouteClient(e.ctx, identity);
  await e.mount('SaveAssignment', { identity, client, workspaceProfile: 'work' }); await e.fill(); await e.click('Review assignment'); await e.click('Save assignment');
  assert.match(e.text(), /Saved, not scheduled/); assert.equal(e.writes.length, 1); client.dispose(); await e.finish();
}
// Closing Save restores its exact initiating control or current task heading, never a stale node/route.
for (const targetState of ['connected', 'disconnected', 'task-done', 'profile-aba']) {
  const e = await fixture(); const heading = { focus() { e.focusTargets.push(heading); } };
  const task = clone(originalTask); await e.mount('TaskWork', { task, snapshotGeneration: 1, companion: true, taskHeadingRef: { current: heading } });
  const launcher = e.nodeMocks.findLast(n => n.name === 'Save future assignment'); assert.ok(launcher);
  await e.change(() => e.button('Save future assignment').props.onClick({ currentTarget: launcher }));
  if (targetState !== 'connected') launcher.isConnected = false;
  if (targetState === 'task-done') task.status = 'done';
  if (targetState === 'profile-aba') await e.change(() => { e.state.profile.set('other'); e.state.profile.set('work'); });
  const before = e.focusTargets.length; await e.click('Close assignment form');
  if (targetState === 'profile-aba') assert.equal(e.focusTargets.length, before);
  else if (targetState === 'connected') assert.equal(e.focusTargets.at(-1), launcher);
  else if (targetState === 'task-done') assert.equal(e.focusTargets.at(-1), heading);
  else { assert.notEqual(e.focusTargets.at(-1), launcher); assert.equal(e.focusTargets.at(-1).name, 'Save future assignment'); }
  assert.equal(e.writes.length, 0); await e.finish();
}
