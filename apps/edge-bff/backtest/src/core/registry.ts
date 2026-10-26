/* The backtest indicator registry (backtest-registry.json, built by apps/backtest-worker/scripts/build-registry.mjs) and
   the checks a request's indicator parameters must pass before anything is calculated. The calculation itself is the
   Terminal's module (F), so the chart, the page's preview and the worker share one formula per indicator.
   Pure module: no DOM and no Node API, so the page (Vite) and the worker (Node, type stripping) import the same file. */
import { F } from '../../../terminal/src/calc/indicators.ts';
import type { Bars, Out, Params } from '../../../terminal/src/calc/indicators.ts';
import doc from './backtest-registry.json' with { type: 'json' };

export interface RegistryParam {
  key: string; type: 'integer' | 'number' | 'enum' | 'boolean'; default: unknown;
  min?: number; max?: number; step?: number; options?: string[]; workbook_default?: unknown;
}
export interface RegistryIndicator {
  id: string; key: string; name: string; category: string; function: string; inputs: string[];
  price_input: 'close' | 'volume'; outputs: string[]; params: RegistryParam[];
  not_accepted: { key: string; value: unknown; reason: string }[]; available_for_backtest: boolean;
}
export interface RegistryDoc {
  schema_version: number; registry_version: string; generated_by: string;
  sources: { file: string; sha256: string }[]; indicators: RegistryIndicator[];
}

export const REGISTRY = doc as unknown as RegistryDoc;
export const BY_ID: Record<string, RegistryIndicator> = Object.fromEntries(REGISTRY.indicators.map(r => [r.id, r]));

/** Content hash of the two sources the registry is built from (indRegistry.json and indicators.ts), written by the
    generator; the worker re-checks it against the files at start, so a stale artifact cannot run. */
export const REGISTRY_VERSION: string = REGISTRY.registry_version;

export class ValidationError extends Error {
  code: string; field: string;
  constructor(code: string, field: string, message: string) { super(message); this.code = code; this.field = field }
}

/** The indicator of a condition, or a ValidationError naming the field. */
export function indicator(id: unknown, field = 'indicator'): RegistryIndicator {
  const r = typeof id === 'string' ? BY_ID[id] : undefined;
  if (!r) throw new ValidationError('UNKNOWN_INDICATOR', field, `${field}: ${JSON.stringify(id)} is not an indicator of the registry.`);
  if (!r.available_for_backtest) throw new ValidationError('INDICATOR_UNAVAILABLE', field, `${field}: ${r.id} is not available for backtests.`);
  return r;
}

/** The checked parameters with every accepted parameter present (missing ones take the registry default). A parameter
    the registry does not accept, a wrong type, a value outside min/max, an integer with a fraction or an option that
    is not listed is refused; nothing is rounded or clamped silently. */
export function resolveParams(r: RegistryIndicator, given: unknown, field = 'params'): Params {
  if (given !== undefined && (given === null || typeof given !== 'object' || Array.isArray(given)))
    throw new ValidationError('INVALID_PARAMS', field, `${field} must be an object.`);
  const g = (given || {}) as Record<string, unknown>;
  const accepted = new Set(r.params.map(p => p.key));
  for (const k of Object.keys(g)) if (!accepted.has(k)) {
    const why = r.not_accepted.find(n => n.key === k);
    throw new ValidationError('PARAM_NOT_ACCEPTED', `${field}.${k}`, `${r.id} does not accept ${k}${why ? ` (${why.reason})` : ''}.`);
  }
  const out: Params = {};
  for (const p of r.params) {
    const v = has(g, p.key) ? g[p.key] : p.default, f = `${field}.${p.key}`;
    if (p.type === 'integer' || p.type === 'number') {
      if (typeof v !== 'number' || !Number.isFinite(v)) throw new ValidationError('INVALID_PARAM', f, `${f} must be a number.`);
      if (p.type === 'integer' && !Number.isInteger(v)) throw new ValidationError('INVALID_PARAM', f, `${f} must be a whole number.`);
      if (p.min !== undefined && v < p.min) throw new ValidationError('PARAM_OUT_OF_RANGE', f, `${f} must be at least ${p.min}.`);
      if (p.max !== undefined && v > p.max) throw new ValidationError('PARAM_OUT_OF_RANGE', f, `${f} must be at most ${p.max}.`);
    } else if (p.type === 'enum') {
      if (typeof v !== 'string' || !(p.options || []).includes(v)) throw new ValidationError('INVALID_PARAM', f, `${f} must be one of ${(p.options || []).join(', ')}.`);
    } else if (p.type === 'boolean') {
      if (typeof v !== 'boolean') throw new ValidationError('INVALID_PARAM', f, `${f} must be true or false.`);
    }
    out[p.key] = v as Params[string];
  }
  return out;
}
const has = (o: object, key: string) => Object.prototype.hasOwnProperty.call(o, key);

/** One indicator's outputs on the bars, with checked parameters. */
export function calculate(r: RegistryIndicator, bars: Bars, params: Params): Out {
  return F[r.key](bars, params);
}
