/* The query planner (EXEC-SCREENER; report TARGET ARCHITECTURE 6.10, 6.16; API CONTRACT 8.5 `conditions[]`, `plan`).
   Stages:
     S0 universe hard filters (universe.ts applyUniverse, then the VALUE metric_filters on its survivors): conjunctive
        and outside `met`, so safe for every logic; stale and price-break tickers hidden by default (P4);
     S1 population-level cross-sectional values (xsection.ts, rs_rank on the fixed population, P7): never pruned;
     S2 snapshot lookups (every series of the condition pre-warmed, O(1) per ticker): evaluated on EVERY S0 survivor,
        so their counts are always exact;
     S3 dynamic conditions, in ascending predicted cost (cost_class x length x survivors' bars, calibrated by an
        exponentially weighted mean of measured ms), each on the tickers not yet pruned;
     S4 completion: every remaining cell of each surviving ticker, so displayed rows are complete.
   Pruning rule: theta = need - 1 when need >= 2, else need; a ticker with m passes and r unevaluated conditions is
   pruned iff m + r < theta. Proof (report 6.10): its final met <= m + r < theta <= need, so it is not a match; with
   theta = need - 1 its met < need - 1, so not near either; FAIL and NA never add to met; every evaluation is pure and
   keyed by (ticker, condition), so order cannot change a value. ALL prunes at the second failure (the first when
   need = 1); AT LEAST k when failures exceed n - theta; ANY never (need 1 -> theta 1: no saving), and the answer says
   so (warning NO_PRUNING_FOR_ANY, plan.note). options.exhaustive disables pruning.
   Counts: each condition reports evaluated, passed, na and exhaustive; passed counts the tickers in evaluated and is
   the full count only when exhaustive (a pruned S3 condition is "m of evaluated", never "m of U").
   Budget: the worst case is costed before running (costEstimate); above SCREENER_MAX_CPU_MS the request is refused with
   LIMIT_EXCEEDED {limit: 'compute_budget', allowed, needed, costliest}, never cut short. A cancel flag is checked
   between tickers. Verification (TEST PLAN 10b.6): pruned output = exhaustive output for the match set, near set,
   every displayed cell, met and na_count; permuting S3 order changes nothing.
   Pure orchestration over closures the worker binds (condition.ts per condition and ticker; screen.ts runs it). */
import type { Cell, Logic, PlanExplain, RowStatus } from './contract.ts';
import { needOf, rowStatus } from './match.ts';

/** theta of the pruning rule (report 6.10). */
export const pruneThreshold = (need: number): number => need >= 2 ? need - 1 : need;
/** Whether a ticker with `met` passes and `unevaluated` conditions left can no longer be a match or near. */
export const canPrune = (met: number, unevaluated: number, theta: number): boolean => met + unevaluated < theta;

export type ConditionStage = 'S1' | 'S2' | 'S3';

/** One active condition as the planner sees it. evaluate(ticker) must be pure: the same ticker always gives the same
    cell, whatever was evaluated before (the proof's premise). predictedMs: the S3 ordering key (0 for S1 and S2). */
export interface PlanCondition {
  id: string;
  stage: ConditionStage;
  predictedMs: number;
  evaluate(ticker: string): Cell;
}
export interface PlanInput {
  tickers: readonly string[];        // the S0 survivors (metric filters applied), in ticker order (signals.ts byTicker)
  conditions: readonly PlanCondition[];
  logic: Logic; atLeast?: number;
  exhaustive: boolean;
  cancelled?: () => boolean;         // checked between tickers; a cancelled plan throws PlanCancelledError (the caller answers nothing)
  cacheHits?: () => number;          // additive: the caller's series-cache hit counter, read into explain.cache_hits
}
/** Thrown by runPlan when input.cancelled() turns true (the browser left, a newer request replaced this one). */
export class PlanCancelledError extends Error {
  constructor() { super('the screen was cancelled'); this.name = 'PlanCancelledError' }
}
const now = (): number => (globalThis.performance ? globalThis.performance.now() : Date.now());
export interface PlanSummary { evaluated: number; passed: number; na: number; exhaustive: boolean }
export interface PlanRow { ticker: string; status: RowStatus; met: number; need: number; na_count: number; cells: Cell[] }
export interface PlanOutput {
  need: number;
  rows: PlanRow[];                   // matches and near rows only, every cell evaluated (S4), cells in condition order
  summaries: Record<string, PlanSummary>;   // per condition id
  pruned: number;                    // tickers pruned before S4
  explain: Omit<PlanExplain, 'stages'> & { stages: { name: 'S1' | 'S2' | 'S3' | 'S4'; in: number; out: number; ms: number }[] };
}

