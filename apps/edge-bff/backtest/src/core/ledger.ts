/* What an engine run hands to the result builder (result.ts): the calendar, the daily marks, the trade ledger and the
   events. The production engine (engine.ts) and the mock-up engine of the test fixture both produce this shape, so the
   statistics, tables and robustness numbers are computed by one implementation whichever engine ran.
   Calendar indices (`*_bar`) point into `dates`. Pure types only. */
import type { BacktestRequest, BacktestResult, ExitPhase, ExitReason, SkippedSignal, SignalTrack, Trade } from './contract.ts';

export interface LedgerTrade {
  ticker: string;
  signal_bar: number;                // calendar index of the signal close
  signal_event: number;              // index into events.entries[ticker].on
  entry_bar: number; entry_price: number;            // fill incl. slippage
  exit_bar: number; exit_price: number;              // fill incl. slippage
  exit_reason: ExitReason; exit_phase: ExitPhase;
  shares: number;
  bars_held: number;                 // the ticker's own bars, entry bar included
  cost_idr: number; proceeds_idr: number; pnl_idr: number; return: number;
  mae: number; mfe: number;
  initial_stop: number | null; initial_target: number | null; initial_risk_pct: number | null;
  entry_condition_ids: string[];
  flags: Trade['flags'];
}

export interface Ledger {
  dates: string[];                   // result calendar (CONTRACT.md section 4)
  equity: number[];                  // IDR after each day's close
  exposure: number[];                // market value / equity after the close
  benchmark_close: number[];         // the primary benchmark's close as of each calendar day (shared as-of rule); every day has one
                                     // (engine.ts: single mode starts at the ticker's first bar, PERIOD_CLIPPED; else PERIOD_BEFORE_DATA)
  benchmark: { kind: 'buy_and_hold' | 'ihsg'; ticker: string };
  trades: LedgerTrade[];             // in exit order: exit_bar, then phase open < intraday < close, then ticker
  events: {
    conditions: { condition_id: string; ticker: string; track: SignalTrack }[];
    entries: Record<string, SignalTrack>;
    exits: Record<string, SignalTrack>;
    skipped: SkippedSignal[];
  };
  per_ticker_signals: { ticker: string; entry_signals: number; last_signal: string | null }[];
  warnings: BacktestResult['meta']['warnings'];
}

/** One sensitivity cell as the page computes it from a full rerun (seriesStats + tradeStats of that run). */
export interface CellRun { ledger: Ledger; variant_hash: string }

/** Everything result.ts needs besides the main ledger. */
export interface ResultInput {
  request: BacktestRequest;
  ledger: Ledger;
  versions: { engine_version: string; registry_version: string; data_version: string; data_through: string };
  tickers: string[];
  prior_trials: { variant_hash: string; sharpe_daily: number }[];
  variant_hash: string; lineage_key: string; request_hash: string;
  sensitivity: null | {
    condition_id: string; xs: number[]; xs_display: number[];
    y_key: 'stop_pct' | 'stop_atr_mult' | 'stop_reward_risk_x' | 'max_hold_bars'; ys: number[]; ys_display: number[];
    base_x: number; base_y: number;
    cells: (CellRun | null)[][];     // cells[y][x]; null exactly where the plan has no request (robustness.ts sensitivityPlan)
  };
  duration_ms: number;
}
