/* One condition bound to its series, evaluated on one ticker (EXEC-SCREENER; report TARGET ARCHITECTURE 6.9 condition
   engine, 6.10 stages, 6.12 remarks; API CONTRACT 8.5 cells and conditions[]). bindCondition resolves a validated
   condition once per request (every reference through metrics.ts, transforms.ts and the registry), and its evaluate()
   reads the ticker's tails through the caller's one series() path (report 6.7: precomputed and dynamic are the same
   call), applies evaluate.ts at the ticker's evaluation bar and returns the wire cell with its NA reason and its
   PRICE_BREAK_IN_LOOKBACK remark. The rules it adds to evaluate.ts, exactly:
   - a bar-field side compared with a series whose compareLag is 1 for that direction (report 6.8 lag probe: Donchian's
     prior band; rolling_max(high, n)) reads the lagged series transform lag(x, 1), resolved like any transform and
     cached under its own key, never a shifted view of the tail (evaluate.ts header). The direction is the bar field's:
     price gt / crosses_above x reads compareLag.gt, lt / crosses_below reads compareLag.lt;
   - a side the ticker lacks an input for (metrics.ts missingInput: IHSG volume) is a view with inputMissing set, so
     its NA is NULL_AT_EVALUATION (TEST PLAN 10b.3);
   - the remark: on a row with PRICE_BREAK remarks, the cell is marked when the lookback of any side it read contains an
     ex-date (evaluate.ts priceBreakRemark); a side's lookback is its window (a pattern's stated window, else the first
     valid bar's) for window-class series, the whole history for recursive, cumulative and calendar ones, one bar for a
     bar field; an EVENT extends each side's lookback by `within`; a cross-section value reads (at - window, at];
     universe attributes (and Phase 2 flow) never carry it (report 6.12);
   - a universe attribute is the snapshot row's value (S2, O(1)); a null attribute is NA INSUFFICIENT_HISTORY (it is
     null only for too few bars); a metric whose applies_to excludes the ticker is NA NOT_APPLICABLE;
   - a cross-section value (return_rank) is a population-level value read from the caller (S1, xsection.ts); null is NA
     INSUFFICIENT_HISTORY (no return over the window at the ticker's bar).
   Worker-side module (imports the backtest core through metrics.ts). */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import type {
  Cell, CellRemark, ConditionDef, MetricRef, ParamMap, PatternRef, Side, Test, TestKind, UniverseRow, ValueTest, XsectionRef,
} from './contract.ts';
import { ScreenerError } from './errors.ts';
import { METRICS_CATALOG, appliesTo, metricSpec, resolveCatalogParams } from './catalog.ts';
import type { MetricDefinition, MetricsCatalog } from './catalog.ts';
import {
  compareAt, crossSignal, evaluateEvent, valuePasses, evaluateState, evaluateStatePattern, evaluateValue, lookbackStart, lookbackStartOfWindow,
  priceBreakRemark, signalAt, toCell, viewOfSeries, viewOfTail,
} from './evaluate.ts';
import type { BarView, Evaluation, Operand } from './evaluate.ts';
import { laggedSeries, missingInput, resolveSeries } from './metrics.ts';
import type { ResolvedIndicator, ResolvedSeries, SeriesSource, Tail, TickerBars } from './metrics.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import { resolveSignal } from './transforms.ts';
import type { ParamOptions } from './registry.ts';
import { priceBreakDates } from './universe.ts';

/** What a binding needs besides the condition: the parameter options (caps), IHSG's bars (vs_index), the technical
    within limit and the metric catalog. */
export interface BindContext extends ParamOptions {
  index?: TickerBars;
  withinMax: number;
  catalog?: MetricsCatalog;
}

