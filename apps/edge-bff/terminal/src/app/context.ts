/* Shared state of the terminal page. The reference page (03-terminal-right-panel.html) keeps it in one closure; here it
   is one object every section module receives, with the same names. Values that the reference reassigns
   (displayMode, chartStyle, axisLabel, onDisplayMode, COMBOS, lastTipIdx …) live on it so every module sees the change. */
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
/* EXEC-TERMINAL-SPIN (user 2026-10-26: "lingkaran berputar dengan cepat"): a spinning ring with a short text, for
   anything still loading */
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
export const spin = (msg: string) => `<span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>${msg}</span>`;

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
  /* EXEC-TERMINAL-PANELS: drag a period on the main chart (rangeSelect.ts) */
  selectRangeOnChart: (done: (from: string, to: string) => void) => void;
  crosshairAt: (i: number | null) => void;           // flow.ts: both charts' crosshair on session i
  /* EXEC-TERMINAL-FRESH: the last session with broker data (N - 1 when none is missing); later sessions are no data */
  brokerEnd: number;
  staleLabel: () => string;                          // flow.ts: "Broker through … · price …", or '' when current
}
