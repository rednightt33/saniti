/* The universal operators on the page (EXEC-SCREENER-FLOW-CANDLES P3; verification/screener/OPERATORS.md, approved by
   the user 2026-11-07, K4). A condition with an operator reads one output of the indicator (its "series"), may apply a
   measure to it (a transform: its own average, percentile, change, z-score, a second series, slope, acceleration,
   distance to its high or low) and tests the measured series one way (above or below a value, a range, a cross, ever /
   K of N / in a row, a rank among the screened stocks). Everything offered comes from the catalog's operators block
   (GET /catalog `operators`, from screener-metrics.json, the same block the core checks against): the measures with
   their arguments, ranges and defaults, the tests with their operators, which unit a result has, and which tests a unit
   cannot take (a rank of a price level). The page never decides a rule the worker does not; the worker refuses what
   the page could not know (naming the field). Pure: no DOM.
   EXEC-SCREENER-FLOW-CANDLES P5c (verification/screener/P5_FLOW.md section 4): a flow indicator's output is a series
   too. Its output type (the catalog's kind: K, P, Rp, L, H, D, F, B) decides the measures and tests offered (the
   block's not_on and not_against_value, OPERATORS.md section 4; the core's transforms.ts operatorTakes and
   condition.ts typeAllows read the same lists), "=" and "!=" are offered on the series itself where it is a whole
   number (K1, OPERATORS.md section 3, the sessions the indicator reads plus the operator's N and the test's sessions
   fit the loaded broker sessions): the worker is the one authority. A session field takes at most the broker sessions
   held, opens within the page's estimate of what the setup leaves and shows it as a hint; the lists leave out only what
   cannot fit at the catalog's own setup (the worker's depth); beyond that the worker's refusal is shown on the card.
   The functions take the card's parameters (`params`) where a flow output's kind, line and depth follow them. */
import type { CatalogOperators, MetricRef, OperatorTestKey, ParamMap, ParamValue, Test, TestFormSpec, ValueOp } from './core/contract.ts';
import { defaultParams, flowBudget, flowExactBudget, flowOutputs, flowSessions, optionText, paramError, testTakes, wholeKind, type Entry, type EntryParam } from './entries.ts';
import { formatOfMetric, formatOfOutput, fmtValue, nf, type ValueFormat } from './format.ts';

/** A card's operator: the series (the indicator output), the measure ('none' or a transform fn) with its arguments,
    the test with its operator and fields. Numbers typed in a field may be '' (empty) until the check refuses them. */
export interface OpState {
  output: string;
  measure: string;                 // 'none' or a measure fn of the catalog
  margs: Record<string, ParamValue>;
  by: string;                      // relative: 'out:<output key>' or 'price:<field>'
  test: OperatorTestKey;
  cmp: string;                     // a value op, or crosses_above / crosses_below for a cross
  value: number | ''; value2: number | '';
  n: number | ''; k: number | '';
}
export type Measure = CatalogOperators['measures'][number];
export type OpTest = CatalogOperators['tests'][number];

export const OP_WORDS: Record<string, string> = {
  gt: 'above', lt: 'below', ge: 'at or above', le: 'at or below', eq: 'equal to', ne: 'not equal to',
  between: 'between', outside: 'outside', crosses_above: 'crosses above', crosses_below: 'crosses below',
};
export const OP_SIGN: Record<string, string> = { gt: '>', lt: '<', ge: '≥', le: '≤', eq: '=', ne: '≠' };

/** One series an operator reads: an indicator output, or a flow indicator's output at the card's setup (P5c). unit and
    comparable as the core names them (a price level is 'price', comparable with the close); type: the output type of
    OPERATORS.md section 4 (a flow kind; null for an indicator output, which takes every operator); whole: "=" and "!="
    apply to it (K7); forms: an indicator output's test forms, which its plain series is tested through; drawn: the
    setup draws it (why not, when it does not); fmt: how its values are written. */
export interface Series { key: string; label: string; unit: string | null; comparable: string | null; type: string | null; whole: boolean;
  forms: TestFormSpec[] | null; drawn: boolean; why: string | null; fmt: ValueFormat }
/** The series of an entry: an indicator's outputs, or a flow indicator's outputs at `params` (the catalog's defaults
    when none are given). */
