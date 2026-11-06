# Host compatibility

Desktop and Agent have different release labels. A backend version alone does not establish that the Desktop SDK supplies the required routing APIs.

## Supported contract

The integration is tested against official Hermes source commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, including the Desktop SDK in that checkout. The isolated native runtime identifies as `vgit.2bd378e`; the source manifests declare `0.0.0`. This is the verified identity, not a confirmed Agent v0.23.0 release build.

The backend manifest's existing `requires_hermes: >=0.23.0` declaration is unchanged. It is not an empirically established numeric minimum or a guarantee for later releases. The pinned host's version gate permits unparseable development versions, so successful loading of `vgit.2bd378e` does not validate that numeric boundary. Use the exact source contract, capability checks and tests when assessing another build.

The native pane requires connection/profile/gateway stores, both gateway activation-epoch APIs, profile-scoped REST, context-managed timers and disposal. It checks capabilities rather than guessing a Desktop version threshold. An older Desktop that can register the pane but lacks these capabilities gets a compatibility notice with CRM reads and changes disabled. It does not substitute a constant epoch, a guessed connection identity, a localhost server or an older scheduler tool name.

The supported path combines the host activation epoch with a plugin-lifetime monotonic generation that synchronously observes connection, profile and gateway-state transitions. This prevents a client from becoming valid again after a rapid disconnect/reconnect or A→B→A switch, even if React batches the intermediate states. Plugin disposal permanently invalidates its clients.

## Older builds checked

### Desktop 0.17.0

Exact source commit: `3c27eb6234bf91b8ceee9e9071591b31e9b148cb`, official tag `v2026.8.3`.

This SDK supports namespace imports, normal CRM contribution areas and the basic host/profile stores. It does not provide `gatewayActivationEpoch`, `useGatewayActivationEpoch`, `host.state.connectionId`, `ctx.setTimeout` or `ctx.setInterval`. Its REST transport scopes the active profile without the newer connection pin. Full CRM operation on this build is not supported. The compatibility notice is deliberate, not a degraded writable mode.

### Agent reporting 0.21.0

Exact source commit: `29112bef099274229cadff79cdff7bf7b99c4b77`, official tag `v2026.8.31`. There is no corresponding `v0.21.0` tag in the checked official repository; use the exact source identity when comparing behavior.

The old host lacks `profile_name_for_home`, uses scheduler tool name `cronjob` instead of `cronjob_manage`, and does not have the newer plugin-request profile/secret scope and isolated-host API routing. Simple symbol aliases would not preserve the current multi-profile contract, so the backend requirement is not lowered.

Isolated probes found that its nonempty `crm_read` plus `no_mcp` scheduler allowlist behaves correctly, and unauthenticated CRM metadata is rejected with 401. Current authenticated CRM metadata returns 503 because the profile helper is absent. Two current-host integration tests stop at an absent refactored module, so they are not evidence that all older-host behavior was exercised. No live job, model call or user-system change was made for these checks.

## Validation versus previews

An isolated UI preview can use synthetic SDK state and sample records to show the actual component layout. It does not prove that an older installed Desktop supports the required APIs. A later native Mac run did verify installation, rendering and core CRM workflows on the pinned source build, as recorded in VERIFICATION.md. Broader accessibility/responsive coverage and live reminder execution remain open. Any app or backend upgrade must be handled separately; this plugin never upgrades the host itself.

Official sources:
- https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19
- https://github.com/NousResearch/hermes-agent/tree/3c27eb6234bf91b8ceee9e9071591b31e9b148cb
- https://github.com/NousResearch/hermes-agent/tree/29112bef099274229cadff79cdff7bf7b99c4b77
