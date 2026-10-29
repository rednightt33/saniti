/* One screen over the snapshot, stages S0-S4 (EXEC-SCREENER; report TARGET ARCHITECTURE 6.10 planner, 6.9 match and
   near, 6.12 remarks; API CONTRACT 8.5 the run answer without versions, data and timings, which the worker adds).
   runScreen takes a definition normalized by validate.ts and the worker's snapshot through ScreenEnv:
     S0 universe.ts applyUniverse on every listed stock (the page's own function), then the metric filters that need a
        formula, each a VALUE test bound like a condition (a filter that does not pass, or is NA, drops the ticker);
     S1 cross-sectional values on the fixed population (xsection.ts returnRankAll), once per distinct reference;
     S2 conditions whose every series is pinned in the snapshot (pre-warmed) and universe attributes: every S0 survivor;
     S3 the other conditions, cheapest predicted first, with the pruning rule of plan.ts;
     S4 completion of every surviving row.
   The worst case is costed before any compute (plan.ts costEstimate); above env.maxCpuMs the request is refused with
   LIMIT_EXCEEDED {limit: 'compute_budget', allowed, needed, costliest}. Rows are the matches and near rows, ordered as
   the page's default sort (match first, then met, then ADV20 descending, then ticker); counts, summaries and warnings
   as report 8.5. Nothing user-specific enters: the answer depends on the definition and the snapshot only (P29, 6d.2).
   Worker-side module. */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import type {
  Cell, ConditionSummary, Definition, PlanExplain, ResultRow, RowRemark, UniverseCounts, UniverseRow, Warning,
} from './contract.ts';
import { ScreenerError } from './errors.ts';
import { bindCondition, bindTest } from './condition.ts';
import type { BindContext, BoundCondition, TickerInput, XsectionNeed } from './condition.ts';
import { evaluationBar } from './evaluate.ts';
import { countCells, needOf, previewStatus } from './match.ts';
import type { ResolvedSeries, SeriesSource, Tail, TickerBars } from './metrics.ts';
import { costEstimate, runPlan } from './plan.ts';
import type { PlanCondition } from './plan.ts';
import { applyUniverse } from './universe.ts';
import { returnRankAll } from './xsection.ts';

/** The snapshot as runScreen reads it (the worker builds it once per publication). */
export interface ScreenEnv extends BindContext {
  evaluationDate: string;
  /** every listed stock's universe row (GET /universe rows: hidden ones included, with their remarks) */
  rows: readonly UniverseRow[];
  /** a listed stock's bars and dates (its own sessions), none after evaluationDate: every series is a tail at the
      ticker's last bar, so its evaluation bar must be that bar (the worker refuses a publication whose price file holds
      a bar after its price_through, snapshot.ts) */
  bars(ticker: string): TickerBars | undefined;
  /** IHSG's calendar (market_sessions_ago) */
  ihsgCalendar: readonly string[];
  /** the one series path for one ticker (metrics.ts series over the worker's cache and a per-ticker Calc) */
  series(r: ResolvedSeries, t: TickerBars): { tail: Tail; source: SeriesSource };
  /** whether a series is pinned in the snapshot (pre-warmed): its condition is stage S2, else S3 */
  isPrewarmed(r: ResolvedSeries): boolean;
  /** predicted ms of computing one series on one ticker (plan.ts CostTracker.predict); 0 when absent */
  predictMs?(r: ResolvedSeries, bars: number): number;
  /** SCREENER_MAX_CPU_MS: a definition costed above it is refused before any compute */
  maxCpuMs?: number;
  /** a precomputed cross-section (the snapshot's default ranks), or undefined to compute it here */
  xsectionValues?(need: XsectionNeed): ReadonlyMap<string, number | null> | undefined;
  cacheHits?(): number;
  cancelled?(): boolean;
}
export interface ScreenOptions { exhaustive?: boolean; explain?: boolean }
export interface ScreenResult {
  mode: 'screen' | 'universe_only';
  universe: UniverseCounts;
  conditions: ConditionSummary[];
  need: number; match_count: number; near_count: number;
  rows: ResultRow[];
  warnings: Warning[];
  plan?: PlanExplain;
  /** ms per stage (the worker adds queue and total) */
  timings: { s0: number; s1: number; s2: number; s3: number; s4: number };
}

const now = (): number => (globalThis.performance ? globalThis.performance.now() : Date.now());
const byTicker = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

