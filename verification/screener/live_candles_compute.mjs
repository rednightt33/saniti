/* EDGE Screener unit C live check (EXEC-SCREENER-FLOW-CANDLES P6, the 20 candlestick patterns;
   verification/screener/P6_CANDLES.md): the judge of live_candles_dev.py.

   1. An INDEPENDENT implementation of the 20 patterns, written from P6_CANDLES.md section 5 (the shared parameters, the
      guards, the trend and the table of rules). Nothing is imported: not candles.ts, not candle-registry.json, not the
      screener core; the defaults are typed here from the document, and each pattern's geometry is its own code below
      (the core instead evaluates the registry's rules with one evaluator). The comparisons are written as the document
      states them ("body <= 30 % of range" is 100 x body <= 30 x range; "the average of trend_length sessions" is
      trend_length x close against their sum), so integer prices compare exactly and nothing is rounded.
   2. The comparison, on the directory live_candles_dev.py fills (OUT): the catalog against the document; every screen's
      answer; set relations over the whole universe (Detected = Detected within 3 with bars_ago 0; a looser minimum
      range or the trend test off never loses a stock; a mixed screen is the intersection of its parts, with the same
      candle cells); and, for each sample stock, the pattern recomputed on the Terminal's own price bars (the price pack
      of POST /api/terminal/v1/bundle) against the Screener's tickers, event dates, bars_ago, last event dates and, on a
      stock with a price break, the PRICE_BREAK_IN_LOOKBACK cell remark.
   Writes OUT/parity.jsonl (one line per sample stock and screen) and OUT/report.json; prints a summary line.
   Exit: 0 everything matches; 1 a mismatch, or a screen refused other than by a published limit; 2 the publication
   changed during the check (run it again); 3 incomplete (a sample stock without bars, a failed request); 4 every
   answer matched but a published limit (LIMIT_EXCEEDED: compute_budget, max_response_bytes) refused some screen.
   Usage: node verification/screener/live_candles_compute.mjs OUT
   Plain JavaScript (no TypeScript, no dependency), so it runs with any Node 18+. */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

/* ==== 1. the definitions (P6_CANDLES.md section 5) ================================================================ */

/** IDX price fractions: [from, below, tick] (Rp 1 below 200, 2 below 500, 5 below 2,000, 10 below 5,000, 25 from 5,000). */
export const TICK_BANDS = [[0, 200, 1], [200, 500, 2], [500, 2000, 5], [2000, 5000, 10], [5000, Infinity, 25]];
/** Price ticks between two prices, counted band by band (each part of the span in its own band's tick). */
export function ticksBetween(a, b) {
  const lo = Math.min(a, b), hi = Math.max(a, b);
  let n = 0;
  for (const [from, below, tick] of TICK_BANDS) {
    const x = Math.max(lo, from), y = Math.min(hi, below);
    if (y > x) n += (y - x) / tick;
  }
  return n;
}

/** Parameters every pattern shares (and the long-candle pair where a long candle is needed), with the document's
    defaults and ranges. */
export const SHARED_PARAMS = {
  trend_length: { type: 'integer', default: 10, min: 2, max: 100 },
  min_range_ticks: { type: 'integer', default: 3, min: 1, max: 50 },
  body_avg_length: { type: 'integer', default: 10, min: 1, max: 100 },
  long_body: { type: 'number', default: 1, min: 0, max: 10 },
};
const TREND_ALL = ['average', 'change', 'none'], TREND_REQUIRED = ['average', 'change'];

// one candle's measures
function candle(B, i) {
  const o = B.O[i], h = B.H[i], l = B.L[i], c = B.C[i];
  return { o, h, l, c, range: h - l, body: Math.abs(c - o), upper: h - Math.max(o, c), lower: Math.min(o, c) - l,
    top: Math.max(o, c), bottom: Math.min(o, c), white: c > o, black: c < o };
}
// shared shapes of the single-candle pairs
const hammerShape = (a, P) => 100 * a.body <= P.body_max_pct * a.range && a.lower >= P.shadow_ratio * a.body && 100 * a.upper <= P.short_shadow_pct * a.range;
const invertedShape = (a, P) => 100 * a.body <= P.body_max_pct * a.range && a.upper >= P.shadow_ratio * a.body && 100 * a.lower <= P.short_shadow_pct * a.range;
const HAMMER = { body_max_pct: 30, shadow_ratio: 2, short_shadow_pct: 10 };
const DOJI = { doji_body_pct: 10, short_shadow_pct: 10 };
const STAR = { star_body_pct: 30, star_overlap_pct: 10, penetration_pct: 50 };
const ARMY = { body_min_pct: 50, short_shadow_pct: 25 };

/** The 20 patterns. bars: candles (1 the oldest, the last the signal bar); trend: the options and default of the prior
    trend; long: the pattern takes body_avg_length and long_body; own: its own parameters with their defaults; ranges:
    the ranges the document states for them; test(candles, P, isLong): the table's rules. */
