"""Synthetic evidence and append review contracts; no network access."""
import json
import pytest
from sqlalchemy import inspect,select,update
from pydantic import ValidationError
from hermes_crm.domain import CRM,CRMError,contacts,activity
from hermes_crm.companies import CompanyStore
from hermes_crm.research_store import ResearchStore,hashed
from hermes_crm.research_schema import OWNED_TABLES,evidence,proposals,operations,schema_state
from hermes_crm.research_models import EvidenceInput

@pytest.fixture
def crm():
    c=CRM('sqlite:///:memory:');yield c;c.close()
def target(crm,kind='contacts',notes='Private prior notes'):
    if kind=='contacts': return crm.create(kind,dict(name='Synthetic Person',notes=notes))
    return CompanyStore(crm).create(dict(name='Synthetic Company',notes=notes),key='company',actor='test')
def packet(t,kind='contacts',**kw):
    return dict(target_kind=kind,target_id=t['id'],target_version=t['version'],question='What is publicly stated?',source_url='https://example.test/source?edition=1#section',source_title='Synthetic source',observed_at='2026-11-08T12:00:00+00:00',published_on='2026-11-01',claims=['A supplied claim'],hypotheses=['An inference'],**kw)
def setup(crm,kind='contacts',notes='Private prior notes'):
    t=target(crm,kind,notes);s=ResearchStore(crm);e=s.submit(packet(t,kind),key='e');p=s.propose(dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=e['lifecycle_version'],target_version=t['version'],addition='  Exact addition\n'),key='p');return s,t,e,p
def review(p): return {k:p[k] for k in ('proposal_version','proposal_digest','target_version','before_hash','after_hash')}

def test_read_does_not_initialize(crm):
    t=target(crm);s=ResearchStore(crm)
    assert s.list('evidence','contacts',t['id'])['items']==[]
    assert s.receipt('none')=={'state':'unknown'}
    with crm.engine.connect() as c: assert not any(inspect(c).has_table(t.name) for t in OWNED_TABLES)
@pytest.mark.parametrize('kind',['contacts','companies'])
def test_apply_replay_and_minimized_storage(crm,kind):
    s,t,e,p=setup(crm,kind);preview=s.preview(p['id'])
    assert preview['proposed_notes']=='Private prior notes\n\n  Exact addition\n'
    assert p['addition']=='  Exact addition\n'
    r=s.review(p['id'],review(p),apply=True,key='apply')
    assert r['applied_target_version']==2 and r['status']=='applied'
    assert s.review(p['id'],review(p),apply=True,key='apply')==r
    assert s.receipt('apply')==dict(state='committed',receipt=r)
    with pytest.raises(CRMError): s.review(p['id'],review(p),apply=True,key='other')
    with pytest.raises(CRMError): s.review(p['id'],dict(review(p),target_version=2),apply=True,key='apply')
    with crm.engine.connect() as c:
        for table in (proposals,operations):
            assert 'Private prior notes' not in json.dumps([dict(x) for x in c.execute(select(table)).mappings()])
        assert c.execute(select(activity).where(activity.c.action=='research_note_appended')).first()
    assert 'addition' not in s.list('proposals',kind,t['id'])['items'][0]
    assert 'claims' not in s.list('evidence',kind,t['id'])['items'][0]
    if kind=='contacts': crm.update(kind,t['id'],dict(version=2,notes='Later edit'))
    else: CompanyStore(crm).update(t['id'],dict(notes='Later edit'),expected_version=2,key='edit',actor='test')
    assert s.review(p['id'],review(p),apply=True,key='apply')==r

def test_aba_and_lifecycle(crm):
    s,t,e,p=setup(crm)
    crm.update('contacts',t['id'],dict(version=1,notes='Other'))
    crm.update('contacts',t['id'],dict(version=2,notes=t['notes']))
    assert s.preview(p['id'])['stale'] and 'current_notes' not in s.preview(p['id'])
    with pytest.raises(CRMError): s.review(p['id'],review(p),apply=True,key='a')
    archive=s.lifecycle(e['id'],dict(lifecycle_version=1),archive=True,key='archive')
    s.lifecycle(e['id'],dict(lifecycle_version=2),archive=False,key='restore')
    assert archive['lifecycle_version']==2
    assert s.preview(p['id'])['stale_reason']=='evidence_changed'

