/* QA of unit C (2026-11-08), the page side of the Screener's patterns (EXEC-SCREENER-FLOW-CANDLES P6;
   verification/screener/OPERATORS.md section 4, type F, and section 5):
   1. every pattern entry (the existing price patterns and the 20 candlesticks) takes the window operators of a 0/1
      signal, read from the catalog's operators block (no measure, the window tests whose not_on leaves F): the wire is a
      window over the pattern's own test on each session, the core accepts it, it reads back as the same card, and the
      card, its column and its cells say it in words ("Detected on at least 3 of the last 10 sessions");
   2. a pattern's side (bullish, bearish) comes through the catalog from the core's candle registry;
   3. the search finds an entry by its group's heading and its side, for every group.
   Over the fixture's catalog, on patterns other than the Hammer QA used (no DOM; the smoke run draws them). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, Cell, ConditionDef } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { entriesOf, GHEAD, type Entry } from '../../src/entries.ts';
import { cardErrors, condText, fromWire, newCard, shortName, toWire } from '../../src/forms.ts';
import { canonical, ctx, freshUniverse, S } from '../../src/state.ts';
import { ALL, addItem, groupsOf, listItems, OP_OPT, resetRules, ruleErrors, ruleOf, setOpt } from '../../src/add-condition.ts';
import { defaultOp, isSignal, measuresFor, offersOperators, operatorTitle, opsFor, plainOffered, SIGNAL_KEY, SIGNAL_TYPE, testsFor, withTest, type OpState } from '../../src/operators.ts';
import { cellNote, cellText } from '../../src/cell-text.ts';
import { sideOf } from '../../src/texts.ts';
import { validateTest } from '../../src/core/validate.ts';
import { CANDLES } from '../../../backtest/src/core/candles.ts';
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
const patterns = () => ctx.entries.filter(e => e.metricKind === 'pattern');
const CTX = vctx(['BBCA']);
/** the operator of a pattern on a window test, N sessions, K of them for K of N */
const opOn = (e: Entry, test: string, n = 10, k = 3): OpState => ({ ...withTest(e.ops!, e, defaultOp(e.ops!, e), test), n, ...(test === 'at_least' ? { k } : {}) });
const cell = (value: number, status: Cell['status'] = 'pass'): Cell => ({ id: 'a', status, value, eval_date: '2026-10-28', reason: null, remark: null });

