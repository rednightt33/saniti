/* Web Worker (EXEC-TERMINAL-UI-1026 U7, user 2026-10-26: "Pembacaan data dipindah ke proses latar browser (Web Worker),
   supaya layar tidak membeku"): downloads the presigned files of one ticker, inflates and parses them, and builds the
   broker structures off the page's main thread. It answers in stages (U5: chart first, then the Flow panel): `price`
   as soon as the price files are read, then `broker`, then `events`. Every download starts at once (the URLs live
   120 s). The shapes match what live.ts built before on the main thread. */
import type { BrokerRow } from './types';

/** one file to read: its presigned URL and, from /bundle, the sha256 of its bytes (the browser cache key) */
export interface FileRef { url: string; sha?: string; name?: string }
export interface WorkerJob { id: number; price: FileRef[]; broker: FileRef[]; events: FileRef[] }
/** EXEC-TERMINAL-SPEED step 1: what each download cost, for ?perf=1 */
export interface FileStat { name: string; ms: number; bytes: number; cached: boolean }
export interface PriceRow { d: string; o: number; h: number; l: number; c: number; v: number | null }
export interface WorkerCombo { broker: string; investor: string; board: string; gross: number; net: Float64Array }
export type WorkerAnswer =
  | { id: number; type: 'price'; rows: PriceRow[] }
  | { id: number; type: 'broker' | 'brokerAll'; combos: WorkerCombo[]; flowFrom: number; flowTo: number; dates: string[]; rows: BrokerRow[][] }
  | { id: number; type: 'events'; rows: Record<string, unknown>[] }
  | { id: number; type: 'stats'; files: FileStat[] }
  | { id: number; type: 'error'; message: string; status: number };

interface Columnar { columns: string[]; [k: string]: any }

/* EXEC-TERMINAL-SPEED step 3 (user 2026-10-26: "Cache boleh, tapi jangan sampai cache itu terlalu menjadi besar"): the
   files are kept in the browser (IndexedDB) under the sha256 of their bytes, at most CACHE_LIMIT bytes; the least
   recently used go first. A file is stored only when its bytes hash to the sha256 /bundle announced. No server cost. */
const CACHE_DB = 'terminal-files', CACHE_STORE = 'files', CACHE_LIMIT = 50_000_000;
let cacheDb: Promise<IDBDatabase | null> | null = null;
const idb = <T>(req: IDBRequest<T>) => new Promise<T>((ok, no) => { req.onsuccess = () => ok(req.result); req.onerror = () => no(req.error) });
function openCache(): Promise<IDBDatabase | null> {
  if (cacheDb) return cacheDb;
  cacheDb = new Promise(ok => {
    try {
      const req = indexedDB.open(CACHE_DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(CACHE_STORE, { keyPath:'sha' }).createIndex('used', 'used');
      req.onsuccess = () => ok(req.result); req.onerror = () => ok(null); req.onblocked = () => ok(null);
    } catch { ok(null) }
  });
  return cacheDb;
}
async function cacheGet(sha: string): Promise<Uint8Array<ArrayBuffer> | null> {
  const db = await openCache(); if (!db) return null;
  try {
    const store = db.transaction(CACHE_STORE, 'readwrite').objectStore(CACHE_STORE);
    const hit: any = await idb(store.get(sha));
    if (!hit) return null;
    store.put({ ...hit, used:Date.now() });
    return new Uint8Array(hit.bytes);
  } catch { return null }
}
async function cachePut(sha: string, bytes: Uint8Array) {
  const db = await openCache(); if (!db) return;
  try {
    const store = db.transaction(CACHE_STORE, 'readwrite').objectStore(CACHE_STORE);
    await idb(store.put({ sha, bytes:bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), size:bytes.byteLength, used:Date.now() }));
    const all: any[] = await idb(store.index('used').getAll());              // oldest use first
    let total = all.reduce((t, r) => t + r.size, 0);
    for (const r of all) { if (total <= CACHE_LIMIT) break; if (r.sha === sha) continue; store.delete(r.sha); total -= r.size }
  } catch { /* a full or blocked store only loses the cache */ }
}
const hex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
export const stats: FileStat[] = [];

