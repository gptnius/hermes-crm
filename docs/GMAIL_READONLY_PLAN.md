# Optional Gmail history: offline design, not an integration

Status: this is the design record reviewed on 2026-11-07. A subsequent optional,
default-off **manual contact-query pilot** is now implemented with synthetic tests
only; see [current setup and limits](GMAIL_SETUP.md). Its manifest declares its own
OAuth entry, but no real grant or account has been accessed during development.
The broader incremental-history design below is not implemented. The original
`DisabledEmailAdapter` send/reconciliation contract remains disabled; the new
reader is a separate metadata-only path. Drafting/sending remain unavailable.

This supplements [the email contract](EMAIL_ACTIVITY.md) and
[the Workspace wrapper assessment](GOOGLE_WORKSPACE_ASSESSMENT.md). It proposes
a CRM-owned integration, not reuse of the bundled Workspace skill's token,
another plugin's grant, the gateway email transport or the `gws` CLI. Do not run
the Workspace setup script: its broader scopes and credential selection are
not this design. Do not vendor or import the separately licensed community
Gmail plugin.

## 1. Verified transport, and what is still missing

Host source is pinned to
[`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`](https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19).
Source inspection, not invocation, established:

- [`credentialed_provider_request`](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/plugin_provider_requests.py)
  is a public function. It identifies an installed plugin from its calling
  code, prefers that plugin's own declared OAuth client, checks HTTPS origins,
  resolves authorization inside Hermes and never follows redirects. It returns
  a `ProviderResponse(status: int, headers: dict[str, str], body: bytes)`, with
  `text` and `json()` conveniences. It does not return a requests/httpx response,
  account ID, grant generation, profile receipt, request handle or token.
- [`plugin_oauth.py`](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/plugin_oauth.py)
  binds grants to the installed plugin key, manifest OAuth **entry ID** and
  manifest-entry fingerprint. That fingerprint includes the client-variable
  names, not their configured values. It does not attest the actual OAuth client
  ID; changing a client-variable value does not by itself invalidate an already
  live token. Changes to that OAuth declaration invalidate its saved grant
  fingerprint. Token refresh belongs
  to Hermes; refresh locking does not pin a grant across a series of API reads.
  `_bearer` resolves each request independently, and a live token read is not
  held under the refresh lock. These private functions are evidence, not APIs
  for CRM to call.
- The helper rebuilds supported credential-bearing exceptions without their
  original request/traceback. It does **not** redact arbitrary provider response
  bodies or application logs. CRM must not echo raw errors, responses, tokens,
  request URLs, page tokens or headers. Its origin restriction is not an HTTP
  method/path restriction: CRM must independently allow only the GET operations
  below. In-process plugins are not a security sandbox.
- [`auth_oauth_pkce_plugin.py`](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/auth_oauth_pkce_plugin.py)
  uses browser authorization code/PKCE and a loopback callback. Its retained
  token fields do not expose an ID-token identity receipt or granted-scope set
  to the CRM. This is not a complete verified OpenID Connect login interface.

### Design decision: resource enforcement versus atomic grant continuity

