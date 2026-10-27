/* The requests the page builds pass the worker's checks field for field (lead decision 2026-10-26: an unknown key is
   refused, UNKNOWN_FIELD, so the page must never send one): every card the page can make, through core catalog.ts
   legacyToCondition / regToCondition (the page's api/compute.ts toWire), in the request shape of the page's
   api/request.ts buildRequest; the page's client_request_id is edge-bff's (it takes it out before the worker) and is
   refused here; a broker code is checked against the published broker list (UNKNOWN_BROKER). No market data. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import IND_REG from '../../edge-bff/terminal/src/data/indRegistry.json' with { type: 'json' };
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { DEFAULT_ENTRY, ENTRY_TEMPLATES, EXIT_TEMPLATES, LEGACY, legacyCard, legacyToCondition, regToCondition } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { LegacyCard, LegacyType, RegCard } from '../../edge-bff/backtest/src/core/catalog.ts';
import { BY_ID } from '../../edge-bff/backtest/src/core/registry.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { LEVEL_LINES } from '../../edge-bff/backtest/src/core/engine.ts';
import type { Config } from '../src/config.ts';
import { checkRequest, checkSignalsRequest } from '../src/validate.ts';
import type { References } from '../src/validate.ts';

const REFS: References = {
  tickers: [{ ticker: 'BBCA', name: 'BBCA (test name)', type: 'stock', sector: 'Sector A' }, { ticker: 'IHSG', name: 'IHSG (test name)', type: 'index', sector: null }],
  brokers: [{ code: 'YU', name: 'test broker', type: 'Foreign' }],
};
const CFG: Pick<Config, 'limits' | 'flow'> = {
  limits: { max_positions: 10, window_bars: { min: 1, max: 20 }, monte_carlo_runs: 1000, max_download_bytes: 1e9, max_broker_rows: 1e9, timeout_seconds: 600, queued_per_owner: 3, max_conditions: 20 },
  flow: { enabled: true, reason: null },
};
const codeOf = (f: () => unknown) => { try { f() } catch (e) { if (e instanceof ValidationError) return [e.code, e.field]; throw e } return null };

/** The page's registry card (src/reg.ts mkReg with regDefaults: every non-fixed parameter at its registry default,
    else false / the first option / ''; a panel compares its first output to a value, an overlay or volume indicator
    crosses the price over its first output). The value stands in for the page's median of the output. */
function regCard(id: string): RegCard {
  const r = (IND_REG as any[]).find(x => x.id === id);
  const p = Object.fromEntries(r.params.filter((x: any) => x.type !== 'fixed').map((x: any) => [x.k, x.def ?? (x.type === 'boolean' ? false : x.type === 'enum' ? (x.opts || [''])[0] : '')]));
  const out = r.outs[0].k;
  const cid = `r${id.toLowerCase()}`;                                // a page id: 1-6 base-36 digits (validate.ts CONDITION_ID)
  return r.zone === 'panel' ? { id: cid, type: 'reg', on: true, ind: id, p, lhs: { t: 'out', o: out }, op: 'gt', rhs: { t: 'val', v: 1 } }
    : { id: cid, type: 'reg', on: true, ind: id, p, lhs: { t: 'price' }, op: 'ca', rhs: { t: 'out', o: out } };
}
const legacy = ([t, over]: [LegacyType, Partial<LegacyCard>], k: number) => legacyToCondition(legacyCard(t, `c${k + 1}`, over));

/** The page's request (api/request.ts buildRequest, its state.ts boot settings) with these entry and exit conditions. */
function pageRequest(entry: Condition[], exit: Condition[] = [], mode: 'single' | 'portfolio' = 'single'): BacktestRequest {
  return {
    schema_version: 1, mode,
    ...(mode === 'single' ? { single: { ticker: 'BBCA', benchmark: 'buy_and_hold' as const } } : { portfolio: { universe: 'all', max_positions: 5, rank_by: 'adx' as const, min_avg_value_20d_idr: 5 * 1e9 } }),
    period: { from: '2019-06-03', to: '2026-10-23', oos_fraction: 30 / 100 as 0.3 },
    entry: { logic: 'at_least', at_least: 3, window_bars: 5, conditions: entry },
    exit: {
      atr_length: 14,
      stop: { mode: 'pct', pct: 7 / 100, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 15 / 100, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 5 / 100, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 20 } } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: exit },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 100 / 100 },
    costs: { buy_fee: .15 / 100, sell_fee: .25 / 100, slippage: .05 / 100, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
  };
}

