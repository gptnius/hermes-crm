# Create records in their relationship context

Status: implemented and independently reviewed, with synthetic backend and
isolated-render checks. See [verification](VERIFICATION.md) for the exact scope
and remaining installed-host limits.

## Create a contact with an explicit Company

New contacts can have an optional **Primary Company**, selected by exact identity
from the paged Company chooser. A name or domain is not a merge key. Duplicate
Company names remain separate records, and choosing a Company does not copy its
name into the independent **Legacy company text** field.

From a Company, **Create contact** starts the ordinary contact form with that
Company selected. Review the contact fields, custom values and Company before
saving. The contact and optional Company link are committed together; there is
no successful contact followed by a silently failed second linking request.
The selected Company's version is checked so a rename or archive cannot silently
change the context that was reviewed. Restore an archived Company before creating
a new link to it.
If the Company changed, explicitly refresh/reselect and review its current
version before saving again; the application does not silently adopt it.

Creating a contact without a Primary Company remains valid. Existing contacts
keep their current edit workflow and separate **Change Company link** action.
This increment does not merge contacts, create Companies by name, alter CSV
matching, or backfill old company text. A new contact starts at version 1 whether
or not a Company was selected.

## Create an Event from a record

Use **Create Event** on a Company, Contact or opportunity. Only that selected
source is prefilled:

- Company supplies its exact Company ID.
- Contact supplies its exact Contact ID.
- Opportunity supplies its exact opportunity ID.

Other associations stay empty rather than being inferred from the contact's
current employer or an opportunity's contact. Review, clear or change each
association deliberately. Enter and review the Event title, times, timezone
and notes; opening the form does not save anything. The existing DST checks,
status rules and ordinary-note boundaries remain in effect.

The source record remains reachable after cancellation or confirmed creation.
A newly saved record opens from its confirmed ID with a fresh read; a cached
Company/contact row is never treated as current write authority. Profile or
workspace changes invalidate the form's old authority.

An Event is a local plan. Creation does not send invitations, schedule an agent,
sync a calendar, place a call or notify anyone. See
[Companies and Events](COMPANIES_EVENTS.md) for relationship semantics and the
separate [assignment workflow](ASSIGNMENT_UI.md).

## Failed or uncertain saves

Validation and known version conflicts preserve the draft for correction and
explicit re-review. When the outcome is uncertain, the original request and
retry key remain fixed. Retry that request rather than starting a replacement:
the original write may already have committed. A malformed or wrong-target
response is not success, and the client never falls back to an unlinked create
after an uncertain linked create.
Moving to another Company does not change the original retry destination or its
source context. A definitive retry rejection must return the original draft for
correction, rather than erase it or substitute the newer form's values.

The retained attempt is local to the current runtime/workspace; it is not durable
draft storage or an offline outbox. Closing the entire host/reloading can lose
unsaved local state. Inspect existing records before deliberately starting a new
operation after losing that context.

## Shared backend and agent contract

The additive `POST /relationship-contacts` operation accepts a workspace token,
stable idempotency key, contact `data`, nullable `company_id` and nullable
`expected_company_version`. A linked Company requires a strict positive integer
version; an unlinked contact cannot carry a Company version. The response contains
the created `contact` and exact `company_link` receipt from the same transaction.

`crm_contact_create_with_company` uses the same service through the existing
`crm_company_write` toolset. Its response omits ordinary notes and custom values
using explicit nested projections. This adds no scheduled-agent permission.
Old `crm_contact_create`, ordinary `/contacts` callers and their stored receipt
shapes remain unchanged. Existing report/Company grouping uses the explicit link
without a new report format or database migration.

Local retry receipts retain the created contact, including ordinary notes and
custom values. This is another ordinary local-data copy, not protected-note
encryption. The optional protected-note feature remains separate; omitting text
from the agent response does not remove it from the local receipt.

Historical same-key retries return the original receipt even if the Company is
later renamed or archived. A changed payload with the same key conflicts.
Validation, stale-version, scope and transactional failures must leave no partial
contact, Company link or retry receipt.

## Limits and next steps

- One optional primary Company per contact; no multiple-company role model.
- Existing contact company edits remain explicit separate link changes.
- No automatic Company/contact creation from Event participants or name matching.
- No provider integration, research execution or attachment storage is added.
- Broader paged task/deal selectors, agent-result acknowledgement and assignment
  simplification remain in the [workflow plan](WORKFLOW_REVIEW.md).
