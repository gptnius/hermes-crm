"""Atomic contact/Company creation using synthetic isolated databases only."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select, func, update
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM, CRMError, contacts, activity, idempotency
from hermes_crm.companies import CompanyStore
from hermes_crm.relationship_schema import contact_companies, operations, schema_state
from hermes_crm.relationship_api import build_router
from hermes_crm.relationship_tools import register_relationship_tools, CORE_FIELDS, LINK_FIELDS
from hermes_crm.relationship_queries import RelationshipQueries
from hermes_crm.reports import ReportEngine

@pytest.fixture(params=['sqlite', 'postgres'])
def crm(request, tmp_path):
    url = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
    if request.param == 'postgres' and not url:
        pytest.skip('Requires explicit disposable PostgreSQL URL')
    schema = 'crm_contact_create_' + uuid.uuid4().hex if request.param == 'postgres' else None
    crm = CRM(url if schema else 'sqlite:///' + str(tmp_path / 'synthetic.db'), **({'schema': schema} if schema else {}))
    try:
        yield crm
    finally:
        crm.close()
        if schema:
            engine = create_engine(url)
            try:
                with engine.begin() as conn: conn.execute(DropSchema(schema, cascade=True, if_exists=True))
            finally: engine.dispose()

def company(crm, key='company'):
    return CompanyStore(crm).create({'name':'Duplicate'}, actor='test', key=key)

def create(crm, co=None, key='contact', data=None):
    return CompanyStore(crm).create_contact(data or {'name':'Person','company':'Independent text'},
        co['id'] if co else None, co['version'] if co else None, actor='test', key=key)

def counts(crm):
    with crm.engine.connect() as conn:
        return tuple(conn.execute(select(func.count()).select_from(t)).scalar_one()
                     for t in (contacts, contact_companies, activity, operations, idempotency))

def test_preserves_custom_legacy_and_exact_report_links(crm):
    co = company(crm); other = company(crm, 'duplicate')
    crm.create_field('contacts', {'key':'tier','label':'Tier','type':'text'})
    data = {'name':'Person','company':'Independent text','notes':'PRIVATE','custom_fields':{'tier':'PRIVATE'}}
    receipt = create(crm, co, data=data); row, link = receipt['contact'], receipt['company_link']
    assert row == crm.get('contacts', row['id'])
    assert row['custom_fields'] == {'tier':'PRIVATE'} and row['company'] == data['company']
    assert link['contact_id'] == row['id'] and link['contact_version'] == row['version'] == 1
    assert link['company_id'] == co['id'] and link['company_link_basis'] == 'explicit'
    unlinked = create(crm, key='unlinked', data={'name':'Text only','company':co['name']})
    assert unlinked['company_link']['company_link_basis'] == 'unlinked'
    assert RelationshipQueries(crm).company_detail(co['id'])['counts']['contacts'] == 1
    assert RelationshipQueries(crm).company_detail(other['id'])['counts']['contacts'] == 0
    result = ReportEngine(crm).run({'entity':'contacts','columns':['id','company_id'],'group_by':{'field':'company_id'}})
    assert {g['key']:g['count'] for g in result['groups']} == {co['id']:1, None:1}

def test_historical_receipt_and_old_create_unchanged(crm):
    legacy = crm.create('contacts', {'name':'Legacy'}, key='same-key')
    with crm.engine.connect() as conn: old = [dict(r) for r in conn.execute(select(idempotency)).mappings()]
    co = company(crm); receipt = create(crm, co, key='same-key'); store = CompanyStore(crm)
    renamed = store.update(co['id'], {'name':'Renamed'}, expected_version=1, actor='test', key='rename')
    store.archive(co['id'], expected_version=2, actor='test', key='archive')
    assert create(crm, co, key='same-key') == receipt
    assert crm.create('contacts', {'name':'Legacy'}, key='same-key') == legacy
    for target, data in ((None,None), (renamed,None), (co,{'name':'Changed'})):
        with pytest.raises(CRMError, match='different data'): create(crm, target, key='same-key', data=data)
    with crm.engine.connect() as conn: assert old == [dict(r) for r in conn.execute(select(idempotency)).mappings()]

@pytest.mark.parametrize('case', ['unknown','scope','stale','archived','uuid','bool','missing','zero','text_version','unlinked_version','custom','data'])
def test_invalid_create_leaves_no_partial_state(crm, case):
    co = company(crm); store = CompanyStore(crm); data = {'name':'Person'}; identifier = co['id']; version = 1
    if case == 'unknown': identifier = str(uuid.uuid4())
    if case == 'scope': crm.profile = 'other'
    if case == 'stale': version = 2
    if case == 'archived': store.archive(co['id'], expected_version=1, actor='test', key='archive'); version = 2
    if case == 'uuid': identifier = 'not-a-uuid'
    if case == 'bool': version = True
    if case == 'missing': version = None
    if case == 'zero': version = 0
    if case == 'text_version': version = '1'
    if case == 'unlinked_version': identifier = None
    if case == 'custom': data['custom_fields'] = {'unknown':'value'}
    if case == 'data': data['unknown'] = 'value'
    before = counts(crm)
    with pytest.raises((CRMError, ValidationError)): store.create_contact(data, identifier, version, actor='test', key='invalid')
    assert counts(crm) == before

def test_post_link_failure_rolls_back_and_key_can_retry(crm, monkeypatch):
    co = company(crm); store = CompanyStore(crm); before = counts(crm); original = store.get_contact_company
    def fail(*args, **kw): raise RuntimeError('Synthetic post-link failure')
    monkeypatch.setattr(store, 'get_contact_company', fail)
    with pytest.raises(RuntimeError): store.create_contact({'name':'Person'}, co['id'], 1, actor='test', key='retry')
    assert counts(crm) == before
    monkeypatch.setattr(store, 'get_contact_company', original)
    assert store.create_contact({'name':'Person'}, co['id'], 1, actor='test', key='retry')['contact']['version'] == 1

def test_concurrent_same_key_and_archive_are_serialized(crm):
    co = company(crm)
    with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(lambda _: create(crm, co), range(8)))
    assert all(r == results[0] for r in results) and len(crm.list('contacts')) == 1
    def archive(): return CompanyStore(crm).archive(co['id'], expected_version=1, actor='test', key='archive')
    def another():
        try: return create(crm, co, key='race')
        except CRMError as exc: assert exc.status == 409; return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(another), pool.submit(archive)]; created, archived = [f.result() for f in futures]
    assert archived['archived_at'] and len(crm.list('contacts')) == (2 if created else 1)
    assert create(crm, co) == results[0]
    if created: assert create(crm, co, key='race') == created

def test_shared_api_strict_scope_and_minimized_tool(crm):
    co = company(crm); token = crm.workspace_token()
    @contextmanager
    def service(): yield crm
    app = FastAPI()
    @app.exception_handler(CRMError)
    def error(request, exc): return JSONResponse({'error':str(exc)}, status_code=exc.status)
    app.include_router(build_router(service, lambda crm, token: None, actor='test-api')); client = TestClient(app)
    body = dict(workspace_token=token,idempotency_key='api',data={'name':'Person','notes':'PRIVATE'},company_id=co['id'],expected_company_version=1)
    response = client.post('/relationship-contacts', json=body)
    assert response.status_code == 201, response.text
    assert client.post('/relationship-contacts', json=body).json() == response.json()
    assert response.json()['contact']['notes'] == 'PRIVATE'
    for patch, status in (({'workspace_token':'forged'},409), ({'actor':'forged'},422), ({'expected_company_version':True},422), ({'expected_company_version':'1'},422), ({'expected_company_version':0},422), ({'company_id':str(uuid.uuid4()),'idempotency_key':'unknown'},404)):
        assert client.post('/relationship-contacts', json=body | patch).status_code == status
    assert client.post('/relationship-contacts?unknown=x',json=body).status_code == 400
    assert client.post('/relationship-contacts', json={k:v for k,v in body.items() if k != 'expected_company_version'}).status_code == 409
    registered = {}
    register_relationship_tools(lambda name,description,properties,required,handler,**kw: registered.update({name:(handler,kw)}))
    handler, options = registered['crm_contact_create_with_company']
    assert options['toolset'] == 'crm_company_write' and all(o['toolset'] != 'crm_read' for _,o in registered.values())
    crm.create_field('contacts', {'key':'private','label':'Private','type':'text'})
    args = options['argument_model'].model_validate(dict(data={'name':'Tool','notes':'PRIVATE','custom_fields':{'private':'SECRET'}},company_id=co['id'],expected_company_version=1,idempotency_key='tool')).model_dump()
    receipt = handler(crm,args,None)
    assert set(receipt['contact']) <= CORE_FIELDS and set(receipt['company_link']) <= LINK_FIELDS
    assert 'PRIVATE' not in str(receipt) and 'SECRET' not in str(receipt)
    assert receipt['company_link']['contact_version'] == receipt['contact']['version'] == 1
    for extra in ({'actor':'forged'}, {'expected_company_version':True}):
        with pytest.raises(ValidationError): options['argument_model'].model_validate(args | extra)

def test_both_actual_hosts_mount_create_contract(crm, monkeypatch):
    from hermes_crm import native_api
    from hermes_crm.web import create_app
    original_close = crm.close
    monkeypatch.setattr(crm, 'close', lambda: None)
    monkeypatch.setattr(native_api, 'open_profile_crm', lambda: crm)
    app = FastAPI(); app.include_router(native_api.router)
    co = company(crm); token = crm.workspace_token()
    try:
        for index, (client, prefix) in enumerate(((TestClient(app), ''), (TestClient(create_app(crm)), '/api'))):
            body = dict(workspace_token=token,idempotency_key='host-'+str(index),data={'name':'Person','company':'Legacy'},company_id=co['id'],expected_company_version=1)
            response = client.post(prefix+'/relationship-contacts', json=body)
            assert response.status_code == 201, response.text
            receipt = response.json()
            assert receipt['contact']['custom_fields'] == {} and receipt['company_link']['company_id'] == co['id']
            assert receipt['company_link']['contact_version'] == receipt['contact']['version'] == 1
            assert client.post(prefix+'/relationship-contacts', json=body | {'workspace_token':'forged'}).status_code == 409
            assert client.post(prefix+'/relationship-contacts', json=body | {'unknown':True}).status_code == 422
    finally: monkeypatch.setattr(crm, 'close', original_close)

def test_schema_failure_and_invalid_custom_shape_do_not_insert(crm):
    company(crm); before = counts(crm)
    for data in ({'name':'Person','custom_fields':[]}, [], None):
        with pytest.raises(CRMError): CompanyStore(crm).create_contact(data, actor='test', key='invalid-shape')
    with crm.engine.begin() as conn: conn.execute(update(schema_state).values(version=2))
    with pytest.raises(CRMError): create(crm, key='unknown-schema')
    assert counts(crm) == before
