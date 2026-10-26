/* Web Worker (EXEC-TERMINAL-UI-1026 U7, user 2026-10-26: "Pembacaan data dipindah ke proses latar browser (Web Worker),
   supaya layar tidak membeku"): downloads the presigned files of one ticker, inflates and parses them, and builds the
   broker structures off the page's main thread. It answers in stages (U5: chart first, then the Flow panel): `price`
   as soon as the price files are read, then `broker`, then `events`. Every download starts at once (the URLs live
   120 s). The shapes match what live.ts built before on the main thread. */
import type { BrokerRow } from './types';

export interface WorkerJob { id: number; price: string[]; broker: string[]; events: string[] }
export interface PriceRow { d: string; o: number; h: number; l: number; c: number; v: number | null }
export interface WorkerCombo { broker: string; investor: string; board: string; gross: number; net: Float64Array }
export type WorkerAnswer =
  | { id: number; type: 'price'; rows: PriceRow[] }
  | { id: number; type: 'broker' | 'brokerAll'; combos: WorkerCombo[]; flowFrom: number; dates: string[]; rows: BrokerRow[][] }
  | { id: number; type: 'events'; rows: Record<string, unknown>[] }
  | { id: number; type: 'error'; message: string; status: number };

interface Columnar { columns: string[]; [k: string]: any }

/* gzip JSON from a presigned URL; a body the browser already inflated (Content-Encoding) is read as is */
export async function download(url: string): Promise<Columnar> {
  const res = await fetch(url, { credentials:'omit' });
  if (!res.ok) throw Object.assign(new Error(`A data file could not be downloaded (${res.status}).`), { status:res.status });
  const bytes = new Uint8Array(await res.arrayBuffer());
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
  let flowFrom = N;
  for (const doc of docs) {
    const { d, b, i: inv, m, bv, sv, bl, sl } = doc;
    for (let k = 0; k < d.length; k++) {
      const brd = board(m[k]);
      const row: BrokerRow = [b[k], inv[k], brd, bv[k] || 0, sv[k] || 0, bl[k] || 0, sl[k] || 0];
      (byDate.get(d[k]) || byDate.set(d[k], []).get(d[k])!).push(row);
      const i = idx.get(d[k]); if (i === undefined) continue;
      if (i < flowFrom) flowFrom = i;
      const key = `${row[0]}|${row[1]}|${brd}`;
      let c = combos.get(key);
      if (!c) combos.set(key, c = { broker:row[0], investor:row[1], board:brd, gross:0, net:new Float64Array(N) });
      c.net[i] += row[3] - row[4]; c.gross += row[3] + row[4];
    }
  }
  const last = [...byDate.keys()].sort().slice(-30);
  return { combos:[...combos.values()], flowFrom, dates:last, rows:last.map(t => byDate.get(t)!) };
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
  };
}
