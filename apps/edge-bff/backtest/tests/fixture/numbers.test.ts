/* Numeric check of the fixture (task: the reference's own result numbers equal buildResult's, field by field).
   For each setting, two paths on the reference's synthetic market:
   - reference: its state S as the reference holds it, run by its own run() (mockup.js runMockup) -> R;
   - page: the same settings as the page's request (src/api/request.ts buildRequest), back to S (state.ts), the same
     run, its ledger, and the production result builder (core/result.ts) -> BacktestResult.
   Then R.st, R.bst, R.ins, R.oos, R.ts, R.tsIn, R.tsOut, the series, the trades, the grid cells, the Monte Carlo and
   R.ds are compared with the result's fields. Every mismatch is printed with its field and both values; the test
   fails on any mismatch that is not one of the documented decisions in KNOWN. This cross-checks the shared statistics
   (core/stats.ts, robustness.ts, result.ts) against the reference's own arithmetic and the page's request mapping. */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import type { BacktestResult, SeriesStats, TradeStats } from '../../src/core/contract.ts';
import { ENTRY_TEMPLATES, legacyCard } from '../../src/core/catalog.ts';
import { buildRequest } from '../../src/api/request.ts';
import { REG_BY } from '../../src/reg.ts';
import * as M from './mockup.js';
import { newSession, runRequest } from './run.ts';

/* ---- the reference's settings ------------------------------------------------------------------------------------ */
let seq = 0;
const card = (type: string, over: Record<string, unknown> = {}) => legacyCard(type as any, `c${++seq}`, over as any);
/** the reference's S at load (backtest.html section 4), with fixed card ids */
function refState(): any {
  return {
    mode:'single', ticker:'MAPI', universe:'ALL', maxPos:5, rankBy:'adx', from:'2019-06-03', to:'2026-10-23', oos:30, logic:'n', atLeast:3, window:5,
    conds:[card('adx', { val:25 }), card('stoch', { op:'lt', val:30 }), card('macd', { op:'bdiv' }), card('fnet', { len:5, val:0 }), card('broker', { broker:'YU', len:5, val:1 })],
    exit:{ stopMode:'pct', sl:7, slAtr:2, slRR:2, atrLen:14, stopLine:{ id:'I09', o:'supertrend' }, tpMode:'pct', tp:15, tpR:2, tpAtr:3, trailMode:'none', trail:5, chLen:22, chK:3, trailLine:{ id:'I01', o:'sma' }, hold:20 },
    exitConds:[], exitLogic:'any', size:{ capital:100e6, alloc:100 }, cost:{ buy:.15, sell:.25, slip:.05, ara:true, minVal:5 },
    sigTicker:'MAPI', bench:'bh', cmp:[], step:2, view:'signals', stale:false, hidden:{}, trials:0, result:null, tab:'overview', heatMetric:'sharpe',
  };
}
const regCard = (ind: string, over: Record<string, unknown>) => ({ id:`c${++seq}`, type:'reg', on:true, ind, p:M.regDefaults(REG_BY[ind]), ...over });

const CASES: [string, (s: any) => void][] = [
  ['default settings', () => {}],
  ...Object.entries(ENTRY_TEMPLATES).map(([k, cards]): [string, (s: any) => void] => [`template ${k}`, s => { s.conds = cards.map(([t, over]) => card(t, over as any)) }]),
  ...['atr', 'rr', 'line', 'none'].map((m): [string, (s: any) => void] => [`stop ${m}`, s => { s.exit.stopMode = m }]),
  ['take profit R with stop %', s => { s.exit.tpMode = 'r' }],
  ['trailing chandelier', s => { s.exit.trailMode = 'chand' }],
  ['exit signal RSI > 70', s => { s.exitConds = [regCard('I13', { lhs:{ t:'out', o:'rsi' }, op:'gt', rhs:{ t:'val', v:70 } })] }],
  ['portfolio Demo 10', s => { s.mode = 'portfolio' }],
  ['portfolio Banks, rank by RSI, benchmark IHSG', s => { s.mode = 'portfolio'; s.universe = 'BANK'; s.rankBy = 'rsi' }],
  ['single, benchmark IHSG, no OOS', s => { s.bench = 'ihsg'; s.oos = 0 }],
];

/* ---- documented differences (CONTRACT.md decisions), not page or statistics errors ------------------------------ */
const KNOWN: [RegExp, string][] = [
  [/^ds\.(sr0|dsr)$/, 'K3: the result counts the trials of the strategy line and takes the variance of all their Sharpes, the run included; the reference takes the variance of the 25 grid cells only'],
  [/^(grid\.cells\[\d\]\[\d\]\..*|trials)$/, 'D-grid: a cell whose threshold conditions.ts refuses (volume ratio 0) is not run, so it has no numbers and is no trial'],
];

