"""Narrow approved CalVer probe extension for scheduled-research tests only.

The historical native-work guard is immutable. This builds an independently
fingerprinted derivative, retaining every original hook and fail-closed wrapper.
"""
import hashlib
import textwrap

ORIGINAL_GUARD_SHA = '5f0c4fd97681dfafeb3cd487026279b685e260a6518d7ac72b56c4d4c9cca14b'
VERSION_SOURCE_SHA = 'c9063a4a9b0ae7dd7027bf58955f3890b0ac671caa9be5fbd3f5bce02bcea0da'
EFFECTIVE_GUARD_SHA = 'bfcb6838eda9b14fbce6221eef452d8d7a3e3dd56954bbd79b3e7a1720a5f2f5'

_SOURCE_ANCHOR = "for path, digest, function in probe_sources.values():\n"
_SOURCE_EXTENSION = "probe_sources['calver'] = (source / 'hermes_cli/version_info.py',\n    '" + VERSION_SOURCE_SHA + "', '_run_git')\n"
_PROCESS_ANCHOR = "        platform_path, _, platform_function = probe_sources['platform']\n"
_PROCESS_EXTENSION = '''        calver_path, _, calver_function = probe_sources['calver']
        if (executable == 'git' and list(argv) == ['git', 'describe', '--tags', '--long',
                '--match', 'v2[0-9][0-9][0-9].*', 'HEAD']
                and cwd and Path(cwd).resolve() == source
                and has_frame(stack, calver_path, calver_function)):
            allow_probe('Read-only pinned source CalVer metadata: git describe', stack)
            return
'''


def build_guard(original):
    assert hashlib.sha256(original.encode()).hexdigest() == ORIGINAL_GUARD_SHA
    # The original is already indented inside its fail-closed try wrapper.
    effective = original
    for anchor, addition in ((_SOURCE_ANCHOR, _SOURCE_EXTENSION),
                             (_PROCESS_ANCHOR, _PROCESS_EXTENSION)):
        anchor = textwrap.indent(anchor, '    ')
        assert effective.count(anchor) == 1
        effective = effective.replace(anchor, textwrap.indent(addition, '    ') + anchor)
    assert hashlib.sha256(effective.encode()).hexdigest() == EFFECTIVE_GUARD_SHA
    return effective
