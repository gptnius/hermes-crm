"""Pinned actual-registry/resolver contract; never agents, jobs or web requests."""
import hashlib
import os
from pathlib import Path
import pytest
import test_customization_host as harness

HARNESS_SHA='4dfb2f4846826a87db232f2ec2061b5c9149b889f59ff765c5fc627ab1ce4ced'
GUARD_SHA='4409f7fcf0c2060f62cdd0a3c45b0eed2e8471b74e1378c7d1f6ac7fe7fbff48'

def test_scheduled_research_host_harness_seam():
    assert hashlib.sha256(Path(harness.__file__).read_bytes()).hexdigest()==HARNESS_SHA
    assert hashlib.sha256(harness.SAFETY_GUARD.encode()).hexdigest()==GUARD_SHA
    assert harness.PINNED_HOST_SHA=='2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'
    compile(HOST_CHECK,'<scheduled-research-host-check>','exec')

@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'),reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation',['in_process','host'])
def test_scheduled_research_real_registry_resolver(tmp_path,isolation,monkeypatch):
    test_scheduled_research_host_harness_seam()
    monkeypatch.setattr(harness,'HOST_CHECK',HOST_CHECK)
    harness.test_custom_schema_pinned_host(tmp_path,isolation)

HOST_CHECK=r'''
import json
import os
from pathlib import Path
from datetime import datetime,timedelta,timezone
from ruamel.yaml import YAML
from hermes_cli.plugins import get_plugin_manager
from tools.registry import registry
from toolsets import resolve_toolset
from cron.scheduler import _resolve_cron_enabled_toolsets
manager=get_plugin_manager()
def raw(name,args):
    value=registry.dispatch(name,args,scope=manager.scope_key)
    return json.loads(value) if isinstance(value,str) else value
def tool(name,args):
    value=raw(name,args)
    assert value.get('ok') is True,(name,value)
    return value['data']
try:
    manager.discover_and_load()
    manifest=YAML(typ='safe').load((Path(os.environ['HERMES_HOME'])/'plugins/hermes-crm/plugin.yaml').read_text())
    assert len(manifest['provides_tools'])==len(set(manifest['provides_tools']))==83
    for name in manifest['provides_tools']:assert registry.get_entry(name,scope=manager.scope_key),name
    run={'crm_scheduled_research_run_get','crm_scheduled_research_evidence','crm_scheduled_research_propose','crm_scheduled_research_report'}
    assert set(resolve_toolset('crm_scheduled_research_run_v1'))==run
    assert len(resolve_toolset('crm_read'))==8
    cfg={'mcp_servers':{'synthetic-enabled':{'command':'NEVER-LAUNCH','enabled':True}}}
    for preset,research_tools in [('search',{'web_search'}),('web',{'web_search','web_extract'})]:
        enabled=_resolve_cron_enabled_toolsets({'enabled_toolsets':[preset,'crm_scheduled_research_run_v1','no_mcp']},cfg)
        assert enabled==[preset,'crm_scheduled_research_run_v1'],enabled
        resolved={tool_name for ts in enabled for tool_name in resolve_toolset(ts)}
        assert resolved==run|research_tools,resolved
    contact=tool('crm_contact_create',{'name':'Synthetic registry subject'})
    task=tool('crm_task_create',{'title':'Synthetic research task','contact_id':contact['id'],'due_at':'2030-04-02T12:00:00Z'})
    intent={'task_id':task['id'],'task_version':task['version'],'human_owner':'Synthetic owner',
        'target_kind':'contacts','target_id':contact['id'],'target_version':contact['version'],
        'public_question':'Synthetic fixture only; do not fetch',
        'run_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),
        'research':'web','propose_note':True,'max_sources':1}
    a=tool('crm_scheduled_research_create',{'data':intent,'idempotency_key':'host-intent'})
    assert a['state']=='pending' and a['job_id'] is None
    assert tool('crm_scheduled_research_get',{'assignment_id':a['id']})['id']==a['id']
    assert tool('crm_scheduled_research_list',{'task_id':task['id']})[0]['id']==a['id']
    denied=raw('crm_scheduled_research_run_get',{'assignment_id':a['id'],'generation':1})
    assert denied.get('ok') is False and denied.get('status')==403,denied
    assert not list(Path(os.environ['HERMES_HOME']).rglob('jobs.json'))
    print('PASS custom-schema actual-host contract')
finally:
    host=getattr(manager,'_plugin_host_instance',None)
    manager.unload()
    if host is not None:
        host.shutdown()
        assert not host.alive
    assert not list(Path(os.environ['HERMES_HOME']).rglob('*.sock'))
'''
