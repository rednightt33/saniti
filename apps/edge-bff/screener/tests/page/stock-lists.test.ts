/* EXEC-SCREENER-STOCK-LISTS (user 2026-11-09, options 1A, 2, 3) on the page, outside the DOM (the pickers and chips
   in a browser are the smoke run's, tests/smoke/smoke.mjs): the fixture publication carries the lists the worker's own
   stocklists.ts builds (catalog block, rows' memberships); the page's universe view counts as the run answers (page =
   worker); saved and remembered screens round-trip the new keys through definitionOf and stateOfDefinition, and an old
   definition is unchanged; the filter groups and "Not available yet" follow the catalog; the refusals of the core are
   shown in plain words naming where and how to pass. */
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import type { CatalogResponse, Definition, UniverseResponse } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { validateUniverse } from '../../src/core/validate.ts';
import { entriesOf } from '../../src/entries.ts';
import { canonical, ctx, definitionOf, freshUniverse, S, stateOfDefinition } from '../../src/state.ts';
import { errorText, LIST_TEXT, T } from '../../src/texts.ts';
import { universeView } from '../../src/universe-view.ts';
import { fsum, naCount } from '../../src/layout/filters.ts';
import { fixtureApi, market } from '../fixture/api.ts';
import { validateContext } from '../fixture/engine.ts';
import { FLOW_CTX } from '../fixture/broker.ts';
import { FIXTURE_STOCK_LISTS } from '../fixture/stock-lists.ts';
import { STOCK_LISTS_REASONS } from '../../../../screener-worker/src/stocklists.ts';
import { internalNames } from './plain-words.ts';

const fx = fixtureApi(), none = fixtureApi({ stockLists:'none' });
let catalog: CatalogResponse, universe: UniverseResponse, bare: CatalogResponse;
beforeAll(async () => {
  const c = await fx.catalog(null), u = await fx.universe(null), b = await none.catalog(null);
  if (c.status !== 200 || u.status !== 200 || b.status !== 200) throw new Error('fixture');
  catalog = c.body; universe = u.body; bare = b.body;
});
const useCatalog = (c: CatalogResponse) => { ctx.catalog = c; ctx.entries = entriesOf(c); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e])) };
afterEach(() => { ctx.catalog = null; ctx.universe = null; ctx.entries = []; ctx.byKey = new Map(); S.universe = freshUniverse() });

const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
/** the universe as the page writes it: an empty metric_filters is left out (state.ts definitionOf) */
const { metric_filters: _none, ...WIRE } = U;
const run = async (u: Partial<Definition['universe']>) => (await fx.run({ schema_version:1, definition:{ universe:{ ...U, ...u }, conditions:[], logic:'all' } as Definition, options:{ exhaustive:true } } as any)).body;

