/* EXEC-BACKTEST-REVAMP P4: the eight point-in-time Flow indicators (src/pit/). On the synthetic market of the look-ahead
   gate (tests/lookahead/fixture.ts: Nego and Cash crossings, both investor types, a broker that appears late and one
   that stops, no database):
   - no look-ahead: every indicator, output and option on the data cut at day t equals the full series up to t;
   - the Terminal's value (calc/flow.ts computeFlow, loadersTable): with brokers the user names, on every candle after the
     warm-up; with the brokers chosen, on the last candle with data (the Terminal ranks once up to there);
   - the edge cases and refusals of the plan (EXEC P4 item 5), and the admins-only gate (CONDITION_RESTRICTED). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as TF from '../../edge-bff/terminal/src/calc/flow.ts';
import { Calc, conditionSeries } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { BrokerColumns } from '../../edge-bff/backtest/src/core/datafile.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { head, market } from './lookahead/fixture.ts';
import type { Row, Ticker } from './lookahead/fixture.ts';
import { installBacktestGrammar, seriesOfRef } from '../src/grammar.ts';
import { WARM_UP } from '../src/pit/compute.ts';
import { checkDRef } from '../src/pit/spec.ts';

installBacktestGrammar();
const M = market(), A = M.stocks[0], ROWS = M.rows[A.ticker];
const ANCHOR = A.dates[120], START = A.dates[90], LAST = A.dates.length - 1;

function columns(rows: readonly Row[]): BrokerColumns {
  const dates: string[] = [], brokers: string[] = [], at = new Map<string, number>(), inv = ['Foreign', 'Domestic'], brd = ['Regular', 'Nego', 'Tunai'];
  const D: number[] = [], B: number[] = [], I: number[] = [], Mm: number[] = [], V: number[][] = [[], [], [], [], [], []];
  for (const r of rows) {
    if (dates[dates.length - 1] !== r.d) dates.push(r.d);
    if (!at.has(r.b)) { at.set(r.b, brokers.length); brokers.push(r.b) }
    D.push(dates.length - 1); B.push(at.get(r.b)!); I.push(inv.indexOf(r.i)); Mm.push(brd.indexOf(r.m === 'Cash' ? 'Tunai' : r.m));
    [r.bv, r.sv, r.bl, r.sl, r.bf, r.sf].forEach((x, k) => V[k].push(x));
  }
  const f = (a: number[]) => Float64Array.from(a);
  return { rows: D.length, dates, brokers, investor_types: inv, boards: brd, D: Int32Array.from(D), B: Int32Array.from(B), I: Uint8Array.from(I), M: Uint8Array.from(Mm),
    BV: f(V[0]), SV: f(V[1]), BL: f(V[2]), SL: f(V[3]), BF: f(V[4]), SF: f(V[5]) };
}
const calcAt = (t: Ticker, rows: readonly Row[], n: number, actions: string[] = []) => {
  const h = head(t, n), last = h.dates[h.dates.length - 1];
  return new Calc(h.bars as never, undefined, { ticker: t.ticker, dates: h.dates, broker: { columns: columns(rows.filter(r => r.d <= last)), classification: {}, actions } });
};
const terminalCtx = (t: Ticker, rows: readonly Row[]): TF.FlowContext => {
  const at = new Map(t.dates.map((d, k) => [d, k]));
  return { rows: TF.flowRows(rows as never, t.dates.length, d => at.get(d) ?? -1), dates: t.dates, close: t.bars.C as number[], volume: t.bars.V as number[], insider: [], classification: {} };
};
const near = (a: number | null | undefined, b: number | null | undefined) => (a ?? null) === (b ?? null) || (typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(b)));
const ref = (metric: string, params: Record<string, unknown>, output?: string) => ({ kind: 'flow', metric, ...(output ? { output } : {}), params });

/** Every indicator with its options, one at a time (the plan's "setiap D dan opsi"). */
const VARIANTS: [string, Record<string, unknown>, string[]][] = [
  ...['FL18', 'FL19', 'FL20', 'FL44', 'FL45'].flatMap(id => [{}, { top: 1 }, { top: 10 }, { boards: ['Regular', 'Nego', 'Cash'] }, { investors: ['Foreign'] },
    ...(id === 'FL19' || id === 'FL20' ? [] : [{ rank: 'gross_buy' }, { rank: 'net_sell' }]), { scope: 'selected', brokers: ['AA', 'BK'] }]
    .map(v => [id, { anchor: ANCHOR, ...v }, ['value', 'cohort_changed']] as [string, Record<string, unknown>, string[]])),
  ...[{}, { unit: 'value' }, { view: 'daily' }, { brokers: ['AA', 'LATE', 'GONE'] }, { boards: ['Regular', 'Nego', 'Cash'] }]
    .map(v => ['FL23', { start: START, ...v }, ['total', 'cohort_changed']] as [string, Record<string, unknown>, string[]]),
  ...[{}, { cost: 'model' }, { top: 5 }, { loader: 1 }, { loader: 3 }, { investors: ['Domestic'] }]
    .map(v => ['FL51', { start: START, ...v }, ['cost', 'distance', 'share', 'cohort_changed']] as [string, Record<string, unknown>, string[]]),
];

