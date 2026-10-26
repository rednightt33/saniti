/* One job (POST /v1/jobs) and one signals preview (POST /v1/signals), from the request to the BacktestResult /
   SignalsPreview, with the shared core doing every calculation:
   1. loading      the request checked (validate.ts), the tickers resolved (single: the ticker; portfolio: the catalog
                   universe), the published files read within the limits (load.ts): IHSG's prices, each ticker's
                   prices and events, its broker files only when a flow condition or rank_by 'fnet' needs them; the
                   period checked against what is published (below). A portfolio universe ticker without published
                   files is left out of the run (load.ts skipUnpublished; engine.ts lists it in TICKERS_EXCLUDED);
   2. signals      engine.ts run(): every ticker's conditions and entry events (its progress, first part); a portfolio
                   leaves out a ticker whose own data cannot serve the strategy (engine.ts EXCLUDED_CODES);
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
   Checks against the published data (CONTRACT.md sections 2-3); the first two are POST /v1/validate's too
   (checkPublished, lead decision 2026-10-26), with the same code, field and message, on the catalog's dates:
   - PERIOD_AFTER_DATA: period.to after IHSG's last published bar (the engine's rule, checked before the run);
   - FLOW_DATA_THROUGH (a run or a preview that reads the broker files): period.to after the date the broker data is
     published through, the catalog's flow.data_through (load.ts brokerDataThrough: the newest broker data_through of
     the stocks' manifests), checked on the manifests before any download. The publisher writes its broker
     data_through into the manifest of each stock whose files changed, so a stock without new files keeps an older
     date: when no loaded ticker's manifest reaches period.to, every stock's manifest is asked (the catalog's value),
     so a run is refused exactly when the catalog's date is before period.to; the per-ticker price data_through is not
     used (a suspended stock would refuse a run that misses nothing); IHSG's last bar is the price check.
     The scan is not cached: no answer of terminal-api carries an exact marker of a publish. The broker data_through
     is written only into the touched stocks' manifests (IHSG's own manifest is not rewritten by a run that does not
     touch IHSG), the reference files are rewritten on every publish but their Last-Modified is the bucket's header
     and not part of terminal-api's answer, and terminal-api's own manifest cache follows the publisher's state file,
     which the worker cannot read; a cache keyed on any of them could keep an old date after a publish;
   - single mode: the ticker has a published bar inside the period (DATA_MISSING otherwise, terminal.ts
     checkPriceRange); a period.from before its first bar starts the run there (engine.ts PERIOD_CLIPPED);
   - PERIOD_BEFORE_DATA (engine.ts): the primary benchmark has no close on or before the first day of the result
     calendar (result.ts cannot scale a benchmark without a first close). */
