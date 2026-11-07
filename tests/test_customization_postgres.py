"""Customization contract against an explicitly configured disposable PostgreSQL DB."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM, CRMError
import test_customization as contract

URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def crm():
    schema='crm_test_'+uuid.uuid4().hex
    instance=None
    try:
        instance=CRM(URL,schema=schema)
        yield instance
    finally:
        if instance: instance.close()
        engine=create_engine(URL)
        with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        engine.dispose()

def test_stages(crm): contract.test_stage_lifecycle_and_outcome(crm)
@pytest.mark.parametrize('kind',['contacts','deals','tasks'])
def test_values(crm,kind): contract.test_custom_roundtrip_atomic_clear_and_archive(crm,kind)
def test_definitions(crm): contract.test_immutable_keys_versions_choices(crm)
@pytest.mark.parametrize('type_,good,bad',[('number',12.5,True),('boolean',False,0),('date','2026-11-07','20261107'),('text','x',4)])
def test_types(crm,type_,good,bad): contract.test_strict_values(crm,type_,good,bad)

def test_concurrent_initialization(crm):
    schema=crm.engine.get_execution_options()['schema_translate_map'][None]
    def initialize(_):
        item=CRM(URL,schema=schema)
        try: return item.catalog()
        finally: item.close()
    with ThreadPoolExecutor(max_workers=4) as pool: results=list(pool.map(initialize,range(8)))
    assert all(len(r['stages'])==6 for r in results)

def test_snapshot_catalog(crm,monkeypatch):
    original=crm.catalog
    changed=False
    def hooked(conn=None):
        nonlocal changed
        result=original(conn)
        if not changed:
            changed=True
            crm.update_stage('lead',dict(version=1,label='New label'))
            crm.create_stage(dict(key='settled',label='Settled',outcome='won'))
        return result
    monkeypatch.setattr(crm,'catalog',hooked)
    snapshot=crm.overview()
    assert snapshot['stages'][0]['label']=='Lead'
    assert 'settled' not in [s['stage'] for s in snapshot['stages']]
    assert crm.overview()['stages'][0]['label']=='New label'

@pytest.mark.parametrize('length',[36,37,64])
def test_definition_audit_identity(crm,length):
    contract.test_definition_audit_identity_fits_legacy_column(crm,length)

def test_full_snapshot_is_atomic(crm,monkeypatch):
    contract.assert_snapshot_survives_concurrent_catalog_and_record_create(crm,crm,monkeypatch)

def test_legacy_schema_upgrade_preserves_records_and_retry_receipt():
    """Start from domain tables only, rather than the already-upgraded CRM fixture."""
    import hashlib
    import json
    from sqlalchemy import select
    from sqlalchemy.schema import CreateSchema
    from hermes_crm.domain import metadata, contacts, deals, tasks, idempotency, ContactInput
    from hermes_crm.customization import definitions
    schema='crm_test_'+uuid.uuid4().hex
    engine=create_engine(URL)
    scoped=engine.execution_options(schema_translate_map={None:schema})
    instances=[]
    try:
        with engine.begin() as conn: conn.execute(CreateSchema(schema))
        metadata.create_all(scoped)
        timestamp='2025-01-02T03:04:05.000000+00:00'
        contact_values=ContactInput(name='Legacy contact',email='legacy@example.test',company='Old company',notes='Keep this exact text').model_dump()
        contact=dict(id=str(uuid.uuid4()),version=7,created_at=timestamp,updated_at=timestamp,**contact_values)
        deal=dict(id=str(uuid.uuid4()),version=4,created_at=timestamp,updated_at=timestamp,title='Legacy deal',contact_id=contact['id'],value=12345,currency='USD',stage='qualified',probability=25,close_date='2027-01-02',notes='Existing deal')
        task=dict(id=str(uuid.uuid4()),version=3,created_at=timestamp,updated_at=timestamp,title='Legacy task',contact_id=contact['id'],deal_id=deal['id'],due_at='2030-01-01T00:00:00.000000+00:00',priority='high',status='open',notes='Existing task',schedule_status='none',scheduler_job_id=None)
        digest=hashlib.sha256(json.dumps(['contacts',contact_values],sort_keys=True).encode()).hexdigest()
        original_response=dict(contact,version=1)
        receipt=dict(key='legacy-create-key',digest=digest,response=json.dumps(original_response))
        with scoped.begin() as conn:
            conn.execute(contacts.insert().values(**contact))
            conn.execute(deals.insert().values(**deal))
            conn.execute(tasks.insert().values(**task))
            conn.execute(idempotency.insert().values(**receipt))
        # Concurrent first initialization exercises PG advisory migration locking.
        def initialize(_): return CRM(URL,schema=schema)
        with ThreadPoolExecutor(max_workers=3) as pool: instances=list(pool.map(initialize,range(3)))
        upgraded=instances[0]
        with upgraded.engine.connect() as conn:
            for table, expected in [(contacts,contact),(deals,deal),(tasks,task),(idempotency,receipt)]:
                assert dict(conn.execute(select(table)).mappings().one())==expected
            seeded=conn.execute(select(definitions)).mappings().all()
            assert len(seeded)==6
            assert {r['key'] for r in seeded}=={'lead','qualified','proposal','negotiation','won','lost'}
        assert upgraded.create('contacts',contact_values,key=receipt['key'])==original_response
        for kind,record in [('contacts',contact),('deals',deal),('tasks',task)]:
            assert upgraded.get(kind,record['id'])==dict(record,custom_fields={})
        snapshot=upgraded.snapshot()
        assert snapshot['overview']['contacts']==1
        assert snapshot['overview']['open_deals']==1
        assert all(instance.catalog()==upgraded.catalog() for instance in instances)
    finally:
        for instance in instances: instance.close()
        with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        engine.dispose()


def test_newer_customization_schema_fails_closed(crm):
    from sqlalchemy import update
    from hermes_crm.customization import state
    schema=crm.engine.get_execution_options()['schema_translate_map'][None]
    with crm.engine.begin() as conn: conn.execute(update(state).values(version=99))
    with pytest.raises(CRMError,match='Unsupported customization schema version'):
        CRM(URL,schema=schema)


def test_malformed_customization_schema_fails_closed(crm):
    schema=crm.engine.get_execution_options()['schema_translate_map'][None]
    # Only this fixture's randomly generated disposable schema is altered.
    with crm.engine.begin() as conn:
        conn.exec_driver_sql(f'ALTER TABLE "{schema}".crm_custom_values ALTER COLUMN record_id TYPE VARCHAR(1)')
    with pytest.raises(CRMError,match='Incompatible customization column'):
        CRM(URL,schema=schema)
