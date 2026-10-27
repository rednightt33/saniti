/* A tiny BacktestApi for the Playwright smoke run (smoke.mjs): six stocks and IHSG with bars drawn from a few smooth
   waves (generated here, not by the reference's generator), the page's calculations with the shared core (compute.ts),
   and a job that answers like edge-bff: one RUNNING status, then FINISHED with a result assembled by the core's
   result.ts from a small hand-made ledger (one fixed-length trade per entry event). The numbers only need to be
   valid; the smoke run checks that the page boots and renders every view without a console error. The texts on the
   data are the production page's (src/api/texts.ts).
   Portfolios run on the picked stocks in ticker order (the worker sorts them, PF3); /events?ticker= answers a ticker
   the run did not have with edge-bff's 404 EVENTS_NOT_FOUND (../served.ts). The catalog's groupings (sector,
   industry) are derived from the stocks' own columns as the worker derives them from terminal-api's reference file
   (PF6: a null value is unclassified, counted apart).
   stubApi({ hostile: true }) (smoke.mjs, ?hostile=1) is the same market with markup in every string the server, the
   catalog or an error gives the page: a ticker, its name, its sector and industry (the picker's filters), a broker,
   the flow reason, the result's and the preview's warnings (the preview leaves the markup ticker out, with a markup
   reason), job ids and an error message (the events of ACES); the page escapes all of them.
   stubApi({ wide: true }) (?wide=1) adds eight stocks whose data cannot serve any strategy: the preview and the run
   leave them out (TICKERS_EXCLUDED, INDICATOR_OUTPUT_EMPTY), as the worker leaves out such a stock; with them a
   portfolio reaches the limit of 12 picked stocks. It also has a published stock without price files (WID0, no
   sector or industry): its bars are the live API's DATA_MISSING, and the preview and the run leave it out with the
   worker's DATA_MISSING (load.ts skipUnpublished).
   window.__replaceNextPreview = true makes the next preview answer edge-bff's 409 PREVIEW_REPLACED (another tab of
   the owner asked a newer one).
   stubApi({ flow: true }) (?flow=1) has flow available, its broker data published through 20 bars before the last
   price bar, and refuses a run that reads the broker files past that day as the worker does (FLOW_DATA_THROUGH, its
   code, field and message); it runs nothing else that reads them (the stub has no broker data). */
import type { BacktestRequest, BacktestResult, Catalog, JobStatus, SignalsPreviewRequest, Warning } from '../../src/core/contract.ts';
import type { Ledger, LedgerTrade, ResultInput } from '../../src/core/ledger.ts';
import { Calc } from '../../src/core/conditions.ts';
import { REGISTRY_VERSION } from '../../src/core/registry.ts';
import { buildResult } from '../../src/core/result.ts';
import { sensitivityPlan } from '../../src/core/robustness.ts';
import { barMap, byTicker, conditionsWithin, leftOut, previewRow, requestConditions, resultCalendar, signalSummary, tickerSignals, track, unlessLeftOut, type Exclusion } from '../../src/core/signals.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../src/core/engine.ts';
import { Compute, toBars } from '../../src/api/compute.ts';
import { PUBLISHED_TEXTS } from '../../src/api/texts.ts';
import { ApiFailure, type BacktestApi, type TickerBars } from '../../src/api/types.ts';
import { readsFlow } from '../../src/api/request.ts';
import { servedEvents, servedResult } from '../served.ts';

/* ticker, name, sector, industry (null: unclassified) */
type StockRow = [string, string, string | null, string | null];
const STOCKS: StockRow[] = [
  ['MAPI', 'Mitra Adiperkasa', 'Consumer', 'Retail'], ['ACES', 'Aspirasi Hidup Indonesia', 'Consumer', 'Retail'], ['BBCA', 'Bank Central Asia', 'Finance', 'Banks'],
  ['BBRI', 'Bank Rakyat Indonesia', 'Finance', 'Banks'], ['TLKM', 'Telkom Indonesia', 'Infrastructure', 'Telecommunication'], ['ASII', 'Astra International', 'Industrials', null],
];
/* the wide market's stocks whose data serves no strategy (left out of every preview and run), and its stock in the
   catalog without price files */
