/* A flow condition when the broker data is behind the prices (QA unit B; P5_FLOW.md section 1, P10 a): a flow value is
   read at the stock's last candle with broker data, which is one or more sessions before its last price bar when the
   publication's broker days end before its prices (dev on 2026-11-07: three sessions). The defect: a stock with a
   history longer than the series tail (within_max + 1 = 131 bars) failed every flow event ("tail of FL32.buy on BBCA
   starts at bar 269, but bar 268 is needed": the event's within_max scan from the flow bar ran past a tail cut at the
   last price bar). The fixture of flow-fixture.ts has 84 bars, a tail of all of them, so it never showed.
   Here every stock has 300 price bars and the broker window ends 0, 1 or 3 sessions before them; each test (a value, a
   cross within N, K of N, a streak, a percentile measure) equals a brute-force reading of OPERATORS.md on the
   Terminal's own series (flow.ts computeFlow on flowRows of the same rows), stock by stock. */
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults, flowRows } from '../../../terminal/src/calc/flow.ts';
import type { Definition, Test } from '../../src/core/contract.ts';
import { round12 } from '../../src/core/evaluate.ts';
import type { FlowBindContext, TickerFlow } from '../../src/core/flowmetrics.ts';
import { runScreen } from '../../src/core/screen.ts';
import { BROKERS, CLASS, INVESTORS, BOARDS, PK, rowsOf, without } from './flow-fixture.ts';
import type { Row } from './flow-fixture.ts';
import { memoryEnv, rowOf, synth, tailBars } from './helpers.ts';

const BARS = 300, START = '2025-03-03';
const CALENDAR = synth('MKT', 1, BARS, START).dates as string[];
type S = (number | null)[];
const isN = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** The market with its broker window ending `lag` sessions before the last price bar: five stocks (every window date;
    the last broker day without a price bar; the last 30 dates only; a short history of 100 bars; no broker data). */
function market(lag: number) {
  const window = CALENDAR.slice(BARS - lag - 60, BARS - lag), first = window[0], last = window[59];
  const flow: FlowBindContext = { sessions: 60, first, last, complete: true, classification: true };
  const make = (ticker: string, seed: number, dates: readonly string[], o: { drop?: string[]; bars?: number } = {}) => {
    const rows = rowsOf(seed, dates).sort(PK), brokers = [...BROKERS].sort(), nan = (v: number | null) => v === null ? NaN : v;
    const store = {
      rows: rows.length, dates: window, brokers, investor_types: INVESTORS, boards: BOARDS,
      D: Uint16Array.from(rows, x => window.indexOf(x.d)), B: Uint16Array.from(rows, x => brokers.indexOf(x.b)),
      I: Uint8Array.from(rows, x => INVESTORS.indexOf(x.i as never)), M: Uint8Array.from(rows, x => BOARDS.indexOf(x.m as never)),
      BV: Float64Array.from(rows, x => x.bv), SV: Float64Array.from(rows, x => x.sv), BL: Float64Array.from(rows, x => x.bl), SL: Float64Array.from(rows, x => x.sl),
      BF: Float64Array.from(rows, x => nan(x.bf)), SF: Float64Array.from(rows, x => nan(x.sf)),
    };
    const full = without(synth(ticker, seed, BARS, START), o.drop ?? []), t = o.bars ? tailBars(full, o.bars) : full;
    const tf: TickerFlow = { first, last, rows: () => store, classification: CLASS, memo: new Map() };
    return { t: { ...t, flow: tf }, rows };
  };
  const stocks = [
    make('AAAA', 21, window), make('BBBB', 22, window, { drop: [last] }), make('CCCC', 23, window.slice(30)),
    make('DDDD', 24, window, { bars: 100 }), make('EEEE', 25, []),
  ];
  return { window, first, last, flow, stocks, E: CALENDAR[BARS - 1] };
}
type Market = ReturnType<typeof market>;

/** The Terminal's series of one stock on its bars (null outside the window): computeFlow on flowRows of its rows, the
    candles its price bars inside the window; and its flow bar, the last bar with broker data (-1 when none). */
