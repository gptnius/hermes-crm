"""Human relationship projections, legacy contracts and authenticated export scope."""
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from hermes_crm import native_api, plugin, domain
from hermes_crm.agent_read_policy import project_agent_result
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.protection import ProtectionStore, Keyring, b64, owned_tables, decrypt_export, canonical, seal
from hermes_crm.relationship_schema import OWNED_TABLES
from hermes_crm.web import create_app
from test_activity_navigation import crm


def event_data(**kw):
    return dict(title='Consultation',kind='appointment',starts_at='2020-01-01T10:00:00Z',
        ends_at='2020-01-01T11:00:00Z',timezone='UTC',notes='EVENT ORDINARY NOTE',**kw)


def test_human_read_projection_leaves_core_receipts_and_agent_defaults(crm):
    contact=crm.create('contacts',dict(name='Contact',company='Retained text',notes='CONTACT NOTE'),key='original')
    with crm.engine.connect() as conn:
        receipt=dict(conn.execute(select(domain.idempotency).where(domain.idempotency.c.key=='original')).mappings().one())
    company=CompanyStore(crm).create(dict(name='Linked company',notes='COMPANY NOTE'),actor='test',key='company')
    CompanyStore(crm).set_contact_company(contact['id'],company['id'],expected_contact_version=1,actor='test',key='link')
    current=crm.get('contacts',contact['id'])
    human=crm.get('contacts',contact['id'],include_relationships=True)
    assert current['company']=='Retained text' and 'company_id' not in current
    assert human['company_id']==company['id'] and human['company_name']=='Linked company'
    assert 'COMPANY NOTE' not in str(human)
    assert project_agent_result('crm_contact_get',human)==project_agent_result('crm_contact_get',current)
    assert crm.create('contacts',dict(name='Contact',company='Retained text',notes='CONTACT NOTE'),key='original')==contact
    with crm.engine.connect() as conn:
        assert dict(conn.execute(select(domain.idempotency).where(domain.idempotency.c.key=='original')).mappings().one())==receipt
    assert crm.snapshot()['contacts'][0]['company_id']==company['id']


def test_event_task_projection_and_preserved_task_contract(crm):
    event=EventStore(crm).create(event_data(),actor='test',key='event')
    receipt=EventStore(crm).create_task(event['id'],dict(title='Prepare',due_at='2030-01-01T12:00:00Z',notes='TASK NOTE'),expected_version=1,actor='test',key='task')
    task=receipt['task']
    assert 'event_id' not in crm.get('tasks',task['id'])
    human=crm.get('tasks',task['id'],include_relationships=True)
    assert human['event_id']==event['id'] and human['event_title']=='Consultation'
    assert human['notes']=='TASK NOTE' and 'EVENT ORDINARY NOTE' not in str(human)
    assert 'event_id' not in project_agent_result('crm_task_get',human)
    assert crm.overview(include_task_assignments=True)['tasks'][0]['event_id']==event['id']


def test_human_routes_and_readonly_scope_validation(crm,monkeypatch):
    monkeypatch.setattr(crm,'close',lambda:None)
    monkeypatch.setattr(native_api,'open_profile_crm',lambda:crm)
    app=FastAPI();app.include_router(native_api.router)
    for client,prefix in [(TestClient(app),''),(TestClient(create_app(crm)),'/api')]:
        assert crm.existing_workspace_token() is None
        assert client.get(prefix+'/companies',params={'workspace_token':'forged'}).status_code==409
        assert crm.existing_workspace_token() is None
        assert not any(inspect(crm.engine).has_table(t.name,schema=crm.engine.get_execution_options().get('schema_translate_map',{}).get(None)) for t in OWNED_TABLES)
    token=crm.workspace_token()
    company=CompanyStore(crm).create(dict(name='Organization'),actor='test',key='company')
    for client,prefix in [(TestClient(app),''),(TestClient(create_app(crm)),'/api')]:
        assert client.get(prefix+'/companies',params={'workspace_token':token}).json()['items'][0]['id']==company['id']
        assert client.get(prefix+'/companies',params={'workspace_token':'forged'}).status_code==409


def test_export_owned_tables_and_current_scope_only(crm):
    ring=Keyring.parse(json.dumps(dict(active='test',keys={'test':b64(bytes(range(32)))})))
    assert owned_tables()['crm_contacts'] is domain.contacts
    first=CompanyStore(crm).create(dict(name='LOCAL COMPANY',notes='LOCAL NOTE'),actor='test',key='company')
    ev=EventStore(crm).create(event_data(company_id=first['id']),actor='test',key='event')
    profile=crm.profile
    crm.profile='other'
    foreign=CompanyStore(crm).create(dict(name='FOREIGN_MARKER',notes='FOREIGN_MARKER'),actor='test',key='company')
    EventStore(crm).create(event_data(company_id=foreign['id'])|{'title':'FOREIGN_MARKER','notes':'FOREIGN_MARKER'},actor='test',key='event')
    crm.profile=profile
    assert 'FOREIGN_MARKER' not in str(crm.activities())
    store=ProtectionStore(crm)
    envelope=store.export(ring)
    value=decrypt_export(envelope,ring,workspace=store.workspace,profile=profile)
    assert 'FOREIGN_MARKER' not in str(value)
    assert value['tables']['crm_companies'][0]['id']==first['id']
    assert value['tables']['crm_events'][0]['id']==ev['id']
    assert value['tables']['crm_events'][0]['notes']=='EVENT ORDINARY NOTE'
    assert len(value['tables']['crm_event_revisions'])==1
    assert {t.name for t in OWNED_TABLES}.issubset(value['tables'])
    assert b'LOCAL NOTE' not in canonical(envelope)


def test_export_absence_and_older_envelope_stay_readable(crm):
    ring=Keyring.parse(json.dumps(dict(active='test',keys={'test':b64(bytes(range(32)))})))
    store=ProtectionStore(crm)
    value=decrypt_export(store.export(ring),ring,workspace=store.workspace,profile=crm.profile)
    assert not ({t.name for t in OWNED_TABLES}&set(value['tables']))
    original=dict(format='hermes-crm-export',version=1,workspace=store.workspace,profile=crm.profile,tables={})
    old=seal(canonical(original),ring,'backup',dict(workspace=store.workspace,profile=crm.profile))
    assert decrypt_export(old,ring,workspace=store.workspace,profile=crm.profile)==original