test('every card the page can make passes the worker\'s checks: no field the worker does not read', () => {
  const sets: [string, Condition[]][] = [
    ['the page defaults', DEFAULT_ENTRY.map(legacy)],
    ...Object.entries(ENTRY_TEMPLATES).map(([k, cards]): [string, Condition[]] => [`template ${k}`, cards.map(legacy)]),
    // every legacy card type with every operator it offers
    ...(Object.keys(LEGACY) as LegacyType[]).flatMap(t => LEGACY[t].ops.map((op, k): [string, Condition[]] => [`${t} ${op}`, [legacy([t, { op }], k)]])),
    // every registry indicator the backtest can calculate, as the page's form builds it
    ...Object.values(BY_ID).filter(r => r.available_for_backtest).map((r): [string, Condition[]] => [`registry ${r.id}`, [regToCondition(regCard(r.id))]]),
  ];
  assert.ok(sets.length > 60, `${sets.length} sets`);
  const exits = Object.values(EXIT_TEMPLATES).map((x, k) => x.kind === 'reg'
    ? regToCondition({ ...regCard(x.ind), id: `x${k}`, p: { ...regCard(x.ind).p, ...(x.p ?? {}) }, lhs: x.lhs, op: x.op, rhs: x.rhs })
    : legacyToCondition(legacyCard(x.type, `x${k}`, x.over)));
  for (const [label, conditions] of sets) for (const mode of ['single', 'portfolio'] as const) {
    const q = pageRequest(conditions, exits, mode);
    assert.equal(codeOf(() => checkRequest(q, REFS, CFG)), null, `${label} (${mode})`);
    assert.equal(codeOf(() => checkSignalsRequest({ schema_version: 1, universe: 'all', period: { from: q.period.from, to: q.period.to }, entry: q.entry }, REFS, CFG)), null, `${label} (preview)`);
  }
  // every price line the page offers for a stop or a trailing stop, with and without its parameters
  for (const l of LEVEL_LINES) for (const params of [undefined, regCard(l.indicator).p]) {
    const q = pageRequest(DEFAULT_ENTRY.map(legacy));
    q.exit.stop = { ...q.exit.stop, mode: 'line', line: { indicator: l.indicator, output: l.output, ...(params ? { params: params as Record<string, number | string | boolean> } : {}) } };
    q.exit.trailing = { ...q.exit.trailing, mode: 'line', line: q.exit.stop.line };
    assert.equal(codeOf(() => checkRequest(q, REFS, CFG)), null, `line ${l.indicator} ${l.output}${params ? ' with params' : ''}`);
  }
});

test('a key the page does not send is refused, never ignored: client_request_id included (edge-bff takes it out)', () => {
  const q = pageRequest(DEFAULT_ENTRY.map(legacy));
  assert.deepEqual(codeOf(() => checkRequest({ ...q, client_request_id: 'c'.repeat(32) }, REFS, CFG)), ['UNKNOWN_FIELD', 'client_request_id']);
  assert.deepEqual(codeOf(() => checkRequest({ ...q, period: { ...q.period, client_request_id: 'x' } }, REFS, CFG)), ['UNKNOWN_FIELD', 'period.client_request_id']);
  assert.deepEqual(codeOf(() => checkSignalsRequest({ schema_version: 1, universe: 'all', period: { from: q.period.from, to: q.period.to }, entry: q.entry, client_request_id: 'x' }, REFS, CFG)), ['UNKNOWN_FIELD', 'client_request_id']);
});

