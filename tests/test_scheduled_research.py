"""Synthetic adapters only: no model, host jobs, provider or network."""
import json
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from sqlalchemy import event, select
from hermes_crm.domain import CRM, CRMError
from hermes_crm.companies import CompanyStore
from hermes_crm.research_store import ResearchStore
from hermes_crm.scheduled_research import ScheduledResearchStore, assignments, operations, RUN_TOOLSET
from hermes_crm.native_work import TOOLSETS
from test_native_work import Host

@pytest.fixture(params=['contacts','companies'])
def setup(tmp_path,request):
    crm=CRM(f'sqlite:///{tmp_path}/research.db',profile='synthetic')
    target=(crm.create('contacts',{'name':'Synthetic subject','notes':'Private existing text'}) if request.param=='contacts' else
        CompanyStore(crm).create({'name':'Synthetic subject','notes':'Private existing text'},actor='test',key='company'))
    store=ScheduledResearchStore(crm)
    task=crm.create('tasks',{'title':'Prepare synthetic relationship brief','due_at':'2030-04-02T12:00:00Z'})
    data=dict(task_id=task['id'],task_version=task['version'],human_owner='Synthetic owner',target_kind=request.param,target_id=target['id'],target_version=1,
        public_question='What public products does Synthetic Example offer?',
        run_at='2030-04-01T12:30:41+00:00',research='web',propose_note=True,max_sources=2)
    yield crm,store,target,data
    crm.close()

def prepare(setup):
    crm,s,t,data=setup; host=Host(); a=s.create(data,idempotency_key='create')
    a=s.schedule(host,a['id'],session_id='synthetic-session',task_id='synthetic-turn')
    assert a['state']=='scheduled'
    host.identity=SimpleNamespace(job_id=a['job_id'],job_name=a['job_name'],execution_id='execution-1',
        source='builtin',profile='synthetic',scheduled_instant=a['payload']['run_at'],started_at='2030-04-01T12:30:42Z')
    return host,a

def packet(setup):
    d=setup[3]
    return dict(target_kind=d['target_kind'],target_id=d['target_id'],target_version=1,
        question='Public products?',source_url='https://example.com/products',source_title='Products',
        observed_at='2030-04-01T12:30:42Z',claims=['Source says widgets.'],hypotheses=[])

def test_complete_flow_keeps_notes_and_old_contract(setup):
    crm,s,t,data=setup; h,a=prepare(setup)
    run=s.run_get(h,a['id'],generation=1)
    assert 'Private existing text' not in json.dumps(run)
    e=s.evidence(h,a['id'],generation=1,operation_id='source1',data=packet(setup))
    p=dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,
        addition='Source says widgets (https://example.com/products).')
    proposal=s.propose(h,a['id'],generation=1,operation_id='proposal',data=p)
    assert proposal['status']=='pending'
    result=s.report(h,a['id'],generation=1,summary='Cited note proposal ready')
    assert result['awaiting_human_review'] and not result['host_terminal_success_verified']
    assert s.report(h,a['id'],generation=1,summary='Cited note proposal ready')==result
    assert ResearchStore(crm).preview(proposal['id'])['current_notes']=='Private existing text'
    assert s.get(a['id'])['enabled_toolsets']==['web',RUN_TOOLSET,'no_mcp']
    assert TOOLSETS==('crm_read','crm_work_read','crm_work_report','no_mcp')
    assert len(h.calls)==2
    assert all(call[1]['session_id']=='synthetic-session' for call in h.calls)

@pytest.mark.parametrize('field,value',[('research','browser'),('research','all'),('max_sources',True),('target_version',True),('propose_note','yes'),('enabled_toolsets',['terminal'])])
def test_manifest_rejects_broadening(setup,field,value):
    data={**setup[3],field:value}
    with pytest.raises((ValidationError,CRMError)): setup[1].create(data,idempotency_key='bad')

@pytest.mark.parametrize('field,value',[('source','direct'),('profile','foreign'),('job_id','foreign'),('job_name','foreign'),('scheduled_instant',None),('execution_id','other')])
def test_identity_rejection(setup,field,value):
    h,a=prepare(setup);s=setup[1]
    s.run_get(h,a['id'],generation=1)
    setattr(h.identity,field,value)
    with pytest.raises(CRMError): s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup))

