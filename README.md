# HermesCRM

**Intelligent Relationship Management**

A small, local-first CRM that your existing Hermes agent can use. Contacts, pipeline, follow-ups and activity share one datastore inside a native Hermes Desktop pane, with an optional standalone web demo.

**Prototype, not production software.** Synthetic demo data is opt-in. No customer data, private repository history, paid account, external model API or outbound messaging integration is included. Nothing sends outreach.

**New here? Read the [setup and user guide](docs/USER_GUIDE.md)** for installation, feature walkthroughs, agent examples, reporting, optional integrations and troubleshooting.

## What works

- Native Desktop: real SDK pane, CRM page, sidebar navigation and palette command, using Hermes-authenticated profile-scoped transport.
- Workbench UI: coordinated light/dark pages, bright dark-mode metadata, flat cards, larger underlined navigation on its own row, clearly separated contact rows with blue name links, structured record/transfer drawers and an original licensed HermesCRM wordmark. See the [design system and coverage](docs/DESIGN_SYSTEM.md).
- Native conversation companion: open CRM beside an existing verified main Hermes chat; copy a validated minimal record reference in one click, with an optional hideable preview, for manual paste/review/Send. No draft writes or automatic submission. See [native chat](docs/NATIVE_CHAT.md).
- Contacts: paged reports with combined Stage, Contact type, company, email and follow-up filters; structured record details, related records and grouped create/edit drawers.
- Main dashboard: preset stage/attention views plus a typed report builder, shared saved definitions, version-pinned table/KPI/bar/line/donut cards and live contributing-record drilldowns. See [flexible reports](docs/FLEXIBLE_REPORTS.md).
- Upcoming Tasks: the earliest six open tasks, including visibly overdue work, with current linked-contact context and direct task links. Business-task ownership is not inferred from the creator, reminders or current Hermes profile; saved agent-work intent and its human owner remain separate from scheduling and execution.
- Recent Activities: five recent CRM audit summaries on the dashboard, with verified current-contact links; contact overviews put recent changes before follow-ups and retain older available history. These are record changes, not proof of customer communication.
- Logged contact: explicit self-reported contact events with corrections, kept separate from CRM edits and optional Gmail observations.
- Pipeline: six initial stages plus custom stages, stable keys and explicit open/won/lost outcomes, integer-cent USD amounts, company/value filters and weighted forecast.
- Customization: versioned optional text/number/boolean/date/single-select fields on contacts, deals and tasks; native record forms and typed reports use the same catalog as agents. Archive retains definitions/values; used deal stages cannot be archived. See [custom fields and stages](docs/CUSTOMIZATION.md).
- Follow-ups: timezone-aware due dates, priority, completion, direct saving of future internal-work assignments, paged assignment history and a server-counted coverage queue. Saving does not schedule work. A separate reviewed CRM confirmation can schedule, check or cancel that exact future assignment through the existing native conversation. Task-specific Preview/Copy remains available for manual native chat Send. See [assignment workflow](docs/ASSIGNMENT_UI.md).
- Native Hermes: 42 tools across separate record, assigned-work, native-report and schema permission sets, active-profile storage, optimistic version checks and idempotent creates. Existing scheduled assignments do not gain schema-writing tools.
- Native scheduling: a one-shot local Hermes reminder for an existing task, with safe handling of saved-but-unregistered and unknown outcomes.
- Assigned-work prototype: explicit agent-tool or CRM-confirmed user-command scheduling, paused-create/bind/resume and authenticated native-run reports awaiting review. Future one-shots passed guarded deterministic-model tests and one separately authorized real-model internal-analysis check. Results still require human review. See [native assigned work](docs/NATIVE_ASSIGNED_WORK.md).
- Contact CSV: native column mapping, row validation, duplicate review and create-only batch imports; filtered, selected-column exports with formula-like text escaping and explicit plaintext-file retention. Existing contact custom fields are supported. See [contact transfer and limits](docs/CONTACT_TRANSFER.md).
- Layered protection: reduced default agent output, explicit ordinary-field reads, optional separately encrypted protected notes and encrypted CRM content exports. Keys remain user-managed; no full restore or general security guarantee. See [scope and recovery limits](docs/PROTECTION.md).
- SQLite default; explicit PostgreSQL schema selection and optional Supabase PostgreSQL connection.
- Optional Gmail metadata history: default off, manual own-mailbox verification and reviewed contact/date reads through host-owned OAuth, a separate durable ledger and native contact timeline. Synthetic tests only; no live account connected or verified. See [setup and limits](docs/GMAIL_SETUP.md).

