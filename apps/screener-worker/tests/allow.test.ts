/* EXEC-MU-ACCOUNTS Phase 3b (verification/edge_multiuser/access_tiers/CONTRACT.md section 8b "3b in detail", and the
   "3b follow-up": the families from the Terminal, step 3 of the deploy order): the body's `context.allow` and
   `context.limits` (run.ts parseContext, checkAllow, effectiveLimits; server.ts gate after normalize). Locked here: every
   place a definition can name an item refused 403 CAPABILITY_REQUIRED with its JSON path and the capability edge-bff
   checks (the Terminal's family for the indicator and Flow kinds) when `allow` lacks it, and accepted when it holds it;
   "*" allows all; an absent allow, or no context, refused INVALID_CONTEXT naming context.allow on every route (step 3);
   a malformed context INVALID_CONTEXT naming the field; the
   limits as min(the worker's own ceiling, the plan's); a result cached for a principal with the item still refused for
   one without it; /counts refusing per entry; the internal calls (presets, normalize) never gated. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { after, before, test } from 'node:test';
import { SHOWN_ATTRIBUTES } from '../../edge-bff/screener/src/core/catalog.ts';
import { ALLOW_ALL, checkAllow, definitionItems, effectiveLimits, parseContext } from '../src/run.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { brokerRowsOf as fakeRows, startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';

captureLogs();
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const RSI = { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' };
const ALL = { indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*' };
/** `allow` with every id of the definition but the one left out (and "*" for the other kinds). */
const without = (kind: string, id: string, ids: string[]) => ({ ...ALL, [kind]: ids.filter(x => x !== id) });

/* One definition naming an item at every place the wire allows (indices fixed: the expected paths below). Its first
   metric filter reads chg_1d_pct, a universe attribute every answer shows: not an item (catalog.ts SHOWN_ATTRIBUTES;
   CONTRACT 8b O3b-2 and re-check R1-35, user 2026-11-19 "1a"; until then it was the walk's first item), so the filter
   place is covered by the second, an indicator. */