test('a broker condition names a broker of the published broker list (UNKNOWN_BROKER), in the entry, the exit and the preview', () => {
  const card = (broker: string) => legacyToCondition(legacyCard('broker', 'b1', { broker }));
  const q = pageRequest([card('YU')]);
  assert.equal(codeOf(() => checkRequest(q, REFS, CFG)), null);
  assert.deepEqual(codeOf(() => checkRequest(pageRequest([card('XX')]), REFS, CFG)), ['UNKNOWN_BROKER', 'entry.conditions[0].params.broker']);
  assert.deepEqual(codeOf(() => checkRequest(pageRequest(DEFAULT_ENTRY.map(legacy), [{ ...card('yu'), id: 'x1' }]), REFS, CFG)), ['UNKNOWN_BROKER', 'exit.signals.conditions[0].params.broker']);
  assert.deepEqual(codeOf(() => checkSignalsRequest({ schema_version: 1, universe: 'all', period: { from: q.period.from, to: q.period.to }, entry: pageRequest([card('XX')]).entry }, REFS, CFG)), ['UNKNOWN_BROKER', 'entry.conditions[0].params.broker']);
  // a disabled card is not checked (the run does not read it); with flow off every flow card is FLOW_UNAVAILABLE first
  assert.equal(codeOf(() => checkRequest(pageRequest([...DEFAULT_ENTRY.map(legacy), { ...card('XX'), id: 'b2', enabled: false }]), REFS, CFG)), null);
  assert.deepEqual(codeOf(() => checkRequest(pageRequest([card('XX')]), REFS, { ...CFG, flow: { enabled: false, reason: 'off in this test' } })), ['FLOW_UNAVAILABLE', 'entry.conditions[0]']);
});

/** A refusal's code, field and details: validate.ts raises LIMIT_EXCEEDED as a WorkerError (422 with details). */
const refusalOf = (f: () => unknown) => { try { f() } catch (e) { const x = e as { code?: string; field?: string; details?: unknown }; return [x.code, x.field, x.details ?? null] } return null };
const preview = (entry: BacktestRequest['entry']) => ({ schema_version: 1, universe: 'all', period: { from: '2019-06-03', to: '2026-10-23' }, entry });

test('a condition id has the page\'s shape (1 to 6 base-36 digits), on every card of every list, enabled or not', () => {
  const card = (id: string, enabled = true) => ({ ...legacy(['volspike', {}], 0), id, enabled });
  for (const id of ['a', 'c1', 'k3x9zq', '000000']) assert.equal(codeOf(() => checkRequest(pageRequest([card(id)]), REFS, CFG)), null, id);
  for (const id of ['k3x9zq1', 'C1', 'c-1', 'c 1', 'ç1', 'x'.repeat(100000)]) {
    const label = id.slice(0, 10);
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([card(id)]), REFS, CFG)), ['INVALID_CONDITION', 'entry.conditions[0].id'], label);
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([card('c1'), card(id, false)]), REFS, CFG)), ['INVALID_CONDITION', 'entry.conditions[1].id'], `${label} disabled`);
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([card('c1')], [card(id)]), REFS, CFG)), ['INVALID_CONDITION', 'exit.signals.conditions[0].id'], `${label} exit`);
    assert.deepEqual(codeOf(() => checkSignalsRequest(preview(pageRequest([card(id)]).entry), REFS, CFG)), ['INVALID_CONDITION', 'entry.conditions[0].id'], `${label} preview`);
  }
});

