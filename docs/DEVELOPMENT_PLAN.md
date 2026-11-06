# Hermes CRM: development plan

Status: focused prototype in development. Target: working, reviewable open-source plugin before November 11, 2026. Official announcement cutoff verified as November 11 at 5 PM EST (22:00 UTC); submission requirements are documented in HERMES_INTEGRATION.md. No submission or deployment is part of this build.

## Product promise
An agent-native relationship workspace: people, pipeline and follow-through in one small local application. A person's existing Hermes agent can work on the same records shown in the UI. One active Hermes profile maps to one workspace by default. The UI should feel considered and legible: calm navy navigation, warm off-white canvas, teal focus, chart cards and useful drillthrough. HubSpot and Salesforce are functional references, not assets to copy.

## Prototype scope and acceptance
1. **Overview:** live pipeline, weighted forecast, contacts and outstanding follow-ups; stage chart and counts link to filtered deals; recent immutable activity and upcoming work.
2. **Contacts:** create, search, inspect, edit; company, title, email and lifecycle; linked opportunities, tasks and activity. All demo contacts are synthetic and use example.com addresses.
3. **Pipeline:** staged opportunities (lead, qualified, proposal, negotiation, won, lost), value in integer minor units, probability, closing date and linked contact. Moving stages is audited; stage filters and detail drawers are keyboard accessible.
4. **Follow-ups:** create and complete tasks with explicit timezone-aware due dates; priority and contact/deal links; overdue and future views. A task due date is not a promise that a scheduler will run.
5. **Agent tools:** validated create, list/search, get and update operations for contacts, opportunities and tasks plus activity; structured errors; actor attribution and retry idempotency. Use Hermes' supported plugin registration mechanism after checking current upstream source. No invented SDK.
6. **Scheduling:** use verified native Hermes scheduler interface only. Separate CRM task persistence from scheduler outcome, surface failures, retain a job reference when scheduled, avoid duplicate jobs on retries. Never silently edit host crontab or assume a background service is running. If the host integration cannot be verified, return a pending scheduling request rather than claim execution.
7. **Storage:** SQLite as explicit default in the current Hermes profile directory (or configured data path). PostgreSQL is opt-in through a database URL with fail-fast validation, never fallback. Supabase is a PostgreSQL deployment option, not a hidden second datastore. Portable schema and common repository behavior; backend-specific checks documented honestly.

## Architecture
- Python package with small domain service and relational repository shared by web endpoints and agent tools.
- Native Hermes Desktop React pane/page over host-authenticated profile-scoped REST. An optional standalone FastAPI/static UI remains available for local demos. No cloud account or paid service is needed.
- SQLAlchemy portable models, foreign keys and transactions. UTC timestamps at boundaries, integer money. Optimistic version checks prevent stale edits; idempotency prevents duplicate creates.
- Dedicated tables for contacts, deals, tasks, activity and idempotency. Every mutation adds activity inside the same transaction.
- No arbitrary SQL, shell execution or URL fetching in agent tools. Strict field allowlists and bounded text/query inputs.
- Profile isolation derives from supported Hermes home/profile configuration, with an explicit override for a shared workspace. There is no cross-profile discovery by default.

## Boundaries and safety
- New repository only. Do not read, import or modify production records, private repository history or the existing CRM deployment.
- Demo seed is opt-in, visibly labeled and refuses non-empty databases.
- No email, messaging, calendar invitation, marketing send or autonomous outreach. Tasks and scheduler jobs may prepare internal reminders only.
- No live external-model calls or credentials needed for tests. Do not invent auth, billing or multi-tenant guarantees.
- A separate Hermes home is not complete credential isolation: host provider auto-discovery may inspect other CLI login state. Use a credential-free test environment, do not copy real credentials, and authorize any live provider setup separately.
- Public distribution gate: source and artifact review for private content, secrets, credentials, filesystem paths, databases, screenshots and dependency licenses. Only an identified repository owner may be used.
- Network exposure is excluded from prototype; deployment, production auth, backups and tenant security are separate future work.

## Build sequence
### Milestone 1: specification and integration discovery
Verify upstream plugin loader, manifest and registration; scheduler and profiles; catalog entry format, installation and license. Record revision and links. Freeze small domain/API contracts and implement a clean repository.
### Milestone 2: vertical slice
Create a synthetic contact, link an opportunity, schedule a CRM follow-up, update stage, inspect activity and dashboard totals through both UI and service. Add local installation/launch instructions.
### Milestone 3: Hermes Desktop and agent integration
Register the native Desktop pane/page/navigation and authenticated backend namespace, plus agent tools sharing the profile-local repository. Test loader contract and scheduler payload construction. Test actual host discovery, authentication, enablement and secondary-profile routing. Distinguish host/React harness checks from visual inspection in the actual Desktop app.
### Milestone 4: quality and portability
Test validation, missing records, idempotency, transaction rollback, stale updates, date/time handling, profile isolation and SQL portability. Run SQLite tests; run the same contract against a disposable PostgreSQL instance if available, otherwise clearly mark runtime portability unverified and supply an opt-in test command.
### Milestone 5: reviewable demo
Browser-test create/edit flows, repeated clicks, cancel, navigation, filtering and mobile layout. Capture synthetic screenshots. Prepare README, architecture, limitation checklist and short demonstration script. Review all files before any public push.

## Nov 6–11 pacing (deadline: November 11, 22:00 UTC)
- Nov 6: plan, upstream research, working local vertical slice.
- Nov 7: Hermes registration and follow-up scheduling, profile isolation, expanded tests.
- Nov 8: PostgreSQL contract test, UI refinement, install documentation.
- Nov 9: clean-room installation and demo rehearsal; review privacy/security and licensing.
- Nov 10: release candidate, packaging/catalog review, optional final independent review.
- Nov 11: only explicitly authorized publication/submission, before verified cutoff.

## Deferred
Multi-user auth, bulk import/export, email sync, attachments, custom schema builders, workflow automation designer, historical forecasting, real-time collaboration, existing CRM migration and production deployment. These would dilute a reliable contest prototype.

## Release checklist
- [x] Official Hermes interface and revision recorded
- [x] Local prototype and domain tests pass
- [x] Native Desktop pane and shared agent/backend implemented
- [x] Actual host authentication, enablement and secondary-profile routing tested
- [x] Native React interactions and stale-scope protection tested
- [x] Core native Mac workflows visually verified on pinned source; broader accessibility/responsive QA remains open
- [x] Profile isolation and no silent database fallback tested
- [x] PostgreSQL runtime contract verified on disposable PostgreSQL 17.11
- [x] Scheduler claims distinguish due dates, job creation and actual execution
- [x] Native install and demo verified in isolated source build using file-URI installation
- [ ] Secret/privacy review complete
- [x] Repository owner verified; source prototype published at https://github.com/gptnius/hermes-crm
- [ ] No production or contest submission claimed without verification
