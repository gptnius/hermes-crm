"""Database-free check of names used by opt-in PostgreSQL fixtures."""
import re
from test_report_reviews_postgres import disposable_schema_name


def test_disposable_schema_name_matches_domain_allowlist():
    names={disposable_schema_name() for _ in range(100)}
    assert len(names)==100
    assert all(re.fullmatch(r'crm_[a-z0-9_]{1,48}',name) for name in names)


def test_incompatible_column_ddl_uses_dialect_quoted_schema():
    from sqlalchemy.dialects import postgresql, sqlite
    from test_report_reviews import incompatible_column_sql
    suffix = 'crm_report_review_events_v1 ADD COLUMN future_contract TEXT'
    assert incompatible_column_sql(sqlite.dialect(), None) == 'ALTER TABLE ' + suffix
    assert incompatible_column_sql(postgresql.dialect(), 'crm_review_test_example') == 'ALTER TABLE crm_review_test_example.' + suffix
    assert incompatible_column_sql(postgresql.dialect(), 'odd"schema') == 'ALTER TABLE "odd""schema".' + suffix
