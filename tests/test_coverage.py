"""Synthetic read-only coverage contracts shared with disposable PostgreSQL."""
import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, inspect, select, update

from hermes_crm import coverage
from hermes_crm.coverage import coverage_report
from hermes_crm.domain import CRM, CRMError, contacts, deals, tasks
from hermes_crm.native_work import NativeWorkStore, assignments, events, reports
from test_native_work import setup, create, Host, identity, report


def test_coverage_read_does_not_initialize_assignment_tables(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/read-only.db', profile='synthetic')
    try:
        crm.workspace_token()
        crm.create('tasks', {'title': 'Human follow-up', 'due_at': '2030-01-01T00:00:00Z'})
        before = set(inspect(crm.engine).get_table_names())
        result = coverage_report(crm)
        assert result['total'] == 1
        assert result['items'][0]['assignment'] is None
        assert result['items'][0]['coverage']['agent_intent_saved'] is False
        assert set(inspect(crm.engine).get_table_names()) == before
        assert NativeWorkStore(crm, initialize=False).page()['total'] == 0
        assert set(inspect(crm.engine).get_table_names()) == before
    finally: crm.close()


def test_coverage_missing_contacts_and_direct_deal_dedup(setup):
    crm, store, task = setup
    a = crm.create('contacts', {'name': 'Direct and deal'})
    b = crm.create('contacts', {'name': 'Unassigned lead'})
    c = crm.create('contacts', {'name': 'Done only'})
    d = crm.create('deals', {'title': 'Opportunity', 'contact_id': a['id']})
    linked = crm.create('tasks', {'title': 'Both links', 'contact_id': a['id'], 'deal_id': d['id'],
                                'due_at': '2000-01-01T00:00:00Z'})
    crm.create('tasks', {'title': 'Completed', 'contact_id': c['id'], 'due_at': '2000-01-01T00:00:00Z', 'status': 'done'})
    all_rows = coverage_report(crm)
    assert all_rows['total'] == 4  # Two open tasks, two contact gaps.
    found = [r for r in all_rows['items'] if r['task'] and r['task']['id'] == linked['id']]
    assert len(found) == 1 and found[0]['contacts'] == [{'id': a['id'], 'name': a['name']}]
    assert found[0]['risk_flags'] == ['agent_not_scheduled', 'no_current_assignment', 'overdue']
    gaps = coverage_report(crm, status='missing_next_action')
    assert {r['contacts'][0]['id'] for r in gaps['items']} == {b['id'], c['id']}
    assert all(r['row_kind'] == 'contact' and r['task'] is None for r in gaps['items'])
    assert coverage_report(crm, q='Completed', status='missing_next_action')['total'] == 0
    # Searching hides nonmatching rows, never linked open tasks for gap detection.
    assert coverage_report(crm, q='Direct and deal', status='missing_next_action')['total'] == 0


def test_coverage_all_assignments_keep_risks_and_current_task_coverage(setup):
    crm, store, task = setup
    host = Host()
    pending = create(setup, idempotency_key='pending')
    scheduled = store.schedule(host, create(setup, idempotency_key='scheduled')['id'])
    cancelled = store.schedule(host, create(setup, idempotency_key='cancelled')['id'])
    cancelled = store.cancel(host, cancelled['id'], version=cancelled['version'])
    failed = create(setup, idempotency_key='uncertain')
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
    failed = store.schedule(host, failed['id'])
    calls = len(host.calls)
    result = coverage_report(crm)
    assert result['total'] == 4 and len(host.calls) == calls
    rows = {r['assignment']['id']: r for r in result['items']}
    assert rows[pending['id']]['risk_flags'] == ['intent_not_scheduled']
    assert rows[cancelled['id']]['assignment']['future_schedule_pause_observed'] is True
    assert 'needs_scheduling_review' not in rows[cancelled['id']]['risk_flags']
    assert 'needs_scheduling_review' in rows[failed['id']]['risk_flags']
    assert rows[scheduled['id']]['assignment']['state'] == 'scheduled'
    assert rows[scheduled['id']]['coverage']['current_scheduled_or_reported_count'] == 1
    assert coverage_report(crm, status='agent_not_scheduled')['total'] == 0
    assert coverage_report(crm, status='needs_scheduling_review')['total'] == 1


def test_coverage_completed_task_does_not_hide_future_assignment(setup):
    crm, store, task = setup
    saved = store.schedule(Host(), create(setup)['id'])
    crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
    rows = coverage_report(crm, status='needs_scheduling_review')['items']
    assert len(rows) == 1 and rows[0]['task']['status'] == 'done'
    assert rows[0]['assignment']['id'] == saved['id']
    assert rows[0]['assignment']['source_task_current'] is False
    assert rows[0]['assignment']['business_task_completed'] is True
    assert rows[0]['assignment']['business_task_completed_by_report'] is False
    assert rows[0]['assignment']['latest_report'] is None


def test_coverage_stale_source_has_task_gap_and_does_not_claim_newer_version_covered(setup):
    crm, store, task = setup
    store.schedule(Host(), create(setup)['id'])
    crm.update('tasks', task['id'], {'version': 1, 'title': 'New reviewed subject'})
    rows = coverage_report(crm)['items']
    assert len(rows) == 2
    assert {r['kind'] for r in rows} == {'unassigned_task', 'assignment'}
    assert coverage_report(crm, status='agent_not_scheduled')['total'] == 1
    assert coverage_report(crm, status='needs_scheduling_review')['total'] == 1


def test_coverage_cancelled_unknown_and_safe_history_are_not_new_sibling_state(setup):
    crm, store, task = setup
    host = Host()
    old = store.schedule(host, create(setup, idempotency_key='old')['id'])
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError())
    old = store.cancel(host, old['id'], version=old['version'])
    host.before = None
    newer = store.schedule(host, create(setup, idempotency_key='new')['id'])
    rows = coverage_report(crm, status='needs_scheduling_review')['items']
    assert len(rows) == 1 and rows[0]['assignment']['id'] == old['id']
    assert 'unverified_pause' in rows[0]['risk_flags']
    assert coverage_report(crm, status='agent_not_scheduled')['total'] == 0
    store.cancel(host, old['id'], version=old['version'])
    assert coverage_report(crm, status='needs_scheduling_review')['total'] == 0
    assert store.get(newer['id'])['state'] == 'scheduled'


