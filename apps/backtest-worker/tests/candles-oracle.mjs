/* An independent recomputation of the 20 candlestick patterns (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/
   P6_CANDLES.md section 4), written from the definitions in plain code: one function per pattern, its own tick table,
   its own trend and average, no import of the core and no use of candle-registry.json's rules. Used only as the test
   oracle of candles.ts (tests/candles.test.ts). p = the pattern's parameters, complete. Plain JS. */

// IDX price fractions since 2016-01-06 (Rp 1 below 200, 2 below 500, 5 below 2,000, 10 below 5,000, 25 from 5,000)
export const tick = price => price < 200 ? 1 : price < 500 ? 2 : price < 2000 ? 5 : price < 5000 ? 10 : 25;
export function ticks(a, b) {
  let lo = Math.min(a, b), hi = Math.max(a, b), n = 0;
  for (const [from, to, t] of [[0, 200, 1], [200, 500, 2], [500, 2000, 5], [2000, 5000, 10], [5000, Infinity, 25]]) {
    const x = Math.max(lo, from), y = Math.min(hi, to);
    if (y > x) n += (y - x) / t;
  }
  return n;
}
const fin = v => typeof v === 'number' && Number.isFinite(v);

/** The oracle's 0/1 signal of pattern `id` on bars {O,H,L,C,V} with complete parameters p. */
export function oracle(id, bars, p) {
  const n = bars.C.length, out = new Uint8Array(n), B = DEF[id];
  const candle = i => {
    const o = bars.O[i], h = bars.H[i], l = bars.L[i], c = bars.C[i], v = bars.V[i];
    if (![o, h, l, c, v].every(fin) || !(o > 0 && h > 0 && l > 0 && c > 0 && v > 0)) return null;   // missing or no trade
    if (h < Math.max(o, c) || l > Math.min(o, c)) return null;
    if (ticks(l, h) < p.min_range_ticks) return null;
    return { o, h, l, c, rng: h - l, body: Math.abs(c - o), up: h - Math.max(o, c), lo: Math.min(o, c) - l, top: Math.max(o, c), bot: Math.min(o, c), white: c > o, black: c < o };
  };
  const close = j => fin(bars.C[j]) ? bars.C[j] : NaN;
  const trendOk = (j, dir) => {
    if (p.trend === 'none') return true;
    const N = p.trend_length;
    if (p.trend === 'change') { if (j - N < 0) return false; return dir === 'down' ? close(j) < close(j - N) : close(j) > close(j - N) }
    if (j - N + 1 < 0) return false;
    let s = 0; for (let t = j - N + 1; t <= j; t++) s += close(t);
    return dir === 'down' ? N * close(j) < s : N * close(j) > s;
  };
  const avgBody = j => {                                     // mean |close - open| of bars j-M+1 .. j
    const M = p.body_avg_length;
    if (j - M + 1 < 0) return NaN;
    let s = 0;
    for (let t = j - M + 1; t <= j; t++) { if (!fin(bars.C[t]) || !fin(bars.O[t])) return NaN; s += Math.abs(bars.C[t] - bars.O[t]) }
    return s / M;
  };
  for (let i = 1; i < n; i++) {
    const first = i - B.bars + 1;
    if (first < 0) continue;
    const k = [];
    for (let t = first; t <= i; t++) k.push(candle(t));
    if (k.some(x => x === null)) continue;
    if (!trendOk(first - 1, B.trend)) continue;
    out[i] = +B.test(k, p, avgBody(first - 1));
  }
  return out;
}

