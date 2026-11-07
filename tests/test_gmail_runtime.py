"""Offline optional configuration and host manifest tests. No grant/account calls."""
from pathlib import Path
import sys
from types import ModuleType

import pytest
import yaml

from hermes_crm.domain import CRM, CRMError
from hermes_crm import gmail_runtime


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    state = {'home': tmp_path / 'alpha', 'config': {}}
    constants = ModuleType('hermes_constants')
    constants.get_hermes_home = lambda: state['home']
    config = ModuleType('hermes_cli.config')
    config.load_config_readonly = lambda: state['config']
    monkeypatch.setitem(sys.modules, 'hermes_constants', constants)
    monkeypatch.setitem(sys.modules, 'hermes_cli.config', config)
    crm = CRM(f'sqlite:///{tmp_path}/crm.db', profile='alpha')
    yield state, crm
    crm.close()


def set_enabled(state, value):
    state['config'] = {'plugins': {'entries': {'hermes-crm': {'settings': {'gmail_history_enabled': value}}}}}


def test_disabled_default_never_constructs_reader(runtime, monkeypatch):
    state, crm = runtime
    reader = ModuleType('hermes_crm.gmail_reader')
    def forbidden(): raise AssertionError('No reader while disabled')
    reader.GmailReader = forbidden
    monkeypatch.setitem(sys.modules, 'hermes_crm.gmail_reader', reader)
    result = gmail_runtime.gmail_runtime(crm)
    assert result['enabled'] is False and result['reader'] is None
    with pytest.raises(CRMError, match='disabled'):
        result['guard']()


@pytest.mark.parametrize('value', ['true', 'false', 1, 0, None, [], {}])
def test_enabled_is_not_truthiness(runtime, value):
    state, crm = runtime
    set_enabled(state, value)
    with pytest.raises(CRMError, match='boolean'):
        gmail_runtime.gmail_runtime(crm)


def test_enabled_only_constructs_reader_and_guard_rechecks_profile(runtime, monkeypatch):
    state, crm = runtime
    set_enabled(state, True)
    reader = ModuleType('hermes_crm.gmail_reader')
    constructions = []
    reader.GmailReader = lambda: constructions.append('constructed') or object()
    monkeypatch.setitem(sys.modules, 'hermes_crm.gmail_reader', reader)
    result = gmail_runtime.gmail_runtime(crm)
    assert result['enabled'] and constructions == ['constructed']
    result['guard']()
    state['home'] = state['home'].parent / 'beta'
    with pytest.raises(CRMError, match='workspace changed'):
        result['guard']()
    state['home'] = state['home'].parent / 'alpha'
    set_enabled(state, False)
    with pytest.raises(CRMError, match='disabled'):
        result['guard']()


def test_settings_override_legacy_without_fallback(runtime):
    state, crm = runtime
    state['config'] = {'plugins': {'entries': {'hermes-crm': {
        'settings': {'gmail_history_enabled': False}, 'config': {'gmail_history_enabled': True}}}}}
    assert gmail_runtime.gmail_runtime(crm)['enabled'] is False
    state['config'] = {'plugins': []}
    with pytest.raises(CRMError, match='invalid'):
        gmail_runtime.gmail_runtime(crm)


def test_optional_manifest_does_not_change_agent_tools():
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / 'plugin.yaml').read_text())
    assert not manifest.get('requires_env') and not manifest.get('requires_auth')
    assert manifest['config_schema']['gmail_history_enabled']['default'] is False
    oauth, = manifest['oauth']
    assert oauth['id'] == 'gmail-history-readonly'
    assert oauth['scopes'] == ['https://www.googleapis.com/auth/gmail.readonly', 'openid',
                               'https://www.googleapis.com/auth/userinfo.email']
    assert set(oauth['hosts']) == {'gmail.googleapis.com', 'openidconnect.googleapis.com'}
    names = {entry['name'] for entry in manifest['optional_env']}
    assert names == {oauth['client_id_env'], oauth['client_secret_env'],
                     'HERMES_CRM_NOTES_KEYS', 'HERMES_CRM_BACKUP_KEYS'}
    assert all(entry.get('secret') is True for entry in manifest['optional_env'])
    for field in ('gmail_client_id', 'gmail_client_secret'):
        assert manifest['config_schema'][field]['type'] == 'secret'
        assert manifest['config_schema'][field]['env'] in names
    assert not any('email' in tool or 'gmail' in tool for tool in manifest['provides_tools'])
    assert not any('gmail_history' in (root / 'hermes_crm' / f).read_text()
                   for f in ('domain.py', 'plugin.py', 'native_work.py'))


def test_actual_pinned_host_oauth_declaration_parser(tmp_path):
    import os
    import subprocess
    source = os.environ.get('HERMES_SOURCE')
    if not source:
        pytest.skip('Set HERMES_SOURCE to inspect the pinned host parser offline')
    manifest = Path(__file__).resolve().parents[1] / 'plugin.yaml'
    home = tmp_path / 'user'
    home.mkdir()
    env = {'HOME': str(home), 'HERMES_HOME': str(home / '.hermes'),
           'HERMES_ENABLE_PROJECT_PLUGINS': '0',
           'HERMES_BUNDLED_PLUGINS': str(home / 'no-bundled-plugins'),
           'PYTHONPATH': str(Path(source).resolve()), 'PYTHONDONTWRITEBYTECODE': '1'}
    code = r'''
import pathlib, sys, yaml
# Actual host parsing only. No socket, child application or credential-store I/O.
def audit(event, args):
    if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system'):
        raise AssertionError('External operations forbidden during manifest validation')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        name = pathlib.Path(args[0]).name
        if name in ('auth.json', 'google_token.json', '.env'):
            raise AssertionError('Credential/config secret reads forbidden')
sys.addaudithook(audit)
from hermes_cli.plugin_oauth import parse_oauth_clients, oauth_admission_problems
path = pathlib.Path(sys.argv[1])
manifest = yaml.safe_load(path.read_text())
clients, problems = parse_oauth_clients(manifest)
assert problems == [] and len(clients) == 1
assert clients[0].id == 'gmail-history-readonly'
assert set(clients[0].hosts) == {'gmail.googleapis.com', 'openidconnect.googleapis.com'}
assert oauth_admission_problems(manifest, path.parent) == []
print('PASS actual OAuth manifest parser and admission checks; no account operations')
'''
    result = subprocess.run([sys.executable, '-P', '-c', code, str(manifest)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS actual OAuth manifest parser' in result.stdout
