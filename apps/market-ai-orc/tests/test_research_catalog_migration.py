"""Ensure the public migration does not publish private research method records."""

from pathlib import Path


MIGRATION = (Path(__file__).resolve().parents[3]
             / "database/migrations/20260924_001_create_ai_research_catalog.sql")


def test_research_migration_is_schema_only_and_grants_catalog_reader() -> None:
    sql = MIGRATION.read_text()
    assert 'CREATE TABLE public."AI_research_catalog"' in sql
    assert 'INSERT INTO public."AI_research_catalog"' not in sql
    assert 'GRANT SELECT ON public."AI_research_catalog" TO market_ai_catalog_reader' in sql
    assert 'TO market_ai_sql_reader' not in sql
