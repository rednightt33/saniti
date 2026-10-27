/* The one interface through which the page reaches market data, calculations on market data and backtest jobs.
   Production: live.ts (edge-bff session, /api/terminal/v1/bundle files decoded with the shared core, the backtest
   endpoints of CONTRACT.md section 9). Tests: tests/smoke (a small generated stub) and tests/fixture (the reference's
   synthetic data with its demo formulas and engine, for the 1:1 check). The page modules never compute an indicator, a
   condition or a backtest themselves; they render what this interface returns, as backtest.html renders its own. */
import type { BacktestRequest, BacktestResultCore, Catalog, JobStatus, SignalsPreview, SignalsPreviewRequest, TickerEvents } from '../core/contract.ts';
import type { LegacyCard, RegCard } from '../core/catalog.ts';

/** A condition card as the page keeps it in S.conds / S.exitConds (backtest.html mkCond / mkReg). */
export type Card = LegacyCard | RegCard;

/** One ticker's published daily bars, oldest first, its whole history (the chart shows the part inside the period). */
export interface TickerBars {
  ticker: string;
  dates: string[];
  o: ArrayLike<number>; h: ArrayLike<number>; l: ArrayLike<number>; c: ArrayLike<number>;
  v: ArrayLike<number | null>;
}

/** Indicator outputs aligned with a ticker's bars; NaN where an output has no value (warm-up, missing input). */
export type Outputs = Record<string, Float64Array>;

/** What /events?ticker= returns for one ticker after a run (CONTRACT.md section 9, part events:<ticker>). */
export type { TickerEvents };

/** The page's words that depend on where its data comes from (lead decision 2026-10-27): each BacktestApi supplies
    them, so the renderers stay shared, the production page says what its data is, and the fixture keeps the
    reference's own words (the 1:1 check). Plain text; the page escapes it. */
export interface SourceTexts {
  /** the header's note on the data, next to the theme button (the reference: "Synthetic demo data · long-only") */
  dataNote(catalog: Catalog): string;
  /** the warning box under the overfitting checks of the Robustness tab, for a result */
  robustnessWarning(result: BacktestResultCore): string;
  /** what the trial count counts, after "Variants tried" and "variants tried" (the reference: "this session") */
  trials: string;
}

/** An API answer that is an error: shown with the page's toast(). */
export class ApiFailure extends Error {
  constructor(message: string, readonly code = '', readonly status = 0, readonly field?: string) { super(message) }
}
/** Whether a call failed because its caller aborted it (an AbortSignal): nothing to show. */
export const isAbort = (e: unknown) => (e as { name?: string } | null)?.name === 'AbortError';

export interface BacktestApi {
  texts: SourceTexts;
  /** What the page may offer: tickers, universes, brokers, dates, limits. */
  catalog(): Promise<Catalog>;
  /** A ticker's bars; with flow also its broker data, so flow cards can be calculated. Once it resolves, the
      synchronous calls below work for that ticker (the reference computes everything at once, so the page keeps its
      synchronous renderers and only waits here). */
  bars(ticker: string, opts?: { flow?: boolean }): Promise<TickerBars>;
  /** Whether a card can be calculated at all (the reference's condReady / regReady): false shows the page's
      "Not calculated" pill and the card is left out of a run. */
  ready(card: Card): boolean;
  /** A registry indicator's outputs on a loaded ticker (the workspace's median default threshold); null when the
      indicator cannot be calculated or the ticker is not loaded. */
  indicatorOutputs(ticker: string, id: string, params: Record<string, unknown>): Outputs | null;
  /** One card's 0/1 series on a loaded ticker's bars (bar 0 is never true); null = not ready (see ready) or the data
      it needs is not loaded. Invalid inputs give an all-zero series in the preview; a run reports them as an error. */
  conditionSeries(ticker: string, card: Card): Uint8Array | null;
  /** Entry signals of every ticker of a universe before a run (the portfolio table). `signal` aborts the call (newer
      settings replaced the preview): the answer then never comes, the call rejects with an AbortError (isAbort). */
  signalsPreview(request: SignalsPreviewRequest, opts?: { signal?: AbortSignal }): Promise<SignalsPreview>;
  submit(request: BacktestRequest): Promise<{ request_id: string }>;
  status(id: string): Promise<JobStatus>;
  /** The finished run as edge-bff serves it (the part core; a single run with its ticker's events merged back). */
  result(id: string): Promise<BacktestResultCore>;
  /** The condition and exit tracks of one ticker of a finished run (portfolio: the ticker the chart shows). */
  events(id: string, ticker: string): Promise<TickerEvents>;
  cancel(id: string): Promise<void>;
  /** A comparison line (S.cmp): the ticker's published close as of each day of `calendar` (null before its first bar). */
  closes(ticker: string, calendar: string[]): Promise<(number | null)[]>;
}
