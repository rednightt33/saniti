/* The 20 candlestick patterns of the Backtest core (candles.ts, candle-registry.json; EXEC-SCREENER-FLOW-CANDLES P6,
   verification/screener/P6_CANDLES.md section 4):
   - the registry: the proposal's 20 names in their pairs, 10 bullish and 10 bearish, and its checks;
   - synthetic bars: a positive and a negative case per pattern, and per IDX guard (no trade, missing bar, the
     minimum range in ticks of the price band, the star's relaxed body gap, the piercing open, the trend);
   - symmetry: mirrored prices (p -> M - p) turn each pattern into its mirror (bullish <-> bearish);
   - an independent recomputation (tests/candles-oracle.mjs, written from the definitions) equal bar for bar on the
     Terminal parity fixtures and on random bars with missing values, days without trades and inconsistent bars;
   - each signal reads exactly candleLookback bars (no history dependence), and eventWithin;
   - the frequency of every pattern on the fixture stocks (each fires, none on more than 6 % of the bars, none on an
     index without volume), printed as the table P6_CANDLES.md records. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import { CANDLES, CANDLE_IDS, candleFormula, candleLookback, candleProblems, candleSignal, eventWithin, patternBar, resolveCandleParams, tickSize, ticksBetween } from '../../edge-bff/backtest/src/core/candles.ts';
import type { CandleParams } from '../../edge-bff/backtest/src/core/candles.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { ORACLE_IDS, oracle, ticks as oracleTicks } from './candles-oracle.mjs';

type Bar = [number, number, number, number] | [number, number, number, number, number | null];   // O H L C (V)
interface B { O: (number | null)[]; H: (number | null)[]; L: (number | null)[]; C: (number | null)[]; V: (number | null)[] }
const barsOf = (rows: Bar[]): B => ({ O: rows.map(r => r[0]), H: rows.map(r => r[1]), L: rows.map(r => r[2]), C: rows.map(r => r[3]), V: rows.map(r => r.length > 4 ? r[4] as number | null : 1e6) });
/** 12 sessions falling (or rising) by 20 a session, bodies of 10, in the Rp 2,000-5,000 band (tick 10); ends at 2760 (down) or 2240 (up). */
const ctx = (dir: 'down' | 'up'): Bar[] => Array.from({ length: 12 }, (_, k) => {
  const c = dir === 'down' ? 3000 - 20 * (k + 1) : 2000 + 20 * (k + 1), o = dir === 'down' ? c + 10 : c - 10;
  return [o, Math.max(o, c) + 10, Math.min(o, c) - 10, c];
});
const last = (id: string, rows: Bar[], p?: Record<string, unknown>) => { const s = candleSignal(barsOf(rows), id, p); return s[s.length - 1] };
const allDefaults = (id: string) => resolveCandleParams(id, undefined);
const codeOf = (f: () => unknown) => { try { f() } catch (e) { if (e instanceof ValidationError) return [e.code, e.field, e.message]; throw e } return null };

/* ---- the registry ---------------------------------------------------------------------------------------------- */

const PAIRS = [['hammer', 'hanging_man', 'Hammer', 'Hanging Man'], ['inverted_hammer', 'shooting_star', 'Inverted Hammer', 'Shooting Star'],
  ['dragonfly_doji', 'gravestone_doji', 'Dragonfly Doji', 'Gravestone Doji'], ['bullish_marubozu', 'bearish_marubozu', 'Bullish Marubozu', 'Bearish Marubozu'],
  ['bullish_engulfing', 'bearish_engulfing', 'Bullish Engulfing', 'Bearish Engulfing'], ['bullish_harami', 'bearish_harami', 'Bullish Harami', 'Bearish Harami'],
  ['piercing_line', 'dark_cloud_cover', 'Piercing Line', 'Dark Cloud Cover'], ['tweezer_bottom', 'tweezer_top', 'Tweezer Bottom', 'Tweezer Top'],
  ['morning_star', 'evening_star', 'Morning Star', 'Evening Star'], ['three_white_soldiers', 'three_black_crows', 'Three White Soldiers', 'Three Black Crows']];

