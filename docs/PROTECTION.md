# Layered protection: first increment

This is an optional, local-user prototype, not a security or compliance
certification. Ordinary CRM use does not require an encryption key. No key,
account, secret source, role, network setting or provider is configured by this
feature. Existing records are not migrated or erased.

## What each layer does

| Layer | Current behavior | Boundary |
| --- | --- | --- |
| Default agent output | Base contact/deal/task reads and mutation responses omit ordinary notes and all custom values; overview omits audit/backend/workspace internals. | Names, email, company, titles, stages, dates and aggregate counts remain visible. Not record authorization or a sensitive-data classifier. |
| Explicit ordinary-field read | `crm_record_fields` in `crm_detail_read` accepts exact `notes` for Contacts/Deals/Tasks/Companies/Events, `custom.<known_key>` for Contacts/Deals/Tasks, or `outcome_summary` for Events. It returns the current record version. | No wildcard, protected-note or arbitrary path access. Granting this tool permits ordinary-data reads; it is not a human-consent check. |
| Protected notes | A separate optional note per contact, deal or task is authenticated-encrypted before database persistence. Native controls require explicit reveal. | Ordinary Notes and custom fields remain unchanged and plaintext. Running host code and the local OS user can access configured keys. |
| Encrypted export | Explicit native action creates an encrypted consistent snapshot of known CRM tables, then offers the host's native Save dialog. | Offline fresh-target SQLite content restore is available; not a full Hermes backup, live restore, or proven disaster-recovery system. Keys, host files and attachments are excluded. |
| Profile and version checks | Existing authenticated native transport, connection generation, workspace token and expected record/note versions apply. | No new human identity, shared-user roles or tenant authorization is introduced. |

The dedicated field-reading tool is not added to fixed scheduled reminder or
assigned-work allowlists. The absence of a host cron identity does not prove
that a caller is interactive: delegated agents can also lack that identity.
This increment deliberately makes no universal scheduled record-scope claim.

## Inventory of ordinary copies

Ordinary Notes and custom values can already be present in record rows, create
receipts, user-authored report definitions/results, assigned-work instructions,
criteria, result reports, activity/contact logs, provider observations, native
chat transcripts, explicit CSV export artifacts/downloads, database journals
and earlier backups. The ordinary UI and
explicit report/work tools can still expose those ordinary values. Minimizing
base tool responses does not remove these existing copies or prevent an agent
from reading permitted data using another capability.

Do not paste credentials or protected text into ordinary fields, report names,
task titles, agent prompts or contact logs. Moving text into a protected note
later does not erase earlier plaintext copies. No automatic conversion or
secure-delete feature is provided.

## Key source and custody

The optional declared secrets are:

- `HERMES_CRM_NOTES_KEYS`: protected-note encryption and keyed request receipts.
- `HERMES_CRM_BACKUP_KEYS`: encrypted content export and artifact authentication.

Both are resolved on every operation using Hermes's supported, profile-scoped
`agent.secret_scope.get_secret` interface. CRM does not directly inspect `.env`,
a browser vault, a keychain, another profile's files or provider credentials, and
does not add its own environment fallback. Missing or malformed configuration
fails closed for that optional operation; ordinary CRM remains available.

**A masked Hermes plugin secret field is not necessarily encrypted storage.**
The tested host can persist that field in ordinary plaintext `.env`. Its
supported external secret sources must be independently configured and reviewed
by the user. CRM does not create, configure or verify an external secret manager.
Do not assume storing keys beside the database protects a copied home directory.

Each secret is a bounded JSON keyring with `active` and `keys` entries. The
`keys` mapping contains one to eight stable key IDs, each mapped to an unpadded
base64url encoding of exactly 32 random bytes. IDs use letters, digits, `_` or
`-`, with a maximum length of 64. `active` identifies the key for new encryption.
Use independently generated keys for the two rings. Do not reuse a provider API
key, password, example test value or a real key in a Git commit or chat.

Actual key generation, provisioning, recovery custody and any new persistent
secret-source access are separate user actions, not part of installation or
this increment's tests. Keep recoverable copies of both rings outside the
exported data, according to your own access and backup policy. Replacing the
active ID does not re-encrypt old notes or exports. Removing an old key can make
old data and replay verification permanently unavailable. There is no automated
key rotation, escrow, revocation or key-recovery workflow.

## Native protected-note workflow

1. Open a record and select **Protected note**. The drawer reads configuration
   status and note metadata without decrypting content.
2. Select **Reveal protected note**, then **Edit protected note** if needed.
3. Save explicitly. Both the record version and protected-note version must
   still match. The note, incremented record version, metadata-only operation
   receipt and redacted activity entry commit together.
4. Close, cancel or change the active view/profile to clear the drawer's text.
   This is application-state cleanup, not cryptographic memory erasure. Revealed
   plaintext necessarily exists in the response and process memory.

