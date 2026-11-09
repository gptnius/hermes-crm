# Existing Hermes Gmail connection bridge

Status: implemented with synthetic providers; independent core/UI review and
local aggregate checks, including a full disposable PostgreSQL-backed run, passed.
Both genuine pinned-host modes passed default-off routing/profile checks.
Live account and installed-host sync validation remain release gates. No
existing account was opened, credentials inspected, Google grant created or email
sent during development. The separate manual CRM-owned OAuth pilot remains under
**Advanced: separate CRM email connection**. This document is not permission to
activate either connection. See [setup, usage and privacy](GMAIL_SETUP.md).

## Implemented workflow

1. A trusted operator configures the gws 0.22.5 absolute executable path and
   enables the default-off bridge for the intended profile. The bridge explicitly
   selects that active profile’s existing `google_token.json`; no account discovery
   or credential-path picker is provided. The user authorizes each access scope.
2. CRM verifies the named own mailbox. It does not discover another account,
   import credentials, sign in or fall back to another connection.
3. Verification reads mailbox profile only and captures a new-from-now checkpoint.
   Message reads are separately approved. Optional 7- or 30-day history is explicit;
   incremental reads can observe messages sent or received outside Hermes. A saved
   checkpoint advances only after a complete, transactionally published batch.
4. Exact email identities associate observations with Contacts. Several
   unambiguous participants can associate the same message with several
   Contacts. Retained ambiguous or case-mismatch candidates are reviewable, not
   assigned by name, domain or guesswork. Unsupported or unmatched messages may
   be omitted; the review list is not an inventory of every problematic header.
5. Company views may derive association from the CRM's explicit Contact–Company
   relationship. A matching email domain does not create a Company link, and
   message subjects do not automatically identify an opportunity or appointment.

The initial scope is selected metadata, not email bodies or file attachments.
The bridge does not send, draft, reply, mark read, modify labels or create
Contacts. An observed Sent label is not proof of delivery or of a CRM-approved
send. Header direction is an observation, not authenticated sender identity.

## Source-backed reuse route

The tested Hermes OAuth broker only offers a calling plugin's own OAuth entry
and its specific shared providers; it has no shared Gmail connection selector.
The Workspace skill's public wrapper omits Gmail profile and history methods.
Importing its private credential helpers or borrowing another plugin's grant
would not create a supported connection contract.