function terminal(m: Market, s: Market['stocks'][number], id: string, params: Record<string, unknown>, output: string): { x: S; at: number } {
  const D = s.t.dates, lo = D.findIndex(d => d >= m.first), candles = D.filter(d => d >= m.first && d <= m.last) as string[];
  const pos = new Map(candles.map((d, k) => [d, k]));
  const rows = flowRows(s.rows as Row[], candles.length, d => pos.get(d) ?? -1);
  const num = (v: unknown) => isN(v) ? v : null;
  const ctx = { rows, dates: candles, close: candles.map((_, k) => num(s.t.bars.C[lo + k])), volume: candles.map((_, k) => num(s.t.bars.V[lo + k])), insider: [], classification: CLASS };
  const v = computeFlow(id, ctx, { ...flowDefaults(id), ...params })[output] as S, x: S = new Array(D.length).fill(null);
  v.forEach((y, k) => { x[lo + k] = y });
  let at = -1;
  for (let k = candles.length - 1; k >= 0; k--) if (rows.has[k]) { at = lo + k; break }
  return { x, at };
}

/* brute force, written from OPERATORS.md (sessions are the stock's own bars) */
type Outcome = { status: 'pass' | 'fail' | 'na'; value?: number | null };
const valueTest = (x: S, at: number, ok: (v: number) => boolean): Outcome => isN(x[at]) ? { status: ok(x[at] as number) ? 'pass' : 'fail', value: x[at] } : { status: 'na' };
const crossAbove = (x: S, at: number, within: number, level: number): Outcome => {
  for (let s = at; s > at - within; s--) if (s >= 1 && isN(x[s]) && isN(x[s - 1]) && (x[s - 1] as number) <= level && (x[s] as number) > level) return { status: 'pass' };
  let seen = false; for (let s = 0; s <= at; s++) if (isN(x[s])) seen = true;
  return { status: seen ? 'fail' : 'na' };
};
/** operators 9 and 10: the sessions of the N ending at t where the value test passes (K of N), the run of them ending
    at t (in a row); a session without a value is not a pass and breaks the run; n/a only when all N are n/a */
const atLeast = (x: S, at: number, n: number, k: number, ok: (v: number) => boolean): Outcome => {
  let hits = 0, valued = 0;
  for (let s = at - n + 1; s <= at; s++) if (s >= 0 && isN(x[s])) { valued++; if (ok(x[s] as number)) hits++ }
  return !valued ? { status: 'na' } : { status: hits >= k ? 'pass' : 'fail', value: hits };
};
const streak = (x: S, at: number, n: number, ok: (v: number) => boolean): Outcome => {
  let run = 0, valued = 0;
  for (let s = at; s > at - n; s--) if (s >= 0 && isN(x[s])) valued++;
  for (let s = at; s > at - n && s >= 0 && isN(x[s]) && ok(x[s] as number); s--) run++;
  return !valued ? { status: 'na' } : { status: run >= n ? 'pass' : 'fail', value: run };
};
const percentile = (x: S, at: number, n: number): number | null => {
  const first = x.findIndex(isN);
  if (!isN(x[at]) || first < 0 || at - n < first) return null;
  const w = x.slice(at - n, at).filter(isN) as number[];
  return w.length ? 100 * (w.filter(v => v < (x[at] as number)).length + 0.5 * w.filter(v => v === x[at]).length) / w.length : null;
};

