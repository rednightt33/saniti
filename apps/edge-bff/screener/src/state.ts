/* The page's state (the prototype's S, "state") and what the modules share: the catalog and universe of this page
   load, the current result, the API, and the renderers each module registers (ui), so the modules call each other
   without import cycles. The portable definition (report 9.5, 6.15) is built from S here: one object for run, save,
   CSV metadata and Send to Backtest. */
import type {
  CatalogPreset, CatalogResponse, Definition, Logic, ResultRow, RunResponse, SavedItem, UniverseDef, UniverseResponse,
  UniverseRow, ValueTest,
} from './core/contract.ts';
import { UNIVERSE_DEFAULTS } from './core/contract.ts';
import type { ScreenerApi } from './api/types.ts';
import type { Entry } from './entries.ts';
import { fromWire, toWire, type Card } from './forms.ts';

/** The universe as the page edits it: the wire UniverseDef (report 8.5) with metric filters kept as cards. */
export interface UState extends Omit<UniverseDef, 'metric_filters'> { filters: Card[] }
export const freshUniverse = (): UState => {
  const { metric_filters, ...u } = JSON.parse(JSON.stringify(UNIVERSE_DEFAULTS)) as UniverseDef;
  return { ...u, sectors_in:[], sectors_out:[], industries_in:[], industries_out:[], filters:[] };
};

export type Source = null | { kind: 'preset'; id: string } | { kind: 'saved'; item_id: string; revision: number };
export type SortKey = 'match' | 'sym' | 'last' | 'd1' | 'adv' | `c:${string}`;
export interface PageState {
  name: string; source: Source; dirty: boolean;
  universe: UState; cards: Card[]; open: Set<string>; logic: Logic; atLeast: number;
  nearMiss: boolean; sort: { key: SortKey; dir: 'asc' | 'desc' }; sel: Set<string>; pick: string | null;
  dtab: 'stock' | 'method'; pcat: string; pexp: boolean; pvView: 'chart' | 'perf'; perf: '1M' | '3M' | '6M' | '1Y';
  q: string; page: number; perPage: number; preview: boolean; bOpen: boolean; pop: string | null; drawer: boolean;
  errors: Record<string, Record<string, string>>;   // per card id: field -> message (refused in place, report 9.2)
}
export const S: PageState = {
  name:'Untitled screen', source:null, dirty:false, universe:freshUniverse(), cards:[], open:new Set(), logic:'all', atLeast:2,
  nearMiss:false, sort:{ key:'match', dir:'desc' }, sel:new Set(), pick:null, dtab:'stock', pcat:'All', pexp:false, pvView:'chart', perf:'6M',
  q:'', page:1, perPage:25, preview:false, bOpen:true, pop:null, drawer:false, errors:{},
};

/** A shown row: a run's row, or a universe row while the screen has no condition (report 6c.4 S5). */
export interface Row {
  ticker: string; name: string | null; sector: string | null; industry: string | null;
  last: number | null; chg_1d_pct: number | null; adv20_idr: number | null;
  status: 'match' | 'near' | 'universe'; met: number; need: number; remarks: ResultRow['remarks']; cells: ResultRow['cells'];
  stale: boolean; last_bar_date: string;
}
export const rowOfUniverse = (u: UniverseRow): Row => ({ ticker:u.ticker, name:u.name, sector:u.sector, industry:u.industry, last:u.last,
  chg_1d_pct:u.chg_1d_pct, adv20_idr:u.adv20_idr, status:'universe', met:0, need:0, remarks:u.remarks, cells:[], stale:u.stale, last_bar_date:u.last_bar });
export const rowOfResult = (r: ResultRow): Row => ({ ticker:r.ticker, name:r.name, sector:r.sector, industry:r.industry, last:r.last,
  chg_1d_pct:r.chg_1d_pct, adv20_idr:r.adv20_idr, status:r.status, met:r.met, need:r.need, remarks:r.remarks, cells:r.cells, stale:r.stale, last_bar_date:r.last_bar_date });

