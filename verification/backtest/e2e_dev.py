"""EDGE backtest: real end-to-end check in Railway dev (user approval 2026-10-26: steps 3-5 of the backtest plan).

The production page (/backtest-app/ on the dev edge-bff) runs in Chromium, signed in as the owner. Its own requests go
page -> edge-bff (job row) -> backtest-worker -> terminal-api (/bundle) -> bucket (terminal-display) -> worker ->
edge-bff (result parts) -> page. The script records every backtest API call the page makes, follows each job's status
while it runs (phase timeline), screenshots the six result tabs at three sizes, then checks the stored results through
the API: shape against contract.ts, finiteness, reconciliation (trades to cash and equity), determinism (the identical
request twice), events per ticker, a request refused at submit, cancel, the trial count, and the measurements the user
asked for (per-phase durations, payload sizes, submit -> finished).
Credentials (EDGE_LOGIN, EDGE_INITIAL_PASSWORD) are read from Railway into memory; they are never printed or saved.
Every backtest the script runs counts as a trial of its strategy line for the owner (decision K3), as any run does.

Usage:
  RAILWAY_TOKEN=... EDGE_TEST_CHROMIUM=<chrome> python e2e_dev.py OUT_DIR [--skip-page] [--only single|portfolio|cancel]
                                                     [--tickers "BBRI TLKM ..."] [--universe sector:<name>]
  EDGE_E2E_LOGIN=... EDGE_E2E_PASSWORD=... python e2e_dev.py OUT_DIR --base http://127.0.0.1:PORT   (a local stack)
  python e2e_dev.py --self-test RESULT.json [RESULT.json ...] [--request REQUEST.json]
Writes OUT_DIR/report.json (every step, its timings, sizes and checks; 'failed' lists the failed checks), the result
payloads (result-*.json), the page's recorded calls (calls.json) and the screenshots. Exit code 1 when a check failed.
--self-test runs the payload checks (contract shape, finite_everywhere, reconcile, robustness, strip_run_fields)
offline on result files; --request gives the request the results were run with (enables the checks that need it).
Portfolio: the design is changing from universes to an explicit list of 1-12 tickers (coordinator, 2026-10-27);
page_portfolio_setup() is the one place that gives the page its portfolio and must be changed when the ticker picker
lands; portfolio_body() takes either request shape (see the section "the portfolio").

Tolerances: none is chosen. A check that repeats one IEEE 754 operation of the engine on the same doubles (the payload
carries them exactly: ECMAScript Number::toString and Python's float repr both give the shortest round-trip decimal)
must match exactly. A check that compares two different summation orders is allowed U = 2**-53 (float64 unit roundoff)
times the sum of |result| over every rounding step of both computations (see reconcile()).
"""
import argparse
import copy
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

PID, EID = '8aef1702-030b-49cb-9df7-5ac2e0a42691', '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49'
VIEWPORTS = [(1600, 1000), (1280, 800), (390, 844)]
TABS = ['overview', 'returns', 'trades', 'risk', 'robust', 'list']   # results/index.ts #rtabs [data-tab]
U = 2.0 ** -53                                                    # float64 unit roundoff (round to nearest)
ENDED = ('FINISHED', 'FAILED', 'CANCELLED')                       # contract.ts JobState, backtest.py ENDED
REPO = Path(__file__).resolve().parents[2]
CORE = REPO / 'apps/edge-bff/backtest/src/core'
# the event clock's order within one calendar day (CONTRACT.md section 6, engine.ts run): open sells (held positions in
# ticker order), then the entries, then intraday sells, then close sells (time exit, end of test; ticker order)
STAGE = {'open': 0, 'buy': 1, 'intraday': 2, 'close': 3}


# ---------------------------------------------------------------------------------------------------------------------
# facts read from the code at run time (a code change shows here instead of a stale constant in this script)
# ---------------------------------------------------------------------------------------------------------------------

def _ts_source(name):
    src = (CORE / name).read_text()
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)(^|[^:])//[^\n]*', r'\1', src)


def _skip_type(s, i):
    """from i to the end of one member's type: ';' or ',' at depth 0 (consumed), or the closing '}' (not consumed)"""
    depth = 0
    while i < len(s):
        ch = s[i]
        if ch in '{([':
            depth += 1
        elif ch in '})]':
            if depth == 0:
                return i
            depth -= 1
        elif ch in ';,' and depth == 0:
            return i + 1
        i += 1
    return i


def _ts_object(s, i):
    """the members of the TypeScript object type starting at s[i] == '{': {key: (required, nested members or None)}"""
    assert s[i] == '{'
    i += 1
    tree = {}
    member = re.compile(r'\s*(\w+)(\??)\s*:\s*')
    while True:
        while i < len(s) and s[i] in ' \t\r\n;,':
            i += 1
        if s[i] == '}':
            return tree, i + 1
        m = member.match(s, i)
        if not m:                                           # an index signature or anything else: skipped
            i = _skip_type(s, i)
            continue
        i = m.end()
        sub = None
        if s[i] == '{':
            sub, i = _ts_object(s, i)
        i = _skip_type(s, i)
        tree[m.group(1)] = (m.group(2) != '?', sub)


def contract_shapes():
    """the interfaces of contract.ts this script reads, parsed from the file"""
    src = _ts_source('contract.ts')
    out = {}
    for name in ('BacktestResult', 'SeriesStats', 'TradeStats', 'Trade', 'MonteCarlo', 'Sensitivity', 'SensitivityCell',
                 'Warning', 'SkippedSignal', 'SignalTrack', 'MonthlyRow', 'AnnualRow', 'WeekdayRow', 'DrawdownPeriod',
                 'JobStatus', 'JobProgress', 'Catalog', 'Limits', 'TickerEvents'):
        m = re.search(r'export interface ' + name + r'\b[^{]*', src)
        if not m:
            raise SystemExit(f'contract.ts has no interface {name}: this script reads it')
        out[name], _ = _ts_object(src, m.end())
    return out


def lot_size():
    """the lot size the engine rounds orders to (engine.ts run, sizing: floor(budget / (fill (1 + fee)) / LOT) * LOT,
    less LOT while over the budget, below LOT insufficient_cash) and the one result.ts divides by (Trade.lots); None
    with the reason when the code does not say it in one way"""
    eng, res = _ts_source('engine.ts'), _ts_source('result.ts')
    a = re.search(r'Math\.floor\(budget / \(fill \* \(1 \+ fb\)\) / (\d+)\) \* (\d+)', eng)
    b = re.search(r'while \(shares >= (\d+) && fill \* shares \* \(1 \+ fb\) > budget\) shares -= (\d+)', eng)
    c = re.search(r'if \(shares < (\d+)\) \{ skip\(r, j, ev, \'insufficient_cash\'\)', eng)
    d = re.search(r'lots: t\.shares / (\d+)', res)
    if not (a and b and c and d):
        return None, 'the sizing lines of engine.ts or Trade.lots in result.ts changed: lot size not found'
    found = {int(x) for x in (*a.groups(), *b.groups(), *c.groups(), *d.groups())}
    if len(found) != 1:
        return None, f'engine.ts / result.ts use different lot sizes {sorted(found)}'
    return found.pop(), 'engine.ts run (sizing) and result.ts trades (lots)'


# ---------------------------------------------------------------------------------------------------------------------
# payload checks (offline: --self-test runs them on files)
# ---------------------------------------------------------------------------------------------------------------------

def finite_everywhere(value, path='$'):
    """paths of non-finite numbers (the contract sends null for 'no value', never NaN or Infinity)"""
    bad = []
    if isinstance(value, float) and not math.isfinite(value):
        bad.append(path)
    elif isinstance(value, dict):
        for k, v in value.items():
            bad += finite_everywhere(v, f'{path}.{k}')
    elif isinstance(value, list):
        for i, v in enumerate(value):
            bad += finite_everywhere(v, f'{path}[{i}]')
    return bad


def _shape(obj, tree, path, out):
    if not isinstance(obj, dict):
        out.append(f'{path}: not an object')
        return
    for k, (required, sub) in tree.items():
        if k not in obj:
            if required:
                out.append(f'{path}.{k}: missing')
        elif sub is not None and isinstance(obj[k], dict):
            _shape(obj[k], sub, f'{path}.{k}', out)
    out += [f'{path}.{k}: not in contract.ts' for k in obj if k not in tree]


