// EXEC-FLOW-PANE-FILTERS and EXEC-TERMINAL-LOOK-2 (user go 2026-11-06): which choices each Flow indicator shows on its row,
// and what an emptied choice does
import { describe, expect, it } from 'vitest';
import { allBrokersBothSides, carriesNothing, emptyChoice, firstValueAt, PANE_FILTER_KEYS } from '../../src/app/flowIndicators';
import { menuItems, visibleItems } from '../../src/app/indMenu';
import IND from '../../src/data/indRegistry.json';
import { MENU_HIDDEN } from '../../src/app/indMenu';
import FLOW from '../../src/data/flowRegistry.json';

// an indicator with a box (FL51 Loaders, its period end 'end') offers Top N (and Show) in the box, not on its row (2026-11-08)
const keysOf = (r: any) => PANE_FILTER_KEYS.filter(k => !(r.params.some((q: any) => q.key === 'end') && k === 'top')
  && r.params.some((q: any) => q.key === k && q.kind !== 'fixed'));
const shown = (FLOW as any).indicators.filter((r: any) => !MENU_HIDDEN.has(r.id));

describe('pane-row choices derived from the registry (the final proposal)', () => {
  // EXEC-FLOW-NEW-3 (2026-11-08): FL49-FL52 add 4 (N on FL49 and FL50; Board on all four, Investor on FL51 and FL52)
  it('27 with a broker scope get Broker, N and Rank by; 9 more get N without a scope; Board 44, Investor 43', () => {
    expect(shown.length).toBe(49);
    expect(shown.filter((r: any) => keysOf(r).includes('scope')).length).toBe(27);
    expect(shown.filter((r: any) => keysOf(r).includes('scope')).every((r: any) => ['top', 'rank', 'brokers'].every(k => keysOf(r).includes(k as any)))).toBe(true);
    expect(shown.filter((r: any) => keysOf(r).includes('top') && !keysOf(r).includes('scope')).map((r: any) => r.id).sort())
      .toEqual(['FL15', 'FL16', 'FL24', 'FL25', 'FL29', 'FL42', 'FL48', 'FL49', 'FL50']);
    expect(shown.filter((r: any) => keysOf(r).includes('boards')).length).toBe(44);
    expect(shown.filter((r: any) => keysOf(r).includes('investors')).length).toBe(43);
  });
  it('no controls on FL27, FL28, FL31 and the two-sided FL46; Broker Inventory keeps brokers, board, investor', () => {
    for (const id of ['FL27', 'FL28', 'FL31', 'FL46']) expect(keysOf(shown.find((r: any) => r.id === id))).toEqual([]);
    expect(keysOf(shown.find((r: any) => r.id === 'FL23'))).toEqual(['brokers', 'boards', 'investors']);
  });
});

describe('an emptied choice', () => {
  it('names what to choose; a broker list hidden by the scope does not count', () => {
    expect(emptyChoice({ brokers:[], boards:['Regular'], investors:['Foreign'] })).toBe('Choose at least one broker');      // FL23
    expect(emptyChoice({ scope:'selected', brokers:[] })).toBe('Choose at least one broker');
    expect(emptyChoice({ scope:'topn', brokers:[], boards:['Regular'] })).toBe('');                                            // N and Rank decide
    expect(emptyChoice({ scope:'all', brokers:[], boards:[] })).toBe('Choose at least one board');
    expect(emptyChoice({ boards:['Nego'], investors:[] })).toBe('Choose at least one investor');
    expect(emptyChoice({ brokers:'auto_c' })).toBe('');
  });
});

describe('QA fixes (2026-11-06)', () => {
  it('M2: every broker over both investor types is the whole market; its net carries nothing', () => {
    expect(allBrokersBothSides({ scope:'all', investors:['Foreign', 'Domestic'] })).toBe(true);
    expect(allBrokersBothSides({ scope:'all' })).toBe(true);
    expect(allBrokersBothSides({ scope:'all', investors:['Foreign'] })).toBe(false);
    expect(allBrokersBothSides({ scope:'topn', investors:['Foreign', 'Domestic'] })).toBe(false);
    expect(carriesNothing({ value:[null, 0, 0, null] })).toBe(true);
    expect(carriesNothing({ value:[null, 0, 0.5] })).toBe(false);
    expect(carriesNothing({ buy:[0, 0], sell:[null, 0] })).toBe(true);
    expect(carriesNothing({})).toBe(false);
    // R2-M1: a flat percentile (50 everywhere) carries nothing; an empty result (short history) is not this case
    expect(carriesNothing({ value:[null, 50, 50, 50] })).toBe(true);
    expect(carriesNothing({ value:[null, null, null] })).toBe(false);
    expect(carriesNothing({ value:[null, 12.5, 13] })).toBe(false);
    // R2-M2: the first candle with a value, across outputs
    expect(firstValueAt({ a:[null, null, 3], b:[null, 1, null] })).toBe(1);
    expect(firstValueAt({ a:[null, null] })).toBe(-1);
  });
  it('M9: the search finds an indicator by its short name, the exact one first', () => {
    const items = menuItems(IND as any[], FLOW as any);
    expect(visibleItems(items, 'all', 'RSI', new Set())[0].name).toBe('Relative Strength Index');
    expect(visibleItems(items, 'all', 'ATR', new Set()).some(i => i.name === 'Average True Range')).toBe(true);
  });
});
