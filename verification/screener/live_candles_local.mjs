/* Offline proof of the unit C live check (live_candles_dev.py + live_candles_compute.mjs) without dev, Railway or the
   database (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/LIVE_CHECK_DEV.md "Unit C").

   A. The independent implementation (live_candles_compute.mjs detect) against the Backtest core's candles.ts, bar for
      bar: the eight Terminal parity fixtures at the live check's parameter sets; random bars in every price band with
      adjusted (fractional) prices, days without trades, one-price days with trades, missing values and inconsistent
      bars, at default, minimum, maximum, random and loose parameters; hand-derived boundary cases written from
      P6_CANDLES.md's words (evaluated by the independent code alone); and the frequency table of P6_CANDLES.md
      section 5 on the fixture stocks.
   B. A local stack: the fake terminal-api of apps/screener-worker/tests (publisher-format files: the fixture stocks and
      synthetic ones near each price band boundary, an illiquid one, one with dropped rows and missing volumes, one
      with a stock split after the adjusted-history boundary, one with adjusted fractional prices, a stale one; 60
      broker days), the real screener-worker (createApp, the production core) on it, and a stand-in for edge-bff's
      public routes (sign-in with a session cookie, the CSRF token and Origin on writes, catalog, universe, run relayed
      to the worker with its key and owner tag, POST /api/terminal/v1/bundle answering each stock's price pack from the
      same rows, the presigned file). live_candles_dev.py --base-url must exit 0 with every comparison equal, use only
      the read routes, and write no secret (password, session cookie, CSRF token) to its output or its OUT files.
   C. Injected faults the check must catch: the Terminal's bars changed for one stock (exit 1, mismatches on that stock
      only); one Screener cell changed (exit 1, that cell only); the publication moved during the check (exit 2); the
      Terminal quota refuses a bundle (exit 3); a compute_budget refusal of one screen (exit 4, the rest equal).
   Run from the repository root (Node 22.6+ and python3):
     node --experimental-strip-types --no-warnings=ExperimentalWarning --import ./apps/backtest-worker/loader/register.mjs \
       verification/screener/live_candles_local.mjs [OUT]
   OUT (default: a new directory under the system temp directory) receives b/, c1/ to c5/ and summary.json.
   Exit 0 when every part holds. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { fileURLToPath, pathToFileURL } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const at = rel => pathToFileURL(path.join(ROOT, rel)).href;
const OUT = path.resolve(process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'live-candles-local-')));
fs.mkdirSync(OUT, { recursive: true });
const { loadFixtures } = await import(at('apps/edge-bff/terminal/tests/calc/fixtures.mjs'));
const K = await import(at('apps/edge-bff/backtest/src/core/candles.ts'));
const M = await import(at('verification/screener/live_candles_compute.mjs'));
const summary = { parts: {} };
const log = (...x) => console.log(...x);

/* ==== A. the independent implementation ========================================================================== */

// the live check's parameter sets (live_candles_dev.py plan_screens and OWN)
const HAMMER = { body_max_pct: 40, shadow_ratio: 1.5, short_shadow_pct: 15, trend: 'change', trend_length: 5 }, DOJI = { doji_body_pct: 5, short_shadow_pct: 5, trend: 'change' };
const OWN = { hammer: HAMMER, hanging_man: HAMMER, inverted_hammer: HAMMER, shooting_star: HAMMER, dragonfly_doji: DOJI, gravestone_doji: DOJI,
  bullish_marubozu: { long_body: 0, body_avg_length: 30, body_min_pct: 80 }, bearish_marubozu: { long_body: 0, body_avg_length: 30, body_min_pct: 80 },
  bullish_engulfing: { trend: 'change', trend_length: 20 }, bearish_engulfing: { trend: 'change', trend_length: 20 },
  bullish_harami: { inside_max_pct: 30, long_body: 1.5 }, bearish_harami: { inside_max_pct: 30, long_body: 1.5 },
  piercing_line: { open_beyond: 'range', penetration_pct: 30 }, dark_cloud_cover: { open_beyond: 'range', penetration_pct: 30 },
  tweezer_bottom: { tolerance_ticks: 0 }, tweezer_top: { tolerance_ticks: 0 },
  morning_star: { star_overlap_pct: -10, penetration_pct: 30, star_body_pct: 50 }, evening_star: { star_overlap_pct: -10, penetration_pct: 30, star_body_pct: 50 },
  three_white_soldiers: { body_min_pct: 60, short_shadow_pct: 10, long_body: 0.5 }, three_black_crows: { body_min_pct: 60, short_shadow_pct: 10, long_body: 0.5 } };
const liveSets = id => [{}, { trend: M.PATTERNS[id].trend.includes('none') ? 'none' : 'change' }, { min_range_ticks: 2 }, { min_range_ticks: 1 }, { trend: 'average', trend_length: 60 }, OWN[id]];

let seed = 20261108;
const rnd = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296;
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const tickOf = p => p < 200 ? 1 : p < 500 ? 2 : p < 2000 ? 5 : p < 5000 ? 10 : 25;
const snap = x => Math.max(1, Math.round(x / tickOf(x)) * tickOf(x));

/** Random bars around `base` (prices on the tick grid, or scaled by `adjust` for an adjusted history), with days
    without trades, one-price days with trades, missing values and inconsistent bars. */
