/* C-P1S independent check (EXEC-MU-ACCOUNTS, ultracode re-check of Phases 0-3b; CONTRACT.md section 12, ERRORS M473;
   user 2026-11-16, EXEC.md EXEC-MU-ACCOUNTS: "Iya, bersihkan pada saat logout", which names `ml.assets.v1`, the series
   added to the chart, as account data cleared at sign-out).

   The Terminal keeps the fold and the height of each added series' Flow Timeline pane in localStorage under a key that
   names the series' ticker: `ml.assets.flow.collapsed.<TICKER>` (written for every added series when its pane is made,
   terminal/src/app/assets.ts setCollapsed) and `ml.assets.flow.h.<TICKER>` (assets.ts setH). The registry
   (shared/edge-session.ts STORAGE) classes the prefix `ml.assets.flow.` as `browser`, so sign-out and a change of user
   keep them, and nothing ever removes them (not even removing the series). The next person on the browser reads which
   tickers the previous account compared from the key names, although the account's own list (`ml.assets.v1`) is
   cleared. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearUserState, LAST_LOGIN_KEY, noteIdentity } from '../../../shared/edge-session';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage(); vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage());
  vi.stubGlobal('indexedDB', { deleteDatabase:() => { const r: any = {}; setTimeout(() => r.onsuccess?.()); return r } });
});
afterEach(() => vi.unstubAllGlobals());

/** what account A's Terminal leaves in localStorage after adding BBRI and TLKM as series (assets.ts) */
function accountAddedTwoSeries() {
  local.setItem(LAST_LOGIN_KEY, 'owner:u_aaaaaaaaaaaaaaaaaaaaaaaa');
  local.setItem('ml.assets.v1', JSON.stringify([{ ticker:'BBRI' }, { ticker:'TLKM' }]));
  local.setItem('ml.assets.flow.collapsed.BBRI', '0');            // setCollapsed(pane.collapsed) when the pane is made
  local.setItem('ml.assets.flow.collapsed.TLKM', '1');
  local.setItem('ml.assets.flow.h.TLKM', '180');                    // setH after a drag of the pane's grip
  local.setItem('ml.stats.w', '300');                               // a real browser setting: stays
}
const naming = (tickers: string[]) => [...local.m.keys()].filter(k => tickers.some(t => k.endsWith('.' + t)));

describe('the series an account added leave nothing behind (contract 12, M473)', () => {
  it('sign-out removes every key that names an added series', async () => {
    accountAddedTwoSeries();
    await clearUserState({ signOut:true });
    expect(local.getItem('ml.assets.v1')).toBeNull();                // the account's list goes
    expect(local.getItem('ml.stats.w')).toBe('300');                  // a browser setting stays
    expect(naming(['BBRI', 'TLKM'])).toEqual([]);                     // ...and so must the keys that name its tickers
  });
  it('another account signing in on the browser inherits no key that names the previous account\'s series', () => {
    accountAddedTwoSeries();
    expect(noteIdentity('bob_b', 'u_bbbbbbbbbbbbbbbbbbbbbbbb').changed).toBe(true);
    expect(local.getItem('ml.assets.v1')).toBeNull();
    expect(naming(['BBRI', 'TLKM'])).toEqual([]);
  });
});
