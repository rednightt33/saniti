/* EXEC-TERMINAL-LOOK 2 (user 2026-11-06: "hilangkan .00 decimal harusnya 1,320"; "1A": the decimals follow the
   instrument's own data, not a list): the price axis writes a price with thousands separators and as many decimals as the
   instrument's prices carry. IDX shares trade in whole Rupiah (0 decimals: 1,320), an index carries two (7,123.45), a bond
   keeps its three. Derived from the prices, so a new data source is covered without a code change. */

/** the fewest decimals (0..max) that write every price exactly; a price with more keeps `max` */
export function priceDecimals(values: Iterable<number>, max = 4): number {
  let need = 0;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    let d = need;
    while (d < max) {
      const x = Math.abs(v) * 10 ** d;
      if (Math.abs(x - Math.round(x)) <= 1e-6 * Math.max(1, x)) break;
      d++;
    }
    need = d;
    if (need >= max) return max;
  }
  return need;
}

/** a price with thousands separators and exactly `decimals` decimals: 1,320 · 7,123.45 · 4.108 */
export function priceText(v: number, decimals: number): string {
  if (!Number.isFinite(v)) return '';
  return v.toLocaleString('en-US', { minimumFractionDigits:decimals, maximumFractionDigits:decimals });
}

/** the decimals of a bar list (open, high, low, close) */
export function barDecimals(bars: { open?: number; high?: number; low?: number; close?: number }[], max = 4): number {
  function* all() { for (const b of bars) { if (b.open != null) yield b.open; if (b.high != null) yield b.high; if (b.low != null) yield b.low; if (b.close != null) yield b.close } }
  return priceDecimals(all(), max);
}
