/* EDGE backtest contract, schema_version 1: the request the page sends, the result the worker returns, and the job and
   error shapes edge-bff relays. One file for the page (Vite), the worker (Node) and the tests; edge-bff (Python)
   stores the request and result as JSON and does not interpret them beyond the fields named in CONTRACT.md.

   Units (one convention everywhere, no percent and no "Rp miliar" on the wire):
   - money: IDR (rupiah); prices: IDR per share (index points for IHSG);
   - rates, returns, fees, slippage, allocation, OOS share, stop/target distances: fractions (0.07 = 7 %);
   - dates: exchange dates 'YYYY-MM-DD' (Asia/Jakarta trading days);
   - indicator thresholds: the indicator output's own unit (RSI 30, ADX 25);
   - price-action thresholds: dip = one-day return as a fraction (-0.03), volspike = volume ratio (2 = 2x);
   - flow thresholds: IDR (the page shows Rp B and multiplies by 1e9);
   - no NaN or Infinity on the wire: a missing number is null; an infinite profit factor is the string 'inf'.
   The page's display scale per condition is in catalog.ts (DISPLAY), so the page and the worker's sensitivity grid
   use the same numbers. */

export const SCHEMA_VERSION = 1;

/* ------------------------------------------------------------------------------------------------------------ */
/* request                                                                                                       */
/* ------------------------------------------------------------------------------------------------------------ */

export type Op = 'gt' | 'lt' | 'crosses_above' | 'crosses_below';
export type ParamValue = number | string | boolean;
export type ParamMap = Record<string, ParamValue>;

/** Registry indicator condition (I01..I53): price/volume or an output against an output of the same indicator or a value. */
export interface IndicatorCondition {
  id: string; enabled?: boolean; kind: 'indicator';
  indicator: string;                                   // registry id, e.g. 'I07'
  params?: ParamMap;                                   // accepted parameters only; missing ones take the registry default
  lhs: { type: 'price' } | { type: 'output'; output: string };
  op: Op;
  rhs: { type: 'output'; output: string } | { type: 'value'; value: number };
}
/** The page's price-action and pattern conditions (CATALOG dip, breakout, volspike, macross, macd). */
export interface PriceActionCondition {
  id: string; enabled?: boolean; kind: 'price_action';
  type: 'dip' | 'breakout' | 'volspike' | 'macross' | 'macd';
  params?: ParamMap;                                   // breakout/volspike: length; macross: fast_length, slow_length; macd: fast_length, slow_length, signal_length
  op?: string;                                         // dip: lte; breakout: close_above_high; volspike: gt; macross: golden_cross | fast_above_slow;
                                                       // macd: bullish_divergence | crosses_above_signal | histogram_positive
  value?: number;                                      // dip (fraction) and volspike (ratio) only
}
/** Flow and broker conditions on the published broker files (enabled only when catalog.flow.available is true). */
export interface FlowCondition {
  id: string; enabled?: boolean; kind: 'flow';
  type: 'fnet' | 'broker' | 'top5';
  params: { length: number; broker?: string };         // broker: the broker code for type 'broker'
  op: 'gt' | 'lt';                                     // fnet: gt | lt; broker, top5: gt
  value: number;                                       // IDR
}
export type Condition = IndicatorCondition | PriceActionCondition | FlowCondition;

/** A price line a stop or a trailing stop can sit on: an output of an overlay indicator (the page's LEVEL_LINES). */
export interface LineRef { indicator: string; output: string; params?: ParamMap }

