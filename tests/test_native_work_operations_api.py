"""Manually mounted candidate router; shipping API remains deliberately unchanged."""
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from hermes_crm.domain import CRM
from hermes_crm import native_api
from hermes_crm.native_work import NativeWorkStore
from hermes_crm.native_work_commands import register_work_command
from hermes_crm.native_work_operations import WorkOperationStore, operations
from hermes_crm.native_work_operations_api import build_router
from test_native_work_operations import context
from test_native_work import Host


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    state = {'profile':'synthetic'}
    def factory(): return CRM(f'sqlite:///{tmp_path}/{state["profile"]}.db', profile=state['profile'])
    monkeypatch.setattr(native_api, 'open_profile_crm', factory)
    app = FastAPI()
    app.include_router(build_router(native_api.service, native_api.require_workspace), prefix='/api/plugins/hermes-crm')
    crm = factory()
    try:
        task = crm.create('tasks', {'title':'Synthetic native command analysis', 'due_at':'2099-05-01T00:00:00Z'})
        assignment = NativeWorkStore(crm).create(task_id=task['id'], human_owner='Synthetic owner',
            prompt='Analyze internal CRM only', success_criteria='Report reviewed limitations',
            run_at='2099-04-01T12:00:00Z', idempotency_key='assignment')
        token = crm.workspace_token()
    finally: crm.close()
    body = dict(workspace_token=token, verb='schedule', assignment_id=assignment['id'],
                expected_assignment_version=1, intended_session_id='native-session-1', idempotency_key='operation')
    return TestClient(app), state, factory, body


PREFIX = '/api/plugins/hermes-crm/work-operations'


def test_prepare_status_and_withdraw_never_dispatch(candidate):
    client, state, factory, body = candidate
    prepared = client.post(PREFIX, json=body)
    assert prepared.status_code == 201
    operation = prepared.json()
    assert operation['state'] == 'prepared' and operation['provenance'] is None
    assert operation['profile'] == state['profile'] and operation['workspace_token'] == body['workspace_token']
    assert client.post(PREFIX, json=body).json()['id'] == operation['id']
    params = {'workspace_token':body['workspace_token']}
    assert client.get(PREFIX+'/'+operation['id'], params=params).json() == operation
    page = client.get(PREFIX, params=params).json()
    assert page['items'] == [operation] and page['total'] == 1
    assert page['profile'] == state['profile'] and page['workspace_token'] == body['workspace_token']
    assert client.post(PREFIX+'/'+operation['id']+'/withdraw', json=params).json()['state'] == 'withdrawn'
    crm = factory()
    try:
        assert NativeWorkStore(crm).get(body['assignment_id'])['state'] == 'pending'
        assert NativeWorkStore(crm).get(body['assignment_id'])['job_id'] is None
    finally: crm.close()


@pytest.mark.parametrize('extra', [dict(approved=True), dict(snapshot={}), dict(profile='another'), dict(source={}),
    dict(expected_assignment_version=True), dict(expected_assignment_version='1'), dict(verb='immediate'),
    dict(session_key='fake'), dict(ctx={}), dict(dispatch=True)])
def test_strict_prepare_schema_rejects_client_authority(candidate, extra):
    client, _, _, body = candidate
    response = client.post(PREFIX, json=dict(body, **extra))
    assert response.status_code == 422


def test_profile_switch_and_token_change_reject_reads_and_writes(candidate):
    client, state, factory, body = candidate
    operation = client.post(PREFIX, json=body).json()
    state['profile'] = 'another'
    assert client.post(PREFIX, json=body).status_code == 409
    params = {'workspace_token':body['workspace_token']}
    assert client.get(PREFIX+'/'+operation['id'], params=params).status_code == 409
    assert client.post(PREFIX+'/'+operation['id']+'/withdraw', json=params).status_code == 409
    crm = factory()
    try: token = crm.workspace_token()
    finally: crm.close()
    assert client.get(PREFIX+'/'+operation['id'], params={'workspace_token':token}).status_code == 404