/* ---- comparison ---------------------------------------------------------------------------------------------- */
type Miss = { field: string; reference: unknown; result: unknown };
const SERIES: [string, keyof SeriesStats][] = [['tot', 'total_return'], ['cagr', 'cagr'], ['vol', 'volatility'], ['sharpe', 'sharpe'], ['srd', 'sharpe_daily'],
  ['sortino', 'sortino'], ['mdd', 'max_drawdown'], ['calmar', 'calmar'], ['maxDur', 'longest_drawdown_bars'], ['ulcer', 'ulcer_index'], ['var95', 'var_95'],
  ['cvar95', 'cvar_95'], ['skew', 'skew'], ['kurt', 'kurtosis'], ['beta', 'beta'], ['alpha', 'alpha'], ['corr', 'correlation'], ['best', 'best_day'],
  ['worst', 'worst_day'], ['pos', 'positive_days'], ['n', 'n_returns']];
const TRADES: [string, keyof TradeStats][] = [['n', 'n'], ['wins', 'wins'], ['losses', 'losses'], ['wr', 'win_rate'], ['aw', 'avg_win'], ['al', 'avg_loss'],
  ['payoff', 'payoff'], ['pf', 'profit_factor'], ['gp', 'gross_profit_idr'], ['gl', 'gross_loss_idr'], ['net', 'net_idr'], ['exp', 'expectancy'],
  ['expRp', 'expectancy_idr'], ['sqn', 'sqn'], ['expR', 'expectancy_r'], ['mw', 'max_consecutive_wins'], ['ml', 'max_consecutive_losses'], ['best', 'best'],
  ['worst', 'worst'], ['hold', 'avg_hold_bars'], ['holdW', 'avg_hold_bars_winners'], ['holdL', 'avg_hold_bars_losers'], ['kelly', 'kelly'], ['mae', 'avg_mae'], ['mfe', 'avg_mfe']];