def test_company_archive(crm):
    s,t,e,p=setup(crm,'companies')
    CompanyStore(crm).archive(t['id'],expected_version=1,actor='test',key='archive')
    assert s.preview(p['id'])['stale_reason']=='target_archived'
    assert s.get_evidence(e['id'])['claims']==['A supplied claim']
    with pytest.raises(CRMError): s.review(p['id'],review(p),apply=True,key='apply')

def test_limits_and_aliasing(crm):
    t=target(crm,notes='x'*9999);s=ResearchStore(crm);data=packet(t);e=s.submit(data,key='e');data['claims'][0]='Mutated';e['source_title']='Mutated'
    assert s.get_evidence(e['id'])['claims']==['A supplied claim']
    with pytest.raises(CRMError): s.propose(dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='x'),key='p')
@pytest.mark.parametrize('url',['http://example.test','https://user:pass@example.test','https://example.test/%0a','https://example.test/\n','https://example.test:bad','https://example.test\\@evil.test'])
def test_invalid_sources(crm,url):
    d=packet(target(crm));d['source_url']=url
    with pytest.raises(ValidationError): EvidenceInput.model_validate(d)

@pytest.mark.parametrize('point',['audit','proposal','receipt'])
def test_atomic_rollback(crm,monkeypatch,point):
    s,t,e,p=setup(crm)
    if point=='audit': monkeypatch.setattr(crm,'_audit',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('fault')))
    else:
        from sqlalchemy import event
        def fail(conn,cursor,statement,parameters,context,executemany):
            compiled=getattr(getattr(context,'compiled',None),'statement',None)
            table=getattr(getattr(compiled,'table',None),'name',None)
            if point=='proposal' and table=='crm_research_proposals' and getattr(compiled,'is_update',False): raise RuntimeError('fault')
            if point=='receipt' and table=='crm_research_operations' and getattr(compiled,'is_insert',False): raise RuntimeError('fault')
        event.listen(crm.engine,'before_cursor_execute',fail)
    with pytest.raises(RuntimeError): s.review(p['id'],review(p),apply=True,key='a')
    if point!='audit': event.remove(crm.engine,'before_cursor_execute',fail)
    assert crm.get('contacts',t['id'])['version']==1
    assert s.preview(p['id'])['status']=='pending'
    assert s.receipt('a')['state']=='unknown'

def test_dismiss_and_schema_version(crm):
    s,t,e,p=setup(crm)
    r=s.review(p['id'],{k:p[k] for k in ('proposal_version','proposal_digest')},apply=False,key='d')
    assert r['status']=='dismissed' and crm.get('contacts',t['id'])['version']==1
    with crm.engine.begin() as c:c.execute(update(schema_state).values(version=999))
    with pytest.raises(CRMError):s.receipt('d')

def test_scoped_export_and_partial_schema(crm):
    from hermes_crm.protection import ProtectionStore,Keyring,decrypt_export
    s,t,e,p=setup(crm)
    with crm.engine.begin() as c:
        row=dict(c.execute(select(evidence)).mappings().first());row['scope']='foreign-scope';c.execute(evidence.insert().values(**row))
        row=dict(c.execute(select(proposals)).mappings().first());row['scope']='foreign-scope';c.execute(proposals.insert().values(**row))
    ring=Keyring('test',{'test':b'x'*32});store=ProtectionStore(crm)
    exported=decrypt_export(store.export(ring),ring,workspace=store.workspace,profile=crm.profile)
    assert len(exported['tables']['crm_research_evidence'])==1
    assert len(exported['tables']['crm_research_proposals'])==1
    with crm.engine.begin() as c:operations.drop(c)
    with pytest.raises(CRMError):s.get_evidence(e['id'])


