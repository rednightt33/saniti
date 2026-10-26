"""EXEC-M216 inspection (read-only): relationships, table keys and catalog rows the date-only join design depends on."""
import json, os, psycopg
from psycopg.rows import dict_row
Q = {
 "rel_types": """SELECT relationship_type, count(*), count(*) FILTER (WHERE is_allowed) FROM public."AI_catalog_relationships" GROUP BY 1 ORDER BY 1""",
 "semantics": """SELECT supported_join_semantics, count(*) FROM public."AI_catalog_relationships" WHERE is_allowed GROUP BY 1 ORDER BY 2 DESC""",
 # for each allowed relationship: the pairs without the time pair, and each side's entity column and primary key
 "rels": """SELECT r.relationship_id, r.left_table, r.left_columns, r.right_table, r.right_columns, r.relationship_type,
       r.supported_join_semantics, r.left_time_column, r.right_time_column, r.requires_preaggregation,
       lt.entity_column AS l_entity, lt.primary_key_columns AS l_pk, rt.entity_column AS r_entity, rt.primary_key_columns AS r_pk
   FROM public."AI_catalog_relationships" r
   JOIN public."AI_table_catalog" lt ON lt.table_name = r.left_table
   JOIN public."AI_table_catalog" rt ON rt.table_name = r.right_table
   WHERE r.is_allowed ORDER BY 1""",
 "tables": """SELECT table_name, entity_column, time_column, primary_key_columns, is_active, ai_access_level FROM public."AI_table_catalog" ORDER BY 1""",
 "live_pk": """SELECT c.relname, array_agg(a.attname ORDER BY k.ord) FROM pg_constraint x JOIN pg_class c ON c.oid=x.conrelid
   JOIN LATERAL unnest(x.conkey) WITH ORDINALITY k(attnum, ord) ON true JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum
   WHERE x.contype='p' AND c.relnamespace='public'::regnamespace AND c.relname IN (SELECT table_name FROM public."AI_table_catalog") GROUP BY 1 ORDER BY 1""",
 "frc_cols": """SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='AI_catalog_relationships' ORDER BY ordinal_position""",
 "frc_index": """SELECT relationship_id, left_feature_table, left_join_columns, right_feature_table, right_join_columns, relationship_type, is_active
   FROM public."Feature_Relationship_Catalog" WHERE left_feature_table LIKE '%INDEX%' OR right_feature_table LIKE '%INDEX%' ORDER BY 1""",
 "index_tickers": """SELECT 'F01' t, ticker, count(*) FROM public."Feature_01_Stock_Daily_INDEX" GROUP BY 1,2
   UNION ALL SELECT 'F04', ticker || '/' || timeframe || '/' || asset_type, count(*) FROM public."Feature_04_Technical_Indicator_INDEX" GROUP BY 1,2
   UNION ALL SELECT 'F06', ticker || '/' || market_board, count(*) FROM public."Feature_06_Foreign_Domestic_INDEX" GROUP BY 1,2""",
 "f04_stock_keys": """SELECT timeframe, asset_type, count(*) FROM public."Feature_04_Technical_Indicator" GROUP BY 1,2 ORDER BY 1,2""",
 "tool_catalog_rel": """SELECT tool_name, version, is_active, left(description, 160) FROM public."Tool_Catalog" WHERE description ILIKE '%relationship%' OR tool_name ILIKE '%relation%' ORDER BY 1,2""",
}
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=20, row_factory=dict_row) as c:
    c.execute("SET default_transaction_read_only = on"); c.execute("SET statement_timeout='300s'")
    for k, s in Q.items():
        try:
            rows = c.execute(s).fetchall()
            for i in range(0, len(rows), 25):
                print("OUT", json.dumps({"q": k, "part": i // 25, "rows": rows[i:i + 25]}, default=str), flush=True)
            if not rows: print("OUT", json.dumps({"q": k, "rows": []}), flush=True)
        except Exception as e:
            c.rollback(); c.execute("SET default_transaction_read_only = on"); print("ERR", json.dumps({"q": k, "e": str(e)[:300]}), flush=True)
print("JOB_DONE", flush=True)
