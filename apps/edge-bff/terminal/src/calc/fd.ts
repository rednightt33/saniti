/* The Foreign × Domestic figures as shown and their quadrants (EXEC-BROKER-INV-PANEL, EXEC-QA5-FIX F1-F3). One formula for
   the right panel's map, the F×D window and the Flow indicators FL49/FL50 (calc/flow.ts). It lives in calc/ because the
   screener-worker and backtest-worker images copy this folder only: a formula the calculations import must sit here
   (ERRORS M405: calc/flow.ts importing data/brokerAgg.ts stopped the screener-worker from starting). Pure: no imports. */
/** the map's four quadrants by the signs of the foreign (x) and domestic (y) contributions; 0 counts as the positive side */
/* QA round 3 (agent 5 M4, the open Low "quadrant names without a minimum"): a part that shows as 0.00% (under FD_FLAT
   percentage points either way) is flat, not a direction; both flat is "No net flow", one flat names the other side only.
   x foreign, y domestic, in % of total buy value. EXEC-QA5-FIX (QA 2026-11-07, F1-F3): the map shows two decimals, as Top
   brokers' verdict, and the flat band is derived from that precision */
export const FD_DP = 2;
export const FD_FLAT = 0.5 / 10 ** FD_DP;
const rd = (v: number) => { const r = Math.round(v * 10 ** FD_DP) / 10 ** FD_DP; return r === 0 ? 0 : r };
/** the figures as shown: each rounded to FD_DP decimals, the verdict as Top brokers rounds it, and the two parts adjusted
    by the largest remainder so that Foreign + Domestic = Verdict on screen too (a rounding never changes a sum) */
export function fdShown(x: number, y: number, r = x + y): { x: number; y: number; r: number } {
  const R = rd(r); let X = rd(x), Y = rd(y);
  const gap = Math.round((R - X - Y) * 10 ** FD_DP);           // whole steps of 0.01 still missing (−1, 0 or +1)
  if (gap) { const ex = x - X, ey = y - Y, step = gap / 10 ** FD_DP;   // give the step to the part rounded furthest the other way
    if ((gap > 0 ? ex >= ey : ex <= ey)) X = rd(X + step); else Y = rd(Y + step) }
  return { x:X, y:Y, r:R };
}
export const FD_QUADRANTS = ['Both accumulating', 'Domestic absorbing, foreign leaving', 'Foreign absorbing, domestic leaving', 'Both distributing',
  'No net flow', 'Domestic accumulating, foreign flat', 'Domestic distributing, foreign flat', 'Foreign accumulating, domestic flat',
  'Foreign distributing, domestic flat'] as const;
export const fdQuadrant = (x: number, y: number) => {
  const fx = Math.abs(x) < FD_FLAT, fy = Math.abs(y) < FD_FLAT;
  if(fx && fy) return 4;
  if(fx) return y > 0 ? 5 : 6;
  if(fy) return x > 0 ? 7 : 8;
  return x > 0 && y > 0 ? 0 : x < 0 && y > 0 ? 1 : x > 0 ? 2 : 3;
};
