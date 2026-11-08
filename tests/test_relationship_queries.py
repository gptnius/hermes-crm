"""Relationship query contracts against synthetic SQLite/disposable PostgreSQL."""
import uuid
import pytest
from sqlalchemy import inspect, select
from hermes_crm.domain import CRM, CRMError, contacts, deals, tasks, settings
from hermes_crm.relationship_schema import companies, contact_companies, events, check_schema
from hermes_crm.relationship_queries import RelationshipQueries
from hermes_crm.report_store import scope_for, schema_name
from hermes_crm.report_interactions import InteractionStore

STAMP = '2020-01-01T00:00:00.000000+00:00'

from test_activity_navigation import crm  # SQLite and optional disposable PostgreSQL.


def seed_company(crm, company_id='company-a'):
    crm.workspace_token()
    with crm.engine.begin() as conn:
        check_schema(crm, conn, write=True)
        scope = scope_for(crm, connection=conn)
        conn.execute(companies.insert().values(scope=scope, id=company_id, version=1, created_at=STAMP, updated_at=STAMP, name='Duplicate', domain='same.test', notes='private company note'))
    return scope


def link(crm, scope, contact_id, company_id='company-a'):
    with crm.engine.begin() as conn:
        conn.execute(contact_companies.insert().values(scope=scope, contact_id=contact_id, company_id=company_id, created_at=STAMP, updated_at=STAMP))


def test_absent_reads_do_not_create_schema_or_token(crm):
    c = crm.create('contacts', {'name': 'Legacy', 'company': 'Duplicate'})
    query = RelationshipQueries(crm)
    record = query.project_records('contacts', [c])[0]
    assert record['company_id'] is None and record['company_name'] is None
    assert record['company'] == 'Duplicate'
    assert query.relationship_activities()['total'] == 0
    assert query.record_history('contacts', c['id'])['total'] == 1
    assert 'crm_companies' not in inspect(crm.engine).get_table_names(schema=schema_name(crm))
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar() is None


def test_large_rollups_count_before_pagination_and_alias_expressions(crm):
    scope = seed_company(crm)
    base = dict(version=1, created_at=STAMP, updated_at=STAMP, email='', company='legacy', title='', lifecycle='lead', notes='ordinary private text')
    with crm.engine.begin() as conn:
        conn.execute(contacts.insert(), [dict(base, id=f'c{i:04}', name='Same') for i in range(603)])
        conn.execute(contact_companies.insert(), [dict(scope=scope, contact_id=f'c{i:04}', company_id='company-a', created_at=STAMP, updated_at=STAMP) for i in range(603)])
    query = RelationshipQueries(crm)
    assert query.company_detail('company-a')['counts']['contacts'] == 603
    page = query.company_records('company-a', 'contacts', limit=100, offset=600)
    assert page['total'] == 603 and [r['id'] for r in page['items']] == ['c0600', 'c0601', 'c0602']
    assert all('notes' not in r and r['company_name'] == 'Duplicate' for r in page['items'])
    with crm._read_connection() as conn:
        alias = contacts.alias('report_contacts')
        expressions = query.company_expressions('contacts', alias, conn=conn)
        rows = conn.execute(select(alias.c.id, expressions['company_id'].label('company_id')).where(alias.c.id == 'c0602')).mappings().all()
        assert rows == [{'id': 'c0602', 'company_id': 'company-a'}]
    with pytest.raises(CRMError): query.company_records('company-a', 'contacts', limit=True)


