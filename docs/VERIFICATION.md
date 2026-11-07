# Verification report

Updated November 7, 2026. Historical native and scheduler runs below retain their original scope. This is a tested prototype, not a production release. Native Mac workflows and real one-shot scheduler execution passed on the exact source builds below. The scheduler test used deterministic loopback model responses, not a real model. Real-model behavior, visible reminder presentation, restart recovery, broader accessibility/responsive coverage and hosted-service validation remain incomplete.

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
