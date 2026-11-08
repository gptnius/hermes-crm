# Workflow review and improvement plan

Review baseline: public commit `80d6605774a2d53da008eb0f9810ee881437d282`.
The goal is a small set of understandable actions that carry a person from a
new relationship to a clear next step, without confusing saved plans, agent
claims, reviewed results and real-world delivery.

This review uses invented records, local service/API calls and isolated UI
fixtures. It does not access a mailbox, run a live research assignment, change
an existing installation or authorize production migration. Each implemented
change needs focused tests, independent review and a final regression run;
existing tests are not evidence that a new workflow passed.

## Typical workflows under review

1. **Intake:** create or import a contact, review duplicates, and explicitly
   associate the correct Company. A matching organization name is not an ID.
2. **Opportunity:** create a related deal, choose a stage/outcome, preserve custom
   values, and return to the contact or Company without losing context.
3. **Consultation:** create an Event with understandable date/time controls,
   review its timezone, add preparation notes and create a linked task.
4. **Follow-up:** open the exact task, make its next action clear, and distinguish
   the business-task status from any saved or scheduled agent assignment.
5. **Agent collaboration:** review the intended scope and time, deliberately
   schedule supported internal work, inspect real evidence, record review and
   separately decide whether the business task is complete.
6. **History:** distinguish planned Events, self-reported completed interactions,
   administrative edits and authorized provider observations.
7. **Reporting:** filter before limiting results, explain which relationships
   count, and return from a chart to the actual contributing records.
8. **Recovery:** retain a draft or explicitly discard it, retry an unknown write
   using the same operation identity, and reject stale profile/record context.

## Verified findings and selected fixes

WF-01 through WF-06, WF-08's clarity improvement and WF-09 are implemented in
this increment. The verification report lists completed tests and remaining
checks. WF-07 and the additional capabilities below remain design/backlog.

### WF-01: record navigation loses the parent

Opening a deal/task from a contact replaces the selected detail. Closing the
child returns to the list rather than the contact. Creating a related follow-up
also abandons the parent, making the next assignment action unnecessarily hard
to find. This was reproduced with the real React component and a synthetic
transport, not a live user session.

**Selected fix:** a bounded record trail with explicit Back, preserved list
filters/page context, and a fresh read of the exact target on return. Successful
child creation should open the confirmed child with its parent still reachable.
Cached rows must never become current write authority. Clear the trail when its
workspace/profile/connection authority changes.

### WF-02: Events require technical timestamp entry

Create/reschedule/completion forms require ISO strings and raw timezone names;
detail pages expose microsecond timestamps as primary content.

**Selected fix:** date/time controls, an explicit timezone, readable display and
a precise instant preview. Preserve the original exact instant if the controls
are unchanged. Reject nonexistent daylight-saving wall times and require an
explicit choice for repeated times. Do not silently reinterpret a changed zone
or round timestamps during unrelated edits.

The interactive editor supports new or changed wall times in 1900–2100.
Unchanged saved originals outside that range remain readable and retain their
exact instants during unrelated edits; this is not a server-wide date restriction.

### WF-03: technical detail overwhelms relationship pages

Company/Event pages expose long identifiers and internal relationship-basis
names beside many equal-weight actions.

**Selected fix:** clearer primary actions and readable context, with technical
metadata in accessible details. Keep source/provenance and capability limits
visible where they affect decisions. Exact identity remains visible in selectors
where duplicate names make it necessary. Use the existing Workbench design
system rather than introduce another visual language.

### WF-04: dirty forms and task actions need clearer control

Escape/navigation can discard edits without an explicit decision. Task details
have an Edit action but lack the direct Complete/Reopen action available in the
task list. Core creation actions are less prominent than some utilities.