/** The per-ticker reader a bound condition evaluates on (condition.ts TickerInput). */
function inputOf(env: ScreenEnv, row: UniverseRow, t: TickerBars, xs: Map<string, ReadonlyMap<string, number | null>>): TickerInput {
  const input: TickerInput = {
    ticker: row.ticker, dates: t.dates, bars: t.bars as Bars, at: evaluationBar(t.dates, env.evaluationDate), row, ihsgCalendar: env.ihsgCalendar,
    series: r => env.series(r, t),
    xsection: key => xs.get(key)?.get(row.ticker) ?? null,
  };
  // the snapshot's answer of missingInput (no bar column read for a lookup), when the worker gives one
  if (t.missing) input.missing = (inputs, at) => t.missing!(inputs, at);
  return input;
}
/** Every cross-section the bound conditions read, over all listed stocks (population fixed at E, xsection.ts). */
function crossSections(env: ScreenEnv, bound: readonly BoundCondition[]): Map<string, ReadonlyMap<string, number | null>> {
  const out = new Map<string, ReadonlyMap<string, number | null>>();
  for (const b of bound) {
    const x = b.xsection;
    if (!x || out.has(x.key)) continue;
    const pre = env.xsectionValues?.(x);
    if (pre) { out.set(x.key, pre); continue }
    if (x.metric !== 'return_rank') throw new RangeError(`screen: no computation for the cross-section ${x.metric}`);
    const closes = new Map<string, { at: number; close: ArrayLike<number | null | undefined> }>();
    for (const r of env.rows) { const t = env.bars(r.ticker); if (t) closes.set(r.ticker, { at: evaluationBar(t.dates, env.evaluationDate), close: t.bars.C }) }
    out.set(x.key, returnRankAll(env.rows, closes, x.window, env.evaluationDate).ranks);
  }
  return out;
}

/** The S0 survivors: applyUniverse, then the metric filters that need a formula (bound VALUE tests). */
function stageS0(def: Definition, env: ScreenEnv): { eligible: UniverseRow[]; counts: UniverseCounts } {
  const u = applyUniverse(env.rows, def.universe);
  if (!u.pending.length) return { eligible: u.eligible, counts: u.counts };
  const filters = u.pending.map(i => bindTest(`f${i}`, def.universe.metric_filters![i], `definition.universe.metric_filters[${i}]`, env));
  const xs = crossSections(env, filters);
  const eligible = u.eligible.filter(row => {
    const t = env.bars(row.ticker);
    if (!t) return false;
    const input = inputOf(env, row, t, xs);
    return filters.every(f => f.evaluate(input).cell.status === 'pass');      // NA fails a filter, as a null attribute does
  });
  const dropped = u.eligible.length - eligible.length;
  return { eligible, counts: { ...u.counts, eligible: eligible.length, filtered_out: u.counts.filtered_out + dropped } };
}

