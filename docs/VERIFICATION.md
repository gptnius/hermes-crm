# Verification report

Verified November 6, 2026. This is a tested prototype, not a production release. Native Mac installation and core visual workflows passed on the exact source build below. Live scheduler firing, broader accessibility/responsive coverage and hosted-service validation remain incomplete.

## Passed

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

Automated host checks used isolated profile homes and no model calls. No cron jobs were created. Doctor/catalog loadability is not proof that a live reminder fires. Native host startup has a separate provider auto-discovery caveat described below.

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

No working model provider was configured for this sandbox, and live cron execution was not attempted. Host provider auto-discovery nevertheless attempted a login refresh and received `invalid_grant`. No credentials were manually retrieved or copied. A fresh Hermes home is not sufficient to isolate all host credential discovery; see NATIVE_DESKTOP.md for safe testing guidance.

## Not completed

- Broader native accessibility, keyboard/focus, responsive-layout and cross-platform QA beyond the Mac workflows above. Standalone desktop/mobile browser QA also remains incomplete; the earlier cloud browser restrictions were not bypassed.
- A real Hermes scheduler create → gateway execution → local delivery cycle. Payload/state/host restriction tests pass, but no live job has been created.
- Hosted Supabase connectivity, network latency/failure behavior and deployment security.
- Catalog PR, social post, contest form or production deployment.

## Source prototype publication

The source prototype is public at https://github.com/gptnius/hermes-crm. Its initial published commit is 1c70b16f09dfb534109abb3406d35e08c9f9085e; the compatibility/reconnect fix and native Mac test baseline is 8ab6f511899253235bc2d9e5432ef486fe95e0dc. Source publication is not completion of all runtime or contest milestones. Changes undergo independent review before publication.

## Release gates still open

1. Expand accessibility, keyboard/focus and responsive/cross-platform coverage beyond the verified native Mac workflows; complete standalone desktop/mobile QA.
2. Exercise one synthetic internal follow-up in an isolated real Hermes gateway, including failure reconciliation.
3. Complete source-distribution review and pin the reviewed commit before publishing each update.
4. Complete the runtime gates before calling this a fully validated release or preparing any authorized contest submission. A clearly labeled source prototype can remain public while those gates are open.

CRM records were synthetic. No production CRM or deployment was modified, and no private repository history or credentials were copied into the plugin. The host authentication auto-discovery attempt is disclosed above rather than treating a separate home as complete credential isolation. Dependency deprecation warnings are recorded in test output; no application test failure remains in the supported checks above.
