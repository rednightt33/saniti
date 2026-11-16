/* TEST ONLY (Stage D, D5): the Screener catalog the backtest page's condition window lists in the smoke run and the 1:1
   check, the Screener fixture's own (apps/edge-bff/screener/tests/fixture/api.ts: the worker's view of the generated
   catalog), and the deterministic stand-in for the worker's tracks of a test card (the page never computes one: a close
   above the previous close), so the lanes have something to draw. Never part of the production bundle. */
import { fixtureApi } from '../../screener/tests/fixture/api.ts';
import type { CatalogResponse } from '../../screener/src/core/contract.ts';
import type { Catalog } from '../src/core/contract.ts';
import FLOW_REGISTRY from '../../terminal/src/data/flowRegistry.json' with { type: 'json' };
import { FLOW_BY_ID } from '../../screener/src/core/flowmetrics.ts';

let cat: Promise<CatalogResponse> | null = null;
export const screenerCatalog = (): Promise<CatalogResponse> =>
  cat ??= fixtureApi().catalog().then(r => (r as { body: CatalogResponse }).body);

/** the stand-in track of a test card: 1 where the close is above the previous close (bar 0 never) */
export const standIn = (close: ArrayLike<number>): Uint8Array => {
  const s = new Uint8Array(close.length);
  for (let i = 1; i < close.length; i++) s[i] = +(close[i] > close[i - 1]);
  return s;
};

/** the Backtest catalog's grammar part as the worker builds it (backtest-worker catalog.ts; its module reads Node files,
    so the test catalogs take this copy of its rule): a Flow indicator the Screener computes with the Terminal module is
    available, the rest not with the worker's reason; no point-in-time one (a session without the admin right, as
    edge-bff rights.py leaves them out); the refused reference kinds with the worker's reasons (grammar.ts NOT_PER_DAY) */
export function grammarCatalog(flowOn: boolean): Pick<Catalog, 'flow_indicators' | 'grammar_refusals'> {
  const off = 'Flow conditions are not available: the broker data is switched off on the backtest worker.';
  return {
    flow_indicators: (FLOW_REGISTRY as { indicators: { id: string; name: string }[] }).indicators.flatMap(r => {
      const e = FLOW_BY_ID[r.id], clean = !!e && e.compute === 'terminal' && !e.requires;
      if (e && (e.compute === 'anchored' || e.compute === 'inventory')) return [];
      const reason = !flowOn ? off : clean ? null : 'It is drawn on the Terminal only (its value is not a number per day).';
      return [{ id: r.id, name: r.name, access: 'all' as const, available: reason === null, reason, date_param: null }];
    }),
    grammar_refusals: {
      universe: 'a universe attribute is a value on the screen date only, so a backtest cannot read it on earlier days',
      xsection: 'a cross-section value ranks the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
      rank: 'a rank across stocks uses the stocks listed on the screen date, so a backtest cannot read it on earlier days without look-ahead',
    },
  };
}
