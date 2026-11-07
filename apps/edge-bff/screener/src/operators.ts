/* The universal operators on the page (EXEC-SCREENER-FLOW-CANDLES P3; verification/screener/OPERATORS.md, approved by
   the user 2026-11-07, K4). A condition with an operator reads one output of the indicator (its "series"), may apply a
   measure to it (a transform: its own average, percentile, change, z-score, a second series, slope, acceleration,
   distance to its high or low) and tests the measured series one way (above or below a value, a range, a cross, ever /
   K of N / in a row, a rank among the screened stocks). Everything offered comes from the catalog's operators block
   (GET /catalog `operators`, from screener-metrics.json, the same block the core checks against): the measures with
   their arguments, ranges and defaults, the tests with their operators, which unit a result has, and which tests a unit
   cannot take (a rank of a price level). The page never decides a rule the worker does not; the worker refuses what
   the page could not know (naming the field). Pure: no DOM. */
import type { CatalogOperators, CatalogOutput, MetricRef, OperatorTestKey, ParamMap, ParamValue, Test, ValueOp } from './core/contract.ts';
import { optionText, paramError, type Entry, type EntryParam } from './entries.ts';
import { formatOfOutput, fmtValue, nf, type ValueFormat } from './format.ts';

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

const outputOf = (e: Entry, key: string): CatalogOutput | undefined => e.indicator?.outputs.find(o => o.key === key);
/** Whether a card on this entry can take an operator: an indicator (its outputs are series) in a catalog that offers
    operators. */
export const offersOperators = (ops: CatalogOperators | undefined, e: Entry | undefined): boolean => !!ops && !!e && e.kind === 'indicator' && !!e.indicator?.outputs.length;
export const measureOf = (ops: CatalogOperators, fn: string): Measure | undefined => ops.measures.find(m => m.fn === fn);
export const testOf = (ops: CatalogOperators, key: string): OpTest | undefined => ops.tests.find(t => t.key === key);
/** the output a new operator opens on: the one the entry's default condition reads, else the first */
export const defaultOutput = (e: Entry): string => e.opts.find(o => o.key === e.def.opt)?.output || e.indicator!.outputs[0].key;
const argDefaults = (m: Measure | undefined): Record<string, ParamValue> => Object.fromEntries((m?.args || []).map(a => [a.key, a.default as ParamValue]));

/** The operator a card opens with: the catalog's default measure on the entry's default output, with the measure's
    default comparison. */
export function defaultOp(ops: CatalogOperators, e: Entry, output = defaultOutput(e)): OpState {
  const m = measureOf(ops, ops.default_measure) ?? ops.measures[0];
  return { output, measure: m.fn, margs: argDefaults(m), by: '', test: 'value', cmp: m.default.cmp, value: m.default.value, value2: '', n: '', k: '' };
}
/** The operator with another measure: its arguments' defaults, then the test (kept when it still applies, else the
    first one offered) with the values that suit the new measure (withTest). */
export function withMeasure(ops: CatalogOperators, e: Entry, op: OpState, fn: string): OpState {
  const m = fn === 'none' ? undefined : measureOf(ops, fn);
  const next: OpState = { ...op, measure: m ? m.fn : 'none', margs: argDefaults(m), by: m?.second ? secondOptions(e, op.output)[0]?.key ?? '' : '', cmp: m?.default.cmp ?? op.cmp };
  const tests = testsFor(ops, e, next);
  return withTest(ops, e, next, tests.some(t => t.key === next.test) ? next.test : tests[0]?.key ?? 'value');
}
/** The thresholds a test opens with on the measured series (QA5 2026-11-07 D3: one range for every measure, and values
    kept from the previous test, gave screens that match nothing): a rank its own (0-100); a range the measure's range
    (catalog default.range) or, on the plain series, the entry's own between bounds, else blank fields to fill in (a
    difference has no scale-free range); any other test the measure's default value, or the entry's own on the plain
    series. Never a value of another measure or test. */
