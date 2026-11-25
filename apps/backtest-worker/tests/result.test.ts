/* result.ts, robustness.ts and hash.ts: hand-built ledgers with hand-computed tables, the same numbers against the
   page's own run() and renderer arithmetic (tests/stats-oracle.mjs) on random ledgers, the OOS split, Monte Carlo,
   the sensitivity axes of every stop mode, trials and the Deflated Sharpe, hashes, and a wire without NaN.
   Every comparison is exact (same formulas in the same order); expected values written as divisions are the same
   divisions the page does (1000 / 1250 - 1 is -0.19999999999999996 on both sides). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import type { Ledger, LedgerTrade, ResultInput } from '../../edge-bff/backtest/src/core/ledger.ts';
import { assertFiniteJson, buildResult } from '../../edge-bff/backtest/src/core/result.ts';
import { cellStats, codedSide, monteCarlo, sensitivityPlan, settingAxis } from '../../edge-bff/backtest/src/core/robustness.ts';
import { canonicalJson, canonicalRequest, lineageKey, requestHash, sha256Hex, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import * as S from '../../edge-bff/backtest/src/core/stats.ts';
import * as O from './stats-oracle.mjs';

/* deterministic random numbers for the test data (mulberry32, as in stats.test.ts) */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
}
/* JSON has no -0 (the page's sd of no value is sqrt(0 / -1) = -0): compare a parsed result with -0 read as 0 */
const noNegZero = (v: unknown): unknown => typeof v === 'number' ? (Object.is(v, -0) ? 0 : v) : Array.isArray(v) ? v.map(noNegZero)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, noNegZero(x)])) : v;

/* ---- fixtures ------------------------------------------------------------------------------------------------- */
const RSI30: Condition = { id: 'c1', kind: 'indicator', indicator: 'I13', params: { length: 14, source: 'close' }, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } };
function request(over: { conditions?: Condition[]; stop?: Partial<BacktestRequest['exit']['stop']>; hold?: number; oos?: 0 | 0.2 | 0.3 | 0.4; sensitivity?: boolean; seed?: number; runs?: number; mode?: 'single' | 'portfolio'; ticker?: string; tickers?: string[]; capital?: number } = {}): BacktestRequest {
  const line = { indicator: 'I01', output: 'sma', params: { length: 20 } };
  return {
    schema_version: 1, mode: over.mode ?? 'single',
    ...(over.mode === 'portfolio'
      ? { portfolio: { tickers: over.tickers ?? ['AAAA', 'BBBB', 'CCCC'], max_positions: 4, rank_by: 'adx' as const, min_avg_value_20d_idr: 1e9 } }
      : { single: { ticker: over.ticker ?? 'AAAA', benchmark: 'buy_and_hold' as const } }),
    period: { from: '2019-01-02', to: '2026-10-23', oos_fraction: over.oos ?? 0 },
    entry: { logic: 'all', at_least: 1, window_bars: 3, conditions: over.conditions ?? [RSI30] },
    exit: {
      atr_length: 14,
      stop: { mode: 'pct', pct: 7 / 100, atr_mult: 2, reward_risk_x: 1, line, ...over.stop },
      take_profit: { mode: 'pct', pct: 15 / 100, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.1, chandelier_length: 22, chandelier_mult: 3, line },
      max_hold_bars: over.hold ?? 0, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: over.capital ?? 1000, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.001, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: over.runs ?? 1000, seed: over.seed ?? 7, sensitivity: over.sensitivity ?? false },
  };
}
const trade = (o: Partial<LedgerTrade> & Pick<LedgerTrade, 'ticker' | 'signal_bar' | 'entry_bar' | 'exit_bar' | 'return' | 'pnl_idr' | 'bars_held' | 'exit_reason'>): LedgerTrade => ({
  signal_event: 0, entry_price: 1000, exit_price: 1000 * (1 + o.return), exit_phase: 'intraday', shares: 200,
  cost_idr: o.pnl_idr / (o.return || 1), proceeds_idr: 0, mae: -0.02, mfe: 0.05, initial_stop: 930, initial_target: 1150, initial_risk_pct: 0.07,
  entry_condition_ids: ['c1'], flags: { corporate_actions: [], stop_and_target_same_bar: false, stale_mark: false }, ...o,
});
function ledger(dates: string[], equity: number[], close: number[], T: LedgerTrade[], signals?: Ledger['per_ticker_signals']): Ledger {
  const tks = [...new Set(T.map(t => t.ticker))].sort();
  return {
    dates, equity, exposure: equity.map((_, k) => (k % 4) / 4), benchmark_close: close, benchmark: { kind: 'buy_and_hold', ticker: 'AAAA' }, trades: T,
    events: { conditions: [], entries: {}, exits: {}, skipped: [] },
    per_ticker_signals: signals ?? tks.map(t => ({ ticker: t, entry_signals: T.filter(x => x.ticker === t).length, last_signal: null })), warnings: [],
  };
}
const VERSIONS = { engine_version: 'test-engine', registry_version: 'test-registry', data_version: 'test-data', data_through: '2026-10-23' };
const input = (q: BacktestRequest, L: Ledger, over: Partial<ResultInput> = {}): ResultInput => ({
  request: q, ledger: L, versions: VERSIONS, tickers: q.single ? [q.single.ticker] : ['AAAA', 'BBBB', 'CCCC'],
  prior_trials: [], variant_hash: 'run', lineage_key: 'lineage', request_hash: 'request', sensitivity: null, duration_ms: 5, ...over,
});

/* a weekday calendar with holes (holidays) from late December, so months and years turn inside it */
function calendar(r: () => number, n: number, start = '2019-12-23'): string[] {
  const out: string[] = []; let t = Date.parse(start + 'T00:00:00Z');
  while (out.length < n) { const d = new Date(t), wd = d.getUTCDay(); if (wd !== 0 && wd !== 6 && r() > 0.04) out.push(d.toISOString().slice(0, 10)); t += 864e5 }
  return out;
}
const walk = (r: () => number, n: number, start: number, vol = 0.015) => { const v = [start]; for (let k = 1; k < n; k++) v.push(v[k - 1] * (1 + vol * (r() - 0.48) * 2)); return v };
const REASONS = ['stop_loss', 'trailing_stop', 'take_profit', 'time_exit', 'exit_signal', 'end_of_test'] as const;
function randomLedger(r: () => number, n: number, count: number, capital = 1e9): Ledger {
  const dates = calendar(r, n), tks = ['AAAA', 'BBBB', 'CCCC', 'DDDD'], T: LedgerTrade[] = [];
  for (let i = 0; i < count && n > 2; i++) {
    const e = 1 + Math.floor(r() * (n - 2)), x = Math.min(n - 1, e + Math.floor(r() * 25)), ret = r() < 0.45 ? r() * 0.25 : -r() * 0.1;
    const cost = 1e7 * (1 + 9 * r());
    T.push(trade({ ticker: tks[Math.floor(r() * tks.length)], signal_bar: e - 1, entry_bar: e, exit_bar: x, return: r() < 0.03 ? 0 : ret, pnl_idr: ret * cost,
      bars_held: x - e + 1, exit_reason: REASONS[Math.floor(r() * REASONS.length)], initial_risk_pct: r() < 0.3 ? null : 0.02 + r() * 0.08, mae: -r() * 0.12, mfe: r() * 0.3 }));
  }
  T.sort((a, b) => a.exit_bar - b.exit_bar || (a.ticker < b.ticker ? -1 : 1));
  const L = ledger(dates, walk(r, n, capital), walk(r, n, 7000, 0.01), T, [...tks, 'EEEE'].map(t => ({ ticker: t, entry_signals: T.filter(x => x.ticker === t).length + 1, last_signal: dates[n - 1] })));
  L.exposure = L.equity.map(() => r());
  return L;
}
/* the page's S.result shape for the same ledger */
const pageTrades = (T: readonly LedgerTrade[]) => T.map(t => ({ tk: t.ticker, ei: t.entry_bar, xi: t.exit_bar, ret: t.return, pnl: t.pnl_idr, bars: t.bars_held, why: t.exit_reason, riskPct: t.initial_risk_pct, mae: t.mae, mfe: t.mfe, cost: t.cost_idr }));
function pageResult(L: Ledger, cap0: number) {
  const eq = L.equity.map((v, k) => [k, v]);
  return { eq, vals: L.equity, bench: O.benchOf(L.benchmark_close, eq, cap0), expo: L.exposure, cap0, trades: pageTrades(L.trades) };
}
const nul = (x: unknown) => (typeof x === 'number' && Number.isFinite(x)) ? x : null;

