/* TEST ONLY (Stage D, D5): the Screener catalog the backtest page's condition window lists in the smoke run and the 1:1
   check, the Screener fixture's own (apps/edge-bff/screener/tests/fixture/api.ts: the worker's view of the generated
   catalog), and the deterministic stand-in for the worker's tracks of a test card (the page never computes one: a close
   above the previous close), so the lanes have something to draw. Never part of the production bundle. */
import { fixtureApi } from '../../screener/tests/fixture/api.ts';
import type { CatalogResponse } from '../../screener/src/core/contract.ts';

let cat: Promise<CatalogResponse> | null = null;
export const screenerCatalog = (): Promise<CatalogResponse> =>
  cat ??= fixtureApi().catalog().then(r => (r as { body: CatalogResponse }).body);

/** the stand-in track of a test card: 1 where the close is above the previous close (bar 0 never) */
export const standIn = (close: ArrayLike<number>): Uint8Array => {
  const s = new Uint8Array(close.length);
  for (let i = 1; i < close.length; i++) s[i] = +(close[i] > close[i - 1]);
  return s;
};

/** the Backtest catalog's grammar part (a copy of the worker's rule, locked by the worker's catalog-copy test) */
export { grammarCatalog } from './grammar-catalog.ts';
