/* EXEC-OVERVIEW O5: the page's only data path, edge-bff's /api/v1/overview (app/overview.py on app/pages.py) with this
   EDGE session. A file is asked for with its sha256, so the browser keeps it for good under that URL and a newer
   publication is a new URL. */
import type { OverviewApi, OverviewIndex } from './types.ts';

export class OverviewError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}

async function getJson<T>(url: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } });
  } catch {
    throw new OverviewError('OFFLINE', 'The overview could not reach EDGE. Check the connection and reload the page.', 0);
  }
  if (r.status === 401) throw new OverviewError('SIGNED_OUT', 'Your EDGE session ended. Sign in again, then open the overview.', 401);
  let body: any = null;
  try { body = await r.json() } catch { body = null }
  if (!r.ok) {
    const e = body?.error;
    throw new OverviewError(e?.code || 'OVERVIEW_UNAVAILABLE', e?.message || 'The market overview could not be read. Try again in a minute.', r.status);
  }
  return body as T;
}

export const live: OverviewApi = {
  index: () => getJson<OverviewIndex>('/api/v1/overview/index'),
  file: <T>(name: string, sha: string) => getJson<T>(`/api/v1/overview/file/${encodeURIComponent(name)}?sha=${sha}`),
};

/** One copy of each file per page: a file is fetched once per sha and kept in memory. */
export function cached(api: OverviewApi): OverviewApi {
  const files = new Map<string, Promise<any>>();
  return {
    index: () => api.index(),
    file<T>(name: string, sha: string): Promise<T> {
      const k = `${name}@${sha}`;
      if (!files.has(k)) files.set(k, api.file<T>(name, sha).catch(e => { files.delete(k); throw e }));
      return files.get(k) as Promise<T>;
    },
  };
}
