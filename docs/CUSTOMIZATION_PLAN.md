# Custom fields and deal stages

Status: implemented, with verification evidence in [VERIFICATION.md](VERIFICATION.md).
This document describes the
bounded increment, not a production-readiness or feature-parity claim. The
[README roadmap](../README.md#development-roadmap) is the priority index for
future development.

## Familiar configuration, one shared contract

HubSpot properties and Salesforce fields distinguish a stable internal name from
the label people see. Deal stages also carry business meaning beyond their
position on a board. HermesCRM will use those patterns without treating
Salesforce Lead Status, Contact type and Opportunity Stage as interchangeable.

References:

- [HubSpot properties](https://knowledge.hubspot.com/properties/create-and-edit-properties)
- [HubSpot pipelines](https://knowledge.hubspot.com/object-settings/set-up-and-customize-pipelines)
- [Salesforce opportunity stages](https://trailhead.salesforce.com/content/learn/projects/customize-a-sales-path-for-your-team/customize-opportunity-stages)

The native UI, agent tools and report engine must use the same current-workspace
metadata and validation. The first release keeps one pipeline and the current
contacts/deals/tasks model. It does not introduce owners, teams, permissions,
provider accounts, imports or CRM synchronization.

## Deal stages

- Keep the existing six stable keys and all existing records.
- Allow additional stages with a display label, order, description, color,
  probability and explicit open/won/lost outcome.
- Keep internal key and outcome immutable. Changing a label must not change the
  meaning of saved filters or rewrite past outcomes.
- Use outcome, not a stage's spelling or board position, for open pipeline and
  won totals. Won probability is 100%; lost probability is 0%.
- Reject retirement of a stage still used by deals. Do not silently move records.
  Retain archived definitions for old filters and reports.
- Keep Contact type separate. A contact with multiple deals can have multiple
  linked stages; stage drilldowns count distinct contacts.

Multiple pipelines, bulk stage remapping and historical funnel analysis remain
future work. Existing current-state data must not be presented as reconstructed
stage history or actual close dates.

## Custom fields

Provide optional text, number, boolean, date and single-select fields on contacts,
deals and tasks. Definitions have a stable internal key, label, description,
display order and version. Limits and validation are explicit.

- Keep field key and type immutable. No automatic destructive type conversion.
- Preserve archived definitions and values. Archiving is not deletion or
  encryption.
- Preserve zero and false, distinguish absent values from explicit clearing, and
  reject unknown keys, invalid choices, invalid dates and non-finite numbers.
- Save values atomically with the record's optimistic version and audit action.
  Ordinary edits that omit custom values must leave them unchanged.
- Keep legacy idempotent create receipts valid. A retried create must not produce
  another record because metadata was added later.

Required fields, uniqueness, formulas, multi-select fields, attachments and
protected fields are outside this increment. These ordinary custom fields are
not a safe place for secrets or a new security boundary.

## Reports and agents

Custom fields participate in typed columns, filters, sorts, groups and applicable
aggregations. Stage labels are presentation; saved queries use stable keys.
Boolean, date and number operators must match their types. Correlated values
must not multiply joined records or distort chart totals.

Each report run must capture its schema and data consistently. Drilldowns retain
the exact typed predicates while remaining explicitly live queries. Archived
definitions must not silently disappear from saved reports. No model-generated
SQL or formulas are executed.

Schema tools use separate read/write toolsets. Existing scheduled assignment
allowlists do not gain schema-writing access. Profile selection remains owned by
Hermes, and native REST mutations require the captured workspace token.

## Data preservation and migration

Use additive, versioned metadata/value storage rather than changing existing
record columns. Initialize existing workspaces with the six original stages and
no custom field values. Validate schema compatibility; refuse unknown/newer or
malformed schemas rather than falling back or discarding data.

Test repeated/concurrent initialization, transaction rollback, stale versions,
idempotent retries, copied workspace identifiers and profile isolation on SQLite
and a disposable PostgreSQL database. Take a consistent backup before updating
an existing installation. This development task does not update the user's
currently open review app.

## Acceptance and release gates

1. Existing records, receipts, tasks, reports and charts retain their behavior.
2. Create/edit/archive controls are usable with keyboard and clearly explain
   dependencies; uncertain writes never silently become new requests.
3. Native forms, tools, filters and reports agree on custom types and stage
   outcomes, including null/false/zero and renamed/archived definitions.
4. SQLite and real disposable PostgreSQL contracts pass, including concurrency
   and rollback; actual host adapters and native component tests pass.
5. Independent review covers migration, data integrity, typed query safety,
   stale-profile routing, chart reconciliation and UI error recovery.
6. Reviewed publication follows the existing repository workflow. Physical native
   inspection is separate evidence and must not be claimed from component tests.

## Next priorities

After this increment, layered protection comes next, followed by import/export.
External CRM linking and synchronization are deferred. See the README for the
ordered roadmap and remaining agent, reporting and email work.
