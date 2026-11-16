/* EXEC-MU-ACCOUNTS Phase 1 (contract 4b; AGENTS.md M68): the page's preferences client against the real answers of
   app/preferences.py, recorded by apps/edge-bff/tests/test_preferences_recorded.py into preferences.recorded.json. Every
   request the client sends must be one the recording holds (method, path and body as sent), and the client must read
   every recorded answer as the server means it. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { preferences } from '../../../shared/edge-session';
import recorded from './preferences.recorded.json';

type Entry = { name: string; request: { method: string; path: string; body: any }; status: number; body: any };
const R = recorded as Entry[];
const named = (n: string) => R.find(e => e.name === n) as Entry;

function memoryStorage() {
  const m = new Map<string, string>();
  return { get length() { return m.size }, key:(i: number) => [...m.keys()][i] ?? null, getItem:(k: string) => m.get(k) ?? null,
    setItem:(k: string, v: string) => { m.set(k, String(v)) }, removeItem:(k: string) => { m.delete(k) }, clear:() => m.clear(), m };
}
let local: ReturnType<typeof memoryStorage>;
beforeEach(() => { local = memoryStorage(); vi.stubGlobal('localStorage', local); vi.stubGlobal('addEventListener', () => {}) });
afterEach(() => vi.unstubAllGlobals());

/* the server, answering only the recorded requests (`get`: the recorded GET answer to give) */
function replay(get: string, extra: (method: string, path: string, body: any) => Entry | undefined = () => undefined) {
  const sent: { method: string; path: string; body: any }[] = [];
  const send = vi.fn(async (url: string, init: RequestInit = {}) => {
    const method = init.method || 'GET', body = init.body === undefined ? null : JSON.parse(String(init.body));
    sent.push({ method, path:url, body });
    const e = method === 'GET' ? named(get) : extra(method, url, body)
      ?? R.find(x => x.request.method === method && x.request.path === url && JSON.stringify(x.request.body) === JSON.stringify(body));
    if (!e) throw new Error(`not a recorded request: ${method} ${url} ${JSON.stringify(body)}`);
    return new Response(JSON.stringify(e.body), { status:e.status, headers:{ 'Content-Type':'application/json' } });
  });
  return { send: send as any, sent };
}
/* a recorded GET whose list is the item one recorded PUT answer holds */
const getWith = (...names: string[]): Entry => ({ ...named('empty'), name:'built',
  body:{ ...named('empty').body, preferences:Object.fromEntries(names.map(n => { const { key, ...item } = named(n).body; return [key, item] })) } });

describe('the preferences client on the recorded answers of app/preferences.py', () => {
  it('the recording holds the shapes the client reads', () => {
    expect(named('empty').body).toEqual({ preferences:{}, limits:{ keys:64, value_bytes:65536, total_bytes:1048576 } });
    expect([named('created').status, named('replaced').status, named('stale').status, named('too_large').status]).toEqual([201, 200, 409, 422]);
    expect(named('stale').body.error.code).toBe('PREFERENCE_CONFLICT');
    expect(named('too_large').body.error).toMatchObject({ code:'PREFERENCE_LIMIT', details:{ limit:'value_bytes' } });
  });
  it('a local value with no server copy is created with version null (201), then replaced with the version read (200)', async () => {
    local.setItem('ml.my', '[{"id":"m1"}]');
    const s = replay('empty'), p = preferences(s, { delayMs:0 });
    expect(await p.load({ uploadLocal:true })).toBe(true);
    expect(p.state.get('ml.my')).toEqual({ value:'[{"id":"m1"}]', version:1 });
    local.setItem('ml.my', '[{"id":"m2"}]'); p.note('ml.my');
    await vi.waitFor(() => expect(p.state.get('ml.my')?.version).toBe(2));
    expect(s.sent.slice(1).map(x => x.body)).toEqual([named('created').request.body, named('replaced').request.body]);
  });
  it('the server copy of GET goes into this browser\'s storage', async () => {
    const s = replay('filled'), p = preferences(s, { delayMs:0 });
    await p.load();
    expect([local.getItem('ml.my'), local.getItem('scr.last')]).toEqual(['[{"id":"m2"}]', '{"name":"Mine"}']);
    expect([p.state.get('ml.my')?.version, p.state.get('scr.last')?.version]).toEqual([2, 1]);
  });
  it('a stale version (409 PREFERENCE_CONFLICT) takes details.current', async () => {
    const built = getWith('created');                          // this page read version 1; another device wrote 2
    const s = replay('empty'); s.send.mockImplementationOnce(async () => new Response(JSON.stringify(built.body), { status:200 }));
    const p = preferences(s, { delayMs:0 });
    await p.load();
    local.setItem('ml.my', '[]'); p.note('ml.my');
    await vi.waitFor(() => expect(local.getItem('ml.my')).toBe('[{"id":"m2"}]'));
    expect(p.state.get('ml.my')).toEqual({ value:'[{"id":"m2"}]', version:2 });
    expect(s.sent.at(-1)?.body).toEqual(named('stale').request.body);
  });
  it('a create over a key another device holds (409 with the current row) takes that row', async () => {
    local.setItem('scr.last', '{"name":"Other"}');
    const s = replay('empty'), p = preferences(s, { delayMs:0 });
    await p.load({ uploadLocal:true });
    expect(s.sent.at(-1)?.body).toEqual(named('missing_version').request.body);
    expect(local.getItem('scr.last')).toBe('{"name":"Mine"}');
  });
  it('a value over value_bytes is never sent; a 422 PREFERENCE_LIMIT stops that key', async () => {
    local.setItem('ml.ind.v1', 'x'.repeat(70000));
    const s = replay('empty', (m, path) => m === 'PUT' && path.endsWith('/ml.tf') ? named('too_large') : undefined);
    const p = preferences(s, { delayMs:0 });
    await p.load({ uploadLocal:true });
    expect(s.sent.filter(x => x.method === 'PUT')).toEqual([]);
    expect(p.refused.has('ml.ind.v1')).toBe(true);
    local.setItem('ml.tf', 'W'); p.note('ml.tf');
    await vi.waitFor(() => expect(p.refused.has('ml.tf')).toBe(true));
    local.setItem('ml.tf', 'M'); p.note('ml.tf');
    await new Promise(r => setTimeout(r, 5));
    expect(s.sent.filter(x => x.method === 'PUT').map(x => x.path)).toEqual(['/api/v1/preferences/ml.tf']);
  });
});
