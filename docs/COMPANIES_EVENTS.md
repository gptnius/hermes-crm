# Companies, Events and Activities

Companies are explicit organization records. Events are local appointment/call
records. Neither feature connects a calendar, sends a message, places a call or
starts an agent. Back up an existing datastore before updating the plugin.

## Create a Company and link contacts

1. Open **Companies**, then **Create Company**. Enter a name, optional domain and
   ordinary notes. Domain is unverified text, not proof of identity or ownership.
2. Choose **Create contact** from the Company, or select its exact identity in a
   new contact's optional **Primary Company** chooser. Contact and link save
   together. For an existing contact, choose **Change Company link** (standalone:
   **Link or unlink Company**) to change its relationship separately. Displayed
   IDs distinguish organizations with identical names; legacy company text is
   independent. See [creation and recovery](CONTEXTUAL_CREATION.md).
3. Click the linked Company to see its contacts, opportunities, tasks and Events.
   Related lists use server pagination and full counts rather than the 500-row
   legacy snapshot. Company archival preserves records/links; restore before
   creating new links to an archived Company.

Each contact has one primary Company in this version. Existing contact company
text remains unchanged and is not automatically linked, merged or converted.
The original text remains visible separately when appropriate. CSV import/export
continues to use that stored text; matching a Company name in CSV does not create
an association. Company/Event custom fields and CSV transfer are not implemented.
The Contacts and Pipeline **Legacy company text** filters search that original
text, not the linked Company name. Use the Company record's related lists or
typed report Company ID/name fields to work with the explicit group.

### What the associated records mean

- Contacts are explicitly linked.
- Opportunities follow their current contact.
- Tasks follow their direct contact, or their opportunity's contact when no
  direct contact is set. A missing direct target does not cause a guessed match.
- Events have their own explicit Company association, retained when a contact
  changes employers.
- Event-linked tasks also appear under the Event's Company. A task can therefore
  have different current-contact and Event Company context. Both bases are
  disclosed, and the task is counted once in each applicable Company view.

These are current relationship views, not historical employer attribution. No
name/domain similarity selects or merges records automatically.

## Plan an Event

Open **Events** and create an appointment or call. Provide a title, start and end,
IANA timezone (for example `America/New_York`), ordinary notes and any explicitly
selected Contact, opportunity or Company context. Associations are related
records, not verified attendees.
Alternatively, **Create Event** from a Company, Contact or opportunity prefills
only that exact source association. Review the other links deliberately; none
are inferred from the source's current relationships.

The interface provides date/time controls interpreted in the displayed timezone
and shows the resolved instant before saving. Nonexistent daylight-saving times
are rejected; repeated times require an explicit occurrence choice. New or changed
wall times are supported from 1900 through 2100. Unchanged saved originals outside
that range remain readable and keep their exact instant during unrelated edits.
The service and agent tools still require offset-aware timestamps, for example
`2026-11-09T14:00:00-05:00`. They store UTC instants and retain the named zone.
End must follow start. Recurring/all-day Events and invitations are not supported.

Statuses are explicit:

- **Scheduled:** the local plan is saved, not proof that anyone was notified.
- **Needs rescheduling:** record a reason; ordinary notes/title edits retain this
  status. Use Reschedule to review new times and return to Scheduled.
- **Completed:** explicitly record when the interaction happened and its outcome.
  This is self-reported, not verified attendance, delivery or call evidence.
- **Cancelled:** record a reason while keeping the original schedule/history.

Time passing never completes an Event. Past scheduled times remain scheduled.
A future claimed completion time is rejected. Reopen completed/cancelled Events
with a reason before correcting them. Revisions retain previous states/outcomes;
there is no Event delete operation in this slice.
Event revisions are available through the API; this increment does not include
a revision-history screen.

## Create and associate tasks

From an Event, choose **Create associated task** or **Link existing task**.
Review the exact Contact/opportunity context, title and timezone-aware due date.
Creating a task and its Event link is atomic. Existing tasks are selected by ID,
not name, and can have one Event link in this version. Unlink first to move a task
to another Event. Unlink confirmation reviews both the Event and task versions
and retains both records.

