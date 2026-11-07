import csv
import io
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, text
from hermes_crm.domain import CRM, CRMError, contacts, activity, idempotency
from hermes_crm.contact_transfer import ContactTransfer, parse_csv, safe_cell, PREFIX


@pytest.fixture
def crm(tmp_path):
    instance = CRM(f'sqlite:///{tmp_path / "transfer.db"}')
    yield instance
    instance.close()


def request(store, csv_text='name,email\r\nAlice,alice@example.test\r\n', mapping=None):
    mapping = mapping or {'name': 'name', 'email': 'email'}
    preview = store.preview(csv_text, mapping)
    return dict(csv_text=csv_text, mapping=mapping, batch_id=str(uuid.uuid4()), expected_fingerprint=preview['fingerprint'],
                approved_rows=[r['row_number'] for r in preview['rows'] if r['status'] != 'invalid'])


def count(crm, table):
    with crm._read_connection() as conn: return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_preview_readonly_and_create_parity(crm):
    store = ContactTransfer(crm)
    before = {t.name: count(crm, t) for t in (contacts, activity, idempotency)}
    data = request(store)
    assert before == {t.name: count(crm, t) for t in (contacts, activity, idempotency)}
    result = store.commit(**data)
    imported = crm.get('contacts', result['created'][0]['id'])
    normal = crm.create('contacts', {'name': 'Alice', 'email': 'alice@example.test'})
    assert {k: imported[k] for k in ('name', 'email', 'company', 'title', 'lifecycle', 'notes', 'custom_fields')} == {k: normal[k] for k in ('name', 'email', 'company', 'title', 'lifecycle', 'notes', 'custom_fields')}
    assert count(crm, activity) == 2
    assert store.receipt(data['batch_id']) == result
    assert store.commit(**data) == result
    assert count(crm, contacts) == 2
    with crm._read_connection() as conn:
        receipt = conn.execute(select(idempotency.c.response).where(idempotency.c.key == PREFIX + data['batch_id'])).scalar_one()
        assert 'Alice' not in receipt and 'alice@example' not in receipt
    with pytest.raises(CRMError): store.commit(**dict(data, duplicate_policy='reject'))


def test_duplicates_and_approved_valid_rows(crm):
    crm.create('contacts', dict(name='Existing', email='A@Example.test'))
    crm.create('contacts', dict(name='Sam Person', company='Acme'))
    store = ContactTransfer(crm)
    raw = 'name,email,company,unused\nOne, a@example.test ,,x\n Sam   Person ,,ACME,x\nNew,n@example.test,,x\nAgain,N@example.test,,x\nBad,no_at,,x\nNo company,,,x\nNo company,,,x\n'
    mapping = {'name':'name','email':'email','company':'company','unused':None}
    preview = store.preview(raw,mapping)
    assert preview['counts'] == dict(ready=3,duplicate=3,invalid=1)
    assert preview['ignored_columns'] == ['unused']
    assert preview['rows'][3]['duplicates'][0]['source'] == 'file'
    args = request(store,raw,mapping)
    with pytest.raises(CRMError): store.commit(**dict(args,duplicate_policy='reject'))
    assert count(crm,contacts)==2
    result=store.commit(**args)
    assert result['counts']==dict(created=3,skipped=3,excluded=1)
    assert count(crm,contacts)==5


def test_stale_preview_and_replay(crm):
    store=ContactTransfer(crm);args=request(store)
    crm.create('contacts',dict(name='Other'))
    with pytest.raises(CRMError,match='changed'): store.commit(**args)
    assert store.receipt(args['batch_id'])['status']=='not_found'
    args=request(store)
    crm.create_field('contacts',dict(key='size',label='Size',type='number'))
    with pytest.raises(CRMError,match='changed'): store.commit(**args)


def test_transaction_rollback(crm,monkeypatch):
    store=ContactTransfer(crm);args=request(store,'name,email\nOne,a@example.test\nTwo,b@example.test\n')
    original=crm._audit
    def fail(conn,kind,record,*a,**kw):
        if record['name']=='Two': raise RuntimeError('synthetic failure')
        return original(conn,kind,record,*a,**kw)
    monkeypatch.setattr(crm,'_audit',fail)
    with pytest.raises(RuntimeError): store.commit(**args)
    assert count(crm,contacts)==count(crm,activity)==count(crm,idempotency)==0


