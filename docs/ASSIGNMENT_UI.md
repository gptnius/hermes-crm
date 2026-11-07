# Prepare agent work and inspect follow-up coverage

The native CRM can prepare a task-specific request beside the existing Hermes conversation and show paged, server-derived coverage evidence. Preparation is not dispatch. The user reviews the text, pastes it into the matching native chat and uses the host's normal Send action. There is no automatic prompt submission, direct cron button, email adapter or enabled Run now bridge.

## Prepare a request

1. Open an existing primary Hermes conversation in the same connection/profile, then open CRM beside it with **Chat with Hermes**. Save or cancel any open record editor first.
2. Open a saved follow-up and choose **Prepare agent request**. The fixed executor is Hermes in this connection/profile. **Human owner** is a separate accountability label, not a person selector or permission grant.
3. Choose **Ask for help now** for an interactive request, or **Prepare future internal analysis** to prepare a saved assignment. Future analysis asks for an owner, instructions, success criteria and an explicit offset-aware run time. Its run time is separate from the business due date. New requests require a five-minute buffer; this is not a disguised immediate scheduler.
4. Choose **Preview request**. Review its exact instructions, task ID/version, profile, conversation, time and request key. The panel reads the current task again; a changed or completed source blocks new work.
5. Choose **Copy request**, paste into the matching native composer, review and use **Send**. Copy performs another scoped read and version check. If clipboard access is unavailable, the preview remains selectable. A manual copy cannot perform another automatic freshness check; the preview is only an observation at its displayed preparation point, not an authorization token.

The panel never reads or edits the native draft, invokes a model, submits a prompt, creates a session or changes provider/tool settings. A missing or changed native conversation, a secondary tile, profile/connection changes and stale callbacks block the prepared action. If the conversation changes, discard the preparation and start again for the intended conversation; it must not silently move an existing draft to another chat.

From the ordinary CRM view, a request action first opens the verified companion; choose that action again beside chat to start preparation. This explicit two-step entry avoids moving mutable form fields between mounts.

Preparation lives only in the mounted CRM view. Closing it, switching scope or discarding it does not cancel work already saved elsewhere. A selectable preview might have been copied manually, so editing a previously exposed request retains a warning and references the earlier keys. It never assumes an earlier request was unsent or safe to replace.

## Saving and scheduling are separate

A future preparation asks the real native agent to call `crm_work_create` and save intent only. It must return the assignment ID and actual saved state. Refresh saved history to see that evidence; copying a request does not create a history row or scheduling badge.

For an exact saved assignment, the UI can prepare **Ask to schedule saved assignment**, **Ask to check assignment** or **Ask to cancel future assignment**. Each preview/copy re-reads that assignment, including its version, generation, frozen fields and bound job ID.

- Scheduling requires a current open source task, an unscheduled saved intent and a future run time. It uses the existing active-tool paused-create/bind/resume flow after the user sends the reviewed request.
- Checking asks the native agent to reconcile the exact assignment. It does not create a replacement, resume a paused job or infer completion.
- Cancellation asks for local invalidation and pausing the exact future job. It remains available when the source task is done or changed, and when local cancellation exists but host pause is uncertain. It does not claim to stop an already running agent.

Scheduled work remains internal CRM analysis with the existing restricted read/report tools. It cannot research the web, create contacts, send email or advance an outreach cadence. Interactive native chat is a different capability lane; it uses whatever ordinary tools and permissions the existing host actually provides. The immediate-help request permits only CRM changes specifically requested in its reviewed instructions; otherwise it asks for analysis or a draft. Scheduling, outreach, settings changes and automatic business-task completion remain excluded from that template. No available research or provider integration is assumed.

### Atomic source-version binding

New prepared create requests include `expected_task_version`. The backend validates it as a positive integer, compares it inside the creation transaction and guards the frozen task snapshot with the existing conditional task-version update. A stale or done task cannot be silently accepted as the reviewed source.

The field is optional for older tool callers, whose omitted-field requests retain their previous behavior. It is included in immutable intent only when supplied. Replaying the same key and exact expected version recovers the same assignment even if the task subsequently changes; changing the expected version, or switching between omission and presence with the same key, conflicts. Recovery is not new authorization to execute a stale assignment. Scheduling still checks the frozen task version and approved time before resume.

## Follow-up coverage queue

The Tasks view includes a separately filtered coverage queue and paged assignment history. Both use authenticated read-only reports with the captured workspace token. Their counts come from the complete relevant database snapshot, not the first 500 tasks or 100 assignments.

Each coverage row is one **evidence item**: an exact assignment, an open task without current assignment intent, or a contact without an open linked follow-up. Counts are not unique lead/contact counts, execution guarantees or a policy that every contact requires autonomous work. A contact/task may legitimately have several assignment rows. Direct and deal-linked task associations are deduplicated.

Filters expose:

- **No open next action:** a contact has no linked open task, including contacts without deals.
- **Overdue next action:** the business due date of an open task has passed.
- **Agent work not scheduled:** current applicable schedule/report evidence is absent. An ordinary human-owned task is not automatically an agent failure.
- **Needs scheduling review:** unknown, paused, stale-source or unconfirmed-cancellation evidence needs attention. Completed business tasks can still have unresolved future jobs and remain visible.
- **Run time passed:** the approved instant passed without an authenticated report. This is not proof that execution failed or never happened.
- **Reported blocked or failed**, and **Awaiting review:** describe saved native-run reports, not verified business completion or message delivery.

Several risk flags can apply to one row. Safely cancelled old work is not substituted for a newer assignment, and a green newer row does not erase a different unresolved job. Source freshness, business-task completion, saved assignment state, observed host state and reported outcome remain separate.

**Refresh coverage evidence** and history refresh read only the local CRM database. They do not query the scheduler or verify that a gateway/model is currently available. Host observations retain their source and time. A failed refresh is not empty history and must not masquerade as new evidence.

## Storage, performance and verification limits

No new table or schema migration is required for the UI reports or optional expected-version field. Assignment report routes do not initialize missing assignment tables. Multi-query reads use explicit SQLite snapshots or PostgreSQL repeatable-read, read-only transactions, including table availability checks. Unknown/incompatible state or corrupt stored intent fails visibly rather than producing a healthy coverage claim.

This prototype classifies complete local task/assignment history before filtering and pagination. Work is proportional to that history, so server paging prevents display truncation but is not a large-dataset query optimization. A later page request is a new snapshot; concurrent changes can move items between offset pages. No background dispatcher, retry daemon, cadence engine, durable human-review toggle or never-missed guarantee is implied.

See [verification](VERIFICATION.md) for executed checks. Native window layout, keyboard/focus, actual clipboard/native Send, real-model behavior and operational restart/recovery must be distinguished from synthetic component and database tests. This feature adds no email account access, external sending or production deployment.
