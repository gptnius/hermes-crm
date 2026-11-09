"""Synthetic-only native-work contract tests. Never create a real host job."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, inspect, select, text, update

from hermes_crm.domain import CRM, CRMError, tasks
from hermes_crm.native_work import NativeWorkStore, TOOLSETS, assignments, events, reports


@pytest.fixture
def setup(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/work.db', profile='synthetic')
    task = crm.create('tasks', {'title': 'Synthetic internal analysis', 'due_at': '2030-05-01T00:00:00Z'})
    store = NativeWorkStore(crm)
    yield crm, store, task
    crm.close()


def create(setup, **extra):
    args = dict(task_id=setup[2]['id'], human_owner='Synthetic owner', prompt='  Analyze the existing pipeline.\n',
                success_criteria='Save a concise internal analysis for review', run_at='2030-04-01T12:30:41+00:00',
                idempotency_key='intent-1')
    args.update(extra)
    return setup[1].create(**args)


class Host:
    profile_name = 'synthetic'
    def __init__(self):
        self.identity = None
        self.calls, self.jobs = [], {}
        self.before = self.after = None
        self.gateway_running = True
    def current_cron_execution(self): return self.identity
    def dispatch_tool(self, name, args, **context):
        assert name == 'cronjob_manage'
        self.calls.append((copy.deepcopy(args), context))
        if self.before: self.before(args)
        action = args['action']
        if action == 'create':
            ident = f'job-{len(self.jobs)+1}'
            job = dict(job_id=ident, name=args['name'], enabled=False, state='paused',
                next_run_at=None, prompt_preview=args['prompt'][:100]+'...', skills=[], skill=None,
                model=None, provider=None, base_url=None, pinned=False, repeat='once',
                schedule='once at '+datetime.fromisoformat(args['schedule']).strftime('%Y-%m-%d %H:%M'),
                enabled_toolsets=args['enabled_toolsets'], deliver=args['deliver'], last_status=None,
                attach_to_session=False, expected_instant=args['schedule'])
            self.jobs[ident] = job
            result = dict(success=True, job_id=ident, job=copy.deepcopy(job), gateway_running=self.gateway_running)
        elif action == 'resume':
            job = self.jobs[args['job_id']]
            job.update(enabled=True, state='scheduled', next_run_at=job['expected_instant'])
            result = dict(success=True, job=copy.deepcopy(job))
        elif action == 'pause':
            job = self.jobs[args['job_id']]
            job.update(enabled=False, state='paused')
            result = dict(success=True, job=copy.deepcopy(job))
        elif action == 'list':
            assert args['include_disabled'] is True
            result = dict(success=True, jobs=copy.deepcopy(list(self.jobs.values())), gateway_running=self.gateway_running)
        else: raise AssertionError(action)
        if self.after: self.after(args, result)
        return json.dumps(result)


def scheduled(setup):
    host = Host()
    a = setup[1].schedule(host, create(setup)['id'], session_id='caller-session', task_id='caller-task')
    assert a['state'] == 'scheduled'
    return host, a


def identity(host, assignment, **extra):
    values = dict(job_id=assignment['job_id'], job_name=assignment['job_name'], execution_id='execution-1',
        source='builtin', profile='synthetic', scheduled_instant=assignment['payload']['run_at'],
        started_at='2030-04-01T12:30:42Z')
    values.update(extra)
    host.identity = SimpleNamespace(**values)
    return host


def report(setup, host, a, **extra):
    args = dict(generation=1, summary='Pipeline analysis ready for review', outcome='completed', operation_id='result')
    args.update(extra)
    return setup[1].report(host, a['id'], **args)


def test_new_schema_leaves_existing_crm_and_execution_tables_unchanged(setup):
    from hermes_crm.execution import ExecutionStore
    crm, store, _ = setup
    before = str(inspect(crm.engine).get_columns('crm_tasks'))
    ExecutionStore(crm)
    original_execution = str(inspect(crm.engine).get_columns('crm_agent_assignments'))
    NativeWorkStore(crm)
    assert str(inspect(crm.engine).get_columns('crm_tasks')) == before
    assert str(inspect(crm.engine).get_columns('crm_agent_assignments')) == original_execution
    assert {'crm_native_assignments','crm_native_work_events','crm_native_work_reports'} <= set(inspect(crm.engine).get_table_names())


def test_incompatible_new_table_fails_without_migration(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/incompatible.db')
    with crm.engine.begin() as conn: conn.execute(text('CREATE TABLE crm_native_assignments (id TEXT PRIMARY KEY)'))
    with pytest.raises(CRMError, match='explicit migration'): NativeWorkStore(crm)
    assert {c['name'] for c in inspect(crm.engine).get_columns('crm_native_assignments')} == {'id'}
    crm.close()


def test_intent_is_immutable_exact_idempotent_and_not_scheduled(setup):
    crm, store, task = setup
    a = create(setup)
    assert a['payload']['prompt'] == '  Analyze the existing pipeline.\n'
    assert a['payload']['business_due_at'] == task['due_at']
    assert a['payload']['run_at'] != a['payload']['business_due_at']
    assert a['state'] == 'pending' and a['job_id'] is None
    assert create(setup) == a
    crm.update('tasks', task['id'], {'version':1, 'title':'Later edited title'})
    recovered = create(setup)
    assert recovered['id'] == a['id'] and recovered['payload'] == a['payload'] and recovered['version'] == a['version']
    assert recovered['source_task_current'] is False and recovered['current_task_version'] == 2
    with pytest.raises(CRMError, match='payload conflict'): create(setup, prompt='Different')
    reopened = CRM(crm.url, profile='synthetic')
    try: assert NativeWorkStore(reopened).get(a['id']) == recovered
    finally: reopened.close()


@pytest.mark.parametrize('value', ['30m', 'in 30m', '2030-04-01', '2030-04-01T12:30:00', '', None, 7])
def test_rejects_naive_relative_or_invalid_times(setup, value):
    with pytest.raises(CRMError): create(setup, run_at=value)


def test_rejects_past_time_and_run_now(setup):
    with pytest.raises(CRMError, match='future'): create(setup, run_at='2000-01-01T00:00:00Z')


def test_missing_completed_or_foreign_task_profile(setup):
    with pytest.raises(CRMError, match='Task not found'): create(setup, task_id='missing')
    with pytest.raises(CRMError, match='Cross-profile'): create(setup, profile='other')
    setup[0].update('tasks', setup[2]['id'], {'version':1,'status':'done'})
    with pytest.raises(CRMError, match='not open'): create(setup)


def test_scope_is_current_store_not_just_custom_profile_name(setup, tmp_path):
    a = create(setup)
    other = CRM(f'sqlite:///{tmp_path}/other.db', profile='synthetic')
    try:
        store = NativeWorkStore(other)
        assert store.list() == []
        with pytest.raises(CRMError, match='current workspace/profile'): store.get(a['id'])
    finally: other.close()
    other = CRM(setup[0].url, profile='other')
    try:
        store = NativeWorkStore(other)
        assert store.list() == []
        with pytest.raises(CRMError): store.get(a['id'])
    finally: other.close()


def test_concurrent_intent_recovery_is_one_row(setup):
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda _: create(setup), range(6)))
    assert len({a['id'] for a in values}) == 1
    assert len(setup[1].list()) == 1


def test_concurrent_schedule_claim_creates_and_resumes_once(setup):
    a, host = create(setup), Host()
    def invoke(_):
        try: return setup[1].schedule(host, a['id'])
        except CRMError as error: assert error.status == 409
    with ThreadPoolExecutor(max_workers=6) as pool: list(pool.map(invoke, range(6)))
    assert [args['action'] for args, _ in host.calls] == ['create','resume']
    assert len(host.jobs) == 1
    assert setup[1].get(a['id'])['state'] == 'scheduled'


def test_exact_paused_create_binding_before_resume_and_narrow_scope(setup):
    a, host = create(setup), Host()
    def verify(args):
        current = setup[1].get(a['id'])
        if args['action'] == 'create':
            assert current['state'] == 'create_unknown' and current['job_id'] is None
            assert args['paused'] is True and args['repeat'] == 1
            assert args['deliver'] == args['failure_deliver'] == 'local'
            assert args['enabled_toolsets'] == list(TOOLSETS)
            assert 'crm_write' not in args['enabled_toolsets'] and 'crm_work_schedule' not in args['enabled_toolsets']
            assert not set(args) & {'model','provider','base_url','skills','script','context_from','workdir','pinned'}
        if args['action'] == 'resume':
            assert current['job_id'] == args['job_id']
            assert current['state'] == 'resume_unknown'
            assert any(e['kind'] == 'job_bound' for e in current['events'])
    host.before = verify
    result = setup[1].schedule(host, a['id'], session_id='caller-session', task_id='caller-task')
    assert result['state'] == 'scheduled'
    assert all(context == {'session_id':'caller-session','task_id':'caller-task'} for _,context in host.calls)
    assert setup[1].schedule(host,a['id']) == result and len(host.calls) == 2
    assert setup[0].get('tasks',setup[2]['id'])['status'] == 'open'


def test_lost_create_reply_leaves_paused_orphan_no_auto_adoption_or_retry(setup):
    a, host = create(setup), Host()
    def lost(args, result):
        if args['action'] == 'create': raise TimeoutError('secret exception content not persisted')
    host.after = lost
    unknown = setup[1].schedule(host, a['id'])
    assert unknown['state'] == 'unknown' and unknown['job_id'] is None
    assert list(host.jobs.values())[0]['enabled'] is False
    host.after = None
    reconciled = setup[1].reconcile(host,a['id'])
    assert reconciled['reason'] == 'unbound_candidates_require_review' and reconciled['job_id'] is None
    assert reconciled['events'][-1]['evidence']['auto_adopted'] is False
    setup[1].schedule(host,a['id'])
    assert [args['action'] for args,_ in host.calls] == ['create','list']
    assert 'secret exception' not in json.dumps(reconciled)


def test_lost_resume_reply_reconciles_exact_bound_job_without_create_or_resume_retry(setup):
    a, host = create(setup), Host()
    def lost(args, result):
        if args['action'] == 'resume': raise TimeoutError('lost')
    host.after = lost
    unknown = setup[1].schedule(host,a['id'])
    assert unknown['state'] == 'unknown' and unknown['job_id'] == 'job-1'
    host.after = None
    reconciled = setup[1].reconcile(host,a['id'])
    assert reconciled['state'] == 'scheduled'
    setup[1].schedule(host,a['id'])
    assert [args['action'] for args,_ in host.calls] == ['create','resume','list']


@pytest.mark.parametrize('response', [{'success':False}, {'success':False,'job_saved':True,'job_id':'known-orphan','scheduler_registered':False}, {'success':True}, 'broken'])
def test_failed_or_malformed_create_never_resumes_or_retries(setup,response):
    a, host = create(setup), Host()
    host.dispatch_tool = lambda *args,**kw: response
    unknown = setup[1].schedule(host,a['id'])
    assert unknown['state'] == 'unknown' and unknown['job_id'] is None
    host.dispatch_tool = lambda *args,**kw: pytest.fail('must not blindly retry')
    setup[1].schedule(host,a['id'])


@pytest.mark.parametrize('change', [dict(enabled=True,state='scheduled'), dict(enabled_toolsets=['crm_read','crm_write']),
                                  dict(deliver='telegram'),dict(provider='other'),dict(script='/tmp/script'),
                                  dict(prompt_preview='replaced'),dict(job_id='foreign'),dict(repeat='forever'),dict(skills=['dangerous'])])
def test_inconsistent_create_response_is_not_bound_or_resumed(setup,change):
    a, host = create(setup),Host()
    host.after=lambda args,result: result['job'].update(change) if args['action']=='create' else None
    result=setup[1].schedule(host,a['id'])
    assert result['state']=='unknown' and result['job_id'] is None
    assert len(host.calls)==1


def test_task_change_during_paused_create_prevents_resume(setup):
    a,host=create(setup),Host()
    host.after=lambda args,result: setup[0].update('tasks',setup[2]['id'],{'version':1,'title':'Changed'}) if args['action']=='create' else None
    result=setup[1].schedule(host,a['id'])
    assert result['job_id']=='job-1' and result['state']!='scheduled'
    assert len(host.calls)==1 and host.jobs['job-1']['enabled'] is False


def test_cancel_during_paused_create_binds_orphan_but_never_resumes(setup):
    a,host=create(setup),Host()
    def cancel_in_flight(args,result):
        if args['action']=='create':
            current=setup[1].get(a['id'])
            setup[1].invalidate(a['id'],version=current['version'])
    host.after=cancel_in_flight
    result=setup[1].schedule(host,a['id'])
    assert result['state']=='cancelled' and result['job_id']=='job-1'
    assert len(host.calls)==1 and host.jobs['job-1']['enabled'] is False


def test_elapsed_run_time_after_create_does_not_resume(setup,monkeypatch):
    import hermes_crm.native_work as native_work
    a,host=create(setup),Host()
    original=native_work._future
    def after(args,result):
        if args['action']=='create': monkeypatch.setattr(native_work,'_future',lambda x: (_ for _ in ()).throw(CRMError('run_at elapsed',409)))
    host.after=after
    result=setup[1].schedule(host,a['id'])
    assert result['state']!='scheduled' and len(host.calls)==1 and not host.jobs['job-1']['enabled']
    monkeypatch.setattr(native_work,'_future',original)


def test_unknown_and_missing_report_are_not_terminal_failure_or_success(setup):
    host,a=scheduled(setup)
    host.jobs[a['job_id']].update(enabled=False,state='completed',next_run_at=None,repeat='1/1',last_status='success')
    result=setup[1].reconcile(host,a['id'])
    assert result['state']=='unknown' and result['reason']=='host_observed_no_authenticated_report'
    assert result['review_status']=='no_report' and not result['host_terminal_success_verified']
    assert result['reports']==[] and setup[0].get('tasks',setup[2]['id'])['status']=='open'


def test_bound_job_absent_stays_unknown_without_retry(setup):
    host,a=scheduled(setup)
    host.jobs.clear()
    result=setup[1].reconcile(host,a['id'])
    assert result['state']=='unknown' and result['job_id']==a['job_id']
    setup[1].schedule(host,a['id'])
    assert len(host.calls)==3


def test_scheduler_health_is_separate_and_unknown_default(setup):
    host,a=scheduled(setup)
    assert a['events'][-1]['evidence']['gateway_running'] is None
    host.gateway_running=False
    a=setup[1].reconcile(host,a['id'])
    assert a['state']=='scheduled' and a['events'][-1]['evidence']['gateway_running'] is False
    assert not a['host_terminal_success_verified'] and a['reports']==[]


def test_authenticated_report_is_awaiting_review_not_host_or_business_success(setup):
    host,a=scheduled(setup)
    result=report(setup,identity(host,a),a)
    assert result['state']=='result_reported' and result['review_status']=='awaiting_human_review'
    assert len(result['reports'])==1 and result['reports'][0]['provenance']=='native_run_reported'
    assert not result['host_terminal_success_verified'] and not result['business_task_completed']
    assert setup[0].get('tasks',setup[2]['id'])['status']=='open'
    assert [args['action'] for args,_ in host.calls]==['create','resume']
    host.identity=None
    host.jobs[a['job_id']].update(enabled=False,state='completed',repeat='1/1',next_run_at=None)
    result=setup[1].reconcile(host,a['id'])
    assert result['state']=='result_reported'


@pytest.mark.parametrize('change',[dict(job_id='other'),dict(job_name='other'),dict(profile='other'),
    dict(scheduled_instant='2030-04-01T12:30:42Z'),dict(scheduled_instant=None),dict(execution_id=''),dict(source=''),dict(source='direct'),dict(source='plugin-provider')])
def test_foreign_or_invalid_execution_identity_cannot_report(setup,change):
    host,a=scheduled(setup)
    with pytest.raises(CRMError): report(setup,identity(host,a,**change),a)
    assert setup[1].get(a['id'])['reports']==[]


def test_missing_context_delegated_child_and_unsupported_host_cannot_report(setup):
    host,a=scheduled(setup)
    with pytest.raises(CRMError,match='Only the assigned'): report(setup,host,a)
    host.current_cron_execution=None
    with pytest.raises(CRMError,match='lacks trusted'): report(setup,host,a)


def test_hosted_mapping_identity_and_equivalent_timestamp_supported(setup):
    host,a=scheduled(setup)
    identity(host,a,scheduled_instant='2030-04-01T14:30:41+02:00')
    host.identity=vars(host.identity)
    result=report(setup,host,a)
    assert result['reports'][0]['identity']['scheduled_instant']==a['payload']['run_at']


@pytest.mark.parametrize('mapping', [False, True], ids=['attributes', 'mapping'])
@pytest.mark.parametrize('started_at,expected', [
    ('2030-11-06T20:44:06.941376-05:00', '2030-11-07T01:44:06.941376+00:00'),
    ('2030-11-07T00:15:06.123456+05:45', '2030-11-06T18:30:06.123456+00:00'),
    # The repeated wall-clock hour during DST fallback names two distinct instants.
    ('2030-11-03T01:30:00-04:00', '2030-11-03T05:30:00.000000+00:00'),
    ('2030-11-03T01:30:00-05:00', '2030-11-03T06:30:00.000000+00:00'),
], ids=['negative-offset-midnight', 'fractional-offset-midnight', 'dst-first-hour', 'dst-second-hour'])
def test_report_started_at_preserves_instant_and_equivalent_replay(setup, mapping, started_at, expected):
    host,a=scheduled(setup)
    identity(host,a,started_at=started_at)
    if mapping: host.identity=vars(host.identity)
    original=copy.deepcopy(host.identity)
    result=report(setup,host,a)
    stored=result['reports'][0]['identity']['started_at']
    assert stored==expected
    assert datetime.fromisoformat(stored)==datetime.fromisoformat(started_at)
    assert host.identity==original, 'Normalization must not rewrite the host evidence'
    assert setup[1].get(a['id'])==result

    # The same instant in UTC must deduplicate, without a new report or version.
    identity(host,a,started_at=expected)
    if mapping: host.identity=vars(host.identity)
    assert report(setup,host,a)==result


@pytest.mark.parametrize('mapping', [False, True], ids=['attributes', 'mapping'])
def test_report_naive_started_at_is_not_assumed_utc(setup, mapping):
    host,a=scheduled(setup)
    identity(host,a,started_at='2030-11-03T01:30:00')
    if mapping: host.identity=vars(host.identity)
    with pytest.raises(CRMError,match='native started_at must be an ISO timestamp with timezone'):
        report(setup,host,a)
    assert setup[1].get(a['id'])==a


def test_forged_model_identity_arguments_rejected_by_signature(setup):
    host,a=scheduled(setup)
    with pytest.raises(TypeError): report(setup,host,a,job_id=a['job_id'],execution_id='forged')
    assert setup[1].get(a['id'])['reports']==[]


@pytest.mark.parametrize('reason',['cancelled','superseded'])
def test_cancelled_superseded_generation_rejects_report(setup,reason):
    host,a=scheduled(setup)
    setup[1].invalidate(a['id'],version=a['version'],reason=reason)
    with pytest.raises(CRMError,match='Cancelled, superseded'): report(setup,identity(host,a),a)


@pytest.mark.parametrize('generation',[0,2,True,'1'])
def test_stale_or_invalid_generation_rejects_report(setup,generation):
    host,a=scheduled(setup)
    with pytest.raises(CRMError): report(setup,identity(host,a),a,generation=generation)


@pytest.mark.parametrize('outcome',['completed','blocked','failed'])
def test_all_reported_outcomes_remain_claims_for_review(setup,outcome):
    host,a=scheduled(setup)
    result=report(setup,identity(host,a),a,outcome=outcome)
    assert result['state']=='result_reported' and result['reports'][0]['outcome']==outcome
    assert result['review_status']=='awaiting_human_review'


def test_duplicate_report_is_idempotent_conflicting_report_rolls_back(setup):
    host,a=scheduled(setup)
    identity(host,a)
    first=report(setup,host,a)
    assert report(setup,host,a)==first
    with pytest.raises(CRMError,match='Conflicting report'): report(setup,host,a,summary='Changed')
    assert setup[1].get(a['id'])==first


def test_stale_source_task_report_rejected_without_marking_done(setup):
    host,a=scheduled(setup)
    setup[0].update('tasks',setup[2]['id'],{'version':1,'title':'Edited'})
    with pytest.raises(CRMError,match='Source task changed'): report(setup,identity(host,a),a)
    assert setup[1].get(a['id'])['reports']==[]
    assert setup[0].get('tasks',setup[2]['id'])['status']=='open'


def test_report_transaction_rolls_back_if_receipt_insert_fails(setup):
    host,a=scheduled(setup)
    def reject(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO crm_native_work_reports'): raise RuntimeError('Synthetic insertion failure')
    event.listen(setup[0].engine,'before_cursor_execute',reject)
    try:
        with pytest.raises(RuntimeError,match='Synthetic'): report(setup,identity(host,a),a)
    finally: event.remove(setup[0].engine,'before_cursor_execute',reject)
    assert setup[1].get(a['id'])==a


def test_create_transaction_rolls_back_if_event_insert_fails(setup):
    def reject(conn,cursor,statement,parameters,context,executemany):
        if statement.startswith('INSERT INTO crm_native_work_events'): raise RuntimeError('Synthetic event failure')
    event.listen(setup[0].engine,'before_cursor_execute',reject)
    try:
        with pytest.raises(RuntimeError): create(setup)
    finally: event.remove(setup[0].engine,'before_cursor_execute',reject)
    assert setup[1].list()==[]


def test_explicit_cancel_invalidates_then_pauses_exact_bound_schedule(setup):
    host,a=scheduled(setup)
    def verify(args):
        if args['action'] in {'list','pause'}:
            current=setup[1].get(a['id'])
            assert current['state']=='cancelled' and current['generation']==2
        if args['action']=='pause': assert args['job_id']==a['job_id']
    host.before=verify
    result=setup[1].cancel(host,a['id'],version=a['version'])
    assert result['state']=='cancelled' and result['reason']=='future_schedule_paused_running_run_not_cancelled'
    assert result['events'][-1]['evidence']['running_execution_cancelled'] is False
    assert [args['action'] for args,_ in host.calls]==['create','resume','list','pause']
    assert not host.jobs[a['job_id']]['enabled']


def test_lost_pause_reply_is_uncertain_local_fence_survives(setup):
    host,a=scheduled(setup)
    host.after=lambda args,result: (_ for _ in ()).throw(TimeoutError()) if args['action']=='pause' else None
    result=setup[1].cancel(host,a['id'],version=a['version'])
    assert result['state']=='cancelled' and result['reason']=='pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind']=='pause_unknown'
    with pytest.raises(CRMError): report(setup,identity(host,a),a)


def test_cancel_foreign_job_name_never_pauses(setup):
    host,a=scheduled(setup)
    host.jobs[a['job_id']]['name']='Foreign replacement'
    result=setup[1].cancel(host,a['id'],version=a['version'])
    assert result['state']=='cancelled' and len(host.calls)==3
    assert host.jobs[a['job_id']]['enabled']


def test_cancel_pending_does_not_call_host_or_claim_host_cancellation(setup):
    a,host=create(setup),Host()
    result=setup[1].cancel(host,a['id'],version=a['version'])
    assert result['state']=='cancelled' and not host.calls
    assert result['events'][-1]['evidence']['host_cancelled'] is False


def test_invalid_profile_or_recursion_prevents_scheduling(setup):
    a,host=create(setup),Host()
    host.profile_name='other'
    with pytest.raises(CRMError,match='profile'): setup[1].schedule(host,a['id'])
    host.profile_name='synthetic'
    identity(host,dict(a,job_id='some-cron-job'))
    with pytest.raises(CRMError,match='cannot schedule'): setup[1].schedule(host,a['id'])
    assert host.calls==[]


def test_host_response_secrets_transcripts_and_unrelated_jobs_not_persisted(setup):
    host,a=scheduled(setup)
    host.jobs[a['job_id']].update(last_error='password=SECRET',last_output='PRIVATE TRANSCRIPT',arbitrary={'api_key':'SECRET'})
    host.jobs['unrelated']=dict(job_id='unrelated',name='Personal unrelated job',prompt='PRIVATE OTHER DATA')
    result=setup[1].reconcile(host,a['id'])
    dumped=json.dumps(result)
    assert all(value not in dumped for value in ['SECRET','PRIVATE','Personal unrelated'])
    with setup[0].engine.connect() as conn:
        dumped=' '.join(conn.execute(select(events.c.evidence)).scalars().all())
    assert 'SECRET' not in dumped and 'PRIVATE' not in dumped


def test_list_limits_and_task_filter(setup):
    a=create(setup)
    assert setup[1].list(task_id=a['task_id'])==[a]
    assert setup[1].list(task_id='other')==[]
    for limit in [0,501,True,'1']:
        with pytest.raises(CRMError): setup[1].list(limit=limit)


def test_concurrent_identical_reports_dedupe(setup):
    host,a=scheduled(setup)
    identity(host,a)
    with ThreadPoolExecutor(max_workers=6) as pool:
        values=list(pool.map(lambda _: report(setup,host,a),range(6)))
    assert len(values[0]['reports'])==1
    assert all(v==values[0] for v in values)


def test_stale_report_records_minimal_rejection_evidence(setup):
    host,a=scheduled(setup)
    identity(host,a)
    setup[0].update('tasks',setup[2]['id'],{'version':1,'status':'done'})
    for _ in range(2):
        with pytest.raises(CRMError,match='Source task changed'):
            report(setup,host,a,summary='This rejected content should not be stored')
    result=setup[1].get(a['id'])
    rejected=[e for e in result['events'] if e['kind']=='stale_report_rejected']
    assert len(rejected)==1 and rejected[0]['evidence']['accepted'] is False
    assert result['reports']==[] and 'rejected content' not in json.dumps(result)
    assert result['business_task_completed'] is True and result['business_task_completed_by_report'] is False


def test_accepted_report_becomes_stale_after_later_source_edit(setup):
    host,a=scheduled(setup)
    report(setup,identity(host,a),a)
    setup[0].update('tasks',setup[2]['id'],{'version':1,'title':'Changed'})
    result=setup[1].get(a['id'])
    assert result['state']=='result_reported' and result['review_status']=='awaiting_human_review'
    assert len(result['reports'])==1 and result['source_task_current'] is False


@pytest.mark.parametrize('defect',['missing_unique','wrong_type','nullable','missing_foreign_key'])
def test_same_columns_with_incompatible_constraints_fail_closed(tmp_path,defect):
    from sqlalchemy import MetaData, String, UniqueConstraint
    crm=CRM(f'sqlite:///{tmp_path}/constraints.db',profile='synthetic')
    cloned=MetaData()
    tasks.to_metadata(cloned)
    table=assignments.to_metadata(cloned)
    if defect=='missing_unique':
        for constraint in list(table.constraints):
            if isinstance(constraint,UniqueConstraint): table.constraints.remove(constraint)
    elif defect=='wrong_type': table.c.profile.type=String(10)
    elif defect=='nullable': table.c.profile.nullable=True
    else:
        for constraint in list(table.foreign_key_constraints): table.constraints.remove(constraint)
    table.create(crm.engine)
    with pytest.raises(CRMError,match='explicit migration'): NativeWorkStore(crm)
    crm.close()


def test_intent_integrity_mismatch_fails_closed(setup):
    a=create(setup)
    with setup[0].engine.begin() as conn:
        conn.execute(update(assignments).where(assignments.c.id==a['id']).values(digest='0'*64))
    host=Host()
    with pytest.raises(CRMError,match='integrity'): setup[1].get(a['id'])
    with pytest.raises(CRMError,match='integrity'): setup[1].schedule(host,a['id'])
    assert host.calls==[]


def test_cancel_while_resume_response_unknown_does_not_enable_replacement(setup):
    a,host=create(setup),Host()
    host.after=lambda args,result: (_ for _ in ()).throw(TimeoutError()) if args['action']=='resume' else None
    unknown=setup[1].schedule(host,a['id'])
    assert unknown['state']=='unknown'
    host.after=None
    cancelled=setup[1].cancel(host,a['id'],version=unknown['version'])
    assert cancelled['state']=='cancelled' and cancelled['generation']==2
    setup[1].schedule(host,a['id'])
    assert [args['action'] for args,_ in host.calls]==['create','resume','list','pause']


def test_mutated_bound_job_scope_reconciliation_remains_unknown(setup):
    host,a=scheduled(setup)
    host.jobs[a['job_id']]['enabled_toolsets'].append('crm_write')
    result=setup[1].reconcile(host,a['id'])
    assert result['state']=='unknown' and result['reason']=='bound_job_unverified'
    assert result['host_terminal_success_verified'] is False


@pytest.mark.parametrize('list_fails',[False,True])
def test_reconcile_pending_intent_never_disables_first_schedule(setup,list_fails):
    a,host=create(setup),Host()
    def before(args):
        if args['action']=='list' and list_fails: raise TimeoutError()
    host.before=before
    result=setup[1].reconcile(host,a['id'])
    assert result==a and host.calls==[]
    result=setup[1].schedule(host,a['id'])
    assert result['state']=='scheduled'


def test_reconcile_does_not_overwrite_newer_local_state(setup):
    host,a=scheduled(setup)
    def during(args,result):
        if args['action']=='list':
            current=setup[1].get(a['id'])
            setup[1].invalidate(a['id'],version=current['version'])
    host.after=during
    result=setup[1].reconcile(host,a['id'])
    assert result['state']=='cancelled'
    saved=setup[1].get(a['id'])
    assert saved['events'][-1]['kind']=='reconcile_stale'


@pytest.mark.parametrize('phase',['create','resume'])
def test_process_interruption_keeps_precommitted_unknown_boundary(setup,phase):
    a,host=create(setup),Host()
    def interrupted(args,result):
        if args['action']==phase: raise KeyboardInterrupt('Synthetic process interruption')
    host.after=interrupted
    with pytest.raises(KeyboardInterrupt): setup[1].schedule(host,a['id'])
    saved=setup[1].get(a['id'])
    assert saved['state']==f'{phase}_unknown'
    assert any(e['kind']==f'{phase}_started' for e in saved['events'])
    if phase=='create':
        assert saved['job_id'] is None and not host.jobs['job-1']['enabled']
    else:
        assert saved['job_id']=='job-1' and host.jobs['job-1']['enabled']
        saved=report(setup,identity(host,saved),saved)
        assert saved['state']=='result_reported' and len(saved['reports'])==1
    assert setup[0].get('tasks',setup[2]['id'])['status']=='open'


@pytest.mark.parametrize('value', [None, True, False, 0, -1, '1', 1.0, [], {}])
def test_expected_task_version_is_strict_positive_integer(setup, value):
    with pytest.raises(CRMError, match='positive integer'):
        create(setup, expected_task_version=value)
    assert setup[1].list() == []


def test_expected_task_version_replay_binds_presence_and_original_approval(setup):
    crm, store, task = setup
    approved = create(setup, expected_task_version=1)
    assert approved['payload']['expected_task_version'] == 1
    crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    replay = create(setup, expected_task_version=1)
    assert replay['id'] == approved['id'] and replay['version'] == approved['version']
    assert replay['payload'] == approved['payload'] and len(replay['events']) == 1
    assert replay['business_task_completed'] and not replay['source_task_current']
    for change in ({'expected_task_version': 2}, {}):
        with pytest.raises(CRMError, match='payload conflict'): create(setup, **change)


def test_expected_task_version_does_not_reinterpret_legacy_request(setup):
    original = create(setup)
    assert 'expected_task_version' not in original['payload']
    assert create(setup)['id'] == original['id']
    with pytest.raises(CRMError, match='payload conflict'): create(setup, expected_task_version=1)


def test_expected_task_version_rejects_changed_source_without_intent_or_events(setup):
    setup[0].update('tasks', setup[2]['id'], {'version': 1, 'title': 'Changed subject'})
    with pytest.raises(CRMError, match='version changed'): create(setup, expected_task_version=1)
    assert setup[1].list() == []
    with setup[0].engine.connect() as conn: assert conn.execute(select(events)).all() == []
    assert create(setup, expected_task_version=2)['payload']['task_version'] == 2


@pytest.mark.parametrize('change', [{'title': 'Concurrent edit'}, {'status': 'done'}])
def test_expected_task_version_guards_edit_between_read_and_insert(setup, monkeypatch, change):
    crm, store, task = setup
    original = store._guard_task
    def raced(conn, row):
        crm.update('tasks', task['id'], dict(change, version=1))
        original(conn, row)
    monkeypatch.setattr(store, '_guard_task', raced)
    with pytest.raises(CRMError, match='Source task changed'): create(setup, expected_task_version=1)
    assert store.list() == []
    with crm.engine.connect() as conn: assert conn.execute(select(events)).all() == []


def test_expected_task_version_concurrent_exact_key_is_one_intent(setup):
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda _: create(setup, expected_task_version=1), range(6)))
    assert len({row['id'] for row in rows}) == 1
    assert len(setup[1].list()) == 1
    assert len(rows[-1]['events']) == 1


@pytest.mark.parametrize('table_name', ['crm_native_assignments', 'crm_native_work_events'])
def test_expected_task_version_first_insert_rolls_back(setup, table_name):
    def reject(conn, cursor, statement, parameters, context, executemany):
        stmt = getattr(context.compiled, 'statement', None)
        if getattr(stmt, 'is_insert', False) and stmt.table.name == table_name:
            raise RuntimeError('Synthetic insertion failure')
    event.listen(setup[0].engine, 'before_cursor_execute', reject)
    try:
        with pytest.raises(RuntimeError, match='Synthetic'):
            create(setup, expected_task_version=1)
    finally:
        event.remove(setup[0].engine, 'before_cursor_execute', reject)
    assert setup[1].list() == []
    with setup[0].engine.connect() as conn: assert conn.execute(select(events)).all() == []
    assert create(setup, expected_task_version=1)['state'] == 'pending'
