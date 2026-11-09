# Record links and bounded file attachments: next-package plan

Status: **proposal only; not implemented**. This document describes the next
attachment increment, not shipped capability or native end-to-end verification.
CRM baseline inspected: tree `e07ab221de1a96fe947ec4ec6b7cbf50b70bc6f5`.
Official Hermes contracts inspected at commit
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.

## Current capability and supported host contracts

CRM has no general attachment store, upload route, or Files UI. Textual references
in Notes are not stored files. This core edition ships no mailbox integration;
CSV transfer is a special-purpose import/export flow.

The official desktop SDK supports single-file multipart uploads through
`ctx.rest(path, {method: 'POST', upload: {filename, contentType?, bytes}})`, where
`bytes` is an `ArrayBuffer`:

- [Desktop REST types and scoped transport](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/apps/desktop/src/api/plugins.ts)
- [Official SDK documentation](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/website/docs/developer-guide/desktop-plugin-sdk.md)
- [Native Kanban attachment upload example](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/apps/desktop/src/plugins/kanban/api.ts)

The same SDK documents `captureGatewayFileDownload()`: capture it before the
associated backend request and retain the resulting function with that result.
It preserves connection/profile binding and accepts a backend-issued persisted
path and safe suggested name. Invoke it only on Download. Its promise settling
does not prove that a file was saved; cancellation is possible.

[CRM contact transfer](../desktop/contact-transfer.js) already uses a standard
file input and `File.arrayBuffer()`. This is the proposed selection route: no
arbitrary local path input, new folder grant, or host-internal API is needed.
Selecting a path is not a read grant. Chat staging and managed-files routes have
separate ownership/lifecycle contracts and are not CRM persistence. Record upload
does not attach content to a conversation or authorize model access.

Source support is not native integration proof. Verify the actual CRM bridge,
multipart backend, remote/local scope binding and downloads before release.

## User-visible increment

Provide a shared **Files and links** section for Company, Contact, Event, Deal
and Task. Show exact record identity, source type, title, creation time and archive
state. Links and stored files must be visibly different.

### HTTPS links

Add a title and HTTPS URL to an exact record. State: **Link only; content is not
stored or read.** Saving/listing a link must not fetch it, resolve DNS, create a
preview, test access or start research. Open is an explicit external-navigation
action through the supported host contract. Do not promise referrer controls the
host cannot supply. External access may require sign-in or expire.

Reuse reviewed URL validation patterns in
[research_models.py](../hermes_crm/research_models.py): bounded text, no controls,
embedded credentials, malformed escapes, secret-bearing query parameters, local
paths or non-HTTPS schemes. This is not exhaustive secret detection. Preserve
meaningful query/fragment components; do not silently rewrite the resource.

### Stored files

Select one file, review filename, byte count, exact record and destination
host/profile, then explicitly Upload. Selection alone sends nothing, performs no
research and grants no persistent directory access. A remote Hermes host is a
remote destination; configured PostgreSQL is also the storage destination and
must be disclosed. No new bucket, provider, service or credential is proposed.

**Proposed product limits, not current capability or host limits:** 2 MiB decoded
bytes per file and 8 MiB retained decoded bytes per workspace/profile, including
archived content. Verify these against actual bridge/proxy behavior and memory
usage. Account for base64, JSON and multipart overhead. No automatic deletion
when a quota is reached.

Initial formats: PDF, UTF-8 TXT/CSV, PNG and JPEG. Validate extension, declared type,
actual byte count and applicable signatures/encoding on the server. These checks
are not malware scanning or a guarantee that a document is safe. Store/download
only: no inline rendering, thumbnails, extraction, OCR, execution or archive
unpacking. DOCX/PPTX and EML require a later reviewed format policy; offer a URL
link or PDF export meanwhile. Reject executables, scripts, HTML, SVG, archives
and unsupported formats with a specific explanation.

Archive/Restore is reversible metadata state. Archived content still consumes
quota. No purge, automatic cleanup or version-replacement editor is required for
this increment; upload changed content as a new attachment. Never silently merge
records, attachment identities or provenance.

