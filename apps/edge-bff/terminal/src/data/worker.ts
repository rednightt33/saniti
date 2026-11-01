/* Web Worker (EXEC-TERMINAL-UI-1026 U7, user 2026-10-26: "Pembacaan data dipindah ke proses latar browser (Web Worker),
   supaya layar tidak membeku"): downloads the presigned files of one ticker, inflates and parses them, and builds the
   broker structures off the page's main thread. It answers in stages (U5: chart first, then the Flow panel): `price`
   as soon as the price files are read, then `broker`, then `events`. Every download starts at once (the URLs live
   120 s). The shapes match what live.ts built before on the main thread. */
import type { BrokerRow } from './types';
import { boardIndex, investorIndex, type FlowRows } from '../calc/flow';
import { barKey, buckets, type Buckets, type Timeframe } from './timeframe';
import { fileCache, readVerified, type FileRef } from './rack';

/** one file to read: its presigned URL and, from /bundle, the sha256 (the browser cache key) and size of its bytes
    (EXEC-MU-RUNTIME T7: rack.ts FileRef, checked by readVerified) */
export type { FileRef } from './rack';
/** `dates` (EXEC-TERMINAL-ASSETS): the daily sessions of the chart's own ticker; with it the broker files of another ticker
    (an added asset's Flow Timeline) are put on those sessions, and its price is not read */
export interface WorkerJob { id: number; price: FileRef[]; broker: FileRef[]; events: FileRef[]; tf?: Timeframe; dates?: string[];
  /** EXEC-INTRADAY-FEATURES C3: the intraday files of the chart's timeframe and the exchange's offset from UTC (seconds) */
  intraday?: FileRef[]; offset?: number }
/** EXEC-TERMINAL-SPEED step 1: what each download cost, for ?perf=1 */
export interface FileStat { name: string; ms: number; bytes: number; cached: boolean }
export interface PriceRow { d: string; o: number; h: number; l: number; c: number; v: number | null }
export interface WorkerCombo { broker: string; investor: string; board: string; gross: number; net: Float64Array }
export type WorkerAnswer =
  | { id: number; type: 'price'; rows: PriceRow[]; bars?: PriceRow[] }
  | { id: number; type: 'broker' | 'brokerAll'; combos: WorkerCombo[]; flowFrom: number; flowTo: number; dates: string[]; rows: BrokerRow[][]; flow: FlowRows }
  | { id: number; type: 'events'; rows: Record<string, unknown>[] }
  | { id: number; type: 'stats'; files: FileStat[] }
  /** `code` DATA_INTEGRITY: a file was not the one /bundle announced (rack.ts IntegrityError, `detail` what differed) */
  | { id: number; type: 'error'; message: string; status: number; code?: string; detail?: string };

interface Columnar { columns: string[]; [k: string]: any }

/* EXEC-TERMINAL-SPEED step 3 (user 2026-10-26: "Cache boleh, tapi jangan sampai cache itu terlalu menjadi besar"): the
   files are kept in the browser (IndexedDB) under the sha256 of their bytes, the least recently used going first. Since
   EXEC-BACKTEST-LOAD (K3) the cache and the download (asked again on a cut-off body or a 5xx, ERRORS M251) are the module
   every rack page shares (rack.ts), and since EXEC-MU-RUNTIME T7 so is the check: a file is drawn and stored only when
   its bytes have the size and sha256 /bundle announced, from the network or the cache (readVerified; before T7 a
   mismatched download was drawn and only not stored, the size was never checked and a cached copy was never checked
   again). */
const cache = fileCache();
export const stats: FileStat[] = [];

/* gzip JSON from a presigned URL (or the browser cache), checked first (rack.ts readVerified: IntegrityError when the
   bytes are not the announced file); a bare URL is a file no index describes, read unchecked, and a body the browser
   already inflated is read as is */
export async function download(file: string | FileRef): Promise<Columnar> {
  const ref = typeof file === 'string' ? { url:file } : file, t0 = performance.now();
  const { bytes, cached } = await readVerified(file, cache);
  stats.push({ name:ref.name || ref.url.split('?')[0].split('/').slice(-2).join('/'), ms:Math.round(performance.now() - t0), bytes:bytes.byteLength, cached });
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes as Uint8Array<ArrayBuffer>]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(stream).text());
  }
  return JSON.parse(new TextDecoder().decode(bytes));
}