function thresholds(ops: CatalogOperators, e: Entry, op: OpState, t: OpTest): { value: number | ''; value2: number | '' } {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  if (t.key === 'rank') return { value: t.default.value ?? '', value2: t.default.value2 ?? '' };
  if (t.key === 'range') {
    const r = m ? m.default.range : (typeof e.def.value === 'number' && typeof e.def.value2 === 'number' ? [e.def.value, e.def.value2] : undefined);
    return r ? { value: r[0], value2: r[1] } : { value: '', value2: '' };
  }
  return { value: m ? m.default.value : e.def.value, value2: '' };
}
/** The operator with another test: its default fields and the thresholds that suit the measured series (thresholds);
    the comparison kept when the test takes it. */
export function withTest(ops: CatalogOperators, e: Entry, op: OpState, key: string): OpState {
  const t = testOf(ops, key) ?? ops.tests[0], d = t.default || {}, offered = opsFor(e, op, t);
  const cmp = offered.includes(op.cmp) ? op.cmp : d.cmp && offered.includes(d.cmp) ? d.cmp : offered[0] ?? t.ops[0];
  return { ...op, test: t.key, cmp: t.key === 'range' && !['between', 'outside'].includes(cmp) ? 'between' : cmp, ...thresholds(ops, e, op, t),
    n: d.n ?? (t.within || t.length ? op.n || 5 : ''), k: d.k ?? (t.count ? op.k || 3 : '') };
}
/** The operator with another comparison: a range operator (between, outside) on a test that was not one opens with the
    range thresholds, a single-value one after a range with the single default. */
export function withCmp(ops: CatalogOperators, e: Entry, op: OpState, cmp: string): OpState {
  const two = (c: string) => c === 'between' || c === 'outside', t = testOf(ops, op.test);
  if (!t || two(cmp) === two(op.cmp)) return { ...op, cmp };
  const th = thresholds(ops, e, op, two(cmp) ? { ...t, key: 'range' } : { ...t, key: 'value' });
  return { ...op, cmp, ...th };
}

/** The unit of the measured series: a measure's own (fixed, or by its form argument; 'diff' is a difference of the
    series: a price difference for a price level, else the series' unit), else the output's. */
export function resultUnit(ops: CatalogOperators, e: Entry, op: OpState): string {
  const out = outputOf(e, op.output), base = out?.unit || 'other';
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  if (!m) return base;
  const u = typeof m.unit === 'string' ? m.unit : m.unit[String(op.margs[m.unit.by])] ?? 'other';
  return u === 'diff' ? (base === 'price' ? 'price_change' : base) : u;
}
/** a level (a price or volume level of the output, not measured): what the rank test's not_on_levels names */
const isLevel = (e: Entry, op: OpState) => op.measure === 'none' && !!outputOf(e, op.output)?.comparable_with;
/** The overlay forms of an output that the plain series ("The value itself", no measure) is tested through: a value
    test (and a window test, whose inner test is a value test) needs the output's 'value' form, a cross its
    'event_value' form, with the operators those forms list (the core's validate.ts requireForm; ge and le belong to gt
    and lt, outside to between). A measured series is a transform, which the core takes in every test. */
const FORM_OF: Partial<Record<OperatorTestKey, string>> = { value: 'value', range: 'value', ever: 'value', at_least: 'value', streak: 'value', cross: 'event_value' };
const FAMILY: Record<string, string> = { ge: 'gt', le: 'lt', outside: 'between' };
function plainOps(e: Entry, op: OpState, t: OpTest): string[] | null {
  if (op.measure !== 'none' || t.key === 'rank') return null;              // no form needed
  const forms = outputOf(e, op.output)?.tests || [];
  const value = forms.find(x => x.form === FORM_OF[t.key])?.ops as string[] | undefined;
  // a window counts a cross on each session through the output's event_value form (its crosses_above / crosses_below)
  const cross = t.key === 'ever' || t.key === 'at_least' ? forms.find(x => x.form === 'event_value')?.ops as string[] | undefined : undefined;
  return [...(value || []), ...(cross || [])];
}
/** The tests the measured series takes: the rank only on a unit that compares across stocks (the catalog's
    not_on_units and not_on_levels; OPERATORS.md section 4); on the plain series, only the tests its forms offer.
    eq / ne are not offered: no operator result is a whole number (K7: they are for counts). */
