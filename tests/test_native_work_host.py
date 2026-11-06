"""Opt-in, pinned actual-Hermes native-work contracts; never a model run.

Every case uses a fresh HOME/HERMES_HOME, a credential-free environment and a
sitecustomize guard inherited by the real hosted-plugin child. No scheduler
loop, agent, provider, transport, or server endpoint is started. Disposable
future one-shots are created/resumed through the public cronjob_manage tool.
Test-only inspection calls the real claim ledger and scheduler identity CAS,
then exercises registered plugin callbacks. That proves identity propagation,
not that a due scheduler tick, model turn or delivery completed successfully.
"""
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


PINNED_HOST_SHA = '2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19'


@pytest.mark.skipif(not os.environ.get('HERMES_SOURCE'), reason='HERMES_SOURCE not set')
@pytest.mark.parametrize('isolation', ['in_process', 'host'])
def test_native_work_real_host_claim_context_contract(tmp_path, isolation):
    source = Path(os.environ['HERMES_SOURCE']).resolve()
    revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert revision == PINNED_HOST_SHA, 'Revalidate contracts before changing the pinned host'
    repo = Path(__file__).resolve().parents[1]
    user_home = tmp_path / 'user'
    home = user_home / '.hermes'
    package = home / 'plugins' / 'hermes-crm'
    shutil.copytree(repo, package, ignore=shutil.ignore_patterns(
        '.git', '__pycache__', '.pytest_cache', 'node_modules', 'build', '*.egg-info', 'artifacts'))
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
    assert 'PASS native-work actual-host claim-only contract' in result.stdout
    assert not (tmp_path / 'forbidden-action.log').exists(), result.stdout + result.stderr
    guards = list(tmp_path.glob('guard-loaded-*.json'))
    assert len(guards) == (2 if isolation == 'host' else 1), guards
    # The child asserts public cleanup while its host/registry are still alive.
    # Inspect only our fresh fixture to ensure nothing remained enabled.
    import json
    for path in home.rglob('jobs.json'):
        data = json.loads(path.read_text())
        rows = data.get('jobs', []) if isinstance(data, dict) else data
        assert rows == [], f'Synthetic job cleanup failed: {path}'


@pytest.mark.skip(reason='Claim/context contract only; a guarded deterministic loopback model/scheduler run needs separate scope')
def test_full_due_scheduler_model_turn_and_delivery():
    """Explicitly unverified: real due tick, agent/model turn, terminal receipt and delivery."""


SAFETY_GUARD = r'''
import importlib.abc
import json
import os
from pathlib import Path
import socket
import sys

root = Path(os.environ['CRM_HOST_CONTRACT_ROOT']).resolve()
assert Path(os.environ['HOME']).resolve() == root / 'user'
assert Path(os.environ['HERMES_HOME']).resolve() == root / 'user/.hermes'
assert not any(key.endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD')) for key in os.environ)
(root / ('guard-loaded-' + str(os.getpid()) + '.json')).write_text(json.dumps({'pid': os.getpid()}))

def forbidden(action):
    with (root / 'forbidden-action.log').open('a') as handle:
        handle.write(str(action) + '\n')
    raise AssertionError('Forbidden in native-work host fixture: ' + str(action))

def audit(event, args):
    if event in {'socket.connect', 'socket.bind', 'socket.getaddrinfo', 'socket.gethostbyname',
                 'socket.gethostbyaddr', 'socket.getnameinfo', 'socket.sendto', 'socket.sendmsg', 'os.system', 'os.posix_spawn', 'os.exec', 'os.fork'}:
        forbidden(event)
    if event == 'subprocess.Popen':
        executable, argv, cwd, env = args
        # Host version discovery legitimately reads pinned-checkout provenance.
        import re
        git_read = (list(argv) in [
            ['git', 'rev-parse', 'HEAD'], ['git', 'rev-parse', '--short=7', 'HEAD'],
            ['git', 'branch', '--show-current'], ['git', 'log', '-1', '--format=%ct', 'HEAD'],
            ['git', '--no-optional-locks', 'status', '--porcelain', '-uno'],
            ['git', 'tag', '--merged', 'HEAD', '--list', 'v[0-9]*'],
        ] or (len(argv) == 4 and list(argv[:3]) == ['git', 'rev-list', '--count']
              and re.fullmatch(r'v[0-9.]+\.\.HEAD', argv[3])))
        if git_read and Path(cwd).resolve() == Path(os.environ['CRM_HOST_CONTRACT_SOURCE']).resolve():
            return
        allowed = [sys.executable, '-m', 'hermes_cli.plugin_host_child']
        if list(argv) != allowed or Path(cwd).resolve() != root / 'user/.hermes':
            forbidden('process launch: ' + repr(argv))
        if not env or str(root / 'guard') not in env.get('PYTHONPATH', '').split(os.pathsep):
            forbidden('plugin child missing safety guard')

sys.addaudithook(audit)

class NoAgentImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'run_agent':
            forbidden('agent/model launch import')

sys.meta_path.insert(0, NoAgentImport())
'''