/* price rows with four finite prices, oldest first */
export function priceRows(docs: Columnar[]): PriceRow[] {
  const out: PriceRow[] = [];
  for (const doc of docs) {
    const { d, o, h, l, c, v } = doc;
    for (let k = 0; k < d.length; k++) {
      if ([o[k], h[k], l[k], c[k]].every(Number.isFinite)) out.push({ d:d[k], o:o[k], h:h[k], l:l[k], c:c[k], v:v ? v[k] : null });
    }
  }
  return out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
}

/* EXEC-INTRADAY-FEATURES C3: intraday bars (columns t,o,h,l,c,v; t the bar's open in UTC seconds) as price rows keyed by
   their open time on the exchange's clock (timeframe.ts barKey); the archive and the current period do not overlap */
export function barRows(docs: Columnar[], offset: number): PriceRow[] {
  const out: PriceRow[] = [];
  for (const doc of docs) {
    const { t, o, h, l, c, v } = doc;
    for (let k = 0; k < t.length; k++) {
      if ([o[k], h[k], l[k], c[k]].every(Number.isFinite)) out.push({ d:barKey(t[k], offset), o:o[k], h:h[k], l:l[k], c:c[k], v:v ? v[k] : null });
    }
  }
  return out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
}

const board = (m: string) => /nego/i.test(m) ? 'Nego' : /cash|tunai/i.test(m) ? 'Cash' : 'Regular';

/* Flow Timeline: net value (buy − sell) per broker × investor type × board on each session of the chart; Broker
   activity: the summary rows of every broker date in the files. EXEC-BROKER-FULL (user 2026-11-01: "kita pindahkan
   langsung saja ke storage", go "4. Go"): the panels read the whole broker history, like the Flow Timeline; the
   two-year limit of B1 (2026-10-26, PANEL_YEARS) is gone. */
export function brokerData(docs: Columnar[], dates: string[], groups: Buckets | null = null) {
  // EXEC-TERMINAL-WM: with groups, a session's net goes to its weekly or monthly candle (`groups.of`)
  const N = groups ? groups.starts.length : dates.length, idx = new Map(dates.map((t, i) => [t, groups ? groups.of[i] : i]));
  const combos = new Map<string, WorkerCombo>(), byDate = new Map<string, BrokerRow[]>();
  let flowFrom = N, flowTo = -1;                      // first and last session with broker rows
  for (const doc of docs) {
    const { d, b, i: inv, m, bv, sv, bl, sl } = doc;
    for (let k = 0; k < d.length; k++) {
      const brd = board(m[k]);
      const row: BrokerRow = [b[k], inv[k], brd, bv[k] || 0, sv[k] || 0, bl[k] || 0, sl[k] || 0];
      (byDate.get(d[k]) || byDate.set(d[k], []).get(d[k])!).push(row);
      const i = idx.get(d[k]); if (i === undefined) continue;
      if (i < flowFrom) flowFrom = i;
      if (i > flowTo) flowTo = i;
      const key = `${row[0]}|${row[1]}|${brd}`;
      let c = combos.get(key);
      if (!c) combos.set(key, c = { broker:row[0], investor:row[1], board:brd, gross:0, net:new Float64Array(N) });
      c.net[i] += row[3] - row[4]; c.gross += row[3] + row[4];
    }
  }
  const all = [...byDate.keys()].sort();
  return { combos:[...combos.values()], flowFrom, flowTo, dates:all, rows:all.map(t => byDate.get(t)!), flow:flowRowsOf(docs, idx, N) };
}

/* EXEC-TERMINAL-FLOW-IND (user go 2026-10-30): the raw broker rows for the Flow indicators (calc/flow.ts FlowRows), one
   typed array per column, on the chart's candles (a weekly or monthly candle holds its sessions' rows). bf/sf are NaN in
   a file published before the transaction counts (the formulas that need them then give null). */
