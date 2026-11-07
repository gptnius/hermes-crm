"""Real PostgreSQL contracts with synthetic hosts only; explicit disposable URL required.

No listener is started by this file. It uses only random crm_test_* schemas in
HERMES_CRM_TEST_POSTGRES_URL. Do not run with ambient accounts or an unapproved DB.
"""
import os

import pytest
from sqlalchemy import inspect, text

from hermes_crm.domain import CRMError
from hermes_crm.native_work import NativeWorkStore
from hermes_crm.native_work_operations import WorkOperationStore, operations
from test_native_work_postgres import crm_factory
import test_native_work_operations as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def setup(crm_factory):
    crm = crm_factory()
    task = crm.create('tasks', {'title':'Synthetic internal analysis', 'due_at':'2099-05-01T00:00:00Z'})
    assignment = NativeWorkStore(crm).create(task_id=task['id'], human_owner='Synthetic owner',
        prompt='  Original instructions\n', success_criteria='Full original criteria',
        run_at='2099-04-01T12:30:41Z', idempotency_key='assignment')
    return crm, WorkOperationStore(crm, initialize=True), assignment, task


REPLACED = {'test_snapshot_and_idempotency_survive_changes_and_restart',
            'test_status_no_table_creation_and_foreign_scope_rejected',
            'test_existing_tables_unchanged', 'test_incompatible_operation_schema_not_migrated'}
for name, check in vars(contract).items():
    if name.startswith('test_') and callable(check) and name not in REPLACED:
        globals()['test_postgres_' + name[5:]] = check


def test_postgres_schema_and_foreign_workspace_rejection(setup, crm_factory):
    crm, store, assignment, task = setup
    operation = contract.prepare(setup)
    schema = crm.engine.get_execution_options()['schema_translate_map'][None]
    assert operations.name in inspect(crm.engine).get_table_names(schema=schema)
    WorkOperationStore(crm, initialize=True)
    other = crm_factory()
    before = inspect(other.engine).get_table_names(schema=other.engine.get_execution_options()['schema_translate_map'][None])
    with pytest.raises(CRMError, match='not found'): WorkOperationStore(other).get(operation['id'])
    assert inspect(other.engine).get_table_names(schema=other.engine.get_execution_options()['schema_translate_map'][None]) == before


def test_postgres_incompatible_operation_schema_not_migrated(crm_factory):
    crm = crm_factory()
    schema = crm.engine.get_execution_options()['schema_translate_map'][None]
    with crm.engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE "{schema}".crm_native_work_operations (id TEXT PRIMARY KEY)'))
    with pytest.raises(CRMError, match='explicit migration'): WorkOperationStore(crm, initialize=True)
    assert [c['name'] for c in inspect(crm.engine).get_columns(operations.name, schema=schema)] == ['id']


def test_postgres_snapshot_idempotence_survives_task_mutation(setup):
    original = contract.prepare(setup)
    setup[0].update('tasks', setup[3]['id'], {'version':1, 'title':'Changed'})
    assert contract.prepare(setup) == original
    assert WorkOperationStore(setup[0]).get(original['id']) == original
