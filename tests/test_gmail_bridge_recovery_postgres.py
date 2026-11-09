"""Explicit disposable PostgreSQL source to fresh SQLite bridge recovery."""
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema

from hermes_crm.domain import CRM
import test_gmail_bridge_recovery as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


@pytest.fixture
def source(monkeypatch):
    schema = 'crm_gmail_restore_' + uuid.uuid4().hex
    monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
    crm = None
    try:
        crm = CRM(URL, schema=schema, profile='Équipe')
        crm.workspace_token()
        yield crm
    finally:
        if crm is not None:
            crm.close()
        engine = create_engine(URL)
        try:
            with engine.begin() as conn:
                conn.execute(DropSchema(schema, cascade=True, if_exists=True))
        finally:
            engine.dispose()


for name, check in vars(contract).items():
    if name.startswith('test_') and callable(check):
        globals()['test_pg_' + name[5:]] = check