export function testsFor(ops: CatalogOperators, e: Entry, op: OpState): OpTest[] {
  const unit = resultUnit(ops, e, op);
  return ops.tests.filter(t => (t.key !== 'rank' || (!(t.not_on_units || []).includes(unit) && !(t.not_on_levels && isLevel(e, op)))) && opsFor(e, op, t).length > 0);
}
/** A test's operators as offered on this series (eq and ne left out, K7; on the plain series the ones its form lists). */
export function opsFor(e: Entry, op: OpState, t: OpTest): string[] {
  const plain = plainOps(e, op, t);
  return opsOf(t).filter(o => plain === null || plain.includes(FAMILY[o] ?? o));
}
export const opsOf = (t: OpTest): string[] => t.ops.filter(o => o !== 'eq' && o !== 'ne');

/** The second series a relative comparison can take on this output: another output of the same indicator with the same
    unit and level, and the bar fields of the same unit (the close against a price level, the volume against a volume
    level). key: 'out:<output>' or 'price:<field>'. */
export function secondOptions(e: Entry, output: string): { key: string; label: string }[] {
  const o = outputOf(e, output); if (!o) return [];
  const outs = (e.indicator?.outputs || []).filter(x => x.key !== output && x.unit === o.unit && x.comparable_with === o.comparable_with)
    .map(x => ({ key: `out:${x.key}`, label: x.label || x.key }));
  const prices = o.comparable_with === 'close' ? ['close', 'open', 'high', 'low'] : o.comparable_with === 'volume' ? ['volume'] : [];
  return [...outs, ...prices.map(f => ({ key: `price:${f}`, label: f.charAt(0).toUpperCase() + f.slice(1) }))];
}
/** The measures offered on this output: every measure of the catalog (an indicator output is never a percentile, a
    z-score or a run: the types of OPERATORS.md section 4 come from the measures themselves), the relative comparison
    only where the output has a second series of its unit. */
export const measuresFor = (ops: CatalogOperators, e: Entry, output: string): Measure[] =>
  ops.measures.filter(m => !m.second || secondOptions(e, output).length > 0);
/** Whether "The value itself" (no measure) is offered on this output: when some test takes the plain series. */
export const plainOffered = (ops: CatalogOperators, e: Entry, output: string): boolean =>
  testsFor(ops, e, { ...defaultOp(ops, e, output), measure: 'none', margs: {} }).length > 0;

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
/** an output, or a measure of one, read back: the indicator, its parameters and the operator's series part */
function read(ops: CatalogOperators, r: any): { indicator: string; params: ParamMap; op: OpState } | null {
  const blank = { test: 'value' as OperatorTestKey, cmp: 'gt', value: '' as const, value2: '' as const, n: '' as const, k: '' as const };
  if (r?.kind === 'indicator') return { indicator: r.indicator, params: r.params || {}, op: { output: r.output, measure: 'none', margs: {}, by: '', ...blank } };
  if (r?.kind !== 'transform' || r.of?.kind !== 'indicator') return null;
  const m = measureOf(ops, r.fn); if (!m) return null;
  const { by, ...rest } = (r.args || {}) as Record<string, any>;
  let byKey = '';
  if (m.second) {
    if (by?.kind === 'price') byKey = `price:${by.field}`;
    else if (by?.kind === 'indicator' && by.indicator === r.of.indicator && JSON.stringify(by.params || {}) === JSON.stringify(r.of.params || {})) byKey = `out:${by.output}`;
    else return null;
  }
  return { indicator: r.of.indicator, params: r.of.params || {}, op: { output: r.of.output, measure: m.fn, margs: { ...argDefaults(m), ...rest }, by: byKey, ...blank } };
}

/* ---- checks and words --------------------------------------------------------------------------------------- */
/** The problems of an operator before it is sent (refused in place, never rounded; report 9.2): field -> message.
    Fields: 'o.value', 'o.value2', 'o.n', 'o.k' and 'o.a.<arg>'. */
