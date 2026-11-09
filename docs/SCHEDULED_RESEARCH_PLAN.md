# Scheduled public research v1

Implemented as an additive, task-linked mode with ten new tools (83 total), a
[native Task panel and API](SCHEDULED_RESEARCH_UI.md), and authenticated run
writers. Existing internal-analysis assignments, prompts and toolsets are
unchanged. The verified execution path and remaining live-research limitations
below are distinct; this document does not claim production readiness.

## Implemented contract

An explicit assignment binds an existing open CRM Task ID/version, a separate
human accountable owner, and one exact current Contact or Company ID/version.
Task due time is captured from the server separately from the approved research
run time. A public research question, research preset (`search` or `web`), maximum
saved source packets (1–10), and permission for one note proposal are immutable. The public
question must contain only information the user intends to send to the configured
research/model providers. Task text and current private record notes are not
copied into the run input.
The source limit caps saved evidence packets, not search calls or fetched URLs;
tool-call budgets and provider availability remain owned by Hermes.

The assignment is saved only until an explicit scheduling request. Public host
scheduling creates a future one-shot paused, durably binds the exact returned job,
and resumes after fresh source checks. Unknown create/resume outcomes never
trigger replacement creation or automatic execution retry. Reconcile observes
only the known exact job; it cannot adopt a name-matched orphan. Local cancellation
invalidates writers before requesting a pause. Pause is not running-agent stop.

Only the new research preset and `crm_scheduled_research_run_v1`, plus `no_mcp`,
are requested. The four run tools read the approved input, save source evidence,
prepare one note proposal if approved, and save an authenticated report. They do
not apply notes, create records, send messages, complete Tasks, delegate, run code,
change host configuration, or grant access.

Each write checks host-owned cron identity, bound job/name/profile, built-in
source, approved instant, generation, first accepted execution ID, active state,
Task version/open state and target version/archive state. Source evidence cannot
be attached elsewhere; a proposal must reference evidence from this assignment.
Evidence/proposal domain validation and insertion, source guards, and durable
operation receipt use one database transaction. Exact retries return the original
receipt; conflicting retries fail. Cancellation fences even historical write
replay. A finished report prevents new writes. Record/Task changes reject new evidence/proposal writes and completed reports.
An authenticated blocked/failed report may explain a stale source with
`source_current=false` and a bounded `source_reason`; it never changes source
records or bypasses schema, identity, generation or cancellation checks. Existing
receipts remain visible to interactive reviewers.

Reports are agent claims awaiting human review, not terminal host receipts or
proof of correct research. A report's `completed` outcome never completes the
business Task. Evidence remains caller-supplied unverified claims; citations and
observation timestamps are retained without pretending storage fetched them.

## Native Task and agent workflow

The reviewed native Task panel and authenticated workspace-token API expose
assignment creation and read-only status/history. The explicit workflow is:

1. Select an existing open Task and exact Contact/Company, review the current
   versions, public question, human owner, run time and source-packet limit.
2. **Save intent**. Saving alone does not create or resume a host schedule.
3. **Prepare**, then **Copy** the request, paste it into genuine native chat,
   review it and send it there. Scheduling, reconciliation and cancellation use
   their distinct native tools. There is no direct scheduling from REST and no
   direct native **Send** button in this panel.
4. Inspect Task-linked history/status and the agent-reported result. Saved
   evidence and proposals are available in the Contact/Company Research panel
   for separate review/apply; a report never means a note was applied.

The plugin registers `register_scheduled_research_tools(register_tool, ctx)`
and declares the ten tools in `plugin.yaml`. Management, read and run toolsets
are distinct. Interactive agents can use create/get/list/schedule/reconcile/
cancel directly within their authorized scope. A future direct-send command
lane needs independent authentication, snapshot and session/profile review;
it is not implemented by routing through the older internal-analysis lane.

## Storage, cancellation and recovery

