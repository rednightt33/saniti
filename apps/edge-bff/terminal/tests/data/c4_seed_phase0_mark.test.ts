/* Independent check of 331aec25 (ERRORS M478 C3 B1, access.seed), 2026-11-16.

   Case: a browser user #1 last used while Phase 0 ran (deployed on dev 2026-11-16). Phase 0's shell wrote the last-login
   mark as the bare login (noteLogin(session.login): 'edge', EDGE_LOGIN), since its session answer had no owner_key. Only
   one account existed then, so a mark of the login form can only be user #1's. If that browser is next opened after the
   switch goes on, the session answer is login 'admin_1' (accounts.py seed_identity: 'edge' is a reserved username),
   owner_key 'edge-private', access.seed true. noteIdentity then sees was='edge' != 'admin_1' and no upgrade (the upgrade
   only matches the same login), so it clears user #1's state; seed is consulted only when there is no mark at all.
   checkUser (an app page opened alone, via its session read) clears it the same way. Expected: user #1's state and its Phase 0 drawing stamps
   are kept and moved to the owner key, as they are with the switch off (login 'edge' matches the mark). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LAST_LOGIN_KEY, noteIdentity, sessionClient } from '../../../shared/edge-session';

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

describe('a Phase 0 mark (the bare login) first met with the switch on', () => {
  const phase0 = () => {
    local.setItem(LAST_LOGIN_KEY, 'edge');                                   // Phase 0 noteLogin('edge')
    local.setItem('ml.my', '[{"row":"rsi"}]');
    local.setItem('ml.drawings.BBCA', JSON.stringify({ owner:'edge', drawings:[{ id:'d1' }] }));   // M468 stamp, Phase 0
  };
  it('the shell keeps user #1\'s state (seed) and moves its stamps', () => {
    phase0();
    const noted = noteIdentity('admin_1', 'edge-private', { seed:true });
    expect(local.getItem('ml.my')).toBe('[{"row":"rsi"}]');
    expect(noted).toEqual({ changed:false, same:true });
    expect(JSON.parse(local.getItem('ml.drawings.BBCA') || 'null')?.owner).toBe('owner:edge-private');
    expect(local.getItem(LAST_LOGIN_KEY)).toBe('owner:edge-private');
  });
  it('an app page opened alone (its session read, checkUser) does not clear it either', async () => {
    phase0();
    const answer = { authenticated:true, login:'admin_1', owner_key:'edge-private', csrf_token:'t', username:'admin_1',
      access:{ role:'admin', status:'active', mfa_ok:true, owner_key:'edge-private', seed:true, next:null, version:'db-x' } };
    const f = (async () => new Response(JSON.stringify(answer), { status:200, headers:{ 'Content-Type':'application/json' } })) as typeof fetch;
    await sessionClient(f).session();
    expect(local.getItem('ml.my')).toBe('[{"row":"rsi"}]');
  });
  it('control: a registered account on that browser still clears it', () => {
    phase0();
    expect(noteIdentity('bob_b', 'u_0123456789abcdef01234567', { seed:false }).changed).toBe(true);
    expect(local.getItem('ml.my')).toBeNull();
  });
});
