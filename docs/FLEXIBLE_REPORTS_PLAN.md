# Flexible reports and main-dashboard cards

Status: implemented in isolated source, independently reviewed and tested; native
physical visual/layout QA remains a separate gate. This is the development plan
for the explicitly requested increment. This
supersedes the earlier contest-scope decision to defer custom report building.
It is a bounded native CRM reporting system, not HubSpot/Salesforce feature parity.
No account connection, production migration, message, grant or paid service is
part of this work.

## Outcome

Humans and Hermes agents create and edit the same persistent report definition.
A saved report can feed a metric, table, bar, line or donut card on the main
CRM dashboard. Users choose fields, combine typed filters, sort rows, group and
summarize data, preview before saving and drill into contributing records.
Existing preset charts and ordinary CRM views remain usable.

## Shared contract

A versioned definition identifies contacts, deals or tasks; selected columns;
bounded ALL/ANY conditions; sort fields/directions; optional grouping and measure;
and explicit UTC date semantics. The server catalog describes allowed fields,
operators, units and supported uses. No model-generated SQL, executable formulas,
network addresses or arbitrary joins are accepted.

Limits: twenty columns, thirty-two conditions, nesting depth three, one hundred
membership values, three sorts, one grouping, one measure and one hundred rows
per page. Use bound SQL expressions with filters before pagination, SQL counts
and aggregates, explicit null ordering and stable ID tie-breakers. Never feed
reports from the legacy 500-row lists or load the full workspace into memory.

Contact linked stages remain a set. They support membership filters but no
invented primary stage or scalar sort/group. Correlated EXISTS/aggregate queries
prevent duplicate contacts/tasks when there are several deals or both direct
and deal-based links. Monetary fields use integer USD cents with explicit units.

## Semantics that remain visible

- **Next follow-up:** earliest due time among actual open linked tasks, including
  overdue tasks. A saved task is not proof an agent will execute it.
- **Last logged contact:** maximum active, explicitly authored touchpoint time.
  Its provenance is self-reported by the logging human/agent, not authenticated
  delivery. Unknown means no contact was logged, not that no contact occurred.
- **Leads created per day:** contacts currently classified as lead, grouped by
  contact creation day in UTC. This is not historical stage membership.
- **Closed Won:** current deals in Won, with count/value. The existing expected
  close date is not an observed win time. No historical conversion or win-event
  trend is promised without typed transition history.
- Ordinary CRM edit activity and optional Gmail observations are separate. No
  audit edit or SENT label is silently converted to a contact event.

A new append-only authored-touchpoint ledger records contact, timezone-aware
happened_at, kind/direction, bounded summary, trusted actor and self_reported
provenance. Future contact claims are rejected. Explicit versioned voiding
preserves erroneous evidence while excluding it from Last logged contact.
Its summaries never enter general report projections or legacy crm_read.

## Reports, charts and persistence

Saved reports hold normalized definitions and optimistic versions, separate from
visualization and layout. A dashboard holds at most twelve ordered cards that
reference report ID/version. Changing the saved report does not silently change
a pinned chart: missing, archived and outdated references remain visible and
require explicit resolution. Archived reports are recoverable, not purged.
All writes use stable idempotency keys and version checks.

Use one profile/workspace-scoped dashboard initially. Per-report filters are
supported; no global dashboard filter is shown unless its mapping is explicit
for every affected card. Excess groups are labelled truncated; a partial donut
must not imply a complete 100 percent distribution. Zero, empty and unknown
buckets remain distinct.

The engine returns canonical detail definitions for each bucket. A click preserves
all report predicates, the exact bucket and the frozen evaluation instant for
relative/overdue comparisons. It reruns **live data** and displays its new
observation time. Timestamps do not freeze later edits or create historical row
membership; unchanged-data chart/detail reconciliation is tested explicitly.

## Native and agent boundaries

New authenticated /analytics routes and dedicated crm_reports/crm_report_write
agent toolsets share the engine and saved definitions. Authored interaction
read/write tools have separate toolsets. Existing crm_read, assigned-job tool
inventories, snapshot responses and Gmail permissions/data remain unchanged.
No scheduled job gains the new tools merely because reports are installed.

The native builder uses labels and typed controls, an explicit Preview and Save,
responsive tables, keyboard-operable chart segments/points and summaries. It
reuses the monotonic route client and captured workspace tokens, rejecting stale
responses and form actions after profile/connection changes. Components are
inlined deterministically because the pinned host permits only SDK/React imports.

## Delivery sequence and verification

1. Implement catalog, strict definition validation and portable SQL compiler.
2. Add separate lazy report/dashboard/touchpoint tables, optimistic/idempotent
   writes and safe recovery/archive behavior without changing existing tables.
3. Wire authenticated REST and dedicated validated native tool handlers.
4. Add the native report editor, saved list, main-dashboard cards, live drilldown
   tables and explicit authored-contact logging.
5. Verify SQLite and real disposable PostgreSQL, >500 records, relationship
   deduplication, UTC/null boundaries, literal wildcard searches, unsupported
   definitions, pagination, aggregates, drilldowns, concurrent saves and profile
   isolation. Test UI stale/repeated/cancelled actions and accessibility semantics.
6. Independent review, source/privacy/license check, clean-export tests and a
   reviewed patch. Native physical visual QA is a separate gate; no modification
   to an already open review app or production system is authorized here.

References guiding workflow, not copied assets:
- https://knowledge.hubspot.com/reports/create-reports-using-ai
- https://knowledge.hubspot.com/ai/generate-data-visualizations-with-breeze-assistant
- https://knowledge.hubspot.com/records/create-and-manage-saved-views
- https://trailhead.salesforce.com/content/learn/modules/high-velocity-sales/get-to-know-the-console-and-cadences
