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
import type { BasisAction, BrokerColumns } from '../../edge-bff/backtest/src/core/datafile.ts';
import { onPriceBasis, unknownBasis } from '../../edge-bff/backtest/src/core/datafile.ts';
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
/** computeFlow on the same rows and bars, every bar (the grammar's window is the bars from the first to the last broker
    date; outside it the grammar is empty). */
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

/* Stage C2 (lens 1 F2, F4): the grammar is the Terminal's formula on the data up to each session. Two places differ from
   computeFlow on the whole history: a session without broker rows (a source gap; the data up to it ends the session
   before) is empty, and before a named broker's first row the broker is not a member yet (on the whole history the
   Terminal counts it as one): there the Terminal is asked with that broker's code replaced by one no row has. */
const FIRST = (rows: readonly Row[], t: Ticker) => { const m = new Map<string, number>(); for (const r of rows) if (!m.has(r.b)) m.set(r.b, t.dates.indexOf(r.d)); return m };
const asOfDay = (t: Ticker, rows: readonly Row[], id: string, params: Record<string, unknown>, key: string): (number | null)[] => {
  const first = FIRST(rows, t), lists = Object.entries(params).filter(([k, v]) => /brokers$|^inst$|^retail$/.test(k) && Array.isArray(v)) as [string, string[]][];
  const days = new Set(rows.map(r => r.d)), full = terminal(t, rows, id, params)[key];
  return Array.from(full, (x, i) => {
    if (!days.has(t.dates[i])) return null;
    const late = lists.some(([, codes]) => codes.some(code => (first.get(code) ?? -1) > i));
    if (!late) return x ?? null;
    const q = { ...params }; for (const [k, codes] of lists) q[k] = codes.map(code => (first.get(code) ?? -1) > i ? '\u0000' + code : code);
    return terminal(t, rows, id, q)[key][i] ?? null;
  });
};
test('every offered Flow indicator, output and option: the grammar series equals the Terminal formula on the data up to each session', () => {
  const rows = M.rows[A.ticker], c = calcAt(A, rows, A.dates.length), lastRow = A.dates.indexOf(rows[rows.length - 1].d);
  let n = 0, refused = 0;
  for (const e of FLOWS) for (const v of e.variants) for (const o of e.outputs) {
    let s: ArrayLike<number | null | undefined>;
    try { s = seriesOfRef(c, { kind: 'flow', metric: e.id, output: o, params: v }, 'f') }
    catch (err) { if (err instanceof ValidationError) { refused++; continue } throw err }
    const q = e.normalized(v), k = e.seriesKey(o, v);
    if (!(k in terminal(A, rows, e.id, q))) continue;                            // a sided line the side does not draw
    const want = asOfDay(A, rows, e.id, q, k).map((x, i) => i > lastRow ? null : x);   // after the last broker date: empty
    same(s, want, `${e.id}.${o} ${JSON.stringify(v)}`);
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
  for (const e of FLOWS) for (const v of e.variants) for (const o of e.outputs) {
    let s: ArrayLike<number | null | undefined>;
    const ref = { kind: 'flow', metric: e.id, output: o, params: v };
    try { s = seriesOfRef(full, ref, 'f') } catch (err) { if (err instanceof ValidationError) continue; throw err }
    for (const k of cuts) {
      const p = seriesOfRef(calcAt(A, rows, k), ref, 'f');
      for (let i = 0; i < k; i++) if ((p[i] ?? null) !== (s[i] ?? null) && !(Number.isNaN(p[i]) && Number.isNaN(s[i]))) { leaks.push(`${e.id}.${o} ${JSON.stringify(v)} at ${i} cut ${k}`); break }
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

/* ---- P3 (K3 a, ERRORS M450): broker prices on another basis than the prices, and the Flow data warnings ---------- */
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import { sessions, ticker as mkTicker, brokerRows as mkRows } from './lookahead/fixture.ts';

test('P9: broker prices on the price basis; empty only where the data up to the bar leaves the basis unsettled', () => {
  const dates = sessions('2026-05-04', 140), t = mkTicker('BASE', 41, dates), base = mkRows(t, 42);
  const terms = dates[30], off = dates[60], unresolved = dates[80], raw = dates[110];
  // as published: the lots before a rights issue the prices carry are on the traded scale (1.5x fewer, so the broker VWAP
  // is 1.5x the adjusted close), and one Regular day is off the scale with no action (a range re-downloaded, PBSA)
  const published = base.map(r => ({ ...r, bl: r.d < terms ? r.bl / 1.5 : r.bl, sl: r.d < terms ? r.sl / 1.5 : r.sl,
    bv: r.d === off && r.m === 'Regular' ? r.bv * 1.5 : r.bv, sv: r.d === off && r.m === 'Regular' ? r.sv * 1.5 : r.sv }));
  const basis: BasisAction[] = [{ ex: terms, type: 'RIGHT_ISSUE', factor: 1.5, status: 'terms', price: 'adjusted' },
    { ex: unresolved, type: 'STOCK_SPLIT', factor: 1, status: 'unresolved', price: null }, { ex: raw, type: 'STOCK_SPLIT', factor: 1, status: 'same', price: 'raw' }];
  const cols = onPriceBasis(columns(published), basis);
  // the lots are back on the price basis: the published rows times the factor before the ex date
  const onBasis = published.map(r => ({ ...r, bl: r.d < terms ? r.bl * 1.5 : r.bl, sl: r.d < terms ? r.sl * 1.5 : r.sl }));
  const calc = () => new Calc(t.bars as never, undefined, { ticker: t.ticker, dates, broker: { columns: cols, classification: CLS, basis } });
  const e17 = FLOWS.find(e => e.id === 'FL17')!, term = terminal(t, onBasis, 'FL17', e17.normalized({ window: 10 }))[e17.seriesKey('value', { window: 10 })];
  const c = calc(), s = seriesOfRef(c, { kind: 'flow', metric: 'FL17', params: { window: 10 } }, 'f');
  let kept = 0;
  for (let i = 0; i < dates.length; i++) {
    const start = Math.max(0, i - 9), from = dates[start], to = dates[i];
    const blocked = (from <= off && off <= to) || [unresolved, raw].some(d => from < d && d <= to);
    assert.equal(s[i] ?? null, blocked ? null : term[i] ?? null, `bar ${i} (${dates[i]})`);
    if (!blocked && i < 30 && s[i] !== null) kept++;
  }
  assert.ok(kept >= 15, `the bars before the rights issue keep their values (${kept}); before P9 every one was empty`);
  assert.equal(c.flowNotes!.masked.size, Array.from(s).filter((v, i) => v === null && term[i] !== null).length);
  // a Flow indicator that is not a broker price is never masked (and reads the lots on the price basis too)
  const fl11 = FLOWS.find(e => e.id === 'FL11')!;
  same(seriesOfRef(calc(), { kind: 'flow', metric: 'FL11', params: {} }, 'f'), terminal(t, onBasis, 'FL11', fl11.normalized({}))[fl11.seriesKey('value', {})], 'FL11 unmasked');
  // an events file without the block: its actions read as unresolved, masked across them only
  const u = new Calc(t.bars as never, undefined, { ticker: t.ticker, dates, broker: { columns: columns(published), classification: CLS, basis: unknownBasis([{ date: terms, type: 'RIGHT_ISSUE' }]) } });
  const su = seriesOfRef(u, { kind: 'flow', metric: 'FL17', params: { window: 10 } }, 'f');
  // the days before it are off the price basis by their own data (VWAP 1.5x the close, outside the day's range): empty
  // through the per-day guard; a window after the action and away from the off day keeps its value
  assert.ok(su[20] === null && su[35] === null && su[50] !== null, 'the per-day guard catches what no factor settled');
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
  // P7 (K4 a, M449): the rights issue inside the period restates the published prices before it
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

test('Stage C2 (lens 1 F2, F3): a named broker counts from its own first row; no row after the period decides a run', () => {
  const rows = M.rows[A.ticker], c = calcAt(A, rows, A.dates.length), firstLate = A.dates.indexOf(rows.find(r => r.b === 'LATE')!.d);
  const cond = (params: Record<string, unknown>, metric = 'FL13', output = 'buy') => ({ id: 'f', kind: 'test', test: { kind: 'value', metric: { kind: 'flow', metric, output, params }, op: 'lt', value: 1 } }) as never;
  // LATE before its first row: not a member (FL13 of LATE alone: no member, no value); the period may end before it
  const late = cond({ scope: 'selected', brokers: ['LATE'] }), s = seriesOfRef(c, { kind: 'flow', metric: 'FL13', output: 'buy', params: { scope: 'selected', brokers: ['LATE'] } }, 'f');
  assert.ok(Array.from(s).slice(0, firstLate).every(x => x === null), 'empty before LATE trades the stock');
  assert.ok(Array.from(s).slice(firstLate).some(x => typeof x === 'number'), 'a value once it does');
  // the run's signals on the whole data equal those on the data cut at the period's end, whatever the end
  for (const params of [{ scope: 'selected', brokers: ['LATE'] }, { scope: 'selected', brokers: ['AA', 'LATE'] }, { inst: ['LATE'], retail: ['BK'] }])
    for (const last of [firstLate - 30, firstLate - 1, firstLate, firstLate + 40]) {
      const q = cond(params, 'inst' in params ? 'FL34' : 'FL13', 'inst' in params ? 'value' : 'buy');
      let full: ArrayLike<number> | string, cut: ArrayLike<number> | string;
      try { full = conditionSeries(c, q, 'f', last) } catch (e) { full = (e as ValidationError).code }
      try { cut = conditionSeries(calcAt(A, rows, last + 1), q, 'f', last) } catch (e) { cut = (e as ValidationError).code }
      if (typeof full === 'string' || typeof cut === 'string') { assert.equal(full, cut, `${JSON.stringify(params)} to ${last}`); continue }
      for (let i = 0; i <= last; i++) assert.equal(full[i], cut[i], `${JSON.stringify(params)} bar ${i} (period to ${last})`);
    }
  // a broker the stock never traded (ZZ) is in neither set: the Terminal's value, and never refused
  assert.doesNotThrow(() => conditionSeries(c, cond({ scope: 'selected', brokers: ['AA', 'ZZ'] }), 'f', 10));
});
