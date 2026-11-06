/**
 * Experimental, unwired immediate-execution protocol foundation.
 *
 * No SDK import, fetch, credentials, timers, model/provider overrides or scheduler.
 * Dispatch is DISABLED by default. Opt-in is for isolated protocol validation, not
 * a production safety claim: tools.show is a snapshot, NOT an atomic host ceiling.
 * Real-model execution, actual authenticated transport and closed-browser dispatch
 * are not established by this module or its synthetic tests.
 *
 * Inject a captured public SDK requestProfile(route, method, params), profileRoutes,
 * and a scoped store adapter. There are deliberately no REST paths here. The store
 * returns a complete ExecutionStore assignment from get and every mutation:
 *   get(assignmentId)
 *   begin_dispatch(occurrenceId, {version,generation,host_connection_identity})
 *   observe(occurrenceId, {...identity,kind:'session',reference,session_id})
 *   observe_host(occurrenceId, {...identity,...structured public receipt})
 *   record_runtime(occurrenceId, {...phase,instance_id,authority_epoch,desktop_protocol})
 *   record_scope(occurrenceId, {...phase,runtime_reference,enabled_toolsets,
 *                              visible_tools,tools,total,resumed_session_id})
 *   prepare_submit(occurrenceId, {...phase,scope_digest,replay})
 * phase adds route, profile_id and session_id (null before create) to identity.
 *   request_cancel/cancel_undispatched(occurrenceId, {version,generation})
 *   mark(occurrenceId, {version,generation,state,reason})
 * identity includes version, generation, session_request_id, submission_id and
 * host_connection_identity. Runtime/scope observations are client_observed, never
 * server-certified. record_scope must atomically freeze the exact scope and return
 * occurrence.scope_digest; prepare_submit must validate that digest, source-task
 * version, cancellation, runtime evidence and CAS before persisting submit_started.
 * Missing methods fail closed. No current UI/API adapter is implied by these types.
 *
 * Required capture: {route,workspace,profile,host_connection_identity,
 * host_profile_identity,desktop_protocol}. Authority profile must come from an
 * independently captured runtime.describe on that exact registered route, NEVER
 * its display name. getGeneration must advance synchronously on route/connection
 * activation, disconnect/reconnect, disposal and ABA transitions. isCurrent must
 * check the captured route against the active route. A fresh bridge is required
 * after invalidation. Every async boundary checks both; cancellation is separate.
 *
 * Deliberate recovery limit: if submit may have reached the host but its admission
 * identity was not persisted, cancellation keeps the durable cancel_requested flag
 * and stops with cancellation_requires_reconciliation. It does not replay task
 * text after cancellation, infer nonadmission from an empty pending list, or match
 * admissions by task text/title. A separate identity-safe host lookup/reconciler is
 * needed to resolve that case. Closing the UI does not run any dispatcher here.
 */

export const APPROVED_READ_TOOLS = Object.freeze([
  "crm_contact_get", "crm_contact_list", "crm_contact_report", "crm_deal_get",
  "crm_deal_list", "crm_overview", "crm_task_get", "crm_task_list",
]);
const DISCOVERY_TOOLS = Object.freeze(["tool_call", "tool_describe", "tool_search"]);
const PROTOCOL = "hermes-gateway-v1";
const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const METHODS = ["get", "begin_dispatch", "observe", "observe_host", "record_runtime",
  "record_scope", "prepare_submit", "request_cancel", "cancel_undispatched", "mark"];
const text = (x, max = 160) => typeof x === "string" && x.trim().length > 0 && x.length <= max;
const object = (x) => x !== null && typeof x === "object" && !Array.isArray(x);
const integer = (x, minimum = 0) => Number.isSafeInteger(x) && x >= minimum;
const flag = (x) => x === true || x === 1;
const booleanFlag = (x) => typeof x === "boolean" || x === 0 || x === 1;
const clone = (x) => JSON.parse(JSON.stringify(x));
const canonical = (x) => JSON.stringify(x, (_key, value) => object(value)
  ? Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]])) : value);
