/* One job (POST /v1/jobs) and one signals preview (POST /v1/signals), from the request to the BacktestResult /
   SignalsPreview, with the shared core doing every calculation:
   1. loading      the request checked (validate.ts), the tickers resolved (single: the ticker; portfolio: the catalog
                   universe), the published files read within the limits (load.ts): IHSG's prices, each ticker's
                   prices and events, its broker files only when a flow condition or rank_by 'fnet' needs them; the
                   period checked against what is published (below);
   2. signals      engine.ts run(): every ticker's conditions and entry events (its progress, first part);
   3. backtest     the same run: the event clock over the result calendar (second part);
   4. sensitivity  robustness.ts sensitivityPlan: one engine run per cell on the same prepared data (the indicator
                   memos are reused); identical cell requests (one variant hash) run once, the cell that equals the run
                   itself reuses the run; a threshold conditions.ts refuses is a null cell;
   5. monte_carlo  result.ts buildResult: the statistics, tables, trials and the Monte Carlo (this phase covers all
                   of buildResult; the Monte Carlo dominates it with 1000 runs);
   6. finalizing   the result serialised and packed (compute.ts).
   Cancellation: hooks.shouldStop is read between phases, between tickers while loading, inside the engine (per ticker
   and per calendar day) and between sensitivity cells; Cancelled is thrown.
   Deterministic: the same request on the same published files gives the same result (meta.duration_ms aside); no
   clock, random number or cache state reaches a number.
   Checks against the published data (CONTRACT.md sections 2-3):
   - PERIOD_AFTER_DATA: period.to after IHSG's last published bar (the engine's rule, checked before the run);
   - broker data: the newest broker data_through among the loaded tickers' manifests must reach period.to
     (DATA_UNAVAILABLE). The publisher writes its global data_through into the manifest of each ticker whose files
     changed, so a ticker without new rows keeps an older date; the per-ticker price data_through is therefore not
     used (a suspended stock would refuse a run that misses nothing); IHSG's last bar is the price check;
   - single mode: the ticker has a published bar inside the period (DATA_MISSING otherwise, terminal.ts checkPriceRange);
   - PERIOD_BEFORE_DATA: the primary benchmark has no close on or before the first day of the result calendar (a
     buy-and-hold ticker listed after period.from; result.ts cannot scale a benchmark without a first close). */
