# Native Hermes Desktop

The unified package now contains the requested native Desktop surface. It does not open an iframe or require the standalone web server.

## Package layout

- plugin.yaml and root __init__.py: agent tools and settings.
- desktop/plugin.js: plain ESM, public @hermes/plugin-sdk and host React only.
- dashboard/manifest.json + plugin_api.py: authenticated /api/plugins/hermes-crm namespace shared by Desktop transport.
- hermes_crm/runtime.py: one profile-aware storage factory for native tools and REST.
- hermes_crm/domain.py: shared CRM validation, transactions, audit and scheduling semantics.

Native contributions: a main-area HermesCRM pane, /hermes-crm full page, HermesCRM sidebar entry and Open HermesCRM palette command. The display branding is HermesCRM, with the tagline Intelligent Relationship Management; route, package and storage identifiers remain unchanged. The pane contains dashboard cards, stage chart drillthrough, contacts and detail/history, configurable deal stages, optional typed custom fields, follow-ups and activity. Customize opens the versioned field/stage editor. Native settings expose explicit SQLite/PostgreSQL selection and the host-managed optional PostgreSQL secret.

## Installation and enablement

Use a host matching the pinned source contract and a Desktop build that supplies the required SDK capabilities. Desktop and Agent have different version labels; see COMPATIBILITY.md for exact tested identities and the limits of the manifest's numeric declaration. Older Desktop builds show a compatibility notice instead of attempting CRM reads or changes.

Install the reviewed local Git checkout using `hermes plugins install "file:///absolute/path/to/hermes-crm"`. The bare absolute-path form was misparsed on the tested host; the file URI was verified. Enable both the Desktop component and the agent/backend component for the intended profile in Capabilities → Plugins. They are separate gates, and the package is inert until enabled.

The Desktop app copies desktop/plugin.js into its app-level plugin root. After editing an installed copy, use Capabilities → Plugins → Rescan or restart as documented by Hermes. A source checkout linked using the documented development workflow hot-reloads through the host.

For a remote backend, the Desktop half must also be installed on the computer running Desktop; the backend half belongs on the selected remote host. This document is not authorization to change any existing remote deployment. A missing or disabled backend produces an actionable error, never a localhost fallback.

## Profile and connection behavior

The active app connection/profile controls ctx.rest. This is deliberately not the owner of an arbitrary focused chat tile. The UI displays the active scope and keys state by connection, profile, gateway activation epoch and a monotonic generation observing connection-state transitions. A switch or reconnect clears prior workspace and form state. Responses from the old scope are discarded, and writes check the captured scope immediately before transport. Plugin disposal invalidates pending clients and removes listeners.

GET /snapshot returns metadata and initial records from one storage-factory call so a backend change cannot mix workspaces during refresh. Metadata contains an opaque persisted workspace_token. Each create/update write includes the token captured when its form or confirmation opens. Search and detail requests also send their captured token. The backend rejects a mismatched token. This is additional stale-scope protection, not authentication; Hermes still enforces credentials and plugin enablement.

## Agent interaction

Desktop and native tools read/write the same database. Changes through either route appear on refresh; the pane also refreshes periodically. Updates carry versions and creates carry retry keys.

Saving a follow-up is not scheduling. The pane displays its scheduler state and tells the user to ask the existing Hermes agent to call crm_followup_schedule. Scheduling remains an active-agent operation through the supported host tool, with local delivery and read-only CRM toolset plus no_mcp. There is no REST scheduler endpoint and no extra model provider.

## Developer-only synthetic workspace setup

Ordinary installations start empty. The native About dialog has no seeding
controls. Existing synthetic workspace records are preserved, with provenance
available in About and standalone Workspace details rather than a working-view
banner.

For development only, use the existing opt-in CLI with a fresh disposable data
directory. From an environment with the package installed:

```bash
env -u HERMES_CRM_DATABASE_URL -u HERMES_CRM_POSTGRES_SCHEMA \
  HERMES_CRM_BACKEND=sqlite \
  HERMES_CRM_DATA_DIR="$(mktemp -d /tmp/hermes-crm-dev.XXXXXX)" hermes-crm --demo
```

The CLI starts a loopback-only server after seeding. Stop it with Ctrl+C. Never
point this command at an existing datastore or a shared/customer database.
It creates eight invented contacts using reserved example-domain addresses,
eight deals and five internal tasks. No user records are imported. Seeding
refuses existing CRM records, is atomic and rolls back completely on failure.
The compatibility `/demo` API retains its explicit confirmation and captured
workspace-token requirement; removing the UI controls does not change that API.
See the isolated-testing guidance below before using a native host or provider.

## Verification scope

Actual pinned Hermes server tests exercise unified component discovery, Python import gates, real authentication, shared native-tool/REST records, optimistic conflicts, workspace tokens, runtime disablement and secondary-profile host IPC. Both in_process and host isolation modes are covered with temporary profiles.

Native JavaScript checks cover SDK registration, scoped transport, lifecycle and rendered interactions. A separate genuine Mac native-window run on the pinned source build also verified installation, rendering, contact editing, registered-tool/desktop record interchange, task completion, pipeline drill-through and a new empty secondary profile. Dashboard and contact-detail screenshots contain synthetic data only. This is core workflow coverage, not a complete accessibility, responsive-layout or cross-platform audit.

A later guarded test verified real one-shot scheduler fires through the actual agent loop and CRM read handler, with expected local outputs for open and completed tasks. Only the model endpoint was deterministic and loopback-only. That run was not through the visible Desktop window and does not verify Desktop notifications, real-model behavior, default deferred-tool discovery or restart recovery. See VERIFICATION.md for exact commits, tool restrictions and cleanup evidence.

## Isolated testing and provider discovery

Use a fresh test home and synthetic records. Do not copy real Hermes configuration, provider credentials, login stores or customer records into it. Native CRM CRUD and direct registered-tool checks do not require a model provider.

A separate Hermes home isolates CRM records but is not a complete credential boundary. During native sandbox testing, the host's provider auto-discovery attempted a login refresh and received `invalid_grant`; no credentials were manually retrieved or copied. Starting the host can therefore touch other CLI authentication state even when the test profile has no working model provider.

For repeatable tests, prefer a credential-free test environment and restrict outbound access where the test permits it. Do not assume that clearing environment variables or choosing a fresh Hermes home disables all host auto-discovery. Do not sign in, copy credentials or expand provider access merely to make a test pass. A live model or scheduler execution test requires separately authorized setup. Existing installations, production data and remote services are not part of these test instructions.

Primary reference: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
