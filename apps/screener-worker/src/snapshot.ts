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
   pre-warmed series (the 53 indicators at registry.ts startParams, 76 outputs, the core's declared derived series of
   the default cards (condition.ts declaredDerivedSeries), plus every series the presets name)
   are tails of tailLength(SCREENER_WITHIN_MAX) bars per (series, ticker) in one shared Float64Array, written by the
   pre-warm through the one series() path (metrics.ts) and installed in each thread's SeriesCache as pinned views.
   snapshot_digest = sha256 over the series keys, the tickers and every tail and its header (6.7 Auditability): two
   replicas at one publication log the same digest.
   EXEC-SCREENER-FLOW-CANDLES P4 (user 2026-11-07; verification/screener/P4_BROKER_DAYS.md section 3): the optional
   broker day files beside the Phase 1 files, decoded and stored once per replica by broker.ts (desc.broker: shared
   columns per ticker of this snapshot; a ticker without price is not loaded); versions.flow_data, data.flow_through
   and data.broker_window come from it, and sid names flow_data, so a change of the broker days alone is another
   snapshot (its own caches, never the previous one's answers).
   EXEC-SCREENER-FLOW-CANDLES P5a (verification/screener/P5_FLOW.md section 1): a request's view of a ticker
   (TickerView.flow) gives the core's flow series (flowmetrics.ts) the ticker's broker rows of the loaded window
   (brokerRows), the brokers' classification of the reference file `brokers` (desc.brokerClasses, read by the refresh
   beside `tickers`; FL34) and the thread's memo of computeFlow answers (one call per ticker, indicator and parameters
   per snapshot, FLOW_MEMO_KEEP of them). Flow series are computed on request, never pinned (the pre-warm views have no
   broker rows). */
