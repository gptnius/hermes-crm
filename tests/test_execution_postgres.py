"""Synthetic execution-store contracts on an explicitly disposable PostgreSQL DB.

Set HERMES_CRM_TEST_POSTGRES_URL; never reads the application's database URL.
Only random crm_test_* schemas are created/dropped. No host calls are made.
"""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM, CRMError, tasks
from hermes_crm.execution import ExecutionStore, assignments, occurrences
import test_execution as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def setup(monkeypatch):
    schema = 'crm_test_' + uuid.uuid4().hex
    # Shared contracts reopen CRM instances. Keep those in this same random schema.
    monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
    crm = None
    try:
        crm = CRM(URL, schema=schema, profile='synthetic')
        task = crm.create('tasks', {'title': 'Internal analysis', 'due_at': '2030-01-01T00:00:00Z'})
        yield crm, ExecutionStore(crm), task
    finally:
        if crm:
            crm.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


# Preserve pytest parameter marks so every shared contract case runs on PostgreSQL.
for _name, _check in vars(contract).items():
    if _name.startswith('test_') and callable(_check):
        globals()['test_postgres_contract_' + _name[5:]] = _check


def test_postgres_completion_wins_before_dispatch_guard(setup, monkeypatch):
    crm, store, task = setup
    assignment = contract.create(setup)
    validated, completed = Event(), Event()
    original = store._validate_task

    def pause_after_validation(conn, assignment):
        original(conn, assignment)
        validated.set()
        assert completed.wait(10), 'Concurrent completion did not finish'

    monkeypatch.setattr(store, '_validate_task', pause_after_validation)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(contract.dispatch, store, assignment)
        try:
            assert validated.wait(10), 'Dispatch did not reach validation'
            crm.update('tasks', task['id'], {'version': 1, 'status': 'done'})
        finally:
            completed.set()
        with pytest.raises(CRMError, match='Source task changed'):
            result.result(timeout=10)
    row = contract.current(store.get(assignment['id']))
    assert row['dispatch_started'] == 0 and row['state'] == 'pending'
    assert crm.get('tasks', task['id'])['status'] == 'done'


def test_postgres_failed_occurrence_creation_rolls_back_intent(setup, monkeypatch):
    crm, store, _ = setup
    original = store._new_occurrence

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('Injected occurrence failure')

    monkeypatch.setattr(store, '_new_occurrence', fail_after_insert)
    with pytest.raises(RuntimeError, match='Injected occurrence failure'):
        contract.create(setup)
    with crm.engine.connect() as conn:
        assert conn.execute(select(assignments)).all() == []
        assert conn.execute(select(occurrences)).all() == []
    monkeypatch.setattr(store, '_new_occurrence', original)
    assert contract.create(setup)['occurrences'][0]['state'] == 'pending'
