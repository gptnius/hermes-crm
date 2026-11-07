"""Inactive operation ledger only; no real host, model, jobs or sockets."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import MetaData, String, UniqueConstraint, event, inspect, select, text, update

from hermes_crm.domain import CRM, CRMError, tasks
from hermes_crm.native_work import NativeWorkStore, assignments
from hermes_crm.native_work_operations import WorkOperationStore, operations


@pytest.fixture
def setup(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/operations.db', profile='synthetic')
    task = crm.create('tasks', {'title': 'Synthetic internal analysis', 'due_at': '2099-05-01T00:00:00Z'})
    work = NativeWorkStore(crm)
    assignment = work.create(task_id=task['id'], human_owner='Synthetic owner', prompt='  Original instructions\n',
        success_criteria='Full original criteria', run_at='2099-04-01T12:30:41Z', idempotency_key='assignment')
    store = WorkOperationStore(crm, initialize=True)
    yield crm, store, assignment, task
    crm.close()


def prepare(setup, **changes):
    args = dict(verb='schedule', assignment_id=setup[2]['id'], expected_assignment_version=1,
                intended_session_id='native-session-1', idempotency_key='operation-1')
    args.update(changes)
    return setup[1].prepare(**args)


def test_prepare_freezes_backend_snapshot_without_scheduling(setup):
    crm, store, assignment, task = setup
    operation = prepare(setup)
    assert operation['state'] == 'prepared' and operation['actual_session_id'] is None
    assert operation['schema_version'] == 1 and operation['version'] == 1
    assert operation['mutation_slot_held'] is True and operation['deadline_elapsed'] is False
    assert operation['snapshot']['assignment']['payload'] == assignment['payload']
    assert operation['snapshot']['assignment']['payload']['prompt'] == '  Original instructions\n'
    assert operation['snapshot']['task']['version'] == task['version']
    assert operation['snapshot']['task']['title'] == task['title']
    assert NativeWorkStore(crm).get(assignment['id']) == assignment
    assert not {'source_digest', 'actual_session_key', 'request'} & set(operation)
    assert prepare(setup) == operation


def test_snapshot_and_idempotency_survive_changes_and_restart(setup):
    crm, store, assignment, task = setup
    operation = prepare(setup)
    crm.update('tasks', task['id'], {'version': task['version'], 'title': 'Changed'})
    NativeWorkStore(crm).invalidate(assignment['id'], version=1)
    assert prepare(setup) == operation
    reopened = CRM(crm.url, profile='synthetic')
    try: assert WorkOperationStore(reopened).get(operation['id']) == operation
    finally: reopened.close()
    with pytest.raises(CRMError, match='payload conflict'):
        prepare(setup, intended_session_id='another-session')


@pytest.mark.parametrize('changes', [dict(expected_assignment_version=True), dict(expected_assignment_version=0),
    dict(expected_assignment_version='1'), dict(verb='run-now'), dict(intended_session_id=''), dict(idempotency_key='')])
def test_prepare_rejects_invalid_inputs(setup, changes):
    with pytest.raises(CRMError): prepare(setup, **changes)


def test_stale_task_and_assignment_fail_closed(setup):
    crm, store, assignment, task = setup
    with pytest.raises(CRMError, match='Stale assignment'): prepare(setup, expected_assignment_version=2)
    crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    with pytest.raises(CRMError, match='Source task'): prepare(setup)
    # Check/cancel freeze the real current task state, they do not lie that it is open.
    assert prepare(setup, verb='check')['snapshot']['task']['status'] == 'done'
    assert prepare(setup, verb='cancel', idempotency_key='cancel')['snapshot']['task']['status'] == 'done'


def test_schedule_rejects_non_pending_assignment(setup):
    NativeWorkStore(setup[0]).invalidate(setup[2]['id'], version=1)
    with pytest.raises(CRMError, match='never-scheduled'):
        prepare(setup, expected_assignment_version=2)


def test_status_no_table_creation_and_foreign_scope_rejected(setup, tmp_path):
    operation = prepare(setup)
    other = CRM(f'sqlite:///{tmp_path}/other.db', profile='synthetic')
    try:
        before = inspect(other.engine).get_table_names()
        with pytest.raises(CRMError, match='not found'): WorkOperationStore(other).get(operation['id'])
        assert inspect(other.engine).get_table_names() == before
    finally: other.close()
    old = setup[0].profile
    setup[0].profile = 'foreign'
    try:
        with pytest.raises(CRMError, match='not found'): WorkOperationStore(setup[0]).get(operation['id'])
    finally: setup[0].profile = old


def test_withdraw_is_local_idempotent_fence(setup):
    operation = prepare(setup)
    withdrawn = setup[1].withdraw(operation['id'])
    assert withdrawn['state'] == 'withdrawn' and withdrawn['mutation_slot_held'] is False
    assert withdrawn['reason'] == 'prepared_command_withdrawn_no_dispatch'
    assert setup[1].withdraw(operation['id']) == withdrawn
    assert NativeWorkStore(setup[0]).get(setup[2]['id']) == setup[2]


def test_read_expiry_observation_does_not_mutate_or_release_slot(setup):
    operation = prepare(setup)
    with setup[0].engine.begin() as conn:
        conn.execute(update(operations).where(operations.c.id == operation['id']).values(expires_at='2000-01-01T00:00:00+00:00'))
    result = setup[1].get(operation['id'])
    assert result['deadline_elapsed'] is True and result['mutation_slot_held'] is True
    assert result['state'] == 'prepared' and result['version'] == 1
    assert setup[1].get(operation['id']) == result


def test_snapshot_integrity_fails_closed(setup):
    operation = prepare(setup)
    with setup[0].engine.begin() as conn:
        conn.execute(update(operations).where(operations.c.id == operation['id']).values(snapshot='{}'))
    with pytest.raises(CRMError, match='integrity'): setup[1].get(operation['id'])


def test_bad_operation_ids_rejected(setup):
    for value in ('x', '1234', ' approve', None, {}, 'ffffffff-ffff-ffff-ffff-ffffffffffff confirm'):
        with pytest.raises(CRMError): setup[1].get(value)


def test_prepare_transaction_rolls_back_insert_failure(setup):
    crm, store, _, _ = setup
    def fail(conn, cursor, statement, params, context, many):
        if statement.startswith('INSERT INTO') and 'crm_native_work_operations' in statement: raise RuntimeError('synthetic failure')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic'): prepare(setup)
    finally: event.remove(crm.engine, 'before_cursor_execute', fail)
    with crm.engine.connect() as conn: assert conn.execute(select(operations)).all() == []
    assert prepare(setup)['state'] == 'prepared'


def test_concurrent_same_idempotency_key_has_one_snapshot(setup):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: prepare(setup), range(4)))
    assert len({row['id'] for row in results}) == 1
    with setup[0].engine.connect() as conn: assert len(conn.execute(select(operations)).all()) == 1


def test_mutation_slot_reserves_unresolved_intent_before_command_delivery(setup):
    first = prepare(setup)
    with pytest.raises(CRMError, match='unresolved operation'):
        prepare(setup, idempotency_key='second')
    check = prepare(setup, verb='check', idempotency_key='observe')
    assert check['mutation_slot_held'] is False
    setup[1].withdraw(first['id'])
    assert prepare(setup, idempotency_key='second')['mutation_slot_held'] is True


def test_existing_tables_unchanged(setup):
    before = {t: inspect(setup[0].engine).get_columns(t) for t in inspect(setup[0].engine).get_table_names()}
    WorkOperationStore(setup[0], initialize=True)
    after = {t: inspect(setup[0].engine).get_columns(t) for t in inspect(setup[0].engine).get_table_names()}
    assert str(before) == str(after)


def test_incompatible_operation_schema_not_migrated(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/incompatible.db')
    try:
        with crm.engine.begin() as conn: conn.execute(text('CREATE TABLE crm_native_work_operations (id TEXT PRIMARY KEY)'))
        with pytest.raises(CRMError, match='explicit migration'): WorkOperationStore(crm, initialize=True)
        assert [c['name'] for c in inspect(crm.engine).get_columns(operations.name)] == ['id']
    finally: crm.close()


from types import SimpleNamespace
from test_native_work import Host
from hermes_crm.native_work_operations import _CommandGuard


def context():
    return dict(source=SimpleNamespace(platform='local', chat_id='source-chat', user_id='synthetic-user',
        profile='synthetic', chat_type='dm', detached_route=None), session_id='native-session-1',
        session_key='local-session-key', platform='local')


def execute(setup, operation, host=None, **changes):
    host = host or Host()
    ctx = context()
    ctx.update(changes)
    return setup[1].execute(host, operation['id'], **ctx)


def test_confirmed_command_schedules_exactly_once_without_question(setup):
    operation = prepare(setup)
    host = Host()
    result = execute(setup, operation, host)
    assert result['state'] == 'finished' and result['result']['state'] == 'scheduled'
    assert result['provenance'] == 'authenticated_local_command'
    assert result['authorization_channel'] == 'crm_user_command'
    assert result['actual_session_id'] == 'native-session-1'
    assert [c[0]['action'] for c in host.calls] == ['create', 'resume']
    assert all('_operation_guard' not in c[1] for c in host.calls)
    assert all(c[1] == dict(session_id='native-session-1', session_key='local-session-key', platform='local') for c in host.calls)
    assert execute(setup, operation, host) == result
    assert len(host.calls) == 2


def test_wrong_native_session_platform_profile_and_cron_context_rejected(setup):
    operation = prepare(setup)
    host = Host()
    with pytest.raises(CRMError, match='session does not match'):
        execute(setup, operation, host, session_id='foreign')
    with pytest.raises(CRMError, match='genuine local'):
        execute(setup, operation, host, platform='telegram')
    host.profile_name = 'foreign'
    with pytest.raises(CRMError, match='profile'): execute(setup, operation, host)
    assert host.calls == [] and setup[1].get(operation['id'])['state'] == 'prepared'


def test_expired_and_withdrawn_delayed_commands_never_dispatch(setup):
    operation = prepare(setup)
    host = Host()
    setup[1].withdraw(operation['id'])
    assert execute(setup, operation, host)['state'] == 'withdrawn'
    expired = prepare(setup, idempotency_key='expired')
    with setup[0].engine.begin() as conn:
        conn.execute(update(operations).where(operations.c.id == expired['id']).values(expires_at='2000-01-01T00:00:00+00:00'))
    assert execute(setup, expired, host)['state'] == 'expired'
    assert host.calls == []


def test_task_and_assignment_changes_after_review_rejected(setup):
    operation = prepare(setup)
    setup[0].update('tasks', setup[3]['id'], {'version':1, 'title':'Changed'})
    host = Host()
    assert execute(setup, operation, host)['state'] == 'stale'
    assert host.calls == []


def test_assignment_version_change_after_review_rejected(setup):
    operation = prepare(setup)
    NativeWorkStore(setup[0]).invalidate(setup[2]['id'], version=1)
    host = Host()
    assert execute(setup, operation, host)['state'] == 'stale'
    assert host.calls == []


def test_same_command_concurrent_consumers_only_create_once(setup):
    operation = prepare(setup)
    host = Host()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: execute(setup, operation, host), range(4)))
    assert {r['state'] for r in results} <= {'dispatching', 'finished'}
    assert [c[0]['action'] for c in host.calls] == ['create', 'resume']
    assert setup[1].get(operation['id'])['state'] == 'finished'


def test_operation_and_assignment_claim_roll_back_together(setup):
    crm, store, assignment, _ = setup
    operation = prepare(setup)
    host, ctx = Host(), context()
    fingerprint = store._source_identity(host, **ctx)
    guard = _CommandGuard(store, operation['id'], host, ctx['source'], ctx['session_id'], ctx['session_key'], ctx['platform'], fingerprint)
    def fail(conn, cursor, statement, params, context, many):
        if statement.startswith('INSERT INTO') and 'crm_native_work_events' in statement: raise RuntimeError('synthetic claim rollback')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic claim rollback'):
            store.work.schedule(host, assignment['id'], _operation_guard=guard)
    finally: event.remove(crm.engine, 'before_cursor_execute', fail)
    assert store.get(operation['id'])['state'] == 'prepared'
    assert store.work.get(assignment['id'])['state'] == 'pending'
    assert host.calls == []


def test_source_change_before_create_blocks_external_call(setup, monkeypatch):
    operation = prepare(setup)
    ctx, host = context(), Host()
    original = NativeWorkStore._command_dispatch
    def change(self, native_ctx, request, *args):
        ctx['source'].chat_id = 'changed-source'
        return original(self, native_ctx, request, *args)
    monkeypatch.setattr(NativeWorkStore, '_command_dispatch', change)
    result = setup[1].execute(host, operation['id'], **ctx)
    assert result['state'] == 'stale' and host.calls == []
    assert setup[1].work.get(setup[2]['id'])['state'] == 'pending'


def test_task_changes_after_paused_create_do_not_resume(setup, monkeypatch):
    operation = prepare(setup)
    host = Host()
    original = NativeWorkStore._command_dispatch
    def change(self, native_ctx, request, *args):
        result = original(self, native_ctx, request, *args)
        if request['action'] == 'create':
            setup[0].update('tasks', setup[3]['id'], {'version':1, 'title':'Changed after create'})
        return result
    monkeypatch.setattr(NativeWorkStore, '_command_dispatch', change)
    result = execute(setup, operation, host)
    assert [c[0]['action'] for c in host.calls] == ['create']
    assert result['result']['state'] == 'bound_paused'
    assert host.jobs['job-1']['enabled'] is False


def test_source_changes_after_paused_create_do_not_resume(setup):
    operation = prepare(setup)
    host, ctx = Host(), context()
    host.after = lambda args, result: setattr(ctx['source'], 'chat_id', 'changed-source') if args['action'] == 'create' else None
    result = setup[1].execute(host, operation['id'], **ctx)
    assert result['state'] == 'stale'
    assert [c[0]['action'] for c in host.calls] == ['create']
    assert result['result']['state'] == 'bound_paused'


def test_unknown_create_never_retries_or_replaces(setup):
    operation = prepare(setup)
    host = Host()
    def lose(args, result):
        if args['action'] == 'create': raise TimeoutError('Synthetic lost create response')
    host.after = lose
    result = execute(setup, operation, host)
    assert result['state'] == 'unknown' and len(host.jobs) == 1
    assert execute(setup, operation, host) == result
    assert len(host.calls) == 1
    with pytest.raises(CRMError): prepare(setup, idempotency_key='replacement', expected_assignment_version=result['result']['version'])


def test_check_is_observation_only_cancel_pauses_exact_job(setup):
    host = Host()
    scheduled = execute(setup, prepare(setup), host)['result']
    check = prepare(setup, verb='check', idempotency_key='check', expected_assignment_version=scheduled['version'])
    observed = execute(setup, check, host)
    assert host.calls[-1][0] == {'action':'list', 'include_disabled':True}
    assert observed['state'] == 'finished'
    cancel = prepare(setup, verb='cancel', idempotency_key='cancel', expected_assignment_version=observed['result']['version'])
    cancelled = execute(setup, cancel, host)
    assert cancelled['state'] == 'finished' and cancelled['result']['state'] == 'cancelled'
    assert [c[0]['action'] for c in host.calls][-2:] == ['list', 'pause']
    assert host.calls[-1][0]['job_id'] == scheduled['job_id']
    assert setup[0].get('tasks', setup[3]['id'])['status'] == 'open'


def test_check_pending_does_not_dispatch_any_host_tool(setup):
    operation = prepare(setup, verb='check')
    host = Host()
    result = execute(setup, operation, host)
    assert result['state'] == 'finished' and result['result']['state'] == 'pending'
    assert host.calls == []


def test_history_pagination_and_scope(setup):
    first = prepare(setup)
    setup[1].withdraw(first['id'])
    second = prepare(setup, idempotency_key='second')
    page = setup[1].page(task_id=setup[3]['id'], limit=1)
    assert page['total'] == 2 and page['items'][0]['id'] == second['id']
    assert setup[1].page(task_id=setup[3]['id'], limit=1, offset=1)['items'][0]['id'] == first['id']
    assert setup[1].page(task_id='unknown')['total'] == 0


@pytest.mark.parametrize('state', ['dispatching', 'unknown', 'finished', 'expired', 'stale'])
def test_withdraw_refuses_after_claim_and_never_releases_slot(setup, state):
    operation = prepare(setup)
    with setup[0].engine.begin() as conn:
        conn.execute(update(operations).where(operations.c.id == operation['id']).values(state=state))
    with pytest.raises(CRMError, match='cannot undo or interrupt'): setup[1].withdraw(operation['id'])
    assert setup[1].get(operation['id'])['mutation_slot_held'] is True


def test_withdraw_race_with_delayed_command_has_only_one_winner(setup):
    operation = prepare(setup)
    host = Host()
    def withdrawal():
        try: return setup[1].withdraw(operation['id'])['state']
        except CRMError as exc:
            assert exc.status == 409
            return 'claimed'
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(execute, setup, operation, host)
        b = pool.submit(withdrawal)
        result, withdrawn = a.result(), b.result()
    if withdrawn == 'withdrawn':
        assert result['state'] == 'withdrawn' and host.calls == []
    else:
        assert result['state'] == 'finished' and len(host.calls) == 2


def test_returned_unknown_releases_only_non_pending_slot(setup):
    operation = prepare(setup)
    host = Host()
    host.after = lambda args, result: (_ for _ in ()).throw(TimeoutError()) if args['action'] == 'create' else None
    result = execute(setup, operation, host)
    assert result['state'] == 'unknown' and result['mutation_slot_held'] is False
    assert result['result']['state'] != 'pending'
    cancellation = prepare(setup, verb='cancel', idempotency_key='cancel-unknown', expected_assignment_version=result['result']['version'])
    assert cancellation['snapshot']['assignment']['job_id'] is None


def test_unknown_pending_and_crashed_dispatching_cannot_release_or_retry(setup):
    operation = prepare(setup)
    setup[1]._settle(operation['id'], 'unknown', 'synthetic_before_claim_failure')
    result = setup[1].get(operation['id'])
    assert result['mutation_slot_held'] is True
    with pytest.raises(CRMError, match='unresolved'): prepare(setup, idempotency_key='replacement')
    with pytest.raises(CRMError, match='cannot undo'): setup[1].withdraw(operation['id'])
    with setup[0].engine.begin() as conn:
        conn.execute(update(operations).where(operations.c.id == operation['id']).values(state='dispatching', expires_at='2000-01-01T00:00:00+00:00'))
    assert setup[1].get(operation['id'])['mutation_slot_held'] is True
    host = Host()
    assert execute(setup, operation, host)['state'] == 'dispatching' and host.calls == []


def test_expiry_between_claim_and_create_has_no_effect(setup, monkeypatch):
    operation = prepare(setup)
    original = NativeWorkStore._command_dispatch
    def expire(self, native_ctx, request, *args):
        with setup[0].engine.begin() as conn:
            conn.execute(update(operations).where(operations.c.id == operation['id']).values(expires_at='2000-01-01T00:00:00+00:00'))
        return original(self, native_ctx, request, *args)
    monkeypatch.setattr(NativeWorkStore, '_command_dispatch', expire)
    host = Host()
    result = execute(setup, operation, host)
    assert result['state'] == 'expired' and host.calls == []
    assert setup[1].work.get(setup[2]['id'])['state'] == 'pending'


def test_expiry_after_paused_create_preserves_exact_job_without_resume(setup, monkeypatch):
    operation = prepare(setup)
    original = NativeWorkStore._command_dispatch
    def expire(self, native_ctx, request, *args):
        result = original(self, native_ctx, request, *args)
        if request['action'] == 'create':
            with setup[0].engine.begin() as conn:
                conn.execute(update(operations).where(operations.c.id == operation['id']).values(expires_at='2000-01-01T00:00:00+00:00'))
        return result
    monkeypatch.setattr(NativeWorkStore, '_command_dispatch', expire)
    host = Host()
    result = execute(setup, operation, host)
    assert result['state'] == 'expired' and [c[0]['action'] for c in host.calls] == ['create']
    assert result['result']['job_id'] == 'job-1' and result['result']['state'] == 'bound_paused'


def test_cancel_source_change_after_list_never_pauses(setup):
    host, ctx = Host(), context()
    scheduled = execute(setup, prepare(setup), host)['result']
    cancellation = prepare(setup, verb='cancel', idempotency_key='cancel', expected_assignment_version=scheduled['version'])
    host.after = lambda args, result: setattr(ctx['source'], 'chat_id', 'changed') if args['action'] == 'list' else None
    result = setup[1].execute(host, cancellation['id'], **ctx)
    assert result['state'] == 'stale'
    assert host.calls[-1][0]['action'] == 'list'
    assert result['result']['state'] == 'cancelled'
    assert host.jobs['job-1']['enabled'] is True



def test_distinct_check_and_schedule_claims_revalidate_same_review(setup):
    scheduling = prepare(setup)
    check = prepare(setup, verb='check', idempotency_key='independent-observation')
    host = Host()
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(execute, setup, scheduling, host)
        b = pool.submit(execute, setup, check, host)
        schedule_result, observed = a.result(), b.result()
    assert schedule_result['state'] == 'finished'
    assert observed['state'] in {'finished', 'stale'}
    assert [c[0]['action'] for c in host.calls].count('create') == 1
    assert [c[0]['action'] for c in host.calls].count('resume') == 1
    assert not any(c[0]['action'] == 'pause' for c in host.calls)


def test_stale_cancel_claim_cannot_invalidate_new_version(setup):
    host = Host()
    scheduled = execute(setup, prepare(setup), host)['result']
    cancellation = prepare(setup, verb='cancel', idempotency_key='cancel-stale', expected_assignment_version=scheduled['version'])
    newer = NativeWorkStore(setup[0]).reconcile(host, scheduled['id'])
    count = len(host.calls)
    result = execute(setup, cancellation, host)
    assert result['state'] == 'stale' and len(host.calls) == count
    assert NativeWorkStore(setup[0]).get(scheduled['id'])['generation'] == newer['generation']


def test_cancel_claim_and_assignment_invalidation_roll_back_together(setup):
    crm, store, assignment, _ = setup
    operation = prepare(setup, verb='cancel')
    host, ctx = Host(), context()
    guard = _CommandGuard(store, operation['id'], host, ctx['source'], ctx['session_id'], ctx['session_key'], ctx['platform'], store._source_identity(host, **ctx))
    def fail(conn, cursor, statement, params, context, many):
        if statement.startswith('INSERT INTO') and 'crm_native_work_events' in statement:
            raise RuntimeError('synthetic invalidation rollback')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError, match='synthetic invalidation rollback'):
            store.work.cancel(host, assignment['id'], version=1, _operation_guard=guard)
    finally: event.remove(crm.engine, 'before_cursor_execute', fail)
    assert store.get(operation['id'])['state'] == 'prepared'
    assert store.work.get(assignment['id'])['state'] == 'pending'
    assert store.work.get(assignment['id'])['generation'] == 1
    assert host.calls == []



def test_reviewed_bound_job_id_change_before_claim_rejected(setup):
    host = Host()
    scheduled = execute(setup, prepare(setup), host)['result']
    cancellation = prepare(setup, verb='cancel', idempotency_key='cancel-job-change', expected_assignment_version=scheduled['version'])
    # Even an unsupported out-of-band change without a version increment must
    # not cause cancellation of a different job than the reviewed ID.
    with setup[0].engine.begin() as conn:
        conn.execute(update(assignments).where(assignments.c.id == scheduled['id']).values(job_id='different-job'))
    count = len(host.calls)
    assert execute(setup, cancellation, host)['state'] == 'stale'
    assert len(host.calls) == count


def test_unknown_resume_records_uncertainty_without_retry(setup):
    operation = prepare(setup)
    host = Host()
    def lose(args, result):
        if args['action'] == 'resume': raise TimeoutError('Synthetic lost resume response')
    host.after = lose
    result = execute(setup, operation, host)
    assert result['state'] == 'unknown' and result['result']['state'] == 'unknown'
    assert result['mutation_slot_held'] is False and host.jobs['job-1']['enabled'] is True
    assert execute(setup, operation, host) == result
    assert [c[0]['action'] for c in host.calls] == ['create', 'resume']


def test_unknown_pause_records_uncertainty_without_retry(setup):
    host = Host()
    scheduled = execute(setup, prepare(setup), host)['result']
    operation = prepare(setup, verb='cancel', idempotency_key='cancel-lost-pause', expected_assignment_version=scheduled['version'])
    def lose(args, result):
        if args['action'] == 'pause': raise TimeoutError('Synthetic lost pause response')
    host.after = lose
    result = execute(setup, operation, host)
    assert result['state'] == 'unknown' and result['result']['state'] == 'cancelled'
    assert result['mutation_slot_held'] is False
    assert execute(setup, operation, host) == result
    assert [c[0]['action'] for c in host.calls].count('pause') == 1


def test_concurrent_distinct_mutation_preparations_have_one_slot(setup):
    def create(key):
        try: return prepare(setup, idempotency_key=key)
        except CRMError as exc:
            assert exc.status == 409 and 'unresolved' in exc.message
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(create, ['one', 'two', 'three', 'four']))
    assert sum(r is not None for r in results) == 1
    with setup[0].engine.connect() as conn: assert len(conn.execute(select(operations)).all()) == 1


def test_concurrent_prepare_and_command_settlement_do_not_release_dispatch_blocker(setup):
    operation = prepare(setup)
    host = Host()
    def another():
        try: return prepare(setup, verb='cancel', idempotency_key='competing-mutation')
        except CRMError as exc:
            assert exc.status == 409
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(execute, setup, operation, host)
        b = pool.submit(another)
        finished, competing = a.result(timeout=10), b.result(timeout=10)
    assert finished['state'] == 'finished' and competing is None
    assert [c[0]['action'] for c in host.calls] == ['create', 'resume']



def _clock_crosses_deadline(monkeypatch):
    import hermes_crm.native_work_operations as module
    from datetime import timedelta
    original = module.datetime
    advanced = {'value':False}
    class Clock(original):
        @classmethod
        def now(cls, tz=None):
            return original.now(tz) + timedelta(seconds=600 if advanced['value'] else 0)
    monkeypatch.setattr(module, 'datetime', Clock)
    return advanced


@pytest.mark.parametrize('verb', ['schedule', 'cancel', 'check'])
def test_deadline_crossing_assignment_claim_lock_prevents_all_local_effects(setup, monkeypatch, verb):
    operation = prepare(setup, verb=verb)
    clock = _clock_crosses_deadline(monkeypatch)
    def wait_for_lock(conn, cursor, statement, params, context, many):
        if statement.startswith('UPDATE') and 'crm_native_assignments' in statement and 'SET version=' in statement:
            clock['value'] = True  # controlled clock crossing while assignment lock is acquired
    event.listen(setup[0].engine, 'after_cursor_execute', wait_for_lock)
    host = Host()
    try: result = execute(setup, operation, host)
    finally: event.remove(setup[0].engine, 'after_cursor_execute', wait_for_lock)
    assert result['state'] == 'expired' and host.calls == []
    current = NativeWorkStore(setup[0]).get(setup[2]['id'])
    assert current['state'] == 'pending' and current['generation'] == 1 and current['version'] == 1


def test_deadline_crossing_create_dispatch_lock_never_reaches_host(setup, monkeypatch):
    operation = prepare(setup)
    clock = _clock_crosses_deadline(monkeypatch)
    count = {'locks':0}
    def wait_for_lock(conn, cursor, statement, params, context, many):
        if statement.startswith('UPDATE') and 'crm_native_assignments' in statement and 'SET version=' in statement and 'reason=' not in statement and 'state=' not in statement:
            count['locks'] += 1
            if count['locks'] == 2: clock['value'] = True  # after claim, at pre-create lock
    event.listen(setup[0].engine, 'after_cursor_execute', wait_for_lock)
    host = Host()
    try: result = execute(setup, operation, host)
    finally: event.remove(setup[0].engine, 'after_cursor_execute', wait_for_lock)
    assert result['state'] == 'expired' and host.calls == []
    assert NativeWorkStore(setup[0]).get(setup[2]['id'])['state'] == 'pending'


def test_deadline_crossing_final_resume_lock_leaves_bound_job_paused(setup, monkeypatch):
    operation = prepare(setup)
    clock = _clock_crosses_deadline(monkeypatch)
    original = NativeWorkStore._change
    def acquire(self, conn, row, **values):
        original(self, conn, row, **values)
        if values == {'reason':'resume_outcome_pending'}:
            clock['value'] = True  # after the final assignment lock, before resume
    monkeypatch.setattr(NativeWorkStore, '_change', acquire)
    host = Host()
    result = execute(setup, operation, host)
    assert result['state'] == 'expired'
    assert [c[0]['action'] for c in host.calls] == ['create']
    assert result['result']['state'] == 'bound_paused' and host.jobs['job-1']['enabled'] is False
