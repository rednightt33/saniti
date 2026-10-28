/* The Screener's indicator contract at run time (EXEC-SCREENER; report TARGET ARCHITECTURE 6.8): loads the generated
   screener-registry.json (scripts/build-screener-registry.mjs), checks it against the base registry it was built from,
   and validates an indicator reference's parameters. Parameter rules are never written twice: every value first passes
   the backtest core's resolveParams (unknown key, type, min/max, enum; nothing rounded or clamped), then only the
   screener narrowing is added (report 6.8 rules a-c and the caps): an exclusive minimum, integer-only, a hidden
   parameter, a derived length cap. Narrow-only, so a parameter set the Screener accepts is one the Backtest accepts.
   Worker-side module (imports the backtest core); the page reads the same data from GET /catalog (catalogIndicators)
   and never imports this file (report I1, 9.1). */
import type { Params } from '../../../terminal/src/calc/indicators.ts';
import { BY_ID, REGISTRY_VERSION, ValidationError, resolveParams } from '../../../backtest/src/core/registry.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import type {
  CatalogIndicator, CatalogOutput, CatalogParam, CostClass, DefaultTest, DisabledTestForm, HistoryClass, ParamMap,
  Shape, TestFormSpec,
} from './contract.ts';
import { ScreenerError } from './errors.ts';
import doc from './screener-registry.json' with { type: 'json' };

/* ---- the generated document (field meanings: scripts/build-screener-registry.mjs and report 6.8) -------------- */

/** Why a parameter is narrower than the base: the derived probe, the overlay override, or a user decision on the
    offered options (P17 a), with its evidence. */
export interface Narrowing { rule: 'exclusive_min' | 'integer' | 'options'; source: 'degeneracy_probe' | 'floor_probe' | 'override' | 'decision'; evidence: string }
export interface ScreenerParam {
  key: string; type: 'integer' | 'number' | 'enum' | 'boolean'; label: string | null;
  default: number | string | boolean;   // the registry default, unchanged (narrow-only; is_default compares with it)
  min?: number; max?: number; step?: number;
  options?: string[];                // the offered options: the base's, or a decided subset (narrowing rule 'options')
  start?: string;                    // only where the registry default is not offered: the value a card opens with (P17)
  exclusive_min: boolean;            // the value must be above min (derived degeneracy probe, or an override)
  integer: boolean;                  // whole numbers only (the base type, or the floor probe)
  narrowing: Narrowing[];
  cost_class?: CostClass;            // integer parameters: how the compute grows with the value (decides the cap)
}
/** Units the scaling and shift probes derive (report 6.8): a price level (comparable with close), a price change, a
    volume level or quantity, a product of price and volume, dimensionless (percent, ratio, index), other (EOM, MFI-BW). */
export type Unit = 'price' | 'price_change' | 'volume' | 'price_x_volume' | 'dimensionless' | 'other';
export const UNITS: readonly Unit[] = ['price', 'price_change', 'volume', 'price_x_volume', 'dimensionless', 'other'];
export interface ScreenerOutput {
  key: string; label: string | null; display_unit: string | null;
  unit: Unit; level_comparable: boolean; comparable_with: 'close' | 'volume' | null;
  price_compare_lag: { gt: 0 | 1; lt: 0 | 1 };
  history_class: HistoryClass;
  first_valid_bar: number | null;    // at the start configuration (start_params), on the probe fixture
  inputs: string[];                  // O H L C V needed at the start configuration (poison probe)
  /** enum parameter -> option -> the fields needed with that option and the other parameters at the start
      configuration; [] when the option leaves the output without any value (I43 upper1 / lower1 at bands_mode None). */
  inputs_by_source: Record<string, Record<string, string[]>>;
  tests: TestFormSpec[]; disabled_tests: DisabledTestForm[];
}
export interface OracleRow { output: string; params: ParamMap; table: string; column?: string; expr?: string; columns?: string[] }
export interface ScreenerIndicator {
  id: string; key: string; name: string; category: string; short: string | null; formula_version: string;
  /** one plain-English line (screener-overlay.json): the catalog's tooltip and search text */
  description: string;
  params: ScreenerParam[];
  /** The start configuration, complete: the registry defaults, with each parameter's `start` where the registry default
      is not offered (I43: anchor Week). A new card opens with it and the snapshot pre-warms it (report 6.7); the derived
      fields are measured on it. Equal to the registry defaults wherever default_offered is true. */
  start_params: ParamMap;
  default_offered: boolean;          // false when a registry default is not offered (no "Default" chip; P17 consequence)
  hidden_params: { key: string; reason: string }[];                  // not read by F: hidden, value never shown (rule c)
  fixed_params: { key: string; value: unknown; reason: string }[];   // fixed in the workbook (not a parameter)
  outputs: ScreenerOutput[]; history_class: HistoryClass; cost_class: CostClass;
  overlay: { shape: Shape; synonyms: string[]; default_test: DefaultTest | null };
  probe_params: { params: ParamMap; evidence: string } | null;
  oracle: OracleRow[]; oracle_note: string | null;
}
export interface CostModel { status: string; rule: string; ns_per_bar_length: number; reference_bars: number; evidence: string }
export interface ScreenerRegistryDoc {
  schema_version: number; screener_registry_version: string; registry_version: string; generated_by: string;
  sources: { role: string; file: string; sha256: string }[];
  probe: Record<string, unknown>; cost_model: CostModel; indicators: ScreenerIndicator[];
}

