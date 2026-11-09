/* EXEC-SCREENER-V21: extra table columns (returns, range, liquidity, volatility and indicator values at their default
   settings) beside the screen's own condition columns. Product decision 5 (user 2026-11-06): only where the value,
   unit, parameters, data version, NA reason and price-break remark are all kept. Values come only from the worker's
   answers, never from a formula on the page (contract header, api/types.ts).

   How the worker returns one cell per column for every ticker of the table, NA cells with their reason included, and
   nothing else (proof: tests/page/extra-columns-core.test.ts runs this module's definition through the real core,
   src/core/screen.ts runScreen):
   - universe = the table's own universe (the same S0 filters, so the same tickers pass and carry the same row remarks)
     with `tickers` set to a chunk of the table's tickers (UniverseDef.tickers; core/universe.ts keeps only those);
   - conditions = an anchor that passes on every listed ticker, VALUE `bars gt 0` (a universe attribute with no
     applies_to: every ticker with bars has bars >= 1; condition.ts bindValue), then one VALUE test per column on the
     column's metric (op and threshold do not change the cell's value; the page shows the value, never pass or fail);
   - logic 'any': need = 1 (match.ts needOf), so every chunk ticker is a match row (met >= 1 through the anchor) and the
     planner prunes nothing (plan.ts runPlan `prune = need >= 2`); S4 completes every cell of every row, so each column
     cell is there, with status, value, unit, eval_date, reason (NA) and remark (PRICE_BREAK_IN_LOOKBACK);
   - data_version = the table's versions.price_data (RunRequest.data_version): the replica answers at that
     publication or refuses DATA_VERSION_CHANGED; an answer whose versions differ (any field but definition_hash) from
     the table's or the catalog's is dropped.
   The request goes on its own client_order page (api/live.ts lane 'aux': a second page id with its own seq), so it
   can never make the main run answer SCREEN_REPLACED: edge-bff keys latest wins by (owner, lane, page)
   (apps/edge-bff/app/screener.py `latest`, slot = (owner, lane, page)) and the worker replaces only a waiting request
   of the same page (apps/screener-worker/src/pool.ts header). It is sent only after the main run has settled, one at a
   time, chunked to catalog.limits (max_conditions: the anchor plus at most max_conditions - 1 columns; tickers sized to
   max_response_bytes and request_bytes), and cancelled by a new main run, a publication change or a column change.
   A failure marks the columns it carried (and the rest still missing for that table) with its message: never a retry
   loop. The answer never touches ctx.R, the saved definition or the main result state. */
import type { Cell, ConditionDef, Definition, ParamMap, PerfPeriod, ResolvedParams, RowRemark, UniverseDef, ValueTest, Versions } from './core/contract.ts';
import { UNIVERSE_DEFAULTS } from './core/contract.ts';
import { ApiFailure, isAbort } from './api/types.ts';
import { VERSION_FIELDS } from './api/boot-cache.ts';
import { canonical, ctx, ui } from './state.ts';
import { defaultParams, formatOfOpt, optionText, paramError, type Entry, type Opt } from './entries.ts';
import { comparableAcrossStocks, type ValueFormat } from './format.ts';
import { newCard, toWire } from './forms.ts';
import { store } from './storage.ts';
import { T } from './texts.ts';

/** A column the user can add. `id` is stable (saved per browser); label, unit and params come from the catalog. */
export interface ExtraColumnDef {
  id: string;
  group: string;                 // e.g. 'Price', 'Returns', 'Volume', 'Volatility', 'Indicators'
  label: string;                 // the header text (catalog wording)
  short: string;                 // a compact header
  unit: string | null;           // the backend unit of the value (contract Cell.unit / registry output unit)
  /** how the value is written (format.ts fmtValue): from the catalog's output unit and display_unit or the metric's
      unit, never from the wire's coarse Cell.unit (integration of the data audit, D-1) */
  format: ValueFormat;
  params: ParamMap;              // the parameters the value is computed with
  /** the parameters in the catalog's words (each parameter's label and option text), for the picker and the header
      tooltip; never the wire keys (QA L2) */
  paramText: string;
  /** why the column cannot be offered now (shown greyed with this reason); null when it can */
  unavailable: string | null;
}
/** What a cell of an extra column shows. `value`: the worker's cell for this ticker, with status, reason, remark and
    eval_date kept (contract Cell). */
