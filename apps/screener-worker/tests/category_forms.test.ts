// EXEC-PINE-INDICATORS (the user 2026-11-23, Alpha KAMA "1a", "2a"): the category forms, generic over any output the
// registry codes in categories (indRegistry outs[].categories; today I58 Alpha KAMA's color_state, a lab item, so this
// runs in the worker suite, which holds the full registry, and not in the page suites, which read the public build).
// The transforms in_categories and category_change against the formula's own series, the canonical arguments, the
// refusals (each naming the field, the keys it may hold and a right and a wrong example), the test forms, and the page's
// card to wire and back. The look-ahead gate covers both transforms (backtest-worker tests/lookahead.test.ts).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { resolveSeries, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { SBY_ID, catalogIndicator } from '../../edge-bff/screener/src/core/registry.ts';
import { validateTest } from '../../edge-bff/screener/src/core/validate.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { categoryPick, entriesOf } from '../../edge-bff/screener/src/entries.ts';
import { fromWire, newCard, toWire, cardErrors } from '../../edge-bff/screener/src/forms.ts';

type N = number | null;
function bars(n: number) {
  let s = 99; const rnd = () => (s = (s * 1103515245 + 12345) % 2147483648) / 2147483648;
  const O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: number[] = [];
  let c = 3000;
  for (let i = 0; i < n; i++) {
    const o = c; c = Math.max(100, Math.round(o + 12 * Math.sin(i / 40) + (rnd() - 0.5) * 60));
    O.push(o); H.push(Math.max(o, c) + 15); L.push(Math.min(o, c) - 15); C.push(c); V.push(1e6);
  }
  return { O, H, L, C, V };
}
const B = bars(900), dates = B.C.map((_, i) => `2023-${String(1 + Math.floor(i / 28) % 12).padStart(2, '0')}-${String(1 + i % 28).padStart(2, '0')}`);
const T = tickerCalc({ ticker: 'AAAA', dates, bars: B as never });
const state = (F.alpha_kama(B as never, {}) as Record<string, N[]>).color_state;
const of = { kind: 'indicator', indicator: 'I58', output: 'color_state' };
const ser = (fn: string, args: Record<string, unknown>) => resolveSeries({ kind: 'transform', fn, of, args } as never, 'c', { capBudgetMs: 2000 });
const refused = (f: () => unknown): { code: string; field: string; message: string } => { try { f() } catch (e) { const x = e as { code: string; field: string; message: string }; return { code: x.code, field: x.field, message: x.message } } throw new Error('not refused') };

test('in_categories: 1 where the colour state is one of the chosen, 0 elsewhere, null where it is missing', () => {
  const s = ser('in_categories', { categories: 'yellow_green,green' }).full(T) as N[];
  assert.equal(s.length, state.length);
  for (let i = 0; i < s.length; i++) assert.equal(s[i], state[i] === null ? null : state[i] === 3 || state[i] === 4 ? 1 : 0, `bar ${i}`);
  assert.ok(s.filter(v => v === 1).length > 0 && s.filter(v => v === 0).length > 0, 'the fixture reaches both');
});

test('category_change: 1 where yesterday was a from and today its to, for any chosen change (OR), else 0', () => {
  const s = ser('category_change', { changes: 'yellow_green>green,yellow>green' }).full(T) as N[];
  let ones = 0;
  for (let i = 0; i < s.length; i++) {
    const a = i > 0 ? state[i - 1] : null, b = state[i];
    assert.equal(s[i], a === null || b === null ? null : (a === 3 && b === 4) || (a === 2 && b === 4) ? 1 : 0, `bar ${i}`);
    ones += s[i] === 1 ? 1 : 0;
  }
  assert.ok(ones > 0, 'the fixture has such a change');
});

test('the arguments are canonical: the same choice in another order, with spaces or repeats, is the same series key', () => {
  const k = (v: string) => ser('in_categories', { categories: v }).key;
  assert.equal(k(' green , yellow_green,green'), k('yellow_green,green'));
  const c = (v: string) => ser('category_change', { changes: v }).key;
  assert.equal(c('yellow>green, yellow_green>green'), c('yellow_green>green,yellow>green,yellow>green'));
  assert.notEqual(k('green'), k('yellow_green,green'));
});

