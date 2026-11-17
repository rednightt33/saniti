/* EDGE multi-user Phase 3b (verification/edge_multiuser/access_tiers/CONTRACT.md section 8b, "3b in detail"): the plan's
   items (context.allow) and limits (context.limits) as validate.ts and run.ts apply them, without the HTTP layer
   (tests/server.test.ts calls the routes). Every place a request names an item is refused with the item's JSON path and
   its Backtest capability when allow lacks it, and passes when allow holds it; "*" and an absent allow pass everything;
   a malformed allow or limits is INVALID_CONTEXT; a plan's limit is the smaller of the two. No market data. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { BacktestRequest, Condition } from '../../edge-bff/backtest/src/core/contract.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { CANDLE_IDS } from '../../edge-bff/backtest/src/core/candles.ts';
import { ALLOW_ALL, ALLOW_KINDS, FAMILY, allowOf, applyLimits, limitsOf, requireItem } from '../src/access.ts';
import type { Allow } from '../src/access.ts';
import type { Config } from '../src/config.ts';
import { WorkerError, toApiError } from '../src/errors.ts';
import { testItems } from '../src/grammar.ts';
import { contextGrants } from '../src/server.ts';
import { checkRequest, checkSignalsRequest } from '../src/validate.ts';
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

const close = { kind: 'price', field: 'close' };
const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi', params: {} };
const T = (id: string, test: unknown, enabled = true) => ({ id, enabled, kind: 'test', test }) as unknown as Condition;
/** a registry indicator condition (kind 'indicator'), as the page's registry card writes it */
const IND = (id: string, enabled = true) => ({ id, enabled, kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'gt', rhs: { type: 'value', value: 50 } }) as unknown as Condition;

function request(entry: Condition[], exit: Condition[] = []): BacktestRequest {
  return {
    schema_version: 1, mode: 'single', single: { ticker: 'BBCA', benchmark: 'buy_and_hold' },
    period: { from: '2019-06-03', to: '2026-10-23', oos_fraction: 0.3 },
    entry: { logic: 'any', at_least: 1, window_bars: 5, conditions: entry },
    exit: {
      atr_length: 14,
      stop: { mode: 'line', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } },
      take_profit: { mode: 'pct', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma', params: { length: 20 } } },
      max_hold_bars: 20, signals: { logic: 'any', conditions: exit },
    },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 },
    costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: true, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 1000, seed: 7, sensitivity: true },
  };
}

/** Every item the request below names, with its path: the full set a plan must hold to run it. */
const ENTRY: Condition[] = [
  IND('a1'),                                                                                                            // entry.conditions[0].indicator
  T('a2', { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: {} } }),   // [1].test.rhs.indicator
  T('a3', { kind: 'event', within: 3, signal: { lhs: { kind: 'flow', metric: 'FL17', params: { window: 20 } }, op: 'crosses_above', rhs: close } }),   // [2].test.signal.lhs.metric
  T('a4', { kind: 'state', pattern: { kind: 'pattern', type: 'hammer', params: {} } }),                                 // [3].test.pattern.type (candle)
  T('a5', { kind: 'event', within: 3, signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: 60 } } } }),   // [4].test.signal.pattern.type (Screener)
  // a transform has no id: the indicator inside it is checked
  T('a6', { kind: 'value', metric: { kind: 'transform', fn: 'change', of: { kind: 'indicator', indicator: 'I07', output: 'adx', params: {} }, args: { bars: 1 } }, op: 'gt', value: 0 }),
  // switched off: still checked (it is stored with the job)
  T('a7', { kind: 'window', mode: 'ever', length: 5, test: { kind: 'value', metric: { kind: 'indicator', indicator: 'I14', output: 'k', params: {} }, op: 'gt', value: 80 } }, false),
];
const EXIT: Condition[] = [T('x1', { kind: 'event', within: 1, signal: { lhs: rsi, op: 'crosses_below', rhs: { value: 70 } } })];
const NAMED: [string, string, string][] = [   // [field, kind, id]
  ['entry.conditions[0].indicator', 'indicator', 'I13'],
  ['entry.conditions[1].test.rhs.indicator', 'indicator', 'I01'],
  ['entry.conditions[2].test.signal.lhs.metric', 'flow_indicator', 'FL17'],
  ['entry.conditions[3].test.pattern.type', 'candle_pattern', 'hammer'],
  ['entry.conditions[4].test.signal.pattern.type', 'screener_metric', 'breakout'],
  ['entry.conditions[5].test.metric.of.indicator', 'indicator', 'I07'],
  ['entry.conditions[6].test.test.metric.indicator', 'indicator', 'I14'],
  ['exit.signals.conditions[0].test.signal.lhs.indicator', 'indicator', 'I13'],
  ['exit.stop.line.indicator', 'indicator', 'I09'],
  ['exit.trailing.line.indicator', 'indicator', 'I01'],
];
/** allow holding exactly the items NAMED lists, less the ones `without` drops (an id named twice stays while another
    place names it) */