def test_current_company_rollups_and_task_direct_precedence(crm):
    scope = seed_company(crm)
    seed_company(crm, 'company-b')
    a = crm.create('contacts', {'name': 'A'})
    b = crm.create('contacts', {'name': 'B'})
    link(crm, scope, a['id'])
    link(crm, scope, b['id'], 'company-b')
    deal = crm.create('deals', {'title': 'Deal', 'contact_id': a['id']})
    indirect = crm.create('tasks', {'title': 'Indirect', 'deal_id': deal['id'], 'due_at': STAMP})
    direct = crm.create('tasks', {'title': 'Direct', 'contact_id': b['id'], 'due_at': STAMP})
    with crm.engine.begin() as conn:
        # Legacy/imported inconsistent context: direct contact still takes precedence.
        conn.execute(tasks.update().where(tasks.c.id == direct['id']).values(deal_id=deal['id']))
    query = RelationshipQueries(crm)
    assert [r['id'] for r in query.company_records('company-a', 'tasks')['items']] == [indirect['id']]
    assert [r['id'] for r in query.company_records('company-b', 'tasks')['items']] == [direct['id']]
    with crm._read_connection() as conn:
        alias = tasks.alias('report_tasks')
        expr = query.company_expressions('tasks', alias, conn=conn)
        assert conn.execute(select(expr['company_id']).select_from(alias).where(alias.c.id == direct['id'])).scalar_one() == 'company-b'
    with crm.engine.begin() as conn:
        conn.execute(contact_companies.update().where(contact_companies.c.contact_id == a['id']).values(company_id='company-b'))
    assert query.company_detail('company-a')['counts']['deals'] == 0
    assert query.company_detail('company-b')['counts']['tasks'] == 2


def test_completed_event_and_nonvoid_log_feed_and_scope(crm):
    scope = seed_company(crm)
    a = crm.create('contacts', {'name': 'A'})
    link(crm, scope, a['id'])
    log = InteractionStore(crm).create(dict(contact_id=a['id'], happened_at=STAMP, kind='call', summary='private log'), a['version'], 'local', 'log')
    base = dict(scope=scope, version=1, created_at=STAMP, updated_at=STAMP, title='Call', kind='call', timezone='UTC', contact_id=a['id'], company_id='company-a', notes='private note', source='local', outcome_happened_at=STAMP, recorded_at=STAMP, outcome_summary='private outcome', outcome_provenance='self_reported')
    start = 'starts_at' if 'starts_at' in events.c else 'start_at'
    end = 'ends_at' if 'ends_at' in events.c else 'end_at'
    base.update({start: STAMP, end: '2020-01-01T01:00:00.000000+00:00'})
    with crm.engine.begin() as conn:
        conn.execute(events.insert(), [dict(base, id=status, status=status) for status in ('scheduled', 'completed', 'cancelled')])
    query = RelationshipQueries(crm)
    page = query.relationship_activities(company_id='company-a')
    assert page['total'] == 2
    assert {r['source_id'] for r in page['items']} == {'completed', log['id']}
    assert all(r['provenance'] == 'self_reported' for r in page['items'])
    assert 'private' not in str(page)
    InteractionStore(crm).void(log['id'], log['version'], 'Correction', 'local', 'void')
    assert query.relationship_activities()['total'] == 1
    crm.profile = 'another-profile'
    assert query.relationship_activities()['total'] == 0
    assert query.project_records('contacts', [a])[0]['company_id'] is None
    with pytest.raises(CRMError): query.company_detail('company-a')


def test_event_task_membership_deduplicates_and_discloses_distinct_context(crm):
    from hermes_crm.relationship_schema import event_tasks
    scope = seed_company(crm)
    seed_company(crm, 'company-b')
    a = crm.create('contacts', {'name': 'A'})
    b = crm.create('contacts', {'name': 'B'})
    link(crm, scope, a['id'])
    link(crm, scope, b['id'], 'company-b')
    ordinary = crm.create('tasks', {'title': 'Both contexts', 'contact_id': a['id'], 'due_at': STAMP})
    opposite = crm.create('tasks', {'title': 'Distinct contexts', 'contact_id': b['id'], 'due_at': STAMP})
    with crm.engine.begin() as conn:
        conn.execute(events.insert().values(scope=scope, id='event-a', version=1, created_at=STAMP, updated_at=STAMP, title='Event A', kind='call', timezone='UTC', starts_at=STAMP, ends_at='2020-01-01T01:00:00.000000+00:00', contact_id=a['id'], company_id='company-a', notes='private', status='scheduled', source='local'))
        conn.execute(event_tasks.insert(), [dict(scope=scope, task_id=t['id'], event_id='event-a', created_at=STAMP, updated_at=STAMP) for t in (ordinary, opposite)])
    query = RelationshipQueries(crm)
    assert query.event_detail('event-a')['counts'] == {'tasks': 2}
    assert query.event_detail('event-a')['event']['notes'] == 'private'
    from hermes_crm.events import Events
    assert 'notes' not in Events(crm).get('event-a')
    page = query.event_tasks('event-a')
    assert page['total'] == 2 and 'notes' not in str(page)
    assert query.company_detail('company-a')['counts']['tasks'] == 2
    assert query.company_detail('company-b')['counts']['tasks'] == 1
    assert query.contact_tasks(a['id'])['total'] == 2
    assert query.contact_tasks(b['id'])['total'] == 1
    row = next(row for row in page['items'] if row['id'] == opposite['id'])
    assert row['company_id'] == 'company-b' and row['event_company_id'] == 'company-a'
    assert row['event_link_basis'] == 'explicit_event_tasks'
    crm.profile = 'other'
    assert query.contact_tasks(a['id'])['total'] == 1
    assert query.project_records('tasks', [opposite])[0]['event_id'] is None
    with pytest.raises(CRMError): query.event_tasks('event-a')


