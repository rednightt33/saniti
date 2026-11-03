// ERRORS M332 (user 2026-11-01, US10Y screenshot): an indicator is drawn only on a ticker that has every input it reads;
// the inputs come from the loaded data, the needs from the definitions (data/inputs.ts)
import { describe, expect, it } from 'vitest';
import { fits, inputsOf, needsOf, splitSaved, withParked } from '../../src/data/inputs';
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
