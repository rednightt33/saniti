/* EXEC-SCREENER-V21 (product decision 6, user 2026-11-06): the explicit Screen now gate (src/run.ts, src/screen-gate.ts)
   and the extra columns' auxiliary request (src/extra-columns.ts), over the fixture's catalog and universe and a fake
   ScreenerApi whose answers the test releases one by one (no DOM: the renderers are the state.ts no-ops). */
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CatalogResponse, RunRequest, RunResponse, UniverseResponse } from '../../src/core/contract.ts';
import { ApiFailure, type CallOpts, type RunAnswer, type ScreenerApi } from '../../src/api/types.ts';
import { liveApi } from '../../src/api/live.ts';
import { entriesOf } from '../../src/entries.ts';
import { newCard } from '../../src/forms.ts';
import { canonical, ctx, definitionOf, freshUniverse, S } from '../../src/state.ts';
import { cancelRun, republished, retry, screenBlocked, screenedCards, screenedDefinition, screenNow, screenPhase, screenReady, sync, useCached } from '../../src/run.ts';
import { cacheKeyOf, extraCell, extraReset, extraColumnInfo, extraSortKey, nextAuxDefinition, setColumns, shownColumns } from '../../src/extra-columns.ts';
import { gateView, shortcutOf, typingTarget } from '../../src/screen-gate.ts';
import { fixtureApi } from '../fixture/api.ts';

type Call = { req: Omit<RunRequest, 'client_order'>; opts: CallOpts; resolve: (a: RunAnswer) => void; reject: (e: unknown) => void; aborted: () => boolean };
const fx = fixtureApi();
let catalog: CatalogResponse, universe: UniverseResponse, calls: Call[] = [];
const main = () => calls.filter(c => c.opts.lane !== 'aux'), aux = () => calls.filter(c => c.opts.lane === 'aux');
/** the fixture engine's real answer to a request */
const answer = async (c: Call, over: (r: RunResponse) => RunResponse = r => r) => { const a = await fx.run(c.req); const body = over(a.body); c.resolve({ body, bytes:new TextEncoder().encode(JSON.stringify(body)) }); await flush() };
const flush = () => new Promise(ok => setTimeout(ok, 0));
const api = (): ScreenerApi => ({
  ...fx,
  run(req, opts = {}) {
    return new Promise<RunAnswer>((resolve, reject) => {
      const c: Call = { req, opts, resolve, reject, aborted:() => !!opts.signal?.aborted };
      opts.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
      calls.push(c);
    });
  },
});
const card = (key: string, over = {}) => newCard(ctx.byKey.get(key)!, S.cards.map(c => c.id), over);
const edit = () => sync();         // app.ts refresh calls sync after every edit

beforeAll(async () => {
  const c = await fx.catalog(null), u = await fx.universe(null);
  if (c.status !== 200 || u.status !== 200) throw new Error('fixture');
  catalog = c.body; universe = u.body;
});
beforeEach(() => {
  cancelRun();
  calls = [];
  ctx.api = api(); ctx.catalog = catalog; ctx.universe = universe; ctx.entries = entriesOf(catalog); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  ctx.R = null; ctx.running = false; ctx.runError = null; ctx.refused = null; ctx.pending = false; ctx.stale = false;
  S.universe = freshUniverse(); S.cards = []; S.logic = 'all'; S.atLeast = 2; S.errors = {};
  extraReset(); setColumns([]);
});
afterEach(() => { vi.useRealTimers() });

