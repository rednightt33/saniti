/* VALUE, STATE and EVENT at the evaluation bar (report TARGET ARCHITECTURE 6.9; TEST PLAN 10b.3 "Condition parity",
   "between", "within boundaries", "Edge bars", "State ≠ event", "NA reason codes", 10b.4 "Missing sessions",
   "Price breaks"; 10b.2 "Tail evaluation equals full evaluation"):
   - gt, lt and both crosses equal the backtest core's conditionSeries[at] on 200 synthetic tickers for registry
     conditions, every output pair of the 8 pair indicators included, and the Donchian prior-band state equals core
     breakout at every bar;
   - between is inclusive at both ends (negative ranges too); value = value2 accepted;
   - within N: an event N-1 bars ago passes, N bars ago fails; event_date, bars_ago, last_event_date exact; N = 1 and N =
     within_max; a state true for 10 bars with no cross fails the event;
   - NA only with a reason, and the reasons are the ticker's: INSUFFICIENT_HISTORY (74 bars), NULL_AT_EVALUATION (zero band
     width, a missing input such as IHSG volume);
   - market_sessions_ago counts the IHSG calendar, bars_ago the ticker's bars, across missing sessions;
   - the PRICE_BREAK_IN_LOOKBACK remark marks exactly the cells whose lookback crosses an ex-date. */
import { describe, expect, it } from 'vitest';
import { Calc, conditionSeries } from '../../../backtest/src/core/conditions.ts';
import { F } from '../../../terminal/src/calc/indicators.ts';
import { INDICATORS } from '../../src/core/registry.ts';
import {
  evaluateEvent, evaluateState, evaluateStatePattern, evaluateValue, lookbackStart, priceBreakRemark, sessionsBetween, toCell,
  viewOfSeries, viewOfTail, crossSignal,
} from '../../src/core/evaluate.ts';
import { bindCondition } from '../../src/core/condition.ts';
import type { TickerInput } from '../../src/core/condition.ts';
import { SeriesCache, series, tailLength, tailOf, tickerCalc } from '../../src/core/metrics.ts';
import type { TickerBars } from '../../src/core/metrics.ts';
import type { ConditionDef, UniverseRow } from '../../src/core/contract.ts';
import { OPTS, WITHIN_MAX, headBars, rowOf, synth, tailBars } from './helpers.ts';

const V = (xs: (number | null)[]) => viewOfSeries(xs);

describe('VALUE', () => {
  it('gt and lt are strict; between is inclusive at both ends, also for negative ranges; value = value2 is accepted', () => {
    const v = V([1, 5]);
    expect([evaluateValue(v, { op: 'gt', value: 5 }, 1).status, evaluateValue(v, { op: 'lt', value: 5 }, 1).status, evaluateValue(v, { op: 'gt', value: 4.999 }, 1).status]).toEqual(['fail', 'fail', 'pass']);
    expect(['between', 'between', 'between'].map((op, k) => evaluateValue(v, { op: op as 'between', value: [5, 1, 5.0001][k], value2: [9, 5, 9][k] }, 1).status)).toEqual(['pass', 'pass', 'fail']);
    expect(evaluateValue(V([0, -5]), { op: 'between', value: -5, value2: -1 }, 1).status).toBe('pass');
    expect(evaluateValue(V([0, -5]), { op: 'between', value: -5, value2: -5 }, 1)).toEqual({ status: 'pass', reason: null, value: -5 });
  });
  it('is NA with the reason when there is no value at the bar', () => {
    expect(evaluateValue(V([null, null]), { op: 'gt', value: 0 }, 1)).toEqual({ status: 'na', reason: 'INSUFFICIENT_HISTORY', value: null });
    expect(evaluateValue(V([3, null]), { op: 'gt', value: 0 }, 1)).toEqual({ status: 'na', reason: 'NULL_AT_EVALUATION', value: null });
  });
});