The Google Workspace CLI from its official repository offers a narrower practical
route, but its distribution states: **“This is not an officially supported Google
product.”** Reviewed
source is version **0.22.5**, commit
[`cd3697e07eb520056dcf142d0c7439bbb9ba32e9`](https://github.com/googleworkspace/cli/tree/cd3697e07eb520056dcf142d0c7439bbb9ba32e9).
It accepts an explicit credential-file selector used by the existing Hermes
Workspace connection. The adapter can pass that file's path without reading or
copying its token contents. Actual CLI execution necessarily lets the CLI use
that credential and refresh an access token; this needs explicit activation
approval. No new Google OAuth grant is intrinsically required if the existing
connection has sufficient permissions.

The adapter must not use ambient connection discovery. In this reviewed CLI,
encrypted-credential decryption failure can remove the old encrypted file and
fall through to another credential source. Explicit-file selection instead
fails when unavailable. The CLI also loads `.env` and can write token caches.
Therefore the implemented adapter uses fixed read-only arguments, a scrubbed
environment, an explicit existing connection file, an owned working directory
with an empty `.env`, and disposable private cache/key storage. It never invokes
authentication commands. Synthetic subprocess and source-contract checks do not
establish real-account behavior; separately authorized live validation remains
necessary.

The mailbox address plus a local account namespace is not an immutable Google
subject or an atomic grant lease. Before/after mailbox checks and file metadata
checks detect observable changes, but operators must not reconfigure the
connection during a read. Different connections must not be silently merged.
CLI version output is compatibility information, not proof of binary provenance.

A Linux binary from the official-repository [v0.22.5 release](https://github.com/googleworkspace/cli/releases/tag/v0.22.5)
was verified without credentials against its companion release checksum. The
expected two-line `--version` output and top-level `--help` were checked; top-level
help includes Gmail and the `--params`, `--format` and `--api-version` options.
These checks do not verify endpoint execution or a mailbox. With a fresh isolated
configuration, the CLI needs public Google Discovery metadata before endpoint
command parsing. Endpoint-specific help failed on DNS resolution for
`www.googleapis.com`; endpoint/runtime mailbox behavior remains unverified.
Consult [verification evidence](VERIFICATION.md) for the exact checks.

## Matching and privacy

- Match From, To and Cc using exact supported bare mailbox identities. Normalize
  the domain's case, but do not remove plus tags, dots or local-part case.
- Contact aliases and own-mailbox aliases must be explicitly supplied. They are
  not inferred or asserted to be provider-verified. Exclude the user's own
  selected addresses from Contact matching. Explicit Contact aliases persist
  until edited or removed, including after a primary email address change.
- Keep ambiguous candidates and the basis of a match visible. Validate current
  Contact identities and aliases before publication and when showing derived
  associations. An address change must not silently preserve an obsolete link.
- Deduplicate by the selected account namespace and Gmail message ID, never by
  subject, thread, date or the RFC Message-ID header.
- Request only Subject, From, To, Cc, Date, selected labels, provider IDs and
  ordering metadata. Never request bodies, snippets, MIME parts, attachments or
  Bcc. Metadata can itself be private and is ordinary CRM storage, not protected
  notes.
- Explain before activation that incremental mailbox reads may examine unrelated
  message metadata in memory. Retain only matched or reviewable candidate items;
  aggregate unmatched counts do not prove complete correspondence coverage.
- Store data in the selected CRM backend, which may be an explicitly configured
  remote PostgreSQL schema. Do not describe all installations as local-only.
- No model tool, normal record projection or scheduled research assignment gains
  access to email metadata merely because this bridge is enabled.

## Sync, recovery and controls

Bootstrap captures a starting Gmail history ID before listing the chosen window.
It retains that starting cursor after a successful scan so a following incremental
read can catch changes during bootstrap. Incremental reads finish every required
history page and corresponding metadata read before publishing a new checkpoint.
IDs are sparse decimal identifiers, not sequential offsets. A stale-cursor 404
requires a disclosed bounded resync, not a hidden reset.

A durable per-workspace lease prevents simultaneous pollers from publishing the
same operation. Disable, disconnect, detected request-scope/configuration changes
and superseded leases fence publication. UI navigation suppresses stale rendering
and stops future polling; it is not a promise to cancel an already dispatched
server read. A killed process leaves a visible recoverable operation; read-only
retries use the old checkpoint and account/message deduplication. Partial work
must never be presented as a complete mailbox snapshot. Explicit deletion
history, unavailable metadata and absence from a query remain distinct states.

The implemented native poller is lifetime-owned by the open CRM pane and requires
explicit **Sync while CRM is open** approval. Checks are at least five minutes
apart. No daemon, cron job or startup service is installed, and importing the
package or reading local status never activates provider access. Unknown outcomes,
missing checkpoints and required resync block polling rather than silently retrying.

Pause, disconnect and clear are distinct controls. Disconnect disables use and
removes the active selection without deleting retained observations. Clear deletes
workspace observations and resets the checkpoint while identity, aliases and
receipts may remain. Receipt retention is bounded to 10,000 ordinary receipts
(with automatic compaction of older terminal receipts and protection for active
or unknown operations) and 128 control receipts. After ordinary receipt
compaction, a missing lookup may report `expired_or_unknown`; otherwise it may
return null. Absence never proves no action. Stale revisions still prevent
replay after receipt expiry.
Neither control revokes Google access. Encrypted backups include
scoped metadata; restore keeps it as quarantined recovery evidence, with no active
account, cursor, lease or polling state and a disabled live bridge.

## Verification coverage and remaining gates

Independent core/UI review and synthetic SQLite/PostgreSQL checks passed; this
list describes coverage, not a claim of completed real-mailbox or installed-host
sync validation. Genuine pinned-host default-off route checks passed.
See [the verification record](VERIFICATION.md) for exact runs and remaining blockers.
That record also discloses one unexplained intermittent OS error during a
synthetic deadline test. A separate, reproducible final-drain deadline defect
was fixed and reviewed; bounded diagnostic reruns did not reproduce the original
error and do not establish its resolution. The feature remains default-off,
with real-account acceptance still required.

1. Parser, matching, incremental reader and fixed CLI transport tests, including
   malformed headers, duplicate recipients, aliases, pagination, stale cursors,
   cancellation, output bounds and no secret-bearing errors.
2. SQLite and disposable PostgreSQL tests for schema upgrades, leases, idempotent
   publication, rollback, cross-profile isolation, changed Contacts and recovery.
3. Authenticated native setup/history/review controls with stale-context guards,
   clear permission and storage descriptions, and no automatic provider reads
   on ordinary status/history navigation.
4. Actual pinned-host lifecycle and CLI compatibility checks without credentials.
5. Separately authorized account verification and a bounded real mailbox read,
   followed by native UI inspection. No production-readiness claim before these
   real integration checks pass.

Sources: [Hermes request broker](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/plugin_provider_requests.py),
[Workspace wrapper](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/skills/productivity/google-workspace/scripts/google_api.py),
[CLI authentication](https://github.com/googleworkspace/cli/blob/cd3697e07eb520056dcf142d0c7439bbb9ba32e9/crates/google-workspace-cli/src/auth.rs),
[Gmail history API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list).