export function seriesList(e: Entry, params?: ParamMap): Series[] {
  if (e.flow) return flowOutputs(e, params ?? defaultParams(e)).map(o => ({ key:o.key, label:o.label, unit:o.unit, comparable:o.comparable, type:o.kind || null,
    whole:wholeKind(e.ops, o.kind), forms:null, drawn:o.drawn, why:o.why, fmt:formatOfMetric(o.unit) }));
  return (e.indicator?.outputs || []).map(o => ({ key:o.key, label:o.label || o.key, unit:o.unit, comparable:o.comparable_with, type:null, whole:false,
    forms:o.tests, drawn:true, why:null, fmt:formatOfOutput(o.unit, o.display_unit, null) }));
}
export const seriesOf = (e: Entry, key: string, params?: ParamMap): Series | undefined => seriesList(e, params).find(s => s.key === key);
/** Whether a card on this entry can take an operator: an indicator or a flow indicator (their outputs are series) in a
    catalog that offers operators. */
export const offersOperators = (ops: CatalogOperators | undefined, e: Entry | undefined): boolean =>
  !!ops && !!e && ((e.kind === 'indicator' && !!e.indicator?.outputs.length) || (!!e.flow && !!e.flow.outputs.length));
export const measureOf = (ops: CatalogOperators, fn: string): Measure | undefined => ops.measures.find(m => m.fn === fn);
export const testOf = (ops: CatalogOperators, key: string): OpTest | undefined => ops.tests.find(t => t.key === key);
/** the output a new operator opens on: the one the entry's default condition reads, else the first the setup draws */
export const defaultOutput = (e: Entry, params?: ParamMap): string => e.opts.find(o => o.key === e.def.opt)?.output
  || (seriesList(e, params).find(s => s.drawn) ?? seriesList(e, params)[0])?.key || '';

/* ---- K1: the broker sessions a flow series leaves to its operator and test (OPERATORS.md section 3) ------------- */
/** the measure argument that counts sessions (its length, or bars for a change), as the core's transforms.ts
    operatorSessions reads it */
const sessionArg = (m: Measure | undefined) => m?.args.find(a => a.key === 'length') ?? m?.args.find(a => a.key === 'bars');
/** sessions per unit of that argument: acceleration reads two slopes of N (OPERATORS.md section 3: 2N + window) */
const perUnit = (m: Measure | undefined) => m?.fn === 'acceleration' ? 2 : 1;
/** the sessions a measure reads before its series' own (0 without one, or for a relative comparison) */
export function measureSessions(ops: CatalogOperators, op: OpState): number {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure), a = sessionArg(m), v = a ? Number(op.margs[a.key]) : 0;
  return Number.isFinite(v) ? v * perUnit(m) : 0;
}
/** the sessions a test reads beyond the evaluated one (the core's condition.ts testSessions: a cross's within, a window's
    length, plus one for a cross counted inside a window) */
export function testSessions(ops: CatalogOperators, op: OpState): number {
  const t = testOf(ops, op.test), n = Number(op.n);
  if (!t || !(t.within || t.length) || !Number.isFinite(n)) return 0;
  return n + (t.length && op.cmp.startsWith('crosses_') ? 1 : 0);
}
/** the broker sessions left at this setup, the page's estimate (null: not a flow entry, or not known): a hint and the
    defaults a field opens with, never a refusal */
const budgetOf = (e: Entry, params?: ParamMap) => e.flow ? flowBudget(e, params ?? defaultParams(e)) : null;
/** the same at the catalog's own setup only, where it is the worker's figure (what the lists may leave out) */
const exactOf = (e: Entry, params?: ParamMap) => e.flow ? flowExactBudget(e, params ?? defaultParams(e)) : null;
/** the estimated most of the measure's session argument with this test on this setup (K1) */
function measureMax(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): number | null {
  const B = budgetOf(e, params), m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  return B == null || !sessionArg(m) ? null : Math.floor((B - testSessions(ops, op)) / perUnit(m));
}
/** the estimated most of the test's sessions (within, the window's N) with this measure on this setup (K1) */
function testMax(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): number | null {
  const B = budgetOf(e, params);
  return B == null ? null : B - measureSessions(ops, op) - (testOf(ops, op.test)?.length && op.cmp.startsWith('crosses_') ? 1 : 0);
}
/** A measure's arguments at their defaults; on a flow series the session argument opens within half of the sessions
    left (the other half for the test's sessions), never below its minimum. */
function argDefaults(m: Measure | undefined, budget: number | null = null): Record<string, ParamValue> {
  const out: Record<string, ParamValue> = Object.fromEntries((m?.args || []).map(a => [a.key, a.default as ParamValue]));
  const a = sessionArg(m);
  if (a && budget != null && typeof out[a.key] === 'number') out[a.key] = Math.max(a.min ?? 1, Math.min(out[a.key] as number, Math.floor(budget / 2 / perUnit(m))));
  return out;
}
/** the fewest sessions a measure reads (its session argument at its minimum) */
const minSessions = (m: Measure) => { const a = sessionArg(m); return a ? (a.min ?? 1) * perUnit(m) : 0 };

