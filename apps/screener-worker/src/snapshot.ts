/* The snapshot: one rack publication in memory (report TARGET ARCHITECTURE 6.5, 6.7; MULTI-USER SCALE AND COST 6d.2,
   6d.4). Built once per publication on the builder thread, shared by every compute thread, never written anywhere.

   Built from (refresh.ts hands the decoded files over):
   - the `price` xsection file: columns t,d,o,h,l,c,v ordered by ticker then date and `tickers: [{t, pack_sha256, first,
     last, rows}]` in file order (apps/terminal-publisher/publisher.py xsection_price_doc). Each ticker's slice becomes a
     document of the pack's shape and goes through the backtest core's priceSeries, so the Terminal's and the
     Backtest's row rules apply unchanged (a row without four finite prices is dropped); the slice must hold exactly its
     entry's rows, first and last dates, and the entries must cover the columns in ticker order (else DATA_INTEGRITY);
   - the `actions` xsection file: columns t, d, type, ratio_old, ratio_new (+ amount_per_share, currency for Phase 2);
     a superset (every action since the first price year, publisher decision 1), so the price-break rule's bounds are
     applied by universe.ts priceBreakRemarks with engine.ts ADJUSTED_HISTORY_BOUNDARY (P4);
   - the reference file ref/tickers.json.gz (name, type, sector, industry; TerminalClient.reference): every ticker of
     the price file must be in it (fixed key, ERRORS M250 class), else the refresh fails.
   Versions: price_data = datafile.dataVersion over (ticker, 'price', pack_sha256) of every ticker of the price file
   (6.5, the Backtest's inputs for price). E = state.json price_through (6.5 As-of policy).

   Memory layout (6.4 "one copy of the bars per replica"; TEST PLAN 10b.1 "typed views"): the bars of every ticker sit
   once in SharedArrayBuffer columns (O, H, L, C, V as Float64Array, V's null as NaN: priceSeries keeps a volume finite
   or null, so the encoding is lossless; T as Int32 indexes into one date table). F never runs on a typed view: a
   ticker's bars are materialized back into plain arrays equal value for value to priceSeries' (materialize), so every
   formula sees exactly what the Backtest's would (typed_views.test.ts holds the round trip and F bit for bit). The
   pre-warmed series (the 53 indicators at registry.ts startParams, 76 outputs, plus every series the presets name)
   are tails of tailLength(SCREENER_WITHIN_MAX) bars per (series, ticker) in one shared Float64Array, written by the
   pre-warm through the one series() path (metrics.ts) and installed in each thread's SeriesCache as pinned views.
   snapshot_digest = sha256 over the series keys, the tickers and every tail and its header (6.7 Auditability): two
   replicas at one publication log the same digest. */
