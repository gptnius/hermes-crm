"""Pure projection tests; no claim of host identity or row authorization."""
from copy import deepcopy

import pytest

from hermes_crm.agent_read_policy import PROJECTED_TOOLS, project_agent_result
from hermes_crm.domain import CRMError


@pytest.mark.parametrize('kind', ['contact', 'deal', 'task'])
@pytest.mark.parametrize('operation', ['get', 'list', 'create', 'update'])
def test_base_record_projection_omits_notes_custom_values_and_future_columns(kind, operation):
    record = dict(id='record', version=7, name='Visible name', title='Visible title',
                  status='done', notes='private note', custom_fields={'private': 'value', 'number': 3},
                  future_sensitive_column='not reviewed')
    before = deepcopy(record)
    data = [record] if operation == 'list' else record
    result = project_agent_result(f'crm_{kind}_{operation}', data)
    projected = result[0] if operation == 'list' else result
    assert projected['id'] == 'record' and projected['version'] == 7
    assert projected['title'] == 'Visible title'
    assert not {'notes', 'custom_fields', 'future_sensitive_column'} & projected.keys()
    if kind == 'task':
        assert projected['status'] == 'done'  # Legacy reminders still learn no action is needed.
    assert record == before


def test_report_remains_workspace_aggregate_but_omits_raw_fields():
    report = dict(items=[dict(id='contact', notes='private', custom_fields={'n': 'secret'},
                   deal_count=3, deal_stages=['lead', 'won'])], total=100, limit=1, offset=3,
                  secret_envelope='private')
    before = deepcopy(report)
    projected = project_agent_result('crm_contact_report', report)
    assert projected == dict(items=[dict(id='contact', deal_count=3, deal_stages=['lead', 'won'])],
                             total=100, limit=1, offset=3)
    projected['items'][0]['deal_stages'].append('changed')
    assert report == before


def test_overview_drops_catalog_audit_and_backend_metadata():
    data = dict(contacts=12, open_tasks=4, tasks=[dict(id='t', notes='private', custom_fields={})],
                activity=[dict(summary='Sensitive old title')], catalog={'private': 'description'},
                profile='workspace-name', backend='sqlite', demo=False,
                stages=[dict(stage='lead', count=2, unknown='secret')],
                lead_attention={'no_open_followup': 1, 'unknown': 'secret'})
    assert project_agent_result('crm_overview', data) == dict(contacts=12, open_tasks=4,
        tasks=[dict(id='t')], stages=[dict(stage='lead', count=2)], lead_attention={'no_open_followup': 1})


def test_schedule_echo_does_not_bypass_minimization():
    data = dict(task=dict(id='task', notes='private', status='open'),
                scheduler=dict(success=True, job_id='job', job={'prompt': 'secret'}, error='private'),
                execution_verified=False)
    assert project_agent_result('crm_followup_schedule', data) == dict(task=dict(id='task', status='open'),
        scheduler=dict(success=True, job_id='job'), execution_verified=False)


def test_no_implicit_unreviewed_tool_projection():
    assert len(PROJECTED_TOOLS) == 15
    for name in ('crm_new_read', 'crm_schema_catalog', 'crm_work_get', 'crm_report_run'):
        with pytest.raises(CRMError, match='No reviewed'):
            project_agent_result(name, {'notes': 'private'})


@pytest.mark.parametrize('tool,data', [
    ('crm_contact_get', []), ('crm_task_list', {}), ('crm_contact_report', {'items': 'bad'}),
    ('crm_overview', {'stages': 'bad'}), ('crm_followup_schedule', {'scheduler': 'bad'}),
])
def test_unexpected_container_fails_closed(tool, data):
    with pytest.raises(CRMError, match='Unexpected CRM projection shape'):
        project_agent_result(tool, data)


def test_unexpected_nested_value_is_not_passed_through():
    assert project_agent_result('crm_contact_get', {'id': 'c', 'name': {'notes': 'private'}}) == {'id': 'c'}