test('the registry holds the proposal\'s 20 patterns in their pairs (10 bullish, 10 bearish) and passes its checks', () => {
  assert.deepEqual(candleProblems(), []);
  assert.equal(CANDLE_IDS.length, 20);
  for (const [bull, bear, nb, ns] of PAIRS) {
    const a = CANDLES.patterns.find(p => p.id === bull)!, b = CANDLES.patterns.find(p => p.id === bear)!;
    assert.deepEqual([a.name, a.side, a.pair, b.name, b.side, b.pair], [nb, 'bullish', bear, ns, 'bearish', bull]);
  }
  // mirrored prices: Hammer <-> Shooting Star and Inverted Hammer <-> Hanging Man (same shape pairs differ by trend only)
  const mirror = Object.fromEntries(CANDLES.patterns.map(p => [p.id, p.mirror]));
  assert.equal(mirror.hammer, 'shooting_star'); assert.equal(mirror.inverted_hammer, 'hanging_man');
  for (const [bull, bear] of PAIRS.slice(2)) assert.equal(mirror[bull], bear);
  assert.deepEqual([...ORACLE_IDS].sort(), [...CANDLE_IDS].sort());
  // every parameter documented with its meaning, min and max (or options)
  for (const p of CANDLES.patterns) for (const q of p.params) {
    assert.ok(q.label && q.meaning, `${p.id}.${q.key}`);
    assert.ok(q.type === 'enum' ? q.options!.length > 1 : q.min! <= (q.default as number) && (q.default as number) <= q.max!, `${p.id}.${q.key}`);
  }
  // the four pairs that differ by the trend only cannot switch the trend test off
  for (const id of ['hammer', 'hanging_man', 'inverted_hammer', 'shooting_star']) assert.deepEqual(CANDLES.patterns.find(p => p.id === id)!.params.find(q => q.key === 'trend')!.options, ['average', 'change']);
  assert.match(candleFormula('morning_star'), /100 x \(top2 - close1\) <= star_overlap_pct x body1/);
});

test('the registry checks refuse a broken registry, each problem named', () => {
  const copy = () => JSON.parse(JSON.stringify({ tick_bands: CANDLES.tick_bands, patterns: CANDLES.patterns }));
  const bad = (edit: (c: any) => void, re: RegExp) => { const c = copy(); edit(c); const p = candleProblems(c); assert.ok(p.some(x => re.test(x)), `${re}: ${p.join('; ')}`) };
  bad(c => { c.patterns[0].rules[0].rhs = ['*', '$nope', ['range', 1]] }, /"\$nope" is not a parameter of hammer/);
  bad(c => { c.patterns[0].rules[0].lhs = ['body', 2] }, /\[body, candle\] needs a candle from 1 to 1/);
  bad(c => { c.patterns[0].rules[0].lhs = ['wick', 1] }, /wick is not a primitive or a function/);
  bad(c => { c.patterns[0].pair = 'shooting_star' }, /pair shooting_star does not name it back/);
  bad(c => { c.patterns.find((p: any) => p.id === 'shooting_star').params.find((q: any) => q.key === 'body_max_pct').default = 40 }, /mirror shooting_star must take the same parameters/);
  bad(c => { c.patterns[0].params = c.patterns[0].params.filter((q: any) => q.key !== 'min_range_ticks') }, /every pattern takes min_range_ticks/);
  bad(c => { c.patterns[0].trend = 'up' }, /a bullish pattern follows a down trend/);
  bad(c => { c.tick_bands[2].below = 300 }, /bands rise/);
  bad(c => { c.patterns[12].rules[3].when = { open_beyond: 'gap' } }, /open_beyond = gap is not an option of piercing_line/);
});

/* ---- synthetic bars: a positive and a negative case per pattern -------------------------------------------------- */