describe('the Screen now gate (run.ts)', () => {
  it('an edit is pending: no request, the table stays (also for a definition listed locally)', async () => {
    screenNow();                                           // the boot: an empty screen is listed from the universe rows
    expect(calls.length).toBe(0);
    const R0 = ctx.R!;
    expect(R0.run).toBeNull(); expect(screenPhase()).toBe('clean');
    S.universe.price_min = 500; edit();                    // a local definition: still pending until Screen now
    expect(ctx.R).toBe(R0); expect(screenPhase()).toBe('pending'); expect(ctx.stale).toBe(true); expect(calls.length).toBe(0);
    S.cards.push(card('I13')); edit();                     // a condition: pending, no request
    expect(ctx.R).toBe(R0); expect(calls.length).toBe(0); expect(screenReady()).toBe(true);
    S.cards = []; edit();                                  // back to a local one
    screenNow();                                           // listed locally at once, no request
    expect(calls.length).toBe(0); expect(ctx.R).not.toBe(R0); expect(ctx.R!.rows.every(r => (r.last ?? 0) >= 500)).toBe(true);
    expect(screenPhase()).toBe('clean'); expect(ctx.stale).toBe(false);
  });
  it('Screen now runs at once: clean -> pending -> running -> clean; the table answers the run', async () => {
    screenNow();
    S.cards.push(card('I13')); edit();
    expect(screenPhase()).toBe('pending');
    screenNow();
    expect(main().length).toBe(1); expect(screenPhase()).toBe('running'); expect(ctx.stale).toBe(true);
    const def = definitionOf();
    expect(canonical(screenedDefinition())).toBe(canonical(def));         // the run on its way
    await answer(main()[0]);
    expect(screenPhase()).toBe('clean'); expect(ctx.R!.defHash).toBe(canonical(def)); expect(ctx.R!.def).toEqual(def);
    expect(screenedCards().map(c => c.id)).toEqual(S.cards.map(c => c.id));
  });
  it('latest wins on repeated Screen now: the older fetch is aborted and its late answer ignored', async () => {
    S.cards.push(card('I13', { value:30 })); edit(); screenNow();
    S.cards[0].value = 40; edit(); screenNow();
    expect(main().length).toBe(2); expect(main()[0].aborted()).toBe(true); expect(main()[1].aborted()).toBe(false);
    await answer(main()[1]);
    const key = canonical(definitionOf());
    expect(ctx.R!.defHash).toBe(key);
    main()[0].resolve({ body:{} as RunResponse, bytes:new Uint8Array() }); await flush();      // a late answer of the aborted call
    expect(ctx.R!.defHash).toBe(key);
  });
  it('an edit during a run does not abort it: the table answers the run, the edit stays pending', async () => {
    S.cards.push(card('I13', { value:30 })); edit(); screenNow();
    const asked = canonical(definitionOf());
    S.cards[0].value = 45; edit();
    expect(main()[0].aborted()).toBe(false); expect(screenPhase()).toBe('running');
    await answer(main()[0]);
    expect(ctx.R!.defHash).toBe(asked); expect(screenPhase()).toBe('pending'); expect(ctx.stale).toBe(true);
    expect(canonical(screenedDefinition())).toBe(asked);                 // the preview describes the table, not the edit
  });
  it('a field error or too many conditions blocks Screen now with its reason; nothing is sent', () => {
    S.cards.push(card('I13')); S.errors = { [S.cards[0].id]:{ value:'Enter a number.' } }; edit();
    expect(screenPhase()).toBe('pending'); expect(screenReady()).toBe(false);
    expect(screenBlocked()).toMatch(/Fix the highlighted field/);
    expect(gateView().hint).toMatch(/Fix the highlighted field/);
    screenNow(); expect(calls.length).toBe(0);
    S.errors = {};
    for (let k = 0; k < 21; k++) S.cards.push(card('I13'));
    edit();
    expect(screenBlocked()).toMatch(/At most 20 enabled conditions\. Switch off or remove 2 condition\(s\)\. Allowed: .*Refused: /);
    screenNow(); expect(calls.length).toBe(0);
  });
  it('a refusal stays on its card; Screen now does not send it again, Retry does; an edit clears the refusal', async () => {
    S.cards.push(card('I13')); edit(); screenNow();
    main()[0].reject(new ApiFailure('RSI length: must be at most 1000.', 'PARAM_OUT_OF_RANGE', 422, 'definition.conditions[0].test.metric.params.length')); await flush();
    expect(screenPhase()).toBe('error'); expect(ctx.refused?.id).toBe(S.cards[0].id); expect(screenReady()).toBe(false);
    screenNow(); expect(main().length).toBe(1);
    retry(); expect(main().length).toBe(2);
    await answer(main()[1]);
    expect(screenPhase()).toBe('clean');
    main(); // a second refusal, then an edit
    S.cards[0].value = 20; edit(); screenNow();
    main()[2].reject(new ApiFailure('no', 'INVALID_CONDITION', 422, 'definition.conditions[0].test.value')); await flush();
    expect(ctx.refused).not.toBeNull();
    S.cards[0].value = 25; edit();
    expect(ctx.refused).toBeNull(); expect(screenPhase()).toBe('pending');
  });
  it('BUSY is retried twice (1 s, 2 s), then the error and Retry stay (6c.6: not sent again until an edit or Retry)', async () => {
    vi.useFakeTimers();
    S.cards.push(card('I13')); edit(); screenNow();
    for (const wait of [1000, 2000]) {
      main().at(-1)!.reject(new ApiFailure('busy', 'BUSY', 409)); await vi.advanceTimersByTimeAsync(0);
      expect(screenPhase()).toBe('running');
      await vi.advanceTimersByTimeAsync(wait);
    }
    expect(main().length).toBe(3);
    main()[2].reject(new ApiFailure('busy', 'BUSY', 409)); await vi.advanceTimersByTimeAsync(5000);
    expect(main().length).toBe(3); expect(screenPhase()).toBe('error'); expect(screenReady()).toBe(false);
    screenNow(); expect(main().length).toBe(3);
    retry(); expect(main().length).toBe(4);
  });
  it('an unreachable service is tried once more after 2 s, then Screen now may send it again (not a refusal)', async () => {
    vi.useFakeTimers();
    S.cards.push(card('I13')); edit(); screenNow();
    main()[0].reject(new ApiFailure('down', 'SCREENER_UNAVAILABLE', 503)); await vi.advanceTimersByTimeAsync(2000);
    expect(main().length).toBe(2);
    main()[1].reject(new ApiFailure('down', 'SCREENER_UNAVAILABLE', 503)); await vi.advanceTimersByTimeAsync(5000);
    expect(main().length).toBe(2); expect(screenPhase()).toBe('error'); expect(screenReady()).toBe(true);
    screenNow(); expect(main().length).toBe(3);
  });
  it('a local screen asked before the universe answered is listed once it arrives', () => {
    ctx.universe = null;
    screenNow(); expect(ctx.R).toBeNull(); expect(calls.length).toBe(0); expect(screenPhase()).toBe('clean');
    ctx.universe = universe; sync();
    expect(ctx.R?.run).toBeNull(); expect(ctx.R!.rows.length).toBeGreaterThan(0); expect(calls.length).toBe(0);
  });
  it('a publication change re-runs the definition the table answered, never the pending edits', async () => {
    S.cards.push(card('I13', { value:30 })); edit(); screenNow(); await answer(main()[0]);
    const answered = ctx.R!.defHash;
    S.cards[0].value = 55; edit();                         // pending
    ctx.catalog = { ...catalog, versions:{ ...catalog.versions, price_data:'n'.repeat(64) } };
    republished();
    expect(main().length).toBe(2); expect(canonical(main()[1].req.definition)).toBe(answered);
    expect(screenPhase()).toBe('running');
    await answer(main()[1]);
    expect(ctx.R!.defHash).toBe(answered); expect(screenPhase()).toBe('pending');
  });
  it('the boot uses a cached result whose versions equal the catalog (no run), else it runs', async () => {
    S.cards.push(card('I13')); edit();
    const def = definitionOf(), r = (await fx.run({ schema_version:1, definition:def })).body;
    useCached(r, def); screenNow();
    expect(calls.length).toBe(0); expect(screenPhase()).toBe('clean');
    cancelRun(); ctx.R = null;
    useCached({ ...r, versions:{ ...r.versions, screener_engine:'f'.repeat(16) } }, def); screenNow();
    expect(main().length).toBe(1);
  });
  it('the shortcuts: Alt+S and Ctrl/Cmd+Enter, left alone while composing; Alt+S not in a text field', () => {
    const k = (o: Partial<KeyboardEvent>) => shortcutOf({ altKey:false, ctrlKey:false, metaKey:false, shiftKey:false, key:'', code:'', repeat:false, isComposing:false, ...o });
    expect(k({ altKey:true, code:'KeyS', key:'ß' })).toBe('alt-s');
    expect(k({ ctrlKey:true, key:'Enter' })).toBe('mod-enter');
    expect(k({ metaKey:true, key:'Enter' })).toBe('mod-enter');
    expect(k({ ctrlKey:true, altKey:true, code:'KeyS' })).toBeNull();        // AltGr
    expect(k({ ctrlKey:true, key:'Enter', isComposing:true })).toBeNull();
    expect(k({ altKey:true, code:'KeyS', repeat:true })).toBeNull();
    expect(typingTarget({ tagName:'INPUT', type:'text' } as any)).toBe(true);
    expect(typingTarget({ tagName:'INPUT', type:'number' } as any)).toBe(false);
    expect(typingTarget({ tagName:'TEXTAREA' } as any)).toBe(true);
    expect(typingTarget({ tagName:'DIV', isContentEditable:true } as any)).toBe(true);
  });
  it('the controls name the phase: Up to date, Screen now, Screening…', async () => {
    screenNow(); expect(gateView()).toMatchObject({ phase:'clean', ready:false, label:'Up to date' });
    S.cards.push(card('I13')); edit(); expect(gateView()).toMatchObject({ phase:'pending', ready:true, label:'Screen now' });
    screenNow(); expect(gateView()).toMatchObject({ phase:'running', ready:false, label:'Screening…' });
  });
});

