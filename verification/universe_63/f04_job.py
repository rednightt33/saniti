# EXEC-UNIVERSE-BROKER S1 (user go 2026-11-05: "ok", "A"): Feature 04 of the 63 codes added to IDX_Stock_Universe,
# by the job of EXEC-PRICE-GAP-0917 S3 (verification/price_gap_0917/jobs/f04_job.py, copied unchanged below this note
# except the reopening step). The worker continues from a checkpoint only; a new ticker has none, so its queue row ends
# REPAIR_REQUIRED ("No compatible checkpoint immediately before <first date>", as ERRORS M336). Every code here is in
# full_tickers: computed from its first stored price, every row written, checkpoints built, queue DONE.
# params.json: {"write_from": "2026-11-05", "full_tickers": [the 63 codes], "processes": 4, "dry_run": false,
#               "reopen_repair": true}
# reopen_repair: the REPAIR_REQUIRED queue rows of full_tickers are opened again (PENDING) before the claims.
# The feature-04-worker service is stopped during the run (its claims would race this job).
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

params.json: {"write_from": "2026-09-17", "full_tickers": [...], "processes": 4, "dry_run": bool, "sample": [...],
              "retry_failed": bool}
The chain and the reference are compared on the rows written (2026-10-31 first run: a few low-priced stocks differ on
rsi_14 far back, about float accumulation over years; those rows are not written).
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


def compute(conn, asset, ticker, check_from=None):
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
    # EXEC-UNIVERSE-BROKER: a full ticker's history is written from the reference (engine.calculate, as the stored
    # history of every other stock was built, features/feature04/backfill.py); the chain must equal it on the rows the
    # worker continues from (the last `keep` rows, its checkpoints). Before them the chain may differ (float accumulation,
    # M316 point 4; flat no-trade stretches, e.g. AKKU rsi_14 2022-02-18 chain 45.81 reference 0.0); counted and reported.
    strict_from = len(rows) - keep if check_from is None else 0
    old_differences = 0
    for i, (a, b) in enumerate(zip(rows, ref)):
        if a['trade_date'] != b['trade_date']:
            raise Check('chain and reference dates differ')
        if check_from is not None and a['trade_date'] < check_from:
            continue   # not written; old rows are compared with the stored ones through the reference (compare_old)
        for c in FEATURE_COLUMNS:
            if same(a[c], b[c]):
                continue
            if i < strict_from:
                old_differences += 1
                continue
            raise Check(f'chain differs from reference {a["trade_date"]} {c}: chain {a[c]} reference {b[c]} '
                        f'(row {i} of {len(rows)}, strict from {strict_from})')
    if old_differences:
        out('OUT', 'old_chain_differences', ticker=history[-1].get('ticker') if history else None,
            values=old_differences, written='reference')
    return history, rows, ref, outcomes, state, list(checkpoints), keep


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
    full = job.ticker in FULL
    with W.connect() as rc:
        history, rows, ref, outcomes, state, checkpoints, keep = compute(
            rc, job.asset_type, job.ticker, None if full else WRITE_FROM)
        candle = 0
        if not full:
            strict, candle, examples = compare_old(rc, job.asset_type, job.ticker, ref)
            if strict:
                raise Check(f'{strict} stored values before {WRITE_FROM} differ: {examples}')
    # a full ticker writes the reference rows (above); the others the chain from WRITE_FROM, as before
    write = ref if full else [r for r in rows if r['trade_date'] >= WRITE_FROM]
    if full and write and not all(k in write[0] for k in ('ticker', 'trade_date', 'timeframe', 'asset_type',
                                                          'calculation_version', 'calculated_at')):
        raise Check(f'reference rows lack a written column: {sorted(write[0])[:8]}')
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


def claim_repair_source() -> str:
    """worker.claim_one, unchanged but for the candidate: a REPAIR_REQUIRED row of full_tickers. The worker never claims
    such a row (next_attempt_at infinity), so the job and the running worker cannot race for it (the worker service
    stays up: stopping it was refused in this session)."""
    import inspect
    src = inspect.getsource(W.claim_one)
    old_where = src[src.index('WHERE (status IN'):src.index('FOR UPDATE SKIP LOCKED LIMIT 1')]
    src = src.replace(old_where, "WHERE status='FAILED' AND last_error_code='REPAIR_REQUIRED' AND ticker = ANY(%s)\n            ")
    src = src.replace('(MAX_SOURCE_ATTEMPTS,),', '(REPAIR_TICKERS,),', 1).replace('def claim_one()', 'def claim_repair()', 1)
    assert 'REPAIR_REQUIRED' in src and 'REPAIR_TICKERS' in src
    return src


if P.get('claim_repair'):
    W.REPAIR_TICKERS = sorted(FULL)
    exec(claim_repair_source(), W.__dict__)


def loop(n: int) -> None:
    while True:
        job = W.claim_repair() if P.get('claim_repair') else W.claim_one()
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
                history, rows, ref, outcomes, state, checkpoints, keep = compute(
                    rc, 'equity', ticker, None if ticker in FULL else WRITE_FROM)
                strict, candle, examples = compare_old(rc, 'equity', ticker, ref)
            out('OUT', 'dry_run', ticker=ticker, rows=len(rows), strict=strict, old_candle_diffs=candle, examples=examples,
                checkpoints=[s['last_date'] for s in checkpoints], seconds=round(time.monotonic() - t, 2))
        except Exception as error:
            out('ERR', 'dry_run_failed', ticker=ticker, error=W.error_detail(error))


def main() -> None:
    out('OUT', 'job_started', version=VERSION, write_from=WRITE_FROM, full=sorted(FULL), dry_run=P['dry_run'])
    if P['dry_run']:
        dry_run()
        return
    if P.get('reopen_repair'):
        with W.connect() as c:
            n = c.execute(
                'UPDATE public."Feature04_Calculation_Queue" SET status=%s,source_attempt_count=0,'
                'next_attempt_at=CURRENT_TIMESTAMP,last_error_code=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP '
                'WHERE status=%s AND last_error_code=%s AND ticker = ANY(%s)',
                ('PENDING', 'FAILED', 'REPAIR_REQUIRED', sorted(FULL))).rowcount
        out('OUT', 'reopen_repair', reopened=n)
    if P.get('retry_failed'):
        # queue rows this job stopped earlier (terminal_failure MANUAL_CHECK_FAILED) are opened again for this run
        with W.connect() as c:
            n = c.execute(
                'UPDATE public."Feature04_Calculation_Queue" SET status=%s,source_attempt_count=0,'
                'next_attempt_at=CURRENT_TIMESTAMP,last_error_code=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP '
                'WHERE status=%s AND last_error_code=%s', ('PENDING', 'FAILED', 'MANUAL_CHECK_FAILED')).rowcount
        out('OUT', 'retry_failed', reopened=n)
    if P.get('claim_repair'):
        # 'infinity' does not load into a Python datetime; 9999-12-31 keeps the row out of the worker's reach as well
        with W.connect() as c:
            n = c.execute('''UPDATE public."Feature04_Calculation_Queue" SET next_attempt_at='9999-12-31'
                             WHERE status='FAILED' AND last_error_code='REPAIR_REQUIRED' AND ticker = ANY(%s)
                               AND next_attempt_at='infinity' ''', (sorted(FULL),)).rowcount
        out('OUT', 'claim_repair', tickers=len(FULL), finite_next_attempt=n)
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