def result_shape(res, shapes, core=False):
    """every key of the result against contract.ts (BacktestResult and the interfaces it names): missing required keys
    and keys the contract does not have. core: the /result answer of a portfolio run (BacktestResultCore, without
    events.conditions and events.exits)."""
    out = []
    top = copy.deepcopy(shapes['BacktestResult'])
    if core:
        ev = top['events'][1]
        ev['conditions'], ev['exits'] = (False, None), (False, None)
    _shape(res, top, '$', out)

    def each(items, name, path, nullable=False):
        if items is None and nullable:
            return
        for i, x in enumerate(items if isinstance(items, list) else [items]):
            _shape(x, shapes[name], f'{path}[{i}]' if isinstance(items, list) else path, out)
    st, ts, tb, rb = res.get('stats', {}), res.get('trade_stats', {}), res.get('tables', {}), res.get('robustness', {})
    each(st.get('all'), 'SeriesStats', '$.stats.all')
    each(st.get('benchmark'), 'SeriesStats', '$.stats.benchmark')
    each(st.get('in_sample'), 'SeriesStats', '$.stats.in_sample', True)
    each(st.get('out_of_sample'), 'SeriesStats', '$.stats.out_of_sample', True)
    each(ts.get('all'), 'TradeStats', '$.trade_stats.all')
    each(ts.get('in_sample'), 'TradeStats', '$.trade_stats.in_sample')
    each(ts.get('out_of_sample'), 'TradeStats', '$.trade_stats.out_of_sample', True)
    each(res.get('trades', []), 'Trade', '$.trades')
    each(res.get('meta', {}).get('warnings', []), 'Warning', '$.meta.warnings')
    each(res.get('events', {}).get('skipped', []), 'SkippedSignal', '$.events.skipped')
    for t, track in (res.get('events', {}).get('entries') or {}).items():
        _shape(track, shapes['SignalTrack'], f'$.events.entries.{t}', out)
    for name, key in (('MonthlyRow', 'monthly'), ('AnnualRow', 'annual'), ('WeekdayRow', 'weekday'), ('DrawdownPeriod', 'drawdowns')):
        each(tb.get(key, []), name, f'$.tables.{key}')
    each(rb.get('monte_carlo'), 'MonteCarlo', '$.robustness.monte_carlo', True)
    each(rb.get('sensitivity'), 'Sensitivity', '$.robustness.sensitivity', True)
    for y, row in enumerate((rb.get('sensitivity') or {}).get('cells') or []):
        for x, c in enumerate(row):
            if c is not None:
                _shape(c, shapes['SensitivityCell'], f'$.robustness.sensitivity.cells[{y}][{x}]', out)
    return out


def _fold(xs):
    """the core's left-to-right sum from 0 (stats.ts mean, result.ts sumPnl, tradeStats): the same doubles in the same
    order give the same bits"""
    s = 0.0
    for x in xs:
        s = s + float(x)
    return s


def _mean(xs):
    xs = list(xs)
    return _fold(xs) / (len(xs) or 1)                    # stats.ts mean: s / (a.length || 1)


