"""Same transfer invariants against an explicit disposable PostgreSQL schema."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
import test_contact_transfer as contract
URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def crm():
    schema='crm_test_'+uuid.uuid4().hex
    instance=None
    try:
        instance=CRM(URL,schema=schema,profile='synthetic')
        yield instance
    finally:
        if instance: instance.close()
        engine=create_engine(URL)
        with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        engine.dispose()

def test_preview_parity(crm): contract.test_preview_readonly_and_create_parity(crm)
def test_duplicates(crm): contract.test_duplicates_and_approved_valid_rows(crm)
def test_stale(crm): contract.test_stale_preview_and_replay(crm)
def test_rollback(crm,monkeypatch): contract.test_transaction_rollback(crm,monkeypatch)
def test_concurrent(crm): contract.test_concurrent_same_batch_and_stale_other_batch(crm)
def test_custom(crm): contract.test_custom_types_archiving_and_contact_type(crm)
def test_export(crm,monkeypatch): contract.test_export_complete_selected_filtered_and_formula_safe(crm,monkeypatch)
def test_legacy(crm): contract.test_legacy_create_idempotency_and_stage_default_unchanged(crm)
def test_snapshot(crm,monkeypatch): contract.test_export_snapshot_consistent(crm,monkeypatch)
def test_receipt_scope(crm): contract.test_receipt_collision_scope_and_exclusions(crm)
def test_nonfinite(crm): contract.test_nan_preview_serializable(crm)
def test_stages(crm): contract.test_export_linked_stage_and_custom_values(crm)
def test_api(crm): contract.test_api_workspace_errors_and_json_hygiene(crm)

@pytest.mark.parametrize('mutation',['missing','nullable','pk','columns','type'])
def test_receipt_schema(crm,mutation):
    from sqlalchemy import text
    from hermes_crm.domain import CRMError
    from hermes_crm.contact_transfer import ContactTransfer
    schema=crm.engine.get_execution_options()['schema_translate_map'][None]
    table=f'"{schema}".crm_idempotency'
    with crm.engine.begin() as conn:
        sql={'missing':f'DROP TABLE {table}', 'nullable':f'ALTER TABLE {table} ALTER COLUMN response DROP NOT NULL',
             'pk':f'ALTER TABLE {table} DROP CONSTRAINT crm_idempotency_pkey',
             'columns':f'ALTER TABLE {table} ADD COLUMN unexpected TEXT',
             'type':f'ALTER TABLE {table} ALTER COLUMN response TYPE INTEGER USING 0'}[mutation]
        conn.execute(text(sql))
    with pytest.raises(CRMError) as error: ContactTransfer(crm).catalog()
    assert error.value.status==503

@pytest.fixture
def artifact_setup(crm,tmp_path,monkeypatch):
    import sys,types
    from hermes_crm.contact_transfer import ContactTransfer
    module=types.ModuleType('plugins.plugin_storage')
    module.plugin_data_dir=lambda _:tmp_path
    monkeypatch.setitem(sys.modules,'plugins.plugin_storage',module)
    crm.create('contacts',dict(name='=Synthetic',email='synthetic@example.invalid',notes='ORDINARY_NOT_SELECTED'))
    return crm,ContactTransfer(crm),tmp_path

def test_artifact_replay(artifact_setup):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_replay_scope_plaintext_minimal_receipt(artifact_setup)

def test_artifact_missing(artifact_setup,monkeypatch):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_missing_unknown_never_recapture(artifact_setup,monkeypatch)

def test_artifact_snapshot_failure(artifact_setup,monkeypatch):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_snapshot_failure_is_durable(artifact_setup,monkeypatch)

def test_artifact_file_rollback(artifact_setup,monkeypatch):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_post_file_rollback_recovers_original(artifact_setup,monkeypatch)

def test_artifact_concurrent(artifact_setup,monkeypatch):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_concurrent_capture_once(artifact_setup,monkeypatch)

def test_export_api(crm,tmp_path,monkeypatch): contract.test_api_export_receipt_contract(crm,tmp_path,monkeypatch)

def test_artifact_reservation_failure(artifact_setup,monkeypatch):
    import test_contact_transfer_artifacts as artifacts
    artifacts.test_reservation_failure_no_capture_or_file(artifact_setup,monkeypatch)

def test_scope_compilation_mutation(crm):
    contract.test_scope_sqlalchemy_schema_map_mutation_keeps_preview_and_receipt(crm)

def test_scope_credentials(crm,monkeypatch):
    contract.test_scope_credential_rotation_retains_approved_import(crm,monkeypatch)
