# Hermes CRM

A small, local-first CRM that your existing Hermes agent can use. Contacts, pipeline, follow-ups and activity share one datastore inside a native Hermes Desktop pane, with an optional standalone web demo.

**Prototype, not production software.** Synthetic demo data is opt-in. No customer data, private repository history, paid account, external model API or messaging integration is included. Nothing sends outreach.

## What works

- Native Desktop: real SDK pane, CRM page, sidebar navigation and palette command, using Hermes-authenticated profile-scoped transport.
- Native conversation companion: open CRM beside an existing verified main Hermes chat; preview and copy a minimal record reference for manual paste/review/Send. No draft writes or automatic submission. See [native chat](docs/NATIVE_CHAT.md).
- Contacts: paged reports with combined Stage, Contact type, company, email and follow-up filters; structured record details, related records and grouped create/edit drawers.
- Main dashboard: six-stage value donut with keyboard/hover details, unique-contact drillthrough and preset missing/overdue follow-up reports.
- Pipeline: six stages, integer-cent USD amounts, company/value filters and weighted forecast.
- Follow-ups: timezone-aware due dates, priority, completion, activity history and read-only native-assignment results awaiting review.
- Native Hermes: 22 tools across separate record, assigned-work and native-report permission sets, active-profile storage, optimistic version checks and idempotent creates.
- Native scheduling: a one-shot local Hermes reminder for an existing task, with safe handling of saved-but-unregistered and unknown outcomes.
- Assigned-work prototype: explicit active-agent paused-create/bind/resume and authenticated native-run reports awaiting review. Future one-shots passed guarded scheduled-agent tests with deterministic local model responses; real-model behavior remains unverified. See [native assigned work](docs/NATIVE_ASSIGNED_WORK.md).
- SQLite default; explicit PostgreSQL schema selection and optional Supabase PostgreSQL connection.

See [the detailed development plan](docs/DEVELOPMENT_PLAN.md), [the next-release agent-work roadmap](docs/NEXT_RELEASE_PLAN.md), [architecture and safety](docs/ARCHITECTURE.md), [Hermes integration](docs/HERMES_INTEGRATION.md) and [verification report](docs/VERIFICATION.md).

## Native Desktop first

Install the unified package and enable both its agent/backend and Desktop components in Capabilities → Plugins. Open CRM from the sidebar or command palette. No localhost service, iframe, separate API token or new model provider is required. The active app connection/profile controls this workspace, and a profile change clears previous records and unfinished forms.

Desktop and Agent version labels differ. Compatibility is verified against the exact host source revision below, not inferred from a release label. Desktop must supply the required routing capabilities; unsupported builds show a notice and disable CRM operations. See [exact host compatibility](docs/COMPATIBILITY.md).

An empty workspace offers an explicit, confirmed synthetic-demo seed. This never runs automatically and refuses existing records. See [native Desktop setup and test scope](docs/NATIVE_DESKTOP.md).

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

Real one-shot scheduler execution, CRM reads and saved local outputs passed controlled tests using deterministic loopback model responses. The newer assigned-work tests also passed default deferred discovery and authenticated reporting in both plugin isolation modes. Test setup invokes registered scheduling handlers with a real active-agent context, rather than testing a model choosing to schedule or an interactive approval dialog. Real-model reasoning, visible Desktop reminders and restart recovery remain unverified. See the verification report for the exact test scope.

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
node --check hermes_crm/static/app.js
```

Tests use temporary synthetic data. See docs/VERIFICATION.md for exact tested environments, native Hermes doctor results, browser limitations and PostgreSQL findings.

## Deliberate limits

This is a single-workspace, local-user prototype. It has no public authentication, tenant permissions, messaging, calendar integration, imports, attachments, migrations from another CRM or background daemon. Contact reports use server pagination with filtered totals. Legacy lists, deal/task views and form choices are bounded at 500 records, and activity at 100; displayed deal-list totals cover returned records. This is a small-workspace prototype, not a large CRM data browser. Direct Desktop submission remains disabled; native future assignments are a bounded, separately tested path. Custom saved views and a report/dashboard builder are not implemented. A future migration system is needed before changing a deployed schema. No public repository, catalog PR, contest entry or production deployment is created by running the app.

## License

MIT for this project's source. Dependencies retain their own licenses, including LGPL-3.0-only for the optional separately installed PostgreSQL driver. See [licensing and distribution notes](docs/LICENSING.md). Product names are used to describe compatibility. This project is not affiliated with Nous Research, HubSpot or Salesforce.