/* ---- hand-computed ledger ------------------------------------------------------------------------------------------ */
// Thu 28 Dec, Fri 29 Dec 2023, Tue 2 Jan, Wed 3 Jan, Wed 31 Jan, Thu 1 Feb, Fri 2 Feb 2024; capital 1000
const HD = ['2023-12-28', '2023-12-29', '2024-01-02', '2024-01-03', '2024-01-31', '2024-02-01', '2024-02-02'];
const HE = [1000, 1250, 1000, 1500, 1200, 1800, 900];
const HB = [100, 125, 100, 150, 150, 200, 100];                    // scaled to 1000: 1000 1250 1000 1500 1500 2000 1000
const HT = [
  trade({ ticker: 'BBBB', signal_bar: 0, entry_bar: 1, exit_bar: 1, return: -0.05, pnl_idr: -50, bars_held: 1, exit_reason: 'stop_loss', shares: 300 }),
  trade({ ticker: 'AAAA', signal_bar: 0, entry_bar: 1, exit_bar: 2, return: 0.1, pnl_idr: 100, bars_held: 2, exit_reason: 'take_profit' }),
  trade({ ticker: 'AAAA', signal_bar: 2, entry_bar: 3, exit_bar: 5, return: 0.2, pnl_idr: 300, bars_held: 3, exit_reason: 'take_profit' }),
  trade({ ticker: 'BBBB', signal_bar: 3, entry_bar: 4, exit_bar: 6, return: -0.1, pnl_idr: -120, bars_held: 3, exit_reason: 'end_of_test', exit_phase: 'close' }),
  trade({ ticker: 'AAAA', signal_bar: 5, entry_bar: 6, exit_bar: 6, return: 0, pnl_idr: 0, bars_held: 1, exit_reason: 'end_of_test', exit_phase: 'close' }),
];
const HS = [{ ticker: 'AAAA', entry_signals: 3, last_signal: '2024-02-01' }, { ticker: 'BBBB', entry_signals: 2, last_signal: '2024-01-03' }, { ticker: 'CCCC', entry_signals: 0, last_signal: null }];

test('hand-computed ledger: monthly, annual, weekday, drawdowns, exit reasons, per ticker, trades', () => {
  const L = ledger(HD, HE, HB, HT, HS); L.exposure = [0, 0.5, 0.5, 1, 1, 0.5, 0];
  const R = buildResult(input(request(), L));
  assert.deepEqual(R.benchmark, [1000, 1250, 1000, 1500, 1500, 2000, 1000]);
  assert.equal(R.stats.exposure_mean, 0.5);
  const rJan = 1200 / 1250 - 1, rFeb = 900 / 1200 - 1;
  assert.deepEqual(R.tables.monthly, [
    { year: 2023, month: 12, ret: 0.25, benchmark_ret: 0.25, ytd: 0.25 },                                   // s = first value
    { year: 2024, month: 1, ret: rJan, benchmark_ret: 1500 / 1250 - 1, ytd: (1 + rJan) - 1 },                 // s = 29 Dec close
    { year: 2024, month: 2, ret: rFeb, benchmark_ret: 1000 / 1500 - 1, ytd: (1 + rJan) * (1 + rFeb) - 1 },
  ]);
  assert.deepEqual(R.tables.annual, [
    { year: 2023, ret: 0.25, benchmark_ret: 0.25, max_drawdown: 0, trades_closed: 1, win_rate: 0, months_compound: 0.25,
      best_month: { month: 12, ret: 0.25 }, worst_month: { month: 12, ret: 0.25 }, positive_months: 1, months: 1 },
    { year: 2024, ret: 900 / 1250 - 1, benchmark_ret: 1000 / 1250 - 1, max_drawdown: -0.5, trades_closed: 4, win_rate: 0.5,
      months_compound: (1 + rJan) * (1 + rFeb) - 1, best_month: { month: 1, ret: rJan }, worst_month: { month: 2, ret: rFeb }, positive_months: 0, months: 2 },
  ]);
  const r2 = 1000 / 1250 - 1, r4 = 1200 / 1500 - 1;
  assert.deepEqual(R.tables.weekday, [
    { weekday: 1, mean: 0, median: null, positive_share: 0, days: 0, best: null, worst: null },                // no Monday
    { weekday: 2, mean: r2, median: r2, positive_share: 0, days: 1, best: r2, worst: r2 },
    { weekday: 3, mean: (0.5 + r4) / 2, median: r4, positive_share: 0.5, days: 2, best: 0.5, worst: r4 },       // lower median
    { weekday: 4, mean: 0.5, median: 0.5, positive_share: 1, days: 1, best: 0.5, worst: 0.5 },
    { weekday: 5, mean: -0.125, median: -0.5, positive_share: 0.5, days: 2, best: 0.25, worst: -0.5 },        // day 0 is no return
  ]);
  assert.deepEqual(R.tables.drawdowns, [
    { peak: 5, trough: 6, recovery: null, depth: -0.5, bars: 1 },                                             // open: to the last day
    { peak: 1, trough: 2, recovery: 3, depth: 1000 / 1250 - 1, bars: 2 },                                     // equal depths: time order
    { peak: 3, trough: 4, recovery: 5, depth: 1200 / 1500 - 1, bars: 2 },
  ]);
  assert.deepEqual(R.tables.exit_reasons, [
    { reason: 'stop_loss', trades: 1, wins: 0, avg_return: -0.05, pnl_idr: -50, avg_bars: 1 },
    { reason: 'take_profit', trades: 2, wins: 2, avg_return: (0.1 + 0.2) / 2, pnl_idr: 400, avg_bars: 2.5 },
    { reason: 'end_of_test', trades: 2, wins: 0, avg_return: -0.1 / 2, pnl_idr: -120, avg_bars: 2 },        // a zero return is a loss
  ]);
  assert.deepEqual(R.tables.per_ticker, [
    { ticker: 'AAAA', entry_signals: 3, last_signal: '2024-02-01', trades: 3, wins: 2, pnl_idr: 400, avg_return: (0.1 + 0.2 + 0) / 3, pnl_share: 400 / 230 },
    { ticker: 'BBBB', entry_signals: 2, last_signal: '2024-01-03', trades: 2, wins: 0, pnl_idr: -170, avg_return: (-0.05 + -0.1) / 2, pnl_share: -170 / 230 },
    { ticker: 'CCCC', entry_signals: 0, last_signal: null, trades: 0, wins: 0, pnl_idr: 0, avg_return: null, pnl_share: null },
  ]);
  assert.deepEqual(R.tables.rolling_sharpe_126, Array(6).fill(null));
  assert.equal(R.tables.rolling_sharpe_126_share_above_1, null);
  assert.deepEqual(R.trades.map(t => [t.trade_id, t.signal_date, t.entry_date, t.exit_date, t.lots, t.streak, t.streak_length]), [
    ['BBBB-2023-12-29-1', '2023-12-28', '2023-12-29', '2023-12-29', 3, 1, 1],
    ['AAAA-2023-12-29-1', '2023-12-28', '2023-12-29', '2024-01-02', 2, 1, 2],
    ['AAAA-2024-01-03-2', '2024-01-02', '2024-01-03', '2024-02-01', 2, 2, 2],
    ['BBBB-2024-01-31-2', '2024-01-03', '2024-01-31', '2024-02-02', 2, 1, 2],
    ['AAAA-2024-02-02-3', '2024-02-01', '2024-02-02', '2024-02-02', 2, 2, 2],
  ]);
  assert.deepEqual(R.trade_returns, { mean: (0 + -0.05 + 0.1 + 0.2 + -0.1 + 0) / 5, median: 0, sd: S.sd([-0.05, 0.1, 0.2, -0.1, 0]), skew: S.skew([-0.05, 0.1, 0.2, -0.1, 0]) });
  assert.deepEqual(R.oos, { fraction: 0, cut: 7, cut_date: '2024-02-02' });
  assert.equal(R.stats.in_sample, null);                                     // cut 7 is not above 20
  assert.equal(R.trade_stats.in_sample.n, 5);
  assert.deepEqual(R.meta.trials, { prior: 0, this_run: 1, total: 1, variants: [{ variant_hash: 'run', sharpe_daily: R.stats.all.sharpe / Math.sqrt(252), kind: 'run' }], owner: null });   // K6 a: no owner trials given
  assert.equal(R.robustness.deflated.sharpe_variance_from, 'sample');
  assert.equal(R.robustness.monte_carlo?.n_trades, 5);
});

test('rolling Sharpe 126: the window is the 126 returns before the point, not the point itself', () => {
  const r = rng(11), dates = calendar(r, 140), eq = walk(r, 140, 1e9, 0.02);
  const R = buildResult(input(request(), ledger(dates, eq, walk(r, 140, 5000), [])));
  const ret = R.daily_returns, roll = R.tables.rolling_sharpe_126;
  assert.equal(roll.length, 139); assert.deepEqual(roll.slice(0, 126), Array(126).fill(null));
  const w = ret.slice(0, 126);
  assert.equal(roll[126], S.mean(w) / S.sd(w) * Math.sqrt(252));
  assert.equal(R.tables.rolling_return_126?.[126], w.reduce((p, x) => p * (1 + x), 1) - 1);
  // moving the close of day 127 changes returns 126 and 127: point 126 stays, point 127 moves
  const eq2 = eq.slice(); eq2[127] *= 1.05;
  const R2 = buildResult(input(request(), ledger(dates, eq2, walk(rng(12), 140, 5000), [])));
  assert.equal(R2.tables.rolling_sharpe_126[126], roll[126]);
  assert.notEqual(R2.tables.rolling_sharpe_126[127], roll[127]);
});

