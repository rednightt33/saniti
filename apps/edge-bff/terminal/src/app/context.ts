/* Shared state of the terminal page. The reference page (03-terminal-right-panel.html) keeps it in one closure; here it
   is one object every section module receives, with the same names. Values that the reference reassigns
   (displayMode, chartStyle, axisLabel, onDisplayMode, COMBOS, lastTipIdx …) live on it so every module sees the change. */
import { flagOf } from './flags';
import type { FlowRows } from '../calc/flow';
import type * as LWC from 'lightweight-charts';
import type { Bar, Combo, CompareSpec, Instrument, MarketData, Point, VolumePoint } from '../data/types';
import { fromChart } from '../data/chartTime';

export const $ = (id: string): any => document.getElementById(id);

/* EXEC-TERMINAL-LAYOUTS: a saved setting that changes is announced (the layout menu's autosave and unsaved mark) */
export const storeWatch = new Set<(k: string) => void>();
const told = (k: string) => storeWatch.forEach(fn => { try { fn(k) } catch(e) {} });
export const store = {
  get(k: string): string | null { try{ return localStorage.getItem(k) }catch(e){ return null } },
  set(k: string, v: string) { let was: string | null = null; try{ was = localStorage.getItem(k); localStorage.setItem(k,v) }catch(e){ return } if(was !== v) told(k) },
  remove(k: string) { let was: string | null = null; try{ was = localStorage.getItem(k); localStorage.removeItem(k) }catch(e){ return } if(was !== null) told(k) }
};

export const nfCompact = new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1});
/** EXEC-QA5-FIX (QA 2026-11-07, S-08): an axis tick keeps two decimals, so 1,250 reads 1.25K, not "1.3K" beside 1.3K */
export const tickCompact = (v: number) => (v < 0 ? '−' : v > 0 ? '+' : '') + new Intl.NumberFormat('en-US', { notation:'compact', maximumFractionDigits:2 }).format(Math.abs(v));
/** EXEC-QA5-FIX (S-09): the candles with any part on screen (a monthly candle half in view counts, as the eye reads it);
    the broker windows, the inventory panel and the Flow anchor share this one rule */
export const visibleBars = (r: { from: number; to: number } | null, N: number): [number, number] =>
  [r ? Math.max(0, Math.ceil(r.from - 0.5)) : 0, r ? Math.min(N - 1, Math.floor(r.to + 0.5)) : N - 1];
/** QA round 3 (one minus sign): a negative figure on the page takes the minus sign "−", never the hyphen "-"; text that
    already holds a hyphen-minus before a figure is turned the same way */
