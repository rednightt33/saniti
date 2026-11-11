// EDGE Design Spec v1.2 section 6 "Format angka" (user 2026-11-01): one set of number rules for every place an indicator
// appears (legend, pane axis, card).
import { describe, expect, it } from 'vitest';
import { change, idr, indicator, num, pctLevel, price, ratio, smart, titled } from '../../src/data/specFormat';

describe('Design Spec v1.2 numbers', () => {
  it('en-US separators and the minus sign U+2212', () => {
    expect(num(-1234.5, 1)).toBe('−1,234.5');
    expect(price(9875)).toBe('9,875');
  });
  it('change: sign and 2 decimals', () => {
    expect(change(1.234)).toBe('+1.23%');
    expect(change(-0.4)).toBe('−0.40%');
    expect(change(0)).toBe('0.00%');
  });
  it('transaction value in B (miliar) or T (triliun), never M', () => {
    expect(idr(96.3e9)).toBe('Rp 96.3B');
    expect(idr(7.71e12)).toBe('Rp 7.7T');
    expect(idr(1217e12)).toBe('Rp 1,217T');
    expect(idr(-4.41e12)).toBe('−Rp 4.4T');
    expect(idr(87_500_000)).toBe('Rp 87,500,000');
  });
  it('ratio with ×, indicator with 1 decimal, a small value with three significant digits', () => {
    expect(ratio(15.2)).toBe('15.20×');
    expect(indicator(48.21)).toBe('48.2');
    expect(indicator(0.00042)).toBe('0.00042');
    expect(pctLevel(-5.62)).toBe('−5.6%');
    expect(smart(-0.0123, 1)).toBe('−0.0123');
  });
  it('parameters in parentheses: RSI (14)', () => {
    expect(titled('RSI', [14, 'close'])).toBe('RSI (14, close)');
    expect(titled('OBV', [])).toBe('OBV');
    expect(titled('Top Brokers · %', ['Top 3', '10D'])).toBe('Top Brokers · % (Top 3, 10D)');
  });
});