def reconcile(res, capital=None, request=None, lot=None):
    """Trades to cash and equity, from the payload alone (plus the request where a check needs it). Returns
    {'checks': {name: {'ok', ...}}, 'not_derivable': {name: why}}.

    Exact (one engine operation on the same doubles, or the same left-to-right sum in the same order):
      pnl = proceeds - cost, return = pnl / cost (engine.ts sell), cost = fill x shares x (1 + buy_fee) and proceeds
      = fill x shares x (1 - sell_fee) (engine.ts entry/sell; needs the request), exposure in [0, 1] (exposure =
      mv / fl(cash + mv) with cash >= 0, so mv <= equity exactly), exposure 0 exactly on the days no position is held
      at the close, equity[0] = benchmark[0] = capital (result.ts: bench = close / b0 x cap0; no entry on day 0), the
      per-ticker and exit-reason tables and trade_stats sums (result.ts sumPnl / stats.ts tradeStats, trade order), the
      cash path replayed in the engine's order and the equity on every flat day (single mode: one position, so the
      order of every cash operation is known).
    Bounded (a different summation order): final equity vs capital + fsum(pnl): U x (sum |pnl_i| (each pnl rounded
      once) + sum over cash operations of |cash after| (each rounded once) + |capital + sum pnl| (fsum rounds once));
      the cash on a day with positions, derived as equity - equity x exposure: U x 4 x (|equity| + |mv| + |cash|) (four
      roundings: cash + mv, mv / equity, equity x exposure, the subtraction); a portfolio day with two or more entries
      (their rank order is not in the payload): from then on 2 U |cash after| per operation."""
    C, ND = {}, {}
    out = {'checks': C, 'not_derivable': ND}

    def check(name, ok, **detail):
        C[name] = {'ok': bool(ok), **detail}
    dates, eq, ex, bench, T = res['dates'], res['equity'], res['exposure'], res['benchmark'], res['trades']
    n = len(dates)
    idx = {d: k for k, d in enumerate(dates)}
    single = res['meta']['mode'] == 'single'
    if capital is None:
        capital = float(bench[0])
        out['capital_from'] = 'benchmark[0] (result.ts: bench = close / b0 x capital, so bench[0] is the capital exactly)'
    else:
        capital = float(capital)
        out['capital_from'] = 'request.sizing.capital_idr'
        check('benchmark0_is_capital', float(bench[0]) == capital)
    check('series_lengths', len(eq) == len(ex) == len(bench) == len(res['drawdown']) == n and len(res['daily_returns']) == n - 1
          and len(set(dates)) == n and dates == sorted(dates), dates=n)
    off = [t['trade_id'] for t in T if not {t['signal_date'], t['entry_date'], t['exit_date']} <= idx.keys()]
    check('trade_dates_on_calendar', not off, bad=off[:5])
    if off:
        return out

    # ---- each trade on its own: identities of engine.ts sell / entry, lots, dates, events
    pnl_bad = [t['trade_id'] for t in T if float(t['proceeds_idr']) - float(t['cost_idr']) != float(t['pnl_idr'])]
    check('pnl_is_proceeds_minus_cost_exact', not pnl_bad, bad=len(pnl_bad), first=pnl_bad[:3])
    ret_bad = [t['trade_id'] for t in T if float(t['pnl_idr']) / float(t['cost_idr']) != float(t['return'])]
    check('return_is_pnl_over_cost_exact', not ret_bad, bad=len(ret_bad), first=ret_bad[:3])
    if request:
        fb, fs = request['costs']['buy_fee'], request['costs']['sell_fee']
        cb = [t['trade_id'] for t in T if float(t['entry_price']) * t['shares'] * (1 + fb) != float(t['cost_idr'])]
        pb = [t['trade_id'] for t in T if float(t['exit_price']) * t['shares'] * (1 - fs) != float(t['proceeds_idr'])]
        check('cost_is_fill_x_shares_x_fee_exact', not cb, bad=len(cb), first=cb[:3])
        check('proceeds_is_fill_x_shares_x_fee_exact', not pb, bad=len(pb), first=pb[:3])
    else:
        ND['cost_and_proceeds_from_fills'] = 'needs request.costs.buy_fee / sell_fee (not in the result)'
    ND['fills_from_prices'] = ('entry_price = open x (1 + slippage) and exit_price = level x (1 - slippage) need the bars '
                               '(open, high, low, close), which the result does not carry')
    if lot:
        lb = [t['trade_id'] for t in T if not (isinstance(t['shares'], int) and t['shares'] >= lot and t['shares'] % lot == 0
                                               and t['lots'] == t['shares'] / lot and float(t['lots']).is_integer())]
        check('whole_lots', not lb, lot=lot, bad=len(lb), first=lb[:3])
    else:
        ND['whole_lots'] = 'lot size not found in the code (lot_size())'
    seq = [t['trade_id'] for t in T if not (idx[t['entry_date']] == idx[t['signal_date']] + 1 <= idx[t['exit_date']] and t['bars_held'] >= 1)]
    check('entry_next_calendar_day_after_signal', not seq, bad=len(seq), first=seq[:3])   # engine.ts: orders[kj + 1]
    check('no_entry_on_first_day', all(idx[t['entry_date']] > 0 for t in T))

    entries = res['events']['entries']
    linked, used = [], {}
    for t in T:
        on = (entries.get(t['ticker']) or {}).get('on', [])
        k = t['signal_event']
        if not (0 <= k < len(on) and on[k] == idx[t['signal_date']]):
            linked.append(t['trade_id'])
        used.setdefault(t['ticker'], []).append(k)
    check('trade_points_at_its_entry_event', not linked, bad=len(linked), first=linked[:3])
    for s in res['events']['skipped']:
        used.setdefault(s['ticker'], []).append(s['signal_event'])
    unaccounted = {tk: len(tr.get('on', [])) for tk, tr in entries.items() if sorted(used.get(tk, [])) != list(range(len(tr.get('on', []))))}
    # every entry event inside the period is an order or a skipped signal, and every order is a trade or skipped
    # (engine.ts: events -> orders[kj + 1] | skip; orders -> skip | position; every position is sold by end_of_test)
    check('every_entry_event_traded_or_skipped_once', not unaccounted, tickers_off=list(unaccounted)[:5])

    # ---- per ticker: no overlap, and at most max_positions at once
    over = []
    by = {}
    for t in T:
        by.setdefault(t['ticker'], []).append(t)
    for tk, ts in by.items():
        ts = sorted(ts, key=lambda t: (idx[t['entry_date']], idx[t['exit_date']]))
        for a, b in zip(ts, ts[1:]):
            ka, kb = idx[a['exit_date']], idx[b['entry_date']]
            # a new entry of the ticker needs the old position sold: at an earlier day, or at this day's open (open
            # sells come before the entries); an intraday or close sale that day happens after the entries
            if not (kb > ka or (kb == ka and a['exit_phase'] == 'open')):
                over.append(b['trade_id'])
    check('no_overlapping_trades_per_ticker', not over, bad=len(over), first=over[:3])
    if single:
        max_pos, why = 1, 'single mode (engine.ts: maxPos = single ? 1 : max_positions)'
    elif request:
        max_pos, why = request['portfolio']['max_positions'], 'request.portfolio.max_positions'
    elif res['robustness']['monte_carlo'] and float(1 / res['robustness']['monte_carlo']['scale']).is_integer():
        max_pos, why = int(1 / res['robustness']['monte_carlo']['scale']), 'robustness.monte_carlo.scale = 1 / max_positions'
    else:
        max_pos, why = None, None
        ND['max_positions'] = 'portfolio without the request or a Monte Carlo scale'

    # ---- the cash path, replayed in the engine's order
    ops = []
    for i, t in enumerate(T):
        ops.append((idx[t['entry_date']], STAGE['buy'], t['ticker'], i, -float(t['cost_idr'])))
        ops.append((idx[t['exit_date']], STAGE[t['exit_phase']], t['ticker'], i, float(t['proceeds_idr'])))
    ops.sort(key=lambda o: o[:3])
    buys_per_day = {}
    for o in ops:
        if o[1] == STAGE['buy']:
            buys_per_day[o[0]] = buys_per_day.get(o[0], 0) + 1
    cash, err, diverged, abs_after, min_cash, k_min = capital, 0.0, False, 0.0, capital, None
    open_at = [0] * (n + 1)                     # positions held at the close of each day (difference array)
    peak_held, held_now, held_after_buys = 0, 0, {}
    for t in T:
        open_at[idx[t['entry_date']]] += 1
        open_at[idx[t['exit_date']]] -= 1
    flat_ok, flat_bad, expo_bad, mid_bad, worst = 0, [], [], [], 0.0
    j = 0
    for k in range(n):
        if buys_per_day.get(k, 0) > 1:
            diverged = True                     # rank order of the entries unknown: rounding of this day's sums may differ
        while j < len(ops) and ops[j][0] == k:
            stage, amount = ops[j][1], ops[j][4]
            cash = cash + amount
            abs_after += abs(cash)
            if diverged:
                err += 2 * U * abs(cash)
            if cash < min_cash:
                min_cash, k_min = cash, k
            if stage == STAGE['buy']:
                held_after_buys[k] = held_after_buys.get(k, 0) + 1
            j += 1
        held_now += open_at[k]
        if k in held_after_buys:
            # held right after the open's entries: the ones held at the close of k-1, less the open sells of k, plus k's buys
            sold_open = sum(1 for o in ops if o[0] == k and o[1] == STAGE['open'])
            peak_held = max(peak_held, (held_now - open_at[k]) - sold_open + held_after_buys[k])
        peak_held = max(peak_held, held_now)
        e, x = float(eq[k]), float(ex[k])
        if not (0.0 <= x <= 1.0):
            expo_bad.append(k)
        if held_now == 0:
            if x != 0.0:
                expo_bad.append(k)
            if (e == cash) if err == 0 else abs(e - cash) <= err:
                flat_ok += 1
            else:
                flat_bad.append((dates[k], e - cash))
        else:
            if not x > 0.0:
                expo_bad.append(k)
            mv = e * x
            derived = e - mv
            tol = 4 * U * (abs(e) + abs(mv) + abs(derived)) + err
            worst = max(worst, abs(derived - cash) / tol)
            if abs(derived - cash) > tol:
                mid_bad.append((dates[k], derived - cash))
    check('exposure_in_0_1_and_zero_exactly_when_flat', not expo_bad, bad_days=[dates[k] for k in expo_bad[:5]])
    check('cash_never_negative', min_cash >= -err, min_cash=min_cash, on=dates[k_min] if k_min is not None else None,
          replay='exact' if not diverged else 'bounded')
    check('equity_equals_replayed_cash_on_flat_days', not flat_bad, flat_days=flat_ok, bad=len(flat_bad), first=flat_bad[:3],
          exact=err == 0)
    check('cash_from_equity_and_exposure_matches_replay', not mid_bad, days_with_positions=n - flat_ok - len(flat_bad),
          bad=len(mid_bad), first=mid_bad[:3], worst_error_over_bound=worst)
    if max_pos is not None:
        check('positions_within_max_positions', peak_held <= max_pos, peak=peak_held, max_positions=max_pos, from_=why)
    ends_flat = held_now == 0 and float(ex[-1]) == 0.0
    check('ends_flat', ends_flat)
    check('day0_equity_is_capital', float(eq[0]) == capital)
    if ends_flat:
        pnl = [float(t['pnl_idr']) for t in T]
        total = math.fsum([capital] + pnl)
        tol = U * (math.fsum(abs(p) for p in pnl) + abs_after + abs(total)) + err
        check('final_equity_is_capital_plus_fsum_pnl', abs(float(eq[-1]) - total) <= tol, final_equity=eq[-1],
              capital_plus_pnl=total, diff=float(eq[-1]) - total, bound=tol)

    # ---- tables and trade statistics from the trades (result.ts perTicker / exitReasons, stats.ts tradeStats)
    rows = {r['ticker']: r for r in res['tables']['per_ticker']}
    pt_bad = []
    for tk, ts in by.items():
        r = rows.get(tk)
        if not r or r['trades'] != len(ts) or r['wins'] != sum(1 for t in ts if t['return'] > 0) or float(r['pnl_idr']) != _fold(t['pnl_idr'] for t in ts):
            pt_bad.append(tk)
    pt_bad += [tk for tk, r in rows.items() if tk not in by and (r['trades'] or r['pnl_idr'])]
    check('per_ticker_table_from_trades_exact', not pt_bad, bad=pt_bad[:5])
    check('per_ticker_tickers_are_meta_tickers', sorted(rows) == sorted(res['meta']['tickers']))
    groups = {}
    for t in T:
        groups.setdefault(t['exit_reason'], []).append(t)
    er = res['tables']['exit_reasons']
    er_ok = [g['reason'] for g in er] == list(groups) and all(
        g['trades'] == len(groups[g['reason']]) and g['wins'] == sum(1 for t in groups[g['reason']] if t['return'] > 0)
        and float(g['pnl_idr']) == _fold(t['pnl_idr'] for t in groups[g['reason']])
        and float(g['avg_return']) == _mean(t['return'] for t in groups[g['reason']])
        and float(g['avg_bars']) == _mean(t['bars_held'] for t in groups[g['reason']]) for g in er)
    check('exit_reasons_table_from_trades_exact', er_ok)
    w = [t for t in T if t['return'] > 0]
    los = [t for t in T if t['return'] <= 0]
    gp, gl = _fold(t['pnl_idr'] for t in w), -_fold(t['pnl_idr'] for t in los)
    a = res['trade_stats']['all']
    check('trade_stats_all_from_trades_exact', a['n'] == len(T) and a['wins'] == len(w) and a['losses'] == len(los)
          and float(a['gross_profit_idr']) == gp and float(a['gross_loss_idr']) == gl and float(a['net_idr']) == gp - gl)
    cut = res['oos']['cut']
    f = res['oos']['fraction']
    cut_ok = cut == (math.floor(n * (1 - f)) if f else n) and res['oos']['cut_date'] == (dates[cut - 1] if cut >= 1 else None)
    cut_day = cut - 1 if cut >= 1 else None
    ins = [t for t in T if cut_day is None or idx[t['entry_date']] <= cut_day]
    tso = res['trade_stats']['out_of_sample']
    check('oos_cut_and_trade_split', cut_ok and res['trade_stats']['in_sample']['n'] == len(ins)
          and (tso is None or tso['n'] == len(T) - len(ins)))

    # ---- the daily series from the equity (stats.ts seriesStats)
    r_ok = all(float(res['daily_returns'][k - 1]) == float(eq[k]) / float(eq[k - 1]) - 1 for k in range(1, n))
    peak, dd_ok, mdd = float(eq[0]), True, 0.0
    for k in range(n):
        peak = max(peak, float(eq[k]))
        d = float(eq[k]) / peak - 1
        dd_ok &= float(res['drawdown'][k]) == d
        mdd = min(mdd, d)
    s_all = res['stats']['all']
    check('daily_returns_drawdown_and_totals_from_equity_exact', r_ok and dd_ok and s_all['n_returns'] == n - 1
          and float(s_all['total_return']) == float(eq[-1]) / float(eq[0]) - 1 and float(s_all['max_drawdown']) == mdd
          and float(res['stats']['benchmark']['total_return']) == float(bench[-1]) / float(bench[0]) - 1
          and float(res['stats'].get('exposure_mean', 0.0)) == _mean(ex))
    return out


