/* EXEC-MU-ACCOUNTS Phase 0: the shared session module (apps/edge-bff/shared/edge-session.ts) that every page uses.
   M471: the error contract in both shapes, the CSRF repeat only on CSRF_INVALID, a plan refusal never a retry or a
   sign-out; M473: the user keys cleared on sign-out and on a change of user; M468: a drawing copy only for its login. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { classify, clearUserState, checkUser, LAST_LOGIN_KEY, noteLogin, onReset, readError, sessionClient, accessText, isAccessRefusal }
  from '../../../shared/edge-session';
import { ownCopy, stampCopy } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
let local: ReturnType<typeof memoryStorage>, session: ReturnType<typeof memoryStorage>, deleted: string[];
beforeEach(() => {
  local = memoryStorage(); session = memoryStorage(); deleted = [];
  vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', session);
  vi.stubGlobal('indexedDB', { deleteDatabase:(n: string) => { deleted.push(n); const r: any = {}; setTimeout(() => r.onsuccess?.()); return r } });
});
afterEach(() => vi.unstubAllGlobals());

describe('the error contract (M471)', () => {
  it('reads the new shape with its code, message, details and Retry-After', () => {
    const e = readError(403, { error:{ code:'CAPABILITY_REQUIRED', message:'', details:{ capability:'radar.view', display_name:'Radar' } } }, '30');
    expect([e.kind, e.code, e.retryAfter, e.legacy]).toEqual(['upgrade', 'CAPABILITY_REQUIRED', 30, false]);
    expect(isAccessRefusal(e)).toBe(true);
    expect(accessText(e)).toContain('Radar is not part of your EDGE plan');
  });
  it('reads the old FastAPI {"detail"} of a 401 and a 403 (the rollout)', () => {
    expect(readError(401, { detail:'Authentication required' })).toMatchObject({ kind:'signin', code:'UNAUTHENTICATED', legacy:true });
    expect(readError(403, { detail:'Invalid CSRF token' })).toMatchObject({ kind:'csrf', code:'CSRF_INVALID', legacy:true });
    expect(readError(403, { detail:'Something else' })).toMatchObject({ kind:'other', code:'FORBIDDEN' });
  });
  it('names a limit with its wait and the server message first', () => {
    expect(readError(429, { error:{ code:'LIMIT_REACHED', details:{ retry_after_s:12 } } }).retryAfter).toBe(12);
    expect(accessText(readError(429, { error:{ code:'LIMIT_REACHED', message:'Batas harian tercapai.' } }))).toBe('Batas harian tercapai.');
    expect(readError(429, { error:{ code:'SIGN_IN_RATE_LIMIT' } }, '5').kind).toBe('wait');
  });
});

describe('the session and CSRF (M471)', () => {
  const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
  function server(refusals: Response[]) {
    const calls: string[] = []; let sessions = 0;
    const f = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(`${init?.method || 'GET'} ${url} ${(init?.headers as any)?.['X-CSRF-Token'] ?? ''}`);
      if (url === '/api/v1/auth/session') { sessions++; return answer(200, { login:'Owner', csrf_token:`t${sessions}` }) }
      return refusals.shift() || answer(200, { ok:true });
    });
    return { f: f as unknown as typeof fetch, calls };
  }
  it('repeats a write once after a 403 CSRF_INVALID, with a new token', async () => {
    const s = server([answer(403, { error:{ code:'CSRF_INVALID' } })]);
    const res = await sessionClient(s.f).send('/api/v1/x', { method:'POST', body:'{}' });
    expect(res.status).toBe(200);
    expect(s.calls).toEqual(['GET /api/v1/auth/session ', 'POST /api/v1/x t1', 'GET /api/v1/auth/session ', 'POST /api/v1/x t2']);
  });
  it('repeats the old "Invalid CSRF token" too, but only once', async () => {
    const s = server([answer(403, { detail:'Invalid CSRF token' }), answer(403, { detail:'Invalid CSRF token' })]);
    const res = await sessionClient(s.f).send('/api/v1/x', { method:'PUT' });
    expect(res.status).toBe(403);
    expect(s.calls.filter(c => c.startsWith('PUT'))).toHaveLength(2);
  });
  it('never repeats nor drops the session on a plan refusal', async () => {
    const s = server([answer(403, { error:{ code:'CAPABILITY_REQUIRED', details:{ capability:'screener.run' } } })]);
    const c = sessionClient(s.f);
    const res = await c.send('/api/v1/x', { method:'POST' });
    expect(res.status).toBe(403);
    expect(c.current?.csrf).toBe('t1');                     // still signed in, same token
    await c.send('/api/v1/x', { method:'POST' });
    expect(s.calls.filter(c => c.startsWith('GET /api/v1/auth/session'))).toHaveLength(1);
  });
  it('another login read again is refused: the write is never sent, the page gets 401 USER_CHANGED and its user state goes', async () => {
    let who = 'alice'; const writes: string[] = [];
    const f = (async (url: string, init?: RequestInit) => {
      if (url === '/api/v1/auth/session') return answer(200, { login:who, csrf_token:`t-${who}` });
      writes.push((init?.headers as any)?.['X-CSRF-Token']);
      return answer(403, { error:{ code:'CSRF_INVALID' } });
    }) as unknown as typeof fetch;
    const c = sessionClient(f), dropped = vi.fn();
    const off = onReset(dropped);
    await c.session();
    expect(c.identity).toBe('alice');
    local.setItem('ml.symbol', 'BBRI');
    who = 'bob';
    const res = await c.send('/api/v1/x', { method:'PUT' });
    off();
    expect(res.status).toBe(401);
    expect((await res.json()).error.code).toBe('USER_CHANGED');
    expect(writes).toEqual(['t-alice']);
    expect(dropped).toHaveBeenCalled();
    expect(local.getItem('ml.symbol')).toBeNull();
    expect(c.identity).toBe('alice');
  });
  it('the "cleared" broadcast of another page drops this page\'s pending writes', async () => {
    const dropped = vi.fn(), off = onReset(dropped);
    sessionClient(async () => answer(200, {}));                // the page listens
    const other = new BroadcastChannel('edge-session');
    other.postMessage({ type:'cleared', from:'another-page' });
    await vi.waitFor(() => expect(dropped).toHaveBeenCalled());
    other.close(); off();
  });
  it('forgets the session on a 401 only', async () => {
    const s = server([answer(401, { error:{ code:'UNAUTHENTICATED' } })]);
    const c = sessionClient(s.f);
    await c.session();
    expect((await c.send('/api/v1/x')).status).toBe(401);
    expect(c.current).toBeNull();
  });
});

describe('the storage registry and the clean-up (M473)', () => {
  it('classes the keys and clears only the user ones, keeping the theme and widths', async () => {
    for (const k of ['edge-auth-monitor-theme', 'edge-monitor-width', 'ml.stats.w', 'scr.panes', 'edge.watchlist.logos']) local.setItem(k, '1');
    for (const k of ['edge-model-choice', 'ml.symbol', 'ml.layout.active', 'ml.drawings.BBRI', 'ml.ind.v1', 'scr.last', 'scr.boot', 'edge.watchlist.view', 'ml.unknown.new']) local.setItem(k, '1');
    session.setItem('edge-side-attach:conv_1', '[]'); session.setItem('edge-details-open', 'true');
    local.setItem(LAST_LOGIN_KEY, 'owner');
    expect(classify('ml.drawings.flow.BBRI')?.kind).toBe('user');
    expect(classify('edge-side-attach:x', 'session')?.kind).toBe('user');
    await clearUserState();
    expect([...local.m.keys()].sort()).toEqual(['edge-auth-monitor-theme', 'edge-last-login', 'edge-monitor-width', 'edge.watchlist.logos', 'ml.stats.w', 'scr.panes']);
    expect([...session.m.keys()]).toEqual(['edge-details-open']);
    expect(deleted).toEqual(['terminal-files']);
    await clearUserState({ signOut:true });
    expect(local.getItem(LAST_LOGIN_KEY)).toBeNull();
  });
  it('a first load adopts the login and clears nothing; another login clears the previous account', () => {
    local.setItem('ml.symbol', 'BBRI');
    expect(noteLogin('Owner')).toBe(false);
    expect([local.getItem('ml.symbol'), local.getItem(LAST_LOGIN_KEY)]).toEqual(['BBRI', 'owner']);
    expect(noteLogin('owner')).toBe(false);
    expect(checkUser('OWNER')).toBe(false);
    expect(local.getItem('ml.symbol')).toBe('BBRI');
    expect(noteLogin('second')).toBe(true);
    expect([local.getItem('ml.symbol'), local.getItem(LAST_LOGIN_KEY)]).toEqual([null, 'second']);
  });
  it('a page clears on another login but never writes the mark', () => {
    local.setItem('scr.last', '{}');
    expect(checkUser('someone')).toBe(false);               // no mark: the shell has not signed in on this browser
    expect(local.getItem(LAST_LOGIN_KEY)).toBeNull();
    local.setItem(LAST_LOGIN_KEY, 'owner');
    expect(checkUser('someone')).toBe(true);
    expect([local.getItem('scr.last'), local.getItem(LAST_LOGIN_KEY)]).toEqual([null, 'owner']);
  });
});

describe('drawings kept in this browser (M468)', () => {
  it('a stamped copy joins only its own login', () => {
    const text = stampCopy('[{"id":"d1"}]', 'Owner');
    expect(JSON.parse(text)).toEqual({ owner:'owner', drawings:[{ id:'d1' }] });
    expect(ownCopy(text, 'owner')).toEqual([{ id:'d1' }]);
    expect(ownCopy(text, 'second')).toBeNull();
    expect(ownCopy(text, '')).toBeNull();
  });
  it('an older copy without a stamp joins only when the login is the last one of this browser', () => {
    local.setItem(LAST_LOGIN_KEY, 'owner');
    expect(ownCopy('[{"id":"d1"}]', 'Owner')).toEqual([{ id:'d1' }]);
    expect(ownCopy('[{"id":"d1"}]', 'second')).toBeNull();
    local.removeItem(LAST_LOGIN_KEY);
    expect(ownCopy('[{"id":"d1"}]', 'owner')).toBeNull();
    expect(ownCopy('not json', 'owner')).toBeNull();
  });
  it('nothing is kept for a page whose login is not known (an unowned copy could join the next account)', () => {
    expect(stampCopy('[]', '')).toBeNull();
  });
});
