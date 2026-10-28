/* FIXTURE ONLY: a ScreenerApi on the prototype's synthetic market (data.ts), for the visual check and the Chromium
   smoke run (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12). The catalog's indicators are the worker's own view of
   the generated screener registry (src/core/registry.ts catalogIndicators); metrics, fundamentals and presets are a
   small hand-kept set in the contract's shape; values are computed by engine.ts. Saved items and the watchlist live in
   this browser's storage under scr.fixture.* (the production page keeps none of them there). `opts` adds latency and
   failures for the late-data smoke run (ERRORS M253). Never part of the production bundle (tests/bundle). */
import type {
  CatalogMetric, CatalogPreset, CatalogResponse, Definition, ItemKind, LimitEntry, PutItemRequest, SavedItem, UniverseResponse, Versions,
} from '../../src/core/contract.ts';
import { ApiFailure, isAbort, type CallOpts, type Conditional, type ScreenerApi } from '../../src/api/types.ts';
import { errorText } from '../../src/texts.ts';
import { sha256Hex } from '../../../terminal/src/data/rack.ts';
import reg from '../../src/core/screener-registry.json' with { type: 'json' };
import { catalogIndicators, resolveScreenerParams, screenerIndicator } from '../../src/core/registry.ts';
import { isScreenerError } from '../../src/core/errors.ts';
import { DAYS, IHSG, LISTINGS, T as TK } from './data.ts';
import { preview as pv, run as runDef, universeRow, type Market, type Tk } from './engine.ts';

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
/** the indicators[] of GET /catalog as the worker builds them (registry.ts catalogIndicators: the start values and
    default_offered of P17 a, the derived caps), at the budget the core tests use (SCREENER_CAP_BUDGET_MS has no default) */
const CAP_BUDGET_MS = 2000;
/** the worker's parameter refusals (registry.ts resolveScreenerParams: ranges, whole numbers, caps, options the
    screener does not offer, P17 a), so the page meets them in the fixture as it would on the wire; the rest of the
    worker's validation is not mirrored here */
function checkParams(definition: Definition) {
  const walk = (x: any, path: string) => {
    if (!x || typeof x !== 'object') return;
    if (Array.isArray(x)) { x.forEach((y, i) => walk(y, `${path}[${i}]`)); return }
    if (x.kind === 'indicator' && typeof x.indicator === 'string') {
      try { resolveScreenerParams(screenerIndicator(x.indicator, `${path}.indicator`), x.params ?? {}, `${path}.params`, { capBudgetMs:CAP_BUDGET_MS }) }
      catch (e) {
        if (!isScreenerError(e)) throw e;
        throw new ApiFailure(errorText(e.code, { field:e.field, details:e.details as Record<string, unknown>, server:e.message }) || e.message, e.code, e.status, e.field, null, (e.details as Record<string, unknown>) ?? null);
      }
    }
    for (const [k, v] of Object.entries(x)) walk(v, `${path}.${k}`);
  };
  walk(definition, 'definition');
}
const P = (key: string, label: string, def: number, min = 1, max?: number) => ({ key, type:'integer' as const, label, default:def, min, ...(max ? { max } : {}), exclusive_min:false, integer:true, step:1 });
const metric = (id: string, group: string, kind: CatalogMetric['kind'], label: string, unit: string | null, tests: CatalogMetric['tests'], extra: Record<string, unknown> = {}): CatalogMetric & Record<string, unknown> => ({
  id, group, kind, params:[], tests, unit, formula:'', interpretation:label, misuse:'', availability:'AVAILABLE', reason:null, applies_to:null, label, ...extra });
