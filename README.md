# Hermes CRM

A small, local-first CRM that your existing Hermes agent can use. Contacts, pipeline, follow-ups and activity share one datastore inside a native Hermes Desktop pane, with an optional standalone web demo.

**Prototype, not production software.** Synthetic demo data is opt-in. No customer data, private repository history, paid account, external model API or messaging integration is included. Nothing sends outreach.

## What works

- Native Desktop: real SDK pane, CRM page, sidebar navigation and palette command, using Hermes-authenticated profile-scoped transport.
- Contacts: search, create, edit and inspect linked opportunities, tasks and activity.
- Pipeline: six stages, integer-cent USD amounts, weighted forecast and stage drillthrough.
- Follow-ups: timezone-aware due dates, priority, completion and activity history.
- Native Hermes: 14 read/write tools, active-profile storage, optimistic version checks and idempotent creates.
- Native scheduling: a one-shot local Hermes job for an existing task, with safe handling of saved-but-unregistered and unknown outcomes.
- SQLite default; explicit PostgreSQL schema selection and optional Supabase PostgreSQL connection.

See [the detailed development plan](docs/DEVELOPMENT_PLAN.md), [architecture and safety](docs/ARCHITECTURE.md), [Hermes integration](docs/HERMES_INTEGRATION.md) and [verification report](docs/VERIFICATION.md).

## Native Desktop first

Install the unified package and enable both its agent/backend and Desktop components in Capabilities → Plugins. Open CRM from the sidebar or command palette. No localhost service, iframe, separate API token or new model provider is required. The active app connection/profile controls this workspace, and a profile change clears previous records and unfinished forms.

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

Integration target: Hermes Agent **v0.23.0**, commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. The repository uses a native plugin.yaml and register(ctx) entry point. There is no invented SDK API version.

After reviewing this checkout, use Hermes' documented local-path install command and enable it in the intended profile:

```bash
hermes plugins install /absolute/path/to/hermes-crm
hermes plugins doctor /absolute/path/to/hermes-crm
hermes plugins validate /absolute/path/to/hermes-crm
```

Follow the host's dependency and enablement prompts. The Python dependencies are declared in pyproject.toml. Do not install into another person's existing profile without their permission.

Try in an interactive Hermes session:

- “Create a CRM contact named Demo Buyer with email buyer@example.com. Use request key demo-buyer-1.”
- “Create a $12,000 qualified opportunity linked to Demo Buyer.”
- “Add an internal follow-up for tomorrow at 10 AM in my timezone.”
- “Schedule that CRM follow-up as a one-shot local Hermes reminder.”
- “Show the CRM overview and update the opportunity to proposal using its latest version.”

The agent must resolve ambiguous people and times rather than guess. Scheduling is a separate explicit operation from saving a due date. CRM tools never send an email or other external message.

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

This is a single-workspace, local-user prototype. It has no public authentication, tenant permissions, messaging, calendar integration, imports, attachments, migrations from another CRM or background daemon. Lists are bounded at 500 records and activity at 100; this is a small-workspace prototype, not a large CRM data browser. A future migration system is needed before changing a deployed schema. No public repository, catalog PR, contest entry or production deployment is created by running the app.

## License

MIT for this project's source. Dependencies retain their own licenses, including LGPL-3.0-only for the optional separately installed PostgreSQL driver. See [licensing and distribution notes](docs/LICENSING.md). Product names are used to describe compatibility. This project is not affiliated with Nous Research, HubSpot or Salesforce.