describe('the fixture publication: the worker\'s lists over the fixture market', () => {
  it('the catalog block names each list with its stocks in the universe; members outside it are not counted', () => {
    const b = catalog.stock_lists!;
    expect(b.availability).toBe('AVAILABLE');
    expect(b.lists.map(l => l.code)).toEqual(['IHSG', 'LQ45', 'IDX30', 'IDX80', 'ISSI', 'SALIM', 'DJARUM', 'ASTRA', 'SINARMAS', 'SARATOGA', 'EMTEK', 'CT-CORP']);
    const n = (code: string) => b.lists.find(l => l.code === code)!.tickers;
    // IHSG lists IHSG itself and XOUT besides the 94 stocks; SALIM two members outside; CT-CORP none inside
    expect([n('IHSG'), n('SALIM'), n('CT-CORP')]).toEqual([universe.rows.length, 3, 0]);
    expect(FIXTURE_STOCK_LISTS && 'lists' in FIXTURE_STOCK_LISTS && FIXTURE_STOCK_LISTS.lists.find(l => l.code === 'SALIM')!.members.length).toBe(5);
    const asii = universe.rows.find(r => r.ticker === 'ASII')!, towr = universe.rows.find(r => r.ticker === 'TOWR')!;
    expect([asii.indices, asii.groups]).toEqual([['IHSG', 'LQ45', 'IDX30', 'IDX80', 'ISSI'], ['ASTRA']]);
    expect(towr.groups).toEqual(['DJARUM', 'SARATOGA']);
  });
  it('the page\'s universe view counts what the run answers (any within a kind, both across kinds, exclusions)', async () => {
    const cases: [Partial<Definition['universe']>, string[] | null][] = [
      [{ indices_in:['LQ45'], groups_in:['ASTRA'] }, ['ASII', 'UNTR']],
      [{ groups_in:['DJARUM', 'SARATOGA'] }, null],
      [{ indices_in:['IDX30'], groups_out:['SALIM', 'ASTRA'] }, null],
      [{ groups_in:['CT-CORP'] }, []],
      [{ indices_in:['ISSI'], sectors_in:['Energy'], groups_in:['SARATOGA'] }, ['ADRO']],
    ];
    for (const [u, want] of cases) {
      const v = universeView(universe.rows, { ...U, ...u }), r = await run(u);
      const page = v.rows.map(x => x.ticker).sort(), worker = (r.rows as { ticker: string }[]).map(x => x.ticker).sort();
      expect([u, page]).toEqual([u, worker]);
      expect(v.counts).toEqual(r.universe);
      if (want) expect(page).toEqual([...want].sort());
    }
    // a group's members across two groups appear once (TOWR is in DJARUM and SARATOGA)
    expect(universeView(universe.rows, { ...U, groups_in:['DJARUM', 'SARATOGA'] }).rows.filter(r => r.ticker === 'TOWR').length).toBe(1);
  });
  it('without the file: REQUIRES_DATA with the worker\'s reason, no memberships, and a list filter refused METRIC_UNAVAILABLE', async () => {
    expect(bare.stock_lists).toEqual({ availability:'REQUIRES_DATA', reason:STOCK_LISTS_REASONS.not_indexed, as_of:null, lists:[] });
    const u = await none.universe(null);
    expect(u.status === 200 && u.body.rows.every(r => r.indices === undefined)).toBe(true);
    await expect(none.run({ schema_version:1, definition:{ universe:{ ...U, indices_in:['LQ45'] }, conditions:[], logic:'all' } as Definition, options:{} } as any))
      .rejects.toMatchObject({ code:'METRIC_UNAVAILABLE', field:'definition.universe.indices_in' });
  });
});

describe('saved and remembered screens round-trip the keys (definitionOf, stateOfDefinition)', () => {
  it('a definition with index and group filters comes back as it was; empty lists are left out', () => {
    useCatalog(catalog);
    const def: Definition = { universe:{ ...WIRE, sectors_in:['Energy'], indices_in:['LQ45', 'IDX30'], indices_out:['ISSI'], groups_in:['ASTRA'], groups_out:['SALIM'] }, conditions:[], logic:'all' };
    const st = stateOfDefinition(def);
    expect([st.universe.indices_in, st.universe.indices_out, st.universe.groups_in, st.universe.groups_out]).toEqual([['LQ45', 'IDX30'], ['ISSI'], ['ASTRA'], ['SALIM']]);
    expect(canonical(definitionOf(st))).toBe(canonical(def));
    const cleared = definitionOf({ ...st, universe:{ ...st.universe, indices_in:[], indices_out:[], groups_in:[], groups_out:[] } });
    expect(Object.keys(cleared.universe).filter(k => /^(indices|groups)_/.test(k))).toEqual([]);
  });
  it('an old definition (no list keys) reads with empty lists and writes back byte for byte', () => {
    const old: Definition = { universe:{ ...WIRE, sectors_out:['Financials'] }, conditions:[], logic:'all' };
    const st = stateOfDefinition(old);
    expect([st.universe.indices_in, st.universe.groups_out]).toEqual([[], []]);
    expect(canonical(definitionOf(st))).toBe(canonical(old));
    const { metric_filters: _m, ...defaults } = UNIVERSE_DEFAULTS;
    expect(canonical(definitionOf({ universe:freshUniverse(), cards:[], logic:'all', atLeast:2 }))).toBe(canonical({ universe:defaults, conditions:[], logic:'all' }));
  });
});

