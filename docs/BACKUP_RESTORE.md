# Offline CRM content recovery

This is a fresh-target **CRM content restore**, not a full Hermes backup or an
in-place restore. The encrypted export excludes host settings, credentials and
keys, attachments, chat transcripts, and filesystem content. Its original
workspace ID, exact profile name, and retained export and notes keyrings are
required. Lost keys cannot be regenerated to recover old ciphertext.

## Mandatory cutover boundary

**Do not connect this restored database to a live Hermes host until an operator
has stopped/fenced the old workspace's jobs, dispatches and writes, reconciled
uncertain external operations, reviewed the recovered records, and approved the
cutover.** The source workspace identity is preserved, not newly generated.
Source host jobs are outside the export and are not cancelled by recovery.
Never run both source and restored copies under that identity. The tool neither
starts a host nor changes a profile, credential, provider, schedule or setting.
The same exact profile name is needed to reveal notes and access scoped records.
A real cutover, key provisioning and fresh scheduling are separate operations.

## What is restored and what stays inactive

`python -m hermes_crm.recovery` consumes the native downloaded encrypted export
artifact, not an arbitrary database dump. It authenticates the operation MAC and
AES-GCM envelope, validates the known table/column contract, required base and
customization tables, complete optional schema families, supported schema
versions, column types, primary/unique keys, declared foreign keys, row scope,
workspace marker and polymorphic note/custom-value record references. Every
protected note must authenticate and decode with its retained notes key before
any destination is created. Notes remain encrypted on disk. Protected operation
receipts require their historical MAC keys too.

A new directory contains:

- `recovery.sqlite3`: current app-compatible CRM schemas and recovered records.
  Ordinary notes and fields are **plaintext**, as in the normal CRM datastore.
- `recovery_*` tables in that database: original exported rows for inspection,
  including original task schedule fields and quarantined runtime history.
  The CRM does not query these prefixed tables.
- `manifest.json`: completion marker with source export identity, exact scope,
  source artifact and recovered database SHA-256, row counts, verified-note count
  and transformation flags. This is provenance, not an external signature.

Contacts, deals, tasks, companies, events, ownership, reports, research,
customization, activity, encrypted notes and safe local operation/idempotency
receipts are restored when present. Retaining local receipts prevents an old
uncertain local create/save from duplicating recovered records. Receipts remain
historical results, not proof of the record's latest state. Protected export
reservations remain, but old export artifacts are not recreated or claimed saved.

Native-work, scheduled public-research assignments/receipts, experimental agent
execution and Gmail tables are created empty.
Their original rows remain only in `recovery_*` quarantine tables. No dispatch,
provider connection or external-operation replay is restored. Tasks have
`schedule_status='none'` and `scheduler_job_id=NULL`; all other task fields remain
unchanged except that a task whose schedule fields change receives an incremented
record version and new updated timestamp, fencing stale pre-restore edits.
Original rows remain in quarantine. The discarded runtime receipts must **not** be automatically retried:
reconcile their outcome at the original host/provider before any fresh action.

## Run an isolated recovery

Use the installed project Python environment. Pass the original workspace/profile
explicitly and choose a target directory that does not yet exist, in a private
parent directory you control. Never use the active profile's data directory.

```sh
python -m hermes_crm.recovery \
  --artifact /private/recovery-input/export.json \
  --workspace ORIGINAL_WORKSPACE_ID \
  --profile ORIGINAL_EXACT_PROFILE_NAME \
  --target /private/recovery-review/new-target \
  < /private/recovery-input/retained-keyrings.json
```

The piped JSON input is an object with `backup` and optional `notes` keys, each
containing the existing `{ "active": ..., "keys": ... }` keyring object described
in [PROTECTION.md](PROTECTION.md). Notes keys are required when notes or protected
operation receipts exist. This tool does not generate keys or discover credentials
from the host/environment. Supply rings using your already-approved key custody
process; the example file is not a recommendation to leave keys beside a backup.
Never paste real keys into shell arguments, chat, source control, logs or examples.
The API `restore_content(artifact_bytes, backup_ring=..., notes_ring=...,
workspace=..., profile=..., target=...)` also accepts keyrings already in memory.

Exit zero and a complete manifest mean the isolated content restore succeeded.
The tool reads back restored rows and runs SQLite integrity and foreign-key
checks before completing. The target directory is mode 0700 and files 0600.
Existing directories, files and symlinks are refused, including concurrent
attempts to create the same target. Authentication and validation failures create
no target. A storage failure can leave an incomplete private directory; do not
open it as a CRM or retry into it. Preserve it for review and use a new target.
Do not treat a partial/invalid manifest as success. Compare the database digest
before first opening; subsequent normal CRM writes change it.

Files are fsynced, but target/parent directory entries are not. Successful output
therefore does not guarantee durability through sudden power loss. Retain the
original export and keys. After a restart, verify the manifest, database integrity
and recorded digest before opening or cutover; if incomplete, restore again into
a new target rather than reusing or overwriting the damaged directory.

A later normal encrypted export enumerates only known CRM tables, so it excludes
the `recovery_*` quarantine copies and the recovery manifest. Preserve the original
export, key custody material and this recovery provenance separately if needed.

## Recovery limits and remaining release gates

- Only current export/schema version 1 and SQLite destinations are supported.
  No profile rename/rebinding, PostgreSQL destination, merging, overwrite,
  automatic key rotation, or production cutover is implemented.
- Export v1 has no separately authenticated full-datastore inventory. Recovery
  rejects missing required tables and partial optional families, but cannot
  distinguish a completely omitted optional family from one never initialized.
  Export producer coverage must be reviewed; a successful restore is not proof
  of a complete installation backup. Unknown tables/types and mixed scope fail
  closed. This is structural recovery validation, not a re-audit of every past
  business rule, receipt payload or external observation.
- Restoring a snapshot cannot recover writes or idempotency receipts made after
  it. Reconcile post-snapshot uncertain work before retrying. Quarantined rows
  retain ordinary sensitive data and need the same access/retention care as CRM.
- Private permissions do not defend against the same OS user, an administrator,
  a compromised process, or an attacker controlling the destination parent.
  Process-memory plaintext and secure deletion are not guaranteed.
- Synthetic tests exercise functional content recovery, relationships and local
  receipt replay, rotated retained keys, wrong/missing keys, authentication,
  malformed/incomplete schemas, invalid references, runtime quarantine,
  no-overwrite and interrupted output. Real-data, real-host cutover and disaster
  recovery remain operator drills, not claims made by these tests.

## Scheduled research history

Encrypted exports include `crm_scheduled_research_v1` and
`crm_scheduled_research_ops_v1` together, scoped to the exact workspace/profile.
Payload digests, Task/target references, source/proposal ownership and authenticated
report identity are validated. Historical source versions may be older than
current records. A stale-source blocked report remains a blocker, not completion.

Recovery keeps both original tables only under `recovery_*`; their app-runtime
counterparts are empty. Ordinary research evidence and pending proposals remain
reviewable content, but no job/execution binding or ability to replay a scheduled
write is restored. Source jobs must still be fenced separately before cutover.

## Report acknowledgements

The optional report-review event/operation family is exported with scoped
identity, context, sequence and immutable receipt validation. Original review
events are retained only under `recovery_*` on restore, with empty live review
tables, because their native/scheduled assignment references are quarantined too.
Recovery does not revive approval or scheduling authority; **Reviewed in CRM** is
not a named-human identity or quality-approval assertion.