def test_concurrent_same_batch_and_stale_other_batch(crm):
    store=ContactTransfer(crm);args=request(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:store.commit(**args),range(2)))
    assert results[0]==results[1] and count(crm,contacts)==1
    with pytest.raises(CRMError,match='changed'): store.commit(**dict(args,batch_id=str(uuid.uuid4())))


@pytest.mark.parametrize('raw', ['', 'name\n', 'name,name\nA,B', ',email\nA,b', ' name,email\nA,b', 'name,email\nA', 'name\nA,B', 'name\n"A', 'name\nA\x00'])
def test_strict_csv_errors(raw):
    with pytest.raises(CRMError): parse_csv(raw)


def test_bom_newlines_limits_and_mapping(crm,monkeypatch):
    store=ContactTransfer(crm)
    raw='\ufeffname,notes\r\nA,"line one\r\nline two"\r\n'
    p=store.preview(raw,{'name':'name','notes':'notes'})
    assert p['rows'][0]['values']['notes']=='line one\r\nline two'
    assert store.preview(raw)['suggested_mapping']=={'name':'name','notes':'notes'}
    with pytest.raises(CRMError): store.preview(raw,{'name':'name'})
    with pytest.raises(CRMError): store.preview(raw,{'name':'name','notes':'name'})
    with pytest.raises(CRMError): store.preview(raw,{'name':'name','notes':'stage'})
    with pytest.raises(CRMError): parse_csv('name\n'+'A\n'*1001)
    monkeypatch.setattr('hermes_crm.contact_transfer.MAX_BYTES',5)
    with pytest.raises(CRMError): parse_csv('name\nA')


def test_custom_types_archiving_and_contact_type(crm):
    for key,typ,extra in [('n','number',{}),('b','boolean',{}),('d','date',{}),('s','single-select',{'choices':['One','Two']})]:
        crm.create_field('contacts',dict(key=key,label=key,type=typ,**extra))
    store=ContactTransfer(crm)
    raw='name,n,b,d,s,type\nA,0,false,2026-01-02,One,customer\nBad,NaN,no,invalid,Other,won\n'
    mapping={'name':'name',**{k:'custom.'+k for k in ('n','b','d','s')},'type':'lifecycle'}
    p=store.preview(raw,mapping)
    assert p['counts']==dict(ready=1,invalid=1,duplicate=0)
    result=store.commit(**request(store,raw,mapping))
    record=crm.get('contacts',result['created'][0]['id'])
    assert record['custom_fields']==dict(n=0,b=False,d='2026-01-02',s='One')
    assert record['lifecycle']=='customer'
    crm.update_field('contacts','b',dict(version=1,archived=True))
    with pytest.raises(CRMError,match='archived'): store.preview(raw,mapping)


def test_export_complete_selected_filtered_and_formula_safe(crm,monkeypatch):
    store=ContactTransfer(crm)
    # Shared insert primitive intentionally used under the same lock for fixture speed.
    from hermes_crm.domain import ContactInput
    with crm.engine.begin() as conn:
        crm._catalog_lock(conn)
        for i in range(505):
            crm._insert_created(conn,'contacts',ContactInput(name=f'Contact {i}',company='Acme').model_dump(),{},'synthetic')
    dangerous=crm.create('contacts',dict(name='=2+2',company='Other',notes="'private note"))
    result=store.export(filters={'company':'Acme'})
    assert result['row_count']==505 and len(list(csv.reader(io.StringIO(result['csv_text']))))==506
    assert 'notes' not in result['columns']
    result=store.export(columns=['name','notes'],filters={'company':'Other'})
    assert list(csv.reader(io.StringIO(result['csv_text'])))[1]==["'=2+2","''private note"]
    assert result['escaped_cells']==2
    for col in ['stage','protected_notes','id','custom.missing']:
        with pytest.raises(CRMError): store.export(columns=[col])
    with pytest.raises(CRMError): store.export(filters={'limit':1})
    monkeypatch.setattr('hermes_crm.contact_transfer.MAX_EXPORT_ROWS',500)
    with pytest.raises(CRMError): store.export()
    monkeypatch.setattr('hermes_crm.contact_transfer.MAX_EXPORT_BYTES',5)
    with pytest.raises(CRMError): store.export(filters={'company':'Other'})