**Selected fix:** Keep editing / Discard changes controls for dirty forms, clear
task status actions and better placement of primary creation. Task completion
does not mean an agent stopped, a report was accepted or a message was delivered.
Do not persist sensitive drafts across profiles or outside the current workspace.
These are in-app cancellation and navigation guards, not durable draft recovery.
Reloading, closing the host or changing profile can still discard an unsaved draft.

### WF-05: archived Companies accept new Event associations

An Event could be newly linked to an archived Company, although contact linking
and the documented policy require restoring it first.

**Selected fix:** reject a new archived association while preserving ordinary
edits/rescheduling of an Event already linked to that Company. Historical retry
receipts must remain historical; a later archive must not rewrite a prior result.

### WF-06: timestamp range errors become server errors

Valid ISO syntax near years 1 and 9999 can overflow during UTC conversion.
Event/task writes then returned a generic HTTP 500 instead of a validation error.

**Selected fix:** normalize this bounded conversion failure into ordinary
validation, without concealing unrelated errors. Verify API, tool and service
paths, unchanged records/receipts and accepted offset-aware timestamps.

### WF-07: agent results cannot be durably marked reviewed

The current assignment projection labels a reported result as awaiting human
review, but no separate review write exists. Reading it does not change that
state. Completing the business task instead changes source currentness; it is
not evidence of review.

**Design under review:** an exact-report review receipt, separate from the agent
claim, observed host status and business-task status. It must bind the report
identity/digest, assignment generation and reviewed source context, retain
history and idempotent retries, and never complete a task or schedule a run as
a side effect. Scheduled agents must not receive permission to approve their own
results. This document does not claim that the review feature is implemented.

The smallest proposed action is **Mark result reviewed**, an acknowledgement
rather than acceptance/rejection of quality. Historical results would need a clear
changed-source warning. The local session does not establish a verified named
reviewer; attribution and a correction/revocation policy must be settled before
presenting the ledger as an approval system. No agent self-review tool is planned.

### WF-08: Event-only tasks and contact follow-up metrics differ

An Event-only task can appear in the Contact/Company related-task views while
the contact still appears in a no-follow-up report. The existing follow-up
metrics count direct contact tasks and tasks related through a deal, not an
Event context link. These are different definitions, not duplicate records.

**Immediate clarity:** explain this boundary when direct contact/deal links are
cleared. Preserve the reviewed prefill when creating an Event task.
**Decision parked:** whether to add a separately named relationship-aware metric
or change a future coverage definition. Do not silently redefine saved reports
or assign a contact merely because an Event mentions them.

### WF-09: mixed-store native-work export scope

A synthetic store containing native assignments from multiple workspace/profile
scopes exposed a mismatch: ordinary native-work reads filtered the active scope,
but encrypted export included the other native rows. The reproduction used mixed
rows in one datastore; it does not show access to another profile's database or
selected PostgreSQL schema. A schema is a logical namespace, not a guarantee of
physical or security isolation.

**Selected fix:** apply the same workspace/profile filters to assignments,
operations and their event/report children during export. Preserve the active
scope's exact data and existing encryption behavior. Encryption does not replace
correct selection of the data being exported.

## Additional workflow gaps to plan

- Canonical Company selection during new-contact creation and Company-level
  Create Contact/Event actions need an atomic relationship-aware contract. A
  two-step create-then-link flow must not hide partial success or create duplicates
  after an uncertain response. Legacy company text is not a substitute.
- Existing core contact/deal selectors are bounded by the legacy snapshot.
  Reuse paged exact-ID selectors where possible rather than imply all records
  are present. Preserve the selected identity even when its page is not loaded.
- Agent assignment offers several overlapping preparation paths. A simpler
  scope-aware entry should lead through saved intent, reviewed scheduling and
  evidence, while retaining manual native-chat fallback for unsupported hosts.
  Simplification must not collapse the distinctions between these operations.
- Event changes do not reschedule/cancel linked tasks or existing assignments.
  Any future coordinated change needs explicit review of each affected action.

## Email, research and external access: honest capability boundaries

