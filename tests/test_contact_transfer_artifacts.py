"""Synthetic plaintext artifacts; no host app, providers, keys or credentials."""
import json
import os
import stat
import sys
import threading
import types
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import event, select
from hermes_crm.domain import CRM, CRMError, idempotency
from hermes_crm.contact_transfer import ContactTransfer
from hermes_crm import contact_transfer_runtime as runtime

@pytest.fixture
def setup(tmp_path, monkeypatch):
    module = types.ModuleType('plugins.plugin_storage')
    module.plugin_data_dir = lambda _: tmp_path
    monkeypatch.setitem(sys.modules, 'plugins.plugin_storage', module)
    crm = CRM('sqlite:///' + str(tmp_path / 'synthetic.db'), profile='synthetic')
    crm.create('contacts', dict(name='=Synthetic', email='synthetic@example.invalid', notes='ORDINARY_NOT_SELECTED'))
    yield crm, ContactTransfer(crm), tmp_path
    crm.close()


def op(): return str(uuid.uuid4())


def _receipt_write(context, operation, state=None):
    """Match SQLAlchemy writes independently of dialect/schema SQL rendering."""
    statement = getattr(getattr(context, 'compiled', None), 'statement', None)
    if (not getattr(statement, 'is_' + operation, False)
            or getattr(getattr(statement, 'table', None), 'name', None) != 'crm_idempotency'):
        return False
    if state is None: return True
    return any(json.loads(values.get('response', '{}')).get('state') == state
               for values in context.compiled_parameters)


def test_replay_scope_plaintext_minimal_receipt(setup):
    crm, store, _ = setup
    operation = op()
    result = runtime.export_artifact(store, operation)
    path = Path(result['stored_path'])
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert "'=Synthetic" in path.read_text()
    assert 'ORDINARY_NOT_SELECTED' not in path.read_text()
    crm.create('contacts', dict(name='Later'))
    assert runtime.export_artifact(store, operation) == result
    assert runtime.export_operation_status(store, operation)['row_count'] == 1
    with crm._read_connection() as conn:
        receipt = conn.execute(select(idempotency.c.response).where(idempotency.c.key == runtime._key(operation))).scalar_one()
    assert 'Synthetic' not in receipt and 'example.invalid' not in receipt and 'csv_text' not in receipt
    with pytest.raises(CRMError): runtime.export_artifact(store, operation, columns=['name'])
    crm.profile = 'different'
    with pytest.raises(CRMError): runtime.export_operation_status(store, operation)


def test_missing_unknown_never_recapture(setup, monkeypatch):
    _, store, _ = setup
    assert runtime.export_operation_status(store, op())['state'] == 'unknown'
    operation = op()
    result = runtime.export_artifact(store, operation)
    Path(result['stored_path']).unlink()
    monkeypatch.setattr(store, 'export', lambda **_: pytest.fail('recaptured'))
    assert runtime.export_operation_status(store, operation)['state'] == 'missing_artifact'
    with pytest.raises(CRMError): runtime.export_artifact(store, operation)


@pytest.mark.parametrize('kind', ['tamper', 'permissions', 'symlink', 'hardlink', 'fifo'])
def test_unsafe_artifact_rejected(setup, kind):
    _, store, root = setup
    operation = op()
    path = Path(runtime.export_artifact(store, operation)['stored_path'])
    if kind == 'tamper': path.write_bytes(b'changed')
    elif kind == 'permissions': path.chmod(0o644)
    elif kind == 'hardlink': os.link(path, root / 'extra.csv')
    else:
        path.unlink()
        if kind == 'symlink': path.symlink_to(root / 'missing')
        else: os.mkfifo(path, 0o600)
    with pytest.raises(CRMError): runtime.export_operation_status(store, operation)


def test_snapshot_failure_is_durable(setup, monkeypatch):
    _, store, _ = setup
    calls = []
    def fail(**_):
        calls.append(1)
        raise RuntimeError('synthetic snapshot failure')
    monkeypatch.setattr(store, 'export', fail)
    operation = op()
    with pytest.raises(RuntimeError): runtime.export_artifact(store, operation)
    with pytest.raises(CRMError): runtime.export_artifact(store, operation)
    assert calls == [1]
    assert runtime.export_operation_status(store, operation)['state'] == 'missing_artifact'