describe('finding 1: a pattern takes the window operators of a 0/1 signal, from the catalog', () => {
  it('every pattern entry: no measure, and the window tests whose not_on leaves F (ever, K of N, in a row); one session and within N stay the card\'s own "Detected"', () => {
    const ops = catalog.operators!;
    // what the block offers a 0/1 signal, computed here from the block itself (OPERATORS.md section 4: 1, 5, 9, 10)
    const windows = ops.tests.filter(t => t.length && !(t.not_on || []).includes(SIGNAL_TYPE)).map(t => t.key);
    expect(windows).toEqual(['ever', 'at_least', 'streak']);
    expect(ops.measures.filter(m => !m.not_on.includes(SIGNAL_TYPE))).toEqual([]);
    const ps = patterns();
    expect(ps.length).toBe(catalog.metrics.filter(m => m.kind === 'pattern').length);
    expect(ps.length).toBeGreaterThan(20);                          // the price patterns and the 20 candlesticks
    for (const e of ps) {
      expect([e.key, isSignal(e), offersOperators(e.ops, e)]).toEqual([e.key, true, true]);
      expect([e.key, measuresFor(e.ops!, e, SIGNAL_KEY)]).toEqual([e.key, []]);
      const op = defaultOp(e.ops!, e);
      expect([e.key, testsFor(e.ops!, e, op).map(t => t.key)]).toEqual([e.key, windows]);
      // the first window test of the catalog, its default sessions, read as "= 1" (detected), never a threshold to type
      expect(op).toMatchObject({ output: SIGNAL_KEY, measure: 'none', test: 'ever', cmp: 'eq', value: 1, n: 5 });
      expect(opsFor(e, op, ops.tests.find(t => t.key === 'value')!)).toEqual([]);
    }
    // an indicator and a flow indicator keep what they had: the measures and every test
    expect(plainOffered(entry('I13').ops!, entry('I13'), 'rsi')).toBe(true);
    expect(measuresFor(entry('I13').ops!, entry('I13'), 'rsi').length).toBeGreaterThan(5);
    expect(isSignal(entry('I13'))).toBe(false);
  });

  it('each one builds a window the core accepts and reads back as the same card: the price patterns and the candlesticks other than the Hammer', () => {
    let n = 0;
    for (const e of patterns().filter(x => x.available && x.key !== 'hammer')) {
      for (const t of testsFor(e.ops!, e, defaultOp(e.ops!, e))) {
        const op = opOn(e, t.key), c = newCard(e, [], { op });
        expect([e.key, t.key, cardErrors(e, c)]).toEqual([e.key, t.key, {}]);
        const w = toWire(e, c);
        expect(() => validateTest(w.test, `${e.key}.${t.key}`, CTX)).not.toThrow();
        expect(w.test).toEqual({ kind: 'window', mode: t.key, length: 10, ...(t.key === 'at_least' ? { count: 3 } : {}), test: { kind: 'state', pattern: { kind: 'pattern', type: e.key } } });
        const back = fromWire(w, ctx.byKey);
        expect([e.key, t.key, back.raw, back.entry, back.op]).toEqual([e.key, t.key, undefined, e.key, op]);
        expect(canonical(toWire(e, back).test)).toBe(canonical(w.test));
        n++;
      }
    }
    expect(n).toBeGreaterThan(80);
    // a pattern's own parameters ride along, read back as the card's
    const b = entry('breakout'), op = opOn(b, 'streak', 3), c = newCard(b, [], { op, params: { length: 55 } });
    const w = toWire(b, c);
    expect(w.test).toEqual({ kind: 'window', mode: 'streak', length: 3, test: { kind: 'state', pattern: { kind: 'pattern', type: 'breakout', params: { length: 55 } } } });
    expect(() => validateTest(w.test, 'breakout.params', CTX)).not.toThrow();
    expect(fromWire(w, ctx.byKey)).toMatchObject({ entry: 'breakout', params: { length: 55 }, op });
  });

  it('the card, its column and its cells say it in words: Volume spike on 3 of the last 10 sessions, Three Black Crows 2 in a row', () => {
    const v = entry('volspike'), c = newCard(v, [], { op: opOn(v, 'at_least') });
    expect(condText(v, c)).toMatch(/: Detected on at least 3 of the last 10 sessions$/);
    expect(shortName(v, c)).toBe(`${v.short} · 3 of 10`);
    expect(cellText(v, c, cell(4))).toBe('Yes · 4/10');
    expect(cellNote(v, c, cell(4))).toBe('Detected on 4 of the last 10 sessions (3 needed)');
    expect(cellText(v, c, cell(1, 'fail'))).toBe('No · 1/10');
    expect(cellNote(v, c, cell(0, 'fail'))).toBe('Not detected in the last 10 sessions (3 needed)');
    expect(cellNote(v, c, { ...cell(0), status: 'na', reason: 'INSUFFICIENT_HISTORY' })).toBe('');
    const k = entry('three_black_crows'), s = newCard(k, [], { op: opOn(k, 'streak', 2) });
    expect(condText(k, s)).toMatch(/^Three Black Crows \(.*\): Detected for 2 sessions in a row$/);
    expect(shortName(k, s)).toBe('Three Black Crows · 2 in a row');
    expect(cellNote(k, s, cell(2))).toBe('Detected on each of the last 2 sessions (2 in a row needed)');
    expect(cellNote(k, s, cell(1, 'fail'))).toBe('Detected on the last session only (2 in a row needed)');
    expect(cellNote(k, s, cell(0, 'fail'))).toBe('Not detected on the last session (2 in a row needed)');
    const ev = newCard(k, [], { op: opOn(k, 'ever', 20) });
    expect(condText(k, ev)).toMatch(/: Detected at least once in the last 20 sessions$/);
    // no threshold, sign or "equal" leaks into the words of a 0/1 signal
    for (const x of [c, s, ev]) { const e = entryOf(x); expect(`${condText(e, x)} ${shortName(e, x)}`).not.toMatch(/=|equal|≥|threshold/) }
    // a window on an indicator keeps its count note in its own words
    const r = entry('I13'), rc = newCard(r, [], { op: { ...withTest(r.ops!, r, defaultOp(r.ops!, r), 'at_least'), n: 5, k: 3 } });
    expect(cellNote(r, rc, cell(3))).toBe('Passed on 3 of the last 5 sessions (3 needed)');
    expect(cellNote(r, newCard(r, [], { op: defaultOp(r.ops!, r) }), cell(95))).toBe('');
  });

  it('Add a condition: "Operator…" on Bearish Engulfing opens on the window tests named in its title; K of N is added as one card, with no run', () => {
    const e = entry('bearish_engulfing');
    expect(operatorTitle(e.ops!, e)).toBe('Count the sessions it is detected on, set in Customize: ever in the last N sessions, on K of the last N sessions, N sessions in a row');
    expect(operatorTitle(e.ops!, entry('I13'))).toMatch(/percentile/);
    setOpt(e, OP_OPT);
    const r = ruleOf(e);
    expect(r.op).toMatchObject({ test: 'ever', n: 5, cmp: 'eq', value: 1 });
    r.op = { ...withTest(e.ops!, e, r.op!, 'at_least'), n: 10, k: 3 };
    expect(ruleErrors(e)).toEqual({});
    const add = addItem(listItems('bearish engulfing', ALL, 'group').find(it => it.key === 'bearish_engulfing')!);
    expect(add).toEqual({ ok: true, message: 'Bearish Engulfing added · Detected on at least 3 of the last 10 sessions' });
    expect(S.cards.length).toBe(1);
    expect(toWire(e, S.cards[0]).test).toEqual({ kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'state', pattern: { kind: 'pattern', type: 'bearish_engulfing' } } });
    // back to its own condition: the operator is gone
    setOpt(e, e.def.opt);
    expect(ruleOf(e).op).toBeUndefined();
  });

  it('refused in place, never rounded: K above N and N above its range, each naming the fix with a right and a wrong example', () => {
    const e = entry('evening_star'), max = catalog.limits.find(l => l.name === 'within_max')!.value;
    setOpt(e, OP_OPT);
    const r = ruleOf(e);
    r.op = { ...withTest(e.ops!, e, r.op!, 'at_least'), n: 5, k: 6 };
    expect(ruleErrors(e)['o.k']).toBe('K of N: K must be at most N (right: 3 of 5; wrong: 6 of 5).');
    r.op = { ...r.op, n: max + 1, k: 3 };
    expect(ruleErrors(e)['o.n']).toBe(`Enter whole sessions from 1 to ${max}.`);
    const res = addItem(listItems('evening star', ALL, 'group').find(it => it.key === 'evening_star')!);
    expect(res.ok).toBe(false); expect(res.message).toContain('Enter whole sessions');
    expect(S.cards.length).toBe(0);
  });

  it('a window the card does not write is kept as saved, named by its pattern, never rewritten: the event read on a pattern that has a state, an unknown key', () => {
    const kept = (test: unknown) => fromWire({ id: 'k', enabled: true, test } as ConditionDef, ctx.byKey);
    const ev = kept({ kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'event', within: 1, signal: { pattern: { kind: 'pattern', type: 'morning_star' } } } });
    expect([ev.entry, !!ev.raw, ev.rawName]).toEqual([null, true, 'Morning Star']);
    expect(condText(undefined, ev)).toBe('Morning Star: detected within 1 session on 3 of the last 10 sessions (kept as saved; not editable here)');
    expect(toWire(undefined, ev).test).toEqual(ev.raw);
    const odd = kept({ kind: 'window', mode: 'ever', length: 5, test: { kind: 'state', pattern: { kind: 'pattern', type: 'breakout' }, op: 'gt' } });
    expect([odd.entry, !!odd.raw, odd.rawName]).toEqual([null, true, 'Breakout above prior N-session high']);
    // a parameter the card does not have
    expect(kept({ kind: 'window', mode: 'ever', length: 5, test: { kind: 'state', pattern: { kind: 'pattern', type: 'breakout', params: { span: 3 } } } }).raw).toBeTruthy();
  });

  it('the fixture screens a pattern window through the core: "ever in the last 20" matches the stocks "within 20" does, each cell with its count', async () => {
    const api = fixtureApi(), U = { ...UNIVERSE_DEFAULTS, include_unclassified: true, price_min: null, adv20_min_idr: null };
    const b = entry('breakout'), c = newCard(b, [], { op: opOn(b, 'ever', 20) });
    c.id = 'a';
    const run = async (test: unknown) => (await api.run({ schema_version: 1, definition: { universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] } } as never)).body;
    const win = await run(toWire(b, c).test), within = await run({ kind: 'event', within: 20, signal: { pattern: { kind: 'pattern', type: 'breakout' } } });
    const names = (r: typeof win) => r.rows.filter(x => x.status === 'match').map(x => x.ticker).sort();
    expect(names(win).length).toBeGreaterThan(0);
    expect(names(win)).toEqual(names(within));
    for (const row of win.rows) {
      const x = row.cells[0];
      expect(cellText(b, c, x)).toMatch(/^Yes · [1-9]\d*\/20$/);
      expect(cellNote(b, c, x)).toBe(`Detected on ${x.value} of the last 20 sessions`);
    }
  });
});

