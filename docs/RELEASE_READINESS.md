# Release readiness and operational acceptance

This is the work plan for a useful, reliable single-user HermesCRM release.
It is not a production-readiness certificate. Completed source changes, local
contracts, actual-host tests and a successful live workflow are different evidence.
Use [verification](VERIFICATION.md) for exact tested revisions and limits.

## Target deployment

First qualify one operator's supported Hermes Desktop/Agent installation with
SQLite in one profile. PostgreSQL remains an explicit alternative with its own
tested schema isolation and connection configuration. Neither deployment is a
hosted multi-user CRM with tenant roles, SSO or a general compliance guarantee.
Existing credentials, approvals and model-provider configuration remain owned by
Hermes. Do not copy them into the plugin or test fixtures.

## Release gates, in priority order

1. **Real agent access to useful records.** Verify the exact installed plugin
   revision and actual registered catalog in both supported isolation modes.
   Verify the selected conversation exposes the needed interactive tools, not
   just that the plugin registered them. Exercise Company/Contact creation,
   current ordinary-note reads, cited evidence/proposals, Events and owned,
   dated tasks. Read fresh versions before updates and retain existing text.
   Company/Event exact-field reads close a concrete gap; default list summaries
   remain compact rather than being mistaken for all available data.
2. **Genuine interactive workflow.** Use a permitted, actually working public
   search/extraction or browser capability in the intended host. Find a company
   and relevant person, retain source/date/uncertainty, create explicitly linked
   records, add a cited note and prepare an Event/task. Verify results through the
   UI and after reload. Do not call fixture-provided sources live research or
   claim complete leadership coverage without evidence. No social login or
   outbound communication is required for this workflow.
3. **Timed work with an explicit scope.** Preserve existing internal-analysis
   jobs. A new versioned research mode must freeze its own reviewed tool/data
   scope and use the supported paused-create/bind/resume path, trusted run
   identity, idempotent writes and durable unknown outcomes. Test the real due
   path and cancellation/recovery, not only job creation. Unattended jobs follow
   host cron approval policy, not interactive approval cards. Never silently
   change global approval policy or inherit new MCP tools.
4. **Usable backup and recovery.** Deliver and rehearse a non-destructive restore
   into a fresh target, with key availability, schema/FK consistency, original
   provenance, record/report/relationship reads and fresh writes verified. Preserve
   safe local retry receipts. Quarantine execution/provider state and fence old
   jobs before any cutover. Wrong/missing keys, incomplete exports, existing
   targets and interrupted recovery must fail clearly. Until this passes,
   encrypted content export is not a full backup or operational restore promise.
5. **Repeatable checks.** Run credential-free SQLite/PostgreSQL, tool/API, React
   and generator contracts on the candidate commit. The [CI definition](CI.md)
   uses read-only permissions without secrets/deployment access; inspect the
   actual remote run before treating this gate as complete. Keep
   skipped live-host/browser cases visible. A workflow file alone is not green CI.
6. **Human acceptance.** Inspect the installed current build in light/dark and
   narrow layouts, including forms, drawers, empty/error/loading states,
   keyboard navigation/focus, readable labels and activity/task drilldowns.
   Exercise interruption, duplicate clicks, stale records, changed profile and
   back navigation. Do not interrupt a user who is working in that app.
7. **Operational handoff.** Document exact install/update, backup, key retention,
   restore/cutover and rollback steps. Verify the installed backend and Desktop
   payload agree after restart. Review pending schedules and uncertain writes
   before updates. Leave a usable review window only after its owner permits the
   coordinated update; do not replace another profile or production system.

## Failure and capability handling

Agents should complete the user's explicit request using available tools. A
missing capability needs a specific diagnosis and next step, not a blanket
refusal. Tool availability, account connection, user authorization and missing
implementation are separate cases. Continue independent permitted work.
See [agent assistance](AGENT_ASSISTANCE.md).

The CRM does not infer completion from elapsed time, a generated answer or a
successful save. Preserve the distinctions between local task state, saved
assignment, actual scheduled execution, agent-reported result, user review and
provider evidence. Unknown writes/sends must not be blindly retried under new
keys. A database rollback cannot undo an external message or a dispatched job.

## Integrations and permission gates

- **Email:** a separately configured host tool may support mail, while CRM's
  optional Gmail reader has its own grant and validation requirements. CRM does
  not yet supply a send adapter or automatic sent/received activity capture.
  Keep direct user review/approval of recipient, sending account and content.
  A draft or research request is not permission to send.
- **Attachments:** general managed uploads, file viewing and agent file access
  need their own storage, path/type/size, retention and access design. A source
  URL or note is not an uploaded file. Follow the [attachment plan](ATTACHMENTS_PLAN.md).
- **External services:** a new grant, credential, paid service or broader access
  needs the appropriate explicit approval. Do not configure these as a hidden
  prerequisite of an install, demo or scheduled task.
- **Public launch:** passing a local demo does not itself authorize a catalog PR,
  contest submission, public announcement or production migration.

## Acceptance record

For each candidate, retain its commit/tree, installed host revision, commands,
pass/fail/skip counts, synthetic versus real inputs, tested isolation modes,
cleanup evidence and remaining limits. Keep private profile paths, keys, account
identifiers and real customer records out of this repository. A failed check or
unverified recovery path remains a release gate rather than a marketing claim.
