# EXEC-UNIVERSE-BROKER L4 (user go 2026-11-05), ERRORS M349: read-only. For every Feature 04 ticker (the Daily rows of
# Feature04_Calculation_Queue), its full price history through the worker's own load_history, then
#   reference  engine.calculate (TA-Lib, as the stored history was built),
#   new chain  calculate_incremental from no checkpoint with the fixed incremental.py (TA-Lib zero tests),
#   old chain  the same with incremental.py before the fix (staged as incremental_old.py),
#   stored     the Feature_04_Technical_Indicator rows,
# and counts the values that differ from the reference per column (bootstrap_states tolerance: exact for flags and
# NULLs, 1e-10 + 1e-12 relative for numbers). Nothing is written.
# params.json: {"processes": 4, "large_write": true}  (large_write: a full read of the Feature 04 table, AGENTS.md)
# Prints OUT lines per ticker with a difference, a SUMMARY line and JOB_DONE.
from __future__ import annotations

import importlib.util
import json
import multiprocessing as mp
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'features' / 'feature04'))
import worker as W  # noqa: E402
from engine import FEATURE_COLUMNS, calculate  # noqa: E402
from incremental import calculate_incremental as new_chain  # noqa: E402

_spec = importlib.util.spec_from_file_location('incremental_old', HERE / 'features' / 'feature04' / 'incremental_old.py')
_old = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_old)
old_chain = _old.calculate_incremental

P = json.load(open('params.json'))
CANDLE = {c for c in FEATURE_COLUMNS if c.startswith('cdl_')}


def out(kind, event, **fields):
    print(f'{kind} ' + json.dumps({'event': event, **fields}, default=str), flush=True)


def same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, bool)) and isinstance(b, (int, bool)):
        return a == b
    try:
        x, y = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    return abs(x - y) <= 1e-10 + 1e-12 * abs(y)


def diff(rows, ref):
    counts, example = Counter(), {}
    for a, b in zip(rows, ref):
        for c in FEATURE_COLUMNS:
            if not same(a.get(c), b[c]):
                counts[c] += 1
                example.setdefault(c, (str(b['trade_date']), a.get(c), b[c]))
    return counts, example


def one(key):
    asset, ticker = key
    try:
        with W.connect() as conn:
            history = W.load_history(conn, asset, ticker)
            stored = {r['trade_date']: r for r in conn.execute(
                f'SELECT trade_date,{",".join(FEATURE_COLUMNS)} FROM public."Feature_04_Technical_Indicator" '
                "WHERE asset_type=%s AND ticker=%s AND timeframe='Daily'", (asset, ticker)).fetchall()}
        ref = calculate(history)
        new = new_chain(history)[0]
        old = old_chain(history)[0]
        if not (len(ref) == len(new) == len(old)):
            return dict(ticker=ticker, asset=asset, error='row counts differ')
        n, ne = diff(new, ref)
        o, oe = diff(old, ref)
        s, se = diff([stored.get(r['trade_date'], {}) for r in ref], ref)
        return dict(ticker=ticker, asset=asset, rows=len(ref), stored_rows=len(stored),
                    new=dict(n), old=dict(o), stored=dict(s), new_example=ne, old_example=oe,
                    stored_example={k: v for k, v in se.items() if k not in CANDLE})
    except Exception as error:   # reported, the run continues
        return dict(ticker=ticker, asset=asset, error=f'{type(error).__name__}: {error}'[:300])


if __name__ == '__main__':
    with W.connect() as conn:
        keys = [(r['asset_type'], r['ticker']) for r in conn.execute(
            '''SELECT DISTINCT asset_type, ticker FROM public."Feature04_Calculation_Queue"
               WHERE timeframe='Daily' ORDER BY 1, 2''').fetchall()]
    out('OUT', 'start', tickers=len(keys))
    totals = {k: Counter() for k in ('new', 'old', 'stored')}
    tickers = {k: 0 for k in totals}
    errors = []
    with mp.get_context('spawn').Pool(P.get('processes', 4)) as pool:
        for r in pool.imap_unordered(one, keys, chunksize=4):
            if 'error' in r:
                errors.append(r)
                out('ERR', 'ticker', **r)
                continue
            for k in totals:
                stored_strict = {c: v for c, v in r[k].items() if not (k == 'stored' and c in CANDLE)}
                totals[k].update(stored_strict)
                tickers[k] += bool(stored_strict)
            if r['new'] or r['old'] or {c for c in r['stored'] if c not in CANDLE}:
                out('OUT', 'ticker', **r)
    out('SUMMARY', 'compare', tickers=len(keys), errors=len(errors),
        tickers_with_difference=tickers, values=dict((k, dict(v)) for k, v in totals.items()),
        note='stored excludes candlestick flags (ERRORS M314)')
    print('JOB_DONE COMPARE', flush=True)
