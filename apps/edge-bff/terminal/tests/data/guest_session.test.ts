/* Track guest (EXEC-MU-ACCOUNTS, decision 1 of 2026-11-19; verification/edge_multiuser/fix_round/guest.md): a page that
   a visitor without an account may open (the Terminal, allowGuest) reads the guest plan's access when the session route
   answers 401; access(), can(), limit() and catalog() read it like an account's; a page that did not ask for it stays
   signed out; a visitor holds nothing of this browser's storage. live.ts lockRules derives what is locked from that
   access and the catalog route, never from a list in the page. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ENTITLEMENTS_HEADER, GUEST_URL, LAST_LOGIN_KEY, SessionError, sessionClient } from '../../../shared/edge-session';
import labelsSource from '../../../static/edge-labels.js?raw';

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

const answer = (status: number, body: unknown, version = '') => new Response(JSON.stringify(body),
  { status, headers:{ 'Content-Type':'application/json', ...(version ? { [ENTITLEMENTS_HEADER]:version } : {}) } });
const GUEST_ACCESS = { plan:'guest', role:'visitor', status:'visitor', mfa_ok:true, seed:false, owner_key:null, next:null,
  version:'db-0123456789ab', capabilities:['terminal.view'], limits:{ 'terminal.tickers':['BBCA'], 'terminal.history_days':730 } };
const UNAUTH = { error:{ code:'UNAUTHENTICATED', message:'Your session has ended or you are not signed in. Please sign in again.', details:{} } };

function server(opts: { guest?: number; entries?: string[] } = {}) {
  const calls: string[] = [];
  const f = vi.fn(async (url: any) => {
    const u = String(url); calls.push(u);
    if (u === '/api/v1/auth/session') return answer(401, UNAUTH);
    if (u === GUEST_URL) return (opts.guest ?? 200) === 200
      ? answer(200, { authenticated:false, visitor:true, login:'', owner_key:null, csrf_token:'', access:GUEST_ACCESS }, 'db-0123456789ab')
      : answer(opts.guest!, UNAUTH);
    const m = /^\/api\/v1\/catalog\/(.+)$/.exec(u);
    if (m) return answer(200, { kind:m[1], entries:(opts.entries || []).map(id => ({ id, stage:'released' })) }, 'db-0123456789ab');
    return answer(200, {});
  });
  return { f, calls };
}

describe('a visitor without an account (allowGuest)', () => {
  it('reads the guest plan\'s access when the session route answers 401', async () => {
    const s = server(), c = sessionClient(s.f as any);
    c.allowGuest();
    const info = await c.session();
    expect(info.guest).toBe(true);
    expect(info.csrf).toBe('');
    expect(c.guest).toBe(true);
    expect(c.can('terminal.view')).toBe(true);
    expect(c.can('terminal.layouts')).toBe(false);
    expect(c.limit('terminal.tickers')).toEqual(['BBCA']);
    expect(c.identity).toBe('guest:');
    expect(s.calls).toEqual(['/api/v1/auth/session', GUEST_URL]);
    // a visitor is never a user of this browser: no last-login mark, nothing cleared
    local.setItem('ml.symbol', 'BBCA');
    expect(local.getItem(LAST_LOGIN_KEY)).toBeNull();
    expect(local.getItem('ml.symbol')).toBe('BBCA');
  });
  it('reads the catalogs it holds like an account', async () => {
    const s = server({ entries:['I01'] }), c = sessionClient(s.f as any);
    c.allowGuest();
    await c.session();
    expect((await c.catalog('indicator')).entries.map(e => e.id)).toEqual(['I01']);
  });
  it('a site without guests (the guest route refuses) stays signed out', async () => {
    const c = sessionClient(server({ guest:401 }).f as any);
    c.allowGuest();
    await expect(c.session()).rejects.toBeInstanceOf(SessionError);
    await expect(c.session()).rejects.toMatchObject({ error:{ kind:'signin' } });
    expect(c.guest).toBe(false);
  });
  it('a page that did not ask for guests never reads the guest route', async () => {
    const s = server(), c = sessionClient(s.f as any);
    await expect(c.session()).rejects.toMatchObject({ error:{ kind:'signin' } });
    expect(s.calls).not.toContain(GUEST_URL);
  });
});

describe('the words of the box are the shell\'s (static/edge-labels.js EdgeLabels.locked)', () => {
  it('names sign in for a visitor and the upgrade for an account', () => {
    const w = (globalThis as any).window = {} as any;
    new Function('window', labelsSource)(w);
    const L = w.EdgeLabels.locked;
    expect(L.guestTitle).toContain('{name}');
    expect(L.upgradeTitle).toContain('{name}');
    expect(L.signIn && L.register && L.contact && L.contactSoon && L.mark).toBeTruthy();
    expect(w.EdgeLabels.access.comingSoon).toBe('Coming soon');
    delete (globalThis as any).window;
  });
});
