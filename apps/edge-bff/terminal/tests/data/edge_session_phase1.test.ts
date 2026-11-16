/* EXEC-MU-ACCOUNTS Phase 1 (contract sections 2, 4b, 12): the identity moves to the stable owner key (with a one-time
   migration of the marks and stamps of the same login), and the account preferences (registry `sync`) are copied to the
   server with GET/PUT /api/v1/preferences (B1b's routes, mocked here). */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { checkUser, identityOf, LAST_LOGIN_KEY, noteIdentity, preferences, sessionClient, SYNC_KEYS, STORAGE } from '../../../shared/edge-session';
import { ownCopy, stampCopy } from '../../src/data/drawingsApi';

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
const answer = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers:{ 'Content-Type':'application/json' } });
let local: ReturnType<typeof memoryStorage>;
const listeners: Record<string, ((e: any) => void)[]> = {};
beforeEach(() => {
  local = memoryStorage(); vi.stubGlobal('localStorage', local); vi.stubGlobal('sessionStorage', memoryStorage());
  for (const k of Object.keys(listeners)) delete listeners[k];
  vi.stubGlobal('addEventListener', (t: string, fn: (e: any) => void) => { (listeners[t] ||= []).push(fn) });
  vi.stubGlobal('indexedDB', { deleteDatabase:() => { const r: any = {}; setTimeout(() => r.onsuccess?.()); return r } });
});
afterEach(() => vi.unstubAllGlobals());

describe('identity: the stable owner key (contract section 2)', () => {
  it('is owner:<key> when the session carries it, else the login; a username can never look like one', () => {
    expect(identityOf('Owner', 'u_0123456789abcdef01234567')).toBe('owner:u_0123456789abcdef01234567');
    expect(identityOf('Owner', null)).toBe('owner');
    expect(identityOf('u_0123456789abcdef01234567')).not.toBe(identityOf('x', 'u_0123456789abcdef01234567'));
  });
  it('a mark of the same login moves to the owner key once, with its drawing stamps, and clears nothing', () => {
    local.setItem(LAST_LOGIN_KEY, 'owner'); local.setItem('ml.symbol', 'BBRI');
    local.setItem('ml.drawings.BBRI', stampCopy('[{"id":"d1"}]', 'owner') as string);
    local.setItem('ml.drawings.flow.BBRI', stampCopy('[{"id":"d2"}]', 'someone') as string);
    expect(noteIdentity('Owner', 'u_0123456789abcdef01234567')).toEqual({ changed:false, same:true });
    const id = 'owner:u_0123456789abcdef01234567';
    expect([local.getItem(LAST_LOGIN_KEY), local.getItem('ml.symbol')]).toEqual([id, 'BBRI']);
    expect(ownCopy(local.getItem('ml.drawings.BBRI'), id)).toEqual([{ id:'d1' }]);
    expect(ownCopy(local.getItem('ml.drawings.flow.BBRI'), id)).toBeNull();      // another login's stamp stays another's
    expect(noteIdentity('Owner', 'u_0123456789abcdef01234567')).toEqual({ changed:false, same:true });
  });
  it('another owner key clears the previous account even when the login is the same text', () => {
    local.setItem(LAST_LOGIN_KEY, 'owner:u_aaaaaaaaaaaaaaaaaaaaaaaa'); local.setItem('scr.last', '{}');
    expect(noteIdentity('owner', 'u_bbbbbbbbbbbbbbbbbbbbbbbb')).toEqual({ changed:true, same:false });
    expect(local.getItem('scr.last')).toBeNull();
  });
  it('a page accepts its login mark with the owner key now known, and moves the stamps without writing the mark', () => {
    local.setItem(LAST_LOGIN_KEY, 'owner'); local.setItem('scr.last', '{}');
    expect(checkUser('owner', 'u_0123456789abcdef01234567')).toBe(false);
    expect([local.getItem(LAST_LOGIN_KEY), local.getItem('scr.last')]).toEqual(['owner', '{}']);
  });
  it('the page identity follows the same account from its login to its owner key (a deploy between two reads)', async () => {
    let owner: string | null = null;
    const c = sessionClient((async () => answer(200, { login:'owner', csrf_token:'t', ...(owner ? { owner_key:owner } : {}) })) as any);
    await c.session();
    expect(c.identity).toBe('owner');
    owner = 'u_0123456789abcdef01234567'; c.invalidate();
    await c.session();
    expect(c.identity).toBe('owner:u_0123456789abcdef01234567');
  });
});