import crypto from 'node:crypto';
import { DataError, PRICE_ACTION_TYPES, dataVersion, priceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { ADJUSTED_HISTORY_BOUNDARY } from '../../edge-bff/backtest/src/core/engine.ts';
import { byTicker } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Bars } from '../../edge-bff/terminal/src/calc/indicators.ts';
import type { DataStatus, Grouping, MetricRef, PatternRef, PriceBreakRemark, RowRemark, UniverseRow, Versions } from '../../edge-bff/screener/src/core/contract.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import type { PresetDefinition } from '../../edge-bff/screener/src/core/catalog.ts';
import { bindCondition } from '../../edge-bff/screener/src/core/condition.ts';
import { SeriesCache, resolveSeries, series, seriesKey, tickerCalc, universeAttributes } from '../../edge-bff/screener/src/core/metrics.ts';
import type { DataVersions, ResolvedSeries, Tail, TickerBars } from '../../edge-bff/screener/src/core/metrics.ts';
import type { ParamOptions } from '../../edge-bff/screener/src/core/registry.ts';
import { INDICATORS, startParams } from '../../edge-bff/screener/src/core/registry.ts';
import { resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { priceBreakRemarks } from '../../edge-bff/screener/src/core/universe.ts';
import type { ActionRow } from '../../edge-bff/screener/src/core/universe.ts';
import type { TickerReference } from '../../backtest-worker/src/terminal.ts';

export const INDEX_TICKER = 'IHSG';
export const PRICE_FILE = 'price';
export const ACTIONS_FILE = 'actions';
/** The xsection files Phase 1 reads (report 6.5 "Phase 1 files"). */
export const PHASE1_FILES = [PRICE_FILE, ACTIONS_FILE] as const;

/** One state.json xsection index entry as terminal-api serves it (bucket.py xsection_index). */
export interface IndexEntry { key: string; sha256: string; bytes: number; rows: number; as_of: string | null }
/** terminal-api GET /state (bucket.py STATE_FIELDS). */
export interface PublicationState {
  finished_at: string; price_through: string | null; broker_through: string | null; broker_behind_sessions: number | null;
  xsection: Record<string, IndexEntry> | null;
}
/** One entry of the price file's `tickers` list. */
export interface TickerEntry { t: string; pack_sha256: string; first: string; last: string; rows: number }

/* ---- the descriptor (structured-cloneable; the buffers are shared, not copied) ---------------------------------- */
export interface SnapshotDesc {
  sid: string;                       // this snapshot's identity: price_data + the actions and reference contents
  versions: Omit<Versions, 'definition_hash'>;
  data: Omit<DataStatus, 'refresh'>;
  finished_at: string;
  tailLength: number;
  tickers: string[];                 // every ticker of the price file, in file order (IHSG included)
  index: number;                     // IHSG's position in `tickers`
  offsets: Int32Array;               // ticker j's bars are [offsets[j], offsets[j + 1])
  O: Float64Array; H: Float64Array; L: Float64Array; C: Float64Array; V: Float64Array;   // V: NaN = null
  T: Int32Array;                     // index into `dates`
  dates: string[];                   // every date of any ticker, ascending
  missing: Uint8Array;               // per ticker: bit k set = BAR_FIELDS[k] has no finite non-zero value (metrics.ts missingInput at its last bar)
  rows: UniverseRow[];               // the listed stocks (GET /universe), ticker order, hidden ones included
  series: { ref: MetricRef; key: string }[];   // the pinned (pre-warmed) series, in order; key: metrics.ts seriesKey
  tails: Float64Array;               // (s * tickers + j) * tailLength: the tail's values (n - from of them)
  tailMeta: Int32Array;              // (s * tickers + j) * 4: n, from, firstValid, lastValid
  digest: string | null;             // set by the pre-warm's last step (snapshotDigest)
}
const FIELDS = ['O', 'H', 'L', 'C', 'V'] as const;

const integrity = (message: string, field = 'price') => new DataError('DATA_INTEGRITY', message, field);
const shared = <T extends Float64Array | Int32Array | Uint8Array>(Kind: { new(b: SharedArrayBuffer): T; BYTES_PER_ELEMENT: number }, n: number): T =>
  new Kind(new SharedArrayBuffer(Math.max(1, n) * Kind.BYTES_PER_ELEMENT));
const isDate = (s: unknown): s is string => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);

/* ---- groupings (the Backtest's rule; catalog.ts groupingsOf is in a backtest-worker file the image does not carry,
   so the same rule is written here over the same TickerReference and a test holds the two equal) ----------------- */
export function groupingsOf(ref: TickerReference): Grouping[] {
  const stocks = ref.tickers.filter(r => r.type === 'stock');
  return ref.groupings.map(key => {
    const counts = new Map<string, number>();
    let unclassified = 0;
    for (const r of stocks) {
      const v = r.groups[key];
      if (v === null || v === undefined) unclassified++;
      else counts.set(v, (counts.get(v) ?? 0) + 1);
    }
    return { key, values: [...counts.keys()].sort(byTicker).map(value => ({ value, tickers: counts.get(value) as number })), unclassified };
  });
}
/** A content hash of the reference file as read (rows in file order), to tell a changed reference on an unchanged index. */
export const referenceHash = (ref: TickerReference): string =>
  crypto.createHash('sha256').update(JSON.stringify([ref.groupings, ref.tickers.map(r => [r.ticker, r.name, r.type, ref.groupings.map(g => r.groups[g] ?? null)])])).digest('hex').slice(0, 16);