export const SCREENER_REGISTRY = doc as unknown as ScreenerRegistryDoc;
/** sha256(canonical JSON of the generated document without this field)[:16] (report 6.8 Versions). */
export const SCREENER_REGISTRY_VERSION: string = SCREENER_REGISTRY.screener_registry_version;
export const INDICATORS: readonly ScreenerIndicator[] = SCREENER_REGISTRY.indicators;
export const SBY_ID: Readonly<Record<string, ScreenerIndicator>> = Object.fromEntries(INDICATORS.map(r => [r.id, r]));
/** The source files and their hashes when the file was generated. The worker compares those present in its image at
    start (the oracle script is build-only and absent there) and refuses to start on a mismatch (report 6.8 Consumers). */
export const SOURCES = SCREENER_REGISTRY.sources;

/** What disagrees between this file and the base registry the code runs on: another registry_version, an indicator,
    output or parameter that is missing or added, or a range wider than the base (narrow-only). Empty when sound. */
export function registryProblems(): string[] {
  const out: string[] = [];
  if (SCREENER_REGISTRY.registry_version !== REGISTRY_VERSION)
    out.push(`screener-registry.json was built from registry ${SCREENER_REGISTRY.registry_version}, the code runs ${REGISTRY_VERSION}: run npm run registry in apps/edge-bff/screener`);
  const ids = Object.keys(BY_ID);
  for (const id of ids) if (!SBY_ID[id]) out.push(`${id} is missing from screener-registry.json`);
  for (const s of INDICATORS) {
    const b = BY_ID[s.id];
    if (!b) { out.push(`${s.id} is not a base indicator`); continue }
    if (s.key !== b.key || s.outputs.map(o => o.key).join() !== b.outputs.join()) out.push(`${s.id}: key or outputs differ from the base`);
    if (s.params.map(p => p.key).join() !== b.params.map(p => p.key).join()) out.push(`${s.id}: parameters differ from the base`);
    for (const p of s.params) {
      const q = b.params.find(x => x.key === p.key);
      if (q && (p.type !== q.type || p.min !== q.min || p.max !== q.max || p.default !== q.default || (q.type === 'integer' && !p.integer)
        || (q.options && (!p.options?.length || p.options.some(o => !q.options!.includes(o))))))
        out.push(`${s.id}.${p.key}: wider than or different from the base (narrow-only)`);
      const offered = !p.options || p.options.includes(p.default as string);
      if (offered ? p.start !== undefined : !p.options!.includes(p.start as string) || s.start_params?.[p.key] !== p.start)
        out.push(`${s.id}.${p.key}: start must be an offered option exactly when the registry default is not offered`);
    }
    if (s.default_offered !== s.params.every(p => p.start === undefined)) out.push(`${s.id}: default_offered disagrees with its parameters`);
    if (typeof s.description !== 'string' || !s.description.trim()) out.push(`${s.id}: description is missing (screener-overlay.json)`);
  }
  return out;
}
const PROBLEMS = registryProblems();
if (PROBLEMS.length) throw new Error(`screener registry: ${PROBLEMS.join('; ')}`);

/* ---- lookups ---------------------------------------------------------------------------------------------------- */

