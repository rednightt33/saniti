/* EXEC-PINE-INDICATORS, checker B-1 (2026-11-23): the Backtest condition window opened "Colour is one of" and "Colour
   changed" with an empty choice (a card that could not run, "Check fields"): it built the entry's default condition and
   only renamed it. A test card at a condition now holds that condition's own default choice, ready to run; over a
   public catalog with one output coded in categories (the Screener's tests/fixture/coded.ts; the coded output in the
   lab build is Alpha KAMA's colour). */
import { beforeAll, describe, expect, it } from 'vitest';
import type { CatalogResponse } from '../../screener/src/core/contract.ts';
import { entriesOf } from '../../screener/src/entries.ts';
import { cardErrors } from '../../screener/src/forms.ts';
import { CODED_DEFAULTS, codedCatalog } from '../../screener/tests/fixture/coded.ts';
import { mkTest } from '../src/grammar.ts';
import { screenerCatalog } from './screener-catalog.ts';

let coded: ReturnType<typeof codedCatalog>;
beforeAll(async () => { coded = codedCatalog(await screenerCatalog() as CatalogResponse) });

describe('a Backtest test card at a category condition', () => {
  it('holds that condition\'s default choice and is ready', () => {
    const e = entriesOf(coded.catalog).find(x => x.key === coded.key)!;
    for (const [form, def] of [['state_category', CODED_DEFAULTS.categories], ['event_category_change', CODED_DEFAULTS.changes]] as const) {
      const o = e.opts.find(x => x.form === form)!, t = mkTest(e, 'c1', o.key);
      expect(t.sc.opt, form).toBe(o.key);
      expect(t.sc.pick, form).toBe(def);
      expect(cardErrors(e, t.sc), form).toEqual({});
    }
  });
  it('a card at the entry\'s default condition holds no choice of another condition', () => {
    const e = entriesOf(coded.catalog).find(x => x.key === coded.key)!, t = mkTest(e, 'c2');
    expect(t.sc.opt).toBe(e.def.opt);
    if (!e.opts.find(o => o.key === e.def.opt)?.pick) expect(t.sc.pick).toBeUndefined();
  });
});
