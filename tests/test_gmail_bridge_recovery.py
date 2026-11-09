"""Synthetic metadata export/recovery: no credentials, provider or user files."""
import hashlib
import hmac
import json
import sqlite3
import uuid

import pytest
from sqlalchemy import delete, select

from hermes_crm.domain import CRM, CRMError
from hermes_crm.gmail_bridge_store import GmailBridgeStore
from hermes_crm.gmail_bridge_schema import OWNED_TABLES, aliases, state, version
from hermes_crm.gmail_incremental import Observation, SyncResult
from hermes_crm.gmail_history import GmailHistoryStore, connections
from hermes_crm.protection import Keyring, ProtectionStore, canonical, decrypt_export, seal
from hermes_crm.recovery import restore_content


@pytest.fixture
def source(tmp_path):
    crm = CRM('sqlite:///' + str(tmp_path / 'source.db'), profile='Équipe')
    crm.workspace_token()
    yield crm
    crm.close()


def populate(crm, mailbox, subject):
    contact = crm.create('contacts', {'name': subject, 'email': 'contact@example.test'})
    store = GmailBridgeStore(crm)
    store.bind_verified('bind', selector_fingerprint='a' * 64, mailbox=mailbox,
                        expected_revision=store.status()['revision'])
    lease = store.begin_sync('read', expected_revision=store.status()['revision'])
    observed = Observation('message1', 'thread1', 1000, '20', ('SENT',),
                           (('from', mailbox), ('to', 'contact@example.test'), ('subject', subject)),
                           observed_in_sent=True)
    store.finish_sync(lease, SyncResult('complete', '20', (observed,), 'bounded_bootstrap'))
    store.set_contact_aliases('aliases', contact_id=contact['id'], contact_version=contact['version'],
                              aliases=['alias@example.test'], expected_revision=store.status()['revision'])
    return store


def export_artifact(crm, ring, mutate=None):
    envelope = ProtectionStore(crm).export(ring)
    if mutate:
        value = decrypt_export(envelope, ring, workspace=crm.workspace_token(), profile=crm.profile)
        mutate(value)
        envelope = seal(canonical(value), ring, 'backup', {'workspace': crm.workspace_token(), 'profile': crm.profile})
    result = {'export_id': str(uuid.uuid4()), 'envelope': envelope}
    result['operation_mac'] = hmac.new(ring.derive(ring.active, 'export-operation'), canonical(result), hashlib.sha256).hexdigest()
    return canonical(result)


def test_scoped_export_and_disabled_quarantined_recovery(source, tmp_path):
    own = populate(source, 'owner@example.test', 'OWN_SUBJECT')
    other = CRM(source.url, profile='other')
    try:
        populate(other, 'other@example.test', 'OTHER_SUBJECT')
        old_other = GmailHistoryStore(other, initialize=True)
        with other.engine.begin() as conn:
            conn.execute(connections.update().where(connections.c.scope == old_other.scope)
                         .values(mailbox='other@example.test'))
        old_own = GmailHistoryStore(source, initialize=True)
        with source.engine.begin() as conn:
            conn.execute(connections.update().where(connections.c.scope == old_own.scope)
                         .values(mailbox='owner@example.test'))
        ring = Keyring('synthetic', {'synthetic': b'e' * 32})
        envelope = ProtectionStore(source).export(ring)
        snapshot = decrypt_export(envelope, ring, workspace=source.workspace_token(), profile=source.profile)
        assert {table.name for table in OWNED_TABLES} <= snapshot['tables'].keys()
        bridge_rows = {name: rows for name, rows in snapshot['tables'].items() if name.startswith('crm_gmail_')}
        rendered = json.dumps(bridge_rows)
        assert 'OWN_SUBJECT' in rendered and 'OTHER_SUBJECT' not in rendered
        assert 'other@example.test' not in rendered
        assert len(bridge_rows['crm_gmail_connections']) == 1
        before = own.status()
        manifest = restore_content(export_artifact(source, ring), backup_ring=ring, notes_ring=None,
                                   workspace=source.workspace_token(), profile=source.profile,
                                   target=tmp_path / 'recovered')
        assert {table.name for table in OWNED_TABLES} <= set(manifest['quarantined_tables'])
        assert manifest['safe_initialized_tables'] == ['crm_gmail_bridge_schema']
        with sqlite3.connect(tmp_path / 'recovered' / 'recovery.sqlite3') as conn:
            assert conn.execute('select count(*) from recovery_crm_gmail_bridge_messages').fetchone() == (1,)
            assert conn.execute('select count(*) from crm_gmail_bridge_messages').fetchone() == (0,)
            assert conn.execute('select count(*) from crm_gmail_bridge_state').fetchone() == (0,)
            assert conn.execute('select * from crm_gmail_bridge_schema').fetchall() == [(1, 1)]
        restored = CRM('sqlite:///' + str(tmp_path / 'recovered' / 'recovery.sqlite3'), profile=source.profile)
        try:
            fresh = GmailBridgeStore(restored)
            assert fresh.status()['enabled'] is False
            assert fresh.status()['account_namespace'] is None
            assert fresh.page()['items'] == []
        finally:
            restored.close()
        assert own.status() == before
    finally:
        other.close()


def test_partial_bridge_family_rejected_on_export(source):
    populate(source, 'owner@example.test', 'OWN_SUBJECT')
    aliases.drop(source.engine)
    with pytest.raises(CRMError, match='Incomplete Gmail bridge schema'):
        ProtectionStore(source).export(Keyring('synthetic', {'synthetic': b'e' * 32}))


@pytest.mark.parametrize('mutation', [
    lambda value: value['tables'].pop('crm_gmail_bridge_aliases'),
    lambda value: value['tables']['crm_gmail_bridge_schema'][0].update(version=2),
    lambda value: value['tables']['crm_gmail_bridge_state'][0].update(scope='0' * 64),
])
def test_tampered_bridge_snapshot_refused_before_target(source, tmp_path, mutation):
    populate(source, 'owner@example.test', 'OWN_SUBJECT')
    ring = Keyring('synthetic', {'synthetic': b'e' * 32})
    target = tmp_path / 'refused'
    with pytest.raises(CRMError):
        restore_content(export_artifact(source, ring, mutation), backup_ring=ring, notes_ring=None,
                        workspace=source.workspace_token(), profile=source.profile, target=target)
    assert not target.exists()