def robustness_checks(res, request=None):
    """Monte Carlo replayed in full (robustness.ts monteCarlo: the page's LCG and products, the same doubles), the
    sensitivity grid's size and its base cell against the run, and the trial bookkeeping (robustness.ts trialSet)."""
    C, ND = {}, {}
    out = {'checks': C, 'not_derivable': ND}

    def check(name, ok, **detail):
        C[name] = {'ok': bool(ok), **detail}
    T, rb, meta = res['trades'], res['robustness'], res['meta']
    mc = rb['monte_carlo']
    runs_req = request['robustness']['monte_carlo_runs'] if request else None
    if len(T) < 3 or runs_req == 0:
        check('monte_carlo_null_below_3_trades_or_off', mc is None)
    elif mc is None:
        check('monte_carlo_present', False, trades=len(T))
    else:
        if request:
            scale = request['sizing']['allocation_fraction'] if request['mode'] == 'single' else 1 / request['portfolio']['max_positions']
            check('monte_carlo_settings_are_the_request', mc['runs'] == runs_req and mc['seed'] == request['robustness']['seed']
                  and float(mc['scale']) == scale, runs=mc['runs'])
        n, runs, scale, s2 = len(T), mc['runs'], float(mc['scale']), mc['seed']
        rets = [float(t['return']) for t in T]
        paths, fin, mdds = [], [], []
        for _ in range(runs):
            v, pk, md, path = 1.0, 1.0, 0.0, [1.0]
            for _ in range(n):
                s2 = (s2 * 1664525 + 1013904223) & 0xFFFFFFFF       # Math.imul(s2, 1664525) + 1013904223 >>> 0
                v *= 1 + rets[math.floor(s2 / 4294967296 * n)] * scale
                pk = max(pk, v)
                md = min(md, v / pk - 1)
                path.append(v)
            paths.append(path)
            fin.append(v - 1)
            mdds.append(md)
        actual = [1.0]
        for x in rets:
            actual.append(actual[-1] * (1 + x * scale))
        bands_ok, below_ok = True, True
        for j in range(n + 1):
            col = sorted(p[j] for p in paths)
            for key, q in (('p05', .05), ('p25', .25), ('p50', .5), ('p75', .75), ('p95', .95)):
                bands_ok &= float(mc['bands'][key][j]) == col[min(runs - 1, max(0, math.floor(q * (runs - 1))))]
            below_ok &= float(mc['below_start'][j]) == sum(1 for p in paths if p[j] < 1) / runs
        check('monte_carlo_replayed_exact', mc['n_trades'] == n and [float(x) for x in mc['actual']] == actual
              and [float(x) for x in mc['final_returns']] == fin and [float(x) for x in mc['max_drawdowns']] == mdds
              and bands_ok and below_ok, runs=runs, n_trades=n)
    s = rb['sensitivity']
    if request and not request['robustness']['sensitivity']:
        check('sensitivity_null_when_off', s is None)
    if s is not None:
        cells = [c for row in s['cells'] for c in row]
        filled = sum(1 for c in cells if c is not None)
        check('sensitivity_grid_5x5', len(s['cells']) == 5 and all(len(r) == 5 for r in s['cells']) and len(s['xs']) == 5
              and len(s['ys']) == 5, filled_cells=filled)
        mid = s['cells'][2][2]
        base = s['xs'][2] == s['base_x'] and s['ys'][2] == s['base_y']
        st, ta = res['stats']['all'], res['trade_stats']['all']
        if mid is not None:
            same = (mid['sharpe'] == st['sharpe'] and mid['cagr'] == st['cagr'] and mid['max_drawdown'] == st['max_drawdown']
                    and mid['trades'] == ta['n'] and mid['profit_factor'] == ta['profit_factor'])
            # result.ts: a cell equal to the run is the run (run.ts: runs.set(variant_hash, ledger)); cellStats = the
            # run's seriesStats / tradeStats numbers
            check('sensitivity_base_cell_is_the_run', same if base else True, base_cell_is_run_variant=base, equal=same)
        variants = meta['trials']['variants']
        check('trial_variants_distinct_run_first', len({v['variant_hash'] for v in variants}) == len(variants)
              and variants and variants[0]['kind'] == 'run' and len(variants) <= 1 + filled, variants=len(variants))
    tr, d = meta['trials'], rb['deflated']
    check('trials_total_prior_plus_this_run', tr['total'] == tr['prior'] + tr['this_run'] and d['trials'] == tr['total']
          and d['sharpe_variance_from'] == ('trials' if tr['total'] > 1 else 'sample'), **{k: tr[k] for k in ('prior', 'this_run', 'total')})
    return out


# What may differ between two runs of the identical request (everything else must be equal, bit for bit):
RUN_FIELDS = [
    ('meta.duration_ms', 'wall time of the computation: run.ts runJob result.meta.duration_ms = Math.round(now() - t0); '
                         'run.ts header: "Deterministic ... (meta.duration_ms aside)"'),
    ('meta.trials.prior', 'distinct variants the line had before this run: robustness.ts trialSet(prior, ...), the prior '
                          'trials edge-bff passes (backtest.py prior_trials: what earlier runs of the owner recorded)'),
    ('meta.trials.this_run', 'this run\'s variants not seen before (robustness.ts trialSet): 0 for a repeat'),
]


def strip_run_fields(result):
    """the result without the fields of RUN_FIELDS; meta.trials.total, the variants, the Deflated Sharpe and every
    number computed from them must stay equal (K3: the repeat adds no new variant, and trialSet keeps the prior order
    then this run's own Sharpes, so the Sharpe list is the same)"""
    r = copy.deepcopy(result)
    for path, _ in RUN_FIELDS:
        *head, last = path.split('.')
        o = r
        for k in head:
            o = o.get(k, {})
        o.pop(last, None)
    return r


def diff_paths(a, b, path='$', out=None, limit=20):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f'{path}.{k}: only in {"first" if k in a else "second"}')
            else:
                diff_paths(a[k], b[k], f'{path}.{k}', out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f'{path}: length {len(a)} != {len(b)}')
        for i, (x, y) in enumerate(zip(a, b)):
            diff_paths(x, y, f'{path}[{i}]', out, limit)
    elif a != b or type(a) is not type(b) and not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
        out.append(path)
    return out


def payload_checks(res, shapes, lot, capital=None, request=None, core=False):
    bad_shape = result_shape(res, shapes, core)
    out = {'shape_vs_contract': {'ok': not bad_shape, 'problems': bad_shape[:20]},
           'non_finite': finite_everywhere(res)[:10]}
    if bad_shape:
        return out                              # the checks below read the contract's fields
    out['reconcile'] = reconcile(res, capital, request, lot)
    out['robustness'] = robustness_checks(res, request)
    return out


def failures(checks, prefix=''):
    """names of failed checks in a nested report"""
    out = []
    if isinstance(checks, dict):
        if 'ok' in checks and isinstance(checks['ok'], bool) and not checks['ok']:
            out.append(prefix.strip('.'))
        for k, v in checks.items():
            if k != 'ok':
                out += failures(v, f'{prefix}.{k}')
    if prefix.endswith('.non_finite') and checks:
        out.append(prefix.strip('.'))
    return out