const FULL = {
  universe: { ...U, metric_filters: [{ kind: 'value', metric: { kind: 'universe', attr: 'chg_1d_pct' }, op: 'gt', value: -100 },
    { kind: 'value', metric: { kind: 'indicator', indicator: 'I07', params: {}, output: 'adx' }, op: 'gt', value: -1 }] },
  conditions: [
    { id: 'a', enabled: true, test: { kind: 'value', metric: RSI, op: 'lt', value: 101 } },
    { id: 'b', enabled: true, test: { kind: 'event', signal: { pattern: { kind: 'pattern', type: 'hammer', params: {} } }, within: 3 } },
    { id: 'c', enabled: true, test: { kind: 'state', pattern: { kind: 'pattern', type: 'breakout', params: {} } } },
    { id: 'd', enabled: true, test: { kind: 'value', metric: { kind: 'flow', metric: 'FL10', params: {} }, op: 'gt', value: -1e15 } },
    { id: 'e', enabled: true, test: { kind: 'window', mode: 'ever', length: 5, test: { kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', params: {}, output: 'sma' } } } },
    { id: 'f', enabled: true, test: { kind: 'value', metric: { kind: 'rank', of: { kind: 'transform', fn: 'pct_distance', of: { kind: 'indicator', indicator: 'I02', params: {}, output: 'ema' }, args: {} } }, op: 'ge', value: 0 } },
    { id: 'g', enabled: true, test: { kind: 'value', metric: { kind: 'transform', fn: 'ratio', of: { kind: 'price', field: 'volume' }, args: { by: { kind: 'indicator', indicator: 'I03', params: {}, output: 'wma' } } }, op: 'gt', value: -1 } },
    { id: 'h', enabled: false, test: { kind: 'value', metric: { kind: 'xsection', metric: 'return_rank', params: {} }, op: 'ge', value: 0 } },
    { id: 'i', enabled: false, test: { kind: 'value', metric: { kind: 'flow', metric: 'fnet', params: {} }, op: 'gt', value: -1e15 } },
  ],
  logic: 'any',
};
const EXPECTED: [string, string, string][] = [       // [kind, id, field] in the walk's order
  ['indicator', 'I07', 'definition.universe.metric_filters[1].metric.indicator'],
  ['indicator', 'I13', 'definition.conditions[0].test.metric.indicator'],
  ['candle_pattern', 'hammer', 'definition.conditions[1].test.signal.pattern.type'],
  ['screener_metric', 'breakout', 'definition.conditions[2].test.pattern.type'],
  ['flow_indicator', 'FL10', 'definition.conditions[3].test.metric.metric'],
  ['indicator', 'I01', 'definition.conditions[4].test.test.rhs.indicator'],
  ['indicator', 'I02', 'definition.conditions[5].test.metric.of.of.indicator'],
  ['indicator', 'I03', 'definition.conditions[6].test.metric.args.by.indicator'],
  ['screener_metric', 'return_rank', 'definition.conditions[7].test.metric.metric'],
  ['flow_indicator', 'fnet', 'definition.conditions[8].test.metric.metric'],
];
// the capability edge-bff checks (app/allow.py FAMILIES): the Terminal's for the indicator and Flow kinds (3b follow-up)
const FAMILY: Record<string, string> = { indicator: 'terminal.indicator', flow_indicator: 'terminal.flow_indicator', candle_pattern: 'screener.candle_pattern', screener_metric: 'screener.metric' };
const idsOf = (kind: string) => EXPECTED.filter(e => e[0] === kind).map(e => e[1]);
const exact = () => Object.fromEntries(Object.keys(FAMILY).map(k => [k, idsOf(k)]));

test('the walk names every item of a definition with its kind and JSON path; the transform metrics (hi52, lo52, rs, vol_ratio) and price fields have no id', () => {
  assert.deepEqual(definitionItems(FULL).map(i => [i.kind, i.id, i.field]), EXPECTED);
  // a counts entry's path
  assert.equal(definitionItems(FULL, 'definitions[3].definition')[1].field, 'definitions[3].definition.conditions[0].test.metric.indicator');
});

/* 3f round 2 (TRC2-5, CS-5): which Screener metrics the walk names by id is read from the catalog's own fields, both
   ways, for every entry: a metric with a reference template (`ref`: the core refuses its id, metricSpec `!x.ref`, so it
   reaches the wire as the template, hi52 as pct_distance(rolling_max(high, 252))) and a universe attribute that names its
   `row` (shown in every answer) are never named; every other entry is. edge-bff's tests/test_releases.py reads the same
   two fields to refuse the lab stage for an item no worker gates by id. */
const METRICS = (JSON.parse(readFileSync(new URL('../../edge-bff/screener/src/core/screener-metrics.json', import.meta.url), 'utf8')) as { metrics: Record<string, unknown>[] }).metrics;
test('the walk names a Screener metric by its id exactly when its catalog entry has no ref and no row', () => {
  const key: Record<string, string> = { pattern: 'type', xsection: 'metric', universe: 'attr', flow: 'metric' };
  const asSent = (m: Record<string, unknown>) => m.ref ? m.ref : { kind: m.kind, [key[m.kind as string] ?? 'id']: m.id, params: {} };
  const kinds = new Set<string>();
  for (const m of METRICS) {
    kinds.add(m.kind as string);
    const def = { universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: asSent(m), op: 'gt', value: 0 } }], logic: 'all' };
    assert.equal(definitionItems(def).some(it => it.id === m.id), !m.ref && m.row === undefined, `${m.id} (${m.kind}, ref ${!!m.ref}, row ${m.row !== undefined})`);
  }
  assert.ok(kinds.has('transform') && kinds.has('universe'), 'the catalog has entries of both halves');
});

test('a universe attribute every answer shows is not an item (O3b-2, R1-35 "1a"); any other universe attribute is', () => {
  assert.deepEqual([...SHOWN_ATTRIBUTES.keys()].sort(), ['adv20_idr', 'bars', 'chg_1d_pct', 'index_membership', 'last']);
  const on = (attr: string) => ({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: { kind: 'universe', attr }, op: 'gt', value: 0 } }] });
  for (const attr of SHOWN_ATTRIBUTES.keys()) {
    assert.deepEqual(definitionItems(on(attr)), [], attr);
    checkAllow(on(attr), parseContext({ allow: { ...ALL, screener_metric: [] } }).allow);
  }
  assert.deepEqual(definitionItems(on('cap')).map(i => [i.kind, i.id, i.field]), [['screener_metric', 'cap', 'definition.conditions[0].test.metric.attr']]);
});

