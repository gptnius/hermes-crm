"""Bounded factual dashboard tasks and saved-work summaries, with no scheduler."""
import hashlib
import json

from fastapi.testclient import TestClient
from sqlalchemy import event, inspect, select

from hermes_crm.agent_read_policy import project_agent_result
from hermes_crm.domain import settings, tasks
from hermes_crm.native_work import NativeWorkStore, assignments, events
from hermes_crm.upcoming_tasks import add_assignment_summaries
from hermes_crm.web import create_app
from test_activity_navigation import crm  # SQLite and optional disposable PostgreSQL.
from test_native_api import native


def task(crm, index=0, **values):
    return crm.create('tasks', dict(title=f'Task {index}', due_at=f'2000-01-{index+1:02d}T12:00:00Z',
                                    notes='PRIVATE TASK NOTE', **values))


def saved(crm, task, key='work', owner='Human owner'):
    return NativeWorkStore(crm).create(task_id=task['id'], human_owner=owner,
        prompt='PRIVATE INSTRUCTIONS', success_criteria='PRIVATE SUCCESS CRITERIA',
        run_at='2099-01-01T00:00:00Z', idempotency_key=key)


def overview(crm):
    return crm.overview(include_task_assignments=True)


def test_linked_contacts_and_six_open_tasks_without_private_values(crm):
    contact = crm.create('contacts', dict(name='Linked <Contact>', notes='PRIVATE CONTACT NOTE'))
    deal = crm.create('deals', dict(title='Deal', contact_id=contact['id']))
    direct = task(crm, 0, contact_id=contact['id'])
    indirect = task(crm, 1, deal_id=deal['id'])
    both = task(crm, 2, contact_id=contact['id'], deal_id=deal['id'])
    for i in range(3, 8): task(crm, i)
    task(crm, 9, status='done')
    before = set(inspect(crm.engine).get_table_names())
    result = overview(crm)
    assert result['open_tasks'] == 8 and result['overdue_tasks'] == 8
    assert len(result['tasks']) == 6
    rows = {r['id']: r for r in result['tasks']}
    for t in (direct, indirect, both):
        assert rows[t['id']]['contact_name'] == contact['name']
        assert rows[t['id']]['linked_contact_id'] == contact['id']
    assert all(r['agent_work'] == dict(status='available', total=0, items=[]) for r in rows.values())
    assert 'PRIVATE' not in str(result['tasks'])
    assert all('notes' not in r and 'custom_fields' not in r for r in rows.values())
    assert set(inspect(crm.engine).get_table_names()) == before
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings).where(settings.c.key == 'workspace_id')).first() is None
    web = TestClient(create_app(crm)).get('/api/overview').json()
    assert web['tasks'] == result['tasks']


def test_no_inferred_agent_from_reminder_and_saved_pending_is_not_scheduled(crm):
    t = task(crm)
    with crm.engine.begin() as conn:
        conn.execute(tasks.update().where(tasks.c.id == t['id']).values(
            schedule_status='scheduled', scheduler_job_id='reminder-only'))
    assert overview(crm)['tasks'][0]['agent_work']['total'] == 0
    work = saved(crm, t, owner='Actual human owner')
    summary = overview(crm)['tasks'][0]['agent_work']
    assert summary == dict(status='available', total=1, items=[dict(id=work['id'],
        human_owner='Actual human owner', executor='Hermes', state='pending', source_task_current=True)])
    assert 'PRIVATE' not in str(summary) and 'prompt' not in str(summary)
    projected = project_agent_result('crm_overview', overview(crm))
    assert 'agent_work' not in projected['tasks'][0] and 'Actual human owner' not in str(projected)
    calls = []
    def capture(conn, cursor, statement, params, context, many): calls.append(statement)
    event.listen(crm.engine, 'before_cursor_execute', capture)
    try: assert 'agent_work' not in crm.overview()['tasks'][0]
    finally: event.remove(crm.engine, 'before_cursor_execute', capture)
    assert not any('crm_native_' in sql for sql in calls), 'Base agent overview must not read assignments'


