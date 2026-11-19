/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge"): the owner's saved chart layouts on edge-bff
   (apps/edge-bff/app/layouts.py, /api/v1/terminal/layouts; table edge_bff.terminal_layouts). Writes carry the EDGE
   session's CSRF token, read once from /api/v1/auth/session.

   QA round 3 (M6): every failure reaches the user as a sentence that says what to do; the backend's own message is kept
   where it names the field and the fix (422, 409), and a status without one gets a plain sentence here. */

export interface LayoutMeta { layout_id: string; name: string; summary: string; favorite: boolean; revision: number;
  created_at: string; updated_at: string; opened_at: string }
export interface Layout extends LayoutMeta { state: Record<string, string> }

import { accessText, edge, isAccessRefusal, readError, SessionError, type EdgeError } from '../../../shared/edge-session';

/* access: a refusal of the account's plan, role or limits (the shared module's isAccessRefusal), never an outage: a
   caller with an offline path keeps nothing for it (re-check R1-19) */
export class LayoutApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: any, public access = false) { super(message) }
}

const LATER = 'Try again in a minute; your chart is unchanged.';
/* EXEC-MU-ACCOUNTS Phase 0 (M471): the session, CSRF and the error contract are the shared module's
   (apps/edge-bff/shared/edge-session.ts): only a 403 CSRF_INVALID reads the session again and repeats the write once; a
   plan refusal (CAPABILITY_REQUIRED, PLAN_EXPIRED, LIMIT_REACHED, MFA_REQUIRED) is shown as its message and keeps the
   session; only a 401 says to sign in again. */
const token = () => edge.session().then(s => s.csrf, (e: any) => Promise.reject(e instanceof SessionError && e.error
  ? new LayoutApiError(e.error.status, e.error.kind === 'signin' ? 'SESSION' : e.error.code,
      e.error.kind === 'signin' ? 'Your EDGE sign-in has ended: sign in to EDGE again, then reload this page.'
        : accessText(e.error) || `Saved layouts are not available right now (EDGE answered ${e.error.status}). ${LATER}`,
      e.error.details, isAccessRefusal(e.error))
  : new LayoutApiError(0, 'NETWORK', `Saved layouts could not be reached: check the connection. ${LATER}`)));

/** the plain sentence for a refusal without its own message (or with one meant for developers); `what` names the saved
    objects ("layout", "preset") */
function sentence(status: number, e: any, what = 'layout', info?: EdgeError): string {
  if (status === 401) return 'Your EDGE sign-in has ended: sign in to EDGE again, then reload this page.';
  if (info && isAccessRefusal(info)) return accessText(info) as string;
  if (status === 403) return 'This page’s sign-in check failed: reload the page and try again.';
  if (status === 404 || e.code === 'NOT_FOUND') return `That ${what} no longer exists (it was deleted on another device or tab).`;
  if (status === 409 && e.code === 'REVISION_CONFLICT') return `This ${what} was changed on another device or tab. Open the list again, then try again.`;
  if (status === 413) return `This ${what} is too large to save.`;
  if (status >= 500 && !/_NOT_READY$/.test(e.code || '')) return `Saved ${what}s are not available right now (server error ${status}). ${LATER}`;
  return e.message || `Saved ${what}s answered ${status}. ${LATER}`;
}

/** EXEC-IND-PRESETS: one client for the EDGE account's saved objects (layouts, presets): session, CSRF, plain messages */
export const savedClient = (BASE: string, what: string) => {
  const call = async <T>(method: string, path: string, body?: unknown): Promise<T> => {
  const headers: Record<string, string> = {};
  if (method !== 'GET') { await token(); headers['content-type'] = 'application/json' }
  let res: Response;
  try { res = await edge.send(BASE + path, { method, headers, body:body === undefined ? undefined : JSON.stringify(body) }) }
  catch (e) { if (e instanceof LayoutApiError) throw e; throw new LayoutApiError(0, 'NETWORK', `Saved ${what}s could not be reached: check the connection. ${LATER}`) }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const info = readError(res.status, data, res.headers.get('Retry-After')), e = data?.error || {};
    throw new LayoutApiError(res.status, e.code || (info.legacy ? info.code : String(res.status)), sentence(res.status, e, what, info), e.details,
      isAccessRefusal(info));
  }
  return data as T;
  };
  return call;
};
const BASE = '/api/v1/terminal/layouts';
const call = savedClient(BASE, 'layout');

/** EXEC-DRAW-PANES: a write sent as the page goes away (keepalive; no answer read), for any saved object of the account */
export const sendOnLeave = (url: string, method: string, body: unknown) => {
  const csrfNow = edge.current?.csrf;
  if (!csrfNow) return;
  try { fetch(url, { method, keepalive:true, credentials:'same-origin', headers:{ 'x-csrf-token':csrfNow, 'content-type':'application/json' }, body:JSON.stringify(body) }) } catch { /* the page is leaving */ }
};
/** the CSRF token is read before the page needs to leave (sendOnLeave) */
export const primeToken = () => { token().catch(() => {}) };

export const newLayoutId = () => 'lay_' + [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');

export const layoutsApi = {
  list: () => call<{ layouts: LayoutMeta[]; limit: number }>('GET', ''),
  get: (id: string) => call<Layout>('GET', `/${id}`),
  put: (id: string, body: { name: string; state: Record<string, string>; summary: string; revision?: number }) => call<Layout>('PUT', `/${id}`, body),
  mark: (id: string, body: { favorite?: boolean; opened?: true }) => call<LayoutMeta>('PATCH', `/${id}`, body),
  remove: (id: string) => call<void>('DELETE', `/${id}`),
  prime: () => { token().catch(() => {}) },
  /** QA round 3 (L2): a change still waiting for its autosave is sent as the page goes away (keepalive; no answer read) */
  putOnLeave: (id: string, body: { name: string; state: Record<string, string>; summary: string; revision: number }) => {
    const csrfNow = edge.current?.csrf;
    if (!csrfNow) return;
    try { fetch(`${BASE}/${id}`, { method:'PUT', keepalive:true, credentials:'same-origin', headers:{ 'x-csrf-token':csrfNow, 'content-type':'application/json' }, body:JSON.stringify(body) }) } catch { /* the page is leaving */ }
  }
};