/** What evaluating a condition reads for one ticker; the worker answers it from its snapshot. */
export interface TickerInput {
  ticker: string;
  dates: readonly string[];
  bars: Bars;
  /** the evaluation bar: the ticker's last bar on or before E (evaluate.ts evaluationBar); in the snapshot its last bar */
  at: number;
  /** the ticker's universe row (attributes and remarks; universe.ts) */
  row: UniverseRow;
  ihsgCalendar: readonly string[];
  /** the caller's one series path for this ticker (metrics.ts series(ctx, tickerCalc(t), r)) */
  series(r: ResolvedSeries): { tail: Tail; source: SeriesSource };
  /** a population-level value (stage S1) by the bound condition's xsection key; null when the ticker has none */
  xsection(key: string): number | null;
}

/** A population-level metric a condition reads (report 6.10 stage S1; xsection.ts). */
export interface XsectionNeed { key: string; metric: string; params: ParamMap; window: number }

/** One side of a STATE or EVENT comparison, bound. */
type BoundSide = { kind: 'value'; value: number } | { kind: 'series'; r: ResolvedSeries };

/** A condition bound once per request (report 6.9). evaluate() is pure per ticker (the planner's premise, plan.ts). */
export interface BoundCondition {
  id: string;
  kind: TestKind;
  /** the test with every reference normalized (parameters and arguments complete; validate.ts uses it) */
  test: Test;
  /** every series the condition reads, lagged sides included (pre-warm, the S2 / S3 choice, the cost model) */
  series: ResolvedSeries[];
  xsection: XsectionNeed | null;
  universeAttr: string | null;
  /** the per-condition summary fields of report 8.5 conditions[] that do not depend on the run */
  summary: { metric: string; params_resolved: ParamMap; is_default: boolean; unit: string | null };
  evaluate(input: TickerInput): { cell: Cell; source: SeriesSource };
}

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const isValueSide = (s: Side): s is { value: number } => isObj(s) && !('kind' in s) && 'value' in s;

/** The start of a series' lookback at `at` (evaluate.ts lookbackStart, or the stated window of a pattern). */
const startOf = (r: ResolvedSeries, tail: Tail, at: number, extra: number): number | null =>
  r.window !== undefined ? lookbackStartOfWindow(r.window, at, extra) : lookbackStart(r.historyClass, tail.firstValid, at, extra);

/** Reads a series for one ticker as a view; checks that the tail holds the bars an evaluation at `at` reads. */
function read(input: TickerInput, r: ResolvedSeries, reach: number): { view: BarView; tail: Tail; source: SeriesSource } {
  const { tail, source } = input.series(r);
  if (input.at - reach < tail.from && tail.from > 0)
    throw new RangeError(`condition: the tail of ${r.label} on ${input.ticker} starts at bar ${tail.from}, but bar ${input.at - reach} is needed (evaluate at the last bar)`);
  return { view: viewOfTail(tail, missingInput(input, r.inputs, input.at) !== null), tail, source };
}

/** The bound side of a STATE / EVENT comparison. */
function bindSide(s: Side, field: string, ctx: BindContext): BoundSide {
  if (isValueSide(s)) {
    if (typeof s.value !== 'number' || !Number.isFinite(s.value)) throw new ScreenerError('INVALID_CONDITION', `${field}.value must be a number.`, `${field}.value`);
    return { kind: 'value', value: s.value };
  }
  return { kind: 'series', r: resolveSeries(s as MetricRef, field, ctx) };
}

/** The display name of a side (report 8.5 conditions[].metric: '<id>.<output>', '<lhs> x <rhs>'). */
const nameOf = (s: BoundSide) => s.kind === 'value' ? String(s.value) : s.r.label;
const indicatorsOf = (rs: readonly ResolvedSeries[]): ResolvedIndicator[] => rs.filter(r => r.kind === 'indicator') as ResolvedIndicator[];

/** A condition (normalized by validate.ts, or a preset's) bound to its series. `field` is its path in the request
    ('definition.conditions[2]'); a reference problem is the ScreenerError naming it. */
export function bindCondition(def: ConditionDef, field: string, ctx: BindContext): BoundCondition {
  return bindTest(def.id, def.test, `${field}.test`, ctx);
}
/** One test bound to its series under the cell id `id`; `f` is the test's own path (a condition's
    'definition.conditions[2].test', a metric filter's 'definition.universe.metric_filters[0]'). */
