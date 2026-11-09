"""Synthetic audit calls only: never install hooks, spawn processes, or import host."""
import ast
import hashlib
import os
from pathlib import Path
import sys

import pytest
import test_desktop_host as harness

PINNED_SHA = 'c9063a4a9b0ae7dd7027bf58955f3890b0ac671caa9be5fbd3f5bce02bcea0da'
ARGV = ['git', 'describe', '--tags', '--long', '--match', 'v2[0-9][0-9][0-9].*', 'HEAD']
CALLER = 'def _run_git(event, args):\n    return audit(event, args)\n'


def audit_fixture(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    version_file = source / 'hermes_cli/version_info.py'
    version_file.parent.mkdir(parents=True)
    version_file.write_text(CALLER)
    monkeypatch.setenv('CRM_DESKTOP_TEST_SOURCE', str(source))
    tree = ast.parse(harness.SAFETY_GUARD)
    functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                 and node.name in {'audit', 'desktop_version_probe'}]
    assert len(functions) == 2
    # Substitute only the pinned hash for our synthetic caller source. The actual
    # predicate still hashes the file on every call, including mutation tests.
    hashes = [node for node in ast.walk(functions[0]) if isinstance(node, ast.Constant)
              and node.value == PINNED_SHA]
    assert len(hashes) == 1
    hashes[0].value = hashlib.sha256(CALLER.encode()).hexdigest()

    def deny(action):
        raise AssertionError('DENIED: ' + action)

    ns = dict(Path=Path, os=os, sys=sys, forbidden=deny, forbidden_home=tmp_path/'private',
              root=tmp_path, homes={tmp_path/'user/.hermes'})
    exec(compile(ast.Module(body=functions, type_ignores=[]), '<synthetic-audit>', 'exec'), ns)
    exec(compile(CALLER, str(version_file), 'exec'), ns)
    return ns, source, version_file


def test_exact_describe_allowed(tmp_path, monkeypatch):
    ns, source, _ = audit_fixture(tmp_path, monkeypatch)
    ns['_run_git']('subprocess.Popen', ('git', ARGV, str(source), {}))


@pytest.mark.parametrize('case', ['cwd', 'missing_cwd', 'argv', 'extra_arg', 'show',
                                  'executable', 'caller_file', 'caller_name', 'no_caller',
                                  'source_hash', 'missing_source'])
def test_nonexact_probe_denied(tmp_path, monkeypatch, case):
    ns, source, version_file = audit_fixture(tmp_path, monkeypatch)
    argv = list(ARGV)
    cwd = str(source)
    executable = 'git'
    call = ns['_run_git']
    if case == 'cwd': cwd = str(tmp_path)
    if case == 'missing_cwd': cwd = None
    if case == 'argv': argv[-1] = 'OTHER'
    if case == 'extra_arg': argv.append('--always')
    if case == 'show': argv = ['git', 'show', 'v2026.1.1:pyproject.toml']
    if case == 'executable': executable = '/other/git'
    if case == 'caller_file':
        exec(compile(CALLER, str(tmp_path/'version_info.py'), 'exec'), ns)
        call = ns['_run_git']
    if case == 'caller_name':
        exec(compile(CALLER.replace('_run_git', 'other'), str(version_file), 'exec'), ns)
        call = ns['other']
    if case == 'no_caller': call = ns['audit']
    if case == 'source_hash': version_file.write_text(CALLER + '# modified\n')
    if case == 'missing_source': version_file.unlink()
    with pytest.raises(AssertionError, match='DENIED'):
        call('subprocess.Popen', (executable, argv, cwd, {}))


@pytest.mark.parametrize('event,args', [
    ('subprocess.Popen', ('sh', ['sh', '-c', 'echo unsafe'], '/tmp', {})),
    ('socket.connect', (None, ('example.com', 443))),
    ('socket.bind', (None, ('127.0.0.1', 9999))),
    ('socket.getaddrinfo', ('example.com', 443)),
    ('socket.sendto', ()), ('os.system', ()), ('os.posix_spawn', ()),
    ('os.exec', ()), ('os.fork', ()),
])
def test_existing_process_network_denials(tmp_path, monkeypatch, event, args):
    ns, _, _ = audit_fixture(tmp_path, monkeypatch)
    with pytest.raises(AssertionError, match='DENIED'):
        ns['audit'](event, args)


def test_home_and_child_guard_denials(tmp_path, monkeypatch):
    ns, _, _ = audit_fixture(tmp_path, monkeypatch)
    with pytest.raises(AssertionError, match='original HOME'):
        ns['audit']('open', (str(tmp_path/'private/file'), 'r', 0))
    child = [sys.executable, '-m', 'hermes_cli.plugin_host_child']
    with pytest.raises(AssertionError, match='missing safety guard'):
        ns['audit']('subprocess.Popen', (sys.executable, child, str(tmp_path/'user/.hermes'), {}))
    ns['audit']('subprocess.Popen', (sys.executable, child, str(tmp_path/'user/.hermes'),
                                    {'PYTHONPATH': str(tmp_path/'guard')}))
