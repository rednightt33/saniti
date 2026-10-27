/* The production BacktestApi. Session and CSRF as the Terminal's live.ts (GET /api/v1/auth/session, the token on every
   POST). Market data: POST /api/terminal/v1/bundle {ticker, datasets, packs: true} gives the presigned files of a
   ticker; the page downloads them itself and decodes them with the shared core (datafile.ts: every file checked against
   its manifest sha256 and bytes; flow.ts for the broker files). Calculations on that data run in the browser with the
   shared core (compute.ts). Verified files are kept in the browser cache the Terminal uses (cache.ts). Backtest jobs:
   the edge-bff endpoints of CONTRACT.md section 9. The texts on the data are the published data's (texts.ts). */
import type { BacktestRequest, BacktestResultCore, Catalog, JobStatus, SignalsPreview, SignalsPreviewRequest } from '../core/contract.ts';
import { asOf, DataError, type FileEntry, type PriceSeries } from '../core/datafile.ts';
import type { FlowData } from '../core/flow.ts';
import { loadFlow, loadPrice, type LoadAnswer, type LoadJob } from './load.ts';
import { ApiFailure, isAbort, type BacktestApi, type Card, type TickerBars, type TickerEvents } from './types.ts';
import { Compute } from './compute.ts';
import { fileCache, type FileCache } from './cache.ts';
import { PUBLISHED_TEXTS } from './texts.ts';

const TERMINAL = '/api/terminal/v1', BACKTESTS = '/api/v1/backtests';
const SIGN_IN = 'Sign in to EDGE first, then open the Backtest tab again.';

/* ---- session and JSON calls -------------------------------------------------------------------------------- */
let csrfP: Promise<string> | null = null;
function csrf(): Promise<string> {
  return csrfP ||= (async () => {
    const res = await fetch('/api/v1/auth/session', { credentials:'same-origin' });
    if (!res.ok) throw new ApiFailure(SIGN_IN, 'UNAUTHENTICATED', res.status);
    const data = await res.json();
    return data.csrf_token || '';
  })().catch(e => { csrfP = null; throw e });
}

/** an edge-bff answer that is not ok as the page's message: {error:{code, field, message}} (CONTRACT.md section 11) */
async function failure(res: Response, service: string): Promise<ApiFailure> {
  let data: any = null;
  try { data = await res.json() } catch { /* no JSON body */ }
  const err = data && data.error && typeof data.error === 'object' ? data.error : null;
  const code = err ? String(err.code || '') : data && typeof data.error === 'string' ? data.error : '';
  const msg = (err && err.message) || (data && data.message) || '';
  if (res.status === 401) return new ApiFailure(SIGN_IN, code || 'UNAUTHENTICATED', 401);
  if (code === 'BACKTEST_DISABLED') return new ApiFailure(msg || 'Backtests are switched off on this server.', code, res.status);
  if (res.status === 429) return new ApiFailure(`Limit reached: ${msg || code || 'try again later'}.`, code, 429);
  return new ApiFailure(msg || `The ${service} answered ${res.status}${code ? ` (${code})` : ''}.`, code, res.status, err?.field);
}

/* `signal`: the caller's AbortSignal; an aborted call rejects with the AbortError itself (types.ts isAbort) */
async function call<T>(base: string, path: string, body?: unknown, service = 'backtest service', signal?: AbortSignal): Promise<T> {
  const init: RequestInit = body === undefined ? { credentials:'same-origin', signal }
    : { method:'POST', credentials:'same-origin', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token':await csrf() }, body:JSON.stringify(body), signal };
  let res: Response;
  try { res = await fetch(base + path, init) }
  catch (e) { if (isAbort(e)) throw e; throw new ApiFailure(`The ${service} could not be reached.`, 'NETWORK') }
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) csrfP = null;      // a new session or token is read on the next call
    throw await failure(res, service);
  }
  if (res.status === 204) return undefined as T;
  // an answer whose body is cut off on the way is no answer: NETWORK, which the status poll asks again (run.ts status)
  try { return await res.json() }
  catch (e) { if (isAbort(e)) throw e; throw new ApiFailure(`The ${service} could not be reached.`, 'NETWORK') }
}