Google documents OAuth access to the consenting user's Gmail data, and
separately documents service-account domain-wide delegation for access on
behalf of other Workspace users. Naming an explicit mailbox is a resource
selector, not authorization to read arbitrary users. For an ordinary own-mailbox
grant, an unrelated B token is expected to fail a request for A's mailbox; this
has not been live-tested here. No source-backed successful cross-account read
was established. Do not treat Gmail web delegation as proof that the same
delegate can access another mailbox through this OAuth flow.
[Gmail authorization](https://developers.google.com/workspace/gmail/api/auth/web-server),
[credential/access types](https://developers.google.com/workspace/guides/create-credentials).

Personal Gmail addresses can change, but Google retains old addresses for that
account and prohibits their reuse. A generic address-reassignment attack should
not be asserted for that consumer case. Workspace rename/alias/reassignment
policy needs separate review; consumer behavior does not establish it.
[Google account email behavior](https://support.google.com/accounts/answer/19870).

The helper still cannot prove that one grant served all reads. An A → B → A
replacement can escape before/after identity checks. With normal provider
resource enforcement that alone does **not** imply a successful cross-mailbox
read. It can still hide intervening logout/reconsent or a same-account grant
replacement. Returning to the same CRM workspace token is also insufficient
without the monotonic activation epoch. A CRM mutex cannot lock another
process's login/logout or profile switch.

Two assurance choices. The implemented manual pilot uses the first; the second
remains a future host requirement:

1. **Bounded own-mailbox pilot:** rely on provider authorization, an explicit
   verified mailbox, before/after subject/profile checks, stable trusted operator
   grant and client-variable configuration, captured profile routing and
   activation checks. No
   concurrent reconnect/account administration, domain-wide delegation,
   arbitrary mailbox/alias selection or silent fallback. Verify these assumptions
   in the later authorized test. Do not claim atomic grant continuity or
   instantaneous cancellation of an already dispatched read. This can be a
   practical design without inventing an impossible B→A success scenario.
2. **Stronger concurrent/rebinding guarantee:** add a supported host request
   session/lease that pins profile and grant generation and binds responses to
   the verified subject, or an equivalently reviewed guarantee. Refuse replaced
   grants and changed activations, including ABA, without exposing credentials.
   The pinned helper provides no such API. This is a gate for that stronger
   guarantee, not proof that every own-mailbox pilot is unsafe.

A browser/model-supplied generation or approval flag proves neither choice.
Never read auth files, take private host locks, borrow another plugin's client
or copy tokens to simulate either guarantee. Synthetic tests show the endpoint
checks' observational limit separately from simulated resource enforcement.
The pilot assumes trusted operators do not change client-variable values during
a run; the pinned helper cannot attest their value or actual OAuth client ID.

## 2. Optional authorization design

Both personal Gmail and Google Workspace Gmail are candidates; this does not
establish that either is configured, permitted by an administrator, or enabled
for this user. A Google account without Gmail is not sufficient. Initially
support only the selected account's own mailbox, not service accounts,
domain-wide delegation, shared mailboxes or inferred aliases.

Proposed smallest scope set for this bounded-query design:

- `https://www.googleapis.com/auth/gmail.readonly`
- `openid`
- `https://www.googleapis.com/auth/userinfo.email` (Google's canonical email permission)

Use Google's canonical email URI rather than the short `email` alias in the
future manifest. Google's [token documentation](https://docs.cloud.google.com/docs/authentication/token-types)
shows `openid` plus that exact URI with `sub`, `email` and `email_verified`, and
its [OAuth discovery schema](https://www.googleapis.com/discovery/v1/apis/oauth2/v2/rest)
lists the URI as its email permission. Google's
[OIDC guide](https://developers.google.com/identity/openid-connect/openid-connect)
also maps a basic `openid email` authorization to the full URI. These support
the requested subject/email claim set without `profile`. OIDC UserInfo returns
the subject and granted email claims; do not request names, birthdays or
photographs. Email can change and is not a primary key.
[OpenID claim rules](https://openid.net/specs/openid-connect-core-1_0.html#ScopeClaims).
Actual claim availability is still checked at binding; missing claims stop the
operation rather than causing a broader scope request. No token introspection
command from the reference documentation was run or is proposed for CRM.

`gmail.metadata` permits less content access but cannot use the list API's `q`
parameter. `gmail.readonly` is the least Gmail scope for the proposed server-side
date window. It can read message bodies even though this adapter would request
metadata only. Consent must disclose that difference; metadata-only behavior is
an application restriction, not an OAuth guarantee. Both are restricted scopes.
Before distribution, review Google's verification and restricted-data handling
requirements, including any server-storage/security assessment obligations.
[Scope definitions](https://developers.google.com/workspace/gmail/api/auth/scopes),
[list/query restrictions](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list).

Scope compatibility still needs a controlled, separately authorized test.
The host's `_require_granted_scopes` compares literal strings, tolerates an
omitted scope field, accepts additional scopes and does not retain a usable
scope receipt. The canonical spelling avoids relying on short-alias
round-tripping. **Requested minimal scopes are not an attestation of the actual
token's maximum powers.** A manifest fingerprint does not prove that ceiling.
Verify the real consent result and whether earlier grants add scope; do not
silently reuse a broader grant. If an exact runtime ceiling is required, a
trusted host-granted-scope receipt is needed. No CRM token inspection or new
host implementation is part of this slice.

The pilot now declares the optional CRM-owned client `gmail-history-readonly`
with its own host-managed client variables. Declaring it creates no grant;
actual sign-in and persistent access still need explicit approval. Do not silently enable incremental authorization, combine earlier
broader grants, request modify/send/compose/settings scopes or use account setup
as an incidental side effect of viewing CRM. Persistent/refresh access requires
explicit authorization, not merely approval of one history read. Desktop client
registration and loopback redirect compatibility need verification against
[Google's native app flow](https://developers.google.com/identity/protocols/oauth2/native-app)
before asking the user to configure anything.

### Fixed endpoints

The public [Google discovery document](https://accounts.google.com/.well-known/openid-configuration)
was inspected without authentication. Current relevant endpoints are:

| Purpose | Fixed endpoint | Caller |
| --- | --- | --- |
| Authorization | `https://accounts.google.com/o/oauth2/v2/auth` | Hermes, after approval |
| Token exchange/refresh | `https://oauth2.googleapis.com/token` | Hermes only |
| Identity | `https://openidconnect.googleapis.com/v1/userinfo` | Future helper GET |
| Mailbox reads | `https://gmail.googleapis.com/gmail/v1/users/{mailbox}/...` | Future helper GET |

Only `gmail.googleapis.com` and `openidconnect.googleapis.com`, HTTPS port 443,
belong in the proposed credentialed resource-host allowlist. The authorization
and token endpoints are separate host-managed OAuth metadata. No wildcard,
user-supplied base URL, fallback host or redirect following. If public discovery
changes, stop and review the new endpoints rather than widening permissions.
Never send the bearer in a URL. Use the helper's fixed provider identifier.

## 3. Account selection and capture

Identity requirements used by the manual pilot; live provider behavior remains
unverified:

1. Capture the authenticated Hermes route, workspace and profile once. The
   Desktop client uses its monotonic route lifetime to reject stale display
   responses; the backend binds the request to its captured host home/workspace
   and a durable operation revision, not a Desktop epoch receipt. Request data
   cannot override the host-selected profile, backend, provider, account subject
   or credentials. Navigation alone does not revoke that server request.
2. After authorized selection, obtain UserInfo through the CRM-owned grant.
   Require nonempty case-sensitive ASCII `sub` (at most 255 characters), a
   verified email claim (`email_verified` boolean true) and the selected mailbox
   address. Ignore other identity fields. Do not fetch profile pictures or follow
   links in claims. If the host uses an ID token for identity, it must validate
   it and compare its subject to UserInfo; CRM must not accept a decoded token
   or caller-supplied claims as proof.
3. Call `users.getProfile` with the verified **explicit email** as `userId`,
   URL-encoded as one path segment. Require the returned email to match. No
   `userId=me` for data reads; no arbitrary userId accepted from the UI. The
   profile exposes email, counts and a history ID, not a stable account subject.
   [Profile contract](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users/getProfile).
4. Bind storage to `(workspace, profile, Google issuer, sub)`, with the mailbox
   address as a separately verified routing attribute. Do not merge addresses
   by case, dots, plus-tags or aliases. A changed mailbox address requires
   rebinding/review, even with the same subject. A new subject requires a separate
   account namespace, not migration of the old mailbox history.
5. Repeat UserInfo/profile checks around each bounded read batch under the
   reviewed assurance model above. Recheck captured activation and permission
   before committing. On any mismatch, discard staged content and cursors.
   Explicit local disconnect invalidates publication. UI navigation discards
   stale display responses but does not cancel the already approved server read:
   it may finish/save in its original captured workspace. The pilot discloses
   this before confirmation. Returning to an old UI view does not revive its
   old response handlers.

UserInfo over a host-owned bearer connection identifies the grant used for that
call, not a standalone CRM login system. The pinned host exposes neither a
validated OIDC login receipt nor atomic continuity. The pilot must not claim
either; a stronger design must add and verify the corresponding host support.

## 4. Bounded read protocol

Suggested initial limits, to be approved with the account: a 30-day UTC window,
100 IDs per page, at most 10 pages/1,000 unique IDs per run, 30 seconds per
request and a short overall deadline. A user may choose a smaller window; an
increase beyond 90 days needs a new reviewed plan. No schedule, watch/Pub/Sub,
automatic reconnect or unattended polling in the first slice.

**Privacy scope is a separate choice.** The examples below enumerate the chosen
mailbox's date window, not one contact's conversations. A narrower first pilot
can instead use a manual `messages.list` query generated from explicitly reviewed
contact email addresses plus the date window. Address quoting/validation and
alias/ambiguous-contact behavior need their own implementation and tests; this
file's original executable examples do not implement that contact query. The
separate production reader and `test_gmail_reader.py` now cover a conservative
bare-address contact query; no live Gmail matching is verified. Do not promise
all of a contact's history: aliases, Bcc, imports and incomplete pagination can
limit matches. No contact content is exposed through existing CRM read tools.

Mailbox-level incremental history is a separate optional increment requiring
clear consent. It has no documented contact/date query equivalent. Deciding
whether a changed message matches a contact/window can require reading metadata
from unrelated messages. A manual contact-filtered pilot must not quietly
upgrade to that processing. If only contact-matching provider results are
authorized, keep using bounded contact queries and do not run history sync.

Only these GET operations are permitted:

- UserInfo and explicit-mailbox profile as above.
- `messages.list`: generated numeric `after:`/`before:` window, `-in:drafts`,
  `includeSpamTrash=false`, fixed page size and opaque `pageToken` only. Avoid
  free-form user/model Gmail queries. Numeric epoch seconds avoid the API's
  date-string timezone behavior. Query a one-second boundary superset, then
  locally filter `start_ms <= internalDate < end_ms`; record that boundary
  metadata may be transiently inspected.
- `messages.get`: exact IDs returned by that account's list/history, with
  `format=metadata`, selected headers and a partial-response `fields` allowlist.
  Fields: `id,threadId,labelIds,historyId,internalDate,payload/headers` only.
  No snippets, `raw`, bodies, MIME parts, attachments or remote resources.
- `history.list`: the last committed account/window-specific `startHistoryId`,
  all change types, no label-only filter, bounded pages. Its partial-response
  fields allowlist contains only top-level `nextPageToken,historyId`, history
  record `id`, generic `messages(id,threadId)` and the four typed change arrays:
  added/deleted `message(id,threadId)`, and label changes' `message(id,threadId)`
  plus `labelIds`. Do not rely on message resources being “typically” minimal.
  Reject unexpected content/shape at every nested level. Every generic message
  ID must correspond to a typed event; unknown-only or incomplete event records
  cannot advance the cursor as a complete sync.

[Filtering semantics](https://developers.google.com/workspace/gmail/api/guides/filtering)
and [metadata get parameters](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get)
inform these proposed restrictions. Never call modify, batchModify, trash,
untrash, delete, drafts, send, import/insert, settings, watch or attachment APIs.

Treat each helper result as typed status/headers/bytes. Accept only HTTP 200,
bounded UTF-8 JSON objects of the expected endpoint shape; reject duplicate JSON
keys and contradictory/malformed fields. Limit each response to 1 MiB before
parsing; note the pinned helper already buffers the response, so an upstream
streaming/response-size limit is also needed for a true transport memory bound.
Require each metadata response's message ID to equal the exact requested ID.
Validate page-token size, message count and IDs. Ignore no required malformed
record silently. A body on a metadata-only response is a protocol failure, not
something to persist. Do not expose raw response bodies as errors.

Pagination continues through empty pages that still have a next-page token.
Detect token cycles, duplicate IDs and budget exhaustion. `resultSizeEstimate`
is not an exact count or evidence of completion. A page token is opaque, not a
URL and not an instruction to change account/query. A capped/failed scan is
partial; never present it as complete mailbox history or infer missing messages
did not exist. Retry transient read failures with bounded backoff while the same
authorization remains valid; never retry auth failures by invoking another
credential source. A per-message 404 means unavailable, not proof of deletion
or absence. Record its coverage gap; do not advance a complete-coverage cursor.

## 5. Metadata and evidence semantics

Do not add mailbox data to existing `crm_contact_get`, `contact_detail`, contact
reports, native chat references, or any current `crm_read` response. Existing
scheduled jobs freeze that toolset; expanding its returned data would silently
expand their access. A future email-history endpoint and permission/toolset must
be separate and explicitly granted. Read-only Gmail permission does not grant
existing agents, scheduled jobs or the model access to the imported metadata.
Manual sync must be explicit; opening CRM, switching profiles or loading a
contact must not discover an account or start a mailbox read.

Keep a separate Gmail observation ledger, not record-change `crm_activity` and
not a forced conversion into the current `ProviderObservation.kind` enum.
That enum cannot express the deliberately weaker `observed_in_sent` fact.

- Entity key: `(workspace, profile, issuer, sub, provider_message_id)`.
  Account subjects distinguish identical IDs from different mailboxes. Threads,
  subjects and RFC Message-ID headers are not deduplication keys.
- Immutable observation: account key, message ID, trusted adapter version,
  local observation time, read provenance and the observed labels/history ID.
  Replay key includes a trusted local batch/read identity, not an agent flag.
- Mutable latest snapshot: labels, thread reference, safe display metadata,
  provider history revision and last observation time. New label snapshots do
  not rewrite earlier observations. Deduplicate entities independently from
  observations. History event replay uses account + history ID + event type +
  message ID + affected label set; generic `messages` and typed history arrays
  must not double-count a change.
- `SENT` means **observed in Gmail Sent**, never sent by CRM, submission receipt,
  recipient delivery, or an approved-message match. Google's label documentation
  also applies SENT to certain inserted messages, so it is not transport proof.
  [Gmail label semantics](https://developers.google.com/workspace/gmail/api/guides/labels).
- Non-SENT means **mailbox item observed**, not automatically received. INBOX,
  From and To do not independently authenticate origin, recipient delivery or
  absence of import. DRAFT items are excluded; no outgoing intent is inferred.
  Exclude SPAM/TRASH from the current view on every metadata read, including
  history refreshes and items relabeled after listing. For a previously observed
  item, retain an exclusion marker with account/message identity, revision
  and relevant labels, without new display headers. The test projection also
  carries the thread reference and provider ordering timestamp; it is not the
  final persistence schema. Preserve earlier immutable
  observations rather than deleting history or leaving an apparently current
  visible snapshot. Newly encountered excluded items need no display metadata.
- `internalDate` is a provider ordering timestamp, not a universally verified
  send/receive time; imported mail may use the header date. Retain the original
  value and its meaning. Header Date is separately sender-supplied. Do not set
  `provider_occurred_at` as though transport time were proved.
  [Message resource semantics](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages).

Selected display headers: From, To, Cc, Subject and Date. No Bcc by default.
Unfold legal header folding, decode RFC 2047 safely and cap lengths/counts.
Reject unsupported encodings, duplicate singleton headers, remaining control
characters and bidi formatting. Preserve a safe placeholder plus a bounded
issue code rather than raw rejected content. Rendering must use text nodes,
never HTML, link activation, image loading or automatic Markdown interpretation.
The synthetic tests cover plain-text projection, not a browser renderer.

From/To/Cc remain untrusted display claims, not verified contact identities.
Automatic contact creation, identity merging and outbound addressing are out of
scope. A future contact-linking policy must parse RFC addresses separately,
surface ambiguities, and avoid canonicalization that changes who an address
means. No header, subject or mail instruction can authorize tools or records.
Separate display metadata from minimal provenance and choose retention before
persisting either. Never log full mail metadata or include it in diagnostics.

## 6. History, atomicity and coverage

Initial enumeration is not a transactionally consistent mailbox snapshot.
Capture a valid starting history checkpoint before listing, stage bounded
message metadata, then catch up all history pages from that checkpoint. Validate
this profile-derived checkpoint against the real API in the later authorized
test; the reference explicitly discusses message/thread/list checkpoints.
Do not merely store a newer profile history ID after the scan, which can skip
changes during enumeration. If catch-up expires or exceeds budget, retain a
partial-coverage state and restart only within the approved window.

For subsequent runs, keep the same starting history ID across pages. Parse IDs
as decimal strings/arbitrary-precision integers, never JavaScript Number and
never `historyId + 1`. After the final page, stage its returned history ID with
all accepted changes. History may include changes outside the window: fetch only
the minimal allowed metadata necessary to filter, discard excluded items, and
disclose that incidental metadata processing in consent. A purely server-filtered
date-window incremental history API is not documented; if that disclosure is
unacceptable, use bounded list rescans instead of history.

History changes can add/delete messages and add/remove labels. Refresh each
affected current message once; current metadata may be newer than its triggering
event, so store event identity and snapshot revision separately. Never roll back
a newer snapshot using an older history replay. A removal event does not erase
the earlier observation. Maintain an unavailable/tombstone state, with an
explicit distinction between a documented deletion event and a GET 404.

Only one database transaction may publish staged observations, snapshot updates,
coverage state and the completed cursor. Compare-and-swap the previous cursor
and activation, and enforce unique keys for concurrent/replayed runs. A crash,
malformed page, fetch failure, changed identity or mid-page limit must leave
the old committed cursor untouched. If staged progress is persisted separately,
it is quarantined, account/query-bound and never mistaken for published history.
The included test models atomic replacement in memory, not database durability.

An expired/invalid `startHistoryId` commonly returns 404. Mark **history gap;
rescan required**, preserve prior evidence, and perform a new bounded scan only
within the existing authorized scope. A rescan can recover current messages,
not prove what was deleted while the cursor was unavailable. Do not claim the
gap is repaired completely or reset the cursor to “now” silently. Even an
otherwise complete run means **window enumeration finished**, not all-time
history, delivery or a transactional snapshot.
[History API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list),
[sync limitations](https://developers.google.com/workspace/gmail/api/guides/sync).

## 7. Required approval and acceptance checklist

Before any real account access or activating a configured connection:

- [ ] User selects the exact personal/Workspace account and own mailbox, plus
  the intended Hermes profile and CRM workspace. Do not discover it implicitly.
- [ ] Explain identity fields, selected mail headers/labels/IDs, date window,
  boundary and incremental incidental metadata, local/remote storage destination,
  retention and deletion controls. Confirm metadata-only behavior versus the
  broader readonly capability. No bodies or attachments in the first slice.
- [ ] Obtain explicit consent for the CRM-owned OAuth grant and any persistent
  refresh access. Development authorization is not account-access approval.
  Review Google app terms, scope verification and Workspace admin restrictions.
- [ ] Choose the assurance model explicitly, verify captured profile routing,
  stable identity checks, scope canonicalization and response-size limits.
  If promising atomic grant continuity or exact scope attestation, add the
  missing trusted host receipts first. Independently review
  the actual fixed endpoint/method/path allowlist and admission behavior.
- [ ] Review the optional manifest/client setup in the implemented pilot before
  enabling it. No hidden OAuth setup, executed setup commands, installed
  credentials or fallback integrations are included.
- [ ] Run a separately approved live test against a selected test mailbox and
  verify account selection, exact granted scopes, expired/revoked grants,
  identity/profile replacement, header anomalies, pagination, history expiry,
  crash recovery and SQLite/PostgreSQL atomicity. Distinguish unavailable tests
  from passes; include a real Desktop cancellation/profile-switch review.
- [ ] Keep sending/drafting/replying unavailable. There is no model-supplied
  approval flag. Any future send capability requires a new reviewed design and
  exact user-approved content/account/recipients plus unknown-outcome handling.

## 8. What the executable design verifies

Run `python -m pytest -q tests/test_gmail_readonly_design.py`.
The file contains pure, test-local specification examples and invented data.
It is not packaged under `hermes_crm`, imported by runtime code, a host adapter,
an OAuth declaration, a connector mock presented as live access or a production
authorization checker. Socket entry points are denied during these tests.

The suite covers typed response projection, fixed GET URLs and explicit mailbox
selection, identity mismatches and activation ABA, the **undetected credential
ABA counterexample**, bounded and empty-page pagination, repeated tokens,
malformed metadata, safe header decoding, account-scoped deduplication,
SENT/import semantics, label snapshot replacement, and all-or-nothing cursor
publication/expiry gaps. It does not execute the host helper, authentication
resolver or provider API. It does not verify OAuth, network isolation against
malicious code, database migrations/locking, real mailbox behavior, UI rendering,
or an account connection. Those are future gates, not successful tests here.