const UNSERVED: StockRow[] = Array.from({ length:8 }, (_, k) => [`WID${k + 1}`, `Wide Stock ${k + 1}`, 'Wide', null]);
const NO_BARS: StockRow[] = [['WID0', 'Wide Stock 0', null, null]];
/** markup that runs (sets window.__xss) if the page puts it into its markup unescaped; the suffix tells where it came from */
export const XSS = (where: string) => `"'><img src=x onerror="window.__xss=(window.__xss||[]).concat('${where}')">${where}`;
const HOSTILE_STOCKS: StockRow[] = [...STOCKS.slice(0, 5), [XSS('ticker'), XSS('name'), XSS('sector'), XSS('industry')]];

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
/* the catalog's groupings of these stocks, as the worker derives them (catalog.ts groupingsOf): per column, each value
   with its number of stocks in value order (byTicker), and the stocks without a value apart */
const GROUP_KEYS = ['sector', 'industry'];
const groupingsOf = (stocks: StockRow[]) => GROUP_KEYS.map((key, k) => {
  const counts = new Map<string, number>(); let unclassified = 0;
  for (const s of stocks) { const v = s[k + 2]; if (v === null) unclassified++; else counts.set(v, (counts.get(v) || 0) + 1) }
  return { key, values:[...counts.keys()].sort(byTicker).map(value => ({ value, tickers:counts.get(value)! })), unclassified };
});
/* one market of stocks: its bars, its catalog (flow off unless `flow`; at most 4 enabled conditions per list, so the
   smoke run meets the limit; the portfolio limits are the core's), the stocks it leaves out, and a Calc per ticker;
   `noBars` are in the catalog without bars */
function market(stocks: StockRow[], hostile: boolean, flow = false, unserved: StockRow[] = [], noBars: StockRow[] = []) {
  const withBars = [...stocks, ...unserved], listed = [...withBars, ...noBars];
  const all: Record<string, TickerBars> = Object.fromEntries([...withBars.map(([t], k) => [t, bars(t, k)]), ['IHSG', bars('IHSG', 7)]]);
  const catalog: Catalog = {
    schema_version:1, engine_version:'stub', registry_version:REGISTRY_VERSION,
    data_through:DATES[DATES.length - 1], first_date:DATES[0],
    tickers:[...listed.map(([ticker, name, sector, industry]) => ({ ticker, name, type:'stock', groups:{ sector, industry } })),
      { ticker:'IHSG', name:hostile ? null : 'Composite Index', type:'index', groups:{ sector:null, industry:null } }],
    groupings:groupingsOf(listed),
    flow:flow ? { available:true, reason:null, brokers:['YU', 'CC', 'PD', 'AK'], data_through:DATES[DATES.length - 21] }
      : { available:false, reason:hostile ? XSS('flow reason') : 'Broker data not verified yet', brokers:['YU', 'CC', 'PD', ...(hostile ? [XSS('broker')] : ['AK'])], data_through:null },
    limits:{ max_positions:MAX_POSITIONS, window_bars:{ min:1, max:20 }, monte_carlo_runs:1000, max_portfolio_tickers:MAX_PORTFOLIO_TICKERS,
             max_download_bytes:5e8, max_broker_rows:5e6, timeout_seconds:600, queued_per_owner:2, max_conditions:4 },
  };
  const calcs = new Map<string, Calc>(), left = new Set(unserved.map(s => s[0]));
  /* a stock the market leaves out: the error the worker gives a stock without price files, or without any value of
     the entry rule's series */
  const unservedError = (t: string): Exclusion | null => !all[t]
    ? { ticker:t, code:'DATA_MISSING', field:`${t}.price`, message:`No price file is published for ${t}.` }
    : left.has(t) ? { ticker:t, code:'INDICATOR_OUTPUT_EMPTY', field:'entry.conditions', message:`${t} has no value of the entry conditions on its bars up to the end of the period.` } : null;
  return { hostile, all, catalog, unservedError,
           calcOf:(t: string) => { let c = calcs.get(t); if (!c) calcs.set(t, c = new Calc(toBars(all[t]))); return c } };
}
type Market = ReturnType<typeof market>;
const PLAIN = market(STOCKS, false), HOSTILE = market(HOSTILE_STOCKS, true), FLOW = market(STOCKS, false, true), WIDE = market(STOCKS, false, false, UNSERVED, NO_BARS);
/** the stocks a request runs on: single its ticker; portfolio the picked stocks in ticker order (the worker's order) */
const requested = (q: BacktestRequest) => q.mode === 'single' ? [q.single!.ticker] : [...q.portfolio!.tickers].sort(byTicker);
/** the stocks of a request the market runs, and the warning on the ones it leaves out (core/signals.ts leftOut) */
function runnable(q: BacktestRequest, mk: Market) {
  const excluded = requested(q).map(mk.unservedError).filter((x): x is Exclusion => !!x), out = new Set(excluded.map(x => x.ticker));
  const tickers = requested(q).filter(t => !out.has(t));
  return { tickers, warning:q.mode === 'portfolio' ? leftOut(excluded, tickers.length, 'portfolio.tickers', 'run') : null };
}
export const CATALOG = PLAIN.catalog;
const asOf = (dates: readonly string[], vals: ArrayLike<number>, cal: readonly string[]) => { const m = barMap(dates, cal); return Array.from(m.asof, j => j >= 0 ? vals[j] : null) };

