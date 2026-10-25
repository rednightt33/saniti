"""EXEC-EVENT-ANNOTATION: full Stockbit pull -> reconcile stockbit_corporate_action and stockbit_insider_transaction ->
refresh_idx_event_annotation(), all in one transaction. Runs on orc-test-runner through run_on_railway.sh
(UPDATE_TABLE.md, section "Corporate action, insider dan anotasi").

Environment: DATABASE_URL and STOCKBIT_TOKEN, both set only for the run. params.json (optional):
  {"mode": "APPLY" | "DRYRUN", "workers": 3, "min_ratio": 0.995}
DRYRUN pulls and reconciles inside the transaction, prints what would change, then rolls back.

Guarantees, each checked before COMMIT (any failure rolls everything back and nothing is written):
- full pull: every corporate action type x year, the whole market-wide insider listing for the ticker list, then
  every ticker's insider pages; a failed request stops the run;
- no gap: the reconciliation sees the whole source, so a late report with an old date is still inserted;
- no duplicate: stable keys (type:id; insider hash + variant) and exact copies collapsed (source_copies);
- nothing vanishes silently: a row Stockbit stops returning is kept with source_removed_at; a pull returning fewer
  than min_ratio of the active rows of a table stops the run (expired token mid-run, partial outage);
- required values present: the tables' NOT NULL and CHECK constraints, and the annotation count equals the active
  source rows.
Prints OUT/ERR lines and JOB_DONE; never prints a secret.
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import stockbit_events as se

CA = "public.stockbit_corporate_action"
INS = "public.stockbit_insider_transaction"
ANN = "public.idx_event_annotation"
LOCK = "hashtext('stockbit_event_annotation')"

CA_COLS = ["corporate_action_key", "action_type", "source_slug", "source_record_id", "symbol", "ticker",
           "instrument_code", "annotation_date", "annotation_date_role", "cum_date", "ex_date", "record_date",
           "pay_date", "start_date", "end_date", "source_payload"]
INS_COLS = ["insider_key", "ticker", "transaction_date", "action_type", "holder_id", "holder_name", "holder_roles",
            "holder_nationality", "broker_code", "shares_before", "shares_after", "shares_change", "pct_before",
            "pct_after", "pct_change", "pct_quality_flag", "price", "is_estimated_price", "value_idr", "data_origin",
            "source_copies", "source_payload"]


def out(q: str, **kw) -> None:
    print("OUT " + json.dumps({"q": q, **kw}, default=str), flush=True)


def err(q: str, **kw) -> None:
    print("ERR " + json.dumps({"q": q, **kw}, default=str), flush=True)


def known_tickers(cur) -> set[str]:
    rows = cur.execute('SELECT DISTINCT upper(btrim("Ticker")) FROM public."IDX_Stock_Universe"').fetchall()
    rows += cur.execute(f"SELECT DISTINCT ticker FROM {INS}").fetchall()
    rows += cur.execute(f"SELECT DISTINCT ticker FROM {CA} WHERE ticker ~ '^[A-Z]{{4}}$'").fetchall()
    return {r[0] for r in rows if r[0]}


def stage(cur, table: str, cols: list[str], rows: list[dict]) -> None:
    from psycopg.types.json import Jsonb
    cur.execute(f"CREATE TEMP TABLE stage_{table} ON COMMIT DROP AS SELECT {', '.join(cols)} FROM public.{table} WITH NO DATA")
    with cur.copy(f"COPY stage_{table} ({', '.join(cols)}) FROM STDIN") as cp:
        for r in rows:
            cp.write_row([Jsonb(r[c]) if c == "source_payload" else r[c] for c in cols])


def reconcile(cur, table: str, key: str, cols: list[str], run_ts, run_id: str) -> dict:
    """Insert new keys, update changed rows, refresh last_seen_at, mark absent rows removed; returns the counts."""
    t, s = f"public.{table}", f"stage_{table}"
    data_cols = [c for c in cols if c != key]
    differs = " OR ".join(f"t.{c} IS DISTINCT FROM s.{c}" for c in data_cols)
    counts = dict(zip(["pulled", "new", "changed", "reappeared", "unchanged"], cur.execute(f"""
        SELECT count(*), count(*) FILTER (WHERE t.{key} IS NULL),
               count(*) FILTER (WHERE t.{key} IS NOT NULL AND ({differs})),
               count(*) FILTER (WHERE t.source_removed_at IS NOT NULL),
               count(*) FILTER (WHERE t.{key} IS NOT NULL AND t.source_removed_at IS NULL AND NOT ({differs}))
        FROM {s} s LEFT JOIN {t} t USING ({key})""").fetchone()))
    counts["removed"] = cur.execute(f"""SELECT count(*) FROM {t} t WHERE t.source_removed_at IS NULL
        AND NOT EXISTS (SELECT 1 FROM {s} s WHERE s.{key} = t.{key})""").fetchone()[0]
    changed = " OR ".join(f"t.{c} IS DISTINCT FROM EXCLUDED.{c}" for c in data_cols)
    cur.execute(f"""INSERT INTO {t} AS t ({', '.join(cols)}, first_seen_at, last_seen_at, load_run_id)
        SELECT {', '.join(cols)}, %(ts)s, %(ts)s, %(run)s FROM {s}
        ON CONFLICT ({key}) DO UPDATE SET {', '.join(f'{c} = EXCLUDED.{c}' for c in data_cols)},
            last_seen_at = EXCLUDED.last_seen_at, load_run_id = EXCLUDED.load_run_id,
            updated_at = CASE WHEN {changed} OR t.source_removed_at IS NOT NULL
                              THEN statement_timestamp() ELSE t.updated_at END,
            source_removed_at = NULL""", {"ts": run_ts, "run": run_id})
    cur.execute(f"""UPDATE {t} t SET source_removed_at = %(ts)s, updated_at = statement_timestamp(), load_run_id = %(run)s
        WHERE t.source_removed_at IS NULL AND t.last_seen_at < %(ts)s""", {"ts": run_ts, "run": run_id})
    return counts


def checks(cur) -> list[str]:
    """Problems that must stop the commit (empty list = pass)."""
    bad = []
    ca, ins, ann = cur.execute(f"""SELECT (SELECT count(*) FROM {CA} WHERE source_removed_at IS NULL),
        (SELECT count(*) FROM {INS} WHERE source_removed_at IS NULL), (SELECT count(*) FROM {ANN})""").fetchone()
    if ann != ca + ins:
        bad.append(f"annotation rows {ann} != active corporate actions {ca} + insider {ins}")
    dup = cur.execute(f"SELECT count(*) - count(DISTINCT event_key) FROM {ANN}").fetchone()[0]
    if dup:
        bad.append(f"{dup} duplicate event_key")
    nulls = cur.execute(f"""SELECT count(*) FROM {ANN} WHERE ticker IS NULL OR annotation_date IS NULL
        OR event_type IS NULL""").fetchone()[0]
    if nulls:
        bad.append(f"{nulls} annotation rows without ticker, date or type")
    return bad


def summary(cur) -> None:
    for name, q in {
        "corporate_action_by_type": f"""SELECT action_type, count(*), min(annotation_date), max(annotation_date)
            FROM {CA} WHERE source_removed_at IS NULL GROUP BY 1 ORDER BY 1""",
        "insider_by_origin": f"""SELECT data_origin, count(*), count(DISTINCT ticker), min(transaction_date),
            max(transaction_date), sum(source_copies) FROM {INS} WHERE source_removed_at IS NULL GROUP BY 1 ORDER BY 1""",
        "insider_pct_flag": f"""SELECT pct_quality_flag, count(*) FROM {INS} WHERE source_removed_at IS NULL
            GROUP BY 1 ORDER BY 2 DESC""",
        "annotation_by_family": f"""SELECT event_family, count(*), count(DISTINCT ticker), min(annotation_date),
            max(annotation_date) FROM {ANN} GROUP BY 1 ORDER BY 1""",
        "removed_kept": f"""SELECT 'corporate_action', count(*) FROM {CA} WHERE source_removed_at IS NOT NULL
            UNION ALL SELECT 'insider', count(*) FROM {INS} WHERE source_removed_at IS NOT NULL""",
    }.items():
        out(name, rows=[list(r) for r in cur.execute(q).fetchall()])


def main() -> int:
    import psycopg

    params = json.load(open("params.json")) if os.path.exists("params.json") else {}
    mode = params.get("mode", "DRYRUN")
    if mode not in ("APPLY", "DRYRUN"):
        err("params", reason=f"mode {mode!r}")
        return 2
    workers = int(params.get("workers", 3))
    min_ratio = float(params.get("min_ratio", 0.995))
    token, dsn = os.environ.get("STOCKBIT_TOKEN", ""), os.environ.get("DATABASE_URL", "")
    if not token or not dsn:
        err("environment", missing=[n for n, v in (("STOCKBIT_TOKEN", token), ("DATABASE_URL", dsn)) if not v])
        return 2
    run_id = "sbev-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    started = time.monotonic()
    out("start", run_id=run_id, mode=mode, workers=workers, min_ratio=min_ratio)
    f = se.Fetcher(token)

    with psycopg.connect(dsn, connect_timeout=30, application_name="stockbit-event-annotation") as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = '30min'")
        if not cur.execute(f"SELECT pg_try_advisory_xact_lock({LOCK})").fetchone()[0]:
            err("lock", reason="another Stockbit event load holds the lock")
            return 3
        known = known_tickers(cur)
        empty_years = {(r[0], r[1]) for r in cur.execute(
            f"SELECT source_slug, extract(year FROM annotation_date)::int FROM {CA} GROUP BY 1, 2").fetchall()}
        # A failing year is "no data" only when the table holds none for that type and year (see pull_corporate_actions).
        last_year = datetime.now(ZoneInfo("Asia/Jakarta")).year + 1
        t0 = time.monotonic()
        pulled, failed = se.pull_corporate_actions(f, last_year, lambda s, y: (s, y) not in empty_years, workers)
        known |= {str(i["row"].get("company_symbol") or "").upper() for i in pulled
                  if se.TICKER.match(str(i["row"].get("company_symbol") or "").upper())}
        corp = se.dedupe_corp(pulled, known)
        out("pull_corporate_action", raw_rows=len(pulled), rows=len(corp), years_without_data_http=len(failed),
            seconds=round(time.monotonic() - t0, 1))
        t0 = time.monotonic()
        market, pages = se.insider_market_tickers(f, workers)
        tickers = known | market | {r["ticker"] for r in corp if se.TICKER.match(r["ticker"])}
        out("insider_ticker_list", market_pages=pages, market_tickers=len(market), tickers=len(tickers),
            seconds=round(time.monotonic() - t0, 1))
        t0 = time.monotonic()
        movements = se.pull_insider(f, tickers, workers,
                                    progress=lambda i, n: out("pull_insider_progress", done=i, of=n))
        insider = [r for t, ms in movements.items() for r in se.insider_rows(t, ms)]
        out("pull_insider", tickers=len(tickers), tickers_with_rows=sum(1 for v in movements.values() if v),
            movements=sum(len(v) for v in movements.values()), rows=len(insider), requests=f.requests,
            seconds=round(time.monotonic() - t0, 1))

        for table, rows in (("stockbit_corporate_action", corp), ("stockbit_insider_transaction", insider)):
            active = cur.execute(f"SELECT count(*) FROM public.{table} WHERE source_removed_at IS NULL").fetchone()[0]
            if active and len(rows) < min_ratio * active:
                err("pull_too_small", table=table, pulled=len(rows), active=active, min_ratio=min_ratio)
                conn.rollback()
                print("JOB_DONE", flush=True)
                return 4

        run_ts = cur.execute("SELECT statement_timestamp()").fetchone()[0]
        stage(cur, "stockbit_corporate_action", CA_COLS, corp)
        stage(cur, "stockbit_insider_transaction", INS_COLS, insider)
        out("reconcile_corporate_action", **reconcile(cur, "stockbit_corporate_action", "corporate_action_key",
                                                      CA_COLS, run_ts, run_id))
        out("reconcile_insider", **reconcile(cur, "stockbit_insider_transaction", "insider_key", INS_COLS,
                                             run_ts, run_id))
        out("refresh_annotation", rows=cur.execute("SELECT public.refresh_idx_event_annotation()").fetchone()[0])
        bad = checks(cur)
        summary(cur)
        if bad:
            err("checks_failed", problems=bad)
            conn.rollback()
            print("JOB_DONE", flush=True)
            return 5
        if mode == "APPLY":
            conn.commit()
            out("committed", run_id=run_id)
        else:
            conn.rollback()
            out("dryrun_rolled_back", run_id=run_id)
    if mode == "APPLY":
        with psycopg.connect(dsn, autocommit=True) as c:
            for t in (CA, INS, ANN):
                c.execute(f"ANALYZE {t}")
    out("done", seconds=round(time.monotonic() - started, 1))
    print("JOB_DONE", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except se.InvalidToken as exc:
        err("STOPPED_INVALID_TOKEN", reason=str(exc))
        print("JOB_DONE", flush=True)
        sys.exit(6)
    except se.StockbitError as exc:
        err("stockbit", reason=str(exc))
        print("JOB_DONE", flush=True)
        sys.exit(7)
