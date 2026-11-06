/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge"): the owner's saved chart layouts on edge-bff
   (apps/edge-bff/app/layouts.py, /api/v1/terminal/layouts; table edge_bff.terminal_layouts). Writes carry the EDGE
   session's CSRF token, read once from /api/v1/auth/session.

   QA round 3 (M6): every failure reaches the user as a sentence that says what to do; the backend's own message is kept
   where it names the field and the fix (422, 409), and a status without one gets a plain sentence here. */

export interface LayoutMeta { layout_id: string; name: string; summary: string; favorite: boolean; revision: number;
  created_at: string; updated_at: string; opened_at: string }
export interface Layout extends LayoutMeta { state: Record<string, string> }

export class LayoutApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: any) { super(message) }
}

const BASE = '/api/v1/terminal/layouts';
const LATER = 'Try again in a minute; your chart is unchanged.';
let csrf: Promise<string> | null = null, csrfNow = '';
const token = () => csrf ??= fetch('/api/v1/auth/session', { credentials:'same-origin' })
  .catch(() => Promise.reject(new LayoutApiError(0, 'NETWORK', `Saved layouts could not be reached: check the connection. ${LATER}`)))
  .then(r => r.ok ? r.json() : Promise.reject(r.status === 401
    ? new LayoutApiError(401, 'SESSION', 'Your EDGE sign-in has ended: sign in to EDGE again, then reload this page.')
    : new LayoutApiError(r.status, 'SESSION', `Saved layouts are not available right now (EDGE answered ${r.status}). ${LATER}`)))
  .then(d => (csrfNow = d.csrf_token || '')).catch(e => { csrf = null; throw e });

/** the plain sentence for a refusal without its own message (or with one meant for developers) */
function sentence(status: number, e: any): string {
  if (status === 401) return 'Your EDGE sign-in has ended: sign in to EDGE again, then reload this page.';
  if (status === 403) return 'This page’s sign-in check failed: reload the page and try again.';
  if (status === 404 || e.code === 'NOT_FOUND') return 'That layout no longer exists (it was deleted on another device or tab).';
  if (status === 409 && e.code === 'REVISION_CONFLICT') return 'This layout was changed on another device or tab. Open it again (Open layout), then try again.';
  if (status === 413) return 'This layout is too large to save: remove some indicators and try again.';
  if (status >= 500 && e.code !== 'LAYOUTS_NOT_READY') return `Saved layouts are not available right now (server error ${status}). ${LATER}`;
  return e.message || `Saved layouts answered ${status}. ${LATER}`;
}

async function call<T>(method: string, path: string, body?: unknown, retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== 'GET') { headers['x-csrf-token'] = await token(); headers['content-type'] = 'application/json' }
  let res: Response;
  try { res = await fetch(BASE + path, { method, headers, credentials:'same-origin', body:body === undefined ? undefined : JSON.stringify(body) }) }
  catch { throw new LayoutApiError(0, 'NETWORK', `Saved layouts could not be reached: check the connection. ${LATER}`) }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error || {};
    // a refused CSRF token (the session was renewed elsewhere): read the session again once
    if (res.status === 403 && !retried) { csrf = null; csrfNow = ''; return call<T>(method, path, body, true) }
    throw new LayoutApiError(res.status, e.code || String(res.status), sentence(res.status, e), e.details);
  }
  return data as T;
}

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
    if (!csrfNow) return;
    try { fetch(`${BASE}/${id}`, { method:'PUT', keepalive:true, credentials:'same-origin', headers:{ 'x-csrf-token':csrfNow, 'content-type':'application/json' }, body:JSON.stringify(body) }) } catch { /* the page is leaving */ }
  }
};
