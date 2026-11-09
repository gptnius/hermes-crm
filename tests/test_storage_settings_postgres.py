"""Explicit disposable PostgreSQL only; never infer a configured user database."""
import asyncio
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from hermes_crm import storage_settings as storage

URL = os.environ.get('HERMES_CRM_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires explicit disposable PostgreSQL URL')


def test_real_probe_closes_connection_and_creates_no_schema(monkeypatch):
    for key in tuple(os.environ):
        if key.startswith('PG'): monkeypatch.delenv(key)
    name = 'crm_probe_fixture_' + uuid.uuid4().hex
    parsed = make_url(URL).update_query_dict({'application_name': name})
    # The diagnostic deliberately requires an explicit password even if the
    # disposable fixture accepts trust auth. This value belongs only to QA.
    if not parsed.password:
        parsed = parsed.set(password='disposable-fixture-only')
    url = parsed.render_as_string(hide_password=False)
    engine = create_engine(URL)
    try:
        with engine.connect() as connection:
            before = connection.execute(text('SELECT nspname FROM pg_namespace ORDER BY nspname')).scalars().all()
        assert asyncio.run(storage._postgres_probe(url)) == 'connected'
        with engine.connect() as connection:
            assert connection.execute(text('SELECT nspname FROM pg_namespace ORDER BY nspname')).scalars().all() == before
            assert connection.execute(text('SELECT count(*) FROM pg_stat_activity WHERE application_name=:name'), {'name':name}).scalar() == 0
    finally:
        engine.dispose()
