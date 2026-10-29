/* The non-indicator metric catalog at run time (EXEC-SCREENER; report TARGET ARCHITECTURE 6.9 "Metric references",
   6.12 "Availability is derived at run time"): loads the hand-kept src/core/screener-metrics.json (transform functions
   with their argument ranges, pattern / cross-section / universe / flow / fundamental metrics with the Feature_Catalog
   fields, the periods block of P23 a) and src/core/presets.json (the presets as data), checks them at import (as
   registry.ts checks the generated registry), and gives the lookups the rest of the core uses. The valid transform
   `fn`, pattern `type`, cross-section and flow `metric` and universe `attr` values are read from here, never from a list
   in code (report 6.9); transforms.ts implements what each fn and pattern type computes, and catalogProblems() fails
   when the two disagree.
   Worker-side module (the page reads the same entries from GET /catalog and never imports this file). */
import type { CatalogParam, Definition, MetricKind, ParamMap, ParamValue, Periods, PriceField, SavedView, TestKind } from './contract.ts';
import { ScreenerError } from './errors.ts';
import metricsDoc from './screener-metrics.json' with { type: 'json' };
import presetsDoc from './presets.json' with { type: 'json' };

/* ---- the documents ---------------------------------------------------------------------------------------------- */

/** A catalog parameter (contract.ts CatalogParam), with an optional source of its options when they come from data
    (the broker list of a Phase 2 flow metric). */
export type MetricParam = CatalogParam & { options_source?: string };

/** One transform function (report 6.9): its scalar arguments with ranges and defaults, the arguments that take a metric
    reference (ratio's denominator `by`), the test kinds a condition may use it in, and, for the rolling windows over a
    bar field, the comparison lag as the right side of a bar-field comparison (derived by the generator's lag probe and
    re-derived by tests/core/catalog.test.ts). */
export interface TransformDefinition {
  fn: string; label: string;
  args: MetricParam[];
  ref_args: { key: string; label: string }[];
  tests: TestKind[];
  formula: string; interpretation: string; misuse: string; evidence: string;
  compare_lag?: Partial<Record<PriceField, { gt: 0 | 1; lt: 0 | 1 }>>;
}

/** One entry of src/core/screener-metrics.json (report 6.12): the non-indicator metrics (transform-based metrics,
    patterns, cross-section, flow, universe attributes, the fundamental metrics) with the Feature_Catalog fields, so
    a later AI onboarding can reuse them. requires: the xsection file and columns the metric reads (null: computed from
    the price snapshot alone); decision: set while the metric waits for a user decision (REQUIRES_DECISION);
    applies_to: a predicate on the reference file, `<Sector|Industry> = <value>` or `!=` (NOT_APPLICABLE elsewhere).
    kind: the reference kind a condition on it uses (contract.ts CatalogMetric; a fundamental is kind 'universe', group
    'Fundamental'). Additive fields the page reads (report 9.2; tests/fixture/api.ts has the same shape): label, short,
    default_test, synonyms, and `ref`, the reference template of a transform-based metric (hi52 is
    pct_distance(rolling_max(high, 252))). unavailable_reason: the plain sentence availabilityOf gives while the metric is
    not AVAILABLE; fl: the FLOW INDICATOR PROPOSALS id of a flow metric. */
export interface MetricDefinition {
  id: string; group: string; kind: MetricKind;
  params: MetricParam[]; tests: TestKind[]; unit: string | null;
  formula: string; interpretation: string; misuse: string; evidence: string;
  requires: { file: string; columns: string[] } | null;
  decision: string | null;
  applies_to: string | null;
  label?: string; short?: string; synonyms?: string[];
  default_test?: { op?: string; test?: TestKind; value?: number; value2?: number; within?: number };
  ref?: unknown;
  unavailable_reason?: string;
  fl?: string;
}
export interface MetricsCatalog {
  schema_version: number; note?: string; cost_note?: string;
  periods: Periods;
  transforms: TransformDefinition[];
  metrics: MetricDefinition[];
}
/** One preset of src/core/presets.json (report 6.12 "Presets"; APPENDIX A.2): the prototype's presets remapped onto
    the registry and the catalog. Availability, the unavailable legs and the match / near counts are derived at run time
    (validate.ts presetAvailability; the worker's snapshot), never stored. */