/** The operator a card opens with: the catalog's default measure on the entry's default output, with the measure's
    default comparison; on a flow series where that measure is not offered (its type, or the broker sessions left),
    the series itself, else the first measure offered. */
export function defaultOp(ops: CatalogOperators, e: Entry, output = defaultOutput(e), params?: ParamMap): OpState {
  const offered = e.flow ? measuresFor(ops, e, output, params) : ops.measures;
  const m = offered.find(x => x.fn === ops.default_measure) ?? (e.flow ? undefined : ops.measures[0]);
  if (!m) {
    const base: OpState = { output, measure: 'none', margs: {}, by: '', test: 'value', cmp: 'gt', value: e.def.value, value2: '', n: '', k: '' };
    if (plainOffered(ops, e, output, params) || !offered.length) { const t = testsFor(ops, e, base, params); return withTest(ops, e, base, t[0]?.key ?? 'value', params) }
    return withMeasure(ops, e, base, offered[0].fn, params);
  }
  return { output, measure: m.fn, margs: argDefaults(m, budgetOf(e, params)), by: '', test: 'value', cmp: m.default.cmp, value: m.default.value, value2: '', n: '', k: '' };
}
/** The operator with another measure: its arguments' defaults, then the test (kept when it still applies, else the
    first one offered) with the values that suit the new measure (withTest). */
export function withMeasure(ops: CatalogOperators, e: Entry, op: OpState, fn: string, params?: ParamMap): OpState {
  const m = fn === 'none' ? undefined : measureOf(ops, fn);
  const next: OpState = { ...op, measure: m ? m.fn : 'none', margs: argDefaults(m, budgetOf(e, params)), by: m?.second ? secondOptions(e, op.output, params)[0]?.key ?? '' : '', cmp: m?.default.cmp ?? op.cmp };
  const tests = testsFor(ops, e, next, params);
  return withTest(ops, e, next, tests.some(t => t.key === next.test) ? next.test : tests[0]?.key ?? 'value', params);
}
/** The thresholds a test opens with on the measured series (QA5 2026-11-07 D3: one range for every measure, and values
    kept from the previous test, gave screens that match nothing): a rank its own (0-100); a range the measure's range
    (catalog default.range) or, on the plain series, the entry's own between bounds, else blank fields to fill in (a
    difference has no scale-free range); any other test the measure's default value, or the entry's own on the plain
    series. Never a value of another measure or test. */
function thresholds(ops: CatalogOperators, e: Entry, op: OpState, t: OpTest, two = t.key === 'range'): { value: number | ''; value2: number | '' } {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  // a rank is 0-100 whatever it ranks: its own value, or its own range (QA5 round 2: a rank range opened blank)
  if (t.key === 'rank') return two && t.default.range ? { value: t.default.range[0], value2: t.default.range[1] } : { value: t.default.value ?? '', value2: '' };
  if (two) {
    const r = m ? m.default.range : (typeof e.def.value === 'number' && typeof e.def.value2 === 'number' ? [e.def.value, e.def.value2] : undefined);
    return r ? { value: r[0], value2: r[1] } : { value: '', value2: '' };
  }
  return { value: m ? m.default.value : e.def.value, value2: '' };
}
/** The operator with another test: its default fields and the thresholds that suit the measured series (thresholds);
    the comparison kept when the test takes it. */
export function withTest(ops: CatalogOperators, e: Entry, op: OpState, key: string, params?: ParamMap): OpState {
  const t = testOf(ops, key) ?? ops.tests[0], d = t.default || {}, offered = opsFor(e, op, t, params);
  const cmp = offered.includes(op.cmp) ? op.cmp : d.cmp && offered.includes(d.cmp) ? d.cmp : offered[0] ?? t.ops[0];
  const next: OpState = { ...op, test: t.key, cmp: t.key === 'range' && !['between', 'outside'].includes(cmp) ? 'between' : cmp, ...thresholds(ops, e, op, t),
    n: d.n ?? (t.within || t.length ? op.n || 5 : ''), k: d.k ?? (t.count ? op.k || 3 : '') };
  // K1 on a flow series: the test's sessions open within what the measure leaves (K of N with K at most N)
  const room = testMax(ops, e, next, params);
  if (room != null && room >= 1 && typeof next.n === 'number' && next.n > room) { next.n = room; if (typeof next.k === 'number' && next.k > room) next.k = room }
  return next;
}
/** The operator with another comparison: a range operator (between, outside) on a test that was not one opens with the
    range thresholds, a single-value one after a range with the single default. */
export function withCmp(ops: CatalogOperators, e: Entry, op: OpState, cmp: string): OpState {
  const two = (c: string) => c === 'between' || c === 'outside', t = testOf(ops, op.test);
  if (!t || two(cmp) === two(op.cmp)) return { ...op, cmp };
  return { ...op, cmp, ...thresholds(ops, e, op, t, two(cmp)) };
}