HOST_CHECK = r'''
import json
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime
from unittest.mock import patch

from hermes_cli.plugins import get_plugin_manager
from tools.registry import registry
from tools import cronjob_tools
from cron import executions, jobs, scheduler
from cron import execution_identity
from agent.delegation_context import delegated_child_context
from toolsets import resolve_toolset

home = Path(os.environ['HERMES_HOME'])
# Do not inspect unrelated service processes; the real fresh-home lock and
# heartbeat checks still run, with no gateway available to this fixture.
gateway_probe = patch('hermes_cli.gateway.find_gateway_pids', return_value=[])
gateway_probe.start()
manager = get_plugin_manager()
manager.discover_and_load()
owned_jobs = set()
ledger_rows = set()
violations = []
cron_calls = []
cron_contexts = []
created_views = {}
real_cron = registry.get_entry('cronjob_manage', scope=manager.scope_key).handler
cron_entry = registry.get_entry('cronjob_manage', scope=manager.scope_key)
mode = {'lose_create': False, 'lose_resume': False}


def raw_tool(name, args, **kwargs):
    entry = registry.get_entry(name, scope=manager.scope_key)
    assert entry is not None, name
    response = registry.dispatch(name, args, scope=manager.scope_key, **kwargs)
    return json.loads(response) if isinstance(response, str) else response


def tool(name, args, **kwargs):
    response = raw_tool(name, args, **kwargs)
    assert response.get('ok') is True, (name, response)
    return response['data']


def reject(name, args, status, **kwargs):
    response = raw_tool(name, args, **kwargs)
    assert response.get('ok') is False and response.get('status') == status, (name, response)
    return response


def stored_assignment(assignment_id):
    with sqlite3.connect(home / 'plugin-data/hermes-crm/data.db') as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM crm_native_assignments WHERE id=?', (assignment_id,)).fetchone()
        events = db.execute('SELECT kind FROM crm_native_work_events WHERE assignment_id=? ORDER BY version',
                            (assignment_id,)).fetchall()
    return dict(row), [row[0] for row in events]


def observe_real_cron(args, **kwargs):
    action = args.get('action')
    cron_calls.append(dict(args))
    cron_contexts.append(dict(kwargs))
    if action not in {'create', 'resume', 'list', 'pause', 'remove'}:
        violations.append('Unexpected scheduler action: ' + str(action))
        raise AssertionError(violations[-1])
    if action == 'create':
        assert args['paused'] is True and args['repeat'] == 1, args
        assert args['deliver'] == args['failure_deliver'] == 'local'
        assert args['enabled_toolsets'] == ['crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp']
    if action == 'resume':
        assert args['job_id'] in owned_jobs
        job = jobs.get_job(args['job_id'])
        assignment_id = job['name'].split()[2]
        row, events = stored_assignment(assignment_id)
        # Separate DB connection observes the durable exact binding before resume.
        assert row['job_id'] == args['job_id'] and row['state'] == 'resume_unknown', row
        assert events.index('job_bound') < events.index('resume_started'), events
        assert job['enabled'] is False and job['state'] == 'paused', job
        assert job['next_run_at'] is None
    response = real_cron(args, **kwargs)
    data = json.loads(response)
    if action == 'create' and data.get('success'):
        owned_jobs.add(data['job_id'])
        created_views[data['job_id']] = data
        job = jobs.get_job(data['job_id'])
        assert job['enabled'] is False and job['state'] == 'paused'
        assert jobs.claim_job_for_fire(job['id']) is False, 'Paused native jobs must be inert'
        if mode['lose_create']:
            return '{\"synthetic_lost_create_response\":'
    if action == 'resume' and mode['lose_resume']:
        return '{\"synthetic_lost_resume_response\":'
    return response


cron_entry.handler = observe_real_cron


def create_assignment(label):
    task = tool('crm_task_create', {'title': 'Synthetic native host task ' + label,
                                  'due_at': '2099-01-01T00:00:00Z'})
    intent = tool('crm_work_create', {
        'task_id': task['id'], 'human_owner': 'Synthetic fixture owner',
        'prompt': 'Summarize only synthetic CRM records. No external work.',
        'success_criteria': 'Return one brief internal analysis for human review.',
        'run_at': '2099-02-03T04:05:37.123456+00:00', 'idempotency_key': label,
    })
    assert intent['state'] == 'pending' and intent['job_id'] is None
    return task, intent


def schedule_assignment(label):
    task, intent = create_assignment(label)
    result = tool('crm_work_schedule', {'assignment_id': intent['id']},
                  session_id='synthetic-host-context', task_id='synthetic-tool-turn')
    assert result['state'] == 'scheduled', result
    assert result['reason'] == 'host_job_saved_execution_unverified', result
    assert result['job_id'] in owned_jobs
    assert result['host_terminal_success_verified'] is False
    assert all(e['evidence'].get('gateway_running') is not True for e in result['events']), result
    return task, result


@contextmanager
def claimed_occurrence(assignment):
    """Real host claim/ledger/CAS, with clock scoped only to synthetic claim creation.

    This does not run a scheduler tick or execute the job. The host, rather than
    a test-constructed CronExecution, derives identity from the claimed ledger.
    """
    instant = datetime.fromisoformat(assignment['payload']['run_at'])
    with patch.object(jobs, '_hermes_now', return_value=instant):
        claimed = jobs.claim_job_for_fire(assignment['job_id'], return_job=True)
    assert claimed and claimed['_scheduled_instant'] == assignment['payload']['run_at'], claimed
    record = executions.create_execution(claimed['id'], source='builtin',
                                         scheduled_instant=claimed['_scheduled_instant'])
    ledger_rows.add(record['id'])
    assert record['status'] == 'claimed'
    assert execution_identity.current_cron_execution() is None
    token = scheduler._start_owned_run(claimed, record['id'])
    assert token is not None
    assert scheduler._start_owned_run(claimed, record['id']) is None, 'Only one claim CAS may win'
    actual = execution_identity.current_cron_execution()
    assert actual.execution_id == record['id'] and actual.job_id == claimed['id']
    assert executions.get_execution(record['id'])['status'] == 'running'
    try:
        yield actual
    finally:
        execution_identity.exit_cron_execution(token)
        assert execution_identity.current_cron_execution() is None
        executions.finish_execution(record['id'], success=False, cancelled=True,
                                    error='Synthetic claim-only fixture cleanup; no model ran')


try:
    for name, toolset in {'crm_work_get': 'crm_work_read', 'crm_work_list': 'crm_work_read',
                         'crm_work_create': 'crm_work_schedule', 'crm_work_schedule': 'crm_work_schedule',
                         'crm_work_reconcile': 'crm_work_schedule', 'crm_work_cancel': 'crm_work_schedule',
                         'crm_work_report': 'crm_work_report'}.items():
        assert registry.get_entry(name, scope=manager.scope_key).toolset == toolset

    task, assignment = schedule_assignment('native-host-primary')
    assert [c['action'] for c in cron_calls] == ['create', 'resume']
    for context in cron_contexts:
        assert context['session_id'] == 'synthetic-host-context', context
        assert context['task_id'] == 'synthetic-tool-turn', context
    job = jobs.get_job(assignment['job_id'])
    assert job['enabled_toolsets'] == ['crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp']
    assert job['schedule']['kind'] == 'once'
    assert not any(job.get(key) for key in ('script', 'no_agent', 'model', 'provider', 'base_url',
                                           'monitor_script', 'monitor_url', 'attach_to_session', 'context_from'))
    # Inspect the actual pinned host resolver, not a copied approximation.
    cfg = {'mcp_servers': {'synthetic-enabled': {'command': 'NEVER-LAUNCH', 'enabled': True}}}
    effective = scheduler._resolve_cron_enabled_toolsets(job, cfg)
    assert effective == ['crm_read', 'crm_work_read', 'crm_work_report'], effective
    allowed_tools = {name for toolset in effective for name in resolve_toolset(toolset)}
    assert {'crm_contact_get', 'crm_task_get', 'crm_work_get', 'crm_work_report'} <= allowed_tools
    assert not ({'crm_work_schedule', 'crm_work_create', 'crm_work_reconcile', 'crm_work_cancel',
                 'crm_task_update', 'crm_task_create', 'crm_contact_update', 'crm_followup_schedule',
                 'cronjob_manage', 'delegate_task', 'send_message'} & allowed_tools), allowed_tools
    assert not any('mcp' in name for name in allowed_tools), allowed_tools
    assert {'cronjob', 'messaging', 'clarify'} <= set(scheduler._resolve_cron_disabled_toolsets({}))

    report_args = {'assignment_id': assignment['id'], 'generation': 1,
                   'summary': 'Synthetic internal analysis, awaiting human review.'}
    reject('crm_work_report', report_args, 403)
    for field, value in {'job_id': job['id'], 'execution_id': 'forged', 'profile': 'default',
                         'scheduled_instant': assignment['payload']['run_at'],
                         'current_cron_execution': {'job_id': job['id']}}.items():
        reject('crm_work_report', {**report_args, field: value}, 422)
    # Handler kwargs also cannot replace the host-owned context.
    reject('crm_work_report', report_args, 403, current_cron_execution={'job_id': job['id']},
           execution_id='forged', job_id=job['id'])

    # A different authentic job occurrence is not allowed to report for this one.
    _, other_assignment = schedule_assignment('native-host-wrong-job')
    with claimed_occurrence(other_assignment):
        reject('crm_work_report', report_args, 403)
    assert not tool('crm_work_get', {'assignment_id': assignment['id']})['reports']

    with claimed_occurrence(assignment) as actual:
        with delegated_child_context():
            assert execution_identity.current_cron_execution() is None
            reject('crm_work_report', report_args, 403)
        reject('crm_work_report', {**report_args, 'generation': 2}, 409)
        reject('crm_work_schedule', {'assignment_id': assignment['id']}, 403)
        reject('crm_work_reconcile', {'assignment_id': assignment['id']}, 403)
        # Adversarial context corruption is explicitly negative-only, not proof
        # of a scheduler firing or a model-supplied way to change host identity.
        for changes in ({'job_id': 'wrong-job'}, {'job_name': 'wrong-name'}, {'profile': 'other'},
                        {'scheduled_instant': '2099-02-03T04:05:37.123457+00:00'},
                        {'scheduled_instant': None}, {'execution_id': ''}, {'source': 'direct'}):
            forged = execution_identity._CURRENT.set(replace(actual, **changes))
            try:
                response = raw_tool('crm_work_report', report_args)
                assert response.get('ok') is False, (changes, response)
            finally:
                execution_identity._CURRENT.reset(forged)
        result = tool('crm_work_report', report_args)
        assert result['state'] == 'result_reported'
        assert result['reason'] == 'native_result_reported_awaiting_review'
        assert len(result['reports']) == 1
        report = result['reports'][0]
        assert report['execution_id'] == actual.execution_id
        expected_identity = asdict(actual)
        from datetime import timezone
        for key in ('started_at', 'scheduled_instant'):
            expected_identity[key] = datetime.fromisoformat(expected_identity[key]).astimezone(timezone.utc).isoformat(timespec='microseconds')
        assert report['identity'] == expected_identity, (report, actual)
        assert report['review_status'] == 'awaiting_human_review'
        assert report['provenance'] == 'native_run_reported'
        assert executions.get_execution(actual.execution_id)['status'] == 'running'
        replay = tool('crm_work_report', report_args)
        assert replay['version'] == result['version'] and replay['events'] == result['events']
        assert replay['reports'] == result['reports']
        reject('crm_work_report', {**report_args, 'summary': 'Conflicting content'}, 409)
        reject('crm_work_report', {**report_args, 'outcome': 'failed'}, 409)
        reject('crm_work_report', {**report_args, 'operation_id': 'another-operation'}, 422)
        assert tool('crm_task_get', {'id': task['id']}) == task, 'A report must not mark business work done'
    reject('crm_work_report', report_args, 403)

    # A lost create reply leaves a real paused orphan, never an adopted name match.
    _, orphan_intent = create_assignment('native-host-lost-create')
    before = len(owned_jobs)
    mode['lose_create'] = True
    unknown = tool('crm_work_schedule', {'assignment_id': orphan_intent['id']})
    mode['lose_create'] = False
    assert unknown['state'] == 'unknown' and unknown['job_id'] is None, unknown
    assert len(owned_jobs) == before + 1
    orphan = next(j for j in jobs.list_jobs(include_disabled=True) if j['name'] == unknown['job_name'])
    view = created_views[orphan['id']]['job']
    assert view['prompt_preview'].endswith('...') and len(orphan['prompt']) > len(view['prompt_preview'])
    assert ':37' not in view['schedule'], view  # Public schedule text loses seconds/microseconds.
    count = len(cron_calls)
    tool('crm_work_schedule', {'assignment_id': unknown['id']})
    assert len(cron_calls) == count, 'Unknown creation cannot be retried automatically'
    reconciled = tool('crm_work_reconcile', {'assignment_id': unknown['id']})
    assert reconciled['job_id'] is None and reconciled['state'] == 'unknown', reconciled
    assert reconciled['events'][-1]['evidence']['auto_adopted'] is False
    assert jobs.get_job(orphan['id'])['enabled'] is False
    assert jobs.claim_job_for_fire(orphan['id']) is False

    # Resume can succeed while its reply is lost; reconciliation observes only.
    _, uncertain = create_assignment('native-host-lost-resume')
    mode['lose_resume'] = True
    uncertain = tool('crm_work_schedule', {'assignment_id': uncertain['id']})
    mode['lose_resume'] = False
    assert uncertain['state'] == 'unknown' and uncertain['job_id'] in owned_jobs
    assert jobs.get_job(uncertain['job_id'])['enabled'] is True
    count = len(cron_calls)
    observed = tool('crm_work_reconcile', {'assignment_id': uncertain['id']})
    assert [c['action'] for c in cron_calls[count:]] == ['list']
    assert observed['state'] == 'scheduled' and not observed['reports']
    cancelled = tool('crm_work_cancel', {'assignment_id': observed['id'], 'version': observed['version']})
    assert cancelled['state'] == 'cancelled' and cancelled['generation'] == 2
    assert jobs.get_job(cancelled['job_id'])['enabled'] is False

    # Invalidating during a real claim rejects its subsequent report, even when
    # a running occurrence still holds its prior identity. Supersession is an
    # internal local-store fence, not a production API claim to cancel a run.
    for invalid_state in ('cancelled', 'superseded'):
        _, invalid = schedule_assignment('native-host-' + invalid_state)
        with claimed_occurrence(invalid):
            # Local fixture mutation invokes the real store, not hand-written SQL.
            import sys
            sys.path.insert(0, str(home / 'plugins/hermes-crm'))
            from hermes_crm.runtime import open_profile_crm
            from hermes_crm.native_work import NativeWorkStore
            crm = open_profile_crm(profile=invalid['profile'])
            try:
                saved = NativeWorkStore(crm).invalidate(invalid['id'], version=invalid['version'], reason=invalid_state)
            finally:
                crm.close()
            assert saved['state'] == invalid_state
            reject('crm_work_report', {'assignment_id': invalid['id'], 'generation': 1,
                                      'summary': 'Must reject stale running occurrence'}, 409)
            reject('crm_work_report', {'assignment_id': invalid['id'], 'generation': 2,
                                      'summary': 'Cannot revive invalid intent'}, 409)

    assert not violations, violations
    print('PASS native-work actual-host claim-only contract: real registry/context dispatch, paused binding before resume, fixed resolver allowlist, ledger CAS identity over plugin callbacks/proxies, adversarial rejection, report idempotency, lost-response non-adoption, cancellation/supersession fences; no model execution or terminal success claim')
finally:
    cron_entry.handler = real_cron
    for job_id in owned_jobs:
        for action in ('pause', 'remove'):
            response = json.loads(registry.dispatch('cronjob_manage', {'action': action, 'job_id': job_id}, scope=manager.scope_key))
            assert response.get('success') is True, response
    assert jobs.list_jobs(include_disabled=True) == []
    for execution_id in ledger_rows:
        row = executions.get_execution(execution_id)
        if row['status'] in {'claimed', 'running'}:
            executions.finish_execution(execution_id, success=False, cancelled=True, error='Fixture cleanup')
        assert executions.get_execution(execution_id)['status'] == 'cancelled'
    host = getattr(manager, '_plugin_host_instance', None)
    manager.unload()
    if host is not None:
        host.shutdown()
        assert not host.alive
    assert not list(home.rglob('*.sock')), 'No endpoint may remain'
    gateway_probe.stop()
'''