describe('STATE', () => {
  it('is compare(lhs, op, rhs)[at] with the core rules; NA names the missing side (lhs first)', () => {
    expect(evaluateState(V([1, 3]), 'gt', V([2, 2]), 1)).toEqual({ status: 'pass', reason: null, lhs: 3, rhs: 2 });
    expect(evaluateState(V([1, 3]), 'gt', 4, 1)).toEqual({ status: 'fail', reason: null, lhs: 3, rhs: 4 });
    expect(evaluateState(V([3]), 'gt', 1, 0).status).toBe('fail');                                   // bar 0 is never true
    expect(evaluateState(V([1, null]), 'gt', V([null, null]), 1)).toEqual({ status: 'na', reason: 'NULL_AT_EVALUATION', lhs: null, rhs: null });
    expect(evaluateState(V([1, 2]), 'lt', V([null, null]), 1)).toEqual({ status: 'na', reason: 'INSUFFICIENT_HISTORY', lhs: 2, rhs: null });
    expect(evaluateStatePattern([0, 1, 0], 1).status).toBe('pass');
    expect(evaluateStatePattern(viewOfTail(tailOf([0, 0, 1], 2)), 2).status).toBe('pass');
  });
  it('a ticker whose first valid bar is the evaluation bar has a state (gt needs one bar), but no event can have happened', () => {
    const a = V([null, null, 5]), b = V([null, null, 4]);
    expect(evaluateState(a, 'gt', b, 2).status).toBe('pass');
    expect(evaluateEvent(crossSignal(a, 'crosses_above', b), 3, WITHIN_MAX, 2, { lhs: a, rhs: b }).status).toBe('fail');
  });
});

describe('EVENT', () => {
  const sig = (bars: number[], n: number) => (i: number) => bars.includes(i) && i < n;
  it('within N: an event N-1 bars ago passes, N bars ago fails; dates and bars_ago exact; last event within within_max', () => {
    const at = 200;
    for (const N of [1, 5, 20, WITHIN_MAX]) {
      const pass = evaluateEvent(sig([at - N + 1], at + 1), N, WITHIN_MAX, at);
      expect([pass.status, pass.eventBar, pass.barsAgo, pass.lastEventBar]).toEqual(['pass', at - N + 1, N - 1, at - N + 1]);
      const fail = evaluateEvent(sig([at - N], at + 1), N, WITHIN_MAX, at);
      expect([fail.status, fail.eventBar, fail.barsAgo, fail.lastEventBar]).toEqual(['fail', null, null, N < WITHIN_MAX ? at - N : null]);
    }
    expect(evaluateEvent(sig([195, 199], 201), 5, WITHIN_MAX, 200).eventBar).toBe(199);              // the latest event
    expect(() => evaluateEvent(sig([], 10), WITHIN_MAX + 1, WITHIN_MAX, 9)).toThrow(RangeError);   // validate.ts refuses it first
  });
  it('a state true for 10 bars with no cross inside N fails the event (an event is never reduced to a state)', () => {
    const a = V([...Array(20).fill(1), ...Array(10).fill(5)]), b = V(Array(30).fill(3));            // crossed at bar 20
    expect(evaluateState(a, 'gt', b, 29).status).toBe('pass');
    const e = evaluateEvent(crossSignal(a, 'crosses_above', b), 5, WITHIN_MAX, 29, { lhs: a, rhs: b });
    expect([e.status, e.lastEventBar, e.lhs, e.rhs]).toEqual(['fail', 20, 5, 3]);
    expect(evaluateEvent(crossSignal(a, 'crosses_above', b), 10, WITHIN_MAX, 29).status).toBe('pass');
  });
  it('is NA only when a side could never have crossed: no value up to the bar, or a missing input', () => {
    const none = V([null, null, null]), some = V([1, 2, 3]);
    expect(evaluateEvent(crossSignal(some, 'crosses_above', none), 3, WITHIN_MAX, 2, { lhs: some, rhs: none })).toMatchObject({ status: 'na', reason: 'INSUFFICIENT_HISTORY' });
    const missing = viewOfSeries([null, null, null], true);
    expect(evaluateEvent(crossSignal(some, 'crosses_above', missing), 3, WITHIN_MAX, 2, { lhs: some, rhs: missing })).toMatchObject({ status: 'na', reason: 'NULL_AT_EVALUATION' });
    const gap = V([1, 5, null]);                                                                   // a value earlier: a cross could have been seen
    expect(evaluateEvent(crossSignal(gap, 'crosses_above', 3), 2, WITHIN_MAX, 2, { lhs: gap, rhs: 3 })).toMatchObject({ status: 'pass', eventBar: 1, lhs: null, rhs: 3 });
  });
});

