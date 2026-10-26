/* The backtest result (contract.ts BacktestResult) from an engine run's ledger: every number the page shows, computed
   as backtest.html computes it in run() (section 10: vals, st, bst, the OOS cut, in- and out-of-sample statistics,
   the trade split, the grid, the trials) and in its renderers (section 11: monthly heatmap, annual bars, weekday bars,
   rolling Sharpe, drawdown table, exit reasons, P&L by stock, streaks, Monte Carlo legends), so the page only formats.
   tests/result.test.ts checks the tables against hand-computed ledgers and against the page's own arithmetic
   (tests/stats-oracle.mjs). Nothing non-finite leaves: '—' on the page is null here, an infinite profit factor 'inf',
   and assertFiniteJson refuses a result that would still carry NaN or ±Infinity.
   Pure module: no DOM and no Node API. */
import type { AnnualRow, BacktestResult, DrawdownPeriod, ExitReason, MonthlyRow, Sensitivity, SensitivityCell, Trade, WeekdayRow } from './contract.ts';
import type { Ledger, LedgerTrade, ResultInput } from './ledger.ts';
import { finiteOrNull, mean, quant, sd, seriesStats, skew, toSeriesStats, toTradeStats, tradeStats } from './stats.ts';
import { cellStats, deflatedSharpe, monteCarlo, monteCarloScale, sensitivityPlan, trialSet, trialSharpe } from './robustness.ts';
import type { RunVariant } from './robustness.ts';

const ROLL = 126;   // the page's rolling-Sharpe window (6 months of trading days)

/** Throws on anything JSON cannot carry exactly: NaN, ±Infinity, undefined inside an array, typed arrays (they
    serialise as objects), functions, bigints. `undefined` object properties are allowed (JSON leaves them out). */
export function assertFiniteJson(value: unknown, path = 'result'): void {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return;
  if (typeof value === 'number') { if (!Number.isFinite(value)) throw new Error(`${path} is ${value}, which JSON cannot carry`); return }
  if (typeof value !== 'object') throw new Error(`${path} is a ${typeof value}, which JSON cannot carry`);
  if (ArrayBuffer.isView(value)) throw new Error(`${path} is a typed array; the wire needs a plain array`);
  if (Array.isArray(value)) { for (let i = 0; i < value.length; i++) { if (value[i] === undefined) throw new Error(`${path}[${i}] is undefined`); assertFiniteJson(value[i], `${path}[${i}]`) } return }
  for (const [k, v] of Object.entries(value)) if (v !== undefined) assertFiniteJson(v, `${path}.${k}`);
}

function checkLedger(L: Ledger): void {
  const n = L.dates.length;
  if (n < 1) throw new Error('ledger: the result calendar is empty');
  for (const [k, a] of [['equity', L.equity], ['exposure', L.exposure], ['benchmark_close', L.benchmark_close]] as const)
    if (a.length !== n) throw new Error(`ledger: ${k} has ${a.length} values for ${n} calendar days`);
  // the page scales the benchmark by its first close and divides consecutive values: every day needs a close
  L.benchmark_close.forEach((c, k) => { if (!(typeof c === 'number' && Number.isFinite(c) && c > 0)) throw new Error(`ledger: the benchmark ${L.benchmark.ticker} has no close on or before ${L.dates[k]}`) });
  for (const t of L.trades) for (const k of ['signal_bar', 'entry_bar', 'exit_bar'] as const)
    if (!(Number.isInteger(t[k]) && t[k] >= 0 && t[k] < n)) throw new Error(`ledger: ${t.ticker} trade ${k} ${t[k]} is outside the calendar`);
}

/* ---- tabOverview: monthly heatmap and annual bars ---------------------------------------------------------------- */
/* Per month the page keeps s = the value before the month's first day (or the first value), e = the month's last
   value, and the same for the benchmark; a month's return is e / s - 1, the heatmap's year total compounds the months,
   the annual bars divide the year's last value by the value before its first day. */