def test_unknown_repeated_and_authority_query_parameters_rejected(candidate):
    client, _, _, body = candidate
    operation = client.post(PREFIX, json=body).json()
    token = body['workspace_token']
    for query in ('approved=true', 'source=local', 'limit=1&limit=2', 'offset=-1', 'limit=01x'):
        assert client.get(PREFIX+'?workspace_token='+token+'&'+query).status_code in (400,422)
    assert client.get(PREFIX+'/'+operation['id']+'?workspace_token='+token+'&approved=true').status_code == 400
    assert client.post(PREFIX+'?approved=true', json=body).status_code == 400
    assert client.post(PREFIX+'/'+operation['id']+'/withdraw', json={'workspace_token':token,'approved':True}).status_code == 422


def test_read_pages_do_not_create_operation_table(candidate):
    client, _, factory, body = candidate
    crm = factory()
    try: before = inspect(crm.engine).get_table_names()
    finally: crm.close()
    assert operations.name not in before
    assert client.get(PREFIX, params={'workspace_token':body['workspace_token']}).json()['items'] == []
    crm = factory()
    try: assert inspect(crm.engine).get_table_names() == before
    finally: crm.close()


def test_register_command_uses_real_context_and_versioned_json(candidate):
    client, _, factory, body = candidate
    operation = client.post(PREFIX, json=body).json()
    host = Host()
    registered = {}
    def register(name, handler, **kwargs): registered.update(name=name, handler=handler, **kwargs)
    host.register_command = register
    register_work_command(host, factory)
    assert registered['name'] == operation['command_name'] and registered['argument_mode'] == 'text'
    assert registered['name'].startswith('crm-assignment-') and len(registered['name']) == 47
    result = json.loads(registered['handler'](operation['id'], **context()))
    assert result['schema_version'] == 1 and result['ok'] is True
    assert result['operation']['state'] == 'finished'
    assert result['operation']['provenance'] == 'authenticated_local_command'
    assert len(host.calls) == 2
    for bad in (operation['id']+' approved=true', json.dumps({'id':operation['id'],'approved':True}), ' '+operation['id']):
        assert json.loads(registered['handler'](bad, **context()))['ok'] is False
    assert len(host.calls) == 2


def test_command_registration_failure_is_sanitized_and_has_no_fallback():
    from hermes_crm.domain import CRMError
    host = Host()
    registered = {}
    host.register_command = lambda name, handler, **kwargs: registered.update(handler=handler)
    def broken(): raise RuntimeError('postgresql://user:private-secret@private.invalid/db')
    with pytest.raises(CRMError, match='registration unavailable') as caught:
        register_work_command(host, broken)
    assert 'private-secret' not in str(caught.value) and not registered


def test_candidate_has_no_rest_execute_approve_schedule_or_native_context(candidate):
    client, _, _, body = candidate
    operation = client.post(PREFIX, json=body).json()
    for suffix in ('execute', 'approve', 'dispatch', 'schedule', 'confirm'):
        assert client.post(PREFIX+'/'+operation['id']+'/'+suffix, json={'approved':True}).status_code == 404



def test_registered_name_is_scope_stable_and_refuses_changed_backend(candidate):
    client, state, factory, body = candidate
    operation = client.post(PREFIX, json=body).json()
    host = Host()
    registered = []
    host.register_command = lambda name, handler, **kwargs: registered.append((name,handler))
    register_work_command(host, factory)
    register_work_command(host, factory)
    assert registered[0][0] == registered[1][0] == operation['command_name']
    state['profile'] = 'other'
    register_work_command(host, factory)
    assert registered[-1][0] != registered[0][0]
    result = json.loads(registered[0][1](operation['id'], **context()))
    assert result['ok'] is False and result['status'] == 409
    assert host.calls == []