/** The indicator of a reference, or UNKNOWN_INDICATOR with the allowed ids (from the file, never a list in code). */
export function screenerIndicator(id: unknown, field = 'indicator'): ScreenerIndicator {
  const r = typeof id === 'string' && Object.prototype.hasOwnProperty.call(SBY_ID, id) ? SBY_ID[id] : undefined;
  if (!r) throw new ScreenerError('UNKNOWN_INDICATOR', `${field}: ${JSON.stringify(id)} is not an indicator of the registry; use one of the catalog's indicator ids.`, field, { allowed: Object.keys(SBY_ID) });
  return r;
}
/** One output of an indicator, or INVALID_CONDITION with the outputs it has. */
export function screenerOutput(ind: ScreenerIndicator, output: unknown, field = 'output'): ScreenerOutput {
  const o = ind.outputs.find(x => x.key === output);
  if (!o) throw new ScreenerError('INVALID_CONDITION', `${field}: ${JSON.stringify(output)} is not an output of ${ind.id} ${ind.name}; use one of ${ind.outputs.map(x => x.key).join(', ')}.`, field, { allowed: ind.outputs.map(x => x.key) });
  return o;
}

/** The bar fields (O H L C V) an output needs at resolved parameters (report 6.8 poison probe, "each option's volume
    need"): the union over the indicator's enum parameters of inputs_by_source[key][value], or the output's inputs when
    it has none; [] when one of the chosen options leaves the output without any value (validate.ts refuses such a
    condition). A ticker without one of these fields (IHSG has no volume: an I27 VWMA basis) has no value for reasons
    other than its history, so its NA is NULL_AT_EVALUATION (metrics.ts missingInput, evaluate.ts naReason; TEST PLAN
    10b.3), while the same cell at an SMA basis has a value. */
export type BarField = 'O' | 'H' | 'L' | 'C' | 'V';
export const BAR_FIELDS: readonly BarField[] = ['O', 'H', 'L', 'C', 'V'];
export function inputsOf(output: ScreenerOutput, params: Params): BarField[] {
  const per = Object.entries(output.inputs_by_source).map(([k, byOption]) => byOption[params[k] as string]);
  if (!per.length) return BAR_FIELDS.filter(f => output.inputs.includes(f));
  if (per.some(f => !f || !f.length)) return [];
  return BAR_FIELDS.filter(f => per.some(x => x.includes(f)));
}

/* ---- caps (report 6.8 "Caps") ------------------------------------------------------------------------------------ */

/** The derived cap of an integer parameter whose cost grows with its value (cost_class O(N·n)): the largest value whose
    full-market cold compute stays within capBudgetMs (SCREENER_CAP_BUDGET_MS) on one thread, under the provisional
    cost model of the file (P5). Undefined for an O(N) parameter (its cost does not grow with the value). The same file
    and budget always give the same caps, so a saved screen stays valid across restarts (report 6.8: no start-up
    micro-benchmark). */
export function capOf(p: ScreenerParam, capBudgetMs: number): number | undefined {
  if (p.cost_class !== 'O(N·n)') return undefined;
  if (!(Number.isFinite(capBudgetMs) && capBudgetMs > 0)) throw new RangeError(`capOf: capBudgetMs must be a positive number, not ${capBudgetMs}`);
  const m = SCREENER_REGISTRY.cost_model;
  return Math.floor(capBudgetMs * 1e6 / (m.ns_per_bar_length * m.reference_bars));
}
/** The highest value a parameter accepts: the base max or the derived cap, whichever is lower. */
export function maxOf(p: ScreenerParam, capBudgetMs: number): number | undefined {
  const cap = capOf(p, capBudgetMs);
  return cap === undefined ? p.max : p.max === undefined ? cap : Math.min(p.max, cap);
}
/** The budget's problems: a cap below a parameter's default would refuse the registry defaults (and the snapshot). The
    worker refuses to start with such a SCREENER_CAP_BUDGET_MS. */
export function capProblems(capBudgetMs: number): string[] {
  const out: string[] = [];
  for (const r of INDICATORS) for (const p of r.params) {
    const cap = capOf(p, capBudgetMs);
    if (cap !== undefined && typeof p.default === 'number' && cap < p.default) out.push(`${r.id}.${p.key}: cap ${cap} at ${capBudgetMs} ms is below its default ${p.default}`);
  }
  return out;
}

/* ---- parameters ------------------------------------------------------------------------------------------------- */

export interface ParamOptions { capBudgetMs: number }

