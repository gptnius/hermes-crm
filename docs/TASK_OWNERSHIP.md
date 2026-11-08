# Task dates and human accountability

Tasks require a timezone-aware due date and time. They can now also record a
**Task owner (human)**: a short accountability label, separate from the Hermes
agent executor and from each saved agent assignment's human owner. An owner label
is not a verified account, permission grant, notification destination or proof
that a person accepted the work.

The default policy is **optional owners, no default label**. Installing or reading
this feature does not assign owners, enable required ownership, change existing
tasks or schedule work. No personal default is selected for you.

## Create and review tasks

1. Create a task from Tasks or a related Event. Review the title, exact related
   records, due date/time and priority as usual.
2. Enter **Task owner (human)**, or deliberately choose the visible configured
   default when one exists. New-task forms may visibly suggest that default.
   Existing ownerless tasks are not silently assigned to it.
3. Save the task. The form's reviewed owner-policy version is checked along with
   the task version. If either changed, review the current values before making
   a corrected request.
4. Review the owner in task details, lists, the Upcoming Tasks card or related
   Event tasks. **Not recorded** means this task has no saved human owner; it does
   not prove that nobody is responsible.

A task's due time is its business deadline. An assignment's requested run time
is when Hermes is asked to work. Saving a task or owner does not create an
assignment, start a model, schedule a job, send a message or move either time.
Changing an owner increments the task version, so a previously frozen assignment
can become stale. Its saved owner and snapshot remain unchanged.

## Configure a workspace policy

In native Desktop, open **Tasks → Task ownership**. The standalone surface uses
**Task ownership policy**. Review the current version and choose:

- Whether to require an owner for new tasks and task-detail edits.
- An optional default human owner label, up to 160 characters. Clear the field
  to remove the default for future choices.

The native drawer has a separate **Review changes → Save reviewed policy** step.
These settings apply to the current workspace/profile only. They do not infer
an identity from your operating system, Hermes profile, task creator, linked
Contact or past assignment.

When required ownership is enabled, the supported task create/update paths,
including agent tools and Event-created tasks, require an owner. An existing
ownerless task remains readable but needs a deliberate owner choice before a
task-detail edit, Complete or Reopen. This is not retroactive backfilling.

Scheduler bookkeeping and relationship-only internal maintenance are exempt:
they do not select, clear or apply a default owner. The policy is a supported
application-write rule, **not a database-wide constraint, access-control system
or enforcement against older binaries/direct SQL**. Do not downgrade a writer
while relying on this policy. Account-directory ownership and bulk backfill are
not included.

## Agent tools and reports

`crm_task_owner_policy` reads the current policy. There is no agent policy-change
tool. Task create/update tools accept `owner_label`, `owner_policy_version` and
`owner_source` (`explicit` or `default`). A default selection must supply the exact
reviewed label and policy version; the service never guesses one. After policy
configuration, even an optional policy requires the current version on explicit
task writes. Re-read after a policy conflict instead of reusing a stale default.

The minimal task projection includes the human owner label. Owner provenance is
not added to every minimal projection. Task lists support missing/present and
exact-label filters; typed task reports can select, filter and sort `owner_label`.
An older custom field named Owner remains separate (`custom.owner_label` if that
is its key). No custom-field values are automatically converted.

The policy-read tool belongs to the separate record-detail permission set.
Existing frozen scheduled assignments gain no tools or permissions. An owner
label never authorizes an agent to contact that person.

## Writes, retries and retention

Policy writes and task writes supplied with idempotency keys use version checks
and durable receipts. The UI supplies keys; API/tool task keys remain optional
for compatibility. An uncertain unkeyed request has no receipt replay guarantee:
inspect the current record before deciding what to do, rather than blindly
repeating it. Repeat a keyed uncertain request only with its original key and
reviewed body. A replay may
return the original successful receipt even if the policy changed afterward;
that is evidence of the earlier operation, not an instruction to apply old
values again. A definitive conflict needs fresh review and a new corrected
operation. Do not treat a timeout or malformed receipt as success.

In-app recovery retains pending/rejected drafts within the current session and
authority; it is not a durable offline draft store. Closing the application can
lose unsaved local drafts. Server receipts persist. No background retry or
automatic submission is added.

Owner labels, provenance, policy and receipts use additive owned tables. Legacy
records and historical owner-free create receipts remain compatible. Reads do
not initialize the new schema. Partial or unsupported owned schemas are refused
rather than silently repaired.

The encrypted **CRM content export** registry includes the scoped owner, policy
and receipt tables. That export still is not a complete backup or tested restore
workflow. Labels and receipts are ordinary CRM data before an explicitly
configured encrypted export; this feature does not encrypt the live database.
See [protection boundaries](PROTECTION.md) and [verification](VERIFICATION.md).

## Further work

Account/directory identities, an explicitly reviewed bulk backfill, richer owner
views, cross-device drafts and a tested restore workflow remain separate work.
The original [ownership plan](TASK_OWNERSHIP_PLAN.md) records the design and the
implementation decisions. Choosing your personal default or enabling required
ownership is a separate explicit settings action, not part of installation.
