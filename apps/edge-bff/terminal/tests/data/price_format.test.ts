// EXEC-TERMINAL-LOOK 2 (user 2026-11-06, "1A"): the price axis's decimals come from the instrument's own prices
import { describe, expect, it } from 'vitest';
import { barDecimals, priceDecimals, priceText } from '../../src/data/priceFormat';

describe('price decimals derived from the data', () => {
  it('whole Rupiah shares need none; an index two; a yield three', () => {
    expect(priceDecimals([1320, 1325, 2660])).toBe(0);
    expect(priceDecimals([7123.45, 7100.1, 7088])).toBe(2);
    expect(priceDecimals([4.108, 4.05])).toBe(3);
  });
  it('floating-point noise does not add decimals; non-finite values are skipped', () => {
    expect(priceDecimals([0.1 + 0.2, 7123.45 * 1])).toBe(2);
    expect(priceDecimals([NaN, Infinity, 50])).toBe(0);
  });
  it('a price with more decimals than the cap keeps the cap', () => {
    expect(priceDecimals([1 / 3], 4)).toBe(4);
  });
  it('reads every price of the bars', () => {
    expect(barDecimals([{ open:1320, high:1330, low:1310, close:1325 }])).toBe(0);
    expect(barDecimals([{ open:7000, high:7010.5, low:6990, close:7005 }])).toBe(1);
  });
});

describe('price text', () => {
  it('thousands separators, exact decimals, minus sign kept', () => {
    expect(priceText(1320, 0)).toBe('1,320');
    expect(priceText(7123.4, 2)).toBe('7,123.40');
    expect(priceText(4.1, 3)).toBe('4.100');
    expect(priceText(-1500, 0)).toBe('-1,500');
    expect(priceText(NaN, 0)).toBe('');
  });
});
