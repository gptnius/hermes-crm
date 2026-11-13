# HermesCRM

**Intelligent Relationship Management for you and your Hermes agent.**

HermesCRM is an open-source, local-first CRM inside Hermes Desktop. You and your
existing Hermes agent work with the same contacts, companies, deals, follow-ups
and relationship history. Research leads, manage a sales pipeline and log
conversations in one workspace. Tailor the CRM with custom fields and deal
stages, and build reports and dashboards with charts you can drill into to
explore the underlying records.

The contest core includes a working native interface and **83 agent tools**.
It is an early release for a local user's workspace, with the operational limits
listed below. Email connectors and sending are outside this edition.

[Watch the contest demo](https://x.com/gptnius/status/2120259388568961305) ·
[Setup and user guide](docs/USER_GUIDE.md) ·
[Current scope and roadmap](docs/ROADMAP.md) ·
[Catalog submission](https://github.com/NousResearch/hermes-agent/pull/152881)

## What you can do today

| Workflow | Available in the contest core |
| --- | --- |
| Build a relationship database | Create and edit contacts and companies; link people to a company and open its related contacts, deals, tasks and Events. |
| Manage sales and follow-ups | Track deal stages, USD values, probabilities and weighted pipeline; organize due dates, priorities and optional human owners. |
| Research leads with Hermes | Use the tools available in your existing Hermes conversation to research a person or company, create linked records, retain sourced evidence and review proposed notes. Search tools and provider access come from Hermes. |
| Keep relationship context | Log calls, meetings, emails, chats and other interactions; keep local Events and linked tasks. These are records of activity, separate from administrative record history. |
| Adapt the CRM | Add typed custom fields to contacts, deals and tasks, and configure deal stages with explicit open/won/lost outcomes. Desktop forms, agent tools and reports use the same definitions. |
| Build reports and dashboards | Save typed report definitions, add table/KPI/bar/line/donut cards and open the contributing records. |
| Bring records in and out | Preview, map and review contact CSV imports; export selected contact columns. Optional encrypted content exports support offline fresh-target recovery with retained keys. |
| Request future agent work | Explicitly schedule one-shot reminders, internal CRM analysis or bounded public research. Review saved results in CRM. Saving a task or assignment alone does not schedule it. |

Ordinary record editing needs no CRM account, paid service or new model API key.
Agent conversations use your existing Hermes provider configuration, permissions
and costs. New workspaces start empty; the demo's dashboard and pipeline use
sample records. Its Nous Research workflow shows separately saved agent research.
Neither sample data nor a saved report establishes a new live action.

## See the native workflow

CRM opens inside Hermes navigation and can sit beside the existing native chat.
The Desktop pane and agent tools share the active profile's datastore; there is
no separate CRM model client. For a record handoff, copy the checked record
reference, then paste, review and send it in native chat.

![HermesCRM dashboard populated with sample records beside native Hermes navigation and chat](https://github.com/user-attachments/assets/9fae4eea-53a0-4d24-9d2c-d1d5e50bb7a3)

*Dashboard with sample records, Hermes navigation and the native chat companion.*

![HermesCRM pipeline with sample deals beside native Hermes navigation and chat](https://github.com/user-attachments/assets/c2027b6a-0d27-4ccf-9b44-52acedf16e6d)

*Pipeline and follow-up context in the same native workspace. These
privacy-reviewed captures are also published in the catalog submission.*

Try an explicit request such as:

> Research a company using the public research tools available in this Hermes
> chat. Create a Company and linked Contacts for the people you can verify,
> retaining source references and distinguishing facts from hypotheses. Show
> me the saved records and any proposed notes for review.

Then use the same records to create a deal, set a follow-up, log an actual
conversation or build a dashboard card. Resolve ambiguous identities and times
before writing. See the [research-to-CRM walkthrough](docs/USER_GUIDE.md#research-to-crm-workflow)
and [agent assistance guide](docs/AGENT_ASSISTANCE.md).

## Quickstart in Hermes Desktop

You need Python 3.11+, Git and a compatible Hermes Agent **and** Desktop build.
The verified host source is official Hermes v0.23.0 at
[`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`](https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19).
Desktop and Agent labels differ; check [host compatibility](docs/COMPATIBILITY.md)
before changing an existing installation. The plugin does not upgrade Hermes.

The following selects the submitted core revision, rather than a development
branch:

```bash
git clone https://github.com/gptnius/hermes-crm.git
cd hermes-crm
git checkout --detach da1d1412eaf10c3ea8ba0b4431cafdbc59c6bcae
```

Review the source and dependencies, then install into your intended Hermes
profile, replacing the example with the checkout's absolute path:

```bash
hermes plugins install "file:///absolute/path/to/hermes-crm"
hermes plugins doctor /absolute/path/to/hermes-crm
hermes plugins validate /absolute/path/to/hermes-crm
```

Follow the host's dependency prompts. In **Capabilities → Plugins**, enable both
the **agent/backend** and **Desktop** components. Open **HermesCRM** from the
sidebar or **Open HermesCRM** in the command palette. Native mode needs no
standalone server, iframe or separate API token.

Create a contact, link a company, add a deal and save a due follow-up. Open an
existing matching Hermes conversation and choose **Chat with Hermes** to work
beside it. The [user guide](docs/USER_GUIDE.md) covers remote-host installation,
updating both components, profile switching and a step-by-step first workflow.
Updating the plugin preserves existing records; installation does not import
another user's data.

An [optional standalone local view](docs/USER_GUIDE.md#use-the-standalone-local-view)
offers a smaller core interface at `http://127.0.0.1:8742`. It is loopback-only and
does not provide all native editors, reporting or scheduling controls. Do not
expose it as a public service.

## Storage, permissions and external activity

- **SQLite by default.** Records belong to the selected Hermes profile.
  Native REST and agent tools use the same per-call storage factory and reject
  stale workspace writes. This is profile scoping, not multi-tenant access control.
- **Optional PostgreSQL.** Native **Settings → Storage** opens host-managed
  configuration and offers an explicit read-only connection check. Records go
  to the database URL you configure. Switching backends does not migrate,
  synchronize, merge or delete records; a connection check does not establish
  schema readiness or write permissions. Invalid PostgreSQL settings do not fall
  back to SQLite. Use a dedicated role and TLS for remote storage. Hosted-service
  deployment is unverified; see [storage setup](docs/STORAGE_SETTINGS.md).
- **User-managed secrets and recovery.** Native secret reads use Hermes's active
  profile scope. A masked host field may still be stored in plaintext `.env`.
  Optional protected notes and encrypted exports require separately retained
  keys; existing ordinary fields remain plaintext. There is no automatic backup,
  in-place restore or full-host recovery. See [protection](docs/PROTECTION.md)
  and [backup/restore](docs/BACKUP_RESTORE.md).
- **Explicit scheduling.** On your request, the agent or reviewed native command
  can create one-shot Hermes cron jobs for a task reminder, internal CRM analysis
  or bounded public research. Jobs run unattended, deliver locally and cannot
  schedule more jobs. Research may use Hermes web/search tools and third-party
  providers for the public question you approve; the gateway must be running.
  Host approvals remain in force. Reconcile unknown outcomes before retrying,
  and review results before applying notes or declaring work complete. See
  [assigned work](docs/NATIVE_ASSIGNED_WORK.md) and
  [public research setup](docs/PUBLIC_RESEARCH_SETUP.md).
- **Communication logs are available; email transport is separate.** This
  edition does not ship Gmail/OAuth connections, mailbox history or polling,
  email sending, calls, texts or calendar synchronization. Legacy provider table
  definitions remain solely for encrypted export and quarantined recovery;
  opening the core does not clear or reconnect them.

## Does it connect to email?

The **submitted core does not include an email connector**. A separate, opt-in Gmail metadata auto-logging
pilot has tested read-only metadata access through an existing Hermes Google
Workspace CLI connection: mailbox verification, an exact inbound-message
metadata match to a CRM contact, and one successful app-open automatic poll.
No message bodies or sends were included. Persistent/background synchronization
and general recovery were not established by those checks. Reusing a compatible
existing connection requires the needed read access; a connection or permission
to send is not proof of read scopes. Verification, history reads and polling have
separate controls. No new CRM OAuth grant is inherent when the existing connection
already has the required access.

Separately authorized Hermes CLI tools may send messages outside CRM, subject to
their existing send permission and user review. CRM adds no send grant; manually
logging a communication is a separate action, not provider delivery evidence.

That pilot is separate development/testing work, not a feature shipped in the
pinned contest entry. See [integration scope and next steps](docs/ROADMAP.md#email-and-other-integrations).

## Current operational limits

This is an early release for a local user's workspace, without public
authentication, shared-user roles or tenant isolation. It has not been qualified
for production operation or large datasets.

- Contact reports and Company/Event related lists/selectors are paged. Legacy
  record lists, deal/task views and form choices return up to **500 records**;
  legacy record history returns up to **100**. Deal-list totals cover returned
  records. Some aggregate/history queries scan local history.
- Reports have typed supported fields, up to 100 rows per page and 100 grouping
  buckets. Dates/day buckets use UTC. Multiple pipelines, arbitrary joins or
  formulas, calculated/required/unique fields, dashboard-wide filters and
  historical conversion funnels remain future work.
- CSV import is contact-only, create-only and bounded; it is not a full CRM
  migration. Attachments and external CRM connectors are not implemented.
- Native chat handoff preserves the existing conversation. The plugin does not
  write drafts, submit prompts or create a hidden session. Future assignments
  and scheduled research have separate, bounded permissions and require review.
- Native Desktop checks include macOS; broader platform, physical keyboard,
  screen-reader and responsive coverage remain incomplete. Broader real-model
  quality, visible reminders and operational restart/cutover recovery also need
  further qualification.

See [detailed limits](docs/USER_GUIDE.md#limits-and-verification),
[report boundaries](docs/FLEXIBLE_REPORTS.md) and the
[prioritized roadmap](docs/ROADMAP.md). Implemented functionality and remaining
release gates are documented separately there.

## Verification and development

The submitted core passed the official Hermes v0.23.0 validator's 16 checks,
genuine host registry/API checks with synthetic records, and a PostgreSQL-enabled
regression suite. Historical native UI and scheduler checks retain their exact
source and test scope in the [verification report](docs/VERIFICATION.md); they
are not all fresh tests of this revision or proof of general model quality.

[Hosted CI for the submitted commit](https://github.com/gptnius/hermes-crm/actions/runs/42724774779)
passed. The [credential-free CI workflow](docs/CI.md) uses disposable synthetic
data and PostgreSQL, does not deploy, and uses no provider credentials.
[The user guide](docs/USER_GUIDE.md#limits-and-verification) lists development
checks; use the matching run and revision when interpreting results.

For implementation details, see [architecture](docs/ARCHITECTURE.md),
[Hermes integration](docs/HERMES_INTEGRATION.md), [native Desktop](docs/NATIVE_DESKTOP.md),
[customization](docs/CUSTOMIZATION.md), [reports](docs/FLEXIBLE_REPORTS.md) and
[contact transfer](docs/CONTACT_TRANSFER.md). Historical detailed plans remain
linked from the [roadmap](docs/ROADMAP.md).

## License

MIT for this project's code. The original outlined wordmark derives from SIL
OFL 1.1 Libre Bodoni; its notice and provenance are retained. Dependencies retain
their own licenses; see [licensing and distribution notes](docs/LICENSING.md).
Product names describe compatibility. This project is not affiliated with
Nous Research, HubSpot or Salesforce.
