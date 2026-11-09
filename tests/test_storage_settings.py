"""Synthetic storage diagnostics: no host, live accounts or network required."""
import asyncio
import hashlib
import logging
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from hermes_crm import native_api, runtime, storage_settings as storage


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = {'home': tmp_path / 'profile-a', 'backend': 'sqlite', 'url': ''}
    state['config'] = {'plugins': {'entries': {'hermes-crm': {'settings': {'backend': 'sqlite'}}}}}
    monkeypatch.setitem(sys.modules, 'hermes_constants', SimpleNamespace(get_hermes_home=lambda: state['home']))
    monkeypatch.setitem(sys.modules, 'hermes_cli.config', SimpleNamespace(load_config_readonly=lambda: state['config']))
    monkeypatch.setitem(sys.modules, 'agent.secret_scope', SimpleNamespace(get_secret=lambda name: state['url']))
    def forbidden(*args, **kwargs):
        raise AssertionError('Storage diagnostics must not initialize CRM')
    monkeypatch.setitem(sys.modules, 'plugins.plugin_storage', SimpleNamespace(plugin_data_dir=forbidden, plugin_db=forbidden))
    monkeypatch.setattr(native_api, 'open_profile_crm', forbidden)
    app = FastAPI()
    app.include_router(native_api.router)
    return TestClient(app), state


def selected(client):
    response = client.get('/storage/status')
    assert response.status_code == 200, response.text
    return response.json()


def check(client, status=None):
    return client.post('/storage/check', json={'selection_token': (status or selected(client))['selection_token']})


def use_postgres(state, url='postgresql://synthetic:fake-secret@fixture.invalid/test'):
    state['config']['plugins']['entries']['hermes-crm']['settings']['backend'] = 'postgres'
    state['url'] = url


def test_no_database_init_status_or_missing_sqlite_check(setup):
    client, state = setup
    assert selected(client)['backend'] == 'sqlite'
    assert check(client).json()['result'] == 'not_initialized'
    assert not state['home'].exists()
    assert client.get('/snapshot').status_code == 503
    assert selected(client)['backend'] == 'sqlite', 'Recovery is independent of failed snapshot'


def test_sqlite_check_preserves_database_bytes_and_records(setup):
    client, state = setup
    path = state['home'] / 'plugin-data/hermes-crm/data.db'
    path.parent.mkdir(parents=True)
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE synthetic (value TEXT)')
        connection.execute("INSERT INTO synthetic VALUES ('keep-me')")
    before = path.read_bytes()
    result = check(client).json()
    assert result['result'] == 'connected' and result['readiness_checked'] is False
    assert path.read_bytes() == before
    with sqlite3.connect(path) as connection:
        assert connection.execute('SELECT value FROM synthetic').fetchall() == [('keep-me',)]
        assert connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [('synthetic',)]


def test_host_lookup_settings_then_legacy_no_environment_fallback(setup, monkeypatch):
    client, state = setup
    monkeypatch.setenv('HERMES_CRM_BACKEND', 'postgres')
    monkeypatch.setenv('HERMES_CRM_DATABASE_URL', 'postgresql://ambient:wrong@wrong.invalid/wrong')
    assert runtime.configured_backend() == 'sqlite'
    state['config']['plugins']['entries']['hermes-crm'] = {'config': {'backend': 'postgres'}}
    assert selected(client)['configuration'] == 'missing_url'
    state['config']['plugins']['entries']['hermes-crm']['settings'] = {'backend': 'sqlite'}
    assert selected(client)['backend'] == 'sqlite'


@pytest.mark.parametrize('backend,url,category', [('bogus','secret','invalid_backend'), ('postgres','','missing_url'), ('postgres','https://private.invalid/secret','invalid_url')])
def test_safe_invalid_configuration_categories(setup, backend, url, category):
    client, state = setup
    state['config']['plugins']['entries']['hermes-crm']['settings']['backend'] = backend
    state['url'] = url
    status = selected(client)
    assert status['configuration'] == category
    assert check(client, status).json()['result'] == category
    assert 'secret' not in str(status) and 'private.invalid' not in str(status)


def test_profile_backend_and_secret_changes_reject_old_selection(setup, monkeypatch):
    client, state = setup
    calls = []
    async def probe(url): calls.append(url); return 'connected'
    monkeypatch.setattr(storage, '_postgres_probe', probe)
    for change in (lambda: state.update(home=state['home'].parent / 'profile-b'), lambda: use_postgres(state), lambda: state.update(url=state['url']+'2')):
        old = selected(client)
        change()
        assert check(client, old).status_code == 409
    assert calls == []
    assert check(client).json()['result'] == 'connected'
    assert calls == [state['url']]


def test_never_accept_arbitrary_probe_destination_or_reflect_caller_secrets(setup):
    client, state = setup
    assert client.get('/storage/status?database_url=private-secret').status_code == 400
    token = selected(client)['selection_token']
    for body in ({'selection_token': token, 'url': 'private-secret'}, {'selection_token': []}, {'selection_token': 'short'}, {'selection_token': 'é' * 64}, {'selection_token': 'x' * 10000}, []):
        response = client.post('/storage/check', json=body)
        assert response.status_code == 400 and 'private-secret' not in response.text
    assert not state['home'].exists()


