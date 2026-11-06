"""Opt-in checks against actual Hermes source, never a running gateway.

Run with HERMES_SOURCE=/path/to/hermes-agent and a Python environment containing
that checkout's import dependencies. Normal unit runs skip this module.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
def test_native_cron_read_allowlist_excludes_configured_mcp(tmp_path):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    assert (source / 'cron' / 'scheduler.py').is_file(), 'Invalid HERMES_SOURCE'
    home = tmp_path / 'home'
    home.mkdir()
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(('HERMES_', 'OPENAI_', 'ANTHROPIC_'))}
    env.update(HERMES_HOME=str(home), HERMES_ENABLE_PROJECT_PLUGINS='0',
               HERMES_BUNDLED_PLUGINS=str(home / 'no-bundled-plugins'),
               PYTHONPATH=str(source), PYTHONDONTWRITEBYTECODE='1')
    code = r'''
import socket
from unittest.mock import patch

def deny(*args, **kwargs):
    raise AssertionError('Network is forbidden in this host contract test')

with patch.object(socket, 'create_connection', deny), \
     patch.object(socket.socket, 'connect', deny), \
     patch.object(socket.socket, 'connect_ex', deny):
    # Test-only inspection of the real pinned host resolver; not plugin code.
    from cron.scheduler import _resolve_cron_enabled_toolsets
    cfg = {'mcp_servers': {
        'crm-test-enabled': {'command': 'never-executed', 'enabled': True},
        'crm-test-disabled': {'command': 'never-executed', 'enabled': False},
    }}
    legacy = _resolve_cron_enabled_toolsets({'enabled_toolsets': ['crm_read']}, cfg)
    assert 'crm-test-enabled' in legacy, legacy
    effective = _resolve_cron_enabled_toolsets(
        {'enabled_toolsets': ['crm_read', 'no_mcp']}, cfg)
    assert effective == ['crm_read'], effective
    print('PASS: configured enabled MCP excluded; effective toolsets =', effective)
'''
    result = subprocess.run([sys.executable, '-P', '-c', code], cwd=tmp_path,
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "effective toolsets = ['crm_read']" in result.stdout
    assert not (home / 'cron' / 'jobs.json').exists()