function calendarTables(dates: string[], vals: number[], bench: number[], T: readonly LedgerTrade[]): { monthly: MonthlyRow[]; annual: AnnualRow[] } {
  const m = new Map<string, { s: number; e: number; bs: number; be: number }>();
  vals.forEach((v, k) => { const ym = dates[k].slice(0, 7); let o = m.get(ym); if (!o) { o = { s: k ? vals[k - 1] : v, e: v, bs: k ? bench[k - 1] : bench[0], be: bench[k] }; m.set(ym, o) } o.e = v; o.be = bench[k] });
  const years = [...new Set([...m.keys()].map(k => k.slice(0, 4)))];
  const monthly: MonthlyRow[] = [], annual: AnnualRow[] = [];
  for (const y of years) {
    let yr = 1; const ms: [number, number][] = [];
    for (let k = 0; k < 12; k++) {
      const e = m.get(`${y}-${String(k + 1).padStart(2, '0')}`);
      if (!e) continue;
      const r = e.e / e.s - 1, br = e.be / e.bs - 1; yr *= 1 + r; ms.push([k + 1, r]);
      monthly.push({ year: +y, month: k + 1, ret: r, benchmark_ret: br, ytd: yr - 1 });
    }
    const best = ms.reduce((a, b) => b[1] > a[1] ? b : a, ms[0]), worst = ms.reduce((a, b) => b[1] < a[1] ? b : a, ms[0]), up = ms.filter(x => x[1] > 0).length;
    // annual bars: the heatmap's year benchmark (last month's be / first month's bs) is the same division
    let a = -1, b = -1; for (let k = 0; k < dates.length; k++) if (dates[k].startsWith(y)) { if (a < 0) a = k; b = k }
    const s0 = a ? vals[a - 1] : vals[0], b0 = a ? bench[a - 1] : bench[0];
    let pk = s0, mdd = 0; for (let k = a; k <= b; k++) { pk = Math.max(pk, vals[k]); mdd = Math.min(mdd, vals[k] / pk - 1) }
    const tr = T.filter(t => dates[t.exit_bar].startsWith(y));
    annual.push({
      year: +y, ret: vals[b] / s0 - 1, benchmark_ret: bench[b] / b0 - 1, max_drawdown: mdd, trades_closed: tr.length,
      win_rate: tr.length ? tr.filter(t => t.return > 0).length / tr.length : null,
      months_compound: yr - 1, best_month: { month: best[0], ret: best[1] }, worst_month: { month: worst[0], ret: worst[1] },
      positive_months: up, months: ms.length,
    });
  }
  return { monthly, annual };
}

/* ---- tabReturns: weekday bars, rolling Sharpe ------------------------------------------------------------------- */
function weekdays(dates: string[], vals: number[]): WeekdayRow[] {
  const dow = dates.map(d => new Date(d).getUTCDay());       // the page: new Date('YYYY-MM-DD') is UTC midnight
  return ([1, 2, 3, 4, 5] as const).map(d => {
    const rr: number[] = []; for (let k = 1; k < vals.length; k++) if (dow[k] === d) rr.push(vals[k] / vals[k - 1] - 1);
    let best = -Infinity, worst = Infinity; for (const x of rr) { best = Math.max(best, x); worst = Math.min(worst, x) }
    return { weekday: d, mean: mean(rr), median: rr.length ? quant(rr, .5) : null, positive_share: rr.filter(x => x > 0).length / (rr.length || 1), days: rr.length,
      best: rr.length ? best : null, worst: rr.length ? worst : null };
  });
}
/* roll[k] uses the 126 returns before return k (slice(k-126, k): the current return is not in its own window); the
   tooltip's 6-month return compounds the same window; the share above 1 counts the finite points. */
