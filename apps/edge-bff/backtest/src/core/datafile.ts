/* The published market-data files (terminal-publisher -> bucket terminal-display -> terminal-api presigned URLs)
   decoded for the backtest. One module for the worker and the page, with the Terminal's reading rules
   (edge-bff/terminal/src/data/worker.ts priceRows, brokerData), so the chart and the backtest see the same bars, and the
   checks a backtest needs on top of them (CONTRACT.md section 2): a file is used only when its bytes match the
   manifest's sha256 and size; dates must be strictly increasing after the files are merged; anything else the
   publisher cannot have written is DATA_INTEGRITY, never repaired.

   File format (apps/terminal-publisher/publisher.py `encode`): gzip (level 9, mtime 0) of compact JSON, one columnar
   document {schema_version: 1, dataset, ticker, year, units, columns, <column>: [...]} per file:
     price/{ticker}/{year}, pack/{ticker}/price          dataset price | price-pack       d,o,h,l,c,v (v null: an index)
     broker/{ticker}/{year}, pack/{ticker}/broker-archive dataset broker | broker-archive d,b,i,m,bv,sv,bl,sl; gap
     events/{ticker}/all                                 dataset events                   EVENT_COLUMNS (d, role, family, type, ...)
     ref/tickers, ref/brokers                            no dataset                       ticker,name,type,sector / code,name,type
   Broker units: bv, sv in IDR; bl, sl lots (verification/backtest/FLOW_DATA_CHECK.md). The index is IHSG (the one
   'index' row of IDX_Stock_Universe, verification/terminal_api/INTEGRITY.md; the publisher codes no ticker).
   Pure module: crypto.subtle, DecompressionStream, TextDecoder/TextEncoder and Blob only (Node 22 and browsers). */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';

export const SCHEMA_VERSION = 1;                       // publisher.py SCHEMA_VERSION
export const INDEX_TICKER = 'IHSG';

export type DataCode = 'DATA_MISSING' | 'DATA_INTEGRITY' | 'DATA_UNAVAILABLE';
/** Market data that is not there (DATA_MISSING), not what the publisher wrote (DATA_INTEGRITY) or could not be fetched
    now (DATA_UNAVAILABLE). edge-bff answers 424 with the code (CONTRACT.md section 11). */
export class DataError extends Error {
  code: DataCode; field?: string; details?: Record<string, unknown>;
  constructor(code: DataCode, message: string, field?: string, details?: Record<string, unknown>) {
    super(message); this.name = 'DataError'; this.code = code; this.field = field; this.details = details;
  }
}
const integrity = (message: string, field?: string) => new DataError('DATA_INTEGRITY', message, field);

/** One file as terminal-api /bundle names it (year: a yearly file; pack: 'price' | 'broker-archive'). */
export interface FileEntry { url: string; sha256: string; bytes: number; rows?: number; year?: number; pack?: string }
/** A decoded columnar document: every name in `columns` is an array of the same length. */
export interface Columnar { schema_version?: number; columns: string[]; [column: string]: unknown }

/* ---- bytes -> document ------------------------------------------------------------------------------------- */
const hex = (buf: ArrayBuffer) => { let s = ''; for (const b of new Uint8Array(buf)) s += b.toString(16).padStart(2, '0'); return s };
export const sha256Bytes = async (raw: Uint8Array): Promise<string> => hex(await crypto.subtle.digest('SHA-256', raw as BufferSource));

async function gunzip(raw: Uint8Array): Promise<Uint8Array> {
  const reader = new Blob([raw as BlobPart]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  const parts: Uint8Array[] = []; let n = 0;
  for (;;) { const { done, value } = await reader.read(); if (done) break; parts.push(value); n += value.byteLength }
  const out = new Uint8Array(n); let at = 0;
  for (const p of parts) { out.set(p, at); at += p.byteLength }
  return out;
}

/** gzip JSON bytes -> a checked columnar document, without a hash check. Only for a file no manifest describes
    (terminal-api /reference answers a URL without sha256); data files go through inflateVerified. */
export async function decodeColumnar(raw: Uint8Array, what = 'file'): Promise<Columnar> {
  if (!(raw.byteLength >= 2 && raw[0] === 0x1f && raw[1] === 0x8b)) throw integrity(`${what} is not a gzip file.`);
  let doc: unknown;
  try { doc = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(await gunzip(raw))) }
  catch { throw integrity(`${what} is not valid gzip JSON.`) }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) throw integrity(`${what} is not a JSON object.`);
  const d = doc as Columnar;
  if (d.schema_version !== undefined && d.schema_version !== SCHEMA_VERSION)
    throw integrity(`${what} has schema_version ${JSON.stringify(d.schema_version)}; this reader knows ${SCHEMA_VERSION}.`);
  if (!Array.isArray(d.columns) || !d.columns.length || !d.columns.every(c => typeof c === 'string') || new Set(d.columns).size !== d.columns.length)
    throw integrity(`${what} has no valid column list.`);
  let n = -1;
  for (const c of d.columns) {
    const a = d[c];
    if (!Array.isArray(a)) throw integrity(`${what}: column ${c} is missing.`);
    if (n >= 0 && a.length !== n) throw integrity(`${what}: column ${c} has ${a.length} values, ${d.columns[0]} has ${n}.`);
    n = a.length;
  }
  return d;
}

