/* EXEC-SCREENER-FLOW-CANDLES P5a (verification/screener/P5_FLOW.md), end to end against the fake terminal-api with
   60 broker day files in the publisher's format and the reference file `brokers` (its classification): the catalog
   shows the Terminal's 48 flow indicators and the Screener's own flow entries (P5b: fnet; FL31 and ksei_net
   REQUIRES_DATA), a run reads each stock at its last candle with broker data (eval_date, source flow) with the value
   flow.ts computeFlow gives the Terminal's way on the same rows (FL34 on the reference file's classification, read at
   the last broker date only), the eight bandar presets run on a loaded window, a condition beyond the loaded window is
   refused LIMIT_EXCEEDED broker_depth, and while the window is still loading a flow condition is refused with
   FLOW_UNAVAILABLE in its details and the catalog's words. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { computeFlow, flowDefaults, flowRows } from '../../edge-bff/terminal/src/calc/flow.ts';
import { round12 } from '../../edge-bff/screener/src/core/evaluate.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { BROKER_DAY_SESSIONS } from '../src/broker.ts';
import { FLOW_DESIGN_SESSIONS } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import { brokerRowsOf as fakeRows, startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';

captureLogs();
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });

const STOCKS = ['T000', 'T001', 'T002', 'T003', 'T004', 'T005'];
const CLASSES: [string, string, string, string][] = [['AK', 'A', 'Local', 'Institutional-heavy'], ['BK', 'B', 'Foreign', 'Retail-heavy'], ['CC', 'C', 'Local', 'Mixed'],
  ['DX', 'D', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy'], ['ZP', 'Z', 'Foreign', 'Mixed']];
const u = universe(6, 300), all = u.prices.IHSG.map((r: unknown[]) => r[0] as string);
/** the 60 broker days: the sessions before the last two (the price runs two sessions ahead of the broker data) */
const DAYS = all.slice(-62, -2), FIRST = DAYS[0], LAST = DAYS[59];
const broker = Object.fromEntries(DAYS.map((d: string, k: number) => [d, fakeRows(k + 1, d, STOCKS)]));
const pubOf = (finished_at: string, extra: Record<string, unknown> = {}) => ({ finished_at, ...u, actions: [], broker, brokers: CLASSES, ...extra });
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const def = (test: unknown) => ({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] });
let seq = 0;
const run = (port: number, test: unknown) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: ++seq }, definition: def(test), options: { exhaustive: true } }, auth(OWNER_A));

async function start(publication: any, env: Record<string, string> = {}) {
  const fake = await startFakeTerminal({ key: PROXY, publication });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1', ...env }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  await app.refresher.tick();
  await app.refresher.tick();                    // a follow-up refresh of the broker days, when one is due
  assert.ok(app.state().current, 'snapshot loaded');
  return { app, fake, port };
}
/** flow.ts computeFlow the Terminal's way on the rows the fake published for a stock: flowRows of the rows as objects in
    the file's order, the stock's price dates inside the window as candles, its close and volume. */
function terminal(t: string, id: string, params: Record<string, unknown>, classification: Record<string, string> = {}) {
  const prices = (u.prices[t] as unknown[][]).filter(r => (r[0] as string) >= FIRST && (r[0] as string) <= LAST);
  const candles = prices.map(r => r[0] as string), at = new Map(candles.map((d, k) => [d, k]));
  const cp = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;
  const rows = DAYS.flatMap((d: string) => (broker[d] as unknown[][]).filter(r => r[0] === t).sort((x, y) => cp(x[1] as string, y[1] as string) || cp(x[2] as string, y[2] as string) || cp(x[3] as string, y[3] as string))
    .map(r => ({ d, b: r[1] as string, i: r[2] as string, m: r[3] as string, bv: r[4] as number, sv: r[5] as number, bl: r[6] as number, sl: r[7] as number, bf: r[8] as number | null, sf: r[9] as number | null })));
  const ctx = { rows: flowRows(rows, candles.length, d => at.get(d) ?? -1), dates: candles, close: prices.map(r => r[4] as number), volume: prices.map(r => r[5] as number), insider: [], classification };
  return { out: computeFlow(id, ctx, params), candles, has: ctx.rows.has };
}