describe('remarks and the wire cell', () => {
  const dates = ['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08', '2026-10-09', '2026-10-12', '2026-10-13', '2026-10-14', '2026-10-15'];
  it('a window-class lookback contains the ex-date only while the window holds it; recursive ones always after it', () => {
    const at = 10, ex = ['2026-10-07'];                                                           // bar 4
    expect(priceBreakRemark([lookbackStart('window', 4, at)], dates, at, ex)).toBe(null);          // 5-bar window [6, 10]
    expect(priceBreakRemark([lookbackStart('window', 6, at)], dates, at, ex)).toBe(null);          // [4, 10]: every bar on or after it, no mix
    expect(priceBreakRemark([lookbackStart('window', 7, at)], dates, at, ex)).toBe('PRICE_BREAK_IN_LOOKBACK');   // [3, 10]
    expect(priceBreakRemark([lookbackStart('recursive', 0, at)], dates, at, ex)).toBe('PRICE_BREAK_IN_LOOKBACK');
    expect(priceBreakRemark([lookbackStart(null, 0, at)], dates, at, ex)).toBe(null);               // a bar field reads one bar
    expect(priceBreakRemark([lookbackStart(null, 0, at, 6)], dates, at, ex)).toBe(null);            // an event within 6 reads [4, 10]
    expect(priceBreakRemark([lookbackStart(null, 0, at, 7)], dates, at, ex)).toBe('PRICE_BREAK_IN_LOOKBACK');   // within 7 reads bar 3 too
    expect(priceBreakRemark([null], dates, at, ['2026-10-16'])).toBe(null);                        // after the last bar
    expect(priceBreakRemark([null], dates, at, ['2026-10-03'])).toBe('PRICE_BREAK_IN_LOOKBACK');    // a non-session ex-date: the next bar
    expect(priceBreakRemark([], dates, at, ex)).toBe(null);                                          // universe attributes and flow
  });
  it('an EVENT cell counts bars_ago on the ticker\'s bars and market_sessions_ago on the IHSG calendar, across missing sessions', () => {
    const own = ['2026-09-15', '2026-09-16', '2026-09-19', '2026-09-22'];                           // 09-17/18 missing for the stock
    const ihsg = ['2026-09-15', '2026-09-16', '2026-09-17', '2026-09-18', '2026-09-19', '2026-09-22'];
    const c = toCell('c', { status: 'pass', reason: null, lhs: 1 / 3, rhs: 2, eventBar: 1, barsAgo: 2, lastEventBar: 1 }, { dates: own, at: 3, ihsgCalendar: ihsg, unit: 'price', remark: null });
    expect(c).toEqual({ id: 'c', status: 'pass', eval_date: '2026-09-22', unit: 'price', reason: null, remark: null, lhs: 0.333333333333, rhs: 2,
      event_date: '2026-09-16', bars_ago: 2, market_sessions_ago: 4, last_event_date: '2026-09-16' });
    expect(sessionsBetween(ihsg, '2026-09-22', '2026-09-22')).toBe(0);
    const na = toCell('a', { status: 'na', reason: 'INSUFFICIENT_HISTORY', value: null }, { dates: own, at: 3, ihsgCalendar: ihsg, unit: null, remark: null });
    expect(na).toEqual({ id: 'a', status: 'na', eval_date: '2026-09-22', unit: null, reason: 'INSUFFICIENT_HISTORY', remark: null, value: null });
    const fail = toCell('e', { status: 'fail', reason: null, eventBar: null, barsAgo: null, lastEventBar: null }, { dates: own, at: 3, ihsgCalendar: ihsg, unit: null, remark: null });
    expect([fail.event_date, fail.bars_ago, fail.market_sessions_ago, fail.last_event_date]).toEqual([null, null, null, null]);
  });
});

