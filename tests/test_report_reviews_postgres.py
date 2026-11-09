"""Opt-in disposable PostgreSQL acknowledgement contracts; no inferred database."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
import test_report_reviews as contracts
import test_report_review_recovery as recovery

URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')

def disposable_schema_name():
    return 'crm_review_test_'+uuid.uuid4().hex

@pytest.fixture(params=['native','scheduled_research','scheduled_company'])
def setup(request):
    schema=disposable_schema_name()
    crm=None
    try:
        crm=CRM(URL,schema=schema,profile='synthetic')
        yield contracts.make_setup(crm,request.param)
    finally:
        if crm:crm.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as c:c.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally:engine.dispose()


def test_lifecycle(setup):contracts.test_acknowledge_revoke_and_historical_retry_no_side_effects(setup)
def test_source_context(setup):contracts.test_source_changes_need_fresh_explicit_context_and_retry_is_historical(setup)
def test_target_context(setup):contracts.test_stale_target_requires_explicit_warning(setup)
def test_concurrent_writes(setup):contracts.test_concurrent_duplicate_and_conflicting_writes(setup)
def test_rollback(setup):contracts.test_receipt_failure_rolls_back_event(setup)
def test_integrity(setup):contracts.test_report_tamper_and_cross_scope_fail_closed(setup)
def test_schema(setup):contracts.test_partial_and_newer_schema_fail_without_repair(setup)
def test_new_report(setup):contracts.test_native_new_report_remains_unacknowledged(setup)
def test_export_recovery(setup,tmp_path):recovery.test_export_recovery_quarantines_reviews(setup,tmp_path)
def test_mixed_scope_export(setup):recovery.test_mixed_scope_export_filters_review_rows(setup)

@pytest.mark.parametrize('damage',['missing_family','missing_report','wrong_context','wrong_binding','wrong_receipt','extra_field','sequence','scope'])
def test_malformed_export(setup,damage):recovery.test_malformed_review_export_rejected(setup,damage)

def test_query_batching(setup):contracts.test_review_queries_are_batched_for_history_and_coverage(setup)
def test_schema_newer_column(setup):contracts.test_full_schema_incompatible_column_rejected(setup)
def test_assignment_cas(setup):contracts.test_wrong_report_identity_and_assignment_context(setup)
def test_scope_isolation(setup):contracts.test_same_workspace_other_profile_cannot_read_receipt(setup)
def test_cancelled_history(setup,tmp_path):contracts.test_cancel_after_report_then_review_and_export(setup,tmp_path)

@pytest.mark.parametrize('reason',['cancelled','superseded'])
@pytest.mark.parametrize('review_before',[False,True])
def test_invalidated_history(setup,reason,review_before,tmp_path):
    contracts.test_invalidated_native_report_remains_reviewable(setup,reason,review_before,tmp_path)
