/* FIXTURE ONLY: the worker's computation on the prototype's synthetic market (data.ts) and its broker rows (broker.ts),
   so the page can be seen and smoke-tested without the worker and meets what production computes (QA5 unit B item 4,
   the 20-question test B). Every number, cell and refusal is the screener core's own, called as the worker calls it
   (apps/screener-worker/src/run.ts normalize and runTask, preview.ts runPreview):
   - validate.ts validateDefinition: the worker's normalize, so its refusals (parameters, K1 broker depth, a flow
     indicator while the broker data loads, METRIC_UNAVAILABLE) are the fixture's too;
   - screen.ts runScreen: the universe (S0), the rank of operator 11 over the S0 survivors (the user's filtered
     universe, decision C), every pattern, transform, cross-section and flow indicator, the pruning of a non-exhaustive
     run;
   - screen.ts previewCells and condition.ts conditionSignal: a preview's cells, status, overlays and markers.
   The fixture adds the envelope (versions, data, timings) and the ScreenEnv over its own bars: one series cache and one
   Calc per ticker for every fixture market (all are built from the same seeded data; a hostile market differs in its
   names only). It is not the worker (no queue, budget, cost model or result cache) and is never part of the production
   bundle (tests/bundle). */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import type { Cell, ConditionDef, Definition, EventTest, Grouping, PreviewResponse, RowRemark, RunOptions, RunResponse, UniverseRow, Versions } from '../../src/core/contract.ts';
