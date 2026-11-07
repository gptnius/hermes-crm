import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, update
from hermes_crm.domain import CRM, CRMError, contacts, idempotency, metadata
from hermes_crm.customization import state

@pytest.fixture
def crm():
    result=CRM('sqlite:///:memory:')
    yield result
    result.close()

def test_stage_lifecycle_and_outcome(crm):
    stage=crm.create_stage(dict(key='contract',label='Contract',probability=85),key='stage-create')
    assert crm.create_stage(dict(key='contract',label='Contract',probability=85),key='stage-create')==stage
    contact=crm.create('contacts',dict(name='A'))
    deal=crm.create('deals',dict(title='D',contact_id=contact['id'],stage='contract',value=10000))
    assert deal['probability']==85
    assert crm.overview()['pipeline_value']==10000
    assert crm.contact_report(stage='contract')['items'][0]['deal_stages']==['contract']
    with pytest.raises(CRMError): crm.update_stage('contract',dict(version=1,archived=True))
    won=crm.create_stage(dict(key='paid',label='Paid',outcome='won',probability=20))
    assert won['probability']==100
    deal=crm.update('deals',deal['id'],dict(version=deal['version'],stage='paid',probability=3))
    assert deal['probability']==100
    assert crm.overview()['won_value']==10000
    assert crm.overview()['open_deals']==0
    assert crm.update_stage('contract',dict(version=1,archived=True))['archived']
    with pytest.raises(CRMError): crm.create('deals',dict(title='D2',contact_id=contact['id'],stage='contract'))
    with pytest.raises(CRMError): crm.update_stage('lead',dict(version=1,archived=True))

@pytest.mark.parametrize('kind', ['contacts','deals','tasks'])
def test_custom_roundtrip_atomic_clear_and_archive(crm,kind):
    crm.create_field(kind,dict(key='segment',label='Segment',type='single-select',choices=['A','B']))
    c=crm.create('contacts',dict(name='C'))
    payload={'contacts':dict(name='A'),'deals':dict(title='D',contact_id=c['id']),'tasks':dict(title='T',due_at='2030-01-01T00:00:00Z')}[kind]
    record=crm.create(kind,dict(payload,custom_fields={'segment':'A'}),key='record-create')
    assert crm.create(kind,dict(payload,custom_fields={'segment':'A'}),key='record-create')==record
    assert crm.get(kind,record['id'])['custom_fields']=={'segment':'A'}
    assert any(r['custom_fields']=={'segment':'A'} for r in crm.list(kind))
    with pytest.raises(CRMError): crm.update(kind,record['id'],dict(version=1,custom_fields={'segment':'C'}))
    assert crm.get(kind,record['id'])['version']==1
    record=crm.update(kind,record['id'],dict(version=1,notes='x'))
    assert record['custom_fields']=={'segment':'A'}
    record=crm.update(kind,record['id'],dict(version=2,custom_fields={'segment':None}))
    assert record['custom_fields']=={}
    record=crm.update(kind,record['id'],dict(version=3,custom_fields={'segment':'B'}))
    crm.update_field(kind,'segment',dict(version=1,archived=True))
    assert crm.update(kind,record['id'],dict(version=4,notes='y'))['custom_fields']=={'segment':'B'}
    with pytest.raises(CRMError): crm.update(kind,record['id'],dict(version=5,custom_fields={'segment':None}))

@pytest.mark.parametrize('type_,good,bad', [('number',12.5,True),('number',0,float('inf')),('boolean',False,0),('date','2026-11-07','20261107'),('text','x',4)])
def test_strict_values(crm,type_,good,bad):
    crm.create_field('contacts',dict(key='field',label='Field',type=type_))
    c=crm.create('contacts',dict(name='A',custom_fields={'field':good}))
    with pytest.raises(CRMError): crm.update('contacts',c['id'],dict(version=1,custom_fields={'field':bad}))
    assert crm.get('contacts',c['id'])['custom_fields']=={'field':good}

def test_immutable_keys_versions_choices(crm):
    crm.create_field('contacts',dict(key='a',label='A',type='single-select',choices=['x']))
    for patch in [dict(type='text'),dict(key='b'),dict(choices=['y'])]:
        with pytest.raises(CRMError): crm.update_field('contacts','a',dict(version=1,**patch))
    field=crm.update_field('contacts','a',dict(version=1,label='New',choices=['x','y']))
    assert field['version']==2
    with pytest.raises(CRMError): crm.update_field('contacts','a',dict(version=1,label='Conflict'))

