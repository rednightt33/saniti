/* EXEC-MU-ACCOUNTS Phase 2 (contract sections 4, 8a, 12): the page's session client mirrors what the account holds
   (access(), can(), limit()) from the session answer's `access`, and reads GET /api/v1/catalog/{kind} (B-side route,
   mocked here) kept in memory per X-Edge-Entitlements version and page identity. The locked wording is in
   static/edge-labels.js (EdgeLabels.access). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearUserState, ENTITLEMENTS_HEADER, SessionError, sessionClient, STORAGE } from '../../../shared/edge-session';
import labelsSource from '../../../static/edge-labels.js?raw';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
let local: ReturnType<typeof memoryStorage>, session: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage(); session = memoryStorage();
  vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', session);
  vi.stubGlobal('indexedDB', { deleteDatabase:() => { const r: any = {}; setTimeout(() => r.onsuccess?.()); return r } });
});
afterEach(() => vi.unstubAllGlobals());

let seq = 0;
const fresh = (name: string) => `${name}-${++seq}-${Math.random().toString(36).slice(2, 8)}`;   // the version is module-wide
const answer = (status: number, body: unknown, version?: string) => new Response(JSON.stringify(body),
  { status, headers:{ 'Content-Type':'application/json', ...(version ? { [ENTITLEMENTS_HEADER]:version } : {}) } });

/** a server: the session answer with `access`, the catalog route (known kinds only), every answer with `version()` */
function server(access: unknown, opts: { version: () => string; catalogStatus?: () => number } = { version:() => '' }) {
  const calls: string[] = [];
  const f = vi.fn(async (url: any) => {
    const u = String(url); calls.push(u);
    const v = opts.version();
    if (u === '/api/v1/auth/session') return answer(200, { authenticated:true, login:'alice', csrf_token:'t', access }, v);
    const m = /^\/api\/v1\/catalog\/(.+)$/.exec(u);
    if (m) {
      const status = opts.catalogStatus?.() ?? 200;
      if (status === 401) return answer(401, { error:{ code:'UNAUTHENTICATED', message:'Sign in to EDGE.', details:{} } }, v);
      if (!['indicator', 'flow_indicator'].includes(m[1])) return answer(404, { error:{ code:'NOT_FOUND', message:'Not found.', details:{} } }, v);
      return answer(200, { kind:m[1], entries:[{ id:'I01', stage:'released' }, { id:'I02', stage:'lab' }] }, v);
    }
    return answer(200, {}, v);
  });
  return { f, calls, catalogCalls:() => calls.filter(u => u.startsWith('/api/v1/catalog/')).length };
}

const paid = { plan:'paid', role:'user', status:'active', version:'abc123', mfa_ok:true, seed:false, owner_key:'u_0123456789abcdef01234567',
  capabilities:['terminal.view', 'monitor.chat', 'backtest.run'],
  limits:{ 'watchlist.lists':20, 'watchlist.per_list':50, 'terminal.tickers':['BBCA', 'BBRI'] } };

describe('access(), can() and limit() mirror the server (contract 8a)', () => {
  it('before a session read there is no access and nothing is held', () => {
    const c = sessionClient(server(paid).f as any);
    expect(c.access()).toBeNull();
    expect(c.can('terminal.view')).toBe(false);
    expect(c.limit('watchlist.lists')).toBeUndefined();
  });
  it('flags: a listed key is held, an absent key is not; limits and lists are read, an absent limit means no limit', async () => {
    const c = sessionClient(server(paid).f as any);
    await c.session();
    expect(c.access()?.plan).toBe('paid');
    expect(c.access()?.capabilities).toEqual(paid.capabilities);
    expect([c.can('terminal.view'), c.can('monitor.chat'), c.can('backtest.run')]).toEqual([true, true, true]);
    expect([c.can('screener.run'), c.can('admin.access'), c.can(''), c.can('*')]).toEqual([false, false, false, false]);
    expect(c.limit('watchlist.lists')).toBe(20);
    expect(c.limit('terminal.tickers')).toEqual(['BBCA', 'BBRI']);
    expect(c.limit('watchlist.indicators')).toBeUndefined();
    expect(c.can('watchlist.lists')).toBe(false);                    // a limit is not a flag
  });
  it('item keys <family>:<id> are not decided from the session answer: false unless * is held', async () => {
    const c = sessionClient(server({ ...paid, capabilities:[...paid.capabilities, 'terminal.indicator', 'terminal.indicator:I01'] }).f as any);
    await c.session();
    expect(c.can('terminal.indicator:I01')).toBe(false);
    expect(c.can('terminal.flow_indicator:FL24')).toBe(false);
  });
  it('* holds every key: flags, item keys and unknown keys', async () => {
    const c = sessionClient(server({ ...paid, plan:'admin', capabilities:['*'], limits:{} }).f as any);
    await c.session();
    expect([c.can('screener.run'), c.can('terminal.indicator:I99'), c.can('anything.at.all')]).toEqual([true, true, true]);
    expect(c.limit('watchlist.lists')).toBeUndefined();
  });
  it('switch-off answer (version env, capabilities [*]): can() is true', async () => {
    const c = sessionClient(server({ plan:null, role:'admin', status:'active', version:'env', capabilities:['*'], limits:{}, seed:true, mfa_ok:true }).f as any);
    await c.session();
    expect(c.access()?.version).toBe('env');
    expect([c.can('terminal.view'), c.can('admin.access'), c.can('terminal.flow_indicator:FL01')]).toEqual([true, true, true]);
  });
  it('a session answer with no access object (an older server) holds nothing and has no limits', async () => {
    const c = sessionClient(server(undefined).f as any);
    await c.session();
    expect(c.access()).toBeNull();
    expect(c.can('terminal.view')).toBe(false);
    expect(c.limit('watchlist.lists')).toBeUndefined();
  });
});

