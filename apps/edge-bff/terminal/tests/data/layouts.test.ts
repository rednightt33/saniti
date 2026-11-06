/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06): what a chart layout holds, and that every stored setting of the page is placed
   on one side (part of a layout, or listed as not part of one) */
import { describe, expect, it } from 'vitest';
import { LAYOUT_KEYS, NOT_LAYOUT, applyState, canonical, snapshotOf, summaryOf } from '../../src/app/layouts';

const SOURCES = import.meta.glob('../../src/**/*.ts', { query:'?raw', import:'default', eager:true }) as Record<string, string>;

describe('layout settings', () => {
  it('every stored setting in the source is a layout setting or listed as not one', () => {
    const found = new Set<string>();
    for (const [f, text] of Object.entries(SOURCES)) {
      if (f.endsWith('/app/layouts.ts')) continue;
      for (const m of text.matchAll(/[`'"](ml\.[A-Za-z0-9_.]*)/g)) found.add(m[1]);
    }
    expect(found.size).toBeGreaterThan(20);
    const placed = (k: string) => (LAYOUT_KEYS as readonly string[]).includes(k) || NOT_LAYOUT.some(p => k.startsWith(p) || p.startsWith(k));
    expect([...found].filter(k => !placed(k))).toEqual([]);
  });
  it('no setting is on both sides', () => {
    expect(LAYOUT_KEYS.filter(k => NOT_LAYOUT.some(p => k.startsWith(p)))).toEqual([]);
  });
  it('a snapshot holds only the layout settings that are set', () => {
    const ls: Record<string, string> = { 'ml.ind.v1':'[]', 'ml.tf':'W', 'ml.symbol':'BBRI', 'ml.flow.h':'', 'ml.draw.line':'ray' };
    expect(snapshotOf(k => ls[k] ?? null)).toEqual({ 'ml.ind.v1':'[]', 'ml.tf':'W' });
  });
  it('opening a layout writes its settings and resets the ones it does not hold, never the ticker', () => {
    const ls: Record<string, string> = { 'ml.symbol':'BBRI', 'ml.tf':'W', 'ml.chart.style':'line', 'ml.drawings.BBRI':'[1]' };
    applyState({ 'ml.ind.v1':'[{"def":"FL12"}]', 'ml.symbol':'TLKM', 'other':'x' }, (k, v) => { ls[k] = v }, k => { delete ls[k] });
    expect(ls).toEqual({ 'ml.symbol':'BBRI', 'ml.ind.v1':'[{"def":"FL12"}]', 'ml.drawings.BBRI':'[1]' });
  });
  it('the unsaved-changes check ignores key order and non-layout keys', () => {
    expect(canonical({ 'ml.tf':'D', 'ml.ind.v1':'[]' })).toBe(canonical({ 'ml.ind.v1':'[]', 'ml.tf':'D', 'ml.symbol':'X' }));
    expect(canonical({ 'ml.tf':'D' })).not.toBe(canonical({ 'ml.tf':'W' }));
  });
  it('the summary names the timeframe and the number of indicators', () => {
    expect(summaryOf({})).toBe('D · 0 indicators');
    expect(summaryOf({ 'ml.tf':'1h', 'ml.ind.v1':'[{"def":"a"}]' })).toBe('1H · 1 indicator');
    expect(summaryOf({ 'ml.tf':'W', 'ml.ind.v1':'not json' })).toBe('W · 0 indicators');
  });
});