import type { BacktestRequest, BacktestResult, JobContext, JobProgress, SignalsPreview, SignalsPreviewRequest } from '../../edge-bff/backtest/src/core/contract.ts';
import { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';
import { DataError, INDEX_TICKER } from '../../edge-bff/backtest/src/core/datafile.ts';
import { Cancelled, prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import type { MarketData } from '../../edge-bff/backtest/src/core/engine.ts';
import { lineageKey, requestHash, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import type { CellRun, ResultInput } from '../../edge-bff/backtest/src/core/ledger.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { buildResult } from '../../edge-bff/backtest/src/core/result.ts';
import { sensitivityPlan } from '../../edge-bff/backtest/src/core/robustness.ts';
import { previewRow, requestConditions } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from './config.ts';
import { loadMarket } from './load.ts';
import type { PlannedClient } from './load.ts';
import { checkPriceRange } from './terminal.ts';
import type { Dataset, LoadedTicker, TickerRef } from './terminal.ts';
import { checkRequest, checkSignalsRequest } from './validate.ts';

export interface RunEnv {
  client: PlannedClient;
  config: Pick<Config, 'limits' | 'flow'> & { terminal: Pick<Config['terminal'], 'concurrency'> };
  versions: { engine_version: string; registry_version: string };
  now?: () => number;                                   // milliseconds, for meta.duration_ms only
}
export interface RunHooks { progress?(p: JobProgress): void; shouldStop?(): boolean }

const lastOf = (a: readonly string[]) => a[a.length - 1];

/** The reference ticker list the request is checked against (the caller passes the one it validated with). */
export type Refs = readonly TickerRef[];

export async function runJob(request: unknown, context: Pick<JobContext, 'prior_trials'>, refs: Refs, env: RunEnv, hooks: RunHooks = {}): Promise<BacktestResult> {
  const now = env.now ?? (() => performance.now()), t0 = now();
  const stop = () => { if (hooks.shouldStop?.()) throw new Cancelled() };
  const report = (phase: JobProgress['phase'], done: number, total: number) => hooks.progress?.({ phase, done, total });
  const { limits } = env.config;

  /* 1. loading */
  report('loading', 0, 0);
  const checked = checkRequest(request, refs, env.config);
  const q = request as BacktestRequest, single = q.mode === 'single', { from, to } = q.period;
  const datasets: Dataset[] = checked.broker ? ['price', 'events', 'broker'] : ['price', 'events'];
  const field = single ? 'single.ticker' : 'portfolio.universe';
  const loaded = await loadMarket(env.client, [{ tickers: [INDEX_TICKER], datasets: ['price'] }, { tickers: checked.tickers, datasets }], limits, field,
    env.config.terminal.concurrency, { shouldStop: hooks.shouldStop, progress: (d, t) => report('loading', d, t) });
  const ihsg = (loaded.tickers.get(INDEX_TICKER) as LoadedTicker).prices!;
  const ihsgLast = lastOf(ihsg.dates);
  if (to > ihsgLast) throw new ValidationError('PERIOD_AFTER_DATA', 'period.to', `period.to is after the latest published bar (${ihsgLast}).`);
  const stocks = checked.tickers.map(t => loaded.tickers.get(t) as LoadedTicker);
  if (checked.broker) {
    const through = stocks.map(t => t.data_through.broker).filter((d): d is string => typeof d === 'string').sort();
    const newest = through.length ? lastOf(through) : null;
    if (!newest || newest < to)
      throw new DataError('DATA_UNAVAILABLE', `The broker data is published through ${newest ?? 'no date'}; the period ends on ${to}.`, 'broker', { data_through: newest, to });
  }
  if (single) checkPriceRange(stocks[0], from, to);
  const market: MarketData = { ihsg, tickers: {} };
  for (const t of stocks) market.tickers[t.ticker] = { prices: t.prices!, corporate_actions: t.corporate_actions ?? [], ...(t.flow ? { flow: t.flow } : {}) };
  const dataThrough = [ihsgLast, ...stocks.map(t => lastOf(t.prices!.dates))].sort();
  stop();

  /* 2-3. signals and backtest: engine.ts counts the tickers first, then the calendar days */
  const ctx = prepare(market), nT = stocks.length;
  const ledger = run(ctx, q, { shouldStop: hooks.shouldStop, progress: (done, total) => done < nT ? report('signals', done, nT) : report('backtest', done - nT, total - nT) });
  if (ledger.benchmark_close[0] === null || ledger.benchmark_close[0] === undefined) {
    const b = ledger.benchmark.ticker, first = (market.tickers[b]?.prices ?? ihsg).dates[0];
    throw new ValidationError('PERIOD_BEFORE_DATA', 'period.from', `The benchmark ${b} has no published close on or before ${ledger.dates[0]} (its first bar is ${first}); start the period on or after ${first}.`);
  }
  stop();

  /* 4. sensitivity */
  const variant_hash = await variantHash(q);
  const plan = sensitivityPlan(q);
  let sensitivity: ResultInput['sensitivity'] = null;
  if (plan) {
    const runs = new Map<string, CellRun>([[variant_hash, { ledger, variant_hash }]]);   // a cell equal to the run is the run
    const total = plan.requests.flat().filter(Boolean).length;
    let done = 0;
    report('sensitivity', 0, total);
    const cells: (CellRun | null)[][] = [];
    for (const row of plan.requests) {
      const out: (CellRun | null)[] = [];
      for (const cq of row) {
        if (!cq) { out.push(null); continue }
        stop();
        const h = await variantHash(cq);
        let c = runs.get(h);
        if (!c) { c = { ledger: run(ctx, cq, { shouldStop: hooks.shouldStop }), variant_hash: h }; runs.set(h, c) }
        out.push(c);
        report('sensitivity', ++done, total);
      }
      cells.push(out);
    }
    const { requests: _requests, ...axes } = plan;
    // ledger.ts types the cells non-null; result.ts reads null exactly where the plan has no request
    sensitivity = { ...axes, cells: cells as CellRun[][] };
  }
  stop();

  /* 5. statistics, tables, trials, Monte Carlo */
  const data_version = loaded.data_version;
  const [lineage_key, request_hash] = await Promise.all([
    lineageKey(q), requestHash(q, { engine_version: env.versions.engine_version, registry_version: env.versions.registry_version, data_version })]);
  if (q.robustness.monte_carlo_runs > 0) report('monte_carlo', 0, q.robustness.monte_carlo_runs);
  else report('finalizing', 0, 1);
  const result = buildResult({
    request: q, ledger,
    versions: { engine_version: env.versions.engine_version, registry_version: env.versions.registry_version, data_version, data_through: lastOf(dataThrough) },
    tickers: [...checked.tickers], prior_trials: context.prior_trials, variant_hash, lineage_key, request_hash, sensitivity, duration_ms: 0,
  });
  stop();
  report('finalizing', 0, 1);
  stop();                                             // compute.ts checks once more after packing the result
  result.meta.duration_ms = Math.round(now() - t0);   // after buildResult, so the duration covers the whole computation
  return result;
}

/** The portfolio table's entry signals before a run (no backtest, no trial): each universe ticker's entry events on its
    own bars inside the period, as the backtest counts them (signals.ts previewRow). */
export async function runSignals(request: unknown, refs: Refs, env: RunEnv, hooks: RunHooks = {}): Promise<SignalsPreview> {
  const stop = () => { if (hooks.shouldStop?.()) throw new Cancelled() };
  const checked = checkSignalsRequest(request, refs, env.config);
  const q = request as SignalsPreviewRequest;
  const loaded = await loadMarket(env.client, [{ tickers: checked.tickers, datasets: checked.broker ? ['price', 'broker'] : ['price'] }], env.config.limits, 'universe',
    env.config.terminal.concurrency, { shouldStop: hooks.shouldStop, progress: (d, t) => hooks.progress?.({ phase: 'loading', done: d, total: t }) });
  const req = { entry: q.entry }, active = requestConditions(req), rows: SignalsPreview['rows'] = [];
  let done = 0;
  for (const ticker of checked.tickers) {
    stop();
    const t = loaded.tickers.get(ticker) as LoadedTicker;
    const calc = new Calc(t.prices!.bars, t.flow ?? undefined);
    rows.push({ ticker, ...previewRow(calc, t.prices!.dates, req, q.period.from, q.period.to, active) });
    hooks.progress?.({ phase: 'signals', done: ++done, total: checked.tickers.length });
  }
  return { data_version: loaded.data_version, rows };
}