function rolling(r: number[]) {
  const roll: (number | null)[] = [], ret: (number | null)[] = [];
  let above = 0, finite = 0;
  for (let k = 0; k < r.length; k++) {
    if (k < ROLL) { roll.push(null); ret.push(null); continue }
    const s = r.slice(k - ROLL, k), v = sd(s) ? mean(s) / sd(s) * Math.sqrt(252) : 0;
    let p = 1; for (const x of s) p = p * (1 + x);
    roll.push(v); ret.push(p - 1); finite++; if (v >= 1) above++;
  }
  return { roll, ret, above: finite ? above / finite : null };
}

/* ---- tabRisk: ddTable -------------------------------------------------------------------------------------------- */
/* A drawdown starts at the last value at or above every earlier one (the peak), its trough is the lowest value before
   the first value at or above the peak again (the recovery); still open at the end = recovery null, days counted to
   the last day. Deepest first (a stable sort keeps equal depths in time order), five rows. */
function drawdowns(v: number[]): DrawdownPeriod[] {
  const out: { s: number; t: number; e: number | null; d: number }[] = [];
  let pk = 0, inDD = false, st = 0, trough = 0;
  for (let k = 1; k < v.length; k++) {
    if (v[k] >= v[pk]) { if (inDD) { out.push({ s: st, t: trough, e: k, d: v[trough] / v[st] - 1 }); inDD = false } pk = k }
    else { if (!inDD) { inDD = true; st = pk; trough = k } if (v[k] < v[trough]) trough = k }
  }
  if (inDD) out.push({ s: st, t: trough, e: null, d: v[trough] / v[st] - 1 });
  out.sort((a, b) => a.d - b.d);
  return out.slice(0, 5).map(d => ({ peak: d.s, trough: d.t, recovery: d.e, depth: d.d, bars: (d.e ?? v.length - 1) - d.s }));
}

/* ---- tabTrades: exit reasons, per ticker, streaks; the trade list ------------------------------------------------ */
function groupBy<K>(T: readonly LedgerTrade[], key: (t: LedgerTrade) => K): Map<K, LedgerTrade[]> {
  const g = new Map<K, LedgerTrade[]>();
  for (const t of T) { const k = key(t); const a = g.get(k); if (a) a.push(t); else g.set(k, [t]) }
  return g;
}
const sumPnl = (T: readonly LedgerTrade[]) => T.reduce((s, t) => s + t.pnl_idr, 0);

function exitReasons(T: readonly LedgerTrade[]): BacktestResult['tables']['exit_reasons'] {
  return [...groupBy(T, t => t.exit_reason)].map(([reason, tt]: [ExitReason, LedgerTrade[]]) => ({
    reason, trades: tt.length, wins: tt.filter(t => t.return > 0).length, avg_return: mean(tt.map(t => t.return)),
    pnl_idr: sumPnl(tt), avg_bars: mean(tt.map(t => t.bars_held)),
  }));
}

/* the page's signals table (trades, wins, P&L per ticker; universe order from the engine) plus the P&L-by-stock
   tooltip (average return, share of the total P&L with the page's `|| 1`) */
function perTicker(L: Ledger): BacktestResult['tables']['per_ticker'] {
  const by = groupBy(L.trades, t => t.ticker), total = sumPnl(L.trades) || 1, known = new Set(L.per_ticker_signals.map(r => r.ticker));
  for (const tk of by.keys()) if (!known.has(tk)) throw new Error(`ledger: ${tk} has trades but no row in per_ticker_signals`);
  return L.per_ticker_signals.map(r => {
    const tr = by.get(r.ticker) ?? [], pnl = sumPnl(tr);
    return { ticker: r.ticker, entry_signals: r.entry_signals, last_signal: r.last_signal, trades: tr.length, wins: tr.filter(t => t.return > 0).length, pnl_idr: pnl,
      avg_return: tr.length ? mean(tr.map(t => t.return)) : null, pnl_share: tr.length ? pnl / total : null };
  });
}

/** Contract trades in ledger order. trade_id n = the trade's place among its ticker's trades by entry (1 = first);
    streak = its place in the current run of wins or losses, streak_length = that run's length (page tabTrades). */