def test_formula_escaping_and_apostrophe_import(crm):
    for value in ['=1','+1','-1','@x','\t=1','\r=1','\n=1','  =1',"'literal",'\x01=1','\ufeff=1','\u200b=1','\x7f=1']:
        assert safe_cell(value)==("'"+value,True)
    assert safe_cell('ordinary')==('ordinary',False)
    store=ContactTransfer(crm)
    result=store.preview("name\n'=1\n",{'name':'name'})
    assert result['rows'][0]['values']['name']=="'=1"
    with pytest.raises(CRMError): store.preview('name\nA\n',{'name':'name'},True)


def test_receipt_schema_failure(crm):
    store=ContactTransfer(crm)
    with crm.engine.begin() as conn: conn.execute(text('ALTER TABLE crm_idempotency ADD COLUMN unexpected TEXT'))
    for call in [store.catalog,lambda:store.preview('name\nA\n',{'name':'name'}),lambda:store.receipt(str(uuid.uuid4())),store.export]:
        with pytest.raises(CRMError) as error: call()
        assert error.value.status==503


def test_legacy_create_idempotency_and_stage_default_unchanged(crm):
    contact=crm.create('contacts',dict(name='Legacy'),key='legacy-contact')
    assert crm.create('contacts',dict(name='Legacy'),key='legacy-contact')==contact
    crm.create_stage(dict(key='review',label='Review',probability=73))
    deal=crm.create('deals',dict(title='Deal',contact_id=contact['id'],stage='review'),key='legacy-deal')
    assert deal['probability']==73
    assert crm.create('deals',dict(title='Deal',contact_id=contact['id'],stage='review'),key='legacy-deal')==deal

@pytest.mark.parametrize('raw',['name\nA"B\n','name\n"A"B\n','name\n"A" "B"\n'])
def test_strict_quote_placement(raw):
    with pytest.raises(CRMError): parse_csv(raw)


def test_receipt_collision_scope_and_exclusions(crm):
    store=ContactTransfer(crm)
    batch=str(uuid.uuid4())
    crm.create('contacts',dict(name='Collision'),key=PREFIX+batch)
    with pytest.raises(CRMError,match='receipt'): store.receipt(batch)
    args=request(store,'name,email\nGood,a@example.test\nBad,bad\nOther,c@example.test\n')
    args['approved_rows']=[2]
    result=store.commit(**args)
    assert result['excluded']==[dict(row_number=3,reason='invalid'),dict(row_number=4,reason='not_selected')]
    assert result['counts']==dict(created=1,skipped=0,excluded=2)
    crm.profile='other-profile'
    with pytest.raises(CRMError,match='receipt'): store.receipt(args['batch_id'])


def test_nan_preview_serializable(crm):
    crm.create_field('contacts',dict(key='score',label='Score',type='number'))
    result=ContactTransfer(crm).preview('name,score\nA,NaN\nB,Infinity\n',{'name':'name','score':'custom.score'})
    assert result['counts']['invalid']==2
    json.dumps(result,allow_nan=False)


def test_export_linked_stage_and_custom_values(crm):
    crm.create_field('contacts',dict(key='score',label='Score',type='number'))
    contact=crm.create('contacts',dict(name='Contact',lifecycle='partner',custom_fields={'score':0}))
    crm.create('deals',dict(title='A',contact_id=contact['id'],stage='won'))
    crm.create('deals',dict(title='B',contact_id=contact['id'],stage='lead'))
    store=ContactTransfer(crm)
    for stage in ('won','lead'):
        result=store.export(columns=['name','lifecycle','custom.score'],filters={'stage':stage})
        assert result['row_count']==1
        assert list(csv.reader(io.StringIO(result['csv_text'])))[1]==['Contact','partner','0']
    assert store.export(filters={'stage':'unassigned'})['row_count']==0


def test_preview_duplicate_reference_bound(crm):
    for _ in range(25): crm.create('contacts',dict(name='Same',email='same@example.test'))
    row=ContactTransfer(crm).preview('name,email\nSame,same@example.test\n',{'name':'name','email':'email'})['rows'][0]
    assert row['duplicate_count']==25 and len(row['duplicates'])==20


