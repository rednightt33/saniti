// EXEC-FL51-TITLE (ERRORS M540; the user 2026-11-23: "M540 masukan exec untuk diperbaiki", wording "B1"): the side a
// Flow indicator's title writes comes from the registry's own options (src/data/sideWord.ts).
import { describe, expect, it } from 'vitest';
import REG from '../../src/data/flowRegistry.json';
import { sideWord, type SideOptions } from '../../src/data/sideWord';

const SIDED = (REG as any).indicators.flatMap((r: any) => r.params.filter((q: any) => q.key === 'side')
  .map((q: any) => ({ id: r.id, options: q.options as SideOptions })));
/** the fixed rule the title used before (every value but buy and both read "Sell") */
const OLD = (v: string) => v === 'buy' ? null : v === 'both' ? 'Buy & Sell' : 'Sell';

describe('the side word of a Flow indicator title', () => {
  it('FL51 Loaders: Loaders is the indicator itself, Sellers, and Loaders & Sellers', () => {
    const fl51 = SIDED.find((s: any) => s.id === 'FL51');
    expect(fl51).toBeTruthy();
    expect(sideWord(fl51.options, 'load')).toBeNull();
    expect(sideWord(fl51.options, 'sell')).toBe('Sellers');
    expect(sideWord(fl51.options, 'both')).toBe('Loaders & Sellers');
  });
  it('every buy/sell indicator of the registry keeps the words it had', () => {
    const buySell = SIDED.filter((s: any) => s.options[0][0] === 'buy');
    expect(buySell.length).toBeGreaterThanOrEqual(8);
    for (const s of buySell) for (const [v] of s.options) expect(sideWord(s.options, v), `${s.id} ${v}`).toBe(OLD(v));
  });
  it('every sided indicator of the registry writes a label of its own options, never a word it does not offer', () => {
    for (const s of SIDED) for (const [v] of s.options) {
      const w = sideWord(s.options, v);
      if (w !== null) for (const part of w.split(' & ')) expect(s.options.map((o: any) => o[1]), `${s.id} ${v}`).toContain(part);
    }
  });
  it('the title code writes the side only through sideWord (no fixed list of side words left)', () => {
    const src = Object.values(import.meta.glob('../../src/app/flowIndicators.ts', { query: '?raw', import: 'default', eager: true }))[0] as string;
    expect(src).toContain('sideWord(byKey.side?.options, p.side)');
    expect(src).not.toMatch(/'Buy & Sell'|: 'Sell'\)/);
  });
  it('no side or no options: nothing is written', () => {
    expect(sideWord(undefined, 'sell')).toBeNull();
    expect(sideWord([['buy', 'Buy']], undefined)).toBeNull();
  });
});
