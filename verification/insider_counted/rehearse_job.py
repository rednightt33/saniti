"""EXEC-INSIDER-COUNT rehearsal (no live change): core.sql runs on a temporary copy of idx_event_annotation
(pg_temp, dropped with the session); the live table and the raw tables are only read. Then the new table is compared
with the live one. Prints OUT/ERR lines and JOB_DONE. Run with scripts/onboarding/run_job.sh (extra: core.sql)."""
import json, os, re, time
import psycopg
from psycopg.rows import dict_row

core = open("core.sql").read()
# the table name only, not idx_event_annotation_terms_map (read from public as it is)
core = re.sub(r"public\.idx_event_annotation\b(?!_)", "pg_temp.idx_event_annotation", core)
core = core.replace("public.refresh_idx_event_annotation", "pg_temp.refresh_idx_event_annotation")
assert not re.search(r"public\.idx_event_annotation\b(?!_)", core) and "public.refresh_idx_event_annotation" not in core

OLD, NEW = "public.idx_event_annotation", "pg_temp.idx_event_annotation"
W = "annotation_date BETWEEN '2026-10-19' AND '2026-10-23' AND event_family = 'INSIDER' AND action = 'BUY'"
# the invariants are written apart from core.sql, on an indexed helper copy (H) of the new insider rows
H = "pg_temp.h"
NEAR = """EXISTS (SELECT 1 FROM pg_temp.h i WHERE i.data_origin='IDX' AND i.ticker=k.ticker AND i.hf=k.hf
          AND i.d BETWEEN k.d - 5 AND k.d + 5)"""
Q = {
 "rows": f"""SELECT (SELECT count(*) FROM {OLD}) old_rows, (SELECT count(*) FROM {NEW}) new_rows,
   (SELECT count(*) FROM {OLD} o WHERE NOT EXISTS (SELECT 1 FROM {NEW} n WHERE n.event_key=o.event_key)) only_old,
   (SELECT count(*) FROM {NEW} n WHERE NOT EXISTS (SELECT 1 FROM {OLD} o WHERE o.event_key=n.event_key)) only_new""",
 "reason_by_origin": f"""SELECT event_family, data_origin, count_reason, counted, count(*) n FROM {NEW} GROUP BY 1,2,3,4 ORDER BY 1,2,3""",
 "invariant_idx_and_ca_counted": f"""SELECT count(*) FILTER (WHERE data_origin='IDX' AND NOT counted) idx_not_counted,
   count(*) FILTER (WHERE event_family='CORPORATE_ACTION' AND (NOT counted OR count_reason<>'CORPORATE_ACTION')) ca_wrong FROM {NEW}""",
 "invariant_ksei_counted_has_no_idx": f"""SELECT count(*) bad FROM {H} k WHERE k.data_origin='KSEI' AND k.counted AND {NEAR}""",
 "invariant_ksei_uncounted_has_idx": f"""SELECT count(*) bad FROM {H} k WHERE k.data_origin='KSEI' AND NOT k.counted AND NOT {NEAR}""",
 "invariant_covered_keys_valid": f"""SELECT count(*) bad FROM {H} k, unnest(k.covered) c(key)
   WHERE NOT EXISTS (SELECT 1 FROM {H} i WHERE i.event_key=c.key AND i.data_origin='IDX' AND i.ticker=k.ticker
     AND i.hf=k.hf AND abs(i.d-k.d)<=5)""",
 "invariant_covered_complete": f"""SELECT count(*) bad FROM {H} k WHERE k.data_origin='KSEI' AND NOT k.counted AND
   (SELECT count(*) FROM {H} i WHERE i.data_origin='IDX' AND i.ticker=k.ticker AND i.hf=k.hf AND i.d BETWEEN k.d - 5 AND k.d + 5)
   <> cardinality(k.covered)""",
 "reason_last_2y_ksei": f"""SELECT count_reason, count(*) n FROM {NEW} WHERE data_origin='KSEI' AND annotation_date >= '2024-11-01' GROUP BY 1 ORDER BY 1""",
 "ksei_null_holder": f"SELECT count(*) n, count(*) FILTER (WHERE counted) counted FROM {NEW} WHERE data_origin='KSEI' AND holder_name IS NULL",
}
COLS = None


def column_diffs(c):
    cols = [r["column_name"] for r in c.execute("""SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='idx_event_annotation' ORDER BY ordinal_position""").fetchall()]
    cols = [x for x in cols if x not in ("event_key", "ingestion_time")]
    parts = ", ".join(f"count(*) FILTER (WHERE o.{x} IS DISTINCT FROM n.{x}) AS {x}" for x in cols)
    row = c.execute(f"SELECT {parts} FROM {OLD} o JOIN {NEW} n USING (event_key)").fetchone()
    return {k: v for k, v in row.items() if v}


