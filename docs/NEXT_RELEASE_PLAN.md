# Next release: useful reports and trustworthy agent work

## Scope and product promise

The entry will provide a preset basket of reports feeding the main dashboard, filters in the existing contact/pipeline/task views, and a staged path to genuine agent-assigned work. There is no separate chart tab or custom report/dashboard builder in this build. Calls, texts and other external outreach are excluded.

The goal is a visible next action for every active lead, with overdue, blocked, failed and uncertain work surfaced. “Never missed” is not a guarantee a CRM can make through outages, expired authorization or unknown execution outcomes. A saved task is not proof an agent will execute it.

## Familiar CRM workflows, without a parity claim

HubSpot's task and saved-view workflows and Salesforce's sales work queue are references for everyday use:
- Search and filter records without losing the current workspace or view context.
- Move from a dashboard summary to the exact records that produced it.
- Separate the human owner accountable for a lead from the agent assigned to execute a task.
- Make upcoming, overdue, failed and uncertain work visible, together with explicit no-next-action exceptions.
- Keep stage history before claiming historical funnel conversion; the current dashboard is a current-state snapshot.

This prototype does not claim full HubSpot or Salesforce feature parity. Saved custom views, a report/dashboard builder, configurable funnels and advanced cadence authoring are future work.

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

Persist assignment and dispatch intent atomically. Durable dispatch state is separate from a future outbox worker: no browser pane can guarantee dispatch after it closes. Hermes remains responsible for accepted execution claims. Normal session creation/submission supports stable request IDs; a lost response must be reconciled or retried with the same immutable identity, never replaced by a new operation. Scheduled-job creation does not provide the same create-idempotency parameter, so it requires an exact operation-marker reconciliation contract. Multiple matches or uncertain execution become visible blockers. Do not promise exactly-once execution.

Validate the task generation and required result before marking the business task complete. An agent returning successfully, producing the required artifact and delivering an action are different facts. This build permits internal CRM results only.

### Public-interface gate

The pinned SDK exposes route-bound gateway RPC and visible composer handoff. However, its `cron.manage` RPC cannot forward the required restricted toolset or provide the full trigger/history lifecycle. Direct `cron.submit` is an admission component, not a replacement for the scheduler's durable fire claim and bookkeeping.

The real interactive plugin tool context can dispatch `cronjob_manage`. Scheduled assignments from the UI remain blocked until a complete supported, restricted scheduler path is verified. A composer handoff, if offered, must be labeled honestly as **Ask Hermes to run**; composer acceptance is not durable admission. Do not borrow a registration context inside REST, read private job files, create a hidden runner or bypass canonical scheduling.

A conditional immediate path exists through captured-profile public gateway RPC: `session.create` with a stable request ID, `prompt.submit` with a stable submission ID, `prompt.receipt` for result evidence and `prompt.cancel` for cancellation. Persist intent and IDs before calling the host. Reconnect through the supported session-resume protocol. Do not use unattended mode or override the profile’s provider/model.

An explicit requested toolset is not a strict capability ceiling at this revision: newly discovered plugin or context tools can be added before the host freezes the session selection. Before any task prompt, inspect the returned effective toolsets and complete tool inventory. Block unexpected or unknown scope, including a deferred-discovery wrapper without a verifiable underlying catalog. Only a verified restricted current-profile session can proceed. A general guarantee needs an upstream strict capability ceiling enforced across direct/deferred/delegated calls. Transport acceptance, a client-observed receipt and server-verified completion must remain distinct. This bridge is not implemented or live-model verified by the report/filter release.

### Recovery and coverage

- Retry only positively known safe failures under a bounded policy, with next retry time visible. Unknown execution or delivery requires reconciliation, not blind repetition.
- On restart, recover dispatch intent and observe known host jobs/admissions/results. Lease expiry is not proof no execution occurred.
- Cancel future scheduling and running execution separately, and distinguish requested cancellation from confirmed cancellation.
- Mark deleted schedules, offline/paused agents and failed or unknown runs as blocked or uncovered. Do not recreate jobs silently.
- Every active lead should eventually have an executable next action or an explicit hold/exclusion with a reason and review time. Bare open tasks do not satisfy this stronger execution contract.
- Future nurture/consultation cadence steps should be transactionally generated and pause on relevant replies, bookings or approved holds. Cadence automation is not implemented by enabling recursive agent scheduling.

### Smallest real execution slice

First: one synthetic lead, one internal task and the current profile, assigned for immediate execution. Verify capability scope, produce a genuine agent session through supported admission, read CRM data, save a meaningful internal result and reconcile evidence. Leave business completion awaiting explicit review. Specified-time assignments follow only after the scheduler adapter gate is resolved; storing a requested time alone is not scheduling. First use deterministic loopback responses to test transport; then use an already authorized, working model provider for a separately approved real-model check. No authentication, billing or model availability is assumed from a subscription/credit balance.

Required failure tests include duplicate clicks, concurrent dispatch, lost create/admission responses, restart before and after admission/completion, cancellation, externally deleted jobs, offline/paused profiles and foreign-profile rejection. Effective tool restrictions must be tested with normal discovery, not only the earlier discovery-off fixture.

## Delivery boundaries

Work stays in the isolated source repository. The existing hands-on Desktop test instance is not changed while these features are developed; its visible state remains the previously tested revision until a separately coordinated install. No VPS deployment, production scheduling, provider setup, credentials, calls or texts are part of this work.

Publish only independently reviewed commits. Update verification with what actually passed, the exact source revision, and any remaining host/API or real-model gaps.
