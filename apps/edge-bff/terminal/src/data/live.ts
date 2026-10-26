/* Live data: the pre-published files of the rack (bucket terminal-display) reached through EDGE's /api/terminal
   gateway (FRONTEND_HANDOFF.md). The page asks for presigned URLs and downloads the gzip JSON files itself.
   Everything is mapped into the reference page's own shapes (types.ts). */
import type { Bar, Combo, CompareSpec, Instrument, MarketData, MarketEvent, Point, VolumePoint } from './types';
import { brokerData, download, priceRows, rowsOf, type PriceRow, type WorkerAnswer } from './worker';

const API = '/api/terminal/v1';

export class TerminalError extends Error {
  constructor(message: string, readonly status = 0) { super(message) }
}

/* the compare list of the reference's Add Series panel, with its colours; offered when the ticker is published */
const COMPARE: CompareSpec[] = [
  { id:'ihsg', symbol:'IHSG', name:'Composite Index', color:'#0070f3' },
  { id:'bbca', symbol:'BBCA', name:'Bank Central Asia', color:'#7928ca' },
  { id:'bbri', symbol:'BBRI', name:'Bank Rakyat Indonesia', color:'#7c5cff' },
  { id:'bmri', symbol:'BMRI', name:'Bank Mandiri', color:'#f59e0b' },
  { id:'tlkm', symbol:'TLKM', name:'Telkom Indonesia', color:'#ef4444' },
  { id:'asii', symbol:'ASII', name:'Astra International', color:'#14b8a6' },
  { id:'unvr', symbol:'UNVR', name:'Unilever Indonesia', color:'#8b5cf6' },
  { id:'goto', symbol:'GOTO', name:'GoTo Gojek Tokopedia', color:'#10b981' },
  { id:'antm', symbol:'ANTM', name:'Aneka Tambang', color:'#06b6d4' },
  { id:'excl', symbol:'EXCL', name:'XL Axiata', color:'#ec4899' }
];

/* idx_event_annotation corporate actions → the reference's event types; the date role names the tooltip row */
const EVENT_TYPE: Record<string, string> = {
  DIVIDEND:'dividend', STOCK_SPLIT:'stocksplit', REVERSE_SPLIT:'reversesplit', RIGHT_ISSUE:'rightissue',
  BONUS_SHARE:'bonus', RUPS:'rups', TENDER_OFFER:'tenderoffer', WARRANT:'warrant'
};
const EVENT_TITLE: Record<string, string> = {
  dividend:'Dividend', stocksplit:'Stock split', reversesplit:'Reverse split', rightissue:'Rights issue',
  bonus:'Bonus shares', rups:'RUPS', tenderoffer:'Tender offer', warrant:'Warrant'
};
/* one detail value as the reference tooltip writes it (Rp 25 / share, 2.50%, 2026-08-28); null → Unavailable */
export const UNAVAILABLE = 'Unavailable';
/* U4 (user 2026-10-26: "format dd mmmm yyyy ... cukup dibagian label annotations", English): every ISO date inside an
   event label reads "03 December 2025", also inside a period ("… – …") or a meeting time */
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
export const longDates = (text: string) => text.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g,
  (all, y, m, d) => +m >= 1 && +m <= 12 ? `${d} ${MONTHS[+m - 1]} ${y}` : all);
export function detailText(value: unknown, kind: string): string {
  if (value === null || value === undefined || value === '') return UNAVAILABLE;
  if (typeof value !== 'number') return longDates(String(value));
  const idr = (n: number) => 'Rp ' + (Number.isInteger(n) ? n : +n.toFixed(2)).toLocaleString('en-US');
  if (kind === 'idr_per_share') return idr(value) + ' / share';
  if (kind === 'idr') return idr(value);
  if (kind === 'pct') return value.toFixed(2) + '%';
  if (kind === 'shares') return Math.round(value).toLocaleString('en-US');
  return String(value);
}
const roleLabel = (role: string) => role.toLowerCase().split('_').map((w, i) => i ? w : w[0].toUpperCase() + w.slice(1)).join(' ');