const CASES: Record<string, { pos: Bar[]; neg: Bar[]; why: string }> = {
  hammer: { pos: [...ctx('down'), [2750, 2760, 2700, 2760]], neg: [...ctx('down'), [2720, 2760, 2700, 2760]], why: 'body 67 % of the range' },
  hanging_man: { pos: [...ctx('up'), [2250, 2260, 2200, 2260]], neg: [...ctx('down'), [2250, 2260, 2200, 2260]], why: 'the same shape after a decline' },
  inverted_hammer: { pos: [...ctx('down'), [2760, 2810, 2750, 2750]], neg: [...ctx('down'), [2760, 2810, 2730, 2750]], why: 'lower shadow 25 % of the range' },
  shooting_star: { pos: [...ctx('up'), [2240, 2300, 2240, 2250]], neg: [...ctx('down'), [2240, 2300, 2240, 2250]], why: 'the same shape after a decline' },
  dragonfly_doji: { pos: [...ctx('down'), [2760, 2760, 2700, 2760]], neg: [...ctx('down'), [2760, 2780, 2700, 2760]], why: 'upper shadow 25 % of the range' },
  gravestone_doji: { pos: [...ctx('up'), [2250, 2310, 2250, 2250]], neg: [...ctx('up'), [2250, 2310, 2230, 2250]], why: 'lower shadow 25 % of the range' },
  bullish_marubozu: { pos: [...ctx('down'), [2760, 2860, 2760, 2860]], neg: [...ctx('down'), [2760, 2860, 2700, 2860]], why: 'body 62 % of the range' },
  bearish_marubozu: { pos: [...ctx('up'), [2860, 2860, 2760, 2760]], neg: [...ctx('up'), [2770, 2780, 2760, 2760]], why: 'body 10, below the average body' },
  bullish_engulfing: { pos: [...ctx('down'), [2760, 2770, 2710, 2720], [2720, 2780, 2710, 2770]], neg: [...ctx('down'), [2760, 2770, 2710, 2720], [2720, 2780, 2710, 2750]], why: 'closes below the black open' },
  bearish_engulfing: { pos: [...ctx('up'), [2240, 2290, 2230, 2280], [2280, 2290, 2220, 2230]], neg: [...ctx('up'), [2240, 2290, 2230, 2280], [2270, 2290, 2220, 2230]], why: 'opens below the white close' },
  bullish_harami: { pos: [...ctx('down'), [2760, 2770, 2650, 2660], [2690, 2720, 2680, 2710]], neg: [...ctx('down'), [2760, 2770, 2650, 2660], [2670, 2740, 2660, 2730]], why: 'inside body 60 % of the first' },
  bearish_harami: { pos: [...ctx('up'), [2240, 2350, 2230, 2340], [2300, 2310, 2270, 2280]], neg: [...ctx('up'), [2240, 2350, 2230, 2340], [2350, 2360, 2270, 2280]], why: 'opens above the first body' },
  piercing_line: { pos: [...ctx('down'), [2760, 2770, 2650, 2660], [2650, 2730, 2640, 2720]], neg: [...ctx('down'), [2760, 2770, 2650, 2660], [2650, 2710, 2640, 2700]], why: 'closes 40 % into the black body' },
  dark_cloud_cover: { pos: [...ctx('up'), [2240, 2350, 2230, 2340], [2350, 2360, 2270, 2280]], neg: [...ctx('up'), [2240, 2350, 2230, 2340], [2340, 2360, 2270, 2280]], why: 'opens at the white close, not above' },
  tweezer_bottom: { pos: [...ctx('down'), [2760, 2770, 2700, 2720], [2720, 2770, 2710, 2760]], neg: [...ctx('down'), [2760, 2770, 2700, 2720], [2720, 2770, 2680, 2760]], why: 'lows 2 ticks apart' },
  tweezer_top: { pos: [...ctx('up'), [2240, 2300, 2230, 2280], [2280, 2300, 2230, 2240]], neg: [...ctx('up'), [2240, 2300, 2230, 2280], [2280, 2320, 2230, 2240]], why: 'highs 2 ticks apart' },
  morning_star: { pos: [...ctx('down'), [2760, 2770, 2650, 2660], [2660, 2680, 2640, 2670], [2670, 2740, 2660, 2730]], neg: [...ctx('down'), [2760, 2770, 2650, 2660], [2660, 2680, 2640, 2670], [2670, 2710, 2660, 2700]], why: 'the third closes 40 % into the first body' },
  evening_star: { pos: [...ctx('up'), [2240, 2350, 2230, 2340], [2340, 2360, 2320, 2330], [2330, 2340, 2260, 2270]], neg: [...ctx('up'), [2240, 2350, 2230, 2340], [2340, 2390, 2320, 2380], [2330, 2340, 2260, 2270]], why: 'the star\'s body is 40 % of the first' },
  three_white_soldiers: { pos: [...ctx('down'), [2760, 2830, 2750, 2820], [2800, 2880, 2790, 2870], [2850, 2930, 2840, 2920]], neg: [...ctx('down'), [2760, 2830, 2750, 2820], [2830, 2880, 2790, 2870], [2850, 2930, 2840, 2920]], why: 'the second opens above the first body' },
  three_black_crows: { pos: [...ctx('up'), [2240, 2250, 2170, 2180], [2200, 2210, 2120, 2130], [2150, 2160, 2070, 2080]], neg: [...ctx('up'), [2240, 2250, 2170, 2180], [2200, 2210, 2120, 2130], [2150, 2160, 2070, 2140]], why: 'the third closes above the second' },
};

