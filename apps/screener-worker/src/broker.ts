/* Broker data for the Screener, one file per trade date (EXEC-SCREENER-FLOW-CANDLES P4 under EXEC-BROKER-DELTA; user
   2026-11-07: per-date files, "hari baru = satu file baru, tanggal berubah = file tanggal itu diganti", one active copy
   per stock-date; compact file code; worker limits unchanged; K1 window 60 sessions). The contract between the
   publisher and this worker is verification/screener/P4_BROKER_DAYS.md (section 1 the file, section 3 the worker). P5
   (the flow computation) reads what this loads; nothing here computes an indicator.

   - The window (brokerWindow): the index entries named broker-YYYY-MM-DD (the Feature 05 trade_date), the newest
     BROKER_DAY_SESSIONS (60) by date. They are optional: a publication without them loads as before. The refresh plans
     which of them it loads (refresh.ts brokerPlan: carried, cached, downloaded newest first within the budget).
   - The document (decodeBrokerDay), after sha256 and size (TerminalClient.file, inflateVerified): name and date equal
     the index name; columns exactly BROKER_COLUMNS; every column the same length; the tickers' rows add up to it and to
     check.rows; b, i, m indices inside brokers (sorted, distinct), investor_types and boards (the fixed lists of the
     table's CHECK); bv, sv, bl, sl numbers; bf, sf whole numbers or null; check.bv and check.sv recomputed within
     CHECK_TOLERANCE (1e-6) relative. A failure is DATA_INTEGRITY naming the file, the refresh's failure as for a Phase 1
     file (the previous snapshot keeps serving, REFRESH_FAILED with the code).
   - The store (buildBrokerStore), once per replica in SharedArrayBuffer columns: per ticker of the price snapshot, its
     rows of every loaded date, ordered by date then file order; D (Uint16, into `dates`, the loaded dates ascending),
     B (Uint16, into `brokers`, the union of the loaded files' brokers), I and M (Uint8, into INVESTOR_TYPES and
     BOARDS), BV SV BL SL BF SF (Float64; a null bf or sf as NaN); ticker j's rows are [offsets[j], offsets[j + 1]).
     A ticker of a broker file that the price snapshot does not have is not loaded (counted: the day's `dropped`).
     A day the held snapshot already loaded with the same sha256 is carried from its store, not read again, when reading
     the file again would give the same rows (nothing was dropped from it, or the price file is the same): so a refresh
     reads only new or changed days, and a window larger than one refresh's download budget fills over follow-up
     refreshes even without a disk cache.
   - versions.flow_data = sha256 over the sorted name:sha256 of the loaded days (null when none); data.flow_through the
     newest loaded date; data.broker_window {first, last, sessions, complete} (brokerWindowOf).
   - brokerRowsOf: one ticker's rows in a date range as typed views (no copy), read through ThreadSnapshot.brokerRows. */
import crypto from 'node:crypto';
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { isIsoDate } from '../../edge-bff/backtest/src/core/signals.ts';
import type { BrokerWindow } from '../../edge-bff/screener/src/core/contract.ts';

/** K1 (user 2026-11-07): the broker days the Screener holds, the newest of the index by date. */
export const BROKER_DAY_SESSIONS = 60;
export const BROKER_COLUMNS = ['b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'] as const;
/** the fixed tables of the file (Feature 05's CHECK constraints), in the file's order */
export const INVESTOR_TYPES = ['Domestic', 'Foreign'] as const;
export const BOARDS = ['Regular', 'Nego', 'Tunai'] as const;
/** check.bv and check.sv against the sums the reader recomputes (relative) */
export const CHECK_TOLERANCE = 1e-6;
const DAY_NAME = /^broker-(\d{4}-\d{2}-\d{2})$/;
const TICKER = /^[A-Z0-9]{1,12}$/;
const MAX_INDEX = 65535;                        // D and B are Uint16

/** A broker day's date, or null for a name that is not broker-YYYY-MM-DD with a real date. */
export function brokerDayDate(name: string): string | null {
  const m = DAY_NAME.exec(name);
  return m && isIsoDate(m[1]) ? m[1] : null;
}

