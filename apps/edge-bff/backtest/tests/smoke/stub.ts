/* A tiny BacktestApi for the Playwright smoke run (smoke.mjs): six stocks and IHSG with bars drawn from a few smooth
   waves (generated here, not by the reference's generator), the page's calculations with the shared core (compute.ts),
   and a job that answers like edge-bff: one RUNNING status, then FINISHED with a result assembled by the core's
   result.ts from a small hand-made ledger (one fixed-length trade per entry event). The numbers only need to be
   valid; the smoke run checks that the page boots and renders every view without a console error. */
import type { BacktestRequest, BacktestResult, Catalog, JobStatus, SignalsPreviewRequest, SignalTrack } from '../../src/core/contract.ts';
import type { Ledger, LedgerTrade, ResultInput } from '../../src/core/ledger.ts';
import { Calc } from '../../src/core/conditions.ts';
import { REGISTRY_VERSION } from '../../src/core/registry.ts';
import { buildResult } from '../../src/core/result.ts';
import { sensitivityPlan } from '../../src/core/robustness.ts';
import { barMap, conditionsWithin, previewRow, resultCalendar, signalSummary, tickerSignals, track } from '../../src/core/signals.ts';
import { Compute, toBars } from '../../src/api/compute.ts';
import type { BacktestApi, TickerBars, TickerEvents } from '../../src/api/types.ts';

const STOCKS: [string, string, string][] = [
  ['MAPI', 'Mitra Adiperkasa', 'Consumer'], ['ACES', 'Aspirasi Hidup Indonesia', 'Consumer'], ['BBCA', 'Bank Central Asia', 'Finance'],
  ['BBRI', 'Bank Rakyat Indonesia', 'Finance'], ['TLKM', 'Telkom Indonesia', 'Infrastructure'], ['ASII', 'Astra International', 'Industrials'],
];

/* weekdays from 2019-01-02 to 2022-12-30 */
const DATES: string[] = (() => {
  const out: string[] = [];
  for (let t = Date.UTC(2019, 0, 2); t <= Date.UTC(2022, 11, 30); t += 864e5) { const d = new Date(t), w = d.getUTCDay(); if (w && w < 6) out.push(d.toISOString().slice(0, 10)) }
  return out;
})();

/* smooth waves around a level, a slow drift and a volume burst every 37 bars */
function bars(ticker: string, k: number): TickerBars {
  const n = DATES.length, o = new Float64Array(n), h = new Float64Array(n), l = new Float64Array(n), c = new Float64Array(n);
  const v: (number | null)[] = new Array(n);
  const base = ticker === 'IHSG' ? 6000 : 800 + 350 * k;
  for (let i = 0; i < n; i++) {
    c[i] = Math.round(base * (1 + .22 * Math.sin(i / 47 + k) + .07 * Math.sin(i / 8.5 + 2 * k) + .03 * Math.sin(i / 3.1 + k) + i / 5000));
    o[i] = i ? c[i - 1] : c[i];
    h[i] = Math.round(Math.max(o[i], c[i]) * (1.004 + .004 * (1 + Math.sin(i / 2.3))));
    l[i] = Math.round(Math.min(o[i], c[i]) * (.996 - .004 * (1 + Math.cos(i / 2.9))));
    v[i] = ticker === 'IHSG' ? null : Math.round(1e6 * (1.3 + Math.sin(i / 6 + k)) * (i % 37 === 0 ? 3 : 1));
  }
  return { ticker, dates:DATES, o, h, l, c, v };
}
const ALL: Record<string, TickerBars> = Object.fromEntries([...STOCKS.map(([t], k) => [t, bars(t, k)]), ['IHSG', bars('IHSG', 7)]]);

export const CATALOG: Catalog = {
  schema_version:1, engine_version:'stub', registry_version:REGISTRY_VERSION,
  data_through:DATES[DATES.length - 1], first_date:DATES[0],
  tickers:[...STOCKS.map(([ticker, name, sector]) => ({ ticker, name, type:'stock', sector })), { ticker:'IHSG', name:'Composite Index', type:'index', sector:null }],
  universes:[{ id:'all', label:`All stocks (${STOCKS.length})`, tickers:STOCKS.length },
    ...[...new Set(STOCKS.map(s => s[2]))].map(s => ({ id:`sector:${s}`, label:`${s} (${STOCKS.filter(x => x[2] === s).length})`, tickers:STOCKS.filter(x => x[2] === s).length }))],
  flow:{ available:false, reason:'Broker data not verified yet', brokers:['YU', 'CC', 'PD', 'AK'] },
  limits:{ max_positions:10, window_bars:{ min:1, max:20 }, monte_carlo_runs:1000, max_download_bytes:5e8, max_broker_rows:5e6, timeout_seconds:600, queued_per_owner:2 },
};
const members = (u: string) => STOCKS.filter(s => u === 'all' || u === `sector:${s[2]}`).map(s => s[0]);
const calcs = new Map<string, Calc>();
const calcOf = (t: string) => { let c = calcs.get(t); if (!c) calcs.set(t, c = new Calc(toBars(ALL[t]))); return c };
const asOf = (dates: readonly string[], vals: ArrayLike<number>, cal: readonly string[]) => { const m = barMap(dates, cal); return Array.from(m.asof, j => j >= 0 ? vals[j] : null) };

