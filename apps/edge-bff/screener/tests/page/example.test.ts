/* 3e, the example mode (ERRORS M527): the Screener's example.
   - The page's own form of a definition (its cards, then the definition they send: stateOfDefinition, definitionOf)
     is the same on every preset whether taken from the preset or from that form again: the page sends a preset in that
     form (brk52's volume spike without its default length), and src/api/example.ts compares the page's run with the
     stored screen in it (pageForm), so the example answers the page's own run and nothing else.
   - src/api/example.ts answers the page from the example's files only: the catalog and universe whole, the stored run
     for the stored screen's definition, a refusal for any other, no saved item, no watchlist, every write and every
     other call refused, and nothing asked but the example's routes. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { CatalogResponse, Definition } from '../../src/core/contract.ts';
import { entriesOf } from '../../src/entries.ts';
import { canonical, ctx, definitionOf, stateOfDefinition } from '../../src/state.ts';
import { exampleApi, pageForm } from '../../src/api/example.ts';
import { fixtureApi } from '../fixture/api.ts';

const cat = ((await fixtureApi().catalog(null)) as { status: 200; body: CatalogResponse }).body;

ctx.catalog = cat; ctx.entries = entriesOf(cat); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
/** the definition the page sends for a definition it shows */
const sent = (d: Definition) => definitionOf(stateOfDefinition(d));
/** the same object with every object's keys in reverse order (another writer's key order) */
const reversed = (v: unknown): unknown => Array.isArray(v) ? v.map(reversed)
  : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).reverse().map(([k, w]) => [k, reversed(w)])) : v;

describe('a preset as the page sends it', () => {
  it('is in the page\'s own form, the same from the preset or from that form again, for every preset', () => {
    expect(cat.presets.length).toBeGreaterThan(10);
    for (const p of cat.presets) {
      expect(pageForm(sent(p.definition)), p.id).toBe(pageForm(p.definition));
      expect(canonical(sent(sent(p.definition))), p.id).toBe(canonical(sent(p.definition)));
    }
  });
});

describe('the example API of the page (src/api/example.ts)', () => {
  const brk52 = cat.presets.find(p => p.id === 'brk52')!;
  const screen = { preset: 'brk52', name: brk52.name, definition: brk52.definition };
  const run = { schema_version: 1, mode: 'screen', data: cat.data, match_count: 1, near_count: 0, rows: [{ ticker: 'BBCA' }] };
  const universe = { schema_version: 1, data: cat.data, rows: [] };
  const files: Record<string, unknown> = { 'screener-catalog': cat, 'screener-universe': universe, 'screener-screen': screen, 'screener-run': run };
  let asked: string[] = [];
  const serve = () => {
    asked = [];
    const index = { finished_at: null, as_of: '2026-10-30', files: Object.fromEntries(Object.keys(files).map(n => [n, { sha256: `sha-${n}` }])) };
    vi.stubGlobal('fetch', async (url: string) => {
      asked.push(url);
      if (url === '/api/v1/examples/screener/index') return Response.json(index);
      const m = /^\/api\/v1\/examples\/screener\/file\/([a-z0-9-]+)\?sha=(.+)$/.exec(url);
      if (m && m[1] in files && m[2] === `sha-${m[1]}`) return Response.json(files[m[1]]);
      return Response.json({ error: { code: 'NOT_HERE', message: url } }, { status: 404 });
    });
    return exampleApi();
  };
  afterEach(() => { vi.unstubAllGlobals() });

  it('opens on the stored screen and answers its run with the stored run', async () => {
    const api = serve();
    expect(await api.screen()).toEqual(screen);
    expect(await api.session()).toMatchObject({ login: 'example' });
    const c = await api.catalog(null), u = await api.universe(null);
    expect(c.status === 200 && c.body).toEqual(cat);
    expect(u.status === 200 && u.body).toEqual(universe);
    // the definition the page sends for the screen it opens (its own form, its keys in any order): the stored run
    expect((await api.run({ schema_version: 1, definition: sent(brk52.definition) })).body).toEqual(run);
    expect((await api.run({ schema_version: 1, definition: reversed(sent(brk52.definition)) as Definition })).body).toEqual(run);
    expect(await api.items('screen')).toEqual({ items: [] });
    expect(await api.watchlist()).toEqual({ tickers: [] });
    expect(asked.every(u => u.startsWith('/api/v1/examples/screener/'))).toBe(true);
    expect(asked.filter(u => u.includes('/file/screener-run')).length).toBe(1);
  });

  it('refuses another definition and every other call', async () => {
    const api = serve();
    const other = structuredClone(brk52.definition) as Definition;
    other.conditions = other.conditions.slice(0, 1);
    await expect(api.run({ schema_version: 1, definition: other })).rejects.toMatchObject({ code: 'EXAMPLE', status: 403 });
    await expect(api.run({ schema_version: 1, definition: { ...brk52.definition, logic: 'any' } })).rejects.toMatchObject({ code: 'EXAMPLE' });
    for (const call of [() => api.preview({} as never), () => api.validate(brk52.definition), () => api.counts({} as never),
                        () => api.putItem('x', {} as never), () => api.deleteItem('x'), () => api.watch('BBCA', true)])
      await expect(call()).rejects.toMatchObject({ code: 'EXAMPLE', status: 403 });
    expect(asked.every(u => u.startsWith('/api/v1/examples/screener/'))).toBe(true);
  });
});
