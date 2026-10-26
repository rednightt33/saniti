/* The page state as the wire request (contract.ts BacktestRequest): the cards become wire conditions with the one
   mapping in core/catalog.ts, percent fields become fractions, Rp B becomes IDR, the Benchmark select becomes
   single.benchmark. Cards the API cannot calculate (its "Not calculated" pill) are left out, as the reference ignores
   them on Run; a card with an invalid input is refused with the core's ValidationError (shown by the page's toast). */
import type { BacktestRequest, SignalsPreviewRequest } from '../core/contract.ts';
import type { Card } from './types.ts';
import { toWire } from './compute.ts';
import { S, type State } from '../state.ts';
import { API, CAT } from '../env.ts';

/** the reference's ARA rule: skip an entry that opens at least 20 % above the previous close */
export const ARA_GAP = 0.2;
/** the reference's Monte Carlo seed (monteCarlo: s2 = 7) */
export const MC_SEED = 7;

const wire = (cards: Card[], ready: (c: Card) => boolean) => cards.filter(ready).map(toWire);

export const entryOf = (s: State, ready: (c: Card) => boolean): BacktestRequest['entry'] => ({
  logic: s.logic === 'n' ? 'at_least' : s.logic, at_least: s.atLeast, window_bars: s.window, conditions: wire(s.conds, ready),
});

export function buildRequest(s: State, opts: { ready: (c: Card) => boolean; monteCarloRuns: number }): BacktestRequest {
  const e = s.exit;
  return {
    schema_version: 1,
    mode: s.mode,
    ...(s.mode === 'single'
      ? { single: { ticker: s.ticker, benchmark: s.bench === 'ihsg' ? 'ihsg' : 'buy_and_hold' } }
      : { portfolio: { universe: s.universe, max_positions: s.maxPos, rank_by: s.rankBy, min_avg_value_20d_idr: s.cost.minVal * 1e9 } }),
    period: { from: s.from, to: s.to, oos_fraction: s.oos / 100 as BacktestRequest['period']['oos_fraction'] },
    entry: entryOf(s, opts.ready),
    exit: {
      atr_length: e.atrLen,
      stop: { mode: e.stopMode as BacktestRequest['exit']['stop']['mode'], pct: e.sl / 100, atr_mult: e.slAtr, reward_risk_x: e.slRR,
              line: { indicator: e.stopLine.id, output: e.stopLine.o, ...(e.stopLine.p ? { params: e.stopLine.p as Record<string, number | string | boolean> } : {}) } },
      take_profit: { mode: e.tpMode as BacktestRequest['exit']['take_profit']['mode'], pct: e.tp / 100, r_multiple: e.tpR, atr_mult: e.tpAtr },
      trailing: { mode: (e.trailMode === 'chand' ? 'chandelier' : e.trailMode) as BacktestRequest['exit']['trailing']['mode'], pct: e.trail / 100,
                  chandelier_length: e.chLen, chandelier_mult: e.chK,
                  line: { indicator: e.trailLine.id, output: e.trailLine.o, ...(e.trailLine.p ? { params: e.trailLine.p as Record<string, number | string | boolean> } : {}) } },
      max_hold_bars: e.hold,
      signals: { logic: s.exitLogic, conditions: wire(s.exitConds, opts.ready) },
    },
    sizing: { capital_idr: s.size.capital, allocation_fraction: s.size.alloc / 100 },
    costs: { buy_fee: s.cost.buy / 100, sell_fee: s.cost.sell / 100, slippage: s.cost.slip / 100, skip_ara_open_gap: s.cost.ara, ara_gap_fraction: ARA_GAP },
    robustness: { monte_carlo_runs: opts.monteCarloRuns, seed: MC_SEED, sensitivity: true },
  };
}

/** the request of the page's current settings */
export const currentRequest = () => buildRequest(S, { ready: c => API.ready(c), monteCarloRuns: CAT.limits.monte_carlo_runs });

/** the portfolio table's signal preview of the current settings (cards with an invalid input are left out here: the
    preview shows what can be calculated, the run reports the error) */
export function previewRequest(): SignalsPreviewRequest {
  const safe = (c: Card) => { if (!API.ready(c)) return false; try { toWire(c); return true } catch { return false } };
  return { schema_version: 1, universe: S.universe, period: { from: S.from, to: S.to }, entry: entryOf(S, safe) };
}
