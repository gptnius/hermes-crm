# Task dates and human accountability: implementation plan

Status: **first increment implemented; personal activation remains explicit**.
The original design below was based on source tree
`2801920b49b3851ed6eb6e1d4110c35972914587`. Read the current
[usage and limitations](TASK_OWNERSHIP.md); historical “current” and “proposed”
sections below describe that original baseline, not missing release features.

## Implemented decisions

- Task owners are optional human accountability labels by default, separate from
  assignment owners and agent executors. No default, backfill or required-owner
  policy is activated on installation.
- Scoped versioned settings may require owners on new tasks and explicit
  task-detail edits, including Complete/Reopen. Existing ownerless records stay
  readable but need deliberate ownership before those edits. Scheduler and
  relationship-only maintenance are exempt and never infer owners.
- Owner edits bump task versions without rewriting saved agent assignments.
  Current policy versions and explicit default labels are checked atomically.
- Native/standalone forms, Event tasks, API/tool writes, minimal projections,
  typed reports and scoped encrypted content export include ownership.
- Reads are non-initializing; additive schemas and original create receipts are
  preserved. Keyed writes have idempotent receipts; no background retry.
- The stronger older-writer gate proposed below is **not implemented**. Older
  binaries or direct SQL can bypass this application policy. Do not downgrade
  while relying on required ownership. It is not a database-wide guarantee.

Personal default identity, account-directory integration, bulk backfill and
restore remain separate choices/work. No policy is changed by this document.

## Current behavior

Every ordinary task already requires `due_at`. The database column is non-null;
`TaskInput` requires a timezone-aware timestamp and normalizes it to UTC
(`hermes_crm/domain.py`). The native editor requires a local date and time and
preserves an unchanged original timestamp (`desktop/plugin.js`). Event-created
tasks validate through the same `TaskInput` (`hermes_crm/events.py`). Base tool
schemas derive from the record model (`hermes_crm/plugin.py`).

This is a date-and-time requirement, not a date-only/all-day task model. Saving a
task does not itself schedule a reminder or agent execution. Do not invent
midnight deadlines or modify the due-time requirement as part of owner work.

Ordinary tasks currently have no stored human owner. The UI states that task
assignees are not stored and agent-work owners are separate. Execution/future
assignment `human_owner` is an accountability label, not an executor, identity
verification, permission grant, or task-level owner (`execution.py`,
`native_work.py`, `desktop/plugin.js`). Hermes is the agent executor; assignment
`run_at` is its requested run time, distinct from task business `due_at`.

## Proposed optional task-accountability feature

Add a human accountability field without requiring it universally. A
workspace/profile-scoped, versioned policy may explicitly enable required owners
and may explicitly configure a default owner label for personal use. Default
product behavior remains optional; configuring one workspace changes no other
workspace or profile.

A default must be visible in the task form and creation review. Never infer it
from the active profile name, operating-system account, task creator, linked
Contact, agent identity, or historical assignment. A label is not an account,
ACL, person lookup, or delegation instruction. Use a bounded human-readable
label initially; account/directory integration is separate work.

Suggested storage is an additive task-accountability table keyed by scope and
exact task ID, plus a scoped policy table and operation receipts. Validate
references to existing tasks and policy versions. Keep ordinary task identity,
relationships, due dates, and assignment storage intact. Final schema and
version-bumping semantics need approval before implementation.

A task owner change should participate in the reviewed task version contract so
frozen assignments can be recognized as based on an earlier task. It must not
rewrite an assignment's saved `human_owner`, execution state, or frozen snapshot.
Assignment UI may offer the current task owner as a visible suggestion, requiring
review rather than silently copying or synchronizing it.

## Interim option using existing customization

A Task text custom field labeled Owner can store a label today after explicit
schema configuration. It is an interim workflow convention, not built-in task
assignment. Existing custom fields support neither requiredness nor defaults
(`hermes_crm/customization.py`). Default model-facing projections omit custom
values; explicit ordinary-field selection can retrieve known fields
(`hermes_crm/agent_read_policy.py`). Do not claim this workaround enforces owner
coverage or makes Owner visible in every task/tool/report surface.

