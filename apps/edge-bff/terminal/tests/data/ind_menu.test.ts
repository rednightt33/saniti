// EXEC-IND-CARDS IC1 (user go 2026-11-01): the indicator menu's rows come from the registries, grouped and searchable
import { describe, expect, it } from 'vitest';
import { MENU_HIDDEN, menuItems, visibleItems } from '../../src/app/indMenu';
import { SINGLE_SECURITY } from '../../src/app/flowIndicators';
import IND from '../../src/data/indRegistry.json';
import FLOW from '../../src/data/flowRegistry.json';

describe('indicator menu rows', () => {
  const all = menuItems(IND as any[], FLOW as any);
  it('lists every technical and Flow indicator once, plus the base volume, except the hidden ones', () => {
    expect(all.length).toBe((IND as any[]).length + (FLOW as any).indicators.length + 1 - MENU_HIDDEN.size);
    expect(new Set(all.map(i => i.id)).size).toBe(all.length);
    expect(all.find(i => i.id === 'VOL')).toMatchObject({ kind:'Base', group:'Volume' });
    expect(all.find(i => i.id === 'FL24')).toMatchObject({ kind:'Flow', group:'Bandar Balance', place:'Panel', unit:'%' });
    expect(all.find(i => i.id === 'I01')).toMatchObject({ kind:'Technical', group:'Trend', place:'Overlay' });
    // EXEC-IND-CARDS IC2: a Flow line on the price axis (FL17 Buy VWAP) and a mark under the candles (FL27) sit on the price chart
    expect(all.find(i => i.id === 'FL17')?.place).toBe('Overlay');
    expect(all.find(i => i.id === 'FL27')?.place).toBe('Overlay');
  });
  it('a bond page (prices, no volume, no broker files) has no Flow rows, no volume and no volume indicator (M332)', () => {
    const bond = menuItems(IND as any[], FLOW as any, new Set(['O', 'H', 'L', 'C'] as const));
    expect(bond.some(i => i.kind === 'Flow' || i.id === 'VOL')).toBe(false);
    const withVolume = (IND as any[]).filter(r => /V/.test(r.req)).map(r => r.id);
    expect(withVolume.length).toBeGreaterThan(0);
    expect(bond.filter(i => withVolume.includes(i.id))).toEqual([]);
    const hiddenPriceOnly = [...MENU_HIDDEN].filter(id => (IND as any[]).some(r => r.id === id && !withVolume.includes(id))).length;
    expect(bond.length).toBe((IND as any[]).length - withVolume.length - hiddenPriceOnly);       // every price-only indicator stays
  });
  it('EXEC-IHSG-FLOW: an index page hides the Flow indicators built on lots or a per-share price, keeps the rest', () => {
    const idx = menuItems(IND as any[], FLOW as any, new Set(['O', 'H', 'L', 'C', 'flow'] as const));
    const flow = idx.filter(i => i.kind === 'Flow').map(i => i.id);
    for (const id of ['FL01', 'FL03', 'FL05', 'FL06', 'FL07', 'FL08', 'FL09', 'FL13', 'FL14', 'FL15', 'FL17', 'FL18', 'FL19',
      'FL20', 'FL27', 'FL31', 'FL39']) expect(flow).not.toContain(id);
    for (const id of ['FL02', 'FL04', 'FL10', 'FL11', 'FL12', 'FL16', 'FL21', 'FL22', 'FL23', 'FL24', 'FL25', 'FL26', 'FL28',
      'FL29', 'FL30', 'FL32', 'FL33', 'FL34', 'FL37', 'FL38']) expect(flow).toContain(id);
    const hiddenFlow = [...MENU_HIDDEN].filter(id => id.startsWith('FL') && !SINGLE_SECURITY.has(id)).length;   // not counted twice
    expect(flow.length).toBe((FLOW as any).indicators.length - SINGLE_SECURITY.size - hiddenFlow);
    for (const id of ['FL42', 'FL43', 'FL44', 'FL45']) expect(flow).not.toContain(id);      // a price per share (2026-11-05)
    for (const id of ['FL40', 'FL41', 'FL46', 'FL47', 'FL48']) expect(flow).toContain(id);
  });
  it('groups, favorites and search', () => {
    expect(visibleItems(all, 'f:Bandar Balance', '', new Set()).every(i => i.group === 'Bandar Balance' && i.kind === 'Flow')).toBe(true);
    expect(visibleItems(all, 't:Volume', '', new Set())[0].id).toBe('VOL');
    expect(visibleItems(all, 'fav', '', new Set(['FL24', 'I01'])).map(i => i.id).sort()).toEqual(['FL24', 'I01']);
    // QA round 3: words match from their start; "rsi" finds RSI, not "Net Buy Persistence"; "pers" still does
    const names = (q: string) => visibleItems(all, 'all', q, new Set()).map(i => i.name);
    expect(names('rsi').some(n => /Persistence/.test(n))).toBe(false);
    expect(names('pers').some(n => /Persistence/.test(n))).toBe(true);
    expect(visibleItems(all, 'fav', 'fl24', new Set()).map(i => i.id)).toEqual(['FL24']);      // a search looks everywhere
    expect(visibleItems(all, 'all', '', new Set()).length).toBe(all.length);
  });
});

