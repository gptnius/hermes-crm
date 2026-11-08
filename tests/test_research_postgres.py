"""Opt-in contracts for an explicitly disposable PostgreSQL URL, never live data."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM,CRMError
from hermes_crm.report_store import schema_name
from hermes_crm.research_store import ResearchStore
import test_research as contracts

URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')
@pytest.fixture
def crm():
    schema='crm_research_test_'+uuid.uuid4().hex
    crm=None
    try:
        crm=CRM(URL,schema=schema,profile='research-test')
        yield crm
    finally:
        if crm:crm.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as conn:conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally:engine.dispose()

@pytest.mark.parametrize('kind',['contacts','companies'])
def test_apply_replay(crm,kind):contracts.test_apply_replay_and_minimized_storage(crm,kind)
def test_aba_lifecycle(crm):contracts.test_aba_and_lifecycle(crm)
def test_archive(crm):contracts.test_company_archive(crm)
def test_length_aliasing(crm):contracts.test_limits_and_aliasing(crm)
@pytest.mark.parametrize('point',['audit','proposal','receipt'])
def test_rollback(crm,monkeypatch,point):contracts.test_atomic_rollback(crm,monkeypatch,point)
def test_dismiss_newer(crm):contracts.test_dismiss_and_schema_version(crm)
def test_scope(crm):contracts.test_cross_scope_reads_and_receipts(crm)
def test_export_partial(crm):contracts.test_scoped_export_and_partial_schema(crm)
def test_provenance_pages(crm):contracts.test_provenance_and_stable_pages(crm)
def test_proposal_digest(crm):contracts.test_stored_proposal_list_validates_shape_and_digest(crm)
def test_invalid_receipt(crm):contracts.test_malformed_operation_never_committed_or_replayed(crm,'{"status":"applied"}')
def test_invalid_evidence(crm):contracts.test_stored_evidence_revalidated_even_with_consistent_digest(crm,{'claims':[123]})

def test_reads_never_initialize(crm):
    from sqlalchemy import inspect
    from hermes_crm.research_schema import OWNED_TABLES
    t=contracts.target(crm);s=ResearchStore(crm)
    assert s.list('evidence','contacts',t['id'])['items']==[]
    assert s.receipt('none')['state']=='unknown'
    with crm.engine.connect() as c:assert not any(inspect(c).has_table(t.name,schema=schema_name(crm)) for t in OWNED_TABLES)


def test_two_proposals_only_one_append(crm):
    s,t,e,p=contracts.setup(crm)
    second=s.propose(dict(evidence_id=e['id'],evidence_digest=e['digest'],evidence_lifecycle_version=1,target_version=1,addition='Second independent proposal'),key='p2')
    schema=schema_name(crm)
    def apply(pair):
        proposal,key=pair
        other=CRM(URL,schema=schema,profile=crm.profile)
        try:
            try:return ResearchStore(other).review(proposal['id'],contracts.review(proposal),apply=True,key=key)
            except CRMError as error:return error.status
        finally:other.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(apply,[(p,'apply-1'),(second,'apply-2')]))
    assert sum(isinstance(r,dict) for r in results)==1
    assert results.count(409)==1
    assert crm.get('contacts',t['id'])['version']==2
    states=[s.preview(x['id'])['status'] for x in (p,second)]
    assert sorted(states)==['applied','pending']


def test_concurrent_same_key_replay(crm):
    s,t,e,p=contracts.setup(crm);schema=schema_name(crm)
    def apply(_):
        other=CRM(URL,schema=schema,profile=crm.profile)
        try:return ResearchStore(other).review(p['id'],contracts.review(p),apply=True,key='same-apply')
        finally:other.close()
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(apply,range(8)))
    assert all(result==results[0] for result in results)
    assert crm.get('contacts',t['id'])['version']==2
