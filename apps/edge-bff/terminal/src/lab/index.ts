/* 3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"; LIVE_PROMOTION.md section 3): the formulas of the items at the
   lab stage, registered into the shared formula maps before the page starts. Only the lab build reaches this module (the
   alias '@edge-lab'; the public build gets none.ts), and edge-bff serves the lab build only to the admin on the beta, so
   a lab formula is never in a file a visitor downloads (tests: shared/release-filter.mjs's proof builds, the bundle scan
   tests/test_3f_public_bundles.py). The workers, their compute threads and the registry generators register it too
   (apps/backtest-worker/loader/resolve.mjs and register.mjs).

   A lab technical indicator (INDICATOR_BETA_TO_LIVE.md, Part A; the user lifted the lab item guard on 2026-11-23):
   its defaults and its function go here, keyed as its registry entry's `key`, built with the same wrapper as the
   released ones (the first lab indicator exports `def`, `srcOf`, `SRC` and `Seg` from calc/indicators.ts):

     import { DEFAULTS, F, def, SRC, srcOf } from '../calc/indicators';
     DEFAULTS.my_key = { length: 20, source: 'close' };
     F.my_key = def('my_key', ['out'], SRC, (B, p) => ({ out: ... }));

   Its registry entry goes into data/indRegistry.json with the item at stage "lab" in catalog/releases.json; the public
   build leaves the entry out. Releasing it moves both lines into calc/indicators.ts (Part B).

   A lab Flow indicator (INDICATOR_BETA_TO_LIVE.md, "A lab Flow indicator"; built 2026-11-23, step 3 of the user's
   sequence): its registry entry comes from the spreadsheet (scripts/build_flow_registry.py) with the item at stage "lab";
   its formula goes here, registered under its id with the building blocks the released ones use:

     import { flowKit as K, registerFlow } from '../calc/flow';
     registerFlow('<its FL id>', (c, p) => ({ value: K.each(c.rows, K.W(p, 20), (a, t) => ...) }));

   registerFlow refuses an id that already has a formula. Releasing it (or putting it at preview) moves the formula into
   calc/flow.ts FLOW (terminal/tests/calc/public_formulas.test.ts and calc/flow.test.ts "registry" compute every entry
   of the public build). */
import { DEFAULTS, F, def, ema, sma, stdev, type Seg } from '../calc/indicators';

/* ---- Alpha Volatile (EXEC-PINE-INDICATORS; the user's Pine "Nic - Tail Move Indicator V2 (RAW Distance)", 2026-11-23,
   defaults from the user's screenshot: EMA 26, lookback 100, decile 9, Z 2). Causal: every value at bar t reads bars up
   to t. As the Pine:
   - distance = close - MA(close, ma_length) (EMA seeded with the SMA of its first ma_length closes, as ta.ema; or SMA);
   - upper_z / lower_z = SMA(distance, lookback_length) +/- z_multiplier x population stdev(distance, lookback_length)
     (ta.stdev, biased);
   - decile = the sorted window's value at floor(decile / 10 x n) - 1 (at least 0) of the last lookback_length distances
     (drawn only); null until the window holds lookback_length values (the Pine sorts a window that still holds na);
   - outside: distance > upper_z (above) or < lower_z (below), strict.
   Outputs for the Terminal: distance (dots, red outside the band, blue inside: `direction` -1 / 1), decile, upper_z,
   lower_z. Flags for the Screener and the Backtest (1 on the bar, else 0; null where the band is not computed yet):
   outside_up, outside_down, outside_any; back_in_up, back_in_down, back_in_any = outside (that side) on the bar
   before and inside the band on this bar (the user's "masuk kembali setelah keluar"). */
DEFAULTS.alpha_volatile = { ma_type: 'EMA', ma_length: 26, lookback_length: 100, decile: 9, z_multiplier: 2 };
const AV_OUTS = ['distance', 'decile', 'upper_z', 'lower_z', 'direction', 'outside_up', 'outside_down', 'outside_any',
  'back_in_up', 'back_in_down', 'back_in_any'];
