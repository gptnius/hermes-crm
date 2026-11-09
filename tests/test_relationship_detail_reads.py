"""Exact ordinary relationship fields through scoped, non-mutating snapshots."""
import uuid

import pytest
from sqlalchemy import inspect, select, update

from hermes_crm.agent_read_policy import read_record_fields
from hermes_crm.companies import CompanyStore
from hermes_crm.domain import CRM, CRMError, activity, idempotency, settings
from hermes_crm.events import EventStore
from hermes_crm.native_work import TOOLSETS
from hermes_crm.relationship_schema import OWNED_TABLES, companies, schema_state
from hermes_crm.report_store import schema_name
from test_native_work_adapters import adapters, LEGACY_READ


@pytest.fixture
def crm():
    instance = CRM('sqlite:///:memory:')
    yield instance
    instance.close()


def seed(crm, kind):
    if kind == 'companies':
        return CompanyStore(crm).create(dict(name='Company', notes='ordinary company note'),
                                        actor='test', key='company')
    return EventStore(crm).create(dict(title='Call', kind='call',
        starts_at='2020-01-01T10:00:00Z', ends_at='2020-01-01T11:00:00Z',
        timezone='UTC', notes='ordinary event note'), actor='test', key='event')


def read(crm, kind, row, fields=None):
    return read_record_fields(crm, kind=kind, id=row['id'], fields=fields or ['notes'])


def snapshot(crm):
    with crm._read_connection() as conn:
        return {table.name: [dict(r) for r in conn.execute(select(table)).mappings()]
                for table in (*OWNED_TABLES, activity, idempotency, settings)}


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_exact_fields_are_read_only_and_current(crm, kind):
    row = seed(crm, kind)
    before = snapshot(crm)
    result = read(crm, kind, row)
    assert result == dict(id=row['id'], version=1, fields={'notes': row['notes']})
    result['fields']['notes'] = 'caller mutation'
    assert snapshot(crm) == before
    store = CompanyStore(crm) if kind == 'companies' else EventStore(crm)
    updated = store.update(row['id'], {'notes': 'current note'}, expected_version=1,
                           actor='test', key='update')
    before = snapshot(crm)
    assert read(crm, kind, row) == dict(id=row['id'], version=updated['version'],
                                      fields={'notes': 'current note'})
    assert snapshot(crm) == before


def test_event_null_completion_and_reopen(crm):
    row = seed(crm, 'events')
    assert read(crm, 'events', row, ['outcome_summary'])['fields'] == {'outcome_summary': None}
    store = EventStore(crm)
    store.complete(row['id'], dict(outcome_happened_at='2020-01-01T11:00:00Z',
        outcome_summary='Self-reported discussion'), expected_version=1, actor='test', key='complete')
    assert read(crm, 'events', row, ['outcome_summary']) == dict(id=row['id'], version=2,
        fields={'outcome_summary': 'Self-reported discussion'})
    store.reopen(row['id'], 'Correct the record', expected_version=2, actor='test', key='reopen')
    assert read(crm, 'events', row, ['notes', 'outcome_summary']) == dict(id=row['id'],
        version=3, fields={'notes': row['notes'], 'outcome_summary': None})


def test_archived_company_notes_remain_readable(crm):
    row = seed(crm, 'companies')
    CompanyStore(crm).archive(row['id'], expected_version=1, actor='test', key='archive')
    assert read(crm, 'companies', row) == dict(id=row['id'], version=2,
                                            fields={'notes': row['notes']})


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_missing_records_and_uninitialized_reads_do_not_write(crm, kind):
    with crm._read_connection() as conn:
        before = inspect(conn).get_table_names(schema=schema_name(crm))
    assert crm.existing_workspace_token() is None
    with pytest.raises(CRMError) as exc:
        read(crm, kind, {'id': str(uuid.uuid4())})
    assert exc.value.status == 404
    assert crm.existing_workspace_token() is None
    with crm._read_connection() as conn:
        assert inspect(conn).get_table_names(schema=schema_name(crm)) == before
    seed(crm, kind)
    before = snapshot(crm)
    with pytest.raises(CRMError) as exc:
        read(crm, kind, {'id': str(uuid.uuid4())})
    assert exc.value.status == 404
    assert snapshot(crm) == before


