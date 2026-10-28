/* Builds apps/edge-bff/screener/src/core/screener-registry.json, the Screener's indicator contract (EXEC-SCREENER, go
   2026-10-28; report TARGET ARCHITECTURE 6.8 "One approved indicator contract"), from three inputs and nothing typed
   by hand:
   1. the base registry apps/edge-bff/backtest/src/core/backtest-registry.json, unchanged: it stays the only contract
      for ids, keys, parameters, types, defaults, min, max, options, not_accepted and outputs (labels and the workbook
      unit come from the Terminal's indRegistry.json it is built from);
   2. the hand-kept src/core/screener-overlay.json: product choices only (shape, allowed test forms per output with
      the prototype's operators and labels, search synonyms, the card a new condition opens with), explicit overrides
      with their evidence, and the provisional cost model of the caps (P5);
   3. fields derived here by running the Terminal's own formulas F (apps/edge-bff/terminal/src/calc/indicators.ts) on
      a deterministic synthetic series, for all 76 outputs: first_valid_bar, history_class (cut probe), unit and
      level_comparable (scaling and shift probes), price_compare_lag (lag probe), inputs per enum option (poison
      probe), the narrowing (degeneracy probe at each numeric minimum, floor probe, the not_accepted rule),
      cost_class (timing ratio at two lengths), and the Feature 04 / Feature 01 parity oracle read from
      `python3 scripts/terminal_indicator_spec.py --json`.
   The overlay and the derived narrowing may only narrow the base (report 6.8 narrow-only rule), so every transferable
   screener condition stays Backtest-valid. Nothing here changes indicators.ts, indRegistry.json or
   backtest-registry.json (report I3; scripts/screener/check_backtest_untouched.mjs).
   screener_registry_version = the first 16 hex of the sha256 of the canonical JSON of the generated document without
   that field (base registry_version and source hashes included), so it changes whenever any input or derived field does.

   Run (from apps/edge-bff/screener): npm run registry (writes) / npm run registry:check (fails when the committed file
   is stale: every probe field is re-derived and compared). Needs python3 for the oracle mapping. */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

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
  out: 'apps/edge-bff/screener/src/core/screener-registry.json',
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
  cost_bars: 10000, cost_long_length: 1000, cost_reps: 3, cost_slowdown: 2,
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

