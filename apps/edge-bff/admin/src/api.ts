/* Phase 4, the admin page: its only data paths, all on this origin with the EDGE session (app/admin.py).
     /api/v1/admin/step-up            the page's own authenticator step (the user's "1A"): GET whether it is needed, POST
                                      the 6-digit code; edge-bff renews the session, so the next write reads it again
     /api/v1/admin/...                the overview, the accounts, the audit (and its file), the plans, the settings and
                                      the support inbox; every write carries the session's CSRF token (shared module)
   A refusal keeps edge-bff's {error: {code, message, details}}: the page shows its message, which names the fix, and each
   field's reason under that field (details.fields, details.reasons). */
import { accessText, edge, readError } from '../../shared/edge-session.ts';
import type { AdminApi, Ticket } from './types.ts';
import { queryOf } from './model.ts';

export class AdminError extends Error {
  constructor(public code: string, message: string, public status: number, public fields: string[] = [],
              public reasons: Record<string, string> = {}, public details: Record<string, unknown> = {}) { super(message) }
}

const OFFLINE = 'The admin page could not reach EDGE. Check the connection and try again.';
const SIGNED_OUT = 'Your EDGE session ended. Sign in again, then open the admin page.';
const FAILED = 'EDGE could not do this. Try again in a minute.';
const A = '/api/v1/admin';

async function answer(method: string, url: string, body?: unknown): Promise<Response> {
  const headers: Record<string, string> = { accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let r: Response;
  try {
    r = await edge.send(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch { throw new AdminError('OFFLINE', OFFLINE, 0) }
  if (r.ok) return r;
  let data: any = null;
  try { data = await r.json() } catch { data = null }
  if (r.status === 401) throw new AdminError('SIGNED_OUT', SIGNED_OUT, 401);
  const e = data && typeof data.error === 'object' ? data.error : null;
  const d = e && typeof e.details === 'object' && e.details ? e.details : {};
  const message = (e && typeof e.message === 'string' && e.message) || accessText(readError(r.status, data, r.headers.get('Retry-After'))) || FAILED;
  throw new AdminError(e?.code || `HTTP_${r.status}`, message, r.status, Array.isArray(d.fields) ? d.fields : [],
                       d.reasons && typeof d.reasons === 'object' ? d.reasons : {}, d);
}

async function json<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await answer(method, url, body);
  try { return await r.json() as T } catch { throw new AdminError('UNREADABLE', FAILED, r.status) }
}

export const live: AdminApi = {
  stepState: () => json('GET', `${A}/step-up`),
  async stepUp(code) {
    await json('POST', `${A}/step-up`, { code });
    // the session was renewed (a new token, the old one revoked): the next write reads it again for its CSRF token
    edge.invalidate();
  },
  overview: () => json('GET', `${A}/overview`),
  users: q => json('GET', `${A}/users${queryOf(q)}`),
  user: id => json('GET', `${A}/users/${id}`),
  reveal: (id, field, reason) => json('POST', `${A}/users/${id}/reveal`, { field, reason }),
  audit: q => json('GET', `${A}/audit${queryOf(q)}`),
  async auditFile(q) { return (await answer('GET', `${A}/audit.csv${queryOf(q)}`)).blob() },
  plans: () => json('GET', `${A}/plans`),
  settings: () => json('GET', `${A}/settings`),
  tickets: q => json('GET', `${A}/support${queryOf(q)}`),
  ticket: id => json('GET', `${A}/support/${id}`),
  imageUrl: (id, position) => `${A}/support/${id}/images/${position}`,
  setStatus: (id, status) => json<Ticket>('POST', `${A}/support/${id}/status`, { status }),
  telegram: id => json('POST', `${A}/support/${id}/telegram`),
  async deleteTicket(id, reason) { await json('DELETE', `${A}/support/${id}`, { reason }) },
};