## Transactional storage proposal

Prefer a small DB-resident store over authoritative profile-local blob files for
this increment. Use additive versioned tables with exact workspace/profile scope,
canonical IDs, target kind/ID, title/source metadata, archive state and immutable
payload identity. Validate all five target kinds and current target version in
the write transaction. Metadata is not an independent authorization boundary.

Store immutable bytes as canonical base64 in a separate bounded String payload
column, with server-computed SHA-256 and decoded byte count. Keep payloads out of
metadata queries and results. Base64 costs approximately one-third extra space,
but fits the existing JSON export and recovery column contract. Raw LargeBinary
would require additional serialization and recovery type support; it is not a
drop-in change. SQLite and PostgreSQL both hold metadata and bytes transactionally,
avoiding a distributed file/DB commit or separate blob restoration protocol.

**Ordinary database content is plaintext**, including base64 bytes, filenames,
URLs and metadata. Base64 is not encryption. Existing protected-notes keys do not
protect attachments. DB replication/backups and remote database configuration
remain relevant exposure surfaces.

Use scoped operation IDs and canonical request digests covering target identity,
expected version and exact content/link intent. Same-key same-request retry returns
the original receipt; changed intent conflicts. After uncertain outcomes, freeze
that operation and recover its receipt rather than starting another upload. Never
reread a changed source file as a retry of the original bytes.

Simple operation idempotency is required; physical byte deduplication is optional.
If implemented later, deduplicate only verified identical bytes within the exact
scope, without merging identities, titles, attribution or record associations.
Never reveal cross-scope existence through deduplication responses. Initial
accounting may count each independently stored payload, including duplicates.

Reads must not initialize schema. Reject partial/incompatible schema families.
Reuse [relationship storage](../hermes_crm/relationship_store.py),
[report storage](../hermes_crm/report_store.py) and catalog locking patterns for
scope, transactions and optimistic concurrency. Keep audit records bounded and
content-free. Avoid raw content, signed URLs and sensitive metadata in diagnostics.

## Upload, download and privacy boundaries

Enforce request size before multipart parsing/spooling, not merely after
`request.body()` buffers the request. Bound actual streaming bytes as well as
metadata/field counts, reject malformed or duplicate fields, and verify the
decoded file limit independently. Client checks improve UX but are not enforcement.
Quota accounting and writes must be serialized appropriately on both databases.

All content operations use opaque attachment IDs and the verified scope. Never
accept a filesystem path to read. Original filenames are bounded display/download
metadata, never storage paths. Validate ownership and target association on each
read/download/archive operation.

For native download, materialize verified DB bytes into a bounded private
profile-owned cache using reviewed patterns from
[contact_transfer_runtime.py](../hermes_crm/contact_transfer_runtime.py): generated
names, owner/mode/link checks, no-follow opens, byte-count/hash verification and
concurrency protection. Return only server-generated persisted paths to the
captured download function. This cache is expendable, not authoritative storage,
and is not part of the attachment backup. Missing cache can be regenerated from
verified DB bytes; corrupt content must fail closed. Cache retention and storage
limits require explicit handling, without deleting authoritative attachments.

Clear picked bytes and invalidate UI on close, disposal, record change or
connection/profile/gateway transitions, including A-to-B-to-A. Prevent stale
submission and late responses updating a newer view. Avoid browser persistent
storage. Review request logs, proxy buffering, telemetry and temporary-file
retention; do not promise secure erasure.

Keep new content and unreviewed private metadata out of existing agent defaults,
record projections, activity summaries and scheduler/research prompts. See
[agent_read_policy.py](../hermes_crm/agent_read_policy.py). Metadata-only listing
is not content access. A later explicit research handoff must identify exact
content and destination, obtain applicable permission and treat content as
untrusted data. No automatic provider upload or model ingestion is in this scope.

## Encrypted export and existing recovery

Fresh-target content recovery **already exists**; see
[BACKUP_RESTORE.md](BACKUP_RESTORE.md) and [recovery.py](../hermes_crm/recovery.py).
It validates an encrypted snapshot and restores into a new private destination,
with execution/provider state quarantined. It is not full Hermes disaster recovery
or automatic live cutover. Archive Restore is a different operation.

