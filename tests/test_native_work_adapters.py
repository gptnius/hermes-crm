"""Adapter contracts with synthetic dispatch, not live scheduler execution proof."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_crm import native_api, plugin
from hermes_crm.domain import CRM
from hermes_crm.native_work import NativeWorkStore, TOOLSETS


LEGACY_READ = {
    'crm_contact_report', 'crm_contact_list', 'crm_contact_get',
    'crm_deal_list', 'crm_deal_get', 'crm_task_list', 'crm_task_get', 'crm_overview',
}
LEGACY_WRITE = {
    'crm_contact_create', 'crm_contact_update', 'crm_deal_create', 'crm_deal_update',
    'crm_task_create', 'crm_task_update', 'crm_followup_schedule',
}
WORK_READ = {'crm_work_get', 'crm_work_list'}
WORK_SCHEDULE = {'crm_work_create', 'crm_work_schedule', 'crm_work_reconcile', 'crm_work_cancel'}
WORK_REPORT = {'crm_work_report'}
REPORT_READ = {'crm_report_catalog', 'crm_report_run', 'crm_report_list', 'crm_report_get', 'crm_saved_report_run', 'crm_dashboard_get'}
REPORT_WRITE = {'crm_report_create', 'crm_report_update', 'crm_report_archive', 'crm_report_restore', 'crm_dashboard_save'}
INTERACTION_READ = {'crm_contact_log_list'}
INTERACTION_WRITE = {'crm_contact_log', 'crm_contact_log_void'}
DETAIL_READ = {'crm_record_fields', 'crm_task_owner_policy'}
SCHEMA_READ = {'crm_schema_catalog'}
SCHEMA_WRITE = {'crm_schema_stage_create', 'crm_schema_stage_update', 'crm_schema_field_create', 'crm_schema_field_update'}
CRM_COMPANY_READ = {'crm_company_records', 'crm_contact_company_get', 'crm_company_list', 'crm_company_get'}
CRM_COMPANY_WRITE = {'crm_company_archive', 'crm_contact_company_set', 'crm_company_restore', 'crm_company_create', 'crm_company_update', 'crm_contact_create_with_company'}
CRM_EVENT_READ = {'crm_event_revisions', 'crm_relationship_activities', 'crm_event_get', 'crm_event_tasks', 'crm_event_list'}
CRM_EVENT_WRITE = {'crm_event_create', 'crm_event_task_create', 'crm_event_task_unlink', 'crm_event_reopen', 'crm_event_complete', 'crm_event_reschedule', 'crm_event_task_link', 'crm_event_cancel', 'crm_event_needs_rescheduling', 'crm_event_update'}
SECRET_ERROR = 'postgresql://secret-user:secret-password@private.example/db'


class AdapterContext:
    """Public context shape only. Host integration is covered in the opt-in suite."""
    def __init__(self, state):
        self.state = state
        self.tools = {}
        self.calls = []
        self.identity = None
        self.job = None
        self.run_at = None
        self.dispatch_failure = None

    @property
    def profile_name(self):
        return self.state['profile']

    def get_config(self, key, default=None):
        assert key == 'backend'
        return default

    def register_tool(self, **kwargs):
        assert kwargs['name'] not in self.tools
        self.tools[kwargs['name']] = kwargs

    def current_cron_execution(self):
        return self.identity

    def dispatch_tool(self, name, args, **kwargs):
        self.calls.append((name, args, kwargs))
        assert name == 'cronjob_manage'
        if self.dispatch_failure:
            raise self.dispatch_failure
        action = args['action']
        if action == 'create':
            self.run_at = args['schedule']
            self.job = dict(
                job_id='synthetic-job', name=args['name'],
                prompt_preview=args['prompt'][:100]+'...',
                schedule='once at '+datetime.fromisoformat(self.run_at).strftime('%Y-%m-%d %H:%M'),
                repeat='once', skills=[], enabled_toolsets=args['enabled_toolsets'],
                deliver='local', enabled=False, state='paused', next_run_at=None,
            )
        elif action == 'resume':
            assert args['job_id'] == self.job['job_id']
            self.job.update(enabled=True, state='scheduled', next_run_at=self.run_at)
        elif action == 'pause':
            assert args['job_id'] == self.job['job_id']
            self.job.update(enabled=False, state='paused', next_run_at=None)
        elif action == 'list':
            return json.dumps(dict(success=True, jobs=[self.job] if self.job else [], gateway_running=True))
        else:
            raise AssertionError('Unexpected scheduler action')
        return json.dumps(dict(success=True, job_id=self.job['job_id'], job=self.job, gateway_running=True))

    def invoke(self, name, args, **kwargs):
        return json.loads(self.tools[name]['handler'](args, **kwargs))


@pytest.fixture
def adapters(tmp_path, monkeypatch):
    state = {'profile': 'alpha'}
    factory_calls = []

    def factory(**kwargs):
        factory_calls.append((state['profile'], kwargs))
        if kwargs:
            assert kwargs == {'backend': 'sqlite', 'profile': state['profile']}
        return CRM(f'sqlite:///{tmp_path}/{state["profile"]}.db', profile=state['profile'])

    monkeypatch.setattr(plugin, 'open_profile_crm', factory)
    monkeypatch.setattr(native_api, 'open_profile_crm', factory)
    ctx = AdapterContext(state)
    plugin.register(ctx)
    app = FastAPI()
    app.include_router(native_api.router)
    return SimpleNamespace(ctx=ctx, client=TestClient(app), state=state,
                           factory=factory, factory_calls=factory_calls)


def create_intent(adapters, *, key='adapter-assignment'):
    crm = adapters.factory()
    try:
        run_at = (datetime.now(timezone.utc)+timedelta(days=3)).isoformat(timespec='microseconds')
        task = crm.create('tasks', {'title': 'Synthetic internal review', 'due_at': run_at})
    finally:
        crm.close()
    args = dict(task_id=task['id'], human_owner='Synthetic owner',
                prompt='Summarize the linked CRM task.', success_criteria='A concise internal summary.',
                run_at=run_at, idempotency_key=key)
    result = adapters.ctx.invoke('crm_work_create', args)
    assert result['ok'], result
    return result['data'], args


def schedule_intent(adapters):
    row, args = create_intent(adapters)
    result = adapters.ctx.invoke('crm_work_schedule', {'assignment_id': row['id']})
    assert result['ok'] and result['data']['state'] == 'scheduled', result
    return result['data'], args


def test_registration_preserves_legacy_tools_and_separates_authority(adapters):
    ctx = adapters.ctx
    expected = LEGACY_READ | LEGACY_WRITE | WORK_READ | WORK_SCHEDULE | WORK_REPORT | REPORT_READ | REPORT_WRITE | INTERACTION_READ | INTERACTION_WRITE | SCHEMA_READ | SCHEMA_WRITE | DETAIL_READ | CRM_COMPANY_READ | CRM_COMPANY_WRITE | CRM_EVENT_READ | CRM_EVENT_WRITE
    assert set(ctx.tools) == expected
    assert adapters.factory_calls == [] and ctx.calls == []
    for names, toolset in ((LEGACY_READ, 'crm_read'), (LEGACY_WRITE, 'crm_write'),
                           (WORK_READ, 'crm_work_read'), (WORK_SCHEDULE, 'crm_work_schedule'),
                           (WORK_REPORT, 'crm_work_report'), (REPORT_READ, 'crm_reports'),
                           (REPORT_WRITE, 'crm_report_write'), (INTERACTION_READ, 'crm_interaction_read'),
                           (INTERACTION_WRITE, 'crm_interaction_write'), (SCHEMA_READ, 'crm_schema_read'),
                           (SCHEMA_WRITE, 'crm_schema_write'), (DETAIL_READ, 'crm_detail_read'),
                           (CRM_COMPANY_READ, 'crm_company_read'), (CRM_COMPANY_WRITE, 'crm_company_write'),
                           (CRM_EVENT_READ, 'crm_event_read'), (CRM_EVENT_WRITE, 'crm_event_write')):
        assert all(ctx.tools[name]['toolset'] == toolset for name in names)
    for name in WORK_READ | WORK_SCHEDULE | WORK_REPORT:
        params = ctx.tools[name]['schema']['parameters']
        assert params['additionalProperties'] is False
        assert not {'identity', 'execution_id', 'job_id', 'parent_agent', 'tool_context',
                    'model', 'provider', 'enabled_toolsets', 'deliver'} & params['properties'].keys()
    manifest = (Path(__file__).resolve().parents[1]/'plugin.yaml').read_text()
    import yaml
    advertised = set(yaml.safe_load(manifest)['provides_tools'])
    assert advertised == expected
    assert tuple(TOOLSETS) == ('crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp')
    assert 'crm_work_schedule' not in TOOLSETS and 'crm_write' not in TOOLSETS
    assert not set(('crm_company_read','crm_company_write','crm_event_read','crm_event_write')) & set(TOOLSETS)


def test_create_is_intent_only_and_read_tools_share_the_same_store(adapters):
    row, args = create_intent(adapters)
    ctx = adapters.ctx
    assert row['state'] == 'pending' and row['reason'] == 'not_scheduled'
    assert row['job_id'] is None and not row['reports'] and ctx.calls == []
    assert ctx.invoke('crm_work_create', args)['data']['id'] == row['id']
    assert ctx.invoke('crm_work_get', {'assignment_id': row['id']})['data'] == row
    assert ctx.invoke('crm_work_list', {'task_id': args['task_id']})['data'] == [row]
    crm = adapters.factory()
    try:
        assert crm.get('tasks', args['task_id'])['status'] == 'open'
        assert NativeWorkStore(crm).get(row['id']) == row
    finally:
        crm.close()
    assert ctx.calls == []


@pytest.mark.parametrize('name', sorted(WORK_READ | WORK_SCHEDULE | WORK_REPORT))
@pytest.mark.parametrize('args', [None, [], 'object', {'unexpected': True}])
def test_new_handlers_reject_malformed_inputs_before_opening_a_backend(adapters, name, args):
    result = adapters.ctx.invoke(name, args)
    assert result['ok'] is False and result['status'] in {400, 422}
    assert adapters.factory_calls == [] and adapters.ctx.calls == []


@pytest.mark.parametrize('name,args', [
    ('crm_work_get', {'assignment_id': 123}),
    ('crm_work_get', {'assignment_id': ''}),
    ('crm_work_get', {'assignment_id': 'x'*37}),
    ('crm_work_list', {'limit': True}),
    ('crm_work_list', {'limit': '1'}),
    ('crm_work_list', {'limit': 0}),
    ('crm_work_list', {'limit': 101}),
    ('crm_work_list', {'task_id': []}),
    ('crm_work_cancel', {'assignment_id': 'id', 'version': True}),
    ('crm_work_report', {'assignment_id': 'id', 'generation': True, 'summary': 'x'}),
    ('crm_work_report', {'assignment_id': 'id', 'generation': 1, 'summary': 'x', 'outcome': 'succeeded'}),
    ('crm_work_report', {'assignment_id': 'id', 'generation': 1, 'summary': 'x', 'operation_id': 'another'}),
    ('crm_work_schedule', {'assignment_id': 'id', 'profile': 'beta'}),
])
def test_new_handlers_validate_strict_types_and_closed_schemas(adapters, name, args):
    result = adapters.ctx.invoke(name, args)
    assert result['ok'] is False and result['status'] == 422
    assert adapters.factory_calls == [] and adapters.ctx.calls == []


def test_create_validates_dates_payload_and_foreign_profile(adapters):
    _, args = create_intent(adapters)
    for change, status in [({'profile': 'beta'}, 403), ({'run_at': 'tomorrow'}, 400),
                           ({'run_at': '2030-01-01T00:00:00'}, 400),
                           ({'prompt': '   '}, 400), ({'human_owner': 5}, 422),
                           ({'task_id': 'missing'}, 404)]:
        result = adapters.ctx.invoke('crm_work_create', dict(args, idempotency_key='invalid', **change))
        assert result['ok'] is False and result['status'] == status, result
    assert adapters.ctx.calls == []


def test_every_tool_call_uses_the_current_profile(adapters):
    row, _ = create_intent(adapters)
    adapters.state['profile'] = 'beta'
    assert adapters.ctx.invoke('crm_work_list', {})['data'] == []
    result = adapters.ctx.invoke('crm_work_get', {'assignment_id': row['id']})
    assert not result['ok'] and result['status'] == 404
    assert adapters.factory_calls[-1] == ('beta', {'backend': 'sqlite', 'profile': 'beta'})
    assert adapters.ctx.calls == []


def test_scheduling_and_reconciliation_forward_host_context_without_replacing_it(adapters):
    row, _ = create_intent(adapters)
    parent_agent = object()
    context = dict(parent_agent=parent_agent, session_id='synthetic-session',
                   task_id='host-turn', user_task='Explicitly schedule this synthetic assignment')
    result = adapters.ctx.invoke('crm_work_schedule', {'assignment_id': row['id']}, **context)
    assert result['ok'] and result['data']['state'] == 'scheduled'
    assert [call[1]['action'] for call in adapters.ctx.calls] == ['create', 'resume']
    create = adapters.ctx.calls[0][1]
    assert create['paused'] is True and create['enabled_toolsets'] == list(TOOLSETS)
    assert create['deliver'] == create['failure_deliver'] == 'local'
    assert create['attach_to_session'] is False
    for _, _, kwargs in adapters.ctx.calls:
        assert kwargs == context and kwargs['parent_agent'] is parent_agent
    result = adapters.ctx.invoke('crm_work_reconcile', {'assignment_id': row['id']}, **context)
    assert result['ok'] and result['data']['state'] == 'scheduled'
    assert adapters.ctx.calls[-1][1] == {'action': 'list', 'include_disabled': True}
    assert adapters.ctx.calls[-1][2] == context


def test_cancel_forwards_exact_job_pause_and_stale_version_never_dispatches(adapters):
    row, _ = schedule_intent(adapters)
    before = len(adapters.ctx.calls)
    stale = adapters.ctx.invoke('crm_work_cancel', {'assignment_id': row['id'], 'version': 1})
    assert not stale['ok'] and stale['status'] == 409
    assert len(adapters.ctx.calls) == before
    context = {'parent_agent': object(), 'session_id': 'cancel-session'}
    result = adapters.ctx.invoke('crm_work_cancel', {'assignment_id': row['id'], 'version': row['version']}, **context)
    assert result['ok'] and result['data']['state'] == 'cancelled', result
    name, args, kwargs = adapters.ctx.calls[-1]
    assert name == 'cronjob_manage' and args['action'] == 'pause' and args['job_id'] == row['job_id']
    assert kwargs == context


def test_permission_denial_is_sanitized_and_not_retried_as_create(adapters):
    row, _ = create_intent(adapters)
    adapters.ctx.dispatch_failure = PermissionError(SECRET_ERROR)
    result = adapters.ctx.invoke('crm_work_schedule', {'assignment_id': row['id']})
    assert result['ok'] and result['data']['state'] == 'unknown'
    assert 'secret-password' not in json.dumps(result) and 'private.example' not in json.dumps(result)
    assert len(adapters.ctx.calls) == 1
    again = adapters.ctx.invoke('crm_work_schedule', {'assignment_id': row['id']})
    assert again['data']['state'] == 'unknown' and len(adapters.ctx.calls) == 1


def test_report_uses_only_trusted_context_and_never_completes_business_task(adapters):
    row, args = schedule_intent(adapters)
    ctx = adapters.ctx
    report_args = dict(assignment_id=row['id'], generation=1, summary='Synthetic internal review complete.')
    identity = dict(job_id=row['job_id'], job_name=row['job_name'], execution_id='synthetic-execution',
                    profile='alpha', source='builtin', scheduled_instant=row['payload']['run_at'], started_at=None)
    spoof = ctx.invoke('crm_work_report', dict(report_args, identity=identity))
    assert not spoof['ok'] and spoof['status'] == 422
    spoof = ctx.invoke('crm_work_report', report_args, current_cron_execution=identity, execution_id='forged')
    assert not spoof['ok'] and spoof['status'] == 403
    ctx.identity = SimpleNamespace(**identity)
    before = len(ctx.calls)
    result = ctx.invoke('crm_work_report', report_args, execution_id='not-used')
    assert result['ok'] and result['data']['state'] == 'result_reported'
    report = result['data']['reports'][0]
    assert report['identity']['execution_id'] == 'synthetic-execution'
    assert report['provenance'] == 'native_run_reported' and report['review_status'] == 'awaiting_human_review'
    assert result['data']['business_task_completed'] is False
    assert result['data']['host_terminal_success_verified'] is False
    assert len(ctx.calls) == before
    assert ctx.invoke('crm_work_report', report_args)['data'] == result['data']
    crm = adapters.factory()
    try:
        assert crm.get('tasks', args['task_id'])['status'] == 'open'
    finally:
        crm.close()


def test_native_history_requires_token_and_matches_tool_history(adapters):
    row, args = create_intent(adapters)
    client = adapters.client
    token = client.get('/meta').json()['workspace_token']
    for path in ['/work', '/work/'+row['id']]:
        assert client.get(path).status_code == 422
        assert client.get(path, params={'workspace_token': 'old'}).status_code == 409
        assert client.get(path, params={'workspace_token': ''}).status_code == 422
    before = len(adapters.factory_calls)
    response = client.get('/work', params={'workspace_token': token, 'task_id': args['task_id'], 'profile': 'alpha'})
    assert response.status_code == 200 and response.json() == [row]
    assert len(adapters.factory_calls) == before+1
    assert client.get('/work/'+row['id'], params={'workspace_token': token, 'profile': 'alpha'}).json() == row
    assert adapters.ctx.calls == []


def test_history_profile_routing_is_host_owned_and_stale_tokens_fail(adapters):
    row, _ = create_intent(adapters)
    client = adapters.client
    alpha_token = client.get('/meta').json()['workspace_token']
    # Without a host profile switch, a query string cannot select a different DB.
    assert client.get('/work', params={'workspace_token': alpha_token, 'profile': 'beta'}).json() == [row]
    adapters.state['profile'] = 'beta'
    for path in ['/work', '/work/'+row['id']]:
        assert client.get(path, params={'workspace_token': alpha_token, 'profile': 'alpha'}).status_code == 409
    beta_token = client.get('/meta').json()['workspace_token']
    assert client.get('/work', params={'workspace_token': beta_token, 'profile': 'alpha'}).json() == []
    assert client.get('/work/'+row['id'], params={'workspace_token': beta_token}).status_code == 404
    assert adapters.ctx.calls == []


@pytest.mark.parametrize('query', ['unknown=x', 'limit=1&limit=2', 'limit=1.0',
                                   'profile=alpha&profile=beta', 'workspace_token=extra', 'task_id=1&task_id=2'])
def test_history_rejects_unknown_ambiguous_or_malformed_query(adapters, query):
    row, _ = create_intent(adapters)
    token = adapters.client.get('/meta').json()['workspace_token']
    response = adapters.client.get('/work?workspace_token='+token+'&'+query)
    assert response.status_code == 400
    if not query.startswith(('limit', 'task_id')):
        response = adapters.client.get('/work/'+row['id']+'?workspace_token='+token+'&'+query)
        assert response.status_code == 400
    assert adapters.ctx.calls == []


def test_history_bounds_and_mutating_routes_do_not_schedule(adapters):
    row, _ = create_intent(adapters)
    token = adapters.client.get('/meta').json()['workspace_token']
    for limit in ('0', '101', '-1', 'true'):
        assert adapters.client.get('/work', params={'workspace_token': token, 'limit': limit}).status_code == 422
    assert adapters.client.get('/work/'+'x'*37, params={'workspace_token': token}).status_code == 422
    body = {'workspace_token': token, 'data': {'assignment_id': row['id']}}
    for method in ('post', 'put', 'patch', 'delete'):
        for path in ('/work', '/work/'+row['id'], '/work/'+row['id']+'/schedule', '/work_schedule'):
            response = adapters.client.request(method.upper(), path, json=body)
            assert response.status_code in {404, 405, 422}
    assert adapters.ctx.calls == []
    assert adapters.ctx.invoke('crm_work_get', {'assignment_id': row['id']})['data']['state'] == 'pending'


def test_adapter_backend_exceptions_never_disclose_credentials(adapters, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError(SECRET_ERROR)
    monkeypatch.setattr(plugin, 'open_profile_crm', fail)
    result = adapters.ctx.invoke('crm_work_list', {})
    assert not result['ok'] and result['status'] == 503
    assert 'secret-password' not in json.dumps(result) and 'private.example' not in json.dumps(result)
    monkeypatch.setattr(native_api, 'open_profile_crm', fail)
    for path in ('/work', '/work/id'):
        response = adapters.client.get(path, params={'workspace_token': 'token'})
        assert response.status_code == 503
        assert 'secret-password' not in response.text and 'private.example' not in response.text


@pytest.mark.parametrize('value', [None, True, False, 0, -1, '1', 1.0, [], {}])
def test_create_handler_expected_version_strict_before_backend(adapters, value):
    args = dict(task_id='synthetic', human_owner='Owner', prompt='Analyze', success_criteria='Report',
                run_at='2030-04-01T12:00:00Z', idempotency_key='strict', expected_task_version=value)
    result = adapters.ctx.invoke('crm_work_create', args)
    assert result['ok'] is False and result['status'] == 422
    assert not adapters.factory_calls and not adapters.ctx.calls


def test_create_schema_advertises_atomic_expected_task_version(adapters):
    schema = adapters.ctx.tools['crm_work_create']['schema']['parameters']
    version = schema['properties']['expected_task_version']
    assert version['type'] == 'integer' and version['minimum'] == 1
    assert 'default' not in version
    assert 'expected_task_version' not in schema['required']
    row, args = create_intent(adapters)
    result = adapters.ctx.invoke('crm_work_create', dict(args, idempotency_key='reviewed', expected_task_version=1))
    assert result['ok'] and result['data']['payload']['expected_task_version'] == 1
    crm = adapters.factory()
    try: crm.update('tasks', args['task_id'], {'version': 1, 'title': 'Changed'})
    finally: crm.close()
    stale = adapters.ctx.invoke('crm_work_create', dict(args, idempotency_key='stale', expected_task_version=1))
    assert stale['status'] == 409 and not stale['ok']
    recovered = adapters.ctx.invoke('crm_work_create', dict(args, idempotency_key='reviewed', expected_task_version=1))
    assert recovered['ok'] and recovered['data']['id'] == result['data']['id']
    assert not adapters.ctx.calls


def test_paginated_work_and_coverage_are_read_only_profile_bound(adapters):
    row, args = create_intent(adapters)
    token = row['workspace']
    for path in ('/reports/work', '/reports/coverage'):
        assert adapters.client.get(path).status_code == 422
        assert adapters.client.get(path, params={'workspace_token': 'stale'}).status_code == 409
        assert adapters.client.post(path, json={'workspace_token': token}).status_code in {404, 405}
        result = adapters.client.get(path, params={'workspace_token': token, 'profile': 'not-authority', 'limit': 1}).json()
        assert result['total'] == 1 and result['limit'] == 1 and result['offset'] == 0
        assert result['observed_at']
        assert adapters.client.get(path, params={'workspace_token': token, 'offset': 1}).json()['items'] == []
    page = adapters.client.get('/reports/work', params={'workspace_token': token, 'task_id': args['task_id']}).json()
    assert page['items'] == [row]
    evidence = adapters.client.get('/reports/coverage', params={'workspace_token': token}).json()
    assert evidence['workspace_token'] == token and evidence['profile'] == 'alpha'
    assert evidence['items'][0]['assignment']['id'] == row['id']
    assert evidence['items'][0]['task']['id'] == args['task_id']
    assert adapters.ctx.calls == []
    adapters.state['profile'] = 'beta'
    for path in ('/reports/work', '/reports/coverage'):
        assert adapters.client.get(path, params={'workspace_token': token}).status_code == 409
    crm = adapters.factory()
    try: other_token = crm.workspace_token()
    finally: crm.close()
    assert adapters.client.get('/reports/work', params={'workspace_token': other_token}).json()['total'] == 0
    assert adapters.client.get('/reports/coverage', params={'workspace_token': other_token}).json()['total'] == 0
    assert adapters.ctx.calls == []


@pytest.mark.parametrize('path', ['/reports/work', '/reports/coverage'])
@pytest.mark.parametrize('query', ['extra=x', 'limit=1&limit=2', 'limit=1.0', 'offset=1.0', 'offset=-1',
                                  'offset=2000000001', 'limit=101', 'workspace_token=duplicate'])
def test_read_reports_reject_ambiguous_or_unbounded_queries(adapters, path, query):
    row, _ = create_intent(adapters)
    response = adapters.client.get(f'{path}?workspace_token={row["workspace"]}&{query}')
    assert response.status_code in {400, 422}
    assert not adapters.ctx.calls


def test_coverage_endpoint_rejects_bad_status_and_preserves_integrity_error(adapters):
    from sqlalchemy import update
    from hermes_crm.native_work import assignments
    row, _ = create_intent(adapters)
    assert adapters.client.get('/reports/coverage', params={'workspace_token': row['workspace'], 'status': 'green'}).status_code == 400
    assert adapters.client.get('/reports/coverage', params={'workspace_token': row['workspace'], 'q': 'x'*201}).status_code == 422
    crm = adapters.factory()
    try:
        with crm.engine.begin() as conn:
            conn.execute(update(assignments).values(digest='0'*64))
    finally: crm.close()
    response = adapters.client.get('/reports/coverage', params={'workspace_token': row['workspace']})
    assert response.status_code == 503 and 'integrity' in response.json()['detail']['error']
    assert not adapters.ctx.calls
