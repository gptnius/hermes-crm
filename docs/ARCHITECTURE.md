# Architecture and safety

## One domain service

`hermes_crm/domain.py` owns validation, transactions, storage, audit entries and scheduling state. Native `native_api.py`, agent `plugin.py` and optional standalone `web.py` call this service. The native adapters share `runtime.py` for profile and backend selection. No extra LLM is required to create or edit a record.

Tables are crm_contacts, crm_deals, crm_tasks, crm_activity, crm_idempotency and crm_settings. All mutating record operations write audit activity in the same transaction. No tool accepts arbitrary SQL, shell text or network destinations.

- IDs: UUID strings.
- Money: non-negative integer cents, USD only in this prototype.
- Dates: due times require an offset and are normalized to UTC.
- Updates: require a version. Competing changes return a conflict rather than silently overwrite.
- Creates: stable idempotency keys return the original result; reused keys with changed input fail.
- Links: foreign keys plus explicit validation. A task's contact must match the selected opportunity.
- Text: bounded, rendered as escaped content. Notes remain untrusted data, not agent instructions.

## Reports and terminology

Stage describes the six deal stages. Contact type describes the existing lead/customer/partner category, retained under the legacy `lifecycle` field without converting data. Contact reports use correlated linked-record predicates, literal escaped search and server-side filters before pagination. A true filtered total counts unique contacts; a contact can appear in multiple stage reports. Dashboard value shares include all six stages, including Won and Lost, and describe current state rather than historical funnel conversion. Missing/overdue follow-up presets describe stored tasks, not guaranteed agent execution.

## Profile boundaries

Native operations resolve Hermes' plugin_data_dir and plugin_db on every call. No global DB connection caches a previous profile. SQLite uses Hermes' connection policy. PostgreSQL uses a dedicated crm_ schema derived from the active profile's resolved data directory and reads the connection secret through the host profile scope.

The standalone web server is a different mode: one explicitly selected workspace per process. HERMES_CRM_DATA_DIR is an intentional local override. It does not switch when a user selects another Desktop chat profile. Users should not point two profiles at the same overridden SQLite directory unless they intentionally want the same workspace. PostgreSQL standalone mode requires explicit schema selection.

## Scheduling state

Saving a task creates no timer. crm_followup_schedule performs a native cronjob_manage create for the task's explicit UTC due date, with local delivery and only the crm_read toolset enabled, plus the host no_mcp sentinel to prevent implicit MCP expansion. The prompt contains a record ID, not user-supplied notes. It reads the task again when fired and treats completed tasks as no action needed.

Before dispatch, the record atomically enters scheduling. A concurrent request cannot create a second job. A success response with job ID records scheduled. Any unproven error, exception, malformed response or saved-but-unregistered result records uncertain and preserves a known ID. Automatic retry-create is blocked. The operator must inspect Hermes jobs before any reconciliation. This prototype intentionally has no reset button that could create duplicates.

Job creation is not execution confirmation. Hermes' gateway must be running. Completing a task does not delete the host job. A scheduled task's due time cannot be edited through CRM until its host schedule is managed; schedule reconciliation UI is deferred.

## Native Desktop boundary

The unified package ships `desktop/plugin.js` and `dashboard/plugin_api.py`. The Desktop contribution is a real React pane/page, not an embedded web server. It imports only the public SDK and host React. All requests use ctx.rest inside /api/plugins/hermes-crm. Hermes supplies authentication, enablement and profile routing, including isolated secondary-profile hosts.

The UI keys all record/form state by connection, active app profile, gateway activation epoch and a synchronous monotonic connection-state generation. It pauses requests when disconnected, rejects stale clients across reconnects, discards stale responses and captures a workspace token when a form opens. Every native REST write checks that token against the current database, so late requests cannot silently create records in a different workspace. The token is an opaque scope marker, not an authentication credential. Timers, listeners and contributions are disposed with the pane/plugin.

Demo seeding requires an explicit confirmation, refuses existing records, and inserts records/activity in one transaction. It locks out concurrent writes during the emptiness check and rolls back fully on interruption.

## Optional standalone web threat boundary

The server binds to 127.0.0.1. It rejects unknown Host headers and cross-origin browser writes, requires JSON writes and adds a restrictive content security policy. It does not implement user authentication. Any process running as the local user may access it. Do not bind or proxy it to a public interface. This is not a multi-tenant production security design.

## Backend portability

SQLAlchemy owns dialect differences, bound parameters and schema mapping. SQLite enforces foreign keys. PostgreSQL needs an explicit crm_ schema and never falls back. Backend initialization errors are not returned with credential-bearing URLs. Portability tests must include an actual disposable PostgreSQL runtime; DDL compilation alone is only a syntax check.

## Future work

Introduce schema migrations, pagination beyond contact reports and scalable aggregate queries before large datasets. Add authentication, authorization, backup/restore and operational health before remote hosting. Expand the verified native Mac workflows to broader platform, responsive-layout and accessibility coverage. Add a safe schedule reconciliation flow only after inspecting real host states and cancellation semantics.