def test_coverage_cancelled_unbound_attempt_requires_review_but_never_scheduled_intent_does_not(setup):
    crm, store, _ = setup
    host = Host()
    clean = create(setup, idempotency_key='never-attempted')
    store.cancel(host, clean['id'], version=clean['version'])
    uncertain = create(setup, idempotency_key='lost-create')
    host.after = lambda args, result: (_ for _ in ()).throw(TimeoutError())
    uncertain = store.schedule(host, uncertain['id'])
    assert uncertain['job_id'] is None
    store.cancel(host, uncertain['id'], version=uncertain['version'])
    rows = coverage_report(crm, status='needs_scheduling_review')['items']
    assert len(rows) == 1 and rows[0]['assignment']['id'] == uncertain['id']
    assert 'unverified_pause' in rows[0]['risk_flags']


def test_coverage_observation_age_and_report_host_business_are_separate(setup, monkeypatch):
    crm, store, task = setup
    host = Host()
    a = store.schedule(host, create(setup)['id'])
    host.jobs[a['job_id']].update(state='completed', enabled=False)
    store.reconcile(host, a['id'])
    # Normalize synthetic evidence times so age assertions are exact.
    with crm.engine.begin() as conn:
        conn.execute(update(events).where(events.c.kind == 'job_observed').values(created_at='2026-11-01T00:00:00.000000+00:00'))
        conn.execute(events.insert().values(id=str(uuid.uuid4()), assignment_id=a['id'], version=900,
            kind='job_observed', evidence=json.dumps({'job_id': 'foreign', 'state': 'failed'}),
            created_at='2026-11-02T00:00:00.000000+00:00'))
    monkeypatch.setattr(coverage, 'now', lambda: '2031-01-01T00:00:00.000000+00:00')
    summary = coverage_report(crm, status='run_time_passed')['items'][0]['assignment']
    observed = summary['latest_host_observation']
    assert observed['state'] == 'completed' and observed['job_id'] == a['job_id']
    assert observed['observed_at'] == '2026-11-01T00:00:00.000000+00:00'
    assert observed['age_seconds'] == int((datetime(2031, 1, 1, tzinfo=timezone.utc) - datetime(2026, 11, 1, tzinfo=timezone.utc)).total_seconds())
    assert summary['latest_report'] is None and not summary['host_terminal_success_verified']
    assert not summary['business_task_completed']
    saved = report(setup, identity(host, a), a, outcome='blocked')
    summary = coverage_report(crm, status='reported_blocked_failed')['items'][0]['assignment']
    assert summary['latest_report']['id'] == saved['reports'][0]['id']
    assert summary['latest_report']['identity']['job_id'] == a['job_id']
    assert summary['latest_report']['provenance'] == 'native_run_reported'
    assert coverage_report(crm, status='awaiting_review')['total'] == 1
    assert coverage_report(crm, status='run_time_passed')['total'] == 0
    assert crm.get('tasks', task['id'])['status'] == 'open'


