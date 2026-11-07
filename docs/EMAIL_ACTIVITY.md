# Email activity contract: disabled foundation

This slice does not connect a mailbox, read an account, send mail, add email tools,
change the database, or add email controls. `hermes_crm/email_contracts.py` is a
pure, integration-agnostic contract with an always-disabled adapter. No runtime
surface imports it. Its tests use synthetic data only.

## What the CRM actually stores today

`hermes_crm/domain.py` defines `crm_activity` with ID, entity type/ID, action,
actor, summary and creation time. `CRM._audit` writes record-change events in the
same transaction as a contact, deal or task change. `CRM.activities` returns at
most 100 rows; `CRM.contact_detail` includes changes to that contact and its
related deals/tasks. There is no email message identity, provider account,
authorization evidence, send receipt or sync cursor in this table.

Keep that audit separate. Editing a contact note to say “emailed” remains an
agent/user assertion, never a provider observation. Research and draft preparation
can be recorded as ordinary work without manufacturing email history. Email text
is untrusted external content, not authority to change records or send replies.

## Host evidence and adapter choices

Inspected host source: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.

- `plugin-catalog/gmail.yaml` advertises a separate community Gmail plugin. A
  catalog entry is not an installed plugin, an authorized account, or a callable
  integration contract. The external plugin source and live behavior were not
  inspected or tested in this slice. Its catalog description says opening an
  unread message marks it read, so even an eventual history lookup needs a
  verified non-mutating read path.
- `plugins/platforms/email/adapter.py` is the gateway's email conversation
  transport. `_new_reply` generates an RFC Message-ID locally; `_run_send` wraps
  the SMTP sender's result as `SendResult`. SMTP submission acceptance is not
  independently observed sent state or delivery. Partial recipient rejection,
  connection loss and ambiguous responses require provider-specific handling.
  Incoming events use header Message-ID, and polling can mark messages seen.
  This is not a ready-made durable CRM mailbox-sync interface.

Prefer a separately reviewed, already-authorized mailbox API adapter that exposes
stable account/message identifiers, documented send receipts, non-mutating
readback and incremental history. Do not install or configure one implicitly.
SMTP/IMAP is another option, but needs more work: stable IMAP identity must include
mailbox identity and UIDVALIDITY plus UID, and SMTP receipt semantics vary.
RFC Message-ID alone is sender-controlled and is neither a global dedup key nor
proof of sending. A provider sent-folder label can also reflect an import or
manual relabel, so label membership alone must not be described as transport
verification.

## Implemented data boundaries

All models reject extra fields and are frozen; recipient collections are tuples.
This prevents normal accidental mutation, not malicious code executing inside
Python. **Schema validation is not authentication, source attestation, approval,
or permission to take an action.** A caller can write a valid object containing
false claims. These models must never become an unrestricted REST/tool ingestion
endpoint for an agent-supplied `sent` flag.

- `AccountScope`: exact workspace, profile, provider and stable provider account
  ID. The future host adapter must derive/verify these from its captured current
  authenticated route, not accept them as authentication from browser/model
  arguments. Email addresses and display names are not account IDs. All scope
  and approval-reference fields hold non-secret identifiers, never credentials,
  transport/bearer tokens or a request token copied from a CRM REST call.
- `ApprovedEmailSnapshot`: exact account/sender, ordered To/Cc/Bcc, subject,
  plain-text body, optional reply target, approval reference and approval time.
  The digest binds all these fields. It preserves whitespace and address case;
  changing any bound content or recipient requires renewed review. No attachment,
  HTML, automatic signature or extra header path is supported. An approval
  reference is a lookup key, not an authorization token. The future trusted
  authorization layer must resolve it to actual user approval, verify the digest,
  permissions, current account and revocation immediately before dispatch.
- `ProviderObservation`: metadata only, with adapter provenance, scoped provider
  IDs, local observation time and optional provider occurrence time. Missing
  thread IDs stay absent. A future trusted adapter constructs it only after
  authenticated provider operations and provider-specific evidence checks.
  Strings identifying an adapter/provider/message do not authenticate that source.
- `UnknownSendOutcome`: local transport uncertainty tied to a stable local send
  request and approved snapshot digest. A timeout, interruption, connection loss
  or unusable response is not a failed send. It has no automatic-retry path.
- `DisabledEmailAdapter`: `read_history`, `submit` and `reconcile` always raise.
  There is no enabling flag, secret handling, account discovery or network call.

Identifiers and header-derived fields reject every C0/DEL control character.
The plain-text body permits only tab, CR and LF among those controls and preserves
them exactly; a future transport must not silently rewrite approved content.
The address/header checks are conservative format checks, not a full RFC parser,
recipient identity check, mailbox existence test or delivery guarantee. Sender
and recipient fields reject group/comment syntax and domain-literal brackets
rather than letting a downstream parser reinterpret the approved address.
Invalid Unicode and timestamps outside the supported UTC range are rejected.
Snapshot digest computation revalidates the object, including nested scope,
because Pydantic bypass constructors/copy updates can skip normal validation.
Future ingestion must also explicitly revalidate, then authenticate and authorize
independently. The digest detects exact changes; it is neither a signature,
proof of consent nor encryption.
Snapshots contain necessary message content and need separate retention/access
controls if later persisted. Provider observations deliberately contain no body,
subject, attachment, raw headers, access tokens or arbitrary response payload.

