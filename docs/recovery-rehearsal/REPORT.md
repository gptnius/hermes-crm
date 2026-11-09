# Synthetic process-separated CRM content recovery

Passed using the unchanged historical safety guard, SHA-256 5f0c4fd97681dfafeb3cd487026279b685e260a6518d7ac72b56c4d4c9cca14b, pinned Python 3.14.9 and host 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19.

CRM payload is git archive of local commit 55dfe558c8c8019b454b3daf40bfab76eb0dc247, tree e07ab221de1a96fe947ec4ec6b7cbf50b70bc6f5. Separate publication verification established the identical tree at published 73a7f611af1941e636d4496424d9420f25187564; this rehearsal itself uses a local archive, not remote installation.

Six separate interpreter invocations: seed and orderly close; reopen and export through normal protection_runtime.export_artifact; wrong-key recovery CLI (expected nonzero and absent target); successful recovery CLI; restored reopen; second restored reopen. All processes finish synchronously; no background process or model/provider endpoint is started. No enabled job is created: the sole native-work assignment is saved intent only, not scheduled. No forbidden audit event occurs.

Assertions include exact persisted Contact and owned Task dictionaries (including versions/custom fields), Company-to-Contact link and Event title, exact full research evidence content, protected note reveal using retained old key with a new active key, immutable protected-operation replay, idempotent Contact create replay, same workspace/profile, zero live native assignments and one quarantined source assignment, no schedule/job on restored Task, encrypted note plaintext absent from SQLite bytes, SQLite integrity and foreign-key checks. Recovery manifest/database digest matches before first reopen; second reopen compares a separate orderly-close digest because normal schema initialization changes database bytes. Wrong-key failure creates no destination.

The native export artifact is produced by the project's supported export function and restored by its documented CLI, with synthetic keyrings piped on stdin. Synthetic retained key files are mode 0600 under a mode 0700 disposable directory. Keys and raw logs/databases are not part of the deliverable. Script source contains clearly synthetic fixed test keys only, not credentials. Summary omits raw paths, record IDs and restore CLI output.

Limits: this is content/process recovery, not a complete host restart, real-host cutover, visible Desktop exercise, authenticated native REST/export download, fresh dependency/bootstrap validation, supported plugin installer activation, power-loss test or production-readiness claim. No report acknowledgement or proposal was created. Evidence is present; report-review and scheduled-research runtime families are not exercised here. No preexisting live schedule is fabricated, so schedule-clearing/version-increment for previously scheduled tasks remains covered by existing tests, not this rehearsal. Only SQLite destination is exercised.

Reproduce with the already verified pinned Linux x86_64 runtime. The binary hash
is platform-specific; these path parameters do not imply cross-platform support.
Keep the source checkout, runtime, bundle and private output parent outside the
original login home, as required by the unchanged guard and runner preflight:

    /absolute/pinned-runtime/venv/bin/python /absolute/bundle/run.py --repo /absolute/crm-checkout --runtime /absolute/pinned-runtime --workdir /absolute/private-rehearsal-output

run.py accepts the exact local or published commit with the pinned identical tree, archives it into a new private run directory and writes summary.json under the supplied workdir. It requires an existing pinned runtime bundle with host/ and venv/ siblings; prepare that bundle using the source repository docs/native-work-test/REPRODUCE.md. It independently checks the interpreter binary, Python version, clean tracked host revision, phase script and archived original guard. Each child must produce its exact PID guard-ready marker and exit; wrong-key rejection must have the exact authentication error. phase.py contains supported API seed/reopen assertions. The original guard is imported without modification. Failed exploratory runs remain separate: first used noncanonical test-key padding; second incorrectly reused original restore digest after normal reopen; third compared compact submit evidence to full detail evidence. These harness errors were corrected, never by relaxing the guard or changing CRM. Final run requires all strengthened checks.

The independent reviewer inspects code and private run evidence read-only; review is not an independent execution. Retained-key checks change the active key in memory while keeping the historical key; they do not write a new note or persist/restart a rotated keyring. The supported installer remains blocked on reviewed PM synchronization and kill-list network behavior, detailed in INSTALL-PLAN.md.

## Portable rerun

The independently reviewed portable runner completed all six phases successfully, including exact wrong-key authentication refusal. Summary records runner/phase hashes, pinned tree/host/Python and per-process guard-ready PID checks. The executed checkout was local 55dfe558c8c8019b454b3daf40bfab76eb0dc247; public 73a7f611af1941e636d4496424d9420f25187564 is accepted only with the identical fixed tree, but that public-commit checkout path was not executed here. No original guard change, installer execution or main-repository edit was made.