test('a list has at most limits.max_conditions enabled conditions (LIMIT_EXCEEDED, details); disabled cards are not counted', () => {
  const max = CFG.limits.max_conditions;
  const cards = (n: number, enabled = true, prefix = 'c') => Array.from({ length: n }, (_, k) => ({ ...legacy(['volspike', {}], 0), id: `${prefix}${k}`, enabled }));
  const over = { limit: 'max_conditions', allowed: max, needed: max + 1 };
  assert.equal(refusalOf(() => checkRequest(pageRequest(cards(max)), REFS, CFG)), null);
  assert.equal(refusalOf(() => checkRequest(pageRequest([...cards(max), ...cards(5, false, 'd')]), REFS, CFG)), null, 'disabled cards are not counted');
  assert.deepEqual(refusalOf(() => checkRequest(pageRequest(cards(max + 1)), REFS, CFG)), ['LIMIT_EXCEEDED', 'entry.conditions', over]);
  assert.deepEqual(refusalOf(() => checkRequest(pageRequest(cards(1), cards(max + 1, true, 'x')), REFS, CFG)), ['LIMIT_EXCEEDED', 'exit.signals.conditions', over]);
  assert.equal(refusalOf(() => checkRequest(pageRequest(cards(max), cards(max, true, 'x')), REFS, CFG)), null, 'the limit is per list');
  assert.deepEqual(refusalOf(() => checkSignalsRequest(preview(pageRequest(cards(max + 1)).entry), REFS, CFG)), ['LIMIT_EXCEEDED', 'entry.conditions', over]);
  const two = { ...CFG, limits: { ...CFG.limits, max_conditions: 2 } };
  assert.deepEqual(refusalOf(() => checkRequest(pageRequest(cards(3)), REFS, two)), ['LIMIT_EXCEEDED', 'entry.conditions', { limit: 'max_conditions', allowed: 2, needed: 3 }]);
});

test('a disabled condition is held to the same shape as an enabled one: kind, fields, indicator, parameters, threshold', () => {
  // the codes and fields conditions.ts gives the enabled card; the disabled one is stored with the job and kept by the page
  const ok = legacy(['volspike', {}], 0);
  const deep: Record<string, unknown> = {}; let at = deep; for (let k = 0; k < 500; k++) { at.d = {}; at = at.d as Record<string, unknown> }
  const reg = regToCondition(regCard('I13'));
  const bad: [string, Record<string, unknown>, string, string][] = [
    ['an unknown kind with junk fields', { id: 'j1', kind: 'no-such-kind', anything: 'x'.repeat(50000), deep }, 'UNKNOWN_CONDITION', 'kind'],
    ['an unknown field', { ...ok, id: 'j2', anything: 'x' }, 'UNKNOWN_FIELD', 'anything'],
    ['an unknown indicator', { ...reg, id: 'j3', indicator: 'I99', params: { evil: [1, 2, 3], deep } }, 'UNKNOWN_INDICATOR', 'indicator'],
    ['a parameter the indicator does not take', { ...reg, id: 'j4', params: { ...(reg as { params: object }).params, evil: [1, 2, 3] } }, 'PARAM_NOT_ACCEPTED', 'params.evil'],
    ['a side that is not a side', { ...reg, id: 'j5', lhs: 'not-a-side' }, 'INVALID_CONDITION', 'lhs'],
    ['an operator the page does not offer', { ...reg, id: 'j6', op: 'zz' }, 'INVALID_CONDITION', 'op'],
    ['a threshold outside what it measures', { ...ok, id: 'j7', value: -1 }, 'VALUE_OUT_OF_RANGE', 'value'],
    ['a flow card without its parameters', { ...legacy(['broker', { broker: 'YU' }], 0), id: 'j8', params: {} }, 'INVALID_PARAM', 'params.length'],
  ];
  for (const [label, c, code, sub] of bad) for (const enabled of [true, false]) {
    const cond = { ...c, enabled } as unknown as Condition, what = `${label} (${enabled ? 'enabled' : 'disabled'})`;
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([ok, cond]), REFS, CFG)), [code, `entry.conditions[1].${sub}`], what);
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([ok], [cond]), REFS, CFG)), [code, `exit.signals.conditions[0].${sub}`], `${what} exit`);
    assert.deepEqual(codeOf(() => checkSignalsRequest(preview(pageRequest([ok, cond]).entry), REFS, CFG)), [code, `entry.conditions[1].${sub}`], `${what} preview`);
  }
});

