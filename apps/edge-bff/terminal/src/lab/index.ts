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
