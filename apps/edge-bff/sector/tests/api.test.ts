/* EXEC-SECTOR-ANALYSIS S4: the data path (src/api.ts, src/loader.ts) on the made-up files in the contract's shapes, and the
   example mode (decision J). */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { FILE, SectorError, cached, example, live } from '../src/api.ts';
import { dayDates, open, stocksFile } from '../src/loader.ts';
import { exampleLocked, readHash } from '../src/app.ts';
import { cloneState, DEFAULT_STATE } from '../src/ctx.ts';
import type { SectorApi } from '../src/types.ts';
// @ts-ignore: a plain module of the tests
import { makeFiles } from './fixture/make.mjs';

const F = makeFiles();
function fakeApi(files = F.files, index = F.index) {
  const calls: string[] = [];
  const api: SectorApi = {
    index: async () => { calls.push('index'); return index },
    file: async <T>(name: string, sha: string) => { calls.push(name); expect(sha).toBe(index.files[name].sha256); return files[name] as T },
  };
  return { api, calls };
}

describe('the files in the contract\'s shapes (CONTRACT section 3; made-up fixtures)', () => {
  it('meta, series, day and stock files carry exactly the contract\'s fields', () => {
    const meta = F.files['sector-meta'], series = F.files['sector-series'], day = F.files[`sector-day-${meta.dates.at(-1)}`];
    expect(Object.keys(meta).sort()).toEqual(['benchmarks', 'breadth_through', 'dates', 'industries', 'market', 'periods', 'prices_through', 'schema', 'sectors', 'stocks', 'weight_basis', 'weight_label']);
    expect(Object.keys(meta.stocks).sort()).toEqual(['industry', 'name', 'sector', 'ticker']);
    expect(meta.dates.length).toBe(20); expect(meta.sectors.length).toBe(11);
    expect(Object.keys(series).sort()).toEqual(['breadth', 'dates', 'index', 'industry', 'schema', 'sector']);
    expect(series.dates.length).toBe(300);
    expect(Object.keys(series.breadth.IHSG).sort()).toEqual(['a200', 'a50', 'adv', 'dec', 'members', 'n200', 'n50', 'unch']);
    expect(Object.keys(series.industry[meta.industries[0].name]).sort()).toEqual(['level', 'members']);
    expect(Object.keys(day.stocks).sort()).toEqual(['above_ema200', 'above_ema50', 'close', 'd_ema200', 'd_ema50', 'days200', 'days50', 'i', 'r1d', 'r1m', 'r3m', 'r5d', 'since200', 'since50', 'volume', 'weight']);
    const st = F.files['sector-stocks-idxfinance'];
    expect(Object.keys(st).sort()).toEqual(['close', 'dates', 'schema', 'sector', 'ticker']);
    for (const name of Object.keys(F.files)) expect(name).toMatch(/^[a-z0-9][a-z0-9_-]{0,31}$/);   // terminal-api's name rule (3.4 amended)
  });
});

describe('the loader (CONTRACT 5 "Downloads")', () => {
  it('reads the index, then meta and series, then the newest day; never a stock file', async () => {
    const { api, calls } = fakeApi(), o = await open(api), meta = F.files['sector-meta'];
    expect(calls[0]).toBe('index');
    expect(calls.slice(1, 3).sort()).toEqual(['sector-meta', 'sector-series']);
    expect(calls[3]).toBe(`sector-day-${meta.dates.at(-1)}`);
    expect(calls.length).toBe(4); expect(calls.some(c => c.startsWith('sector-stocks'))).toBe(false);
    expect(o.day!.date).toBe(meta.dates.at(-1));
  });
  it('opens a chosen date; the picker lists the dates the index has a day file for', async () => {
    const meta = F.files['sector-meta'], idx = { ...F.index, files: { ...F.index.files } };
    delete idx.files[`sector-day-${meta.dates[3]}`];
    expect(dayDates(meta, idx)).toHaveLength(19);
    const { api } = fakeApi(F.files, idx), o = await open(api, meta.dates[0]);
    expect(o.day!.date).toBe(meta.dates[0]);
  });
  it('names a sector\'s stock file by its index ticker lowercased (CONTRACT 3.4 as amended)', () => {
    expect(FILE.stocks('IDXFINANCE')).toBe('sector-stocks-idxfinance');
    expect(stocksFile(F.files['sector-meta'], 'Financials')).toBe('sector-stocks-idxfinance');
    expect(stocksFile(F.files['sector-meta'], 'Other')).toBeNull();
  });
  it('refuses a missing file with a message that says what to do', async () => {
    const idx = { finished_at: null, files: {} };
    await expect(open(fakeApi(F.files, idx as any).api)).rejects.toThrow(SectorError);
  });
  it('keeps one copy of a file per sha', async () => {
    const { api, calls } = fakeApi(), c = cached(api), sha = F.index.files['sector-meta'].sha256;
    await Promise.all([c.file('sector-meta', sha), c.file('sector-meta', sha)]);
    expect(calls.filter(x => x === 'sector-meta')).toHaveLength(1);
  });
});

describe('the gateway paths and their refusals', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('asks /api/v1/sector, or /api/v1/examples/sector in the example, with the session cookie', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', async (u: string, o: any) => { urls.push(u); expect(o.credentials).toBe('same-origin'); return new Response(JSON.stringify({ files: {} }), { status: 200 }) });
    await live.index(); await example.file('sector-meta', 'ab'.repeat(32));
    expect(urls).toEqual(['/api/v1/sector/index', `/api/v1/examples/sector/file/sector-meta?sha=${'ab'.repeat(32)}`]);
  });
  it('a signed-out session and an unknown refusal read as plain words', async () => {
    vi.stubGlobal('fetch', async () => new Response('{}', { status: 401 }));
    await expect(live.index()).rejects.toMatchObject({ code: 'SIGNED_OUT' });
    vi.stubGlobal('fetch', async () => new Response(JSON.stringify({ error: { code: 'X', message: 'Try later.' } }), { status: 503 }));
    await expect(live.index()).rejects.toMatchObject({ code: 'X', message: 'Try later.' });
  });
});

describe('the example mode (decision J: the five tabs switch, every other control asks for the box)', () => {
  const el = (match: string[]) => ({ closest: (sel: string) => (sel.split(',').map(s => s.trim()).some(s => match.includes(s)) ? {} : null) }) as unknown as Element;
  it('locks every control but the tabs', () => {
    expect(exampleLocked(el(['button']))).toBe(true);                        // a period, a sort header, Open in Terminal
    expect(exampleLocked(el(['[data-n]']))).toBe(true);                       // a sector row
    expect(exampleLocked(el(['.fwx', 'button']))).toBe(true);                 // expand
    expect(exampleLocked(el(['button', '[role=tab]', '#tabs [role=tab]']))).toBe(false);
    expect(exampleLocked(el([]))).toBe(false);                                // text, a card's blank part
  });
  it('the address keeps the choices and drops a value of the wrong kind', () => {
    const S = cloneState(DEFAULT_STATE);
    readHash(S, '#' + encodeURIComponent(JSON.stringify({ tab: 'pm', rcW: 'YTD', rsN: 'x', pin: 'Energy', rcIh: false, dS: [['a', 1]], nope: 1 })));
    expect(S.tab).toBe('pm'); expect(S.rcW).toBe('YTD'); expect(S.rsN).toBe(5); expect(S.pin).toBe('Energy'); expect(S.rcIh).toBe(false); expect(S.dS).toEqual([]);
    readHash(S, '#%7Bbad'); expect(S.tab).toBe('pm');
  });
});
