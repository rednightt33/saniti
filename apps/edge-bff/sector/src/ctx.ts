/* EXEC-SECTOR-ANALYSIS S4: what every card is drawn with. A context holds the data of the chosen date (model.ts Data), the
   viewer's choices (State) and the actions a card may take. The page has one context; a floating window has its own, a
   copy of the page's choices made when it opens, so the window's filters never move the page's (the prototype's rule,
   logic.js L1274-1281). The state is plain data (it goes into the address, app.ts). */
import * as M from './model.ts';
import type { N, StocksFile } from './types.ts';
import { W } from './words.ts';

export type TabKey = 'ov' | 'rs' | 'rot' | 'pm' | 'br';
export const TABS: TabKey[] = ['ov', 'rs', 'rot', 'pm', 'br'];
export type Pk = string;                                     // a period key ('1M', '3M', 'YTD', 'C' = Custom)

export const DEFAULT_STATE = {
  tab: 'ov' as TabKey,
  date: null as string | null,                              // the picked market date (null: the newest), kept in the address (check 1 BD-10)
  pin: null as string | null,                               // the locked sector (every card that shows one sector follows it)
  // Overview
  rcW: '3M' as Pk, rcR: null as M.Range | null, rcSel: null as string[] | null, rcIh: true,
  mmX: '3M', mmY: '1M', hxS: [] as M.Level[], mkSub: null as string | null,
  // Relative Strength
  rsN: 5, rsB: 'rel', rbK: '5' as string, rbD: null as string | null, rsWn: '8' as string, rsWr: null as M.Range | null, rsWS: [] as M.Level[],
  rsS: [] as M.Level[], rsOpen: [] as string[], rsLw: '3M' as Pk, rsLr: null as M.Range | null, rsLh: null as string | null,
  // Rotation
  rotV: 'map', rotT: 4, rotK: null as string | null, rotIh: true, cmpW: 1, cmpS: 'ang', rotSel: [] as string[], rotP: 5,
  rbV: 'ch',                                                // Rotation detail's window: its quadrant changes ('ch') or all its columns ('all')
  rotS: [] as M.Level[], rotBm: 'ih', rqT: null as string | null,
  // Pair Matrix
  pmA: null as string | null, pmB: null as string | null, pqM: 'sp', pqP: '1M' as Pk, pqR: null as M.Range | null, pqW: 60, pqS: [] as M.Level[],
  prP: '6M' as Pk, prR: null as M.Range | null, prMA: 50, prMk: null as string | null,
  btW: '120' as string, btR: null as M.Range | null, btB: 'IHSG', btS: [] as M.Level[], stH: '1M', stF: 'all', stN: '7', stS: [] as M.Level[],
  // Breadth
  bhS: M.MARKET as string, bhM: 50 as 50 | 200, bhP: '6M' as Pk, bhR: null as M.Range | null, bhV: null as [string, string] | null, bhX: [] as string[],
  bhHid: [] as string[], bhMk: null as string | null, btC: 'pct', btTS: [] as M.Level[], btX: [] as string[], brM: 'ema', adH: 'r1d', bdF: 'all', bdS: [] as M.Level[], bdQ: '',
  // a window's detail table: its sort levels and search
  dS: [] as M.Level[], dQ: '',
};
export type State = typeof DEFAULT_STATE;
export const cloneState = (s: State): State => JSON.parse(JSON.stringify(s));

export type StocksState = { state: 'ready'; file: StocksFile } | { state: 'loading' | 'missing' | 'error' };
export interface Ctx {
  D: M.Data;
  S: State;
  win: boolean;                                              // drawn inside a floating window
  example: boolean;                                          // decision J: the example of one day
  /** lock a sector for every card of this context (again on the same sector: unlock) */
  lock(name: string | null, toggle?: boolean): void;
  /** draw every card of this context again (a choice changed) */
  redraw(): void;
  /** open the Terminal on a ticker (a stock, a sector index, IHSG) */
  terminal(ticker: string): void;
  /** one sector's daily stock closes (CONTRACT 3.4), read when first asked; the context is drawn again when it arrives */
  stocks(sector: string): StocksState;
}
export interface Col { k: string; l: string; f?: (v: any, r: any) => string; num?: boolean; tone?: boolean; html?: string; b?: boolean; hl?: boolean; tip?: string; term?: boolean }
/** a floating window's detail table (logic.js fwd*), with its "How to read" footer */
export interface Detail {
  title: string; sub: string; cols: Col[]; rows: any[]; sort: M.Level;
  onRow?(r: any, e?: MouseEvent | KeyboardEvent): void; isSel?(r: any): boolean;
  ctl?: string; onSel?(v: string): void;
  search?: string;                                           // the search box's placeholder (a table of stocks or pairs)
  center?: boolean;
  read: string;                                              // How to read
  ex?(r: any): string;                                       // the example sentence, built from the first row shown
  note?: string;
  limit?: number;                                            // show that many rows of the order (Stretched pairs' Show)
  limitNone?(q: string): string;                             // the search's no-match line while rows are limited
  empty?: string;                                            // the line of a table without rows
  wire?(box: HTMLElement): void;                             // binds the detail's own controls (its ctl) after a draw
}
export interface Card {
  id: string; tab: TabKey; cls: string;
  render(el: HTMLElement, c: Ctx): void;
  detail?(c: Ctx): Detail;
  stack?: boolean;                                           // the window shows the card above its detail
  /* visual round 2 (windows.ts): the side-by-side window as tall as its detail table, the element `fit[0]` of the card
     taking the height (its least: the natural height of `fit[1]`, else its CSS min-height or its rows); the card's table
     and the detail's on one column grid (`align`); the Rotation detail's list and detail (`layout: 'c1'`); the detail
     hidden for a view (`hideDetail`, the Rotation map's Timeline); a window up to the screen's width (`wide`) */
  fit?: [grow: string, least?: string, plus?: number];
  align?: boolean;
  layout?: 'c1';
  hideDetail?(c: Ctx): boolean;
  wide?: boolean;
}