export const minus = (s: string) => s.replace(/(^|[\s(>:=~≤≥|])-(?=\d|Rp|\.\d)/g, '$1−');
export const rupiah = (n: number) => (n<0?'−':'')+'Rp '+nfCompact.format(Math.abs(n));
export const keyOf = (t: any): string | null => typeof t === 'string' ? t
  : typeof t === 'number' ? fromChart(t)                    // an intraday candle (data/chartTime.ts)
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
export const pct = (v: number, d=2) => { const r = +v.toFixed(d); return (r>0?'+':r<0?'−':'')+Math.abs(r).toFixed(d)+'%' };   // never "−0.00%"
export const cls = (v: number) => v>=0 ? 'up' : 'down';
export const row = (l: string, v: string | number, c='', tip='') => `<div class="st-row"${tip?` data-tip="${l}|${minus(tip)}"`:''}><span>${l}</span><b class="${c}">${minus(String(v))}</b></div>`;
export const empty = (msg: string) => `<div class="st-row"><span>${msg}</span></div>`;
/* EXEC-TERMINAL-SPIN: the loading ring, ui/spin.ts (one for every rack page since EXEC-BACKTEST-SPIN) */
export { spin } from '../ui/spin';
/* EXEC-TERMINAL-LOGO: a ticker's logo, or its monogram (first two letters) when it has none or the image fails.
   ERRORS M333: the logo list arrives after the chart (the chart does not wait for it); what shows a logo when the page
   starts redraws it through onLogos. A government bond shows its country's flag (app/flags.ts, setCountries). */
let LOGOS: Record<string, string> | null = null, COUNTRY: Record<string, string> = {}, errorHook = false;
const logoWaiters: (() => void)[] = [];
/** run `fn` now and again when the logo list arrives (a part drawn before the list) */
export const onLogos = (fn: () => void) => { logoWaiters.push(fn); fn() };
/** ticker → country of the government bonds (ref/fixed_income) */
export const setCountries = (c: Record<string, string> | undefined) => { COUNTRY = c || {} };
export const setLogos = (logos: Record<string, string> | undefined) => {
  LOGOS = logos || null;
  if (LOGOS) logoWaiters.forEach(fn => fn());
  if (!LOGOS || errorHook) return;
  errorHook = true;
  document.addEventListener('error', (e: Event) => {
    const img = e.target as HTMLElement;
    if (img instanceof HTMLImageElement && img.classList.contains('tk-logo')) img.replaceWith(Object.assign(document.createElement('span'),
      { className:'tk-mono ' + [...img.classList].filter(c => c !== 'tk-logo').join(' '), textContent:img.dataset.t!.slice(0, 2) }));
  }, true);
};
export const hasLogos = () => !!LOGOS || Object.keys(COUNTRY).length > 0;
export const logoHtml = (ticker: string, cls = '') => LOGOS && LOGOS[ticker]
  ? `<img class="tk-logo ${cls}" src="/api/terminal/v1/logo/${ticker}?v=${LOGOS[ticker]}" alt="" data-t="${ticker}" loading="lazy" decoding="async">`
  : flagOf(COUNTRY[ticker]) ? `<span class="tk-flag ${cls}" title="${COUNTRY[ticker]}">${flagOf(COUNTRY[ticker])}</span>`
  : `<span class="tk-mono ${cls}">${ticker.slice(0, 2)}</span>`;

export interface ActiveSeries extends CompareSpec { series: LWC.ISeriesApi<'Line'>; visible: boolean }

export interface VolCtl {
  removed: boolean; on: boolean;
  /** ERRORS M332: the ticker has no volume, so the histogram and its row are not drawn (not the user's removal) */
  absent?: boolean;
  apply: () => void; setRemoved: (r: boolean) => void; onChange: (() => void) | null; relabel?: () => void;
}

export interface IndSurface {
  byName: Record<string, string>; tips: Record<string, string>;
  countOf: (id: string) => number; count: () => number; add: (id: string) => unknown; removeAll: () => void;
  onChange: (() => void) | null;
  /** EXEC-IND-CARDS: an indicator as the chart has it, for its card */
  /** EXEC-INV-SYNC: a broker picked in the right panel (Broker Inventory indicators take it) */
  brokerPicked?: (code: string, panel?: { before: string[]; after: string[]; restore: (codes: string[]) => void }) => void;
  /** EXEC-IND-PRESETS: add an indicator from a preset (one undo step); the chart's indicators of an id, as presets read them;
      the presets module's "save this one" (set by presets.ts) */
  addPreset?: (defId: string, config: any, presetId?: string) => unknown;
  onChartOf?: (defId: string) => { title: string; config: any; presetId?: string }[];
  savePreset?: (p: { defId: string; title: string; config: any }) => void;
  defName?: (defId: string) => string | null;
}

export interface HistEntry { undo(): void; redo(): void }

export interface FilterOption { id: string; label: string }
export interface FilterApi { root: HTMLElement; close(): void; refresh(): void; sync?: () => void }

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
  /** EXEC-TERMINAL-LOOK 2: the price as the axis writes it (thousands, the instrument's decimals) */
  priceText: (v: number) => string;
  priceDecimals: number;
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
  /** QA M6: the broker files could not be loaded */
  brokerFailed?: boolean;
  /** QA R2-M3: the right panel says the broker files failed instead of loading for ever */
  redrawFlow?: () => void;
  brokerPanelFailed?: () => void;
  /* EXEC-TERMINAL-PANELS: drag a period on the main chart (rangeSelect.ts) */
  selectRangeOnChart: (done: (from: string, to: string) => void, cancelled?: () => void) => void;
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
  /** EXEC-DRAW-PANES (live): the drawings of each indicator pane, called by indicators.ts for a pane indicator (`pid` kept
      with it): attach once its series exist, rebind when its series are replaced, show with its pane, forget when the user
      removes it (2A), detach when it goes */
  paneDraw?: { attach(inst: any): void; rebind(inst: any): void; show(inst: any): void; forget(inst: any): void; detach(inst: any): void };
  extraFlowCharts?: () => LWC.IChartApi[];
  extraFlowHeight?: () => number;
  axisWidths?: { left: number; right: number };
  refitFlow?: () => void;
  /* EXEC-TERMINAL-POPOUT (broker.ts): what Broker activity shares with its windows (popout.ts), live */
  brokerShared?: BrokerShared;
  /** EXEC-IND-PRESETS: the owner's indicator presets (live only; presets.ts) */
  presets?: import('./presets').PresetsSurface | null;
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
