/* EXEC-SECTOR-ANALYSIS S4: the page's only data path, edge-bff's /api/v1/sector with this EDGE session, as the Overview's
   (overview/src/api.ts). A file is asked for with its sha256, so the browser keeps it for good under that URL and a newer
   publication is a new URL. */
import { accessText, isAccessRefusal, readError } from '../../shared/edge-session.ts';
import type { SectorApi, SectorIndex } from './types.ts';
import { W } from './words.ts';

export class SectorError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}

async function getJson<T>(url: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } });
  } catch {
    throw new SectorError('OFFLINE', W.err.offline, 0);
  }
  if (r.status === 401) throw new SectorError('SIGNED_OUT', W.err.signedOut, 401);
  let body: any = null;
  try { body = await r.json() } catch { body = null }
  if (!r.ok) {
    // EXEC-MU-ACCOUNTS Phase 0 (M471): a plan refusal keeps the session and is shown as its message (shared/edge-session.ts)
    const info = readError(r.status, body, r.headers.get('Retry-After'));
    if (isAccessRefusal(info)) throw new SectorError(info.code, accessText(info) as string, r.status);
    const e = body?.error;
    throw new SectorError(e?.code || 'SECTOR_UNAVAILABLE', e?.message || W.err.unavailable, r.status);
  }
  return body as T;
}

const pageApi = (base: string): SectorApi => ({
  index: () => getJson<SectorIndex>(`${base}/index`),
  file: <T>(name: string, sha: string) => getJson<T>(`${base}/file/${encodeURIComponent(name)}?sha=${sha}`),
});
export const live = pageApi('/api/v1/sector');
/* decision J (UD66, the user 2026-11-26), as the Overview's example (EXEC-MU-ACCOUNTS 3e, ERRORS M527): the example of
   one market date for a principal holding sector.example (edge-bff app/examples.py), in the same shapes */
export const example = pageApi('/api/v1/examples/sector');

/** One copy of each file per page: a file is fetched once per sha and kept in memory (a failed read is tried again). */
export function cached(api: SectorApi): SectorApi {
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

/* the file names of CONTRACT section 3 (3.4 amended 2026-11-26: the index ticker lowercased, terminal-api's name rule) */
export const FILE = {
  meta: 'sector-meta',
  series: 'sector-series',
  day: (date: string) => `sector-day-${date}`,
  stocks: (indexTicker: string) => `sector-stocks-${indexTicker.toLowerCase()}`,
};