test('a number or price line the chosen modes do not read is held to its type all the same (review VAL-1)', () => {
  // contract.ts types every one of these fields; they are stored with the job and hashed into request_hash, so any other
  // JSON there was kept unchecked (a 4000-deep object in exit.stop.line under stop pct passed /v1/validate, then failed
  // POST /v1/jobs with 500 when the job was handed to its thread: server.test.ts)
  const deep: Record<string, unknown> = {}; let at = deep; for (let k = 0; k < 300; k++) { at.d = {}; at = at.d as Record<string, unknown> }
  const bad: [string, (q: BacktestRequest) => void, string, string][] = [
    ['stop.atr_mult a string (stop pct)', q => { (q.exit.stop as any).atr_mult = 'x' }, 'INVALID_EXIT', 'exit.stop.atr_mult'],
    ['stop.reward_risk_x null (stop pct)', q => { (q.exit.stop as any).reward_risk_x = null }, 'INVALID_EXIT', 'exit.stop.reward_risk_x'],
    ['stop.pct missing (stop atr)', q => { q.exit.stop.mode = 'atr'; delete (q.exit.stop as any).pct }, 'INVALID_EXIT', 'exit.stop.pct'],
    ['stop.line a number (stop pct)', q => { (q.exit.stop as any).line = 12345 }, 'INVALID_EXIT', 'exit.stop.line'],
    ['stop.line an unknown indicator (stop pct)', q => { q.exit.stop.line = { indicator: 'I999', output: 'nope', params: { deep } as any } }, 'UNKNOWN_INDICATOR', 'exit.stop.line.indicator'],
    ['stop.line params nested (stop pct)', q => { q.exit.stop.line = { indicator: 'I09', output: 'supertrend', params: { deep } as any } }, 'PARAM_NOT_ACCEPTED', 'exit.stop.line.params.deep'],
    ['trailing.line params nested (trailing none)', q => { q.exit.trailing.line = { indicator: 'I01', output: 'sma', params: { length: deep } as any } }, 'INVALID_PARAM', 'exit.trailing.line.params.length'],
    ['trailing.line not a price line (trailing none)', q => { q.exit.trailing.line = { indicator: 'I13', output: 'rsi' } }, 'INVALID_LINE', 'exit.trailing.line.indicator'],
    ['take_profit.r_multiple an object (tp pct)', q => { (q.exit.take_profit as any).r_multiple = { a: [1, 2, 3] } }, 'INVALID_EXIT', 'exit.take_profit.r_multiple'],
    ['take_profit.atr_mult a string (tp pct)', q => { (q.exit.take_profit as any).atr_mult = '3' }, 'INVALID_EXIT', 'exit.take_profit.atr_mult'],
    ['trailing.pct a list (trailing none)', q => { (q.exit.trailing as any).pct = [0.05] }, 'INVALID_EXIT', 'exit.trailing.pct'],
    ['trailing.chandelier_length a string (trailing none)', q => { (q.exit.trailing as any).chandelier_length = '22' }, 'INVALID_EXIT', 'exit.trailing.chandelier_length'],
    ['trailing.chandelier_mult null (trailing none)', q => { (q.exit.trailing as any).chandelier_mult = null }, 'INVALID_EXIT', 'exit.trailing.chandelier_mult'],
    ['exit.atr_length a string (no ATR mode)', q => { (q.exit as any).atr_length = '14' }, 'INVALID_EXIT', 'exit.atr_length'],
    ['entry.at_least an array (logic all)', q => { q.entry.logic = 'all'; (q.entry as any).at_least = [1, 2] }, 'INVALID_ENTRY', 'entry.at_least'],
    ['sizing.allocation_fraction a string (portfolio)', q => { q.mode = 'portfolio'; delete q.single; q.portfolio = { universe: 'all', max_positions: 3, rank_by: 'adx', min_avg_value_20d_idr: 0 }; (q.sizing as any).allocation_fraction = 'x' }, 'INVALID_SIZING', 'sizing.allocation_fraction'],
  ];
  for (const [label, f, code, field] of bad) { const q = pageRequest(DEFAULT_ENTRY.map(legacy)); f(q); assert.deepEqual(codeOf(() => checkRequest(q, REFS, CFG)), [code, field], label) }
  assert.deepEqual(codeOf(() => checkSignalsRequest(preview({ ...pageRequest(DEFAULT_ENTRY.map(legacy)).entry, logic: 'any', at_least: deep as any }), REFS, CFG)), ['INVALID_ENTRY', 'entry.at_least'], 'preview');
  // what the page can send for a field it no longer shows is a number (builder.ts: +input, a cleared input is 0): only
  // the type is held, never the range the mode would check (engine.ts validateRun)
  const kept: [string, (q: BacktestRequest) => void][] = [
    ['cleared inputs', q => { q.exit.stop.atr_mult = 0; q.exit.stop.reward_risk_x = 0; q.exit.take_profit.r_multiple = 0; q.exit.take_profit.atr_mult = 0; q.exit.trailing.pct = 0; q.exit.trailing.chandelier_length = 0; q.exit.trailing.chandelier_mult = 0; q.exit.atr_length = 0 }],
    ['negative and fractional numbers', q => { q.exit.stop.atr_mult = -2; q.exit.atr_length = -5; q.exit.trailing.chandelier_length = 2.5 }],
    ['at_least 0 under ALL', q => { q.entry.logic = 'all'; q.entry.at_least = 0 }],
    ['at_least 2.5 under ANY', q => { q.entry.logic = 'any'; q.entry.at_least = 2.5 }],
    ['allocation 0 in a portfolio', q => { q.mode = 'portfolio'; delete q.single; q.portfolio = { universe: 'all', max_positions: 3, rank_by: 'adx', min_avg_value_20d_idr: 0 }; q.sizing.allocation_fraction = 0 }],
  ];
  for (const [label, f] of kept) { const q = pageRequest(DEFAULT_ENTRY.map(legacy)); f(q); assert.equal(codeOf(() => checkRequest(q, REFS, CFG)), null, label) }
});

