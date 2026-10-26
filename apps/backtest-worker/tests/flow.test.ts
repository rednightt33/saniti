/* flow.ts and the flow conditions of conditions.ts: hand-computed sums; the daily and rolling values against the
   Terminal's own code (edge-bff/terminal/src/data/worker.ts brokerData, and copies of the Terminal's netBuyFlow /
   brokerLines and recomputeFlow, which live inside its page modules); top5 and fnet against copies of the backtest
   page's formulas (backtest.html CATALOG top5 / fnet, rollsum, cmpSeries). Values compare with Object.is: the same
   additions in the same order give the same bits. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Calc, conditionSeries, flowCondition, flowConditionShape } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { FlowCondition } from '../../edge-bff/backtest/src/core/conditions.ts';
import { legacyCard, legacyToCondition } from '../../edge-bff/backtest/src/core/catalog.ts';
import type { BrokerRow, Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { brokerRows } from '../../edge-bff/backtest/src/core/datafile.ts';
import { brokerNet, flowData, rollingSum, top5Accumulation } from '../../edge-bff/backtest/src/core/flow.ts';
import type { FlowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { brokerData } from '../../edge-bff/terminal/src/data/worker.ts';
import { brokerDoc } from './fake-terminal.mjs';

const same = (a: ArrayLike<number>, b: ArrayLike<number>, what: string) => {
  assert.equal(a.length, b.length, what);
  for (let i = 0; i < a.length; i++) if (!Object.is(a[i], b[i])) assert.fail(`${what}: bar ${i}: ${a[i]} vs ${b[i]}`);
};
const bars = (n: number) => { const c = Array.from({ length: n }, (_, i) => 100 + i); return { O: c, H: c, L: c, C: c, V: c } };
const row = (d: string, b: string, i: string, m: string, bv: number, sv: number): BrokerRow => ({ d, b, i, m, bv, sv, bl: 0, sl: 0 });
const cond = (type: string, params: Record<string, unknown>, op: string, value: number): FlowCondition => ({ id: 'f', kind: 'flow', type, params, op, value });
const codeOf = (f: () => unknown) => { try { f() } catch (e) { if (e instanceof ValidationError) return [e.code, e.field]; throw e } return null };

/* ---- hand-computed -------------------------------------------------------------------------------------------- */
const D = ['2025-01-02', '2025-01-03', '2025-01-06', '2025-01-07', '2025-01-08', '2025-01-09'];
const ROWS = [
  row('2024-12-31', 'AK', 'Foreign', 'Regular', 999, 0),                                   // no price bar that day
  row(D[1], 'AK', 'Foreign', 'Regular', 100, 30), row(D[1], 'AK', 'Domestic', 'Regular', 50, 0),
  row(D[1], 'YP', 'Foreign', 'Nego', 0, 20), row(D[1], 'YP', 'Domestic', 'Tunai', 10, 40),
  // D[2]: no broker row (counts 0)
  row(D[3], 'AK', 'Foreign', 'Tunai', 5, 0), row(D[3], 'ZP', 'Domestic', 'Regular', 0, 100),
  row(D[4], 'YP', 'Foreign', 'Regular', 300, 0),
  // D[5]: after the last broker date (no flow)
];
const N_ = NaN;

test('flowData: foreign net over every broker and board, broker net over both investors; 0 on a session without rows, NaN outside the broker dates', () => {
  const f = flowData(ROWS, D, [{ d: D[3], m: 'Regular' }, { d: '2024-12-31', m: 'Nego' }]);
  same(f.fnet, [N_, 50, 0, 5, 300, N_], 'fnet');
  assert.deepEqual([...f.brokers.keys()], ['AK', 'YP', 'ZP']);
  same(f.brokers.get('AK')!, [N_, 120, 0, 5, 0, N_], 'AK');
  same(f.brokers.get('YP')!, [N_, -50, 0, 0, 300, N_], 'YP');
  same(f.brokers.get('ZP')!, [N_, 0, 0, -100, 0, N_], 'ZP');
  assert.deepEqual([f.from, f.to, f.unmatched_rows, f.gap_bars], [1, 4, 1, [3]]);
  same(rollingSum(f.fnet, 2, f.from, f.to), [N_, N_, 50, 5, 305, N_], 'fnet 2D');
  same(rollingSum(f.fnet, 1, f.from, f.to), [N_, 50, 0, 5, 300, N_], 'fnet 1D');
  same(rollingSum(f.fnet, 5, f.from, f.to), [N_, N_, N_, N_, N_, N_], 'longer than the broker dates');
  same(top5Accumulation(f, 1), [N_, N_, 0, -95, 300, N_], 'top5 1D');              // the page starts at bar n of the series
  const none = flowData([], D);
  assert.deepEqual([none.from, none.to, none.brokers.size], [6, -1, 0]);
  same(none.fnet, D.map(() => N_), 'no rows');
});

