"""Actual JavaScript request shapes replayed through the real standalone router."""
import json
import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from hermes_crm.domain import CRM
from hermes_crm.web import create_app


def test_ui_owner_transport_contract(tmp_path):
    root = Path(__file__).resolve().parents[1]
    requests = json.loads(subprocess.check_output(['node', str(root / 'tests/standalone_owner_transport.cjs')], cwd=root, text=True))
    crm = CRM('sqlite:///' + str(tmp_path / 'synthetic-owner-contract.db'))
    try:
        with TestClient(create_app(crm)) as client:
            scope = client.get('/api/meta').json()['workspace_token']
            assert requests[1]['path'] == 'task-owner-policy'
            task_id = None
            for request in requests:
                path = request['path'].replace('SYNTHETIC_SCOPE', scope)
                if task_id:
                    path = path.replace('synthetic-task', task_id)
                body = request.get('body')
                if body and 'workspace_token' in body:
                    body['workspace_token'] = scope
                headers = {'Idempotency-Key': request['key']} if request.get('key') else {}
                response = client.request(request['method'], '/api/' + path, json=body, headers=headers)
                assert response.status_code in (200, 201), response.text
                if request['method'] == 'POST':
                    task_id = response.json()['id']
                if request['method'] != 'GET':
                    validation = subprocess.check_output(['node', str(root / 'tests/standalone_owner_transport.cjs'), '--validate-receipt'], input=json.dumps({'request': request, 'result': response.json()}), cwd=root, text=True)
                    assert validation.strip() == 'true'
                    replay = client.request(request['method'], '/api/' + path, json=body, headers=headers)
                    assert replay.status_code in (200, 201) and replay.json() == response.json()
            task = response.json()
            assert task['owner_label'] == 'Reviewed owner' and task['owner_source'] == 'default'
            assert task['due_at'].endswith('.123456+00:00')
            assert len(crm.list('tasks')) == 1
    finally:
        crm.close()