test('every table equals the page\'s run() and renderer arithmetic on random ledgers', () => {
  const r = rng(5);
  for (const [n, count, oosPct, oos] of [[2, 0, 0, 0], [7, 3, 40, 0.4], [30, 6, 20, 0.2], [130, 20, 30, 0.3], [400, 60, 20, 0.2], [1300, 250, 40, 0.4], [1300, 250, 0, 0]] as const) {
    const L = randomLedger(r, n, count), q = request({ oos, capital: 1e9 }), R = buildResult(input(q, L));
    const P = pageResult(L, 1e9), D = O.runDerived(P, oosPct), tag = `n=${n} oos=${oos}`;
    assert.deepEqual(R.benchmark, P.bench, tag);
    assert.deepEqual(R.drawdown, D.st.dd, tag); assert.deepEqual(R.daily_returns, D.st.r, tag);
    assert.deepEqual(R.stats.all, S.toSeriesStats(D.st), tag);
    assert.deepEqual(R.stats.benchmark, S.toSeriesStats(D.bst), tag);
    assert.deepEqual(R.stats.in_sample, D.ins && S.toSeriesStats(D.ins), tag);
    assert.deepEqual(R.stats.out_of_sample, D.oos && S.toSeriesStats(D.oos), tag);
    assert.equal(R.stats.exposure_mean, O.exposureMean(P), tag);
    assert.equal(R.oos.cut, D.cut, tag); assert.equal(R.oos.cut_date, D.cutDay == null ? null : L.dates[D.cutDay], tag);
    assert.deepEqual(R.trade_stats.all, S.toTradeStats(D.ts), tag);
    assert.deepEqual(R.trade_stats.in_sample, S.toTradeStats(D.tsIn), tag);
    assert.deepEqual(R.trade_stats.out_of_sample, D.oos ? S.toTradeStats(D.tsOut) : null, tag);
    // overview
    const H = O.heatmap(P, L.dates), years = H.map((h: any) => h.y), A = O.annual(P, L.dates, years);
    assert.deepEqual(R.tables.monthly, H.flatMap((h: any) => h.cells.map((c: any) => ({ year: +h.y, month: c.month, ret: c.r, benchmark_ret: c.br, ytd: c.ytd }))), tag);
    assert.deepEqual(R.tables.annual, A.map((a: any, i: number) => ({ year: +a.y, ret: a.v, benchmark_ret: a.b, max_drawdown: a.mdd, trades_closed: a.closed, win_rate: a.wr,
      months_compound: H[i].total, best_month: { month: H[i].best[0], ret: H[i].best[1] }, worst_month: { month: H[i].worst[0], ret: H[i].worst[1] }, positive_months: H[i].up, months: H[i].months })), tag);
    H.forEach((h: any, i: number) => assert.equal(h.by, A[i].b, `${tag} heatmap year benchmark = annual bar`));
    // returns & distribution
    assert.deepEqual(R.tables.weekday, O.weekday(P, L.dates).map((w: any) => ({ weekday: w.d, mean: w.mean, median: nul(w.median), positive_share: w.pos, days: w.days, best: nul(w.best), worst: nul(w.worst) })), tag);
    const RO = O.rolling(D.st);
    assert.deepEqual(R.tables.rolling_sharpe_126, RO.roll.map(nul), tag);
    assert.deepEqual(R.tables.rolling_return_126, RO.ret.map(nul), tag);
    assert.equal(R.tables.rolling_sharpe_126_share_above_1, nul(RO.above), tag);
    const TR = O.tradeReturns(P.trades);
    assert.deepEqual(R.trade_returns, { mean: TR.mean, median: nul(TR.median), sd: TR.sd, skew: nul(TR.skew) }, tag);
    // trade analysis
    assert.deepEqual(R.tables.exit_reasons, O.exitReasons(P.trades).map((e: any) => ({ reason: e.why, trades: e.n, wins: e.wins, avg_return: e.avg, pnl_idr: e.pnl, avg_bars: e.bars })), tag);
    const BT = new Map(O.byTicker(P.trades).map((b: any) => [b.tk, b]));
    assert.deepEqual(R.tables.per_ticker, L.per_ticker_signals.map(s => { const t = O.tickerRow(P.trades, s.ticker), b: any = BT.get(s.ticker);
      return { ...s, trades: t.n, wins: t.wins, pnl_idr: t.pnl, avg_return: b ? b.avg : null, pnl_share: b ? b.share : null } }), tag);
    const ST = O.streaks(P.trades);
    assert.deepEqual(R.trades.map(t => [t.streak, t.streak_length]), ST.pos.map((p: number, i: number) => [p, ST.len[i]]), tag);
    // risk & ratios
    assert.deepEqual(R.tables.drawdowns, O.ddTable(P).map((d: any) => ({ peak: d.s, trough: d.t, recovery: d.e, depth: d.d, bars: d.days })), tag);
    // robustness
    const mc = O.monteCarlo(P.trades, 1e9, 1000, 1, 7);
    if (!mc) assert.equal(R.robustness.monte_carlo, null, tag);
    else { assert.deepEqual(R.robustness.monte_carlo?.bands.p50, mc.bands[2], tag); assert.deepEqual(R.robustness.monte_carlo?.final_returns, mc.fin, tag) }
    const ds = O.dsr(D.st, 1, [R.meta.trials.variants[0].sharpe_daily]);
    assert.deepEqual(R.robustness.deflated, { sr0: nul(ds.sr0), dsr: nul(ds.dsr), trials: 1, sharpe_variance_from: 'sample' }, tag);
    assert.doesNotThrow(() => assertFiniteJson(JSON.parse(JSON.stringify(R))));
  }
});

test('OOS split: cut = floor(n x (1 - share)), in-sample equity[0..cut-1], out-of-sample from cut-1, trades by entry bar', () => {
  const r = rng(6), n = 101, dates = calendar(r, n), eq = walk(r, n, 1e9), close = walk(r, n, 5000);
  const T = [79, 80, 10, 100].map((e, i) => trade({ ticker: 'AAAA', signal_bar: e - 1, entry_bar: e, exit_bar: Math.min(n - 1, e + 1), return: [0.1, -0.05, 0.02, 0.03][i], pnl_idr: 10 * (i + 1), bars_held: 2, exit_reason: 'take_profit' }))
    .sort((a, b) => a.exit_bar - b.exit_bar);
  const q = request({ oos: 0.2, capital: 1e9 }), R = buildResult(input(q, ledger(dates, eq, close, T)));
  const bench = close.map(v => v / close[0] * 1e9);
  assert.equal(R.oos.cut, 80); assert.equal(R.oos.cut_date, dates[79]);                     // floor(101 x 0.8) = 80
  assert.deepEqual(R.stats.in_sample, S.toSeriesStats(S.seriesStats(eq.slice(0, 80), bench.slice(0, 80))));
  assert.deepEqual(R.stats.out_of_sample, S.toSeriesStats(S.seriesStats(eq.slice(79), bench.slice(79))));   // 22 values, 21 > 20
  assert.equal(R.stats.out_of_sample?.n_returns, 21);
  assert.equal(R.trade_stats.in_sample.n, 2); assert.equal(R.trade_stats.out_of_sample?.n, 2);              // entries 10, 79 | 80, 100
  // 100 days: 20 out-of-sample days are not above 20 -> no out-of-sample statistics, trade split not shown
  const R2 = buildResult(input(q, ledger(dates.slice(0, 100), eq.slice(0, 100), close.slice(0, 100), T.filter(t => t.exit_bar < 100))));
  assert.equal(R2.oos.cut, 80); assert.equal(R2.stats.out_of_sample, null); assert.equal(R2.trade_stats.out_of_sample, null);
  // no OOS: cut = n, in-sample = the whole series once n > 20
  const R3 = buildResult(input(request({ oos: 0, capital: 1e9 }), ledger(dates, eq, close, T)));
  assert.equal(R3.oos.cut, 101); assert.deepEqual(R3.stats.in_sample, R3.stats.all); assert.equal(R3.trade_stats.in_sample.n, 4);
});

test('Monte Carlo: deterministic for a seed, the page\'s numbers for the same trades, scale per mode, null below 3 trades', () => {
  const r = rng(7), T = randomLedger(r, 300, 40).trades, P = pageTrades(T);
  for (const [seed, scale] of [[7, 1], [0, 0.5], [123456789, 0.25], [2 ** 32 + 5, 1 / 3]] as const) {
    const a = monteCarlo(T, scale, 1000, seed), b = monteCarlo(T, scale, 1000, seed), o = O.monteCarlo(P, 1e9, 1000, scale, seed);
    assert.deepEqual(a, b, `seed ${seed} twice`);
    assert.ok(a && o);
    assert.deepEqual([a.bands.p05, a.bands.p25, a.bands.p50, a.bands.p75, a.bands.p95], o.bands, `bands seed ${seed}`);
    assert.deepEqual(a.below_start, o.below); assert.deepEqual(a.actual, o.actual); assert.deepEqual(a.final_returns, o.fin); assert.deepEqual(a.max_drawdowns, o.mdds);
    const lg = O.mcLegend(o);
    assert.deepEqual([a.final_return_p05, a.final_return_p50, a.final_return_p95, a.loss_share, a.max_drawdown_p50, a.max_drawdown_p05], [lg.p05, lg.p50, lg.p95, lg.loss, lg.mdd50, lg.mdd05]);
    assert.equal(a.n_trades, 40); assert.equal(a.runs, 1000); assert.equal(a.seed, seed); assert.equal(a.scale, scale);
  }
  assert.notDeepEqual(monteCarlo(T, 1, 1000, 7)?.final_returns, monteCarlo(T, 1, 1000, 8)?.final_returns);
  assert.equal(monteCarlo(T.slice(0, 2), 1, 1000, 7), null);
  assert.ok(monteCarlo(T.slice(0, 3), 1, 1000, 7));
  assert.equal(monteCarlo(T, 1, 0, 7), null);                                                // switched off
  // through the result: single = allocation, portfolio = 1 / max positions, seed from the request
  const L = randomLedger(rng(8), 200, 12);
  const single = buildResult(input({ ...request({ seed: 42 }), sizing: { capital_idr: 1e9, allocation_fraction: 0.6 } }, L));
  assert.deepEqual(single.robustness.monte_carlo, monteCarlo(L.trades, 0.6, 1000, 42));
  const port = buildResult(input(request({ mode: 'portfolio', capital: 1e9 }), L));
  assert.deepEqual(port.robustness.monte_carlo, monteCarlo(L.trades, 1 / 4, 1000, 7));
  assert.equal(buildResult(input(request({ runs: 0, capital: 1e9 }), L)).robustness.monte_carlo, null);
});