test('no look-ahead: every point-in-time indicator, output and option on the data cut at t equals the full series up to t', () => {
  const full = calcAt(A, ROWS, A.dates.length), leaks: string[] = [];
  let checked = 0;
  for (const [id, p, outs] of VARIANTS) for (const o of outs) {
    const s = seriesOfRef(full, ref(id, p, o), 'f');
    assert.ok(Array.from(s).some(v => typeof v === 'number'), `${id}.${o} ${JSON.stringify(p)} has values`);
    for (const k of [140, 260, 351, 470]) {
      const part = seriesOfRef(calcAt(A, ROWS, k), ref(id, p, o), 'f');
      for (let i = 0; i < k; i++) if (!near(part[i], s[i])) { leaks.push(`${id}.${o} ${JSON.stringify(p)} bar ${i} cut ${k}`); break }
      checked++;
    }
  }
  assert.ok(checked > 300, `${checked} cuts`);
  assert.deepEqual(leaks, []);
});

test('the Terminal\'s value: with named brokers on every candle after the warm-up, with chosen brokers on the last candle', () => {
  const c = calcAt(A, ROWS, A.dates.length), ctx = terminalCtx(A, ROWS);
  const firstValue = (() => { let seen = 0; for (let i = 120; i < A.dates.length; i++) if (ctx.rows.has[i] && ++seen === WARM_UP) return i; return -1 })();
  for (const id of ['FL18', 'FL19', 'FL20', 'FL44', 'FL45']) {
    for (const v of [{ scope: 'selected', brokers: ['AA', 'BK'] }, { scope: 'selected', brokers: ['LATE'] }, { scope: 'selected', brokers: ['GONE', 'SQ'], boards: ['Regular', 'Nego', 'Cash'] }]) {
      const p = { anchor: ANCHOR, ...v }, mine = seriesOfRef(c, ref(id, p), 'f'), theirs = TF.computeFlow(id, ctx, { ...p, top: 3, rank: 'net_buy' }).value;
      for (let i = firstValue; i < A.dates.length; i++) assert.ok(near(mine[i], theirs[i]), `${id} ${JSON.stringify(v)} bar ${i}: ${mine[i]} vs ${theirs[i]}`);
      for (let i = 0; i < firstValue; i++) assert.equal(mine[i] ?? null, null, `${id}: empty during the warm-up (bar ${i})`);
    }
    for (const v of [{}, { top: 5 }, { rank: 'gross_buy' }, { boards: ['Regular', 'Nego'] }]) {
      if ((id === 'FL19' || id === 'FL20') && 'rank' in v) continue;
      const p = { anchor: ANCHOR, ...v }, mine = seriesOfRef(c, ref(id, p), 'f'), theirs = TF.computeFlow(id, ctx, p).value;
      assert.ok(near(mine[LAST], theirs[LAST]), `${id} ${JSON.stringify(v)} on the last candle: ${mine[LAST]} vs ${theirs[LAST]}`);
    }
  }
  // FL23: named brokers on every candle; auto_c (K2 a) on the last
  for (const v of [{ brokers: ['AA', 'BK', 'LATE'] }, { brokers: ['GONE'], unit: 'value' }, { brokers: ['AA', 'XL'], view: 'daily' }]) {
    const p = { start: START, ...v }, mine = seriesOfRef(c, ref('FL23', p), 'f'), theirs = TF.computeFlow('FL23', ctx, { ...p, total: true }).total;
    let seen = 0;
    for (let i = 90; i < A.dates.length; i++) { if (!ctx.rows.has[i]) continue; if (++seen < WARM_UP) continue; assert.ok(near(mine[i], theirs[i]), `FL23 ${JSON.stringify(v)} bar ${i}`) }
  }
  for (const v of [{}, { unit: 'value' }, { boards: ['Regular', 'Nego', 'Cash'], investors: ['Foreign'] }]) {
    const p = { start: START, ...v }, mine = seriesOfRef(c, ref('FL23', p), 'f'), theirs = TF.computeFlow('FL23', ctx, { ...p, brokers: 'auto_c', total: true }).total;
    assert.ok(near(mine[LAST], theirs[LAST]), `FL23 auto_c ${JSON.stringify(v)} on the last candle: ${mine[LAST]} vs ${theirs[LAST]}`);
  }
  // FL51: the loaders and their costs on the last candle (the Terminal's box up to its last candle)
  for (const cost of ['avg', 'model']) for (const top of [3, 5]) {
    const T = TF.loadersTable(ctx, { start: START, end: A.dates[LAST], side: 'load', top: String(top), cost, boards: ['Regular'], investors: ['Foreign', 'Domestic'] });
    for (let k = 1; k <= Math.min(top, T.rows.length); k++)
      assert.ok(near(seriesOfRef(c, ref('FL51', { start: START, top, cost, loader: k }), 'f')[LAST], T.rows[k - 1].cost), `FL51 ${cost} top ${top} loader ${k}`);
    assert.ok(near(seriesOfRef(c, ref('FL51', { start: START, top, cost }, 'share'), 'f')[LAST], T.share), `FL51 ${cost} share`);
  }
});