/* ---- the job: a ledger of one fixed-length trade per entry event, the result by the core ------------------------ */
const WHY = ['take_profit', 'stop_loss', 'time_exit', 'exit_signal', 'trailing_stop'] as const;
function ledgerOf(q: BacktestRequest, scale = 1): Ledger {
  const tickers = q.mode === 'single' ? [q.single!.ticker] : members(q.portfolio!.universe);
  const dates = resultCalendar(q.period.from, q.period.to, [ALL.IHSG.dates, ...tickers.map(t => ALL[t].dates)]), n = dates.length;
  const cap0 = q.sizing.capital_idr, slots = q.mode === 'single' ? 1 : q.portfolio!.max_positions;
  const per = q.mode === 'single' ? cap0 * q.sizing.allocation_fraction : cap0 / slots;
  const events: Ledger['events'] = { conditions:[], entries:{}, exits:{}, skipped:[] };
  const trades: LedgerTrade[] = [], per_ticker_signals: Ledger['per_ticker_signals'] = [];
  for (const t of tickers) {
    const B = ALL[t], m = barMap(B.dates, dates), sig = tickerSignals(calcOf(t), q);
    const entries = track(sig.entry, m);
    events.entries[t] = entries; events.exits[t] = track(sig.exit, m);
    for (const x of [...sig.entryConditions, ...sig.exitConditions]) events.conditions.push({ condition_id:x.id, ticker:t, track:track(x.s, m) });
    per_ticker_signals.push({ ticker:t, ...signalSummary(entries, dates) });
    let free = -1;
    entries.on.forEach((k, e) => {
      const j = m.cal[k], ej = j + 1, xj = Math.min(j + 6, m.last);
      if (ej > m.last || ej <= free || xj <= ej) return;
      const entry = B.o[ej] * (1 + q.costs.slippage), exit = B.c[xj] * (1 - q.costs.slippage), shares = Math.max(100, Math.floor(per / entry / 100) * 100);
      const cost = shares * entry * (1 + q.costs.buy_fee), proceeds = shares * exit * (1 - q.costs.sell_fee), pnl = (proceeds - cost) * scale;
      let lo = Infinity, hi = -Infinity; for (let i = ej; i <= xj; i++) { lo = Math.min(lo, B.l[i]); hi = Math.max(hi, B.h[i]) }
      trades.push({ ticker:t, signal_bar:k, signal_event:e, entry_bar:m.bar[ej], entry_price:entry, exit_bar:m.bar[xj], exit_price:exit, exit_reason:WHY[e % WHY.length],
        exit_phase:'close', shares, bars_held:xj - ej + 1, cost_idr:cost, proceeds_idr:cost + pnl, pnl_idr:pnl, return:pnl / cost,
        mae:Math.min(0, lo / entry - 1), mfe:Math.max(0, hi / entry - 1), initial_stop:entry * (1 - q.exit.stop.pct), initial_target:entry * (1 + q.exit.take_profit.pct),
        initial_risk_pct:q.exit.stop.pct, entry_condition_ids:conditionsWithin(sig, j), flags:{ corporate_actions:[], stop_and_target_same_bar:false, stale_mark:false } });
      free = xj;
    });
  }
  trades.sort((a, b) => a.exit_bar - b.exit_bar || a.ticker.localeCompare(b.ticker));
  // equity: the capital plus the closed trades' P&L and the open trades marked at the close
  const equity = new Array(n).fill(cap0), exposure = new Array(n).fill(0);
  for (const tr of trades) {
    const B = ALL[tr.ticker], m = barMap(B.dates, dates);
    for (let k = tr.entry_bar; k < n; k++) {
      if (k >= tr.exit_bar) { equity[k] += tr.pnl_idr; continue }
      const j = m.asof[k], mv = tr.shares * B.c[j];
      equity[k] += (mv - tr.cost_idr) * scale; exposure[k] += mv;
    }
  }
  for (let k = 0; k < n; k++) exposure[k] = Math.min(1, exposure[k] / equity[k]);
  const bm = q.mode === 'single' && q.single!.benchmark === 'buy_and_hold' ? q.single!.ticker : 'IHSG';
  return { dates, equity, exposure, benchmark_close:asOf(ALL[bm].dates, ALL[bm].c, dates) as number[],
    benchmark:{ kind:bm === 'IHSG' ? 'ihsg' : 'buy_and_hold', ticker:bm }, trades, events, per_ticker_signals,
    warnings:q.mode === 'portfolio' ? [{ code:'SURVIVORSHIP', message:'Today’s universe; delisted tickers are not included.' }] : [] };
}

