/* QA unit C (P6): the refusal of a reference that is not a series (metrics.ts notSeriesRefusal), and the refusal of a
   window's count (condition.ts countRefusal). AGENTS.md "Gates and evidence": each names where the problem is (the field
   of the reference itself, never "<field>.kind"), why (what the reference is), how to pass in the test form it occurs
   in (a condition, a window's inner test, a universe filter), and one right and one wrong example; the right example is
   a definition the core accepts, the wrong one the shape it refused. The class, not the instance: every kind that is not
   a series (a pattern, a cross-sectional value, a universe attribute, a rank), at every place a series is needed (each
   transform of the catalog as the series and as the second series, a rank, both sides of a state test, an event, a
   value test, a window, a universe filter), through validation and through a binding of an unchecked test. */
import { describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import type { MetricRef } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { bindTest } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { NOT_SERIES_KINDS, notSeriesRefusal } from '../../src/core/metrics.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { OPTS, WITHIN_MAX, vctx } from './helpers.ts';

const CTX = vctx(['A']);
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null };
const refusal = (fn: () => unknown): ScreenerError => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e } throw new Error('expected a ScreenerError') };
const asCondition = (test: unknown) => ({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] });
const asFilter = (test: unknown) => ({ universe: { ...U, metric_filters: [test] }, logic: 'all', conditions: [] });
const refuse = (test: unknown, filter = false) => refusal(() => validateDefinition((filter ? asFilter(test) : asCondition(test)) as never, CTX));
const accepts = (test: unknown) => expect(() => validateDefinition(asCondition(test) as never, CTX)).not.toThrow();
const T = 'definition.conditions[0].test';

const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' };
const close = { kind: 'price', field: 'close' };
const pattern = (type: string) => ({ kind: 'pattern', type });
/** one available reference of each kind that is not a series: a candlestick pattern, an older pattern, the cross-sectional
    RS rank, a universe attribute and a rank among the screened stocks */
const NOT_SERIES: Record<string, MetricRef> = {
  candle: pattern('hammer') as MetricRef, older: pattern('breakout') as MetricRef, xsection: { kind: 'xsection', metric: 'return_rank' } as MetricRef,
  universe: { kind: 'universe', attr: 'chg_1d_pct' } as MetricRef, rank: { kind: 'rank', of: rsi } as MetricRef,
};
const labelOf = (fn: string) => METRICS_CATALOG.operators.measures.find(m => m.fn === fn)?.label ?? METRICS_CATALOG.transforms.find(t => t.fn === fn)!.label;
const WINDOW_LABELS = (['ever', 'at_least', 'streak'] as const).map(k => METRICS_CATALOG.operators.tests.find(t => t.key === k)!.label);
/** what no refusal of the class may say again: the words that named no reason, no fix and no example (QA unit C) */
const OLD = /not a series on the ticker's bars|use it where its test form allows it|is offered in (state|value)|is tested on its own|signal, not a value/;
/** a right and a wrong example close the message (a catalog name may hold parentheses: RS rank (percentile)) */
const examples = (m: string) => /\(right: .+; wrong: .+\)\.$/.test(m);

