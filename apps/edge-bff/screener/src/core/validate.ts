/* Refusals of a screen definition (EXEC-SCREENER; report TARGET ARCHITECTURE 6.1 I7, 6.9, 6.12; API CONTRACT 8.5,
   8.8, 8.9). Invalid input is refused with the field and the fix, never clamped, rounded or reordered (I7): the first
   problem is thrown as a ScreenerError (errors.ts) whose `field` is the path in the request body
   ('definition.conditions[2].test.metric.params.length', 'definition.universe.sectors_in[0]') and whose message says
   what to change; details carry the allowed values, the range or the limit (report 8.8):
   - INVALID_INPUT: an unknown field (every object is closed), a wrong JSON type, schema_version other than 1;
   - INVALID_CONDITION: a wrong test shape; between with value > value2 (field value2; value = value2 is accepted); an
     operator or test form the output does not allow (the catalog's tests[].ops); price vs an output that is not
     level_comparable; an output the chosen options leave without any value (registry.ts inputsOf empty: I43 upper1 or
     lower1 at bands_mode None), naming that parameter, so no cell is NA for a reason that is not the ticker's; a within
     that is not a whole number of at least 1; a duplicate or malformed condition id; logic at_least without a whole
     at_least >= 1 (and at_least with another logic); an unknown sector, industry or ticker (refused by name, with the
     allowed list); a value on the left of a comparison (the metric goes left, never reordered);
   - UNKNOWN_INDICATOR / PARAM_OUT_OF_RANGE: through registry.ts (resolveScreenerParams; the backtest core's
     resolveParams first, then the narrowing and the caps) and catalog.ts (transform arguments, pattern and cross-section
     parameters); an enum option the screener does not offer (P17 a: the I43 anchors Session, Decade and Century,
     including Session taken as the registry default when anchor is left out) is INVALID_CONDITION with the offered
     options;
   - METRIC_UNAVAILABLE {metric, availability, reason}: a metric whose availability is not AVAILABLE (derived at run
     time from screener-metrics.json `requires` against the files indexed in state.json; report 6.12) in an enabled
     condition or a metric filter (a switched-off condition is kept and checked for shape only);
   - LIMIT_EXCEEDED {limit, allowed, needed}: more than max_conditions enabled conditions, more than
     max_metric_filters metric filters (VALUE tests only), a within above within_max (a published limit of 8.9, so its
     rule and examples are in catalog.limits[] before the user meets it).
   The valid ids (indicator ids, transform fn, pattern type, flow and cross-section metric, universe attr) are read from
   the generated registry and screener-metrics.json, never from a list in this file (report 6.9). The normalized
   definition has every parameter and argument resolved (defaults filled in; condition.ts builds it from the resolved
   references), the universe with its defaults stated and empty lists left out; definitionHash is taken over it with
   the labels removed (report 8.3), so a request that leaves a default out hashes as one that states it.
   Worker-side module (imports the registry and the backtest core through condition.ts). */
import { canonicalJson, sha256Hex } from '../../../backtest/src/core/hash.ts';
import type {
  Availability, ConditionDef, Definition, Grouping, MetricRef, Side, Test, TestForm, TestKind, UniverseDef, ValueTest,
} from './contract.ts';
import { CONDITION_ID } from './contract.ts';
import { ScreenerError } from './errors.ts';
import { METRICS_CATALOG, PRESETS, metricSpec, resolveCatalogParams, transformSpec } from './catalog.ts';
import type { MetricDefinition, MetricsCatalog, PresetDefinition, TransformDefinition } from './catalog.ts';
import { bindTest } from './condition.ts';
import { resolveIndicator } from './metrics.ts';
import { screenerIndicator, screenerOutput } from './registry.ts';
import type { ScreenerOutput } from './registry.ts';

export type { MetricDefinition, MetricsCatalog, TransformDefinition, PresetDefinition } from './catalog.ts';

/** Availability of a metric at run time (report 6.12): REQUIRES_DECISION when `decision` is set; REQUIRES_DATA when its
    `requires.file` is not in the state.json xsection index or lacks a column (an index entry without a `columns` list
    is not checked for columns: the worker may add the columns of the decoded file to its index first); else AVAILABLE
    (NOT_APPLICABLE is per ticker, from applies_to). reason: a plain sentence naming the file or the decision. */
export function availabilityOf(m: MetricDefinition, index: Readonly<Record<string, { columns?: string[] }>>): { availability: Availability; reason: string | null } {
  if (m.decision) return { availability: 'REQUIRES_DECISION', reason: m.decision };
  if (m.requires) {
    const e = Object.prototype.hasOwnProperty.call(index, m.requires.file) ? index[m.requires.file] : undefined;
    const why = m.unavailable_reason ? `${m.unavailable_reason} ` : '';
    if (!e) return { availability: 'REQUIRES_DATA', reason: `${why}It needs the published file "${m.requires.file}", which this publication does not carry.` };
    const missing = e.columns ? m.requires.columns.filter(c => !e.columns!.includes(c)) : [];
    if (missing.length) return { availability: 'REQUIRES_DATA', reason: `${why}The published file "${m.requires.file}" lacks the column${missing.length > 1 ? 's' : ''} ${missing.join(', ')}.` };
  }
  return { availability: 'AVAILABLE', reason: null };
}
/** availabilityOf for every metric of the catalog, by id (ValidateContext.availability). */
export const availabilityMap = (index: Readonly<Record<string, { columns?: string[] }>>, catalog: MetricsCatalog = METRICS_CATALOG): Map<string, { availability: Availability; reason: string | null }> =>
  new Map(catalog.metrics.map(m => [m.id, availabilityOf(m, index)]));

