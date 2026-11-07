# Verification report

Updated November 7, 2026. Historical native and scheduler runs below retain their original scope. This is a tested prototype, not a production release. Native Mac workflows and real one-shot scheduler execution passed on the exact source builds below. The scheduler test used deterministic loopback model responses, not a real model. Real-model behavior, visible reminder presentation, restart recovery, broader accessibility/responsive coverage and hosted-service validation remain incomplete.

## Optional layered protection and agent data minimization

This increment adds separate opt-in protected notes and encrypted CRM content
exports, while reducing ordinary base-tool responses and adding exact
ordinary-field selection. It does not configure any real keys or secret source,
move/delete existing notes, modify the active review app, expand scheduled
allowlists, or claim general record authorization. Existing ordinary data and
copies remain plaintext. See [protection threat and recovery boundaries](PROTECTION.md).

Verification on November 7, 2026:

- A clean 145-file shipping-source export passed **1,111 Python tests**, with
  **525 optional cases skipped** and two dependency deprecation warnings.
  Dormant direct-chat experiments are not part of this source or count.
- Twenty-nine focused synthetic protection tests cover authenticated encryption,
  retained-key replay, altered envelopes and cross-record/workspace/profile
  rejection, absence of protected plaintext in known table rows/database bytes,
  metadata-only receipts, rollback, exact supported schema validation and
  sanitized native request/error responses. Fifteen additional PostgreSQL
  contracts passed on the separate disposable target below; the cloud suite
  skips them without a configured disposable database.
- Failure regressions cover a committed save followed by a 503, reservation
  interruption, missing/deleted artifacts, post-file database rollback, same-ID
  concurrent export capture, unsafe file permissions and FIFO rejection.
  Encrypted artifacts decode to the original synthetic table snapshot, without
  keys or plaintext temporary files. This is authenticated offline decoding,
  **not a live restore or disaster-recovery drill**.
- A separate disposable macOS PostgreSQL **17.11 ARM64** run passed **597
  synthetic checks, zero failures and zero skips**, against the shipping source
  plus a reviewed test-only SQL-hook correction. The focused 87 comprise 29
  SQLite protection cases, 15 PostgreSQL protection cases, 22 projection cases
  and 21 adapter cases. The other 510 existing regression cases include fifteen
  SQLite report variants and one SQL-compilation case; not all 597 cases are
  PostgreSQL-backed. The correction makes the rollback fault injection identify
  the compiled insert table instead of matching a SQLite-only SQL prefix; no
  runtime fix was needed. Cryptography 50.0.2, psycopg 3.3.8 and SQLAlchemy 2.1.8
  were used. All four owned disposable containers were removed; no existing
  volumes, real keys/accounts, providers or active app/profile were changed.
- Three tests against exact official Hermes source
  `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` passed: both registration/isolation
  modes and actual scheduled-tool resolution. Forty-two tools are registered;
  `crm_record_fields` uses `crm_detail_read`, outside fixed scheduled allowlists.
  These checks use no live model, account or real scheduling.
- Thirteen native SDK/component suites passed, including actual React 19.3,
  protected-note explicit reveal, plaintext cleanup at save dispatch and view
  invalidation, lost-response receipt recovery, 5xx unknown locks, close/reopen
  during pending operations and preservation of the original file-download
  binding. Independent protection React recheck also passed under StrictMode.
  The execution bridge passed all 25 tests with the real SQLite store adapter;
  standalone VM/syntax and all four generated-panel checks passed. The cloud
  environment lacked the optional real nanostores fixture.
- Independent security and native UI reviews passed after fixes for malformed
  storage refusal, native HTTP status preservation, post-commit uncertainty,
  durable export reservations, unsafe special files and remounted recovery
  controls. Cryptography 50.0.0 supplied encryption in the cloud test environment.

Real key provisioning/external secret-source integration was not exercised.
The tested host's masked configuration can use plaintext `.env`; neither masking
nor a copied home directory is a verified key-custody boundary. Profile rename,
rekeying and supported restore/rebinding remain unimplemented. Physical native
Save-dialog/focus/Escape testing, wider accessibility and full recovery drills
remain pending. No private profile, provider, mailbox or production datastore
was used by these checks.

## Custom fields and deal stages

The customization increment adds versioned optional typed fields, configurable
single-pipeline deal stages and a shared catalog for native forms, agent tools
and reports. Stable keys/types/outcomes and existing record columns are
preserved. Stage retirement rejects current dependencies; archived field values
remain readable. No active user app, provider configuration, real records or
credentials were changed by this development and verification.

Verification on November 7, 2026:

- A clean shipping-source export passed **1,039 Python tests**, with **510
  optional cases skipped** and two dependency deprecation warnings. Dormant
  direct-chat experiments are excluded from this source and count.
- A separate disposable macOS PostgreSQL **17.11 ARM64** run passed **510 tests,
  zero failures and zero skips** against the exact source plus its reviewed
  portability delta. This suite includes fifteen SQLite report variants and one
  SQL-compilation case; it is not a claim that all 510 cases used PostgreSQL.
  Coverage includes customization, reports, report storage, core records,
  assignments/operations, coverage and synthetic Gmail storage. It covers legacy
  rows and exact idempotency receipts surviving concurrent first upgrade,
  incompatible/newer schema refusal, read snapshots and long-key SQL aliases.
  Only known dependency warnings and an intentional malformed-primary-key
  fixture warning occurred. All four owned disposable containers were removed;
  no existing volumes, apps, profiles, providers or mailboxes were used.
