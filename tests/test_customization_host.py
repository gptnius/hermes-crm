"""Opt-in real pinned-host tool dispatch, with no network, agents or scheduler."""
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import pytest
from test_native_work_host import PINNED_HOST_SHA, SAFETY_GUARD as BASE_SAFETY_GUARD

# Pinned host version_info._calver_release_version reads local tag provenance.
# Extend only the exact argv allowlist, retaining the original pinned-source
# cwd check and every process/network/agent restriction. This checkout has no
# matching CalVer tags, so no git-show or broader read command is needed.
_VERSION_QUERY_ANCHOR = "            ['git', 'tag', '--merged', 'HEAD', '--list', 'v[0-9]*'],"
assert BASE_SAFETY_GUARD.count(_VERSION_QUERY_ANCHOR) == 1
SAFETY_GUARD = BASE_SAFETY_GUARD.replace(
    _VERSION_QUERY_ANCHOR,
    _VERSION_QUERY_ANCHOR + "\n            ['git', 'describe', '--tags', '--long', '--match', 'v2[0-9][0-9][0-9].*', 'HEAD'],",
)


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_custom_schema_pinned_host(tmp_path, isolation):
    if importlib.util.find_spec('ruamel') is None:
        pytest.skip('Pinned Hermes host dependency ruamel.yaml is not installed in this interpreter')
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert revision == PINNED_HOST_SHA, 'Revalidate contracts before changing the pinned host'
    repo = Path(__file__).resolve().parents[1]
    user_home = tmp_path / 'user'
    home = user_home / '.hermes'
    package = home / 'plugins' / 'hermes-crm'
    shutil.copytree(repo, package, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.pytest_cache', 'node_modules', 'build', '*.egg-info', 'artifacts', '*native_chat*'))
    (home / 'config.yaml').write_text(
        f'plugins:\n  isolation: {isolation}\n  enabled: [hermes-crm]\n'
        '  entries:\n    hermes-crm:\n      settings:\n        backend: sqlite\n')
    # Fresh scratch needs no pruning and must not spawn a detached helper.
    scratch = home / 'cache/scratch'
    scratch.mkdir(parents=True)
    (scratch / '.last_prune').touch()
    guard = tmp_path / 'guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text(SAFETY_GUARD)
    # The validation interpreter may expose this library through user-site.
    # Copy only installed distribution files, never an existing user home or
    # profile, so the clean child does not depend on ambient user-site access.
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
    # Construct, never copy: no ambient auth, provider, profile or path survives.
    env = {
        'HOME': str(user_home), 'USERPROFILE': str(user_home), 'HERMES_HOME': str(home),
        'HERMES_ENABLE_PROJECT_PLUGINS': '0',
        'HERMES_BUNDLED_PLUGINS': str(tmp_path / 'no-bundled-plugins'),
        'PYTHONPATH': os.pathsep.join((str(guard), str(source), str(dependencies))),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'CRM_HOST_CONTRACT_ROOT': str(tmp_path), 'CRM_HOST_CONTRACT_ISOLATION': isolation,
        'CRM_HOST_CONTRACT_SOURCE': str(source),
    }
    result = subprocess.run([sys.executable, '-P', '-c', HOST_CHECK], cwd=tmp_path,
                            env=env, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS custom-schema actual-host contract' in result.stdout
    assert not (tmp_path / 'forbidden-action.log').exists(), result.stdout + result.stderr
    guards = list(tmp_path.glob('guard-loaded-*.json'))
    assert len(guards) == (2 if isolation == 'host' else 1), guards


HOST_CHECK = r'''
import json
import os
from pathlib import Path
from hermes_cli.plugins import get_plugin_manager
from tools.registry import registry

manager = get_plugin_manager()
manager.discover_and_load()
def raw(name, args):
    response = registry.dispatch(name, args, scope=manager.scope_key)
    return json.loads(response) if isinstance(response, str) else response

def tool(name, args):
    response = raw(name, args)
    assert response.get('ok') is True, (name, response)
    return response['data']

try:
    for name in ['crm_schema_catalog', 'crm_schema_stage_create', 'crm_schema_stage_update', 'crm_schema_field_create', 'crm_schema_field_update']:
        entry = registry.get_entry(name, scope=manager.scope_key)
        assert entry.toolset == ('crm_schema_read' if name == 'crm_schema_catalog' else 'crm_schema_write')
    catalog = tool('crm_schema_catalog', {})
    assert catalog['schema_version'] == 1 and not catalog['fields']['contacts']
    args = {'data': {'key': 'discovery', 'label': 'Discovery', 'probability': 25}, 'idempotency_key': 'host-stage'}
    stage = tool('crm_schema_stage_create', args)
    assert tool('crm_schema_stage_create', args) == stage
    field = tool('crm_schema_field_create', {'kind': 'contacts', 'data': {'key': 'tier', 'label': 'Tier', 'type': 'single-select', 'choices': ['A', 'B']}, 'idempotency_key': 'host-field'})
    contact = tool('crm_contact_create', {'name': 'Synthetic host', 'custom_fields': {'tier': 'A'}, 'idempotency_key': 'host-contact'})
    assert contact['custom_fields'] == {'tier': 'A'}
    assert tool('crm_contact_get', {'id': contact['id']})['custom_fields'] == {'tier': 'A'}
    deal = tool('crm_deal_create', {'title': 'Synthetic deal', 'stage': 'discovery', 'contact_id': contact['id']})
    assert tool('crm_deal_list', {'stage': 'discovery'})[0]['id'] == deal['id']
    updated = tool('crm_schema_stage_update', {'stage_key': 'discovery', 'data': {'version': 1, 'label': 'Discovery call'}})
    assert updated['version'] == 2
    assert raw('crm_schema_stage_update', {'stage_key': 'discovery', 'data': {'version': 1, 'label': 'Stale'}})['status'] == 409
    assert not raw('crm_schema_field_update', {'kind': 'contacts', 'field_key': 'tier', 'data': {'version': 1, 'type': 'number'}})['ok']
    assert not raw('crm_schema_catalog', {'profile': 'other'})['ok']
    assert not raw('crm_schema_field_create', {'kind': 'stages', 'data': {}, 'idempotency_key': 'invalid'})['ok']
    print('PASS custom-schema actual-host contract')
finally:
    host = getattr(manager, '_plugin_host_instance', None)
    manager.unload()
    if host is not None:
        host.shutdown()
        assert not host.alive
    assert not list(Path(os.environ['HERMES_HOME']).rglob('*.sock'))
'''
