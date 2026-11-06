// Pure synthetic protocol tests. No host, model, SDK transport or REST calls.
// node tests/execution_bridge.mjs
// Optional exact Python store mapping (existing env, no installation):
// CRM_EXECUTION_TEST_PYTHON=/path/to/python node tests/execution_bridge.mjs
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {test} from 'node:test';

const source = await readFile(new URL('../desktop/execution-bridge.js', import.meta.url), 'utf8');
const {createExecutionBridge, inspectReadScope, APPROVED_READ_TOOLS, redactHostResult} =
  await import(`data:text/javascript;base64,${Buffer.from(source + '\n//# sourceURL=execution-bridge.js').toString('base64')}`);
const copy = (x) => JSON.parse(JSON.stringify(x));
const row = (a) => a.occurrences.at(-1);
const route = {connectionId: 'registry-1', profile: 'synthetic', targetProfile: 'target-profile', mode: 'local'};
const capture = {route, workspace: 'synthetic-workspace', profile: 'synthetic',
  host_connection_identity: 'synthetic-connection-binding', host_profile_identity: 'authority-profile-1',
  desktop_protocol: 'hermes-gateway-v1'};
const input = {assignment_id: 'assignment-1', occurrence_id: 'occurrence-1'};
const deferred = () => { let resolve; const promise = new Promise((done) => resolve = done); return {promise, resolve}; };
const snapshot = () => ({session_id: 'session-1', stored_session_id: 'session-1', authority_epoch: 1,
  revision: 0, execution_generation: 0, replay_epoch: 'replay-1', subscription_id: 'subscription-1',
  last_sequence: 0, running: false, messages: [], message_count: 0, pending: [], prompts: [],
  info: {desktop_protocol: 'hermes-gateway-v1', profile_id: capture.host_profile_identity,
    enabled_toolsets: ['crm_read'], tools: {discovery: ['tool_search', 'tool_describe', 'tool_call']}}});
const inventory = () => ({sections: [{name: 'crm_read', tools: APPROVED_READ_TOOLS.map((name) =>
  ({name, description: `Synthetic ${name}`}))}], total: 8});
const receipt = (status = 'queued', outcome = null, result) => ({admission_id: 'admission-1',
  ref: {profile_id: capture.host_profile_identity, session_id: 'session-1'}, sequence: 1,
  status, outcome, authority_epoch: 1, execution_generation: status === 'queued' ? null : 7,
  ...(result === undefined ? {} : {result})});
const initial = () => ({id: input.assignment_id, workspace: capture.workspace, profile: capture.profile,
  generation: 1, digest: 'a'.repeat(64), payload: {workspace: capture.workspace, profile: capture.profile,
    host_connection_identity: capture.host_connection_identity, host_profile_identity: capture.host_profile_identity,
    host_route: copy(route), run_at: null, action: 'internal', authorization_scope: 'internal_crm_only',
    prompt: '  Frozen synthetic instruction\n', task_version: 1, task_status: 'open', required_tools: ['crm_task_get']},
  occurrences: [{id: input.occurrence_id, generation: 1, version: 1, state: 'pending',
    session_request_id: 'create-stable-1', submission_id: 'submit-stable-1', session_id: null,
    admission_id: null, dispatch_started: 0, submit_started: false, cancel_requested: 0,
    safe_to_retry: 0, review_status: 'not_ready', scope_digest: null, receipts: []}]});

