/* C3 Phase 1 conformance check (EXEC-MU-ACCOUNTS; user decision: nothing visible with EDGE_MULTIUSER off; option A:
   sign-out clears, and Phase 1 restores the account's preferences on any device; "Isi pertama diunggah dari browser
   saat sign-in pertama, bila datanya masih ada").

   A browser where EDGE was last used before the Phase 0 deploy has the current user's browser-only data (My metrics
   `ml.my`, favourite indicators `ml.ind.favs`, ...) but no last-login mark. With the switch off the only principal is
   user #1 (owner key EDGE_OWNER = edge-private, the seed), so that data can only be user #1's. Since the C2 Phase 1 #3
   fix, noteIdentity clears it ("a browser with no mark and account state clears it instead of adopting it") before the
   first upload, so the data the Phase 1 sync was added to keep is deleted on the first load after the deploy.
   Expected: the state of user #1 on such a browser is kept and uploaded once (same: true). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LAST_LOGIN_KEY, noteIdentity } from '../../../shared/edge-session';

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

describe('the first load after the Phase 1 deploy, switch off, on a browser without a mark', () => {
  it('keeps user #1\'s browser-only data so the sync can upload it', () => {
    local.setItem('ml.my', '[{"row":"rsi","card":{}}]');          // My metrics: no server copy before Phase 1
    local.setItem('ml.ind.favs', '["I01"]');
    expect(local.getItem(LAST_LOGIN_KEY)).toBeNull();
    // the switch-off session answer: login EDGE_LOGIN, owner_key EDGE_OWNER (user #1, the seed)
    const noted = noteIdentity('edge', 'edge-private');
    expect(local.getItem('ml.my')).toBe('[{"row":"rsi","card":{}}]');
    expect(local.getItem('ml.ind.favs')).toBe('["I01"]');
    expect(noted.same).toBe(true);                                 // so edge-client.js uploads it (uploadLocal)
  });
});
