"""Opt-in synthetic CRM workflow through the real pinned Hermes registry.

This proves local tool dispatch, not model reasoning, web research, provider
communication or scheduled execution. Both modes reuse the credential-free,
network/process-guarded customization harness without changing its guard.
"""
import hashlib
import os
from pathlib import Path

import pytest
import test_customization_host as harness


# Fail closed if the reviewed harness (including environment construction,
# subprocess timeout, cleanup checks or success marker) or inherited guard
# changes. Re-review the actual diff before updating either fingerprint.
_HARNESS_SHA256 = '4dfb2f4846826a87db232f2ec2061b5c9149b889f59ff765c5fc627ab1ce4ced'
_GUARD_SHA256 = '4409f7fcf0c2060f62cdd0a3c45b0eed2e8471b74e1378c7d1f6ac7fe7fbff48'


def test_agent_workflow_harness_seam():
    assert hashlib.sha256(Path(harness.__file__).read_bytes()).hexdigest() == _HARNESS_SHA256
    assert hashlib.sha256(harness.SAFETY_GUARD.encode()).hexdigest() == _GUARD_SHA256
    assert harness.PINNED_HOST_SHA == '2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'
    compile(HOST_CHECK, '<agent-workflow-host-check>', 'exec')


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_agent_workflow_pinned_host(tmp_path, isolation, monkeypatch):
    test_agent_workflow_harness_seam()
    # Reuse exactly the reviewed disposable-home harness, changing only the
    # dispatched test body. pytest restores the original after each case.
    monkeypatch.setattr(harness, 'HOST_CHECK', HOST_CHECK)
    harness.test_custom_schema_pinned_host(tmp_path, isolation)