export function bindTest(id: string, test: Test, f: string, ctx: BindContext): BoundCondition {
  const t = test as Test, catalog = ctx.catalog ?? METRICS_CATALOG;
  if (!isObj(t)) throw new ScreenerError('INVALID_CONDITION', `${f} must be a test.`, f);
  if (t.kind === 'value') return bindValue(id, t, f, ctx, catalog);
  if (t.kind === 'state') {
    if ('pattern' in t && t.pattern) return bindPattern(id, 'state', t.pattern as PatternRef, 0, `${f}.pattern`, ctx);
    const st = t as Extract<Test, { kind: 'state'; lhs: Side }>;
    return bindCompare(id, 'state', st.lhs, st.op, st.rhs, 0, f, ctx);
  }
  if (t.kind === 'event') {
    const within = t.within;
    if (!(Number.isInteger(within) && within >= 1 && within <= ctx.withinMax))
      throw new ScreenerError('INVALID_CONDITION', `${f}.within must be a whole number of sessions from 1 to ${ctx.withinMax}.`, `${f}.within`);
    const sig = t.signal as unknown as Record<string, unknown>;
    if (!isObj(sig)) throw new ScreenerError('INVALID_CONDITION', `${f}.signal must be a cross or a pattern.`, `${f}.signal`);
    if ('pattern' in sig) return bindPattern(id, 'event', sig.pattern as PatternRef, within, `${f}.signal.pattern`, ctx);
    return bindCompare(id, 'event', sig.lhs as Side, sig.op as 'crosses_above' | 'crosses_below', sig.rhs as Side, within, `${f}.signal`, ctx);
  }
  throw new ScreenerError('INVALID_CONDITION', `${f}.kind must be value, state or event.`, `${f}.kind`, { allowed: ['value', 'state', 'event'] });
}

function bindValue(id: string, t: ValueTest, f: string, ctx: BindContext, catalog: MetricsCatalog): BoundCondition {
  const m = t.metric as MetricRef;
  if (!isObj(m)) throw new ScreenerError('INVALID_CONDITION', `${f}.metric must be a metric reference.`, `${f}.metric`);
  const rule = { op: t.op, value: t.value, value2: t.value2 };
  const testOf = (metric: MetricRef): ValueTest => ({ kind: 'value', metric, op: t.op, value: t.value, ...(t.op === 'between' ? { value2: t.value2 } : {}) });
  if (m.kind === 'universe') {
    const spec = universeSpec(m.attr, `${f}.metric.attr`, catalog);
    return {
      id, kind: 'value', test: testOf({ kind: 'universe', attr: spec.id }), series: [], xsection: null, universeAttr: spec.id,
      summary: { metric: spec.id, params_resolved: {}, is_default: true, unit: spec.unit },
      evaluate: input => {
        let e: Evaluation;
        if (!appliesTo(spec.applies_to, input.row)) e = { status: 'na', reason: 'NOT_APPLICABLE', value: null };
        else {
          const x = (input.row as unknown as Record<string, unknown>)[spec.id];
          e = typeof x === 'number' && Number.isFinite(x) ? { status: valuePasses(x, rule) ? 'pass' : 'fail', reason: null, value: x } : { status: 'na', reason: 'INSUFFICIENT_HISTORY', value: null };
        }
        return { cell: toCell(id, e, { dates: input.dates, at: input.at, ihsgCalendar: input.ihsgCalendar, unit: spec.unit, remark: null }), source: 'precomputed' };
      },
    };
  }
  if (m.kind === 'xsection') {
    const x = xsectionNeed(m, `${f}.metric`, catalog);
    return {
      id, kind: 'value', test: testOf({ kind: 'xsection', metric: x.metric, params: x.params } as XsectionRef), series: [], xsection: x, universeAttr: null,
      summary: { metric: x.metric, params_resolved: x.params, is_default: canonicalJson(x.params) === canonicalJson(defaultsOf(metricSpec('xsection', x.metric, 'm', catalog))), unit: metricSpec('xsection', x.metric, 'm', catalog).unit },
      evaluate: input => {
        const v = input.xsection(x.key);
        const e: Evaluation = typeof v === 'number' && Number.isFinite(v) ? { status: valuePasses(v, rule) ? 'pass' : 'fail', reason: null, value: v } : { status: 'na', reason: 'INSUFFICIENT_HISTORY', value: null };
        const ex = priceBreakDates(input.row);
        const remark = ex.length ? priceBreakRemark([input.at - x.window], input.dates, input.at, ex) : null;
        return { cell: toCell(id, e, { dates: input.dates, at: input.at, ihsgCalendar: input.ihsgCalendar, unit: null, remark }), source: 'precomputed' };
      },
    };
  }
  if (m.kind === 'flow') throw unavailableFlow(m.metric, `${f}.metric`, catalog);
  if (m.kind === 'pattern') throw new ScreenerError('INVALID_CONDITION', `${f}.metric: a pattern is a signal, not a value; use it in a state or event test ({"kind":"state","pattern":...}).`, `${f}.metric`);
  const r = resolveSeries(m, `${f}.metric`, ctx);
  return {
    id, kind: 'value', test: testOf(r.ref), series: [r], xsection: null, universeAttr: null,
    summary: summaryOf([{ kind: 'series', r }], r.label, r.unit),
    evaluate: input => {
      const { view, tail, source } = read(input, r, 0);
      const e = evaluateValue(view, rule, input.at);
      return { cell: cellOf(id, e, input, r.unit, [startOf(r, tail, input.at, 0)]), source };
    },
  };
}