export function flowRowsOf(docs: Columnar[], idx: Map<string, number>, N: number): FlowRows {
  let n = 0;
  const codes = new Set<string>();
  for (const doc of docs) for (let k = 0; k < doc.d.length; k++) if (idx.has(doc.d[k])) { n++; codes.add(doc.b[k]) }
  const brokers = [...codes].sort(), at = new Map(brokers.map((b, k) => [b, k]));
  const R: FlowRows = { n, N, t:new Int32Array(n), b:new Uint16Array(n), inv:new Uint8Array(n), brd:new Uint8Array(n),
    bv:new Float64Array(n), sv:new Float64Array(n), bl:new Float64Array(n), sl:new Float64Array(n), bf:new Float64Array(n), sf:new Float64Array(n),
    brokers, has:new Uint8Array(N) };
  let j = 0;
  for (const doc of docs) {
    const { d, b, i: inv, m, bv, sv, bl, sl, bf, sf } = doc;
    for (let k = 0; k < d.length; k++) {
      const t = idx.get(d[k]); if (t === undefined) continue;
      R.t[j] = t; R.b[j] = at.get(b[k])!; R.inv[j] = investorIndex(inv[k]); R.brd[j] = boardIndex(m[k]);
      R.bv[j] = bv[k] || 0; R.sv[j] = sv[k] || 0; R.bl[j] = bl[k] || 0; R.sl[j] = sl[k] || 0;
      R.bf[j] = bf && bf[k] != null ? bf[k] : NaN; R.sf[j] = sf && sf[k] != null ? sf[k] : NaN;
      R.has[t] = 1; j++;
    }
  }
  return R;
}
/** the buffers of a FlowRows, to move it to the page without a copy */
export const flowBuffers = (R: FlowRows): ArrayBuffer[] =>
  [R.t, R.b, R.inv, R.brd, R.bv, R.sv, R.bl, R.sl, R.bf, R.sf, R.has].map(a => a.buffer as ArrayBuffer);

export const rowsOf = (doc: Columnar) => {
  const n = doc[doc.columns[0]].length;
  return Array.from({ length:n }, (_, i) => Object.fromEntries(doc.columns.map(c => [c, doc[c][i]])));
};

/* the worker side; skipped when the module is imported by the tests */
const scope = globalThis as any;
if (typeof scope.WorkerGlobalScope !== 'undefined' && scope instanceof scope.WorkerGlobalScope) {
  scope.onmessage = async (e: MessageEvent<WorkerJob>) => {
    const { id, price, broker, events, tf, dates:onto, intraday, offset } = e.data;
    const post = (answer: WorkerAnswer, transfer: Transferable[] = []) => scope.postMessage(answer, transfer);
    const fail = (err: any) => post({ id, type:'error', message:err?.message || 'The terminal could not read its data.', status:err?.status || 0,
      ...(typeof err?.code === 'string' ? { code:err.code } : {}), ...(typeof err?.detail === 'string' ? { detail:err.detail } : {}) });
    /* EXEC-TERMINAL-1026B F5 (user 2026-10-26: "dimuat di awal tahun, tapi setelah terload maka sistem akan otomatis meload
       seluruh data"): the broker files (about 98 % of a ticker's bytes) come newest first: the last RECENT years are read
       and answered (`broker`), then the older years follow by themselves and the whole history is answered
       (`brokerAll`). The price (about 0.03 MB for all years) is read at once: the chart keeps one fixed timeline. */
    const RECENT = 2;
    const recent = broker.slice(-RECENT), older = broker.slice(0, -RECENT);
    const recentDocs = Promise.all(recent.map(download));
    const eventDocs = Promise.all(events.map(download));
    recentDocs.catch(() => {}); eventDocs.catch(() => {});      // read below, after the price; no unhandled rejection
    let rows: PriceRow[], bars: PriceRow[] | undefined;
    try {
      const barDocs = intraday?.length ? Promise.all(intraday.map(download)) : null;
      barDocs?.catch(() => {});
      rows = priceRows(await Promise.all(price.map(download)));
      if (barDocs) bars = barRows(await barDocs, offset || 0);
    } catch (err) { return fail(err) }
    post({ id, type:'price', rows, ...(bars ? { bars } : {}) });
    // the broker data goes on the daily sessions; weekly and monthly candles group them (an intraday chart maps the daily
    // figures onto its candles on the page, timeframe.ts dayOfCandles)
    const dates = onto || rows.map(r => r.d), groups = tf === 'W' || tf === 'M' ? buckets(dates, tf) : null;
    let latest: Columnar[];
    try {
      latest = await recentDocs;
      const b = brokerData(latest, dates, groups);
      post({ id, type:'broker', ...b }, [...b.combos.map(c => c.net.buffer), ...flowBuffers(b.flow)]);
    } catch (err) { return fail(err) }
    try { post({ id, type:'events', rows:(await eventDocs).flatMap(rowsOf) }) } catch (err) { fail(err) }
    try {
      const all = brokerData([...await Promise.all(older.map(download)), ...latest], dates, groups);
      post({ id, type:'brokerAll', ...all }, [...all.combos.map(c => c.net.buffer), ...flowBuffers(all.flow)]);
    } catch (err) { fail(err) }
    post({ id, type:'stats', files:stats.splice(0) });
  };
}
