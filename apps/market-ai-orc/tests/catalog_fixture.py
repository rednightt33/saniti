"""Catalog test fixture: exact DDL from the live migration plus crafted visibility cases."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CATALOG_MIGRATION = REPO_ROOT / "database/migrations/20260922_001_create_ai_catalogs.sql"
READER_MIGRATION = REPO_ROOT / "database/migrations/20260923_001_create_market_ai_catalog_reader.sql"
RESEARCH_MIGRATION = REPO_ROOT / "database/migrations/20260924_001_create_ai_research_catalog.sql"

TRIGGER_FUNCTION_STUB = '''
CREATE FUNCTION public.set_database_catalog_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END $$;
'''


def catalog_ddl() -> str:
    """The CREATE TABLE/INDEX/TRIGGER/COMMENT block of the applied migration, verbatim."""
    text = CATALOG_MIGRATION.read_text()
    start = text.index('CREATE TABLE public."AI_table_catalog"')
    end = text.index("WITH requested(")
    return text[start:end]


def research_catalog_ddl() -> str:
    """The new table and comments, without private workbook records or catalog metadata."""
    text = RESEARCH_MIGRATION.read_text()
    return text[text.index('CREATE TABLE public."AI_research_catalog"'):text.index('-- The orchestrator catalog login')]


RESEARCH_FIXTURE_SQL = '''
INSERT INTO public."AI_research_catalog" (
    method_id, method_name, category, purpose, example_question, analysis_kind, input_grain,
    required_inputs_json, optional_inputs_json, future_outcome_required, supports_numeric_directly,
    preprocessing, parameter_keys_json, expected_outputs_json, validation_requirements_json,
    main_risks, compute_strategy, tool_or_library_examples, implementation_status
) VALUES (
    'example_method', 'Example method', 'descriptive', 'Synthetic test only', 'Example?', 'descriptive',
    'entity x date', '["entity_id","date","value"]', '[]', false, true, 'Sort rows', '[]',
    '["value"]', '["coverage"]', 'No production method claims', 'Test only', 'None', 'REFERENCE_ONLY'
);
'''


FIXTURE_SQL = '''
INSERT INTO public."AI_table_catalog" (table_name, description, category, grain, primary_key_columns,
    time_column, entity_column, is_active, ai_access_level, freshness_sla, coverage_enabled,
    documentation_status) VALUES
 ('IDX_Broker_Summary', 'Daily broker activity by stock, investor type and board.', 'TRANSACTIONAL',
  'Date x Symbol x Broker x Investor Type x Market Board',
  ARRAY['Date','Symbol','Broker','Investor Type','Market Board'], 'Date', 'Symbol', true, 'BOUNDED_READ',
  interval '1 day', true, 'VERIFIED'),
 ('Feature_02_Broker_Rolling', 'Validated daily and rolling broker flows.', 'FEATURE',
  'date x ticker x broker x investor_type x market_board',
  ARRAY['date','ticker','broker','investor_type','market_board'], 'date', 'ticker', true, 'BOUNDED_READ',
  interval '1 day', true, 'VERIFIED'),
 ('Feature_03_Stock_Broker_Daily', 'Stock-level daily broker breadth and flows.', 'FEATURE',
  'date x ticker x market_board', ARRAY['date','ticker','market_board'], 'date', 'ticker', true,
  'BOUNDED_READ', interval '1 day', true, 'VERIFIED'),
 ('IDX_Broker_Profile', 'Broker identity and classification.', 'REFERENCE', 'One row per broker',
  ARRAY['broker_code'], NULL, 'broker_code', true, 'BOUNDED_READ', interval '365 days', false, 'PARTIAL'),
 ('Hidden_Inactive_Table', 'Must never be exposed (inactive).', 'REFERENCE', 'n/a', ARRAY['id'], NULL,
  'id', false, 'BOUNDED_READ', NULL, true, 'VERIFIED'),
 ('Denied_Table', 'Must never be exposed (denied).', 'REFERENCE', 'n/a', ARRAY['id'], NULL, 'id', true,
  'DENIED', NULL, true, 'VERIFIED');

INSERT INTO public."AI_column_catalog" (table_name, column_name, ordinal_position, description, data_type,
    semantic_type, unit, nullable, is_primary_key, source_column_or_expression, is_sensitive, ai_allowed,
    allowed_aggregations, filter_allowed, group_by_allowed, example_value, coverage_required,
    documentation_status) VALUES
 ('IDX_Broker_Summary','Date',1,'Transaction date.','date','TIME',NULL,false,true,NULL,false,true,
  ARRAY['COUNT','COUNT_DISTINCT'],true,true,NULL,true,'VERIFIED'),
 ('IDX_Broker_Summary','Investor Type',4,'Source investor type: Domestic or Foreign.','text','DIMENSION',
  NULL,false,true,NULL,false,true,ARRAY['COUNT','COUNT_DISTINCT'],true,true,NULL,true,'VERIFIED'),
 ('IDX_Broker_Summary','Undocumented Field',9,NULL,'text','DIMENSION',NULL,true,false,NULL,false,true,
  ARRAY['COUNT'],true,false,NULL,false,'NEEDS_REVIEW'),
 ('IDX_Broker_Summary','Internal Note',10,'Must be hidden (ai_allowed=false).','text','DIMENSION',NULL,
  true,false,NULL,false,false,ARRAY['COUNT'],true,false,NULL,false,'VERIFIED'),
 ('IDX_Broker_Summary','Account Holder',11,'Must be hidden (sensitive).','text','DIMENSION',NULL,true,
  false,NULL,true,true,ARRAY['COUNT'],true,false,NULL,false,'VERIFIED'),
 ('Feature_02_Broker_Rolling','net_value_1d',9,'Buy value minus sell value.','numeric','MEASURE','IDR',
  false,false,'Buy Value - Sell Value',false,true,ARRAY['SUM','AVG','MIN','MAX'],true,false,NULL,false,
  'VERIFIED'),
 ('Feature_02_Broker_Rolling','net_value_20d',14,'Sum of net_value_1d over 20 ticker transaction dates.',
  'numeric','MEASURE','IDR',true,false,'net_value_1d',false,true,ARRAY['SUM','AVG'],true,false,NULL,false,
  'VERIFIED'),
 ('Hidden_Inactive_Table','id',1,'hidden','text','IDENTIFIER',NULL,false,true,NULL,false,true,
  ARRAY['COUNT'],true,true,NULL,false,'VERIFIED');

INSERT INTO public."AI_catalog_relationships" (left_table, left_columns, right_table, right_columns,
    relationship_type, temporal_rule, safe_output_grain, requires_preaggregation, description, version,
    is_allowed) VALUES
 ('IDX_Broker_Summary', ARRAY['Date','Symbol','Broker','Investor Type','Market Board'],
  'Feature_02_Broker_Rolling', ARRAY['date','ticker','broker','investor_type','market_board'],
  'ONE_TO_ONE','Exact source trading date','date x ticker x broker x investor_type x market_board',false,
  'Broker Summary source row to its canonical Feature 02 daily identity.','v1',true),
 ('Feature_02_Broker_Rolling', ARRAY['ticker','date','market_board'],
  'Feature_03_Stock_Broker_Daily', ARRAY['ticker','date','market_board'],
  'MANY_TO_ONE','Exact trading date and market board','date x ticker x market_board',true,
  'Feature 02 must be aggregated across broker and investor type before joining Feature 03.','v1',true),
 ('IDX_Broker_Profile', ARRAY['broker_code'], 'IDX_Broker_Summary', ARRAY['Broker'],
  'ONE_TO_MANY','Current-state broker metadata','Broker Summary primary-key grain',false,
  'Disallowed relationship; must be hidden.','v1',false),
 ('Denied_Table', ARRAY['id'], 'IDX_Broker_Summary', ARRAY['Symbol'],
  'ONE_TO_MANY','n/a','n/a',false,'Touches a denied table; must be hidden.','v1',true);

INSERT INTO public."AI_calculation_catalog" (calculation_name, version, target_table, target_columns,
    definition, required_inputs, parameters, defaults, implementation_ref, alignment_rules,
    missing_data_policy, output_definition, validation_evidence, status) VALUES
 ('net_value_20d','v2','Feature_02_Broker_Rolling',ARRAY['net_value_20d'],
  'Sum of net_value_1d over 20 ticker transaction dates; missing activity contributes zero.',
  '{"source_tables":["IDX_Broker_Summary"],"source_columns":["Buy Value","Sell Value"]}',
  '{"lookback_window":"20 ticker transaction dates","minimum_history":null}','{}',
  ARRAY['database/migrations/x.sql'],'Ticker transaction-date calendar across boards.',
  'NULL until 20 dates exist.','{"unit":"IDR","semantic_role":"MEASURE"}',ARRAY['evidence/a.md'],'ACTIVE'),
 ('net_value_1d','v2','Feature_02_Broker_Rolling',ARRAY['net_value_1d'],
  'Buy value minus sell value.','{"source_tables":["IDX_Broker_Summary"]}','{}','{}',
  ARRAY['database/migrations/x.sql'],'Same date.','Never NULL.','{"unit":"IDR"}',ARRAY['evidence/b.md'],
  'ACTIVE'),
 ('net_value_1d','v1','Feature_02_Broker_Rolling',ARRAY['net_value_1d'],'Retired v1 definition.','{}',
  '{}','{}',ARRAY['old.sql'],'n/a','n/a','{}',ARRAY['old.md'],'INACTIVE');

INSERT INTO public."AI_data_coverage" (dataset_name, coverage_scope, entity_id, reference_dataset_name,
    coverage_mode, actual_min_date, actual_max_date, expected_min_date, expected_max_date,
    source_row_count, source_key_count, pipeline_status, verification_status, quality_status,
    check_error, last_checked_at, last_full_checked_at) VALUES
 ('IDX_Broker_Summary','DATASET',NULL,NULL,'ACTUAL_SOURCE','2018-01-02','2026-08-31',NULL,NULL,1000,2,
  'SOURCE_OBSERVED','VERIFIED','HEALTHY',NULL,'2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('IDX_Broker_Summary','ENTITY','BBCA',NULL,'ACTUAL_SOURCE','2018-01-02','2026-08-31',NULL,NULL,600,1,
  'SOURCE_OBSERVED','VERIFIED','HEALTHY',NULL,'2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('IDX_Broker_Summary','ENTITY','BBRI',NULL,'ACTUAL_SOURCE','2019-01-02','2026-08-31',NULL,NULL,400,1,
  'SOURCE_OBSERVED','VERIFIED','HEALTHY',NULL,'2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('Feature_02_Broker_Rolling','DATASET',NULL,'IDX_Broker_Summary','EXPECTED_DERIVED',NULL,NULL,
  '2018-01-02','2026-08-31',1000,2,'MANUAL_REFRESH_REQUIRED','UNVERIFIED','WARNING',NULL,
  '2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('Feature_02_Broker_Rolling','ENTITY','BBCA','IDX_Broker_Summary','EXPECTED_DERIVED',NULL,NULL,
  '2018-01-02','2026-08-31',600,1,'MANUAL_REFRESH_REQUIRED','UNVERIFIED','WARNING',NULL,
  '2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('Feature_02_Broker_Rolling','ENTITY','BBRI','IDX_Broker_Summary','EXPECTED_DERIVED',NULL,NULL,
  '2019-01-02','2026-08-31',400,1,'MANUAL_REFRESH_REQUIRED','UNVERIFIED','WARNING',NULL,
  '2026-09-22T00:30:00Z','2026-09-22T00:30:00Z'),
 ('IDX_Broker_Profile','DATASET',NULL,NULL,'SNAPSHOT',NULL,NULL,NULL,NULL,90,90,'SOURCE_OBSERVED',
  'VERIFIED','HEALTHY',NULL,'2026-09-22T00:30:00Z','2026-09-22T00:30:00Z');
'''

# Tables the reader migration must NOT expose; created so the least-privilege check has targets.
MARKET_DATA_STUBS = '''
CREATE TABLE public."Feature_02_Broker_Rolling" (ticker text, net_value_1d numeric);
CREATE TABLE public."IDX_Broker_Summary" ("Symbol" text, "Buy Value" numeric);
CREATE TABLE public."Table_Catalog" (table_name text);
'''


# --- Market-data tables for the preview interface -------------------------------------------------
import re as _re

SCHEMA_DOC = REPO_ROOT / "DATABASE_SCHEMA.md"
PREVIEW_MIGRATION = REPO_ROOT / "database/migrations/20260923_002_create_market_ai_preview_interface.sql"
MARKET_TABLES = (
    "Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily",
    "IDX_Broker_Profile", "IDX_Broker_Summary", "IDX_Stock_Universe", "Price_Stock_Indonesia_IDX",
)


def _schema_section(table: str) -> str:
    text = SCHEMA_DOC.read_text()
    start = text.index(f"\n## {table}\n")
    end = text.find("\n## ", start + 5)
    return text[start:end]


def market_columns(table: str) -> list[tuple[str, str, bool]]:
    """(name, type, nullable) exactly as generated from the live database."""
    return [
        (name, data_type, nullable == "Yes")
        for name, data_type, nullable in _re.findall(
            r"^\| `([^`]+)` \| `([^`]+)` \| (Yes|No) \|", _schema_section(table), _re.M
        )
    ]


def market_primary_key(table: str) -> list[str]:
    match = _re.search(r"`PRIMARY KEY \(([^)]*)\)`", _schema_section(table))
    return [part.strip().strip('"') for part in match.group(1).split(",")]


def market_table_ddl(table: str) -> str:
    """CREATE TABLE plus the non-primary-key indexes, verbatim from the live-generated schema."""
    columns = ",\n  ".join(
        f'"{name}" {data_type}{"" if nullable else " NOT NULL"}'
        for name, data_type, nullable in market_columns(table)
    )
    key = ", ".join(f'"{name}"' for name in market_primary_key(table))
    indexes = [
        statement for statement in _re.findall(r"`(CREATE (?:UNIQUE )?INDEX [^`]+)`", _schema_section(table))
        if "_pkey" not in statement
    ]
    return (f'CREATE TABLE public."{table}" (\n  {columns},\n  PRIMARY KEY ({key})\n);\n'
            + "".join(statement + ";\n" for statement in indexes))


def _value_expression(name: str, data_type: str, nullable: bool, key: list[str]) -> str:
    """Deterministic synthetic values; primary keys stay unique because one text key uses g."""
    if data_type == "date":
        return "(date '2026-08-01' + (g % 7))"
    if name in key and data_type in ("text", "character varying"):
        return f"('{name[:1].upper()}' || lpad(g::text, 6, '0'))"
    if data_type in ("text", "character varying"):
        return "NULL" if nullable else f"('{name}-' || (g % 3))"
    if data_type == "smallint":
        return "(g % 20)::smallint"
    if data_type == "numeric":
        return "NULL" if nullable and name.endswith("_60d") else "(g * 1000.25)::numeric"
    if data_type == "double precision":
        return "(g * 0.125)::double precision"
    if data_type == "timestamp with time zone":
        return "timestamptz '2026-09-22 00:00:00+00'"
    raise AssertionError(f"unhandled type {data_type}")


def market_insert(table: str, rows: int) -> str:
    key = market_primary_key(table)
    expressions = ", ".join(
        _value_expression(name, data_type, nullable, key) for name, data_type, nullable in market_columns(table)
    )
    return f'INSERT INTO public."{table}" SELECT {expressions} FROM generate_series(1, {rows}) AS g;'


# Row counts: >20 everywhere except IDX_Broker_Profile (5) to exercise the fewer-than-20 case.
MARKET_ROWS = {
    "Feature_01_Stock_Daily": 60, "Feature_02_Broker_Rolling": 60, "Feature_03_Stock_Broker_Daily": 60,
    "IDX_Broker_Profile": 5, "IDX_Broker_Summary": 60, "IDX_Stock_Universe": 30,
    "Price_Stock_Indonesia_IDX": 60,
}