import crypto from 'node:crypto';
import { DataError, PRICE_ACTION_TYPES, dataVersion, priceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { ADJUSTED_HISTORY_BOUNDARY } from '../../edge-bff/backtest/src/core/engine.ts';
import { byTicker } from '../../edge-bff/backtest/src/core/signals.ts';
import { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { Bars } from '../../edge-bff/terminal/src/calc/indicators.ts';
import type { DataStatus, Grouping, MetricRef, PatternRef, PriceBreakRemark, RowRemark, UniverseRow, Versions } from '../../edge-bff/screener/src/core/contract.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import type { PresetDefinition } from '../../edge-bff/screener/src/core/catalog.ts';
import { bindCondition, declaredDerivedSeries } from '../../edge-bff/screener/src/core/condition.ts';
import type { XsectionNeed } from '../../edge-bff/screener/src/core/condition.ts';
import { SeriesCache, resolveSeries, scanMissingInput, series, seriesKey, tickerCalc, universeAttributes } from '../../edge-bff/screener/src/core/metrics.ts';
import type { DataVersions, ResolvedSeries, Tail, TickerBars, TickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import type { BarField, ParamOptions } from '../../edge-bff/screener/src/core/registry.ts';
import { INDICATORS, startParams } from '../../edge-bff/screener/src/core/registry.ts';
import { resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { evaluationBar, round12 } from '../../edge-bff/screener/src/core/evaluate.ts';
import { returnRankAll } from '../../edge-bff/screener/src/core/xsection.ts';
import { priceBreakRemarks } from '../../edge-bff/screener/src/core/universe.ts';
import type { ActionRow } from '../../edge-bff/screener/src/core/universe.ts';
import type { TickerReference } from '../../backtest-worker/src/terminal.ts';
import { brokerFlowData, brokerRowsOf, brokerWindowOf, buildBrokerStore } from './broker.ts';
import { readsFlow } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import type { FlowBindContext, TickerFlow } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import type { FlowOut } from '../../edge-bff/terminal/src/calc/flow.ts';
import type { BrokerDay, BrokerRows, BrokerStats, BrokerStore } from './broker.ts';

export const INDEX_TICKER = 'IHSG';
export const PRICE_FILE = 'price';
export const ACTIONS_FILE = 'actions';
/** The required xsection files (report 6.5 "Phase 1 files"), the one list of them: the refresh requires these (P4 reads
    the optional broker days beside them, broker.ts), the builder decodes each into BuildInput (thread.ts), and a metric
    counts as available only over a file of this list (catalog.ts metricAvailability), never one the index merely names. */
export const PHASE1_FILES = [PRICE_FILE, ACTIONS_FILE] as const;
export type ReadFile = typeof PHASE1_FILES[number];

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
  broker: BrokerStore;               // P4: the loaded broker days (broker.ts), per ticker of `tickers`
  brokerClasses: Record<string, string>;   // P5a: broker code -> classification (reference file `brokers`; {} when not published)
}
/** The reference the refresh hands the build: the tickers file, and (P5a) the brokers' classification of the reference
    file `brokers` (code -> IDX_Broker_Profile class, as the Terminal reads it), absent when it could not be read. */
export type SnapshotReference = TickerReference & { brokerClasses?: Record<string, string> };
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
export const referenceHash = (ref: SnapshotReference): string =>
  crypto.createHash('sha256').update(JSON.stringify([ref.groupings, ref.tickers.map(r => [r.ticker, r.name, r.type, ref.groupings.map(g => r.groups[g] ?? null)]),
    // P5a: the brokers' classification too (a changed class changes FL34, so it is another snapshot); absent: as before
    ...(ref.brokerClasses ? [Object.entries(ref.brokerClasses).sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)] : [])])).digest('hex').slice(0, 16);

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

/** The decoded files of PHASE1_FILES by name, and what the build needs besides them. */
export interface BuildInput extends Record<ReadFile, Columnar> {
  ref: SnapshotReference; state: PublicationState;
  engine: { screener_engine: string; registry: string; screener_registry: string };
  tailLength: number; capBudgetMs: number; withinMax: number;
  /** the presets: every series their enabled conditions read (bound as a run binds them, lagged sides included) is
      pinned too; a condition that does not bind (an unavailable metric) is left out and listed */
  presets: readonly PresetDefinition[];
  /** P4: the broker days read now (decoded, broker.ts decodeBrokerDay), those carried from the held snapshot's store
      and the window's days left for a follow-up refresh; none: an empty store */
  broker?: { days: readonly BrokerDay[]; carry: { from: BrokerStore; names: readonly string[] } | null; missing: number };
}
export interface BuildStats { tickers: number; stocks: number; bars: number; dropped: number; no_price: number; actions: number; series: number; skipped: { ref: string; reason: string }[]; broker: BrokerStats }

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
  const afterE: string[] = [];
  for (let j = 0; j < T; j++) {
    const e = entries[j];
    const s = priceSeries(e.t, [sliceDoc(doc, e, at)]);
    at += e.rows; dropped += s.dropped;
    offsets[j] = w;
    const n = s.dates.length, b = s.bars;
    if (n && s.dates[n - 1] > E) afterE.push(e.t);
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
    // the wire's numbers (round12, report 8.5): the page applies universe.ts to these very rows, the worker's S0 too
    rows.push({
      ticker: e.t, name: r.name, sector: r.groups.sector ?? null, industry: r.groups.industry ?? null,
      last: round12(a.last), chg_1d_pct: round12(a.chg_1d_pct), adv20_idr: round12(a.adv20_idr), first_bar: a.first_bar, last_bar: a.last_bar, bars: a.bars, stale: a.stale, remarks,
    });
  }
  offsets[T] = w;
  // no bar after E (6.5 as-of policy; no look-ahead): every series is cut to its tail at the ticker's last bar and the
  // core evaluates there (evaluate.ts evaluationBar), so a ticker with a bar after price_through would be read at a bar
  // its tail does not hold, or past E. A file holding one disagrees with the state of its own publication (a session
  // loaded while the publisher ran): DATA_INTEGRITY, the previous snapshot keeps serving
  if (afterE.length) throw integrity(`${afterE.length} ticker(s) of the price file have bars after the publication's price_through ${E} (${afterE.slice(0, 5).join(', ')}${afterE.length > 5 ? ', ...' : ''}); the file and the state disagree, so the publication is not loaded.`);
  // the date table in date order; the bars' indexes renumbered to it
  const order = dateList.map((d, i) => [d, i] as const).sort((a, b) => a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
  const renum = new Int32Array(order.length);
  order.forEach(([, old], k) => { renum[old] = k });
  for (let i = 0; i < w; i++) Tix[i] = renum[Tix[i]];
  const dates = order.map(([d]) => d);
  rows.sort((a, b) => byTicker(a.ticker, b.ticker));

  const price_data = await dataVersion(entries.map(e => ({ ticker: e.t, dataset: 'price', sha256: e.pack_sha256 })));
  // P4: the broker store per ticker of this snapshot, and the versions and data it gives (broker_window last, so
  // published_at stays in the head edge-bff reads)
  const broker = buildBrokerStore(entries.map(e => e.t), input.broker?.days ?? [], input.broker?.carry ?? null, input.broker?.missing ?? 0);
  const flow_data = brokerFlowData(broker.store.days);
  const versions = { screener_engine: input.engine.screener_engine, registry: input.engine.registry, screener_registry: input.engine.screener_registry, price_data, flow_data };
  const data = { evaluation_date: E, price_through: input.state.price_through ?? E, flow_through: broker.store.dates[broker.store.dates.length - 1] ?? null,
    broker_behind_sessions: input.state.broker_behind_sessions, published_at: input.state.finished_at, broker_window: brokerWindowOf(broker.store) };
  const actionsSha = crypto.createHash('sha256').update(JSON.stringify([...actions.entries()])).digest('hex').slice(0, 16);
  const sid = `${price_data.slice(0, 32)}:${actionsSha}:${referenceHash(input.ref)}:${flow_data ? flow_data.slice(0, 16) : '-'}`;

  // the pinned series: the 53 at their start configuration (76 outputs), then the presets' (6.7 "Pre-warmed")
  const desc0 = { offsets, O, H, L, C, V, T: Tix, dates, tickers: entries.map(e => e.t), index, missing };
  const ihsg = materialize(desc0, index);
  const dv: DataVersions = { price_data, screener_engine: versions.screener_engine };
  const seen = new Set<string>(), list: { ref: MetricRef; key: string }[] = [], skipped: BuildStats['skipped'] = [];
  const opts = { capBudgetMs: input.capBudgetMs, index: ihsg };
  // a flow series is never pinned: the pre-warm's views carry no broker rows (P5a; it is computed on request)
  const add = (r: ResolvedSeries) => { if (readsFlow(r)) return; const key = seriesKey(dv, r); if (!seen.has(key)) { seen.add(key); list.push({ ref: r.ref, key }) } };
  for (const ind of INDICATORS) {
    const params = startParams(ind, opts);
    for (const o of ind.outputs) add(resolveSeries({ kind: 'indicator', indicator: ind.id, params, output: o.key }, `start.${ind.id}.${o.key}`, opts));
  }
  // the contract-declared derived series (core condition.ts declaredDerivedSeries: the five bar fields, the prior bar
  // of the Donchian bands a price comparison reads, the lag and moving average the rising and vs-MA forms open with),
  // so every default card is a snapshot lookup (stage S2, 6.7)
  for (const r of declaredDerivedSeries(opts)) add(r);
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
    tails: shared(Float64Array, S * T * input.tailLength), tailMeta: shared(Int32Array, S * T * 4), digest: null, broker: broker.store,
    brokerClasses: { ...(input.ref.brokerClasses ?? {}) },
  };
  const stats: BuildStats = { tickers: T, stocks: rows.length, bars: w, dropped, no_price: input.ref.tickers.filter(r => r.type === 'stock' && !entries.some(e => e.t === r.ticker)).length, actions: nActions, series: S, skipped, broker: broker.stats };
  return { desc, entries, stats };
}
/** A pinned series' reference resolved again (a thread resolves the list the builder wrote): a pattern through
    transforms.ts resolveSignal, anything else through metrics.ts resolveSeries. */
export function resolvePinned(ref: MetricRef, field: string, opts: ParamOptions & { index: TickerBars }): ResolvedSeries {
  return ref.kind === 'pattern' ? resolveSignal(ref as PatternRef, field, opts) : resolveSeries(ref, field, opts);
}

/* ---- reading the bars back -------------------------------------------------------------------------------------- */
type BarsDesc = Pick<SnapshotDesc, 'offsets' | 'O' | 'H' | 'L' | 'C' | 'V' | 'T' | 'dates' | 'tickers'>;
type Field = typeof FIELDS[number];
/** Ticker j's own dates, oldest first. */
function datesOf(d: BarsDesc, j: number): string[] {
  const a = d.offsets[j], n = d.offsets[j + 1] - a, T = new Array<string>(n);
  for (let i = 0; i < n; i++) T[i] = d.dates[d.T[a + i]];
  return T;
}
/** Ticker j's price column k as a plain array: numbers, and V's NaN back to null (header). */
function column(d: BarsDesc, j: number, k: Field): (number | null)[] {
  const a = d.offsets[j], n = d.offsets[j + 1] - a, src = d[k], out = new Array<number | null>(n);
  if (k === 'V') for (let i = 0; i < n; i++) { const v = src[a + i]; out[i] = Number.isNaN(v) ? null : v }
  else for (let i = 0; i < n; i++) out[i] = src[a + i];
  return out;
}
/** Ticker j's bars as plain arrays, value for value what priceSeries gave (header): O H L C numbers, V a number or
    null, T and `dates` the ticker's own dates. The dates are built at once (every evaluation reads them); each price
    column on its first read (a screen of pre-warmed series reads none of them), then kept. */
export function materialize(d: BarsDesc, j: number): TickerBars {
  const T = datesOf(d, j);
  return { ticker: d.tickers[j], dates: T, bars: lazyBars(T, k => column(d, j, k)) };
}
/** Bars whose price columns are made on their first read and then become plain data properties, so the loops of F
    that read B.C, B.H ... again and again pay no getter call (about 4% of a pre-warm, measured). */
function lazyBars(T: readonly string[], make: (k: Field) => (number | null)[]): Bars {
  const bars: Record<string, unknown> = { T };
  for (const k of FIELDS) Object.defineProperty(bars, k, { configurable: true, enumerable: true,
    get() { const v = make(k); Object.defineProperty(bars, k, { value: v, enumerable: true, writable: false, configurable: false }); return v } });
  return bars as unknown as Bars;
}

/** One ticker of a compute thread's snapshot as one request reads it (run.ts screenEnv; report 6.7: a screen of
    pre-warmed series is a lookup that reads no bar). The dates are the thread's own copy, kept for the snapshot's life
    (ThreadSnapshot.view); each price column is made on its first read and the backtest core's Calc on the first
    computation (its constructor reads the close column); `missing` answers metrics.ts missingInput from the snapshot's
    per-ticker mask (built from the same bars with the same rule, so a lookup reads no column), and scans only when the
    evaluation bar is not the last bar (the mask covers the whole history). release() drops the Calc with its memo of
    full outputs (about 25 KB per output per ticker as F returns them): the planner holds every survivor's view until
    the screen ends, so without it a request with k custom series would keep k outputs of every survivor (about
    0.2 GB for five custom conditions on the whole market); with it a request keeps at most run.ts CALC_KEEP tickers'
    outputs, plus the columns it read (at most five of every survivor, about 55 MB; making them again on every
    condition pass costs more CPU than it saves, measured). A released view computes again, the same values. */
export class TickerView implements TickerCalc {
  readonly ticker: string;
  readonly dates: readonly string[];
  readonly bars: Bars;
  private desc: SnapshotDesc;
  private j: number;
  private made: Calc | null = null;
  /** P5a: the ticker's broker rows of the loaded window, the classification and the thread's computeFlow memo (the core's
      flow series read them; flowmetrics.ts TickerFlow); absent on a view without them (the pre-warm's) */
  readonly flow?: TickerFlow;
  /** the thread's meter of reused work (run.ts screenEnv): the Calc's memo of full outputs reports a read of an output
      made before the measurement began */
  private reuse?: Reuse;
  constructor(desc: SnapshotDesc, j: number, dates: readonly string[], onColumn: () => void = () => {}, flow?: TickerFlow, reuse?: Reuse) {
    this.desc = desc; this.j = j; this.ticker = desc.tickers[j]; this.dates = dates;
    this.bars = lazyBars(dates, k => { onColumn(); return column(desc, j, k) });
    if (flow) this.flow = flow;
    if (reuse) this.reuse = reuse;
  }
  get calc(): Calc {
    if (this.made) return this.made;
    const c = new Calc(this.bars);
    if (this.reuse) c.memo = new StampedMap(this.reuse);
    return this.made = c;
  }
  /** The ticker's broker rows and distinct brokers in the loaded window (the work a flow series does grows with them;
      run.ts costUnits). */
  get flowSize(): { rows: number; brokers: number } { return { rows: brokerRowCount(this.desc, this.j), brokers: brokerCounts(this.desc)[this.j] } }
  readonly missing = (inputs: readonly BarField[], at: number): BarField | null => {
    if (at !== this.dates.length - 1) return scanMissingInput(this, inputs, at);
    const m = this.desc.missing[this.j];
    for (const f of inputs) if (m & (1 << FIELDS.indexOf(f))) return f;
    return null;
  };
  /** Whether the view holds a Calc (outputs computed since its creation or its last release). */
  get holding(): boolean { return this.made !== null }
  release(): void { this.made = null }
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
  /** each ticker's dates, built on its first request and kept for the snapshot's life on this thread (every request
      reads them; at most one string reference per bar of the snapshot, about 10.6 MB for 1.33 M bars) */
  private dates: (readonly string[] | undefined)[];
  /** price columns made for requests on this thread (a screen of pre-warmed series makes none) */
  stats = { columns: 0 };
  constructor(desc: SnapshotDesc, lruBytes: number) {
    this.desc = desc;
    this.dates = new Array(desc.tickers.length);
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
  /** P4 (for P5's flow module): one ticker's broker rows from `from` to `to` (ISO dates, both included; null = open), as
      views into the shared store without a copy (broker.ts brokerRowsOf); undefined for a ticker the snapshot does not
      have. No formula: the rows as the files hold them. */
  brokerRows(ticker: string, from: string | null = null, to: string | null = null): BrokerRows | undefined {
    const j = this.position.get(ticker);
    return j === undefined ? undefined : brokerRowsOf(this.desc.broker, j, from, to);
  }
  /** A request's view of one ticker (TickerView), with this thread's copy of its dates; undefined for an unknown ticker. */
  view(ticker: string): TickerView | undefined {
    const j = this.position.get(ticker);
    if (j === undefined) return undefined;
    const dates = this.dates[j] ??= datesOf(this.desc, j);
    const w = this.desc.data.broker_window, store = this.desc.broker;
    const flow: TickerFlow = { first: w?.first ?? null, last: w?.last ?? null, classification: this.desc.brokerClasses ?? {}, memo: this.flowMemo, meter: this.contexts,
      rows: () => brokerRowsOf(store, j, w?.first ?? null, w?.last ?? null) };
    return new TickerView(this.desc, j, dates, () => { this.stats.columns++ }, flow, this.reuse);
  }
  /** The thread's meter of reused work on this snapshot: its computeFlow memo and every view's Calc memo report a read
      of an entry made before the current measurement began (run.ts screenEnv learns only from series computed cold). */
  readonly reuse = new Reuse();
  /** The thread's meter of the flow windows' contexts (flowmetrics.ts TickerFlow.meter): each build's time and the rows
      it read, summed, so run.ts screenEnv takes it out of the flow series that built it and observes it on its own. */
  readonly contexts = { ms: 0, rows: 0, built: 0, context<T>(build: () => T): T {
    const t0 = performance.now(), v = build() as T & { rows?: { n: number } };
    this.ms += performance.now() - t0; this.rows += v.rows?.n ?? 0; this.built++;
    return v;
  } };
  /** The broker rows and brokers of an average ticker with broker data in the loaded window (run.ts: the S3 order's
      flow costs). */
  get avgFlowSize(): { rows: number; brokers: number } {
    if (this.perTicker === undefined) {
      const counts = brokerCounts(this.desc);
      let rows = 0, brokers = 0, n = 0;
      for (let j = 0; j < this.desc.tickers.length; j++) { const r = brokerRowCount(this.desc, j); if (r) { rows += r; brokers += counts[j]; n++ } }
      this.perTicker = { rows: n ? rows / n : 0, brokers: n ? brokers / n : 0 };
    }
    return this.perTicker;
  }
  private perTicker?: { rows: number; brokers: number };
  /** P5a: the loaded broker window as the core checks a flow condition against it (K1 depth, availability, anchors). */
  get flowContext(): FlowBindContext { return flowContextOf(this.desc) }
  /** P5a: computeFlow answers by (ticker, indicator, parameters) for this snapshot, the FLOW_MEMO_KEEP most recent (a
      few KB each: the outputs over the window's 60 candles), so one call serves every output and request. */
  readonly flowMemo = new LruMemo<FlowOut>(FLOW_MEMO_KEEP, this.reuse);
  /** A cross-section's values (stage S1, report 6.7 "pre-warmed per publication", 6.10; core screen.ts
      xsectionValues): return_rank on the fixed population depends on the snapshot alone (every listed row, never the
      request's filters, xsection.ts), so it is computed once per thread by the core's own functions on the same inputs
      screen.ts would give them (each row's close and evaluation bar) and kept for the snapshot's life; at most
      XSECTION_KEEP windows (least recently used out). undefined for another metric: screen.ts then computes it. */
  crossSection(need: XsectionNeed): ReadonlyMap<string, number | null> | undefined {
    if (need.metric !== 'return_rank') return undefined;
    let v = this.xs.get(need.key);
    if (v) { this.xs.delete(need.key); this.xs.set(need.key, v); return v }
    const E = this.desc.data.evaluation_date, closes = new Map<string, { at: number; close: ArrayLike<number | null | undefined> }>();
    for (const r of this.desc.rows) { const t = this.view(r.ticker); if (t) closes.set(r.ticker, { at: evaluationBar(t.dates, E), close: t.bars.C }) }
    v = returnRankAll(this.desc.rows, closes, need.window, E).ranks;
    this.xs.set(need.key, v);
    if (this.xs.size > XSECTION_KEEP) this.xs.delete(this.xs.keys().next().value as string);
    return v;
  }
  private xs = new Map<string, ReadonlyMap<string, number | null>>();
}
/** Cross-sections (one per window) a thread keeps per snapshot: about 844 numbers each. */
export const XSECTION_KEEP = 16;
/** P5a: computeFlow answers a thread keeps per snapshot (an answer is its outputs over the window's candles, about 1 KB
    per output: some 20 MB at most). */
export const FLOW_MEMO_KEEP = 16384;
/** What a measurement reused (QA unit B, QA4: the cost model learns only from a series computed cold): a memo stamps
    each entry with the measurement it was made in, and a read of an entry made before the current measurement began
    is counted. begin() starts a measurement. One per compute thread and snapshot. */
export class Reuse {
  private epoch = 0;
  /** reads, since begin(), of entries made before it */
  reused = 0;
  begin(): void { this.epoch++; this.reused = 0 }
  get stamp(): number { return this.epoch }
  read(made: number): void { if (made < this.epoch) this.reused++ }
}
/** A Map that reports to a Reuse meter each read of an entry made before the current measurement (a view's Calc memo). */
export class StampedMap<V> extends Map<string, V> {
  private made = new Map<string, number>();
  private meter: Reuse;
  constructor(meter: Reuse) { super(); this.meter = meter }
  get(key: string): V | undefined { const v = super.get(key); if (v !== undefined) this.meter.read(this.made.get(key) ?? 0); return v }
  set(key: string, v: V): this { this.made?.set(key, this.meter?.stamp ?? 0); return super.set(key, v) }
}
/** A memo of at most `keep` entries, the least recently used out; with a Reuse meter, a read of an entry made before the
    current measurement is reported to it. */
export class LruMemo<V> {
  private map = new Map<string, { v: V; made: number }>(); private keep: number; private meter?: Reuse;
  constructor(keep: number, meter?: Reuse) { this.keep = keep; if (meter) this.meter = meter }
  get(key: string): V | undefined {
    const e = this.map.get(key);
    if (e === undefined) return undefined;
    this.map.delete(key); this.map.set(key, e); this.meter?.read(e.made);
    return e.v;
  }
  set(key: string, v: V): void { this.map.delete(key); this.map.set(key, { v, made: this.meter?.stamp ?? 0 }); if (this.map.size > this.keep) this.map.delete(this.map.keys().next().value as string) }
  get size(): number { return this.map.size }
}
/** Ticker j's broker rows in the loaded window (the store holds the window's days only). */
export const brokerRowCount = (d: Pick<SnapshotDesc, 'broker'>, j: number): number => d.broker.offsets[j + 1] - d.broker.offsets[j];
const brokerCountsOf = new WeakMap<object, Uint16Array>();
/** Each ticker's distinct brokers in the loaded window (computed once per store: one pass over its rows). */
export function brokerCounts(d: Pick<SnapshotDesc, 'broker'>): Uint16Array {
  const s = d.broker;
  let c = brokerCountsOf.get(s);
  if (c) return c;
  const T = s.offsets.length - 1, seen = new Int32Array(Math.max(1, s.brokers.length)).fill(-1);
  c = new Uint16Array(Math.max(0, T));
  for (let j = 0; j < T; j++) for (let k = s.offsets[j]; k < s.offsets[j + 1]; k++) if (seen[s.B[k]] !== j) { seen[s.B[k]] = j; c[j]++ }
  brokerCountsOf.set(s, c);
  return c;
}
/** The loaded broker window of a snapshot as the core checks a flow condition against it (P5a): its sessions and dates,
    whether every day of the window is loaded (data.broker_window.complete) and whether the brokers' classification is
    published. */
export function flowContextOf(d: Pick<SnapshotDesc, 'data' | 'brokerClasses'>): FlowBindContext {
  const w = d.data.broker_window;
  return { sessions: w?.sessions ?? 0, first: w?.first ?? null, last: w?.last ?? null, complete: w?.complete ?? false, classification: Object.keys(d.brokerClasses ?? {}).length > 0 };
}