/** The unit of the measured series: a measure's own (fixed, or by its form argument; 'diff' is a difference of the
    series: a price difference for a price level, else the series' unit), else the output's. */
export function resultUnit(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): string {
  const out = seriesOf(e, op.output, params), base = out?.unit || 'other';
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  if (!m) return base;
  const u = typeof m.unit === 'string' ? m.unit : m.unit[String(op.margs[m.unit.by])] ?? 'other';
  return u === 'diff' ? (base === 'price' ? 'price_change' : base) : u;
}
/** The output type of the measured series (the core's transforms.ts outputType): the series' own on the series itself;
    P or D from the measure that makes it (the block's types[].fns: a percentile or a z-score); null for any other
    measure (a difference, a ratio, a slope: no type, every test). */
export function resultType(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): string | null {
  if (op.measure === 'none') return seriesOf(e, op.output, params)?.type ?? null;
  return Object.entries(ops.types).find(([, t]) => t.fns.includes(op.measure))?.[0] ?? null;
}
/** a level (a price or volume level of the output, not measured): what the rank test's not_on_levels names */
const isLevel = (e: Entry, op: OpState, params?: ParamMap) => op.measure === 'none' && !!seriesOf(e, op.output, params)?.comparable;
/** The overlay forms of an output that the plain series ("The value itself", no measure) is tested through: a value
    test (and a window test, whose inner test is a value test) needs the output's 'value' form, a cross its
    'event_value' form, with the operators those forms list (the core's validate.ts requireForm; ge and le belong to gt
    and lt, outside to between). A measured series is a transform, which the core takes in every test. */
const FORM_OF: Partial<Record<OperatorTestKey, string>> = { value: 'value', range: 'value', ever: 'value', at_least: 'value', streak: 'value', cross: 'event_value' };
const FAMILY: Record<string, string> = { ge: 'gt', le: 'lt', outside: 'between' };
function plainOps(e: Entry, op: OpState, t: OpTest): string[] | null {
  if (op.measure !== 'none' || t.key === 'rank' || e.flow) return null;   // no form needed (a flow series: its type decides)
  const forms = seriesOf(e, op.output)?.forms || [];
  const value = forms.find(x => x.form === FORM_OF[t.key])?.ops as string[] | undefined;
  // a window counts a cross on each session through the output's event_value form (its crosses_above / crosses_below)
  const cross = t.key === 'ever' || t.key === 'at_least' ? forms.find(x => x.form === 'event_value')?.ops as string[] | undefined : undefined;
  return [...(value || []), ...(cross || [])];
}
/** The tests the measured series takes: the rank only on a unit that compares across stocks (the catalog's
    not_on_units and not_on_levels; OPERATORS.md section 4); on the plain series, only the tests its forms offer; on a
    flow series only the tests its output type takes (not_on) and, for a test that reads sessions at the catalog's own
    setup, while the broker sessions leave one (K1, the worker's depth). */
export function testsFor(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): OpTest[] {
  const unit = resultUnit(ops, e, op, params), type = resultType(ops, e, op, params), B = exactOf(e, params), used = measureSessions(ops, op);
  return ops.tests.filter(t => (t.key !== 'rank' || (!(t.not_on_units || []).includes(unit) && !(t.not_on_levels && isLevel(e, op, params))))
    && (!type || !(t.not_on || []).includes(type)) && (t.key !== 'cross' || testTakes(ops, 'cross', type, true))
    && (B == null || !(t.within || t.length) || used + 1 <= B) && opsFor(e, op, t, params).length > 0);
}
/** the test a comparison is on its own (a cross of a fixed value, a range, else a value test): inside a window the inner
    test of each session (the core's condition.ts typeAllows on it) */
const CMP_TEST = (o: string) => o.startsWith('crosses_') ? 'cross' : o === 'between' || o === 'outside' ? 'range' : 'value';
/** A test's operators as offered on this series: on the plain series of an indicator the ones its form lists; on a flow
    series the ones whose own test its output type takes; "=" and "!=" only on the series itself where it is a whole
    number (a day count, a 0/1 signal, a broker count: K7), never on a measured series (no measure gives a whole number). */