const FLOW_REASON = 'Flow arrives with Phase 2 (all boards, P8).', BANDAR_REASON = 'Bandar definitions wait for P9 (Phase 3).';
const FUND_REASON = 'No data: fundamentals wait for a data source and its own decision (P11).';
export const METRICS: (CatalogMetric & Record<string, unknown>)[] = [
  metric('hi52', 'Technical', 'transform', 'Distance from 52W high', '%', ['value'], { short:'52W high', interpretation:'(Close ÷ 52-week high − 1), 252 sessions (P23 a).', default_test:{ op:'gt', value:-10, value2:0 },
    ref:{ kind:'transform', fn:'pct_distance', of:{ kind:'transform', fn:'rolling_max', of:{ kind:'price', field:'high' }, args:{ length:252 } } } }),
  metric('lo52', 'Technical', 'transform', 'Distance from 52W low', '%', ['value'], { short:'52W low', interpretation:'(Close ÷ 52-week low − 1), 252 sessions (P23 a).', default_test:{ op:'gt', value:30, value2:100 },
    ref:{ kind:'transform', fn:'pct_distance', of:{ kind:'transform', fn:'rolling_min', of:{ kind:'price', field:'low' }, args:{ length:252 } } } }),
  { ...metric('rs', 'Technical', 'transform', 'Relative strength vs IHSG', 'pts', ['value'], { short:'RS', interpretation:'Stock return minus IHSG return over N sessions (points).', default_test:{ op:'gt', value:0, value2:20 },
    ref:{ kind:'transform', fn:'vs_index', of:{ kind:'price', field:'close' }, args:{ window:63 } } }), params:[P('window', 'Sessions', 63)] },
  { ...metric('return_rank', 'Technical', 'xsection', 'RS rank (percentile)', 'rank', ['value'], { short:'RS rank', interpretation:'Percentile of the N-session return on the fixed population (P7; 99 = strongest).', default_test:{ op:'gt', value:70, value2:100 } }), params:[P('window', 'Sessions', 252)] },
  { ...metric('breakout', 'Technical', 'pattern', 'Breakout', null, ['event'], { interpretation:'Close above the prior N-session high.', default_test:{ test:'event', within:3 } }), params:[P('length', 'Sessions', 20)] },
  { ...metric('volspike', 'Technical', 'pattern', 'Volume spike', null, ['state'], { interpretation:'Volume above 2× the average of the previous N sessions.' }), params:[P('length', 'Average of', 20)] },
  metric('adv20_idr', 'Flow', 'universe', 'Average daily value', 'IDR', ['value'], { short:'ADV20', interpretation:'Mean traded value (close × volume) over 20 sessions.', default_test:{ op:'gt', value:10, value2:100 } }),
  ...([['fnet', 'Foreign net flow'], ['fstreak', 'Foreign net-buy streak'], ['broker', 'Broker net buy'], ['topacc', 'Top-N broker net'], ['freq', 'Frequency spike']] as const)
    .map(([id, l]) => ({ ...metric(id, 'Flow', 'flow', l, 'IDR', ['value']), availability:'REQUIRES_DATA' as const, reason:FLOW_REASON })),
  { ...metric('bandar', 'Flow', 'flow', 'Bandar status', '%', ['state']), availability:'REQUIRES_DECISION' as const, reason:BANDAR_REASON },
];
const FUND = [['cap', 'Market cap'], ['pe', 'P/E'], ['pb', 'P/B'], ['peg', 'PEG'], ['evEbitda', 'EV/EBITDA'], ['divYield', 'Dividend yield'], ['payout', 'Payout ratio'], ['divYears', 'Years of dividends'],
  ['roe', 'ROE'], ['roa', 'ROA'], ['roic', 'ROIC'], ['netMargin', 'Net margin'], ['grossMargin', 'Gross margin'], ['revG', 'Revenue growth YoY'], ['epsG', 'EPS growth YoY'], ['epsGq', 'EPS growth, latest quarter YoY'],
  ['epsG3y', 'EPS CAGR 3Y'], ['der', 'Debt / equity'], ['curr', 'Current ratio'], ['intCov', 'Interest coverage'], ['fcfYield', 'FCF yield'], ['piotroski', 'Piotroski F-score (0–9)'], ['altman', 'Altman Z-score'],
  ['grahamRatio', 'Price ÷ Graham number'], ['magicRank', 'Magic Formula rank'], ['freeFloat', 'Free float'], ['foreignOwn', 'Foreign ownership'], ['nim', 'NIM (banks)'], ['npl', 'Gross NPL (banks)'], ['car', 'CAR (banks)'], ['casa', 'CASA (banks)'], ['ldr', 'LDR (banks)']];
export const FUNDAMENTALS: CatalogMetric[] = FUND.map(([id, l]) => ({ ...metric(id, 'Fundamental', 'universe', l, null, ['value']), availability:'REQUIRES_DATA', reason:id === 'divYield' ? 'No data yet: dividends come with Phase 2, after validation.' : FUND_REASON }));

