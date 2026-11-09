"""Shared SQLite/PostgreSQL report contracts, using synthetic fixtures only."""
import json
from datetime import datetime, timezone
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM, CRMError, contacts, deals, tasks
from hermes_crm import domain, native_api, plugin
from hermes_crm.web import create_app

@pytest.fixture
def crm():
    instance = CRM('sqlite:///:memory:')
    yield instance
    instance.close()


def populate(crm):
    a = crm.create('contacts', {'name':'Alpha', 'company':r'Literal %_\ Co','email':'a@example.com'})
    b = crm.create('contacts', {'name':'Beta','lifecycle':'customer'})
    c = crm.create('contacts', {'name':'Missing'})
    d = crm.create('deals', {'title':'First','contact_id':a['id'],'stage':'qualified','value':100})
    crm.create('deals', {'title':'Duplicate stage','contact_id':a['id'],'stage':'qualified','value':200})
    crm.create('deals', {'title':'Won','contact_id':a['id'],'stage':'won','value':0})
    crm.create('deals', {'title':'Customer lead stage','contact_id':b['id'],'stage':'lead'})
    crm.create('tasks', {'title':'Direct and indirect','contact_id':a['id'],'deal_id':d['id'],'due_at':'2000-01-01T00:00:00Z','priority':'high'})
    crm.create('tasks', {'title':'Indirect','deal_id':d['id'],'due_at':'2090-01-01T00:00:00Z'})
    crm.create('tasks', {'title':'Done only','contact_id':c['id'],'due_at':'2000-01-01T00:00:00Z','status':'done'})
    return a,b,c


def test_report_unique_aggregates_and_dashboard(crm):
    a,b,c = populate(crm)
    report = crm.contact_report(stage='qualified')
    assert report['total']==1
    row = report['items'][0]
    assert row['id']==a['id'] and row['deal_stages']==['qualified','won']
    assert row['deal_count']==3 and row['open_followup_count']==2 and row['overdue_followup_count']==1
    assert row['next_followup_at']=='2000-01-01T00:00:00.000000+00:00'
    assert crm.contact_report(followup='overdue')['total']==crm.contact_report(followup='upcoming')['total']==1
    missing = crm.contact_report(stage='unassigned')['items'][0]
    assert missing['id']==c['id'] and missing['next_followup_at'] is None and missing['deal_stages']==[]
    overview=crm.overview()
    for stage in overview['stages']:
        assert stage['contact_count']==crm.contact_report(stage=stage['stage'])['total']
    assert overview['lead_attention']=={'no_open_followup':1,'overdue_followup':1}
    for key,state in [('no_open_followup','missing'),('overdue_followup','overdue')]:
        assert overview['lead_attention'][key]==crm.contact_report(contact_type='lead',followup=state)['total']
    assert crm.contact_report(contact_type='customer',stage='lead')['items'][0]['id']==b['id']


def test_combined_literal_filters(crm):
    a,b,c=populate(crm)
    filters=dict(q='ALP',company='%_\\',stage='qualified',contact_type='lead',email='present',followup='overdue')
    assert [r['id'] for r in crm.contact_report(**filters)['items']]==[a['id']]
    assert [r['id'] for r in crm.list('contacts',**filters)]==[a['id']]
    assert crm.contact_report(q='%')['total']==1
    assert crm.contact_report(q="' OR 1=1 --")['total']==0
    assert len(crm.list('deals',company='%_\\',min_value=100,max_value=100,stage='qualified'))==1
    assert len(crm.list('tasks',q='DIRECT',priority='high',due='overdue',status='open'))==1
    assert crm.list('tasks',status='done',due='overdue')==[]
    assert crm.contact_report(email='missing')['total']==2


def test_report_pages_beyond_500(crm):
    # Bulk fixtures keep the same timestamp to exercise deterministic ID tie-breaking.
    base=dict(version=1,created_at='2020-01-01T00:00:00.000000+00:00',updated_at='2020-01-01T00:00:00.000000+00:00',email='',company='Bulk',title='',lifecycle='lead',notes='')
    with crm.engine.begin() as conn:
        conn.execute(contacts.insert(),[dict(base,id=f'c{i:04}',name=f'Bulk {i}') for i in range(603)])
        conn.execute(deals.insert(),[dict(id=f'd{i:04}',version=1,created_at=base['created_at'],updated_at=base['updated_at'],title='Old match' if i==602 else 'Noise',contact_id=f'c{i:04}',value=i,currency='USD',stage='won' if i==602 else 'lead',probability=100,notes='') for i in range(603)])
        conn.execute(tasks.insert(),[dict(id=f't{i:04}',version=1,created_at=base['created_at'],updated_at=base['updated_at'],title='Old match' if i==602 else 'Noise',contact_id=f'c{i:04}',due_at='2090-01-01T00:00:00.000000+00:00',priority='high' if i==602 else 'normal',status='open',notes='',schedule_status='none') for i in range(603)])
    found=[]
    for offset in range(0,700,100):
        page=crm.contact_report(company='bulk',limit=100,offset=offset)
        assert page['total']==603 and page['limit']==100 and page['offset']==offset
        found.extend(r['id'] for r in page['items'])
    assert found==[f'c{i:04}' for i in range(603)]
    assert crm.contact_report(stage='won')['items'][0]['id']=='c0602'
    assert crm.list('contacts',stage='won')[0]['id']=='c0602'
    assert crm.list('deals',min_value=602)[0]['id']=='d0602'
    assert crm.list('tasks',priority='high',due='upcoming')[0]['id']=='t0602'


