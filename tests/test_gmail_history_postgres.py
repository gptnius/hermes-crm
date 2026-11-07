"""Opt-in disposable PostgreSQL tests; provider responses remain synthetic."""
import os
import uuid
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM, CRMError
from hermes_crm.gmail_history import GmailHistoryStore, observations, snapshots
import test_gmail_history_storage as contract

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def setup(monkeypatch):
    schema = 'crm_test_' + uuid.uuid4().hex
    monkeypatch.setenv('HERMES_CRM_POSTGRES_SCHEMA', schema)
    crm = CRM(URL, schema=schema, profile='synthetic')
    contact = crm.create('contacts', {'name': 'Contact', 'email': 'contact@example.test'})
    store = GmailHistoryStore(crm, initialize=True)
    yield crm, store, contract.Reader(), contact
    crm.close()
    engine = create_engine(URL)
    try:
        with engine.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True, if_exists=True))
    finally:
        engine.dispose()

EXCLUDED = {'test_lazy_gets_create_no_tables', 'test_postgres_ddl_compiles_without_sqlite_specific_constructs',
            'test_atomic_publish_failure_leaves_old_evidence', 'test_schema_mismatch_rejected_without_migration'}
for name, check in vars(contract).items():
    if name.startswith('test_') and callable(check) and name not in EXCLUDED:
        globals()['test_pg_' + name[5:]] = check


def test_pg_publish_rollback(setup):
    crm, store, reader, contact = setup
    contract.verify(setup); contract.sync(setup)
    def fail(connection, cursor, statement, parameters, context, many):
        compiled = getattr(context, 'compiled', None)
        stmt = getattr(compiled, 'statement', None)
        if getattr(stmt, 'is_insert', False) and getattr(stmt, 'table', None) is observations:
            raise RuntimeError('Synthetic persistence failure')
    event.listen(crm.engine, 'before_cursor_execute', fail)
    try:
        assert contract.sync(setup)['state'] == 'failed'
    finally:
        event.remove(crm.engine, 'before_cursor_execute', fail)
    assert contract.count(crm, observations) == 1 and contract.count(crm, snapshots) == 1


def test_pg_schema_mismatch_rejected(setup):
    crm, *_ = setup
    schema = crm.engine.get_execution_options()['schema_translate_map'][None]
    with crm.engine.begin() as conn:
        conn.execute(text(f'ALTER TABLE "{schema}".crm_gmail_connections ADD COLUMN unexpected TEXT'))
    with pytest.raises(CRMError, match='explicit migration'):
        GmailHistoryStore(crm, initialize=True)