The task appears on its Event and the relevant Contact/Company lists. Opening it
uses the existing task record. In Hermes Desktop, that record provides the genuine
agent-assignment workflow; the standalone interface directs users to Hermes
Desktop for assignment actions. The business task does not gain a fictional assignee from its creator or the current Hermes
profile. A saved assignment, a registered job, a reported result and a reviewed
business outcome remain different states.

If you clear both the task's direct Contact and opportunity links, it retains
only its Event context. Related Contact/Company views can still show that task,
but current contact follow-up coverage counts direct/contact-through-opportunity
tasks, not Event-only context. Review the prefilled links deliberately; the app
does not silently change a saved report's coverage definition.

Creating/completing an Event does not create a scheduler job or complete its
tasks. Rescheduling or cancelling an Event also leaves associated tasks and
existing agent-work schedules unchanged; review those separately. Linking or
unlinking changes the task version, so a previously prepared
assignment may require fresh review. [Assignment instructions](ASSIGNMENT_UI.md)
describe the separate native scheduling confirmation.

In Hermes Desktop, **Back** returns through recently opened linked records with
fresh reads, while retaining the originating list context. Creating a follow-up
opens the confirmed new task with its parent reachable. Task details provide
**Complete** or **Reopen** separately from agent-work controls. Dirty native record
forms and Event forms offer **Keep editing** / **Discard changes** for in-app
cancellation; this is not durable draft storage across reload, host closure or
profile changes.

## Activities versus Record history

**Activities** shows completed local Events and non-voided, self-reported Contact
Log entries, with source and time basis. The timestamp is the claimed occurrence,
not when a record was edited. Scheduled/cancelled Events remain in the Events
list and are not presented as proof of an actual interaction.

**Record history** contains administrative changes. Existing API `/activity`
responses retain that audit meaning for compatibility. A CRM edit is not an
email, a phone call or a completed meeting. Optional Gmail metadata remains in
its separate, explicitly configured Email history surface and is never fetched
by opening a Company or Event.

Event completion does not manufacture a duplicate Contact Log entry. Existing
"Last logged contact" report fields retain their original Contact Log meaning.
A self-reported interaction and an Event about the same conversation remain
separate records unless explicitly managed by the user.

## Use agents and reports

New Company/Event tools use separate read/write permission sets. They can create
and update local records and associations. Default results omit ordinary notes
and outcome text; no protected data, mailbox credentials or provider capability
is exposed. Existing scheduled `crm_read` and internal-work allowlists are
unchanged. Agent text and record notes are untrusted data, not instructions.

Typed reports now support Companies and Events, plus distinct linked Company
ID/name fields on existing records. The old contact `company` report field still
means stored text. Group by stable Company ID when names are duplicated. Filters
apply before pagination, and chart drilldowns retain the same typed filters.
Reports aggregate UTC dates and current state, not historical stage/status.
Ordinary notes and free-text outcomes are not report fields.

A useful consultation-preparation workflow is to plan an Event, create a real
linked task, and review research in context. **The current scheduled assignment
lane only reads CRM data and reports results.** It does not silently gain web or
terminal access, write research notes, or attach files. Internet research,
scoped result-writing and record attachments need separate implementation and
verification. Do not present a copied prompt or saved task as completed research.

## Safe retries and storage

The first explicit Company/Event write creates an empty, versioned additive
schema. Existing records and create receipts are preserved; there is no automatic
backfill. Missing storage reads as empty, while partial/incompatible/newer storage
fails closed. SQLite is the default; PostgreSQL remains explicitly selected.

Writes carry stable retry keys and expected versions. An uncertain request must
be retried with its original key rather than recreated. Refresh and review a
changed record before applying a draft to a newer version. Profile/navigation
changes suppress stale results; they do not promise cancellation of a request
already accepted by the backend.

Ordinary notes, outcome text and revision copies are plaintext in the datastore.
Optional encrypted content exports include the explicit relationship tables for
the current scope, but are not a full backup or supported restore workflow.
Existing protected-note kinds are unchanged. See [protection](PROTECTION.md) and
[verification](VERIFICATION.md) for boundaries and tested scope.

## Not included

Multiple Company memberships/hierarchies, verified attendees, calendar sync,
recurrence, calling, email sending, delivery notifications, attachments, automatic
research execution, external CRM linking and production migration are not part
of this increment.
