# Verification report

Verified November 6, 2026. This is a tested local prototype, not a production release. Visual browser QA and a live scheduler firing remain incomplete.

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

Exact source: Hermes v0.23.0, commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19.

- Plugin Doctor: actual discovery, manifest, import and registration passed; 14 tools, 0 hooks.
- Catalog validator: all 16 checks passed, including the Desktop surface; zero warnings; security scan safe; host_ready true.
- Native CRUD: actual PluginManager and scoped registry dispatched contact create/get/list, deal create/stage update, linked task create/get and overview using real ctx.get_config and plugin_db. Disposable profile only; no mocked host Context for this test.
- Host scheduler resolver: with an enabled external MCP configured, crm_read alone expands; crm_read + no_mcp resolves to exactly crm_read. Test imports the actual pinned upstream resolver, not a copied implementation.
- Actual Desktop backend: unified component discovery and Python import/enablement gates, real gateway session-token authentication, native tools and REST sharing records, version/token conflicts, runtime disablement and secondary-profile routing through host IPC. Two tests cover in_process and isolated host modes using the actual upstream server and plugin manager, not replacement core APIs.

The three opt-in host tests are reproducible with HERMES_SOURCE pointing at the official checkout and its dependencies installed:
`HERMES_SOURCE=/path/to/hermes-agent python -m pytest tests/test_desktop_host.py tests/test_hermes_host.py -q`.

All host checks used isolated profile homes and no model calls. No cron jobs were created. Doctor/catalog loadability is not proof that a live reminder fires.

### Native Desktop and standalone UI checks

JavaScript syntax and whitespace checks pass. The standalone VM suite covers section rendering, empty states, escaping, currency, server-side task filters, pending form cancellation, stale-response rejection, current-version replacement and exact timestamp preservation.

The native VM suite checks SDK registration/imports, scoped transport, stale response/write rejection, create payloads, profile remounts and timer cleanup. The actual React 19.3.0 Strict Mode suite tests dashboard/contacts/forms, name-only contact creation, versioned edit/completion, unchanged scheduled timestamps, scoped snapshot/search, captured demo targets, navigation races, profile/source remounts and subscription/timer cleanup. React is real; the SDK transport is an explicit fixture. Optional HERMES_SOURCE checks compare the used SDK exports and CSS variables with the pinned host.

Run `node tests/ui_smoke.cjs`, `node --experimental-vm-modules tests/native_desktop_smoke.mjs` and `node --experimental-vm-modules tests/native_desktop_react.mjs`. The React suite requires the exact test-only dependencies listed at its top; they are not bundled with the plugin. These are logic, component and server checks, not a real Electron rendering or full browser-to-backend pass.

## Not completed

- Live browser layout and interaction QA. The available executable Chromium was denied socket creation before page startup. The supported cloud browser could not connect to the isolated local server. The browser also rejected file URLs. These restrictions were not bypassed. No screenshot or real-browser success is claimed.
- A real Hermes scheduler create → gateway execution → local delivery cycle. Payload/state/host restriction tests pass, but no live job has been created.
- Hosted Supabase connectivity, network latency/failure behavior and deployment security.
- Visual inspection of the native Hermes Desktop pane in a running Electron app. The native pane and real-host backend integration exist and pass the automated checks above; pixel layout, focus behavior and full accessibility remain unverified.
- External public repository creation, catalog PR, social post, contest form or production deployment.

## Release gates still open

1. Complete native Desktop/Electron visual and accessibility QA, plus standalone desktop/mobile QA, in an authorized browser-reachable environment.
2. Exercise one synthetic internal follow-up in an isolated real Hermes gateway, including failure reconciliation.
3. Complete the final source-distribution review and pin the reviewed commit before creating the repository under its verified owner.
4. Only then prepare the authorized public release or contest submission steps.

No real contacts, production systems, private repository history or credential stores were used. Dependency deprecation warnings are recorded in test output; no application test failure remains in the verified checks above.