export function opsFor(e: Entry, op: OpState, t: OpTest, params?: ParamMap): string[] {
  const plain = plainOps(e, op, t);
  const type = e.flow && e.ops && t.key !== 'rank' ? resultType(e.ops, e, op, params) : null;
  const whole = t.key === 'value' && op.measure === 'none' && !!seriesOf(e, op.output, params)?.whole;
  // a cross counted inside a window reads the session before its first one too (K1: at least two sessions left)
  const B = t.length && e.ops ? exactOf(e, params) : null, crossRoom = B == null || B - measureSessions(e.ops!, op) >= 2;
  return t.ops.filter(o => ((o !== 'eq' && o !== 'ne') || whole) && (plain === null || plain.includes(FAMILY[o] ?? o))
    && (!type || testTakes(e.ops, CMP_TEST(o), type, CMP_TEST(o) === 'cross')) && (crossRoom || !o.startsWith('crosses_')));
}
export const opsOf = (t: OpTest): string[] => t.ops.filter(o => o !== 'eq' && o !== 'ne');

/** The second series a relative comparison can take on this output: another output of the same indicator with the same
    unit and level, and the bar fields of the same unit (the close against a price level, the volume against a volume
    level). key: 'out:<output>' or 'price:<field>'. */
export function secondOptions(e: Entry, output: string, params?: ParamMap): { key: string; label: string }[] {
  const all = seriesList(e, params), o = all.find(x => x.key === output); if (!o) return [];
  const outs = all.filter(x => x.key !== output && x.drawn && x.unit === o.unit && x.comparable === o.comparable)
    .map(x => ({ key: `out:${x.key}`, label: x.label }));
  const prices = o.comparable === 'close' ? ['close', 'open', 'high', 'low'] : o.comparable === 'volume' ? ['volume'] : [];
  return [...outs, ...prices.map(f => ({ key: `price:${f}`, label: f.charAt(0).toUpperCase() + f.slice(1) }))];
}
/** The measures offered on this output: every measure of the catalog (an indicator output is never a percentile, a
    z-score or a run: the types of OPERATORS.md section 4 come from the measures themselves), the relative comparison
    only where the output has a second series of its unit; on a flow series only the measures its output type takes
    (not_on) and, at the catalog's own setup, that fit the broker sessions it leaves (K1, the worker's depth). */
export function measuresFor(ops: CatalogOperators, e: Entry, output: string, params?: ParamMap): Measure[] {
  const type = e.flow ? seriesOf(e, output, params)?.type : null, B = exactOf(e, params);
  return ops.measures.filter(m => (!m.second || secondOptions(e, output, params).length > 0) && !(type && m.not_on.includes(type)) && (B == null || minSessions(m) <= B));
}
/** Whether "The value itself" (no measure) is offered on this output: when some test takes the plain series. */
export function plainOffered(ops: CatalogOperators, e: Entry, output: string, params?: ParamMap): boolean {
  const base: OpState = { output, measure: 'none', margs: {}, by: '', test: 'value', cmp: 'gt', value: '', value2: '', n: '', k: '' };
  return testsFor(ops, e, base, params).length > 0;
}

/* ---- the wire ------------------------------------------------------------------------------------------------- */
type IndRef = (params: ParamMap, output: string) => MetricRef;
const num = (v: number | '' | undefined) => v === '' || v == null ? NaN : Number(v);
/** The measured series' reference: the output (built by the caller, which sends only the parameters that differ from
    the registry's), wrapped in the measure's transform with its arguments. */
function seriesRef(ops: CatalogOperators, op: OpState, params: ParamMap, ind: IndRef): MetricRef {
  const base = ind(params, op.output);
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  if (!m) return base;
  const args: Record<string, ParamValue | MetricRef> = { ...op.margs };
  if (m.second) args.by = op.by.startsWith('price:') ? { kind: 'price', field: op.by.slice(6) as never } : ind(params, op.by.slice(4));
  return { kind: 'transform', fn: m.fn, of: base, args };
}
/** The wire test of an operator (contract.ts: a value test, an event cross of a value, a window test over a value test,
    or a value test on a rank). */
export function opTest(ops: CatalogOperators, op: OpState, params: ParamMap, ind: IndRef): Test {
  const s = seriesRef(ops, op, params, ind), v = num(op.value), v2 = num(op.value2), n = num(op.n), k = num(op.k);
  const value = (metric: MetricRef, cmp = op.cmp): Test => ({ kind: 'value', metric, op: cmp as ValueOp, value: v, ...(cmp === 'between' || cmp === 'outside' ? { value2: v2 } : {}) });
  // inside a window a cross is read on each session: an event with within 1 (OPERATORS.md 5 and 9 over operator 8)
  const inner = (): Test => op.cmp.startsWith('crosses_') ? { kind: 'event', within: 1, signal: { lhs: s, op: op.cmp as 'crosses_above' | 'crosses_below', rhs: { value: v } } } : value(s);
  switch (op.test) {
    case 'value': case 'range': return value(s);
    case 'cross': return { kind: 'event', within: n, signal: { lhs: s, op: op.cmp as 'crosses_above' | 'crosses_below', rhs: { value: v } } };
    case 'ever': case 'streak': return { kind: 'window', mode: op.test, length: n, test: inner() as never };
    case 'at_least': return { kind: 'window', mode: 'at_least', length: n, count: k, test: inner() as never };
    case 'rank': return value({ kind: 'rank', of: s });
  }
}
/** An operator read back from a wire test (fromWire), with the indicator and its parameters, or null when the test is
    not an operator's (or names what the catalog does not offer). */
