"""Live PostgreSQL contract tests. Use only a disposable database.

HERMES_CRM_TEST_POSTGRES_URL=postgresql+psycopg://... pytest tests/test_postgres.py
Creates random crm_test_* schemas and drops only those schemas on teardown.
Never defaults to the application's configured database or SQLite.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM, CRMError
import test_crm as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def crm():
    schema = 'crm_test_' + uuid.uuid4().hex
    instance = None
    try:
        instance = CRM(URL, schema=schema, profile='postgres-contract-test')
        assert instance.backend == 'postgres'
        yield instance
    finally:
        if instance:
            instance.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()

CONTRACTS = [
    contract.test_vertical_slice_and_audit,
    contract.test_open_followups_filtered_before_list_limit,
    contract.test_deal_reassignment_updates_linked_tasks_atomically,
    contract.test_stale_edit_rejected_and_audited_once,
    contract.test_create_idempotency_and_conflicts,
    contract.test_concurrent_create_idempotency,
    contract.test_validation_and_rollback,
    contract.test_task_links_cannot_mismatch,
    contract.test_literal_search_and_filter,
    contract.test_related_contact_search_applies_before_limit,
    contract.test_utc_normalization,
    contract.test_demo_is_explicit_and_refuses_existing,
    contract.test_scheduler_payload_and_retry,
    contract.test_scheduler_uncertainty_blocks_duplicates,
    contract.test_scheduler_rejection_is_visible,
    contract.test_closed_or_past_task_not_scheduled,
    contract.test_api_and_security_boundaries,
    contract.test_saved_scheduler_failure_preserves_id_and_blocks_retry,
]

@pytest.mark.parametrize('check', CONTRACTS, ids=lambda check: check.__name__)
def test_live_postgres_contract(crm, check):
    check(crm)


def test_postgres_schema_isolation(crm):
    schema = 'crm_test_' + uuid.uuid4().hex
    other = CRM(URL, schema=schema, profile='other-test-profile')
    try:
        first = crm.create('contacts', {'name': 'First workspace'}, key='shared-key')
        second = other.create('contacts', {'name': 'Second workspace'}, key='shared-key')
        assert first['id'] != second['id']
        assert [c['name'] for c in crm.list('contacts')] == ['First workspace']
        assert [c['name'] for c in other.list('contacts')] == ['Second workspace']
        with pytest.raises(CRMError, match='not found'):
            other.get('contacts', first['id'])
        assert len(crm.activities()) == len(other.activities()) == 1
    finally:
        other.close()
        with crm.engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True, if_exists=True))


def test_postgres_utc_roundtrip(crm):
    item = crm.create('tasks', {'title': 'Offset time', 'due_at': '2026-11-09T10:00:00+05:30'})
    assert crm.get('tasks', item['id'])['due_at'] == '2026-11-09T04:30:00.000000+00:00'
    updated = crm.update('tasks', item['id'], {'version': 1, 'due_at': '2026-11-10T05:00:00-07:00'})
    assert crm.get('tasks', item['id'])['due_at'] == '2026-11-10T12:00:00.000000+00:00'
    assert updated['version'] == 2


def test_postgres_transaction_rolls_back_record_and_audit(crm, monkeypatch):
    original = crm._audit
    def failing_audit(*args):
        original(*args)
        raise RuntimeError('Injected failure after audit insert')
    monkeypatch.setattr(crm, '_audit', failing_audit)
    with pytest.raises(RuntimeError, match='Injected failure'):
        crm.create('contacts', {'name': 'Must roll back'}, key='failed-transaction')
    assert crm.list('contacts') == []
    assert crm.activities() == []
    monkeypatch.setattr(crm, '_audit', original)
    crm.create('contacts', {'name': 'Must roll back'}, key='failed-transaction')
    assert len(crm.activities()) == 1


def test_postgres_workspace_tokens_are_stable(crm):
    first = crm.workspace_token()
    assert crm.workspace_token() == first
    other = CRM(URL, schema=crm.engine.get_execution_options()['schema_translate_map'][None])
    try:
        assert other.workspace_token() == first
    finally:
        other.close()


def test_postgres_demo_seed_is_atomic(crm, monkeypatch):
    from hermes_crm.demo import seed
    original = CRM.create
    count = 0
    def interrupted(self, *args, **kwargs):
        nonlocal count
        count += 1
        if count == 4:
            raise RuntimeError('Injected demo interruption')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(CRM, 'create', interrupted)
    with pytest.raises(RuntimeError, match='interruption'):
        seed(crm)
    assert crm.list('contacts') == []
    assert crm.activities() == []
    monkeypatch.setattr(CRM, 'create', original)
    seed(crm)
    assert crm.overview()['contacts'] == 8