const I = (indicator: string, output: string, params?: Record<string, number | string>) => ({ kind:'indicator' as const, indicator, output, ...(params ? { params } : {}) });
const close = { kind:'price' as const, field:'close' as const };
const U = { security_types:['stock'] as ['stock'], price_min:50, adv20_min_idr:1e9, traded_on_eval_date:true, exclude_price_breaks:true };
const pre = (id: string, category: string, name: string, why: string, conditions: Definition['conditions'], unavailable: string[] = [], universe: Partial<Definition['universe']> = {}): CatalogPreset => ({
  id, category, name, why, definition:{ universe:{ ...U, ...universe }, conditions, logic:'all' }, availability:unavailable.length ? 'REQUIRES_DATA' : 'AVAILABLE',
  reason:unavailable.length ? 'Needs data that is not loaded yet.' : null, match_count:null, near_count:null, unavailable_legs:unavailable });
const flowLeg = (id: string, label: string, metricId: string, window: number) => ({ id, enabled:true, label, test:{ kind:'value' as const, op:'gt' as const, value:0, metric:{ kind:'flow' as const, metric:metricId, params:{ window } } } });
const fundLeg = (id: string, label: string, attr: string, op: 'gt' | 'lt', value: number) => ({ id, enabled:true, label, test:{ kind:'value' as const, op, value, metric:{ kind:'universe' as const, attr } } });
export const PRESETS: CatalogPreset[] = [
  pre('bigacc', 'Bandarmology', 'Big Accumulation', 'Top-3 brokers absorbing ≥ 10% of 10-session value while price holds above MA20.', [flowLeg('a', 'Bandar status', 'bandar', 10), { id:'b', enabled:true, test:{ kind:'state', lhs:close, op:'gt', rhs:I('I01', 'sma') } }], ['a']),
  pre('fstreak', 'Bandarmology', 'Foreign Accumulation Streak', 'Foreign investors net buying 5+ sessions in a row and positive over 20 sessions.', [flowLeg('a', 'Foreign net-buy streak', 'fstreak', 1), flowLeg('b', 'Foreign net flow', 'fnet', 20)], ['a', 'b']),
  pre('minervini', 'Technical', 'Minervini Trend Template', 'Price > MA50 > MA150 > MA200, ≥ 30% above 52W low, within 25% of 52W high, RS rank ≥ 70.', [
    { id:'a', enabled:true, test:{ kind:'state', lhs:close, op:'gt', rhs:I('I01', 'sma', { length:150 }) } },
    { id:'b', enabled:true, test:{ kind:'state', lhs:close, op:'gt', rhs:I('I01', 'sma', { length:200 }) } },
    { id:'c', enabled:true, test:{ kind:'state', lhs:I('I01', 'sma', { length:50 }), op:'gt', rhs:I('I01', 'sma', { length:150 }) } },
    { id:'d', enabled:true, test:{ kind:'value', op:'gt', value:30, metric:(METRICS[1] as any).ref } },
    { id:'e', enabled:true, test:{ kind:'value', op:'gt', value:-25, metric:(METRICS[0] as any).ref } },
    { id:'f', enabled:true, test:{ kind:'value', op:'gt', value:70, metric:{ kind:'xsection', metric:'return_rank', params:{ window:252 } } } }], [], { adv20_min_idr:5e9 }),
  pre('oversold', 'Technical', 'Oversold in Uptrend', 'Long-term uptrend (above MA200) with RSI(14) below 40 — a pullback, not a breakdown.', [
    { id:'a', enabled:true, test:{ kind:'state', lhs:close, op:'gt', rhs:I('I01', 'sma', { length:200 }) } },
    { id:'b', enabled:true, test:{ kind:'value', op:'lt', value:40, metric:I('I13', 'rsi') } }]),
  pre('golden', 'Technical', 'Golden Cross', 'MA50 crossed above MA200 within the last 20 sessions.', [
    { id:'a', enabled:true, test:{ kind:'event', within:20, signal:{ lhs:I('I01', 'sma', { length:50 }), op:'crosses_above', rhs:I('I01', 'sma', { length:200 }) } } }]),
  pre('macdx', 'Technical', 'MACD Signal Cross', 'MACD crossed above its signal line in the last 5 sessions.', [
    { id:'a', enabled:true, test:{ kind:'event', within:5, signal:{ lhs:I('I06', 'macd'), op:'crosses_above', rhs:I('I06', 'signal') } } }]),
  pre('stflip', 'Technical', 'Supertrend Flip', 'Supertrend (10, 3) turned bullish in the last 5 sessions with ADX ≥ 20.', [
    { id:'a', enabled:true, test:{ kind:'event', within:5, signal:{ lhs:I('I09', 'direction'), op:'crosses_above', rhs:{ value:0 } } } },
    { id:'b', enabled:true, test:{ kind:'value', op:'gt', value:20, metric:I('I07', 'adx') } }]),
  pre('brk20', 'Technical', 'Breakout + Volume', 'Close above the prior 20-session high in the last 3 sessions on a volume spike.', [
    { id:'a', enabled:true, test:{ kind:'event', within:3, signal:{ pattern:{ kind:'pattern', type:'breakout', params:{ length:20 } } } } },
    { id:'b', enabled:true, test:{ kind:'state', pattern:{ kind:'pattern', type:'volspike', params:{ length:20 } } } }]),
  pre('ichi', 'Technical', 'Ichimoku Bullish', 'Close above the cloud and a Tenkan/Kijun bullish cross (needs a registry release, P6).', [
    { id:'a', enabled:true, label:'Ichimoku cloud', test:{ kind:'state', pattern:{ kind:'pattern', type:'ichimoku_above' } } }], ['a']),
  pre('graham', 'Fundamental', 'Graham Defensive', 'P/E < 15, P/B < 1.5 (P/E × P/B < 22.5), D/E < 1, 5+ years of dividends, positive 3Y EPS growth.', [fundLeg('a', 'P/E', 'pe', 'lt', 15), fundLeg('b', 'Price ÷ Graham number', 'grahamRatio', 'lt', 1), fundLeg('c', 'Debt / equity', 'der', 'lt', 1)], ['a', 'b', 'c']),
  pre('piotroski', 'Fundamental', 'Piotroski F-score ≥ 7', 'Financially improving companies (score 7–9) that are not expensive (P/B < 3).', [fundLeg('a', 'Piotroski', 'piotroski', 'gt', 6), fundLeg('b', 'P/B', 'pb', 'lt', 3)], ['a', 'b']),
  pre('qflow', 'Combined', 'Quality + Foreign Inflow', 'ROE > 15%, D/E < 1, foreign net buying over 20 sessions, price above MA50.', [fundLeg('a', 'ROE', 'roe', 'gt', 15), fundLeg('b', 'Debt / equity', 'der', 'lt', 1), flowLeg('c', 'Foreign net flow', 'fnet', 20), { id:'d', enabled:true, test:{ kind:'state', lhs:close, op:'gt', rhs:I('I01', 'sma', { length:50 }) } }], ['a', 'b', 'c']),
];
const limit = (name: string, value: number, unit: string, rule: string, ok: string, refused: string): LimitEntry => ({ name, value, unit, rule, example_ok:ok, example_refused:refused });
const LIMITS = [limit('max_conditions', 20, 'conditions', 'At most 20 enabled conditions', 'a screen with 20 enabled conditions', 'a screen with 21 enabled conditions'),
  limit('max_metric_filters', 8, 'filters', 'At most 8 universe metric filters', '8 metric filters', '9 metric filters'),
  limit('within_max', 130, 'sessions', '"within" is 1 to 130 sessions', 'within 130 sessions', 'within 131 sessions'),
  limit('max_counts', 50, 'definitions', 'Counts for at most 50 saved screens at once', '50 saved screens', '51 saved screens')];

