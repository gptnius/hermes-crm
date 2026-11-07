from concurrent.futures import ThreadPoolExecutor
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from hermes_crm.domain import CRM, CRMError, settings
from hermes_crm.report_store import ReportStore

@pytest.fixture
def crm(tmp_path):
    c = CRM(f'sqlite:///{tmp_path}/reports.db')
    yield c
    c.close()

def definition(): return {'entity':'contacts','columns':['id','name']}
def card(report, visual='table'):
    return dict(id=str(uuid.uuid4()),report_id=report['id'],report_version=report['version'],visualization=visual)

def test_reads_are_lazy(crm):
    s=ReportStore(crm)
    before=inspect(crm.engine).get_table_names()
    assert s.list()['items']==[]
    assert s.get_dashboard()['version']==0
    with pytest.raises(CRMError): s.get(str(uuid.uuid4()))
    assert inspect(crm.engine).get_table_names()==before
    with crm.engine.connect() as c:
        assert c.execute(select(settings.c.value).where(settings.c.key=='workspace_id')).scalar() is None

def test_versions_and_lost_reply_idempotency(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new')
    assert s.create('People',definition(),'new')==r
    with pytest.raises(CRMError,match='different'): s.create('Other',definition(),'new')
    changed=s.update(r['id'],'Renamed',definition(),1,'edit')
    assert changed['version']==2
    assert s.update(r['id'],'Renamed',definition(),1,'edit')==changed
    with pytest.raises(CRMError,match='changed'): s.update(r['id'],'Lost edit',definition(),1,'other')
    assert s.get(r['id'],1)==r
    assert s.get(r['id'])==changed

def test_archive_dashboard_keeps_pinned_meaning(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new'); c=card(r)
    d=s.save_dashboard([c],0,'dashboard')
    assert s.save_dashboard([c],0,'dashboard')==d
    s.update(r['id'],'Changed',{'entity':'deals'},1,'edit')
    pinned=s.get_dashboard()['cards'][0]
    assert pinned['reference_status']=='outdated'
    assert pinned['report']['definition']['entity']=='contacts'
    s.archive(r['id'],2,'archive')
    assert s.get_dashboard()['cards'][0]['reference_status']=='archived'
    assert s.list()['items']==[]
    assert s.list(include_archived=True)['total']==1
    s.save_dashboard([c],1,'resave')
    s.restore(r['id'],3,'restore')
    assert s.get(r['id'])['archived_at'] is None

def test_dashboard_refresh_is_explicit_and_conflicts(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new'); c=card(r)
    s.save_dashboard([c],0,'dashboard')
    newer=s.update(r['id'],'New',definition(),1,'edit')
    with pytest.raises(CRMError,match='changed'): s.save_dashboard([],0,'lost')
    c['report_version']=newer['version']
    s.save_dashboard([c],1,'adopt')
    assert s.get_dashboard()['cards'][0]['reference_status']=='active'
    with pytest.raises(ValidationError): s.save_dashboard([c,c],2,'duplicates')
    with pytest.raises(CRMError): s.save_dashboard([dict(c,report_version=900)],2,'missing')

def test_profile_isolation(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'same'); s.save_dashboard([card(r)],0,'dash')
    other=CRM(crm.url,profile='other')
    try:
        second=ReportStore(other)
        assert second.list()['total']==0 and second.get_dashboard()['cards']==[]
        with pytest.raises(CRMError): second.get(r['id'])
        assert second.create('Other',definition(),'same')['id']!=r['id']
    finally: other.close()

def test_concurrent_saves_one_winner(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new')
    def edit(i):
        try: return s.update(r['id'],str(i),definition(),1,f'edit{i}')
        except CRMError as e: return e.status
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(edit,range(4)))
    assert sum(isinstance(x,dict) for x in results)==1
    assert results.count(409)==3

def test_concurrent_create_same_key(crm):
    s=ReportStore(crm)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:s.create('People',definition(),'same'),range(4)))
    assert all(r==results[0] for r in results)
    assert s.list()['total']==1

def test_partial_schema_not_repaired(crm):
    with crm.engine.begin() as c: c.execute(text('CREATE TABLE crm_saved_reports (id TEXT PRIMARY KEY)'))
    with pytest.raises(CRMError,match='incomplete'): ReportStore(crm).create('People',definition(),'new')
    assert 'crm_saved_dashboards' not in inspect(crm.engine).get_table_names()

def test_chart_validation(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new')
    with pytest.raises(CRMError,match='measure'): s.save_dashboard([card(r,'metric')],0,'metric')
    grouped=s.create('Groups',{'entity':'contacts','group_by':{'field':'company'},'measure':{'op':'count'}},'groups')
    with pytest.raises(CRMError,match='date'): s.save_dashboard([card(grouped,'line')],0,'line')
    assert s.save_dashboard([card(grouped,'bar')],0,'bar')['version']==1

def test_bad_definition_and_title_do_not_initialize(crm):
    with pytest.raises(ValidationError): ReportStore(crm).create('a'*161,definition(),'new')
    with pytest.raises(ValidationError): ReportStore(crm).create('People',{'entity':'contacts','columns':['notes']},'new')
    assert 'crm_saved_reports' not in inspect(crm.engine).get_table_names()

def test_missing_reference_retained_and_new_missing_rejected(crm):
    from hermes_crm.report_store import reports, revisions
    s=ReportStore(crm); r=s.create('People',definition(),'new'); c=card(r)
    s.save_dashboard([c],0,'dashboard')
    with crm.engine.begin() as conn:
        conn.execute(reports.delete().where(reports.c.id==r['id']))
        conn.execute(revisions.delete().where(revisions.c.id==r['id']))
    loaded=s.get_dashboard()
    assert loaded['cards'][0]['reference_status']=='missing'
    s.save_dashboard([c],1,'preserve')
    assert s.get_dashboard()['cards'][0]['id']==c['id']
    with pytest.raises(CRMError): s.save_dashboard([dict(c,report_id=str(uuid.uuid4()))],2,'new-broken')

def test_schema_column_mismatch_not_repaired(crm):
    s=ReportStore(crm); s.create('People',definition(),'new')
    with crm.engine.begin() as c: c.execute(text('ALTER TABLE crm_saved_dashboards ADD COLUMN surprise TEXT'))
    with pytest.raises(CRMError,match='incompatible'): s.get_dashboard()

def test_dashboard_card_limit_uuid_and_versions(crm):
    s=ReportStore(crm); r=s.create('People',definition(),'new')
    for cards in [[card(r) for _ in range(13)], [dict(card(r),id='not-uuid')], [dict(card(r),report_version=True)]]:
        with pytest.raises(ValidationError): s.save_dashboard(cards,0,'bad')
    with pytest.raises(CRMError): s.save_dashboard([],True,'boolean')

def test_independent_connections_same_key_and_dashboard_conflict(crm):
    second=CRM(crm.url)
    try:
        stores=[ReportStore(crm),ReportStore(second)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda s:s.create('People',definition(),'shared'),stores))
        assert results[0]==results[1]
        def save(s):
            try: return s.save_dashboard([],0,'dashboard-'+str(id(s)))
            except CRMError as e: return e.status
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(save,stores))
        assert sum(isinstance(x,dict) for x in results)==1 and results.count(409)==1
    finally: second.close()
