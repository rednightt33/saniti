/* Live data: the pre-published files of the rack (bucket terminal-display) reached through EDGE's /api/terminal
   gateway (FRONTEND_HANDOFF.md). The page asks for presigned URLs and downloads the gzip JSON files itself.
   Everything is mapped into the reference page's own shapes (types.ts). */
import type { AssetBar, Bar, Combo, CompareSpec, InsiderTx, Instrument, Locks, MarketData, MarketEvent, Point, VolumePoint } from './types';
import { barRows, brokerData, download, priceRows, rowsOf, type PriceRow, type WorkerAnswer } from './worker';
import { INTEGRITY_MESSAGE, isIntegrity, type FileRef } from './rack';
import { aggregateRows, alignCandles, alignCandlesCarry, buckets, candleOf, dayOfCandles, dayOfKey, isIntraday, type Timeframe } from './timeframe';
import { fileStats, mark } from '../app/perf';
import { LockedData } from '../app/locked';
import { accessText, edge, isAccessRefusal, readError, SessionError } from '../../../shared/edge-session';
import { numberFormat } from './intlCache';

const API = '/api/terminal/v1';
/* track guest (decision 1 of 2026-11-19, "1a"): the Terminal is the page a visitor without an account opens; its session
   read then answers with the guest plan's access (shared/edge-session.ts allowGuest) */
edge.allowGuest();

/** `code` DATA_INTEGRITY: a file was not the one terminal-api announced (rack.ts IntegrityError; `detail` what differed,
    never a URL) */
export class TerminalError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly detail: string | undefined;
  constructor(message: string, status = 0, code?: string, detail?: string) { super(message); this.status = status; this.code = code; this.detail = detail }
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
  const idr = (n: number) => 'Rp ' + numberFormat('en-US').format((Number.isInteger(n) ? n : +n.toFixed(2)));
  if (kind === 'idr_per_share') return idr(value) + ' / share';
  if (kind === 'idr') return idr(value);
  if (kind === 'pct') return value.toFixed(2) + '%';
  if (kind === 'shares') return numberFormat('en-US').format(Math.round(value));
  return String(value);
}
const roleLabel = (role: string) => role.toLowerCase().split('_').map((w, i) => i ? w : w[0].toUpperCase() + w.slice(1)).join(' ');

/* EXEC-MU-ACCOUNTS Phase 0 (M471): session, CSRF and the error contract from the shared module
   (apps/edge-bff/shared/edge-session.ts): a plan refusal (CAPABILITY_REQUIRED, PLAN_EXPIRED, LIMIT_REACHED, MFA_REQUIRED)
   is shown as its message, not as "answered 403"; only a 401 asks to sign in again; a 403 CSRF_INVALID is repeated once.
   `csrf` is kept for the callers' signatures: the shared module sets the header itself. */
const SIGN_IN = 'Sign in to EDGE first, then open the Terminal tab again.';
/* EXEC-MU-ACCOUNTS re-check R2-32: a plan none of whose tickers is published (the ticker list is whole since decision 1
   of 2026-11-19, track guest; the page opens only a ticker the plan holds) */
const NO_TICKER = 'No ticker of your EDGE plan is published yet. Upgrade the plan to open others; you are still signed in.';
/* 3c check C3-9: the same for a visitor without an account, who has no plan and is not signed in */
const NO_TICKER_VISITOR = 'No ticker open to visitors is published yet. Sign in or create an EDGE account to open others.';
async function api(path: string, _csrf: string, body?: unknown) {
  let res: Response;
  try {
    res = await edge.send(API + path, body === undefined ? {}
      : { method:'POST', headers:{ 'Content-Type':'application/json' }, body:JSON.stringify(body) });
  } catch (e) { throw sessionFailure(e) }
  let data: any = null;
  try { data = await res.json() } catch(e) {}
  if (!res.ok) {
    const info = readError(res.status, data, res.headers.get('Retry-After'));
    const msg = data && (data.message || (data.error && (data.error.code || data.error)));
    /* re-check R1-1: edge-bff relays every terminal-api refusal in the contract's shape with EDGE's own words (a
       terminal-api 401 or 403 about its own account is 503 TERMINAL_UNAVAILABLE): those words, never the code */
    const words = data && typeof data.error === 'object' && data.error && !info.legacy ? info.message : '';
    throw new TerminalError(res.status === 401 ? SIGN_IN
      : isAccessRefusal(info) ? accessText(info) as string
      : words ? words
      : res.status === 429 ? `Download limit reached: ${msg || 'try again later'}.`
      : `The terminal data service answered ${res.status}${msg ? ` (${msg})` : ''}.`, res.status, info.code);
  }
  return data;
}

async function session(): Promise<string> {
  try { return (await edge.session()).csrf }
  catch (e) {
    throw sessionFailure(e);
  }
}

