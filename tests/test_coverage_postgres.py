"""Actual PostgreSQL storage for synthetic coverage contracts; no host jobs.

Uses only explicit disposable HERMES_CRM_TEST_POSTGRES_URL and random schemas.
"""
import pytest

from hermes_crm.domain import CRM
from hermes_crm.native_work import NativeWorkStore
from test_native_work_postgres import crm_factory, setup, URL
import test_coverage as contract

pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def fresh_crm(crm_factory):
    return crm_factory()


for _name, _check in vars(contract).items():
    if _name.startswith('test_') and callable(_check) and _name != 'test_coverage_read_does_not_initialize_assignment_tables':
        globals()['test_postgres_' + _name[5:]] = _check


def test_postgres_read_does_not_initialize_native_tables(fresh_crm):
    from sqlalchemy import inspect
    from hermes_crm.coverage import coverage_report
    crm = fresh_crm
    crm.workspace_token()
    crm.create('tasks', {'title': 'Human follow-up', 'due_at': '2030-01-01T00:00:00Z'})
    schema = crm.engine.get_execution_options()['schema_translate_map'][None]
    before = set(inspect(crm.engine).get_table_names(schema=schema))
    assert coverage_report(crm)['total'] == 1
    assert NativeWorkStore(crm, initialize=False).page()['total'] == 0
    assert set(inspect(crm.engine).get_table_names(schema=schema)) == before
