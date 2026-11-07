"""Real PostgreSQL storage tests with synthetic host responses only.

Requires HERMES_CRM_TEST_POSTGRES_URL pointing to a disposable database.
Creates/drops only random crm_test_* schemas; never creates real jobs.
The six SQLite-specific shared test functions below have PG replacements,
not skipped cases counted as successful PostgreSQL coverage.
"""
import os
import uuid

import pytest
from sqlalchemy import MetaData, String, UniqueConstraint, create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM, CRMError, tasks
from hermes_crm.native_work import NativeWorkStore, assignments, events, reports
import test_native_work as contract
import test_native_work_cancellation as cancellation_contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def crm_factory(monkeypatch):
    instances = []
    schemas = []
    def factory(profile='synthetic'):
        schema = 'crm_test_' + uuid.uuid4().hex
        schemas.append(schema)
        crm = CRM(URL, schema=schema, profile=profile)
        instances.append(crm)
        if len(schemas) == 1:
            monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
        return crm
    yield factory
    for crm in instances:
        crm.close()
    engine = create_engine(URL)
    try:
        with engine.begin() as conn:
            for schema in schemas:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
    finally:
        engine.dispose()


@pytest.fixture
def setup(crm_factory):
    crm = crm_factory()
    task = crm.create('tasks', {'title': 'Synthetic internal analysis', 'due_at': '2030-05-01T00:00:00Z'})
    return crm, NativeWorkStore(crm), task


def schema_of(crm):
    return crm.engine.get_execution_options()['schema_translate_map'][None]


REPLACED = {
    'test_new_schema_leaves_existing_crm_and_execution_tables_unchanged',
    'test_incompatible_new_table_fails_without_migration',
    'test_scope_is_current_store_not_just_custom_profile_name',
    'test_same_columns_with_incompatible_constraints_fail_closed',
    'test_report_transaction_rolls_back_if_receipt_insert_fails',
    'test_create_transaction_rolls_back_if_event_insert_fails',
}
for _name, _check in vars(contract).items():
    if _name.startswith('test_') and callable(_check) and _name not in REPLACED:
        globals()['test_postgres_contract_' + _name[5:]] = _check

for _name, _check in vars(cancellation_contract).items():
    if _name.startswith('test_') and callable(_check):
        globals()['test_postgres_cancellation_' + _name[5:]] = _check


def test_postgres_only_new_tables_and_compatible_inspector(crm_factory):
    from hermes_crm.execution import ExecutionStore
    crm = crm_factory()
    ExecutionStore(crm)
    schema = schema_of(crm)
    inspector = inspect(crm.engine)
    before_tables = set(inspector.get_table_names(schema=schema))
    before_columns = {name: str(inspector.get_columns(name, schema=schema)) for name in before_tables}
    NativeWorkStore(crm)
    NativeWorkStore(crm)
    after = inspect(crm.engine)
    assert set(after.get_table_names(schema=schema)) - before_tables == {
        'crm_native_assignments', 'crm_native_work_events', 'crm_native_work_reports'}
    assert all(str(after.get_columns(name, schema=schema)) == columns for name, columns in before_columns.items())


def test_postgres_incompatible_table_not_migrated(crm_factory):
    crm = crm_factory()
    schema = schema_of(crm)
    with crm.engine.begin() as conn:
        conn.execute(text(f'CREATE TABLE "{schema}".crm_native_assignments (id TEXT PRIMARY KEY)'))
    with pytest.raises(CRMError, match='explicit migration'):
        NativeWorkStore(crm)
    assert [col['name'] for col in inspect(crm.engine).get_columns('crm_native_assignments', schema=schema)] == ['id']


@pytest.mark.parametrize('defect', ['missing_unique', 'wrong_type', 'nullable', 'missing_foreign_key'])
def test_postgres_rejects_incompatible_constraints(crm_factory, defect):
    crm = crm_factory()
    cloned = MetaData()
    tasks.to_metadata(cloned)
    table = assignments.to_metadata(cloned)
    if defect == 'missing_unique':
        for constraint in list(table.constraints):
            if isinstance(constraint, UniqueConstraint): table.constraints.remove(constraint)
    elif defect == 'wrong_type': table.c.profile.type = String(10)
    elif defect == 'nullable': table.c.profile.nullable = True
    else:
        for constraint in list(table.foreign_key_constraints): table.constraints.remove(constraint)
    table.create(crm.engine)
    with pytest.raises(CRMError, match='explicit migration'):
        NativeWorkStore(crm)


def test_postgres_schema_and_profile_isolation(setup, crm_factory):
    a = contract.create(setup)
    other = crm_factory()
    store = NativeWorkStore(other)
    assert store.list() == []
    with pytest.raises(CRMError, match='current workspace/profile'): store.get(a['id'])
    foreign = CRM(URL, schema=schema_of(setup[0]), profile='other')
    try:
        store = NativeWorkStore(foreign)
        assert store.list() == []
        with pytest.raises(CRMError, match='current workspace/profile'): store.get(a['id'])
    finally:
        foreign.close()


def fail_on_insert(table_name):
    def reject(conn, cursor, statement, parameters, context, executemany):
        # Inspect the compiled table instead of SQLite-specific unqualified SQL.
        if context.compiled is not None:
            stmt = context.compiled.statement
            if getattr(stmt, 'is_insert', False) and stmt.table.name == table_name:
                raise RuntimeError('Synthetic insertion failure')
    return reject


def test_postgres_report_transaction_rollback(setup):
    host, a = contract.scheduled(setup)
    reject = fail_on_insert(reports.name)
    event.listen(setup[0].engine, 'before_cursor_execute', reject)
    try:
        with pytest.raises(RuntimeError, match='Synthetic'):
            contract.report(setup, contract.identity(host, a), a)
    finally:
        event.remove(setup[0].engine, 'before_cursor_execute', reject)
    assert setup[1].get(a['id']) == a


def test_postgres_create_transaction_rollback(setup):
    reject = fail_on_insert(events.name)
    event.listen(setup[0].engine, 'before_cursor_execute', reject)
    try:
        with pytest.raises(RuntimeError, match='Synthetic'):
            contract.create(setup)
    finally:
        event.remove(setup[0].engine, 'before_cursor_execute', reject)
    assert setup[1].list() == []
    with setup[0].engine.connect() as conn:
        assert conn.execute(select(events)).all() == []
    assert contract.create(setup)['state'] == 'pending'


def test_postgres_foreign_key_and_unique_constraints_enforced(setup):
    crm, store, _ = setup
    a = contract.create(setup)
    with pytest.raises(IntegrityError):
        with crm.engine.begin() as conn:
            conn.execute(assignments.update().where(assignments.c.id == a['id']).values(task_id='missing'))
    with crm.engine.connect() as conn:
        duplicate = dict(conn.execute(select(assignments).where(assignments.c.id == a['id'])).mappings().one())
    duplicate['id'] = str(uuid.uuid4())
    with pytest.raises(IntegrityError):
        with crm.engine.begin() as conn:
            conn.execute(assignments.insert().values(**duplicate))
    assert store.get(a['id']) == a
    assert len(store.list()) == 1
