"""Offline, fresh-target content recovery of encrypted CRM content exports.

Never opens a CRM runtime, discovers secrets, or writes an existing target.
Execution/provider state is quarantined, never activated.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from sqlalchemy import Boolean, Integer, String, UniqueConstraint, MetaData, create_engine, select
from sqlalchemy.engine import URL

from .domain import CRMError, TABLES, now
from .protection import (
    MAX_EXPORT, MAX_NOTE, canonical, decrypt_export_artifact, owned_tables, unseal,
)


def _invalid():
    raise CRMError('Export is not a consistent supported recovery snapshot', 422)


def _validate(snapshot, notes_ring):
    if type(snapshot['version']) is not int or snapshot['version'] != 1:
        _invalid()
    unified = MetaData()
    for table in owned_tables().values():
        table.to_metadata(unified)
    registry = unified.tables
    tables = snapshot['tables']
    # Every schema family is complete or absent. Legacy FK clones in module
    # metadata are references, not independent members of that family.
    from . import (domain, customization, execution, gmail_history, native_work,
                   protection, report_store, report_interactions)
    from .relationship_schema import OWNED_TABLES as relationships
    from .research_schema import OWNED_TABLES as research
    from .task_ownership import OWNED_TABLES as owners
    from .scheduled_research import TABLES as scheduled_research
    from .report_review_schema import TABLES as report_reviews
    from .gmail_bridge_schema import OWNED_TABLES as gmail_bridge
    families = [set(domain.metadata.tables)]
    for module in (customization, execution, gmail_history, native_work,
                   protection, report_store, report_interactions):
        families.append({name for name in module.metadata.tables
                         if name not in domain.metadata.tables})
    families.extend({t.name for t in group} for group in (relationships, research, owners, scheduled_research, report_reviews, gmail_bridge))
    if not (families[0] | set(customization.metadata.tables)) <= tables.keys():
        _invalid()
    for family in families:
        if family & tables.keys() and not family <= tables.keys():
            _invalid()
    scope = hashlib.sha256(json.dumps(
        [snapshot['workspace'], snapshot['profile']], sort_keys=True,
        separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    for name, rows in tables.items():
        table = registry[name]
        constraints = [tuple(c.name for c in table.primary_key)]
        constraints.extend(tuple(c.name for c in constraint.columns)
                           for constraint in table.constraints if isinstance(constraint, UniqueConstraint))
        for row in rows:
            for column in table.c:
                value = row[column.name]
                if value is None:
                    if not column.nullable: _invalid()
                elif isinstance(column.type, Boolean):
                    if type(value) is not bool: _invalid()
                elif isinstance(column.type, Integer):
                    if type(value) is not int or not -(2**63) <= value < 2**63: _invalid()
                elif isinstance(column.type, String):
                    if not isinstance(value, str): _invalid()
                    if column.type.length and len(value) > column.type.length: _invalid()
                else:
                    _invalid()  # A new column type requires an explicit review.
            if 'scope' in row:
                expected_scope = (hashlib.sha256(canonical([snapshot['workspace'], snapshot['profile']])).hexdigest()
                                  if name.startswith('crm_gmail_') else scope)
                if row['scope'] != expected_scope: _invalid()
            if 'workspace' in row and row['workspace'] != snapshot['workspace']: _invalid()
            if 'profile' in row and row['profile'] != snapshot['profile']: _invalid()
        for columns in constraints:
            seen = set()
            for row in rows:
                key = tuple(row[c] for c in columns)
                if not columns or None in key: continue
                if key in seen: _invalid()
                seen.add(key)
        if name.endswith('_schema'):
            # Current versioned families all use singleton schema version 1.
            if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['version'] != 1: _invalid()
    # Check declared references independently of SQLite's coercion and DDL.
    for name, rows in tables.items():
        for constraint in registry[name].foreign_key_constraints:
            elements = list(constraint.elements)
            target = elements[0].column.table.name
            wanted = {tuple(r[e.column.name] for e in elements) for r in tables.get(target, [])}
            for row in rows:
                key = tuple(row[e.parent.name] for e in elements)
                if None not in key and key not in wanted: _invalid()
    markers = [r['value'] for r in tables['crm_settings'] if r['key'] == 'workspace_id']
    if markers != [snapshot['workspace']]: _invalid()
    # These record references are intentionally polymorphic, so SQL FKs do not
    # cover them. Retain ciphertext; decrypt only to verify every note in memory.
    records = {kind: {r['id']: r for r in tables[table.name]} for kind, table in TABLES.items()}
    for name in ('crm_protected_notes', 'crm_protected_operations', 'crm_custom_values'):
        for row in tables.get(name, []):
            record = records.get(row['kind'], {}).get(row['record_id'])
            if record is None: _invalid()
            if name == 'crm_protected_notes':
                if notes_ring is None:
                    raise CRMError('Retained notes keys are required for recovery verification', 503)
                if row['version'] < 1 or row['version'] >= record['version']: _invalid()
                context = dict(workspace=snapshot['workspace'], profile=snapshot['profile'],
                               kind=row['kind'], record_id=row['record_id'], note_version=row['version'])
                unseal(json.loads(row['envelope']), notes_ring, 'notes', context, MAX_NOTE).decode('utf-8')
            elif name == 'crm_protected_operations':
                if notes_ring is None:
                    raise CRMError('Retained notes keys are required for recovery verification', 503)
                notes_ring.derive(row['key_id'], 'notes-request-mac')
    return registry


def _private_file(path):
    return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)


def restore_content(artifact, *, backup_ring, workspace, profile, target, notes_ring=None):
    """Restore authenticated CRM content into a *new* private local directory.

    ``artifact`` is downloaded JSON bytes. Explicit original scope is required;
    keyrings are supplied in memory. Returns metadata only. No keys, decrypted
    protected notes, or source paths are written. Ordinary fields ARE plaintext
    in the recovered database. Host cutover requires separate review and fencing.
    """
    if not isinstance(artifact, bytes) or len(artifact) > MAX_EXPORT * 4 // 3 + 65536:
        raise CRMError('Recovery artifact exceeds the supported limit or is not bytes', 422)
    if not isinstance(workspace, str) or not workspace or not isinstance(profile, str) or not profile:
        raise CRMError('Original workspace and profile are required', 422)
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise CRMError('Recovery target must not already exist', 409)
    try:
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result: _invalid()
                result[key] = value
            return result
        parsed = json.loads(artifact, object_pairs_hook=pairs)
        snapshot = decrypt_export_artifact(parsed, backup_ring, workspace=workspace, profile=profile)
        registry = _validate(snapshot, notes_ring)
    except CRMError:
        raise
    except Exception:
        raise CRMError('Export is not a consistent supported recovery snapshot', 422) from None

    # Exclusive mkdir is the no-overwrite boundary, including concurrent calls.
    # A failed write intentionally leaves an incomplete private target for review;
    # never recursively delete a directory that another process could modify.
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise CRMError('Recovery target must not already exist', 409) from None
    connection = None
    try:
        db = target / 'recovery.sqlite3'
        os.close(_private_file(db))
        connection = sqlite3.connect(db)
        connection.execute('PRAGMA journal_mode=MEMORY')
        with connection:
            for name, rows in sorted(snapshot['tables'].items()):
                table = registry[name]
                columns = list(table.c)
                definitions = ','.join('"' + c.name + '" ' +
                                       ('INTEGER' if isinstance(c.type, (Integer, Boolean)) else 'TEXT')
                                       for c in columns)
                # Identifiers come only from the compiled registry, never input.
                recovered_name = 'recovery_' + name
                connection.execute(f'CREATE TABLE "{recovered_name}" ({definitions})')
                placeholders = ','.join('?' for _ in columns)
                connection.executemany(f'INSERT INTO "{recovered_name}" VALUES ({placeholders})',
                                       [tuple(row[c.name] for c in columns) for row in rows])
                restored = connection.execute(f'SELECT * FROM "{recovered_name}"').fetchall()
                expected = [tuple(int(row[c.name]) if isinstance(c.type, Boolean) and row[c.name] is not None
                                  else row[c.name] for c in columns) for row in rows]
                if restored != expected: _invalid()
            if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]: _invalid()
        connection.close()
        connection = None
        # Build genuine current schemas without constructing a CRM, host context,
        # scheduler or provider. The raw recovery tables retain original evidence.
        schema = MetaData()
        for table in registry.values():
            table.to_metadata(schema)
        engine = create_engine(URL.create('sqlite', database=str(db)))
        quarantined = []
        safe_initialized = []
        try:
            with engine.begin() as conn:
                schema.create_all(conn, tables=[schema.tables[name] for name in snapshot['tables']])
                for name, rows in snapshot['tables'].items():
                    quarantine = name.startswith(('crm_native_', 'crm_agent_', 'crm_gmail_', 'crm_scheduled_research_', 'crm_report_review_'))
                    if quarantine:
                        quarantined.append(name)
                        if name == 'crm_gmail_bridge_schema':
                            # Preserve all original rows in recovery_* evidence,
                            # but allow a new disabled bridge to be configured.
                            # No account, cursor, lease or polling flag is restored.
                            conn.execute(schema.tables[name].insert().values(id=1, version=1))
                            safe_initialized.append(name)
                        continue
                    values = [dict(row) for row in rows]
                    if name == 'crm_tasks':
                        for row in values:
                            if row['schedule_status'] != 'none' or row['scheduler_job_id'] is not None:
                                row.update(schedule_status='none', scheduler_job_id=None,
                                           version=row['version'] + 1, updated_at=now())
                    if values:
                        conn.execute(schema.tables[name].insert(), values)
                    actual = [dict(r) for r in conn.execute(select(schema.tables[name])).mappings()]
                    if actual != values: _invalid()
                if conn.exec_driver_sql('PRAGMA foreign_key_check').fetchall(): _invalid()
                if conn.exec_driver_sql('PRAGMA integrity_check').fetchall() != [('ok',)]: _invalid()
        finally:
            engine.dispose()
        with db.open('rb') as completed_db:
            os.fsync(completed_db.fileno())
        manifest = dict(format='hermes-crm-content-recovery', version=1,
                        created_at=now(), export_id=parsed['export_id'],
                        workspace=workspace, profile=profile,
                        artifact_sha256=hashlib.sha256(artifact).hexdigest(),
                        database_sha256=hashlib.sha256(db.read_bytes()).hexdigest(),
                        table_counts={name: len(rows) for name, rows in sorted(snapshot['tables'].items())},
                        protected_notes_verified=len(snapshot['tables'].get('crm_protected_notes', [])),
                        live_restore=False, full_backup=False,
                        content_restored=True, exact_profile_required=True,
                        quarantined_tables=sorted(quarantined),
                        safe_initialized_tables=sorted(safe_initialized),
                        task_schedules_reset=True)
        # This completion marker is published last. It is provenance, not a
        # signature, and does not protect against a local attacker replacing both.
        with os.fdopen(_private_file(target / 'manifest.json'), 'wb') as output:
            output.write(canonical(manifest))
            output.flush()
            os.fsync(output.fileno())
        return manifest
    except Exception:
        raise CRMError('Recovery output failed; retain the incomplete target for inspection and use a new target', 500) from None
    finally:
        if connection is not None:
            connection.close()


def main():
    """Offline CLI; secrets are accepted through a pipe, never command arguments."""
    import argparse
    import sys
    from .protection import Keyring
    parser = argparse.ArgumentParser(description='Restore encrypted CRM content into a fresh isolated SQLite target. No host activation.')
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--workspace', required=True)
    parser.add_argument('--profile', required=True)
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    try:
        if sys.stdin.isatty():
            raise CRMError('Supply retained keyrings on piped standard input; do not type secrets into a terminal', 422)
        raw = sys.stdin.buffer.read(9001)
        if len(raw) > 9000: raise ValueError()
        keys = json.loads(raw)
        if not isinstance(keys, dict) or set(keys) - {'backup', 'notes'} or 'backup' not in keys:
            raise ValueError()
        backup_ring = Keyring.parse(json.dumps(keys['backup']))
        notes_ring = Keyring.parse(json.dumps(keys['notes'])) if keys.get('notes') is not None else None
        with Path(args.artifact).open('rb') as source:
            artifact = source.read(MAX_EXPORT * 4 // 3 + 65537)
        result = restore_content(artifact, backup_ring=backup_ring, notes_ring=notes_ring,
                                 workspace=args.workspace, profile=args.profile, target=args.target)
    except CRMError as error:
        print(error.message, file=sys.stderr)
        return 1
    except Exception:
        print('Recovery input could not be read or validated', file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