const equal = (a, b) => canonical(a) === canonical(b);

export class ExecutionBridgeError extends Error {
  constructor(code) {
    // Do not echo host errors, response bodies, task text or credentials.
    super(`Execution bridge stopped: ${code}.`);
    this.name = "ExecutionBridgeError";
    this.code = code;
  }
}
const stop = (code) => { throw new ExecutionBridgeError(code); };
const requireThat = (condition, code) => { if (!condition) stop(code); };

export function normalizeRoute(route) {
  requireThat(object(route) && ["connectionId", "profile", "targetProfile"].every(
    (key) => text(route[key])) && ["local", "remote"].includes(route.mode), "route_schema_unknown");
  return Object.freeze(Object.fromEntries(
    ["connectionId", "profile", "targetProfile", "mode"].map((key) => [key, route[key]])));
}

function names(values, code) {
  requireThat(Array.isArray(values) && values.length > 0 && values.every((x) => text(x)) &&
    new Set(values).size === values.length, code);
  return [...values].sort();
}

/** Require the entire reviewed catalog, including deferred tools' hidden surface. */
export function inspectReadScope(snapshot, catalog) {
  const info = snapshot?.info;
  requireThat(object(info) && equal(info.enabled_toolsets, ["crm_read"]), "scope_toolsets_rejected");
  requireThat(object(info.tools) && Object.keys(info.tools).length > 0 &&
    Object.values(info.tools).every(Array.isArray), "scope_visible_schema_unknown");
  const visible = names(Object.values(info.tools).flat(), "scope_visible_schema_unknown");
  requireThat(visible.every((x) => APPROVED_READ_TOOLS.includes(x) || DISCOVERY_TOOLS.includes(x)),
    "scope_visible_tool_rejected");
  if (visible.some((x) => DISCOVERY_TOOLS.includes(x)))
    requireThat(DISCOVERY_TOOLS.every((x) => visible.includes(x)), "scope_discovery_schema_unknown");
  requireThat(object(catalog) && Object.keys(catalog).every((k) => ["sections", "total"].includes(k)) &&
    Array.isArray(catalog.sections) && catalog.sections.length > 0 && integer(catalog.total, 1),
    "scope_inventory_schema_unknown");
  const flattened = [];
  for (const section of catalog.sections) {
    requireThat(object(section) && Object.keys(section).every((k) => ["name", "tools"].includes(k)) &&
      section.name === "crm_read" && Array.isArray(section.tools) && section.tools.length > 0,
      "scope_inventory_schema_unknown");
    for (const tool of section.tools) {
      requireThat(object(tool) && Object.keys(tool).every((k) => ["name", "description"].includes(k)) &&
        text(tool.name) && typeof tool.description === "string", "scope_inventory_schema_unknown");
      flattened.push(tool.name);
    }
  }
  const full = names(flattened, "scope_inventory_schema_unknown");
  requireThat(catalog.total === full.length, "scope_inventory_count_mismatch");
  requireThat(equal(full, APPROVED_READ_TOOLS), "scope_inventory_rejected");
  return {enabled_toolsets: ["crm_read"], visible_tools: visible, tools: full};
}

function validateSnapshot(snapshot, capture, expectedSession, fresh = false) {
  requireThat(object(snapshot) && text(snapshot.session_id) && text(snapshot.stored_session_id) &&
    integer(snapshot.authority_epoch) && integer(snapshot.revision) &&
    integer(snapshot.execution_generation) && integer(snapshot.last_sequence) &&
    text(snapshot.replay_epoch) && text(snapshot.subscription_id) &&
    Array.isArray(snapshot.pending) && Array.isArray(snapshot.prompts) &&
    Array.isArray(snapshot.messages) && integer(snapshot.message_count) &&
    typeof snapshot.running === "boolean" && object(snapshot.info), "host_snapshot_schema_unknown");
  requireThat(snapshot.info.desktop_protocol === PROTOCOL, "canonical_protocol_required");
  requireThat(snapshot.info.profile_id === capture.host_profile_identity, "host_profile_mismatch");
  requireThat(!expectedSession || snapshot.session_id === expectedSession, "host_session_mismatch");
  if (fresh) requireThat(!snapshot.running && snapshot.message_count === 0 &&
    snapshot.messages.length === 0 && snapshot.pending.length === 0 && snapshot.prompts.length === 0,
    "fresh_session_required");
}

