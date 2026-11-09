"""No real audit installation, processes, model calls or networking in these tests."""
import ast
import hashlib
from pathlib import Path
import re
import sys

import pytest
import test_native_work_e2e as harness
from scheduled_research_guard import build_guard, EFFECTIVE_GUARD_SHA, VERSION_SOURCE_SHA

ARGV = ['git', 'describe', '--tags', '--long', '--match', 'v2[0-9][0-9][0-9].*', 'HEAD']


def audit_fixture(tmp_path):
    effective = build_guard(harness.SAFETY_GUARD)
    tree = ast.parse(effective)
    audit = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'audit')
    source = tmp_path / 'source'
    frame = {'file': str(source / 'hermes_cli/version_info.py'), 'function': '_run_git'}
    stack = [frame]
    admitted = []
    def deny(action):
        raise AssertionError('DENIED: ' + action)
    ns = dict(Path=Path, re=re, sys=sys, source=source, root=tmp_path,
              forbidden_home=tmp_path / 'private', endpoint=('127.0.0.1', 12345),
              unit='test-unit', frames=lambda: stack, forbidden=deny,
              has_frame=lambda rows,p,f: any(r['file']==str(p) and r['function']==f for r in rows),
              allow_probe=lambda action,frames: admitted.append(action),
              probe_sources={k:(source / path,'unused',function) for k,path,function in [
                  ('calver','hermes_cli/version_info.py','_run_git'),
                  ('platform','platform.py','from_subprocess'),('sdk','sdk.py','get_platform'),
                  ('ipv6','ipv6.py','_has_ipv6')]})
    exec(compile(ast.Module(body=[audit],type_ignores=[]),'<audit-unit>','exec'),ns)
    return ns, stack, admitted


def test_guard_fingerprints_and_retains_original(tmp_path):
    effective=build_guard(harness.SAFETY_GUARD)
    assert hashlib.sha256(effective.encode()).hexdigest()==EFFECTIVE_GUARD_SHA
    assert VERSION_SOURCE_SHA in effective
    # All historical lines remain, in order; additions cannot replace hooks.
    lines=iter(effective.splitlines())
    for old in harness.SAFETY_GUARD.splitlines():
        assert any(line==old for line in lines)
    with pytest.raises(AssertionError):build_guard(harness.SAFETY_GUARD+'\n')
    ns,stack,admitted=audit_fixture(tmp_path)
    ns['audit']('subprocess.Popen',('git',ARGV,str(ns['source']),{}))
    assert len(admitted)==1


@pytest.mark.parametrize('case',['cwd','missing_cwd','extra_arg','changed_arg','show','caller_file','caller_function','no_caller','executable'])
def test_probe_denies_nonexact_invocations(tmp_path,case):
    ns,stack,admitted=audit_fixture(tmp_path)
    argv=list(ARGV);cwd=str(ns['source']);executable='git'
    if case=='cwd':cwd=str(tmp_path)
    if case=='missing_cwd':cwd=None
    if case=='extra_arg':argv.append('--always')
    if case=='changed_arg':argv[-1]='OTHER'
    if case=='show':argv=['git','show','v2026.1.1:pyproject.toml']
    if case=='caller_file':stack[0]['file']=str(tmp_path/'version_info.py')
    if case=='caller_function':stack[0]['function']='other'
    if case=='no_caller':stack.clear()
    if case=='executable':executable='/other/git'
    with pytest.raises(AssertionError,match='DENIED'):
        ns['audit']('subprocess.Popen',(executable,argv,cwd,{}))
    assert admitted==[]


@pytest.mark.parametrize('event,args',[
    ('subprocess.Popen',('sh',['sh','-c','echo unsafe'],'/tmp',{})),
    ('socket.connect',(None,('example.com',443))),
    ('socket.bind',(None,('127.0.0.1',9999))),
    ('socket.getaddrinfo',('example.com',443)),
    ('socket.sendto',()),('os.system',()),('os.posix_spawn',()),('os.exec',()),('os.fork',()),
])
def test_existing_process_and_network_denials_remain(tmp_path,event,args):
    ns,_,admitted=audit_fixture(tmp_path)
    with pytest.raises(AssertionError,match='DENIED'):ns['audit'](event,args)
    assert admitted==[]