def test_tools_and_shared_routes(crm):
    from contextlib import contextmanager
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient
    from hermes_crm.research_api import build_router
    from hermes_crm.research_tools import register_research_tools
    token=crm.workspace_token();t=target(crm)
    @contextmanager
    def service():yield crm
    def require(crm,supplied):
        if supplied!=token: raise CRMError('Stale workspace',409)
    app=FastAPI()
    @app.exception_handler(CRMError)
    def error(request,exc):return JSONResponse({'error':str(exc)},status_code=exc.status)
    @app.exception_handler(ValidationError)
    def invalid(request,exc):return JSONResponse({'error':'Invalid input'},status_code=422)
    app.include_router(build_router(service,require));client=TestClient(app)
    params={'workspace_token':token,'target_kind':'contacts','target_id':t['id']}
    assert client.get('/research/evidence',params=params).json()['total']==0
    assert client.get('/research/evidence',params=dict(params,unknown='x')).status_code==400
    assert client.get('/research/evidence',params=list(params.items())+[('limit','1'),('limit','2')]).status_code==400
    assert client.get('/research/evidence',params=dict(params,workspace_token='wrong')).status_code==409
    body=dict(workspace_token=token,idempotency_key='api',data=packet(t))
    response=client.post('/research/evidence',json=body);assert response.status_code==201,response.text
    assert client.post('/research/evidence',content='{"workspace_token":"x","workspace_token":"y","data":{}}').status_code==422
    invalid=dict(body,data=dict(body['data'],source_url='https://user:secret@example.test'))
    assert client.post('/research/evidence',json=invalid).status_code==422
    registry={}
    register_research_tools(lambda name,desc,props,required,handler,**kw:registry.update({name:(handler,kw)}))
    assert len(registry)==5
    assert {v[1]['toolset'] for v in registry.values()}=={'crm_research_read','crm_research_write'}
    handler,options=registry['crm_research_evidence_submit']
    args=options['argument_model'].model_validate(dict(data=packet(t),idempotency_key='tool')).model_dump()
    result=handler(crm,args,None);assert 'claims' not in result and 'notes' not in result
    with pytest.raises(ValidationError):options['argument_model'].model_validate(dict(data=dict(packet(t),target_version=True),idempotency_key='bad'))

@pytest.mark.parametrize('url',['https://bad..host','https://%65xample.test','https://-bad.test','https://example.test?token=secret','https://example.test#access_token=secret','https://example.test?X-Amz-Signature=secret'])
def test_bad_hosts_and_known_secret_parameters(crm,url):
    with pytest.raises(ValidationError): EvidenceInput.model_validate(dict(packet(target(crm)),source_url=url))

def test_archived_company_rejects_submission(crm):
    t=target(crm,'companies');t=CompanyStore(crm).archive(t['id'],expected_version=1,key='archive',actor='test')
    with pytest.raises(CRMError):ResearchStore(crm).submit(packet(t,'companies'),key='e')

def test_cross_scope_reads_and_receipts(crm):
    s,t,e,p=setup(crm); original=crm.profile;crm.profile='different-profile'
    try:
        assert s.receipt('e')['state']=='unknown'
        assert s.list('evidence','contacts',t['id'])['total']==0
        with pytest.raises(CRMError): s.get_evidence(e['id'])
        with pytest.raises(CRMError): s.preview(p['id'])
    finally:crm.profile=original
    assert s.get_evidence(e['id'])['id']==e['id']

def test_tampered_proposal_fails_closed(crm):
    s,t,e,p=setup(crm)
    with crm.engine.begin() as c:c.execute(update(proposals).values(addition='Modified addition'))
    with pytest.raises(CRMError):s.preview(p['id'])
    with pytest.raises(CRMError):s.review(p['id'],review(p),apply=True,key='a')
    assert crm.get('contacts',t['id'])['version']==1

