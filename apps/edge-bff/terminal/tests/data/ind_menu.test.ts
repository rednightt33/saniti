// EXEC-IND-CARDS IC1 (user go 2026-11-01): the indicator menu's rows come from the registries, grouped and searchable
import { describe, expect, it } from 'vitest';
import { menuItems, visibleItems } from '../../src/app/indMenu';
import IND from '../../src/data/indRegistry.json';
import FLOW from '../../src/data/flowRegistry.json';

describe('indicator menu rows', () => {
  const all = menuItems(IND as any[], FLOW as any, true);
  it('lists every technical and Flow indicator once, plus the base volume', () => {
    expect(all.length).toBe((IND as any[]).length + (FLOW as any).indicators.length + 1);
    expect(new Set(all.map(i => i.id)).size).toBe(all.length);
    expect(all.find(i => i.id === 'VOL')).toMatchObject({ kind:'Base', group:'Volume' });
    expect(all.find(i => i.id === 'FL24')).toMatchObject({ kind:'Flow', group:'Bandar Balance', place:'Panel', unit:'%' });
    expect(all.find(i => i.id === 'I01')).toMatchObject({ kind:'Technical', group:'Trend', place:'Overlay' });
  });
  it('a bond page has no Flow rows (no broker data)', () => {
    expect(menuItems(IND as any[], FLOW as any, false).some(i => i.kind === 'Flow')).toBe(false);
  });
  it('groups, favorites and search', () => {
    expect(visibleItems(all, 'f:Bandar Balance', '', new Set()).every(i => i.group === 'Bandar Balance' && i.kind === 'Flow')).toBe(true);
    expect(visibleItems(all, 't:Volume', '', new Set())[0].id).toBe('VOL');
    expect(visibleItems(all, 'fav', '', new Set(['FL24', 'I01'])).map(i => i.id).sort()).toEqual(['FL24', 'I01']);
    expect(visibleItems(all, 'fav', 'fl24', new Set()).map(i => i.id)).toEqual(['FL24']);      // a search looks everywhere
    expect(visibleItems(all, 'all', '', new Set()).length).toBe(all.length);
  });
});