Runtime schema checks run noninitializing on the active read/write connection
before assignment locking or mutation. Missing, partial, newer or malformed
storage fails closed for execution and mutations.

`ScheduledResearchStore.page(task_id=None, limit=50, offset=0)` filters and
paginates in the database and returns an exact total. Wholly absent optional
storage returns `initialized:false`, `storage:absent`, `items:[]`, `total:null`.
This is not proof that no prior assignments existed. Partial or incompatible
storage is an error, not an empty history.

Cancellation invalidates local run authority first, then reads the exact bound
public job. A matching completed one-shot with explicit `enabled=false` and
`next_run_at=null` records a distinct inactive observation without pause.
Missing, duplicate, mismatched or unreadable jobs stay unconfirmed; other exact
matching jobs receive the authorized future pause. Lost replies stay unknown,
and observations cannot overwrite a newer assignment version. Repeating cancel
on an already cancelled assignment does not retry pause. Neither cancellation
nor inactive observation stops a running agent or completes the business Task.

Export includes both scheduled-owned tables as one scoped family. Export and
offline recovery validate payload integrity, scope, Task/target references,
evidence/proposal ownership and report identity. Recovery preserves original
rows under `recovery_*`, with empty scheduled runtime tables and no scheduling
authority. No host action, source cancellation or identity rebind occurs.

## Verification status

The pinned registry/resolver and Company/Event workflow suites passed again in
both plugin isolation modes: six tests, comprising two seams and four actual
host cases. The scheduled due-run separately passed its seam and both real
isolation-mode cases. These counts describe different tests, not live-provider
research. See [verification](VERIFICATION.md) for consolidated acceptance results
and the final local-suite counts: 1,761 Python passes with 753 optional skips;
all 48 scrubbed check commands passed.

The final independent database run passed **1,319 mixed checks**, with two
not-applicable Contact-archive skips and no failures/errors. Focused coverage
was 269 local cases plus **38 actual PostgreSQL cases**; all 1,012 prior mixed
regressions also passed. PostgreSQL 17.11 ARM64 exercised the distinct JSON
filter/pagination path, absent/malformed storage, stale-source reports,
completed-inactive cancellation and PostgreSQL export to SQLite quarantine.
The earlier attempt failed before CRM creation because its fixture schema name
exceeded the existing domain limit. The reviewed test-only correction uses a
shorter random prefix and a regression against the actual validation rule.
Runtime bytes were unchanged. All 273 frozen files matched the reviewed snapshot
and all four owned initial/final containers were removed. Concurrency evidence
is same-process threads, not cross-process. See verification for exact scope.

## Host evidence checked from official pinned source

All links below target `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` and were read
through the web connector for this assessment; they are not local runtime tests.

