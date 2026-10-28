/* The production ScreenerApi: edge-bff /api/v1/screener/* (report API CONTRACT 8.2). Session and CSRF as the Backtest
   page (apps/edge-bff/backtest/src/api/live.ts csrf() and call(); P27 b, a third copy now, a shared module later):
   GET /api/v1/auth/session once for the token, the token on every PUT, POST and DELETE. GETs carry only the cookie.
   Catalog and universe are conditional GETs: the page sends If-None-Match from its own pointer (report 6c.5 item 5)
   and reads the ETag back; the house Cache-Control no-store keeps the browser's HTTP cache out.
   Errors keep the contract's shape {"error": {code, field, message, details}}; the TEMPORARY 401/403 {"detail": ...}
   of the auth dependencies (report 8.1, ERRORS M261) is mapped the same way. */
import type {
  CatalogResponse, CountsRequest, CountsResponse, Definition, ItemKind, ItemsResponse, PreviewRequest, PreviewResponse,
  PutItemRequest, RunRequest, SavedItem, UniverseResponse, ValidateResponse, WatchlistResponse,
} from '../core/contract.ts';
import { SCHEMA_VERSION } from '../core/contract.ts';
import { ApiFailure, isAbort, type CallOpts, type Conditional, type RunAnswer, type ScreenerApi, type Session } from './types.ts';
import { errorText, T } from '../texts.ts';

const BASE = '/api/v1/screener';

/** Reads Retry-After (seconds, or an HTTP date) as whole seconds; null when absent or unreadable. */
export function retryAfter(h: string | null, now = Date.now()): number | null {
  if (!h) return null;
  const s = Number(h);
  if (Number.isFinite(s) && s >= 0) return Math.ceil(s);
  const t = Date.parse(h);
  return Number.isFinite(t) ? Math.max(0, Math.ceil((t - now) / 1000)) : null;
}

/** An edge-bff answer that is not ok, as the page's ApiFailure: the contract's error body, or the auth dependencies'
    {"detail": ...} (TEMPORARY, M261), or no JSON at all. The message is the page's own wording per code (texts.ts),
    with the server's message where the page has none, so every refusal names where and how to fix (report 8.8). */
export async function failure(res: Response): Promise<ApiFailure> {
  let data: any = null;
  try { data = await res.json() } catch { /* no JSON body */ }
  const err = data && data.error && typeof data.error === 'object' ? data.error : null;
  const ra = retryAfter(res.headers.get('Retry-After'));
  if (res.status === 401) return new ApiFailure(T.signIn, 'UNAUTHENTICATED', 401);
  if (res.status === 403 && !err) return new ApiFailure(T.forbidden, 'FORBIDDEN', 403);
  const code = err ? String(err.code || '') : '';
  const details = err && err.details && typeof err.details === 'object' ? err.details : null;
  const msg = errorText(code, { field:err?.field, details, retryAfter:ra, server:err?.message || (typeof data?.detail === 'string' ? data.detail : '') })
    || `The screener answered ${res.status}${code ? ` (${code})` : ''}.`;
  return new ApiFailure(msg, code || `HTTP_${res.status}`, res.status, err?.field, ra, details);
}

