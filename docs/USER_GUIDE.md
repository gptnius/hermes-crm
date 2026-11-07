# Hermes CRM: setup and user guide

Hermes CRM keeps contacts, deals, follow-ups and activity in one workspace that
you can use from Hermes Desktop and your existing Hermes agent. Start here to
install it, try a small example and understand what the current prototype does.

**This is a local-user prototype, not production or multi-tenant CRM software.**
Start with invented data. It does not send outreach, import a mailbox, or run an
agent just because you save a record. Gmail is an optional, default-off pilot
with no live-account verification yet.

## Contents

- [Features and the two ways to run](#features-and-the-two-ways-to-run)
- [Install in Hermes Desktop](#install-in-hermes-desktop)
- [Try the standalone demo](#try-the-standalone-demo)
- [Your first contact, deal and follow-up](#your-first-contact-deal-and-follow-up)
- [Record an actual conversation](#record-an-actual-conversation)
- [Build reports and dashboard cards](#build-reports-and-dashboard-cards)
- [Work with your Hermes agent](#work-with-your-hermes-agent)
- [Save and schedule future internal work](#save-and-schedule-future-internal-work)
- [Optional Gmail history](#optional-gmail-history)
- [Storage, profiles and backups](#storage-profiles-and-backups)
- [Troubleshooting](#troubleshooting)
- [Limits and verification](#limits-and-verification)

## Features and the two ways to run

**Native Hermes Desktop is the main experience.** It provides:

- Contacts with name, email, company, job title, notes and Contact type
  (`lead`, `customer` or `partner`). Search and combine filters for linked deal
  stage, Contact type, company, email presence and follow-up status.
- Deals linked to contacts, with USD value, probability, expected close date,
  notes and six stages: Lead, Qualified, Proposal, Negotiation, Won and Lost.
- Follow-ups with a due date/time, normal or high priority, open/done state,
  notes and optional contact/deal links.
- A dashboard with pipeline totals, weighted value, stage drill-through and
  leads needing attention, plus saved reports and custom cards.
- Contact details, related records, CRM activity, and a separate self-reported
  contact log for meetings, calls, emails, chats and other interactions.
- A CRM companion beside an existing native conversation, reviewed copy/paste
  requests, explicit one-shot reminder scheduling, and future internal-work
  assignments with saved results and review states.
- Profile-scoped SQLite storage by default, with explicit PostgreSQL support.

**The standalone browser demo** is a smaller, loopback-only way to try the core
contacts, pipeline, follow-ups, activity and preset dashboard views without
Hermes Desktop. It does not provide the native report builder, contact-log
panel, Gmail pilot, chat companion or native assignment/scheduler controls.
It is not a hosted web application or a substitute for native integration tests.

## Install in Hermes Desktop

### 1. Check the host before installing

You need Git, the Python dependencies declared by this project (Python 3.11 or
newer), and a compatible Hermes Agent **and** Desktop build. Follow the
[official Hermes documentation](https://hermes-agent.nousresearch.com/docs/)
for installing Hermes itself.

The verified host is the official Hermes source revision
[`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`](https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19),
including its Desktop SDK. Desktop and Agent version labels differ. The plugin
manifest's `requires_hermes: >=0.23.0` is **not** a verified minimum-version
promise. In particular, the checked Desktop 0.17.0 lacks required APIs and only
shows a compatibility notice. Read [Host compatibility](COMPATIBILITY.md) before
changing an existing installation. The plugin never upgrades Hermes for you.

No new CRM account, model API key or paid service is needed for ordinary record
editing. Agent conversations and scheduled analysis use your existing Hermes
provider configuration and its ordinary permissions and costs.

### 2. Get and review the source

```bash
git clone https://github.com/gptnius/hermes-crm.git
cd hermes-crm
```

Review the checkout and its dependency declarations before installing. There is
no JavaScript build step for the native pane: it uses the host's SDK and React.
Keep credentials and personal data out of the checkout.

### 3. Install and enable both components

Run the following with Hermes configured for the profile you intend to use.
Replace the example path with your checkout's absolute path:

```bash
hermes plugins install "file:///absolute/path/to/hermes-crm"
hermes plugins doctor /absolute/path/to/hermes-crm
hermes plugins validate /absolute/path/to/hermes-crm
```

The `file://` form matters: the bare absolute path was misinterpreted as a
GitHub identifier by the tested host. Follow Hermes's dependency and enablement
prompts. In **Capabilities → Plugins**, enable both the **agent/backend** and
**Desktop** components for the intended profile. Enabling just one is not enough.

Open **CRM** in the sidebar, or **Open Hermes CRM** in the command palette.
Native mode needs no standalone server, localhost URL, iframe or separate API
token. For a remote Hermes connection, the backend component belongs on that
host and the Desktop component must also be installed on the Desktop computer.

### 4. Choose empty or synthetic data

Check the connection/profile shown in CRM. An empty workspace lets you create
your first contact or choose **Explore demo data**, followed by a separate
confirmation. The demo contains eight invented contacts, eight deals and five
internal tasks, using reserved example-domain email addresses. It refuses to
seed a workspace that already contains CRM records.

Use a disposable profile for exploration. Switching the active app connection
or profile switches the CRM workspace and clears previous views and unfinished
forms. Do not use switching as a way to cancel a save already sent to the backend.

### Updating an installed copy

Review the new revision, preserve your data and resolve any pending operations
before updating. Hermes Desktop copies the plugin's Desktop file into its own
plugin root, so editing or pulling the source checkout alone may not update the
installed copy. Update both the backend and Desktop components to the intended
plugin revision through the host's plugin install/update workflow. Rescan in
**Capabilities → Plugins**, and restart the intended Hermes gateway/backend and
Desktop app as required by that workflow, then reopen CRM. A separately running
gateway can still serve an older backend even after Desktop reloads. Coordinate
a gateway restart with any running agent work; do not stop an unrelated process.
A linked development checkout has a different hot-reload workflow; see
[Native Desktop](NATIVE_DESKTOP.md).

Check that you reopened the intended app and profile rather than an older
installed Desktop. Closing an old app does not give it the new SDK capabilities.
There is no automatic database migration or app upgrade in this project.

## Try the standalone demo

From the repository root, on a Unix-like shell:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
export HERMES_CRM_DATA_DIR="$PWD/.demo-data"
hermes-crm --demo
```

Open [http://127.0.0.1:8742](http://127.0.0.1:8742). Stop the server with Ctrl+C.
On later starts, reactivate the virtual environment, select the **same** data
directory and omit `--demo`:

```bash
. .venv/bin/activate
export HERMES_CRM_DATA_DIR="$PWD/.demo-data"
hermes-crm
```

To start empty, choose a different fresh data directory and omit `--demo` on the
first run. Never seed an existing datastore. If port 8742 is already in use,
choose another, for example `hermes-crm --port 8743`, and open that loopback port.

This server deliberately binds to `127.0.0.1` and has no public authentication
or multi-user permissions. Do not expose it through a public proxy or tunnel.
Starting it does not install or connect the native plugin.

## Your first contact, deal and follow-up

These steps use native Desktop labels. Use invented data in a test workspace.

1. Open **Contacts → + Contact**. Enter `Demo Buyer`, `buyer@example.com`,
   company `Example Company`, and Contact type **Lead**. Add any useful notes
   and save. Open the contact to see its details and related records.
2. Choose **Create deal** on that contact. Give it a title such as
   `Example pilot`, enter **12000** in the USD value field, choose
   **Qualified**, review probability and expected close date, and save.
3. Choose **Create follow-up** on the contact or deal. Use a title such as
   `Review pilot requirements`, pick a due date and time, and save. The ordinary
   form interprets its date/time in the computer's local timezone and stores an
   absolute time. Choose normal or high priority as appropriate.
4. Return to the dashboard or pipeline to inspect the new deal. Use a stage
   drill-through or combined contact filters to find matching contacts. Use
   **Clear filters** to return to an unfiltered list.
5. When the human follow-up is actually done, mark the task done. A saved due
   date is only a CRM record: it does not create a reminder or schedule an agent.

**Contact type and deal stage are separate.** A lead contact may have multiple
deals in different stages; there is no guessed primary stage. A stage-filtered
contact report counts that contact once even when several linked deals match.

The pipeline's open and weighted values exclude Won and Lost deals. Weighted
value uses each open deal's probability; it is a planning estimate, not booked
revenue. USD is the only currency. The UI accepts dollars; tools and APIs use
integer cents, so **$12,000 = 1,200,000 cents**.

Open a record and choose **Edit** to change it. If a version conflict appears,
refresh and review the latest record rather than overwriting another change.
CRM activity records edits; it does not prove a customer was contacted.

## Record an actual conversation

On a native contact detail, open **Logged contact → Log contact**. Enter the
actual past time with an explicit timezone, select the kind and direction,
write a short factual summary, then **Save contact log**.

For example, `2026-11-06T14:00:00-05:00` means 2 PM at UTC−05:00. Use the real
time of the interaction, not a future planned call. `Z` means UTC.

This is a self-reported claim. Logging an email does not send it, read a mailbox
or verify delivery. The latest active entry becomes **Last logged contact** in
reports. If an entry is wrong, choose **Void entry**, provide a correction reason
and confirm. The original entry remains visible but no longer contributes to
that last-contact value.

## Build reports and dashboard cards

In native Desktop's main dashboard:

1. Choose **Build a report**. Start with **Preset: leads table**,
   **Preset: leads per day** or **Preset: closed won**, or select Contacts,
   Deals or Tasks and choose the fields yourself.
2. Give the report a title. Select columns, combine ALL/ANY conditions, sort,
   and optionally group and summarize a numeric field. Choose a table, metric,
   bar, line or donut presentation that fits the result.
3. Choose **Preview live** and inspect fields, filters, units and results.
   Choose **Save report**, then **Preview live** again for the saved version.
4. Choose **Add saved version to dashboard**. On the card, choose **Run live**
   to fetch current results. Click a chart value or its accompanying summary to
   inspect contributing records.
5. Use **Move up**, **Move down** or **Remove card** to arrange the dashboard.
   Removing a card leaves the saved report intact. The saved-report list also
   supports archiving and restoring report definitions.

A useful first table is lead contacts with linked stages, last logged contact
and next follow-up, sorted by next follow-up. The built-in presets give you a
starting definition to inspect rather than requiring a query language.

Cards pin a specific saved report version. After editing a definition, an older
card is marked outdated: choose **Review latest version**, preview it, and
explicitly adopt it. There is one custom dashboard per workspace, with up to
twelve cards. Saved here means shared by the pane and agent in that workspace,
not published to other users. Cards are not scheduled monitors.

Read the results carefully:

- **Next follow-up** is the earliest open linked task, including overdue tasks.
- An empty **Last logged contact** means no active claim was logged, not that
  nobody ever contacted the person.
- **Leads per day** groups creation dates of contacts currently classified as
  leads, using UTC days. It is not a historical lead-status funnel.
- **Closed won** selects deals currently Won. Expected close date is not an
  actual win date.
- A drilldown is a new live read with the report's predicates, not an immutable
  copy of the earlier result. Records may have changed meanwhile.

See [Saved reports and dashboard cards](FLEXIBLE_REPORTS.md) for supported fields,
query bounds, chart coverage warnings and agent tools.

## Work with your Hermes agent

The native pane and native CRM tools use the same active-profile records. Open
an existing primary Hermes conversation in the same connection/profile, then
choose **Chat with Hermes** to open CRM beside it. No new model configuration is
required by CRM.

You can ask, for example:

- “Create a CRM contact named Demo Buyer with email buyer@example.com and
  company Example Company. Use request key guide-demo-buyer-1.”
- “Find Demo Buyer and create a $12,000 qualified deal linked to that contact.
  Show me the saved deal and amount.”
- “Show lead contacts with no open follow-up. Do not send messages or schedule
  anything.”
- “Preview a report of lead contacts, their linked stages, last logged contact
  and next follow-up. Let me review it before saving a dashboard card.”
- “Read the latest version of Example pilot and change its stage to proposal.”

Resolve ambiguous people, records and times before making changes. The example
request key belongs to one create intent; use the same key only to recover that
same request, not to create another record with different fields.

For a record handoff, **Preview record reference** and **Copy record reference**
prepare minimal identifiers for you to paste, review and send in the native
composer. The plugin does not write the native draft or submit prompts for you.
On a follow-up, **Prepare agent request** offers reviewed requests for immediate
help or future work. Interactive chat uses the host's existing tools and
permissions; CRM does not supply web research or an email-sending integration.
See [Native chat](NATIVE_CHAT.md) and [Assignment workflow](ASSIGNMENT_UI.md).

## Save and schedule future internal work

Keep four things separate: the business follow-up, saved assignment, native
schedule and reported result. A successful save or schedule does not prove the
work ran or the business task is complete.

For a **simple local reminder**, explicitly ask your Hermes agent to schedule
an existing future open follow-up as a one-shot reminder. The host gateway must
be running. Completing the task does not remove the job; the reminder checks
the current task status when it runs.

For **future internal CRM analysis**:

1. Open an existing open follow-up and choose **Save future assignment**. Enter
   the human owner label, instructions, success criteria and an ISO run time
   with a timezone offset. Choose a time at least five minutes in the future.
   Run time is separate from the follow-up's due date.
2. Choose **Review assignment**, inspect the exact task/version and request,
   then **Save assignment**. **Saved, not scheduled** means no native job exists.
3. Beside the intended existing primary Hermes conversation, select the exact
   saved assignment and choose **Review CRM scheduling**. Review its profile,
   conversation, instructions, time and provider-processing implications, then
   choose **Confirm schedule in CRM** if you want it scheduled.
4. Use **Check native status** for an explicit scheduler observation. A local
   history refresh only reads saved CRM evidence. Inspect any resulting native
   report and review its quality before treating the business work as done.
5. To stop future scheduling, use **Review CRM cancellation**, then
   **Confirm cancellation in CRM** for that exact assignment. This cannot stop
   an agent that is already running.

If an action in the ordinary CRM page first opens the companion, choose the
action again beside the chat. Manual Preview/Copy/Paste/Send remains an
alternative to the CRM-confirmed scheduling lane.

Scheduled assignments have restricted CRM read/report tools and local output.
They cannot browse the web, create contacts, send email or run an outreach
sequence. The configured model provider may still process task data: local
output does not mean local-only model processing. Human owner is an
accountability label, not permission to act as that person.

The **Follow-up coverage** queue flags missing next actions, overdue tasks,
unscheduled work, uncertain scheduling, elapsed run times and reports awaiting
review. Its totals count evidence items, not unique contacts or guaranteed
failures. One task can have several assignment rows.

**If an outcome is unknown, do not create a replacement or click through again
with a new request.** Read the exact saved operation/assignment and reconcile
the native job. Use a same-request recovery action only where the UI explicitly
offers it. Closing a panel or app is not cancellation. Some recovery controls
exist only until the plugin/app reloads, although confirmed records and operation
receipts are durable. See [Assignment workflow](ASSIGNMENT_UI.md) and
[CRM-confirmed operations](CRM_CONFIRMED_OPERATIONS.md) before relying on this
prototype for scheduled work.

## Optional Gmail history

Skip this section if you only need the CRM. Gmail is **off by default**, is
native-only, and has been tested with synthetic providers rather than a real
Google account. Do not assume an existing Gmail or Workspace login is connected.

The pilot requires your own Google OAuth Desktop app setup, Hermes-managed
secret fields and a separately authorized host-owned sign-in. Follow
[Gmail setup and privacy](GMAIL_SETUP.md) for the complete sequence. Do not paste
credentials or tokens into CRM, chat, source files or screenshots.

After setup, the contact panel has separate **Verify own mailbox** and
**Read Gmail history** review steps. Reads are manual 7- or 30-day queries for
one contact's email. The implementation requests selected message headers and
metadata, not bodies or attachments. However, the requested Gmail readonly
OAuth scope is broader and can read bodies; review Google's consent carefully.

There is no automatic sync, send, reply, draft, mark-read or mailbox modification.
Observed Sent items are not proof that CRM sent them or that they were delivered.
Metadata stays in the selected CRM datastore and is not automatically added to
agent context or the self-reported contact log. **Disconnect locally** and
**Forget local email history** do not revoke Google's grant; host/Google grant
management is separate. Read the full guide's retention and cancellation limits.

## Storage, profiles and backups

SQLite needs no extra service. Native mode uses Hermes's profile-local plugin
data directory, with `data.db` as the database file. Without a standalone path
override, the fallback is `$HERMES_HOME/plugin-data/hermes-crm/data.db`, using
`~/.hermes` when `HERMES_HOME` is unset.

`HERMES_CRM_DATA_DIR` selects standalone data; it does not redirect native
profile storage. The standalone process does not follow Desktop profile
switches. Only use both against the same records when you have explicitly
selected the intended Hermes home and backend configuration.

Before an update or storage experiment, back up the intended workspace using a
consistent SQLite backup or your database administrator's PostgreSQL backup
procedure. Do not copy a live SQLite main file alone while writers are active;
journal/WAL state can matter. Keep backups private and outside the source repo.
There is no built-in backup, restore, export/import or schema-migration UI.

### Optional PostgreSQL / Supabase PostgreSQL

The default SQLite setup is the simplest starting point. To use PostgreSQL,
install the optional driver in the runtime that loads CRM:

```bash
python -m pip install -e '.[postgres]'
```

For standalone mode, set `HERMES_CRM_BACKEND=postgres`, securely supply
`HERMES_CRM_DATABASE_URL`, and explicitly select a dedicated
`HERMES_CRM_POSTGRES_SCHEMA`, for example `crm_demo`. Schema names must begin
with `crm_` and use lowercase letters, digits and underscores. The role needs
permission to create the schema and tables. Invalid PostgreSQL configuration
fails rather than silently falling back to SQLite.

For native mode, select `postgres` in the plugin's backend setting and supply
the database URL through Hermes's profile secret configuration. Native mode
derives a separate schema from the active profile's data directory. Setting the
standalone variables alone does not configure native mode. Switching backends
does not migrate existing records.

Supabase is a PostgreSQL connection option, not a Supabase REST integration or
verified hosted multi-tenant deployment. Hosted Supabase has not been tested.
Use TLS and a dedicated least-privilege role for remote databases, and review
[Hermes integration](HERMES_INTEGRATION.md) and the [README](../README.md#postgresql-and-supabase)
before configuring one.

## Troubleshooting

- **No CRM entry or backend unavailable:** check that both plugin components are
  installed and enabled in the intended profile. On remote connections, check
  both machines. Follow Hermes's rescan/restart workflow after installation.
- **New report features fail after updating:** confirm the Desktop and backend
  are running the same plugin revision. Restart the intended gateway as well as
  the app if it is still serving the old backend, then reopen CRM. Do not reset
  or reseed the datastore to fix a component-version mismatch.
- **Compatibility notice:** compare the exact host build with
  [Host compatibility](COMPATIBILITY.md). Reinstalling the plugin does not add
  missing host APIs. Do not disable the compatibility guard.
- **Expected records disappeared after switching:** check the active
  connection/profile and backend. The standalone demo may use a different
  `HERMES_CRM_DATA_DIR`. Do not seed demo data to recover missing records.
- **Saved report cannot be added as a card:** save the definition, then preview
  the saved version again. An edited report may require **Review latest version**
  on its card. Archived reports must be restored and reviewed.
- **A version conflict or changed-source error:** refresh, inspect current
  values, and decide whether the change or assignment still applies. Do not
  overwrite blindly.
- **Save/schedule response lost or unknown:** inspect its original request key,
  record and operation/job evidence. Missing history on one page does not prove
  nothing happened. Do not create another assignment or job to “fix” uncertainty.
- **No reminder or report at the expected time:** check the gateway, exact
  native job state, approved time and provider availability. A saved task is not
  a schedule, and a scheduled job is not evidence of execution.
- **Gmail unavailable:** leave it off unless you intend to complete the optional
  setup. A local status refresh does not authorize Google access or test a grant.

## Limits and verification

- No public authentication, shared-user roles, tenant isolation, external
  messaging, calendar sync, imports, attachments or automatic outreach.
- No custom stages, arbitrary SQL/joins/formulas, dashboard-global filters or
  historical conversion funnels. Report dates/day buckets use UTC.
- Contact reports are server-paged, but legacy lists, deal/task views, related
  records and form choices are bounded at 500 records; activity is bounded at
  100. Deal-list totals cover returned records. Some coverage/aggregate queries
  scan complete local history and are not optimized for large workspaces.
- Reports allow up to 100 rows per page and 100 grouping buckets. Partial or
  unsuitable chart results are labelled rather than presented as complete.
- No direct native prompt submission, hidden session, automatic provider setup,
  automatic retry of unknown scheduling, or enabled Run now bridge.
- No migration system for deployed schemas. Advanced features fail closed on
  incompatible stored schemas rather than silently repairing them.

The repo's [verification report](VERIFICATION.md) records actual checks and
remaining gaps. Synthetic tests, controlled scheduler runs and a limited real
model check are not proof of general model quality, cross-platform usability,
visible notifications, restart recovery or production readiness. Live Gmail
OAuth/mailbox behavior and hosted Supabase are unverified.

For local development checks, from the repository root in your virtual
environment:

```bash
python -m pip install -e '.[test]'
python -m pytest -q
python scripts/build_email_panel.py --check
python scripts/build_report_panels.py --check
export HERMES_CRM_REACT_TEST_ROOT="$(mktemp -d /tmp/hermes-crm-react-tests.XXXXXX)"
npm install --prefix "$HERMES_CRM_REACT_TEST_ROOT" --ignore-scripts --no-audit --no-fund react@19.3.0 react-test-renderer@19.3.0
node --experimental-vm-modules tests/desktop_reports.mjs
node --experimental-vm-modules tests/desktop_contact_log.mjs
node --experimental-vm-modules tests/desktop_email_history.mjs
node --check hermes_crm/static/app.js
```

JavaScript checks need Node.js and the separately installed React test
dependencies above; those dependencies are not shipped with the plugin. The
temporary test directory can be removed when you finish. Host and PostgreSQL
integration tests are opt-in and may skip without their documented environment;
skipped checks are not
passes. Use disposable profiles/databases and invented data. A fresh Hermes
home alone does not prevent the host from discovering other CLI logins; follow
the [isolated-testing guidance](NATIVE_DESKTOP.md#isolated-testing-and-provider-discovery).

The project uses the MIT license. Dependencies retain their own licenses; see
[Licensing](LICENSING.md). Hermes CRM is not affiliated with Nous Research,
HubSpot or Salesforce.
