"""Opt-in real scheduled execution with a deterministic, keyless loopback model.

No real model quality, restart recovery, or desktop notification is asserted.
Fresh disposable profile; actual scheduler, canonical admission, AIAgent, tool
search and plugin handlers. Only the HTTP model is synthetic. No production
credentials, profiles, provider children, external sockets or messages allowed.

Validated on pinned host 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19 with
CPython 3.14.9+20261021, OpenAI 2.54.0 and urllib3 2.8.0. Both plugin isolation
modes retain default deferred discovery. Probe source hashes remain pinned;
other runtimes or dependency sources require explicit revalidation.
"""
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import textwrap

import pytest

PINNED_HOST_SHA = '2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.skipif(os.environ.get('HERMES_NATIVE_E2E') != '1', reason='Guarded full runner requires separate HERMES_NATIVE_E2E=1 opt-in')
@pytest.mark.skipif(sys.version_info[:3] != (3, 14, 9), reason='Guard source hashes are validated only on pinned CPython 3.14.9')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_native_work_real_due_scheduler_loopback_model(tmp_path, isolation):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    original_home = Path.home().resolve()
    repo = Path(__file__).resolve().parents[1]
    required_roots = [source, repo, tmp_path.resolve(), Path(sys.executable).resolve(),
                      Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
    assert original_home != Path(original_home.anchor), 'Cannot deny a filesystem root as the original home'
    assert all(not path.is_relative_to(original_home) for path in required_roots), (
        'Isolated fixture, host and Python dependencies must all be outside the forbidden original home')
    sha = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                         check=True, capture_output=True, text=True).stdout.strip()
    assert sha == PINNED_HOST_SHA
    home = tmp_path / 'profile'
    shutil.copytree(repo, home / 'plugins/hermes-crm', ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.pytest_cache', 'node_modules', 'build', '*.egg-info', 'artifacts'))
    dependencies = tmp_path / 'dependencies'
    dependencies.mkdir()
    dist = importlib.metadata.distribution('sqlalchemy')
    for relative in dist.files or ():
        if relative.parts[0] != 'sqlalchemy' and not relative.parts[0].endswith('.dist-info'):
            continue
        original = dist.locate_file(relative)
        if original.is_file():
            target = dependencies / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    # Reserve an unused port for this process; the child guard allows exactly it.
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    config = {
        'model': {'default': 'synthetic-crm-fixture', 'provider': 'custom',
                  'base_url': f'http://127.0.0.1:{port}/v1', 'context_length': 131072},
        'agent': {'max_turns': 16, 'environment_probe': False},
        'compression': {'enabled': False},
        'memory': {'enabled': False},
        'mcp_servers': {},
        'cron': {'max_parallel_jobs': 1, 'preflight': True},
        'plugins': {'isolation': isolation, 'enabled': ['hermes-crm'],
                    'entries': {'hermes-crm': {'settings': {'backend': 'sqlite'}}}},
    }
    # JSON is also YAML and avoids using an ambient config loader in the parent.
    (home / 'config.yaml').write_text(json.dumps(config))
    scratch = home / 'cache/scratch'
    scratch.mkdir(parents=True)
    (scratch / '.last_prune').touch()
    guard = tmp_path / 'guard'
    guard.mkdir()
    (guard / 'sitecustomize.py').write_text(SAFETY_GUARD)
    env = {
        'HOME': str(tmp_path / 'user'), 'USERPROFILE': str(tmp_path / 'user'),
        'HERMES_HOME': str(home), 'HERMES_ENABLE_PROJECT_PLUGINS': '0',
        'HERMES_GATEWAY_SESSION': '1',  # The fixture initializes a real local GatewayRunner.
        'HERMES_BUNDLED_PLUGINS': str(tmp_path / 'no-bundled-plugins'),
        'PYTHONPATH': os.pathsep.join((str(guard), str(source), str(dependencies))),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'CRM_E2E_ROOT': str(tmp_path), 'CRM_E2E_SOURCE': str(source),
        'CRM_E2E_PORT': str(port), 'CRM_E2E_ISOLATION': isolation,
        'CRM_E2E_FORBIDDEN_HOME': str(original_home),
    }
    # Python normally swallows sitecustomize exceptions. A changed source hash
    # must terminate startup before any fixture code or hosted child can run.
    invalid_guard = tmp_path / 'invalid-guard'
    invalid_guard.mkdir()
    sdk_hash = '5539c83d01c27e1bbf1ad34e59cc872202feb6c8bf81b56fadbeeb2b81a3e869'
    assert sdk_hash in SAFETY_GUARD
    (invalid_guard / 'sitecustomize.py').write_text(SAFETY_GUARD.replace(sdk_hash, '0' * 64))
    invalid_env = dict(env, PYTHONPATH=os.pathsep.join((str(invalid_guard), str(source), str(dependencies))))
    invalid = subprocess.run([sys.executable, '-P', '-c', "raise RuntimeError('UNGUARDED_FIXTURE_RAN')"],
        cwd=tmp_path, env=invalid_env, capture_output=True, text=True, timeout=15)
    assert invalid.returncode == 97 and 'UNGUARDED_FIXTURE_RAN' not in invalid.stderr, invalid
    invalid_child = subprocess.run([sys.executable, '-P', '-m', 'hermes_cli.plugin_host_child'],
        cwd=tmp_path, env=invalid_env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert invalid_child.returncode == 97, invalid_child
    assert not list(tmp_path.glob('guard-ready-*.json'))
    result = subprocess.run([sys.executable, '-P', '-c', E2E_CHECK], cwd=tmp_path,
                            env=env, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=150)
    (tmp_path / 'fixture-output.txt').write_text(result.stdout + result.stderr)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS actual due scheduler and deterministic model' in result.stdout
    assert not (tmp_path / 'forbidden-action.log').exists(), result.stdout + result.stderr
    guard_loads = list(tmp_path.glob('guard-ready-*.json'))
    assert len(guard_loads) == (2 if isolation == 'host' else 1), guard_loads
    assert all(json.loads(path.read_text())['hook_ready'] is True for path in guard_loads)
    evidence = json.loads((tmp_path / 'evidence.json').read_text())
    assert evidence['cleanup']['enabled_jobs'] == 0
    assert evidence['cleanup']['scheduler_stopped'] and evidence['cleanup']['endpoint_stopped']
    assert evidence['cleanup']['plugin_host_stopped']
    assert evidence['terminal_status'] == 'completed'
    with socket.socket() as probe:
        assert probe.connect_ex(('127.0.0.1', port)) != 0, 'Fixture endpoint leaked'
    for path in home.rglob('jobs.json'):
        rows = json.loads(path.read_text())
        assert (rows.get('jobs', []) if isinstance(rows, dict) else rows) == []


SAFETY_GUARD = r'''
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import sys

root = Path(os.environ['CRM_E2E_ROOT']).resolve()
source = Path(os.environ['CRM_E2E_SOURCE']).resolve()
forbidden_home = Path(os.environ['CRM_E2E_FORBIDDEN_HOME']).resolve()
assert forbidden_home.is_absolute() and forbidden_home != Path(forbidden_home.anchor)
assert all(not path.is_relative_to(forbidden_home) for path in (
    root, source, Path(sys.executable).resolve(), Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()))
endpoint = ('127.0.0.1', int(os.environ['CRM_E2E_PORT']))
assert Path(os.environ['HOME']).resolve() == root / 'user'
assert Path(os.environ['HERMES_HOME']).resolve() == root / 'profile'
assert not any(key.endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD')) for key in os.environ)
# Pin the source of each narrowly authorized capability probe. These hashes
# came from the checksum-verified runtime and frozen, hash-verified host wheels.
probe_sources = {
    'ipv6': (Path(sys.prefix) / 'lib/python3.14/site-packages/urllib3/util/connection.py',
             '2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74', '_has_ipv6'),
    'platform': (Path(sys.base_prefix) / 'lib/python3.14/platform.py',
                 '240eba74565cd0dc4f99f182f7afc32bbea0593016ddb34165b529b5bcb6be0a', 'from_subprocess'),
    'sdk': (Path(sys.prefix) / 'lib/python3.14/site-packages/openai/_base_client.py',
            '5539c83d01c27e1bbf1ad34e59cc872202feb6c8bf81b56fadbeeb2b81a3e869', 'get_platform'),
}
for path, digest, function in probe_sources.values():
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path
unit = 'hermes-gateway-' + hashlib.sha256(str(root / 'profile').encode()).hexdigest()[:8]


def frames():
    # Only source coordinates. Never collect locals, parameters or credentials.
    result = []
    frame = sys._getframe(1)
    while frame is not None and len(result) < 80:
        result.append({'file': frame.f_code.co_filename, 'function': frame.f_code.co_name,
                       'line': frame.f_lineno})
        frame = frame.f_back
    return result


def has_frame(stack, path, function):
    return any(row['file'] == str(path) and row['function'] == function for row in stack)


def allow_probe(action, stack):
    with (root / 'probe-evidence.jsonl').open('a') as stream:
        stream.write(json.dumps({'action': action, 'source_frames': stack}) + '\n')


real_listen = socket.socket.listen

def guarded_listen(sock, *args):
    if sock.getsockname() != endpoint:
        forbidden('listener outside exact model endpoint')
    return real_listen(sock, *args)

socket.socket.listen = guarded_listen

def forbidden(action):
    with (root / 'forbidden-action.log').open('a') as stream:
        stream.write(json.dumps({'action': str(action), 'source_frames': frames()}) + '\n')
    raise AssertionError('Forbidden in native-work e2e: ' + str(action))

def audit(event, args):
    if event in {'socket.connect', 'socket.bind'}:
        if args[1] != endpoint:
            stack = frames()
            path, _, function = probe_sources['ipv6']
            if (event == 'socket.bind' and args[1] == ('::1', 0)
                    and args[0].family == socket.AF_INET6 and has_frame(stack, path, function)):
                allow_probe('urllib3 IPv6 capability bind ::1:0; never a listener', stack)
                return
            forbidden(event + ': ' + repr(args[1]))
    if event == 'socket.getaddrinfo':
        if tuple(args[:2]) != endpoint:
            forbidden(event + ': ' + repr(args[:2]))
    if event in {'socket.gethostbyname', 'socket.gethostbyaddr', 'socket.getnameinfo',
                 'socket.sendto', 'socket.sendmsg', 'os.system', 'os.posix_spawn', 'os.exec', 'os.fork'}:
        forbidden(event)
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = os.fsdecode(args[0])
        resolved = Path(path).resolve()
        if resolved.is_relative_to(forbidden_home):
            forbidden('original user/profile read: ' + path)
        if not resolved.is_relative_to(root):
            if resolved.name in {'.env', '.netrc', 'auth.json', 'credentials.json', 'credentials', 'token.json'} and resolved.exists():
                forbidden('outside credential read: ' + path)
    if event == 'subprocess.Popen':
        executable, argv, cwd, env = args
        stack = frames()
        platform_path, _, platform_function = probe_sources['platform']
        sdk_path, _, sdk_function = probe_sources['sdk']
        if (list(argv) == ['uname', '-p'] and has_frame(stack, platform_path, platform_function)
                and has_frame(stack, sdk_path, sdk_function)):
            allow_probe('OpenAI SDK platform metadata: uname -p', stack)
            return
        if (list(argv) in [
                ['systemctl', '--user', 'list-units', unit, '--plain', '--no-legend', '--no-pager'],
                ['systemctl', 'list-units', unit, '--plain', '--no-legend', '--no-pager'],
                ] and has_frame(stack, source / 'hermes_cli/gateway.py', '_get_service_pids')):
            allow_probe('Read-only disposable profile service unit lookup: ' + ' '.join(argv), stack)
            return
        git_read = list(argv) in [
            ['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', '--short=7', 'HEAD'],
            ['git', 'branch', '--show-current'], ['git', 'log', '-1', '--format=%ct', 'HEAD'],
            ['git', '--no-optional-locks', 'status', '--porcelain', '-uno'],
            ['git', 'tag', '--merged', 'HEAD', '--list', 'v[0-9]*'],
        ] or (len(argv) == 4 and list(argv[:3]) == ['git', 'rev-list', '--count']
              and re.fullmatch(r'v[0-9.]+\.\.HEAD', argv[3]))
        if git_read and cwd and Path(cwd).resolve() == source:
            return
        if list(argv) != [sys.executable, '-m', 'hermes_cli.plugin_host_child'] or Path(cwd).resolve() != root / 'profile':
            forbidden('process launch: ' + repr(argv))
        if not env or str(root / 'guard') not in env.get('PYTHONPATH', '').split(os.pathsep):
            forbidden('plugin child missing safety guard')

sys.addaudithook(audit)
(root / ('guard-ready-' + str(os.getpid()) + '.json')).write_text(json.dumps({'pid': os.getpid(), 'hook_ready': True}))
'''
# sitecustomize exceptions otherwise only print a warning and let Python run.
# This fail-closed wrapper is inherited unchanged by the official plugin child.
SAFETY_GUARD = ('import os\ntry:\n' + textwrap.indent(SAFETY_GUARD, '    ')
                + '\nexcept BaseException:\n    os._exit(97)\n')


E2E_CHECK = r'''
import asyncio
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
from pathlib import Path
import re
import socketserver
import sqlite3
import threading
import time

logging.basicConfig(level=logging.INFO)
root = Path(os.environ['CRM_E2E_ROOT'])
home = Path(os.environ['HERMES_HOME'])
guard_ready = json.loads((root / ('guard-ready-' + str(os.getpid()) + '.json')).read_text())
assert guard_ready == {'pid': os.getpid(), 'hook_ready': True}, 'Audit guard must be ready before runner work'
port = int(os.environ['CRM_E2E_PORT'])
model_requests = []
model_request_received_at = []
model_errors = []
report_summary = None
expected = {}
scheduled_catalog = {'crm_contact_report', 'crm_contact_list', 'crm_contact_get',
    'crm_deal_list', 'crm_deal_get', 'crm_task_list', 'crm_task_get', 'crm_overview',
    'crm_work_get', 'crm_work_list', 'crm_work_report'}
forbidden_descriptions = {'crm_task_update', 'crm_work_schedule', 'crm_work_create',
    'cronjob_manage', 'delegate_task', 'send_message'}
discovery_evidence = {}

class LoopbackServer(HTTPServer):
    def server_bind(self):
        # HTTPServer's reverse-DNS hostname display is unnecessary for a local fixture.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address

class Model(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        return
    def do_POST(self):
        try:
            # Capture the real local receive time before reading the body or
            # processing any model protocol. This covers the whole due window.
            model_request_received_at.append(datetime.now(timezone.utc).isoformat(timespec='microseconds'))
            assert self.path == '/v1/chat/completions', self.path
            assert self.headers.get('Authorization') in (None, 'Bearer no-key-required')
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert data['model'] == 'synthetic-crm-fixture'
            model_requests.append(data)
            name, args, final = self.next_step(data)
            if name:
                delta = {'role': 'assistant', 'tool_calls': [{'index': 0,
                    'id': 'synthetic_call_' + str(len(model_requests)), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}]}
                finish = 'tool_calls'
            else:
                delta, finish = {'role': 'assistant', 'content': final}, 'stop'
            if data.get('stream'):
                chunks = [dict(id='synthetic-' + str(len(model_requests)), object='chat.completion.chunk',
                    created=int(time.time()), model=data['model'], choices=[dict(index=0, delta=delta, finish_reason=None)]),
                    dict(id='synthetic-' + str(len(model_requests)), object='chat.completion.chunk',
                    created=int(time.time()), model=data['model'], choices=[dict(index=0, delta={}, finish_reason=finish)])]
                body = ''.join('data: ' + json.dumps(c) + '\n\n' for c in chunks) + 'data: [DONE]\n\n'
                content_type = 'text/event-stream'
            else:
                message = dict(delta)
                for call in message.get('tool_calls', []):
                    call.pop('index', None)
                body = json.dumps(dict(id='synthetic', object='chat.completion', created=int(time.time()),
                    model=data['model'], choices=[dict(index=0, message=message, finish_reason=finish)],
                    usage={'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130}))
                content_type = 'application/json'
            body = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except BaseException as exc:
            model_errors.append(repr(exc))
            self.send_error(500, 'Synthetic fixture assertion failed')
    def next_step(self, data):
        global report_summary
        names = {t['function']['name'] for t in data.get('tools', [])}
        allowed = scheduled_catalog | {'tool_search', 'tool_describe', 'tool_call'}
        assert names <= allowed, names - allowed
        catalog = json.dumps(data.get('tools', []))
        for forbidden in ('crm_task_update', 'crm_work_schedule', 'crm_work_create', 'crm_followup_schedule',
                          'cronjob_manage', 'delegate_task', 'send_message'):
            assert forbidden not in catalog, forbidden
        messages = data['messages']
        results = []
        call_names = {}
        for message in messages:
            for call in message.get('tool_calls') or []:
                call_names[call['id']] = call['function']['name']
            if message['role'] == 'tool':
                value = json.loads(message['content'])
                results.append((call_names[message['tool_call_id']], value))
        def invoke(name, args):
            if name in names:
                return name, args, None
            assert 'tool_call' in names
            return 'tool_call', {'calls': [{'name': name, 'arguments': args}]}, None
        # Exercise actual default deferred discovery instead of disabling it.
        if 'tool_search' in names and not results:
            return 'tool_search', {'queries': ['crm', 'crm_task_update', 'crm_work_schedule',
                'cronjob_manage', 'delegate_task', 'send_message', 'mcp'], 'limit': 25}, None
        if results and results[-1][0] == 'tool_search':
            found = results[-1][1]
            assert found['total_available'] == len(scheduled_catalog), found
            assert set(found['tools']) == scheduled_catalog, found
            assert set(found['results'][0]['matches']) == scheduled_catalog, found
            assert all(set(group['matches']) <= scheduled_catalog for group in found['results']), found
            discovery_evidence['search_catalog'] = sorted(found['tools'])
            discovery_evidence['total_available'] = found['total_available']
            return 'tool_describe', {'names': ['crm_work_get', 'crm_task_get', 'crm_contact_get',
                'crm_work_report'] + sorted(forbidden_descriptions)}, None
        if results and results[-1][0] == 'tool_describe':
            described = results[-1][1]
            assert set(described['tools']) == {'crm_work_get', 'crm_task_get', 'crm_contact_get', 'crm_work_report'}, described
            unavailable = set(described.get('not_found', [])) | set(described.get('errors', {}))
            assert unavailable == forbidden_descriptions, described
            discovery_evidence['forbidden_descriptions_unavailable'] = sorted(unavailable)
        useful = []
        for name, value in results:
            if name in ('tool_search', 'tool_describe'):
                continue
            assert value.get('ok') is True, value
            useful.append(value['data'])
        if not useful:
            return invoke('crm_work_get', {'assignment_id': expected['assignment_id']})
        work = useful[0]
        assert work['id'] == expected['assignment_id']
        if len(useful) == 1:
            return invoke('crm_task_get', {'id': work['task_id']})
        task = useful[1]
        if len(useful) == 2:
            return invoke('crm_contact_get', {'id': task['contact_id']})
        contact = useful[2]
        if len(useful) == 3:
            report_summary = ('SYNTHETIC internal analysis: ' + contact['name'] + ' at ' + contact['company']
                + ' has open task "' + task['title'] + '" with ' + task['priority']
                + ' priority. CRM notes: ' + contact['notes']
                + ' Recommendation: the human owner should review the renewal needs before outreach. '
                + 'No outreach performed; this synthetic report awaits human review.')
            return invoke('crm_work_report', {'assignment_id': work['id'], 'generation': work['generation'],
                'operation_id': 'result', 'outcome': 'completed', 'summary': report_summary})
        assert len(useful) == 4 and useful[3]['state'] == 'result_reported', useful
        return None, None, report_summary

server = LoopbackServer(('127.0.0.1', port), Model)
server_thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
server_thread.start()
stop = threading.Event()
ticker = None
manager = None
creator = None
owned_jobs = set()
evidence = {'synthetic_model': True, 'live_model_quality_verified': False, 'desktop_notification_verified': False}
import hashlib
import sys
evidence['python'] = sys.version
evidence['isolation'] = os.environ['CRM_E2E_ISOLATION']
evidence['tested_plugin_sha256'] = {name: hashlib.sha256((home / 'plugins/hermes-crm' / name).read_bytes()).hexdigest()
    for name in ('hermes_crm/native_work.py', 'hermes_crm/plugin.py', 'hermes_crm/native_api.py', 'plugin.yaml')}

async def run():
    global ticker, manager, creator
    from hermes_cli.plugins import get_plugin_manager
    from tools.registry import registry
    from cron import jobs, executions, scheduler
    from cron.scheduler_provider import InProcessCronScheduler
    from gateway.config import GatewayConfig
    from gateway.run import GatewayRunner
    from gateway.session_authority import initialize_session_authority
    from gateway.session_cron import unbind_owner
    from run_agent import AIAgent

    manager = get_plugin_manager()
    manager.discover_and_load()
    runner = GatewayRunner(GatewayConfig())
    authority = await initialize_session_authority(runner, profile_id='default', instance_id='synthetic-e2e')
    creator = AIAgent(model='synthetic-crm-fixture', provider='custom', api_key='no-key-required',
        base_url=f'http://127.0.0.1:{port}/v1', enabled_toolsets=['crm_read', 'crm_write', 'crm_work_read', 'crm_work_schedule', 'cronjob', 'no_mcp'],
        quiet_mode=True, skip_context_files=True, skip_memory=True, skip_background_review=True)
    from model_tools import get_tool_definitions
    from gateway.session_context import scoped_current_session_id, get_session_env
    from hermes_cli.plugin_host_wire import Opaque
    creator_catalog = get_tool_definitions(enabled_toolsets=creator.enabled_toolsets,
        disabled_toolsets=creator.disabled_toolsets, quiet_mode=True, skip_tool_search_assembly=True)
    # Inspection only: the agent retains its ordinary deferred discovery surface.
    assert {'crm_work_create', 'crm_work_schedule', 'cronjob_manage'} <= {
        t['function']['name'] for t in creator_catalog}
    evidence['creator_scheduling_available'] = True
    evidence['creator_context_contract'] = 'AIAgent object in-process; official Opaque(AIAgent) over host wire; origin session ContextVar preserved'
    def raw(name, args, **context):
        if context.get('parent_agent') is creator:
            context.setdefault('session_id', 'synthetic-creator')
            context.setdefault('task_id', 'synthetic-scheduling-turn')
            with scoped_current_session_id('synthetic-creator'):
                value = registry.dispatch(name, args, scope=manager.scope_key, **context)
        else:
            value = registry.dispatch(name, args, scope=manager.scope_key, **context)
        return json.loads(value) if isinstance(value, str) else value
    def tool(name, args, **context):
        value = raw(name, args, **context)
        assert value.get('ok') is True, (name, value)
        return value['data']
    real_cron = registry.get_entry('cronjob_manage', scope=manager.scope_key).handler
    observed = []
    def observe(args, **context):
        observed.append(args['action'])
        parent = context.get('parent_agent')
        if os.environ['CRM_E2E_ISOLATION'] == 'host':
            assert isinstance(parent, Opaque) and parent.type_name == 'AIAgent'
        else:
            assert parent is creator
        assert context['session_id'] == 'synthetic-creator'
        assert context['task_id'] == 'synthetic-scheduling-turn'
        assert get_session_env('HERMES_SESSION_ID') == 'synthetic-creator'
        if args['action'] == 'create':
            assert args['paused'] is True and args['repeat'] == 1
            assert args['deliver'] == args['failure_deliver'] == 'local'
        if args['action'] == 'resume':
            job = jobs.get_job(args['job_id'])
            assert job['enabled'] is False and job['state'] == 'paused'
            with sqlite3.connect(home / 'plugin-data/hermes-crm/data.db') as db:
                row = db.execute('SELECT job_id,state FROM crm_native_assignments WHERE id=?',
                                 (expected['assignment_id'],)).fetchone()
            assert row == (args['job_id'], 'resume_unknown'), row
        value = real_cron(args, **context)
        parsed = json.loads(value)
        if args['action'] == 'create' and parsed.get('success'):
            owned_jobs.add(parsed['job_id'])
        return value
    registry.get_entry('cronjob_manage', scope=manager.scope_key).handler = observe
    try:
        contact = tool('crm_contact_create', {'name': 'Synthetic Avery', 'company': 'Synthetic Acme',
            'notes': 'Renewal needs two additional seats; no price approved.'})
        task = tool('crm_task_create', {'title': 'Review synthetic renewal needs', 'contact_id': contact['id'],
            'priority': 'high', 'due_at': (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()})
        due = datetime.now(timezone.utc) + timedelta(seconds=8)
        work = tool('crm_work_create', {'task_id': task['id'], 'human_owner': 'Synthetic owner',
            'prompt': 'Analyze the linked contact notes and task priority. Do not contact anyone.',
            'success_criteria': 'State renewal needs and a human-reviewed next step.',
            'run_at': due.isoformat(timespec='microseconds'), 'idempotency_key': 'synthetic-e2e'}, parent_agent=creator)
        expected['assignment_id'] = work['id']
        work = tool('crm_work_schedule', {'assignment_id': work['id']}, parent_agent=creator,
                    session_id='synthetic-creator', task_id='synthetic-scheduling-turn')
        assert work['state'] == 'scheduled', work
        assert observed == ['create', 'resume'], observed
        assert not model_requests
        ticker = threading.Thread(target=InProcessCronScheduler().start, args=(stop,),
                                  kwargs={'interval': .1}, daemon=True)
        ticker.start()
        await asyncio.sleep(.5)
        assert datetime.now(timezone.utc) < due
        assert not model_requests, 'Model called before the due instant'
        assert executions.list_executions(job_id=work['job_id']) == []
        deadline = time.monotonic() + 70
        terminal = None
        while time.monotonic() < deadline:
            rows = executions.list_executions(job_id=work['job_id'])
            if rows and rows[0]['status'] not in {'claimed', 'running'}:
                terminal = rows[0]
                break
            await asyncio.sleep(.1)
        assert terminal, (jobs.get_job(work['job_id']), rows, model_errors)
        assert terminal['status'] == 'completed', (terminal, model_errors)
        report = tool('crm_work_get', {'assignment_id': work['id']})
        assert report['state'] == 'result_reported' and report['review_status'] == 'awaiting_human_review', report
        assert report['host_terminal_success_verified'] is False
        assert report['business_task_completed_by_report'] is False
        assert len(report['reports']) == 1
        receipt = report['reports'][0]
        assert receipt['execution_id'] == terminal['id']
        assert receipt['identity']['execution_id'] == terminal['id']
        assert receipt['workspace'] == work['workspace']
        assert receipt['identity']['job_name'] == work['job_name']
        assert receipt['identity']['source'] == terminal['source'] == 'builtin'
        assert terminal['scheduled_instant'] == work['payload']['run_at']
        approved_due = datetime.fromisoformat(work['payload']['run_at'])
        ledger_started = datetime.fromisoformat(terminal['started_at'])
        assert approved_due.tzinfo is not None and ledger_started.tzinfo is not None
        assert ledger_started >= approved_due, (terminal['started_at'], work['payload']['run_at'])
        assert len(model_request_received_at) == len(model_requests) > 0
        assert all(datetime.fromisoformat(stamp) >= approved_due for stamp in model_request_received_at), (
            work['payload']['run_at'], model_request_received_at)
        assert terminal['finished_at'] and terminal['error'] is None
        assert receipt['identity']['job_id'] == work['job_id']
        assert receipt['identity']['scheduled_instant'] == work['payload']['run_at']
        assert receipt['identity']['profile'] == 'default' and receipt['generation'] == work['generation']
        assert receipt['summary'] == report_summary and 'two additional seats' in report_summary
        assert tool('crm_task_get', {'id': task['id']})['status'] == 'open'
        output = list((jobs.get_cron_output_dir() / work['job_id']).glob('*.md'))
        assert len(output) == 1 and report_summary in output[0].read_text()
        # Inspect the actual durable canonical receipt for this exact fire, not
        # merely the existence of some session in the initialized authority.
        from hermes_state_keys import CRON_PRINCIPAL_ID, cron_request_id, local_identity
        from hermes_state_runtime import find_session_admission, get_session_admission
        from gateway.session_results import admission_result
        from gateway.session_local_recovery import local_adapter_map
        from gateway.config import Platform
        request_id = cron_request_id(work['job_id'], terminal['id'])
        session_id = local_identity(authority.profile_id, CRON_PRINCIPAL_ID, request_id)
        admission = find_session_admission(authority.db, principal_id=CRON_PRINCIPAL_ID,
            session_id=session_id, request_id=request_id)
        assert admission and admission['status'] == 'terminal' and admission['outcome'] == 'completed', admission
        assert admission == get_session_admission(authority.db, admission_id=admission['admission_id'])
        assert admission['target_session_id'] == session_id and admission['request_id'] == request_id
        assert admission['principal_id'] == CRON_PRINCIPAL_ID and session_id in authority.sessions
        policy = local_adapter_map(authority)[Platform.LOCAL].policies[session_id]
        policy_request = json.loads(policy.request_json)
        assert policy.source == policy.platform == 'cron'
        assert policy_request['request_id'] == request_id
        assert policy_request['cron_job']['id'] == work['job_id']
        saved = admission_result(authority.db, admission['admission_id'])
        assert saved['result']['completed'] is True and saved['result']['failed'] is False, saved
        canonical_result = saved['result']['cron_result']
        assert len(canonical_result) == 4 and canonical_result[0] is True and canonical_result[3] is None, canonical_result
        assert canonical_result[2] == report_summary and report_summary in canonical_result[1]
        assert saved['result']['final_response'] == report_summary
        assert discovery_evidence['total_available'] == len(scheduled_catalog)
        before = len(model_requests)
        await asyncio.sleep(.6)
        assert len(model_requests) == before
        assert len(executions.list_executions(job_id=work['job_id'])) == 1
        assert len(tool('crm_work_get', {'assignment_id': work['id']})['reports']) == 1
        evidence.update(terminal_status=terminal['status'], model_requests=len(model_requests),
            streaming_requests=sum(bool(r.get('stream')) for r in model_requests),
            initial_model_tool_names=[t['function']['name'] for t in model_requests[0]['tools']],
            approved_due_instant=work['payload']['run_at'], ledger_started_at=terminal['started_at'],
            model_request_received_at=list(model_request_received_at),
            all_model_requests_at_or_after_due=True, ledger_started_at_or_after_due=True,
            actual_report=receipt, local_output_verified=True, duplicate_extra_ticks=False,
            canonical_admission_verified=True, paused_bind_resume=observed[:2],
            canonical_receipt={'admission_id': admission['admission_id'], 'session_id': session_id,
                'request_id': request_id, 'principal_id': admission['principal_id'],
                'status': admission['status'], 'outcome': admission['outcome'],
                'stored_cron_result_matches': True}, scheduled_discovery=discovery_evidence)
        # A second real scheduled assignment is cancelled before its due instant.
        # The scheduler keeps ticking; neither a model call nor an attempt may appear.
        cancelled_due = datetime.now(timezone.utc) + timedelta(seconds=3)
        cancelled = tool('crm_work_create', {'task_id': task['id'], 'human_owner': 'Synthetic owner',
            'prompt': 'Synthetic cancelled analysis; must never execute.',
            'success_criteria': 'No execution after cancellation.',
            'run_at': cancelled_due.isoformat(timespec='microseconds'),
            'idempotency_key': 'synthetic-cancelled-e2e'}, parent_agent=creator)
        expected['assignment_id'] = cancelled['id']
        cancelled = tool('crm_work_schedule', {'assignment_id': cancelled['id']}, parent_agent=creator)
        cancelled = tool('crm_work_cancel', {'assignment_id': cancelled['id'], 'version': cancelled['version']},
                         parent_agent=creator)
        assert cancelled['state'] == 'cancelled'
        assert cancelled['reason'] == 'future_schedule_paused_running_run_not_cancelled', cancelled
        assert jobs.get_job(cancelled['job_id'])['enabled'] is False
        await asyncio.sleep(max(0, (cancelled_due - datetime.now(timezone.utc)).total_seconds()) + .4)
        assert len(model_requests) == before
        assert executions.list_executions(job_id=cancelled['job_id']) == []
        assert tool('crm_work_get', {'assignment_id': cancelled['id']})['reports'] == []
        assert tool('crm_task_get', {'id': task['id']})['status'] == 'open'
        evidence['cancelled_before_due_never_executed'] = True
    finally:
        stop.set()
        if ticker:
            await asyncio.to_thread(ticker.join, 10)
            assert not ticker.is_alive()
        registry.get_entry('cronjob_manage', scope=manager.scope_key).handler = real_cron
        for job_id in owned_jobs:
            actions = ('pause', 'remove') if jobs.get_job(job_id).get('enabled') else ('remove',)
            for action in actions:
                value = json.loads(real_cron({'action': action, 'job_id': job_id}, parent_agent=creator))
                assert value.get('success'), value
        assert jobs.list_jobs(include_disabled=True) == []
        unbind_owner(authority)
        creator.close()
        runner.session_store.close_all_db_handles()
        if runner._executor:
            runner._executor.shutdown(wait=True)
        evidence['cleanup'] = {'enabled_jobs': 0, 'scheduler_stopped': ticker is None or not ticker.is_alive()}

try:
    asyncio.run(run())
finally:
    stop.set()
    server.shutdown()
    server.server_close()
    server_thread.join(10)
    if manager is not None:
        host = getattr(manager, '_plugin_host_instance', None)
        manager.unload()
        if host is not None:
            host.shutdown()
            assert not host.alive
        evidence.setdefault('cleanup', {})['plugin_host_stopped'] = host is None or not host.alive
    evidence.setdefault('cleanup', {})['endpoint_stopped'] = not server_thread.is_alive()
    (root / 'evidence.json').write_text(json.dumps(evidence, indent=2))
assert not model_errors, model_errors
print('PASS actual due scheduler and deterministic model')
'''
