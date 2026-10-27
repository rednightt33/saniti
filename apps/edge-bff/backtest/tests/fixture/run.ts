/* A fixture run: the reference's own run (mockup.js runMockup: backtest, statistics, sensitivity grid, Monte Carlo,
   trials) on the request's settings, its backtest turned into a ledger (core/ledger.ts), and the result assembled by
   the production result builder (core/result.ts buildResult). The page therefore renders the reference's numbers
   through the code path it renders the worker's, and tests/fixture/numbers.test.ts compares the two field by field.
   - Calendar: the days the reference's backtest marks (res.eq); every ticker trades on every one of them.
   - Trades in the reference's order (per day, the newest position first): its tradeStats, streaks and Monte Carlo
     read that order, and buildResult keeps the ledger's order.
   - Events: the reference's condition and entry series (signalsFor, exitSeries) as SignalTracks on the calendar.
   - Sensitivity: the cells' own backtests from the reference's grid when its axes are the request's
     (core/robustness.ts sensitivityPlan); otherwise each planned cell is a reference backtest of that variant.
   - Trials: the reference counts every variant of the page session (S.trials: +1 per run, +25 per grid); the fixture
     hands buildResult the session's earlier variants as prior trials with one hash per variant, so the count it shows
     is the reference's. */
import type { BacktestRequest, BacktestResult, ExitPhase, ExitReason, SignalsPreview, SignalsPreviewRequest } from '../../src/core/contract.ts';
import type { CellRun, Ledger, LedgerTrade, ResultInput } from '../../src/core/ledger.ts';
import { REGISTRY_VERSION } from '../../src/core/registry.ts';
import { buildResult } from '../../src/core/result.ts';
import { sensitivityPlan } from '../../src/core/robustness.ts';
import { barMap, signalSummary, track } from '../../src/core/signals.ts';
import * as M from './mockup.js';
import { previewStateOf, stateOf } from './state.ts';

export const ENGINE_VERSION = 'reference mock-up (backtest.html section 8)';
export const DATA_VERSION = 'reference synthetic market (seed 20261025)';

const REASON: Record<string, ExitReason> = {
  'Stop loss':'stop_loss', 'Trailing stop':'trailing_stop', 'Take profit':'take_profit', 'Time exit':'time_exit', 'Exit signal':'exit_signal', 'End of test':'end_of_test',
};
/* where in the day the reference fills each exit: stops and targets during the bar (or at its open on a gap), the time
   exit and the end of the test at the close, a pending exit signal at the open */
const PHASE: Record<ExitReason, ExitPhase> = { stop_loss:'intraday', trailing_stop:'intraday', take_profit:'intraday', time_exit:'close', exit_signal:'open', end_of_test:'close' };

/** what the session remembers between runs (the reference's S.trials and the variants behind it) */
export interface Session { runs: number; trials: number; prior: { variant_hash: string; sharpe_daily: number }[] }
export const newSession = (): Session => ({ runs:0, trials:0, prior:[] });

/** A reference backtest (backtest() result) as a ledger; with `events`, the condition, entry and exit tracks of every
    ticker of the universe (the page's chart after a run) and each trade's entry conditions. Reads the state set in
    mockup.js (the run's own settings). */
