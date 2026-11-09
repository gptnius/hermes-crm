"""Synthetic owned fake executable only. Never run gws or access a real connection."""
import json
import os
from pathlib import Path
import sys
from urllib.parse import quote, urlencode

import pytest

from hermes_crm.gmail_gws import (ExistingWorkspaceGwsTransport, HISTORY_FIELDS,
                                 LIST_FIELDS, MAX_OUTPUT)
from hermes_crm.gmail_reader import GmailReadError, HEADER_NAMES, MESSAGE_FIELDS

MAILBOX = 'owner@example.test'
BASE = 'https://gmail.googleapis.com/gmail/v1/users/' + quote(MAILBOX, safe='')


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / 'private'
    root.mkdir(mode=0o700)
    connection = tmp_path / 'google_token.json'
    connection.write_text('synthetic-not-a-credential')
    connection.chmod(0o600)
    executable = tmp_path / 'fake-gws'
    def make(body='', version='0.22.5', guard=lambda: True):
        executable.write_text(f'#!{sys.executable}\nimport sys, os, json, time\n'
                              f'if sys.argv[1:] == ["--version"]:\n print("gws {version}\\nThis is not an officially supported Google product.")\n sys.exit(0)\n'
                              + (body or 'print("{}")\n'))
        executable.chmod(0o700)
        return ExistingWorkspaceGwsTransport(executable=executable, connection_file=connection,
                                             work_root=root, expected_mailbox=MAILBOX, guard=guard)
    return make, root, connection, executable


def url(path='/profile', **params):
    return BASE + path + '?' + urlencode(params or {'fields': 'emailAddress,historyId'}, doseq=True)


def test_constructor_no_dispatch_or_content_read(fixture, monkeypatch):
    make, _, _, _ = fixture
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('constructor dispatched'))
    monkeypatch.setattr(Path, 'read_text', lambda *a, **k: pytest.fail('credential read'))
    make()


def test_isolation_and_exact_params(fixture, monkeypatch):
    make, root, connection, _ = fixture
    monkeypatch.setenv('GOOGLE_WORKSPACE_CLI_TOKEN', 'ambient-secret')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/ambient')
    monkeypatch.setenv('RUST_LOG', 'trace')
    body = '''
assert os.environ['GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND'] == 'file'
assert not set(('GOOGLE_WORKSPACE_CLI_TOKEN','GOOGLE_APPLICATION_CREDENTIALS','RUST_LOG')) & set(os.environ)
assert os.path.isfile('.env') and open('.env').read() == ''
for name in ('HOME','XDG_CONFIG_HOME','XDG_CACHE_HOME','TMPDIR','GOOGLE_WORKSPACE_CLI_CONFIG_DIR'):
 assert os.environ[name].startswith(os.getcwd() + '/')
assert sys.argv[1:4] == ['gmail','users','getProfile']
p = json.loads(sys.argv[sys.argv.index('--params')+1])
assert p == {'userId':'owner@example.test','fields':'emailAddress,historyId'}
open(os.path.join(os.environ['GOOGLE_WORKSPACE_CLI_CONFIG_DIR'], '.encryption_key'), 'w').write('synthetic')
print(json.dumps({'emailAddress':'owner@example.test','historyId':'123'}))
'''
    response = make(body)('GET', url(), timeout=3)
    assert response.status == 200
    assert json.loads(response.body)['historyId'] == '123'
    assert list(root.iterdir()) == []
    assert connection.read_text() == 'synthetic-not-a-credential'


@pytest.mark.parametrize('status', [403, 404, 429, 500])
def test_structured_api_status_without_raw_errors(fixture, status):
    make, root, _, _ = fixture
    t = make(f'print(json.dumps({{"error":{{"code":{status},"message":"SECRET","reason":"opaque"}}}}))\nsys.exit(1)\n')
    response = t('GET', url(), timeout=3)
    assert response.status == status and response.body == b'{}'
    assert not list(root.iterdir())


