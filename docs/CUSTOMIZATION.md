# Custom fields and deal stages

HermesCRM uses one workspace catalog for native forms, agent tools, filters and
reports. Open **Customize** in the native workspace to manage it. This is a
single-local-user feature, not a new administrator role or access-control layer.
No model call or external service is required.

## Deal stages

The existing Lead, Qualified, Proposal, Negotiation, Won and Lost stages are
preserved. Add a stage with a stable internal key, label, order, color,
description, probability and **Open**, **Won** or **Lost** outcome.

- The label can change; the key and outcome cannot. Use a new stage when the
  business meaning changes, then explicitly move the intended deals.
- Stage order controls display. It does not infer outcome or historical funnel
  progression.
- Won stages use 100% probability; Lost stages use 0%. Open stages have a default
  probability; a particular deal can retain an explicit override.
- Changing a stage's default probability does not recalculate existing deals.
  New deals and stage moves without an explicit probability use the default.
- Archive only an unused stage. A stage still referenced by deals is rejected,
  and the default `lead` stage cannot be archived. No automatic remapping occurs.
- Archived stage definitions remain readable for saved filters. Restore a stage
  to make it selectable again.

Open pipeline and won totals use the configured outcome, not the key's spelling.
For example, a new `contract_paid` stage with Won outcome contributes to won
value. A contact with several deals may appear in several stage reports; each
report counts that contact once. **Contact type** remains the separate
lead/customer/partner classification.

## Custom fields

Choose Contacts, Deals or Tasks, then add a field with its stable key, display
label, description, order and type:

- **Text:** up to 10,000 characters.
- **Number:** a finite JSON number between -1,000,000,000,000,000 and
  1,000,000,000,000,000. This has no implicit currency unit; deal value still uses
  integer USD cents. Floating-point number behavior applies to this field type.
- **Boolean:** true or false. False is a value, not missing data.
- **Date:** a calendar date in YYYY-MM-DD form, not a timestamp or scheduled job.
- **Single-select:** one of the configured string choices. Choices can be added;
  existing choices cannot be removed or silently renamed.

Keys begin with a lowercase letter and contain lowercase letters, digits or
underscores. Field keys are at most 64 characters; stage keys at most 20.
Labels may be changed without changing stable identities. Types cannot be
converted. Each kind supports at most 100 definitions, including archived ones;
a single-select supports at most 100 choices. The current report/card limits
still apply independently.

The native create/edit drawer displays active fields. Record details retain
archived values. Leaving a field unchanged preserves it; explicitly clearing a
field removes that value. Ordinary record updates that omit `custom_fields`
preserve all custom values. Zero and false remain distinct from empty values.

Archiving hides a field from editing, but keeps its definition and values for
reading and reports. Restore it before changing or clearing its values. There is
no field deletion, required-field enforcement, uniqueness, formula, multi-select
or automatic data conversion in this increment.

These are ordinary stored CRM fields, **not encrypted or protected fields**.
Do not use them for passwords, API keys or other secrets. Layered protection is
the next development priority in the [README roadmap](../README.md#development-roadmap).

## Reports and agents

The report catalog exposes custom fields as `custom.<key>` with their current
label, type and allowed operators. Numbers can use applicable numeric measures;
booleans use true/false values; date filters use calendar dates. Archived fields
remain available so saved reports do not silently lose their meaning.

Deal reports also expose `stage_outcome`. Use it for all Won stages. An older
report explicitly filtering `stage = won` continues to mean that particular
stable stage, not every stage with Won outcome. Current labels are presentation
metadata; definitions retain stable keys. This is current-state reporting, not a
historical funnel or a verified actual close date.

Example agent requests:

- “Read the CRM customization catalog. Add a contact single-select field named
  Customer segment, with key customer_segment and choices Small business and
  Enterprise. Use a stable request key.”
- “Create an Open deal stage named Discovery call, with key discovery_call and
  default probability 30%.”
- “Read this contact's latest version, then set customer_segment to Enterprise.”
- “Build a contact report grouped by Customer segment and show the records
  behind each group.”

Five schema tools use separate `crm_schema_read` and `crm_schema_write` toolsets.
Definition updates require the current version, and creates use stable
idempotency keys. Record tools accept `custom_fields`; explicit JSON null clears
one named value. Scheduled assignment toolsets are unchanged and do not gain
schema-writing access. Text labels/descriptions remain data, not instructions.

## Saving, errors and updates

A stale version requires refreshing and reopening the definition before editing
again. If a write response is uncertain, retain the original request and use the
provided recovery action. Do not create a different request to guess whether the
first one saved. A confirmed save followed by failed refresh is shown separately;
refresh the catalog rather than repeat the write.

The upgrade adds versioned catalog/value tables and initializes the six original
stages without altering existing record columns or old idempotency receipts.
Unknown/newer or incompatible customization schemas fail closed. Take a
consistent database backup before updating an installed copy. No automatic
backup, rollback UI, production deployment or user-profile migration is included.
Keep backend and Desktop components on the same reviewed revision. Older plugin
code does not understand custom stages or values; do not assume a downgrade can
display or edit them correctly. Recovery from a backup is a separate deliberate
operation, not an automatic rollback supplied here.

Native Desktop is the editing experience. The smaller standalone demo displays
configured stages and retained custom values, and preserves them during ordinary
record edits; it does not provide the customization editor or custom-value form
controls. Its local API accepts validated values.

See [implementation plan](CUSTOMIZATION_PLAN.md) and
[verification evidence](VERIFICATION.md) for actual tested scope and open gates.