F.alpha_volatile = def('alpha_volatile', AV_OUTS, () => 'C', (B: Seg, p) => {
  const n = B.N, L = p.lookback_length as number, dec = Math.min(10, Math.max(1, Math.floor(Number(p.decile))));
  const ma = p.ma_type === 'SMA' ? sma(B.C, p.ma_length as number) : ema(B.C, p.ma_length as number);
  const distance = ma.map((m, i) => m === null ? null : B.C[i] - m);
  const mean = sma(distance, L), sd = stdev(distance, L);
  const upper_z = mean.map((m, i) => m === null || sd[i] === null ? null : m + (p.z_multiplier as number) * (sd[i] as number));
  const lower_z = mean.map((m, i) => m === null || sd[i] === null ? null : m - (p.z_multiplier as number) * (sd[i] as number));
  const decile = distance.map((_, i) => {
    if (i < L - 1) return null;
    const w: number[] = [];
    for (let j = 0; j < L; j++) { const v = distance[i - j]; if (v === null) return null; w.push(v) }
    w.sort((a, b) => a - b);
    return w[Math.max(Math.floor((dec / 10) * w.length) - 1, 0)];
  });
  const side = (i: number): number | null => {           // 1 above the band, -1 below, 0 inside, null not computed
    const d = distance[i], u = upper_z[i], l = lower_z[i];
    return d === null || u === null || l === null ? null : d > u ? 1 : d < l ? -1 : 0;
  };
  const S = Array.from({ length: n }, (_, i) => side(i));
  const flag = (f: (s: number, prev: number | null) => boolean) => S.map((s, i) => s === null ? null : f(s, i > 0 ? S[i - 1] : null) ? 1 : 0);
  return {
    distance, decile, upper_z, lower_z,
    direction: S.map(s => s === null ? null : s === 0 ? 1 : -1),
    outside_up: flag(s => s === 1), outside_down: flag(s => s === -1), outside_any: flag(s => s !== 0),
    back_in_up: flag((s, q) => s === 0 && q === 1), back_in_down: flag((s, q) => s === 0 && q === -1),
    back_in_any: flag((s, q) => s === 0 && q !== null && q !== 0),
  };
});

/* ---- Inside Bar Detection (EXEC-PINE-INDICATORS; the user's Pine "Nic- Inside Bar Chain Break Alert (Stable & Exact)",
   2026-11-23). Causal. As the Pine:
   - ib = high <= high[1] and low >= low[1] (an equal bar counts; a day without trades counts too, the user's "1.B");
   - the first inside bar outside a compression starts one, the mother bar being the bar before it (its high and low);
     inside the compression a bar may trade beyond the mother's range while its close stays inside;
   - break_up = close > mother high, break_down = close < mother low, during a compression; either ends it.
   Flags 1 on the bar, else 0 (bar 0: 0). */
DEFAULTS.inside_bar = {};
F.inside_bar = def('inside_bar', ['ib', 'break_up', 'break_down'], () => 'HLC', (B: Seg) => {
  const n = B.N, ib: number[] = [], up: number[] = [], down: number[] = [];
  let on = false, mh = NaN, ml = NaN;
  for (let i = 0; i < n; i++) {
    const inside = i > 0 && B.H[i] <= B.H[i - 1] && B.L[i] >= B.L[i - 1];
    if (!on && inside) { mh = B.H[i - 1]; ml = B.L[i - 1]; on = true }
    const bu = on && B.C[i] > mh, bd = on && B.C[i] < ml;
    ib.push(inside ? 1 : 0); up.push(bu ? 1 : 0); down.push(bd ? 1 : 0);
    if (bu || bd) { on = false; mh = NaN; ml = NaN }
  }
  return { ib, break_up: up, break_down: down };
});

/* ---- Alpha Price Action BUY / SELL (EXEC-PINE-INDICATORS; the user's Pine "Nic - Candle A BUY" / "Nic - Candle A SELL",
   2026-11-23). Causal: on bar t only the N completed bars before it (offsets 1..N) are read, from bar N on. As the Pine:
   - BUY: Candle 1 = the lowest low (a tie: the most recent); A = the first older bar with high > Candle 1's high; B = the
     first older bar than A with high > A's high; levels = the highs of 1, A, B (null when not found);
   - SELL: Candle 1 = the highest high; A = the first older bar with low < Candle 1's low; B = older than A with low < A's
     low; levels = the lows;
   - break of a level: the source (wick: high for BUY, low for SELL; or close) beyond today's level while the source of the
     bar before was not (BUY: src > level and src[1] <= level; SELL: src < level and src[1] >= level). The Pine breaks A and
     B; break_1 follows the same rule (the user's "levelnya bisa dipilih", 1, A or B). */
