/* The data the terminal draws, in the reference page's own shapes (03-terminal-right-panel.html). Two sources fill it:
   fixture.ts (the reference's synthetic generator, for the 1:1 check) and live.ts (the published files of the rack). */
import type { FlowRows } from '../calc/flow';
import type { Timeframe } from './timeframe';

export interface Bar { time: string; open: number; high: number; low: number; close: number }
export interface Point { time: string; value: number }
/** EXEC-FI-TERMINAL: a candle of an added asset. A bond on a stock chart may carry its last close onto a session it did
    not trade (`carriedFrom`: the date the value comes from) or have no value on a candle (`gap`: the line breaks there;
    its numbers are NaN) */
export interface AssetBar extends Bar { carriedFrom?: string; gap?: boolean }
/** `none`: the source has no volume for the candle (an index); `value` is then 0 for the histogram only */
export interface VolumePoint extends Point { color: string; none?: boolean }

/** [ticker, name, sector, last price, where] — the reference's INSTRUMENTS row (the price only seeds the fixture);
    `where` (live): the market it trades in ("IDX · Equity", "Fixed income") and a bond's country, for the search */
export interface InstrumentPlace { market: string; place?: string }
export type Instrument = [string, string, string, number, InstrumentPlace?];

/** one compare series of the Add Series panel */
export interface CompareSpec { id: string; symbol: string; name: string; color: string }

/** one broker × investor type × board with its daily net value per session of the chart */
export interface Combo { broker: string; investor: string; board: string; gross: number; tilt: number; net: Float64Array }

/** a broker summary row: [broker, investor, board, buyValue, sellValue, buyLots, sellLots] */
export type BrokerRow = [string, string, string, number, number, number, number];

/** `at`: the session the marker sits on when the event date is not a session (live data); the tooltip shows `date` */
export interface MarketEvent { id: string; type: string; date: string; at?: string; title: string; rows: [string, string][];
  /** the date as the tooltip writes it (live: "03 December 2025"); the fixture shows `date` as the reference does */
  label?: string }

/** EXEC-TERMINAL-ASSETS: an added asset's broker flow on the chart's sessions, the recent years first (as LateBroker) */
export interface AssetFlowPart { combos: Combo[]; flowFrom: number; flowTo: number }
export interface AssetFlow { recent: Promise<AssetFlowPart>; all: Promise<AssetFlowPart>; through?: string }

/** live broker data that arrives after the first draw: the recent years first, then the whole history (F5) */
/** flow (EXEC-TERMINAL-FLOW-IND): the raw broker rows on the chart's candles, for the Flow indicators (calc/flow.ts) */
export interface LateBroker { combos: Combo[]; flowFrom: number; flowTo: number; broker: MarketData['broker']; flow?: FlowRows }

/** an insider transaction of the events file: its date and signed value (BUY +, SELL −; IDR) */
export interface InsiderTx { d: string; value: number }

export interface MarketData {
  mode: 'fixture' | 'live';
  symbol: string;
  instruments: Instrument[];
  ohlc: Bar[];
  volume: VolumePoint[];
  lineData: Point[];
  /** compare series offered in the Add Series panel, and their values aligned to the chart's sessions */
  catalog: CompareSpec[];
  loadCompare(id: string): Promise<Point[]>;
  /** fixture only: every compare series, built up front as the reference does */
  rawSeries?: Record<string, Point[]>;
  /** IHSG aligned to the chart's sessions (Statistics, Relative performance); live: empty, read with loadIhsg when
      the Statistics panel is open */
  ihsg: Point[];
  loadIhsg?(): Promise<Point[]>;
  /** live: the broker data, after the first draw (Flow Timeline, then Broker activity when its panel is open) */
  later?: { broker: Promise<LateBroker>; brokerAll: Promise<LateBroker> };
  /** EXEC-TERMINAL-FLOW-IND, live: the insider transactions of the events file, and each broker's classification
      (ref/brokers `classification`: Institutional-heavy, Retail-heavy, Mixed, Niche) */
  loadInsider?: () => Promise<InsiderTx[]>;
  brokerClass?: Promise<Record<string, string>>;
  combos: Combo[];
  flowSource: 'synthetic' | 'real';
  /** first session index that has broker data (0 in the fixture) */
  flowFrom: number;
  /** Broker activity panel: its sessions (ascending) and the summary rows of each */
  broker: { dates: string[]; rows(d: number): BrokerRow[]; label: string; category(code: string): string };
  loadEvents(): Promise<MarketEvent[]>;
  /** live: ticker → logo version for /logo/{ticker}?v=…; absent in the fixture (the reference has no logos) */
  logos?: Record<string, string>;
  /** live (ERRORS M333): the same list, arriving after the chart (the chart does not wait for it) */
  logosLater?: Promise<Record<string, string>>;
  /** live: a government bond's country (ref/fixed_income), for its flag */
  countries?: Record<string, string>;
  /** live (EXEC-TERMINAL-WM): the timeframe of the candles, each candle's last session date and the candle that holds
      a date (drawings, G1); absent in the fixture (daily) */
  tf?: Timeframe;
  endDates?: string[];
  barOf?(date: string): string | null;
  /** live (EXEC-TERMINAL-FRESH): each dataset's last date from the manifest; sessions after `broker` have no broker
      data yet. Absent in the fixture. */
  through?: { price?: string; broker?: string };
  /** live (EXEC-TERMINAL-ASSETS): an added asset's candles on the chart's candles, and its Flow Timeline data; absent in
      the fixture (its Add Series panel stays the reference's) */
  loadAsset?(ticker: string): Promise<AssetBar[]>;
  /** EXEC-FI-TERMINAL: a government bond (ref/fixed_income): as an added asset its yield, without a Flow Timeline */
  isBond?(ticker: string): boolean;
  loadAssetFlow?(ticker: string): Promise<AssetFlow>;
  /** live (EXEC-INTRADAY-FEATURES C3): the intraday timeframes the ticker has (its /bundle answer) */
  timeframes?: string[];
  /** live: why the chart is not the timeframe asked (the ticker lacks it) */
  note?: string;
  /** live, on an intraday chart (C3-C4): the daily sessions behind the daily figures, their price rows, the session each
      candle shows (timeframe.ts dayOfCandles), the timeframe's bars per year and its first and last bar */
  intraday?: { dayOf: Int32Array; days: string[]; daily: { d: string; o: number; h: number; l: number; c: number; v: number | null }[];
    barsPerYear?: number; first?: string; last?: string };
  /** EXEC-FI-TERMINAL (user go 2026-11-01): the chart is a government bond: the metric drawn (yield by default, or its
      price), its units (`PCTDY`: a US bill's price is a discount quote) and where it is from; no broker, events or
      intraday data */
  fixedIncome?: { metric: 'yield' | 'price'; name: string; country: string; units: { yield?: string; price?: string } };
  /** EXEC-IHSG-FLOW (user go 2026-11-03): the ticker is an index (ref/tickers type 'index'): its broker rows are the market
      aggregate, so lots and average prices are not one security's (data/inputs.ts 'single') */
  index?: true;
  /** what the live page cannot show yet (approved formulas pending); the fixture shows everything */
  hide: { brokerGauge: boolean; bandar: boolean };
}