test('flow conditions on the hand-computed sums (page cmpSeries: bar 0 never, no value never)', () => {
  const c = new Calc(bars(D.length), flowData(ROWS, D));
  const s = (q: FlowCondition) => [...conditionSeries(c, q)];
  assert.deepEqual(s(cond('fnet', { length: 2 }, 'gt', 0)), [0, 0, 1, 1, 1, 0]);
  assert.deepEqual(s(cond('fnet', { length: 2 }, 'lt', 10)), [0, 0, 0, 1, 0, 0]);
  assert.deepEqual(s(cond('fnet', { length: 1 }, 'gt', -1)), [0, 1, 1, 1, 1, 0]);
  assert.deepEqual(s(cond('broker', { length: 1, broker: 'AK' }, 'gt', 100)), [0, 1, 0, 0, 0, 0]);
  assert.deepEqual(s(cond('broker', { length: 3, broker: 'YP' }, 'gt', 200)), [0, 0, 0, 0, 1, 0]);   // -50+0+0, 0+0+300
  assert.deepEqual(s(cond('top5', { length: 1 }, 'gt', -100)), [0, 0, 1, 1, 1, 0]);
  assert.deepEqual(s(cond('top5', { length: 1 }, 'gt', 0)), [0, 0, 0, 0, 1, 0]);
  assert.ok(c.flowMemo.has('fnet|2') && c.flowMemo.has('broker|AK|1') && c.flowMemo.has('top5|1'));
});

test('a broker without any row on the ticker\'s bars has a net of 0 on every bar with broker data (lead decision 2026-10-26)', () => {
  const f = flowData(ROWS, D), c = new Calc(bars(D.length), f);
  assert.equal(brokerNet(f, 'AK'), f.brokers.get('AK'));
  same(brokerNet(f, 'XX'), [N_, 0, 0, 0, 0, N_], 'XX');                           // NaN outside [from, to], as every flow series
  same(brokerNet(flowData([], D), 'XX'), D.map(() => N_), 'no broker data');
  // its condition is evaluated on those zeros (the code is checked against the broker list by the worker's validation)
  assert.deepEqual([...conditionSeries(c, cond('broker', { length: 2, broker: 'XX' }, 'gt', -1))], [0, 0, 1, 1, 1, 0]);
  assert.deepEqual([...conditionSeries(c, cond('broker', { length: 2, broker: 'XX' }, 'gt', 0))], [0, 0, 0, 0, 0, 0]);
  assert.ok(c.flowMemo.has('broker|XX|2'));
});