describe('the filter groups and "Not available yet" follow the catalog', () => {
  it('More filters names the chosen lists by name; Not available yet lists index membership only without the lists', () => {
    useCatalog(catalog);
    S.universe = { ...freshUniverse(), indices_in:['LQ45'], groups_in:['SALIM'], groups_out:['CT-CORP'] };
    expect(fsum('index')).toEqual({ l:'Index', n:1, d:'LQ45' });
    expect(fsum('group')).toEqual({ l:'Group (konglomerasi)', n:2, d:'Salim, not CT Corp' });
    expect(fsum('index', freshUniverse()).d).toBe('All indices');
    const withLists = naCount();
    useCatalog(bare);
    expect(naCount()).toBe(withLists + 1);
    // an older worker's catalog (no block): the same row, with the page's own reason
    useCatalog({ ...bare, stock_lists:undefined } as CatalogResponse);
    expect(naCount()).toBe(withLists + 1);
  });
  it('the pickers\' words are plain', () => {
    const words = ([LIST_TEXT.INDEX, LIST_TEXT.KONGLO].flatMap(w => Object.values(w)) as string[]).concat([LIST_TEXT.hint, LIST_TEXT.rule, LIST_TEXT.groups, LIST_TEXT.asOf('2026-11-09 20:31 WIB'), LIST_TEXT.count(1), LIST_TEXT.count(45), LIST_TEXT.na, T.noIndex, ...Object.values(STOCK_LISTS_REASONS)]);
    for (const w of words) expect(internalNames(String(w)), String(w)).toEqual([]);
  });
});

describe('the refusals as the page shows them: where, how to pass, a right and a wrong example, in plain words', () => {
  const refusal = (u: Record<string, unknown>, lists = true): ScreenerError => {
    const m = market(), ctxv = validateContext(m, { flow:FLOW_CTX, groupings:[], lists:lists ? FIXTURE_STOCK_LISTS : undefined });
    try { validateUniverse({ ...U, ...u }, 'definition.universe', ctxv) } catch (e) { if (e instanceof ScreenerError) return e; throw e }
    throw new Error('expected a refusal');
  };
  const shown = (e: ScreenerError) => { const t = errorText(e.code, { field:e.field, details:e.details as Record<string, unknown>, server:e.message }); expect(internalNames(t), t).toEqual([]); return t };
  it('an unknown code names the place, the list to pick from and the right and wrong code', () => {
    expect(shown(refusal({ indices_in:['LQ45', 'LQ46'] })))
      .toBe('The universe, included indices 2: "LQ46" is not the code of an index the Screener holds. Pick it from the Index list, which shows each by its code: "LQ45" is accepted, "LQ46" is refused. Change it and run again.');
    expect(shown(refusal({ groups_out:['astra'] })))
      .toBe('The universe, excluded groups 1: "astra" is not the code of a group the Screener holds. Write it as the Group list shows it: "ASTRA" is accepted, "astra" is refused. Change it and run again.');
  });
  it('a code twice, and one both included and excluded', () => {
    expect(shown(refusal({ groups_in:['ASTRA', 'ASTRA'] }))).toBe('The universe, included groups 2: "ASTRA" is listed twice; list it once ("ASTRA" once is accepted, "ASTRA" twice is refused). Change it and run again.');
    expect(shown(refusal({ indices_in:['LQ45'], indices_out:['LQ45'] })))
      .toBe('The universe, excluded indices 1: "LQ45" is both included and excluded, which leaves no stock; keep it on one side (include "LQ45" and exclude "IHSG" is accepted; include and exclude "LQ45" is refused). Each index is either included or excluded. Change it and run again.');
  });
  it('a list filter without the lists: why, and remove it to run', () => {
    expect(shown(refusal({ groups_in:['SALIM'] }, false)))
      .toBe('The universe, included groups: index and group membership is not available yet: This publication carries no index and group lists. Switch it off or remove it to run the screen.');
  });
});

describe('the preview names the stock\'s indices and groups (user 2026-11-09 "2. A")', () => {
  it('lists each by its catalog name with its definition as the tooltip, "none" for a kind it is in no list of, nothing while the lists are unavailable', async () => {
    const { listsLine } = await import('../../src/preview.ts');
    useCatalog(catalog);
    const towr = universe.rows.find(r => r.ticker === 'TOWR')!;
    const html = listsLine(towr), name = (code: string) => catalog.stock_lists!.lists.find(l => l.code === code)!;
    expect(html).toContain(T.listsIndices); expect(html).toContain(T.listsGroups);
    for (const code of towr.groups!) expect(html).toContain(`title="${name(code).definition.replace(/"/g, '&quot;')}">${name(code).name}</span>`);
    const outside = { indices: [], groups: [] };
    expect(listsLine(outside).match(new RegExp(`>${T.listsNone}<`, 'g'))!.length).toBe(2);
    useCatalog(bare);
    expect(listsLine(towr)).toBe('');                                         // the line above says "indexes: no data"
  });
});