/* ---- the job: a ledger of one fixed-length trade per entry event, the result by the core ------------------------ */
const WHY = ['take_profit', 'stop_loss', 'time_exit', 'exit_signal', 'trailing_stop'] as const;
function ledgerOf(q: BacktestRequest, mk: Market, scale = 1): Ledger {
  const { all:ALL, calcOf } = mk, { tickers, warning } = runnable(q, mk);
  // the calendar: IHSG and every requested stock with bars, run or left out (PF8)
  const dates = resultCalendar(q.period.from, q.period.to, [ALL.IHSG.dates, ...requested(q).filter(t => ALL[t]).map(t => ALL[t].dates)]), n = dates.length;
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
    warnings:[...(warning ? [warning] : []), ...(q.mode === 'portfolio' ? [{ code:'SURVIVORSHIP', message:'Today’s universe; delisted tickers are not included.' }] : []),
      ...(mk.hostile ? [hostileWarning('result')] : [])] };
}
const hostileWarning = (where: string): Warning => ({ code:'TICKERS_EXCLUDED', message:XSS(`${where} warning`), count:1, tickers:[XSS(`${where} warning ticker`)],
  reasons:[{ ticker:XSS(`${where} warning ticker`), code:XSS(`${where} warning code`), message:XSS(`${where} warning reason`) }] });

export function resultOf(q: BacktestRequest, runs: number, mk: Market = PLAIN): BacktestResult {
  const plan = sensitivityPlan(q);
  const input: ResultInput = {
    request:q, ledger:ledgerOf(q, mk),
    versions:{ engine_version:'stub', registry_version:REGISTRY_VERSION, data_version:'stub', data_through:mk.catalog.data_through },
    tickers:runnable(q, mk).tickers,
    prior_trials:Array.from({ length:runs - 1 }, (_, k) => ({ variant_hash:`prior-${k}`, sharpe_daily:.02 * Math.sin(k + 1) })),
    variant_hash:`run-${runs}`, lineage_key:'stub', request_hash:`stub-${runs}`,
    sensitivity:plan && { condition_id:plan.condition_id, xs:plan.xs, xs_display:plan.xs_display, y_key:plan.y_key, ys:plan.ys, ys_display:plan.ys_display,
      base_x:plan.base_x, base_y:plan.base_y,
      cells:plan.requests.map((row, i) => row.map((v, j) => v ? { ledger:ledgerOf(v, mk, .6 + .1 * (i + j)), variant_hash:`cell-${runs}-${i}-${j}` } : null)) },
    duration_ms:1234,
  };
  return buildResult(input);
}

