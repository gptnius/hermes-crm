# Hermes integration notes

## Verified upstream target

Official Hermes source commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19, including its Desktop SDK. The isolated native runtime identified as vgit.2bd378e, while the source package manifests declare 0.0.0. Use this exact source identity rather than the earlier, imprecise v0.23.0 label. No release date or broad version compatibility is inferred from this test.

Primary sources:
- https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/public-api
- https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission
- https://hermes-agent.nousresearch.com/docs/user-guide/features/cron
- https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/plugins.py
- https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/plugins/plugin_storage.py
- https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/cronjob_tools.py

## Native registration

The root entry point uses a relative package import because Hermes loads plugin packages in its own namespace, not by adding the checkout directory to sys.path. register(ctx) registers 83 tools, matching `plugin.yaml`. This is the registered catalog, not a claim that every tool is enabled in every conversation. Tool handlers accept `(args, **kwargs)` and return a JSON string. Dependencies are declared in pyproject.toml.

Read toolset crm_read: crm_contact_report, crm_contact_list, crm_contact_get, crm_deal_list, crm_deal_get, crm_task_list, crm_task_get, crm_overview.

Write toolset crm_write: crm_contact_create, crm_contact_update, crm_deal_create, crm_deal_update, crm_task_create, crm_task_update, crm_followup_schedule.

Assigned-work toolsets are separate: `crm_work_read` contains get/list; `crm_work_schedule` contains create/schedule/reconcile/cancel; `crm_work_report` contains only the trusted-context report writer. The original `crm_read` inventory stays at eight. See NATIVE_ASSIGNED_WORK.md for the active-context scheduling contract, provenance and uncertainty limits.

Saved reports and authored contact logs use separate `crm_reports`,
`crm_report_write`, `crm_interaction_read` and `crm_interaction_write` toolsets.
Customization adds `crm_schema_catalog` in `crm_schema_read`, and stage/field
create/update tools in `crm_schema_write`. They do not enter existing scheduled
allowlists. Record tools accept optional `custom_fields` validated against the
current catalog; stage filters use stable keys rather than a frozen six-key enum.
See [customization contracts](CUSTOMIZATION.md).

Base read/write outputs omit ordinary notes and custom values. Exact ordinary
field selection uses `crm_record_fields` in separate `crm_detail_read`; it is not
added to fixed scheduled allowlists. The supported kinds are Contacts, Deals,
Tasks, Companies and Events. Exact ordinary `notes` are available for all five;
`custom.<known_key>` is limited to Contacts/Deals/Tasks and `outcome_summary` to
Events. Reads share a schema/scope/row snapshot, return the current version and
do not initialize absent relationship storage. Optional protected notes have no agent
tool. Native protection routes use profile-scoped `get_secret` for dedicated
keyrings and the supported optional `captureGatewayFileDownload` SDK helper for
explicit encrypted export downloads. No real keys are created or configured;
masked host configuration may be plaintext `.env`. See [protection boundaries](PROTECTION.md).

Native storage comes from plugins.plugin_storage. Plugin PostgreSQL selection uses ctx.get_config('backend', default='sqlite') and agent.secret_scope.get_secret('HERMES_CRM_DATABASE_URL'). No secret is needed for SQLite. The CRM plugin does not scan the filesystem to discover settings, jobs, tokens or credentials. The Hermes host has separate provider auto-discovery behavior; see NATIVE_DESKTOP.md for the testing caveat.

Native PostgreSQL schema is `crm_` followed by the first 24 hex characters of SHA-256 of the resolved plugin data-directory path. This keeps active profiles separate on one explicitly selected database. The standalone CLI needs the same explicit HERMES_CRM_POSTGRES_SCHEMA to view those records. Do not publish resolved profile paths; they are only local namespace inputs.

## Contact report contract

`crm_contact_report` and `/reports/contacts` share server-side filtering and return `items`, `total`, `limit` and `offset`. Filters cover linked deal stage, Contact type, company, email presence, text and open-follow-up state. Results count contacts once even when multiple deals match and include distinct linked stages plus follow-up aggregates. The base agent tool intentionally returns a minimized item projection: notes, custom values and canonical Company-link metadata stay out of that default response. Shared allowed fields, totals, filters and pagination match the human REST result; full dictionaries are not identical. Requested ordinary notes and supported custom values use `crm_record_fields`. The legacy contact `lifecycle` field stores Contact type; it is not a deal stage. Existing list tools retain array responses and the 500-record bound.

