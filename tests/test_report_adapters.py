"""Typed report and authored-log parity across REST and registered agent tools.

Host authentication and real profile IPC are covered by test_desktop_host.
This fixture is intentionally local and never dispatches cron or a provider.
"""
import uuid

import pytest

from test_native_work_adapters import (
    adapters, REPORT_READ, REPORT_WRITE, INTERACTION_READ, INTERACTION_WRITE,
)
from hermes_crm.native_work import TOOLSETS


DEFINITION = {'entity': 'contacts', 'columns': ['id', 'name']}
REPORT_TOOLS = REPORT_READ | REPORT_WRITE | INTERACTION_READ | INTERACTION_WRITE


def invoke(a, name, args):
    result = a.ctx.invoke(name, args)
    assert result['ok'], result
    return result['data']


def token(a):
    return a.client.get('/meta').json()['workspace_token']


def request(a, method, path, expected=200, **kwargs):
    result = a.client.request(method, path, **kwargs)
    assert result.status_code == expected, result.text
    return result.json()


def create(a):
    return invoke(a, 'crm_report_create', dict(title='People', definition=DEFINITION, idempotency_key='create'))


def test_dedicated_tools_never_expand_saved_cron_authority(adapters):
    assert len(adapters.ctx.tools) == 73
    for names, toolset in ((REPORT_READ, 'crm_reports'), (REPORT_WRITE, 'crm_report_write'),
                           (INTERACTION_READ, 'crm_interaction_read'), (INTERACTION_WRITE, 'crm_interaction_write')):
        for name in names:
            registered = adapters.ctx.tools[name]
            assert registered['toolset'] == toolset
            assert registered['schema']['parameters']['additionalProperties'] is False
    assert tuple(TOOLSETS) == ('crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp')
    assert not adapters.factory_calls and not adapters.ctx.calls


@pytest.mark.parametrize('name', sorted(REPORT_TOOLS))
@pytest.mark.parametrize('args', [None, [], 'object', {'unexpected': True}])
def test_strict_tool_inputs_before_opening_backend(adapters, name, args):
    result = adapters.ctx.invoke(name, args)
    assert result['ok'] is False and result['status'] in {400, 422}
    assert adapters.factory_calls == [] and adapters.ctx.calls == []


@pytest.mark.parametrize('name,args', [
    ('crm_report_run', {'definition': DEFINITION, 'limit': True}),
    ('crm_report_list', {'include_archived': 'false'}),
    ('crm_report_get', {'report_id': 'id', 'version': '1'}),
    ('crm_saved_report_run', {'report_id': 'id', 'expected_version': True}),
    ('crm_dashboard_save', {'cards': [], 'expected_version': False, 'idempotency_key': 'x'}),
    ('crm_contact_log_list', {'contact_id': 'id', 'offset': -1}),
    ('crm_contact_log_void', {'interaction_id': 'id', 'expected_version': 1, 'reason': 'x', 'idempotency_key': 'x', 'actor': 'forged'}),
])
def test_strict_types_and_no_authority_injection(adapters, name, args):
    result = adapters.ctx.invoke(name, args)
    assert not result['ok'] and result['status'] == 422
    assert not adapters.factory_calls and not adapters.ctx.calls


def test_catalog_preview_and_saved_dashboard_cross_adapter_parity(adapters):
    a = adapters
    t = token(a)
    contact = invoke(a, 'crm_contact_create', {'name': 'Synthetic Person'})
    assert request(a, 'GET', '/analytics/catalog', params={'workspace_token': t}) == invoke(a, 'crm_report_catalog', {})
    args = dict(definition=DEFINITION, evaluated_at='2026-01-01T00:00:00Z')
    preview = request(a, 'POST', '/analytics/run', json=dict(args, workspace_token=t))
    agent_preview = invoke(a, 'crm_report_run', args)
    # Observation timestamps intentionally reflect separate live reads.
    assert {k: v for k, v in preview.items() if k != 'observed_at'} == {k: v for k, v in agent_preview.items() if k != 'observed_at'}
    assert preview['items'][0]['id'] == contact['id']
    payload = dict(title='People', definition=DEFINITION, idempotency_key='create')
    saved = request(a, 'POST', '/analytics/reports', 201, json=dict(payload, workspace_token=t))
    assert invoke(a, 'crm_report_create', payload) == saved
    assert request(a, 'GET', '/analytics/reports/'+saved['id'], params={'workspace_token': t}) == saved
    assert request(a, 'GET', '/analytics/reports', params={'workspace_token': t}) == invoke(a, 'crm_report_list', {})
    card = dict(id=str(uuid.uuid4()), report_id=saved['id'], report_version=1, visualization='table')
    dash_args = dict(cards=[card], expected_version=0, idempotency_key='dashboard')
    dashboard = invoke(a, 'crm_dashboard_save', dash_args)
    assert request(a, 'PUT', '/analytics/dashboard', json=dict(dash_args, workspace_token=t)) == dashboard
    assert request(a, 'GET', '/analytics/dashboard', params={'workspace_token': t}) == invoke(a, 'crm_dashboard_get', {})
    assert not a.ctx.calls