/** A downloaded file -> its document, after the bytes are checked against the manifest's size and sha256 (a cached or
    downloaded file that does not match is DATA_INTEGRITY, never used). */
export async function inflateVerified(raw: Uint8Array, f: { sha256: string; bytes: number }, what = 'file'): Promise<Columnar> {
  if (raw.byteLength !== f.bytes) throw integrity(`${what} has ${raw.byteLength} bytes; the manifest says ${f.bytes}.`);
  const sha = await sha256Bytes(raw);
  if (sha !== String(f.sha256).toLowerCase()) throw integrity(`${what} does not match its manifest sha256.`);
  return decodeColumnar(raw, what);
}

/* ---- shared checks ------------------------------------------------------------------------------------------ */
const ISO = /^\d{4}-\d{2}-\d{2}$/;
/** A memo of checked date strings (a broker year repeats each date ~100 times). */
function dateCheck(): (s: unknown) => boolean {
  const seen = new Map<string, boolean>();
  return s => {
    if (typeof s !== 'string') return false;
    let ok = seen.get(s);
    if (ok === undefined) {
      const t = ISO.test(s) ? Date.parse(`${s}T00:00:00Z`) : NaN;
      ok = Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === s;
      seen.set(s, ok);
    }
    return ok;
  };
}
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
function cols(doc: Columnar, names: readonly string[], what: string): unknown[][] {
  if (!doc || !Array.isArray(doc.columns)) throw integrity(`${what} is not a columnar document.`);
  return names.map(c => {
    if (!doc.columns.includes(c) || !Array.isArray(doc[c])) throw integrity(`${what}: column ${c} is missing.`);
    return doc[c] as unknown[];
  });
}
function kind(doc: Columnar, datasets: readonly string[], ticker: string | null, what: string): void {
  if (doc.dataset !== undefined && !datasets.includes(doc.dataset as string)) throw integrity(`${what} is a ${String(doc.dataset)} file, not ${datasets.join(' or ')}.`);
  if (ticker !== null && doc.ticker !== undefined && doc.ticker !== ticker) throw integrity(`${what} belongs to ${String(doc.ticker)}, not ${ticker}.`);
}
/** The documents in the order of their first date (a pack and yearly files may come in any order); their rows are then
    read as one sequence, which must be strictly increasing (price) or non-decreasing (broker) by date. */
const byFirstDate = <T extends { first: string }>(parts: T[]): T[] => parts.sort((a, b) => a.first < b.first ? -1 : a.first > b.first ? 1 : 0);

/* ---- price ---------------------------------------------------------------------------------------------------- */
export const PRICE_COLUMNS = ['d', 'o', 'h', 'l', 'c', 'v'] as const;
/** A ticker's published bars, as they are (no adjusted close). bars.T = dates; V is null where the file has no volume. */
export interface PriceSeries { ticker: string; dates: string[]; bars: Bars; dropped: number }

/** Price documents (the price pack or yearly files) -> the ticker's bars. As the Terminal's priceRows: a row without
    four finite prices (o, h, l, c) is dropped (counted in `dropped`), v is kept as published (null stays null). On top:
    every date a real 'YYYY-MM-DD', v a number or null, and the merged rows strictly increasing by date (a date twice,
    within a file or across files, or out of order is DATA_INTEGRITY). No bar at all is DATA_MISSING. */
