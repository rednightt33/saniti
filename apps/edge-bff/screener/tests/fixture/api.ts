/* FIXTURE ONLY: a ScreenerApi on the prototype's synthetic market (data.ts), for the visual check and the Chromium
   smoke run (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12). The catalog is the worker's own view of the generated
   catalog (apps/screener-worker/src/catalog.ts catalogDoc, QA5 unit B item 4): the indicators (registry.ts
   catalogIndicators), every metric and fundamental of screener-metrics.json and the flow entries (core catalog.ts
   METRICS_CATALOG) with their availability on the fixture's publication (validate.ts availabilityMap: no
   cross-sectional file, the fixture's broker window), the operators, and the presets of presets.json with their
   availability (validate.ts presetAvailability) and counts; values and refusals are the core's (engine.ts). Only the
   limits[] are a copy of the worker's words (its catalog.ts imports Node modules). Saved items and the watchlist live
   in this browser's storage under scr.fixture.* (the production page keeps none of them there). `opts` adds latency,
   failures and a broker window still loading for the smoke run (ERRORS M253). Never part of the production bundle
   (tests/bundle). */
import { BROKERS } from './data.ts';
import type {
  Availability, CatalogMetric, CatalogOperators, CatalogPreset, CatalogResponse, Definition, ItemKind, LimitEntry, PutItemRequest, SavedItem, UniverseResponse, Versions,
} from '../../src/core/contract.ts';
import { ApiFailure, isAbort, type CallOpts, type Conditional, type ScreenerApi } from '../../src/api/types.ts';
import { errorText } from '../../src/texts.ts';
import { sha256Hex } from '../../../terminal/src/data/rack.ts';
import reg from '../../src/core/screener-registry.json' with { type: 'json' };
import { catalogIndicators } from '../../src/core/registry.ts';
import { isScreenerError } from '../../src/core/errors.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import type { MetricDefinition } from '../../src/core/catalog.ts';
import { availabilityMap, definitionHash, presetAvailability, presetDefinitions } from '../../src/core/validate.ts';
import { indicatorDepth, resolveFlowParams } from '../../src/core/flowmetrics.ts';
import type { FlowBindContext } from '../../src/core/flowmetrics.ts';
import { DAYS, IHSG, LISTINGS, T as TK } from './data.ts';
import { CAP_BUDGET_MS, LIMITS as L, groupingsOf, normalize, preview as pv, run as runDef, universeRow, type FixtureData, type Market, type Tk } from './engine.ts';
import { BROKER_SESSIONS, BROKER_WINDOW, FLOW_CTX } from './broker.ts';

/** the catalog's operators block as the worker sends it (screener-worker catalog.ts catalogOperators): each measure with
    its transform's arguments */
const OPERATORS: CatalogOperators = (() => { const o = METRICS_CATALOG.operators; return { types:o.types, default_measure:o.default_measure, tests:o.tests.map(t => ({ ...t })),
  measures:o.measures.map(x => ({ ...x, args:(METRICS_CATALOG.transforms.find(t => t.fn === x.fn)?.args ?? []).map(a => ({ ...a })) })) } as CatalogOperators })();

/* ---- the market ---------------------------------------------------------------------------------------------- */
const STALE = new Set(['LPPF', 'ELSA']), BREAK = new Map([['GOTO', 'STOCK_SPLIT'], ['BUKA', 'REVERSE_SPLIT']]), UNCLASSIFIED = new Set(['MTDL', 'ASSA']);
export function market(): Market {
  const evalDate = DAYS[DAYS.length - 1];
  const tickers: Tk[] = LISTINGS.map((L: any) => {
    const t = TK[L.tk], cut = STALE.has(L.tk) ? 3 : 0, n = DAYS.length - cut;
    const tk: Tk = { ticker:L.tk, name:L.name, sector:UNCLASSIFIED.has(L.tk) ? null : L.sector, industry:UNCLASSIFIED.has(L.tk) ? null : L.industry,
      d:DAYS.slice(0, n), o:t.o.slice(0, n), h:t.h.slice(0, n), l:t.l.slice(0, n), c:t.c.slice(0, n), v:t.v.slice(0, n), remarks:[], breakAt:null };
    if (cut) tk.remarks.push({ code:'STALE', last_bar_date:tk.d[n - 1] });
    if (BREAK.has(L.tk)) { const at = n - 40; tk.breakAt = at; tk.remarks.push({ code:'PRICE_BREAK', action:BREAK.get(L.tk)!, ex_date:tk.d[at], ratio_old:BREAK.get(L.tk) === 'STOCK_SPLIT' ? 1 : 10, ratio_new:BREAK.get(L.tk) === 'STOCK_SPLIT' ? 5 : 1, close_ratio:tk.c[at] / tk.c[at - 1] }) }
    return tk;
  });
  return { tickers, byTicker:new Map(tickers.map(t => [t.ticker, t])), days:DAYS, ihsg:IHSG, evalDate };
}