def test_additive_upgrade_and_fail_closed(tmp_path):
    from sqlalchemy import create_engine
    url=f'sqlite:///{tmp_path}/old.db'
    engine=create_engine(url)
    metadata.create_all(engine)
    row=dict(id='old',version=9,created_at='old',updated_at='old',name='Old',email='',company='',title='',lifecycle='lead',notes='')
    with engine.begin() as conn: conn.execute(contacts.insert().values(**row))
    engine.dispose()
    crm=CRM(url)
    with crm.engine.connect() as conn: assert dict(conn.execute(select(contacts)).mappings().one())==row
    assert crm.get('contacts','old')['custom_fields']=={}
    with crm.engine.begin() as conn: conn.execute(update(state).values(version=99))
    crm.close()
    with pytest.raises(CRMError,match='Unsupported'): CRM(url)

def test_concurrent_initialization_and_stale_updates(tmp_path):
    url=f'sqlite:///{tmp_path}/concurrent.db'
    def work(_):
        crm=CRM(url)
        catalog=crm.catalog()
        crm.close()
        return catalog
    with ThreadPoolExecutor(max_workers=4) as pool: catalogs=list(pool.map(work,range(8)))
    assert all(len(c['stages'])==6 for c in catalogs)
    crm=CRM(url)
    c=crm.create('contacts',dict(name='A'))
    def edit(_):
        try: return crm.update('contacts',c['id'],dict(version=1,name='B'))['version']
        except CRMError as exc: return exc.status
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(edit,range(2)))
    assert sorted(results)==[2,409]
    crm.close()

def test_overview_uses_one_snapshot_during_catalog_edit(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path}/snapshot.db'
    crm=CRM(url)
    with crm.engine.connect() as conn: conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    writer=CRM(url)
    original=crm.catalog
    changed=False
    def concurrent_catalog(conn=None):
        nonlocal changed
        result=original(conn)
        if not changed:
            changed=True
            writer.update_stage('lead',dict(version=1,label='New label'))
            writer.create_stage(dict(key='settled',label='Settled',outcome='won'))
        return result
    monkeypatch.setattr(crm,'catalog',concurrent_catalog)
    snapshot=crm.overview()
    assert snapshot['catalog']['stages'][0]['label']=='Lead'
    assert snapshot['stages'][0]['label']=='Lead'
    assert 'settled' not in [s['stage'] for s in snapshot['stages']]
    subsequent=crm.overview()
    assert subsequent['stages'][0]['label']=='New label'
    assert next(s for s in subsequent['stages'] if s['stage']=='settled')['outcome']=='won'
    crm.close();writer.close()

def test_legacy_retry_digest_preserved(crm):
    import hashlib
    from hermes_crm.domain import ContactInput
    values=ContactInput(name='Legacy').model_dump()
    digest=hashlib.sha256(json.dumps(['contacts',values],sort_keys=True).encode()).hexdigest()
    response=dict(id='old-response',version=1,**values)
    with crm.engine.begin() as conn:
        conn.execute(idempotency.insert().values(key='old-key',digest=digest,response=json.dumps(response)))
    assert crm.create('contacts',dict(name='Legacy'),key='old-key')==response
    with pytest.raises(CRMError): crm.create('contacts',dict(name='Legacy',custom_fields=None),key='old-key')

def test_archive_race_cannot_strand_deals(tmp_path):
    crm=CRM(f'sqlite:///{tmp_path}/race.db')
    crm.create_stage(dict(key='review',label='Review'))
    contact=crm.create('contacts',dict(name='A'))
    def archive():
        try: return crm.update_stage('review',dict(version=1,archived=True))
        except CRMError: return None
    def create():
        try: return crm.create('deals',dict(title='D',contact_id=contact['id'],stage='review'))
        except CRMError: return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[pool.submit(archive),pool.submit(create)]
        results=[f.result() for f in results]
    assert sum(r is not None for r in results)==1
    stage=next(s for s in crm.catalog()['stages'] if s['key']=='review')
    assert not (stage['archived'] and crm.list('deals',stage='review'))
    crm.close()

