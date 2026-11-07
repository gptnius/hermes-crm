"""Synthetic storage/REST tests: no host, account, OAuth or provider calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
import uuid

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from hermes_crm.domain import CRM, CRMError
from hermes_crm.gmail_reader import IdentityBinding, MessageMetadata, ScanResult
from hermes_crm.gmail_history import GmailHistoryStore, metadata, observations, snapshots
from hermes_crm.gmail_history_api import build_router


class Reader:
    def __init__(self):
        self.calls = 0
        self.hook = lambda: None
        self.partial = False
    def verify_identity(self, mailbox, guard):
        guard()
        self.calls += 1
        self.hook()
        guard()
        return IdentityBinding('synthetic-sub', mailbox)
    def scan_contact(self, binding, email, start_ms, end_ms, guard):
        guard()
        self.calls += 1
        self.hook()
        guard()
        assert email == 'contact@example.test'
        assert end_ms - start_ms in (7 * 86400000, 30 * 86400000)
        return ScanResult((MessageMetadata('msg1','thread1',end_ms-1000,('SENT',),
            (('Subject','Synthetic <not HTML>'),),(),'observed_in_sent'),),
            'partial' if self.partial else 'complete_query', ('unavailable',) if self.partial else (), 1)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **k: pytest.fail('Network forbidden'))
    crm = CRM(f'sqlite:///{tmp_path}/mail.db', profile='synthetic')
    contact = crm.create('contacts', {'name':'Contact', 'email':'contact@example.test'})
    store = GmailHistoryStore(crm, initialize=True)
    reader = Reader()
    yield crm, store, reader, contact
    crm.close()


def verify(setup, **kw):
    args = dict(kind='verify', operation_id=str(uuid.uuid4()), expected_revision=setup[1].status()['revision'],
                reader=setup[2], guard=lambda: None, mailbox='own@example.test')
    args.update(kw)
    return setup[1].run(**args)


def sync(setup, **kw):
    args = dict(kind='sync', operation_id=str(uuid.uuid4()), expected_revision=setup[1].status()['revision'],
                reader=setup[2], guard=lambda: None, contact_id=setup[3]['id'], expected_contact_version=1, days=7)
    args.update(kw)
    return setup[1].run(**args)


def count(crm, table):
    with crm.engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(table)).scalar_one()


def test_lazy_gets_create_no_tables(tmp_path):
    crm = CRM(f'sqlite:///{tmp_path}/lazy.db')
    contact = crm.create('contacts', {'name':'Contact'})
    before = inspect(crm.engine).get_table_names()
    store = GmailHistoryStore(crm)
    assert store.status()['revision'] == 0
    assert store.page(contact['id'])['items'] == []
    assert before == inspect(crm.engine).get_table_names()
    crm.close()


def test_manual_sync_ledger_and_duplicate_replay(setup):
    crm, store, reader, contact = setup
    operation_id = str(uuid.uuid4())
    first = verify(setup, operation_id=operation_id)
    assert first['state'] == 'finished'
    assert verify(setup, operation_id=operation_id, expected_revision=0) == first
    assert reader.calls == 1
    ident, revision = str(uuid.uuid4()), store.status()['revision']
    result = sync(setup, operation_id=ident)
    assert result['state'] == 'finished'
    assert sync(setup, operation_id=ident, expected_revision=revision) == result
    assert reader.calls == 2
    assert count(crm, observations) == 1
    assert store.page(contact['id'])['items'][0]['description'] == 'observed_in_sent'
    sync(setup)
    assert count(crm, observations) == 2 and count(crm, snapshots) == 1
    assert store.page(contact['id'])['total'] == 1
    assert 'email' not in crm.contact_detail(contact['id']).get('activities', {})


def test_local_clear_disconnect_account_rebinding(setup):
    crm, store, reader, contact = setup
    verify(setup); sync(setup)
    store.mutate_local('disconnect', store.status()['revision'])
    assert not store.status()['connected']
    assert store.page(contact['id'])['total'] == 1
    with pytest.raises(CRMError, match='clear'):
        verify(setup)
    store.mutate_local('clear', store.status()['revision'])
    assert store.page(contact['id'])['total'] == 0
    assert count(crm, observations) == 0
    assert verify(setup)['state'] == 'finished'


def test_partial_and_safe_failure(setup):
    crm, store, reader, contact = setup
    verify(setup)
    reader.partial = True
    assert sync(setup)['state'] == 'partial'
    reader.hook = lambda: (_ for _ in ()).throw(RuntimeError('SECRET PROVIDER BODY'))
    failed = sync(setup)
    assert failed['state'] == 'failed' and 'SECRET' not in str(failed)
    assert count(crm, observations) == 1


def test_contact_changed_during_scan_discards_metadata(setup):
    crm, store, reader, contact = setup
    verify(setup)
    reader.hook = lambda: crm.update('contacts', contact['id'], {'version':1, 'email':'changed@example.test'})
    assert sync(setup)['state'] == 'failed'
    assert count(crm, observations) == 0


def test_disconnect_clear_reverify_aba_fences_old_operation(setup):
    crm, store, reader, contact = setup
    verify(setup)
    def change():
        store.mutate_local('disconnect', store.status()['revision'])
        store.mutate_local('clear', store.status()['revision'])
        other = list(setup); other[2] = Reader()
        verify(other)
    reader.hook = change
    assert sync(setup)['state'] == 'cancelled'
    assert store.status()['connected']
    assert count(crm, observations) == 0


def test_false_host_guard_prevents_read(setup):
    assert verify(setup, guard=lambda: False)['state'] == 'failed'
    assert setup[2].calls == 0


def test_concurrent_sync_only_one_dispatch_and_disconnect_cancels(setup):
    crm, store, reader, contact = setup
    verify(setup)
    started, release = Event(), Event()
    reader.hook = lambda: (started.set(), release.wait(5))
    with ThreadPoolExecutor(2) as pool:
        future = pool.submit(sync, setup)
        assert started.wait(3)
        with pytest.raises(CRMError, match='running'):
            sync(setup)
        assert store.status()['operation']['state'] == 'running'
        store.mutate_local('disconnect', store.status()['revision'])
        release.set()
        assert future.result()['state'] == 'cancelled'
    assert reader.calls == 2 and count(crm, observations) == 0


def test_profile_scope_isolation(setup):
    crm, store, reader, contact = setup
    verify(setup); sync(setup)
    alternate = CRM(crm.url, profile='another')
    try:
        other = GmailHistoryStore(alternate)
        assert not other.status()['connected']
        assert other.page(contact['id'])['total'] == 0
    finally:
        alternate.close()


def test_postgres_ddl_compiles_without_sqlite_specific_constructs():
    for table in metadata.sorted_tables:
        assert 'CREATE TABLE' in str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_authenticated_routes_are_lazy_strict_and_disabled(setup):
    crm, store, reader, contact = setup
    @contextmanager
    def service():
        try:
            yield crm
        except CRMError as error:
            raise HTTPException(error.status, detail=error.message) from None
    def require(crm, token):
        if token != crm.workspace_token():
            raise CRMError('Changed workspace', 409)
    app = FastAPI()
    app.include_router(build_router(service, require, lambda crm: {'enabled':False,'reader':reader,'guard':lambda:None}))
    client = TestClient(app)
    token = crm.workspace_token()
    assert client.get('/email/status').status_code == 422
    assert client.get('/email/status', params={'workspace_token':'wrong'}).status_code == 409
    for endpoint in ('status','setup',f'contacts/{contact["id"]}'):
        assert client.get('/email/'+endpoint, params={'workspace_token':token}).status_code == 200
    body = dict(workspace_token=token, expected_revision=0, operation_id=str(uuid.uuid4()),mailbox='own@example.test',consent=True)
    assert client.post('/email/verify', json=body).status_code == 503
    assert client.post('/email/verify', json=dict(body, subject='attacker')).status_code == 422
    assert client.post('/email/verify', json=dict(body, consent=False)).status_code == 422
    assert client.get('/email/status', params={'workspace_token':token, 'backend':'other'}).status_code == 400
    assert client.get('/email/contacts/'+contact['id'], params={'workspace_token':token, 'limit':101}).status_code == 422
    assert reader.calls == 0


def test_atomic_publish_failure_leaves_old_evidence(setup, monkeypatch):
    crm, store, reader, contact = setup
    verify(setup); sync(setup)
    from sqlalchemy import event
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith('INSERT INTO crm_gmail_observations'):
            raise RuntimeError('Synthetic persistence failure')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        assert sync(setup)['state'] == 'failed'
    finally:
        event.remove(crm.engine, 'before_cursor_execute', fail)
    assert count(crm, observations) == 1 and count(crm, snapshots) == 1
    assert store.page(contact['id'])['total'] == 1


def test_idempotent_lost_response_survives_reopen(setup):
    crm, store, reader, contact = setup
    ident = str(uuid.uuid4())
    result = verify(setup, operation_id=ident)
    reopened = CRM(crm.url, profile=crm.profile)
    try:
        new_setup = reopened, GmailHistoryStore(reopened, initialize=True), reader, contact
        assert verify(new_setup, operation_id=ident, expected_revision=0) == result
        assert reader.calls == 1
        with pytest.raises(CRMError, match='already used'):
            verify(new_setup, operation_id=ident, expected_revision=0, mailbox='other@example.test')
    finally:
        reopened.close()


def test_window_and_immutable_provenance(setup):
    crm, store, reader, contact = setup
    verify(setup)
    operation = sync(setup, days=30)
    assert operation['end_ms'] - operation['start_ms'] == 30 * 86400000
    assert operation['coverage'] == 'complete_query'
    import json
    with crm.engine.connect() as conn:
        row = conn.execute(select(observations)).mappings().one()
        provenance = json.loads(row['provenance'])
        assert provenance['adapter'] == 'gmail-readonly-v1'
        assert provenance['contact_version'] == 1
        assert provenance['start_ms'] == operation['start_ms']


def test_schema_mismatch_rejected_without_migration(setup):
    from sqlalchemy import text
    crm, store, reader, contact = setup
    with crm.engine.begin() as conn:
        conn.execute(text('ALTER TABLE crm_gmail_connections ADD COLUMN unexpected TEXT'))
    with pytest.raises(CRMError, match='explicit migration'):
        GmailHistoryStore(crm, initialize=True)


@pytest.mark.parametrize('kind', ['disconnect', 'clear'])
def test_local_action_lost_response_receipt_replays_once(setup, kind):
    crm, store, reader, contact = setup
    verify(setup); sync(setup)
    revision = store.status()['revision']
    ident = str(uuid.uuid4())
    result = store.mutate_local(kind, revision, ident)
    assert result['id'] == ident and result['state'] == 'finished'
    assert store.mutate_local(kind, revision, ident) == result
    assert store.status()['revision'] == revision + 1
    assert store.status()['operation'] == result
    assert reader.calls == 2
