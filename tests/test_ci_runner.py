"""Credential-free CI runner validation; no database or child process is started."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    'hermes_ci_checks', Path(__file__).resolve().parents[1] / 'scripts/ci_checks.py')
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)
BASE = 'postgresql+psycopg://crm_ci:disposable-ci-only@127.0.0.1:5432/crm_ci'


@pytest.mark.parametrize('url', [
    BASE, 'postgresql+psycopg://localhost/test',
    'postgresql+psycopg://user@127.0.0.1:1/test',
    'postgresql+psycopg://user:password@[::1]:65535/test_db',
])
def test_accept_simple_loopback_url(url):
    assert ci.disposable_postgres_url(url) == url


@pytest.mark.parametrize('url', [
    BASE + '?host=remote.example', BASE + '?hostaddr=203.0.113.9',
    BASE + '?service=external', BASE + '?host=127.0.0.1&host=remote.example',
    BASE + '?', BASE + '#fragment', BASE + '#',
    BASE.replace('127.0.0.1', 'remote.example'),
    BASE.replace('5432', '0'), BASE.replace('5432', '65536'),
    BASE.replace('5432', '-1'), BASE.replace('5432', 'text'),
    BASE.replace(':5432', ':'), BASE.replace('127.0.0.1', '[::1'),
    BASE.replace('127.0.0.1', '::1'),
    BASE.replace('127.0.0.1', '127.0.0.1,remote.example'),
    BASE.replace('@127.0.0.1', '@remote.example@127.0.0.1'),
    BASE.replace('@127.0.0.1', '@remote.example\\@127.0.0.1'),
    BASE.replace('127.0.0.1', '%31%32%37.0.0.1'),
    BASE.replace('crm_ci:disposable-ci-only', 'user%40remote:password'),
    BASE.replace('/crm_ci', '/crm_ci%3Fhost=remote.example'),
    BASE.replace('postgresql+psycopg', 'postgresql'),
    BASE.replace('/crm_ci', '/'), BASE + '/other',
    ' ' + BASE, BASE + '\n', BASE.replace('127.0.0.1', '127.0.\n0.1'),
])
def test_reject_ambiguous_or_destination_overriding_url(url):
    with pytest.raises(argparse.ArgumentTypeError):
        ci.disposable_postgres_url(url)


def test_rejected_url_stops_before_any_process_and_redacts_value(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['ci_checks.py', '--suite', 'python',
                                   '--postgres-url', BASE + '?host=remote.example'])
    def unexpected(*args, **kwargs):
        pytest.fail('Invalid URL must not reach child execution')
    monkeypatch.setattr(ci.subprocess, 'run', unexpected)
    with pytest.raises(SystemExit) as exc:
        ci.main()
    assert exc.value.code == 2
    assert 'disposable-ci-only' not in capsys.readouterr().err


@pytest.mark.parametrize('explicit_url', [False, True])
def test_environment_drops_ambient_credentials_and_injection(monkeypatch, explicit_url):
    injected = {'OPENAI_API_KEY': 'synthetic-not-a-key', 'HERMES_SOURCE': '/unused',
                'HERMES_CRM_TEST_POSTGRES_URL': 'ambient-remote-db',
                'HERMES_NATIVE_E2E': '1', 'HERMES_NATIVE_COMMAND_E2E': '1',
                'NODE_OPTIONS': '--unused', 'PYTHONSTARTUP': '/unused',
                'PYTEST_ADDOPTS': '--unused', 'PGHOST': 'remote.example',
                'PGSERVICE': 'remote', 'PGPASSWORD': 'synthetic-not-a-password'}
    for name, value in injected.items():
        monkeypatch.setenv(name, value)
    argv = ['ci_checks.py', '--suite', 'python']
    if explicit_url:
        argv += ['--postgres-url', BASE]
    monkeypatch.setattr(sys, 'argv', argv)
    observed = []
    def capture(command, **kwargs):
        observed.append((command, kwargs['env'].copy()))
        assert Path(kwargs['env']['HOME']).is_dir()
    monkeypatch.setattr(ci.subprocess, 'run', capture)
    assert ci.main() == 0
    assert len(observed) == 1
    command, env = observed[0]
    assert command[:3] == [sys.executable, '-m', 'pytest']
    for name in injected:
        if name == 'HERMES_CRM_TEST_POSTGRES_URL' and explicit_url:
            assert env[name] == BASE
        else:
            assert name not in env
    assert env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'] == '1'
    assert env['CRM_EXECUTION_TEST_PYTHON'] == sys.executable
    assert env['HERMES_CRM_TEST_PYTHON'] == sys.executable
    assert not Path(env['HOME']).exists()


@pytest.mark.parametrize('error, expected', [
    (subprocess.CalledProcessError(7, ['fixture']), 7),
    (subprocess.TimeoutExpired(['fixture'], 600), 1),
])
def test_child_failure_is_not_a_pass(monkeypatch, error, expected):
    monkeypatch.setattr(sys, 'argv', ['ci_checks.py', '--suite', 'python'])
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(ci.subprocess, 'run', fail)
    assert ci.main() == expected


def test_workflow_postgres_publish_is_loopback_only_and_matches_test_url():
    import shlex
    from urllib.parse import urlsplit
    import yaml

    workflow = yaml.safe_load((ci.ROOT / '.github/workflows/test.yml').read_text())
    job = workflow['jobs']['contracts']
    service = job['services']['postgres']
    # A bare "5432:5432" would expose the service on every runner interface.
    # Docker publish syntax must include the host binding, not just a DB client
    # URL that happens to connect through localhost.
    assert service['ports'] == ['127.0.0.1:5432:5432']
    assert not any(option in service.get('options', '') for option in
                   ('--publish', '--network', '-p '))
    python_steps = [step for step in job['steps']
                    if '--postgres-url' in step.get('run', '')]
    assert len(python_steps) == 1
    command = shlex.split(python_steps[0]['run'])
    url = ci.disposable_postgres_url(command[command.index('--postgres-url') + 1])
    connection = urlsplit(url)
    address, host_port, container_port = service['ports'][0].split(':')
    assert connection.hostname == address
    assert connection.port == int(host_port)
    assert container_port == '5432'
    assert connection.path == '/' + service['env']['POSTGRES_DB']
    assert connection.username == service['env']['POSTGRES_USER']
    assert connection.password == service['env']['POSTGRES_PASSWORD']