async function api(path: string, csrf: string, body?: unknown) {
  const res = await fetch(API + path, body === undefined ? { credentials:'same-origin' }
    : { method:'POST', credentials:'same-origin', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token':csrf }, body:JSON.stringify(body) });
  let data: any = null;
  try { data = await res.json() } catch(e) {}
  if (!res.ok) {
    const msg = data && (data.message || (data.error && (data.error.code || data.error)));
    throw new TerminalError(res.status === 401 ? 'Sign in to EDGE first, then open the Terminal tab again.'
      : res.status === 429 ? `Download limit reached: ${msg || 'try again later'}.`
      : `The terminal data service answered ${res.status}${msg ? ` (${msg})` : ''}.`, res.status);
  }
  return data;
}

async function session(): Promise<string> {
  const res = await fetch('/api/v1/auth/session', { credentials:'same-origin' });
  if (!res.ok) throw new TerminalError('Sign in to EDGE first, then open the Terminal tab again.', res.status);
  const data = await res.json();
  return data.csrf_token || '';
}

/* EXEC-TERMINAL-UI-1026 U6: one call gives every file of the displayed ticker (terminal-api /bundle) */
type Dataset = 'price' | 'broker' | 'events';
async function bundle(ticker: string, datasets: Dataset[], csrf: string) {
  const answer = await api('/bundle', csrf, { ticker, datasets });
  const urls = (name: Dataset) => (answer.datasets?.[name]?.files || []).map((f: any) => f.url as string);
  return { price:urls('price'), broker:urls('broker'), events:urls('events') };
}

/* U7: the files are downloaded, inflated and parsed by one Web Worker (worker.ts); its answers arrive in stages.
   Without Worker support the same functions run here. */
type BrokerAnswer = Omit<Extract<WorkerAnswer, { type:'broker' | 'brokerAll' }>, 'id' | 'type'>;
/* broker: the recent years (F5), brokerAll: the whole history, read after them */
interface Job { price: Promise<PriceRow[]>; broker: Promise<BrokerAnswer>; brokerAll: Promise<BrokerAnswer>; events: Promise<Record<string, unknown>[]> }
let worker: Worker | null = null, jobs = 0;
const waiting = new Map<number, Record<string, [(v: any) => void, (e: any) => void]>>();
function run(files: { price: string[]; broker: string[]; events: string[] }): Job {
  const stage = <T>() => { let ok!: (v: T) => void, no!: (e: any) => void; const p = new Promise<T>((a, b) => { ok = a; no = b }); p.catch(() => {}); return { p, ok, no } };
  const price = stage<PriceRow[]>(), broker = stage<any>(), brokerAll = stage<any>(), events = stage<Record<string, unknown>[]>();
  if (typeof Worker === 'undefined') {
    (async () => {
      const brokerDocs = Promise.all(files.broker.map(download)), eventDocs = Promise.all(files.events.map(download));
      const rows = priceRows(await Promise.all(files.price.map(download))); price.ok(rows);
      const all = brokerData(await brokerDocs, rows.map(r => r.d)); broker.ok(all); brokerAll.ok(all);
      events.ok((await eventDocs).flatMap(rowsOf));
    })().catch(e => [price, broker, brokerAll, events].forEach(s => s.no(e)));
    return { price:price.p, broker:broker.p, brokerAll:brokerAll.p, events:events.p };
  }
  if (!worker) {
    worker = new Worker(new URL('./worker.ts', import.meta.url));
    worker.onmessage = (e: MessageEvent<WorkerAnswer>) => {
      const w = waiting.get(e.data.id); if (!w) return;
      const { id, type, ...data } = e.data as any;
      if (type === 'error') {
        const err = new TerminalError(data.message, data.status);
        Object.values(w).forEach(([, no]) => no(err)); waiting.delete(id); return;
      }
      w[type][0](type === 'price' ? data.rows : type === 'events' ? data.rows : data);
      delete w[type]; if (!Object.keys(w).length) waiting.delete(id);
    };
  }
  const id = ++jobs;
  waiting.set(id, { price:[price.ok, price.no], broker:[broker.ok, broker.no], brokerAll:[brokerAll.ok, brokerAll.no], events:[events.ok, events.no] });
  worker.postMessage({ id, ...files });
  return { price:price.p, broker:broker.p, brokerAll:brokerAll.p, events:events.p };
}

async function prices(ticker: string, csrf: string) {
  return run(await bundle(ticker, ['price'], csrf)).price;
}

/* a series on the chart's sessions: the last close on or before each session (forward fill); sessions before its
   first close have no point */
function alignTo(dates: string[], rows: { d: string; c: number }[]): Point[] {
  const out: Point[] = []; let k = 0, last: number | null = null;
  for (const t of dates) {
    while (k < rows.length && rows[k].d <= t) { last = rows[k].c; k++ }
    if (last !== null) out.push({ time:t, value:last });
  }
  return out;
}

/* U5 (user 2026-10-26: "automatically load chart dan panel bawah.. lalu panel kiri dan kanan akan load kalau user
   buka/expand the panel"): the page draws as soon as the price is read; the broker data (Flow, Broker activity) and
   the events follow through `later`, IHSG (Statistics, Relative performance) only when that panel asks for it. */
export async function liveData(stored: string | null): Promise<MarketData> {
  const csrf = await session();
  const reference = async (name: string) => rowsOf(await download((await api(`/reference/${name}`, csrf)).url));
  /* the ticker list, the broker list and the files of the remembered ticker are asked for together */
  const tickersP = reference('tickers'), brokerRefP = reference('brokers');
  brokerRefP.catch(() => {});
  const guess = stored || 'MAPI';
  const guessP = bundle(guess, ['price', 'broker', 'events'], csrf);
  guessP.catch(() => {});
  const tickers = await tickersP as { ticker: string; name: string; type: string; sector: string | null }[];
  const known = new Set(tickers.map(t => t.ticker));
  const instruments: Instrument[] = tickers.map(t => [t.ticker, t.name || t.ticker, t.sector || (t.type === 'index' ? 'Index' : 'Other'), 0]);
  const SYMBOL = stored && known.has(stored) ? stored : known.has('MAPI') ? 'MAPI' : tickers[0].ticker;
  const job = run(SYMBOL === guess ? await guessP : await bundle(SYMBOL, ['price', 'broker', 'events'], csrf));

  const rows = await job.price;
  if (!rows.length) throw new TerminalError(`No price data is published for ${SYMBOL}.`);
  const ohlc: Bar[] = rows.map(r => ({ time:r.d, open:r.o, high:r.h, low:r.l, close:r.c }));
  const volume: VolumePoint[] = rows.map(r => ({ time:r.d, value:r.v ?? 0, color:r.c >= r.o ? 'rgba(0,150,109,.48)' : 'rgba(235,57,69,.48)' }));
  const lineData: Point[] = ohlc.map(b => ({ time:b.time, value:b.close }));
  const dates = ohlc.map(b => b.time), N = dates.length;

  /* IHSG for Statistics → Relative performance; sessions before its first close take its first close */
  let ihsgP: Promise<{ d: string; c: number }[]> | null = null;
  const ihsgRows = () => ihsgP ||= SYMBOL === 'IHSG' ? Promise.resolve(rows) : prices('IHSG', csrf);
  const loadIhsg = async (): Promise<Point[]> => {
    const aligned = alignTo(dates, await ihsgRows());
    const first = aligned.length ? aligned[0].value : NaN;
    return dates.map((t, i) => aligned[i - (N - aligned.length)] ?? { time:t, value:first });
  };

  /* broker files: Flow Timeline (net per broker × investor type × board) and Broker activity (last 30 sessions) */
  const brokerOf = async (stage: Promise<BrokerAnswer>) => {
    const b = await stage;
    const brokerTypes = new Map((await brokerRefP.catch(() => [])).map((r: any) => [r.code, r.type] as [string, string]));
    return {
      combos:b.combos.map(c => ({ ...c, tilt:0 })) as Combo[], flowFrom:b.flowFrom,
      broker:{ dates:b.dates, rows:(d: number) => b.rows[d] || [], label:SYMBOL,
               category:(code: string) => brokerTypes.get(code) === 'Foreign' ? 'F' : 'L' }
    };
  };
  const broker = brokerOf(job.broker), brokerAll = brokerOf(job.brokerAll);
  broker.catch(() => {}); brokerAll.catch(() => {});

  const catalog = COMPARE.filter(c => known.has(c.symbol));
  const loadCompare = async (id: string) => {
    const spec = catalog.find(c => c.id === id); if (!spec) return [];
    const series = spec.symbol === 'IHSG' ? await ihsgRows() : spec.symbol === SYMBOL ? rows : await prices(spec.symbol, csrf);
    return alignTo(dates, series);
  };

  const loadEvents = async (): Promise<MarketEvent[]> => (await job.events).flatMap((r: any, k) => {
    const type = r.family === 'CORPORATE_ACTION' ? EVENT_TYPE[r.type] : undefined;
    if (!type || r.d < dates[0]) return [];
    const at = dates.find(t => t >= r.d);                 // the marker sits on the first session on or after the date
    /* T9 (user 2026-10-26): the published detail rows; a value the source leaves blank shows "Unavailable" */
    const rows: [string, string][] = Array.isArray(r.detail)
      ? r.detail.map(([label, value, kind]: [string, unknown, string]) => [label, detailText(value, kind)] as [string, string])
      : [[roleLabel(r.role || 'Date'), longDates(r.d)]];
    if (r.instrument) rows.push(['Instrument', r.instrument]);
    return [{ id:`${SYMBOL}-${type}-${r.d}-${k}`, type, date:r.d, label:longDates(r.d), at, title:r.title || EVENT_TITLE[type], rows }];
  });

  return {
    mode:'live', symbol:SYMBOL, instruments, ohlc, volume, lineData, catalog, loadCompare, ihsg:[], loadIhsg,
    combos:[], flowSource:'real', flowFrom:N,
    broker: { dates:[], rows:() => [], label:SYMBOL, category:() => 'L' },
    later: { broker, brokerAll },
    loadEvents,
    hide: { brokerGauge:true, bandar:true }
  };
}