def test_interactive_forgery_cancel_and_future_management_rejected(setup):
    h,a=prepare(setup); s=setup[1]
    with pytest.raises(CRMError): s.schedule(h,a['id'])
    with pytest.raises(CRMError): s.run_get(h,a['id'],generation=True)
    h.identity=None
    with pytest.raises(CRMError): s.run_get(h,a['id'],generation=1)
    saved=s.cancel(h,a['id'],expected_version=s.get(a['id'])['version'])
    assert saved['state']=='cancelled'
    assert 'future_pause_observed' in saved['reason']

def test_idempotency_limits_and_no_post_report_writes(setup):
    h,a=prepare(setup); s=setup[1]; p=packet(setup)
    first=s.evidence(h,a['id'],generation=1,operation_id='e1',data=p)
    assert s.evidence(h,a['id'],generation=1,operation_id='e1',data=p)==first
    with pytest.raises(CRMError,match='Conflicting'): s.evidence(h,a['id'],generation=1,operation_id='e1',data={**p,'claims':['Different']})
    s.evidence(h,a['id'],generation=1,operation_id='e2',data=p)
    with pytest.raises(CRMError,match='limit'): s.evidence(h,a['id'],generation=1,operation_id='e3',data=p)
    s.report(h,a['id'],generation=1,summary='Done')
    with pytest.raises(CRMError): s.evidence(h,a['id'],generation=1,operation_id='e4',data=p)
    with pytest.raises(CRMError): s.report(h,a['id'],generation=1,summary='Conflicting')

def test_wrong_target_and_unapproved_proposal(setup):
    setup[3]['propose_note']=False; h,a=prepare(setup); s=setup[1];p=packet(setup)
    with pytest.raises(CRMError): s.evidence(h,a['id'],generation=1,operation_id='e',data={**p,'target_id':'00000000-0000-0000-0000-000000000001'})
    e=s.evidence(h,a['id'],generation=1,operation_id='e',data=p)
    with pytest.raises(CRMError,match='not approved'): s.propose(h,a['id'],generation=1,operation_id='p',data=dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Note'))

@pytest.mark.parametrize('action',['create','resume'])
def test_lost_host_reply_does_not_retry(setup,action):
    s=setup[1];h=Host();a=s.create(setup[3],idempotency_key='create')
    def lost(args,result):
        if args['action']==action: raise RuntimeError('lost response')
    h.after=lost
    a=s.schedule(h,a['id'])
    assert a['state']==action+'_unknown'
    count=len(h.calls); s.schedule(h,a['id']); assert len(h.calls)==count
    h.after=None; s.reconcile(h,a['id'])
    assert len([x for x in h.calls if x[0]['action']=='create'])==1
    assert len([x for x in h.calls if x[0]['action']=='resume'])==(0 if action=='create' else 1)

def test_cancellation_during_paused_create_never_resumes(setup):
    s=setup[1];h=Host();a=s.create(setup[3],idempotency_key='create')
    def cancel(args,result):
        if args['action']=='create': s.cancel(h,a['id'],expected_version=s.get(a['id'])['version'])
    h.after=cancel; result=s.schedule(h,a['id'])
    assert result['state']=='cancelled' and result['job_id']
    assert [c[0]['action'] for c in h.calls]==['create']

def _fail_scheduled_receipt_insert(conn,cursor,statement,parameters,context,executemany):
    compiled=getattr(context,'compiled',None)
    compiled_statement=getattr(compiled,'statement',None)
    if getattr(context,'isinsert',False) and getattr(compiled_statement,'table',None) is operations:
        raise RuntimeError('receipt failed')


@pytest.mark.parametrize('dialect_name',['sqlite','postgresql'])
def test_receipt_failure_hook_uses_compiled_table_identity(dialect_name):
    from sqlalchemy.dialects import sqlite,postgresql
    dialect=(sqlite.dialect() if dialect_name=='sqlite' else postgresql.dialect())
    options=({'schema_translate_map':{None:'crm_synthetic_test'},'render_schema_translate':True}
        if dialect_name=='postgresql' else {})
    target=operations.insert().compile(dialect=dialect,**options)
    if dialect_name=='postgresql':assert 'crm_synthetic_test.crm_scheduled_research_ops_v1' in str(target)
    context=SimpleNamespace(compiled=target,isinsert=True)
    with pytest.raises(RuntimeError,match='receipt failed'):
        _fail_scheduled_receipt_insert(None,None,str(target),None,context,False)
    other=assignments.insert().compile(dialect=dialect,**options)
    _fail_scheduled_receipt_insert(None,None,str(other),None,SimpleNamespace(compiled=other,isinsert=True),False)
    update=operations.update().compile(dialect=dialect,**options)
    _fail_scheduled_receipt_insert(None,None,str(update),None,SimpleNamespace(compiled=update,isinsert=False),False)
    _fail_scheduled_receipt_insert(None,None,'uncompiled statement',None,SimpleNamespace(compiled=None,isinsert=False),False)


def test_receipt_failure_rolls_back_evidence_and_execution_binding(setup):
    crm,s,t,data=setup;h,a=prepare(setup)
    fail=_fail_scheduled_receipt_insert
    event.listen(crm.engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='receipt failed'): s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup))
    finally: event.remove(crm.engine,'before_cursor_execute',fail)
    assert ResearchStore(crm).list('evidence',data['target_kind'],t['id'])['total']==0
    assert s.get(a['id'])['execution_id'] is None
    assert s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup))['id']