export function ledgerOf(res: any, events: boolean): Ledger {
  const S = M.getState(), first: number = res.first, U: string[] = M.universe();
  const days: string[] = res.eq.map(([i]: [number, number]) => M.DAYS[i]);
  const bk: string = M.primaryBench(), bc: number[] = M.closeOf(bk);
  const ev: Ledger['events'] = { conditions:[], entries:{}, exits:{}, skipped:[] };
  const sigs: Record<string, { series: { c: any; s: Uint8Array }[]; entry: Uint8Array }> = {};
  if (events) {
    const m = barMap(M.DAYS, days), exitCards = S.exitConds.filter((c: any) => c.on && M.condReady(c));
    for (const t of U) {
      const sig = sigs[t] = M.signalsFor(t);
      ev.entries[t] = track(sig.entry, m);
      ev.exits[t] = track(M.exitSeries(t), m);
      for (const x of sig.series) ev.conditions.push({ condition_id:x.c.id, ticker:t, track:track(x.s, m) });
      for (const c of exitCards) ev.conditions.push({ condition_id:c.id, ticker:t, track:track(M.catOf(c).eval(t, c), m) });
    }
  }
  const W = Math.max(1, S.window | 0);
  const within = (t: string, j: number) => {
    if (!sigs[t]) return [];
    const ids: string[] = [];
    for (const x of sigs[t].series) for (let k = j; k > j - W && k >= 0; k--) if (x.s[k]) { ids.push(x.c.id); break }
    return ids;
  };
  const trades: LedgerTrade[] = res.trades.map((t: any) => {
    const reason = REASON[t.why], k = t.sig - first, on = ev.entries[t.tk]?.on ?? [];
    let e = 0; on.forEach((b, j) => { if (b <= k) e = j });            // the switch-on of the entry state the signal bar belongs to
    return {
      ticker:t.tk, signal_bar:k, signal_event:e, entry_bar:t.ei - first, entry_price:t.entry, exit_bar:t.xi - first, exit_price:t.exit,
      exit_reason:reason, exit_phase:PHASE[reason], shares:t.sh, bars_held:t.bars, cost_idr:t.cost, proceeds_idr:t.proceeds, pnl_idr:t.pnl, return:t.ret,
      mae:t.mae, mfe:t.mfe, initial_stop:t.stop > 0 ? t.stop : null, initial_target:t.tgt < 1e18 ? t.tgt : null, initial_risk_pct:t.riskPct,
      entry_condition_ids:within(t.tk, t.sig),
      flags:{ corporate_actions:[], stop_and_target_same_bar:(reason === 'stop_loss' || reason === 'trailing_stop') && t.tgt < 1e18 && M.DATA[t.tk].h[t.xi] >= t.tgt, stale_mark:false },
    };
  });
  return {
    dates:days, equity:res.eq.map((x: [number, number]) => x[1]), exposure:res.expo, benchmark_close:res.eq.map(([i]: [number, number]) => bc[i]),
    benchmark:{ kind:S.mode === 'single' && S.bench !== 'ihsg' ? 'buy_and_hold' : 'ihsg', ticker:bk },
    trades, events:ev,
    per_ticker_signals:U.map(t => ({ ticker:t, ...(ev.entries[t] ? signalSummary(ev.entries[t], days) : { entry_signals:0, last_signal:null }) })),
    warnings:[],
  };
}

const same = (a: readonly number[], b: readonly number[]) => a.length === b.length && a.every((x, i) => Object.is(x, b[i]));

export interface FixtureRun { result: BacktestResult; R: any; cellRuns: any[]; gridFromReference: boolean }

/** One run of the request on the reference's engine, its result built by core/result.ts. */
export function runRequest(q: BacktestRequest, session: Session): FixtureRun {
  const S = stateOf(q, session.trials), id = `run${++session.runs}`;
  M.setState(S);
  const { R, cellRuns } = M.runMockup();
  session.trials = S.trials;
  const ledger = ledgerOf(R, true);
  const plan = sensitivityPlan(q), G = R.grid;
  const gridFromReference = !!(plan && G && G.cond.id === plan.condition_id && same(G.xs, plan.xs_display) && same(G.ys, plan.ys_display));
  let sensitivity: ResultInput['sensitivity'] = null;
  if (plan) {
    const cells = plan.requests.map((row, i) => row.map((v, j): CellRun | null => {
      if (!v) return null;
      let r = gridFromReference ? cellRuns[i * row.length + j] : null;
      if (!r) { M.setState(stateOf(v)); r = M.backtest(); M.setState(S) }
      return { ledger:ledgerOf(r, false), variant_hash:`${id}-y${i}-x${j}` };
    }));
    sensitivity = { condition_id:plan.condition_id, xs:plan.xs, xs_display:plan.xs_display, y_key:plan.y_key, ys:plan.ys, ys_display:plan.ys_display,
      base_x:plan.base_x, base_y:plan.base_y, cells };          // null where the plan refuses the threshold
  }
  const result = buildResult({
    request:q, ledger,
    versions:{ engine_version:ENGINE_VERSION, registry_version:REGISTRY_VERSION, data_version:DATA_VERSION, data_through:M.DAYS[M.N - 1] },
    tickers:M.universe(), prior_trials:session.prior.slice(), variant_hash:id, lineage_key:'fixture-session', request_hash:id,
    sensitivity, duration_ms:R.ms,
  });
  session.prior.push(...result.meta.trials.variants.map(v => ({ variant_hash:v.variant_hash, sharpe_daily:v.sharpe_daily })));
  return { result, R, cellRuns, gridFromReference };
}

/** The portfolio table's signals before a run: the reference's own loop over the universe (refreshSignals); every
    demo ticker has data for every card, so none is left out (no TICKERS_EXCLUDED). */
export function previewRequest(q: SignalsPreviewRequest): SignalsPreview {
  M.setState(previewStateOf(q));
  const rows = M.universe().map((t: string) => {
    const s = M.signalsFor(t); let n = 0, last: string | null = null;
    for (let i = 0; i < M.N; i++) if (M.inRange(i) && s.entry[i] && !s.entry[i - 1]) { n++; last = M.DAYS[i] }
    return { ticker:t, entry_signals:n, last_signal:last };
  });
  return { data_version:DATA_VERSION, rows, warnings:[] };
}