describe('the QA repros: a transform of a pattern names the reason, how to pass and a right and a wrong example', () => {
  it('change over 5 sessions of Hammer in a value test', () => {
    const e = refuse({ kind: 'value', metric: { kind: 'transform', fn: 'change', of: pattern('hammer'), args: { bars: 5 } }, op: 'gt', value: 0 });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', `${T}.metric.of`]);
    expect(e.message).toMatch(/Hammer is a pattern: a 0\/1 signal, detected or not on each session, with no value to measure, so "Change, in its own unit" cannot be taken of it/);
    expect(e.message).toContain('"Detected" (on the evaluated session) or "Detected within N sessions"');
    for (const w of WINDOW_LABELS) expect(e.message).toContain(`"${w}"`);
    expect(e.message).toMatch(/\(right: Hammer detected within 3 sessions, or Hammer detected on 3 of the last 10 sessions; wrong: "Change, in its own unit" of Hammer\)\.$/);
  });
  it('a moving average of Hammer in a state test, and in a value test: the same reason, never "offered in state or event tests"', () => {
    const ma = { kind: 'transform', fn: 'ma', of: pattern('hammer'), args: { length: 5 } };
    const st = refuse({ kind: 'state', lhs: ma, op: 'gt', rhs: { value: 0.5 } }), va = refuse({ kind: 'value', metric: ma, op: 'gt', value: 0.5 });
    expect([st.field, va.field]).toEqual([`${T}.lhs.of`, `${T}.metric.of`]);
    for (const e of [st, va]) { expect(e.message).toMatch(/so "Moving average of a series" cannot be taken of it\. Test it on its own/); expect(e.message).not.toMatch(OLD) }
    expect(st.message.slice(st.field.length)).toBe(va.message.slice(va.field.length));
  });
  it('the right examples are accepted and the wrong shapes refused (a case other than the repro: Morning Star, lag)', () => {
    const e = refuse({ kind: 'value', metric: { kind: 'transform', fn: 'lag', of: pattern('morning_star'), args: { bars: 1 } }, op: 'eq', value: 1 });
    expect(e.message).toMatch(/right: Morning Star detected within 3 sessions, or Morning Star detected on 3 of the last 10 sessions; wrong: "Value N sessions earlier" of Morning Star/);
    accepts({ kind: 'event', within: 3, signal: { pattern: pattern('morning_star') } });                                         // detected within 3 sessions
    accepts({ kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'state', pattern: pattern('morning_star') } }); // on 3 of the last 10
    accepts({ kind: 'window', mode: 'streak', length: 2, test: { kind: 'event', within: 1, signal: { pattern: pattern('morning_star') } } });
  });
});

