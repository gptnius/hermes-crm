"""Encrypted evidence retention and quarantined recovery, never host activation."""
import copy
import json
import sqlite3
import pytest
from sqlalchemy import select
from hermes_crm.domain import CRMError
from hermes_crm.protection import ProtectionStore, Keyring, decrypt_export, seal, canonical
from hermes_crm.recovery import restore_content
from hermes_crm.report_review_schema import TABLES,events,operations
from hermes_crm.report_reviews import digest
from test_report_reviews import setup,write,get,body
from test_recovery import artifact


def test_export_recovery_quarantines_reviews(setup,tmp_path):
    s=setup;crm=s['crm'];ring=Keyring('test',{'test':b'e'*32})
    write(s);write(s,'revoke','undo');write(s,key='again')
    source=ProtectionStore(crm)
    value=decrypt_export(source.export(ring),ring,workspace=source.workspace,profile=crm.profile)
    assert len(value['tables'][events.name])==3 and len(value['tables'][operations.name])==3
    target=tmp_path/'restored'
    result=restore_content(artifact(crm,ring),backup_ring=ring,workspace=source.workspace,profile=crm.profile,target=target)
    assert {t.name for t in TABLES}<=set(result['quarantined_tables'])
    with sqlite3.connect(target/'recovery.sqlite3') as c:
        for t in TABLES:
            assert c.execute('SELECT COUNT(*) FROM '+t.name).fetchone()==(0,)
            assert c.execute('SELECT COUNT(*) FROM recovery_'+t.name).fetchone()==(3,)
    assert get(s)['review']['status']=='reviewed_in_crm'


def test_mixed_scope_export_filters_review_rows(setup):
    s=setup;crm=s['crm'];write(s)
    with crm.engine.begin() as c:
        for t in TABLES:
            row=dict(c.execute(select(t)).mappings().first());row['scope']='f'*64
            c.execute(t.insert().values(**row))
    ring=Keyring('test',{'test':b'e'*32});store=ProtectionStore(crm)
    value=decrypt_export(store.export(ring),ring,workspace=store.workspace,profile=crm.profile)
    assert all(len(value['tables'][t.name])==1 for t in TABLES)
    assert get(s)['review']['version']==1


@pytest.mark.parametrize('damage',['missing_family','missing_report','wrong_context','wrong_binding','wrong_receipt','extra_field','sequence','scope'])
def test_malformed_review_export_rejected(setup,damage):
    s=setup;crm=s['crm'];write(s)
    ring=Keyring('test',{'test':b'e'*32});store=ProtectionStore(crm)
    value=decrypt_export(store.export(ring),ring,workspace=store.workspace,profile=crm.profile)
    tables=value['tables'];e=tables[events.name][0];op=tables[operations.name][0]
    if damage=='missing_family':del tables[operations.name]
    elif damage=='missing_report':tables['crm_native_work_reports' if s['family']=='native' else 'crm_scheduled_research_ops_v1']=[]
    elif damage=='wrong_context':
        v=json.loads(e['context']);v['source_current']=False;e['context']=json.dumps(v)
    elif damage=='wrong_binding':
        # Even a self-consistent forged ledger cannot bind to an unrelated source.
        v=json.loads(e['context']);v['report']['assignment_digest']='a'*64;e['context']=json.dumps(v);e['context_digest']=digest(v)
        response=json.loads(op['response']);response['event']['context']=v;response['event']['context_digest']=digest(v);op['response']=json.dumps(response)
        request=json.loads(op['request']);request['context_digest']=digest(v);op['request']=json.dumps(request);op['digest']=digest(request)
    elif damage=='wrong_receipt':op['response']='{}'
    elif damage=='extra_field':e['unexpected']='new contract'
    elif damage=='sequence':e['version']=2
    elif damage=='scope':e['scope']='f'*64
    envelope=seal(canonical(value),ring,'backup',dict(workspace=store.workspace,profile=crm.profile))
    with pytest.raises(CRMError):decrypt_export(envelope,ring,workspace=store.workspace,profile=crm.profile)