/* ---- published market data ---------------------------------------------------------------------------------- */
type Dataset = 'price' | 'broker';
export { FILE_RETRIES, FILE_RETRY_MS } from '../../../terminal/src/data/rack.ts';

/* EXEC-BACKTEST-LOAD (K3, "Seperti bagian terminal"): one /bundle per ticker for what it is about to need (its prices,
   and its broker files when a flow card will ask for them), reused for the other dataset while its URLs are still
   good (terminal-api's links live 120 s; URL_LIFE_MS keeps a margin) */
const URL_LIFE_MS = 90_000;
function bundles() {
  const kept = new Map<string, { at: number; datasets: Dataset[]; p: Promise<any> }>();
  return (ticker: string, need: Dataset[]) => {
    const k = kept.get(ticker);
    if (k && Date.now() - k.at < URL_LIFE_MS && need.every(d => k.datasets.includes(d))) return k.p;
    const p = call(TERMINAL, '/bundle', { ticker, datasets:need, packs:true }, 'market data service');
    kept.set(ticker, { at:Date.now(), datasets:need, p });
    p.catch(() => { if (kept.get(ticker)?.p === p) kept.delete(ticker) });
    return p;
  };
}
const filesOf = (answer: any, ticker: string, dataset: Dataset): FileEntry[] => {
  const list = answer?.datasets?.[dataset]?.files;
  if (!Array.isArray(list) || !list.length) throw new ApiFailure(`No ${dataset} data is published for ${ticker}.`, 'DATA_MISSING');
  return list.map((f: any) => ({ url:f.url, sha256:f.sha256, bytes:f.bytes }));
};

/* the loading worker (load.worker.ts) when the browser has Web Workers; the same work on the page otherwise (tests) */
function loader(cache: FileCache, offThread: boolean) {
  let worker: Worker | null = null, n = 0;
  const waiting = new Map<number, [(v: any) => void, (e: unknown) => void]>();
  const start = () => {
    if (worker || !offThread) return worker;
    try {
      worker = new Worker(new URL('./load.worker.ts', import.meta.url));
      worker.onmessage = (e: MessageEvent<LoadAnswer>) => {
        const a = e.data, w = waiting.get(a.id); if (!w) return;
        waiting.delete(a.id);
        if (a.ok === true) w[0](a.out);
        else w[1](new ApiFailure(a.error.message, a.error.code, a.error.status, a.error.field));
      };
      worker.onerror = () => { for (const [, w] of waiting) w[1](new ApiFailure('The data could not be read.', 'DATA_UNAVAILABLE')); waiting.clear(); worker = null; offThread = false };
    } catch { worker = null; offThread = false }
    return worker;
  };
  type Job = { kind: 'price'; ticker: string; files: FileEntry[] } | { kind: 'flow'; ticker: string; files: FileEntry[]; dates: string[] };
  const ask = <T>(job: Job): Promise<T> => {
    const w = start();
    if (!w) return (job.kind === 'price' ? loadPrice(job.ticker, job.files, cache) : loadFlow(job.ticker, job.files, job.dates, cache)) as Promise<T>;
    const id = ++n;
    return new Promise<T>((ok, no) => { waiting.set(id, [ok, no]); w.postMessage({ ...job, id } satisfies LoadJob) });
  };
  return {
    price: (ticker: string, files: FileEntry[]) => ask<PriceSeries>({ kind:'price', ticker, files }),
    flow: (ticker: string, files: FileEntry[], dates: string[]) => ask<FlowData>({ kind:'flow', ticker, files, dates }),
  };
}

/** the page's TickerBars of a decoded price series */
const tickerBars = (p: PriceSeries): TickerBars => ({ ticker:p.ticker, dates:p.dates as string[], o:p.bars.O as number[], h:p.bars.H as number[], l:p.bars.L as number[], c:p.bars.C as number[], v:p.bars.V as (number | null)[] });
/* a core DataError (its message names the file) or any other decoding error as the page's message */
const dataFailure = (e: unknown, ticker: string) => e instanceof ApiFailure ? e
  : e instanceof DataError ? new ApiFailure(e.message, e.code, 0, e.field)
  : new ApiFailure(`The published data of ${ticker} could not be read (${(e as Error)?.message || e}).`, 'DATA_INTEGRITY');

