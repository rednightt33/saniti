/* C2 isolation check (EXEC-MU-ACCOUNTS Phase 0; CONTRACT.md sections 12 and 13.8; M468, M471, M473): a page that is
   already open when the user of this browser changes (A signs out in another tab and B signs in; the session cookie is
   the browser's, so the open page's next call carries B's session) still holds A's state in memory. The shell moves the
   last-login mark to B, so the page's own check (checkUser: the session's login against that mark) sees no change.

   1. shared/edge-session.ts send(): a write of the page answers 403 CSRF_INVALID (A's token, B's cookie); the client
      reads the session again (now B) and repeats the write with B's token, so A's in-memory change lands in B's account.
   2. terminal/src/data/drawingsApi.ts: a drawing change of A that cannot reach the account is kept in this browser
      stamped with signedIn() = edge.current?.login || lastLogin(); after the session was dropped (the 'cleared'
      broadcast, a 401) that is B's mark, so B's next load merges A's drawings into B's account (M468 defeated). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { edge, LAST_LOGIN_KEY, sessionClient } from '../../../shared/edge-session';
import { accountDrawings, ownCopy } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage();
  vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage());
  vi.stubGlobal('window', { addEventListener() {} });
});
afterEach(() => { vi.unstubAllGlobals(); edge.invalidate() });

describe('a page open while the user of the browser changes', () => {
  it('never repeats a write of the first user under the second user\'s session (CSRF repeat)', async () => {
    let user = 'alice';                                    // whose session cookie the browser holds now
    const writes: string[] = [];
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/auth/session') return answer(200, { login:user, csrf_token:`csrf-${user}` });
      const token = (init?.headers as any)?.['X-CSRF-Token'];
      if (token !== `csrf-${user}`) return answer(403, { error:{ code:'CSRF_INVALID' } });
      writes.push(`${user}: ${init?.body}`);
      return answer(200, { ok:true });
    }) as unknown as typeof fetch;
    const page = sessionClient(f);
    expect((await page.session()).login).toBe('alice');   // the page was opened by alice and holds her state
    user = 'bob';                                          // alice signs out in another tab, bob signs in
    local.setItem(LAST_LOGIN_KEY, 'bob');
    await page.send('/api/v1/terminal/drawings/BBCA/chart', { method:'PUT', body:'{"drawings":["alice"]}' });
    expect(writes).toEqual([]);                            // alice's change must not reach bob's account
  });

  it('never stamps the first user\'s unsaved drawings with the second user\'s login', async () => {
    const f = vi.fn(async (url: string) => {
      if (url === '/api/v1/auth/session') return answer(200, { login:'alice', csrf_token:'csrf-alice' });
      throw new TypeError('offline');                      // the account cannot be reached: the copy is kept here
    });
    vi.stubGlobal('fetch', f);
    local.setItem(LAST_LOGIN_KEY, 'alice');
    const drawings = accountDrawings(() => {}, 0);
    expect((await edge.session()).login).toBe('alice');
    drawings.save('BBCA', 'chart', '[{"id":"a1"}]', 'ml.drawings.BBCA');   // alice draws; the write waits a moment
    edge.invalidate();                                     // the 'cleared' broadcast of alice's sign-out in another tab
    local.setItem(LAST_LOGIN_KEY, 'bob');                  // bob signs in there
    await vi.waitFor(() => expect(local.getItem('ml.drawings.BBCA')).not.toBeNull());
    expect(ownCopy(local.getItem('ml.drawings.BBCA'), 'bob')).toBeNull();
  });
});
