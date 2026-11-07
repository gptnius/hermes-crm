# Native assigned work

This prototype adds future one-shot internal assignments. Intent can be saved through the native CRM form or an agent tool; scheduling requires a real active Hermes tool context. It is separate from the default-disabled Desktop execution bridge and from the simpler existing follow-up reminder tool. It does not send email, make calls, modify provider settings or complete business tasks automatically.

## User-facing contract

1. Save an assignment for an existing open CRM task, with a human owner, immutable instructions, success criteria and an explicit future time including timezone.
2. Explicitly request scheduling. The tool persists its scheduling claim, creates the native job paused, stores its exact ID, then resumes it through the host's existing permissions.
3. Hermes may run the scheduled internal work and report a result. A report is displayed as **result reported, awaiting human review**.
4. Review the result and decide whether the business task is complete. Report creation never marks it done.

The first slice supports future one-shots only. It has no run-now shortcut, recurring cadence advancement, automatic retry or automatic adoption of orphan jobs. The gateway and a working existing model configuration are still required. Saving or enabling a job is not proof it will execute.

## Tools and permissions

- `crm_work_create`: save intent only, with optional atomic `expected_task_version` binding. New UI-prepared requests include it; older callers can omit it. Exact idempotency replay preserves the original approved snapshot rather than adopting a newer task version.
- `crm_work_get` and `crm_work_list`: read current-workspace assignment/history.
- `crm_work_schedule`: explicit paused-create, bind and resume.
- `crm_work_reconcile`: observe host job summaries without recreating, resuming or adopting jobs.
- `crm_work_cancel`: invalidate local intent, then request a pause of the exact bound future job.
- `crm_work_report`: accept a bounded report only from the assigned native run.

The existing 15 tools remain. Assignment reads use `crm_work_read`; create/schedule/reconcile/cancel use `crm_work_schedule`; report writes use `crm_work_report`. No write is hidden inside `crm_read`.

Scheduled jobs request exactly `crm_read`, `crm_work_read`, `crm_work_report` and `no_mcp`. They do not receive scheduling, ordinary CRM writes, delegation, browser, shell, messaging or external MCP tools through those sets. Current host resolver behavior is tested; changing trusted tool implementations remains outside a static toolset guarantee.

The report handler obtains `ctx.current_cron_execution()` itself. Model arguments cannot supply job, execution, profile, source or scheduled-instant identity. The handler verifies the current profile/workspace, exact bound job, built-in source, generation and approved instant. Manual off-schedule execution, ordinary interactive calls, delegated children, cancelled or superseded work and identity mismatches are rejected. Hosted callback proxy records are supported.

## Evidence and uncertainty

A report proves that this identified native run called the reporting tool and reported the stored content. It does not prove that the host later finished successfully, that a final response matched the report, that delivery occurred, or that the analysis is correct. The public context does not attest an unchanged job prompt or expose a complete terminal execution receipt.

Assignment state, observed job state, authenticated result reports and business-task completion remain separate. A completed host summary without a report remains **no authenticated report received**. A changed source task makes a prior report stale for current-task review rather than silently treating it as current work.

Scheduling uncertainty is persisted before host mutations. The paused-create response must provide a verified exact binding before resume. If create's response is lost, the public list is insufficient to prove its complete prompt and schedule because it abbreviates both. Candidate orphan IDs may be shown for review, but they are never automatically adopted, resumed or replaced. A known bound job may be observed after an uncertain resume.

Task version, cancellation and approved time are checked again before resume. If time elapsed while the job was paused, the tool leaves it paused with a visible blocker. Explicit cancellation pauses a future schedule; it does not claim to interrupt an agent already running. Reports are deduplicated by execution/operation identity; conflicting duplicates are not silently overwritten.

## Storage and UI boundary

Three new profile-scoped tables store native assignments, events and reports. Existing CRM and experimental execution tables are unchanged. Incompatible table shapes or constraints fail closed rather than silently migrating. PostgreSQL remains explicit and isolated by the existing profile schema.

The native API exposes read-only `/work` and `/work/{assignment_id}` routes, plus paged `/reports/work` history and `/reports/coverage` evidence. Explicit `POST /work` saves local intent only, requires a positive integer `expected_task_version`, and uses the same atomic create/idempotency implementation as the agent tool. All these routes require the captured workspace token and use the same per-call profile factory as tools. Host routing parameters do not independently select a database. There is no REST scheduling endpoint and no borrowed tool context.

The native task record displays assignment history, observed job state, source-task freshness and authenticated reports awaiting review. An unavailable history request is not shown as an empty history. The UI can save intent and replay the exact local save after an uncertain response; it does not schedule, dispatch, retry execution or approve work. It can prepare a task-specific request with Preview/Copy beside the genuine native chat; the user pastes, reviews and uses native Send. The coverage queue uses complete local evidence before paging, not bounded task/history caches. See [assignment UI](ASSIGNMENT_UI.md) for version binding, recovery actions and exact limits.

## Verification status

Synthetic domain/adapter tests and actual PostgreSQL contracts cover claim races, lost responses, paused orphans, source-task changes, cancellation, rollback, duplicate/conflicting reports, identity mismatches, schema compatibility and absence of automatic business-task completion.

Actual pinned-host tests exercise the real plugin registry, paused create/bind/resume, resolver inventory, fire claims, running-ledger CAS and trusted context propagation in both in-process and hosted-plugin modes. They also verify ordinary/delegated/forged reports are rejected. Actual Desktop backend tests verify tool-created intent is readable through authenticated history routes, including token/profile isolation.

Separate guarded tests now pass with SQLite in both in-process and hosted-plugin modes on the pinned host and Linux x86_64 CPython 3.14.9. They exercise a real due-time scheduler run, canonical admission and stored result, AIAgent, default deferred discovery of the 11 permitted tools, actual CRM reads, an authenticated report and local output. Only the streamed model endpoint is synthetic. Setup calls the registered scheduling handlers with a real active-agent/session context; a model-issued scheduling request and interactive approval presentation are not tested.

Each mode verifies no pre-due model request, no duplicate execution/report after extra ticks, and a second assignment cancelled before due that never executes. The business task stays open and the report awaits human review. Exact runtime and dependency/probe hashes, fail-closed guard checks and portable instructions are in [the reproduction bundle](native-work-test/REPRODUCE.md).

This establishes the tested internal execution/data path, not real-model reasoning, prompt-injection resistance, a universal capability ceiling, visible Desktop notifications, owner-process restart recovery or external delivery. No MCP servers were configured in these runs; configured-MCP exclusion has separate resolver evidence. No production profile or provider configuration was used.
