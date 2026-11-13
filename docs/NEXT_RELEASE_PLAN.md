# Reports and trustworthy agent work: phased development plan

This document retains the reasoning and acceptance gates for several implemented
phases. It is not a list of entirely unavailable features. Typed reports, custom
fields/stages, future internal assignments through CRM confirmation, Company/Event
records and associated tasks are implemented in bounded increments. A separate
[scheduled public research mode](SCHEDULED_RESEARCH_PLAN.md) now supports reviewed
task-bound evidence and note proposals through configured host research tools.
Immediate execution, broader research capabilities, result attachments and
provider-backed sending remain separate work. Use the [README](../README.md), [workflow review](WORKFLOW_REVIEW.md)
and [verification report](VERIFICATION.md) for current behavior and test scope.

## Scope and product promise

The original entry scope provided preset reports feeding the main dashboard, filters in existing record views and a staged path to genuine agent-assigned work. A later explicit development request expanded reporting to typed saved definitions and customizable main-dashboard cards; see [the flexible-report plan](FLEXIBLE_REPORTS_PLAN.md) and [current behavior](FLEXIBLE_REPORTS.md). There is still no separate chart tab. Calls, texts and other external outreach are excluded.

The goal is a visible next action for every active lead, with overdue, blocked, failed and uncertain work surfaced. “Never missed” is not a guarantee a CRM can make through outages, expired authorization or unknown execution outcomes. A saved task is not proof an agent will execute it.

## Familiar CRM workflows, without a parity claim

HubSpot's task and saved-view workflows and Salesforce's sales work queue are references for everyday use:
- Search and filter records without losing the current workspace or view context.
- Move from a dashboard summary to the exact records that produced it.
- Separate the human owner accountable for a lead from the agent assigned to execute a task.
- Make upcoming, overdue, failed and uncertain work visible, together with explicit no-next-action exceptions.
- Keep stage history before claiming historical funnel conversion; the current dashboard is a current-state snapshot.

The current release does not provide full HubSpot or Salesforce feature parity. Typed saved reports, dashboard cards, optional typed custom fields and a configurable single deal pipeline are now included in bounded native increments. Multiple pipelines, required/unique/calculated fields, historical conversion and advanced cadence authoring remain future work. The [current roadmap](ROADMAP.md) is the current priority index. First customization, protection and contact-transfer increments are implemented; external CRM linking remains deferred.

References:
- https://knowledge.hubspot.com/tasks/create-tasks
- https://knowledge.hubspot.com/records/create-and-manage-saved-views
- https://trailhead.salesforce.com/content/learn/modules/high-velocity-sales/get-to-know-the-console-and-cadences

## Phase 1: terminology, filters and preset reports

### One meaning for Stage

Use **Stage** consistently for the six deal stages: Lead, Qualified, Proposal, Negotiation, Won and Lost. Contact reports show linked deal stages explicitly. A contact with several deals may have several stages, so no arbitrary primary stage is inferred.

The existing lead/customer/partner category becomes **Contact type** in the UI and schema descriptions. Its legacy `lifecycle` storage/API field is retained for compatibility. No records are converted, and customer is not silently mapped to won. The word Lifecycle is removed from ordinary UI labels.

### Main dashboard

- Replace the stage bars with an accessible pie/donut chart showing deal value by stage. Label the measure and whether closed stages are included.
- Each stage summary and hover/focus detail shows value, share, deal count and unique contact count.
- Clicking a segment or summary opens the existing Contacts view as a preset report of unique contacts linked to deals in that stage. The report title and active filter make that relationship explicit.
- Include preset attention reports for lead contacts with no open follow-up and lead contacts with overdue follow-ups. These describe stored task records, not guaranteed execution coverage.
- Retain useful totals, upcoming work and recent activity. Charts remain on the main dashboard.

### Filters and report contracts

Contacts: text search, linked deal Stage (including unstaged), Contact type, company, email presence, and open-follow-up state. Deal/pipeline filters: text search, Stage, company and value range. Tasks: text, status, priority and overdue/upcoming open work.