Do not automatically convert a similarly named custom field into the proposed
accountability field. Any later import needs a reviewed mapping, provenance,
conflict handling, and a reversible preview.

## Decisions deliberately left open

Before enabling a personal policy, decide:

- Exact default human owner label, if any. No identity is assumed here.
- User-facing terminology: prefer “Human owner” or “Accountable person” and
  separately show “Agent executor.” Do not overload “assignee” to mean both.
- Policy for editing existing ownerless tasks: reject edits until an owner is
  selected, or permit explicit grandfathering with a visible missing-owner
  warning. Specify completion and due-date changes as well as metadata edits.
- Backfill: leave existing tasks unchanged, or review an explicit selected set
  and owner mapping. Never silently assign every legacy task to the default.
- Whether changing the default affects only new tasks (recommended) and whether
  clearing an owner is permitted while a required-owner policy is enabled.
- Policy scope and exceptions for historical/done tasks. Do not retroactively
  imply that an owner accepted responsibility for historical work.

Until those decisions are made, no policy/default or backfill should be enabled.

## Enforcement and UI contract

Enforce requiredness at a shared service/storage boundary, not only in the UI.
Cover base create/update, Event task creation, native and standalone routes,
agent tools, and any future import path. A missing owner under enabled policy
must produce a useful validation error, not a guessed owner. Reject whitespace-
only labels and stale policy versions. A policy change during a form or tool
operation requires fresh review, not silent application of a different default.

Show human owner in task editor, detail, list/upcoming views, relevant reports,
and explicitly reviewed tool projections. Report “Owner missing” truthfully for
legacy records. Keep task owner, assignment owner, and agent executor separate
where they differ. Task owner is ordinary potentially personal metadata; do not
include it in unrelated exports or external messages without an intentional
contract update.

Store policy/owner changes with version checks, idempotency, and small audit
records. If a write outcome is uncertain, inspect the original receipt before
retrying or creating another operation. Record default application explicitly so
reviewers can distinguish a selected owner from a configured default.

## Migration, compatibility, and rollback

Use additive owned tables and explicit version markers; no destructive change to
legacy tasks. Reads must not enable the feature or initialize policy. Refuse
partial/incompatible schemas. Activation is scoped and explicit. Do not treat
missing tables as a globally required policy.

Before enabling required owners, verify every supported writer uses enforcement.
Older writers must be gated or rejected rather than silently bypassing policy.
Rollback should disable new configuration/writes while preserving labels,
policy history, receipts, and legacy records; it must not drop tables or silently
turn off a user's required-owner guarantee while allowing unenforced writes.
Document the compatibility behavior before rollout.

Exports use explicit registries: add approved owner/policy coverage deliberately
and label any exclusions. Existing encrypted content export is not a complete
backup and has no current restore workflow. This feature does not change that.

## Acceptance tests

- Existing due-time tests remain: missing/invalid/naive timestamps rejected;
  timezone normalization and unchanged timestamp preservation remain intact.
- Optional default product behavior; policy enabled in one workspace/profile
  only; no inference from profile/creator/Contact/assignment; no universal
  requirement or owner backfill from migration/read operations.
- Explicit default application, no silent default on stale form, clearing-owner
  behavior, whitespace/length validation, policy races and optimistic conflicts.
- Identical behavior on SQLite and PostgreSQL through every task write entry
  point, including Event task creation and standalone UI/API/tool adapters.
- Selected legacy policy enforced consistently; legacy ownerless records visible;
  reviewed backfill, if later implemented, previews exact IDs and can be audited.
- Task-owner changes do not execute agents, schedule jobs, send messages, rewrite
  assignment snapshots, or grant permissions. Historical `human_owner` remains.
- Default agent projection and explicit read behavior deliberate; reports,
  detail/upcoming views, export allowlists, and audit display truthful ownership.
- Schema/read-only checks, cross-scope references, retries, uncertain operations,
  stale policy/task versions, rollback compatibility, and preserved data.

Recommended order: approve terminology and personal policy choices, implement
optional scoped storage and shared enforcement, update all task surfaces, test
both backends and older-writer behavior, then explicitly enable a personal policy.
