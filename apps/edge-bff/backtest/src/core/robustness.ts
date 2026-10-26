/* Robustness numbers of the backtest page (backtest.html sections 9 and 10): the Monte Carlo of reshuffled trade
   sequences, the Deflated Sharpe over the strategy line's trials (CONTRACT.md section 7, K3) and the sensitivity grid
   (the page's GRID_Y and xs/ys rules on the first enabled entry condition with a numeric threshold, D-grid).
   Pure module: no DOM and no Node API. */
import type { BacktestRequest, Condition, MonteCarlo, Sensitivity, SensitivityCell } from './contract.ts';
import type { Ledger, LedgerTrade } from './ledger.ts';
import { displayScale, threshold, withThreshold } from './catalog.ts';
import { thresholdAccepted } from './conditions.ts';
import { dsr, finiteOrNull, profitFactor, quant, seriesStats, tradeStats } from './stats.ts';
import type { SeriesStatsRaw } from './stats.ts';

/* ---- Monte Carlo ------------------------------------------------------------------------------------------------ */
/** Trade return × scale = the equity change of one trade: the single-stock allocation, or 1 / max positions. */
export function monteCarloScale(q: BacktestRequest): number {
  return q.mode === 'single' ? q.sizing.allocation_fraction : 1 / (q.portfolio as NonNullable<BacktestRequest['portfolio']>).max_positions;
}

/** The page's monteCarlo: `runs` sequences of n trades drawn with replacement by the page's LCG (Numerical Recipes
    constants, state in 32 bits) started at `seed`; growth of 1 after k trades, its 5/25/50/75/95 % quantiles (page
    `quant`, no interpolation), the share of runs below 1, the backtest's own order, and each run's final return and
    maximum drawdown. Null with fewer than 3 trades (page rule) or when the runs are switched off (0).
    The legend numbers the page derives from the runs (median / 5th / 95th final return, chance of loss, median and
    95 %-worst drawdown) are added with the same quant. */
export function monteCarlo(T: readonly Pick<LedgerTrade, 'return'>[], scale: number, runs: number, seed: number): MonteCarlo | null {
  if (T.length < 3 || !(runs > 0)) return null;
  const n = T.length, paths: Float64Array[] = [], mdds: number[] = [], fin: number[] = [];
  let s2 = seed;
  const r2 = () => ((s2 = (Math.imul(s2, 1664525) + 1013904223) >>> 0) / 4294967296);
  for (let k = 0; k < runs; k++) {
    let v = 1, pk = 1, md = 0; const path = new Float64Array(n + 1); path[0] = 1;
    for (let j = 0; j < n; j++) { const t = T[Math.floor(r2() * n)]; v *= 1 + t.return * scale; pk = Math.max(pk, v); md = Math.min(md, v / pk - 1); path[j + 1] = v }
    paths.push(path); mdds.push(md); fin.push(v - 1);
  }
  // one sort per step instead of one per quantile: the same sorted values (no NaN, no -0 in a product of factors
  // >= 0), so every band equals the page's quant(paths.map(p => p[j]), q)
  const Q = [.05, .25, .5, .75, .95], bands = Q.map(() => new Array<number>(n + 1)), below = new Array<number>(n + 1);
  const col = new Float64Array(runs);
  for (let j = 0; j <= n; j++) {
    let under = 0;
    for (let k = 0; k < runs; k++) { col[k] = paths[k][j]; if (paths[k][j] < 1) under++ }
    col.sort();
    Q.forEach((q, b) => { bands[b][j] = col[Math.min(runs - 1, Math.max(0, Math.floor(q * (runs - 1))))] });
    below[j] = under / runs;
  }
  const actual = [1]; for (const t of T) actual.push(actual[actual.length - 1] * (1 + t.return * scale));
  return {
    runs, seed, n_trades: n, scale,
    bands: { p05: bands[0], p25: bands[1], p50: bands[2], p75: bands[3], p95: bands[4] },
    below_start: below, actual, final_returns: fin, max_drawdowns: mdds,
    final_return_p05: quant(fin, .05), final_return_p50: quant(fin, .5), final_return_p95: quant(fin, .95),
    loss_share: fin.filter(x => x < 0).length / fin.length,
    max_drawdown_p50: quant(mdds, .5), max_drawdown_p05: quant(mdds, .05),
  };
}