/** What validation needs besides the definition. limits: the worker's environment values (report 8.9); capBudgetMs:
    SCREENER_CAP_BUDGET_MS (registry.ts caps); tickers: the listed stocks of the snapshot; groupings: catalog.groupings
    (the allowed sector and industry values); metrics: screener-metrics.json; availability: availabilityMap of it
    against the publication's index (a metric missing from the map counts as AVAILABLE). */
export interface ValidateContext {
  limits: { max_conditions: number; max_metric_filters: number; within_max: number };
  capBudgetMs: number;
  tickers: ReadonlySet<string>;
  groupings: readonly Grouping[];
  metrics: MetricsCatalog;
  availability: ReadonlyMap<string, { availability: Availability; reason: string | null }>;
}

/* ---- JSON shape --------------------------------------------------------------------------------------------------- */

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const has = (o: Record<string, unknown>, k: string) => Object.prototype.hasOwnProperty.call(o, k);
function object(x: unknown, field: string, keys: readonly string[], what: string): Record<string, unknown> {
  if (!isObj(x)) throw new ScreenerError('INVALID_INPUT', `${field} must be an object (${what}).`, field);
  for (const k of Object.keys(x)) if (!keys.includes(k))
    throw new ScreenerError('INVALID_INPUT', `${field}.${k} is not a field of ${what}; use only ${keys.join(', ')}.`, `${field}.${k}`, { allowed: [...keys] });
  return x;
}
const finite = (x: unknown, field: string, what = 'a number'): number => {
  if (typeof x !== 'number' || !Number.isFinite(x)) throw new ScreenerError('INVALID_INPUT', `${field} must be ${what}.`, field);
  return x;
};
const bool = (x: unknown, field: string, absent: boolean): boolean => {
  if (x === undefined) return absent;
  if (typeof x !== 'boolean') throw new ScreenerError('INVALID_INPUT', `${field} must be true or false.`, field);
  return x;
};

/* ---- metric references --------------------------------------------------------------------------------------------- */

const REF_KEYS: Record<string, readonly string[]> = {
  indicator: ['kind', 'indicator', 'params', 'output'], price: ['kind', 'field'], transform: ['kind', 'fn', 'of', 'args'],
  pattern: ['kind', 'type', 'params'], flow: ['kind', 'metric', 'params'], xsection: ['kind', 'metric', 'params'], universe: ['kind', 'attr'],
};
/** Every metric reference of a test with its field (transform operands and reference arguments included), outer first. */
function walkRefs(ref: unknown, field: string, visit: (r: MetricRef, field: string) => void): void {
  if (!isObj(ref)) throw new ScreenerError('INVALID_CONDITION', `${field} must be a metric reference {"kind": ...}.`, field);
  const keys = REF_KEYS[ref.kind as string];
  if (!keys) throw new ScreenerError('INVALID_CONDITION', `${field}.kind must be one of ${Object.keys(REF_KEYS).join(', ')}.`, `${field}.kind`, { allowed: Object.keys(REF_KEYS) });
  object(ref, field, keys, `a ${ref.kind} reference`);
  visit(ref as unknown as MetricRef, field);
  if (ref.kind === 'transform') {
    const spec = transformSpec(ref.fn, `${field}.fn`);
    walkRefs(ref.of, `${field}.of`, visit);
    if (ref.args !== undefined && !isObj(ref.args)) throw new ScreenerError('INVALID_CONDITION', `${field}.args must be an object.`, `${field}.args`);
    for (const a of spec.ref_args) if (ref.args && has(ref.args as Record<string, unknown>, a.key)) walkRefs((ref.args as Record<string, unknown>)[a.key], `${field}.args.${a.key}`, visit);
  }
}
/** The catalog entry a reference names (pattern, flow, cross-section, universe), or null (indicator, price, transform). */
function entryOf(r: MetricRef, field: string, catalog: MetricsCatalog): MetricDefinition | null {
  switch (r.kind) {
    case 'pattern': return metricSpec('pattern', r.type, `${field}.type`, catalog);
    case 'flow': return metricSpec('flow', r.metric, `${field}.metric`, catalog);
    case 'xsection': return metricSpec('xsection', r.metric, `${field}.metric`, catalog);
    case 'universe': return metricSpec('universe', r.attr, `${field}.attr`, catalog);
  }
  return null;
}
function checkRef(r: MetricRef, field: string, ctx: ValidateContext, enabled: boolean): void {
  const m = entryOf(r, field, ctx.metrics);
  if (m && enabled) {
    const a = ctx.availability.get(m.id);
    if (a && a.availability !== 'AVAILABLE')
      throw new ScreenerError('METRIC_UNAVAILABLE', `${field}: ${m.label || m.id} is not available: ${a.reason}`, field, { metric: m.id, availability: a.availability, reason: a.reason ?? '' });
  }
  if (r.kind === 'indicator') {
    const ri = resolveIndicator(r, field, { capBudgetMs: ctx.capBudgetMs });
    if (!ri.inputs.length) {
      const key = Object.entries(ri.output.inputs_by_source).find(([k, by]) => !(by[ri.params[k] as string] || []).length)?.[0];
      const f = key ? `${field}.params.${key}` : `${field}.output`;
      throw new ScreenerError('INVALID_CONDITION', `${f}: ${ri.indicator.id} ${ri.output.key} has no value at ${key ? `${key} ${JSON.stringify(ri.params[key])}` : 'these parameters'}; choose another option.`, f,
        key ? { allowed: Object.entries(ri.output.inputs_by_source[key]).filter(([, v]) => v.length).map(([o]) => o) } : undefined);
    }
  }
}