/* track guest (decision 1 of 2026-11-19: "user tetap bisa search ticker, tapi ketika dia klik ticker selain bbca maka akan
   keluar pop up box"): what the principal does not hold, derived from what the server says it holds, never from a list
   here: a ticker outside its terminal.tickers (no list: every ticker), an indicator or Flow indicator the catalog route
   does not list for it (`*` holds every one, so no catalog is read), a feature flag it lacks. An answer without
   `access` (a server before the catalog) locks nothing, as before; a catalog that cannot be read locks its kind. */
export async function lockRules(): Promise<Locks> {
  const a = edge.access(), guest = edge.guest;
  if (!a) return { guest, ticker:() => false, item:() => false, feature:() => false };
  const all = a.capabilities.includes('*'), tickers = edge.limit('terminal.tickers');
  const held: Record<'indicator' | 'flow_indicator', Set<string>> = { indicator:new Set(), flow_indicator:new Set() };
  if (!all) await Promise.all((['indicator', 'flow_indicator'] as const).map(kind => edge.catalog(kind)
    .then(c => { held[kind] = new Set(c.entries.map(e => e.id)) }, () => {})));
  return { guest, ticker:t => Array.isArray(tickers) && !tickers.includes(t), item:(kind, id) => !all && !held[kind].has(id),
    feature:cap => !edge.can(cap) };
}
/* a session that could not be read: a plan refusal's message, EDGE out of reach, or the sign-in sentence */
function sessionFailure(e: unknown): unknown {
  if (!(e instanceof SessionError)) return e;
  if (!e.error) return new TerminalError(e.message, 0);
  return new TerminalError(isAccessRefusal(e.error) ? e.message : SIGN_IN, e.error.status, e.error.code);
}

/* EXEC-TERMINAL-UI-1026 U6: one call gives every file of the displayed ticker (terminal-api /bundle) */
type Dataset = 'price' | 'broker' | 'events' | 'yield';
/* EXEC-TERMINAL-SPEED step 2: with packs the price is one file and the broker the archive plus the last two years (5
   objects instead of 21); each file carries its sha256, the key of the browser cache */
async function bundle(ticker: string, datasets: Dataset[], csrf: string, timeframe?: string) {
  const answer = await api('/bundle', csrf, { ticker, datasets, packs:true, ...(timeframe ? { timeframe } : {}) });
  // EXEC-MU-RUNTIME T7: each file with the sha256 and size /bundle announces; the worker draws only bytes that match both
  const refs = (name: Dataset): FileRef[] => (answer.datasets?.[name]?.files || []).map((f: any) =>
    ({ url:f.url, sha:f.sha256, bytes:f.bytes, name:`${name}/${f.pack || f.year || 'all'}` }));
  // EXEC-TERMINAL-FRESH: each dataset's own last date (a session after the broker's has no broker data yet, not zero)
  const through = { price:answer.datasets?.price?.data_through ?? undefined, broker:answer.datasets?.broker?.data_through ?? undefined };
  /* EXEC-INTRADAY-FEATURES C3: the asked timeframe's files (archive, then the current period) and how to read them; the
     timeframes the ticker has, for the buttons */
  const day = answer.datasets?.intraday;
  const intraday: FileRef[] | undefined = day ? (day.files || []).map((f: any) => ({ url:f.url, sha:f.sha256, bytes:f.bytes, name:`intraday/${f.part}` })) : undefined;
  const meta = day ? { barsPerYear:day.bars_per_year ?? undefined, first:day.first ?? undefined, last:day.last ?? undefined } : undefined;
  /* live checker after the switch-on (F1): every dataset the server answered as locked for this principal, read from the
     answer (no list here), and the history window of a capped price */
  const locked = Object.entries(answer.datasets || {}).filter(([, d]: [string, any]) => d && d.locked === true).map(([n]) => n);
  const cut = answer.datasets?.price?.cut;
  const history = cut && Number.isFinite(cut.history_days) && typeof cut.after === 'string'
    ? { days:cut.history_days as number, after:cut.after as string } : undefined;
  return { price:refs('price'), broker:refs('broker'), events:refs('events'), through, intraday, offset:day?.utc_offset_seconds ?? 0, meta,
           locked, history,
           timeframes:(answer.timeframes || {}) as Record<string, { first?: string; last?: string; rows?: number; bars_per_year?: number }>,
           // EXEC-FI-TERMINAL: a government bond: its yield files beside its price files, and what it is
           yieldFiles:refs('yield'), kind:(answer.kind || 'equity') as string, instrument:answer.instrument as any };
}

/* EXEC-FI-TERMINAL (user go 2026-11-01): a bond's files as a price job reads them: the chosen metric's files (the yield by
   default, or the bond's price) in the place of the price files; a bond has no broker or events files */
async function bondBundle(ticker: string, metric: 'yield' | 'price', csrf: string) {
  const f = await bundle(ticker, ['yield', 'price'], csrf);
  return { ...f, price:metric === 'yield' ? f.yieldFiles : f.price, broker:[], events:[], intraday:undefined,
           locked:f.locked.filter(n => n !== 'broker' && n !== 'events'),
           through:{ price:undefined, broker:undefined } };
}