export const PATTERNS = {
  hammer: { name: 'Hammer', side: 'bullish', bars: 1, trend: TREND_REQUIRED, long: false, own: HAMMER, test: ([a], P) => hammerShape(a, P) },
  hanging_man: { name: 'Hanging Man', side: 'bearish', bars: 1, trend: TREND_REQUIRED, long: false, own: HAMMER, test: ([a], P) => hammerShape(a, P) },
  inverted_hammer: { name: 'Inverted Hammer', side: 'bullish', bars: 1, trend: TREND_REQUIRED, long: false, own: HAMMER, test: ([a], P) => invertedShape(a, P) },
  shooting_star: { name: 'Shooting Star', side: 'bearish', bars: 1, trend: TREND_REQUIRED, long: false, own: HAMMER, test: ([a], P) => invertedShape(a, P) },
  dragonfly_doji: { name: 'Dragonfly Doji', side: 'bullish', bars: 1, trend: TREND_ALL, long: false, own: DOJI,
    test: ([a], P) => 100 * a.body <= P.doji_body_pct * a.range && 100 * a.upper <= P.short_shadow_pct * a.range },
  gravestone_doji: { name: 'Gravestone Doji', side: 'bearish', bars: 1, trend: TREND_ALL, long: false, own: DOJI,
    test: ([a], P) => 100 * a.body <= P.doji_body_pct * a.range && 100 * a.lower <= P.short_shadow_pct * a.range },
  bullish_marubozu: { name: 'Bullish Marubozu', side: 'bullish', bars: 1, trend: TREND_ALL, trendDefault: 'none', long: true, own: { body_min_pct: 90 },
    test: ([a], P, isLong) => a.white && 100 * a.body >= P.body_min_pct * a.range && isLong(a) },
  bearish_marubozu: { name: 'Bearish Marubozu', side: 'bearish', bars: 1, trend: TREND_ALL, trendDefault: 'none', long: true, own: { body_min_pct: 90 },
    test: ([a], P, isLong) => a.black && 100 * a.body >= P.body_min_pct * a.range && isLong(a) },
  bullish_engulfing: { name: 'Bullish Engulfing', side: 'bullish', bars: 2, trend: TREND_ALL, long: false, own: {},
    test: ([a, b]) => a.black && b.white && b.o <= a.c && b.c >= a.o && b.body > a.body },
  bearish_engulfing: { name: 'Bearish Engulfing', side: 'bearish', bars: 2, trend: TREND_ALL, long: false, own: {},
    test: ([a, b]) => a.white && b.black && b.o >= a.c && b.c <= a.o && b.body > a.body },
  bullish_harami: { name: 'Bullish Harami', side: 'bullish', bars: 2, trend: TREND_ALL, long: true, own: { inside_max_pct: 50 },
    test: ([a, b], P, isLong) => a.black && isLong(a) && b.top <= a.o && b.bottom >= a.c && 100 * b.body <= P.inside_max_pct * a.body },
  bearish_harami: { name: 'Bearish Harami', side: 'bearish', bars: 2, trend: TREND_ALL, long: true, own: { inside_max_pct: 50 },
    test: ([a, b], P, isLong) => a.white && isLong(a) && b.top <= a.c && b.bottom >= a.o && 100 * b.body <= P.inside_max_pct * a.body },
  piercing_line: { name: 'Piercing Line', side: 'bullish', bars: 2, trend: TREND_ALL, long: true, own: { open_beyond: 'close', penetration_pct: 50 }, options: { open_beyond: ['close', 'range'] },
    test: ([a, b], P, isLong) => a.black && isLong(a) && b.white && (P.open_beyond === 'range' ? b.o < a.l : b.o < a.c)
      && 100 * (b.c - a.c) >= P.penetration_pct * a.body && b.c < a.o },
  dark_cloud_cover: { name: 'Dark Cloud Cover', side: 'bearish', bars: 2, trend: TREND_ALL, long: true, own: { open_beyond: 'close', penetration_pct: 50 }, options: { open_beyond: ['close', 'range'] },
    test: ([a, b], P, isLong) => a.white && isLong(a) && b.black && (P.open_beyond === 'range' ? b.o > a.h : b.o > a.c)
      && 100 * (a.c - b.c) >= P.penetration_pct * a.body && b.c > a.o },
  tweezer_bottom: { name: 'Tweezer Bottom', side: 'bullish', bars: 2, trend: TREND_ALL, long: false, own: { tolerance_ticks: 1 },
    test: ([a, b], P) => a.black && b.white && ticksBetween(a.l, b.l) <= P.tolerance_ticks },
  tweezer_top: { name: 'Tweezer Top', side: 'bearish', bars: 2, trend: TREND_ALL, long: false, own: { tolerance_ticks: 1 },
    test: ([a, b], P) => a.white && b.black && ticksBetween(a.h, b.h) <= P.tolerance_ticks },
  morning_star: { name: 'Morning Star', side: 'bullish', bars: 3, trend: TREND_ALL, long: true, own: STAR, ranges: { star_overlap_pct: [-50, 50] },
    test: ([a, b, c], P, isLong) => a.black && isLong(a) && 100 * b.body <= P.star_body_pct * a.body && 100 * (b.top - a.c) <= P.star_overlap_pct * a.body
      && c.white && 100 * (c.c - a.c) >= P.penetration_pct * a.body },
  evening_star: { name: 'Evening Star', side: 'bearish', bars: 3, trend: TREND_ALL, long: true, own: STAR, ranges: { star_overlap_pct: [-50, 50] },
    test: ([a, b, c], P, isLong) => a.white && isLong(a) && 100 * b.body <= P.star_body_pct * a.body && 100 * (a.c - b.bottom) <= P.star_overlap_pct * a.body
      && c.black && 100 * (a.c - c.c) >= P.penetration_pct * a.body },
  three_white_soldiers: { name: 'Three White Soldiers', side: 'bullish', bars: 3, trend: TREND_ALL, long: true, own: ARMY,
    test: ([a, b, c], P, isLong) => [a, b, c].every(x => x.white && 100 * x.body >= P.body_min_pct * x.range && 100 * x.upper <= P.short_shadow_pct * x.range && isLong(x))
      && b.o >= a.o && b.o <= a.c && c.o >= b.o && c.o <= b.c && b.c > a.c && c.c > b.c },
  three_black_crows: { name: 'Three Black Crows', side: 'bearish', bars: 3, trend: TREND_ALL, long: true, own: ARMY,
    test: ([a, b, c], P, isLong) => [a, b, c].every(x => x.black && 100 * x.body >= P.body_min_pct * x.range && 100 * x.lower <= P.short_shadow_pct * x.range && isLong(x))
      && b.o <= a.o && b.o >= a.c && c.o <= b.o && c.o >= b.c && b.c < a.c && c.c < b.c },
};
export const PATTERN_IDS = Object.keys(PATTERNS);

