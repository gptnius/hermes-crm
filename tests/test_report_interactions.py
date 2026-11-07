from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select
from hermes_crm.domain import CRM, CRMError, contacts
from hermes_crm.report_interactions import InteractionStore, last_contact_expression

@pytest.fixture
def crm(tmp_path):
    c=CRM(f'sqlite:///{tmp_path}/ledger.db')
    yield c
    c.close()

def data(contact, **extra):
    return dict(contact_id=contact['id'],happened_at='2020-02-03T04:05:00+02:00',kind='email',summary='I recall discussing the proposal.',**extra)

def last(crm):
    with crm.engine.connect() as conn:
        return conn.execute(select(last_contact_expression(crm,conn)).select_from(contacts)).scalar()

def test_lazy_reads_and_authored_claim(crm):
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    assert s.list(contact['id'])['items']==[] and last(crm) is None
    assert 'crm_report_interactions' not in inspect(crm.engine).get_table_names()
    r=s.create(data(contact),1,'local-user','create')
    assert r['provenance']=='self_reported' and r['actor']=='local-user'
    assert r['happened_at']=='2020-02-03T02:05:00.000000+00:00'
    assert 'delivered' not in r and last(crm)==r['happened_at']
    assert s.create(data(contact),1,'local-user','create')==r

def test_contact_change_rejects_and_void_preserves_evidence(crm):
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    crm.update('contacts',contact['id'],{'version':1,'name':'Renamed'})
    with pytest.raises(CRMError,match='Contact changed'): s.create(data(contact),1,'user','old')
    r=s.create(data(contact),2,'user','new')
    voided=s.void(r['id'],1,'Wrong contact','user','void')
    assert voided['summary']==r['summary'] and voided['happened_at']==r['happened_at']
    assert voided['version']==2 and voided['void_reason']=='Wrong contact'
    assert s.void(r['id'],1,'Wrong contact','user','void')==voided
    with pytest.raises(CRMError): s.void(r['id'],1,'Again','user','again')
    assert s.list(contact['id'])['total']==0 and s.list(contact['id'],include_voided=True)['total']==1
    assert last(crm) is None

def test_future_naive_and_spoofed_actor_rejected(crm):
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    for change in [dict(happened_at='2020-01-01T12:00:00'),dict(happened_at=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()),dict(actor='forged'),dict(provenance='verified'),dict(summary=' '),dict(kind='sent')]:
        values=data(contact); values.update(change)
        with pytest.raises(ValidationError): s.create(values,1,'user','bad')
    assert 'crm_report_interactions' not in inspect(crm.engine).get_table_names()

def test_profile_isolation_and_pagination(crm):
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    for n in range(3): s.create(data(contact),1,'user',str(n))
    assert len(s.list(contact['id'],limit=2)['items'])==2
    assert len(s.list(contact['id'],limit=2,offset=2)['items'])==1
    other=CRM(crm.url,profile='another')
    try:
        assert InteractionStore(other).list(contact['id'])['total']==0
        assert last(other) is None
    finally: other.close()

def test_report_does_not_expose_summary(crm):
    from hermes_crm.reports import ReportEngine
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    r=s.create(data(contact),1,'user','new')
    result=ReportEngine(crm).run({'entity':'contacts','columns':['id','last_logged_contact_at']})
    assert r['summary'] not in str(result)
    assert r['happened_at'] in str(result)

def test_latest_active_and_idempotency_conflict(crm):
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    old=s.create(data(contact),1,'user','old')
    values=data(contact); values['happened_at']='2021-01-01T00:00:00Z'
    newer=s.create(values,1,'user','new')
    assert last(crm)==newer['happened_at']
    with pytest.raises(CRMError,match='different'): s.create(values,1,'other','new')
    s.void(newer['id'],1,'Correction','user','void')
    assert last(crm)==old['happened_at']
    with pytest.raises(CRMError,match='different'): s.void(newer['id'],1,'Different reason','user','void')

def test_concurrent_claim_retries_insert_once(crm):
    from concurrent.futures import ThreadPoolExecutor
    contact=crm.create('contacts',{'name':'Someone'}); s=InteractionStore(crm)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda _:s.create(data(contact),1,'user','same'),range(4)))
    assert all(row==rows[0] for row in rows)
    assert s.list(contact['id'])['total']==1

def test_partial_schema_refused_by_report_read(crm):
    from sqlalchemy import text
    from hermes_crm.reports import ReportEngine
    crm.create('contacts',{'name':'Someone'})
    with crm.engine.begin() as conn: conn.execute(text('CREATE TABLE crm_report_interactions (id TEXT PRIMARY KEY)'))
    with pytest.raises(CRMError,match='incomplete'):
        ReportEngine(crm).run({'entity':'contacts','columns':['last_logged_contact_at']})
    assert 'crm_interaction_operations' not in inspect(crm.engine).get_table_names()