/* ---- sensitivity -------------------------------------------------------------------------------------------- */
const X = (q: BacktestRequest) => ({ stopMode: q.exit.stop.mode, sl: q.exit.stop.pct * 100, slAtr: q.exit.stop.atr_mult, slRR: q.exit.stop.reward_risk_x, hold: q.exit.max_hold_bars });

test('sensitivity axes for every stop mode equal the page grid; cell requests vary exactly the two settings', async () => {
  const cases: [string, BacktestRequest, number[], number[], number[], string][] = [
    ['pct 7 %', request({ sensitivity: true }), [18, 24, 30, 36, 42], [3, 5, 7, 9, 11], [3, 5, 7, 9, 11].map(y => y / 100), 'stop_pct'],
    ['pct 1 % (min 1)', request({ sensitivity: true, stop: { pct: 1 / 100 } }), [18, 24, 30, 36, 42], [1, 1, 1, 3, 5], [1, 1, 1, 3, 5].map(y => y / 100), 'stop_pct'],
    ['atr 2', request({ sensitivity: true, stop: { mode: 'atr' } }), [18, 24, 30, 36, 42], [1, 1.5, 2, 2.5, 3], [1, 1.5, 2, 2.5, 3], 'stop_atr_mult'],
    ['rr 1 (min 0.5)', request({ sensitivity: true, stop: { mode: 'rr' } }), [18, 24, 30, 36, 42], [0.5, 0.5, 1, 1.5, 2], [0.5, 0.5, 1, 1.5, 2], 'stop_reward_risk_x'],
    ['line: max hold 20', request({ sensitivity: true, stop: { mode: 'line' }, hold: 20 }), [18, 24, 30, 36, 42], [10, 15, 20, 25, 30], [10, 15, 20, 25, 30], 'max_hold_bars'],
    ['none: max hold off (0)', request({ sensitivity: true, stop: { mode: 'none' } }), [18, 24, 30, 36, 42], [2, 2, 2, 5, 10], [2, 2, 2, 5, 10], 'max_hold_bars'],
  ];
  for (const [label, q, xs, ysD, ys, yKey] of cases) {
    const p = sensitivityPlan(q), page = O.gridAxes(30, X(q));
    assert.ok(p, label);
    assert.deepEqual(p.xs_display, page.xs, label); assert.deepEqual(p.ys_display, page.ys, label);
    assert.deepEqual(p.xs_display, xs, label); assert.deepEqual(p.xs, xs, label);
    assert.deepEqual(p.ys_display, ysD, label); assert.deepEqual(p.ys, ys, label);
    assert.equal(p.y_key, yKey, label); assert.equal(p.condition_id, 'c1'); assert.equal(p.base_x, 30);
    p.requests.forEach((row, i) => row.forEach((v, j) => {
      assert.ok(v);
      assert.equal((v.entry.conditions[0] as any).rhs.value, p.xs[j]);
      const y = yKey === 'stop_pct' ? v.exit.stop.pct : yKey === 'stop_atr_mult' ? v.exit.stop.atr_mult : yKey === 'stop_reward_risk_x' ? v.exit.stop.reward_risk_x : v.exit.max_hold_bars;
      assert.equal(y, p.ys[i]);
      assert.deepEqual(v.robustness, { ...q.robustness, sensitivity: false, monte_carlo_runs: 0 });
      // nothing else changes
      const strip = (z: BacktestRequest) => { const c = JSON.parse(JSON.stringify(z)); c.entry.conditions[0].rhs.value = 0; c.exit.stop.pct = c.exit.stop.atr_mult = c.exit.stop.reward_risk_x = c.exit.max_hold_bars = 0; c.robustness = 0; return c };
      assert.deepEqual(strip(v), strip(q));
    }));
  }
  // the centre cell is the run itself when the grid hits the base exactly: the same variant hash (one trial)
  const q = request({ sensitivity: true }), p = sensitivityPlan(q)!;
  assert.equal(p.base_y, 7 / 100); assert.equal(p.ys[2], p.base_y);
  assert.equal(await variantHash(p.requests[2][2]!), await variantHash(q));
  assert.notEqual(await variantHash(p.requests[2][3]!), await variantHash(q));
});

test('sensitivity: display scales (dip %, flow Rp B), a refused threshold is no cell, which condition is varied, off', () => {
  const dip: Condition = { id: 'd', kind: 'price_action', type: 'dip', op: 'lte', value: -3 * 0.01 };   // the page's card: -3 %
  const p = sensitivityPlan(request({ sensitivity: true, conditions: [dip] }))!;
  assert.deepEqual(p.xs_display, O.gridAxes(-3, X(request())).xs); assert.deepEqual(p.xs_display, [-5, -4, -3, -2, -1]);
  assert.deepEqual(p.xs, [-5, -4, -3, -2, -1].map(x => x * 0.01)); assert.equal(p.xs[2], p.base_x);
  const fnet: Condition = { id: 'f', kind: 'flow', type: 'fnet', params: { length: 5 }, op: 'gt', value: 0 };
  const pf = sensitivityPlan(request({ sensitivity: true, conditions: [fnet] }))!;
  assert.deepEqual(pf.xs_display, [-2, -1, 0, 1, 2]); assert.deepEqual(pf.xs, [-2e9, -1e9, 0, 1e9, 2e9]);           // step max(1, 0 || 1)
  // volume ratio 2: the page's grid reaches 0, which conditions.ts accepts (a ratio of at least 0, lead decision
  // 2026-10-26): every cell runs; from 1 it reaches -1, which it refuses: no request
  const vs: Condition = { id: 'v', kind: 'price_action', type: 'volspike', params: { length: 20 }, op: 'gt', value: 2 };
  const pv = sensitivityPlan(request({ sensitivity: true, conditions: [vs] }))!;
  assert.deepEqual(pv.xs_display, [0, 1, 2, 3, 4]);
  assert.deepEqual(pv.requests.map(row => row.map(v => v !== null)), Array(5).fill([true, true, true, true, true]));
  const pv1 = sensitivityPlan(request({ sensitivity: true, conditions: [{ ...vs, value: 1 }] }))!;
  assert.deepEqual(pv1.xs_display, [-1, 0, 1, 2, 3]);
  assert.deepEqual(pv1.requests.map(row => row.map(v => v !== null)), Array(5).fill([false, true, true, true, true]));
  // the first ENABLED condition WITH a numeric threshold; output-vs-output and value-less conditions are skipped
  const dmi: Condition = { id: 'm', kind: 'indicator', indicator: 'I07', params: {}, lhs: { type: 'output', output: 'plus_di' }, op: 'gt', rhs: { type: 'output', output: 'minus_di' } };
  const brk: Condition = { id: 'b', kind: 'price_action', type: 'breakout', params: { length: 20 }, op: 'close_above_high' };
  const off: Condition = { ...RSI30, id: 'x', enabled: false, rhs: { type: 'value', value: 70 } };
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [dmi, brk, off, { ...RSI30, id: 'r2', rhs: { type: 'value', value: 25 } }] }))?.condition_id, 'r2');
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [dmi, brk] })), null);
  assert.equal(sensitivityPlan(request({ sensitivity: false })), null);
});

/* ---- EXEC-SENSITIVITY-FLAGS (user choice C, 2026-11-24): a yes/no condition varies its first numeric setting ------- */
const ind = (id: string, indicator: string, output: string, value: number, params: Record<string, number | string> = {}): Condition =>
  ({ id, kind: 'indicator', indicator, params, lhs: { type: 'output', output }, op: 'gt', rhs: { type: 'value', value } });
const state = (id: string, lhs: Record<string, unknown>, value = 0.5): Condition => ({ id, kind: 'test', test: { kind: 'state', lhs, op: 'gt', rhs: { value } } });
const indRef = (indicator: string, output: string, params: Record<string, number | string> = {}) => ({ kind: 'indicator', indicator, output, params });
const flowValue = (id: string, metric: string, output: string, params: Record<string, unknown> = {}): Condition =>
  ({ id, kind: 'test', test: { kind: 'value', metric: { kind: 'flow', metric, output, params }, op: 'gt', value: 0.5 } });