/** The parameter keys and defaults of a pattern, by the document. */
export function defaultsOf(id) {
  const p = PATTERNS[id];
  if (!p) throw new Error(`not a pattern of P6_CANDLES.md: ${id}`);
  // the trend test is off by default where a pattern offers none (user decision 2026-11-08); the Hammer family's is average
  const out = { trend: p.trendDefault ?? (p.trend.includes('none') ? 'none' : 'average'), trend_length: 10, min_range_ticks: 3 };
  if (p.long) Object.assign(out, { body_avg_length: 10, long_body: 1 });
  return Object.assign(out, p.own);
}
/** The parameters of a run: the document's defaults, then the given ones (an unknown key is an error here, so a
    mistyped definition of the check cannot pass silently). */
export function resolveParams(id, given = {}) {
  const P = defaultsOf(id);
  for (const [k, v] of Object.entries(given || {})) {
    if (!(k in P)) throw new Error(`${id} takes no parameter ${k}`);
    P[k] = v;
  }
  if (!PATTERNS[id].trend.includes(P.trend)) throw new Error(`${id}: trend ${P.trend} is not offered`);
  return P;
}

const num = x => typeof x === 'number' && Number.isFinite(x) ? x : NaN;
/** The pattern's 0/1 signal on bars {O, H, L, C, V} (arrays by bar; null or a non-number is missing): 1 on bar i when
    the pattern's last candle is bar i, every candle of it traded (open, high, low, close and volume above 0, high and
    low around the open and the close) and spans at least min_range_ticks ticks, the trend on the session before
    candle 1 holds (unless none), and the rules hold. Bar 0 is never 1. */
export function detect(bars, id, given = {}) {
  const spec = PATTERNS[id], P = resolveParams(id, given), k = spec.bars;
  const B = { O: Array.from(bars.O, num), H: Array.from(bars.H, num), L: Array.from(bars.L, num), C: Array.from(bars.C, num), V: Array.from(bars.V, num) };
  const n = B.C.length, out = new Uint8Array(n), bullish = spec.side === 'bullish', N = P.trend_length;
  const traded = i => {
    const o = B.O[i], h = B.H[i], l = B.L[i], c = B.C[i], v = B.V[i];
    if (!(o > 0 && h > 0 && l > 0 && c > 0 && v > 0)) return false;           // NaN (missing) is never above 0
    if (h < o || h < c || l > o || l > c) return false;
    return ticksBetween(l, h) >= P.min_range_ticks;
  };
  // the trend on session j (the one before candle 1): its close against its own trend_length-session average, or
  // against the close trend_length sessions earlier; below for a bullish pattern, above for a bearish one
  const trendHolds = j => {
    if (P.trend === 'none') return true;
    if (P.trend === 'change') {
      if (j - N < 0) return false;
      return bullish ? B.C[j] < B.C[j - N] : B.C[j] > B.C[j - N];
    }
    if (j - N + 1 < 0) return false;
    let sum = 0;
    for (let t = j - N + 1; t <= j; t++) sum += B.C[t];
    return bullish ? N * B.C[j] < sum : N * B.C[j] > sum;
  };
  // the average body of the body_avg_length sessions before candle 1 (NaN when there are not that many: no long candle)
  const averageBody = first => {
    const M = P.body_avg_length;
    if (first - M < 0) return NaN;
    let s = 0;
    for (let t = first - M; t < first; t++) s += Math.abs(B.C[t] - B.O[t]);
    return s / M;
  };
  for (let i = Math.max(1, k - 1); i < n; i++) {
    const first = i - k + 1;
    let ok = true;
    for (let t = first; t <= i && ok; t++) ok = traded(t);
    if (!ok || !trendHolds(first - 1)) continue;
    const cs = [];
    for (let t = first; t <= i; t++) cs.push(candle(B, t));
    const avg = spec.long ? averageBody(first) : NaN;
    out[i] = spec.test(cs, P, x => x.body >= P.long_body * avg) ? 1 : 0;
  }
  return out;
}