export type ExtraCellState =
  | { kind: 'value'; cell: Cell }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'none' };            // the column is not shown, or the row is not part of the answer the table holds

/* ---- which columns exist (THE one list to change; subagent 2 / the coordinator decide VERIFIED, BLOCKED, REMOVE) --
   Each candidate is a catalog entry (ctx.byKey: an indicator id or a metric id) read with its VALUE test at the given
   parameters (missing ones take the catalog default). `unavailable`: a fixed reason that keeps the column greyed out.
   Never here: a value the page would derive itself (the reference's 52-week high/low price from last / (1 + %/100),
   its Return YTD from a count of weekdays: product decision 4). */
interface Candidate { id: string; group: string; label: string; short: string; entry: string; params?: ParamMap; period?: PerfPeriod; format?: ValueFormat; unavailable?: string }
/* Verdicts of the data audit (EXEC-SCREENER-V21 report s2_data.md 1e and 2): every column below is VERIFIED. Left out
   (REMOVE): Return YTD (a weekday count; product decision 4: only after a backend measure from the year's first
   trading session) and the 52-week high/low as a price (the reference derives it on the page from the distance;
   BLOCKED until the catalog publishes it). The 1M-1Y returns read their session counts from catalog.periods, the same
   counts as Stock vs IHSG; ROC is a close-to-close return over N of the stock's own sessions, so the labels say
   sessions. */
export const COLUMN_CANDIDATES: readonly Candidate[] = [
  { id:'ret_1w', group:'Returns', label:'Return, 5 sessions (1W)', short:'Return 1W', entry:'I17', params:{ length:5, source:'close' } },
  { id:'ret_1m', group:'Returns', label:'Return, 1M in sessions', short:'Return 1M', entry:'I17', period:'1M', params:{ source:'close' } },
  { id:'ret_3m', group:'Returns', label:'Return, 3M in sessions', short:'Return 3M', entry:'I17', period:'3M', params:{ source:'close' } },
  { id:'ret_6m', group:'Returns', label:'Return, 6M in sessions', short:'Return 6M', entry:'I17', period:'6M', params:{ source:'close' } },
  { id:'ret_1y', group:'Returns', label:'Return, 1Y in sessions', short:'Return 1Y', entry:'I17', period:'1Y', params:{ source:'close' } },
  { id:'hi52_pct', group:'Range', label:'Distance from the 252-session high (52W)', short:'vs 52W high', entry:'hi52' },
  { id:'lo52_pct', group:'Range', label:'Distance from the 252-session low (52W)', short:'vs 52W low', entry:'lo52' },
  { id:'vol_1d', group:'Liquidity', label:'Volume on the evaluation day (shares)', short:'Volume', entry:'I35', params:{ length:1 } },
  { id:'vol_20', group:'Liquidity', label:'Average volume, 20 sessions (shares)', short:'Avg vol 20D', entry:'I35', params:{ length:20 } },
  { id:'rvol', group:'Liquidity', label:'Relative volume (today ÷ 20-session average, today included)', short:'Rel volume', entry:'I37', format:'multiple' },
  { id:'natr', group:'Volatility', label:'ATR, % of close (14 sessions)', short:'ATR %', entry:'I31' },
  { id:'hv', group:'Volatility', label:'Historical volatility, 20 sessions, annualised', short:'Hist vol', entry:'I33' },
];
/** the generic group: every catalog indicator with a VALUE test, at its default settings */
const INDICATOR_GROUP = 'Indicator values';
/** the anchor: passes on every listed ticker (see the header); its id and the column ids are condition ids */
const ANCHOR: ConditionDef = { id:'xa', enabled:true, test:{ kind:'value', metric:{ kind:'universe', attr:'bars' }, op:'gt', value:0 } };
const STORE_KEY = 'scr.extraCols';

interface Spec { def: ExtraColumnDef; test: ValueTest | null; colKey: string }
let specMemo: { byKey: Map<string, Entry>; list: Spec[]; byId: Map<string, Spec> } | null = null;