- Actual pinned Hermes source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`
  passed two new guarded registration/dispatch cases, one in-process and one
  hosted-child. Forty-one tools are registered; the five schema tools use
  dedicated toolsets, and existing scheduled capabilities are unchanged. The
  fixtures prohibit network/model/agent execution and allow only the exact
  read-only source-version query additionally required by the pinned host.
- Eleven native SDK/component suites passed, including actual React 19.3,
  configuration lifecycle, typed values, renamed stage labels and default
  probabilities, stale workspace dismissal, known-save refresh failures and
  frozen unknown outcomes. Standalone VM smoke, syntax and all three generated
  panel checks passed. One optional real nanostores fixture was unavailable.
- Independent backend/report and UI reviews passed after fixes for bounded audit
  identifiers, declared schema lengths, coherent native snapshots, PostgreSQL
  identifier length, default probabilities, label collisions and recovery flows.

The cloud test runtime could not open a private PostgreSQL socket; the separate
authorized disposable Mac database supplied the live portability evidence. No
cloud database server remains running. Hosted Supabase, shared-database tenant
authorization and production migration are not verified by these tests.

**Physical native/browser inspection of the new customization controls is still
pending.** React/VM tests are not a visual or full accessibility pass. The user's
open review app remained on its prior published revision throughout this work.
See [customization behavior and limits](CUSTOMIZATION.md) and the
[README roadmap](../README.md#development-roadmap).

## Flexible reports, saved dashboard and contact log

The next isolated source increment adds typed contacts/deals/tasks reports,
shared saved definitions, pinned main-dashboard cards and explicit self-reported
contact events. It changes no Gmail, scheduler, production or existing user
profile configuration. New report/log capabilities use separate toolsets; the
legacy eight CRM read tools and eleven scheduled-assignment read/report tools
remain unchanged. The total registered plugin inventory is now thirty-six.

Verification on November 7, 2026:

- Default shipping-scope Python: **992 passed, 475 opt-in tests skipped**, with
  two dependency deprecation warnings. This includes 86 new REST/tool adapter
  cases; dormant direct-chat experiments are excluded from the release tree.
- Actual disposable PostgreSQL 17.11: **38 new report/storage contracts passed**.
  This covers SQL aggregation, null typing, fractional numeric measures, maximum
  date buckets, snapshot consistency, cross-process lazy initialization,
  same-key concurrent replay, profile scope and schema refusal. A deliberate
  malformed-key schema fixture produces one SQLAlchemy warning. The loopback-only
  disposable cluster was stopped after testing.
- Actual pinned Hermes source, CPython 3.14: **two guarded host cases passed**,
  one per plugin isolation mode. Registered tools and authenticated REST share
  saved reports, dashboards and authored logs; stale workspace/version requests,
  archived runs and secondary-profile leakage are rejected. No scheduler job,
  model/provider call, mailbox access or network server runs in these cases.
- Ten native SDK/component suites pass, including actual React 19.3 StrictMode,
  typed builder/preview/save, version adoption, archive/restore and saved-list
  paging, chart click/keyboard drilldowns, UTC date spacing and honest capped
  distributions. Contact-log tests cover cancelled/stale form handlers, exact
  timezone input, void provenance and known-rejection recovery. Both panels keep
  frozen unknown requests across new route clients within the plugin lifetime,
  isolated by connection and app profile even with copied workspace tokens.
  Standalone UI smoke, JS syntax and both generated-panel sync checks also pass.
- Independent backend and UI reviews passed after corrections to read snapshots,
  maximum-date drilldowns, stale form callbacks, reconnect recovery and sibling
  React keys. No unresolved findings from these reviews.

Each report response uses one consistent database read snapshot; subsequent
pages and drilldowns remain live and disclose that limitation. The report engine
never substitutes current stage for historical stage, expected close for actual
win time, generic activity for contact, or a stored follow-up for execution proof.

### Native reporting check on November 7, 2026

A separately authorized isolated Mac review app was updated to published CRM
`460c2b642b040cb4d4c5a3a0879f799e6833db22` (tree
`58a5815b773b302a03342b791a08e8928227798a`) on unchanged host source
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. A recoverable SQLite backup passed
integrity verification first. Existing sample data remained nine contacts,
$113,500 open pipeline and four open follow-ups; no existing records were edited.
An older separately running test gateway initially served the previous API.
Restarting that exact test gateway and app resolved the version mismatch.

Actual native interaction and light-mode screen inspection passed:

- Opening the builder, selecting columns and previewing the lead filter returned
  five matching records.
- Saving report version 1, adding it to the dashboard and running its table card.
- Saving a UTC-day report, adding/running its bar card and clicking through to
  the same five contributing lead records.
- The app remained working, with native chat beside the CRM workspace.

No layout defect was confirmed in the inspected builder/dashboard views. Testing
paused when the user resumed navigation. The two clearly named synthetic QA
reports/cards were retained; no existing records or other profiles were changed.

This is a **partial native visual and functional check**, not a complete UI or
accessibility pass. Line/donut/KPI cards, archive/restore, report-version edits,
contact-log create/void, keyboard/hover interactions, larger-result pagination
and narrow/dark layouts remain unrun in the physical native app. Their automated
component/backend tests above are separate evidence. No production readiness,
custom stage support, historical conversion, automated dashboard monitoring or
live Gmail connection is established. See [report limits](FLEXIBLE_REPORTS.md).

## Compact workspace and HermesCRM branding

A subsequent screenshot-driven UI increment changes the visible branding to
**HermesCRM: Intelligent Relationship Management**, while retaining package,
route, tool and storage identifiers. Every tab has a compact title/action row
with an accessible About dialog. Record discussion offers direct, scoped,
version-checked Copy and an optional Hide preview control. Normal views no longer
show persistent test-data banners or setup pitches; provenance and the guarded
empty-workspace seed flow remain in About.

Independent review and native React/SDK tests cover all five headings, modal
focus/Tab/Escape/return focus, one-click Copy, preview collapse/reopen, stale
record/chat/profile safeguards and hidden setup controls. The test setup’s first
collapsed-disclosure focus issue was corrected before review passed. Existing
alerts, execution uncertainty, permissions and data boundaries remain intact.

The exact pinned SDK was inspected again. Its deferred insertion targets mutable
main-composer state and appends from a draft mirror without atomic live-editor
reconciliation. No safe automatic paste contract is established. This increment
never calls composer write/submit or reads a draft; Copy does not mean attached,
pasted or sent. The user retains paste/review/Send.

The default Python regression suite passed **992 tests**, with **475 optional
cases skipped** and two dependency warnings. Seven affected native suites passed,
including actual React 19.3 and pinned SDK source checks; one optional nanostores
fixture was unavailable. Generated panel sync and syntax checks pass. These are
automated checks, not physical visual inspection of the compact layout. The
user’s open review app was not changed while they were interacting with it.

## Completed inactive schedule handling

Cancellation previously always attempted Pause after finding a bound job, even
when that one-shot had already completed and was disabled. The pinned host
rejects changing a terminal job to paused. The correction recognizes only a fresh,
unique exact-job observation matching the existing assignment contract, with
`state=completed`, `enabled=false` and an explicitly null next run. It records
**already inactive observed** and sends no pause for that observation. This is
historical host evidence, not a successful cancellation, interrupted agent,
verified business completion or guarantee against a later host change.

The inactive observation is distinct from pause success in the coverage queue
and task details. Old unknowns are not rewritten. Missing, malformed, conflicting,
foreign, stale or subsequently contradicted evidence cannot clear uncertainty.
Report contents, human review and business-task completion remain separate.

Every local assignment-event append shares a row lock. Cancellation and
reconciliation compare both assignment version and an event-count watermark
before accepting an observation, so event-only concurrent changes cannot be
silently overwritten. New local event-recording times are monotonic under that
lock, advancing by one microsecond when necessary to preserve ordering across
equal clock ticks or rollback. This is local recording order, not a correction
to native execution timestamps; actual deadline guards still use the real clock.

No timestamp correction was needed: the report normalizes an offset-aware host
start to UTC, preserving the instant. New timezone regressions cover midnight,
fractional offsets, the repeated DST hour, equivalent replay and naive rejection;
there is no execution-timestamp normalization change or historical report rewrite.

Final correction checks on November 7, 2026:

- Shipping-scope default Python: **718 passed, 421 opt-in cases skipped**, with
  three dependency warnings. Dormant chat-request research remains excluded.
- Actual disposable PostgreSQL 17.11: **281 contracts passed**, including
  cancellation/observation races, equal ticks/rollback ordering and coverage.
  The synthetic localhost-only cluster was stopped after the run.
- Actual pinned-host ASGI/IPC, native-work and command routing: **six passed**;
  one historical due-run placeholder remains explicitly skipped.
- Guarded command-to-scheduled-agent fixture: **two passed**, both modes. The
  completed first assignment's cancellation performs exactly one List and no
  Pause, preserves its report and open business task, and records inactive
  evidence. The separate future assignment is still paused before due and never
  executes. The original guard/runner is unchanged; only the model endpoint is
  synthetic. Both modes recorded zero forbidden audit events and cleaned up all
  jobs, scheduler, plugin child and endpoint. See
  [sanitized results](native-work-test/inactive-cancellation-result-summary.json).
- All eight UI suites and the unchanged disabled bridge's **25 tests** pass;
  Python/JS syntax and whitespace checks pass. Independent review found no
  remaining actionable issue. Native-window and real-model validation of this
  correction remain unperformed.

## Real-model scheduled check

A separately authorized isolated Mac test passed on published CRM commit
`3ea680a7dfe817ee255990b3b5005ed87e73a962` and exact Hermes source
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Terra 6.1 with xhigh reasoning ran once
at the approved time, read the synthetic assignment/task, reported the requested
calculation (7 × 13 = 91 USD) and verified its saved report. Canonical native
admission/result and local output were verified. The authenticated report awaited
human review and the business task remained open.

The run exposed only the eleven CRM read/report tools. Deferred discovery was
disabled in this particular test. It used no new credentials/grants, outbound
email/text, production data or production system changes. This is one bounded
real-model internal-analysis check, not a guarantee of general reasoning quality,
prompt-injection resistance, native-window interaction, model-chosen scheduling,
restart recovery, or future-cancellation behavior.

Cleanup invalidated local assignment intent, but its pause outcome remained
unknown because the isolation guard rejected a shared host-lock write. No retry
or guard relaxation occurred. Independently persisted job evidence showed that
the one-shot had completed and disabled itself before cleanup, with no next run;
zero enabled test jobs remained and the scheduler exited. This was **not** a
verified pause/cancellation. The newer completed-inactive handling above has
separate synthetic verification; it was not exercised in this historical real
model run. The initially suspected timezone discrepancy was a reporting mistake:
the UTC and local-offset values represent exactly the same instant.

## CRM-confirmed future-operation increment

The CRM companion now offers explicit review and confirmation for an exact saved
future assignment, plus separate host-status checks and cancellation. REST
prepares a durable server-derived operation; an authenticated registered native
user command claims that operation once and invokes the existing paused-create,
bind and resume implementation. It never submits a prompt or touches native
drafts. This is CRM confirmation, not a model-tool approval receipt.

The operation table is new; existing CRM/native-work tables are unchanged.
SQLite and PostgreSQL contracts cover immutable snapshots, source/assignment CAS,
expiry including lock waits, withdrawal, duplicate/concurrent dispatch, backend
identity, unknown replies and the separation of local status from native effects.
A lost or delayed command is not replayed automatically. Unresolved history is
paged and remains recoverable after reload.

Actual pinned-host cases use real plugin registration, durable local-session
creation/receipts, SessionAuthority, actor/owner/source authorization,
AuthorityConnection command admission and context propagation in both plugin
isolation modes. The scheduler boundary in those routing cases is synthetic:
they establish native command admission, not job or model execution.

Separate guarded command-to-run cases also pass in both isolation modes. Actual
REST preparation and durable native user-command admission schedule two future
assignments through the real paused-create/bind/resume path. The actual clock,
scheduler, canonical admission, AIAgent, default deferred discovery, CRM reads,
authenticated report and local output then execute. Only the keyless loopback
model responses are synthetic. Seven model requests per mode discover exactly
the eleven allowed tools and reject six forbidden descriptions. No request or
ledger start precedes the due instant; extra ticks add no duplicate run/report.
The second assignment is cancelled through the same command lane before due and
never executes. Reports await review and business tasks remain open. The guard,
original runner and cleanup checks are unchanged. Both modes recorded zero
forbidden audit events and stopped jobs, scheduler, endpoint and plugin child.
See [sanitized results](native-work-test/command-result-summary.json) and
[reproduction](native-work-test/REPRODUCE.md#crm-confirmed-command-to-run-variant).

Final checks on November 7, 2026:

- Shipping-scope default Python: **617 passed, 320 explicit opt-in cases skipped**,
  with three dependency warnings. Inactive chat-request research is excluded.
- Actual disposable PostgreSQL 17.11: **180 contracts passed**, including 57
  operation cases and the 123 earlier native-work/coverage cases. The localhost-only
  synthetic cluster was stopped after testing; no hosted database was used.
- Actual pinned-host ASGI/IPC, native-work and user-command contracts:
  **six passed**, two per suite across both modes. One historical placeholder
  remains explicitly skipped; it is not counted as a passed due-run test.
- Guarded command-to-scheduled-agent execution: **two passed**, both modes.
- Eight UI suites pass, including real React 19.3.0 and exact-source SDK/catalog/
  nanostores checks. The unchanged disabled execution bridge passes **25 tests**,
  including its explicit SQLite adapter. Syntax and whitespace checks pass.

The namespace is derived from existing high-entropy workspace identity; it is
not a credential. Exact-source catalog probes and the UI reject current
quick-command, alias, skill and built-in collisions or discovery warnings. The
host still resolves commands from current configuration at dispatch time. These
checks assume stable trusted host configuration and do not atomically attest
plugin ownership or protect against a concurrent malicious registration.

UI tests cover explicit review/confirmation, no automatic dispatch, exact route
and runtime checks, backend-profile aliases, synchronous session/profile/
connection/visibility changes, Close during an await, one-use attempts, unknown
results, recovery-only history, withdrawal and unsupported APIs. The visibility
contract executes the pinned SDK wrapper/predicate/cache and tree model with
integrity-verified official nanostores 1.4.2; its physical-column classification
is synthetic. Tests do not open a real native window.

Native-window layout/focus/accessibility, an actual user clicking through this
new lane, real-model reasoning and restart/crash reconciliation remain separate
release checks. No upstream Hermes change, live provider, account access,
external communication or production modification was used. See
[the operation boundary](CRM_CONFIRMED_OPERATIONS.md) for scope and rejected
unsafe chat-submission alternatives.

## Direct assignment-saving increment

The native CRM now saves a real future internal-analysis assignment through an
explicit review and Save action, without requiring an open conversation. The
new authenticated `POST /work` route writes local intent through the existing
atomic native-work store. It cannot dispatch a tool, model or scheduler. Exact
receipts and paged history show **Saved, not scheduled** separately from later
native-chat scheduling requests.

Verification on November 7, 2026:

- Full default Python regression: **541 passed, 259 opt-in cases skipped**,
  with three dependency warnings. Save contracts cover strict inputs, captured
  workspace/profile, atomic expected version, stale/done source rejection,
  exact idempotent replay after source changes, and zero host dispatch.
- Actual pinned-host authenticated ASGI/IPC: **two cases passed**, one in each
  plugin isolation mode. They exercise direct saving, token/profile boundaries,
  source conflicts and replay through the real host routes. The isolated guard
  forbids network/model calls and original-home access. An independent reviewer
  reran both cases successfully.
- All six UI suites passed, including real React 19.3.0, pinned-source chat and
  the expanded assignment suite. Save regressions cover exact microseconds and
  keys, no-chat use, duplicate/stale writes, malformed/lost replies, profile and
  reconnect A→B→A, backend-profile aliases, a second deliberate assignment,
  receipt/history presentation, and focus return after closure. The unchanged,
  disabled execution bridge passed **25 tests**, including its SQLite adapter.
- Independent source/documentation review found no remaining actionable issue
  in this Save-only increment. Syntax and whitespace checks passed.

No database schema changed. The earlier 123 PostgreSQL native-work/coverage
checks below remain historical evidence. A fresh optional rerun was blocked at
disposable-cluster startup by the environment's Unix-socket restriction; the
server shut down before any tests ran. This is not a new PostgreSQL pass.

Unconfirmed-save recovery is retained only for the plugin lifetime, with an
explicit reload warning and selectable original request. Confirmed intent is
durable. A lost response is not proof of no write, and the UI offers only the
same-key replay, not an automatic replacement. Native pixels, physical
keyboard/focus behavior, actual chat Send and real-model execution of these
requests were not tested. No direct native Send, provider adapter or external
communication was enabled. The separate Google Workspace assessment is
source-only; see [its exact limits](GOOGLE_WORKSPACE_ASSESSMENT.md).

## Assignment request and coverage increment

The native Tasks view now prepares explicit requests beside the genuine native conversation and shows paged coverage/history evidence. Preview and Copy re-read scoped source records; preparation does not save intent, submit a prompt or schedule work. The user must paste, review and use native Send. New create requests include an atomic `expected_task_version` check; exact legacy omission and original-version replay remain supported. No tool names or scheduled toolsets were added.

Verification on November 7, 2026:

- Full default Python suite: **537 passed, 259 explicitly skipped**, with three dependency deprecation warnings. Skips are optional PostgreSQL, actual-host and guarded runtime cases, not passing executions.
- Actual disposable PostgreSQL 17.11: **123 native-work/coverage contracts passed**, including expected-version races, replay and rollback, more than 500 tasks/100 assignments, exact totals, completed/stale-task risks, mixed assignment histories and consistent first-use/data/count snapshots. The fresh UTF-8 test cluster was stopped after testing. An initial SQL_ASCII harness handshake failure was corrected before this passing run; it was not counted as success.
- Actual pinned Hermes backend on CPython 3.14.9: **two ASGI/IPC integration cases passed**, one per plugin isolation mode. They cover authenticated `/reports/work` and `/reports/coverage`, filtering/paging, expected-version schema and handling, stale rejection, original intent replay after completion, and secondary-profile/token isolation. The fixture constructs fresh homes/environment, denies original-home reads and network/model access, and permits only the exact hosted-plugin child and narrowly specified read-only Git probes in the pinned checkout, and requires post-guard ready markers before host imports. Broken-setup probes terminate both the main runner and IPC child before fixture work. No network server, scheduler job or model turn runs in these cases.
- Six UI suites passed: standalone VM, native SDK smoke, routing, real React 19.3.0, pinned-source native chat and the new assignment suite. The unchanged disabled execution bridge passed all **25 tests**, including the explicit real-SQLite adapter check. Syntax and whitespace checks passed.

The new component regressions cover exact expected versions and stable keys, persisted microsecond timestamps, explicit offset input, task/assignment edits between Preview and Copy, preparation-time chat binding, pre-Preview conversation changes, source/profile/chat A→B→A transitions, stale async actions, clipboard uncertainty, discard focus, history/coverage filter-page ABA, exact-assignment drillthrough outside the first 100 history entries, and cancellation pause-evidence fencing. A synthetic history response reports 700 assignments with the selected assignment outside its current page; the separate database tests exercise more than 100 stored assignments. Tests assert zero composer access, prompt/session/cron dispatch or CRM writes from preparation and report controls. Immediate-help text permits only CRM changes specifically requested in the user-reviewed instructions through normal host policy; future assigned work remains internal read/report only.

Coverage totals are evidence-item counts, not unique leads or guaranteed execution. The report reads complete relevant history in one actual database snapshot before filtering and paging; its current cost scales with that history. First-use schema availability is checked inside the same snapshot so new tables cannot produce a false unassigned result. Offset pages are not a frozen cursor across concurrent changes. Stored job observations, authenticated agent reports and business-task completion remain distinct. A local refresh does not query the scheduler.

These are database, source-contract and component checks, not native-window layout, actual clipboard/native Send, a model choosing the requested tools, operational restart recovery or external delivery. The existing review application and production profiles were not modified. No email provider access or sending was added. See [the workflow](ASSIGNMENT_UI.md) for the two-step entry from ordinary CRM and remaining limits.

Run the normal regression suite, `node --experimental-vm-modules tests/native_desktop_assignments.mjs`, and the other UI suites below. The actual-host cases use `HERMES_SOURCE=/path/to/the/pinned/hermes-agent python -m pytest tests/test_desktop_host.py -q` with the supported host dependencies. The optional database command is `HERMES_CRM_TEST_POSTGRES_URL='postgresql+psycopg://...' python -m pytest tests/test_native_work_postgres.py tests/test_coverage_postgres.py -q`; use only a separately selected disposable database.

## Native conversation companion increment

The latest UI adds **Chat with Hermes** for an already loaded, verified primary conversation in the current connection/profile. It opens a right-docked CRM workspace and returns to that same native conversation, preserving the CRM section, filters, page and selected detail. Unsaved CRM forms block relocation. **Preview record reference** and **Copy record reference** expose only connection/profile/kind/ID/version, with a scoped fresh-read/version check before clipboard writing. The user pastes, reviews and sends in native chat; the plugin performs zero composer reads, writes or submissions and creates no conversation.

The focused chat suite exercises actual pinned SDK docking code and layout-model functions plus real React 19.3.0 lifecycle with explicit host/transport fixtures. It covers source/session/profile/cwd changes, same-tick invalidation, duplicate opens, stale close callbacks, disposal, missing capabilities, ignored docking, selected-view preservation, blocked active forms, minimal context, unavailable clipboard, fresh-record/version checks and stale copy responses. Missing or unmounted composer cannot receive a delayed write because no composer helper is accessed. An independent review found and fixed epoch-only reconnection recovery: reopening now replaces a dock bound to the previous activation.

These are source-contract and component checks, not a live Electron, native clipboard, full keyboard/focus or real-model conversation test. Earlier native Mac screenshots do not verify this new split. The final run passed all five UI suites and the 25-test bridge suite; the default Python regression remained 300 passed, 222 explicitly skipped. The new harness was tested with Node 24.22.1 and uses its built-in `stripTypeScriptTypes` support alongside the existing React 19.3.0 test dependencies. Run `HERMES_SOURCE=/path/to/the/pinned/hermes-agent node --experimental-vm-modules tests/native_desktop_chat.mjs` in addition to the existing UI suites. Blank/new chats and secondary-session tiles are deliberately unsupported by this first handoff; no session is guessed or created.

## Native assigned-work increment

The current source adds future one-shot assignments through real active Hermes tool context, using paused create, exact durable binding and separate resume. Seven new tools bring the registered total to 22; the ordinary `crm_read` inventory remains eight. Assignment reads, scheduling and the trusted-context report writer have separate toolsets. There is no direct Desktop scheduling endpoint or Run now button, and reports do not complete business tasks. See NATIVE_ASSIGNED_WORK.md for the exact contract.

- The full default Python suite passes: 300 tests passed, 222 skipped. Skips are explicit opt-in host, PostgreSQL or guarded-run tests, not successful executions of those cases.
- Native-work domain and adapter suites pass 144 tests. Actual PostgreSQL 17.11 passes 86 native-work contracts, including schema constraints and both crash-boundary regressions. Disposable schemas were removed and the server stopped.
- Two actual pinned-host contract tests cover in-process and hosted plugin modes: real registry dispatch, paused create/bind/resume, resolver scope, fire claims, running-ledger compare-and-swap and trusted report context. They reject ordinary/delegated/forged reports and cover unknown outcomes without creating replacement jobs. Those tests do not run a model turn.
- Both actual Desktop backend modes verify that tool-created intent is readable through authenticated assignment-history routes, preserving workspace/profile tokens, serving-profile aliases and secondary-profile isolation.
- Guarded scheduler/agent execution with SQLite passes both modes on Linux x86_64, CPython 3.14.9+20261021, OpenAI 2.54.0 and urllib3 2.8.0: 2 tests passed. The official host is the exact pinned revision below. Runtime/archive, host locks, probe source hashes, installed versions and portable setup instructions are recorded in [the reproduction bundle](native-work-test/REPRODUCE.md). The host's intentional Pillow 13.0.0 security override remains in its frozen dependency closure; its own compatibility check reports no unexpected mismatches.

The guarded test setup invokes real registered scheduling handlers with a real active-agent/session context, verifies paused create/bind/resume, then lets the real clock and InProcessCronScheduler fire the job. It does not test a model choosing to create a schedule or an interactive approval dialog. The scheduled run enters actual canonical admission and AIAgent. Only its keyless loopback model endpoint is synthetic; seven streaming responses per mode drive real default tool search/description, assignment/task/contact reads and authenticated reporting.

The observed default discovery catalog contains exactly the 11 permitted scheduled tools; six forbidden descriptions are rejected. The test correlates the exact request, principal, session, admission, policy, stored successful cron result, execution ledger and report identity. Local output contains the data-derived synthetic report. The report remains awaiting human review and the business task remains open. The real ledger start and every model-request receive timestamp are at or after the approved due instant; extra scheduler ticks add no execution, report or model request. A second real future assignment is cancelled before due and never executes.

Guard bootstrap failure is fatal, not a swallowed sitecustomize warning. Corrupted-hash negative startup tests stop both the runner and official plugin child before application work; post-hook ready markers are required. The original home is denied entirely, and only the exact model endpoint plus narrowly source-pinned benign probes are allowed. Both final runs recorded zero forbidden audit events and cleaned up all disposable jobs, scheduler threads, model endpoints and hosted plugin processes. Generated profiles, logs, databases and evidence are not shipped.

This verifies the bounded internal execution/data path. It does not verify real-model quality, prompt-injection resistance, visible Desktop presentation, external delivery, restart recovery or live failure reconciliation. No MCP server was configured in this run; configured-MCP exclusion remains a separate resolver test. It is not a general guarantee that future host versions or changed tool implementations preserve the same capability boundary.

## Native record-form increment

The native record view now groups identity and key properties, real edit/related-record actions, upcoming work, the CRM audit timeline and related deals. Create/edit uses a pane-local drawer with persistent labels and grouped fields. Task details include read-only assignment history; record audit remains distinct from sent/received email history. No email/chat sending control or provider integration is added.

Real React and SDK fixtures cover field validation, values and exact unchanged timestamps, linked-ID retention, duplicate saves, dismissed/stale callbacks and profile/reconnect safety. Independent review found and fixed local-domain email validation and assignment-history refresh issues. Expanded reports now stay open through polling and refresh errors, with explicit last-observation notices rather than false freshness. All four UI suites and the 25-test experimental bridge suite pass; independent re-review found no remaining actionable defects. React checks also pass in UTC and America/New_York. These component tests do not establish native pixel layout, real browser disclosure/focus/inert behavior, scrolling, contrast or narrow-pane usability. Those are still release gates.

## Earlier report/filter increment

This increment added Stage versus Contact type terminology, a six-stage dashboard value donut, unique-contact drillthrough, missing/overdue lead follow-up presets and server-side combined filters. Contact reports return stable pages and true filtered totals beyond 500 records. These changes are separate from the historical native Mac and scheduler runs below; new chart/filter workflows have not yet been visually checked in a native window. Direct agent assignments/execution were not part of this increment.

Verification for this increment:
- SQLite/domain, standalone/native API and report contracts pass, including unique counts across multiple deals, indirect task links, literal wildcard search, combined filters, strict validation, cent ranges and timezone boundaries.
- Actual PostgreSQL 17.11: 28 tests pass on a disposable local cluster, including the shared report contracts. Test schemas were removed and the server stopped. Hosted Supabase remains untested.
- Three actual-host tests pass against the pinned source below, including authenticated profile routing and the scheduler MCP resolver.
- All four JavaScript suites pass: standalone VM, native SDK smoke, routing, and real React 19.3.0 Strict Mode. Added cases cover zero/single/multiple chart segments, hover/focus/keyboard drillthrough, unique-contact versus deal counts, server pagination/filter reset, stale responses, cents and preservation of linked IDs outside bounded form choices.
- Independent review found and fixed a report/editor race: cancelling a new-contact form no longer discards a still-current pending report response. Its regression failed before the fix and passes afterward.

Run `python -m pytest tests/test_crm.py tests/test_native_api.py tests/test_reports.py -q`, plus the opt-in host/PostgreSQL and JavaScript commands below. This increment registered 15 tools, including eight read tools; the older Doctor and live-scheduler counts below remain historical evidence, not a fresh run of those checks.

## Earlier verified baseline

### SQLite/domain and native API regression: 30 tests

Python 3.12, SQLAlchemy 2, SQLite. The 23 domain/standalone tests cover the contact/opportunity/task vertical slice, transactional audit, optimistic edits, concurrent create idempotency, input validation, literal search, linked-record integrity, timezone normalization, profile isolation, explicit backend selection, opt-in demo seed, API origin/Host controls and scheduler success/uncertainty handling. Seven native API tests cover shared storage, scoped reads/writes, validation, sanitized failures, atomic demo rollback, standalone entry-point import and a single-factory workspace snapshot.

Review fixes are regression-tested:
- Reassigning a deal updates linked task contacts atomically, advances task versions and records activity.
- Open follow-ups are filtered before the 500-row list limit, so completed history cannot hide them.
- Money schemas explicitly require integer USD cents and include the $12,000 → 1,200,000 example.
- Scheduled jobs carry no_mcp so enabled external MCP tools cannot be silently added.
- Task/deal searches include linked contact names and apply search/status filters before the 500-row cap.
- Workspace tokens prevent stale forms, demo confirmations and scoped reads from targeting a changed database.
- An unchanged task due date preserves its original seconds and microseconds instead of silently rounding a scheduled timestamp.

Run: `python -m pytest tests/test_crm.py tests/test_native_api.py -q`.

### Actual PostgreSQL: 23 tests

PostgreSQL 17.11 from official Debian packages, extracted into an isolated temporary directory. Tests ran on a disposable local cluster, not a hosted or user database. The shared CRM contracts passed alongside schema isolation, persisted UTC round trips, concurrent workspace-token creation, atomic demo seeding and injected rollback after record plus audit insertion. The contact-name search-before-limit regression also passed. All test schemas were removed and the server was stopped afterward.

Run with an explicit disposable database only:
`HERMES_CRM_TEST_POSTGRES_URL='postgresql+psycopg://...' python -m pytest tests/test_postgres.py -q`.

The test fixture creates random crm_test_ schemas and removes only those schemas. Without the explicit test URL, these tests are skipped. This verifies PostgreSQL behavior, not hosted Supabase authentication, RLS or deployment.

### Official Hermes checks

Exact source: official Hermes commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19. The isolated native runtime identifies as vgit.2bd378e and its source manifests declare 0.0.0. Earlier documentation's v0.23.0 label was imprecise; these checks establish source-revision compatibility, not a numeric release minimum.

- Plugin Doctor: actual discovery, manifest, import and registration passed; 14 tools, 0 hooks.
- Catalog validator: all 16 checks passed, including the Desktop surface; zero warnings; security scan safe; host_ready true.
- Native CRUD: actual PluginManager and scoped registry dispatched contact create/get/list, deal create/stage update, linked task create/get and overview using real ctx.get_config and plugin_db. Disposable profile only; no mocked host Context for this test.
- Host scheduler resolver: with an enabled external MCP configured, crm_read alone expands; crm_read + no_mcp resolves to exactly crm_read. Test imports the actual pinned upstream resolver, not a copied implementation.
- Actual Desktop backend: unified component discovery and Python import/enablement gates, real gateway session-token authentication, native tools and REST sharing records, version/token conflicts, runtime disablement and secondary-profile routing through host IPC. Two tests cover in_process and isolated host modes using the actual upstream server and plugin manager, not replacement core APIs.

The three opt-in host tests are reproducible with HERMES_SOURCE pointing at the official checkout and its dependencies installed:
`HERMES_SOURCE=/path/to/hermes-agent python -m pytest tests/test_desktop_host.py tests/test_hermes_host.py -q`.

These automated host checks used isolated profile homes and no model calls or cron jobs. A separate real scheduler execution test is documented below; Doctor/catalog loadability alone is not proof that a reminder fires. Native host startup has a separate provider auto-discovery caveat.

### Native Desktop and standalone UI checks

JavaScript syntax and whitespace checks pass. The standalone VM suite covers section rendering, empty states, escaping, currency, server-side task filters, pending form cancellation, stale-response rejection, current-version replacement and exact timestamp preservation.

The native VM suite checks SDK registration/imports, scoped transport, stale response/write rejection, create payloads, profile remounts and timer cleanup. The actual React 19.3.0 Strict Mode suite tests dashboard/contacts/forms, name-only contact creation, versioned edit/completion, unchanged scheduled timestamps, scoped snapshot/search, captured demo targets, navigation races, profile/source remounts and subscription/timer cleanup. React is real; the SDK transport is an explicit fixture. Optional HERMES_SOURCE checks compare the used SDK exports and CSS variables with the pinned host.

The routing regression suite additionally exercises synchronous open→closed→open and profile/source A→B→A transitions before React can render, same-valued official epoch changes, pending stale responses, stale write callbacks, Strict Mode request invalidation and plugin unload/reload. An exact legacy capability-shape fixture links the namespace import and verifies that the compatibility screen performs zero REST calls or polling. The actual React suite checks stale form callbacks in the same transition batch and the subsequent workspace remount.

Run `node tests/ui_smoke.cjs`, `node --experimental-vm-modules tests/native_desktop_smoke.mjs`, `node --experimental-vm-modules tests/native_desktop_routing.mjs` and `node --experimental-vm-modules tests/native_desktop_react.mjs`. The React suite requires the exact test-only dependencies listed at its top; they are not bundled with the plugin. These are logic, component and server checks, not a real Electron rendering or full browser-to-backend pass.

Exact historical Desktop and Agent source checks are recorded in COMPATIBILITY.md. The older Agent is deliberately unsupported; its two current-host integration-test failures and authenticated metadata 503 responses are not counted as passing product tests.

### Genuine native Mac workflow run

CRM source: public commit `8ab6f511899253235bc2d9e5432ef486fe95e0dc`. Host: the pinned official source commit above, built in its supported isolated development sandbox and reporting `vgit.2bd378e`. The existing Desktop/Agent installation was not modified; this was a separate source build, not a demonstration that an older installed release is compatible.

Verified in the native window:
- Local Git installation through a `file:///absolute/path` URI, enablement and CRM rendering. The bare absolute-path install form failed by being misparsed as a GitHub identifier.
- Explicit demo seed: eight contacts, eight deals, $113,500 open pipeline and $48,100 weighted forecast.
- Contact editing persisted version 2 and a desktop audit entry. The actual registered agent tool read that change, updated the record, and Desktop displayed the update. This was a registered-tool interoperability check, not a live model conversation.
- Completing a follow-up changed open tasks from five to four and overdue tasks from one to zero.
- Pipeline drill-through showed two proposal deals totaling $60,000.
- A new empty secondary profile showed zero contacts, deals and tasks; switching back restored the synthetic sample workspace.
- Genuine native-window dashboard and contact-detail screenshots were captured using synthetic records only.

