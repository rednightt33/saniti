"""Database_Table_Status refresh with scripts/sync_database_schema.py in ONE transaction: DRYRUN rolls back and
reports the change; APPLY commits and prints the regenerated DATABASE_SCHEMA.md in chunks. No secret is printed."""
import json, os, sys, time
from datetime import datetime, timezone
import psycopg
sys.path.insert(0, "scripts")
import sync_database_schema as s  # noqa: E402

mode = json.load(open("params.json"))["mode"]
assert mode in ("DRYRUN", "APPLY")
TRIG = """SELECT c.relname || ':' || t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public' AND NOT t.tgisinternal
          AND t.tgname LIKE 'database_table_status%' ORDER BY 1"""
ROWS = 'SELECT "Table Name", "Table Category", "Update Pattern", "Latest Data Date"::text FROM public."Database_Table_Status"'
refreshed_at = datetime.now(timezone.utc).replace(microsecond=0)
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET LOCAL lock_timeout = '5s'"); db.execute("SET LOCAL statement_timeout = '60s'")
    before = {r[0]: r[1:] for r in db.execute(ROWS).fetchall()}
    trig_before = [r[0] for r in db.execute(TRIG).fetchall()]
    started = time.monotonic()
    s.ensure_status_table(db, "public")
    names = s.table_names(db, "public")
    s.refresh_status(db, "public", names, refreshed_at)
    s.ensure_reference_tracking(db, "public", names)
    s.ensure_broker_load_tracking(db, "public", names)
    after = {r[0]: r[1:] for r in db.execute(ROWS).fetchall()}
    trig_after = [r[0] for r in db.execute(TRIG).fetchall()]
    changed = {k: {"before": before.get(k), "after": v} for k, v in after.items() if before.get(k) != v}
    print("OUT " + json.dumps({"tables": len(names), "rows_before": len(before), "rows_after": len(after),
        "deleted": sorted(set(before) - set(after)), "inserted": sorted(set(after) - set(before)),
        "changed": len(changed), "new_triggers": sorted(set(trig_after) - set(trig_before)),
        "seconds": round(time.monotonic() - started, 1)}, default=str), flush=True)
    for k, v in sorted(changed.items()):
        print("CHG " + json.dumps({k: v}, default=str, ensure_ascii=False)[:600], flush=True)
    if mode == "DRYRUN":
        db.rollback()
    else:
        statuses = s.fetch_status_rows(db, "public"); columns = s.fetch_columns(db, "public")
        constraints = s.fetch_constraints(db, "public"); indexes = s.fetch_indexes(db, "public")
        comments = s.fetch_table_comments(db, "public")
        s.apply_catalog_definitions(db, "public", names, comments, columns)
        views = s.view_definitions(db, "public")
        doc = s.generate_document("public", refreshed_at, names, columns, constraints, indexes, comments, statuses, views)
        db.commit()
        for i in range(0, len(doc), 50000):
            print("DOC %d %s" % (i // 50000, json.dumps(doc[i:i + 50000])), flush=True)
        print("OUT " + json.dumps({"committed": True, "doc_chars": len(doc)}), flush=True)
print("JOB_DONE", mode, flush=True)
