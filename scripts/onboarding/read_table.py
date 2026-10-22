"""NEW_TABLE_ONBOARDING_PLAN.md step 1: the live state of the tables to onboard, read-only, before anything is written.

params.json: {"tables": ["Feature_06_Foreign_Domestic"], "time_column": {"Feature_06_Foreign_Domestic": "trade_date"},
              "model_tables": ["Feature_04_Technical_Indicator"]}
  tables        the objects to onboard (base tables or views);
  time_column   per table, its date column (date range and per-date density); optional;
  model_tables  exposed tables whose AI catalog rows serve as the pattern (Feature 04 is the benchmark).

Prints one `OUT {json}` line per query part, `ERR {json}` for a query that failed, then JOB_DONE. Every statement runs
in a read-only transaction; no secret is printed. Run with scripts/onboarding/run_job.sh.
"""
import json
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

params = json.load(open("params.json"))
TABLES = params["tables"]
MODELS = params.get("model_tables") or ["Feature_04_Technical_Indicator"]
TIME = params.get("time_column") or {}

SHAPE = {
    "columns": """SELECT table_name, ordinal_position, column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY(%(t)s) ORDER BY 1, 2""",
    "kind_and_size": """SELECT c.relname, c.relkind, c.reltuples::bigint AS estimated_rows,
        pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size, pg_size_pretty(pg_relation_size(c.oid)) AS heap_size
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relname = ANY(%(t)s)""",
    "constraints": """SELECT conrelid::regclass::text AS table_name, conname, contype, pg_get_constraintdef(oid) AS definition
        FROM pg_constraint WHERE conrelid::regclass::text = ANY(SELECT format('%%I', x) FROM unnest(%(t)s::text[]) x)
        ORDER BY 1, 2""",
    # the Governor's view of an index (governor.py INDEX_LEADING_SQL): only the FIRST column counts for a date split
    "indexes": """SELECT t.relname AS table_name, i.relname AS index_name, a.attname AS leading_column, ix.indisvalid,
        ix.indisunique, pg_size_pretty(pg_relation_size(i.oid)) AS size, pg_get_indexdef(i.oid) AS definition
        FROM pg_index ix JOIN pg_class t ON t.oid = ix.indrelid JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ix.indkey[0]
        WHERE n.nspname = 'public' AND t.relname = ANY(%(t)s) ORDER BY 1, 2""",
    "view_definition": """SELECT c.relname, pg_get_viewdef(c.oid, true) AS definition FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND c.relkind = 'v' AND c.relname = ANY(%(t)s)""",
    "grants": """SELECT table_name, grantee, privilege_type FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = ANY(%(t)s) ORDER BY 1, 2""",
}
CATALOGS = {
    "table_catalog": """SELECT * FROM public."Table_Catalog" WHERE table_name = ANY(%(t)s)""",
    "column_catalog": """SELECT table_name, column_name, ordinal_position, data_type, is_primary_key, unit,
        left(definition, 200) AS definition, documentation_status FROM public."Column_Catalog" WHERE table_name = ANY(%(t)s)
        ORDER BY 1, 3""",
    "feature_catalog": """SELECT feature_table, feature_column, version, unit, semantic_role, allowed_aggregations,
        is_filterable, is_groupable, feature_category, left(definition, 160) AS definition, left(calculation, 160) AS
        calculation, lookback_window, minimum_history, point_in_time_safe, semantic_review_status
        FROM public."Feature_Catalog" WHERE feature_table = ANY(%(t)s) AND is_active ORDER BY 1, 2""",
    "feature_relationships": """SELECT * FROM public."Feature_Relationship_Catalog"
        WHERE left_feature_table = ANY(%(t)s) OR right_feature_table = ANY(%(t)s)""",
    "ai_table_catalog": """SELECT * FROM public."AI_table_catalog" WHERE table_name = ANY(%(t)s)""",
    "ai_column_catalog_count": """SELECT table_name, count(*) AS columns, count(*) FILTER (WHERE ai_allowed) AS ai_allowed
        FROM public."AI_column_catalog" WHERE table_name = ANY(%(t)s) GROUP BY 1""",
    "ai_relationships": """SELECT * FROM public."AI_catalog_relationships" WHERE left_table = ANY(%(t)s) OR right_table = ANY(%(t)s)""",
    "ai_calculations_count": """SELECT target_table, count(*) AS rows FROM public."AI_calculation_catalog"
        WHERE target_table = ANY(%(t)s) GROUP BY 1""",
    "ai_coverage": """SELECT dataset_name, coverage_scope, count(*) AS rows, min(actual_min_date) AS min_date,
        max(actual_max_date) AS max_date FROM public."AI_data_coverage" WHERE dataset_name = ANY(%(t)s) GROUP BY 1, 2""",
}
# the benchmark's rows: what a complete onboarding looks like
MODEL = {
    "model_ai_table_catalog": """SELECT * FROM public."AI_table_catalog" WHERE table_name = ANY(%(m)s)""",
    "model_ai_column_catalog": """SELECT table_name, column_name, ordinal_position, semantic_type, unit, ai_allowed,
        allowed_aggregations, filter_allowed, group_by_allowed, coverage_required, resample_aggregation,
        cross_entity_aggregation, value_time_basis, left(description, 120) AS description,
        left(description_id, 120) AS description_id, description_id_status, entity_name, documentation_status
        FROM public."AI_column_catalog" WHERE table_name = ANY(%(m)s) ORDER BY 1, 3 LIMIT 12""",
    "model_ai_relationships": """SELECT * FROM public."AI_catalog_relationships" WHERE left_table = ANY(%(m)s) LIMIT 4""",
    "model_ai_calculations": """SELECT * FROM public."AI_calculation_catalog" WHERE target_table = ANY(%(m)s) LIMIT 3""",
    "model_ai_coverage": """SELECT * FROM public."AI_data_coverage" WHERE dataset_name = ANY(%(m)s) AND coverage_scope = 'DATASET'""",
    "roles": """SELECT rolname FROM pg_roles WHERE rolname LIKE 'market\\_%%' OR rolname = 'pgweb_reader' ORDER BY 1""",
}


