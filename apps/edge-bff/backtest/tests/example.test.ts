/* 3e, the example mode (ERRORS M527): the Backtest's example.
   - The stored example (verification/edge_multiuser/example_mode/capture_backtest.json: the request run on dev and the
     part of the worker's catalog it was built on) is the page's own default request on that part, and the part is the
     part of itself for that request (tests/example-part.ts). A change of the page's default setup fails here: capture
     the example again (that folder's backtest_catalog_job.py, backtest_request.ts and capture_job.py; ERRORS M527).
   - The part's rule holds on the made-up market: the page's request on the part is its request on the whole catalog.
   - src/api/example.ts answers the page from the example's files only: the stored run for the page's request (its card
     ids mapped onto the run), a refusal for any other, the run's condition tracks as the cards' series, the stored bars
     of the one ticker, and nothing else (no catalog, preview, job or price route of the live page). */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import CAPTURE from '../../../../verification/edge_multiuser/example_mode/capture_backtest.json?raw';
import { S } from '../src/state.ts';
import { toWire } from '../src/api/compute.ts';
import { exampleApi, requestForm } from '../src/api/example.ts';
import type { Card, TickerBars } from '../src/api/types.ts';
import type { BacktestRequest } from '../src/core/contract.ts';
import { defaultRequestOn, madeUpExample, type MadeUp } from './example-made-up.ts';
import { catalogPart } from './example-part.ts';

const AS_OF = '2026-10-23', FIRST = '2025-10-23';       // the synthetic market's last day, one year before it

describe('the stored Backtest example', () => {
  const cap = JSON.parse(CAPTURE) as { as_of: string; backtest: { built_on: never; request: BacktestRequest } };
  it('is the page\'s own default request on the catalog part it was built on, over the year to its date', () => {
    const { built_on, request } = cap.backtest;
    expect(catalogPart(built_on, request)).toEqual(built_on);
    expect(requestForm(defaultRequestOn(built_on)), 'the page\'s default setup changed: capture the Backtest example again (ERRORS M527)')
      .toBe(requestForm(request));
    expect([request.mode, request.period.to]).toEqual(['single', cap.as_of]);
  });
});

