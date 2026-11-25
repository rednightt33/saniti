/* Robustness numbers of the backtest page (backtest.html sections 9 and 10): the Monte Carlo of reshuffled trade
   sequences, the Deflated Sharpe over the strategy line's trials (CONTRACT.md section 7, K3) and the sensitivity grid
   (the page's GRID_Y and xs/ys rules on the first enabled entry condition with a numeric threshold, D-grid; for a yes/no
   condition the first numeric setting of what it reads, EXEC-SENSITIVITY-FLAGS).
   Pure module: no DOM and no Node API. */
import type { BacktestRequest, Condition, MonteCarlo, Sensitivity, SensitivityCell } from './contract.ts';
import type { Ledger, LedgerTrade } from './ledger.ts';
import { displayScale, testThresholdPath, threshold, thresholdField, withThreshold } from './catalog.ts';
import { thresholdAccepted } from './conditions.ts';
import { BY_ID } from './registry.ts';
import { dsr, finiteOrNull, profitFactor, quant, seriesStats, tradeStats } from './stats.ts';
import type { SeriesStatsRaw } from './stats.ts';
import indDoc from '../../../terminal/src/data/indRegistry.json' with { type: 'json' };
import flowDoc from '../../../terminal/src/data/flowRegistry.json' with { type: 'json' };
import kindsDoc from '../../../screener/src/core/flow-kinds.json' with { type: 'json' };
import metricsDoc from '../../../screener/src/core/screener-metrics.json' with { type: 'json' };

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

/** Whether conditions.ts accepts a cell's condition: a price-action value must lie inside what it measures
    (conditions.ts PRICE_ACTION: dip > -1, volume ratio >= 0). The page's grid can step past it (volspike 1 → -1);
    such a cell is not run. The worker adds the grammar's own check of a test condition (run.ts gridAccepts). */
function accepted(c: Condition): boolean {
  return c.kind !== 'price_action' || c.value === undefined || thresholdAccepted(c.type, c.value);
}
/** The x axis's step and rounding: the page's for its own conditions; for a grammar condition (EXEC-BACKTEST-REVAMP P2)
    20 % of its base without the page's floor of 1 (a z-score of 0.5 steps by 0.1, an RSI of 30 by 6 as on the page),
    1 at a base of 0, and six significant digits (its unit is the metric's own, often below 1). */
const stepOf = (c: Condition, base: number) => c.kind === 'test' ? (Math.abs(base) * .2 || 1) : Math.max(1, Math.abs(base) * .2 || 1);
const roundX = (c: Condition, x: number) => c.kind === 'test' ? +x.toPrecision(6) : +x.toFixed(2);

/* ---- yes/no conditions (EXEC-SENSITIVITY-FLAGS, user choice C, 2026-11-24) ---------------------------------------
   A condition whose threshold compares an output whose values are codes (0/1, -1/1, categories) has its threshold only
   as a formality (0.5, 0): the grid's columns of it gave the same trades, and the Deflated Sharpe counted 25 trials
   where 5 differed. Such a condition's x axis is the first numeric setting of what it reads instead. Whether an output
   is coded is read from the registries, never from a list of ids:
   - an indicator output: the Terminal's registry draws it as a state or a marker (indRegistry.json outs[].r), not as a
     line, a histogram or dots with a value, or it lists categories (outs[].categories): Supertrend's and Parabolic
     SAR's `direction` (-1/1), the lab I54-I60 flags and states, Alpha KAMA's colour state;
   - a Flow output: its output kind in the Screener's flow-kinds.json is F, "0/1 signal" (FL09, FL27), the kind
     following a parameter where the file says so (`by`);
   - a transform that takes category arguments (screener-metrics.json transforms[].category_args: in_categories,
     category_change) gives 1 or 0 by its formula; its setting is the one of the indicator output it reads (`of`).
   Any other transform (a lag, an average, a rank) is read as a real number, as before. */