function priceAction(B: Seg, p: Record<string, unknown>, buy: boolean) {
  const n = B.N, N = Math.floor(Number(p.lookback_length)), close = p.break_source === 'Close';
  const ext = buy ? B.L : B.H, opp = buy ? B.H : B.L;            // the extreme that picks Candle 1, the side its levels use
  const beyond = (a: number, b: number) => buy ? a > b : a < b;
  const src = close ? B.C : opp;
  const lv: Record<'1' | 'a' | 'b', (number | null)[]> = { '1': [], a: [], b: [] };
  for (let t = 0; t < n; t++) {
    if (t < N) { lv['1'].push(null); lv.a.push(null); lv.b.push(null); continue }
    let c1 = 1;
    for (let i = 2; i <= N; i++) if (buy ? ext[t - i] < ext[t - c1] : ext[t - i] > ext[t - c1]) c1 = i;
    const l1 = opp[t - c1];
    let a = 0; for (let i = c1 + 1; i <= N; i++) if (beyond(opp[t - i], l1)) { a = i; break }
    let b = 0; if (a) for (let i = a + 1; i <= N; i++) if (beyond(opp[t - i], opp[t - a])) { b = i; break }
    lv['1'].push(l1); lv.a.push(a ? opp[t - a] : null); lv.b.push(b ? opp[t - b] : null);
  }
  const brk = (L: (number | null)[]) => L.map((l, t) => l === null || t === 0 ? (l === null ? null : 0) : beyond(src[t], l) && !beyond(src[t - 1], l) ? 1 : 0);
  return { level_1: lv['1'], level_a: lv.a, level_b: lv.b, break_1: brk(lv['1']), break_a: brk(lv.a), break_b: brk(lv.b) };
}
const PA_OUTS = ['level_1', 'level_a', 'level_b', 'break_1', 'break_a', 'break_b'];
DEFAULTS.price_action_buy = { lookback_length: 30, break_source: 'High (wick)' };
DEFAULTS.price_action_sell = { lookback_length: 30, break_source: 'Low (wick)' };
F.price_action_buy = def('price_action_buy', PA_OUTS, () => 'HLC', (B: Seg, p) => priceAction(B, p, true));
F.price_action_sell = def('price_action_sell', PA_OUTS, () => 'HLC', (B: Seg, p) => priceAction(B, p, false));

/* ---- Alpha KAMA (EXEC-PINE-INDICATORS; the user's Pine v5 "VHF Adaptive Linear Regression KAMA", 2026-11-23).
   Translated from the original script, © simwai, under the Mozilla Public License 2.0 (https://mozilla.org/MPL/2.0/):
   this block is a translation of that work and stays under the MPL 2.0.
   Causal: the value at bar t reads the bars up to t - 1 (the script's request.security of [close[1], high[1], low[1]] on
   the chart's own timeframe), the EMA X up to t. As the Pine, step by step (t is the bar of the segment, from 0):
   - the previous bar's close, high and low, with high and low SWAPPED as the script has them (its line 109 assigns
     [close[1], high[1], low[1]] to [_close, _low, _high]); bar 0 has none;
   - smoothing (default T3, length 3, hot 1: alpha 2 / (1 + length), six EMAs each starting from 0, nz of the bar before;
     or a Hann window, every missing value read as 0; or none);
   - VHF period: noise = the running sum of |close - nz(close[1])| over kama_length bars (nz(noise[1]) - nz(diff[L]) +
     diff, from 0); VHF = (highest - lowest of the smoothed close over kama_length bars, a missing value left out) /
     noise; period = round(kama_length x VHF x 2) (kama_length itself when VHF is off);
   - KAMA (the script's kama(), an `if bar_index > period` block): on a bar where the block runs, ER = |close -
     close[period]| / the sum of |close - close[1]| over the last max(period, 1) runs of the block (0 while fewer runs
     than that, or a sum of 0), sc = (ER x (f1 - f2) + f2)^2, kama = nz(kama of the block's last run) + sc x (close -
     that); on a bar where it does not run, kama is missing and the next run continues from the last one. Pine keeps the
     history of a value inside a block per run of the block (its documented rule for functions), read the same way here;
   - linear regression (off by default): the least-squares line of the last 5 KAMA values, read 2 bars back;
   - angle = atan((KAMA - SMA(KAMA, gradient_lookback)) / ATR) in degrees, the ATR a Hann window of length
     gradient_lookback over the true range of the swapped high and low and nz(close[1]); missing where the ATR is 0;
   - colour index (the 20 colours "Red -> Green" drawn on the line) = trunc(19 x (angle + 20)) / 40 kept to 0..19;
     colour state = the index's group of 4 (0 red, 1 orange, 2 yellow, 3 yellow-green, 4 green; the user's "1a");
   - ENTER LONG = the smoothed close crosses above KAMA, KAMA crosses above its value of the bar before, and angle > 0.5;
     ENTER SHORT the opposite with angle < -0.5 (1 on the bar, else 0; missing where KAMA or the angle is);
   - EMA X = the released EMA (I02) of today's close with length ema_length (the user's "EMA X", for the Screener and
     the Backtest), seeded with the SMA of its first values (ta.ema). */