/* ---- against the Terminal --------------------------------------------------------------------------------------- */
let seed = 20261026;
const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
const BROKERS = ['AK', 'BK', 'CC', 'DX', 'KZ', 'RX', 'YP', 'YU', 'ZP', 'AG', 'CP', 'LG'];
const INV = ['Foreign', 'Domestic'], BRD = ['Regular', 'Nego', 'Tunai'];
function market(nDates: number, brokers: string[], firstRow: number, lastRow: number) {
  const dates: string[] = [];
  for (let t = Date.UTC(2024, 0, 1); dates.length < nDates; t += 864e5) { const w = new Date(t).getUTCDay(); if (w && w < 6) dates.push(new Date(t).toISOString().slice(0, 10)) }
  const rows: [string, string, string, string, number, number, number, number, boolean][] = [];
  const days = ['2023-12-29', ...dates.slice(firstRow, lastRow + 1).filter(() => rnd() > 0.08)];      // a day before the prices, some sessions without rows
  for (const d of days) for (const b of brokers) for (const i of INV) for (const m of BRD) {
    if (rnd() < (m === 'Regular' ? 0.35 : 0.85)) continue;
    // fractional rupiah, so the order of the additions shows in the bits
    rows.push([d, b, i, m, Math.round(rnd() * 5e11) / 100 + 0.3, Math.round(rnd() * 5e11) / 100 + 0.7, Math.round(rnd() * 1e6) / 10, Math.round(rnd() * 1e6) / 10, false]);
  }
  rows.sort((x, y) => x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] < y[1] ? -1 : x[1] > y[1] ? 1 : x[2] < y[2] ? -1 : x[2] > y[2] ? 1 : x[3] < y[3] ? -1 : 1);
  return { dates, docs: [brokerDoc('TEST', null, rows) as unknown as Columnar] };
}
/* the Terminal: app/indicators.ts netBuyFlow and brokerLines (Rolling) and app/flow.ts recomputeFlow, on its combos */
type Combo = { broker: string; investor: string; board: string; net: Float64Array };
function terminalNet(combos: Combo[], N: number, keep: (c: Combo) => boolean) {
  const net = new Float64Array(N);
  combos.forEach(c => { if (!keep(c)) return; for (let i = 0; i < N; i++) net[i] += c.net[i] });
  return net;
}
function terminalRolling(net: Float64Array, length: number) {
  const N = net.length, out: (number | null)[] = new Array(N).fill(null); let sum = 0;
  for (let i = 0; i < N; i++) { sum += net[i]; if (i >= length) sum -= net[i - length]; if (i >= length - 1) out[i] = sum }
  return out;
}

test('daily foreign and broker net and their rolling sums equal the Terminal (brokerData, recomputeFlow, netBuyFlow, brokerLines) bit for bit where both have a value', () => {
  const { dates, docs } = market(80, BROKERS, 6, 70), N = dates.length;
  const t = brokerData(docs as any, dates), f = flowData(brokerRows(docs), dates);
  assert.deepEqual([f.from, f.to], [t.flowFrom, t.flowTo]);
  const all = t.combos as Combo[];
  const tf = terminalNet(all, N, c => c.investor === 'Foreign');
  for (let i = 0; i < N; i++) {
    if (i < f.from || i > f.to) assert.ok(Number.isNaN(f.fnet[i]) && tf[i] === 0, `bar ${i} outside`);
    else assert.ok(Object.is(f.fnet[i], tf[i]), `fnet bar ${i}: ${f.fnet[i]} vs ${tf[i]}`);
  }
  for (const b of BROKERS) {
    const tb = terminalNet(all, N, c => c.broker === b);
    for (let i = f.from; i <= f.to; i++) assert.ok(Object.is(f.brokers.get(b)![i], tb[i]), `${b} bar ${i}`);
    for (const len of [1, 5, 20]) {
      const ours = rollingSum(f.brokers.get(b)!, len, f.from, f.to), theirs = terminalRolling(tb, len);
      for (let i = 0; i < N; i++) {
        if (i >= f.from + len - 1 && i <= f.to) assert.ok(Object.is(ours[i], theirs[i]), `${b} ${len}D bar ${i}: ${ours[i]} vs ${theirs[i]}`);
        else assert.ok(Number.isNaN(ours[i]), `${b} ${len}D bar ${i} has no value here`);
      }
    }
  }
  for (const len of [1, 5, 10, 60]) {
    const ours = rollingSum(f.fnet, len, f.from, f.to), theirs = terminalRolling(tf, len);
    for (let i = f.from + len - 1; i <= f.to; i++) assert.ok(Object.is(ours[i], theirs[i]), `fnet ${len}D bar ${i}`);
  }
  assert.equal(f.unmatched_rows, (docs[0].d as string[]).filter(d => d === '2023-12-29').length);
  assert.ok(f.unmatched_rows > 0);
});