Apply filters on the server before limiting records. Use one shared SQL implementation for UI and agent tools, with bound parameters, strict field/value validation and literal wildcard escaping. Contact reports return unique contacts, a true filtered total, a bounded page and stable ordering. Multiple matching deals never duplicate a contact.

Add a dedicated contact-report endpoint rather than breaking existing list response shapes. It returns items, total, limit and offset. Each item can include distinct linked deal stages and open/overdue follow-up counts. Existing list tools gain applicable filter arguments while preserving backward compatibility.

Open follow-ups include directly linked tasks and tasks linked through a contact's deal. Define missing as no open task; overdue as an open due date before the current instant. These are not healthy-agent-assignment indicators. Date handling remains timezone-aware.

No custom report builder, new navigation tab, production data migration or provider change is needed for this phase.

### Acceptance

- No Lifecycle label remains in normal native or standalone UI.
- Chart values and unique contact counts agree with server report totals, including contacts with several deals and zero-value stages.
- Hover details also work with keyboard focus; summaries remain usable without color or pointer interaction.
- Empty, zero-value and filtered-empty states are clear.
- Filters combine correctly, escape literal search characters, reset pagination and work beyond the former 500-row contact cap.
- Profile switches, same-tick reconnects, stale responses, cancelled forms and rapid filter changes retain existing safety guarantees.
- SQLite, real PostgreSQL, native API, agent-filter and JavaScript/React regression tests pass, followed by independent review. No push before review.

## Phase 2: durable internal agent assignments

### Reuse Hermes execution ownership

Use Hermes' persisted jobs, canonical admissions and execution history rather than constructing a separate AIAgent runner. Keep business-task completion separate from agent execution completion.

An assignment needs an immutable workspace/installation/profile identity, a separate human owner, action intent and success criteria, run time separate from due time, authorization scope and a generation/version. Begin with the current workspace's existing profile only. Cross-profile work must not silently read another database or copy credentials.

Each occurrence needs a stable operation identity, requested time, dispatch state, Hermes job/execution/session/admission references where available, timestamps, redacted result/error, cancellation state and retry relationship. Suggested execution states are Pending, Scheduling, Admitted, Queued, Running, Succeeded, Failed, Cancelled, Missed and Unknown. None is inferred from merely clicking a button.

Persist assignment and dispatch intent atomically. Durable dispatch state is separate from a future outbox worker: no browser pane can guarantee dispatch after it closes. Hermes remains responsible for accepted execution claims. Normal session creation/submission supports stable request IDs; a lost response must be reconciled or retried with the same immutable identity, never replaced by a new operation. Scheduled-job creation does not provide the same create-idempotency parameter. The implemented paused-create path therefore binds only a verified create response; after a lost response, an operation marker identifies possible orphan candidates but cannot prove their complete contents. Multiple matches or uncertain execution become visible blockers, not automatic adoption or replacement. Do not promise exactly-once execution.

Validate the task generation and required result before marking the business task complete. An agent returning successfully, producing the required artifact and delivering an action are different facts. This build permits internal CRM results only.

### Supported active-agent scheduling slice

Implement and test a bounded alternative to direct Desktop scheduling: a real active plugin tool saves immutable internal-work intent, creates a native future one-shot job paused, persists its exact job binding, then resumes it. Creation and scheduling are separate explicit actions. There are no jobs at registration and no hidden background dispatcher.

Use separate `crm_work_read`, `crm_work_schedule` and `crm_work_report` toolsets. The scheduled agent receives CRM reads, assignment reads and the narrow report writer, plus `no_mcp`; it does not receive scheduling, general record mutation, delegation, browser, shell or messaging tools. The report handler obtains trusted identity from `ctx.current_cron_execution()` itself, rather than accepting job or execution identity from model arguments.

