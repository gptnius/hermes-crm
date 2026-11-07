"""Separate opt-in CRM command → real scheduled agent → authenticated report proof.

Reuses the existing due-run harness and its SAFETY_GUARD unchanged. Only setup
admission changes: authenticated CRM REST prepares the exact operation, a real
native session command schedules/cancels, and the original actual scheduler,
AIAgent, deferred discovery, report, timing and cleanup assertions still run.
The model is the same deterministic keyless loopback fixture, not a real provider.
"""
import os
import sys

import pytest
import test_native_work_e2e as due_contract


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.skipif(os.environ.get('HERMES_NATIVE_E2E') != '1' or os.environ.get('HERMES_NATIVE_COMMAND_E2E') != '1',
                    reason='Requires both guarded due-run and command-path explicit opt-ins')
@pytest.mark.skipif(sys.version_info[:3] != (3, 14, 9), reason='Requires exact source-pinned guard runtime CPython 3.14.9')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_crm_command_real_due_scheduler_and_report(tmp_path, monkeypatch, isolation):
    original_guard = due_contract.SAFETY_GUARD
    code = command_due_check(due_contract.E2E_CHECK)
    monkeypatch.setattr(due_contract, 'E2E_CHECK', code)
    assert due_contract.SAFETY_GUARD == original_guard
    due_contract.test_native_work_real_due_scheduler_loopback_model(tmp_path, isolation)
    import json
    evidence = json.loads((tmp_path / 'evidence.json').read_text())
    assert [item['verb'] for item in evidence['crm_user_commands']] == ['schedule','schedule','cancel']
    assert all(item['provenance'] == 'authenticated_local_command' for item in evidence['crm_user_commands'])
    assert evidence['command_session_durable'] is True
    assert evidence['canonical_admission_verified'] and evidence['local_output_verified']
    assert evidence['cancelled_before_due_never_executed'] is True


def command_due_check(base):
    """Exact bounded replacements fail closed if the reviewed base fixture drifts."""
    def replace(old, new):
        nonlocal base
        assert base.count(old) == 1, 'Base fixture changed; re-review command integration seam'
        base = base.replace(old, new)

    replace("authority = await initialize_session_authority(runner, profile_id='default', instance_id='synthetic-e2e')",
            "authority = await initialize_session_authority(runner, profile_id=str(home), instance_id='synthetic-e2e')")
    replace("evidence['creator_context_contract'] = 'AIAgent object in-process; official Opaque(AIAgent) over host wire; origin session ContextVar preserved'",
            "evidence['creator_context_contract'] = 'Setup assignment uses registered CRM tools; scheduling and cancellation use authenticated CRM user commands, not a model turn.'\n" + COMMAND_SETUP)
    replace("""        parent = context.get('parent_agent')
        if os.environ['CRM_E2E_ISOLATION'] == 'host':
            assert isinstance(parent, Opaque) and parent.type_name == 'AIAgent'
        else:
            assert parent is creator
        assert context['session_id'] == 'synthetic-creator'
        assert context['task_id'] == 'synthetic-scheduling-turn'
        assert get_session_env('HERMES_SESSION_ID') == 'synthetic-creator'""", """        assert context.get('parent_agent') is None, 'Command does not claim a current model-turn parent'
        assert context['session_id'] == command_ref.session_id
        assert context['session_key'] == command_live.route
        assert context['platform'] == 'local'
        assert '_operation_guard' not in context
        assert get_session_env('HERMES_SESSION_ID') == command_ref.session_id""")
    replace("""        work = tool('crm_work_schedule', {'assignment_id': work['id']}, parent_agent=creator,
                    session_id='synthetic-creator', task_id='synthetic-scheduling-turn')""",
            "        work = await user_command('schedule', work, 'command-schedule-due')")
    replace("""        cancelled = tool('crm_work_schedule', {'assignment_id': cancelled['id']}, parent_agent=creator)
        cancelled = tool('crm_work_cancel', {'assignment_id': cancelled['id'], 'version': cancelled['version']},
                         parent_agent=creator)""", """        cancelled = await user_command('schedule', cancelled, 'command-schedule-cancelled')
        cancelled = await user_command('cancel', cancelled, 'command-cancel-before-due')""")
    replace("""    finally:
        stop.set()""", """    finally:
        await command_connection.close()
        stop.set()""")
    replace("for name in ('hermes_crm/native_work.py', 'hermes_crm/plugin.py', 'hermes_crm/native_api.py', 'plugin.yaml')}",
            "for name in ('hermes_crm/native_work.py', 'hermes_crm/native_work_operations.py', 'hermes_crm/native_work_commands.py', 'hermes_crm/native_work_operations_api.py', 'hermes_crm/plugin.py', 'hermes_crm/native_api.py', 'plugin.yaml')}")
    return base


