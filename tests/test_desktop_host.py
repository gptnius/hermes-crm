"""Opt-in native API integration against the actual, pinned Hermes checkout.

No Desktop launch, model execution, cron writes, or user profiles are involved.
HERMES_SOURCE must point to an official Hermes source checkout with its imports
available to this interpreter. The complete server runs only as an ASGI test app.
"""
import json
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_official_dashboard_discovery_auth_crud_tools_and_profiles(tmp_path, isolation):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    repo = Path(__file__).resolve().parents[1]
    original_home = Path.home().resolve()
    assert original_home != Path(original_home.anchor)
    assert all(not path.is_relative_to(original_home) for path in (
        tmp_path.resolve(), source, Path(sys.executable).resolve(),
        Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()))
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert revision == '2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'
    user_home = tmp_path / 'user'
    home = user_home / '.hermes'
    package = home / 'plugins' / 'hermes-crm'
    shutil.copytree(repo, package, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.pytest_cache', 'node_modules', 'build', '*.egg-info', 'artifacts',
        '.env', '.env.*', '.venv', '.codex', '.agents', '*.db'))
    config = f'plugins:\n  isolation: {isolation}\n  enabled: [hermes-crm]\n  entries:\n    hermes-crm:\n      settings:\n        backend: sqlite\n'
    (home / 'config.yaml').write_text(config)
    other = home / 'profiles' / 'crm-test-other'
    other.mkdir(parents=True)
    (other / 'config.yaml').write_text(config)
    # Construct a new environment rather than filtering inherited credentials.
    # The same safety guard is required in the actual hosted-profile IPC child.
    for profile_home in (home, other):
        scratch = profile_home / 'cache/scratch'
        scratch.mkdir(parents=True)
        (scratch / '.last_prune').touch()
    guard = tmp_path / 'guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text(SAFETY_GUARD)
    # Supply only the installed distribution needed from user-site. The guarded
    # child must never inspect the original HOME or inherit its credentials.
    dependencies = tmp_path / 'dependencies'
    dependencies.mkdir()
    distribution = importlib.metadata.distribution('sqlalchemy')
    for relative in distribution.files or ():
        if relative.parts[0] != 'sqlalchemy' and not relative.parts[0].endswith('.dist-info'):
            continue
        source_file = distribution.locate_file(relative)
        if source_file.is_file():
            target = dependencies / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target)
    env = {
        'HOME': str(user_home), 'USERPROFILE': str(user_home), 'HERMES_HOME': str(home),
        'HERMES_ENABLE_PROJECT_PLUGINS': '0',
        'HERMES_BUNDLED_PLUGINS': str(tmp_path / 'no-bundled-plugins'),
        'PYTHONPATH': os.pathsep.join((str(guard), str(source), str(dependencies))),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'CRM_DESKTOP_TEST_ROOT': str(tmp_path), 'CRM_DESKTOP_TEST_SOURCE': str(source),
        'CRM_DESKTOP_TEST_FORBIDDEN_HOME': str(original_home),
    }
    # Python otherwise logs and swallows sitecustomize exceptions. Verify the
    # exact wrapper fails closed for both the main runner and real IPC child.
    invalid_guard = tmp_path / 'invalid-guard'
    invalid_guard.mkdir()
    setup_line = "root = Path(os.environ['CRM_DESKTOP_TEST_ROOT']).resolve()"
    assert setup_line in SAFETY_GUARD
    (invalid_guard / 'sitecustomize.py').write_text(SAFETY_GUARD.replace(
        setup_line, "raise RuntimeError('INTENTIONAL_GUARD_SETUP_FAILURE')"))
    invalid_env = dict(env, PYTHONPATH=os.pathsep.join((str(invalid_guard), str(source))))
    invalid = subprocess.run([sys.executable, '-P', '-c', "raise RuntimeError('UNGUARDED_FIXTURE_RAN')"],
        cwd=tmp_path, env=invalid_env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert invalid.returncode == 97 and 'UNGUARDED_FIXTURE_RAN' not in invalid.stderr, invalid
    invalid_child = subprocess.run([sys.executable, '-P', '-m', 'hermes_cli.plugin_host_child'],
        cwd=tmp_path, env=invalid_env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert invalid_child.returncode == 97, invalid_child
    assert not list(tmp_path.glob('guard-ready-*.json'))
    result = subprocess.run([sys.executable, '-P', '-c', HOST_CHECK], cwd=tmp_path,
                            env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS native host' in result.stdout
    assert not list(home.rglob('jobs.json')), 'Validation must never create cron jobs'
    assert not (tmp_path / 'forbidden-action.log').exists(), result.stdout + result.stderr
    guard_loads = list(tmp_path.glob('guard-ready-*.json'))
    assert len(guard_loads) >= 2, 'Secondary-profile IPC child must inherit guard'
    assert all(json.loads(path.read_text())['hook_ready'] is True for path in guard_loads)


SAFETY_GUARD = r'''
import importlib.abc
import json
import os
from pathlib import Path
import socket
import sys

root = Path(os.environ['CRM_DESKTOP_TEST_ROOT']).resolve()
forbidden_home = Path(os.environ['CRM_DESKTOP_TEST_FORBIDDEN_HOME']).resolve()
assert forbidden_home.is_absolute() and forbidden_home != Path(forbidden_home.anchor)
assert all(not path.is_relative_to(forbidden_home) for path in (
    root, Path(os.environ['CRM_DESKTOP_TEST_SOURCE']).resolve(), Path(sys.executable).resolve(),
    Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()))
homes = {root / 'user/.hermes', root / 'user/.hermes/profiles/crm-test-other'}
assert Path(os.environ['HOME']).resolve() == root / 'user'
assert Path(os.environ['HERMES_HOME']).resolve() in homes
assert not any(key.endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD')) for key in os.environ)

def forbidden(action):
    with (root / 'forbidden-action.log').open('a') as handle:
        handle.write(str(action) + '\n')
    raise AssertionError('Forbidden in read-only Desktop host validation: ' + str(action))

# Bounded exception for the pinned host's read-only CalVer identity probe.
# No shell, arbitrary git show, alternate checkout, or unpinned caller is allowed.
def desktop_version_probe(executable, argv, cwd):
    if (executable != 'git' or list(argv) != ['git', 'describe', '--tags', '--long',
            '--match', 'v2[0-9][0-9][0-9].*', 'HEAD'] or not cwd):
        return False
    source = Path(os.environ['CRM_DESKTOP_TEST_SOURCE']).resolve()
    if Path(cwd).resolve() != source:
        return False
    version_file = source / 'hermes_cli/version_info.py'
    frame = sys._getframe(1)
    try:
        while frame is not None:
            if (frame.f_code.co_name == '_run_git'
                    and Path(frame.f_code.co_filename).resolve() == version_file):
                import hashlib
                try:
                    return hashlib.sha256(version_file.read_bytes()).hexdigest() == (
                        'c9063a4a9b0ae7dd7027bf58955f3890b0ac671caa9be5fbd3f5bce02bcea0da')
                except OSError:
                    return False
            frame = frame.f_back
        return False
    finally:
        del frame

def audit(event, args):
    if event in {'open', 'os.listdir', 'os.scandir'} and args and isinstance(args[0], (str, bytes)):
        if Path(os.fsdecode(args[0])).resolve().is_relative_to(forbidden_home):
            forbidden('original HOME file access')
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname',
                 'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.sendto', 'socket.sendmsg',
                 'os.system', 'os.posix_spawn', 'os.exec', 'os.fork'}:
        forbidden(event)
    if event == 'subprocess.Popen':
        executable, argv, cwd, env = args
        if desktop_version_probe(executable, argv, cwd):
            return
        import re
        git_read = (list(argv) in [
            ['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', '--short=7', 'HEAD'],
            ['git', 'branch', '--show-current'], ['git', 'log', '-1', '--format=%ct', 'HEAD'],
            ['git', '--no-optional-locks', 'status', '--porcelain', '-uno'],
            ['git', 'tag', '--merged', 'HEAD', '--list', 'v[0-9]*'],
        ] or (len(argv) == 4 and list(argv[:3]) == ['git', 'rev-list', '--count']
              and re.fullmatch(r'v[0-9.]+\.\.HEAD', argv[3])))
        if git_read and Path(cwd).resolve() == Path(os.environ['CRM_DESKTOP_TEST_SOURCE']).resolve():
            return
        if list(argv) != [sys.executable, '-m', 'hermes_cli.plugin_host_child'] or Path(cwd).resolve() not in homes:
            forbidden('process launch: ' + repr(argv))
        if not env or str(root / 'guard') not in env.get('PYTHONPATH', '').split(os.pathsep):
            forbidden('plugin child missing safety guard')

sys.addaudithook(audit)

class NoAgentImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'run_agent': forbidden('agent/model launch import')

sys.meta_path.insert(0, NoAgentImport())
(root / ('guard-ready-' + str(os.getpid()) + '.json')).write_text(json.dumps({'pid': os.getpid(), 'hook_ready': True}))
'''
# Inherited unchanged by the real plugin child; broken setup terminates before
# the app can import or execute, rather than becoming a sitecustomize warning.
SAFETY_GUARD = ('import os\ntry:\n' + textwrap.indent(SAFETY_GUARD, '    ')
                + '\nexcept BaseException:\n    os._exit(97)\n')


HOST_CHECK = r'''
import json
import os
from pathlib import Path
import socket
from unittest.mock import patch


root = Path(os.environ['CRM_DESKTOP_TEST_ROOT'])
guard_ready = json.loads((root / ('guard-ready-' + str(os.getpid()) + '.json')).read_text())
assert guard_ready == {'pid': os.getpid(), 'hook_ready': True}


def deny_network(*args, **kwargs):
    raise AssertionError('External network is forbidden in native host validation')


with patch.object(socket, 'create_connection', deny_network), \
     patch.object(socket.socket, 'connect', deny_network), \
     patch.object(socket.socket, 'connect_ex', deny_network):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_cli import web_server as host
    from hermes_cli.web_server_dashboard import _discover_dashboard_plugins, _mount_one_plugin_api
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from hermes_constants import get_hermes_home

    home = Path(os.environ['HERMES_HOME'])
    from hermes_cli.plugins_cmd_inspect import detect_components
    assert detect_components(home / 'plugins/hermes-crm', 'hermes-crm') == {
        'agent': True, 'desktop': True, 'agent_name': 'hermes-crm'}
    discovered = _discover_dashboard_plugins()
    plugin = next(p for p in discovered if p['name'] == 'hermes-crm')
    assert plugin['source'] == 'user' and plugin['_api_file'] == 'plugin_api.py'
    assert not _mount_one_plugin_api(FastAPI(), plugin, set(), set())
    assert not _mount_one_plugin_api(FastAPI(), plugin, {'hermes-crm'}, {'hermes-crm'})
    project = {**plugin, 'source': 'project'}
    assert not _mount_one_plugin_api(FastAPI(), project, {'hermes-crm'}, set())
    assert _mount_one_plugin_api(FastAPI(), plugin, {'hermes-crm'}, set())

    manager = get_plugin_manager()
    manager.discover_and_load()
    assert 'crm_contact_get' in manager._plugin_tool_names, manager._plugins
    assert 'crm_contact_report' in manager._plugin_tool_names, manager._plugins

    def raw_tool(name, args):
        entry = registry.get_entry(name, scope=manager.scope_key)
        assert entry is not None, name
        return json.loads(entry.handler(args))

    def tool(name, args):
        response = raw_tool(name, args)
        assert response['ok'], response
        return response['data']

    client = TestClient(host.app, base_url='http://localhost')
    prefix = '/api/plugins/hermes-crm'
    headers = {'Authorization': f'Bearer {host._SESSION_TOKEN}'}
    def request(method, path, expected=200, **kwargs):
        response = client.request(method, prefix + path, headers=headers, **kwargs)
        assert response.status_code == expected, (method, path, response.status_code, response.text)
        return response.json()

    def assert_contact_report_projection(rest, agent):
        # Base tools intentionally minimize ordinary record fields. REST retains
        # the full human view; compare exact allowed values and reject leakage.
        fields = {'id', 'version', 'created_at', 'updated_at', 'name', 'email',
                  'company', 'title', 'lifecycle', 'deal_count',
                  'open_followup_count', 'overdue_followup_count',
                  'next_followup_at', 'deal_stages'}
        expected = {key: rest[key] for key in ('total', 'limit', 'offset')}
        expected['items'] = [{key: value for key, value in row.items() if key in fields}
                             for row in rest['items']]
        assert agent == expected, (agent, expected)

    assert client.get(prefix + '/meta').status_code == 401
    assert client.get(prefix + '/work', params={'workspace_token': 'not-authentication'}).status_code == 401
    assert client.get(prefix + '/work/not-an-assignment', params={'workspace_token': 'not-authentication'}).status_code == 401
    for path in ('/reports/work', '/reports/coverage'):
        assert client.get(prefix + path, params={'workspace_token': 'not-authentication'}).status_code == 401
    assert client.post(prefix + '/contacts', json={}).status_code == 401
    assert client.post(prefix + '/work', json={'workspace_token': 'not-authentication'}).status_code == 401
    meta = request('GET', '/meta')
    token = meta['workspace_token']
    assert meta['native_desktop'] is True
    created = request('POST', '/contacts', 201, json={
        'workspace_token': token, 'idempotency_key': 'native-host-contact',
        'data': {'name': 'Synthetic Native Contact', 'email': 'synthetic@example.invalid'}})
    contact_id = created['id']
    # Optional Gmail surfaces share real host auth/profile routing but default
    # off. These checks never resolve credentials or invoke the provider helper.
    for email_path in ('/email/status', '/email/setup', '/email/contacts/' + contact_id):
        assert client.get(prefix + email_path, params={'workspace_token': token}).status_code == 401
        request('GET', email_path, 409, params={'workspace_token': 'stale-profile-token'})
        local = request('GET', email_path, params={'workspace_token': token})
        if email_path.endswith('status'):
            assert local['enabled'] is False and local['connected'] is False and local['revision'] == 0
    assert request('GET', '/email/contacts/' + contact_id, params={'workspace_token': token})['items'] == []
    request('POST', '/email/verify', 503, json={'workspace_token': token, 'operation_id': '11111111-1111-4111-8111-111111111111',
        'expected_revision': 0, 'mailbox': 'own@example.test', 'consent': True})
    bridge_paths = ('/email-bridge/status', '/email-bridge/setup',
                    '/email-bridge/contacts/' + contact_id, '/email-bridge/unresolved',
                    '/email-bridge/operations/missing')
    for bridge_path in bridge_paths:
        assert client.get(prefix + bridge_path, params={'workspace_token': token}).status_code == 401
        request('GET', bridge_path, 409, params={'workspace_token': 'stale-profile-token'})
        request('GET', bridge_path, params={'workspace_token': token})
    bridge_status = request('GET', '/email-bridge/status', params={'workspace_token': token})
    assert bridge_status['enabled'] is False and bridge_status['polling_enabled'] is False
    assert bridge_status['revision'] == 0 and bridge_status['account_namespace'] is None
    assert bridge_status['runtime']['available'] is False
    assert request('GET', '/email-bridge/contacts/' + contact_id, params={'workspace_token': token})['items'] == []
    bridge_verify = dict(workspace_token=token, operation_key='host-disabled-verify',
        expected_revision=0, own_mailbox='own@example.test', consent=True)
    assert client.post(prefix + '/email-bridge/verify', json=bridge_verify).status_code == 401
    request('POST', '/email-bridge/verify', 409, json=bridge_verify)
    request('POST', '/email-bridge/sync', 409, json=dict(workspace_token=token,
        operation_key='host-disabled-sync', expected_revision=0, consent=True))
    assert request('GET', '/email-bridge/status', params={'workspace_token': token}) == bridge_status
    assert tool('crm_contact_get', {'id': contact_id})['name'] == 'Synthetic Native Contact'
    updated = tool('crm_contact_update', {'id': contact_id, 'version': created['version'], 'company': 'Synthetic LLC'})
    detail = request('GET', '/contacts/' + contact_id)
    assert detail['contact']['company'] == 'Synthetic LLC', detail
    request('PATCH', '/contacts/' + contact_id, 409, json={
        'workspace_token': token, 'data': {'version': created['version'], 'name': 'Stale'}})
    request('POST', '/contacts', 409, json={
        'workspace_token': 'stale-profile-token', 'data': {'name': 'Must Not Exist'}})
    deal = request('POST', '/deals', 201, json={'workspace_token': token, 'data': {
        'title': 'Synthetic Deal', 'contact_id': contact_id, 'value': 123400, 'stage': 'proposal'}})
    assert tool('crm_deal_get', {'id': deal['id']})['value'] == 123400
    task = tool('crm_task_create', {'title': 'Synthetic follow-up', 'contact_id': contact_id, 'due_at': '2099-01-01T00:00:00Z'})
    task_updated = request('PATCH', '/tasks/' + task['id'], json={
        'workspace_token': token, 'data': {'version': task['version'], 'status': 'done'}})
    assert tool('crm_task_get', {'id': task['id']})['status'] == 'done'
    # Intent saving uses authenticated REST without a borrowed tool context.
    # The registered tool must recover the same workspace/profile-bound intent.
    work_task = tool('crm_task_create', {
        'title': 'Synthetic native-work analysis', 'due_at': '2099-01-02T00:00:00Z'})
    create_schema = registry.get_entry('crm_work_create', scope=manager.scope_key).schema['parameters']
    version_schema = create_schema['properties']['expected_task_version']
    assert version_schema['type'] == 'integer' and version_schema['minimum'] == 1
    assert 'default' not in version_schema
    assert 'expected_task_version' not in create_schema['required']
    work_request = {
        'task_id': work_task['id'], 'expected_task_version': work_task['version'], 'human_owner': 'Synthetic Native Owner',
        'prompt': 'Summarize this existing CRM task using internal records only.',
        'success_criteria': 'One concise internal summary for human review.',
        'run_at': '2099-01-01T00:00:00.123456Z', 'idempotency_key': 'native-host-work-intent'}
    save_body = {**work_request, 'workspace_token': token}
    work = request('POST', '/work', 201, json=save_body)
    assert work['payload']['run_at'] == '2099-01-01T00:00:00.123456+00:00'
    assert tool('crm_work_create', work_request) == work
    assert request('POST', '/work', 201, json=save_body) == work
    request('POST', '/work', 409, json={**save_body, 'workspace_token': 'stale-profile-token'})
    for extra in ({'approved': True}, {'profile': 'foreign'}, {'backend': 'sqlite'}):
        request('POST', '/work', 422, json={**save_body, **extra})
    request('POST', '/work', 409, json={**save_body, 'expected_task_version': 2, 'idempotency_key': 'stale-rest'})
    assert work['payload']['expected_task_version'] == work_task['version']
    for bad_version in (None, True, '1', 1.0, 0):
        request('POST', '/work', 422, json={**save_body, 'expected_task_version': bad_version})
        rejected = raw_tool('crm_work_create', {**work_request, 'expected_task_version': bad_version})
        assert not rejected['ok'] and rejected['status'] == 422, rejected
    stale = raw_tool('crm_work_create', {**work_request, 'expected_task_version': 2, 'idempotency_key': 'stale'})
    assert not stale['ok'] and stale['status'] == 409, stale
    assert work['state'] == 'pending' and work['job_id'] is None, work
    assert work['workspace'] == token and work['profile'] == meta['profile'], (work, meta)
    assert request('GET', '/work', params={'workspace_token': token}) == [work]
    assert request('GET', '/work/' + work['id'], params={'workspace_token': token}) == work
    assert request('GET', '/work', params={'workspace_token': token, 'task_id': work_task['id']}) == [work]
    assert tool('crm_work_get', {'assignment_id': work['id']}) == work
    assert tool('crm_work_list', {'task_id': work_task['id']}) == [work]
    for work_path in ('/work', '/work/' + work['id'], '/reports/work', '/reports/coverage'):
        request('GET', work_path, 422)
        request('GET', work_path, 409, params={'workspace_token': 'stale-profile-token'})
    page = request('GET', '/reports/work', params={'workspace_token': token, 'task_id': work_task['id'], 'limit': 1})
    assert page['total'] == 1 and page['items'] == [work] and page['observed_at']
    assert request('GET', '/reports/work', params={'workspace_token': token, 'offset': 1})['items'] == []
    queue = request('GET', '/reports/coverage', params={'workspace_token': token, 'status': 'agent_not_scheduled'})
    assert queue['total'] == 1 and queue['total_unit'] == 'evidence_items'
    assert queue['workspace_token'] == token and queue['profile'] == meta['profile']
    row = queue['items'][0]
    assert row['task']['id'] == work_task['id'] and row['assignment']['id'] == work['id']
    assert row['assignment']['source_task_current'] and row['assignment']['latest_report'] is None
    assert 'intent_not_scheduled' in row['risk_flags']
    for path in ('/reports/work', '/reports/coverage'):
        request('GET', path, 400, params={'workspace_token': token, 'unknown_filter': 'x'})
        assert client.post(prefix + path, headers=headers, json={'workspace_token': token}).status_code in {404, 405}
    request('GET', '/reports/coverage', 400, params={'workspace_token': token, 'status': 'green'})
    assert not list(home.rglob('jobs.json')), 'Saving intent and reading history must not schedule'
    assert request('GET', '/overview')
    # The registered agent report and REST report share filters and aggregates.
    report_filters = {'stage': 'proposal', 'contact_type': 'lead', 'followup': 'missing',
                      'limit': 1, 'offset': 0}
    report = request('GET', '/reports/contacts',
                     params={**report_filters, 'workspace_token': token})
    assert_contact_report_projection(report, tool('crm_contact_report', report_filters))
    assert report['total'] == 1 and report['items'][0]['id'] == contact_id, report
    assert report['items'][0]['deal_stages'] == ['proposal']
    from hermes_cli.web_server_profiles import serving_profile_name
    for profile_alias in dict.fromkeys(('current', '', serving_profile_name())):
        assert request('GET', '/email-bridge/status',
            params={'workspace_token': token, 'profile': profile_alias}) == bridge_status
        assert request('GET', '/email-bridge/contacts/' + contact_id,
            params={'workspace_token': token, 'profile': profile_alias})['items'] == []
        assert request('GET', '/reports/contacts',
            params={**report_filters, 'workspace_token': token, 'profile': profile_alias}) == report
        assert request('GET', '/contacts',
            params={'workspace_token': token, 'stage': 'proposal', 'profile': profile_alias})[0]['id'] == contact_id
        assert request('GET', '/work',
            params={'workspace_token': token, 'profile': profile_alias}) == [work]
        assert request('GET', '/work/' + work['id'],
            params={'workspace_token': token, 'profile': profile_alias}) == work
        assert request('GET', '/reports/work', params={'workspace_token': token, 'profile': profile_alias})['items'] == [work]
        assert request('GET', '/reports/coverage', params={'workspace_token': token, 'profile': profile_alias,
            'status': 'agent_not_scheduled'})['items'][0]['assignment']['id'] == work['id']
    request('GET', '/reports/contacts', 409,
            params={**report_filters, 'workspace_token': 'stale-profile-token'})
    # Original approved version replays exactly after the source is completed;
    # changed approval with the same key conflicts, and no replacement is saved.
    tool('crm_task_update', {'id': work_task['id'], 'version': work_task['version'], 'status': 'done'})
    replay = request('POST', '/work', 201, json=save_body)
    assert tool('crm_work_create', work_request) == replay
    assert replay['id'] == work['id'] and replay['payload'] == work['payload']
    assert not replay['source_task_current'] and replay['business_task_completed']
    assert len(replay['events']) == 1
    work = replay
    changed = raw_tool('crm_work_create', {**work_request, 'expected_task_version': 2})
    assert not changed['ok'] and changed['status'] == 409, changed
    request('POST', '/work', 409, json={**save_body, 'expected_task_version': 2})
    request('POST', '/work', 409, json={**save_body, 'expected_task_version': 2, 'idempotency_key': 'done-source'})
    review = request('GET', '/reports/coverage', params={'workspace_token': token, 'status': 'needs_scheduling_review'})
    assert review['total'] == 1 and review['items'][0]['task']['status'] == 'done'
    assert review['items'][0]['assignment']['id'] == work['id']


    # Flexible reports and authored claims use the same real host admission,
    # profile scope and registry as ordinary CRM, without scheduler authority.
    import uuid
    for path in ('/analytics/catalog', '/analytics/reports', '/analytics/dashboard', '/interactions'):
        assert client.get(prefix + path, params={'workspace_token': token}).status_code == 401
        request('GET', path, 409, params={'workspace_token': 'stale', **({'contact_id': contact_id} if path == '/interactions' else {})})
    assert client.post(prefix + '/analytics/reports', json={}).status_code == 401
    assert client.post(prefix + '/interactions', json={}).status_code == 401
    assert request('GET', '/analytics/catalog', params={'workspace_token': token}) == tool('crm_report_catalog', {})
    definition = {'entity': 'contacts', 'columns': ['id', 'name']}
    save_report = {'title': 'Synthetic saved report', 'definition': definition, 'idempotency_key': 'host-report'}
    saved = request('POST', '/analytics/reports', 201, json={**save_report, 'workspace_token': token})
    assert tool('crm_report_create', save_report) == saved
    report_path = '/analytics/reports/' + saved['id']
    assert request('GET', report_path, params={'workspace_token': token}) == tool('crm_report_get', {'report_id': saved['id']})
    run_args = {'report_id': saved['id'], 'expected_version': 1, 'evaluated_at': '2026-01-01T00:00:00Z'}
    live = tool('crm_saved_report_run', run_args)
    rest_live = request('POST', report_path + '/run', json={'workspace_token': token, 'expected_version': 1, 'evaluated_at': run_args['evaluated_at']})
    assert {k: v for k, v in live.items() if k != 'observed_at'} == {k: v for k, v in rest_live.items() if k != 'observed_at'}
    cards = [{'id': str(uuid.uuid4()), 'report_id': saved['id'], 'report_version': 1, 'visualization': 'table'}]
    dash_args = {'cards': cards, 'expected_version': 0, 'idempotency_key': 'host-dashboard'}
    dashboard = tool('crm_dashboard_save', dash_args)
    assert request('PUT', '/analytics/dashboard', json={**dash_args, 'workspace_token': token}) == dashboard
    assert request('GET', '/analytics/dashboard', params={'workspace_token': token}) == tool('crm_dashboard_get', {})
    tool('crm_report_update', {**save_report, 'report_id': saved['id'], 'expected_version': 1, 'idempotency_key': 'host-edit', 'title': 'Changed'})
    request('GET', report_path, 409, params={'workspace_token': token, 'version': 1})
    assert raw_tool('crm_report_get', {'report_id': saved['id'], 'version': 1})['status'] == 409
    request('POST', report_path + '/run', 409, json={'workspace_token': token, 'expected_version': 1})
    assert raw_tool('crm_saved_report_run', run_args)['status'] == 409
    assert tool('crm_dashboard_get', {})['cards'][0]['reference_status'] == 'outdated'
    tool('crm_report_archive', {'report_id': saved['id'], 'expected_version': 2, 'idempotency_key': 'host-archive'})
    request('POST', report_path + '/run', 409, json={'workspace_token': token, 'expected_version': 3})
    assert raw_tool('crm_saved_report_run', {**run_args, 'expected_version': 3})['status'] == 409
    log_data = {'contact_id': contact_id, 'happened_at': '2020-01-01T12:00:00Z', 'kind': 'call', 'summary': 'Synthetic self-reported discussion'}
    log_body = {'workspace_token': token, 'data': log_data, 'expected_contact_version': updated['version'], 'idempotency_key': 'host-log'}
    logged = request('POST', '/interactions', 201, json=log_body)
    assert logged['actor'] == 'desktop' and logged['provenance'] == 'self_reported'
    assert request('POST', '/interactions', 201, json=log_body) == logged
    assert request('GET', '/interactions', params={'workspace_token': token, 'contact_id': contact_id}) == tool('crm_contact_log_list', {'contact_id': contact_id})
    request('POST', '/interactions', 422, json={**log_body, 'data': {**log_data, 'actor': 'forged'}})
    voided = tool('crm_contact_log_void', {'interaction_id': logged['id'], 'expected_version': 1, 'reason': 'Synthetic correction', 'idempotency_key': 'host-void'})
    assert voided['actor'] == 'desktop' and voided['void_actor'] == 'hermes'
    assert voided['summary'] == logged['summary']
    assert request('GET', '/interactions', params={'workspace_token': token, 'contact_id': contact_id})['items'] == []
    assert request('GET', '/interactions', params={'workspace_token': token, 'contact_id': contact_id, 'include_voided': True})['items'] == [voided]
    assert not list(home.rglob('jobs.json'))

    # Official request middleware must apply consent again after routes are mounted.
    config_path = home / 'config.yaml'
    enabled_config = config_path.read_text()
    config_path.write_text('plugins:\n  enabled: [hermes-crm]\n  disabled: [hermes-crm]\n')
    request('GET', '/meta', 404)
    config_path.write_text(enabled_config)
    request('GET', '/meta')

    # Secondary requests use the real host profile router / private plugin-host IPC.
    other_meta = request('GET', '/meta?profile=crm-test-other')
    assert other_meta['workspace_token'] != token
    request('POST', '/work?profile=crm-test-other', 409, json=save_body)
    request('POST', '/work', 409, json={**save_body, 'workspace_token': other_meta['workspace_token']})
    other_work_scope = {'workspace_token': other_meta['workspace_token'], 'profile': 'crm-test-other'}
    for analytics_path in ('/analytics/catalog', '/analytics/reports', '/analytics/dashboard'):
        request('GET', analytics_path, 409, params={**other_work_scope, 'workspace_token': token})
        request('GET', analytics_path, 409, params={'workspace_token': other_meta['workspace_token']})
    assert request('GET', '/analytics/reports', params=other_work_scope)['items'] == []
    assert request('GET', '/analytics/dashboard', params=other_work_scope)['cards'] == []
    request('GET', report_path, 404, params=other_work_scope)
    request('POST', report_path + '/run?profile=crm-test-other', 404, json={'workspace_token': other_meta['workspace_token'], 'expected_version': 3})
    request('GET', '/interactions', 404, params={**other_work_scope, 'contact_id': contact_id})
    assert request('GET', '/work', params=other_work_scope) == []
    for path in ('/reports/work', '/reports/coverage'):
        empty = request('GET', path, params=other_work_scope)
        assert empty['total'] == 0 and empty['items'] == []
    assert request('GET', '/reports/work', params={**other_work_scope, 'task_id': work_task['id']})['total'] == 0
    request('GET', '/work/' + work['id'], 404, params=other_work_scope)
    for work_path in ('/work', '/work/' + work['id'], '/reports/work', '/reports/coverage'):
        request('GET', work_path, 409, params={**other_work_scope, 'workspace_token': token})
        request('GET', work_path, 409, params={'workspace_token': other_meta['workspace_token']})
    assert request('GET', '/work', params={'workspace_token': token}) == [work]
    assert request('GET', '/work/' + work['id'], params={'workspace_token': token}) == work
    request('POST', '/contacts?profile=crm-test-other', 409,
            json={'workspace_token': token, 'data': {'name': 'Cross-profile stale'}})
    other_contact = request('POST', '/contacts?profile=crm-test-other', 201, json={
        'workspace_token': other_meta['workspace_token'], 'data': {'name': 'Other Profile Only', 'lifecycle': 'customer'}})
    other_token = other_meta['workspace_token']
    assert request('GET', '/email/status', params={'workspace_token': other_token, 'profile': 'crm-test-other'})['enabled'] is False
    request('GET', '/email/status', 409, params={'workspace_token': token, 'profile': 'crm-test-other'})
    request('GET', '/email/status', 409, params={'workspace_token': other_token})
    assert request('GET', '/email/contacts/' + other_contact['id'],
        params={'workspace_token': other_token, 'profile': 'crm-test-other'})['items'] == []
    other_bridge = request('GET', '/email-bridge/status', params=other_work_scope)
    assert other_bridge['enabled'] is False and other_bridge['polling_enabled'] is False
    for bridge_path in ('/email-bridge/status', '/email-bridge/setup', '/email-bridge/unresolved'):
        request('GET', bridge_path, 409, params={**other_work_scope, 'workspace_token': token})
        request('GET', bridge_path, 409, params={'workspace_token': other_token})
    assert request('GET', '/email-bridge/contacts/' + other_contact['id'], params=other_work_scope)['items'] == []
    request('POST', '/email-bridge/verify?profile=crm-test-other', 409, json=bridge_verify)
    request('POST', '/email-bridge/verify?profile=crm-test-other', 409,
            json={**bridge_verify, 'workspace_token': other_token})
    request('GET', '/email-bridge/status', 400, params={**other_work_scope, 'unknown': 'x'})
    assert request('GET', '/email-bridge/status', params={'workspace_token': token}) == bridge_status
    other_queue = request('GET', '/reports/coverage', params=other_work_scope)
    assert other_queue['total'] == 1 and other_queue['items'][0]['contacts'][0]['id'] == other_contact['id']
    assert other_queue['items'][0]['kind'] == 'missing_next_action'
    assert 'Synthetic Native' not in json.dumps(other_queue)
    assert request('GET', '/reports/work', params=other_work_scope)['items'] == []
    request('POST', '/deals?profile=crm-test-other', 201, json={
        'workspace_token': other_token, 'data': {'title': 'Other Profile Won',
        'contact_id': other_contact['id'], 'stage': 'won', 'value': 500}})
    # Secondary routing consumes profile; serving-profile requests may retain it.
    # CRM accepts that host-owned routing key without using it for DB selection.
    # Both paths must preserve strict business filters and workspace-token checks.
    other_filters = {'profile': 'crm-test-other', 'workspace_token': other_token,
                     'stage': 'won', 'contact_type': 'customer', 'limit': 1, 'offset': 0}
    other_report = request('GET', '/reports/contacts', params=other_filters)
    assert other_report['total'] == 1 and other_report['items'][0]['id'] == other_contact['id'], other_report
    assert other_report['items'][0]['deal_stages'] == ['won']
    assert 'Synthetic Native Contact' not in json.dumps(other_report), other_report
    assert request('GET', '/reports/contacts', params={**other_filters, 'stage': 'proposal'})['total'] == 0
    assert request('GET', '/reports/contacts', params={**other_filters, 'contact_type': 'lead'})['total'] == 0
    request('GET', '/reports/contacts', 409, params={**other_filters, 'workspace_token': token})
    request('GET', '/reports/contacts', 409, params={'workspace_token': other_token})
    request('GET', '/reports/contacts', 400, params={**other_filters, 'unknown_filter': 'x'})
    current_report = request('GET', '/reports/contacts', params={**report_filters, 'workspace_token': token})
    assert current_report == report
    assert_contact_report_projection(current_report, tool('crm_contact_report', report_filters))
    assert request('GET', '/reports/contacts', params={'workspace_token': token, 'stage': 'won'})['total'] == 0
    other_rows = request('GET', '/contacts?profile=crm-test-other')
    assert 'Synthetic Native Contact' not in json.dumps(other_rows), other_rows
    current_rows = request('GET', '/contacts')
    assert 'Other Profile Only' not in json.dumps(current_rows), current_rows
    assert Path(get_hermes_home()) == home
    (home / 'profiles/crm-test-other/config.yaml').write_text('plugins:\n  enabled: []\n')
    request('GET', '/meta?profile=crm-test-other', 404)
    request('GET', '/meta')
    assert not list(home.rglob('jobs.json'))
    print('PASS native host: real discovery, allowlist, project refusal, mount, auth, CRUD, tools, stale versions, stale workspace, runtime disable, filtered report/tool parity, atomic reviewed-version create/replay, paginated work and coverage routes, secondary-profile report/work token and IPC isolation; clean HOME/environment and inherited network/agent guard; no network server, jobs or model execution')
'''