/* gzip JSON from a presigned URL (or the browser cache); a body the browser already inflated is read as is */
export async function download(file: string | FileRef): Promise<Columnar> {
  const ref = typeof file === 'string' ? { url:file } : file, t0 = performance.now();
  let bytes: Uint8Array<ArrayBuffer> | null = ref.sha ? await cacheGet(ref.sha) : null;
  const cached = !!bytes;
  if (!bytes) {
    const res = await fetch(ref.url, { credentials:'omit' });
    if (!res.ok) throw Object.assign(new Error(`A data file could not be downloaded (${res.status}).`), { status:res.status });
    bytes = new Uint8Array(await res.arrayBuffer());
    if (ref.sha && typeof crypto !== 'undefined' && crypto.subtle && hex(await crypto.subtle.digest('SHA-256', bytes)) === ref.sha) cachePut(ref.sha, bytes);
  }
  stats.push({ name:ref.name || ref.url.split('?')[0].split('/').slice(-2).join('/'), ms:Math.round(performance.now() - t0), bytes:bytes.byteLength, cached });
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
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

const board = (m: string) => /nego/i.test(m) ? 'Nego' : /cash|tunai/i.test(m) ? 'Cash' : 'Regular';

/* Flow Timeline: net value (buy − sell) per broker × investor type × board on each session of the chart; Broker
   activity: the summary rows of the last 30 broker dates */
export function brokerData(docs: Columnar[], dates: string[]) {
  const N = dates.length, idx = new Map(dates.map((t, i) => [t, i]));
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
  const last = [...byDate.keys()].sort().slice(-30);
  return { combos:[...combos.values()], flowFrom, flowTo, dates:last, rows:last.map(t => byDate.get(t)!) };
}

export const rowsOf = (doc: Columnar) => {
  const n = doc[doc.columns[0]].length;
  return Array.from({ length:n }, (_, i) => Object.fromEntries(doc.columns.map(c => [c, doc[c][i]])));
};

/* the worker side; skipped when the module is imported by the tests */
const scope = globalThis as any;
if (typeof scope.WorkerGlobalScope !== 'undefined' && scope instanceof scope.WorkerGlobalScope) {
  scope.onmessage = async (e: MessageEvent<WorkerJob>) => {
    const { id, price, broker, events } = e.data;
    const post = (answer: WorkerAnswer, transfer: Transferable[] = []) => scope.postMessage(answer, transfer);
    const fail = (err: any) => post({ id, type:'error', message:err?.message || 'The terminal could not read its data.', status:err?.status || 0 });
    /* EXEC-TERMINAL-1026B F5 (user 2026-10-26: "dimuat di awal tahun, tapi setelah terload maka sistem akan otomatis meload
       seluruh data"): the broker files (about 98 % of a ticker's bytes) come newest first: the last RECENT years are read
       and answered (`broker`), then the older years follow by themselves and the whole history is answered
       (`brokerAll`). The price (about 0.03 MB for all years) is read at once: the chart keeps one fixed timeline. */
    const RECENT = 2;
    const recent = broker.slice(-RECENT), older = broker.slice(0, -RECENT);
    const recentDocs = Promise.all(recent.map(download));
    const eventDocs = Promise.all(events.map(download));
    recentDocs.catch(() => {}); eventDocs.catch(() => {});      // read below, after the price; no unhandled rejection
    let rows: PriceRow[];
    try { rows = priceRows(await Promise.all(price.map(download))) } catch (err) { return fail(err) }
    post({ id, type:'price', rows });
    const dates = rows.map(r => r.d);
    let latest: Columnar[];
    try {
      latest = await recentDocs;
      const b = brokerData(latest, dates);
      post({ id, type:'broker', ...b }, b.combos.map(c => c.net.buffer));
    } catch (err) { return fail(err) }
    try { post({ id, type:'events', rows:(await eventDocs).flatMap(rowsOf) }) } catch (err) { fail(err) }
    try {
      const all = brokerData([...await Promise.all(older.map(download)), ...latest], dates);
      post({ id, type:'brokerAll', ...all }, all.combos.map(c => c.net.buffer));
    } catch (err) { fail(err) }
    post({ id, type:'stats', files:stats.splice(0) });
  };
}
