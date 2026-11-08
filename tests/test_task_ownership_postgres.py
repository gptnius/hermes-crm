"""Run only against an explicitly supplied disposable PostgreSQL database."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
import test_task_ownership as contracts
URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')
@pytest.fixture
def crm():
    schema='crm_owner_test_'+uuid.uuid4().hex
    instance=None
    try:
        instance=CRM(URL,schema=schema)
        yield instance
    finally:
        if instance: instance.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally: engine.dispose()

def test_legacy(crm): contracts.test_lazy_and_legacy_receipt(crm)
def test_required(crm): contracts.test_required_legacy_edit_default_and_version(crm)
def test_scoped(crm): contracts.test_optional_clear_scoped_no_inference(crm)
def test_policy(crm): contracts.test_policy_retry_and_stale_forms(crm)
def test_atomic(crm,monkeypatch): contracts.test_atomic_rollback(crm,monkeypatch)
def test_newer(crm): contracts.test_schema_newer_partial_reject(crm)
def test_partial(crm): contracts.test_schema_partial_no_repair(crm)
def test_filters(crm): contracts.test_filters_and_projection(crm)
def test_events(crm): contracts.test_event_task_shared_enforcement(crm)
def test_receipts(crm): contracts.test_scoped_create_receipts_and_unknown_retry(crm)
def test_assignment(crm): contracts.test_assignment_snapshot_not_rewritten(crm)
def test_report(crm): contracts.test_report_owner_missing_and_exact(crm)
def test_export(crm): contracts.test_export_scope_and_policy_audit(crm)
def test_maintenance(crm): contracts.test_relationship_maintenance_does_not_apply_default(crm)
def test_receipt_lanes(crm): contracts.test_receipt_lane_changes_rejected(crm)