test('synthetic bars: each pattern on its positive case, not on its negative case (and the oracle agrees)', () => {
  assert.deepEqual(Object.keys(CASES).sort(), [...CANDLE_IDS].sort());
  for (const id of CANDLE_IDS) {
    const { pos, neg, why } = CASES[id];
    assert.equal(last(id, pos), 1, `${id}: positive case`);
    assert.equal(last(id, neg), 0, `${id}: negative case (${why})`);
    assert.equal(oracle(id, barsOf(pos), allDefaults(id)).at(-1), 1, `${id}: oracle positive`);
    assert.equal(oracle(id, barsOf(neg), allDefaults(id)).at(-1), 0, `${id}: oracle negative`);
    // the signal is on the pattern's last candle only
    const s = candleSignal(barsOf(pos), id);
    assert.equal(s.reduce((a, b) => a + b, 0) >= 1 && s.slice(0, 12).every(x => x === 0), true, `${id}: no signal inside the trend context`);
  }
  // Hammer and Hanging Man are one shape: after a rise the hammer is not flagged, the hanging man is
  assert.equal(last('hammer', CASES.hanging_man.pos), 0);
  assert.equal(last('shooting_star', CASES.inverted_hammer.pos), 0);
});

test('the trend before the pattern: average and change, read on the session before candle 1', () => {
  const pos = CASES.hammer.pos;
  assert.equal(last('hammer', pos, { trend: 'change', trend_length: 5 }), 1);
  // a last context close above its average (a bounce on the session before) is no decline, whatever the shape
  const bounce = [...ctx('down').slice(0, 11), [2780, 2900, 2770, 2890] as Bar, [2750, 2760, 2700, 2760] as Bar];
  assert.equal(last('hammer', bounce), 0);
  assert.equal(last('hammer', bounce, { trend: 'change', trend_length: 2 }), 0);
  assert.equal(last('hammer', bounce, { trend: 'change', trend_length: 11 }), 1, 'close 2890 below the close 11 sessions earlier (2980): a decline by change');
  // a pattern that offers none: the trend test off finds the shape after a rise too
  assert.equal(last('bullish_engulfing', [...ctx('up'), [2240, 2250, 2190, 2200], [2200, 2260, 2190, 2250]]), 0);
  assert.equal(last('bullish_engulfing', [...ctx('up'), [2240, 2250, 2190, 2200], [2200, 2260, 2190, 2250]], { trend: 'none' }), 1);
  // too few sessions before the pattern for the trend: never a pattern
  assert.equal(last('hammer', pos.slice(-6)), 0);
  assert.equal(last('hammer', pos.slice(-11)), 1, 'exactly trend_length sessions before candle 1');
});

/* ---- the IDX guards ------------------------------------------------------------------------------------------------ */

