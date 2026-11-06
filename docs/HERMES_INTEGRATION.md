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

The root entry point uses a relative package import because Hermes loads plugin packages in its own namespace, not by adding the checkout directory to sys.path. register(ctx) registers 14 tools. Tool handlers accept `(args, **kwargs)` and return a JSON string. Dependencies are declared in pyproject.toml.

Read toolset crm_read: crm_contact_list, crm_contact_get, crm_deal_list, crm_deal_get, crm_task_list, crm_task_get, crm_overview.

Write toolset crm_write: crm_contact_create, crm_contact_update, crm_deal_create, crm_deal_update, crm_task_create, crm_task_update, crm_followup_schedule.

Native storage comes from plugins.plugin_storage. Plugin PostgreSQL selection uses ctx.get_config('backend', default='sqlite') and agent.secret_scope.get_secret('HERMES_CRM_DATABASE_URL'). No secret is needed for SQLite. The CRM plugin does not scan the filesystem to discover settings, jobs, tokens or credentials. The Hermes host has separate provider auto-discovery behavior; see NATIVE_DESKTOP.md for the testing caveat.

Native PostgreSQL schema is `crm_` followed by the first 24 hex characters of SHA-256 of the resolved plugin data-directory path. This keeps active profiles separate on one explicitly selected database. The standalone CLI needs the same explicit HERMES_CRM_POSTGRES_SCHEMA to view those records. Do not publish resolved profile paths; they are only local namespace inputs.

## Scheduler contract

Use `ctx.dispatch_tool('cronjob_manage', payload, **context)` in an active tool turn. Forward session context. Do not import the private cron function or edit jobs.json.

The adapter targets the pinned source contract and does not pretend to support older `cronjob` registry naming. ISO timestamps with UTC offsets are one-shot schedules. A bare interval such as 30m is recurring, so this prototype never constructs that shorthand.

Hermes can save a job but fail scheduler registration. Its result may contain success=false, job_id, job_saved=true, scheduler_registered=false and retry_create=false. The CRM preserves the ID and marks uncertain. A generic error can also arise after persistence and is not proof no job exists.

No jobs are installed at registration. No new credentials, LLM providers, subscriptions or remote connections are created. Scheduled prompts can only read CRM records, prepare local reminders and check current completion state. They do not contact third parties.

## Native Desktop

The unified package now includes a real native main pane, /hermes-crm route, sidebar item and palette action in desktop/plugin.js. It uses only @hermes/plugin-sdk and React imports, with no build step or iframe. The dashboard directory exposes only the common plugin REST namespace; it is not a separate web-dashboard frontend.

The UI uses ctx.rest, active app profile/connection state and gateway activation epoch. Native mutations additionally carry the captured workspace token. The backend uses the exact same runtime factory and relational domain service as tools. The Desktop and backend enablement gates remain separate and opt-in. See NATIVE_DESKTOP.md for install and validation details.

Official Desktop reference: https://hermes-agent.nousresearch.com/docs/developer-guide/desktop-plugin-sdk

## Catalog and release gates

Catalog metadata must identify a verified repository owner and pin an exact reviewed 40-character plugin commit. A template is intentionally not submitted. Public distribution requires privacy/secret review, dependency review, install instructions, declared capabilities and truthful compatibility floor. No automatic self-update or core patching is included.

Contest requirements were checked against the official Nous Research announcement: November 11, 2026 at 5 PM EST (22:00 UTC); open catalog PR, under-90-second working X demo tagging @NousResearch and form links. These are preparation notes only. No PR, social post or form submission is authorized by running this code.
