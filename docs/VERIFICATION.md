# Verification report

## Reading the release evidence

The submitted core is
[`da1d1412eaf10c3ea8ba0b4431cafdbc59c6bcae`](https://github.com/gptnius/hermes-crm/tree/da1d1412eaf10c3ea8ba0b4431cafdbc59c6bcae).
Its [hosted CI run](https://github.com/gptnius/hermes-crm/actions/runs/42724774779)
passed, and [catalog PR #152881](https://github.com/NousResearch/hermes-agent/pull/152881)
was merged on November 11, 2026. Catalog acceptance does not establish production
qualification. Historical sections below retain their original dates, source
identities, open items and test scope; their submission status is not a current
status report.

The [current scope and roadmap](ROADMAP.md) is the feature/status index. The
[published demo](https://x.com/gptnius/status/2120259388568961305) shows saved
native UI state and research records, with sample data for the dashboard and
pipeline. It is distinct from a new automated test run.

Gmail is absent from this core. The separate pilot's bounded live metadata check
is summarized in the [user guide](USER_GUIDE.md#provider-integration); it is
separate evidence, not a core test or proof of background synchronization,
message bodies, sending, a new OAuth grant or general recovery.

> **Contest core.** Available workflows and integration boundaries are summarized in the [user guide](USER_GUIDE.md) and [current scope and roadmap](ROADMAP.md). Gmail connections, OAuth settings, mailbox history and polling are not shipped in this edition. Legacy provider tables remain solely for encrypted export and quarantined recovery; opening the core does not clear or reconnect them. Exact host validation and remaining operational limits are recorded in [verification](VERIFICATION.md); test passes and catalog acceptance are not production certification.


Historical record, updated November 9, 2026. Native and scheduler runs below retain their original scope. This is a tested prototype, not a production release. Native Mac workflows and real one-shot scheduler execution passed on the exact source builds below. Most scheduler fixtures used deterministic loopback model responses; a separate bounded real-model internal-analysis check is recorded below. Broader reasoning behavior, visible reminder presentation, restart recovery, accessibility/cross-platform coverage and hosted-service validation remain incomplete.

## Storage Settings checks (November 9, 2026)

The SQLite/PostgreSQL Settings increment is based on core release
`001cb6aa617a544d182b5b9ef761d0bc6133e819`. The initial frozen QA tree was
`23a95186341c30bdfceba9d283d97f18dfe15214`; the final tested tree was
`02b004ce080e1646d6804bc90fdc0783c2be720b`. Only the actual-host test fixture
changed between those trees. All 296 final source hashes were checked. The
subsequent documentation update adds this evidence and the scheduled-work
cutover caveat, without changing runtime, UI or tests.

- **Local contracts:** final-byte Python completed with 1,616 passed, 824 explicit
  optional skips and two known warnings. All 13 generated-source checks and the
  JavaScript/React fixtures passed, including settings access after a failed
  snapshot, paused polling, stale-response rejection and the profile-scoped host
  settings handoff. The full runner covered 51 commands; Python was rerun after
  the last implementation change rather than treating the earlier count as final.
- **Read-only probe:** 18 local cases and one real disposable PostgreSQL case
  passed. Existing SQLite content is preserved; missing/corrupt stores, stale
  selection, malformed input, credential minimization and cleanup are covered.
  Independent real-driver tests used synthetic protocol peers to verify timeout
  cancellation, closed sockets and client-certificate suppression. These are not
  tests against a user's database or authentication setup.
- **PostgreSQL-enabled aggregate:** 2,417 passed, 23 explicit skips and four known
  warnings on PostgreSQL 17.11 ARM64. This mixed suite includes local/SQLite cases;
  it is not 2,417 exclusively PostgreSQL-backed checks. The focused cases overlap
  this total and must not be added. Its runtime/UI bytes match the final tree.
- **Official catalog:** the released Hermes v0.23.0 validator passed all 16 checks,
  with no warnings, six declared dependencies installed and host readiness true.
  PostgreSQL's driver is now a normal declared dependency. The later test-only
  correction does not change package dependencies or runtime behavior.
- **Actual host:** the final corrected fixture passed both Desktop isolation
  modes, both 83-tool registry/workflow modes and one local harness seam: five
  passes, no skips. This used the genuine v0.23.0 source and a separate Python
  3.14.9 environment with psycopg 3.3.8. These are synthetic ASGI/registry tests,
  not model calls or visible-app interactions; the seam also overlaps local tests.
- **Offscreen appearance:** 36 combinations passed layout checks across three
  saved/error states, light/dark themes, three widths and compact/expanded help.
  Six rendered images were inspected. The hidden Electron renderer used synthetic
  component responses, denied network/permissions and no visible window. This
  does not establish live database setup, physical keyboard/screen-reader use or
  complete accessibility coverage.

The first actual-host attempt failed a new fixture assumption that no database
existed before Storage was requested. Existing native command registration already
initializes the workspace. The corrected test snapshots the existing schema and
rows in a read-only transaction and checks that the Storage requests leave them
unchanged. It does not delete a database, skip registration or weaken the safety
guard. Absent-store non-initialization remains covered by the focused tests.

Owned PostgreSQL containers and hidden renderer exited; all guarded child
processes were confirmed gone, with no forbidden-action logs or cron jobs. No
installed app, user profile, database configuration or credentials were changed.
These checks do not prove a live hosted PostgreSQL/Supabase deployment, migration,
write readiness, production operation, catalog acceptance or submission. The
connection check deliberately tests connectivity only; normal CRM initialization
and any data/scheduler cutover remain separate operations.

## Core-only candidate checks (November 9, 2026)

**Historical baseline:** these checks precede the Storage Settings increment above.

The earlier core-only candidate is derived from public source tree `3b000756d78253b827d089cdfc20bc73c3fdc4a5` (public commit `c8ef7f2ffafc74f6d710e0fcff0447713ad8cef3`). Active provider code and provider-only tests are excluded, not hidden behind settings. The 83 core tools and existing data identifiers remain unchanged. Shared recovery tests seed synthetic legacy tables directly rather than invoking removed provider stores.

Candidate-specific regression tests check absent provider imports/routes/UI/polling, unchanged legacy rows after core CRUD, encrypted metadata export, recovery quarantine and partial/incompatible-schema rejection. Independent review found an inherited export gap for an incomplete older Gmail-history table family; a read-only schema check now rejects missing tables, changed columns and changed constraints instead of producing an unrestorable export. This check never creates, alters, reconnects or clears provider state. The acceptance runs below used source tree `a5dcad4759c045c1da61717a893fa6878e3fcaab`; all 288 file hashes were reconciled unchanged. This subsequent update changes only README.md, COMPATIBILITY.md and VERIFICATION.md. It does not change the tested runtime or tests.

- **Credential-free aggregate:** 1,598 Python tests passed, with 823 explicit skips; all 49 runner commands passed, including generated-section checks and JavaScript/React fixtures. Optional host/PostgreSQL coverage is not implied by this run.
- **Released-host validator:** the official v0.23.0 tag resolves to `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`; the clean runtime reports `0.23.0`. `plugins validate --install-deps --json` passed all 16 checks, with an empty warnings list, dependencies installed and `host_ready: true`.
- **Genuine host checks:** five passed: two Desktop isolation modes, two real 83-tool registry/workflow modes and one workflow seam. These exercise the real host using synthetic records, not live models or providers.
- **PostgreSQL-enabled aggregate:** PostgreSQL 17.11 run completed with 2,398 passed, 23 skipped and four known warnings in 130.34 seconds. This is a mixed suite that includes local variants, not 2,398 exclusively PostgreSQL-backed tests. Its coverage overlaps the other checks; do not add these counts together.
- **Source and UI contracts:** the pinned SDK chat fixture passed, including retention of an existing native tab draft and unchanged action-binding guards. The official Desktop source scanner reports no findings after renaming an internal CSV session method from `import` to `importRows`; HTTP operations, approval, retry and data guards are unchanged.

Owned-container and guard-process cleanup was verified. No live provider or model calls, installed-app changes or user-profile changes were made. These results do not establish maintainer acceptance, catalog listing, physical UI certification, live public research, hosted-service operation or production readiness. Historical full-edition evidence below retains its original scope.

## Historical full-edition evidence

The following records describe earlier snapshots. They are background, not certification of this candidate or its removed provider features.

## Empty-first distribution and preserved workspace records (November 9, 2026)

Normal standalone instructions now select SQLite explicitly, use an ignored
`.crm-data` directory and omit the opt-in seed flag. The native About dialog no
longer offers synthetic record creation. A previously seeded workspace retains
its conditional provenance in About or standalone Workspace details; existing
records, notes, audit actors and seed markers are not rewritten or deleted.
The developer-only CLI flag and explicit confirmation/workspace-token API remain
compatible. No backend, schema, storage factory or seed implementation changed.

Six release regressions passed from the source and an extracted freshly built
wheel. Temporary SQLite stores start with zero Contacts, Deals, Tasks, Companies
and Events. A separately seeded profile has eight contacts, eight deals and five
tasks while a second profile stays empty. Exact whole-table snapshots survive
reopening and ordinary reads, including IDs, notes, actors and provenance.
Import/tool registration does not open storage. CLI server startup is intercepted
and native host storage/config are doubles: this is not actual Hermes package
installation or activation proof.

Offline wheel and source-distribution inventories contain no saved databases,
SQLite WAL/SHM files, CSV exports, `.env`, `.git` or private workspace directories.
They contain reusable synthetic generators/test fixtures, not a user's saved
records, and those generators are not invoked by ordinary startup. Python
packages include backend/static assets; the native Desktop manifest/UI is
installed from the repository, a separate path not exercised by this packaging
check. Deliberately configuring a shared PostgreSQL database/workspace is not
local-only storage.

The actual React fixture checks empty SQLite and PostgreSQL metadata, ordinary
contact creation controls, conditional seeded provenance, absence of seed
buttons and zero `/demo` writes. It uses synthetic transport, not a physical
native window. No user datastore or installed app was modified for these checks.

The final credential-free local aggregate passed **1,871 Python tests, with 834
optional skips and two dependency warnings**, and all **50 runner commands**
(13 generators, the Python suite and 36 JavaScript/React commands). All 236 local
document-link targets resolved. Independent review reran the six new default
cases and the full native React interaction suite with no blocking findings.
PostgreSQL, genuine host activation, live providers and physical-window behavior
were not re-exercised for this UI/documentation-only change.

## Process-separated content recovery rehearsal (November 9, 2026)

The exact report-acknowledgement source tree
`e07ab221de1a96fe947ec4ec6b7cbf50b70bc6f5` passed a six-process rehearsal with
synthetic data and test-only keys. It seeded and reopened linked Company,
Contact, Event and owned Task content, custom values and research evidence;
produced an encrypted artifact through the supported export function; rejected
the wrong key without creating a target; restored through the documented CLI;
and reopened the restored content in two separate processes.

Assertions cover exact record versions and local idempotency/protected receipts,
retained-key decryption, SQLite integrity/foreign keys and content hashes.
Changing the supplied keyring's active key while retaining its historical key
preserved old-note reads; this was not persisted host key rotation or
re-encryption. The saved native-work intent was quarantined, with no live
assignment or task schedule restored. No actual job or endpoint was started.
All six processes produced guard-ready markers and exited; no forbidden audit
event occurred. The original child guard was unchanged.

Independent review covered the portable runner, preflight pins and recorded
results; it was not a second independent execution. The
[report and reproduction bundle](recovery-rehearsal/REPORT.md) retain exact
source/runtime hashes, the sanitized summary and limits. Raw profiles, logs,
databases and generated keyring files are excluded. The executed local archive
has the verified tree of public `73a7f61`; remote installation was not exercised.

This proves bounded content/process recovery, not supported plugin installation,
host activation/restart, authenticated native download, real-data cutover or
power-loss durability. No report acknowledgement, proposal, scheduled-research
run or previously active schedule was created in this rehearsal; their existing
unit/integration coverage remains separate. The current native React behavior
suites also passed, but the cloud visual attempt could not reach its isolated
HTTP fixture server. Generated HTML is not pixel or accessibility acceptance.

## Durable report acknowledgement and undo (November 9, 2026)

The separate review ledger records **Mark result reviewed** and **Undo
acknowledgement** for native-work and scheduled-research reports. It binds the
exact immutable report and fresh source context, with version checks and stable
retry receipts. Historical/stale reports require an explicit warning. Undo adds
a revocation; it does not erase history. Original scheduled report results remain
unchanged, and old retry receipts never replace a fresh current-status read.

This is local authenticated UI provenance labelled **Reviewed in CRM**, not a
verified named human, quality decision, host success, task completion, note
application or permission to rerun work. No agent review tool was added: the
registered catalog remains **83 tools**. Source freshness stays independent.
Native `review_status` now describes acknowledgement rather than substituting
`stale_source_task`; consumers retain `source_task_current` and current version/
status fields for freshness. Native queue counts omit acknowledged results from
awaiting-review flags while retaining other risks. Scheduled history is separate.

Independent database acceptance passed **1,504 mixed checks**, with two existing
not-applicable Contact-archive skips and no failures/errors. Focused coverage was
**185 passes: 104 local/SQLite/API/export/recovery/compiler checks and 81 actual
PostgreSQL cases**. All 1,319 prior mixed regressions passed again. The server was
PostgreSQL 17.11 ARM64 with Python 3.12.13, SQLAlchemy 2.1.8 and psycopg 3.3.8.
All four initial/final tmpfs-only, loopback-bound containers were removed and
verified absent. All 290 frozen source hashes matched the archive plus reviewed
two-file test correction. The aggregate is not exclusively PostgreSQL-backed.
Concurrency evidence is same-process threads, not cross-process stress testing.

The initial three PostgreSQL failures were in test setup: an unqualified raw
ALTER TABLE could not find the isolated-schema table, so the intended malformed
schema rejection was never reached. The reviewed test-only correction uses the
actual connection schema and dialect identifier quoting, without changing search
paths. One compiler test contains three SQLite/PostgreSQL/quoted-schema assertions;
it counts as one test, not three. Runtime bytes were unchanged to obtain the pass.

The final local aggregate passed **1,865 Python tests with 834 optional skips**,
two known dependency warnings, and all **50 scrubbed runner commands**: 13
generators, full Python and 36 JavaScript/React commands including preflight.
Independent reviews and real React 19.3 normal/StrictMode tests verified both
report families, source warnings, undo, exact uncertain retries, late receipts
after remount, shared locks, old receipt replay after undo, malformed contexts,
failed refresh, scope/connection ABA and disposed clients. Actual synthetic
SQLite fixtures exercise cancelled/superseded native reports and both research
targets through the JavaScript validator and mounted component.

Review found and fixed historical generation binding (mutable cancelled
assignment generation versus frozen report generation), stale-report and late-
receipt coverage refresh, hidden current-source warnings and impossible archived
target contexts. The backend also uses the same transaction for authoritative
workspace/source checks and batch-loads review projections. Export validates
ledger/receipt identity and sequencing; recovery quarantines review rows with
their source assignments. This does not revive review or schedule authority.

### Current genuine-host regression

Official host `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` passed **six registry/
Company/Event workflow checks** (two seams plus four actual isolation-mode cases),
then **three scheduled due-run checks** (one seam plus both actual modes). Each
due run made eight deterministic loopback requests and completed. Cleanup
verified zero jobs and stopped scheduler, plugin host and endpoint, with no
remaining processes/listeners/sockets or forbidden audit events. All six copied
scheduled backends matched SHA256
`2a2008d640d4d581ddb7f616d4ef5b2cb1398f02baeb0a02b674debd7d4f62ab`;
native API SHA256 was `391760a78a8ef31ec9ed926e49c7062e01076c94c2ce81c77f7ea36545e05707`.
The pinned test/harness/guard sources were unchanged.

These are existing actual-host regression paths, not physical acknowledgement
UI or live research: their model/source packets were synthetic and `web_search`
was absent. Separate **real keyless provider** verification through normal host
plugin discovery and the web-search callable passed in a disposable home; see
[exact provider setup, result and limits](PUBLIC_RESEARCH_SETUP.md). Neither proof
is a combined live-model research workflow in the intended review profile.

Final documentation and two JavaScript test updates are reviewed separately
from the corrected PostgreSQL snapshot; backend and UI runtime bytes are unchanged.
Current installed-window acceptance, real-profile model research,
operational restart/live cutover and general security certification remain open.
Exact-head hosted CI passed on published
[`73a7f611af1941e636d4496424d9420f25187564`](https://github.com/gptnius/hermes-crm/commit/73a7f611af1941e636d4496424d9420f25187564):
**2,675 Python tests passed, 24 skipped**, with four known warnings; all 13
generators and 36 JavaScript/React commands passed. The
[verified run](https://github.com/gptnius/hermes-crm/actions/runs/42555603291)
used PostgreSQL 16.15 x86_64 with explicit loopback-only port mapping and
successful container teardown. The pinned actions' Node 20-to-24 annotation
was nonblocking. This is not live-provider, installed-app or visual acceptance.
See [the UI workflow](REPORT_REVIEW_UI.md) and [ledger/retention plan](REPORT_REVIEW_PLAN.md).

### Isolated native-component pixel check

On the same public `73a7f61` tree, **60 offscreen Mac renders** covered native
report acknowledgement, scheduled-report acknowledgement and the scheduled
research form. Each component had normal, long, stale, unknown and error states
at 360px and 1100px in light/dark themes. The actual component modules,
production CSS and production wordmark were used with synthetic in-memory
clients, not a live Hermes gateway or customer records.

Every case recorded Chromium sandboxing enabled, Node integration disabled,
context isolation enabled, a secure context, a hidden window, zero external
requests recorded by the browser-session interceptor and zero measured
right-edge overflow. Electron app activation was
prohibited. Representative screenshots across all states, widths and themes
were visually inspected with no blocking defect; not every screenshot received
individual inspection. Long unbroken text wrapped. Confirmation heading focus
and Cancel returning to **Mark result reviewed** passed all eight normal report
combinations. Report buttons were at least 44px; research buttons used the
approved 36px desktop-pointer styling. Touch behavior was not emulated.

Versions were Electron 44.9.3, Chromium 152.0.7977.167, React/ReactDOM 19.3.0 and
esbuild 0.28.2. The first harness used a non-secure data origin and could not
reach the uncertain-write state because `crypto.randomUUID` was unavailable.
The final run used an offline secure custom scheme with external requests
denied; no CRM source change or sandbox relaxation was made. The white canvas
below short dark panels was the standalone harness background, not a component
surface. Research assignment history was empty in the form fixture; populated
scheduled-report acknowledgement was tested separately.

The renderer exited and its synthetic profile/cache directories were removed.
The public checkout was unchanged before/after, and no existing app, window,
profile, provider or credential was used. This is component-pixel verification,
not installed-host integration, full keyboard traversal, OS focus behavior,
screen-reader or full accessibility acceptance. The
[sanitized derived measurement record](native-panel-check/summary.json) includes
case counts, source/harness hashes and explicit fixture limits, without private
paths, screenshots or raw browser state.

## Task-linked scheduled public research (November 9, 2026)

This additive mode registers ten new tools (**83 total**) while retaining the
existing internal-analysis assignment inventory. A reviewed intent binds an open
Task/version, accountable human owner and current Contact/Company/version to a
public question and future run time. Native controls save intent and prepare a
request for explicit Copy/Paste/Review/Send in the genuine Hermes chat. Saving
or copying does not schedule work. The host uses paused-create/bind/resume;
unknown outcomes remain distinct and do not create replacement jobs.

The corrected full local run passed **1,761 Python tests with 753 optional
skips** and two known dependency warnings. All **48 scrubbed runner commands**
passed: 12 generator checks, the full Python suite and 35 JavaScript/React
commands including the required React version preflight. Native component tests
cover exact scoped save/retry, delayed receipts across Close/remount, malformed
nested history, stale profile/task/target, DST inputs, explicit preview/copy and
pagination. They are not physical Desktop or accessibility acceptance.

### Independent PostgreSQL and mixed regression checks

The final corrected snapshot passed **1,319 mixed checks**, with two explicit
not-applicable Contact-archive skips and no failures/errors. Focused coverage
was **307 passes**: 269 local/SQLite/adapter/guard/protocol cases and **38 actual
PostgreSQL cases**. All 1,012 prior mixed regressions passed again on that same
snapshot. Do not interpret the aggregate as exclusively PostgreSQL-backed.
The actual server was PostgreSQL 17.11 ARM64, with Python 3.12.13, SQLAlchemy
2.1.8 and psycopg 3.3.8, in fresh tmpfs-only loopback-bound containers. All four
initial/final owned containers were independently confirmed absent afterward.
All 273 frozen source hashes matched the archive plus reviewed two-file test delta.

The first PostgreSQL attempt stopped in fixture setup because its random schema
name exceeded the existing domain limit. The reviewed test-only correction uses
a shorter prefix and adds a regression against the actual validation rule; no
runtime code changed to obtain the pass. Earlier errors are not successful
PostgreSQL execution. The final cases cover real JSON filtering/pagination,
schema errors, source-version gates, rollback, same-process thread concurrency,
completed-inactive cancellation and PostgreSQL export to fresh SQLite quarantine.
No cross-process concurrency or live user database is claimed.

The scheduled-research public commit `88192fb600fb9b371005abf83bcbbbfc8544660f`
also passed [Actions run 42551678955](https://github.com/gptnius/hermes-crm/actions/runs/42551678955):
**2,490 Python passes, 24 skips**, four known warnings, all 12 generators and 35
JavaScript/React commands. PostgreSQL 16.15 x86_64 used the verified explicit
loopback mapping and was removed successfully. This evidence applies to that
exact prior commit, not the later acknowledgement increment above.

### Genuine pinned-host checks

On official source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, using the
separately prepared source-pinned Python 3.14.9 runtime, the final registry and
Company/Event workflow run passed **six checks**: two harness seams and four
actual cases covering both `in_process` and `host` isolation. The catalog has
83 registered tools. The actual resolver test verifies both research presets
and `no_mcp` with a configured synthetic MCP entry, without launching that entry.
No provider or model call is part of this registry test.

The due-run fixture separately passed **three checks**: its seam and both
isolation-mode cases through real scheduling, canonical admission, AIAgent,
streaming tool dispatch and CRM persistence. Each mode made eight deterministic
loopback model requests at or after the due instant, saved a supplied synthetic
source packet, a pending note proposal and an authenticated report. Ordinary
notes were unchanged and the business Task remained open. Extra ticks did not
produce a duplicate; a separately cancelled future assignment did not execute.
The four assignment-bound run tools were available and ten unrelated/write/
browser/terminal/delegation/scheduling tools were unavailable. Cleanup verified
no remaining jobs, fixture processes, endpoints, sockets or forbidden audit events.

**No public search was performed:** `web_search` was absent in these intentionally
credential-free profiles. The source packet and model responses were synthetic.
These results establish scheduler/identity/data wiring, not search-provider
readiness, reasoning quality, prompt-injection resistance, visible delivery or
crash/restart recovery. See the [sanitized run summary](native-work-test/scheduled-research-result-summary.json).

The new-mode-only guard permits one exact read-only Git version query from the
pinned version module in the owned checkout. It retains source/fingerprint and
caller/argument/cwd checks; the older native fixture is unchanged. Earlier failed
fixture attempts are not passes: one encountered that version query; another
exceeded the host discovery batch limits. Reviewed corrections added the narrow
probe and split synthetic discovery into supported batches, without changing
production runtime or broadening general subprocess/network/credential access.

Human report-review disposition receipts remain unimplemented. A report is an
agent claim, not host-success evidence or Task completion. Evidence/proposal
writes are source/version bound; note application remains a separate reviewed
action. Exports preserve the new family, and offline recovery quarantines its
runtime rows without restoring schedule authority. A complete live-provider
research workflow and current native visual acceptance remain release gates.
See [implemented contract](SCHEDULED_RESEARCH_PLAN.md) and [native workflow](SCHEDULED_RESEARCH_UI.md).

## Offline fresh-target CRM content restore (November 9, 2026)

The offline `python -m hermes_crm.recovery` command restores a downloaded native
encrypted CRM export into a **new SQLite directory**, using explicit original
workspace/profile and retained export/notes keyrings. It validates authentication,
known schema/type/unique/FK contracts and note context before creating output.
Recovered services support content reads and fresh version-checked writes; safe
local retry receipts are preserved. Source schedule fields and runtime/provider
rows remain in inspection-only `recovery_*` tables. Operational tasks have their
schedule binding cleared and changed tasks receive a new version; native-work,
experimental execution and Gmail runtime tables start empty.

Focused command (set an explicit disposable PostgreSQL URL for portability):

```sh
python -m pytest -q tests/test_recovery.py tests/test_recovery_postgres.py tests/test_protection.py
```

The initial local run passed **56 cases** with 13 PostgreSQL cases skipped.
The independently verified frozen snapshot then passed **69 focused checks**:
27 SQLite recovery, 13 actual PostgreSQL-source → SQLite-destination recovery,
and 29 local protection cases, with no failures or skips. PostgreSQL was 17.11
ARM64 in a fresh tmpfs-only, loopback-bound disposable container. The subsequent
943 prior mixed regression checks also passed: **1,012 mixed checks total**, not
1,012 exclusively PostgreSQL-backed cases. Both owned containers were removed
and all 253 frozen source hashes remained unchanged.

Reproduce the PostgreSQL source contracts using an owned disposable database:

```sh
HERMES_CRM_TEST_POSTGRES_URL=postgresql+psycopg://localhost/disposable_crm python -m pytest -q tests/test_recovery_postgres.py
```

Every PostgreSQL case creates and drops its own random schema. No source host,
provider, key provisioning or active app is used. Those cases reuse contracts for
protected notes and rotated retained keys, local receipt replay, relationships,
reports/research and fresh writes, runtime quarantine, six authentication
failures, invalid references, no overwrite and interrupted output. An additional
ownership/customization case verifies policy and schema receipts, typed values,
deals, current-version writes and unchanged source rows. This case passed on
both its actual PostgreSQL source and a separate synthetic SQLite smoke run.
The base SQLite cases additionally cover malformed authenticated snapshots, CLI
input sanitization and path punctuation without redirecting the database.

The full local suite passed **1,489 tests with 709 optional skips** and two
known dependency warnings. All **46 scrubbed runner commands** passed, including
11 generators and the existing JavaScript/React suites. These local checks do
not execute actual Hermes, live providers, physical dialogs or production cutover.

The published recovery commit `bf48b86abc40a6bfc5830ed1d6e0fe68e8d818c5`
also passed [Actions run 42548143056](https://github.com/gptnius/hermes-crm/actions/runs/42548143056):
**2,180 Python tests passed, 18 skipped**, four known warnings, all 11 generators
and 34 JavaScript/React commands passed. PostgreSQL was 16.15 x86_64 with the
verified loopback port mapping and successful container teardown. This hosted
result applies only to that exact recovery commit, not this later research increment.

The artifact is usable fresh-target CRM content recovery, not a full-host backup,
in-place restore, rebinding, PostgreSQL destination or production cutover. Ordinary
recovered notes/fields are plaintext; protected notes remain encrypted and require
the original exact scope and retained keys. Export v1 lacks a separately
authenticated full-table inventory: a wholly omitted optional family cannot be
distinguished from one never initialized. No claim of complete installation
backup follows from a successful restore. Operators must stop/fence old jobs,
dispatches and writes and reconcile uncertain external outcomes before live
cutover under the preserved workspace identity. Source host jobs are neither
exported nor cancelled. Real-data, real-host disaster and live-cutover drills
remain **unverified**. See [procedure and boundaries](BACKUP_RESTORE.md).

## Credential-free CI definition and local runner (November 9, 2026)

The workflow uses read-only repository permissions, nonpersistent checkout
credentials, SHA-pinned official actions, no secrets/OIDC/deployments and a
fresh PostgreSQL 16 job service. It does not use `pull_request_target`. The runner
constructs a fresh HOME/HERMES_HOME and a narrow child environment rather than
inheriting provider/database settings, source/E2E flags or Node/Python preloads.
This is environment hygiene, not an OS/network sandbox for untrusted code.

Independent review found and fixed a PostgreSQL URL validation bypass: a query
parameter could override a loopback URL's host. The runner now accepts a narrow
unambiguous loopback grammar and rejects query/fragment components, escapes,
whitespace and invalid ports before subprocess execution. **36 local runner
regressions passed**, including redacted validation errors, environment canaries,
child failure and timeout handling. No database connection was needed to verify
this fix; accepted forms were compared with SQLAlchemy connection arguments.

The local all-suite runner completed **46 commands**: 11 generator checks, full
pytest, a required React/react-test-renderer 19.3.0 version check, 21 executable
module suites and 12 CommonJS suites. The initial working-tree aggregate was
1,425 Python passes/696 optional skips; after the runner regressions were added,
the full scrubbed Python rerun passed **1,461 tests with 696 optional skips** and
two known dependency warnings. These counts include the detail-reader increment.

The exact-host-only JavaScript entrypoint, physical Playwright layout fixture and
artifact-only/helper entrypoints are explicitly excluded. Python host/model E2E
and optional JS source checks retain their skip/exclusion reasons. The workflow
passes its own disposable PostgreSQL URL, but that PostgreSQL 16 service and
GitHub-hosted execution have **not been verified by these local runs**. Earlier
PostgreSQL 17.11 checks and genuine-host evidence above/below retain their own
scope. Inspect the actual Actions result for the exact public commit before
calling CI green. This configuration neither changes branch protection nor
publishes/deploys software. See [CI coverage and reproduction](CI.md).

### Independently verified hosted run

The exact public CI commit `5bf345f23e58abd746b5897863458f026ff80435`
passed [Actions run 42547059580](https://github.com/gptnius/hermes-crm/actions/runs/42547059580).
Actual hosted Python results: **2,140 passed, 18 skipped**, four known warnings.
All 11 generator commands, the Python command and 34 JavaScript/React commands
passed. Docker output verified the explicit `127.0.0.1:5432:5432` mapping;
the service ran PostgreSQL **16.15 x86_64** and container teardown succeeded.
This result is for that exact commit, not later untested changes or live-host gates.
The runner emitted a nonblocking compatibility annotation because the pinned
actions target Node 20 and were run on Node 24; action-version maintenance is a
separate follow-up, not a failed check or reason to grant more permissions.

## Company/Event detail reads and actual-host workflow (November 9, 2026)

This increment uses public baseline
`7363fce95965cd4c16a69ae86080a33b173501c7` (tree
`2ccd24bd5012ca135f3050a45ac86a614d093798`). The existing `crm_record_fields`
reader now supports exact Company notes and Event notes/outcome summaries,
returning their current version. Default summaries, protected-note boundaries,
registered tool count, frozen scheduler toolsets and update/version checks are
unchanged. Schema validation, workspace/profile resolution and the row read share
one read-only snapshot; absent stores remain uninitialized.

The final cloud suite for this increment passed **1,425 Python tests**, with
**696 optional cases skipped** and two known dependency warnings. The separately
developed CI-runner tests were excluded from that count because they are not part
of this package. Runtime, test and manifest bytes match the frozen snapshot used
for PostgreSQL and actual-host verification below. This increment changes no
native UI source.

Independent review and disposable PostgreSQL 17.11 ARM64 verification passed
**943 mixed checks with no failures/skips**: 62 focused checks (47 local detail
cases, 14 PostgreSQL cases and one harness-fingerprint seam) plus all 881 prior
mixed cases. Six additional local semantic/HTTP-to-JavaScript/catalog checks
passed separately. Do not describe these as 943 exclusively PostgreSQL-backed
tests. Both owned fresh tmpfs-only loopback containers were removed and confirmed
absent; all frozen source hashes were verified.

A new genuine-host synthetic workflow passed in **both in-process and hosted
plugin modes** against exact Hermes source
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. It uses real discovery/registry dispatch,
not adapter stubs, to verify the 73 advertised names, explicit Company/Contact
creation, scoped current-note reads, preservation/stale-write rejection, supplied
research evidence and note proposal, local Event/owned task and self-reported outcome. Registered tools are not proof that all are enabled in any given
conversation. The fingerprint seam was rerun with these two modes; it is already
counted above and is not an extra new pass.

The first host attempts stopped before discovery because the test body imported
an unavailable YAML parser. A reviewed two-line test-only correction uses the
host's installed safe ruamel.yaml loader. The guard, isolated environment, harness
and workflow assertions were unchanged. Final host runs used Python 3.14.9 with
SQLAlchemy 2.1.8 and ruamel.yaml 0.18.16. All initial/final owned guarded processes
exited; no sockets, jobs files or forbidden-action logs remained.

This is real host tool/data integration with synthetic records. It does not run
a model, fetch the supplied example URL, apply the research proposal, invite
anyone, send a message, schedule the task or validate physical UI behavior. No
user app/profile, credentials, grants or provider settings changed. A live public
research/model/UI workflow and real-host restore/cutover drill remain distinct release gates
in the [readiness plan](RELEASE_READINESS.md).

## Interactive assistance guidance (November 9, 2026)

This focused increment uses public baseline
`f58f7a3f1555599f8a1db2ddabf8bf01b94ac52f` (tree
`6c6f4d135e36bcd15354bdc7bf17bba75f42b72e`). It removes an unnecessary blanket
restriction in the interactive **Ask for help now** preview and makes selected
tool descriptions point to available research/detail routes. It preserves direct
user review before sending, normal host approvals and exact request scope.
It does not change scheduled prompts/toolsets, record/version checks, schemas,
credentials, retries or actual dispatch behavior.

Cloud verification passed **1,377 Python tests**, with **680 optional skips** and
two known dependency warnings. Three new registration/guidance contracts check
research routes, explicit scheduling intent, preserved approval wording, exact
registered/manifest tool inventory and unchanged frozen scheduled scope. The
registered inventory is 73; the stale integration-guide count was corrected.
Registration is not proof that a tool is enabled in a particular conversation.
Actual React assignment fixtures cover interactive research, reviewed external
sending, scheduling and task-completion requests without invoking an action.
They assert the specific missing-tool/account/permission guidance, unchanged
future-mode limits, no native composer access and no automatic submission.

The **22 non-render module entrypoints** completed: 21 passing suites and one
exact-host-source skip. Two additional optional source assertions skipped.
**12 supported CommonJS entrypoints**, **11 generators**, syntax and whitespace
checks passed. Independent source review found no blocking issue. These are
prompt/description and component behavior tests, not evidence of live model
obedience, current-host execution or external sending. No new PostgreSQL run was
needed for description-only Python changes; prior backend results retain their
original scope. No user app/profile or permission was changed. No green hosted
CI or production-readiness claim is made. See [agent assistance](AGENT_ASSISTANCE.md).

## Sourced evidence and reviewed note proposals (November 8, 2026)

This increment uses public ownership baseline
`aed3f70e6ec5b55fe9192f856b520d1f241a26cf` (tree
`0d7e4759978c6012f94770da032554a7f14493f6`). It stores supplied source claims
and separate hypotheses against one exact Contact or Company, then prepares an
append-only Notes proposal for explicit review. It does not fetch sources, run
research, send messages, grant access or widen scheduled-agent toolsets. Source
URLs, observation times and actor-channel labels are not verified authorship or
proof of execution. Existing authorized record-editing tools remain available;
this is not a global human-only write boundary.

Final cloud Python aggregate: **1,374 passed, 680 optional cases skipped**, with
two known dependency warnings. Coverage includes strict schema and packet
validation, source/time grammar, workspace isolation, non-initializing reads,
archive/restore staleness, exact Notes append, version/hash checks, atomic rollback,
same-key historical replay and encrypted-export inclusion. Two local SQLite cases
included in this aggregate verify that preparing a proposal leaves last-edit unchanged and
applying it changes last-edit without changing last logged contact, open follow-up
counts or the linked task's status/version. Same-key replay preserves the report
metrics. These tests do not establish a new agent-run review or task-completion
workflow.

Disposable PostgreSQL 17.11 ARM64 verification passed **881 mixed checks with
zero failures or skips** on the frozen backend plus the reviewed timestamp delta:
**75 focused cases (57 local and 18 PostgreSQL)** and all 806 prior mixed
regressions. A separate local test fed actual in-process FastAPI SQLite responses
to the shipped native and standalone JavaScript validators and also passed. These
are not 881 exclusively PostgreSQL-backed cases. All four owned fresh tmpfs-only
loopback containers were removed and independently confirmed absent. Concurrency
coverage uses same-process threads, not separate processes. Managed Supabase and
hosted-service behavior remain unverified.

Independent backend review found and corrected missing stored-packet validation
on list/replay/export paths and malformed success-response handling. Timestamp
syntax now agrees across Python and JavaScript before this unreleased increment
ships, retaining accepted offsets and precision rather than normalizing evidence
silently. URL restrictions reject malformed values and common credential-bearing
parameters, but are not exhaustive secret detection or proof that a URL is public
or safe. Digests are consistency checks, not authenticated tamper protection.

Independent native and standalone reviews covered malformed packets/receipts,
dirty drafts, pagination, exact append/hash previews, rejected and uncertain
writes, duplicate clicks, historical receipt recovery, late responses and
workspace/profile changes. Fixed defects included retained response extras,
committed drafts that could be resubmitted, inaccessible Previous after a failed
next page, and invalid empty proposal identifiers. Unknown requests retain their
original key/body and require an explicit check or retry; no automatic write is
performed. UI recovery does not persist full before/after Notes snapshots.

The **22 non-render JavaScript module entrypoints** completed: 21 ran passing
suites, while the exact-host work-command contract skipped because pinned source
was unavailable. Two other optional assertions (chat pinned-source contract and
Hermes CSS compatibility) also skipped. **12 supported CommonJS entrypoints**,
**11 generator checks**, JavaScript syntax and whitespace checks passed, including
the existing 25 bridge checks. React tests used actual React/react-test-renderer
19.3.0 with synthetic SDK transports. The HTTP-to-JavaScript bridge exercises real
application routes with synthetic records, not live Hermes authentication or a
model/provider. A separate Playwright layout fixture was not rerun because the
browser executable was absent; no bypass or installation was attempted.

Physical native/standalone visual inspection, light/dark/responsive review,
assistive-technology behavior and live public-source research remain **unverified
for this increment**. The user's running application, records, profiles and
credentials were not changed. Research content remains ordinary plaintext in the
live database, and host conversations/tool logs may retain independent copies.
Encrypted content export includes research tables. The later offline content
restore increment above supersedes this increment's lack of restore coverage;
it remains distinct from a full backup or live-host recovery drill. General attachments, broader research
execution, outbound email and agent-result review closure remain separate work.
See [research evidence and boundaries](RESEARCH_EVIDENCE.md).

## Optional task ownership and policy (November 8, 2026)

The ownership increment uses public planning baseline
`1ba38a0b4a732dae840e97b269d42502b893594b` (tree
`1caeda8e419f2c573d20b4fc8dcfda2902e6fd9a`). It adds human task-accountability
labels and an explicitly configured workspace policy, not user accounts or
execution permissions. No personal policy/default, backfill, real task, native
application, provider, key or credential was changed during these tests.

Final cloud Python aggregate: **1,314 passed, 662 optional cases skipped**, with
two known dependency warnings. New backend contracts cover optional and required
owners, explicit defaults, stale policy/task versions, legacy completion rules,
Event task enforcement, receipt replay, preserved legacy rows/receipts, rollback,
profile-scoped reads/exports and unchanged assignment snapshots. Reads remain
non-initializing. The policy deliberately excludes scheduler bookkeeping and
relationship-only maintenance; older binaries/direct SQL are not constrained.

Disposable PostgreSQL 17.11 ARM64 verification passed **806 mixed checks with
zero failures or skips** on the frozen backend plus the reviewed two-file test
delta. The focused 39 comprised **22 SQLite contracts, two local API/tool adapter
cases and 15 PostgreSQL cases**. The remaining 767 included prior portability
coverage and SQLite/compiler checks; these are not 806 exclusively PostgreSQL-
backed cases. Two initial test failures were corrected without runtime changes:
the legacy task projection now expects nullable owner fields while preserving
exact raw-row/receipt assertions, and activity-query detection checks the compiled
Table identity instead of matching a schema-name substring. All four owned
fresh tmpfs-only loopback containers were removed and independently confirmed
absent. This does not establish managed Supabase, hosted-service or cross-process
concurrency behavior.

Independent native and standalone reviews reproduced and corrected policy-route,
malformed-policy, rejected-draft and receipt-validation defects. Retained unknown
requests use the original fields/key. Definitive rejection keeps a recoverable
draft; fresh task/policy review and explicit corrected Save are required. Tests
cover dismissal/navigation, changed scope, no automatic resubmission and strict
receipt checks, including exact version, explicit owner clearing and microsecond-
equivalent timestamps. Actual in-process FastAPI SQLite receipts were fed to the
shipped native and standalone JavaScript validators. These are real application
route tests with synthetic records, not live Hermes authentication/model tests.

The **21 non-render JavaScript module entrypoints** completed: 20 ran passing
suites, while the exact-host work-command contract skipped because pinned source
was unavailable. Two other optional assertions (chat pinned-source contract and
Hermes CSS compatibility) also skipped. **11 supported CommonJS entrypoints**,
**ten generator checks**, JavaScript syntax and whitespace checks passed. React
tests used actual React/react-test-renderer 19.3.0 with synthetic SDK transports.
Existing bridge, relationship, report, protection, transfer and Workbench
contracts were included; no new live-host verification is claimed. A separate
Playwright layout fixture could not
launch because the browser executable was absent; that layout test did not pass
and no bypass or browser installation was attempted.

Physical native task-owner forms, visual light/dark/responsive inspection and
assistive-technology behavior remain **unverified for this increment**. No live
app activation or user-policy setting is implied. In-app draft recovery is not a
durable offline draft store; task API/tool keys remain optional, and unkeyed
uncertain writes have no receipt-replay guarantee. Encrypted content export
includes the four ownership tables. Later offline content restore coverage is
recorded above; neither increment establishes a complete backup or live cutover. See [task ownership and boundaries](TASK_OWNERSHIP.md).

## Assignment evidence navigation and workflow audit

The follow-up audit used public baseline
`4179d507d0710ff7abb3a3e00f099622f39cd30b`. A focused synthetic backend slice
passed **401 tests with 8 optional cases skipped**. A separate combined SQLite
workflow exercised explicit Company/Contact/Event/task links, saved future
assignment, schedule/check/report, Complete/Reopen, rejection of the old task
version, completed one-shot inactivity and future-schedule cancellation. Its
scheduler/model interfaces were doubles, not a new live-host execution test.
No new backend state-machine defect was reproduced.

Two native usability defects were reproduced and fixed: later-page loading/error
hid Previous in the three evidence lists, and opening an exact older assignment
from coverage omitted its report when outside the first history page. Shared
read-only evidence now includes the selected result without changing review state
or task completion. Known current-task version/status conflicts conservatively
mark older source/report evidence stale; backend stale/unknown evidence is never
upgraded. Local operation history also distinguishes loading from previously
observed rows. Independent actual-React review cleared full-route drillthrough,
Close, pagination recovery, late responses, profile changes, conservative labels
and zero new write/command calls.

Final cloud aggregate: **1,288 Python tests passed, 647 optional cases skipped**,
with two known dependency warnings. Applicable native React/VM, standalone UI and
contextual recovery suites, both design contracts, **25 bridge checks**, all
**nine generator checks**, syntax and whitespace checks passed. Pinned-host source
and optional real nanostores assertions were not available in the cloud. Backend
runtime, Python tests and plugin manifest remain byte-identical to the prior
**766-pass mixed PostgreSQL/SQLite snapshot**; no new PostgreSQL run is claimed
for this UI-only increment. Schema, permissions and operation authority are
unchanged.

An isolated Mac Electron fixture rendered the actual native components with
synthetic SDK/endpoints in all **six light/dark and 1280/640/390-pixel cases**.
The older exact report remained visible across successful history pages, long
unbroken text wrapped, and the report end/caveats remained reachable by scrolling.
All three pagers preserved focusable Previous during loading/failure, disabled
unsupported forward navigation and rejected delayed page-two replies after
returning. Pending exact-record reads were suppressed after navigation/profile
changes, and conflicting task observations downgraded stale report labels.

**12 of 60 captured screenshots were actually inspected**, spanning every
width/theme combination. No unintended clipping or horizontal page overflow was
observed. Recorded renderer-error, network-attempt and mutation counts were zero;
all three owned Electron launches exited. This is DOM focus/click and sampled
pixel verification, not installed-host, OS keyboard or assistive-technology QA.
The operation pager fixture used empty rows with a positive total: operation-row
recovery contents were not rendered in this check. The rendered task conflict
combined changed version/status; the separate cases are React fixture coverage,
not independently rendered cases. No live scheduler/model run was added.

No active app, real profile, credential, provider, message or production record
was accessed. The durable report-review policy, Event-only coverage definition,
immediate execution and research/mailbox permission decisions remain separate
in the [workflow plan](WORKFLOW_REVIEW.md).

## Contextual contact and Event creation

The new optional Primary Company selector creates a contact and its exact Company
link in one transaction. It does not infer identity from names, overwrite legacy
company text, merge records or alter the existing contact-create receipt format.
Company, Contact and opportunity shortcuts prefill only the explicitly selected
source identity. The new agent tool shares that service in `crm_company_write`;
no scheduled-agent toolset gains access.

Independent backend and interface reviews cleared the implementation. New
contracts cover exact Company/version checks, archives, scope, custom values,
rollback, unchanged historical receipts, same-key replay and conflicting retries.
Interface checks cover paged duplicate Company names, explicit refresh/review of
changed versions, source-only Event prefills and fresh detail reads. Uncertain
requests retain their exact original payload, key and source after navigating to
a different record; a definitive retry rejection restores the original draft
without automatically submitting a replacement. Original list context also
remains distinct from a subsequently opened Company.

Disposable PostgreSQL 17.11 ARM64 verification passed **766 mixed checks with
zero failures or skips** on the frozen backend snapshot: **19 new PostgreSQL and
19 new SQLite/local cases**, plus all 728 earlier mixed regressions. This is not
766 exclusively PostgreSQL-backed tests. Both fresh memory-backed, loopback-only
containers were removed and independently confirmed absent; all source hashes
remained unchanged. Concurrency fixtures use threads in one process, not multiple
independent PostgreSQL client processes. Known dependency and intentional
malformed-primary-key warnings remain disclosed.

Cloud aggregate verification: **1,288 Python cases passed, 647 optional cases
skipped**, with two known dependency warnings. Native React/VM suites, both
design contracts, standalone contextual creation/retry/recovery and prior UI/time
fixtures, **25 bridge checks**, JavaScript syntax and all **nine generator
checks** passed. Pinned-host source and optional real nanostores assertions were
unavailable in the cloud and are not counted as new host verification. Python
runtime/tests and the plugin manifest are byte-identical to the frozen
PostgreSQL snapshot.

An isolated Mac Electron fixture rendered the actual native and standalone
components with synthetic SDK/endpoints in light/dark themes at 1280, 640 and
390 pixels. **378 renderer assertions passed**: 196 native checks and 182 final
standalone rerun checks. This includes source-only prefills, paged Company
selection, explicit stale-version review, exact custom values, dirty cancellation,
confirmed child/parent navigation, and original Company/list recovery after
uncertain or rejected saves. Native stale-profile completion was also checked.

Rendering found a retained standalone retry that could become invisible after
closing later details without refreshing the list. A scoped notice-slot update
fixed it without another request, list replacement or automatic retry. The fix
and regression passed independent review. Final standalone Contact/Event recovery
covered both original Company and list sources, successful replay and definitive
conflict restoration without extra section navigation; all six standalone
responsive/theme cases were repeated. Native source was unchanged and was not
rerun after this standalone-only patch. Nine earlier standalone parent-navigation
and archived-control assertions were not repeated after the patch.

**27 distinct screenshots were actually inspected** out of 151 retained captures:
10 final patched standalone, 9 unchanged native and 8 earlier standalone images.
The retained total includes exploratory and superseded captures. No unintended
control clipping, overlap or horizontal page overflow was observed in inspected
images; responsive DOM checks also confirmed page width. Long dialogs require
scrolling and some placeholders truncate normally. Recorded renderer-error and
blocked-network-request arrays were empty; intended synthetic transport failures
were used for recovery tests. Nonfatal Electron deprecation/resource-extension
warnings were recorded. All owned launch sessions exited.

This is sampled pixel and DOM-event verification, not installed-host or OS
keyboard/mouse testing. Synthetic fixtures do not establish full accessibility,
physical host operation, real provider behavior or production performance.

No active app, real profile, credential, provider, mailbox, external message or
production record was involved. The new operation adds no research execution,
invitation, calendar synchronization or agent scheduling. See
[the contract and its remaining limits](CONTEXTUAL_CREATION.md).

## Workflow continuity and validation fixes

This increment adds native linked-record Back navigation, confirmed child-record
continuity after saving, direct task Complete/Reopen, in-app dirty-form guards,
and less technical Company/Event details. Relationship list filters and bounded
page offsets survive child navigation and native chat relocation. Records are
read again by exact identity; retained navigation state is not write authority.
The final navigation review also verified that retained Chat callbacks cannot
relocate CRM while a Company/Event form is dirty.

Native and standalone Event forms use wall-time controls with an explicit IANA
zone and resolved-instant preview. They reject DST gaps and require a choice for
folds. New/changed wall times are limited to 1900–2100; unchanged saved originals
outside that range keep exact precision during unrelated edits. In-app
Keep editing/Discard changes is not persistent draft recovery after reload,
host closure or profile changes.

Backend fixes reject new Event associations to archived Companies while retaining
existing context and historical retry receipts, and convert bounded UTC overflow
into validation errors. Native encrypted-export queries now filter assignments,
events, reports and command operations consistently by current scope/parent.
The export reproduction used mixed/copied rows in one datastore; it did not access
another profile's database or selected PostgreSQL schema. Shared tables and encryption format are
unchanged; this is not a new general access-control or restore claim.

Cloud Python verification: **1,269 passed, 628 optional cases skipped**, with two
known dependency warnings. Independent reviews cleared the backend fixes,
time controls and navigation. Native React/VM suites, standalone/time fixtures,
design contracts, **25 bridge checks** and all **nine generator checks** passed.
Exact pinned-host source assertions were unavailable in the cloud.

Disposable PostgreSQL 17.11 ARM64 verification passed **728 mixed checks with
zero failures or skips** on the same 200-file source snapshot. The new 44 cases
comprise 3 PostgreSQL/9 local integrity checks and 16 PostgreSQL/16 SQLite export
scope checks; all 684 earlier mixed portability cases also passed. These totals
are not exclusively PostgreSQL-backed. Both fresh memory-backed, loopback-only
containers were removed and independently confirmed absent. Dependency and
intentional malformed-primary-key fixture warnings were recorded, not hidden.

An isolated Mac Electron fixture rendered the actual CRMRoot and standalone
components with synthetic endpoints/SDK at 1280, 640 and 390 pixels in both
themes. **60 native + 36 standalone workflow assertions**, plus **3 additional
Company-parent chains**, passed. Dirty Company/Event Chat controls and retained
callbacks blocked mock navigation; a positive control worked after discard.
All **138 DOM layout states** had no page overflow. Of 210 captured final-matrix
screenshots, **20 were actually inspected**; this was sampled pixel review,
not inspection of every capture. Two small cosmetic issues were found and
corrected: native Kind selector stretching and touching standalone discard
buttons. The scoped CSS and layout-contract delta passed independent review.
Targeted rerenders covered all 12 renderer/theme/width combinations and **48 DOM
states**: Kind controls measured 44px high, discard buttons had a 12px gap, and
hidden controls stayed hidden. Of 24 new captures, **8 were pixel-inspected**,
with no observed clipping, overlap or page overflow. No console errors or network
attempts occurred, and the owned Electron process exited successfully. The full
base workflow matrix was not repeated for this CSS-only delta.

This is isolated component/DOM-event verification, not an installed-host or
OS keyboard/mouse test. Every owned launch exited; global process listing was
unavailable. The active app, real profiles, credentials, providers and real chat
were untouched. The final backend difference from the PostgreSQL snapshot is
one wording-only export docstring correction; executable Python AST is unchanged.

At this historical workflow release, result-review acknowledgement remained a
design. A later [dedicated increment](REPORT_REVIEW_UI.md) implements durable
acknowledgement/undo separately from quality approval.
No mailbox grant, live research task, external communication, active-profile
change or production migration was performed. See the
[workflow findings and remaining decisions](WORKFLOW_REVIEW.md).

## Companies, Events and linked tasks

This increment adds explicit Company identities and primary contact associations,
local Events, and atomic Event-task links. Company names/domains are not merge
keys. Legacy contact company text and old create receipts remain unchanged.
The seven new relationship tables initialize empty on an explicit write, use
workspace/profile scope and reject incompatible, partial or newer schemas.
Legacy table clones used only for foreign-key resolution are not owned or
included as replacement tables in encrypted exports.

Events distinguish Scheduled, Needs rescheduling, Completed and Cancelled.
Completion records a nonfuture, self-reported occurrence and a separate recording
time; it never implies a provider call, attendance, task completion or delivery.
Immutable revisions preserve corrections. Activities includes completed Events
and non-voided Contact Logs, while Record history retains administrative edits.
Task membership discloses current-contact and explicit-Event Company context,
with distinct counts and server pagination rather than silent name matching.

Cloud verification: **1,244 Python tests passed, 609 optional cases skipped**,
with two known dependency warnings. Native React/VM, relationship UI, standalone,
design-contract and **25 bridge checks** passed, as did all **eight generator**
checks, JavaScript syntax and whitespace checks. React/test-renderer was 19.3.0.
Pinned-host-only source assertions and optional real nanostores checks were not
available in the cloud and are not counted as new host verification.

Independent backend and interface review cleared the implementation after fixes
for exact unlink targets/versions, scoped read-only token validation, PostgreSQL
foreign-key target identity, task-context review, stale navigation and shared
pending state. Native and standalone mutation receipts require positive versions
and operation-specific identities. **31 native and 30 standalone malformed or
wrong-target receipt cases** retain the original unknown request/key rather than
silently enabling another mutation. A confirmed unlink no-op retains the task
version. Identical retries preserve the originally reviewed payload.

New contracts cover absent-schema reads, old row/receipt preservation,
duplicate identities, archives, scope isolation, literals in search, more than
500 relationships, report/filter/drilldown reconciliation, explicit-offset DST
and timestamp precision, version conflicts, rollback, no-op replay and encrypted
export scoping. Threaded initialization/replay checks share a process lock;
they do not independently prove cross-process PostgreSQL initialization behavior.

Disposable PostgreSQL 17.11 ARM64 verification passed **684 mixed checks with
zero failures or skips**: **106 focused contracts** and **578 existing
portability regressions**. The focused set includes **22 starter-data guard
cases (11 SQLite, 11 PostgreSQL)** plus **84 relationship cases**. The
relationship set contains 23 local storage cases,
15 PostgreSQL storage cases, 8 SQLite/8 PostgreSQL query cases, 6 SQLite/6
PostgreSQL report cases, 8 local adapter cases and 5 SQLite/5 PostgreSQL core
integration cases. Two report cases on each backend also assert SQL compilation.
This is not a claim that all 684 cases were PostgreSQL-backed. The live checks
include exact foreign-key schema-target rejection and same-process threaded
initialization/replay. The existing regressions also include their disclosed
SQLite/compiler variants.

The final two fresh databases used temporary memory-backed storage and
loopback-only ports; those and the two earlier containers were removed and
independently confirmed absent. All 194 files in the backend-test snapshot
matched the reviewed source ZIP plus guard delta before and after testing.
The UI-only polish delta was verified separately as described below. Dependencies
were Python 3.12.13, SQLAlchemy 2.1.8, psycopg 3.3.8, pytest 9.2.0, Pydantic 2.14.3
and cryptography 50.0.2. Warnings were the known Starlette/httpx/raw-upload
deprecations and the intentional malformed-primary-key fixture warning.

Isolated rendering exercised the full native CRMRoot pane and standalone shell
in light/dark themes at 1280, 640 and 390 pixels. The fixture captured **174
initial views** and **48 targeted rerender views** after a small polish fix;
representative actual pixels were inspected. Measured documents stayed within
the viewport. Eight-item navigation scrolls within its own container at narrow
widths, exposes the final Record history item and responds to DOM clicks.
Standalone Event context links initially ran together; the reviewed fix gives
them 44px-high targets, 16px horizontal gaps and an 8px wrapping gap at 390px.
Legacy-company-text filter labels were also clarified without changing queries.

**Ten synthetic DOM mutation scenarios** passed and were repeated after the UI
delta: Company creation, rescheduling with exact offset/fractional precision,
self-reported completion, associated-task creation and existing-task linking in
both frontends. Four duplicate-name Company selection cases sent the selected
exact second Company ID rather than inferring by name. These fixtures use
in-memory endpoints, sandboxed hidden Electron and blocked HTTP(S), not a live
Hermes backend. They verify rendered interaction wiring, not physical keyboard,
native focus, host authentication or model execution. All five UI delta hashes
and 188 untouched source files were verified; owned renderer processes exited.
The active review app, real records, credentials and providers were untouched.

The final optional-starter-data guard rejects Company-only and Event-only
workspaces, including archived Companies and records under another profile in
the same physical datastore. The shared catalog lock precedes core table locks.
Refusal or invalid relationship schema rolls back the catalog revision and
preserves full table/receipt snapshots. Successful empty seeding does not create
relationship storage or a workspace token. Injected failure retains all-or-nothing
behavior. The 684-check result above includes this reviewed guard and supersedes
the earlier 662-check pre-guard result.

The scheduled assignment lane remains CRM-read/report-only. The new Event/task
links do not grant web research, terminal access, note-writing, attachments or
external communication. Creating a linked task is not proof of assignment,
scheduling or execution. Physical native keyboard/focus behavior, live provider
integration, external calendar invitations and a complete research-to-attachment
workflow remain separate verification and development gates.

## Navigation, contact rows and Upcoming Tasks

The native and standalone navigation now occupies its own row, with 18px text,
52px minimum targets and an underlined active page. Contact rows use alternating
approved surfaces, retained separators and bold blue name links. The dashboard's
Upcoming Tasks section shows the earliest six open tasks, including explicitly
marked overdue work, the current linked contact and a blue exact-record link.

Task records do not have an assignee field, so the UI says **Task assignee: Not
recorded**. Separate saved Hermes work, when present, shows its actual human
owner and stored state. It is not inferred from the current profile, audit actor
or reminder. At most three assignment summaries per displayed task are returned,
with the full history count and explicit unknown/stale states. Counts still scan
that task's history. This read-only summary neither queries nor changes the
scheduler. Assignment instructions/results, notes and custom values are omitted;
agent overview responses retain their prior minimized contract.

Cloud verification on the final code: **1,183 Python tests passed**, **564 optional
cases skipped**, with two known dependency warnings. React/VM, standalone,
routing, both design-contract suites, **25 bridge checks**, seven generator
checks, JavaScript syntax and whitespace checks passed. The fresh cloud fixture
uses React/test-renderer 19.3.0. Exact pinned-host source and optional actual
nanostores fixtures were unavailable, so those source/runtime assertions were
skipped rather than claimed as new host verification.

Independent review found no remaining blocker. It checked malformed summaries,
all saved assignment states, direct-contact precedence and missing-reference
behavior, bounded projections, exact-ID fresh standalone reads, preservation of
notes/custom fields when editing, and late-response/navigation/Escape guards.
Both surfaces fail closed on malformed counts, owners, executors or states.

A separate disposable PostgreSQL 17.11 ARM64 run passed **578 mixed checks**,
with zero failures or skips on the exact 173-file source snapshot. The new
Upcoming Tasks file passed five actual PostgreSQL cases, five SQLite cases and
one local native-API fixture. The total also includes local/compiler report and
activity cases and is not exclusively PostgreSQL-backed. All source hashes were
unchanged. Both owned tmpfs-only loopback containers were removed and independently
confirmed absent. Only known dependency and intentional malformed-primary-key
fixture warnings remained. No active app, user profile, provider or key changed.

Final isolated rendering passed **12 native/standalone combinations**: light and
dark at 1280, 640 and 390 pixels. A visible standalone explanation-inset defect
was corrected; all six standalone combinations then passed again, including
expanded disclosures. Four additional delayed-response and narrow-table-scroll
cases passed. Actual screenshots were inspected across all original combinations
and the six final standalone reruns. No unresolved visual defect was found in
this scope. The final correction changed only two standalone UI files and one
style test; all backend/Python-test bytes match the PostgreSQL-tested snapshot.

The sandboxed offscreen renderer used Electron 44.9.3, Chromium 152.0.7977.167
and React 19.3.0, with synthetic SDK/REST responses, separate temporary browser
state and HTTP(S) blocked. It checked the navigation row, contact/task link
styles, row distinction, wrapped long text, saved-work states, precise fresh-ID
navigation, separate editing/cancellation, late-response suppression and
contained table scrolling. No fixture writes or external requests occurred.
Hidden-window Tab/Enter input did not activate controls, so actual keyboard
traversal, focus-visible outlines, Escape behavior and assistive-technology
behavior were **not** verified by this render run. DOM activation/programmatic
focus checks and the separate automated keyboard-handler tests are not a
physical-host accessibility audit. All owned offscreen harness processes exited;
read-only process checks found none remaining. The active review app remained
untouched.

## Recent Activities and current-contact navigation

The dashboard now shows five recent CRM audit summaries with server-resolved
current-contact links. Contact overviews show recent changes before follow-ups
and retain older available history in a disclosure. These are CRM changes,
not email/call/proposal delivery evidence; self-reported contact logs and optional
Gmail observations stay separate. No schema migration or new integration is added.

The activity query limits audit rows before primary-key joins, preserves actor,
summary and timestamp, and resolves the current existing contact without relying
on the 500-row client snapshot. Missing/deleted/unknown targets remain unlinked;
a task's direct contact takes precedence and linked-deal fallback is allowed
only when its direct contact is null. Link metadata is not historical attribution.

Cloud verification: **1,177 Python tests passed**, **559 optional cases skipped**,
two known dependency warnings. Eight new local tests cover link resolution,
reassignment, absent/dangling references, stable ties, one-query transaction
reuse, limits, parameterized IDs, beyond-500 records and unchanged agent output
minimization. Seven skipped cases are the matching disposable PostgreSQL variants.
Independent review found no code blockers. Native React/VM tests cover five-row
limits, escaped/malformed targets, fresh read-only contact navigation, retained
older history and the existing stale-profile/response guards.

A separate disposable PostgreSQL 17.11 ARM64 run passed **567 mixed checks**
with zero failures/skips on the exact backend and Python-test bytes shipped in
this increment. Later corrections were limited to UI, UI tests and documentation.
The new activity file
passed all 15 cases (7 actual PostgreSQL, 8 SQLite/compiler). The other cases
cover core, reports/storage, customization, protection, CSV, assigned work and
existing portability contracts; this total is not exclusively PostgreSQL-backed.
Both owned tmpfs-only loopback containers were removed. No existing app, profile,
account or key was changed. Only known dependency/intentional-fixture warnings
were observed.

Final isolated rendering passed **32 cases**: native and standalone, light/dark,
1280/390 pixels, and Overview, contact detail, expanded older history and Activity.
The renderer used the same Electron/Chromium/React versions described below,
with synthetic SDK/REST responses and HTTP(S) blocked. It verified exactly five
dashboard entries, fail-closed missing/invalid links, fresh read-only navigation
from Overview and Activity, five recent plus three older fixture entries and
activity preceding tasks. No unintended overflow, writes or external requests
were observed. Full-size narrow review confirmed padded captions, removed
redundant self-contact links and separated native link/date metadata. Known
harness processes exited. The active app, backend, accounts and production
records were untouched. This was actual browser rendering, not physical-host
keyboard, screen-reader, real-provider or new end-to-end backend validation.

The final code also passes all sixteen native suites, three exact-host Python
checks, 25 bridge checks, both design-contract checks, standalone VM/syntax and
seven generator checks. The optional actual nanostores fixture remained absent
in the cloud rerun; the prior design publication ran it separately.

## Workbench UI application

This presentation increment applies the approved light/dark system to the native
pane, all existing native pages and drawers, report/dashboard builder, and the
standalone surface. It adds an original outlined Libre Bodoni wordmark with the
OFL notice, readable full-opacity dark metadata, contact table rows, compact
stage summaries, flat cards, and grouped forms. It does not change the backend,
permissions, schema or scheduling behavior. See [design coverage](DESIGN_SYSTEM.md).

Automated checks on November 7, 2026:

- **1,169 Python cases passed**, **552 optional cases skipped**, two known
  dependency deprecation warnings. PostgreSQL was not rerun for this UI-only
  increment; the unchanged backend retains the CSV portability evidence below.
- **3 exact-host Python checks passed** against host source
  2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19. These check authenticated routing and
  shared record/catalog boundaries, not physical UI rendering.
- Sixteen native SDK/React suites passed, including routing/profile changes,
  stale forms, chart keyboard/drilldown behavior, assignment/operation unknown
  outcomes, CSV consent/receipts and protected-note controls. The SDK source
  contract suite passes; an optional exact nanostores visibility run remains
  skipped without its separate fixture in this environment.
- **25 execution bridge checks passed**. Standalone VM behavior/syntax,
  native/standalone Workbench contrast/style checks, seven generator parity
  checks and whitespace checks passed. Text/status/link color pairs tested
  meet 4.5:1. These checks are not a screen-reader or accessibility certification.
- Independent review found and corrected stacked report/Gmail checkboxes,
  dark forced-color token specificity and narrow footer provenance wrapping.
  It found no remaining routing, authorization or operation-state regression.

Actual isolated rendering used Electron **44.9.3**, Chromium
**152.0.7977.167** and React/ReactDOM **19.3.0**, with the real CRM component code
and synthetic SDK/REST responses. It did not launch Hermes, use the authenticated
backend or alter the active review app.

- The native matrix covered **150 cases** across light and dark at 1280, 640 and
  390 pixels: all five pages, report builder, contact/deal/task details and
  editors, contact log, email setup, Customize, protection, CSV import/export,
  loading, errors and empty states. No unintended viewport/drawer horizontal
  overflow or missing navigation target was found. Tables and pipeline boards
  retain intentional contained scrolling.
- The standalone matrix covered **48 cases**: five routes and three creation
  dialogs across the same two themes and three widths. No unintended page or
  dialog horizontal overflow was found.
- Representative screenshots of every native page and major drawer in both
  themes were inspected, including narrow forms, reports, email/log sections
  and error states. Full-size review verified the new wordmark, readable dark
  text and padded CSV body/footer. Expanded standalone provenance wrapping passed. After the scoped filter-width
  correction, all eight final Contacts/Tasks rerenders at 640/390 in both themes
  passed: default dropdown labels are fully visible and page overflow is absent.
- Supplemental rendered checks confirm inline checkbox captions, full-opacity
  secondary/disabled text and live light-to-dark changes. DOM-dispatched modal
  key handlers verify forward/reverse focus-boundary wrapping, Escape close
  and opener-focus restoration. Genuine Electron key input did not reach the
  hidden offscreen DOM reliably, so physical keyboard navigation/focus-visible
  behavior is **not claimed as passed**. Screen readers, native file dialogs,
  touch hardware and broad zoom testing remain unverified.
- Renderers used sandboxing, context isolation, disposable state and blocked
  HTTP(S). The final instrumented handler run recorded zero external request
  attempts. Known owned harness processes exited; an OS-wide process audit was
  not performed. No real model, provider, mailbox, key, active profile or
  production data was used. No screenshot was published as part of the source.

This is real browser rendering with synthetic transport, not a new end-to-end
Hermes backend, scheduler, authorization or production-readiness certification.

## Contact-first CSV portability

This increment adds native contact-only CSV mapping/preview, valid-row selection,
conservative duplicate decisions, atomic create-only import receipts and
filtered selected-column plaintext exports. Existing contacts are not overwritten,
custom-field definitions are not created, deal stages are not converted to
Contact type, and no agents/providers/jobs or external accounts are invoked.
See [transfer scope, privacy and fidelity limits](CONTACT_TRANSFER.md).

Verification on November 7, 2026:

- Clean shipping source plus the reviewed scope correction passed **1,169 Python
  tests**, with **552 optional cases skipped** and two dependency warnings. The
  source has 156 files; dormant chat experiments are excluded.
- Fifty-eight focused local/compiler cases cover UTF-8/CSV boundaries, quoted
  cells and newlines, typed values, duplicate candidates, selected/excluded rows,
  invalid/stale approvals, atomic rollback, concurrent same-ID replay, legacy
  create/idempotency/default-stage behavior, coherent filtered exports beyond
  500 records, field minimization, formula-risk escaping, unknown outcomes and
  private artifact safety. Four artifact cases compile both SQLite/PostgreSQL
  statements with and without schemas; compilation is not a live database test.
- The first live PostgreSQL run caught a preview fingerprint bug: SQLAlchemy
  adds a string bookkeeping key to a schema map whose existing key is `None`.
  The reviewed correction binds a fixed tuple of logical workspace identity,
  profile, backend and resolved schema. It excludes mutable bookkeeping and
  connection credentials. Regressions verify stable previews/receipts across
  real compilation and credential changes, with profile/schema/workspace
  separation retained. This is scope/freshness validation, not new authorization.
- The final corrected source passed **610 synthetic checks, zero failures and
  zero skips**, in fresh disposable macOS PostgreSQL **17.11 ARM64** runs. The
  focused 85 comprise 34 local/backend/API cases, 24 artifact/compiler cases
  and 27 real PostgreSQL cases. The existing 525 regression cases include
  fifteen SQLite report variants and one SQL-compilation case, so not all 610
  are PostgreSQL-backed. macOS permissions, symlink/hardlink/FIFO rejection and
  directory-lock behavior also passed. Python 3.12, SQLAlchemy 2.1.8, psycopg
  3.3.8 and cryptography 50.0.2 were used. All 156 source hashes matched the
  reviewed archive plus its three-file scope/test correction. All four owned
  containers were removed; no existing volumes, real data or app/profile/key/
  provider settings were changed.
- Fifteen native SDK/component suites passed, including actual React 19.3,
  fatal UTF-8 decoding, no upload on file selection, explicit mapping/ignored
  columns, archived-field handling, selected-row confirmation revision, labeled
  value previews, late file/preview responses, unknown-operation recovery and
  download capture before preparation. Generated panels synchronize with all
  five generator checks. Standalone VM/syntax and all 25 execution-bridge tests
  with the real SQLite adapter passed. Three pinned-host registration/resolver
  tests passed; the existing 42-tool inventory and scheduled allowlists remain
  unchanged. The cloud lacks the optional real nanostores fixture.
- Independent code, security, UI, source-contract and documentation review
  passed. Corrections included strict UTF-8 decoding, export response alignment,
  exact receipt scope/shape, schema refusal, portable fault injection and the
  PostgreSQL scope fix. The host download contract was checked against exact
  official source `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.

The formula tests use inert strings through CSV writers/parsers and confirm
visible apostrophe transformations and preserved cell boundaries. They do not
execute a spreadsheet or establish Excel/LibreOffice save/reopen safety. No
sanitization strategy is universal; subsequent saving or transformation can
remove protections. Re-import retains escapes rather than silently decoding
them. Physical native file selection/Save-dialog/accessibility testing remains
pending. No active app, real source file, user profile, mailbox, keys or
production data were changed by this work.

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
rekeying and rebinding remain unimplemented. The later offline content restore
increment above adds fresh-target SQLite recovery without live cutover. Physical native
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
[current roadmap](ROADMAP.md).

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
source-only; see provider integration (not shipped in this core edition).

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
- Broader real-model scheduled reasoning beyond the one bounded internal-analysis check, a configured-MCP live run, visible Desktop reminder presentation, external delivery, restart recovery and live failure reconciliation. Default deferred discovery passed a bounded synthetic assigned-work fixture; the real-model check explicitly disabled it. External outreach remains outside this plugin's scope.
- Hosted Supabase connectivity, network latency/failure behavior and deployment security.
- Catalog PR, social post, contest form or production deployment.

## Source prototype publication

The source prototype is public at https://github.com/gptnius/hermes-crm. Its initial published commit is 1c70b16f09dfb534109abb3406d35e08c9f9085e; the native Mac workflow baseline is 8ab6f511899253235bc2d9e5432ef486fe95e0dc and the scheduler test baseline is e3daa0bad315bef4d996b900848e11c600e408a4. Source publication is not completion of all runtime or contest milestones. Changes undergo independent review before publication.

## Release gates still open

1. Visually verify the new chart/filter/report workflows in the native window. Expand accessibility, keyboard/focus and responsive/cross-platform coverage beyond the earlier verified Mac workflows; complete standalone desktop/mobile QA.
2. Extend scheduler coverage beyond the single authorized real-model internal-analysis check to broader tasks, restart/failure recovery and any intended human-visible reminder surface. The bounded synthetic assigned-work fixture covers default tool discovery; a configured-MCP live run remains separate. Keep external outreach excluded.
3. Complete source-distribution review and pin the reviewed commit before publishing each update.
4. Complete the runtime gates before calling this a fully validated release or preparing any authorized contest submission. A clearly labeled source prototype can remain public while those gates are open.

CRM records were synthetic. No production CRM or deployment was modified, and no private repository history or credentials were copied into the plugin. The host authentication auto-discovery attempt is disclosed above rather than treating a separate home as complete credential isolation. Dependency deprecation warnings are recorded in test output; no application test failure remains in the supported checks above.