/* ---- the catalog ----------------------------------------------------------------------------------------------- */
const R = reg as any;
/** the worker's refusal as the page meets it on the wire (live.ts failure): the page's wording of its code, field and
    details, and the contract's error body */
const refuse = (e: unknown): never => {
  if (!isScreenerError(e)) throw e;
  throw new ApiFailure(errorText(e.code, { field:e.field, details:e.details as Record<string, unknown>, server:e.message }) || e.message, e.code, e.status, e.field, null,
    (e.details as Record<string, unknown>) ?? null, e.toApi().error);
};
const isFundamental = (x: MetricDefinition) => /fundamental/i.test(x.group);
/** A catalog entry as the worker writes it (screener-worker catalog.ts catalogMetric, without its flow part): the
    contract's fields and the additive ones the page reads (label, short, synonyms, default_test, ref, side). */
function catalogMetric(x: MetricDefinition, a: { availability: Availability; reason: string | null }): CatalogMetric {
  const extra: Record<string, unknown> = {};
  for (const k of ['label', 'short', 'synonyms', 'default_test', 'ref', 'side'] as const) if (x[k] !== undefined) extra[k] = x[k];
  return { id:x.id, group:x.group, kind:x.kind, params:x.params, tests:x.tests, unit:x.unit, formula:x.formula, interpretation:x.interpretation, misuse:x.misuse,
    availability:a.availability, reason:a.reason, applies_to:x.applies_to, ...extra } as CatalogMetric;
}
/** The flow entries as the worker writes them (catalogMetric's flow part: the core's flow entries, the Terminal's
    indicators and the Screener's own, each with its setup at the loaded broker window: the defaults the core resolves,
    the sessions it reads at them), on the fixture's complete window. EXEC-SCREENER-FLOW-CANDLES P5c. The worker builds
    them once per publication; the fixture once per browser (kept under fixture.flowCatalog with the entries they were
    built from): the depth probes leave megabytes of garbage, whose collection, run on every page load, landed in a
    later task of the page and failed the smoke run's long-task check. Their availability is set per publication
    (metricsOf). */
function buildFlowMetrics(): CatalogMetric[] {
  return METRICS_CATALOG.metrics.filter(x => x.flow).map(x => {
    const f = x.flow!, defaults = resolveFlowParams(f, undefined, 'catalog', BROKER_SESSIONS);
    let depth: number | null = null;
    if (!f.requires) try { depth = indicatorDepth(f, f.default_output, defaults) } catch { depth = null }
    const version = (f as { version?: string }).version;
    return { ...catalogMetric(x, { availability:'AVAILABLE', reason:null }),
      flow:{ family:f.family, place:f.place, tip:f.tip, unit:f.unit, outputs:f.outputs, default_output:f.default_output,
        params:f.params.map(p => p.key in defaults ? { ...p, default:defaults[p.key] } : p), adv_floor:f.adv_floor, needs_classification:f.needs_classification,
        ...(version ? { version } : {}), depth, sessions:BROKER_SESSIONS } } as CatalogMetric;
  });
}
const FLOW_METRICS: Map<string, CatalogMetric> = (() => {
  const KEY = 'fixture.flowCatalog', src = JSON.stringify([BROKER_SESSIONS, METRICS_CATALOG.metrics.filter(x => x.flow), METRICS_CATALOG.operators]);
  let out: CatalogMetric[] | null = null;
  try { const kept = JSON.parse(globalThis.localStorage?.getItem(KEY) || 'null'); if (kept?.src === src) out = kept.out as CatalogMetric[] } catch { /* no storage: built here */ }
  if (!out) {
    out = buildFlowMetrics();
    try { globalThis.localStorage?.setItem(KEY, JSON.stringify({ src, out })) } catch { /* storage full or off */ }
  }
  return new Map(out.map(m => [m.id, m]));
})();
type AvailabilityMap = ReturnType<typeof availabilityMap>;
/** metrics[] and fundamentals[] of GET catalog (screener-worker catalog.ts catalogDoc): every entry of the catalog in its
    order, with its availability on this publication */