function fixture(options = {}) {
  const env = {assignment: initial(), events: [], generation: 1, current: true, cancelled: false,
    sourceVersion: 1, hooks: {}, routes: [copy(route)], snapshot: snapshot(), inventory: inventory(),
    receipt: receipt(), cancelReceipt: receipt('terminal', 'cancelled'),
    runtime: {profile_id: capture.host_profile_identity, instance_id: 'instance-1', authority_epoch: 1,
      capabilities: ['durable-admission-v1'], session_create: {sources: ['gui'], parameters: ['request_id', 'source', 'toolsets']}}};
  const invoke = async (name, args, fn) => {
    env.events.push({name, args: copy(args)});
    await env.hooks[`before:${name}`]?.(args);
    const value = await fn();
    await env.hooks[`after:${name}`]?.(value, args);
    return copy(value);
  };
  const store = {get: (id) => invoke('get', {id}, () => env.assignment)};
  for (const method of ['begin_dispatch', 'observe', 'observe_host', 'record_runtime', 'record_scope',
    'prepare_submit', 'request_cancel', 'cancel_undispatched', 'mark']) {
    store[method] = (id, params) => invoke(method, {id, ...params}, () => {
      const r = row(env.assignment);
      assert.equal(id, r.id);
      if (params.version !== r.version || params.generation !== r.generation) throw Error('CAS conflict');
      switch (method) {
        case 'begin_dispatch':
          if (r.state !== 'pending' || r.cancel_requested || env.sourceVersion !== 1) throw Error('Blocked');
          Object.assign(r, {state: 'unknown', dispatch_started: 1}); break;
        case 'record_runtime':
          r.runtime = {reference: `runtime:${r.version}`, ...params}; break;
        case 'observe':
          assert.equal(params.kind, 'session');
          r.session_id = params.session_id; break;
        case 'record_scope':
          assert.equal(params.runtime_reference, r.runtime.reference);
          r.scope = copy(params);
          r.scope_digest = createHash('sha256').update(JSON.stringify(params)).digest('hex'); break;
        case 'prepare_submit':
          if (r.cancel_requested || env.sourceVersion !== env.assignment.payload.task_version ||
              params.scope_digest !== r.scope_digest || !!params.replay !== !!r.submit_started) throw Error('Blocked');
          r.submit_started = true; r.state = 'unknown'; break;
        case 'observe_host': {
          r.admission_id = params.admission_id;
          // Only a test stand-in. Actual state/result interpretation is verified
          // independently against Python below, not claimed from this mock.
          const f = params.redacted_result;
          r.state = params.status === 'queued' ? 'admitted' : params.status === 'started' ? 'running' : 'unknown';
          if (params.status === 'terminal' && params.outcome === 'cancelled') r.state = 'cancelled';
          if (params.status === 'terminal' && params.outcome === 'completed' && f?.final_response &&
              !f.failed && !f.error && !f.interrupted && f.completed !== false) r.state = 'succeeded';
          if (r.state === 'succeeded') r.review_status = 'awaiting_human_review';
          r.receipts.push(copy(params)); break;
        }
        case 'request_cancel': r.cancel_requested = 1; break;
        case 'cancel_undispatched': assert.equal(r.dispatch_started, 0); r.state = 'cancelled'; break;
        case 'mark': r.state = params.state; r.reason = params.reason; break;
      }
      r.version++;
      return env.assignment;
    });
  }
  const requestProfile = (actualRoute, method, params) => invoke(method, params, () => {
    assert.deepEqual(actualRoute, route, 'Only captured descriptor routing, no profile-name fallback');
    if (method === 'runtime.describe') return env.runtime;
    if (method === 'session.create' || method === 'session.resume') return env.snapshot;
    if (method === 'tools.show') return env.inventory;
    if (method === 'prompt.submit' || method === 'prompt.receipt') return env.receipt;
    if (method === 'prompt.cancel') return env.cancelReceipt;
    assert.fail(`Unexpected host call ${method}`);
  });
  const deps = {requestProfile, profileRoutes: () => invoke('profileRoutes', {}, () => env.routes), store,
    capture, isCurrent: () => env.current, getGeneration: () => env.generation,
    isCancelled: () => env.cancelled, experimentalDispatch: true, ...options};
  env.store = store; env.deps = deps; env.bridge = createExecutionBridge(deps);
  env.calls = (name) => env.events.filter((event) => event.name === name);
  return env;
}
const rejectsCode = (promise, code) => assert.rejects(promise, (error) => error.code === code);

await test('Default disabled; adapter/protocol identity capabilities fail closed', async () => {
  const e = fixture({experimentalDispatch: false});
  await rejectsCode(e.bridge.start(input), 'experimental_dispatch_disabled');
  assert.equal(e.events.length, 0);
  for (const method of ['record_runtime', 'record_scope', 'prepare_submit', 'observe_host']) {
    const store = {...e.store}; delete store[method];
    assert.throws(() => createExecutionBridge({...e.deps, store}), /durable_adapter_capabilities_missing/);
  }
  for (const property of ['host_profile_identity', 'host_connection_identity']) {
    const bad = {...capture}; delete bad[property];
    assert.throws(() => createExecutionBridge({...e.deps, capture: bad}), /captured_identity_required/);
  }
  assert.throws(() => createExecutionBridge({...e.deps, capture: {...capture, desktop_protocol: 'legacy'}}),
    /canonical_protocol_required/);
});

