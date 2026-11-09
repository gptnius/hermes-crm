# Explicit result acknowledgement in the native CRM

The existing native-work selected-assignment and history report cards, and scheduled public-research report history, use one shared acknowledgement component. This is an additive action row, not a redesigned page or a merged work queue. Source freshness, task status, host success, and proposed-note disposition remain separate.

- Opening or refreshing a report performs only a scoped read. **Mark result reviewed** reads a fresh confirmation containing the exact immutable summary and reported outcome. Only **Confirm mark reviewed** writes an acknowledgement. **Undo acknowledgement** has the same fresh-preview and confirmation flow.
- The current label is **Reviewed in CRM** or **Not reviewed in CRM**, read from the dedicated review API. It does not copy the immutable report's old awaiting-human-review field. History identifies the server actor as `desktop`, never the task owner or an authenticated human reviewer.
- Historical, completed-task, changed-target and missing-source results remain reviewable. Their confirmation displays the source reason and requires an explicit changed-source checkbox. Undo requires the same warning when the source is stale. Cancel and Escape dismiss without a write; focus returns to the action, with a focusable confirmation heading. Actions have 44px minimum height and use existing Workbench classes and theme tokens.
- Native coverage/history refresh is requested after a confirmed acknowledgement or undo in the still-current UI scope, including historical source results and late receipts received after remount. Freshly read source warnings remain visible independently of acknowledgement. Scheduled research remains its own history. Neither action completes a task, schedules/cancels/reruns work, applies a proposed note, sends a message, grants permissions, or calls an agent review tool.

## Integrity and interrupted operations

The shared module validates the full report binding, native/scheduled identifiers, immutable summary/outcome/identity, source context, latest event and bounded chronological history before rendering any status. Invalid/unavailable responses never become an empty history or an assumed review state. Technical IDs/context and event history are collapsed.

Each attempted write retains its exact endpoint, body and idempotency key in plugin-lifetime memory scoped to connection, profile, workspace, task, family, assignment and report. Pending panels share a write lock. An uncertain or malformed receipt allows only an explicit exact retry. A late verified receipt is retained for its original scope even if its panel unmounted, and same-scope remounted panels are notified. Reconnection preserves recovery for that connection/profile, while old route clients and callbacks remain invalidated. A full plugin restart loses this in-memory recovery; read durable status before taking another action.

POST receipts are historical acknowledgements, including exact replay after a later undo. They never directly set the current status. A fresh GET is required; if that fails the UI says status unavailable. Scope changes, render generations, mounting/disposal, cancel, replaced previews and stale source-checkbox callbacks are fenced. An unclassified transport error remains uncertain conservatively; the UI cannot certify that a thrown transport error means a rejected write.

## Verification

`tests/native_report_review_react.mjs` runs against real React 19.3, normal and StrictMode, for both families. It covers explicit acknowledgement and undo, unchanged write keys, historical-source confirmation, cancel, unknown/malformed writes, late receipt after remount, concurrent panels, old historical replay after undo, failed status refresh, changed task/profile/workspace, unavailable client, nested invalid previews and stale cancelled callbacks. Captured synthetic backend SQLite fixtures also verify native, cancelled/superseded native, Contact-research and Company-research preview/receipt/history contracts against the JavaScript validator and mounted component.

The native SDK/route fixtures in `tests/native_desktop_assignments.mjs` additionally exercise the actual scoped component/client, same-tick profile ABA, reconnect recovery and disposed-client rejection for both families. Existing native assignment, React, scheduled research, work-command, routing and smoke tests are rerun. Legacy display assertions now check source freshness instead of the immutable old review label.

Run `python scripts/build_report_review_panel.py --check` and `python scripts/build_scheduled_research_panel.py --check` for generated bundle synchronization. Run React tests with the documented `HERMES_CRM_REACT_TEST_ROOT` fixture dependency directory and `node --experimental-vm-modules`.

No current app, installed plugin, production profile, provider, schedule or user record was touched. These are synthetic tests. No pixel inspection or live native UI verification is claimed.

Synthetic backend fixtures can be regenerated with `PYTHONPATH=.:tests python tests/generate_report_review_ui_fixtures.py` in the repository test environment. Native invalidation changes the mutable assignment generation; the UI binds the immutable report generation instead.

## Stored review evidence

Acknowledgements retain the report summary/identity and source version/status
context in the CRM ledger and retry receipt. They do not copy current record
notes or titles. This is ordinary live datastore content, not a new encryption
feature. Undo preserves the earlier event; export/restore follows the documented
[retention and quarantine boundaries](REPORT_REVIEW_PLAN.md#retention-and-disclosure).
