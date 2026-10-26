/* The production BacktestApi. Session and CSRF as the Terminal's live.ts (GET /api/v1/auth/session, the token on every
   POST). Market data: POST /api/terminal/v1/bundle {ticker, datasets, packs: true} gives the presigned files of a
   ticker; the page downloads them itself and decodes them with the shared core (datafile.ts: every file checked against
   its manifest sha256 and bytes; flow.ts for the broker files). Calculations on that data run in the browser with the
   shared core (compute.ts). Backtest jobs: the edge-bff endpoints of CONTRACT.md section 9. */
import type { BacktestRequest, BacktestResult, Catalog, JobStatus, SignalsPreview, SignalsPreviewRequest } from '../core/contract.ts';
import { asOf, brokerGaps, brokerRows, DataError, inflateVerified, priceSeries, type FileEntry, type PriceSeries } from '../core/datafile.ts';
import { flowData } from '../core/flow.ts';
import { ApiFailure, type BacktestApi, type Card, type TickerBars, type TickerEvents } from './types.ts';
import { Compute } from './compute.ts';

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

async function call<T>(base: string, path: string, body?: unknown, service = 'backtest service'): Promise<T> {
  const init: RequestInit = body === undefined ? { credentials:'same-origin' }
    : { method:'POST', credentials:'same-origin', headers:{ 'Content-Type':'application/json', 'X-CSRF-Token':await csrf() }, body:JSON.stringify(body) };
  let res: Response;
  try { res = await fetch(base + path, init) }
  catch { throw new ApiFailure(`The ${service} could not be reached.`, 'NETWORK') }
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) csrfP = null;      // a new session or token is read on the next call
    throw await failure(res, service);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

/* ---- published market data ---------------------------------------------------------------------------------- */
type Dataset = 'price' | 'broker';

async function files(ticker: string, dataset: Dataset): Promise<FileEntry[]> {
  const answer: any = await call(TERMINAL, '/bundle', { ticker, datasets:[dataset], packs:true }, 'market data service');
  const list = answer?.datasets?.[dataset]?.files;
  if (!Array.isArray(list) || !list.length) throw new ApiFailure(`No ${dataset} data is published for ${ticker}.`, 'DATA_MISSING');
  return list.map((f: any) => ({ url:f.url, sha256:f.sha256, bytes:f.bytes }));
}
/* a presigned file (no cookies to the storage host), checked against its manifest entry and inflated */
async function download(f: FileEntry, what: string) {
  let res: Response;
  try { res = await fetch(f.url, { credentials:'omit' }) }
  catch { throw new ApiFailure('A data file could not be downloaded.', 'DATA_UNAVAILABLE') }
  if (!res.ok) throw new ApiFailure(`A data file could not be downloaded (${res.status}).`, 'DATA_UNAVAILABLE', res.status);
  return inflateVerified(new Uint8Array(await res.arrayBuffer()), f, what);
}
const readAll = async (ticker: string, dataset: Dataset) => Promise.all((await files(ticker, dataset)).map((f, k) => download(f, `${ticker} ${dataset} file ${k + 1}`)));

/** the page's TickerBars of a decoded price series */
const tickerBars = (p: PriceSeries): TickerBars => ({ ticker:p.ticker, dates:p.dates as string[], o:p.bars.O as number[], h:p.bars.H as number[], l:p.bars.L as number[], c:p.bars.C as number[], v:p.bars.V as (number | null)[] });
/* a core DataError (its message names the file) or any other decoding error as the page's message */
const dataFailure = (e: unknown, ticker: string) => e instanceof ApiFailure ? e
  : e instanceof DataError ? new ApiFailure(e.message, e.code, 0, e.field)
  : new ApiFailure(`The published data of ${ticker} could not be read (${(e as Error)?.message || e}).`, 'DATA_INTEGRITY');

export function liveApi(): BacktestApi {
  let catalog: Catalog | null = null;
  const compute = new Compute(() => catalog);
  const prices = new Map<string, Promise<PriceSeries>>();
  const flows = new Map<string, Promise<void>>();

  const priceOf = (ticker: string) => {
    let p = prices.get(ticker);
    if (!p) {
      p = readAll(ticker, 'price').then(docs => priceSeries(ticker, docs)).catch(e => { prices.delete(ticker); throw dataFailure(e, ticker) });
      prices.set(ticker, p);
    }
    return p;
  };
  const flowOf = (ticker: string, series: PriceSeries) => {
    let p = flows.get(ticker);
    if (!p) {
      p = readAll(ticker, 'broker').then(docs => { compute.put(tickerBars(series), flowData(brokerRows(docs), series.dates, brokerGaps(docs)), series.bars) })
        .catch(e => { flows.delete(ticker); throw dataFailure(e, ticker) });
      flows.set(ticker, p);
    }
    return p;
  };

  return {
    async catalog() { catalog = await call<Catalog>(BACKTESTS, '/catalog'); return catalog },

    async bars(ticker, opts = {}) {
      const series = await priceOf(ticker);
      if (!compute.has(ticker)) compute.put(tickerBars(series), undefined, series.bars);
      if (opts.flow && catalog?.flow.available && !compute.has(ticker, true)) await flowOf(ticker, series);
      return compute.get(ticker)!;
    },

    ready: (card: Card) => compute.ready(card),
    indicatorOutputs: (ticker, id, params) => compute.indicatorOutputs(ticker, id, params),
    conditionSeries: (ticker, card) => compute.conditionSeries(ticker, card),

    signalsPreview: (req: SignalsPreviewRequest) => call<SignalsPreview>(BACKTESTS, '/signals', req),
    submit: (req: BacktestRequest) => call<{ request_id: string }>(BACKTESTS, '', { ...req, client_request_id:newId() }),
    status: (id: string) => call<JobStatus>(BACKTESTS, `/${encodeURIComponent(id)}`),
    result: (id: string) => call<BacktestResult>(BACKTESTS, `/${encodeURIComponent(id)}/result`),
    events: (id: string, ticker: string) => call<TickerEvents>(BACKTESTS, `/${encodeURIComponent(id)}/events?ticker=${encodeURIComponent(ticker)}`),
    async cancel(id: string) { await call(BACKTESTS, `/${encodeURIComponent(id)}/cancel`, {}) },

    async closes(ticker, calendar) {
      const p = await priceOf(ticker);
      return asOf(p.dates, p.bars.C as (number | null)[], calendar);
    },
  };
}

const newId = () => typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36);