function randomBars(n, base, { adjust = 1, holes = true } = {}) {
  const B = { O: [], H: [], L: [], C: [], V: [] };
  let c = base;
  for (let i = 0; i < n; i++) {
    const t = tickOf(c), kind = rnd();
    let o = snap(c + t * ri(-2, 2) + (base - c) * 0.05);
    const body = kind < 0.12 ? 0 : ri(1, kind < 0.6 ? 4 : 14);
    let cl = snap(o + (rnd() < 0.5 ? -1 : 1) * body * tickOf(o));
    let h = snap(Math.max(o, cl) + tickOf(Math.max(o, cl)) * (rnd() < 0.35 ? 0 : ri(1, kind < 0.3 ? 14 : 4)));
    let l = snap(Math.min(o, cl) - tickOf(Math.min(o, cl)) * (rnd() < 0.35 ? 0 : ri(1, kind < 0.3 ? 14 : 4)));
    h = Math.max(h, o, cl); l = Math.min(l, o, cl);
    let v = ri(1, 5e6);
    const z = rnd();
    if (z < 0.04) { o = h = l = cl = c; v = 0 }                              // a day without trades
    else if (z < 0.06) { o = h = l = cl; }                                     // a one-price day with trades
    else if (holes && z < 0.07) v = null;
    else if (holes && z < 0.075) cl = null;
    else if (holes && z < 0.08) o = null;
    else if (holes && z < 0.085) h = Math.min(o, cl) - tickOf(o);             // inconsistent: high below the body
    const k = adjust;
    B.O.push(o === null ? null : o * k); B.H.push(h * k); B.L.push(l * k); B.C.push(cl === null ? null : cl * k); B.V.push(v);
    if (cl !== null) c = cl;
  }
  return B;
}
/** Parameters within the core registry's ranges: default, min, max, random or loose (short windows, 1 tick). */
function paramsOf(id, mode) {
  const pat = K.CANDLES.patterns.find(p => p.id === id), g = {};
  if (mode === 'default') return g;
  for (const q of pat.params) {
    if (q.type === 'enum') { g[q.key] = q.options[ri(0, q.options.length - 1)]; continue }
    const lo = q.min, hi = q.max;
    let v = mode === 'min' ? lo : mode === 'max' ? hi
      : q.type === 'integer' ? ri(Math.max(lo, 1), Math.min(hi, ['trend_length', 'body_avg_length'].includes(q.key) ? 15 : q.key === 'min_range_ticks' ? 6 : hi)) : lo + Math.round(rnd() * (hi - lo) * 4) / 4;
    if (mode === 'loose') { if (q.key === 'min_range_ticks') v = 1; if (q.key === 'trend_length') v = ri(2, 4); if (q.key === 'body_avg_length') v = ri(1, 3); if (q.key === 'long_body') v = [0, 0.5, 1][ri(0, 2)] }
    g[q.key] = v;
  }
  return g;
}
function oracle(bars, id, given, tag, acc) {
  const a = K.candleSignal(bars, id, given), b = M.detect(bars, id, given);
  for (let i = 0; i < a.length; i++) {
    acc.bars++; acc.signals += b[i];
    if (a[i] !== b[i]) { acc.mismatches++; if (acc.examples.length < 5) acc.examples.push({ tag, id, bar: i, core: a[i], independent: b[i], given }) }
  }
}
function partA() {
  const res = {};
  const fx = loadFixtures();
  // A1: the fixtures at the live check's parameter sets
  const a1 = { bars: 0, signals: 0, mismatches: 0, examples: [] };
  for (const f of fx) for (const id of M.PATTERN_IDS) for (const g of liveSets(id)) oracle({ O: f.O, H: f.H, L: f.L, C: f.C, V: f.V }, id, g, f.ticker, a1);
  res.fixtures_live_sets = a1;
  // A2: random bars in every band, adjusted prices among them
  const a2 = { bars: 0, signals: 0, mismatches: 0, examples: [] };
  for (const id of M.PATTERN_IDS) for (const [base, adjust] of [[60, 1], [150, 1], [198, 1], [350, 1], [499, 1], [1000, 1], [1990, 1], [3000, 1], [4980, 1], [8000, 1], [2400, 0.8333], [480, 0.37], [5100, 1.7]])
    for (const mode of ['default', 'min', 'max', 'rand', 'rand', 'loose', 'loose']) oracle(randomBars(400, base, { adjust }), id, paramsOf(id, mode), `${base}x${adjust}/${mode}`, a2);
  res.random = a2;
  // A3: hand-derived boundary cases (expected values from the document's words; the core is not consulted)
  const fall = (len, end = 2760, body = 10, slope = 2) => Array.from({ length: len }, (_, k) => { const c = end + slope * (len - 1 - k), o = c + body; return [o, o + body / 2, c - body / 2, c] });
  const mir = r => [5000 - r[0], 5000 - r[2], 5000 - r[1], 5000 - r[3]];
  const toB = rows => ({ O: rows.map(r => r[0]), H: rows.map(r => r[1]), L: rows.map(r => r[2]), C: rows.map(r => r[3]), V: rows.map(r => r.length > 4 ? r[4] : 1e6) });
  const F = fall(12), FB = fall(12, 2760, 100, 2), hc1 = [2800, 2800, 2700, 2700], pc1 = [2800, 2810, 2690, 2700], sc1 = [2800, 2800, 2700, 2700];
  const star = top => [...F, sc1, [top - 5, top + 20, top - 35, top], [2710, 2765, 2705, 2750]];
  const sw = (o2, o3) => [...F, [2700, 2765, 2695, 2760], [o2, 2825, o2 - 5, 2820], [o3, 2885, o3 - 5, 2880]];
  const tw = (l1, l2) => [[l1 + 40, l1 + 60, l1, l1 + 10], [l2 + 10, l2 + 60, l2, l2 + 50]];
  const CASES = [
    ['hammer: body exactly 30 % of the range fires', 'hammer', [...F, [2730, 2760, 2660, 2760]], {}, 1],
    ['hammer: body 31 % does not', 'hammer', [...F, [2729, 2760, 2660, 2760]], {}, 0],
    ['hammer: upper shadow exactly 10 % fires', 'hammer', [...F, [2750, 2770, 2670, 2760]], {}, 1],
    ['hammer: upper shadow 11 % does not', 'hammer', [...F, [2750, 2771, 2671, 2760]], {}, 0],
    ['hammer: body 30 %, lower shadow 2 x body and upper shadow 10 % all at their limits fire', 'hammer', [...F, [2730, 2770, 2670, 2760]], {}, 1],
    ['hammer: the same candle with shadow_ratio 2.1 does not', 'hammer', [...F, [2730, 2770, 2670, 2760]], { shadow_ratio: 2.1 }, 0],
    ['hammer after a rise is not a hammer', 'hammer', [...F.map(mir), [2750, 2770, 2670, 2760]], {}, 0],
    ['hanging man after a rise fires', 'hanging_man', [...F.map(mir), [2750, 2770, 2670, 2760]], {}, 1],
    ['average trend of 10 needs 10 sessions before the candle: 10 fire', 'hammer', [...fall(10), [2750, 2760, 2660, 2760]], {}, 1],
    ['average trend of 10: 9 sessions do not', 'hammer', [...fall(9), [2750, 2760, 2660, 2760]], {}, 0],
    ['change trend of 10 needs 11 sessions: 11 fire', 'hammer', [...fall(11), [2750, 2760, 2660, 2760]], { trend: 'change' }, 1],
    ['change trend of 10: 10 sessions do not', 'hammer', [...fall(10), [2750, 2760, 2660, 2760]], { trend: 'change' }, 0],
    ['equal closes are not a decline (change)', 'hammer', [...fall(11, 2760, 10, 0), [2750, 2760, 2660, 2760]], { trend: 'change' }, 0],
    ['equal closes are not a decline (average)', 'hammer', [...fall(10, 2760, 10, 0), [2750, 2760, 2660, 2760]], {}, 0],
    ['trend none: a doji on bar 1 fires', 'dragonfly_doji', [[2760, 2770, 2760, 2770], [2750, 2750, 2650, 2750]], { trend: 'none' }, 1],
    ['trend none: never on bar 0', 'dragonfly_doji', [[2750, 2750, 2650, 2750]], { trend: 'none' }, 0],
    ['doji: body exactly 10 % fires', 'dragonfly_doji', [...F, [2740, 2750, 2650, 2750]], {}, 1],
    ['doji: body 11 % does not', 'dragonfly_doji', [...F, [2739, 2750, 2650, 2750]], {}, 0],
    ['a one-price bar is never a doji', 'dragonfly_doji', [...F, [2750, 2750, 2750, 2750]], { min_range_ticks: 1 }, 0],
    ['a day without trades is never a doji', 'dragonfly_doji', [...F, [2750, 2750, 2650, 2750, 0]], {}, 0],
    ['missing volume is never a candle', 'dragonfly_doji', [...F, [2750, 2750, 2650, 2750, null]], {}, 0],
    ['marubozu: body 90.09 % of the range, equal to the average body, fires', 'bullish_marubozu', [...FB, [2700, 2811, 2700, 2800]], {}, 1],
    ['marubozu: body 89.3 % does not', 'bullish_marubozu', [...FB, [2700, 2812, 2700, 2800]], {}, 0],
    ['marubozu: body 99 below the average 100 does not', 'bullish_marubozu', [...FB, [2700, 2799, 2700, 2799]], {}, 0],
    ['marubozu: long_body 0.99 lets body 99 fire', 'bullish_marubozu', [...FB, [2700, 2799, 2700, 2799]], { long_body: 0.99 }, 1],
    ['marubozu: the average needs its 10 sessions (9 do not)', 'bullish_marubozu', [...fall(9, 2760, 100, 2), [2700, 2811, 2700, 2800]], {}, 0],
    ['engulfing: equal edges fire', 'bullish_engulfing', [...F, [2770, 2770, 2740, 2740], [2740, 2790, 2740, 2771]], {}, 1],
    ['engulfing: equal bodies do not', 'bullish_engulfing', [...F, [2770, 2770, 2730, 2740], [2740, 2790, 2740, 2770]], {}, 0],
    ['engulfing: close below the first open does not', 'bullish_engulfing', [...F, [2770, 2770, 2730, 2740], [2730, 2790, 2730, 2769]], {}, 0],
    ['harami: both edges equal fire (inside 100 %)', 'bullish_harami', [...F, hc1, [2700, 2800, 2700, 2800]], { inside_max_pct: 100 }, 1],
    ['harami: top above the first open does not', 'bullish_harami', [...F, hc1, [2700, 2801, 2700, 2801]], { inside_max_pct: 100 }, 0],
    ['harami: second body exactly 50 % fires', 'bullish_harami', [...F, hc1, [2725, 2780, 2720, 2775]], {}, 1],
    ['harami: second body 51 % does not', 'bullish_harami', [...F, hc1, [2724, 2780, 2720, 2775]], {}, 0],
    ['piercing: exactly 50 % into the body fires', 'piercing_line', [...F, pc1, [2680, 2760, 2675, 2750]], {}, 1],
    ['piercing: 49 % does not', 'piercing_line', [...F, pc1, [2680, 2760, 2675, 2749]], {}, 0],
    ['piercing: closing at the first open is past it (strict)', 'piercing_line', [...F, pc1, [2680, 2810, 2675, 2800]], { penetration_pct: 0 }, 0],
    ['piercing: opening at the first close does not (strict)', 'piercing_line', [...F, pc1, [2700, 2760, 2675, 2750]], {}, 0],
    ['piercing, range: opening at the first low does not', 'piercing_line', [...F, pc1, [2690, 2760, 2675, 2750]], { open_beyond: 'range' }, 0],
    ['piercing, range: opening below the first low fires', 'piercing_line', [...F, pc1, [2689, 2760, 2675, 2750]], { open_beyond: 'range' }, 1],
    ['morning star: star top at close1 + 10 % fires', 'morning_star', star(2710), {}, 1],
    ['morning star: star top 1 above that does not', 'morning_star', star(2711), {}, 0],
    ['morning star, overlap -10 %: a real gap of 10 fires', 'morning_star', star(2690), { star_overlap_pct: -10 }, 1],
    ['morning star, overlap -10 %: a gap of 9 does not', 'morning_star', star(2691), { star_overlap_pct: -10 }, 0],
    ['soldiers: open2 at open1 fires', 'three_white_soldiers', sw(2700, 2800), {}, 1],
    ['soldiers: open2 at close1 fires', 'three_white_soldiers', sw(2760, 2820), {}, 1],
    ['soldiers: open2 above close1 does not', 'three_white_soldiers', sw(2761, 2820), {}, 0],
    ['soldiers: open2 below open1 does not', 'three_white_soldiers', sw(2699, 2800), {}, 0],
    ['tweezer: 1995 and 2010 are 2 ticks apart (tolerance 1: no)', 'tweezer_bottom', tw(1995, 2010), { trend: 'none', min_range_ticks: 1, tolerance_ticks: 1 }, 0],
    ['tweezer: 1995 and 2010 within tolerance 2 fire', 'tweezer_bottom', tw(1995, 2010), { trend: 'none', min_range_ticks: 1, tolerance_ticks: 2 }, 1],
    ['tweezer: 199 and 200 are 1 tick apart', 'tweezer_bottom', tw(199, 200), { trend: 'none', min_range_ticks: 1, tolerance_ticks: 1 }, 1],
    ['tweezer: 4995 and 5025 are 1.5 ticks apart (tolerance 1: no)', 'tweezer_bottom', tw(4995, 5025), { trend: 'none', min_range_ticks: 1, tolerance_ticks: 1 }, 0],
    ['tweezer: equal lows with tolerance 0 fire', 'tweezer_bottom', tw(100, 100), { trend: 'none', min_range_ticks: 1, tolerance_ticks: 0 }, 1],
    ['range 1990-2010 is 3 ticks (2 + 1): fires at 3', 'dragonfly_doji', [[2000, 2010, 2000, 2010], [2010, 2010, 1990, 2010]], { trend: 'none', short_shadow_pct: 0 }, 1],
    ['range 1995-2010 is 2 ticks: not at 3', 'dragonfly_doji', [[2000, 2010, 2000, 2010], [2010, 2010, 1995, 2010]], { trend: 'none' }, 0],
    ['range 198-202 is 3 ticks (2 + 1): fires at 3', 'dragonfly_doji', [[200, 202, 200, 202], [202, 202, 198, 202]], { trend: 'none' }, 1],
    ['range 199-202 is 2 ticks: not at 3', 'dragonfly_doji', [[200, 202, 200, 202], [202, 202, 199, 202]], { trend: 'none' }, 0],
  ];
  const failed = [];
  for (const [name, id, rows, g, want] of CASES) { const s = M.detect(toB(rows), id, g); if (s[s.length - 1] !== want) failed.push({ name, got: s[s.length - 1], want }) }
  const TICKS = [[199, 200, 1], [200, 201, 0.5], [199, 201, 1.5], [499, 500, 0.5], [498, 500, 1], [1999, 2000, 0.2], [1995, 2010, 2], [4995, 5000, 0.5], [4995, 5025, 1.5], [5000, 5025, 1], [100, 6000, 890], [2500, 2500, 0]];
  for (const [a, b, want] of TICKS) if (Math.abs(M.ticksBetween(a, b) - want) > 1e-9 || M.ticksBetween(a, b) !== M.ticksBetween(b, a)) failed.push({ name: `ticks ${a}-${b}`, got: M.ticksBetween(a, b), want });
  res.boundaries = { cases: CASES.length + TICKS.length, failed };
  // A4: the frequency table of P6_CANDLES.md section 5 (7 fixture stocks, 9,014 bars, defaults)
  const DOC = { hammer: 155, hanging_man: 253, inverted_hammer: 207, shooting_star: 132, dragonfly_doji: 53, gravestone_doji: 31, bullish_marubozu: 324, bearish_marubozu: 406,
    bullish_engulfing: 163, bearish_engulfing: 184, bullish_harami: 195, bearish_harami: 150, piercing_line: 24, dark_cloud_cover: 23, tweezer_bottom: 296, tweezer_top: 261,
    morning_star: 23, evening_star: 16, three_white_soldiers: 6, three_black_crows: 6 };
  const got = {}, stocks = fx.filter(f => f.ticker !== 'IHSG');
  for (const id of M.PATTERN_IDS) got[id] = stocks.reduce((s, f) => s + M.detect({ O: f.O, H: f.H, L: f.L, C: f.C, V: f.V }, id).reduce((a, x) => a + x, 0), 0);
  res.frequency = { stocks: stocks.length, bars: stocks.reduce((s, f) => s + f.T.length, 0), differs: Object.keys(DOC).filter(k => DOC[k] !== got[k]).map(k => ({ id: k, doc: DOC[k], independent: got[k] })) };
  return res;
}

