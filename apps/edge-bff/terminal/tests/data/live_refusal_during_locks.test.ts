/* Integration of the fix round (fix-int2; ERRORS M490): live.ts starts the reference reads, then waits for the plan's
   locks (lockRules, track guest), which for a principal without `*` read the catalog route. A reference read refused
   meanwhile (here the ticker list, 503 TERMINAL_UNAVAILABLE) had no handler yet: the browser reported an unhandled
   rejection (Playwright `pageerror` in tests/test_fix_plans.py and test_c2web_browser.py) although liveData later threw
   the same refusal to its caller, which shows it. Every promise started before an await has its handler at once; the
   refusal reaches the caller once, as a TerminalError with the contract's words. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { liveData, TerminalError } from '../../src/data/live';

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
const ACCESS = { plan:'free', role:'user', status:'active', mfa_ok:true, seed:false, owner_key:'u_1', next:null, version:'db-0123456789ab',
  capabilities:['terminal.view'], limits:{ 'terminal.tickers':['BBCA'] } };
const UNAVAILABLE = { error:{ code:'TERMINAL_UNAVAILABLE', message:'Market data cannot be reached right now. Wait a moment, then try again.', details:{} } };

/* the test runner's process (node): an unhandled rejection is reported to it; typed here, the page's tsconfig has no node types */
const proc = (globalThis as unknown as { process: { on(e: string, f: (r: unknown) => void): void; off(e: string, f: (r: unknown) => void): void } }).process;
const unhandled: unknown[] = [];
const onUnhandled = (reason: unknown) => { unhandled.push(reason) };
beforeEach(() => { unhandled.length = 0; proc.on('unhandledRejection', onUnhandled) });
afterEach(() => { proc.off('unhandledRejection', onUnhandled); vi.unstubAllGlobals() });

describe('live.ts: a reference read refused while the plan\'s locks are read', () => {
  it('reaches the caller once, as a TerminalError, and is never an unhandled rejection', async () => {
    let release!: () => void; const gate = new Promise<void>(r => { release = r });
    vi.stubGlobal('fetch', async (url: string) => {
      const u = String(url);
      if (u === '/api/v1/auth/session') return json(200, { authenticated:true, login:'paula', owner_key:'u_1', csrf_token:'t', access:ACCESS });
      if (u.startsWith('/api/v1/catalog/')) { await gate; return json(200, { kind:u.split('/').pop(), entries:[] }) }
      if (u.startsWith('/api/terminal/v1/')) return json(503, UNAVAILABLE);
      return json(404, {});
    });
    const page = liveData('BBCA');
    page.catch(() => {});                                     // the caller's handler, as main.ts has
    await new Promise(r => setTimeout(r, 50));                // the reference reads are refused while the catalog waits
    release();
    const e = await page.then(() => null, (err: unknown) => err);
    expect(e).toBeInstanceOf(TerminalError);
    expect((e as Error).message).toBe(UNAVAILABLE.error.message);
    await new Promise(r => setTimeout(r, 50));
    expect(unhandled).toEqual([]);
  });
});