// user 2026-11-01: a filter by group type (Technical, with the base volume, or Flow) narrows every view; units read as text
import { ofKind, unitText, visibleItems as visible2, menuItems as items2 } from '../../src/app/indMenu';
import IREG from '../../src/data/indRegistry.json';
import FREG from '../../src/data/flowRegistry.json';
describe('group-type filter and unit text', () => {
  const all = items2(IREG as any[], FREG as any);
  it('Technical keeps the technical rows and the volume, Flow the Flow rows, in a group, a search and favorites', () => {
    expect(visible2(all, 'all', '', new Set(), 'Flow').every(i => i.kind === 'Flow')).toBe(true);
    expect(visible2(all, 'all', '', new Set(), 'Technical').some(i => i.kind === 'Base')).toBe(true);
    expect(visible2(all, 'all', 'balance', new Set(), 'Technical').filter(i => i.kind === 'Flow')).toEqual([]);
    expect(visible2(all, 'fav', '', new Set(['FL24', 'I13']), 'Flow').map(i => i.id)).toEqual(['FL24']);
    expect(visible2(all, 'all', '', new Set(), 'all').length).toBe(all.length);
    expect(ofKind(all.find(i => i.id === 'VOL')!, 'Flow')).toBe(false);
  });
  it('writes a unit as text', () => {
    expect([unitText('0-100'), unitText('lot|IDR'), unitText('-1..1'), unitText('%')]).toEqual(['0–100', 'lot / IDR', '−1 to 1', '%']);
    // every registry unit reads as words, never a code with underscores
    const units = [...new Set(all.map(i => i.unit))];
    expect(units.map(unitText).filter(u => /_/.test(u))).toEqual([]);
    expect([unitText('index_0_100'), unitText('percent_signed'), unitText('price_difference_nonnegative')]).toEqual(['0–100', '%', 'price change']);
  });
});

// EXEC-TERMINAL-IND-EDIT (user 2026-11-05): I37, I41 (Terminal menu only) and FL07, FL35, FL36 are not offered anywhere in
// the menu (groups, search, favorites), while their definitions stay in the registries
describe('indicators hidden from the menu', () => {
  const all = menuItems(IND as any[], FLOW as any);
  it('are the agreed ids and exist in the registries', () => {
    expect([...MENU_HIDDEN].sort()).toEqual(['FL07', 'FL35', 'FL36', 'I37', 'I41']);
    for (const id of MENU_HIDDEN) expect([...(IND as any[]), ...(FLOW as any).indicators].some(r => r.id === id), id).toBe(true);
  });
  it('appear in no group, search or favorites view', () => {
    for (const id of MENU_HIDDEN) {
      expect(all.some(i => i.id === id), id).toBe(false);
      expect(visibleItems(all, 'all', id.toLowerCase(), new Set()).some(i => i.id === id), `search ${id}`).toBe(false);
      expect(visibleItems(all, 'fav', '', new Set([id])), `favorite ${id}`).toEqual([]);
    }
    expect(visibleItems(all, 'all', 'relative volume', new Set()).map(i => i.id)).toEqual([]);
  });
});
