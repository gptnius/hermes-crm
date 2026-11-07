"""Pinned actual registration, authorization and command-context tests, socket-free.

The unchanged hardened Desktop harness constructs isolated HOME/environment,
blocks original HOME, networking/model imports, and admits only exact official
hosted-plugin children plus read-only pinned Git probes. The real scheduler
handler is replaced by synthetic responses before any command; no jobs run or
are created. Real SessionAuthority/AuthorityConnection/LocalSessionAdapter and
native command-context machinery remain unchanged in both isolation modes.
"""
import os

import pytest
import test_desktop_host as desktop_contract


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_registered_native_command_authority_and_context(tmp_path, monkeypatch, isolation):
    monkeypatch.setattr(desktop_contract, 'HOST_CHECK', HOST_CHECK)
    desktop_contract.test_official_dashboard_discovery_auth_crud_tools_and_profiles(tmp_path, isolation)


HOST_CHECK = r'''
import asyncio
import copy
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient
from hermes_cli import web_server as host
from hermes_cli.plugins import get_plugin_manager, get_plugin_command_handler
from tools.registry import registry
from tools import cronjob_tools
from gateway.config import GatewayConfig, Platform
from gateway.session import SessionStore, SessionSource
from gateway.session_authority import SessionAuthority, LiveSession
from gateway.session_controls import AuthorityConnection
from gateway.session_local import LocalSessionAdapter, create_local_session
from gateway.session_contract import SessionActor
from hermes_state_runtime import begin_runtime_epoch
from hermes_state_local import local_receipt
from gateway.session_policy import LocalSessionPolicy
from gateway.run import GatewayRunner

root = Path(os.environ['CRM_DESKTOP_TEST_ROOT'])
home = Path(os.environ['HERMES_HOME'])
assert json.loads((root / ('guard-ready-' + str(os.getpid()) + '.json')).read_text())['hook_ready']
manager = get_plugin_manager()
manager.discover_and_load()
assert get_plugin_command_handler('crm-assignment') is None
assert len(manager._plugin_tool_names) == 22

calls, jobs = [], {}

def synthetic_cron(args, **kwargs):
    assert '_operation_guard' not in kwargs
    assert kwargs['platform'] == 'local'
    assert kwargs['session_id'] in fixture_sessions
    assert kwargs['session_key'] == fixture_sessions[kwargs['session_id']].session_key
    calls.append((copy.deepcopy(args), {k: kwargs[k] for k in ('session_id', 'session_key', 'platform')}))
    action = args['action']
    if action == 'create':
        assert args['paused'] is True and args['deliver'] == 'local'
        assert args['enabled_toolsets'] == ['crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp']
        ident = 'synthetic-job-' + str(len(jobs) + 1)
        job = dict(job_id=ident, name=args['name'], enabled=False, state='paused', next_run_at=None,
            prompt_preview=args['prompt'][:100]+'...', skills=[], model=None, provider=None, base_url=None,
            pinned=False, repeat='once', schedule='once at '+datetime.fromisoformat(args['schedule']).strftime('%Y-%m-%d %H:%M'),
            enabled_toolsets=args['enabled_toolsets'], deliver='local', expected_instant=args['schedule'])
        jobs[ident] = job
        result = dict(success=True, job_id=ident, job=job, gateway_running=True)
    elif action == 'resume':
        job = jobs[args['job_id']]
        job.update(enabled=True, state='scheduled', next_run_at=job['expected_instant'])
        result = dict(success=True, job=job)
    elif action == 'list':
        result = dict(success=True, jobs=list(jobs.values()), gateway_running=True)
    elif action == 'pause':
        job = jobs[args['job_id']]
        job.update(enabled=False, state='paused', next_run_at=None)
        result = dict(success=True, job=job)
    else:
        raise AssertionError('Unexpected synthetic scheduler action')
    return json.dumps(result)

entry = registry.get_entry('cronjob_manage', scope=manager.scope_key)
assert entry is not None
entry.handler = synthetic_cron

# Real authority/session/registered-source state, without starting a gateway or
# executing a model turn. The runner constructor and startup are not invoked.
runner = GatewayRunner.__new__(GatewayRunner)
runner._draining = False
runner.config = GatewayConfig()
# Upstream's test-isolation guard intentionally refuses HOME/.hermes/state.db
# even when HOME was freshly constructed. Use its documented explicit db_path
# instead, with the real SessionDB and unchanged guard/authorization behavior.
class FixtureSessionStore(SessionStore):
    def _open_session_db_for_active_scope(self, db_path=None):
        return super()._open_session_db_for_active_scope(root / 'command-state.db')
runner.session_store = FixtureSessionStore(root / 'command-sessions', runner.config)
runner.session_authority = SessionAuthority(runner, profile_id=str(home), instance_id='fixture-instance',
    db=runner.session_store._db, epoch=begin_runtime_epoch(runner.session_store._db, instance_id='fixture-instance'))
authority = runner.session_authority
adapter = LocalSessionAdapter(authority)
runner.adapters = {Platform.LOCAL: adapter}
runner._primary_profile_name = 'default'
fixture_sessions = {}

def make_session(request_id, owner):
    params = dict(request_id=request_id, source='gui', cwd=str(root), model='fixture-no-model-executed', toolsets=[])
    policy = LocalSessionPolicy(source='gui', platform='desktop', cwd=str(root), model=params['model'],
        toolsets=(), config_json='{}', request_json=json.dumps({k:v for k,v in params.items() if k != 'request_id'}), terminal_json=json.dumps({'TERMINAL_CWD':str(root)}))
    actor = SessionActor(owner, str(home), frozenset({'session:create','session:read','session:control','session:respond'}), 'fixture-bootstrap')
    ref = create_local_session(authority, actor, params, trusted_policy=policy)
    live = authority.sessions[ref.session_id]
    stored = runner.session_store.lookup_by_session_key(live.route)
    assert stored.session_id == ref.session_id
    assert authority.db.get_session(ref.session_id)['user_id'] == owner
    assert local_receipt(authority.db, ref.session_id)['principal_id'] == owner
    assert adapter.authorize_source(live.source) is True
    fixture_sessions[stored.session_id] = stored
    return live.source, stored

source, session = make_session('local-fixture-one', 'fixture-owner')
other_source, other_session = make_session('local-fixture-two', 'fixture-owner')

client = TestClient(host.app, base_url='http://localhost')
prefix = '/api/plugins/hermes-crm'
headers = {'Authorization': 'Bearer ' + host._SESSION_TOKEN}

def api(method, path, expected=200, **kwargs):
    response = client.request(method, prefix + path, headers=headers, **kwargs)
    assert response.status_code == expected, (method, path, response.status_code, response.text)
    return response.json()

for path in ('/work-operations', '/work-operations/00000000-0000-0000-0000-000000000000'):
    assert client.get(prefix+path, params={'workspace_token':'not-auth'}).status_code == 401
assert client.post(prefix+'/work-operations', json={}).status_code == 401
meta = api('GET', '/meta')
token = meta['workspace_token']
command_name = meta['work_command_name']
assert command_name.startswith('crm-assignment-') and len(command_name) == 47
assert get_plugin_command_handler(command_name) is not None
task = api('POST', '/tasks', 201, json={'workspace_token':token, 'data':{'title':'Synthetic command analysis','due_at':'2099-05-01T00:00:00Z'}})
work = api('POST', '/work', 201, json=dict(workspace_token=token, task_id=task['id'], expected_task_version=task['version'],
    human_owner='Synthetic owner', prompt='Read existing CRM records only', success_criteria='Report concise limitations',
    run_at='2099-04-01T12:00:00Z', idempotency_key='fixture-assignment'))

def prepare(verb, assignment, key):
    return api('POST', '/work-operations', 201, json=dict(workspace_token=token, verb=verb,
        assignment_id=assignment['id'], expected_assignment_version=assignment['version'],
        intended_session_id=session.session_id, idempotency_key=key))

operation = prepare('schedule', work, 'fixture-schedule')
assert operation['state'] == 'prepared' and calls == []
assert operation['command_name'] == command_name
for extra in ({'approved':True}, {'source':{}}, {'profile':'foreign'}, {'snapshot':{}}):
    api('POST', '/work-operations', 422, json=dict(workspace_token=token, verb='schedule', assignment_id=work['id'],
        expected_assignment_version=work['version'], intended_session_id=session.session_id, idempotency_key='bad', **extra))

async def check_commands():
    connections = []
    async def dispatch(identity, operation_id=operation['id'], sid=session.session_id, extra=None):
        connection = AuthorityConnection(authority, object(), identity)
        connections.append(connection)
        params = dict(session_id=sid, profile='default', name=command_name, arg=operation_id)
        params.update(extra or {})
        return await connection.dispatch({'id':len(connections), 'method':'command.dispatch', 'params':params})
    owner = {'user_id':'fixture-owner', 'provider':'local', 'profile_id':str(home),
        'instance_id':'fixture-instance', 'capabilities':['session:read','session:control','session:respond']}
    # Public catalog is read-only and scoped to this exact native session.
    catalog_connection = AuthorityConnection(authority, object(), owner)
    connections.append(catalog_connection)
    async def catalog():
        response = await catalog_connection.dispatch({'id':1000, 'method':'commands.catalog',
            'params':{'session_id':session.session_id,'profile':'default'}})
        assert 'result' in response, response
        return response['result']
    discovered = await catalog()
    assert discovered['warning'] == '' and discovered['plugin_discovery_error'] == '', discovered
    assert command_name in discovered['plugin_commands']
    assert any(c['name'] == 'Plugin commands' and any(p[0] == '/'+command_name for p in c['pairs']) for c in discovered['categories'])
    # Resolution-only collision regressions. No exec/shell is ever dispatched.
    from unittest.mock import patch
    from gateway.session_commands import _runner_command, _resolve_alias
    for quick_name in ('crm-assignment', command_name):
        config = {'quick_commands':{quick_name:{'type':'exec','command':'NEVER_EXECUTE_FIXTURE_COMMAND'}}}
        with patch('gateway.run._load_gateway_config', return_value=config), patch('hermes_cli.config.load_config_readonly', return_value=config):
            colliding = await catalog()
            assert any(c['name'] == 'User commands' and any(p[0] == '/'+quick_name for p in c['pairs']) for c in colliding['categories'])
            if quick_name == 'crm-assignment':
                assert _runner_command(command_name) == ('plugin', command_name)
            else:
                assert _runner_command(command_name)[0] == 'exec'
                assert command_name in colliding['plugin_commands']  # presence alone is unsafe
                assert not any(c['name'] == 'Plugin commands' and any(p[0] == '/'+command_name for p in c['pairs']) for c in colliding['categories'])
    with patch('gateway.run._load_gateway_config', return_value={'quick_commands':{command_name:{'type':'alias','target':'/help'}}}):
        assert _resolve_alias(command_name, operation['id'])[0] == 'help'
    assert calls == []
    for identity, reason in [
        (dict(owner, user_id='someone-else'), 'permission_denied'),
        (dict(owner, capabilities=['session:read']), 'permission_denied'),
        (dict(owner, profile_id='foreign'), 'profile_mismatch'),
        (dict(owner, instance_id='old-instance'), 'permission_denied')]:
        result = await dispatch(identity)
        assert result.get('error',{}).get('message') == reason, result
    for extra in ({'approved':True}, {'source':'local'}, {'session_key':session.session_key}):
        result = await dispatch(owner, extra=extra)
        assert result.get('error',{}).get('message') == 'invalid_params', result
    result = await dispatch(owner, extra={'profile':'foreign'})
    assert result.get('error',{}).get('message') == 'profile_mismatch', result
    # This second session has the same authenticated owner but is not the one
    # frozen into the operation. The actual host context must reach the plugin.
    result = await dispatch(owner, sid=other_session.session_id)
    refused = json.loads(result['result']['output'])
    assert refused['ok'] is False and refused['status'] == 403, result
    assert calls == []
    result = await dispatch(owner)
    assert result['result']['type'] == 'exec', result
    scheduled = json.loads(result['result']['output'])
    assert scheduled['ok'] and scheduled['operation']['state'] == 'finished', result
    assert scheduled['operation']['actual_session_id'] == session.session_id
    assert scheduled['operation']['provenance'] == 'authenticated_local_command'
    assert scheduled['operation']['authorization_channel'] == 'crm_user_command'
    assert [a['action'] for a,c in calls] == ['create','resume']
    replay = json.loads((await dispatch(owner))['result']['output'])
    assert replay == scheduled and len(calls) == 2
    observation = prepare('check', scheduled['operation']['result'], 'fixture-check')
    checked = json.loads((await dispatch(owner, observation['id']))['result']['output'])
    assert checked['operation']['state'] == 'finished' and calls[-1][0]['action'] == 'list'
    cancellation = prepare('cancel', checked['operation']['result'], 'fixture-cancel')
    cancelled = json.loads((await dispatch(owner, cancellation['id']))['result']['output'])
    assert cancelled['operation']['state'] == 'finished' and cancelled['operation']['result']['state'] == 'cancelled'
    assert calls[-1][0]['action'] == 'pause' and calls[-1][0]['job_id'] == 'synthetic-job-1'
    for connection in connections:
        await connection.close()

asyncio.run(check_commands())
assert api('GET','/tasks/'+task['id'])['status'] == 'open'
page = api('GET','/work-operations', params={'workspace_token':token,'task_id':task['id']})
assert page['total'] == 3 and all(row['task_id'] == task['id'] for row in page['items'])
# Real secondary profile REST/IPC preserves namespace. Accessing its metadata
# exercises the unchanged guarded child even for in-process root isolation.
other_meta = api('GET','/meta?profile=crm-test-other')
assert other_meta['workspace_token'] != token
api('GET','/work-operations/'+operation['id'], 409, params={'profile':'crm-test-other','workspace_token':token})
api('GET','/work-operations/'+operation['id'], 404, params={'profile':'crm-test-other','workspace_token':other_meta['workspace_token']})
assert api('GET','/work-operations', params={'profile':'crm-test-other','workspace_token':other_meta['workspace_token']})['items'] == []
assert not list(home.rglob('jobs.json')), 'Synthetic registry boundary must never create native jobs'
assert 'run_agent' not in __import__('sys').modules
if getattr(runner, '_executor', None) is not None:
    runner._executor.shutdown(wait=True)
print('PASS native host: actual command registration/catalog, durable fixture session creation, collision detection, actor/capability/profile/source admission, strict args, real session context, hosted IPC, exact-once CRM commands, read-only recovery and secondary isolation; synthetic scheduler responses only, no sockets/jobs/models')
'''
