# Save, schedule and review agent assignments

The native CRM can save future internal-work assignments, explicitly schedule/check/cancel them beside the existing Hermes conversation, and show paged coverage evidence. Saving is not scheduling; reviewing is not dispatch. CRM confirmation uses an authenticated native user command, separate from the model-tool approval path. Manual Preview/Copy into native chat remains available for conversational requests. There is no automatic prompt submission, email adapter or enabled Run now bridge.

## Save a future assignment in CRM

1. Open an existing open follow-up and choose **Save future assignment**. No open native conversation is required.
2. Enter the human owner, reviewed instructions, success criteria and an explicit offset-aware future run time. The owner is an accountability label, not a permission grant; run time is separate from the business due date. The form requires a five-minute buffer for new work.
3. Choose **Review assignment**, check the exact task/version, fields and request key, then choose **Save assignment**. Preview alone writes nothing. The authenticated local REST handler atomically binds the source task version and saves the same native-work intent used by agent tools. It never receives a tool context or calls a scheduler or model.
4. The exact returned assignment is pinned independently of the history page, and history refreshes. **Saved, not scheduled** means exactly that: there is no native job yet. Use **Review CRM scheduling** for the separate confirmation below, or **Prepare scheduling for saved assignment** for a manual native-chat request.

If saving is not confirmed, the form retains the immutable request and key and offers **Retry same save**. Replaying that exact request can recover its original assignment even if the task subsequently changes or the run time passes. It does not authorize execution. A rejected, malformed or lost response is not treated as proof of no save; the form cannot silently generate a replacement. Missing history is not proof of no save either.

Recovery fields remain available across panel closure, sibling CRM views and profile changes within the same plugin lifetime. **An app/plugin reload loses this in-memory recovery panel.** Keep the selectable exact request before reloading and reconcile that key through the native agent if necessary. Confirmed assignments themselves are stored durably in the CRM. Closing a form does not cancel an in-flight save.

After a confirmed save, **Save another future assignment** explicitly starts additional intent with a new key. It does not replace or cancel the earlier assignment; review existing history first. The backend profile from scoped CRM metadata is distinct from a Desktop display-profile alias, and both are kept bound to the captured workspace.

## Schedule from CRM with explicit confirmation

1. Open the intended existing primary Hermes conversation in this connection/profile. Use **Chat with Hermes** to place CRM beside it. An action chosen from the ordinary CRM page opens the companion first; choose it again there. No hidden session is created.
2. On an exact saved assignment, choose **Review CRM scheduling**. The backend prepares a durable, short-lived operation from the current stored assignment and task. Preparation does not create a native job.
3. Review the complete server-derived instructions, success criteria, owner, time, task/assignment versions, profile, intended conversation and existing job ID. The profile's configured model provider will process CRM data when a scheduled run executes; local output is not a promise of local-only model processing.
4. Choose **Confirm schedule in CRM**. This sends only that operation's UUID to the workspace-specific registered native command, after checking the exact session/profile/runtime and current command catalog. The backend claims it once, creates a paused job, durably binds its exact ID, then resumes it. A successful scheduling result does not mean the agent has run or completed the business task.
5. Use **Check native status** for an explicit host observation. **Review CRM cancellation**, then **Confirm cancellation in CRM**, invalidates the saved assignment and requests a pause of its exact future schedule. It cannot stop an already running agent. **Read local operation status** and **Refresh local operation history** read CRM evidence only, without querying the scheduler.

Confirmation is recorded as a CRM user-command action, not a native approval receipt or proof of a physical human click. The native command has real session/source authorization, but does not run through model `pre_tool_call` approval hooks. Missing host capabilities, ambiguous routing, hidden companion/main panes, changed sessions/profiles, stale snapshots and catalog collisions block dispatch.

A lost reply is **unknown**, not failed. The UI never resends an operation automatically, and recovered history does not offer the original Confirm button. Use its exact durable ID to read status. **Withdraw unclaimed operation** only fences an operation still stored as prepared, preventing a delayed command from claiming it; it does not cancel an assignment or existing schedule. Once dispatch starts, withdrawal cannot undo it. A still-dispatching or crashed operation retains its mutation reservation; status reads and Check do not clear it. There is no automatic recovery lease. Only a returned unknown result with atomically recorded, known non-pending assignment evidence can release that reservation and permit a separately reviewed cancellation, without authorizing a replacement schedule.

Closing the review, switching views or reaching a timeout is not cancellation. Operation records survive app reload and are paged in task history. If preflight definitely failed before any preparation POST, **Retry same preparation** explicitly rechecks the same frozen key and scope and opens review only. Once a POST may have been invoked, that retry is unavailable; recover the original immutable key through history instead of replacing it blindly. The catalog/name check assumes stable trusted host configuration and cannot atomically attest plugin ownership. See [the full operation contract](CRM_CONFIRMED_OPERATIONS.md).

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

Direct **Save future assignment** is the shortest path to real saved intent. The older future-preparation option also remains available: it asks the real native agent to call `crm_work_create` and save intent only. It must return the assignment ID and actual saved state. Refresh saved history to see that evidence; copying a request does not create a history row or scheduling badge.

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

The UI reports and optional expected-version field do not change existing tables. CRM-confirmed operations add one profile-scoped table lazily on explicit preparation; status reads do not create it. Incompatible shapes fail closed and require an explicit future migration. Assignment report routes do not initialize missing assignment tables. Multi-query reads use explicit SQLite snapshots or PostgreSQL repeatable-read, read-only transactions, including table availability checks. Unknown/incompatible state or corrupt stored intent fails visibly rather than producing a healthy coverage claim.

This prototype classifies complete local task/assignment history before filtering and pagination. Work is proportional to that history, so server paging prevents display truncation but is not a large-dataset query optimization. A later page request is a new snapshot; concurrent changes can move items between offset pages. No background dispatcher, retry daemon, cadence engine, durable human-review toggle or never-missed guarantee is implied.

See [verification](VERIFICATION.md) for executed checks. Native window layout, keyboard/focus, actual clipboard/native Send, real-model behavior and operational restart/recovery must be distinguished from synthetic component and database tests. This feature adds no email account access, external sending or production deployment.
