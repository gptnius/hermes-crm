# Choose storage in native HermesCRM

SQLite is the default and the easiest starting point. It does not need a database
server, credentials or PostgreSQL administration. Its database lives on the
**Hermes gateway** in the active profile, not necessarily on the computer showing
the Desktop UI. A gateway on a VPS keeps SQLite on that VPS.

PostgreSQL is optional for people who already operate a PostgreSQL database on a
computer, VPS or another host and want its server-management/concurrency features.
It is not automatically better for a small personal CRM. HermesCRM does not
provision a database or manage its availability, users, network access or backups.

## Connect through Settings

1. In HermesCRM, open **Settings → Storage**. The card reports the saved backend
   independently of the normal CRM snapshot, so it remains usable when a bad
   database configuration prevents records from loading.
2. Select **Open Hermes plugin settings**. This opens the supported Hermes
   **Settings → Plugins** page, handing off the active app profile. Select
   **HermesCRM**, then **Agent settings** if shown. It is a settings landing link,
   not a direct link to the URL field. Verify the profile in the host settings.
3. Choose **SQLite** or **PostgreSQL**. For PostgreSQL, put the database URL in
   **PostgreSQL connection URL**, then save in Hermes. Use TLS for a remote
   database. The role used by normal CRM operations needs permission to create
   its profile schema and tables. Use a dedicated role/database with the minimum
   required privileges. Do not paste credentials into CRM records, chat or source
   control. Hermes owns this credential entry; the CRM panel has no secret input.
4. Return to CRM and select **Reload storage settings**, then **Check saved
   connection**. If changed credentials or a driver remain unavailable, restart
   the relevant gateway using Hermes controls. The plugin never restarts it for
   you or switches the active connection/profile.
5. Return to the overview to load records. Ordinary CRM operations initialize or
   upgrade CRM tables as necessary. Back up an existing datastore before updating.

The pinned host masks secret fields but may persist their values in the profile's
plaintext `.env` file. Masking is not an encrypted vault. The host leaves a blank
secret field unchanged. Protect that host/profile and keep backups securely.

PostgreSQL's driver is a normal plugin dependency. Existing installations that
lack it should update/reinstall using Hermes's supported plugin installer for the
relevant gateway, rather than installing into an unrelated Python environment.
The `postgres` extra remains available for existing packaging commands.

## What changing storage does

Changing the backend or URL **does not migrate, upload, merge or delete existing
records**. A different selected store may therefore look empty. Existing records
stay in their original store; switching back selects that store again. Keep full
backups and plan any migration separately. Contact CSV transfer is not a full CRM
migration, and the storage card does not perform restore or cutover.

Review scheduled CRM work before a storage cutover. Native scheduler jobs are
separate from the database: changing storage neither migrates nor cancels them.
Keep the original store and reconcile existing jobs through the supported Hermes
controls; do not assume a storage switch cancels already-running work.

Native PostgreSQL retains the existing `crm_` schema derived from the gateway's
resolved profile data location. Separate profiles stay in separate namespaces.
Pointing another installation at the same database is not automatic shared-
workspace or cross-device synchronization, and these namespaces are not database-
role access-control boundaries. No schema selection or new grants are added here.

## What the connection check proves

The check is an explicit, authenticated, active-app-profile request. It reads only
the saved configuration; callers cannot supply a different endpoint, path, schema
or URL. An opaque selection token rejects checks after the saved backend, URL or
profile changes. Returned errors use fixed categories, not credentials, hostnames
or driver error strings. No model tool or scheduled capability is added.

The diagnostic supports complete host/database/username/password URLs and a
current libpq driver with explicit authentication controls. It refuses ambient
`PG*` environment settings, service files, password-file fallback, client-
certificate authentication and OS/OAuth identity flows. Custom connections may
continue to work in normal CRM operations, whose behavior is unchanged; have the
database operator verify them rather than treating a skipped check as failure.
No environment is edited and no credentials are collected by the panel.

The PostgreSQL probe uses a read-only `SELECT 1`, with an eight-second overall
probe deadline, five-second per-connect timeout and three-second SQL timeout.
Known connections are closed before cancellation. It never opens the CRM domain
service, creates schemas/tables, migrates data, writes records or tests write
permissions. A successful check means connectivity worked, **not that the CRM
schema, permissions or migrations are ready**. The normal overview is a separate
operation with its existing initialization behavior.

The SQLite check opens only an existing profile database in read-only mode and
reads SQLite’s schema catalog; it does not create a missing file or change journal mode. SQLite
may maintain a shared-memory sidecar for an existing WAL database. A missing file
is reported as not initialized rather than created by the check.

Opening Storage reads saved settings, not the database, and stops new periodic
snapshot requests in that view. A normal CRM request already admitted before
opening Settings may still complete on the server; its late UI response is
ignored. Host configuration reads retain the host's own configuration handling,
which can create host configuration directories/backups. These diagnostics do
not promise zero host filesystem activity.

## Future storage work

Dedicated Supabase integration and guided provider setup are roadmap work, not
part of this release. The current choices are SQLite and PostgreSQL. No Supabase
account, API key, CLI, MCP connection or provider-specific workflow is required.
Hosted-provider end-to-end behavior has not been verified by the synthetic and
disposable database checks.
