/* The page's own logic outside the DOM: CSV export (report 9.6), the boot pointer of the cached paint (6c.3-6c.5,
   6c.9 item 3), the live client's conditional GETs, CSRF and error mapping (8.1, 8.8; M261), the results sort (6.9
   Sort), the universe view and chip counts (P4, P15), and the remark wording (P4). */
import { describe, expect, it } from 'vitest';
import type { CatalogResponse, Cell, RunResponse, UniverseRow, Versions } from '../../src/core/contract.ts';
import { csvText, field, metaOf } from '../../src/csv.ts';
import { BootCache, sameVersions } from '../../src/api/boot-cache.ts';
import { liveApi, retryAfter } from '../../src/api/live.ts';
import { ApiFailure } from '../../src/api/types.ts';
import { sha256Hex, type FileCache } from '../../../terminal/src/data/rack.ts';
import { cellKey, sortRows } from '../../src/results.ts';
import { hiddenCounts, universeView } from '../../src/universe-view.ts';
import { remarkCsv, remarkText, T } from '../../src/texts.ts';
import { cardOfField, type Row } from '../../src/state.ts';
import type { Card } from '../../src/forms.ts';

const row = (ticker: string, over: Partial<Row> = {}): Row => ({ ticker, name:ticker + ' Tbk', sector:'Financials', industry:'Banks', last:1000, chg_1d_pct:1.5, adv20_idr:2e9,
  status:'match', met:1, need:1, remarks:[], cells:[], stale:false, last_bar_date:'2026-10-27', ...over });

describe('CSV export (csv.ts, report 9.6)', () => {
  it('prefixes formula-looking text with an apostrophe and writes numbers as numbers', () => {
    expect(field('=HYPERLINK("x")')).toBe(`"'=HYPERLINK(""x"")"`);
    expect(field('+1')).toBe("'+1");
    expect(field('-2')).toBe("'-2");
    expect(field('@cmd')).toBe("'@cmd");
    expect(field(-2)).toBe('-2');
    expect(field(1234.5)).toBe('1234.5');
    expect(field(null)).toBe('');
    expect(field('a,b')).toBe('"a,b"');
  });
  it('writes the metadata lines, the columns and per condition value, status, event date, bars ago and note', () => {
    const cells: Cell[] = [{ id:'a', status:'pass', value:27.4, eval_date:'2026-10-27', reason:null, remark:'PRICE_BREAK_IN_LOOKBACK' },
      { id:'b', status:'na', eval_date:'2026-10-27', reason:'INSUFFICIENT_HISTORY', remark:null }];
    const r = row('XMPL', { name:'=evil', met:1, remarks:[{ code:'PRICE_BREAK', action:'STOCK_SPLIT', ex_date:'2026-10-01', ratio_old:1, ratio_new:5, close_ratio:0.2 }], cells });
    const text = csvText([r], [{ id:'a', text:'RSI (7) < 30' }, { id:'b', text:'SMA 50' }],
      metaOf('My screen', null, { evaluation_date:'2026-10-27', published_at:'2026-10-27T13:03:23Z', versions:{ price_data:'p'.repeat(64), registry:'r'.repeat(16), screener_registry:'s'.repeat(16) } }));
    const lines = text.trim().split('\n');
    expect(lines.slice(0, 8)).toEqual(['# Screen,My screen', '# evaluation_date,2026-10-27', '# published_at,2026-10-27T13:03:23Z', `# price_data_version,${'p'.repeat(64)}`,
      `# registry_version,${'r'.repeat(16)}`, `# screener_registry_version,${'s'.repeat(16)}`, '# definition_hash,', '# market cap,not available']);
    expect(lines[8].split(',').slice(0, 10)).toEqual(['Symbol', 'Name', 'Sector', 'Industry', 'Last', '1D %', 'Avg value 20D (Rp B)', 'Status', 'Met (m/n)', 'Remark']);
    expect(lines[9]).toBe("XMPL,'=evil,Financials,Banks,1000,1.5,2,match,1/2,PRICE_BREAK STOCK_SPLIT 2026-10-01,27.4,pass,,,PRICE_BREAK_IN_LOOKBACK,,na,,,INSUFFICIENT_HISTORY");
  });
});