await test('Stable IDs and persistence ordering; deferred catalog never bypasses full tools.show', async () => {
  const e = fixture();
  const result = await e.bridge.start(input);
  assert.equal(row(result).state, 'admitted');
  assert.deepEqual(e.events.map((x) => x.name), ['get', 'begin_dispatch', 'profileRoutes', 'runtime.describe',
    'record_runtime', 'session.create', 'observe', 'tools.show', 'record_scope', 'prepare_submit', 'prompt.submit', 'observe_host']);
  assert.deepEqual(e.calls('session.create')[0].args, {request_id: 'create-stable-1', source: 'gui', toolsets: ['crm_read', 'no_mcp']});
  assert.deepEqual(e.calls('prompt.submit')[0].args, {session_id: 'session-1', submission_id: 'submit-stable-1',
    text: '  Frozen synthetic instruction\n', finite: true});
  assert.equal(e.calls('observe_host')[0].args.execution_generation, null);
  await rejectsCode(e.bridge.start(input), 'new_pending_intent_required');
  assert.equal(e.calls('prompt.submit').length, 1);
});

await test('Synchronous duplicate-start lock prevents duplicate transport even before first await', async () => {
  const e = fixture(), gate = deferred();
  e.hooks['before:get'] = () => gate.promise;
  const first = e.bridge.start(input);
  await rejectsCode(e.bridge.start(input), 'operation_in_progress');
  gate.resolve(); await first;
  assert.equal(e.calls('session.create').length, 1); assert.equal(e.calls('prompt.submit').length, 1);
});

await test('Scheduled, foreign, mutated and stale-generation intents cannot dispatch', async () => {
  for (const change of [
    (a) => a.payload.run_at = '2030-01-01T00:00:00Z',
    (a) => a.workspace = 'other',
    (a) => a.payload.host_profile_identity = 'display-name',
    (a) => a.payload.host_connection_identity = 'other-connection',
    (a) => a.payload.host_route.targetProfile = 'other-target',
    (a) => a.generation = 2,
  ]) {
    const e = fixture(); change(e.assignment);
    await assert.rejects(e.bridge.start(input));
    assert.equal(e.calls('session.create').length, 0); assert.equal(e.calls('prompt.submit').length, 0);
  }
  const e = fixture();
  e.hooks['after:record_scope'] = () => { e.assignment.payload.prompt = 'Changed'; };
  await rejectsCode(e.bridge.start(input), 'immutable_intent_changed');
  assert.equal(e.calls('prompt.submit').length, 0);
});

await test('Runtime authority and full route mapping checks precede session.create', async () => {
  for (const modify of [
    (e) => e.runtime.profile_id = 'synthetic',
    (e) => e.runtime.capabilities = [],
    (e) => e.runtime.session_create.parameters = ['source'],
    (e) => e.routes[0].targetProfile = 'different-owner',
    (e) => e.routes = [],
    (e) => e.routes.push(copy(route)),
  ]) {
    const e = fixture(); modify(e);
    await assert.rejects(e.bridge.start(input));
    assert.equal(e.calls('session.create').length, 0);
  }
});

await test('Session schema, exact identity and empty fresh conversation required', async () => {
  for (const modify of [
    (s) => delete s.info.desktop_protocol,
    (s) => s.info.profile_id = 'wrong',
    (s) => delete s.execution_generation,
    (s) => s.pending = [{}],
    (s) => s.message_count = 1,
    (s) => s.running = true,
  ]) {
    const e = fixture(); modify(e.snapshot);
    await assert.rejects(e.bridge.start(input));
    assert.equal(e.calls('prompt.submit').length, 0);
    assert.equal(row(e.assignment).state, 'unknown');
  }
});

await test('Owner epoch change between runtime and snapshot fails before any task text', async () => {
  const e = fixture(); e.snapshot.authority_epoch++;
  await rejectsCode(e.bridge.start(input), 'runtime_snapshot_epoch_mismatch');
  assert.equal(e.calls('prompt.submit').length, 0); assert.equal(e.calls('record_scope').length, 0);
  assert.equal(row(e.assignment).state, 'unknown');
  const resumed = fixture(); await resumed.bridge.start(input); resumed.snapshot.authority_epoch++;
  await rejectsCode(resumed.bridge.resume(input), 'runtime_snapshot_epoch_mismatch');
  assert.equal(resumed.calls('prompt.receipt').length, 0);
});