See [the detailed development plan](docs/DEVELOPMENT_PLAN.md), [the next-release agent-work roadmap](docs/NEXT_RELEASE_PLAN.md), [architecture and safety](docs/ARCHITECTURE.md), [Hermes integration](docs/HERMES_INTEGRATION.md) and [verification report](docs/VERIFICATION.md).

## Development roadmap

This README is the priority index for future development. Planned capabilities
below are not claims about the current release; detailed plans and verification
remain linked here as work progresses.

1. **Custom fields and stages, implemented in this increment.** Typed optional fields for contacts,
   deals and tasks; configurable deal stages with stable identities and explicit
   open/won/lost outcomes; shared native forms, agent tools and report metadata.
   Preserve existing records and saved definitions, validate migrations on SQLite
   and PostgreSQL, and reject destructive changes rather than silently convert
   data. See the [customization plan](docs/CUSTOMIZATION_PLAN.md).
2. **Layered protection, first increment implemented.** Default agent responses
   minimize ordinary notes/custom values; exact-field reads are separate. Optional
   protected notes and encrypted content exports use user-managed dedicated keys.
   Existing ordinary copies remain plaintext. Continue with scoped authorization,
   key lifecycle, tested restore/recovery, copy retention and remote database
   roles/TLS. A masked secret may be plaintext `.env`; no tenant-isolation,
   compliance or production-security claim is made. See [protection boundaries](docs/PROTECTION.md).
3. **Import and export, contact-first increment implemented.** Native UTF-8 CSV
   mapping/preview, existing typed contact fields, explicit row/duplicate review,
   atomic create-only batches and durable outcome receipts. Filtered exports use
   selected ordinary columns, visible spreadsheet escaping and explicit plaintext
   artifact retention. No existing contact is overwritten. Continue with reviewed
   updates/merges, relationship-aware deals/tasks, larger resumable batches and
   retention controls. See [contact transfer](docs/CONTACT_TRANSFER.md).
4. **External CRM linking, deferred.** Future HubSpot/Salesforce connections need
   account-scoped authorization, durable external identifiers, field ownership,
   conflict review and recovery. Read-only refresh, reviewed write-back and
   automatic two-way synchronization are different capabilities, not synonyms
   for CSV import. No connector or live migration is included today.

Other planned work remains explicitly separate:

- **Agent work:** a supported safe immediate-execution path, stronger recovery
  evidence, reviewed cadences and bounded research capabilities. No promise that
  every task executes or that outages and unknown outcomes cannot occur. See
  [agent-work roadmap](docs/NEXT_RELEASE_PLAN.md).
- **Reporting:** multiple pipelines, stage-transition history and actual outcome
  dates before historical funnels; broader date controls, dashboard-wide filter
  semantics and scale testing. Advanced formulas, arbitrary joins and custom
  objects are deferred. See [report limits](docs/FLEXIBLE_REPORTS.md).
- **Future communication integrations:** automatic inbound/outbound email history,
  provider-backed proposal activity, and optional calling/texting integrations
  (for example, Telnyx). These need explicit account authorization, reviewed
  actions, durable provider identifiers and delivery/outcome evidence. They are
  not implemented by the audit timeline; no calls, texts or email sends are
  enabled by this roadmap.
- **Conversation and email:** safer host-supported draft insertion only when a
  session-bound contract exists; separately approved live Gmail validation and
  later provider-backed communication features. No automatic sending, account
  grants or inbox access is authorized by this roadmap. See
  [native chat](docs/NATIVE_CHAT.md) and [Gmail setup](docs/GMAIL_SETUP.md).
- **Release quality:** the Workbench design system is applied across native pages,
  dialogs and the standalone surface. Continue physical-host accessibility,
  responsive/dark-mode and
  interrupted-workflow coverage, backup/restore validation, larger datasets and
  operational documentation. The current product remains a prototype.

## Native Desktop first

