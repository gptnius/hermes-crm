# Optional Gmail metadata history

**Implemented and independently reviewed with synthetic providers, including
disposable PostgreSQL tests and default-off routing in the genuine pinned host;
real-account access and installed-host mailbox sync remain gates.** No real mailbox was opened,
credential inspected, grant created or message sent during development. Ordinary
CRM features work without either Gmail option.

## Existing Hermes connection: default-off bridge

The native Contact **Email history** panel can reuse the active Hermes profile's
existing Google Workspace connection. This is an explicit opt-in, not automatic
account discovery. It is separate from the older CRM-owned OAuth pilot under
**Advanced: separate CRM email connection**. Neither option works in the
standalone local view or gives CRM a sending tool.

### Applicability and host setup

Use a selected account's own Gmail mailbox, personal Gmail or Workspace Gmail,
with existing permissions sufficient for Gmail profile, message metadata and
history reads. A Google login without Gmail, insufficient existing permissions,
Workspace administrator restrictions, delegated/shared mailboxes and service
accounts are not established supported configurations. The bridge does not
create or broaden a grant, install software, discover an executable, or launch
sign-in. If the existing connection is unsuitable, stop and review setup
separately; there is no automatic fallback to another account or the OAuth pilot.

A trusted operator must configure the intended profile's Hermes CRM settings:

- **Existing Hermes Gmail bridge**: `gmail_bridge_enabled`, default `false`.
- **Trusted Google Workspace CLI path**: `gmail_bridge_gws_path`, default empty;
  an absolute path to a trusted administrator-installed **gws 0.22.5** executable.

The adapter selects exactly `google_token.json` beneath the active profile's
Hermes home. There is no account picker or arbitrary token-path field in CRM.
CRM passes that explicit path to gws without reading or copying credential
bytes. **gws itself reads the credential and may refresh an access token** into
its disposable private cache. This is real account access and requires explicit
authorization, even though no new grant is requested. Existing credentials may
have powers broader than the bridge's read-only commands; metadata-only requests
do not narrow the token's permissions.

Only the reviewed POSIX transport is supported. The executable and credential
must be regular, singly linked files, with no symlink path components. The
executable must be executable and not group/world-writable; the credential must
be owned by the current OS user with no group/world permissions. The adapter
uses a private temporary working directory, an empty `.env`, a scrubbed
environment and disposable CLI configuration/cache/key storage. Do not change
the selected profile, binary or connection during an operation. File checks and
mailbox verification detect observable changes, not an atomic credential lease
or immutable Google account identity.

