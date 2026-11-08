"""Task accountability contracts, using synthetic records only."""
import hashlib
import json
import pytest
from sqlalchemy import inspect, select, update
from pydantic import ValidationError
from hermes_crm.domain import CRM, CRMError, TaskInput, tasks, idempotency, settings
from hermes_crm.task_ownership import TaskOwnership, OWNED_TABLES, schema_state, owners
from hermes_crm.report_store import schema_name

@pytest.fixture
def crm():
    c=CRM('sqlite:///:memory:'); yield c; c.close()

def data(**kw):
    return dict(title='Follow up', due_at='2030-03-10T12:00:00.123456+05:30', **kw)

def policy(crm, version=0, required=True, default='Alice', key='policy'):
    return TaskOwnership(crm).set_policy(dict(version=version,required=required,default_owner_label=default),key=key)

def test_lazy_and_legacy_receipt(crm):
    raw=data(); old=TaskInput.model_validate(raw).model_dump()
    for k in ('owner_label','owner_source','owner_policy_version'): old.pop(k)
    old.update(schedule_status='none',scheduler_job_id=None)
    digest=hashlib.sha256(json.dumps(['tasks',old],sort_keys=True).encode()).hexdigest()
    result={'id':'historical-response','version':1,'title':'Frozen legacy payload'}
    with crm.engine.begin() as c: c.execute(idempotency.insert().values(key='legacy',digest=digest,response=json.dumps(result)))
    assert TaskOwnership(crm).policy()['version']==0
    task=crm.create('tasks',raw)
    assert task['owner_label'] is None
    crm.get('tasks',task['id']);crm.list('tasks');crm.overview()
    with crm.engine.connect() as c:
        assert not any(inspect(c).has_table(t.name,schema=schema_name(crm)) for t in OWNED_TABLES)
        assert c.execute(select(settings).where(settings.c.key=='workspace_id')).first() is None
    policy(crm)
    assert crm.create('tasks',raw,key='legacy')==result
    assert crm.get('tasks',task['id'])['owner_label'] is None

def test_required_legacy_edit_default_and_version(crm):
    t=crm.create('tasks',data()); before=crm.get('tasks',t['id'])
    p=policy(crm)
    assert p['legacy_edit_rule']=='owner_required_on_edit'
    for patch in ({'status':'done'}, {'notes':'edit'}, {'owner_label':'Alice'}, {'owner_label':'Alice','owner_policy_version':0}):
        with pytest.raises(CRMError): crm.update('tasks',t['id'],dict(version=1,**patch))
    with pytest.raises(CRMError): crm.update('tasks',t['id'],dict(version=1,status='done',owner_policy_version=1))
    with pytest.raises(CRMError): crm.create('tasks',data(owner_policy_version=1))
    with pytest.raises(CRMError): crm.create('tasks',data(owner_label='Bob',owner_policy_version=1,owner_source='default'))
    patch=dict(version=1,owner_label='Alice',owner_source='default',owner_policy_version=1)
    after=crm.update('tasks',t['id'],patch,key='owner-update')
    assert after['version']==2 and after['owner_label']=='Alice' and after['owner_source']=='default'
    assert after['due_at']==before['due_at'] and after['schedule_status']=='none'
    policy(crm,version=1,default='Bob',key='next')
    assert crm.update('tasks',t['id'],patch,key='owner-update')==after
    with pytest.raises(CRMError): crm.update('tasks',t['id'],dict(version=2,owner_label=None,owner_policy_version=2))
    with pytest.raises(CRMError): crm.update('tasks',t['id'],dict(version=2,owner_label='Alice',owner_policy_version=1))
    assert crm.get('tasks',t['id'])==after

def test_optional_clear_scoped_no_inference(crm):
    policy(crm,required=False)
    t=crm.create('tasks',data(owner_label='Alice',owner_policy_version=1))
    same=crm.update('tasks',t['id'],dict(version=1,notes='ordinary edit',owner_policy_version=1))
    assert same['owner_label']=='Alice'
    cleared=crm.update('tasks',t['id'],dict(version=2,owner_label=None,owner_policy_version=1))
    assert cleared['owner_label'] is None
    crm.profile='other'
    assert TaskOwnership(crm).policy()['version']==0
    assert crm.get('tasks',t['id'])['owner_label'] is None
    assert crm.create('tasks',data())['owner_label'] is None
    other=crm.create('tasks',data(owner_label='Bob',owner_policy_version=0),key='other')
    crm.profile='default'
    assert crm.get('tasks',other['id'])['owner_label'] is None

