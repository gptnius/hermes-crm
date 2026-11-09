import os,sys,json,tempfile,subprocess,hashlib,importlib.util,base64,shutil
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description='Synthetic process-separated content recovery; no host activation')
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--runtime',type=Path,required=True,help='Verified pinned host/ and venv/ runtime bundle')
parser.add_argument('--workdir',type=Path,required=True,help='Private output parent outside original home')
a=parser.parse_args()
here=Path(__file__).resolve().parent
repo=a.repo.resolve(); runtime=a.runtime.resolve(); workdir=a.workdir.resolve(); python=runtime/'venv/bin/python'
assert sys.version_info[:3]==(3,14,9), 'Run using pinned Python 3.14.9'
assert Path(sys.executable).resolve()==python.resolve(), 'Run with the supplied runtime interpreter'
assert hashlib.sha256(python.resolve().read_bytes()).hexdigest()=='3642edb46c7bfad367e99751c422ca6b57977157b78f8f77ee4daa9498c002b5', 'Pinned interpreter binary mismatch'
phase_sha=hashlib.sha256((here/'phase.py').read_bytes()).hexdigest()
assert phase_sha=='7a72f0ab86f37c1bcb6603ba2e332eec17d113914a4e8f42d5baedec5a7404b5'
def git(path,*args): return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
commit=git(repo,'rev-parse','HEAD'); tree=git(repo,'rev-parse','HEAD^{tree}')
assert commit in {'55dfe558c8c8019b454b3daf40bfab76eb0dc247','73a7f611af1941e636d4496424d9420f25187564'}
assert tree=='e07ab221de1a96fe947ec4ec6b7cbf50b70bc6f5'
host_commit=git(runtime/'host','rev-parse','HEAD')
assert host_commit=='2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'
assert not git(runtime/'host','status','--porcelain','--untracked-files=no'), 'Host tracked source must be clean'
original_home=Path.home().resolve()
assert all(not p.is_relative_to(original_home) for p in (repo,runtime,workdir,here,python.resolve()))
workdir.mkdir(parents=True,exist_ok=True)
root=Path(tempfile.mkdtemp(prefix='run-',dir=workdir)); root.chmod(0o700)
(root/'profile').mkdir(); (root/'user').mkdir(); payload=root/'payload'; payload.mkdir()
archive=subprocess.check_output(['git','-C',str(repo),'archive',commit])
subprocess.run(['tar','-xf','-','-C',str(payload)],input=archive,check=True)
# Import fixture only from the verified immutable tree archive, never the mutable checkout.
spec=importlib.util.spec_from_file_location('fixture',payload/'tests/test_native_work_e2e.py'); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
assert hashlib.sha256(module.SAFETY_GUARD.encode()).hexdigest()=='5f0c4fd97681dfafeb3cd487026279b685e260a6518d7ac72b56c4d4c9cca14b'
(root/'guard').mkdir(); (root/'guard/sitecustomize.py').write_text(module.SAFETY_GUARD)
keys={'backup':{'active':'old-export','keys':{'old-export':base64.urlsafe_b64encode(b'e'*32).decode().rstrip('=')}},'notes':{'active':'old-notes','keys':{'old-notes':base64.urlsafe_b64encode(b'n'*32).decode().rstrip('=')}}}
(root/'retained-keyrings.json').write_text(json.dumps(keys)); (root/'retained-keyrings.json').chmod(0o600)
env={'HOME':str(root/'user'),'USERPROFILE':str(root/'user'),'HERMES_HOME':str(root/'profile'),'HERMES_ENABLE_PROJECT_PLUGINS':'0','HERMES_BUNDLED_PLUGINS':str(root/'none'),'PYTHONPATH':os.pathsep.join(map(str,[root/'guard',runtime/'host',payload])),'PYTHONDONTWRITEBYTECODE':'1','CRM_E2E_ROOT':str(root),'CRM_E2E_SOURCE':str(runtime/'host'),'CRM_E2E_PORT':'39291','CRM_E2E_FORBIDDEN_HOME':str(Path.home()),'CRM_E2E_ISOLATION':'in_process'}
results=[]
def run(args,phase=None,input=None,success=True):
    e=dict(env)
    if phase:e['REHEARSAL_PHASE']=phase
    with subprocess.Popen([str(python),'-P',*args],env=e,cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as child:
        try: stdout,stderr=child.communicate(input=input,timeout=90)
        except subprocess.TimeoutExpired:
            child.kill(); child.communicate(); raise
        p=subprocess.CompletedProcess(child.args,child.returncode,stdout,stderr)
        marker=json.loads((root/('guard-ready-'+str(child.pid)+'.json')).read_text())
        assert marker=={'pid':child.pid,'hook_ready':True}
    try: os.kill(child.pid,0)
    except ProcessLookupError: pass
    else: raise AssertionError('Owned child remains alive')
    (root/('log-'+str(len(results))+'.txt')).write_text(p.stdout+p.stderr)
    results.append({'phase':phase or 'recovery-cli','exit':p.returncode,'stdout':p.stdout.strip()})
    assert (p.returncode==0)==success,(p.returncode,p.stdout,p.stderr)
    assert not (root/'forbidden-action.log').exists(),(root/'forbidden-action.log').read_text()
    return p
try:
    for phase in ('seed','reopen'):run([str(here/'phase.py')],phase)
    state=json.loads((root/'state.json').read_text())
    args=['-m','hermes_crm.recovery','--artifact',state['artifact'],'--workspace',state['workspace'],'--profile','synthetic-recovery','--target',str(root/'wrong-key')]
    wrong=json.loads(json.dumps(keys)); wrong['backup']['keys']['old-export']=base64.urlsafe_b64encode(b'z'*32).decode().rstrip('=')
    rejected=run(args,input=json.dumps(wrong),success=False); assert rejected.returncode==1 and rejected.stderr.strip()=='Export could not be authenticated'; assert not (root/'wrong-key').exists()
    args[-1]=str(root/'restored'); run(args,input=json.dumps(keys))
    run([str(here/'phase.py')],'restored')
    run([str(here/'phase.py')],'restored')
    summary={'success':True,'scope':'process-separated content recovery, not host installation/activation or Desktop acceptance','phases':results,'guard_sha256':hashlib.sha256(module.SAFETY_GUARD.encode()).hexdigest(),'jobs_created':0,'network_endpoints_started':0,'all_children_joined':True,'forbidden_events':0,'key_retention':'synthetic old keys retained; new active notes key preserves old decrypt and operation receipt','payload_commit':commit,'payload_tree':tree,'host_commit':host_commit,'python_version':sys.version.split()[0],'phase_sha256':phase_sha,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'guard_ready_pid_checked_each_phase':True}
    # stdout from restore includes private paths/record IDs, exclude from deliverable.
    for item in summary['phases']:item.pop('stdout',None)
    (workdir/'summary.json').write_text(json.dumps(summary,indent=2)); print(json.dumps(summary,indent=2))
finally:
    (workdir/'last-run.txt').write_text(str(root))