const ADX25 = ind('a', 'I07', 'adx', 25, { di_length: 14, adx_smoothing: 14 });
/** the condition of cell [i][j] whose id is the plan's */
const cellCond = (p: NonNullable<ReturnType<typeof sensitivityPlan>>, i: number, j: number) => p.requests[i][j]!.entry.conditions.find(c => c.id === p.condition_id) as any;
const at = (o: unknown, path: string) => path.split('.').reduce((v: any, k) => v?.[k], o);

test('a yes/no condition first: the grid varies its first numeric setting (registry order), 20 % steps, whole numbers, inside min and max', async () => {
  // Supertrend direction (-1/1, indRegistry outs[].r 'state'): ATR length 10 -> 6, 8, 10, 12, 14; the threshold 0 stays
  const st = sensitivityPlan(request({ sensitivity: true, conditions: [ind('s', 'I09', 'direction', 0), RSI30] }))!;
  assert.deepEqual([st.condition_id, st.x_param, st.x_field, st.x_label], ['s', 'setting', 'params.atr_length', 'Atr Length']);
  assert.deepEqual(st.xs, [6, 8, 10, 12, 14]); assert.deepEqual(st.xs_display, st.xs); assert.equal(st.base_x, 10);
  st.requests.forEach((row, i) => row.forEach((v, j) => {
    const c = cellCond(st, i, j);
    assert.equal(c.rhs.value, 0, 'the threshold is not varied');
    // the run's own value is the run's own condition (the cell that equals the run is the run)
    if (st.xs[j] === 10) assert.deepEqual(c, ind('s', 'I09', 'direction', 0)); else assert.deepEqual(c.params, { atr_length: st.xs[j] });
    assert.deepEqual(v!.entry.conditions[1], RSI30, 'the other conditions are unchanged');
  }));
  assert.equal(await variantHash(st.requests[2][2]!), await variantHash(request({ sensitivity: true, conditions: [ind('s', 'I09', 'direction', 0), RSI30] })));
  assert.equal(new Set(await Promise.all(st.requests[2].map(v => variantHash(v!)))).size, 5, 'five distinct variants per row');
  // the condition's own value is the base; Parabolic SAR's first setting is a fraction (six significant digits)
  assert.deepEqual(sensitivityPlan(request({ sensitivity: true, conditions: [ind('s', 'I09', 'direction', 0, { atr_length: 12, factor: 3 })] }))!.xs, [7, 10, 12, 14, 17]);
  const sar = sensitivityPlan(request({ sensitivity: true, conditions: [ind('z', 'I12', 'direction', 0)] }))!;
  assert.deepEqual([sar.x_field, sar.xs], ['params.start', [0.012, 0.016, 0.02, 0.024, 0.028]]);
  // a test condition in the Screener's grammar (STATE on Alpha Price Action BUY's break flag): Lookback 30 -> 18-42,
  // the setting written into the reference it compares; Lookback 10 steps by 2; 3 and 400 stay inside min 3, max 400
  const pa = sensitivityPlan(request({ sensitivity: true, conditions: [state('p', indRef('I56', 'break_1'))] }))!;
  assert.deepEqual([pa.x_param, pa.x_field, pa.x_label, pa.xs], ['setting', 'test.lhs.params.lookback_length', 'Lookback N (completed candles)', [18, 24, 30, 36, 42]]);
  assert.equal(at(cellCond(pa, 0, 0), 'test.lhs.params.lookback_length'), 18); assert.equal(at(cellCond(pa, 0, 0), 'test.rhs.value'), 0.5);
  const lb = (n: number) => sensitivityPlan(request({ sensitivity: true, conditions: [state('p', indRef('I56', 'break_1', { lookback_length: n }))] }))!.xs;
  assert.deepEqual(lb(10), [6, 8, 10, 12, 14]); assert.deepEqual(lb(3), [3, 3, 3, 4, 5]); assert.deepEqual(lb(400), [240, 320, 400, 400, 400]);
  // an EVENT and a window over it read the signal's lhs; a category transform (in_categories, screener-metrics.json
  // category_args) is 0/1 and varies the indicator it reads (Alpha KAMA's KAMA length 89, min 6)
  const ev = sensitivityPlan(request({ sensitivity: true, conditions: [{ id: 'e', kind: 'test', test: { kind: 'window', mode: 'ever', length: 5, test: { kind: 'event', within: 3, signal: { lhs: indRef('I09', 'direction'), op: 'crosses_above', rhs: { value: 0 } } } } }] }))!;
  assert.deepEqual([ev.x_field, ev.xs], ['test.test.signal.lhs.params.atr_length', [6, 8, 10, 12, 14]]);
  const cat = sensitivityPlan(request({ sensitivity: true, conditions: [{ id: 'k', kind: 'test', test: { kind: 'value', metric: { kind: 'transform', fn: 'in_categories', of: indRef('I58', 'color_state'), args: { categories: 'green' } }, op: 'gt', value: 0.5 } }] }))!;
  assert.deepEqual([cat.x_param, cat.x_field, cat.x_label, cat.xs], ['setting', 'test.metric.of.params.kama_length', 'KAMA Length', [53, 71, 89, 107, 125]]);
  // Flow outputs of kind F (flow-kinds.json, "0/1 signal"): FL09 Top N 3 -> 1-5 (at least 1 per step), FL27 Recent 5 -> 3-7
  const fl = sensitivityPlan(request({ sensitivity: true, conditions: [flowValue('f', 'FL09', 'value')] }))!;
  assert.deepEqual([fl.x_param, fl.x_field, fl.x_label, fl.xs], ['setting', 'test.metric.params.top', 'Top N', [1, 2, 3, 4, 5]]);
  assert.equal(at(cellCond(fl, 0, 4), 'test.metric.params.top'), 5);
  assert.deepEqual(sensitivityPlan(request({ sensitivity: true, conditions: [flowValue('f', 'FL09', 'value', { top: 1 })] }))!.xs, [1, 1, 1, 2, 3]);
  assert.deepEqual(sensitivityPlan(request({ sensitivity: true, conditions: [flowValue('f', 'FL27', 'net')] }))!.xs, [3, 4, 5, 6, 7]);
});

test('a yes/no condition without a numeric setting: the next condition with an axis (way A), else the stop setting only; real numbers unchanged', () => {
  const ib = state('i', indRef('I55', 'ib')), div: Condition = { id: 'd', kind: 'test', test: { kind: 'event', within: 3, signal: { lhs: indRef('I60', 'bull_div'), op: 'crosses_above', rhs: { value: 0.5 } } } };
  // Inside Bar (no settings), then ADX 25: ADX's threshold, as a plan with ADX alone
  const a = sensitivityPlan(request({ sensitivity: true, conditions: [ib, ADX25] }))!, adx = sensitivityPlan(request({ sensitivity: true, conditions: [ADX25] }))!;
  assert.deepEqual([a.condition_id, a.x_param, a.x_field, a.x_label, a.xs], ['a', 'value', 'rhs.value', null, [15, 20, 25, 30, 35]]);
  assert.deepEqual((({ requests: _r, ...x }) => x)(adx), (({ requests: _r, ...x }) => x)(a));
  // Alpha Divergence (one setting, an option), then Supertrend direction: Supertrend's ATR length
  assert.deepEqual((({ condition_id, x_param, xs }) => [condition_id, x_param, xs])(sensitivityPlan(request({ sensitivity: true, conditions: [div, ind('s', 'I09', 'direction', 0)] }))!), ['s', 'setting', [6, 8, 10, 12, 14]]);
  // no later condition with an axis: one column at the condition as it is, the stop setting varies (5 backtests)
  for (const c of [ib, div]) {
    const p = sensitivityPlan(request({ sensitivity: true, conditions: [c, { id: 'b', kind: 'price_action', type: 'breakout', params: { length: 20 }, op: 'close_above_high' }] }))!;
    assert.deepEqual([p.condition_id, p.x_param, p.x_label, p.xs, p.xs_display, p.base_x], [c.id, 'none', null, [0.5], [0.5], 0.5]);
    assert.deepEqual(p.ys, [3, 5, 7, 9, 11].map(y => y / 100));
    assert.deepEqual(p.requests.map(row => row.length), [1, 1, 1, 1, 1]);
    p.requests.forEach((row, i) => { assert.deepEqual(row[0]!.entry.conditions[0], c); assert.equal(row[0]!.exit.stop.pct, p.ys[i]) });
  }
  // a switched-off yes/no condition is skipped as before; no numeric condition at all is still no grid
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [{ ...ind('s', 'I09', 'direction', 0), enabled: false }, ADX25] }))!.condition_id, 'a');
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [{ id: 'b', kind: 'price_action', type: 'breakout', params: { length: 20 }, op: 'close_above_high' }] })), null);
  // real numbers keep their threshold axis: RSI in the grammar, a K-kind Flow output (FL10 -1..1), an indicator line
  // (Supertrend's own price line), a lag of a flag (a transform other than a category one)
  const rsiT = sensitivityPlan(request({ sensitivity: true, conditions: [{ id: 'r', kind: 'test', test: { kind: 'value', metric: indRef('I13', 'rsi'), op: 'lt', value: 30 } }] }))!;
  assert.deepEqual([rsiT.x_param, rsiT.x_field, rsiT.xs], ['value', 'test.value', [18, 24, 30, 36, 42]]);
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [{ ...flowValue('f', 'FL10', 'value'), test: { kind: 'value', metric: { kind: 'flow', metric: 'FL10', output: 'value', params: {} }, op: 'gt', value: 0.2 } } as Condition] }))!.x_param, 'value');
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [ind('s', 'I09', 'supertrend', 1000)] }))!.x_param, 'value');
  assert.equal(sensitivityPlan(request({ sensitivity: true, conditions: [{ id: 'l', kind: 'test', test: { kind: 'value', metric: { kind: 'transform', fn: 'lag', of: indRef('I09', 'direction'), args: { bars: 1 } }, op: 'gt', value: 0 } }] }))!.x_param, 'value');
  // the caller's check refuses a column: that column is no cell (the worker's grammar check, run.ts gridAccepts)
  const refused = sensitivityPlan(request({ sensitivity: true, conditions: [ind('s', 'I09', 'direction', 0)] }), c => (c as any).params?.atr_length !== 6)!;
  assert.deepEqual(refused.requests.map(row => row.map(v => v !== null)), Array(5).fill([false, true, true, true, true]));
});