/* ---- decoding ---------------------------------------------------------------------------------------------------- */

/** The price file's `tickers` entries, checked: an object list in strictly increasing ticker order with a 64-hex
    pack_sha256, ISO first and last dates and whole rows >= 1 whose sum is the column length. */
export function tickerEntries(doc: Columnar): TickerEntry[] {
  const list = (doc as { tickers?: unknown }).tickers;
  if (!Array.isArray(list) || !list.length) throw integrity('The price file has no tickers list.');
  let prev = '', total = 0;
  const out = list.map((e: any, k: number): TickerEntry => {
    if (!e || typeof e.t !== 'string' || !/^[A-Z0-9]{1,12}$/.test(e.t) || typeof e.pack_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(e.pack_sha256)
      || !isDate(e.first) || !isDate(e.last) || !Number.isSafeInteger(e.rows) || e.rows < 1)
      throw integrity(`The price file's tickers entry ${k + 1} is not {t, pack_sha256, first, last, rows}.`);
    if (prev && !(e.t > prev)) throw integrity(`The price file's tickers are not in ticker order (${e.t} after ${prev}).`);
    prev = e.t; total += e.rows;
    return { t: e.t, pack_sha256: e.pack_sha256, first: e.first, last: e.last, rows: e.rows };
  });
  if (total !== (doc.t as unknown[]).length) throw integrity(`The price file's tickers list counts ${total} rows; its columns hold ${(doc.t as unknown[]).length}.`);
  return out;
}

/** The actions file's rows by ticker (universe.ts ActionRow), checked. */
export function actionsByTicker(doc: Columnar): Map<string, ActionRow[]> {
  for (const c of ['t', 'd', 'type', 'ratio_old', 'ratio_new']) if (!doc.columns.includes(c)) throw integrity(`The actions file has no column ${c}.`, 'actions');
  const [t, d, type, ro, rn] = ['t', 'd', 'type', 'ratio_old', 'ratio_new'].map(c => doc[c] as unknown[]);
  const out = new Map<string, ActionRow[]>();
  const num = (v: unknown, k: number, c: string) => {
    if (v === null) return null;
    if (typeof v !== 'number' || !Number.isFinite(v)) throw integrity(`The actions file's row ${k + 1} has ${c} ${JSON.stringify(v)}, not a number or null.`, 'actions');
    return v;
  };
  for (let k = 0; k < t.length; k++) {
    if (typeof t[k] !== 'string' || !t[k] || !isDate(d[k]) || typeof type[k] !== 'string')
      throw integrity(`The actions file's row ${k + 1} is not a ticker, an ex date and a type.`, 'actions');
    const row: ActionRow = { ticker: t[k] as string, type: type[k] as string, ex_date: d[k] as string, ratio_old: num(ro[k], k, 'ratio_old'), ratio_new: num(rn[k], k, 'ratio_new') };
    let list = out.get(row.ticker);
    if (!list) out.set(row.ticker, list = []);
    list.push(row);
  }
  return out;
}

