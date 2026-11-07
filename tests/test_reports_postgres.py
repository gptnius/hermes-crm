"""Flexible report parity against an explicitly selected disposable PostgreSQL database."""
import os
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.schema import DropSchema
from hermes_crm.domain import CRM
from hermes_crm.reports import ReportEngine
import test_flexible_reports as contracts

URL = os.getenv('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')

@pytest.fixture
def setup():
    schema='crm_test_'+uuid.uuid4().hex
    crm=None
    try:
        crm=CRM(URL,schema=schema,profile='reports-portability-test')
        assert crm.backend=='postgres'
        yield crm,ReportEngine(crm)
    finally:
        if crm: crm.close()
        engine=create_engine(URL)
        try:
            with engine.begin() as conn: conn.execute(DropSchema(schema,cascade=True,if_exists=True))
        finally: engine.dispose()

CONTRACTS=[getattr(contracts,name) for name in dir(contracts)
           if name.startswith('test_') and name!='test_rejects_invalid']

@pytest.mark.parametrize('check',CONTRACTS,ids=lambda f:f.__name__)
def test_live_postgres_flexible_reports(setup,check):
    check(setup)
