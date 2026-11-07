# Native conversation beside CRM

This increment uses Hermes Desktop's own conversation view beside a CRM workspace. It does not implement a second transcript, model client, approval dialog or message queue. The existing native conversation continues to own its model, tools, permissions, drafts, streaming and Send action.

## Safe first slice

Start with an already loaded primary Hermes conversation in the same connection and profile as the CRM. The plugin verifies that ownership before opening a companion workspace. It does not create a conversation, choose another session or change providers. A missing or ambiguous conversation, a focused secondary tile or unavailable host capabilities is a visible blocker rather than an implicit fallback to another chat.

1. Open the intended existing main conversation, then return to CRM.
2. Save or cancel any open record form. Select a record if you want to discuss one.
3. Choose **Chat with Hermes**. CRM opens on the right beside the same native conversation, retaining the section, search, filters, page and selected detail.
4. Choose **Preview record reference**, then **Copy record reference**. The plugin re-reads the scoped record and checks its version before copying.
5. Paste into the native composer, add your request, review and use its normal Send action.

The copied reference contains only connection, profile, record kind, ID and version. It excludes record text, contact details and the workspace token.

The existing CRM view and selected record can move into the companion workspace. An unsaved record editor must be saved or dismissed first. Selected-record context is previewed as a bounded reference, then copied only after an explicit action. Copying is not attaching or sending: the user pastes, reviews and sends through the genuine native composer. No transcript, credential or draft is read by this feature.

The plugin does not call the native composer write or submit helpers. On the tested source revision, their addressed insertion can defer through a mutable main-composer target and append from a draft reference. The copy-and-review flow avoids silently changing a different session or overwriting newer typing. It also works without pretending that an unmounted composer accepted text.

Record context is data, not authorization to take an action. The user still tells the native agent what to do, and the host retains its normal approval behavior. Existing CRM tools can read and modify records in the current profile. This UI fetches records for display and copy validation, but does not dispatch agent work or modify records merely by opening the view or copying a reference. There is no email integration, sent/received capture or automatic outreach in this increment.

## Task-specific requests

Saved follow-ups also support a reviewed [assignment request workflow](ASSIGNMENT_UI.md). It prepares explicit task/version/time instructions and exact-assignment scheduling/check/cancel requests. Preview and Copy re-read scoped source records; the backend atomically binds the expected task version when saving new intent. Preparation remains local and does not submit, schedule or approve an action. The same native conversation and no-composer-access boundary apply.

## Routing and lifecycle

The integration uses public `host.openWorkspace`, an explicit side dock, `host.revealPane`, `host.navigate`, read-only host state and the plugin's existing scoped CRM transport. It checks the connection, profile, active and focused session ownership, workspace identity and activation generation. Changes invalidate old actions before they can copy a stale record reference. Repeated open/close, old disposer callbacks and plugin unload must not leave orphan workspaces or close a replacement workspace.

The tested host is official commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, not a claimed numeric release minimum. Optional APIs are feature-detected. A host that ignores side docking or cannot show both surfaces must report the limitation rather than present a tab switch as a working split.

## Verification boundary

Pinned SDK/layout source contracts and real React component tests pass, with no remaining blocking findings from independent review. Reconnection recovery, stale close/copy callbacks, absent or ignored host capabilities, duplicate opens, form preservation and minimal-context checks are included. Native window layout, actual clipboard behavior, keyboard focus, narrow layouts and a real-model conversation remain separate checks. This feature does not change the evidence for scheduled work or make its reports equivalent to business-task completion.
