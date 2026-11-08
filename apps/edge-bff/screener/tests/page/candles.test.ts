/* The candlestick patterns on the page (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/P6_CANDLES.md section 2):
   "Add a condition" offers the catalog's 20 pattern entries in their own group after Technical, each with its
   parameters (the core registry's, at their defaults), found by search ("hammer", "engulfing", "doji", and the
   Indonesian synonyms); a row adds a card whose wire test is the pattern within 3 sessions (the catalog default) or on
   the bar; a parameter outside its range is refused in the row with its label and range, and nothing is added; and the
   fixture runs a screen with a candle condition through the core. Over the fixture's catalog (no DOM). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { entriesOf, GORD } from '../../src/entries.ts';
import { toWire } from '../../src/forms.ts';
import { ctx, freshUniverse, S } from '../../src/state.ts';
import { ALL, addItem, groupsOf, listItems, resetRules, ruleErrors, ruleOf, setOpt } from '../../src/add-condition.ts';
import { CANDLES } from '../../../backtest/src/core/candles.ts';
import { fixtureApi } from '../fixture/api.ts';

let catalog: CatalogResponse;
beforeAll(async () => {
  const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
});
beforeEach(() => {
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.api = { run: () => { throw new Error('the window sent a run') } } as never;
  ctx.metrics = [];
  S.universe = freshUniverse(); S.cards = []; S.errors = {};
  resetRules();
});
const IDS = CANDLES.patterns.map(p => p.id);
const item = (key: string) => listItems('', ALL, 'group').find(it => it.key === key)!;
const found = (q: string) => listItems(q, ALL, 'group').filter(it => it.group === 'Candlestick').map(it => it.key);

describe('Add a condition offers the 20 candlestick patterns', () => {
  it('in their own group "Candlestick patterns", right after Technical, each available with its parameters', () => {
    expect(GORD.indexOf('Candlestick')).toBe(GORD.indexOf('Technical') + 1);
    const g = groupsOf(), at = g.findIndex(x => x.g === 'Candlestick');
    expect(g[at]).toEqual({ g: 'Candlestick', label: 'Candlestick patterns', n: 20 });
    expect(g[at - 1].g).toBe('Technical');
    for (const p of CANDLES.patterns) {
      const e = ctx.byKey.get(p.id)!, it = item(p.id);
      expect([e.kind, e.group, e.label, e.available]).toEqual(['metric', 'Candlestick', p.name, true]);
      expect(e.params.map(q => [q.key, q.default])).toEqual(p.params.map(q => [q.key, q.default]));
      // the row shows the parameters at their defaults
      expect(it.ok).toBe(true);
      for (const q of p.params) expect(it.sub).toContain(`${q.label} ${q.default}`);
      // tested on the bar ("Detected") or within N sessions ("Detected (event)", the default: within 3)
      expect(e.opts.map(o => [o.label, o.kind, o.within])).toEqual([['Detected', 'state', false], ['Detected (event)', 'event', true]]);
      expect([e.opts.find(o => o.key === e.def.opt)!.kind, e.def.within]).toEqual(['event', 3]);
    }
  });
  it('search finds them: hammer, engulfing, doji, and the Indonesian synonyms', () => {
    expect(found('hammer')).toEqual(['hammer', 'inverted_hammer']);
    expect(found('engulfing')).toEqual(['bullish_engulfing', 'bearish_engulfing']);
    expect(found('doji')).toEqual(['dragonfly_doji', 'gravestone_doji']);
    expect(found('star')).toEqual(['shooting_star', 'morning_star', 'evening_star']);
    expect(found('palu')).toEqual(['hammer', 'inverted_hammer']);
    expect(found('bintang pagi')).toEqual(['morning_star']);
    expect(found('candlestick').length).toBe(0);                     // the group name is a heading, not a search word
    expect(new Set(listItems('', ALL, 'group').filter(it => it.group === 'Candlestick').map(it => it.key))).toEqual(new Set(IDS));
  });
});

describe('a candle row adds its card', () => {
  it('Add: the pattern within 3 sessions at the defaults; on the bar when "Detected" is chosen', () => {
    expect(addItem(item('morning_star')).ok).toBe(true);
    const e = ctx.byKey.get('morning_star')!, c = S.cards[0];
    // the page sends only the parameters changed from the catalog default (forms.ts withParams); the core fills the rest
    expect(toWire(e, c).test).toEqual({ kind: 'event', signal: { pattern: { kind: 'pattern', type: 'morning_star' } }, within: 3 });
    const h = ctx.byKey.get('hammer')!;
    setOpt(h, h.opts.find(o => o.kind === 'state')!.key);
    ruleOf(h).params = { ...ruleOf(h).params, trend: 'change', body_max_pct: 25 };
    expect(ruleErrors(h)).toEqual({});
    expect(addItem(item('hammer')).ok).toBe(true);
    expect(toWire(h, S.cards[1]).test).toEqual({ kind: 'state', pattern: { kind: 'pattern', type: 'hammer', params: { trend: 'change', body_max_pct: 25 } } });
  });
  it('a parameter outside its range is refused in the row with its label and range; nothing is added', () => {
    const e = ctx.byKey.get('tweezer_bottom')!;
    ruleOf(e).params = { ...ruleOf(e).params, tolerance_ticks: 11 };
    expect(ruleErrors(e)['p.tolerance_ticks']).toMatch(/Lows equal within \(ticks\)/);
    const r = addItem(item('tweezer_bottom'));
    expect(r.ok).toBe(false); expect(r.message).toContain('Lows equal within (ticks)');
    expect(S.cards.length).toBe(0);
    ruleOf(e).params = { ...ruleOf(e).params, tolerance_ticks: 1.5 };
    expect(ruleErrors(e)['p.tolerance_ticks']).toBeTruthy();         // a whole number of ticks
  });
});

describe('the fixture screens with a candle condition through the core', () => {
  it('runs, and refuses a parameter outside the range as the worker does', async () => {
    const api = fixtureApi();
    const def = (params: Record<string, unknown>) => ({ universe: { ...UNIVERSE_DEFAULTS, include_unclassified: true, price_min: null, adv20_min_idr: null }, logic: 'all' as const,
      conditions: [{ id: 'a', enabled: true, test: { kind: 'event', within: 20, signal: { pattern: { kind: 'pattern', type: 'bullish_engulfing', params } } } }] });
    const run = await api.run({ schema_version: 1, definition: def({ trend: 'none' }) } as never);
    expect(run.body.match_count).toBeGreaterThan(0);
    expect(run.body.rows.every(r => r.cells[0].status === 'pass')).toBe(true);
    await expect(api.run({ schema_version: 1, definition: def({ trend_length: 1 }) } as never)).rejects.toMatchObject({ code: 'PARAM_OUT_OF_RANGE' });
  });
});