/* ---- the boot pointer (api/boot-cache.ts) ------------------------------------------------------------------- */
const memCache = (): FileCache & { m: Map<string, Uint8Array> } => { const m = new Map<string, Uint8Array>(); return { m, async get(s) { return m.get(s) ?? null }, async put(s, b) { m.set(s, b) } } };
const memStore = () => { const m = new Map<string, string>(); return { m, get<T>(k: string, d: T): T { const v = m.get(k); return v == null ? d : JSON.parse(v) }, set(k: string, v: unknown) { m.set(k, JSON.stringify(v)) }, del(k: string) { m.delete(k) } } };
const V = (p = 'a'): Versions => ({ screener_engine:'e'.repeat(16), registry:'r'.repeat(16), screener_registry:'s'.repeat(16), price_data:p.repeat(64), flow_data:null });
const catalogOf = (v: Versions) => ({ versions:v, data:{ evaluation_date:'2026-10-27', price_through:'2026-10-27', flow_through:null, broker_behind_sessions:0, published_at:'2026-10-27T13:03:23Z', refresh:'ready' } }) as unknown as CatalogResponse;
const bytes = (x: unknown) => new TextEncoder().encode(JSON.stringify(x));

describe('boot pointer (6c.3, 6c.9 item 3)', () => {
  it('stores bytes only when their sha256 equals the ETag, and reads them back for the same login', async () => {
    const cache = memCache(), st = memStore(), bc = new BootCache(cache, st);
    const c = catalogOf(V()), b = bytes(c), etag = await sha256Hex(b);
    expect(await bc.putCatalog('daniel', b, 'f'.repeat(64), c)).toBe(false);
    expect(cache.m.size).toBe(0);
    expect(await bc.putCatalog('daniel', b, etag, c)).toBe(true);
    const again = new BootCache(cache, st);
    expect(again.etags().catalog).toBe(etag);
    expect((await again.read('daniel')).catalog?.versions).toEqual(V());
  });
  it('drops a pointer of another login and never reads its bytes', async () => {
    const cache = memCache(), st = memStore(), bc = new BootCache(cache, st);
    const c = catalogOf(V()), b = bytes(c);
    await bc.putCatalog('alice', b, await sha256Hex(b), c);
    const other = new BootCache(cache, st);
    expect(await other.read('bob')).toEqual({ catalog:null, universe:null, result:null });
    expect(st.m.has('scr.boot')).toBe(false);
  });
  it('never draws a result at other versions than the cached catalog', async () => {
    const cache = memCache(), st = memStore(), bc = new BootCache(cache, st);
    const c = catalogOf(V()), b = bytes(c);
    await bc.putCatalog('daniel', b, await sha256Hex(b), c);
    const def = { universe:{ security_types:['stock'], traded_on_eval_date:true, exclude_price_breaks:true }, conditions:[], logic:'all' } as any;
    const stale = { versions:{ ...V('b'), definition_hash:'d'.repeat(64) } } as unknown as RunResponse;
    expect(await bc.putResult('daniel', def, bytes(stale), stale)).toBe(false);
    const ok = { versions:{ ...V(), definition_hash:'d'.repeat(64) } } as unknown as RunResponse;
    expect(await bc.putResult('daniel', def, bytes(ok), ok)).toBe(true);
    expect((await new BootCache(cache, st).read('daniel')).result?.versions.definition_hash).toBe('d'.repeat(64));
    // a new publication drops the rest of the pointer (6c.5 item 2)
    const c2 = catalogOf(V('c')), b2 = bytes(c2);
    await bc.putCatalog('daniel', b2, await sha256Hex(b2), c2);
    expect(bc.pointer()?.last).toBeNull();
    expect(sameVersions(V(), V('c'))).toBe(false);
  });
});

