# CRM-confirmed assignment operations

This feature provides a separate user-interface action lane for saved future
internal assignments. It is not direct chat submission and does not claim
model-tool approval parity. It adds no external messaging, provider connection
or immediate-execution shortcut. See [verification](VERIFICATION.md) for the
executed checks and remaining native-window and real-model limits.

## Supported host boundary

The inspected Hermes source is
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. Its Desktop cron controls already use
authenticated dashboard actions separately from agent `pre_tool_call` hooks
(`apps/desktop/src/api/cron.ts` and `hermes_cli/web_server_cron.py`). Its plugin
SDK also supports registered user commands, scoped tool dispatch and exact
profile-routed command requests.

CRM uses that explicit user-action model. It does not submit a chat prompt,
alter a native draft, manufacture a transcript, create a hidden conversation,
change providers or mutate another profile. No host-core modification is needed
for this lane. Future jobs retain the existing restricted read/report toolsets,
local output and authenticated run-report boundary.

## User workflow

1. Save a future assignment and select its exact record. Saving alone remains
   distinct from scheduling.
2. In the verified CRM companion beside the intended existing main native chat,
   choose to review scheduling or cancellation. CRM prepares a durable operation
   from the backend's current assignment, not a browser-supplied copy.
3. Review the complete action and scope: profile, assignment/task identities and
   versions, run time, owner, instructions, success criteria, bound job and
   consequences. Scheduled analysis uses that profile's configured model provider
   and CRM data; local delivery does not mean no model-provider data processing.
4. Explicitly choose **Confirm schedule in CRM** or **Confirm cancellation in CRM**.
   The actual authenticated native user command receives only the prepared
   operation ID. Check is a separate, explicit observation-only
   action and requires no redundant confirmation.
5. Inspect the durable operation and actual assignment state. A successful
   transport response is not proof the agent ran, produced a correct result or
   completed the business follow-up. Pausing future scheduling does not stop an
   already running agent. A fully matched completed/disabled one-shot with an
   explicit null next run needs no Pause; its distinct inactive observation does
   not claim cancellation success and remains historical evidence.

The UI describes this as **CRM-confirmed scheduling**, not a native approval
receipt or proof that a human clicked. Authentication and a recorded confirmation
request do not attest to a physical user's interaction. Native command admission
and the plugin's own exact-scope checks remain mandatory.

## Durable boundaries

- REST only prepares, reads and withdraws local operations. It never receives a
  plugin tool context or directly calls a model or scheduler.
- Preparation freezes a server-derived assignment/task snapshot and an intended
  native session. The command verifies its actual admitted source/session and
  current profile against that target.
- A stable operation ID and idempotency key survive uncertain replies. Repeated
  commands return existing state rather than dispatching again. An explicit
  same-key preparation retry is offered only when preflight proved that no POST
  was attempted; it opens review and never silently confirms or dispatches.
- The registered command name is a stable, high-entropy name derived from the
  current workspace/profile. Before dispatch, the UI checks the current command
  catalog for that registration and rejects reported user-command, built-in or
  skill collisions and discovery warnings. It never falls back to a generic
  fixed command name or dispatches an unknown command.
- The operation's one-use dispatch transition and the exact assignment claim
  occur in the same database transaction. Expected version, generation, digest,
  source freshness, approved time and withdrawal are checked at the relevant
  boundaries. Existing agent tool callers keep their current behavior.
- Unknown outcomes are recorded before external mutations. Existing paused
  create, exact job binding and separate resume remain in force. A lost response
  never authorizes a replacement job.
- Local withdrawal fences work only where the stored state permits. It cannot
  undo an effect that already happened. Closing a panel, navigating or timing out
  is not cancellation.
- History is paged with true totals; an absent item on one page is not evidence
  that no operation occurred. Local status recovery is read-only and never retries
  execution or silently invokes a host action.

## Rejected alternatives

A fixed command name can collide with a configured quick command or alias;
Hermes resolves those before the plugin handler. The scoped name and catalog
checks avoid ordinary accidental collisions. They are **not** an atomic handler
ownership guarantee: this SDK's catalog exposes names/descriptions, not plugin
owner/revision, and dispatch resolves configuration again afterward. This lane
assumes stable, operator-controlled host configuration. It does not protect
against a concurrent trusted configuration edit or malicious plugin replacement.
An upstream exact-plugin dispatch/registration identity would be needed for that
stronger contract. The name is not a credential or an authorization token.

Direct `prompt.submit` without native history repair can collapse repeated
responses into an earlier turn and mix persisted row identities. Ordinary
`openSession` can also navigate back to an older conversation after a newer user
selection. The safe in-place refresh option lacks a runtime compatibility marker
in this host. No direct chat-request foundation is activated or distributed in this increment.

Blocking `ctx.ask_choice` inside a user command is also unsuitable here. It holds
the socket's control queue while waiting; Stop/resume can queue, Stop can clear
the native question, and another agent question can overwrite the same session
slot. Its public API has no per-call timeout or cancellation handle. An application
deadline does not release that queue. CRM will not activate that flow, change the
host's global timeout or invent a background-thread workaround.

## Verification checklist and limits

- Immutable server snapshots, strict input and exact workspace/profile/session
  binding; aliases must not be confused with backend profile names.
- Atomic duplicate, stale source/assignment, expiry, withdrawal and concurrent
  dispatch guards on SQLite and actual disposable PostgreSQL.
- Unknown create/resume/pause outcomes, lost command replies, reload recovery and
  separate business-task/report/host states.
- Actual host command registration and authenticated routing in both plugin
  isolation modes, under credential/network guards and synthetic inputs.
- UI explicit review/confirm, no automatic dispatch, every asynchronous boundary,
  same-tick reconnect/profile/session A→B→A, focus, repeated clicks and paged
  unresolved history. Unsupported capabilities must fail closed.
- Independent source review, followed by distinct native-window and guarded
  execution checks. No real email, account access, provider calls or production
  deployment is enabled by this feature.