The Mac run also passed 33 Python tests (the 30 domain/API plus three actual-host tests, not an additional 33 distinct contracts), Plugin Doctor's 14 registered tools, all 16 catalog checks, standalone/native smoke and routing suites, actual React 19.3.0 Strict Mode tests, syntax and whitespace checks.

During this native-window phase, no working model provider was configured and cron execution was not attempted. Host provider auto-discovery nevertheless attempted a login refresh and received `invalid_grant`. No credentials were manually retrieved or copied. A fresh Hermes home is not sufficient to isolate all host credential discovery; see NATIVE_DESKTOP.md for safe testing guidance. The later scheduler test used a separate guarded, disposable profile and a keyless loopback endpoint.

### Real scheduler execution with deterministic local model responses

Passed November 6, 2026 on macOS against CRM commit `e3daa0bad315bef4d996b900848e11c600e408a4` and Hermes host commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.

Execution used real plugin discovery and the native `crm_followup_schedule` handler, actual `ctx.dispatch_tool('cronjob_manage', ...)` registration, `InProcessCronScheduler` with one-second ticks, real due-date selection and fire claims, canonical `SessionAuthority` admission, and `AIAgent`. The streamed tool call reached the actual `crm_task_get` handler and database. The scheduler, clock, resolver, admission, CRM handlers, database and agent loop were not mocked.