/* ---- test forms (report 6.9.1; the overlay's tests per output) ----------------------------------------------------- */

const formRefusal = (field: string, what: string, allowed?: string[]) =>
  new ScreenerError('INVALID_CONDITION', `${field}: ${what}${allowed && allowed.length ? `; the catalog offers ${allowed.join(', ')}` : ''}.`, field, allowed ? { allowed } : undefined);
/** The output's test form allows the operator (catalog tests[].ops), else INVALID_CONDITION with what it offers. */
function requireForm(out: ScreenerOutput, id: string, form: TestForm, op: string, field: string, withOutput?: string): void {
  const spec = out.tests.find(t => t.form === form && (withOutput === undefined || t.with_output === withOutput));
  const offered = out.tests.flatMap(t => t.ops.map(o => `${t.form} ${o}${t.with_output ? ` with ${t.with_output}` : ''}`));
  const disabled = out.disabled_tests.find(d => d.form === form);
  if (disabled) throw formRefusal(field, `${id}.${out.key} does not offer ${form}: ${disabled.reason}`, offered);
  if (!spec || !spec.ops.includes(op as never)) throw formRefusal(field, `${id}.${out.key} does not offer ${form} with ${op}`, offered);
}
const indOut = (r: { indicator: string; output: string }) => { const ind = screenerIndicator(r.indicator); return { ind, out: screenerOutput(ind, r.output) } };
const sameRef = (a: unknown, b: unknown, ctx: ValidateContext) => {
  try { return canonicalJson(resolveIndicator(a as never, 'a', { capBudgetMs: ctx.capBudgetMs }).ref) === canonicalJson(resolveIndicator(b as never, 'b', { capBudgetMs: ctx.capBudgetMs }).ref) }
  catch { return false }
};
const sameParams = (a: MetricRef, b: MetricRef, ctx: ValidateContext) => {
  const p = (r: MetricRef) => canonicalJson(resolveIndicator(r as never, 'p', { capBudgetMs: ctx.capBudgetMs }).params);
  return p(a) === p(b);
};
function transformAllows(r: MetricRef, kind: TestKind, field: string): void {
  if (r.kind !== 'transform') return;
  const t = transformSpec(r.fn, `${field}.fn`);
  if (!t.tests.includes(kind)) throw formRefusal(field, `the transform ${t.fn} is offered in ${t.tests.join(' or ')} tests, not in a ${kind} test`);
}
function entryAllows(m: MetricDefinition | null, kind: TestKind, field: string): void {
  if (m && !m.tests.includes(kind)) throw formRefusal(field, `${m.id} is offered in ${m.tests.join(' or ')} tests, not in a ${kind} test`);
}
/** VALUE: the metric's form (indicator output 'value'; pct_distance / band_position of an output; a transform, pattern
    or catalog metric by its tests). */
function valueForm(m: MetricRef, op: string, field: string, ctx: ValidateContext): void {
  if (m.kind === 'indicator') { const { ind, out } = indOut(m); requireForm(out, ind.id, 'value', op, field); return }
  if (m.kind === 'transform' && (m.fn === 'pct_distance' || m.fn === 'band_position') && isObj(m.of) && (m.of as MetricRef).kind === 'indicator') {
    const { ind, out } = indOut(m.of as { indicator: string; output: string });
    requireForm(out, ind.id, m.fn === 'pct_distance' ? 'value_pct_distance' : 'value_band_position', op, field);
    return;
  }
  if (m.kind === 'pattern') throw formRefusal(field, 'a pattern is a signal, not a value; use it in a state or event test ({"kind":"state","pattern":...})');
  transformAllows(m, 'value', field);
  entryAllows(entryOf(m, field, ctx.metrics), 'value', field);
}
/** STATE / EVENT comparison: the indicator forms of report 6.9.1 (level, value, output, instance, rising, vs_ma), a
    bar field against a comparable transform or a value, a catalog metric against a value. */