/* ==== B. the local stack ========================================================================================== */

const { startFakeTerminal, brokerRowsOf } = await import(at('apps/screener-worker/tests/fake-terminal.mjs'));
const { encode, pricePack } = await import(at('apps/backtest-worker/tests/fake-terminal.mjs'));
const { createApp } = await import(at('apps/screener-worker/src/server.ts'));
const { configFor, KEY, PROXY, OWNER_A } = await import(at('apps/screener-worker/tests/helpers.ts'));
const { setLogSink } = await import(at('apps/screener-worker/src/log.ts'));

/** Synthetic rows [d, o, h, l, c, v] on `dates` around `base` (on the tick grid unless adjusted), drawn as randomBars. */
function synth(dates, base, opt = {}) {
  const B = randomBars(dates.length, base, { holes: false, ...opt });
  return dates.map((d, i) => [d, B.O[i], B.H[i], B.L[i], B.C[i], B.V[i]]);
}
function market() {
  const fx = loadFixtures(), prices = {}, ref = [];
  for (const f of fx) {
    prices[f.ticker] = f.T.map((d, i) => [d, f.O[i], f.H[i], f.L[i], f.C[i], f.V[i]]);
    ref.push([f.ticker, `${f.ticker} fixture`, f.ticker === 'IHSG' ? 'index' : 'stock', f.ticker === 'IHSG' ? 'Undefined' : 'Fixtures', f.ticker === 'IHSG' ? 'Undefined' : 'Fixture stocks']);
  }
  const cal = fx.find(f => f.ticker === 'IHSG').T, recent = cal.slice(-700);
  const add = (t, rows, sector = 'Synthetic') => { prices[t] = rows; ref.push([t, `${t} synthetic`, 'stock', sector, `${sector} stocks`]) };
  add('BND200', synth(recent, 200)); add('BND500', synth(recent, 500)); add('BND2K', synth(recent, 2000)); add('BND5K', synth(recent, 5000));
  // illiquid: many days without trades and one-price days
  add('THIN', synth(recent, 120).map(r => { const z = rnd(); return z < 0.35 ? [r[0], r[4], r[4], r[4], r[4], 0] : z < 0.45 ? [r[0], r[4], r[4], r[4], r[4], ri(100, 900)] : [r[0], r[1], r[2], r[3], r[4], ri(100, 5000)] }));
  // rows without four prices (left out by the readers) and missing volumes
  add('HOLE', synth(recent, 900).map((r, i) => i % 97 === 5 ? [r[0], null, r[2], r[3], r[4], r[5]] : i % 89 === 7 ? [r[0], r[1], r[2], r[3], r[4], null] : r));
  // a stock split after the adjusted-history boundary (2026-09-12): unadjusted, halved from 2026-10-19
  add('SPLT', synth(recent, 1500).map(r => r[0] >= '2026-10-19' ? [r[0], snap(r[1] / 2), snap(r[2] / 2), snap(r[3] / 2), snap(r[4] / 2), r[5] * 2] : r).map(r => [r[0], r[1], Math.max(r[1], r[2], r[4]), Math.min(r[1], r[3], r[4]), r[4], r[5]]));
  // an adjusted history: fractional prices before the boundary
  add('ADJ', synth(recent, 2400).map(r => r[0] < '2026-09-12' ? [r[0], r[1] * 0.8333, r[2] * 0.8333, r[3] * 0.8333, r[4] * 0.8333, r[5]] : r));
  add('STALE', synth(cal.filter(d => d <= '2026-08-21').slice(-500), 700));
  // the rarest patterns built on the last bars (after a synthetic history and a falling or rising context), so every
  // pattern has a stock that shows it end to end: Dark Cloud Cover, Evening Star (mirrored Piercing Line and Morning
  // Star), Three White Soldiers and Three Black Crows
  const fall = Array.from({ length: 12 }, (_, k) => { const c = 2760 + 2 * (11 - k), o = c + 10; return [o, o + 5, c - 5, c] });
  const mir = r => [5000 - r[0], 5000 - r[2], 5000 - r[1], 5000 - r[3]];
  const built = (bars, mirror) => { const d = recent.slice(-330), body = [...fall, ...bars].map(r => mirror ? mir(r) : r), head = synth(d.slice(0, d.length - body.length), mirror ? 2240 : 2760);
    return [...head, ...body.map((r, k) => [d[head.length + k], ...r, 1e6])] };
  add('DCC', built([[2800, 2810, 2690, 2700], [2680, 2765, 2675, 2760]], true));
  add('ESTAR', built([[2800, 2800, 2700, 2700], [2695, 2720, 2685, 2705], [2710, 2765, 2705, 2760]], true));
  add('SOLD', built([[2700, 2765, 2695, 2760], [2740, 2825, 2735, 2820], [2800, 2885, 2795, 2880]], false));
  add('CROW', built([[2700, 2765, 2695, 2760], [2740, 2825, 2735, 2820], [2800, 2885, 2795, 2880]], true));
  const stocks = Object.keys(prices).filter(t => t !== 'IHSG' && t !== 'STALE'), days = cal.slice(-62, -2);
  const broker = Object.fromEntries(days.map((d, k) => [d, brokerRowsOf(k + 1, d, stocks.filter(t => prices[t].some(r => r[0] === d)))]));
  const brokers = [['AK', 'A', 'Local', 'Institutional-heavy'], ['BK', 'B', 'Foreign', 'Retail-heavy'], ['CC', 'C', 'Local', 'Mixed'],
    ['DX', 'D', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy'], ['ZP', 'Z', 'Foreign', 'Mixed']];
  return { finished_at: '2026-10-23T12:59:56Z', prices, ref, actions: [['SPLT', '2026-10-19', 'STOCK_SPLIT', 1, 2, null, null]], broker, brokers };
}

const readBody = req => new Promise((ok, no) => { const parts = []; req.on('data', c => parts.push(c)); req.on('end', () => ok(Buffer.concat(parts))); req.on('error', no) });
/** A stand-in for edge-bff's public routes the check uses (apps/edge-bff/app/main.py sign-in and session,
    screener.py catalog, universe and run, the terminal gateway's bundle). tamper: {pack(t, rows), run(answer), quota}. */
async function startEdge(workerPort, prices, login, password) {
  const sessions = new Map(), issued = [], requests = [], files = new Map(), opened = new Set();
  const edge = { requests, issued, tamper: {}, base: '' };
  const relay = (method, p, body) => new Promise((ok, no) => {
    const req = http.request({ host: '127.0.0.1', port: workerPort, method, path: p, headers: { 'x-screener-worker-key': KEY, 'x-screener-owner': OWNER_A, 'accept-encoding': 'gzip',
      ...(body ? { 'content-type': 'application/json', 'content-length': String(body.length) } : {}) } }, res => {
      const parts = []; res.on('data', c => parts.push(c)); res.on('end', () => ok({ status: res.statusCode, headers: res.headers, body: Buffer.concat(parts) }));
    });
    req.on('error', no); if (body) req.write(body); req.end();
  });
  const server = http.createServer(async (req, res) => {
    const u = new URL(req.url, 'http://edge'), body = await readBody(req);
    const entry = { method: req.method, path: u.pathname, cookie: !!req.headers.cookie };
    requests.push(entry);
    const json = (status, obj, headers = {}) => { const b = Buffer.from(JSON.stringify(obj)); res.writeHead(status, { 'content-type': 'application/json', 'content-length': b.length, ...headers }); res.end(b) };
    const pass = r => { res.writeHead(r.status, { 'content-type': r.headers['content-type'] || 'application/json', ...(r.headers['content-encoding'] ? { 'content-encoding': r.headers['content-encoding'] } : {}), 'content-length': r.body.length }); res.end(r.body) };
    try {
      if (u.pathname.startsWith('/bucket/')) {
        const f = files.get(u.pathname.slice(8));
        if (!f || !u.searchParams.get('X-Amz-Signature')) return json(403, { error: 'AccessDenied' });
        res.writeHead(200, { 'content-type': 'application/gzip', 'content-length': f.length }); return res.end(f);
      }
      if (req.method === 'POST' && u.pathname === '/api/v1/auth/sign-in') {
        const b = JSON.parse(body.toString() || '{}');
        if (b.login !== login || b.password !== password) return json(401, { error: { code: 'INVALID_CREDENTIALS' } });
        const token = crypto.randomBytes(32).toString('hex'), csrf = crypto.randomBytes(24).toString('hex');
        sessions.set(token, csrf); issued.push(token, csrf);
        return json(200, { authenticated: true, login, csrf_token: csrf }, { 'set-cookie': `edge_session=${token}; HttpOnly; SameSite=Strict; Path=/` });
      }
      const token = /(?:^|;\s*)edge_session=([0-9a-f]+)/.exec(req.headers.cookie || '')?.[1], csrf = token && sessions.get(token);
      if (!csrf) return json(401, { detail: 'Not signed in.' });
      if (req.method === 'POST' && (req.headers['x-csrf-token'] !== csrf || req.headers.origin !== edge.base)) return json(403, { detail: 'CSRF or Origin check failed.' });
      if (req.method === 'GET' && u.pathname === '/api/v1/auth/session') return json(200, { authenticated: true, login, csrf_token: csrf });
      if (req.method === 'POST' && u.pathname === '/api/v1/auth/sign-out') { sessions.delete(token); return json(200, { authenticated: false }) }
      if (req.method === 'GET' && ['/api/v1/screener/catalog', '/api/v1/screener/universe'].includes(u.pathname)) return pass(await relay('GET', u.pathname.replace('/api/v1/screener', '/v1'), null));
      if (req.method === 'POST' && u.pathname === '/api/v1/screener/run') {
        if (edge.tamper.refuse?.(JSON.parse(body.toString()))) return json(422, { error: { code: 'LIMIT_EXCEEDED', field: 'definition', message: 'This screen needs about 31000 ms of compute; the limit is 20000 ms.', details: { limit: 'compute_budget', allowed: 20000, needed: 31000, costliest: 'c' } } });
        const r = await relay('POST', '/v1/run', body);
        if (!edge.tamper.run || r.status !== 200) return pass(r);
        const doc = JSON.parse((r.headers['content-encoding'] === 'gzip' ? zlib.gunzipSync(r.body) : r.body).toString());
        return json(200, edge.tamper.run(doc, JSON.parse(body.toString())));
      }
      if (req.method === 'POST' && u.pathname === '/api/terminal/v1/bundle') {
        const b = JSON.parse(body.toString() || '{}'), t = b.ticker;
        if (!prices[t]) return json(404, { detail: { error: 'unknown_ticker', message: `No published data for ${t}.` } });
        opened.add(t);
        if (edge.tamper.quota && opened.size > edge.tamper.quota) return json(429, { detail: { error: 'quota_exceeded', message: 'Quota tickers_per_hour reached.' } });
        const rows = edge.tamper.pack ? edge.tamper.pack(t, prices[t]) : prices[t], e = encode(pricePack(t, rows)), name = `pack/${t}.${e.sha256.slice(0, 16)}.json.gz`;
        files.set(name, e.body);
        return json(200, { ticker: t, window: null, generated_at: '2026-10-23T12:59:56Z', expires_in_seconds: 120, encoding: 'gzip json', timeframes: {}, kind: 'equity', instrument: null,
          datasets: { price: { data_through: rows[rows.length - 1][0], first_year: +rows[0][0].slice(0, 4), files: [{ year: null, url: `${edge.base}/bucket/${name}?X-Amz-Expires=120&X-Amz-Signature=${crypto.randomBytes(16).toString('hex')}`, sha256: e.sha256, bytes: e.body.length, rows: rows.length, pack: 'price' }] } } });
      }
      entry.unexpected = true;
      return json(404, { detail: 'Not Found' });
    } catch (e) { entry.error = String(e); json(500, { detail: String(e) }) }
  });
  await new Promise(ok => server.listen(0, '127.0.0.1', ok));
  edge.base = `http://127.0.0.1:${server.address().port}`;
  edge.reset = () => { requests.length = 0; opened.clear(); edge.tamper = {} };
  edge.close = () => new Promise(ok => { server.closeAllConnections?.(); server.close(() => ok()) });
  return edge;
}

function runCheck(dir, base, env, extra = []) {
  return new Promise(ok => {
    const p = spawn('python3', [path.join(ROOT, 'verification/screener/live_candles_dev.py'), dir, '--base-url', base, '--pace', '0', '--bundle-pace', '0', '--max-sample', '40', '--sample', 'HOLE', ...extra],
      { cwd: ROOT, env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'pipe'] });
    let out = '', err = '';
    p.stdout.on('data', c => { out += c }); p.stderr.on('data', c => { err += c });
    p.on('close', code => ok({ code, out, err }));
  });
}
function runJudge(dir) {
  return new Promise(ok => { const p = spawn(process.execPath, [path.join(ROOT, 'verification/screener/live_candles_compute.mjs'), dir], { stdio: ['ignore', 'pipe', 'pipe'] }); let out = ''; p.stdout.on('data', c => { out += c }); p.on('close', code => ok({ code, out })) });
}
const filesUnder = dir => fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? filesUnder(path.join(dir, e.name)) : [path.join(dir, e.name)]);
function noSecret(texts, secrets) {
  const hits = [];
  for (const [where, text] of texts) for (const s of secrets) if (s && text.includes(s)) hits.push(where);
  return [...new Set(hits)];
}
const READ_ROUTES = new Set(['POST /api/v1/auth/sign-in', 'GET /api/v1/auth/session', 'GET /api/v1/screener/catalog', 'GET /api/v1/screener/universe', 'POST /api/v1/screener/run', 'POST /api/terminal/v1/bundle', 'POST /api/v1/auth/sign-out']);

