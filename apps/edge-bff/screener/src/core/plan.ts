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
   Pure orchestration over closures the worker binds (evaluate.ts per condition and ticker). Implemented here:
   pruneThreshold, canPrune. The rest are typed stubs for the core-logic agent. */
import type { Cell, Logic, PlanExplain, RowStatus } from './contract.ts';

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
  cancelled?: () => boolean;         // checked between tickers; a cancelled plan throws (the caller answers nothing)
}
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
  throw new Error('not implemented: runPlan');
}

/** The S3 order: ascending predictedMs, ties by condition id (deterministic; the order never changes a result). */
export function orderS3(conditions: readonly PlanCondition[]): PlanCondition[] {
  throw new Error('not implemented: orderS3');
}

/** The cost model of S3 ordering and of the budget: predicted ms of a dynamic condition = (cost_class O(N·n) ? length :
    1) x bars x the ns per bar measured so far for its key (an exponentially weighted mean; before any measurement, the
    registry cost model's ns_per_bar_length). observe() feeds measured times back. */
export interface CostTracker {
  predict(key: string, costClass: 'O(N)' | 'O(N·n)', length: number, bars: number): number;
  observe(key: string, ms: number, bars: number, length: number): void;
}
export function costTracker(initialNsPerBarLength: number, alpha: number): CostTracker {
  throw new Error('not implemented: costTracker');
}

/** The worst case of a definition before running (report 6.10 "Counts and budget"): every dynamic condition on every S0
    survivor, as predicted; costliest = the condition id with the largest share (null when nothing is dynamic). The
    caller refuses LIMIT_EXCEEDED {limit: 'compute_budget', allowed: SCREENER_MAX_CPU_MS, needed, costliest} above
    the budget, before any compute. */
export function costEstimate(conditions: readonly PlanCondition[], survivors: number): { needed_ms: number; costliest: string | null } {
  throw new Error('not implemented: costEstimate');
}
