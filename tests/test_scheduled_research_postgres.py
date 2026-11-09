"""Opt-in disposable PostgreSQL contracts; never connect without explicit URL."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
from hermes_crm.companies import CompanyStore
from hermes_crm.scheduled_research import ScheduledResearchStore
import test_scheduled_research as contracts

URL=os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark=pytest.mark.skipif(not URL,reason='Requires explicit disposable PostgreSQL URL')
def disposable_schema_name():
    return 'crm_sr_test_'+uuid.uuid4().hex


@pytest.fixture(params=['contacts','companies'])
def setup(request):
    schema=disposable_schema_name()
    crm=None
    try:
        crm=CRM(URL,schema=schema,profile='synthetic')
        t=(crm.create('contacts',{'name':'Synthetic subject','notes':'Private existing text'}) if request.param=='contacts' else
            CompanyStore(crm).create({'name':'Synthetic subject','notes':'Private existing text'},actor='test',key='company'))
        task=crm.create('tasks',{'title':'Prepare synthetic brief','due_at':'2030-04-02T12:00:00Z'})
        data=dict(task_id=task['id'],task_version=task['version'],human_owner='Synthetic owner',
            target_kind=request.param,target_id=t['id'],target_version=1,
            public_question='What public products does Synthetic Example offer?',run_at='2030-04-01T12:30:41+00:00',
            research='web',propose_note=True,max_sources=2)
        yield crm,ScheduledResearchStore(crm),t,data
    finally:
        if crm:crm.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as c:c.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally:engine.dispose()

def test_flow(setup):contracts.test_complete_flow_keeps_notes_and_old_contract(setup)
def test_atomic_rollback(setup):contracts.test_receipt_failure_rolls_back_evidence_and_execution_binding(setup)
def test_task_binding(setup):contracts.test_task_version_status_and_filtered_visibility(setup)
def test_target_stale(setup):contracts.test_stale_target_blocks_new_write_but_exact_receipt_replays(setup)
def test_concurrency(setup):contracts.test_concurrent_schedule_and_evidence_same_key(setup)

# Same assertions run independently on SQLite in the portable contract module.
import test_scheduled_research_database_contracts as database_contracts
import test_scheduled_research_recovery as recovery_contracts
from hermes_crm.protection import Keyring


def test_page_task_filter_total_offset(setup):
    database_contracts.test_page_task_filter_total_and_offset(setup)


@pytest.mark.parametrize('damage',['absent','partial','newer','malformed'])
def test_page_optional_schema_noninitializing(setup,damage):
    database_contracts.test_page_optional_schema_is_read_only_and_fail_closed(setup,damage)


@pytest.mark.parametrize('change',['task_changed','task_completed','target_changed'])
@pytest.mark.parametrize('outcome',['blocked','failed'])
def test_stale_source_report(setup,change,outcome):
    contracts.test_stale_source_can_report_blocker_but_cannot_write_or_complete(setup,change,outcome)


@pytest.mark.parametrize('setup',['companies'],indirect=True)
@pytest.mark.parametrize('outcome',['blocked','failed'])
def test_archived_company_report(setup,outcome):
    # Contacts have no archive operation: exclude at collection, not runtime skip.
    contracts.test_stale_source_can_report_blocker_but_cannot_write_or_complete(setup,'target_archived',outcome)


def test_completed_inactive_cancel_does_not_pause(setup):
    contracts.test_cancel_observes_exact_inactive_job_before_pause(setup,'completed')


def test_postgres_export_to_sqlite_restore_quarantines_authority(setup,tmp_path):
    ring=Keyring('test-export',{'test-export':b'e'*32})
    recovery_contracts.test_export_recovery_quarantines_scheduled_authority(setup,ring,tmp_path)