const pct = (x, share, of) => 100 * x <= share * of;                // x is at most share % of `of`
const pctMin = (x, share, of) => 100 * x >= share * of;
const DEF = {
  hammer: { bars: 1, trend: 'down', test: ([a], p) => pct(a.body, p.body_max_pct, a.rng) && a.lo >= p.shadow_ratio * a.body && pct(a.up, p.short_shadow_pct, a.rng) },
  hanging_man: { bars: 1, trend: 'up', test: ([a], p) => pct(a.body, p.body_max_pct, a.rng) && a.lo >= p.shadow_ratio * a.body && pct(a.up, p.short_shadow_pct, a.rng) },
  inverted_hammer: { bars: 1, trend: 'down', test: ([a], p) => pct(a.body, p.body_max_pct, a.rng) && a.up >= p.shadow_ratio * a.body && pct(a.lo, p.short_shadow_pct, a.rng) },
  shooting_star: { bars: 1, trend: 'up', test: ([a], p) => pct(a.body, p.body_max_pct, a.rng) && a.up >= p.shadow_ratio * a.body && pct(a.lo, p.short_shadow_pct, a.rng) },
  dragonfly_doji: { bars: 1, trend: 'down', test: ([a], p) => pct(a.body, p.doji_body_pct, a.rng) && pct(a.up, p.short_shadow_pct, a.rng) },
  gravestone_doji: { bars: 1, trend: 'up', test: ([a], p) => pct(a.body, p.doji_body_pct, a.rng) && pct(a.lo, p.short_shadow_pct, a.rng) },
  bullish_marubozu: { bars: 1, trend: 'down', test: ([a], p, avg) => a.white && pctMin(a.body, p.body_min_pct, a.rng) && a.body >= p.long_body * avg },
  bearish_marubozu: { bars: 1, trend: 'up', test: ([a], p, avg) => a.black && pctMin(a.body, p.body_min_pct, a.rng) && a.body >= p.long_body * avg },
  bullish_engulfing: { bars: 2, trend: 'down', test: ([a, b]) => a.black && b.white && b.o <= a.c && b.c >= a.o && b.body > a.body },
  bearish_engulfing: { bars: 2, trend: 'up', test: ([a, b]) => a.white && b.black && b.o >= a.c && b.c <= a.o && b.body > a.body },
  bullish_harami: { bars: 2, trend: 'down', test: ([a, b], p, avg) => a.black && a.body >= p.long_body * avg && b.top <= a.o && b.bot >= a.c && pct(b.body, p.inside_max_pct, a.body) },
  bearish_harami: { bars: 2, trend: 'up', test: ([a, b], p, avg) => a.white && a.body >= p.long_body * avg && b.top <= a.c && b.bot >= a.o && pct(b.body, p.inside_max_pct, a.body) },
  piercing_line: { bars: 2, trend: 'down', test: ([a, b], p, avg) => a.black && a.body >= p.long_body * avg && b.white
    && (p.open_beyond === 'range' ? b.o < a.l : b.o < a.c) && pctMin(b.c - a.c, p.penetration_pct, a.body) && b.c < a.o },
  dark_cloud_cover: { bars: 2, trend: 'up', test: ([a, b], p, avg) => a.white && a.body >= p.long_body * avg && b.black
    && (p.open_beyond === 'range' ? b.o > a.h : b.o > a.c) && pctMin(a.c - b.c, p.penetration_pct, a.body) && b.c > a.o },
  tweezer_bottom: { bars: 2, trend: 'down', test: ([a, b], p) => a.black && b.white && ticks(a.l, b.l) <= p.tolerance_ticks },
  tweezer_top: { bars: 2, trend: 'up', test: ([a, b], p) => a.white && b.black && ticks(a.h, b.h) <= p.tolerance_ticks },
  morning_star: { bars: 3, trend: 'down', test: ([a, s, b], p, avg) => a.black && a.body >= p.long_body * avg && pct(s.body, p.star_body_pct, a.body)
    && pct(s.top - a.c, p.star_overlap_pct, a.body) && b.white && pctMin(b.c - a.c, p.penetration_pct, a.body) },
  evening_star: { bars: 3, trend: 'up', test: ([a, s, b], p, avg) => a.white && a.body >= p.long_body * avg && pct(s.body, p.star_body_pct, a.body)
    && pct(a.c - s.bot, p.star_overlap_pct, a.body) && b.black && pctMin(a.c - b.c, p.penetration_pct, a.body) },
  three_white_soldiers: { bars: 3, trend: 'down', test: (k, p, avg) => k.every(x => x.white && pctMin(x.body, p.body_min_pct, x.rng) && pct(x.up, p.short_shadow_pct, x.rng) && x.body >= p.long_body * avg)
    && [1, 2].every(j => k[j].o >= k[j - 1].o && k[j].o <= k[j - 1].c && k[j].c > k[j - 1].c) },
  three_black_crows: { bars: 3, trend: 'up', test: (k, p, avg) => k.every(x => x.black && pctMin(x.body, p.body_min_pct, x.rng) && pct(x.lo, p.short_shadow_pct, x.rng) && x.body >= p.long_body * avg)
    && [1, 2].every(j => k[j].o <= k[j - 1].o && k[j].o >= k[j - 1].c && k[j].c < k[j - 1].c) },
};
export const ORACLE_IDS = Object.keys(DEF);