/* the page (backtest.html section 2 rollsum, section 3 cmpSeries and CATALOG fnet / top5), on its own arrays from bar 0 */
const rollsum = (a: ArrayLike<number>, n: number) => { const r = new Float64Array(a.length).fill(NaN); let s = 0; for (let i = 0; i < a.length; i++) { s += a[i]; if (i >= n) s -= a[i - n]; if (i >= n - 1) r[i] = s } return r };
const cmpSeries = (s: ArrayLike<number>, op: string, v: number) => { const r = new Uint8Array(s.length); for (let i = 1; i < s.length; i++) { const x = s[i], p = s[i - 1]; if (isNaN(x)) continue; r[i] = +(op === 'gt' ? x > v : op === 'lt' ? x < v : op === 'ca' ? (p <= v && x > v) : op === 'cb' ? (p >= v && x < v) : 0) } return r };
function pageTop5(br: Record<string, ArrayLike<number>>, brokers: string[], N: number, len: number) {
  const acc = new Float64Array(N).fill(NaN), sums = brokers.map(b => rollsum(br[b], len));
  for (let i = len; i < N; i++) {
    const v = sums.map(s => s[i]).sort((a, b) => b - a);
    acc[i] = v.slice(0, 5).filter(x => x > 0).reduce((s, x) => s + x, 0) + v.slice(-5).filter(x => x < 0).reduce((s, x) => s + x, 0);
  }
  return acc;
}
const pageTop5Signal = (acc: Float64Array, val: number) => { const r = new Uint8Array(acc.length); for (let i = 0; i < acc.length; i++) r[i] = +(acc[i] / 1e9 > val); return r };

for (const [label, brokers] of [['12 brokers', BROKERS], ['3 brokers (the top and bottom five overlap)', BROKERS.slice(0, 3)]] as const) {
  test(`top5 and fnet equal the page's formulas on the page's arrays (${label})`, () => {
    const { dates, docs } = market(90, brokers as string[], 0, 89), N = dates.length;
    const f = flowData(brokerRows(docs), dates), c = new Calc(bars(N), f);
    const seg = (a: Float64Array) => a.slice(f.from, f.to + 1), M = f.to - f.from + 1;   // the page's arrays start where the data starts
    const br = Object.fromEntries([...f.brokers].map(([b, a]) => [b, seg(a)]));
    for (const len of [1, 3, 10]) {
      const page = pageTop5(br, [...f.brokers.keys()], M, len), ours = top5Accumulation(f, len);
      for (let i = 0; i < N; i++) {
        const j = i - f.from;
        if (j >= len && i <= f.to) assert.ok(Object.is(ours[i], page[j]), `top5 ${len}D bar ${i}: ${ours[i]} vs ${page[j]}`);
        else assert.ok(Number.isNaN(ours[i]), `top5 ${len}D bar ${i} has no value here`);
      }
      for (const val of [-2, 0, 0.5, 2]) {
        const want = pageTop5Signal(page, val), got = flowCondition(c, cond('top5', { length: len }, 'gt', val * 1e9));
        for (let i = 0; i < N; i++) assert.equal(got[i], i >= f.from && i <= f.to ? want[i - f.from] : 0, `top5 ${len}D > ${val} bar ${i}`);
      }
      for (const [op, val] of [['gt', 0], ['lt', 0], ['gt', 1], ['lt', -1]] as const) {
        const want = cmpSeries(Float64Array.from(rollsum(seg(f.fnet), len), x => x / 1e9), op, val), got = flowCondition(c, cond('fnet', { length: len }, op, val * 1e9));
        for (let i = 0; i < N; i++) if (i > f.from) assert.equal(got[i], want[i - f.from], `fnet ${len}D ${op} ${val} bar ${i}`);
      }
    }
  });
}

test("the page's flow cards (catalog.ts legacyToCondition: fnet, broker YU, top5) evaluate on flow data", () => {
  const { dates, docs } = market(60, BROKERS, 0, 59), c = new Calc(bars(dates.length), flowData(brokerRows(docs), dates));
  for (const card of [legacyCard('fnet', 'a'), legacyCard('broker', 'b'), legacyCard('top5', 'c'), legacyCard('fnet', 'd', { op: 'lt', val: 0, len: 5 })]) {
    const s = conditionSeries(c, legacyToCondition(card) as FlowCondition);
    assert.equal(s.length, dates.length);
  }
});