def test_current_version_guard_archive_and_explicit_dashboard_adoption(adapters):
    a = adapters; t = token(a); saved = create(a); path = '/analytics/reports/'+saved['id']
    card = dict(id=str(uuid.uuid4()), report_id=saved['id'], report_version=1, visualization='table')
    invoke(a, 'crm_dashboard_save', dict(cards=[card], expected_version=0, idempotency_key='dash'))
    update = dict(title='Renamed', definition=DEFINITION, expected_version=1, idempotency_key='edit')
    newer = request(a, 'PATCH', path, json=dict(update, workspace_token=t))
    assert invoke(a, 'crm_report_update', dict(update, report_id=saved['id'])) == newer
    request(a, 'GET', path, 409, params={'workspace_token': t, 'version': 1})
    assert a.ctx.invoke('crm_report_get', dict(report_id=saved['id'], version=1))['status'] == 409
    request(a, 'POST', path+'/run', 409, json={'workspace_token': t, 'expected_version': 1})
    assert a.ctx.invoke('crm_saved_report_run', dict(report_id=saved['id'], expected_version=1))['status'] == 409
    assert invoke(a, 'crm_dashboard_get', {})['cards'][0]['reference_status'] == 'outdated'
    request(a, 'POST', path+'/run', json={'workspace_token': t, 'expected_version': 2})
    archived = invoke(a, 'crm_report_archive', dict(report_id=saved['id'], expected_version=2, idempotency_key='archive'))
    assert archived['version'] == 3
    request(a, 'POST', path+'/run', 409, json={'workspace_token': t, 'expected_version': 3})
    assert a.ctx.invoke('crm_saved_report_run', dict(report_id=saved['id'], expected_version=3))['status'] == 409
    assert invoke(a, 'crm_report_list', {})['items'] == []
    assert invoke(a, 'crm_dashboard_get', {})['cards'][0]['reference_status'] == 'archived'
    restored = request(a, 'POST', path+'/restore', json={'workspace_token': t, 'expected_version': 3, 'idempotency_key': 'restore'})
    assert restored['version'] == 4
    card['report_version'] = 4
    invoke(a, 'crm_dashboard_save', dict(cards=[card], expected_version=1, idempotency_key='adopt'))
    assert invoke(a, 'crm_dashboard_get', {})['cards'][0]['reference_status'] == 'active'


def test_idempotency_and_optimistic_conflicts(adapters):
    a = adapters; t = token(a); saved = create(a)
    assert create(a) == saved
    request(a, 'POST', '/analytics/reports', 409, json=dict(workspace_token=t, title='Changed', definition=DEFINITION, idempotency_key='create'))
    args = dict(report_id=saved['id'], title='New', definition=DEFINITION, expected_version=1, idempotency_key='update')
    updated = invoke(a, 'crm_report_update', args)
    assert invoke(a, 'crm_report_update', args) == updated
    assert a.ctx.invoke('crm_report_update', dict(args, title='Conflict'))['status'] == 409
    assert a.ctx.invoke('crm_report_update', dict(args, idempotency_key='stale'))['status'] == 409
    dash = dict(cards=[], expected_version=0, idempotency_key='dash')
    saved_dash = invoke(a, 'crm_dashboard_save', dash)
    assert invoke(a, 'crm_dashboard_save', dash) == saved_dash
    request(a, 'PUT', '/analytics/dashboard', 409, json=dict(dash, workspace_token=t, expected_version=1))
    assert a.ctx.invoke('crm_dashboard_save', dict(dash, idempotency_key='stale'))['status'] == 409


@pytest.mark.parametrize('definition', [
    {'entity': 'contacts', 'sql': 'SELECT * FROM contacts'},
    {'entity': 'gmail'}, {'entity': 'contacts', 'columns': ['gmail_subject']},
    {'entity': 'contacts', 'filter': {'field': 'gmail_body', 'op': 'contains', 'value': 'secret'}},
])
def test_sql_and_gmail_never_enter_report_language(adapters, definition):
    t = token(adapters)
    request(adapters, 'POST', '/analytics/run', 422, json={'workspace_token': t, 'definition': definition})
    result = adapters.ctx.invoke('crm_report_run', {'definition': definition})
    assert not result['ok'] and result['status'] == 422
    assert not adapters.ctx.calls


