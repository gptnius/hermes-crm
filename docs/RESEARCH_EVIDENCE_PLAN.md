# Sourced research evidence and note proposals

Status: **first increment implemented**. Live research, broader execution and
physical UI validation remain separate gates. This plan describes the bounded
package following optional task ownership. Baseline: public
`aed3f70e6ec5b55fe9192f856b520d1f241a26cf`, tree
`0d7e4759978c6012f94770da032554a7f14493f6`. It is not a claim that research,
website access, agent execution or provider integrations have been enabled.

## The workflow

1. A user or an already-authorized interactive Hermes agent works on one exact
   saved Company or Contact and one research question.
2. They submit one source URL and the information they observed. The application
   stores a source snapshot, labelled source claims and separate hypotheses.
   Saving a packet does not open the URL, verify the claims or run an agent.
3. They prepare an ordinary-note addition from that evidence. Preparation binds
   the exact evidence version/digest and the record's current version/note hash.
   It does not modify the record.
4. The user opens a fresh review of the current note, exact proposed addition and
   resulting note. An explicit Apply action appends it atomically, or Dismiss
   retains the proposal without applying it.
5. The application retains a bounded receipt describing the operation and
   versions. A receipt describes what happened then, not proof that the record's
   note is still unchanged now.

The package deliberately separates evidence, proposal and applied action. It is
not a replacement for permissions in other tools: existing authorized ordinary
CRM edits remain available. There is no new agent apply tool, but this does not
prove that only a physical human can call an application route.

## Data model and scope

All new tables are additive and use the current workspace/profile scope. Existing
records, Company relationships, tasks, assignments, due dates, owners and notes
are retained. Reads must not initialize a schema or create a workspace token.
Partial, malformed or newer schemas fail closed rather than being repaired.

Four owned tables cover:

- Schema version and compatibility checks.
- Evidence: immutable validated source packet, target/version, server recording
  time, content digest, lifecycle version and optional archive timestamp.
- Proposals: evidence identity/digest/lifecycle version, target/version, exact
  addition, before/after note hashes, proposal digest/version and disposition.
- Operations: scoped idempotency key, canonical request digest and original
  bounded response. Archive/restore and proposal dispositions remain auditable
  through retained operation receipts.

Do not store complete before/after notes in evidence, proposals or receipts.
A fresh preview may read them transiently. After subsequent record edits, the
saved hashes cannot reconstruct the old note or an exact historical diff.

Input and returned nested objects must not alias stored source packets. Validate,
serialize and deep-copy before computing digests. Mutating a caller's claims or
returned response cannot change saved evidence or a historical receipt.

## Bounded source data

A packet has one exact Company/Contact, its reviewed version, one question and
one HTTPS source URL/title. `observed_at` is a supplied timezone-aware observation
time; optional `published_on` remains unknown when not provided. `recorded_at`
is server time. None is a provider-issued publication or access attestation.

Source claims and hypotheses use separate arrays of bounded plain text. Initial
limits are a 1,000-character question, 2,048-character URL, 200-character title,
10 entries in each array of at most 2,000 characters, and a 32 KiB packet limit.
These are application limits, not a claim about an upstream browser/provider.

HTTPS syntax checks are not proof that a source is public, trustworthy or safe.
Reject credentials, control characters and malformed URLs. Do not log rejected
URLs or contents in error details. Do not store secret-bearing or signed/private
links as public evidence. Keep meaningful ordinary query/fragment components;
never silently rewrite a cited source to a different resource. No DNS lookup,
network fetch, favicon, preview, HTML rendering, extraction or automatic opening
is included. Display source/model text as untrusted data, not instructions.

Evidence corrections create a new packet. Archive/restore is reversible and
changes the lifecycle version so old reviews cannot silently become current
again. Archived evidence cannot support a new or applied proposal. Archived
Companies likewise reject new evidence/proposals/apply; Contact currently has no
corresponding archive model. There is no permanent purge in this package.

## Exact note application

The operation is append-only. Construct the new note as the unchanged current
note, followed by two newlines when it is nonempty, followed by the exact saved
addition. Preserve meaningful whitespace and Unicode. Reject blank additions or
any final note above the existing 10,000-character limit; never truncate, replace
unrelated text, automatically rebase or guess an updated proposal.

Apply validates the proposal version/digest, evidence version/digest/lifecycle,
record version and before hash within one transaction. It performs the note
compare-and-swap, record version/update time, minimal administrative audit,
proposal disposition and receipt insert atomically. Do not stitch together
independently committed service updates. Use the existing catalog lock order.

