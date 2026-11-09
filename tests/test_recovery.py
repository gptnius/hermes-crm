import hashlib
import hmac
import json
import sqlite3
import stat
import uuid

import pytest
from sqlalchemy import select

from hermes_crm.domain import CRM, CRMError, tasks
from hermes_crm.protection import Keyring, ProtectionStore, canonical, seal, decrypt_export
from hermes_crm.recovery import restore_content


@pytest.fixture
def source(tmp_path):
    crm = CRM('sqlite:///' + str(tmp_path / 'source.sqlite3'), profile='synthetic')
    yield crm
    crm.close()


@pytest.fixture
def rings():
    return Keyring('export-old', {'export-old': b'e' * 32}), Keyring('notes-old', {'notes-old': b'n' * 32})


def artifact(source, ring, change=None):
    store = ProtectionStore(source)
    envelope = store.export(ring)
    if change:
        value = decrypt_export(envelope, ring, workspace=store.workspace, profile=source.profile)
        change(value)
        envelope = seal(canonical(value), ring, 'backup', dict(workspace=store.workspace, profile=source.profile))
    value = dict(export_id=str(uuid.uuid4()), envelope=envelope)
    value['operation_mac'] = hmac.new(ring.derive(ring.active, 'export-operation'), canonical(value), hashlib.sha256).hexdigest()
    return canonical(value)


def restore(source, rings, tmp_path, data=None, **kwargs):
    return restore_content(data or artifact(source, rings[0]), backup_ring=rings[0],
                           notes_ring=rings[1], workspace=source.workspace_token(),
                           profile=source.profile, target=tmp_path / 'restored', **kwargs)


def test_operational_roundtrip_keys_receipts_and_no_source_mutation(source, rings, tmp_path):
    contact = source.create('contacts', {'name': 'Synthetic', 'notes': 'ordinary'}, key='create-contact')
    task = source.create('tasks', {'title': 'Synthetic', 'contact_id': contact['id'], 'due_at': '2030-01-01T00:00:00Z'})
    store = ProtectionStore(source)
    op = str(uuid.uuid4())
    response = store.save('contacts', contact['id'], ring=rings[1], operation_id=op,
                         expected_record_version=1, expected_note_version=0, plaintext='SYNTHETIC_PROTECTED')
    with source.engine.begin() as conn:
        conn.execute(tasks.update().where(tasks.c.id == task['id']).values(schedule_status='scheduled', scheduler_job_id='old-job'))
    manifest = restore(source, rings, tmp_path)
    target = tmp_path / 'restored'
    assert stat.S_IMODE(target.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in target.iterdir())
    assert manifest['content_restored'] and not manifest['full_backup'] and not manifest['live_restore']
    assert b'SYNTHETIC_PROTECTED' not in (target / 'recovery.sqlite3').read_bytes()
    recovered = CRM('sqlite:///' + str(target / 'recovery.sqlite3'), profile='synthetic')
    try:
        assert recovered.workspace_token() == source.workspace_token()
        assert recovered.get('contacts', contact['id'])['notes'] == 'ordinary'
        assert recovered.create('contacts', {'name': 'Synthetic', 'notes': 'ordinary'}, key='create-contact')['id'] == contact['id']
        rotated = Keyring('new', {'new': b'x' * 32, **rings[1].keys})
        recovered_store = ProtectionStore(recovered)
        assert recovered_store.reveal('contacts', contact['id'], rotated)['plaintext'] == 'SYNTHETIC_PROTECTED'
        assert recovered_store.save('contacts', contact['id'], ring=rotated, operation_id=op,
                                    expected_record_version=1, expected_note_version=0, plaintext='SYNTHETIC_PROTECTED') == response
        assert recovered.get('tasks', task['id'])['scheduler_job_id'] is None
        assert recovered.get('tasks', task['id'])['schedule_status'] == 'none'
        assert source.get('tasks', task['id'])['scheduler_job_id'] == 'old-job'
        assert recovered.get('tasks', task['id'])['version'] == task['version'] + 1
        with pytest.raises(CRMError):
            recovered.update('tasks', task['id'], {'version': task['version'], 'title': 'stale'})
        current = recovered.get('tasks', task['id'])
        assert recovered.update('tasks', task['id'], {'version': current['version'], 'title': 'fresh'})['title'] == 'fresh'
    finally:
        recovered.close()
    db = sqlite3.connect(target / 'recovery.sqlite3')
    assert db.execute('select scheduler_job_id from recovery_crm_tasks').fetchone() == ('old-job',)
    assert db.execute('pragma foreign_key_check').fetchall() == []
    db.close()


