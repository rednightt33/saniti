/* EXEC-MU-ACCOUNTS 3e, the example mode as the user set it on 2026-11-21 (ERRORS M527): "the Backtest the page's
   default setup (MAPI, single stock) over one year to 30 October 2026". The BacktestApi of the page opened with
   ?example=1 for a principal holding backtest.example: everything comes from the example's files
   (/api/v1/examples/backtest, edge-bff app/examples.py), written once by the capture job
   (apps/terminal-publisher/examples.py backtest_files):
     backtest-catalog        the worker's catalog from the period's first day to the example's date (so the page's own
                             default period is that year)
     backtest-request        the request the page's own code builds on that catalog (backtest_request.ts)
     backtest-result         the real worker's result of that request
     backtest-bars-<ticker>  the ticker's final daily prices of the period (the chart)
   The page opens with the run done (boot autorun): its submit is answered with the stored run when the page's request
   is the stored one (the cards' random ids aside), else refused; the cards' series are the run's own condition tracks
   (the worker computed them on the whole history; no broker file is sent). Nothing else is asked: no Terminal data, no
   job. The page stays still (shared/example-view.ts): a click asks to sign in or to upgrade. */
import type { BacktestRequest, BacktestResultCore, Catalog, Condition, JobStatus, SignalTrack } from '../core/contract.ts';
import { ApiFailure, type BacktestApi, type Card, type TickerBars, type TickerEvents } from './types.ts';
import { PUBLISHED_TEXTS } from './texts.ts';
import { toWire } from './compute.ts';

const BASE = '/api/v1/examples/backtest';
const ID = 'example';
const NOT_HERE = 'This is an example of the Backtest: sign in or upgrade to change it and run your own.';

interface Index { finished_at: string | null; as_of: string; files: Record<string, { sha256: string }> }

async function getJson<T>(url: string): Promise<T> {
  let r: Response;
  try { r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } }) }
  catch { throw new ApiFailure('The example could not be reached. Check the connection and reload the page.', 'NETWORK') }
  let body: any = null;
  try { body = await r.json() } catch { body = null }
  if (!r.ok) {
    const e = body && typeof body.error === 'object' ? body.error : null;
    throw new ApiFailure(e?.message || 'The example could not be read. Try again in a minute.', e?.code || `HTTP_${r.status}`, r.status);
  }
  return body as T;
}

/** a JSON value with every object's keys in order, so two values compare by their content alone */
const canonical = (v: unknown): unknown => Array.isArray(v) ? v.map(canonical)
  : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, canonical((v as Record<string, unknown>)[k])]))
    : v;
/** a condition as its form, without its id (the page's cards get random ids; the stored request has its own) */
const form = (c: Condition) => JSON.stringify(canonical({ ...c, id: '' }));
/** a request as its form, every condition's id aside (the page's request and the stored one compare by it) */
export const requestForm = (q: BacktestRequest) => JSON.stringify(canonical({
  ...q, entry: { ...q.entry, conditions: q.entry.conditions.map(c => ({ ...c, id: '' })) },
  exit: { ...q.exit, signals: { ...q.exit.signals, conditions: q.exit.signals.conditions.map(c => ({ ...c, id: '' })) } },
}));

