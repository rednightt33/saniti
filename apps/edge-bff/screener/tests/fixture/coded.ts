/* TEST ONLY (EXEC-PINE-INDICATORS, checker SC-4/C-6 of 2026-11-23): the page suites run the public build, whose registry
   holds no output coded in categories (the one that has them, Alpha KAMA's colour, is lab). This gives a copy of a
   catalog one released indicator (the first) whose first output carries three categories and the two category forms, so the
   category paths of the pages (the pick, its default, Reset, a changed condition, the operator list) run on every push. */
import type { CatalogResponse } from '../../src/core/contract.ts';

export const CODED_CATS = [{ value: 0, key: 'low', label: 'Low' }, { value: 1, key: 'mid', label: 'Middle' }, { value: 2, key: 'high', label: 'High' }];
export const CODED_DEFAULTS = { categories: 'high', changes: 'mid>high' };

/** the catalog with the first indicator's first output coded in categories; returns it, that indicator's id (its entry's key) and the output */
export function codedCatalog(catalog: CatalogResponse): { catalog: CatalogResponse; key: string; output: string } {
  const c = structuredClone(catalog) as CatalogResponse;
  const ind = c.indicators[0], out = ind.outputs[0];
  out.categories = CODED_CATS.map(x => ({ ...x }));
  out.tests = [...out.tests,
    { form: 'state_category', ops: ['gt'], labels: { gt: 'Is one of' }, defaults: { categories: CODED_DEFAULTS.categories } },
    { form: 'event_category_change', ops: ['gt'], labels: { gt: 'Changed (from → to)' }, defaults: { changes: CODED_DEFAULTS.changes } }] as never;
  return { catalog: c, key: ind.id, output: out.key };          // an indicator entry is keyed by its id (entries.ts)
}