def test_stale_target_blocks_new_write_but_exact_receipt_replays(setup):
    crm,s,t,data=setup; h,a=prepare(setup);p=packet(setup)
    e=s.evidence(h,a['id'],generation=1,operation_id='e',data=p)
    if data['target_kind']=='contacts': crm.update('contacts',t['id'],{'version':1,'name':'Changed'})
    else: CompanyStore(crm).update(t['id'],{'name':'Changed'},expected_version=1,actor='test',key='changed')
    assert s.evidence(h,a['id'],generation=1,operation_id='e',data=p)==e
    with pytest.raises(CRMError,match='target changed'): s.evidence(h,a['id'],generation=1,operation_id='new',data=p)

def test_create_exact_retry_preserves_stale_intent(setup):
    s=setup[1];a=s.create(setup[3],idempotency_key='create')
    assert s.create(setup[3],idempotency_key='create')['id']==a['id']
    with pytest.raises(CRMError,match='Conflicting'): s.create({**setup[3],'research':'search'},idempotency_key='create')

def test_tools_register_only_new_toolsets(setup):
    from hermes_crm.scheduled_research_tools import register_scheduled_research_tools
    registrations=[]
    register_scheduled_research_tools(lambda *a,**kw:registrations.append((a,kw)),Host())
    assert len(registrations)==10
    assert {r[1]['toolset'] for r in registrations}=={RUN_TOOLSET,'crm_scheduled_research_read_v1','crm_scheduled_research_schedule_v1'}
    assert len([r for r in registrations if r[1]['toolset']==RUN_TOOLSET])==4

@pytest.mark.parametrize('tamper',[{'enabled_toolsets':['web',RUN_TOOLSET]}, {'skills':['unreviewed']}, {'workdir':'/tmp'}, {'prompt_preview':'modified'}, {'next_run_at':'2030-04-01T12:30:41+00:00'}])
def test_unverified_paused_create_never_binds_or_resumes(setup,tamper):
    s=setup[1];h=Host();a=s.create(setup[3],idempotency_key='create')
    h.after=lambda args,result: result['job'].update(tamper) if args['action']=='create' else None
    result=s.schedule(h,a['id'])
    assert result['state']=='create_unknown' and result['job_id'] is None
    assert [c[0]['action'] for c in h.calls]==['create']

def test_target_changes_while_create_in_flight_leaves_paused(setup):
    crm,s,t,data=setup;h=Host();a=s.create(data,idempotency_key='create')
    def change(args,result):
        if args['action']=='create':
            if data['target_kind']=='contacts': crm.update('contacts',t['id'],{'version':1,'name':'Changed'})
            else: CompanyStore(crm).update(t['id'],{'name':'Changed'},expected_version=1,actor='test',key='changed')
    h.after=change;result=s.schedule(h,a['id'])
    assert result['state']=='bound_paused' and result['job_id']
    assert [c[0]['action'] for c in h.calls]==['create']