const valueOpt = (e: Entry): Opt | undefined => {
  const ok = (o: Opt) => o.kind === 'value' && !o.disabled && (o.form === 'value' || o.form === 'metric');
  const def = e.opts.find(o => o.key === e.def.opt);
  return (def && ok(def) && def.op === 'gt' ? def : undefined) || e.opts.find(o => ok(o) && o.op === 'gt') || e.opts.find(ok);
};
function specOf(c: Candidate, anchorReason: string | null): Spec | null {
  const e = ctx.byKey.get(c.entry);
  if (!e) return null;                                       // not in this publication's catalog: not offered
  const n = c.period ? ctx.catalog?.periods?.[c.period] : undefined;
  const o = valueOpt(e), params: ParamMap = { ...defaultParams(e), ...(c.params || {}), ...(n ? { length:n } : {}) };
  const label = c.period ? c.label.replace(`${c.period} in sessions`, n ? `${n} sessions (${c.period})` : c.period) : c.label;
  let why = c.unavailable || anchorReason || (!e.available ? e.reason || 'Not available in this publication.' : null) || (!o ? 'This measure has no value to show.' : null);
  if (!why) for (const p of e.params) { const msg = paramError(p, params[p.key]); if (msg) { why = `${p.label || p.key}: ${msg}`; break } }
  let test: ValueTest | null = null;
  if (!why && o) {
    const card = newCard(e, [], { opt:o.key, value:0, params });
    test = toWire(e, card).test as ValueTest;
  }
  const paramText = e.params.map(p => `${p.label || p.key} ${optionText(p, params[p.key])}`).join(' · ');
  const def: ExtraColumnDef = { id:c.id, group:c.group, label, short:c.short, unit:o?.unit ?? null, format:c.format ?? formatOfOpt(e, o), params, paramText, unavailable:why };
  return { def, test, colKey:test ? canonical({ metric:test.metric, params }) : '' };
}
function specs(): { list: Spec[]; byId: Map<string, Spec> } {
  if (specMemo && specMemo.byKey === ctx.byKey) return specMemo;
  const lim = ctx.catalog?.limits.find(l => l.name === 'max_conditions')?.value;
  // the anchor's attribute is validated by the worker against its own metrics file; a catalog that lists it as not
  // available greys every column out (a catalog that does not list it, as the fixture's, leaves the worker to judge)
  const anchor = ctx.byKey.get('bars');
  const anchorReason = anchor && !anchor.available ? 'Not available: this publication cannot list values for every row.'
    : lim !== undefined && lim < 2 ? 'Not available: the screen allows too few conditions to add a column.' : null;
  const list: Spec[] = [];
  for (const c of COLUMN_CANDIDATES) { const s = specOf(c, anchorReason); if (s) list.push(s) }
  for (const e of ctx.byKey.values()) {
    if (e.kind !== 'indicator' || !e.available) continue;
    const o = valueOpt(e); if (!o || o.form !== 'value') continue;
    const outs = e.indicator?.outputs.filter(x => x.tests.some(t => t.form === 'value')) || [];
    const out = outs.length > 1 ? e.indicator!.outputs.find(x => x.key === o.output)?.label || o.output : '';
    // data audit 2.3: a value without a plain unit (Ease of Movement, Market Facilitation Index) is BLOCKED; a value
    // in the stock's own price, share or rupiah units carries the unit in its header (and the tooltip warns)
    const f = formatOfOpt(e, o); if (f === 'raw') continue;
    const unit = comparableAcrossStocks(f) ? '' : ({ price:'Rp', price_change:'Rp', volume:'shares', idr:'Rp' } as Record<string, string>)[f] || '';
    const name = out ? `${e.label} · ${out}` : e.label;
    const s = specOf({ id:'ind_' + e.key, group:INDICATOR_GROUP, label:unit ? `${name} (${unit})` : name, short:unit ? `${e.short} (${unit})` : e.short, entry:e.key }, anchorReason);
    if (s) list.push(s);
  }
  specMemo = { byKey:ctx.byKey, list, byId:new Map(list.map(s => [s.def.id, s])) };
  return specMemo;
}

/** Every column that can be added, in picker order (unavailable ones included, greyed with their reason). */
export function availableColumns(): ExtraColumnDef[] { return specs().list.map(s => s.def) }

/* ---- the chosen columns, per browser (scr.extraCols; storage.ts store wraps every access in try/catch) ---------- */
let chosen: string[] = (() => { const v = store.get<unknown>(STORE_KEY, []); return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, 50) : [] })();
/** The ids of the shown extra columns, in table order (a saved id the catalog does not offer, or offers greyed, is
    kept in the browser but not shown). */