@pytest.mark.parametrize('extra', [dict(owner_label='  ',owner_policy_version=0),dict(owner_label='x'*161,owner_policy_version=0),dict(owner_label='A',owner_policy_version=True),dict(owner_policy_version=-1),dict(owner_source='hermes'),dict(owner_policy_version='0')])
def test_validation(crm,extra):
    with pytest.raises((CRMError,ValidationError)): crm.create('tasks',data(**extra))

def test_policy_retry_and_stale_forms(crm):
    first=policy(crm)
    assert policy(crm)==first
    with pytest.raises(CRMError): policy(crm,required=False)
    with pytest.raises(CRMError): policy(crm,key='stale')
    policy(crm,version=1,required=False,key='disable')
    with pytest.raises(CRMError): crm.create('tasks',data())
    with pytest.raises(CRMError): crm.create('tasks',data(owner_policy_version=1,owner_label='Alice',owner_source='default'))
    assert crm.create('tasks',data(owner_policy_version=2))['owner_label'] is None

def test_atomic_rollback(crm,monkeypatch):
    policy(crm)
    t=crm.create('tasks',data(owner_policy_version=1,owner_label='Alice'))
    old=crm.get('tasks',t['id'])
    def fail(*a,**k): raise RuntimeError('synthetic failure')
    monkeypatch.setattr(crm,'_audit',fail)
    with pytest.raises(RuntimeError): crm.update('tasks',t['id'],dict(version=1,owner_label='Bob',owner_policy_version=1),key='retry')
    assert crm.get('tasks',t['id'])==old
    with pytest.raises(RuntimeError): policy(crm,version=1,key='failed')
    assert TaskOwnership(crm).policy()['version']==1

def test_schema_newer_partial_reject(crm):
    policy(crm)
    with crm.engine.begin() as c: c.execute(update(schema_state).values(version=2))
    for action in (lambda:TaskOwnership(crm).policy(),lambda:crm.create('tasks',data()),lambda:crm.list('tasks')):
        with pytest.raises(CRMError,match='schema version'): action()

def test_schema_partial_no_repair(crm):
    with crm.engine.begin() as c: schema_state.create(c)
    with pytest.raises(CRMError,match='incomplete'): policy(crm)
    with crm.engine.connect() as c: assert not inspect(c).has_table(owners.name,schema=schema_name(crm))

def test_filters_and_projection(crm):
    from hermes_crm.agent_read_policy import project_agent_result
    missing=crm.create('tasks',data()); owned=crm.create('tasks',data(owner_label='A',owner_policy_version=0))
    assert [r['id'] for r in crm.list('tasks',owner='missing')]==[missing['id']]
    assert [r['id'] for r in crm.list('tasks',owner='present',owner_label='A')]==[owned['id']]
    projected=project_agent_result('crm_task_get',owned)
    assert projected['owner_label']=='A' and 'owner_source' not in projected
    assert crm.overview()['tasks'][0]['owner_label'] in (None,'A')

def test_event_task_shared_enforcement(crm):
    from hermes_crm.events import EventStore
    from test_relationship_storage import event_data
    store=EventStore(crm); event=store.create(event_data(),actor='test',key='event')
    policy(crm)
    with pytest.raises(CRMError): store.create_task(event['id'],data(),expected_version=1,actor='test',key='task')
    assert store.get(event['id'])['version']==1
    result=store.create_task(event['id'],data(owner_label='Alice',owner_policy_version=1),expected_version=1,actor='test',key='task')
    assert result['task']['owner_label']=='Alice'
    assert store.create_task(event['id'],data(owner_label='Alice',owner_policy_version=1),expected_version=1,actor='test',key='task')==result

def test_scoped_create_receipts_and_unknown_retry(crm):
    raw=data(owner_label='Alice',owner_policy_version=0)
    first=crm.create('tasks',raw,key='same-key')
    policy(crm)
    assert crm.create('tasks',raw,key='same-key')==first
    crm.profile='other'
    second=crm.create('tasks',raw,key='same-key')
    assert first['id']!=second['id']
    with pytest.raises(CRMError): crm.create('tasks',data(owner_label='Bob',owner_policy_version=0),key='same-key')