export interface PresetDefinition {
  id: string; category: string; name: string; why: string; definition: Definition;
  /** the table's default sort when the preset opens (the prototype's per-preset sort), sent in the catalog as is */
  view?: SavedView;
}
/** The keys a preset's view.sort may name besides 'c:<condition id>' (the page's result columns). */
export const VIEW_SORT_COLUMNS: readonly string[] = ['match', 'sym', 'last', 'd1', 'adv'];
export interface PresetsDoc { schema_version: number; note?: string; presets: PresetDefinition[] }

export const METRICS_CATALOG = metricsDoc as unknown as MetricsCatalog;
export const PRESETS = presetsDoc as unknown as PresetsDoc;
export const TRANSFORM_FNS: readonly string[] = METRICS_CATALOG.transforms.map(t => t.fn);

/* ---- lookups ------------------------------------------------------------------------------------------------------ */

/** The transform function of a reference, or INVALID_CONDITION with the allowed functions (from the file). */
export function transformSpec(fn: unknown, field: string): TransformDefinition {
  const t = METRICS_CATALOG.transforms.find(x => x.fn === fn);
  if (!t) throw new ScreenerError('INVALID_CONDITION', `${field}: ${JSON.stringify(fn)} is not a transform; use one of ${TRANSFORM_FNS.join(', ')}.`, field, { allowed: [...TRANSFORM_FNS] });
  return t;
}
/** The catalog entry of a metric of one kind (pattern type, cross-section or flow metric, universe attr), or
    INVALID_CONDITION with the ids of that kind. */
export function metricSpec(kind: MetricKind, id: unknown, field: string, catalog: MetricsCatalog = METRICS_CATALOG): MetricDefinition {
  const m = catalog.metrics.find(x => x.kind === kind && x.id === id && !x.ref);
  if (!m) {
    const allowed = catalog.metrics.filter(x => x.kind === kind && !x.ref).map(x => x.id);
    throw new ScreenerError('INVALID_CONDITION', `${field}: ${JSON.stringify(id)} is not a ${kind} metric of the catalog; use one of ${allowed.join(', ')}.`, field, { allowed });
  }
  return m;
}
export const metricById = (id: string, catalog: MetricsCatalog = METRICS_CATALOG): MetricDefinition | undefined => catalog.metrics.find(x => x.id === id);

/* ---- parameters --------------------------------------------------------------------------------------------------- */

const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const range = (p: MetricParam) => {
  const parts: string[] = [];
  if (p.min !== undefined) parts.push(`${p.exclusive_min ? 'above' : 'at least'} ${p.min}`);
  if (p.max !== undefined) parts.push(`at most ${p.max}`);
  return `${p.integer ? 'a whole number' : 'a number'}${parts.length ? ' ' + parts.join(' and ') : ''}`;
};
/** Catalog parameters (or transform arguments) checked and complete, missing ones taking their default; never rounded,
    clamped or adjusted (I7). Unknown key or wrong type or option -> INVALID_CONDITION with the allowed values; a number
    outside its range or not whole where it must be -> PARAM_OUT_OF_RANGE {field, min, max, exclusive_min, integer}.
    `skip` names keys checked elsewhere (a reference argument). */
export function resolveCatalogParams(specs: readonly MetricParam[], given: unknown, field: string, skip: readonly string[] = []): ParamMap {
  if (given !== undefined && !isObj(given)) throw new ScreenerError('INVALID_CONDITION', `${field} must be an object of parameters.`, field);
  const g = (given || {}) as Record<string, unknown>, out: ParamMap = {}, keys = specs.map(p => p.key);
  for (const k of Object.keys(g)) if (!keys.includes(k) && !skip.includes(k))
    throw new ScreenerError('INVALID_CONDITION', `${field}.${k}: not a parameter here; ${keys.length ? `use only ${keys.join(', ')}` : 'it takes no parameter'}.`, `${field}.${k}`, { allowed: keys });
  for (const p of specs) {
    const f = `${field}.${p.key}`, v = Object.prototype.hasOwnProperty.call(g, p.key) ? g[p.key] : p.default;
    if (p.type === 'enum') {
      if (typeof v !== 'string' || (p.options && !p.options.includes(v)))
        throw new ScreenerError('INVALID_CONDITION', `${f} must be one of ${(p.options || []).join(', ') || p.options_source}.`, f, { allowed: p.options || [] });
    } else if (p.type === 'boolean') {
      if (typeof v !== 'boolean') throw new ScreenerError('INVALID_CONDITION', `${f} must be true or false.`, f, { allowed: [true, false] });
    } else {
      const details = { field: f, ...(p.min !== undefined ? { min: p.min } : {}), ...(p.max !== undefined ? { max: p.max } : {}), exclusive_min: p.exclusive_min, integer: p.integer };
      if (typeof v !== 'number' || !Number.isFinite(v)) throw new ScreenerError('INVALID_CONDITION', `${f} must be ${range(p)}.`, f);
      if ((p.integer && !Number.isInteger(v)) || (p.min !== undefined && (p.exclusive_min ? !(v > p.min) : !(v >= p.min))) || (p.max !== undefined && v > p.max))
        throw new ScreenerError('PARAM_OUT_OF_RANGE', `${f} must be ${range(p)}.`, f, details);
    }
    out[p.key] = v as ParamValue;
  }
  return out;
}
export const catalogDefaults = (specs: readonly MetricParam[]): ParamMap => Object.fromEntries(specs.map(p => [p.key, p.default]));

