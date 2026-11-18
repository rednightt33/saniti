/* Checker C1 (security), EDGE multi-user Phase 3b (verification/edge_multiuser/access_tiers/CONTRACT.md 8b "3b in
   detail": "Every place an item can be named counts"), changed to the user's decision on O3b-1 (2026-11-18; CONTRACT.md
   8b "3b follow-up"). The checker found built-in options of the Backtest that compute a catalog item without naming its
   id. The user decided:
   - "Semua indikator technical sekarang dibuka ... ADX, RSI, dan sebagainya, pokoknya indikator yang untuk yang
     technical by nature itu nanti bisa diakses oleh user berbayar": the built-ins that compute a technical indicator are
     part of the Backtest and are accepted with an allow that lacks their indicator: portfolio.rank_by 'adx' / 'vol' /
     'rsi' (I07 / I35 / I13, signals.ts rankScores), the legacy price_action card {type: 'macd'} (I06), and the ATR stop,
     the ATR target and the chandelier trailing stop (I30, engine.ts atrParams);
   - "Pokoknya gate-nya adalah terminal ... menu yang akan ditutup di terminal adalah menu yang sifatnya flow": the
     built-ins that read broker data follow the flow rule and are refused 403 CAPABILITY_REQUIRED without their flow item:
     portfolio.rank_by 'fnet' (the item fnet, signals.ts RANK_ITEM), and the legacy flow cards {type: 'broker'} and
     {type: 'top5'} (catalog items since the follow-up, validate.ts legacyItemKind from catalog.ts LEGACY group 'flow').
   The capability a refusal names is the family edge-bff expands for this worker (access.ts FAMILY = app/allow.py
   FAMILIES): the Terminal's terminal.flow_indicator, so edge-bff's display_name is the catalog's "Terminal Flow
   indicators: <id>". */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import { RANK_BY, RANK_ITEM } from '../../edge-bff/backtest/src/core/signals.ts';
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
/** A plan holding only the indicators the request names (I13 entry, I09 stop line, I01 trailing line): not I07, I35,
    I06 or I30, no Flow item, no pattern, no Screener metric. */
const PLAN: Allow = { indicator: ['I13', 'I01', 'I09'], flow_indicator: [], candle_pattern: [], screener_metric: [] };
const RSI_GT_50 = { id: 'a1', enabled: true, kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'gt', rhs: { type: 'value', value: 50 } } as unknown as Condition;

function request(over: Partial<BacktestRequest> = {}, exit: Partial<BacktestRequest['exit']> = {}, entry: Condition[] = [RSI_GT_50]): BacktestRequest {
  return {
    schema_version: 1, mode: 'single', single: { ticker: 'BBCA', benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: '2026-10-23', oos_fraction: 0.3 },
    entry: { logic: 'any', at_least: 1, window_bars: 5, conditions: entry },
    exit: {
      atr_length: 14,
      stop: { mode: 'line', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 20 } } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: [] },
      ...exit,
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
    ...over,
  };
}
const CLOSE_GT_SMA = { id: 's1', enabled: true, kind: 'indicator', indicator: 'I01', params: {}, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } } as unknown as Condition;
const portfolio = (rank_by: string, entry: Condition[] = [RSI_GT_50]): BacktestRequest => {
  const q = request({ mode: 'portfolio', portfolio: { tickers: ['BBCA', 'BMRI'], max_positions: 2, rank_by: rank_by as 'adx', min_avg_value_20d_idr: 0 } }, {}, entry);
  delete (q as { single?: unknown }).single;
  return q;
};
const card = (id: string, type: string, params: Record<string, unknown>, enabled = true) =>
  ({ id, enabled, kind: 'flow', type, params, op: 'gt', value: 0 }) as unknown as Condition;

function accepted(q: BacktestRequest, plan: Allow = PLAN): void {
  checkRequest(q, REFS, CFG, new Set(), plan);
}
function refused(q: BacktestRequest, field: string, id: string): void {
  assert.throws(() => checkRequest(q, REFS, CFG, new Set(), PLAN),
    (e: unknown) => {
      const x = e as { status?: number; code?: string; field?: string; details?: unknown };
      assert.deepEqual({ status: x.status, code: x.code, field: x.field, details: x.details },
        { status: 403, code: 'CAPABILITY_REQUIRED', field, details: { kind: 'flow_indicator', id, capability: `terminal.flow_indicator:${id}` } });
      return true;
    });
  accepted(q, { ...PLAN, flow_indicator: [id] });                                    // and passes once the plan holds it
}

test('the request with only held items passes (control)', () => {
  accepted(request());
});

/* ---- technical built-ins: part of the Backtest, accepted without their indicator ---------------------------------- */
for (const [rank, id] of [['adx', 'I07'], ['vol', 'I35'], ['rsi', 'I13']] as const) {
  test(`rank_by '${rank}' (${id}) is accepted with an allow that lacks ${id}`, () => {
    // the entry reads I01 only, so the plan holds neither I07, I35 nor I13
    accepted(portfolio(rank, [CLOSE_GT_SMA]), { ...PLAN, indicator: ['I01', 'I09'] });
  });
}
test("the legacy price_action card 'macd' (I06) is accepted, with every MACD operator", () => {
  for (const op of ['crosses_above_signal', 'histogram_positive', 'bullish_divergence']) {
    const macd = { id: 'm1', enabled: true, kind: 'price_action', type: 'macd', params: { fast_length: 12, slow_length: 26, signal_length: 9 }, op } as unknown as Condition;
    accepted(request({}, {}, [RSI_GT_50, macd]));
  }
});
test('the ATR stop, the ATR target and the chandelier trailing stop (I30) are accepted', () => {
  accepted(request({}, { stop: { mode: 'atr', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } } }));
  accepted(request({}, { take_profit: { mode: 'atr', pct: 0.15, r_multiple: 2, atr_mult: 3 } }));
  accepted(request({}, { trailing: { mode: 'chandelier', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 20 } } } }));
});

/* ---- built-ins that read broker data: they follow the flow rule ---------------------------------------------------- */
test("rank_by 'fnet' is refused without terminal.flow_indicator:fnet, as the legacy fnet card is", () => {
  refused(portfolio('fnet'), 'portfolio.rank_by', 'fnet');
  refused(request({}, {}, [RSI_GT_50, card('f1', 'fnet', { length: 5 })]), 'entry.conditions[1].type', 'fnet');
});
test("the legacy 'broker' and 'top5' cards are refused without their flow item, enabled or switched off", () => {
  refused(request({}, {}, [RSI_GT_50, card('b1', 'broker', { length: 5, broker: 'YU' })]), 'entry.conditions[1].type', 'broker');
  refused(request({}, {}, [RSI_GT_50, card('t1', 'top5', { length: 10 }, false)]), 'entry.conditions[1].type', 'top5');
  refused(request({}, { signals: { logic: 'any', conditions: [card('t2', 'top5', { length: 10 })] } }), 'exit.signals.conditions[0].type', 'top5');
});
test('the ranking table names an item for every ranking that reads one, and only fnet does today', () => {
  assert.deepEqual(Object.keys(RANK_ITEM), RANK_BY);
  assert.deepEqual(Object.entries(RANK_ITEM).filter(([, v]) => v).map(([k, v]) => [k, v]), [['fnet', { kind: 'flow_indicator', id: 'fnet' }]]);
});
