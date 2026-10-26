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

/* tiny maths / formatting */
export const median = (a: number[]) => { const s=[...a].sort((x,y)=>x-y), m=s.length>>1; return s.length%2 ? s[m] : (s[m-1]+s[m])/2 };
export const avgOf = (a: number[]) => a.reduce((s,x)=>s+x,0)/a.length;
export const pct = (v: number, d=2) => (v>=0?'+':'')+v.toFixed(d)+'%';
export const cls = (v: number) => v>=0 ? 'up' : 'down';
export const row = (l: string, v: string | number, c='', tip='') => `<div class="st-row"${tip?` data-tip="${l}|${tip}"`:''}><span>${l}</span><b class="${c}">${v}</b></div>`;
export const empty = (msg: string) => `<div class="st-row"><span>${msg}</span></div>`;
/* EXEC-TERMINAL-SPIN (user 2026-10-26: "lingkaran berputar dengan cepat"): a spinning ring with a short text, for
   anything still loading */
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
  setFlowData: (combos: Combo[], flowFrom: number, more?: boolean) => void;
  setBrokerPanelData: (broker: MarketData['broker']) => void;
  refreshFlowIndicators: () => void;
}
