/* EXEC-BACKTEST-REVAMP P3: the Flow indicators in the grammar, read per bar from the ticker's whole broker history with
   the Terminal's formula as it is. For every Flow indicator a backtest offers (the Screener's entries computed by the
   Terminal module, without the ones refused: FL31, the anchored and inventory entries, the Screener's own entries) and
   every output and option (one at a time, as the look-ahead gate does), the series the grammar reads equals
   calc/flow.ts computeFlow on the same rows and bars, value for value, with the registry's baselines (nothing lowered)
   and FL34 on every date (user decision 5). The same series computed on the data cut at day t equals the full one up
   to t (no look-ahead through this path). Synthetic market (tests/lookahead/fixture.ts), no database. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as TF from '../../edge-bff/terminal/src/calc/flow.ts';
import { Calc, conditionSeries } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { BrokerColumns } from '../../edge-bff/backtest/src/core/datafile.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { FLOWS } from './lookahead/flow-helpers.ts';
import { head, market } from './lookahead/fixture.ts';
import type { Row, Ticker } from './lookahead/fixture.ts';
import { installBacktestGrammar, seriesOfRef } from '../src/grammar.ts';

installBacktestGrammar();
const M = market(), A = M.stocks[0];
const CLS = { AA: 'Institutional-heavy', BK: 'Retail-heavy', SQ: 'Institutional-heavy', YP: 'Retail-heavy', XL: 'Mixed' };

/** Fixture rows as the published columns (brokerColumns' shape; the fixture's Cash board is the files' Tunai). */
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
const calcAt = (t: Ticker, rows: readonly Row[], n: number) => {
  const h = head(t, n), last = h.dates[h.dates.length - 1];
  return new Calc(h.bars as never, undefined, { ticker: t.ticker, dates: h.dates, index: { dates: M.ihsg.dates, bars: M.ihsg.bars as never },
    broker: { columns: columns(rows.filter(r => r.d <= last)), classification: CLS } });
};
/** computeFlow on the same rows and bars (the fixture has broker rows on every session: the window is every bar). */
const terminal = (t: Ticker, rows: readonly Row[], id: string, params: Record<string, unknown>) => {
  const at = new Map(t.dates.map((d, k) => [d, k]));
  return TF.computeFlow(id, { rows: TF.flowRows(rows as never, t.dates.length, d => at.get(d) ?? -1), dates: t.dates, close: t.bars.C as number[], volume: t.bars.V as number[],
    insider: [], classification: CLS }, params);
};
const same = (a: ArrayLike<unknown>, b: ArrayLike<unknown>, what: string) => {
  assert.equal(a.length, b.length, what);
  for (let i = 0; i < a.length; i++) {
    const x = a[i] ?? null, y = b[i] ?? null;
    if (!(x === y || (typeof x === 'number' && typeof y === 'number' && Object.is(x, y)))) assert.fail(`${what}: bar ${i} grammar ${x} terminal ${y}`);
  }
};

test('every offered Flow indicator, output and option: the grammar series equals the Terminal formula on the whole history', () => {
  const rows = M.rows[A.ticker], c = calcAt(A, rows, A.dates.length);
  let n = 0, refused = 0;
  for (const e of FLOWS) for (const v of e.variants) for (const o of e.outputs) {
    let s: ArrayLike<number | null | undefined>;
    try { s = seriesOfRef(c, { kind: 'flow', metric: e.id, output: o, params: v }, 'f') }
    catch (err) { if (err instanceof ValidationError) { refused++; continue } throw err }
    const r = terminal(A, rows, e.id, e.normalized(v));
    const k = e.seriesKey(o, v);
    if (!(k in r)) continue;                                                    // a sided line the side does not draw
    same(s, r[k], `${e.id}.${o} ${JSON.stringify(v)}`);
    n++;
  }
  console.log(`flow parity: ${n} series equal, ${refused} option combinations the Screener's validation refuses`);
  assert.ok(n > 150, `${n} series`);
});

test('FL34 reads today\'s classification on every date, and no baseline is lowered', () => {
  const c = calcAt(A, M.rows[A.ticker], A.dates.length);
  const s = seriesOfRef(c, { kind: 'flow', metric: 'FL34', params: {} }, 'f');
  assert.ok(Array.from(s).slice(0, -1).filter(x => typeof x === 'number').length > 100, 'values before the last date');
  const base = FLOWS.find(e => e.defaults.baseline !== undefined)!;
  assert.equal(base.normalized({}).baseline, base.defaults.baseline, `${base.id}: the registry's baseline`);
});