/** The bars a signal on one bar reads: its candles and, before them, the trend's sessions (average: trend_length
    closes ending on the session before candle 1; change: that session and the one trend_length earlier) or the average
    body's body_avg_length sessions, whichever reach further; at least 2, since a signal is never on bar 0 (the
    Screener's stated window, candles.ts candleLookback). */
export function lookback(id, given = {}) {
  const spec = PATTERNS[id], P = resolveParams(id, given);
  const trend = P.trend === 'average' ? P.trend_length : P.trend === 'change' ? P.trend_length + 1 : 0;
  return Math.max(2, spec.bars + Math.max(trend, spec.long ? P.body_avg_length : 0));
}
/** The cell remark of a row with price breaks (P4.1 A, contract.ts CellRemark): PRICE_BREAK_IN_LOOKBACK when an
    ex-date's first bar d lies inside the bars the test reads (the pattern's lookback and, for "within N", the N - 1
    sessions before), i.e. start < d <= at; else null. */
export function priceBreakRemark(dates, at, start, exDates) {
  for (const ex of exDates) {
    const d = dates.findIndex(x => x >= ex);
    if (d >= 0 && d <= at && start < d) return 'PRICE_BREAK_IN_LOOKBACK';
  }
  return null;
}

/** The latest bar in [at - within + 1, at] with the signal, or null (the Screener's "within N sessions"). */
export function latestWithin(sig, at, within) {
  for (let i = at; i > at - within && i >= 0; i--) if (sig[i]) return i;
  return null;
}

/* ==== 2. the Terminal's bars ======================================================================================= */

/** Price documents of the Terminal (a price pack, or yearly files) -> bars by date, oldest first, with the row rule the
    Screener's decoder states (snapshot.ts header): a row without four finite prices is left out; a missing volume stays
    missing. dates must rise. */
export function barsOfDocs(docs) {
  const problems = [], parts = [...docs].filter(d => Array.isArray(d?.d) && d.d.length).sort((x, y) => (x.d[0] < y.d[0] ? -1 : x.d[0] > y.d[0] ? 1 : 0));
  const out = { dates: [], O: [], H: [], L: [], C: [], V: [], dropped: 0 };
  let prev = '';
  for (const doc of parts) {
    if (!['price', 'price-pack'].includes(doc.dataset)) problems.push(`a ${doc.dataset} document among the price files`);
    for (let k = 0; k < doc.d.length; k++) {
      const d = doc.d[k];
      if (prev && !(d > prev)) { problems.push(`date ${d} after ${prev}`); continue }
      prev = d;
      const p = [doc.o[k], doc.h[k], doc.l[k], doc.c[k]];
      if (!p.every(x => typeof x === 'number' && Number.isFinite(x))) { out.dropped++; continue }
      out.dates.push(d); out.O.push(p[0]); out.H.push(p[1]); out.L.push(p[2]); out.C.push(p[3]);
      out.V.push(typeof doc.v[k] === 'number' && Number.isFinite(doc.v[k]) ? doc.v[k] : null);
    }
  }
  return { bars: out, problems };
}
/** The ticker's evaluation bar: its last bar on or before E. */
export function evaluationBar(dates, E) {
  let j = -1;
  for (let i = 0; i < dates.length; i++) if (dates[i] <= E) j = i; else break;
  return j;
}

/* ==== 3. the comparison ============================================================================================ */

const readJson = (dir, name, fallback) => { const f = path.join(dir, name); return fs.existsSync(f) ? JSON.parse(fs.readFileSync(f, 'utf8')) : fallback };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** The catalog's candlestick entries against the document: the 20 ids, AVAILABLE, kind pattern, tested on the bar or
    within N (default within 3), every parameter with its default (and the ranges the document states). */