@pytest.mark.parametrize('code,status,expected', [(0,404,'gws_execution_failed'), (3,404,'gws_execution_failed'),
                                                  (2,401,'gws_auth_unavailable'), (1,200,'gws_execution_failed')])
def test_do_not_trust_status_without_exit_contract(fixture, code, status, expected):
    t = fixture[0](f'print(json.dumps({{"error":{{"code":{status},"message":"SECRET"}}}}))\nsys.exit({code})\n')
    with pytest.raises(GmailReadError, match=expected) as e:
        t('GET', url(), timeout=3)
    assert 'SECRET' not in str(e.value)


@pytest.mark.parametrize('target', [
    'https://evil.test/gmail/v1/users/owner%40example.test/profile?fields=emailAddress',
    'https://gmail.googleapis.com:443/gmail/v1/users/owner%40example.test/profile?fields=emailAddress',
    'https://gmail.googleapis.com/gmail/v1/users/me/profile?fields=emailAddress',
    BASE + '/profile?fields=emailAddress&fields=emailAddress',
    BASE + '/profile?fields=emailAddress#x',
    BASE + '/messages/a?format=full&fields=id',
    BASE + '/messages/a/attachments/b?fields=data',
    BASE + '/messages/send?format=metadata',
    BASE + '/messages?q=anything&maxResults=100&includeSpamTrash=false&fields=' + LIST_FIELDS,
])
def test_rejected_urls_never_spawn(fixture, monkeypatch, target):
    t = fixture[0]()
    monkeypatch.setattr('subprocess.Popen', lambda *a, **k: pytest.fail('invalid request dispatched'))
    with pytest.raises(GmailReadError, match='gws_request_not_allowed'):
        t('GET', target, timeout=3)


@pytest.mark.parametrize('path,params,command', [
    ('/messages', {'q':'after:1000 before:2000 -in:drafts', 'fields':LIST_FIELDS,
                   'maxResults':100, 'includeSpamTrash':'false'}, ['messages','list']),
    ('/history', {'startHistoryId':'123', 'maxResults':100,'fields':HISTORY_FIELDS}, ['history','list']),
    ('/messages/abc123', {'format':'metadata','fields':MESSAGE_FIELDS,
                          'metadataHeaders':HEADER_NAMES}, ['messages','get']),
])
def test_supported_fixed_reads(fixture, path, params, command):
    t = fixture[0](f'assert sys.argv[3:5] == {command!r}\nprint("{{}}")\n')
    assert t('GET', url(path, **params), timeout=3).status == 200


@pytest.mark.parametrize('body,expected', [
    ('time.sleep(10)\n', 'gws_timeout'),
    (f'sys.stdout.write("x" * {MAX_OUTPUT + 100000})\n', 'gws_output_limit'),
    (f'sys.stderr.write("SECRET" * {MAX_OUTPUT})\n', 'gws_output_limit'),
    ('print("not-json SECRET")\n', 'gws_invalid_output'),
    ('print(\'{"id":"a", "id":"b"}\')\n', 'gws_invalid_output'),
])
def test_failure_cleanup(fixture, body, expected):
    t = fixture[0](body)
    with pytest.raises(GmailReadError, match=expected):
        t('GET', url(), timeout=.5)
    assert not list(fixture[1].iterdir())


def test_version_fail_closed(fixture):
    t = fixture[0]('raise RuntimeError("should not dispatch")\n', version='0.22.4')
    with pytest.raises(GmailReadError, match='gws_unsupported_version'):
        t('GET', url(), timeout=3)


def test_rebinding_before_and_during_dispatch(fixture):
    make, root, connection, _ = fixture
    t = make()
    connection.write_text('changed')
    with pytest.raises(GmailReadError, match='gws_connection_changed'):
        t('GET', url(), timeout=3)
    t = make('open(os.environ["GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"], "w").write("fake replacement")\nprint("{}")\n')
    with pytest.raises(GmailReadError, match='gws_connection_changed'):
        t('GET', url(), timeout=3)
    assert not list(root.iterdir())