def test_report_timezone_edges(crm,monkeypatch):
    monkeypatch.setattr(domain,'now',lambda:'2026-11-06T12:00:00.000000+00:00')
    c=crm.create('contacts',{'name':'Boundary'})
    for due in ['2026-11-06T17:29:59.999999+05:30','2026-11-06T05:00:00-07:00','2026-11-06T12:00:00.000001Z']:
        crm.create('tasks',{'title':'Boundary','contact_id':c['id'],'due_at':due})
    row=crm.contact_report()['items'][0]
    assert row['overdue_followup_count']==1 and row['open_followup_count']==3
    assert len(crm.list('tasks',due='overdue'))==1 and len(crm.list('tasks',due='upcoming'))==2
    assert crm.overview()['overdue_tasks']==1


@pytest.mark.parametrize('filters',[{'limit':0},{'limit':101},{'limit':True},{'limit':2.0},{'offset':-1},{'offset':'1'}, {'q':None},{'company':True},{'stage':'customer'},{'contact_type':'won'},{'email':'yes'},{'email':None},{'followup':'done'},{'followup':None}])
def test_report_invalid_filters(crm,filters):
    with pytest.raises(CRMError): crm.contact_report(**filters)


@pytest.mark.parametrize('kind,filters',[('deals',{'min_value':True}),('deals',{'max_value':1.2}),('deals',{'min_value':-1}),('deals',{'min_value':5,'max_value':4}),('deals',{'priority':'high'}),('tasks',{'due':'yesterday'}),('tasks',{'priority':'low'}),('tasks',{'company':'X'}),('contacts',{'status':'done'})])
def test_list_invalid_filters(crm,kind,filters):
    with pytest.raises(CRMError): crm.list(kind,**filters)


def test_api_and_tool_parity(crm,monkeypatch):
    populate(crm)
    # Prevent adapters closing this in-memory test database between calls.
    monkeypatch.setattr(crm,'close',lambda:None)
    monkeypatch.setattr(native_api,'open_profile_crm',lambda:crm)
    monkeypatch.setattr(plugin,'open_profile_crm',lambda **kw:crm)
    app=FastAPI();app.include_router(native_api.router)
    native=TestClient(app);standalone=TestClient(create_app(crm))
    class Context:
        profile_name='test'
        def __init__(self): self.tools={}
        def get_config(self,k,default=None): return default
        def register_tool(self,**kw): self.tools[kw['name']]=kw
    ctx=Context();plugin.register(ctx)
    filters=dict(stage='qualified',contact_type='lead',followup='overdue',limit=1,offset=0)
    expected=crm.contact_report(**filters)
    human_expected=crm.contact_report(**filters,include_relationships=True)
    assert native.get('/reports/contacts',params=dict(filters,workspace_token=crm.workspace_token())).json()==human_expected
    assert standalone.get('/api/reports/contacts',params=filters).json()==human_expected
    agent_expected = dict(expected, items=[{key: value for key, value in item.items()
        if key not in {'notes', 'custom_fields'}} for item in expected['items']])
    assert json.loads(ctx.tools['crm_contact_report']['handler'](filters))['data']==agent_expected
    assert native.get('/reports/contacts',params={'workspace_token':'other'}).status_code==409
    assert native.get('/contacts',params={'stage':'qualified','workspace_token':'other'}).status_code==409
    assert json.loads(ctx.tools['crm_contact_list']['handler']({'stage':'qualified'}))['data'] == [
        {key: value for key, value in item.items() if key not in {'notes', 'custom_fields'}}
        for item in crm.list('contacts', stage='qualified')]
    for root,client in [('',native),('/api',standalone)]:
        assert client.get(root+'/reports/contacts',params={'limit':101}).status_code==422
        for query in ['unknown=x', 'limit=1.0', 'limit=1&limit=2', 'stage=']:
            assert client.get(root+'/reports/contacts?'+query).status_code==400
        assert client.get(root+'/deals',params={'min_value':'1.0'}).status_code==400
        assert client.get(root+'/tasks?due=overdue&due=upcoming').status_code==400
        assert client.get(root+'/reports/contacts',params={'stage':'customer'}).status_code==400
        assert client.get(root+'/deals',params={'min_value':200,'max_value':100}).status_code==400
        assert client.get(root+'/tasks',params={'priority':'low'}).status_code==400
        assert client.get(root+'/deals',params={'min_value':100,'max_value':100}).json()==crm.list('deals',min_value=100,max_value=100,include_relationships=True)
        assert client.get(root+'/tasks',params={'priority':'high','due':'overdue'}).json()==crm.list('tasks',priority='high',due='overdue',include_relationships=True)
    assert not json.loads(ctx.tools['crm_contact_report']['handler']({'limit':True}))['ok']
    assert not json.loads(ctx.tools['crm_contact_report']['handler']({'unknown':True}))['ok']
    assert len(ctx.tools)==83 and sum(t['toolset']=='crm_read' for t in ctx.tools.values())==8
    assert ctx.tools['crm_contact_create']['schema']['parameters']['properties']['lifecycle']['title']=='Contact type'
