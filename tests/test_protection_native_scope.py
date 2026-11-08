"""Synthetic current-scope exports; optional disposable PostgreSQL parity.

No real host, configured protection key, provider or active profile is accessed.
"""
import json
import os
import uuid

import pytest
from sqlalchemy import MetaData, UniqueConstraint, create_engine, event, inspect, select, text
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM, CRMError
from hermes_crm.native_work import NativeWorkStore, assignments, events, reports
from hermes_crm.native_work_operations import WorkOperationStore, operations
from hermes_crm.protection import Keyring, ProtectionStore, decrypt_export, owned_tables
from test_native_work import Host, identity

NATIVE = (assignments, events, reports, operations)
URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')


@pytest.fixture(params=['sqlite', 'postgres'])
def crm(request, tmp_path):
    if request.param == 'postgres':
        if not URL:
            pytest.skip('Requires explicit disposable PostgreSQL URL')
        schema = 'crm_test_' + uuid.uuid4().hex
        value = CRM(URL, profile='synthetic', schema=schema)
    else:
        schema = None
        value = CRM('sqlite:///' + str(tmp_path / 'synthetic.db'), profile='synthetic')
    yield value
    value.close()
    if schema:
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


def seed(crm, *, profile='synthetic', workspace=None, key='seed'):
    previous = crm.profile
    crm.profile = profile
    try:
        task = crm.create('tasks', {'title': 'Shared task ' + key, 'due_at': '2099-05-01T00:00:00Z'})
        store = NativeWorkStore(crm, workspace=workspace)
        saved = store.create(task_id=task['id'], human_owner='Synthetic owner', prompt='Private intent '+key,
            success_criteria='Synthetic only', run_at='2099-04-01T12:30:41Z', idempotency_key=key)
        host = Host()
        host.profile_name = profile
        saved = store.schedule(host, saved['id'], session_id='synthetic-session', task_id='synthetic-task')
        identity(host, saved, profile=profile, execution_id='execution-'+key)
        saved = store.report(host, saved['id'], generation=1, summary='Private result '+key)
        op_store = WorkOperationStore(crm, initialize=True)
        # Explicit foreign-workspace fixture; no production scope is rebound.
        op_store.workspace, op_store.work = store.workspace, store
        op = op_store.prepare(verb='check', assignment_id=saved['id'], expected_assignment_version=saved['version'],
            intended_session_id='synthetic-session', idempotency_key='check-'+key)
        return dict(assignment=saved, operation=op, task=task)
    finally:
        crm.profile = previous


def export(crm):
    store = ProtectionStore(crm)
    ring = Keyring('synthetic', {'synthetic': bytes(range(32))})
    return decrypt_export(store.export(ring), ring, workspace=store.workspace, profile=crm.profile)


def table_rows(crm):
    with crm.engine.connect() as conn:
        return {table.name: [dict(r) for r in conn.execute(select(table)).mappings()] for table in NATIVE}


def assert_rows_equal(actual, expected):
    normalize = lambda rows: sorted(json.dumps(row, sort_keys=True) for row in rows)
    assert normalize(actual) == normalize(expected)


def test_normal_native_export_exact_and_shared_tables_preserved(crm):
    seed(crm)
    before = table_rows(crm)
    value = export(crm)
    assert set(value) == {'format', 'version', 'workspace', 'profile', 'tables'}
    assert value['format'] == 'hermes-crm-export' and value['version'] == 1
    for table in NATIVE:
        assert_rows_equal(value['tables'][table.name], before[table.name])
    from hermes_crm.domain import tasks
    with crm.engine.connect() as conn:
        shared_tasks = [dict(r) for r in conn.execute(select(tasks)).mappings()]
    assert_rows_equal(value['tables']['crm_tasks'], shared_tasks)
    assert owned_tables()['crm_tasks'].name == 'crm_tasks'
    assert table_rows(crm) == before


def test_export_excludes_mixed_scopes_and_keeps_all_shared_tasks(crm):
    local = seed(crm, key='local')
    foreign = [seed(crm, profile='other', key='foreign-profile'),
        seed(crm, workspace=str(uuid.uuid4()), key='foreign-workspace'),
        seed(crm, profile='other', workspace=str(uuid.uuid4()), key='foreign-both')]
    before = table_rows(crm)
    assert [r['id'] for r in NativeWorkStore(crm, initialize=False).list()] == [local['assignment']['id']]
    tables = export(crm)['tables']
    for table in NATIVE:
        expected = [row for row in before[table.name] if
            (row['id'] if table is assignments else row['assignment_id']) == local['assignment']['id']]
        assert_rows_equal(tables[table.name], expected)
    assert {r['id'] for r in tables['crm_tasks']} == {x['task']['id'] for x in [local, *foreign]}
    assert table_rows(crm) == before


