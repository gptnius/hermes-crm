# Agent conversation, immediate work and public research

This is a source-backed development plan, not an enabled capability. The
reference host is exactly
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. No user account, browser profile,
provider grant, scheduled job or production setting was changed for this plan.

## Interactive requests are not the scheduled-analysis mode

A user can ask the existing interactive Hermes agent to research or perform other
supported work using its actual available tools. Do not apply this document's
frozen scheduled-mode limits to every conversation. If a tool, account or approval
is missing, identify the specific next step instead of refusing the whole goal;
continue permitted work. These instructions do not grant new access or make an
unimplemented feature available. Preserve direct user send review and host
safeguards. See [agent assistance](AGENT_ASSISTANCE.md).

## What works today

CRM can sit beside the genuine existing Hermes conversation. Reviewed record
references and task requests can be copied for manual paste and native Send.
The plugin does not read or replace native drafts, submit hidden prompts, invent
a conversation, or own a second transcript/approval interface.

Future internal assignments use the separately reviewed native user-command
lane: create paused, bind the exact job, resume, and accept an authenticated
scheduled report. The immutable job scope is `crm_read`, `crm_work_read`,
`crm_work_report`, `no_mcp`. Its effective inventory is eleven read/report tools.
It does not include browser, terminal, ordinary CRM writes, email or delegation.
A report remains an agent claim awaiting human review, not business-task
completion. Enabling tools elsewhere in Hermes must not silently widen an
existing assignment.

## True Run now: unsupported through the verified plugin boundary

The pinned public `cronjob_manage(action='run')` cannot run a freshly paused job,
despite contradictory help text. It requests a manual claim, while only the
host's separate force-claim path can atomically clear pause. A resume followed
by Run is unsuitable: manual execution is an extra fire that preserves a
still-future occurrence and repeat budget. The assignment could run twice.
A later cleanup Pause is not an atomic cure for a lost response or crash.

The tool's background execution also delivers an asynchronous completion into
the caller's conversation. That is not the CRM's existing untouched-native-chat
contract. Its delegation identity is not the durable cron execution identity.

The core dashboard has a force-trigger route. A fresh, never-resumed paused
one-shot has no next-run instant, so this candidate is different from
resume-then-run. However, it is not callable through the verified public plugin
SDK: plugin REST is restricted to its own namespace, and the gateway's public
cron management method lacks this trigger. Raw Electron calls, core HTTP escape
routes, private imports and borrowed authentication are not acceptable substitutes.
The force-claim/dispatch crash window also needs verification before calling it
manual-only execution.

Relevant pinned source:

- `tools/cronjob_tools.py:240–255,559–590,636–660,790–844,1129`
- `cron/jobs.py:1913–1919,2723–2752,2952–2978,3177–3194`
- `cron/extra_fire.py:1–8,38–45,81–94`
- `hermes_cli/web_routers/cron.py:686–705,795–797`
- `apps/desktop/src/contrib/plugin.ts:150–154`
- `apps/desktop/src/api/plugins.ts:53–87`
- `tui_gateway/contracts/tools_commands.py:438–455`

### Practical alternative and future requirement

An explicitly labelled **Schedule soon** could use the existing future one-shot
path, with the exact reviewed timestamp, a sufficient setup buffer and a warning
that execution can be delayed. It must not be presented as immediate execution.
This is a proposed UI increment, not an existing Run now feature.

True immediate work needs a supported host operation that atomically consumes
one approved operation ID, claims the exact job, binds a durable execution ID,
and leaves no independent future occurrence or automatic retry. It needs a
separate immutable execution mode. Merely allowing a null scheduled instant or
`source='direct'` in the present report validator is unsafe: dashboard manual
execution can instead have `source='builtin'` and a null instant.

Verification must cover duplicate requests, lost replies, crash before dispatch,
account/profile/session changes, task edits, report identity and remaining future
schedule. A request to stop an active execution is distinct from invalidating
an assignment or pausing future work. Cooperative cancellation acknowledgement
is not proof the execution stopped.

## Browser research is a separate capability decision

The pinned browser toolset includes real browser automation, dialogs and vault
login capabilities. `browser_exec` runs arbitrary host Python and is deliberately gated on terminal
access (`model_tools.py:395–399`; `tools/browser_use_cli.py:1007–1037`).
Allowing it in scheduled CRM work therefore widens the existing read/report
boundary. A new Hermes profile is not, by itself, an operating-system sandbox.
Public-only instructions do not turn a browser or terminal into a read-only
security boundary.

There are two distinct development options:

1. **Interactive public-web research.** Use the genuine native conversation and
   the selected environment and its available authorized tools. For disposable
   integration tests, use an actually isolated environment and verify the browser
   backend and effective tool inventory. Isolation is a test condition here, not
   a new prerequisite imposed on every interactive research request. Do not copy credentials,
   reuse personal browser cookies, install paid services, weaken security/network
   settings, fill forms, submit messages, or assume access to a particular site.
   Any necessary login, credential, new grant or broader capability is a separate
   decision. Browser availability in one environment does not prove availability
   in another or in scheduled agents.
2. **Narrower search/extract research.** If already configured, the host's web
   search/extraction tools can support public research without browser/terminal
   automation. Clearly call this web research rather than a browser test. Treat
   results as untrusted data and retain source URLs and observation dates.

For a future scheduled research mode, define a new action and explicitly reviewed
capability set instead of modifying `internal_crm_analysis`. Keep the research
input minimal, exclude private CRM notes unless specifically needed/authorized,
and separate findings from record creation. A useful first demonstration is:
research public leads → review sourced findings → explicitly create selected
contacts. Do not turn a web page's instructions into permission to update records,
contact people, expose CRM information, or change configuration.

Suggested verification gates:

- The selected browser/search backend actually works in the selected environment;
  no mock output is labelled live research.
- Public-page-only test with no account session, form submission or external send.
- Full tool inventory checked, including inherited MCP tools and terminal access.
- Malicious page text cannot authorize additional tasks; sensitive/private data
  is not included in research URLs, external requests or generated logs.
- Stale profile/task/record context is rejected before CRM writes.
- Contact creation requires explicit intent, stable source references and duplicate
  review; no automatic email matching/merging of distinct people.
- New research capability never changes old assignment scope, report identity or
  business-task completion semantics.

## Eventual CRM migration is a separate project

A discussion of migration does not authorize reading or changing the existing
CRM. Before any migration, inventory the explicitly selected source and export
format, establish a backup/rollback plan, map contacts, deals/stages, owners,
relationships, tasks, timestamps, currency and activity provenance, and run a
read-only comparison followed by a synthetic dry run.

Do not copy authentication material or live scheduler IDs. Imported tasks must
not silently activate jobs, send outreach, or inherit another provider's grant.
Provider-backed mail observations must retain their account identity and source;
agent notes must not become provider evidence. Reconcile counts, duplicates,
links and representative records in a separate staging workspace before asking
for any production cutover. Existing private CRM data/history never belongs in
the public source repository.
