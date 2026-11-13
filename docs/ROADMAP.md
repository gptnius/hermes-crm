# Current scope and roadmap

HermesCRM's contest core is a working local-first CRM shared by Hermes Desktop
and the user's existing Hermes agent. This page separates available workflows
from future integration work and operational qualification. It makes no delivery
date or production-readiness promise.

The submitted code revision is
[`da1d1412eaf10c3ea8ba0b4431cafdbc59c6bcae`](https://github.com/gptnius/hermes-crm/tree/da1d1412eaf10c3ea8ba0b4431cafdbc59c6bcae).
See the [demo](https://x.com/gptnius/status/2120259388568961305),
[user guide](USER_GUIDE.md) and [verification report](VERIFICATION.md).

## Available in the contest core

- Shared native Desktop and agent access to contacts, companies, deals, tasks,
  local Events, communication logs and relationship activities.
- Pipeline stages and weighted USD forecasts; typed custom fields and configurable
  stages; saved reports, dashboard cards and contributing-record drilldowns.
- Research evidence and reviewable note proposals for exact contacts/companies.
  Interactive research uses the user's existing Hermes tools and permissions.
- Explicit one-shot local reminders, bounded internal-analysis assignments and
  opt-in scheduled public research, with saved results requiring human review.
- Reviewed create-only contact CSV import, selected-column export, optional
  protected notes and encrypted content export/fresh-target SQLite recovery.
- Profile-local SQLite and optional explicitly configured PostgreSQL, with
  native storage settings and a read-only connection check.

Current feature guides describe the limits of each workflow:
[Companies/Events](COMPANIES_EVENTS.md), [customization](CUSTOMIZATION.md),
[reporting](FLEXIBLE_REPORTS.md), [research evidence](RESEARCH_EVIDENCE.md),
[future assignments](ASSIGNMENT_UI.md), [scheduled research](SCHEDULED_RESEARCH_UI.md),
[CSV](CONTACT_TRANSFER.md) and [recovery](BACKUP_RESTORE.md).

## Next priorities

| Priority | Work to qualify or build | Evidence needed before claiming completion |
| --- | --- | --- |
| Operational reliability | Broader native-host and real-model workflows, visible reminders, interrupted/unknown outcomes and restart/cutover recovery. | Reproducible installed-host runs, retained result/identity evidence and explicit recovery outcomes. |
| Usability and access | Physical keyboard/focus, screen-reader, responsive/dark-mode and cross-platform acceptance. | Native-window review on the supported builds and platforms, beyond offscreen fixtures. |
| Larger workspaces and reporting | Replace bounded legacy lists/form choices, measure history/aggregate queries, extend report date/filter semantics. | Larger-dataset measurements and tests that reconcile totals, drilldowns and partial results. |
| Portability and retained context | Reviewed updates/merges, relationship-aware imports, resumable batches, record attachments and stronger retention controls. | Conflict review, provenance, explicit storage destinations and demonstrated recovery. |
| Multi-user workspaces | Design shared workspaces with explicit roles, permissions and ownership. | Authentication, enforceable access boundaries, audit behavior, concurrency and isolation tests. Pointing clients at one database is not this feature. |
| Fuller email integration | Qualify the read-only metadata pilot, then design broader history/sync and reviewed provider-backed communication. | Separate read/send scopes and controls, supported credential routes, live authorization/recovery tests and durable provider outcomes. |
| Established CRM connections | Connect to systems such as HubSpot and Salesforce with reviewed field ownership and conflict handling. | Account authorization, durable external IDs and tested refresh, write-back and recovery contracts. |

These priorities do not enable new tools or permissions. Multiple pipelines,
historical funnels, arbitrary formulas/joins, custom objects and multi-user
authorization are outside the current core.

## Email and other integrations

**Communication logging is available today.** You or your agent can record an
actual email, call, meeting or chat as a self-reported interaction. This is
distinct from provider-verified delivery, an inbox connection or sending.

**A separate, opt-in Gmail metadata auto-logging pilot has passed a bounded live check.** At pilot
revision
[`c8ef7f2ffafc74f6d710e0fcff0447713ad8cef3`](https://github.com/gptnius/hermes-crm/tree/c8ef7f2ffafc74f6d710e0fcff0447713ad8cef3),
authorized testing through an existing Hermes Google Workspace CLI connection
verified the mailbox, matched exact inbound message metadata to a CRM contact,
and completed one successful app-open automatic poll. This was read-only metadata
access, with no message bodies or sends.

The pilot is **not shipped in the pinned contest core**. The check does not
establish persistent/background synchronization, general recovery, a new OAuth
grant or the readiness of later broker changes. Further authorization,
reopen/recovery and host-compatibility validation remain release gates. The
pilot is development/testing work, not an installation recommendation. The
published pilot README records its earlier synthetic baseline; the bounded live
result above is a separate later validation result.

Reusing an existing compatible Hermes connection requires the needed read access;
its presence or send permission is not proof of read scopes. Mailbox verification,
history reads and polling remain separately controlled. No new CRM OAuth grant
is inherent if the connection already has the required access.

Separately authorized Hermes CLI sending remains outside CRM and subject to its
existing send permission and user review. CRM grants no additional sending
access. Manual communication logs, this read-only metadata pilot and CLI sends
are distinct; a log entry does not prove provider delivery.

Always-running inbox synchronization, provider-backed communication activity,
email sending, calling/texting and calendar synchronization require separate
design, authorization, provider evidence and testing. No roadmap item grants
account access or bypasses user review or Hermes approvals.

HubSpot/Salesforce linking is also future work: durable external identifiers,
field ownership, conflict review and recovery must precede any read-only refresh,
reviewed write-back or two-way synchronization claim. CSV import is a different,
already available capability. Guided hosted-storage setup is also future work;
PostgreSQL support alone does not establish a tested hosted service or tenant
isolation.

## Release boundaries and historical plans

The core remains a local-user early release. Its legacy 500-record list/form
bounds, 100-entry record-history bound, report limits, user-managed keys and
profile/host requirements still apply. See [current limits](USER_GUIDE.md#limits-and-verification),
[host compatibility](COMPATIBILITY.md), [storage](STORAGE_SETTINGS.md) and
[protection](PROTECTION.md).

Earlier implementation plans retain design history and completed increments;
their titles do not mean that every item is still pending or already released:
[development plan](DEVELOPMENT_PLAN.md), [agent-work plan](NEXT_RELEASE_PLAN.md),
[release qualification](RELEASE_READINESS.md), [workflow review](WORKFLOW_REVIEW.md)
and [attachments plan](ATTACHMENTS_PLAN.md). Actual test results retain their
dates and source identities in [verification](VERIFICATION.md).