/** `cache`: the browser's file cache of this page load (a test passes its own) */
export function liveApi(opts: { cache?: FileCache } = {}): BacktestApi {
  const cache = opts.cache ?? fileCache();
  // a test passes its own cache and reads on the page; the browser reads off the page's main thread
  const load = loader(cache, !opts.cache && typeof Worker !== 'undefined'), bundle = bundles();
  let catalog: Catalog | null = null;
  const compute = new Compute(() => catalog);
  const prices = new Map<string, Promise<PriceSeries>>();
  const flows = new Map<string, Promise<void>>();
  // this page's order of its previews, client_order (CONTRACT.md P8): edge-bff lets a newer one end an older one, and
  // two sent close together can reach it swapped (ERRORS M247); the count is taken as the preview is asked, so it is
  // the order preview.ts asked them in
  const page = newId();
  let previews = 0;

  const priceOf = (ticker: string, soon = false) => {
    let p = prices.get(ticker);
    if (!p) {
      p = bundle(ticker, soon ? ['price', 'broker'] : ['price']).then(a => load.price(ticker, filesOf(a, ticker, 'price')))
        .catch(e => { prices.delete(ticker); throw dataFailure(e, ticker) });
      prices.set(ticker, p);
    }
    return p;
  };
  const flowOf = (ticker: string, series: PriceSeries) => {
    let p = flows.get(ticker);
    if (!p) {
      p = bundle(ticker, ['broker']).then(a => load.flow(ticker, filesOf(a, ticker, 'broker'), series.dates as string[]))
        .then(flow => { compute.put(tickerBars(series), flow, series.bars) })
        .catch(e => { flows.delete(ticker); throw dataFailure(e, ticker) });
      flows.set(ticker, p);
    }
    return p;
  };

  return {
    texts: PUBLISHED_TEXTS,
    async catalog() { catalog = await call<Catalog>(BACKTESTS, '/catalog'); return catalog },

    async bars(ticker, opts = {}) {
      const series = await priceOf(ticker, !!(opts.flow || opts.soon));
      if (!compute.has(ticker)) compute.put(tickerBars(series), undefined, series.bars);
      // EXEC-BACKTEST-LOAD: the broker files load before the catalog answers too (flow off is only known from it)
      if (opts.flow && catalog?.flow.available !== false && !compute.has(ticker, true)) await flowOf(ticker, series);
      return compute.get(ticker)!;
    },

    ready: (card: Card) => compute.ready(card),
    indicatorOutputs: (ticker, id, params) => compute.indicatorOutputs(ticker, id, params),
    conditionSeries: (ticker, card) => compute.conditionSeries(ticker, card),

    signalsPreview: (req: SignalsPreviewRequest, o = {}) =>
      call<SignalsPreview>(BACKTESTS, '/signals', { ...req, client_order:{ page, seq:++previews } }, undefined, o.signal),
    submit: (req: BacktestRequest) => call<{ request_id: string }>(BACKTESTS, '', { ...req, client_request_id:newId() }),
    status: (id: string) => call<JobStatus>(BACKTESTS, `/${encodeURIComponent(id)}`),
    result: (id: string) => call<BacktestResultCore>(BACKTESTS, `/${encodeURIComponent(id)}/result`),
    events: (id: string, ticker: string) => call<TickerEvents>(BACKTESTS, `/${encodeURIComponent(id)}/events?ticker=${encodeURIComponent(ticker)}`),
    async cancel(id: string) { await call(BACKTESTS, `/${encodeURIComponent(id)}/cancel`, {}) },

    async closes(ticker, calendar) {
      const p = await priceOf(ticker);
      return asOf(p.dates, p.bars.C as (number | null)[], calendar);
    },
  };
}

const newId = () => typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
