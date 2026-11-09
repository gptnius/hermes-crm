from contextlib import contextmanager
import json
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM, CRMError
from hermes_crm.gmail_bridge_api import build_router
from hermes_crm.gmail_bridge_runtime import GmailBridgeRuntime
from hermes_crm.gmail_bridge_store import GmailBridgeStore

@pytest.fixture
def app(tmp_path):
    crm = CRM('sqlite:///' + str(tmp_path / 'crm.db'), profile='synthetic')
    token = crm.workspace_token()
    @contextmanager
    def service():
        try:
            yield crm
        except CRMError as e:
            raise HTTPException(e.status, detail={'error': e.message})
    def require(crm, supplied):
        if supplied != token:
            raise CRMError('Workspace changed', 409)
    def runtime(crm):
        return GmailBridgeRuntime(crm, selection=lambda: (tmp_path, False, ''))
    api = FastAPI()
    api.include_router(build_router(service, require, runtime))
    with TestClient(api) as client:
        yield client, crm, token
    crm.close()

def test_reads_default_off_and_no_secret_fields(app):
    client, crm, token = app
    for route in ('status', 'setup', 'unresolved', 'contacts/missing', 'operations/missing'):
        response = client.get('/email-bridge/' + route, params={'workspace_token': token})
        assert response.status_code == 200
        assert 'selector_fingerprint' not in response.text
        assert 'google_token.json' not in response.text
    assert not GmailBridgeStore(crm).status()['enabled']

@pytest.mark.parametrize('query', ['workspace_token=x', 'other_profile=other', 'limit=-1', 'limit=1&limit=2', 'path=/private'])
def test_query_rejected(app, query):
    client, _, token = app
    response = client.get('/email-bridge/unresolved?workspace_token=' + token + '&' + query)
    assert response.status_code in (400, 409, 422)

def test_auth_required_every_read(app):
    client, _, _ = app
    for route in ('status', 'setup', 'unresolved', 'contacts/x', 'operations/x'):
        assert client.get('/email-bridge/' + route).status_code == 422

@pytest.mark.parametrize('consent', [False, 1, 'true', None])
def test_consent_cannot_be_coerced(app, consent):
    client, _, token = app
    body = dict(workspace_token=token, expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=consent)
    assert client.post('/email-bridge/verify', json=body).status_code == 422

def test_disabled_verify_and_strict_body(app):
    client, _, token = app
    body = dict(workspace_token=token, expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=True)
    assert client.post('/email-bridge/verify', json=body).status_code == 409
    assert client.post('/email-bridge/verify', json=dict(body, executable='/private')).status_code == 422

def test_clear_requires_confirmation_and_local_controls_work_disabled(app):
    client, crm, token = app
    body = dict(workspace_token=token, expected_revision=0, operation_key='clear', action='clear')
    assert client.post('/email-bridge/control', json=body).status_code == 400
    assert client.post('/email-bridge/control', json=dict(body, confirm=True)).status_code == 200
    assert GmailBridgeStore(crm).status()['revision'] == 1

@pytest.fixture
def enabled_app(tmp_path):
    from hermes_crm.gmail_incremental import MailboxVerification, SyncResult
    crm = CRM('sqlite:///' + str(tmp_path / 'enabled.db'), profile='synthetic')
    crm.create('contacts', {'name': 'Synthetic', 'email': 'contact@example.test'})
    token = crm.workspace_token()
    calls = []
    class Reader:
        def verify_mailbox(self, mailbox, guard):
            assert guard()
            calls.append('verify')
            return MailboxVerification(mailbox, '100')
        def incremental(self, mailbox, checkpoint, guard):
            assert guard()
            calls.append('sync')
            return SyncResult('complete', '101', (), 'incremental_history')
        def bootstrap(self, mailbox, start, end, guard):
            assert guard()
            calls.append('bootstrap')
            return SyncResult('complete', '102', (), 'bounded_bootstrap')
    class Runtime:
        selector_fingerprint = 'a' * 64
        clock = staticmethod(lambda: 1700000000)
        def setup(self):
            return {'available': True}
        def guard(self):
            return True
        host_guard = guard
        @contextmanager
        def reader(self, mailbox, lease_guard=lambda: True):
            yield Reader(), lease_guard
            assert lease_guard(), 'Session cleanup must precede publication'
    @contextmanager
    def service():
        try:
            yield crm
        except CRMError as exc:
            raise HTTPException(exc.status, detail={'error': exc.message})
    def require(crm, supplied):
        if supplied != token:
            raise CRMError('Workspace changed', 409)
    api = FastAPI()
    api.include_router(build_router(service, require, lambda crm: Runtime()))
    with TestClient(api) as client:
        yield client, crm, token, calls, Runtime
    crm.close()