import type { BacktestRequest, BacktestResult, JobContext, JobProgress, SignalsPreview, SignalsPreviewRequest } from '../../edge-bff/backtest/src/core/contract.ts';
import { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';
import { INDEX_TICKER } from '../../edge-bff/backtest/src/core/datafile.ts';
import { Cancelled, prepare, run } from '../../edge-bff/backtest/src/core/engine.ts';
import type { MarketData } from '../../edge-bff/backtest/src/core/engine.ts';
import { lineageKey, requestHash, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import type { CellRun, ResultInput } from '../../edge-bff/backtest/src/core/ledger.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { buildResult } from '../../edge-bff/backtest/src/core/result.ts';
import { sensitivityPlan } from '../../edge-bff/backtest/src/core/robustness.ts';
import { leftOut, previewRow, requestConditions, unlessLeftOut } from '../../edge-bff/backtest/src/core/signals.ts';
import type { Config } from './config.ts';
import { brokerDataThrough, loadMarket } from './load.ts';
import type { Bundle, PlannedClient } from './load.ts';
import { checkPriceRange } from './terminal.ts';
import type { Dataset, LoadedTicker, TerminalClient } from './terminal.ts';
import { checkRequest, checkSignalsRequest, stocksOf } from './validate.ts';
import type { CheckedRequest, References } from './validate.ts';

export interface RunEnv {
  client: PlannedClient;
  config: Pick<Config, 'limits' | 'flow'> & { terminal: Pick<Config['terminal'], 'concurrency'> };
  versions: { engine_version: string; registry_version: string };
  now?: () => number;                                   // milliseconds, for meta.duration_ms only
}
export interface RunHooks { progress?(p: JobProgress): void; shouldStop?(): boolean }

const lastOf = (a: readonly string[]) => a[a.length - 1];

/** The reference lists the request is checked against (the caller passes the ones it validated with). */
export type Refs = References;

/** What the published-data checks need: a terminal client and the manifest concurrency. */
type CheckEnv = { client: TerminalClient; config: { terminal: Pick<Config['terminal'], 'concurrency'> } };

/** FLOW_DATA_THROUGH before any download (load.ts hooks.planned): the loaded stocks' manifests, else every stock's. */
async function checkFlowThrough(bundles: ReadonlyMap<string, Bundle>, to: string, refs: Refs, env: CheckEnv, shouldStop?: () => boolean): Promise<void> {
  const own = [...bundles.values()].map(b => b.datasets.broker?.data_through).filter((d): d is string => typeof d === 'string').sort();
  if (own.length && lastOf(own) >= to) return;
  const through = await brokerDataThrough(env.client, stocksOf(refs.tickers), env.config.terminal.concurrency, shouldStop);
  if (through === null || through < to)
    throw new ValidationError('FLOW_DATA_THROUGH', 'period.to', `The broker data is published through ${through ?? 'no date'}: a run with flow conditions or ranked by foreign net flow must end on or before it (period.to is ${to}).`);
}
/** PERIOD_AFTER_DATA: period.to after IHSG's last published bar. */
function checkAfterData(ihsgDates: readonly string[], to: string): void {
  const last = lastOf(ihsgDates);
  if (to > last) throw new ValidationError('PERIOD_AFTER_DATA', 'period.to', `period.to is after the latest published bar (${last}).`);
}

/** POST /v1/validate's checks against the published data (lead decision 2026-10-26), in the job's order and with its
    codes, fields and messages, on the catalog's dates and no file of the request's tickers: FLOW_DATA_THROUGH on every
    stock's manifest (the catalog's flow.data_through) when the request reads the broker files, then PERIOD_AFTER_DATA
    on IHSG's price files (the catalog's data_through). The job checks both again on the data it reads. */
export async function checkPublished(request: BacktestRequest, checked: CheckedRequest, refs: Refs, env: CheckEnv): Promise<void> {
  if (checked.broker) await checkFlowThrough(new Map(), request.period.to, refs, env);
  checkAfterData((await env.client.loadTicker(INDEX_TICKER, ['price'])).prices!.dates, request.period.to);
}

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
  const loaded = await loadMarket(env.client, [{ tickers: [INDEX_TICKER], datasets: ['price'] }, { tickers: checked.tickers, datasets, skipUnpublished: !single }],
    limits, field, env.config.terminal.concurrency, {
      shouldStop: hooks.shouldStop, progress: (d, t) => report('loading', d, t),
      planned: checked.broker ? b => checkFlowThrough(new Map([...b].filter(([t]) => t !== INDEX_TICKER)), to, refs, env, hooks.shouldStop) : undefined,
    });
  const ihsg = (loaded.tickers.get(INDEX_TICKER) as LoadedTicker).prices!;
  const ihsgLast = lastOf(ihsg.dates);
  checkAfterData(ihsg.dates, to);
  const stocks = checked.tickers.filter(t => loaded.tickers.has(t)).map(t => loaded.tickers.get(t) as LoadedTicker);
  if (single) checkPriceRange(stocks[0], from, to);
  const market: MarketData = { ihsg, tickers: {}, excluded: loaded.excluded };
  for (const t of stocks) market.tickers[t.ticker] = { prices: t.prices!, corporate_actions: t.corporate_actions ?? [], ...(t.flow ? { flow: t.flow } : {}) };
  const dataThrough = [ihsgLast, ...stocks.map(t => lastOf(t.prices!.dates))].sort();
  stop();

  /* 2-3. signals and backtest: engine.ts counts the tickers first, then the calendar days */
  const ctx = prepare(market), nT = stocks.length;
  const ledger = run(ctx, q, { shouldStop: hooks.shouldStop, progress: (done, total) => done < nT ? report('signals', done, nT) : report('backtest', done - nT, total - nT) });
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
    sensitivity = { ...axes, cells };                  // null exactly where the plan has no request
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
    tickers: single ? [...checked.tickers] : ledger.per_ticker_signals.map(t => t.ticker), prior_trials: context.prior_trials, variant_hash, lineage_key, request_hash, sensitivity, duration_ms: 0,
  });
  stop();
  report('finalizing', 0, 1);
  stop();                                             // compute.ts checks once more after packing the result
  result.meta.duration_ms = Math.round(now() - t0);   // after buildResult, so the duration covers the whole computation
  return result;
}

/** The portfolio table's entry signals before a run (no backtest, no trial): each universe ticker's entry events on its
    own bars inside the period, as the backtest counts them (signals.ts previewRow), with the run's checks and
    exclusions (lead decision 2026-10-26: a preview never fails where the matching run succeeds): a ticker without
    published files (load.ts skipUnpublished) or whose own data cannot serve the strategy (signals.ts EXCLUDED_CODES)
    is left out and listed in the warning TICKERS_EXCLUDED, none left is UNIVERSE_EMPTY, and a preview that reads the
    broker files is held to FLOW_DATA_THROUGH. */
export async function runSignals(request: unknown, refs: Refs, env: RunEnv, hooks: RunHooks = {}): Promise<SignalsPreview> {
  const stop = () => { if (hooks.shouldStop?.()) throw new Cancelled() };
  const checked = checkSignalsRequest(request, refs, env.config);
  const q = request as SignalsPreviewRequest;
  const loaded = await loadMarket(env.client, [{ tickers: checked.tickers, datasets: checked.broker ? ['price', 'broker'] : ['price'], skipUnpublished: true }], env.config.limits, 'universe',
    env.config.terminal.concurrency, {
      shouldStop: hooks.shouldStop, progress: (d, t) => hooks.progress?.({ phase: 'loading', done: d, total: t }),
      planned: checked.broker ? b => checkFlowThrough(b, q.period.to, refs, env, hooks.shouldStop) : undefined,
    });
  const req = { entry: q.entry }, active = requestConditions(req), rows: SignalsPreview['rows'] = [], excluded = [...loaded.excluded];
  let done = 0;
  for (const ticker of checked.tickers) {
    stop();
    const t = loaded.tickers.get(ticker);
    if (t) {
      const calc = new Calc(t.prices!.bars, t.flow ?? undefined);
      const row = unlessLeftOut(ticker, excluded, () => previewRow(calc, t.prices!.dates, req, q.period.from, q.period.to, active));
      if (row) rows.push({ ticker, ...row });
    }
    hooks.progress?.({ phase: 'signals', done: ++done, total: checked.tickers.length });
  }
  const left = leftOut(excluded, rows.length, 'universe', 'preview');                        // UNIVERSE_EMPTY when none is left
  return { data_version: loaded.data_version, rows, warnings: left ? [left] : [] };
}