Version output checks compatibility, **not binary provenance**. Review the source
and trusted installation route independently. The reviewed CLI source is
[0.22.5, commit cd3697e](https://github.com/googleworkspace/cli/tree/cd3697e07eb520056dcf142d0c7439bbb9ba32e9).
The distribution disclaimer is: **“This is not an officially supported Google
product.”** An official-repository release is not a Google product-support promise.
Enabling host settings alone makes no provider request and proves no working
installation. Never paste credentials into CRM, chat, source or screenshots.

### Verify, then choose what to read

1. Open native **Settings → Connections**. No Contact is needed. The same
   controls remain available under a Contact's **Email history → Account & sync settings**. Review the
   storage destination: the selected SQLite database or PostgreSQL database,
   which may be remote. Metadata is ordinary CRM data, not protected notes.
2. Choose **Verify existing connection**, enter the exact own mailbox and any
   explicit own aliases, select the approval checkbox in the surfaced review,
   then choose **Confirm verification (no messages read)**. The review scrolls
   into view and focuses the mailbox field; Escape cancels before dispatch. This reads the provider's
   mailbox profile and current history checkpoint, **not messages**. Aliases are
   user-supplied, not provider-verified. The default starting point is new changes
   from verification onward, not a historical import. Successful verification
   enables local use but does not enable app-open sync or read messages. Check
   **Verified mailbox** for the recorded identity. Host configuration alone is
   never displayed as verified. In-progress, failed, cancelled and unknown
   outcomes are distinct; unknown operations remain locked and are not resent.
   Recent receipt feedback survives route changes within the current pane
   lifetime; verified identity is loaded from durable local account state.
   Host flags and external account authorization must still be configured
   through Hermes; this panel cannot grant access or sign in.
3. Separately approve **Sync new metadata** for changes since that checkpoint.
   For older observations, explicitly choose **Read last 7 days** or **Read last
   30 days**. These are bounded workspace reads, not only a read of the Contact
   currently open. Unrelated message metadata may be examined in memory; only
   matching or reviewable candidate observations are retained. Newly added or
   changed Contacts do not trigger a hidden historical backfill.
4. Optionally approve **Sync while CRM is open**. Checks occur at least five
   minutes apart while the native CRM pane is open and eligible to poll. There
   is no daemon, cron, startup job or promise of sync while the app is closed.
   Opening Settings/the pane or **Refresh local status/history** only loads local state; it
   does not itself read Google. An already approved poller can read later.
5. Review receipts, coverage and **Participants & match evidence**. A partial or
   unknown operation is not a completed read. Refresh reconciles the saved
   receipt rather than automatically resending the request. An expired history
   checkpoint is **requires resync** and requires a newly approved 7- or 30-day
   window; no hidden checkpoint reset occurs.

Reads request Subject, From, To, Cc, Date, selected labels, provider IDs and
ordering metadata. **No bodies, snippets, Bcc, MIME content or attachments** are
requested. There is no send, draft, reply, mark-read or label modification.
Headers are untrusted text. A Sent label means observed in Gmail Sent, not proof
of CRM sending, delivery, reading or authenticated sender identity. Provider
ordering timestamps can reflect imported mail. Missing results, unsupported
headers, excluded drafts/spam/trash, bounded history and provider failures mean
absence is never proof of no correspondence.

### Contact and Company association

Exact supported email addresses and explicitly entered Contact aliases determine
associations. Domain case is normalized; dots, plus tags and local-part case are
not collapsed or guessed. Own mailbox/explicit own aliases are excluded. One
message can belong to several unambiguous Contacts. Retained ambiguous or
case-mismatch candidates, including duplicate Contact addresses, and identity
changes remain reviewable instead of being silently assigned. Unsupported or unmatched messages
may be omitted, so not every problematic header appears in review. Use **Edit
contact email aliases** to supply known aliases. Explicit aliases persist until
you edit or remove them, including after a primary email address changes. Current
identities are checked on publication and display; old evidence
does not silently become a valid current link after an address change.

Company **Email history** is read-only and groups retained observations through
**current explicitly linked Contacts**. Names or email domains do not create
Company links. No Deal, Task or Event association is inferred. Email observations
remain separate from self-reported Logged contact and ordinary audit history.
Syncing metadata does not create a Logged contact entry or update that reporting
measure. They are not added automatically to agent tools, native chat context, ordinary
record responses or scheduled research.

### Pause, disconnect, clear and recover

- **Stop app-open sync** stops polling. **Pause sync** disables local bridge use
  while retaining the selected identity and metadata; **Resume sync** is explicit.
- **Disconnect locally** disables use and removes the active selection while
  retaining observations. A future verified binding receives its own account
  namespace; different connections are not silently merged. Re-verifying
  the same mailbox can therefore retain a second observation of the same message
  in the new namespace; old retained history is not silently merged or deleted.
- **Clear retained metadata** deletes bridge observations across this workspace
  and resets its checkpoint. The selected identity, aliases, operation receipts,
  database logs and backups can remain. Clearing is not Google grant revocation
  or mailbox deletion. After clearing, choose an explicit bounded history read
  before incremental reads can resume.

Local controls fence publication by cancelled or superseded operations. A
provider call already dispatched cannot be recalled; navigating away is not
server cancellation. Durable leases and receipts expose running, unknown,
partial and requires-resync states. Only complete batches publish retained
observations and advance the checkpoint, atomically. Retained rows show last
observations, not guaranteed current mailbox state; explicit deletion history,
unavailable metadata and absence from a query are distinct.

Each scan is bounded to 10 provider pages, 1,000 distinct message IDs and a
120-second deadline, with at most 30 seconds per transport request. A busy
historical window can therefore remain partial without advancing its checkpoint.
This is not a bulk mailbox archive importer; an empty or partial view never proves
that all correspondence was captured.

Receipts are durable but bounded: at most 10,000 ordinary receipts are retained,
with older terminal receipts compacted automatically; active and unknown
operations are protected. Control receipts have a separate 128-receipt limit.
After ordinary receipt compaction, a missing lookup may report
`expired_or_unknown`; otherwise it may return null. Absence never proves no action.
Revision fencing prevents replay with a stale revision even after receipt expiry.

Disconnect and clear never revoke Google's grant or sign out of Hermes. Manage
the existing Workspace connection separately using its authorized host controls.
Encrypted CRM backups include scoped retained bridge metadata and receipts, not
credential bytes. Restore preserves these as quarantined recovery evidence and
leaves the live bridge disabled, without restoring an active account, lease,
cursor or polling state. A restore does not resume mailbox access.

### Verification limits

Synthetic transport, matching, incremental, storage, API, UI and recovery tests
use invented data. They do not establish a real login, permissions, refresh,
Google matching behavior, administrator policy or physical Desktop operation.
Independent core/UI review, local aggregate checks and a full disposable
PostgreSQL-backed run passed. Both genuine pinned-host modes also passed
authenticated default-off routing and profile isolation. Separately authorized
real mailbox reads and installed-host sync remain gates; disabled-route checks
do not establish provider behavior.
Consult the current [verification record](VERIFICATION.md) for exact run counts
and blockers. See the [bridge design and constraints](GMAIL_BRIDGE_PLAN.md).

A Linux binary from the official-repository [v0.22.5 release](https://github.com/googleworkspace/cli/releases/tag/v0.22.5)
was checked without credentials against its companion release checksum. Its
`--version` output matched the expected two lines, and top-level `--help` showed
the Gmail command family and `--params`, `--format` and `--api-version` options.
This is narrow binary/version/top-level-help evidence, not endpoint or mailbox
validation. A fresh isolated CLI configuration needs network access to public
Google Discovery metadata before endpoint command parsing. Endpoint-specific
help failed because `www.googleapis.com` could not resolve in the test
environment. Endpoint behavior, token refresh and real mailbox reads therefore
remain unverified; a passing version check alone is not sufficient setup.

Focused no-provider checks:

```bash
python -m pytest -q tests/test_gmail_gws.py tests/test_gmail_matching.py tests/test_gmail_incremental.py tests/test_gmail_bridge_store.py tests/test_gmail_bridge_api.py tests/test_gmail_bridge_runtime.py tests/test_gmail_bridge_recovery.py
python scripts/build_email_bridge_panel.py --check
node --experimental-vm-modules tests/desktop_email_bridge.mjs
```

Use `HERMES_CRM_TEST_POSTGRES_URL` only for a disposable database for
`tests/test_gmail_bridge_postgres.py`. None of these checks authorizes or requires
a real Google account.

---

## Advanced: separate CRM OAuth pilot

**Implemented, default off; live OAuth and mailbox behavior are not verified.**
This pilot has only synthetic provider tests. No account was connected, no OAuth
grant created, no mailbox read and no message sent during its development. It
works through the native authenticated Desktop plugin, not the standalone local view.
Ordinary CRM features work without Gmail setup.

### What it does

On a contact record, Email history can explicitly verify a selected own mailbox
and read a manually approved 7- or 30-day query for that contact's email address.
Opening a record or refreshing local status does not discover an account or call
Google. There is no background sync, mailbox-wide history cursor, model tool,
sending, drafting, reply, mark-read or other mailbox change.

The separate ledger retains selected Subject, From, To, Cc and Date headers,
labels, message/thread IDs, provider ordering timestamps, observation time and
query provenance. It requests no bodies, snippets, MIME parts, attachments or
Bcc. Headers remain untrusted plain text. Unsupported address syntax is rejected,
not silently widened. Aliases, Bcc, imported mail and incomplete provider results
can limit matching; an empty result does not prove no correspondence exists.

An item with a SENT label is **observed in Gmail Sent**, not proof CRM sent it,
that it matches an approved message, or that anybody received it. Other items
are **mailbox items observed**, not automatically received mail. Retained rows
show their last observation, not current mailbox state; absence from a later
query does not delete evidence or prove deletion. Google's internalDate is an
ordering timestamp and can derive from imported mail, not verified delivery time.

### Setup, only after account-access approval

Both ordinary personal Gmail and Google Workspace Gmail are candidates. A Google
account without Gmail is insufficient; Workspace administrator policy may prevent
access. Use only the selected account's own mailbox, not delegated/shared mailboxes
or service-account domain-wide delegation. This release does not establish that
any particular account is configured or eligible.

1. Review the code, data scope, target profile/workspace and the privacy limits
   below. Installing a version that adds the optional OAuth declaration can
   trigger Hermes's re-pin permission prompt. That declaration does not create
   a grant or verify a live connection.
2. In your own Google Cloud project, enable the Gmail API, configure the OAuth
   consent screen and register an OAuth **Desktop app** client. Use Google's
   [native-app guidance](https://developers.google.com/identity/protocols/oauth2/native-app)
   and [Gmail authorization guide](https://developers.google.com/workspace/gmail/api/auth/web-server).
   External testing-mode apps may require adding the chosen account as a test
   user and have refresh-token restrictions. Review Google's current requirements;
   do not bypass verification or an administrator restriction.
3. In the intended Hermes profile's CRM plugin settings, supply the client ID
   and matching client secret through Hermes's secret fields
   (`HERMES_CRM_GMAIL_CLIENT_ID`, `HERMES_CRM_GMAIL_CLIENT_SECRET`). CRM never reads
   those values, handles tokens or copies existing Workspace/other-plugin grants.
   Do not paste credentials into CRM forms, chat, source files or screenshots.
4. Turn on `gmail_history_enabled` for that profile. It remains off by default;
   enabling it alone makes no provider call. After separately approving the
   account and persistent access, run the host-owned flow yourself in a terminal:

   ```bash
   hermes --profile YOUR_PROFILE auth add hermes-crm:gmail-history-readonly
   ```

   This is a supported command shape in the pinned host, not a live-tested
   sign-in for this plugin. The panel does not execute it. Hermes owns the PKCE
   flow, loopback callback, grant storage and refresh. A remote host may require
   the host's documented callback tunnel; do not open extra ports automatically.
5. On a contact record, choose **Verify own mailbox**, review the exact address
   and confirm the identity/profile read. Only a successful provider identity
   match changes the saved status to verified. This does not read message history.
6. Choose **Read Gmail history**, review the mailbox, contact address, date range
   and storage destination, then confirm. Check the operation result and coverage.
   There are at most 10 list pages/1,000 unique message IDs and a 120-second overall
   dispatch deadline. Partial results are labelled; a failed scan publishes no
   staged metadata. Refresh local status reconciles the existing operation and
   never repeats a provider read.

Requested scopes are exactly Gmail readonly, OpenID and Google's canonical email
identity permission. No profile, send, compose, modify, Calendar, Drive, Contacts,
Sheets or Docs scope is requested. **Gmail readonly can read bodies even though
this implementation only requests metadata.** Google does not support the list
query parameter with the narrower Gmail metadata scope. The pinned host compares
scope strings but does not provide CRM an exact granted-scope receipt, so requested
minimal scopes are not proof of the actual token's maximum powers. Review actual
consent and any pre-existing grants in the separately authorized live test.

### Storage, cancellation and retention

Metadata is stored in the selected CRM backend: profile-local SQLite or the
explicitly selected PostgreSQL schema, which may be on a remote server. This is
not necessarily only on the Desktop computer. Know that destination before
approving reads. Nothing adds email metadata to `crm_read`, native chat context,
ordinary contact-detail responses or scheduled agent assignments.

A confirmed read remains bound to its original profile/workspace and **can finish
and save there after you navigate away**. The UI ignores responses for old views;
navigation is not server cancellation. **Disconnect locally** invalidates the
binding and operation, preventing further reads and publication. A provider
request already dispatched cannot be recalled. A crash may leave the operation
running/unknown; refresh its local receipt, then disconnect explicitly before
starting new work. Never interpret a missing response as permission to repeat.

**Forget local email history** removes retained metadata rows and clears the
local identity, across all contacts in this workspace. Minimal operation receipts
are retained for deduplication/reconciliation; database backups and transaction
logs are outside this control. Disconnect retains observations until forgotten.
Neither action revokes Google's grant or signs out of Hermes. Manage that
separately through the host, for example the pinned host's user-run
`hermes --profile YOUR_PROFILE auth logout hermes-crm:gmail-history-readonly`.
Rebinding requires clearing old retained history first; there is no silent
account switch or merge.

The own-mailbox pilot relies on Google's resource authorization and a trusted
operator keeping the grant/client configuration stable during a read. Explicit
mailbox paths plus before/after subject checks do not constitute an atomic grant
lease. Do not reconfigure client variables, reconnect or switch accounts mid-read.
The host buffers responses before the adapter's size validation; the adapter's
1 MiB parser limit is not a transport streaming-memory guarantee.

### Verification and remaining gates

Synthetic reader, SQL storage, REST and React tests exercise only invented data.
They do not establish Google OAuth consent, token refresh, account selection,
actual Gmail query matching, real mailbox headers, Workspace admin behavior or a
physical Desktop flow. Live authorization/mailbox tests, native visual QA and
Google restricted-scope distribution review remain required before claiming a
working connection or production readiness.

Run the focused checks with:

```bash
python -m pytest -q tests/test_gmail_reader.py tests/test_gmail_history_storage.py tests/test_gmail_runtime.py
python scripts/build_email_panel.py --check
node --experimental-vm-modules tests/desktop_email_history.mjs
```

Use `HERMES_SOURCE` for the opt-in actual pinned-host OAuth declaration parser
check, and `HERMES_CRM_TEST_POSTGRES_URL` only for a disposable database when
running `tests/test_gmail_history_postgres.py`. These remain no-provider tests.
The earlier [design record](GMAIL_READONLY_PLAN.md) also discusses broader history
sync; that broader scope is not implemented by this pilot.
