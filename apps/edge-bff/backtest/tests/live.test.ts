/* The page on live data outside the DOM: the default period end from the catalog (state.ts applyCatalog, request.ts
   publishedThrough), the live BacktestApi's answers for a refused request and an aborted preview (live.ts), and the
   production words on the data (texts.ts). */
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BacktestResultCore, Catalog, Warning } from '../src/core/contract.ts';
import { legacyCard } from '../src/core/catalog.ts';
import { Compute } from '../src/api/compute.ts';
import { buildRequest, publishedThrough } from '../src/api/request.ts';
import { liveApi } from '../src/api/live.ts';
import { PUBLISHED_TEXTS, warningText } from '../src/api/texts.ts';
import { ApiFailure, isAbort, type BacktestApi } from '../src/api/types.ts';
import { setEnv } from '../src/env.ts';
import { applyCatalog, S, TEMPLATES } from '../src/state.ts';
import { CATALOG } from './smoke/stub.ts';

afterEach(() => vi.unstubAllGlobals());

/* a catalog with flow as given; the page's readiness from it (production: compute.ts) */
const withFlow = (flow: Partial<Catalog['flow']>): Catalog => ({ ...CATALOG, data_through:'2022-12-30', flow:{ ...CATALOG.flow, ...flow } });
function boot(cat: Catalog) {
  const compute = new Compute(() => cat);
  setEnv({ ready:c => compute.ready(c) } as BacktestApi, cat);
  applyCatalog();
  return S.to;
}

describe('the default period end (applyCatalog)', () => {
  const DEFAULT = S.conds;
  afterEach(() => { S.conds = DEFAULT; S.mode = 'single' });
  it('is the broker data\'s day when the default strategy reads the broker files and flow is available', () => {
    expect(S.conds.some(c => c.type === 'fnet' || c.type === 'broker')).toBe(true);           // the default entry has flow cards
    expect(boot(withFlow({ available:true, reason:null, data_through:'2022-11-30' }))).toBe('2022-11-30');
  });
  it('is catalog.data_through while flow is not available (the flow cards are not sent)', () => {
    expect(boot(withFlow({ available:false, data_through:null }))).toBe('2022-12-30');
  });
  it('is catalog.data_through for a strategy without flow cards', () => {
    S.conds = TEMPLATES['Breakout + volume']();
    expect(boot(withFlow({ available:true, reason:null, data_through:'2022-11-30' }))).toBe('2022-12-30');
  });
  it('is never after catalog.data_through', () => {
    expect(boot(withFlow({ available:true, reason:null, data_through:'2023-01-31' }))).toBe('2022-12-30');
  });
  it('counts a portfolio ranked by foreign net flow as reading the broker files (the worker\'s rule)', () => {
    const cat = withFlow({ available:true, reason:null, data_through:'2022-11-30' });
    const q = buildRequest({ ...S, mode:'portfolio', rankBy:'fnet', conds:[legacyCard('adx', 'a1')], exitConds:[] }, { ready:() => true, monteCarloRuns:0 });
    expect(publishedThrough(q, cat)).toBe('2022-11-30');
    expect(publishedThrough({ ...q, portfolio:{ ...q.portfolio!, rank_by:'adx' } }, cat)).toBe('2022-12-30');
  });
});

describe('the live BacktestApi (live.ts)', () => {
  const answer = (status: number, body: unknown) => vi.stubGlobal('fetch', async (url: string, init?: RequestInit) =>
    url === '/api/v1/auth/session' ? Response.json({ csrf_token:'t' }) : Response.json(body, { status }));
  it('gives the server\'s 422 FLOW_DATA_THROUGH as the ApiFailure the page\'s toast shows (its message, code and field)', async () => {
    const message = 'The broker data is published through 2022-11-30: a run with flow conditions or ranked by foreign net flow must end on or before it (period.to is 2022-12-30).';
    answer(422, { error:{ code:'FLOW_DATA_THROUGH', field:'period.to', message } });
    const err = await liveApi({ cache:{ get:async () => null, put:async () => {} } }).submit({} as never).catch(e => e);
    expect(err).toBeInstanceOf(ApiFailure);
    expect([err.message, err.code, err.status, err.field]).toEqual([message, 'FLOW_DATA_THROUGH', 422, 'period.to']);
  });
  it('hands the preview\'s AbortSignal to fetch: an aborted preview rejects with an AbortError (nothing to show)', async () => {
    let seen: AbortSignal | undefined;
    vi.stubGlobal('fetch', (url: string, init?: RequestInit) => url === '/api/v1/auth/session' ? Promise.resolve(Response.json({ csrf_token:'t' }))
      : new Promise((_, no) => { seen = init?.signal ?? undefined; seen?.addEventListener('abort', () => no(new DOMException('aborted', 'AbortError'))) }));
    const ctl = new AbortController();
    const p = liveApi({ cache:{ get:async () => null, put:async () => {} } }).signalsPreview({} as never, { signal:ctl.signal }).catch(e => e);
    await vi.waitFor(() => expect(seen).toBe(ctl.signal));
    ctl.abort();
    expect(isAbort(await p)).toBe(true);
  });
});

describe('the production words on the data (texts.ts)', () => {
  const W: Warning[] = [
    { code:'PERIOD_CLIPPED', message:'MAPI has no published bar before 2019-06-03.' },
    { code:'TICKERS_EXCLUDED', message:'2 ticker(s) of the universe were left out of this run.', count:2, tickers:['AAAA', 'BBBB'],
      reasons:[{ ticker:'AAAA', code:'DATA_MISSING', message:'no files' }, { ticker:'BBBB', code:'INDICATOR_OUTPUT_EMPTY', message:'no value' }] },
    { code:'DATA_GAP', message:'3 calendar day(s) without a bar.', count:3, tickers:['CCCC'] },
    { code:'SURVIVORSHIP', message:'The universe is today\'s list.' },
  ];
  it('the header names the published data, in the short form', () => {
    expect(PUBLISHED_TEXTS.dataNote(CATALOG)).toBe('Published data · long-only');
  });
  it('the Robustness warning box has every warning of the run, with the tickers it names', () => {
    const box = PUBLISHED_TEXTS.robustnessWarning({ meta:{ warnings:W } } as unknown as BacktestResultCore);
    expect(box).toBe(['⚠︎ Single market path: history happened once.', 'MAPI has no published bar before 2019-06-03.',
      '2 ticker(s) of the universe were left out of this run. Tickers: AAAA (DATA_MISSING), BBBB (INDICATOR_OUTPUT_EMPTY).',
      '3 calendar day(s) without a bar. Tickers: CCCC.', 'The universe is today\'s list.',
      'Before trusting a result: keep the out-of-sample untouched while tuning, and re-check the liquidity of every fill.'].join(' '));
    expect(warningText(W[3])).toBe('The universe is today\'s list.');
  });
  it('the trial count is the server\'s, per strategy line', () => {
    expect(PUBLISHED_TEXTS.trials).toBe('for this strategy');
  });
});