Protected content is not included in ordinary snapshots, agent tools, reports,
audit summaries, clipboard actions or local browser storage by this feature.
Routes are mounted only in the Hermes-authenticated native component, not the
standalone web demo. That is transport scoping, not proof of a human caller or
a defense against privileged code running inside the same host.

Protected responses use `no-store`; validation and failure responses are
sanitized rather than echoing request text. An uncertain save retains only its
operation identity and versions in UI state. **Check save outcome** queries a
scoped metadata receipt, not plaintext and not a replay. A missing receipt is
not proof that a write did not occur. Do not make a replacement write merely to
resolve uncertainty.

## Cryptography and storage

The `cryptography` library supplies AES-256-GCM with a fresh random 96-bit nonce.
HKDF-SHA256 derives purpose-separated keys. The authenticated envelope carries
a version and key ID; its authenticated context binds the workspace, exact
profile name, record kind/ID and note version. The export envelope binds the
workspace and exact profile name. Note request receipts store a keyed MAC, not
the plaintext request or an unkeyed plaintext hash.

Protection tables are additive and versioned. Partial, malformed or unsupported
schemas are rejected without destructive repair. Existing ordinary data is not
encrypted in place. The threat addressed is a copy of the protected ciphertext
without the corresponding keys, not a compromised running host, malicious
privileged plugin, authorized model with shell access, local administrator,
screenshots, process memory or a backup that also contains the keys.

## Encrypted export and recovery limits

Use **Encrypted export** in the native CRM toolbar, then **Prepare encrypted
export** and **Download encrypted export**. The supported SDK download function
is captured before the preparation request so it stays bound to that
connection/profile. Its promise settling does not prove a file was saved:
Hermes shows the native Save dialog and outcome. Cancellation leaves the
prepared ciphertext in the profile's plugin export directory.

Only explicitly enumerated CRM tables are captured through a consistent
transaction. The payload includes ordinary records, stored receipts, reports,
assignment state and encrypted protected-note rows. No plaintext temporary
database is created. Keys, `.env`, host configuration, native chat history and
arbitrary filesystem content are excluded. The envelope itself exposes format,
key ID and scope identifiers; it is not metadata-anonymous encryption.

Preparation is bounded to a 32 MiB decoded snapshot, 20 retained artifacts and
256 MiB of artifacts in the plugin export folder. Files are created privately;
there is no automatic retention deletion. Review retention outside the app
without deleting recovery material you still need. Preserve the original
operation identity when investigating an uncertain preparation rather than
creating another export blindly. **Check export outcome** only inspects the original
receipt and artifact. A durable reservation prevents the same operation ID from
capturing a newer snapshot after cleanup or an interrupted write. A missing or
unverified artifact remains unresolved; it is not recreated by that check.

`decrypt_export_artifact` provides offline authenticated inspection and payload
shape validation. The [offline restore CLI](BACKUP_RESTORE.md) implements usable
CRM content recovery into a new SQLite target, with synthetic service read/write
and failure-path evidence. It preserves safe local receipts, validates schema,
references and retained note keys, and quarantines execution/provider history.
Ordinary fields and notes are plaintext in the recovered database; protected
notes remain encrypted. There is no in-place restore, restore UI or automatic
live cutover. A successful export/restore is not proof of a complete Hermes
backup: export v1 has no separate full-table inventory, so a completely omitted
optional family cannot be detected. Real-data/host disaster and cutover drills
remain release gates.

Recovery also requires the original workspace identity and exact profile name.
Renaming a profile or moving rows into a fresh workspace prevents normal note
reveal. The restore preserves the original identities; profile rebinding and
PostgreSQL destinations are unsupported. Before connecting a recovered copy to
a live host, the operator must stop/fence source jobs, dispatches and writes and
reconcile uncertain external operations. Recovery does not cancel host jobs. The export key decrypts the
outer snapshot only: protected-note rows still require their retained notes
keys. Do not discard either ring or assume a fresh profile can open copied rows.

## Remaining work

- Real-host cutover/disaster drills, key rotation and profile-rename/rebinding.
- Durable policy enforcement for records/fields across all agent, report and
  delegated-execution paths, with human roles where needed.
- Inventory and retention controls across transcripts, journals, earlier
  receipts/backups and provider-derived content.
- Database role and TLS verification for remote storage, larger-data limits,
  additional accessibility and physical native Save-dialog testing.

Import/export for routine data portability follows this protection increment;
external CRM linking remains deferred. See the [README roadmap](../README.md#development-roadmap)
and [verification record](VERIFICATION.md) for implemented versus planned scope.

## Verified host interfaces

These claims are tied to official host source revision
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, not every Hermes release:

- [Declared secret access contract](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/plugin-catalog/README.md)
  and [profile-aware secret API](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/agent/secret_scope.py).
- [Plugin configuration guide](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/website/docs/developer-guide/plugins/index.md),
  including masked secret fields and environment persistence.
- [Native file-download SDK contract](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/website/docs/developer-guide/desktop-plugin-sdk.md)
  and [download implementation](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/apps/desktop/src/lib/media.ts).