/** Content-free redaction by default. Do not send transcripts, usage or raw errors to the store. */
export function redactHostResult(result) {
  if (result === undefined || result === null) return null;
  requireThat(object(result), "host_result_schema_unknown");
  const allowedMetadata = new Set(["final_response", "failed", "error", "interrupted", "completed",
    "messages", "tool_calls", "api_calls", "tools_used", "iterations", "exit_reason", "failure_reason",
    "failure_code", "retryable", "error_surface", "failure", "usage",
    // Pinned host agent/turn_finalizer.py and hermes_state_terminal.py metadata.
    // These keys are recognized only to discard them, not to forward their data.
    "last_reasoning", "turn_exit_reason", "partial", "response_transformed", "pre_transform_response",
    "response_previewed", "response_reused", "model", "requested_model", "served_model", "provider",
    "base_url", "input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens",
    "reasoning_tokens", "prompt_tokens", "completion_tokens", "total_tokens", "last_prompt_tokens",
    "estimated_cost_usd", "cost_status", "cost_source", "service_tier", "session_id", "guardrail",
    "failure_retryable", "cleanup_errors", "pending_steer", "interrupt_message", "_compressed",
    "_messages_are_turn_suffix", "_turn_user_row", "current_turn_user_idx", "agent_persisted",
    "codex_thread_id", "codex_turn_id", "usage_window_message", "failure_resets_at", "usage_limit",
    "billing_unverified", "billing_block", "compression_deferred", "compression_exhausted"]);
  // Unknown result schemas cannot become apparent success through dropped flags.
  requireThat(Object.keys(result).every((key) => allowedMetadata.has(key)), "host_result_schema_unknown");
  const safe = {};
  if (Object.hasOwn(result, "final_response")) {
    requireThat(typeof result.final_response === "string", "host_result_schema_unknown");
    safe.final_response = result.final_response.trim() ? "[nonempty response omitted]" : "";
  }
  for (const key of ["failed", "interrupted", "completed"]) {
    if (Object.hasOwn(result, key)) {
      requireThat(typeof result[key] === "boolean", "host_result_schema_unknown");
      safe[key] = result[key];
    }
  }
  if (Object.hasOwn(result, "error")) {
    requireThat(result.error === null || typeof result.error === "boolean" ||
      typeof result.error === "string", "host_result_schema_unknown");
    safe.error = typeof result.error === "string" ? !!result.error.trim() : !!result.error;
  }
  // Failure metadata is not silently dropped. Its schema needs an upstream
  // normalizer; conservative error=true prevents a contradictory success.
  if (Object.hasOwn(result, "partial"))
    requireThat(typeof result.partial === "boolean", "host_result_schema_unknown");
  const benignExit = (value) => value === null || value === undefined ||
    ["completed", "complete", "stop", "success"].includes(value) ||
    (typeof value === "string" && /^text_response\(finish_reason=(stop|end_turn)\)$/.test(value));
  if (["failure", "failure_reason", "failure_code", "guardrail", "cleanup_errors",
      "compression_deferred", "compression_exhausted", "partial", "billing_block", "billing_unverified",
      "usage_limit", "usage_window_message", "failure_resets_at", "error_surface"].some((key) => !!result[key]) ||
      !benignExit(result.exit_reason) || !benignExit(result.turn_exit_reason)) safe.error = true;
  return safe;
}

