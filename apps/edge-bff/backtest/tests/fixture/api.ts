/* The fixture BacktestApi (src/api/types.ts) for the 1:1 check: the reference page's synthetic market (10 demo tickers
   and IHSG, 2019-01-02 .. 2026-10-23, every weekday), its demo formulas for every card and indicator output, and its
   mock-up engine for a run (run.ts), so the page shows the reference's numbers. Built only into dist-fixture/
   (vite build --mode fixture, tests/fixture/main.ts); never part of dist/.
   Jobs answer like edge-bff: FINISHED at the first status call (the reference computes in one go), /result and
   /events?ticker= as edge-bff serves them (../served.ts). The texts on the data are the reference's own words. */
import type { BacktestRequest, BacktestResult, Catalog, JobStatus } from '../../src/core/contract.ts';
import { REGISTRY_VERSION } from '../../src/core/registry.ts';
import type { BacktestApi, Card, SourceTexts, TickerBars } from '../../src/api/types.ts';
import * as M from './mockup.js';
import { ENGINE_VERSION, newSession, previewRequest, runRequest } from './run.ts';
import { servedEvents, servedResult } from '../served.ts';

const BANKS: string[] = ['BBCA', 'BBRI', 'BMRI'];                    // the reference's universe BANK (section 6 universe)
const STOCKS: string[] = M.TICKERS.map((t: [string]) => t[0]);

/* the reference's choices as a catalog: its tickers in its order, its two universes with its labels, its brokers, its
   broker data on every day; the reference has no limit on conditions */
export const CATALOG: Catalog = {
  schema_version:1, engine_version:ENGINE_VERSION, registry_version:REGISTRY_VERSION,
  data_through:M.DAYS[M.N - 1], first_date:M.DAYS[0],
  tickers:[...STOCKS.map(t => ({ ticker:t, name:t, type:'stock', sector:BANKS.includes(t) ? 'Banks' : null })), { ticker:'IHSG', name:'IHSG', type:'index', sector:null }],
  universes:[{ id:'all', label:'Demo 10 (LQ45 sample)', tickers:STOCKS.length }, { id:'sector:Banks', label:'Banks (BBCA, BBRI, BMRI)', tickers:BANKS.length }],
  flow:{ available:true, reason:null, brokers:M.BROKERS, data_through:M.DAYS[M.N - 1] },
  limits:{ max_positions:10, window_bars:{ min:1, max:20 }, monte_carlo_runs:1000, max_download_bytes:0, max_broker_rows:0, timeout_seconds:600, queued_per_owner:1,
           max_conditions:Infinity },
};

/* the reference's words (backtest.html: the header, the Robustness warning box, "Variants tried this session") */
export const REFERENCE_TEXTS: SourceTexts = {
  dataNote: () => 'Synthetic demo data · long-only',
  robustnessWarning: () => '⚠︎ Synthetic data, single market path. Before trusting a result: keep the out-of-sample untouched while tuning, include delisted stocks (survivorship), adjust prices for corporate actions, and re-check liquidity of every fill.',
  trials: 'this session',
};

const DAY = new Map<string, number>(M.DAYS.map((d: string, i: number) => [d, i]));

function barsOf(t: string): TickerBars {
  if (t === 'IHSG') return { ticker:t, dates:M.DAYS, o:M.IHSG, h:M.IHSG, l:M.IHSG, c:M.IHSG, v:M.IHSG.map(() => null) };
  const D = M.DATA[t];
  if (!D) throw new Error(`No price data is published for ${t}.`);
  return { ticker:t, dates:M.DAYS, o:D.o, h:D.h, l:D.l, c:D.c, v:D.v };
}

export function fixtureApi(): BacktestApi {
  const session = newSession();
  const jobs = new Map<string, { request: BacktestRequest; result: BacktestResult; cancelled?: boolean }>();
  /* answers are asynchronous like the network's, and arrive at once (the reference has its data at hand) */
  const now = <T>(f: () => T) => Promise.resolve().then(f);
  const status = (id: string, state: JobStatus['state']): JobStatus =>
    ({ request_id:id, state, progress:null, error:null, created_at:'2026-10-26T00:00:00Z', started_at:null, finished_at:null, duration_ms:null, result_bytes:null });
  const job = (id: string) => { const j = jobs.get(id); if (!j) throw new Error(`fixture: no job ${id}`); return j };
  return {
    texts: REFERENCE_TEXTS,
    catalog: () => now(() => CATALOG),
    bars: t => now(() => barsOf(t)),
    ready: (c: Card) => M.condReady(c),
    indicatorOutputs: (t, id, p) => M.regReady(id) && M.DATA[t] ? M.memo(t, 'reg' + id + JSON.stringify(p), () => M.REG_CALC[id](M.DATA[t], p)) : null,
    conditionSeries: (t, c) => M.condReady(c) && M.DATA[t] ? M.catOf(c).eval(t, c) : null,
    signalsPreview: q => now(() => previewRequest(q)),
    submit: q => now(() => {
      const request = JSON.parse(JSON.stringify(q)) as BacktestRequest, { result } = runRequest(request, session);
      const id = `fixture-${session.runs}`;
      jobs.set(id, { request, result });
      return { request_id:id };
    }),
    status: id => now(() => status(id, job(id).cancelled ? 'CANCELLED' : 'FINISHED')),
    result: id => now(() => { const j = job(id); return servedResult(j.result, j.request.single?.ticker ?? null) }),
    events: (id, t) => now(() => servedEvents(job(id).result, t)),
    cancel: id => now(() => { const j = jobs.get(id); if (j) j.cancelled = true }),
    closes: (t, cal) => now(() => { const c: number[] = M.closeOf(t); return cal.map(d => { const i = DAY.get(d); return i === undefined ? null : c[i] }) }),
  };
}
