"""Real REST routing and registered tools use one profile-scoped domain service."""
import json
import pytest
from test_native_work_adapters import adapters, SCHEMA_READ, SCHEMA_WRITE, LEGACY_READ
from hermes_crm.native_work import TOOLSETS
from hermes_crm import native_api


def token(adapters):
    return adapters.client.get('/meta').json()['workspace_token']


def test_schema_catalog_route_tool_isolation_and_manifest(adapters):
    a = adapters
    scope = token(a)
    catalog = a.client.get('/customization/catalog', params={'workspace_token': scope})
    assert catalog.status_code == 200
    assert a.ctx.invoke('crm_schema_catalog', {})['data'] == catalog.json()
    assert set(a.ctx.tools) >= SCHEMA_READ | SCHEMA_WRITE
    assert {name for name, tool in a.ctx.tools.items() if tool['toolset'] == 'crm_read'} == LEGACY_READ
    assert not {'crm_schema_read', 'crm_schema_write'} & set(TOOLSETS)
    for name in SCHEMA_WRITE:
        assert a.ctx.tools[name]['toolset'] == 'crm_schema_write'
    assert len(a.ctx.tools) == 83
    assert 'enum' not in a.ctx.tools['crm_deal_list']['schema']['parameters']['properties']['stage']
    assert 'enum' not in a.ctx.tools['crm_contact_report']['schema']['parameters']['properties']['stage']
    for name in ['crm_contact_create', 'crm_deal_create', 'crm_task_update']:
        assert 'custom_fields' in a.ctx.tools[name]['schema']['parameters']['properties']


def test_stage_rest_tool_equivalence_conflicts_and_profile_switch(adapters):
    a = adapters
    scope = token(a)
    data = {'key': 'discovery', 'label': 'Discovery', 'probability': 25, 'color': '#123abc', 'description': 'Discovery call'}
    body = {'workspace_token': scope, 'data': data, 'idempotency_key': 'stage-one'}
    response = a.client.post('/customization/stages', json=body)
    assert response.status_code == 201, response.text
    stage = response.json()
    contact = a.ctx.invoke('crm_contact_create', {'name': 'Discovery contact'})['data']
    deal = a.ctx.invoke('crm_deal_create', {'title': 'Discovery deal', 'stage': 'discovery', 'contact_id': contact['id']})['data']
    assert a.client.get('/deals', params={'stage': 'discovery'}).json()[0]['id'] == deal['id']
    assert a.ctx.invoke('crm_deal_update', {'id': deal['id'], 'version': 1, 'stage': 'won'})['ok']
    assert a.ctx.invoke('crm_schema_stage_create', {'data': data, 'idempotency_key': 'stage-one'})['data'] == stage
    updated = a.ctx.invoke('crm_schema_stage_update', {'stage_key': 'discovery', 'data': {'version': 1, 'label': 'Discovery meeting'}})
    assert updated['ok'] and updated['data']['version'] == 2
    assert a.client.patch('/customization/stages/discovery', json={'workspace_token': scope, 'data': {'version': 1, 'archived': True}}).status_code == 409
    assert a.client.patch('/customization/stages/discovery', json={'workspace_token': scope, 'data': {'version': 2, 'archived': True}}).json()['archived'] is True
    a.state['profile'] = 'beta'
    assert a.client.get('/customization/catalog', params={'workspace_token': scope}).status_code == 409
    assert a.client.post('/customization/stages', json=body).status_code == 409
    assert not any(x['key'] == 'discovery' for x in a.ctx.invoke('crm_schema_catalog', {})['data']['stages'])
    assert a.client.get('/customization/catalog', params={'workspace_token': token(a)}).status_code == 200