def test_guard_cancels_running_child(fixture):
    n = [0]
    def guard():
        n[0] += 1
        return n[0] < 14
    t = fixture[0]('time.sleep(10)\n', guard=guard)
    with pytest.raises(GmailReadError, match='cancelled_or_profile_changed'):
        t('GET', url(), timeout=3)
    assert not list(fixture[1].iterdir())


def test_nonprivate_connection_rejected(fixture):
    fixture[2].chmod(0o644)
    with pytest.raises(GmailReadError, match='gws_connection_unavailable'):
        fixture[0]()


def test_symlink_connection_rejected(fixture):
    connection = fixture[2]
    target = connection.with_name('other.json')
    connection.rename(target)
    connection.symlink_to(target)
    with pytest.raises(GmailReadError, match='gws_invalid_configuration'):
        fixture[0]()


def test_timeout_reaps_owned_child(fixture):
    import time
    pid_file = fixture[1].parent / 'synthetic-child.pid'
    t = fixture[0](f'open({str(pid_file)!r}, "w").write(str(os.getpid()))\ntime.sleep(10)\n')
    with pytest.raises(GmailReadError, match='gws_timeout'):
        t('GET', url(), timeout=.5)
    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_query_grammar_only_and_api_version_pin(fixture):
    t = fixture[0]()
    params = {'q':'{from:contact@example.test to:contact@example.test cc:contact@example.test} '
                   'after:1000 before:2000 -in:drafts', 'fields':LIST_FIELDS,
              'includeSpamTrash':'false','maxResults':100}
    args = t._command('GET', url('/messages', **params))
    assert args[-2:] == ['--api-version', 'v1']
    for q in ('after:1000 before:9000000 -in:drafts',
              params['q'].replace('cc:contact@example.test', 'cc:someone@example.test'),
              params['q'] + ' OR in:anywhere'):
        with pytest.raises(GmailReadError, match='gws_request_not_allowed'):
            t._command('GET', url('/messages', **dict(params, q=q)))


def test_session_reuses_only_own_cache_and_checks_version_once(fixture, monkeypatch):
    t = fixture[0]('p=os.path.join(os.environ["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"], "token_cache.json")\n'
                   'n=int(open(p).read()) if os.path.exists(p) else 0\n'
                   'open(p,"w").write(str(n+1))\nprint(json.dumps({"count":n+1,"cwd":os.getcwd()}))\n')
    run = t._run
    versions = []
    def recording(args, *rest):
        if args == ['--version']:
            versions.append(1)
        return run(args, *rest)
    monkeypatch.setattr(t, '_run', recording)
    with t.session() as owned:
        assert owned is t
        a = json.loads(t('GET', url(), timeout=3).body)
        b = json.loads(t('GET', url(), timeout=3).body)
        assert (a['count'], b['count']) == (1, 2)
        assert a['cwd'] == b['cwd']
        assert len(versions) == 1
    assert not list(fixture[1].iterdir())
    with t.session():
        c = json.loads(t('GET', url(), timeout=3).body)
        assert c['count'] == 1 and c['cwd'] != a['cwd']
    assert len(versions) == 2 and not list(fixture[1].iterdir())


def test_session_rejects_nested_and_other_thread(fixture):
    from concurrent.futures import ThreadPoolExecutor
    t = fixture[0]()
    with t.session():
        with pytest.raises(GmailReadError, match='gws_session_in_use'):
            with t.session():
                pytest.fail('nested entered')
        with ThreadPoolExecutor(max_workers=1) as pool:
            other = pool.submit(t, 'GET', url(), timeout=3)
            with pytest.raises(GmailReadError, match='gws_session_in_use'):
                other.result()
        assert t('GET', url(), timeout=3).status == 200
    assert not list(fixture[1].iterdir())


def test_session_exception_cleanup_and_poison(fixture):
    t = fixture[0]('print("not-json")\n')
    with t.session():
        with pytest.raises(GmailReadError, match='gws_invalid_output'):
            t('GET', url(), timeout=3)
        assert not list(fixture[1].iterdir())
        with pytest.raises(GmailReadError, match='gws_session_failed'):
            t('GET', url(), timeout=3)
    with pytest.raises(RuntimeError, match='caller failure'):
        with t.session():
            raise RuntimeError('caller failure')
    assert not list(fixture[1].iterdir())