/* ---- parity with the Backtest on synthetic tickers, through the condition binding --------------------------------- */
const E = '2026-12-31';
const TICKERS = Array.from({ length: 200 }, (_, k) => synth(`T${k}`, 1000 + k, 300 + (k % 7) * 40));
const IX = { ...synth('IHSG', 9, 700, '2023-06-01') };
function inputFor(t: TickerBars, cache = new SeriesCache(1 << 28), row?: UniverseRow): TickerInput {
  const c = tickerCalc(t), ctx = { versions: { price_data: 'p', screener_engine: 'e' }, tailLength: tailLength(WITHIN_MAX), cache };
  return { ticker: t.ticker, dates: t.dates, bars: t.bars, at: t.dates.length - 1, row: row ?? rowOf(t, E), ihsgCalendar: IX.dates, series: r => series(ctx, c, r), xsection: () => null };
}
const ind = (indicator: string, output: string, params?: Record<string, unknown>) => ({ kind: 'indicator' as const, indicator, output, ...(params ? { params } : {}) });
const cond = (test: any): ConditionDef => ({ id: 'c', enabled: true, test });

describe('parity with the backtest core (conditionSeries[at]) on 200 tickers', () => {
  // the registry conditions the Backtest has: an output vs a value, a price vs an output, two outputs of one instance
  const cases: { core: any; test: (op: string) => any }[] = [
    { core: { indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, rhs: { type: 'value', value: 50 } }, test: op => op.startsWith('cross') ? { kind: 'event', within: 1, signal: { lhs: ind('I13', 'rsi'), op, rhs: { value: 50 } } } : { kind: 'state', lhs: ind('I13', 'rsi'), op, rhs: { value: 50 } } },
    { core: { indicator: 'I01', params: { length: 30 }, lhs: { type: 'price' }, rhs: { type: 'output', output: 'sma' } }, test: op => op.startsWith('cross') ? { kind: 'event', within: 1, signal: { lhs: { kind: 'price', field: 'close' }, op, rhs: ind('I01', 'sma', { length: 30 }) } } : { kind: 'state', lhs: { kind: 'price', field: 'close' }, op, rhs: ind('I01', 'sma', { length: 30 }) } },
  ];
  // every output pair of the 8 "pair" indicators (report 6.9.1), state and cross
  for (const r of INDICATORS.filter(x => x.overlay.shape === 'pair')) {
    const [a, b] = r.outputs.map(o => o.key);
    cases.push({ core: { indicator: r.id, params: {}, lhs: { type: 'output', output: a }, rhs: { type: 'output', output: b } },
      test: op => op.startsWith('cross') ? { kind: 'event', within: 1, signal: { lhs: ind(r.id, a), op, rhs: ind(r.id, b) } } : { kind: 'state', lhs: ind(r.id, a), op, rhs: ind(r.id, b) } });
  }
  it('gt, lt, crosses_above and crosses_below at the evaluation bar equal the Backtest\'s, cell for cell', () => {
    let checked = 0, passes = 0;
    for (const c of cases) for (const op of ['gt', 'lt', 'crosses_above', 'crosses_below']) {
      const b = bindCondition(cond(c.test(op)), 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX });
      for (const t of TICKERS) {
        const calc = new Calc(t.bars), at = t.dates.length - 1;
        let want: number | null;
        try { want = conditionSeries(calc, { id: 'x', kind: 'indicator', op, ...c.core } as any, 'c')[at] } catch { want = null }   // INDICATOR_OUTPUT_EMPTY: NA here
        const got = b.evaluate(inputFor(t)).cell;
        if (want === null) expect(got.status).toBe('na');
        else expect([t.ticker, op, got.status === 'pass' ? 1 : 0]).toEqual([t.ticker, op, want]);
        checked++; passes += got.status === 'pass' ? 1 : 0;
      }
    }
    expect(checked).toBe(cases.length * 4 * 200);
    expect(passes).toBeGreaterThan(checked / 10);
  }, 120_000);   // about 4.7 s alone, near vitest's 5 s default: a heavy test's own timeout, as oracle.test.ts
  it('Donchian: close above the upper band reads the prior band (lag probe), so the state equals core breakout at every bar', () => {
    const t = synth('DON', 77, 600), calc = new Calc(t.bars), core = conditionSeries(calc, { id: 'x', kind: 'price_action', type: 'breakout', params: { length: 20 } } as any, 'c');
    const b = bindCondition(cond({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: ind('I10', 'upper') }), 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX });
    expect(b.series.map(s => s.label)).toEqual(['close', 'lag(I10.upper, 1)']);
    for (let n = 40; n <= 600; n += 7) expect([n, b.evaluate(inputFor(headBars(t, n))).cell.status === 'pass' ? 1 : 0]).toEqual([n, core[n - 1]]);
    const same = F.donchian(t.bars, {}).upper;                                                    // the same-bar form never passes
    expect(t.bars.C.some((c, i) => typeof same[i] === 'number' && c > (same[i] as number))).toBe(false);
  });
});

