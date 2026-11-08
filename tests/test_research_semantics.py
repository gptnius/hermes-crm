"""A reviewed note edit must never masquerade as communication or task execution."""
import pytest
from hermes_crm.domain import CRM
from hermes_crm.report_interactions import InteractionStore
from hermes_crm.reports import ReportEngine
from hermes_crm.research_store import ResearchStore
from test_research import packet, review


@pytest.mark.parametrize('logged', [False, True])
def test_append_changes_last_edit_not_contact_history_or_task(logged, monkeypatch):
    crm = CRM('sqlite:///:memory:')
    try:
        contact = crm.create('contacts', {'name': 'Synthetic review subject', 'notes': 'Existing note'})
        task = crm.create('tasks', {'title': 'Synthetic preparation', 'contact_id': contact['id'], 'due_at': '2030-01-01T00:00:00Z'})
        if logged:
            InteractionStore(crm).create({'contact_id': contact['id'], 'happened_at': '2020-01-01T12:00:00Z',
                'kind': 'meeting', 'summary': 'Synthetic self-reported interaction'},
                expected_contact_version=1, actor='test', key='interaction')
        definition = {'entity': 'contacts', 'columns': ['id', 'last_logged_contact_at', 'open_followup_count'],
            'filter': {'field': 'id', 'op': 'eq', 'value': contact['id']}}
        before = ReportEngine(crm).run(definition)['items']
        assert before[0]['last_logged_contact_at'] == ('2020-01-01T12:00:00.000000+00:00' if logged else None)
        store = ResearchStore(crm)
        evidence = store.submit(packet(contact), key='evidence')
        proposal = store.propose({'evidence_id': evidence['id'], 'evidence_digest': evidence['digest'],
            'evidence_lifecycle_version': 1, 'target_version': 1, 'addition': 'A reviewed source claim'}, key='proposal')
        # Proposal preparation does not edit the target at all.
        assert crm.get('contacts', contact['id'])['updated_at'] == contact['updated_at']
        monkeypatch.setattr('hermes_crm.research_store.now', lambda: '2030-01-01T12:00:00.000000+00:00')
        receipt = store.review(proposal['id'], review(proposal), apply=True, key='apply')
        current = crm.get('contacts', contact['id'])
        assert current['version'] == 2
        assert current['updated_at'] == receipt['recorded_at'] != contact['updated_at']
        assert ReportEngine(crm).run(definition)['items'] == before
        assert crm.get('tasks', task['id'])['status'] == 'open'
        assert crm.get('tasks', task['id'])['version'] == task['version']
        assert store.review(proposal['id'], review(proposal), apply=True, key='apply') == receipt
        assert ReportEngine(crm).run(definition)['items'] == before
    finally:
        crm.close()