describe('finding 2: a pattern\'s side comes through the catalog', () => {
  it('every candlestick entry carries its side as the core\'s candle registry states it; no other entry has one; the page words it', () => {
    const sides = new Map(CANDLES.patterns.map(p => [p.id, p.side]));
    expect(sides.size).toBe(20);
    for (const m of [...catalog.metrics, ...catalog.fundamentals]) expect([m.id, m.side]).toEqual([m.id, sides.get(m.id)]);
    for (const e of ctx.entries) expect([e.key, e.side]).toEqual([e.key, sides.get(e.key)]);
    expect([...sides.values()].filter(s => s === 'bullish').length).toBe(10);
    expect(sideOf(entry('morning_star'))).toEqual({ side: 'bullish', word: 'Bullish', line: 'Bullish pattern', title: 'Bullish pattern: read as a sign that the price may rise.' });
    expect(sideOf(entry('dark_cloud_cover'))).toMatchObject({ side: 'bearish', word: 'Bearish', line: 'Bearish pattern' });
    expect(sideOf(entry('breakout'))).toBe(null);
    expect(sideOf(entry('I13'))).toBe(null);
  });
});

describe('finding 3: the search finds an entry by its group\'s heading and its side, for every group', () => {
  const found = (q: string) => listItems(q, ALL, 'group').filter(it => it.kind === 'ind').map(it => it.key);
  const inGroup = (g: string) => ctx.entries.filter(e => e.group === g).map(e => e.key);
  it('each group\'s heading, as the page shows it, finds every entry of that group', () => {
    const gs = groupsOf();
    expect(gs.length).toBeGreaterThan(6);
    for (const g of gs) {
      const got = new Set(found(GHEAD(g.g).toLowerCase()));
      expect([g.g, inGroup(g.g).filter(k => !got.has(k))]).toEqual([g.g, []]);
    }
  });
  it('"flow" and "bandarmology" find the flow entries, "momentum" the momentum indicators, "candle" and "pattern" the candlesticks (the two Doji too)', () => {
    const flow = inGroup('Flow');
    expect(flow.length).toBeGreaterThan(40);
    for (const q of ['flow', 'bandarmology', 'Bandarmology']) expect(flow.filter(k => !found(q).includes(k))).toEqual([]);
    expect(inGroup('Momentum').filter(k => !found('momentum').includes(k))).toEqual([]);
    const candles = inGroup('Candlestick');
    expect(candles.length).toBe(20);
    for (const q of ['candle', 'candlestick', 'pattern']) expect(candles.filter(k => !found(q).includes(k))).toEqual([]);
    expect(found('candle')).toEqual(expect.arrayContaining(['dragonfly_doji', 'gravestone_doji']));
  });
  it('"bullish" and "bearish" find the candlesticks of that side, not the other side', () => {
    const side = (s: string) => CANDLES.patterns.filter(p => p.side === s).map(p => p.id);
    for (const [q, mine, other] of [['bullish', 'bullish', 'bearish'], ['bearish', 'bearish', 'bullish'], ['bull', 'bullish', 'bearish']] as const) {
      const got = found(q);
      expect([q, side(mine).filter(k => !got.includes(k))]).toEqual([q, []]);
      expect([q, side(other).filter(k => got.includes(k))]).toEqual([q, []]);
    }
    // a name with the word keeps matching (MACD bullish divergence is a price pattern)
    expect(found('bullish')).toContain('macd_divergence');
  });
});

const entryOf = (c: { entry: string | null }) => c.entry ? ctx.byKey.get(c.entry) : undefined;