/** Runs one normalized definition over the snapshot (stages above). */
export function runScreen(def: Definition, env: ScreenEnv, options: ScreenOptions = {}): ScreenResult {
  const t0 = now();
  const s0 = stageS0(def, env), ts0 = now();
  const active = def.conditions.filter(c => c.enabled);
  const bound = active.map(c => bindCondition(c, `definition.conditions[${def.conditions.indexOf(c)}]`, env));
  const xs = crossSections(env, bound), ts1 = now();
  const survivors = s0.eligible.flatMap(row => { const t = env.bars(row.ticker); return t ? [{ row, t }] : [] });
  const avgBars = survivors.length ? survivors.reduce((n, s) => n + s.t.dates.length, 0) / survivors.length : 0;
  const sources = new Map<string, { precomputed: number; dynamic: number }>();
  const inputs = new Map(survivors.map(s => [s.row.ticker, inputOf(env, s.row, s.t, xs)]));
  const planConds: PlanCondition[] = bound.map(b => {
    const pinned = (r: ResolvedSeries) => r.kind === 'price' || env.isPrewarmed(r);    // a bar field is the snapshot itself
    const stage = b.xsection ? 'S1' : b.universeAttr !== null || b.series.every(pinned) ? 'S2' : 'S3';
    const predictedMs = stage === 'S3' ? b.series.filter(r => !pinned(r)).reduce((ms, r) => ms + (env.predictMs?.(r, avgBars) ?? 0), 0) : 0;
    const tally = { precomputed: 0, dynamic: 0 };
    sources.set(b.id, tally);
    return {
      id: b.id, stage, predictedMs,
      evaluate: (ticker: string): Cell => { const r = b.evaluate(inputs.get(ticker)!); tally[r.source]++; return r.cell },
    };
  });
  if (env.maxCpuMs !== undefined) {
    const est = costEstimate(planConds, survivors.length);
    if (est.needed_ms > env.maxCpuMs)
      throw new ScreenerError('LIMIT_EXCEEDED', `This screen is costed at ${Math.ceil(est.needed_ms)} ms of compute, above the ${env.maxCpuMs} ms budget; use default parameters, shorter lengths or a narrower universe${est.costliest ? ` (the costliest is condition ${est.costliest})` : ''}.`,
        'definition.conditions', { limit: 'compute_budget', allowed: env.maxCpuMs, needed: Math.ceil(est.needed_ms), ...(est.costliest ? { costliest: est.costliest } : {}) });
  }
  const plan = runPlan({ tickers: survivors.map(s => s.row.ticker), conditions: planConds, logic: def.logic, atLeast: def.at_least, exhaustive: !!options.exhaustive, cancelled: env.cancelled, cacheHits: env.cacheHits });
  const byRow = new Map(survivors.map(s => [s.row.ticker, s.row]));
  const rows: ResultRow[] = plan.rows.map(p => {
    const r = byRow.get(p.ticker)!;
    return {
      ticker: r.ticker, name: r.name, sector: r.sector, industry: r.industry, board: null, market_cap: null,
      last: r.last, chg_1d_pct: r.chg_1d_pct, adv20_idr: r.adv20_idr, last_bar_date: r.last_bar, stale: r.stale, remarks: r.remarks,
      status: p.status, met: p.met, need: p.need, na_count: p.na_count, cells: p.cells,
    };
  });
  rows.sort((a, b) => (a.status === b.status ? 0 : a.status === 'match' ? -1 : 1) || b.met - a.met || (b.adv20_idr ?? -Infinity) - (a.adv20_idr ?? -Infinity) || byTicker(a.ticker, b.ticker));
  const conditions: ConditionSummary[] = bound.map(b => {
    const s = plan.summaries[b.id], pc = planConds.find(c => c.id === b.id)!, tally = sources.get(b.id)!;
    return {
      id: b.id, source: pc.stage === 'S1' ? 'xsection' : tally.dynamic > 0 ? 'dynamic' : 'precomputed', metric: b.summary.metric,
      params_resolved: b.summary.params_resolved, is_default: b.summary.is_default, kind: b.kind, unit: b.summary.unit,
      evaluated: s.evaluated, passed: s.passed, na: s.na, exhaustive: s.exhaustive, eval_date_basis: 'ticker_last_bar',
    };
  });
  const warnings: Warning[] = [];
  if (def.logic === 'any' && active.length >= 2 && !options.exhaustive)
    warnings.push({ code: 'NO_PRUNING_FOR_ANY', message: 'With "any" logic no ticker can be ruled out early: every condition is evaluated on every ticker in the universe.' });
  const brokenRows = rows.filter(r => r.remarks.some(x => x.code === 'PRICE_BREAK'));
  if (brokenRows.length) {
    const cells = brokenRows.reduce((n, r) => n + r.cells.filter(c => c.remark === 'PRICE_BREAK_IN_LOOKBACK').length, 0);
    warnings.push({ code: 'PRICE_BREAKS_IN_RESULT', message: 'Some rows have an unadjusted price break; their values are shown and the affected cells are marked.', count: brokenRows.length, details: { rows: brokenRows.length, cells } });
  }
  const st = (n: string) => plan.explain.stages.find(x => x.name === n)?.ms ?? 0;
  const result: ScreenResult = {
    mode: active.length ? 'screen' : 'universe_only', universe: s0.counts, conditions, need: plan.need,
    match_count: rows.filter(r => r.status === 'match').length, near_count: rows.filter(r => r.status === 'near').length,
    rows, warnings,
    timings: { s0: ts0 - t0, s1: ts1 - ts0 + st('S1'), s2: st('S2'), s3: st('S3'), s4: st('S4') },
  };
  if (options.explain) result.plan = {
    stages: [{ name: 'S0', in: s0.counts.listed, out: s0.counts.eligible, ms: ts0 - t0 }, ...plan.explain.stages],
    order: plan.explain.order, pruned: plan.explain.pruned, cache_hits: plan.explain.cache_hits, exhaustive: plan.explain.exhaustive,
    ...(plan.explain.note ? { note: plan.explain.note } : {}),
  };
  return result;
}

/** One ticker's cells, met, need and status under a definition (report 8.6 preview): every active condition evaluated
    (even outside the universe), the status by the one near rule (match.ts previewStatus), the row remarks. Bars,
    overlays, markers and perf are the worker's (condition.ts conditionSignal gives the markers). */
export function previewCells(def: Definition, env: ScreenEnv, ticker: string): { status: ReturnType<typeof previewStatus>; remarks: RowRemark[]; met: number; need: number; cells: Cell[]; bound: BoundCondition[] } {
  const row = env.rows.find(r => r.ticker === ticker), t = env.bars(ticker);
  if (!row || !t) throw new ScreenerError('INVALID_CONDITION', `ticker ${ticker} is not a listed stock of this publication.`, 'ticker');
  const inUniverse = stageS0({ ...def, universe: { ...def.universe, tickers: [ticker] } }, env).eligible.length === 1 && (!def.universe.tickers || def.universe.tickers.includes(ticker));
  const active = def.conditions.filter(c => c.enabled);
  const bound = active.map(c => bindCondition(c, `definition.conditions[${def.conditions.indexOf(c)}]`, env));
  const input = inputOf(env, row, t, crossSections(env, bound));
  const cells = bound.map(b => b.evaluate(input).cell);
  const { met } = countCells(cells), need = needOf(def.logic, def.at_least, active.length);
  return { status: previewStatus(inUniverse, met, need), remarks: row.remarks, met, need, cells, bound };
}