await test('Missing, widened, malformed or unknown full/visible catalogs never receive text; no fixes', async () => {
  const changes = [
    (e) => e.snapshot.info.enabled_toolsets.push('crm_write'),
    (e) => e.snapshot.info.enabled_toolsets = ['crm_read', 'no_mcp'],
    (e) => delete e.snapshot.info.tools,
    (e) => e.snapshot.info.tools = {tools: ['crm_task_create']},
    (e) => e.snapshot.info.tools = {tools: ['tool_call']},
    (e) => e.snapshot.info.tools = {tools: ['crm_task_get', 'crm_task_get']},
    (e) => e.inventory = {},
    (e) => e.inventory.sections = [],
    (e) => e.inventory.total = 7,
    (e) => e.inventory.sections[0].tools.pop(),
    (e) => e.inventory.sections[0].tools.push({name: 'crm_task_create', description: ''}),
    (e) => e.inventory.sections[0].tools[0].name = 'crm_future_read',
    (e) => e.inventory.sections[0].tools[0].name = 'crm_task_get',
    (e) => e.inventory.sections[0].tools[0].name = null,
    (e) => delete e.inventory.sections[0].tools[0].description,
    (e) => e.inventory.sections[0].name = 'terminal',
    (e) => e.inventory.extra = 'unknown schema',
  ];
  for (const change of changes) {
    const e = fixture(); change(e);
    await assert.rejects(e.bridge.start(input));
    assert.equal(e.calls('prompt.submit').length, 0);
    assert.equal(row(e.assignment).state, 'blocked');
    assert.equal(row(e.assignment).safe_to_retry, 0);
    assert.ok(e.events.every((x) => !/config|toolsets\.set|settings|cron/.test(x.name)));
  }
  assert.deepEqual(inspectReadScope({...snapshot(), info: {...snapshot().info,
    tools: {crm_read: [...APPROVED_READ_TOOLS]}}}, inventory()).tools, [...APPROVED_READ_TOOLS]);
});

await test('Each awaited initial boundary rejects same-tick generation ABA and performs no later call', async () => {
  const names = ['get', 'begin_dispatch', 'profileRoutes', 'runtime.describe', 'record_runtime',
    'session.create', 'observe', 'tools.show', 'record_scope', 'prepare_submit', 'prompt.submit', 'observe_host'];
  for (const target of names) {
    const e = fixture();
    e.hooks[`after:${target}`] = () => { e.generation += 2; e.current = true; };
    await rejectsCode(e.bridge.start(input), 'stale_route');
    assert.equal(e.events.at(-1).name, target, `No action after stale ${target}`);
  }
});

await test('Local cancellation at each awaited boundary suppresses further starts without invented cancellation', async () => {
  for (const target of ['get', 'begin_dispatch', 'profileRoutes', 'runtime.describe', 'record_runtime',
    'session.create', 'observe', 'tools.show', 'record_scope', 'prepare_submit', 'prompt.submit', 'observe_host']) {
    const e = fixture(); e.hooks[`after:${target}`] = () => { e.cancelled = true; };
    await rejectsCode(e.bridge.start(input), 'cancellation_requested');
    assert.equal(e.events.at(-1).name, target);
    assert.notEqual(row(e.assignment).state, 'cancelled');
  }
});

await test('Resume and cancel guard every awaited boundary against stale route', async () => {
  for (const operation of ['resume', 'cancel']) {
    const phases = ['get', ...(operation === 'cancel' ? ['request_cancel'] : []),
      'profileRoutes', 'runtime.describe', 'record_runtime', 'session.resume',
      operation === 'cancel' ? 'prompt.cancel' : 'prompt.receipt', 'observe_host'];
    for (const target of phases) {
      const e = fixture(); await e.bridge.start(input); e.events.length = 0;
      e.hooks[`after:${target}`] = () => { e.generation++; };
      await rejectsCode(e.bridge[operation](input), 'stale_route');
      assert.equal(e.events.at(-1).name, target);
    }
  }
});

