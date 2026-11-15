/* EXEC-BACKTEST-REVAMP P0.1 (ERRORS M449): the absolute lineage key, variant hash and request hash of a set of legacy
   requests, frozen. Trials are counted per (owner, lineage) and keyed by variant hash in edge_bff.backtest_trials, so a
   refactor of hash.ts that changes any of these values silently splits or merges stored trial lines. A change is made
   only on purpose (user decision K7 a, 2026-11-15) and then recorded here: GOLDEN_UPDATE=1 npm test. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { LEGACY, legacyCard, legacyToCondition } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { LegacyType } from '../../edge-bff/backtest/src/core/catalog.ts';
import { canonicalRequest, lineageKey, requestHash, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';

const FILE = new URL('./hash-golden.json', import.meta.url).pathname;
const VERSIONS = { engine_version: 'e'.repeat(16), registry_version: 'r'.repeat(16), data_version: 'd'.repeat(64) };
const card = (t: LegacyType, id: string, over: Record<string, unknown> = {}) => legacyToCondition(legacyCard(t, id, over as never));

function base(conditions: Condition[], over: Partial<BacktestRequest> = {}): BacktestRequest {
  return {
    schema_version: 1, mode: 'single', single: { ticker: 'BBCA', benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: '2026-10-23', oos_fraction: 0.3 },
    entry: { logic: 'at_least', at_least: 2, window_bars: 5, conditions },
    exit: {
      atr_length: 14,
      stop: { mode: 'pct', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: [] },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
    ...over,
  } as BacktestRequest;
}

function requests(): Record<string, BacktestRequest> {
  const all = (Object.keys(LEGACY) as LegacyType[]).map((t, k) => card(t, `c${k + 1}`));
  const rsiEmpty: Condition = { id: 'r1', enabled: true, kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } } as Condition;
  const rsiFull: Condition = { ...rsiEmpty, params: { length: 14, source: 'close' } } as Condition;
  const out: Record<string, BacktestRequest> = {};
  for (const t of Object.keys(LEGACY) as LegacyType[]) out[`legacy:${t}`] = base([card(t, 'c1')]);
  out['legacy:all'] = base(all);
  out['legacy:all:disabled-one'] = base(all.map((c, k) => k === 2 ? { ...c, enabled: false } as Condition : c));
  out['rsi:params-empty'] = base([rsiEmpty]);
  out['rsi:params-full'] = base([rsiFull]);
  out['exit-signal'] = base([card('rsi', 'c1')], { exit: { ...base([]).exit, signals: { logic: 'all', conditions: [card('macross', 'x1'), card('dip', 'x2')] } } });
  out['portfolio'] = base([card('adx', 'c1'), card('volspike', 'c2')], { mode: 'portfolio', single: undefined,
    portfolio: { tickers: ['UNVR', 'BBCA', 'GOTO'], max_positions: 5, rank_by: 'adx', min_avg_value_20d_idr: 5e9 } } as Partial<BacktestRequest>);
  return out;
}

test('legacy requests keep their absolute lineage, variant and request hashes (EXEC-BACKTEST-REVAMP P0.1)', async () => {
  const got: Record<string, [string, string, string]> = {};
  for (const [k, q0] of Object.entries(requests())) {
    const q = canonicalRequest(q0);
    got[k] = [await lineageKey(q), await variantHash(q), await requestHash(q, VERSIONS)];
  }
  if (process.env.GOLDEN_UPDATE === '1') fs.writeFileSync(FILE, JSON.stringify(got, null, 1) + '\n');
  assert.deepEqual(got, JSON.parse(fs.readFileSync(FILE, 'utf8')));
});