/** The pack-shaped document of one ticker's slice (publisher.py price_pack_doc), for priceSeries. */
function sliceDoc(doc: Columnar, e: TickerEntry, at: number): Columnar {
  const cut = (c: string) => (doc[c] as unknown[]).slice(at, at + e.rows);
  const t = cut('t');
  if (!t.every(x => x === e.t)) throw integrity(`The price file's rows ${at + 1}-${at + e.rows} are not all ${e.t}, as its tickers list says.`, e.t);
  const d = cut('d');
  if (d[0] !== e.first || d[d.length - 1] !== e.last) throw integrity(`${e.t}'s rows in the price file run ${String(d[0])} to ${String(d[d.length - 1])}; its tickers entry says ${e.first} to ${e.last}.`, e.t);
  return { schema_version: 1, dataset: 'price-pack', ticker: e.t, columns: ['d', 'o', 'h', 'l', 'c', 'v'], d, o: cut('o'), h: cut('h'), l: cut('l'), c: cut('c'), v: cut('v') };
}

export interface BuildInput {
  price: Columnar; actions: Columnar; ref: TickerReference; state: PublicationState;
  engine: { screener_engine: string; registry: string; screener_registry: string };
  tailLength: number; capBudgetMs: number; withinMax: number;
  /** the presets: every series their enabled conditions read (bound as a run binds them, lagged sides included) is
      pinned too; a condition that does not bind (an unavailable metric) is left out and listed */
  presets: readonly PresetDefinition[];
}
export interface BuildStats { tickers: number; stocks: number; bars: number; dropped: number; no_price: number; actions: number; series: number; skipped: { ref: string; reason: string }[] }

/** The snapshot of one publication (header), without its tails' values (prewarm fills them, snapshotDigest seals
    them). Throws DataError for anything the publisher cannot have written. */