def test_coverage_paused_elapsed_is_not_execution_failure(setup, monkeypatch):
    crm, store, _ = setup
    host = Host()
    host.before = lambda args: (_ for _ in ()).throw(TimeoutError()) if args['action'] == 'resume' else None
    a = store.schedule(host, create(setup)['id'])
    host.before = None
    store.reconcile(host, a['id'])
    monkeypatch.setattr(coverage, 'now', lambda: '2031-01-01T00:00:00.000000+00:00')
    row = coverage_report(crm, status='needs_scheduling_review')['items'][0]
    assert row['assignment']['state'] == 'bound_paused'
    assert {'run_time_elapsed_while_paused', 'run_time_passed'} <= set(row['risk_flags'])
    assert 'reported_blocked_failed' not in row['risk_flags']


def test_coverage_literal_search_and_unknown_filters(setup):
    crm, _, task = setup
    crm.update('tasks', task['id'], {'version': 1, 'title': r'Literal %_\ search'})
    crm.create('tasks', {'title': 'Unrelated noise', 'due_at': task['due_at']})
    for q in ('%', '_', '\\', '%_\\', 'LITERAL'):
        assert coverage_report(crm, q=q)['total'] == 1
    assert coverage_report(crm, q="' OR 1=1 --")['total'] == 0
    for filters in ({'q': None}, {'q': 'x'*201}, {'limit': True}, {'limit': 101}, {'offset': -1},
                    {'offset': 1.0}, {'status': 'healthy'}, {'status': None}):
        with pytest.raises(CRMError): coverage_report(crm, **filters)


def test_coverage_authoritative_pages_beyond_task_and_assignment_caps(setup):
    crm, store, task = setup
    template = create(setup)
    with crm.engine.begin() as conn:
        for i in range(1, 606):
            conn.execute(tasks.insert().values(dict(task, id=f't{i:04}', title=f'Bulk {i}',
                due_at='2000-01-01T00:00:00.000000+00:00' if i == 605 else task['due_at'])))
        raw = dict(conn.execute(select(assignments).where(assignments.c.id == template['id'])).mappings().one())
        for i in range(1, 121):
            payload = json.loads(raw['payload']); payload['task_id'] = f't{i:04}'
            encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
            conn.execute(assignments.insert().values(dict(raw, id=f'a{i:04}', task_id=f't{i:04}',
                idempotency_key=f'bulk-{i}', payload=encoded, digest=hashlib.sha256(encoded.encode()).hexdigest())))
    found = []
    for offset in range(0, 700, 100):
        page = coverage_report(crm, limit=100, offset=offset)
        assert page['total'] == 606 and page['total_unit'] == 'evidence_items'
        found.extend(r['id'] for r in page['items'])
    assert len(found) == len(set(found)) == 606
    assert coverage_report(crm, status='overdue', limit=1)['items'][0]['task']['id'] == 't0605'
    assert coverage_report(crm, q='Bulk 605', limit=1)['total'] == 1
    work_ids = []
    for offset in range(0, 150, 25):
        page = store.page(limit=25, offset=offset)
        assert page['total'] == 121
        work_ids.extend(r['id'] for r in page['items'])
    assert len(work_ids) == len(set(work_ids)) == 121
    assert store.page(task_id='t0120', limit=1)['total'] == 1


def test_coverage_profile_scope_ignores_other_profile_history(setup):
    crm, store, task = setup
    row = create(setup)
    with crm.engine.begin() as conn:
        conn.execute(update(assignments).where(assignments.c.id == row['id']).values(profile='other'))
    result = coverage_report(crm)
    assert result['total'] == 1 and result['items'][0]['assignment'] is None
    assert store.page()['total'] == 0


@pytest.mark.parametrize('corruption', ['digest', 'schema', 'state', 'event'])
def test_coverage_corrupt_evidence_fails_closed(setup, corruption):
    crm, store, _ = setup
    row = create(setup)
    with crm.engine.begin() as conn:
        if corruption == 'digest': conn.execute(update(assignments).values(digest='0'*64))
        elif corruption == 'schema':
            payload = dict(row['payload'], schema_version=999)
            encoded = json.dumps(payload)
            conn.execute(update(assignments).values(payload=encoded, digest=hashlib.sha256(encoded.encode()).hexdigest()))
        elif corruption == 'state': conn.execute(update(assignments).values(state='unrecognized'))
        else: conn.execute(update(events).values(evidence='not-json'))
    with pytest.raises((CRMError, ValueError)): coverage_report(crm)