export const KAMA_PALETTE = ['#ff0000', '#ff2c00', '#fe4200', '#fc5300', '#f96200', '#f57000', '#f07e00', '#ea8a00', '#e39600',
  '#dca100', '#d3ac00', '#c9b600', '#bfc000', '#b3ca00', '#a6d400', '#97dd00', '#86e600', '#71ee00', '#54f700', '#1eff00'];
DEFAULTS.alpha_kama = { kama_length: 89, kama_factor_1: 0.66, kama_factor_2: 0.0645, smoothing_method: 'T3', smoothing_length: 3,
  vhf_adaptive: true, linear_regression: false, gradient_lookback: 14, ema_length: 20 };
type Nn = number | null;
const nz = (v: Nn) => v === null ? 0 : v;
/** the script's t3(): six EMAs from 0 (nz of the bar before), a missing input missing on its bar */
function kamaT3(x: Nn[], len: number): Nn[] {
  const a = 1, c1 = -a * a * a, c2 = 3 * a * a + 3 * a * a * a, c3 = -6 * a * a - 3 * a - 3 * a * a * a, c4 = 1 + 3 * a + a * a * a + 3 * a * a;
  const al = 2 / (1 + len), prev: Nn[] = [null, null, null, null, null, null];
  return x.map(v => {
    let inp: Nn = v;
    for (let k = 0; k < 6; k++) { const p = nz(prev[k]); prev[k] = inp === null ? null : p + al * (inp - p); inp = prev[k] }
    const [, , t2, t3, t4, t5] = prev;
    return t5 === null ? null : c1 * t5 + c2 * (t4 as number) + c3 * (t3 as number) + c4 * (t2 as number);
  });
}
/** the script's doHannWindow(): weights 1 - cos(2 pi i / (len + 1)), i = 1..len, a missing value read as 0 */
function kamaHann(x: Nn[], len: number): number[] {
  const w: number[] = []; for (let i = 1; i <= len; i++) w.push(1 - Math.cos(2 * Math.PI * i / (len + 1)));
  const coef = w.reduce((s, v) => s + v, 0);
  return x.map((_, t) => { let s = 0; for (let i = 1; i <= len; i++) s += w[i - 1] * nz(t - i + 1 >= 0 ? x[t - i + 1] : null); return coef !== 0 ? s / coef : 0 });
}
const KAMA_OUTS = ['kama', 'ema_x', 'color_index', 'color_state', 'long', 'short'];
F.alpha_kama = def('alpha_kama', KAMA_OUTS, () => 'HLC', (B: Seg, p) => {
  const n = B.N, L = p.kama_length as number, f1 = p.kama_factor_1 as number, f2 = p.kama_factor_2 as number;
  const sl = Math.max(1, Math.floor(Number(p.smoothing_length))), gl = Math.max(1, Math.floor(Number(p.gradient_lookback)));
  const prev = (a: number[]): Nn[] => a.map((_, t) => t > 0 ? a[t - 1] : null);
  const smooth = (x: Nn[]): Nn[] => p.smoothing_method === 'T3' ? kamaT3(x, sl) : p.smoothing_method === 'Hann Window' ? kamaHann(x, sl) : x;
  const cl = smooth(prev(B.C)), lo = smooth(prev(B.H)), hi = smooth(prev(B.L));          // high and low swapped, as the script
  /* VHF period */
  const period: Nn[] = new Array(n).fill(null);
  if (p.vhf_adaptive === false) period.fill(L);
  else {
    const diff: Nn[] = cl.map((c, t) => { const q = nz(t > 0 ? cl[t - 1] : null); return c === null ? null : c > q ? c - q : q - c });
    let noise: Nn = null;
    for (let t = 0; t < n; t++) {
      noise = diff[t] === null ? null : nz(noise) - nz(t - L >= 0 ? diff[t - L] : null) + (diff[t] as number);
      if (t < L - 1 || noise === null) continue;
      let h = -Infinity, l = Infinity;
      for (let j = t - L + 1; j <= t; j++) { const v = cl[j]; if (v !== null) { if (v > h) h = v; if (v < l) l = v } }
      const v = (h - l) / noise, r = Math.round(L * v * 2);
      if (h !== -Infinity && Number.isFinite(r)) period[t] = r;
    }
  }
  /* KAMA (the block runs where bar_index > period) */
  const raw: Nn[] = new Array(n).fill(null), runs: Nn[] = [];
  let last: Nn = null;
  for (let t = 0; t < n; t++) {
    const per = period[t];
    if (per === null || !(t > per)) continue;
    const c = cl[t] as number, len = Math.max(per, 1);
    runs.push(cl[t - 1] === null ? null : Math.abs(c - (cl[t - 1] as number)));
    let s: Nn = null;
    if (runs.length >= len) { s = 0; for (let j = runs.length - len; j < runs.length; j++) { const v = runs[j]; if (v === null) { s = null; break } s += v } }
    const back = cl[t - per];
    const er: Nn = s !== null && s !== 0 ? (back === null ? null : Math.abs(c - back) / s) : 0;
    last = er === null ? null : nz(last) + Math.pow(er * (f1 - f2) + f2, 2) * (c - nz(last));
    raw[t] = last;
  }
  let kama = raw;
  if (p.linear_regression === true) kama = raw.map((_, t) => {
    if (t < 4) return null;
    const y: number[] = []; for (let j = t - 4; j <= t; j++) { const v = raw[j]; if (v === null) return null; y.push(v) }
    const xm = 2, ym = y.reduce((s, v) => s + v, 0) / 5; let sxy = 0, sxx = 0;
    for (let i = 0; i < 5; i++) { sxy += (i - xm) * (y[i] - ym); sxx += (i - xm) ** 2 }
    const b = sxy / sxx; return ym + b * (5 - 1 - 2 - xm);
  });
  /* angle, colour, signals */
  const ma = sma(kama, gl);
  const tr: Nn[] = cl.map((_, t) => { const h = hi[t], l = lo[t]; if (h === null || l === null) return null; const q = nz(t > 0 ? cl[t - 1] : null); return Math.max(h - l, Math.abs(h - q), Math.abs(l - q)) });
  const atr = kamaHann(tr, gl);
  const angle: Nn[] = kama.map((k, t) => { const m = ma[t]; return k === null || m === null || atr[t] === 0 ? null : Math.atan((k - m) / atr[t]) * 180 / Math.PI });
  const color_index = angle.map(a => { if (a === null) return null; const x = Math.trunc(19 * (a + 20)); return x <= 0 ? 0 : Math.min(19, Math.floor(x / 40)) });
  const color_state = color_index.map(k => k === null ? null : Math.floor(k / 4));
  const up = (a: Nn[], b: Nn[], t: number, dn: boolean) => { const a0 = a[t], b0 = b[t], a1 = t > 0 ? a[t - 1] : null, b1 = t > 0 ? b[t - 1] : null;
    return a0 !== null && b0 !== null && a1 !== null && b1 !== null && (dn ? a0 < b0 && a1 >= b1 : a0 > b0 && a1 <= b1) };
  const kama1: Nn[] = kama.map((_, t) => t > 0 ? kama[t - 1] : null);
  const signal = (dn: boolean) => kama.map((k, t) => { const a = angle[t]; if (k === null || a === null) return null;
    return up(cl, kama, t, dn) && up(kama, kama1, t, dn) && (dn ? a < -0.5 : a > 0.5) ? 1 : 0 });
  /* EMA X is the released EMA (I02) of the close, so it equals the EMA line the user draws beside it */
  const ema_x = (F.ema(B as never, { length: p.ema_length as number, source: 'close' }) as Record<string, Nn[]>).ema;
  return { kama, ema_x, color_index, color_state, long: signal(false), short: signal(true) };
});