COMMAND_SETUP = r'''
    from fastapi.testclient import TestClient
    from hermes_cli import web_server as command_host
    from gateway.session_controls import AuthorityConnection
    from gateway.session_contract import SessionActor
    from gateway.session_local import create_local_session
    from gateway.session_policy import LocalSessionPolicy
    from hermes_state_local import local_receipt
    command_owner = 'synthetic-crm-user-command-owner'
    command_actor = SessionActor(command_owner, str(home),
        frozenset({'session:create','session:read','session:control','session:respond'}), 'fixture-user-command')
    command_params = dict(request_id='fixture-crm-user-command', source='gui', cwd=str(root),
                          model='synthetic-crm-fixture', toolsets=[])
    command_policy = LocalSessionPolicy(source='gui', platform='desktop', cwd=str(root),
        model='synthetic-crm-fixture', toolsets=(), config_json='{}',
        request_json=json.dumps({k:v for k,v in command_params.items() if k != 'request_id'}),
        terminal_json=json.dumps({'TERMINAL_CWD':str(root)}))
    command_ref = create_local_session(authority, command_actor, command_params, trusted_policy=command_policy)
    command_live = authority.sessions[command_ref.session_id]
    assert authority.db.get_session(command_ref.session_id)['user_id'] == command_owner
    assert local_receipt(authority.db, command_ref.session_id)['principal_id'] == command_owner
    evidence['command_session_durable'] = True
    command_connection = AuthorityConnection(authority, object(), {
        'user_id':command_owner, 'provider':'local', 'profile_id':str(home), 'instance_id':'synthetic-e2e',
        'capabilities':['session:read','session:control','session:respond']})
    command_client = TestClient(command_host.app, base_url='http://localhost')
    command_prefix = '/api/plugins/hermes-crm'
    command_headers = {'Authorization':'Bearer '+command_host._SESSION_TOKEN}
    assert command_client.get(command_prefix+'/work-operations').status_code == 401
    response = command_client.get(command_prefix+'/meta', headers=command_headers)
    assert response.status_code == 200, response.text
    command_meta = response.json()
    command_token, native_command_name = command_meta['workspace_token'], command_meta['work_command_name']
    assert native_command_name.startswith('crm-assignment-') and len(native_command_name) == 47
    evidence['crm_user_commands'] = []

    async def user_command(verb, reviewed_assignment, key):
        prepared = command_client.post(command_prefix+'/work-operations', headers=command_headers, json={
            'workspace_token':command_token, 'verb':verb, 'assignment_id':reviewed_assignment['id'],
            'expected_assignment_version':reviewed_assignment['version'],
            'intended_session_id':command_ref.session_id, 'idempotency_key':key})
        assert prepared.status_code == 201, prepared.text
        operation = prepared.json()
        assert operation['state'] == 'prepared' and operation['command_name'] == native_command_name
        assert operation['snapshot']['assignment']['payload'] == reviewed_assignment['payload']
        catalog_reply = await command_connection.dispatch({'id':key+'-catalog', 'method':'commands.catalog',
            'params':{'session_id':command_ref.session_id,'profile':'default'}})
        assert 'result' in catalog_reply, catalog_reply
        catalog = catalog_reply['result']
        assert catalog['warning'] == catalog['plugin_discovery_error'] == ''
        assert native_command_name in catalog['plugin_commands']
        matching_categories = [c['name'] for c in catalog['categories']
            if any(pair[0].lower() == '/'+native_command_name for pair in c['pairs'])]
        assert matching_categories == ['Plugin commands'], matching_categories
        result = await command_connection.dispatch({'id':key, 'method':'command.dispatch', 'params':{
            'session_id':command_ref.session_id,'profile':'default','name':native_command_name,'arg':operation['id']}})
        assert result.get('result',{}).get('type') == 'exec', result
        output = json.loads(result['result']['output'])
        assert output['schema_version'] == 1 and output['ok'] is True, output
        receipt = output['operation']
        assert receipt['id'] == operation['id'] and receipt['state'] == 'finished', receipt
        assert receipt['actual_session_id'] == command_ref.session_id
        assert receipt['provenance'] == 'authenticated_local_command'
        assert receipt['authorization_channel'] == 'crm_user_command'
        recovered = command_client.get(command_prefix+'/work-operations/'+operation['id'],
            headers=command_headers, params={'workspace_token':command_token})
        assert recovered.status_code == 200 and recovered.json() == receipt
        evidence['crm_user_commands'].append({
            'verb':verb, 'operation_id':receipt['id'], 'session_id':receipt['actual_session_id'],
            'command_name':native_command_name, 'provenance':receipt['provenance'],
            'assignment_id':receipt['assignment_id'], 'state':receipt['state']})
        return receipt['result']
'''