test('settingAxis: an exclusive minimum is not clamped onto, a fraction at 0 steps by its registry step', () => {
  assert.deepEqual(settingAxis({ key: 'x', label: 'X', integer: true, base: 2, min: 1, min_exclusive: true }), [0, 1, 2, 3, 4]);
  assert.deepEqual(settingAxis({ key: 'x', label: 'X', integer: false, base: 0, min: 0, min_exclusive: false, step: 0.1 }), [0, 0, 0, 0.1, 0.2]);
  assert.deepEqual(settingAxis({ key: 'x', label: 'X', integer: true, base: 14, min: 1, min_exclusive: false }), [8, 11, 14, 17, 20]);
  // yes/no is read from the registries: indRegistry render kinds and categories, flow-kinds F, category transforms
  assert.equal(codedSide(ind('s', 'I09', 'direction', 0))?.setting?.key, 'atr_length');
  assert.equal(codedSide(ind('s', 'I55', 'ib', 0.5))?.setting, null);
  assert.equal(codedSide(ind('a', 'I07', 'adx', 25)), null);
  assert.equal(codedSide(flowValue('f', 'FL13', 'buy')), null);                               // 0-1, kind K: a real number
});

test('trials and the Deflated Sharpe: run + distinct cells + distinct prior, the trials\' Sharpe variance, page cell numbers', async () => {
  const r = rng(9), q = request({ sensitivity: true, capital: 1e9 }), p = sensitivityPlan(q)!, L = randomLedger(r, 300, 30);
  const runHash = await variantHash(q), cellLedgers: Ledger[][] = p.requests.map(row => row.map(() => randomLedger(r, 300, 5 + Math.floor(r() * 20))));
  const cells = await Promise.all(p.requests.map(async (row, i) => Promise.all(row.map(async (v, j) => ({ ledger: cellLedgers[i][j], variant_hash: await variantHash(v!) })))));
  const prior = [{ variant_hash: 'old-1', sharpe_daily: 0.03 }, { variant_hash: cells[0][0].variant_hash, sharpe_daily: 0.5 }, { variant_hash: 'old-1', sharpe_daily: 0.04 }, { variant_hash: 'old-2', sharpe_daily: -0.01 }];
  const { requests: _r, ...axes } = p;
  const R = buildResult(input(q, L, { variant_hash: runHash, prior_trials: prior, sensitivity: { ...axes, cells } }));
  // cells: the page's per-cell arithmetic
  R.robustness.sensitivity!.cells.forEach((row, i) => row.forEach((c, j) => {
    const g = O.gridCell({ eq: cellLedgers[i][j].equity.map((v, k) => [k, v]), trades: pageTrades(cellLedgers[i][j].trades) });
    assert.deepEqual(c, { sharpe: g.sharpe, cagr: g.cagr, profit_factor: g.pf === Infinity ? 'inf' : g.pf, trades: g.n, max_drawdown: g.mdd });
    assert.deepEqual(c, cellStats(cellLedgers[i][j]));
  }));
  // the centre cell has the run's hash: 1 run + 24 other cells; 3 distinct prior, one of them a cell again
  assert.equal(R.meta.trials.variants.length, 25);
  assert.deepEqual(R.meta.trials.variants[0], { variant_hash: runHash, sharpe_daily: R.stats.all.sharpe / Math.sqrt(252), kind: 'run' });
  assert.equal(R.meta.trials.prior, 3); assert.equal(R.meta.trials.this_run, 24); assert.equal(R.meta.trials.total, 27);
  const cellSr = (i: number, j: number) => R.robustness.sensitivity!.cells[i][j]!.sharpe / Math.sqrt(252);
  const own = [R.meta.trials.variants[0].sharpe_daily, ...p.requests.flatMap((row, i) => row.map((_, j) => [i, j])).filter(([i, j]) => !(i === 2 && j === 2)).map(([i, j]) => cellSr(i, j))];
  const srs = [0.03, -0.01, ...own];                                       // prior kept (old-1 first value, old-2), then this run
  const P = pageResult(L, 1e9), st = O.seriesStats(P.vals, P.bench), ds = O.dsr(st, 27, srs);
  assert.deepEqual(R.robustness.deflated, { sr0: ds.sr0, dsr: ds.dsr, trials: 27, sharpe_variance_from: 'trials' });
  // axes that are not the request's grid, or a missing grid, are refused
  assert.throws(() => buildResult(input(q, L, { sensitivity: { ...axes, xs: [1, 2, 3, 4, 5], cells } })), /xs/);
  assert.throws(() => buildResult(input(q, L)), /no cells/);
});