const F = (metric: string, params: Record<string, unknown> = {}, output?: string) => ({ kind: 'flow', metric, params, ...(output ? { output } : {}) }) as never;
const positive = (v: number) => v > 0;
const CASES: { name: string; test: Test; id: string; params: Record<string, unknown>; output: string; brute: (x: S, at: number) => Outcome }[] = [
  { name: 'a value', test: { kind: 'value', metric: F('FL24'), op: 'gt', value: 0 } as Test, id: 'FL24', params: {}, output: 'value', brute: (x, at) => valueTest(x, at, positive) },
  // the freq preset's form (FL32 crosses above a level within N), on the value measure (this fixture's transaction
  // counts are missing now and then, so its default count measure has no value), and a cross of FL24 within 10
  { name: 'FL32 crossing above 1.2 within 3', test: { kind: 'event', within: 3, signal: { lhs: F('FL32', { measure: 'value' }, 'buy'), op: 'crosses_above', rhs: { value: 1.2 } } } as Test,
    id: 'FL32', params: { measure: 'value' }, output: 'buy', brute: (x, at) => crossAbove(x, at, 3, 1.2) },
  { name: 'FL24 crossing above 0 within 10', test: { kind: 'event', within: 10, signal: { lhs: F('FL24'), op: 'crosses_above', rhs: { value: 0 } } } as Test,
    id: 'FL24', params: {}, output: 'value', brute: (x, at) => crossAbove(x, at, 10, 0) },
  { name: 'on 6 of the last 10 sessions', test: { kind: 'window', mode: 'at_least', length: 10, count: 6, test: { kind: 'value', metric: F('FL24'), op: 'gt', value: 0 } } as Test,
    id: 'FL24', params: {}, output: 'value', brute: (x, at) => atLeast(x, at, 10, 6, positive) },
  { name: '3 sessions in a row', test: { kind: 'window', mode: 'streak', length: 3, test: { kind: 'value', metric: F('FL24'), op: 'gt', value: 0 } } as Test,
    id: 'FL24', params: {}, output: 'value', brute: (x, at) => streak(x, at, 3, positive) },
  { name: 'a percentile measure over 20 sessions', test: { kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: F('FL24', { window: 5 }), args: { length: 20 } } as never, op: 'ge', value: 50 } as Test,
    id: 'FL24', params: { window: 5 }, output: 'value', brute: (x, at) => { const p = percentile(x, at, 20); return p === null ? { status: 'na' } : { status: p >= 50 ? 'pass' : 'fail', value: p } } },
];

describe('a flow condition read at the last candle with broker data, the broker data 0, 1 or 3 sessions behind the prices (QA unit B)', () => {
  const seen: Record<string, { pass: number; fail: number }> = {};
  for (const lag of [0, 1, 3]) for (const c of CASES) {
    it(`${c.name}, ${lag} session${lag === 1 ? '' : 's'} behind: every stock's cell equals the brute-force reading`, () => {
      const m = market(lag), INDEX = synth('IHSG', 2, BARS, START);
      const env = memoryEnv(m.stocks.map(s => s.t), INDEX, m.stocks.map(s => rowOf(s.t, m.E)), m.E, { flow: m.flow });
      // with a second condition every stock passes (its last close above 0), every stock matches or comes near (one of
      // two met), so each one's cell of the flow condition is in the answer
      const r = runScreen({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all',
        conditions: [{ id: 'c0', enabled: true, test: c.test }, { id: 'c1', enabled: true, test: { kind: 'value', metric: { kind: 'universe', attr: 'last' }, op: 'gt', value: 0 } as Test }] } as Definition, env, { exhaustive: true });
      expect(r.conditions[0]).toMatchObject({ source: 'flow', eval_date_basis: 'flow_date' });
      for (const s of m.stocks) {
        const T = terminal(m, s, c.id, c.params, c.output), want: Outcome = T.at < 0 ? { status: 'na' } : c.brute(T.x, T.at);
        const cell = r.rows.find(x => x.ticker === s.t.ticker)?.cells[0];
        // its cell read at its flow bar
        expect([s.t.ticker, cell?.status, cell?.eval_date ?? null]).toEqual([s.t.ticker, want.status, T.at < 0 ? null : s.t.dates[T.at]]);
        if (want.value !== undefined && want.status !== 'na') expect([s.t.ticker, cell!.value]).toEqual([s.t.ticker, round12(want.value as number)]);
        const n = seen[c.name] ??= { pass: 0, fail: 0 };
        if (want.status === 'pass') n.pass++; else if (want.status === 'fail') n.fail++;
      }
      // the flow bar is behind the last price bar by the lag, and the series' history is longer than its tail
      const a = m.stocks[0];
      expect([a.t.dates.length > 131, a.t.dates.length - 1 - terminal(m, a, 'FL24', {}, 'value').at]).toEqual([true, lag]);
    }, 60_000);
  }
  it('each case above decides both ways (some stocks pass, some fail)', () => {
    for (const c of CASES) expect([c.name, seen[c.name]?.pass > 0, seen[c.name]?.fail > 0]).toEqual([c.name, true, true]);
  });
});