Install the unified package and enable both its agent/backend and Desktop components in Capabilities → Plugins. Open CRM from the sidebar or command palette. No localhost service, iframe, separate API token or new model provider is required. The active app connection/profile controls this workspace, and a profile change clears previous records and unfinished forms.

Desktop and Agent version labels differ. Compatibility is verified against the exact host source revision below, not inferred from a release label. Desktop must supply the required routing capabilities; unsupported builds show a notice and disable CRM operations. See [exact host compatibility](docs/COMPATIBILITY.md).

An empty workspace starts with ordinary record creation. Optional synthetic test setup is inside the page’s About information dialog; it requires explicit confirmation, never runs automatically and refuses existing records. See [native Desktop setup and test scope](docs/NATIVE_DESKTOP.md).

## Optional standalone demo

Use Python 3.11 or newer. A virtual environment is recommended.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
export HERMES_CRM_DATA_DIR="$PWD/.demo-data"
hermes-crm --demo
```

Open http://127.0.0.1:8742. The server deliberately binds only to loopback. `--demo` seeds an empty workspace; remove that flag on later starts. Never point the demo at an existing datastore.

The demo contains eight invented contacts using example.com, eight opportunities and five internal tasks. The workspace banner labels synthetic data. This is not a snapshot of any real CRM.

To start an empty workspace, choose a fresh HERMES_CRM_DATA_DIR and omit `--demo`. Without a path override, storage is the active HERMES_HOME/plugin-data/hermes-crm/data.db; when loaded in Hermes, its public storage helper is used.

## Install as a native Hermes plugin

Verified integration target: official Hermes source commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, including its Desktop SDK. The isolated native test runtime identified as `vgit.2bd378e`; the source manifests say `0.0.0`. Earlier documentation called this v0.23.0, which was not a reliable identity for the tested build. The repository uses a native plugin.yaml and register(ctx) entry point. Its existing `requires_hermes: >=0.23.0` declaration is retained, but is not proof of a tested numeric minimum or compatibility with every later release.

After reviewing a local Git checkout, install it with a file URI and enable it in the intended profile. On the tested host, a bare absolute path was misparsed as a GitHub identifier; this file-URI form worked:

```bash
hermes plugins install "file:///absolute/path/to/hermes-crm"
hermes plugins doctor /absolute/path/to/hermes-crm
hermes plugins validate /absolute/path/to/hermes-crm
```

Follow the host's dependency and enablement prompts. The Python dependencies are declared in pyproject.toml. Do not install into another person's existing profile without their permission.

For isolated testing, use synthetic records and a fresh test home, without copying real credentials or configuration. A separate Hermes home does not prevent the host from auto-discovering other CLI logins. See [safe test setup](docs/NATIVE_DESKTOP.md#isolated-testing-and-provider-discovery).

Try in an interactive Hermes session:

- “Create a CRM contact named Demo Buyer with email buyer@example.com. Use request key demo-buyer-1.”
- “Create a $12,000 qualified opportunity linked to Demo Buyer.”
- “Add an internal follow-up for tomorrow at 10 AM in my timezone.”
- “Schedule that CRM follow-up as a one-shot local Hermes reminder.”
- “Show the CRM overview and update the opportunity to proposal using its latest version.”

The agent must resolve ambiguous people and times rather than guess. Scheduling is a separate explicit operation from saving a due date. CRM tools never send an email or other external message.

Real one-shot scheduler execution, CRM reads and saved local outputs passed controlled tests using deterministic loopback model responses. The newer assigned-work tests also passed default deferred discovery and authenticated reporting in both plugin isolation modes. Earlier setup tests invoke registered scheduling handlers with a real active-agent context. Separate command-to-run tests now prepare through authenticated CRM REST and schedule through a real durable native user session, then execute the actual scheduler/agent/report path. Neither fixture tests a model choosing to schedule or a physical native confirmation click. A separate isolated Terra 6.1 check passed for synthetic internal analysis; broad real-model quality, visible Desktop reminders and restart recovery remain unverified. See the verification report for the exact test scope.

### Desktop and agent use the same records

The native pane calls the plugin namespace through ctx.rest; Hermes owns authentication and profile routing. Native REST and tool handlers share the same per-call storage factory. A workspace token and activation-epoch checks reject stale cross-profile writes.

The optional standalone CLI is a separate local demo mode. Start it in the same intended HERMES_HOME and leave HERMES_CRM_DATA_DIR unset to see the same SQLite records. That standalone process does not follow Desktop profile switches. Do not expose it as a public service.

## PostgreSQL and Supabase

Install `.[postgres]` for the psycopg driver. For the standalone CLI, select a dedicated database and a dedicated schema explicitly:

```bash
export HERMES_CRM_BACKEND=postgres
export HERMES_CRM_DATABASE_URL='postgresql://...'
export HERMES_CRM_POSTGRES_SCHEMA=crm_my_workspace
hermes-crm
```

Provide the real URL securely, not in chat or a committed file. Backend and schema must be set; invalid or unavailable PostgreSQL never falls back to SQLite. Schema names must start with crm_ and use lowercase letters, digits and underscores. The database role needs permission to create this schema and its tables.

For native Hermes, set the plugin's backend setting to postgres and supply HERMES_CRM_DATABASE_URL through the host's supported profile secret configuration. Native tools use agent.secret_scope.get_secret, not another profile's process environment. The schema is derived from the active profile data directory, so profiles remain isolated even on the same database. See the integration document for selecting the matching schema in the standalone UI.

Supabase is supported as a PostgreSQL connection option, not via its REST SDK. A direct database connection or session-mode pooler is recommended; use TLS for remote connections and a least-privilege dedicated database role. Hosted Supabase has not been exercised in this prototype. Do not mistake SQL portability for hosted-service or multi-tenant security verification.

## Tests

```bash
python -m pytest -q
python scripts/build_email_panel.py --check
python scripts/build_report_panels.py --check
python scripts/build_customization_panel.py --check
python scripts/build_protection_panel.py --check
python scripts/build_contact_transfer_panel.py --check
python scripts/build_design_system.py --check
python scripts/build_wordmark_component.py --check
node tests/native_workbench.mjs
node tests/standalone_workbench.cjs
node --experimental-vm-modules tests/desktop_contact_transfer.mjs
node --experimental-vm-modules tests/desktop_protection.mjs
node --experimental-vm-modules tests/desktop_reports.mjs
node --experimental-vm-modules tests/desktop_contact_log.mjs
node --experimental-vm-modules tests/desktop_email_history.mjs
node --check hermes_crm/static/app.js
```

Tests use temporary synthetic data. See docs/VERIFICATION.md for exact tested environments, native Hermes doctor results, browser limitations and PostgreSQL findings.

## Deliberate limits

This is a single-workspace, local-user prototype. It has no public authentication, tenant permissions, messaging, calendar integration, attachments, full CRM migrations or a background daemon. Contact reports use server pagination with filtered totals. Coverage and assignment history use server pages with exact evidence-item totals; their current implementation scans local history and is not optimized for large datasets. Legacy lists, deal/task list views and form choices are bounded at 500 records, and activity at 100; displayed deal-list totals cover returned records. This is a small-workspace prototype, not a large CRM data browser. Direct chat prompt submission remains disabled. CRM-confirmed future scheduling uses an authenticated user command, not model-tool approval hooks; it requires the matching existing main native chat and stable trusted host configuration. See [operation boundaries](docs/CRM_CONFIRMED_OPERATIONS.md). Native future assignments remain a bounded, separately tested path. Native saved report definitions and dashboard cards are implemented within the [documented report limits](docs/FLEXIBLE_REPORTS.md). CSV transfer is contact-only, create-only and bounded; it is not a full migration or restore. Multiple pipelines, required/unique/calculated fields, arbitrary joins/formulas, dashboard-global filters and historical funnel reports remain future work. Customization uses a versioned additive schema upgrade; it does not migrate another CRM or provide automatic backup/restore. Optional encrypted exports do not provide a supported restore workflow; keep existing tested backups and recovery keys. Back up an existing datastore before updating. No catalog PR, contest entry or production deployment is created by running the app.

## License

MIT for this project's code. The original outlined wordmark derives from SIL OFL 1.1 Libre Bodoni; its notice and provenance are retained. Dependencies retain their own licenses, including LGPL-3.0-only for the optional separately installed PostgreSQL driver. See [licensing and distribution notes](docs/LICENSING.md). Product names are used to describe compatibility. This project is not affiliated with Nous Research, HubSpot or Salesforce.