describe('the class: every reference that is not a series, wherever a series is needed', () => {
  // every transform of the catalog takes a series as its `of`; the ones with a second series take it as that too
  const fns = METRICS_CATALOG.transforms.map(t => t.fn);
  const byArgs = METRICS_CATALOG.transforms.filter(t => t.ref_args.length);
  it('covers every kind of reference the contract has that is not a series', () => {
    expect([...NOT_SERIES_KINDS].sort()).toEqual(['pattern', 'rank', 'universe', 'xsection']);
    expect(new Set(Object.values(NOT_SERIES).map(r => r.kind))).toEqual(new Set(NOT_SERIES_KINDS));
    expect(fns.length).toBeGreaterThanOrEqual(18);
    expect(byArgs.map(t => t.fn).sort()).toEqual(['ratio', 'relative']);
  });
  it('as the series of each transform, in a value, a state and an event test: refused at the operand, its transform named', () => {
    let n = 0;
    for (const [k, r] of Object.entries(NOT_SERIES)) for (const fn of fns) {
      const tr = { kind: 'transform', fn, of: r };
      for (const [test, field] of [
        [{ kind: 'value', metric: tr, op: 'gt', value: 0 }, `${T}.metric.of`],
        [{ kind: 'state', lhs: tr, op: 'gt', rhs: { value: 0 } }, `${T}.lhs.of`],
        [{ kind: 'event', within: 3, signal: { lhs: tr, op: 'crosses_above', rhs: { value: 0 } } }, `${T}.signal.lhs.of`],
      ] as const) {
        const e = refuse(test);
        expect([k, fn, e.code, e.field]).toEqual([k, fn, 'INVALID_CONDITION', field]);
        expect(e.message, `${k} ${fn}`).toContain(`"${labelOf(fn)}"`);
        expect(examples(e.message), e.message).toBe(true);
        expect(e.message).not.toMatch(OLD);
        n++;
      }
    }
    expect(n).toBe(Object.keys(NOT_SERIES).length * fns.length * 3);
  });
  it('as the second series of ratio and relative, as the series a rank orders, and as either side of a comparison', () => {
    for (const [k, r] of Object.entries(NOT_SERIES)) {
      for (const t of byArgs) {
        const e = refuse({ kind: 'value', metric: { kind: 'transform', fn: t.fn, of: rsi, args: { [t.ref_args[0].key]: r } }, op: 'gt', value: 0 });
        expect([k, t.fn, e.field]).toEqual([k, t.fn, `${T}.metric.args.${t.ref_args[0].key}`]);
        expect(e.message).toContain(`second series of "${labelOf(t.fn)}"`);
        expect(examples(e.message), e.message).toBe(true);
      }
      const rk = refuse({ kind: 'value', metric: { kind: 'rank', of: r }, op: 'ge', value: 90 });
      expect([k, rk.field, examples(rk.message)]).toEqual([k, `${T}.metric.of`, true]);
      expect(rk.message).toMatch(k === 'rank' ? /cannot be ranked again/ : /cannot be ranked among the screened stocks/);
      for (const [test, field, words] of [
        [{ kind: 'state', lhs: r, op: 'gt', rhs: { value: 0 } }, `${T}.lhs`, /state comparison|compared with a value or another series/],
        [{ kind: 'state', lhs: close, op: 'gt', rhs: r }, `${T}.rhs`, /state comparison|compared with a value or another series/],
        [{ kind: 'event', within: 3, signal: { lhs: r, op: 'crosses_above', rhs: { value: 0 } } }, `${T}.signal.lhs`, /does not cross a value or another series/],
      ] as const) {
        const e = refuse(test);
        expect([k, e.code, e.field]).toEqual([k, 'INVALID_CONDITION', field]);
        expect(e.message).toMatch(words);
        expect(examples(e.message), e.message).toBe(true);
        expect(e.message).not.toMatch(OLD);
      }
    }
  });
  it('a pattern in a value test: how to pass in a condition, in a window and in a universe filter (each true where it occurs)', () => {
    for (const type of ['hammer', 'breakout', 'three_black_crows']) {
      const name = METRICS_CATALOG.metrics.find(m => m.id === type)!.label!, v = { kind: 'value', metric: pattern(type), op: 'eq', value: 1 };
      const c = refuse(v), w = refuse({ kind: 'window', mode: 'ever', length: 5, test: v }), f = refuse(v, true);
      expect([c.field, w.field, f.field]).toEqual([`${T}.metric`, `${T}.test.metric`, 'definition.universe.metric_filters[0].metric']);
      expect(c.message).toMatch(new RegExp(`Test it on its own: .*wrong: ${name} = 1\\)\\.$`));
      expect(w.message).toMatch(new RegExp(`Inside a window, count the sessions on which the pattern itself was detected.*right: ${name} detected on 3 of the last 10 sessions; wrong: ${name} = 1 on 3 of the last 10 sessions\\)\\.$`));
      expect(f.message).toMatch(new RegExp(`it cannot be a universe filter.*Add it as a condition instead.*right: a condition ${name} detected within \\d+ sessions; wrong: a universe filter ${name} = 1\\)\\.$`));
      for (const e of [c, w, f]) expect(e.message).not.toMatch(OLD);
    }
  });
  it('a value per stock inside a window: taken out of the window (a universe attribute, the RS rank, a rank)', () => {
    for (const k of ['universe', 'xsection', 'rank']) {
      const e = refuse({ kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'value', metric: NOT_SERIES[k], op: 'gt', value: 0 } });
      expect([k, e.field]).toEqual([k, `${T}.test.metric`]);
      expect(e.message).toMatch(/a window cannot count the sessions on which it passed\. Test (its value|the rank) on its own, as a condition outside any window/);
      expect(examples(e.message), e.message).toBe(true);
    }
    // a rank as a universe filter: a condition instead
    const f = refuse({ kind: 'value', metric: NOT_SERIES.rank, op: 'ge', value: 90 }, true);
    expect([f.field, examples(f.message)]).toEqual(['definition.universe.metric_filters[0].metric', true]);
    expect(f.message).toMatch(/Add it as a condition instead/);
    // and as values they pass where they are offered: alone in a condition, a universe attribute as a filter
    for (const k of ['universe', 'xsection', 'rank']) accepts({ kind: 'value', metric: NOT_SERIES[k], op: 'gt', value: 0 });
    expect(() => validateDefinition(asFilter({ kind: 'value', metric: NOT_SERIES.universe, op: 'gt', value: 0 }) as never, CTX)).not.toThrow();
  });
  it('the same words when an unchecked test is bound (condition.ts, metrics.ts resolveSeries) as when it is validated', () => {
    const ctx = { ...OPTS, withinMax: WITHIN_MAX, catalog: METRICS_CATALOG };
    for (const test of [
      { kind: 'value', metric: { kind: 'transform', fn: 'change_pct', of: pattern('tweezer_top'), args: { bars: 5 } }, op: 'gt', value: 0 },
      { kind: 'value', metric: { kind: 'rank', of: pattern('evening_star') }, op: 'ge', value: 90 },
      { kind: 'state', lhs: { kind: 'transform', fn: 'slope', of: NOT_SERIES.universe, args: { length: 5 } }, op: 'gt', rhs: { value: 0 } },
      { kind: 'value', metric: pattern('dragonfly_doji'), op: 'gt', value: 0 },
      { kind: 'window', mode: 'ever', length: 4, test: { kind: 'value', metric: pattern('gravestone_doji'), op: 'gt', value: 0 } },
      { kind: 'window', mode: 'ever', length: 4, test: { kind: 'value', metric: NOT_SERIES.xsection, op: 'gt', value: 50 } },
    ]) {
      const v = refuse(test), b = refusal(() => bindTest('a', test as never, T, ctx));
      expect([b.code, b.field, b.message]).toEqual([v.code, v.field, v.message]);
    }
  });
  it('a kind that is no reference at all keeps its own refusal (the kinds of the contract)', () => {
    const e = refuse({ kind: 'value', metric: { kind: 'transform', fn: 'change', of: { kind: 'candle', type: 'x' }, args: { bars: 5 } }, op: 'gt', value: 0 });
    expect([e.field, e.details?.allowed]).toEqual([`${T}.metric.of.kind`, ['indicator', 'price', 'transform', 'pattern', 'flow', 'xsection', 'universe', 'rank']]);
    expect(notSeriesRefusal({ kind: 'candle' } as never, 'f', { as: 'value' }).field).toBe('f.kind');
  });
});