export async function buildSnapshot(input: BuildInput): Promise<{ desc: SnapshotDesc; entries: TickerEntry[]; stats: BuildStats }> {
  const doc = input.price;
  for (const c of ['t', 'd', 'o', 'h', 'l', 'c', 'v']) if (!doc.columns.includes(c)) throw integrity(`The price file has no column ${c}.`);
  if (doc.dataset !== undefined && doc.dataset !== 'xsection') throw integrity(`The price file is a ${String(doc.dataset)} file, not xsection.`);
  const entries = tickerEntries(doc);
  const refBy = new Map(input.ref.tickers.map(r => [r.ticker, r]));
  const outside = entries.filter(e => !refBy.has(e.t)).map(e => e.t);
  if (outside.length) throw integrity(`${outside.length} ticker(s) of the price file are not in the reference file (${outside.slice(0, 5).join(', ')}${outside.length > 5 ? ', ...' : ''}); it is written under a fixed key and may be from another run.`, 'ref');
  const index = entries.findIndex(e => e.t === INDEX_TICKER);
  if (index < 0) throw new DataError('DATA_MISSING', `The price file has no ${INDEX_TICKER} rows; the screener needs its calendar and closes.`, `${INDEX_TICKER}.price`);
  const actions = actionsByTicker(input.actions);

  const N = (doc.t as unknown[]).length, T = entries.length;
  const offsets = shared(Int32Array, T + 1), O = shared(Float64Array, N), H = shared(Float64Array, N), L = shared(Float64Array, N),
    C = shared(Float64Array, N), V = shared(Float64Array, N), Tix = shared(Int32Array, N), missing = shared(Uint8Array, T);
  const dateIds = new Map<string, number>(), dateList: string[] = [];
  const E = input.state.price_through && isDate(input.state.price_through) ? input.state.price_through : entries.reduce((m, e) => e.last > m ? e.last : m, '');
  const rows: UniverseRow[] = [];
  let at = 0, w = 0, dropped = 0, nActions = 0;
  for (let j = 0; j < T; j++) {
    const e = entries[j];
    const s = priceSeries(e.t, [sliceDoc(doc, e, at)]);
    at += e.rows; dropped += s.dropped;
    offsets[j] = w;
    const n = s.dates.length, b = s.bars;
    let mask = 0;
    for (let k = 0; k < FIELDS.length; k++) {
      const xs = b[FIELDS[k]];
      let has = false;
      for (let i = 0; i < n && !has; i++) { const v = xs[i]; has = typeof v === 'number' && Number.isFinite(v) && v !== 0 }
      if (!has) mask |= 1 << k;
    }
    missing[j] = mask;
    for (let i = 0; i < n; i++) {
      O[w + i] = b.O[i] as number; H[w + i] = b.H[i] as number; L[w + i] = b.L[i] as number; C[w + i] = b.C[i] as number;
      const v = b.V[i]; V[w + i] = v === null || v === undefined ? NaN : v;
      const d = s.dates[i];
      let id = dateIds.get(d);
      if (id === undefined) { id = dateList.length; dateIds.set(d, id); dateList.push(d) }
      Tix[w + i] = id;
    }
    w += n;
    const r = refBy.get(e.t)!;
    if (r.type !== 'stock') continue;
    // universe attributes (report 6.7) and the remarks of P4, by the core's own functions (metrics.ts
    // universeAttributes: last close, 1D %, ADV20 = signals.ts liquidity, bars, stale; universe.ts priceBreakRemarks)
    const a = universeAttributes(tickerCalc({ ticker: e.t, dates: s.dates, bars: b }), E);
    const remarks: RowRemark[] = a.stale ? [{ code: 'STALE', last_bar_date: a.last_bar }] : [];
    const own = actions.get(e.t) ?? [];
    nActions += own.length;
    if (own.length) {
      const breaks: PriceBreakRemark[] = priceBreakRemarks(own, s.dates, b.C, { boundary: ADJUSTED_HISTORY_BOUNDARY, priceActionTypes: PRICE_ACTION_TYPES });
      remarks.push(...breaks);
    }
    rows.push({
      ticker: e.t, name: r.name, sector: r.groups.sector ?? null, industry: r.groups.industry ?? null,
      last: a.last, chg_1d_pct: a.chg_1d_pct, adv20_idr: a.adv20_idr, first_bar: a.first_bar, last_bar: a.last_bar, bars: a.bars, stale: a.stale, remarks,
    });
  }
  offsets[T] = w;
  // the date table in date order; the bars' indexes renumbered to it
  const order = dateList.map((d, i) => [d, i] as const).sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
  const renum = new Int32Array(order.length);
  order.forEach(([, old], k) => { renum[old] = k });
  for (let i = 0; i < w; i++) Tix[i] = renum[Tix[i]];
  const dates = order.map(([d]) => d);
  rows.sort((a, b) => byTicker(a.ticker, b.ticker));

  const price_data = await dataVersion(entries.map(e => ({ ticker: e.t, dataset: 'price', sha256: e.pack_sha256 })));
  const versions = { screener_engine: input.engine.screener_engine, registry: input.engine.registry, screener_registry: input.engine.screener_registry, price_data, flow_data: null };
  const data = { evaluation_date: E, price_through: input.state.price_through ?? E, flow_through: null, broker_behind_sessions: input.state.broker_behind_sessions, published_at: input.state.finished_at };
  const actionsSha = crypto.createHash('sha256').update(JSON.stringify([...actions.entries()])).digest('hex').slice(0, 16);
  const sid = `${price_data.slice(0, 32)}:${actionsSha}:${referenceHash(input.ref)}`;

  // the pinned series: the 53 at their start configuration (76 outputs), then the presets' (6.7 "Pre-warmed")
  const desc0 = { offsets, O, H, L, C, V, T: Tix, dates, tickers: entries.map(e => e.t), index, missing };
  const ihsg = materialize(desc0, index);
  const dv: DataVersions = { price_data, screener_engine: versions.screener_engine };
  const seen = new Set<string>(), list: { ref: MetricRef; key: string }[] = [], skipped: BuildStats['skipped'] = [];
  const opts = { capBudgetMs: input.capBudgetMs, index: ihsg };
  const add = (r: ResolvedSeries) => { const key = seriesKey(dv, r); if (!seen.has(key)) { seen.add(key); list.push({ ref: r.ref, key }) } };
  for (const ind of INDICATORS) {
    const params = startParams(ind, opts);
    for (const o of ind.outputs) add(resolveSeries({ kind: 'indicator', indicator: ind.id, params, output: o.key }, `start.${ind.id}.${o.key}`, opts));
  }
  for (const p of input.presets) {
    p.definition.conditions.forEach((c, k) => {
      if (!c.enabled) return;
      try { bindCondition(c, `presets.${p.id}.conditions[${k}]`, { ...opts, withinMax: input.withinMax, catalog: METRICS_CATALOG }).series.forEach(add) }
      catch (e) { skipped.push({ ref: `${p.id}.${c.id}`, reason: (e as Error)?.message?.slice(0, 200) ?? String(e) }) }
    });
  }
  const S = list.length;
  const desc: SnapshotDesc = {
    sid, versions, data, finished_at: input.state.finished_at, tailLength: input.tailLength, ...desc0, rows, series: list,
    tails: shared(Float64Array, S * T * input.tailLength), tailMeta: shared(Int32Array, S * T * 4), digest: null,
  };
  const stats: BuildStats = { tickers: T, stocks: rows.length, bars: w, dropped, no_price: input.ref.tickers.filter(r => r.type === 'stock' && !entries.some(e => e.t === r.ticker)).length, actions: nActions, series: S, skipped };
  return { desc, entries, stats };
}
/** A pinned series' reference resolved again (a thread resolves the list the builder wrote): a pattern through
    transforms.ts resolveSignal, anything else through metrics.ts resolveSeries. */
