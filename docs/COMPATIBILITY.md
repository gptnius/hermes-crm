# Host compatibility

> **Core-only contest candidate.** Gmail transports, OAuth settings, provider routes, connection panels and polling are not shipped in this edition. Contacts, relationships, agent tools, research, reports, scheduling boundaries, customization, protection and import/export remain. Legacy provider table definitions exist only for safe encrypted export and quarantined recovery; opening this edition does not clear or reconnect existing data. The tested core snapshot passed the official Hermes v0.23.0 validator, genuine host checks and a PostgreSQL-enabled regression suite. See the verification report for exact scope; these results are not maintainer acceptance or production certification.


Desktop and Agent have different release labels. A backend version alone does not establish that the Desktop SDK supplies the required routing APIs.

## Supported contract

The tested core snapshot is verified against official Hermes v0.23.0. The official tag resolves to source commit `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`, including the Desktop SDK in that checkout, and the clean validation runtime reports `0.23.0`. This release identity is independently established; it is not inferred from the earlier `vgit.2bd378e` development-runtime label.

The official `plugins validate --install-deps --json` run passed all 16 checks with no warnings, dependencies installed and `host_ready: true`. Five genuine host checks passed: both Desktop isolation modes, both 83-tool registry/workflow modes and one workflow seam. These use synthetic records with no live model or provider calls. See [the candidate verification results](VERIFICATION.md#core-only-candidate-checks-november-9-2026).

The backend manifest's `requires_hermes: >=0.23.0` declaration is unchanged and was exercised at 0.23.0. This is not a guarantee for every later release, nor an exhaustive proof of the earliest compatible release. Desktop and backend capabilities still need checking for any other build.

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

An isolated UI preview can use synthetic SDK state and sample records to show the actual component layout. It does not prove that an older installed Desktop supports the required APIs. Historical full-edition native Mac runs verified installation, rendering and core CRM workflows on their recorded source builds. Historical scheduler execution and local outputs used deterministic loopback model responses. The current core candidate checks do not claim a fresh physical Desktop UI, live-model or provider run. Broader accessibility/responsive coverage, real-model behavior, visible reminder presentation, default deferred-tool discovery and restart recovery remain open; see VERIFICATION.md. Any app or backend upgrade must be handled separately; this plugin never upgrades the host itself.

Official sources:
- https://github.com/NousResearch/hermes-agent/tree/2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19
- https://github.com/NousResearch/hermes-agent/tree/3c27eb6234bf91b8ceee9e9071591b31e9b148cb
- https://github.com/NousResearch/hermes-agent/tree/29112bef099274229cadff79cdff7bf7b99c4b77

## Credential sources

The native factory uses the host's profile-scoped storage helpers and secret resolver for PostgreSQL and protection keys. It does not fall back to ambient environment credentials. A poison-environment regression exercises that boundary without provider access or a PostgreSQL connection. The standalone CLI retains its documented, explicitly configured `HERMES_CRM_*` environment settings; these are not a fallback for native host-secret paths. This distinction is not a claim of a catalog policy exemption or maintainer acceptance.
