/* Shared state of the terminal page. The reference page (03-terminal-right-panel.html) keeps it in one closure; here it
   is one object every section module receives, with the same names. Values that the reference reassigns
   (displayMode, chartStyle, axisLabel, onDisplayMode, COMBOS, lastTipIdx …) live on it so every module sees the change. */
import type { FlowRows } from '../calc/flow';
import type * as LWC from 'lightweight-charts';
import type { Bar, Combo, CompareSpec, Instrument, MarketData, Point, VolumePoint } from '../data/types';

export const $ = (id: string): any => document.getElementById(id);

export const store = {
  get(k: string): string | null { try{ return localStorage.getItem(k) }catch(e){ return null } },
  set(k: string, v: string) { try{ localStorage.setItem(k,v) }catch(e){} }
};

export const nfCompact = new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1});
export const rupiah = (n: number) => (n<0?'-':'')+'Rp '+nfCompact.format(Math.abs(n));
export const keyOf = (t: any): string | null => typeof t === 'string' ? t
  : (t && typeof t === 'object' ? `${t.year}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}` : null);

/** EXEC-TERMINAL-FRESH (user 2026-10-27): the last session on or before the broker data's last date; every session
    when that date is unknown (the fixture) */
export function brokerEnd(dates: string[], through?: string) {
  if(!through) return dates.length - 1;
  let i = dates.length - 1;
  while(i >= 0 && dates[i] > through) i--;
  return i;
}

/* tiny maths / formatting */
export const median = (a: number[]) => { const s=[...a].sort((x,y)=>x-y), m=s.length>>1; return s.length%2 ? s[m] : (s[m-1]+s[m])/2 };
export const avgOf = (a: number[]) => a.reduce((s,x)=>s+x,0)/a.length;
export const pct = (v: number, d=2) => (v>=0?'+':'')+v.toFixed(d)+'%';
export const cls = (v: number) => v>=0 ? 'up' : 'down';
export const row = (l: string, v: string | number, c='', tip='') => `<div class="st-row"${tip?` data-tip="${l}|${tip}"`:''}><span>${l}</span><b class="${c}">${v}</b></div>`;
export const empty = (msg: string) => `<div class="st-row"><span>${msg}</span></div>`;
/* EXEC-TERMINAL-SPIN: the loading ring, ui/spin.ts (one for every rack page since EXEC-BACKTEST-SPIN) */
export { spin } from '../ui/spin';
/* EXEC-TERMINAL-LOGO: a ticker's logo, or its monogram (first two letters) when it has none or the image fails */
let LOGOS: Record<string, string> | null = null;
export const setLogos = (logos: Record<string, string> | undefined) => {
  LOGOS = logos || null;
  if (LOGOS) document.addEventListener('error', (e: Event) => {
    const img = e.target as HTMLElement;
    if (img instanceof HTMLImageElement && img.classList.contains('tk-logo')) img.replaceWith(Object.assign(document.createElement('span'),
      { className:'tk-mono ' + [...img.classList].filter(c => c !== 'tk-logo').join(' '), textContent:img.dataset.t!.slice(0, 2) }));
  }, true);
};
export const hasLogos = () => !!LOGOS;
export const logoHtml = (ticker: string, cls = '') => LOGOS && LOGOS[ticker]
  ? `<img class="tk-logo ${cls}" src="/api/terminal/v1/logo/${ticker}?v=${LOGOS[ticker]}" alt="" data-t="${ticker}" loading="lazy" decoding="async">`
  : `<span class="tk-mono ${cls}">${ticker.slice(0, 2)}</span>`;

export interface ActiveSeries extends CompareSpec { series: LWC.ISeriesApi<'Line'>; visible: boolean }

export interface VolCtl {
  removed: boolean; on: boolean;
  apply: () => void; setRemoved: (r: boolean) => void; onChange: (() => void) | null; relabel?: () => void;
}

export interface IndSurface {
  byName: Record<string, string>; tips: Record<string, string>;
  countOf: (id: string) => number; count: () => number; add: (id: string) => unknown; removeAll: () => void;
  onChange: (() => void) | null;
}

export interface HistEntry { undo(): void; redo(): void }

export interface FilterOption { id: string; label: string }
export interface FilterApi { root: HTMLElement; close(): void; refresh(): void }