export function checkCatalog(catalog) {
  const problems = [];
  if (!catalog || catalog.status !== 200) return { problems: [`catalog answered ${catalog?.status}`], entries: 0 };
  const entries = (catalog.metrics || []).filter(m => m.group === 'Candlestick');
  const ids = entries.map(m => m.id).sort(), want = [...PATTERN_IDS].sort();
  if (!same(ids, want)) problems.push(`the Candlestick group lists ${ids.join(',')}; the document has ${want.join(',')}`);
  for (const m of entries) {
    const p = PATTERNS[m.id], w = `catalog ${m.id}`;
    if (!p) continue;
    if (m.kind !== 'pattern') problems.push(`${w}: kind ${m.kind}, not pattern`);
    if (m.availability !== 'AVAILABLE') problems.push(`${w}: ${m.availability} (${m.reason})`);
    if (!same([...(m.tests || [])].sort(), ['event', 'state'])) problems.push(`${w}: tests ${JSON.stringify(m.tests)}`);
    if (!same(m.default_test, { test: 'event', within: 3 })) problems.push(`${w}: default test ${JSON.stringify(m.default_test)}, the document: event within 3`);
    if (m.label !== undefined && m.label !== p.name) problems.push(`${w}: label ${m.label}, the document: ${p.name}`);
    const D = defaultsOf(m.id), keys = (m.params || []).map(q => q.key);
    if (!same([...keys].sort(), Object.keys(D).sort())) problems.push(`${w}: parameters ${keys.join(',')}; the document: ${Object.keys(D).join(',')}`);
    for (const q of m.params || []) {
      if (!(q.key in D)) continue;
      if (!same(q.default, D[q.key])) problems.push(`${w}.${q.key}: default ${JSON.stringify(q.default)}, the document: ${JSON.stringify(D[q.key])}`);
      if (q.key === 'trend' && !same(q.options, p.trend)) problems.push(`${w}.trend: options ${JSON.stringify(q.options)}, the document: ${JSON.stringify(p.trend)}`);
      if (p.options?.[q.key] && !same(q.options, p.options[q.key])) problems.push(`${w}.${q.key}: options ${JSON.stringify(q.options)}`);
      const r = SHARED_PARAMS[q.key] ? [SHARED_PARAMS[q.key].min, SHARED_PARAMS[q.key].max] : p.ranges?.[q.key];
      if (r && !same([q.min, q.max], r)) problems.push(`${w}.${q.key}: range ${q.min}..${q.max}, the document: ${r[0]}..${r[1]}`);
      if (SHARED_PARAMS[q.key] && (SHARED_PARAMS[q.key].type === 'integer') !== !!q.integer) problems.push(`${w}.${q.key}: integer ${q.integer}`);
    }
  }
  return { problems, entries: entries.length };
}

/** The candle cell of a screen for a ticker: {pass, cell} (no row: the condition did not pass, for a one-condition
    screen and for logic all with two conditions, whose rows are the matches and the near ones). */
function cellOf(screen, ticker, cid) {
  const row = screen.byTicker.get(ticker);
  if (!row) return { pass: false, cell: null, row: null };
  const cell = (row.cells || []).find(c => c.id === cid) || null;
  return { pass: cell?.status === 'pass', cell, row };
}