@pytest.mark.parametrize('table', [reports, operations], ids=['reports', 'operations'])
@pytest.mark.parametrize('direction', ['local_child_foreign_parent', 'foreign_child_local_parent'])
def test_export_requires_both_child_and_parent_scope(crm, table, direction):
    local = seed(crm, key='local')
    foreign = seed(crm, profile='other', key='foreign')
    source = local if direction == 'local_child_foreign_parent' else foreign
    target = foreign if direction == 'local_child_foreign_parent' else local
    with crm.engine.begin() as conn:
        row = dict(conn.execute(select(table).where(table.c.assignment_id == source['assignment']['id'])).mappings().one())
        row.update(id=str(uuid.uuid4()), assignment_id=target['assignment']['id'])
        if table is reports:
            row['execution_id'] = 'mismatch-' + uuid.uuid4().hex
        else:
            row['idempotency_key'] = 'mismatch-' + uuid.uuid4().hex
        conn.execute(table.insert().values(**row))
    exported = export(crm)['tables'][table.name]
    assert len(exported) == 1
    assert exported[0]['assignment_id'] == local['assignment']['id']
    assert exported[0]['id'] != row['id']


def test_export_without_native_storage_does_not_create_it(crm):
    crm.workspace_token()
    schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
    before = set(inspect(crm.engine).get_table_names(schema=schema))
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(crm.engine, 'before_cursor_execute', capture)
    try:
        tables = export(crm)['tables']
    finally:
        event.remove(crm.engine, 'before_cursor_execute', capture)
    assert not {table.name for table in NATIVE}.intersection(tables)
    assert set(inspect(crm.engine).get_table_names(schema=schema)) == before
    assert not any(s.lstrip().upper().startswith(('CREATE', 'INSERT', 'UPDATE', 'DELETE', 'ALTER', 'DROP')) for s in statements)


def test_export_present_but_foreign_only_is_empty(crm):
    seed(crm, profile='other')
    tables = export(crm)['tables']
    for table in NATIVE:
        assert tables[table.name] == []
    assert len(tables['crm_tasks']) == 1


@pytest.mark.parametrize('malformation', ['partial_work', 'bad_operation', 'operation_without_work'])
def test_export_rejects_partial_or_incompatible_native_schema(crm, malformation):
    crm.workspace_token()
    schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
    prefix = ('"' + schema + '".') if schema else ''
    if malformation == 'bad_operation':
        NativeWorkStore(crm)
    with crm.engine.begin() as conn:
        if malformation == 'partial_work':
            # Deliberately malformed synthetic fixture, never user data.
            conn.execute(text(f'CREATE TABLE {prefix}crm_native_assignments (id TEXT PRIMARY KEY)'))
        else:
            conn.execute(text(f'CREATE TABLE {prefix}crm_native_work_operations (id TEXT PRIMARY KEY)'))
    before = set(inspect(crm.engine).get_table_names(schema=schema))
    with pytest.raises(CRMError) as error:
        export(crm)
    assert error.value.status == 503
    assert set(inspect(crm.engine).get_table_names(schema=schema)) == before


def test_export_rejects_operation_constraint_mismatch(crm):
    NativeWorkStore(crm)
    copied = MetaData()
    assignments.to_metadata(copied)
    malformed = operations.to_metadata(copied)
    for constraint in list(malformed.constraints):
        if isinstance(constraint, UniqueConstraint):
            malformed.constraints.remove(constraint)
    copied.create_all(crm.engine, tables=[malformed])
    with pytest.raises(CRMError) as error:
        export(crm)
    assert error.value.status == 503
    schema = crm.engine.get_execution_options().get('schema_translate_map', {}).get(None)
    assert inspect(crm.engine).get_unique_constraints(operations.name, schema=schema) == []


@pytest.mark.parametrize('state', ['result_reported', 'cancelled', 'superseded'])
def test_export_preserves_terminal_and_invalidated_history(crm, state):
    local = seed(crm)
    if state != 'result_reported':
        saved = local['assignment']
        NativeWorkStore(crm, initialize=False).invalidate(saved['id'], version=saved['version'], reason=state)
    before = table_rows(crm)
    tables = export(crm)['tables']
    assert tables[assignments.name][0]['state'] == state
    for table in NATIVE:
        assert_rows_equal(tables[table.name], before[table.name])


def test_export_native_validation_and_reads_use_supplied_snapshot(crm):
    seed(crm)
    store = ProtectionStore(crm)
    ring = Keyring('synthetic', {'synthetic': bytes(range(32))})
    seen = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        seen.append((conn, statement))
    with crm._read_connection() as connection:
        event.listen(crm.engine, 'before_cursor_execute', capture)
        try:
            envelope = store.export(ring, connection=connection)
        finally:
            event.remove(crm.engine, 'before_cursor_execute', capture)
        assert seen and all(conn is connection for conn, statement in seen)
        assert not any(statement.lstrip().upper().startswith(('CREATE', 'INSERT', 'UPDATE', 'DELETE', 'ALTER', 'DROP'))
                       for conn, statement in seen)
    tables = decrypt_export(envelope, ring, workspace=store.workspace, profile=crm.profile)['tables']
    assert all(tables[table.name] for table in NATIVE)