/** One broker day of the publication's index. */
export interface WindowDay { name: string; date: string; entry: { sha256: string; bytes: number } }
/** The window: the index entries named broker-YYYY-MM-DD, the newest BROKER_DAY_SESSIONS by date, newest first. */
export function brokerWindow<E extends { sha256: string; bytes: number }>(index: Record<string, E> | null): (WindowDay & { entry: E })[] {
  const out: (WindowDay & { entry: E })[] = [];
  for (const [name, entry] of Object.entries(index ?? {})) { const date = brokerDayDate(name); if (date) out.push({ name, date, entry }) }
  return out.sort((a, b) => a.date < b.date ? 1 : a.date > b.date ? -1 : 0).slice(0, BROKER_DAY_SESSIONS);
}

/* ---- the document ---------------------------------------------------------------------------------------------- */

/** One decoded broker day: the file's rows as typed columns (the parsed JSON is not kept), its tables and its tickers. */
export interface BrokerDay {
  name: string; date: string; sha256: string; rows: number;
  brokers: string[];
  gap: [string, number][];                         // [ticker, index into BOARDS]
  tickers: string[]; starts: Int32Array;           // tickers[k]'s rows are [starts[k], starts[k + 1])
  b: Uint16Array; i: Uint8Array; m: Uint8Array;
  bv: Float64Array; sv: Float64Array; bl: Float64Array; sl: Float64Array; bf: Float64Array; sf: Float64Array;
}
const sameList = (a: unknown, b: readonly string[]) => Array.isArray(a) && a.length === b.length && b.every((x, k) => a[k] === x);
const near = (a: number, b: number) => a === b || Math.abs(a - b) <= CHECK_TOLERANCE * Math.max(Math.abs(a), Math.abs(b));

/** The broker day file `name` (sha256 already verified), checked by the rules of the header; DATA_INTEGRITY naming the
    file and the rule otherwise. */