export function resolvePinned(ref: MetricRef, field: string, opts: ParamOptions & { index: TickerBars }): ResolvedSeries {
  return ref.kind === 'pattern' ? resolveSignal(ref as PatternRef, field, opts) : resolveSeries(ref, field, opts);
}

/* ---- reading the bars back -------------------------------------------------------------------------------------- */
type BarsDesc = Pick<SnapshotDesc, 'offsets' | 'O' | 'H' | 'L' | 'C' | 'V' | 'T' | 'dates' | 'tickers'>;
/** Ticker j's bars as plain arrays, value for value what priceSeries gave (header): O H L C numbers, V a number or
    null, T and `dates` the ticker's own dates. */
export function materialize(d: BarsDesc, j: number): TickerBars {
  const a = d.offsets[j], n = d.offsets[j + 1] - a;
  const O = new Array<number>(n), H = new Array<number>(n), L = new Array<number>(n), C = new Array<number>(n), V = new Array<number | null>(n), T = new Array<string>(n);
  for (let i = 0; i < n; i++) {
    O[i] = d.O[a + i]; H[i] = d.H[a + i]; L[i] = d.L[a + i]; C[i] = d.C[a + i];
    const v = d.V[a + i]; V[i] = Number.isNaN(v) ? null : v;
    T[i] = d.dates[d.T[a + i]];
  }
  const bars: Bars = { O, H, L, C, V, T };
  return { ticker: d.tickers[j], dates: T, bars };
}
export const barCount = (d: Pick<SnapshotDesc, 'offsets'>, j: number): number => d.offsets[j + 1] - d.offsets[j];

/* ---- pre-warm and digest ---------------------------------------------------------------------------------------- */

/** The pinned series of tickers [from, to), through the one series() path (metrics.ts, prewarm true), written into the
    shared tails. The work of one pre-warm chunk on one thread (the builder, or at a cold start every compute thread). */