export function stubApi(opts: { hostile?: boolean; flow?: boolean; wide?: boolean; catalogMs?: number; flowMs?: number } = {}): BacktestApi {
  const mk = opts.hostile ? HOSTILE : opts.flow ? FLOW : opts.wide ? WIDE : PLAIN, { all:ALL, catalog:CATALOG, calcOf } = mk;
  const compute = new Compute(() => CATALOG);
  const jobs = new Map<string, { polls: number; request: BacktestRequest; result?: BacktestResult; cancelled?: boolean }>();
  let runs = 0;
  /* an answer after `ms`, as the network's; an aborted call rejects with the AbortError fetch gives. The smoke run reads
     how many calls were aborted (globalThis.__aborted), how many previews were asked and answered (__previewAsks,
     __previewAnswers) and which tickers' events were asked (__events). */
  const probe = globalThis as { __aborted?: number; __previewAsks?: number; __previewAnswers?: number; __events?: string[]; __replaceNextPreview?: boolean };
  const later = <T>(v: () => T, ms = 20, signal?: AbortSignal) => new Promise<T>((ok, no) => {
    const t = setTimeout(() => { try { ok(v()) } catch (e) { no(e) } }, ms);
    signal?.addEventListener('abort', () => { clearTimeout(t); probe.__aborted = (probe.__aborted || 0) + 1; no(new DOMException('The operation was aborted.', 'AbortError')) }, { once:true });
  });
  const status = (id: string, state: JobStatus['state'], progress: JobStatus['progress']): JobStatus =>
    ({ request_id:id, state, progress, error:null, created_at:'2026-10-26T00:00:00Z', started_at:null, finished_at:null, duration_ms:null, result_bytes:null });
  return {
    texts: PUBLISHED_TEXTS,
    catalog: () => later(() => CATALOG, opts.catalogMs ?? 20),   // catalogMs: a catalog that answers late (EXEC-BACKTEST-LOAD)
    // flowMs: the broker data of a flow card arrives that late (EXEC-BACKTEST-LOAD: the chart draws the prices first)
    bars: (t: string, o: { flow?: boolean } = {}) => later(() => { if (!ALL[t]) throw new ApiFailure(`No price data is published for ${t}.`, 'DATA_MISSING'); if (!compute.has(t)) compute.put(ALL[t]); return compute.get(t)! }, o.flow ? opts.flowMs ?? 20 : 20),
    ready: c => compute.ready(c),
    indicatorOutputs: (t, id, p) => compute.indicatorOutputs(t, id, p),
    conditionSeries: (t, c) => compute.conditionSeries(t, c),
    // the worker's preview (backtest-worker run.ts): the run's exclusions, TICKERS_EXCLUDED, UNIVERSE_EMPTY
    signalsPreview: (req: SignalsPreviewRequest, o = {}) => (probe.__previewAsks = (probe.__previewAsks || 0) + 1, later(() => {
      if (probe.__replaceNextPreview) { probe.__replaceNextPreview = false; throw new ApiFailure('A newer signals preview replaced this one.', 'PREVIEW_REPLACED', 409) }
      const active = requestConditions(req), excluded: Exclusion[] = [], rows = [];
      for (const t of [...req.tickers].sort(byTicker)) {
        if (mk.hostile && t === XSS('ticker')) { excluded.push({ ticker:t, code:XSS('preview reason code'), message:XSS('preview reason') }); continue }
        const no = mk.unservedError(t); if (no) { excluded.push(no); continue }
        const row = unlessLeftOut(t, excluded, () => previewRow(calcOf(t), ALL[t].dates, req, req.period.from, req.period.to, active));
        if (row) rows.push({ ticker:t, ...row });
      }
      const left = leftOut(excluded, rows.length, 'tickers', 'preview');
      probe.__previewAnswers = (probe.__previewAnswers || 0) + 1;
      return { data_version:'stub', rows, warnings:[...(left ? [left] : []), ...(mk.hostile ? [hostileWarning('preview')] : [])] };
    }, 20, o.signal)),
    submit: req => later(() => {
      const f = CATALOG.flow;
      if (f.available && readsFlow(req) && req.period.to > f.data_through!)
        throw new ApiFailure(`The broker data is published through ${f.data_through}: a run with flow conditions or ranked by foreign net flow must end on or before it (period.to is ${req.period.to}).`, 'FLOW_DATA_THROUGH', 422, 'period.to');
      const id = `${mk.hostile ? XSS('job id') : 'stub'}-${++runs}`;
      jobs.set(id, { polls:0, request:JSON.parse(JSON.stringify(req)) });
      return { request_id:id };
    }),
    status: id => later(() => {
      const j = jobs.get(id)!;
      if (j.cancelled) return status(id, 'CANCELLED', null);
      return j.polls++ < 1 ? status(id, 'RUNNING', { phase:'sensitivity', done:12, total:25 }) : status(id, 'FINISHED', null);
    }),
    result: id => later(() => {
      const j = jobs.get(id)!;
      const r = j.result ||= resultOf(j.request, runs, mk);
      return servedResult(r, j.request.single?.ticker ?? null);
    }),
    events: (id, t) => later(() => { probe.__events = [...(probe.__events || []), t]; if (mk.hostile && t === 'ACES') throw new ApiFailure(XSS('error message'), 'EVENTS_NOT_FOUND', 404); return servedEvents(jobs.get(id)!.result!, t) }),
    cancel: id => later(() => { const j = jobs.get(id); if (j) j.cancelled = true }),
    closes: (t, cal) => later(() => asOf(ALL[t].dates, ALL[t].c, cal)),
  };
}
