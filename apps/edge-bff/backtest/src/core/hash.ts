/* Hashes of a backtest request (CONTRACT.md section 7, K3): the canonical JSON every hash is taken over, the variant
   hash (one evaluated strategy variant = one trial), the lineage key (the strategy line trials are counted in) and the
   request hash (the variant plus everything that can change a number of the result).
   Pure module: crypto.subtle and TextEncoder only (Node 22 and browsers). */
import type { BacktestRequest, Condition, LineRef } from './contract.ts';
import { PRICE_ACTION } from './conditions.ts';
import { byTicker } from './signals.ts';

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

/** The request in its canonical form (PF3, 2026-10-27): a portfolio's picked stocks in ticker order (signals.ts
    byTicker), because the order the user picked them in does not matter: the same set in any order is the same
    request, variant and result. The worker runs and hashes this form; every hash below takes it too, so a request
    in another order hashes the same wherever it is hashed. Anything else is kept as it is (a copy where it changes). */
export function canonicalRequest(q: BacktestRequest): BacktestRequest {
  const p = q.portfolio;
  if (!p || !Array.isArray(p.tickers)) return q;
  return { ...q, portfolio: { ...p, tickers: [...p.tickers].sort(byTicker) } };
}

/** The part of a request that decides the trades and the equity curve: what the engine reads, in a canonical form.
    Left out, because no trade and no trial Sharpe (the full run's, robustness.ts trialSharpe) depends on it:
    - `robustness` (Monte Carlo runs and seed reshuffle the same trades; the sensitivity switch adds cells that are
      trials of their own), `single.benchmark` (beta, alpha and correlation only), `period.oos_fraction` (it splits the
      statistics, not the run);
    - condition ids and disabled conditions: each list's enabled conditions are the sorted list of their content
      without id and enabled flag (the entry and exit rules combine them in any order; a repeated condition stays
      repeated, because at_least counts it);
    - `entry.at_least` unless the logic is at_least, and above the number of enabled entry conditions (conditions.ts
      combineEntry needs min(at_least, that number): the page's at_least 3 with 2 cards enabled is at_least 2); the
      exit-signal logic without an enabled exit condition;
    - the numbers of the stop, take-profit and trailing modes that are not chosen: only the chosen mode's number (pct,
      atr_mult, reward_risk_x, r_multiple), the chandelier's length and multiple, a line mode's line, and atr_length
      only with an ATR stop or target (engine.ts validateRun reads exactly these);
    - `sizing.allocation_fraction` in portfolio mode (a slot is 1 / max_positions of equity); `costs.ara_gap_fraction`
      while skip_ara_open_gap is off;
    - the order of the picked stocks (canonicalRequest): the set is kept, so another set is another variant (PF4).
    Rerunning a request that differs only there is not a new trial. */
export function variantOf(request: BacktestRequest): Record<string, unknown> {
  const q = canonicalRequest(request), x = q.exit, single = q.mode === 'single';
  const content = (cs: readonly Condition[]) => cs.filter(c => c.enabled !== false).map(c => { const { id: _i, enabled: _e, ...rest } = c; return canonicalJson(rest) }).sort();
  const entryConditions = content(q.entry.conditions), exitConditions = content(x.signals.conditions);
  const s = x.stop, t = x.take_profit, tr = x.trailing;
  const stop = s.mode === 'pct' ? { mode: s.mode, pct: s.pct } : s.mode === 'atr' ? { mode: s.mode, atr_mult: s.atr_mult }
    : s.mode === 'rr' ? { mode: s.mode, reward_risk_x: s.reward_risk_x } : s.mode === 'line' ? { mode: s.mode, line: s.line } : { mode: s.mode };
  const take_profit = t.mode === 'pct' ? { mode: t.mode, pct: t.pct } : t.mode === 'r' ? { mode: t.mode, r_multiple: t.r_multiple }
    : t.mode === 'atr' ? { mode: t.mode, atr_mult: t.atr_mult } : { mode: t.mode };
  const trailing = tr.mode === 'pct' ? { mode: tr.mode, pct: tr.pct } : tr.mode === 'chandelier' ? { mode: tr.mode, chandelier_length: tr.chandelier_length, chandelier_mult: tr.chandelier_mult }
    : tr.mode === 'line' ? { mode: tr.mode, line: tr.line } : { mode: tr.mode };
  return {
    schema_version: q.schema_version, mode: q.mode,
    ...(single ? { single: { ticker: q.single?.ticker } } : { portfolio: q.portfolio }),
    period: { from: q.period.from, to: q.period.to },
    entry: { logic: q.entry.logic, ...(q.entry.logic === 'at_least' ? { at_least: Math.min(q.entry.at_least, entryConditions.length) } : {}), window_bars: q.entry.window_bars, conditions: entryConditions },
    exit: {
      ...(s.mode === 'atr' || t.mode === 'atr' ? { atr_length: x.atr_length } : {}), stop, take_profit, trailing, max_hold_bars: x.max_hold_bars,
      signals: exitConditions.length ? { logic: x.signals.logic, conditions: exitConditions } : { conditions: [] },
    },
    sizing: single ? { capital_idr: q.sizing.capital_idr, allocation_fraction: q.sizing.allocation_fraction } : { capital_idr: q.sizing.capital_idr },
    costs: { buy_fee: q.costs.buy_fee, sell_fee: q.costs.sell_fee, slippage: q.costs.slippage, skip_ara_open_gap: q.costs.skip_ara_open_gap,
      ...(q.costs.skip_ara_open_gap ? { ara_gap_fraction: q.costs.ara_gap_fraction } : {}) },
  };
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
    counted apart); entry logic and condition shapes; stop, take-profit and trailing modes (with the line's indicator
    and output for a line mode); exit-signal logic (only when an exit condition is enabled) and condition shapes. Not
    in it: every number (thresholds, lengths, multiples, percentages, window, at_least, max hold, sizing, costs, max
    positions, liquidity), parameters, condition ids, the period and OOS share, the benchmark, the portfolio ranking,
    the robustness settings, and a portfolio's picked stocks: changing any of those is a new variant (a trial) of the
    same line. The picked stocks are in the variant, not in the line (PF4, lead 2026-10-27): picking stocks is
    selection, so adding or removing one is another trial of the same strategy, never a line whose count restarts at
    1. `universe` stays in the shape as null (the portfolio universes it held are gone, PF1), so a single-mode line
    keeps the key it had. */
export function lineageShape(q: BacktestRequest): unknown {
  const x = q.exit, exitConds = shapes(x.signals.conditions);
  return {
    lineage: 1, mode: q.mode,
    ticker: q.mode === 'single' ? q.single?.ticker ?? null : null,
    universe: null,
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

/** Hash of everything that can change a number of the result: the whole request in its canonical form (robustness
    included: the seed moves the Monte Carlo) and the engine, registry and data versions. */
export const requestHash = (q: BacktestRequest, v: { engine_version: string; registry_version: string; data_version: string }): Promise<string> =>
  sha256Hex(canonicalJson({ request: canonicalRequest(q), engine_version: v.engine_version, registry_version: v.registry_version, data_version: v.data_version }));