def test_provenance_and_stable_pages(crm):
    t=target(crm);s=ResearchStore(crm)
    for i in range(3):
        e=s.submit(packet(t),key='e'+str(i),actor='hermes')
        assert e['recorded_actor']=='hermes'
    first=s.list('evidence','contacts',t['id'],limit=2)
    second=s.list('evidence','contacts',t['id'],limit=2,offset=2)
    assert first['total']==3 and len(first['items'])==2 and len(second['items'])==1
    assert {r['id'] for r in first['items']}.isdisjoint({r['id'] for r in second['items']})
    p=s.propose(dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Synthetic note'),key='p',actor='web')
    assert p['created_actor']=='web'
    assert s.get_evidence(e['id'])['recorded_actor']=='hermes'

@pytest.mark.parametrize('url',['https://example.test/%','https://example.test/%ZZ','https://example.test?client_secret=x','https://example.test?authorization=x','https://example.test?api-key=x','https://example.test?X-Amz-Security-Token=x'])
def test_malformed_escapes_and_credential_names(crm,url):
    with pytest.raises(ValidationError):EvidenceInput.model_validate(dict(packet(target(crm)),source_url=url))

def test_stored_proposal_list_validates_shape_and_digest(crm):
    s,t,e,p=setup(crm)
    with crm.engine.begin() as c:c.execute(update(proposals).values(created_actor='Changed actor'))
    for read in (lambda:s.list('proposals','contacts',t['id']),lambda:s.preview(p['id'])):
        with pytest.raises(CRMError) as error:read()
        assert error.value.status==503

@pytest.mark.parametrize('bad',['{"status":"applied"}','{"id":42}','null','{"status":"applied","status":"dismissed"}'])
def test_malformed_operation_never_committed_or_replayed(crm,bad):
    s,t,e,p=setup(crm)
    with crm.engine.begin() as c:c.execute(update(operations).where(operations.c.key=='e').values(response=bad))
    for read in (lambda:s.receipt('e'),lambda:s.submit(packet(t),key='e')):
        with pytest.raises(CRMError) as error:read()
        assert error.value.status==503
    from hermes_crm.protection import ProtectionStore,Keyring
    with pytest.raises(CRMError):ProtectionStore(crm).export(Keyring('test',{'test':b'x'*32}))

@pytest.mark.parametrize('mutation',[{'claims':[123]},{'source_url':'https://user:secret@example.test'},{'unexpected':'field'}])
def test_stored_evidence_revalidated_even_with_consistent_digest(crm,mutation):
    s,t,e,p=setup(crm)
    with crm.engine.begin() as c:
        stored=json.loads(c.execute(select(evidence.c.packet)).scalar_one());stored.update(mutation)
        from hermes_crm.report_store import canonical
        encoded=canonical(stored);c.execute(update(evidence).values(packet=encoded,digest=hashed(encoded)))
    for read in (lambda:s.get_evidence(e['id']),lambda:s.list('evidence','contacts',t['id'])):
        with pytest.raises(CRMError) as error:read()
        assert error.value.status==503
    from hermes_crm.protection import ProtectionStore,Keyring
    with pytest.raises(CRMError):ProtectionStore(crm).export(Keyring('test',{'test':b'x'*32}))

@pytest.mark.parametrize('value',[
    '2026-11-08X12:00:00Z','2026-11-08 12:00:00Z',
    '20261108T120000Z','2026-W45-7T12:00:00Z',
    '2026-11-08T12:00:00+01:00:30','2026-11-08T12:00:00+0100',
    '2026-11-08T12:00:00+01:99','2026-11-08T12:00:00.1234567Z',
])
def test_observed_timestamp_rejects_non_ui_grammar(crm,value):
    with pytest.raises(ValidationError):EvidenceInput.model_validate(dict(packet(target(crm)),observed_at=value))

@pytest.mark.parametrize('value',[
    '2026-11-08T12:00Z','2026-11-08T12:00:01Z',
    '2026-11-08T12:00:01.1Z','2026-11-08T12:00:01.123456Z',
    '2026-11-08T12:00+05:30','2026-11-08T12:00:01-04:00',
    '2026-11-08T12:00:01.123456+05:45',
])
def test_observed_timestamp_preserves_ui_grammar(crm,value):
    t=target(crm);data=dict(packet(t),observed_at=value)
    assert EvidenceInput.model_validate(data).observed_at==value
    store=ResearchStore(crm);submitted=store.submit(data,key='timestamp')
    assert submitted['observed_at']==value
    assert store.get_evidence(submitted['id'])['observed_at']==value
