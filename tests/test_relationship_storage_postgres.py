"""Run relationship contracts only against an explicit disposable PostgreSQL URL."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
import test_relationship_storage as contracts
URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')
@pytest.fixture
def crm():
    schema='crm_rel_test_'+uuid.uuid4().hex
    crm=None
    try:
        crm=CRM(URL,schema=schema,profile='relationship-test')
        yield crm
    finally:
        if crm: crm.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally: engine.dispose()

def test_legacy(crm): contracts.test_lazy_schema_and_legacy_preservation(crm)
def test_links(crm): contracts.test_company_duplicates_link_replay_archive_and_scope(crm)
def test_events(crm): contracts.test_event_lifecycle_revisions_minimization_no_side_effects(crm)
def test_tasks(crm): contracts.test_event_tasks_atomic_versioned_and_no_scheduler(crm)
def test_newer(crm): contracts.test_newer_schema_fail_closed(crm)
def test_partial(crm): contracts.test_partial_and_newer_schema_fail_closed(crm)
def test_rollback(crm,monkeypatch): contracts.test_rollback_and_expected_versions(crm,monkeypatch)
def test_task_rollback(crm,monkeypatch): contracts.test_future_completion_and_atomic_task_failure(crm,monkeypatch)
def test_unlink_target_version(crm): contracts.test_unlink_reviews_event_target_version_and_receipt(crm)
@pytest.mark.parametrize('term',['%', '_', '\\', "' OR 1=1 --"])
def test_literal_search(crm,term): contracts.test_literal_company_event_search(crm,term)

def test_live_foreign_key_target_schema_validation(crm):
    """Reject a wrong target even when search_path hides its schema in reflection."""
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateSchema
    from hermes_crm.domain import CRMError
    from hermes_crm.relationship_schema import check_schema, contact_companies
    from hermes_crm.report_store import schema_name
    contracts.company(crm)
    source=schema_name(crm)
    foreign='crm_relationship_foreign_'+uuid.uuid4().hex
    with crm.engine.begin() as conn:
        assert check_schema(crm,conn)
        fks=inspect(conn).get_foreign_keys(contact_companies.name,schema=source)
        assert all(f['referred_schema']==source for f in fks)
    try:
        with crm.engine.begin() as conn:
            conn.execute(CreateSchema(foreign))
            quote=conn.dialect.identifier_preparer.quote
            src=quote(source);dst=quote(foreign)
            conn.exec_driver_sql(f'CREATE TABLE {dst}.crm_contacts (id VARCHAR(36) PRIMARY KEY)')
            fk=next(f for f in fks if f['referred_table']=='crm_contacts')
            conn.exec_driver_sql(f'ALTER TABLE {src}.crm_contact_companies DROP CONSTRAINT {quote(fk["name"])}')
            conn.exec_driver_sql(f'ALTER TABLE {src}.crm_contact_companies ADD CONSTRAINT wrong_contact_target FOREIGN KEY (contact_id) REFERENCES {dst}.crm_contacts (id)')
            conn.exec_driver_sql(f'SET LOCAL search_path TO {dst}, {src}, public')
            with pytest.raises(CRMError,match='target schema'):
                check_schema(crm,conn)
    finally:
        with crm.engine.begin() as conn: conn.execute(DropSchema(foreign,cascade=True,if_exists=True))


def test_concurrent_initialization_and_exact_replay(crm):
    from concurrent.futures import ThreadPoolExecutor
    from hermes_crm.companies import CompanyStore
    from hermes_crm.report_store import schema_name
    from hermes_crm.relationship_schema import operations
    from sqlalchemy import select, func
    schema=schema_name(crm)
    def create(_):
        other=CRM(URL,schema=schema,profile=crm.profile)
        try: return contracts.company(other)
        finally: other.close()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(create,range(8)))
    assert all(row==results[0] for row in results)
    assert CompanyStore(crm).list()['total']==1
    with crm.engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(operations)).scalar_one()==1