type IndOut = { k: string; r?: string; categories?: unknown[] };
const IND = new Map((indDoc as unknown as { id: string; outs: IndOut[]; params: { k: string; label?: string }[] }[]).map(r => [r.id, r]));
/** the Terminal's renderers of an output that is a code, not a value: an internal state and a marker on a session */
const CODE_RENDERS = ['state', 'marker'];
const coded = (o: IndOut | undefined) => !!o && (CODE_RENDERS.includes(o.r ?? '') || (Array.isArray(o.categories) && o.categories.length > 0));
interface FlowParam { key: string; label?: string; kind: string; default?: unknown; min?: unknown; max?: unknown; min_exclusive?: boolean; terminal_only?: boolean }
const FLOWS = new Map((flowDoc as unknown as { indicators: { id: string; outputs: string[]; params: FlowParam[] }[] }).indicators.map(f => [f.id, f]));
const KINDS = (kindsDoc as unknown as { indicators: Record<string, { outputs: Record<string, unknown> }> }).indicators;
/** flow-kinds.json `kinds`: F = "0/1 signal" */
const FLAG_KIND = 'F';
const CATEGORY_FNS = new Set((metricsDoc as unknown as { transforms: { fn: string; category_args?: unknown[] }[] }).transforms
  .filter(t => (t.category_args ?? []).length > 0).map(t => t.fn));
const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
/** An output's kind in flow-kinds.json: a letter, {kind, unit}, or {by: parameter, <option>: spec} read at the
    reference's parameter (the registry default when absent); null when the file does not say. */
function kindOf(spec: unknown, params: Record<string, unknown>, defaults: Record<string, unknown>, depth = 0): string | null {
  if (typeof spec === 'string') return spec;
  if (!isObj(spec) || depth > 4) return null;
  if (typeof spec.kind === 'string') return spec.kind;
  if (typeof spec.by !== 'string') return null;
  const v = spec.by in params ? params[spec.by] : defaults[spec.by];
  return typeof v === 'string' || typeof v === 'number' ? kindOf(spec[String(v)], params, defaults, depth + 1) : null;
}
const num = (x: unknown): number | undefined => typeof x === 'number' && Number.isFinite(x) ? x : undefined;

/** The numeric setting a grid varies: its key and label in its registry, whole or not, the condition's value (the
    registry default when the condition leaves it out) and its bounds. */
export interface GridSetting { key: string; label: string; integer: boolean; base: number; min?: number; max?: number; min_exclusive: boolean; step?: number }
/** An indicator's first numeric setting in its registry's Settings order (backtest-registry.json params, the accepted
    ones), at the condition's parameters; null when it has none (Inside Bar, Alpha Divergence). */
function indicatorSetting(id: unknown, params: unknown): GridSetting | null {
  const r = typeof id === 'string' ? BY_ID[id] : undefined, p = r?.params.find(x => x.type === 'integer' || x.type === 'number');
  if (!p) return null;
  const base = num(isObj(params) && p.key in params ? params[p.key] : p.default);
  if (base === undefined) return null;
  return { key: p.key, label: IND.get(r.id)?.params.find(x => x.k === p.key)?.label || p.key, integer: p.type === 'integer', base, min: p.min, max: p.max, min_exclusive: false, step: p.step };
}
/** A Flow indicator's first numeric setting in its registry's order (flowRegistry.json params of kind int or num, the
    Terminal's own drawing options aside), at the reference's parameters; null when it has none. */
function flowSetting(id: unknown, params: unknown): GridSetting | null {
  const e = typeof id === 'string' ? FLOWS.get(id) : undefined, p = e?.params.find(x => (x.kind === 'int' || x.kind === 'num') && !x.terminal_only);
  if (!p) return null;
  const base = num(isObj(params) && p.key in params ? params[p.key] : p.default);
  if (base === undefined) return null;
  return { key: p.key, label: p.label || p.key, integer: p.kind === 'int', base, min: num(p.min), max: num(p.max), min_exclusive: p.min_exclusive === true };
}
/** When a condition's threshold is compared with a coded output: the path of the reference whose setting varies (from
    the condition's root: [] for an indicator condition, whose parameters are its own `params`; 'test.lhs' and the like
    for a test) and that setting (null: coded, but nothing numeric to vary). Null when the threshold is compared with a
    real number (today's axis). */