export interface BacktestRequest {
  schema_version: 1;
  mode: 'single' | 'portfolio';
  single?: {
    ticker: string;
    benchmark: 'buy_and_hold' | 'ihsg';                // the page's Benchmark select (S.bench 'bh' | 'ihsg')
  };
  portfolio?: {
    universe: string;                                  // a catalog universe id: 'all' or 'sector:<published sector name>'
    max_positions: number;                             // whole number 1-10
    rank_by: 'adx' | 'fnet' | 'vol' | 'rsi';           // highest ADX(14) | biggest foreign net 5D | highest volume ratio | lowest RSI(14)
    min_avg_value_20d_idr: number;                     // >= 0; 20-day average of close x volume on the signal day
  };
  period: { from: string; to: string; oos_fraction: 0 | 0.2 | 0.3 | 0.4 };
  entry: {
    logic: 'all' | 'any' | 'at_least';
    at_least: number;                                  // whole >= 1 (used when logic = at_least; above the active count means all)
    window_bars: number;                               // whole 1-20
    conditions: Condition[];                           // enabled: false conditions are kept but not evaluated
  };
  exit: {
    atr_length: number;                                // the page's one ATR length for the stop and the target (S.exit.atrLen)
    stop: { mode: 'pct' | 'atr' | 'rr' | 'line' | 'none'; pct: number; atr_mult: number; reward_risk_x: number; line: LineRef };
    take_profit: { mode: 'pct' | 'r' | 'atr' | 'none'; pct: number; r_multiple: number; atr_mult: number };
    trailing: { mode: 'none' | 'pct' | 'chandelier' | 'line'; pct: number; chandelier_length: number; chandelier_mult: number; line: LineRef };
    max_hold_bars: number;                             // whole >= 0; 0 = off
    signals: { logic: 'any' | 'all'; conditions: Condition[] };
  };
  sizing: { capital_idr: number; allocation_fraction: number };   // allocation: single mode, (0, 1]
  costs: { buy_fee: number; sell_fee: number; slippage: number; skip_ara_open_gap: boolean; ara_gap_fraction: number };
  robustness: { monte_carlo_runs: number; seed: number; sensitivity: boolean };
}

/** What edge-bff adds to the request when it hands the job to the worker (the user never sends it). */
export interface JobContext {
  job_id: string;
  /** Trials already recorded for this strategy line (K3): every distinct variant evaluated before, with its daily
      Sharpe; the worker adds this run's variants and computes the Deflated Sharpe from the union. */
  prior_trials: { variant_hash: string; sharpe_daily: number }[];
}

/* ------------------------------------------------------------------------------------------------------------ */
/* result                                                                                                        */
/* ------------------------------------------------------------------------------------------------------------ */

export type ExitReason = 'stop_loss' | 'trailing_stop' | 'take_profit' | 'time_exit' | 'exit_signal' | 'end_of_test';
export type ExitPhase = 'open' | 'intraday' | 'close';
export type ProfitFactor = number | 'inf';

/** Daily-series statistics (page seriesStats; 252 trading days a year, rf = 0). Null where the page shows '—'. */
export interface SeriesStats {
  n_returns: number;                 // number of daily returns
  total_return: number; cagr: number; volatility: number; sharpe: number; sharpe_daily: number;
  sortino: number; max_drawdown: number; calmar: number; longest_drawdown_bars: number; ulcer_index: number;
  var_95: number; cvar_95: number;
  skew: number | null; kurtosis: number | null;     // null: no volatility (flat equity, e.g. no trade), the page's NaN '—'
  beta: number | null; alpha: number | null; correlation: number | null;   // against the primary benchmark
  best_day: number; worst_day: number; positive_days: number;
  psr_0: number | null;              // probabilistic Sharpe against 0; null as skew, or without any return
}

/** Trade statistics (page tradeStats). */
export interface TradeStats {
  n: number; wins: number; losses: number; win_rate: number; avg_win: number; avg_loss: number; payoff: number;
  profit_factor: ProfitFactor; gross_profit_idr: number; gross_loss_idr: number; net_idr: number;
  expectancy: number; expectancy_idr: number; sqn: number; expectancy_r: number;
  max_consecutive_wins: number; max_consecutive_losses: number; best: number; worst: number;
  avg_hold_bars: number; avg_hold_bars_winners: number; avg_hold_bars_losers: number; kelly: number;
  avg_mae: number; avg_mfe: number;
}

export interface Trade {
  trade_id: string;                  // '<ticker>-<entry date>-<n>' (stable for a given request and data version)
  ticker: string;
  signal_date: string;               // the bar whose close produced the entry event
  signal_event: number;              // index into events.entries[ticker].on (the entry event this trade executes)
  entry_date: string; entry_price: number;            // fill incl. slippage
  exit_date: string; exit_price: number;              // fill incl. slippage
  exit_reason: ExitReason; exit_phase: ExitPhase;
  shares: number; lots: number; bars_held: number;    // bars of the ticker, entry bar included
  cost_idr: number; proceeds_idr: number; pnl_idr: number; return: number;   // return = pnl / cost
  mae: number; mfe: number;
  initial_stop: number | null; initial_target: number | null; initial_risk_pct: number | null;
  entry_condition_ids: string[];     // entry conditions true within the window on the signal bar
  flags: {
    corporate_actions: { date: string; type: string }[];   // price-affecting actions with ex-date in (entry, exit]
    stop_and_target_same_bar: boolean;                     // both touched in one candle: stop taken (E4)
    stale_mark: boolean;                                   // the exit or a mark used a last close from an earlier day
  };
  streak?: number;                   // place in the current run of wins or losses, 1-based (page "Win / loss streaks")
  streak_length?: number;            // length of that run
}

