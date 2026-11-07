# Optional Gmail metadata history

**Implemented, default off; live OAuth and mailbox behavior are not verified.**
This pilot has only synthetic provider tests. No account was connected, no OAuth
grant created, no mailbox read and no message sent during its development. It
works through the native authenticated Desktop plugin, not the standalone demo.
Ordinary CRM features work without Gmail setup.

## What it does

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

## Setup, only after account-access approval

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

## Storage, cancellation and retention

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

## Verification and remaining gates

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
