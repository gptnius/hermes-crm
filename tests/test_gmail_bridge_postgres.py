"""Explicit disposable PostgreSQL URL only; never starts a database."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
from hermes_crm.gmail_bridge_store import GmailBridgeStore
import test_gmail_bridge_store as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def setup(monkeypatch):
    schema = 'crm_test_' + uuid.uuid4().hex
    monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
    crm = CRM(URL, schema=schema, profile='synthetic')
    contact = crm.create('contacts', {'name': 'Contact', 'email': 'contact@example.test'})
    yield crm, GmailBridgeStore(crm), contact
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