await test('Independent bridge instances cannot both pass durable start CAS', async () => {
  const e = fixture(), gate = deferred(); let count = 0;
  e.hooks['after:get'] = async () => { if (++count === 2) gate.resolve(); await gate.promise; };
  const second = createExecutionBridge(e.deps);
  const results = await Promise.allSettled([e.bridge.start(input), second.start(input)]);
  assert.equal(results.filter((x) => x.status === 'fulfilled').length, 1);
  assert.equal(e.calls('session.create').length, 1); assert.equal(e.calls('prompt.submit').length, 1);
});

await test('Durable task mutation/cancel immediately before prepare_submit prevents task text', async () => {
  for (const mutate of [(e) => e.sourceVersion++, (e) => row(e.assignment).cancel_requested = 1]) {
    const e = fixture(); e.hooks['before:prepare_submit'] = () => mutate(e);
    await rejectsCode(e.bridge.start(input), 'store_request_uncertain');
    assert.equal(e.calls('prompt.submit').length, 0);
    assert.equal(row(e.assignment).state, 'unknown');
  }
});

await test('Lost create replay reuses request identity; no automatic second start or retry generation', async () => {
  const e = fixture();
  e.hooks['after:session.create'] = () => { throw Error('socket lost after commit'); };
  await rejectsCode(e.bridge.start(input), 'host_request_uncertain');
  assert.equal(row(e.assignment).state, 'unknown');
  assert.equal(row(e.assignment).session_id, null);
  await rejectsCode(e.bridge.start(input), 'new_pending_intent_required');
  delete e.hooks['after:session.create'];
  await e.bridge.resume(input, {replay: true});
  assert.equal(new Set(e.calls('session.create').map((x) => x.args.request_id)).size, 1);
  assert.equal(e.calls('prompt.submit').length, 1);
  assert.equal(row(e.assignment).generation, 1);
});

await test('Lost submit resumes original session and replays exact frozen submission only', async () => {
  const e = fixture();
  e.hooks['after:prompt.submit'] = () => { throw Error('lost reply'); };
  await rejectsCode(e.bridge.start(input), 'host_request_uncertain');
  assert.equal(row(e.assignment).submit_started, true);
  assert.equal(row(e.assignment).admission_id, null);
  delete e.hooks['after:prompt.submit'];
  e.runtime.authority_epoch = 2; e.runtime.instance_id = 'restarted-owner';
  e.snapshot.authority_epoch = e.receipt.authority_epoch = 2;
  await e.bridge.resume(input, {replay: true});
  assert.equal(e.calls('session.create').length, 1);
  assert.equal(e.calls('session.resume').length, 1);
  assert.deepEqual(e.calls('prompt.submit')[0].args, e.calls('prompt.submit')[1].args);
  assert.equal(e.calls('prepare_submit')[1].args.replay, true);
  assert.equal(e.calls('record_scope')[1].args.resumed_session_id, 'session-1');
  await e.bridge.resume(input, {replay: true});
  assert.equal(e.calls('prompt.submit').length, 2, 'Known admission is read, never resubmitted');
  assert.equal(e.calls('prompt.receipt').length, 1);
});

await test('Lost store phase responses and generic errors never trigger implicit retry or claim nonadmission', async () => {
  for (const target of ['begin_dispatch', 'record_runtime', 'observe', 'record_scope', 'prepare_submit', 'observe_host']) {
    const e = fixture(); e.hooks[`after:${target}`] = () => { throw Error('lost store acknowledgement'); };
    await rejectsCode(e.bridge.start(input), 'store_request_uncertain');
    assert.equal(e.events.at(-1).name, target);
    assert.equal(row(e.assignment).safe_to_retry, 0);
    assert.equal(e.assignment.occurrences.length, 1);
  }
  const e = fixture(); e.hooks['before:prompt.submit'] = () => { throw Error('not_found'); };
  await rejectsCode(e.bridge.start(input), 'host_request_uncertain');
  assert.equal(row(e.assignment).state, 'unknown'); assert.equal(row(e.assignment).safe_to_retry, 0);
});