@pytest.mark.parametrize('change', [
    lambda v: v.update(version=True),
    lambda v: v.update(version=1.0),
    lambda v: v.update(version='1'),
    lambda v: v['tables'].pop('crm_contacts'),
    lambda v: v['tables'].pop('crm_custom_values'),
    lambda v: v['tables']['crm_contacts'].append(dict(v['tables']['crm_contacts'][0])),
    lambda v: v['tables']['crm_contacts'][0].update(version=True),
    lambda v: v['tables']['crm_settings'][0].update(value='other'),
    lambda v: v['tables']['crm_custom_schema'][0].update(version=99),
    lambda v: v['tables'].update(unknown=[]),
    lambda v: v['tables']['crm_contacts'][0].update(extra='not supported'),
])
def test_invalid_authenticated_snapshots_leave_no_target(source, rings, tmp_path, change):
    source.create('contacts', {'name': 'Synthetic'})
    with pytest.raises(CRMError):
        restore(source, rings, tmp_path, artifact(source, rings[0], change))
    assert not (tmp_path / 'restored').exists()


def test_fk_and_note_context_rejection(source, rings, tmp_path):
    c = source.create('contacts', {'name': 'Synthetic'})
    source.create('deals', {'title': 'Synthetic', 'contact_id': c['id']})
    data = artifact(source, rings[0], lambda v: v['tables']['crm_contacts'].clear())
    with pytest.raises(CRMError): restore(source, rings, tmp_path, data)
    ProtectionStore(source).save('contacts', c['id'], ring=rings[1], operation_id=str(uuid.uuid4()),
                                expected_record_version=1, expected_note_version=0, plaintext='SYNTHETIC')
    data = artifact(source, rings[0], lambda v: v['tables']['crm_protected_notes'][0].update(version=2))
    with pytest.raises(CRMError): restore(source, rings, tmp_path, data)
    assert not (tmp_path / 'restored').exists()


@pytest.mark.parametrize('failure', ['profile', 'workspace', 'backup', 'notes', 'missing_notes', 'tamper'])
def test_authentication_fails_closed(source, rings, tmp_path, failure):
    c = source.create('contacts', {'name': 'Synthetic'})
    ProtectionStore(source).save('contacts', c['id'], ring=rings[1], operation_id=str(uuid.uuid4()),
                                expected_record_version=1, expected_note_version=0, plaintext='SYNTHETIC')
    data = artifact(source, rings[0])
    args = dict(backup_ring=rings[0], notes_ring=rings[1], workspace=source.workspace_token(),
                profile=source.profile, target=tmp_path / 'restored')
    if failure in ('profile', 'workspace'): args[failure] = 'other'
    if failure == 'backup': args['backup_ring'] = Keyring('export-old', {'export-old': b'x' * 32})
    if failure == 'notes': args['notes_ring'] = Keyring('new', {'new': b'x' * 32})
    if failure == 'missing_notes': args['notes_ring'] = None
    if failure == 'tamper': data = data.replace(b'operation_mac', b'operation_bad')
    with pytest.raises(CRMError): restore_content(data, **args)
    assert not args['target'].exists()


