/* EXEC-PINE-INDICATORS, checker round 1 (2026-11-23): the category choice of a card (Card.pick) on the Screener page,
   over a public catalog with one output coded in categories (tests/fixture/coded.ts):
   - a new card and a changed condition take the condition's own default (never the other condition's keys);
   - Reset to default in Customize gives the default back (SC-1: it kept the old choice);
   - the operator panel offers no output coded in categories (SC-7: a z-score of a colour code). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse } from '../../src/core/contract.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { ctx, freshUniverse, S } from '../../src/state.ts';
import { cardOfRule, resetRule, resetRules, ruleOf, setOpt } from '../../src/add-condition.ts';
import { seriesList } from '../../src/operators.ts';
import { fixtureApi } from '../fixture/api.ts';
import { CODED_DEFAULTS, codedCatalog } from '../fixture/coded.ts';

let coded: ReturnType<typeof codedCatalog>;
beforeAll(async () => {
  const c = await fixtureApi().catalog(null); if (c.status !== 200) throw new Error('fixture catalog');
  coded = codedCatalog(c.body as CatalogResponse);
});
beforeEach(() => {
  ctx.catalog = coded.catalog; ctx.entries = entriesOf(coded.catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.api = { run: () => { throw new Error('no run') } } as never; ctx.metrics = [];
  S.universe = freshUniverse(); S.cards = []; S.errors = {}; resetRules();
});
const entry = () => ctx.byKey.get(coded.key)!;
const optOfForm = (form: string) => entry().opts.find(o => o.form === form)!;

describe('a category choice belongs to its condition', () => {
  it('the entry offers both category forms, each with its own pick and default', () => {
    expect(optOfForm('state_category').pick?.default).toBe(CODED_DEFAULTS.categories);
    expect(optOfForm('event_category_change').pick?.default).toBe(CODED_DEFAULTS.changes);
  });
  it('a new card at a category condition holds that condition\'s default', () => {
    for (const [form, def] of [['state_category', CODED_DEFAULTS.categories], ['event_category_change', CODED_DEFAULTS.changes]] as const)
      expect(newCard(entry(), [], { opt: optOfForm(form).key }).pick, form).toBe(def);
  });
  it('a changed condition takes the new condition\'s default, never the old keys', () => {
    const e = entry();
    setOpt(e, optOfForm('state_category').key); ruleOf(e).pick = 'low,mid';
    setOpt(e, optOfForm('event_category_change').key);
    expect(cardOfRule(e).pick).toBe(CODED_DEFAULTS.changes);
  });
  it('Reset to default gives the condition\'s default back (SC-1), the condition kept', () => {
    const e = entry(), k = optOfForm('state_category').key;
    setOpt(e, k); ruleOf(e).pick = 'low';
    expect(cardOfRule(e).pick).toBe('low');
    resetRule(e);
    expect(ruleOf(e).opt).toBe(k);
    expect(cardOfRule(e).pick).toBe(CODED_DEFAULTS.categories);
  });
  it('the operator panel offers no output coded in categories (SC-7)', () => {
    const keys = seriesList(entry()).map(s => s.key);
    expect(keys).not.toContain(coded.output);
    expect(keys.length).toBe(coded.catalog.indicators[0].outputs.length - 1);
  });
});
