// EXEC-IHSG-FLOW, EXEC-TERMINAL-IND-EDIT (user 2026-11-05: "Ok, masukan exec"): an index has no lots, so no Flow
// indicator offers Lot on an index, and a saved Lot reads as Rupiah. Derived from every select's options, not by id.
import { describe, expect, it } from 'vitest';
import { FLOW_REG, offeredOptions, withoutLot } from '../../src/app/flowIndicators';

describe('Lot on an index', () => {
  const withLot = FLOW_REG.indicators.filter(r => r.params.some(q => q.kind === 'select' && (q.options || []).some(o => o[0] === 'lot')));
  it('every indicator with a Lot choice has another choice to fall back to', () => {
    expect(withLot.map(r => r.id).length).toBeGreaterThan(0);
    for (const r of withLot) for (const q of r.params.filter(q => q.kind === 'select'))
      expect(offeredOptions(q, true).every(o => o[0] !== 'lot'), `${r.id}.${q.key}`).toBe(true);
  });
  it('a stock keeps Lot; an index turns a saved Lot into the next choice', () => {
    for (const r of withLot) {
      const q = r.params.find(q => q.kind === 'select' && (q.options || []).some(o => o[0] === 'lot'))!;
      expect(offeredOptions(q, false).some(o => o[0] === 'lot'), r.id).toBe(true);
      const p = withoutLot(r.params, { [q.key]:'lot' }, true);
      expect(p[q.key], r.id).not.toBe('lot');
      expect(p[q.key], r.id).toBe('value');
    }
  });
});
