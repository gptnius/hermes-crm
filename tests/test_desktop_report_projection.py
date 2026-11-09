"""Exercise the actual-host assertion's allowed view without importing a host."""
import ast
from copy import deepcopy

import pytest
import test_desktop_host as host


def checker():
    tree = ast.parse(host.HOST_CHECK)
    nodes = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
             and node.name == 'assert_contact_report_projection']
    assert len(nodes) == 1
    ns = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<host-report-assertion>', 'exec'), ns)
    return ns['assert_contact_report_projection']


def report():
    row = dict(id='contact', version=2, created_at='2026-01-01T00:00:00Z',
               updated_at='2026-01-02T00:00:00Z', name='Synthetic', email=None,
               company='Example', title='', lifecycle='lead', deal_count=1,
               open_followup_count=2, overdue_followup_count=1,
               next_followup_at='2026-01-03T00:00:00Z', deal_stages=['proposal'])
    agent = dict(total=1, limit=25, offset=0, items=[deepcopy(row)])
    rest = dict(total=1, limit=25, offset=0, items=[dict(row, notes='Ordinary note',
                custom_fields={'private': 'omitted'}, canonical_company={'id': 'company'})])
    return rest, agent


def test_expected_minimized_report_and_metadata():
    rest, agent = report()
    checker()(rest, agent)


@pytest.mark.parametrize('mutation', ['total', 'missing_date', 'leaked_notes',
                                    'leaked_custom', 'stage', 'contact_id'])
def test_parity_still_rejects_wrong_values_and_leaks(mutation):
    rest, agent = report()
    if mutation == 'total': agent['total'] = 2
    if mutation == 'missing_date': agent['items'][0].pop('created_at')
    if mutation == 'leaked_notes': agent['items'][0]['notes'] = rest['items'][0]['notes']
    if mutation == 'leaked_custom': agent['items'][0]['custom_fields'] = {'private': 'omitted'}
    if mutation == 'stage': agent['items'][0]['deal_stages'] = ['won']
    if mutation == 'contact_id': agent['items'][0]['id'] = 'another'
    with pytest.raises(AssertionError): checker()(rest, agent)