test('edge cases: anchor after the data, before it, no positive buyers, a broker without rows, cohort changes, the warm-up', () => {
  const c = calcAt(A, ROWS, A.dates.length);
  const cond = (r: object, op = 'gt', value = 0) => ({ id: 'd1', kind: 'test', test: { kind: 'value', metric: r, op, value } }) as never;
  assert.throws(() => conditionSeries(c, cond(ref('FL18', { anchor: '2030-01-02' })), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'FLOW_OUTPUT_EMPTY');
  assert.throws(() => conditionSeries(c, cond(ref('FL18', { anchor: '2016-01-04' })), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'ANCHOR_BEFORE_DATA' && /AAAA has broker data from 2018-01-02/.test(e.message));
  assert.throws(() => conditionSeries(c, cond(ref('FL18', { anchor: ANCHOR, scope: 'selected', brokers: ['ZZ'] })), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'UNKNOWN_BROKER' && e.field === 'f.test.metric.params.brokers[0]');
  // a broker that appears later (LATE, from session 200) is decided on the rows up to the period's end only
  const late = cond(ref('FL23', { start: START, brokers: ['AA', 'LATE'] }), 'ne', 0);
  assert.throws(() => conditionSeries(c, late, 'f', 150), (e: unknown) => e instanceof ValidationError && e.code === 'UNKNOWN_BROKER' && /up to the end of the period/.test(e.message));
  assert.ok(conditionSeries(c, late, 'f', 300).some(Boolean));
  // only sellers: no broker with a positive net buy, so no cohort and no value
  const sellers = ROWS.map(r => ({ ...r, bv: 0, bl: 0 })), s = seriesOfRef(calcAt(A, sellers, A.dates.length), ref('FL18', { anchor: ANCHOR }), 'f');
  assert.ok(Array.from(s).every(v => v === null));
  const changed = seriesOfRef(c, ref('FL18', { anchor: ANCHOR }, 'cohort_changed'), 'f');
  assert.ok(Array.from(changed).some(v => v === 1) && Array.from(changed).every(v => v === null || v === 0 || v === 1), 'cohort_changed is 0/1 and changes');
  // odd lots (fractional, as PSSI's after its bonus) compute as any other
  const odd = ROWS.map(r => ({ ...r, bl: r.bl + 0.3171 })), o = seriesOfRef(calcAt(A, odd, A.dates.length), ref('FL19', { anchor: ANCHOR }), 'f');
  assert.ok(Array.from(o).some(v => typeof v === 'number'));
  // the Nego / Cash boards are noted for the run's warning
  const n = calcAt(A, ROWS, A.dates.length);
  seriesOfRef(n, ref('FL18', { anchor: ANCHOR, boards: ['Regular', 'Nego'] }), 'f');
  assert.equal(n.flowNotes?.crossing, true);
  assert.equal(n.flowNotes?.first, ANCHOR);
  // an action after the anchor whose adjustment the prices carry (before 2026-09-12): every price value from the anchor is empty
  const k3 = calcAt(A, ROWS, A.dates.length, [A.dates[300]]), m = seriesOfRef(k3, ref('FL18', { anchor: ANCHOR }), 'f');
  assert.ok(Array.from(m).every(v => v === null) && k3.flowNotes!.masked.size > 0);
  assert.ok(Array.from(seriesOfRef(k3, ref('FL23', { start: START }), 'f')).some(v => typeof v === 'number'), 'lots are not a price: kept (warned)');
});

test('refusals name the field and the fix', () => {
  const r = (p: Record<string, unknown>, id = 'FL18', output?: string) => { try { checkDRef(ref(id, p, output) as never, 'entry.conditions[1].test.metric'); return 'ok' } catch (e) { return `${(e as ValidationError).code} ${(e as ValidationError).field}` } };
  assert.equal(r({}), 'ANCHOR_REQUIRED entry.conditions[1].test.metric.params.anchor');
  assert.equal(r({ anchor: 'view' }), 'ANCHOR_REQUIRED entry.conditions[1].test.metric.params.anchor');
  assert.equal(r({ anchor: '2024-13-45' }), 'INVALID_ANCHOR entry.conditions[1].test.metric.params.anchor');
  assert.equal(r({ anchor: '2024-1-2' }), 'INVALID_ANCHOR entry.conditions[1].test.metric.params.anchor');
  assert.equal(r({ anchor: '2024-01-02', top: 11 }), 'TOP_N_LIMIT entry.conditions[1].test.metric.params.top');
  assert.equal(r({ anchor: '2024-01-02', rank: 'gross_buy' }, 'FL19'), 'RANK_NOT_ALLOWED entry.conditions[1].test.metric.params.rank');
  assert.equal(r({ anchor: '2024-01-02', ranking: 'frozen' }), 'INVALID_CONDITION entry.conditions[1].test.metric.params.ranking');
  assert.equal(r({ anchor: '2024-01-02' }, 'FL18', 'lines'), 'INVALID_CONDITION entry.conditions[1].test.metric.output');
  assert.equal(r({ start: '2024-01-02', end: '2024-06-03' }, 'FL51'), 'CONDITION_UNAVAILABLE entry.conditions[1].test.metric.params.end');
  assert.equal(r({ start: '2024-01-02' }, 'FL52'), 'CONDITION_UNAVAILABLE entry.conditions[1].test.metric');
  assert.equal(r({ start: '2024-01-02' }, 'FL23'), 'ok');
  // completed: the same condition with and without its defaults is one form (one trial)
  assert.deepEqual(checkDRef(ref('FL18', { anchor: '2024-01-02' }) as never, 'f'), checkDRef(ref('FL18', { anchor: '2024-01-02', top: 3, rank: 'net_buy', boards: ['Regular'] }) as never, 'f'));
});
