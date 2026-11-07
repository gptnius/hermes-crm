# Experimental execution foundation

This is development infrastructure, not an enabled product feature. The native pane and registered CRM tools do not import it. There are no execution REST routes, timers, background workers or live model calls. The JavaScript bridge disables new submission and replay by default. Scheduled assignment intents remain blocked.

## What the isolated code does

`hermes_crm/execution.py` stores immutable internal-work intent, a separate human owner, the existing task's version, stable session/submission IDs and an exact workspace/profile/connection association. Optional captured route and authority identity come from the authenticated public SDK transport; they are caller-observed, not an independent installation certificate.

Each occurrence keeps a versioned state and append-only observations. Dispatch and submission uncertainty are persisted before external calls. Source-task changes, cancellation, stale versions, changed routes and expired scope observations prevent submission. Retry cannot replace IDs after an unknown outcome. Replaying the same submission requires newly observed resume/scope evidence. Successful observed agent output remains awaiting human review and never completes the business task automatically.

Host receipts retain allowlisted status, outcome, epoch, execution generation and sequence separately from CRM versions. Initial terminal or unknown receipts can bind an admission without inventing an earlier queued state. Runtime chronology and admission-owner chronology are separate. A historical admission may retain its original owner epoch after the current runtime restarts. Its insertion sequence is immutable, not an event counter. Stale observations within that admission and contradictory terminal outcomes cannot overwrite newer state. Raw transcripts, provider credentials and arbitrary host response objects are not accepted as stored evidence. Client-derived observation hashes are not host-issued result IDs.

`desktop/execution-bridge.js` is an unwired, dependency-injected adapter for the public immediate-session protocol:

1. Capture a registered route and its authority identity through `runtime.describe`.
2. Persist intent, then use `session.create` with the existing stable request ID. Omit title because the host can reuse an existing titled session.
3. Verify the exact effective toolsets and full `tools.show` inventory, including the catalog behind deferred-discovery wrappers.
4. Persist a guarded submit phase, then call `prompt.submit` with the same frozen text and submission ID.
5. Observe `prompt.receipt`, or reconnect through `session.resume`. Cancellation intent and terminal cancellation evidence are separate.

The approved inventory is the eight current CRM read tools. Unexpected tools, unknown schemas, widened toolsets, mismatched identities or stale activation generations fail closed. No configuration, authentication, model, provider or permission setting is changed to make a check pass. The experimental bridge does not request unattended mode or external outreach.

## Verification boundary

Storage contracts run on temporary SQLite and an explicitly selected disposable PostgreSQL database. They cover persistence, concurrent changes, rollback, idempotent intent recovery, task and scope races, receipt binding, authority ordering, cancellation and unknown outcomes. PostgreSQL fixtures remove only their own random test schemas.

The JavaScript suite tests synthetic transport and includes an opt-in adapter check against the real SQLite `ExecutionStore`. It exercises stable IDs, failure/cancellation boundaries, stale routes, scope widening and lost-response recovery. It is not a native-window, authenticated WebSocket, restart or real-model execution test.

Separate source-contract research against official Hermes commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` exercised real plugin discovery, runtime identity, canonical admission, stable-ID replay, resume, queued cancellation and default deferred-tool scope resolution. The authority's turn drain was deliberately disabled; no agent turn or provider call executed. A fixture-only policy produced a clean read scope, while a fresh default profile reproduced widening to `crm_write`. No user configuration was changed.

The final isolated checks on November 6, 2026 passed: 97 SQLite execution cases; 99 actual PostgreSQL 17.11 cases (the shared 97 plus two race/rollback checks); 25 JavaScript cases including the real SQLite adapter with no skips; and one opt-in actual-host sequence/owner-epoch semantics test. Existing CRM tests also remain passing. Independent storage and bridge reviews found no remaining blockers within this disabled foundation. These counts do not turn synthetic transport into live agent execution.

## Remaining gates

- No UI, REST or registered-tool adapter connects this foundation to user actions yet.
- Requested toolsets can widen through host defaults. Full inventory inspection detects this before sending task text, but is a snapshot, not an atomic tool-name ceiling. A host-enforced strict ceiling and admission-bound scope hash are needed for the stronger confinement guarantee.
- Captured gateway RPC routes do not pin `ctx.rest` to the same workspace. A future adapter must retain workspace-token/CAS checks and synchronous connection/profile invalidation.
- A lost first submission response may leave cancellation requested with no known admission ID. This is an unresolved outcome, not confirmed cancellation; do not send a replacement task to discover the ID.
- The `cron.manage` RPC lacks restricted creation fields and the full lifecycle. The separate Desktop/dashboard cron REST API supports paused creation and toolsets, but has no reviewed adapter to the CRM intent/approval contract here. Neither is used as a direct scheduling shortcut. The existing explicit reminder and active-tool assigned-work paths remain separate from this disabled immediate bridge.
- Real-model behavior, owner-process restart recovery, human-visible results, closed-pane dispatch and operational monitoring remain unverified. Saved intent alone is not scheduled or executable coverage.

## Reproduce the isolated tests

From an environment with this project's test dependencies:

```sh
python -m pytest tests/test_execution.py -q
CRM_EXECUTION_TEST_PYTHON=/path/to/test/python node tests/execution_bridge.mjs
```

The optional bridge-to-store check is skipped when its interpreter is not explicitly supplied. A passing JavaScript-only run is not a passing real-store adapter check.

The host semantics test additionally requires the pinned source and its test dependencies:

```sh
HERMES_SOURCE=/path/to/hermes-agent python -m pytest tests/test_execution_host.py -q
```

It uses test-only inspection of the real runtime store and serializer with a fresh home and blocked networking. It is not a production dependency on private host APIs or a full restart test.

For PostgreSQL, use only a disposable test database:

```sh
HERMES_CRM_TEST_POSTGRES_URL='postgresql+psycopg://...' python -m pytest tests/test_execution_postgres.py -q
```

No live task execution is authorized or enabled by these commands.