/* ---- the live client (api/live.ts) ---------------------------------------------------------------------------- */
type Call = { url: string; init: RequestInit };
function fakeFetch(answers: ((c: Call) => Response)[]) {
  const calls: Call[] = [];
  const f = (async (url: string, init: RequestInit = {}) => { const c = { url, init }; calls.push(c); const a = answers.shift(); if (!a) throw new Error('no answer for ' + url); return a(c) }) as unknown as typeof fetch;
  return { f, calls };
}
const json = (status: number, body: unknown, headers: Record<string, string> = {}) => () => new Response(status === 304 ? null : JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json', ...headers } });

describe('live client (8.1, 8.8)', () => {
  it('sends If-None-Match from the pointer and reads 304 and the ETag', async () => {
    const { f, calls } = fakeFetch([json(304, null, { ETag:'"abc"' }), json(200, { versions:V() }, { ETag:'"def"' })]);
    const api = liveApi({ fetchImpl:f });
    expect(await api.catalog('abc')).toEqual({ status:304, etag:'abc' });
    expect((calls[0].init.headers as Record<string, string>)['If-None-Match']).toBe('"abc"');
    const r = await api.universe(null);
    expect(r.status).toBe(200);
    expect(r.etag).toBe('def');
    expect(calls[1].url).toBe('/api/v1/screener/universe');
  });
  it('puts the CSRF token on writes and orders runs and previews per page (client_order)', async () => {
    const { f, calls } = fakeFetch([json(200, { login:'daniel', csrf_token:'tok' }), json(200, { rows:[] }), json(200, { rows:[] })]);
    const api = liveApi({ fetchImpl:f });
    const req = { schema_version:1 as const, definition:{} as any };
    await api.run(req); await api.run(req);
    expect((calls[1].init.headers as Record<string, string>)['X-CSRF-Token']).toBe('tok');
    const a = JSON.parse(String(calls[1].init.body)), b = JSON.parse(String(calls[2].init.body));
    expect(a.client_order.page).toBe(b.client_order.page);
    expect([a.client_order.seq, b.client_order.seq]).toEqual([1, 2]);
  });
  it('maps 401 {"detail": ...} (TEMPORARY, M261) to the sign-in message', async () => {
    const { f } = fakeFetch([json(401, { detail:'Not authenticated' })]);
    await expect(liveApi({ fetchImpl:f }).catalog(null)).rejects.toMatchObject({ code:'UNAUTHENTICATED', status:401, message:T.signIn });
  });
  it('maps a refusal with its field and details, and 503 NOT_READY with Retry-After', async () => {
    const { f } = fakeFetch([json(200, { login:'d', csrf_token:'t' }),
      json(422, { error:{ code:'PARAM_OUT_OF_RANGE', field:'definition.conditions[0].test.metric.params.length', details:{ field:'length', min:1, max:500 } } }),
      json(503, { error:{ code:'SCREENER_NOT_READY' } }, { 'Retry-After':'7' })]);
    const api = liveApi({ fetchImpl:f });
    const e1 = await api.run({ schema_version:1, definition:{} as any }).catch(e => e) as ApiFailure;
    expect(e1).toBeInstanceOf(ApiFailure);
    expect(e1.code).toBe('PARAM_OUT_OF_RANGE');
    expect(e1.field).toBe('definition.conditions[0].test.metric.params.length');
    expect(e1.message).toMatch(/1 to 500/);
    const e2 = await api.catalog(null).catch(e => e) as ApiFailure;
    expect([e2.code, e2.status, e2.retryAfter]).toEqual(['SCREENER_NOT_READY', 503, 7]);
    expect(e2.message).toMatch(/retries in 7 s/);
  });
  it('reads Retry-After as seconds or an HTTP date', () => {
    expect(retryAfter('3')).toBe(3);
    expect(retryAfter(new Date(10_000).toUTCString(), 0)).toBe(10);
    expect(retryAfter(null)).toBeNull();
  });
  it('turns a network failure into SCREENER_UNAVAILABLE wording', async () => {
    const f = (async () => { throw new TypeError('fetch failed') }) as unknown as typeof fetch;
    await expect(liveApi({ fetchImpl:f }).items('screen')).rejects.toMatchObject({ code:'NETWORK', message:T.unreachable });
  });
});

describe('results sort (report 6.9 Sort)', () => {
  const c = (id: string, value: number | null, status: Cell['status'] = 'pass'): Cell => ({ id, status, value, eval_date:'2026-10-27', reason:status === 'na' ? 'INSUFFICIENT_HISTORY' : null, remark:null });
  it('puts matches above near rows, nulls last in both directions, ties by ADV20 then ticker', () => {
    const rows = [row('AAA', { status:'near', met:1, cells:[c('a', 50)] }), row('BBB', { cells:[c('a', null, 'na')] }), row('CCC', { cells:[c('a', 10)], adv20_idr:1e9 }),
      row('DDD', { cells:[c('a', 10)], adv20_idr:5e9 }), row('EEE', { cells:[c('a', 30)] })];
    const order = (dir: 'asc' | 'desc') => sortRows(rows, { key:'c:a', dir }).map(r => r.ticker);
    expect(order('desc')).toEqual(['EEE', 'DDD', 'CCC', 'BBB', 'AAA']);
    expect(order('asc')).toEqual(['DDD', 'CCC', 'EEE', 'BBB', 'AAA']);
  });
  it('sorts events by 1000 − bars_ago', () => {
    expect(cellKey({ id:'a', status:'pass', bars_ago:2, eval_date:null, reason:null, remark:null }, 'event')).toBe(998);
    expect(cellKey({ id:'a', status:'fail', bars_ago:null, eval_date:null, reason:null, remark:null }, 'event')).toBeNull();
  });
});

describe('universe view and chips (P4, P15)', () => {
  const u = (ticker: string, over: Partial<UniverseRow> = {}): UniverseRow => ({ ticker, name:ticker, sector:'Energy', industry:'Coal', last:500, chg_1d_pct:0, adv20_idr:5e9, first_bar:'2020-01-02', last_bar:'2026-10-27', bars:1500, stale:false, remarks:[], ...over });
  const rows = [u('A'), u('B', { stale:true, last_bar:'2026-10-20', remarks:[{ code:'STALE', last_bar_date:'2026-10-20' }] }),
    u('C', { remarks:[{ code:'PRICE_BREAK', action:'STOCK_SPLIT', ex_date:'2026-10-01', ratio_old:1, ratio_new:5, close_ratio:0.2 }] }), u('D', { sector:null, industry:null }), u('E', { last:40 })];
  const base = { security_types:['stock'] as ['stock'], traded_on_eval_date:true, exclude_price_breaks:true, price_min:50, adv20_min_idr:1e9 };
  it('hides stale and price-break stocks by default and counts what each chip hides', () => {
    const v = universeView(rows, base);
    expect(v.rows.map(r => r.ticker)).toEqual(['A', 'D']);
    expect(v.counts).toEqual({ listed:5, eligible:2, stale_hidden:1, price_break_hidden:1, filtered_out:1 });
    expect(hiddenCounts(rows)).toEqual({ stale:1, breaks:1 });
    expect(universeView(rows, { ...base, traded_on_eval_date:false, exclude_price_breaks:false }).rows.map(r => r.ticker)).toEqual(['A', 'B', 'C', 'D']);
  });
  it('keeps an unclassified stock under an include filter only with include_unclassified', () => {
    expect(universeView(rows, { ...base, sectors_in:['Energy'] }).rows.map(r => r.ticker)).toEqual(['A']);
    expect(universeView(rows, { ...base, sectors_in:['Energy'], include_unclassified:true }).rows.map(r => r.ticker)).toEqual(['A', 'D']);
    expect(universeView(rows, { ...base, sectors_out:['Energy'] }).rows.map(r => r.ticker)).toEqual(['D']);
  });
  it('is not exact while a metric filter needs a formula (the run decides)', () => {
    expect(universeView(rows, { ...base, metric_filters:[{ kind:'value', op:'gt', value:1, metric:{ kind:'indicator', indicator:'I13', output:'rsi' } }] }).exact).toBe(false);
    expect(universeView(rows, { ...base, metric_filters:[{ kind:'value', op:'gt', value:1e10, metric:{ kind:'universe', attr:'adv20_idr' } }] }).rows).toEqual([]);
  });
});

describe('remarks (P4)', () => {
  it('words the remark codes as the report says', () => {
    expect(remarkText({ code:'STALE', last_bar_date:'2026-10-20' })).toBe('Stale: last trade 2026-10-20');
    expect(remarkText({ code:'PRICE_BREAK', action:'STOCK_SPLIT', ex_date:'2026-10-01', ratio_old:1, ratio_new:5, close_ratio:0.2 })).toBe('Price break: stock split (1:5) ex 2026-10-01, history not adjusted');
    expect(remarkCsv([{ code:'STALE', last_bar_date:'2026-10-20' }])).toBe('STALE 2026-10-20');
  });
});

describe('a worker refusal on its card (report 8.8: where and how to fix)', () => {
  const cards = ['a', 'b', 'c'].map(id => ({ id }) as unknown as Card);
  it('finds the card a condition field names, switched-off cards counted (definitionOf keeps card order)', () => {
    expect(cardOfField('definition.conditions[1].test.metric.params.length', cards)?.id).toBe('b');
    expect(cardOfField('conditions[2].test.within', cards)?.id).toBe('c');
    expect(cardOfField('definition.conditions[7].test', cards)).toBeNull();
    expect(cardOfField('definition.universe.metric_filters[0].value', cards)).toBeNull();
    expect(cardOfField(undefined, cards)).toBeNull();
  });
});