def test_multiple_terminal_unknown_stale_and_exact_overflow_are_separate(crm):
    t = task(crm)
    works = [saved(crm, t, key=f'work-{i}', owner=f'Owner {i}') for i in range(5)]
    with crm.engine.begin() as conn:
        for i, work in enumerate(works):
            conn.execute(assignments.update().where(assignments.c.id == work['id']).values(
                created_at=f'2026-01-0{i+1}T00:00:00Z', state=['scheduled', 'result_reported', 'cancelled', 'unknown', 'pending'][i]))
        conn.execute(tasks.update().where(tasks.c.id == t['id']).values(version=t['version'] + 1))
    summary = overview(crm)['tasks'][0]['agent_work']
    assert summary['total'] == 5 and len(summary['items']) == 3
    assert [r['state'] for r in summary['items']] == ['pending', 'unknown', 'cancelled']
    assert all(r['source_task_current'] is False for r in summary['items'])
    # A lone terminal record is retained as history, not promoted to current intent.
    for terminal in ['cancelled', 'superseded', 'result_reported']:
        with crm.engine.begin() as conn:
            conn.execute(assignments.update().where(assignments.c.id == works[-1]['id']).values(state=terminal))
        assert overview(crm)['tasks'][0]['agent_work']['items'][0]['state'] == terminal


def test_unknown_schema_and_corrupt_intent_are_unavailable_not_unassigned(crm):
    t = task(crm)
    work = saved(crm, t)
    with crm.engine.begin() as conn:
        conn.execute(assignments.update().where(assignments.c.id == work['id']).values(payload='invalid json'))
    assert overview(crm)['tasks'][0]['agent_work'] == dict(status='unavailable', total=None, items=[])
    with crm.engine.begin() as conn:
        payload = dict(work['payload'], profile='other-profile')
        raw = json.dumps(payload)
        conn.execute(assignments.update().where(assignments.c.id == work['id']).values(
            payload=raw, digest=hashlib.sha256(raw.encode()).hexdigest()))
    assert overview(crm)['tasks'][0]['agent_work']['status'] == 'unavailable'
    # A schema read failure must not be rewritten as zero assignments.
    from hermes_crm import upcoming_tasks
    from hermes_crm.domain import CRMError
    original = upcoming_tasks.NativeWorkStore
    try:
        upcoming_tasks.NativeWorkStore = lambda *a, **k: (_ for _ in ()).throw(CRMError('Incompatible schema', 503))
        assert overview(crm)['tasks'][0]['agent_work']['status'] == 'unavailable'
    finally: upcoming_tasks.NativeWorkStore = original
    with crm.engine.begin() as conn:
        events.drop(conn)
    assert overview(crm)['tasks'][0]['agent_work']['status'] == 'unavailable'


def test_projection_uses_supplied_snapshot_and_scopes_only_six_task_ids(crm, monkeypatch):
    first = task(crm)
    saved(crm, first)
    others = [task(crm, i) for i in range(1, 8)]
    outside = saved(crm, others[-1], key='outside')
    with crm.engine.begin() as conn:
        conn.execute(assignments.update().where(assignments.c.id == outside['id']).values(payload='corrupt outside six'))
    rows = overview(crm)['tasks']
    assert len(rows) == 6 and all(r['agent_work']['status'] == 'available' for r in rows)
    with crm.engine.begin() as conn:
        conn.execute(tasks.update().where(tasks.c.id == first['id']).values(version=2))
        current = [dict(rows[0], version=2)]
        monkeypatch.setattr(crm, 'workspace_token', lambda: (_ for _ in ()).throw(AssertionError('No bootstrap')))
        add_assignment_summaries(crm, conn, current)
        assert current[0]['agent_work']['items'][0]['source_task_current'] is False
    with crm.engine.begin() as conn:
        conn.execute(assignments.update().values(profile='different-profile'))
    assert overview(crm)['tasks'][0]['agent_work']['total'] == 0
    with crm.engine.begin() as conn:
        conn.execute(assignments.update().values(profile=crm.profile, workspace='different-workspace'))
    assert overview(crm)['tasks'][0]['agent_work']['total'] == 0


def test_native_snapshot_and_detail_keep_workspace_guards(native):
    client, state, factory = native
    prefix = '/api/plugins/hermes-crm'
    instance = factory()
    try:
        t = task(instance)
        saved(instance, t)
    finally: instance.close()
    snapshot = client.get(prefix + '/snapshot').json()
    assert snapshot['overview']['tasks'][0]['agent_work']['items'][0]['executor'] == 'Hermes'
    token = snapshot['meta']['workspace_token']
    result = client.get(f'{prefix}/tasks/{t["id"]}', params={'workspace_token': token})
    assert result.json()['notes'] == 'PRIVATE TASK NOTE'
    state['profile'] = 'beta'
    assert client.get(f'{prefix}/tasks/{t["id"]}', params={'workspace_token': token}).status_code == 409
    assert client.get(prefix + '/snapshot').json()['overview']['tasks'] == []