test('flow conditions refuse what the page cannot send and data they cannot read', () => {
  const f = flowData(ROWS, D), c = new Calc(bars(D.length), f), ok = cond('fnet', { length: 5 }, 'gt', 0);
  assert.deepEqual(codeOf(() => conditionSeries(new Calc(bars(D.length)), ok)), ['FLOW_UNAVAILABLE', 'condition']);
  assert.deepEqual(codeOf(() => conditionSeries(new Calc(bars(D.length)), { id: 'x', kind: 'flow', type: 'fnet' } as FlowCondition)), ['FLOW_UNAVAILABLE', 'condition']);
  assert.deepEqual(codeOf(() => conditionSeries(new Calc(bars(D.length), flowData([], D)), ok)), ['FLOW_UNAVAILABLE', 'condition']);
  // a series without any value on the ticker's bars (a window longer than its bars with broker data, 4 here)
  assert.deepEqual(codeOf(() => conditionSeries(c, cond('fnet', { length: 5 }, 'gt', 0))), ['FLOW_OUTPUT_EMPTY', 'condition.params.length']);
  assert.deepEqual(codeOf(() => conditionSeries(c, cond('broker', { length: 5, broker: 'AK' }, 'gt', 0))), ['FLOW_OUTPUT_EMPTY', 'condition.params.length']);
  assert.deepEqual(codeOf(() => conditionSeries(c, cond('broker', { length: 5, broker: 'XX' }, 'gt', 0))), ['FLOW_OUTPUT_EMPTY', 'condition.params.length']);
  assert.deepEqual(codeOf(() => conditionSeries(c, cond('top5', { length: 4 }, 'gt', 0))), ['FLOW_OUTPUT_EMPTY', 'condition.params.length']);   // from at bar from + n
  assert.equal(codeOf(() => conditionSeries(c, cond('top5', { length: 3 }, 'gt', 0))), null);
  const cases: [FlowCondition, [string, string]][] = [
    [cond('volume', { length: 5 }, 'gt', 0), ['UNKNOWN_CONDITION', 'condition.type']],
    [cond('__proto__', { length: 5 }, 'gt', 0), ['UNKNOWN_CONDITION', 'condition.type']],
    [cond('broker', { length: 5, broker: 'AK' }, 'lt', 0), ['INVALID_CONDITION', 'condition.op']],
    [cond('top5', { length: 5 }, 'crosses_above', 0), ['INVALID_CONDITION', 'condition.op']],
    [{ id: 'x', kind: 'flow', type: 'fnet', op: 'gt', value: 0 }, ['INVALID_PARAMS', 'condition.params']],
    [cond('fnet', { length: 0 }, 'gt', 0), ['INVALID_PARAM', 'condition.params.length']],
    [cond('fnet', { length: 2.5 }, 'gt', 0), ['INVALID_PARAM', 'condition.params.length']],
    [cond('fnet', { length: '5' }, 'gt', 0), ['INVALID_PARAM', 'condition.params.length']],
    [cond('fnet', {}, 'gt', 0), ['INVALID_PARAM', 'condition.params.length']],
    [cond('fnet', { length: 5, broker: 'AK' }, 'gt', 0), ['PARAM_NOT_ACCEPTED', 'condition.params.broker']],
    [cond('top5', { length: 5, window: 3 }, 'gt', 0), ['PARAM_NOT_ACCEPTED', 'condition.params.window']],
    [cond('broker', { length: 5 }, 'gt', 0), ['INVALID_PARAM', 'condition.params.broker']],
    [cond('fnet', { length: 5 }, 'gt', NaN), ['INVALID_CONDITION', 'condition.value']],
    [cond('fnet', { length: 5 }, 'gt', '1' as unknown as number), ['INVALID_CONDITION', 'condition.value']],
  ];
  for (const [q, want] of cases) {
    assert.deepEqual(codeOf(() => conditionSeries(c, q)), want, JSON.stringify(q));
    assert.deepEqual(codeOf(() => flowConditionShape(q)), want, `shape only: ${JSON.stringify(q)}`);   // without any data
  }
  assert.throws(() => new Calc(bars(D.length + 1), f), RangeError);                 // flow data of other bars
});