export function shownColumns(): string[] {
  if (!ctx.catalog) return [];
  const by = specs().byId;
  return chosen.filter(id => by.get(id)?.test);
}
/** Show these columns in this order (add, remove, reorder); asks the worker for what is missing. */
export function setColumns(ids: string[]): void {
  chosen = [...new Set(ids.filter(x => typeof x === 'string'))].slice(0, 50);
  store.set(STORE_KEY, chosen);
  const t = tableOf(); if (t) errors.delete(t.key);           // a user action may ask a failed column again
  extraCancel();
  ui.renderResults();
  extraKick();
}

/* ---- the table the columns describe, and the cache ------------------------------------------------------------ */
type VersionsKey = Pick<Versions, (typeof VERSION_FIELDS)[number]>;
interface Table { key: string; versions: VersionsKey; universe: UniverseDef; tickers: string[]; dataVersion: string; rows: Set<string> }
const pickVersions = (v: Partial<Versions>): VersionsKey => Object.fromEntries(VERSION_FIELDS.map(k => [k, v[k] ?? null])) as VersionsKey;
const sameV = (a: Partial<Versions>, b: Partial<Versions>) => VERSION_FIELDS.every(k => (a[k] ?? null) === (b[k] ?? null));
/** the universe in one canonical form: defaults filled (an absent P4 flag means true), empty lists left out, lists sorted */
export function normalizedUniverse(u: UniverseDef): UniverseDef {
  const out: Record<string, unknown> = { ...UNIVERSE_DEFAULTS, ...u };
  for (const k of ['sectors_in', 'sectors_out', 'industries_in', 'industries_out', 'indices_in', 'indices_out', 'groups_in', 'groups_out', 'tickers'] as const) {
    const v = out[k] as string[] | null | undefined;
    if (Array.isArray(v) && v.length) out[k] = [...v].sort(); else if (k === 'tickers') out[k] = null; else delete out[k];
  }
  if (!(out.metric_filters as unknown[] | undefined)?.length) out.metric_filters = [];
  return out as unknown as UniverseDef;
}
/** The table the extra columns describe: ctx.R (never the pending edits), at the catalog's versions; null when there
    is no table yet, it carries no definition, or it is of another publication than the catalog (nothing is asked). */
/** The table the columns describe, kept per (result, catalog) object: every cell and every sort comparison asks for
    it, and its key serialises the whole ticker list (S4 D2: rebuilt per cell, it made adding a column a long task).
    A result or a catalog is never changed in place (run.ts and app.ts replace ctx.R and ctx.catalog). */
let tableMemo: { R: unknown; cat: unknown; t: Table | null } | null = null;
function tableOf(): Table | null {
  const R = ctx.R, cat = ctx.catalog;
  if (tableMemo && tableMemo.R === R && tableMemo.cat === cat) return tableMemo.t;
  const t = buildTable();
  tableMemo = { R, cat, t };
  return t;
}
function buildTable(): Table | null {
  const R = ctx.R, cat = ctx.catalog;
  if (!R || !R.def || !cat) return null;
  const v = R.run ? R.run.versions : cat.versions;
  if (!sameV(v, cat.versions)) return null;
  const tickers = [...new Set(R.rows.map(r => r.ticker))].sort();
  const universe = normalizedUniverse(R.def.universe), versions = pickVersions(v);
  return { key:canonical({ versions, universe, tickers }), versions, universe, tickers, dataVersion:v.price_data, rows:new Set(tickers) };
}
/** The cache key of a column's values (exported for the tests): the full versions, the canonical normalized universe
    of the table's definition, the ticker set, and the column's metric reference with its resolved parameters. */
export function cacheKeyOf(id: string): string | null {
  const t = tableOf(), s = specs().byId.get(id);
  return t && s?.test ? t.key + '#' + s.colKey : null;
}

interface ColAnswer { cells: Map<string, Cell>; params_resolved: ResolvedParams | null; unit: string | null; metric: string | null }
/** table key -> column key -> what the worker answered; at most KEEP tables (the oldest goes first) */
const cache = new Map<string, Map<string, ColAnswer>>();
/** table key -> ticker -> its row remarks as the auxiliary answer gave them (equal to the table row's at one version) */
const remarks = new Map<string, Map<string, RowRemark[]>>();
/** table key -> column key -> the message of the request that failed for it (no retry until a user action) */
const errors = new Map<string, Map<string, string>>();
/** table key -> the canonical versions it was asked at (prune) */
const published = new Map<string, string>();
const KEEP = 4;
const keep = <V>(m: Map<string, V>, k: string, make: () => V): V => {
  let v = m.get(k);
  if (!v) { v = make(); m.set(k, v); while (m.size > KEEP) m.delete(m.keys().next().value!) }
  return v;
};
/** drop what belongs to another publication than the catalog's (invalidation rule 1) */
function prune() {
  const cat = ctx.catalog; if (!cat) return;
  const now = canonical(pickVersions(cat.versions));
  for (const [k, v] of [...published]) if (v !== now) { published.delete(k); cache.delete(k); remarks.delete(k); errors.delete(k) }
}