function metricsOf(a: AvailabilityMap): { metrics: CatalogMetric[]; fundamentals: CatalogMetric[] } {
  const metrics: CatalogMetric[] = [], fundamentals: CatalogMetric[] = [];
  for (const x of METRICS_CATALOG.metrics) {
    const av = a.get(x.id) ?? { availability:'REQUIRES_DATA' as const, reason:'Not evaluated.' };
    const m = x.flow ? { ...FLOW_METRICS.get(x.id)!, availability:av.availability, reason:av.reason } : catalogMetric(x, av);
    (isFundamental(x) ? fundamentals : metrics).push(m);
  }
  return { metrics, fundamentals };
}
/** The presets of presets.json as the worker answers them (screener-worker server.ts presets): each with its
    availability (validate.ts presetAvailability: available only when every leg is) and, when available, its match and
    near counts on this publication (computed once per fixture data, which never changes; null when the run fails, as
    the worker's). */
const COUNTS = new Map<string, { match_count: number | null; near_count: number | null }>();
function presetsOf(a: AvailabilityMap, count: (d: Definition) => { match_count: number; near_count: number }): CatalogPreset[] {
  return presetDefinitions().map(p => {
    const base = { id:p.id, category:p.category, name:p.name, why:p.why, definition:p.definition, ...(p.view ? { view:p.view } : {}) };
    const av = presetAvailability(p, a, METRICS_CATALOG);
    if (av.availability !== 'AVAILABLE') return { ...base, availability:av.availability, reason:av.reason, match_count:null, near_count:null, unavailable_legs:av.unavailable_legs };
    let c = COUNTS.get(p.id);
    if (!c) { try { const r = count(p.definition); c = { match_count:r.match_count, near_count:r.near_count } } catch { c = { match_count:null, near_count:null } } COUNTS.set(p.id, c) }
    return { ...base, availability:'AVAILABLE' as const, reason:null, ...c, unavailable_legs:[] };
  });
}

/* ---- limits[]: the worker's words at its values (screener-worker catalog.ts limitEntries, brokerDepthLimit) -------- */
const limit = (name: string, value: number, unit: string, rule: string, ok: string, refused: string): LimitEntry => ({ name, value, unit, rule, example_ok:ok, example_refused:refused });
/** K1 at the loaded window (screener-worker catalog.ts brokerDepthLimit, the same words) */
function brokerDepthLimit(sessions: number): LimitEntry {
  const own = Math.min(10, Math.max(1, sessions - 1)), n = Math.max(1, sessions - own);
  return limit('broker_depth', sessions, 'sessions', `a flow condition reads at most the ${sessions} sessions of broker data the Screener holds: the indicator's own window plus the operator's N, length or within`,
    `Bandar Balance · % over ${own} sessions with a percentile over ${n} sessions (${own + n} in all)`, `the same with a percentile over ${n + 5} sessions (${own + n + 5} in all; use a shorter window or N)`);
}
const limitsAt = (sessions: number): LimitEntry[] => [
  limit('max_conditions', L.max_conditions, 'conditions', `at most ${L.max_conditions} enabled conditions in one screen`, `a screen with ${L.max_conditions} enabled conditions`, `a screen with ${L.max_conditions + 1} enabled conditions (switch one off or remove it)`),
  limit('max_metric_filters', L.max_metric_filters, 'filters', `at most ${L.max_metric_filters} universe metric filters in one screen`, `${L.max_metric_filters} metric filters`, `${L.max_metric_filters + 1} metric filters (remove one)`),
  limit('within_max', L.within_max, 'sessions', `"within" is a whole number of sessions from 1 to ${L.within_max}`, `within ${L.within_max} sessions`, `within ${L.within_max + 1} sessions (use ${L.within_max} or fewer)`),
  limit('max_counts', 50, 'saved screens', 'counts for at most 50 saved screens per request', '50 saved screens', '51 saved screens (ask for the rest in a second request)'),
  brokerDepthLimit(sessions)];

