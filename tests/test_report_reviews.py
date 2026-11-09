"""Synthetic-only acknowledgement contracts, shared with disposable PostgreSQL."""
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import event, inspect, select, update
from hermes_crm.domain import CRM, CRMError
from hermes_crm.companies import CompanyStore
from hermes_crm.native_work import NativeWorkStore
from hermes_crm.scheduled_research import ScheduledResearchStore
from hermes_crm.report_reviews import ReportReviewStore, digest
from hermes_crm.report_review_schema import TABLES, events, operations
from hermes_crm.coverage import coverage_report
from test_native_work import Host, identity

@pytest.fixture(params=['native','scheduled_research','scheduled_company'])
def setup(tmp_path,request):
    crm=CRM(f'sqlite:///{tmp_path}/review.db',profile='synthetic')
    yield make_setup(crm,request.param)
    crm.close()


def make_setup(crm,kind):
    task=crm.create('tasks',{'title':'Synthetic review source','due_at':'2030-05-01T00:00:00Z'})
    host=Host();target=None
    if kind=='native':
        source=NativeWorkStore(crm)
        a=source.create(task_id=task['id'],human_owner='Not a reviewer',prompt='Internal analysis',
            success_criteria='Report useful findings',run_at='2030-04-01T12:30:41+00:00',idempotency_key='create')
    else:
        family='companies' if kind=='scheduled_company' else 'contacts'
        target=CompanyStore(crm).create({'name':'Synthetic','notes':'PRIVATE SOURCE NOTES'},actor='test',key='target') if family=='companies' else crm.create('contacts',{'name':'Synthetic','notes':'PRIVATE SOURCE NOTES'})
        source=ScheduledResearchStore(crm)
        a=source.create(dict(task_id=task['id'],task_version=1,human_owner='Not a reviewer',
            target_kind=family,target_id=target['id'],target_version=1,public_question='Public products?',
            run_at='2030-04-01T12:30:41+00:00',research='web',propose_note=False,max_sources=2),idempotency_key='create')
    a=source.schedule(host,a['id'])
    identity(host,a)
    source.report(host,a['id'],generation=1,summary='Synthetic claimed result',outcome='blocked')
    a=source.get(a['id'])
    rid=a['reports'][0]['id'] if kind=='native' else next(r['operation_key'] for r in a['receipts'] if r['kind']=='report')
    return dict(crm=crm,source=source,host=host,assignment=a,task=task,target=target,
                family='native' if kind=='native' else 'scheduled_research',report_id=rid,store=ReportReviewStore(crm))


def get(s): return s['store'].get(s['family'],s['assignment']['id'],s['report_id'])
def body(preview,stale=False): return dict(context_digest=preview['context_digest'],expected_review_version=preview['review']['version'],acknowledge_stale=stale)
def write(s,action='acknowledge',key='ack',data=None):
    return s['store'].write(s['family'],s['assignment']['id'],s['report_id'],action,data if data is not None else body(get(s)),key=key)