export function exampleApi(): BacktestApi {
  let index: Promise<Index> | null = null;
  const file = async <T>(name: string): Promise<T> => {
    const i = await (index ??= getJson<Index>(`${BASE}/index`));
    const e = i.files[name];
    if (!e) throw new ApiFailure(`The example has no ${name}. Reload the page.`, 'EXAMPLE_FILE_NOT_FOUND', 404);
    return getJson<T>(`${BASE}/file/${encodeURIComponent(name)}?sha=${e.sha256}`);
  };
  let stored: Promise<{ request: BacktestRequest; result: BacktestResultCore }> | null = null;
  const run = () => stored ??= Promise.all([file<BacktestRequest>('backtest-request'), file<BacktestResultCore>('backtest-result')])
    .then(([request, result]) => ({ request, result }));
  // the stored request's conditions by their form (known with the catalog: the page builds no request before it), and
  // the stored run's condition tracks by the same form, as 0/1 series on the loaded bars (filled by bars())
  const forms = new Set<string>();
  const series = new Map<string, Uint8Array>();
  let shown: TickerBars | null = null, request: BacktestRequest | null = null, result: BacktestResultCore | null = null;
  // the page's ids of the stored conditions (set when the page submits its request: the run then names them)
  let ids = new Map<string, string>();

  const onBars = (bars: TickerBars, q: BacktestRequest, r: BacktestResultCore) => {
    const at = new Map(r.dates.map((d, k) => [d, k] as [string, number]));
    const of = (track: SignalTrack) => {
      const on = new Uint8Array(r.dates.length);
      for (let k = 0; k + 1 < track.runs.length; k += 2) for (let j = track.runs[k]; j <= track.runs[k + 1]; j++) on[j] = 1;
      return Uint8Array.from(bars.dates, d => (at.has(d) ? on[at.get(d) as number] : 0));
    };
    const tracks = new Map((r.events.conditions || []).filter(c => c.ticker === bars.ticker).map(c => [c.condition_id, c.track] as [string, SignalTrack]));
    for (const c of [...q.entry.conditions, ...q.exit.signals.conditions]) {
      const t = tracks.get(c.id);
      if (t) series.set(form(c), of(t));
    }
  };
  const named = <T>(x: T): T => {
    if (!ids.size) return x;
    const swap = (v: unknown): unknown => Array.isArray(v) ? v.map(swap)
      : v && typeof v === 'object' ? Object.fromEntries(Object.entries(v).map(([k, w]) => [k, k === 'condition_id' && typeof w === 'string' && ids.has(w) ? ids.get(w) : swap(w)]))
        : v;
    return swap(x) as T;
  };
  const cardForm = (card: Card) => { try { return form(toWire(card)) } catch { return '' } };
  const finished = (): JobStatus => ({ request_id: ID, state: 'FINISHED', progress: null, error: null, created_at: null,
    started_at: null, finished_at: null, duration_ms: result?.meta.duration_ms ?? null, result_bytes: null } as unknown as JobStatus);

  return {
    texts: PUBLISHED_TEXTS,
    async catalog() {
      const [cat, s] = await Promise.all([file<Catalog>('backtest-catalog'), run()]);
      for (const c of [...s.request.entry.conditions, ...s.request.exit.signals.conditions]) forms.add(form(c));
      return cat;
    },
    async bars(ticker: string) {
      const s = await run();
      request = s.request; result = s.result;
      if (ticker !== s.request.single?.ticker) throw new ApiFailure(`This example shows ${s.request.single?.ticker} only. ${NOT_HERE}`, 'EXAMPLE', 403);
      if (!shown) {
        shown = await file<TickerBars>(`backtest-bars-${ticker.toLowerCase()}`);
        onBars(shown, s.request, s.result);
      }
      return shown;
    },
    ready: card => forms.has(cardForm(card)),
    indicatorOutputs: () => null,
    conditionSeries: (ticker, card) => (shown && ticker === shown.ticker ? series.get(cardForm(card)) ?? null : null),
    tracks: () => {},
    tracked: () => null,
    screenerCatalog: () => Promise.reject(new ApiFailure(`The condition window is not part of the example. ${NOT_HERE}`, 'EXAMPLE', 403)),
    signalsPreview: () => Promise.reject(new ApiFailure(NOT_HERE, 'EXAMPLE', 403)),
    async submit(q: BacktestRequest) {
      const s = await run();
      if (requestForm(q) !== requestForm(s.request)) throw new ApiFailure(NOT_HERE, 'EXAMPLE', 403);
      const mine = [...q.entry.conditions, ...q.exit.signals.conditions], theirs = [...s.request.entry.conditions, ...s.request.exit.signals.conditions];
      ids = new Map(theirs.map((c, k) => [c.id, mine[k].id] as [string, string]));
      request = s.request; result = s.result;
      return { request_id: ID };
    },
    status: async () => finished(),
    result: async () => named((await run()).result),
    async events(_id: string, ticker: string): Promise<TickerEvents> {
      const r = (await run()).result;
      return named({ conditions: (r.events.conditions || []).filter(c => c.ticker === ticker), exits: r.events.exits?.[ticker] ? { [ticker]: r.events.exits[ticker] } : {} });
    },
    cancel: async () => {},
    closes: () => Promise.reject(new ApiFailure(NOT_HERE, 'EXAMPLE', 403)),
  };
}