test('refusals name the field, the keys and a right and a wrong example', () => {
  let r = refused(() => ser('in_categories', { categories: 'purple' }));
  assert.equal(r.code, 'INVALID_CONDITION'); assert.equal(r.field, 'c.args.categories');
  assert.match(r.message, /purple is not a category/); assert.match(r.message, /red, orange, yellow, yellow_green, green/); assert.match(r.message, /right: .* wrong: /);
  r = refused(() => ser('in_categories', {}));
  assert.equal(r.field, 'c.args.categories'); assert.match(r.message, /choose at least one category/);
  r = refused(() => ser('category_change', { changes: 'green>green,red-orange' }));
  assert.equal(r.field, 'c.args.changes'); assert.match(r.message, /green>green, red-orange are not changes/);
  r = refused(() => resolveSeries({ kind: 'transform', fn: 'in_categories', of: { kind: 'price', field: 'close' }, args: { categories: 'green' } } as never, 'c', { capBudgetMs: 2000 }));
  assert.equal(r.field, 'c.of'); assert.match(r.message, /reads an indicator output coded in categories/);
  r = refused(() => resolveSeries({ kind: 'transform', fn: 'in_categories', of: { kind: 'indicator', indicator: 'I58', output: 'kama' }, args: { categories: 'green' } } as never, 'c', { capBudgetMs: 2000 }));
  assert.equal(r.field, 'c.of');
});

test('the test forms: the output offers "is one of" and "changed within N"; another operator is refused with what it offers', () => {
  const ctx = { limits: { max_conditions: 10, max_metric_filters: 5, within_max: 130 }, capBudgetMs: 2000, tickers: new Set<string>(), groupings: [], metrics: METRICS_CATALOG, availability: new Map() };
  const v = (fn: string, args: Record<string, unknown>, op = 'gt', value = 0.5) => ({ kind: 'value', metric: { kind: 'transform', fn, of, args }, op, value });
  assert.doesNotThrow(() => validateTest(v('in_categories', { categories: 'green' }), 't', ctx as never));
  assert.doesNotThrow(() => validateTest({ kind: 'window', mode: 'ever', length: 5, test: v('category_change', { changes: 'yellow>green' }) }, 't', ctx as never));
  const r = refused(() => validateTest(v('in_categories', { categories: 'green' }, 'lt'), 't', ctx as never));
  assert.equal(r.code, 'INVALID_CONDITION'); assert.match(r.message, /does not offer state_category with lt/); assert.match(r.message, /state_category gt/);
});

test('the page: the choice is derived from the categories; a card goes to the wire and back unchanged', () => {
  const ind = catalogIndicator(SBY_ID.I58, { capBudgetMs: 2000 });
  const out = ind.outputs.find(o => o.key === 'color_state')!;
  assert.deepEqual(out.categories?.map(c => c.key), ['red', 'orange', 'yellow', 'yellow_green', 'green']);
  const changes = categoryPick(out, out.tests.find(t => t.form === 'event_category_change')!)!;
  assert.equal(changes.options!.length, 20);                       // every change between two of 5 categories
  assert.equal(changes.option_labels!['yellow_green>green'], 'Yellow-green → Green');
  const e = entriesOf({ indicators: [ind], metrics: [], fundamentals: [] } as never).find(x => x.key === 'I58')!;
  const set = e.opts.find(o => o.form === 'state_category')!, chg = e.opts.find(o => o.form === 'event_category_change')!;
  const a = newCard(e, [], { opt: set.key, pick: 'yellow_green,green' });
  const wa = toWire(e, a);
  assert.deepEqual((wa.test as any).metric, { kind: 'transform', fn: 'in_categories', of: { kind: 'indicator', indicator: 'I58', output: 'color_state' }, args: { categories: 'yellow_green,green' } });
  const back = fromWire(wa, new Map([[e.key, e]]));
  assert.equal(back.opt, set.key); assert.equal(back.pick, 'yellow_green,green'); assert.ok(!back.raw);
  const b = newCard(e, [], { opt: chg.key, pick: 'yellow>green', within: 7 });
  const wb = toWire(e, b);
  assert.equal((wb.test as any).kind, 'window'); assert.equal((wb.test as any).length, 7); assert.equal((wb.test as any).test.metric.args.changes, 'yellow>green');
  const back2 = fromWire(wb, new Map([[e.key, e]]));
  assert.equal(back2.opt, chg.key); assert.equal(back2.pick, 'yellow>green'); assert.equal(back2.within, 7);
  // a new card opens on the overlay's defaults; an empty choice is the card's error, not a request the worker refuses
  assert.equal(newCard(e, [], { opt: chg.key }).pick, 'yellow_green>green');
  assert.match(cardErrors(e, { ...a, pick: '' }).pick, /at least one category/);
});