@pytest.mark.parametrize('kind', ['companies', 'events'])
@pytest.mark.parametrize('fields', [[], ['*'], ['custom.*'], ['custom.known'],
    ['protected_notes'], ['private.notes'], ['notes', 'notes'], ['notes.*'],
    ['notes\n'], ['../notes'], [1], [{}], 'notes', ['notes'] * 21, ['version']])
def test_rejects_non_allowlisted_paths_before_storage(crm, kind, fields, monkeypatch):
    def unexpected():
        pytest.fail('Invalid selection must not open storage')
    monkeypatch.setattr(crm, '_read_connection', unexpected)
    with pytest.raises(CRMError):
        read_record_fields(crm, kind=kind, id='record', fields=fields)


def test_outcome_not_available_for_companies_or_legacy(crm):
    for kind in ('companies', 'contacts', 'deals', 'tasks'):
        with pytest.raises(CRMError):
            read_record_fields(crm, kind=kind, id='record', fields=['outcome_summary'])


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_profile_and_workspace_marker_isolation(crm, kind):
    row = seed(crm, kind)
    original_profile = crm.profile
    crm.profile = 'other-profile'
    with pytest.raises(CRMError) as exc:
        read(crm, kind, row)
    assert exc.value.status == 404
    crm.profile = original_profile
    assert read(crm, kind, row)['fields']['notes'] == row['notes']
    with crm.engine.begin() as conn:
        conn.execute(update(settings).where(settings.c.key == 'workspace_id').values(value=str(uuid.uuid4())))
    with pytest.raises(CRMError) as exc:
        read(crm, kind, row)
    assert exc.value.status == 404


@pytest.mark.parametrize('kind', ['companies', 'events'])
@pytest.mark.parametrize('damage', ['partial', 'version', 'column'])
def test_malformed_relationship_schema_fails_closed(crm, kind, damage):
    if damage == 'partial':
        with crm.engine.begin() as conn:
            companies.create(conn)
        row = {'id': str(uuid.uuid4())}
    else:
        row = seed(crm, kind)
        with crm.engine.begin() as conn:
            if damage == 'version':
                conn.execute(update(schema_state).values(version=999))
            else:
                prefix = (conn.dialect.identifier_preparer.quote(schema_name(crm)) + '.') if schema_name(crm) else ''
                conn.exec_driver_sql(f'ALTER TABLE {prefix}crm_companies ADD COLUMN unexpected TEXT')
    with pytest.raises(CRMError) as exc:
        read(crm, kind, row)
    assert exc.value.status == 503


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_registered_tool_exact_response_scope_and_no_grant_changes(adapters, kind):
    a = adapters
    crm = a.factory()
    try:
        row = seed(crm, kind)
    finally:
        crm.close()
    fields = ['notes', 'outcome_summary'] if kind == 'events' else ['notes']
    args = dict(kind=kind, id=row['id'], fields=fields)
    result = a.ctx.invoke('crm_record_fields', args)
    assert result == dict(ok=True, data=dict(id=row['id'], version=1,
        fields={field: row[field] for field in fields}))
    base = a.ctx.invoke('crm_company_get' if kind == 'companies' else 'crm_event_get',
                        {'record_id': row['id']})
    assert base['ok'] and row['notes'] not in str(base)
    assert a.ctx.tools['crm_record_fields']['toolset'] == 'crm_detail_read'
    assert 'crm_detail_read' not in TOOLSETS
    assert {name for name, tool in a.ctx.tools.items() if tool['toolset'] == 'crm_read'} == LEGACY_READ
    for invalid in (dict(args, fields=['protected_notes']), dict(args, fields=['custom.known']),
                    dict(args, profile='other'), dict(args, include_protected=True)):
        rejected = a.ctx.invoke('crm_record_fields', invalid)
        assert not rejected['ok'] and row['notes'] not in str(rejected)
    a.state['profile'] = 'beta'
    rejected = a.ctx.invoke('crm_record_fields', args)
    assert not rejected['ok'] and rejected['status'] == 404
    assert a.ctx.calls == []