test('a price-action condition holds only what its type reads: no value without a threshold, params an object, op a string (review VAL-1)', () => {
  const deep: Record<string, unknown> = {}; let at = deep; for (let k = 0; k < 300; k++) { at.d = {}; at = at.d as Record<string, unknown> }
  const breakout = legacy(['breakout', {}], 0), macd = legacy(['macd', {}], 0), dip = legacy(['dip', {}], 0);
  const bad: [string, Record<string, unknown>, string, string][] = [
    ['a value on breakout', { ...breakout, value: deep }, 'UNKNOWN_FIELD', 'value'],
    ['a value on macd', { ...macd, value: 1 }, 'UNKNOWN_FIELD', 'value'],
    ['params a number', { ...breakout, params: 5 }, 'INVALID_PARAMS', 'params'],
    ['params null', { ...breakout, params: null }, 'INVALID_PARAMS', 'params'],
    ['params a list', { ...dip, params: [] }, 'INVALID_PARAMS', 'params'],
    ['op null', { ...breakout, op: null }, 'INVALID_CONDITION', 'op'],
  ];
  for (const [label, c, code, sub] of bad) for (const enabled of [true, false]) {
    const cond = { ...c, enabled } as unknown as Condition, what = `${label} (${enabled ? 'enabled' : 'disabled'})`;
    assert.deepEqual(codeOf(() => checkRequest(pageRequest([dip, { ...cond, id: 'c9' } as Condition]), REFS, CFG)), [code, `entry.conditions[1].${sub}`], what);
    assert.deepEqual(codeOf(() => checkSignalsRequest(preview(pageRequest([dip, { ...cond, id: 'c9' } as Condition]).entry), REFS, CFG)), [code, `entry.conditions[1].${sub}`], `${what} preview`);
  }
  // the page's own cards: a threshold on dip and volspike only, no op means the type's one, no params on dip
  const { op: _op, ...noOp } = breakout as { op?: string };
  for (const c of [breakout, macd, dip, legacy(['volspike', {}], 0), noOp as Condition, { ...dip, params: {} } as Condition])
    assert.equal(codeOf(() => checkRequest(pageRequest([{ ...c, id: 'c1' } as Condition]), REFS, CFG)), null, JSON.stringify(c));
});