Only the model endpoint was synthetic. A keyless loopback HTTP server emitted deterministic streaming responses: first a request to read the scheduled task, then a response based on the returned task data. This proves execution and data wiring, not model reasoning, instruction-following quality or prompt-injection resistance.

Two future one-shot jobs were created through the real CRM scheduling tool:
- One task remained open. After its due instant, the result contained the internal reminder and due date.
- The other task was completed after scheduling but before firing. Its result reported no action needed.

Neither job made model requests before its due time. Each fired after the real due instant, performed one real CRM read and made exactly two loopback model HTTP requests. Three additional scheduler ticks produced no further model requests or duplicate execution rows. This is bounded duplicate-execution evidence, not a guarantee across restarts or failures.

Both host execution-ledger rows recorded a scheduled instant, source `builtin`, status `completed` and no error. Both persisted host jobs finished completed, disabled and with last status `ok`. Local output files contained the expected open/completed responses. The delivery outcome `suppressed` means external transport was not used for `deliver='local'`; it does not mean local output persistence failed. No visible Desktop notification, chat presentation or external delivery was tested.

The stored allowlist was `['crm_read', 'no_mcp']`. The advertised tools were exactly `crm_contact_get`, `crm_contact_list`, `crm_deal_get`, `crm_deal_list`, `crm_overview`, `crm_task_get` and `crm_task_list`. Deferred tool-schema discovery was explicitly disabled with `tools.tool_search.enabled='off'` for direct inspection. No MCP servers were configured in this run. Default deferred discovery and a configured-MCP live run are therefore not covered; exclusion of configured MCP tools was checked separately by the actual-host resolver test above.