function bindCompare(id: string, kind: 'state' | 'event', lhs: Side, op: string, rhs: Side, within: number, f: string, ctx: BindContext): BoundCondition {
  const ops = kind === 'state' ? ['gt', 'lt'] : ['crosses_above', 'crosses_below'];
  if (!ops.includes(op)) throw new ScreenerError('INVALID_CONDITION', `${f}.op must be ${ops.join(' or ')}.`, `${f}.op`, { allowed: ops });
  if (!isObj(lhs) || !isObj(rhs)) throw new ScreenerError('INVALID_CONDITION', `${f}: lhs and rhs are both required.`, f);
  const L0 = bindSide(lhs, `${f}.lhs`, ctx), R0 = bindSide(rhs, `${f}.rhs`, ctx);
  // the lag probe's rule (report 6.8): a bar field compared with a series that same-bar comparisons can never pass
  // reads the series' previous bar. The bar field's direction decides the lag: price gt / crosses_above x reads
  // x.compareLag.gt; with the bar field on the right (x gt price, i.e. price lt x) the direction turns over
  const isBar = (s: BoundSide) => s.kind === 'series' && s.r.kind === 'price';
  const up = op === 'gt' || op === 'crosses_above';
  const lagged = (s: BoundSide, d: 'gt' | 'lt', field: string): BoundSide => s.kind === 'series' && s.r.compareLag[d] === 1 ? { kind: 'series', r: laggedSeries(s.r, field, ctx) } : s;
  const L = isBar(R0) && !isBar(L0) ? lagged(L0, up ? 'lt' : 'gt', `${f}.lhs`) : L0;
  const R = isBar(L0) && !isBar(R0) ? lagged(R0, up ? 'gt' : 'lt', `${f}.rhs`) : R0;
  const sides = [L, R];
  const series = sides.flatMap(s => s.kind === 'series' ? [s.r] : []);
  const norm = (s: BoundSide): Side => s.kind === 'value' ? { value: s.value } : s.r.ref;
  const test: Test = kind === 'state'
    ? { kind: 'state', lhs: norm(L0), op: op as 'gt' | 'lt', rhs: norm(R0) }
    : { kind: 'event', signal: { lhs: norm(L0), op: op as 'crosses_above' | 'crosses_below', rhs: norm(R0) }, within };
  // report 8.5: '<id>.<output>' for a level against the price (the example's condition b), '<lhs> x <rhs>' for two
  // references, the reference alone against a value
  const name = isBar(L0) && R0.kind === 'series' ? R0.r.label : isBar(R0) && L0.kind === 'series' ? L0.r.label
    : R0.kind === 'value' ? nameOf(L0) : L0.kind === 'value' ? nameOf(R0) : `${nameOf(L0)} x ${nameOf(R0)}`;
  const unitOf = (s: BoundSide) => s.kind === 'series' && !isBar(s) ? s.r.unit : null;
  const unit = (unitOf(L0) ?? unitOf(R0) ?? (L0.kind === 'series' ? L0.r.unit : R0.kind === 'series' ? R0.r.unit : null)) as string | null;
  const reach = kind === 'event' ? ctx.withinMax : 0;
  return {
    id, kind, test, series, xsection: null, universeAttr: null,
    summary: summaryOf([L0, R0], name, unit),
    evaluate: input => {
      const reads = sides.map(s => s.kind === 'value' ? null : read(input, s.r, reach));
      const operand = (k: number): Operand => sides[k].kind === 'value' ? (sides[k] as { value: number }).value : reads[k]!.view;
      const lv = operand(0), rv = operand(1);
      const e = kind === 'state'
        ? evaluateState(lv, op as 'gt' | 'lt', rv, input.at)
        : evaluateEvent(crossSignal(lv, op as 'crosses_above' | 'crosses_below', rv), within, ctx.withinMax, input.at, { lhs: lv, rhs: rv });
      const starts = sides.flatMap((s, k) => s.kind === 'value' ? [] : [startOf(s.r, reads[k]!.tail, input.at, kind === 'event' ? within : 0)]);
      const source: SeriesSource = reads.every(x => !x || x.source === 'precomputed') ? 'precomputed' : 'dynamic';
      return { cell: cellOf(id, e, input, unit, starts), source };
    },
  };
}

