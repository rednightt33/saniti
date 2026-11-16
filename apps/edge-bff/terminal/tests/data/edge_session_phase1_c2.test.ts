/* C2 Phase 1 isolation check (EXEC-MU-ACCOUNTS; CONTRACT.md sections 12 and 13.8; M468, M473): a browser with no
   last-login mark (EDGE last used there before the Phase 0 deploy, by the one account EDGE had) adopts the first
   identity that signs in and clears nothing (shared/edge-session.ts noteIdentity: "A browser with no mark adopts the
   identity"). With accounts, that first identity may be another user: the unstamped drawings copy left by user #1
   (a bare list, the pre-M468 form) then joins that user (ownCopy accepts a bare list for isLastLogin), and the Terminal
   merges it into that user's account on the next load (drawingsApi.ts load -> write). An unstamped copy can belong to
   anyone; it must never be merged into an account named by its owner key. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { identityOf, LAST_LOGIN_KEY, noteIdentity, sessionClient } from '../../../shared/edge-session';
import { ownCopy } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage();
  vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage());
  vi.stubGlobal('indexedDB', { deleteDatabase:() => { const r: any = {}; setTimeout(() => r.onsuccess?.()); return r } });
});
afterEach(() => vi.unstubAllGlobals());

describe('a browser without a mark, first signed in by another account', () => {
  it('never hands user #1\'s unstamped drawings to the account that signs in first', () => {
    local.setItem('ml.drawings.BBCA', '[{"id":"user1-line"}]');        // left before Phase 0 by user #1, no stamp
    expect(local.getItem(LAST_LOGIN_KEY)).toBeNull();
    noteIdentity('bob_b', 'u_0123456789abcdef01234567');                 // a registered user signs in on this browser
    const bob = identityOf('bob_b', 'u_0123456789abcdef01234567');
    expect(ownCopy(local.getItem('ml.drawings.BBCA'), bob)).toBeNull();
  });
});

/* The shell's 'cleared' handler (static/edge-client.js onCleared -> stopPrefs) calls prefs.stop() and edge.forget(),
   which empties the page identity. A preference write already on the wire with the previous account's token gets 403
   CSRF_INVALID (the cookie is now the new account's); send() reads the session again and, with no identity left to
   compare, adopts the new account and repeats the write: the previous account's value lands in the new account. */
describe('a preference write in flight while another account signs in', () => {
  it('is never repeated under the new account after the shell forgets the identity', async () => {
    const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
    let user = 'alice', ownerKey = 'u_aaaaaaaaaaaaaaaaaaaaaaaa';
    const stored: string[] = [];
    let client: ReturnType<typeof sessionClient>;
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/auth/session') return answer(200, { login:user, owner_key:ownerKey, csrf_token:`csrf-${user}` });
      const token = (init?.headers as any)?.['X-CSRF-Token'];
      if (token !== `csrf-${user}`) {
        client.forget();                    // the 'cleared' broadcast reaches the shell while the write is on the wire
        return answer(403, { error:{ code:'CSRF_INVALID' } });
      }
      stored.push(`${user}: ${init?.body}`);
      return answer(200, { key:'ml.tf', value:'W', version:1 });
    }) as unknown as typeof fetch;
    client = sessionClient(f);
    expect((await client.session()).login).toBe('alice');
    user = 'bob_b'; ownerKey = 'u_bbbbbbbbbbbbbbbbbbbbbbbb';   // bob signs in in another tab: the cookie is his
    await client.send('/api/v1/preferences/ml.tf', { method:'PUT', headers:{ 'Content-Type':'application/json' },
      body:JSON.stringify({ value:'alice-value', version:null }) });
    expect(stored).toEqual([]);
  });
});