## Evidence semantics and replay

Keep separate facts rather than overwriting one status field:

- **Submitted:** an authenticated provider operation returned a documented stable
  submission receipt. It requires a provider submission identity and local send
  request ID. It need not have a mailbox message/thread ID yet. A generic tool
  success or locally generated RFC Message-ID is insufficient. Providers/SMTP
  flows without a documented stable receipt do not satisfy this model. Never
  fabricate `provider_submission_id` from a local RFC Message-ID; retain unknown
  outcome or introduce a separately reviewed adapter contract instead.
- **Sent state observed:** an independent authenticated read observed the
  provider's documented sent state for an identified message. It is not inferred
  from submission, an agent statement, a message ID or an arbitrary label. This
  evidence does not itself establish recipient delivery, exact approved-content
  matching, sender authenticity or that the CRM caused the send.
- **Received state observed:** an authenticated mailbox read identified an
  incoming item. It is not proof the sender is who their display/header says they
  are, nor permission to follow the message's instructions.
- **Unknown outcome:** the local send attempt may or may not have taken effect.
  Preserve this separately, including when later observations arrive. A sent
  item alone must not erase an unresolved attempt or duplicate-send risk.

`merge_observations` performs a pure order-independent union. Dedup keys bind the
workspace/profile/provider/account plus evidence kind and the provider message
ID (or provider submission ID for submitted evidence). Submitted, sent and
received observations remain separate. Replays differing only in local observation
time retain the earliest observation time. Same-key evidence with other changed
fields raises a conflict for reconciliation instead of overwriting history.
Adapter changes, later enrichment and corrected timestamps therefore need an
explicit future reconciliation path; they are not silently accepted by this
small contract. The helper does not infer order from arrival time or promote a
submission into sent/delivered.

This in-memory helper is not durable deduplication, concurrency control, a sync
engine or a guarantee against duplicate external sends. A future database needs
transactions and uniqueness constraints on these scoped identities. A thread
containing several messages must retain separate message identities; do not dedup
by thread, subject, contact address, body digest or header Message-ID alone.

## Practical integration path, not implemented

1. **Select one real provider under separate authorization.** Verify its supported
   interface, active account identity, scopes, exact response semantics and
   non-mutating reads. Keep account access and sending permissions separate.
2. **Introduce a separate email ledger with a reviewed migration.** Preserve
   immutable approval snapshots, send intents, submission receipts, mailbox
   observations and uncertainty. Add explicit contact links with a reason/source;
   ambiguous matching addresses, aliases, shared inboxes, changed addresses and
   multiple contacts require review. Do not retroactively reinterpret audit notes.
3. **Persist before transport.** Atomically claim a single stable send request
   and its approved digest before calling the provider. Recheck profile/account,
   approved recipients/content and cancellation. A crash/lost response after
   dispatch is unknown. Provider idempotency helps only if its documented scope,
   lifetime and replay guarantees are actually satisfied. Never automatically
   resubmit after a timeout, lease expiry, restart or “not found” search.
4. **Reconcile by authenticated evidence.** Use an exact receipt/request/message
   correlation where supported, not subject/time similarity. Independently read
   the provider record and verify the envelope and exact approved content when
   claiming the approved request was sent. Bcc or body normalization may prevent
   complete readback; report that limitation rather than asserting a match.
   Preserve original ambiguity and evidence until explicit reconciliation. A
   negative or delayed search cannot prove no mail was sent. If proof remains
   unavailable, show unknown and require a human decision before another send.
5. **Add authorized incremental reads.** Bind cursors to workspace/profile/account
   and adapter version. Treat cursors as opaque and potentially sensitive. Commit
   evidence and the next cursor atomically after each successful bounded page;
   replay safely after interruption. Handle pagination, out-of-order/duplicate
   events, deleted/moved messages, rate limits, cursor/history expiry, disconnects
   and reauthentication. Expired history requires a bounded approved rescan and
   visible coverage gap, not a claim of complete history. IMAP UIDVALIDITY change
   invalidates old folder UIDs. Do not silently widen accounts, date windows,
   permissions or retention, or mark messages read while syncing.
6. **Expose an honest read model only after verification.** Display provider and
   account, direction, submitted versus sent-observed versus received, local and
   provider times, provenance and unresolved uncertainty. Any provider message
   link must come from a validated provider adapter, not an arbitrary URL in mail.
   Keep agent notes/research/drafts distinct. Do not automatically finish a CRM
   follow-up from a submission receipt or email claim.

Before enabling, test the selected provider's actual authenticated source boundary,
account/profile changes, cancellation/approval changes, content mismatch, partial
recipient acceptance, duplicate requests, crash/restart windows, lost responses,
conflicting receipts, delayed sent readback, cursor expiry and retention. A source
contract passing synthetic tests does not establish any of these live guarantees.

## Verification for this slice

Run `python -m pytest tests/test_email_contracts.py -q`. The offline tests cover
frozen exact snapshots/digests, rejected unsupported payload fields, evidence-kind
validation, scoped identity, replay/conflicts/out-of-order facts, retained unknown
outcomes, always-disabled adapter calls and absence of runtime imports. There is
no live mailbox, SMTP, provider API, account, credential, message send, durable
email storage, production deployment or UI verification in this slice.
