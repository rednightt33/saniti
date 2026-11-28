/* EXEC-RADAR R7: the page's only data path, edge-bff's /api/v1/radar (app/radar.py) with this EDGE session. A file is
   asked for with its sha256, so the browser keeps it for good under that URL and a newer publication is a new URL. */
import { accessText, isAccessRefusal, readError } from '../../shared/edge-session.ts';
import type { RadarApi, RadarIndex } from './types.ts';
import { issuerLogoSrc, readIssuerLogos } from '../../shared/issuer-logos.ts';

export class RadarError extends Error {
  constructor(public code: string, message: string, public status: number) { super(message) }
}

async function getJson<T>(url: string): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, { credentials: 'same-origin', headers: { accept: 'application/json' } });
  } catch {
    throw new RadarError('OFFLINE', 'The Radar could not reach EDGE. Check the connection and reload the page.', 0);
  }
  if (r.status === 401) throw new RadarError('SIGNED_OUT', 'Your EDGE session ended. Sign in again, then open the Radar.', 401);
  let body: any = null;
  try { body = await r.json() } catch { body = null }
  if (!r.ok) {
    // EXEC-MU-ACCOUNTS Phase 0 (M471): a plan refusal keeps the session and is shown as its message (shared/edge-session.ts)
    const info = readError(r.status, body, r.headers.get('Retry-After'));
    if (isAccessRefusal(info)) throw new RadarError(info.code, accessText(info) as string, r.status);
    const e = body?.error;
    throw new RadarError(e?.code || 'RADAR_UNAVAILABLE', e?.message || 'The Radar data could not be read. Try again in a minute.', r.status);
  }
  return body as T;
}

const pageApi = (base: string): RadarApi => ({
  index: () => getJson<RadarIndex>(`${base}/index`),
  file: <T>(name: string, sha: string) => getJson<T>(`${base}/file/${encodeURIComponent(name)}?sha=${sha}`),
});
// the Terminal's issuer logos (EXEC-RADAR-VIEW): the Watchlist's list and images; a viewer without them sees monograms
export const live: RadarApi = { ...pageApi('/api/v1/radar'), logos: () => readIssuerLogos(() => getJson('/api/terminal/v1/reference/logos')).catch(() => ({})), logoSrc: issuerLogoSrc };
/* EXEC-MU-ACCOUNTS 3e, the example mode (user 2026-11-21; ERRORS M527): the files of the page's opening view on one past
   date, for <tab>.example (edge-bff app/examples.py), in the same shapes as the live files */
export const example = pageApi('/api/v1/examples/radar');

/** One copy of each file per page: a file is fetched once per sha and kept in memory. */
export function cached(api: RadarApi): RadarApi & { reset(): void } {
  const files = new Map<string, Promise<any>>();
  return {
    index: () => api.index(),
    logos: api.logos, logoSrc: api.logoSrc,
    file<T>(name: string, sha: string): Promise<T> {
      const k = `${name}@${sha}`;
      if (!files.has(k)) files.set(k, api.file<T>(name, sha).catch(e => { files.delete(k); throw e }));
      return files.get(k) as Promise<T>;
    },
    reset() { files.clear() },
  };
}