/* ---- the auxiliary request ------------------------------------------------------------------------------------ */
interface Job { table: Table; ids: string[]; tickers: string[]; def: Definition }
let auxCtl: AbortController | null = null, inflight: Job | null = null;

/** what is still missing for the shown columns of this table, as the next request (null: nothing to ask) */
function nextJob(t: Table): Job | null {
  const by = specs().byId, have = cache.get(t.key), failed = errors.get(t.key);
  const missing = shownColumns().map(id => by.get(id)!).filter(s => s.test && !failed?.has(s.colKey))
    .filter(s => { const a = have?.get(s.colKey); return !a || t.tickers.some(tk => !a.cells.has(tk)) });
  // one column per metric reference (two ids may read the same value)
  const seen = new Set<string>(), cols = missing.filter(s => !seen.has(s.colKey) && !!seen.add(s.colKey));
  if (!cols.length || !t.tickers.length) return null;
  const lim = ctx.catalog?.limits || [], val = (n: string) => lim.find(l => l.name === n)?.value;
  const group = cols.slice(0, Math.max(1, (val('max_conditions') ?? 10) - 1));
  const need = t.tickers.filter(tk => group.some(s => !have?.get(s.colKey)?.cells.has(tk)));
  // rows of the answer: ~450 bytes each plus ~260 per cell; half the response limit, at most 400 tickers
  const maxResp = val('max_response_bytes'), maxReq = val('request_bytes');
  let size = maxResp ? Math.floor(maxResp * 0.5 / (450 + 260 * (group.length + 1))) : 300;
  if (maxReq) size = Math.min(size, Math.floor((maxReq * 0.5 - 4096) / 16));
  size = Math.max(25, Math.min(400, size));
  const tickers = need.slice(0, size);
  const def: Definition = {
    universe:{ ...t.universe, tickers },
    conditions:[ANCHOR, ...group.map((s, k) => ({ id:'x' + k.toString(36), enabled:true, test:s.test! }))],
    logic:'any',
  };
  return { table:t, ids:group.map(s => s.colKey), tickers, def };
}
/** the definition of the next auxiliary request for the current table (exported for the tests; nothing is sent) */
export function nextAuxDefinition(): Definition | null { const t = tableOf(); return t ? nextJob(t)?.def ?? null : null }

/** Ask the worker for what the shown columns miss, one request at a time, only while no main run is in flight. */
export function extraKick(): void {
  if (auxCtl || ctx.running) return;
  prune();
  const t = tableOf(); if (!t) return;
  const job = nextJob(t); if (!job) return;
  void runJob(job);
}
/** Cancel the auxiliary request in flight (a new main run, a publication change, a column change). */
export function extraCancel(): void { auxCtl?.abort(); auxCtl = null; inflight = null }