export function opFromTest(ops: CatalogOperators, t: any): { indicator: string; params: ParamMap; op: OpState } | null {
  if (!t || typeof t !== 'object') return null;
  let test: OperatorTestKey, inner = t, n: number | '' = '', k: number | '' = '';
  if (t.kind === 'window') {
    test = t.mode; inner = t.test; n = t.length; k = t.mode === 'at_least' ? t.count : '';
    // a cross counted over the window: an event with within 1 (opTest inner)
    if (inner?.kind === 'event' && inner.within === 1 && !inner.signal?.pattern && typeof inner.signal?.rhs?.value === 'number' && !inner.signal.rhs.kind) {
      const r = read(ops, inner.signal.lhs); if (!r) return null;
      return { ...r, op: { ...r.op, test, cmp: inner.signal.op, value: inner.signal.rhs.value, value2: '', n, k } };
    }
  }
  else if (t.kind === 'event') {
    if (!t.signal || t.signal.pattern || typeof t.signal.rhs?.value !== 'number' || t.signal.rhs.kind) return null;
    const r = read(ops, t.signal.lhs); if (!r || r.op.measure === 'none') return null;          // a plain cross is the card's own form
    return { ...r, op: { ...r.op, test: 'cross', cmp: t.signal.op, value: t.signal.rhs.value, n: t.within } };
  } else test = 'value';
  if (!inner || inner.kind !== 'value') return null;
  let metric = inner.metric;
  if (metric?.kind === 'rank') { if (test !== 'value') return null; test = 'rank'; metric = metric.of }
  const r = read(ops, metric); if (!r) return null;
  if (test === 'value' && (inner.op === 'between' || inner.op === 'outside')) test = 'range';
  // a plain value test (no measure, no window, no rank) on gt / lt / between is the card's own form, not an operator
  if (r.op.measure === 'none' && test !== 'rank' && t.kind !== 'window' && ['gt', 'lt', 'between'].includes(inner.op)) return null;
  return { ...r, op: { ...r.op, test, cmp: inner.op, value: inner.value, value2: typeof inner.value2 === 'number' ? inner.value2 : '', n, k } };
}
/** an output, or a measure of one, read back: the indicator (or flow indicator: its id), its parameters as the wire
    has them and the operator's series part; a flow output left out is '' (the caller names the entry's default) */
function read(ops: CatalogOperators, r: any): { indicator: string; params: ParamMap; op: OpState } | null {
  const blank = { test: 'value' as OperatorTestKey, cmp: 'gt', value: '' as const, value2: '' as const, n: '' as const, k: '' as const };
  const idOf = (x: any): string | null => x?.kind === 'indicator' && typeof x.indicator === 'string' ? x.indicator : x?.kind === 'flow' && typeof x.metric === 'string' ? x.metric : null;
  const outOf = (x: any): string => typeof x?.output === 'string' ? x.output : '';
  if (idOf(r)) return { indicator: idOf(r)!, params: r.params || {}, op: { output: outOf(r), measure: 'none', margs: {}, by: '', ...blank } };
  if (r?.kind !== 'transform' || !idOf(r.of)) return null;
  const m = measureOf(ops, r.fn); if (!m) return null;
  const { by, ...rest } = (r.args || {}) as Record<string, any>;
  let byKey = '';
  if (m.second) {
    if (by?.kind === 'price') byKey = `price:${by.field}`;
    else if (by?.kind === r.of.kind && idOf(by) === idOf(r.of) && JSON.stringify(by.params || {}) === JSON.stringify(r.of.params || {})) byKey = `out:${outOf(by)}`;
    else return null;
  }
  return { indicator: idOf(r.of)!, params: r.of.params || {}, op: { output: outOf(r.of), measure: m.fn, margs: { ...argDefaults(m), ...rest }, by: byKey, ...blank } };
}

/* ---- checks and words --------------------------------------------------------------------------------------- */
/** The problems of an operator before it is sent (refused in place, never rounded; report 9.2): field -> message.
    Fields: 'o.value', 'o.value2', 'o.n', 'o.k' and 'o.a.<arg>'. */