def test_export_snapshot_consistent(crm,monkeypatch):
    # SQLite WAL permits the independent synthetic writer while a reader remains
    # open; PostgreSQL uses the production repeatable-read implementation.
    if crm.backend=='sqlite':
        with crm.engine.connect() as conn: conn.exec_driver_sql('PRAGMA journal_mode=WAL')
    crm.create_field('contacts',dict(key='score',label='Score',type='number'))
    older=crm.create('contacts',dict(name='Older',custom_fields={'score':1}))
    crm.create('contacts',dict(name='Newer',custom_fields={'score':2}))
    original=crm._custom_values
    changed=False
    def interleave(conn,kind,record_id):
        nonlocal changed
        if not changed:
            changed=True
            crm.update('contacts',older['id'],dict(version=1,custom_fields={'score':99}))
        return original(conn,kind,record_id)
    monkeypatch.setattr(crm,'_custom_values',interleave)
    result=ContactTransfer(crm).export(columns=['name','custom.score'])
    assert list(csv.reader(io.StringIO(result['csv_text'])))[1:]==[['Newer','2'],['Older','1']]


def test_api_workspace_errors_and_json_hygiene(crm):
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_crm.contact_transfer_api import build_router
    token=crm.workspace_token()
    @contextmanager
    def service(): yield crm
    def require(instance,value):
        if value!=token: raise CRMError('Workspace changed',409)
    app=FastAPI();app.include_router(build_router(service,require));client=TestClient(app)
    payload=dict(workspace_token=token,csv_text='name\nA\n',mapping={'name':'name'})
    response=client.post('/contact-transfer/preview',json=payload)
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert client.post('/contact-transfer/preview',json=dict(payload,workspace_token='other')).status_code==409
    assert client.post('/contact-transfer/preview?unknown=x',json=payload).status_code==400
    assert client.post('/contact-transfer/preview',json=dict(payload,spreadsheet_safe=True)).status_code==422
    assert client.post('/contact-transfer/preview',content='{"workspace_token":"a","workspace_token":"b"}',headers={'content-type':'application/json'}).status_code==422
    assert count(crm,contacts)==0


def test_api_export_receipt_contract(crm,tmp_path,monkeypatch):
    import sys,types
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_crm.contact_transfer_api import build_router
    module=types.ModuleType('plugins.plugin_storage')
    module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    token=crm.workspace_token()
    @contextmanager
    def service(): yield crm
    def require(instance,value):
        if value!=token: raise CRMError('Workspace changed',409)
    app=FastAPI();app.include_router(build_router(service,require));client=TestClient(app)
    operation=str(uuid.uuid4())
    body=dict(workspace_token=token,operation_id=operation,columns=['name'],filters={},spreadsheet_safe=True)
    response=client.post('/contact-transfer/export',json=body)
    assert response.status_code==200
    result=response.json()
    assert result['operation_id']==operation and result['state']=='committed'
    assert result['stored_path'] and result['suggested_name'].endswith('.csv')
    status=client.get(f'/contact-transfer/export/operations/{operation}',params={'workspace_token':token})
    assert status.status_code==200 and status.json()==result
    assert status.headers['cache-control']=='no-store'
    assert client.post('/contact-transfer/export',json=dict(body,spreadsheet_safe=False)).status_code==422