The added report tool makes the current read toolset eight tools. Historical live-scheduler evidence in VERIFICATION.md used an earlier seven-read-tool revision and is not a new live-scheduler verification of this addition.

## Follow-up reminder scheduler contract

Use `ctx.dispatch_tool('cronjob_manage', payload, **context)` in an active tool turn. Forward session context. Do not import the private cron function or edit jobs.json.

The adapter targets the pinned source contract and does not pretend to support older `cronjob` registry naming. ISO timestamps with UTC offsets are one-shot schedules. A bare interval such as 30m is recurring, so this prototype never constructs that shorthand.

Hermes can save a job but fail scheduler registration. Its result may contain success=false, job_id, job_saved=true, scheduler_registered=false and retry_create=false. The CRM preserves the ID and marks uncertain. A generic error can also arise after persistence and is not proof no job exists.

No jobs are installed at registration. The plugin does not create credentials, configure model providers or implement external outreach. The original `crm_followup_schedule` reminder requests `crm_read` plus `no_mcp` and local delivery. The separate native assigned-work path requests `crm_read`, `crm_work_read`, `crm_work_report` and `no_mcp`. Enforcement evidence is limited to the tested configurations; a configured model provider may receive task data.

A historical reminder test exercised actual registration, due-time firing, canonical admission, AIAgent, CRM reads, execution-ledger completion and local output persistence. Its only synthetic component was a deterministic loopback model endpoint. Deferred discovery was disabled in that run, no MCP servers were configured, and no Desktop notification, external delivery, real-model reasoning or restart recovery was tested. Current native-assignment evidence is reported separately in VERIFICATION.md; neither path should be treated as unrestricted end-to-end validation.

## Native Desktop

The unified package now includes a real native main pane, /hermes-crm route, sidebar item and palette action in desktop/plugin.js. It uses only @hermes/plugin-sdk and React imports, with no build step or iframe. The dashboard directory exposes only the common plugin REST namespace; it is not a separate web-dashboard frontend.

The UI uses ctx.rest, active app profile/connection state and gateway activation epoch. Native mutations additionally carry the captured workspace token. The backend uses the exact same runtime factory and relational domain service as tools. The Desktop and backend enablement gates remain separate and opt-in. See NATIVE_DESKTOP.md for install and validation details.

Official Desktop reference: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk

### Existing native conversation companion

The optional chat handoff uses the tested public `host.openWorkspace` side-dock option, `host.revealPane`, `host.paneVisibility`, `host.navigate` and read-only session ownership atoms. It returns only to an already loaded matching primary conversation. It does not call `host.openSession`, `host.newChat`, gateway RPC or any composer helper. Missing, ambiguous or foreign ownership fails closed. Old hosts that ignore side docking do not receive a misleading success state.

Record preview/copy carries only connection, profile, kind, ID and version. Copy re-reads the scoped record with its workspace token and checks the version, but never puts that token or record text on the clipboard. The user pastes and sends through the genuine native composer, retaining host approvals. Read NATIVE_CHAT.md for steps, required state and limitations. This is not email integration or automatic context attachment.

## Catalog and release gates

Catalog metadata must identify a verified repository owner and pin an exact reviewed 40-character plugin commit. A template is intentionally not submitted. Public distribution requires privacy/secret review, dependency review, install instructions, declared capabilities and truthful compatibility floor. No automatic self-update or core patching is included.

Contest requirements were checked against the official Nous Research announcement: November 11, 2026 at 5 PM EST (22:00 UTC); open catalog PR, under-90-second working X demo tagging @NousResearch and form links. These are preparation notes only. No PR, social post or form submission is authorized by running this code.


## Opt-in task-linked scheduled public research

Ten additional tools provide the separate `scheduled_research_v1` mode. Its
management/read/run toolsets are `crm_scheduled_research_schedule_v1`,
`crm_scheduled_research_read_v1`, and `crm_scheduled_research_run_v1`.
An explicitly scheduled future one-shot binds an open Task/version and exact
Company/Contact/version. It requests `search` or `web`, four assignment-bound
run tools, and `no_mcp`. Evidence and a permitted note proposal are stored for
review, never applied automatically. Reports do not complete business Tasks.
Host tools/backend availability and unattended approval policy still apply.
Existing internal-analysis assignments retain their original 11-tool inventory.
See [implementation and remaining verification](SCHEDULED_RESEARCH_PLAN.md).