const unquote = (etag: string | null) => etag ? etag.replace(/^W\//, '').replace(/^"|"$/g, '') : null;
const newId = () => typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID().replace(/-/g, '') : Math.random().toString(36).slice(2) + Date.now().toString(36);

/** `fetchImpl`: a test passes its own fetch. */
export function liveApi(opts: { fetchImpl?: typeof fetch } = {}): ScreenerApi {
  const f: typeof fetch = opts.fetchImpl ?? ((...a) => fetch(...a));
  let sessionP: Promise<Session> | null = null;
  const session = () => sessionP ||= (async () => {
    let res: Response;
    try { res = await f('/api/v1/auth/session', { credentials:'same-origin' }) }
    catch { throw new ApiFailure(T.unreachable, 'NETWORK') }
    if (!res.ok) throw new ApiFailure(T.signIn, 'UNAUTHENTICATED', res.status);
    const d = await res.json().catch(() => ({}));
    return { login:String(d.login || ''), csrf:String(d.csrf_token || '') };
  })().catch(e => { sessionP = null; throw e });

  async function send(method: string, path: string, body?: unknown, o: CallOpts & { etag?: string | null } = {}): Promise<Response> {
    const headers: Record<string, string> = {};
    if (method !== 'GET') { headers['X-CSRF-Token'] = (await session()).csrf; if (body !== undefined) headers['Content-Type'] = 'application/json' }
    if (o.etag) headers['If-None-Match'] = `"${o.etag}"`;
    let res: Response;
    try { res = await f(BASE + path, { method, credentials:'same-origin', headers, body:body === undefined ? undefined : JSON.stringify(body), signal:o.signal }) }
    catch (e) { if (isAbort(e)) throw e; throw new ApiFailure(T.unreachable, 'NETWORK') }
    if (res.status === 304) return res;
    if (!res.ok) {
      if (res.status === 401 || res.status === 403) sessionP = null;     // a new session or token is read on the next call
      throw await failure(res);
    }
    return res;
  }
  const bytesOf = async (res: Response, o: CallOpts = {}) => {
    try { return new Uint8Array(await res.arrayBuffer()) }
    catch (e) { if (isAbort(e) || o.signal?.aborted) throw e; throw new ApiFailure(T.unreachable, 'NETWORK') }
  };
  const decode = <T>(bytes: Uint8Array): T => {
    try { return JSON.parse(new TextDecoder().decode(bytes)) as T }
    catch { throw new ApiFailure(T.unreachable, 'NETWORK') }
  };
  async function json<T>(method: string, path: string, body?: unknown, o: CallOpts = {}): Promise<T> {
    const res = await send(method, path, body, o);
    if (res.status === 204) return undefined as T;
    return decode<T>(await bytesOf(res, o));
  }
  async function conditional<T>(path: string, etag?: string | null): Promise<Conditional<T>> {
    const res = await send('GET', path, undefined, { etag });
    const tag = unquote(res.headers.get('ETag'));
    if (res.status === 304) return { status:304, etag:tag ?? etag ?? null };
    const bytes = await bytesOf(res);
    return { status:200, etag:tag, body:decode<T>(bytes), bytes };
  }

  // latest wins per page (report 8.1 client_order): one page id per page load, one sequence for run and preview each
  const page = 'pg_' + newId().slice(0, 32);
  let runs = 0, previews = 0;

  return {
    kind:'live',
    session,
    catalog: etag => conditional<CatalogResponse>('/catalog', etag),
    universe: etag => conditional<UniverseResponse>('/universe', etag),
    async run(req, o = {}): Promise<RunAnswer> {
      const res = await send('POST', '/run', { ...req, schema_version:SCHEMA_VERSION, client_order:{ page, seq:++runs } } satisfies RunRequest, o);
      const bytes = await bytesOf(res, o);
      return { body:decode(bytes), bytes };
    },
    preview: (req, o = {}) => json<PreviewResponse>('POST', '/preview', { ...req, schema_version:SCHEMA_VERSION, client_order:{ page, seq:++previews } } satisfies PreviewRequest, o),
    validate: (definition: Definition) => json<ValidateResponse>('POST', '/validate', { schema_version:SCHEMA_VERSION, definition }),
    counts: (req: CountsRequest) => json<CountsResponse>('POST', '/counts', req),
    items: (kind: ItemKind) => json<ItemsResponse>('GET', `/items?kind=${encodeURIComponent(kind)}`),
    putItem: (id: string, req: PutItemRequest) => json<SavedItem>('PUT', `/items/${encodeURIComponent(id)}`, req),
    async deleteItem(id: string) { await json('DELETE', `/items/${encodeURIComponent(id)}`) },
    watchlist: () => json<WatchlistResponse>('GET', '/watchlist'),
    async watch(ticker: string, on: boolean) { await json(on ? 'PUT' : 'DELETE', `/watchlist/${encodeURIComponent(ticker)}`) },
  };
}