export function opErrors(ops: CatalogOperators, e: Entry, op: OpState, withinMax: number, params?: ParamMap): Record<string, string> {
  const out: Record<string, string> = {}, t = testOf(ops, op.test), m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  const s = seriesOf(e, op.output, params);
  if (!s) out['o.output'] = 'Pick a line of the indicator.';
  else if (!s.drawn && s.why) out['o.output'] = s.why;
  if (op.measure !== 'none' && !m) out['o.measure'] = 'Pick a measure.';
  // a flow series: the measure its output type takes (OPERATORS.md section 4), within the broker sessions (K1)
  if (m && e.flow && s && s.type && m.not_on.includes(s.type))
    out['o.measure'] = `${s.label} ${ops.types[s.type]?.words ?? 'is not of a type this measure takes'}, so ${m.label} is not offered on it; pick another measure or the value itself.`;
  for (const a of m?.args || []) { const msg = paramError(a as EntryParam, op.margs[a.key]); if (msg) out[`o.a.${a.key}`] = `${a.label || a.key}: ${msg}` }
  if (m?.second && !secondOptions(e, op.output, params).some(x => x.key === op.by)) out['o.by'] = 'Pick the series to compare with.';
  if (!t) { out['o.test'] = 'Pick a test.'; return out }
  if (!opsFor(e, op, t, params).includes(op.cmp)) out['o.cmp'] = 'Pick how to compare.';
  if (!testsFor(ops, e, op, params).some(x => x.key === t.key)) out['o.test'] = 'This test is not offered on this series; pick another test or a measure.';
  if (!Number.isFinite(num(op.value))) out['o.value'] = 'Enter a value.';
  if (op.cmp === 'between' || op.cmp === 'outside') {
    if (!Number.isFinite(num(op.value2))) out['o.value2'] = 'Enter the upper value.';
    else if (Number.isFinite(num(op.value)) && num(op.value) > num(op.value2)) out['o.value2'] = 'The upper value must be at least the lower value (right: 2 to 8; wrong: 8 to 2).';
  }
  if (t.within || t.length) {
    const n = num(op.n);
    if (!Number.isInteger(n) || n < 1 || n > withinMax) out['o.n'] = `Enter whole sessions from 1 to ${withinMax}.`;
  }
  if (t.count) {
    const k = num(op.k), n = num(op.n);
    if (!Number.isInteger(k) || k < 1) out['o.k'] = 'Enter a whole number of sessions of at least 1.';
    else if (Number.isInteger(n) && k > n) out['o.k'] = `K of N: K must be at most N (right: 3 of 5; wrong: ${k} of ${n}).`;
  }
  // K1 on a flow series: no field reads more than the broker sessions the Screener holds (nothing fits beyond them);
  // what the setup itself leaves is the worker's to judge (its refusal is shown on the card)
  const S0 = flowSessions(e), arg = sessionArg(m);
  if (S0 != null) {
    const held = (what: string) => `${what}: the Screener holds the last ${S0} sessions of broker data, so no condition on it reads more (right: ${Math.max(1, Math.floor(S0 / 2))}; wrong: ${S0 + 1}).`;
    if ((t.within || t.length) && !out['o.n'] && Number.isFinite(num(op.n)) && num(op.n) > S0) out['o.n'] = held('Sessions');
    if (arg && !out[`o.a.${arg.key}`] && Number.isFinite(Number(op.margs[arg.key])) && Number(op.margs[arg.key]) * perUnit(m) > S0) out[`o.a.${arg.key}`] = held(arg.label || arg.key);
  }
  return out;
}
/** The highest value a session field of the operator takes: within_max (the test's N) or the argument's own maximum,
    and on a flow series at most the broker sessions held (K1; null: the argument's own range only). */
export function fieldMax(ops: CatalogOperators, e: Entry, op: OpState, field: 'n' | 'arg', withinMax: number, _params?: ParamMap): number | null {
  const S0 = flowSessions(e), m = op.measure === 'none' ? undefined : measureOf(ops, op.measure), a = sessionArg(m);
  if (field === 'n') return S0 == null ? withinMax : Math.min(withinMax, S0);
  if (S0 == null || !a) return null;
  const cap = Math.floor(S0 / perUnit(m));
  return a.max != null ? Math.min(a.max, cap) : cap;
}
/** The page's estimate of the most a session field of the operator can be at this setup (the hint it shows; null where
    it has none): the broker sessions the setup leaves, less the other field's. */