def out(name, rows):
    for i in range(0, max(len(rows), 1), 8):
        print("OUT " + json.dumps({"q": name, "part": i // 8, "rows": rows[i:i + 8]}, default=str), flush=True)


def run(conn, name, statement, args):
    try:
        with conn.transaction():
            out(name, conn.execute(statement, args).fetchall())
    except Exception as e:  # noqa: BLE001 - one failed query must not hide the others
        print("ERR " + json.dumps({"q": name, "error": f"{type(e).__name__}: {str(e)[:300]}"}), flush=True)


with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True,
                     options="-c default_transaction_read_only=on -c statement_timeout=120000") as conn:
    print("READONLY " + json.dumps(conn.execute("SHOW transaction_read_only").fetchone()), flush=True)
    for group in (SHAPE, CATALOGS):
        for name, statement in group.items():
            run(conn, name, statement, {"t": TABLES})
    for name, statement in MODEL.items():
        run(conn, name, statement, {"m": MODELS})
    for table in TABLES:
        columns = [r["column_name"] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position", (table,)).fetchall()]
        if not columns:
            print("ERR " + json.dumps({"q": f"profile:{table}", "error": "no such table or view"}), flush=True)
            continue
        ident = sql.Identifier(table)
        # exact rows and NULLs per column: the numbers the catalog and the Governor estimate are checked against
        nulls = sql.SQL(", ").join(sql.SQL("count(*) FILTER (WHERE {} IS NULL) AS {}").format(
            sql.Identifier(c), sql.Identifier(f"null:{c}")) for c in columns)
        try:
            with conn.transaction():
                row = conn.execute(sql.SQL("SELECT count(*) AS rows, {} FROM public.{}").format(nulls, ident)).fetchone()
            values = list(row.values())
            out(f"profile:{table}", [{"rows": values[0], "nulls": dict(zip(columns, values[1:]))}])
        except Exception as e:  # noqa: BLE001
            print("ERR " + json.dumps({"q": f"profile:{table}", "error": f"{type(e).__name__}: {str(e)[:300]}"}), flush=True)
        time_column = TIME.get(table)
        if time_column:
            t = sql.Identifier(time_column)
            run(conn, f"dates:{table}", sql.SQL("SELECT min({t}) AS min_date, max({t}) AS max_date, count(DISTINCT {t}) AS dates, "
                                                "round(count(*)::numeric / nullif(count(DISTINCT {t}), 0)) AS rows_per_date "
                                                "FROM public.{x}").format(t=t, x=ident), None)
print("JOB_DONE READ", flush=True)