export function prewarmChunk(d: SnapshotDesc, from: number, to: number, capBudgetMs: number): { ms: number; series: number } {
  const t0 = performance.now(), T = d.tickers.length, L = d.tailLength;
  const ihsg = materialize(d, d.index);
  const resolved = d.series.map((s, k) => resolvePinned(s.ref, `series[${k}]`, { capBudgetMs, index: ihsg }));
  const ctx = { versions: { price_data: d.versions.price_data, screener_engine: d.versions.screener_engine }, tailLength: L, cache: new SeriesCache(0) };
  for (let j = from; j < to; j++) {
    const tc = tickerCalc(materialize(d, j));
    for (let s = 0; s < resolved.length; s++) {
      const { tail } = series(ctx, tc, resolved[s], true);
      const cell = s * T + j, base = cell * L;
      d.tails.set(tail.values, base);
      d.tailMeta[cell * 4] = tail.n; d.tailMeta[cell * 4 + 1] = tail.from;
      d.tailMeta[cell * 4 + 2] = tail.firstValid; d.tailMeta[cell * 4 + 3] = tail.lastValid;
    }
    ctx.cache.clear();                                  // a ticker's Calc and tails go with it (metrics.ts tickerCalc)
  }
  return { ms: Math.round(performance.now() - t0), series: resolved.length };
}

/** sha256 over the pinned series' keys, the tickers and every tail with its header (header: Auditability). */
export function snapshotDigest(d: SnapshotDesc): string {
  const h = crypto.createHash('sha256');
  h.update(JSON.stringify([d.versions.price_data, d.tailLength, d.tickers, d.series.map(s => s.key)]));
  h.update(new Uint8Array(d.tailMeta.buffer, d.tailMeta.byteOffset, d.tailMeta.byteLength));
  h.update(new Uint8Array(d.tails.buffer, d.tails.byteOffset, d.tails.byteLength));
  return h.digest('hex');
}

/** Ticker j's pinned tail of series s, as a view into the shared tails (no copy). */
export function pinnedTail(d: SnapshotDesc, s: number, j: number): Tail {
  const cell = s * d.tickers.length + j, m = d.tailMeta, n = m[cell * 4], from = m[cell * 4 + 1], base = cell * d.tailLength;
  return { n, from, values: d.tails.subarray(base, base + (n - from)), firstValid: m[cell * 4 + 2], lastValid: m[cell * 4 + 3] };
}

/* ---- a compute thread's view of one snapshot ---------------------------------------------------------------------- */
export class ThreadSnapshot {
  desc: SnapshotDesc;
  cache: SeriesCache;
  dv: DataVersions;
  ihsg: TickerBars;
  ihsgCalendar: string[];
  position = new Map<string, number>();
  rows = new Map<string, UniverseRow>();
  /** ex dates of each PRICE_BREAK row's remarks (evaluate.ts priceBreakRemark) */
  breaks = new Map<string, string[]>();
  /** SeriesCache key of each pinned series */
  pinned: Set<string>;
  constructor(desc: SnapshotDesc, lruBytes: number) {
    this.desc = desc;
    this.cache = new SeriesCache(lruBytes);
    this.dv = { price_data: desc.versions.price_data, screener_engine: desc.versions.screener_engine };
    desc.tickers.forEach((t, j) => this.position.set(t, j));
    for (const r of desc.rows) {
      this.rows.set(r.ticker, r);
      const ex = r.remarks.filter((x): x is PriceBreakRemark => x.code === 'PRICE_BREAK').map(x => x.ex_date);
      if (ex.length) this.breaks.set(r.ticker, ex);
    }
    this.ihsg = materialize(desc, desc.index);
    this.ihsgCalendar = this.ihsg.dates as string[];
    this.pinned = new Set(desc.series.map(s => s.key));
    const T = desc.tickers.length;
    desc.series.forEach((s, k) => { for (let j = 0; j < T; j++) this.cache.set(s.key, desc.tickers[j], pinnedTail(desc, k, j), true) });
  }
  bars(ticker: string): TickerBars {
    const j = this.position.get(ticker);
    if (j === undefined) throw new RangeError(`snapshot: no ticker ${ticker}`);
    return materialize(this.desc, j);
  }
  /** The bar fields a ticker lacks over its whole history (metrics.ts missingInput at its last bar). */
  missingFields(ticker: string): string[] {
    const m = this.desc.missing[this.position.get(ticker) ?? -1] ?? 0;
    return FIELDS.filter((_, k) => m & (1 << k));
  }
}