export function codedSide(c: Condition): { path: string[]; setting: GridSetting | null } | null {
  if (c.kind === 'indicator') {
    if (c.rhs.type !== 'value' || c.lhs.type !== 'output') return null;
    const out = c.lhs.output;
    return coded(IND.get(c.indicator)?.outs.find(o => o.k === out)) ? { path: [], setting: indicatorSetting(c.indicator, c.params) } : null;
  }
  if (c.kind !== 'test') return null;
  const at = testThresholdPath(c.test);
  if (!at) return null;
  // the side the constant is compared with: a VALUE test's metric, a STATE's lhs, an EVENT signal's lhs, inside a window too
  const side = at.slice(0, -1);
  if (side[side.length - 1] === 'rhs') side[side.length - 1] = 'lhs'; else side.push('metric');
  const path = ['test', ...side];
  let ref = path.reduce<unknown>((v, k) => isObj(v) ? v[k] : undefined, c);
  if (isObj(ref) && ref.kind === 'transform') {
    if (!CATEGORY_FNS.has(String(ref.fn)) || !isObj(ref.of) || ref.of.kind !== 'indicator') return null;
    path.push('of');
    return { path, setting: indicatorSetting(ref.of.indicator, ref.of.params) };
  }
  if (!isObj(ref)) return null;
  if (ref.kind === 'indicator') {
    const out = ref.output;
    return coded(IND.get(String(ref.indicator))?.outs.find(o => o.k === out)) ? { path, setting: indicatorSetting(ref.indicator, ref.params) } : null;
  }
  if (ref.kind === 'flow') {
    const e = FLOWS.get(String(ref.metric)), outs = KINDS[String(ref.metric)]?.outputs;
    if (!e || !outs) return null;
    const out = typeof ref.output === 'string' ? ref.output : e.outputs[0], params = isObj(ref.params) ? ref.params : {};
    const defaults = Object.fromEntries(e.params.map(p => [p.key, p.default]));
    return kindOf(outs[out], params, defaults) === FLAG_KIND ? { path, setting: flowSetting(ref.metric, ref.params) } : null;
  }
  return null;
}
/** A setting's grid values: 20 % of its base per step (at least 1 for a whole number, so a small one such as Top N 3
    steps 1, 2, 3, 4, 5 instead of repeating after rounding), k = -2..2, rounded to a whole number where the setting is
    one (six significant digits otherwise; at a base of 0 its registry step, else 1), kept inside its min and max.
    Supertrend ATR length 10: 6, 8, 10, 12, 14; Alpha Price Action BUY lookback 30: 18, 24, 30, 36, 42. */
export function settingAxis(s: GridSetting): number[] {
  const step = s.integer ? Math.max(1, Math.abs(s.base) * .2) : (Math.abs(s.base) * .2 || s.step || 1);
  return KS.map(k => {
    let x = s.base + k * step;
    x = s.integer ? Math.round(x) : +x.toPrecision(6);
    if (s.min !== undefined && !s.min_exclusive) x = Math.max(s.min, x);
    if (s.max !== undefined) x = Math.min(s.max, x);
    return x === 0 ? 0 : x;                              // never -0 (JSON has none)
  });
}
/** The condition with the setting of the reference at `path` set to `value`; the condition itself at its own value,
    so the cell of the run's own settings is the run (one variant, whichever hash form reads it). */
function withSetting<T extends Condition>(c: T, path: readonly string[], s: GridSetting, value: number): T {
  if (value === s.base) return c;
  const v = JSON.parse(JSON.stringify(c)) as Record<string, unknown>;
  const ref = path.reduce<Record<string, unknown>>((o, k) => o[k] as Record<string, unknown>, v);
  ref.params = { ...(isObj(ref.params) ? ref.params : {}), [s.key]: value };
  return v as T;
}

export interface SensitivityPlan {
  condition_id: string;
  /** what x varies: the condition's threshold ('value'); a yes/no condition's first numeric setting ('setting'); nothing
      ('none': a yes/no condition without one and no later condition with an axis: one column, the stop setting only) */
  x_param: Sensitivity['x_param']; x_field: string; x_label: string | null;
  xs: number[]; xs_display: number[]; y_key: YKey; ys: number[]; ys_display: number[];
  base_x: number; base_y: number;
  /** The variant requests, [y][x] (5 × 5; 5 × 1 for 'none'); null where conditions.ts, or the caller's `accepts`,
      refuses the cell's condition, or a setting at its exclusive minimum. Each has sensitivity and Monte Carlo off: a
      cell is one backtest, as on the page. */
  requests: (BacktestRequest | null)[][];
}

interface XAxis {
  c: Condition; x_param: Sensitivity['x_param']; x_field: string; x_label: string | null; xs: number[]; xs_display: number[]; base_x: number;
  /** the condition of the column at x (wire units), null when that value is refused */
  at: (x: number) => Condition | null;
}
/** The grid's x axis: the first enabled entry condition with a numeric threshold, in the entry's order (D-grid). When
    its threshold is compared with a coded output (codedSide): the first numeric setting of what it reads (x 'setting',
    user choice C); when that has none, the next such condition (way A); a yes/no condition and no axis after it: x
    'none' on that condition (the stop axis only). Null when no enabled entry condition has a numeric threshold. */
