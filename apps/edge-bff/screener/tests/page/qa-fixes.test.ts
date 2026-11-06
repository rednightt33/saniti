/* EXEC-SCREENER-V21 phase C, the QA fixes of run.ts (no DOM): M1 pageCardOf (a column header offers its parameter chip
   only for the page card of the same id, entry and option, never a raw card or a My metric) and M3 dataChanged (a
   DATA_VERSION_CHANGED refusal re-runs the screened definition at most once per definition and price_data pair, so a
   service that stays behind cannot loop the page). */
import { beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type { CatalogResponse, RunRequest, UniverseResponse } from '../../src/core/contract.ts';
import type { CallOpts, RunAnswer, ScreenerApi } from '../../src/api/types.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { ctx, freshUniverse, S } from '../../src/state.ts';
import { cancelRun, dataChanged, pageCardOf, screenNow, sync } from '../../src/run.ts';
import { extraReset, setColumns } from '../../src/extra-columns.ts';
import { fixtureApi } from '../fixture/api.ts';

type Call = { req: Omit<RunRequest, 'client_order'>; opts: CallOpts; resolve: (a: RunAnswer) => void };
const fx = fixtureApi();
let catalog: CatalogResponse, universe: UniverseResponse, calls: Call[] = [];
const main = () => calls.filter(c => c.opts.lane !== 'aux');
const flush = () => new Promise(ok => setTimeout(ok, 0));
const answer = async (c: Call) => { const a = await fx.run(c.req); c.resolve({ body:a.body, bytes:new Uint8Array() }); await flush() };
const card = (key: string, over = {}) => newCard(ctx.byKey.get(key)!, S.cards.map(c => c.id), over);

beforeAll(async () => {
  const c = await fx.catalog(null), u = await fx.universe(null);
  if (c.status !== 200 || u.status !== 200) throw new Error('fixture');
  catalog = c.body; universe = u.body;
});
beforeEach(() => {
  cancelRun(); calls = [];
  ctx.api = { ...fx, run:(req, opts = {}) => new Promise<RunAnswer>(resolve => { calls.push({ req, opts, resolve }) }) } as ScreenerApi;
  ctx.catalog = catalog; ctx.universe = universe; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.R = null; ctx.running = false; ctx.runError = null; ctx.refused = null; ctx.pending = false; ctx.stale = false;
  S.universe = freshUniverse(); S.cards = []; S.logic = 'all'; S.atLeast = 2; S.errors = {};
  extraReset(); setColumns([]);
});

describe('pageCardOf: a screened column maps to a page card only when it is the same condition (M1)', () => {
  it('same id, entry and option: the page card; another entry or option under the same id: none', () => {
    const rsi = card('I13', { value:30, opt:'value|rsi|lt' }); S.cards.push(rsi);
    expect(pageCardOf({ ...rsi })).toBe(rsi);
    expect(pageCardOf({ ...rsi, value:45 })).toBe(rsi);                  // a pending value change keeps the mapping
    expect(pageCardOf({ ...rsi, opt:'value|rsi|gt' })).toBeNull();       // another test
    const other = card('I01'); expect(pageCardOf({ ...other, id:rsi.id })).toBeNull();   // the id reused by another indicator
    expect(pageCardOf({ ...rsi, id:'zz' })).toBeNull();                  // removed from the page
  });
  it('never a raw card or a My metric, on either side', () => {
    const rsi = card('I13'); S.cards.push(rsi);
    expect(pageCardOf({ ...rsi, raw:{} as any })).toBeNull();
    expect(pageCardOf({ ...rsi, metric:'m1' } as any)).toBeNull();
    S.cards[0] = { ...rsi, metric:'m1' } as any;
    expect(pageCardOf({ ...rsi })).toBeNull();
  });
});

describe('dataChanged: one re-run per definition and publication pair (M3)', () => {
  it('re-runs the screened definition once; a second refusal at the same pair does not loop; cancelRun forgets', async () => {
    S.cards.push(card('I13', { value:60, opt:'value|rsi|lt' })); sync(); screenNow(); await answer(main()[0]);
    expect(main().length).toBe(1);
    expect(dataChanged()).toBe(true); expect(main().length).toBe(2);     // Retry of the screened definition
    await answer(main()[1]);
    expect(dataChanged()).toBe(false); expect(main().length).toBe(2);    // same definition, same price_data: no loop
    // a new catalog publication is a new pair: one more re-run
    ctx.catalog = { ...catalog, versions:{ ...catalog.versions, price_data:'n'.repeat(64) } };
    expect(dataChanged()).toBe(true); expect(main().length).toBe(3);
    ctx.catalog = catalog;
  });
  it('nothing before the first screen', () => { expect(dataChanged()).toBe(false); expect(calls.length).toBe(0) });
});