export function priceSeries(ticker: string, docs: Columnar[]): PriceSeries {
  const isDate = dateCheck();
  const parts = docs.map((doc, k) => {
    const what = `${ticker} price file ${k + 1}`;
    kind(doc, ['price', 'price-pack'], ticker, what);
    const [d, o, h, l, c, v] = cols(doc, PRICE_COLUMNS, what);
    return { what, first: d.length ? String(d[0]) : '', d, o, h, l, c, v };
  }).filter(p => p.d.length);
  const dates: string[] = [], O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: (number | null)[] = [];
  let dropped = 0, prev = '';
  for (const p of byFirstDate(parts)) for (let k = 0; k < p.d.length; k++) {
    const day = p.d[k];
    if (!isDate(day)) throw integrity(`${p.what}: ${JSON.stringify(day)} is not a date.`, ticker);
    if (prev && !((day as string) > prev))
      throw integrity(`${ticker}: price date ${day as string} ${day === prev ? 'appears twice' : `comes after ${prev}`} in the published files.`, ticker);
    prev = day as string;
    const vol = p.v[k];
    if (vol !== null && !fin(vol)) throw integrity(`${p.what}: the volume of ${prev} is ${JSON.stringify(vol)}, not a number or null.`, ticker);
    const ohlc = [p.o[k], p.h[k], p.l[k], p.c[k]];
    if (!ohlc.every(fin)) { dropped++; continue }
    dates.push(prev); O.push(ohlc[0] as number); H.push(ohlc[1] as number); L.push(ohlc[2] as number); C.push(ohlc[3] as number); V.push(vol as number | null);
  }
  if (!dates.length) throw new DataError('DATA_MISSING', `No price bar is published for ${ticker}.`, ticker);
  return { ticker, dates, bars: { O, H, L, C, V, T: dates }, dropped };
}

/* ---- broker --------------------------------------------------------------------------------------------------- */
export const BROKER_COLUMNS = ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'] as const;
/* the values Feature 05 allows (CHECK constraints of feature_05_foreign_domestic_broker_detail) and the only ones the
   published files hold (FLOW_DATA_CHECK.md); the Terminal reads investor and board by pattern (flow.ts normInvestor,
   worker.ts board), so a value outside them would be read differently by its live and its manual path: refused */
export const INVESTORS = ['Foreign', 'Domestic'] as const;
export const BOARDS = ['Regular', 'Nego', 'Tunai'] as const;
/** One broker row: date, broker code, investor type (Foreign/Domestic, the source investor identity), market board
    (Regular/Nego/Tunai), buy and sell value (IDR), buy and sell lots. */
export interface BrokerRow { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number }
/** A date and board where the source's buy and sell totals differ (publisher `gap`, source_balance_gap, ERRORS M157). */
export interface BrokerGap { d: string; m: string }

/** Broker documents (the broker archive pack and yearly files) -> rows ordered by date. Checked: dates, a non-empty
    broker code, investor and board among the Feature 05 values, four finite values >= 0 (Feature 05 CHECK), dates
    non-decreasing within and across files, and one row per (date, broker, investor, board) (the Feature 05 key; a row
    in two files, e.g. a stale archive overlapping a yearly file, is DATA_INTEGRITY, where the Terminal would add it
    twice). All documents must belong to one ticker. */
export function brokerRows(docs: Columnar[]): BrokerRow[] {
  const isDate = dateCheck(), keys = new Set<string>(), owners = new Set<unknown>();
  const parts = docs.map((doc, k) => {
    const what = `broker file ${k + 1}${doc && typeof doc.ticker === 'string' ? ` of ${doc.ticker}` : ''}`;
    kind(doc, ['broker', 'broker-archive'], null, what);
    if (doc.ticker !== undefined) owners.add(doc.ticker);
    return { what, first: Array.isArray(doc.d) && doc.d.length ? String(doc.d[0]) : '', c: cols(doc, BROKER_COLUMNS, what) };
  }).filter(p => p.c[0].length);
  if (owners.size > 1) throw integrity(`The broker files belong to different tickers (${[...owners].join(', ')}).`);
  const out: BrokerRow[] = [];
  let prev = '';
  for (const p of byFirstDate(parts)) {
    const [d, b, i, m, bv, sv, bl, sl] = p.c;
    for (let k = 0; k < d.length; k++) {
      const day = d[k], at = () => `${p.what}, row ${k + 1}`;
      if (!isDate(day)) throw integrity(`${at()}: ${JSON.stringify(day)} is not a date.`);
      if ((day as string) < prev) throw integrity(`${p.what}: broker date ${day as string} comes after ${prev}.`);
      prev = day as string;
      if (typeof b[k] !== 'string' || !b[k]) throw integrity(`${at()}: no broker code.`);
      if (!(INVESTORS as readonly unknown[]).includes(i[k])) throw integrity(`${at()}: investor type ${JSON.stringify(i[k])} is not ${INVESTORS.join(' or ')}.`);
      if (!(BOARDS as readonly unknown[]).includes(m[k])) throw integrity(`${at()}: board ${JSON.stringify(m[k])} is not ${BOARDS.join(', ')}.`);
      const v = [bv[k], sv[k], bl[k], sl[k]];
      if (!v.every(x => fin(x) && x >= 0)) throw integrity(`${at()}: buy/sell value and lots must be numbers of at least 0.`);
      const key = `${prev}|${b[k]}|${i[k]}|${m[k]}`;
      if (keys.has(key)) throw integrity(`${p.what}: the broker row ${key} appears twice in the published files.`);
      keys.add(key);
      out.push({ d: prev, b: b[k] as string, i: i[k] as string, m: m[k] as string, bv: v[0] as number, sv: v[1] as number, bl: v[2] as number, sl: v[3] as number });
    }
  }
  return out;
}

