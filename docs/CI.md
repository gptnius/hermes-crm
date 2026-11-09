# Credential-free continuous integration

`.github/workflows/test.yml` runs on pushes, pull requests (including fork PRs under
GitHub's normal approval rules), and manual dispatch. It is a contract regression
gate, **not** a production deployment or live Hermes/Desktop acceptance test.
A workflow definition and a local passing runner are not evidence of a successful
GitHub Actions run. Check the run for the exact candidate commit before release.

## Trust and permissions

- GitHub-hosted Ubuntu 24.04; Python 3.12; Node 24; 20-minute job timeout.
- Only `contents: read` is granted. Checkout does not persist credentials.
- No repository/environment secrets, custom tokens, OIDC, provider keys, signed-in
  app access, publishing, deployments, releases, or `pull_request_target` event.
- New runs cancel superseded runs for the same PR/ref.
- Official checkout, setup-python and setup-node actions are pinned to immutable
  commits verified against the official repositories' release tags:
  - `actions/checkout` v4.2.2: `11bd71901bbe5b1630ceea73d27597364c9af683`
  - `actions/setup-python` v5.6.0: `a26af69be951a213d495a4c3e4e4022e16d87065`
  - `actions/setup-node` v4.4.0: `49933ea5288caeca8642d1e84afbd3f7d6820020`
- Dependencies come from public Python/npm registries. npm lifecycle scripts are
  disabled. React and react-test-renderer are both fixed at 19.3.0. Python
  dependencies follow `pyproject.toml` bounds. Interpreter patch releases,
  transitive dependencies and the official PostgreSQL image tag can update;
  this is not a fully locked, byte-reproducible build.
- PostgreSQL 16 runs as a disposable job service. Its published loopback port,
  database, user and password are test fixtures, not deployment credentials.
  Tests create isolated random schemas and remove them. Never substitute a
  production or shared database URL, including one forwarded to localhost.

The runner creates a temporary HOME/HERMES_HOME and config/cache directories,
then starts each check with a narrow environment allowlist. It does not inherit
provider credentials, application database settings, `HERMES_SOURCE`, E2E flags,
Python/Node preload settings, or user pytest plugins. Python bridge fixtures use
that runner's interpreter explicitly. This is environment hygiene, **not** an
OS/network sandbox: checks execute repository code and can access the runner's
filesystem/network. Use a clean disposable runner, not a credential-bearing
workstation, for untrusted changes.

## Coverage

`scripts/ci_checks.py` discovers current suites, so additions matching the
existing filenames run automatically. At introduction it includes:

- All 11 `scripts/build_*.py --check` generation consistency checks.
- Full `pytest tests`, with short reasons for every skip. CI passes an explicit
  disposable PostgreSQL URL, so both SQLite and optional PostgreSQL contracts
  run. Missing driver/service is a failure, not a substitute SQLite pass.
- 21 executable `.mjs` and 12 `.cjs` assertion entrypoints, including React
  fixtures and Python-backed execution-bridge/store mapping. React dependency
  presence/version is required, preventing optional blocks from silently being
  omitted. JavaScript uses `--experimental-vm-modules`.

Explicit exclusions:

- `native_research_contract.mjs`: imported fixture helper, not a standalone suite.
- `render_relationship_fixtures.mjs`: artifact generator, not assertion coverage.
- `native_desktop_work_commands_host.mjs`: requires a separately verified,
  pinned Hermes source checkout. CI never supplies or downloads that checkout.
- `workbench_navigation_layout.cjs`: requires separate Playwright/Chromium.

Python host-source suites and guarded model/scheduler E2E remain skipped because
CI intentionally supplies neither `HERMES_SOURCE` nor E2E opt-ins. Source-specific
branches within other JS fixtures also report skips. Physical Desktop/browser
rendering, provider/Gmail calls, native transports, deployment health, and backup
restoration against a real installation are not established by this workflow.
See the separate host and operational verification procedures for those gates.
Never combine a skipped test count with the passing count.

## Reproduce with an existing test environment

Install the project's test dependencies and official React fixtures in a clean
throwaway environment, or use an already provisioned environment. The runner
itself installs nothing:

```sh
/path/to/test-env/bin/python scripts/ci_checks.py \
  --react-root /path/to/react-fixture-prefix
```

The prefix must contain `node_modules/react` and
`node_modules/react-test-renderer` version 19.3.0. To exercise PostgreSQL, add
`--postgres-url postgresql+psycopg://USER:PASSWORD@127.0.0.1:PORT/DISPOSABLE_DB`.
Only an explicitly supplied loopback URL is accepted. The runner rejects all
query/fragment components (including libpq destination overrides), percent
escapes, whitespace, ambiguous authorities, and ports outside 1–65535. Use a
simple database name and optional credentials containing only ASCII letters,
digits, dots, underscores, tildes or hyphens. Ambient test/database URLs and libpq
connection variables are ignored; loopback validation is not proof a database
is disposable. `tests/test_ci_runner.py` tests this parser and environment
isolation without starting any database or child processes.

Use `--suite generated`, `--suite python`, or `--suite javascript` to run a single
group. JavaScript requires `--react-root`; Python and generated checks do not.
Each command fails on a nonzero exit or a ten-minute timeout; CI has the stricter
20-minute overall job limit. Console output reports exclusions and pytest skips.

## Release interpretation

A passing credential-free run validates the supported contracts on that commit.
It does not certify a live host, establish production credentials/permissions, or
publish anything. Branch protection/required-check configuration is not changed
by this workflow. Require the check in the repository's release process and
review the separately documented host, backup, and deployment evidence before
calling a release production-ready.