export interface Ctx {
  M: MarketData;
  L: typeof LWC;
  SYMBOL: string;
  INSTRUMENTS: Instrument[];
  container: HTMLElement;
  dates: string[];
  ohlc: Bar[];
  volume: VolumePoint[];
  lineData: Point[];
  closes: number[];
  N: number;
  idxByTime: Map<string, number>;
  /* main chart (chart.ts) */
  chart: LWC.IChartApi;
  candle: LWC.ISeriesApi<'Candlestick'>;
  mainLine: LWC.ISeriesApi<'Line'>;
  volumeSeries: LWC.ISeriesApi<'Histogram'>;
  chartStyle: string;
  displayMode: string;
  active: Map<string, ActiveSeries>;
  catalog: CompareSpec[];
  rawSeries: Record<string, Point[]>;
  axisLabel: (v: number) => string;
  formatMode: () => LWC.PriceFormatCustom;
  updateMainDisplay: () => void;
  onDisplayMode: () => void;
  displayHooks: (() => void)[];
  /* panels */
  ws: HTMLElement;
  scheduleStats: () => void;
  showStTip: (x: number, y: number, html: string) => void;
  hideStTip: () => void;
  tipHtml: (s: string) => string;
  volCtl: VolCtl;
  Ind: IndSurface;
  IND_REG: any[];
  Hist: { push(e: HistEntry): void };
  /* flow timeline (flow.ts) */
  flowChart: LWC.IChartApi;
  COMBOS: Combo[];
  flowSource: string;
  BOARDS: FilterOption[];
  INVESTORS: FilterOption[];
  allBrokers: () => string[];
  makeFilter: (root: HTMLElement, o: any) => FilterApi;
  lastTipIdx: number;
  tipHooks: ((i: number) => void)[];
  pushRange: (from: LWC.IChartApi, to: LWC.IChartApi) => void;
  syncAxisWidths: () => void;
  /* data that arrives after the first draw (live, EXEC-TERMINAL-UI-1026 U5) */
  setFlowData: (combos: Combo[], flowFrom: number, more?: boolean, flowTo?: number) => void;
  setBrokerPanelData: (broker: MarketData['broker']) => void;
  refreshFlowIndicators: () => void;
  /* EXEC-TERMINAL-FLOW-IND, live: the raw broker rows on the candles (worker.ts flowRowsOf), for the Flow indicators */
  flowRows?: FlowRows;
  /* EXEC-TERMINAL-PANELS: drag a period on the main chart (rangeSelect.ts) */
  selectRangeOnChart: (done: (from: string, to: string) => void) => void;
  crosshairAt: (i: number | null) => void;           // flow.ts: both charts' crosshair on session i
  /* EXEC-TERMINAL-FRESH: the last session with broker data (N - 1 when none is missing); later sessions are no data */
  brokerEnd: number;
  /* EXEC-TERMINAL-WM: each candle's last session date (= dates for daily candles); the first view of the timeframe */
  endDates: string[];
  resetRange: () => void;
  /* EXEC-TERMINAL-ASSETS, live: the ticker search used to add an asset (search.ts), the drawings of an asset's Flow
     Timeline (drawings.ts), the charts and heights the asset Flow Timelines add below the chart's own (assets.ts) */
  openTickerSearch?: (from: HTMLElement | null, use: { pick?: (r: Instrument) => void; tag?: (ticker: string) => string; label?: string }) => void;
  attachFlowDrawings?: (chart: LWC.IChartApi, series: LWC.ISeriesApi<any>, el: HTMLElement, ticker: string) => { manager: any; detach(): void };
  extraFlowCharts?: () => LWC.IChartApi[];
  extraFlowHeight?: () => number;
  axisWidths?: { left: number; right: number };
  refitFlow?: () => void;
  /* EXEC-TERMINAL-POPOUT (broker.ts): what Broker activity shares with its windows (popout.ts), live */
  brokerShared?: BrokerShared;
}

export interface BrokerShared {
  invSel: Set<string>; max: number; colors: string[];   // the brokers drawn in Broker inventory (panel and window)
  pick(b: string): void;                                // highlight a broker and add it to Broker inventory
  changed(): void;                                      // after invSel changed: the panel and the windows redraw
  listen(fn: () => void): void;                         // a window's redraw (also on new broker data)
  ready(): boolean;                                     // the broker data has arrived
  brokers(): string[];                                  // every broker code of the data
  selected(): string | null;
  ensureDefaults(): void;                               // no broker chosen: the three largest net buyers of the last 20 sessions
}