@pytest.fixture
def fresh_crm(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/fresh-coverage.db', profile='synthetic')
    yield crm
    crm.close()


def _other(crm):
    schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
    return CRM(crm.url, profile=crm.profile, schema=schema)


@pytest.mark.parametrize('report_name', ['coverage', 'history'])
def test_first_use_schema_inspected_inside_read_snapshot(fresh_crm, report_name):
    crm = fresh_crm
    task = crm.create('tasks', {'title': 'Before', 'due_at': '2030-05-01T00:00:00Z'})
    reader = NativeWorkStore(crm, initialize=False)
    assert not reader.available
    other = _other(crm)
    created, triggered = [], []
    def on_begin(conn, cursor, statement, parameters, context, executemany):
        boundary = statement == 'BEGIN' if crm.backend == 'sqlite' else statement == 'SET TRANSACTION READ ONLY'
        if boundary and not triggered:
            triggered.append(True)
            other.update('tasks', task['id'], {'version': 1, 'title': 'After'})
            created.append(create((other, NativeWorkStore(other), task), expected_task_version=2))
    event.listen(crm.engine, 'before_cursor_execute', on_begin)
    try:
        result = coverage_report(crm) if report_name == 'coverage' else reader.page()
        assert triggered and result['total'] == 1
        if report_name == 'coverage':
            assert result['items'][0]['assignment']['id'] == created[0]['id']
            assert result['items'][0]['task']['version'] == 2
        else: assert result['items'][0]['id'] == created[0]['id']
    finally:
        event.remove(crm.engine, 'before_cursor_execute', on_begin)
        other.close()


def test_coverage_task_and_assignment_reads_share_snapshot(setup):
    crm, store, task = setup
    a = create(setup)
    other = _other(crm)
    wrote, finished = threading.Event(), threading.Event()
    failures, threads = [], []
    def writer():
        try:
            with other.engine.begin() as conn:
                conn.execute(update(tasks).where(tasks.c.id == task['id']).values(version=2, status='done'))
                conn.execute(update(assignments).where(assignments.c.id == a['id']).values(
                    version=2, state='cancelled', generation=2))
                wrote.set()
            finished.set()
        except Exception as exc:
            failures.append(exc); wrote.set(); finished.set()
    def after_tasks(conn, cursor, statement, parameters, context, executemany):
        stmt = getattr(context.compiled, 'statement', None)
        if not threads and getattr(stmt, 'is_select', False) and 'crm_tasks' in statement and 'crm_native' not in statement:
            thread = threading.Thread(target=writer)
            threads.append(thread); thread.start()
            assert wrote.wait(5)
            # PG writer can commit during repeatable read. SQLite rollback-mode
            # writer commits only when the explicit read snapshot is released.
            if crm.backend == 'postgres': assert finished.wait(5)
    event.listen(crm.engine, 'after_cursor_execute', after_tasks)
    try:
        result = coverage_report(crm)
        assert len(threads) == 1
        assert result['total'] == 1
        row = result['items'][0]
        assert row['task']['version'] == 1 and row['assignment']['state'] == 'pending'
        assert row['assignment']['source_task_current']
    finally:
        event.remove(crm.engine, 'after_cursor_execute', after_tasks)
        for thread in threads: thread.join(10)
        other.close()
    assert finished.is_set() and not failures
    assert crm.get('tasks', task['id'])['version'] == 2


def test_work_page_count_and_items_share_snapshot(setup):
    crm, store, task = setup
    original = create(setup)
    other = _other(crm)
    other_store = NativeWorkStore(other)
    wrote, finished = threading.Event(), threading.Event()
    failures, threads = [], []
    def after_insert(conn, cursor, statement, parameters, context, executemany):
        stmt = getattr(context.compiled, 'statement', None)
        if getattr(stmt, 'is_insert', False) and stmt.table.name == events.name: wrote.set()
    def writer():
        try: create((other, other_store, task), idempotency_key='concurrent-page')
        except Exception as exc: failures.append(exc)
        finally: finished.set()
    def after_count(conn, cursor, statement, parameters, context, executemany):
        if not threads and 'count(' in statement.lower() and 'crm_native_assignments' in statement:
            thread = threading.Thread(target=writer); threads.append(thread); thread.start()
            assert wrote.wait(5)
            if crm.backend == 'postgres': assert finished.wait(5)
    event.listen(other.engine, 'after_cursor_execute', after_insert)
    event.listen(crm.engine, 'after_cursor_execute', after_count)
    try:
        result = store.page()
        assert result['total'] == 1 and [r['id'] for r in result['items']] == [original['id']]
    finally:
        event.remove(crm.engine, 'after_cursor_execute', after_count)
        event.remove(other.engine, 'after_cursor_execute', after_insert)
        for thread in threads: thread.join(10)
        other.close()
    assert finished.is_set() and not failures
    assert store.page()['total'] == 2
