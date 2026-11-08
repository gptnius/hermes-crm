# Record file links and managed uploads: implementation plan

Status: **proposal only**. This document does not enable attachments, authorize
implementation, or claim native end-to-end upload verification. Audited source tree:
`2801920b49b3851ed6eb6e1d4110c35972914587`.

## Current facts and reusable contracts

There is no general record attachment store, upload route, or attachment UI.
Ordinary Notes may contain textual references; those are not managed files.
Gmail history excludes message bodies and attachments. CSV transfer is a
special-purpose import/export workflow, not a general attachment feature.

Existing code offers useful patterns:

- `hermes_crm/relationship_schema.py`, `relationship_store.py`,
  `relationship_api.py`, and `relationship_tools.py`: exact record references,
  workspace/profile scope, optimistic versions, idempotency receipts, and
  explicit schema checks. Company archive and Event revisions provide examples.
- `hermes_crm/report_store.py`: scoped identity, SQLite transactions, PostgreSQL
  locking, and refusal to silently repair incompatible schemas.
- `desktop/contact-transfer.js`: human file input, selected bytes via
  `arrayBuffer()`, bounded input, explicit submission, scope-change invalidation,
  and original-operation recovery after uncertain outcomes.
- `hermes_crm/contact_transfer_runtime.py`: private profile-owned artifacts,
  opaque generated names, owner/mode/link checks, `O_NOFOLLOW`, bounded retention,
  byte count/hash verification, and reservation receipts. These are patterns to
  review, not a reusable attachment store or a comprehensive security guarantee.
- `hermes_crm/agent_read_policy.py`: minimal default agent projections and an
  explicit ordinary-field read path. Attachments must not bypass these boundaries.

Pinned official Hermes source provides a single-file multipart REST upload
contract: `upload: {filename, contentType?, bytes: ArrayBuffer}`. See
[Desktop REST types](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/apps/desktop/src/api/plugins.ts).
A browser file input followed by `arrayBuffer()` and this transport is the
candidate no-new-folder-grant upload path. It still needs real native integration
verification, backend multipart support, size enforcement, and scope tests.
The source contract is not proof that this CRM currently uploads files.

Native path selection is not itself a read grant. The SDK's folder-handle file
APIs are a separate permission-bearing alternative, not required for this plan.
No composer `attachFile` API was found in the inspected SDK. A record upload
must not pretend to attach the file to a model conversation.

## User-visible scope and stages

### Stage 1: HTTPS references

Provide an optional Files section on Company, Contact, Event, deal, and task
records. A user adds a title and an HTTPS URL to an exact record. Show the URL,
source/provenance, created time, and archive state. An explicit Open action may
navigate to it using the supported external-navigation contract. Saving a link
must not fetch the destination, create a preview, test access, or ingest content.

Accept only validated HTTPS URLs initially. Reject embedded credentials,
control characters, local paths, and schemes such as `file:`, `data:`, and
`javascript:`. Warn against signed/token-bearing private URLs. Do not resolve
DNS or make requests during validation. Preserve meaningful query/fragment
components rather than silently changing the linked resource for deduplication.
Use supported safe external navigation and referrer controls; do not promise
controls the host does not provide. A reference grants no access and may expire.

### Stage 2: managed uploads

The human selects one file using the native pane's standard file input. The pane
shows the exact target record, filename, size, and destination host/profile before
an explicit Upload action sends bytes through profile-scoped REST. Selection
alone does not upload, parse for research, or grant ongoing folder access.

The server owns storage names and locations. Do not accept arbitrary path-read
arguments from the UI or an agent. Prefer opaque attachment/revision IDs on all
subsequent reads and downloads. Original filenames are display/download metadata,
never storage paths. Download is a separate action and does not prove that the
user saved a copy.

Proposed initial limits, **not current capabilities or host guarantees**: one
file per request; 10 MiB maximum actual file bytes; 100 MiB retained bytes per
workspace/profile, including archived revisions and pending reservations. Confirm
these values against transport memory usage and host request limits before
implementation. Server enforcement is mandatory even with UI checks; reject
oversized streams before buffering all content and account for encoding overhead.
No automatic deletion when quota is reached.