test('guard: a day without trades (O=H=L=C, volume 0) or a missing bar is never a pattern candle, not a doji', () => {
  const flat0: Bar = [2760, 2760, 2760, 2760, 0], flatV: Bar = [2760, 2760, 2760, 2760, 5000];
  for (const id of ['dragonfly_doji', 'gravestone_doji', 'hammer', 'hanging_man'])
    for (const b of [flat0, flatV]) for (const c of ['down', 'up'] as const) assert.equal(last(id, [...ctx(c), b], id === 'hammer' || id === 'hanging_man' ? {} : { trend: 'none' }), 0, `${id} on ${b}`);
  // the doji rules alone accept a flat bar (100 x 0 <= 10 x 0): the guard is what refuses it
  assert.equal(patternBar(barsOf([flat0]), 0, 1), false); assert.equal(patternBar(barsOf([flatV]), 0, 1), false);
  assert.equal(last('dragonfly_doji', [...ctx('down'), [2760, 2760, 2730, 2760, 5000]]), 1, 'the same bar with a 3-tick range traded');
  // a hammer shape with volume 0, or with no volume (an index), is not a candle of a pattern
  for (const v of [0, null]) assert.equal(last('hammer', [...ctx('down'), [2750, 2760, 2700, 2760, v]]), 0, `volume ${v}`);
  // a missing price in a candle, or inconsistent prices (close above the high)
  assert.equal(last('bullish_engulfing', [...ctx('down'), [2760, 2770, 2710, null] as unknown as Bar, [2720, 2780, 2710, 2770]]), 0);
  assert.equal(last('hammer', [...ctx('down'), [2750, 2755, 2700, 2760]]), 0);
  // a missing close in the trend's sessions: no trend, no pattern (as an average with a hole)
  const hole = CASES.hammer.pos.map((b, k) => k === 8 ? [b[0], b[1], b[2], null] as unknown as Bar : b);
  assert.equal(last('hammer', hole), 0);
  assert.equal(last('hammer', hole, { trend_length: 3 }), 1, 'a shorter trend window that does not reach the hole');
  // a missing open in the average body's sessions
  const avgHole = CASES.bullish_marubozu.pos.map((b, k) => k === 6 ? [null, b[1], b[2], b[3]] as unknown as Bar : b);
  assert.equal(last('bullish_marubozu', avgHole), 0);
  assert.equal(last('bullish_marubozu', avgHole, { body_avg_length: 4 }), 1);
});

test('guard: the minimum range is counted in price ticks of the bar\'s own price band (IDX fractions), not per stock', () => {
  for (const [p, t] of [[1, 1], [199, 1], [200, 2], [499, 2], [500, 5], [1999, 5], [2000, 10], [4999, 10], [5000, 25], [26100, 25]]) assert.equal(tickSize(p), t, `tick of ${p}`);
  assert.equal(ticksBetween(495, 505), 3.5);                                 // 5 / 2 below 500, 5 / 5 above
  assert.equal(ticksBetween(505, 495), 3.5);
  assert.equal(ticksBetween(1990, 2030), 2 + 3);
  assert.equal(ticksBetween(4975, 5050), 2.5 + 2);
  for (const [a, b] of [[495, 505], [150, 210], [1990, 2030], [4975, 5050], [1.5, 7777]]) assert.equal(oracleTicks(a, b), ticksBetween(a, b));
  // the same hammer shape: range 20 at Rp 3,000 is 2 ticks (refused at the default 3), at Rp 150 it is 20 ticks
  const low = (range: number): Bar[] => Array.from({ length: 12 }, (_, j) => { const c = 190 - j; return [c + 1, c + 2, c - 1, c] as Bar }).concat([[170, 170, 170 - range, 170]]);
  assert.equal(last('hammer', [...ctx('down'), [2760, 2760, 2740, 2760]]), 0, 'range 20 at Rp 2,760: 2 ticks');
  assert.equal(last('hammer', [...ctx('down'), [2760, 2760, 2740, 2760]], { min_range_ticks: 2 }), 1);
  assert.equal(last('hammer', [...ctx('down'), [2760, 2760, 2730, 2760]]), 1, 'range 30: 3 ticks');
  assert.equal(last('hammer', low(2)), 0, 'range 2 at Rp 170: 2 ticks');
  assert.equal(last('hammer', low(2), { min_range_ticks: 2 }), 1);
  assert.equal(last('hammer', low(20)), 1, 'range 20 at Rp 170: 20 ticks');
  // every candle of a pattern: a 2-tick inside candle stops a harami
  assert.equal(last('bullish_harami', [...ctx('down'), [2760, 2770, 2650, 2660], [2690, 2700, 2680, 2700]]), 0);
  assert.equal(last('bullish_harami', [...ctx('down'), [2760, 2770, 2650, 2660], [2690, 2700, 2680, 2700]], { min_range_ticks: 2 }), 1);
});