export function decodeBrokerDay(doc: Columnar, name: string, sha256: string): BrokerDay {
  const fail = (why: string) => new DataError('DATA_INTEGRITY', `The ${name} broker file ${why}.`, name);
  const date = brokerDayDate(name);
  if (!date) throw fail('is not named broker-YYYY-MM-DD');
  if (!doc || typeof doc !== 'object') throw fail('is not a JSON object');
  if (doc.dataset !== undefined && doc.dataset !== 'xsection') throw fail(`is a ${String(doc.dataset)} file, not xsection`);
  if (doc.name !== name || doc.date !== date) throw fail(`names ${JSON.stringify(doc.name)} of ${JSON.stringify(doc.date)}; the index names ${name} of ${date}`);
  if (!sameList(doc.columns, BROKER_COLUMNS)) throw fail(`has the columns ${JSON.stringify(doc.columns)?.slice(0, 120)}, not ${BROKER_COLUMNS.join(', ')}`);
  const col = BROKER_COLUMNS.map(c => doc[c]) as unknown[][];
  col.forEach((a, k) => { if (!Array.isArray(a)) throw fail(`has no column ${BROKER_COLUMNS[k]}`) });
  const n = col[0].length;
  col.forEach((a, k) => { if (a.length !== n) throw fail(`has ${a.length} values in column ${BROKER_COLUMNS[k]} and ${n} in b`) });
  // the tables: brokers sorted and distinct; investor types and boards the fixed lists
  const brokers = doc.brokers as unknown[];
  if (!Array.isArray(brokers) || brokers.length > MAX_INDEX || !brokers.every((x, k) => typeof x === 'string' && x.length > 0 && (k === 0 || x > (brokers[k - 1] as string))))
    throw fail('has no sorted list of distinct broker codes');
  if (!sameList(doc.investor_types, INVESTOR_TYPES)) throw fail(`has investor_types ${JSON.stringify(doc.investor_types)?.slice(0, 80)}, not ${JSON.stringify(INVESTOR_TYPES)}`);
  if (!sameList(doc.boards, BOARDS)) throw fail(`has boards ${JSON.stringify(doc.boards)?.slice(0, 80)}, not ${JSON.stringify(BOARDS)}`);
  // the tickers: in ticker order, each with its rows, adding up to the columns and to check.rows
  const list = doc.tickers as unknown[];
  if (!Array.isArray(list)) throw fail('has no tickers list');
  const tickers: string[] = new Array(list.length), starts = new Int32Array(list.length + 1);
  let total = 0;
  list.forEach((e: any, k) => {
    if (!e || typeof e.t !== 'string' || !TICKER.test(e.t) || !Number.isSafeInteger(e.rows) || e.rows < 1) throw fail(`has a tickers entry ${k + 1} that is not {t, rows}`);
    if (k && !(e.t > tickers[k - 1])) throw fail(`lists ${e.t} after ${tickers[k - 1]}, not in ticker order`);
    tickers[k] = e.t; starts[k] = total; total += e.rows;
  });
  starts[list.length] = total;
  if (total !== n) throw fail(`counts ${total} rows in its tickers list; its columns hold ${n}`);
  const check = doc.check as { rows?: unknown; bv?: unknown; sv?: unknown } | undefined;
  if (!check || typeof check !== 'object' || check.rows !== n) throw fail(`has check.rows ${JSON.stringify(check?.rows)}; its columns hold ${n}`);
  if (typeof check.bv !== 'number' || typeof check.sv !== 'number') throw fail('has no check.bv and check.sv numbers');
  // the rows
  const [B, I, M, BV, SV, BL, SL, BF, SF] = col;
  const b = new Uint16Array(n), i = new Uint8Array(n), m = new Uint8Array(n);
  const bv = new Float64Array(n), sv = new Float64Array(n), bl = new Float64Array(n), sl = new Float64Array(n), bf = new Float64Array(n), sf = new Float64Array(n);
  const index = (v: unknown, size: number) => typeof v === 'number' && Number.isInteger(v) && v >= 0 && v < size;
  const value = (v: unknown, c: string, r: number) => { if (typeof v !== 'number' || !Number.isFinite(v)) throw fail(`has ${c} ${JSON.stringify(v)} in row ${r + 1}, not a number`); return v };
  const count = (v: unknown, c: string, r: number) => {
    if (v === null) return NaN;
    if (typeof v !== 'number' || !Number.isSafeInteger(v)) throw fail(`has ${c} ${JSON.stringify(v)} in row ${r + 1}, not a whole number or null`);
    return v;
  };
  let sumBv = 0, sumSv = 0;
  for (let r = 0; r < n; r++) {
    if (!index(B[r], brokers.length)) throw fail(`has b ${JSON.stringify(B[r])} in row ${r + 1}, not an index into its ${brokers.length} brokers`);
    if (!index(I[r], INVESTOR_TYPES.length)) throw fail(`has i ${JSON.stringify(I[r])} in row ${r + 1}, not an index into investor_types`);
    if (!index(M[r], BOARDS.length)) throw fail(`has m ${JSON.stringify(M[r])} in row ${r + 1}, not an index into boards`);
    b[r] = B[r] as number; i[r] = I[r] as number; m[r] = M[r] as number;
    bv[r] = value(BV[r], 'bv', r); sv[r] = value(SV[r], 'sv', r); bl[r] = value(BL[r], 'bl', r); sl[r] = value(SL[r], 'sl', r);
    bf[r] = count(BF[r], 'bf', r); sf[r] = count(SF[r], 'sf', r);
    sumBv += bv[r]; sumSv += sv[r];
  }
  if (!near(sumBv, check.bv)) throw fail(`has check.bv ${check.bv}; its rows add up to ${sumBv}`);
  if (!near(sumSv, check.sv)) throw fail(`has check.sv ${check.sv}; its rows add up to ${sumSv}`);
  // the [ticker, board] pairs whose source_balance_gap is true (as broker_doc)
  const gap: [string, number][] = [];
  if (doc.gap !== undefined) {
    if (!Array.isArray(doc.gap)) throw fail('has a gap that is not a list');
    for (const g of doc.gap as unknown[]) {
      const k = Array.isArray(g) && g.length === 2 && typeof g[0] === 'string' && TICKER.test(g[0]) ? (BOARDS as readonly unknown[]).indexOf(g[1]) : -1;
      if (k < 0) throw fail(`has a gap entry ${JSON.stringify(g)?.slice(0, 60)} that is not [ticker, board]`);
      gap.push([(g as string[])[0], k]);
    }
  }
  return { name, date, sha256, rows: n, brokers: brokers as string[], gap, tickers, starts, b, i, m, bv, sv, bl, sl, bf, sf };
}

