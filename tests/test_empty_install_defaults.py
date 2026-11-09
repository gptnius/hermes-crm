"""Release regressions using synthetic temporary storage, never a user's profile.

Native storage/config below are host doubles, not installer or activation proof.
CLI server launch is intercepted; the CRM constructor and REST reads are real.
"""
import importlib
import sqlite3
import sys
from types import ModuleType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, Table, inspect, select

from hermes_crm.domain import CRM, settings, activity
from hermes_crm.companies import CompanyStore
from hermes_crm.events import EventStore
from hermes_crm.demo import seed
from hermes_crm import native_api, runtime, web


def snapshot(crm):
    with crm.engine.connect() as conn:
        return {name: sorted((tuple(row) for row in conn.execute(select(
            Table(name, MetaData(), autoload_with=conn)))), key=repr)
            for name in inspect(conn).get_table_names()}


def assert_empty(crm):
    for kind in ('contacts', 'deals', 'tasks'):
        assert crm.list(kind) == []
    for store in (CompanyStore, EventStore):
        assert store(crm).list()['total'] == 0
    with crm.engine.connect() as conn:
        assert conn.execute(select(settings.c.value).where(settings.c.key == 'demo')).scalar() is None


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    for key in ('HERMES_CRM_DATABASE_URL', 'HERMES_CRM_POSTGRES_SCHEMA'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('HERMES_CRM_BACKEND', 'sqlite')
    monkeypatch.setenv('HERMES_CRM_DATA_DIR', str(tmp_path / 'standalone'))
    return tmp_path


def test_default_constructor_and_standalone_reads_are_empty(isolated_home):
    crm = CRM()
    try:
        assert_empty(crm)
        with TestClient(web.create_app(crm)) as client:
            for kind in ('contacts', 'deals', 'tasks'):
                response = client.get('/api/' + kind)
                assert response.status_code == 200, response.text
                assert response.json() == []
        assert_empty(crm)
    finally:
        crm.close()
    assert (isolated_home / 'standalone' / 'data.db').is_file()


@pytest.fixture
def native_profiles(isolated_home, monkeypatch):
    state = {'profile': 'alpha'}
    def data_dir(name):
        assert name == 'hermes-crm'
        path = isolated_home / state['profile'] / 'plugin-data' / name
        path.mkdir(parents=True, exist_ok=True)
        return path
    storage = ModuleType('plugins.plugin_storage')
    storage.plugin_data_dir = data_dir
    storage.plugin_db = lambda name: sqlite3.connect(data_dir(name) / 'data.db', check_same_thread=False)
    constants = ModuleType('hermes_constants')
    constants.get_hermes_home = lambda: isolated_home / state['profile']
    constants.profile_name_for_home = lambda home: home.name
    config = ModuleType('hermes_cli.config')
    config.load_config_readonly = lambda: {}
    for name, module in [('plugins', ModuleType('plugins')), ('plugins.plugin_storage', storage),
                         ('hermes_constants', constants), ('hermes_cli', ModuleType('hermes_cli')),
                         ('hermes_cli.config', config)]:
        monkeypatch.setitem(sys.modules, name, module)
    app = FastAPI()
    app.include_router(native_api.router, prefix='/crm')
    return state, TestClient(app)


def test_native_default_reads_and_second_profile_isolation(native_profiles):
    state, client = native_profiles
    with client:
        for profile in ('alpha', 'beta'):
            state['profile'] = profile
            crm = runtime.open_profile_crm()
            try:
                assert crm.profile == profile
                assert_empty(crm)
            finally:
                crm.close()
            meta = client.get('/crm/meta').json()
            assert meta['profile'] == profile
            token = meta['workspace_token']
            for kind in ('contacts', 'deals', 'tasks', 'companies', 'events'):
                response = client.get('/crm/' + kind, params={'workspace_token': token})
                assert response.status_code == 200, response.text
                data = response.json()
                if isinstance(data, list):
                    assert data == []
                else:
                    assert data['total'] == 0
            crm = runtime.open_profile_crm()
            try:
                assert_empty(crm)
                if profile == 'alpha':
                    seed(crm)
                    assert len(crm.list('contacts')) == 8
                    alpha_token = token
                else:
                    assert token != alpha_token
            finally:
                crm.close()
        state['profile'] = 'alpha'
        assert len(client.get('/crm/contacts').json()) == 8


def test_seeded_records_and_provenance_survive_reopen_and_reads(isolated_home):
    crm = CRM()
    seed(crm)
    crm.workspace_token()  # metadata is normally created when opening the UI
    before = snapshot(crm)
    assert [len(crm.list(k)) for k in ('contacts', 'deals', 'tasks')] == [8, 8, 5]
    with crm.engine.connect() as conn:
        assert set(conn.execute(select(activity.c.actor)).scalars()) == {'demo'}
        assert conn.execute(select(settings.c.value).where(settings.c.key == 'demo')).scalar_one() == 'true'
    crm.close()
    reopened = CRM()
    try:
        with TestClient(web.create_app(reopened)) as client:
            for kind in ('contacts', 'deals', 'tasks'):
                assert client.get('/api/' + kind).status_code == 200
        # Exact whole-table equality includes IDs, notes, actors, and seed marker.
        assert snapshot(reopened) == before
    finally:
        reopened.close()


@pytest.mark.parametrize('demo', [False, True])
def test_cli_requires_explicit_demo_flag(isolated_home, monkeypatch, demo):
    import uvicorn
    launched = []
    def capture(app, **kwargs):
        launched.append(kwargs)
        with TestClient(app) as client:
            assert len(client.get('/api/contacts').json()) == (8 if demo else 0)
    monkeypatch.setattr(uvicorn, 'run', capture)
    monkeypatch.setattr(sys, 'argv', ['hermes-crm'] + (['--demo'] if demo else []))
    web.main()
    assert launched == [{'host': '127.0.0.1', 'port': 8742}]
    crm = CRM()
    try:
        if not demo:
            assert_empty(crm)
        else:
            assert [len(crm.list(k)) for k in ('contacts', 'deals', 'tasks')] == [8, 8, 5]
    finally:
        crm.close()


def test_import_and_tool_registration_never_open_storage(isolated_home, monkeypatch):
    from hermes_crm import plugin
    def forbidden(*args, **kwargs):
        pytest.fail('Import/registration must not open CRM storage')
    monkeypatch.setattr(plugin, 'open_profile_crm', forbidden)
    class Context:
        def register_tool(self, *args, **kwargs):
            pass
    plugin.register(Context())
    # Reload pure runtime and developer generator definitions without invocation.
    importlib.reload(runtime)
    importlib.reload(sys.modules['hermes_crm.demo'])
    assert not (isolated_home / 'standalone').exists()