A proposed first allowlist is PDF, plain UTF-8 text/CSV, PNG, and JPEG, with
server-side extension/type/signature consistency checks. Store/download only:
no inline rendering, thumbnail generation, OCR, extraction, or execution. MIME
checks are not malware scanning. PDFs and images are not guaranteed safe.
Initially reject executables, scripts, HTML, SVG, macro-enabled Office files,
archives, and rendered email formats. Supporting DOCX/PPTX proposals or EML
later requires a separate reviewed format policy; Office ZIP containers cannot
be supported by blindly allowing every ZIP or extracting its contents.

### Stage 3: optional research handoff, separately designed

No automatic content transfer to an LLM, conversation, scheduler, or provider.
If requested later, let the human select exact revisions, preview what will be
shared and the destination, and explicitly authorize processing. Keep model
input separate from attachment storage. Treat file content as untrusted data,
not instructions. Do not invent a composer capability or substitute filesystem
access to bypass a missing host API.

## Proposed data and operations

Use a separate additive, versioned registry rather than new overloaded Notes
fields. Validate the schema on SQLite and PostgreSQL. Reads must not create it.

- Attachment: scoped UUID, version, title, source type (`external_url` or
  `managed_file`), creator/actor, timestamps, archive timestamp, and provenance.
- Exact link: attachment ID plus target kind and ID within the same scope.
  Allow all five record kinds. Validate the target's current reviewed version
  and existence. Never link by company/person name or silently inherit links
  from another related record. Multiple record links do not duplicate provenance.
- Revision: immutable URL or managed-content reference, original filename,
  server-derived byte count/hash, declared/detected MIME, capture time, and source
  attribution. Replacing content creates a new revision; old revisions remain.
- Managed blob: opaque generated storage ID scoped to workspace/profile. Do not
  expose host paths in model-facing results. Metadata ownership is not an ACL.
- Provenance: source URL when appropriate, supplied author/source label, capture
  or upload timestamp, and a description of origin. A label is a claim, not
  verified authorship, public availability, or permission to share.
- Operation receipt: scoped stable key, canonical request digest, state, original
  result, and bounded diagnostic metadata. Never log raw content or signed URLs.

Use reviewed versions for link/unlink, metadata edits, archive/restore, and new
revisions. Retain audit history without copying file contents into activity
summaries. Define ordering/locking alongside the current catalog lock so a record
cannot change between validation and linking.

Retries with the same key and payload return the original result; changed
payloads conflict. For uncertain upload outcomes, freeze the original intent and
check its receipt rather than create a replacement. Specify reserved/staged/
committed/failed states and crash recovery for the filesystem/DB boundary.
Atomic rename alone is not a transaction with PostgreSQL or SQLite. Unregistered
or tampered bytes must fail closed, and cleanup must never remove referenced
revisions. Recovery must not silently reread a changed source file.

Deduplicate bytes only within scope if useful; identical hashes do not merge
attachment identities, provenance, or record links. Do not expose cross-workspace
existence through dedupe responses. Initial implementation may avoid physical
blob dedupe entirely while still preventing duplicate operations.

Archive and restore are recoverable metadata actions. Unlinking one record
retains the attachment and other links. Archiving retains bytes and revisions;
there is no automatic purge or garbage collection in the first release. Show
archived/missing targets explicitly rather than cascading content deletion.

## Storage topology and privacy

Managed bytes reside in an explicitly configured profile-local plugin data
subdirectory on the serving Hermes host. Local Desktop and remote gateway
connections are different destinations. Uploading from a desktop to a remote
Hermes host transmits the file; disclose that destination in the review UI.

PostgreSQL stores metadata; it does not replicate profile-local files. Two
Hermes hosts pointing at one database need a deliberately supported shared
storage topology or must be rejected for managed-file access. A connection
switch must not guess that another host's same-named directory contains the
same bytes. Missing storage is a visible error, not permission to fall back to
another folder, storage service, or external provider. No new cloud bucket,
paid service, credential, or persistent file grant is part of this plan.

Default agent listings should return only reviewed minimal metadata. Filenames,
URLs, descriptions, and provenance can themselves be sensitive. Keep bytes,
protected notes, hidden paths, and unreviewed private metadata out of default
projections. Content fetch and research are separate explicit capabilities.