test('the window of K1 is the publisher\'s: 60 sessions, the core\'s design window for a baseline left out without a loaded one', () => {
  assert.equal(BROKER_DAY_SESSIONS, 60);
  assert.equal(FLOW_DESIGN_SESSIONS, BROKER_DAY_SESSIONS);
});

test('the catalog: the 48 flow indicators with their Terminal setup and the Screener\'s own flow entries, available on a complete window (FL31 and ksei_net need data not published); the Screener\'s versions marked; no other flow entry', async () => {
  const { port, app } = await start(pubOf('2026-10-27T13:03:23Z'));
  assert.deepEqual(app.state().current!.desc.data.broker_window, { first: FIRST, last: LAST, sessions: 60, complete: true });
  assert.equal(Object.keys(app.state().current!.desc.brokerClasses).length, CLASSES.length, 'the classification of the reference file brokers');
  const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body;
  const flows = (cat.metrics as any[]).filter(m => m.kind === 'flow' && m.flow);
  assert.equal(flows.length, 50);
  assert.equal((cat.metrics as any[]).filter(m => m.kind === 'flow').length, 50, 'every flow entry is a generated one');
  assert.deepEqual(flows.filter(m => m.availability !== 'AVAILABLE').map(m => m.id), ['FL31', 'ksei_net']);
  assert.deepEqual(flows.filter(m => m.flow.version === 'screener').map(m => m.id), ['FL18', 'FL19', 'FL20', 'FL23', 'FL44', 'FL45', 'fnet', 'ksei_net']);
  const fl23 = flows.find(m => m.id === 'FL23'), fl18 = flows.find(m => m.id === 'FL18');
  assert.deepEqual([fl23.flow.outputs.map((o: any) => o.key), fl23.flow.depth, fl18.flow.depth, fl18.flow.params.find((p: any) => p.key === 'anchor_sessions')],
    [['value', 'count'], 20, 21, { key: 'anchor_sessions', label: 'Anchor: sessions before the evaluated candle', kind: 'int', default: 20, min: 1, max: 59, text: fl18.flow.params.find((p: any) => p.key === 'anchor_sessions').text, condition: true, screener: true }]);
  const fl24 = flows.find(m => m.id === 'FL24'), fl37 = flows.find(m => m.id === 'FL37');
  assert.deepEqual([fl24.label, fl24.unit, fl24.params, fl24.flow.default_output, fl24.flow.depth, fl24.flow.sessions, fl24.flow.outputs], ['Top Brokers · %', '%', [], 'value', 10, 60, [{ key: 'value', kind: 'K' }]]);
  assert.deepEqual([fl37.flow.params.find((p: any) => p.key === 'baseline').default, fl37.flow.depth], [40, 60], 'the built-in baseline capped to the window less its own (K1)');
  // the limit is published with its rule and examples before a user meets it (the gate rule)
  const limit = (cat.limits as any[]).find(l => l.name === 'broker_depth');
  assert.deepEqual([limit.value, limit.unit, limit.example_ok], [60, 'sessions', 'Top Brokers · % over 10 sessions with a percentile over 50 sessions (60 in all)']);
  // the eight bandar presets read the flow entries: available on the loaded window, with their counts computed
  for (const id of ['bigacc', 'fstreak', 'silent', 'freq', 'bavg', 'follow']) {
    const p = (cat.presets as any[]).find(x => x.id === id);
    assert.deepEqual([id, p.availability, typeof p.match_count], [id, 'AVAILABLE', 'number']);
  }
  for (const id of ['qflow', 'vacc']) assert.deepEqual([id, (cat.presets as any[]).find(x => x.id === id).unavailable_legs.every((l: string) => l === 'a' || l === 'b')], [id, true]);
});