/* ---- trials and the Deflated Sharpe (K3) ------------------------------------------------------------------------ */
export interface Trial { variant_hash: string; sharpe_daily: number }
export interface RunVariant extends Trial { kind: 'run' | 'sensitivity' }

/** A trial's daily Sharpe as the page puts it into dsr: the annualised Sharpe ÷ √252 (run(): c.sharpe / √252). */
export const trialSharpe = (st: Pick<SeriesStatsRaw, 'sharpe'>): number => st.sharpe / Math.sqrt(252);

/** The run's distinct variants (first occurrence of a hash wins, so the run itself wins over an identical cell). */
export function distinctVariants(variants: readonly RunVariant[]): RunVariant[] {
  const seen = new Set<string>(), out: RunVariant[] = [];
  for (const v of variants) if (!seen.has(v.variant_hash)) { seen.add(v.variant_hash); out.push(v) }
  return out;
}

/** The trials of the strategy line after this run: the distinct prior variants, then this run's distinct variants.
    A variant this run evaluated again takes this run's Sharpe (current data). prior = distinct prior variants,
    this_run = this run's variants not seen before, total = prior + this_run = the number of distinct trials; the
    Sharpe list follows the same order (prior order from edge-bff, then run, then cells [y][x]). */
export function trialSet(prior: readonly Trial[], variants: readonly RunVariant[]) {
  const own = distinctVariants(variants), ownHash = new Set(own.map(v => v.variant_hash));
  const seenPrior = new Set<string>(), priorKept: Trial[] = [];
  for (const p of prior) if (!seenPrior.has(p.variant_hash)) { seenPrior.add(p.variant_hash); if (!ownHash.has(p.variant_hash)) priorKept.push(p) }
  const srs = [...priorKept.map(p => p.sharpe_daily), ...own.map(v => v.sharpe_daily)];
  return { prior: seenPrior.size, this_run: srs.length - seenPrior.size, total: srs.length, srs, variants: own };
}

/** The page's dsr with trials = every distinct trial of the line; the variance of their daily Sharpes when there are
    at least 2, else the sample rule 1 / n (CONTRACT.md section 7). Null where the page would show '—' (NaN: a series
    without volatility or without returns). */
export function deflatedSharpe(st: SeriesStatsRaw, srs: readonly number[]) {
  const d = dsr(st, srs.length, srs);
  return { sr0: finiteOrNull(d.sr0), dsr: finiteOrNull(d.dsr), trials: srs.length, sharpe_variance_from: (srs.length > 1 ? 'trials' : 'sample') as 'trials' | 'sample' };
}

/* ---- sensitivity grid (D-grid) ---------------------------------------------------------------------------------- */
const KS = [-2, -1, 0, 1, 2];
type YKey = Sensitivity['y_key'];
/* The page's GRID_Y in display units, with the request field it varies and the conversion to the wire: the stop %
   is a percent on the page and a fraction on the wire (the page's exitLevels divides by 100). */
const GRID_Y: Record<'pct' | 'atr' | 'rr' | 'hold', { key: YKey; step: number; min: number; get: (q: BacktestRequest) => number; toWire: (y: number) => number; set: (q: BacktestRequest, y: number) => void }> = {
  pct: { key: 'stop_pct', step: 2, min: 1, get: q => q.exit.stop.pct * 100, toWire: y => y / 100, set: (q, y) => { q.exit.stop.pct = y } },
  atr: { key: 'stop_atr_mult', step: .5, min: .5, get: q => q.exit.stop.atr_mult, toWire: y => y, set: (q, y) => { q.exit.stop.atr_mult = y } },
  rr: { key: 'stop_reward_risk_x', step: .5, min: .5, get: q => q.exit.stop.reward_risk_x, toWire: y => y, set: (q, y) => { q.exit.stop.reward_risk_x = y } },
  hold: { key: 'max_hold_bars', step: 5, min: 2, get: q => q.exit.max_hold_bars, toWire: y => y, set: (q, y) => { q.exit.max_hold_bars = y } },
};
const gridY = (q: BacktestRequest) => { const m = q.exit.stop.mode; return GRID_Y[m === 'pct' || m === 'atr' || m === 'rr' ? m : 'hold'] };