describe('the example API of the page (src/api/example.ts)', () => {
  let made: MadeUp, bars: TickerBars, files: Record<string, unknown>, asked: string[];
  beforeAll(async () => {
    made = await madeUpExample(AS_OF, FIRST);
    const col = (k: number) => made.bars.map(r => r[k]);
    bars = { ticker: made.ticker, dates: col(0), o: col(1), h: col(2), l: col(3), c: col(4), v: col(5) } as unknown as TickerBars;
    files = { 'backtest-catalog': made.catalog, 'backtest-request': made.request, 'backtest-result': made.result,
              [`backtest-bars-${made.ticker.toLowerCase()}`]: bars };
  }, 60000);
  const serve = () => {
    asked = [];
    const index = { finished_at: null, as_of: AS_OF, files: Object.fromEntries(Object.keys(files).map(n => [n, { sha256: `sha-${n}` }])) };
    vi.stubGlobal('fetch', async (url: string) => {
      asked.push(url);
      if (url === '/api/v1/examples/backtest/index') return Response.json(index);
      const m = /^\/api\/v1\/examples\/backtest\/file\/([a-z0-9-]+)\?sha=(.+)$/.exec(url);
      if (m && m[1] in files && m[2] === `sha-${m[1]}`) return Response.json(files[m[1]]);
      return Response.json({ error: { code: 'NOT_HERE', message: url } }, { status: 404 });
    });
    return exampleApi();
  };
  afterEach(() => { vi.unstubAllGlobals() });
  /** the page's request with the page's own card ids (other than the stored ones, as in the browser) */
  const pageRequest = (): BacktestRequest => {
    const q = structuredClone(made.request);
    q.entry.conditions.forEach((c, k) => { c.id = `page${k}` });
    q.exit.signals.conditions.forEach((c, k) => { c.id = `pagex${k}` });
    return q;
  };

  it('answers the page\'s request with the stored run, the run naming the page\'s cards', async () => {
    const api = serve();
    expect(await api.catalog()).toEqual(made.catalog);
    expect(await api.bars(made.ticker, {})).toEqual(bars);
    const q = pageRequest();
    expect(await api.submit(q)).toEqual({ request_id: 'example' });
    expect((await api.status('example')).state).toBe('FINISHED');
    const r = await api.result('example');
    const ids = new Set([...q.entry.conditions, ...q.exit.signals.conditions].map(c => c.id));
    expect(r.events.conditions?.length).toBeGreaterThan(0);
    expect(r.events.conditions!.every(c => ids.has(c.condition_id))).toBe(true);
    // the stored run as it is, but every condition_id (the tracks, the sensitivity grid's card) the page's card's id
    const theirs = [...made.request.entry.conditions, ...made.request.exit.signals.conditions].map(c => c.id);
    const mine = [...q.entry.conditions, ...q.exit.signals.conditions].map(c => c.id);
    const renamed = JSON.parse(JSON.stringify(made.result), (k, v) => k === 'condition_id' && theirs.includes(v) ? mine[theirs.indexOf(v)] : v);
    expect(r).toEqual(renamed);
    expect(JSON.stringify(r)).not.toMatch(new RegExp(`"condition_id":"(${theirs.join('|')})"`));
    const ev = await api.events('example', made.ticker);
    expect(ev.conditions.map(c => c.condition_id).sort()).toEqual([...ids].filter(i => !i.startsWith('pagex')).sort());
    // each file once, and only the example's routes
    expect(asked.every(u => u.startsWith('/api/v1/examples/backtest/'))).toBe(true);
    expect(asked.filter(u => u.includes('/file/backtest-result')).length).toBe(1);
  });

  it('refuses any other request, another ticker and every other kind of call', async () => {
    const api = serve();
    await api.catalog();
    for (const change of [
      (q: BacktestRequest) => { q.period.from = '2025-11-03' },
      (q: BacktestRequest) => { q.entry.conditions[0].enabled = false },
      (q: BacktestRequest) => { q.single!.ticker = 'BBCA' },
      (q: BacktestRequest) => { q.robustness.monte_carlo_runs = 500 },
    ]) {
      const q = pageRequest(); change(q);
      await expect(api.submit(q)).rejects.toMatchObject({ code: 'EXAMPLE', status: 403 });
    }
    await expect(api.bars('BBCA', {})).rejects.toMatchObject({ code: 'EXAMPLE', status: 403 });
    await expect(api.screenerCatalog()).rejects.toMatchObject({ code: 'EXAMPLE' });
    await expect(api.signalsPreview(made.request as never)).rejects.toMatchObject({ code: 'EXAMPLE' });
    await expect(api.closes('IHSG', [])).rejects.toMatchObject({ code: 'EXAMPLE' });
    expect(asked.every(u => u.startsWith('/api/v1/examples/backtest/'))).toBe(true);
  });

  it('holds the page\'s default cards ready, with the run\'s own tracks as their series, and no other card', async () => {
    const api = serve();
    defaultRequestOn(made.catalog);                     // S.conds: the page's default cards, as the page holds them
    await api.catalog();
    await api.bars(made.ticker, {});
    const on = S.conds.filter(c => c.on) as Card[];
    expect(on.length).toBe(made.request.entry.conditions.length);
    const tracks = new Map((made.result.events.conditions ?? []).map(c => [c.condition_id, c.track]));
    for (const card of on) {
      expect(api.ready(card)).toBe(true);
      const id = made.request.entry.conditions.find(c => JSON.stringify({ ...c, id: '' }) === JSON.stringify({ ...toWire(card), id: '' }))?.id;
      const track = tracks.get(id!)!, at = new Map(made.result.dates.map((d, k) => [d, k]));
      const expected = Uint8Array.from(bars.dates, d => {
        const k = at.get(d);
        for (let j = 0; k !== undefined && j + 1 < track.runs.length; j += 2) if (k >= track.runs[j] && k <= track.runs[j + 1]) return 1;
        return 0;
      });
      expect(api.conditionSeries(made.ticker, card)).toEqual(expected);
      expect(api.ready({ ...card, on: false } as Card)).toBe(false);
    }
    expect(api.conditionSeries('BBCA', on[0])).toBeNull();
  });
});