def test_audit_scope_predicate_filters_before_limit_and_preserves_legacy(crm):
    from hermes_crm.domain import activity
    from hermes_crm.relationship_queries import audit_scope_predicate
    seed_company(crm, 'company-a')
    with crm.engine.begin() as conn:
        conn.execute(companies.insert().values(scope='other-scope', id='company-b', version=1, created_at=STAMP, updated_at=STAMP, name='Other', notes=''))
        rows = [dict(id='legacy', entity_type='contacts', entity_id='legacy-contact', summary='Legacy')]
        rows += [dict(id='mine', entity_type='companies', entity_id='company-a', summary='Mine')]
        rows += [dict(id=f'other-{i:03}', entity_type='companies', entity_id='company-b', summary='Other') for i in range(105)]
        rows += [dict(id='missing', entity_type='events', entity_id='missing-event', summary='Missing')]
        conn.execute(activity.insert(), [dict(row, action='created', actor='local', created_at=STAMP) for row in rows])
    query = RelationshipQueries(crm)
    page = query.record_history(limit=1)
    assert page['total'] == 2
    assert page['items'][0]['id'] == 'legacy'
    with crm._read_connection() as conn:
        ids = conn.execute(select(activity.c.id).where(audit_scope_predicate(crm, conn)).order_by(activity.c.id).limit(100)).scalars().all()
        assert ids == ['legacy', 'mine']
    crm.profile = 'another-profile'
    assert query.record_history()['total'] == 1


def test_audit_scope_absent_and_incompatible_fail_closed(crm):
    from hermes_crm.domain import activity
    from hermes_crm.relationship_queries import audit_scope_predicate
    with crm.engine.begin() as conn:
        conn.execute(activity.insert(), [dict(id=kind, entity_type=kind, entity_id='unknown', action='created', actor='local', summary='Original', created_at=STAMP) for kind in ('contacts', 'companies', 'events')])
    assert RelationshipQueries(crm).record_history()['total'] == 1
    with crm.engine.begin() as conn:
        companies.create(conn)
    with crm._read_connection() as conn, pytest.raises(CRMError) as error:
        audit_scope_predicate(crm, conn)
    assert error.value.status == 503


def test_selectors_filter_before_paging_and_omit_notes(crm):
    base = dict(version=1, created_at=STAMP, updated_at=STAMP, email='', company='legacy', title='', lifecycle='lead', notes='private')
    with crm.engine.begin() as conn:
        conn.execute(contacts.insert(), [dict(base, id=f's{i:04}', name='Needle %_' if i == 602 else 'Same') for i in range(603)])
    query = RelationshipQueries(crm)
    page = query.selectors('contacts', limit=100, offset=600)
    assert page['total'] == 603 and len(page['items']) == 3
    assert 'notes' not in str(page)
    found = query.selectors('contacts', q='%_')
    assert found['total'] == 1 and found['items'][0]['id'] == 's0602'
    assert query.selectors('contacts', q='s0602')['total'] == 1
    assert 'crm_companies' not in inspect(crm.engine).get_table_names(schema=schema_name(crm))
    with pytest.raises(CRMError): query.selectors('bogus')
