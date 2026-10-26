"""Read-only: every catalog text cell that still holds an old corrected value or names the dropped Freq table."""
import json, os, psycopg
from psycopg import sql
corr = json.load(open("corrections.json"))
olds = sorted({c["old"] for c in corr})
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET default_transaction_read_only = on")
    cols = db.execute("""SELECT c.table_name, c.column_name, c.data_type FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema='public' AND t.table_type='BASE TABLE'
          AND (c.table_name ILIKE '%catalog%' OR c.table_name IN ('Feature_Vocabulary','Database_Table_Status'))
          AND c.data_type IN ('text','jsonb','ARRAY','character varying')""").fetchall()
    for t, c, dt in cols:
        expr = sql.SQL("{}::text").format(sql.Identifier(c))
        q = sql.SQL("SELECT count(*) FILTER (WHERE {e} ~ 'Summary_Freq|sync_broker_summary_freq'), "
                    "count(*) FILTER (WHERE {e} = ANY(%s)), count(*) FILTER (WHERE {e} LIKE ANY(%s)) FROM public.{t}").format(
            e=expr, t=sql.Identifier(t))
        a, b, cnt = db.execute(q, (olds, ['%' + o.replace('%', r'\%').replace('_', r'\_') + '%' for o in olds if len(o) > 25])).fetchone()
        if a or b or cnt:
            print("OUT", json.dumps({"table": t, "column": c, "freq_mention": a, "equals_old": b, "contains_old": cnt}), flush=True)
    for t, c in (("Table_Catalog", "definition"), ("Table_Catalog", "refresh_cadence"), ("Database_Table_Status", "update_frequency")):
        try:
            rows = db.execute(sql.SQL("SELECT table_name, {c} FROM public.{t} WHERE {c}::text ~ 'Summary_Freq|sync_broker_summary_freq'").format(
                c=sql.Identifier(c), t=sql.Identifier(t))).fetchall()
            for r in rows: print("ROW", json.dumps([t, c] + list(r), default=str), flush=True)
        except Exception as e:
            db.rollback(); db.execute("SET default_transaction_read_only = on"); print("ERR", t, c, type(e).__name__, flush=True)
print("JOB_DONE", flush=True)