function allowOf_(without: (kind: string, id: string) => boolean = () => false): Allow {
  const a: Record<string, string[]> = Object.fromEntries(ALLOW_KINDS.map(k => [k, []]));
  for (const [, kind, id] of NAMED) if (!without(kind, id) && !a[kind].includes(id)) a[kind].push(id);
  return allowOf(a);
}
const refusal = (f: () => unknown) => {
  try { f() } catch (e) { if (e instanceof WorkerError || e instanceof ValidationError) { const a = toApiError(e); return { status: a.status, ...a.error } } throw e }
  return null;
};

test('the request passes with every item it names allowed, with "*" for every kind, and with allow left out', () => {
  const q = request(ENTRY, EXIT);
  assert.equal(refusal(() => checkRequest(q, REFS, CFG, undefined, allowOf_())), null);
  assert.equal(refusal(() => checkRequest(q, REFS, CFG, undefined, allowOf({ indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*' }))), null);
  assert.equal(refusal(() => checkRequest(q, REFS, CFG)), null);                         // internal calls: everything
  assert.equal(refusal(() => checkRequest(q, REFS, CFG, undefined, ALLOW_ALL)), null);
  // the walk finds every item of a test (testItems), and only those
  const found = ENTRY.flatMap((c, k) => (c as { kind: string }).kind === 'test' ? testItems((c as { test: unknown }).test, `entry.conditions[${k}].test`) : []);
  assert.deepEqual(found.map(x => [x.field, x.kind, x.id]), NAMED.filter(([f]) => f.startsWith('entry.conditions[') && f.includes('.test.')));
});

test('every place an item is named: refused 403 CAPABILITY_REQUIRED at its JSON path with the Backtest capability', () => {
  const q = request(ENTRY, EXIT);
  // each item alone left out of allow: the refusal names the first place it appears in the order of the checks
  // (the price lines before the conditions, entry before exit)
  const order = [...NAMED.filter(([f]) => f.startsWith('exit.') && f.includes('.line.')), ...NAMED.filter(([f]) => !f.includes('.line.'))];
  const ids = [...new Set(NAMED.map(([, kind, id]) => `${kind}\t${id}`))];
  for (const key of ids) {
    const [kind, id] = key.split('\t');
    const first = order.find(([, k, i]) => k === kind && i === id)!;
    const r = refusal(() => checkRequest(q, REFS, CFG, undefined, allowOf_((k, i) => k === kind && i === id)));
    const capability = `${FAMILY[kind as keyof typeof FAMILY]}:${id}`;
    assert.deepEqual(r && { status: r.status, code: r.code, field: r.field, details: r.details }, { status: 403, code: 'CAPABILITY_REQUIRED', field: first[0], details: { kind, id, capability } }, key);
    assert.ok(r!.message!.includes(id) && r!.message!.includes('not included in your plan') && r!.message!.includes(capability), r!.message);
  }
  // the families: a Backtest item is backtest.<kind>, a Screener metric screener.metric
  assert.deepEqual(FAMILY, { indicator: 'backtest.indicator', flow_indicator: 'backtest.flow_indicator', candle_pattern: 'backtest.candle_pattern', screener_metric: 'screener.metric' });
  // every candle id of the core's registry is a candle_pattern; any other pattern type a screener_metric
  for (const id of CANDLE_IDS) assert.equal(testItems({ kind: 'state', pattern: { kind: 'pattern', type: id } }, 't')[0].kind, 'candle_pattern', id);
  assert.equal(testItems({ kind: 'state', pattern: { kind: 'pattern', type: 'squeeze' } }, 't')[0].kind, 'screener_metric');
  // a universe attribute and a cross-section metric are Screener metrics (the backtest then refuses them as not per day)
  assert.deepEqual(testItems({ kind: 'value', metric: { kind: 'universe', attr: 'pe' }, op: 'gt', value: 1 }, 't'), [{ kind: 'screener_metric', id: 'pe', field: 't.metric.attr' }]);
  assert.deepEqual(testItems({ kind: 'value', metric: { kind: 'xsection', metric: 'return_rank' }, op: 'gt', value: 1 }, 't'), [{ kind: 'screener_metric', id: 'return_rank', field: 't.metric.metric' }]);
  const pe = request([T('u1', { kind: 'value', metric: { kind: 'universe', attr: 'pe' }, op: 'gt', value: 1 })]);
  assert.equal(refusal(() => checkRequest(pe, REFS, CFG, undefined, allowOf_()))?.code, 'CAPABILITY_REQUIRED');
  assert.equal(refusal(() => checkRequest(pe, REFS, CFG, undefined, ALLOW_ALL))?.code, 'CONDITION_UNAVAILABLE');
  // the four transform metrics carry no id on the wire: nothing to check by id
  assert.deepEqual(testItems({ kind: 'value', metric: { kind: 'transform', fn: 'pct_distance', of: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } }, args: {} }, op: 'gt', value: -5 }, 't'), []);
});

test('a price line is checked whatever its mode, and the point-in-time right still applies to an allowed D item', () => {
  const q = request([IND('a1')]);
  q.exit.stop.mode = 'pct';                                                              // the line is not read, but stored
  const a = allowOf({ indicator: ['I13', 'I01'], flow_indicator: [], candle_pattern: [], screener_metric: [] });
  assert.deepEqual(refusal(() => checkRequest(q, REFS, CFG, undefined, a))?.field, 'exit.stop.line.indicator');
  const d = request([IND('a1'), T('d1', { kind: 'value', metric: { kind: 'flow', metric: 'FL45', params: { anchor: '2026-01-02' } }, op: 'gt', value: 5 }, false)]);
  const all = allowOf({ indicator: '*', flow_indicator: ['FL45'], candle_pattern: [], screener_metric: [] });
  const none = allowOf({ indicator: '*', flow_indicator: ['FL01'], candle_pattern: [], screener_metric: [] });
  assert.deepEqual(refusal(() => checkRequest(d, REFS, CFG, new Set(['flow_point_in_time']), none))?.details, { kind: 'flow_indicator', id: 'FL45', capability: 'backtest.flow_indicator:FL45' });
  assert.equal(refusal(() => checkRequest(d, REFS, CFG, new Set(), all))?.code, 'CONDITION_RESTRICTED');
  assert.equal(refusal(() => checkRequest(d, REFS, CFG, new Set(['flow_point_in_time']), all)), null);
});

test('signals preview: the entry and detail.exit_signals items, the latter at their own path', () => {
  const p = { schema_version: 1, tickers: ['BBCA'], period: { from: '2024-01-02', to: '2026-10-23' }, entry: { logic: 'any', at_least: 1, window_bars: 5, conditions: [IND('a1')] },
    detail: { ticker: 'BBCA', exit_signals: { logic: 'any', conditions: [EXIT[0], T('x2', { kind: 'state', pattern: { kind: 'pattern', type: 'doji_star_not_a_candle' } }, false)] } } };
  // everything allowed: the unknown pattern type is the Screener validation's refusal (422), not the plan's
  assert.equal(refusal(() => checkSignalsRequest(p, REFS, CFG))?.status, 422);
  const only = (ids: string[], metrics: string[] = []) => allowOf({ indicator: ids, flow_indicator: [], candle_pattern: [], screener_metric: metrics });
  assert.deepEqual(refusal(() => checkSignalsRequest(p, REFS, CFG, undefined, only([]))), {
    status: 403, code: 'CAPABILITY_REQUIRED', field: 'entry.conditions[0].indicator', details: { kind: 'indicator', id: 'I13', capability: 'backtest.indicator:I13' },
    message: 'entry.conditions[0].indicator: the indicator I13 is not included in your plan (backtest.indicator:I13); remove it or change the plan to run this strategy.' });
  // a switched-off exit condition naming an unknown pattern type: the plan check comes first, and names the true path
  assert.deepEqual(refusal(() => checkSignalsRequest(p, REFS, CFG, undefined, only(['I13'])))?.field, 'detail.exit_signals.conditions[1].test.pattern.type');
  assert.deepEqual(refusal(() => checkSignalsRequest(p, REFS, CFG, undefined, only(['I13'])))?.details, { kind: 'screener_metric', id: 'doji_star_not_a_candle', capability: 'screener.metric:doji_star_not_a_candle' });
  const q = { ...p, detail: { ticker: 'BBCA', exit_signals: { logic: 'any', conditions: [EXIT[0]] } } };
  assert.equal(refusal(() => checkSignalsRequest(q, REFS, CFG, undefined, only(['I13']))), null);
  assert.equal(refusal(() => checkSignalsRequest(q, REFS, CFG, undefined, allowOf({ indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*' }))), null);
});

test('allow and limits: the shapes refused as INVALID_CONTEXT, with the key and how to fix it', () => {
  const ok = { indicator: '*', flow_indicator: ['FL01'], candle_pattern: [], screener_metric: ['breakout', 'hi52'] };
  assert.deepEqual(allowOf(ok), ok);
  assert.equal(allowOf(undefined), ALLOW_ALL);
  const bad: [unknown, string][] = [
    [null, 'context.allow'], ['*', 'context.allow'], [[], 'context.allow'],
    [{ ...ok, screener_preset: '*' }, 'context.allow.screener_preset'],
    [{ indicator: '*', flow_indicator: '*', candle_pattern: '*' }, 'context.allow.screener_metric'],
    [{ ...ok, indicator: 'all' }, 'context.allow.indicator'], [{ ...ok, indicator: ['I01', 'I01'] }, 'context.allow.indicator'],
    [{ ...ok, indicator: ['I01', 7] }, 'context.allow.indicator'], [{ ...ok, indicator: [''] }, 'context.allow.indicator'], [{ ...ok, indicator: null }, 'context.allow.indicator'],
  ];
  for (const [v, field] of bad) {
    const r = refusal(() => allowOf(v));
    assert.deepEqual(r && [r.status, r.code, r.field], [422, 'INVALID_CONTEXT', field], JSON.stringify(v));
    assert.ok(r!.message!.startsWith(field), r!.message);
  }
  assert.deepEqual(limitsOf(undefined), {});
  assert.deepEqual(limitsOf({}), {});
  assert.deepEqual(limitsOf({ max_portfolio_tickers: 5, max_broker_rows: 0 }), { max_portfolio_tickers: 5, max_broker_rows: 0 });
  for (const [v, field] of [[[], 'context.limits'], [5, 'context.limits'], [{ max_tickers: 5 }, 'context.limits.max_tickers'], [{ timeout_seconds: 5 }, 'context.limits.timeout_seconds'],
    [{ queued_per_owner: 1 }, 'context.limits.queued_per_owner'], [{ max_conditions: 0 }, 'context.limits.max_conditions'], [{ max_conditions: 2.5 }, 'context.limits.max_conditions'],
    [{ max_conditions: '3' }, 'context.limits.max_conditions'], [{ max_broker_rows: -1 }, 'context.limits.max_broker_rows']] as [unknown, string][]) {
    const r = refusal(() => limitsOf(v));
    assert.deepEqual(r && [r.status, r.code, r.field], [422, 'INVALID_CONTEXT', field], JSON.stringify(v));
  }
  // the context as a whole (server.ts contextGrants): each part optional, any other key refused
  assert.deepEqual(contextGrants(undefined), { rights: [], allow: ALLOW_ALL, limits: {} });
  assert.deepEqual(contextGrants({ rights: [], allow: ok, limits: {} }), { rights: [], allow: ok, limits: {} });
  assert.deepEqual(refusal(() => contextGrants({ allow: ok, plan: 'paid' }))?.field, 'context.plan');
  assert.deepEqual(refusal(() => contextGrants({ allow: { ...ok, indicator: 'I01' } }))?.field, 'context.allow.indicator');
  // requireItem alone
  assert.equal(refusal(() => requireItem(allowOf(ok), 'flow_indicator', 'FL01', 'f')), null);
  assert.equal(refusal(() => requireItem(allowOf(ok), 'flow_indicator', 'FL02', 'f'))?.status, 403);
});

test('limits: the plan lowers a limit (the smaller of the two), never raises one; the checks then name the plan\'s value', () => {
  assert.equal(applyLimits(CFG.limits, {}), CFG.limits);
  assert.deepEqual(applyLimits(CFG.limits, { max_conditions: 2, max_portfolio_tickers: 999 }), { ...CFG.limits, max_conditions: 2 });
  const lowered = { ...CFG, limits: applyLimits(CFG.limits, { max_conditions: 1 }) };
  const q = request([IND('a1'), IND('a2')]);
  assert.equal(refusal(() => checkRequest(q, REFS, CFG)), null);
  assert.deepEqual(refusal(() => checkRequest(q, REFS, lowered))?.details, { limit: 'max_conditions', allowed: 1, needed: 2 });
  const p = { schema_version: 1, tickers: ['BBCA', 'BMRI'], period: { from: '2024-01-02', to: '2026-10-23' }, entry: { logic: 'any', at_least: 1, window_bars: 5, conditions: [IND('a1')] } };
  assert.equal(refusal(() => checkSignalsRequest(p, REFS, CFG)), null);
  assert.equal(refusal(() => checkSignalsRequest(p, REFS, { ...CFG, limits: applyLimits(CFG.limits, { max_portfolio_tickers: 1 }) }))?.code, 'INVALID_PORTFOLIO');
});

test('legacy cards: a type that is a catalog id is gated by that id (derived from the registries); a built-in type is not', async () => {
  const { LEGACY, legacyCard, legacyToCondition } = await import('../../edge-bff/backtest/src/core/catalog.ts');
  const { legacyItemKind } = await import('../src/validate.ts');
  const card = (t: string, over: Record<string, unknown> = {}) => legacyToCondition(legacyCard(t as never, 'c1', over as never));
  const with_ = (kind: string, ids: string[]) => allowOf({ indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*', [kind]: ids });
  // the overlap today, derived: breakout, volspike, macross (Screener metrics), fnet (a Flow indicator); the rest built in
  const kinds = Object.fromEntries(Object.keys(LEGACY).map(t => [t, (card(t) as { kind: string }).kind === 'indicator' ? 'registry' : legacyItemKind((card(t) as { type: string }).type)]));
  assert.deepEqual(kinds, { adx: 'registry', dmi: 'registry', stoch: 'registry', rsi: 'registry', macd: null, ma: 'registry', macross: 'screener_metric', volspike: 'screener_metric',
    breakout: 'screener_metric', bb: 'registry', dip: null, fnet: 'flow_indicator', broker: null, top5: null });
  const breakout = request([card('breakout')]);
  assert.deepEqual(refusal(() => checkRequest(breakout, REFS, CFG, undefined, with_('screener_metric', ['volspike']))), {
    status: 403, code: 'CAPABILITY_REQUIRED', field: 'entry.conditions[0].type', details: { kind: 'screener_metric', id: 'breakout', capability: 'screener.metric:breakout' },
    message: 'entry.conditions[0].type: the Screener metric breakout is not included in your plan (screener.metric:breakout); remove it or change the plan to run this strategy.' });
  assert.equal(refusal(() => checkRequest(breakout, REFS, CFG, undefined, with_('screener_metric', ['breakout']))), null);
  // a switched-off fnet card in the exit signals: refused at its path, allowed with fnet
  const fnet = request([card('breakout')], [{ ...card('fnet'), id: 'x1', enabled: false } as Condition]);
  assert.deepEqual(refusal(() => checkRequest(fnet, REFS, CFG, undefined, with_('flow_indicator', ['FL01'])))?.details, { kind: 'flow_indicator', id: 'fnet', capability: 'backtest.flow_indicator:fnet' });
  assert.equal(refusal(() => checkRequest(fnet, REFS, CFG, undefined, with_('flow_indicator', ['FL01'])))?.field, 'exit.signals.conditions[0].type');
  assert.equal(refusal(() => checkRequest(fnet, REFS, CFG, undefined, with_('flow_indicator', ['fnet']))), null);
  // built-in types (dip, macd, top5, broker) pass with nothing of their kinds allowed
  const builtIn = request([card('dip'), card('macd'), card('top5'), card('broker', { broker: 'YU' })].map((c, k) => ({ ...c, id: `b${k}` }) as Condition));
  const nothing = allowOf({ indicator: '*', flow_indicator: [], candle_pattern: [], screener_metric: [] });
  assert.equal(refusal(() => checkRequest(builtIn, REFS, CFG, undefined, nothing)), null);
});
