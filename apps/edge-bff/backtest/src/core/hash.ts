/* Hashes of a backtest request (CONTRACT.md section 7, K3): the canonical JSON every hash is taken over, the variant
   hash (one evaluated strategy variant = one trial), the lineage key (the strategy line trials are counted in) and the
   request hash (the variant plus everything that can change a number of the result).
   Pure module: crypto.subtle and TextEncoder only (Node 22 and browsers). */
import type { BacktestRequest, Condition, LineRef } from './contract.ts';
import { PRICE_ACTION } from './conditions.ts';

/** JSON with the keys of every object sorted (UTF-16 order, Array.prototype.sort default) and no whitespace; keys
    whose value is undefined are left out as JSON.stringify does. A value JSON cannot carry exactly (NaN, ±Infinity,
    undefined in an array, a function, a bigint) is an error: it would otherwise hash like null. */
export function canonicalJson(value: unknown): string {
  if (value === null) return 'null';
  switch (typeof value) {
    case 'number': if (!Number.isFinite(value)) throw new TypeError(`canonicalJson: ${value} has no JSON form`); return JSON.stringify(value);
    case 'string': case 'boolean': return JSON.stringify(value);
    case 'object': {
      if (Array.isArray(value)) return '[' + value.map(v => { if (v === undefined) throw new TypeError('canonicalJson: undefined in an array'); return canonicalJson(v) }).join(',') + ']';
      const o = value as Record<string, unknown>;
      return '{' + Object.keys(o).sort().filter(k => o[k] !== undefined).map(k => JSON.stringify(k) + ':' + canonicalJson(o[k])).join(',') + '}';
    }
    default: throw new TypeError(`canonicalJson: a ${typeof value} has no JSON form`);
  }
}

/** Lowercase hex SHA-256 of the UTF-8 bytes of a string. */
export async function sha256Hex(text: string): Promise<string> {
  const d = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
  let s = ''; for (const b of d) s += b.toString(16).padStart(2, '0');
  return s;
}

/** The part of a request that decides the trades and the equity curve. Left out: `robustness` (Monte Carlo runs and
    seed reshuffle the same trades; the sensitivity switch adds cells that are trials of their own) and
    `single.benchmark` (it changes beta, alpha and correlation, never a trade or the Sharpe). Rerunning a request
    that differs only there is not a new trial. */
export function variantOf(q: BacktestRequest): Record<string, unknown> {
  const { robustness: _r, single, ...rest } = q;
  if (!single) return rest;
  const { benchmark: _b, ...s } = single;
  return { ...rest, single: s };
}
/** Hash of one evaluated strategy variant (K3: distinct variant hashes are the trials of a lineage). */
export const variantHash = (q: BacktestRequest): Promise<string> => sha256Hex(canonicalJson(variantOf(q)));

/* The strategy shape of K3: everything categorical about the strategy, no number. A condition is its kind, indicator
   or type, operator and the output names it compares (a numeric side is just 'value'); parameters (numbers, and the
   enum or broker choices that tune them) are left out. Only enabled conditions count (a disabled one is not part of
   the tested strategy), and their order does not (the same set of rules is the same strategy). */
const sideShape = (s: { type: string; output?: string }) => s.type === 'output' ? { type: 'output', output: s.output } : { type: s.type };
function conditionShape(c: Condition): unknown {
  if (c.kind === 'indicator') return { kind: c.kind, indicator: c.indicator, lhs: sideShape(c.lhs), op: c.op, rhs: sideShape(c.rhs) };
  if (c.kind === 'price_action') return { kind: c.kind, type: c.type, op: c.op ?? PRICE_ACTION[c.type]?.ops[0] ?? null };
  return { kind: c.kind, type: c.type, op: c.op };
}
const shapes = (cs: readonly Condition[]) => cs.filter(c => c.enabled !== false).map(c => canonicalJson(conditionShape(c))).sort();
const lineShape = (l: LineRef) => ({ indicator: l.indicator, output: l.output });

/** The lineage's shape: mode; the single ticker (another stock is another test of the strategy, so its trials are
    counted apart) or the portfolio universe; entry logic and condition shapes; stop, take-profit and trailing modes
    (with the line's indicator and output for a line mode); exit-signal logic (only when an exit condition is enabled)
    and condition shapes. Not in it: every number (thresholds, lengths, multiples, percentages, window, at_least,
    max hold, sizing, costs, max positions, liquidity), parameters, condition ids, the period and OOS share, the
    benchmark, the portfolio ranking and the robustness settings: changing any of those is a new variant (a trial)
    of the same line. */
export function lineageShape(q: BacktestRequest): unknown {
  const x = q.exit, exitConds = shapes(x.signals.conditions);
  return {
    lineage: 1, mode: q.mode,
    ticker: q.mode === 'single' ? q.single?.ticker ?? null : null,
    universe: q.mode === 'portfolio' ? q.portfolio?.universe ?? null : null,
    entry: { logic: q.entry.logic, conditions: shapes(q.entry.conditions) },
    exit: {
      stop: x.stop.mode === 'line' ? { mode: 'line', line: lineShape(x.stop.line) } : { mode: x.stop.mode },
      take_profit: { mode: x.take_profit.mode },
      trailing: x.trailing.mode === 'line' ? { mode: 'line', line: lineShape(x.trailing.line) } : { mode: x.trailing.mode },
      signals: { logic: exitConds.length ? x.signals.logic : null, conditions: exitConds },
    },
  };
}
export const lineageKey = (q: BacktestRequest): Promise<string> => sha256Hex(canonicalJson(lineageShape(q)));

/** Hash of everything that can change a number of the result: the whole request (robustness included: the seed moves
    the Monte Carlo) and the engine, registry and data versions. */
export const requestHash = (q: BacktestRequest, v: { engine_version: string; registry_version: string; data_version: string }): Promise<string> =>
  sha256Hex(canonicalJson({ request: q, engine_version: v.engine_version, registry_version: v.registry_version, data_version: v.data_version }));