/** The publisher's gap markers of broker documents ([[date, board], ...]); a document without `gap` has none. */
export function brokerGaps(docs: Columnar[]): BrokerGap[] {
  const isDate = dateCheck(), out: BrokerGap[] = [];
  docs.forEach((doc, k) => {
    if (doc.gap === undefined) return;
    if (!Array.isArray(doc.gap)) throw integrity(`broker file ${k + 1}: gap is not a list.`);
    for (const g of doc.gap) {
      if (!Array.isArray(g) || g.length !== 2 || !isDate(g[0]) || !(BOARDS as readonly unknown[]).includes(g[1]))
        throw integrity(`broker file ${k + 1}: gap entry ${JSON.stringify(g)} is not [date, board].`);
      out.push({ d: g[0], m: g[1] });
    }
  });
  return out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : 0);
}

/* ---- events --------------------------------------------------------------------------------------------------- */
/* Corporate actions that change the share count, so the published history is back-adjusted across them (CONTRACT
   D-K4) and a trade held across one is flagged: idx_event_annotation event_type values (stockbit_corporate_action
   CHECK; stockbit_events.py CORP_TYPES annotates each of them on its ex date, role EX_DATE). STOCK_DIVIDEND (shares
   paid as a dividend) is published but not titled by the publisher; it changes the share count like BONUS_SHARE.
   Not listed: DIVIDEND (cash), RUPS, TENDER_OFFER, WARRANT, PUBLIC_EXPOSE and INSIDER_TRANSACTION. */
export const PRICE_ACTION_TYPES: readonly string[] = ['STOCK_SPLIT', 'REVERSE_SPLIT', 'BONUS_SHARE', 'RIGHT_ISSUE', 'STOCK_DIVIDEND'];
export interface CorporateAction { date: string; type: string }

/** Events documents -> the price-affecting corporate actions (family CORPORATE_ACTION, type in PRICE_ACTION_TYPES) on
    their annotation date (the ex date), oldest first. */
export function corporateActions(docs: Columnar[]): CorporateAction[] {
  const isDate = dateCheck(), out: CorporateAction[] = [];
  docs.forEach((doc, k) => {
    const what = `events file ${k + 1}`;
    kind(doc, ['events'], null, what);
    const [d, family, type] = cols(doc, ['d', 'family', 'type'], what);
    for (let j = 0; j < d.length; j++) {
      if (family[j] !== 'CORPORATE_ACTION' || !PRICE_ACTION_TYPES.includes(type[j] as string)) continue;
      if (!isDate(d[j])) throw integrity(`${what}, row ${j + 1}: ${JSON.stringify(d[j])} is not a date.`);
      out.push({ date: d[j] as string, type: type[j] as string });
    }
  });
  return out.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
}

/* ---- alignment and version ------------------------------------------------------------------------------------ */
/** The value of the last date on or before each calendar date, null before the first date (the Terminal's alignTo:
    benchmark and compare lines on the result calendar, D-X2). `dates` strictly increasing (a PriceSeries). */
export function asOf(dates: readonly string[], values: ArrayLike<number | null>, calendar: readonly string[]): (number | null)[] {
  if (values.length !== dates.length) throw new RangeError(`asOf: ${dates.length} dates but ${values.length} values.`);
  return calendar.map(t => {
    let lo = 0, hi = dates.length - 1, j = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (dates[mid] <= t) { j = mid; lo = mid + 1 } else hi = mid - 1 }
    return j < 0 ? null : values[j] ?? null;
  });
}

/** CONTRACT.md section 2: data_version = lowercase hex sha256 of the UTF-8 text made of the distinct lines
    `ticker \t dataset \t file sha256` of every file a run read (dataset: price | broker | events, the /bundle name),
    sorted (JavaScript string order) and joined with '\n' (no trailing newline). */
export async function dataVersion(files: readonly { ticker: string; dataset: string; sha256: string }[]): Promise<string> {
  const lines = [...new Set(files.map(f => {
    const parts = [f.ticker, f.dataset, f.sha256];
    if (parts.some(s => typeof s !== 'string' || !s || /[\t\n]/.test(s))) throw new TypeError(`dataVersion: invalid file ${JSON.stringify(f)}.`);
    return parts.join('\t');
  }))].sort();
  return hex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(lines.join('\n')) as BufferSource));
}