def test_concurrent_schedule_and_evidence_same_key(setup):
    from concurrent.futures import ThreadPoolExecutor
    crm,s,t,data=setup;h=Host();a=s.create(data,idempotency_key='create')
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _:s.schedule(h,a['id']),range(6)))
    assert [c[0]['action'] for c in h.calls]==['create','resume']
    a=s.get(a['id'])
    h.identity=SimpleNamespace(job_id=a['job_id'],job_name=a['job_name'],execution_id='execution-1',source='builtin',profile='synthetic',scheduled_instant=a['payload']['run_at'],started_at=None)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results=list(pool.map(lambda _:s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup)),range(6)))
    assert all(r==results[0] for r in results)
    assert ResearchStore(crm).list('evidence',data['target_kind'],t['id'])['total']==1

def test_cross_assignment_evidence_and_scope_are_rejected(setup):
    crm,s,t,data=setup;h,a=prepare(setup)
    e=ResearchStore(crm).submit(packet(setup),key='unrelated-evidence')
    with pytest.raises(CRMError,match='does not belong'): s.propose(h,a['id'],generation=1,operation_id='p',data=dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Note'))
    other=CRM(str(crm.engine.url),profile='other')
    try:
        with pytest.raises(CRMError,match='not found'): ScheduledResearchStore(other).get(a['id'])
    finally: other.close()

def test_schema_and_payload_fail_closed(setup):
    from sqlalchemy import text,update
    crm,s,t,data=setup;a=s.create(data,idempotency_key='create')
    with crm.engine.begin() as c:
        c.execute(update(assignments).where(assignments.c.id==a['id']).values(payload='{}'))
    with pytest.raises(CRMError,match='integrity'):s.get(a['id'])
    with crm.engine.begin() as c:c.execute(text('ALTER TABLE crm_scheduled_research_v1 ADD COLUMN unexpected TEXT'))
    with pytest.raises(CRMError,match='incompatible'):ScheduledResearchStore(crm)

def test_task_version_status_and_filtered_visibility(setup):
    crm,s,t,data=setup;h,a=prepare(setup)
    assert a['payload']['task_due_at']!=a['payload']['run_at']
    assert s.list(task_id=data['task_id'])[0]['id']==a['id']
    assert s.list(task_id='00000000-0000-0000-0000-000000000001')==[]
    crm.update('tasks',data['task_id'],{'version':data['task_version'],'title':'Changed task'})
    for operation in (lambda:s.run_get(h,a['id'],generation=1),
        lambda:s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup)),
        lambda:s.report(h,a['id'],generation=1,summary='Result')):
        with pytest.raises(CRMError,match='Source task changed'):operation()
    assert crm.get('tasks',data['task_id'])['status']=='open'

def test_stale_task_before_schedule_does_not_create_job(setup):
    crm,s,t,data=setup;a=s.create(data,idempotency_key='create');h=Host()
    crm.update('tasks',data['task_id'],{'version':data['task_version'],'status':'done'})
    with pytest.raises(CRMError,match='Source task changed'):s.schedule(h,a['id'])
    assert not h.calls

@pytest.mark.parametrize('field,value',[('human_owner',' '),('task_version',True),('task_id','not-an-id')])
def test_bad_task_binding(setup,field,value):
    with pytest.raises((ValidationError,CRMError,ValueError)):setup[1].create({**setup[3],field:value},idempotency_key='bad')

@pytest.mark.parametrize('damage',['missing','partial','newer','corrupt'])
@pytest.mark.parametrize('operation',['get','list','create','run_get','evidence','proposal','report','cancel','schedule','reconcile'])
def test_runtime_schema_gate_on_noninitializing_store(setup,damage,operation):
    from sqlalchemy import text,inspect
    crm,s,t,data=setup;h,a=prepare(setup)
    # Save real source evidence so proposal would otherwise be valid.
    e=s.evidence(h,a['id'],generation=1,operation_id='source-before-damage',data=packet(setup))
    proposal=dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Cited proposal')
    version=s.get(a['id'])['version']
    with crm.engine.begin() as c:
        if damage in ('missing','partial'):c.execute(text('DROP TABLE crm_scheduled_research_ops_v1'))
        if damage=='missing':c.execute(text('DROP TABLE crm_scheduled_research_v1'))
        if damage=='newer':c.execute(text('ALTER TABLE crm_scheduled_research_v1 ADD COLUMN future_version TEXT'))
        if damage=='corrupt':c.execute(text('ALTER TABLE crm_scheduled_research_v1 RENAME COLUMN state TO wrong_state'))
    def snapshot():
        with crm.engine.connect() as c:
            return {name:[tuple(r) for r in c.execute(text('SELECT * FROM '+name))]
                for name in inspect(c).get_table_names()}
    before=snapshot();calls=len(h.calls)
    s=ScheduledResearchStore(crm,initialize=False)
    if operation in ('cancel','schedule','reconcile'):h.identity=None
    actions={
        'get':lambda:s.get(a['id']),
        'list':lambda:s.list(task_id=data['task_id']),
        'create':lambda:s.create(data,idempotency_key='new-create'),
        'run_get':lambda:s.run_get(h,a['id'],generation=1),
        'evidence':lambda:s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup)),
        'proposal':lambda:s.propose(h,a['id'],generation=1,operation_id='p',data=proposal),
        'report':lambda:s.report(h,a['id'],generation=1,summary='Not permitted to commit'),
        'cancel':lambda:s.cancel(h,a['id'],expected_version=version),
        'schedule':lambda:s.schedule(h,a['id']),
        'reconcile':lambda:s.reconcile(h,a['id'])}
    with pytest.raises(CRMError,match='schema|storage|column'):actions[operation]()
    assert snapshot()==before
    assert len(h.calls)==calls