export interface FixtureOpts {
  /** extra milliseconds per call (smoke: late answers, ERRORS M253) */
  delay?: Partial<Record<'session' | 'catalog' | 'universe' | 'run' | 'preview' | 'items' | 'watchlist', number>>;
  /** fail a call: code and how many times (then it answers) */
  fail?: Partial<Record<'catalog' | 'run' | 'preview', { code: string; status: number; times: number; retryAfter?: number; field?: string }>>;
  /** a second publication after N runs (smoke: an answer newer than the catalog) */
  newPublicationAfterRuns?: number;
  /** the publication the page load starts at (smoke: a cached paint followed by a newer publication, 6c.9 item 2) */
  publication?: number;
  /** markup in the names (smoke: no element is made from them, report 9.1 text rendering): a company name and a sector,
      and (EXEC-SCREENER-V21) a catalog label (RSI's indicator name and description), a preset's name and why, and the
      message of every injected failure (a server message) */
  hostile?: boolean;
  /** the broker data still loading, with this many sessions loaded so far (P5_FLOW.md section 1 Availability): every
      flow entry and every preset with a flow leg is unavailable, and a screen with a flow condition is refused
      METRIC_UNAVAILABLE with reason code FLOW_UNAVAILABLE on its card, as the worker does */
  brokerLoading?: number;
}

