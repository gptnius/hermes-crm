# Guarded synthetic native-work reproduction

This is a disposable Linux x86_64 test only. It does not use a real model,
credentials, accounts, external messages, production configuration, or user
profiles. It verifies the native scheduler and agent/tool protocol, not model
reasoning quality, restart recovery, or visible Desktop delivery.

Use `manifest.json` and the two accompanying hashed requirements files. The
runtime, host commit, lock hashes, and guard source hashes are exact, not version
ranges. Do not relax a hash check to accommodate a different installation.

## Prerequisites and boundaries

- The existing Hermes source checkout must be at commit
  `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.
- Verify `pm/lock.json` SHA-256 is
  `40b06778980ff8c50dcd97c0d9b39ba3eb4a7a242ea62eaeaaa9a90d68ea1a85`
  and `uv.lock` SHA-256 is
  `5057a8a3cbc6d2b1f2059d66e27ffa43f447021f89779599dca416056574c064`.
- `$HOST` is that checkout; `$CRM` is the CRM checkout containing the reviewed
  test; `$BUNDLE` is this directory; `$CASE` is a newly allocated disposable
  directory outside the original home. `$UV` is an already available official
  uv 0.13.5 binary. Use absolute paths and do not modify shell profiles or PATH.
- Host, CRM, interpreter, venv, and test directories must all be outside the
  original home. The fixture validates this and denies the entire original home.
- Obtain permission required by the execution environment before installation,
  downloads, and local probes. Do not bypass an access denial. The test's guard
  allows only the exact local probes documented in the manifest.

## Runtime and dependency setup

Download the following official Astral python-build-standalone archive into
`$CASE/python.tar.gz`:

https://github.com/astral-sh/python-build-standalone/releases/download/20261021/cpython-3.14.9+20261021-x86_64-unknown-linux-gnu-install_only.tar.gz

Verify its SHA-256 **before extraction or execution**:

```sh
printf '%s  %s\n' dfa4c5a40c47f338f41658017be550c72247c391e6bfb1fa4da03ebc8451abdf "$CASE/python.tar.gz" | sha256sum -c -
mkdir "$CASE/runtime"
tar -xzf "$CASE/python.tar.gz" -C "$CASE/runtime"
"$CASE/runtime/python/bin/python3.14" -m venv "$CASE/venv"
"$CASE/venv/bin/python" --version
```

The required output is Python 3.14.9 from build 3.14.9+20261021. Verify both
requirements file SHA-256 values against `manifest.json`, then install only the
frozen default host closure and the pinned test requirements:

```sh
"$UV" pip install --python "$CASE/venv/bin/python" --no-deps --require-hashes --no-config --default-index https://pypi.org/simple --cache-dir "$CASE/uv-cache" -r "$BUNDLE/host-runtime-requirements.txt"
"$UV" pip install --python "$CASE/venv/bin/python" --no-deps --require-hashes --no-config --default-index https://pypi.org/simple --cache-dir "$CASE/uv-cache" -r "$BUNDLE/host-test-requirements.txt"
"$CASE/venv/bin/python" -m pip install --no-cache-dir --index-url https://pypi.org/simple sqlalchemy==2.1.8 greenlet==3.5.5
```

The host closure was generated in the pinned host checkout with uv 0.13.5:

```sh
cd "$HOST"
"$UV" export --frozen --no-dev --no-default-groups --no-emit-project --no-config --offline --no-python-downloads --cache-dir "$CASE/uv-cache" --output-file "$CASE/host-runtime-requirements.txt"
```

The distributed requirements contain exactly that closure, with the generated
comment's machine-specific paths replaced by a portable comment. Test-only
pytest 9.1.1, pluggy 1.7.0, and iniconfig 2.3.1 hashes come from the same host
lock. SQLAlchemy 2.1.8 and greenlet 3.5.5 are the separately pinned plugin test
dependencies. The manifest includes all observed package versions.

**Intentional upstream override:** the pinned host lock forces Pillow 13.0.0 for
security fixes even though browser-harness 0.1.13 metadata requests Pillow
12.3.0. This is why the complete frozen closure is installed with `--no-deps`;
an ordinary resolver reports a conflict. `uv pip check` reports this one known
metadata mismatch. The host's `pm.pip_check.unexpected_incompatibilities` check
against the pinned lock returned no unexpected incompatibilities. Do not change
Pillow or unlock the closure to make ordinary pip check appear clean.

## Execute and inspect

```sh
cd "$CRM"
HERMES_SOURCE="$HOST" HERMES_NATIVE_E2E=1 "$CASE/venv/bin/python" -m pytest -q tests/test_native_work_e2e.py -x --basetemp="$CASE/results"
```

Both `in_process` and `host` cases must pass. Each case first checks malformed
guard startup exits before runner code and before the official plugin child.
The actual child receives a fresh environment, fresh HOME and HERMES_HOME,
empty MCP configuration, source-hash-pinned guard, and one allowed loopback
model port. No provider credentials are installed or inherited.

The proof includes real future scheduling, paused-create/bind/resume, no model
call before due, real scheduler claim and running identity, default deferred
discovery of the exact 11 scheduled tools, and six forbidden describe negatives.
All model request receive times and the real ledger started_at are asserted at
or after the approved due instant. The proof also includes CRM reads and a
data-derived synthetic report, exact canonical admission and
stored successful cron result, output file, one execution/report despite extra
ticks, and a cancelled future assignment that never executes. The report remains
awaiting human review and does not complete the business task.

Success also requires no forbidden audit event, correct post-install guard-ready
marker counts (one in-process, two hosted), no enabled disposable jobs, stopped
scheduler and plugin child, and a closed model endpoint. Any unexpected denied
audit event is a failed overall result even if functional assertions pass.

Keep generated logs, databases, profiles, and paths private. The synthetic fixture
produces temporary evidence; it does not publish or upload it. Earlier failed
experiments must remain distinguishable from final strict passing runs.

## CRM-confirmed command-to-run variant

Use the same pinned runtime, dependency closure, host revision and safety guard
above. A separate opt-in fixture changes only setup admission: it creates a real
durable native user session, prepares the exact operation through authenticated
CRM REST and dispatches its UUID through the registered workspace-specific user
command. It also cancels the second future assignment through that lane.

```sh
cd "$CRM"
HERMES_SOURCE="$HOST" HERMES_NATIVE_E2E=1 HERMES_NATIVE_COMMAND_E2E=1 "$CASE/venv/bin/python" -m pytest -q tests/test_native_work_commands_e2e.py -x --basetemp="$CASE/command-results"
```

The original guard, actual scheduler/agent/report assertions, fatal bootstrap
negatives and cleanup requirements remain unchanged. The setup context is an
authenticated local user command, not an active model turn or model approval
receipt. Both plugin isolation modes must pass. This verifies the command-to-run
backend path, not a real native-window click or model reasoning. The original
fixture still tests the separate agent-tool scheduling path.

The selected, privacy-safe results and exact tested source hashes are in
`command-result-summary.json`. Its evidence supplements the historical manifest
and result summary above; it does not replace their original scope. Raw temporary
homes, logs, sessions, databases, transcripts and tokens are not distributed.