- [Toolsets](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/toolsets.py#L64-L65): `search` is search-only; `web` includes extraction. Named toolsets resolve dynamically, so a frozen name list does not attest immutable implementations.
- [Scheduler resolution](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/cron/scheduler.py#L378-L446): explicit per-job selection is supported; `no_mcp` suppresses automatic MCP augmentation. Host deny configuration can still remove capabilities.
- [Scheduler tool](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/cronjob_tools.py#L1128-L1185): public `cronjob_manage` supports `enabled_toolsets`, paused creation and separate resume. Do not substitute arbitrary individual tool names for toolset names.
- [Plugin context](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/hermes_cli/plugins.py#L625-L634): scoped `dispatch_tool` is the supported dispatch facade. `current_cron_execution` is available on the same context (lines 379–382). No complete effective-inventory or full remote-prompt attestation API was identified in this facade.
- [Execution identity](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/cron/execution_identity.py): identity comes from the running execution ledger; delegated children do not receive it. This identifies the occurrence, not unchanged prompt content or later completion.
- [Unattended approvals](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/approval.py#L918-L1017) and [default policy](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/approval_context.py#L309-L320): cron cannot wait for interactive approval cards. Flagged operations resolve under the existing unattended policy; its default is deny. CRM does not change that policy or disable approval hooks.
- [Web backend](https://github.com/NousResearch/hermes-agent/blob/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19/tools/web_tools.py): search/extraction availability depends on the host's selected providers. This increment does not configure, probe credentials, install or grant a backend.

## Remaining boundaries and deployment gates

- Live public research still needs an explicitly authorized, configured host
  research/model provider and an observed real search/extraction flow with
  useful cited evidence. The synthetic due-run does not establish provider
  availability or reasoning quality. Never change credentials, grants or cron
  approval policy merely to make a demonstration succeed.
- Native visual, accessibility and real Desktop-delivery acceptance remain
  separate from API/component tests and headless host execution.
- Human report-review disposition receipts (accepted, revision requested or
  dismissed) are not implemented. Reports remain agent-reported and awaiting
  review. Proposal review/apply, host success and Task completion stay separate.
- Preserve the reviewed source/runtime parity through publication and inspect
  hosted CI on the exact public commit. Prior green runs do not qualify a new head.

Presets request named host toolsets, not arbitrary per-assignment permissions.
Browser, terminal, MCP and broader record mutations require separate design and
review. `no_mcp` prevents implicit MCP augmentation; host deny/provider settings
may still remove tools. Public job matching uses a prompt preview, not full
prompt attestation. Preflight does not attest the complete effective inventory.
Trusted host configuration and tool implementations remain an operator boundary.

Cron cannot wait for interactive approval cards. Existing unattended approval
policy applies, including denial; CRM does not weaken it. A missing backend may
produce a blocked report or prevent a model turn entirely. A saved schedule or
live gateway is not proof of research execution. The maximum source count limits
saved packets only, not network requests, fetched URLs, model cost or tool calls.

### Approved CalVer probe guard extension

The original `test_native_work_e2e.py` and historical fingerprints remain
unchanged. Only the new scheduled due-run installs `scheduled_research_guard.py`
via a temporary pytest monkeypatch. It validates original and effective guard
hashes and the exact pinned `hermes_cli/version_info.py` source hash before
allowing exactly `git describe --tags --long --match v2[0-9][0-9][0-9].* HEAD`,
with executable `git`, cwd the owned pinned checkout, and the `_run_git` source
frame. This is a read-only version query, not general Git permission. Dynamic
`git show`, altered arguments, other callers/cwd, processes, external networking
and credential access remain subject to the unchanged guard. Negative tests
exercise the effective audit function without launching processes or networking.
The narrow correction passed independent review before the successful guarded
due-run. Local seam tests alone do not establish host execution success.


### Actual guarded execution evidence

Both plugin isolation modes (`in_process` and `host`) passed the real pinned
Hermes scheduler/admission/agent/tool path with a keyless deterministic loopback
model. Each made eight model requests at or after the approved due time and
saved supplied synthetic evidence, a pending note proposal and an authenticated
report. Notes stayed unchanged and the business task stayed open. Extra ticks
produced no duplicate execution; a separately cancelled future assignment did
not run. Both cases completed cleanup with no jobs, processes, endpoints,
sockets, forbidden audit events or synthetic model errors remaining.

Only the four assignment-bound CRM run tools were advertised. `web_search` was
absent in these intentionally credential-free profiles. This verifies timing,
identity and persistence, **not live public search, provider readiness, research
quality or visible Desktop delivery**. The selected reproducible hashes and
results are in [the sanitized execution summary](native-work-test/scheduled-research-result-summary.json).

Two earlier failed harness attempts are not counted as passes: one exposed the
read-only version probe described above; another exceeded the pinned discovery
limits (seven queries and ten describe names). The corrected fixture uses two
search queries and describe batches of ten plus four, preserving all four
positive and ten forbidden-tool checks. Local protocol tests validate those
limits and persist assertion diagnostics before an HTTP error. No production
runtime or broader guard permission was changed to fix the batching error.
