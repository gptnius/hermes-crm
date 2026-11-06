"""Opt-in native API integration against the actual, pinned Hermes checkout.

No Desktop launch, model execution, cron writes, or user profiles are involved.
HERMES_SOURCE must point to an official Hermes source checkout with its imports
available to this interpreter. The complete server runs only as an ASGI test app.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_official_dashboard_discovery_auth_crud_tools_and_profiles(tmp_path, isolation):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / 'home'
    package = home / 'plugins' / 'hermes-crm'
    shutil.copytree(repo, package, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.pytest_cache', 'node_modules', 'build', '*.egg-info', 'artifacts'))
    config = f'plugins:\n  isolation: {isolation}\n  enabled: [hermes-crm]\n  entries:\n    hermes-crm:\n      settings:\n        backend: sqlite\n'
    (home / 'config.yaml').write_text(config)
    other = home / 'profiles' / 'crm-test-other'
    other.mkdir(parents=True)
    (other / 'config.yaml').write_text(config)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('HERMES_', 'OPENAI_', 'ANTHROPIC_'))}
    env.update(HERMES_HOME=str(home), HERMES_ENABLE_PROJECT_PLUGINS='0',
               HERMES_BUNDLED_PLUGINS=str(tmp_path / 'no-bundled-plugins'),
               PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-P', '-c', HOST_CHECK], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS native host' in result.stdout
    assert not list(home.rglob('jobs.json')), 'Validation must never create cron jobs'


HOST_CHECK = r'''
import json
import os
from pathlib import Path
import socket
from unittest.mock import patch


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

    def tool(name, args):
        entry = registry.get_entry(name, scope=manager.scope_key)
        assert entry is not None, name
        response = json.loads(entry.handler(args))
        assert response['ok'], response
        return response['data']

    client = TestClient(host.app, base_url='http://localhost')
    prefix = '/api/plugins/hermes-crm'
    headers = {'Authorization': f'Bearer {host._SESSION_TOKEN}'}
    def request(method, path, expected=200, **kwargs):
        response = client.request(method, prefix + path, headers=headers, **kwargs)
        assert response.status_code == expected, (method, path, response.status_code, response.text)
        return response.json()

    assert client.get(prefix + '/meta').status_code == 401
    assert client.post(prefix + '/contacts', json={}).status_code == 401
    meta = request('GET', '/meta')
    token = meta['workspace_token']
    assert meta['native_desktop'] is True
    created = request('POST', '/contacts', 201, json={
        'workspace_token': token, 'idempotency_key': 'native-host-contact',
        'data': {'name': 'Synthetic Native Contact', 'email': 'synthetic@example.invalid'}})
    contact_id = created['id']
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
    assert request('GET', '/overview')
    # The registered agent report and REST report share filters and aggregates.
    report_filters = {'stage': 'proposal', 'contact_type': 'lead', 'followup': 'missing',
                      'limit': 1, 'offset': 0}
    report = request('GET', '/reports/contacts',
                     params={**report_filters, 'workspace_token': token})
    assert report == tool('crm_contact_report', report_filters), report
    assert report['total'] == 1 and report['items'][0]['id'] == contact_id, report
    assert report['items'][0]['deal_stages'] == ['proposal']
    from hermes_cli.web_server_profiles import serving_profile_name
    for profile_alias in dict.fromkeys(('current', '', serving_profile_name())):
        assert request('GET', '/reports/contacts',
            params={**report_filters, 'workspace_token': token, 'profile': profile_alias}) == report
        assert request('GET', '/contacts',
            params={'workspace_token': token, 'stage': 'proposal', 'profile': profile_alias})[0]['id'] == contact_id
    request('GET', '/reports/contacts', 409,
            params={**report_filters, 'workspace_token': 'stale-profile-token'})


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
    request('POST', '/contacts?profile=crm-test-other', 409,
            json={'workspace_token': token, 'data': {'name': 'Cross-profile stale'}})
    other_contact = request('POST', '/contacts?profile=crm-test-other', 201, json={
        'workspace_token': other_meta['workspace_token'], 'data': {'name': 'Other Profile Only', 'lifecycle': 'customer'}})
    other_token = other_meta['workspace_token']
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
    assert current_report == report == tool('crm_contact_report', report_filters)
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
    print('PASS native host: real discovery, allowlist, project refusal, mount, auth, CRUD, tools, stale versions, stale workspace, runtime disable, filtered report/tool parity, secondary-profile report token and IPC isolation')
'''