test('no look-ahead through the grammar: the series on the data cut at t equals the full series up to t', () => {
  const rows = M.rows[A.ticker], full = calcAt(A, rows, A.dates.length), cuts = [120, 260, 333, 480];
  const leaks: string[] = [];
  for (const e of FLOWS) for (const o of e.outputs) {
    let s: ArrayLike<number | null | undefined>;
    const ref = { kind: 'flow', metric: e.id, output: o, params: {} };
    try { s = seriesOfRef(full, ref, 'f') } catch (err) { if (err instanceof ValidationError) continue; throw err }
    for (const k of cuts) {
      const p = seriesOfRef(calcAt(A, rows, k), ref, 'f');
      for (let i = 0; i < k; i++) if ((p[i] ?? null) !== (s[i] ?? null) && !(Number.isNaN(p[i]) && Number.isNaN(s[i]))) { leaks.push(`${e.id}.${o} at ${i} cut ${k}`); break }
    }
  }
  assert.deepEqual(leaks, []);
});

test('a Flow condition: per-bar test, FLOW_UNAVAILABLE without broker data, the refused entries name their reason', () => {
  const c = calcAt(A, M.rows[A.ticker], A.dates.length);
  // FL01's lots per transaction are tested by their own history (a value is not offered on them): a cross of 0 by its change
  const cond = (metric: string) => ({ id: 'f1', kind: 'test', test: { kind: 'event', within: 1, signal: { lhs: { kind: 'transform', fn: 'change', of: { kind: 'flow', metric, output: 'buy', params: {} }, args: { bars: 1 } }, op: 'crosses_above', rhs: { value: 0 } } } }) as never;
  assert.ok(conditionSeries(c, cond('FL01'), 'f').some(Boolean));
  const bare = new Calc(A.bars as never, undefined, { ticker: A.ticker, dates: A.dates });
  assert.throws(() => conditionSeries(bare, cond('FL01'), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'FLOW_UNAVAILABLE');
  const refused = (id: string) => () => conditionSeries(c, { id: 'f1', kind: 'test', test: { kind: 'value', metric: { kind: 'flow', metric: id, params: {} }, op: 'gt', value: 0 } } as never, 'f');
  for (const id of ['FL31', 'fnet', 'ksei_net', 'FL52'])
    assert.throws(refused(id), (e: unknown) => e instanceof ValidationError && e.code === 'CONDITION_UNAVAILABLE' && /test\.metric$/.test(e.field ?? ''), id);
  // P4: the point-in-time versions need their anchor or start date
  for (const [id, key] of [['FL18', 'anchor'], ['FL19', 'anchor'], ['FL20', 'anchor'], ['FL44', 'anchor'], ['FL45', 'anchor'], ['FL23', 'start'], ['FL51', 'start']])
    assert.throws(refused(id), (e: unknown) => e instanceof ValidationError && e.code === 'ANCHOR_REQUIRED' && e.field === `f.test.metric.params.${key}`, id);
});

/* ---- P3 (K3 a, ERRORS M448): broker prices on another basis than the prices, and the Flow data warnings ---------- */
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import { sessions, ticker as mkTicker, brokerRows as mkRows } from './lookahead/fixture.ts';

test('a broker-price value is empty where its window reads lots on another basis; every other value is the Terminal\'s', () => {
  const dates = sessions('2026-05-04', 140), t = mkTicker('BASE', 41, dates), rows = mkRows(t, 42);
  const pre = dates[30], post = dates[110];                               // ex-dates before and after 2026-09-12
  assert.ok(pre < '2026-09-12' && post > '2026-09-12');
  const calc = (actions: string[]) => new Calc(t.bars as never, undefined, { ticker: t.ticker, dates, broker: { columns: columns(rows), classification: CLS, actions } });
  const ref = { kind: 'flow', metric: 'FL17', params: { window: 10 } };
  const term = terminal(t, rows, 'FL17', FLOWS.find(e => e.id === 'FL17')!.normalized({ window: 10 }))[FLOWS.find(e => e.id === 'FL17')!.seriesKey('value', { window: 10 })];
  const c = calc([pre, post]), s = seriesOfRef(c, ref, 'f');
  for (let i = 0; i < dates.length; i++) {
    const start = Math.max(0, i - 9), reads = (d: string) => dates[start] < d && (d <= '2026-09-12' || dates[i] >= d);
    const want = reads(pre) || reads(post) ? null : term[i] ?? null;
    assert.equal(s[i] ?? null, want, `bar ${i} (${dates[i]})`);
  }
  assert.ok(c.flowNotes!.masked.size >= 30 + 9, 'every bar before the adjusted action, and the windows across the later one');
  // a Flow indicator that is not a broker price is never masked
  const n = seriesOfRef(calc([pre, post]), { kind: 'flow', metric: 'FL11', params: {} }, 'f');
  const fl11 = FLOWS.find(e => e.id === 'FL11')!;
  same(n, terminal(t, rows, 'FL11', fl11.normalized({}))[fl11.seriesKey('value', {})], 'FL11 unmasked');
});

test("the run's Flow warnings: before 2021, basis change, source gaps and dropped rows, per stock over the sessions read", () => {
  const dates = sessions('2020-06-01', 420), t = mkTicker('WARN', 51, dates), rows = mkRows(t, 52);
  const gaps = [{ d: dates[300], m: 'Regular' }, { d: dates[350], m: 'Nego' }];
  // rows on two days without a price bar (a Nego crossing on a holiday-like date between two sessions)
  const extra = [{ ...rows[0], d: '2021-07-04', m: 'Nego' }, { ...rows[1], d: '2021-07-04', m: 'Regular' }] as typeof rows;
  const all = [...rows, ...extra].sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
  const action = dates[320];
  const market = (actions: string[]) => prepare({ ihsg: { ticker: 'IHSG', dates, bars: t.bars, dropped: 0 } as never,
    tickers: { WARN: { prices: { ticker: 'WARN', dates, bars: t.bars, dropped: 0 } as never, corporate_actions: actions.map(date => ({ date, type: 'RIGHT_ISSUE' })),
      flow: flowData(all as never, dates, gaps as never), broker: columns(all) } }, classification: CLS });
  const req = (from: string, metric: string) => ({
    schema_version: 1, mode: 'single', single: { ticker: 'WARN', benchmark: 'buy_and_hold' }, period: { from, to: dates[dates.length - 1], oos_fraction: 0 },
    entry: { logic: 'all', at_least: 1, window_bars: 1, conditions: [{ id: 'f1', kind: 'test', test: { kind: 'event', within: 3, signal: { lhs: { kind: 'flow', metric, params: { window: 20 } }, op: 'crosses_above', rhs: metric === 'FL17' ? { kind: 'price', field: 'close' } : { value: 0 } } } }] },
    exit: { atr_length: 14, stop: { mode: 'pct', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } }, take_profit: { mode: 'none', pct: 0.15, r_multiple: 2, atr_mult: 3 },
      trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } }, max_hold_bars: 20, signals: { logic: 'any', conditions: [] } },
    sizing: { capital_idr: 100e6, allocation_fraction: 1 }, costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: false, ara_gap_fraction: 0.2 },
    robustness: { monte_carlo_runs: 0, seed: 7, sensitivity: false } }) as never;
  const codes = (l: { warnings: { code: string; count?: number; tickers?: string[] }[] }) => Object.fromEntries(l.warnings.filter(w => w.code.startsWith('FLOW_')).map(w => [w.code, [w.count, w.tickers]]));
  // a period from 2021-02 whose 20-session window reaches into 2021 only: no FLOW_PRE_2021; an action inside: basis change
  const a = run(market([action]), req(dates.find(d => d >= '2021-03-01')!, 'FL17'));
  const w = codes(a);
  assert.equal(w.FLOW_PRE_2021, undefined, 'the sessions read start in 2021');
  assert.deepEqual(w.FLOW_BASIS_CHANGE, [1, ['WARN']]);
  assert.deepEqual(w.FLOW_SOURCE_GAP, [2, ['WARN']]);
  assert.deepEqual(w.FLOW_ROWS_DROPPED, [2, ['WARN']]);
  assert.match(a.warnings.find(x => x.code === 'FLOW_ROWS_DROPPED')!.message, /1 day on the Regular board, 1 day on the Nego board/);
  // P7 (K4 a, M447): the rights issue inside the period restates the published prices before it
  assert.deepEqual(a.warnings.filter(x => x.code === 'PRICES_RESTATED').map(x => [x.count, x.tickers]), [[1, ['WARN']]]);
  assert.deepEqual(run(market([]), req(dates.find(d => d >= '2021-03-01')!, 'FL17')).warnings.filter(x => x.code === 'PRICES_RESTATED'), []);
  // from 2020: FLOW_PRE_2021; FL11 is no broker price, so no basis change
  const b = codes(run(market([action]), req(dates[25], 'FL11')));
  assert.deepEqual(b.FLOW_PRE_2021, [1, ['WARN']]);
  assert.equal(b.FLOW_BASIS_CHANGE, undefined);
  // no Flow condition: no Flow warning
  const plain = run(market([]), { ...(req(dates[25], 'FL11') as object), entry: { logic: 'all', at_least: 1, window_bars: 1, conditions: [{ id: 'r', kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 40 } }] } } as never);
  assert.deepEqual(codes(plain), {});
});