/** The current result the table shows (the prototype's R). */
export interface Result {
  rows: Row[];                       // matches and near rows of a run; the eligible universe rows without conditions
  run: RunResponse | null;           // null while the screen has no condition (local, no run)
  defHash: string;                   // canonical JSON of the definition it answers (the page's own key; out-of-date mark)
  eligible: number; listed: number; staleHidden: number; breakHidden: number;
}
export interface Ctx {
  api: ScreenerApi;
  catalog: CatalogResponse | null; universe: UniverseResponse | null;
  entries: Entry[]; byKey: Map<string, Entry>;
  R: Result | null;
  running: boolean; runError: string | null; updating: boolean; stale: boolean;
  saved: SavedItem[] | null; metrics: SavedItem[] | null; watch: Set<string> | null;
  counts: Map<string, { match: number; near: number } | { error: string }>;
  login: string;
  bootState: 'skeleton' | 'cached' | 'results';
}
export const ctx: Ctx = {
  api:null as unknown as ScreenerApi, catalog:null, universe:null, entries:[], byKey:new Map(), R:null,
  running:false, runError:null, updating:false, stale:false, saved:null, metrics:null, watch:null, counts:new Map(), login:'', bootState:'skeleton',
};

/** The renderers and actions the modules register (app.ts wires them). */
export const ui = {
  refresh: (_level: 'all' | 'universe' | 'universe-light' | 'conds' | 'conds-light' | 'results') => {},
  renderHeader: () => {}, renderUniverse: () => {}, renderPresets: () => {}, renderConds: () => {}, renderResults: () => {},
  renderDetails: () => {}, togglePreview: (_on: boolean) => {}, pickStock: (_tk: string) => {}, openSource: (_id: string) => {},
  toast: (_m: string) => {}, markDirty: () => {}, schedule: (_now?: boolean) => {},
};

export const activeCards = (cards = S.cards) => cards.filter(c => c.on);
export const entryOf = (c: Card) => c.entry ? ctx.byKey.get(c.entry) : undefined;

/** The portable definition of the page state (report 6.15): universe, conditions in card order, logic. */
export function definitionOf(st: { universe: UState; cards: Card[]; logic: Logic; atLeast: number } = S): Definition {
  const { filters, ...u } = st.universe;
  const universe: UniverseDef = {
    ...u,
    metric_filters:filters.map(f => toWire(ctx.byKey.get(f.entry || ''), f).test as ValueTest),
  };
  // empty include and exclude lists are left out of the wire (they mean "no filter")
  for (const k of ['sectors_in', 'sectors_out', 'industries_in', 'industries_out'] as const) if (!universe[k]?.length) delete universe[k];
  if (!universe.metric_filters?.length) delete universe.metric_filters;
  const def: Definition = { universe, conditions:st.cards.map(c => toWire(entryOf(c), c)), logic:st.logic };
  if (st.logic === 'at_least') def.at_least = Math.max(1, Math.round(Number(st.atLeast) || 1));
  return def;
}
/** Canonical JSON (sorted keys): the page's own key of a definition (out-of-date mark, CSV metadata when the run has
    not answered). The worker's definition_hash is the sha256 of the resolved definition; the page never computes it. */
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']';
  if (v && typeof v === 'object') return '{' + Object.keys(v).sort().filter(k => (v as any)[k] !== undefined).map(k => JSON.stringify(k) + ':' + canonical((v as any)[k])).join(',') + '}';
  return JSON.stringify(v);
}

/** Page state of a definition (a preset's, a saved screen's): cards from the wire, nothing adjusted (report 9.5). */
export function stateOfDefinition(def: Definition): { universe: UState; cards: Card[]; logic: Logic; atLeast: number } {
  const base = freshUniverse();
  const { metric_filters, ...u } = def.universe || ({} as UniverseDef);
  const universe: UState = { ...base, ...JSON.parse(JSON.stringify(u)),
    filters:(metric_filters || []).map((t, i) => fromWire({ id:'f' + i, enabled:true, test:t }, ctx.byKey)) };
  for (const k of ['sectors_in', 'sectors_out', 'industries_in', 'industries_out'] as const) universe[k] = universe[k] || [];
  const cards = (def.conditions || []).map(cd => fromWire(cd, ctx.byKey));
  return { universe, cards, logic:def.logic || 'all', atLeast:def.at_least || 2 };
}

export const presetOf = (id: string): CatalogPreset | undefined => ctx.catalog?.presets.find(p => p.id === id);
export const savedOf = (id: string): SavedItem | undefined => ctx.saved?.find(s => s.item_id === id);
/** the evaluation date E of this page load */
export const evalDate = () => ctx.catalog?.data.evaluation_date || ctx.universe?.data.evaluation_date || null;