### Email

The implemented optional Gmail pilot is default off and metadata-only at runtime,
with synthetic verification only. It has no sending, drafting, automatic sync,
body/attachment ingestion or live-account verification. Gmail readonly is broader
than the metadata this code requests; requested scopes are not proof of the
token's actual powers. See [setup and limits](GMAIL_SETUP.md).

The bundled Hermes Google Workspace skill is a separate integration, not a CRM
connection. Its current setup requests broad services/scopes and does not provide
the documented service-selection option; see
[upstream issue 74128](https://github.com/NousResearch/hermes-agent/issues/74128).
Do not run that setup or borrow another plugin's credentials as a shortcut.

A future draft/send adapter needs account binding, minimal permissions, an exact
reviewed message snapshot, a durable outbox and provider-specific evidence.
Gmail compose permission also allows sending: a draft-only promise needs enforced
application behavior, not a scope-name assumption. Uncertain sending must be
reconciled, never blindly repeated. Keep drafted, submitted, observed-in-Sent,
received and unknown states distinct. See [the disabled contract](EMAIL_ACTIVITY.md).

### Lead research, social access and scraping

Interactive Hermes research depends on the selected host's actually available
tools and authorization. The scheduled CRM lane currently has only CRM
read/report tools. Browser/terminal access must not be silently added to existing
assignments. A profile is not an operating-system sandbox.

Public search/extraction, authenticated browser use and a platform API are
different capabilities. Do not infer permission to scrape a logged-in social
network, reuse cookies, bypass access controls or automate messaging. Follow each
site's access rules and the exact user's authorization. Store source URLs and
observation dates, label uncertainty, and treat retrieved content as untrusted
data rather than instructions.

The candidate demonstration is research → reviewed findings/draft → explicitly
created CRM records/follow-up. It is a plan until each live tool and evidence
path is verified. There is no generic social connector, reliable scraping engine,
research attachment store or verified research-to-send workflow in this release.
See [research and immediate-work constraints](AGENT_RESEARCH_AND_IMMEDIATE_WORK.md).

## Decisions reserved for discussion

1. Whether Event-only preparation tasks should satisfy contact follow-up coverage,
   and how a new metric should be named without changing old reports silently.
2. Result-review labels, local reviewer attribution and correction/revocation,
   including acknowledgement of a historical stale report separately from
   accepting it as current work. No automatic task completion.
3. A permitted research capability set and result/attachment provenance contract.
   No broad terminal/browser permission is implied by an internal task.
4. A selected mailbox and separately authorized least-privilege live test. No
   grants, setup changes, actual recipients or sends are part of this review.
5. Future immediate execution and cadences. A nearby future timestamp is not
   a verified Run now feature, and no scheduler can promise that work is never missed.

## Reference patterns and verification plan

Use familiar CRM patterns without a feature-parity claim:
[HubSpot record work](https://knowledge.hubspot.com/records/work-with-records),
[HubSpot tasks](https://knowledge.hubspot.com/tasks/create-tasks), and
[Salesforce work queue/cadences](https://trailhead.salesforce.com/content/learn/modules/high-velocity-sales/get-to-know-the-console-and-cadences).
The useful common ideas are visible next actions, clear relationship context,
manageable work queues and deliberate handoff, not copying every feature.

For each fix: reproduce the original problem; add failure and interrupted-flow
tests; verify SQLite and applicable disposable PostgreSQL contracts; run native
React/standalone suites and deterministic generators; independently inspect the
diff; inspect real isolated light/dark rendering at wide/narrow widths; record
what remains untested. Physical host interaction, provider behavior, accessibility
and production performance must not be inferred from synthetic fixtures.

The [README roadmap](../README.md#development-roadmap) remains the priority index.
The [verification report](VERIFICATION.md) separates implemented and tested fixes
from remaining verification limits. The result-review action and the additional
workflow capabilities above remain designs or backlog, not release claims.
