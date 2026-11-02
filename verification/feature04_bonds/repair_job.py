"""EXEC-F04-BONDS (user go 2026-11-02): Feature 04 bonds held at REPAIR_REQUIRED since the M324 price correction.

Per bond in the failed queue: price history read in memory and calculated with the deployed engine; every stored row
before the queue's dirty date must equal the calculation (else the bond is skipped); rows from the dirty date on are
written with the worker's own upsert/delete; the recent checkpoints are rebuilt; the queue row is closed DONE and
re-queued through enqueue_feature04_group at the last price date, so the worker finishes the last session itself.
MODE=dry (default, read-only transactions) or MODE=write. Prints OUT/ERR lines and JOB_DONE."""
import json, os, sys
from datetime import date, datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import worker
from worker import Job, connect, load_history, upsert_columns, delete_missing_outputs, replace_checkpoints
from engine import FEATURE_COLUMNS, VERSION, calculate_with_diagnostics
from incremental import build_recent_checkpoints, STATE_VERSION

WRITE = os.environ.get('MODE', 'dry') == 'write'
def out(part, **k): print('OUT ' + json.dumps({'part': part, **k}, default=str), flush=True)
def err(part, **k): print('ERR ' + json.dumps({'part': part, **k}, default=str), flush=True)

def same(a, b):
    if a is None or b is None: return a is b
    if isinstance(a, (bool, int)) and isinstance(b, (bool, int)): return a == b
    try: x, y = float(a), float(b)
    except (TypeError, ValueError): return a == b
    return abs(x - y) <= 1e-10 + 1e-12 * abs(y)

out('start', write=WRITE, version=VERSION, state_version=STATE_VERSION)
with connect() as c:
    if c.execute('SELECT EXISTS(SELECT 1 FROM public."Feature04_Calculation_Queue" WHERE status=\'PROCESSING\')').fetchone()['exists']:
        err('active_claim'); print('JOB_DONE'); sys.exit(1)
    queue = c.execute("""SELECT ticker, dirty_from_date, requested_generation, completed_generation, status
        FROM public."Feature04_Calculation_Queue" WHERE asset_type='bonds' AND timeframe='Daily' ORDER BY ticker""").fetchall()
out('queue', rows=[[q['ticker'], q['dirty_from_date'], q['status'], q['requested_generation'], q['completed_generation']] for q in queue])
summary = []
for q in queue:
    ticker, dirty = q['ticker'], q['dirty_from_date']
    if q['status'] != 'FAILED' or dirty is None:
        out('skip', ticker=ticker, reason=f"status {q['status']} dirty {dirty}"); continue
    try:
        with connect() as c:
            history = load_history(c, 'bonds', ticker)
            lookback = int(c.execute("""SELECT DISTINCT s.correction_lookback_sessions FROM public."Universe_Fixed_income" u
                JOIN public."Fixed_Income_Market_Schedule" s ON s.country=u.country
                WHERE u.ticker=%s AND u.metric_type='price' AND s.enabled""", (ticker,)).fetchone()['correction_lookback_sessions'])
            stored = c.execute("""SELECT * FROM public."Feature_04_Technical_Indicator"
                WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' ORDER BY trade_date""", (ticker,)).fetchall()
        rows, outcomes = calculate_with_diagnostics(history, calculated_at=datetime.now(timezone.utc))
        failed_groups = {k: v for k, v in outcomes.items() if v.get('status') != 'SUCCESS'}
        if failed_groups:
            err('formula', ticker=ticker, groups=list(failed_groups)[:10]); continue
        calc = {r['trade_date']: r for r in rows}
        before = [s for s in stored if s['trade_date'] < dirty]
        diffs = [(str(s['trade_date']), col, s[col], calc.get(s['trade_date'], {}).get(col)) for s in before
                 for col in FEATURE_COLUMNS if s['trade_date'] not in calc or not same(s[col], calc[s['trade_date']][col])]
        if diffs:
            err('history_mismatch', ticker=ticker, count=len(diffs), first=diffs[:5]); continue
        suffix = [r for r in rows if r['trade_date'] >= dirty]
        stored_suffix = {s['trade_date']: s for s in stored if s['trade_date'] >= dirty}
        changed_dates = sorted(str(d) for d, r in ((r['trade_date'], r) for r in suffix)
                               if d not in stored_suffix or any(not same(stored_suffix[d][col], r[col]) for col in FEATURE_COLUMNS))
        gone = sorted(str(d) for d in stored_suffix if d not in calc)
        retention = lookback + 2
        states = build_recent_checkpoints(history, retain=retention)
        last = history[-1]['date']
        info = dict(ticker=ticker, dirty=dirty, last_price=last, stored_before=len(before), before_equal=True,
                    rows_from_dirty=len(suffix), changed_dates=len(changed_dates), changed_sample=changed_dates[:6],
                    stored_dates_gone=gone, checkpoints=len(states), checkpoint_last=states[-1]['last_date'] if states else None)
        if WRITE:
            job = Job(asset_type='bonds', ticker=ticker, dirty_from_date=dirty, requested_generation=q['requested_generation'],
                      work_revision=0, requested_columns=None, origin_execution_id=None, attempt_no=0,
                      source_attempt_count=0, claim_token=None, started_at=datetime.now(timezone.utc))
            with connect() as c, c.transaction():
                c.execute("SET LOCAL statement_timeout='180s'")
                locked = c.execute("""SELECT status, requested_generation FROM public."Feature04_Calculation_Queue"
                    WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' FOR UPDATE""", (ticker,)).fetchone()
                if locked['status'] != 'FAILED' or locked['requested_generation'] != q['requested_generation']:
                    raise RuntimeError(f'queue changed under the job: {dict(locked)}')
                info['deleted'] = delete_missing_outputs(c, job, [h['date'] for h in history])
                info['upserted'] = upsert_columns(c, suffix, FEATURE_COLUMNS)
                replace_checkpoints(c, job, states, retention)
                c.execute("""UPDATE public."Feature04_Calculation_Queue" SET status='DONE',
                    completed_generation=requested_generation, last_error_code=NULL, last_error=NULL,
                    claimed_at=NULL, claim_token=NULL, claim_expires_at=NULL, completed_at=CURRENT_TIMESTAMP,
                    updated_at=CURRENT_TIMESTAMP WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily'""", (ticker,))
                info['requeued_generation'] = c.execute(
                    "SELECT public.enqueue_feature04_group('bonds', %s, %s, 'Daily', NULL) AS g", (ticker, last)).fetchone()['g']
        out('bond', **info); summary.append(ticker)
    except Exception as e:
        err('bond', ticker=ticker, error=f'{type(e).__name__}: {str(e)[:400]}')
out('done', bonds=len(summary), write=WRITE)
print('JOB_DONE', flush=True)