Attachments must be included coherently in supported content export/recovery
before claiming their recoverability. Required implementation changes:

1. Add the complete attachment schema family to
   [protection.owned_tables()](../hermes_crm/protection.py), schema checks and
   scoped snapshot selection. Export metadata, immutable payloads, associations,
   archive state and relevant operation receipts in one consistent snapshot.
2. Extend snapshot validation for exact scope, canonical IDs, valid target kinds
   and existing record associations, payload references, canonical base64,
   decoded size, signatures/types and SHA-256. Reject orphan/partial families,
   tampered bytes and inconsistent receipts; do not trust polymorphic references
   simply because SQL constraints pass.
3. Extend recovery's schema-family completeness and semantic validation before
   writing the fresh target. Preserve content and original scope; never restore
   source filesystem paths or download-cache files. Keep existing quarantine and
   no-live-cutover behavior unchanged.
4. Verify encrypted export/decrypt/fresh-target recovery with active and archived
   attachments, all five target kinds, links, receipts and duplicate payloads.
   Confirm ordinary recovered bytes remain plaintext in the database.

The current whole-snapshot plaintext export cap is **32 MiB**. The proposed
8 MiB decoded attachment quota adds roughly 10.7 MiB base64 plus metadata; it does
not guarantee space for an arbitrarily growing CRM. Measure serialization memory
and enforce existing export limits. Surface an explicit capacity failure, never
silently omit files or claim a metadata-only export is complete. Export encryption
does not encrypt the live DB, download cache or downloaded copies. External links
are backed up as references, not destination content or access grants.

## Migration and rollback

Create additive tables only on an explicit feature write/configuration path;
keep existing record tables unchanged. No auto-import from Notes or email history.
Gate writes on supported transport and scope binding. Rollback disables the UI
and writes while preserving new data and receipts. Older builds must not falsely
claim complete attachment exports. No destructive migration is part of this plan.

## Acceptance and release gates

- SQLite/PostgreSQL parity: no read-time initialization, schema-family integrity,
  transaction/locking races, all five record kinds, missing/archived targets,
  optimistic versions, forged tokens and cross-profile/workspace references.
- Same-key retry, conflicting intent, repeated clicks, interrupted upload, failed
  DB commit and uncertain outcome recovery; concurrent quota enforcement.
- Oversized streams rejected before multipart parsing/spooling; declared versus
  actual lengths, malformed/duplicate fields, excessive metadata, filename
  traversal/controls, MIME/extension spoofing, invalid UTF-8 and signatures.
- Archive/Restore and retained-byte accounting, duplicate files without silent
  merging, deterministic metadata pagination and payload-free ordinary queries.
- No URL fetch/DNS/preview at save/list time; no automatic extraction, active
  rendering, model call, provider upload or arbitrary local read.
- Native local and remote synthetic-file tests: selection cancellation, review
  before transmission, real multipart round trip, bridge/proxy size failures,
  close/reopen, double clicks, profile/connection changes, A-to-B-to-A and plugin
  disposal. Missing capability names the required host feature, not a generic
  refusal. Source inspection alone does not satisfy this gate.
- Captured download binding, explicit gesture, safe name, cancellation without a
  false saved claim, cache regeneration, corruption, symlinks/hardlinks,
  FIFOs/devices, wrong owner/mode and concurrent materialization.
- No payload in agent defaults, audit/error/metadata responses, logs, telemetry,
  browser persistent caches or scheduled prompts; existing notes boundaries hold.
- Encrypted export/recovery drill and negative tests for changed hashes, scope,
  target links, payload references, partial schema families and snapshot size.
  Verify recovered bytes exactly and keep execution/provider state quarantined.

Implementation order: validate contracts and limits, add HTTPS references with
export/recovery coverage, verify native upload transport, implement bounded
transactional files and downloads, then pass cross-engine/native/privacy/recovery
gates. Research ingestion is a separately designed increment.
