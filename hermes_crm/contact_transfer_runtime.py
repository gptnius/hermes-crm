"""Private plaintext CSV artifacts for the host captureGatewayFileDownload bridge.

Reservations outlive files. Retention is manual: remove old CSV files only, never
receipts, and use a new operation ID for another snapshot. No secrets or keys.
"""
import hashlib
import json
import os
import stat
import uuid
from contextlib import contextmanager
from pathlib import Path
from sqlalchemy import select
from .domain import CRMError, idempotency, settings
from .contact_transfer import DEFAULT_COLUMNS, MAX_EXPORT_BYTES, digest

PREFIX = 'contact-csv-export:v1:'
MAX_FILES = 20
MAX_STORAGE = 64 * 1024 * 1024


def _key(operation_id):
    try:
        if not isinstance(operation_id, str) or str(uuid.UUID(operation_id)) != operation_id: raise ValueError()
    except Exception: raise CRMError('Invalid export operation identifier') from None
    return PREFIX + operation_id


def _directory(create=False):
    from plugins.plugin_storage import plugin_data_dir
    # The supported helper supplies the trusted, profile-owned parent per call.
    directory = Path(plugin_data_dir('hermes-crm')) / 'csv-exports'
    if create: directory.mkdir(mode=0o700, exist_ok=True)
    if not directory.exists() and not directory.is_symlink(): return directory
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise CRMError('Unsafe CSV export directory', 503)
    return directory


def _safe_file(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_EXPORT_BYTES):
        raise CRMError('Invalid CSV export artifact', 503)


def _capacity(directory, size):
    entries = list(directory.iterdir())
    total = 0
    for entry in entries:
        info = entry.lstat()
        _safe_file(info)
        total += info.st_size
    if len(entries) >= MAX_FILES: raise CRMError('CSV export retention limit reached; remove old files manually', 409)
    if total + size > MAX_STORAGE: raise CRMError('CSV export storage limit reached', 413)


@contextmanager
def _directory_lock(directory):
    # One filesystem lock also coordinates separate workspace databases sharing
    # this profile directory. It adds no cleanup-sensitive lock-file artifact.
    import fcntl
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def _scope(store, conn=None):
    workspace = store.crm.workspace_token() if conn is None else conn.execute(
        select(settings.c.value).where(settings.c.key == 'workspace_id')).scalar()
    return dict(workspace=workspace, profile=store.crm.profile)


def _receipt(conn, key):
    return conn.execute(select(idempotency).where(idempotency.c.key == key)).mappings().first()


def _check_scope(receipt, scope):
    value = json.loads(receipt['response'])
    if any(value.get(k) != v for k, v in scope.items()): raise CRMError('CSV export operation scope mismatch', 409)
    return value


def _metadata(target, operation_id, value):
    return dict(operation_id=operation_id, export_id=operation_id, stored_path=str(target), suggested_name='hermes-contacts.csv',
                format='csv', state='committed', spreadsheet_safe=True, **value['artifact'])


def export_operation_status(store, operation_id):
    """Read-only recovery of the original bytes. Never takes a new snapshot."""
    key = _key(operation_id)
    with store.crm._read_connection() as conn:
        store._storage(conn)
        scope = _scope(store, conn)
        receipt = _receipt(conn, key)
    if receipt is None: return dict(operation_id=operation_id, state='unknown')
    value = _check_scope(receipt, scope)
    target = _directory() / (operation_id + '.csv')
    if not target.exists() and not target.is_symlink(): return dict(operation_id=operation_id, state='missing_artifact')
    if 'artifact' not in value: raise CRMError('Unregistered CSV export artifact', 503)
    _safe_file(target.lstat())
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        _safe_file(info)
        payload = stream.read(MAX_EXPORT_BYTES + 1)
    if len(payload) != value['artifact']['byte_count'] or hashlib.sha256(payload).hexdigest() != value['artifact']['sha256']:
        raise CRMError('CSV export artifact verification failed', 503)
    return dict(_metadata(target, operation_id, value), state='committed')


def export_artifact(store, operation_id, columns=None, filters=None):
    key = _key(operation_id)
    columns = list(DEFAULT_COLUMNS) if columns is None else columns
    filters = {} if filters is None else filters
    scope = _scope(store)
    request_digest = digest(dict(scope, columns=columns, filters=filters, spreadsheet_safe=True))
    directory = _directory(create=True)
    target = directory / (operation_id + '.csv')
    with store.crm.engine.begin() as conn:
        store._storage(conn)
        store.crm._catalog_lock(conn)
        receipt = _receipt(conn, key)
        if receipt is not None:
            _check_scope(receipt, scope)
            if receipt['digest'] != request_digest: raise CRMError('Export operation was already used with different selections', 409)
        else:
            store.validate_export(conn, columns, filters)
            if target.exists() or target.is_symlink(): raise CRMError('Unregistered CSV export artifact', 503)
            _capacity(directory, 0)
            conn.execute(idempotency.insert().values(key=key, digest=request_digest, response=json.dumps(dict(scope, state='reserved'))))
    if receipt is not None:
        result = export_operation_status(store, operation_id)
        if result['state'] != 'committed': raise CRMError('Original CSV export unavailable; use a new operation for a new export', 409)
        return result
    # No open reservation transaction: compatible with SQLite StaticPool and
    # PostgreSQL repeatable-read export. Only the reservation winner captures.
    result = store.export(columns=columns, filters=filters)
    payload = result['csv_text'].encode('utf-8')
    if len(payload) > MAX_EXPORT_BYTES: raise CRMError('CSV export exceeds size limit', 413)
    value = dict(scope, state='captured', artifact=dict(row_count=result['row_count'], columns=result['columns'],
                 escaped_cells=result['escaped_cells'], byte_count=len(payload), sha256=hashlib.sha256(payload).hexdigest()))
    # Commit verification metadata BEFORE writing bytes, so post-file rollback
    # can recover the exact original artifact without another snapshot.
    with store.crm.engine.begin() as conn:
        store.crm._catalog_lock(conn)
        conn.execute(idempotency.update().where(idempotency.c.key == key).values(response=json.dumps(value)))
    with store.crm.engine.begin() as conn:
        store.crm._catalog_lock(conn)
        with _directory_lock(directory):
            _directory()
            _capacity(directory, len(payload))
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            dirfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: os.fsync(dirfd)
            finally: os.close(dirfd)
            conn.execute(idempotency.update().where(idempotency.c.key == key).values(response=json.dumps(dict(value, state='ready'))))
    return _metadata(target, operation_id, value)