import { PERF_PERIODS, PREVIEW_BARS, UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { conditionSignal } from '../../src/core/condition.ts';
import { SeriesCache, series, tailLength, tickerCalc } from '../../src/core/metrics.ts';
import type { ResolvedIndicator, ResolvedSeries, TickerBars, TickerCalc } from '../../src/core/metrics.ts';
import { previewCells, runScreen } from '../../src/core/screen.ts';
import type { ScreenEnv } from '../../src/core/screen.ts';
import { availabilityMap, validateDefinition } from '../../src/core/validate.ts';
import type { ValidateContext } from '../../src/core/validate.ts';
import type { FlowBindContext } from '../../src/core/flowmetrics.ts';
import { tickerFlow } from './broker.ts';
import type { StockListsBlock } from '../../src/core/contract.ts';
import { stockListsOf } from '../../../../screener-worker/src/stocklists.ts';
import type { StockListsRef } from '../../../../screener-worker/src/stocklists.ts';

export interface Tk {
  ticker: string; name: string; sector: string | null; industry: string | null;
  d: string[]; o: number[]; h: number[]; l: number[]; c: number[]; v: number[];
  remarks: RowRemark[]; breakAt: number | null;
}
export interface Market { tickers: Tk[]; byTicker: Map<string, Tk>; days: string[]; ihsg: number[]; evalDate: string }
/** What the fixture's publication holds besides the bars: its broker window (complete, or still loading), the
    groupings the validation checks sector and industry names against and (EXEC-SCREENER-STOCK-LISTS) the stock-lists
    file as the worker's refresh reads it (absent: as a publication without it); stockListsBlock gives its catalog block. */
export interface FixtureData { flow: FlowBindContext; groupings: readonly Grouping[]; lists?: StockListsRef }
/** The universe rows of a market with the indices and groups of `fx.lists` (the worker's stocklists.ts stockListsOf,
    as its snapshot build runs it), and the catalog block it gives. */
export function universeRows(m: Market, fx: FixtureData): { rows: UniverseRow[]; block: StockListsBlock } {
  const rows = m.tickers.map(t => universeRow(m, t));
  return { rows, block: stockListsOf(fx.lists, rows) };
}

/** the worker's limits the fixture's catalog states (tests/fixture/api.ts LIMITS) and its cap budget (the core tests') */
export const LIMITS = { max_conditions: 20, max_metric_filters: 8, within_max: 130 };
export const CAP_BUDGET_MS = 2000;

const isN = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const sma = (a: number[], n: number): (number | null)[] => a.map((_, i) => { if (i < n - 1) return null; let s = 0; for (let j = i - n + 1; j <= i; j++) s += a[j]; return s / n });

/* ---- the series path: the worker's (metrics.ts series over a SeriesCache and a Calc per ticker) -------------------- */
const SCTX = { versions:{ price_data:'f'.repeat(64), screener_engine:'e'.repeat(16) }, tailLength:tailLength(LIMITS.within_max), cache:new SeriesCache(1 << 30) };
const BARS = new Map<string, TickerBars>(), CALCS = new Map<string, TickerCalc>();
function barsOf(t: Tk): TickerBars {
  let b = BARS.get(t.ticker);
  if (!b) { b = { ticker:t.ticker, dates:t.d, bars:{ O:t.o, H:t.h, L:t.l, C:t.c, V:t.v, T:t.d }, flow:tickerFlow(t.ticker, t.d) }; BARS.set(t.ticker, b) }
  return b;
}
function calcOf(b: TickerBars): TickerCalc {
  let c = CALCS.get(b.ticker);
  if (!c) { c = tickerCalc(b); CALCS.set(b.ticker, c) }
  return c;
}
/** IHSG as the index series (vs_index, market_sessions_ago): the fixture's index level, no volume */
const indexOf = (m: Market): TickerBars => {
  const ih = m.ihsg.map(x => x * 7000);
  return { ticker:'IHSG', dates:m.days, bars:{ O:ih, H:ih, L:ih, C:ih, V:ih.map(() => null), T:m.days } as unknown as Bars };
};
/** The ScreenEnv of a market (screen.ts): its universe rows, its bars and the worker's series path. */
const ENVS = new WeakMap<Market, ScreenEnv>();
function envOf(m: Market, fx: FixtureData): ScreenEnv {
  let env = ENVS.get(m);
  if (!env) {
    const index = indexOf(m);
    env = { capBudgetMs:CAP_BUDGET_MS, withinMax:LIMITS.within_max, index, catalog:METRICS_CATALOG, flow:fx.flow,
      evaluationDate:m.evalDate, rows:universeRows(m, fx).rows, ihsgCalendar:index.dates,
      bars:tk => { const t = m.byTicker.get(tk); return t ? barsOf(t) : undefined },
      series:(r, t) => series(SCTX, calcOf(t), r), isPrewarmed:() => false };
    ENVS.set(m, env);
  }
  return env;
}

/* ---- the worker's calls ---------------------------------------------------------------------------------------- */

/** The groupings of a market (GET catalog groupings): sector and industry values with their counts. */
export function groupingsOf(m: Market): Grouping[] {
  const one = (key: 'sector' | 'industry') => {
    const n = new Map<string, number>(); let un = 0;
    for (const t of m.tickers) { const v = t[key]; if (v == null) un++; else n.set(v, (n.get(v) || 0) + 1) }
    return { key, values:[...n].sort((a, b) => a[0].localeCompare(b[0])).map(([value, tickers]) => ({ value, tickers })), unclassified:un };
  };
  return [one('sector'), one('industry')];
}
/** The worker's validation context on the fixture's publication (apps/screener-worker/src/server.ts vctx). */
export function validateContext(m: Market, fx: FixtureData): ValidateContext {
  return { limits:LIMITS, capBudgetMs:CAP_BUDGET_MS, tickers:new Set(m.tickers.map(t => t.ticker)), groupings:fx.groupings,
    metrics:METRICS_CATALOG, availability:availabilityMap({}, METRICS_CATALOG, undefined, fx.flow), flow:fx.flow, stockLists:stockListsBlock(m, fx) };
}
/** The catalog's stock_lists block of the fixture's publication (computed once per market and file). */
const BLOCKS = new WeakMap<Market, { lists: StockListsRef | undefined; block: StockListsBlock }>();
export function stockListsBlock(m: Market, fx: FixtureData): StockListsBlock {
  const b = BLOCKS.get(m);
  if (b && b.lists === fx.lists) return b.block;
  const block = universeRows(m, fx).block;
  BLOCKS.set(m, { lists: fx.lists, block });
  return block;
}
/** The worker's normalize: the definition with every default resolved, or the core's ScreenerError (its refusal). */
export const normalize = (m: Market, fx: FixtureData, def: unknown): Definition => validateDefinition(def, validateContext(m, fx));

/** The universe row of a stock (GET universe): last close, 1-day change, ADV20 (SMA20 of close x volume, the core's
    liquidity), first and last bar, the stale flag and the remarks. */
export function universeRow(m: Market, t: Tk): UniverseRow {
  const i = t.c.length - 1, adv = sma(t.c.map((c, j) => c * t.v[j]), 20)[i];
  return { ticker:t.ticker, name:t.name, sector:t.sector, industry:t.industry, last:t.c[i], chg_1d_pct:(t.c[i] / t.c[i - 1] - 1) * 100, adv20_idr:adv,
    first_bar:t.d[0], last_bar:t.d[i], bars:t.c.length, stale:t.d[i] < m.evalDate, remarks:t.remarks };
}

/** POST run on a normalized definition: screen.ts runScreen, the answer in the contract's envelope. */
export function run(m: Market, fx: FixtureData, def: Definition, versions: Versions, data: RunResponse['data'], options: RunOptions = {}): RunResponse {
  const t0 = performance.now(), r = runScreen(def, envOf(m, fx), { exhaustive:!!options.exhaustive, explain:!!options.explain });
  return { schema_version:1, versions, data, mode:r.mode, universe:r.universe, conditions:r.conditions, need:r.need, match_count:r.match_count, near_count:r.near_count,
    rows:r.rows, warnings:r.warnings, timings_ms:{ queue:0, ...r.timings, total:performance.now() - t0 }, ...(r.plan ? { plan:r.plan } : {}) };
}

/** One condition's cell on one stock (screen.ts previewCells over a one-condition definition). */
export function cellOf(m: Market, fx: FixtureData, ticker: string, cd: ConditionDef): Cell {
  const def = normalize(m, fx, { universe:{ ...UNIVERSE_DEFAULTS }, conditions:[cd], logic:'all' });
  return previewCells(def, envOf(m, fx), ticker).cells[0];
}

/** The overlay name of a series (the worker's preview.ts overlayName): its label, with the parameters when they are not
    the registry defaults. */
const overlayName = (r: ResolvedSeries) => {
  const ind = r.kind === 'indicator' ? r as ResolvedIndicator : null;
  return ind && !ind.isDefault ? `${r.label}(${Object.entries(ind.params).map(([k, v]) => `${k}=${v}`).join(',')})` : r.label;
};
const cut = (xs: ArrayLike<number | null | undefined>, from: number, to: number) => { const out: (number | null)[] = []; for (let i = from; i < to; i++) { const v = xs[i]; out.push(isN(v) ? v : null) } return out };
/** POST preview on a normalized definition, as the worker's preview.ts builds it: the core's cells, status and
    remarks (screen.ts previewCells, even outside the universe), the last PREVIEW_BARS bars, IHSG on the same dates, an
    overlay per series a condition reads that is not a bar field or a pattern signal, markers where an EVENT condition's
    signal fires (condition.ts conditionSignal), and the returns over the catalog's periods. */
export function preview(m: Market, fx: FixtureData, def: Definition, ticker: string, versions: Versions, data: PreviewResponse['data'], periods: Record<string, number>): PreviewResponse {
  const t = m.byTicker.get(ticker), env = envOf(m, fx);
  const p = previewCells(def, env, ticker);
  const b = barsOf(t!), tc = calcOf(b), n = t!.d.length, from = Math.max(0, n - PREVIEW_BARS);
  const full = (r: ResolvedSeries) => r.full(tc);
  const overlays: PreviewResponse['overlays'] = [], markers: PreviewResponse['markers'] = [];
  for (const bc of p.bound) {
    for (const r of bc.series) if (r.kind !== 'price' && r.kind !== 'pattern') overlays.push({ condition_id:bc.id, output:overlayName(r), unit:r.unit ?? null, values:cut(full(r), from, n) });
    if (bc.kind !== 'event') continue;
    const sig = conditionSignal(bc, full, n); if (!sig) continue;
    const signal = (bc.test as EventTest).signal, kind = 'pattern' in signal ? signal.pattern.type : signal.op, fired: { date: string; kind: string }[] = [];
    for (let i = Math.max(1, from); i < n; i++) if (sig[i] === 1) fired.push({ date:t!.d[i], kind });
    markers.push({ condition_id:bc.id, bars:fired });
  }
  // IHSG on the stock's own dates (a stale stock's last bar is earlier than the index's)
  const off = m.days.indexOf(t!.d[0]), ihsg = m.ihsg.slice(off, off + n).map(x => x * 7000);
  const ret = (s: number[], k: number) => n - 1 - k >= 0 ? (s[n - 1] / s[n - 1 - k] - 1) * 100 : null;
  const perf = Object.fromEntries(PERF_PERIODS.map(k => { const len = periods[k]; return [k, isN(len) ? { stock_pct:ret(t!.c, len), ihsg_pct:ret(ihsg, len) } : { stock_pct:null, ihsg_pct:null }] })) as PreviewResponse['perf'];
  return { versions, data, ticker, status:p.status, remarks:p.remarks, met:p.met, need:p.need, cells:p.cells,
    bars:{ d:t!.d.slice(from), o:cut(t!.o, from, n), h:cut(t!.h, from, n), l:cut(t!.l, from, n), c:cut(t!.c, from, n), v:cut(t!.v, from, n) },
    ihsg_close:ihsg.slice(from), overlays, markers, perf };
}