export function resultOf(q: BacktestRequest, runs: number): BacktestResult {
  const plan = sensitivityPlan(q);
  const input: ResultInput = {
    request:q, ledger:ledgerOf(q),
    versions:{ engine_version:'stub', registry_version:REGISTRY_VERSION, data_version:'stub', data_through:CATALOG.data_through },
    tickers:q.mode === 'single' ? [q.single!.ticker] : members(q.portfolio!.universe),
    prior_trials:Array.from({ length:runs - 1 }, (_, k) => ({ variant_hash:`prior-${k}`, sharpe_daily:.02 * Math.sin(k + 1) })),
    variant_hash:`run-${runs}`, lineage_key:'stub', request_hash:`stub-${runs}`,
    sensitivity:plan && { condition_id:plan.condition_id, xs:plan.xs, xs_display:plan.xs_display, y_key:plan.y_key, ys:plan.ys, ys_display:plan.ys_display,
      base_x:plan.base_x, base_y:plan.base_y,
      cells:plan.requests.map((row, i) => row.map((v, j) => (v ? { ledger:ledgerOf(v, .6 + .1 * (i + j)), variant_hash:`cell-${runs}-${i}-${j}` } : null) as any)) },
    duration_ms:1234,
  };
  return buildResult(input);
}

export function stubApi(): BacktestApi {
  const compute = new Compute(() => CATALOG);
  const jobs = new Map<string, { polls: number; request: BacktestRequest; result?: BacktestResult; cancelled?: boolean }>();
  let runs = 0;
  const later = <T>(v: () => T, ms = 20) => new Promise<T>((ok, no) => setTimeout(() => { try { ok(v()) } catch (e) { no(e) } }, ms));
  const status = (id: string, state: JobStatus['state'], progress: JobStatus['progress']): JobStatus =>
    ({ request_id:id, state, progress, error:null, created_at:'2026-10-26T00:00:00Z', started_at:null, finished_at:null, duration_ms:null, result_bytes:null });
  return {
    catalog: () => later(() => CATALOG),
    bars: (t: string) => later(() => { if (!ALL[t]) throw new Error(`No price data is published for ${t}.`); if (!compute.has(t)) compute.put(ALL[t]); return compute.get(t)! }),
    ready: c => compute.ready(c),
    indicatorOutputs: (t, id, p) => compute.indicatorOutputs(t, id, p),
    conditionSeries: (t, c) => compute.conditionSeries(t, c),
    signalsPreview: (req: SignalsPreviewRequest) => later(() => ({ data_version:'stub',
      rows:members(req.universe).map(t => ({ ticker:t, ...previewRow(calcOf(t), ALL[t].dates, req, req.period.from, req.period.to) })) })),
    submit: req => later(() => { const id = `stub-${++runs}`; jobs.set(id, { polls:0, request:JSON.parse(JSON.stringify(req)) }); return { request_id:id } }),
    status: id => later(() => {
      const j = jobs.get(id)!;
      if (j.cancelled) return status(id, 'CANCELLED', null);
      return j.polls++ < 1 ? status(id, 'RUNNING', { phase:'sensitivity', done:12, total:25 }) : status(id, 'FINISHED', null);
    }),
    result: id => later(() => {
      const j = jobs.get(id)!;
      const r = j.result ||= resultOf(j.request, runs);
      // edge-bff's /result: the core part, plus the single ticker's condition and exit tracks in single mode
      return j.request.mode === 'single' ? r : { ...r, events:{ ...r.events, conditions:[], exits:{} } };
    }),
    events: (id, t) => later((): TickerEvents => {
      const r = jobs.get(id)!.result!;
      return { conditions:r.events.conditions.filter(c => c.ticker === t), exits:{ [t]:r.events.exits[t] as SignalTrack } };
    }),
    cancel: id => later(() => { const j = jobs.get(id); if (j) j.cancelled = true }),
    closes: (t, cal) => later(() => asOf(ALL[t].dates, ALL[t].c, cal)),
  };
}