/** Runs S1-S4 over the S0 survivors with the pruning rule above (none when exhaustive or need <= 1). match_count and
    near_count are the rows' statuses (match.ts rowStatus, the one near rule). */
export function runPlan(input: PlanInput): PlanOutput {
  const { tickers, conditions } = input, T = tickers.length, K = conditions.length;
  const ids = new Set<string>();
  for (const c of conditions) { if (ids.has(c.id)) throw new RangeError(`runPlan: condition ${c.id} is listed twice`); ids.add(c.id) }
  const need = needOf(input.logic, input.atLeast, K), theta = pruneThreshold(need);
  const prune = !input.exhaustive && need >= 2;                 // need 1 (ANY, or one condition): nothing to save (theta 1)
  const cells: (Cell | null)[][] = tickers.map(() => new Array(K).fill(null));
  const met = new Int32Array(T), left = new Int32Array(T).fill(K), alive = new Uint8Array(T).fill(1);
  const sum = conditions.map(() => ({ evaluated: 0, passed: 0, na: 0 }));
  const check = () => { if (input.cancelled?.()) throw new PlanCancelledError() };
  const evaluate = (ti: number, k: number) => {
    const cell = conditions[k].evaluate(tickers[ti]);
    if (cell.id !== conditions[k].id) throw new RangeError(`runPlan: condition ${conditions[k].id} answered a cell for ${cell.id}`);
    cells[ti][k] = cell; left[ti]--; sum[k].evaluated++;
    if (cell.status === 'pass') { met[ti]++; sum[k].passed++ } else if (cell.status === 'na') sum[k].na++;
  };
  let pruned = 0;
  const tryPrune = (ti: number) => { if (prune && alive[ti] && canPrune(met[ti], left[ti], theta)) { alive[ti] = 0; pruned++ } };
  const aliveCount = () => { let n = 0; for (let i = 0; i < T; i++) n += alive[i]; return n };
  const pos = new Map(conditions.map((c, k) => [c.id, k]));
  const s1 = conditions.filter(c => c.stage === 'S1'), s2 = conditions.filter(c => c.stage === 'S2'), s3 = orderS3(conditions.filter(c => c.stage === 'S3'));
  const stages: { name: 'S1' | 'S2' | 'S3' | 'S4'; in: number; out: number; ms: number }[] = [];
  // S1 and S2: every condition on every S0 survivor (population values and snapshot lookups: their counts are exact)
  for (const [name, list] of [['S1', s1], ['S2', s2]] as const) {
    const t0 = now(), n0 = aliveCount();
    for (const c of list) { const k = pos.get(c.id)!; for (let ti = 0; ti < T; ti++) { check(); evaluate(ti, k) } }
    if (name === 'S2') for (let ti = 0; ti < T; ti++) tryPrune(ti);
    stages.push({ name, in: n0, out: aliveCount(), ms: now() - t0 });
  }
  // S3: dynamic conditions in ascending predicted cost, each on the tickers that can still match or be near
  {
    const t0 = now(), n0 = aliveCount();
    for (const c of s3) {
      const k = pos.get(c.id)!;
      for (let ti = 0; ti < T; ti++) { if (!alive[ti]) continue; check(); evaluate(ti, k); tryPrune(ti) }
    }
    stages.push({ name: 'S3', in: n0, out: aliveCount(), ms: now() - t0 });
  }
  // S4: completion, so every displayed row has every cell (a guarantee: S3 already evaluated each surviving ticker)
  const rows: PlanRow[] = [];
  {
    const t0 = now(), n0 = aliveCount();
    for (let ti = 0; ti < T; ti++) {
      if (!alive[ti]) continue;
      check();
      for (let k = 0; k < K; k++) if (cells[ti][k] === null) evaluate(ti, k);
      let na = 0; for (const c of cells[ti]) if (c!.status === 'na') na++;
      const status = rowStatus(met[ti], need);
      if (status) rows.push({ ticker: tickers[ti], status, met: met[ti], need, na_count: na, cells: cells[ti] as Cell[] });
    }
    stages.push({ name: 'S4', in: n0, out: rows.length, ms: now() - t0 });
  }
  const summaries: Record<string, PlanSummary> = {};
  conditions.forEach((c, k) => { summaries[c.id] = { ...sum[k], exhaustive: sum[k].evaluated === T } });
  const exhaustive = conditions.every((_, k) => sum[k].evaluated === T);
  const note = input.exhaustive ? 'exhaustive: pruning off' : input.logic === 'any' ? 'ANY: no safe pruning' : need <= 1 ? 'need 1: no safe saving from pruning' : undefined;
  return {
    need, rows, summaries, pruned,
    explain: { stages, order: [...s1, ...s2, ...s3].map(c => c.id), pruned, cache_hits: input.cacheHits?.() ?? 0, exhaustive, ...(note ? { note } : {}) },
  };
}