def self_test(paths, request_path=None):
    shapes, (lot, lot_from) = contract_shapes(), lot_size()
    request = json.loads(Path(request_path).read_text()) if request_path else None
    report = {'lot_size': lot, 'lot_size_from': lot_from, 'stripped_fields': RUN_FIELDS, 'payloads': {}}
    for p in paths:
        res = json.loads(Path(p).read_text())
        req = None
        if request and request.get('mode') == res['meta']['mode']:     # a request of another mode is not this run's
            req = copy.deepcopy(request)
            if req['mode'] == 'single':
                req['single']['ticker'] = res['meta']['tickers'][0]
        core = res['meta']['mode'] == 'portfolio' and 'conditions' not in res['events']
        out = payload_checks(res, shapes, lot, req and req['sizing']['capital_idr'], req, core)
        # strip_run_fields: equal after changing only the stripped fields, different after changing anything else
        a = copy.deepcopy(res)
        a['meta']['duration_ms'] += 1
        a['meta']['trials']['prior'] += 3
        a['meta']['trials']['this_run'] -= 3
        b = copy.deepcopy(res)
        b['meta']['trials']['total'] += 1
        out['strip_run_fields'] = {'ok': strip_run_fields(a) == strip_run_fields(res) and strip_run_fields(b) != strip_run_fields(res)
                                   and diff_paths(strip_run_fields(b), strip_run_fields(res)) == ['$.meta.trials.total']}
        out['facts'] = {'mode': res['meta']['mode'], 'tickers': len(res['meta']['tickers']), 'days': len(res['dates']),
                        'trades': len(res['trades']), 'json_bytes': len(Path(p).read_bytes()),
                        'gzip6_bytes': len(gzip.compress(Path(p).read_bytes(), 6))}
        out['failed'] = failures(out)
        report['payloads'][os.path.basename(p)] = out
    print(json.dumps(report, indent=1, default=str))
    return all(not v['failed'] for v in report['payloads'].values())


# ---------------------------------------------------------------------------------------------------------------------
# Railway and the API
# ---------------------------------------------------------------------------------------------------------------------

def gql(query, variables):
    req = urllib.request.Request('https://backboard.railway.com/graphql/v2', json.dumps({'query': query, 'variables': variables}).encode(),
                                 {'Content-Type': 'application/json', 'Project-Access-Token': os.environ['RAILWAY_TOKEN'],
                                  'User-Agent': 'saniti-backtest-e2e/1'})
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    if body.get('errors') or not body.get('data'):
        raise SystemExit('Railway GraphQL refused a query: ' + '; '.join(str(e.get('message'))[:200] for e in body.get('errors') or [{}]))
    return body['data']


def service_vars(name):
    sid = {e['node']['name']: e['node']['id'] for e in gql('query($id:String!){project(id:$id){services{edges{node{id name}}}}}',
                                                            {'id': PID})['project']['services']['edges']}[name]
    return gql('query($p:String!,$e:String!,$s:String!){variables(projectId:$p,environmentId:$e,serviceId:$s)}',
               {'p': PID, 'e': EID, 's': sid})['variables']


def iso_s(a, b):
    """seconds between two edge-bff timestamps (JobStatus created_at / started_at / finished_at, ISO 8601)"""
    from datetime import datetime
    if not a or not b:
        return None
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds(), 3)


class Api:
    """The public backtest API with the browser context's session cookie (the same session the page uses). POSTs carry
    Origin (main.py protections: must equal EDGE_PUBLIC_ORIGIN) and X-CSRF-Token (main.py write)."""

    def __init__(self, ctx, base, csrf, pause):
        self.ctx, self.base, self.csrf, self.pause = ctx, base, csrf, pause

    def get(self, path):
        t0 = time.monotonic()
        r = self.ctx.request.get(self.base + path, timeout=300_000, headers={'Accept-Encoding': 'gzip'})
        body = r.body()
        wire = r.headers.get('content-length')
        if body[:2] == b'\x1f\x8b':                          # not decoded by the client: the gzip part as stored
            wire, body = len(body), gzip.decompress(body)
        return r.status, body, {'ms': round((time.monotonic() - t0) * 1000), 'json_bytes': len(body),
                                'wire_bytes': int(wire) if wire is not None else None,
                                'content_encoding': r.headers.get('content-encoding')}

    def post(self, path, body):
        r = self.ctx.request.post(self.base + path, data=json.dumps(body), timeout=300_000,
                                  headers={'Content-Type': 'application/json', 'Origin': self.base, 'X-CSRF-Token': self.csrf})
        try:
            return r.status, r.json()
        except Exception:
            return r.status, {}

    def json(self, path):
        status, body, _ = self.get(path)
        return status, json.loads(body or b'{}')

    def submit(self, body):
        """POST /api/v1/backtests without a client_request_id: edge-bff makes a new submission key (backtest.py submit:
        'auto:' + token), so it is always a new job; the page's client_request_id would return the page's job"""
        body = {k: v for k, v in body.items() if k != 'client_request_id'}
        t0 = time.monotonic()
        status, ans = self.post('/api/v1/backtests', body)
        return status, ans, t0

    def follow(self, request_id, t0, limit_s, every=0.5):
        """the job's status until it ends: a timeline [seconds since t0, state, phase, done, total] at each change of
        (state, phase), with the phase's last done/total. edge-bff stores the worker's progress at each of its polls
        (backtest.py BacktestLoop.follow, every EDGE_POLL_SECONDS), so a phase shorter than one poll can be missed and
        every boundary is known to about one poll."""
        seen, st = [], {}
        while True:
            code, st = self.json(f'/api/v1/backtests/{request_id}')
            if code != 200:
                return {'status': code, **st}, seen
            p = st.get('progress') or {}
            mark = (st.get('state'), p.get('phase'), p.get('done'), p.get('total'))
            now = round(time.monotonic() - t0, 2)
            if not seen or tuple(seen[-1][1:3]) != mark[:2]:
                seen.append([now, *mark])
            else:
                seen[-1][3:] = mark[2:]
            if st.get('state') in ENDED or now > limit_s:
                return st, seen
            self.pause(every)


def phase_durations(timeline):
    """seconds per (state, phase) from the status timeline: from its first sighting to the next one's"""
    return [{'state': a[1], 'phase': a[2], 'from_s': a[0], 'seconds': None if b is None else round(b[0] - a[0], 2),
             'done': a[3], 'total': a[4]} for a, b in zip(timeline, timeline[1:] + [None])]


def timings(st, timeline, submit_ms=None):
    return {'submit_ms': submit_ms, 'submit_to_ended_s': timeline[-1][0] if timeline else None,
            'queued_s': iso_s(st.get('created_at'), st.get('started_at')),
            'running_s': iso_s(st.get('started_at'), st.get('finished_at')),
            'worker_duration_ms': st.get('duration_ms'), 'stored_result_bytes': st.get('result_bytes'),
            'phases': phase_durations(timeline)}


# ---------------------------------------------------------------------------------------------------------------------
# the portfolio: the only part that knows how a portfolio is given its tickers
# ---------------------------------------------------------------------------------------------------------------------
# The user changed the design (coordinator, 2026-10-27): a portfolio becomes an explicit list of 1-12 tickers the user
# picks, replacing the universes ('all' | 'sector:<name>', contract.ts BacktestRequest.portfolio.universe as this
# script was written). The two functions below handle both shapes where the shape can be read (a request that has
# portfolio.tickers or portfolio.universe); the page's ticker picker does not exist yet, so page_portfolio_setup must be
# changed when it lands (it reports the missing Universe select instead of guessing a new DOM).
# The measurement's worst case: the 12 stocks with the largest broker files (~2.49M broker rows; coordinator).
WORST_CASE_TICKERS = ('BBRI', 'TLKM', 'BBCA', 'ASII', 'BMRI', 'ANTM', 'ADRO', 'PGAS', 'BBNI', 'BUMI', 'BRPT', 'UNVR')


def portfolio_pick(args, cat):
    """what the portfolio step runs on, for either shape: the tickers (--tickers, else WORST_CASE_TICKERS) and the
    universe (--universe, else the catalog sector with the most tickers that is not 'all')"""
    tickers = args.tickers.replace(',', ' ').split() if args.tickers else list(WORST_CASE_TICKERS)
    universes = cat.get('universes') or []
    sectors = sorted((u for u in universes if u['id'] != 'all'), key=lambda u: (-u['tickers'], u['id']))
    universe = args.universe or (sectors[0]['id'] if sectors else None)
    if universe is not None and universe not in {u['id'] for u in universes}:
        raise SystemExit(f'universe {universe} is not in the catalog')
    known = {t['ticker'] for t in cat['tickers']}
    return {'tickers': tickers, 'tickers_from': '--tickers' if args.tickers else 'WORST_CASE_TICKERS',
            'tickers_not_in_catalog': [t for t in tickers if t not in known], 'tickers_given': bool(args.tickers),
            'universe': universe, 'universe_from': '--universe' if args.universe else 'the catalog sector with the most tickers',
            'universe_tickers': next((u['tickers'] for u in universes if u['id'] == universe), None)}