/** A 0/1 series on the result calendar, sent as the bars where it switches on and its true runs. */
export interface SignalTrack {
  on: number[];                      // calendar indices where it switches on (false on the ticker's previous bar)
  runs: number[];                    // flattened [start, end, start, end, ...] inclusive calendar indices where it is true
}

export interface SkippedSignal {
  ticker: string; signal_date: string; signal_event: number;
  reason: 'already_held' | 'no_slot' | 'insufficient_cash' | 'ara_open_gap' | 'below_min_value' | 'no_next_bar' | 'period_end';
}

export interface MonthlyRow {
  year: number; month: number; ret: number; benchmark_ret: number;
  ytd?: number;                      // heatmap tooltip "Year to date": the year's months compounded up to this one
}
export interface AnnualRow {
  year: number; ret: number; benchmark_ret: number; max_drawdown: number; trades_closed: number; win_rate: number | null;
  /* the heatmap's year column and its tooltip (ret above is the annual bars' last value / value before the year) */
  months_compound?: number;          // the year's monthly returns compounded
  best_month?: { month: number; ret: number }; worst_month?: { month: number; ret: number };   // first one on ties
  positive_months?: number; months?: number;
}
export interface WeekdayRow {
  weekday: 1 | 2 | 3 | 4 | 5; mean: number; median: number | null; positive_share: number; days: number;
  best: number | null; worst: number | null;   // null: no day of that weekday in the calendar
}
export interface DrawdownPeriod { peak: number; trough: number; recovery: number | null; depth: number; bars: number }  // calendar indices

export interface MonteCarlo {
  runs: number; seed: number; n_trades: number;
  scale: number;                     // trade return x scale = equity change per trade (single: allocation; portfolio: 1 / max positions)
  bands: { p05: number[]; p25: number[]; p50: number[]; p75: number[]; p95: number[] };   // growth of 1 after k trades, k = 0..n
  below_start: number[];             // share of runs below 1 after k trades
  actual: number[];                  // the backtest's own trade order
  final_returns: number[];           // per run (runs values)
  max_drawdowns: number[];           // per run
  /* the page's legends (page quant on final_returns / max_drawdowns) */
  final_return_p05?: number; final_return_p50?: number; final_return_p95?: number;
  loss_share?: number;               // "Chance of loss": share of runs with a final return below 0
  max_drawdown_p50?: number; max_drawdown_p05?: number;   // median and "95 % worst" drawdown
}
export interface SensitivityCell { sharpe: number; cagr: number; profit_factor: ProfitFactor; trades: number; max_drawdown: number }
export interface Sensitivity {
  condition_id: string;              // the first enabled entry condition with a numeric threshold
  x_param: 'value';                  // what varies on x: the condition's threshold
  xs: number[]; xs_display: number[];                       // wire units and the page's display units
  y_key: 'stop_pct' | 'stop_atr_mult' | 'stop_reward_risk_x' | 'max_hold_bars';
  ys: number[]; ys_display: number[];
  base_x: number; base_y: number;    // the run's own settings (wire units)
  cells: (SensitivityCell | null)[][];   // cells[y][x]; null: a threshold the condition refuses (volspike 2 - 2 = 0), not run
}