def test_post_file_rollback_recovers_original(setup, monkeypatch):
    crm, store, _ = setup
    operation = op()
    def fail(conn, cursor, statement, parameters, context, executemany):
        if _receipt_write(context, 'update', 'ready'):
            raise RuntimeError('synthetic final receipt failure')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        with pytest.raises(RuntimeError): runtime.export_artifact(store, operation)
    finally: event.remove(crm.engine, 'before_cursor_execute', fail)
    monkeypatch.setattr(store, 'export', lambda **_: pytest.fail('recaptured'))
    recovered = runtime.export_operation_status(store, operation)
    assert recovered['state'] == 'committed'
    assert runtime.export_artifact(store, operation)['sha256'] == recovered['sha256']


def test_reservation_failure_no_capture_or_file(setup, monkeypatch):
    crm, store, root = setup
    def fail(conn, cursor, statement, parameters, context, executemany):
        if _receipt_write(context, 'insert'): raise RuntimeError('synthetic reservation failure')
    monkeypatch.setattr(store, 'export', lambda **_: pytest.fail('captured before reservation'))
    event.listen(crm.engine, 'before_cursor_execute', fail)
    operation = op()
    try:
        with pytest.raises(RuntimeError): runtime.export_artifact(store, operation)
    finally: event.remove(crm.engine, 'before_cursor_execute', fail)
    assert runtime.export_operation_status(store, operation)['state'] == 'unknown'
    assert not list((root / 'csv-exports').iterdir())


def test_concurrent_capture_once(setup, monkeypatch):
    _, store, _ = setup
    entered, release = threading.Event(), threading.Event()
    original = store.export
    calls = []
    def blocked(**kwargs):
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return original(**kwargs)
    monkeypatch.setattr(store, 'export', blocked)
    operation = op()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(runtime.export_artifact, store, operation)
        try:
            assert entered.wait(5)
            second = pool.submit(runtime.export_artifact, store, operation)
            with pytest.raises(CRMError): second.result(timeout=5)
        finally: release.set()
        assert first.result(timeout=5)['row_count'] == 1
    assert calls == [1]


def test_limits_and_bad_ids(setup, monkeypatch):
    _, store, root = setup
    with pytest.raises(CRMError): runtime.export_artifact(store, '../invalid')
    monkeypatch.setattr(runtime, 'MAX_FILES', 1)
    runtime.export_artifact(store, op())
    with pytest.raises(CRMError): runtime.export_artifact(store, op())
    monkeypatch.setattr(runtime, 'MAX_FILES', 20)
    monkeypatch.setattr(runtime, 'MAX_STORAGE', 1)
    with pytest.raises(CRMError): runtime.export_artifact(store, op())
    (root / 'csv-exports').chmod(0o755)
    with pytest.raises(CRMError): runtime.export_artifact(store, op())


def test_host_storage_denial_never_captures(setup, monkeypatch):
    _, store, _ = setup
    def denied(_): raise PermissionError('synthetic profile storage denial')
    monkeypatch.setattr(sys.modules['plugins.plugin_storage'], 'plugin_data_dir', denied)
    monkeypatch.setattr(store, 'export', lambda **_: pytest.fail('captured'))
    with pytest.raises(PermissionError): runtime.export_artifact(store, op())


def test_invalid_selection_no_reservation(setup):
    crm, store, _ = setup
    operation = op()
    with pytest.raises(CRMError): runtime.export_artifact(store, operation, columns=['protected_notes'])
    with crm._read_connection() as conn:
        assert conn.execute(select(idempotency).where(idempotency.c.key == runtime._key(operation))).first() is None


def test_protected_notes_not_read_or_exported(setup):
    from hermes_crm.protection import Keyring, ProtectionStore
    crm, store, _ = setup
    record = crm.create('contacts', dict(name='Protected synthetic'))
    ring = Keyring('synthetic', {'synthetic': bytes(range(32))})
    ProtectionStore(crm).save('contacts', record['id'], ring=ring, operation_id=op(),
        expected_record_version=1, expected_note_version=0, plaintext='PROTECTED_SECRET_NEVER_CSV')
    statements = []
    def trace(conn, cursor, statement, parameters, context, executemany): statements.append(statement)
    event.listen(crm.engine, 'before_cursor_execute', trace)
    try: result = runtime.export_artifact(store, op(), columns=['name', 'notes'])
    finally: event.remove(crm.engine, 'before_cursor_execute', trace)
    assert 'PROTECTED_SECRET_NEVER_CSV' not in Path(result['stored_path']).read_text()
    assert not any('crm_protected_notes' in stmt or 'crm_protected_operations' in stmt for stmt in statements)