def test_existing_and_symlink_targets_untouched(source, rings, tmp_path):
    target = tmp_path / 'restored'
    target.mkdir()
    (target / 'sentinel').write_text('do not change')
    with pytest.raises(CRMError): restore(source, rings, tmp_path)
    assert (target / 'sentinel').read_text() == 'do not change'
    link = tmp_path / 'symlink'
    link.symlink_to(target)
    with pytest.raises(CRMError):
        restore_content(artifact(source, rings[0]), backup_ring=rings[0], workspace=source.workspace_token(),
                        profile=source.profile, target=link)


def test_relationships_native_and_provider_quarantine(source, rings, tmp_path):
    from hermes_crm.companies import CompanyStore
    from hermes_crm.events import EventStore
    from hermes_crm.native_work import NativeWorkStore, assignments
    from hermes_crm.gmail_history import GmailHistoryStore, connections
    c = source.create('contacts', {'name': 'Synthetic'})
    company = CompanyStore(source).create({'name': 'Synthetic Company'}, actor='test', key='company')
    CompanyStore(source).set_contact_company(c['id'], company['id'], expected_contact_version=1, actor='test', key='link')
    event = EventStore(source).create(dict(title='Synthetic meeting', kind='appointment',
        starts_at='2030-01-01T12:00:00Z', ends_at='2030-01-01T13:00:00Z',
        timezone='UTC', contact_id=c['id'], company_id=company['id']), actor='test', key='event')
    task = source.create('tasks', {'title': 'Synthetic', 'due_at': '2030-01-01T00:00:00Z'})
    NativeWorkStore(source).create(task_id=task['id'], human_owner='Synthetic', prompt='Synthetic analysis',
        success_criteria='Synthetic report', run_at='2030-01-01T12:00:00Z', idempotency_key='native')
    gmail = GmailHistoryStore(source, initialize=True)
    with source.engine.begin() as conn:
        conn.execute(connections.update().where(connections.c.scope == gmail.scope).values(revision=1, connected=1,
                     subject='synthetic', mailbox='synthetic@example.test', issuer='synthetic', active_operation=None))
    result = restore(source, rings, tmp_path)
    assert 'crm_native_assignments' in result['quarantined_tables']
    assert 'crm_gmail_connections' in result['quarantined_tables']
    recovered = CRM('sqlite:///' + str(tmp_path / 'restored' / 'recovery.sqlite3'), profile='synthetic')
    try:
        assert CompanyStore(recovered).get_contact_company(c['id'])['company_id'] == company['id']
        assert EventStore(recovered).get(event['id'])['title'] == 'Synthetic meeting'
        assert CompanyStore(recovered).create({'name': 'Synthetic Company'}, actor='test', key='company')['id'] == company['id']
        NativeWorkStore(recovered)  # Actual strict schema validation, no host context.
        GmailHistoryStore(recovered, initialize=True)
        with recovered.engine.connect() as conn:
            assert conn.execute(select(assignments)).all() == []
            assert conn.execute(select(connections.c.connected)).scalar() == 0
            assert conn.exec_driver_sql('select count(*) from recovery_crm_native_assignments').scalar() == 1
    finally:
        recovered.close()


def test_partial_output_has_no_completion_marker(source, rings, tmp_path, monkeypatch):
    import hermes_crm.recovery as recovery
    original = recovery._private_file
    def fail_manifest(path):
        if path.name == 'manifest.json': raise OSError('synthetic full disk')
        return original(path)
    monkeypatch.setattr(recovery, '_private_file', fail_manifest)
    with pytest.raises(CRMError, match='incomplete target'):
        restore(source, rings, tmp_path)
    assert not (tmp_path / 'restored' / 'manifest.json').exists()
    with pytest.raises(CRMError, match='must not already exist'):
        restore(source, rings, tmp_path)


