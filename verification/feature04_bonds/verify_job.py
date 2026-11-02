"""Read-only check of EXEC-F04-BONDS (user 2026-11-02: "mesti ensure ya tidak di ulang dari awal ... cek ensure hasil benar").
Per bond: (1) which rows were written today (calculated_at) vs the dirty date; (2) every stored row and column equals a
full calculation by the deployed engine; (3) incremental-from-checkpoint equals full for the last sessions
(bootstrap_states.validate_recent); (4) independent recomputation (plain numpy, not the engine) of close, SMA20/50,
EMA12/26, RSI14 (Wilder), Bollinger 20/2 and MACD 12/26/9 on the rows written today."""
import json, sys, math
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from worker import connect, load_history
from engine import FEATURE_COLUMNS, calculate_with_diagnostics
from incremental import build_recent_checkpoints
from bootstrap_states import validate_recent
def out(p, **k): print('OUT ' + json.dumps({'part': p, **k}, default=str), flush=True)
def same(a, b, tol=1e-10):
    if a is None or b is None: return a is b
    if isinstance(a, (bool, int)) and isinstance(b, (bool, int)): return a == b
    x, y = float(a), float(b); return abs(x - y) <= tol + 1e-9 * abs(y)
DIRTY = {'ID01Y': date(2026, 10, 12), 'ID25Y': date(2026, 10, 12)}
REPAIR = datetime(2026, 11, 2, 16, 50, tzinfo=timezone.utc)
def sma(c, n): r = np.full(len(c), np.nan); cs = np.cumsum(np.insert(c, 0, 0.0)); r[n-1:] = (cs[n:] - cs[:-n]) / n; return r
def ema(c, n, start=0):
    r = np.full(len(c), np.nan); k = 2 / (n + 1); s = start + n - 1
    if len(c) <= s: return r
    r[s] = c[start:s+1].mean()
    for i in range(s + 1, len(c)): r[i] = c[i] * k + r[i-1] * (1 - k)
    return r
def rsi(c, n=14):
    r = np.full(len(c), np.nan); d = np.diff(c); g = np.where(d > 0, d, 0.0); l = np.where(d < 0, -d, 0.0)
    ag, al = g[:n].mean(), l[:n].mean(); r[n] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(c)):
        ag = (ag * (n-1) + g[i-1]) / n; al = (al * (n-1) + l[i-1]) / n; r[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return r
total = {'bonds': 0, 'engine_mismatch': 0, 'independent_mismatch': 0, 'old_rows_rewritten': 0}
with connect() as c:
    tickers = [r['ticker'] for r in c.execute("""SELECT DISTINCT ticker FROM public."Universe_Fixed_income" WHERE metric_type='price' ORDER BY 1""")]
for t in tickers:
    dirty = DIRTY.get(t, date(2026, 10, 21) if t.startswith('US') else date(2026, 10, 5))
    with connect() as c:
        history = load_history(c, 'bonds', t)
        stored = c.execute("""SELECT * FROM public."Feature_04_Technical_Indicator" WHERE asset_type='bonds' AND ticker=%s
            AND timeframe='Daily' ORDER BY trade_date""", (t,)).fetchall()
        lookback = int(c.execute("""SELECT DISTINCT s.correction_lookback_sessions FROM public."Universe_Fixed_income" u
            JOIN public."Fixed_Income_Market_Schedule" s ON s.country=u.country WHERE u.ticker=%s AND u.metric_type='price' AND s.enabled""", (t,)).fetchone()['correction_lookback_sessions'])
        states = build_recent_checkpoints(history, retain=lookback + 2)
        drift = validate_recent(c, 'bonds', t, history, states, lookback)
    today = [s for s in stored if s['calculated_at'] >= REPAIR]
    old = [s for s in stored if s['calculated_at'] < REPAIR]
    first_today = min((s['trade_date'] for s in today), default=None)
    rewritten_old = sum(1 for s in today if s['trade_date'] < dirty)
    rows, _ = calculate_with_diagnostics(history, calculated_at=datetime.now(timezone.utc))
    calc = {r['trade_date']: r for r in rows}
    eng_mis = [(str(s['trade_date']), col) for s in stored for col in FEATURE_COLUMNS
               if s['trade_date'] not in calc or not same(s[col], calc[s['trade_date']][col])]
    eng_mis += [(str(d), 'missing_row') for d in calc if d not in {s['trade_date'] for s in stored}]
    cl = np.array([float(h['close']) for h in history]); idx = {h['date']: i for i, h in enumerate(history)}
    e12, e26 = ema(cl, 12), ema(cl, 26); macd = e12 - e26; sig = ema(np.nan_to_num(macd, nan=0.0), 9, start=25); sig[:33] = np.nan
    s20 = sma(cl, 20); sd20 = np.array([cl[max(0, i-19):i+1].std() if i >= 19 else np.nan for i in range(len(cl))])
    ind = {'close': cl, 'sma_20': s20, 'sma_50': sma(cl, 50), 'ema_12': e12, 'ema_26': e26, 'rsi_14': rsi(cl),
           'bb_middle_20': s20, 'bb_upper_20': s20 + 2 * sd20, 'bb_lower_20': s20 - 2 * sd20, 'macd': macd, 'macd_signal': sig}
    ind_mis = []
    for s in today:
        i = idx[s['trade_date']]
        for col, arr in ind.items():
            v = arr[i]
            if (s[col] is None) != (math.isnan(v)) or (s[col] is not None and not same(s[col], v, 1e-7)):
                ind_mis.append((str(s['trade_date']), col, s[col], None if math.isnan(v) else round(float(v), 10)))
    total['bonds'] += 1; total['engine_mismatch'] += len(eng_mis); total['independent_mismatch'] += len(ind_mis); total['old_rows_rewritten'] += rewritten_old
    out('bond', ticker=t, dirty=dirty, stored_rows=len(stored), rows_written_today=len(today), first_written_today=first_today,
        rows_before_dirty_rewritten=rewritten_old, rows_untouched=len(old), oldest_untouched_calc=min((s['calculated_at'] for s in old), default=None),
        newest_untouched_calc=max((s['calculated_at'] for s in old), default=None),
        engine_mismatch=len(eng_mis), engine_sample=eng_mis[:3], incremental_vs_full_drift=len(drift),
        independent_checked=len(today) * len(ind), independent_mismatch=len(ind_mis), independent_sample=ind_mis[:3])
out('total', **total)
print('JOB_DONE', flush=True)
