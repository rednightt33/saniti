/* C1 adversarial security check of EXEC-MU-ACCOUNTS Phase 0 (M468, M471, M473): failing tests for the findings (no
   fix here). Threat: a shared browser where account A has a page open while account B signs in in another tab (the
   session cookie is per browser, so A's open tab now carries B's cookie). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { edge, LAST_LOGIN_KEY, sessionClient } from '../../../shared/edge-session';
import { accountDrawings } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => { local = memoryStorage(); vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage()) });
afterEach(() => vi.unstubAllGlobals());

describe('C1: a change of account between a page\'s session read and its write', () => {
  it('a CSRF repeat never sends the first account\'s write under another account\'s session', async () => {
    /* edge-session.ts send(): on 403 CSRF_INVALID it reads the session again and repeats the write with whatever
       session comes back. After B signs in on the same browser, A's open tab gets CSRF_INVALID (A's token, B's
       cookie), re-reads the session (B's) and repeats A's write (A's layout, drawings, watchlist change) into B's
       account. The repeat must only happen when the session read again is the same login. */
    let n = 0; const writes: string[] = [];
    const f = (async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/auth/session') { n++; return answer(200, n === 1 ? { login:'alice', csrf_token:'tA' } : { login:'bob', csrf_token:'tB' }) }
      const t = (init?.headers as any)?.['X-CSRF-Token'];
      writes.push(t);
      return t === 'tB' ? answer(200, { ok:true }) : answer(403, { error:{ code:'CSRF_INVALID' } });
    }) as unknown as typeof fetch;
    const c = sessionClient(f);
    await c.session();                                              // the page opened as alice
    await c.send('/api/v1/terminal/layouts/lay_1', { method:'PUT', body:'{"state":"alice"}' }).catch(() => null);
    expect(writes).not.toContain('tB');                             // alice's body was written into bob's account
  });

  it('a drawing copy kept as the page leaves is never stamped with another account\'s login', async () => {
    /* drawingsApi.ts signedIn() = edge.current?.login || lastLogin(). When B signs in in another tab, the shell's
       noteLogin() writes B into edge-last-login and broadcasts 'cleared', which invalidates this page's session
       (edge.current = null). A's pending drawing is then stamped with B's login on pagehide, and B's next Terminal
       load merges it into B's account: M468 again, through the fallback. */
    const handlers: Record<string, () => void> = {};
    vi.stubGlobal('window', { addEventListener:(t: string, fn: () => void) => { handlers[t] = fn } });
    local.setItem(LAST_LOGIN_KEY, 'alice');
    vi.stubGlobal('fetch', async (url: string) => url === '/api/v1/auth/session'
      ? answer(200, { login:'alice', csrf_token:'tA' }) : answer(200, { sets:[] }));
    const d = accountDrawings(() => {}, 60_000);
    await d.load('BBCA', 'chart', 'ml.drawings.BBCA');               // edge.current is alice
    d.save('BBCA', 'chart', '[{"id":"alice-line"}]', 'ml.drawings.BBCA');   // waiting for its timer
    local.setItem(LAST_LOGIN_KEY, 'bob');                            // bob signs in in the shell (another tab)
    edge.invalidate();                                               // the 'cleared' broadcast reaches this page
    vi.stubGlobal('fetch', async () => answer(200, {}));
    handlers.pagehide?.();
    const kept = local.getItem('ml.drawings.BBCA');
    expect(kept === null ? null : JSON.parse(kept).owner).not.toBe('bob');
  });
});