def test_incompatible_customization_column_length_fails_closed(tmp_path):
    url=f'sqlite:///{tmp_path}/incompatible.db'
    crm=CRM(url)
    # Deliberately corrupt only a disposable fixture, retaining names and key shape.
    with crm.engine.begin() as conn:
        conn.exec_driver_sql('DROP TABLE crm_custom_values')
        conn.exec_driver_sql('CREATE TABLE crm_custom_values (kind VARCHAR(20) NOT NULL, record_id VARCHAR(1) NOT NULL, values_json TEXT NOT NULL, PRIMARY KEY (kind,record_id))')
    crm.close()
    with pytest.raises(CRMError,match='Incompatible customization column'): CRM(url)

@pytest.mark.parametrize('length',[36,37,64])
def test_definition_audit_identity_fits_legacy_column(crm,length):
    import uuid
    from hermes_crm.domain import activity
    key='a'*length
    crm.create_field('contacts',dict(key=key,label='Boundary field',type='text'))
    crm.update_field('contacts',key,dict(version=1,label='Updated boundary'))
    record=crm.create('contacts',dict(name='Record',custom_fields={key:'Retained'}))
    with crm.engine.connect() as conn:
        events=[dict(r) for r in conn.execute(select(activity)).mappings()]
    definition_events=[r for r in events if r['entity_type']=='customization']
    expected=str(uuid.uuid5(uuid.NAMESPACE_URL,f'hermes-crm:customization:contacts:{key}'))
    assert len(definition_events)==2
    assert all(e['entity_id']==expected and len(e['entity_id'])==36 for e in definition_events)
    assert all(f'contacts.{key}:' in e['summary'] for e in definition_events)
    assert next(e for e in events if e['entity_type']=='contacts')['entity_id']==record['id']
    assert crm.get('contacts',record['id'])['custom_fields']=={key:'Retained'}

def test_field_operations_reject_stage_kind(crm):
    with pytest.raises(CRMError,match='Invalid record kind'):
        crm.create_field('stages',dict(key='wrong',label='Wrong'))
    with pytest.raises(CRMError,match='Invalid record kind'):
        crm.update_field('stages','lead',dict(version=1,label='Wrong'))

def assert_snapshot_survives_concurrent_catalog_and_record_create(crm,writer,monkeypatch):
    original=crm.catalog
    changed=False
    def hooked(conn=None):
        nonlocal changed
        result=original(conn)
        if not changed:
            changed=True
            writer.create_stage(dict(key='new_stage',label='New stage'))
            contact=writer.create('contacts',dict(name='Concurrent contact'))
            writer.create('deals',dict(title='Concurrent deal',contact_id=contact['id'],stage='new_stage'))
        return result
    monkeypatch.setattr(crm,'catalog',hooked)
    snapshot=crm.snapshot()
    assert snapshot['meta']['workspace_token']
    assert not snapshot['contacts'] and not snapshot['deals']
    assert 'new_stage' not in snapshot['meta']['stages']
    assert 'new_stage' not in [s['stage'] for s in snapshot['overview']['stages']]
    assert not snapshot['activity']
    subsequent=crm.snapshot()
    assert 'new_stage' in subsequent['meta']['stages']
    assert len(subsequent['contacts'])==len(subsequent['deals'])==1
    assert subsequent['deals'][0]['stage']=='new_stage'

def test_full_snapshot_is_atomic(tmp_path,monkeypatch):
    url=f'sqlite:///{tmp_path}/full-snapshot.db'
    crm=CRM(url)
    with crm.engine.connect() as conn: conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    writer=CRM(url)
    try: assert_snapshot_survives_concurrent_catalog_and_record_create(crm,writer,monkeypatch)
    finally: writer.close();crm.close()

def test_initial_stage_palette_preserved_without_overwriting_edits(tmp_path):
    url=f'sqlite:///{tmp_path}/palette.db'
    crm=CRM(url)
    assert [s['color'] for s in crm.catalog()['stages']]==['#4779ce','#9b69c6','#c67e24','#338b95','#32825e','#b85f67']
    crm.update_stage('lead',dict(version=1,color='#123456'))
    crm.close()
    crm=CRM(url)
    assert crm.catalog()['stages'][0]['color']=='#123456'
    assert crm.create_stage(dict(key='custom',label='Custom'))['color']=='#64748b'
    crm.close()