/* ===================== the measures several cards read, computed once per date ===================== */
export interface Calc {
  /** excess return of a sector over n sessions ending at i, pp (logic.js L26) */
  rr(nm: string, n: number, i?: number): N;
  /** rank 1..11 by the n-session excess return at i */
  rankAt(n: number, i: number): Record<string, number>;
  /** the rotation map series of each sector against the market (model.ts rotation) */
  rot: Record<string, { rs: N[]; mom: N[] }>;
  /** the quadrant of each sector on every date */
  q: Record<string, (M.Quad | null)[]>;
  /** the sector with the best 1W excess return on the date (the single-sector cards' sector until one is locked) */
  strongest: string;
  /** a return over a period key ending at E (or a Custom span) */
  retP(a: N[], p: Pk, r: M.Range | null): N;
  /** the span of a period key: [base, end], the period it shows (`key`: 'C' only when the Custom range is shown) and a
      note when a stored Custom range was clamped or could not be shown (check 1 RP-1: never replaced silently) */
  span(p: Pk, r: M.Range | null, dflt?: string): PSpan;
  /** the name of a span in a label: its dates for a Custom range, else its period key (never the internal "C") */
  plabel(s: PSpan): string;
}
export interface PSpan { b: number; e: number; custom: boolean; key: string; note: string | null }
/** a stored Custom range on the page's data: its span and the note of what was clamped; or the card's preset, with the
    note that the range has no session up to the page's date */
export function customSpan(D: M.Data, r: M.Range, dflt: string, o: M.RangeOpts = {}): { s: M.Resolved | null; note: string | null } {
  const s = M.resolveRange(D.dates, r, D.E, o);
  if (!s) return { s: null, note: W.range.none(dflt) };
  const note = s.clampStart ? W.range.clampStart(M.dateLabel(D.dates[o.level ? s.first : s.base], false, true)) : s.clampEnd ? W.range.clampEnd(M.dateLabel(D.dates[s.last], false, true)) : null;
  return { s, note };
}
const cache = new WeakMap<M.Data, Calc>();
export function calc(D: M.Data): Calc {
  let c = cache.get(D);
  if (c) return c;
  const E = D.E, IH = D.IH, rrMemo = new Map<string, N>();
  const rr = (nm: string, n: number, i = E): N => {
    const k = `${nm}|${n}|${i}`;
    if (!rrMemo.has(k)) rrMemo.set(k, M.minus(M.ret(D.sec(nm), i, n), M.ret(IH, i, n)));
    return rrMemo.get(k) as N;
  };
  const rot = Object.fromEntries(D.names.map(n => [n, M.rotation(D.sec(n), IH)]));
  const q = Object.fromEntries(D.names.map(n => [n, rot[n].rs.map((x, i) => M.quad(x, rot[n].mom[i]))]));
  const w = D.P('1W');
  const strongest = [...D.names].sort((a, b) => (rr(b, w) ?? -Infinity) - (rr(a, w) ?? -Infinity))[0];
  const preset = (k: string, note: string | null): PSpan => (k === 'YTD' ? { b: D.ytd(), e: E, custom: false, key: k, note } : { b: Math.max(0, E - D.P(k)), e: E, custom: false, key: k, note });
  const span = (p: Pk, r: M.Range | null, dflt = '3M'): PSpan => {
    if (p !== 'C') return preset(p, null);
    if (!r) return preset(dflt, null);                          // Custom without a range: the card's own period
    const { s, note } = customSpan(D, r, dflt);
    return s ? { b: s.base, e: s.last, custom: true, key: 'C', note } : preset(dflt, note);
  };
  c = {
    rr, rot, q, strongest, span,
    plabel: s => (s.custom ? M.rangeLabel(D.dates[s.b], D.dates[s.e], D.ref) : s.key),
    rankAt: (n, i) => M.rankOf(D.names, nm => rr(nm, n, i)),
    retP: (a, p, r) => { const s = span(p, r); return M.retAt(a, s.b, s.e) },
  };
  cache.set(D, c);
  return c;
}
/** the sector a single-sector card shows: the locked one, else the strongest of the week (defect: Infra shown silently) */
export const shown = (c: Ctx) => (c.S.pin && c.D.names.includes(c.S.pin) ? c.S.pin : calc(c.D).strongest);