await test('Receipts bind exact initial terminal/unknown identities without invented queued state', async () => {
  for (const hostReceipt of [receipt('unknown'), receipt('terminal', 'completed', {final_response: 'Secret-looking answer'}),
    receipt('terminal', 'completed'), receipt('terminal', 'completed', {final_response: 'Answer', failed: true}),
    receipt('terminal', 'cancelled'), receipt('terminal', 'future-outcome')]) {
    const e = fixture(); e.receipt = hostReceipt;
    await e.bridge.start(input);
    assert.equal(e.calls('observe_host').length, 1);
    const observed = e.calls('observe_host')[0].args;
    assert.equal(observed.status, hostReceipt.status); assert.equal(observed.outcome, hostReceipt.outcome);
    assert.equal(observed.admission_id, hostReceipt.admission_id);
    assert.equal(observed.execution_generation, 7, 'Host generation is not CRM generation');
    assert.ok(!Object.hasOwn(observed, 'state'));
    assert.ok(!JSON.stringify(observed).includes('Secret-looking answer'));
  }
});

await test('Receipt schema/identity mismatch, voice_stopped, and unsafe result schemas stay unknown', async () => {
  for (const modify of [
    (r) => r.ref.profile_id = 'wrong', (r) => r.ref.session_id = 'wrong',
    (r) => r.sequence = 0, (r) => r.execution_generation = '1', (r) => delete r.outcome,
    (r) => r.status = 'voice_stopped', (r) => r.result = {final_response: 'x', unfamiliar_failure_flag: true},
  ]) {
    const e = fixture(); modify(e.receipt);
    await assert.rejects(e.bridge.start(input));
    assert.equal(row(e.assignment).state, 'unknown'); assert.equal(e.calls('observe_host').length, 0);
  }
  const e = fixture(); await e.bridge.start(input);
  e.receipt.admission_id = 'different';
  await rejectsCode(e.bridge.resume(input), 'host_admission_mismatch');
  assert.equal(row(e.assignment).admission_id, 'admission-1');
});

await test('Resume revalidates route and exact session; failed mapping cannot silently switch', async () => {
  const e = fixture(); await e.bridge.start(input);
  e.routes[0].targetProfile = 'new-target';
  await rejectsCode(e.bridge.resume(input), 'route_mapping_changed');
  assert.equal(e.calls('session.resume').length, 0);
  e.routes = [copy(route)]; e.snapshot.session_id = 'other-session';
  await rejectsCode(e.bridge.resume(input), 'host_session_mismatch');
  assert.equal(e.calls('prompt.receipt').length, 0);
});

await test('Queued cancellation has no result; running cancellation stays running with intent retained', async () => {
  for (const hostCancel of [receipt('terminal', 'cancelled'), receipt('started')]) {
    const e = fixture(); await e.bridge.start(input); e.cancelReceipt = hostCancel;
    const result = await e.bridge.cancel(input);
    assert.equal(row(result).cancel_requested, 1);
    assert.equal(row(result).state, hostCancel.status === 'started' ? 'running' : 'cancelled');
    assert.deepEqual(e.calls('prompt.cancel')[0].args, {session_id: 'session-1', admission_id: 'admission-1'});
    const cancelObservation = e.calls('observe_host').at(-1).args;
    assert.equal(cancelObservation.source, 'prompt.cancel'); assert.equal(cancelObservation.redacted_result, null);
    if (hostCancel.status === 'started') {
      e.receipt = receipt('terminal', 'cancelled');
      const ended = await e.bridge.resume(input);
      assert.equal(row(ended).state, 'cancelled', 'Cancellation latch does not prevent later receipt reconciliation');
    }
  }
});

await test('In-flight local cancellation persists before host response and blocks later task text', async () => {
  const e = fixture(), gate = deferred(), entered = deferred();
  e.hooks['before:session.create'] = () => { entered.resolve(); return gate.promise; };
  const start = e.bridge.start(input); await entered.promise;
  await rejectsCode(e.bridge.cancel(input), 'cancellation_requires_reconciliation');
  assert.equal(row(e.assignment).cancel_requested, 1);
  gate.resolve(); await rejectsCode(start, 'cancellation_requested');
  assert.equal(e.calls('prompt.submit').length, 0);
  assert.equal(row(e.assignment).state, 'unknown');
});

await test('Undispatched cancellation is local; uncertain submission never invents cancelled or replays after cancel', async () => {
  const e = fixture(); const result = await e.bridge.cancel(input);
  assert.equal(row(result).state, 'cancelled'); assert.equal(e.calls('runtime.describe').length, 0);
  const lost = fixture(); lost.hooks['after:prompt.submit'] = () => { throw Error('lost'); };
  await rejectsCode(lost.bridge.start(input), 'host_request_uncertain');
  await rejectsCode(lost.bridge.cancel(input), 'cancellation_requires_reconciliation');
  assert.equal(row(lost.assignment).cancel_requested, 1);
  assert.equal(row(lost.assignment).state, 'unknown');
  assert.equal(lost.calls('prompt.cancel').length, 0);
  await rejectsCode(lost.bridge.resume(input, {replay: true}), 'cancellation_requested');
  assert.equal(lost.calls('prompt.submit').length, 1);
});