/* ---- the store --------------------------------------------------------------------------------------------------- */

/** One loaded day as the store keeps it (aligned with `dates`). */
export interface BrokerDayMeta {
  name: string; date: string; sha256: string;
  file_rows: number;                               // the file's rows
  rows: number;                                    // the rows stored (those of tickers the price snapshot has)
  dropped: string[];                               // its tickers the price snapshot does not have (not loaded)
  brokers: string[]; gap: [string, number][];      // the file's broker table and gap pairs
}
/** The broker rows of one snapshot (header). Structured-cloneable: the columns are shared, not copied. */
export interface BrokerStore {
  tickers: string[];                               // the price snapshot's tickers; offsets are per ticker of this list
  dates: string[];                                 // the loaded dates, ascending (D indexes it)
  days: BrokerDayMeta[];                           // aligned with dates
  brokers: string[];                               // the union of the loaded days' brokers, sorted (B indexes it)
  missing: number;                                 // days of the window not loaded (they wait for a follow-up refresh)
  offsets: Int32Array;
  D: Uint16Array; B: Uint16Array; I: Uint8Array; M: Uint8Array;
  BV: Float64Array; SV: Float64Array; BL: Float64Array; SL: Float64Array; BF: Float64Array; SF: Float64Array;
}
export interface BrokerStats { read: number; carried: number; rows: number; dropped_tickers: number; dropped_rows: number; store_bytes: number }

const shared = <T extends Float64Array | Int32Array | Uint16Array | Uint8Array>(Kind: { new(b: SharedArrayBuffer): T; BYTES_PER_ELEMENT: number }, n: number): T =>
  new Kind(new SharedArrayBuffer(Math.max(1, n) * Kind.BYTES_PER_ELEMENT));
/** The bytes of a store's columns and offsets (its memory per replica, the tables aside). */
export const storeBytes = (s: BrokerStore): number =>
  [s.offsets, s.D, s.B, s.I, s.M, s.BV, s.SV, s.BL, s.SL, s.BF, s.SF].reduce((n, a) => n + a.byteLength, 0);

/** First position in [a, b) of the ascending `xs` whose value is >= v (upper: > v). */
function bound(xs: ArrayLike<number>, v: number, a: number, b: number, upper: boolean): number {
  while (a < b) { const h = (a + b) >>> 1; if (upper ? xs[h] <= v : xs[h] < v) a = h + 1; else b = h }
  return a;
}
function boundOf(xs: readonly string[], v: string, upper: boolean): number {
  let a = 0, b = xs.length;
  while (a < b) { const h = (a + b) >>> 1; if (upper ? xs[h] <= v : xs[h] < v) a = h + 1; else b = h }
  return a;
}

/** The store of a snapshot whose price file has `tickers` (in its order): the days read now and the days carried from
    the held snapshot's store (`carry.names`, each in `carry.from` with the sha256 the refresh compared), `missing` the
    window's days left for a follow-up refresh. */
