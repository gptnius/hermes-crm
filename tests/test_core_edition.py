"""Core-only contract and synthetic upgrade safety. No user files or providers."""
import ast
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from hermes_crm import native_api
from hermes_crm.domain import CRM, CRMError
from hermes_crm import gmail_history as legacy
from hermes_crm import gmail_bridge_schema as bridge
from hermes_crm.protection import Keyring, ProtectionStore, canonical, decrypt_export
from hermes_crm.recovery import restore_content

ROOT = Path(__file__).resolve().parents[1]
REMOVED = ('gmail_gws', 'gmail_bridge_runtime', 'gmail_bridge_api', 'gmail_runtime',
           'gmail_history_api', 'gmail_reader', 'gmail_incremental', 'gmail_matching',
           'gmail_bridge_store', 'email_contracts')


def test_manifest_and_source_have_no_provider_entry_points():
    manifest = yaml.safe_load((ROOT / 'plugin.yaml').read_text())
    assert len(manifest['provides_tools']) == 83
    assert 'oauth' not in manifest
    assert 'gmail' not in json.dumps(manifest).lower()
    for name in REMOVED:
        assert not (ROOT / 'hermes_crm' / (name + '.py')).exists()
    # The reusable QA venv contains an editable full-edition install. Exclude
    # that unrelated fallback finder when checking this distribution's imports.
    probe = """import sys, importlib.util
sys.meta_path[:] = [f for f in sys.meta_path if not getattr(f, '__module__', '').startswith('__editable__')]
import hermes_crm
assert hermes_crm.__file__.startswith(sys.argv[1])
for name in sys.argv[2:]:
    assert importlib.util.find_spec('hermes_crm.' + name) is None, name
"""
    subprocess.run([sys.executable, '-c', probe, str(ROOT), *REMOVED], cwd=ROOT, check=True)
    for path in (ROOT / 'hermes_crm').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in REMOVED
    source = (ROOT / 'desktop/plugin.js').read_text()
    for marker in ('EmailBridge', 'EmailHistory', '/email-bridge/', '/email/',
                   'emailBridgeMemory', 'GENERATED EMAIL', 'gmail.readonly',
                   'Workspace connection status and explicit account actions.'):
        assert marker not in source
    assert not list((ROOT / 'desktop').glob('email-*.js'))
    assert not list((ROOT / 'scripts').glob('build_email*.py'))


def test_provider_routes_not_registered(tmp_path, monkeypatch):
    monkeypatch.setattr(native_api, 'open_profile_crm',
        lambda: CRM('sqlite:///' + str(tmp_path / 'empty.db'), profile='core'))
    assert not any(getattr(route, 'path', '').startswith(('/email/', '/email-bridge'))
                   for route in native_api.router.routes)
    app = FastAPI()
    app.include_router(native_api.router)
    with TestClient(app) as client:
        meta = client.get('/meta')
        assert meta.status_code == 200
        token = meta.json()['workspace_token']
        assert not any(path.startswith(('/email/', '/email-bridge')) for path in app.openapi()['paths'])
        for path in ('/email/status', '/email-bridge/status', '/email-bridge/sync'):
            # Generic core routes reject an unknown Literal resource with 422;
            # neither a provider status nor a provider mutation is available.
            response = client.get(path, params={'workspace_token': token})
            assert response.status_code == 422
            errors = response.json()['detail']
            assert len(errors) == 1
            assert errors[0]['type'] == 'literal_error'
            assert errors[0]['loc'] == ['path', 'kind']
            assert errors[0]['input'] == path.split('/')[1]
            assert client.post(path, json={}).status_code == 405


def seed_legacy(crm, scope):
    legacy.metadata.create_all(crm.engine)
    bridge.metadata.create_all(crm.engine)
    with crm.engine.begin() as conn:
        conn.execute(bridge.version.insert().values(id=1, version=1))
        conn.execute(bridge.state.insert().values(scope=scope, payload=json.dumps({
            'enabled': True, 'mailbox': 'synthetic@example.test', 'cursor': '42',
            'polling': True, 'lease': 'old-running-lease'})))
        conn.execute(bridge.messages.insert().values(scope=scope, account_namespace=str(uuid.uuid4()),
            message_id='synthetic-message', payload='{"subject":"LEGACY_METADATA"}'))
        conn.execute(legacy.connections.insert().values(scope=scope, revision=7, connected=1,
            subject='synthetic-subject', mailbox='synthetic@example.test', active_operation='old-operation'))
        conn.execute(legacy.operations.insert().values(id='old-operation', scope=scope,
            digest='synthetic-digest', kind='sync', state='running', reason='legacy',
            created_at='2026-01-01T00:00:00Z'))
        conn.execute(legacy.snapshots.insert().values(key='synthetic-key', scope=scope,
            subject='synthetic-subject', message_id='old-message', payload='{"subject":"OLD_HISTORY"}',
            observed_at='2026-01-01T00:00:00Z'))


def rows(crm):
    with crm.engine.connect() as conn:
        return {table.name: [dict(row) for row in conn.execute(select(table)).mappings()]
                for table in (*legacy.metadata.sorted_tables, *bridge.OWNED_TABLES)}