test('checkAllow: each item outside allow refused 403 CAPABILITY_REQUIRED with its field and capability; inside allowed; "*" allows all', () => {
  checkAllow(FULL, ALLOW_ALL);
  checkAllow(FULL, parseContext({ allow: exact() }).allow);
  for (const [kind, id, field] of EXPECTED) {
    const allow = parseContext({ allow: without(kind, id, idsOf(kind)) }).allow;
    assert.throws(() => checkAllow(FULL, allow), (e: any) => {
      assert.deepEqual([e.status, e.code, e.field, e.details], [403, 'CAPABILITY_REQUIRED', field, { kind, id, capability: `${FAMILY[kind]}:${id}` }]);
      assert.ok(e.message.startsWith(`${field}: the `) && e.message.includes(id) && /not included in your plan/.test(e.message) && /remove it/.test(e.message), e.message);
      assert.deepEqual(Object.keys(e.toApi().error).sort(), ['code', 'details', 'field', 'message']);
      return true;
    }, `${kind} ${id}`);
  }
});

test('the context: allow required (step 3); malformed allow, limits or context refused INVALID_CONTEXT naming the field', () => {
  assert.deepEqual(parseContext({ allow: ALL, limits: {} }).limits, {});
  assert.deepEqual(parseContext({ allow: ALL }), { rights: [], allow: parseContext({ allow: ALL }).allow, limits: {} });
  const bad = (c: unknown, field: string) => assert.throws(() => parseContext(c), (e: any) => {
    assert.deepEqual([e.code, e.status, e.field], ['INVALID_CONTEXT', 422, field]); assert.ok(e.message.length > 20); return true;
  }, JSON.stringify(c));
  for (const c of [undefined, {}, { rights: [] }, { rights: [], limits: {} }]) {
    bad(c, 'context.allow');
    assert.throws(() => parseContext(c), (e: any) => /right: \{"indicator": "\*"/.test(e.message) && /wrong: no allow/.test(e.message), JSON.stringify(c));
  }
  bad([], 'context');
  bad({ who: 1 }, 'context.who');
  bad({ rights: ['root'] }, 'context.rights');
  bad({ allow: '*' }, 'context.allow');
  bad({ allow: { ...ALL, preset: '*' } }, 'context.allow.preset');
  bad({ allow: { indicator: '*', flow_indicator: '*', candle_pattern: '*' } }, 'context.allow.screener_metric');
  bad({ allow: { ...ALL, indicator: 'I01' } }, 'context.allow.indicator');
  bad({ allow: { ...ALL, indicator: ['I01', 'I01'] } }, 'context.allow.indicator');
  bad({ allow: { ...ALL, indicator: [1] } }, 'context.allow.indicator');
  bad({ allow: ALL, limits: [] }, 'context.limits');
  bad({ allow: ALL, limits: { max_rows: 5 } }, 'context.limits.max_rows');
  bad({ allow: ALL, limits: { max_conditions: 0 } }, 'context.limits.max_conditions');
  bad({ allow: ALL, limits: { max_counts: 1.5 } }, 'context.limits.max_counts');
  assert.deepEqual(parseContext({ allow: ALL, limits: { max_metric_filters: 0 } }).limits, { max_metric_filters: 0 });
});

test('limits: min(the worker\'s own ceiling, the plan\'s), never above the worker\'s', () => {
  const own = { max_cpu_ms: 4500, owner_cpu_ms: 20000, owner_inflight: 2, max_conditions: 12, max_metric_filters: 8, max_counts: 50, queue: 9 };
  assert.deepEqual(effectiveLimits(own, {}), own);
  assert.deepEqual(effectiveLimits(own, { max_conditions: 3, max_counts: 500, owner_inflight: 1 }), { ...own, max_conditions: 3, owner_inflight: 1 });
});

/* ---- over HTTP, on the real core ------------------------------------------------------------------------------ */
let app: WorkerApp, fake: { close(): Promise<void> }, port: number;
before(async () => {
  const u = universe(6, 300), all = u.prices.IHSG.map((r: unknown[]) => r[0] as string), days = all.slice(-62, -2), tickers = Object.keys(u.prices).filter(t => t !== 'IHSG');
  const broker = Object.fromEntries(days.map((d: string, k: number) => [d, fakeRows(k + 1, d, tickers)]));
  fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...u, actions: [], broker, brokers: [['AK', 'A', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy']] } });
  app = createApp(configFor(fake.url, { SCREENER_THREADS: '1' }), { pollMs: 3_600_000 });
  port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick(); await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
});
after(async () => { await app?.close(); await fake?.close() });

const ticker = () => app.state().current!.desc.rows[0].ticker;
const dataVersion = () => app.state().current!.price_data;
const SMALL = { universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: RSI, op: 'lt', value: 101 } }], logic: 'all' };
const LOCKED = { ...ALL, indicator: [] as string[] };
const refused = (r: { status: number; body: any }, field: string, capability: string) => {
  assert.equal(r.status, 403, JSON.stringify(r.body));
  assert.deepEqual([r.body.error.code, r.body.error.field, r.body.error.details.capability], ['CAPABILITY_REQUIRED', field, capability]);
};

