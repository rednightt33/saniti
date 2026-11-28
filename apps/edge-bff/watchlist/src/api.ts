/* EXEC-WATCHLIST L5: the page's only data paths, all on this origin with the EDGE session.
     /api/v1/watchlist/index, /file/<name>?sha=   the publisher's watchlist-stocks file (app/pages.py, as the Overview's):
                                                  asked for by sha256, so the browser keeps it for good under that URL
     /api/v1/watchlist/lists ...                  the account's lists (app/watchlist.py); every write carries the session's
                                                  CSRF token (GET /api/v1/auth/session, as the Screener page's live.ts)
     /api/terminal/v1/reference/logos, /logo/<T>  the Terminal's issuer logos (as apps/edge-bff/terminal/src/data/live.ts)
   A refusal keeps edge-bff's {error: {code, field, message}}: the page shows its message, which names the fix. */
import { accessText, edge, isAccessRefusal, readError, SessionError } from '../../shared/edge-session.ts';
import { issuerLogoSrc, readIssuerLogos } from '../../shared/issuer-logos.ts';
import type { AddAnswer, CreateBody, ListsAnswer, WList, WatchlistApi, WatchlistIndex } from './types.ts';

export class WatchlistError extends Error {
  constructor(public code: string, message: string, public status: number, public field?: string) { super(message) }
}

const OFFLINE = 'The watchlist could not reach EDGE. Check the connection and try again.';
const SIGNED_OUT = 'Your EDGE session ended. Sign in again, then open the Watchlist.';
const FORBIDDEN = 'EDGE refused the change because the page’s session token is out of date. Reload the page and try again.';

/* EXEC-MU-ACCOUNTS Phase 0 (M471): the session, CSRF and the error contract are the shared module's
   (apps/edge-bff/shared/edge-session.ts): only a 401 is "signed out"; a 403 CSRF_INVALID is repeated once; a plan refusal
   (CAPABILITY_REQUIRED, PLAN_EXPIRED, LIMIT_REACHED, MFA_REQUIRED) keeps the session and is shown as its message. */
const csrf = () => edge.session().then(s => s.csrf, e => {
  const info = e instanceof SessionError ? e.error : null;
  if (!info) throw new WatchlistError('OFFLINE', OFFLINE, 0);
  if (isAccessRefusal(info)) throw new WatchlistError(info.code, e.message, info.status);
  throw new WatchlistError('SIGNED_OUT', SIGNED_OUT, info.status);
});

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { accept: 'application/json' };
  if (method !== 'GET') { await csrf(); if (body !== undefined) headers['Content-Type'] = 'application/json' }
  let r: Response;
  try {
    r = await edge.send(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new WatchlistError('OFFLINE', OFFLINE, 0) }
  if (r.status === 204) return undefined as T;
  let data: any = null;
  try { data = await r.json() } catch { data = null }
  if (!r.ok) {
    const e = data && typeof data.error === 'object' ? data.error : null;
    const info = readError(r.status, data, r.headers.get('Retry-After'));
    if (r.status === 401) throw new WatchlistError('SIGNED_OUT', SIGNED_OUT, 401);
    if (isAccessRefusal(info)) throw new WatchlistError(info.code, accessText(info) as string, r.status, e?.field);
    if (r.status === 403 && !e) throw new WatchlistError('FORBIDDEN', FORBIDDEN, 403);
    throw new WatchlistError(e?.code || `HTTP_${r.status}`, e?.message || 'The watchlist could not be read or saved. Try again in a minute.', r.status, e?.field);
  }
  return data as T;
}

const L = '/api/v1/watchlist/lists';
const enc = encodeURIComponent;

/* the logo list: shared/issuer-logos.ts (the Radar reads the same list under the same key) */

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
  logos: () => readIssuerLogos(() => call<{ url: string; sha256: string | null }>('GET', '/api/terminal/v1/reference/logos')).catch(() => ({})),
  logoSrc: issuerLogoSrc,
};

/* EXEC-MU-ACCOUNTS 3e, the example mode (user 2026-11-21; ERRORS M527): the files of the page's opening view on the
   latest price date, for watchlist.example (edge-bff app/examples.py cuts the live publication): watchlist-stocks of the
   example list (today's LQ45) and watchlist-lists, the one list in the shape of GET /api/v1/watchlist/lists. Read
   without the session (a visitor has none); nothing is
   written (the page is a view: shared/example-view.ts stops every click before it could ask), no logo is read. */
const EXAMPLE = '/api/v1/examples/watchlist';
async function exampleJson<T>(url: string): Promise<T> {
  let r: Response;
  try { r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } }) }
  catch { throw new WatchlistError('OFFLINE', OFFLINE, 0) }
  let data: any = null;
  try { data = await r.json() } catch { data = null }
  if (!r.ok) {
    const e = data && typeof data.error === 'object' ? data.error : null;
    throw new WatchlistError(e?.code || `HTTP_${r.status}`, e?.message || 'The example could not be read. Try again in a minute.', r.status);
  }
  return data as T;
}
const exampleFile = <T>(name: string, sha: string) => exampleJson<T>(`${EXAMPLE}/file/${enc(name)}?sha=${enc(sha)}`);
const viewOnly = (): never => { throw new WatchlistError('EXAMPLE', 'This is an example: sign in or upgrade to change it.', 403) };
export const example: WatchlistApi = {
  index: () => exampleJson<WatchlistIndex>(`${EXAMPLE}/index`),
  file: exampleFile,
  lists: async () => {
    const index = await exampleJson<WatchlistIndex>(`${EXAMPLE}/index`), e = index.files['watchlist-lists'];
    if (!e) throw new WatchlistError('EXAMPLE_NOT_READY', 'The example list is not ready yet.', 404);
    return exampleFile<ListsAnswer>('watchlist-lists', e.sha256);
  },
  create: async () => viewOnly(), rename: async () => viewOnly(), setIndicators: async () => viewOnly(),
  setIndicatorsAll: async () => viewOnly(), remove: async () => viewOnly(), addTickers: async () => viewOnly(),
  removeTicker: async () => viewOnly(),
  logos: async () => ({}),
  logoSrc: () => '',
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