def test_export_formula_like_csv_boundaries_and_reimport_limits(crm):
    """Parser roundtrip only, not a guarantee about spreadsheet save/reopen.

    Quotes and delimiters must remain cell content. Import does not infer the
    provenance of leading apostrophes or undo spreadsheet-risk mitigation.
    """
    values = [
        '=SUM(1,2)',
        '+"quoted, text"',
        '-"first\r\nsecond"',
        '@"first\nsecond,third"',
        "'literal, apostrophe",
        '\t="tab,quoted"',
        '\r\n="line break,quoted"',
        'ordinary "quote", comma\r\nand newline',
    ]
    crm.create_field('contacts', dict(key='source_text', label='Source text', type='text'))
    for index, value in enumerate(values):
        crm.create('contacts', dict(name=f'Formula boundary {index}', custom_fields={'source_text': value}))
    exported = ContactTransfer(crm).export(columns=['name', 'custom.source_text'])
    parsed = list(csv.reader(io.StringIO(exported['csv_text'], newline=''), strict=True))
    assert parsed[0] == ['name', 'custom.source_text']
    assert len(parsed) == len(values) + 1 and all(len(row) == 2 for row in parsed)
    expected = {f'Formula boundary {index}': safe_cell(value)[0] for index, value in enumerate(values)}
    assert {row[0]: row[1] for row in parsed[1:]} == expected
    assert exported['escaped_cells'] == 7
    preview = ContactTransfer(crm).preview(exported['csv_text'], {'name': 'name', 'custom.source_text': 'custom.source_text'})
    assert len(preview['rows']) == len(values)
    assert all(not row['errors'] for row in preview['rows'])
    assert {row['values']['name']: row['values']['custom_fields']['source_text'] for row in preview['rows']} == expected
    # Export escapes are retained, so mitigation is intentionally not a
    # byte-identical roundtrip for formula-like or apostrophe-leading values.
    assert expected['Formula boundary 0'] != values[0]
    assert expected['Formula boundary 4'] == "''literal, apostrophe"
    assert expected['Formula boundary 7'] == values[7]


def test_scope_resolved_schema_ignores_bookkeeping_and_credentials(crm,monkeypatch):
    from hermes_crm.domain import settings
    crm.workspace_token()
    store=ContactTransfer(crm)
    with crm._read_connection() as conn:
        original=store._scope(conn)
        monkeypatch.setattr(crm,'url','sqlite:///renamed-synthetic-connection.db')
        assert store._scope(conn)==original
        options={'schema_translate_map':{None:None}}
        monkeypatch.setattr(crm.engine,'get_execution_options',lambda:options)
        assert store._scope(conn)==original
        options['schema_translate_map']['_none']=True
        assert store._scope(conn)==original
        monkeypatch.setattr(crm,'backend','postgres')
        options['schema_translate_map'][None]='crm_synthetic'
        postgres_scope=store._scope(conn)
        assert postgres_scope!=original
        options['schema_translate_map'].pop('_none')
        assert store._scope(conn)==postgres_scope
        options['schema_translate_map'].update({'_none':True,'unrelated':'crm_other'})
        monkeypatch.setattr(crm,'url','postgresql+psycopg://synthetic:before@localhost/test')
        assert store._scope(conn)==postgres_scope
        monkeypatch.setattr(crm,'url','postgresql+psycopg://synthetic:after@localhost/test')
        assert store._scope(conn)==postgres_scope
        options['schema_translate_map'][None]='crm_different'
        assert store._scope(conn)!=postgres_scope
        options['schema_translate_map'][None]='crm_synthetic'
        monkeypatch.setattr(crm,'profile','different-profile')
        assert store._scope(conn)!=postgres_scope
    monkeypatch.undo()
    with crm.engine.begin() as conn:
        conn.execute(settings.update().where(settings.c.key=='workspace_id').values(value=str(uuid.uuid4())))
    with crm._read_connection() as conn: assert store._scope(conn)!=original


def test_scope_sqlalchemy_schema_map_mutation_keeps_preview_and_receipt(crm):
    crm.workspace_token()
    schema_map={None:(crm.engine.get_execution_options().get('schema_translate_map') or {}).get(None)}
    crm.engine=crm.engine.execution_options(schema_translate_map=schema_map)
    store=ContactTransfer(crm)
    args=request(store)
    # SQLAlchemy compilation adds bookkeeping to the caller-owned map. Do not
    # serialize the whole map: mixed None/string keys fail sorted JSON encoding.
    assert '_none' in schema_map
    assert schema_map['_none']==schema_map[None]
    result=store.commit(**args)
    assert store.receipt(args['batch_id'])==result
    assert store.commit(**args)==result


def test_scope_credential_rotation_retains_approved_import(crm,monkeypatch):
    crm.workspace_token()
    store=ContactTransfer(crm)
    args=request(store)
    monkeypatch.setattr(crm,'url','postgresql+psycopg://synthetic:rotated@localhost/test')
    result=store.commit(**args)
    assert store.receipt(args['batch_id'])==result
    assert store.commit(**args)==result