function compareForm(kind: 'state' | 'event', lhs: Side, op: string, rhs: Side, field: string, ctx: ValidateContext): void {
  const isVal = (s: Side) => isObj(s) && !has(s as Record<string, unknown>, 'kind');
  const pre = kind === 'state' ? 'state' : 'event';
  if (isVal(lhs)) throw formRefusal(`${field}.lhs`, 'the left side must be the metric and the right side the value or the second metric (never reordered)');
  const L = lhs as MetricRef, R = rhs as MetricRef;
  if (L.kind === 'pattern' || (!isVal(rhs) && R.kind === 'pattern')) throw formRefusal(field, `a pattern is tested on its own: {"kind":"${kind}", ${kind === 'state' ? '"pattern"' : '"signal": {"pattern"'}: ...}`);
  if (L.kind === 'indicator') {
    const { ind, out } = indOut(L);
    if (isVal(rhs)) return requireForm(out, ind.id, `${pre}_value` as TestForm, op, field);
    if (R.kind === 'indicator') {
      if (R.indicator !== L.indicator) throw formRefusal(`${field}.rhs`, `${ind.id} is compared with its own outputs or a second ${ind.id} instance, not with ${R.indicator}`);
      if (R.output !== L.output) {
        if (!sameParams(L, R, ctx)) throw formRefusal(`${field}.rhs.params`, `${pre}_output compares two outputs of the same instance: give both sides the same parameters`);
        return requireForm(out, ind.id, `${pre}_output` as TestForm, op, field, R.output);
      }
      return requireForm(out, ind.id, `${pre}_instance` as TestForm, op, field);
    }
    if (R.kind === 'transform' && (R.fn === 'lag' || R.fn === 'ma')) {
      if (!sameRef(R.of, L, ctx)) throw formRefusal(`${field}.rhs.of`, `${R.fn} must be taken of the left side itself (the same output and parameters)`);
      if (R.fn === 'lag') { if (kind !== 'state') throw formRefusal(field, 'rising (lag) is a state test'); return requireForm(out, ind.id, 'state_rising', op, field) }
      return requireForm(out, ind.id, `${pre}_vs_ma` as TestForm, op, field);
    }
    if (R.kind === 'price') throw formRefusal(field, `put the price on the left: {"lhs": {"kind":"price","field":"${out.comparable_with || 'close'}"}, "rhs": ${ind.id}.${out.key}}`);
    throw formRefusal(`${field}.rhs`, `${ind.id}.${out.key} is not compared with this reference`);
  }
  if (L.kind === 'price') {
    if (isVal(rhs)) return;                                          // a price level, e.g. close crosses above 1000
    if (R.kind === 'indicator') {
      const { ind, out } = indOut(R);
      if (!out.comparable_with) throw formRefusal(`${field}.rhs`, `${ind.id}.${out.key} is not a level comparable with the price (level_comparable false)`);
      if (L.field !== out.comparable_with) throw formRefusal(`${field}.lhs.field`, `${ind.id}.${out.key} is compared with ${out.comparable_with}`, [out.comparable_with]);
      return requireForm(out, ind.id, `${pre}_level` as TestForm, op, field);
    }
    if (R.kind === 'transform') {
      transformAllows(R, kind, `${field}.rhs`);
      return;                                                        // comparability is checked on the resolved series below
    }
    throw formRefusal(`${field}.rhs`, `the price is compared with an indicator level, a transform of a level or a value`);
  }
  if (!isVal(rhs)) throw formRefusal(`${field}.rhs`, `${L.kind} metrics are compared with a value`);
  if (L.kind === 'transform') {
    const of = L.of as MetricRef;
    if ((L.fn === 'pct_distance' || L.fn === 'band_position') && isObj(of) && of.kind === 'indicator') {
      const { ind, out } = indOut(of as { indicator: string; output: string });
      throw formRefusal(field, `${L.fn} of ${ind.id}.${out.key} is a value test ({"kind":"value"})`);
    }
    return transformAllows(L, kind, `${field}.lhs`);
  }
  entryAllows(entryOf(L, `${field}.lhs`, ctx.metrics), kind, `${field}.lhs`);
}

/* ---- tests ----------------------------------------------------------------------------------------------------------- */

const VALUE_OPS = ['gt', 'lt', 'between'], STATE_OPS = ['gt', 'lt'], EVENT_OPS = ['crosses_above', 'crosses_below'];
/** One test (a condition card's, a metric filter's or a My metric's), normalized. `enabled` false checks the shape and
    the parameters only (a switched-off condition may name a metric that is not available yet). */