function trades(L: Ledger): Trade[] {
  const T = L.trades, d = L.dates;
  const ord = new Array<number>(T.length), byTk = new Map<string, number[]>();
  T.forEach((t, i) => { const a = byTk.get(t.ticker); if (a) a.push(i); else byTk.set(t.ticker, [i]) });
  for (const idx of byTk.values()) idx.sort((a, b) => T[a].entry_bar - T[b].entry_bar || a - b).forEach((i, k) => { ord[i] = k + 1 });
  let run = 0, prev: boolean | null = null;
  const pos = T.map(t => { const w = t.return > 0; run = w === prev ? run + 1 : 1; prev = w; return run });
  const len = pos.slice();                                   // the page's forward scan, as one backward pass
  for (let i = pos.length - 2; i >= 0; i--) if (pos[i + 1] > pos[i]) len[i] = len[i + 1];
  return T.map((t, i) => ({
    trade_id: `${t.ticker}-${d[t.entry_bar]}-${ord[i]}`,
    ticker: t.ticker, signal_date: d[t.signal_bar], signal_event: t.signal_event,
    entry_date: d[t.entry_bar], entry_price: t.entry_price, exit_date: d[t.exit_bar], exit_price: t.exit_price,
    exit_reason: t.exit_reason, exit_phase: t.exit_phase, shares: t.shares, lots: t.shares / 100, bars_held: t.bars_held,
    cost_idr: t.cost_idr, proceeds_idr: t.proceeds_idr, pnl_idr: t.pnl_idr, return: t.return, mae: t.mae, mfe: t.mfe,
    initial_stop: t.initial_stop, initial_target: t.initial_target, initial_risk_pct: t.initial_risk_pct,
    entry_condition_ids: [...t.entry_condition_ids],
    flags: { corporate_actions: t.flags.corporate_actions.map(c => ({ ...c })), stop_and_target_same_bar: t.flags.stop_and_target_same_bar, stale_mark: t.flags.stale_mark },
    streak: pos[i], streak_length: len[i],
  }));
}

/* ---- sensitivity ------------------------------------------------------------------------------------------------- */
const same = (a: readonly unknown[], b: readonly unknown[]) => a.length === b.length && a.every((x, i) => Object.is(x, b[i]));

/** The grid from the cells' runs; the axes must be the request's own plan (robustness.ts sensitivityPlan), and a cell
    is null exactly where the plan has no request (a threshold conditions.ts refuses). */
function sensitivity(input: ResultInput, variants: RunVariant[]): Sensitivity | null {
  const plan = sensitivityPlan(input.request), s = input.sensitivity;
  if (!plan && !s) return null;
  if (!plan || !s) throw new Error(plan ? 'result: the request has a sensitivity grid but the run sent no cells' : 'result: sensitivity cells sent for a request without a grid');
  for (const k of ['condition_id', 'y_key', 'base_x', 'base_y'] as const) if (!Object.is(plan[k], s[k])) throw new Error(`result: sensitivity ${k} ${String(s[k])} is not the request's ${String(plan[k])}`);
  for (const k of ['xs', 'xs_display', 'ys', 'ys_display'] as const) if (!same(plan[k], s[k])) throw new Error(`result: sensitivity ${k} differ from the request's grid`);
  const cells: (SensitivityCell | null)[][] = plan.requests.map((row, i) => row.map((req, j) => {
    const c = s.cells[i]?.[j];
    if (!req) { if (c) throw new Error(`result: sensitivity cell [${i}][${j}] has a run but its threshold is refused`); return null }
    if (!c) throw new Error(`result: sensitivity cell [${i}][${j}] is missing`);
    const cell = cellStats(c.ledger);
    variants.push({ variant_hash: c.variant_hash, sharpe_daily: trialSharpe(cell), kind: 'sensitivity' });
    return cell;
  }));
  return { condition_id: plan.condition_id, x_param: 'value', xs: plan.xs, xs_display: plan.xs_display, y_key: plan.y_key, ys: plan.ys, ys_display: plan.ys_display,
    base_x: plan.base_x, base_y: plan.base_y, cells };
}