describe('extra columns: the auxiliary request (extra-columns.ts)', () => {
  const tableRun = async () => { S.cards.push(card('I13', { value:60, opt:'value|rsi|lt' })); edit(); screenNow(); await answer(main()[0]) };
  it('is sent after the main run settled, on its own lane, at the table version, for the table tickers', async () => {
    setColumns(['rvol', 'ret_1m']);
    expect(shownColumns()).toEqual(['rvol', 'ret_1m']);
    S.cards.push(card('I13', { value:60, opt:'value|rsi|lt' })); edit(); screenNow();
    expect(aux().length).toBe(0);                          // never while the main run is in flight
    await answer(main()[0]);
    expect(aux().length).toBe(1);
    const a = aux()[0];
    expect(a.req.data_version).toBe(ctx.R!.run!.versions.price_data);
    expect(a.req.definition.logic).toBe('any');
    expect([...a.req.definition.universe.tickers!]).toEqual([...new Set(ctx.R!.rows.map(r => r.ticker))].sort());
    expect(a.req.definition.conditions.map(c => c.id)).toEqual(['xa', 'x0', 'x1']);
    expect(extraCell(ctx.R!.rows[0].ticker, 'rvol')).toEqual({ kind:'loading' });
    const R = ctx.R;
    await answer(a);
    expect(ctx.R).toBe(R);                                 // the auxiliary answer never touches the table's result
    const tk = ctx.R!.rows[0].ticker, x = extraCell(tk, 'rvol');
    expect(x.kind).toBe('value');
    if (x.kind === 'value') { expect(x.cell).toHaveProperty('eval_date'); expect(x.cell).toHaveProperty('reason'); expect(x.cell).toHaveProperty('remark') }
    expect(extraSortKey(tk, 'rvol')).toBe(x.kind === 'value' ? x.cell.value : null);
    expect(extraColumnInfo('ret_1m')).not.toBeNull();
    expect(aux().length).toBe(1);                          // everything answered: nothing more is asked
  });
  it('a main run while an auxiliary request is in flight cancels the auxiliary one and is never replaced by it', async () => {
    setColumns(['rvol']); await tableRun();
    expect(aux().length).toBe(1);
    S.cards[0].value = 55; edit(); screenNow();
    expect(aux()[0].aborted()).toBe(true); expect(main()[1].aborted()).toBe(false);
    await answer(main()[1]);
    expect(ctx.R!.defHash).toBe(canonical(definitionOf()));
    expect(aux().length).toBe(2);                          // asked again for the new table, after it settled
  });
  it('a publication change cancels the auxiliary request in flight', async () => {
    setColumns(['rvol']); await tableRun();
    expect(aux().length).toBe(1);
    ctx.catalog = { ...catalog, versions:{ ...catalog.versions, price_data:'n'.repeat(64) } };
    republished();
    expect(aux()[0].aborted()).toBe(true); expect(main().length).toBe(2);
    ctx.catalog = catalog;
  });
  it('the live client sends the auxiliary request on a second page id with its own sequence', async () => {
    const bodies: any[] = [];
    const f = (async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/auth/session') return new Response(JSON.stringify({ login:'u', csrf_token:'t' }), { status:200 });
      bodies.push(JSON.parse(String(init!.body)));
      return new Response(JSON.stringify({ ok:1 }), { status:200 });
    }) as typeof fetch;
    const live = liveApi({ fetchImpl:f });
    await live.run({ schema_version:1, definition:definitionOf() });
    await live.run({ schema_version:1, definition:definitionOf() }, { lane:'aux' });
    await live.run({ schema_version:1, definition:definitionOf() }, { lane:'main' });
    await live.run({ schema_version:1, definition:definitionOf() }, { lane:'aux' });
    const [m1, a1, m2, a2] = bodies.map(b => b.client_order);
    expect(m1.page).toBe(m2.page); expect(a1.page).toBe(a2.page); expect(a1.page).not.toBe(m1.page);
    expect([m1.seq, m2.seq, a1.seq, a2.seq]).toEqual([1, 2, 1, 2]);
    expect(/^[A-Za-z0-9._:-]{1,100}$/.test(a1.page)).toBe(true);      // edge-bff's client_order page form
  });
  it('drops an answer whose versions differ from the table or the catalog; the table stays', async () => {
    setColumns(['rvol']); await tableRun();
    const R = ctx.R;
    await answer(aux()[0], r => ({ ...r, versions:{ ...r.versions, screener_registry:'z'.repeat(16) } }));
    const x = extraCell(ctx.R!.rows[0].ticker, 'rvol');
    expect(x.kind).toBe('error'); expect(ctx.R).toBe(R);
    expect(aux().length).toBe(1);                          // no retry loop
  });
  it('a failure marks the columns with its message and is not retried until the columns change', async () => {
    setColumns(['rvol', 'natr']); await tableRun();
    aux()[0].reject(new ApiFailure('This screen is costed above your compute budget for the minute; try again shortly.', 'LIMIT_EXCEEDED', 422)); await flush();
    expect(extraCell(ctx.R!.rows[0].ticker, 'natr')).toEqual({ kind:'error', message:expect.stringMatching(/compute budget/) });
    sync(); await flush(); expect(aux().length).toBe(1);
    setColumns(['rvol', 'natr']); expect(aux().length).toBe(2);       // a user action asks again
  });
  it('keeps the NA reason of a cell', async () => {
    setColumns(['ret_1m']); await tableRun();
    const tk = ctx.R!.rows[0].ticker;
    await answer(aux()[0], r => ({ ...r, rows:r.rows.map(row => row.ticker !== tk ? row : { ...row, cells:row.cells.map(c => c.id === 'x0' ? { ...c, status:'na', value:null, reason:'INSUFFICIENT_HISTORY' } : c) }) }));
    expect(extraCell(tk, 'ret_1m')).toMatchObject({ kind:'value', cell:{ status:'na', reason:'INSUFFICIENT_HISTORY', value:null } });
    expect(extraSortKey(tk, 'ret_1m')).toBeNull();
  });
  it('cache keys: versions (every field), universe, ticker set and the column parameters; never the evaluation date alone', async () => {
    setColumns(['rvol', 'ret_1m']); await tableRun();
    const k0 = cacheKeyOf('rvol')!, kRet = cacheKeyOf('ret_1m')!;
    expect(k0).not.toBe(kRet);
    const R = ctx.R!, run = R.run!;
    const withRun = (v: Partial<typeof run.versions>) => { ctx.R = { ...R, run:{ ...run, versions:{ ...run.versions, ...v } } }; ctx.catalog = { ...catalog, versions:{ ...catalog.versions, ...v } } };
    for (const f of ['price_data', 'flow_data', 'screener_engine', 'registry', 'screener_registry'] as const) {
      withRun({ [f]:'q'.repeat(16) }); expect(cacheKeyOf('rvol'), f).not.toBe(k0);
    }
    ctx.R = R; ctx.catalog = catalog; expect(cacheKeyOf('rvol')).toBe(k0);
    ctx.catalog = { ...catalog, data:{ ...catalog.data, evaluation_date:'2030-01-01' } }; expect(cacheKeyOf('rvol')).toBe(k0);   // the date alone changes nothing
    ctx.catalog = catalog;
    ctx.R = { ...R, def:{ ...R.def!, universe:{ ...R.def!.universe, price_min:999 } } }; expect(cacheKeyOf('rvol')).not.toBe(k0);
    ctx.R = { ...R, rows:R.rows.slice(1) }; expect(cacheKeyOf('rvol')).not.toBe(k0);
    ctx.R = { ...R, def:{ ...R.def!, universe:{ ...R.def!.universe, traded_on_eval_date:true } } };   // absent means true: same key
    expect(cacheKeyOf('rvol')).toBe(k0);
    ctx.R = R;
    // the table of another publication than the catalog asks nothing
    ctx.catalog = { ...catalog, versions:{ ...catalog.versions, price_data:'m'.repeat(64) } };
    expect(cacheKeyOf('rvol')).toBeNull(); expect(nextAuxDefinition()).toBeNull();
    ctx.catalog = catalog;
  });
  it('chunks to max_conditions: the anchor plus at most max_conditions - 1 columns per request', async () => {
    ctx.catalog = catalog = { ...catalog, limits:catalog.limits.map(l => l.name === 'max_conditions' ? { ...l, value:3 } : l) };
    setColumns(['rvol', 'ret_1m', 'natr', 'hv']); await tableRun();
    expect(aux()[0].req.definition.conditions.length).toBe(3);
    await answer(aux()[0]);
    expect(aux().length).toBe(2); expect(aux()[1].req.definition.conditions.length).toBe(3);
    await answer(aux()[1]);
    expect(aux().length).toBe(2);
    for (const id of ['rvol', 'ret_1m', 'natr', 'hv']) expect(extraCell(ctx.R!.rows[0].ticker, id).kind).toBe('value');
    ctx.catalog = catalog = { ...catalog, limits:catalog.limits.map(l => l.name === 'max_conditions' ? { ...l, value:20 } : l) };
  });
  it('persists the chosen columns per browser under its own key', () => {
    const m = new Map<string, string>();
    vi.stubGlobal('localStorage', { getItem:(k: string) => m.get(k) ?? null, setItem:(k: string, v: string) => m.set(k, v), removeItem:(k: string) => m.delete(k) });
    try { setColumns(['hv', 'rvol', 'hv']); expect(JSON.parse(m.get('scr.extraCols')!)).toEqual(['hv', 'rvol']) }
    finally { vi.unstubAllGlobals() }
  });
});
