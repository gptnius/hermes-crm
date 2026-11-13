# Companies, Events and relationship history

Status: implemented for a local workspace, with the documented limits. See the
[verification report](VERIFICATION.md) for actual tests and remaining gates.
This plan adds genuine Company groups and local Events without rewriting
existing records or claiming an external communication/calendar integration.

## Product contract

- **Company** is an explicit organization record with a stable ID. One reviewed
  primary Company link per contact; duplicate names/domains remain distinct.
- **Activities** is relationship history: local Events and self-reported logged
  interactions. Planning an Event and recording that it happened are different.
- **Events** are local appointments/calls with scheduled/needs-rescheduling/completed/cancelled
  states. Saving does not invite anyone, place a call, send a reminder, create a
  scheduler job or synchronize a calendar.
- **Record history** is the administrative audit trail. Existing `/activity`
  endpoints and stored audit rows retain their meaning for compatibility.

HubSpot's company/contact associations and record layout and Salesforce's
account/activity concepts are references, not a claim of equivalent features:
[HubSpot records](https://knowledge.hubspot.com/records/work-with-records),
[Salesforce opportunity stages](https://trailhead.salesforce.com/content/learn/projects/customize-a-sales-path-for-your-team/customize-opportunity-stages).

## Storage and compatibility

A private relationship metadata registry owns only new tables:
`crm_companies`, `crm_contact_companies`, `crm_events`, `crm_event_revisions`,
`crm_event_tasks`,
`crm_relationship_operations` and `crm_relationship_schema`. An explicit
`OWNED_TABLES` tuple excludes any legacy table clones used solely for foreign-key
resolution. Do not add new entity types to core `TABLES`, `MODELS` or metadata.

The new schema initializes empty on the first explicit relationship write. An
absent store reads as empty/null; partial, incompatible or newer schemas fail
closed rather than silently returning an empty success. No read creates the
schema or workspace token. A versioned marker, reflected columns/keys/foreign
keys and serialized initialization protect both SQLite and PostgreSQL upgrades.

Rows/links/revisions/receipts use the existing workspace-and-profile scope.
Writes lock in a consistent order, compare strict versions and commit data,
audit/revision and retry receipt together. Replaying the same key/payload returns
the original result before stale-version checks; changed payloads conflict.

Existing contact `company` text, core records, custom fields, CSV behavior,
report definitions and old idempotency receipts remain unchanged. There is no
name/domain matching, automatic Company creation or contact backfill. Old
clients changing company text cannot change an explicit relationship.

## Companies

Company fields: ID/version/timestamps, required nonunique name, optional
nonunique domain, ordinary notes and nullable archive timestamp. Domain is
unverified text, not proof of ownership. No hard deletion or Company custom
fields in this slice.

Methods: list/get/create/update/archive/restore; exact-ID contact link/unlink.
The additive [contextual contact-create operation](CONTEXTUAL_CREATION.md) saves
a contact and optional version-reviewed Company link in one transaction using
the existing tables and scoped retry receipts. Old core create receipts remain
unchanged; Company names are never inferred as links.
Link changes require the contact's expected version and a stable retry key,
then atomically bump its version/timestamp and add audit history. Linking an
archived Company is rejected; existing archived links remain visible. Setting
the same link again is a no-op with a receipt. No legacy text is overwritten.

Company details provide paged associated contacts, opportunities, tasks and
Events with full server totals. Membership is calculated before pagination:

- Contacts use their explicit primary Company link.
- Opportunities use their current contact.
- Tasks use their explicit contact, or their deal's contact only when the direct
  contact ID is null. A dangling direct ID does not cause a guessed fallback.
- Events use their own explicit Company ID, retained across contact moves.
- A task explicitly linked to an Event also appears under that Event’s Company.
  The current-contact and explicit-Event bases are labeled and deduplicated by
  task ID; neither association silently rewrites the other.

These are current relationship rollups, not historical Company ownership.
Distinct identities and stable sort ties prevent join multiplication. Linked
Company names are clickable. Unlinked legacy text remains visible as unlinked;
renaming a Company changes its displayed name, not legacy contact text.

## Local Events

Create/update fields: title, kind (`appointment`/`call`), explicit-offset start
and end, valid IANA display timezone, optional exact contact/deal/Company IDs,
and ordinary notes. Times normalize to UTC and end must follow start. Related
records are context, not verified attendees. No recurrence/all-day semantics.

Create is always scheduled. Time passing does not complete the Event. A past
scheduled time remains visibly scheduled. General edits apply only to scheduled or needs-rescheduling
Events; terminal records first require explicit reopening with a reason. Marking
Needs rescheduling is an explicit reasoned action, and rescheduling reviews the
new times before restoring scheduled status.

Completion requires a current version, a nonfuture claimed occurrence time and
an outcome summary. The service records `source=local`,
`outcome_provenance=self_reported`, the claimed occurrence and separate recording
time. Cancellation/reopening is explicit and versioned. Immutable revision
snapshots preserve earlier states and corrections. There is no delete.

Completion neither completes a task nor creates a Contact Log entry. Existing
`last_logged_contact_at` retains its original meaning. Ordinary notes/outcomes
and revision copies are plaintext unless the datastore is protected elsewhere;
these are not protected-note fields.

## Associated tasks and the research workflow

One explicit Event link per task is stored separately from legacy task columns.
Creating a task from an Event is atomic: validate the reviewed Event version,
create a normal core task through existing validation, save its Event link,
and commit audit/revision/retry evidence together. Existing tasks can be linked
or unlinked with expected task/Event versions. A contact/deal prefill is shown
and reviewed rather than inferred after save. Existing task creation receipts
and task custom fields are preserved.

Event task pages and Company task rollups use server pagination and exact totals.
A task may have current-contact context different from its Event's explicit
Company; display both bases rather than merging organizations or hiding the task.
Linking does not assign an agent, create a scheduler job or complete the task.
Users can open the normal task record and use the existing genuine assignment
workflow. Association changes must invalidate stale task-based intents by
updating the task version.

The proposed consultation-preparation demo requires a separately verified research
capability and result-writing policy. Current scheduled assignments are restricted
to CRM reads/reporting; they cannot silently gain web/terminal access, write notes
or attach files. This increment provides real Event notes, tasks and links, not
fictional research execution. Files, scoped research tools and approved result
promotion remain separate implementation and verification gates.

## Shared service and adapters

Modules: `relationship_schema.py`, `relationship_store.py`, `companies.py`,
`events.py`, `relationship_queries.py`, `relationship_api.py` and
`relationship_tools.py`. Native/standalone/tools use the same validation.

Common pages: `{items,total,limit,offset}`, limit 1–100 (default 50), with stable
ID tie ordering. Read methods accept an internal connection for coherent
snapshots. Public callers cannot provide scope, actor or provider provenance.

Routes are registered before legacy generic routes:

- `/companies`, `/companies/{id}`, `/companies/{id}/archive|restore`,
  `/companies/{id}/records/{kind}`.
- `/contacts/{id}/company` for explicit relationship read/link/unlink.
- `/events`, `/events/{id}`, `/events/{id}/complete|cancel|reopen|needs-rescheduling|reschedule`,
  `/events/{id}/revisions`, `/events/{id}/tasks`, `/tasks/{id}/event` and
  `/tasks/{id}/event/unlink`.
- `/relationship-activities` and `/record-history`.

Native writes require the captured workspace token and stable idempotency key;
updates/status changes require expected versions. Standalone uses the same
contract with its fixed local workspace and existing same-origin protection.
Company detail returns `{company,counts,relationship_semantics}`. Existing core
record reads may add current Company projection fields; raw mutation records
and receipt hashes must retain their existing shapes.

Relationship history uses source-qualified IDs, explicit provenance, timestamp
basis and server pagination. Completed Events use their claimed occurrence;
logged interactions use `happened_at`. Planned/cancelled Events remain available
in Events, not represented as verified communications. Company interaction
membership is based on the currently linked contact and disclosed as such.

## Reports, agents and protection

Typed reports add Companies and Events through a report-local source registry,
not core table registration. Absent stores provide typed zero-row relations.
New Company ID/name fields are distinct from the old stored company-text field.
Reports count each record once, preserve exact drilldown filters and aggregate
UTC dates. Current status/stage is not historical status. Notes/outcome text are
not report fields. Existing custom-field report behavior is unchanged.

New Company/Event tools use separate read/write toolsets and explicit minimized
projections. Existing scheduled `crm_read` and execution allowlists remain
unchanged. No scheduler, mailbox, terminal or provider capability is introduced.
Existing base record projections continue to omit newly added metadata unless
separately reviewed.

Encrypted content export explicitly adds only new owned tables and current-scope
rows plus the schema marker. Do not export metadata clones or unrelated tables.
Old envelopes remain readable; new authenticated round-trip tests are required.
No new key configuration, protected-note kinds or restore claim is added.

## UI and verification

Native and standalone provide Company list/detail/forms/linking and Event
list/detail/create/edit/complete/cancel/reopen/reschedule, plus associated tasks. Preserve captured workspace,
request-generation, focus/cancel and stale-response guards. Select exact IDs,
show distinguishing context for duplicate names, and never select the first
name match automatically. Forms show times and timezone together; no silent
browser-timezone reinterpretation or minute-rounding of unchanged timestamps.

Activities, Events and Record history have distinct labels and sources. Contact
and Company details show related Events/interaction history separately from
administrative changes. This core edition has no provider integration; these pages never fetch mail.

Acceptance: legacy row/receipt preservation, concurrent upgrade, partial/newer
schema rejection, duplicate identities, archive/restore, link/relink/unlink,
strict versions/idempotent retries/rollback, scope isolation, task/Event link retries and atomic creation, dangling records,
more than 500 relationships, distinct full counts, DST/offset validation, future
completion rejection, revision retention, no side effects, old CSV/report
compatibility, agent minimization and encrypted-export round trips. Run SQLite,
disposable PostgreSQL, adapter/tool/report tests, native/standalone lifecycle
checks and real isolated light/dark rendering at wide/narrow widths. State
physical-host/provider/accessibility limitations honestly.

## Explicit follow-on scope

Multiple Company associations/hierarchies, custom fields on these new entities,
Company/Event CSV transfer, reviewed legacy relationship import, external CRM
linking, recurrence, attendees/invitations, calendar sync, verified calling,
notification delivery, and automatic inbound/outbound communication history
remain separate development. No live migration or production configuration is
part of this increment.