/** the wire's encoding of a reference number: NaN and ±Infinity are null, an infinite profit factor 'inf' */
const same = (ref: unknown, res: unknown) => {
  if (res === 'inf') return ref === Infinity;
  if (typeof ref === 'number' && !Number.isFinite(ref) && res === null) return true;
  return Object.is(ref, res) || (ref === null && res === null);
};
function compare(R: any, res: BacktestResult, trials: number): Miss[] {
  const out: Miss[] = [];
  const val = (field: string, a: unknown, b: unknown) => { if (!same(a, b)) out.push({ field, reference:a, result:b }) };
  const arr = (field: string, a: ArrayLike<number> | null, b: ArrayLike<number | null> | null) => {
    if (!a || !b) { val(field, a && 'array', b && 'array'); return }
    if (a.length !== b.length) { out.push({ field:`${field}.length`, reference:a.length, result:b.length }); return }
    for (let i = 0; i < a.length; i++) val(`${field}[${i}]`, a[i], b[i]);
  };
  const series = (field: string, s: any, w: SeriesStats | null) => {
    if (!s || !w) { val(field, s ? 'stats' : null, w ? 'stats' : null); return }
    for (const [k, wk] of SERIES) val(`${field}.${k}`, s[k], w[wk]);
    val(`${field}.psr(0)`, s.psr(0), w.psr_0);
  };
  const trades = (field: string, t: any, w: TradeStats | null) => {
    if (!w) { val(field, 'stats', null); return }
    for (const [k, wk] of TRADES) val(`${field}.${k}`, t[k], w[wk]);
  };
  arr('vals', R.vals, res.equity); arr('bench', R.bench, res.benchmark); arr('expo', R.expo, res.exposure);
  arr('st.dd', R.st.dd, res.drawdown); arr('st.r', R.st.r, res.daily_returns);
  val('cut', R.cut, res.oos.cut); val('cutDay', R.cutDay == null ? null : M.DAYS[R.cutDay], res.oos.cut_date);
  series('st', R.st, res.stats.all); series('bst', R.bst, res.stats.benchmark);
  series('ins', R.ins, res.stats.in_sample); series('oos', R.oos, res.stats.out_of_sample);
  trades('ts', R.ts, res.trade_stats.all); trades('tsIn', R.tsIn, res.trade_stats.in_sample);
  if (R.oos) trades('tsOut', R.tsOut, res.trade_stats.out_of_sample);
  val('trades.length', R.trades.length, res.trades.length);
  R.trades.forEach((t: any, i: number) => {
    const w = res.trades[i]; if (!w) return;
    for (const [k, v] of [['tk', w.ticker], ['ei', w.entry_date], ['xi', w.exit_date], ['entry', w.entry_price], ['exit', w.exit_price], ['sh', w.shares],
      ['bars', w.bars_held], ['pnl', w.pnl_idr], ['ret', w.return], ['mae', w.mae], ['mfe', w.mfe], ['riskPct', w.initial_risk_pct]] as [string, unknown][])
      val(`trades[${i}].${k}`, k === 'ei' || k === 'xi' ? M.DAYS[t[k]] : t[k], v);
  });
  const G = R.grid, s = res.robustness.sensitivity;
  if (!G || !s) val('grid', G ? 'grid' : null, s ? 'grid' : null);
  else {
    arr('grid.xs', G.xs, s.xs_display); arr('grid.ys', G.ys, s.ys_display); val('grid.cond', G.cond.id, s.condition_id);
    G.cells.forEach((row: any[], i: number) => row.forEach((c, j) => {
      const w = s.cells[i]?.[j];
      for (const [k, wk] of [['sharpe', 'sharpe'], ['cagr', 'cagr'], ['pf', 'profit_factor'], ['n', 'trades'], ['mdd', 'max_drawdown']] as const)
        val(`grid.cells[${i}][${j}].${k}`, c[k], w ? w[wk] : null);
    }));
  }
  const mc = R.mc, w = res.robustness.monte_carlo;
  if (!mc || !w) val('mc', mc ? 'mc' : null, w ? 'mc' : null);
  else {
    (['p05', 'p25', 'p50', 'p75', 'p95'] as const).forEach((q, b) => arr(`mc.bands[${b}]`, mc.bands[b], w.bands[q]));
    arr('mc.mdds', mc.mdds, w.max_drawdowns); arr('mc.fin', mc.fin, w.final_returns); arr('mc.below', mc.below, w.below_start); arr('mc.actual', mc.actual, w.actual);
    val('mc.n', mc.n, w.n_trades);
  }
  val('ds.sr0', R.ds.sr0, res.robustness.deflated.sr0); val('ds.dsr', R.ds.dsr, res.robustness.deflated.dsr);
  val('trials', trials, res.meta.trials.total); val('ms', R.ms, res.meta.duration_ms);
  return out;
}

/** the page's state for the same settings (the page's universe ids) and its request */
const requestOf = (s: any) => buildRequest({ ...s, universe:s.universe === 'BANK' ? 'sector:Banks' : 'all' }, { ready:c => M.condReady(c), monteCarloRuns:1000 });

describe('fixture: the reference run vs core/result.ts buildResult', () => {
  /* the run's duration (R.ms, meta.duration_ms) is the clock's; frozen like the visual harness, both read 0 */
  beforeAll(() => { vi.spyOn(performance, 'now').mockReturnValue(0) });
  afterAll(() => { vi.restoreAllMocks() });
  it.each(CASES)('%s', (name, edit) => {
    const s = refState(); edit(s);
    const request = requestOf(s);
    // the reference path
    M.setState(JSON.parse(JSON.stringify(s)));
    const ref = M.runMockup().R, trials = M.getState().trials;
    // the page path: request -> S -> the same run -> ledger -> buildResult
    const run = runRequest(request, newSession());
    // the request round trip gives the reference's own run
    const R = run.R;
    expect(R.vals).toEqual(ref.vals);
    expect(R.trades).toEqual(ref.trades);
    expect(R.grid && R.grid.cells).toEqual(ref.grid && ref.grid.cells);
    expect([R.ds.sr0, R.ds.dsr]).toEqual([ref.ds.sr0, ref.ds.dsr]);
    const miss = compare(ref, run.result, trials);
    const known = miss.map(m => KNOWN.find(([re]) => re.test(m.field))?.[1] ?? null);
    const lines = miss.map((m, i) => `  ${m.field}: reference ${String(m.reference)} | result ${String(m.result)}${known[i] ? `  [${known[i].split(':')[0]}]` : '  [UNEXPECTED]'}`);
    console.log(`${name}: ${R.trades.length} trades, grid ${run.gridFromReference ? 'from the reference' : 'planned by core'}, ${miss.length} mismatch(es)${lines.length ? '\n' + lines.join('\n') : ''}`);
    expect(miss.filter((_, i) => !known[i])).toEqual([]);
  }, 120_000);
});