The run used no real provider credentials, account login, external service or external message. A process-local audit guard allowed socket connections only to the exact test endpoint and denied real credential/profile reads and child application/provider launches; no disallowed network attempts were recorded. Cleanup verified zero enabled jobs in disposable test homes, exited test processes and closed test endpoints. Successful jobs disabled themselves; interrupted harness-development jobs were paused through the host API. Existing Desktop/profile state, production/VPS state and repository files were unchanged. Private test logs, databases and outputs are not included in this source package.

## Not completed

- Broader native accessibility, keyboard/focus, responsive-layout and cross-platform QA beyond the Mac workflows above. Standalone desktop/mobile browser QA also remains incomplete; the earlier cloud browser restrictions were not bypassed.
- Real-model scheduled reasoning, a configured-MCP live run, visible Desktop reminder presentation, external delivery, restart recovery and live failure reconciliation. Default deferred discovery passed the newer bounded assigned-work fixture, not a real-model conversation. External outreach remains outside this plugin's scope.
- Hosted Supabase connectivity, network latency/failure behavior and deployment security.
- Catalog PR, social post, contest form or production deployment.

## Source prototype publication

The source prototype is public at https://github.com/gptnius/hermes-crm. Its initial published commit is 1c70b16f09dfb534109abb3406d35e08c9f9085e; the native Mac workflow baseline is 8ab6f511899253235bc2d9e5432ef486fe95e0dc and the scheduler test baseline is e3daa0bad315bef4d996b900848e11c600e408a4. Source publication is not completion of all runtime or contest milestones. Changes undergo independent review before publication.