function xAxis(q: BacktestRequest): XAxis | null {
  let first: Condition | null = null;
  for (const c of q.entry.conditions) {
    if (c.enabled === false || threshold(c) === null) continue;
    const side = codedSide(c);
    if (!side) {
      const scale = displayScale(c) as number, base_x = threshold(c) as number, base = base_x / scale, step = stepOf(c, base);
      const xs_display = KS.map(k => roundX(c, base + k * step));
      return { c, x_param: 'value', x_field: thresholdField(c) as string, x_label: null, xs: xs_display.map(x => x * scale), xs_display, base_x, at: x => withThreshold(c, x) };
    }
    if (side.setting) {
      const s = side.setting, xs = settingAxis(s);
      return { c, x_param: 'setting', x_field: [...side.path, 'params', s.key].join('.'), x_label: s.label, xs, xs_display: xs, base_x: s.base,
        at: x => s.min_exclusive && s.min !== undefined && x <= s.min ? null : withSetting(c, side.path, s, x) };
    }
    first ??= c;
  }
  if (!first) return null;
  const c = first, base_x = threshold(c) as number;
  return { c, x_param: 'none', x_field: thresholdField(c) as string, x_label: null, xs: [base_x], xs_display: [base_x / (displayScale(c) as number)], base_x, at: () => c };
}

/** The page's grid on the request: x = the first enabled entry condition with a numeric threshold, base in display
    units (catalog.ts DISPLAY; wire ÷ scale), step = max(1, |base| × 0.2 || 1), xs = +(base + k·step).toFixed(2);
    y = the stop setting (pct: step 2 %, min 1 %; atr: 0.5 / 0.5; rr: 0.5 / 0.5; line or none: max hold, step 5,
    min 2), ys = +max(min, y0 + k·step).toFixed(2); k = -2..2. Wire values: x display × scale (catalog.ts), y as
    GRID_Y.toWire. A yes/no condition varies its first numeric setting instead (xAxis, settingAxis; display = wire).
    Null when sensitivity is off or no enabled entry condition has a numeric threshold.
    Recovering the display base from the wire (e.g. -0.03 / 0.01 = -2.9999999999999996) can differ from the typed
    value by an ulp; after the page's 2-decimal rounding the axes are the page's for every base of at most 2 decimals
    (the grid values are then multiples of 0.002, far from a rounding boundary). */
export function sensitivityPlan(q: BacktestRequest, accepts: (c: Condition) => boolean = accepted): SensitivityPlan | null {
  if (!q.robustness.sensitivity) return null;
  const ax = xAxis(q);
  if (!ax) return null;
  const yk = gridY(q), y0 = yk.get(q);
  const ys_display = KS.map(k => +Math.max(yk.min, y0 + k * yk.step).toFixed(2)), ys = ys_display.map(yk.toWire);
  const base_y = yk.key === 'stop_pct' ? q.exit.stop.pct : y0;
  // each column's condition once (the grammar's check of a test condition is not free), then the rows
  const cols = ax.xs.map(x => { const c = ax.at(x); return c && accepted(c) && accepts(c) ? c : null });
  const requests = ys.map(y => cols.map(cell => {
    if (!cell) return null;
    const v = JSON.parse(JSON.stringify(q)) as BacktestRequest;
    v.entry.conditions = v.entry.conditions.map(c => c.id === ax.c.id ? JSON.parse(JSON.stringify(cell)) as Condition : c);
    yk.set(v, y);
    v.robustness = { ...v.robustness, sensitivity: false, monte_carlo_runs: 0 };
    return v;
  }));
  return { condition_id: ax.c.id, x_param: ax.x_param, x_field: ax.x_field, x_label: ax.x_label, xs: ax.xs, xs_display: ax.xs_display, y_key: yk.key, ys, ys_display,
    base_x: ax.base_x, base_y, requests };
}

/** One grid cell from its full run, as the page: seriesStats of the equity (no benchmark) and tradeStats. */
export function cellStats(ledger: Pick<Ledger, 'equity' | 'trades'>): SensitivityCell {
  const s = seriesStats(ledger.equity), t = tradeStats(ledger.trades);
  return { sharpe: s.sharpe, cagr: s.cagr, profit_factor: profitFactor(t.pf), trades: t.n, max_drawdown: s.mdd };
}