def test_assignment_snapshot_not_rewritten(crm):
    from hermes_crm.native_work import NativeWorkStore
    t=crm.create('tasks',data(owner_label='Alice',owner_policy_version=0))
    store=NativeWorkStore(crm)
    assignment=store.create(task_id=t['id'],human_owner='Separate assignment owner',prompt='Analyze locally',success_criteria='Report locally',run_at='2030-01-01T10:00:00Z',idempotency_key='assignment',expected_task_version=1)
    frozen=assignment['payload'].copy()
    crm.update('tasks',t['id'],dict(version=1,owner_label='Bob',owner_policy_version=0),key='edit')
    current=store.get(assignment['id'])
    assert current['payload']==frozen
    assert not current['source_task_current'] and current['current_task_version']==2
    assert current['payload']['human_owner']=='Separate assignment owner'

def test_report_owner_missing_and_exact(crm):
    from hermes_crm.reports import ReportEngine
    crm.create('tasks',data())
    engine=ReportEngine(crm)
    assert engine.run(dict(entity='tasks',columns=['owner_label'],filter=dict(field='owner_label',op='is_null',value=None)))['total']==1
    crm.create('tasks',data(owner_label='Alice',owner_policy_version=0))
    result=engine.run(dict(entity='tasks',columns=['owner_label'],filter=dict(field='owner_label',op='eq',value='Alice')))
    assert result['items']==[{'owner_label':'Alice'}]
    crm.profile='other'
    assert engine.run(dict(entity='tasks',columns=['owner_label'],filter=dict(field='owner_label',op='is_null',value=None)))['total']==2

def test_policy_and_create_serialization(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    path=f'sqlite:///{tmp_path}/race.db'
    a=CRM(path); b=CRM(path); barrier=threading.Barrier(2)
    def change():
        barrier.wait();return policy(a)
    def create():
        barrier.wait()
        try: return b.create('tasks',data(owner_label='Alice',owner_policy_version=0))
        except CRMError as e: return e.status
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            f=pool.submit(change); g=pool.submit(create); f.result(); result=g.result()
        assert result==409 or result['owner_label']=='Alice'
        assert TaskOwnership(a).policy()['version']==1
        with pytest.raises(CRMError): b.create('tasks',data(owner_policy_version=0))
    finally: a.close();b.close()

def test_export_scope_and_policy_audit(crm):
    from hermes_crm.protection import Keyring, ProtectionStore, decrypt_export, owned_tables
    from hermes_crm.task_ownership import metadata as owner_metadata
    ring=Keyring('synthetic',{'synthetic':bytes(range(32))})
    policy(crm)
    crm.create('tasks',data(owner_label='Alice',owner_policy_version=1),key='created')
    assert any(a['entity_type']=='task_owner_policy' for a in crm.activities())
    crm.profile='other'
    assert not any(a['entity_type']=='task_owner_policy' for a in crm.activities())
    policy(crm,default='Bob')
    crm.create('tasks',data(owner_label='Bob',owner_policy_version=1),key='created')
    for profile,expected in [('default','Alice'),('other','Bob')]:
        crm.profile=profile
        store=ProtectionStore(crm)
        captured=decrypt_export(store.export(ring),ring,workspace=store.workspace,profile=profile)['tables']
        assert captured['crm_task_owner_policies'][0]['default_owner_label']==expected
        assert len(captured['crm_task_owner_policies'])==1
        assert [r['owner_label'] for r in captured['crm_task_owners']]==[expected]
        assert len(captured['crm_task_owner_operations'])==2
        assert len(captured['crm_task_owner_schema'])==1
    assert owned_tables()['crm_tasks'] is not owner_metadata.tables['crm_tasks']

def test_relationship_maintenance_does_not_apply_default(crm):
    from hermes_crm.events import EventStore
    from test_relationship_storage import event_data
    task=crm.create('tasks',data())
    events=EventStore(crm); event=events.create(event_data(),actor='test',key='event')
    policy(crm)
    linked=events.link_task(event['id'],task['id'],expected_version=1,expected_task_version=1,actor='test',key='link')
    current=crm.get('tasks',task['id'])
    assert current['owner_label'] is None and current['due_at']==task['due_at']
    assert current['schedule_status']=='none'

def test_receipt_lane_changes_rejected(crm):
    crm.create('tasks',data(),key='legacy-key')
    with pytest.raises(CRMError): crm.create('tasks',data(owner_policy_version=0,owner_label='Alice'),key='legacy-key')
    crm.create('tasks',data(owner_policy_version=0,owner_label='Alice'),key='aware-key')
    with pytest.raises(CRMError): crm.create('tasks',data(),key='aware-key')
    assert len(crm.list('tasks'))==2