export function validateTest(input: unknown, field: string, ctx: ValidateContext, enabled = true): Test {
  if (!isObj(input)) throw new ScreenerError('INVALID_INPUT', `${field} must be a test object.`, field);
  const kind = input.kind;
  const refs = (ref: unknown, f: string) => walkRefs(ref, f, (r, rf) => checkRef(r, rf, ctx, enabled));
  if (kind === 'value') {
    const t = object(input, field, ['kind', 'metric', 'op', 'value', 'value2'], 'a value test');
    if (!VALUE_OPS.includes(t.op as string)) throw new ScreenerError('INVALID_CONDITION', `${field}.op must be one of ${VALUE_OPS.join(', ')}.`, `${field}.op`, { allowed: VALUE_OPS });
    finite(t.value, `${field}.value`);
    if (t.op === 'between') {
      finite(t.value2, `${field}.value2`, 'a number (the upper bound of between)');
      if ((t.value as number) > (t.value2 as number)) throw new ScreenerError('INVALID_CONDITION', `${field}.value2 must be at least value (${t.value}): between is value <= x <= value2, and the bounds are never swapped.`, `${field}.value2`);
    } else if (has(t, 'value2')) throw new ScreenerError('INVALID_CONDITION', `${field}.value2 is used only with op between; remove it.`, `${field}.value2`);
    refs(t.metric, `${field}.metric`);
    valueForm(t.metric as MetricRef, t.op as string, `${field}.metric`, ctx);
  } else if (kind === 'state') {
    if (has(input, 'pattern')) {
      const t = object(input, field, ['kind', 'pattern'], 'a state pattern test');
      if (!isObj(t.pattern) || t.pattern.kind !== 'pattern') throw new ScreenerError('INVALID_CONDITION', `${field}.pattern must be a pattern reference {"kind":"pattern","type":...}.`, `${field}.pattern`);
      refs(t.pattern, `${field}.pattern`);
      entryAllows(entryOf(t.pattern as unknown as MetricRef, `${field}.pattern`, ctx.metrics), 'state', `${field}.pattern`);
    } else {
      const t = object(input, field, ['kind', 'lhs', 'op', 'rhs'], 'a state test');
      if (!STATE_OPS.includes(t.op as string)) throw new ScreenerError('INVALID_CONDITION', `${field}.op must be one of ${STATE_OPS.join(', ')}.`, `${field}.op`, { allowed: STATE_OPS });
      sides(t, field, refs);
      compareForm('state', t.lhs as Side, t.op as string, t.rhs as Side, field, ctx);
    }
  } else if (kind === 'event') {
    const t = object(input, field, ['kind', 'signal', 'within'], 'an event test');
    const w = t.within;
    if (typeof w !== 'number' || !Number.isInteger(w) || w < 1) throw new ScreenerError('INVALID_CONDITION', `${field}.within must be a whole number of sessions of at least 1 (at most ${ctx.limits.within_max}).`, `${field}.within`);
    if (w > ctx.limits.within_max) throw new ScreenerError('LIMIT_EXCEEDED', `${field}.within is at most ${ctx.limits.within_max} sessions.`, `${field}.within`, { limit: 'within_max', allowed: ctx.limits.within_max, needed: w });
    if (!isObj(t.signal)) throw new ScreenerError('INVALID_CONDITION', `${field}.signal must be a cross {"lhs","op","rhs"} or a pattern {"pattern"}.`, `${field}.signal`);
    const sf = `${field}.signal`;
    if (has(t.signal, 'pattern')) {
      const s = object(t.signal, sf, ['pattern'], 'an event pattern');
      if (!isObj(s.pattern) || s.pattern.kind !== 'pattern') throw new ScreenerError('INVALID_CONDITION', `${sf}.pattern must be a pattern reference {"kind":"pattern","type":...}.`, `${sf}.pattern`);
      refs(s.pattern, `${sf}.pattern`);
      entryAllows(entryOf(s.pattern as unknown as MetricRef, `${sf}.pattern`, ctx.metrics), 'event', `${sf}.pattern`);
    } else {
      const s = object(t.signal, sf, ['lhs', 'op', 'rhs'], 'an event cross');
      if (!EVENT_OPS.includes(s.op as string)) throw new ScreenerError('INVALID_CONDITION', `${sf}.op must be one of ${EVENT_OPS.join(', ')}.`, `${sf}.op`, { allowed: EVENT_OPS });
      sides(s, sf, refs);
      compareForm('event', s.lhs as Side, s.op as string, s.rhs as Side, sf, ctx);
    }
  } else throw new ScreenerError('INVALID_CONDITION', `${field}.kind must be value, state or event.`, `${field}.kind`, { allowed: ['value', 'state', 'event'] });
  // normalize through the binding: every reference resolved (parameters, arguments), and a bar field compared with a
  // transform only where the transform is a level of that field
  if (!enabled) return normalizeTest(input as unknown as Test, field, ctx);   // switched off: never bound, shape and parameters only
  const b = bindTest('v', input as unknown as Test, field, { capBudgetMs: ctx.capBudgetMs, withinMax: ctx.limits.within_max, catalog: ctx.metrics });
  if (b.test.kind === 'state' || b.test.kind === 'event') {
    const s = (b.test.kind === 'state' ? b.test : b.test.signal) as { lhs?: Side; rhs?: Side };
    const lf = s.lhs && (s.lhs as MetricRef).kind === 'price' ? (s.lhs as { field: string }).field : null;
    if (lf && s.rhs && (s.rhs as MetricRef).kind === 'transform') {
      const level = b.series[b.series.length - 1];
      if (!level || level.comparableWith !== lf)
        throw formRefusal(`${field}${b.test.kind === 'event' ? '.signal' : ''}.rhs`, `${level ? level.label : 'the right side'} is not a level comparable with ${lf}${level?.comparableWith ? ` (it is comparable with ${level.comparableWith})` : ''}`);
    }
  }
  return b.test;
}
/** A reference with its parameters and arguments complete, without binding it to a computation (a switched-off
    condition may name a metric that has no data yet, report 6.12). */
