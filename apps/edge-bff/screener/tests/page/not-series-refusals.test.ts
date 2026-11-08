/* The page words the core's refusal of a reference that is not a series, and of a window's count (QA unit C; metrics.ts
   notSeriesRefusal, condition.ts countRefusal), as the worker sends them: texts.ts errorText leads with the card's
   place, keeps the core's reason, how to pass and its right and wrong example, ends with the fix, and shows no internal
   name (tests/page/plain-words.ts INTERNAL). The refusals are the core's own (validateDefinition), not copies. */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { errorText } from '../../src/texts.ts';
import { ctx, S } from '../../src/state.ts';
import type { Card } from '../../src/forms.ts';
import type { Entry } from '../../src/entries.ts';
import { vctx } from '../core/helpers.ts';
import { INTERNAL } from './plain-words.ts';

const CTX = vctx(['A']);
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null };
const entry = (key: string, label: string) => ({ key, kind:'metric', group:'Candlestick', label, short:label, desc:'', params:[], opts:[],
  def:{ opt:'', value:'', value2:'', within:3 }, available:true, availability:'AVAILABLE', reason:null, synonyms:[], history:null }) as unknown as Entry;
const card = (id: string, e: string): Card => ({ id, on:true, entry:e, params:{}, opt:'', value:'', value2:'', within:'', second:{} });
/** the page's words of the core's refusal of a definition whose first condition is `test` (or whose first universe filter
    is `filter`) */
function shown(test: unknown, filter?: unknown): string {
  const def = { universe: filter ? { ...U, metric_filters: [filter] } : U, logic: 'all', conditions: test ? [{ id: 'a', enabled: true, test }] : [] };
  try { validateDefinition(def as never, CTX) } catch (e) {
    if (!(e instanceof ScreenerError)) throw e;
    const m = errorText(e.code, { field: e.field, details: e.details ?? null, server: e.message });
    expect(m, m).not.toMatch(INTERNAL);
    return m;
  }
  throw new Error('expected a refusal');
}

beforeEach(() => {
  ctx.byKey = new Map([entry('hammer', 'Hammer'), entry('morning_star', 'Morning Star'), entry('chg_1d_pct', '1-day change')].map(e => [e.key, e]));
  S.cards = [card('a', 'hammer')];
  S.universe.filters = [card('f', 'morning_star')];
});
afterEach(() => { ctx.byKey = new Map(); S.cards = []; S.universe.filters = [] });

describe('a reference that is not a series, on the page', () => {
  it('the QA repro: the card, the reason, how to pass, the right and the wrong example, the fix', () => {
    const m = shown({ kind: 'value', metric: { kind: 'transform', fn: 'change', of: { kind: 'pattern', type: 'hammer' }, args: { bars: 5 } }, op: 'gt', value: 0 });
    expect(m).toBe('Condition 1 (Hammer): Hammer is a pattern: a 0/1 signal, detected or not on each session, with no value to measure, so "Change, in its own unit" cannot be taken of it. '
      + 'Test it on its own: "Detected" (on the evaluated session) or "Detected within N sessions", or count the sessions it was detected on with a window over "Detected" '
      + '("Ever in the last N sessions", "On K of the last N sessions" or "N sessions in a row") (right: Hammer detected within 3 sessions, or Hammer detected on 3 of the last 10 sessions; '
      + 'wrong: "Change, in its own unit" of Hammer). Change it and run again.');
  });
  it('the other places: a moving average in a state test, a window, a universe filter, a value per stock in a window', () => {
    const ma = shown({ kind: 'state', lhs: { kind: 'transform', fn: 'ma', of: { kind: 'pattern', type: 'hammer' }, args: { length: 5 } }, op: 'gt', rhs: { value: 0.5 } });
    expect(ma).toMatch(/^Condition 1 \(Hammer\): Hammer is a pattern: .*"Moving average of a series" cannot be taken of it\. Test it on its own: .*\(right: .+; wrong: .+\)\. Change it and run again\.$/);
    const w = shown({ kind: 'window', mode: 'ever', length: 5, test: { kind: 'value', metric: { kind: 'pattern', type: 'hammer' }, op: 'gt', value: 0 } });
    expect(w).toMatch(/^Condition 1 \(Hammer\): .*Inside a window, count the sessions on which the pattern itself was detected.*\(right: Hammer detected on 3 of the last 10 sessions; wrong: Hammer = 1 on 3 of the last 10 sessions\)\. Change it and run again\.$/);
    const f = shown(null, { kind: 'value', metric: { kind: 'pattern', type: 'morning_star' }, op: 'gt', value: 0 });
    expect(f).toMatch(/^Universe filter 1 \(Morning Star\): Morning Star is a pattern: .*Add it as a condition instead.*\(right: a condition Morning Star detected within 3 sessions; wrong: a universe filter Morning Star = 1\)\. Change it and run again\.$/);
    S.cards = [card('a', 'chg_1d_pct')];
    const u = shown({ kind: 'window', mode: 'ever', length: 5, test: { kind: 'value', metric: { kind: 'universe', attr: 'chg_1d_pct' }, op: 'gt', value: 0 } });
    expect(u).toMatch(/^Condition 1 \(1-day change\): 1-day change is one value per stock at the evaluation date.*as a condition outside any window.*\(right: .+; wrong: .+\)\. Change it and run again\.$/);
  });
  it("a window's count: the card and its count, the rule, why, the right and the wrong example", () => {
    const m = shown({ kind: 'window', mode: 'at_least', length: 5, count: 0, test: { kind: 'state', pattern: { kind: 'pattern', type: 'hammer' } } });
    expect(m).toBe('Condition 1 (Hammer), count must be a whole number of sessions from 1 to the window length 5: 0 is below 1, so the test would pass without a single passing session (right: 3 of 5; wrong: 0 of 5). Change it and run again.');
  });
});