## Release gates still open

1. Visually verify the new chart/filter/report workflows in the native window. Expand accessibility, keyboard/focus and responsive/cross-platform coverage beyond the earlier verified Mac workflows; complete standalone desktop/mobile QA.
2. Extend scheduler coverage to an authorized real model, restart/failure recovery and any intended human-visible reminder surface. The bounded assigned-work fixture covers default tool discovery; a configured-MCP live run remains separate. Keep external outreach excluded.
3. Complete source-distribution review and pin the reviewed commit before publishing each update.
4. Complete the runtime gates before calling this a fully validated release or preparing any authorized contest submission. A clearly labeled source prototype can remain public while those gates are open.

CRM records were synthetic. No production CRM or deployment was modified, and no private repository history or credentials were copied into the plugin. The host authentication auto-discovery attempt is disclosed above rather than treating a separate home as complete credential isolation. Dependency deprecation warnings are recorded in test output; no application test failure remains in the supported checks above.

## Optional read-only Gmail pilot (2026-11-07)

This increment is default off and was tested only with synthetic provider
responses. No OAuth sign-in, account discovery, mailbox read, send, external
service, native application or production change occurred during validation.
The new manual-contact reader is separate from the still-disabled generic email
send/reconciliation contract and adds no agent tool or data to `crm_read`.

