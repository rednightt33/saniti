/* Shared test helpers: a configuration for a local worker against the fake terminal-api, an HTTP client, waiting. */
import http from 'node:http';
import zlib from 'node:zlib';
import { loadConfig } from '../src/config.ts';
import type { Config } from '../src/config.ts';
import { setLogSink } from '../src/log.ts';

export const KEY = 'k'.repeat(40);
export const PROXY = 'p'.repeat(40);
export const OWNER_A = 'a'.repeat(16), OWNER_B = 'b'.repeat(16);

/** Every limit set (no default exists); overrides by variable name. */
export function envFor(url: string, over: Record<string, string> = {}): Record<string, string> {
  return {
    SCREENER_WORKER_KEY: KEY, TERMINAL_URL: url, TERMINAL_PROXY_KEY: PROXY, SCREENER_FILE_ORIGIN: url,
    SCREENER_THREADS: '2', SCREENER_THREAD_HEAP_MB: '512', SCREENER_CACHE_BYTES: String(64 * 1024 * 1024),
    SCREENER_DOWNLOAD_CONCURRENCY: '8', SCREENER_DOWNLOAD_RETRIES: '1', SCREENER_RETRY_BASE_MS: '10', SCREENER_HTTP_TIMEOUT_MS: '10000',
    SCREENER_MAX_CPU_MS: '20000', SCREENER_CAP_BUDGET_MS: '10000', SCREENER_DEADLINE_MS: '20000', SCREENER_MAX_CONDITIONS: '20',
    SCREENER_MAX_METRIC_FILTERS: '8', SCREENER_WITHIN_MAX: '130', SCREENER_MAX_COUNTS: '50', SCREENER_MAX_RESPONSE_BYTES: String(2 * 1024 * 1024),
    SCREENER_QUEUE: '4', SCREENER_OWNER_INFLIGHT: '2', SCREENER_OWNER_CPU_MS: '60000', SCREENER_PREVIOUS_GRACE_S: '600',
    SCREENER_MAX_FILE_BYTES: String(64 * 1024 * 1024), SCREENER_MAX_INFLATED_BYTES: String(256 * 1024 * 1024), SCREENER_MAX_REFRESH_BYTES: String(128 * 1024 * 1024),
    SCREENER_MAX_REQUEST_BYTES: '131072',
    ...over,
  };
}
export const configFor = (url: string, over: Record<string, string> = {}): Config => loadConfig(envFor(url, over));

/** Log lines (parsed) while a test runs. */
export function captureLogs(): { lines: Record<string, any>[]; events(name: string): Record<string, any>[] } {
  const lines: Record<string, any>[] = [];
  setLogSink(l => { try { lines.push(JSON.parse(l)) } catch { /* not ours */ } });
  return { lines, events: name => lines.filter(l => l.event === name) };
}

export interface Answer { status: number; headers: http.IncomingHttpHeaders; body: any; raw: Buffer }
/** One request to the worker; gzip answers inflated; JSON parsed. */
export function call(port: number, method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<Answer> {
  return new Promise((ok, no) => {
    const data = body === undefined ? null : Buffer.from(typeof body === 'string' ? body : JSON.stringify(body));
    const req = http.request({ host: '127.0.0.1', port, method, path, headers: { 'accept-encoding': 'gzip', ...(data ? { 'content-type': 'application/json', 'content-length': String(data.length) } : {}), ...headers } }, res => {
      const parts: Buffer[] = [];
      res.on('data', c => parts.push(c));
      res.on('end', () => {
        let raw = Buffer.concat(parts);
        if (res.headers['content-encoding'] === 'gzip') raw = zlib.gunzipSync(raw);
        let parsed: any = null;
        try { parsed = raw.length ? JSON.parse(raw.toString()) : null } catch { parsed = raw.toString() }
        ok({ status: res.statusCode ?? 0, headers: res.headers, body: parsed, raw });
      });
    });
    req.on('error', no);
    if (data) req.write(data);
    req.end();
  });
}
export const auth = (owner?: string): Record<string, string> => ({ 'x-screener-worker-key': KEY, ...(owner ? { 'x-screener-owner': owner } : {}) });

export async function until(cond: () => boolean | Promise<boolean>, ms = 30000, step = 25): Promise<void> {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await cond()) return; await new Promise(r => setTimeout(r, step)) }
  throw new Error(`condition not met within ${ms} ms`);
}
export const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));