function bindPattern(id: string, kind: 'state' | 'event', p: PatternRef, within: number, f: string, ctx: BindContext): BoundCondition {
  if (!isObj(p) || (p as { kind?: unknown }).kind !== 'pattern') throw new ScreenerError('INVALID_CONDITION', `${f} must be a pattern reference {"kind":"pattern","type":...}.`, f);
  const r = resolveSignal(p, f, ctx);
  const spec = metricSpec('pattern', r.ref && (r.ref as PatternRef).type, f, ctx.catalog ?? METRICS_CATALOG);
  if (!spec.tests.includes(kind)) throw new ScreenerError('INVALID_CONDITION', `${f}: ${spec.id} is offered as ${spec.tests.join(' or ')}, not as ${kind}.`, f, { allowed: spec.tests });
  const test: Test = kind === 'state' ? { kind: 'state', pattern: r.ref as PatternRef } : { kind: 'event', signal: { pattern: r.ref as PatternRef }, within };
  const params = (r.ref as PatternRef).params || {};
  return {
    id, kind, test, series: [r], xsection: null, universeAttr: null,
    summary: { metric: spec.id, params_resolved: params, is_default: canonicalJson(params) === canonicalJson(defaultsOf(spec)), unit: null },
    evaluate: input => {
      const { view, tail, source } = read(input, r, kind === 'event' ? ctx.withinMax : 0);
      const e = kind === 'state' ? evaluateStatePattern(view, input.at) : evaluateEvent(i => signalAt(view, i), within, ctx.withinMax, input.at);
      return { cell: cellOf(id, e, input, null, [startOf(r, tail, input.at, kind === 'event' ? within : 0)]), source };
    },
  };
}

/* ---- helpers ------------------------------------------------------------------------------------------------------- */