/** The S3 order: ascending predictedMs, ties by condition id (deterministic; the order never changes a result). */
export function orderS3(conditions: readonly PlanCondition[]): PlanCondition[] {
  return [...conditions].sort((a, b) => a.predictedMs - b.predictedMs || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/** The cost model of S3 ordering and of the budget: predicted ms of a dynamic condition = (cost_class O(N·n) ? length :
    1) x bars x the ns per bar measured so far for its key (an exponentially weighted mean with weight alpha on the new
    measurement; before any measurement, the registry cost model's ns_per_bar_length). observe() feeds measured times
    back; its `length` is the multiplier predict() used (the length for O(N·n), 1 for O(N)). bars: what the caller
    costs (one ticker's bars for PlanCondition.predictedMs, which is per ticker). */
export interface CostTracker {
  predict(key: string, costClass: 'O(N)' | 'O(N·n)', length: number, bars: number): number;
  observe(key: string, ms: number, bars: number, length: number): void;
}
export function costTracker(initialNsPerBarLength: number, alpha: number): CostTracker {
  if (!(Number.isFinite(initialNsPerBarLength) && initialNsPerBarLength > 0)) throw new RangeError(`costTracker: initialNsPerBarLength must be positive, not ${initialNsPerBarLength}`);
  if (!(alpha > 0 && alpha <= 1)) throw new RangeError(`costTracker: alpha must be in (0, 1], not ${alpha}`);
  const ns = new Map<string, number>();
  return {
    predict: (key, costClass, length, bars) => (costClass === 'O(N·n)' ? Math.max(1, length) : 1) * Math.max(0, bars) * (ns.get(key) ?? initialNsPerBarLength) / 1e6,
    observe: (key, ms, bars, length) => {
      if (!(Number.isFinite(ms) && ms >= 0 && bars > 0)) return;
      const sample = ms * 1e6 / (bars * Math.max(1, length)), prev = ns.get(key);
      ns.set(key, prev === undefined ? sample : alpha * sample + (1 - alpha) * prev);
    },
  };
}

/** The worst case of a definition before running (report 6.10 "Counts and budget"): every dynamic (S3) condition on
    every S0 survivor, as predicted (predictedMs is per ticker); costliest = the condition id with the largest share,
    ties by id (null when nothing is dynamic). The caller refuses LIMIT_EXCEEDED {limit: 'compute_budget', allowed:
    SCREENER_MAX_CPU_MS, needed, costliest} above the budget, before any compute. */
export function costEstimate(conditions: readonly PlanCondition[], survivors: number): { needed_ms: number; costliest: string | null } {
  let needed = 0, best: PlanCondition | null = null;
  for (const c of conditions) {
    if (c.stage !== 'S3') continue;
    needed += c.predictedMs * survivors;
    if (!best || c.predictedMs > best.predictedMs || (c.predictedMs === best.predictedMs && c.id < best.id)) best = c;
  }
  return { needed_ms: needed, costliest: best ? best.id : null };
}