describe('a window\'s count: the rule, what is wrong with the count given, a right and a wrong example (the count given)', () => {
  const w = (count: unknown, length = 5) => ({ kind: 'window', mode: 'at_least', length, ...(count === undefined ? {} : { count }), test: { kind: 'state', pattern: pattern('hammer') } });
  it('0 of 5: at least 1 and at most the length, wrong 0 of 5 (QA unit C), and the other ways to miss it', () => {
    const cases: [unknown, number, RegExp][] = [
      [0, 5, /from 1 to the window length 5: 0 is below 1, so the test would pass without a single passing session \(right: 3 of 5; wrong: 0 of 5\)\.$/],
      [-2, 5, /-2 is below 1.*\(right: 3 of 5; wrong: -2 of 5\)\.$/],
      [6, 5, /6 is more than the 5 sessions of the window, so it can never be met \(right: 3 of 5; wrong: 6 of 5\)\.$/],
      [1.5, 5, /1\.5 is not a whole number of sessions \(right: 3 of 5; wrong: 1\.5 of 5\)\.$/],
      ['3', 5, /"3" is not a number \(right: 3 of 5; wrong: "3" of 5\)\.$/],
      [3, 2, /from 1 to the window length 2: 3 is more than the 2 sessions.*\(right: 2 of 2; wrong: 3 of 2\)\.$/],
      [0, 1, /\(right: 1 of 1; wrong: 0 of 1\)\.$/],
    ];
    for (const [count, length, words] of cases) {
      const e = refuse(w(count, length));
      expect([count, e.code, e.field]).toEqual([count, 'INVALID_CONDITION', `${T}.count`]);
      expect(e.message).toMatch(words);
      expect(e.message).not.toMatch(/cannot be met;|is required/);
    }
    for (const count of [undefined, null]) expect(refuse(w(count)).message).toMatch(/count is required with mode at_least: how many of the 5 sessions must pass, a whole number from 1 to 5 \(right: 3 of 5; wrong: no count, or 0 of 5\)\.$/);
  });
  it('the right examples are accepted: 3 of 5, 2 of 2, 1 of 1, and the bounds 1 and the length', () => {
    for (const [count, length] of [[3, 5], [2, 2], [1, 1], [1, 5], [5, 5]]) accepts(w(count, length));
  });
});