@pytest.fixture
def source(tmp_path):
    crm = CRM('sqlite:///' + str(tmp_path / 'source.db'), profile='Équipe')
    scope = hashlib.sha256(json.dumps([crm.workspace_token(), crm.profile],
        sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
    seed_legacy(crm, scope)
    yield crm
    crm.close()


def test_core_upgrade_crud_export_and_restore_preserve_legacy_evidence(source, tmp_path):
    before = rows(source)
    workspace = source.workspace_token()
    reopened = CRM(source.url, schema=source.engine.get_execution_options().get('schema_translate_map', {}).get(None), profile=source.profile) if source.backend == 'postgres' else CRM(source.url, profile=source.profile)
    try:
        assert reopened.workspace_token() == workspace
        assert rows(reopened) == before
    finally:
        reopened.close()
    record = source.create('contacts', {'name': 'Core contact', 'email': 'core@example.test'})
    source.update('contacts', record['id'], {'version': record['version'], 'name': 'Updated'})
    assert source.get('contacts', record['id'])['name'] == 'Updated'
    assert source.workspace_token() == workspace
    assert rows(source) == before
    ring = Keyring('synthetic', {'synthetic': b'e' * 32})
    envelope = ProtectionStore(source).export(ring)
    snapshot = decrypt_export(envelope, ring, workspace=workspace, profile=source.profile)
    for name, expected in before.items():
        assert snapshot['tables'][name] == expected
    assert 'LEGACY_METADATA' not in json.dumps(envelope)
    artifact = {'export_id': str(uuid.uuid4()), 'envelope': envelope}
    artifact['operation_mac'] = hmac.new(ring.derive(ring.active, 'export-operation'),
                                        canonical(artifact), hashlib.sha256).hexdigest()
    target = tmp_path / 'recovered'
    manifest = restore_content(canonical(artifact), backup_ring=ring, notes_ring=None,
                               workspace=workspace, profile=source.profile, target=target)
    assert set(before) <= set(manifest['quarantined_tables'])
    assert manifest['safe_initialized_tables'] == ['crm_gmail_bridge_schema']
    with sqlite3.connect(target / 'recovery.sqlite3') as conn:
        for name, expected in before.items():
            assert conn.execute(f'SELECT COUNT(*) FROM "recovery_{name}"').fetchone()[0] == len(expected)
            if name != 'crm_gmail_bridge_schema':
                assert conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] == 0
        assert conn.execute('SELECT * FROM crm_gmail_bridge_schema').fetchall() == [(1, 1)]
    assert rows(source) == before


def test_partial_legacy_schema_fails_closed_on_export(source):
    bridge.aliases.drop(source.engine)
    with pytest.raises(CRMError, match='Incomplete Gmail bridge schema'):
        ProtectionStore(source).export(Keyring('synthetic', {'synthetic': b'e' * 32}))


@pytest.mark.parametrize('damage', ['missing_table', 'extra_column', 'extra_unique'])
def test_legacy_history_export_rejects_incomplete_or_incompatible_schema(source, damage):
    if damage == 'missing_table':
        legacy.links.drop(source.engine)
    else:
        from hermes_crm.report_store import schema_name
        table = 'crm_gmail_contact_links'
        schema = schema_name(source)
        if schema:
            table = '"' + schema + '"."' + table + '"'
        with source.engine.begin() as conn:
            if damage == 'extra_column':
                conn.exec_driver_sql('ALTER TABLE ' + table + ' ADD COLUMN unexpected TEXT')
            else:
                conn.exec_driver_sql('CREATE UNIQUE INDEX legacy_extra_unique ON ' + table + ' (snapshot_key)')
    with pytest.raises(CRMError, match='legacy Gmail history'):
        ProtectionStore(source).export(Keyring('synthetic', {'synthetic': b'e' * 32}))


def test_native_secret_paths_do_not_fall_back_to_environment(tmp_path, monkeypatch):
    """Poison ambient lookup while exercising actual native factory/key resolvers."""
    import os
    import types
    from hermes_crm import runtime, protection_runtime

    requested = []
    secret_value = [None]
    storage = types.ModuleType('plugins.plugin_storage')
    storage.plugin_data_dir = lambda name: tmp_path
    storage.plugin_db = lambda name: sqlite3.connect(tmp_path / 'native.db', check_same_thread=False)
    secrets = types.ModuleType('agent.secret_scope')
    def get_secret(name):
        requested.append(name)
        return secret_value[0]
    secrets.get_secret = get_secret
    def poison(*args, **kwargs):
        raise AssertionError('Native secret/storage path must not consult ambient getenv')

    with monkeypatch.context() as patch:
        patch.setitem(sys.modules, 'plugins.plugin_storage', storage)
        patch.setitem(sys.modules, 'agent.secret_scope', secrets)
        patch.setattr(os, 'getenv', poison)
        crm = runtime.open_profile_crm(backend='sqlite', profile='synthetic')
        crm.close()
        with pytest.raises(CRMError, match='missing or invalid'):
            runtime.open_profile_crm(backend='postgres', profile='synthetic')
        for purpose in ('notes', 'backup'):
            with pytest.raises(CRMError):
                protection_runtime.resolve_keyring(purpose)
        assert requested == ['HERMES_CRM_DATABASE_URL', 'HERMES_CRM_NOTES_KEYS', 'HERMES_CRM_BACKUP_KEYS']
        secret_value[0] = 'postgresql://synthetic:fixture@127.0.0.1/synthetic'
        captured = {}
        def capture(url, **kwargs):
            captured.update(url=url, **kwargs)
            return captured
        patch.setattr(runtime, 'CRM', capture)
        runtime.open_profile_crm(backend='postgres', profile='synthetic')
        assert captured['url'] == 'postgresql+psycopg://synthetic:fixture@127.0.0.1/synthetic'
        assert captured['profile'] == 'synthetic'
        assert captured['schema'].startswith('crm_') and len(captured['schema']) == 28
