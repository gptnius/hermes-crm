"""Synthetic-only terminal cancellation observations; no native jobs or providers."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest

from hermes_crm.domain import CRMError
from hermes_crm import native_work
from test_native_work import identity, report, scheduled, setup


def completed(host, assignment):
    host.jobs[assignment['job_id']].update(
        enabled=False, state='completed', next_run_at=None, repeat='1/1')


@pytest.mark.parametrize('has_report', [False, True])
def test_cancel_completed_disabled_one_shot_observes_without_pause(setup, has_report):
    host, assignment = scheduled(setup)
    if has_report:
        assignment = report(setup, identity(host, assignment), assignment)
        host.identity = None
    completed(host, assignment)

    def check(args):
        assert args['action'] == 'list', 'A completed disabled one-shot must not be paused'
        local = setup[1].get(assignment['id'])
        assert local['state'] == 'cancelled' and local['generation'] == 2

    host.before = check
    context = {'session_id': 'cancel-session', 'task_id': 'cancel-task'}
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'], **context)
    assert result['reason'] == 'future_schedule_already_inactive_running_run_not_cancelled'
    assert result['state'] == 'cancelled' and result['generation'] == 2
    assert result['reports'] == assignment['reports']
    event = result['events'][-1]
    assert event['kind'] == 'inactive_schedule_observed'
    assert event['version'] > result['events'][-2]['version']
    assert event['evidence'] == {
        'source': 'public_job_list', 'job_id': assignment['job_id'], 'state': 'completed',
        'enabled': False, 'next_run_at': None, 'future_schedule_inactive': True,
        'pause_attempted': False, 'running_execution_cancelled': False}
    assert [args['action'] for args, _ in host.calls] == ['create', 'resume', 'list']
    assert host.calls[-1][1] == context
    assert not result['business_task_completed'] and not result['host_terminal_success_verified']
    assert setup[0].get('tasks', setup[2]['id'])['status'] == 'open'
    with pytest.raises(CRMError, match='Cancelled, superseded'):
        report(setup, identity(host, assignment, execution_id='after-cancel'), assignment)


@pytest.mark.parametrize('change', [
    {'enabled': True}, {'enabled': None}, {'enabled': 0}, {'enabled': 'false'},
    {'state': 'error'}, {'state': 'paused'}, {'state': 'running'}, {'state': None},
    {'next_run_at': '2030-04-01T12:30:41Z'}, {'next_run_at': ''},
    {'repeat': 'forever'}, {'repeat': '2/2'}, {'schedule': 'every day'},
    {'deliver': 'external'}, {'enabled_toolsets': ['all']},
    {'prompt_preview': 'Different instructions'}, {'script': '/unrelated/script'},
])
def test_incomplete_or_conflicting_job_never_becomes_inactive_success(setup, change):
    host, assignment = scheduled(setup)
    completed(host, assignment)
    host.jobs[assignment['job_id']].update(change)
    # A failed pause cannot be reinterpreted as terminal-success evidence.
    host.before = lambda args: (_ for _ in ()).throw(PermissionError('denied')) if args['action'] == 'pause' else None
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'pause_unknown'
    assert [args['action'] for args, _ in host.calls][-2:] == ['list', 'pause']


@pytest.mark.parametrize('field', ['enabled', 'state', 'next_run_at', 'repeat', 'enabled_toolsets'])
def test_missing_fields_are_not_null_terminal_evidence(setup, field):
    host, assignment = scheduled(setup)
    completed(host, assignment)
    host.jobs[assignment['job_id']].pop(field)
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError()) if args['action'] == 'pause' else None
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'pause_unknown'


@pytest.mark.parametrize('corrupt', ['missing', 'duplicate', 'conflicting_duplicate', 'foreign_name',
                                     'wrong_id', 'not_list', 'missing_jobs', 'failed'])
def test_absent_ambiguous_or_failed_list_never_proves_inactive(setup, corrupt):
    host, assignment = scheduled(setup)
    completed(host, assignment)

    def mutate(args, response):
        assert args['action'] == 'list', 'An unusable exact-job observation must not dispatch pause'
        if corrupt == 'missing':
            response.update(jobs=[], count=100, truncated=True)
        elif corrupt in {'duplicate', 'conflicting_duplicate'}:
            duplicate = copy.deepcopy(response['jobs'][0])
            if corrupt == 'conflicting_duplicate':
                duplicate['name'] = 'Foreign replacement'
                duplicate['enabled'] = True
            response['jobs'].append(duplicate)
        elif corrupt == 'foreign_name': response['jobs'][0]['name'] = 'Foreign replacement'
        elif corrupt == 'wrong_id': response['jobs'][0]['job_id'] = 'unbound-job'
        elif corrupt == 'not_list': response['jobs'] = {'unrelated': 'invalid'}
        elif corrupt == 'missing_jobs': response.pop('jobs')
        elif corrupt == 'failed': response['success'] = False

    host.after = mutate
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'pause_unknown'
    assert [args['action'] for args, _ in host.calls] == ['create', 'resume', 'list']


def test_failed_cancel_and_reconcile_keep_old_unknown_until_fresh_observation(setup):
    host, assignment = scheduled(setup)
    host.before = lambda args: (_ for _ in ()).throw(PermissionError('denied')) if args['action'] == 'pause' else None
    unknown = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    completed(host, assignment)
    assert setup[1].get(assignment['id']) == unknown
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
    result = setup[1].reconcile(host, assignment['id'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'reconcile_unknown'
    assert not any(event['evidence'].get('future_schedule_inactive') for event in result['events'])
    host.before = None
    result = setup[1].reconcile(host, assignment['id'])
    # Reconciliation adds new evidence, never rewrites the failed pause history.
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'job_observed'
    assert result['events'][-1]['evidence']['future_schedule_inactive'] is True
    assert result['events'][-1]['evidence']['next_run_at'] is None
    assert any(event['kind'] == 'pause_unknown' for event in result['events'])
    assert sum(args['action'] == 'pause' for args, _ in host.calls) == 1


def test_later_scheduled_observation_contradicts_inactive_without_new_pause(setup):
    host, assignment = scheduled(setup)
    completed(host, assignment)
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    host.jobs[assignment['job_id']].update(
        enabled=True, state='scheduled', next_run_at=assignment['payload']['run_at'])
    result = setup[1].reconcile(host, assignment['id'])
    assert result['state'] == 'cancelled'
    assert result['events'][-1]['kind'] == 'job_observed'
    assert result['events'][-1]['evidence']['future_schedule_inactive'] is False
    assert result['events'][-1]['evidence']['enabled'] is True
    assert not any(args['action'] == 'pause' for args, _ in host.calls)


def test_concurrent_local_observation_invalidates_terminal_cancel_snapshot(setup):
    host, assignment = scheduled(setup)
    completed(host, assignment)

    def changed(args, response):
        assert args['action'] == 'list'
        with setup[0].engine.begin() as conn:
            row = setup[1]._row(conn, assignment['id'])
            setup[1]._change(conn, row, reason='concurrent_local_change')

    host.after = changed
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'pause_unknown'
    assert not any(args['action'] == 'pause' for args, _ in host.calls)


@pytest.mark.parametrize('failed_check', [False, True])
@pytest.mark.parametrize('outer_action', ['cancel', 'reconcile'])
def test_evidence_only_concurrent_check_invalidates_old_inactive_observation(setup, failed_check, outer_action):
    host, assignment = scheduled(setup)
    assignment = setup[1].invalidate(assignment['id'], version=assignment['version'])
    completed(host, assignment)

    def newer_check(args, response):
        assert args['action'] == 'list'
        host.after = None
        host.jobs[assignment['job_id']].update(
            enabled=True, state='scheduled', next_run_at=assignment['payload']['run_at'])
        if failed_check: host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
        newer = setup[1].reconcile(host, assignment['id'])
        assert newer['version'] == assignment['version'], 'This is an evidence-only update'
        assert newer['events'][-1]['kind'] == ('reconcile_unknown' if failed_check else 'job_observed')
        host.before = None

    host.after = newer_check
    if outer_action == 'cancel':
        result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
        assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
        assert result['events'][-1]['kind'] == 'pause_unknown'
    else:
        result = setup[1].reconcile(host, assignment['id'])
        assert result['events'][-1]['kind'] == 'reconcile_stale'
    assert not any(event['evidence'].get('future_schedule_inactive') for event in result['events'])
    assert not any(args['action'] == 'pause' for args, _ in host.calls)


@pytest.mark.parametrize('failed_check', [False, True])
def test_newer_evidence_also_invalidates_old_successful_pause_response(setup, failed_check):
    host, assignment = scheduled(setup)
    assignment = setup[1].invalidate(assignment['id'], version=assignment['version'])

    def newer_check(args, response):
        if args['action'] != 'pause': return
        host.after = None
        host.jobs[assignment['job_id']].update(
            enabled=True, state='scheduled', next_run_at=assignment['payload']['run_at'])
        if failed_check: host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
        newer = setup[1].reconcile(host, assignment['id'])
        assert newer['version'] == assignment['version']
        host.before = None

    host.after = newer_check
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    assert result['reason'] == 'pause_outcome_unknown_running_run_not_cancelled'
    assert result['events'][-1]['kind'] == 'pause_unknown'
    assert result['events'][-1]['evidence']['future_schedule_paused'] is False
    assert host.jobs[assignment['job_id']]['enabled'] is True
    assert sum(args['action'] == 'pause' for args, _ in host.calls) == 1


@pytest.mark.parametrize('outer_action', ['cancel', 'reconcile'])
def test_event_only_writer_serializes_after_locked_inactive_observation(setup, monkeypatch, outer_action):
    host, assignment = scheduled(setup)
    assignment = setup[1].invalidate(assignment['id'], version=assignment['version'])
    completed(host, assignment)
    store = setup[1]
    original_count, original_event = store._event_count, store._event
    writer_at_event, writer_finished = threading.Event(), threading.Event()
    futures = []

    def append_unknown():
        try:
            return store._uncertain(assignment['id'], 'reconciliation_unavailable', kind='reconcile_unknown')
        finally:
            writer_finished.set()

    def observe_event(conn, row, kind, evidence):
        if kind == 'reconcile_unknown': writer_at_event.set()
        return original_event(conn, row, kind, evidence)

    with ThreadPoolExecutor(max_workers=1) as pool:
        def count_with_concurrent_append(conn, assignment_id):
            value = original_count(conn, assignment_id)
            futures.append(pool.submit(append_unknown))
            assert writer_at_event.wait(2), 'Concurrent evidence writer did not reach append'
            assert not writer_finished.wait(.05), 'Evidence append bypassed the assignment lock'
            return value

        monkeypatch.setattr(store, '_event', observe_event)
        monkeypatch.setattr(store, '_event_count', count_with_concurrent_append)
        if outer_action == 'cancel':
            store.cancel(host, assignment['id'], version=assignment['version'])
        else:
            store.reconcile(host, assignment['id'])
        assert len(futures) == 1
        futures[0].result(timeout=5)

    result = store.get(assignment['id'])
    assert result['events'][-2]['evidence']['future_schedule_inactive'] is True
    assert result['events'][-1]['kind'] == 'reconcile_unknown'
    assert result['events'][-1]['version'] == result['version']
    assert result['events'][-1]['created_at'] > result['events'][-2]['created_at']


@pytest.mark.parametrize('clock_rollback', [False, True])
def test_equal_or_rollback_clock_keeps_new_unknown_after_inactive_evidence(setup, monkeypatch, clock_rollback):
    host, assignment = scheduled(setup)
    assignment = setup[1].invalidate(assignment['id'], version=assignment['version'])
    completed(host, assignment)
    monkeypatch.setattr(native_work, 'now', lambda: '2030-04-01T13:00:00.000000+00:00')
    observed = setup[1].reconcile(host, assignment['id'])
    assert observed['events'][-1]['evidence']['future_schedule_inactive'] is True
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
    if clock_rollback:
        monkeypatch.setattr(native_work, 'now', lambda: '2029-04-01T13:00:00.000000+00:00')
    unknown = setup[1].reconcile(host, assignment['id'])
    assert unknown['version'] == observed['version']
    assert unknown['events'][-1]['kind'] == 'reconcile_unknown'
    recorded = [datetime.fromisoformat(event['created_at']) for event in unknown['events']]
    assert recorded == sorted(set(recorded))


def test_inactive_recording_failure_rolls_back_observation_but_keeps_local_cancel(setup, monkeypatch):
    host, assignment = scheduled(setup)
    completed(host, assignment)
    original_event = setup[1]._event

    def failed_recording(conn, row, kind, evidence):
        if kind == 'inactive_schedule_observed': raise RuntimeError('Synthetic evidence insert failure')
        return original_event(conn, row, kind, evidence)

    monkeypatch.setattr(setup[1], '_event', failed_recording)
    with pytest.raises(RuntimeError, match='Synthetic evidence'):
        setup[1].cancel(host, assignment['id'], version=assignment['version'])
    result = setup[1].get(assignment['id'])
    assert result['state'] == 'cancelled' and result['generation'] == 2
    assert result['reason'] == 'local_only_host_cancellation_unverified'
    assert result['events'][-1]['kind'] == 'intent_invalidated'
    assert not any(args['action'] == 'pause' for args, _ in host.calls)


def test_inactive_evidence_never_persists_host_secrets_or_transcripts(setup):
    host, assignment = scheduled(setup)
    completed(host, assignment)
    host.jobs[assignment['job_id']].update(
        last_error='password=SECRET', last_output='PRIVATE TRANSCRIPT', arbitrary={'api_key': 'SECRET'})
    host.jobs['unrelated'] = {'job_id': 'unrelated', 'name': 'Private unrelated task', 'prompt': 'PRIVATE DATA'}
    result = setup[1].cancel(host, assignment['id'], version=assignment['version'])
    serialized = json.dumps(result)
    assert result['events'][-1]['kind'] == 'inactive_schedule_observed'
    assert 'SECRET' not in serialized and 'PRIVATE' not in serialized and 'unrelated' not in serialized