def test_acknowledge_revoke_and_historical_retry_no_side_effects(setup):
    s=setup;crm=s['crm'];before=s['source'].get(s['assignment']['id']);calls=copy.deepcopy(s['host'].calls)
    names=set(inspect(crm.engine).get_table_names());preview=get(s)
    assert get(s)==preview and set(inspect(crm.engine).get_table_names())==names
    assert not {t.name for t in TABLES}&names
    assert preview['review']==dict(status='awaiting_review',version=0,latest_event=None,history=[],history_total=0,history_truncated=False)
    assert preview['context']['source_current'] is True and 'PRIVATE SOURCE NOTES' not in json.dumps(preview)
    request=body(preview);receipt=write(s,data=request)
    assert receipt['review']==dict(status='reviewed_in_crm',version=1)
    assert receipt['event']['actor']=='desktop' and receipt['event']['context']==preview['context']
    assert write(s,data=request)==receipt
    with pytest.raises(CRMError,match='different data'):write(s,data={**request,'acknowledge_stale':True})
    reviewed=get(s);assert reviewed['review']['status']=='reviewed_in_crm'
    undo=write(s,'revoke','undo',body(reviewed))
    assert undo['review']==dict(status='awaiting_review',version=2)
    assert write(s,data=request)==receipt  # historical success never undoes a later revocation
    assert get(s)['review']['status']=='awaiting_review'
    write(s,key='again')
    assert [e['action'] for e in get(s)['review']['history']]==['acknowledge','revoke','acknowledge']
    assert crm.get('tasks',s['task']['id'])==s['task'] and s['host'].calls==calls
    after=s['source'].get(s['assignment']['id'])
    assert after['state']==before['state'] and after['version']==before['version']
    if s['family']=='native':
        assert after['host_terminal_success_verified'] is False
        assert after['reports'][0]['review']['status']=='reviewed_in_crm'
        assert after['reports'][0]['summary']==before['reports'][0]['summary']
        row=next(r for r in coverage_report(crm)['items'] if r['assignment'])
        assert 'awaiting_review' not in row['risk_flags'] and 'reported_blocked_failed' in row['risk_flags']
    else:
        assert [r['result'] for r in before['receipts']]==[r['result'] for r in after['receipts']]
        report=next(r for r in after['receipts'] if r['kind']=='report')
        assert report['result']['awaiting_human_review'] is True and report['review']['status']=='reviewed_in_crm'


def test_source_changes_need_fresh_explicit_context_and_retry_is_historical(setup):
    s=setup;crm=s['crm'];preview=get(s);request=body(preview)
    receipt=write(s,data=request)
    task=crm.update('tasks',s['task']['id'],{'version':1,'status':'done'})
    assert write(s,data=request)==receipt
    with pytest.raises(CRMError,match='context changed'):write(s,'revoke','stale',body(preview))
    current=get(s)
    assert not current['context']['source_current'] and current['review']['status']=='reviewed_in_crm'
    with pytest.raises(CRMError,match='Explicit'):write(s,'revoke','needs-warning',body(current))
    write(s,'revoke','undo',body(current,True))
    current=get(s);write(s,key='historical',data=body(current,True))
    assert get(s)['review']['status']=='reviewed_in_crm'
    crm.update('tasks',task['id'],{'version':task['version'],'status':'open'})
    assert not get(s)['context']['source_current']


def test_stale_target_requires_explicit_warning(setup):
    s=setup
    if s['family']=='native':return
    before=get(s);target=s['target']
    if s['assignment']['payload']['target_kind']=='companies':
        CompanyStore(s['crm']).archive(target['id'],expected_version=1,actor='test',key='archive')
    else:s['crm'].update('contacts',target['id'],{'version':1,'name':'Changed'})
    with pytest.raises(CRMError,match='context changed'):write(s,data=body(before))
    current=get(s)
    assert not current['context']['source_current'] and current['context']['source_reason']=='research_target_changed_or_archived'
    with pytest.raises(CRMError,match='Explicit'):write(s,data=body(current))
    write(s,data=body(current,True))
    assert get(s)['review']['status']=='reviewed_in_crm'


def test_concurrent_duplicate_and_conflicting_writes(setup):
    s=setup;request=body(get(s))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:write(s,data=request),range(4)))
    assert results==[results[0]]*4 and get(s)['review']['version']==1
    undo=body(get(s))
    def attempt(i):
        try:return write(s,'revoke','undo-'+str(i),undo)
        except CRMError as e:return e.status
    with ThreadPoolExecutor(max_workers=3) as pool: results=list(pool.map(attempt,range(3)))
    assert sum(isinstance(r,dict) for r in results)==1 and results.count(409)==2
    assert get(s)['review']['version']==2


