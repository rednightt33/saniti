/* 3e, the example mode (ERRORS M527): the made-up stocks this suite draws so that the presets the Screener's example
   may show have matches (no market data): GCRS, whose 50-session SMA crosses above its 200-session SMA a few sessions
   before the day the example is evaluated on (Golden Cross, terminal-publisher examples.py SCREENER_PRESET), and BRKA,
   quiet for a year, then closing above its year's high two sessions before that day with a volume spike on it (brk52).
   Drawn on a universe of tests/fake-terminal.mjs (universe) relative to `end`, the index of that day in its calendar:
   example-files.ts draws them at the market's last day, example_capture.test.ts at the date it cuts the publication at
   (every row after it is changed there, so the matches are on the cut only). */

type Universe = { prices: Record<string, unknown[][]>; ref: unknown[][] };
const bar = (d: string, c: number, v: number) => [d, c, Math.round(c * 1.01), Math.round(c * 0.99), c, v];
const sma = (c: number[], i: number, len: number) => { let s = 0; for (let k = i - len + 1; k <= i; k++) s += c[k]; return s / len };

/** closes over the calendar whose last 50/200 SMA cross up to `end` lands 3 to 8 sessions before it (the turn is
    searched, so the cross lands where the preset looks: within 20 sessions) */
function crossing(n: number, end: number): number[] {
  for (let turn = end - 150; turn < end - 20; turn++) {
    const c = [...Array(n).keys()].map(i => Math.round(i < turn ? 1500 - i * 2 : (1500 - turn * 2) + (i - turn) * 9));
    const last = [...Array(end + 1).keys()].filter(i => i >= 200 && sma(c, i - 1, 50) <= sma(c, i - 1, 200) && sma(c, i, 50) > sma(c, i, 200)).pop();
    if (last !== undefined && last >= end - 8 && last <= end - 3) return c;
  }
  throw new Error('no golden cross could be drawn on the made-up calendar');
}

/** draws GCRS and BRKA into the universe (module comment); returns their tickers */
export function drawExampleStocks(u: Universe, end?: number): string[] {
  const days = (u.prices.IHSG as unknown[][]).map(r => r[0] as string), n = days.length, e = end ?? n - 1;
  if (e < 230 || e >= n) throw new Error(`the example's day must have 230 sessions before it in the calendar, not ${e}`);
  const golden = crossing(n, e);
  u.prices.GCRS = days.map((d, i) => bar(d, golden[i], 5e6));
  u.ref.push(['GCRS', 'Golden cross', 'stock', 'Industrials', 'Industrials industry']);
  u.prices.BRKA = days.map((d, i) => bar(d, Math.round(i >= e - 2 ? 530 : 500 * (1 + 0.02 * Math.sin(i / 7))), i === e ? 2e7 : 5e6));
  u.ref.push(['BRKA', 'Breakout', 'stock', 'Industrials', 'Industrials industry']);
  return ['GCRS', 'BRKA'];
}