/** Poison probe: the bar fields (O H L C V) whose loss (all NaN) empties the output are its inputs. */
export function inputsProbe(run, B, outputs) {
  const base = run(B), out = Object.fromEntries(outputs.map(o => [o, []]));
  for (const f of ['O', 'H', 'L', 'C', 'V']) {
    const poisoned = run({ ...B, [f]: B[f].map(() => NaN) });
    for (const o of outputs) if (finite(base[o]).length && !finite(poisoned[o]).length) out[o].push(f);
  }
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

/** The two timings of costClass: the minimum of `reps` alternating runs after one warm-up of each. */
function timePair(a, b, reps) {
  a(); b(); let ta = Infinity, tb = Infinity;
  const time = fn => { const t0 = process.hrtime.bigint(); fn(); return Number(process.hrtime.bigint() - t0) };
  for (let r = 0; r < reps; r++) { ta = Math.min(ta, time(a)); tb = Math.min(tb, time(b)) }
  return [ta, tb];
}
/** cost_class of an integer parameter (report 6.8), from timings at two lengths on a long fixture (cost_bars): the
    default L1 and L2 = max(cost_long_length, 50 x L1), at most a quarter of the bars. The slowdown t(L2) / t(L1) - 1
    of a kernel that loops over its window (O(N·n)) is large (measured 12-31 on HMA, Aroon, Donchian, Stochastic RSI,
    Stochastic, Williams %R, CCI and historical volatility, 3 runs each, 2026-10-28); a running-sum or recursive kernel
    (O(N)) stays at timer noise (measured -0.31 to 0.34 on the other 57 integer parameters). The class is O(N·n) at a
    slowdown of at least cost_slowdown; a result between half and twice that is measured again with three times the
    runs. */
export function costClass(run, B, p, value) {
  const L1 = Math.max(1, value), L2 = Math.min(Math.max(PROBE.cost_long_length, 50 * L1), Math.floor(B.C.length / 4));
  const slowdown = reps => { const [t1, t2] = timePair(() => run(B, { [p]: L1 }), () => run(B, { [p]: L2 }), reps); return t2 / t1 - 1 };
  let s = slowdown(PROBE.cost_reps);
  if (s > PROBE.cost_slowdown / 2 && s < PROBE.cost_slowdown * 2) s = slowdown(PROBE.cost_reps * 3);
  return { cost_class: s >= PROBE.cost_slowdown ? 'O(N·n)' : 'O(N)', lengths: [L1, L2], slowdown: s };
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
  return out;
}

/* ---- the oracle mapping (report 7.3) -------------------------------------------------------------------------- */
function readOracle() {
  const r = spawnSync('python3', [at(PATHS.spec), '--json'], { encoding: 'utf8', maxBuffer: 16 << 20 });
  if (r.error) throw new Error(`python3 is needed to read the oracle mapping (${PATHS.spec} --json): ${r.error.message}`);
  if (r.status !== 0) throw new Error(`${PATHS.spec} --json failed: ${r.stderr.trim()}`);
  return Object.fromEntries(JSON.parse(r.stdout).indicators.map(x => [x.id, x]));
}

/* ---- build ---------------------------------------------------------------------------------------------------- */
export async function build() {
  const base = readJson(PATHS.base), terminal = readJson(PATHS.terminal), overlay = readJson(PATHS.overlay);
  const { F, DEFAULTS } = await import(at(PATHS.calc));
  const { BY_ID, REGISTRY_VERSION, resolveParams } = await import(at(PATHS.coreRegistry));
  const { canonicalJson } = await import(at(PATHS.hash));
  if (REGISTRY_VERSION !== base.registry_version) throw new Error('backtest registry.ts and backtest-registry.json disagree');
  const problems = overlayProblems(overlay, base);
  if (problems.length) throw new Error(`screener-overlay.json:\n  ${problems.join('\n  ')}`);
  const oracle = readOracle(), byTerminal = Object.fromEntries(terminal.map(r => [r.id, r]));
  const B = fixture(), cut = sliceBars(B, PROBE.cut_at), CB = fixture({ bars: PROBE.cost_bars });

  const indicators = base.indicators.map(r => {
    const ov = overlay.indicators[r.id], ti = byTerminal[r.id], fn = F[r.key];
    if (!fn || !ti) throw new Error(`${r.id}: no function or terminal entry`);
    const defaults = { ...DEFAULTS[r.key] };
    const run = (bars, over = {}) => fn(bars, { ...defaults, ...over });
    const bandOutputs = ov.shape === 'band' ? r.outputs : [];
    const hasAnchor = r.params.some(p => p.key === 'anchor');
    // the scaling and lag probes may run at the overlay's probe configuration (with evidence; today I43, whose default
    // anchor makes its bands degenerate); every other field is measured at the registry defaults
    const probeParams = ov.probe ? resolveParams(BY_ID[r.id], { ...ov.probe.params }, `overlay ${r.id}.probe.params`) : {};
    const full = run(B), cutOut = run(cut), units = unitProbe(b => run(b, probeParams), B), atProbe = run(B, probeParams);
    const inputs = inputsProbe(b => run(b), B, r.outputs);
    const inputsBy = {};
    for (const p of r.params.filter(q => q.type === 'enum')) {
      inputsBy[p.key] = {};
      for (const opt of p.options) {
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
        const c = costClass(run, CB, p.key, p.default);
        q.cost_class = c.cost_class;
        // worst over the enum options: a basis or method can swap a running-sum kernel for a window loop (I32 sample)
        for (const e of r.params.filter(x => x.type === 'enum')) for (const opt of e.options) {
          if (q.cost_class === 'O(N·n)' || opt === e.default) continue;
          if (costClass((bars, over) => run(bars, { [e.key]: opt, ...over }), CB, p.key, p.default).cost_class === 'O(N·n)') q.cost_class = 'O(N·n)';
        }
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
      hidden_params: r.not_accepted.filter(n => n.reason === 'not read by the calculation module').map(n => ({ key: n.key, reason: n.reason })),
      fixed_params: r.not_accepted.filter(n => n.reason !== 'not read by the calculation module').map(n => ({ key: n.key, value: n.value, reason: n.reason })),
      outputs, history_class: history,
      cost_class: params.some(p => p.cost_class === 'O(N·n)') ? 'O(N·n)' : 'O(N)',
      overlay: { shape: ov.shape, synonyms: ov.synonyms, default_test: ov.default_test },
      probe_params: ov.probe ? { params: probeParams, evidence: ov.probe.evidence } : null,
      oracle: oracleRows, oracle_note: orc.oracle_note ?? null,
    };
  });
  // narrow-only (report 6.8): the overlay and the derived fields never widen a base range or add a parameter
  for (const s of indicators) for (const p of s.params) {
    const b = BY_ID[s.id].params.find(x => x.key === p.key);
    if (!b || p.min !== b.min || p.max !== b.max || p.default !== b.default || (b.type === 'integer' && !p.integer)) throw new Error(`narrow-only: ${s.id}.${p.key} differs from the base`);
  }
  const doc = {
    schema_version: 1,
    screener_registry_version: '',
    registry_version: base.registry_version,
    generated_by: PATHS.generator,
    sources: Object.entries({ base: PATHS.base, terminal: PATHS.terminal, calc: PATHS.calc, overlay: PATHS.overlay, oracle: PATHS.spec, generator: PATHS.generator })
      .map(([role, file]) => ({ role, file, sha256: sha256(fs.readFileSync(at(file))) })),
    probe: PROBE,
    cost_model: overlay.cost_model,
    indicators,
  };
  const { screener_registry_version: _v, ...hashed } = doc;
  doc.screener_registry_version = sha256(canonicalJson(hashed)).slice(0, 16);
  return doc;
}

export const serialize = doc => JSON.stringify(doc, null, 2) + '\n';

if (process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1])) {
  const text = serialize(await build());
  if (process.argv.includes('--check')) {
    const current = fs.existsSync(at(PATHS.out)) ? fs.readFileSync(at(PATHS.out), 'utf8') : '';
    if (current !== text) { console.error(`${PATHS.out} is stale: run npm run registry (in apps/edge-bff/screener)`); process.exit(1) }
    console.log(`${PATHS.out} is current`);
  } else {
    fs.writeFileSync(at(PATHS.out), text);
    console.log(`wrote ${PATHS.out}`);
  }
}