await test('Read-scope drift on uncertain replay is blocked without fixing configuration', async () => {
  const e = fixture(); e.hooks['after:prompt.submit'] = () => { throw Error('lost'); };
  await rejectsCode(e.bridge.start(input), 'host_request_uncertain');
  delete e.hooks['after:prompt.submit']; e.snapshot.info.enabled_toolsets.push('crm_write');
  await rejectsCode(e.bridge.resume(input, {replay: true}), 'scope_toolsets_rejected');
  assert.equal(e.calls('prompt.submit').length, 1);
  assert.equal(row(e.assignment).state, 'unknown'); assert.equal(row(e.assignment).safe_to_retry, 0);
});

await test('Redaction never forwards raw final answer, errors, transcripts, usage or failure metadata', () => {
  assert.deepEqual(redactHostResult({final_response: 'private output', messages: [{secret: 'x'}],
    usage: {cost: 1}, error: 'private error', failed: true, completed: false}),
    {final_response: '[nonempty response omitted]', failed: true, completed: false, error: true});
  assert.deepEqual(redactHostResult({final_response: 'answer', exit_reason: 'budget_exhausted'}),
    {final_response: '[nonempty response omitted]', error: true});
  for (const key of ['billing_block', 'billing_unverified', 'usage_limit', 'error_surface']) {
    assert.equal(redactHostResult({final_response: 'Answer', completed: true, [key]: {private: 'detail'}}).error, true,
      `Failure marker ${key} cannot become apparent success`);
  }
  assert.equal(redactHostResult(null), null);
  assert.deepEqual(redactHostResult({final_response: 'Answer', completed: true, failed: false,
    interrupted: false, partial: false, turn_exit_reason: 'text_response(finish_reason=stop)',
    last_reasoning: 'never forward', base_url: 'never forward', _messages_are_turn_suffix: true,
    messages: [], _turn_user_row: {secret: 'never forward'}, input_tokens: 1}),
    {final_response: '[nonempty response omitted]', failed: false, interrupted: false, completed: true});
});

