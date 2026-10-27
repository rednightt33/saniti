/* The server's BacktestResult (contract.ts) in the shape the reference's renderers read (backtest.html section 10, the
   object `run` stores in S.result): calendar indices into the result's own days, the reference's short names for the
   statistics, Infinity for an infinite profit factor, exit reasons as the page labels them. Pure: no DOM. */
import type { BacktestRequest, BacktestResultCore, ExitReason, SeriesStats, SignalTrack, TradeStats } from '../core/contract.ts';
import type { Card } from './types.ts';

export const WHY: Record<ExitReason, string> = {
  stop_loss:'Stop loss', trailing_stop:'Trailing stop', take_profit:'Take profit', time_exit:'Time exit', exit_signal:'Exit signal', end_of_test:'End of test',
};

export interface PageStats {
  tot: number; cagr: number; vol: number; sharpe: number; srd: number; sortino: number; mdd: number; calmar: number; maxDur: number; ulcer: number;
  var95: number; cvar95: number; skew: number | null; kurt: number | null; beta: number | null; alpha: number | null; corr: number | null;
  best: number; worst: number; pos: number; n: number; psr: (sr0: number) => number | null;
  r: number[]; dd: number[];
}
export interface PageTradeStats {
  n: number; wins: number; losses: number; wr: number; aw: number; al: number; payoff: number; pf: number; gp: number; gl: number; net: number;
  exp: number; expRp: number; sqn: number; expR: number; mw: number; ml: number; best: number; worst: number;
  hold: number; holdW: number; holdL: number; kelly: number; mae: number; mfe: number;
}
export interface PageTrade {
  id: string; tk: string; sig: number; ei: number; xi: number; entry: number; exit: number; sh: number; cost: number; pnl: number; ret: number;
  bars: number; mae: number; mfe: number; why: string; riskPct: number | null;
}
export interface GridY { k: 'sl' | 'slAtr' | 'slRR' | 'hold'; lbl: string; u: string; step: number; min: number }
export interface PageCell { sharpe: number; cagr: number; pf: number; n: number; mdd: number }
/** cells[y][x]; null: a cell the condition refuses (its threshold is not a value the condition takes), not run */
export interface PageGrid { cond: any; xs: number[]; ys: number[]; yk: GridY; cells: (PageCell | null)[][] }
export interface PageMC { bands: number[][]; mdds: number[]; fin: number[]; n: number; below: number[]; actual: number[] }

export interface PageResult {
  id: string; raw: BacktestResultCore;
  days: string[]; eq: [number, number][]; vals: number[]; bench: number[]; expo: number[]; cap0: number; first: number;
  st: PageStats; bst: PageStats; ins: PageStats | null; oos: PageStats | null; cut: number; cutDay: number | null;
  ts: PageTradeStats; tsIn: PageTradeStats; tsOut: PageTradeStats;
  trades: PageTrade[]; grid: PageGrid | null; mc: PageMC | null; ds: { sr0: number; dsr: number };   // NaN where the server sends null (the reference's NaN)
  ms: number; trials: number;
  /** the run's events: the entry track of every ticker, the condition tracks per ticker as they are read */
  ev: { entries: Record<string, SignalTrack>; cond: Map<string, Map<string, SignalTrack>> };
  /** comparison closes on `days`, per ticker, as they are loaded */
  cmp: Map<string, (number | null)[]>;
}

const pf = (v: number | 'inf') => v === 'inf' ? Infinity : v;
export function seriesStats(s: SeriesStats, r: number[] = [], dd: number[] = []): PageStats {
  return { tot:s.total_return, cagr:s.cagr, vol:s.volatility, sharpe:s.sharpe, srd:s.sharpe_daily, sortino:s.sortino, mdd:s.max_drawdown, calmar:s.calmar,
    maxDur:s.longest_drawdown_bars, ulcer:s.ulcer_index, var95:s.var_95, cvar95:s.cvar_95, skew:s.skew, kurt:s.kurtosis, beta:s.beta, alpha:s.alpha,
    corr:s.correlation, best:s.best_day, worst:s.worst_day, pos:s.positive_days, n:s.n_returns,
    // the renderers read the probabilistic Sharpe against 0 only (Risk & ratios, Robustness)
    psr: (sr0: number) => sr0 === 0 ? s.psr_0 : null, r, dd };
}
const EMPTY_TS: TradeStats = { n:0, wins:0, losses:0, win_rate:0, avg_win:0, avg_loss:0, payoff:0, profit_factor:0, gross_profit_idr:0, gross_loss_idr:0, net_idr:0,
  expectancy:0, expectancy_idr:0, sqn:0, expectancy_r:0, max_consecutive_wins:0, max_consecutive_losses:0, best:0, worst:0, avg_hold_bars:0,
  avg_hold_bars_winners:0, avg_hold_bars_losers:0, kelly:0, avg_mae:0, avg_mfe:0 };
