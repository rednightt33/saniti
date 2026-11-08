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
      a deterministic synthetic series, for all 76 outputs: first_valid_bar, history_class (cut probe), unit and
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
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { computeFlow } from '../../terminal/src/calc/flow.ts';
import { probeContext, probeLength } from '../src/core/flowprobe.ts';

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
  flowRegistry: 'apps/edge-bff/terminal/src/data/flowRegistry.json',
  flowKinds: 'apps/edge-bff/screener/src/core/flow-kinds.json',
  flowCalc: 'apps/edge-bff/terminal/src/calc/flow.ts',
  flowProbe: 'apps/edge-bff/screener/src/core/flowprobe.ts',
  candleRegistry: 'apps/edge-bff/backtest/src/core/candle-registry.json',
  candles: 'apps/edge-bff/backtest/src/core/candles.ts',
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
};
const MA_TYPES = ['SMA', 'EMA'];

/* ---- the deterministic synthetic series the probes run on -------------------------------------------------- */
/** Probe settings; recorded in the generated file so a reader knows what the derived fields were measured on. */
export const PROBE = Object.freeze({
  seed: 20261028, bars: 4000, start: '2016-01-04', cut_at: 1000,
  scale_price: 3.7, scale_volume: 5.3, shift_price_of_median: 0.5, shift_volume_of_median: 0.5,
  tolerance: 1e-9, unit_tolerance: 1e-6, min_common_bars: 100, converged_ratio: 1e-3,
  cost_bars: 10000, cost_long_length: 1000, cost_measure: 'v8_block_coverage_executed_source_chars', cost_tier: '--max-opt=1',
  cost_growth: 2, cost_margin: 2,
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
const mapBars = (B, f) => ({ O: B.O.map(f.p), H: B.H.map(f.p), L: B.L.map(f.p), C: B.C.map(f.p), V: B.V.map(f.v), T: B.T });
const sliceBars = (B, from) => ({ O: B.O.slice(from), H: B.H.slice(from), L: B.L.slice(from), C: B.C.slice(from), V: B.V.slice(from), T: B.T.slice(from) });
const median = xs => { const s = [...xs].sort((a, b) => a - b); return s[s.length >> 1] };

/* ---- series helpers ------------------------------------------------------------------------------------------ */
const isN = v => typeof v === 'number' && Number.isFinite(v);
const finite = s => s.filter(isN);
const firstValid = s => { const i = s.findIndex(isN); return i < 0 ? null : i };
/** A series' magnitude for tolerances: its 99th percentile absolute value (1 when it has none). */
function scaleOf(s) { const v = finite(s).map(Math.abs).sort((a, b) => a - b); return v.length ? Math.max(v[Math.floor((v.length - 1) * 0.99)], 1e-12) : 1 }
/** other[i] equals f(base[i]) on every bar where both are finite, the two have the same finite bars, and there are at
    least min_common_bars of them; equality within unit_tolerance x the larger magnitude. The scaled and shifted inputs
    differ from the base by factors (3.7, 5.3) or offsets (half the median) far above it, while running sums and the
    E[x²] - E[x]² of a band leave residue up to about the square root of the double precision (2e-8 relative, measured
    on I43 upper1 at a period's first bar), so 1e-6 separates the cases with room on both sides. */
function related(base, other, f) {
  const b = base.map(v => isN(v) ? f(v) : null), tol = PROBE.unit_tolerance * Math.max(scaleOf(b), scaleOf(other));
  let n = 0;
  for (let i = 0; i < b.length; i++) {
    if (isN(b[i]) !== isN(other[i])) return false;
    if (!isN(b[i])) continue;
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
    const full = run(B), cutOut = run(cut), units = unitProbe(b => run(b, probeParams), B), atProbe = run(B, probeParams);
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
    const outputs = r.outputs.map(o => {
      const to = ti.outs.find(x => x.k === o), u = units[o], spec = ov.outputs[o];
      const field = u.comparable_with === 'close' ? B.C : u.comparable_with === 'volume' ? B.V : null;
      for (const t of spec.tests || []) {
        const need = TEST_FORMS[t.form].needs;
        if (need === 'close' && u.comparable_with !== 'close') throw new Error(`overlay ${r.id}.${o}: ${t.form} needs a price level (the scaling probe finds ${u.unit})`);
        if (need === 'level' && !u.comparable_with) throw new Error(`overlay ${r.id}.${o}: ${t.form} needs a level comparable with a bar field (the scaling probe finds ${u.unit})`);
        if (need === 'band' && !(['upper', 'lower'].every(b => units[b]?.comparable_with === 'close') || ['upper1', 'lower1'].every(b => units[b]?.comparable_with === 'close')))
          throw new Error(`overlay ${r.id}.${o}: ${t.form} needs upper and lower price bands`);
      }
      return {
        key: o, label: to?.label ?? null, display_unit: ti.unit ?? null,
        unit: u.unit, level_comparable: u.comparable_with !== null, comparable_with: u.comparable_with,
        price_compare_lag: field ? compareLag(field, atProbe[o]) : { gt: 0, lt: 0 },
        history_class: historyClass(full[o], cutOut[o], PROBE.cut_at, hasAnchor),
        first_valid_bar: firstValid(full[o]),
        inputs: inputs[o],
        inputs_by_source: Object.fromEntries(Object.entries(inputsBy).map(([k, opts]) => [k, Object.fromEntries(Object.entries(opts).map(([opt, per]) => [opt, per[o]]))])),
        tests: spec.tests || [], disabled_tests: spec.disabled_tests || [],
      };
    });
    const ORDER = ['window', 'calendar', 'recursive', 'cumulative'];
    const history = outputs.reduce((h, o) => ORDER.indexOf(o.history_class) > ORDER.indexOf(h) ? o.history_class : h, 'window');
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
      flow_registry: PATHS.flowRegistry, flow_kinds: PATHS.flowKinds, flow_calc: PATHS.flowCalc, flow_probe: PATHS.flowProbe,
      candle_registry: PATHS.candleRegistry, candles: PATHS.candles })
      .map(([role, file]) => ({ role, file, sha256: sha256(fs.readFileSync(at(file))) })),
    probe: PROBE,
    cost_model: overlay.cost_model,
    indicators,
    flows: flowEntries(readJson(PATHS.flowRegistry), readJson(PATHS.flowKinds)),
    candles: candleEntries(await import(at(PATHS.candles))),
  };
  const { screener_registry_version: _v, ...hashed } = doc;
  doc.screener_registry_version = sha256(canonicalJson(hashed)).slice(0, 16);
  return doc;
}

export const serialize = doc => JSON.stringify(doc, null, 2) + '\n';

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
    let text;
    try { text = serialize(await build({ against })) }
    catch (e) {                 // a refusal of the build is its message (rule, fix and examples); anything else keeps its stack
      if (!(e instanceof Error && e.message.startsWith('cost_class lowered'))) throw e;
      console.error(e.message);
      process.exit(1);
    }
    if (process.argv.includes('--check')) {
      const current = fs.existsSync(at(PATHS.out)) ? fs.readFileSync(at(PATHS.out), 'utf8') : '';
      if (current !== text) { console.error(`${PATHS.out} is stale: run npm run registry (in apps/edge-bff/screener)`); process.exit(1) }
      console.log(`${PATHS.out} is current`);
    } else {
      fs.writeFileSync(at(PATHS.out), text);
      console.log(`wrote ${PATHS.out}`);
    }
  }
}
