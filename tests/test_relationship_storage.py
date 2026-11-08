"""Additive Company/Event transactional contracts; synthetic records only."""
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import select, inspect, update, text, func
from hermes_crm.domain import CRM, CRMError, contacts, activity, idempotency, settings, tasks
from hermes_crm.report_store import schema_name
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.relationship_schema import OWNED_TABLES, schema_state, event_revisions, events, operations, companies

@pytest.fixture
def crm():
    c=CRM('sqlite:///:memory:');yield c;c.close()

def event_data(**kw):
    return dict(title='Consultation',kind='appointment',starts_at='2020-11-01T01:30:00-04:00',ends_at='2020-11-01T01:30:00-05:00',timezone='America/New_York',notes='ordinary private note',**kw)

def company(crm,key='company'):
    return CompanyStore(crm).create(dict(name='Duplicate',domain='duplicate.test',notes='private'),actor='test',key=key)

def test_lazy_schema_and_legacy_preservation(crm):
    legacy=crm.create('contacts',dict(name='Legacy',company='Old text'),key='old')
    with crm.engine.connect() as conn:
        before=[dict(r) for r in conn.execute(select(idempotency)).mappings()]
    assert CompanyStore(crm).list()['total']==EventStore(crm).list()['total']==0
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings).where(settings.c.key=='workspace_id')).first() is None
        assert not any(inspect(conn).has_table(t.name,schema=schema_name(crm)) for t in OWNED_TABLES)
    company(crm)
    with crm.engine.connect() as conn:
        assert all(inspect(conn).has_table(t.name,schema=schema_name(crm)) for t in OWNED_TABLES)
        assert before==[dict(r) for r in conn.execute(select(idempotency)).mappings()]
    assert crm.get('contacts',legacy['id'])==legacy

def test_company_duplicates_link_replay_archive_and_scope(crm):
    s=CompanyStore(crm);a=company(crm);b=company(crm,'second');assert a['id']!=b['id']
    contact=crm.create('contacts',dict(name='Person',company='Unlinked original'))
    result=s.set_contact_company(contact['id'],a['id'],expected_contact_version=1,actor='test',key='link')
    assert result['contact_version']==2
    assert s.set_contact_company(contact['id'],a['id'],expected_contact_version=1,actor='test',key='link')==result
    assert crm.get('contacts',contact['id'])['company']=='Unlinked original'
    with pytest.raises(CRMError): s.set_contact_company(contact['id'],b['id'],expected_contact_version=2,actor='test',key='link')
    same=s.set_contact_company(contact['id'],a['id'],expected_contact_version=2,actor='test',key='same');assert same['contact_version']==2
    a=s.archive(a['id'],expected_version=1,actor='test',key='archive');assert s.list()['total']==1
    assert s.get_contact_company(contact['id'])['company_archived']
    with pytest.raises(CRMError): s.set_contact_company(contact['id'],a['id'],expected_contact_version=2,actor='test',key='archived')
    s.restore(a['id'],expected_version=2,actor='test',key='restore')
    result=s.set_contact_company(contact['id'],None,expected_contact_version=2,actor='test',key='unlink');assert result['contact_version']==3
    crm.profile='another';assert s.list()['total']==0
    assert s.get_contact_company(contact['id'])['company_id'] is None

def test_event_lifecycle_revisions_minimization_no_side_effects(crm):
    e=EventStore(crm);record=e.create(event_data(),actor='test',key='event');identifier=record['id']
    assert record['starts_at']=='2020-11-01T05:30:00.000000+00:00'
    assert record['ends_at']=='2020-11-01T06:30:00.000000+00:00'
    assert record['status']=='scheduled' and 'notes' not in e.get(identifier)
    assert 'notes' not in e.list()['items'][0]
    data=dict(outcome_happened_at='2020-11-01T06:00:00Z',outcome_summary='A claimed conversation')
    completed=e.complete(identifier,data,expected_version=1,actor='test',key='complete')
    assert completed['outcome_provenance']=='self_reported' and completed['recorded_at']!=completed['outcome_happened_at']
    assert e.complete(identifier,data,expected_version=1,actor='test',key='complete')==completed
    with pytest.raises(CRMError): e.update(identifier,dict(title='Changed'),expected_version=2,actor='test',key='editterminal')
    opened=e.reopen(identifier,'Correct dates',expected_version=2,actor='test',key='reopen');assert opened['outcome_summary'] is None
    e.needs_rescheduling(identifier,'Person unavailable',expected_version=3,actor='test',key='needs')
    updated=e.update(identifier,dict(notes='Preparation'),expected_version=4,actor='test',key='edit');assert updated['status']=='needs_rescheduling'
    e.reschedule(identifier,{k:v for k,v in event_data().items() if k in ('starts_at','ends_at','timezone')},expected_version=5,actor='test',key='reschedule')
    e.cancel(identifier,'Cancelled by person',expected_version=6,actor='test',key='cancel')
    history=e.revisions(identifier,include_text=True);assert history['total']==7
    assert any(r['record'].get('outcome_summary')=='A claimed conversation' for r in history['items'])
    assert all('notes' not in r['record'] and 'reason' not in r for r in e.revisions(identifier)['items'])
    assert crm.list('tasks')==[]
    with crm.engine.connect() as conn: assert not inspect(conn).has_table('crm_report_interactions',schema=schema_name(crm))