export function compare(dir) {
  const fetch = readJson(dir, 'fetch.json', { problems: [] });
  const before = readJson(dir, 'catalog_before.json', null), after = readJson(dir, 'catalog_after.json', null);
  const universe = readJson(dir, 'universe.json', { rows: [] });
  const screens = readJson(dir, 'screens.json', []);
  const sample = readJson(dir, 'sample.json', []);
  const report = { checked_at: new Date().toISOString(), publication: {}, catalog: {}, screens: {}, relations: {}, params: {}, sample: [], parity: {}, coverage: {}, fetch_problems: fetch.problems || [] };
  const failures = [], incomplete = [...(fetch.problems || [])], changed = [];

  // ---- publication: one version from the first catalog read to the last ----
  const pv = before?.versions?.price_data, E = before?.data?.evaluation_date;
  report.publication = { versions: before?.versions ?? null, data: before?.data ?? null, versions_after: after?.versions ?? null, data_after: after?.data ?? null };
  if (!before || before.status !== 200) incomplete.push('the catalog was not read');
  if (after && after.status === 200 && (after.versions?.price_data !== pv || after.data?.published_at !== before?.data?.published_at)) changed.push(`the catalog moved from ${before?.data?.published_at} to ${after?.data?.published_at}`);
  if (!after) incomplete.push('the catalog was not read again at the end');

  // ---- catalog ----
  const cat = checkCatalog(before);
  report.catalog = { entries: cat.entries, problems: cat.problems, limits: (before?.limits || []).filter(l => ['within_max', 'max_conditions', 'compute_budget', 'owner_cpu_budget', 'max_response_bytes'].includes(l.name)) };
  failures.push(...cat.problems);
  const withinMax = (before?.limits || []).find(l => l.name === 'within_max')?.value ?? 130;

  // ---- screens ----
  const byName = new Map();
  let ok = 0;
  const refused = [];
  for (const s of screens) {
    s.byTicker = new Map((s.rows || []).map(r => [r.ticker, r]));
    byName.set(s.name, s);
    if (s.status === 200) {
      ok++;
      if (s.versions?.price_data !== pv) changed.push(`screen ${s.name} answered at price_data ${s.versions?.price_data}`);
      if (s.data?.evaluation_date !== E) changed.push(`screen ${s.name} evaluated on ${s.data?.evaluation_date}, the catalog on ${E}`);
    } else if (s.status === 409 && s.error?.code === 'DATA_VERSION_CHANGED') changed.push(`screen ${s.name}: ${s.error.code}`);
    // not the Screener's answer to the definition: the service, the network, the owner's compute per minute after the
    // retries, or a flow screen while the broker window is still loading (the catalog's availability)
    else if ([0, 429, 502, 503, 504].includes(s.status) || (s.status === 409 && s.error?.code === 'BUSY') || (s.flow && s.error?.code === 'METRIC_UNAVAILABLE')
      || s.error?.details?.limit === 'owner_cpu_budget') incomplete.push(`screen ${s.name} answered ${s.status} ${s.error?.code ?? ''}`);
    else refused.push({ name: s.name, status: s.status, code: s.error?.code, field: s.error?.field, message: s.error?.message, details: s.error?.details });
  }
  // a published limit (compute_budget, max_response_bytes, ...) refused the screen: not a wrong answer, reported apart
  // (verdict LIMIT_REFUSED, exit 4, when nothing else failed) with the limit, allowed and needed
  const limitRefused = refused.filter(r => r.code === 'LIMIT_EXCEEDED');
  for (const r of refused) if (r.code !== 'LIMIT_EXCEEDED') failures.push(`screen ${r.name} refused: ${r.status} ${r.code} ${r.field ?? ''} ${r.message ?? ''}`.trim());
  const perPattern = {};
  for (const s of screens) if (s.pattern) (perPattern[s.pattern] ??= {})[s.variant] = s.status === 200 ? s.match_count : `refused ${s.status}`;
  report.screens = { count: screens.length, answered: ok, refused, match_counts: perPattern,
    timings_ms: screens.filter(s => s.status === 200).map(s => s.timings_ms?.total ?? null).filter(x => x !== null).sort((a, b) => a - b).filter((_, i, a) => i === 0 || i === a.length - 1 || i === Math.floor(a.length / 2)),
    round_trip_ms: (() => { const ms = screens.map(s => s.ms).filter(x => typeof x === 'number').sort((a, b) => a - b); return ms.length ? { min: ms[0], median: ms[Math.floor(ms.length / 2)], max: ms[ms.length - 1] } : null })() };

  // ---- parameters the Screener resolved, against the document ----
  const paramProblems = [];
  let paramChecked = 0;
  for (const s of screens) {
    if (s.status !== 200 || !s.pattern) continue;
    const c = (s.conditions || []).find(x => x.id === s.candle_id);
    if (!c) { paramProblems.push(`${s.name}: no condition summary ${s.candle_id}`); continue }
    paramChecked++;
    const mine = resolveParams(s.pattern, s.params || {});
    if (!same(Object.fromEntries(Object.entries(c.params_resolved || {}).sort()), Object.fromEntries(Object.entries(mine).sort())))
      paramProblems.push(`${s.name}: the Screener resolved ${JSON.stringify(c.params_resolved)}, the document gives ${JSON.stringify(mine)}`);
    const isDefault = !s.params || !Object.keys(s.params).length || same(resolveParams(s.pattern, s.params), defaultsOf(s.pattern));
    if (c.is_default !== isDefault) paramProblems.push(`${s.name}: is_default ${c.is_default}, expected ${isDefault}`);
    if (c.eval_date_basis !== 'ticker_last_bar') paramProblems.push(`${s.name}: eval_date_basis ${c.eval_date_basis}`);
  }
  report.params = { checked: paramChecked, problems: paramProblems };
  failures.push(...paramProblems);

  // ---- relations over the whole universe ----
  const rel = [];
  let relChecked = 0;
  const setOf = s => new Set([...s.byTicker.values()].filter(r => r.status === 'match').map(r => r.ticker));
  const okScreen = name => { const s = byName.get(name); return s && s.status === 200 ? s : null };
  for (const id of PATTERN_IDS) {
    const st = okScreen(`${id}:default_state`), w3 = okScreen(`${id}:default_w3`);
    if (st && w3) {
      relChecked++;
      const zero = new Set([...w3.byTicker.values()].filter(r => r.cells?.[0]?.status === 'pass' && r.cells[0].bars_ago === 0).map(r => r.ticker));
      const a = setOf(st);
      const only1 = [...a].filter(t => !zero.has(t)), only2 = [...zero].filter(t => !a.has(t));
      if (only1.length || only2.length) rel.push(`${id}: Detected has ${only1.join(',') || 'none'} beyond "within 3, 0 sessions ago", which has ${only2.join(',') || 'none'} beyond it`);
    }
    // a looser setting never loses a stock: minimum range 3 -> 2 -> 1; the trend test off against on (the default is off
    // where the pattern offers none: then the "alternative" is the tighter one)
    const alt = okScreen(`${id}:trend_alt_w3`), dflt = defaultsOf(id).trend;
    const trendPair = !alt ? null : alt.params?.trend === 'none' ? ['default_w3', 'trend_alt_w3'] : dflt === 'none' ? ['trend_alt_w3', 'default_w3'] : null;
    for (const [tight, loose] of [['default_w3', 'tick2_w3'], ['tick2_w3', 'tick1_w3'], ...(trendPair ? [trendPair] : [])]) {
      const a = okScreen(`${id}:${tight}`), b = okScreen(`${id}:${loose}`);
      if (!a || !b) continue;
      relChecked++;
      const lost = [...setOf(a)].filter(t => !setOf(b).has(t));
      if (lost.length) rel.push(`${id}: ${loose} lost ${lost.slice(0, 10).join(',')} that ${tight} has`);
    }
  }
  for (const s of screens.filter(x => x.mix && x.status === 200)) {
    const alone = okScreen(s.mix.candle_screen), other = okScreen(s.mix.other_screen);
    if (!alone || !other) { incomplete.push(`${s.name}: its parts were not answered`); continue }
    relChecked++;
    const A = setOf(alone), O = setOf(other), M = setOf(s);
    const want = new Set([...A].filter(t => O.has(t)));
    const extra = [...M].filter(t => !want.has(t)), missing = [...want].filter(t => !M.has(t));
    if (extra.length || missing.length) rel.push(`${s.name}: matches beyond the intersection ${extra.join(',') || 'none'}, missing ${missing.join(',') || 'none'}`);
    for (const r of s.byTicker.values()) {
      const mine = (r.cells || []).find(c => c.id === s.candle_id), ref = alone.byTicker.get(r.ticker)?.cells?.[0] ?? null;
      const p1 = mine?.status === 'pass', p2 = ref?.status === 'pass';
      if (p1 !== p2 || (p1 && (mine.event_date !== ref.event_date || mine.bars_ago !== ref.bars_ago))) rel.push(`${s.name} ${r.ticker}: candle cell ${JSON.stringify(mine)} differs from the candle screen's ${JSON.stringify(ref)}`);
      const oc = (r.cells || []).find(c => c.id !== s.candle_id);
      if ((oc?.status === 'pass') !== O.has(r.ticker)) rel.push(`${s.name} ${r.ticker}: the other cell ${oc?.status} differs from its screen`);
    }
    const oc = (s.conditions || []).find(c => c.id !== s.candle_id);
    if (s.mix.flow && oc?.eval_date_basis !== 'flow_date') rel.push(`${s.name}: the flow condition's eval_date_basis is ${oc?.eval_date_basis}`);
  }
  report.relations = { checked: relChecked, problems: rel };
  failures.push(...rel);

  // ---- each sample stock: recomputed on the Terminal's bars ----
  const urow = new Map((universe.rows || []).map(r => [r.ticker, r]));
  const lines = [], byPattern = {};
  let compared = 0, equal = 0;
  const mismatches = [];
  for (const smp of sample) {
    const t = smp.ticker, file = path.join(dir, 'bars', `${t}.json`), info = { ticker: t, reasons: smp.reasons };
    report.sample.push(info);
    if (!fs.existsSync(file)) { incomplete.push(`${t}: no bars`); info.problem = 'no bars'; continue }
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (raw.status !== 200) { incomplete.push(`${t}: bundle answered ${raw.status}`); info.problem = `bundle ${raw.status}`; continue }
    const { bars, problems } = barsOfDocs(raw.docs || []);
    const u = urow.get(t), at = evaluationBar(bars.dates, E);
    Object.assign(info, { bars: bars.dates.length, dropped_rows: bars.dropped, first: bars.dates[0], last: bars.dates[at],
      one_price_days: bars.dates.filter((_, i) => bars.O[i] === bars.H[i] && bars.H[i] === bars.L[i] && bars.L[i] === bars.C[i]).length,
      zero_volume_days: bars.V.filter(v => !(v > 0)).length, last_close: bars.C[at], remarks: u?.remarks ?? null, stale: u?.stale ?? null,
      file_problems: [...problems, ...(raw.file_problems || [])] });
    if (problems.length || (raw.file_problems || []).length) { failures.push(`${t}: price files ${[...problems, ...(raw.file_problems || [])].join('; ')}`); continue }
    if (!u) { failures.push(`${t}: not in the Screener's universe`); continue }
    if (bars.dates.length > at + 1) changed.push(`${t}: the Terminal has bars after ${E} (${bars.dates[bars.dates.length - 1]})`);
    if (u.last_bar !== bars.dates[at] || u.bars !== at + 1 || u.first_bar !== bars.dates[0]) {
      failures.push(`${t}: the Screener holds ${u.bars} bars ${u.first_bar}..${u.last_bar}, the Terminal ${at + 1} bars ${bars.dates[0]}..${bars.dates[at]}`); continue
    }
    const sigs = new Map(), exDates = (u.remarks || []).filter(x => x?.code === 'PRICE_BREAK').map(x => x.ex_date);
    info.price_break_cells = 0;
    for (const s of screens) {
      if (s.status !== 200 || !s.pattern) continue;
      const key = `${s.pattern}|${JSON.stringify(s.params || {})}`;
      if (!sigs.has(key)) sigs.set(key, detect(bars, s.pattern, s.params || {}));
      const sig = sigs.get(key);
      const scr = cellOf(s, t, s.candle_id);
      let mine;
      const start = at - lookback(s.pattern, s.params || {}) + 1 - (s.kind === 'event' ? s.within - 1 : 0);
      const remark = priceBreakRemark(bars.dates, at, start, exDates);
      if (s.kind === 'state') mine = { pass: !!sig[at], eval_date: bars.dates[at], remark };
      else {
        const j = latestWithin(sig, at, s.within), last = latestWithin(sig, at, withinMax);
        mine = { pass: j !== null, eval_date: bars.dates[at], event_date: j === null ? null : bars.dates[j], bars_ago: j === null ? null : at - j, last_event_date: last === null ? null : bars.dates[last], remark };
      }
      const theirs = { pass: scr.pass };
      if (scr.cell) {
        theirs.eval_date = scr.cell.eval_date;
        if (s.kind === 'event') Object.assign(theirs, { event_date: scr.cell.event_date ?? null, bars_ago: scr.cell.bars_ago ?? null, last_event_date: scr.cell.last_event_date ?? null });
        theirs.remark = scr.cell.remark ?? null;
      }
      // a cell the Screener shows must agree field by field; a stock it does not list must have no pattern here
      let agree = theirs.pass === mine.pass;
      if (agree && scr.cell) for (const k of Object.keys(theirs)) if (k !== 'pass' && theirs[k] !== mine[k]) agree = false;
      compared++; if (agree) equal++;
      const bp = (byPattern[s.pattern] ??= { compared: 0, equal: 0, positives: 0 });
      bp.compared++; if (agree) bp.equal++; if (agree && mine.pass) bp.positives++;
      if (theirs.remark) info.price_break_cells++;
      const line = { t, screen: s.name, pattern: s.pattern, variant: s.variant, kind: s.kind, within: s.within ?? null, params: s.params || {}, screener: theirs, terminal: mine, same: agree };
      lines.push(line);
      if (!agree) mismatches.push(line);
    }
  }
  fs.writeFileSync(path.join(dir, 'parity.jsonl'), lines.map(l => JSON.stringify(l)).join('\n') + (lines.length ? '\n' : ''));
  report.parity = { compared, equal, mismatches: mismatches.length, first_mismatches: mismatches.slice(0, 20), by_pattern: byPattern };
  report.coverage = { patterns_without_a_positive_in_the_sample: PATTERN_IDS.filter(id => !(byPattern[id]?.positives > 0)) };
  for (const m of mismatches.slice(0, 50)) failures.push(`${m.t} ${m.screen}: Screener ${JSON.stringify(m.screener)}, Terminal bars ${JSON.stringify(m.terminal)}`);
  if (!compared) incomplete.push('nothing was compared');

  const verdict = changed.length ? 'PUBLICATION_CHANGED' : incomplete.length ? 'INCOMPLETE' : failures.length ? 'MISMATCH' : limitRefused.length ? 'LIMIT_REFUSED' : 'PASS';
  const code = { PASS: 0, MISMATCH: 1, PUBLICATION_CHANGED: 2, INCOMPLETE: 3, LIMIT_REFUSED: 4 }[verdict];
  Object.assign(report, { verdict, exit_code: code, failures: failures.slice(0, 200), failure_count: failures.length, incomplete, publication_changes: changed,
    limit_refused: limitRefused.map(r => ({ name: r.name, limit: r.details?.limit ?? null, allowed: r.details?.allowed ?? null, needed: r.details?.needed ?? null, costliest: r.details?.costliest ?? null })) });
  fs.writeFileSync(path.join(dir, 'report.json'), JSON.stringify(report, null, 1));
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2];
  if (!dir) { console.error('usage: node live_candles_compute.mjs OUT'); process.exit(64) }
  const r = compare(dir);
  console.log(JSON.stringify({ verdict: r.verdict, screens: `${r.screens.answered}/${r.screens.count}`, catalog_entries: r.catalog.entries, relations: r.relations.checked,
    relation_problems: r.relations.problems.length, compared: r.parity.compared, equal: r.parity.equal, sample: r.sample.length,
    uncovered: r.coverage.patterns_without_a_positive_in_the_sample, failures: r.failure_count, limit_refused: r.limit_refused.length, incomplete: r.incomplete.length, changes: r.publication_changes.length }));
  process.exit(r.exit_code);
}
