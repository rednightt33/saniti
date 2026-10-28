/* The evaluate.ts primitives the evaluators build on (report TARGET ARCHITECTURE 6.9; TEST PLAN 10b.3 "Edge bars"):
   compareAt equals the backtest core's compare at every bar (it is compare itself over two bars), on full series and
   on tails; bar 0 is never true; NaN is false; a cross needs the bar before; naReason tells INSUFFICIENT_HISTORY from
   NULL_AT_EVALUATION; evaluationBar finds the ticker's own last bar on or before E. */
import { describe, expect, it } from 'vitest';
import { compare } from '../../../backtest/src/core/conditions.ts';
import { F } from '../../../terminal/src/calc/indicators.ts';
import * as G from '../../scripts/build-screener-registry.mjs';
import { compareAt, crossSignal, evaluationBar, naReason, round12, viewOfSeries, viewOfTail } from '../../src/core/evaluate.ts';
import { tailOf } from '../../src/core/metrics.ts';

const B = G.fixture({ bars: 600 });

describe('compareAt', () => {
  it('equals core compare on every bar for gt, lt and both crosses, on the full series and on a 131-bar tail', () => {
    const close = B.C as number[], sma = F.sma(B, { length: 20 }).sma, ema = F.ema(B, { length: 50 }).ema;
    for (const op of ['gt', 'lt', 'crosses_above', 'crosses_below'] as const) {
      const ref = compare(close, op, sma, 0, close.length), ref2 = compare(sma, op, ema, 0, close.length), refV = compare(sma, op, null, 1000, close.length);
      const full = [viewOfSeries(close), viewOfSeries(sma), viewOfSeries(ema)];
      const tail = [viewOfTail(tailOf(close, 131)), viewOfTail(tailOf(sma, 131)), viewOfTail(tailOf(ema, 131))];
      for (let i = 0; i < close.length; i++) {
        expect(compareAt(full[0], op, full[1], i)).toBe(ref[i] === 1);
        expect(compareAt(full[1], op, full[2], i)).toBe(ref2[i] === 1);
        expect(compareAt(full[1], op, 1000, i)).toBe(refV[i] === 1);
        if (i >= close.length - 130) expect(compareAt(tail[0], op, tail[1], i)).toBe(ref[i] === 1);
      }
    }
  });
  it('bar 0 is never true, NaN is false, and a cross needs both sides on the bar before', () => {
    const a = viewOfSeries([5, 5, null, 5, 7]), b = viewOfSeries([1, 6, 6, 6, 6]);
    expect(compareAt(a, 'gt', b, 0)).toBe(false);                                     // 5 > 1 but bar 0
    expect(compareAt(a, 'gt', b, 2)).toBe(false);                                     // NaN
    expect(compareAt(a, 'crosses_above', b, 3)).toBe(false);                          // bar 2 missing on a
    expect(crossSignal(a, 'crosses_above', b)(4)).toBe(true);                         // 5 <= 6 then 7 > 6
  });
});

describe('naReason, evaluationBar, round12', () => {
  it('INSUFFICIENT_HISTORY without any value up to the bar, NULL_AT_EVALUATION with earlier values, null with a value', () => {
    const v = viewOfSeries([null, null, 3, null]);
    expect([naReason(v, 1), naReason(v, 2), naReason(v, 3)]).toEqual(['INSUFFICIENT_HISTORY', null, 'NULL_AT_EVALUATION']);
    expect(naReason(viewOfSeries([null, null]), 1)).toBe('INSUFFICIENT_HISTORY');
  });
  it('a series whose input the ticker lacks is NULL_AT_EVALUATION, never INSUFFICIENT_HISTORY (TEST PLAN 10b.3 IHSG volume)', () => {
    expect(naReason(viewOfSeries([null, null, null], true), 2)).toBe('NULL_AT_EVALUATION');
    expect(naReason(viewOfTail(tailOf([null, null, null], 131), true), 2)).toBe('NULL_AT_EVALUATION');
    expect(naReason(viewOfSeries([null, 4], true), 1)).toBe(null);                  // a value is a value
  });
  it('the evaluation bar is the ticker\'s last bar on or before E (a stale ticker: its own last bar)', () => {
    const dates = ['2026-08-20', '2026-08-21'];
    expect([evaluationBar(dates, '2026-10-27'), evaluationBar(dates, '2026-08-21'), evaluationBar(dates, '2026-08-01')]).toEqual([1, 1, -1]);
  });
  it('wire numbers are rounded to 12 significant digits and never NaN', () => {
    expect([round12(1 / 3), round12(NaN), round12(Infinity), round12(null), round12(1234.5)]).toEqual([0.333333333333, null, null, null, 1234.5]);
  });
});