def test_session_total_deadline_cleans_cache(fixture):
    t = fixture[0]('time.sleep(.3)\nprint("{}")\n')
    with t.session(max_seconds=.15):
        with pytest.raises(GmailReadError, match='gws_timeout'):
            t('GET', url(), timeout=3)
        assert not list(fixture[1].iterdir())


def test_session_checks_binding_before_every_request(fixture):
    t = fixture[0]()
    with pytest.raises(GmailReadError, match='gws_connection_changed'):
        with t.session():
            assert t('GET', url(), timeout=3).status == 200
            fixture[2].write_text('synthetic replacement')
            t('GET', url(), timeout=3)
    assert not list(fixture[1].iterdir())


def test_session_cancel_between_requests_cleans_cache(fixture):
    allow = [True]
    t = fixture[0](guard=lambda: allow[0])
    with pytest.raises(GmailReadError, match='cancelled_or_profile_changed'):
        with t.session():
            assert t('GET', url(), timeout=3).status == 200
            allow[0] = False
            t('GET', url(), timeout=3)
    assert not list(fixture[1].iterdir())


def test_version_output_matches_pinned_official_source():
    # googleworkspace/cli cd3697e, crates/google-workspace-cli/src/main.rs:108-112.
    from hermes_crm.gmail_gws import VERSION_OUTPUT
    assert VERSION_OUTPUT == (b'gws 0.22.5\n'
                              b'This is not an officially supported Google product.')


@pytest.mark.parametrize('ending,allowed', [('\n',True), ('\r\n',True),
                                           ('\nextra',False), (' ',False)])
def test_version_newlines_no_arbitrary_suffix(fixture, monkeypatch, ending, allowed):
    from hermes_crm.gmail_gws import VERSION_OUTPUT
    t = fixture[0]()
    def run(args, *rest):
        if args == ['--version']:
            return 0, VERSION_OUTPUT.replace(b'\n', ending.encode()) + ending.encode()
        return 0, b'{}'
    monkeypatch.setattr(t, '_run', run)
    if allowed:
        assert t('GET', url(), timeout=3).status == 200
    else:
        with pytest.raises(GmailReadError, match='gws_unsupported_version'):
            t('GET', url(), timeout=3)


@pytest.mark.parametrize('finished_at', [1.0, 2.0])
def test_deadline_crossed_during_final_drain_reaps_and_cleans(fixture, monkeypatch, finished_at):
    """EOF can empty the selector before poll observes the expired deadline."""
    import signal
    from hermes_crm import gmail_gws

    clock = [0.0]
    signals = []

    def pipe(data):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, data)
        finally:
            os.close(write_fd)
        return os.fdopen(read_fd, 'rb')

    class FinishedProcess:
        pid = 99999999
        returncode = 0
        reaped = False

        def __init__(self):
            self.stdout = pipe(b'{}')
            self.stderr = pipe(b'')

        def poll(self):
            # This poll happens after both EOFs unregister their pipes.
            clock[0] = finished_at
            return self.returncode

        def wait(self):
            self.reaped = True
            return self.returncode

    process = FinishedProcess()
    monkeypatch.setattr(gmail_gws.subprocess, 'Popen', lambda *a, **kw: process)
    monkeypatch.setattr(gmail_gws.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(gmail_gws.os, 'killpg', lambda pid, sig: signals.append((pid, sig)))
    t = fixture[0]()
    try:
        with pytest.raises(GmailReadError, match='gws_timeout'):
            with t.session():
                state = t._session
                t._run([], state['env'], state['cwd'], deadline=1.0)
        assert process.reaped
        assert process.stdout.closed and process.stderr.closed
        assert signals == [(process.pid, signal.SIGKILL)]
        assert not list(fixture[1].iterdir())
    finally:
        process.stdout.close()
        process.stderr.close()
