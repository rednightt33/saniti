"""Read-only read-back of the three Stockbit event tables after the load."""
import json, os, psycopg
OUT = lambda **k: print("OUT " + json.dumps(k, default=str), flush=True)
with psycopg.connect(os.environ["DATABASE_URL"]) as db:
    db.execute("SET default_transaction_read_only = on")
    for t, d in (("stockbit_corporate_action", "annotation_date"), ("stockbit_insider_transaction", "transaction_date"),
                 ("idx_event_annotation", "annotation_date")):
        r = db.execute(f"""SELECT count(*), count(DISTINCT ticker), min({d}), max({d}),
            {'count(*) FILTER (WHERE source_removed_at IS NULL)' if t != 'idx_event_annotation' else 'NULL'},
            {'count(DISTINCT load_run_id)' if t != 'idx_event_annotation' else 'NULL'},
            pg_size_pretty(pg_total_relation_size('public.{t}')) FROM public.{t}""").fetchone()
        OUT(table=t, rows=r[0], tickers=r[1], first=r[2], last=r[3], active=r[4], load_runs=r[5], size=r[6])
    OUT(check="annotation_equals_active_sources", ok=db.execute("""SELECT (SELECT count(*) FROM public.idx_event_annotation) =
        (SELECT count(*) FROM public.stockbit_corporate_action WHERE source_removed_at IS NULL) +
        (SELECT count(*) FROM public.stockbit_insider_transaction WHERE source_removed_at IS NULL)""").fetchone()[0])
    OUT(check="sample_bbca", rows=db.execute("""SELECT event_type, annotation_date, action, holder_name, pct_after, pct_change
        FROM public.idx_event_annotation WHERE ticker='BBCA' ORDER BY annotation_date DESC LIMIT 5""").fetchall())
print("JOB_DONE", flush=True)