function normalizeRef(r: MetricRef, field: string, ctx: ValidateContext): MetricRef {
  switch (r.kind) {
    case 'indicator': return resolveIndicator(r, field, { capBudgetMs: ctx.capBudgetMs }).ref;
    case 'price': return { kind: 'price', field: r.field };
    case 'transform': {
      const spec = transformSpec(r.fn, `${field}.fn`), refKeys = spec.ref_args.map(a => a.key), given = (r.args || {}) as Record<string, unknown>;
      const args: Record<string, unknown> = resolveCatalogParams(spec.args, Object.fromEntries(Object.entries(given).filter(([k]) => !refKeys.includes(k))), `${field}.args`, refKeys);
      for (const k of refKeys) if (has(given, k)) args[k] = normalizeRef(given[k] as MetricRef, `${field}.args.${k}`, ctx);
      return { kind: 'transform', fn: spec.fn, of: normalizeRef(r.of, `${field}.of`, ctx), args } as MetricRef;
    }
    case 'pattern': case 'flow': case 'xsection': {
      const id = r.kind === 'pattern' ? r.type : r.metric, spec = metricSpec(r.kind, id, `${field}.${r.kind === 'pattern' ? 'type' : 'metric'}`, ctx.metrics);
      const params = resolveCatalogParams(spec.params, r.params, `${field}.params`);
      return (r.kind === 'pattern' ? { kind: 'pattern', type: spec.id, params } : { kind: r.kind, metric: spec.id, params }) as MetricRef;
    }
    case 'universe': return { kind: 'universe', attr: metricSpec('universe', r.attr, `${field}.attr`, ctx.metrics).id };
  }
}
function normalizeTest(t: Test, field: string, ctx: ValidateContext): Test {
  const side = (s: Side, f: string): Side => isObj(s) && !has(s as Record<string, unknown>, 'kind') ? { value: (s as { value: number }).value } : normalizeRef(s as MetricRef, f, ctx);
  if (t.kind === 'value') return { kind: 'value', metric: normalizeRef(t.metric, `${field}.metric`, ctx), op: t.op, value: t.value, ...(t.op === 'between' ? { value2: t.value2 } : {}) };
  if (t.kind === 'state') return 'pattern' in t && t.pattern ? { kind: 'state', pattern: normalizeRef(t.pattern, `${field}.pattern`, ctx) as never }
    : { kind: 'state', lhs: side((t as { lhs: Side }).lhs, `${field}.lhs`), op: (t as { op: 'gt' | 'lt' }).op, rhs: side((t as { rhs: Side }).rhs, `${field}.rhs`) };
  const s = t.signal as { pattern?: MetricRef; lhs?: Side; op?: 'crosses_above' | 'crosses_below'; rhs?: Side };
  return s.pattern ? { kind: 'event', signal: { pattern: normalizeRef(s.pattern, `${field}.signal.pattern`, ctx) as never }, within: t.within }
    : { kind: 'event', signal: { lhs: side(s.lhs!, `${field}.signal.lhs`), op: s.op!, rhs: side(s.rhs!, `${field}.signal.rhs`) }, within: t.within };
}
function sides(t: Record<string, unknown>, field: string, refs: (ref: unknown, f: string) => void): void {
  for (const k of ['lhs', 'rhs'] as const) {
    const s = t[k], f = `${field}.${k}`;
    if (isObj(s) && !has(s, 'kind')) { object(s, f, ['value'], 'a value side'); finite(s.value, `${f}.value`); continue }
    refs(s, f);
  }
}

/* ---- the universe ---------------------------------------------------------------------------------------------------- */

const UNIVERSE_KEYS = ['security_types', 'sectors_in', 'sectors_out', 'industries_in', 'industries_out', 'include_unclassified', 'price_min',
  'adv20_min_idr', 'min_history_bars', 'traded_on_eval_date', 'exclude_price_breaks', 'tickers', 'metric_filters'] as const;
function stringList(x: unknown, field: string, allowed: readonly string[], what: string): string[] {
  if (!Array.isArray(x)) throw new ScreenerError('INVALID_INPUT', `${field} must be a list of ${what}.`, field);
  const seen = new Set<string>();
  x.forEach((v, i) => {
    const f = `${field}[${i}]`;
    if (typeof v !== 'string') throw new ScreenerError('INVALID_INPUT', `${f} must be a string.`, f);
    if (!allowed.includes(v)) throw new ScreenerError('INVALID_CONDITION', `${f}: ${JSON.stringify(v)} is not ${what === 'tickers' ? 'a listed stock' : `a ${what.replace(/s$/, '')} of the reference file`}; use one of the catalog's values.`, f, { allowed: [...allowed] });
    if (seen.has(v)) throw new ScreenerError('INVALID_CONDITION', `${f}: ${v} is listed twice; list it once.`, f);
    seen.add(v);
  });
  return x as string[];
}
const bound = (x: unknown, field: string, integer: boolean, min: number): number | null => {
  if (x === undefined || x === null) return null;
  if (typeof x !== 'number' || !Number.isFinite(x)) throw new ScreenerError('INVALID_INPUT', `${field} must be a number or null.`, field);
  if ((integer && !Number.isInteger(x)) || x < min)
    throw new ScreenerError('PARAM_OUT_OF_RANGE', `${field} must be ${integer ? 'a whole number' : 'a number'} of at least ${min}, or null for no bound.`, field, { field, min, integer });
  return x;
};
/** The universe block, normalized (contract.ts UniverseDef; P15 classification values from the groupings). The P4 chips
    traded_on_eval_date and exclude_price_breaks are true when absent (report 8.5 "Default true") and include_unclassified
    false; a present value that is not a boolean is INVALID_INPUT. The normalized block always holds security_types,
    the three booleans, the three bounds (null for none) and tickers (null for all); the include and exclude lists and
    metric_filters only when not empty (the page leaves empty ones out). So the definition hash of a request that leaves
    a default out equals that of one that states it. */
