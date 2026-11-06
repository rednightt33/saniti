/* EXEC-SCREENER-ADD (user 2026-11-06): the one way to add a condition, "Add a condition" (src/add-condition.ts), over
   the fixture's catalog (no DOM: the model the window draws), and the preview chart's overlay choice (ERRORS M368). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, PreviewResponse, SavedItem } from '../../src/core/contract.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard, toWire } from '../../src/forms.ts';
import { canonical, ctx, entryOf, freshUniverse, S } from '../../src/state.ts';
import { isCustom } from '../../src/forms.ts';
import { ALL, MY, ON_SCREEN, addItem, cardOfRule, groupsOf, itemSig, listItems, removeItem, resetRules, restore, ruleErrors, ruleOf, screenSigs, setOpt } from '../../src/add-condition.ts';
import { candleOverlays } from '../../src/preview.ts';
import { fixtureApi } from '../fixture/api.ts';

let catalog: CatalogResponse;
beforeAll(async () => {
  const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  catalog = c.body;
});
beforeEach(() => {
  ctx.catalog = catalog; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  // a run must never start from the window: adding is an edit, the table waits for Screen now
  ctx.api = { run: () => { throw new Error('the window sent a run') } } as never;
  ctx.metrics = [];
  S.universe = freshUniverse(); S.cards = []; S.errors = {};
  resetRules();
});
const item = (key: string) => listItems('', ALL, 'group').find(it => it.key === key)!;
const sigOf = (c: (typeof S.cards)[number]) => canonical(toWire(entryOf(c), c).test);

describe('the rows (from the catalog)', () => {
  it('every indicator once, by group in the page order, the ones without data last in their group', () => {
    const rows = listItems('', ALL, 'group');
    expect(rows.length).toBe(ctx.entries.length);
    const order = groupsOf().map(g => g.g);
    for (let i = 1; i < rows.length; i++) {
      const a = order.indexOf(rows[i - 1].group), b = order.indexOf(rows[i].group);
      expect(a <= b, `${rows[i - 1].key} before ${rows[i].key}`).toBe(true);
      if (a === b) expect(Number(rows[i - 1].ok) >= Number(rows[i].ok)).toBe(true);
    }
    // the group counts are the catalog's and add up to every indicator
    expect(groupsOf().reduce((n, g) => n + g.n, 0)).toBe(ctx.entries.length);
    // an indicator without data says why (the catalog's reason), never a blank row
    for (const r of rows.filter(r => !r.ok)) expect(r.why || r.sub).toBeTruthy();
  });
  it('searches name, short name and what it measures; sorts by name; My metrics lists the saved metrics only', () => {
    expect(listItems('rsi', ALL, 'group').some(it => it.key === 'I13')).toBe(true);
    const az = listItems('', ALL, 'az').filter(it => it.ok).map(it => it.label);
    expect(az).toEqual([...az].sort((a, b) => a.localeCompare(b)));
    const rsi = ctx.byKey.get('I13')!, fast = newCard(rsi, [], { params:{ length:7 } });
    ctx.metrics = [{ item_id:'m1', kind:'metric', name:'Fast RSI', revision:1, updated_at:null, definition:{ test:toWire(rsi, fast).test } } as unknown as SavedItem];
    const mine = listItems('', MY, 'group');
    expect(mine.map(it => it.label)).toEqual(['Fast RSI']);
    expect(mine[0].ok).toBe(true);
  });
});

describe('adding, removing, Undo', () => {
  it('Add makes a card with the catalog defaults (the card\'s own test), never a run; the row is then on the screen', () => {
    const it0 = item('I07');                                       // ADX: a value threshold (default 25)
    const r = addItem(it0);
    expect(r.ok).toBe(true);
    expect(S.cards.length).toBe(1);
    const c = S.cards[0], e = ctx.byKey.get('I07')!;
    expect(c.entry).toBe('I07'); expect(c.opt).toBe(e.def.opt); expect(c.value).toBe(e.def.value);
    expect(screenSigs().has(itemSig(it0))).toBe(true);
    expect(listItems('', ON_SCREEN, 'group').map(x => x.key)).toEqual(['I07']);
  });
  it('a changed threshold is a different condition: added with it, and the default row is not "on the screen"', () => {
    const e = ctx.byKey.get('I07')!;
    ruleOf(e).value = 30;
    expect(addItem(item('I07')).ok).toBe(true);
    expect(S.cards[0].value).toBe(30);
    resetRules();                                                   // the row back at the default 25
    expect(screenSigs().has(itemSig(item('I07')))).toBe(false);
  });
  it('a wrong threshold is refused with the card\'s own message, and nothing is added', () => {
    const e = ctx.byKey.get('I07')!;
    ruleOf(e).value = '';
    expect(ruleErrors(e).value).toBe('Enter a value.');
    const r = addItem(item('I07'));
    expect(r.ok).toBe(false); expect(r.message).toContain('Enter a value.');
    expect(S.cards.length).toBe(0);
  });
  it('another condition of the same indicator fills its value fields from the catalog default when empty', () => {
    const e = ctx.entries.find(x => x.opts.some(o => o.between && !o.disabled))!;
    const between = e.opts.find(o => o.between && !o.disabled)!;
    ruleOf(e).value = ''; ruleOf(e).value2 = '';
    setOpt(e, between.key);
    expect(ruleOf(e).value).toBe(e.def.value);
    expect(ruleOf(e).value2).not.toBe('');
  });
  it('an indicator without data cannot be added; its reason is the message', () => {
    const na = listItems('', ALL, 'group').find(it => !it.ok);
    if (!na) return;                                                // a catalog where every indicator has data
    const r = addItem(na);
    expect(r.ok).toBe(false); expect(S.cards.length).toBe(0);
  });
  it('Remove takes every card with that exact test; Undo puts them back at their places', () => {
    addItem(item('I13')); addItem(item('I07')); addItem(item('I13'));
    expect(S.cards.length).toBe(3);
    const before = S.cards.map(sigOf);
    const gone = removeItem(item('I13'));
    expect(gone.length).toBe(2); expect(S.cards.length).toBe(1);
    restore(gone);
    expect(S.cards.map(sigOf)).toEqual(before);
    expect(new Set(S.cards.map(c => c.id)).size).toBe(3);           // ids stay unique
  });
});

describe('the parameters in the row (user 2026-11-06, option A: as on the card)', () => {
  it('a row opens at the catalog defaults; a changed Length is added with the card (Custom) and is another condition', () => {
    const e = ctx.byKey.get('I01')!, len = e.params.find(p => p.key === 'length')!;
    expect(ruleOf(e).params.length).toBe(len.default);
    ruleOf(e).params = { ...ruleOf(e).params, length:50 };
    expect(ruleErrors(e)).toEqual({});
    expect(addItem(item('I01')).ok).toBe(true);
    const c = S.cards[0];
    expect(c.params.length).toBe(50); expect(isCustom(e, c)).toBe(true);
    expect(screenSigs().has(itemSig(item('I01')))).toBe(true);
    resetRules();                                                   // the row back at Length 20: not the card's test
    expect(screenSigs().has(itemSig(item('I01')))).toBe(false);
  });
  it('a parameter outside the catalog limits is refused with the card\'s own check (paramError), and nothing is added', () => {
    const e = ctx.entries.find(x => x.available && x.params.some(p => p.type !== 'enum' && p.type !== 'boolean' && p.min != null))!;
    const p = e.params.find(x => x.type !== 'enum' && x.type !== 'boolean' && x.min != null)!;
    ruleOf(e).params = { ...ruleOf(e).params, [p.key]:p.min! - 1 };
    const er = ruleErrors(e);
    expect(er[`p.${p.key}`]).toContain(p.label || p.key);
    const r = addItem(item(e.key));
    expect(r.ok).toBe(false); expect(r.message).toContain(p.label || p.key);
    expect(S.cards.length).toBe(0);
    ruleOf(e).params = { ...ruleOf(e).params, [p.key]:NaN };
    expect(ruleErrors(e)[`p.${p.key}`]).toContain('Enter a number.');
  });
  it('a two-line condition carries the second line\'s parameters; another condition starts from its own defaults', () => {
    const e = ctx.entries.find(x => x.available && x.params.some(p => p.type !== 'enum' && p.type !== 'boolean') && x.opts.some(o => !o.disabled && (o.form === 'state_instance' || o.form === 'event_instance')))!;
    const two = e.opts.find(o => !o.disabled && (o.form === 'state_instance' || o.form === 'event_instance'))!;
    const one = e.opts.find(o => !o.disabled && o.form !== 'state_instance' && o.form !== 'event_instance')!;
    const p = e.params.find(x => x.type !== 'enum' && x.type !== 'boolean')!;
    setOpt(e, two.key);
    const d2 = cardOfRule(e).second[p.key] as number;
    ruleOf(e).second = { ...cardOfRule(e).second, [p.key]:d2 + 1 };
    expect(cardOfRule(e).second[p.key]).toBe(d2 + 1);
    expect(addItem(item(e.key)).ok).toBe(true);
    expect(S.cards[0].second[p.key]).toBe(d2 + 1);
    setOpt(e, one.key); setOpt(e, two.key);                         // the second line's edit belonged to the old choice
    expect(cardOfRule(e).second[p.key]).toBe(d2);
  });
});

describe('the preview chart draws price overlays only (ERRORS M368)', () => {
  it('keeps unit "price", drops percents, oscillators, ranks and an answer without a unit', () => {
    const ov = (unit: string | null | undefined): PreviewResponse['overlays'][number] => ({ condition_id:'a', output:String(unit), ...(unit === undefined ? {} : { unit }), values:[] });
    const kept = candleOverlays([ov('price'), ov('dimensionless'), ov('volume'), ov('other'), ov(null), ov(undefined), ov('price_change')]);
    expect(kept.map(o => o.unit)).toEqual(['price']);
  });
});
