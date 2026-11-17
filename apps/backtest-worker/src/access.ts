/* EDGE multi-user Phase 3b (EXEC-MU-ACCOUNTS; verification/edge_multiuser/access_tiers/CONTRACT.md section 8b, "3b in
   detail"; user go 2026-11-17 "Aman, lanjutkan"): the plan's item grants and limits edge-bff sends in a request's
   context, beside the rights (server.ts rightsOf).

   context.allow  {indicator, flow_indicator, candle_pattern, screener_metric}: each "*" (every id, lab included) or a
                  list of distinct ids (possibly empty), the principal's grants expanded by edge-bff against
                  releases.json. All four kinds are named; any other key, or a value of another shape, is
                  INVALID_CONTEXT. Absent: every item (deploy step 1 of 3b: an edge-bff that does not send it yet keeps
                  today's behaviour; step 3 makes it required).
   context.limits {name: whole number}: a plan's own ceilings, for the worker's per-request limits (LIMIT_KEYS); the
                  worker takes min(its own, the plan's), never more. Absent or {}: the worker's own. Any other name is
                  INVALID_CONTEXT (timeout_seconds, queued_per_owner and window_bars are not per-request limits here).

   An item outside allow is refused 403 CAPABILITY_REQUIRED, field the JSON path of its id, details {kind, id,
   capability} with capability the Backtest's family key (FAMILY). validate.ts checks every item a request names
   (checkConditions, checkRequest, checkSignalsRequest), so /v1/validate, /v1/signals, /v1/jobs and the job's own
   re-check on the job thread (run.ts runJob) all pass through it. Internal calls (tests, the look-ahead gate) leave
   allow out and get ALLOW_ALL; only the HTTP layer (server.ts) reads it. */
import type { Limits } from '../../edge-bff/backtest/src/core/contract.ts';
import { WorkerError, invalid } from './errors.ts';

export const ALLOW_KINDS = ['indicator', 'flow_indicator', 'candle_pattern', 'screener_metric'] as const;
export type AllowKind = (typeof ALLOW_KINDS)[number];
/** The wire form, kept as it is so it crosses to the compute threads unchanged ("*" or the ids). */
export type Allow = Readonly<Record<AllowKind, '*' | readonly string[]>>;
export const ALLOW_ALL: Allow = Object.freeze({ indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*' });

/** The capability family of each kind on the Backtest (CONTRACT 8b families table): a Backtest test condition reads the
    Screener's metrics, so their family is the Screener's. */
export const FAMILY: Readonly<Record<AllowKind, string>> = {
  indicator: 'backtest.indicator', flow_indicator: 'backtest.flow_indicator', candle_pattern: 'backtest.candle_pattern', screener_metric: 'screener.metric',
};
const WORDS: Readonly<Record<AllowKind, string>> = { indicator: 'indicator', flow_indicator: 'Flow indicator', candle_pattern: 'candlestick pattern', screener_metric: 'Screener metric' };

const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);

/** context.allow checked (undefined: ALLOW_ALL), or INVALID_CONTEXT naming the key and the expected shape. */
export function allowOf(v: unknown, field = 'context.allow'): Allow {
  if (v === undefined) return ALLOW_ALL;
  const shape = `{${ALLOW_KINDS.map(k => `"${k}": "*" | [ids]`).join(', ')}}`;
  if (!isObject(v)) throw invalid('INVALID_CONTEXT', field, `${field} must be an object ${shape}.`);
  for (const k of Object.keys(v)) if (!(ALLOW_KINDS as readonly string[]).includes(k))
    throw invalid('INVALID_CONTEXT', `${field}.${k}`, `${field}.${k} is not an item kind of the Backtest; the kinds are ${ALLOW_KINDS.join(', ')}.`);
  const out = {} as Record<AllowKind, '*' | readonly string[]>;
  for (const k of ALLOW_KINDS) {
    const x = v[k], f = `${field}.${k}`;
    if (x === undefined) throw invalid('INVALID_CONTEXT', f, `${f} is missing: ${field} names every kind (${ALLOW_KINDS.join(', ')}), each "*" or a list of ids.`);
    if (x === '*') { out[k] = '*'; continue }
    if (!Array.isArray(x) || x.some(id => typeof id !== 'string' || !id) || new Set(x).size !== x.length)
      throw invalid('INVALID_CONTEXT', f, `${f} must be "*" or a list of distinct non-empty ids, for example ["I01", "I07"].`);
    out[k] = Object.freeze([...x as string[]]);
  }
  return Object.freeze(out);
}

/** The per-request limits a plan may lower, with the least value each takes (the worker's own Limits keys). */
export const LIMIT_KEYS: Readonly<Record<string, number>> = {
  max_positions: 1, max_portfolio_tickers: 1, max_conditions: 1, max_flow_series: 1, monte_carlo_runs: 1, max_download_bytes: 1, max_broker_rows: 0,
};
export type LimitKey = 'max_positions' | 'max_portfolio_tickers' | 'max_conditions' | 'max_flow_series' | 'monte_carlo_runs' | 'max_download_bytes' | 'max_broker_rows';
export type PlanLimits = Readonly<Partial<Record<LimitKey, number>>>;

/** context.limits checked (undefined: none), or INVALID_CONTEXT naming the key. */
export function limitsOf(v: unknown, field = 'context.limits'): PlanLimits {
  if (v === undefined) return {};
  if (!isObject(v)) throw invalid('INVALID_CONTEXT', field, `${field} must be an object {name: whole number} (${Object.keys(LIMIT_KEYS).join(', ')}).`);
  const out: Partial<Record<LimitKey, number>> = {};
  for (const [k, x] of Object.entries(v)) {
    const f = `${field}.${k}`;
    if (!Object.prototype.hasOwnProperty.call(LIMIT_KEYS, k))
      throw invalid('INVALID_CONTEXT', f, `${f} is not a limit a plan sets on the Backtest worker; the limits are ${Object.keys(LIMIT_KEYS).join(', ')}.`);
    if (typeof x !== 'number' || !Number.isSafeInteger(x) || x < LIMIT_KEYS[k])
      throw invalid('INVALID_CONTEXT', f, `${f} must be a whole number of at least ${LIMIT_KEYS[k]}.`);
    out[k as LimitKey] = x;
  }
  return Object.freeze(out);
}

/** The worker's limits with a plan's: each the smaller of the two (a plan never raises a limit). */
export function applyLimits(own: Limits, plan: PlanLimits | undefined): Limits {
  if (!plan || !Object.keys(plan).length) return own;
  const out: Limits = { ...own };
  for (const [k, v] of Object.entries(plan) as [LimitKey, number][]) out[k] = Math.min(own[k], v);
  return out;
}

/** The item `id` of `kind` named at `field`, or 403 CAPABILITY_REQUIRED. */
export function requireItem(allow: Allow, kind: AllowKind, id: string, field: string): void {
  const a = allow[kind];
  if (a === '*' || a.includes(id)) return;
  const capability = `${FAMILY[kind]}:${id}`;
  throw new WorkerError(403, 'CAPABILITY_REQUIRED',
    `${field}: the ${WORDS[kind]} ${id} is not included in your plan (${capability}); remove it or change the plan to run this strategy.`,
    field, { kind, id, capability });
}
