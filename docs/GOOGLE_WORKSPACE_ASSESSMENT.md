# Google Workspace email adapter assessment

Source inspected: Hermes commit
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, specifically
`skills/productivity/google-workspace/SKILL.md` and its
`scripts/google_api.py`. This is source inspection, not an account connection
check. No skill command, authentication check, mailbox read or send was run.

## Decision for this release

Keep `DisabledEmailAdapter` disabled. The pinned, unchanged wrapper can search,
read and submit mail, but does not expose enough information to implement the
CRM's approved-message and history contracts faithfully. This does not establish
anything about a user's account or its existing grants, and it does not mean a
Google Workspace integration is impossible. A separately reviewed extension to
the host or skill is needed before connecting this CRM adapter.

## Verified capabilities and missing boundaries

- **Search** returns message and thread IDs, From, To, Subject, Date, snippet and
  labels. It reads one list page and then metadata for each message. Pagination,
  history IDs and provider timestamps are discarded. A negative search cannot
  prove that a submission did not occur.
- **Get** reads full messages but returns a simplified body plus selected
  headers. Search and get do not modify mailbox labels in this source. Credential
  refresh may still write local authentication state. The wrapper omits complete
  headers, Cc/Bcc, provider occurrence time and full MIME provenance; nested
  bodies may be omitted or returned as untyped HTML. Header Date and From are
  not authenticated provider time or sender identity.
- **Send/reply** returns a literal `status: "sent"` after an API response,
  together with message/thread IDs. This is not independent sent-state evidence
  or recipient delivery. Send lacks Bcc and a content-safe structured-input
  channel. Reply reconstructs recipients and headers from the current message
  rather than consuming an immutable, exact approved snapshot.
- **Account binding** is absent from operation results: every Gmail operation
  uses `userId="me"`. A configured sender, credential-file path or caller claim
  cannot substitute for a verified account identity. The module caches its home
  and token paths at import, so importing it once into a multiplexed plugin can
  also bind later calls to the wrong profile.
- **Transport selection** automatically prefers the external `gws` CLI and
  otherwise uses the Python client. There is no explicit backend/capability
  receipt. CLI arguments contain message content, and some errors print raw
  provider output. Neither path exposes a structured distinction between
  known rejection and an unknown outcome after submission.
- **Authorization** in the skill is instructional text, not a runtime receipt
  bound to an exact message digest, account and recipient set. Skill readiness
  is not proof of authenticated account identity or sufficient grants. The
  public skill-view interface serves documentation and readiness metadata, not
  a typed email transport with an approval checker.

Relevant source locations in `google_api.py`: profile paths 39–43; backend and
process handling 82–129; simplified parsing 132–155; credential refresh 246–261;
search 279–336; get 340–376; send/reply 380–482; CLI arguments 1153–1188.
Additional host references: `tools/skills_tool.py` and
`tools/credential_files.py`. These locations refer to the exact commit above.

## Smallest credible next increment

First establish a supported, per-call profile-bound transport that provides:

1. Verified authenticated account identity and explicit backend selection, using
   existing authorized scopes where sufficient. Do not discover or copy secrets
   in the CRM plugin.
2. Structured message input that avoids content in process arguments, and a
   trusted check for actual approval of the exact account, recipients and
   content. A model-supplied approval flag is insufficient.
3. Documented submission receipts and unknown-outcome handling, with no automatic
   resend after a timeout or parsing failure.
4. Complete, nonmutating readback and bounded pagination/history, with explicit
   coverage and cursor-expiry behavior.

Then build and test a disabled-by-default concrete adapter with synthetic
transport fixtures before any authorized live-account test. Keep submission,
independently observed sent state, incoming mailbox observations and unknown
outcomes separate. Do not deduplicate by thread, subject or header Message-ID.
No provider integration is enabled by this assessment.

See [Email activity contract](EMAIL_ACTIVITY.md) for the existing evidence and
deduplication boundaries. CRM record-change audit entries remain separate from
provider-backed email history.