export function buildBrokerStore(tickers: readonly string[], read: readonly BrokerDay[], carry: { from: BrokerStore; names: readonly string[] } | null, missing = 0): { store: BrokerStore; stats: BrokerStats } {
  type Source = { date: string; name: string; sha256: string; day: BrokerDay | null; old: number; meta: BrokerDayMeta | null };
  const sources: Source[] = read.map(d => ({ date: d.date, name: d.name, sha256: d.sha256, day: d, old: -1, meta: null }));
  for (const name of carry?.names ?? []) {
    const from = carry!.from, k = from.days.findIndex(d => d.name === name);
    if (k < 0) throw new Error(`broker store: ${name} is not in the held store`);
    sources.push({ date: from.days[k].date, name, sha256: from.days[k].sha256, day: null, old: k, meta: from.days[k] });
  }
  sources.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0);
  for (let k = 1; k < sources.length; k++) if (sources[k].date === sources[k - 1].date) throw new Error(`broker store: ${sources[k].date} twice`);
  if (sources.length > MAX_INDEX) throw new Error('broker store: too many dates');
  // one broker table, the union of the loaded files' tables
  const union = new Set<string>();
  for (const s of sources) for (const x of s.day ? s.day.brokers : s.meta!.brokers) union.add(x);
  const brokers = [...union].sort();
  if (brokers.length > MAX_INDEX) throw new Error('broker store: too many brokers');
  const brokerId = new Map(brokers.map((x, k) => [x, k]));
  const remap = (codes: readonly string[]) => Uint16Array.from(codes, x => brokerId.get(x) ?? 0);
  const fromMap = carry ? remap(carry.from.brokers) : new Uint16Array(0);
  const position = new Map(tickers.map((t, j) => [t, j]));
  const T = tickers.length;
  /** each source's runs: (ticker j of `tickers`, first row, end row) in the source's columns; the others dropped */
  const runs = sources.map(s => {
    const out: [number, number, number][] = [], dropped: string[] = [];
    const add = (t: string, a: number, b: number) => {
      if (b <= a) return;
      const j = position.get(t);
      if (j === undefined) dropped.push(t); else out.push([j, a, b]);
    };
    if (s.day) s.day.tickers.forEach((t, k) => add(t, s.day!.starts[k], s.day!.starts[k + 1]));
    else {
      const f = carry!.from;
      for (let jo = 0; jo < f.tickers.length; jo++) {
        const a = f.offsets[jo], b = f.offsets[jo + 1];
        add(f.tickers[jo], bound(f.D, s.old, a, b, false), bound(f.D, s.old, a, b, true));
      }
      // tickers dropped from it before stay dropped (the refresh carries such a day only on the same price file)
      for (const t of s.meta!.dropped) if (!position.has(t) && !dropped.includes(t)) dropped.push(t);
    }
    return { out, dropped: dropped.sort() };
  });
  // offsets: per ticker, its rows of every date
  const counts = new Int32Array(T);
  for (const r of runs) for (const [j, a, b] of r.out) counts[j] += b - a;
  const offsets = shared(Int32Array, T + 1);
  for (let j = 0; j < T; j++) offsets[j + 1] = offsets[j] + counts[j];
  const N = offsets[T];
  const D = shared(Uint16Array, N), B = shared(Uint16Array, N), I = shared(Uint8Array, N), M = shared(Uint8Array, N);
  const BV = shared(Float64Array, N), SV = shared(Float64Array, N), BL = shared(Float64Array, N), SL = shared(Float64Array, N), BF = shared(Float64Array, N), SF = shared(Float64Array, N);
  // date by date (ascending), so each ticker's rows end ordered by date, then by the file's order
  const at = Int32Array.from(offsets.subarray(0, T));
  const days: BrokerDayMeta[] = [];
  const droppedTickers = new Set<string>();
  let droppedRows = 0;
  sources.forEach((s, k) => {
    const r = runs[k];
    let rows = 0;
    if (s.day) {
      const d = s.day, map = remap(d.brokers);
      for (const [j, a, b] of r.out) {
        let w = at[j];
        for (let x = a; x < b; x++, w++) {
          D[w] = k; B[w] = map[d.b[x]]; I[w] = d.i[x]; M[w] = d.m[x];
          BV[w] = d.bv[x]; SV[w] = d.sv[x]; BL[w] = d.bl[x]; SL[w] = d.sl[x]; BF[w] = d.bf[x]; SF[w] = d.sf[x];
        }
        rows += b - a; at[j] = w;
      }
    } else {
      const f = carry!.from;
      for (const [j, a, b] of r.out) {
        let w = at[j];
        for (let x = a; x < b; x++, w++) {
          D[w] = k; B[w] = fromMap[f.B[x]]; I[w] = f.I[x]; M[w] = f.M[x];
          BV[w] = f.BV[x]; SV[w] = f.SV[x]; BL[w] = f.BL[x]; SL[w] = f.SL[x]; BF[w] = f.BF[x]; SF[w] = f.SF[x];
        }
        rows += b - a; at[j] = w;
      }
    }
    const fileRows = s.day ? s.day.rows : s.meta!.file_rows;
    for (const t of r.dropped) droppedTickers.add(t);
    droppedRows += fileRows - rows;                 // the file's rows not stored: those of the dropped tickers
    days.push({ name: s.name, date: s.date, sha256: s.sha256, file_rows: fileRows, rows,
      dropped: r.dropped, brokers: s.day ? s.day.brokers : s.meta!.brokers, gap: s.day ? s.day.gap : s.meta!.gap });
  });
  const store: BrokerStore = { tickers: [...tickers], dates: sources.map(s => s.date), days, brokers, missing, offsets, D, B, I, M, BV, SV, BL, SL, BF, SF };
  return { store, stats: { read: read.length, carried: carry?.names.length ?? 0, rows: N, dropped_tickers: droppedTickers.size, dropped_rows: droppedRows, store_bytes: storeBytes(store) } };
}