function fail(job: Job, message: string) {
  published.set(job.table.key, canonical(job.table.versions));
  const m = keep(errors, job.table.key, () => new Map<string, string>());
  for (const k of job.ids) m.set(k, message);
  // the rest still missing for this table would meet the same refusal (owner budget, limits): marked too, not sent
  const by = specs().byId, have = cache.get(job.table.key);
  for (const id of shownColumns()) { const s = by.get(id); if (s?.test && !m.has(s.colKey) && (!have?.get(s.colKey) || job.table.tickers.some(tk => !have.get(s.colKey)!.cells.has(tk)))) m.set(s.colKey, message) }
}
async function runJob(job: Job) {
  const c = new AbortController(); auxCtl = c; inflight = job;
  try {
    const { body } = await ctx.api.run({ schema_version:1, data_version:job.table.dataVersion, definition:job.def, options:{ exhaustive:false, explain:false } }, { signal:c.signal, lane:'aux' });
    if (auxCtl !== c) return;
    auxCtl = null; inflight = null;
    const cat = ctx.catalog;
    if (!cat || !sameV(body.versions, job.table.versions) || !sameV(body.versions, cat.versions)) {
      // another publication answered: dropped; the page asks the catalog again when price_data moved (app.ts
      // versionSeen), and a new table brings a new key
      fail(job, 'The data was updated while these values loaded; they load again with the refreshed table.');
      ui.versionSeen(body.versions);
      ui.renderResults();
      return;
    }
    published.set(job.table.key, canonical(job.table.versions));
    const cols = keep(cache, job.table.key, () => new Map<string, ColAnswer>());
    const rem = keep(remarks, job.table.key, () => new Map<string, RowRemark[]>());
    const rows = new Map(body.rows.map(r => [r.ticker, r]));
    job.ids.forEach((colKey, k) => {
      const id = 'x' + k.toString(36), sum = body.conditions.find(x => x.id === id);
      const a = cols.get(colKey) || { cells:new Map<string, Cell>(), params_resolved:null, unit:null, metric:null };
      a.params_resolved = sum?.params_resolved ?? a.params_resolved; a.unit = sum?.unit ?? a.unit; a.metric = sum?.metric ?? a.metric;
      for (const tk of job.tickers) {
        const r = rows.get(tk), cell = r?.cells.find(x => x.id === id);
        if (cell) a.cells.set(tk, cell);
      }
      cols.set(colKey, a);
    });
    for (const tk of job.tickers) { const r = rows.get(tk); if (r) rem.set(tk, r.remarks) }
    // a ticker the answer left out (it should not: the anchor passes on every listed ticker) is named, not guessed
    const lost = job.tickers.filter(tk => !rows.has(tk));
    if (lost.length) { const m = keep(errors, job.table.key, () => new Map<string, string>()); for (const k of job.ids) if (!m.has(k)) m.set(k, 'No value came back for some stocks of this table.') }
    ui.renderResults();
    extraKick();
  } catch (e) {
    if (isAbort(e) || auxCtl !== c) return;
    auxCtl = null; inflight = null;
    const f = e instanceof ApiFailure ? e : new ApiFailure(T.unreachable, 'NETWORK');
    fail(job, f.message || T.unreachable);
    // the table is older than the worker: the screen runs again, once per publication pair; a second refusal at the
    // same pair keeps the column's message, with nothing sent again (run.ts dataChanged, QA M3)
    if (f.code === 'DATA_VERSION_CHANGED' && !ui.dataChanged()) fail(job, T.dataBehind);
    ui.renderResults();
  }
}

/* ---- what the table shows ------------------------------------------------------------------------------------- */
/** The cell of an extra column for one row of the table. */
export function extraCell(ticker: string, id: string): ExtraCellState {
  const s = specs().byId.get(id), t = tableOf();
  if (!s?.test || !chosen.includes(id) || !t || !t.rows.has(ticker)) return { kind:'none' };
  const cell = cache.get(t.key)?.get(s.colKey)?.cells.get(ticker);
  if (cell) return { kind:'value', cell };
  const err = errors.get(t.key)?.get(s.colKey);
  if (err) return { kind:'error', message:err };
  return { kind:'loading' };
}
/** The sort key of an extra-column cell (numeric; null sorts last), the same rule as a condition's VALUE cell. */
export function extraSortKey(ticker: string, id: string): number | null {
  const x = extraCell(ticker, id);
  return x.kind === 'value' && x.cell.status !== 'na' && typeof x.cell.value === 'number' && Number.isFinite(x.cell.value) ? x.cell.value : null;
}
/** What the worker said about a column for the current table (header tooltip): the parameters it resolved, the unit,
    its metric name; null before the first answer. */
export function extraColumnInfo(id: string): { params_resolved: ResolvedParams | null; unit: string | null; metric: string | null } | null {
  const s = specs().byId.get(id), t = tableOf(); if (!s?.test || !t) return null;
  const a = cache.get(t.key)?.get(s.colKey);
  return a ? { params_resolved:a.params_resolved, unit:a.unit, metric:a.metric } : null;
}
/** The row remarks the auxiliary answer carried for a ticker (equal to the table row's at the same versions). */
export function extraRowRemarks(ticker: string): RowRemark[] | null { const t = tableOf(); return t ? remarks.get(t.key)?.get(ticker) ?? null : null }
/** Forget every value, error and request of the extra columns (the tests; a sign-out would too). */
export function extraReset(): void { extraCancel(); cache.clear(); remarks.clear(); errors.clear(); published.clear() }
/** Whether an auxiliary request is in flight (tests, the column picker's ring). */
export const extraBusy = () => !!inflight;