function receiptObservation(receipt, capture, row, source) {
  requireThat(object(receipt) && text(receipt.admission_id) && object(receipt.ref) &&
    integer(receipt.sequence, 1) && integer(receipt.authority_epoch) &&
    (receipt.execution_generation === null || integer(receipt.execution_generation)) &&
    ["queued", "started", "unknown", "terminal"].includes(receipt.status) &&
    (receipt.outcome === null || text(receipt.outcome, 80)), "host_receipt_schema_unknown");
  requireThat(receipt.ref.profile_id === capture.host_profile_identity, "host_profile_mismatch");
  requireThat(receipt.ref.session_id === row.session_id, "host_session_mismatch");
  requireThat(!row.admission_id || row.admission_id === receipt.admission_id, "host_admission_mismatch");
  return {session_id: row.session_id, admission_id: receipt.admission_id,
    profile_id: receipt.ref.profile_id, source, status: receipt.status, outcome: receipt.outcome,
    sequence: receipt.sequence, authority_epoch: receipt.authority_epoch,
    execution_generation: receipt.execution_generation, redacted_result: redactHostResult(receipt.result),
    redacted_summary: ""};
}

export function createExecutionBridge({requestProfile, profileRoutes, store, capture,
  isCurrent, getGeneration, isCancelled = () => false, experimentalDispatch = false} = {}) {
  requireThat(typeof requestProfile === "function" && typeof profileRoutes === "function" &&
    typeof isCurrent === "function" && typeof getGeneration === "function" &&
    typeof isCancelled === "function", "public_adapter_required");
  requireThat(object(store) && METHODS.every((key) => typeof store[key] === "function"),
    "durable_adapter_capabilities_missing");
  requireThat(object(capture) && ["workspace", "profile", "host_connection_identity",
    "host_profile_identity"].every((key) => text(capture[key])), "captured_identity_required");
  const bound = Object.freeze({...clone(capture), route: normalizeRoute(capture.route)});
  requireThat(bound.desktop_protocol === PROTOCOL, "canonical_protocol_required");
  requireThat(bound.profile === bound.route.profile, "route_profile_mismatch");
  const generation = getGeneration();
  requireThat(typeof generation === "string" || integer(generation), "route_generation_required");
  const locks = new Set(), cancelLocks = new Set(), cancelled = new Set();
  const current = () => isCurrent() === true && Object.is(getGeneration(), generation);
  const check = (id, allowCancel = false) => {
    requireThat(current(), "stale_route");
    if (!allowCancel) requireThat(!cancelled.has(id) && !isCancelled(id), "cancellation_requested");
  };
  const wait = async (id, fn, allowCancel = false, errorCode = "store_request_uncertain") => {
    check(id, allowCancel);
    let value;
    try { value = await fn(); }
    catch (error) {
      check(id, allowCancel);
      if (error instanceof ExecutionBridgeError) throw error;
      stop(errorCode);
    }
    check(id, allowCancel);
    return value;
  };
  const rpc = (ctx, method, params, allowCancel = false) => wait(ctx.id,
    () => requestProfile(bound.route, method, params), allowCancel, "host_request_uncertain");
  const identity = (ctx) => ({version: ctx.row.version, generation: ctx.row.generation,
    session_request_id: ctx.row.session_request_id, submission_id: ctx.row.submission_id,
    host_connection_identity: bound.host_connection_identity});
  const phase = (ctx) => ({...identity(ctx), route: bound.route,
    profile_id: bound.host_profile_identity, session_id: ctx.row.session_id || null});

  function adopt(ctx, assignment) {
    requireThat(object(assignment) && assignment.id === ctx.assignmentId &&
      assignment.workspace === bound.workspace && assignment.profile === bound.profile &&
      object(assignment.payload) && typeof assignment.digest === "string" && /^[a-f0-9]{64}$/.test(assignment.digest) &&
      Array.isArray(assignment.occurrences), "store_assignment_mismatch");
    const payload = assignment.payload;
    requireThat(payload.workspace === bound.workspace && payload.profile === bound.profile &&
      payload.host_connection_identity === bound.host_connection_identity &&
      payload.host_profile_identity === bound.host_profile_identity &&
      equal(normalizeRoute(payload.host_route), bound.route), "store_identity_mismatch");
    requireThat(payload.run_at === null && payload.action === "internal" &&
      payload.authorization_scope === "internal_crm_only", "immediate_internal_intent_required");
    requireThat(text(payload.prompt, 50000) && integer(payload.task_version, 1) && payload.task_status === "open" &&
      Array.isArray(payload.required_tools) && payload.required_tools.includes("crm_task_get") &&
      payload.required_tools.every((name) => APPROVED_READ_TOOLS.includes(name)), "immutable_prompt_required");
    const rows = assignment.occurrences.filter((r) => r.id === ctx.id);
    requireThat(rows.length === 1, "store_occurrence_mismatch");
    const row = rows[0];
    requireThat(integer(row.version, 1) && integer(row.generation, 1) &&
      row.generation === assignment.generation && text(row.session_request_id) && text(row.submission_id) &&
      ["pending", "blocked", "unknown", "admitted", "running", ...TERMINAL].includes(row.state) &&
      [row.dispatch_started, row.cancel_requested, row.submit_started].every(booleanFlag) &&
      (row.session_id === null || text(row.session_id)) && (row.admission_id === null || text(row.admission_id)),
      "store_generation_mismatch");
    const immutable = canonical({id: assignment.id, digest: assignment.digest, payload,
      occurrence: row.id, generation: row.generation, session_request_id: row.session_request_id,
      submission_id: row.submission_id});
    requireThat(!ctx.immutable || ctx.immutable === immutable, "immutable_intent_changed");
    requireThat(!ctx.row?.session_id || row.session_id === ctx.row.session_id, "store_session_changed");
    requireThat(!ctx.row?.admission_id || row.admission_id === ctx.row.admission_id, "store_admission_changed");
    requireThat(!ctx.row || row.version >= ctx.row.version, "store_version_regressed");
    ctx.immutable = immutable;
    ctx.assignment = clone(assignment);
    ctx.row = ctx.assignment.occurrences.find((r) => r.id === ctx.id);
    return ctx;
  }
  const mutate = async (ctx, method, params, allowCancel = false) => {
    const result = await wait(ctx.id, () => store[method](ctx.id, params), allowCancel);
    adopt(ctx, result);
    return result;
  };
  const load = async (input, allowCancel = false) => {
    requireThat(object(input) && text(input.assignment_id) && text(input.occurrence_id), "intent_identity_required");
    const ctx = {id: input.occurrence_id, assignmentId: input.assignment_id};
    return adopt(ctx, await wait(ctx.id, () => store.get(ctx.assignmentId), allowCancel));
  };
  async function runtime(ctx, allowCancel = false) {
    const routes = await wait(ctx.id, profileRoutes, allowCancel, "route_inventory_unavailable");
    requireThat(Array.isArray(routes), "route_inventory_schema_unknown");
    const same = routes.map(normalizeRoute).filter((r) => r.connectionId === bound.route.connectionId &&
      r.profile === bound.route.profile);
    requireThat(same.length === 1 && equal(same[0], bound.route), "route_mapping_changed");
    const value = await rpc(ctx, "runtime.describe", {}, allowCancel);
    requireThat(object(value) && text(value.profile_id) && text(value.instance_id) &&
      integer(value.authority_epoch) && Array.isArray(value.capabilities) &&
      value.capabilities.every((x) => text(x)) && value.capabilities.includes("durable-admission-v1") &&
      object(value.session_create) && Array.isArray(value.session_create.sources) &&
      value.session_create.sources.includes("gui") && Array.isArray(value.session_create.parameters) &&
      ["request_id", "source", "toolsets"].every((x) => value.session_create.parameters.includes(x)),
      "canonical_runtime_required");
    requireThat(value.profile_id === bound.host_profile_identity, "host_profile_mismatch");
    await mutate(ctx, "record_runtime", {...phase(ctx),
      instance_id: value.instance_id, authority_epoch: value.authority_epoch,
      desktop_protocol: PROTOCOL}, allowCancel);
  }
  async function session(ctx, create, allowCancel = false) {
    const value = create
      ? await rpc(ctx, "session.create", {request_id: ctx.row.session_request_id,
        source: "gui", toolsets: ["crm_read", "no_mcp"]}, allowCancel)
      : await rpc(ctx, "session.resume", {session_id: ctx.row.session_id}, allowCancel);
    validateSnapshot(value, bound, ctx.row.session_id, create);
    requireThat(value.authority_epoch === ctx.row.runtime?.authority_epoch, "runtime_snapshot_epoch_mismatch");
    if (create) {
      await mutate(ctx, "observe", {...identity(ctx), kind: "session", reference: value.session_id,
        session_id: value.session_id, provenance: "client_observed", redacted_summary: ""}, allowCancel);
      requireThat(ctx.row.session_id === value.session_id, "session_receipt_not_persisted");
    }
    ctx.resumedSession = create ? null : value.session_id;
    return value;
  }
  async function scope(ctx, snapshot) {
    // Reject widened/unknown visible scope before even querying the full catalog.
    requireThat(equal(snapshot.info.enabled_toolsets, ["crm_read"]), "scope_toolsets_rejected");
    const inventory = await rpc(ctx, "tools.show", {session_id: ctx.row.session_id});
    const evidence = inspectReadScope(snapshot, inventory);
    requireThat(text(ctx.row.runtime?.reference), "runtime_receipt_not_persisted");
    await mutate(ctx, "record_scope", {...phase(ctx), runtime_reference: ctx.row.runtime.reference,
      ...evidence, total: evidence.tools.length, resumed_session_id: ctx.resumedSession});
    requireThat(typeof ctx.row.scope_digest === "string" && /^[a-f0-9]{64}$/.test(ctx.row.scope_digest),
      "scope_receipt_not_persisted");
  }
  async function observe(ctx, value, source, allowCancel = false) {
    const normalized = receiptObservation(value, bound, ctx.row, source);
    await mutate(ctx, "observe_host", {...identity(ctx), ...normalized}, allowCancel);
    requireThat(ctx.row.admission_id === normalized.admission_id, "admission_receipt_not_persisted");
    return clone(ctx.assignment);
  }
  async function submit(ctx) {
    requireThat(experimentalDispatch === true, "experimental_dispatch_disabled");
    requireThat(!flag(ctx.row.cancel_requested), "cancellation_requested");
    const digest = ctx.row.scope_digest;
    await mutate(ctx, "prepare_submit", {...phase(ctx), scope_digest: digest, replay: flag(ctx.row.submit_started)});
    requireThat(flag(ctx.row.submit_started) && ctx.row.scope_digest === digest &&
      !flag(ctx.row.cancel_requested), "submit_preflight_not_persisted");
    // No awaits between final route/cancel guard and sending the immutable text.
    const receipt = await rpc(ctx, "prompt.submit", {session_id: ctx.row.session_id,
      submission_id: ctx.row.submission_id, text: ctx.assignment.payload.prompt, finite: true});
    return observe(ctx, receipt, "prompt.submit");
  }
  async function run(input, operation, allowCancel = false) {
    requireThat(text(input?.occurrence_id), "intent_identity_required");
    requireThat(!locks.has(input.occurrence_id), "operation_in_progress");
    locks.add(input.occurrence_id);
    let ctx;
    try {
      ctx = await load(input, allowCancel);
      return await operation(ctx);
    } catch (error) {
      // Lost transport/storage calls stay uncertain. Never infer nonadmission or
      // launch a new attempt. Stale route/CAS cannot safely write anything else.
      if (ctx && current() && error instanceof ExecutionBridgeError &&
          error.code.startsWith("scope_") && !TERMINAL.has(ctx.row.state)) {
        try {
          await mutate(ctx, "mark", {version: ctx.row.version, generation: ctx.row.generation,
            state: flag(ctx.row.submit_started) ? "unknown" : "blocked", reason: error.code});
        } catch { /* Existing durable uncertainty wins; no retry of failed writes. */ }
      }
      throw error;
    } finally { locks.delete(input.occurrence_id); }
  }
  return Object.freeze({
    /** New intent only. Stable IDs must already exist in durable storage. */
    start(input) {
      if (experimentalDispatch !== true) return Promise.reject(new ExecutionBridgeError("experimental_dispatch_disabled"));
      return run(input, async (ctx) => {
        requireThat(ctx.row.state === "pending" && !flag(ctx.row.dispatch_started) &&
          !flag(ctx.row.cancel_requested), "new_pending_intent_required");
        await mutate(ctx, "begin_dispatch", {version: ctx.row.version, generation: ctx.row.generation,
          host_connection_identity: bound.host_connection_identity});
        requireThat(flag(ctx.row.dispatch_started) && ctx.row.state === "unknown", "dispatch_intent_not_persisted");
        await runtime(ctx);
        const snapshot = await session(ctx, true);
        await scope(ctx, snapshot);
        return submit(ctx);
      });
    },
    /** Read/reconcile by durable IDs. Replay is explicit, same IDs, never a retry generation. */
    resume(input, {replay = false} = {}) {
      if (replay && experimentalDispatch !== true)
        return Promise.reject(new ExecutionBridgeError("experimental_dispatch_disabled"));
      return run(input, async (ctx) => {
        if (TERMINAL.has(ctx.row.state)) return clone(ctx.assignment);
        requireThat(flag(ctx.row.dispatch_started), "dispatch_not_started");
        await runtime(ctx, !replay);
        requireThat(ctx.row.session_id || replay, "session_identity_requires_replay");
        const snapshot = await session(ctx, !ctx.row.session_id, !replay);
        if (ctx.row.admission_id) {
          const receipt = await rpc(ctx, "prompt.receipt", {session_id: ctx.row.session_id,
            admission_id: ctx.row.admission_id, include_result: true}, !replay);
          return observe(ctx, receipt, "prompt.receipt", !replay);
        }
        if (!replay) return clone(ctx.assignment);
        requireThat(!flag(ctx.row.cancel_requested), "cancellation_requires_reconciliation");
        await scope(ctx, snapshot);
        return submit(ctx);
      }, !replay);
    },
    /** Cancellation intent persists first. A running cancellation can remain running. */
    async cancel(input) {
      requireThat(text(input?.occurrence_id), "intent_identity_required");
      const id = input.occurrence_id;
      cancelled.add(id); // Immediately interrupts an in-flight local start after its await.
      requireThat(!cancelLocks.has(id), "cancellation_in_progress");
      cancelLocks.add(id);
      try {
        const ctx = await load(input, true);
        if (TERMINAL.has(ctx.row.state)) return clone(ctx.assignment);
        if (!flag(ctx.row.cancel_requested)) await mutate(ctx, "request_cancel",
          {version: ctx.row.version, generation: ctx.row.generation}, true);
        requireThat(flag(ctx.row.cancel_requested), "cancel_intent_not_persisted");
        if (!flag(ctx.row.dispatch_started)) return await mutate(ctx, "cancel_undispatched",
          {version: ctx.row.version, generation: ctx.row.generation}, true);
        requireThat(ctx.row.session_id && ctx.row.admission_id, "cancellation_requires_reconciliation");
        await runtime(ctx, true);
        await session(ctx, false, true);
        const receipt = await rpc(ctx, "prompt.cancel", {session_id: ctx.row.session_id,
          admission_id: ctx.row.admission_id}, true);
        return await observe(ctx, receipt, "prompt.cancel", true);
      } finally { cancelLocks.delete(id); }
    },
  });
}