def portfolio_body(template, pick):
    """an API request of a portfolio on the pick, in the template's own shape: portfolio.tickers (the ticker-list
    portfolio) or portfolio.universe (contract.ts as written). Returns (body, what was used)."""
    body = copy.deepcopy(template)
    p = body['portfolio']
    if 'tickers' in p:
        p['tickers'] = list(pick['tickers'])
        return body, {'tickers': p['tickers']}
    if 'universe' in p:
        p['universe'] = pick['universe']
        return body, {'universe': p['universe'], **({'not_applied': 'the request has portfolio.universe, no ticker list: '
                                                                    '--tickers not used'} if pick['tickers_given'] else {})}
    raise RuntimeError('the portfolio request has neither tickers nor universe: update portfolio_body()')


def page_portfolio_setup(page, pick):
    """THE ONE PLACE THAT KNOWS HOW THE PAGE IS SWITCHED TO PORTFOLIO AND GIVEN ITS TICKERS. As the page is written
    (builder.ts): the view tab #viewSeg [data-v="signals"], the summary row #sumbox [data-st="1"] (goStep 1), the mode
    switch #modeSeg [data-m="portfolio"], then step 1's Universe select [data-k="universe"] (its option values are the
    catalog universe ids). TO CHANGE when the ticker-list portfolio lands: pick pick['tickers'] in its picker."""
    page.click('#viewSeg [data-v="signals"]')
    page.click('#sumbox [data-st="1"]')
    page.click('#modeSeg [data-m="portfolio"]')
    sel = '#builder select[data-k="universe"]'
    if page.query_selector(sel) is None:
        raise RuntimeError('the page has no Universe select (the ticker-list portfolio?): update page_portfolio_setup() '
                           'to pick the --tickers in the new picker')
    page.select_option(sel, pick['universe'])
    return {'universe': pick['universe'], **({'not_applied': 'the page has universes only: --tickers not used'}
                                              if pick['tickers_given'] else {})}


def preview_matches(body, used):
    """whether a signals preview request (SignalsPreviewRequest) is the one of this portfolio"""
    return all(body.get(k) == v for k, v in used.items() if k in ('universe', 'tickers'))