describe('NA reasons are the ticker\'s', () => {
  it('74 bars: SMA(200) INSUFFICIENT_HISTORY; a zero-width band: band position NULL_AT_EVALUATION; IHSG volume: NULL_AT_EVALUATION', () => {
    const rans = tailBars(synth('RANS', 5, 400), 74);
    const sma200 = bindCondition(cond({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: ind('I01', 'sma', { length: 200 }) }), 'd', { ...OPTS, withinMax: WITHIN_MAX });
    expect(sma200.evaluate(inputFor(rans)).cell).toMatchObject({ status: 'na', reason: 'INSUFFICIENT_HISTORY', lhs: Number((rans.bars.C[73] as number).toPrecision(12)), rhs: null });
    const flat = synth('BNBR', 6, 300), n = flat.dates.length, C = Array.from(flat.bars.C) as number[];
    for (let i = n - 25; i < n; i++) C[i] = 50;                                                      // a flat window: zero width
    const flatT = { ...flat, bars: { ...flat.bars, O: C, H: C, L: C, C } };
    const pos = bindCondition(cond({ kind: 'value', op: 'gt', value: 50, metric: { kind: 'transform', fn: 'band_position', of: ind('I27', 'basis') } }), 'd', { ...OPTS, withinMax: WITHIN_MAX });
    expect(pos.evaluate(inputFor(flatT)).cell).toMatchObject({ status: 'na', reason: 'NULL_AT_EVALUATION', value: null });
    const ihsg = { ...IX, bars: { ...IX.bars, V: IX.bars.V.map(() => null) } };
    const vwma = bindCondition(cond({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: ind('I27', 'basis', { basis_ma_type: 'VWMA' }) }), 'd', { ...OPTS, withinMax: WITHIN_MAX });
    const smaBasis = bindCondition(cond({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: ind('I27', 'basis') }), 'd', { ...OPTS, withinMax: WITHIN_MAX });
    expect(vwma.evaluate(inputFor(ihsg)).cell).toMatchObject({ status: 'na', reason: 'NULL_AT_EVALUATION' });
    expect(smaBasis.evaluate(inputFor(ihsg)).cell.status).not.toBe('na');
  });
});

describe('tail evaluation equals full evaluation (report 6.7)', () => {
  it('for every bar of the within_max + 1 tail, VALUE, STATE and EVENT on the tail equal the same test on the full series', () => {
    const t = synth('TAIL', 31, 500), at = t.dates.length - 1;
    const rsi = F.rsi(t.bars, {}).rsi, sma = F.sma(t.bars, { length: 50 }).sma, C = t.bars.C as number[];
    const tRsi = viewOfTail(tailOf(rsi, tailLength(WITHIN_MAX))), tSma = viewOfTail(tailOf(sma, tailLength(WITHIN_MAX))), tC = viewOfTail(tailOf(C, tailLength(WITHIN_MAX)));
    const fRsi = viewOfSeries(rsi), fSma = viewOfSeries(sma), fC = viewOfSeries(C);
    for (let i = at - WITHIN_MAX + 1; i <= at; i++) {
      expect(evaluateValue(tRsi, { op: 'lt', value: 45 }, i)).toEqual(evaluateValue(fRsi, { op: 'lt', value: 45 }, i));
      expect(evaluateState(tC, 'gt', tSma, i)).toEqual(evaluateState(fC, 'gt', fSma, i));
    }
    for (const N of [1, 17, WITHIN_MAX]) expect(evaluateEvent(crossSignal(tC, 'crosses_above', tSma), N, WITHIN_MAX, at, { lhs: tC, rhs: tSma }))
      .toEqual(evaluateEvent(crossSignal(fC, 'crosses_above', fSma), N, WITHIN_MAX, at, { lhs: fC, rhs: fSma }));
  });
});