The result means **identified native run reported a result, awaiting review**. It is not proof of terminal host success, final delivery, correctness or business-task completion. UI history must keep these facts separate. A future one-shot is the first slice; run-now behavior and cadence advancement remain out of scope until verified.

Persist uncertainty before every host mutation. Lost create responses cannot be safely auto-adopted from job-list summaries, which truncate prompts and schedules; keep the assignment unknown and do not create a replacement. A known bound job can be inspected after an uncertain resume. Revalidate task version, cancellation and approved time before resume; if the time elapsed while paused, surface a missed/blocked action instead of silently executing late. Explicit cancellation pauses the exact future job but does not claim to stop a running agent.

Test deterministic synthetic success/failure paths, concurrent requests, rollback, stale/cancelled tasks, paused orphan recovery limits, forged execution identity, profile/generation/instant mismatches, duplicate/conflicting reports, and actual host/plugin-isolation behavior before enabling the feature. This was the original verification gate. The implemented future-assignment lane has since passed bounded scheduler/agent/report tests described in [verification](VERIFICATION.md); neither a design nor an unrelated reminder test alone establishes that result.

### Public-interface gate

The pinned SDK exposes route-bound gateway RPC and visible composer handoff. However, its `cron.manage` RPC cannot forward the required restricted toolset or provide the full trigger/history lifecycle. The separate Desktop/dashboard cron REST API accepts paused creation and explicit toolsets, but is not wired to the CRM assignment ledger or interactive tool-policy workflow and is not used as a direct scheduling shortcut. Direct `cron.submit` is an admission component, not a replacement for the scheduler's durable fire claim and bookkeeping.

The real interactive plugin tool context can dispatch `cronjob_manage`. The original direct-RPC UI route remains unsuitable; the implemented alternative is [CRM-confirmed scheduling](CRM_CONFIRMED_OPERATIONS.md) through an authenticated native user command, with exact identity and scope checks. Manual task-request copy/paste remains a fallback; composer acceptance is not durable admission. Do not borrow a registration context inside REST, read private job files, create a hidden runner or bypass canonical scheduling.

A conditional immediate path exists through captured-profile public gateway RPC: `session.create` with a stable request ID, `prompt.submit` with a stable submission ID, `prompt.receipt` for result evidence and `prompt.cancel` for cancellation. Persist intent and IDs before calling the host. Reconnect through the supported session-resume protocol. Do not use unattended mode or override the profile’s provider/model.

An explicit requested toolset is not a strict capability ceiling at this revision: newly discovered plugin or context tools can be added before the host freezes the session selection. Before any task prompt, inspect the returned effective toolsets and complete tool inventory. Block unexpected or unknown scope, including a deferred-discovery wrapper without a verifiable underlying catalog. Only a verified restricted current-profile session can proceed. A general guarantee needs an upstream strict capability ceiling enforced across direct/deferred/delegated calls. Transport acceptance, a client-observed receipt and server-verified completion must remain distinct. A reviewed experimental bridge and durable storage foundation exist, but remain unwired and disabled. They do not provide a working Run now button or a live-model verification. See EXPERIMENTAL_EXECUTION.md.

### Recovery and coverage

- Retry only positively known safe failures under a bounded policy, with next retry time visible. Unknown execution or delivery requires reconciliation, not blind repetition.
- On restart, recover dispatch intent and observe known host jobs/admissions/results. Lease expiry is not proof no execution occurred.
- Cancel future scheduling and running execution separately, and distinguish requested cancellation from confirmed cancellation.
- Mark deleted schedules, offline/paused agents and failed or unknown runs as blocked or uncovered. Do not recreate jobs silently.
- Every active lead should eventually have an executable next action or an explicit hold/exclusion with a reason and review time. Bare open tasks do not satisfy this stronger execution contract.
- Future nurture/consultation cadence steps should be transactionally generated and pause on relevant replies, bookings or approved holds. Cadence automation is not implemented by enabling recursive agent scheduling.

### Smallest real execution slice