export function fixtureApi(opts: FixtureOpts = {}): ScreenerApi & { market: Market; counters: Record<string, number>; busy: [number, number][] } {
  const m = market();
  if (opts.hostile) { const t = m.byTicker.get('BBCA')!; t.name = '<img src=x onerror="window.__xss=1">Bank "Central" Asia'; t.sector = '<b id="xss">Financials</b>' }
  let pub = opts.publication ?? 1;
  // the broker window the publication holds: complete, or still loading (opts.brokerLoading sessions so far)
  const window = opts.brokerLoading != null ? { ...BROKER_WINDOW, sessions:opts.brokerLoading, complete:false } : { ...BROKER_WINDOW };
  const flow: FlowBindContext = { ...FLOW_CTX, ...window };
  const fx: FixtureData = { flow, groupings:groupingsOf(m) };
  const avail = availabilityMap({}, METRICS_CATALOG, undefined, flow);
  const versions = (): Versions => ({ screener_engine:'0a1b2c3d4e5f6071', registry:R.registry_version, screener_registry:R.screener_registry_version, price_data:'fixture-' + String(pub).padStart(58, '0'), flow_data:'fixture-flow-' + '0'.repeat(51) });
  // the broker data ends a session before the prices (broker.ts): a flow value carries its own date (P10 a)
  const data = () => ({ evaluation_date:m.evalDate, price_through:m.evalDate, flow_through:BROKER_WINDOW.last, broker_behind_sessions:1, broker_window:{ ...window },
    published_at:pub === 1 ? `${m.evalDate}T12:03:23Z` : `${m.evalDate}T23:59:00Z` });
  const periods = METRICS_CATALOG.periods as Record<string, number>;
  /** the worker's normalize, its refusal as the wire carries it */
  const norm = (def: unknown): Definition => { try { return normalize(m, fx, def) } catch (e) { return refuse(e) } };
  /** the core's computation; an error that is no refusal is the worker's unexpected error, which edge-bff answers 503
      SERVICE_UNAVAILABLE (main.py unexpected), so the page meets it as it would there */
  const compute = <T>(f: () => T): T => {
    try { return f() } catch (e) {
      if (isScreenerError(e)) return refuse(e);
      throw new ApiFailure(errorText('SERVICE_UNAVAILABLE'), 'SERVICE_UNAVAILABLE', 503);
    }
  };
  const catalog = (): CatalogResponse => {
    const v = versions(), d = data(), { metrics, fundamentals } = metricsOf(avail);
    const presets = presetsOf(avail, def => runDef(m, fx, normalize(m, fx, def), v, d));
    let indicators = catalogIndicators({ capBudgetMs:CAP_BUDGET_MS });
    if (opts.hostile) {                            // copies: the shared catalog objects stay as they are
      indicators = indicators.map(x => x.id === 'I13' ? { ...x, name:'<b id="xss2">Relative</b> Strength <img src=x onerror="window.__xss=2"> Index', description:'<script>window.__xss=3</script>gains & losses' } : x);
      for (let i = 0; i < presets.length; i++) if (presets[i].id === 'golden') presets[i] = { ...presets[i], name:'<img src=x onerror="window.__xss=4">Golden "Cross"', why:'<u id="xss3">why</u> it matters' };
    }
    return { versions:v, data:{ ...d, refresh:'ready', brokers:BROKERS.map(([code, name, f]: [string, string, number]) => ({ code, name, type:f ? 'Foreign' : 'Domestic' })) }, limits:limitsAt(window.sessions), indicators, metrics, fundamentals, periods:periods as CatalogResponse['periods'],
      groupings:fx.groupings as CatalogResponse['groupings'], presets, operators:OPERATORS };
  };
  const counters: Record<string, number> = {};
  /** the fixture's own main-thread compute ([start, end] in performance.now() ms): the worker's work in production,
      left out of the smoke run's long-task check of the page */
  const busy: [number, number][] = [];
  const timed = <T>(f: () => T): T => { const t0 = performance.now(); try { return f() } finally { busy.push([t0, performance.now()]) } };
  /** answer in a later task, as a network answer arrives: the page's own work on it is then a task of its own */
  const later = () => new Promise<void>(ok => setTimeout(ok, 0));
  const count = (k: string) => { counters[k] = (counters[k] || 0) + 1 };
  const wait = (k: keyof NonNullable<FixtureOpts['delay']>, signal?: AbortSignal) => new Promise<void>((ok, no) => {
    const ms = opts.delay?.[k] ?? 0;
    const t = setTimeout(ok, ms);                 // a later task even without a delay, as a network answer arrives
    signal?.addEventListener('abort', () => { clearTimeout(t); no(new DOMException('aborted', 'AbortError')) });
  });
  const failing = (k: 'catalog' | 'run' | 'preview') => {
    const f = opts.fail?.[k]; if (!f || f.times <= 0) return;
    f.times--;
    const msg = opts.hostile ? '<img src=x onerror="window.__xss=5">The <b id="xss4">server</b> said no.' : errorText(f.code, { field:f.field, retryAfter:f.retryAfter ?? null }) || `fixture failure ${f.code}`;
    throw new ApiFailure(msg, f.code, f.status, f.field, f.retryAfter ?? null);
  };
  const enc = (x: unknown) => new TextEncoder().encode(JSON.stringify(x));
  async function conditional<T>(k: string, body: T, inm?: string | null): Promise<Conditional<T>> {
    const bytes = enc(body), etag = await sha256Hex(bytes);
    if (inm && inm === etag) { count(k + '304'); return { status:304, etag } }
    return { status:200, etag, body:JSON.parse(new TextDecoder().decode(bytes)), bytes };
  }
  const KEY = (k: string) => 'scr.fixture.' + k;
  const load = <T>(k: string, d: T): T => { try { return JSON.parse(localStorage.getItem(KEY(k)) || 'null') ?? d } catch { return d } };
  const save = (k: string, v: unknown) => { try { localStorage.setItem(KEY(k), JSON.stringify(v)) } catch { /* storage off */ } };
  const hash = async (x: unknown) => sha256Hex(enc(x));
  let runs = 0;
  return {
    kind:'fixture', market:m, counters, busy,
    async session() { count('session'); await wait('session'); return { login:'fixture', csrf:'fixture-csrf' } },
    async catalog(inm) { count('catalog'); await wait('catalog'); failing('catalog'); const c = timed(catalog); await later(); return conditional('catalog', c, inm) },
    async universe(inm) { count('universe'); await wait('universe'); return conditional<UniverseResponse>('universe', { versions:versions(), data:data(), rows:m.tickers.map(t => universeRow(m, t)) }, inm) },
    async run(req, o: CallOpts = {}) {
      count(o.lane === 'aux' ? 'aux' : 'run'); await wait('run', o.signal);      // the extra columns' lane counted apart
      if (o.signal?.aborted) throw new DOMException('aborted', 'AbortError');
      failing('run');
      const def = timed(() => norm(req.definition));
      runs++; if (opts.newPublicationAfterRuns && runs > opts.newPublicationAfterRuns) pub = 2;
      const v = { ...versions(), definition_hash:await definitionHash(def) }, body = timed(() => compute(() => runDef(m, fx, def, v, data(), req.options)));
      const bytes = enc(body); await later();
      return { body:JSON.parse(new TextDecoder().decode(bytes)), bytes };
    },
    async preview(req, o: CallOpts = {}) {
      count('preview'); await wait('preview', o.signal); if (o.signal?.aborted) throw new DOMException('aborted', 'AbortError');
      failing('preview');
      const def = timed(() => norm(req.definition));
      if (req.data_version !== versions().price_data) throw new ApiFailure('New data was published; the screen is re-run.', 'DATA_VERSION_CHANGED', 409);
      const a = timed(() => compute(() => pv(m, fx, def, req.ticker, versions(), data(), periods))); await later(); return a;
    },
    async validate(definition) { const normalized = norm(definition); return { valid:true, definition_hash:await definitionHash(normalized), normalized } },
    async counts(req) {
      count('counts');
      const v = versions(), d = data();
      const counts = timed(() => req.definitions.map(x => {
        try { const r = runDef(m, fx, normalize(m, fx, x.definition), v, d); return { item_id:x.item_id, match_count:r.match_count, near_count:r.near_count } }
        // a refusal, or the worker's unexpected error of one saved screen (its counts entry, the error in its log)
        catch (e) { return { item_id:x.item_id, error:isScreenerError(e) ? e.toApi().error : { code:'INTERNAL_ERROR' as const, message:'The screener could not count this screen.' } } }
      }));
      await later(); return { versions:v, data:d, counts };
    },
    async items(kind: ItemKind) { count('items'); await wait('items'); return { items:load<SavedItem[]>('items', []).filter(i => i.kind === kind) } },
    async putItem(id: string, req: PutItemRequest) {
      const all = load<SavedItem[]>('items', []), old = all.find(i => i.item_id === id);
      if (old && req.revision !== old.revision) throw new ApiFailure('This screen was changed elsewhere since you opened it. Reload it, or save as a copy.', 'REVISION_CONFLICT', 409);
      if (all.some(i => i.item_id !== id && i.kind === req.kind && i.name === req.name)) throw new ApiFailure('A saved item with this name exists. Pick another name.', 'NAME_TAKEN', 409);
      const now = new Date().toISOString(), v = versions();
      const it: SavedItem = { item_id:id, kind:req.kind, name:req.name, definition:req.definition, schema_version:1, registry_version:v.registry, screener_registry_version:v.screener_registry,
        definition_hash:await hash(req.definition), revision:(old?.revision ?? 0) + 1, created_at:old?.created_at ?? now, updated_at:now, needs_review:[] };
      save('items', [...all.filter(i => i.item_id !== id), it]);
      return it;
    },
    async deleteItem(id: string) {
      const all = load<SavedItem[]>('items', []);
      if (!all.some(i => i.item_id === id)) throw new ApiFailure('This saved item no longer exists; reload the list.', 'NOT_FOUND', 404);
      save('items', all.filter(i => i.item_id !== id));
    },
    async watchlist() { count('watchlist'); await wait('watchlist'); return { tickers:load<string[]>('watch', []).map(t => ({ ticker:t, added_at:'2026-10-23T00:00:00Z' })) } },
    async watch(ticker: string, on: boolean) { const w = new Set(load<string[]>('watch', [])); on ? w.add(ticker) : w.delete(ticker); save('watch', [...w]) },
  };
}
export { isAbort };