test('/v1/validate: every place of the full definition refused without its item (the exact field and capability), accepted with it and with "*"', async () => {
  const v = (context: unknown) => call(port, 'POST', '/v1/validate', { schema_version: 1, definition: FULL, context }, auth(OWNER_A));
  const ok = await v({ allow: ALL, limits: {} });
  assert.equal(ok.status, 200, JSON.stringify(ok.body));
  assert.equal((await v({ allow: exact(), limits: {} })).status, 200);
  for (const [kind, id, field] of EXPECTED) refused(await v({ allow: without(kind, id, idsOf(kind)), limits: {} }), field, `${FAMILY[kind]}:${id}`);
  // a saved My metric is validated by edge-bff as the one condition of a screen (app/screener.py validated_definition):
  // one on a universe attribute every answer shows needs no grant (R1-35 "1a"; it was refused without
  // screener.metric:adv20_idr before), one on any other Screener metric does
  const myMetric = (metric: unknown, op = 'gt') => ({ universe: { security_types: ['stock'] }, conditions: [{ id: 'm', enabled: true, test: { kind: 'value', metric, op, value: 0 } }], logic: 'all' });
  const shown = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: myMetric({ kind: 'universe', attr: 'adv20_idr' }), context: { allow: { ...ALL, screener_metric: [] } } }, auth(OWNER_A));
  assert.equal(shown.status, 200, JSON.stringify(shown.body));
  refused(await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: myMetric({ kind: 'xsection', metric: 'return_rank', params: {} }, 'ge'), context: { allow: { ...ALL, screener_metric: ['last'] } } }, auth(OWNER_A)), 'definition.conditions[0].test.metric.metric', 'screener.metric:return_rank');
  // a malformed context is INVALID_CONTEXT before anything else
  const m = await v({ allow: { indicator: '*' } });
  assert.deepEqual([m.status, m.body.error.code, m.body.error.field], [422, 'INVALID_CONTEXT', 'context.allow.flow_indicator']);
});