test('a run reads each stock at its last candle with broker data, with the Terminal\'s value: FL24 at its defaults and FL34 on the reference file\'s classification', async () => {
  const { port } = await start(pubOf('2026-10-27T14:00:00Z'));
  const classification = Object.fromEntries(CLASSES.map(r => [r[0], r[3]]));
  for (const [id, cls] of [['FL24', {}], ['FL34', classification]] as const) {
    const r = await run(port, { kind: 'value', metric: { kind: 'flow', metric: id }, op: 'gt', value: -1e9 });
    assert.equal(r.status, 200, JSON.stringify(r.body));
    assert.deepEqual([r.body.conditions[0].source, r.body.conditions[0].eval_date_basis], ['flow', 'flow_date']);
    let checked = 0;
    for (const t of STOCKS) {
      const T = terminal(t, id, flowDefaults(id), cls), k = T.candles.length - 1 - [...T.has].reverse().indexOf(1), want = T.out.value[k];
      const cell = r.body.rows.find((x: any) => x.ticker === t)?.cells[0];
      if (want === null) { assert.ok(!cell || cell.status !== 'pass', `${id} ${t}`); continue }
      assert.deepEqual([id, t, cell.status, cell.eval_date, cell.value], [id, t, 'pass', T.candles[k], round12(want)]);
      checked++;
    }
    assert.ok(checked >= 3, `${id}: ${checked} stocks compared`);
    assert.ok(r.body.rows.every((x: any) => x.cells[0].eval_date === LAST || x.cells[0].eval_date < LAST), 'never after the last broker day');
    assert.ok(r.body.rows.some((x: any) => x.cells[0].eval_date === LAST && x.last_bar_date > LAST), 'the price runs ahead');
  }
});

test('beyond the loaded window a flow condition is refused LIMIT_EXCEEDED broker_depth, naming both numbers and the window', async () => {
  const { port } = await start(pubOf('2026-10-27T15:00:00Z'));
  const pct = (length: number) => ({ kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: { kind: 'flow', metric: 'FL24' }, args: { length } }, op: 'ge', value: 90 });
  assert.equal((await run(port, pct(40))).status, 200);
  const r = await run(port, pct(55));
  assert.equal(r.status, 422);
  assert.deepEqual([r.body.error.code, r.body.error.field, r.body.error.details], ['LIMIT_EXCEEDED', 'definition.conditions[0].test', { limit: 'broker_depth', allowed: 60, needed: 65 }]);
});

test('while the window is still loading, a flow condition is refused with FLOW_UNAVAILABLE and the catalog\'s words; the other conditions run', async () => {
  // the oldest day is indexed larger than one refresh may download: it waits, so the window stays incomplete
  const name = `broker-${FIRST}`;
  const { port, app } = await start(pubOf('2026-10-27T16:00:00Z', { files: { [name]: { bytes: 3_000_000 } } }), { SCREENER_MAX_REFRESH_BYTES: '2000000' });
  assert.deepEqual(app.state().current!.desc.data.broker_window, { first: DAYS[1], last: LAST, sessions: 59, complete: false });
  const cat = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body, fl24 = (cat.metrics as any[]).find(m => m.id === 'FL24');
  assert.equal(fl24.availability, 'REQUIRES_DATA');
  assert.match(fl24.reason, /^The broker data is still loading \(59 sessions loaded so far\)/);
  const v = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: def({ kind: 'value', metric: { kind: 'flow', metric: 'FL24' }, op: 'gt', value: 0 }) }, auth(OWNER_A));
  assert.equal(v.status, 422);
  assert.deepEqual([v.body.error.code, v.body.error.details.availability, v.body.error.details.reason, v.body.error.details.reason_code], ['METRIC_UNAVAILABLE', 'REQUIRES_DATA', fl24.reason, 'FLOW_UNAVAILABLE']);
  const r = await run(port, { kind: 'value', metric: { kind: 'flow', metric: 'FL24' }, op: 'gt', value: 0 });
  assert.equal(r.body.error.code, 'METRIC_UNAVAILABLE');
  assert.equal((await run(port, { kind: 'value', op: 'lt', value: 101, metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' } })).status, 200);
});
