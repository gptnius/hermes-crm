# Native Hermes Desktop

The unified package now contains the requested native Desktop surface. It does not open an iframe or require the standalone web server.

## Package layout

- plugin.yaml and root __init__.py: agent tools and settings.
- desktop/plugin.js: plain ESM, public @hermes/plugin-sdk and host React only.
- dashboard/manifest.json + plugin_api.py: authenticated /api/plugins/hermes-crm namespace shared by Desktop transport.
- hermes_crm/runtime.py: one profile-aware storage factory for native tools and REST.
- hermes_crm/domain.py: shared CRM validation, transactions, audit and scheduling semantics.

Native contributions: a main-area CRM pane, /hermes-crm full page, CRM sidebar entry and Open Hermes CRM palette command. The pane contains dashboard cards, stage chart drillthrough, contacts and detail/history, six-stage opportunities, follow-ups and activity. Native settings expose explicit SQLite/PostgreSQL selection and the host-managed optional PostgreSQL secret.

## Installation and enablement

Use Hermes v0.23.0 or newer compatible release. Install the reviewed unified package using the host plugin installer. Enable both the Desktop component and the agent/backend component for the intended profile in Capabilities → Plugins. They are separate gates, and the package is inert until enabled.

The Desktop app copies desktop/plugin.js into its app-level plugin root. After editing an installed copy, use Capabilities → Plugins → Rescan or restart as documented by Hermes. A source checkout linked using the documented development workflow hot-reloads through the host.

For a remote backend, the Desktop half must also be installed on the computer running Desktop; the backend half belongs on the selected remote host. This document is not authorization to change any existing remote deployment. A missing or disabled backend produces an actionable error, never a localhost fallback.

## Profile and connection behavior

The active app connection/profile controls ctx.rest. This is deliberately not the owner of an arbitrary focused chat tile. The UI displays the active scope and keys all state by connection, profile and gateway activation epoch. A switch clears the prior workspace and form state. Responses from the old scope are discarded, and writes check the captured scope immediately before transport.

GET /snapshot returns metadata and initial records from one storage-factory call so a backend change cannot mix workspaces during refresh. Metadata contains an opaque persisted workspace_token. Each create/update/demo write includes the token captured when its form or confirmation opens. Search and detail requests also send their captured token. The backend rejects a mismatched token. This is additional stale-scope protection, not authentication; Hermes still enforces credentials and plugin enablement.

## Agent interaction

Desktop and native tools read/write the same database. Changes through either route appear on refresh; the pane also refreshes periodically. Updates carry versions and creates carry retry keys.

Saving a follow-up is not scheduling. The pane displays its scheduler state and tells the user to ask the existing Hermes agent to call crm_followup_schedule. Scheduling remains an active-agent operation through the supported host tool, with local delivery and read-only CRM toolset plus no_mcp. There is no REST scheduler endpoint and no extra model provider.

## Synthetic demonstration

An empty workspace offers Explore demo data. It requires a second explicit confirmation, checks the current workspace token and refuses existing records. Seeding is atomic and rolls back completely on failure. It uses only invented names and reserved example-domain emails. No user records are imported.

## Verification scope

Actual pinned Hermes server tests exercise unified component discovery, Python import gates, real authentication, shared native-tool/REST records, optimistic conflicts, workspace tokens, runtime disablement and secondary-profile host IPC. Both in_process and host isolation modes are covered with temporary profiles.

Native JavaScript checks cover SDK registration, scoped transport, lifecycle and rendered interactions. These are not a claim that the macOS/Electron window has been visually inspected. Full visual layout/accessibility QA and a live gateway reminder firing remain release gates.

Primary reference: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk
