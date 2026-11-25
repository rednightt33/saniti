/* Builds apps/edge-bff/screener/src/core/screener-registry.json, the Screener's indicator contract (EXEC-SCREENER, go
   2026-10-28; report TARGET ARCHITECTURE 6.8 "One approved indicator contract"), from three inputs and nothing typed
   by hand:
   1. the base registry apps/edge-bff/backtest/src/core/backtest-registry.json, unchanged: it stays the only contract
      for ids, keys, parameters, types, defaults, min, max, options, not_accepted and outputs (labels and the workbook
      unit come from the Terminal's indRegistry.json it is built from);
   2. the hand-kept src/core/screener-overlay.json: product choices only (shape, allowed test forms per output with
      the prototype's operators and labels, search synonyms, a one-line description in our own plain English (the
      catalog's tooltip and search text), the card a new condition opens with, the options of an
      enum parameter a user decision narrows with its start value, today P17 a for the I43 anchor), explicit
      overrides with their evidence, and the provisional cost model of the caps (P5);
   3. fields derived here by running the Terminal's own formulas F (apps/edge-bff/terminal/src/calc/indicators.ts) on
      a deterministic synthetic series, for all 76 outputs: first_valid_bar, history_class (cut probe, and for the
      outputs it finds window the reach probe on four price shapes, UD36: reachProbe), for a recursive output its
      effective_window and that window's scaling rule (EXEC-PRICE-DISTORTION UD55: effectiveProbe, effectiveScaling),
      history_by_option and history_class_combined (UD52: the class and window at each enum or switch option,
      historyByOption), unit and
      level_comparable (scaling and shift probes), price_compare_lag (lag probe), inputs per enum option (poison
      probe), the narrowing (degeneracy probe at each numeric minimum, floor probe, the not_accepted rule),
      cost_class (work ratio at two lengths, counted by V8 block coverage, never timed; a class lowered from the
      committed registry's needs a reviewed reason in the overlay's cost_reviews, see costLowerings), and the Feature 04
      / Feature 01 parity oracle read from `python3 scripts/terminal_indicator_spec.py --json`.
   EXEC-SCREENER-FLOW-CANDLES P5a (verification/screener/P5_FLOW.md section 2): `flows`, the Terminal's 48 flow
   indicators generated from apps/edge-bff/terminal/src/data/flowRegistry.json (name, family, unit, place, tip and
   parameters as they are) with each output's kind from the hand-kept src/core/flow-kinds.json (flowEntries: the build
   stops when an FL or an output has no row); both files are sources of the version. P5b (section 3): the Screener's
   versions of FL18-FL20, FL23, FL44, FL45, FL34's point-in-time guard and the Screener's own entries (fnet, ksei_net),
   from the same file. P6 (verification/screener/P6_CANDLES.md): `candles`, the 20 candlestick patterns generated from
   the Backtest core's candle-registry.json through its candles.ts (candleEntries); both files are sources.
   EXEC-PRICE-DISTORTION D-5 (the user's go 2026-11-24): each flow output's `reads` (the broker lots, the close, the
   volume), `reads_from` and `reads_probe`, from the basis probe (basisReads: the output computed by flowscreener.ts
   computeEntry, a source, on flowprobe.ts's context with those inputs before a middle candle changed); the Screener
   marks a Flow cell from them (condition.ts).
   Every derived field is a pure function of the inputs and the code: nothing reads a clock, so the file and its version
   are the same bytes on any machine at any load (ERRORS: the timed cost_class flipped under CPU contention).
   The overlay and the derived narrowing may only narrow the base (report 6.8 narrow-only rule), so every transferable
   screener condition stays Backtest-valid. Nothing here changes indicators.ts, indRegistry.json or
   backtest-registry.json (report I3; scripts/screener/check_backtest_untouched.mjs).
   screener_registry_version = the first 16 hex of the sha256 of the canonical JSON of the generated document without
   that field (base registry_version and source hashes included), so it changes whenever any input or derived field does.

   Run (from apps/edge-bff/screener): npm run registry (writes) / npm run registry:check (fails when the committed file
   is stale: every probe field is re-derived and compared). Needs python3 for the oracle mapping. The cost probe runs
   in a child process of this script (--cost-work, see costWork). `--check --against <file>` compares the cost classes
   with that registry instead of the committed one (committedRegistry; the tests use it; never when writing). */
import '../../terminal/src/lab/index.ts';      // the lab formulas' one registration point, by path: vitest loads this file too (3f TR-2)
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { computeFlow } from '../../terminal/src/calc/flow.ts';
import { probeContext, probeLength, scaledBars, scaledLots, turnedContext } from '../src/core/flowprobe.ts';
import { computeEntry } from '../src/core/flowscreener.ts';
import { movingBars } from '../src/core/effective.ts';

const here = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(here, '../../../..');
const at = rel => path.join(ROOT, rel);
export const PATHS = {
  base: 'apps/edge-bff/backtest/src/core/backtest-registry.json',
  terminal: 'apps/edge-bff/terminal/src/data/indRegistry.json',
  calc: 'apps/edge-bff/terminal/src/calc/indicators.ts',
  coreRegistry: 'apps/edge-bff/backtest/src/core/registry.ts',
  hash: 'apps/edge-bff/backtest/src/core/hash.ts',
  overlay: 'apps/edge-bff/screener/src/core/screener-overlay.json',
  spec: 'scripts/terminal_indicator_spec.py',
  generator: 'apps/edge-bff/screener/scripts/build-screener-registry.mjs',
  loader: 'apps/backtest-worker/loader/register.mjs',
  out: 'apps/edge-bff/screener/src/core/screener-registry.json',
  // EXEC-BACKTEST-REVAMP P2 (K5 a, ERRORS M451): the lag probe's verdict for the Backtest core's own conditions
  compareLag: 'apps/edge-bff/backtest/src/core/compare-lag.json',
  flowRegistry: 'apps/edge-bff/terminal/src/data/flowRegistry.json',
  flowKinds: 'apps/edge-bff/screener/src/core/flow-kinds.json',
  flowCalc: 'apps/edge-bff/terminal/src/calc/flow.ts',
  flowProbe: 'apps/edge-bff/screener/src/core/flowprobe.ts',
  // EXEC-PRICE-DISTORTION D-5: the basis probe computes every entry through its computeEntry (basisReads)
  flowScreener: 'apps/edge-bff/screener/src/core/flowscreener.ts',
  candleRegistry: 'apps/edge-bff/backtest/src/core/candle-registry.json',
  candles: 'apps/edge-bff/backtest/src/core/candles.ts',
  // UD55: the effective-window probe counts moving bars as the lookback rule does (effective.ts movingBars)
  effective: 'apps/edge-bff/screener/src/core/effective.ts',
};

const sha256 = buf => crypto.createHash('sha256').update(buf).digest('hex');
const readJson = rel => JSON.parse(fs.readFileSync(at(rel), 'utf8'));

/* ---- vocabulary the overlay is checked against (report 6.9.1; contract.ts Shape, TestForm) ------------------- */
export const SHAPES = ['line', 'band', 'dir', 'osc', 'pair', 'adx', 'vol', 'cum'];
const VALUE_OPS = ['gt', 'lt', 'between'], STATE_OPS = ['gt', 'lt'], EVENT_OPS = ['crosses_above', 'crosses_below'];
/** Per test form: the operators it can take, what it needs from the output (derived fields) and the keys its card may
    open with (overlay `defaults`, all optional: the user fills a missing one). */
export const TEST_FORMS = {
  value: { ops: VALUE_OPS },
  value_pct_distance: { ops: VALUE_OPS, needs: 'close' },
  value_band_position: { ops: VALUE_OPS, needs: 'band' },
  state_level: { ops: STATE_OPS, needs: 'level' },
  state_value: { ops: STATE_OPS, defaults: ['value'] },
  state_output: { ops: STATE_OPS, with: true },
  state_instance: { ops: STATE_OPS },
  state_rising: { ops: ['gt'], defaults: ['bars'] },
  state_vs_ma: { ops: STATE_OPS, defaults: ['ma', 'length'] },
  event_level: { ops: EVENT_OPS, needs: 'level' },
  event_value: { ops: EVENT_OPS, defaults: ['value'] },
  event_output: { ops: EVENT_OPS, with: true },
  event_instance: { ops: EVENT_OPS },
  event_vs_ma: { ops: EVENT_OPS, defaults: ['ma', 'length'] },
  // EXEC-PINE-INDICATORS (the user 2026-11-23, Alpha KAMA "1a", "2a"): an output with categories (indRegistry outs[].
  // categories): in one of the chosen categories (transform in_categories), and changed from one category to another,
  // several changes joined by OR, within N sessions (transform category_change). `gt` is the form's one operator ("is").
  state_category: { ops: ['gt'], needs: 'categories', defaults: ['categories'] },
  event_category_change: { ops: ['gt'], needs: 'categories', defaults: ['changes'] },
};
/** An output's categories as indRegistry outs[].categories gives them: a non-empty list of {value: whole number, key:
    lower-case word, label}, values and keys unique; the problems, empty when there are none. */
export function categoryProblems(cats, where) {
  if (!Array.isArray(cats) || !cats.length) return [`${where}: categories must be a non-empty list`];
  const out = [];
  for (const c of cats) if (!c || !Number.isInteger(c.value) || typeof c.key !== 'string' || !/^[a-z][a-z0-9_]*$/.test(c.key) || typeof c.label !== 'string' || !c.label.trim())
    out.push(`${where}: each category needs a whole-number value, a key of lower-case letters, digits and _ and a label (${JSON.stringify(c)})`);
  if (new Set(cats.map(c => c?.value)).size !== cats.length || new Set(cats.map(c => c?.key)).size !== cats.length) out.push(`${where}: category values and keys must be unique`);
  return out;
}
/** The keys a default of a category form names, checked against the output's categories: `categories` a comma list of
    keys, `changes` a comma list of from>to pairs of two different keys. */
export function categoryDefaultProblems(k, v, cats, where) {
  const keys = new Set(cats.map(c => c.key)), items = typeof v === 'string' ? v.split(',').map(x => x.trim()).filter(Boolean) : [];
  if (!items.length) return [`${where}: default ${k} must name at least one ${k === 'categories' ? 'category' : 'change'}`];
  if (k === 'categories') return items.filter(x => !keys.has(x)).map(x => `${where}: ${x} is not a category (${[...keys]})`);
  return items.filter(x => { const [a, b, extra] = x.split('>'); return extra !== undefined || !keys.has(a) || !keys.has(b) || a === b }).map(x => `${where}: ${x} is not a change from>to of two categories (${[...keys]})`);
}
const MA_TYPES = ['SMA', 'EMA'];

/* ---- the deterministic synthetic series the probes run on -------------------------------------------------- */
/** The reach probe's price shapes (UD36, ERRORS M558 SC-3; EXEC-PRICE-DISTORTION step F2b): one series of one regime
    left a state that real prices keep for a long time unseen (the last swing of a trend, a long compression, a band
    the price stays outside of after a crash), so the window class was measured on a long uptrend, a crash, a sideways
    range and a recovery as well. Each shape is a list of stretches: `bars`, the volatility `vol` (sd of the log return
    per bar) and either `drift` (the mean log return per bar) or `revert` (the share of the log distance to the start
    price closed per bar, a range). */
const REACH_SHAPES = [
  { name: 'uptrend', stretches: [{ bars: 1500, drift: 0.0015, vol: 0.012 }] },
  { name: 'crash', stretches: [{ bars: 400, drift: 0.0004, vol: 0.012 }, { bars: 60, drift: -0.012, vol: 0.03 }, { bars: 1040, drift: 0.0002, vol: 0.012 }] },
  { name: 'sideways', stretches: [{ bars: 1500, revert: 0.05, vol: 0.01 }] },
  { name: 'recovery', stretches: [{ bars: 600, drift: -0.0018, vol: 0.014 }, { bars: 900, drift: 0.0022, vol: 0.014 }] },
];
/** The effective-window probe's price shapes (UD55; effectiveProbe): the reach shapes, and five regimes of IDX prices
    the reach shapes do not hold, each of which made a recursion remember longer on the real-price fixtures of
    apps/edge-bff/terminal/tests/calc/fixtures (measured 2026-11-25): a volatile small cap (`jump`: on a share `p` of the
    bars a move of `size` up or down on top of the noise, the daily limits of 25 % and more, with a volume that swings as
    much, `volume_vol`; DEWI, KOCI, CLAY), a calm trend, a stock pinned at one price for 250 sessions (`flat`: open,
    high, low and close equal to the last close; GOTO held 87 such sessions in 2026), a stock whose trading thins out to
    a thousandth for 300 sessions (`volume_level`: an average of volumes holds the busy sessions' level while the thin
    ones barely move it; KOCI traded 400 shares on 2025-04-09 and 38.9 million on 2025-05-09) and a stock trading at its
    floor in whole-rupiah ticks (`tick`, `floor`: every price rounded to the tick and never below the floor, so most
    sessions repeat a price, with sessions without trades, `idle`; GOTO, KOCI and ISEA at Rp 50). */
const EFFECT_SHAPES = [
  ...REACH_SHAPES,
  { name: 'jumpy', stretches: [{ bars: 1500, drift: 0, vol: 0.04, jump: { p: 0.03, size: 0.25 }, volume_vol: 1.5 }] },
  { name: 'calm', stretches: [{ bars: 1500, drift: 0.002, vol: 0.004 }] },
  { name: 'pinned', stretches: [{ bars: 300, drift: -0.004, vol: 0.02 }, { bars: 250, flat: true }, { bars: 950, drift: 0.002, vol: 0.02 }] },
  { name: 'thin', stretches: [{ bars: 400, drift: 0.0005, vol: 0.015 }, { bars: 300, drift: 0, vol: 0.01, volume_level: 0.001 }, { bars: 800, drift: 0.0005, vol: 0.015 }] },
  { name: 'floor', stretches: [{ bars: 250, drift: -0.012, vol: 0.02 }, { bars: 1000, drift: 0, vol: 0.02, tick: 1, floor: 50, idle: 0.3 }, { bars: 250, drift: 0.004, vol: 0.03, tick: 1, floor: 50 }] },
];
/** Probe settings; recorded in the generated file so a reader knows what the derived fields were measured on. */
export const PROBE = Object.freeze({
  seed: 20261028, bars: 4000, start: '2016-01-04', cut_at: 1000,
  scale_price: 3.7, scale_volume: 5.3, shift_price_of_median: 0.5, shift_volume_of_median: 0.5,
  tolerance: 1e-9, unit_tolerance: 1e-6, unit_from: 2000, min_common_bars: 100, converged_ratio: 1e-3,
  cost_bars: 10000, cost_long_length: 1000, cost_measure: 'v8_block_coverage_executed_source_chars', cost_tier: '--max-opt=1',
  cost_growth: 2, cost_margin: 2,
  // the reach probe (reachProbe): every shape cut at cut_from, cut_from + cut_every, ... while cut_margin bars remain
  reach: Object.freeze({ seed: 20261124, shapes: REACH_SHAPES, cut_from: 30, cut_every: 37, cut_margin: 300, tolerance: 1e-6 }),
  // the basis probe of the flow outputs (basisReads, EXEC-PRICE-DISTORTION D-5): the factors the lots, the closes and the
  // volumes of the candles up to t0 are multiplied by, the sessions every whole-number parameter is raised by in the
  // raised contexts, and the relative tolerance of a difference
  basis: Object.freeze({ lots_factors: Object.freeze([2, 0.5]), close_factor: 0.5, volume_factor: 2, raise_sessions: 4, tolerance: 1e-9 }),
  // the effective-window probe (effectiveProbe, UD55): `tolerance` is the user's (0.1 % of the output's magnitude), the
  // window is measured at `probe_tolerance` (a hundred times tighter, see the effective-window notes); every shape cut at
  // cut_from, cut_from + cut_every, ... while `room` bars follow the cut, a difference still there in the last `margin`
  // bars of a shape is not bounded; a difference that ends more than end_ratio times the tolerance was reset, one whose
  // later half reaches decay_ratio of the earlier half's (logs above the tolerance, halves of at least min_span moving
  // bars) does not decay (effectiveDecay); the scaling rule is fitted with every whole-number parameter raised by each
  // factor of `raise` (the first each alone and all together, the next all together) and checked, rung by rung, at the
  // factor of `checks` beside it and at `lower`, the rule's windows scaling_margin above the fitted curve; every number
  // parameter is tried at each of number_factors (effectiveScaling)
  effective: Object.freeze({
    seed: 20261125, shapes: EFFECT_SHAPES, tolerance: 1e-3, probe_tolerance: 1e-5, cut_from: 30, cut_every: 37, room: 1000, margin: 300,
    min_span: 10, end_ratio: 10, decay_ratio: 1.25, raise: Object.freeze([2, 4]), checks: Object.freeze([1.5, 3]), lower: 0.5,
    number_factors: Object.freeze([0.5, 2]), scaling_margin: 0.05,
  }),
});

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
}
/** OHLCV bars of a random walk with drift regimes (so bands are breached and trends turn), High >= max(Open, Close),
    Low <= min(Open, Close), positive volume, weekday dates (the VWAP anchors read them). Pure function of `opts`. */
export function fixture(opts = {}) {
  const { seed, bars: N, start } = { ...PROBE, ...opts };
  const rnd = mulberry32(seed), g = () => { const u = 1 - rnd(), v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) };
  const O = [], H = [], L = [], C = [], V = [], T = [];
  let c = 1000, mu = 0, t = Date.parse(`${start}T00:00:00Z`);
  for (let i = 0; i < N; i++) {
    if (i % 200 === 0) mu = (rnd() - 0.5) * 0.006;
    const o = c * (1 + 0.004 * g());
    c = c * Math.exp(mu + 0.02 * g());
    O.push(o); C.push(c); H.push(Math.max(o, c) * (1 + 0.008 * Math.abs(g()))); L.push(Math.min(o, c) * (1 - 0.008 * Math.abs(g())));
    V.push(Math.round(1e6 * Math.exp(0.6 * g())));
    while ([0, 6].includes(new Date(t).getUTCDay())) t += 864e5;
    T.push(new Date(t).toISOString().slice(0, 10)); t += 864e5;
  }
  return { O, H, L, C, V, T };
}
/** The OHLCV bars of one shape (PROBE.reach.shapes, PROBE.effective.shapes), built as fixture() builds its bars (the
    same open, high, low and volume noise, weekday dates from PROBE.start), the close following the shape's stretches.
    The effective probe's stretches may add `jump` ({p, size}: on a share p of the bars a move of size up or down),
    `volume_vol` (the sd of the log volume, 0.6 otherwise), `volume_level` (the volume's level, 1 otherwise; at least
    one share), `flat` (open, high, low and close equal to the last close), `idle` (on that share of the bars a session
    without trades: the prices of `flat` and no volume) or `tick` and `floor` (every price rounded to the tick, never
    below the floor); a stretch without them draws the same numbers in the same order as before they existed, so the
    reach probe's shapes are unchanged. Pure function of the shape and `seed`. */
export function shapeFixture(shape, seed) {
  const rnd = mulberry32(seed), g = () => { const u = 1 - rnd(), v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) };
  const O = [], H = [], L = [], C = [], V = [], T = [], c0 = 1000;
  let c = c0, t = Date.parse(`${PROBE.start}T00:00:00Z`);
  for (const s of shape.stretches) for (let k = 0; k < s.bars; k++) {
    const idle = s.idle !== undefined && rnd() < s.idle;
    if (s.flat || idle) { O.push(c); H.push(c); L.push(c); C.push(c) }
    else {
      const o = c * (1 + 0.004 * g()), mu = s.revert !== undefined ? s.revert * Math.log(c0 / c) : s.drift;
      let r = mu + s.vol * g();
      if (s.jump && rnd() < s.jump.p) r += (rnd() < 0.5 ? -1 : 1) * Math.log(1 + s.jump.size);
      c = c * Math.exp(r);
      let h = Math.max(o, c) * (1 + 0.008 * Math.abs(g())), l = Math.min(o, c) * (1 - 0.008 * Math.abs(g())), oo = o;
      if (s.tick) {
        const q = x => Math.max(s.floor ?? s.tick, Math.round(x / s.tick) * s.tick);
        oo = q(o); c = q(c); h = Math.max(oo, c, q(h)); l = Math.min(oo, c, q(l));
      }
      O.push(oo); C.push(c); H.push(h); L.push(l);
    }
    V.push(idle ? 0 : Math.max(1, Math.round(1e6 * (s.volume_level ?? 1) * Math.exp((s.volume_vol ?? 0.6) * g()))));
    while ([0, 6].includes(new Date(t).getUTCDay())) t += 864e5;
    T.push(new Date(t).toISOString().slice(0, 10)); t += 864e5;
  }
  return { O, H, L, C, V, T };
}
const mapBars = (B, f) => ({ O: B.O.map(f.p), H: B.H.map(f.p), L: B.L.map(f.p), C: B.C.map(f.p), V: B.V.map(f.v), T: B.T });
const sliceBars = (B, from) => ({ O: B.O.slice(from), H: B.H.slice(from), L: B.L.slice(from), C: B.C.slice(from), V: B.V.slice(from), T: B.T.slice(from) });
const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[s.length >> 1] };

/* ---- series helpers ------------------------------------------------------------------------------------------ */
const isN = v => typeof v === 'number' && Number.isFinite(v);
const finite = s => s.filter(isN);
const firstValid = s => { const i = s.findIndex(isN); return i < 0 ? null : i };
/** A series' magnitude for tolerances: its 99th percentile absolute value (1 when it has none). */
export function scaleOf(s) { const v = finite(s).map(Math.abs).sort((a, b) => a - b); return v.length ? Math.max(v[Math.floor((v.length - 1) * 0.99)], 1e-12) : 1 }
/** other[i] equals f(base[i]) on every bar from unit_from on where both are finite, the two have the same finite bars
    (on every bar), and there are at least min_common_bars such bars; equality within unit_tolerance x the larger
    magnitude. A unit is a property of the series once its start has decayed (ERRORS M555): a recursion that starts
    from 0 rather than from the first price (the Pine `nz(x[1])` start, Alpha KAMA I58) is a price level that only reaches
    the shifted level after some hundred bars, so its values are compared on the second half of the fixture (bar 2000 of
    4000), where such a start has decayed below the tolerance. Every released output's unit is the same either way (the
    registry check of 2026-11-23). The scaled and shifted inputs
    differ from the base by factors (3.7, 5.3) or offsets (half the median) far above it, while running sums and the
    E[x²] - E[x]² of a band leave residue up to about the square root of the double precision (2e-8 relative, measured
    on I43 upper1 at a period's first bar), so 1e-6 separates the cases with room on both sides. */
function related(base, other, f) {
  const b = base.map(v => isN(v) ? f(v) : null), tol = PROBE.unit_tolerance * Math.max(scaleOf(b), scaleOf(other));
  let n = 0;
  for (let i = 0; i < b.length; i++) {
    if (isN(b[i]) !== isN(other[i])) return false;
    if (!isN(b[i]) || i < PROBE.unit_from) continue;
    if (Math.abs(b[i] - other[i]) > tol) return false;
    n++;
  }
  return n >= PROBE.min_common_bars;
}
const sameSeries = (a, b) => a.length === b.length && a.every((v, i) => (isN(v) || isN(b[i])) ? v === b[i] : true);

/* ---- the probes (report 6.8 "fields derived at build time"); each takes F and returns plain data -------------- */

/** Cut probe: the output recomputed from bar cut_at on equals the full-history output wherever the cut has a value
    (window); differs at first but decays toward it (recursive: the median gap over the last 100 common bars is at most
    converged_ratio of the first 100); does not decay (cumulative: the level depends on the start bar). An indicator
    with an `anchor` parameter is calendar (report 6.8: "Calendar class comes from an anchor parameter"). */
export function historyClass(full, cut, cutAt, hasAnchor) {
  if (hasAnchor) return 'calendar';
  const tol = PROBE.tolerance * Math.max(scaleOf(full), 1), gaps = [];
  for (let i = 0; i < cut.length; i++) if (isN(cut[i]) && isN(full[cutAt + i])) gaps.push(Math.abs(cut[i] - full[cutAt + i]));
  if (gaps.length < 2 * PROBE.min_common_bars) throw new Error(`cut probe: only ${gaps.length} common bars`);
  if (gaps.every(d => d <= tol)) return 'window';
  const head = median(gaps.slice(0, 100)), tail = median(gaps.slice(-100));
  return tail <= tol || tail <= head * PROBE.converged_ratio ? 'recursive' : 'cumulative';
}

/** Reach probe, one cut (UD36, ERRORS M558 SC-3): the bars before its window that an output's value still depends on.
    The window class promises that the value at bar t reads only the bars t - firstValid .. t, firstValid being the
    output's first valid bar on that stock (evaluate.ts lookbackStart, the PRICE_BREAK_IN_LOOKBACK remark). So the
    output recomputed from the cut at bar cutAt must give, at every bar from cutAt + firstValid on, what the full history
    gives: both a value, equal within PROBE.reach.tolerance of the output's magnitude, or both none. The answer is the
    last bar where they differ, counted from that first bar (1: the window is one bar short), 0 when the promise holds.
    The tolerance is a share of the magnitude far above the residue running sums leave (MFI on real prices: 1e-7 on a
    scale of 100) and far below a state the cut left out (a 0/1 flag, a swing's price). */
export function reachBeyond(full, cut, cutAt) {
  const fv = firstValid(full);
  if (fv === null) return 0;
  const tol = PROBE.reach.tolerance * Math.max(scaleOf(full), 1);
  let last = -1;
  for (let i = fv; i < cut.length && cutAt + i < full.length; i++) {
    const a = cut[i], b = full[cutAt + i];
    if (isN(a) !== isN(b) || (isN(a) && Math.abs(a - b) > tol)) last = i;
  }
  return last < 0 ? 0 : last - fv + 1;
}
/** Reach probe (UD36): reachBeyond of each output on every shape of PROBE.reach (shapeFixture) at every cut, the
    longest kept with the shape and the cut that gave it. `run` computes the indicator at its start configuration. */
export function reachProbe(run, outputs) {
  const R = PROBE.reach, best = Object.fromEntries(outputs.map(o => [o, { beyond: 0, shape: null, cut: null }]));
  R.shapes.forEach((shape, k) => {
    const B = shapeFixture(shape, R.seed + k), full = run(B);
    for (let c = R.cut_from; c < B.C.length - R.cut_margin; c += R.cut_every) {
      const part = run(sliceBars(B, c));
      for (const o of outputs) {
        const beyond = reachBeyond(full[o], part[o], c);
        if (beyond > best[o].beyond) best[o] = { beyond, shape: shape.name, cut: c };
      }
    }
  });
  return best;
}
/** The history class of an output from both probes: the cut probe's class, except that an output the cut probe finds
    window while the reach probe finds its value depending on bars before its window (on any shape) reads the whole
    history: 'recursive', the existing class whose lookback is the whole history and whose start's effect ends (a state
    the start left out is rebuilt by a later swing, compression or band exit), rather than 'cumulative' (a level that
    depends on the start forever, which the page notes as such). Its reach is not bounded by a parameter (the last swing
    of Alpha Divergence can be a year old), and the contract has no window longer than the first valid bar. */
export const reachClass = (cutClass, beyond) => cutClass === 'window' && beyond > 0 ? 'recursive' : cutClass;

/* ---- the effective window (UD55; the user 2026-11-25, "3. Ok boleh": option (a) at 0.1 %; src/core/effective.ts) ----
   A recursive output reads its whole history, but a bar far enough back moves its value by less than the tolerance.
   The effective window is that distance, in moving bars (effective.ts: a bar moves on the output's fields when each of
   them changes), measured here per output and configuration on the shapes of PROBE.effective, as the cut probe
   measures: the output recomputed from a cut against the full history. The user's tolerance is 0.1 % of the output's
   magnitude (PROBE.effective.tolerance; scaleOf, so a value near zero is not judged on its own size); the window is
   measured at probe_tolerance, a hundred times tighter, because a cut of a synthetic shape leaves a smaller gap than
   real prices do: on the eight real-price fixtures the windows at 0.1 % were up to 1.5 times those of the shapes at
   0.1 % (EMA 20: 67 sessions on DEWI against 44), and the decay of a recursion is geometric, so a hundred times the
   tolerance covers a gap a hundred times larger. A price break is a larger gap than a cut: an unadjusted split of 1:5,
   1:2 or 2:1 planted on the fixtures every 97 bars moves every output by more than 0.1 % of its magnitude for at most
   0.78 of its window (measured 2026-11-25). The eight fixtures test both at 0.1 % (tests/core/reach.test.mjs). An
   output gets no window, and keeps the whole history, when its values are
   whole numbers (a flag, a direction, a category: a difference far below the tolerance in the recursion beneath can
   flip it at any later bar), when a difference lasts to the end of a shape (not bounded), or when it does not decay
   (effectiveDecay: a level held until a later bar resets it, the Parabolic SAR or a ratcheting band, or one a
   stochastic of a flat series amplifies). An output the reach probe moved out of window (a state a later swing rebuilds,
   UD36) keeps the whole history too: its reach is not bounded by a parameter (reachClass). */

/** One cut of the effective probe for one output (`full` and `cut` its series, `moving` the moving bars of the full
    bars on its fields, `tol` the tolerance in its units): the moving bars from the cut's own bar to the last bar where
    the output recomputed from the cut still differs from the full history (a value against none, or more than tol),
    whether that difference is still there in a shape's last PROBE.effective.margin bars (open: not bounded), and the
    cut's decay ratio (effectiveDecay). */
export function effectiveCut(full, cut, cutAt, moving, tol) {
  let last = -1;
  for (let i = 0; i < cut.length && cutAt + i < full.length; i++) {
    const a = cut[i], b = full[cutAt + i];
    if (isN(a) !== isN(b) || (isN(a) && Math.abs(a - b) > tol)) last = i;
  }
  let count = 0;
  for (let i = 0; i <= last; i++) count += moving[cutAt + i];
  return { moving: count, open: last >= 0 && cutAt + last >= full.length - PROBE.effective.margin, ...effectiveDecay(full, cut, cutAt, moving, tol, last) };
}
/** How one cut's difference ends (`last`: the last bar where it exceeds the tolerance `tol`), two ratios:
    - `decay`: the bars from the first where both have a value to `last`, split into two halves of moving bars; the log
      of the largest difference over the tolerance on the moving bars of the later half, divided by that of the earlier
      half (a value against none counts as infinite). A geometric decay (an EMA's (1 - alpha)^k) gives about a half, a
      difference a stochastic of a quiet series amplifies more than 1. 0 when the stretch holds fewer than
      PROBE.effective.min_span moving bars (too short to tell). Only moving bars count: on a bar that does not move a
      recursion holds its difference (RSI on a pinned price) and forgets it again once prices move;
    - `end`: the difference on `last` over the tolerance (infinite for a value against none). A recursion forgets a
      little on every bar, so its difference falls under the tolerance from just above it (an EMA of length n by a factor
      1 - 2 / (n + 1) a bar: at most 3 at n = 2); a difference that ends far above it was reset at once (a Parabolic SAR
      at a reversal, a ratcheting band at a flip, a swing level at a new swing), and such a reset can come at any later
      bar. */
export function effectiveDecay(full, cut, cutAt, moving, tol, last) {
  const diff = i => { const a = cut[i], b = full[cutAt + i]; return isN(a) && isN(b) ? Math.abs(a - b) : isN(a) !== isN(b) ? Infinity : 0 };
  let f0 = -1;
  for (let i = 0; i <= last; i++) if (isN(cut[i]) && isN(full[cutAt + i])) { f0 = i; break }
  // only the cut's warm-up differs (it has no value where the full history has one): nothing left to decay
  if (f0 < 0) return { decay: 0, end: 0 };
  // the end is read only where the difference ends inside moving bars (the min_span bars up to `last` and the one after
  // it): after bars that did not move, a recursion's averages have shrunk while its value held (RSI on a pinned price),
  // so the first moving bar ends the difference at once without a reset
  let steady = cutAt + last + 1 < full.length && !!moving[cutAt + last + 1];
  for (let i = Math.max(0, last - PROBE.effective.min_span + 1); i <= last && steady; i++) steady = !!moving[cutAt + i];
  const end = steady ? diff(last) / tol : 0;
  let span = 0;
  for (let i = f0; i <= last; i++) span += moving[cutAt + i];
  if (span < PROBE.effective.min_span) return { decay: 0, end };
  let k = 0, m1 = 0, m2 = 0;
  for (let i = f0; i <= last; i++) {
    if (!moving[cutAt + i]) continue;
    const d = diff(i);
    if (k < span / 2) m1 = Math.max(m1, d); else m2 = Math.max(m2, d);
    k++;
  }
  const l1 = Math.log(Math.max(m1, tol) / tol), l2 = Math.log(Math.max(m2, tol) / tol);
  return { decay: l2 === Infinity ? Infinity : l1 > 0 ? l2 / l1 : l2 > 0 ? Infinity : 0, end };
}
/** The reasons an output with the class recursive has no effective window (it reads the whole history): its values are
    whole numbers, a difference lasts to the end of a shape (not bounded), a difference ends far above the tolerance
    (reset), a difference grows (no decay), or the reach probe moved it out of window (reachClass). */
export const EFFECTIVE_REASONS = ['discrete', 'not_bounded', 'reset', 'no_decay', 'reach'];
/** A ratio of effectiveDecay as the registry writes it: three significant digits, null for infinite. */
const ratio3 = x => Number.isFinite(x) ? Number(x.toPrecision(3)) : null;
/** Effective-window probe (UD55) of `outputs` at one configuration (`run` computes the indicator there): on every shape
    of PROBE.effective at every cut, effectiveCut at probe_tolerance times the output's magnitude on that shape, the
    moving bars counted on the output's fields there (`fieldsOf`). Per output: `bars`, the effective window (the most
    moving bars any cut still differs on, plus one: at bar t the value equals the full history's within the tolerance,
    whatever the bars before the first of the `bars` moving bars ending at t held), and `at`, the shape and the cut that
    gave it; or bars null with the reason (EFFECTIVE_REASONS) and the shape and cut that showed it; `decay` and `end`,
    the largest of each ratio over every cut (effectiveDecay; null: infinite). */
export function effectiveProbe(run, outputs, fieldsOf) {
  const E = PROBE.effective;
  const res = Object.fromEntries(outputs.map(o => [o, { moving: 0, at: null, open: null, decay: 0, decayAt: null, end: 0, endAt: null, whole: true, values: 0 }]));
  E.shapes.forEach((shape, k) => {
    const B = shapeFixture(shape, E.seed + k), full = run(B);
    const mv = Object.fromEntries(outputs.map(o => [o, movingBars(B, fieldsOf(o))]));
    const tol = Object.fromEntries(outputs.map(o => [o, E.probe_tolerance * scaleOf(full[o])]));
    for (const o of outputs) for (const v of full[o]) if (isN(v)) { res[o].values++; if (!Number.isInteger(v)) res[o].whole = false }
    for (let c = E.cut_from; B.C.length - c >= E.room; c += E.cut_every) {
      const part = run(sliceBars(B, c));
      for (const o of outputs) {
        const x = effectiveCut(full[o], part[o], c, mv[o], tol[o]), r = res[o];
        if (x.open && !r.open) r.open = `${shape.name}@${c}`;
        if (x.moving > r.moving) { r.moving = x.moving; r.at = `${shape.name}@${c}` }
        if (x.decay > r.decay) { r.decay = x.decay; r.decayAt = `${shape.name}@${c}` }
        if (x.end > r.end) { r.end = x.end; r.endAt = `${shape.name}@${c}` }
      }
    }
  });
  return Object.fromEntries(outputs.map(o => {
    const r = res[o], ratios = { decay: ratio3(r.decay), end: ratio3(r.end) };
    if (r.whole && r.values) return [o, { bars: null, reason: 'discrete', at: null }];
    if (r.open) return [o, { bars: null, reason: 'not_bounded', at: r.open, ...ratios }];
    if (r.end > E.end_ratio) return [o, { bars: null, reason: 'reset', at: r.endAt, ...ratios }];
    if (r.decay >= E.decay_ratio) return [o, { bars: null, reason: 'no_decay', at: r.decayAt, ...ratios }];
    return [o, { bars: r.moving + 1, reason: null, at: r.at, ...ratios }];
  }));
}
/** The value of whole-number or number parameter p at `factor` times its start value `v`, within its range (a whole
    number rounded, at least 1, above an exclusive minimum), or null when that is the start value itself. */
function scaledParam(p, v, factor) {
  let x = v * factor;
  if (p.integer) x = factor >= 1 ? Math.round(x) : Math.floor(x);
  if (p.max !== undefined) x = Math.min(p.max, x);
  const lo = p.min !== undefined ? p.min : p.integer ? 1 : -Infinity;
  if (p.exclusive_min ? x <= lo : x < lo) { if (!p.integer) return null; x = p.exclusive_min ? lo + 1 : lo }
  if (p.integer) x = Math.max(1, x);
  return x === v ? null : x;
}
/** The scaling rule of the effective windows `W0` (output -> bars at the start configuration `base`) of one indicator
    (UD55: "RSI 100 remembers longer than RSI 14"). `probeAt(over)` is effectiveProbe of those outputs with `over`
    applied to the start configuration; `params` the indicator's parameters as the registry writes them (integer, min,
    max, exclusive_min). The rule, per output:
      W(p) = W0 at R = 1, else ceil(W0 x R^exponent x (1 + margin))  for R <= max_ratio,
      R = max(1, the largest p_k / start_k over the whole-number parameters);
    a recursion's memory grows about in proportion to its lengths, and the exponent (at least 1, rounded up to three
    decimals) takes up what grows faster (a longer EMA lags further, so a cut leaves it a larger gap: 98, 150, 199 and
    440 bars at lengths 20, 30, 40 and 80). It is fitted and checked rung by rung, on the factors of PROBE.effective.raise:
    on the first, every whole-number parameter raised by it alone and all of them together, on each later one all
    together; the exponent is the smallest that holds on every probe of the rung and the ones before, and the rung
    stands when the rule also holds at the factor of `checks` beside it (all together, a setting it was not fitted on).
    The window of a probe is a maximum over cuts, so at a setting between two fitted ones another cut can lead and the
    window lie a bar or two above the fitted curve (EMA 30: 150 bars, the curve through 98 and 199 gives 148.3): the
    rule's windows stand PROBE.effective.scaling_margin (5 %) above it, and the check holds them to that. max_ratio is the
    largest factor whose rung stands (1: none): above it, where the rule was not shown to hold, the output reads the
    whole history. A probe without a window (a difference not bounded, reset or growing) or above the rule ends the
    rungs there. `lower` (all together at PROBE.effective.lower) must not remember longer than W0, so a setting with a
    parameter below its start value reads W0 at R = 1 only when that holds. Every number parameter (not a whole number)
    is tried alone at each of number_factors x its start value: number_ranges[key] is the range of the tried values, the
    start value with them, whose window stays at most W0; outside it the output reads the whole history. `probes`
    records every measurement (role fit, check, lower or number) and `stopped` why the rungs ended, if they did. */
export function effectiveScaling(probeAt, params, base, W0) {
  const E = PROBE.effective, outs = Object.keys(W0);
  const ints = params.filter(p => p.integer && isN(base[p.key]) && base[p.key] > 0);
  const nums = params.filter(p => p.type === 'number' && !p.integer && isN(base[p.key]) && base[p.key] !== 0);
  const ratio = over => Math.max(1, ...ints.map(p => (over[p.key] ?? base[p.key]) / base[p.key]));
  const all = f => Object.fromEntries(ints.map(p => [p.key, scaledParam(p, base[p.key], f)]).filter(([, v]) => v !== null));
  const out = Object.fromEntries(outs.map(o => [o, { whole_number: ints.map(p => p.key), exponent: 1, margin: E.scaling_margin, max_ratio: 1, lower: true, number_ranges: {}, probes: [], stopped: null }]));
  const measure = (over, role) => {
    const got = probeAt(over);
    for (const o of outs) out[o].probes.push({ role, params: over, ratio: ratio(over), bars: got[o].bars });
    return got;
  };
  const low = all(E.lower);
  if (Object.keys(low).length) {
    const got = measure(low, 'lower');
    for (const o of outs) if (got[o].bars === null || got[o].bars > W0[o]) out[o].lower = false;
  }
  let alive = [...outs];
  E.raise.forEach((f, rung) => {
    const top = all(f), fits = rung ? [top] : [...Object.entries(top).map(([k, v]) => ({ [k]: v })), ...(Object.keys(top).length > 1 ? [top] : [])];
    if (!alive.length || !Object.keys(top).length) return;
    const cand = Object.fromEntries(alive.map(o => [o, out[o].exponent])), failed = {};
    const fit = (got, over) => { const R = ratio(over); for (const o of alive) { const b = got[o].bars;
      if (b === null) failed[o] ??= `${JSON.stringify(over)}: ${got[o].reason}`;
      else if (R > 1 && b > W0[o]) cand[o] = Math.max(cand[o], Math.log(b / W0[o]) / Math.log(R)) } };
    for (const over of fits) fit(measure(over, 'fit'), over);
    for (const o of alive) cand[o] = Math.ceil(cand[o] * 1000 - 1e-9) / 1000;
    const chk = all(E.checks[rung]);
    if (Object.keys(chk).length) {
      const got = measure(chk, 'check'), R = ratio(chk);
      for (const o of alive) { const b = got[o].bars, bound = Math.ceil(W0[o] * R ** cand[o] * (1 + E.scaling_margin));
        if (b === null) failed[o] ??= `${JSON.stringify(chk)}: ${got[o].reason}`;
        else if (b > bound) failed[o] ??= `${JSON.stringify(chk)}: ${b} bars, above the rule's ${bound}`; }
    }
    for (const o of alive) {
      if (failed[o]) { out[o].stopped = `x${f}: at ${failed[o]}`; continue }
      out[o].exponent = cand[o]; out[o].max_ratio = ratio(top);
    }
    alive = alive.filter(o => !failed[o]);
  });
  for (const p of nums) {
    const tried = E.number_factors.map(f => scaledParam(p, base[p.key], f)).filter(v => v !== null);
    const ok = Object.fromEntries(outs.map(o => [o, [base[p.key]]]));
    for (const v of tried) {
      const got = measure({ [p.key]: v }, 'number');
      for (const o of outs) if (got[o].bars !== null && got[o].bars <= W0[o]) ok[o].push(v);
    }
    for (const o of outs) out[o].number_ranges[p.key] = [Math.min(...ok[o]), Math.max(...ok[o])];
  }
  return out;
}

/** The history classes in order of how much history they read; where several apply, the worst one holds. */
export const HISTORY_ORDER = ['window', 'calendar', 'recursive', 'cumulative'];
export const worstClass = classes => classes.reduce((w, c) => HISTORY_ORDER.indexOf(c) > HISTORY_ORDER.indexOf(w) ? c : w, 'window');
/** UD52 (the user 2026-11-25, "3. Ok boleh": option (a), "one class per output and setting (the generator probes each
    basis; the remark rule reads the class of the setting in use)"): Bollinger Bands, %B and Band Width read a window at
    the SMA basis and the whole history at EMA or RMA, ATR a window at SMA or WMA smoothing, so one class per output was
    wrong at some settings. Per output: `byOption` (history_by_option) param -> option -> the history at that option with
    every other parameter at the start configuration (historyAt: the class, and for a recursive output its effective
    window there, without a scaling rule), for every offered option of every enum parameter and both values of every
    switch (as inputs_by_source probes each option), kept only where it differs from the start configuration's;
    `combined` (history_class_combined) the worst class over every combination of two or more options away from the
    start, kept only for an output where some combination reads more history than the worst of its options alone (the
    rule the lookback reads otherwise, registry.ts historyOf), so no setting is classed below what it reads; `scaling`,
    `scale` of the start configuration's effective windows (effectiveScaling). An anchored indicator is calendar at
    every option (historyClass). `params` the registry's parameters, `defaults` the start configuration, `start`
    historyAt({}). */
export function historyByOption(params, defaults, hasAnchor, start, historyAt, scale) {
  const outs = Object.keys(start), choosers = params.filter(p => p.type === 'enum' || p.type === 'boolean');
  const optionsOf = p => p.type === 'boolean' ? [false, true] : p.options;
  // the same lookback: the class, and the window's bars (two outputs without a window read the whole history alike)
  const same = (a, b) => a.history_class === b.history_class && (a.effective_window?.bars ?? null) === (b.effective_window?.bars ?? null);
  const byOption = {};
  for (const p of choosers) for (const v of optionsOf(p)) {
    if (v === defaults[p.key]) continue;
    const h = historyAt({ [p.key]: v });
    for (const o of outs) if (h[o] && !same(h[o], start[o])) ((byOption[o] ??= {})[p.key] ??= {})[String(v)] = h[o];
  }
  const combined = {};
  if (!hasAnchor && choosers.length > 1) {
    const worstSeen = {}, under = new Set();
    let combos = [[]];
    for (const p of choosers) combos = combos.flatMap(c => optionsOf(p).map(v => [...c, [p.key, v]]));
    for (const combo of combos) {
      const differing = combo.filter(([k, v]) => v !== defaults[k]);
      if (differing.length < 2) continue;
      const h = historyAt(Object.fromEntries(differing), false);
      for (const o of outs) {
        if (!h[o]) continue;
        const predicted = worstClass(differing.map(([k, v]) => byOption[o]?.[k]?.[String(v)]?.history_class ?? start[o].history_class));
        worstSeen[o] = worstClass([worstSeen[o] ?? 'window', h[o].history_class]);
        if (HISTORY_ORDER.indexOf(h[o].history_class) > HISTORY_ORDER.indexOf(predicted)) under.add(o);
      }
    }
    for (const o of under) combined[o] = worstSeen[o];
  }
  const W0 = Object.fromEntries(outs.filter(o => start[o].effective_window?.bars).map(o => [o, start[o].effective_window.bars]));
  return { byOption, combined, scaling: Object.keys(W0).length ? scale(W0) : {} };
}

/** Scaling and shift probes: OHLC x k, volume x m, OHLC + s, volume + sv. A price level scales with k and moves with s
    (comparable with close); a price change scales with k and ignores s; a volume level scales with m and moves with sv
    (comparable with volume); a volume quantity (OBV, A/D) scales with m only; a product of both is price_x_volume;
    an output neither moves is dimensionless; anything else is 'other' (EOM, Market FI). */
export function unitProbe(run, B) {
  const k = PROBE.scale_price, m = PROBE.scale_volume, s = PROBE.shift_price_of_median * median(B.C), sv = PROBE.shift_volume_of_median * median(B.V);
  const base = run(B), byK = run(mapBars(B, { p: x => x * k, v: x => x })), byM = run(mapBars(B, { p: x => x, v: x => x * m }));
  const byS = run(mapBars(B, { p: x => x + s, v: x => x })), bySv = run(mapBars(B, { p: x => x, v: x => x + sv }));
  const out = {};
  for (const o of Object.keys(base)) {
    if (o.startsWith('_')) continue;
    const pk = related(base[o], byK[o], x => x * k), p0 = related(base[o], byK[o], x => x);
    const vm = related(base[o], byM[o], x => x * m), v0 = related(base[o], byM[o], x => x);
    const shiftP = related(base[o], byS[o], x => x + s), shiftV = related(base[o], bySv[o], x => x + sv);
    let unit = 'other', comparable = null;
    if (pk && v0) { unit = shiftP ? 'price' : 'price_change'; if (shiftP) comparable = 'close' }
    else if (p0 && vm) { unit = 'volume'; if (shiftV) comparable = 'volume' }
    else if (p0 && v0) unit = 'dimensionless';
    else if (pk && vm) unit = 'price_x_volume';
    out[o] = { unit, comparable_with: comparable };
  }
  return out;
}

/** Lag probe: a comparison `field > output` (or `<`) that is never true on a bar where both are finite reads the
    output's previous bar (lag 1): a channel built from today's high can never be exceeded by today's close (Donchian
    upper, report 6.8: 0 same-bar hits against 29,041-54,652 with the prior bar). Otherwise lag 0. */
export function compareLag(field, output) {
  let both = 0, gt = 0, lt = 0;
  for (let i = 0; i < output.length; i++) {
    if (!isN(field[i]) || !isN(output[i])) continue;
    both++; if (field[i] > output[i]) gt++; if (field[i] < output[i]) lt++;
  }
  if (both < PROBE.min_common_bars) throw new Error(`lag probe: only ${both} comparable bars`);
  return { gt: gt ? 0 : 1, lt: lt ? 0 : 1 };
}

/** Poison probe: the bar fields (O H L C V) whose loss (all NaN) empties the output are its inputs. An output with
    values always has at least one (it is computed from the bars), so an empty list means exactly "no value at this
    configuration" (I43 upper1 / lower1 at bands_mode None), which registry.ts inputsOf and validate.ts rely on; an
    output that keeps values whichever field is lost stops the build instead of being listed as needing nothing. */
export function inputsProbe(run, B, outputs) {
  const base = run(B), out = Object.fromEntries(outputs.map(o => [o, []]));
  for (const f of ['O', 'H', 'L', 'C', 'V']) {
    const poisoned = run({ ...B, [f]: B[f].map(() => NaN) });
    for (const o of outputs) if (finite(base[o]).length && !finite(poisoned[o]).length) out[o].push(f);
  }
  for (const o of outputs) if (finite(base[o]).length && !out[o].length) throw new Error(`poison probe: ${o} keeps values whichever bar field is lost, so its inputs cannot be derived`);
  return out;
}

/** Degeneracy probe (report 6.8 rule a): at the parameter's minimum, an output that is all null (non-finite values
    are null in F), constant, or two band outputs that are equal on every bar make the minimum exclusive. */
export function degenerate(out, outputs, bandOutputs) {
  for (const o of outputs) {
    const v = finite(out[o]);
    if (!v.length) return `${o} has no value`;
    const lo = Math.min(...v), hi = Math.max(...v);
    if (hi - lo <= PROBE.tolerance * Math.max(1, Math.abs(hi), Math.abs(lo))) return `${o} is constant (${lo})`;
  }
  for (let a = 0; a < bandOutputs.length; a++) for (let b = a + 1; b < bandOutputs.length; b++) {
    const x = out[bandOutputs[a]], y = out[bandOutputs[b]];
    let n = 0, eq = true;
    for (let i = 0; i < x.length && eq; i++) if (isN(x[i]) && isN(y[i])) { n++; eq = Math.abs(x[i] - y[i]) <= PROBE.tolerance * Math.max(1, Math.abs(x[i])) }
    if (n && eq) return `${bandOutputs[a]} equals ${bandOutputs[b]} on every bar`;
  }
  return null;
}

/** Floor probe (report 6.8 rule b): a numeric parameter for which F gives the same outputs at x + 0.5 as at x is
    integer-only, whatever its registry type (indicators.ts def() floors every LENGTH_KEYS key). */
export function floored(run, B, p, value) {
  const a = run(B, { [p]: value }), b = run(B, { [p]: value + 0.5 });
  return Object.keys(a).filter(o => !o.startsWith('_')).every(o => sameSeries(a[o], b[o]));
}

/* ---- cost_class: how the work of F grows with an integer parameter (report 6.8), counted, never timed ---------- */
/* The class decides a parameter's cap (registry.ts capOf), so it is part of the contract and of its version. It was
   once a wall-clock ratio (process.hrtime): under CPU contention an O(N) parameter's ratio crossed the threshold
   (6 to 16 of the 58 O(N) parameters came out O(N·n) in each of 5 runs with 12 busy loops on 4 cores, 2026-10-29), so
   --check failed and the version depended on the machine's load. The measure is now the work F does: V8's precise
   block coverage (the inspector Profiler with call counts per block) counts how many times every block of the measured
   code ran. The count is exact only below V8's optimizing compiler: TurboFan counts some blocks differently from the
   bytecode (121 of the 268 measurements, e.g. I05 KAMA by 306,000 characters at length 1000), and when it takes over
   depends on background compile threads, so under load 1 of 3 and 2 of 8 runs gave other numbers (the classes held).
   The probe's child therefore runs with --max-opt=1: the interpreter and the Sparkplug baseline compiler, which emits
   the same builtin call for every bytecode, count each block as the bytecode does (8 of 8 runs identical under 12 busy
   loops on 4 cores, the same numbers as the interpreter alone). */

/** The two lengths of the cost probe: the default L1 and L2 = max(cost_long_length, 50 x L1), at most a quarter of the
    bars (with the 53 defaults, at most 55: L2 / L1 is at least 45). */
export function costLengths(value, bars) {
  const L1 = Math.max(1, value);
  return [L1, Math.min(Math.max(PROBE.cost_long_length, 50 * L1), Math.floor(bars / 4))];
}

/** The most an O(N·n) parameter can grow between the two lengths on `bars` bars: the growth of a kernel that is all
    window loop (bars - L + 1 windows of L values each). The quarter-of-the-bars limit brings L2 close to a large
    default L1 (a default of 1500 on 10000 bars: L2 = 2500, at most 0.47), where even such a kernel stays below the
    O(N) bound and would be written O(N), without its cap; costClass refuses those lengths instead (review 2026-10-29). */
export function windowGrowth([L1, L2], bars) {
  return (L2 * (bars - L2 + 1)) / (L1 * (bars - L1 + 1)) - 1;
}

/** The class of a measured growth W(L2) / W(L1) - 1, or null when neither is decisive. A kernel that loops over its
    window (O(N·n)) grows 13.4 to 32.4 (HMA, Aroon, Donchian, Stochastic RSI, Stochastic, Williams %R, CCI, standard
    deviation 'sample', historical volatility: 34 configurations); a running-sum or recursive kernel (O(N)) grows -0.09
    to 0 (the other 58 integer parameters: 259 configurations; every offered enum option, 2026-10-29). O(N·n) needs a
    growth of at least cost_growth x cost_margin (4: the work at least five times larger at the longer length), O(N) at
    most cost_growth / cost_margin (1: at most twice). A class is written only that far from the boundary, so a small
    change in how a V8 version splits blocks does not flip it; a growth in between stops the build instead of guessing. */
export function costVerdict(growth) {
  if (!Number.isFinite(growth)) return null;
  if (growth >= PROBE.cost_growth * PROBE.cost_margin) return 'O(N·n)';
  if (growth <= PROBE.cost_growth / PROBE.cost_margin) return 'O(N)';
  return null;
}

/** The work of one measured window, in executed source characters: per function, each character of its source counted
    once per run of the innermost block that holds it (V8 reports a block only where its count differs from the block
    around it, and this sum does not depend on that). Skips node internals and the harness scripts (the code that
    calls the meter, compiled before it started). A measured function that ran without block counts was compiled
    before the meter started (V8 adds block counters at compile time), so its loops would count as one: that stops the
    probe instead of under-counting. Not counted: work inside a built-in that does not call back into JavaScript
    (Array.prototype.slice, fill, a spread). A window taken that way, Math.max(...x.slice(i - n + 1, i + 1)), measures
    O(N) (growth -0.05 from 14 to 1000; Donchian and Williams %R rewritten so would lose their caps, review 2026-10-29),
    while one that calls back (slice(...).reduce(callback)) is counted O(N·n). Every window of the 53 kernels of
    indicators.ts is a JavaScript loop (read 2026-10-29); a kernel that moves its window into a built-in needs its
    class read from its code. */
export function executedChars(scripts, harness = []) {
  let work = 0;
  for (const s of scripts) {
    if (s.url.startsWith('node:') || harness.includes(s.url)) continue;
    for (const f of s.functions) {
      const name = `${f.functionName || '(anonymous)'} in ${s.url || '(no url)'}`;
      if (!f.isBlockCoverage) {
        if (f.ranges.some(r => r.count > 0)) throw new Error(`cost probe: ${name} ran without block counts (compiled before the work meter started), so its loops would not be counted`);
        continue;
      }
      const ranges = [...f.ranges].sort((a, b) => a.startOffset - b.startOffset || b.endOffset - a.endOffset), open = [];
      for (const r of ranges) {
        while (open.length && open[open.length - 1].endOffset <= r.startOffset) open.pop();
        const parent = open[open.length - 1];
        if (parent && r.endOffset > parent.endOffset) throw new Error(`cost probe: the coverage blocks of ${name} overlap without nesting`);
        work += (r.endOffset - r.startOffset) * (r.count - (parent ? parent.count : 0));
        open.push(r);
      }
    }
  }
  return work;
}

/** A work meter: starts V8's precise block coverage in this process; work(fn) runs fn and returns its executedChars.
    Only code compiled after the meter started is measured, so the measured module is imported after this. */
export async function workMeter(harness = [import.meta.url]) {
  const { Session } = await import('node:inspector/promises');
  const session = new Session();
  session.connect();
  await session.post('Profiler.enable');
  await session.post('Profiler.startPreciseCoverage', { callCount: true, detailed: true });
  const take = async () => (await session.post('Profiler.takePreciseCoverage')).result;   // also resets the counts
  return {
    async work(fn) {
      await take();
      fn();
      const w = executedChars(await take(), harness);
      if (!(w > 0)) throw new Error('cost probe: the measured run executed no counted code');
      return w;
    },
    async close() { await session.post('Profiler.stopPreciseCoverage'); await session.post('Profiler.disable'); session.disconnect() },
  };
}

/** cost_class of an integer parameter p of `run` at its default `value` (report 6.8): the work at the two costLengths
    on the bars B, classed by costVerdict (null when not decisive). Null without measuring (work null) when the lengths
    cannot tell the classes apart: windowGrowth below the O(N·n) bound. */
export async function costClass(meter, run, B, p, value) {
  const lengths = costLengths(value, B.C.length), ceiling = windowGrowth(lengths, B.C.length);
  if (!(ceiling >= PROBE.cost_growth * PROBE.cost_margin)) return { cost_class: null, lengths, ceiling, work: null, growth: null };
  const work = [];
  for (const L of lengths) work.push(await meter.work(() => run(B, { [p]: L })));
  const growth = work[1] / work[0] - 1;
  return { cost_class: costVerdict(growth), lengths, ceiling, work, growth };
}

/** Why a measurement of costClass gives no class, with its numbers and the probe setting that resolves it: the second
    length comes from cost_long_length (or 50 x the default) until it reaches a quarter of cost_bars. */
export function costRefusal(at, c, bars) {
  const [L1, L2] = c.lengths, hi = PROBE.cost_growth * PROBE.cost_margin, lo = PROBE.cost_growth / PROBE.cost_margin;
  const longer = L2 >= Math.floor(bars / 4) ? `raise PROBE.cost_bars (the second length is at most a quarter of the ${bars} bars)` : 'raise PROBE.cost_long_length';
  if (c.work === null) return `${at}: at lengths ${L1} and ${L2} on ${bars} bars even a kernel that is all window loop grows only ${c.ceiling.toFixed(3)}, `
    + `less than ${hi} (O(N·n)), so the probe cannot tell O(N·n) from O(N) at this default: ${longer} before building`;
  return `${at}: the work grows ${c.growth.toFixed(3)} from length ${L1} to ${L2} (${c.work.join(' -> ')} executed source characters), neither at most `
    + `${lo} (O(N)) nor at least ${hi} (O(N·n)), so no class can be derived with the required margin: read the kernel's loops, or ${longer} `
    + 'before building';
}

/** The V8 tier limit of the cost probe's child (PROBE.cost_tier; see the cost_class notes above): no optimizing
    compiler. */
export const COST_TIER_FLAG = PROBE.cost_tier;
/** The node arguments of the cost probe's child process: the tier limit, the Terminal's TypeScript loader (as the npm
    scripts), this script and --cost-work. */
export const costChildArgs = () => [COST_TIER_FLAG, '--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', pathToFileURL(at(PATHS.loader)).href,
  fileURLToPath(import.meta.url), '--cost-work'];

/** The cost probe's child process (`--cost-work`, the job as JSON on stdin, only under COST_TIER_FLAG): starts the
    meter, then imports `module` (its F, as indicators.ts exports it) so that every function of it has block counters,
    and measures each group on the fixture of `bars` bars: { id, key, param, value, base (the start configuration),
    variants (enum overrides, the default first) }. A group is O(N·n) at its first variant that is (a basis or method
    can swap a running-sum kernel for a window loop: I32 'sample'), else O(N). A measurement without a class
    (costRefusal) stops the probe with the numbers. */
export async function costWork({ module, bars, groups }) {
  if (!process.execArgv.includes(COST_TIER_FLAG)) throw new Error(`cost probe: the child must run with ${COST_TIER_FLAG} (an optimizing tier changes block counts); start it with costChildArgs()`);
  const meter = await workMeter();
  const { F } = await import(pathToFileURL(module).href);
  const B = fixture({ bars }), out = [];
  for (const g of groups) {
    const fn = F[g.key];
    if (typeof fn !== 'function') throw new Error(`cost probe: ${module} has no function ${g.key}`);
    const measured = [];
    let cls = 'O(N)';
    for (const v of g.variants) {
      const c = await costClass(meter, (b, over) => fn(b, { ...g.base, ...v, ...over }), B, g.param, g.value);
      measured.push({ variant: v, ...c });
      if (!c.cost_class) throw new Error(costRefusal(`cost probe ${g.id}.${g.param} ${JSON.stringify(v)}`, c, bars));
      if (c.cost_class === 'O(N·n)') { cls = 'O(N·n)'; break }
    }
    out.push({ id: g.id, param: g.param, cost_class: cls, measured });
  }
  await meter.close();
  return out;
}

/** Runs costWork in a child process of this script (the meter must start before the measured module is compiled, and
    the rest of the build runs at full speed without coverage or the tier limit) and returns its answer. */
export function measureCost(job) {
  const r = spawnSync(process.execPath, costChildArgs(), { input: JSON.stringify(job), encoding: 'utf8', maxBuffer: 64 << 20 });
  if (r.error) throw new Error(`cost probe: ${r.error.message}`);
  if (r.status !== 0) throw new Error(`cost probe failed (exit ${r.status}): ${r.stderr.trim()}`);
  const out = JSON.parse(r.stdout);
  if (out.length !== job.groups.length || out.some((x, i) => x.id !== job.groups[i].id || x.param !== job.groups[i].param)) throw new Error('cost probe: the answer does not match the job');
  return out;
}

/* ---- a lowered cost_class needs a reviewed reason (ERRORS M300; AGENTS.md "Gates and evidence") ------------------ */
/* The probe counts the work JavaScript does, so work inside a built-in that does not call back is invisible to it
   (executedChars): a kernel whose window loop moves into such a built-in regenerates O(N) and loses its cap while its
   work still grows with the length. The build therefore never lowers a class silently. Rule: against the committed
   registry (committedRegistry), a parameter that was O(N·n) and is derived O(N) stops the build unless
   screener-overlay.json `cost_reviews` holds a reviewed reason for it; the reason is copied into the parameter
   (`cost_review`), so the registry shows which classes rest on a review. A raise to O(N·n) needs nothing: it only adds
   a cap. A review of a parameter the probe finds O(N·n) again is not copied (the cap is back). */
export const COST_REVIEW_FIELDS = ['indicator', 'param', 'from', 'to', 'reason', 'reviewed'];
const LOWER = { from: 'O(N·n)', to: 'O(N)' };
/** The review of a lowered id.param in the overlay's cost_reviews, or undefined (only a complete one counts). */
export const costReviewOf = (overlay, id, param) => (overlay?.cost_reviews || []).find(v => v && v.indicator === id && v.param === param
  && v.from === LOWER.from && v.to === LOWER.to && typeof v.reason === 'string' && v.reason.trim() && typeof v.reviewed === 'string' && v.reviewed.trim());
/** Every way the overlay's cost_reviews break their rule (costLowerings); empty when sound. */
export function costReviewProblems(reviews, base) {
  if (reviews === undefined) return [];
  if (!Array.isArray(reviews)) return ['cost_reviews must be a list of {indicator, param, from, to, reason, reviewed}'];
  const out = [], seen = new Set();
  for (const v of reviews) {
    const where = `cost_reviews ${v?.indicator}.${v?.param}`, p = base.indicators.find(x => x.id === v?.indicator)?.params.find(x => x.key === v?.param);
    if (!p || p.type !== 'integer') out.push(`${where}: no such integer parameter (a cost_class is derived for integer parameters only)`);
    if (v?.from !== LOWER.from || v?.to !== LOWER.to) out.push(`${where}: from must be "${LOWER.from}" and to "${LOWER.to}" (only a lowered class needs a review)`);
    if (typeof v?.reason !== 'string' || !v.reason.trim()) out.push(`${where}: reason is required (what in the kernel's code makes its work stop growing with the length)`);
    if (typeof v?.reviewed !== 'string' || !v.reviewed.trim()) out.push(`${where}: reviewed is required (who approved it, when, and where it is recorded)`);
    for (const k of Object.keys(v || {})) if (!COST_REVIEW_FIELDS.includes(k)) out.push(`${where}: ${k} is not a field (${COST_REVIEW_FIELDS.join(', ')})`);
    if (seen.has(`${v?.indicator}.${v?.param}`)) out.push(`${where}: repeated`);
    seen.add(`${v?.indicator}.${v?.param}`);
  }
  return out;
}
/** The registry the derived cost classes are compared with: `against` (a file) when given; else the one committed at
    git HEAD; else (no git, or the file not committed yet) the file on disk; null at the first build. */
export function committedRegistry(against = null) {
  if (against) return { from: against, doc: JSON.parse(fs.readFileSync(path.resolve(against), 'utf8')) };
  const g = spawnSync('git', ['-C', ROOT, 'show', `HEAD:${PATHS.out}`], { encoding: 'utf8', maxBuffer: 64 << 20 });
  if (!g.error && g.status === 0 && g.stdout.trim()) return { from: `git HEAD:${PATHS.out}`, doc: JSON.parse(g.stdout) };
  return fs.existsSync(at(PATHS.out)) ? { from: PATHS.out, doc: readJson(PATHS.out) } : null;
}
/** The parameters whose class the regeneration lowers without a review: O(N·n) in `committed` (a registry document),
    O(N) in `derived` (`id.param` -> class, measureCost's answer), and no costReviewOf in the overlay. */
export function costLowerings(committed, derived, overlay) {
  const out = [];
  for (const r of committed?.indicators || []) for (const p of r.params || []) {
    const now = derived.get(`${r.id}.${p.key}`);
    if (p.cost_class === LOWER.from && now === LOWER.to && !costReviewOf(overlay, r.id, p.key)) out.push({ id: r.id, param: p.key, name: r.name ?? r.id });
  }
  return out;
}
/** The refusal of costLowerings: where (the parameters and the registry compared with), the rule, how to pass, and one
    right and one wrong cost_reviews entry for the first of them. */
export function costLoweringRefusal(lowered, from) {
  const first = lowered[0], list = lowered.map(x => `${x.id}.${x.param} (${x.name})`).join(', ');
  // the right one shows the shape and the kind of words (the code that makes it O(N); who approved it and where)
  const right = { indicator: first.id, param: first.param, ...LOWER,
    reason: 'the window maximum is kept in a monotonic deque: each bar enters and leaves it once, so the work per bar does not grow with the length',
    reviewed: '2026-11-02, approved by the user, recorded in EXEC.md EXEC-SCREENER' };
  const wrong = { indicator: first.id, param: first.param, reason: 'the probe now says O(N)' };
  return `cost_class lowered: the regeneration derives O(N) for ${list}, which ${from} has as O(N·n); writing it would drop the cap of each `
    + '(registry.ts capOf).\n'
    + 'Rule: the cost probe counts JavaScript work only, so a window loop moved into a built-in that does not call back (slice, a spread into '
    + 'Math.max) measures O(N) while its work still grows with the length; a lowered class is written only with a reviewed reason in '
    + `${PATHS.overlay} cost_reviews (a raise to O(N·n) needs none).\n`
    + `How to pass: read the kernel of each parameter above in ${PATHS.calc}. If its work per bar no longer grows with the length, add one `
    + `cost_reviews entry per parameter {${COST_REVIEW_FIELDS.join(', ')}} with the reason and who reviewed it, then run npm run registry; if it `
    + 'still loops over the window inside a built-in, write that loop in JavaScript again so the probe counts it.\n'
    + `Right: ${JSON.stringify(right)}\n`
    + `Wrong: ${JSON.stringify(wrong)} (it restates the probe, whose answer is what is under review, and has no from, to or reviewed)`;
}

/* ---- overlay checks ------------------------------------------------------------------------------------------- */
/** Every way the overlay breaks its rules (one entry per base id and vice versa, known shapes, forms, operators, labels,
    defaults, overrides with evidence, the cost model); empty when sound. */
export function overlayProblems(overlay, base) {
  const out = [], ids = base.indicators.map(r => r.id), oi = overlay.indicators || {};
  for (const id of ids) if (!oi[id]) out.push(`overlay: ${id} has no entry (one entry per base id)`);
  for (const id of Object.keys(oi)) if (!ids.includes(id)) out.push(`overlay: ${id} is not a base indicator`);
  for (const r of base.indicators) {
    const e = oi[r.id]; if (!e) continue;
    if (!SHAPES.includes(e.shape)) out.push(`overlay ${r.id}: shape ${e.shape} is not one of ${SHAPES}`);
    if (!Array.isArray(e.synonyms) || e.synonyms.some(s => typeof s !== 'string' || !s)) out.push(`overlay ${r.id}: synonyms must be a list of words`);
    // the catalog's one-line description (page tooltip and search text; our own plain English): one line of 20-160 characters
    if (typeof e.description !== 'string' || e.description.length < 20 || e.description.length > 160 || /[\r\n]/.test(e.description) || e.description !== e.description.trim())
      out.push(`overlay ${r.id}: description must be one line of 20-160 characters`);
    const keys = Object.keys(e.outputs || {});
    for (const o of r.outputs) if (!keys.includes(o)) out.push(`overlay ${r.id}: output ${o} has no entry`);
    for (const o of keys) if (!r.outputs.includes(o)) out.push(`overlay ${r.id}: ${o} is not an output of ${r.key}`);
    for (const [o, spec] of Object.entries(e.outputs || {})) {
      for (const t of spec.tests || []) {
        const f = TEST_FORMS[t.form], where = `overlay ${r.id}.${o} ${t.form}`;
        if (!f) { out.push(`${where}: not a test form (${Object.keys(TEST_FORMS)})`); continue }
        if (!Array.isArray(t.ops) || !t.ops.length || t.ops.some(op => !f.ops.includes(op))) out.push(`${where}: ops must be a non-empty subset of ${f.ops}`);
        if (f.with && (!r.outputs.includes(t.with_output) || t.with_output === o)) out.push(`${where}: with_output must be another output of ${r.key}`);
        if (!f.with && t.with_output !== undefined) out.push(`${where}: with_output is not used by this form`);
        for (const l of Object.keys(t.labels || {})) if (!(t.ops || []).includes(l)) out.push(`${where}: label for ${l}, which is not one of its ops`);
        for (const [k, v] of Object.entries(t.defaults || {})) {
          if (!(f.defaults || []).includes(k)) out.push(`${where}: default ${k} is not used by this form`);
          else if (k === 'ma' && !MA_TYPES.includes(v)) out.push(`${where}: ma must be one of ${MA_TYPES}`);
          else if ((k === 'bars' || k === 'length') && !(Number.isInteger(v) && v >= 1)) out.push(`${where}: ${k} must be a whole number of at least 1`);
          else if (k === 'value' && !isN(v)) out.push(`${where}: value must be a number`);
          else if ((k === 'categories' || k === 'changes') && typeof v !== 'string') out.push(`${where}: ${k} must be a comma list`);
        }
      }
      for (const d of spec.disabled_tests || []) if (!TEST_FORMS[d.form] || typeof d.reason !== 'string' || !d.reason) out.push(`overlay ${r.id}.${o}: a disabled test needs a known form and a reason`);
    }
    if (e.probe !== undefined && !(e.probe && typeof e.probe.params === 'object' && typeof e.probe.evidence === 'string' && e.probe.evidence))
      out.push(`overlay ${r.id}: probe needs params and evidence`);
    // offered options of an enum parameter (a user decision, e.g. P17 a): a non-empty subset of the base options with
    // the decision as evidence; `start` names the value a card opens with exactly when the registry default is not
    // offered (report 13 P17 consequence), and nowhere else (narrow-only: the base default itself never changes)
    for (const [k, spec] of Object.entries(e.params || {})) {
      const p = r.params.find(x => x.key === k), where = `overlay ${r.id}.params.${k}`;
      if (!p || p.type !== 'enum') { out.push(`${where}: only an enum parameter of ${r.key} can have its options narrowed`); continue }
      const opts = spec?.options;
      if (!Array.isArray(opts) || !opts.length || opts.some(o => !p.options.includes(o)) || new Set(opts).size !== opts.length)
        out.push(`${where}: options must be a non-empty subset of the base options ${p.options}, without repeats`);
      else if (opts.includes(p.default) ? spec.start !== undefined : !opts.includes(spec.start))
        out.push(`${where}: start is required, and one of the options, exactly when the registry default ${p.default} is not offered`);
      if (typeof spec?.decision !== 'string' || !spec.decision) out.push(`${where}: decision (the user's decision and where it is recorded) is required`);
      for (const x of Object.keys(spec || {})) if (!['options', 'start', 'decision'].includes(x)) out.push(`${where}: ${x} is not a field (options, start, decision)`);
    }
    const dt = e.default_test;
    if (dt !== null) {
      const t = dt && (e.outputs?.[dt.output]?.tests || []).find(x => x.form === dt.form);
      if (!t || !t.ops.includes(dt.op)) out.push(`overlay ${r.id}: default_test must be one of the output's test forms and operators`);
      if (dt && !(Number.isInteger(dt.within) && dt.within >= 1)) out.push(`overlay ${r.id}: default_test.within must be a whole number of at least 1`);
    }
  }
  for (const ov of overlay.overrides || []) {
    const r = base.indicators.find(x => x.id === ov.indicator), p = r?.params.find(x => x.key === ov.param);
    if (!p) out.push(`override ${ov.indicator}.${ov.param}: no such parameter`);
    else if (ov.rule !== 'exclusive_min' || p.min === undefined) out.push(`override ${ov.indicator}.${ov.param}: only rule exclusive_min on a parameter with a min is known`);
    if (typeof ov.evidence !== 'string' || !ov.evidence) out.push(`override ${ov.indicator}.${ov.param}: evidence is required`);
  }
  const cm = overlay.cost_model || {};
  for (const k of ['ns_per_bar_length', 'reference_bars']) if (!(isN(cm[k]) && cm[k] > 0)) out.push(`cost_model.${k} must be a positive number`);
  if (typeof cm.evidence !== 'string' || !cm.evidence) out.push('cost_model.evidence is required');
  // QA unit B, QA4: the flow kernels' prior per broker row, measured (its evidence names the benchmark note)
  const fl = cm.flow || {};
  for (const k of ['context_ns_per_row', 'presence_ns_per_row']) if (!(isN(fl[k]) && fl[k] > 0)) out.push(`cost_model.flow.${k} must be a positive number`);
  // one measured prior per way an entry is computed (FLOW_COMPUTES; none is never computed), no other key
  const computed = FLOW_COMPUTES.filter(c => c !== 'none'), per = fl.ns_per_unit && typeof fl.ns_per_unit === 'object' ? fl.ns_per_unit : {};
  for (const c of computed) if (!(isN(per[c]) && per[c] > 0)) out.push(`cost_model.flow.ns_per_unit.${c} must be a positive number`);
  for (const c of Object.keys(per)) if (!computed.includes(c)) out.push(`cost_model.flow.ns_per_unit.${c} is not a way a flow entry is computed (${computed.join(', ')})`);
  if (typeof fl.evidence !== 'string' || !fl.evidence) out.push('cost_model.flow.evidence is required');
  // QA unit C: a pattern's prior per bar, and a candlestick pattern's per bar and session of the window candles.ts reads,
  // measured (its evidence names the benchmark note)
  const pa = cm.pattern || {};
  for (const k of ['ns_per_bar', 'candle_ns_per_bar_session']) if (!(isN(pa[k]) && pa[k] > 0)) out.push(`cost_model.pattern.${k} must be a positive number`);
  if (typeof pa.evidence !== 'string' || !pa.evidence) out.push('cost_model.pattern.evidence is required');
  out.push(...costReviewProblems(overlay.cost_reviews, base));
  return out;
}

/* ---- the flow indicators (EXEC-SCREENER-FLOW-CANDLES P5a; verification/screener/P5_FLOW.md section 2) ---------- */
/** The kinds of OPERATORS.md section 4 an output of flow-kinds.json may name. */
export const FLOW_KINDS = ['K', 'P', 'Rp', 'L', 'H', 'D', 'F', 'B'];
/** Registry parameter kinds that only draw (the Terminal's reference lines, its buttons and fixed texts): a condition
    never takes them (P5_FLOW.md section 1). */
export const FLOW_DISPLAY_KINDS = ['levels', 'button', 'fixed'];
/** How the core computes an entry (P5b, P5_FLOW.md section 3; flowscreener.ts): the Terminal's computeFlow as it is
    (terminal), the anchor N sessions back (anchored, FL18-FL20, FL44, FL45), the Screener's Broker Inventory (inventory,
    FL23), the foreign net in rupiah (foreign_net, fnet), or never (none: the data is not published, ksei_net). */
export const FLOW_COMPUTES = ['terminal', 'anchored', 'inventory', 'foreign_net', 'none'];
/** The parameter kinds a screener parameter may have (the condition kinds of the registry). */
const SCREENER_PARAM_KINDS = ['int', 'num', 'select', 'multi', 'bool', 'brokers'];
/** What is wrong with one output's kind row of flow-kinds.json (empty when sound): a kind letter, {kind, unit}, or
    {by: <select parameter>, <each of its options>: one of these three} (P5b: a kind by a parameter may itself follow
    another parameter, FL23's value by series, then by unit). `params` are the entry's parameters. */
function flowKindProblems(where, spec, id, params) {
  if (typeof spec === 'string') return FLOW_KINDS.includes(spec) ? [] : [`${where}: kind ${spec} is not one of ${FLOW_KINDS.join(', ')}`];
  if (!spec || typeof spec !== 'object') return [`${where}: not a kind`];
  if (!('by' in spec)) return FLOW_KINDS.includes(spec.kind) && typeof spec.unit === 'string' && spec.unit ? [] : [`${where}: {kind, unit} needs a kind of ${FLOW_KINDS.join(', ')} and a unit`];
  const p = params.find(q => q.key === spec.by);
  if (!p || p.kind !== 'select') return [`${where}: by ${spec.by} is not a select parameter of ${id}`];
  const options = p.options.map(o => Array.isArray(o) ? o[0] : o);
  const out = options.filter(o => !(o in spec)).map(o => `${where}: no kind for ${spec.by} = ${o}`);
  for (const [k, s] of Object.entries(spec)) if (k !== 'by') out.push(...(options.includes(k) ? flowKindProblems(`${where}.${k}`, s, id, params) : [`${where}: ${k} is not an option of ${spec.by}`]));
  return out;
}
/** A screener parameter of flow-kinds.json as an entry parameter (P5b): its key, label, kind, options, default, range
    and words, condition true and `screener` true (not the Terminal's); a maximum "window" is the broker window, "window-1"
    one less (K1, derived from window_sessions), never a number typed per parameter. */
function screenerParam(spec, W, where, problems) {
  const max = spec.max === 'window' ? W : spec.max === 'window-1' ? W - 1 : spec.max;
  const p = { key: spec.key, label: spec.label, kind: spec.kind };
  if (spec.options) p.options = structuredClone(spec.options);
  p.default = structuredClone(spec.default);
  if (spec.min !== undefined) p.min = spec.min;
  if (max !== undefined) p.max = max;
  if (spec.text) p.text = spec.text;
  p.condition = true; p.screener = true;
  const w = `${where}.${spec.key}`;
  if (!spec.key || !spec.label || !SCREENER_PARAM_KINDS.includes(spec.kind)) problems.push(`${w}: a screener parameter needs a key, a label and a kind of ${SCREENER_PARAM_KINDS.join(', ')}`);
  if (spec.max !== undefined && typeof max !== 'number') problems.push(`${w}: max must be a number, "window" or "window-1"`);
  if ((spec.kind === 'int' || spec.kind === 'num') && (typeof p.default !== 'number' || (p.min !== undefined && p.default < p.min) || (max !== undefined && p.default > max) || (spec.kind === 'int' && !Number.isInteger(p.default))))
    problems.push(`${w}: default ${JSON.stringify(p.default)} is outside its own range`);
  const values = (p.options || []).map(o => Array.isArray(o) ? o[0] : o);
  if (spec.kind === 'select' && !values.includes(p.default)) problems.push(`${w}: default ${JSON.stringify(p.default)} is not one of its options`);
  if (spec.kind === 'multi' && !(Array.isArray(p.default) && p.default.length && p.default.every(v => values.includes(v)))) problems.push(`${w}: default must be a list of its options`);
  if (spec.kind === 'brokers' && !Array.isArray(p.default)) problems.push(`${w}: a broker list's default is a list`);
  return p;
}
/** The values a select or switch parameter of the registry takes (its options; false and true). */
const choicesOf = p => p.kind === 'bool' ? [false, true] : (p.options || []).map(o => Array.isArray(o) ? o[0] : o);
const hasValue = out => Object.values(out).some(s => Array.isArray(s) && s.some(v => typeof v === 'number' && Number.isFinite(v)));
/** The registry's select and switch parameters of indicator r that change no value computeFlow gives (QA unit B, QA5:
    the Terminal's display options, such as "Plot" histogram or line). Derived, never listed: on the depth probe's
    synthetic context (src/core/flowprobe.ts probeContext, as long as any of the contexts' sessions reach), every option
    of such a parameter gives the same outputs, at the registry defaults and with each other parameter of options set
    to each of its other values in turn: a select or switch to each option, a list (boards, investor types) to each
    single option and to all of them (so a choice that matters only beside another, a Top-N ranking under scope topn, a
    denominator of the chosen investor types against the board's, keeps its place); a parameter whose outputs have no
    value on any probed context is kept (the probe cannot tell). computeFlow fills a parameter left out with its default
    (flow.ts flowDefaults), so leaving it out changes no value either. */
export function displayOnlyParams(r) {
  const defaults = Object.fromEntries(r.params.filter(p => p.default !== undefined).map(p => [p.key, p.default]));
  const choosers = r.params.filter(p => (p.kind === 'select' || p.kind === 'bool') && choicesOf(p).length > 1);
  const lists = r.params.filter(p => p.kind === 'multi' && choicesOf(p).length > 1).map(q => [q.key, [...choicesOf(q).map(o => [o]), choicesOf(q)]]);
  const others = [...choosers.map(q => [q.key, choicesOf(q)]), ...lists];
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const contexts = [defaults, ...others.flatMap(([k, values]) => values.filter(v => !same(v, defaults[k])).map(v => ({ ...defaults, [k]: v })))];
  const L = Math.max(...contexts.flatMap(c => choosers.map(p => Math.max(...choicesOf(p).map(v => probeLength(r.params, { ...c, [p.key]: v }))))), probeLength(r.params, defaults));
  const ctx = probeContext(L), memo = new Map();
  const outputs = values => {
    const k = JSON.stringify(values);
    if (!memo.has(k)) { const out = computeFlow(r.id, ctx, values); memo.set(k, { text: JSON.stringify(out), value: hasValue(out) }) }
    return memo.get(k);
  };
  return choosers.filter(p => {
    let valued = false;
    for (const c of contexts) {
      const outs = choicesOf(p).map(v => outputs({ ...c, [p.key]: v }));
      if (outs.some(o => o.text !== outs[0].text)) return false;
      valued ||= outs[0].value;
    }
    return valued;
  }).map(p => p.key);
}
/** One entry's parameters: the registry's (every kind; condition false for the kinds that only draw and, with
    display_only true, for a select or switch that changes no value, displayOnlyParams), with a row's screener version
    applied (replace: a registry key replaced in place by the listed parameters, a shared one of screener_params by its
    key, an empty list dropping it; add: appended). */
function entryParams(r, sv, shared, W, problems) {
  const params = [], display = new Set(displayOnlyParams(r));
  for (const p of r.params) {
    if (p.terminal_only) continue;                              // a Terminal-only option (FL14's average line, user 2026-11-08 "A")
    const rep = sv?.replace?.[p.key];
    if (rep === undefined) { params.push({ ...structuredClone(p), condition: !FLOW_DISPLAY_KINDS.includes(p.kind) && !display.has(p.key), ...(display.has(p.key) ? { display_only: true } : {}) }); continue }
    for (const x of rep) params.push(screenerParam(typeof x === 'string' ? shared[x] ?? { key: x } : x, W, `flow-kinds.json ${r.id}.screener`, problems));
  }
  for (const k of Object.keys(sv?.replace || {})) if (!r.params.some(p => p.key === k)) problems.push(`flow-kinds.json ${r.id}.screener.replace: ${k} is not a parameter of ${r.id}`);
  for (const x of sv?.add || []) params.push(screenerParam(typeof x === 'string' ? shared[x] ?? { key: x } : x, W, `flow-kinds.json ${r.id}.screener`, problems));
  const keys = params.map(p => p.key);
  for (const k of keys.filter((k, i) => keys.indexOf(k) !== i)) problems.push(`flow-kinds.json ${r.id}: parameter ${k} twice`);
  return params;
}
/** The Screener's flow entries (generated, never typed: P5_FLOW.md sections 2 and 3): one per FL of flowRegistry.json,
    with the registry's name, family, unit, place, tip and parameters as they are, the outputs with their kind from
    flow-kinds.json (a test fails, and this build stops, when an FL or an output has no row), the default output (the
    first), the ADV floor flag, the data the Screener does not hold (requires: insider for FL31) and whether a default
    reads the broker classification (a `class:` broker list, FL34); then the Screener's versions (P5b: a row's
    `screener`: compute, the parameters it replaces or adds, the outputs it replaces, the catalog's formula and misuse
    words; version 'screener') and the point-in-time guard (current_only, FL34); then the Screener's own entries
    (screener_entries: fnet, ksei_net). The board default stays the registry's Regular (G1, user 2026-11-07), except
    where a screener entry keeps its old definition's (fnet: every board). */
export function flowEntries(reg, kinds) {
  const problems = [];
  if (!reg || !Array.isArray(reg.indicators)) throw new Error('flowRegistry.json has no indicators');
  const rows = kinds?.indicators || {}, shared = kinds?.screener_params || {}, W = kinds?.window_sessions;
  if (!Number.isInteger(W) || W < 2) problems.push('flow-kinds.json: window_sessions must be a whole number of at least 2');
  for (const id of Object.keys(rows)) if (!reg.indicators.some(r => r.id === id)) problems.push(`flow-kinds.json: ${id} is not an indicator of flowRegistry.json`);
  const common = (row, where) => {
    if (typeof row.adv_floor !== 'boolean') problems.push(`${where} adv_floor must be true or false`);
    if (row.requires !== undefined && !['insider', 'ksei'].includes(row.requires)) problems.push(`${where} requires ${row.requires}: only insider and ksei are known`);
    const compute = row.screener?.compute ?? row.compute ?? 'terminal';
    if (!FLOW_COMPUTES.includes(compute)) problems.push(`${where} compute ${compute} is not one of ${FLOW_COMPUTES.join(', ')}`);
    return compute;
  };
  /* user 2026-11-08 ("A"): an indicator or output the registry marks terminal_only (FL49-FL52, FL14's average line) is
     drawn by the Terminal and not offered here, until a decision adds it with its kinds */
  const flows = reg.indicators.filter(r => !r.terminal_only).map(r => {
    const row = rows[r.id];
    if (!row) { problems.push(`flow-kinds.json: ${r.id} ${r.name} has no row`); return null }
    const sv = row.screener, params = entryParams(r, sv, shared, W, problems), outKeys = sv?.replace_outputs ? Object.keys(row.outputs || {}) : r.outputs.filter(o => !(r.terminal_only_outputs || []).includes(o));
    const keys = Object.keys(row.outputs || {});
    for (const o of outKeys) if (!keys.includes(o)) problems.push(`flow-kinds.json: ${r.id} output ${o} has no kind`);
    for (const o of keys) if (!outKeys.includes(o)) problems.push(`flow-kinds.json: ${r.id} ${o} is not an output`);
    for (const o of outKeys) if (row.outputs?.[o]) problems.push(...flowKindProblems(`flow-kinds.json ${r.id}.${o}`, row.outputs[o], r.id, params));
    const compute = common(row, `flow-kinds.json: ${r.id}`);
    return {
      id: r.id, name: r.name, family: r.family, unit: r.unit, place: r.place, tip: r.tip ?? null, needs_frequency: !!r.needs_frequency,
      outputs: outKeys.map(o => ({ key: o, kind: row.outputs?.[o] ?? null })),
      default_output: outKeys[0],
      params,
      adv_floor: !!row.adv_floor,
      requires: row.requires ?? null,
      needs_classification: params.some(p => typeof p.default === 'string' && p.default.startsWith('class:')),
      version: sv && (sv.compute || sv.replace || sv.add || sv.replace_outputs) ? 'screener' : 'terminal', compute,
      current_only: !!row.current_only,
      formula: sv?.formula ?? null, misuse: sv?.misuse ?? null,
    };
  });
  for (const [id, e] of Object.entries(kinds?.screener_entries || {})) {
    const where = `flow-kinds.json screener_entries.${id}`;
    if (reg.indicators.some(r => r.id === id)) problems.push(`${where}: ${id} is an indicator of flowRegistry.json`);
    for (const k of ['name', 'family', 'place', 'unit', 'tip', 'formula', 'misuse']) if (typeof e[k] !== 'string' || !e[k]) problems.push(`${where}: ${k} is required`);
    const params = (e.params || []).map(p => screenerParam(p, W, where, problems)), keys = Object.keys(e.outputs || {});
    if (!keys.length) problems.push(`${where}: outputs are required`);
    for (const o of keys) problems.push(...flowKindProblems(`${where}.${o}`, e.outputs[o], id, params));
    const compute = common(e, `${where}:`);
    if (compute === 'none' && !e.requires) problems.push(`${where}: an entry that is never computed names the data it requires`);
    flows.push({
      id, name: e.name, family: e.family, unit: e.unit, place: e.place, tip: e.tip, needs_frequency: false,
      outputs: keys.map(o => ({ key: o, kind: e.outputs[o] })), default_output: keys[0], params,
      adv_floor: !!e.adv_floor, requires: e.requires ?? null, needs_classification: false,
      version: 'screener', compute, current_only: false, formula: e.formula, misuse: e.misuse,
    });
  }
  if (problems.length) throw new Error(`flow kinds:\n  ${problems.join('\n  ')}`);
  return flows;
}

/* ---- the basis probe (EXEC-PRICE-DISTORTION D-5; the user 2026-11-24: "untuk mereka yang tertangkap, maka akan tetap
   di show seluruhnya, tapi dengan badge, berikut juga untuk cell flownya?", yes) ------------------------------------------
   A Flow cell is marked when the window it reads crosses a corporate action whose broker lots are not on one basis with
   the lots after it, or a price break, and only when its output reads what that distorts. Which outputs do is derived
   here, never listed: per output, `reads` (a subset of BASIS_READS), `reads_from` (depth: its value at a candle reads its
   depth's sessions, flowmetrics.ts indicatorDepth; window_start: it still reads the candles before them, from the start
   of the loaded window) and `reads_probe` (measured, or cannot_tell when no context gave it two different values and no
   perturbation moved it: a flag that never fires on the probe; it is then taken to read everything from the window's
   start, so a cell may be marked where it need not be, never left unmarked where it should be). */
export const BASIS_READS = ['lots', 'close', 'volume'];
/** A difference of two values beyond the probe's relative tolerance, or a value against none. */
const basisDiffers = (a, b) => {
  const fa = typeof a === 'number' && Number.isFinite(a), fb = typeof b === 'number' && Number.isFinite(b);
  if (fa !== fb) return true;
  return fa && Math.abs(a - b) > PROBE.basis.tolerance * Math.max(1, Math.abs(a), Math.abs(b));
};
/** The parameter contexts the basis probe runs an entry at: the registry defaults (an anchor date at the window's first
    candle, as indicatorDepth probes it) and, as displayOnlyParams builds them, each select or switch at each of its other
    options and each list at each single option and at all of them; around every anchor, an anchor being the defaults and
    each option of a select or switch that gives an output the defaults do not (a sided indicator's sell line); and each
    of these again with every whole-number parameter raised by PROBE.basis.raise_sessions (within its maximum), so a
    window of one session, where a share or a concentration of one candle does not mix candles, is probed over several
    too. */
export function basisContexts(e, compute = computeEntry) {
  const cond = e.params.filter(p => p.condition && p.default !== undefined);
  const defaults = Object.fromEntries(cond.map(p => [p.key, structuredClone(p.default)]));
  for (const p of e.params) if (p.kind === 'date' && typeof defaults[p.key] === 'string') defaults[p.key] = 'view';
  const choosers = cond.filter(p => (p.kind === 'select' || p.kind === 'bool') && choicesOf(p).length > 1).map(q => [q.key, choicesOf(q)]);
  const lists = cond.filter(p => p.kind === 'multi' && choicesOf(p).length > 1).map(q => [q.key, [...choicesOf(q).map(o => [o]), choicesOf(q)]]);
  const ints = cond.filter(p => p.kind === 'int');
  const raise = c => ({ ...c, ...Object.fromEntries(ints.map(q => [q.key, Math.min(q.max ?? Infinity, c[q.key] + PROBE.basis.raise_sessions)])) });
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const around = a => [a, ...[...choosers, ...lists].flatMap(([k, values]) => values.filter(v => !same(v, a[k])).map(v => ({ ...a, [k]: v })))];
  const outputsAt = c => Object.keys(compute(e, probeContext(probeLength(e.params, c)), c));
  const produced = new Set(outputsAt(defaults)), anchors = [defaults];
  for (const [k, values] of choosers) for (const v of values) {
    const c = { ...defaults, [k]: v }, got = outputsAt(c);
    if (got.some(o => !produced.has(o))) { anchors.push(c); got.forEach(o => produced.add(o)) }
  }
  const seen = new Set(), out = [];
  for (const a of anchors) for (const c of around(a)) for (const x of ints.length ? [c, raise(c)] : [c]) {
    const key = JSON.stringify(x);
    if (!seen.has(key)) { seen.add(key); out.push(x) }
  }
  return out;
}
/** The basis probe of one entry (above): on each context of basisContexts, a context of L = 2P + 2 candles (P the
    probe's length at those parameters, flowprobe.ts probeLength, so every output has its value well before t0 = P and
    a window of its depth ending at the last candle lies after t0) with a third of the brokers turned at t0
    (turnedContext); the outputs from t0 on compared with the same entry's on the context with the lots up to t0 times
    each of PROBE.basis.lots_factors (scaledLots), the closes up to t0 times close_factor and the volumes times
    volume_factor (scaledBars). An output reads what changed it on any context (conservative: it may mark more cells,
    never fewer); a difference still at the last candle means it reads further back than its depth (window_start).
    `compute` is the function the Screener computes the entry with (flowscreener.ts computeEntry; a test plants
    another). An entry never computed (compute none) gets none: null. */
export function basisReads(e, compute = computeEntry) {
  if (e.compute === 'none') return null;
  const B = PROBE.basis, res = Object.fromEntries(e.outputs.map(o => [o.key, { reads: new Set(), told: false, whole: false }]));
  for (const values of basisContexts(e, compute)) {
    const P = probeLength(e.params, values), L = 2 * P + 2, t0 = P;
    const base = turnedContext(probeContext(L), t0), out0 = compute(e, base, values);
    const perturbed = [...B.lots_factors.map(f => ['lots', scaledLots(base, t0, f)]), ['close', scaledBars(base, t0, 'close', B.close_factor)], ['volume', scaledBars(base, t0, 'volume', B.volume_factor)]];
    const outs = perturbed.map(([read, c]) => [read, compute(e, c, values)]);
    for (const o of e.outputs) {
      const a = out0[o.key], r = res[o.key];
      if (!a) continue;
      const seen = new Set();
      for (let t = t0; t < L && seen.size < 2; t++) if (typeof a[t] === 'number' && Number.isFinite(a[t])) seen.add(a[t]);
      if (seen.size > 1) r.told = true;
      for (const [read, out] of outs) {
        const b = out[o.key];
        for (let t = t0; t < L; t++) if (basisDiffers(a[t], b?.[t])) { r.reads.add(read); r.told = true; break }
        if (basisDiffers(a[L - 1], b?.[L - 1])) r.whole = true;
      }
    }
  }
  return Object.fromEntries(e.outputs.map(o => {
    const r = res[o.key];
    return [o.key, r.told ? { reads: BASIS_READS.filter(x => r.reads.has(x)), reads_from: r.whole ? 'window_start' : 'depth', reads_probe: 'measured' }
      : { reads: [...BASIS_READS], reads_from: 'window_start', reads_probe: 'cannot_tell' }];
  }));
}
/** The flow entries with each output's basis probe (basisReads) beside its kind. */
export const withBasisReads = (flows, compute = computeEntry) => flows.map(e => {
  const reads = basisReads(e, compute);
  return reads ? { ...e, outputs: e.outputs.map(o => ({ ...o, ...reads[o.key] })) } : e;
});

/* ---- the candlestick patterns (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/P6_CANDLES.md section 2) ------- */
/** The Screener's candle entries, generated from the Backtest core's candle registry (candles.ts CANDLES, read through
    the core's own module, never a copy): per pattern its id, name, side, pair and mirror, the candles it reads, its
    parameters in the catalog's parameter shape (label, default, min, max, options and the registry's plain meaning;
    step 1 for whole numbers and for percent shares, 0.1 for multiples), the exact definition (candleFormula), the
    plain interpretation and misuse words, the search synonyms and the sessions it reads at its defaults. */
export function candleEntries(core) {
  const { CANDLES, candleFormula, candleLookback } = core;
  const guard = 'A day without trades or a missing bar is never a candle of a pattern, and every candle spans at least the minimum range in price ticks of its price band (IDX tick sizes). Prices are the series the Screener reads (adjusted for corporate actions as the price data is).';
  return CANDLES.patterns.map(p => ({
    id: p.id, name: p.name, side: p.side, pair: p.pair, mirror: p.mirror, bars: p.bars, trend: p.trend,
    params: p.params.map(q => ({
      key: q.key, type: q.type, label: q.label, default: q.default,
      ...(q.type === 'enum' ? { options: q.options } : { min: q.min, max: q.max, step: q.type === 'integer' || q.max > 20 ? 1 : 0.1 }),
      exclusive_min: false, integer: q.type === 'integer', meaning: q.meaning,
    })),
    formula: candleFormula(p.id), interpretation: p.summary, misuse: `${p.misuse} ${guard}`, synonyms: p.synonyms,
    sessions_at_defaults: candleLookback(p.id),
  }));
}

/* ---- the oracle mapping (report 7.3) -------------------------------------------------------------------------- */
function readOracle() {
  const r = spawnSync('python3', [at(PATHS.spec), '--json'], { encoding: 'utf8', maxBuffer: 16 << 20 });
  if (r.error) throw new Error(`python3 is needed to read the oracle mapping (${PATHS.spec} --json): ${r.error.message}`);
  if (r.status !== 0) throw new Error(`${PATHS.spec} --json failed: ${r.stderr.trim()}`);
  return Object.fromEntries(JSON.parse(r.stdout).indicators.map(x => [x.id, x]));
}

/** The options the screener offers per enum parameter of base indicator r (the base's, or the overlay's decided subset
    in base order), and the start configuration: the registry defaults, with the overlay's start where the registry
    default is not offered (P17 a: I43 anchor Week instead of Session). It is what a new card opens with and what the
    snapshot pre-warms (report 6.7), so the derived fields are measured on it. */
function startConfig(r, ov, DEFAULTS) {
  const offered = Object.fromEntries(r.params.filter(p => p.type === 'enum')
    .map(p => [p.key, ov.params?.[p.key] ? p.options.filter(o => ov.params[p.key].options.includes(o)) : p.options]));
  const starts = Object.fromEntries(Object.entries(ov.params || {}).filter(([, s]) => s.start !== undefined).map(([k, s]) => [k, s.start]));
  return { offered, starts, defaults: { ...DEFAULTS[r.key], ...starts } };
}

/** The cost probe's job for the base registry: every integer parameter at its start configuration, worst over the
    offered options of every enum parameter (the default first). */
export function costJob(base, overlay, DEFAULTS) {
  const groups = base.indicators.flatMap(r => {
    const { offered, defaults } = startConfig(r, overlay.indicators[r.id], DEFAULTS);
    const variants = [{}, ...r.params.filter(e => e.type === 'enum').flatMap(e => offered[e.key].filter(o => o !== defaults[e.key]).map(o => ({ [e.key]: o })))];
    return r.params.filter(p => p.type === 'integer').map(p => ({ id: r.id, key: r.key, param: p.key, value: p.default, base: defaults, variants }));
  });
  return { module: at(PATHS.calc), bars: PROBE.cost_bars, groups };
}