test('guard: the star\'s relaxed body gap, and the piercing / dark cloud open', () => {
  const ms = CASES.morning_star.pos;                                          // the star's top reaches 10 % into the first body
  assert.equal(last('morning_star', ms), 1);
  assert.equal(last('morning_star', ms, { star_overlap_pct: 9 }), 0);
  assert.equal(last('morning_star', ms, { star_overlap_pct: 0 }), 0);
  const gap = [...ctx('down'), [2760, 2770, 2650, 2660], [2640, 2650, 2610, 2630], [2640, 2740, 2630, 2730]] as Bar[];
  assert.equal(last('morning_star', gap, { star_overlap_pct: -20 }), 1, 'a real gap of 20 % of the first body');
  assert.equal(last('morning_star', gap, { star_overlap_pct: -21 }), 0);
  const pl = CASES.piercing_line.pos;                                         // opens at the black low, below its close
  assert.equal(last('piercing_line', pl), 1);
  assert.equal(last('piercing_line', pl, { open_beyond: 'range' }), 0, 'the classic gap below the low is not there');
  assert.equal(last('piercing_line', [...ctx('down'), [2760, 2770, 2650, 2660], [2640, 2730, 2630, 2720]], { open_beyond: 'range' }), 1);
  assert.equal(last('dark_cloud_cover', CASES.dark_cloud_cover.pos, { open_beyond: 'range' }), 0);
});

test('parameters are checked, never adjusted: each refusal names the field, the range and a right and a wrong example', () => {
  const p = (id: string, params: unknown) => codeOf(() => candleSignal(barsOf(CASES.hammer.pos), id, params));
  assert.deepEqual(p('hammer', { width: 3 })!.slice(0, 2), ['PARAM_NOT_ACCEPTED', 'pattern.params.width']);
  const r = p('hammer', { body_max_pct: 150 })!;
  assert.deepEqual(r.slice(0, 2), ['PARAM_OUT_OF_RANGE', 'pattern.params.body_max_pct']);
  assert.match(r[2] as string, /a number from 0 to 100 \(right: 30; wrong: 150\)/);
  assert.match(p('hammer', { trend: 'none' })![2] as string, /must be one of average, change/);
  assert.deepEqual(p('hammer', { trend_length: 2.5 })!.slice(0, 2), ['INVALID_PARAM', 'pattern.params.trend_length']);
  assert.deepEqual(p('hammer', null)!.slice(0, 2), ['INVALID_PARAMS', 'pattern.params']);
  assert.deepEqual(p('hammer', { min_range_ticks: 0 })!.slice(0, 2), ['PARAM_OUT_OF_RANGE', 'pattern.params.min_range_ticks']);
  const u = p('cup_and_handle', {})!;
  assert.deepEqual(u.slice(0, 2), ['UNKNOWN_CONDITION', 'pattern.type']);
  assert.match(u[2] as string, /use one of hammer, hanging_man/);
  assert.deepEqual(Object.keys(resolveCandleParams('morning_star', {})), CANDLES.patterns.find(x => x.id === 'morning_star')!.params.map(q => q.key));
});

/* ---- symmetry ------------------------------------------------------------------------------------------------------- */

function seeded(seed: number) { let s = seed >>> 0; return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296) }
/** IDX-like random bars on a tick grid (opens at or near the previous close, tick-sized bodies and shadows, some days
    without trades), inside [lo, hi]. */
