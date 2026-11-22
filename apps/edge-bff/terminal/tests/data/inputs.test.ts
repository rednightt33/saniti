// ERRORS M332 (user 2026-11-01, US10Y screenshot): an indicator is drawn only on a ticker that has every input it reads;
// the inputs come from the loaded data, the needs from the definitions (data/inputs.ts)
import { describe, expect, it } from 'vitest';
import { fits, inputsOf, needsOf, restoreList, restoreSaved, splitSaved, withParked } from '../../src/data/inputs';
import IND from '../../src/data/indRegistry.json';

const bars = (n: number) => Array.from({ length:n }, (_, i) => ({ time:`2026-01-${String(i + 1).padStart(2, '0')}`, open:1, high:2, low:0.5, close:1.5 }));
const vol = (n: number, none: boolean) => Array.from({ length:n }, (_, i) => ({ time:`2026-01-${String(i + 1).padStart(2, '0')}`, value:none ? 0 : 100, color:'', ...(none ? { none:true } : {}) }));
const later = { broker:Promise.resolve({} as any), brokerAll:Promise.resolve({} as any) };

describe('the inputs a ticker has', () => {
  it('a stock: prices, volume and its broker files', () => {
    expect([...inputsOf({ mode:'live', ohlc:bars(3), volume:vol(3, false), later })].sort()).toEqual(['C', 'H', 'L', 'O', 'V', 'flow', 'single']);
  });
  it('a bond: prices only (no volume in its files, no broker files)', () => {
    expect([...inputsOf({ mode:'live', ohlc:bars(3), volume:vol(3, true), later:undefined })].sort()).toEqual(['C', 'H', 'L', 'O', 'single']);
  });
  it('an index whose source has no volume: its broker files, no volume (the same rule, not a list of kinds)', () => {
    const have = inputsOf({ mode:'live', ohlc:bars(3), volume:vol(3, true), later });
    expect(have.has('V')).toBe(false);
    expect(have.has('flow')).toBe(true);
  });
  it('EXEC-IHSG-FLOW: an index\'s broker rows are the market aggregate, not one security\'s', () => {
    const idx = inputsOf({ mode:'live', ohlc:bars(3), volume:vol(3, true), later, index:true });
    expect(idx.has('flow')).toBe(true);
    expect(idx.has('single')).toBe(false);
    expect(fits(needsOf({ flow:true, single:true }), idx)).toBe(false);
    expect(fits(needsOf({ flow:true }), idx)).toBe(true);
    expect(needsOf({ flow:true, single:true })).toEqual(['flow', 'single']);
  });
  it('one candle with a volume is enough; the reference fixture has broker data of its own', () => {
    const v = vol(3, true); v[1] = { ...v[1], value:5, none:undefined as any };
    expect(inputsOf({ mode:'fixture', ohlc:bars(3), volume:v, later:undefined }).has('V')).toBe(true);
    expect(inputsOf({ mode:'fixture', ohlc:bars(3), volume:v, later:undefined }).has('flow')).toBe(true);
  });
});

describe('what an indicator reads', () => {
  it('the registry letters, Flow for a Flow indicator, the definition\'s own list first', () => {
    expect(needsOf({ reg:{ req:'HLCV' } })).toEqual(['H', 'L', 'C', 'V']);
    expect(needsOf({ reg:{ req:'C' } })).toEqual(['C']);
    expect(needsOf({ flow:true })).toEqual(['flow']);
    expect(needsOf({ needs:['flow'] })).toEqual(['flow']);
    expect(needsOf({})).toEqual(['C']);
  });
  it('on a bond every price-only indicator fits and every volume one does not', () => {
    const bond = new Set(['O', 'H', 'L', 'C'] as const);
    for (const r of IND as any[]) expect(fits(needsOf({ reg:r }), bond)).toBe(!/V/.test(r.req));
    expect(fits(needsOf({ flow:true }), bond)).toBe(false);
  });
});

describe('the saved list across tickers', () => {
  it('parks what this ticker cannot draw and writes it back at its place', () => {
    const saved = [{ def:'rsi' }, { def:'FL24' }, { def:'obv' }, { def:'sma' }, { def:'FL01' }];
    const ok = (o: { def: string }) => o.def === 'rsi' || o.def === 'sma';
    const { drawn, parked } = splitSaved(saved, ok);
    expect(drawn.map(o => o.def)).toEqual(['rsi', 'sma']);
    expect(withParked(drawn, parked)).toEqual(saved);
    // an indicator added on the bond page goes after the drawn ones; the parked keep their places
    expect(withParked([...drawn, { def:'ema' }], parked).map(o => o.def)).toEqual(['rsi', 'FL24', 'obv', 'sma', 'FL01', 'ema']);
    // one removed on the bond page: the parked stay
    expect(withParked([drawn[1]], parked).map(o => o.def)).toEqual(['sma', 'FL24', 'obv', 'FL01']);
  });
});