def test_custom_values_across_rest_tools_archive_and_clear(adapters):
    a = adapters
    scope = token(a)
    field = {'key': 'tier', 'label': 'Tier', 'type': 'single-select', 'choices': ['A', 'B']}
    result = a.ctx.invoke('crm_schema_field_create', {'kind': 'contacts', 'data': field, 'idempotency_key': 'tier-one'})
    assert result['ok'], result
    assert a.client.post('/customization/fields/contacts', json={'workspace_token': scope, 'data': field, 'idempotency_key': 'tier-one'}).json() == result['data']
    created = a.ctx.invoke('crm_contact_create', {'name': 'Example', 'custom_fields': {'tier': 'A'}})['data']
    record_id = created['id']
    assert a.client.get('/contacts/'+record_id).json()['contact']['custom_fields'] == {'tier': 'A'}
    updated = a.client.patch('/contacts/'+record_id, json={'workspace_token': scope, 'data': {'version': 1, 'company': 'Retained'}})
    assert updated.status_code == 200 and updated.json()['custom_fields'] == {'tier': 'A'}
    cleared = a.ctx.invoke('crm_contact_update', {'id': record_id, 'version': 2, 'custom_fields': {'tier': None}})
    assert cleared['ok'] and 'custom_fields' not in cleared['data']
    assert a.ctx.invoke('crm_record_fields', {'kind': 'contacts', 'id': record_id, 'fields': ['custom.tier']})['data']['fields'] == {'custom.tier': None}
    archive = a.client.patch('/customization/fields/contacts/tier', json={'workspace_token': scope, 'data': {'version': 1, 'archived': True}})
    assert archive.status_code == 200 and archive.json()['archived']
    assert not a.ctx.invoke('crm_contact_update', {'id': record_id, 'version': 3, 'custom_fields': {'tier': 'B'}})['ok']
    assert a.client.patch('/customization/fields/contacts/tier', json={'workspace_token': scope, 'data': {'version': 1, 'label': 'stale'}}).status_code == 409


@pytest.mark.parametrize('query', ['&unknown=x', '&workspace_token=again', '&profile=a&profile=b'])
def test_catalog_rejects_unknown_repeated_query(adapters, query):
    assert adapters.client.get('/customization/catalog?workspace_token='+token(adapters)+query).status_code == 400


def test_reject_ambiguous_body_unknown_fields_and_missing_versions(adapters):
    a = adapters
    scope = token(a)
    body = {'workspace_token': scope, 'idempotency_key': 'invalid', 'data': {'key': 'new', 'label': 'New'}}
    for raw in [json.dumps(body).replace('"New"', '"New", "label":"Other"'),
                json.dumps(body)[:-1] + ',"workspace_token":"other"}']:
        assert a.client.post('/customization/stages', content=raw, headers={'content-type': 'application/json'}).status_code == 422
    assert a.client.post('/customization/stages', json=dict(body, profile='other')).status_code == 422
    assert a.client.post('/customization/stages', json=dict(body, data=dict(body['data'], unknown=True))).status_code == 400
    assert a.client.post('/customization/stages?profile=a&profile=b', json=body).status_code == 400
    assert a.client.post('/customization/stages?unknown=x', json=body).status_code == 400
    assert a.client.post('/customization/stages', json={'workspace_token': scope, 'data': body['data']}).status_code == 422
    assert a.client.patch('/customization/stages/lead', json={'workspace_token': scope, 'data': {'label': 'No version'}}).status_code in (400, 409, 422)
    assert not a.ctx.invoke('crm_schema_stage_update', {'stage_key': 'lead', 'data': {'label': 'No version'}})['ok']
    assert not a.ctx.invoke('crm_schema_field_create', {'kind': 'stages', 'data': body['data'], 'idempotency_key': 'nope'})['ok']
    assert not a.ctx.invoke('crm_schema_stage_create', {'data': body['data'], 'idempotency_key': None})['ok']
    assert not a.ctx.invoke('crm_schema_catalog', {'profile': 'beta'})['ok']


def test_generic_backend_failure_has_no_paths_or_secrets(adapters, monkeypatch):
    def fail():
        raise RuntimeError('postgresql://user:secret@private.example/database')
    monkeypatch.setattr(native_api, 'open_profile_crm', fail)
    response = adapters.client.get('/customization/catalog?workspace_token=anything')
    assert response.status_code == 503
    assert 'secret' not in response.text and 'private.example' not in response.text


def test_snapshot_enriches_domain_snapshot_without_rereading_metadata(adapters, monkeypatch):
    class SnapshotOnly:
        profile = 'alpha'
        def snapshot(self):
            return {'meta': {'workspace_token': 'snapshot-token', 'catalog': {'sentinel': True}},
                    'overview': {}, 'contacts': [], 'deals': [], 'tasks': [], 'activity': []}
        def close(self):
            pass
        def info(self):
            raise AssertionError('Adapter must not reread metadata outside the snapshot')
        def workspace_token(self):
            raise AssertionError('Adapter must use token returned by domain snapshot')
    monkeypatch.setattr(native_api, 'open_profile_crm', SnapshotOnly)
    result = adapters.client.get('/snapshot')
    assert result.status_code == 200
    meta = result.json()['meta']
    assert meta['workspace_token'] == 'snapshot-token' and meta['catalog'] == {'sentinel': True}
    assert meta['native_desktop'] and meta['scheduler'] == 'existing-agent' and meta['work_command_name']