test('/v1/run: a result cached for a principal with the item is still refused for one without it; the extra-column request (one VALUE test per column) is gated too, its anchor (bars) needs no grant', async () => {
  const body = (seq: number, context?: unknown) => ({ schema_version: 1, client_order: { page: 'p', seq }, definition: SMALL, ...(context ? { context } : {}) });
  const first = await call(port, 'POST', '/v1/run', body(1, { allow: ALL, limits: {} }), auth(OWNER_A));
  assert.equal(first.status, 200, JSON.stringify(first.body));
  const hits = app.results.hits;
  refused(await call(port, 'POST', '/v1/run', body(2, { allow: LOCKED, limits: {} }), auth(OWNER_A)), 'definition.conditions[0].test.metric.indicator', 'terminal.indicator:I13');
  assert.equal(app.results.hits, hits, 'refused before the result cache is read');
  const again = await call(port, 'POST', '/v1/run', body(3, { allow: { ...LOCKED, indicator: ['I13'] } }), auth(OWNER_A));   // another principal with I13
  assert.equal(again.status, 200);
  assert.equal(app.results.hits, hits + 1, 'the cached answer serves a principal with the item');
  // extra columns (static/extra-columns.ts): the anchor `bars gt 0` and the columns as VALUE tests
  const extra = { universe: { ...U, tickers: [ticker()] }, logic: 'any', conditions: [
    { id: 'x0', enabled: true, test: { kind: 'value', metric: { kind: 'universe', attr: 'bars' }, op: 'gt', value: 0 } },
    { id: 'x1', enabled: true, test: { kind: 'value', metric: { kind: 'transform', fn: 'pct_distance', of: { kind: 'indicator', indicator: 'I05', params: {}, output: 'kama' }, args: {} }, op: 'gt', value: -1e9 } }] };
  const run = (context: unknown) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'aux', seq: 1 }, definition: extra, context }, auth(OWNER_A));
  refused(await run({ allow: { ...ALL, indicator: ['I13'] } }), 'definition.conditions[1].test.metric.of.indicator', 'terminal.indicator:I05');
  // re-check R1-35 (user 2026-11-19, "1a"): the anchor reads bars, which /universe shows for every stock, so it no longer
  // needs screener.metric:bars (until then refused naming a metric the person never chose)
  const anchored = await run({ allow: { ...ALL, indicator: ['I05'], screener_metric: [] } });
  assert.equal(anchored.status, 200, JSON.stringify(anchored.body));
  assert.equal((await run({ allow: { ...ALL, indicator: ['I05'], screener_metric: ['bars'] } })).status, 200);
});

test('/v1/preview: refused before its cache read, cached or not', async () => {
  const body = (context: unknown) => ({ schema_version: 1, client_order: { page: 'pv', seq: 1 }, definition: SMALL, ticker: ticker(), data_version: dataVersion(), context });
  assert.equal((await call(port, 'POST', '/v1/preview', body({ allow: ALL }), auth(OWNER_A))).status, 200);
  const hits = app.results.hits;
  refused(await call(port, 'POST', '/v1/preview', body({ allow: LOCKED }), auth(OWNER_A)), 'definition.conditions[0].test.metric.indicator', 'terminal.indicator:I13');
  assert.equal(app.results.hits, hits);
});

test('/v1/counts: a locked entry answers its own CAPABILITY_REQUIRED, the others their counts; a cached count is still refused', async () => {
  const candle = { universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'event', signal: { pattern: { kind: 'pattern', type: 'hammer', params: {} } }, within: 3 } }], logic: 'all' };
  const counts = (context: unknown) => call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'rsi', definition: SMALL }, { item_id: 'candle', definition: candle }], context }, auth(OWNER_A));
  const open = await counts({ allow: ALL });
  assert.equal(open.status, 200, JSON.stringify(open.body));
  assert.ok(open.body.counts.every((c: any) => 'match_count' in c), JSON.stringify(open.body.counts));
  const r = await counts({ allow: { ...ALL, candle_pattern: ['doji_star_not_held'] }, limits: {} });
  assert.equal(r.status, 200);
  assert.ok('match_count' in r.body.counts[0]);
  assert.deepEqual(r.body.counts[1].item_id, 'candle');
  assert.deepEqual([r.body.counts[1].error.code, r.body.counts[1].error.field, r.body.counts[1].error.details],
    ['CAPABILITY_REQUIRED', 'definitions[1].definition.conditions[0].test.signal.pattern.type', { kind: 'candle_pattern', id: 'hammer', capability: 'screener.candle_pattern:hammer' }]);
});

