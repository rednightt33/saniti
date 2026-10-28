/* The screener-worker's configuration, read once from the environment and checked (report TARGET ARCHITECTURE 6.17,
   API CONTRACT 8.9). Every limit is a variable with NO default (the backtest worker's convention): the service does
   not start without it, and a missing or invalid variable is an error that names the variable, never its value (the
   keys are secrets). PORT alone has the repository's default (8080, the port Railway routes to).

   PORT                          HTTP port
   SCREENER_WORKER_KEY           shared secret edge-bff sends as x-screener-worker-key (>= 32 characters, contract.ts
                                 WORKER_KEY_MIN_LENGTH, as edge-bff config.py requires of the same value)
   TERMINAL_URL                  terminal-api origin (private network), without user name, password or path
   TERMINAL_PROXY_KEY            the gateway key (>= 32 characters): GET /state, POST /xsection, GET /manifest,
                                 GET /reference
   SCREENER_FILE_ORIGIN          the bucket origin every presigned URL must have (the backtest's BACKTEST_FILE_ORIGIN
                                 rule, terminal.ts fileOriginOf: scheme://host[:port], a host may start with '*.')
   SCREENER_THREADS              K, the compute threads (worker_threads) that run screens, previews and counts
   SCREENER_CACHE_BYTES          the bytes the series LRU (custom parameters) and the result cache may hold in total on
                                 one replica: split in K + 1 equal shares, one per compute thread's series LRU and one
                                 for the result cache (the pinned snapshot is not counted: it is the publication)
   SCREENER_CACHE_DIR            optional: the directory of the file cache by sha256 (terminal.ts DiskCache; the
                                 container's own disk, report 6d.4: no volume); with it SCREENER_CACHE_DIR_BYTES
   SCREENER_DOWNLOAD_CONCURRENCY HTTP requests in flight to terminal-api and the bucket (the 845 /manifest reads)
   SCREENER_DOWNLOAD_RETRIES     retries of a network error or a 5xx; also the quick retries of a skewed /xsection
   SCREENER_RETRY_BASE_MS        backoff base: retry k waits base x 2^k
   SCREENER_HTTP_TIMEOUT_MS      longest one HTTP request may take, body included
   SCREENER_MAX_CPU_MS           compute_budget: a request whose worst case is costed above it is refused before compute
   SCREENER_CAP_BUDGET_MS        the length caps (registry.ts capOf); a budget whose caps fall below a default is refused
   SCREENER_DEADLINE_MS          longest a request may take from arrival (queue included) -> 504 TIMEOUT
   SCREENER_MAX_CONDITIONS       enabled conditions per definition
   SCREENER_MAX_METRIC_FILTERS   universe metric filters per definition
   SCREENER_WITHIN_MAX           the longest `within`; the snapshot tail is this + 1 bars (metrics.ts tailLength)
   SCREENER_MAX_COUNTS           definitions per counts request
   SCREENER_MAX_RESPONSE_BYTES   JSON bytes of one answer
   SCREENER_QUEUE                requests waiting for a thread on this replica (every owner) -> 409 BUSY beyond it
   SCREENER_OWNER_INFLIGHT       requests of one owner tag running at once on this replica (the owner's lane)
   SCREENER_OWNER_CPU_MS         P33 (user 2026-10-28, built in Phase 1): thread milliseconds one owner tag may use per
                                 minute on this replica; a request that would pass it is refused with its wait
   SCREENER_PREVIOUS_GRACE_S     seconds the previous snapshot keeps serving requests pinned to it after a swap
   SCREENER_MAX_FILE_BYTES       gzip bytes of one xsection file (checked on the index before any grant)
   SCREENER_MAX_INFLATED_BYTES   bytes one file may inflate to (TerminalClient maxFileBytes, inflateVerified)
   SCREENER_MAX_REFRESH_BYTES    gzip bytes one refresh may download in total
   SCREENER_MAX_REQUEST_BYTES    bytes of one request body (edge-bff's own body limit is 131,072)
   Added to the report's list (6.17), each because a component needs a value and the rule is "no default": the four
   download settings and the disk budget (TerminalOptions requires them), SCREENER_OWNER_CPU_MS (P33) and
   SCREENER_MAX_REQUEST_BYTES (a body the worker reads must be bounded). */
import { capProblems } from '../../edge-bff/screener/src/core/registry.ts';
import { WORKER_KEY_MIN_LENGTH } from '../../edge-bff/screener/src/core/contract.ts';
import { fileOriginOf } from '../../backtest-worker/src/terminal.ts';
import type { TerminalOptions } from '../../backtest-worker/src/terminal.ts';

export const DEFAULT_PORT = 8080;

export interface Limits {
  max_cpu_ms: number; cap_budget_ms: number; deadline_ms: number; max_conditions: number; max_metric_filters: number;
  within_max: number; max_counts: number; max_response_bytes: number; queue: number; owner_inflight: number;
  owner_cpu_ms: number; previous_grace_s: number; max_file_bytes: number; max_inflated_bytes: number;
  max_refresh_bytes: number; max_request_bytes: number;
}
export interface Config {
  port: number;
  workerKey: string;
  threads: number;
  cacheBytes: number;
  terminal: TerminalOptions;          // the backtest worker's client options (maxFileBytes = SCREENER_MAX_INFLATED_BYTES)
  limits: Limits;
}

type Env = Record<string, string | undefined>;

