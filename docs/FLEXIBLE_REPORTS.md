# Saved reports and dashboard cards

The native CRM dashboard includes a typed report builder. Hermes agents use the
same definitions, saved reports and dashboard, through separate reporting tools.
The standalone local view retains its earlier preset views; this builder is native-only.

## Human workflow

1. On the main dashboard choose **Build a report**, or start with Leads and
   follow-ups, Leads created per UTC day, or Current closed won deals.
2. Choose Contacts, Deals or Tasks. Select columns, combine ALL/ANY conditions,
   choose up to three sorts, and optionally group and summarize a numeric field.
3. **Preview live**. Review the selected fields, units, conditions and results.
   Save the report, then preview the saved version before adding a dashboard card.
4. Choose table, metric, bar, line or donut. Cards can be reordered or removed;
   removing a card does not delete its saved report. Reports can be archived and
   restored through the saved-report list.
5. Run a card to refresh its data. Click a chart segment, point, metric or its
   accompanying summary to open the contributing records. Keyboard controls and
   exact values accompany the visual charts.

Cards pin an explicit report version. Editing a report marks existing cards
outdated; review its latest definition and explicitly adopt it. Archived or
missing reports remain visible as unavailable references. There is one custom
ordered dashboard per workspace/profile, with at most twelve cards.

A dashboard card is not an automatic monitor. It runs on request, with its own
saved filters. There is no dashboard-wide filter that silently skips cards.

## Agent workflow

Ask the agent to describe fields using `crm_report_catalog`, preview a typed
query with `crm_report_run`, save it with `crm_report_create`, and add its exact
ID/version to `crm_dashboard_save`. Updates require the current optimistic
version and a stable request key. Both adapters validate the actual arguments,
not just the advertised tool schema. No SQL, executable formula or arbitrary
join is accepted.

Dedicated toolsets are `crm_reports`, `crm_report_write`,
`crm_interaction_read` and `crm_interaction_write`. Existing scheduled agents do
not gain these capabilities: their fixed CRM read/report inventory is unchanged.
Saving a report or dashboard never schedules work, calls a model or contacts a
provider.

Example request: “Preview lead contacts with their linked stages, last logged
contact and next follow-up, sorted by next follow-up. Save the report after I
review it, and add it as a table on my dashboard.” Ordinary host permissions
still apply. There is no hidden report-authoring model or API key.

## Definitions and honest interpretation

- Contacts can have several deals in different **Stages**. Linked stages are a
  set with membership filters, not a guessed primary stage. Contact type is the
  separate lead/customer/partner classification.
- Counts and aggregates use one row per selected record. Contact counts do not
  multiply when a contact has several deals/tasks. A deal-value chart drills into
  contributing deals, not a misleading list of distinct contacts.
- **Last logged contact** is the latest active self-reported contact event. An
  empty value means no event was logged, not proof that contact never happened.
  CRM edits and optional Gmail observations are not automatically contact events.
- **Next follow-up** is the earliest due time among open linked tasks, including
  overdue tasks. It is not evidence of execution or a never-missed guarantee.
- **Leads created per UTC day** selects contacts currently classified as leads
  and groups their creation dates. It does not reconstruct historical lead state.
- **Current closed won deals** selects stages with current Won outcome. An older
  saved `stage = won` filter still selects that exact stable key. Expected close date is
  not actual win date. Historical stage transitions and conversion/win trends
  require future typed history, not reinterpretation of current data.
- Currency is integer **USD cents**. Measures disclose units; counts are record
  counts. AVG is a numeric result and can be fractional, including fractional cents.
- Optional custom fields use stable `custom.<key>` identifiers and their declared
  text/number/boolean/date/single-select types. Current labels are separate
  presentation metadata. Archived definitions remain readable. Number fields
  have no implicit currency unit. See [customization](CUSTOMIZATION.md).

Each response reads one database snapshot. Later pages or drilldowns are new
live reads. The canonical drilldown preserves all predicates and the evaluation
instant used for overdue comparisons, but cannot freeze changes made afterward.
Displayed results are not immutable historical snapshots.

## Log an actual contact event

A contact's **Logged contact** panel accepts a past timezone-aware time,
meeting/call/email/chat/other kind, direction and short summary. This records the
human or agent's claim only. It sends nothing, verifies no delivery and reads no
mailbox. The adapter records the author and self-reported provenance.

An erroneous claim can be voided with a reason and expected version. Original
content remains available; voided entries no longer affect last logged contact.
Summaries are not exposed through general report columns or legacy CRM read tools.

## Limits and recovery

- Contacts/deals/tasks and optional typed custom fields; one configurable deal
  pipeline, not custom objects or multiple pipelines.
- UTC dates/day buckets only; no arbitrary timezones or historical funnels.
- Twenty columns, thirty-two conditions, nesting depth three, three sorts,
  one grouping/measure, one hundred list values, one hundred rows per page.
  Grouped queries reserve drilldown capacity: thirty conditions and depth two.
- Group output is capped at one hundred buckets. Partial distributions are
  explicitly marked; a truncated/null/negative/all-zero donut is not drawn as a
  complete distribution. Exact summaries remain visible. Line charts use actual
  UTC-day distances and disclose unplottable buckets and partial coverage.
- Saved definitions and contact logs use separate lazy tables. Reads do not create
  those tables. Incompatible/partial schemas fail closed; there is no automatic
  repair or migration of deployed tables.
- Writes use exact version checks and stable idempotency keys. A lost response
  leaves an unknown outcome, not an automatic retry. Explicit retry uses the
  original frozen payload/key; client reconnects retain that lock for the plugin
  lifetime. Closing the plugin/app loses the in-memory recovery view, so inspect
  saved records before attempting a replacement. Local writes can complete after
  navigation; stale responses are not displayed in another profile.

This is a bounded prototype. It is not HubSpot/Salesforce parity, a tenant
permission system or a production migration. Synthetic database and component
checks do not replace native physical visual and accessibility testing.