test('limits over HTTP: max_conditions, max_counts and max_cpu_ms take the lower of the worker\'s and the plan\'s', async () => {
  const L = app.state().current!.vctx.limits;
  const two = { ...SMALL, conditions: [SMALL.conditions[0], { ...SMALL.conditions[0], id: 'b' }] };
  const v = (limits: unknown) => call(port, 'POST', '/v1/validate', { schema_version: 1, definition: two, context: { allow: ALL, limits } }, auth(OWNER_A));
  assert.equal((await v({})).status, 200);
  assert.equal((await v({ max_conditions: L.max_conditions + 10 })).status, 200, 'a plan value above the worker\'s ceiling changes nothing');
  const c = await v({ max_conditions: 1 });
  assert.deepEqual([c.status, c.body.error.code], [422, 'LIMIT_EXCEEDED'], JSON.stringify(c.body));
  const n = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'a', definition: SMALL }, { item_id: 'b', definition: SMALL }], context: { allow: ALL, limits: { max_counts: 1 } } }, auth(OWNER_A));
  assert.deepEqual([n.status, n.body.error.code, n.body.error.details.limit, n.body.error.details.allowed], [422, 'LIMIT_EXCEEDED', 'max_counts', 1]);
  // an anchored flow condition (cost.test.ts): costed above 1 ms on this fixture, within the worker's own budget
  const anchored = { kind: 'transform', fn: 'percentile', of: { kind: 'flow', metric: 'FL18', params: { anchor_sessions: 40 } }, args: { length: 10 } };
  const custom = { ...SMALL, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: anchored, op: 'ge', value: 50 } }] };
  const lim = (limits: unknown) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'lim', seq: 1 }, definition: custom, context: { rights: ['flow_point_in_time'], allow: ALL, limits } }, auth(OWNER_A));
  const b = await lim({ max_cpu_ms: 1 });
  assert.deepEqual([b.status, b.body.error.code, b.body.error.details.limit, b.body.error.details.allowed], [422, 'LIMIT_EXCEEDED', 'compute_budget', 1], JSON.stringify(b.body));
  assert.equal((await lim({ max_cpu_ms: 10_000_000 })).status, 200, 'the worker\'s own budget when the plan\'s is higher');
});