@pytest.mark.parametrize('error,category', [(RuntimeError('private-secret@private.invalid'),'unavailable'), (TimeoutError('private-secret'),'timeout'), (ImportError('private-secret'),'driver_missing')])
def test_probe_errors_are_redacted(setup, monkeypatch, caplog, error, category):
    client, state = setup
    use_postgres(state)
    async def fail(url):
        logging.getLogger('psycopg').debug('private-secret@private.invalid')
        raise error
    monkeypatch.setattr(storage, '_postgres_probe', fail)
    with caplog.at_level(logging.DEBUG, logger='psycopg'):
        response = check(client)
    assert response.json()['result'] == category
    assert 'private-secret' not in response.text + caplog.text
    assert 'private.invalid' not in response.text + caplog.text
    assert not state['home'].exists()


def test_mid_check_config_change_rejects_result(setup, monkeypatch):
    client, state = setup; use_postgres(state)
    async def changed(url): state['url'] += 'changed'; return 'connected'
    monkeypatch.setattr(storage, '_postgres_probe', changed)
    assert check(client).status_code == 409


def test_async_roundtrip_is_read_only_bounded_and_closes(monkeypatch):
    calls = []
    class Cursor:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): calls.append('cursor-close')
        async def execute(self, sql): calls.append(sql)
        async def fetchone(self): return (1,)
    class Connection:
        def cursor(self): return Cursor()
        async def close(self): calls.append('close')
    async def connect(**kwargs): calls.append(kwargs); return Connection()
    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect)))
    monkeypatch.setattr(storage, '_postgres_parameters', lambda url: {'host': 'fixture', 'connect_timeout':5, 'options':'default_transaction_read_only=on statement_timeout=3000'})
    assert asyncio.run(storage._postgres_probe('postgresql+psycopg://fixture')) == 'connected'
    kwargs = calls[0]
    assert kwargs['host'] == 'fixture'
    assert kwargs['connect_timeout'] == 5 and kwargs['autocommit'] is True and kwargs['prepare_threshold'] is None
    assert 'default_transaction_read_only=on' in kwargs['options'] and 'statement_timeout=3000' in kwargs['options']
    assert calls[1:] == ['SELECT 1', 'cursor-close', 'close', 'close']


def test_deadline_closes_before_query_cancellation(monkeypatch):
    calls = []
    monkeypatch.setattr(storage, 'PROBE_TIMEOUT', .01)
    class Connection:
        closed = False
        async def close(self): self.closed = True; calls.append('closed')
    async def hung(url, holder):
        connection = Connection(); holder.append(connection)
        try: await asyncio.sleep(10)
        except asyncio.CancelledError:
            assert connection.closed, 'Close first to avoid psycopg network cancellation delay'
            calls.append('cancelled')
            raise
    monkeypatch.setattr(storage, '_postgres_roundtrip', hung)
    async def run():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(storage._postgres_probe('fixture'), .3)
    asyncio.run(run())
    assert calls == ['closed', 'cancelled']


def test_connect_deadline_cancels_pending_resolution(monkeypatch):
    monkeypatch.setattr(storage, 'PROBE_TIMEOUT', .01)
    cleaned = []
    async def hung(url, holder):
        try: await asyncio.sleep(10)
        finally: cleaned.append(True)
    monkeypatch.setattr(storage, '_postgres_roundtrip', hung)
    async def run():
        with pytest.raises(TimeoutError): await storage._postgres_probe('fixture')
    asyncio.run(run())
    assert cleaned == [True]


def test_postgres_parameters_explicit_identity_and_no_ambient_fallback(monkeypatch):
    import psycopg
    for key in tuple(storage.os.environ):
        if key.startswith('PG'): monkeypatch.delenv(key)
    url = 'postgresql://synthetic:explicit-password@localhost:5432/synthetic?sslmode=require'
    params = storage._postgres_parameters(url)
    assert params['host'] == 'localhost' and params['dbname'] == 'synthetic' and params['user'] == 'synthetic'
    assert params['password'] == 'explicit-password' and params['passfile'] == storage.os.devnull
    assert params['sslcertmode'] == 'disable' and params['gssencmode'] == 'disable'
    assert params['require_auth'] == 'scram-sha-256,md5,password,none'
    assert params['sslmode'] == 'require'
    for key in ('PGSERVICE', 'PGHOST', 'PGPASSWORD', 'PGPASSFILE', 'PGSSLCERT', 'PGHOSTADDR'):
        monkeypatch.setenv(key, 'never-use-this')
        with pytest.raises(storage.UnsupportedProbe): storage._postgres_parameters(url)
        monkeypatch.delenv(key)
    for invalid in ('postgresql://localhost/db', 'postgresql://user@localhost/db',
                    'postgresql://user:pass@/db', 'postgresql://user:pass@localhost/db?service=other',
                    'postgresql://user:pass@localhost/db?sslcert=secret-file'):
        with pytest.raises(storage.UnsupportedProbe): storage._postgres_parameters(invalid)
    monkeypatch.setattr(psycopg.pq, 'Conninfo', SimpleNamespace(get_defaults=lambda: [], parse=psycopg.pq.Conninfo.parse))
    with pytest.raises(storage.UnsupportedProbe): storage._postgres_parameters(url)


def test_corrupt_sqlite_is_not_reported_connected(setup):
    client, state = setup
    path = state['home'] / 'plugin-data/hermes-crm/data.db'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'not a database' * 50)
    before = path.read_bytes()
    assert check(client).json()['result'] == 'unavailable'
    assert path.read_bytes() == before


def test_sqlite_probe_runs_off_event_loop(setup, monkeypatch):
    import threading
    client, state = setup
    observed = []
    def probe(path):
        observed.append(threading.current_thread().name)
        with pytest.raises(RuntimeError): asyncio.get_running_loop()
        return 'connected'
    monkeypatch.setattr(storage, '_sqlite_probe', probe)
    assert check(client).json()['result'] == 'connected'
    assert observed