/* ---- applies_to (report 6.12: bank metrics NOT_APPLICABLE outside Banks) ------------------------------------------ */

const PREDICATE = /^(Sector|Industry) (=|!=) (.+)$/;
/** Whether a metric applies to a ticker of the reference file: `Industry = Banks` keeps the banks only, `Sector !=
    Financials` leaves the Financials out; null applies everywhere. A ticker without that classification (unclassified,
    P15) is outside an `=` predicate and inside a `!=` one. */
export function appliesTo(predicate: string | null, row: { sector: string | null; industry: string | null }): boolean {
  if (predicate === null) return true;
  const m = PREDICATE.exec(predicate);
  if (!m) throw new RangeError(`appliesTo: ${JSON.stringify(predicate)} is not a predicate`);
  const v = m[1] === 'Sector' ? row.sector : row.industry;
  return m[2] === '=' ? v === m[3] : v !== m[3];
}

/* ---- checks (asserted at import) ---------------------------------------------------------------------------------- */

const KINDS: readonly MetricKind[] = ['transform', 'pattern', 'flow', 'xsection', 'universe'];
const TEST_KINDS: readonly TestKind[] = ['value', 'state', 'event'];
function paramProblems(where: string, ps: readonly MetricParam[]): string[] {
  const out: string[] = [], seen = new Set<string>();
  for (const p of ps) {
    const w = `${where}.${p.key}`;
    if (seen.has(p.key)) out.push(`${w}: repeated`); seen.add(p.key);
    if (!['integer', 'number', 'enum', 'boolean'].includes(p.type)) out.push(`${w}: type ${p.type}`);
    if (p.integer !== (p.type === 'integer')) out.push(`${w}: integer must say whether the type is integer`);
    if (p.type === 'enum' && !p.options_source && (!p.options?.length || !p.options.includes(p.default as string))) out.push(`${w}: an enum needs options holding its default`);
    if ((p.type === 'integer' || p.type === 'number')) {
      const d = p.default as number;
      if (typeof d !== 'number' || (p.min !== undefined && (p.exclusive_min ? !(d > p.min) : d < p.min)) || (p.max !== undefined && d > p.max) || (p.integer && !Number.isInteger(d)))
        out.push(`${w}: default ${d} is outside its own range`);
    }
  }
  return out;
}
/** Every way screener-metrics.json and presets.json break their rules; empty when sound. `implemented`: the transform
    functions and pattern types transforms.ts computes (passed in to keep this module free of it). */