test('step 3: every route refuses a body without context.allow INVALID_CONTEXT naming context.allow, with a right example', async () => {
  // CONTRACT 8b "3b follow-up": edge-bff sends allow on every call; a body without it is not computed, cached or counted.
  // The bodies go as strings, exactly as written (helpers.ts call adds edge-bff's context to an object body)
  const bodies: [string, Record<string, unknown>][] = [
    ['/v1/validate', { schema_version: 1, definition: SMALL }],
    ['/v1/run', { schema_version: 1, client_order: { page: 's3', seq: 1 }, definition: SMALL }],
    ['/v1/preview', { schema_version: 1, client_order: { page: 's3', seq: 2 }, definition: SMALL, ticker: ticker(), data_version: dataVersion() }],
    ['/v1/counts', { schema_version: 1, definitions: [{ item_id: 'a', definition: SMALL }] }],
  ];
  const hits = app.results.hits;
  for (const [path, body] of bodies) for (const context of [undefined, { rights: [] }, { rights: [], limits: {} }]) {
    const r = await call(port, 'POST', path, JSON.stringify(context === undefined ? body : { ...body, context }), auth(OWNER_A));
    assert.deepEqual([r.status, r.body.error.code, r.body.error.field], [422, 'INVALID_CONTEXT', 'context.allow'], `${path} ${JSON.stringify(context)}: ${JSON.stringify(r.body)}`);
    assert.ok(/right: \{"indicator": "\*"/.test(r.body.error.message) && /wrong: no allow/.test(r.body.error.message), r.body.error.message);
    // with allow the same body passes
    if (context) assert.equal((await call(port, 'POST', path, JSON.stringify({ ...body, context: { ...context, allow: ALL } }), auth(OWNER_A))).status, 200, path);
  }
  assert.ok(app.results.hits >= hits);
});

test('internal calls are never gated: the presets of the refresh were computed in the system lane with everything allowed', () => {
  const presets = app.state().current!.presets;
  assert.ok(presets.length > 0);
  assert.ok(presets.some(p => p.match_count !== null), 'at least one preset counted');
});

/* EXEC-MU-ACCOUNTS Phase 3b, C2 F1: each preset in the catalog carries `items`, the distinct items its definition reads
   by the allow check's own walk; edge-bff leaves a preset out for a plan that does not hold all of them. The two must
   agree on every real preset: an allow without any one of the items refuses the preset when it is run. */
test('every preset lists the items the allow check reads, and an allow without one of them refuses it', async () => {
  const { presetItems } = await import('../src/run.ts');
  const { PRESETS } = await import('../../edge-bff/screener/src/core/catalog.ts');
  assert.ok(PRESETS.presets.length > 0);
  for (const p of PRESETS.presets) {
    const items = presetItems(p.definition);
    const walked = definitionItems(p.definition).map(({ kind, id }) => `${kind}:${id}`);
    assert.deepEqual(items.map(i => `${i.kind}:${i.id}`), [...new Set(walked)].sort(), p.id);
    for (const missing of items) {
      const allow = { ...ALLOW_ALL, [missing.kind]: new Set<string>() } as typeof ALLOW_ALL;
      assert.throws(() => checkAllow(p.definition, allow), (e: any) => e?.error?.code === 'CAPABILITY_REQUIRED' || e?.code === 'CAPABILITY_REQUIRED', `${p.id} without ${missing.kind}:${missing.id}`);
    }
  }
});

/* 3f checker L2, CAT-3 (FUTURE_PLAN.md "Before the first lab item or tab"; the user's go 2026-11-22): the allow walk runs
   on the definition as sent, before the normalizer, so an item outside allow (an id the registry has, or one it lacks) is
   refused by its id alone: never UNKNOWN_INDICATOR's list of every registry id, never a parameter or output of an item
   the principal does not hold, never a registry name. The whole answer is searched, not only its code. */
test('/v1/validate, /v1/run, /v1/preview, /v1/counts: an item outside allow is refused before the normalizer names anything', async () => {
  const registryIds = ['I01', 'I02', 'I07', 'I35', 'FL01', 'FL24'];
  const plantedUnknown = { kind: 'indicator', indicator: 'I_LAB_PLANTED', params: {}, output: 'x' };
  const heldNot = { ...RSI, params: { length: -5, not_a_parameter: 1 } };       // held by no one here: a bad parameter
  const def = (metric: unknown) => ({ universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric, op: 'lt', value: 50 } }], logic: 'all' });
  const context = { allow: { ...ALL, indicator: ['I01'] }, limits: {} };
  const bodies: [string, (d: unknown) => unknown][] = [
    ['/v1/validate', d => ({ schema_version: 1, definition: d, context })],
    ['/v1/run', d => ({ schema_version: 1, client_order: { page: 'p', seq: 1 }, data_version: dataVersion(), definition: d, context })],
    ['/v1/preview', d => ({ schema_version: 1, client_order: { page: 'p', seq: 2 }, data_version: dataVersion(), definition: d, ticker: ticker(), context })],
  ];
  for (const [path, body] of bodies) {
    for (const [metric, id] of [[plantedUnknown, 'I_LAB_PLANTED'], [heldNot, 'I13']] as const) {
      const r = await call(port, 'POST', path, body(def(metric)), auth(OWNER_A));
      assert.equal(r.status, 403, `${path} ${id}: ${JSON.stringify(r.body)}`);
      assert.equal(r.body.error.code, 'CAPABILITY_REQUIRED');
      assert.equal(r.body.error.details.id, id);
      const text = JSON.stringify(r.body);
      assert.ok(!('allowed' in (r.body.error.details ?? {})), `${path}: a list in details: ${text}`);
      for (const other of registryIds) assert.ok(!text.includes(`"${other}"`) && !text.includes(` ${other} `) && !text.includes(` ${other})`), `${path} names ${other}: ${text}`);
      assert.ok(!/RSI|Relative Strength|length|not_a_parameter/.test(text), `${path} names the item's name, outputs or parameters: ${text}`);
    }
  }
  const counts = await call(port, 'POST', '/v1/counts', { schema_version: 1, data_version: dataVersion(), definitions: [{ item_id: 'x', definition: def(plantedUnknown) }], context }, auth(OWNER_A));
  assert.equal(counts.status, 200, JSON.stringify(counts.body));
  const entry = counts.body.counts?.[0] ?? counts.body.entries?.[0] ?? counts.body.items?.[0];
  assert.equal(entry?.error?.code, 'CAPABILITY_REQUIRED', JSON.stringify(counts.body));
  assert.ok(!JSON.stringify(counts.body).includes('"I01"'), JSON.stringify(counts.body));
  // a principal holding every item still meets the normalizer's own answers (the list is the admin's to see)
  const admin = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: def(plantedUnknown), context: { allow: ALL, limits: {} } }, auth(OWNER_A));
  assert.equal(admin.status, 422, JSON.stringify(admin.body));
});