def test_report_research_and_reexport(source, rings, tmp_path):
    from hermes_crm.report_store import ReportStore
    from hermes_crm.research_store import ResearchStore
    c = source.create('contacts', {'name': 'Synthetic', 'notes': 'Prior'})
    report = ReportStore(source).create('Synthetic report', {'entity': 'contacts', 'columns': ['id', 'name']}, 'report')
    research = ResearchStore(source)
    evidence = research.submit(dict(target_kind='contacts', target_id=c['id'], target_version=c['version'],
        question='Synthetic question', source_url='https://example.test/source', source_title='Synthetic source',
        observed_at='2026-11-08T12:00:00+00:00', claims=['Synthetic claim'], hypotheses=[]), key='evidence')
    proposal = research.propose(dict(evidence_id=evidence['id'], evidence_digest=evidence['digest'],
        evidence_lifecycle_version=evidence['lifecycle_version'], target_version=c['version'], addition='Synthetic addition'), key='proposal')
    restore(source, rings, tmp_path)
    recovered = CRM('sqlite:///' + str(tmp_path / 'restored' / 'recovery.sqlite3'), profile='synthetic')
    try:
        assert ReportStore(recovered).get(report['id']) == report
        r = ResearchStore(recovered)
        assert r.preview(proposal['id'])['proposed_notes'] == 'Prior\n\nSynthetic addition'
        review = {k: proposal[k] for k in ('proposal_version', 'proposal_digest', 'target_version', 'before_hash', 'after_hash')}
        result = r.review(proposal['id'], review, apply=True, key='apply-after-recovery')
        assert result['status'] == 'applied'
        assert recovered.get('contacts', c['id'])['notes'] == 'Prior\n\nSynthetic addition'
        value = decrypt_export(ProtectionStore(recovered).export(rings[0]), rings[0],
                               workspace=recovered.workspace_token(), profile=recovered.profile)
        assert not any(n.startswith('recovery_') for n in value['tables'])
    finally:
        recovered.close()


def test_cli_roundtrip_and_sanitized_bad_input(source, rings, tmp_path):
    import subprocess
    import sys
    from hermes_crm.protection import b64
    path = tmp_path / 'artifact.json'
    path.write_bytes(artifact(source, rings[0]))
    command = [sys.executable, '-m', 'hermes_crm.recovery', '--artifact', str(path),
               '--workspace', source.workspace_token(), '--profile', source.profile,
               '--target', str(tmp_path / 'restored')]
    key_input = json.dumps({'backup': {'active': rings[0].active,
                           'keys': {k: b64(v) for k, v in rings[0].keys.items()}}})
    run = subprocess.run(command, input=key_input, text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)['content_restored']
    bad = subprocess.run(command, input='SYNTHETIC_INVALID_SECRET', text=True, capture_output=True)
    assert bad.returncode == 1
    assert 'SYNTHETIC_INVALID_SECRET' not in bad.stderr + bad.stdout


@pytest.mark.parametrize('name', ['target?query', 'target#fragment', 'target%25escape'])
def test_target_path_punctuation_cannot_redirect_database(source, rings, tmp_path, name):
    contact = source.create('contacts', {'name': 'Synthetic punctuation'})
    sibling = tmp_path / 'target'
    with sqlite3.connect(sibling) as conn:
        conn.execute('create table sentinel (value text)')
        conn.execute("insert into sentinel values ('untouched')")
    before = sibling.read_bytes()
    target = tmp_path / name
    result = restore_content(artifact(source, rings[0]), backup_ring=rings[0],
        workspace=source.workspace_token(), profile=source.profile, target=target)
    assert sibling.read_bytes() == before
    db = target / 'recovery.sqlite3'
    with sqlite3.connect(db) as conn:
        assert conn.execute('select name from crm_contacts where id=?', (contact['id'],)).fetchone() == ('Synthetic punctuation',)
        assert conn.execute('select name from recovery_crm_contacts where id=?', (contact['id'],)).fetchone() == ('Synthetic punctuation',)
    assert result['database_sha256'] == hashlib.sha256(db.read_bytes()).hexdigest()
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(['source.sqlite3', 'target', name])