/** Whether conditions.ts accepts this threshold: a price-action value must lie inside what it measures
    (conditions.ts PRICE_ACTION: dip > -1, volume ratio >= 0). The page's grid can step past it (volspike 1 → -1);
    such a cell is not run. */
function accepted(c: Condition, value: number): boolean {
  return c.kind !== 'price_action' || thresholdAccepted(c.type, value);
}

export interface SensitivityPlan {
  condition_id: string; xs: number[]; xs_display: number[]; y_key: YKey; ys: number[]; ys_display: number[];
  base_x: number; base_y: number;
  /** The 25 variant requests, [y][x]; null where the threshold is outside what conditions.ts accepts. Each has
      sensitivity and Monte Carlo off: a cell is one backtest, as on the page. */
  requests: (BacktestRequest | null)[][];
}

/** The page's grid on the request: x = the first enabled entry condition with a numeric threshold, base in display
    units (catalog.ts DISPLAY; wire ÷ scale), step = max(1, |base| × 0.2 || 1), xs = +(base + k·step).toFixed(2);
    y = the stop setting (pct: step 2 %, min 1 %; atr: 0.5 / 0.5; rr: 0.5 / 0.5; line or none: max hold, step 5,
    min 2), ys = +max(min, y0 + k·step).toFixed(2); k = -2..2. Wire values: x display × scale (catalog.ts), y as
    GRID_Y.toWire. Null when sensitivity is off or no enabled entry condition has a numeric threshold.
    Recovering the display base from the wire (e.g. -0.03 / 0.01 = -2.9999999999999996) can differ from the typed
    value by an ulp; after the page's 2-decimal rounding the axes are the page's for every base of at most 2 decimals
    (the grid values are then multiples of 0.002, far from a rounding boundary). */
export function sensitivityPlan(q: BacktestRequest): SensitivityPlan | null {
  if (!q.robustness.sensitivity) return null;
  const c0 = q.entry.conditions.find(c => c.enabled !== false && threshold(c) !== null);
  if (!c0) return null;
  const scale = displayScale(c0) as number, base_x = threshold(c0) as number, base = base_x / scale;
  const step = Math.max(1, Math.abs(base) * .2 || 1);
  const xs_display = KS.map(k => +(base + k * step).toFixed(2)), xs = xs_display.map(x => x * scale);
  const yk = gridY(q), y0 = yk.get(q);
  const ys_display = KS.map(k => +Math.max(yk.min, y0 + k * yk.step).toFixed(2)), ys = ys_display.map(yk.toWire);
  const base_y = yk.key === 'stop_pct' ? q.exit.stop.pct : y0;
  const requests = ys.map(y => xs.map(x => {
    if (!accepted(c0, x)) return null;
    const v = JSON.parse(JSON.stringify(q)) as BacktestRequest;
    v.entry.conditions = v.entry.conditions.map(c => c.id === c0.id ? withThreshold(c, x) : c);
    yk.set(v, y);
    v.robustness = { ...v.robustness, sensitivity: false, monte_carlo_runs: 0 };
    return v;
  }));
  return { condition_id: c0.id, xs, xs_display, y_key: yk.key, ys, ys_display, base_x, base_y, requests };
}

/** One grid cell from its full run, as the page: seriesStats of the equity (no benchmark) and tradeStats. */
export function cellStats(ledger: Pick<Ledger, 'equity' | 'trades'>): SensitivityCell {
  const s = seriesStats(ledger.equity), t = tradeStats(ledger.trades);
  return { sharpe: s.sharpe, cagr: s.cagr, profit_factor: profitFactor(t.pf), trades: t.n, max_drawdown: s.mdd };
}