describe('restoreSaved (3f round 2 CRIT-1: a saved entry the build lacks is parked, never dropped)', () => {
  // the admin's synced layout from the lab build: a lab indicator (I_LAB) between released ones; the public build (the
  // live site) knows only the released ones. A session there saves the list; the lab build must find it unchanged.
  const saved = [{ def:'rsi', params:{ length:14 } }, { def:'I_LAB', params:{ k:3 } }, { def:'sma' }, { def:'FL24' }];
  const publicBuild = (id: string) => ['rsi', 'sma', 'FL24', 'ema'].includes(id);
  const same = <T,>(o: T) => o;
  it('parks the unknown entry at its place, so the saved list round-trips', () => {
    const { drawn, parked } = restoreSaved(saved, same, publicBuild, same, () => true);
    expect(drawn.map(o => o.def)).toEqual(['rsi', 'sma', 'FL24']);
    expect(parked).toEqual([{ at:1, o:saved[1] }]);
    expect(withParked(drawn, parked)).toEqual(saved);
  });
  it('the lab build draws it again from what the public build saved', () => {
    const fromPublic = withParked(...Object.values(restoreSaved(saved, same, publicBuild, same, () => true)) as [any, any]);
    const lab = restoreSaved(fromPublic, same, (id: string) => publicBuild(id) || id === 'I_LAB', same, () => true);
    expect(lab.drawn.map(o => o.def)).toEqual(['rsi', 'I_LAB', 'sma', 'FL24']);
    expect(lab.parked).toEqual([]);
  });
  it('is what the Terminal restores its saved list with (src/app/indicators.ts)', async () => {
    // @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
    const { readFileSync } = await import('node:fs');
    const src = readFileSync(new URL('../../src/app/indicators.ts', import.meta.url), 'utf8');
    // the whole restore is restoreList's: `parked` is its answer as it is, and the draw callback reports what add took
    // (its test-out: a filter of `parked` here, e.g. s.parked.filter(p => !!defOf(p.o.def)), dropped the lab entries
    // again and no test saw it; any logic added between the call and `parked` fails this match)
    expect(src).toMatch(/const restore = \(saved: any\[\]\) => \{\s*parked = restoreList\(saved, migrate, \(id: string\) => !!defOf\(id\), dropStale, \(o: any\) => usable\(o\.def\), \(o: any\) => \{\s*const before = list\.length;\s*try \{ return add\(o\.def, o\) != null \} catch\(e\) \{ return list\.length > before \}\s*\}\);\s*\};/);
    expect(src.match(/\bparked = /g)).toHaveLength(1);                 // nothing else rewrites the parked entries
    expect(src).not.toMatch(/filter\(o => defOf\(o\.def\)\)/);          // the old drop of an unknown entry
  });
  it('restoreList: the saved list round-trips through a public-build restore and the lab build draws it again', () => {
    const drawnBy = (build: (id: string) => boolean) => {
      const held: any[] = [];
      const parked = restoreList(saved, same, build, same, () => true, o => { held.push(o); return true });
      return { held, parked };
    };
    const pub = drawnBy(publicBuild);
    expect(pub.held.map(o => o.def)).toEqual(['rsi', 'sma', 'FL24']);
    expect(withParked(pub.held, pub.parked)).toEqual(saved);
    const lab = restoreList(withParked(pub.held, pub.parked), same, (id: string) => publicBuild(id) || id === 'I_LAB', same,
                            () => true, () => true);
    expect(lab).toEqual([]);
  });
  it('restoreList: an entry whose drawing throws is parked as saved, and the entries after it are still drawn', () => {
    // its test-out (CRIT-1 residual): one build() that threw ended the loop, and the save after it wrote the shorter list
    const held: any[] = [];
    const parked = restoreList(saved, same, publicBuild, same, () => true, o => {
      if (o.def === 'sma') throw new Error('build failed');
      held.push(o); return true;
    });
    expect(held.map(o => o.def)).toEqual(['rsi', 'FL24']);
    expect(withParked(held, parked)).toEqual(saved);
    // a draw that took the entry and then threw reports it held (the caller's list grew): kept once, not twice
    const list: any[] = [];
    const twice = restoreList(saved, same, publicBuild, same, () => true, o => {
      const before = list.length;
      try { list.push(o); if (o.def === 'sma') throw new Error('after the push'); return true } catch { return list.length > before }
    });
    expect(withParked(list, twice)).toEqual(saved);
    // a migration or preparation that throws parks the entry as it was saved
    const bad = restoreList(saved, o => { if (o.def === 'FL24') throw new Error('migrate'); return o }, publicBuild, same,
                            () => true, () => true);
    expect(bad).toEqual([{ at:1, o:saved[1] }, { at:3, o:saved[3] }]);
  });
  it('migrates first, prepares only the known, drops what is not an entry', () => {
    const migrate = (o: any) => o.def === 'ma' ? { ...o, def:'sma' } : o;
    const prepare = (o: any) => ({ ...o, prepared:true });
    const { drawn, parked } = restoreSaved([{ def:'ma' }, { def:'I_LAB' }, null, 'x', { def:7 }], migrate, publicBuild, prepare,
      () => true);
    expect(drawn).toEqual([{ def:'sma', prepared:true }]);
    expect(parked).toEqual([{ at:1, o:{ def:'I_LAB' } }]);
  });
});

describe('failAll (3f SERVE-4: the Terminal worker\'s error ends every waiting stage)', () => {
  it('rejects each stage of each waiting job with the error and empties the map', async () => {
    const { failAll } = await import('../../src/data/live');
    const seen: unknown[] = [];
    const stage = () => [() => {}, (e: unknown) => seen.push(e)] as [(v: any) => void, (e: any) => void];
    const w = new Map([[1, { price:stage(), broker:stage() }], [2, { events:stage() }]]);
    const err = new Error('worker failed');
    failAll(w, err);
    expect(seen).toEqual([err, err, err]);
    expect(w.size).toBe(0);
  });
  it('is the worker\'s error handler (src/data/live.ts)', async () => {
    // @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
    const { readFileSync } = await import('node:fs');
    const src = readFileSync(new URL('../../src/data/live.ts', import.meta.url), 'utf8');
    expect(src).toMatch(/worker\.onerror = \(ev: ErrorEvent\) => \{[^}]*failAll\(waiting,/);
  });
});
