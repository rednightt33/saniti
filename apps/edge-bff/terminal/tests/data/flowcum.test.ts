// EXEC-TERMINAL-CUM (user 2026-10-27, ERRORS M244 C1): the Flow's cumulative line from the first visible candle, which
// gives Stockbit's F Flow. Daily nets: BMRI Foreign, Regular board, from Feature 05 (billion rupiah, 28 Sep–23 Oct 2026).
import { describe, expect, it } from 'vitest';
import { cumulativeFrom } from '../../src/app/flow';

const NET = [-241.50, -276.20, -205.94, -68.49, -66.03, 86.82, -127.23, -0.75, -190.63, -3.82, -78.66, -120.07, -35.97,
  34.26, -868.01, -113.41, -269.82, -227.42, 152.31, -43.00];                    // 28 Sep .. 23 Oct
const STOCKBIT_F_FLOW: [number, number][] = [[4, -858.17], [5, -771.35], [6, -898.58], [7, -899.33], [8, -1090],
  [9, -1090], [10, -1170], [11, -1290], [12, -1330], [13, -1290], [14, -2160], [15, -2280], [16, -2550], [17, -2770],
  [18, -2620], [19, -2660]];                                                     // index into NET → Stockbit (B)

describe('cumulative from the first visible candle', () => {
  it('starts with that session\'s net and leaves earlier sessions empty', () => {
    const c = cumulativeFrom([5, 7, -3, 2], 1);
    expect(Number.isNaN(c[0])).toBe(true);
    expect([...c.slice(1)]).toEqual([7, 4, 6]);
    expect([...cumulativeFrom([5, 7], 0)]).toEqual([5, 12]);                    // 'history': from the first session
  });
  it('gives Stockbit\'s F Flow for BMRI when the view starts on 28 Sep 2026', () => {
    const c = cumulativeFrom(NET, 0);
    // Stockbit rounds to 0.01B below 1T and to 0.01T above it
    for (const [i, v] of STOCKBIT_F_FLOW) expect(Math.abs(c[i] - v)).toBeLessThanOrEqual(Math.abs(v) >= 1000 ? 5.01 : 0.02);
  });
});