export function validateUniverse(input: unknown, field: string, ctx: ValidateContext): UniverseDef {
  const u = object(input, field, UNIVERSE_KEYS, 'the universe');
  if (u.security_types !== undefined) {
    if (!Array.isArray(u.security_types) || u.security_types.length !== 1 || u.security_types[0] !== 'stock')
      throw new ScreenerError('INVALID_CONDITION', `${field}.security_types must be ["stock"]: stocks are the only security type today (P15).`, `${field}.security_types`, { allowed: ['stock'] });
  }
  const values = (key: 'sector' | 'industry') => ctx.groupings.find(g => g.key === key)?.values.map(v => v.value) ?? [];
  const out: UniverseDef = { security_types: ['stock'] };
  for (const [k, g] of [['sectors_in', 'sector'], ['sectors_out', 'sector'], ['industries_in', 'industry'], ['industries_out', 'industry']] as const) {
    if (u[k] === undefined) continue;
    const list = stringList(u[k], `${field}.${k}`, values(g), g === 'sector' ? 'sectors' : 'industries');
    if (list.length) out[k] = [...list];
  }
  out.include_unclassified = bool(u.include_unclassified, `${field}.include_unclassified`, false);
  out.price_min = bound(u.price_min, `${field}.price_min`, false, 0);
  out.adv20_min_idr = bound(u.adv20_min_idr, `${field}.adv20_min_idr`, false, 0);
  out.min_history_bars = bound(u.min_history_bars, `${field}.min_history_bars`, true, 1);
  out.traded_on_eval_date = bool(u.traded_on_eval_date, `${field}.traded_on_eval_date`, true);
  out.exclude_price_breaks = bool(u.exclude_price_breaks, `${field}.exclude_price_breaks`, true);
  out.tickers = u.tickers === undefined || u.tickers === null ? null : [...stringList(u.tickers, `${field}.tickers`, [...ctx.tickers], 'tickers')];
  if (u.metric_filters !== undefined) {
    if (!Array.isArray(u.metric_filters)) throw new ScreenerError('INVALID_INPUT', `${field}.metric_filters must be a list of value tests.`, `${field}.metric_filters`);
    const max = ctx.limits.max_metric_filters;
    if (u.metric_filters.length > max)
      throw new ScreenerError('LIMIT_EXCEEDED', `${field}.metric_filters holds at most ${max} filters; remove ${u.metric_filters.length - max}.`, `${field}.metric_filters`, { limit: 'max_metric_filters', allowed: max, needed: u.metric_filters.length });
    const filters = u.metric_filters.map((t, i) => {
      const f = `${field}.metric_filters[${i}]`;
      if (!isObj(t) || t.kind !== 'value') throw new ScreenerError('INVALID_CONDITION', `${f} must be a value test ({"kind":"value", ...}): metric filters are values at the evaluation bar.`, `${f}.kind`, { allowed: ['value'] });
      return validateTest(t, f, ctx) as ValueTest;
    });
    if (filters.length) out.metric_filters = filters;
  }
  return out;
}

/* ---- the definition -------------------------------------------------------------------------------------------------- */

const LOGICS = ['all', 'any', 'at_least'];
const LABEL_MAX = 120;
/** The whole definition, normalized (rules above), or the first ScreenerError. `field` is the path of the definition
    in the request body ('definition'). */
