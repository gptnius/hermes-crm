"""Synthetic PostgreSQL exports restored to fresh operational SQLite targets.

An explicit disposable PostgreSQL URL is required. Each case owns one random
schema; no host, key provisioning, provider access or scheduler is invoked.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM, CRMError
from hermes_crm.protection import ProtectionStore, decrypt_export
from hermes_crm.task_ownership import TaskOwnership
import test_recovery as contracts
from test_recovery import rings

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def source():
    schema = 'crm_recovery_test_' + uuid.uuid4().hex
    instance = None
    try:
        instance = CRM(URL, schema=schema, profile='synthetic')
        yield instance
    finally:
        if instance:
            instance.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


def test_operational_roundtrip(source, rings, tmp_path):
    contracts.test_operational_roundtrip_keys_receipts_and_no_source_mutation(source, rings, tmp_path)


def test_relationships_and_runtime_quarantine(source, rings, tmp_path):
    contracts.test_relationships_native_and_provider_quarantine(source, rings, tmp_path)


def test_report_research_and_reexport(source, rings, tmp_path):
    contracts.test_report_research_and_reexport(source, rings, tmp_path)


@pytest.mark.parametrize('failure', ['profile', 'workspace', 'backup', 'notes', 'missing_notes', 'tamper'])
def test_authentication_fails_closed(source, rings, tmp_path, failure):
    contracts.test_authentication_fails_closed(source, rings, tmp_path, failure)


def test_foreign_keys_and_note_context(source, rings, tmp_path):
    contracts.test_fk_and_note_context_rejection(source, rings, tmp_path)


def test_existing_targets_untouched(source, rings, tmp_path):
    contracts.test_existing_and_symlink_targets_untouched(source, rings, tmp_path)


def test_interrupted_output(source, rings, tmp_path, monkeypatch):
    contracts.test_partial_output_has_no_completion_marker(source, rings, tmp_path, monkeypatch)


def test_owned_customized_content_and_local_replays(source, rings, tmp_path):
    """Exercise boolean/integer/custom schema portability and scoped receipts."""
    field_payload = dict(key='segment', label='Segment', type='single-select', choices=['A', 'B'])
    field = source.create_field('contacts', field_payload, key='field')
    stage_payload = dict(key='contract', label='Contract', probability=85)
    stage = source.create_stage(stage_payload, key='stage')
    contact_payload = dict(name='Synthetic portable', notes='Ordinary plaintext', custom_fields={'segment': 'A'})
    contact = source.create('contacts', contact_payload, key='contact')
    deal_payload = dict(title='Synthetic contract', contact_id=contact['id'], stage='contract', value=12345)
    deal = source.create('deals', deal_payload, key='deal')
    policy_payload = dict(version=0, required=True, default_owner_label='Synthetic owner')
    policy = TaskOwnership(source).set_policy(policy_payload, key='policy')
    task_payload = dict(title='Synthetic owned task', due_at='2030-03-10T12:00:00.123456+05:30',
                        contact_id=contact['id'], owner_label='Synthetic owner',
                        owner_source='default', owner_policy_version=policy['version'])
    task = source.create('tasks', task_payload, key='owned-task')
    store = ProtectionStore(source)
    snapshot_before = decrypt_export(store.export(rings[0]), rings[0],
                                     workspace=source.workspace_token(), profile=source.profile)
    manifest = contracts.restore(source, rings, tmp_path)
    assert manifest['content_restored'] and not manifest['live_restore']
    recovered = CRM('sqlite:///' + str(tmp_path / 'restored' / 'recovery.sqlite3'), profile=source.profile)
    try:
        assert recovered.workspace_token() == source.workspace_token()
        assert recovered.get('contacts', contact['id']) == contact
        assert recovered.get('deals', deal['id']) == deal
        assert recovered.get('tasks', task['id']) == task
        assert recovered.create_field('contacts', field_payload, key='field') == field
        assert recovered.create_stage(stage_payload, key='stage') == stage
        assert recovered.create('contacts', contact_payload, key='contact') == contact
        assert recovered.create('deals', deal_payload, key='deal') == deal
        assert recovered.create('tasks', task_payload, key='owned-task') == task
        assert TaskOwnership(recovered).policy() == policy
        assert TaskOwnership(recovered).set_policy(policy_payload, key='policy') == policy
        with pytest.raises(CRMError):
            recovered.create('tasks', dict(title='Missing required owner', due_at=task['due_at']))
        changed = recovered.update('contacts', contact['id'],
            dict(version=contact['version'], custom_fields={'segment': 'B'}), key='fresh-edit')
        assert changed['custom_fields'] == {'segment': 'B'}
        assert recovered.update('deals', deal['id'],
            dict(version=deal['version'], title='Fresh contract'))['title'] == 'Fresh contract'
        assert recovered.update('tasks', task['id'], dict(version=task['version'],
            owner_policy_version=policy['version'], status='done'))['status'] == 'done'
        new_task = recovered.create('tasks', dict(task_payload, title='Fresh owned task'), key='fresh-task')
        assert new_task['id'] != task['id'] and new_task['owner_label'] == 'Synthetic owner'
        # Writes and local receipt replay on the destination never modify source.
        after = decrypt_export(store.export(rings[0]), rings[0],
                               workspace=source.workspace_token(), profile=source.profile)
        assert after['tables'] == snapshot_before['tables']
    finally:
        recovered.close()