/* ---- hashes ---------------------------------------------------------------------------------------------------- */
test('hashes: canonical JSON, sha256, variant (no robustness, no benchmark), lineage (shape only), request', async () => {
  assert.equal(canonicalJson({ b: 1, a: [true, null, 'x', { d: 2, c: undefined }], c: -0.5 }), '{"a":[true,null,"x",{"d":2}],"b":1,"c":-0.5}');
  assert.throws(() => canonicalJson({ a: NaN })); assert.throws(() => canonicalJson([undefined]));
  assert.equal(await sha256Hex('abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  const q = request();
  const reordered = JSON.parse(canonicalJson(q)) as BacktestRequest;                        // same request, keys sorted
  assert.equal(await variantHash(reordered), await variantHash(q));
  assert.equal(await variantHash({ ...q, robustness: { monte_carlo_runs: 0, seed: 99, sensitivity: true } }), await variantHash(q));
  assert.equal(await variantHash({ ...q, single: { ticker: 'AAAA', benchmark: 'ihsg' } }), await variantHash(q));
  assert.notEqual(await variantHash(request({ stop: { pct: 0.08 } })), await variantHash(q));
  // lineage: numbers, ids, parameters, period, disabled conditions and order do not matter; shape does
  const L0 = await lineageKey(q);
  const rsi = (id: string, v: number, op: 'lt' | 'gt' = 'lt'): Condition => ({ ...RSI30, id, op, params: { length: 9, source: 'close' }, rhs: { type: 'value', value: v } });
  const adx: Condition = { id: 'a', kind: 'indicator', indicator: 'I07', params: {}, lhs: { type: 'output', output: 'adx' }, op: 'gt', rhs: { type: 'value', value: 25 } };
  assert.equal(await lineageKey(request({ conditions: [rsi('zz', 22)], stop: { pct: 0.03 }, hold: 10, oos: 0.3, seed: 1 })), L0);
  assert.equal(await lineageKey(request({ conditions: [adx, rsi('r', 30)] })), await lineageKey(request({ conditions: [rsi('q', 40), { ...adx, rhs: { type: 'value', value: 30 } }] })));
  assert.equal(await lineageKey(request({ conditions: [rsi('r', 30), { ...adx, enabled: false }] })), L0);
  assert.notEqual(await lineageKey(request({ conditions: [rsi('r', 30, 'gt')] })), L0);           // operator
  assert.notEqual(await lineageKey(request({ conditions: [rsi('r', 30), adx] })), L0);            // another condition
  assert.notEqual(await lineageKey(request({ stop: { mode: 'atr' } })), L0);                      // exit mode
  assert.notEqual(await lineageKey(request({ ticker: 'BBBB' })), L0);                             // another stock
  assert.notEqual(await lineageKey(request({ mode: 'portfolio' })), L0);
  // request hash: the whole request and the versions
  const H0 = await requestHash(q, VERSIONS);
  assert.equal(await requestHash(reordered, VERSIONS), H0);
  assert.notEqual(await requestHash(request({ seed: 8 }), VERSIONS), H0);
  assert.notEqual(await requestHash(q, { ...VERSIONS, data_version: 'other' }), H0);
  // a single-mode line keeps the key it had before the picked stocks replaced the universes (PF1, PF4): computed on the
  // hash.ts of e08a420, so the trials recorded for it keep counting
  assert.equal(L0, '185aab382b973b2ec54ed9e174f63d4f5d791ad398b9288dc6633cc49ff5a255');
});

test('picked stocks: their order is no part of any hash; the set is in the variant and the request hash, never in the lineage (PF3, PF4)', async () => {
  const p = (tickers: string[], f?: (q: BacktestRequest) => void) => { const q = request({ mode: 'portfolio', tickers }); f?.(q); return q };
  const q = p(['AAAA', 'BBBB', 'CCCC']), V0 = await variantHash(q), L0 = await lineageKey(q), H0 = await requestHash(q, VERSIONS);
  for (const order of [['CCCC', 'AAAA', 'BBBB'], ['BBBB', 'CCCC', 'AAAA'], ['CCCC', 'BBBB', 'AAAA']]) {
    const o = p(order);
    assert.deepEqual([await variantHash(o), await lineageKey(o), await requestHash(o, VERSIONS)], [V0, L0, H0], order.join(','));
    assert.deepEqual(canonicalRequest(o), q, 'the canonical form is the request in ticker order');
    assert.deepEqual(o.portfolio!.tickers, order, 'the request itself is left as it was');
  }
  // another set: another variant (a trial) of the same line, whichever stock is added, removed or swapped
  for (const set of [['AAAA', 'BBBB'], ['AAAA', 'BBBB', 'CCCC', 'DDDD'], ['AAAA', 'BBBB', 'DDDD'], ['DDDD']]) {
    const o = p(set);
    assert.notEqual(await variantHash(o), V0, set.join(','));
    assert.notEqual(await requestHash(o, VERSIONS), H0, set.join(','));
    assert.equal(await lineageKey(o), L0, set.join(','));
  }
  // the line is still the strategy's shape: another condition is another line, a number another variant
  assert.notEqual(await lineageKey(p(['AAAA'], o => { o.entry.conditions = [{ ...RSI30, op: 'gt' }] })), L0);
  assert.equal(await lineageKey(p(['AAAA'], o => { o.portfolio!.max_positions = 12 })), L0);
  assert.notEqual(await variantHash(p(['AAAA', 'BBBB', 'CCCC'], o => { o.portfolio!.max_positions = 12 })), V0);
  // single mode keeps its ticker in the line (K3)
  assert.notEqual(await lineageKey(request({ ticker: 'AAAA' })), await lineageKey(request({ ticker: 'BBBB' })));
  const single = request();
  assert.equal(canonicalRequest(single), single, 'a single request is its own canonical form');
});

test('variant hash: only what the engine reads; ids, order, disabled cards, the OOS share and unused numbers are not new trials', async () => {
  const adx: Condition = { id: 'a1', kind: 'indicator', indicator: 'I07', params: { di_length: 14, adx_smoothing: 14 }, lhs: { type: 'output', output: 'adx' }, op: 'gt', rhs: { type: 'value', value: 25 } };
  const dip: Condition = { id: 'd1', kind: 'price_action', type: 'dip', op: 'lte', value: -0.03 };
  const q = request({ conditions: [RSI30, adx, dip], sensitivity: true, oos: 0.3 });
  const same = async (f: (v: BacktestRequest) => void, label: string) => { const v = JSON.parse(JSON.stringify(q)) as BacktestRequest; f(v); assert.equal(await variantHash(v), await variantHash(q), label) };
  const other = async (f: (v: BacktestRequest) => void, label: string) => { const v = JSON.parse(JSON.stringify(q)) as BacktestRequest; f(v); assert.notEqual(await variantHash(v), await variantHash(q), label) };
  // the page gives every card a new random id on each load; the cards' order, a disabled card and the OOS share
  await same(v => { v.entry.conditions = v.entry.conditions.map((c, k) => ({ ...c, id: `n${k}` })) }, 'new ids');
  await same(v => { v.entry.conditions.reverse() }, 'another order');
  await same(v => { v.entry.conditions.push({ ...adx, id: 'off', enabled: false, rhs: { type: 'value', value: 40 } }) }, 'a disabled card');
  await same(v => { v.entry.conditions = v.entry.conditions.map(c => ({ ...c, enabled: true })) }, 'enabled: true written out');
  await same(v => { v.period.oos_fraction = 0.2 }, 'another OOS share');
  await same(v => { v.entry.at_least = 2 }, 'at_least under logic all');
  // the numbers of the modes that are not chosen (stop pct, target pct, no trailing), atr_length without an ATR mode
  await same(v => { v.exit.stop.atr_mult = 3; v.exit.stop.reward_risk_x = 4; v.exit.stop.line = { indicator: 'I12', output: 'sar' } }, 'stop numbers of other modes');
  await same(v => { v.exit.take_profit.r_multiple = 5; v.exit.take_profit.atr_mult = 1 }, 'target numbers of other modes');
  await same(v => { v.exit.trailing.pct = 0.2; v.exit.trailing.chandelier_length = 10; v.exit.trailing.chandelier_mult = 1 }, 'trailing numbers while off');
  await same(v => { v.exit.atr_length = 20 }, 'atr_length without an ATR stop or target');
  await same(v => { v.exit.signals.logic = 'all' }, 'exit logic without an exit condition');
  await same(v => { v.exit.signals.conditions = [{ ...RSI30, id: 'x9', enabled: false }] }, 'a disabled exit card');
  const off = (fraction: number) => { const v = JSON.parse(JSON.stringify(q)) as BacktestRequest; v.costs.skip_ara_open_gap = false; v.costs.ara_gap_fraction = fraction; return variantHash(v) };
  assert.equal(await off(0.3), await off(0.2), 'ARA fraction while the rule is off');
  // at_least above the number of enabled entry cards needs all of them (combineEntry): the page's at_least 3 with a
  // card switched off is at_least 2
  const atLeast = (n: number, extra: Condition[] = []) => { const v = JSON.parse(JSON.stringify(q)) as BacktestRequest; v.entry.logic = 'at_least'; v.entry.at_least = n; v.entry.conditions.push(...extra); return variantHash(v) };
  assert.equal(await atLeast(5), await atLeast(3), 'at_least above the enabled cards');
  assert.equal(await atLeast(4, [{ ...dip, id: 'd9', enabled: false }]), await atLeast(3));
  assert.notEqual(await atLeast(2), await atLeast(3));
  // what the engine reads is a new variant
  await other(v => { v.costs.ara_gap_fraction = 0.3 }, 'ARA fraction while the rule is on');
  await other(v => { (v.entry.conditions[1] as any).rhs.value = 26 }, 'a threshold');
  await other(v => { (v.entry.conditions[0] as any).params.length = 9 }, 'a parameter');
  await other(v => { v.entry.conditions.push({ ...dip, id: 'd2' }) }, 'a repeated condition (at_least counts it)');
  await other(v => { v.entry.logic = 'at_least'; v.entry.at_least = 2 }, 'at_least');
  await other(v => { v.exit.stop.pct = 0.08 }, 'the chosen stop');
  await other(v => { v.exit.stop.mode = 'atr' }, 'another stop mode');
  await other(v => { v.exit.stop.mode = 'atr'; v.exit.atr_length = 20 }, 'atr_length with an ATR stop');
  await other(v => { v.exit.trailing.mode = 'chandelier' }, 'a trailing mode');
  await other(v => { v.exit.signals.conditions = [{ ...RSI30, id: 'x9' }] }, 'an exit condition');
  await other(v => { v.sizing.allocation_fraction = 0.5 }, 'the allocation of a single stock');
  await other(v => { v.period.from = '2019-01-03' }, 'the period');
  const p = request({ mode: 'portfolio' }), p2 = JSON.parse(JSON.stringify(p)) as BacktestRequest;
  p2.sizing.allocation_fraction = 0.25;
  assert.equal(await variantHash(p2), await variantHash(p), 'a portfolio slot is 1 / max positions, not the allocation');
  // a rerun after a reload (new ids, a disabled card, another OOS share) adds no trial: this_run 0, the same DSR
  const r = rng(11), L = randomLedger(r, 300, 30), plan = sensitivityPlan(q)!, { requests: _r, ...axes } = plan;
  const cellsOf = async (v: BacktestRequest) => Promise.all(sensitivityPlan(v)!.requests.map(async row => Promise.all(row.map(async c => ({ ledger: L, variant_hash: await variantHash(c!) })))));
  const first = buildResult(input(q, L, { variant_hash: await variantHash(q), sensitivity: { ...axes, cells: await cellsOf(q) } }));
  const again = JSON.parse(JSON.stringify(q)) as BacktestRequest;
  again.entry.conditions = again.entry.conditions.map((c, k) => ({ ...c, id: `z${k}` }));
  again.entry.conditions.push({ ...dip, id: 'zoff', enabled: false });
  again.period.oos_fraction = 0.2;
  const ax2 = (({ requests: _q, ...a }) => a)(sensitivityPlan(again)!);
  const second = buildResult(input(again, L, { variant_hash: await variantHash(again), prior_trials: first.meta.trials.variants.map(v => ({ variant_hash: v.variant_hash, sharpe_daily: v.sharpe_daily })),
    sensitivity: { ...ax2, cells: await cellsOf(again) } }));
  assert.deepEqual([second.meta.trials.prior, second.meta.trials.this_run, second.meta.trials.total], [first.meta.trials.total, 0, first.meta.trials.total]);
  assert.deepEqual(second.robustness.deflated, first.robustness.deflated);
});

/* ---- the wire --------------------------------------------------------------------------------------------------- */
test('trials: a run and cells without trades or with a flat equity have a finite daily Sharpe (the page\'s 0), no variant twice', async () => {
  // stop 1 %: the page's stop rows max(1, 1 + 2k) are 1, 1, 1, 3, 5 %, so rows 0-2 are the same 5 variants (the run among
  // them); the worker runs a variant once and gives every cell of it the same CellRun (run.ts runJob)
  const r = rng(12), q = request({ sensitivity: true, capital: 1e9, stop: { pct: 0.01 } }), p = sensitivityPlan(q)!, dates = calendar(r, 40);
  assert.deepEqual(p.ys_display, [1, 1, 1, 3, 5]);
  const flat = ledger(dates, Array(40).fill(1e9), walk(r, 40, 5000), []);
  const evenTrade = trade({ ticker: 'AAAA', signal_bar: 2, entry_bar: 3, exit_bar: 9, return: 0, pnl_idr: 0, bars_held: 7, exit_reason: 'time_exit' });
  const flatWithTrade = ledger(dates, Array(40).fill(1e9), walk(r, 40, 5000), [evenTrade]);
  const oneDay = ledger(dates.slice(0, 1), [1e9], [5000], []);
  const runHash = await variantHash(q), runs = new Map<string, { ledger: Ledger; variant_hash: string }>([[runHash, { ledger: flat, variant_hash: runHash }]]);
  const cells = [];
  for (const [i, row] of p.requests.entries()) {
    const out = [];
    for (const [j, cq] of row.entries()) {
      const h = await variantHash(cq!);
      if (!runs.has(h)) runs.set(h, { ledger: [flat, flatWithTrade, oneDay][(i + j) % 3], variant_hash: h });
      out.push(runs.get(h)!);
    }
    cells.push(out);
  }
  assert.equal(runs.size, 15, '1 run + 4 more variants in rows 0-2 + 10 in rows 3-4');
  const { requests: _r, ...axes } = p;
  const prior = [{ variant_hash: cells[0][0].variant_hash, sharpe_daily: 0.2 }, { variant_hash: 'old', sharpe_daily: 0.01 }, { variant_hash: 'old', sharpe_daily: 0.02 }];
  for (const prior_trials of [[], prior]) {
    const R = buildResult(input(q, flat, { variant_hash: runHash, prior_trials, sensitivity: { ...axes, cells } }));
    const v = R.meta.trials.variants;
    assert.equal(new Set(v.map(x => x.variant_hash)).size, v.length, 'no variant_hash twice');
    assert.deepEqual(v.map(x => x.variant_hash), [...runs.keys()]);
    assert.deepEqual(v.map(x => x.sharpe_daily), Array(15).fill(0), 'sd 0 or no return: the page\'s sharpe = sd(r) ? ... : 0');
    assert.deepEqual([v[0].kind, v.slice(1).every(x => x.kind === 'sensitivity')], ['run', true]);
    assert.deepEqual([R.meta.trials.prior, R.meta.trials.this_run, R.meta.trials.total], prior_trials.length ? [2, 14, 16] : [0, 15, 15]);
    assert.ok(R.robustness.sensitivity!.cells.flat().every(c => c!.sharpe === 0));
    assert.doesNotThrow(() => assertFiniteJson(R));
  }
});

test('no NaN or Infinity on the wire: a flat run without trades, a one-day period, all wins', () => {
  const r = rng(10), dates = calendar(r, 30), flat = Array(30).fill(1e9);
  const R = buildResult(input(request({ capital: 1e9 }), ledger(dates, flat, walk(r, 30, 5000), [])));
  assert.equal(R.stats.all.sharpe, 0); assert.equal(R.stats.all.skew, null); assert.equal(R.stats.all.kurtosis, null); assert.equal(R.stats.all.psr_0, null);
  assert.equal(R.robustness.deflated.dsr, null); assert.equal(R.trade_returns.median, null); assert.equal(R.trade_returns.skew, null);
  assert.equal(R.robustness.monte_carlo, null); assert.equal(R.trade_stats.all.profit_factor, 0);
  const text = JSON.stringify(R);
  assert.ok(!/NaN|Infinity/.test(text)); assert.deepEqual(JSON.parse(text), noNegZero(R));
  const one = buildResult(input(request({ capital: 1e9 }), ledger(dates.slice(0, 1), [1e9], [5000], [])));
  assert.equal(one.daily_returns.length, 0); assert.equal(one.robustness.deflated.sr0, null); assert.equal(one.stats.all.psr_0, null);
  assert.deepEqual(one.tables.weekday.map(w => [w.days, w.median, w.best, w.worst]), Array(5).fill([0, null, null, null]));
  const wins = randomLedger(r, 60, 6); wins.trades.forEach(t => { t.return = Math.abs(t.return) + 0.01; t.pnl_idr = Math.abs(t.pnl_idr) + 1 });
  assert.equal(buildResult(input(request({ capital: 1e9 }), wins)).trade_stats.all.profit_factor, 'inf');
  for (const bad of [{ a: NaN }, { a: [1, Infinity] }, { a: new Float64Array(2) }, [undefined], { f: () => 1 }]) assert.throws(() => assertFiniteJson(bad));
  assert.doesNotThrow(() => assertFiniteJson({ a: undefined, b: [null, 'x', 0, { c: -1 }] }));
});

test('statistical warnings (ERRORS M457): few trades, trades across the cut, one trial, a point-in-time anchor inside the period', async () => {
  const { statWarnings } = await import('../../edge-bff/backtest/src/core/result.ts');
  const dates = Array.from({ length: 100 }, (_, k) => `2025-${String(1 + Math.floor(k / 28)).padStart(2, '0')}-${String(1 + (k % 28)).padStart(2, '0')}`);
  const t = (e: number, x: number) => ({ entry_bar: e, exit_bar: x }) as never;
  const q = (conds: unknown[] = []) => ({ period: { from: dates[0] }, entry: { conditions: conds }, exit: { signals: { conditions: [] } } }) as never;
  const codes = (w: { code: string }[]) => w.map(x => x.code);
  const many = Array.from({ length: 40 }, (_, k) => t(k, k + 1));
  assert.deepEqual(codes(statWarnings(q(), many, null, false, 5, dates)), []);
  assert.deepEqual(codes(statWarnings(q(), many.slice(0, 29), null, false, 5, dates)), ['FEW_TRADES']);
  // with an out-of-sample cut at bar 69: 30 trades after it would pass, 9 do not; one trade across the cut
  const split = [...Array.from({ length: 30 }, (_, k) => t(k, k + 1)), t(68, 71), ...Array.from({ length: 9 }, (_, k) => t(80 + k, 81 + k))];
  const w = statWarnings(q(), split, 69, true, 5, dates);
  assert.deepEqual(codes(w), ['FEW_TRADES', 'OOS_STRADDLE']);
  assert.match(w[0].message, /9 of them after the out-of-sample cut/);
  assert.deepEqual(codes(statWarnings(q(), many, null, false, 1, dates)), ['DSR_SAMPLE_RULE']);
  const d = { id: 'd', kind: 'test', test: { kind: 'value', metric: { kind: 'flow', metric: 'FL45', params: { anchor: dates[80] } }, op: 'gt', value: 5 } };
  const a = statWarnings(q([d]), many, 69, true, 5, dates).find(x => x.code === 'ANCHOR_INSIDE_PERIOD')!;
  assert.match(a.message, /after the out-of-sample cut/);
  // a switched-off point-in-time condition is not run, so it raises no warning (Stage C F10)
  assert.equal(statWarnings(q([{ ...d, enabled: false }]), many, 69, true, 5, dates).find(x => x.code === 'ANCHOR_INSIDE_PERIOD'), undefined);
});

test('K6 a: the owner\'s trials across lines give a second, stricter deflated Sharpe beside the line\'s', async () => {
  const { buildResult } = await import('../../edge-bff/backtest/src/core/result.ts');
  const r = rng(77), L = randomLedger(r, 300, 12), q = request({});
  const owner = Array.from({ length: 40 }, (_, k) => ({ variant_hash: (k + 1).toString(16).padStart(64, '0'), sharpe_daily: (r() - 0.5) * 0.2 }));
  const base = { request: q, ledger: L, versions: { ...VERSIONS, data_through: L.dates[L.dates.length - 1] }, tickers: ['AAAA'], prior_trials: [], sensitivity: null, duration_ms: 0, variant_hash: 'v'.repeat(64), lineage_key: 'l'.repeat(64), request_hash: 'h'.repeat(64) };
  const line = buildResult(base as never), both = buildResult({ ...base, owner_trials: owner } as never);
  assert.equal(line.robustness.deflated_owner, null);
  assert.deepEqual(both.meta.trials.owner, { total: 41, days: 90 });
  assert.equal(both.robustness.deflated_owner!.trials, 41);
  assert.deepEqual(both.robustness.deflated, line.robustness.deflated, 'the line\'s own deflated Sharpe is unchanged');
  assert.ok((both.robustness.deflated_owner!.dsr ?? 0) <= (line.robustness.deflated.dsr ?? 1), 'more trials, a stricter (lower) deflated Sharpe');
});
