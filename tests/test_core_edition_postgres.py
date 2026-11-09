"""Exact core upgrade fixture on an explicit disposable PostgreSQL schema."""
import hashlib
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM
import test_core_edition as contracts

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def source():
    schema = 'crm_core_test_' + uuid.uuid4().hex
    crm = None
    try:
        crm = CRM(URL, schema=schema, profile='Équipe')
        scope = hashlib.sha256(json.dumps([crm.workspace_token(), crm.profile],
            sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
        contracts.seed_legacy(crm, scope)
        yield crm
    finally:
        if crm:
            crm.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


def test_preserved_legacy_export_quarantine(source, tmp_path):
    contracts.test_core_upgrade_crud_export_and_restore_preserve_legacy_evidence(source, tmp_path)


def test_partial_schema_fails_closed(source):
    contracts.test_partial_legacy_schema_fails_closed_on_export(source)


@pytest.mark.parametrize('damage', ['missing_table', 'extra_column', 'extra_unique'])
def test_legacy_schema_fails_closed(source, damage):
    contracts.test_legacy_history_export_rejects_incomplete_or_incompatible_schema(source, damage)