def test_registered_plugin_tools_execute_task_linked_flow(setup,monkeypatch):
    from hermes_crm import plugin
    crm,store,target,data=setup
    class Context(Host):
        def __init__(self):super().__init__();self.tools={}
        def get_config(self,key,default=None):return default
        def register_tool(self,**value):self.tools[value['name']]=value
    ctx=Context()
    monkeypatch.setattr(plugin,'open_profile_crm',lambda **kwargs:CRM(str(crm.engine.url),profile='synthetic'))
    plugin.register(ctx)
    assert len(ctx.tools)==83
    def call(name,args):
        response=json.loads(ctx.tools[name]['handler'](args))
        assert response.get('ok') is True,response
        return response['data']
    a=call('crm_scheduled_research_create',{'data':data,'idempotency_key':'registered-create'})
    a=call('crm_scheduled_research_schedule',{'assignment_id':a['id']})
    ctx.identity=SimpleNamespace(job_id=a['job_id'],job_name=a['job_name'],execution_id='registered-execution',source='builtin',profile='synthetic',scheduled_instant=a['payload']['run_at'],started_at=None)
    common=dict(assignment_id=a['id'],generation=1)
    assert call('crm_scheduled_research_run_get',common)['task_id']==data['task_id']
    e=call('crm_scheduled_research_evidence',{**common,'operation_id':'e','data':packet(setup)})
    call('crm_scheduled_research_propose',{**common,'operation_id':'p','data':dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Synthetic cited source https://example.com/products')})
    assert call('crm_scheduled_research_report',{**common,'summary':'Synthetic supplied evidence ready'})['awaiting_human_review']
    assert call('crm_scheduled_research_get',{'assignment_id':a['id']})['state']=='result_reported'
    assert call('crm_scheduled_research_list',{'task_id':data['task_id']})[0]['id']==a['id']
    assert crm.get('tasks',data['task_id'])['status']=='open'

def test_page_reports_absent_without_creating_and_filters_before_paging(tmp_path):
    from sqlalchemy import inspect
    crm=CRM(f'sqlite:///{tmp_path}/fresh.db',profile='synthetic')
    try:
        before=inspect(crm.engine).get_table_names()
        page=ScheduledResearchStore(crm,initialize=False).page()
        assert page==dict(initialized=False,storage='absent',items=[],total=None,limit=50,offset=0)
        assert inspect(crm.engine).get_table_names()==before
        t=crm.create('contacts',{'name':'Synthetic'})
        task=crm.create('tasks',{'title':'Synthetic task','due_at':'2030-04-02T12:00:00Z'})
        s=ScheduledResearchStore(crm)
        data=dict(task_id=task['id'],task_version=1,human_owner='Synthetic owner',target_kind='contacts',target_id=t['id'],target_version=1,public_question='Synthetic question',run_at='2030-04-01T12:30:41+00:00',research='search',propose_note=False,max_sources=1)
        created=[s.create(data,idempotency_key=f'page-{n}') for n in range(3)]
        page=s.page(task_id=task['id'],limit=1,offset=1)
        assert page['initialized'] and page['total']==3 and len(page['items'])==1
        assert page['items'][0]['id']==created[1]['id']
        assert s.page(task_id='00000000-0000-0000-0000-000000000001')['total']==0
    finally:crm.close()

@pytest.mark.parametrize('change',['task_changed','task_completed','target_changed','target_archived'])
@pytest.mark.parametrize('outcome',['blocked','failed'])
def test_stale_source_can_report_blocker_but_cannot_write_or_complete(setup,change,outcome):
    crm,s,t,data=setup
    if change=='target_archived' and data['target_kind']!='companies':pytest.skip('Contacts do not have archive')
    h,a=prepare(setup)
    if change.startswith('task_'):
        patch={'title':'Changed task'} if change=='task_changed' else {'status':'done'}
        crm.update('tasks',data['task_id'],dict(version=data['task_version'],**patch))
    elif data['target_kind']=='contacts':crm.update('contacts',t['id'],{'version':1,'name':'Changed'})
    elif change=='target_archived':CompanyStore(crm).archive(t['id'],expected_version=1,actor='test',key='archive')
    else:CompanyStore(crm).update(t['id'],{'name':'Changed'},expected_version=1,actor='test',key='change')
    before=crm.get('tasks',data['task_id'])
    with pytest.raises(CRMError):s.run_get(h,a['id'],generation=1)
    with pytest.raises(CRMError):s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup))
    with pytest.raises(CRMError):s.report(h,a['id'],generation=1,summary='Cannot claim completion',outcome='completed')
    result=s.report(h,a['id'],generation=1,summary='Source changed; no research edits made',outcome=outcome)
    assert result['source_current'] is False and result['source_reason']
    assert result['awaiting_human_review'] and not result['host_terminal_success_verified']
    assert crm.get('tasks',data['task_id'])==before
    assert [r['kind'] for r in s.get(a['id'])['receipts']]==['report']
    assert ResearchStore(crm).list('evidence',data['target_kind'],t['id'])['total']==0

