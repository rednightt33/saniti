/* The universal operators on the page (EXEC-SCREENER-FLOW-CANDLES P3; src/operators.ts, src/forms.ts, the Add a
   condition window): every measure x test the page offers on real catalog indicators builds a wire test the worker's
   own validation accepts (the page never offers what the core refuses), reads back to the same card (fromWire), and is
   one card added from the window; the page's lists follow the catalog (the rank not offered on a price level). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse } from '../../src/core/contract.ts';
import { entriesOf, type Entry } from '../../src/entries.ts';
import { cardErrors, condText, fromWire, newCard, toWire } from '../../src/forms.ts';
import { canonical, ctx, freshUniverse, S } from '../../src/state.ts';
import { OP_OPT, addItem, cardOfRule, listItems, resetRules, ruleErrors, ruleOf, setOpt, ALL } from '../../src/add-condition.ts';
import { defaultOp, measuresFor, opShort, opsFor, plainOffered, secondOptions, testsFor, withCmp, withMeasure, withTest } from '../../src/operators.ts';
import { validateTest } from '../../src/core/validate.ts';
import { vctx } from '../core/helpers.ts';
import { fixtureApi } from '../fixture/api.ts';

let catalog: CatalogResponse;
beforeAll(async () => {
  const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
});
beforeEach(() => {
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.api = { run: () => { throw new Error('the window sent a run') } } as never;
  ctx.metrics = []; S.universe = freshUniverse(); S.cards = []; S.errors = {};
  resetRules();
});
const entry = (id: string) => ctx.byKey.get(id) as Entry;
const CTX = vctx(['BBCA']);

describe('every operator the page offers is one the worker accepts, and reads back', () => {
  it('measures x tests on RSI, MACD (two lines, a second series), SMA (a price level) and OBV (a volume-type line)', () => {
    let n = 0;
    for (const id of ['I13', 'I06', 'I01', 'I40']) {
      const e = entry(id), ops = e.ops!;
      for (const out of e.indicator!.outputs) {
        for (const m of [...(plainOffered(ops, e, out.key) ? [{ fn: 'none' }] : []), ...measuresFor(ops, e, out.key)]) {
          let op = withMeasure(ops, e, defaultOp(ops, e, out.key), m.fn);
          for (const t of testsFor(ops, e, op)) {
            op = withTest(ops, e, op, t.key);
            for (const cmp of opsFor(e, op, t)) {
              const o = { ...op, cmp, value: 1, value2: cmp === 'between' || cmp === 'outside' ? 2 : '' as const };
              const c = newCard(e, [], { op: o });
              expect(cardErrors(e, c)).toEqual({});
              const w = toWire(e, c);
              expect(() => validateTest(w.test, `${id}.${out.key}.${m.fn}.${t.key}.${cmp}`, CTX)).not.toThrow();
              const back = fromWire(w, ctx.byKey);
              if (back.op) expect(canonical(toWire(e, back).test)).toBe(canonical(w.test));
              n++;
            }
          }
        }
      }
    }
    expect(n).toBeGreaterThan(400);
  });
  it('the rank is not offered on a price level (SMA) but on its percent distance from its own average', () => {
    const e = entry('I01'), ops = e.ops!, op = defaultOp(ops, e, 'sma');
    expect(testsFor(ops, e, { ...op, measure: 'none' }).map(t => t.key)).not.toContain('rank');
    expect(testsFor(ops, e, withMeasure(ops, e, op, 'vs_average')).map(t => t.key)).toContain('rank');               // percent by default
    expect(testsFor(ops, e, { ...withMeasure(ops, e, op, 'vs_average'), margs: { ma: 'SMA', length: 20, form: 'difference' } }).map(t => t.key)).not.toContain('rank');
  });
  it('a second series of the same unit only: MACD against its signal or histogram; RSI has none', () => {
    expect(secondOptions(entry('I06'), 'macd').map(s => s.key)).toEqual(expect.arrayContaining(['out:signal']));
    expect(secondOptions(entry('I13'), 'rsi')).toEqual([]);
    expect(measuresFor(entry('I13').ops!, entry('I13'), 'rsi').map(m => m.fn)).not.toContain('relative');
    expect(secondOptions(entry('I01'), 'sma').map(s => s.key)).toEqual(['price:close', 'price:open', 'price:high', 'price:low']);
  });
});

describe('the Add a condition window', () => {
  it('"Operator…" puts the row on the operator; its card is added with the wire test and its words', () => {
    const e = entry('I13');
    setOpt(e, OP_OPT);
    const r = ruleOf(e);
    expect(r.op).toMatchObject({ output: 'rsi', measure: 'percentile', margs: { length: 60 }, test: 'value', cmp: 'ge', value: 90 });
    expect(ruleErrors(e)).toEqual({});
    expect(addItem(listItems('relative strength', ALL, 'group').find(it => it.key === 'I13')!).ok).toBe(true);
    const c = S.cards[0];
    expect(toWire(e, c).test).toEqual({ kind: 'value', op: 'ge', value: 90, metric: { kind: 'transform', fn: 'percentile', of: { kind: 'indicator', indicator: 'I13', output: 'rsi' }, args: { length: 60 } } });
    expect(condText(e, c)).toBe('Relative Strength Index (14, close): Percentile of its own history, 60 sessions ≥ 90');
    setOpt(e, e.def.opt);                                            // back to a plain condition: the operator is gone
    expect(ruleOf(e).op).toBeUndefined();
    expect(cardOfRule(e).op).toBeUndefined();
  });
  it('a check refuses in place, never rounds: N above its range, K above N, a range the wrong way round', () => {
    const e = entry('I13'), ops = e.ops!;
    setOpt(e, OP_OPT);
    const r = ruleOf(e);
    r.op = { ...r.op!, margs: { length: 300 } };
    expect(ruleErrors(e)['o.a.length']).toMatch(/at most 260/);
    r.op = { ...withTest(ops, e, { ...r.op, margs: { length: 60 } }, 'at_least'), n: 5, k: 6 };
    expect(ruleErrors(e)['o.k']).toMatch(/right: 3 of 5; wrong: 6 of 5/);
    r.op = { ...withTest(ops, e, r.op, 'range'), cmp: 'between', value: 80, value2: 20 };
    expect(ruleErrors(e)['o.value2']).toMatch(/right: 2 to 8; wrong: 8 to 2/);
  });
});

describe('QA5 round 1 fixes (2026-11-07)', () => {
  it('D3: a test opens with thresholds that suit the measure, never a value of another measure or test', () => {
    const e = entry('I13'), ops = e.ops!, base = defaultOp(ops, e);
    // a range: the measure's own range, blank for a difference (no scale-free range), the entry's own bounds on the plain series
    expect(withTest(ops, e, withMeasure(ops, e, base, 'change_pct'), 'range')).toMatchObject({ cmp: 'between', value: -5, value2: 5 });
    expect(withTest(ops, e, withMeasure(ops, e, base, 'zscore'), 'range')).toMatchObject({ value: -1, value2: 1 });
    expect(withTest(ops, e, withMeasure(ops, e, base, 'change'), 'range')).toMatchObject({ value: '', value2: '' });
    // switching back to a single value takes the measure's default, not the range's lower bound
    const r = withTest(ops, e, withMeasure(ops, e, base, 'zscore'), 'range');
    expect(withCmp(ops, e, r, 'ge')).toMatchObject({ cmp: 'ge', value: 2, value2: '' });
    // the plain series opens with the entry's own default, not the percentile's 90 (Volume SMA "above 90" matched everything)
    const v = entry('I13');
    expect(withMeasure(ops, v, base, 'none')).toMatchObject({ measure: 'none', value: v.def.value });
    // a rank keeps its own 0-100 threshold
    expect(withTest(ops, e, withMeasure(ops, e, base, 'zscore'), 'rank')).toMatchObject({ cmp: 'ge', value: 90 });
  });
  it('D2: an operator names itself in a column header', () => {
    const e = entry('I13'), ops = e.ops!, base = defaultOp(ops, e);
    expect(opShort(ops, base)).toBe('pctl · ≥90');
    expect(opShort(ops, { ...withTest(ops, e, base, 'at_least'), n: 5, k: 3 })).toBe('pctl · 3 of 5 · ≥90');
    expect(opShort(ops, withTest(ops, e, withMeasure(ops, e, base, 'none'), 'rank'))).toBe('rank · ≥90');
    // a rank range opens on 0-100 whatever the measure (a change has no range of its own)
    const rk = withTest(ops, e, withMeasure(ops, e, base, 'change'), 'rank');
    expect(withCmp(ops, e, rk, 'between')).toMatchObject({ value: 80, value2: 100 });
  });
});