def test_workspace_and_profile_rechecked_for_reads_and_writes(adapters):
    a = adapters; old = token(a); saved = create(a)
    paths = ['/analytics/catalog', '/analytics/reports', '/analytics/reports/'+saved['id'], '/analytics/dashboard']
    for path in paths:
        request(a, 'GET', path, 422)
        request(a, 'GET', path, 409, params={'workspace_token': 'stale'})
        request(a, 'GET', path, 400, params={'workspace_token': old, 'sql': 'SELECT 1'})
    a.state['profile'] = 'beta'
    new = token(a)
    assert new != old
    for path in paths:
        request(a, 'GET', path, 409, params={'workspace_token': old})
    request(a, 'POST', '/analytics/reports', 409, json=dict(workspace_token=old, title='Bad', definition=DEFINITION, idempotency_key='bad'))
    assert invoke(a, 'crm_report_list', {})['items'] == []
    assert invoke(a, 'crm_dashboard_get', {})['cards'] == []
    assert a.ctx.invoke('crm_report_get', {'report_id': saved['id']})['status'] == 404
    request(a, 'GET', paths[2], 404, params={'workspace_token': new})


def test_authored_logs_actor_provenance_replay_void_and_strict_input(adapters):
    a = adapters; t = token(a)
    c = invoke(a, 'crm_contact_create', {'name': 'Synthetic Person'})
    data = dict(contact_id=c['id'], happened_at='2020-01-01T12:00:00Z', kind='call', summary='Self-reported discussion')
    body = dict(workspace_token=t, data=data, expected_contact_version=1, idempotency_key='ui-log')
    ui = request(a, 'POST', '/interactions', 201, json=body)
    assert ui['actor'] == 'desktop' and ui['provenance'] == 'self_reported'
    assert request(a, 'POST', '/interactions', 201, json=body) == ui
    agent = invoke(a, 'crm_contact_log', dict(data, expected_contact_version=1, idempotency_key='agent-log'))
    assert agent['actor'] == 'hermes' and agent['provenance'] == 'self_reported'
    assert 'delivered' not in agent
    assert request(a, 'GET', '/interactions', params={'workspace_token': t, 'contact_id': c['id']}) == invoke(a, 'crm_contact_log_list', {'contact_id': c['id']})
    for change in ({'actor': 'forged'}, {'provenance': 'provider_verified'}):
        request(a, 'POST', '/interactions', 422, json=dict(body, data=dict(data, **change)))
        assert a.ctx.invoke('crm_contact_log', dict(data, expected_contact_version=1, idempotency_key='forged', **change))['status'] == 422
    request(a, 'POST', '/interactions', 409, json=dict(body, data=dict(data, summary='Changed')))
    request(a, 'POST', '/interactions', 409, json=dict(body, expected_contact_version=2, idempotency_key='stale'))
    void = dict(interaction_id=ui['id'], expected_version=1, reason='Wrong contact', idempotency_key='void')
    corrected = invoke(a, 'crm_contact_log_void', void)
    assert corrected['actor'] == 'desktop' and corrected['void_actor'] == 'hermes'
    assert corrected['summary'] == ui['summary'] and corrected['version'] == 2
    assert invoke(a, 'crm_contact_log_void', void) == corrected
    assert a.ctx.invoke('crm_contact_log_void', dict(void, reason='Changed'))['status'] == 409
    assert invoke(a, 'crm_contact_log_list', {'contact_id': c['id']})['items'] == [agent]
    assert invoke(a, 'crm_contact_log_list', {'contact_id': c['id'], 'include_voided': True})['total'] == 2
    ui_void = request(a, 'POST', '/interactions/'+agent['id']+'/void', json=dict(workspace_token=t, expected_version=1, reason='Correction', idempotency_key='ui-void'))
    assert ui_void['void_actor'] == 'desktop' and ui_void['actor'] == 'hermes'
    request(a, 'GET', '/interactions', 409, params={'workspace_token': 'stale', 'contact_id': c['id']})
    assert not a.ctx.calls


@pytest.mark.parametrize('extra', [
    {'profile': 'beta'}, {'backend': 'sqlite'}, {'actor': 'forged'},
    {'limit': True}, {'limit': '1'}, {'offset': -1}, {'sql': 'SELECT 1'},
])
def test_rest_preview_closed_schema_and_strict_types(adapters, extra):
    request(adapters, 'POST', '/analytics/run', 422,
            json=dict(workspace_token=token(adapters), definition=DEFINITION, **extra))
    assert not adapters.ctx.calls


@pytest.mark.parametrize('version', [True, '1', 1.0, 0, None])
def test_rest_saved_run_requires_strict_reviewed_version(adapters, version):
    saved = create(adapters)
    request(adapters, 'POST', '/analytics/reports/'+saved['id']+'/run', 422,
            json={'workspace_token': token(adapters), 'expected_version': version})


def test_backend_errors_are_sanitized(adapters, monkeypatch):
    from hermes_crm import native_api, plugin
    def broken(**kwargs):
        raise RuntimeError('postgresql://private-user:private-secret@internal/db')
    monkeypatch.setattr(native_api, 'open_profile_crm', broken)
    monkeypatch.setattr(plugin, 'open_profile_crm', broken)
    response = request(adapters, 'GET', '/analytics/catalog', 503, params={'workspace_token': 'opaque'})
    result = adapters.ctx.invoke('crm_report_catalog', {})
    assert not result['ok'] and result['status'] == 503
    assert 'private-secret' not in str(response) + str(result)
