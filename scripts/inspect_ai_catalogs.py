#!/usr/bin/env python3
"""Read-only inspection of the five AI_* catalog tables (structure, states, sizes, samples).

Runs inside a READ ONLY transaction and only SELECTs catalog metadata, so it works with the
catalog-only market_ai_orc login (CATALOG_DATABASE_URL). No market-data table is read.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal

import psycopg
from psycopg.rows import dict_row


TABLES = (
    "AI_table_catalog", "AI_column_catalog", "AI_catalog_relationships",
    "AI_calculation_catalog", "AI_data_coverage",
)
PATTERNS = tuple(f"%{table}%" for table in TABLES)
STATE_QUERIES = {
    "table_visibility": '''SELECT is_active, ai_access_level, documentation_status, coverage_enabled,
                                  count(*) FROM public."AI_table_catalog" GROUP BY 1,2,3,4 ORDER BY 1,2,3,4''',
    "column_visibility": '''SELECT ai_allowed, is_sensitive, documentation_status, count(*),
                                   count(*) FILTER (WHERE description IS NULL) AS null_description,
                                   count(*) FILTER (WHERE unit IS NULL) AS null_unit,
                                   count(*) FILTER (WHERE example_value IS NULL) AS null_example
                            FROM public."AI_column_catalog" GROUP BY 1,2,3 ORDER BY 1,2,3''',
    "columns_per_table": '''SELECT table_name, count(*), max(length(description)) AS max_description_chars
                            FROM public."AI_column_catalog" GROUP BY 1 ORDER BY 1''',
    "relationship_states": '''SELECT is_allowed, version, count(*) FROM public."AI_catalog_relationships"
                              GROUP BY 1,2 ORDER BY 1,2''',
    "calculation_states": '''SELECT target_table, status, count(*),
                                    max(length(definition)) AS max_definition_chars,
                                    max(length(required_inputs::text) + length(output_definition::text)
                                        + length(alignment_rules) + length(missing_data_policy)) AS max_contract_chars
                             FROM public."AI_calculation_catalog" GROUP BY 1,2 ORDER BY 1,2''',
    "coverage_states": '''SELECT dataset_name, coverage_scope, coverage_mode, pipeline_status,
                                 verification_status, quality_status, count(*)
                          FROM public."AI_data_coverage" GROUP BY 1,2,3,4,5,6 ORDER BY 1,2,3,4,5,6''',
}
SAMPLES = {
    "AI_table_catalog": 'SELECT * FROM public."AI_table_catalog" ORDER BY table_name LIMIT 7',
    "AI_column_catalog": '''SELECT * FROM public."AI_column_catalog"
                            WHERE table_name = 'Feature_03_Stock_Broker_Daily' ORDER BY ordinal_position LIMIT 3''',
    "AI_catalog_relationships": 'SELECT * FROM public."AI_catalog_relationships" ORDER BY relationship_id LIMIT 5',
    "AI_calculation_catalog": '''SELECT * FROM public."AI_calculation_catalog"
                                 WHERE target_table = 'Feature_02_Broker_Rolling' ORDER BY calculation_name LIMIT 2''',
    "AI_data_coverage": '''SELECT * FROM public."AI_data_coverage" WHERE coverage_scope = 'DATASET'
                           ORDER BY dataset_name''',
}


def _json(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def main() -> None:
    url = os.environ.get("CATALOG_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("CATALOG_DATABASE_URL (preferred) or DATABASE_URL is required")
    report: dict[str, object] = {}
    with psycopg.connect(url, row_factory=dict_row, options="-c statement_timeout=15000") as connection:
        connection.read_only = True
        report["login"] = connection.execute("SELECT current_user AS login").fetchone()["login"]
        report["columns"] = {
            table: [
                f"{row['column_name']} {row['data_type']}{'' if row['is_nullable'] == 'YES' else ' NOT NULL'}"
                for row in connection.execute(
                    """SELECT column_name, data_type, is_nullable FROM information_schema.columns
                       WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""",
                    (table,),
                )
            ]
            for table in TABLES
        }
        report["row_counts"] = {
            table: connection.execute(f'SELECT count(*) AS n FROM public."{table}"').fetchone()["n"]
            for table in TABLES
        }
        report["states"] = {name: connection.execute(query).fetchall() for name, query in STATE_QUERIES.items()}
        report["samples"] = {name: connection.execute(query).fetchall() for name, query in SAMPLES.items()}
        report["views_or_functions_referencing_ai_catalogs"] = connection.execute(
            """SELECT 'view' AS kind, viewname AS name FROM pg_views
               WHERE schemaname = 'public' AND definition ILIKE ANY (%s)
               UNION ALL
               SELECT 'function', p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'public' AND p.prosrc ILIKE ANY (%s)""",
            (list(PATTERNS), list(PATTERNS)),
        ).fetchall()
        connection.rollback()
    print(json.dumps(report, indent=2, default=_json, ensure_ascii=False))


if __name__ == "__main__":
    main()