One proposal can apply once. Same-key retries return the original result, even
when later edits changed the current record. A different key cannot append an
already-applied proposal again. Reusing a key with different data conflicts.
Two proposals prepared against one record version cannot both apply unchanged.
Archive/restore or an intervening edit requires a newly reviewed proposal.

Applying updates **last edit**, not last interaction. It does not complete a
business task, acknowledge a separate agent-run report, prove a source was
researched, or send a communication. Those are separate actions and evidence.

## UI and agent contract

A contextual Research action belongs on Company and Contact details, preserving
navigation and record context. Paginated evidence/proposal lists remain separate.
Manual evidence entry, note preparation, current-note preview, explicit apply,
dismiss and reversible archive are distinct actions with truthful labels.

New agent capabilities use separate research read/write toolsets:

- Submit supplied evidence.
- Prepare a note-addition proposal.
- List evidence and proposals with reduced metadata.
- Read an exact evidence packet explicitly.

Do not add these tools to existing frozen scheduled allowlists. There is no
agent preview of private current notes through this package, no agent apply,
archive or dismiss tool, and no automatic browser/email capability. Existing
ordinary record detail tools retain their separate permissions.

UI/API writes require current workspace tokens, strict bounded fields and an
idempotency key. Adapter-owned actor labels are not verified person identities.
Reject unknown/repeated parameters and ambiguous JSON. Bind retained operations
to the original record, profile/backend authority and request generation.

Unknown outcomes retain the exact original key/body. Users may explicitly inspect
its receipt or retry that request, never silently create a new key/proposal.
Malformed receipts do not establish success. Definitive rejection retains a
recoverable draft and requires fresh review before a corrected request. Close,
Back, navigation, reconnect, unmount, profile A→B→A and late responses must not
apply old actions to a different record or release a stale preview.

Keep notes transient rather than putting entire before/after copies in draft
storage. In-app recovery is not a durable cross-device/offline draft system.

## Export and protection boundaries

Include every new owned table in the explicit encrypted content-export registry,
schema/decode validation and scope predicates. Retain only the selected scope's
evidence, additions/hashes and operation receipts. A successful export is not a
complete backup or a tested restore workflow. Hashes cannot recover prior notes.

Ordinary live evidence and notes remain plaintext. Encryption of a separately
configured export does not encrypt the database or turn source links into safe
public resources. Protected notes and uploaded file contents are outside this
package. No new key, access grant, account or external service is configured.

## Validation and release gates

- SQLite and actual disposable PostgreSQL parity; legacy data retained, strict
  schema checks, read-only noninitialization and current scope validation.
- Exact target/evidence identity, archive/restore and version ABA, stale previews,
  concurrent edits, duplicate/different-key retries and receipt replay.
- Transaction fault injection after record mutation and later disposition/audit
  steps: all changes roll back together.
- Empty/full notes, newline/Unicode preservation, exact length limits and no
  duplicate append. No stored full before/after note copies in research tables.
- Nested-object aliasing, URL/HTML/control inputs, claim/hypothesis labels,
  timestamp semantics, bounded pagination and no outgoing requests.
- Agent schemas and reduced responses; unchanged frozen scheduling tools;
  protected notes inaccessible through evidence endpoints.
- Native/standalone actual handler/component tests for repeated clicks, stale
  scopes, dismissal, recovery, malformed receipts and explicit corrected saves.
- Export scope and lifecycle coverage; last-interaction metrics unchanged.
- Full existing regressions and deterministic bundles, independent review and
  source/privacy checks before coordinated publication.
- Physical native light/dark/narrow-width/accessibility verification remains a
  separate gate. Do not interrupt the user's open review app to obtain it.

## Deliberately deferred

Automatic web research, source fact verification, provider-linked attachments,
managed uploads, task proposals, quality-review dispositions, email sending,
background scraping and broader scheduled-tool permissions are separate work.
The interactive agent may submit evidence only after obtaining information
through its existing authorized capabilities. This feature does not establish
those capabilities or complete an end-to-end live research test by itself.

Later increments add [opt-in timed research](SCHEDULED_RESEARCH_PLAN.md) and
[durable report acknowledgement](REPORT_REVIEW_PLAN.md). They do not turn source
storage into automatic fact verification, quality approval or outbound delivery.