/* U7: the files are downloaded, inflated and parsed by one Web Worker (worker.ts); its answers arrive in stages.
   Without Worker support the same functions run here. */
type BrokerAnswer = Omit<Extract<WorkerAnswer, { type:'broker' | 'brokerAll' }>, 'id' | 'type'>;
/* broker: the recent years (F5), brokerAll: the whole history, read after them */
interface Job { price: Promise<PriceRow[]>; bars: Promise<PriceRow[] | undefined>; broker: Promise<BrokerAnswer>; brokerAll: Promise<BrokerAnswer>; events: Promise<Record<string, unknown>[]> }
let worker: Worker | null = null, jobs = 0;
const waiting = new Map<number, Record<string, [(v: any) => void, (e: any) => void]>>();
/** 3f checker SERVE-4 (the lab gaps' optional row; the user's go 2026-11-22): every stage still waiting ends with `err`,
    and the map is emptied (the worker's error handler below; exported for its test). */
export function failAll(w: Map<number, Record<string, [(v: any) => void, (e: any) => void]>>, err: unknown) {
  for (const stages of w.values()) Object.values(stages).forEach(([, no]) => no(err));
  w.clear();
}
function run(files: Files, tf: Timeframe = 'D', onto?: string[]): Job {
  const stage = <T>() => { let ok!: (v: T) => void, no!: (e: any) => void; const p = new Promise<T>((a, b) => { ok = a; no = b }); p.catch(() => {}); return { p, ok, no } };
  const price = stage<PriceRow[]>(), bars = stage<PriceRow[] | undefined>(), broker = stage<any>(), brokerAll = stage<any>(), events = stage<Record<string, unknown>[]>();
  const job = { price:price.p, bars:bars.p, broker:broker.p, brokerAll:brokerAll.p, events:events.p };
  const groups = (ds: string[]) => tf === 'W' || tf === 'M' ? buckets(ds, tf) : null;
  if (typeof Worker === 'undefined') {
    (async () => {
      const brokerDocs = Promise.all(files.broker.map(download)), eventDocs = Promise.all(files.events.map(download));
      brokerDocs.catch(() => {}); eventDocs.catch(() => {});      // read below, after the price; no unhandled rejection (as worker.ts)
      const rows = priceRows(await Promise.all(files.price.map(download))); price.ok(rows);
      bars.ok(files.intraday?.length ? barRows(await Promise.all(files.intraday.map(download)), files.offset || 0) : undefined);
      const ds = onto || rows.map(r => r.d), all = brokerData(await brokerDocs, ds, groups(ds)); broker.ok(all); brokerAll.ok(all);
      events.ok((await eventDocs).flatMap(rowsOf));
    })().catch(e => [price, bars, broker, brokerAll, events].forEach(s => s.no(e)));
    return job;
  }
  if (!worker) {
    worker = new Worker(new URL('./worker.ts', import.meta.url));
    worker.onmessage = (e: MessageEvent<WorkerAnswer>) => {
      if (e.data.type === 'stats') { fileStats(e.data.files); return }
      const w = waiting.get(e.data.id); if (!w) return;
      const { id, type, ...data } = e.data as any;
      if (type === 'error') {
        const err = new TerminalError(data.message, data.status, data.code, data.detail);
        Object.values(w).forEach(([, no]) => no(err)); waiting.delete(id); return;
      }
      if (type === 'price' && w.bars) { w.bars[0](data.bars); delete w.bars }
      w[type][0](type === 'price' ? data.rows : type === 'events' ? data.rows : data);
      delete w[type]; if (!Object.keys(w).length) waiting.delete(id);
    };
    /* a worker that fails to load or throws outside a job answered nothing, so the chart stayed silent: every waiting
       stage now ends with the data-unavailable error the page shows, and the next job starts a new worker (as the
       Backtest's loader does, backtest/src/api/live.ts) */
    worker.onerror = (ev: ErrorEvent) => {
      ev.preventDefault?.();
      failAll(waiting, new TerminalError('The data could not be read. Reload the page to try again.', 0, 'DATA_UNAVAILABLE'));
      worker?.terminate(); worker = null;
    };
  }
  const id = ++jobs;
  waiting.set(id, { price:[price.ok, price.no], bars:[bars.ok, bars.no], broker:[broker.ok, broker.no], brokerAll:[brokerAll.ok, brokerAll.no], events:[events.ok, events.no] });
  worker.postMessage({ id, price:files.price, broker:files.broker, events:files.events, intraday:files.intraday, offset:files.offset, tf, dates:onto });
  return job;
}

/* EXEC-MU-RUNTIME T7: a job whose files fail their check (DATA_INTEGRITY: bytes unlike the sha256 and size /bundle
   announced) runs once more on a new /bundle (`again`, the same request). A content key never names other bytes (ERRORS
   M250), so a mismatch is a stale answer or a damaged transfer, which the new answer and download mend; the stages still
   waiting (every stage the failure ended) take the new job's answers. A failure of the second job, or any other error,
   reaches the page as it is, a failed check with the plain INTEGRITY_MESSAGE. */
