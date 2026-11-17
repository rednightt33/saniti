/* Checker C1 (security), EDGE multi-user Phase 3b (verification/edge_multiuser/access_tiers/CONTRACT.md 8b "3b in
   detail": "Every place an item can be named counts"; the only recorded exemption is the four transform metrics).
   These requests reach a catalog item the plan does not hold through a built-in option of the Backtest, with no
   CAPABILITY_REQUIRED:
   - portfolio.rank_by 'fnet' ranks by the Screener flow entry fnet (releases.json flow_indicator 'fnet'), the same
     series the legacy flow card {type: 'fnet'} reads, which IS gated (validate.ts legacyItemKind);
   - portfolio.rank_by 'adx' / 'rsi' / 'vol' compute I07 / I13 / I35 (signals.ts rankScores);
   - the legacy price_action card {type: 'macd'} computes I06 (MACD), and with op bullish_divergence it is the Screener
     metric macd_divergence (conditions.ts PRICE_ACTION macd);
   - an ATR stop computes I30 (engine.ts atrParams).
   Each test expects 403 CAPABILITY_REQUIRED (or, if the user decides these are exempt, the exemption must be recorded
   in CONTRACT.md 8b as the transform metrics are, and this file changed with that decision). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import type { Allow } from '../src/access.ts';
import type { Config } from '../src/config.ts';
import { checkRequest } from '../src/validate.ts';
import type { References } from '../src/validate.ts';

const REFS: References = {
  tickers: [{ ticker: 'BBCA', name: 'BBCA (test name)', type: 'stock', groups: { sector: 'Sector A' } }, { ticker: 'BMRI', name: 'BMRI (test name)', type: 'stock', groups: { sector: 'Sector A' } },
    { ticker: 'IHSG', name: 'IHSG (test name)', type: 'index', groups: { sector: null } }],
  brokers: [{ code: 'YU', name: 'test broker', type: 'Foreign' }],
};
const CFG: Pick<Config, 'limits' | 'flow'> = {
  limits: { max_positions: MAX_POSITIONS, window_bars: { min: 1, max: 20 }, monte_carlo_runs: 1000, max_portfolio_tickers: MAX_PORTFOLIO_TICKERS, max_download_bytes: 1e9, max_broker_rows: 1e9, timeout_seconds: 600, queued_per_owner: 3, max_conditions: 20, max_flow_series: 8 },
  flow: { enabled: true, reason: null },
};
/** A plan holding only I13 (the entry condition below) and nothing else. */
const PLAN: Allow = { indicator: ['I13', 'I01', 'I09'], flow_indicator: [], candle_pattern: [], screener_metric: [] };
const RSI_GT_50 = { id: 'a1', enabled: true, kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'gt', rhs: { type: 'value', value: 50 } } as unknown as Condition;

function request(over: Partial<BacktestRequest> = {}, stop: Partial<BacktestRequest['exit']['stop']> = {}, entry: Condition[] = [RSI_GT_50]): BacktestRequest {
  return {
    schema_version: 1, mode: 'single', single: { ticker: 'BBCA', benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: '2026-10-23', oos_fraction: 0.3 },
    entry: { logic: 'any', at_least: 1, window_bars: 5, conditions: entry },
    exit: {
      atr_length: 14,
      stop: { mode: 'line', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' }, ...stop },
      take_profit: { mode: 'pct', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 20 } } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
    ...over,
  };
}
const portfolio = (rank_by: string): BacktestRequest => {
  const q = request({ mode: 'portfolio', portfolio: { tickers: ['BBCA', 'BMRI'], max_positions: 2, rank_by: rank_by as 'adx', min_avg_value_20d_idr: 0 } });
  delete (q as { single?: unknown }).single;
  return q;
};
function refused(q: BacktestRequest, capability: string): void {
  assert.throws(() => checkRequest(q, REFS, CFG, new Set(), PLAN),
    (e: unknown) => (e as { status?: number }).status === 403 && (e as { code?: string }).code === 'CAPABILITY_REQUIRED'
      && (e as { details?: { capability?: string } }).details?.capability === capability,
    `expected 403 CAPABILITY_REQUIRED ${capability}`);
}

test('the request with only held items passes (control)', () => {
  checkRequest(request(), REFS, CFG, new Set(), PLAN);
});
test("rank_by 'fnet' is refused without backtest.flow_indicator:fnet (the legacy fnet card is)", () => {
  refused(portfolio('fnet'), 'backtest.flow_indicator:fnet');
});
for (const [rank, id] of [['adx', 'I07'], ['vol', 'I35']] as const) {
  test(`rank_by '${rank}' is refused without backtest.indicator:${id}`, () => refused(portfolio(rank), `backtest.indicator:${id}`));
}
test("the legacy price_action card 'macd' is refused without backtest.indicator:I06", () => {
  const macd = { id: 'm1', enabled: true, kind: 'price_action', type: 'macd', params: { fast_length: 12, slow_length: 26, signal_length: 9 }, op: 'crosses_above_signal' } as unknown as Condition;
  refused(request({}, {}, [RSI_GT_50, macd]), 'backtest.indicator:I06');
});
test('an ATR stop is refused without backtest.indicator:I30', () => {
  refused(request({}, { mode: 'atr' }), 'backtest.indicator:I30');
});
