from contextlib import contextmanager
from pathlib import Path
import pytest
from hermes_crm.domain import CRMError
from hermes_crm.gmail_bridge_runtime import GmailBridgeRuntime

class CRM:
    profile = 'synthetic'
    def existing_workspace_token(self):
        return 'workspace'

def test_reads_and_disabled_never_construct_transport(tmp_path):
    def forbidden(**kw):
        raise AssertionError('provider')
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: (tmp_path, False, ''), transport_factory=forbidden)
    assert not runtime.setup()['available']
    with pytest.raises(CRMError):
        with runtime.reader('own@example.test'):
            pass

def test_private_temp_lifetime_and_dispatch_guard(tmp_path):
    roots, calls = [], []
    class Transport:
        def __init__(self, **kw):
            roots.append(kw['work_root'])
            assert kw['connection_file'] == tmp_path / 'google_token.json'
            assert kw['work_root'].stat().st_mode & 0o777 == 0o700
            assert kw['guard']() is True
        @contextmanager
        def session(self):
            calls.append('session')
            yield
    (tmp_path / 'gws').write_text('synthetic')
    (tmp_path / 'google_token.json').write_text('synthetic')
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: (tmp_path, True, str(tmp_path / 'gws')),
                                 transport_factory=Transport, reader_factory=lambda t: t)
    with runtime.reader('own@example.test') as (reader, guard):
        assert guard()
        assert roots[0].exists()
    assert not roots[0].exists()
    assert calls == ['session']

def test_selector_changes_but_not_token_metadata(tmp_path):
    selected = [tmp_path, True, '/trusted/gws']
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: tuple(selected))
    (tmp_path / 'google_token.json').write_text('synthetic')
    assert GmailBridgeRuntime(CRM(), selection=lambda: tuple(selected)).selector_fingerprint == runtime.selector_fingerprint
    selected[2] = '/different/gws'
    with pytest.raises(CRMError):
        runtime.host_guard()
    assert GmailBridgeRuntime(CRM(), selection=lambda: tuple(selected)).selector_fingerprint != runtime.selector_fingerprint

def test_transaction_guard_does_not_read_database(tmp_path):
    crm = CRM()
    runtime = GmailBridgeRuntime(crm, selection=lambda: (tmp_path, True, '/trusted/gws'))
    crm.existing_workspace_token = lambda: (_ for _ in ()).throw(AssertionError('nested database read'))
    assert runtime.host_guard()

def test_host_configuration_no_ambient_executable(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from hermes_crm.gmail_bridge_runtime import host_selection
    config = {'plugins': {'entries': {'hermes-crm': {'settings': {'gmail_bridge_enabled': True}}}}}
    monkeypatch.setitem(sys.modules, 'hermes_constants', SimpleNamespace(get_hermes_home=lambda: tmp_path))
    monkeypatch.setitem(sys.modules, 'hermes_cli.config', SimpleNamespace(load_config_readonly=lambda: config))
    monkeypatch.setenv('GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE', '/ambient/secret')
    assert host_selection() == (tmp_path, True, '')
    config['plugins']['entries']['hermes-crm']['settings']['gmail_bridge_gws_path'] = 'gws'
    with pytest.raises(CRMError):
        host_selection()

def test_stat_source_guard_aborts_publish(tmp_path):
    (tmp_path / 'gws').write_text('synthetic')
    (tmp_path / 'google_token.json').write_text('synthetic')
    class Transport:
        def __init__(self, **kw):
            pass
        @contextmanager
        def session(self):
            yield
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: (tmp_path, True, str(tmp_path / 'gws')),
                                 transport_factory=Transport, reader_factory=lambda t: t)
    with runtime.reader('own@example.test'):
        (tmp_path / 'google_token.json').write_text('changed synthetic')
        with pytest.raises(CRMError):
            runtime.host_guard()

def test_owned_temporary_alias_is_canonicalized_for_real_transport(tmp_path, monkeypatch):
    """Model macOS /var -> /private/var using only owned synthetic paths."""
    import sys
    import tempfile
    from hermes_crm.gmail_gws import ExistingWorkspaceGwsTransport
    canonical = tmp_path.resolve()
    temp_parent = canonical / 'private-temp'
    temp_parent.mkdir(mode=0o700)
    alias = canonical / 'temp-alias'
    alias.symlink_to(temp_parent, target_is_directory=True)
    monkeypatch.setattr(tempfile, 'tempdir', str(alias))
    executable = canonical / 'fake-gws'
    executable.write_text(f'#!{sys.executable}\n' + '''import sys, json
if sys.argv[1:] == ['--version']:
 print('gws 0.22.5\\nThis is not an officially supported Google product.')
elif sys.argv[1:4] == ['gmail', 'users', 'getProfile']:
 print(json.dumps({'emailAddress':'own@example.test','historyId':'100'}))
else:
 sys.exit(1)
''')
    executable.chmod(0o700)
    connection = canonical / 'google_token.json'
    connection.write_text('synthetic-not-a-credential')
    connection.chmod(0o600)
    roots = []
    def real_transport(**kwargs):
        roots.append(kwargs['work_root'])
        return ExistingWorkspaceGwsTransport(**kwargs)
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: (canonical, True, str(executable)),
                                 transport_factory=real_transport)
    with runtime.reader('own@example.test') as (reader, guard):
        assert reader.verify_mailbox('own@example.test', guard).checkpoint == '100'
        assert roots[0] == roots[0].resolve(strict=True)
        assert roots[0].parent == temp_parent
        assert roots[0].stat().st_mode & 0o777 == 0o700
    assert runtime.host_guard()  # Publication still validates retained source stamps.
    assert not roots[0].exists()
    assert list(temp_parent.iterdir()) == []

@pytest.mark.parametrize('aliased_source', ['executable', 'connection'])
def test_temp_canonicalization_does_not_relax_supplied_source_paths(tmp_path, monkeypatch, aliased_source):
    from hermes_crm.gmail_reader import GmailReadError
    canonical = tmp_path.resolve()
    source = canonical / 'source'
    source.mkdir(mode=0o700)
    alias = canonical / 'source-alias'
    alias.symlink_to(source, target_is_directory=True)
    executable = source / 'fake-gws'
    executable.write_text('#!/bin/false\n')
    executable.chmod(0o700)
    connection = source / 'google_token.json'
    connection.write_text('synthetic-not-a-credential')
    connection.chmod(0o600)
    home = alias if aliased_source == 'connection' else source
    binary = alias / 'fake-gws' if aliased_source == 'executable' else executable
    monkeypatch.setattr('subprocess.Popen', lambda *a, **kw: pytest.fail('Rejected source dispatched'))
    runtime = GmailBridgeRuntime(CRM(), selection=lambda: (home, True, str(binary)))
    with pytest.raises(GmailReadError, match='gws_invalid_configuration'):
        with runtime.reader('own@example.test'):
            pytest.fail('Aliased source accepted')