function randomBars(n: number, seed: number, lo: number, hi: number, tickOf: (p: number) => number, holes = false): B {
  const r = seeded(seed), b: B = { O: [], H: [], L: [], C: [], V: [] };
  let c = Math.round((lo + hi) / 2 / tickOf((lo + hi) / 2)) * tickOf((lo + hi) / 2), drift = 0;
  for (let i = 0; i < n; i++) {
    if (i % 40 === 0) drift = (r() - 0.5) * 3;
    const t = tickOf(c), snap = (x: number) => Math.min(hi, Math.max(lo, Math.round(x / t) * t));
    if (r() < 0.03) { b.O.push(c); b.H.push(c); b.L.push(c); b.C.push(c); b.V.push(0); continue }   // no trade
    const o = snap(c + (r() < 0.7 ? 0 : Math.round((r() - 0.5) * 4) * t));
    const cl = snap(o + Math.round((r() - 0.5 + drift / 10) * 12) * t);
    const h = snap(Math.max(o, cl) + Math.floor(r() * r() * 8) * t), l = snap(Math.min(o, cl) - Math.floor(r() * r() * 8) * t);
    b.O.push(o); b.H.push(h); b.L.push(l); b.C.push(cl); b.V.push(1 + Math.floor(r() * 1e6)); c = cl;
    if (holes && r() < 0.01) { const k = Math.floor(r() * 5); (['O', 'H', 'L', 'C', 'V'] as const).forEach((f, j) => { if (j === k) b[f][i] = null }) }
    if (holes && r() < 0.005) b.H[i] = (b.L[i] as number) - t;               // an inconsistent bar
  }
  return b;
}
const M = 7000;
const mirrored = (b: B): B => ({ O: b.O.map(x => M - (x as number)), H: b.L.map(x => M - (x as number)), L: b.H.map(x => M - (x as number)), C: b.C.map(x => M - (x as number)), V: b.V });
/** Random parameters inside each one's range (whole numbers for integers; enum options by chance). */
function randomParams(id: string, r: () => number, loose: boolean): CandleParams {
  const p = CANDLES.patterns.find(x => x.id === id)!, out: CandleParams = {};
  for (const q of p.params) {
    if (q.type === 'enum') { out[q.key] = q.options![Math.floor(r() * q.options!.length)]; continue }
    const lo = q.min!, hi = q.key === 'trend_length' || q.key === 'body_avg_length' ? Math.min(q.max!, 30) : q.max!;
    let v = lo + r() * (hi - lo);
    if (loose && q.key === 'min_range_ticks') v = 1 + r() * 3;
    out[q.key] = q.type === 'integer' ? Math.round(v) : Math.round(v * 4) / 4;
  }
  return out;
}

test('symmetry: on mirrored prices each pattern becomes its mirror (bullish <-> bearish), bar for bar', () => {
  const tick10 = () => 10, fired = new Map<string, number>();
  for (let k = 0; k < 6; k++) {
    const b = randomBars(3000, 77 + k, 2010, 4990, tick10), m = mirrored(b), r = seeded(900 + k);
    for (const p of CANDLES.patterns) for (let v = 0; v < 4; v++) {
      const params = v === 0 ? undefined : randomParams(p.id, r, v > 1);
      const a = candleSignal(b, p.id, params), z = candleSignal(m, p.mirror, params);
      assert.deepEqual([...z], [...a], `${p.id} vs ${p.mirror} on mirrored prices (${k}, ${JSON.stringify(params)})`);
      fired.set(p.id, (fired.get(p.id) || 0) + a.reduce((s, x) => s + x, 0));
    }
  }
  for (const id of CANDLE_IDS) assert.ok((fired.get(id) || 0) > 0, `${id} never fired on the random bars: the symmetry check would be empty`);
  // and the hand-made cases: the mirror of each positive case is a positive case of the mirror pattern
  for (const p of CANDLES.patterns) assert.equal(last(p.mirror, CASES[p.id].pos.map(([o, h, l, c]) => [M - o, M - l, M - h, M - c] as Bar)), 1, `${p.id} mirrored`);
});

/* ---- independent recomputation ---------------------------------------------------------------------------------- */

const fixtures = loadFixtures().map((f: any) => ({ ticker: f.ticker as string, bars: { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V } }));
const same = (a: ArrayLike<number>, b: ArrayLike<number>, what: string) => {
  assert.equal(a.length, b.length, what);
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) assert.fail(`${what}: bar ${i}: core ${a[i]}, oracle ${b[i]}`);
};

test('independent recomputation: the oracle written from the definitions gives the same signal bar for bar', () => {
  const r = seeded(4242);
  let ones = 0;
  for (const { ticker, bars } of fixtures) for (const id of CANDLE_IDS) for (let v = 0; v < 4; v++) {
    const params = v === 0 ? undefined : randomParams(id, r, v === 3);
    const core = candleSignal(bars, id, params);
    same(core, oracle(id, bars, resolveCandleParams(id, params)), `${ticker} ${id} ${JSON.stringify(params)}`);
    ones += core.reduce((s, x) => s + x, 0);
  }
  assert.ok(ones > 2000, `the fixtures fire ${ones} signals`);
  // random bars across every price band, with missing values, days without trades and inconsistent bars
  const bands = (p: number) => tickSize(p);
  for (const [k, lo, hi] of [[1, 51, 199], [2, 150, 700], [3, 400, 2600], [4, 1800, 6000], [5, 4500, 30000]] as const) {
    const b = randomBars(2500, k, lo, hi, bands, true);
    for (const id of CANDLE_IDS) for (let v = 0; v < 3; v++) {
      const params = v === 0 ? undefined : randomParams(id, r, true);
      same(candleSignal(b, id, params), oracle(id, b, resolveCandleParams(id, params)), `random ${lo}-${hi} ${id} ${JSON.stringify(params)}`);
    }
  }
});

