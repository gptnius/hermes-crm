"""Current-record navigation for audit rows, on isolated SQLite/PostgreSQL fixtures."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import DropSchema

from hermes_crm.agent_read_policy import project_agent_result
from hermes_crm.domain import CRM, activity, contacts, deals, tasks


@pytest.fixture(params=['sqlite', 'postgres'])
def crm(request):
    url = 'sqlite:///:memory:' if request.param == 'sqlite' else os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Requires explicit disposable PostgreSQL URL')
    schema = 'crm_activity_' + uuid.uuid4().hex if request.param == 'postgres' else None
    instance = CRM(url, **({'schema': schema} if schema else {}))
    try:
        yield instance
    finally:
        instance.close()
        if schema:
            engine = create_engine(url)
            try:
                with engine.begin() as conn:
                    conn.execute(DropSchema(schema, cascade=True))
            finally:
                engine.dispose()


def contact(crm, name='Current contact'):
    return crm.create('contacts', dict(name=name, notes='PRIVATE CONTACT NOTE'))


def deal(crm, c):
    return crm.create('deals', dict(title='Deal', contact_id=c['id'], notes='PRIVATE DEAL NOTE'))


def task(crm, **links):
    return crm.create('tasks', dict(title='Task', due_at='2030-01-01T00:00:00Z', notes='PRIVATE TASK NOTE', **links))


def assert_link(row, c):
    assert row['linked_contact_id'] == c['id']
    assert row['linked_contact_name'] == c['name']
    assert row['link_basis'] == 'current_relationship'


def assert_unlinked(row):
    assert row['linked_contact_id'] is None
    assert row['linked_contact_name'] is None
    assert row['link_basis'] is None


def test_navigation_all_record_relationships_without_private_values(crm):
    c = contact(crm)
    d = deal(crm, c)
    direct = task(crm, contact_id=c['id'])
    via_deal = task(crm, deal_id=d['id'])
    both = task(crm, contact_id=c['id'], deal_id=d['id'])
    unlinked = task(crm)
    rows = crm.activities()
    assert len(rows) == 6
    by_entity = {row['entity_id']: row for row in rows}
    for record in [c, d, direct, via_deal, both]:
        assert_link(by_entity[record['id']], c)
    assert_unlinked(by_entity[unlinked['id']])
    assert 'PRIVATE' not in str(rows)
    assert set(rows[0]) == {'id', 'entity_type', 'entity_id', 'action', 'actor', 'summary',
                            'created_at', 'linked_contact_id', 'linked_contact_name', 'link_basis'}
    assert 'activity' not in project_agent_result('crm_overview', crm.overview())


def test_current_relationship_and_name_not_historical_attribution(crm):
    old, current = contact(crm, 'Former'), contact(crm, 'Current')
    d = deal(crm, old)
    t = task(crm, deal_id=d['id'])
    before = {row['id']: row for row in crm.activities([d['id'], t['id']])}
    with crm.engine.begin() as conn:
        conn.execute(deals.update().where(deals.c.id == d['id']).values(contact_id=current['id']))
        conn.execute(contacts.update().where(contacts.c.id == current['id']).values(name='Renamed'))
    for row in crm.activities([d['id'], t['id']]):
        assert_link(row, dict(current, name='Renamed'))
        for field in ('entity_id', 'entity_type', 'summary', 'action', 'actor', 'created_at'):
            assert row[field] == before[row['id']][field]


def test_deleted_missing_unknown_and_nonrecord_events_do_not_link(crm):
    c = contact(crm)
    d = deal(crm, c)
    t = task(crm, deal_id=d['id'])
    with crm.engine.begin() as conn:
        # Only synthetic fixture data is deleted; the audit rows deliberately survive.
        conn.execute(tasks.delete().where(tasks.c.id == t['id']))
        conn.execute(deals.delete().where(deals.c.id == d['id']))
        conn.execute(contacts.delete().where(contacts.c.id == c['id']))
        for kind, record_id in [('unknown', c['id']), ('settings', c['id']), ('contacts', 'missing')]:
            conn.execute(activity.insert().values(id=str(uuid.uuid4()), entity_type=kind,
                entity_id=record_id, action='changed', actor='test', summary='Synthetic', created_at='2030'))
    for row in crm.activities():
        assert_unlinked(row)
    existing = contact(crm)
    with crm.engine.begin() as conn:
        conn.execute(activity.insert().values(id=str(uuid.uuid4()), entity_type='unknown',
            entity_id=existing['id'], action='changed', actor='test', summary='Synthetic', created_at='2031'))
    assert_unlinked(crm.activities()[0])


def test_direct_task_contact_takes_precedence_without_invented_fallback(crm):
    direct, via = contact(crm, 'Direct'), contact(crm, 'Deal contact')
    d = deal(crm, via)
    t = task(crm, contact_id=direct['id'])
    with crm.engine.begin() as conn:
        # Legacy inconsistent relationship: direct target still wins, not a guess.
        conn.execute(tasks.update().where(tasks.c.id == t['id']).values(deal_id=d['id']))
    assert_link(crm.activities([t['id']])[0], direct)


def test_single_bounded_query_same_supplied_transaction_and_portable_sql(crm, monkeypatch):
    c = contact(crm)
    d = deal(crm, c)
    calls = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        calls.append((statement, context.compiled))
    with crm.engine.begin() as conn:
        conn.execute(contacts.update().where(contacts.c.id == c['id']).values(name='Uncommitted name'))
        monkeypatch.setattr(crm, '_read_connection', lambda: pytest.fail('Must use supplied connection'))
        event.listen(crm.engine, 'before_cursor_execute', capture)
        try:
            rows = crm.activities([d['id']], _conn=conn)
        finally:
            event.remove(crm.engine, 'before_cursor_execute', capture)
        assert_link(rows[0], dict(c, name='Uncommitted name'))
    assert len(calls) == 1
    statement, compiled = calls[0]
    assert 'notes' not in statement and 'custom' not in statement
    for dialect in [sqlite.dialect(), postgresql.dialect()]:
        sql = str(compiled.statement.compile(dialect=dialect))
        assert 'LIMIT' in sql and 'LEFT OUTER JOIN' in sql


def test_stable_ties_limit_filters_and_injection_safe_ids(crm):
    c = contact(crm)
    with crm.engine.begin() as conn:
        conn.execute(activity.delete())
        conn.execute(activity.insert(), [dict(id=f'{i:036d}', entity_type='contacts', entity_id=c['id'],
            action='changed', actor='test', summary=f'Event {i}', created_at='2030') for i in range(105)])
    rows = crm.activities()
    assert [r['id'] for r in rows] == [f'{i:036d}' for i in range(104, 4, -1)]
    assert len({r['id'] for r in rows}) == 100
    assert crm.activities([]) == []
    assert crm.activities(["' OR 1=1 --"]) == []
    assert len(crm.activities([c['id'], "' OR 1=1 --"])) == 100


def test_link_target_resolves_beyond_capped_parent_lists(crm):
    target = contact(crm, 'Old target outside loaded list')
    with crm.engine.begin() as conn:
        conn.execute(contacts.update().where(contacts.c.id == target['id']).values(created_at='1900'))
        conn.execute(contacts.insert(), [dict(id=str(uuid.uuid4()), version=1, created_at='2099', updated_at='2099',
            name=f'Other {i}', email='', company='', title='', lifecycle='lead', notes='') for i in range(501)])
    d = deal(crm, target)
    assert len(crm.list('contacts')) == 500
    assert target['id'] not in {c['id'] for c in crm.list('contacts')}
    assert_link(crm.activities([d['id']])[0], target)


def test_legacy_dangling_relationships_fail_closed_in_synthetic_sqlite():
    # Foreign keys prevent these states in normal writes. Simulate an old/corrupt
    # import only in a fresh in-memory fixture, never an application database.
    crm = CRM('sqlite:///:memory:')
    try:
        c = contact(crm)
        d = deal(crm, c)
        direct = task(crm, contact_id=c['id'], deal_id=d['id'])
        missing_deal = task(crm, deal_id=d['id'])
        dangling_deal = deal(crm, c)
        with crm.engine.connect() as conn:
            conn.exec_driver_sql('PRAGMA foreign_keys=OFF')
            conn.commit()
            try:
                conn.execute(tasks.update().where(tasks.c.id == direct['id']).values(contact_id='missing'))
                conn.execute(tasks.update().where(tasks.c.id == missing_deal['id']).values(deal_id='missing'))
                conn.execute(deals.update().where(deals.c.id == dangling_deal['id']).values(contact_id='missing'))
                for row in crm.activities([direct['id'], missing_deal['id'], dangling_deal['id']], _conn=conn):
                    assert_unlinked(row)
            finally:
                conn.rollback()
                conn.exec_driver_sql('PRAGMA foreign_keys=ON')
                conn.commit()
    finally:
        crm.close()
