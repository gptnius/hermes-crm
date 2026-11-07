"""Resolve optional profile-scoped secrets on every call, without fallbacks."""
from .domain import CRMError
from .protection import Keyring


def resolve_keyring(purpose):
    names = {'notes':'HERMES_CRM_NOTES_KEYS', 'backup':'HERMES_CRM_BACKUP_KEYS'}
    if purpose not in names: raise CRMError('Invalid protection purpose')
    try:
        from agent.secret_scope import get_secret
        raw = get_secret(names[purpose])
    except Exception:
        raise CRMError('Profile-scoped protection keys unavailable', 503) from None
    return Keyring.parse(raw)


def _operation_id(value):
    import uuid
    try:
        if str(uuid.UUID(value)) != value: raise ValueError()
    except Exception: raise CRMError('Invalid operation identifier') from None


def _export_directory(*, create=False):
    import os
    import stat
    from pathlib import Path
    from plugins.plugin_storage import plugin_data_dir
    # The supported host helper supplies the trusted profile-owned parent.
    directory = Path(plugin_data_dir('hermes-crm')) / 'exports'
    if create: directory.mkdir(mode=0o700, exist_ok=True)
    if not directory.exists() and not directory.is_symlink(): return directory
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
        raise CRMError('Unsafe export directory',503)
    return directory


def _artifact_metadata(target, operation_id):
    return dict(export_id=operation_id, stored_path=str(target), suggested_name='HermesCRM-encrypted-export.json', format='hermes-crm-encrypted-export', version=1)


def _read_artifact(store, ring, target, operation_id):
    import os
    import stat
    import json
    from .protection import decrypt_export_artifact, MAX_EXPORT
    if not stat.S_ISREG(target.lstat().st_mode): raise CRMError('Invalid export artifact',503)
    fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > MAX_EXPORT * 2
            or stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid()):
            raise CRMError('Invalid export artifact',503)
        try: envelope = json.loads(stream.read())
        except Exception: raise CRMError('Invalid export artifact',503) from None
    decrypt_export_artifact(envelope, ring, workspace=store.workspace, profile=store.crm.profile, export_id=operation_id)
    return _artifact_metadata(target,operation_id)


def export_operation_status(store, ring, operation_id):
    """Read-only original-outcome lookup; missing artifacts never trigger export."""
    from sqlalchemy import select
    from .protection import exports
    _operation_id(operation_id)
    with store.crm._read_connection() as conn:
        receipt = conn.execute(select(exports).where(exports.c.id==operation_id,
            exports.c.workspace==store.workspace, exports.c.profile==store.crm.profile)).mappings().first() if store._exists(conn) else None
    if receipt is None: return dict(operation_id=operation_id,state='unknown')
    target = _export_directory() / (operation_id+'.hermes-crm.enc.json')
    if not target.exists() and not target.is_symlink(): return dict(operation_id=operation_id,state='missing_artifact')
    return dict(_read_artifact(store,ring,target,operation_id),operation_id=operation_id,state='committed')


def export_artifact(store, ring, operation_id):
    """Durably reserve once, then write ciphertext. Never repeat a reserved capture."""
    import os
    import hmac
    import hashlib
    from sqlalchemy import select, update
    from .protection import canonical, exports
    _operation_id(operation_id)
    directory = _export_directory(create=True)
    target = directory / (operation_id+'.hermes-crm.enc.json')
    with store.crm.engine.begin() as conn:
        store.crm._catalog_lock(conn)
        store.initialize(conn)
        receipt = conn.execute(select(exports).where(exports.c.id==operation_id)).mappings().first()
        if receipt is None:
            if target.exists() or target.is_symlink(): raise CRMError('Unregistered export artifact',503)
            conn.execute(exports.insert().values(id=operation_id,workspace=store.workspace,profile=store.crm.profile,state='reserved'))
        elif receipt['workspace'] != store.workspace or receipt['profile'] != store.crm.profile:
            raise CRMError('Export operation scope mismatch',409)
    # Reservation committed before file creation: even a crash/cleanup cannot
    # turn this ID into permission to capture newer contents.
    if receipt is not None:
        result = export_operation_status(store,ring,operation_id)
        if result['state'] != 'committed': raise CRMError('Original export artifact unavailable; use a new operation for a new export',409)
        return {k:v for k,v in result.items() if k not in ('operation_id','state')}
    entries = list(directory.iterdir())
    if len(entries) >= 20: raise CRMError('Export retention limit reached; remove old exports manually',409)
    total = sum(p.lstat().st_size for p in entries)
    envelope = dict(export_id=operation_id,envelope=store.export(ring))
    envelope['operation_mac'] = hmac.new(ring.derive(envelope['envelope']['key_id'],'export-operation'),canonical(envelope),hashlib.sha256).hexdigest()
    payload = canonical(envelope)
    if total + len(payload) > 256 * 1024 * 1024: raise CRMError('Export storage limit reached',413)
    # Serialize capacity checks/file creation across processes. Snapshot was
    # captured in its own consistent read transaction, never a nested pool use.
    with store.crm.engine.begin() as conn:
        store.crm._catalog_lock(conn)
        store._exists(conn)
        entries = list(directory.iterdir())
        if len(entries) >= 20: raise CRMError('Export retention limit reached; remove old exports manually',409)
        if sum(p.lstat().st_size for p in entries)+len(payload)>256*1024*1024: raise CRMError('Export storage limit reached',413)
        fd = os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            dirfd = os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try: os.fsync(dirfd)
            finally: os.close(dirfd)
        except Exception: raise CRMError('Encrypted export could not be completed',503) from None
        conn.execute(update(exports).where(exports.c.id==operation_id).values(state='ready'))
    return _artifact_metadata(target,operation_id)
