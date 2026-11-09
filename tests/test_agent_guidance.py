"""Agent guidance should enable requested work without granting new capabilities."""
from hermes_crm.plugin import register
from hermes_crm.native_work import TOOLSETS
from pathlib import Path
import yaml


def descriptions(monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError('Registering guidance must not open a datastore or call the host')
    monkeypatch.setattr('hermes_crm.plugin.open_profile_crm', unexpected)

    class Context:
        profile_name = 'synthetic'
        dispatch_tool = staticmethod(unexpected)

        def __init__(self):
            self.tools = {}

        def register_tool(self, **definition):
            assert definition['name'] not in self.tools
            self.tools[definition['name']] = definition

        def get_config(self, key, default=None):
            return default

    ctx = Context()
    register(ctx)
    assert len(ctx.tools) == 73
    root = Path(__file__).resolve().parents[1]
    advertised = yaml.safe_load((root / 'plugin.yaml').read_text())['provides_tools']
    assert len(advertised) == len(set(advertised)) == 73
    assert set(advertised) == set(ctx.tools)
    assert 'register(ctx) registers 73 tools' in (root / 'docs/HERMES_INTEGRATION.md').read_text()
    return {name: item['schema']['description'] for name, item in ctx.tools.items()}


def test_research_guidance_routes_to_available_tools_and_explicit_review(monkeypatch):
    tools = descriptions(monkeypatch)
    evidence = tools['crm_research_evidence_submit']
    assert 'separately available host research tools' in evidence
    assert 'specific setup or permission needed' in evidence
    assert 'continue permitted work' in evidence
    assert 'does not fetch or verify' in evidence
    assert 'Never submit secrets or private/signed URLs' in evidence
    proposal = tools['crm_research_note_propose']
    assert 'explicit review in the record Research panel' in proposal
    assert 'separate explicit ordinary-record edit request' in proposal
    assert 'current versions and applicable approvals' in proposal


def test_scheduling_guidance_recognizes_request_without_expanding_scope(monkeypatch):
    tools = descriptions(monkeypatch)
    for name in ('crm_followup_schedule', 'crm_work_schedule', 'crm_work_cancel'):
        assert 'request supplies' in tools[name]
        assert 'host-required approval prompts' in tools[name]
    create = tools['crm_work_create']
    assert 'Saves intent only' in create
    assert 'scheduled mode uses existing CRM data only' in create
    assert 'current interactive conversation' in create
    assert 'do not impose this scheduled mode on every user request' in create
    assert tuple(TOOLSETS) == ('crm_read', 'crm_work_read', 'crm_work_report', 'no_mcp')
    assert 'Internal CRM reads and reporting only' in tools['crm_work_schedule']


def test_reduced_reads_point_to_implemented_detail_tool(monkeypatch):
    tools = descriptions(monkeypatch)
    for name in ('crm_contact_get', 'crm_deal_get', 'crm_task_get'):
        assert 'Use crm_record_fields' in tools[name]
    assert 'Cannot access protected notes' in tools['crm_record_fields']