Avoid persistent browser caches and localStorage for selected bytes. Clear
selection and invalidate pending UI on close, disposal, record change, or any
connection/profile/gateway activation transition. Address request-body logs,
errors, telemetry, reverse-proxy buffering, and temporary-file retention in
native tests. Do not promise secure erasure of memory or filesystem copies.

## Encryption, portability, and release gates

Existing optional protection covers protected notes and encrypted CRM content
exports, not ordinary Notes, fields, or file bytes. Protected notes currently
cover contacts/deals/tasks, not Company/Event. Existing exports use a table
allowlist and do not automatically include new attachment tables. See
`hermes_crm/protection.py`, `desktop/protection.js`, and `docs/CONTACT_TRANSFER.md`.

Do not call attachment storage encrypted merely because an encrypted export
exists. Filenames, URLs, metadata, staging files, backups, and downloads are
separate exposure surfaces. Existing encrypted exports remain host artifacts;
downloading produces another copy. Export is not a complete Hermes backup and
there is no current restore workflow.

Release gates must state exact coverage:

1. URL-reference release: explicitly decide whether link/revision metadata is
   included in the supported content export. Update the allowlist and validation
   if included; otherwise clearly disclose exclusion. Test archive/revision data.
2. Managed-upload release: ship a documented byte-preservation and reconciliation
   procedure, or clearly label exports metadata-only and attachments as excluded.
   Do not claim recoverability until a consistent DB-plus-bytes snapshot and
   restoration drill verifies hashes, links, versions, and scope.
3. Future portable bundle: versioned manifest, exact immutable revision coverage,
   bounded entries, authenticated encryption if promised, key separation, safe
   path handling, and explicit restore destination/conflict rules. Never treat a
   ZIP archive as an automatically safe restore or import format.

Archive restore only restores metadata state. It cannot recover deleted bytes,
revoked document access, missing keys, or expired external URLs.

## Migration and rollback

Create new owned tables only on an explicit feature write/configuration path.
Keep legacy record tables unchanged. Use scoped state/version markers; reject
partial or incompatible registries and require an explicit migration plan.
Do not silently populate attachments from Notes or email-history links.

Deploy additive storage and read-only views before writes. Gate writes by host
capability and scope binding. Rollback disables writes/UI while preserving new
tables, receipts, and bytes; it must not drop data. Validate that an older build
ignoring new tables does not falsely claim complete exports. Restore/cleanup
procedures need independent review before any destructive migration.

## Acceptance tests before claiming support

- SQLite and PostgreSQL parity: schema isolation, no read-time initialization,
  transaction races, catalog lock ordering, exact kind/ID, stale versions,
  archived/nonexistent targets, forged workspace tokens, and cross-profile IDs.
- All five record kinds, multi-link visibility, unlink/archive/restore semantics,
  immutable revisions, minimal audit records, and deterministic pagination.
- Same-key retries, conflicting payloads, interrupted upload, failed DB commit,
  missing/tampered blobs, orphan reconciliation, and uncertain receipt recovery.
- Traversal/absolute/UNC paths, filename controls, symlink and hard-link attacks,
  FIFOs/devices, races between validation/open, private modes and directory owner.
- Client MIME/extension spoofing, malformed and truncated files, Unicode names,
  actual versus declared lengths, request and workspace quotas, decompression
  bombs, active files, and unsupported archives. Never extract to validate.
- No URL auto-fetch, network preview, active rendering, OCR, model calls,
  provider uploads, or arbitrary local reads from any create/list/open operation.
- Native file input cancellation and scope changes during selection/upload;
  A→B→A transitions; plugin disposal; remote destination shown correctly; no
  stale client upload; missing supported transport disables writes safely.
- Download capability binding, user action, safe filename, hash verification,
  no claim of confirmed save, and retention/copy warnings.
- No content in logs/caches/telemetry/agent defaults; ordinary/protected note
  boundaries unchanged; export metadata/byte coverage and missing-file restore
  limitations accurately reported.

Implementation order: approve contracts and limits, implement URL references,
verify native single-file transport, implement managed storage, then run the
cross-engine/native/privacy/export gates. Model ingestion is not in that scope.