export function catalogProblems(implemented?: { transforms: readonly string[]; patterns: readonly string[] }): string[] {
  const out: string[] = [], c = METRICS_CATALOG;
  if (c.schema_version !== 1) out.push('screener-metrics.json: schema_version must be 1');
  const pe = c.periods || ({} as Periods);
  if (!(['1M', '3M', '6M', '1Y'] as const).every(k => Number.isInteger(pe[k]) && pe[k] > 0)) out.push('periods must hold whole session counts for 1M, 3M, 6M and 1Y');
  const fns = new Set<string>();
  for (const t of c.transforms) {
    if (fns.has(t.fn)) out.push(`transform ${t.fn}: repeated`); fns.add(t.fn);
    out.push(...paramProblems(`transform ${t.fn}`, t.args));
    if (!t.tests.length || t.tests.some(k => !TEST_KINDS.includes(k))) out.push(`transform ${t.fn}: tests must be a non-empty subset of ${TEST_KINDS}`);
    for (const k of ['formula', 'interpretation', 'misuse', 'evidence'] as const) if (!t[k]) out.push(`transform ${t.fn}: ${k} is required`);
  }
  const ids = new Set<string>();
  for (const m of c.metrics) {
    const w = `metric ${m.id}`;
    if (ids.has(m.id)) out.push(`${w}: repeated id`); ids.add(m.id);
    if (!KINDS.includes(m.kind)) out.push(`${w}: kind ${m.kind}`);
    if (!m.tests.length || m.tests.some(k => !TEST_KINDS.includes(k))) out.push(`${w}: tests must be a non-empty subset of ${TEST_KINDS}`);
    for (const k of ['formula', 'interpretation', 'misuse', 'evidence'] as const) if (!m[k]) out.push(`${w}: ${k} is required`);
    if (m.requires !== null && !(m.requires && typeof m.requires.file === 'string' && m.requires.file && Array.isArray(m.requires.columns) && m.requires.columns.length)) out.push(`${w}: requires must be null or {file, columns}`);
    if (m.applies_to !== null && !PREDICATE.test(m.applies_to)) out.push(`${w}: applies_to must be "<Sector|Industry> = <value>" or "!="`);
    if ((m.requires || m.decision) && !m.unavailable_reason && !m.decision) out.push(`${w}: a metric that can be unavailable needs unavailable_reason`);
    out.push(...paramProblems(w, m.params));
    if (m.kind === 'flow' && !m.params.some(p => p.key === 'window')) out.push(`${w}: a flow metric needs a window parameter (contract FlowRef)`);
    if (m.kind === 'transform' && !m.ref) out.push(`${w}: a transform-based metric needs its reference template (ref)`);
    if (m.kind === 'pattern' && m.tests.includes('value')) out.push(`${w}: a pattern is a signal, never a VALUE`);
  }
  // a fundamental is a universe attribute read from its file (the worker's universe row), never counted here: that the
  // catalog holds every fundamental of APPENDIX C.3 is derived from the prototype's catalogue in tests/core/catalog.test.ts
  for (const m of c.metrics) if (m.group === 'Fundamental' && (m.kind !== 'universe' || !m.requires)) out.push(`metric ${m.id}: a fundamental is kind universe and requires its file`);
  if (implemented) {
    for (const fn of fns) if (!implemented.transforms.includes(fn)) out.push(`transform ${fn} is in the catalog but transforms.ts does not compute it`);
    for (const fn of implemented.transforms) if (!fns.has(fn)) out.push(`transforms.ts computes ${fn}, which the catalog does not list`);
    const types = c.metrics.filter(m => m.kind === 'pattern' && !m.decision).map(m => m.id);
    for (const t of types) if (!implemented.patterns.includes(t)) out.push(`pattern ${t} is offered but transforms.ts does not compute it`);
  }
  const pids = new Set<string>();
  for (const p of PRESETS.presets) {
    if (pids.has(p.id)) out.push(`preset ${p.id}: repeated id`); pids.add(p.id);
    if (!p.name || !p.why || !p.category) out.push(`preset ${p.id}: name, category and why are required`);
    if (!p.definition || !Array.isArray(p.definition.conditions)) out.push(`preset ${p.id}: definition.conditions is required`);
    if (p.view !== undefined) {
      const v = p.view as unknown as Record<string, unknown>, sort = v?.sort as { key?: unknown; dir?: unknown } | undefined;
      const ids = (p.definition?.conditions || []).map(c => `c:${c.id}`);
      if (!v || typeof v !== 'object' || Object.keys(v).some(k => k !== 'sort' && k !== 'show_near')) out.push(`preset ${p.id}: view holds only sort and show_near`);
      else if (v.show_near !== undefined && typeof v.show_near !== 'boolean') out.push(`preset ${p.id}: view.show_near must be true or false`);
      if (sort !== undefined && (typeof sort.key !== 'string' || !(VIEW_SORT_COLUMNS.includes(sort.key) || ids.includes(sort.key)) || (sort.dir !== 'asc' && sort.dir !== 'desc')))
        out.push(`preset ${p.id}: view.sort must be {key, dir} with key one of ${[...VIEW_SORT_COLUMNS, ...ids].join(', ')} and dir asc or desc`);
    }
  }
  return out;
}
const PROBLEMS = catalogProblems();
if (PROBLEMS.length) throw new Error(`screener catalog: ${PROBLEMS.join('; ')}`);
