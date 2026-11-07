"""Real adapter registration and storage; no scheduler or provider calls."""
import pytest

from test_native_work_adapters import adapters, LEGACY_READ
from hermes_crm.native_work import TOOLSETS


def seed(a):
    crm = a.factory()
    try:
        crm.create_field('contacts', {'key': 'private_text', 'label': 'Text', 'type': 'text'})
        crm.create_field('contacts', {'key': 'unset_number', 'label': 'Number', 'type': 'number'})
        return crm.create('contacts', {'name': 'Core name', 'notes': 'ordinary sensitive notes',
            'custom_fields': {'private_text': 'ordinary sensitive custom value'}})
    finally:
        crm.close()


def test_base_adapter_minimizes_without_changing_human_api(adapters):
    a = adapters
    row = seed(a)
    for name, args in [('crm_contact_get', {'id': row['id']}), ('crm_contact_list', {}),
                       ('crm_contact_report', {}), ('crm_overview', {})]:
        response = a.ctx.invoke(name, args)
        assert response['ok'], response
        assert 'ordinary sensitive' not in str(response)
        assert 'custom_fields' not in str(response)
    assert a.client.get('/contacts/'+row['id']).json()['contact'] == row
    result = a.ctx.invoke('crm_contact_update', {'id': row['id'], 'version': 1, 'company': 'Updated'})
    assert result['ok'] and result['data']['version'] == 2
    assert 'notes' not in result['data'] and 'custom_fields' not in result['data']
    assert a.client.get('/contacts/'+row['id']).json()['contact']['notes'] == row['notes']


def test_explicit_detail_selection_is_separate_and_bounded(adapters):
    a = adapters
    row = seed(a)
    args = dict(kind='contacts', id=row['id'], fields=['custom.private_text'])
    result = a.ctx.invoke('crm_record_fields', args)
    assert result == dict(ok=True, data=dict(id=row['id'], version=1,
        fields={'custom.private_text': 'ordinary sensitive custom value'}))
    assert a.ctx.invoke('crm_record_fields', dict(args, fields=['notes', 'custom.unset_number']))['data']['fields'] == {
        'notes': row['notes'], 'custom.unset_number': None}
    assert a.ctx.tools['crm_record_fields']['toolset'] == 'crm_detail_read'
    assert 'crm_detail_read' not in TOOLSETS
    assert {name for name, tool in a.ctx.tools.items() if tool['toolset'] == 'crm_read'} == LEGACY_READ
    assert a.ctx.calls == []
    # None cron context is not interpreted as explicit human approval. This
    # endpoint is field selection under host toolset permissions, not consent.
    a.ctx.identity = None
    assert a.ctx.invoke('crm_record_fields', args)['ok']


@pytest.mark.parametrize('fields', [[], ['*'], ['custom.*'], ['custom.unknown'], ['notes', 'notes'],
    ['protected_notes'], ['private.notes'], ['custom.private_text.value'], ['../notes'],
    ['notes'] * 21, [1], 'notes'])
def test_detail_rejects_wildcards_unknown_keys_paths_duplicates_and_invalid_shapes(adapters, fields):
    row = seed(adapters)
    response = adapters.ctx.invoke('crm_record_fields', dict(kind='contacts', id=row['id'], fields=fields))
    assert not response['ok']
    assert 'ordinary sensitive' not in str(response)


@pytest.mark.parametrize('extra', ['profile', 'workspace', 'include_protected', 'current_cron_execution'])
def test_detail_disallows_caller_scope_or_authority_fields(adapters, extra):
    row = seed(adapters)
    args = dict(kind='contacts', id=row['id'], fields=['notes'])
    args[extra] = 'forged'
    result = adapters.ctx.invoke('crm_record_fields', args)
    assert not result['ok'] and result['status'] == 422


def test_completed_reminder_remains_readable_and_schedule_echo_minimized(adapters):
    a = adapters
    row = a.ctx.invoke('crm_task_create', dict(title='Reminder', due_at='2099-01-01T00:00:00Z',
        status='done', notes='ordinary sensitive reminder'))['data']
    read = a.ctx.invoke('crm_task_get', {'id': row['id']})['data']
    assert read['status'] == 'done' and 'notes' not in read
    assert a.ctx.calls == []


def test_detail_profile_switch_cannot_read_other_workspace(adapters):
    row = seed(adapters)
    adapters.state['profile'] = 'beta'
    result = adapters.ctx.invoke('crm_record_fields', dict(kind='contacts', id=row['id'], fields=['notes']))
    assert not result['ok'] and result['status'] == 404


def test_idempotent_create_and_schedule_response_echoes_are_projected(adapters, monkeypatch):
    a = adapters
    args = {'name': 'Idempotent', 'notes': 'ordinary sensitive create', 'idempotency_key': 'repeat'}
    first = a.ctx.invoke('crm_contact_create', args)
    assert first == a.ctx.invoke('crm_contact_create', args)
    assert first['ok'] and 'notes' not in first['data']
    from hermes_crm.domain import CRM
    # Only a synthetic return: no scheduler is contacted or job created.
    monkeypatch.setattr(CRM, 'schedule_followup', lambda *a, **k: dict(
        task=dict(id='t', status='open', notes='ordinary sensitive scheduled task', custom_fields={'x': 1}),
        scheduler=dict(success=True, job_id='synthetic', job={'prompt': 'ordinary sensitive prompt'}),
        execution_verified=False))
    result = a.ctx.invoke('crm_followup_schedule', {'task_id': 't'})
    assert result == dict(ok=True, data=dict(task=dict(id='t', status='open'),
        scheduler=dict(success=True, job_id='synthetic'), execution_verified=False))
    assert a.ctx.calls == []