type Files = { price: FileRef[]; broker: FileRef[]; events: FileRef[]; intraday?: FileRef[]; offset?: number };
/* a failed check as the page shows it (TerminalError, INTEGRITY_MESSAGE); its detail goes to the console once */
const logged = new WeakSet<object>();
function integrityFailure(e: any) {
  if (!isIntegrity(e)) return e;
  if (e.detail && !logged.has(e)) { logged.add(e); console.warn(`terminal: a data file failed its check: ${e.detail}`) }
  return e instanceof TerminalError ? e : new TerminalError(INTEGRITY_MESSAGE, 0, 'DATA_INTEGRITY', e.detail);
}
function checked(files: Files, again: () => Promise<Files>, tf: Timeframe = 'D', onto?: string[]): Job {
  const first = run(files, tf, onto);
  /* review of T7 (2026-10-29): the sessions the new job puts its broker data on are the ones the page draws: `onto`, else
     the first job's price once it was read (the chart keeps that price), else (the price failed too) the new job's own.
     A publication between the two answers can move the price's sessions (the year window, a corrected session); the
     new answer's own sessions would then shift every Flow value against the chart's candles. */
  const drawn = onto ? Promise.resolve(onto) : first.price.then(rows => rows.map(r => r.d), () => undefined);
  let second: Promise<Job> | null = null;
  const stage = <K extends keyof Job>(k: K): Job[K] => {
    const p = (first[k] as Promise<unknown>).catch(e => {
      if (!isIntegrity(e)) throw e;
      integrityFailure(e);                                     // logs what differed
      // one new /bundle per job, whichever stage failed first
      second ||= Promise.all([again(), drawn]).then(([f, on]) => run(f, tf, on));
      return second.then(j => j[k] as Promise<unknown>).catch(e2 => { throw integrityFailure(e2) });
    }) as Job[K];
    p.catch(() => {});
    return p;
  };
  return { price:stage('price'), bars:stage('bars'), broker:stage('broker'), brokerAll:stage('brokerAll'), events:stage('events') };
}

/* one ticker's datasets, checked (one new /bundle on a failed check) */
async function load(ticker: string, datasets: Dataset[], csrf: string, tf: Timeframe = 'D', onto?: string[], first?: Files, timeframe?: string) {
  const again = () => bundle(ticker, datasets, csrf, timeframe);
  return checked(first || await again(), again, tf, onto);
}

/* a published file outside a job (the reference files), read on the page: a failed check asks its announcement once
   more (`attempt` asks terminal-api again), then shows INTEGRITY_MESSAGE */
async function once<T>(attempt: () => Promise<T>): Promise<T> {
  try { return await attempt() }
  catch (e) {
    if (!isIntegrity(e)) throw e;
    integrityFailure(e);                                       // logs what differed
    try { return await attempt() } catch (e2) { throw integrityFailure(e2) }
  }
}

async function prices(ticker: string, csrf: string) {
  return (await load(ticker, ['price'], csrf)).price;
}

/* a series on the chart's sessions: the last close on or before each session (forward fill); sessions before its
   first close have no point */
function alignTo(dates: string[], rows: { d: string; c: number }[], ends: string[] = dates): Point[] {
  // EXEC-TERMINAL-WM: a weekly or monthly candle takes the value at its last session (`ends`), labelled with its first
  const out: Point[] = []; let k = 0, last: number | null = null;
  dates.forEach((t, i) => {
    while (k < rows.length && rows[k].d <= ends[i]) { last = rows[k].c; k++ }
    if (last !== null) out.push({ time:t, value:last });
  });
  return out;
}

/* EXEC-INTRADAY-FEATURES C3: another ticker's bars on the chart's candles by key; a candle it did not trade repeats its
   last close; candles before its first bar are left out */
function alignBars(keys: string[], rows: PriceRow[]): Bar[] {
  const at = new Map(rows.map(r => [r.d, r])), out: Bar[] = [];
  let last: number | null = null, k = 0;
  while (k < rows.length && rows[k].d < keys[0]) last = rows[k++].c;
  for (const t of keys) {
    const r = at.get(t);
    if (r) { out.push({ time:t, open:r.o, high:r.h, low:r.l, close:r.c }); last = r.c }
    else if (last !== null) out.push({ time:t, open:last, high:last, low:last, close:last });
  }
  return out;
}

/* U5 (user 2026-10-26: "automatically load chart dan panel bawah.. lalu panel kiri dan kanan akan load kalau user
   buka/expand the panel"): the page draws as soon as the price is read; the broker data (Flow, Broker activity) and
   the events follow through `later`, IHSG (Statistics, Relative performance) only when that panel asks for it. */