export function opErrors(ops: CatalogOperators, e: Entry, op: OpState, withinMax: number): Record<string, string> {
  const out: Record<string, string> = {}, t = testOf(ops, op.test), m = op.measure === 'none' ? undefined : measureOf(ops, op.measure);
  if (!outputOf(e, op.output)) out['o.output'] = 'Pick a line of the indicator.';
  if (op.measure !== 'none' && !m) out['o.measure'] = 'Pick a measure.';
  for (const a of m?.args || []) { const msg = paramError(a as EntryParam, op.margs[a.key]); if (msg) out[`o.a.${a.key}`] = `${a.label || a.key}: ${msg}` }
  if (m?.second && !secondOptions(e, op.output).some(s => s.key === op.by)) out['o.by'] = 'Pick the series to compare with.';
  if (!t) { out['o.test'] = 'Pick a test.'; return out }
  if (!opsFor(e, op, t).includes(op.cmp)) out['o.cmp'] = 'Pick how to compare.';
  if (!testsFor(ops, e, op).some(x => x.key === t.key)) out['o.test'] = 'This test is not offered on this series; pick another test or a measure.';
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
  return out;
}
const v = (x: number | '') => x === '' ? '…' : String(x);
/** The measure in words: "Percentile of its own history (60 sessions)". */
export function measureText(ops: CatalogOperators, e: Entry, op: OpState): string {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure); if (!m) return '';
  // every number argument of a measure is a count of sessions (the catalog's Sessions / Sessions before today)
  const args = m.args.map(a => a.type === 'integer' ? `${op.margs[a.key]} sessions` : optionText(a as EntryParam, op.margs[a.key])).join(', ');
  const name = m.second ? `Compared with ${secondOptions(e, op.output).find(s => s.key === op.by)?.label || '…'}` : m.label;
  return `${name}, ${args}`;
}
/** The operator in a column header's few words (catalog `short`): "pctl", "z · 3 in a row", "ever 5", "3 of 5", "rank". */
export function opShort(ops: CatalogOperators, op: OpState): string {
  const m = op.measure === 'none' ? undefined : measureOf(ops, op.measure), t = testOf(ops, op.test);
  const tw = !t?.short ? '' : t.key === 'at_least' ? `${v(op.k)} of ${v(op.n)}` : t.key === 'ever' ? `ever ${v(op.n)}` : t.key === 'streak' ? `${v(op.n)} in a row` : t.short;
  return [m?.short, tw].filter(Boolean).join(' · ');
}
/** The operator's rule in words, after the card's name: "RSI · percentile of its own history (60) ≥ 90". */
export function opText(ops: CatalogOperators, e: Entry, op: OpState): string {
  const out = outputOf(e, op.output), line = (e.indicator?.outputs.length || 0) > 1 ? ` ${out?.label || op.output}` : '';
  const mt = measureText(ops, e, op), what = `${line}${mt ? `${line ? ' ·' : ''} ${mt}` : ''}`.trim();
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
export function opValueText(ops: CatalogOperators, e: Entry, op: OpState, x: number | null | undefined, pass: boolean): string {
  if (op.test === 'ever' || op.test === 'at_least' || op.test === 'streak') return `${pass ? 'Yes' : 'No'} · ${x == null ? '—' : nf(x, 0)}/${v(op.n)}`;
  if (x == null || !Number.isFinite(x)) return '—';
  if (op.test === 'rank') return fmtValue(x, 'index');
  const f = opFormat(ops, e, op);
  return f === 'sd' ? `${fmtValue(x, 'fraction')}σ` : fmtValue(x, f);
}
/** How the measured series' value is written (format.ts): percent, multiple, percentile (0-100), z (σ), else the
    output's own format (a difference of a price is a price difference). */
export function opFormat(ops: CatalogOperators, e: Entry, op: OpState): ValueFormat | 'sd' {
  const u = resultUnit(ops, e, op), out = outputOf(e, op.output);
  if (u === 'percent') return 'pct_signed';
  if (u === 'ratio') return 'multiple';
  if (u === 'percentile') return 'index';
  if (u === 'sd') return 'sd';
  if (u === 'price_change') return 'price_change';
  return formatOfOutput(out?.unit, out?.display_unit, null);
}
/** The unit word a value field shows. */
export function opFieldUnit(ops: CatalogOperators, e: Entry, op: OpState): string {
  if (op.test === 'rank' || resultUnit(ops, e, op) === 'percentile') return '0–100';
  const f = opFormat(ops, e, op);
  return f === 'pct_signed' || f === 'pct' ? '%' : f === 'multiple' ? '×' : f === 'sd' ? 'σ' : '';
}
