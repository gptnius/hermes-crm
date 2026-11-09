"""Run exact relationship detail contracts on an explicit disposable PostgreSQL."""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM
import test_relationship_detail_reads as contracts

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def crm():
    schema = 'crm_detail_test_' + uuid.uuid4().hex
    instance = None
    try:
        instance = CRM(URL, schema=schema, profile='detail-test')
        yield instance
    finally:
        if instance:
            instance.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_exact_fields(crm, kind):
    contracts.test_exact_fields_are_read_only_and_current(crm, kind)


def test_event_lifecycle(crm):
    contracts.test_event_null_completion_and_reopen(crm)


def test_archive(crm):
    contracts.test_archived_company_notes_remain_readable(crm)


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_absent_schema(crm, kind):
    contracts.test_missing_records_and_uninitialized_reads_do_not_write(crm, kind)


@pytest.mark.parametrize('kind', ['companies', 'events'])
def test_scope(crm, kind):
    contracts.test_profile_and_workspace_marker_isolation(crm, kind)


@pytest.mark.parametrize('kind', ['companies', 'events'])
@pytest.mark.parametrize('damage', ['partial', 'version', 'column'])
def test_invalid_schema(crm, kind, damage):
    contracts.test_malformed_relationship_schema_fails_closed(crm, kind, damage)