HOST_CHECK = r'''
import json
import os
from pathlib import Path
from ruamel.yaml import YAML
from hermes_cli.plugins import get_plugin_manager
from tools.registry import registry

home = Path(os.environ['HERMES_HOME'])
manager = get_plugin_manager()

def raw(name, args):
    response = registry.dispatch(name, args, scope=manager.scope_key)
    return json.loads(response) if isinstance(response, str) else response

def tool(name, args):
    response = raw(name, args)
    assert response.get('ok') is True, (name, response)
    return response['data']

def fields(kind, record, names):
    result = tool('crm_record_fields', {'kind': kind, 'id': record['id'], 'fields': names})
    assert set(result) == {'id', 'version', 'fields'}, result
    assert result['id'] == record['id'] and result['version'] == record['version'], result
    assert set(result['fields']) == set(names), result
    return result['fields']

def stale(name, args):
    response = raw(name, args)
    assert response.get('ok') is False and response.get('status') == 409, response

try:
    manager.discover_and_load()
    manifest = YAML(typ='safe').load((home / 'plugins/hermes-crm/plugin.yaml').read_text())
    names = manifest['provides_tools']
    assert len(names) == len(set(names)) == 83, names
    # Registry visibility is NOT a claim that all tools are enabled in every
    # agent/cron context. Verify each actual advertised plugin name in scope.
    for name in names:
        assert registry.get_entry(name, scope=manager.scope_key) is not None, name
    assert registry.get_entry('crm_record_fields', scope=manager.scope_key).toolset == 'crm_detail_read'

    company_args = {'data': {'name': 'Synthetic Workflow Company',
                    'domain': 'workflow.example.test', 'notes': 'Supplied ordinary company notes'},
                    'idempotency_key': 'workflow-company'}
    company = tool('crm_company_create', company_args)
    assert tool('crm_company_create', company_args) == company
    assert 'notes' not in company
    contact_args = {'data': {'name': 'Synthetic Workflow Contact', 'company': 'Legacy supplied text'},
                    'company_id': company['id'], 'expected_company_version': company['version'],
                    'idempotency_key': 'workflow-contact'}
    linked = tool('crm_contact_create_with_company', contact_args)
    assert tool('crm_contact_create_with_company', contact_args) == linked
    contact = linked['contact']
    assert contact['company'] == 'Legacy supplied text'
    link = tool('crm_contact_company_get', {'record_id': contact['id']})
    assert link['company_id'] == company['id']
    detail = tool('crm_company_get', {'record_id': company['id']})
    assert 'notes' not in detail['company'] and detail['counts']['contacts'] == 1
    assert fields('companies', company, ['notes']) == {'notes': 'Supplied ordinary company notes'}
    company = tool('crm_company_update', {'record_id': company['id'], 'expected_version': company['version'],
                   'data': {'notes': 'Reviewed company note edit'}, 'idempotency_key': 'workflow-company-edit'})
    stale('crm_company_update', {'record_id': company['id'], 'expected_version': 1,
          'data': {'name': 'STALE overwrite', 'notes': 'STALE overwrite'}, 'idempotency_key': 'workflow-company-stale'})
    assert fields('companies', company, ['notes']) == {'notes': 'Reviewed company note edit'}
    retained = tool('crm_company_get', {'record_id': company['id']})['company']
    assert retained['name'] == company_args['data']['name'] and retained['domain'] == company_args['data']['domain']

    # Entirely synthetic supplied evidence. This .test reference is never
    # fetched and neither evidence nor proposal asserts provider verification.
    evidence_args = {'data': {'target_kind': 'companies', 'target_id': company['id'],
        'target_version': company['version'], 'question': 'What does the synthetic supplied fixture say?',
        'source_url': 'https://workflow.example.test/supplied-fixture',
        'source_title': 'Synthetic supplied fixture, not fetched',
        'observed_at': '2020-01-01T12:00:00Z',
        'claims': ['Synthetic caller-supplied claim; not independently verified'],
        'hypotheses': ['Synthetic unverified hypothesis']}, 'idempotency_key': 'workflow-evidence'}
    evidence = tool('crm_research_evidence_submit', evidence_args)
    assert tool('crm_research_evidence_submit', evidence_args) == evidence
    read_evidence = tool('crm_research_evidence_get', {'record_id': evidence['id']})
    assert read_evidence['claims'] == evidence_args['data']['claims']
    proposal_args = {'data': {'evidence_id': evidence['id'], 'evidence_digest': evidence['digest'],
        'evidence_lifecycle_version': evidence['lifecycle_version'], 'target_version': company['version'],
        'addition': 'Synthetic proposed addition, pending review'}, 'idempotency_key': 'workflow-proposal'}
    proposal = tool('crm_research_note_propose', proposal_args)
    assert tool('crm_research_note_propose', proposal_args) == proposal
    listed = tool('crm_research_proposal_list', {'target_kind': 'companies', 'target_id': company['id']})
    assert listed['total'] == 1 and listed['items'][0]['id'] == proposal['id']
    assert fields('companies', company, ['notes']) == {'notes': 'Reviewed company note edit'}, 'Proposal must not apply notes'

    event_args = {'data': {'title': 'Synthetic local discussion', 'kind': 'call',
        'starts_at': '2020-01-01T10:00:00Z', 'ends_at': '2020-01-01T11:00:00Z', 'timezone': 'UTC',
        'company_id': company['id'], 'contact_id': contact['id'], 'notes': 'Ordinary event preparation'},
        'idempotency_key': 'workflow-event'}
    event = tool('crm_event_create', event_args)
    assert tool('crm_event_create', event_args) == event
    original_start = event['starts_at']
    assert 'notes' not in event and 'outcome_summary' not in event and event['source'] == 'local'
    assert fields('events', event, ['notes', 'outcome_summary']) == {
        'notes': 'Ordinary event preparation', 'outcome_summary': None}
    policy = tool('crm_task_owner_policy', {})
    assert policy['version'] == 0 and policy['required'] is False
    task_args = {'record_id': event['id'], 'expected_version': event['version'],
        'data': {'title': 'Synthetic linked follow-up', 'due_at': '2099-01-01T00:00:00Z',
                 'notes': 'Ordinary task notes', 'owner_label': 'Synthetic fixture owner',
                 'owner_source': 'explicit', 'owner_policy_version': policy['version']},
        'idempotency_key': 'workflow-event-task'}
    receipt = tool('crm_event_task_create', task_args)
    assert tool('crm_event_task_create', task_args) == receipt
    event, task = receipt['event'], receipt['task']
    assert receipt['event_id'] == event['id'] and receipt['task_id'] == task['id']
    task_read = tool('crm_task_get', {'id': task['id']})
    assert task_read['owner_label'] == 'Synthetic fixture owner' and task_read['status'] == 'open'
    assert task_read['schedule_status'] == 'none' and task_read['scheduler_job_id'] is None
    linked_tasks = tool('crm_event_tasks', {'record_id': event['id']})
    assert linked_tasks['total'] == 1 and linked_tasks['items'][0]['id'] == task['id']
    old_version = event['version']
    event = tool('crm_event_update', {'record_id': event['id'], 'expected_version': old_version,
        'data': {'notes': 'Reviewed event notes'}, 'idempotency_key': 'workflow-event-edit'})
    stale('crm_event_update', {'record_id': event['id'], 'expected_version': old_version,
        'data': {'notes': 'STALE overwrite'}, 'idempotency_key': 'workflow-event-stale'})
    assert fields('events', event, ['notes', 'outcome_summary']) == {'notes': 'Reviewed event notes', 'outcome_summary': None}
    event = tool('crm_event_complete', {'record_id': event['id'], 'expected_version': event['version'],
        'data': {'outcome_happened_at': '2020-01-01T11:00:00Z',
                 'outcome_summary': 'Synthetic self-reported outcome, no provider evidence'},
        'idempotency_key': 'workflow-event-complete'})
    assert event['status'] == 'completed' and event['outcome_provenance'] == 'self_reported'
    assert event['company_id'] == company['id'] and event['contact_id'] == contact['id']
    assert event['starts_at'] == original_start
    assert fields('events', event, ['notes', 'outcome_summary']) == {
        'notes': 'Reviewed event notes', 'outcome_summary': 'Synthetic self-reported outcome, no provider evidence'}
    assert 'notes' not in tool('crm_event_get', {'record_id': event['id']})
    assert tool('crm_task_get', {'id': task['id']}) == task_read, 'Event completion must not complete or schedule its task'
    assert not list(home.rglob('jobs.json')), 'Local CRM workflow must not create cron jobs'
    print('PASS agent-workflow actual-host synthetic local tools (83 advertised names)')
    # Existing harness success marker; emitted only after all workflow checks.
    print('PASS custom-schema actual-host contract')
finally:
    host = getattr(manager, '_plugin_host_instance', None)
    try:
        manager.unload()
    finally:
        if host is not None:
            host.shutdown()
            assert not host.alive
    assert not list(home.rglob('*.sock'))
'''