/** versions.flow_data: sha256 over the sorted name:sha256 of the loaded days; null when none is loaded. */
export function brokerFlowData(days: readonly { name: string; sha256: string }[]): string | null {
  if (!days.length) return null;
  return crypto.createHash('sha256').update(days.map(d => `${d.name}:${d.sha256}`).sort().join('\n')).digest('hex');
}
/** data.broker_window: the loaded days and whether the window is complete. */
export const brokerWindowOf = (s: Pick<BrokerStore, 'dates' | 'missing'>): BrokerWindow =>
  ({ first: s.dates[0] ?? null, last: s.dates[s.dates.length - 1] ?? null, sessions: s.dates.length, complete: s.missing === 0 });

/* ---- reading ------------------------------------------------------------------------------------------------------ */

/** One ticker's broker rows in a date range (ThreadSnapshot.brokerRows): views into the store's columns, ordered by
    date then file order; D indexes `dates`, B `brokers`, I `investor_types`, M `boards`; a null bf or sf is NaN. */
export interface BrokerRows {
  ticker: string; rows: number;
  dates: readonly string[]; brokers: readonly string[]; investor_types: readonly string[]; boards: readonly string[];
  D: Uint16Array; B: Uint16Array; I: Uint8Array; M: Uint8Array;
  BV: Float64Array; SV: Float64Array; BL: Float64Array; SL: Float64Array; BF: Float64Array; SF: Float64Array;
  /** the ticker's [date, board] pairs whose source_balance_gap is true, in the range */
  gaps: { d: string; m: string }[];
}
/** Ticker j's rows from `from` to `to` (ISO dates, both included; null = open). */
export function brokerRowsOf(s: BrokerStore, j: number, from: string | null = null, to: string | null = null): BrokerRows {
  const k0 = from === null ? 0 : boundOf(s.dates, from, false), k1 = to === null ? s.dates.length : boundOf(s.dates, to, true);
  const a0 = s.offsets[j], b0 = s.offsets[j + 1];
  const a = k1 > k0 ? bound(s.D, k0, a0, b0, false) : a0, b = k1 > k0 ? bound(s.D, k1 - 1, a, b0, true) : a0;
  const ticker = s.tickers[j], gaps: BrokerRows['gaps'] = [];
  for (let k = k0; k < k1; k++) for (const [t, m] of s.days[k].gap) if (t === ticker) gaps.push({ d: s.dates[k], m: BOARDS[m] });
  return {
    ticker, rows: b - a, dates: s.dates, brokers: s.brokers, investor_types: INVESTOR_TYPES, boards: BOARDS, gaps,
    D: s.D.subarray(a, b), B: s.B.subarray(a, b), I: s.I.subarray(a, b), M: s.M.subarray(a, b),
    BV: s.BV.subarray(a, b), SV: s.SV.subarray(a, b), BL: s.BL.subarray(a, b), SL: s.SL.subarray(a, b), BF: s.BF.subarray(a, b), SF: s.SF.subarray(a, b),
  };
}