/* ---- the result ------------------------------------------------------------------------------------------------- */
export function buildResult(input: ResultInput): BacktestResult {
  const q = input.request, L = input.ledger;
  checkLedger(L);
  const n = L.dates.length, dates = L.dates, vals = L.equity, cap0 = q.sizing.capital_idr, T = L.trades;
  // backtest(): the benchmark scaled to the capital on the first day; run(): st, bst, the OOS cut and its splits
  const b0 = L.benchmark_close[0], bench = L.benchmark_close.map(v => v / b0 * cap0);
  const st = seriesStats(vals, bench), bst = seriesStats(bench);
  const f = q.period.oos_fraction;
  const cut = f ? Math.floor(n * (1 - f)) : n;
  const ins = cut > 20 ? seriesStats(vals.slice(0, cut), bench.slice(0, cut)) : null;
  const oos = f && n - cut > 20 ? seriesStats(vals.slice(cut - 1), bench.slice(cut - 1)) : null;
  const cutDay = cut >= 1 ? cut - 1 : null;                 // page: res.eq[cut-1] ? its day : null
  const tsIn = tradeStats(T.filter(t => cutDay == null || t.entry_bar <= cutDay));
  const tsOut = oos ? tradeStats(T.filter(t => cutDay != null && t.entry_bar > cutDay)) : null;   // shown only with OOS stats

  const variants: RunVariant[] = [{ variant_hash: input.variant_hash, sharpe_daily: trialSharpe(st), kind: 'run' }];
  const grid = sensitivity(input, variants);
  const tset = trialSet(input.prior_trials, variants);
  const rets = T.map(t => t.return), cal = calendarTables(dates, vals, bench, T), roll = rolling(st.r);

  const result: BacktestResult = {
    schema_version: 1,
    meta: {
      engine_version: input.versions.engine_version, registry_version: input.versions.registry_version,
      data_version: input.versions.data_version, request_hash: input.request_hash, lineage_key: input.lineage_key,
      seed: q.robustness.seed, duration_ms: input.duration_ms, mode: q.mode, tickers: input.tickers,
      benchmark: L.benchmark, data_through: input.versions.data_through, warnings: L.warnings,
      trials: { prior: tset.prior, this_run: tset.this_run, total: tset.total, variants: tset.variants },
    },
    dates, equity: vals, benchmark: bench, drawdown: st.dd, exposure: L.exposure, daily_returns: st.r,
    oos: { fraction: f, cut, cut_date: cutDay != null ? dates[cutDay] : null },
    stats: { all: toSeriesStats(st), in_sample: ins && toSeriesStats(ins), out_of_sample: oos && toSeriesStats(oos), benchmark: toSeriesStats(bst), exposure_mean: mean(L.exposure) },
    trade_stats: { all: toTradeStats(tradeStats(T)), in_sample: toTradeStats(tsIn), out_of_sample: tsOut && toTradeStats(tsOut) },
    trade_returns: { mean: mean(rets), median: rets.length ? quant(rets, .5) : null, sd: sd(rets), skew: T.length > 3 ? finiteOrNull(skew(rets)) : null },
    tables: {
      monthly: cal.monthly, annual: cal.annual, weekday: weekdays(dates, vals),
      rolling_sharpe_126: roll.roll, rolling_return_126: roll.ret, rolling_sharpe_126_share_above_1: roll.above,
      drawdowns: drawdowns(vals), exit_reasons: exitReasons(T), per_ticker: perTicker(L),
    },
    trades: trades(L),
    events: L.events,
    robustness: {
      monte_carlo: monteCarlo(T, monteCarloScale(q), q.robustness.monte_carlo_runs, q.robustness.seed),
      sensitivity: grid,
      deflated: deflatedSharpe(st, tset.srs),
    },
  };
  assertFiniteJson(result);
  return result;
}
