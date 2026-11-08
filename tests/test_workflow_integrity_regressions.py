"""Synthetic workflow fixes, with opt-in disposable PostgreSQL service coverage."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, func
from test_activity_navigation import crm
from test_native_work_adapters import adapters
from hermes_crm.domain import CRMError, TaskInput, activity, tasks
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore, timestamp
from hermes_crm.relationship_schema import events, event_revisions, operations
from hermes_crm.web import create_app

BAD_TIMES = ('0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00')


def data(**changes):
    return dict(title='Synthetic consultation', kind='appointment',
                starts_at='2020-01-01T10:00:00.123456Z',
                ends_at='2020-01-01T11:00:00.654321Z', timezone='UTC', **changes)


def counts(crm):
    with crm.engine.connect() as conn:
        return tuple(conn.execute(select(func.count()).select_from(t)).scalar_one()
                     for t in (events, event_revisions, operations, tasks, activity))


def test_archived_company_new_links_rejected_existing_context_retained(crm):
    companies = CompanyStore(crm); store = EventStore(crm)
    company = companies.create({'name':'Synthetic organization'}, actor='test', key='company')
    original = store.create(data(company_id=company['id']), actor='test', key='original')
    unlinked = store.create(data(), actor='test', key='unlinked')
    companies.archive(company['id'], expected_version=1, actor='test', key='archive')
    before = counts(crm)
    with pytest.raises(CRMError, match='Archived Company') as error:
        store.create(data(company_id=company['id']), actor='test', key='new')
    assert error.value.status == 409
    with pytest.raises(CRMError, match='Archived Company'):
        store.update(unlinked['id'], {'company_id':company['id']}, expected_version=1, actor='test', key='reassign')
    assert counts(crm) == before
    assert store.get(unlinked['id'])['version'] == 1
    # A retry is historical evidence, not a new link.
    assert store.create(data(company_id=company['id']), actor='test', key='original') == original
    edited = store.update(original['id'], {'notes':'Retained context','company_id':company['id']}, expected_version=1, actor='test', key='edit')
    assert edited['starts_at'] == original['starts_at']
    moved = store.reschedule(original['id'], {k:data()[k] for k in ('starts_at','ends_at','timezone')}, expected_version=2, actor='test', key='reschedule')
    assert moved['company_id'] == company['id']
    completed = store.complete(original['id'], {'outcome_happened_at':'2020-01-01T11:00:00Z','outcome_summary':'Synthetic'}, expected_version=3, actor='test', key='complete')
    reopened = store.reopen(original['id'], 'Correction', expected_version=completed['version'], actor='test', key='reopen')
    assert reopened['company_id'] == company['id']
    cleared = store.update(original['id'], {'company_id':None}, expected_version=reopened['version'], actor='test', key='clear')
    assert cleared['company_id'] is None
    companies.restore(company['id'], expected_version=2, actor='test', key='restore')
    # Reuse failed operation keys: no receipt was committed on failure.
    assert store.create(data(company_id=company['id']), actor='test', key='new')['company_id'] == company['id']
    assert store.update(unlinked['id'], {'company_id':company['id']}, expected_version=1, actor='test', key='reassign')['company_id'] == company['id']


@pytest.mark.parametrize('bad', BAD_TIMES)
def test_timestamp_range_failures_are_atomic_validation_errors(crm, bad):
    store = EventStore(crm); original = store.create(data(), actor='test', key='event')
    before = counts(crm)
    with pytest.raises(ValidationError, match='supported UTC range'):
        store.create(data() | {'starts_at':bad}, actor='test', key='bad-create')
    with pytest.raises(ValidationError, match='supported UTC range'):
        store.update(original['id'], {'ends_at':bad}, expected_version=1, actor='test', key='bad-update')
    with pytest.raises(ValidationError, match='supported UTC range'):
        store.complete(original['id'], {'outcome_happened_at':bad,'outcome_summary':'Synthetic'}, expected_version=1, actor='test', key='bad-complete')
    with pytest.raises(ValidationError, match='supported UTC range'):
        store.create_task(original['id'], {'title':'Synthetic task','due_at':bad}, expected_version=1, actor='test', key='bad-task')
    with pytest.raises(CRMError, match='supported UTC range') as error:
        store.list(starts_from=bad)
    assert error.value.status == 400
    assert counts(crm) == before
    assert store.get(original['id'], include_text=True) == original
    receipt = store.create_task(original['id'], {'title':'Synthetic task','due_at':data()['starts_at']}, expected_version=1, actor='test', key='bad-task')
    assert receipt['task']['due_at'] == original['starts_at']


@pytest.mark.parametrize('value', ['0001-01-01T00:00:00Z','9999-12-31T23:59:59.999999Z','2020-01-01T11:30:00.123456+01:30'])
def test_representable_timestamp_boundaries_and_precision_preserved(value):
    assert TaskInput.model_validate({'title':'Task','due_at':value}).due_at == timestamp(value)


@pytest.mark.parametrize('bad', BAD_TIMES)
def test_http_and_registered_tool_validation(adapters, bad):
    a = adapters; token = a.client.get('/meta').json()['workspace_token']
    event = a.ctx.invoke('crm_event_create', {'data':data(),'idempotency_key':'event'})['data']
    crm = a.factory()
    try:
        before = counts(crm)
        clients = [(a.client,''), (TestClient(create_app(crm)), '/api')]
        for client,prefix in clients:
            for path,body in [
                ('/events', {'data':data() | {'starts_at':bad}}),
                ('/events/'+event['id']+'/tasks', {'expected_version':1,'data':{'title':'Task','due_at':bad}}),
                ('/events/'+event['id']+'/complete', {'expected_version':1,'data':{'outcome_happened_at':bad,'outcome_summary':'Synthetic'}}),
                ('/tasks', {'data':{'title':'Task','due_at':bad}}),
            ]:
                payload = body['data'] if prefix and path == '/tasks' else dict(workspace_token=token,idempotency_key='bad',**body)
                response = client.post(prefix+path, json=payload)
                assert response.status_code == 422, response.text
                assert 'supported UTC range' in response.text
            response = client.get(prefix+'/events', params={'workspace_token':token,'starts_before':bad})
            assert response.status_code == 400 and 'supported UTC range' in response.text
        assert counts(crm) == before
        for name,args in [
            ('crm_event_create', {'data':data() | {'starts_at':bad},'idempotency_key':'tool-bad'}),
            ('crm_event_task_create', {'record_id':event['id'],'expected_version':1,'data':{'title':'Task','due_at':bad},'idempotency_key':'tool-bad'}),
            ('crm_task_create', {'title':'Task','due_at':bad}),
        ]:
            result = a.ctx.invoke(name,args)
            assert result['ok'] is False and result['status'] == 422, result
            assert 'supported UTC range' in result['error']
        assert counts(crm) == before
        assert crm.list('tasks') == [] and EventStore(crm).get(event['id'])['version'] == 1
        assert a.ctx.calls == []
    finally:
        crm.close()


def test_archived_company_http_and_tool_guards(adapters):
    a=adapters; token=a.client.get('/meta').json()['workspace_token']
    company=a.ctx.invoke('crm_company_create',{'data':{'name':'Archived'},'idempotency_key':'company'})['data']
    assert a.ctx.invoke('crm_company_archive',{'record_id':company['id'],'expected_version':1,'idempotency_key':'archive'})['ok']
    payload={'data':data(company_id=company['id']),'idempotency_key':'rejected'}
    assert a.client.post('/events',json=dict(payload,workspace_token=token)).status_code==409
    result=a.ctx.invoke('crm_event_create',payload)
    assert result['ok'] is False and result['status']==409
    assert not a.ctx.calls