The current first slice is one synthetic lead, one internal task and the current profile, assigned for a future one-shot through the supported active-agent scheduler. Verify capability scope, actual due-time admission, CRM reads, authenticated internal result reporting and reconciliation. Leave business completion awaiting explicit review. Immediate Desktop execution remains a separate disabled experiment; storing a requested time alone is not scheduling. First use deterministic loopback responses to test transport; then use an already authorized, working model provider for a separately approved real-model check. No authentication, billing or model availability is assumed from a subscription/credit balance.

Required failure tests include duplicate clicks, concurrent dispatch, lost create/admission responses, restart before and after admission/completion, cancellation, externally deleted jobs, offline/paused profiles and foreign-profile rejection. Effective tool restrictions must be tested with normal discovery, not only the earlier discovery-off fixture.

## Next UI increment: records and in-CRM agent conversation

Use a reusable contact/opportunity shell inspired by familiar CRM structure: identity and key properties, a clear action row, a central activity timeline with upcoming work, and related records. Keep the distinctions between Contact type, linked deal Stage, human ownership and agent execution explicit. A responsive quick-create drawer needs persistent labels, sensible field grouping and pinned Save/Cancel, without hiding validation below the fold. Preserve keyboard access, unsaved-form cancellation, exact existing timestamps and stale-workspace rejection.

References are workflow/layout guidance rather than assets to copy:
- https://knowledge.hubspot.com/records/work-with-records
- https://knowledge.hubspot.com/records/create-records-on-the-updated-index-page

A bounded first handoff is implemented: **Chat with Hermes** opens a right-docked CRM view beside the already loaded, verified primary native conversation. It preserves the current CRM view, blocks relocation while a form is open and checks session/source/profile ownership. Selected-record reference preview/copy includes only connection, profile, kind, ID and version. The user pastes, reviews and sends through the native composer. There are no composer reads/writes, automatic submissions, new sessions or fabricated transcript. Source-contract and React checks are separate from the remaining live native-window/model tests; see NATIVE_CHAT.md.

The implemented task-specific Preview/Copy request builder uses atomic `expected_task_version` intent binding and server-paged coverage/history reports. Its manual path uses the same genuine native conversation and explicit user Send. The separate CRM-confirmed command path can schedule a reviewed future assignment. A copied request alone is not dispatched, evidence totals are not unique lead counts, and stored observations do not establish live execution coverage. See [the assignment workflow](ASSIGNMENT_UI.md) for current behavior and [verification](VERIFICATION.md) for tested scope.

The tested SDK does not export the full native ChatPane, and its composer insertion helper does not provide the race-free draft/target contract needed for automatic context insertion in this build. A future custom transcript would own streaming/replay, queues, cancellation and approval/question handling. Do not present a text box that only submits prompts as a complete agent chat. Future attachment or broader session support must preserve the user's drafts, exact session ownership and host permissions.

Record history is the administrative audit. Relationship Activities separately contains completed local Events and self-reported contact logs. This core edition ships no mailbox integration. Legacy provider evidence remains separate from self-reported contact logs. Future communication features still need explicit provider evidence for the specific claimed outcome. Drafts, attempted actions, agent claims and confirmed sent messages must be separate states. Received-message capture also needs an authorized source and sync/recovery policy. Do not assume an existing mail connection or show inert Send controls. No email sending, new credentials or account connection is part of the present implementation authorization.

The proposed demo can progress from lead research and contact creation to reviewing a personalized draft and the corresponding CRM activity. Actual sending requires separately authorized recipients/content and a working provider integration, not a simulated sent event.

## Delivery boundaries

Work stays in the isolated source repository. The existing hands-on Desktop test instance is not changed while these features are developed; its visible state remains the previously tested revision until a separately coordinated install. No VPS deployment, production scheduling, provider setup, credentials, calls or texts are part of this work.

Publish only independently reviewed commits. Update verification with what actually passed, the exact source revision, and any remaining host/API or real-model gaps.
