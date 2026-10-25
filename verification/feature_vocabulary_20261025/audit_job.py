"""Read-only: the Feature catalog audit, and the old audit query's misses grouped by table."""
import json, os, subprocess, sys, psycopg
r = subprocess.run([sys.executable, "audit.py"], capture_output=True, text=True)
print("OUT " + json.dumps({"audit_rc": r.returncode, "out": r.stdout[-2500:], "err": r.stderr[-1500:]}), flush=True)
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET default_transaction_read_only = on")
    rows = db.execute('''SELECT c.table_name, count(*) FROM information_schema.columns c JOIN public."Table_Catalog" t
        ON t.table_schema=c.table_schema AND t.table_name=c.table_name WHERE t.category='Feature' AND NOT EXISTS (
        SELECT 1 FROM public."Feature_Catalog" f WHERE f.feature_table=c.table_name AND f.feature_column=c.column_name AND f.is_active)
        GROUP BY 1 ORDER BY 1''').fetchall()
    print("OUT " + json.dumps({"old_query_misses": rows}), flush=True)
    com = db.execute("""SELECT c.relname, a.attname, d.description FROM pg_description d JOIN pg_class c ON c.oid = d.objoid
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.objsubid AND d.objsubid > 0
        WHERE d.classoid = 'pg_class'::regclass AND d.description ~ 'sync_broker_summary_freq|Summary_Freq'""").fetchall()
    print("OUT " + json.dumps({"comments": com}), flush=True)
print("JOB_DONE", flush=True)