EXTRA = {
 "m242_changes": f"""SELECT o.data_origin, count(*) FILTER (WHERE o.price IS DISTINCT FROM n.price) price_changed,
   count(*) FILTER (WHERE o.price IS DISTINCT FROM n.price AND NOT (o.price = 0 AND n.price IS NULL
     AND o.source_payload->'price'->>'formatted' = '-')) price_changed_unexpected,
   count(*) FILTER (WHERE o.value_idr IS DISTINCT FROM n.value_idr) value_changed,
   count(*) FILTER (WHERE o.value_idr IS DISTINCT FROM n.value_idr AND NOT (o.value_idr = 0 AND n.value_idr IS NULL
     AND o.source_payload->'value'->>'formatted' = '-')) value_changed_unexpected,
   count(*) FILTER (WHERE n.price = 0) price_zero_left, count(*) FILTER (WHERE n.value_idr = 0) value_zero_left,
   count(*) FILTER (WHERE n.value_idr = 0 AND n.source_payload->'value'->>'formatted' = '-') value_zero_dash_left
   FROM {OLD} o JOIN {NEW} n USING (event_key) WHERE o.event_family='INSIDER' GROUP BY 1""",
 "window_19_23_buy": f"""SELECT 'old_all_rows' v, count(*) n, count(DISTINCT ticker) tickers, sum(value_idr) value FROM {OLD} WHERE {W}
   UNION ALL SELECT 'new_counted', count(*), count(DISTINCT ticker), sum(value_idr) FROM {NEW} WHERE {W} AND counted
   UNION ALL SELECT 'new_not_counted', count(*), count(DISTINCT ticker), sum(value_idr) FROM {NEW} WHERE {W} AND NOT counted""",
 "window_19_23_buy_by_reason": f"SELECT count_reason, count(*) n, sum(value_idr) value FROM {NEW} WHERE {W} GROUP BY 1 ORDER BY 1",
 "window_twin_examples_now": f"""SELECT ticker, holder_name, annotation_date, data_origin, shares_change, value_idr, counted, count_reason
   FROM {NEW} WHERE {W} AND ticker IN ('ENRG','GULA','UVCR','WIFI','SRTG','SPMA') ORDER BY ticker, holder_name, annotation_date, data_origin""",
 "two_years_buy": f"""SELECT 'old_all_rows' v, count(*) n, sum(value_idr) value FROM {OLD} WHERE event_family='INSIDER' AND action='BUY' AND annotation_date >= '2024-11-01'
   UNION ALL SELECT 'new_counted', count(*), sum(value_idr) FROM {NEW} WHERE event_family='INSIDER' AND action='BUY' AND annotation_date >= '2024-11-01' AND counted""",
 "samples": f"""SELECT * FROM (SELECT k.count_reason, k.ticker, k.holder_name, k.annotation_date, k.data_origin, k.action, k.shares_change,
     k.value_idr, (SELECT json_agg(json_build_object('date', i.annotation_date, 'change', i.shares_change, 'action', i.action)
       ORDER BY i.annotation_date) FROM {NEW} i WHERE i.event_key = ANY(k.covered_by_event_keys)) idx_reports,
     row_number() OVER (PARTITION BY k.count_reason ORDER BY md5(k.event_key)) r
   FROM {NEW} k WHERE k.data_origin='KSEI' AND k.annotation_date >= '2026-09-01') x WHERE r <= 4 ORDER BY count_reason, ticker""",
}

with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as c:
    c.execute("SET default_transaction_read_only = off"); c.execute("SET statement_timeout = '600s'")
    c.execute("CREATE TEMP TABLE idx_event_annotation (LIKE public.idx_event_annotation INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING INDEXES)")
    started = time.monotonic()
    c.execute(core)
    print("OUT " + json.dumps({"q": "core_ran", "seconds": round(time.monotonic() - started, 1)}), flush=True)
    c.execute("""CREATE TEMP TABLE h AS SELECT event_key, data_origin, ticker, lower(btrim(holder_name)) hf, annotation_date d,
        counted, covered_by_event_keys covered FROM pg_temp.idx_event_annotation WHERE event_family = 'INSIDER'""")
    c.execute("CREATE INDEX ON pg_temp.h (ticker, hf, d) WHERE data_origin = 'IDX'")
    c.execute("CREATE INDEX ON pg_temp.h (event_key)")
    c.execute("ANALYZE pg_temp.h")
    for name, sql in {**Q, **EXTRA}.items():
        try:
            print("OUT " + json.dumps({"q": name, "rows": c.execute(sql).fetchall()}, default=str, ensure_ascii=False), flush=True)
        except Exception as e:
            c.rollback(); print("ERR " + json.dumps({"q": name, "error": f"{type(e).__name__}: {str(e)[:300]}"}), flush=True); break
    try:
        print("OUT " + json.dumps({"q": "column_diffs", "rows": column_diffs(c)}, default=str), flush=True)
    except Exception as e:
        print("ERR " + json.dumps({"q": "column_diffs", "error": str(e)[:300]}), flush=True)
    c.rollback()  # nothing is kept: the temp table and function go with the transaction and the session
    print("OUT " + json.dumps({"q": "live_untouched", "rows": c.execute(
        "SELECT count(*) n, max(ingestion_time)::text latest FROM public.idx_event_annotation").fetchall(),
        "has_counted_column": c.execute("""SELECT count(*) FROM information_schema.columns WHERE table_schema='public'
           AND table_name='idx_event_annotation' AND column_name='counted'""").fetchone()}, default=str), flush=True)
print("JOB_DONE", flush=True)