function cellOf(id: string, e: Evaluation, input: TickerInput, unit: string | null, starts: (number | null)[]): Cell {
  const ex = priceBreakDates(input.row);
  const remark: CellRemark | null = ex.length ? priceBreakRemark(starts, input.dates, input.at, ex) : null;
  return toCell(id, e, { dates: input.dates, at: input.at, ihsgCalendar: input.ihsgCalendar, unit: unit as string | null, remark });
}
const defaultsOf = (m: MetricDefinition): ParamMap => Object.fromEntries(m.params.map(p => [p.key, p.default]));
function summaryOf(sides: BoundSide[], metric: string, unit: string | null): BoundCondition['summary'] {
  const rs = sides.flatMap(s => s.kind === 'series' ? [s.r] : []);
  const inds = indicatorsOf(rs), main = inds[0];
  return { metric, params_resolved: main ? (main.params as ParamMap) : {}, is_default: inds.every(r => r.isDefault) && rs.every(r => r.kind === 'indicator' || r.kind === 'price'), unit: unit as string | null };
}
function universeSpec(attr: unknown, field: string, catalog: MetricsCatalog): MetricDefinition {
  return metricSpec('universe', attr, field, catalog);
}
/** A cross-section reference with its parameters complete (catalog), keyed for the caller's S1 values. */
export function xsectionNeed(m: XsectionRef, field: string, catalog: MetricsCatalog = METRICS_CATALOG): XsectionNeed {
  const spec = metricSpec('xsection', m.metric, `${field}.metric`, catalog);
  const params = resolveCatalogParams(spec.params, m.params, `${field}.params`);
  return { key: canonicalJson({ kind: 'xsection', metric: spec.id, params }), metric: spec.id, params, window: params.window as number };
}
function unavailableFlow(metric: unknown, field: string, catalog: MetricsCatalog): ScreenerError {
  const spec = metricSpec('flow', metric, `${field}.metric`, catalog);
  const why = (spec.decision || spec.unavailable_reason || 'Flow arrives with Phase 2').replace(/\.$/, '');
  return new ScreenerError('METRIC_UNAVAILABLE', `${field}: ${spec.id} is not available yet: ${why}.`, field,
    { metric: spec.id, availability: spec.decision ? 'REQUIRES_DECISION' : 'REQUIRES_DATA', reason: spec.decision || spec.unavailable_reason || '' });
}

/* ---- whole-series signals (preview markers and chart; report 8.6) --------------------------------------------------- */

/** The condition's 0/1 outcome on every bar of a ticker's full series (VALUE: the test passes on the bar; STATE: the
    comparison or pattern on the bar; EVENT: the cross or the pattern signal on the bar, i.e. its markers), from full
    series through `full` (the caller's Calc for the ticker). Universe and cross-section conditions have no series. */
export function conditionSignal(b: BoundCondition, full: (r: ResolvedSeries) => ArrayLike<number | null | undefined>, n: number): Uint8Array | null {
  if (b.universeAttr !== null || b.xsection !== null) return null;
  const out = new Uint8Array(n), t = b.test;
  if (t.kind === 'value') {
    const v = viewOfSeries(full(b.series[0]) as ArrayLike<number | null>);
    for (let i = 0; i < n; i++) { const x = v.get(i); out[i] = +(Number.isFinite(x) && valuePasses(x, t)) }
    return out;
  }
  if ((t.kind === 'state' && 'pattern' in t && t.pattern) || (t.kind === 'event' && 'pattern' in t.signal)) {
    const s = full(b.series[0]);
    for (let i = 0; i < n; i++) out[i] = +(s[i] === 1);
    return out;
  }
  const sig = (t.kind === 'state' ? t : t.signal) as { lhs: Side; op: 'gt' | 'lt' | 'crosses_above' | 'crosses_below'; rhs: Side };
  const views: Operand[] = [], rs = [...b.series];                 // the series sides in order, lagged where bound so
  for (const s of [sig.lhs, sig.rhs]) views.push(isValueSide(s) ? s.value : viewOfSeries(full(rs.shift()!) as ArrayLike<number | null>));
  for (let i = 0; i < n; i++) out[i] = +compareAt(views[0], sig.op, views[1], i);
  return out;
}