def test_receipt_failure_rolls_back_event(setup):
    s=setup;request=body(get(s))
    def fail(conn,cursor,statement,parameters,context,executemany):
        compiled=getattr(context,'compiled',None)
        sql=getattr(compiled,'statement',None)
        if getattr(sql,'is_insert',False) and getattr(sql,'table',None) is operations:raise RuntimeError('synthetic receipt failure')
    event.listen(s['crm'].engine,'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError,match='synthetic'):write(s,data=request)
    finally:event.remove(s['crm'].engine,'before_cursor_execute',fail)
    assert get(s)['review']['version']==0
    assert write(s,data=request)['review']['version']==1


def test_report_tamper_and_cross_scope_fail_closed(setup):
    s=setup;write(s)
    if s['family']=='native':
        from hermes_crm.native_work import reports
        with s['crm'].engine.begin() as c:c.execute(update(reports).where(reports.c.id==s['report_id']).values(summary='tampered'))
    else:
        from hermes_crm.scheduled_research import operations as source_ops
        with s['crm'].engine.begin() as c:
            row=c.execute(select(source_ops).where(source_ops.c.key==s['report_id'])).mappings().one()
            value=json.loads(row['response']);value['summary']='tampered'
            c.execute(update(source_ops).where(source_ops.c.key==s['report_id']).values(response=json.dumps(value)))
    with pytest.raises(CRMError):get(s)


def test_partial_and_newer_schema_fail_without_repair(setup):
    s=setup;write(s)
    with s['crm'].engine.begin() as c:operations.drop(c)
    with pytest.raises(CRMError,match='incomplete'):get(s)
    with pytest.raises(CRMError,match='incomplete'):write(s,key='repair')
    assert operations.name not in inspect(s['crm'].engine).get_table_names()


def test_native_new_report_remains_unacknowledged(setup):
    s=setup
    if s['family']!='native':return
    write(s)
    identity(s['host'],s['assignment'],execution_id='execution-2')
    s['source'].report(s['host'],s['assignment']['id'],generation=1,summary='New report')
    row=next(r for r in coverage_report(s['crm'])['items'] if r['assignment'])
    assert 'awaiting_review' in row['risk_flags']
    reports=s['source'].get(s['assignment']['id'])['reports']
    assert [r['review']['status'] for r in reports]==['reviewed_in_crm','awaiting_review']


def test_history_is_bounded_but_ledger_is_complete(setup):
    s=setup
    for index in range(52):
        write(s,'acknowledge' if index%2==0 else 'revoke','history-'+str(index))
    review=get(s)['review']
    assert len(review['history'])==50 and review['history_total']==52 and review['history_truncated'] is True
    assert review['history'][0]['version']==3 and review['latest_event']['version']==52
    with s['crm'].engine.connect() as c:assert len(c.execute(select(events)).all())==52


@pytest.mark.parametrize('field,value',[('expected_review_version',True),('expected_review_version',-1),('context_digest','wrong'),('acknowledge_stale','true'),('actor','named-owner')])
def test_strict_store_request(setup,field,value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):write(setup,data={**body(get(setup)),field:value})
    assert get(setup)['review']['version']==0


def test_wrong_report_identity_and_assignment_context(setup):
    s=setup;preview=get(s)
    with pytest.raises(CRMError):s['store'].get(s['family'],s['assignment']['id'],'00000000-0000-0000-0000-000000000000')
    if s['family']=='native':
        from hermes_crm.native_work import assignments as source_assignments
    else:
        from hermes_crm.scheduled_research import assignments as source_assignments
    with s['crm'].engine.begin() as c:
        c.execute(update(source_assignments).where(source_assignments.c.id==s['assignment']['id']).values(version=source_assignments.c.version+1))
    with pytest.raises(CRMError,match='context changed'):write(s,data=body(preview))
    assert get(s)['review']['version']==0


def incompatible_column_sql(dialect, schema):
    preparer = dialect.identifier_preparer
    table = preparer.format_table(events, use_schema=False)
    if schema is not None:
        table = preparer.quote_schema(schema) + '.' + table
    return 'ALTER TABLE ' + table + ' ADD COLUMN future_contract TEXT'


def test_full_schema_incompatible_column_rejected(setup):
    s=setup;write(s)
    with s['crm'].engine.begin() as c:
        schema = (c.get_execution_options().get('schema_translate_map') or {}).get(None)
        c.exec_driver_sql(incompatible_column_sql(c.dialect, schema))
    with pytest.raises(CRMError,match='incompatible'):get(s)
    with pytest.raises(CRMError,match='incompatible'):write(s,key='no-repair')


def test_same_workspace_other_profile_cannot_read_receipt(setup):
    s=setup;write(s);crm=s['crm'];original=crm.profile
    crm.profile='foreign'
    try:
        with pytest.raises(CRMError):get(s)
        with pytest.raises(CRMError):write(s,key='foreign')
    finally:crm.profile=original
    assert get(s)['review']['version']==1


def test_uninitialized_read_never_creates_workspace_or_review_tables(tmp_path):
    crm=CRM(f'sqlite:///{tmp_path}/empty.db',profile='synthetic')
    before=inspect(crm.engine).get_table_names()
    try:
        assert crm.existing_workspace_token() is None
        with pytest.raises(CRMError):ReportReviewStore(crm).get('native','00000000-0000-0000-0000-000000000000','00000000-0000-0000-0000-000000000000')
        assert crm.existing_workspace_token() is None and inspect(crm.engine).get_table_names()==before
    finally:crm.close()


def test_review_queries_are_batched_for_history_and_coverage(setup):
    s=setup;write(s)
    counts=[]
    def count(conn,cursor,statement,parameters,context,executemany):
        from sqlalchemy.sql import visitors
        sql=getattr(getattr(context,'compiled',None),'statement',None)
        if sql is not None and getattr(sql,'is_select',False):
            used={id(node) for node in visitors.iterate(sql)}
            if id(events) in used or id(operations) in used:counts.append(sql)
    event.listen(s['crm'].engine,'before_cursor_execute',count)
    try:
        s['source'].page(task_id=s['task']['id'])
        assert len(counts)==2
        if s['family']=='native':
            counts.clear();coverage_report(s['crm']);assert len(counts)==2
    finally:event.remove(s['crm'].engine,'before_cursor_execute',count)


@pytest.mark.parametrize('reason',['cancelled','superseded'])
@pytest.mark.parametrize('review_before',[False,True])
def test_invalidated_native_report_remains_reviewable(setup,reason,review_before,tmp_path):
    s=setup
    if s['family']!='native':return
    from hermes_crm.protection import Keyring
    from hermes_crm.recovery import restore_content
    from test_recovery import artifact
    if review_before:write(s)
    original=get(s)
    source=s['source'].get(s['assignment']['id'])
    s['source'].invalidate(source['id'],version=source['version'],reason=reason)
    preview=get(s)
    assert preview['generation']==1 and preview['context']['assignment_state']==reason
    assert preview['context']['assignment_version']>original['context']['assignment_version']
    assert preview['report_digest']==original['report_digest']
    with pytest.raises(CRMError,match='context changed'):
        write(s,'revoke' if review_before else 'acknowledge','old-context',body(original))
    if review_before:write(s,'revoke','undo')
    write(s,key='historical')
    assert s['source'].get(source['id'])['generation']==2
    assert get(s)['review']['status']=='reviewed_in_crm'
    assert next(r for r in coverage_report(s['crm'])['items'] if r['assignment'])['assignment']['latest_report']['review_status']=='reviewed_in_crm'
    ring=Keyring('test',{'test':b'e'*32})
    result=restore_content(artifact(s['crm'],ring),backup_ring=ring,workspace=s['crm'].workspace_token(),
        profile=s['crm'].profile,target=tmp_path/'invalidated-recovery')
    assert events.name in result['quarantined_tables']


def test_cancel_after_report_then_review_and_export(setup,tmp_path):
    s=setup
    if s['family']!='native':return
    from hermes_crm.protection import Keyring
    from hermes_crm.recovery import restore_content
    from test_recovery import artifact
    write(s)
    s['host'].identity=None
    row=s['source'].get(s['assignment']['id'])
    s['source'].cancel(s['host'],row['id'],version=row['version'])
    write(s,'revoke','after-cancel');write(s,key='review-history')
    assert get(s)['context']['assignment_state']=='cancelled'
    ring=Keyring('test',{'test':b'e'*32})
    result=restore_content(artifact(s['crm'],ring),backup_ring=ring,workspace=s['crm'].workspace_token(),profile=s['crm'].profile,target=tmp_path/'cancelled-recovery')
    assert events.name in result['quarantined_tables']
