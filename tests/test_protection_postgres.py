"""Synthetic-only protection tests on explicit disposable PostgreSQL target."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
import test_protection as contract
from test_protection import ring

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def crm():
    schema = 'crm_test_' + uuid.uuid4().hex
    instance = None
    try:
        instance = CRM(URL, schema=schema, profile='synthetic')
        yield instance
    finally:
        if instance: instance.close()
        engine = create_engine(URL)
        with engine.begin() as conn: conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        engine.dispose()

def test_concurrent_notes(crm,ring): contract.test_concurrent_zero_note_create(crm,ring)
def test_note_binding(crm,ring): contract.test_tamper_cross_record_workspace_and_wrong_key(crm,ring)
def test_export_roundtrip(crm,ring): contract.test_export_exact_and_bounded(crm,ring)
def test_rollback(crm,ring,monkeypatch): contract.test_write_rollback(crm,ring,monkeypatch)
def test_artifact(crm,ring,tmp_path,monkeypatch): contract.test_export_artifact_replay_permissions_and_tamper(crm,ring,tmp_path,monkeypatch)
def test_export_tombstone(crm,ring,tmp_path,monkeypatch): contract.test_export_tombstone_and_readonly_recovery(crm,ring,tmp_path,monkeypatch)
@pytest.mark.parametrize('mutation',['missing','nullable','pk','columns','type','version'])
def test_schema_validation(crm,ring,mutation):
    # Tests use schema-bound DDL via SQLAlchemy rather than an unqualified target.
    from hermes_crm.protection import ProtectionStore,state,notes
    from hermes_crm.domain import CRMError
    from sqlalchemy import text
    store=ProtectionStore(crm);record=contract.contact(crm)
    schema=crm.engine.get_execution_options()['schema_translate_map'][None]
    with crm.engine.begin() as conn:
        store.initialize(conn)
        if mutation=='version': conn.execute(state.update().values(version=2))
        elif mutation=='missing': conn.execute(text(f'DROP TABLE "{schema}".crm_protected_operations'))
        elif mutation=='columns': conn.execute(text(f'ALTER TABLE "{schema}".crm_protected_notes ADD COLUMN unexpected TEXT'))
        elif mutation=='nullable': conn.execute(text(f'ALTER TABLE "{schema}".crm_protected_notes ALTER COLUMN envelope DROP NOT NULL'))
        elif mutation=='pk': conn.execute(text(f'ALTER TABLE "{schema}".crm_protected_notes DROP CONSTRAINT crm_protected_notes_pkey'))
        else: conn.execute(text(f'ALTER TABLE "{schema}".crm_protected_notes ALTER COLUMN version TYPE TEXT'))
    for call in (lambda:store.status('contacts',record['id']),lambda:contract.save(store,record,ring),lambda:store.export(ring)):
        with pytest.raises(CRMError) as error: call()
        assert error.value.status==503
def test_snapshot_failure_reservation(crm,ring,tmp_path,monkeypatch): contract.test_export_snapshot_failure_keeps_reservation(crm,ring,tmp_path,monkeypatch)
def test_file_rollback_recovery(crm,ring,tmp_path,monkeypatch): contract.test_export_file_survives_receipt_rollback(crm,ring,tmp_path,monkeypatch)
def test_same_id_one_capture(crm,ring,tmp_path,monkeypatch): contract.test_export_concurrent_same_id_one_capture(crm,ring,tmp_path,monkeypatch)