test('a signal reads exactly candleLookback bars: computed on its last lookback bars it is the same; on one fewer it never fires', () => {
  const b = randomBars(1200, 5150, 2010, 4990, () => 10), r = seeded(31);
  const cut = (x: B, from: number, to: number): B => ({ O: x.O.slice(from, to), H: x.H.slice(from, to), L: x.L.slice(from, to), C: x.C.slice(from, to), V: x.V.slice(from, to) });
  for (const id of CANDLE_IDS) for (let v = 0; v < 4; v++) {
    const params = v === 0 ? undefined : randomParams(id, r, true), w = candleLookback(id, params), full = candleSignal(b, id, params);
    for (let at = w + 3; at < 1200; at += 7) {
      const s = candleSignal(cut(b, at - w + 1, at + 1), id, params);
      assert.equal(s[s.length - 1], full[at], `${id} ${JSON.stringify(params)} at ${at} on its last ${w} bars`);
      assert.ok(!candleSignal(cut(b, at - w + 2, at + 1), id, params).some(x => x === 1), `${id} fires on ${w - 1} bars`);
    }
  }
  assert.equal(candleLookback('hammer'), 11);                                 // 1 candle + 10 trend sessions
  assert.equal(candleLookback('hammer', { trend: 'change' }), 12);
  assert.equal(candleLookback('bullish_marubozu'), 11);                       // trend none, average body of 10
  assert.equal(candleLookback('bullish_engulfing', { trend: 'none' }), 2);
  assert.equal(candleLookback('dragonfly_doji', { trend: 'none' }), 2);       // bar 0 is never true
  assert.equal(candleLookback('three_white_soldiers', { trend: 'none', body_avg_length: 4 }), 7);
});

test('events: on the bar, or within N sessions', () => {
  const s = Uint8Array.from([0, 1, 0, 0, 0, 1, 0]);
  assert.deepEqual([...eventWithin(s, 1)], [...s]);
  assert.deepEqual([...eventWithin(s, 3)], [0, 1, 1, 1, 0, 1, 1]);
  assert.deepEqual([...eventWithin(s, 10)], [0, 1, 1, 1, 1, 1, 1]);
  assert.deepEqual(codeOf(() => eventWithin(s, 0))!.slice(0, 2), ['INVALID_CONDITION', 'within']);
});

/* ---- frequency on the fixture stocks -------------------------------------------------------------------------------- */

test('frequency on the fixture stocks: every pattern fires, none on more than 6 % of the bars, none on an index without volume', () => {
  const rows: string[] = [], totals = new Map<string, number>();
  let stockBars = 0;
  for (const { ticker, bars } of fixtures) {
    const counts = CANDLE_IDS.map(id => candleSignal(bars, id).reduce((s, x) => s + x, 0));
    if (ticker === 'IHSG') { assert.deepEqual(counts, CANDLE_IDS.map(() => 0), 'IHSG has no volume: no candle of it is a pattern candle'); continue }
    stockBars += bars.C.length;
    CANDLE_IDS.forEach((id, k) => totals.set(id, (totals.get(id) || 0) + counts[k]));
    rows.push(`${ticker.padEnd(6)} ${String(bars.C.length).padStart(5)} ${counts.map(c => String(c).padStart(4)).join(' ')}`);
  }
  console.log(`# pattern frequency at the defaults (fixture stocks, ${stockBars} bars)\n# ${CANDLE_IDS.map((id, k) => `${k + 1}=${id}`).join(' ')}\n${rows.map(r => `# ${r}`).join('\n')}`);
  for (const id of CANDLE_IDS) {
    const n = totals.get(id)!, rate = n / stockBars;
    console.log(`# ${id.padEnd(22)} ${String(n).padStart(4)}  ${(1000 * rate).toFixed(2)} per 1,000 bars`);
    assert.ok(n > 0, `${id} never fires on the fixture stocks`);
    assert.ok(rate <= 0.06, `${id} fires on ${(100 * rate).toFixed(1)} % of the bars: an unreasonable rate`);
  }
});