async function partsBC() {
  setLogSink(() => {});                                       // the worker's log lines are not this proof's output
  const publication = market();
  const fake = await startFakeTerminal({ key: PROXY, publication });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '2' }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick(); await app.refresher.tick();
  assert.ok(app.state().current, 'the worker loaded the local publication');
  const LOGIN = 'owner-local', PASSWORD = crypto.randomBytes(18).toString('base64url');
  const edge = await startEdge(port, publication.prices, LOGIN, PASSWORD), env = { EDGE_LOGIN: LOGIN, EDGE_INITIAL_PASSWORD: PASSWORD };
  const res = {};
  try {
    // B: the check against the local stack
    const b = path.join(OUT, 'b');
    let r = await runCheck(b, edge.base, env);
    if (!fs.existsSync(path.join(b, 'report.json'))) { log(r.out.slice(-3000), r.err.slice(-3000)); throw new Error(`the check wrote no report (exit ${r.code})`) }
    const rep = JSON.parse(fs.readFileSync(path.join(b, 'report.json'), 'utf8'));
    const secrets = [PASSWORD, ...edge.issued];
    const leaks = noSecret([['stdout', r.out], ['stderr', r.err], ...filesUnder(b).map(f => [path.relative(OUT, f), fs.readFileSync(f, 'utf8')])], secrets);
    const routes = [...new Set(edge.requests.filter(x => !x.path.startsWith('/bucket/')).map(x => `${x.method} ${x.path}`))];
    res.b = { exit: r.code, verdict: rep.verdict, screens: rep.screens.count, answered: rep.screens.answered, catalog_entries: rep.catalog.entries, catalog_problems: rep.catalog.problems,
      relations: rep.relations.checked, relation_problems: rep.relations.problems, params_checked: rep.params.checked, compared: rep.parity.compared, equal: rep.parity.equal,
      sample: rep.sample.map(s => `${s.ticker} (${s.reasons.join('; ')})`), uncovered: rep.coverage.patterns_without_a_positive_in_the_sample,
      positives: Object.fromEntries(Object.entries(rep.parity.by_pattern).map(([k, v]) => [k, v.positives])), routes,
      unexpected_routes: routes.filter(x => !READ_ROUTES.has(x)), bucket_with_cookie: edge.requests.filter(x => x.path.startsWith('/bucket/') && x.cookie).length, secret_leaks: leaks,
      price_break_cells: Object.fromEntries(rep.sample.filter(x => x.price_break_cells).map(x => [x.ticker, x.price_break_cells])), failures: rep.failures.slice(0, 5), incomplete: rep.incomplete };
    log('B', JSON.stringify({ exit: r.code, verdict: rep.verdict, compared: rep.parity.compared, equal: rep.parity.equal, screens: `${rep.screens.answered}/${rep.screens.count}`, relations: rep.relations.checked }));
    if (r.code !== 0) log(r.out.slice(-3000), r.err.slice(-2000));

    // C1: the Terminal's bars of one stock changed (open and close swapped on its last three bars)
    edge.reset();
    edge.tamper.pack = (t, rows) => t === 'BBCA' ? rows.map((x, i) => i >= rows.length - 3 ? [x[0], x[4], x[2], x[3], x[1], x[5]] : x) : rows;
    const c1 = path.join(OUT, 'c1');
    r = await runCheck(c1, edge.base, env);
    let rc = JSON.parse(fs.readFileSync(path.join(c1, 'report.json'), 'utf8'));
    const lines1 = fs.readFileSync(path.join(c1, 'parity.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l)).filter(l => !l.same);
    res.c1 = { exit: r.code, verdict: rc.verdict, mismatches: lines1.length, tickers: [...new Set(lines1.map(l => l.t))], example: lines1[0] ?? null };
    log('C1', JSON.stringify({ exit: r.code, verdict: rc.verdict, mismatches: lines1.length, tickers: res.c1.tickers }));

    // C2: one Screener cell changed: bars_ago + 1 on one passing event cell of a sample stock, in one screen only (the
    // first equal line of B with a pattern found within N on a stock picked for itself, not for a screen)
    const picked = new Set(rep.sample.filter(s => s.reasons.some(w => !w.startsWith('shows '))).map(s => s.ticker));
    const target = fs.readFileSync(path.join(b, 'parity.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l))
      .find(l => l.same && l.kind === 'event' && l.terminal.pass && picked.has(l.t) && !l.variant.startsWith('mix'));
    edge.reset();
    let done = false;
    const isTarget = q => { const c = q.definition?.conditions; const p = c?.length === 1 && c[0].test.kind === 'event' ? c[0].test.signal.pattern : null;
      return !!p && p.type === target.pattern && c[0].test.within === target.within && JSON.stringify(p.params || {}) === JSON.stringify(target.params) };
    edge.tamper.run = (doc, q) => { if (done || !isTarget(q)) return doc; for (const row of doc.rows || []) if (row.ticker === target.t) for (const c of row.cells || []) if (c.status === 'pass') { c.bars_ago += 1; done = true } return doc };
    const c2 = path.join(OUT, 'c2');
    r = await runCheck(c2, edge.base, env);
    rc = JSON.parse(fs.readFileSync(path.join(c2, 'report.json'), 'utf8'));
    const lines2 = fs.readFileSync(path.join(c2, 'parity.jsonl'), 'utf8').trim().split('\n').map(l => JSON.parse(l)).filter(l => !l.same);
    res.c2 = { exit: r.code, verdict: rc.verdict, target: `${target.t} ${target.screen}`, tampered: done, mismatches: lines2.length, lines: lines2.map(l => `${l.t} ${l.screen}: Screener ${JSON.stringify(l.screener)} / Terminal ${JSON.stringify(l.terminal)}`), relation_problems: rc.relations.problems };
    log('C2', JSON.stringify({ exit: r.code, verdict: rc.verdict, mismatches: lines2.length }));

    // C3: the publication moved during the check (the last catalog read names another price_data)
    const c3 = path.join(OUT, 'c3');
    fs.cpSync(b, c3, { recursive: true });
    const after = JSON.parse(fs.readFileSync(path.join(c3, 'catalog_after.json'), 'utf8'));
    after.versions.price_data = 'f'.repeat(64); after.data.published_at = '2026-10-24T12:59:56Z';
    fs.writeFileSync(path.join(c3, 'catalog_after.json'), JSON.stringify(after));
    const j3 = await runJudge(c3);
    res.c3 = { exit: j3.code, verdict: JSON.parse(fs.readFileSync(path.join(c3, 'report.json'), 'utf8')).verdict };
    log('C3', JSON.stringify(res.c3));

    // C5: a published limit refuses one screen (as the worker words a compute_budget refusal): exit 4, the rest equal
    edge.reset();
    edge.tamper.refuse = q => { const c = q.definition?.conditions; return c?.length === 1 && c[0].test.kind === 'event' && c[0].test.signal.pattern?.type === 'hammer' && c[0].test.signal.pattern.params?.trend_length === 60 };
    const c5 = path.join(OUT, 'c5');
    r = await runCheck(c5, edge.base, env);
    rc = JSON.parse(fs.readFileSync(path.join(c5, 'report.json'), 'utf8'));
    res.c5 = { exit: r.code, verdict: rc.verdict, limit_refused: rc.limit_refused, compared: rc.parity.compared, equal: rc.parity.equal };
    log('C5', JSON.stringify({ exit: r.code, verdict: rc.verdict, limit_refused: rc.limit_refused.length }));

    // C4: the Terminal quota refuses the fourth bundle
    edge.reset();
    edge.tamper.quota = 3;
    const c4 = path.join(OUT, 'c4');
    r = await runCheck(c4, edge.base, env);
    rc = JSON.parse(fs.readFileSync(path.join(c4, 'report.json'), 'utf8'));
    res.c4 = { exit: r.code, verdict: rc.verdict, incomplete: rc.incomplete.slice(0, 4), bundles: edge.requests.filter(x => x.path === '/api/terminal/v1/bundle').length };
    log('C4', JSON.stringify({ exit: r.code, verdict: rc.verdict, bundles: res.c4.bundles }));
  } finally { await edge.close(); await app.close(); await fake.close() }
  return res;
}

/* ==== run ======================================================================================================== */

const a = partA();
summary.parts.a = a;
log('A', JSON.stringify({ fixtures: [a.fixtures_live_sets.bars, a.fixtures_live_sets.signals, a.fixtures_live_sets.mismatches], random: [a.random.bars, a.random.signals, a.random.mismatches],
  boundaries: [a.boundaries.cases, a.boundaries.failed.length], frequency_differs: a.frequency.differs.length }));
for (const f of [...a.boundaries.failed, ...a.frequency.differs, ...a.fixtures_live_sets.examples, ...a.random.examples]) log('  A', JSON.stringify(f));
const bc = await partsBC();
Object.assign(summary.parts, bc);
const checks = {
  'A1 fixtures: independent = core': a.fixtures_live_sets.mismatches === 0,
  'A2 random bars: independent = core': a.random.mismatches === 0,
  'A3 boundary cases as the document says': a.boundaries.failed.length === 0,
  'A4 frequency table of P6_CANDLES.md': a.frequency.differs.length === 0,
  'B exit 0, PASS': bc.b.exit === 0 && bc.b.verdict === 'PASS',
  'B every comparison equal': bc.b.compared > 0 && bc.b.compared === bc.b.equal,
  'B every screen answered, catalog checked': bc.b.screens === bc.b.answered && bc.b.catalog_entries === 20 && bc.b.relations > 0,
  'B only the read routes, no cookie on the bucket': bc.b.unexpected_routes.length === 0 && bc.b.bucket_with_cookie === 0,
  'B no secret written or printed': bc.b.secret_leaks.length === 0,
  'C1 changed Terminal bars: exit 1 on that stock only': bc.c1.exit === 1 && bc.c1.mismatches > 0 && bc.c1.tickers.length === 1 && bc.c1.tickers[0] === 'BBCA',
  'B every pattern shown by a sample stock': bc.b.uncovered.length === 0,
  'C2 changed Screener cell: exit 1 on that cell': bc.c2.exit === 1 && bc.c2.tampered && bc.c2.mismatches === 1 && bc.c2.lines[0].startsWith(bc.c2.target),
  'C3 publication moved: exit 2': bc.c3.exit === 2,
  'C4 Terminal quota: exit 3': bc.c4.exit === 3 && bc.c4.verdict === 'INCOMPLETE',
  'C5 a limit refusal: exit 4, the rest equal': bc.c5.exit === 4 && bc.c5.limit_refused.length === 1 && bc.c5.limit_refused[0].name === 'hammer:long_trend_w5' && bc.c5.compared === bc.c5.equal,
  'B a stock with left-out rows and missing volumes compared': bc.b.sample.some(x => x.startsWith('HOLE ')),
  'B the price-break cell remark compared on a stock with a split': (bc.b.price_break_cells.SPLT || 0) > 0,
};
summary.checks = checks;
fs.writeFileSync(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 1));
for (const [k, v] of Object.entries(checks)) log(v ? 'ok  ' : 'FAIL', k);
log('summary', path.join(OUT, 'summary.json'));
process.exit(Object.values(checks).every(Boolean) ? 0 : 1);
