/* EXEC-WATCHLIST L5: the page's only data paths, all on this origin with the EDGE session.
     /api/v1/watchlist/index, /file/<name>?sha=   the publisher's watchlist-stocks file (app/pages.py, as the Overview's):
                                                  asked for by sha256, so the browser keeps it for good under that URL
     /api/v1/watchlist/lists ...                  the account's lists (app/watchlist.py); every write carries the session's
                                                  CSRF token (GET /api/v1/auth/session, as the Screener page's live.ts)
     /api/terminal/v1/reference/logos, /logo/<T>  the Terminal's issuer logos (as apps/edge-bff/terminal/src/data/live.ts)
   A refusal keeps edge-bff's {error: {code, field, message}}: the page shows its message, which names the fix. */
import type { AddAnswer, CreateBody, ListsAnswer, WList, WatchlistApi, WatchlistIndex } from './types.ts';

export class WatchlistError extends Error {
  constructor(public code: string, message: string, public status: number, public field?: string) { super(message) }
}

const OFFLINE = 'The watchlist could not reach EDGE. Check the connection and try again.';
const SIGNED_OUT = 'Your EDGE session ended. Sign in again, then open the Watchlist.';
const FORBIDDEN = 'EDGE refused the change because the page’s session token is out of date. Reload the page and try again.';

let csrfP: Promise<string> | null = null;
const csrf = () => csrfP ||= (async () => {
  let r: Response;
  try { r = await fetch('/api/v1/auth/session', { credentials: 'same-origin' }) } catch { throw new WatchlistError('OFFLINE', OFFLINE, 0) }
  if (!r.ok) throw new WatchlistError('SIGNED_OUT', SIGNED_OUT, r.status);
  const d = await r.json().catch(() => ({}));
  return String(d.csrf_token || '');
})().catch(e => { csrfP = null; throw e });

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { accept: 'application/json' };
  if (method !== 'GET') { headers['X-CSRF-Token'] = await csrf(); if (body !== undefined) headers['Content-Type'] = 'application/json' }
  let r: Response;
  try {
    r = await fetch(url, { method, credentials: 'same-origin', headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new WatchlistError('OFFLINE', OFFLINE, 0) }
  if (r.status === 204) return undefined as T;
  let data: any = null;
  try { data = await r.json() } catch { data = null }
  if (!r.ok) {
    if (r.status === 401 || r.status === 403) csrfP = null;           // a new session or token is read on the next call
    const e = data && typeof data.error === 'object' ? data.error : null;
    if (r.status === 401) throw new WatchlistError('SIGNED_OUT', SIGNED_OUT, 401);
    if (r.status === 403 && !e) throw new WatchlistError('FORBIDDEN', FORBIDDEN, 403);
    throw new WatchlistError(e?.code || `HTTP_${r.status}`, e?.message || 'The watchlist could not be read or saved. Try again in a minute.', r.status, e?.field);
  }
  return data as T;
}

const L = '/api/v1/watchlist/lists';
const enc = encodeURIComponent;

/* the logo list: read at most every LOGO_HOURS per browser (each read of a reference file counts against the terminal
   account's quota, as the Terminal's); a per-viewer convenience, so a blocked storage only costs one more read */
const LOGO_KEY = 'edge.watchlist.logos', LOGO_HOURS = 12;
async function readLogos(): Promise<Record<string, string>> {
  try {
    const c = JSON.parse(localStorage.getItem(LOGO_KEY) || 'null');
    if (c && typeof c.at === 'number' && Date.now() - c.at < LOGO_HOURS * 3600e3 && c.map && typeof c.map === 'object') return c.map;
  } catch { /* storage off or unreadable: read the list */ }
  const ref = await call<{ url: string; sha256: string | null }>('GET', '/api/terminal/v1/reference/logos');
  const r = await fetch(ref.url);
  if (!r.ok) throw new Error('logos');
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (ref.sha256 && crypto?.subtle) {
    const got = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b => b.toString(16).padStart(2, '0')).join('');
    if (got !== ref.sha256) throw new Error('logos');                // not the announced file: monograms
  }
  const text = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text()
    : new TextDecoder().decode(bytes);
  const doc = JSON.parse(text);
  const map: Record<string, string> = {};
  (doc.ticker || []).forEach((t: string, i: number) => { if (doc.sha256?.[i]) map[t] = String(doc.sha256[i]).slice(0, 12) });
  try { localStorage.setItem(LOGO_KEY, JSON.stringify({ at: Date.now(), map })) } catch { /* storage off */ }
  return map;
}

export const live: WatchlistApi = {
  index: () => call<WatchlistIndex>('GET', '/api/v1/watchlist/index'),
  file: <T>(name: string, sha: string) => call<T>('GET', `/api/v1/watchlist/file/${enc(name)}?sha=${sha}`),
  lists: () => call<ListsAnswer>('GET', L),
  create: async (body: CreateBody) => (await call<{ list: WList }>('POST', L, body)).list,
  rename: async (id, name) => (await call<{ list: WList }>('PATCH', `${L}/${enc(id)}`, { name })).list,
  setIndicators: async (id, indicators) => (await call<{ list: WList }>('PATCH', `${L}/${enc(id)}`, { indicators })).list,
  setIndicatorsAll: async indicators => (await call<{ lists: WList[] }>('PUT', '/api/v1/watchlist/indicators', { indicators })).lists,
  remove: async id => (await call<{ deleted: WList }>('DELETE', `${L}/${enc(id)}`)).deleted,
  addTickers: (id, tickers, position) => call<AddAnswer>('POST', `${L}/${enc(id)}/tickers`, position == null ? { tickers } : { tickers, position }),
  removeTicker: (id, ticker) => call<void>('DELETE', `${L}/${enc(id)}/tickers/${enc(ticker)}`),
  logos: () => readLogos().catch(() => ({})),
  logoSrc: (t, v) => `/api/terminal/v1/logo/${enc(t)}?v=${enc(v)}`,
};

/** One copy of each file per page: a file is fetched once per sha and kept in memory. */
export function cached(api: WatchlistApi): WatchlistApi {
  const files = new Map<string, Promise<any>>();
  return {
    ...api,
    file<T>(name: string, sha: string): Promise<T> {
      const k = `${name}@${sha}`;
      if (!files.has(k)) files.set(k, api.file<T>(name, sha).catch(e => { files.delete(k); throw e }));
      return files.get(k) as Promise<T>;
    },
  };
}