- Full source test suite: **856 passed, 437 optional checks skipped**, two
  dependency deprecation warnings. Optional skips are not counted as passes.
- Reader tests: **67 passed**; the original design examples remain separate.
  Strict method/path and response limits, contact query validation, identity
  checks, headers, empty pages, duplicates, time budgets and partial coverage
  use invented data and denied network access.
- Storage/API tests: **17 passed**, including durable replay, rollback, contact
  edits, revision ABA, explicit cancellation and local-action receipts.
- Actual disposable PostgreSQL 17.11: **15 passed**, including concurrent reads
  and disconnect, rollback, namespace separation, schema validation and replay.
  The fresh TCP-loopback-only database was stopped afterward; no hosted database
  or Supabase behavior was exercised.
- Native UI: eight SDK/React suites passed, including the email panel's explicit
  reviews, pending-read cancellation, response validation, durable receipts,
  stale-route suppression, plain text and storage-destination consent. The
  deterministic single-module build check and JavaScript syntax passed. These
  are not pixel screenshots or physical Desktop interaction tests.
- Actual pinned Hermes host source
  `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`: **two guarded native API tests passed**,
  covering in-process and hosted isolation, authentication, disabled-email
  endpoints, workspace tokens and secondary-profile routing/IPC. They used
  Python 3.14, FastAPI 0.133.1, Starlette 1.9.0 and Pydantic 2.14.1. The guard
  denied external networking, original-home access and agent/model launches.
  Only installed SQLAlchemy distribution files were copied into fresh test
  dependencies; the guard was not relaxed.
- The real host OAuth parser/admission checks passed separately without invoking
  authentication or a provider request. The manifest's requested scopes and
  origins were validated, not an actual consent grant or token's scope ceiling.
- Independent code/document review found no remaining issue under the disclosed
  original-workspace completion semantics.

An alternate environment (Python 3.12, FastAPI 0.141.1, Starlette 1.6.0,
Pydantic 2.13.4) failed the in-process native host test in repeated hot-mount
fallback recursion. The unchanged pre-Gmail baseline reproduced the same
failure. Hosted isolation passed in that environment, but it is **not** a fully
verified native dependency combination. No host code, installed application or
system configuration was modified to obtain the passing result above.

The first PostgreSQL attempt started its test server in a separate command;
that process did not survive to the test command. It produced connection-refused
setup failures, not application passes. Starting the fresh cluster and tests in
the same bounded command produced the 15-pass result and confirmed shutdown.

Live Gmail authorization/refresh, actual contact-query matching and mailbox
content, Workspace policy, physical Desktop visual QA, broader incremental sync,
OAuth scope attestation and production readiness remain unverified. Read the
current [setup, privacy and cancellation limits](GMAIL_SETUP.md).
