/* TEST ONLY (Stage D, D5; Agent 10, ERRORS M460 item 9): the Backtest catalog's grammar part as the worker gives it to a
   session without the admin right (apps/backtest-worker/src/catalog.ts flowIndicators and grammar.ts NOT_PER_DAY, then
   edge-bff rights.py leaves the admin entries out). The worker's module reads Node files, so the page's test builds take
   this copy of its rule; apps/backtest-worker/tests/catalog-copy.test.ts fails when the copy and the worker differ.
   Imports nothing that only a browser build can read. */
import type { Catalog } from '../src/core/contract.ts';
import FLOW_REGISTRY from '../../terminal/src/data/flowRegistry.json' with { type: 'json' };
import { FLOW_BY_ID } from '../../screener/src/core/flowmetrics.ts';

const OFF = 'Flow conditions are not available: the broker data is switched off on the backtest worker.';
/** the worker's admin-only entries: the point-in-time ones (its pit/spec.ts D_SPECS, named here because the page's
    type check would read that module; nothing in the Flow registry marks them, FL51 has no Screener formula) and FL52.
    catalog-copy.test.ts fails when this list and D_SPECS differ. */
const POINT_IN_TIME = new Set(['FL18', 'FL19', 'FL20', 'FL23', 'FL44', 'FL45', 'FL51']);
const adminOnly = (id: string) => id === 'FL52' || POINT_IN_TIME.has(id);

export function grammarCatalog(flowOn: boolean): Pick<Catalog, 'flow_indicators' | 'grammar_refusals'> {
  return {
    flow_indicators: (FLOW_REGISTRY as { indicators: { id: string; name: string }[] }).indicators.filter(r => !adminOnly(r.id)).map(r => {
      const e = FLOW_BY_ID[r.id], clean = !!e && e.compute === 'terminal' && !e.requires;
      const reason = !flowOn ? OFF : clean ? null
        : e?.requires === 'insider' ? 'It needs insider transactions with the date they were made public, which are not published yet.'
        : 'It is drawn on the Terminal only (its value is not a number per day).';
      return { id: r.id, name: r.name, access: 'all' as const, available: reason === null, reason, date_param: null };
    }),
    grammar_refusals: {
      universe: 'a universe attribute is a value on the screen date only, so a backtest cannot read it on earlier days',
      xsection: 'a cross-section value ranks the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
      rank: 'a rank across stocks uses the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
    },
  };
}