/* ---- build ---------------------------------------------------------------------------------------------------- */
export async function build({ against = null } = {}) {
  const base = readJson(PATHS.base), terminal = readJson(PATHS.terminal), overlay = readJson(PATHS.overlay);
  const { F, DEFAULTS } = await import(at(PATHS.calc));
  const { BY_ID, REGISTRY_VERSION, resolveParams } = await import(at(PATHS.coreRegistry));
  const { canonicalJson } = await import(at(PATHS.hash));
  if (REGISTRY_VERSION !== base.registry_version) throw new Error('backtest registry.ts and backtest-registry.json disagree');
  const problems = overlayProblems(overlay, base);
  if (problems.length) throw new Error(`screener-overlay.json:\n  ${problems.join('\n  ')}`);
  const oracle = readOracle(), byTerminal = Object.fromEntries(terminal.map(r => [r.id, r]));
  const B = fixture(), cut = sliceBars(B, PROBE.cut_at);
  const cost = new Map(measureCost(costJob(base, overlay, DEFAULTS)).map(c => [`${c.id}.${c.param}`, c.cost_class]));
  const committed = committedRegistry(against), lowered = costLowerings(committed?.doc, cost, overlay);
  if (lowered.length) throw new Error(costLoweringRefusal(lowered, committed.from));

  const indicators = base.indicators.map(r => {
    const ov = overlay.indicators[r.id], ti = byTerminal[r.id], fn = F[r.key];
    if (!fn || !ti) throw new Error(`${r.id}: no function or terminal entry`);
    const { offered, starts, defaults } = startConfig(r, ov, DEFAULTS);
    const startParams = resolveParams(BY_ID[r.id], starts, `overlay ${r.id}.params`);
    const run = (bars, over = {}) => fn(bars, { ...defaults, ...over });
    const bandOutputs = ov.shape === 'band' ? r.outputs : [];
    const hasAnchor = r.params.some(p => p.key === 'anchor');
    // the scaling and lag probes may run at the overlay's probe configuration (with evidence; today I43, whose registry
    // default anchor makes its bands degenerate); every other field is measured at the start configuration
    const probeParams = ov.probe ? resolveParams(BY_ID[r.id], { ...ov.probe.params }, `overlay ${r.id}.probe.params`) : {};
    const full = run(B), units = unitProbe(b => run(b, probeParams), B), atProbe = run(B, probeParams);
    /* the history class per output at a configuration (`over` applied to the start configuration): the cut probe, then the
       reach probe on the price shapes for the outputs it finds window (UD36), then (withWindows) the effective probe for
       the outputs it finds recursive, on their fields there (the poison probe's; UD55). An output without any value at
       `over` has no entry (no condition reads it there: inputsOf gives [], validate.ts refuses it). */
    const historyAt = (over, withWindows = true) => {
      const f = run(B, over), c = run(cut, over), valued = r.outputs.filter(o => f[o].some(isN));
      const cls = Object.fromEntries(valued.map(o => [o, historyClass(f[o], c[o], PROBE.cut_at, hasAnchor)]));
      const win = valued.filter(o => cls[o] === 'window'), reach = win.length ? reachProbe(b => run(b, over), win) : {};
      const rec = withWindows ? valued.filter(o => cls[o] === 'recursive') : [];
      const fields = rec.length ? inputsProbe(b => run(b, over), B, r.outputs) : {};
      const eff = rec.length ? effectiveProbe(b => run(b, over), rec, o => fields[o]) : {};
      return Object.fromEntries(valued.map(o => {
        const h = reachClass(cls[o], reach[o]?.beyond ?? 0);
        if (h !== 'recursive' || !withWindows) return [o, { history_class: h }];
        return [o, { history_class: h, effective_window: cls[o] === 'recursive' ? eff[o] : { bars: null, reason: 'reach', at: `${reach[o].shape}@${reach[o].cut}` } }];
      }));
    };
    const startHistory = historyAt({});
    const inputs = inputsProbe(b => run(b), B, r.outputs);
    const inputsBy = {};
    for (const p of r.params.filter(q => q.type === 'enum')) {
      inputsBy[p.key] = {};
      for (const opt of offered[p.key]) {
        const per = inputsProbe(b => run(b, { [p.key]: opt }), B, r.outputs);
        for (const o of r.outputs) (inputsBy[p.key][opt] ||= {})[o] = per[o];
      }
    }
    const overrides = (overlay.overrides || []).filter(x => x.indicator === r.id);
    const params = r.params.map(p => {
      const tp = ti.params.find(x => x.k === p.key);
      const q = { key: p.key, type: p.type, label: tp?.label ?? null, default: p.default };
      for (const k of ['min', 'max', 'step', 'options']) if (p[k] !== undefined) q[k] = p[k];
      q.exclusive_min = false; q.integer = p.type === 'integer'; q.narrowing = [];
      const decided = ov.params?.[p.key];
      if (decided) {
        q.options = offered[p.key];
        q.narrowing.push({ rule: 'options', source: 'decision', evidence: decided.decision });
        if (decided.start !== undefined) q.start = decided.start;
      }
      if ((p.type === 'integer' || p.type === 'number') && p.min !== undefined) {
        const why = degenerate(run(B, { [p.key]: p.min }), r.outputs, bandOutputs);
        const ovr = overrides.find(x => x.param === p.key);
        if (why && ovr) throw new Error(`override ${r.id}.${p.key}: the degeneracy probe already makes the minimum exclusive (${why}); remove the override`);
        if (why) { q.exclusive_min = true; q.narrowing.push({ rule: 'exclusive_min', source: 'degeneracy_probe', evidence: `at ${p.key} = ${p.min}: ${why}` }) }
        if (ovr) { q.exclusive_min = true; q.narrowing.push({ rule: 'exclusive_min', source: 'override', evidence: ovr.evidence }) }
      }
      if (p.type === 'number' && (p.max === undefined || p.default + 0.5 <= p.max) && floored(run, B, p.key, p.default)) {
        q.integer = true; q.narrowing.push({ rule: 'integer', source: 'floor_probe', evidence: `F gives the same outputs at ${p.default} and ${p.default + 0.5}` });
      }
      if (p.type === 'integer') {
        q.cost_class = cost.get(`${r.id}.${p.key}`);
        const review = q.cost_class === LOWER.to ? costReviewOf(overlay, r.id, p.key) : undefined;
        if (review) q.cost_review = { reason: review.reason, reviewed: review.reviewed };
      }
      return q;
    });
    const { byOption, combined, scaling } = historyByOption(params, defaults, hasAnchor, startHistory, historyAt,
      W0 => effectiveScaling(over => effectiveProbe(b => run(b, over), Object.keys(W0), o => inputs[o]), params, defaults, W0));
    const outputs = r.outputs.map(o => {
      const to = ti.outs.find(x => x.k === o), u = units[o], spec = ov.outputs[o];
      const field = u.comparable_with === 'close' ? B.C : u.comparable_with === 'volume' ? B.V : null;
      if (to?.categories !== undefined) { const bad = categoryProblems(to.categories, `indRegistry ${r.id}.${o}`); if (bad.length) throw new Error(bad.join('; ')) }
      for (const t of spec.tests || []) {
        const need = TEST_FORMS[t.form].needs;
        if (need === 'categories') {
          if (!to?.categories) throw new Error(`overlay ${r.id}.${o}: ${t.form} needs an output with categories (indRegistry outs[].categories)`);
          const bad = Object.entries(t.defaults || {}).flatMap(([k, v]) => categoryDefaultProblems(k, v, to.categories, `overlay ${r.id}.${o} ${t.form}`));
          if (bad.length) throw new Error(bad.join('; '));
        }
        if (need === 'close' && u.comparable_with !== 'close') throw new Error(`overlay ${r.id}.${o}: ${t.form} needs a price level (the scaling probe finds ${u.unit})`);
        if (need === 'level' && !u.comparable_with) throw new Error(`overlay ${r.id}.${o}: ${t.form} needs a level comparable with a bar field (the scaling probe finds ${u.unit})`);
        if (need === 'band' && !(['upper', 'lower'].every(b => units[b]?.comparable_with === 'close') || ['upper1', 'lower1'].every(b => units[b]?.comparable_with === 'close')))
          throw new Error(`overlay ${r.id}.${o}: ${t.form} needs upper and lower price bands`);
      }
      return {
        key: o, label: to?.label ?? null, display_unit: ti.unit ?? null,
        ...(to?.categories ? { categories: to.categories.map(({ value, key, label }) => ({ value, key, label })) } : {}),
        /* checker SC-7 (2026-11-23): an output that only colours another one (indRegistry outs[].paletteFrom names it) and
           has no test is the Terminal's drawing aid, not a series to screen (the operator panel leaves it out) */
        ...(!(spec.tests || []).length && ti.outs.some(x => x.paletteFrom === o) ? { drawing_only: true } : {}),
        unit: u.unit, level_comparable: u.comparable_with !== null, comparable_with: u.comparable_with,
        price_compare_lag: field ? compareLag(field, atProbe[o]) : { gt: 0, lt: 0 },
        history_class: startHistory[o].history_class,
        // UD55: a recursive output's effective window at the start configuration, with its scaling rule; UD52: the class
        // (and window) of each enum or switch option that differs from the start configuration's, and the class of two
        // or more options together where the worst of theirs does not hold (historyByOption)
        ...(startHistory[o].effective_window ? { effective_window: { ...startHistory[o].effective_window, ...(scaling[o] ? { scaling: scaling[o] } : {}) } } : {}),
        ...(byOption[o] ? { history_by_option: byOption[o] } : {}),
        ...(combined[o] ? { history_class_combined: combined[o] } : {}),
        first_valid_bar: firstValid(full[o]),
        inputs: inputs[o],
        inputs_by_source: Object.fromEntries(Object.entries(inputsBy).map(([k, opts]) => [k, Object.fromEntries(Object.entries(opts).map(([opt, per]) => [opt, per[o]]))])),
        tests: spec.tests || [], disabled_tests: spec.disabled_tests || [],
      };
    });
    const history = worstClass(outputs.map(o => o.history_class));
    const orc = oracle[r.id] || { oracle: [], oracle_note: null };
    const oracleRows = orc.oracle.map(e => {
      if (!r.outputs.includes(e.output)) throw new Error(`oracle ${r.id}: ${e.output} is not an output`);
      const row = { output: e.output, params: resolveParams(BY_ID[r.id], e.params, `oracle ${r.id}`), table: e.table };
      if (e.column) row.column = e.column; else { row.expr = e.expr; row.columns = e.columns }
      return row;
    });
    return {
      id: r.id, key: r.key, name: r.name, category: r.category, short: ti.short ?? null,
      formula_version: base.registry_version,
      params,
      start_params: startParams,
      default_offered: !Object.keys(starts).length,
      hidden_params: r.not_accepted.filter(n => n.reason === 'not read by the calculation module').map(n => ({ key: n.key, reason: n.reason })),
      fixed_params: r.not_accepted.filter(n => n.reason !== 'not read by the calculation module').map(n => ({ key: n.key, value: n.value, reason: n.reason })),
      outputs, history_class: history,
      cost_class: params.some(p => p.cost_class === 'O(N·n)') ? 'O(N·n)' : 'O(N)',
      description: ov.description,
      overlay: { shape: ov.shape, synonyms: ov.synonyms, default_test: ov.default_test },
      probe_params: ov.probe ? { params: probeParams, evidence: ov.probe.evidence } : null,
      oracle: oracleRows, oracle_note: orc.oracle_note ?? null,
    };
  });
  // narrow-only (report 6.8): the overlay and the derived fields never widen a base range or add a parameter or option
  for (const s of indicators) for (const p of s.params) {
    const b = BY_ID[s.id].params.find(x => x.key === p.key);
    if (!b || p.min !== b.min || p.max !== b.max || p.default !== b.default || (b.type === 'integer' && !p.integer)
      || (b.options && (!p.options?.length || p.options.some(o => !b.options.includes(o)))) || (p.start !== undefined && !p.options?.includes(p.start)))
      throw new Error(`narrow-only: ${s.id}.${p.key} differs from the base`);
  }
  const doc = {
    schema_version: 1,
    screener_registry_version: '',
    registry_version: base.registry_version,
    generated_by: PATHS.generator,
    sources: Object.entries({ base: PATHS.base, terminal: PATHS.terminal, calc: PATHS.calc, overlay: PATHS.overlay, oracle: PATHS.spec, generator: PATHS.generator,
      flow_registry: PATHS.flowRegistry, flow_kinds: PATHS.flowKinds, flow_calc: PATHS.flowCalc, flow_probe: PATHS.flowProbe, flow_screener: PATHS.flowScreener,
      candle_registry: PATHS.candleRegistry, candles: PATHS.candles, effective: PATHS.effective })
      .map(([role, file]) => ({ role, file, sha256: sha256(fs.readFileSync(at(file))) })),
    probe: PROBE,
    cost_model: overlay.cost_model,
    indicators,
    flows: withBasisReads(flowEntries(readJson(PATHS.flowRegistry), readJson(PATHS.flowKinds))),
    candles: candleEntries(await import(at(PATHS.candles))),
  };
  const { screener_registry_version: _v, ...hashed } = doc;
  doc.screener_registry_version = sha256(canonicalJson(hashed)).slice(0, 16);
  return doc;
}

export const serialize = doc => JSON.stringify(doc, null, 2) + '\n';

/** EXEC-BACKTEST-REVAMP P2 (user K5 a, 2026-11-15; ERRORS M451): the outputs the lag probe reads one bar late against
    a bar field (price_compare_lag gt or lt 1, e.g. Donchian's bands, which hold today's high and low), written for the
    Backtest core (conditions.ts indicatorCondition): its "price above / crosses above the upper band" then reads the
    band of the prior bar, as the Screener does, instead of a comparison that can never be true. One derivation (this
    probe) for both; an output the probe marks later is covered without a code change. The Backtest core cannot read
    screener-registry.json itself (its generator reads the Backtest registry; the page would also carry 0.46 MB).
    ERRORS M554 (2026-11-23): the same file carries `price_levels`, the outputs of each indicator the unit probe marks as
    a price level (unit price, comparable with close: they scale with the price and move with a shift of it), in the
    registry's order. The Backtest's price lines (engine.ts LEVEL_LINES and lineOf, the page's reg.ts LEVEL_LINES: the
    lines a stop or a trailing stop can sit on) read it instead of every output but one named `direction`, which offered
    a 0/1 flag of an indicator drawn on the price (Inside Bar's `ib`) as a stop line. */
export function compareLagDoc(doc) {
  const lag = {}, levels = {};
  for (const i of doc.indicators) for (const o of i.outputs) {
    const l = o.price_compare_lag;
    if (l && (l.gt || l.lt)) (lag[i.id] ??= {})[o.key] = { field: o.comparable_with, gt: l.gt, lt: l.lt };
    if (o.unit === 'price' && o.comparable_with === 'close') (levels[i.id] ??= []).push(o.key);
  }
  return {
    schema_version: 2,
    about: 'Indicator outputs a comparison with a bar field reads one bar late (the lag probe of build-screener-registry.mjs, report 6.8): price gt / crosses_above the output reads its gt entry, lt / crosses_below its lt entry. price_levels: the outputs the unit probe marks as a price level (unit price, comparable with close), the only ones a Backtest stop or trailing stop can sit on. Generated: do not edit.',
    generated_by: PATHS.generator,
    price_compare_lag: lag,
    price_levels: levels,
  };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  if (process.argv.includes('--cost-work')) {
    try {
      process.stdout.write(JSON.stringify(await costWork(JSON.parse(fs.readFileSync(0, 'utf8')))));
    } catch (e) {               // a refusal of the probe is its message; anything else keeps its stack
      console.error(e instanceof Error && e.message.startsWith('cost probe') ? e.message : e);
      process.exitCode = 1;
    }
  } else {
    const k = process.argv.indexOf('--against'), against = k > 0 ? process.argv[k + 1] : null;
    if (k > 0 && (!against || !process.argv.includes('--check'))) { console.error('--against <registry file> is for --check only: a regeneration that writes is compared with the committed registry (a lowered cost_class needs its cost_reviews entry)'); process.exit(2) }
    let text, doc;
    try { doc = await build({ against }); text = serialize(doc) }
    catch (e) {                 // a refusal of the build is its message (rule, fix and examples); anything else keeps its stack
      if (!(e instanceof Error && e.message.startsWith('cost_class lowered'))) throw e;
      console.error(e.message);
      process.exit(1);
    }
    const files = [[PATHS.out, text], [PATHS.compareLag, serialize(compareLagDoc(doc))]];
    if (process.argv.includes('--check')) {
      let stale = false;
      for (const [file, want] of files) {
        const current = fs.existsSync(at(file)) ? fs.readFileSync(at(file), 'utf8') : '';
        if (current !== want) { console.error(`${file} is stale: run npm run registry (in apps/edge-bff/screener)`); stale = true }
        else console.log(`${file} is current`);
      }
      if (stale) process.exit(1);
    } else {
      for (const [file, want] of files) { fs.writeFileSync(at(file), want); console.log(`wrote ${file}`) }
    }
  }
}
