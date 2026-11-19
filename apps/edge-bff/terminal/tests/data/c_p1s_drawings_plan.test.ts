/* C-P1S independent check (EXEC-MU-ACCOUNTS, ultracode re-check of Phases 0-3b): the Terminal's drawings (M468's
   offline copy, Phase 0/1) against Phase 3a's gate `terminal.drawings` (CONTRACT.md 8b; section 9: the free plan has
   "No add-indicator, drawing, layout, compare or asset capability") and AGENTS.md "Gates and evidence" (d): a refusal
   names where the problem is and how to fix it.

   terminal/src/data/drawingsApi.ts listOf() maps every failure of GET /api/v1/terminal/drawings to null (`() => null`),
   the "account cannot be reached" case. A plan refusal (403 CAPABILITY_REQUIRED) is read the same way: load() says
   "could not be saved to your EDGE account just now ... move to the account when it can be reached" and save() keeps the
   drawing in this browser (keepCopy), where every later load shows it again. So a principal without terminal.drawings
   draws and keeps drawings, is told the connection failed, and never sees why (its plan). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { edge } from '../../../shared/edge-session';
import { accountDrawings } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
const REFUSED = { error:{ code:'CAPABILITY_REQUIRED', message:'Drawings is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.',
  details:{ capability:'terminal.drawings', display_name:'Drawings' } } };
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage();
  vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage());
  vi.stubGlobal('window', { addEventListener() {} });
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/v1/auth/session') return answer(200, { login:'free_user', owner_key:'u_cccccccccccccccccccccccc', csrf_token:'csrf' });
    return answer(403, REFUSED);                           // every drawings route: the plan lacks terminal.drawings
  }));
});
afterEach(() => { vi.unstubAllGlobals(); edge.invalidate() });

describe('a plan without terminal.drawings', () => {
  it('is told its plan does not include drawings, and no drawing is kept for it in the browser', async () => {
    const said: string[] = [];
    const drawings = accountDrawings(t => { said.push(t) }, 0);
    await edge.session();
    await drawings.load('BBCA', 'chart', 'ml.drawings.BBCA');
    drawings.save('BBCA', 'chart', '[{"id":"d1","kind":"trend-line"}]', 'ml.drawings.BBCA');
    await new Promise(r => setTimeout(r, 30));
    expect(said.some(t => /could not be saved to your EDGE account just now/.test(t)), `a plan refusal worded as a connection failure: ${JSON.stringify(said)}`).toBe(false);
    expect(said.some(t => /not part of your EDGE plan/.test(t)), `the refusal's own words never reach the page: ${JSON.stringify(said)}`).toBe(true);
    expect(local.getItem('ml.drawings.BBCA'), 'the refused drawing is kept in the browser and shown on every load').toBeNull();
  });
});