export interface BacktestResult {
  schema_version: 1;
  meta: {
    engine_version: string; registry_version: string;
    data_version: string;            // sha256 over the sorted (ticker, dataset, file sha256) the run read
    request_hash: string;            // sha256 of the canonical request + engine, registry and data versions
    lineage_key: string;             // the strategy line for trial counting (K3)
    seed: number; duration_ms: number;
    mode: 'single' | 'portfolio';
    tickers: string[];               // single: [ticker]; portfolio: the universe the run used
    benchmark: { kind: 'buy_and_hold' | 'ihsg'; ticker: string };
    data_through: string;            // the latest published bar the run could see
    warnings: { code: string; message: string; count?: number; tickers?: string[] }[];
    trials: {
      prior: number; this_run: number; total: number;
      /** The distinct variants this run evaluated (the run itself and the sensitivity cells), which edge-bff records
          in edge_bff.backtest_trials for the next run of the same lineage (K3). */
      variants: { variant_hash: string; sharpe_daily: number; kind: 'run' | 'sensitivity' }[];
    };
  };
  dates: string[];                   // result calendar: exchange days from the first to the last day of the period
  equity: number[];                  // IDR, after each day's close
  benchmark: number[];               // primary benchmark, IDR, scaled to the capital on the first day
  drawdown: number[];                // equity / running peak - 1
  exposure: number[];                // market value / equity after the close
  daily_returns: number[];           // equity[k] / equity[k-1] - 1, k = 1..n-1
  oos: { fraction: number; cut: number; cut_date: string | null };  // cut = page's `cut`: in-sample is equity[0..cut-1]
  stats: {
    all: SeriesStats; in_sample: SeriesStats | null; out_of_sample: SeriesStats | null; benchmark: SeriesStats;
    exposure_mean?: number;          // KPI "Exposure": mean of exposure
  };
  trade_stats: { all: TradeStats; in_sample: TradeStats; out_of_sample: TradeStats | null };
  trade_returns: { mean: number; median: number | null; sd: number; skew: number | null };   // median null: no trade
  tables: {
    monthly: MonthlyRow[]; annual: AnnualRow[]; weekday: WeekdayRow[];
    rolling_sharpe_126: (number | null)[];             // aligned with daily_returns
    drawdowns: DrawdownPeriod[];                       // five deepest, deepest first
    exit_reasons: { reason: ExitReason; trades: number; wins: number; avg_return: number; pnl_idr: number; avg_bars: number }[];
    per_ticker: {
      ticker: string; entry_signals: number; last_signal: string | null; trades: number; wins: number; pnl_idr: number;
      avg_return?: number | null; pnl_share?: number | null;   // "P&L by stock" tooltip; null without a trade
    }[];
    rolling_return_126?: (number | null)[];            // rolling-Sharpe tooltip: the same 126 returns compounded
    rolling_sharpe_126_share_above_1?: number | null;  // "Share of time above 1" over the finite points
  };
  trades: Trade[];
  events: {
    conditions: { condition_id: string; ticker: string; track: SignalTrack }[];   // entry and exit conditions
    entries: Record<string, SignalTrack>;              // combined entry rule per ticker
    exits: Record<string, SignalTrack>;                // combined exit-signal rule per ticker
    skipped: SkippedSignal[];
  };
  robustness: {
    monte_carlo: MonteCarlo | null;                    // null with fewer than 3 trades (page rule)
    sensitivity: Sensitivity | null;                   // null without a numeric threshold or when switched off
    deflated: { sr0: number | null; dsr: number | null; trials: number; sharpe_variance_from: 'trials' | 'sample' };   // null: page NaN
  };
}

/* ------------------------------------------------------------------------------------------------------------ */
/* jobs and errors (edge-bff relays these; the worker's private API uses the same shapes)                       */
/* ------------------------------------------------------------------------------------------------------------ */

export type JobState = 'QUEUED' | 'RUNNING' | 'FINISHED' | 'FAILED' | 'CANCELLED';
export type JobPhase = 'queued' | 'loading' | 'signals' | 'backtest' | 'sensitivity' | 'monte_carlo' | 'finalizing';
export interface JobProgress { phase: JobPhase; done: number; total: number }
export interface JobStatus {
  request_id: string; state: JobState; progress: JobProgress | null;
  error: ApiError['error'] | null;
  created_at: string; started_at: string | null; finished_at: string | null;
  duration_ms: number | null; result_bytes: number | null;
}
/** Error body, edge-bff convention: {"error": {"code": ...}} plus field and message where they help. */
export interface ApiError { error: { code: string; field?: string; message?: string; details?: Record<string, unknown> } }

/** Signals preview for the portfolio table (no backtest, no trial). */
export interface SignalsPreviewRequest {
  schema_version: 1; universe: string; period: { from: string; to: string };
  entry: BacktestRequest['entry'];
}
export interface SignalsPreview {
  data_version: string;
  rows: { ticker: string; entry_signals: number; last_signal: string | null }[];
}

/** GET catalog: what the page may offer (built by the worker from its registry, catalog.ts and the published data). */
export interface Catalog {
  schema_version: 1; engine_version: string; registry_version: string;
  data_through: string;                                  // IHSG's latest published bar
  first_date: string;                                    // IHSG's first published bar
  tickers: { ticker: string; name: string; type: string; sector: string | null }[];
  universes: { id: string; label: string; tickers: number }[];
  flow: { available: boolean; reason: string | null; brokers: string[] };
  limits: Limits;
}
export interface Limits {
  max_positions: number; window_bars: { min: number; max: number }; monte_carlo_runs: number;
  max_download_bytes: number; max_broker_rows: number; timeout_seconds: number; queued_per_owner: number;
}
