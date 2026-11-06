/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "di akun edge"): the owner's saved chart layouts on edge-bff
   (apps/edge-bff/app/layouts.py, /api/v1/terminal/layouts; table edge_bff.terminal_layouts). Writes carry the EDGE
   session's CSRF token, read once from /api/v1/auth/session. */

export interface LayoutMeta { layout_id: string; name: string; summary: string; favorite: boolean; revision: number;
  created_at: string; updated_at: string; opened_at: string }
export interface Layout extends LayoutMeta { state: Record<string, string> }

export class LayoutApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details?: any) { super(message) }
}

const BASE = '/api/v1/terminal/layouts';
let csrf: Promise<string> | null = null;
const token = () => csrf ??= fetch('/api/v1/auth/session', { credentials:'same-origin' })
  .then(r => r.ok ? r.json() : Promise.reject(new LayoutApiError(r.status, 'SESSION', 'Sign in to EDGE again to use saved layouts.')))
  .then(d => d.csrf_token || '').catch(e => { csrf = null; throw e });

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (method !== 'GET') { headers['x-csrf-token'] = await token(); headers['content-type'] = 'application/json' }
  let res: Response;
  try { res = await fetch(BASE + path, { method, headers, credentials:'same-origin', body:body === undefined ? undefined : JSON.stringify(body) }) }
  catch { throw new LayoutApiError(0, 'NETWORK', 'Saved layouts could not be reached: check the connection and try again.') }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data?.error || {};
    const message = res.status === 401 ? 'Sign in to EDGE again to use saved layouts.'
      : res.status === 403 ? 'The page’s sign-in expired: reload the page and try again.'
      : e.message || `Saved layouts answered ${res.status}.`;
    if (res.status === 403) csrf = null;
    throw new LayoutApiError(res.status, e.code || String(res.status), message, e.details);
  }
  return data as T;
}

export const newLayoutId = () => 'lay_' + [...crypto.getRandomValues(new Uint8Array(16))].map(b => b.toString(16).padStart(2, '0')).join('');

export const layoutsApi = {
  list: () => call<{ layouts: LayoutMeta[]; limit: number }>('GET', ''),
  get: (id: string) => call<Layout>('GET', `/${id}`),
  put: (id: string, body: { name: string; state: Record<string, string>; summary: string; revision?: number }) => call<Layout>('PUT', `/${id}`, body),
  mark: (id: string, body: { favorite?: boolean; opened?: true }) => call<LayoutMeta>('PATCH', `/${id}`, body),
  remove: (id: string) => call<void>('DELETE', `/${id}`)
};