# ---------------------------------------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out', nargs='?')
    ap.add_argument('--skip-page', action='store_true', help='no browser run: the API runs the latest stored requests')
    ap.add_argument('--only', choices=['single', 'portfolio', 'cancel'])
    ap.add_argument('--tickers', help='portfolio tickers, comma or space separated (default WORST_CASE_TICKERS); '
                                      'used once the portfolio is a ticker list')
    ap.add_argument('--universe', help='portfolio universe id while the portfolio is a universe (default: the catalog '
                                       'sector with the most tickers that is not "all")')
    ap.add_argument('--base', help='a local stack instead of Railway dev: its origin; credentials from EDGE_E2E_LOGIN '
                                   'and EDGE_E2E_PASSWORD')
    ap.add_argument('--self-test', nargs='+', metavar='RESULT_JSON')
    ap.add_argument('--request', help='--self-test: the request the results were run with')
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test(a.self_test, a.request) else 1)
    if not a.out:
        ap.error('OUT_DIR is required')
    os.makedirs(a.out, exist_ok=True)
    shapes, (lot, lot_from) = contract_shapes(), lot_size()
    from playwright.sync_api import sync_playwright

    if a.base:
        base, login, password = a.base.rstrip('/'), os.environ.get('EDGE_E2E_LOGIN'), os.environ.get('EDGE_E2E_PASSWORD')
        poll_seconds = float(os.environ.get('EDGE_POLL_SECONDS') or 2)
    else:
        v = service_vars('edge-bff')
        base = (v.get('EDGE_PUBLIC_ORIGIN') or ('https://' + v['RAILWAY_PUBLIC_DOMAIN'])).rstrip('/')   # config.py origin
        login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD') or os.environ.get('EDGE_E2E_PASSWORD')
        poll_seconds = float(v.get('EDGE_POLL_SECONDS') or 2)        # config.py: EDGE_POLL_SECONDS, default 2
        del v
    if not login or not password:
        raise SystemExit('no credentials: EDGE_LOGIN / EDGE_INITIAL_PASSWORD in edge-bff\'s Railway variables '
                         '(or EDGE_E2E_PASSWORD; with --base EDGE_E2E_LOGIN and EDGE_E2E_PASSWORD)')
    report = {'base': base, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'lot_size': lot,
              'lot_size_from': lot_from, 'edge_poll_seconds': poll_seconds, 'stripped_for_determinism': RUN_FIELDS, 'steps': {}}
    steps = report['steps']
    calls = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                     proxy={'server': os.environ['HTTPS_PROXY']} if os.environ.get('HTTPS_PROXY') and not a.base else None)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        # the toasts the page shows (format.ts toast: #toast, hidden again after 2.2 s), kept for the report
        ctx.add_init_script("""document.addEventListener('DOMContentLoaded', () => { const t = document.getElementById('toast');
          window.__toasts = []; if (!t) return; new MutationObserver(() => { if (!t.hidden && t.textContent) window.__toasts.push(t.textContent) })
          .observe(t, { attributes: true, childList: true, characterData: true, subtree: true }) });""")
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        del password
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        page = None if a.skip_page else ctx.new_page()
        pause = (lambda s: page.wait_for_timeout(s * 1000)) if page else time.sleep   # page events are served while waiting
        api = Api(ctx, base, r.json()['csrf_token'], pause)

        status, cat = api.json('/api/v1/backtests/catalog')
        if status != 200:
            raise SystemExit(f'catalog answered {status}: {cat.get("error")}')
        cat_shape = []
        _shape(cat, shapes['Catalog'], '$', cat_shape)
        _shape(cat.get('limits', {}), shapes['Limits'], '$.limits', cat_shape)
        limits = cat['limits']
        pick = portfolio_pick(a, cat)
        report['catalog'] = {'status': status, 'shape_vs_contract': {'ok': not cat_shape, 'problems': cat_shape[:10]},
                             'tickers': len(cat['tickers']), 'universes': len(cat.get('universes') or []),
                             'data_through': cat['data_through'], 'first_date': cat['first_date'],
                             'flow': {k: cat['flow'].get(k) for k in ('available', 'data_through', 'reason')},
                             'engine_version': cat['engine_version'], 'registry_version': cat['registry_version'], 'limits': limits}
        report['portfolio_pick'] = pick
        wait_limit = limits['timeout_seconds'] + 120                    # the job's own limit, then edge-bff's poll and storage

        def on_finished(req):
            u = req.url.split('?')[0]
            if not ('/api/v1/backtests' in u or '/api/terminal/v1/bundle' in u or 'storageapi.dev' in u):
                return
            entry = {'t': round(time.monotonic(), 3), 'method': req.method, 'url': 'storage file' if 'storageapi.dev' in u else u,
                     'query': req.url.partition('?')[2] if u.endswith('/events') else None}   # never a presigned query
            try:
                resp = req.response()
                entry['status'] = resp.status if resp else None
                tm = req.timing
                entry['ms'] = round(tm['responseEnd'], 1) if tm and tm.get('responseEnd', -1) >= 0 else None
                entry['wire_bytes'] = req.sizes().get('responseBodySize')
                if resp and '/api/v1/backtests' in u:
                    entry['json_bytes'] = len(resp.body())
                    if req.method == 'POST' and (u.endswith('/api/v1/backtests') or u.endswith('/signals')):
                        entry['body'] = json.loads(req.post_data or '{}')
                        entry['answer'] = resp.json() if u.endswith('/api/v1/backtests') else None
            except Exception as e:
                entry['error'] = type(e).__name__
            calls.append(entry)
        errors, http_errors = [], []
        # where a console error came from, and every answer >= 400 of any URL (never a query: presigned links)
        where = lambda m: ((m.location or {}).get('url') or '').split('?')[0]
        if page:
            page.on('requestfinished', on_finished)
            page.on('pageerror', lambda e: errors.append(str(e)[:300]))
            page.on('console', lambda m: errors.append(f'{m.text[:300]} @ {where(m)}') if m.type == 'error' else None)
            page.on('response', lambda r: http_errors.append({'status': r.status, 'method': r.request.method,
                                                              'url': r.url.split('?')[0]}) if r.status >= 400 else None)

        def toasts():
            try:
                return page.evaluate('window.__toasts || []')
            except Exception:
                return []

        def step(name, fn):
            """one step; an exception ends that step only (recorded, with a screenshot), never the report"""
            try:
                return fn()
            except SystemExit:
                raise
            except Exception as e:
                steps[name] = {**(steps.get(name) or {}), 'ok': False, 'exception': f'{type(e).__name__}: {str(e)[:400]}'}
                if page:
                    try:
                        page.screenshot(path=os.path.join(a.out, f'error-{name}.png'), full_page=True)
                    except Exception:
                        pass
                return None

        def page_run(label):
            """click Run (#runTop, one of the .js-run buttons: run.ts bindRun), follow the job, wait for the page's own
            end of the run, screenshot the six result tabs at the three sizes"""
            n_toasts = len(toasts())
            t_click = time.monotonic()
            with page.expect_response(lambda r: r.request.method == 'POST' and r.url.split('?')[0].endswith('/api/v1/backtests'),
                                      timeout=180_000) as info:
                page.click('#runTop')
            resp = info.value
            body = json.loads(resp.request.post_data or '{}')
            out = {'submit_status': resp.status, 'submit_ms': round((time.monotonic() - t_click) * 1000), 'request': body}
            try:
                ans = resp.json()
            except Exception:
                ans = {}
            if resp.status != 202:
                out['error'] = ans.get('error')
                return out
            out['request_id'] = ans['request_id']
            st, timeline = api.follow(ans['request_id'], t_click, wait_limit)
            out['status'], out['timeline'] = st, timeline
            page.wait_for_function("() => !document.getElementById('runTop').disabled", timeout=600_000)
            note = page.inner_text('#runNote')
            out['page'] = {'click_to_done_s': round(time.monotonic() - t_click, 2), 'run_note': note,
                           'done': {'ok': note.startswith('Done in')}}   # run.ts: `Done in ${R.ms} ms · ...`
            shots, failed = [], []
            if out['page']['done']['ok']:
                for w, h in VIEWPORTS:
                    page.set_viewport_size({'width': w, 'height': h})
                    for t in TABS:
                        try:
                            page.click(f'#rtabs [data-tab="{t}"]', timeout=10_000)
                            page.wait_for_timeout(700)
                            path = os.path.join(a.out, f'{label}-{t}-{w}x{h}.png')
                            page.screenshot(path=path, full_page=True)
                            shots.append(os.path.basename(path))
                        except Exception as e:
                            failed.append(f'{t} {w}x{h}: {type(e).__name__}')
                page.set_viewport_size({'width': 1600, 'height': 1000})
            out['screenshots'], out['screenshot_failures'] = shots, failed
            # the page shows errors (and the preview's warnings, which a fresh result does not fetch) as toasts: none is
            # expected from a run and its six tabs (run.ts:85/98, signals.ts:78-83 the chart's events/bars, overview.ts:42)
            got = toasts()[n_toasts:]
            out['page']['no_error_toast'] = {'ok': not got, 'toasts': got}
            return out

        def stored_request(mode):
            """the newest stored request of this mode (GET /api/v1/backtests: each JobStatus with its request)"""
            _, jobs = api.json('/api/v1/backtests?limit=100')
            return next((j['request'] for j in jobs.get('items', []) if j['request'].get('mode') == mode), None)

        def check_result(label, request_id, request):
            """the stored result through the API: sizes, shape, checks; and one ticker's events"""
            out = {}
            status, raw, size = api.get(f'/api/v1/backtests/{request_id}/result')
            out['result_status'] = status
            if status != 200:
                out['error'] = json.loads(raw or b'{}').get('error')
                return out, None
            res = json.loads(raw)
            single = request['mode'] == 'single'
            out['sizes'] = {'result': {**size, 'gzip6_bytes': len(gzip.compress(raw, 6))}}
            out['checks'] = payload_checks(res, shapes, lot, request['sizing']['capital_idr'], request, core=not single)
            m = res['meta']
            out['meta'] = {k: m.get(k) for k in ('engine_version', 'registry_version', 'data_version', 'request_hash',
                                                 'lineage_key', 'mode', 'data_through', 'benchmark', 'seed', 'duration_ms')}
            out['meta']['tickers'] = len(m['tickers'])
            out['meta']['warnings'] = [w['code'] for w in m['warnings']]
            excl = next((w for w in m['warnings'] if w['code'] == 'TICKERS_EXCLUDED'), None)
            out['meta']['tickers_excluded'] = excl and {'count': excl.get('count'), 'codes': sorted({x['code'] for x in excl.get('reasons') or []})}
            out['meta']['trials'] = {k: m['trials'][k] for k in ('prior', 'this_run', 'total')}
            out['period'] = [res['dates'][0], res['dates'][-1], len(res['dates'])]
            out['trades'] = len(res['trades'])
            out['stats_all'] = {k: res['stats']['all'][k] for k in ('total_return', 'cagr', 'sharpe', 'max_drawdown', 'volatility', 'n_returns')}
            rb = res['robustness']
            out['robustness'] = {'monte_carlo_runs': rb['monte_carlo'] and rb['monte_carlo']['runs'],
                                 'sensitivity_cells': None if not rb['sensitivity'] else
                                 sum(1 for row in rb['sensitivity']['cells'] for c in row if c is not None),
                                 'deflated': rb['deflated']}
            # events: the ticker with the most trades (or the first one), and one catalog stock the run did not have
            counts = {}
            for t in res['trades']:
                counts[t['ticker']] = counts.get(t['ticker'], 0) + 1
            tick = max(counts, key=lambda k: (counts[k], k)) if counts else (m['tickers'] or [None])[0]
            if tick:
                es, eraw, esize = api.get(f'/api/v1/backtests/{request_id}/events?ticker={tick}')
                ev = json.loads(eraw or b'{}')
                bad = []
                _shape(ev, shapes['TickerEvents'], '$', bad)
                e_out = {'ticker': tick, 'status': es, **esize, 'shape_vs_contract': {'ok': es == 200 and not bad, 'problems': bad[:5]},
                         'conditions': len(ev.get('conditions', [])), 'exit_tracks': len(ev.get('exits', {})),
                         'only_this_ticker': {'ok': all(c['ticker'] == tick for c in ev.get('conditions', [])) and set(ev.get('exits', {})) <= {tick}}}
                if single:   # /result merges the single ticker's part back (backtest.py result): the same tracks
                    e_out['equals_result_events'] = {'ok': ev.get('conditions') == res['events'].get('conditions')
                                                     and ev.get('exits') == res['events'].get('exits')}
                out['sizes']['events'] = {k: e_out[k] for k in ('ms', 'json_bytes', 'wire_bytes')}
                out['events'] = e_out
            ran = set(m['tickers'])
            other = next((t['ticker'] for t in cat['tickers'] if t['type'] == 'stock' and t['ticker'] not in ran), None)
            if other:
                es, ev = api.json(f'/api/v1/backtests/{request_id}/events?ticker={other}')
                out['events_of_ticker_not_run'] = {'ok': es == 404 and (ev.get('error') or {}).get('code') == 'EVENTS_NOT_FOUND', 'status': es}
            if single:
                out['events_in_result'] = {'conditions': len(res['events'].get('conditions', [])),
                                           'entries': len(res['events']['entries']), 'skipped': len(res['events']['skipped'])}
            else:
                out['core_has_no_condition_tracks'] = {'ok': 'conditions' not in res['events'] and 'exits' not in res['events']}
            with open(os.path.join(a.out, f'result-{label}.json'), 'w') as f:
                json.dump(res, f)
            return out, res

        def api_run(label, body):
            """a job submitted by the script (not the page), followed to its end"""
            status, ans, t0 = api.submit(body)
            out = {'submit_status': status, 'submit_ms': round((time.monotonic() - t0) * 1000), 'answer': ans}
            if status != 202:
                return out, None
            st, timeline = api.follow(ans['request_id'], t0, wait_limit)
            out.update(request_id=ans['request_id'], status=st, timing=timings(st, timeline, out['submit_ms']))
            if st.get('state') != 'FINISHED':
                return out, None
            res_out, res = check_result(label, ans['request_id'], body)
            out.update(res_out)
            return out, res

        def page_job(label):
            """the page's run, then its stored result checked through the API"""
            s = page_run(label)
            req = {k: v for k, v in s['request'].items() if k != 'client_request_id'}
            out = {k: s[k] for k in ('submit_status', 'submit_ms', 'page', 'screenshots', 'screenshot_failures', 'error') if k in s}
            out['request'] = req
            if 'request_id' not in s:
                return out, req, None
            st = s['status']
            out.update(request_id=s['request_id'], status=st, timing=timings(st, s['timeline'], s['submit_ms']))
            if st.get('state') != 'FINISHED':
                return out, req, None
            res_out, res = check_result(label, s['request_id'], req)
            out.update(res_out)
            return out, req, res

        def boot():
            t0 = time.monotonic()
            page.goto(base + '/backtest-app/', wait_until='domcontentloaded')
            # app.ts boot: the run buttons are enabled once the catalog and the shown ticker's bars loaded; a failure
            # leaves them disabled and shows a toast
            page.wait_for_function("() => !document.getElementById('runTop').disabled || (window.__toasts || []).length > 0", timeout=180_000)
            steps['page_boot'] = {'ok': not page.is_disabled('#runTop'), 'seconds': round(time.monotonic() - t0, 1),
                                  'toasts': toasts(), 'run_note': page.inner_text('#runNote')}
            page.screenshot(path=os.path.join(a.out, 'boot-1600x1000.png'), full_page=True)
        if page:
            step('page_boot', boot)

        state = {}

        def single_step():
            if page:
                out, req, res = page_job('single')
            else:
                req = stored_request('single')
                if req is None:
                    raise RuntimeError('--skip-page: no stored single request to run')
                out, res = api_run('single', req)
                out['request'] = req
            steps['single'] = out
            state['single_request'] = req
            rq = req['robustness']
            # the user's measurement (a): the page sends sensitivity on and the catalog's Monte Carlo runs
            # (api/request.ts buildRequest: robustness {monte_carlo_runs: CAT.limits.monte_carlo_runs, seed: 7, sensitivity: true})
            got = out.get('robustness') or {}
            out['measurement_run'] = {'ok': rq['sensitivity'] is True and rq['monte_carlo_runs'] == limits['monte_carlo_runs']
                                      and res is not None and got.get('sensitivity_cells') == 25
                                      and got.get('monte_carlo_runs') == limits['monte_carlo_runs'],
                                      'sensitivity': rq['sensitivity'], 'monte_carlo_runs': rq['monte_carlo_runs'],
                                      'trades': out.get('trades'), 'result_monte_carlo_runs': got.get('monte_carlo_runs'),
                                      'result_sensitivity_cells': got.get('sensitivity_cells')}
            if res is not None and len(res['trades']) < 3:
                # robustness.ts monteCarlo: null below 3 trades; the measurement needs a strategy that trades more
                out['measurement_run']['note'] = 'fewer than 3 trades: the Monte Carlo is null by design (robustness.ts monteCarlo: T.length < 3)'
            if res is None:
                return
            # the identical request again: the same numbers apart from RUN_FIELDS, the same trial total (K3)
            out2, res2 = api_run('single-repeat', req)
            same_data = res2 is not None and res2['meta']['data_version'] == res['meta']['data_version']
            diffs = diff_paths(strip_run_fields(res), strip_run_fields(res2)) if res2 is not None else ['no second result']
            t1, t2 = res['meta']['trials'], (res2 or {}).get('meta', {}).get('trials', {})
            out2['determinism'] = {'ok': same_data and not diffs, 'same_data_version': same_data, 'differences': diffs,
                                   'stripped': [p for p, _ in RUN_FIELDS]}
            out2['trial_bookkeeping'] = {'ok': res2 is not None and t2['this_run'] == 0 and t2['total'] == t1['total']
                                         and t2['prior'] == t1['prior'] + t1['this_run'],
                                         'first': {k: t1[k] for k in ('prior', 'this_run', 'total')},
                                         'repeat': {k: t2.get(k) for k in ('prior', 'this_run', 'total')}}
            steps['single_repeat'] = out2

        def refused_step():
            # a request the worker refuses at submit: 422 before queueing, no job made (CONTRACT.md D-L2)
            req = state.get('single_request') or stored_request('single')
            if req is None:
                raise RuntimeError('no single request to refuse')
            _, before = api.json('/api/v1/backtests?limit=1')
            bad = copy.deepcopy(req)
            bad['period']['to'] = '2100-01-01'
            status, ans, _ = api.submit(bad)
            _, after = api.json('/api/v1/backtests?limit=1')
            newest = lambda j: (j.get('items') or [{}])[0].get('request_id')
            steps['refused_at_submit'] = {'ok': status == 422 and (ans.get('error') or {}).get('code') == 'PERIOD_AFTER_DATA'
                                          and newest(before) == newest(after), 'status': status, 'error': ans.get('error'),
                                          'no_job_made': newest(before) == newest(after)}

        def portfolio_step():
            if page:
                steps['portfolio'] = {}
                n0 = len(calls)
                t0 = time.monotonic()
                used = page_portfolio_setup(page, pick)
                steps['portfolio']['pick_used'] = used
                # the page's signals preview of this portfolio (the latest wins, D-P8: earlier ones end 409 or aborted)
                prev = None
                while time.monotonic() - t0 < wait_limit and prev is None:
                    prev = next((c for c in calls[n0:] if c['url'].endswith('/signals') and c.get('status') == 200
                                 and preview_matches(c.get('body') or {}, used)), None)
                    page.wait_for_timeout(250)
                steps['portfolio']['preview'] = {'status': prev and prev['status'], 'ms': prev and prev['ms'],
                                                 'json_bytes': prev and prev.get('json_bytes'), 'wire_bytes': prev and prev.get('wire_bytes'),
                                                 'seen_s': round(time.monotonic() - t0, 1)}
                page.screenshot(path=os.path.join(a.out, 'portfolio-signals-1600x1000.png'), full_page=True)
                out, req, _ = page_job('portfolio')
                steps['portfolio'].update(out)
            else:
                template = stored_request('portfolio')
                if template is None:
                    raise RuntimeError('--skip-page: no stored portfolio request to run')
                req, used = portfolio_body(template, pick)
                out, _ = api_run('portfolio', req)
                steps['portfolio'] = {'pick_used': used, 'request': req, **out}
            state['portfolio_request'] = req

        def cancel_step():
            req = state.get('portfolio_request') or stored_request('portfolio')
            if req is None:
                raise RuntimeError('no portfolio request to vary for the cancel (run the portfolio step first)')
            # a variant never run before (a new trial of the line, a job that must compute): the capital is in the
            # variant hash in both modes (hash.ts variantOf: sizing.capital_idr), so it works for either portfolio shape
            body = copy.deepcopy(req)
            body['sizing']['capital_idr'] = body['sizing']['capital_idr'] + 1 + int(time.time()) % 1_000_000
            status, ans, t0 = api.submit(body)
            c = {'submit_status': status, 'answer': ans, 'capital_idr': body['sizing']['capital_idr'], 'request': body}
            steps['cancel'] = c
            if status != 202:
                c['ok'] = False
                return
            rid = ans['request_id']
            # early: as soon as the worker has the job (edge-bff stores the worker's progress, backtest.py follow), so the
            # cancel goes the worker's way (cancel_requested -> POST /v1/jobs/{id}/cancel at the loop's next poll); a
            # cancel while the job is still QUEUED ends it in edge-bff alone (BacktestStore.cancel)
            while True:
                _, st = api.json(f'/api/v1/backtests/{rid}')
                if st.get('state') in ENDED or st.get('progress') or time.monotonic() - t0 > 120:
                    break
                pause(0.25)
            c['at_cancel'] = {'seconds': round(time.monotonic() - t0, 2), 'state': st.get('state'), 'progress': st.get('progress')}
            t1 = time.monotonic()
            cs, cans = api.post(f'/api/v1/backtests/{rid}/cancel', {})
            c['cancel_status'], c['cancel_answer_state'] = cs, cans.get('state')
            st, timeline = api.follow(rid, t1, 600, every=0.25)
            c.update(request_id=rid, state=st.get('state'), error=st.get('error'), final_progress=st.get('progress'),
                     cancel_to_ended_s=timeline[-1][0] if timeline else None, timeline=timeline, duration_ms=st.get('duration_ms'),
                     ok=st.get('state') == 'CANCELLED' and cs == 202 and st.get('error') is None)

        if a.only in (None, 'single'):
            step('single', single_step)
            step('refused_at_submit', refused_step)
        if a.only in (None, 'portfolio'):
            step('portfolio', portfolio_step)
        if a.only in (None, 'cancel'):
            step('cancel', cancel_step)

        report['page_errors'] = errors[:20]
        report['page_http_errors'] = http_errors[:20]
        report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        api.post('/api/v1/auth/sign-out', {})
        browser.close()

    with open(os.path.join(a.out, 'calls.json'), 'w') as f:
        json.dump(calls, f, indent=1)
    report['failed'] = failures(steps, '.steps') + failures(report['catalog'], '.catalog')
    with open(os.path.join(a.out, 'report.json'), 'w') as f:
        json.dump(report, f, indent=1, default=str)
    # a step's 'status' is the JobStatus (a dict) for a job, the HTTP status (an int) for refused_at_submit
    state_of = lambda s: (s['status'].get('state') if isinstance(s.get('status'), dict)
                          else s.get('state', s.get('status', 'ok' if s.get('ok') else 'failed')))
    print(json.dumps({'states': {k: state_of(s) for k, s in steps.items() if isinstance(s, dict)},
                      'measure_dev_window': [report.get('started_at'), report.get('finished_at')],
                      'failed': report['failed']}, indent=1))
    sys.exit(1 if report['failed'] else 0)


if __name__ == '__main__':
    main()
