"""Governor test database: exact catalog DDL, exact market-table structure, synthetic rows.

Catalog DDL comes verbatim from the applied migration 20260922_001; market tables use the
columns, keys, and indexes of the live-generated DATABASE_SCHEMA.md. Catalog rows follow the
same seeding rules as the live migration, plus crafted policy cases. Rows are synthetic.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "database/migrations"
CATALOG_MIGRATION = MIGRATIONS / "20260922_001_create_ai_catalogs.sql"
READER_MIGRATION = MIGRATIONS / "20260923_005_create_market_ai_sql_reader.sql"
SCHEMA_DOC = REPO_ROOT / "DATABASE_SCHEMA.md"

MARKET_TABLES = (
    "Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
    "IDX_Broker_Profile", "IDX_Broker_Summary", "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX",
)
# time_column, entity_column, category: exactly as seeded by the live migration
TABLE_META = {
    "IDX_Broker_Summary": ("Date", "Symbol", "TRANSACTIONAL"),
    "IDX_Stock_Universe": (None, "Ticker", "REFERENCE"),
    "IDX_Broker_Profile": (None, "broker_code", "REFERENCE"),
    "Feature_01_Stock_Daily": ("date", "ticker", "FEATURE"),
    "Feature_02_Broker_Rolling": ("date", "ticker", "FEATURE"),
    "Feature_03_Stock_Broker_Daily": ("date", "ticker", "FEATURE"),
    "Price_Stock_Indonesia_IDX": ("date", "ticker", "TRANSACTIONAL"),
}
NUMERIC = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
TICKERS = ["BBCA", "BBRI", "BMRI", "TLKM", "ASII"] + [f"T{index:03d}" for index in range(1, 26)]
BROKERS = ["AK", "BK", "CC"]
KINDS = ["Domestic", "Foreign"]
FIRST_DAY, LAST_DAY = "2025-01-02", "2026-08-31"

TRIGGER_FUNCTION_STUB = '''
CREATE FUNCTION public.set_database_catalog_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END $$;
'''


def catalog_ddl() -> str:
    text = CATALOG_MIGRATION.read_text()
    return text[text.index('CREATE TABLE public."AI_table_catalog"'):text.index("WITH requested(")]


def relationships_sql() -> str:
    text = CATALOG_MIGRATION.read_text()
    start = text.index('INSERT INTO public."AI_catalog_relationships"')
    return text[start:text.index(";", start) + 1]


def _section(table: str) -> str:
    text = SCHEMA_DOC.read_text()
    start = text.index(f"\n## {table}\n")
    return text[start:text.find("\n## ", start + 5)]


def columns(table: str) -> list[tuple[str, str, bool]]:
    return [(name, kind, nullable == "Yes") for name, kind, nullable in
            re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| (Yes|No) \|", _section(table), re.M)]


def primary_key(table: str) -> list[str]:
    match = re.search(r"`PRIMARY KEY \(([^)]*)\)`", _section(table))
    return [part.strip().strip('"') for part in match.group(1).split(",")]


def table_ddl(table: str) -> str:
    body = ",\n  ".join(f'"{n}" {k}{"" if nullable else " NOT NULL"}' for n, k, nullable in columns(table))
    key = ", ".join(f'"{n}"' for n in primary_key(table))
    indexes = [s for s in re.findall(r"`(CREATE (?:UNIQUE )?INDEX [^`]+)`", _section(table)) if "_pkey" not in s]
    return f'CREATE TABLE public."{table}" (\n  {body},\n  PRIMARY KEY ({key})\n);\n' + "".join(i + ";\n" for i in indexes)


KEY_EXPRESSIONS = {
    "ticker": "tk.v", "Symbol": "tk.v", "Ticker": "tk.v", "date": "d.v", "Date": "d.v",
    "broker": "br.v", "Broker": "br.v", "broker_code": "br.v", "investor_type": "iv.v",
    "Investor Type": "iv.v", "market_board": "'RG'", "Market Board": "'RG'",
}
SOURCES = {
    "Price_Stock_Indonesia_IDX": ("tk", "d"), "Feature_01_Stock_Daily": ("tk", "d"),
    "Feature_03_Stock_Broker_Daily": ("tk", "d"), "Feature_02_Broker_Rolling": ("tk", "d", "br", "iv"),
    "IDX_Broker_Summary": ("tk", "d", "br", "iv"), "IDX_Stock_Universe": ("tk",), "IDX_Broker_Profile": ("br",),
}


def _value(table: str, name: str, kind: str) -> str:
    if name in KEY_EXPRESSIONS and (name != "date" or "d" in SOURCES[table]):
        return KEY_EXPRESSIONS[name]
    seed = "hashtext(" + " || ".join(
        {"tk": "tk.v", "d": "d.v::text", "br": "br.v", "iv": "iv.v"}[s] for s in SOURCES[table]) + f" || '{name}')"
    if kind in ("numeric", "double precision", "real"):
        return f"(1000 + abs({seed}) % 9000 + (abs({seed}) % 100) / 100.0)::{kind}"
    if kind in ("smallint", "integer", "bigint"):
        return f"(abs({seed}) % 20)::{kind}"
    if kind == "date":
        return "DATE '2026-09-01'"
    if kind.startswith("timestamp"):
        return "TIMESTAMPTZ '2026-09-01 00:00:00+00'"
    return f"'{name[:12]}-' || (abs({seed}) % 5)"


def market_insert(table: str) -> str:
    exprs = ", ".join(_value(table, name, kind) for name, kind, _ in columns(table))
    from_parts = {
        "tk": f"unnest(ARRAY{TICKERS!r}::text[]) AS tk(v)",
        "d": f"(SELECT g::date AS v FROM generate_series(DATE '{FIRST_DAY}', DATE '{LAST_DAY}', interval '1 day') AS g "
             "WHERE extract(isodow FROM g) < 6) AS d",
        "br": f"unnest(ARRAY{BROKERS!r}::text[]) AS br(v)",
        "iv": f"unnest(ARRAY{KINDS!r}::text[]) AS iv(v)",
    }
    sources = " CROSS JOIN ".join(from_parts[s] for s in SOURCES[table])
    return f'INSERT INTO public."{table}" SELECT {exprs} FROM {sources};'


def catalog_rows_sql() -> str:
    statements = []
    for table, (time_col, entity_col, category) in TABLE_META.items():
        pk = primary_key(table)
        statements.append(
            'INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns, '
            "time_column, entity_column, is_active, ai_access_level, coverage_enabled, documentation_status) VALUES "
            f"('{table}', 'Synthetic test table.', '{category}', 'One row per {' x '.join(pk)}', "
            f"ARRAY{pk!r}::text[], {repr(time_col) if time_col else 'NULL'}, '{entity_col}', true, 'BOUNDED_READ', "
            f"{'true' if time_col else 'false'}, 'VERIFIED');")
        for position, (name, kind, nullable) in enumerate(columns(table), 1):
            is_pk = name in pk
            numeric = kind in NUMERIC
            semantic = "TIME" if name == time_col else "IDENTIFIER" if is_pk else "MEASURE" if numeric else "DIMENSION"
            aggs = "ARRAY['SUM','AVG','MIN','MAX']" if numeric and not is_pk else "ARRAY['COUNT','COUNT_DISTINCT']"
            groupable = is_pk or name in (time_col, entity_col) or not numeric
            statements.append(
                'INSERT INTO public."AI_column_catalog" (table_name, column_name, ordinal_position, description, '
                "data_type, semantic_type, nullable, is_primary_key, is_sensitive, ai_allowed, allowed_aggregations, "
                "filter_allowed, group_by_allowed, coverage_required, documentation_status) VALUES "
                f"('{table}', '{name}', {position}, 'Synthetic.', '{kind}', '{semantic}', {str(nullable).lower()}, "
                f"{str(is_pk).lower()}, false, true, {aggs}::text[], true, {str(groupable).lower()}, "
                f"{str(is_pk).lower()}, 'VERIFIED');")
    return "\n".join(statements)


# Crafted policy cases on top of the live-equivalent seed.
POLICY_CASES_SQL = f'''
UPDATE public."AI_column_catalog" SET ai_allowed = false
 WHERE table_name = 'Price_Stock_Indonesia_IDX' AND column_name = 'source';
UPDATE public."AI_column_catalog" SET is_sensitive = true
 WHERE table_name = 'Price_Stock_Indonesia_IDX' AND column_name = 'ingestion_time';
UPDATE public."AI_column_catalog" SET filter_allowed = false
 WHERE table_name = 'Price_Stock_Indonesia_IDX' AND column_name = 'query_date';
UPDATE public."AI_column_catalog" SET allowed_aggregations = ARRAY['SUM','AVG','MEDIAN','MIN','MAX']
 WHERE table_name = 'Price_Stock_Indonesia_IDX' AND column_name = 'volume';

CREATE TABLE public."Unapproved_Market_Table" (ticker text PRIMARY KEY, secret_value numeric);
CREATE TABLE public."Table_Catalog" (table_schema text, table_name text);
CREATE TABLE public."Analysis_Request" (request_id text PRIMARY KEY, question text);
INSERT INTO public."Unapproved_Market_Table" VALUES ('BBCA', 42);
CREATE TABLE public."Catalog_Only_Table" (ticker text PRIMARY KEY, note text);
CREATE TABLE public."Inactive_Table" (ticker text PRIMARY KEY);
CREATE TABLE public."Denied_Table" (ticker text PRIMARY KEY);
INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns,
    time_column, entity_column, is_active, ai_access_level, coverage_enabled, documentation_status) VALUES
 ('Catalog_Only_Table', 'Catalog-approved but no database grant (layer-2 test).', 'REFERENCE', 'ticker',
  ARRAY['ticker'], NULL, 'ticker', true, 'BOUNDED_READ', false, 'VERIFIED'),
 ('Inactive_Table', 'Inactive.', 'REFERENCE', 'ticker', ARRAY['ticker'], NULL, 'ticker', false, 'BOUNDED_READ',
  false, 'VERIFIED'),
 ('Denied_Table', 'Denied.', 'REFERENCE', 'ticker', ARRAY['ticker'], NULL, 'ticker', true, 'DENIED', false, 'VERIFIED');
INSERT INTO public."AI_column_catalog" (table_name, column_name, ordinal_position, description, data_type,
    semantic_type, nullable, is_primary_key, allowed_aggregations, group_by_allowed, documentation_status) VALUES
 ('Catalog_Only_Table', 'ticker', 1, 'Ticker.', 'text', 'IDENTIFIER', false, true, ARRAY['COUNT'], true, 'VERIFIED'),
 ('Inactive_Table', 'ticker', 1, 'Ticker.', 'text', 'IDENTIFIER', false, true, ARRAY['COUNT'], true, 'VERIFIED'),
 ('Denied_Table', 'ticker', 1, 'Ticker.', 'text', 'IDENTIFIER', false, true, ARRAY['COUNT'], true, 'VERIFIED');

INSERT INTO public."AI_catalog_relationships" (left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain, requires_preaggregation, description, version, is_allowed)
VALUES ('Feature_01_Stock_Daily', ARRAY['ticker','date'], 'Feature_03_Stock_Broker_Daily', ARRAY['ticker','date'],
        'ONE_TO_MANY', 'Exact trading date', 'date x ticker', false, 'Disallowed for testing.', 'v1', false);

INSERT INTO public."AI_data_coverage" (dataset_name, coverage_scope, coverage_mode, actual_min_date,
    actual_max_date, expected_min_date, expected_max_date, pipeline_status, verification_status, quality_status,
    last_checked_at) VALUES
 ('Price_Stock_Indonesia_IDX', 'DATASET', 'ACTUAL_SOURCE', DATE '{FIRST_DAY}', DATE '{LAST_DAY}', NULL, NULL,
  'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', now()),
 ('IDX_Broker_Summary', 'DATASET', 'ACTUAL_SOURCE', DATE '{FIRST_DAY}', DATE '{LAST_DAY}', NULL, NULL,
  'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', now()),
 ('Feature_01_Stock_Daily', 'DATASET', 'EXPECTED_DERIVED', NULL, NULL, DATE '{FIRST_DAY}', DATE '{LAST_DAY}',
  'NOT_FULLY_CONFIRMED', 'UNVERIFIED', 'WARNING', now()),
 ('Feature_02_Broker_Rolling', 'DATASET', 'EXPECTED_DERIVED', NULL, NULL, DATE '{FIRST_DAY}', DATE '{LAST_DAY}',
  'MANUAL_REFRESH_REQUIRED', 'UNVERIFIED', 'WARNING', now()),
 ('Feature_03_Stock_Broker_Daily', 'DATASET', 'EXPECTED_DERIVED', NULL, NULL, DATE '{FIRST_DAY}', DATE '{LAST_DAY}',
  'MANUAL_REFRESH_REQUIRED', 'UNVERIFIED', 'WARNING', now());
'''