describe('catalog(kind) (GET /api/v1/catalog/{kind})', () => {
  it('reads the entries once per version and keeps nothing in browser storage', async () => {
    const v = fresh('v');
    const s = server(paid, { version:() => v });
    const c = sessionClient(s.f as any);
    const a = await c.catalog('indicator');
    expect(a).toEqual({ kind:'indicator', entries:[{ id:'I01', stage:'released' }, { id:'I02', stage:'lab' }] });
    expect(await c.catalog('indicator')).toBe(a);
    expect(s.catalogCalls()).toBe(1);
    expect(s.calls[0]).toBe('/api/v1/auth/session');                // the page identity is read first
    await c.catalog('flow_indicator');
    expect(s.catalogCalls()).toBe(2);                               // per kind
    expect([local.length, session.length]).toEqual([0, 0]);
    expect(STORAGE.some(e => /catalog/i.test(e.key))).toBe(false);
  });
  it('reads again after the X-Edge-Entitlements value changes', async () => {
    let v = fresh('v1');
    const s = server(paid, { version:() => v });
    const c = sessionClient(s.f as any);
    await c.catalog('indicator'); await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(1);
    v = fresh('v2');
    await c.send('/api/v1/other');                                  // any answer with the new version
    await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(2);
    await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(2);
  });
  it('reads again after another page\'s "cleared" broadcast', async () => {
    const v = fresh('v');
    const s = server(paid, { version:() => v });
    const c = sessionClient(s.f as any);
    await c.catalog('indicator');
    const other = new BroadcastChannel('edge-session');
    other.postMessage({ type:'cleared', from:'another-page' });
    await vi.waitFor(() => expect(c.current).toBeNull());
    other.close();
    await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(2);
  });
  it('reads again after this page clears the user state', async () => {
    const v = fresh('v');
    const s = server(paid, { version:() => v });
    const c = sessionClient(s.f as any);
    await c.catalog('indicator');
    await clearUserState();
    await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(2);
  });
  it('a 401 drops the kept answers and rejects with UNAUTHENTICATED; the refusal is not kept', async () => {
    const v = fresh('v');
    let status = 200;
    const s = server(paid, { version:() => v, catalogStatus:() => status });
    const c = sessionClient(s.f as any);
    await c.catalog('indicator');
    await c.catalog('flow_indicator');
    status = 401;
    await c.send('/api/v1/catalog/flow_indicator');               // a 401 on any request of the page
    status = 200;
    await c.catalog('indicator');
    expect(s.catalogCalls()).toBe(4);
    status = 401;
    await c.invalidate();
    const e = await c.catalog('indicator').catch(x => x);
    expect(e).toBeInstanceOf(SessionError);
    expect(e.error).toMatchObject({ status:401, code:'UNAUTHENTICATED', kind:'signin' });
    status = 200;
    expect((await c.catalog('indicator')).entries).toHaveLength(2);
  });
  it('an unknown kind rejects with the error contract\'s NOT_FOUND, and is asked again next time', async () => {
    const v = fresh('v');
    const s = server(paid, { version:() => v });
    const c = sessionClient(s.f as any);
    const e = await c.catalog('nothing_like_this').catch(x => x);
    expect(e).toBeInstanceOf(SessionError);
    expect(e.error).toMatchObject({ status:404, code:'NOT_FOUND', kind:'not_found' });
    await c.catalog('nothing_like_this').catch(() => null);
    expect(s.catalogCalls()).toBe(2);
  });
  it('EDGE out of reach rejects with a SessionError whose error is null', async () => {
    let down = false;
    const s = server(paid, { version:() => '' });
    const c = sessionClient((async (url: any) => { if (down) throw new TypeError('offline'); return s.f(url) }) as any);
    await c.session();
    down = true;
    const e = await c.catalog('indicator').catch(x => x);
    expect(e).toBeInstanceOf(SessionError);
    expect(e.error).toBeNull();
  });
});

describe('the locked wording (EdgeLabels.access, EXEC-UI-1019B)', () => {
  it('holds the Phase 2 texts in English', () => {
    const window: any = {};
    new Function('window', labelsSource)(window);
    const a = window.EdgeLabels.access;
    expect(a.paidPlan).toBe('Available on a paid plan');
    expect(a.comingSoon).toBe('Coming soon');
    expect(a.contactUpgrade).toBe('Contact us to upgrade');
    expect(a.planEnded).toBe('Your plan has ended');
    expect(typeof a.refusedToast).toBe('string');
    expect(a.refusedToast.length).toBeGreaterThan(0);
    for (const k of ['CAPABILITY_REQUIRED', 'PLAN_EXPIRED', 'MFA_REQUIRED', 'LIMIT_REACHED', 'SIGN_IN_RATE_LIMIT']) expect(typeof a[k]).toBe('string');
  });
});