export async function liveData(stored: string | null, tf: Timeframe = 'D', bondMetric: 'yield' | 'price' = 'yield'): Promise<MarketData> {
  const csrf = await session();
  mark('session');
  const locksP = lockRules();
  /* EXEC-MU-RUNTIME T5/T7: a reference file the publication's refs index names comes with its sha256 and size, and is
     checked and cached as a data file; without them (an older terminal-api or publication) it is the fixed-key copy no
     index describes, read as it comes */
  const refFile = (a: any, name: string): string | FileRef => a && (a.sha256 != null || a.bytes != null)
    ? { url:a.url, sha:a.sha256, bytes:a.bytes, name:`ref/${name}` } : a?.url;
  const reference = (name: string) => once(async () => rowsOf(await download(refFile(await api(`/reference/${name}`, csrf), name))));
  /* the ticker list, the broker list and the files of the remembered ticker are asked for together */
  const tickersP = reference('tickers'), brokerRefP = reference('brokers');
  /* EXEC-TERMINAL-LOGO: ticker → logo version (sha256 prefix); a ticker without one shows its monogram */
  const logosP = reference('logos').then(rows => Object.fromEntries(rows.map((r: any) => [r.ticker, String(r.sha256).slice(0, 12)])), () => ({}));
  /* a promise awaited later gets its handler at once: the ticker list is awaited only after the locks (below), and a
     refusal of it meanwhile would otherwise be an unhandled rejection besides the error liveData throws (fix-int2, M490) */
  brokerRefP.catch(() => {}); tickersP.catch(() => {});
  const locks = await locksP;
  /* track guest: a remembered ticker the plan does not hold never locks the page: the first ticker of the plan instead */
  const planTickers = edge.limit('terminal.tickers');
  const firstHeld = Array.isArray(planTickers) ? planTickers[0] : undefined;
  const guess = [stored, 'MAPI', firstHeld].find(t => t && !locks.ticker(t)) || stored || 'MAPI';
  const want = isIntraday(tf) ? tf : undefined;                // EXEC-INTRADAY-FEATURES C3
  /* EXEC-FI-TERMINAL: the government bonds (ref/fixed_income), a group of their own in the search; the remembered
     ticker's first answer also asks for a bond's yield files, so a bond needs no second /bundle (a stock has none) */
  const bondsP = reference('fixed_income').catch(() => []) as Promise<any[]>;
  // a terminal-api from before the bonds refuses `yield` (400): the stock datasets alone, as before
  const guessP = bundle(guess, ['price', 'broker', 'events', 'yield'], csrf, want)
    .catch((e: any) => e?.status === 400 ? bundle(guess, ['price', 'broker', 'events'], csrf, want) : Promise.reject(e));
  guessP.catch(() => {});
  const metric = bondMetric;                                  // a bond's metric (main.ts: remembered as ml.fi.metric)
  type Answer = Awaited<ReturnType<typeof bundle>>;
  const asBond = (f: Answer) => ({ ...f, price:metric === 'yield' ? f.yieldFiles : f.price, broker:[], events:[],
    intraday:undefined, through:{ price:undefined, broker:undefined } });
  /* a ticker's /bundle answer → its files and the started job (downloads begin in the worker at once) */
  const prepare = async (sym: string, first: Answer, isBond: boolean) => {
    /* M327: a bond's first answer without the chosen metric's files (the stock-only fallback above) is not read as an
       empty chart: the bond's own two datasets are asked for once more */
    const files = !isBond ? first : (metric === 'yield' ? first.yieldFiles : first.price).length ? asBond(first)
      : await bondBundle(sym, metric, csrf);
    // a ticker without the asked intraday timeframe shows its daily chart and says so (`note`; a bond has none)
    const intraday = !!want && !!files.intraday?.length;
    const tfx: Timeframe = want && !intraday ? 'D' : tf;
    const job = isBond ? checked(files, () => bondBundle(sym, metric, csrf), tfx)
      : await load(sym, ['price', 'broker', 'events'], csrf, tfx, undefined, files, intraday ? want : undefined);
    return { files, intraday, tf:tfx, job };
  };
  /* ERRORS M333: the remembered ticker's files start downloading as soon as its /bundle answers, beside the ticker list
     (a 200 answer means the ticker is published, and it says whether it is a bond); before, the download
     waited for the ticker list's own download (up to ~2 s on a first visit) */
  const isBondAnswer = (f: Answer) => f.kind === 'fixed_income' || f.yieldFiles.length > 0;   // only a bond has yield files
  const early = guessP.then(f => prepare(guess, f, isBondAnswer(f)));
  early.catch(() => {});
  const tickers = await tickersP as { ticker: string; name: string; type: string; sector: string | null; instrument?: string | null }[];
  const bonds = await bondsP;
  const bondOf = new Map(bonds.map((b: any) => [b.ticker as string, b]));
  const known = new Set([...tickers.map(t => t.ticker), ...bondOf.keys()]);
  /* the search's right column: the market each instrument trades in, from its own data (the ticker list's `type`, a bond
     from ref/fixed_income); a bond's upper line names its country (user 2026-11-01: "ini obligasi, tapi kenapa IDX equity?") */
  const typeWord = (t: string) => t === 'stock' ? 'Equity' : t ? t[0].toUpperCase() + t.slice(1) : 'Equity';
  /* EXEC-UNIVERSE-BROKER S1.4: the ticker list's instrument (TradingView's type detail) names a security that is not a
     common share, e.g. 'etf' -> ETF; 'common' and 'Undefined' (no detail) keep the type word */
  const detail = (i?: string | null) => i && i !== 'common' && i !== 'Undefined' ? i.toUpperCase() : '';
  const sectorOf = (t: typeof tickers[number]) => t.sector && t.sector !== 'Undefined' ? t.sector
    : detail(t.instrument) || t.sector || (t.type === 'index' ? 'Index' : 'Other');
  /* track guest: every ticker of the list is searchable; one the plan does not hold is marked (search.ts opens the box) */
  const lockedOf = (t: string) => locks.ticker(t) ? { locked:true } : {};
  const instruments: Instrument[] = [...tickers.map(t => [t.ticker, t.name || t.ticker, sectorOf(t), 0,
      { market:`IDX · ${detail(t.instrument) || typeWord(t.type)}`, ...lockedOf(t.ticker) }] as Instrument),
    ...bonds.map((b: any) => [b.ticker, b.name || b.ticker, 'Fixed income', 0, { market:'Fixed income', place:b.country || undefined, ...lockedOf(b.ticker) }] as Instrument)];
  const open = (t: string | null | undefined) => !!t && known.has(t) && !locks.ticker(t);
  const SYMBOL = [stored, 'MAPI'].find(open) ?? tickers.find(t => open(t.ticker))?.ticker ?? bonds.find((b: any) => open(b.ticker))?.ticker;
  if (!SYMBOL) throw new TerminalError(edge.guest ? NO_TICKER_VISITOR : NO_TICKER);
  const bond = bondOf.get(SYMBOL);
  const isIndex = tickers.some(t => t.ticker === SYMBOL && t.type === 'index');     // EXEC-IHSG-FLOW
  const ready = SYMBOL === guess && (await guessP.then(f => isBondAnswer(f) === !!bond, () => false)) ? await early
    : await prepare(SYMBOL, await bundle(SYMBOL, bond ? ['yield', 'price'] : ['price', 'broker', 'events'], csrf, want), !!bond);
  const { files, intraday, job } = ready;
  tf = ready.tf;

  mark('ticker list and bundle');
  const rows = await job.price;                            // daily sessions
  const bars = intraday ? (await job.bars) || [] : null;   // the intraday candles, keyed by their open time (WIB)
  mark('price read');
  if (!rows.length && !bars?.length) throw new TerminalError(`No price data is published for ${SYMBOL}.`);
  /* EXEC-TERMINAL-WM: the chart's candles (daily, or built from the daily sessions); `ends` = each candle's last session.
     EXEC-INTRADAY-FEATURES C3: an intraday candle's session is its key's date; `dayOf` = the daily session each candle
     shows for the daily figures (Flow, Bandar, Broker, a daily-only indicator; C4, timeframe.ts dayOfCandles) */
  const sessions = rows.map(r => r.d), groups = buckets(sessions, intraday ? 'D' : tf);
  const candles = bars || aggregateRows(rows, tf), ends = bars ? bars.map(b => dayOfKey(b.d)) : groups.ends;
  const dayOf = bars ? dayOfCandles(bars.map(b => b.d), sessions) : undefined;
  const ohlc: Bar[] = candles.map(r => ({ time:r.d, open:r.o, high:r.h, low:r.l, close:r.c }));
  const volume: VolumePoint[] = candles.map(r => ({ time:r.d, value:r.v ?? 0, color:r.c >= r.o ? 'rgba(0,150,109,.48)' : 'rgba(235,57,69,.48)', ...(r.v == null ? { none:true } : {}) }));
  const lineData: Point[] = ohlc.map(b => ({ time:b.time, value:b.close }));
  const dates = ohlc.map(b => b.time), N = dates.length;
  /* intraday: another ticker's bars of the same timeframe (IHSG, a compare series, an added asset) */
  const barsOf = async (ticker: string) => ticker === SYMBOL && bars ? bars
    : (await (await load(ticker, ['price'], csrf, 'D', undefined, undefined, want)).bars) || [];
  /* the candle a date falls on: intraday, the first candle of the first session on or after it */
  const firstCandleOn = (d: string) => { let lo = 0, hi = N; while (lo < hi) { const m = (lo + hi) >> 1; if (ends[m] < d) lo = m + 1; else hi = m } return lo };
  const barOf = (d: string) => intraday ? (N ? dates[Math.min(firstCandleOn(d), N - 1)] : null) : candleOf(d, groups, sessions);
  /* the daily figures on the candles: a session's values on the candles that show it (dayOf), its broker rows' first and
     last session as candle indices */
  const onTheCandles = <T extends { combos: any[]; flowFrom: number; flowTo: number }>(b: T): T => {
    if (!dayOf) return b;
    let from = N, to = -1;
    dayOf.forEach((d, i) => { if (d >= 0 && d >= b.flowFrom && d <= b.flowTo) { if (i < from) from = i; to = i } });
    return { ...b, flowFrom:from, flowTo:to, combos:b.combos.map(c => ({ ...c, net:Float64Array.from(dayOf, d => d >= 0 ? c.net[d] || 0 : 0) })) };
  };

  /* IHSG for Statistics → Relative performance; sessions before its first close take its first close */
  let ihsgP: Promise<{ d: string; c: number }[]> | null = null;
  const ihsgRows = () => ihsgP ||= intraday ? barsOf('IHSG') : SYMBOL === 'IHSG' ? Promise.resolve(rows) : prices('IHSG', csrf);
  const loadIhsg = async (): Promise<Point[]> => {
    // 3e: a principal that does not hold IHSG (a visitor, the free plan: decision D3) is never sent to ask for it
    if (SYMBOL !== 'IHSG' && locks.ticker('IHSG')) throw new LockedData({ kind:'ticker', id:'IHSG', name:'Composite Index' });
    const aligned = alignTo(dates, await ihsgRows(), intraday ? dates : ends);
    const first = aligned.length ? aligned[0].value : NaN;
    return dates.map((t, i) => aligned[i - (N - aligned.length)] ?? { time:t, value:first });
  };

  /* broker files: Flow Timeline (net per broker × investor type × board) and Broker activity (every broker date, EXEC-BROKER-FULL) */
  const brokerOf = async (stage: Promise<BrokerAnswer>) => {
    const b = onTheCandles(await stage);
    const brokerTypes = new Map((await brokerRefP.catch(() => [])).map((r: any) => [r.code, r.type] as [string, string]));
    return {
      combos:b.combos.map(c => ({ ...c, tilt:0 })) as Combo[], flowFrom:b.flowFrom, flowTo:b.flowTo, flow:b.flow,
      broker:{ dates:b.dates, rows:(d: number) => b.rows[d] || [], label:SYMBOL,
               category:(code: string) => brokerTypes.get(code) === 'Foreign' ? 'F' : 'L' }
    };
  };
  const broker = brokerOf(job.broker), brokerAll = brokerOf(job.brokerAll);
  broker.catch(() => {}); brokerAll.catch(() => {});

  const catalog = COMPARE.filter(c => known.has(c.symbol));
  const loadCompare = async (id: string) => {
    const spec = catalog.find(c => c.id === id); if (!spec) return [];
    const series = spec.symbol === 'IHSG' ? await ihsgRows() : intraday ? await barsOf(spec.symbol) : spec.symbol === SYMBOL ? rows : await prices(spec.symbol, csrf);
    return alignTo(dates, series, intraday ? dates : ends);
  };

  /* EXEC-TERMINAL-ASSETS (user 2026-10-28: "ketika kita add asset, maka yang keluar adalah search box exactly sama seperti
     kalau kita search ticker ... maksimal 2"; "Menambah aset hanya menambah flow timeline di bawah"): any published ticker
     as candles on the chart's candles, and its broker files as Flow Timeline combos on the chart's sessions (the worker
     puts them there, `dates`); the right panel stays the chart's own ticker */
  /* 3e (the 3e checker TL-1): an added asset the principal does not hold (its ticker, or broker data for its Flow
     Timeline) is never asked for; the loaders reject with LockedData, as the IHSG of Statistics does, so every caller
     (the restore of the last visit, the + search, the settings' Symbol) says Locked and opens the box */
  const tickerLock = (t: string) => new LockedData({ kind:'ticker', id:t, name:instruments.find(i => i[0] === t)?.[1] || t });
  const brokerLocked = (files.locked || []).includes('broker');            // the chart's answer: broker data is closed
  const loadAsset = async (ticker: string): Promise<AssetBar[]> => {
    if (locks.ticker(ticker)) throw tickerLock(ticker);
    if (!known.has(ticker)) return [];
    /* EXEC-FI-TERMINAL (user 2026-11-01: a bond as a comparison on a stock chart): its yield file alone (one pack), on the
       chart's candles with the 3-session carry; a bond has no intraday bars */
    if (bondOf.has(ticker)) {
      if (intraday) return [];
      const ask = async () => { const f = await bundle(ticker, ['yield'], csrf);
        return { ...f, price:f.yieldFiles, broker:[], events:[], intraday:undefined, through:{ price:undefined, broker:undefined } } };
      return alignCandlesCarry(sessions, groups, await checked(await ask(), ask, 'D').price);
    }
    if (intraday) return alignBars(dates, await barsOf(ticker));
    const daily = ticker === SYMBOL ? rows : await prices(ticker, csrf);
    return alignCandles(sessions, groups, daily);
  };
  const loadAssetFlow = async (ticker: string) => {
    if (locks.ticker(ticker)) throw tickerLock(ticker);
    if (brokerLocked) throw new LockedData({ kind:'feature', id:'terminal.dataset:broker', name:'Broker data' });
    const files = await bundle(ticker, ['broker'], csrf);
    const asset = await load(ticker, ['broker'], csrf, intraday ? 'D' : tf, sessions, files);   // a broker-only answer: no price or events files
    const part = async (stage: Promise<BrokerAnswer>) => {
      const b = onTheCandles(await stage);
      return { combos:b.combos.map(c => ({ ...c, tilt:0 })) as Combo[], flowFrom:b.flowFrom, flowTo:b.flowTo };
    };
    const recent = part(asset.broker), all = part(asset.brokerAll);
    recent.catch(() => {}); all.catch(() => {});
    return { recent, all, through:files.through.broker };
  };

  const loadEvents = async (): Promise<MarketEvent[]> => (await job.events).flatMap((r: any, k) => {
    const type = r.family === 'CORPORATE_ACTION' ? EVENT_TYPE[r.type] : undefined;
    if (!type || r.d < (intraday ? ends[0] : sessions[0])) return [];
    // the marker sits on the candle that holds the first session on or after the date
    const at = barOf(r.d) ?? undefined;
    /* T9 (user 2026-10-26): the published detail rows; a value the source leaves blank shows "Unavailable" */
    const rows: [string, string][] = Array.isArray(r.detail)
      ? r.detail.map(([label, value, kind]: [string, unknown, string]) => [label, detailText(value, kind)] as [string, string])
      : [[roleLabel(r.role || 'Date'), longDates(r.d)]];
    if (r.instrument) rows.push(['Instrument', r.instrument]);
    return [{ id:`${SYMBOL}-${type}-${r.d}-${k}`, type, date:r.d, label:longDates(r.d), at, title:r.title || EVENT_TITLE[type], rows }];
  });

  /* EXEC-TERMINAL-FLOW-IND: Insider Net Change reads the insider rows of the same events file; Institutional vs Retail
     Net the brokers' classification (absent from a reference file published before it: no list, no value) */
  /* EXEC-QA5-FIX (QA 2026-11-07, F2-03): a ticker with no events file published has no insider rows to read; that is "not
     available", not a flat "Rp 0" (the indicator says so) */
  const loadInsider = async (): Promise<InsiderTx[]> => { if (!files.events?.length) throw new Error('no events file'); return (await job.events).flatMap((r: any) =>
    r.family === 'INSIDER' && (r.action === 'BUY' || r.action === 'SELL') && Number.isFinite(r.value) ? [{ d:r.d, value:r.action === 'BUY' ? r.value : -r.value }] : []) };
  const brokerClass = brokerRefP.then((rows: any[]) => Object.fromEntries(rows.filter(r => typeof r.classification === 'string').map(r => [r.code, r.classification])), () => ({}));

  return {
    /* ERRORS M333: the logo list arrives after the chart (main.ts setLogos); a bond shows its country's flag */
    mode:'live', symbol:SYMBOL, instruments, locks, ohlc, volume, lineData, catalog, loadCompare, ihsg:[], loadIhsg, logosLater:logosP,
    countries:Object.fromEntries(bonds.filter((b: any) => b.country).map((b: any) => [b.ticker, b.country])),
    loadInsider, brokerClass,
    loadAsset, loadAssetFlow, isBond:(t: string) => bondOf.has(t),
    combos:[], flowSource:'real', flowFrom:N,
    broker: { dates:[], rows:() => [], label:SYMBOL, category:() => 'L' },
    later: { broker, brokerAll },
    tf, endDates:ends, barOf,
    through: files.through,
    // EXEC-INTRADAY-FEATURES C3-C4: the timeframes the ticker has, and on an intraday chart the daily sessions behind
    // the daily figures, the session each candle shows (dayOf) and the timeframe's bars per year
    timeframes:Object.keys(files.timeframes || {}),
    // a locked timeframe is not "not published": the page opens the lock box instead (main.ts lockedPage)
    ...(want && !intraday && !(files.locked || []).includes('intraday') ? { note:`No ${want.toUpperCase()} data is published for ${SYMBOL}; showing the daily chart.` } : {}),
    lockedData:files.locked || [], ...(files.history ? { history:files.history } : {}),
    // a principal without the broker data has no Flow input at all (as a bond): no Flow Timeline, readout or broker panel
    ...((files.locked || []).includes('broker') ? { later:undefined } : {}),
    ...(intraday && dayOf ? { intraday:{ dayOf, days:sessions, daily:rows, barsPerYear:files.meta?.barsPerYear, first:files.meta?.first, last:files.meta?.last } } : {}),
    loadEvents,
    ...(isIndex ? { index:true as const } : {}),
    ...(bond ? { fixedIncome:{ metric, name:bond.name || SYMBOL, country:bond.country || '',
                               units:{ yield:bond.yield_unit ?? undefined, price:bond.price_unit ?? undefined } }, later:undefined } : {}),
    // the broker-action gauge has no approved formula yet; the Bandar detector's sums and verdict live in Top brokers
    // (EXEC-BANDAR-MERGE, user 2026-11-01: "Pakai opsi 10 ya Tarik tambang")
    hide: { brokerGauge:true, bandar:true }
  };
}
