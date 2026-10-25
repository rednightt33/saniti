"""Read-only: the catalog cells that name the dropped Freq table or its sync."""
import json, os, psycopg
from psycopg import sql
CELLS = [("Column_Catalog", "table_name", "column_name", "definition"), ("AI_column_catalog", "table_name", "column_name", "description"),
         ("Feature_Catalog", "feature_table", "feature_column", "refresh_trigger"), ("Table_Catalog", "table_name", "table_schema", "update_rule"),
         ("Table_Catalog", "table_name", "table_schema", "definition"), ("Database_Table_Status", "Table Name", "Table Name", "Table Name")]
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET default_transaction_read_only = on")
    for t, a, b, c in CELLS:
        rows = db.execute(sql.SQL("SELECT {a}, {b}, {c}::text FROM public.{t} WHERE {c}::text ~ 'Summary_Freq|sync_broker_summary_freq'").format(
            a=sql.Identifier(a), b=sql.Identifier(b), c=sql.Identifier(c), t=sql.Identifier(t))).fetchall()
        for r in rows:
            print("ROW", json.dumps([t, c] + list(r), default=str, ensure_ascii=False), flush=True)
    for r in db.execute("""SELECT feature_table, refresh_trigger, count(*) FROM public."Feature_Catalog" WHERE is_active
                           AND feature_table ~ '^Feature_0[2356]' GROUP BY 1, 2 ORDER BY 1""").fetchall():
        print("TRIG", json.dumps(list(r), ensure_ascii=False), flush=True)
print("JOB_DONE", flush=True)