def test_static_pool_no_nested_transactions(tmp_path, monkeypatch):
    module = types.ModuleType('plugins.plugin_storage')
    module.plugin_data_dir = lambda _: tmp_path
    monkeypatch.setitem(sys.modules, 'plugins.plugin_storage', module)
    crm = CRM('sqlite:///:memory:', profile='memory-synthetic')
    try:
        crm.create('contacts', dict(name='Memory synthetic'))
        store = ContactTransfer(crm)
        operation = op()
        result = runtime.export_artifact(store, operation)
        assert result['row_count'] == 1
        assert runtime.export_artifact(store, operation) == result
    finally: crm.close()


def test_readonly_unknown_status_does_not_bootstrap_workspace(setup):
    from hermes_crm.domain import settings
    crm, store, _ = setup
    with crm.engine.begin() as conn: conn.execute(settings.delete().where(settings.c.key == 'workspace_id'))
    assert runtime.export_operation_status(store, op())['state'] == 'unknown'
    with crm._read_connection() as conn:
        assert conn.execute(select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar() is None


def test_wrong_owner_rejected(setup, monkeypatch):
    _, store, _ = setup
    operation = op()
    runtime.export_artifact(store, operation)
    actual = os.getuid()
    monkeypatch.setattr(runtime.os, 'getuid', lambda: actual + 1)
    with pytest.raises(CRMError): runtime.export_operation_status(store, operation)


def test_cross_workspace_capacity_serialized(setup, monkeypatch):
    crm, first_store, root = setup
    other = CRM('sqlite:///' + str(root / 'other.db'), profile='synthetic')
    other.create('contacts', dict(name='Other workspace'))
    second_store = ContactTransfer(other)
    barrier = threading.Barrier(2)
    monkeypatch.setattr(runtime, 'MAX_FILES', 1)
    for store in (first_store, second_store):
        original = store.export
        def blocked(original=original, **kwargs):
            result = original(**kwargs)
            barrier.wait(timeout=5)
            return result
        monkeypatch.setattr(store, 'export', blocked)
    def attempt(store):
        try: return runtime.export_artifact(store, op())
        except CRMError as error: return error.status
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (first_store, second_store)))
        assert sum(isinstance(value, dict) for value in results) == 1
        assert 409 in results
        assert len(list((root / 'csv-exports').iterdir())) == 1
    finally: other.close()


def test_runtime_payload_cap_retains_reservation(setup, monkeypatch):
    _, store, root = setup
    operation = op()
    original = store.export
    calls = []
    def oversized(**kwargs):
        calls.append(1)
        return dict(original(**kwargs), csv_text='x' * (runtime.MAX_EXPORT_BYTES + 1))
    monkeypatch.setattr(store, 'export', oversized)
    with pytest.raises(CRMError) as caught: runtime.export_artifact(store, operation)
    assert caught.value.status == 413
    with pytest.raises(CRMError): runtime.export_artifact(store, operation)
    assert calls == [1]
    assert not list((root / 'csv-exports').iterdir())


@pytest.mark.parametrize('dialect_name', ['sqlite', 'postgresql'])
@pytest.mark.parametrize('schema', [None, 'crm_synthetic'])
def test_receipt_failure_hook_handles_qualified_sql(dialect_name, schema):
    from sqlalchemy import MetaData
    from sqlalchemy.dialects import postgresql, sqlite
    table = idempotency.to_metadata(MetaData(), schema=schema)
    dialect = (postgresql if dialect_name == 'postgresql' else sqlite).dialect()
    for operation in ('insert', 'update'):
        for state in ('reserved', 'captured', 'ready'):
            statement = getattr(table, operation)().values(key='synthetic', digest='0' * 64, response=json.dumps({'state': state}))
            compiled = statement.compile(dialect=dialect)
            context = types.SimpleNamespace(compiled=compiled, compiled_parameters=[compiled.params])
            assert _receipt_write(context, operation)
            assert _receipt_write(context, 'update', 'ready') == (operation == 'update' and state == 'ready')
            assert _receipt_write(context, 'insert') == (operation == 'insert')
    assert not _receipt_write(types.SimpleNamespace(compiled=None), 'update', 'ready')
    unrelated = table.to_metadata(MetaData(), name='unrelated')
    context = types.SimpleNamespace(compiled=unrelated.insert().values(key='synthetic', digest='0' * 64, response='{}').compile(dialect=dialect))
    assert not _receipt_write(context, 'insert')
