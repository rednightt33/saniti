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