describe('account preferences (contract 4b)', () => {
  it('the registry marks every synced key and only exact localStorage keys', () => {
    expect(SYNC_KEYS).toContain('edge-model-choice');
    expect(SYNC_KEYS).toContain('scr.last');
    expect(STORAGE.filter(e => e.kind === 'user').every(e => !!e.sync !== !!e.cache)).toBe(true);
  });
  function server(initial: Record<string, { value: unknown; version: number }> = {}, status = 200) {
    const rows = new Map(Object.entries(initial)), calls: { method: string; key?: string; body?: any }[] = [];
    const send = vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = init.method || 'GET';
      if (status !== 200) return answer(status, { error:{ code:'NOT_FOUND' } });
      if (method === 'GET') { calls.push({ method }); return answer(200, { preferences:[...rows].map(([key, r]) => ({ key, ...r })) }) }
      const key = decodeURIComponent(url.split('/').pop() as string), body = JSON.parse(String(init.body));
      calls.push({ method, key, body });
      const row = rows.get(key);
      if (row && body.version !== row.version) return answer(409, { error:{ code:'VERSION_CONFLICT', details:{ value:row.value, version:row.version } } });
      const next = { value:body.value, version:(row?.version ?? 0) + 1 }; rows.set(key, next);
      return answer(200, { key, ...next });
    });
    return { send: send as any, rows, calls };
  }
  it('loads the server copy into storage, and uploads a local value with no server copy once for the same identity', async () => {
    local.setItem('ml.my', '[1]'); local.setItem('edge-model-choice', '"local"'); local.setItem('ml.stats.w', '300');
    const s = server({ 'edge-model-choice':{ value:'"server"', version:3 } });
    const p = preferences(s, { delayMs:0 });
    expect(await p.load({ uploadLocal:true })).toBe(true);
    expect(local.getItem('edge-model-choice')).toBe('"server"');
    expect(s.calls.filter(c => c.method === 'PUT').map(c => [c.key, c.body])).toEqual([['ml.my', { value:'[1]' }]]);
    await p.load({ uploadLocal:true });
    expect(s.calls.filter(c => c.method === 'PUT')).toHaveLength(1);           // once: the server holds it now
  });
  it('never uploads a local value of another or unknown identity', async () => {
    local.setItem('ml.my', '[1]');
    const s = server();
    await preferences(s, { delayMs:0 }).load({ uploadLocal:false });
    expect(s.calls.filter(c => c.method === 'PUT')).toEqual([]);
  });
  it('a change is written a moment later with its version; a 409 takes the server value', async () => {
    const s = server({ 'scr.last':{ value:'{"a":1}', version:1 } });
    const p = preferences(s, { delayMs:0 });
    await p.load();
    local.setItem('scr.last', '{"a":2}'); p.note('scr.last');
    await vi.waitFor(() => expect(s.rows.get('scr.last')).toEqual({ value:'{"a":2}', version:2 }));
    s.rows.set('scr.last', { value:'{"other":true}', version:5 });            // another device wrote it
    local.setItem('scr.last', '{"a":3}'); p.note('scr.last');
    await vi.waitFor(() => expect(local.getItem('scr.last')).toBe('{"other":true}'));
    expect(s.calls.at(-1)?.body).toEqual({ value:'{"a":3}', version:2 });
  });
  it('a change made in a page frame reaches the shell as a storage event; a removal (the clean-up) is never sent', async () => {
    const s = server();
    const p = preferences(s, { delayMs:0 });
    await p.load();
    local.setItem('ml.ind.favs', '["rsi"]');
    listeners.storage.forEach(fn => fn({ key:'ml.ind.favs', newValue:'["rsi"]', storageArea:local }));
    listeners.storage.forEach(fn => fn({ key:'ml.my', newValue:null, storageArea:local }));
    listeners.storage.forEach(fn => fn({ key:'ml.stats.w', newValue:'1', storageArea:local }));
    await vi.waitFor(() => expect(s.rows.get('ml.ind.favs')?.value).toBe('["rsi"]'));
    expect(s.calls.filter(c => c.method === 'PUT').map(c => c.key)).toEqual(['ml.ind.favs']);
  });
  it('without the route (404: switch off) nothing is read or written; after stop() nothing more is sent', async () => {
    const off = server({}, 404);
    const p = preferences(off, { delayMs:0 });
    expect(await p.load({ uploadLocal:true })).toBe(false);
    local.setItem('ml.my', '[2]'); p.note('ml.my');
    await new Promise(r => setTimeout(r, 5));
    expect(off.send).toHaveBeenCalledTimes(1);
    const s = server(), q = preferences(s, { delayMs:20 });
    await q.load(); q.note('ml.my'); q.stop();
    await new Promise(r => setTimeout(r, 40));
    expect(s.calls.filter(c => c.method === 'PUT')).toEqual([]);
  });
});
