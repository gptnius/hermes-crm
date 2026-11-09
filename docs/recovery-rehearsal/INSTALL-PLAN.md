# Pending supported-install guard review

Not run. No guard extension has been written or approved.

Proposed bounded call: hermes_cli.plugins_cmd_install.cmd_install('file://<disposable exact-commit git payload>', ref='55dfe558c8c8019b454b3daf40bfab76eb0dc247', no_deps=True, enable=False). Preserve normal scanner, security verdict and exact pin checks; do not use force/allow_removed or scanner overrides. File installation is disabled-only. Fresh dependency bootstrap and activation remain separate missing proof.

Call chain: cmd_install -> _install_plugin_core -> _clone_at_reviewed_commit -> plugins_cmd_git._clone_plugin_repo -> _run_plugin_git -> git_credentials.run_git_with_credential_fallback -> subprocess.run. Expected exact Git forms (absolute verified git executable):

- clone --depth 1 --no-checkout file://<disposable payload> <profile/plugins/.install-*/plugin>
- fetch --depth 1 origin 55dfe558c8c8019b454b3daf40bfab76eb0dc247
- checkout --detach 55dfe558c8c8019b454b3daf40bfab76eb0dc247
- rev-parse HEAD
- rev-parse --verify --quiet 55dfe558c8c8019b454b3daf40bfab76eb0dc247^{commit}

Allow only exact source/destination root, pinned source frames and sanitized environment. Subprocess Git is not covered by Python socket audits: require disabled global/system configuration, empty isolated HOME, no credential helper, no hooks, only file protocol, no inherited Git config injection, exact local origin verification before fetch, and a preverified synthetic bare source with no remote/push/hook config. Determine supported noninteractive scan outcome before allowing further operations. Catalog reads may request network; keep denied and report rather than permitting remote access. Any additional call remains denied pending new review. Local metadata/capability probes already approved by the historical guard remain unchanged; CalVer probe may require separately reviewed existing derivative, not a blanket Git allowance.

Pinned host file SHA-256:
- plugins_cmd_install.py: 5a4c9d344204a3f8b1138bd6b607e9dddf42aa41e4b71c5b64057f6646eaa0f0
- plugins_cmd_git.py: e0a71fad2f8a3fc33b80ecff9e6afff00f59df60b57504e4b317927412588f38
- plugins_cmd_catalog.py: 907ee43556510695abda150b033f696250891f9837fd115296266d7a657f946f
- git_credentials.py: dc45a45db417e887c05d86c45062337244caaf55abc74d2ae8c0e70694fbae14
- _subprocess_compat.py: 50b77ec24e7cc3772eb8cda170099b853058f4d939bf0cefa75ed1609ce000f2
- plugins_cmd.py: b36cd47f8feb9e56160c043adb330585f044edd2314a39851a675a9baade92d2

Reviewer must also inspect installer scanner/PM/catalog control flow before executable extension is approved. This plan does not assert the five listed Git forms exhaust all host behavior.

## Independent inspection: concrete blocker (do not execute)

Review found the Git-only premise insufficient. `plugins_transaction.py:45` invokes `sync_venv(explicit=True, plugins=StagedUpdate(...))` unconditionally, including disabled `no_deps` publication. The fresh-profile kill-list path `find_removed -> live_removed_list -> fetch_live_catalog` calls `httpx.get` in `plugin_catalog.py:375`; caught network failure would still be a forbidden audit event, not a passing installation. Non-TTY scanner caution refusal at `plugins_cmd_install.py:342` and dangerous verdict blocks must remain intact. No executable guard extension is approved. Installer proof requires separately scoped review of dependency synchronization and online kill-list behavior; this rehearsal grants neither. No installation attempt or bypass has occurred.
