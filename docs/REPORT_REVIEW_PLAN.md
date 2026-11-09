# Bounded report review acknowledgement

Baseline: local `0d9865149ddec3abc28d773d17fd71a81272bd9b`.
This increment adds authenticated local UI acknowledgement, not named-human
identity, quality approval, execution success or task completion. No model review
tool, scheduler call, note application, provider action or external send is added.

## Contract

The report families are `native` and `scheduled_research`. Native report IDs are
stored report UUIDs; scheduled report IDs are their immutable `run:…` operation
keys. GET `/report-reviews/{family}/{assignment_id}/{report_id}` with the captured
`workspace_token` returns exact report content/identity, current source context,
`context_digest` and `review` (status, integer version, latest event and history).

POST the same path plus `/acknowledge` or `/revoke` with strict JSON fields:
`workspace_token`, `idempotency_key`, `context_digest`, `expected_review_version`,
`acknowledge_stale` (boolean, default false). Explicit acknowledgement of changed
source is required when source context is stale. Both actions bind the freshly
read context and exact current review version. Response is the immutable event
receipt plus the resulting review status/version. The UI retains the exact key
and body after an uncertain result, and retries only that operation. Exact retry
returns its original receipt even after source changes. A new action needs a
fresh GET. Report reading never records acknowledgement.

Review status is `awaiting_review` or `reviewed_in_crm`. Revocation appends a new
event; it does not erase history. Actor is server-selected `desktop`, displayed as
“Reviewed in CRM”, never inferred from assignment owner. Source freshness remains
separate from review status. Native report and scheduled receipt views receive an
additive `review` projection; original scheduled receipt result JSON is immutable.

## Storage and concurrency

An independent optional two-table family stores append-only review events and
idempotent operation receipts. No old schema or source receipt is rewritten.
Read-only operations never initialize tables. Partial/incompatible families fail
closed; complete absence means no acknowledgements. Writes initialize only the
new family. SQLite immediate transactions and PostgreSQL locks serialize exact
report review state and source checks. Context includes assignment version/state,
generation/digest, report identity/digest/content, frozen task/target versions and
current task/target version/status/archive state. Current context mismatch rejects
without mutation. Historical sources remain reviewable after explicit warning.

Native queue awaiting-review flags count any unacknowledged report, while all
other scheduling/outcome risk flags remain independent. Scheduled history is
separate; this does not claim a unified review queue.

## Export and recovery

Allowlist and scope-filter both new tables. Validate event sequencing, hashes,
operation receipts and immutable report/assignment references on export/decrypt.
Historical source snapshots are validated structurally, not rewritten to current
source versions. Absent family remains backward compatible. Recovery retains
raw review evidence but quarantines live review tables with native/scheduled
assignments, preventing revived acknowledgement authority or orphaned state.

## Verification

Use synthetic SQLite and disposable PostgreSQL only. Cover both report families,
all outcomes, current and stale/archived sources, old/new reports, undo/re-review,
identity tampering, scope isolation, wrong context/version, exact/conflicting
retries, concurrent writes, transaction rollback, no side effects, unchanged
scheduled receipts, strict API inputs, read-only schema behavior, malformed
storage, mixed-scope encrypted export and quarantined recovery. Add focused
PostgreSQL wrappers to existing disposable test workflow. No live application,
provider, profile or production migration is part of these checks. The native UI and its interrupted-flow tests cover a separate acceptance layer;
see [the shared native workflow](REPORT_REVIEW_UI.md). Pixel/live-app acceptance
is not implied by those component tests.

## Intentional projection compatibility change

Native `review_status` is now independent of source freshness. Report projections
use `awaiting_human_review` or `reviewed_in_crm`; an assignment uses those values
according to whether any report remains unacknowledged, or `no_report` when empty.
Coverage latest-report projections use the same review statuses. They no longer
substitute `stale_source_task` for review state. Existing `source_task_current`,
`current_task_version` and `current_task_status` remain the source-freshness
signals. Consumers must preserve changed/completed-source warnings using those
fields, including for an acknowledged report. The additive `review.status` uses
`awaiting_review` / `reviewed_in_crm` consistently across both families. This is a
read projection change, not a rewrite of any stored report, assignment reason or
scheduled-operation response.

GET history is the last 50 events in review-version order with `history_total`
and `history_truncated`; full history remains in the immutable export ledger.
Paged native/scheduled history loads the scoped review ledger once per snapshot,
not once per report. Coverage does the same. The bounded response is not a claim
of bounded full-history database work: validation still checks the scoped ledger.
A replayed write receipt is historical even if a newer revocation exists; always
refresh the current GET projection after a confirmed receipt.

## Retention and disclosure

The ledger/receipt copies the report summary and identity plus source versions,
status and review context. It does not copy current source notes/titles. Ordinary
live CRM storage is not encrypted by this feature. Undo appends history rather
than erasing the earlier event. Scoped encrypted exports include this history;
restore quarantines it. Read projections batch the scoped ledger once per
history/coverage snapshot, but validation cost still grows with that history.
Only the last 50 events are returned in an individual review preview.
