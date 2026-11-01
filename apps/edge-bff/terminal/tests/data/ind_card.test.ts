// EXEC-IND-CARDS IC2 (user go 2026-11-01): the card's pure parts. Its numbers come from the indicator's definition and the
// explainers (tests/calc/explain.test.ts: equal to the chart); here: one number style from the unit, the formula line's
// terms as whole words, and a notes entry (formula, source) for every indicator of the registries.
import { describe, expect, it } from 'vitest';
import { cardFormat, termWords } from '../../src/app/indCard';
import NOTES from '../../src/data/indNotes.json';
import IND from '../../src/data/indRegistry.json';
import FLOW from '../../src/data/flowRegistry.json';

describe('indicator card', () => {
  it('writes numbers by the EDGE Design Spec v1.2 rules, chosen from the unit', () => {
    expect(cardFormat('%')(-5.6221)).toBe('−5.6%');                 // indicator: 1 decimal, minus U+2212
    expect(cardFormat('percent_signed')(12.5)).toBe('12.5%');
    expect(cardFormat('IDR')(2.83e12)).toBe('Rp 2.8T');             // B = miliar, T = triliun, never "M"
    expect(cardFormat('IDR')(555.18e9)).toBe('Rp 555.2B');
    expect(cardFormat('price')(5509)).toBe('5,509');                 // a whole value: no decimals
    expect(cardFormat('price')(5509.04)).toBe('5,509.0');
    expect(cardFormat('ratio')(0.0423)).toBe('0.0423×');             // a small value keeps three significant digits
    expect(cardFormat('x')(4)).toBe('4.00×');
    expect(cardFormat('index_0_100')(48.21)).toBe('48.2');           // "RSI 48.2"
    expect(cardFormat('flag')(1)).toBe('1');
  });
  it('fills the formula line by whole terms (a term n never matches inside another word)', () => {
    const re = termWords([{ key:'n', label:'', value:20, unit:'count' }, { key:'SUM', label:'', value:1, unit:'price' }]);
    expect('SUM ÷ n'.replace(re, k => `[${k}]`)).toBe('[SUM] ÷ [n]');
    const re2 = termWords([{ key:'EMA₋₁', label:'', value:1, unit:'price' }, { key:'α', label:'', value:.1, unit:'num' }, { key:'src', label:'', value:1, unit:'price' }]);
    expect('EMA₋₁ + α × (src − EMA₋₁)'.replace(re2, k => `[${k}]`)).toBe('[EMA₋₁] + [α] × ([src] − [EMA₋₁])');
  });
  it('has a formula for every indicator of both registries (scripts/build_indicator_notes.py)', () => {
    expect((IND as any[]).filter(r => !(NOTES.technical as any)[r.id]?.formula).map(r => r.id)).toEqual([]);
    expect((FLOW as any).indicators.filter((r: any) => !(NOTES.flow as any)[r.id]?.formula).map((r: any) => r.id)).toEqual([]);
  });
});
