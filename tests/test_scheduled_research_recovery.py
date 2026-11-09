"""Encrypted content export/recovery retains evidence but no scheduler authority."""
import json
import sqlite3
import pytest
from sqlalchemy import select,update,text
from hermes_crm.domain import CRM,CRMError
from hermes_crm.protection import ProtectionStore,Keyring,decrypt_export
from hermes_crm.recovery import restore_content
from hermes_crm.scheduled_research import ScheduledResearchStore,assignments,operations,digest
from test_scheduled_research import setup,prepare,packet
from test_recovery import artifact

FAMILY={'crm_scheduled_research_v1','crm_scheduled_research_ops_v1'}
@pytest.fixture
def ring():return Keyring('test-export',{'test-export':b'e'*32})

def finished(setup):
    crm,s,t,data=setup;h,a=prepare(setup)
    e=s.evidence(h,a['id'],generation=1,operation_id='e',data=packet(setup))
    p=s.propose(h,a['id'],generation=1,operation_id='p',data=dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Synthetic claim (https://example.com/products).'))
    s.report(h,a['id'],generation=1,summary='Synthetic proposal ready')
    return h,a,e,p

def test_export_recovery_quarantines_scheduled_authority(setup,ring,tmp_path):
    crm,s,t,data=setup;h,a,e,p=finished(setup)
    before=s.get(a['id']);calls=len(h.calls)
    artifact_bytes=artifact(crm,ring)
    target=tmp_path/'recovered'
    result=restore_content(artifact_bytes,backup_ring=ring,workspace=crm.workspace_token(),profile=crm.profile,target=target)
    assert FAMILY <= set(result['quarantined_tables'])
    assert result['content_restored'] and not result['live_restore']
    with sqlite3.connect(target/'recovery.sqlite3') as c:
        for table in FAMILY:
            assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()==(0,)
        raw=c.execute('SELECT job_id,execution_id,state FROM recovery_crm_scheduled_research_v1').fetchone()
        assert raw==(before['job_id'],before['execution_id'],'result_reported')
        assert c.execute('SELECT COUNT(*) FROM recovery_crm_scheduled_research_ops_v1').fetchone()==(4,)
        assert c.execute('SELECT status FROM crm_research_proposals WHERE id=?',(p['id'],)).fetchone()==('pending',)
    recovered=CRM('sqlite:///'+str(target/'recovery.sqlite3'),profile=crm.profile)
    try:
        assert ScheduledResearchStore(recovered,initialize=False).list(task_id=data['task_id'])==[]
        with pytest.raises(CRMError):ScheduledResearchStore(recovered,initialize=False).get(a['id'])
        assert recovered.get('tasks',data['task_id'])['status']=='open'
    finally:recovered.close()
    assert s.get(a['id'])==before and len(h.calls)==calls

@pytest.mark.parametrize('damage',['partial','scope','payload','missing_task','missing_target','missing_assignment','missing_evidence','missing_proposal','report_identity','report_source_status','create_digest','excess_source_count'])
def test_corrupted_family_refused_before_recovery_target(setup,ring,tmp_path,damage):
    crm,s,t,data=setup;finished(setup)
    def change(v):
        a=v['tables']['crm_scheduled_research_v1'][0]
        ops=v['tables']['crm_scheduled_research_ops_v1']
        if damage=='partial':v['tables'].pop('crm_scheduled_research_ops_v1')
        elif damage=='scope':a['scope']='f'*64
        elif damage=='payload':a['payload']='{}'
        elif damage in ('missing_task','missing_target'):
            payload=json.loads(a['payload']);payload['task_id' if damage=='missing_task' else 'target_id']='00000000-0000-0000-0000-000000000001'
            a.update(payload=json.dumps(payload),digest=digest(payload))
        elif damage=='missing_assignment':ops[0]['assignment_id']='00000000-0000-0000-0000-000000000001'
        elif damage=='missing_evidence':v['tables']['crm_research_evidence']=[]
        elif damage=='missing_proposal':v['tables']['crm_research_proposals']=[]
        elif damage=='create_digest':next(o for o in ops if o['kind']=='create')['digest']='0'*64
        elif damage=='excess_source_count':
            op=dict(next(o for o in ops if o['kind']=='evidence'))
            for key in ('a','b'):ops.append(dict(op,key='run:'+key*64))
        else:
            op=next(o for o in ops if o['kind']=='report');r=json.loads(op['response'])
            if damage=='report_identity':r['identity']['execution_id']='foreign'
            else:r.update(source_current=False,source_reason='source_task_changed_or_closed')
            op['response']=json.dumps(r)
    data_bytes=artifact(crm,ring,change)
    target=tmp_path/'must-not-exist'
    with pytest.raises(CRMError):restore_content(data_bytes,backup_ring=ring,workspace=crm.workspace_token(),profile=crm.profile,target=target)
    assert not target.exists()

def test_export_filters_foreign_family_and_refuses_own_corruption(setup,ring):
    crm,s,t,data=setup;h,a=prepare(setup)
    with crm.engine.begin() as c:
        original=dict(c.execute(select(assignments).where(assignments.c.id==a['id'])).mappings().one())
        foreign=dict(original,scope='f'*64)
        c.execute(assignments.insert().values(**foreign))
    protection=ProtectionStore(crm)
    snapshot=decrypt_export(protection.export(ring),ring,workspace=protection.workspace,profile=crm.profile)
    assert len(snapshot['tables']['crm_scheduled_research_v1'])==1
    assert snapshot['tables']['crm_scheduled_research_v1'][0]['scope']==s.scope
    with crm.engine.begin() as c:
        c.execute(update(assignments).where(assignments.c.scope==s.scope).values(payload='{}'))
    with pytest.raises(CRMError):protection.export(ring)

def test_export_refuses_partial_storage(setup,ring):
    crm,s,t,data=setup;prepare(setup)
    with crm.engine.begin() as c:c.execute(text('DROP TABLE crm_scheduled_research_ops_v1'))
    with pytest.raises(CRMError,match='incomplete'):ProtectionStore(crm).export(ring)