export function fieldHint(ops: CatalogOperators, e: Entry, op: OpState, field: 'n' | 'arg', params?: ParamMap): number | null {
  const r = field === 'n' ? testMax(ops, e, op, params) : measureMax(ops, e, op, params);
  return r == null ? null : Math.max(0, r);
}
const v = (x: number | '') => x === '' ? '…' : String(x);
/** The measure in words: "Percentile of its own history (60 sessions)". */
export function measureText(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): string {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure); if (!m) return '';
  // every number argument of a measure is a count of sessions (the catalog's Sessions / Sessions before today)
  const args = m.args.map(a => a.type === 'integer' ? `${op.margs[a.key]} sessions` : optionText(a as EntryParam, op.margs[a.key])).join(', ');
  const name = m.second ? `Compared with ${secondOptions(e, op.output, params).find(s => s.key === op.by)?.label || '…'}` : m.label;
  return `${name}, ${args}`;
}
/** The operator in a column header's few words (catalog `short`): "pctl", "z · 3 in a row", "ever 5", "3 of 5", "rank". */
export function opShort(ops: CatalogOperators, op: OpState): string {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure), t = testOf(ops, op.test);
  const tw = !t?.short ? '' : t.key === 'at_least' ? `${v(op.k)} of ${v(op.n)}` : t.key === 'ever' ? `ever ${v(op.n)}` : t.key === 'streak' ? `${v(op.n)} in a row` : t.short;
  // the comparison too, so two cards that differ only there get two headers (QA5 round 2): "≥90", "50–80", "↑70"
  const cmp = OP_SIGN[op.cmp] ? `${OP_SIGN[op.cmp]}${v(op.value)}` : op.cmp === 'between' ? `${v(op.value)}–${v(op.value2)}` : op.cmp === 'outside' ? `out ${v(op.value)}–${v(op.value2)}`
    : op.cmp === 'crosses_above' ? `↑${v(op.value)}` : op.cmp === 'crosses_below' ? `↓${v(op.value)}` : '';
  return [m?.short, tw, cmp].filter(Boolean).join(' · ');
}
/** The operator's rule in words, after the card's name: "RSI · percentile of its own history (60) ≥ 90". */
export function opText(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): string {
  const all = seriesList(e, params), out = all.find(s => s.key === op.output), line = all.length > 1 ? ` ${out?.label || op.output}` : '';
  const mt = measureText(ops, e, op, params), what = `${line}${mt ? `${line ? ' ·' : ''} ${mt}` : ''}`.trim();
  const sign = OP_SIGN[op.cmp] ? `${OP_SIGN[op.cmp]} ${v(op.value)}` : op.cmp === 'between' ? `between ${v(op.value)} and ${v(op.value2)}` : op.cmp === 'outside' ? `outside ${v(op.value)} to ${v(op.value2)}` : `${OP_WORDS[op.cmp] || op.cmp} ${v(op.value)}`;
  switch (op.test) {
    case 'value': case 'range': return `${what} ${sign}`.trim();
    case 'cross': return `${what} ${sign} within ${v(op.n)} sessions`.trim();
    case 'ever': return `${what} ${sign} at least once in the last ${v(op.n)} sessions`.trim();
    case 'at_least': return `${what} ${sign} on ${v(op.k)} of the last ${v(op.n)} sessions`.trim();
    case 'streak': return `${what} ${sign} for ${v(op.n)} sessions in a row`.trim();
    case 'rank': return `${what ? what + ': ' : ''}rank among the screened stocks ${sign}`;
  }
}
/** The value a cell shows, in the unit of the measured series (or the rank, or the count of a window test). */
export function opValueText(ops: CatalogOperators, e: Entry, op: OpState, x: number | null | undefined, pass: boolean, params?: ParamMap): string {
  if (op.test === 'ever' || op.test === 'at_least' || op.test === 'streak') return `${pass ? 'Yes' : 'No'} · ${x == null ? '—' : nf(x, 0)}/${v(op.n)}`;
  if (x == null || !Number.isFinite(x)) return '—';
  if (op.test === 'rank') return fmtValue(x, 'index');
  const f = opFormat(ops, e, op, params);
  return f === 'sd' ? `${fmtValue(x, 'fraction')}σ` : fmtValue(x, f);
}
/** How the measured series' value is written (format.ts): percent, multiple, percentile (0-100), z (σ), else the
    output's own format (a difference of a price is a price difference). */
export function opFormat(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): ValueFormat | 'sd' {
  const u = resultUnit(ops, e, op, params), out = seriesOf(e, op.output, params);
  if (u === 'percent') return 'pct_signed';
  if (u === 'ratio') return 'multiple';
  if (u === 'percentile') return 'index';
  if (u === 'sd') return 'sd';
  if (u === 'price_change') return 'price_change';
  return out?.fmt ?? 'raw';
}
/** The unit word a value field shows. */
export function opFieldUnit(ops: CatalogOperators, e: Entry, op: OpState, params?: ParamMap): string {
  if (op.test === 'rank' || resultUnit(ops, e, op, params) === 'percentile') return '0–100';
  const f = opFormat(ops, e, op, params);
  return f === 'pct_signed' || f === 'pct' ? '%' : f === 'multiple' ? '×' : f === 'sd' ? 'σ' : '';
}