const rangeDetails = (p: ScreenerParam, f: string, capBudgetMs: number) => {
  const max = maxOf(p, capBudgetMs);
  return { field: f, ...(p.min !== undefined ? { min: p.min } : {}), ...(max !== undefined ? { max } : {}), exclusive_min: p.exclusive_min, integer: p.integer };
};
const rangeText = (p: ScreenerParam, capBudgetMs: number) => {
  const max = maxOf(p, capBudgetMs), parts: string[] = [];
  if (p.min !== undefined) parts.push(`${p.exclusive_min ? 'above' : 'at least'} ${p.min}`);
  if (max !== undefined) parts.push(`at most ${max}`);
  return `${p.integer ? 'a whole number' : 'a number'}${parts.length ? ' ' + parts.join(' and ') : ''}`;
};

/** The backtest core's refusal of one parameter, translated to a screener refusal (report 8.8): ranges and whole
    numbers to PARAM_OUT_OF_RANGE with {field, min, max, exclusive_min, integer}; an unknown or hidden parameter, a
    wrong type or an option that is not listed to INVALID_CONDITION with the allowed values. */
export function mapCoreError(e: unknown, ind: ScreenerIndicator, field: string, opts: ParamOptions): unknown {
  if (!(e instanceof ValidationError)) return e;
  const key = e.field.startsWith(`${field}.`) ? e.field.slice(field.length + 1) : null;
  const p = key === null ? undefined : ind.params.find(x => x.key === key);
  switch (e.code) {
    case 'PARAM_OUT_OF_RANGE':
      if (p) return new ScreenerError('PARAM_OUT_OF_RANGE', `${e.field} must be ${rangeText(p, opts.capBudgetMs)}.`, e.field, rangeDetails(p, e.field, opts.capBudgetMs));
      break;
    case 'INVALID_PARAM':
      if (p && (p.type === 'integer' || p.type === 'number') && typeof (e as ValidationError).message === 'string' && /whole number/.test(e.message))
        return new ScreenerError('PARAM_OUT_OF_RANGE', `${e.field} must be ${rangeText(p, opts.capBudgetMs)}.`, e.field, rangeDetails(p, e.field, opts.capBudgetMs));
      if (p?.type === 'enum') return new ScreenerError('INVALID_CONDITION', `${e.field} must be one of ${(p.options || []).join(', ')}.`, e.field, { allowed: p.options || [] });
      if (p?.type === 'boolean') return new ScreenerError('INVALID_CONDITION', `${e.field} must be true or false.`, e.field, { allowed: [true, false] });
      if (p) return new ScreenerError('INVALID_CONDITION', `${e.field} must be ${rangeText(p, opts.capBudgetMs)}.`, e.field);
      break;
    case 'PARAM_NOT_ACCEPTED': {
      const hidden = ind.hidden_params.find(h => h.key === key);
      const allowed = ind.params.map(x => x.key);
      return new ScreenerError('INVALID_CONDITION', `${e.field}: ${ind.id} does not accept ${key}${hidden ? ` (${hidden.reason})` : ''}; ${allowed.length ? `use only ${allowed.join(', ')}` : 'it takes no parameter'}.`, e.field, { allowed });
    }
    case 'INVALID_PARAMS':
      return new ScreenerError('INVALID_CONDITION', `${e.field} must be an object of parameters.`, e.field);
    case 'UNKNOWN_INDICATOR':
      return new ScreenerError('UNKNOWN_INDICATOR', e.message, e.field, { allowed: Object.keys(SBY_ID) });
  }
  return new ScreenerError('INVALID_CONDITION', e.message, e.field);
}

/** An indicator reference's parameters, checked and complete (missing ones take the registry default), or a
    ScreenerError naming the field: first the backtest core's resolveParams (one copy of the parameter rules), then the
    screener narrowing: exclusive minimum, whole numbers, the derived cap. Nothing is rounded, clamped or reordered (I7). */
