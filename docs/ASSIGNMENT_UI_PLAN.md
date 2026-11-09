# Make agent assignments usable from CRM

Original implementation plan reviewed against CRM `04b69ac1cd093481ab1d43634a1a144425bb2f3a` and official Hermes `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. The request builder, atomic expected-version check and paged coverage/history reports now exist in source; see [the current workflow and limits](ASSIGNMENT_UI.md) and [executed verification](VERIFICATION.md). A separate durable [review acknowledgement](REPORT_REVIEW_UI.md) is now implemented; direct dispatch alternatives, quality dispositions, cadences and wider automation remain future work. Baseline line references are historical design evidence, not current line numbers.

## Recommendation

Add a **Prepare agent request** panel to an open task, beside the existing native conversation. It prepares reviewable text for the user to copy, paste and explicitly send in native chat. The panel does not submit prompts, schedule jobs or read/write the native composer. Keep the existing assignment history as the source of durable state.

This is useful workflow assistance, not a working one-click Run now button. It makes the supported future-assignment tools discoverable without introducing another execution path. A separate read-only coverage report should make unassigned, overdue, uncertain and review-needed work visible across leads. Neither feature can promise that a task will never be missed.

## 1. First increment: a request builder, not a dispatcher

### Entry points and labels

- On an **open task**, offer **Prepare agent request**. On contacts and opportunities, retain **Create follow-up** and **Chat with Hermes**; require selection or creation of a real task before preparing a scheduled assignment.
- Show fixed executor text: **Hermes in this connection / profile**. The current implementation does not select another agent, another profile or a named specialist. Show **Human owner** as a separate, user-entered accountability label. It is not an authenticated person, permission grant or executor selector.
- Modes: **Ask for help now**, **Prepare future internal analysis**, **Ask to schedule saved assignment**, **Ask to check assignment**, and **Ask to cancel future assignment**. Offer the latter three only for an explicitly selected existing assignment.
- Buttons: **Preview request**, **Copy request**, **Open native chat**, **Refresh saved status**, and **Discard prepared request**. Do not label a copy action **Run now**, **Schedule**, **Assign**, **Cancel job** or **Send**.
- Always show: **This request is prepared here only. Copying does not save an assignment, schedule work or send a message. Paste into the matching native chat, review, then use its Send button.** Display any already saved assignment separately. A successful copy changes only the local copy status.

### Prepared data

Store the builder in component memory, scoped to the mounted connection/profile/task and native conversation binding. Do not persist it in local storage, native chat drafts, task notes or assignment tables. Do not call `crm_work_create` merely to preview.

Fields for future analysis: human-owner label; instructions; success criteria; a future one-shot run instant with explicit timezone/offset; separately displayed existing business due time; and a stable request/idempotency key. State the scheduled scope visibly: **Existing CRM data only; no web research, record changes or outreach.** Do not use a time a few seconds ahead as a disguised run-now feature.

Keep a request's key and frozen fields stable across repeated Preview/Copy. Editing meaningful fields invalidates its preview and creates a new revision only before it may have been sent. After Copy, the UI cannot know whether the user sent the old text: do not offer a silent replacement/retry. If changing a copied request, warn that an earlier assignment may exist and ask the agent to inspect it before creating another. A new key is not evidence that the old work never executed.

Preview the exact text to be copied. Include connection/profile, task ID and version, user-entered instructions, success criteria, requested instant and request key. Do not include the workspace token, hidden record text, contact details, credentials, transcripts or another conversation's draft. Record content must be read through CRM tools and treated as untrusted data.

### Preview and Copy checks

Reuse `captureChatBinding`, `createRouteClient`, activation generations and lifecycle disposal, not a second routing system (`desktop/plugin.js:19–99,122–173,211–255`).

1. Require no open unsaved record editor; an existing primary native conversation must have verified matching connection/profile ownership. Missing, secondary-tile or ambiguous ownership is a blocker, not a fallback.
2. At **Preview**, capture task ID/version, workspace token internally, route identity, chat binding, builder revision and action generation. Fetch the task using the scoped read endpoint and token. For new work or scheduling, require the same ID/version and `status=open`; do not silently refresh the user's approved subject to a newer task version. Validate the future instant and explicit timezone. Check/cancel modes may target done or changed tasks because their old future jobs can still need attention.
3. At **Copy**, repeat the scoped task read and all checks. For saved-assignment actions, also re-read that exact assignment and check its task link, version, generation, state and source-task freshness. A change since Preview requires a new preview. Do not schedule cancelled/stale assignments. Check remains available; cancellation help remains available for done/changed tasks and locally cancelled assignments whose host pause is unverified, using their latest reviewed version.
4. Recheck mount, latest builder revision, task selection, workspace, chat and activation generations after every asynchronous boundary and immediately before the clipboard call. Use one in-flight copy lock. An A→B→A switch, disconnect/reconnect or plugin reload must invalidate old callbacks.
5. A failed/uncertain clipboard result is not a successful copy. If a route changes after a clipboard write has started, suppress stale success feedback; do not overwrite or erase the clipboard to compensate. The reviewed text carries its scope, and native Send remains the user's final check.
6. Display the intended conversation/profile alongside the preview. Never promise the user cannot manually paste into a different chat. Never inspect the composer to verify paste or infer submission.

The existing reference preview does not fetch at Preview time; it fetches again at Copy (`desktop/plugin.js:385–405`). The new builder should deliberately add both checks rather than claiming the old helper already provides them.

### Text templates

Future intent, **save only**:

> In this CRM profile, read task {id} and verify it is still open at version {version}. If it changed, stop and show the difference. Save one future internal-analysis assignment with human owner {owner}, instructions {instructions}, success criteria {criteria}, run time {ISO instant and displayed timezone}, and idempotency key {key}. Use crm_work_create. Do not schedule it yet. Return the assignment ID and saved state. Do not contact anyone, change business records or mark this task complete.

Scheduling an existing saved assignment:

> Read assignment {assignment_id} and its source task. Confirm its frozen instructions, human owner, task version and run time still match this reviewed request: {bounded frozen fields}. If they differ, stop. I request scheduling this existing assignment using crm_work_schedule. Do not create a replacement or use another scheduler route. If the outcome is unknown, reconcile that assignment and report uncertainty without retrying creation. Keep the business task open.

Alternatively, a distinct **Prepare save-and-schedule request** can combine these explicit instructions in one reviewed native message. It must still describe two backend operations; creating intent and scheduling remain separate state transitions. The smaller first increment can omit this combined mode.

Immediate help:

> Read open CRM task {id}, version {version}; stop if it changed. Help with {user-written goal} now in this conversation. State what you actually did and any unavailable capability. Do not schedule work, send outreach, change account/provider settings or mark the business task complete. This is an interactive request, not an authenticated scheduled-work report.

Check/cancel requests must name the exact assignment. Check uses `crm_work_get` then `crm_work_reconcile`, not a new create. Cancellation requests a fresh version read and `crm_work_cancel`; explain that it invalidates the assignment and requests pausing its future schedule, not stopping an already running agent. A done or changed source task must not prevent asking to cancel the old future job.

### Residual authorization/version boundary

Copy-time checks are observations, not atomic approval carried to execution. At the reviewed baseline, `_WorkCreate` had no expected-task-version argument; creation captured whatever open task version existed inside its transaction (`hermes_crm/plugin.py:18–27`; `hermes_crm/native_work.py:202–240`). An agent can re-read and compare the copied version, but an edit can still occur between that read and create.

The current source adds optional `expected_task_version` and rejects a mismatch inside the same transaction/guard that freezes intent. New prepared requests include it. Legacy omitted-field requests remain compatible, and exact replay cannot silently replace the original expected version. This is a backend guarantee; it is not accomplished by frontend checks alone. Do not describe the initial request builder as a secure execution-authorization token. The existing schedule path continues to recheck the frozen task version, cancellation and future time before resume (`native_work.py:312–389`).

## 2. Show only states supported by evidence

Render these as separate facts, not a single green progress bar:

- **Request prepared / copied**: local UI only; not persisted intent and no execution coverage.
- **Intent saved, not scheduled**: backend `pending/not_scheduled`.
- **Scheduling outcome pending or unknown**: `create_unknown`, `resume_unknown` or `unknown`. An unsuccessful or lost reply is not proof nothing happened. Offer a request to reconcile, never blind retry/create.
- **Bound job paused**: show the blocker/reason. If approved time elapsed, say **Run time elapsed while paused; review required**. Do not resume late or reschedule silently.
- **Schedule registered, execution unverified**: backend `scheduled`, exact job ID and requested instant. Show last observation time and source; an old observation does not establish current gateway/model availability.
- **Host state observed**: derive only from the latest applicable `job_observed` event for the exact bound job. Label **Host observed running/failed/completed at {time}**, distinct from assignment and report state. No authenticated report still means no authenticated report, even after observed host completion.
- **Result reported, awaiting human review**: show report outcome `completed`, `blocked` or `failed`; content, time and native provenance. A report never marks the business task done and does not prove host terminal success or delivery.
- **Source task changed**: prominently mark the assignment/report stale. Do not hide it or treat a new open task version as covered by old work.
- **Cancelled assignment**: show local invalidation separately from **future schedule pause observed** or **pause outcome unknown**. Never say an already running execution stopped.
- **Business task done**: separate existing task state. Do not offer a new-work request without deliberate reopening. Completion does not cancel a host job. Existing assignment history and cancellation help remain visible.

The task schema has only `open` and `done`, not a business-task `cancelled` status (`domain.py:112–125`). Assignment cancellation/supersession has its own generation fence (`native_work.py:448–493`). At this original baseline there was no persisted report-review action. The later [acknowledgement increment](REPORT_REVIEW_PLAN.md) adds a durable ledger and separates review status from source freshness; it is not a frontend-only toggle. Original line references describe the historical baseline.

Read `/work` and `/work/{id}` only for saved facts (`native_api.py:111–131`). **Refresh saved status** does not query Hermes jobs; `crm_work_reconcile` is the separate active-tool observation. History errors must retain last successful data with its age, not become empty history. Show task ID, assignment ID, exact native job ID, frozen task version, requested run time/timezone and human owner without raw provider errors or secrets.

## 3. Coverage queue: make the next action visible

First retain the existing server-filtered **Leads with no open follow-up** and **Leads with overdue follow-ups** reports. Their counts describe stored business tasks, not scheduled execution (`domain.py:311–369,435–452`). Do not infer missing work from the 500-record task snapshot or the first 100 assignment rows.

A small, separately scoped read-only follow-up report should return a bounded, stable page with exact filtered totals and `observed_at`, joining contacts → directly linked tasks or deal-linked tasks → assignments. Deduplicate tasks with both links. Include the earliest open task's exact ID/title/due time plus coverage evidence. Current contact reports return earliest date/counts but not that task's title or assignment coverage.

Useful queue predicates:

- **No open next action**: no linked open task in authoritative SQL.
- **Overdue next action**: an open linked task has business due time before the server instant.
- **Agent work not scheduled**: an open task has no current assignment, or only saved `pending` intent. Keep human-only follow-ups distinguishable; do not claim every open task was intended for autonomous execution.
- **Needs scheduling review**: unknown/create/resume outcomes, bound-paused work, stale source, or local cancellation with unverified host pause. Historical cancelled assignments must not make a newer valid assignment appear cancelled.
- **Run time passed, no report observed**: approved instant is past and no accepted report exists. This is not necessarily failure or nonexecution; include observation age and an explicit check action.
- **Reported blocked / failed**: from report outcome. A host-observed failure without a report is a different evidence label.
- **Result awaiting review**: report exists, with separate source freshness and business-task state. Today reviewed reports cannot be durably excluded until a review contract is added.

When multiple assignments remain relevant, show all unresolved risks rather than choosing one convenient green status. Read queues do not reconcile, retry, cancel or advance a cadence. A genuinely durable future coverage monitor, notification policy, explicit hold/exclusion model and recurring next-step advancement are later work, not implied by this panel.

The legacy assignment listing sorts oldest-first and returns a bounded list without pagination/total (`native_work.py:273–280`; `native_api.py:111–122`). That is sufficient for labeled task history but not proof of global completeness or a reliable newest-assignment selector. The new read-only report endpoints provide server pagination/filtered counts. Coverage totals count evidence rows, not unique leads, and current classification remains proportional to complete local history.

## 4. Credible research → contacts → personalized draft workflow

Keep two capability lanes explicit:

1. **Interactive native conversation:** ordinary host tools may research public sources, read/write CRM records and prepare a personalized email draft, depending on the already available tools and normal host permissions. The CRM plugin already registers contact/task create and versioned update tools (`plugin.py:93–116`), but provides no web-research or email tool. Do not infer capabilities from a provider balance, visible chat or generic RPC transport. If research tools are unavailable, report that blocker rather than inventing facts or changing setup.
2. **Scheduled assigned work:** the current job receives only the 11 CRM read/work-read/report tools through the restricted sets, with `no_mcp`. Its fixed job prompt prohibits external research, business-record mutation, delegation and outreach (`native_work.py:25–27,188–199,329–332`). It can analyze existing CRM facts and report a proposed next step or draft text for human review. It cannot research new leads, create contacts or send email.

Suggested interactive demo: choose a task; ask for public-source research with citations and uncertainty; review the proposed contact and duplicate candidates; explicitly request contact creation/update and a linked next-action task; review a personalized email draft in native chat. User-entered facts must not be replaced by guessed addresses. Draft text is not a sent message. Preserve the next action while work is blocked or awaiting review.

No email-account read, provider setup, credentials, sending, calls or texts are in this increment. CRM audit activity records CRM changes, not sent/received email. A future email adapter needs explicit recipient/content authorization, provider availability, message/thread IDs, idempotency, sent-vs-draft-vs-unknown evidence and recovery. Do not fabricate a Sent activity from an agent claim. Ordinary interactive output must not be inserted as a `crm_work_report`: that handler is reserved for the exact assigned cron occurrence (`native_work.py:516–560`).

## 5. Direct dispatch alternatives and exact host boundaries

The public APIs exist; their availability is not permission to use them or evidence that the CRM contract is implemented.

- **Keep native Send (recommended):** uses the existing native transcript and ordinary agent tool-policy flow. No composer API, parallel model client, hidden session, background runner or borrowed REST tool context. This is the only proposed first UI increment.
- **Canonical RPC run now (later):** `host.requestProfile` can address an exact connection/profile; generic `host.request` resolves the live ambient gateway per call (`apps/desktop/src/sdk/index.ts:1367–1389,1502–1514`). Canonical `session.create`, `prompt.submit`, `prompt.receipt` and `prompt.cancel` support stable IDs and admission receipts. The disabled bridge already models part of this. Before enabling, require reviewed durable store/API wiring, exact route/runtime/session binding, normal visible approval/question handling, cancellation/reconnect/restart and unknown-admission recovery, full effective scope verification and real native/model tests. Current tool-scope snapshots are not an atomic host ceiling. Do not set unattended/yolo/ignore-rules, change providers or create access grants. This is a separate execution product, not a copy-button upgrade.
- **`cron.manage` gateway RPC:** its action enum is only list/add/remove/pause/resume, and its input schema has no `enabled_toolsets` or `paused` (`tui_gateway/contracts/tools_commands.py:438–455`). The actual `add` implementation forwards name/schedule/prompt/repeat/continuity/deliver only (`tui_gateway/methods_tools.py:1305–1329`). Therefore the existing NEXT_RELEASE_PLAN statement specifically about this RPC is correct.
- **Desktop/dashboard cron REST:** a different surface supports create/get/runs/pause/resume/trigger/cancel (`hermes_cli/web_routers/cron.py:734–805`). Its create schema includes `paused` and `enabled_toolsets` (`hermes_cli/web_models.py:325–350`), and creation forwards them (`hermes_cli/web_server_cron.py:244–285`). Do not generalize the RPC limitation to this REST surface. It still does not supply the CRM assignment ledger, user-reviewed version binding, active-agent authorization path or a reviewed direct adapter. Directly calling it is not an approved shortcut. Manual trigger is also not the approved scheduled occurrence accepted by `crm_work_report`.
- **Composer helpers:** the SDK exposes them, but CRM must continue to use none. Address resolution can reduce a stored session to mutable `main`; insertion defers through the focus bus and appends `draftRef` (`apps/desktop/src/sdk/composer.ts:28–52,109–126`; `apps/desktop/src/app/chat/composer/focus.ts:175–180`; `apps/desktop/src/app/chat/composer/hooks/use-composer-draft.ts:259–280`). Do not revive automatic insertion, draft reads/writes, automatic submit or DOM workarounds.

### What the registered tool context actually establishes

CRM's registered handler accepts `**kwargs`, validates model arguments and forwards context to scheduling, reconciliation and cancellation (`hermes_crm/plugin.py:56–79,135–143`). `_host` checks matching profile, callable `dispatch_tool`, and rejects scheduling/reconciliation from a current cron execution (`native_work.py:176–182`). Create itself is a local intent write and does not call `_host`.

These are **trusted reachability and source checks**, not new secure attestations of an active agent or explicit human approval. There is no required active-agent token, signed approval field or separate delegated-child prohibition in the registered scheduling handler. Normal host model-tool dispatch provides task/session/user-task context and binds approval observability; it does not universally supply a `parent_agent` argument (`model_tools.py:836–859`). `PluginContext.dispatch_tool` forwards to `registry.dispatch` and only opportunistically supplies a CLI parent (`hermes_cli/plugins.py:676–685`); registry dispatch calls the handler directly (`tools/registry.py:972–989`). Do not claim the nested cron dispatch independently reruns all outer agent approval gates. The ordinary agent executor is where scope/hooks/guardrails run (`agent/tool_executor.py:678–748`).

Consequently keep mutations reachable through the genuine interactive tool path and host policy; never manufacture a context in REST or treat a nonempty session ID as authorization. The guarded end-to-end fixture explicitly supplies an AIAgent/context to the registered handlers (`tests/test_native_work_e2e.py:441–493`); it proves context propagation and scheduled execution, not a model-issued scheduling request or approval presentation. Before stronger UI claims, test the latter through the normal interactive executor in a disposable environment.

### Minimal proposed documentation clarification

Leave NEXT_RELEASE_PLAN's `cron.manage` limitation intact. After that sentence, add: “The separate Desktop/dashboard cron REST API does accept paused creation and explicit toolsets. It is not wired to the CRM assignment ledger or the active-agent authorization workflow, and is not an approved direct scheduling path for this build.”

Replace the older generic “public UI cron-management surface does not provide…” sentence in EXPERIMENTAL_EXECUTION's remaining gates with that RPC/REST distinction. Prefer “Scheduling is exposed through the real interactive tool path; REST does not borrow a tool context” over claiming `_host` independently verifies an active agent. These are proposed edits only; existing documents were not changed by this investigation.

## 6. Acceptance and delivery gates

For the first builder increment:

1. Preview/Copy/open/close performs only scoped reads and an explicitly requested clipboard write. Assert zero composer access, prompt submission, session creation, cron mutation, CRM writes and execution-bridge imports.
2. Assert no assignment appears and no scheduling badge changes after preparation/copy. Empty and unavailable history remain distinct. Backend state, report outcome and business completion render independently.
3. Test edits between render→Preview, Preview→Copy and during each read; changed IDs/versions, done tasks, cancelled/superseded assignments, past run times, invalid/ambiguous timezone inputs, edited builder fields and duplicate clicks all invalidate stale actions.
4. Test connection/profile/chat A→B→A transitions, same-profile different connections, disconnect/reconnect, unmount/reload, stale API/clipboard callbacks, focused secondary tiles, missing SDK capabilities and failed clipboard writes. Preserve unsaved forms and native draft typing without reading the draft.
5. For scheduling/cancellation requests, test exact assignment references, no replacement on unknown results, and cancellation help on a completed/changed source task. For completed reports, assert no automatic task completion and no fabricated reviewed/sent state.
6. Test keyboard focus, labels, narrow split layouts and real clipboard paste/native Send manually in an isolated native window. Source/React tests alone do not verify actual window layout or delivery.

For a later coverage report, add SQLite and actual disposable PostgreSQL tests for direct/deal-linked task deduplication, multiple assignments, historical cancellation, overdue-vs-run-time differences, stale reports, more than 500 tasks/100 assignments, exact totals, stable pagination, profile isolation and refresh failure. Counts must derive from authoritative server queries, not a partial UI cache.

For any eventual automatic dispatch, separately verify denial through the normal agent tool-policy path, real-model capability availability, visible approvals, lost responses, duplicate admission, cancellation races, owner-process restart and closed-pane behavior. No real-provider or production check is authorized by this plan. Keep source implementation, testing, review and deployment approvals explicit.

## Source locator

CRM line references above are relative to the repository at the reviewed commit. Official-host line references are relative to the pinned source checkout, or to:

`https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/`

Append the cited file path and `#L<first>-L<last>` to inspect that exact source. No host APIs or provider accounts were invoked during this investigation.