// A separate opt-in test process maps each injected method directly to the real
// Python store. It never opens a host connection. Python is a preexisting env.
const python = process.env.CRM_EXECUTION_TEST_PYTHON;
await test('Real SQLite store adapter: queued/completed, missing/contradictory results, lost-submit replay/cancel, task race',
  {skip: !python && 'Set CRM_EXECUTION_TEST_PYTHON to an existing environment with the project dependencies'}, async () => {
    const child = spawn(python, ['-u', new URL('./execution_bridge_store.py', import.meta.url).pathname],
      {stdio: ['pipe', 'pipe', 'pipe'], env: {PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: '1'}});
    let serial = 0, stderr = '';
    const waiting = new Map();
    child.stderr.on('data', (data) => stderr += data.toString());
    const lines = createInterface({input: child.stdout});
    lines.on('line', (line) => {
      const result = JSON.parse(line), pending = waiting.get(result.id);
      waiting.delete(result.id);
      if (result.error) pending.reject(Error(result.error)); else pending.resolve(result.result);
    });
    child.on('error', (error) => { for (const item of waiting.values()) item.reject(error); });
    child.on('exit', (code) => {
      for (const item of waiting.values()) item.reject(Error(`Fixture exited ${code}: ${stderr}`));
    });
    const call = (method, id, params) => new Promise((resolve, reject) => {
      const request_id = ++serial; waiting.set(request_id, {resolve, reject});
      child.stdin.write(JSON.stringify({request_id, method, id, params}) + '\n');
    });
    const store = Object.fromEntries(['get', 'begin_dispatch', 'observe', 'observe_host', 'record_runtime',
      'record_scope', 'prepare_submit', 'request_cancel', 'cancel_undispatched', 'mark']
      .map((method) => [method, (id, params) => call(method, id, params)]));
    let hostCounter = 0;
    const realFixture = async () => {
      const a = await call('init'), e = fixture(), suffix = ++hostCounter;
      e.snapshot.session_id = e.snapshot.stored_session_id = `real-session-${suffix}`;
      e.receipt.admission_id = `real-admission-${suffix}`; e.receipt.ref.session_id = e.snapshot.session_id;
      e.cancelReceipt.admission_id = e.receipt.admission_id; e.cancelReceipt.ref.session_id = e.snapshot.session_id;
      e.realInput = {assignment_id: a.id, occurrence_id: row(a).id}; e.original = a;
      e.bridge = createExecutionBridge({...e.deps, store, capture: {...capture, workspace: a.workspace}});
      return e;
    };
    try {
      const happy = await realFixture();
      let a = await happy.bridge.start(happy.realInput);
      assert.equal(row(a).state, 'admitted');
      // Admission owner_epoch is historical: the current runtime/snapshot can
      // advance without rewriting a completed admission's original receipt epoch.
      happy.runtime.authority_epoch = happy.snapshot.authority_epoch = 2;
      happy.runtime.instance_id = 'new-runtime-owner';
      happy.receipt = {...happy.receipt, status: 'terminal', outcome: 'completed', execution_generation: 9,
        result: {final_response: 'Synthetic complete result', completed: true}};
      a = await happy.bridge.resume(happy.realInput);
      assert.equal(row(a).state, 'succeeded'); assert.equal(row(a).review_status, 'awaiting_human_review');
      assert.equal(row(a).runtime.authority_epoch, 2);
      const historical = row(a).receipts.filter((r) => r.kind === 'host').map((r) => JSON.parse(r.evidence))
        .find((r) => r.host_observation.status === 'terminal');
      assert.equal(historical.host_observation.authority_epoch, 1, 'Retain authentic historical owner epoch');
      assert.equal((await call('source_task', a.task_id)).status, 'open');
      assert.ok(!JSON.stringify(a).includes('Synthetic complete result'));
      for (const result of [undefined, {final_response: 'Answer', failed: true}, {final_response: 'Answer', completed: false},
        {final_response: 'Answer', completed: true, billing_block: {provider: 'synthetic'}}]) {
        const e = await realFixture();
        e.receipt = {...e.receipt, status: 'terminal', outcome: 'completed', result};
        a = await e.bridge.start(e.realInput);
        assert.equal(row(a).state, 'unknown'); assert.equal(row(a).admission_id, e.receipt.admission_id);
        assert.equal(row(a).receipts.filter((x) => x.kind === 'host').length, 1);
      }
      const lost = await realFixture();
      lost.hooks['after:prompt.submit'] = () => { throw Error('lost receipt after host admission'); };
      await rejectsCode(lost.bridge.start(lost.realInput), 'host_request_uncertain');
      a = await call('get', lost.realInput.assignment_id);
      assert.equal(row(a).state, 'unknown'); assert.equal(row(a).submit_started, true);
      delete lost.hooks['after:prompt.submit'];
      lost.runtime.authority_epoch++; lost.runtime.instance_id = 'restarted-instance';
      lost.snapshot.authority_epoch = lost.receipt.authority_epoch = lost.cancelReceipt.authority_epoch = lost.runtime.authority_epoch;
      a = await lost.bridge.resume(lost.realInput, {replay: true});
      assert.equal(row(a).state, 'admitted'); assert.equal(row(a).submission.replay, true);
      assert.equal(row(a).submission.submit_attempt, 2);
      assert.deepEqual(lost.calls('prompt.submit')[0].args, lost.calls('prompt.submit')[1].args);
      a = await lost.bridge.cancel(lost.realInput);
      assert.equal(row(a).state, 'cancelled'); assert.equal(row(a).cancel_requested, 1);
      assert.equal((await call('source_task', a.task_id)).status, 'open');
      const changed = await realFixture();
      changed.hooks['after:tools.show'] = () => call('edit_source_task', changed.original.task_id);
      await rejectsCode(changed.bridge.start(changed.realInput), 'store_request_uncertain');
      assert.equal(changed.calls('prompt.submit').length, 0);
      a = await call('get', changed.realInput.assignment_id);
      assert.equal(row(a).state, 'unknown'); assert.equal(row(a).submit_started, false);
    } finally {
      child.stdin.end();
      await new Promise((resolve) => child.once('exit', resolve));
      lines.close();
    }
  });