export function resolveScreenerParams(ind: ScreenerIndicator, given: unknown, field: string, opts: ParamOptions): Params {
  let params: Params;
  try { params = resolveParams(BY_ID[ind.id], given, field) }
  catch (e) { throw mapCoreError(e, ind, field, opts) }
  for (const p of ind.params) {
    if (p.type === 'enum' && p.options && !p.options.includes(params[p.key] as string)) {
      // a base option the screener does not offer (P17 a), including a registry default left out of the request
      const f = `${field}.${p.key}`, sent = !!given && typeof given === 'object' && Object.prototype.hasOwnProperty.call(given, p.key);
      throw new ScreenerError('INVALID_CONDITION', `${f}: ${JSON.stringify(params[p.key])} is not offered for ${ind.id} ${ind.name}${sent ? '' : ` (it is the registry default, taken because ${p.key} was left out)`}; use one of ${p.options.join(', ')}.`, f, { allowed: p.options });
    }
    if (p.type !== 'integer' && p.type !== 'number') continue;
    const v = params[p.key] as number, f = `${field}.${p.key}`, max = maxOf(p, opts.capBudgetMs);
    const bad = (p.exclusive_min && p.min !== undefined && !(v > p.min)) || (p.integer && !Number.isInteger(v)) || (max !== undefined && v > max);
    if (bad) {
      const why = p.narrowing.find(n => (n.rule === 'exclusive_min' && p.min !== undefined && !(v > p.min)) || (n.rule === 'integer' && !Number.isInteger(v)));
      throw new ScreenerError('PARAM_OUT_OF_RANGE', `${f} must be ${rangeText(p, opts.capBudgetMs)}${why ? ` (${why.evidence})` : max !== undefined && v > max ? ' (the length cap keeps a full-market computation within the screener budget)' : ''}.`, f, rangeDetails(p, f, opts.capBudgetMs));
    }
  }
  return params;
}

/** The registry defaults of an indicator, complete (resolveParams of {}): what is_default compares with. For an
    indicator whose registry default is not offered (default_offered false, I43) the screener refuses them. */
export function defaultParams(ind: ScreenerIndicator): Params { return resolveParams(BY_ID[ind.id], {}, 'params') }
/** The start configuration (ScreenerIndicator.start_params), checked: what a new card opens with and what the snapshot
    pre-warms for the 53 indicators (report 6.7; I43 at anchor Week, P17). Equals defaultParams where default_offered. */
export function startParams(ind: ScreenerIndicator, opts: ParamOptions): Params { return resolveScreenerParams(ind, ind.start_params, 'start_params', opts) }
/** canonicalJson of resolved parameters: the parameter part of a series key (report 6.7). */
export const paramsKey = (params: Params): string => canonicalJson(params);
/** Whether resolved parameters are the registry defaults (a condition's is_default, report 8.5). */
export const isDefaultParams = (ind: ScreenerIndicator, params: Params): boolean => paramsKey(params) === paramsKey(defaultParams(ind));

/* ---- the catalog view (GET /catalog indicators[], report 8.4) ---------------------------------------------------- */

export function catalogIndicator(ind: ScreenerIndicator, opts: ParamOptions): CatalogIndicator {
  const params: CatalogParam[] = ind.params.map(p => {
    const max = maxOf(p, opts.capBudgetMs);
    return {
      key: p.key, type: p.type, label: p.label, default: p.start ?? p.default,   // the value a card opens with (contract.ts)
      ...(p.min !== undefined ? { min: p.min } : {}), ...(max !== undefined ? { max } : {}),
      exclusive_min: p.exclusive_min, integer: p.integer,
      ...(p.options ? { options: p.options } : {}), ...(p.step !== undefined ? { step: p.step } : {}),
    };
  });
  const outputs: CatalogOutput[] = ind.outputs.map(o => ({
    key: o.key, shape: ind.overlay.shape, tests: o.tests, unit: o.unit, level_comparable: o.level_comparable,
    price_compare_lag: o.price_compare_lag, inputs_by_source: o.inputs_by_source, label: o.label, display_unit: o.display_unit,
    comparable_with: o.comparable_with, disabled_tests: o.disabled_tests, history_class: o.history_class, first_valid_bar: o.first_valid_bar,
  }));
  return {
    id: ind.id, key: ind.key, name: ind.name, category: ind.category, synonyms: ind.overlay.synonyms,
    formula_version: ind.formula_version, params, outputs, history_class: ind.history_class, cost_class: ind.cost_class,
    overlay: { shape: ind.overlay.shape, default_test: ind.overlay.default_test },
    default_offered: ind.default_offered, short: ind.short, description: ind.description,
  };
}
export const catalogIndicators = (opts: ParamOptions): CatalogIndicator[] => INDICATORS.map(r => catalogIndicator(r, opts));