export function tradeStats(t: TradeStats | null): PageTradeStats {
  const x = t || EMPTY_TS;
  return { n:x.n, wins:x.wins, losses:x.losses, wr:x.win_rate, aw:x.avg_win, al:x.avg_loss, payoff:x.payoff, pf:pf(x.profit_factor), gp:x.gross_profit_idr,
    gl:x.gross_loss_idr, net:x.net_idr, exp:x.expectancy, expRp:x.expectancy_idr, sqn:x.sqn, expR:x.expectancy_r, mw:x.max_consecutive_wins,
    ml:x.max_consecutive_losses, best:x.best, worst:x.worst, hold:x.avg_hold_bars, holdW:x.avg_hold_bars_winners, holdL:x.avg_hold_bars_losers,
    kelly:x.kelly, mae:x.avg_mae, mfe:x.avg_mfe };
}

/* the reference's sensitivity rows (GRID_Y): what varies on y, its label, unit, step and minimum */
export const GRID_Y: Record<string, GridY> = {
  stop_pct: {k:'sl', lbl:'SL %', u:'%', step:2, min:1},
  stop_atr_mult: {k:'slAtr', lbl:'SL × ATR', u:'×', step:.5, min:.5},
  stop_reward_risk_x: {k:'slRR', lbl:'R:R (1 : x)', u:'', step:.5, min:.5},
  max_hold_bars: {k:'hold', lbl:'Max hold (days)', u:'d', step:5, min:2},
};

/** `cards`: the entry cards the run was built from (the sensitivity grid names its condition by the card) */
export function adaptResult(id: string, res: BacktestResultCore, request: BacktestRequest, cards: Card[]): PageResult {
  const days = res.dates, at = new Map(days.map((d, k) => [d, k])), ix = (d: string) => at.get(d) ?? -1;
  const trades: PageTrade[] = res.trades.map(t => ({
    id:t.trade_id, tk:t.ticker, sig:ix(t.signal_date), ei:ix(t.entry_date), xi:ix(t.exit_date), entry:t.entry_price, exit:t.exit_price, sh:t.shares,
    cost:t.cost_idr, pnl:t.pnl_idr, ret:t.return, bars:t.bars_held, mae:t.mae, mfe:t.mfe, why:WHY[t.exit_reason] || t.exit_reason, riskPct:t.initial_risk_pct,
  }));
  const s = res.robustness.sensitivity, c0 = s && cards.find(c => c.id === s.condition_id);
  const grid: PageGrid | null = s && c0 ? {
    // the heatmap outlines the cell of the current settings by comparing with the card's value (display units)
    cond: c0.type === 'reg' ? { ...c0, val: (c0 as any).rhs.v } : c0,
    xs: s.xs_display, ys: s.ys_display, yk: GRID_Y[s.y_key],
    // a cell the condition refuses was not run: it stays null (no numbers, no trade count)
    cells: s.cells.map(row => row.map(c => c ? { sharpe:c.sharpe, cagr:c.cagr, pf:pf(c.profit_factor), n:c.trades, mdd:c.max_drawdown } : null)),
  } : null;
  const m = res.robustness.monte_carlo;
  const mc: PageMC | null = m ? { bands:[m.bands.p05, m.bands.p25, m.bands.p50, m.bands.p75, m.bands.p95], mdds:m.max_drawdowns, fin:m.final_returns,
    n:m.n_trades, below:m.below_start, actual:m.actual } : null;
  const cond = new Map<string, Map<string, SignalTrack>>();
  for (const e of res.events.conditions || []) {
    let byId = cond.get(e.ticker); if (!byId) cond.set(e.ticker, byId = new Map());
    byId.set(e.condition_id, e.track);
  }
  const cut = res.oos.cut;
  return {
    id, raw:res, days, eq:res.equity.map((v, k) => [k, v] as [number, number]), vals:res.equity, bench:res.benchmark, expo:res.exposure,
    cap0:request.sizing.capital_idr, first:0,
    st:seriesStats(res.stats.all, res.daily_returns, res.drawdown), bst:seriesStats(res.stats.benchmark),
    ins:res.stats.in_sample ? seriesStats(res.stats.in_sample) : null, oos:res.stats.out_of_sample ? seriesStats(res.stats.out_of_sample) : null,
    cut, cutDay:cut > 0 && cut <= days.length ? cut - 1 : null,
    ts:tradeStats(res.trade_stats.all), tsIn:tradeStats(res.trade_stats.in_sample), tsOut:tradeStats(res.trade_stats.out_of_sample),
    trades, grid, mc, ds:{ sr0:res.robustness.deflated.sr0 ?? NaN, dsr:res.robustness.deflated.dsr ?? NaN },
    ms:res.meta.duration_ms, trials:res.meta.trials.total,
    ev:{ entries:res.events.entries || {}, cond },
    cmp:new Map(),
  };
}
