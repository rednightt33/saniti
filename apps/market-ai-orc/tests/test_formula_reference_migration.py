"""Ensure the public migration does not publish private formula workbook records."""

from pathlib import Path


MIGRATION = (Path(__file__).resolve().parents[3]
             / "database/migrations/20260924_003_create_ai_formula_reference.sql")


def test_formula_migration_is_schema_only_and_grants_catalog_reader() -> None:
    sql = MIGRATION.read_text()
    assert 'CREATE TABLE public."AI_formula_reference"' in sql
    assert 'INSERT INTO public."AI_formula_reference"' not in sql
    assert 'GRANT SELECT ON public."AI_formula_reference" TO market_ai_catalog_reader' in sql
    assert 'TO market_ai_sql_reader' not in sql