const grouping = (key: 'sector' | 'industry', rows: Tk[]) => {
  const m = new Map<string, number>(); let un = 0;
  for (const t of rows) { const v = t[key]; if (v == null) un++; else m.set(v, (m.get(v) || 0) + 1) }
  return { key, values:[...m].sort((a, b) => a[0].localeCompare(b[0])).map(([value, tickers]) => ({ value, tickers })), unclassified:un };
};

export interface FixtureOpts {
  /** extra milliseconds per call (smoke: late answers, ERRORS M253) */
  delay?: Partial<Record<'session' | 'catalog' | 'universe' | 'run' | 'preview' | 'items' | 'watchlist', number>>;
  /** fail a call: code and how many times (then it answers) */
  fail?: Partial<Record<'catalog' | 'run' | 'preview', { code: string; status: number; times: number; retryAfter?: number }>>;
  /** a second publication after N runs (smoke: an answer newer than the catalog) */
  newPublicationAfterRuns?: number;
  /** markup in the names (smoke: no element is made from them, report 9.1 text rendering) */
  hostile?: boolean;
}

export function fixtureApi(opts: FixtureOpts = {}): ScreenerApi & { market: Market; counters: Record<string, number> } {
  const m = market();
  if (opts.hostile) { const t = m.byTicker.get('BBCA')!; t.name = '<img src=x onerror="window.__xss=1">Bank "Central" Asia'; t.sector = '<b id="xss">Financials</b>' }
  let pub = 1;
  const versions = (): Versions => ({ screener_engine:'0a1b2c3d4e5f6071', registry:R.registry_version, screener_registry:R.screener_registry_version, price_data:'fixture-' + String(pub).padStart(58, '0'), flow_data:null });
  const data = () => ({ evaluation_date:m.evalDate, price_through:m.evalDate, flow_through:null, broker_behind_sessions:0, published_at:pub === 1 ? `${m.evalDate}T12:03:23Z` : `${m.evalDate}T23:59:00Z` });
  const shape = new Map<string, string>(R.indicators.map((x: any) => [x.id, x.overlay?.shape]));
  const periods = { '1M':21, '3M':63, '6M':126, '1Y':252 };
  const catalog = (): CatalogResponse => {
    const v = versions(), d = data();
    const presets = PRESETS.map(p => {
      if (p.availability !== 'AVAILABLE') return p;
      const r = runDef(m, p.definition, v, d);
      return { ...p, match_count:r.match_count, near_count:r.near_count };
    });
    return { versions:v, data:{ ...d, refresh:'ready' }, limits:LIMITS,
      indicators:catalogIndicators({ capBudgetMs:CAP_BUDGET_MS }),
      metrics:METRICS, fundamentals:FUNDAMENTALS, periods, groupings:[grouping('sector', m.tickers), grouping('industry', m.tickers)], presets };
  };
  const counters: Record<string, number> = {};
  const count = (k: string) => { counters[k] = (counters[k] || 0) + 1 };
  const wait = (k: keyof NonNullable<FixtureOpts['delay']>, signal?: AbortSignal) => new Promise<void>((ok, no) => {
    const ms = opts.delay?.[k] ?? 0; if (!ms) return ok();
    const t = setTimeout(ok, ms);
    signal?.addEventListener('abort', () => { clearTimeout(t); no(new DOMException('aborted', 'AbortError')) });
  });
  const failing = (k: 'catalog' | 'run' | 'preview') => {
    const f = opts.fail?.[k]; if (!f || f.times <= 0) return;
    f.times--; throw new ApiFailure(errorText(f.code, { retryAfter:f.retryAfter ?? null }) || `fixture failure ${f.code}`, f.code, f.status, undefined, f.retryAfter ?? null);
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
    kind:'fixture', market:m, counters,
    async session() { count('session'); await wait('session'); return { login:'fixture', csrf:'fixture-csrf' } },
    async catalog(inm) { count('catalog'); await wait('catalog'); failing('catalog'); return conditional('catalog', catalog(), inm) },
    async universe(inm) { count('universe'); await wait('universe'); return conditional<UniverseResponse>('universe', { versions:versions(), data:data(), rows:m.tickers.map(t => universeRow(m, t)) }, inm) },
    async run(req, o: CallOpts = {}) {
      count('run'); await wait('run', o.signal); if (o.signal?.aborted) throw new DOMException('aborted', 'AbortError');
      failing('run');
      checkParams(req.definition);
      runs++; if (opts.newPublicationAfterRuns && runs > opts.newPublicationAfterRuns) pub = 2;
      const v = { ...versions(), definition_hash:await hash(req.definition) }, body = runDef(m, req.definition, v, data());
      const bytes = enc(body);
      return { body:JSON.parse(new TextDecoder().decode(bytes)), bytes };
    },
    async preview(req, o: CallOpts = {}) {
      count('preview'); await wait('preview', o.signal); if (o.signal?.aborted) throw new DOMException('aborted', 'AbortError');
      failing('preview');
      checkParams(req.definition);
      if (req.data_version !== versions().price_data) throw new ApiFailure('New data was published; the screen is re-run.', 'DATA_VERSION_CHANGED', 409);
      return pv(m, req.definition, req.ticker, versions(), data(), id => shape.get(id), periods);
    },
    async validate(definition) { return { valid:true, definition_hash:await hash(definition), normalized:definition } },
    async counts(req) {
      count('counts');
      const v = versions(), d = data();
      return { versions:v, data:d, counts:req.definitions.map(x => { try { const r = runDef(m, x.definition, v, d); return { item_id:x.item_id, match_count:r.match_count, near_count:r.near_count } } catch (e) { return { item_id:x.item_id, error:{ code:'INVALID_CONDITION', message:String((e as Error).message) } } } }) };
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
