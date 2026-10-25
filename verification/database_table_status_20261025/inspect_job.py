"""Read-only: Database_Table_Status against the live tables and Table_Catalog."""
import json, os, psycopg
from psycopg.rows import dict_row
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
    db.execute("SET default_transaction_read_only = on")
    tables = [r["table_name"] for r in db.execute("""SELECT table_name FROM information_schema.tables
        WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1""").fetchall()]
    status = {r["Table Name"]: r for r in db.execute('SELECT * FROM public."Database_Table_Status"').fetchall()}
    cat = {r["table_name"]: r for r in db.execute("""SELECT table_name, category, update_rule, observation_date_column,
        readiness_date_column FROM public."Table_Catalog" WHERE table_schema='public'""").fetchall()}
    print("OUT " + json.dumps({"tables": len(tables), "status_rows": len(status), "catalog_rows": len(cat),
        "stale_status": sorted(set(status) - set(tables)), "missing_status": sorted(set(tables) - set(status)),
        "tables_not_in_catalog": sorted(set(tables) - set(cat))}), flush=True)
    for t in tables:
        s, c = status.get(t) or {}, cat.get(t) or {}
        print("ROW " + json.dumps({"t": t, "s_cat": s.get("Table Category"), "s_pat": s.get("Update Pattern"),
            "s_latest": s.get("Latest Data Date"), "s_track": s.get("Tracking Status"), "c_cat": c.get("category"),
            "c_rule": c.get("update_rule"), "c_obs": c.get("observation_date_column")}, default=str, ensure_ascii=False), flush=True)
print("JOB_DONE", flush=True)