def test_verified_cursor_sync_replay_and_private_receipt(enabled_app):
    client, crm, token, calls, _ = enabled_app
    body = dict(workspace_token=token, expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=True)
    first = client.post('/email-bridge/verify', json=body)
    assert first.status_code == 200, first.text
    assert calls == ['verify']
    assert GmailBridgeStore(crm).status()['checkpoint'] == '100'
    assert client.post('/email-bridge/verify', json=body).json() == first.json()
    assert calls == ['verify']
    sync = dict(workspace_token=token, expected_revision=1, operation_key='sync', consent=True)
    result = client.post('/email-bridge/sync', json=sync)
    assert result.status_code == 200, result.text
    assert result.json()['outcome']['status'] == 'complete'
    assert calls == ['verify', 'sync']
    assert client.post('/email-bridge/sync', json=sync).json() == result.json()
    assert calls == ['verify', 'sync']
    for field in ('lease', 'scope', 'token', 'selector_fingerprint'):
        assert field not in result.text
    assert client.post('/email-bridge/sync', json=dict(sync, mode='7days')).status_code == 409

def test_poll_requires_explicit_local_opt_in(enabled_app):
    client, crm, token, calls, _ = enabled_app
    GmailBridgeStore(crm).bind_verified('bind', selector_fingerprint='a'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    body = dict(workspace_token=token, expected_revision=1, operation_key='poll', trigger='poll', consent=True)
    assert client.post('/email-bridge/sync', json=body).status_code == 409
    assert not calls

def test_failure_is_unknown_and_never_redispatched(enabled_app):
    client, crm, token, calls, Runtime = enabled_app
    @contextmanager
    def broken(self, mailbox, lease_guard=lambda: True):
        calls.append('attempt')
        raise TimeoutError('PRIVATE credential /private/path')
        yield
    Runtime.reader = broken
    body = dict(workspace_token=token, expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=True)
    first = client.post('/email-bridge/verify', json=body)
    assert first.status_code == 200
    assert first.json()['status'] == 'unknown'
    assert 'PRIVATE' not in first.text
    assert client.post('/email-bridge/verify', json=body).json() == first.json()
    assert calls == ['attempt']
    assert not GmailBridgeStore(crm).status()['enabled']

def test_sync_unknown_keeps_old_cursor_and_no_repeat(enabled_app):
    client, crm, token, calls, Runtime = enabled_app
    store = GmailBridgeStore(crm)
    store.bind_verified('bind', selector_fingerprint='a'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    @contextmanager
    def broken(self, mailbox, lease_guard=lambda: True):
        calls.append('attempt')
        raise TimeoutError('PRIVATE')
        yield
    Runtime.reader = broken
    body = dict(workspace_token=token, expected_revision=1, operation_key='sync', consent=True)
    first = client.post('/email-bridge/sync', json=body)
    assert first.json()['outcome']['status'] == 'unknown'
    assert store.status()['checkpoint'] == '100'
    assert client.post('/email-bridge/sync', json=body).json() == first.json()
    assert calls == ['attempt']

def test_publish_context_guard_blocks_verify(enabled_app):
    client, crm, token, calls, Runtime = enabled_app
    Runtime.host_guard = lambda self: False
    body = dict(workspace_token=token, expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=True)
    response = client.post('/email-bridge/verify', json=body)
    assert response.json()['status'] == 'unknown'
    assert GmailBridgeStore(crm).status()['revision'] == 0
    assert not GmailBridgeStore(crm).status()['enabled']

def test_selector_change_aborts_before_sync_dispatch(enabled_app):
    client, crm, token, calls, Runtime = enabled_app
    GmailBridgeStore(crm).bind_verified('bind', selector_fingerprint='b'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    body = dict(workspace_token=token, expected_revision=1, operation_key='sync', consent=True)
    response = client.post('/email-bridge/sync', json=body)
    assert response.json()['outcome']['status'] == 'unknown'
    assert not calls

def test_metadata_stays_out_of_ordinary_projection(enabled_app):
    from hermes_crm.gmail_incremental import Observation, SyncResult
    client, crm, token, _, _ = enabled_app
    store = GmailBridgeStore(crm)
    store.bind_verified('bind', selector_fingerprint='a'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    lease = store.begin_sync_once('seed', expected_revision=1)
    item = Observation('message1', 'thread1', 1000, '101', (), (('from','own@example.test'), ('to','contact@example.test'), ('subject','PRIVATE METADATA SUBJECT')))
    store.finish_sync(lease, SyncResult('complete', '101', (item,), 'incremental_history'))
    assert 'PRIVATE METADATA SUBJECT' not in json.dumps(crm.snapshot())
    page = store.page()
    contact_id = page['items'][0]['current_match']['matches'][0]['contact_id']
    response = client.get('/email-bridge/contacts/' + contact_id, params={'workspace_token': token})
    assert 'PRIVATE METADATA SUBJECT' in response.text

def test_actual_transport_session_closes_before_atomic_publication(tmp_path, monkeypatch):
    """Real subprocess adapter, synthetic executable/account marker only."""
    import sys
    executable = tmp_path / 'fake-gws'
    connection = tmp_path / 'google_token.json'
    connection.write_text('synthetic-not-a-credential')
    connection.chmod(0o600)
    executable.write_text(f'#!{sys.executable}\n' + '''import sys, json
if sys.argv[1:] == ['--version']:
 print('gws 0.22.5\\nThis is not an officially supported Google product.')
elif sys.argv[1:4] == ['gmail', 'users', 'getProfile']:
 print(json.dumps({'emailAddress':'own@example.test','historyId':'100'}))
elif sys.argv[1:5] == ['gmail', 'users', 'history', 'list']:
 print(json.dumps({'historyId':'101','history':[]}))
else:
 sys.exit(1)
''')
    executable.chmod(0o700)
    crm = CRM('sqlite:///' + str(tmp_path / 'actual.db'), profile='synthetic')
    token = crm.workspace_token()
    @contextmanager
    def service():
        try:
            yield crm
        except CRMError as exc:
            raise HTTPException(exc.status, detail={'error': exc.message})
    def require(crm, supplied):
        assert supplied == token
    # Fail hooks must never run on success: earlier code swallowed exit guard failures.
    monkeypatch.setattr(GmailBridgeStore, 'fail_verify', lambda *a, **k: pytest.fail('success entered fail_verify'))
    monkeypatch.setattr(GmailBridgeStore, 'fail_sync', lambda *a, **k: pytest.fail('success entered fail_sync'))
    api = FastAPI()
    api.include_router(build_router(service, require, lambda crm: GmailBridgeRuntime(crm,
        selection=lambda: (tmp_path, True, str(executable)))))
    try:
        with TestClient(api) as client:
            response = client.post('/email-bridge/verify', json=dict(workspace_token=token,
                expected_revision=0, operation_key='verify', own_mailbox='own@example.test', consent=True))
            assert response.status_code == 200, response.text
            assert GmailBridgeStore(crm).status()['checkpoint'] == '100'
            response = client.post('/email-bridge/sync', json=dict(workspace_token=token,
                expected_revision=1, operation_key='sync', consent=True))
            assert response.status_code == 200, response.text
            assert response.json()['outcome']['status'] == 'complete'
            assert GmailBridgeStore(crm).status()['checkpoint'] == '101'
    finally:
        crm.close()

def test_company_history_requires_explicit_membership_and_never_calls_provider(enabled_app):
    from hermes_crm.companies import CompanyStore
    from hermes_crm.gmail_incremental import Observation, SyncResult
    client, crm, token, calls, Runtime = enabled_app
    contact = crm.create('contacts', {'name': 'Linked', 'email': 'linked@example.test'})
    crm.create('contacts', {'name': 'Unlinked', 'email': 'unlinked@example.test', 'company': 'Explicit company'})
    companies = CompanyStore(crm)
    company = companies.create({'name': 'Explicit company', 'domain': 'example.test'}, actor='test', key='company')
    companies.set_contact_company(contact['id'], company['id'], expected_contact_version=1, actor='test', key='link')
    store = GmailBridgeStore(crm)
    store.bind_verified('bind', selector_fingerprint='a'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    lease = store.begin_sync_once('seed', expected_revision=1)
    observations = tuple(Observation(mid, 'thread', 1000, '101', (),
        (('from', 'own@example.test'), ('to', address))) for mid, address in
        [('linked', 'linked@example.test'), ('unlinked', 'unlinked@example.test')])
    store.finish_sync(lease, SyncResult('complete', '101', observations, 'incremental_history'))
    Runtime.reader = lambda *a, **kw: pytest.fail('Company navigation called provider')
    route = '/email-bridge/companies/' + company['id']
    assert client.get(route).status_code == 422
    assert client.get(route, params={'workspace_token': 'wrong'}).status_code == 409
    assert client.get(route, params={'workspace_token': token, 'profile': 'other'}).status_code == 200
    assert client.get(route, params={'workspace_token': token, 'other_profile': 'other'}).status_code == 400
    assert client.get(route, params={'workspace_token': token, 'limit': 101}).status_code == 422
    page = client.get(route, params={'workspace_token': token}).json()
    assert page['total'] == 1
    assert page['items'][0]['message_id'] == 'linked'
    assert page['association_basis'] == 'current_explicit_company_contacts'
    companies.set_contact_company(contact['id'], None, expected_contact_version=2, actor='test', key='unlink')
    assert client.get(route, params={'workspace_token': token}).json()['total'] == 0
    assert not calls


def test_reserved_profile_query_does_not_select_service_or_connection(enabled_app):
    client, crm, token, calls, _ = enabled_app
    store = GmailBridgeStore(crm)
    store.bind_verified('bind', selector_fingerprint='a'*64, mailbox='own@example.test', expected_revision=0, initial_checkpoint='100')
    normal = client.get('/email-bridge/status', params={'workspace_token': token}).json()
    for profile in ('current', 'default', 'secondary', '../../other'):
        response = client.get('/email-bridge/status', params={'workspace_token': token, 'profile': profile})
        assert response.status_code == 200
        assert response.json() == normal
        assert client.get('/email-bridge/status', params={'workspace_token': 'wrong', 'profile': profile}).status_code == 409
    assert crm.profile == 'synthetic'
    assert not calls
    assert client.get('/email-bridge/status', params={'workspace_token': token, 'home': '/other'}).status_code == 400
    assert client.get('/email-bridge/status?workspace_token=' + token + '&profile=current&profile=secondary').status_code == 400