describe('price-break cell remarks through the binding (P4.1 A: values shown, cells marked)', () => {
  it('a window-class cell is marked while its window holds the ex-date, a recursive one always, a universe attribute never', () => {
    const t = synth('PBSA', 13, 300), ex = t.dates[t.dates.length - 10];                            // 9 bars before the last
    const row = rowOf(t, E, {}, [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: ex, ratio_old: 1, ratio_new: 2, close_ratio: 0.45 }]);
    const run = (test: any) => bindCondition(cond(test), 'd', { ...OPTS, withinMax: WITHIN_MAX }).evaluate(inputFor(t, undefined, row)).cell;
    const sma = (length: number) => run({ kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: ind('I01', 'sma', { length }) });
    // the ex-date is bar at - 9: SMA(10) reads [at - 9, at], all after it; SMA(11) reads bar at - 10 too, mixing both sides
    expect([sma(5).remark, sma(10).remark, sma(11).remark, sma(20).remark]).toEqual([null, null, 'PRICE_BREAK_IN_LOOKBACK', 'PRICE_BREAK_IN_LOOKBACK']);
    expect(run({ kind: 'value', op: 'gt', value: 0, metric: ind('I13', 'rsi') }).remark).toBe('PRICE_BREAK_IN_LOOKBACK');   // recursive
    const value = sma(20);
    expect(typeof value.rhs).toBe('number');                                                        // shown, not blanked
    expect(run({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'universe', attr: 'adv20_idr' } }).remark).toBe(null);
    const ev = run({ kind: 'event', within: 3, signal: { lhs: { kind: 'price', field: 'close' }, op: 'crosses_above', rhs: ind('I01', 'sma', { length: 5 }) } });
    expect(ev.remark).toBe(null);                                                                   // [at-3-4, at] = [at-7, at]: after at-9
    const ev2 = run({ kind: 'event', within: 6, signal: { lhs: { kind: 'price', field: 'close' }, op: 'crosses_above', rhs: ind('I01', 'sma', { length: 5 }) } });
    expect(ev2.remark).toBe('PRICE_BREAK_IN_LOOKBACK');                                            // [at-10, at] mixes both sides
    const plain = bindCondition(cond({ kind: 'value', op: 'gt', value: 0, metric: ind('I13', 'rsi') }), 'd', { ...OPTS, withinMax: WITHIN_MAX }).evaluate(inputFor(t)).cell;
    expect(plain.remark).toBe(null);                                                               // no PRICE_BREAK row remark
  });
});

describe('NOT_APPLICABLE (report 6.9, 6.12: bank metrics outside Banks)', () => {
  it('a metric whose applies_to excludes the ticker is NA NOT_APPLICABLE; inside its scope the value is tested', () => {
    // the binding does not decide availability (validate.ts refuses npl today: no data); here the row carries a value
    const b = bindCondition(cond({ kind: 'value', op: 'lt', value: 3, metric: { kind: 'universe', attr: 'npl' } }), 'd', { ...OPTS, withinMax: WITHIN_MAX });
    const t = synth('BANK', 21, 120), bank = { ...rowOf(t, E, { sector: 'Financials', industry: 'Banks' }), npl: 2.1 } as UniverseRow;
    const coal = { ...rowOf(t, E, { sector: 'Energy', industry: 'Coal' }), npl: 2.1 } as UniverseRow;
    expect(b.evaluate(inputFor(t, undefined, bank)).cell).toMatchObject({ status: 'pass', value: 2.1, reason: null, remark: null });
    expect(b.evaluate(inputFor(t, undefined, coal)).cell).toMatchObject({ status: 'na', reason: 'NOT_APPLICABLE', value: null });
  });
});
