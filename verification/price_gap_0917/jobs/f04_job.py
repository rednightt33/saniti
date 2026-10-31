"""EXEC-PRICE-GAP-0917 S3, Feature 04 by hand (runs on orc-test-runner through scripts/onboarding/run_job.sh).

The worker's own code does every step except one: the worker continues from a checkpoint over at most
`correction_lookback_sessions` rows (D26), so here the state is rebuilt from the first stored price in memory.
Per queue item, claimed with `worker.claim_one` while the worker service is stopped:
  1. history = worker.load_history; calculate_incremental from no checkpoint (the chain the worker continues) must
     equal engine.calculate (the full reference) on every row and column, and pass the availability check;
  2. a stock not in `full_tickers`: every stored row before `write_from` must equal the calculation (indicators, swing
     and close within the bootstrap tolerance); a differing old candlestick flag (M314) is reported, never written;
     any other difference stops the stock (MANUAL_CHECK_FAILED, nothing written);
  3. written rows: from `write_from` for the others, every row for `full_tickers` (user decision 2026-10-31);
  4. the worker's success transaction: claim fence, upsert_columns, attempt log, column status, the latest
     checkpoints (lookback + 2), queue DONE, monitoring, finalize_runs.
Formula, libraries and VERSION are the worker's (features/feature04, requirements pinned like the worker image).

params.json: {"write_from": "2026-09-17", "full_tickers": [...], "processes": 4, "dry_run": bool, "sample": [...]}
Dry run: no claim and no write; computes the sample against the stored rows. Ends with JOB_DONE.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'features' / 'feature04'))
import worker as W  # noqa: E402
from engine import FEATURE_COLUMNS, VERSION, calculate, validate_output_availability  # noqa: E402
from incremental import calculate_incremental  # noqa: E402

P = json.load(open('params.json'))
WRITE_FROM = date.fromisoformat(P['write_from'])
FULL = set(P['full_tickers'])
CANDLE = {c for c in FEATURE_COLUMNS if c.startswith('cdl_')}


class Check(RuntimeError):
    pass


def out(kind, event, **fields):
    print(f'{kind} ' + json.dumps({'event': event, **fields}, default=str), flush=True)


def same(a, b) -> bool:
    """bootstrap_states.equal_value: exact for flags and NULLs, 1e-10 + 1e-12 relative for numbers"""
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, bool)) and isinstance(b, (int, bool)):
        return a == b
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(x - y) <= 1e-10 + 1e-12 * abs(y)


def retention(conn) -> int:
    row = conn.execute('SELECT correction_lookback_sessions FROM public."Equity_Market_Schedule" '
                       "WHERE market_code='IDX' AND enabled").fetchone()
    return int(row['correction_lookback_sessions']) + 2


def compute(conn, asset, ticker):
    history = W.load_history(conn, asset, ticker)
    keep = retention(conn)
    rows, outcomes, state, checkpoints = calculate_incremental(history, checkpoint_limit=keep)
    failed = {k: v for k, v in outcomes.items() if v['status'] == 'FAILED'}
    if failed:
        raise Check(f'formula group failed: {sorted(failed)}')
    missing = validate_output_availability(history, rows)
    if missing:
        raise Check(f'unavailable values: {sorted(missing)}')
    ref = calculate(history)
    if len(ref) != len(rows):
        raise Check('chain and reference row counts differ')
    for a, b in zip(rows, ref):
        if a['trade_date'] != b['trade_date']:
            raise Check('chain and reference dates differ')
        for c in FEATURE_COLUMNS:
            if not same(a[c], b[c]):
                raise Check(f'chain differs from reference {a["trade_date"]} {c}')
    return history, rows, outcomes, state, list(checkpoints), keep


def compare_old(conn, asset, ticker, rows):
    """rows before WRITE_FROM against the stored ones: (strict differences, candlestick differences, examples)"""
    stored = {r['trade_date']: r for r in conn.execute(
        f'SELECT trade_date,{",".join(FEATURE_COLUMNS)} FROM public."Feature_04_Technical_Indicator" '
        "WHERE asset_type=%s AND ticker=%s AND timeframe='Daily' AND trade_date<%s", (asset, ticker, WRITE_FROM)).fetchall()}
    old = [r for r in rows if r['trade_date'] < WRITE_FROM]
    strict, candle, examples = 0, 0, []
    if len(old) != len(stored):
        strict += abs(len(old) - len(stored))
        examples.append(f'rows calculated {len(old)} stored {len(stored)}')
    for r in old:
        s = stored.get(r['trade_date'])
        if s is None:
            continue
        for c in FEATURE_COLUMNS:
            if not same(r[c], s[c]):
                if c in CANDLE:
                    candle += 1
                else:
                    strict += 1
                    if len(examples) < 3:
                        examples.append(f'{r["trade_date"]} {c} calc {r[c]} stored {s[c]}')
    return strict, candle, examples


def handle(job) -> str:
    with W.connect() as rc:
        history, rows, outcomes, state, checkpoints, keep = compute(rc, job.asset_type, job.ticker)
        full = job.ticker in FULL
        candle = 0
        if not full:
            strict, candle, examples = compare_old(rc, job.asset_type, job.ticker, rows)
            if strict:
                raise Check(f'{strict} stored values before {WRITE_FROM} differ: {examples}')
    write = rows if full else [r for r in rows if r['trade_date'] >= WRITE_FROM]
    requested = W.dependency_closure(job.requested_columns)
    with W.connect() as c, c.transaction():
        c.execute("SET LOCAL statement_timeout = '900s'")
        if not W.current_claim(c, job):
            out('OUT', 'superseded', ticker=job.ticker)
            return 'SUPERSEDED'
        changed = W.delete_missing_outputs(c, job, [h['date'] for h in history])
        changed += W.upsert_columns(c, write, requested)
        attempt = W.write_attempt(
            c, job, requested=requested, successful=requested, failed=(), outcomes=outcomes, result='SUCCESS',
            history=history, digest=state['source_chain_sha256'], changed=changed, checkpoint_date=None,
            detail=f'EXEC-PRICE-GAP-0917 manual: state rebuilt from the first price; rows written from '
                   f'{write[0]["trade_date"] if write else None}; old candlestick differences reported {candle}')
        c.execute(
            """UPDATE public."Feature04_Column_Status" SET status='SUCCESS',
                 completed_generation=%s,calculation_version=%s,dirty_from_date=NULL,
                 validated_through=%s,last_attempt_id=%s,last_error_code=NULL,last_error=NULL,
                 last_calculated_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
               WHERE asset_type=%s AND ticker=%s AND timeframe='Daily' AND feature_column=ANY(%s)""",
            (job.requested_generation, VERSION, history[-1]['date'], attempt, job.asset_type, job.ticker, list(requested)))
        for column in requested:
            available = bool(rows and rows[-1][column] is not None)
            c.execute(
                """UPDATE public."Feature04_Column_Status" SET latest_value_available=%s,
                     null_reason=CASE WHEN %s THEN NULL ELSE 'EXPECTED_FORMULA_NULL' END
                   WHERE asset_type=%s AND ticker=%s AND timeframe='Daily' AND feature_column=%s""",
                (available, available, job.asset_type, job.ticker, column))
        W.replace_checkpoints(c, job, checkpoints, keep)
        c.execute(
            """UPDATE public."Feature04_Calculation_Queue" SET status='DONE',
                 completed_generation=requested_generation,claimed_at=NULL,claim_token=NULL,
                 claim_expires_at=NULL,completed_at=CURRENT_TIMESTAMP,last_error_code=NULL,last_error=NULL,
                 updated_at=CURRENT_TIMESTAMP
               WHERE asset_type=%s AND ticker=%s AND timeframe='Daily'""", (job.asset_type, job.ticker))
        c.execute(
            """UPDATE public."Monitoring_Feature04_Ticker" SET status='SUCCESS',
                 completed_generation=%s,finished_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
               WHERE asset_type=%s AND ticker=%s AND timeframe='Daily' AND required_generation<=%s
                 AND status IN ('PENDING','PROCESSING')""",
            (job.requested_generation, job.asset_type, job.ticker, job.requested_generation))
        W.finalize_runs(c)
    out('OUT', 'done', ticker=job.ticker, rows=len(write), changed=changed, full=full, old_candle_diffs=candle,
        checkpoints=len(checkpoints))
    return 'SUCCESS'


def loop(n: int) -> None:
    while True:
        job = W.claim_one()
        if job is None:
            return
        if job == 'EXHAUSTED':
            continue
        try:
            handle(job)
        except Exception as error:   # Check or anything else: the stock stops visibly, nothing of it is written
            detail = f'EXEC-PRICE-GAP-0917 manual: {W.error_detail(error)}'
            out('ERR', 'stock_failed', ticker=job.ticker, error=detail[:600])
            with W.connect() as c, c.transaction():
                if W.current_claim(c, job):
                    W.terminal_failure(c, job.asset_type, job.ticker, job.requested_generation, job.work_revision,
                                       'MANUAL_CHECK_FAILED', detail)


def dry_run() -> None:
    for ticker in P['sample']:
        t = time.monotonic()
        try:
            with W.connect() as rc:
                history, rows, outcomes, state, checkpoints, keep = compute(rc, 'equity', ticker)
                strict, candle, examples = compare_old(rc, 'equity', ticker, rows)
            out('OUT', 'dry_run', ticker=ticker, rows=len(rows), strict=strict, old_candle_diffs=candle, examples=examples,
                checkpoints=[s['last_date'] for s in checkpoints], seconds=round(time.monotonic() - t, 2))
        except Exception as error:
            out('ERR', 'dry_run_failed', ticker=ticker, error=W.error_detail(error))


def main() -> None:
    out('OUT', 'job_started', version=VERSION, write_from=WRITE_FROM, full=sorted(FULL), dry_run=P['dry_run'])
    if P['dry_run']:
        dry_run()
        return
    with W.connect() as c:
        busy = c.execute('''SELECT count(*) AS n FROM public."Feature04_Calculation_Queue"
                            WHERE status='PROCESSING' AND claim_expires_at > CURRENT_TIMESTAMP''').fetchone()['n']
        pending = c.execute('''SELECT count(*) AS n FROM public."Feature04_Calculation_Queue"
                               WHERE status IN ('PENDING','FAILED')''').fetchone()['n']
    if busy:
        out('ERR', 'worker_claims_active', processing=busy)   # the worker service must be stopped first
        raise SystemExit(1)
    out('OUT', 'queue', pending=pending)
    t = time.monotonic()
    procs = [mp.Process(target=loop, args=(i,)) for i in range(int(P['processes']))]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    with W.connect() as c:
        left = c.execute('''SELECT status, count(*) AS n FROM public."Feature04_Calculation_Queue"
                            WHERE asset_type='equity' GROUP BY 1''').fetchall()
    out('VERDICT', 'feature04', queue={r['status']: r['n'] for r in left}, seconds=round(time.monotonic() - t, 1))


if __name__ == '__main__':
    try:
        main()
    finally:
        print('JOB_DONE', flush=True)