@pytest.mark.parametrize('change',[dict(starts_at='2020-01-01T00:00:00'),dict(timezone='Bad/Zone'),dict(ends_at='2019-01-01T00:00:00Z'),dict(status='completed'),dict(source='gmail')])
def test_invalid_event_input(crm,change):
    with pytest.raises((CRMError,ValidationError)): EventStore(crm).create(event_data()|change,actor='test',key='invalid')
    assert not EventStore(crm).exists()

def test_rollback_and_expected_versions(crm,monkeypatch):
    s=CompanyStore(crm);a=company(crm)
    with pytest.raises(CRMError): s.update(a['id'],dict(name='Other'),expected_version=True,actor='test',key='bad')
    original=crm._audit
    def fail(*args,**kw): raise RuntimeError('Injected audit failure')
    monkeypatch.setattr(crm,'_audit',fail)
    with pytest.raises(RuntimeError): s.update(a['id'],dict(name='Other'),expected_version=1,actor='test',key='retry')
    assert s.get(a['id'])['name']=='Duplicate'
    monkeypatch.setattr(crm,'_audit',original)
    assert s.update(a['id'],dict(name='Other'),expected_version=1,actor='test',key='retry')['version']==2

def test_partial_and_newer_schema_fail_closed(crm):
    with crm.engine.begin() as conn: companies.create(conn)
    with pytest.raises(CRMError): CompanyStore(crm).list()
    with pytest.raises(CRMError): company(crm)

def test_newer_schema_fail_closed(crm):
    company(crm)
    with crm.engine.begin() as conn: conn.execute(update(schema_state).values(version=2))
    with pytest.raises(CRMError): CompanyStore(crm).list()
    with pytest.raises(CRMError): company(crm,'new')

def test_event_tasks_atomic_versioned_and_no_scheduler(crm):
    e=EventStore(crm);ev=e.create(event_data(),actor='test',key='event')
    data=dict(title='Research person',due_at='2020-10-31T10:00:00Z',notes='Prepare a briefing')
    result=e.create_task(ev['id'],data,expected_version=1,actor='test',key='task')
    assert result==e.create_task(ev['id'],data,expected_version=1,actor='test',key='task')
    task=result['task'];assert task['version']==1 and task['scheduler_job_id'] is None
    assert result['event']['version']==2
    same=e.link_task(ev['id'],task['id'],expected_version=2,expected_task_version=1,actor='test',key='same');assert same['task']['version']==1
    unlinked=e.unlink_task(task['id'],event_id=ev['id'],expected_version=2,expected_task_version=1,actor='test',key='unlink');assert unlinked['task']['version']==2 and unlinked['event']['version']==3
    linked=e.link_task(ev['id'],task['id'],expected_version=3,expected_task_version=2,actor='test',key='relink');assert linked['task']['version']==3 and linked['event']['version']==4
    assert crm.get('tasks',task['id'])['contact_id'] is None

def test_concurrent_initialization_and_exact_replay(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    url='sqlite:///'+str(tmp_path/'relationships.db')
    first=CRM(url);second=CRM(url)
    try:
        def create(c): return company(c)
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(create,[first,second]))
        assert results[0]==results[1]
        assert CompanyStore(first).list()['total']==1
        with first.engine.connect() as conn: assert conn.execute(select(func.count()).select_from(operations)).scalar_one()==1
    finally: first.close();second.close()