/** The configuration, or an Error naming the first variable that is missing or invalid. */
export function loadConfig(env: Env = process.env): Config {
  const raw = (k: string) => (env[k] ?? '').trim();
  const need = (k: string) => { const v = raw(k); if (!v) throw new Error(`${k} is required.`); return v };
  const whole = (k: string, min: number, def?: number) => {
    const s = raw(k);
    if (!s) { if (def === undefined) throw new Error(`${k} is required.`); return def }
    const v = Number(s);
    if (!/^\d+$/.test(s) || !Number.isSafeInteger(v) || v < min) throw new Error(`${k} must be a whole number of at least ${min}.`);
    return v;
  };
  const port = whole('PORT', 1, DEFAULT_PORT);
  if (port > 65535) throw new Error('PORT must be a whole number from 1 to 65535.');
  const workerKey = need('SCREENER_WORKER_KEY');
  if (workerKey.length < WORKER_KEY_MIN_LENGTH) throw new Error(`SCREENER_WORKER_KEY must be at least ${WORKER_KEY_MIN_LENGTH} characters.`);
  const url = need('TERMINAL_URL').replace(/\/+$/, '');
  let parsed: URL | null = null;
  try { parsed = new URL(url) } catch { /* refused below */ }
  if (!parsed || !/^https?:\/\/[^/?#]+$/.test(url)) throw new Error('TERMINAL_URL must be an http(s) origin without a path.');
  if (parsed.username || parsed.password) throw new Error('TERMINAL_URL must not contain a user name or password.');
  const proxyKey = need('TERMINAL_PROXY_KEY');
  if (proxyKey.length < 32) throw new Error('TERMINAL_PROXY_KEY must be at least 32 characters.');
  const fileOrigin = need('SCREENER_FILE_ORIGIN');
  if (!fileOriginOf(fileOrigin)) throw new Error('SCREENER_FILE_ORIGIN must be scheme://host[:port], http or https, the host lowercase and optionally starting with *.');
  const cacheDir = raw('SCREENER_CACHE_DIR') || undefined;
  const limits: Limits = {
    max_cpu_ms: whole('SCREENER_MAX_CPU_MS', 1),
    cap_budget_ms: whole('SCREENER_CAP_BUDGET_MS', 1),
    deadline_ms: whole('SCREENER_DEADLINE_MS', 1),
    max_conditions: whole('SCREENER_MAX_CONDITIONS', 1),
    max_metric_filters: whole('SCREENER_MAX_METRIC_FILTERS', 0),
    within_max: whole('SCREENER_WITHIN_MAX', 1),
    max_counts: whole('SCREENER_MAX_COUNTS', 1),
    max_response_bytes: whole('SCREENER_MAX_RESPONSE_BYTES', 1),
    queue: whole('SCREENER_QUEUE', 0),
    owner_inflight: whole('SCREENER_OWNER_INFLIGHT', 1),
    owner_cpu_ms: whole('SCREENER_OWNER_CPU_MS', 1),
    previous_grace_s: whole('SCREENER_PREVIOUS_GRACE_S', 0),
    max_file_bytes: whole('SCREENER_MAX_FILE_BYTES', 1),
    max_inflated_bytes: whole('SCREENER_MAX_INFLATED_BYTES', 1),
    max_refresh_bytes: whole('SCREENER_MAX_REFRESH_BYTES', 1),
    max_request_bytes: whole('SCREENER_MAX_REQUEST_BYTES', 1),
  };
  // a budget whose caps would refuse a registry default (and so the snapshot's own pre-warm) is a configuration error
  const caps = capProblems(limits.cap_budget_ms);
  if (caps.length) throw new Error(`SCREENER_CAP_BUDGET_MS is too low: ${caps.join('; ')}.`);
  if (limits.owner_cpu_ms < limits.max_cpu_ms) throw new Error('SCREENER_OWNER_CPU_MS must be at least SCREENER_MAX_CPU_MS (an owner must be able to run one admitted request per minute).');
  const terminal: TerminalOptions = {
    url, proxyKey, cacheBytes: 0, cacheDir, cacheDirBytes: cacheDir ? whole('SCREENER_CACHE_DIR_BYTES', 1) : undefined,
    concurrency: whole('SCREENER_DOWNLOAD_CONCURRENCY', 1), retries: whole('SCREENER_DOWNLOAD_RETRIES', 0),
    retryBaseMs: whole('SCREENER_RETRY_BASE_MS', 0), timeoutMs: whole('SCREENER_HTTP_TIMEOUT_MS', 1),
    fileOrigin, maxFileBytes: limits.max_inflated_bytes,
  };
  return { port, workerKey, threads: whole('SCREENER_THREADS', 1), cacheBytes: whole('SCREENER_CACHE_BYTES', 0), terminal, limits };
}

/** The share of SCREENER_CACHE_BYTES each cache gets (header: K + 1 equal shares). */
export const cacheShare = (c: Pick<Config, 'cacheBytes' | 'threads'>): number => Math.floor(c.cacheBytes / (c.threads + 1));

/** What may be logged of a configuration: no key, no URL credentials. */
export function describeConfig(c: Config): Record<string, unknown> {
  const t = c.terminal;
  return {
    port: c.port, threads: c.threads, cache_bytes: c.cacheBytes, limits: c.limits,
    terminal: { origin: new URL(t.url).origin, file_origin: t.fileOrigin, max_file_bytes: t.maxFileBytes, cache_dir: !!t.cacheDir,
      cache_dir_bytes: t.cacheDirBytes ?? null, concurrency: t.concurrency, retries: t.retries, retry_base_ms: t.retryBaseMs, timeout_ms: t.timeoutMs },
  };
}