export function validateDefinition(input: unknown, ctx: ValidateContext, field = 'definition'): Definition {
  const d = object(input, field, ['universe', 'conditions', 'logic', 'at_least'], 'a screen definition');
  if (d.universe === undefined) throw new ScreenerError('INVALID_INPUT', `${field}.universe is required.`, `${field}.universe`);
  const universe = validateUniverse(d.universe, `${field}.universe`, ctx);
  if (!Array.isArray(d.conditions)) throw new ScreenerError('INVALID_INPUT', `${field}.conditions must be a list (empty lists the universe).`, `${field}.conditions`);
  const ids = new Set<string>();
  const enabled = d.conditions.filter(c => isObj(c) && c.enabled === true).length;
  if (enabled > ctx.limits.max_conditions)
    throw new ScreenerError('LIMIT_EXCEEDED', `${field}.conditions: at most ${ctx.limits.max_conditions} enabled conditions; switch off or remove ${enabled - ctx.limits.max_conditions}.`, `${field}.conditions`, { limit: 'max_conditions', allowed: ctx.limits.max_conditions, needed: enabled });
  const conditions: ConditionDef[] = d.conditions.map((c, i) => {
    const f = `${field}.conditions[${i}]`, x = object(c, f, ['id', 'enabled', 'label', 'test'], 'a condition');
    if (typeof x.id !== 'string' || !CONDITION_ID.test(x.id)) throw new ScreenerError('INVALID_CONDITION', `${f}.id must be 1 to 6 characters of 0-9 and a-z.`, `${f}.id`);
    if (ids.has(x.id)) throw new ScreenerError('INVALID_CONDITION', `${f}.id ${x.id} is used twice; give each condition its own id.`, `${f}.id`);
    ids.add(x.id);
    if (typeof x.enabled !== 'boolean') throw new ScreenerError('INVALID_INPUT', `${f}.enabled must be true or false.`, `${f}.enabled`);
    if (x.label !== undefined && (typeof x.label !== 'string' || x.label.length > LABEL_MAX)) throw new ScreenerError('INVALID_INPUT', `${f}.label must be a text of at most ${LABEL_MAX} characters.`, `${f}.label`);
    if (x.test === undefined) throw new ScreenerError('INVALID_INPUT', `${f}.test is required.`, `${f}.test`);
    const test = validateTest(x.test, `${f}.test`, ctx, x.enabled);
    return { id: x.id, enabled: x.enabled, ...(x.label !== undefined ? { label: x.label as string } : {}), test };
  });
  if (!LOGICS.includes(d.logic as string)) throw new ScreenerError('INVALID_CONDITION', `${field}.logic must be one of ${LOGICS.join(', ')}.`, `${field}.logic`, { allowed: LOGICS });
  const out: Definition = { universe, conditions, logic: d.logic as Definition['logic'] };
  if (d.logic === 'at_least') {
    const k = d.at_least;
    if (typeof k !== 'number' || !Number.isInteger(k) || k < 1) throw new ScreenerError('INVALID_CONDITION', `${field}.at_least must be a whole number of at least 1 with logic at_least (above the enabled count it means all).`, `${field}.at_least`);
    out.at_least = k;
  } else if (d.at_least !== undefined) throw new ScreenerError('INVALID_CONDITION', `${field}.at_least is used only with logic at_least; remove it.`, `${field}.at_least`);
  return out;
}

/** The definition without condition labels (a label never changes a number, so it never changes the hash). */
export function withoutLabels(d: Definition): Definition {
  return { ...d, conditions: d.conditions.map(({ label: _label, ...c }) => c) };
}
/** definition_hash (report 8.3): sha256 hex of canonicalJson (backtest core hash.ts) of the normalized definition with
    labels removed. The result cache, counts and saved items key on it (report 8.6, 8.10). */
export const definitionHash = (normalized: Definition): Promise<string> => sha256Hex(canonicalJson(withoutLabels(normalized)));

/* ---- presets (report 6.12 "Presets") ------------------------------------------------------------------------------- */

/** A preset's availability at run time: AVAILABLE only when every enabled leg (and metric filter) is; otherwise
    REQUIRES_DECISION when a leg waits for a decision, else REQUIRES_DATA, with the unavailable legs (condition ids, and
    `metric_filters[i]` for a filter) and a reason naming them. A preset never runs with a leg removed (report 6.12). */
export function presetAvailability(p: PresetDefinition, availability: ReadonlyMap<string, { availability: Availability; reason: string | null }>, catalog: MetricsCatalog = METRICS_CATALOG): { availability: Availability; reason: string | null; unavailable_legs: string[] } {
  const legs: { leg: string; metric: string; a: Availability; reason: string | null }[] = [];
  const look = (leg: string, test: unknown) => {
    const visit = (r: MetricRef) => {
      const id = r.kind === 'pattern' ? r.type : r.kind === 'flow' || r.kind === 'xsection' ? r.metric : r.kind === 'universe' ? r.attr : null;
      const m = id === null ? undefined : catalog.metrics.find(x => x.kind === r.kind && x.id === id);
      const a = m ? availability.get(m.id) : undefined;
      if (m && a && a.availability !== 'AVAILABLE') legs.push({ leg, metric: m.label || m.id, a: a.availability, reason: a.reason });
    };
    const each = (x: unknown) => { if (isObj(x) && typeof x.kind === 'string' && REF_KEYS[x.kind]) { visit(x as unknown as MetricRef); if (x.kind === 'transform') { each(x.of); if (isObj(x.args)) Object.values(x.args).forEach(each) } } };
    const t = test as Record<string, unknown>;
    if (!isObj(t)) return;
    each(t.metric); each(t.lhs); each(t.rhs); each(t.pattern);
    if (isObj(t.signal)) { each(t.signal.lhs); each(t.signal.rhs); each(t.signal.pattern) }
  };
  for (const c of p.definition.conditions) if (c.enabled) look(c.id, c.test);
  (p.definition.universe.metric_filters || []).forEach((t, i) => look(`metric_filters[${i}]`, t));
  if (!legs.length) return { availability: 'AVAILABLE', reason: null, unavailable_legs: [] };
  const availabilityOut: Availability = legs.some(l => l.a === 'REQUIRES_DECISION') ? 'REQUIRES_DECISION' : legs.some(l => l.a === 'REQUIRES_DATA') ? 'REQUIRES_DATA' : 'NOT_APPLICABLE';
  const unavailable_legs = [...new Set(legs.map(l => l.leg))];
  const reason = `Not available: ${legs.map(l => `${l.leg} (${l.metric}): ${l.reason}`).join(' ')}`;
  return { availability: availabilityOut, reason, unavailable_legs };
}
/** The presets of presets.json (catalog.ts PRESETS). */
export const presetDefinitions = (): readonly PresetDefinition[] => PRESETS.presets;