def test_future_completion_and_atomic_task_failure(crm,monkeypatch):
    e=EventStore(crm);ev=e.create(event_data(),actor='test',key='event')
    with pytest.raises(ValidationError): e.complete(ev['id'],dict(outcome_happened_at='2999-01-01T00:00:00Z',outcome_summary='Future'),expected_version=1,actor='test',key='future')
    original=e._revision
    def fail(*args,**kwargs): raise RuntimeError('Injected revision failure')
    monkeypatch.setattr(e,'_revision',fail)
    with pytest.raises(RuntimeError): e.create_task(ev['id'],dict(title='Research',due_at='2020-01-01T00:00:00Z'),expected_version=1,actor='test',key='task')
    assert crm.list('tasks')==[] and e.get(ev['id'])['version']==1
    monkeypatch.setattr(e,'_revision',original)
    assert e.create_task(ev['id'],dict(title='Research',due_at='2020-01-01T00:00:00Z'),expected_version=1,actor='test',key='task')['task']['version']==1

def test_incompatible_unique_index_rejected(crm):
    company(crm)
    with crm.engine.begin() as conn: conn.exec_driver_sql('CREATE UNIQUE INDEX accidental_unique_name ON crm_companies(name)')
    with pytest.raises(CRMError): CompanyStore(crm).list()

def test_unlink_reviews_event_target_version_and_receipt(crm):
    e=EventStore(crm);ev=e.create(event_data(),actor='test',key='event')
    other=e.create(event_data(),actor='test',key='other')
    result=e.create_task(ev['id'],dict(title='Research',due_at='2020-01-01T00:00:00Z'),expected_version=1,actor='test',key='task')
    task=result['task']
    with pytest.raises(CRMError):
        e.unlink_task(task['id'],event_id=ev['id'],expected_version=1,expected_task_version=1,actor='test',key='stale')
    with pytest.raises(CRMError):
        e.unlink_task(task['id'],event_id=other['id'],expected_version=1,expected_task_version=1,actor='test',key='wrong')
    assert e.get(ev['id'])['version']==2 and crm.get('tasks',task['id'])['version']==1
    args=dict(event_id=ev['id'],expected_version=2,expected_task_version=1,actor='test',key='unlink')
    result=e.unlink_task(task['id'],**args)
    assert result['event']['version']==3 and result['task']['version']==2
    assert e.unlink_task(task['id'],**args)==result
    with pytest.raises(CRMError): e.unlink_task(task['id'],**(args|dict(event_id=other['id'])))
    with pytest.raises(CRMError): e.unlink_task(task['id'],**(args|dict(key='stale-noop',expected_task_version=2)))
    noop=e.unlink_task(task['id'],**(args|dict(key='noop',expected_version=3,expected_task_version=2)))
    assert noop['event'] is None and noop['task']['version']==2
    assert e.get(ev['id'])['version']==3

@pytest.mark.parametrize('term',['%', '_', '\\', "' OR 1=1 --"])
def test_literal_company_event_search(crm,term):
    c=CompanyStore(crm);e=EventStore(crm)
    match=c.create(dict(name='Literal '+term),actor='test',key='match')
    c.create(dict(name='Ordinary unrelated'),actor='test',key='nonmatch')
    domain=c.create(dict(name='Domain match',domain='domain'+term+'.test'),actor='test',key='domain')
    ev=e.create(event_data()|dict(title='Literal '+term),actor='test',key='eventmatch')
    e.create(event_data()|dict(title='Ordinary unrelated'),actor='test',key='eventnonmatch')
    assert {i['id'] for i in c.list(q=term)['items']}=={match['id'],domain['id']}
    assert [i['id'] for i in e.list(q=term)['items']]==[ev['id']]

@pytest.mark.parametrize('target_schema,valid',[('relationship_expected',True),(None,False),('relationship_foreign',False)])
def test_postgres_reflection_requires_exact_target_schema(crm,monkeypatch,target_schema,valid):
    """Exercise full reflection validation without needing a PostgreSQL server."""
    from types import SimpleNamespace
    import hermes_crm.relationship_schema as schema_module
    company(crm)
    with crm.engine.connect() as conn:
        actual=inspect(conn)
        class Inspector:
            def __getattr__(self,name):
                method=getattr(actual,name)
                def call(*args,**kwargs):
                    kwargs['schema']=None
                    result=method(*args,**kwargs)
                    if name=='get_foreign_keys':
                        result=[dict(f,referred_schema=target_schema) for f in result]
                    return result
                return call
        monkeypatch.setattr(schema_module,'inspect',lambda connection:Inspector())
        configured=SimpleNamespace(backend='postgres',engine=SimpleNamespace(get_execution_options=lambda:dict(schema_translate_map={None:'relationship_expected'})))
        if valid: assert schema_module.check_schema(configured,conn)
        else:
            with pytest.raises(CRMError,match='target schema'): schema_module.check_schema(configured,conn)