@pytest.mark.parametrize('case',['completed','missing_next','still_enabled','wrong_state','mismatch','missing_job','duplicate','list_lost','pause_lost','concurrent_change'])
def test_cancel_observes_exact_inactive_job_before_pause(setup,case):
    h,a=prepare(setup);s=setup[1];h.identity=None
    job=h.jobs[a['job_id']]
    job.update(state='completed',enabled=False,next_run_at=None,repeat='1/1')
    if case=='missing_next':job.pop('next_run_at')
    if case=='still_enabled':job['enabled']=True
    if case=='wrong_state':job['state']='unknown'
    if case=='mismatch':job['enabled_toolsets']=['terminal']
    if case=='missing_job':h.jobs.clear()
    def after(args,result):
        if args['action']=='list':
            if case=='duplicate':result['jobs']*=2
            if case=='list_lost':raise RuntimeError('lost list')
            if case=='concurrent_change':
                with s.crm.engine.begin() as conn:
                    conn.execute(assignments.update().where(assignments.c.id==a['id']).values(version=999,reason='newer_observation'))
        if args['action']=='pause' and case=='pause_lost':raise RuntimeError('lost pause')
    h.after=after
    # Force a pause for the lost-response case rather than completed shortcut.
    if case=='pause_lost':job['state']='scheduled'
    before=len(h.calls)
    saved=s.cancel(h,a['id'],expected_version=a['version'])
    actions=[call[0]['action'] for call in h.calls[before:]]
    assert saved['state']=='cancelled'
    assert actions[0]=='list'
    if case=='completed':
        assert actions==['list']
        assert saved['reason']=='future_schedule_already_inactive_running_execution_not_stopped'
    elif case=='concurrent_change':
        assert actions==['list'] and saved['reason']=='newer_observation'
    elif case in ('mismatch','missing_job','duplicate','list_lost'):
        assert actions==['list'] and saved['reason']=='locally_invalidated_host_pause_unconfirmed'
    else:
        assert actions==['list','pause']
        assert saved['reason']==('locally_invalidated_host_pause_unconfirmed' if case=='pause_lost'
            else 'future_pause_observed_running_execution_not_stopped')
    h.identity=SimpleNamespace(job_id=a['job_id'],job_name=a['job_name'],execution_id='late',
        source='builtin',profile='synthetic',scheduled_instant=a['payload']['run_at'],started_at=a['payload']['run_at'])
    with pytest.raises(CRMError):s.run_get(h,a['id'],generation=1)
