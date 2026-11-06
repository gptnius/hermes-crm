"""Test-only JSON-lines adapter to the real store in disposable SQLite.

No HTTP server, host/plugin calls, provider calls, credentials or persistent user
state. Used by execution_bridge.mjs to check exact bridge/storage signatures.
"""
import json
import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_crm.domain import CRM
from hermes_crm.execution import ExecutionStore


def denied(*args, **kwargs):
    raise AssertionError('Network is forbidden in the bridge store fixture')

socket.create_connection = socket.getaddrinfo = denied
socket.socket.connect = socket.socket.connect_ex = denied
ALLOWED = {'get', 'begin_dispatch', 'observe', 'observe_host', 'record_runtime',
           'record_scope', 'prepare_submit', 'request_cancel', 'cancel_undispatched', 'mark'}
with tempfile.TemporaryDirectory(prefix='crm-bridge-store-') as directory:
    crm = CRM(f'sqlite:///{directory}/store.db', profile='synthetic')
    store = ExecutionStore(crm)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                method = request['method']
                if method == 'init':
                    task = crm.create('tasks', {'title': 'Synthetic internal report',
                                              'due_at': '2030-01-01T00:00:00Z'})
                    result = store.create(task_id=task['id'], human_owner='Synthetic owner',
                        prompt='  Frozen synthetic instruction\n', success_criteria='Review the report',
                        idempotency_key=task['id'], profile='synthetic',
                        host_connection_identity='synthetic-connection-binding',
                        host_profile_identity='authority-profile-1',
                        host_route={'connectionId': 'registry-1', 'profile': 'synthetic',
                                    'targetProfile': 'target-profile', 'mode': 'local'})
                elif method == 'source_task':
                    result = crm.get('tasks', request['id'])
                elif method == 'edit_source_task':
                    task = crm.get('tasks', request['id'])
                    result = crm.update('tasks', request['id'], {'version': task['version'], 'notes': 'Changed'})
                elif method in ALLOWED:
                    result = getattr(store, method)(request['id'], **request.get('params', {}))
                else:
                    raise ValueError('Unapproved test fixture method')
                print(json.dumps({'id': request['request_id'], 'result': result}), flush=True)
            except Exception as error:
                print(json.dumps({'id': request.get('request_id'), 'error': str(error)}), flush=True)
    finally:
        crm.close()
