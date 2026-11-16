/* The worker's configuration, read once from the environment and checked; a missing or invalid variable is an error
   that names the variable, never its value (the keys are secrets).

   PORT                          HTTP port (8080: the port Railway routes to, as the other services of the repository)
   BACKTEST_WORKER_KEY           shared secret edge-bff sends as x-backtest-worker-key (>= 32 characters, as edge-bff's
                                 config.py requires of the same value)
   TERMINAL_URL, TERMINAL_PROXY_KEY, BACKTEST_CACHE_BYTES, BACKTEST_DOWNLOAD_CONCURRENCY, BACKTEST_DOWNLOAD_RETRIES,
   BACKTEST_RETRY_BASE_MS, BACKTEST_HTTP_TIMEOUT_MS, BACKTEST_FILE_ORIGIN, BACKTEST_MAX_FILE_BYTES, BACKTEST_CACHE_DIR,
   BACKTEST_CACHE_DIR_BYTES      the terminal-api client (terminal.ts optionsFromEnv; all required except the disk cache)
   BACKTEST_MAX_DOWNLOAD_BYTES   bytes of published files one job or preview may read (manifest sizes)   } required: the
   BACKTEST_MAX_BROKER_ROWS      broker rows one job or preview may read (manifest rows)                 } limits are
   BACKTEST_TIMEOUT_SECONDS      longest a job, a signals preview or a validation may take               } measured in
   BACKTEST_MAX_CONDITIONS       enabled conditions one list (entry, exit signals) may have              } the dev E2E (K7b)
   BACKTEST_MAX_RESULT_BYTES     the most JSON a job's result may have (validate.ts, compute.ts); the    }
                                 same value as edge-bff's BACKTEST_MAX_RESULT_BYTES, which refuses a     }
                                 larger result anyway: the worker stops before it packs or sends one     }
   BACKTEST_MAX_POSITIONS        default engine.ts MAX_POSITIONS = the page's Max positions input (its max is the
                                 catalog's limits.max_positions); may only be lowered
   BACKTEST_MAX_PORTFOLIO_TICKERS
                                 default engine.ts MAX_PORTFOLIO_TICKERS (12, user N 2026-10-27) = the most stocks one
                                 portfolio or preview may pick (the page reads limits.max_portfolio_tickers); may only be
                                 lowered
   BACKTEST_MONTE_CARLO_RUNS     default 1000 = the page's monteCarlo(T, cap0, runs = 1000)
   BACKTEST_QUEUED_PER_OWNER     default 3 = edge-bff's BACKTEST_QUEUED_PER_OWNER default (edge-bff enforces it; the
                                 catalog only reports it)
   BACKTEST_FLOW_ENABLED         '1' turns the flow and broker conditions and rank_by 'fnet' on; anything else but unset,
                                 '' or '0' is an error. Off when unset. The published broker files were verified against
                                 the SQL source (verification/backtest/FLOW_DATA_CHECK.md: 12 tickers, every published
                                 year, 0 mismatches, values in IDR), and the deployment sets it to 1 (lead decision
                                 2026-10-26).
   BACKTEST_THREAD_HEAP_MB       optional: the V8 heap limit of each compute thread in MB (0 = none); unset, it is derived
                                 from the container's memory (threadHeapMb; ERRORS M463, user 2026-11-16 "Go untuk opsi 1")
   The entry window (1-20 bars) is not configurable: it is the page's "within N bars" input, which conditions.ts enforces. */
import fs from 'node:fs';
import type { Limits } from '../../edge-bff/backtest/src/core/contract.ts';
import { WINDOW_BARS } from '../../edge-bff/backtest/src/core/conditions.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import { optionsFromEnv } from './terminal.ts';
import type { TerminalOptions } from './terminal.ts';

export const DEFAULT_PORT = 8080;
export const DEFAULT_MONTE_CARLO_RUNS = 1000;       // backtest.html monteCarlo(T, cap0, runs = 1000)
export const DEFAULT_QUEUED_PER_OWNER = 3;          // edge-bff config.py backtest_queued_per_owner
/** EXEC-BACKTEST-REVAMP P3 (K9 b: the worker keeps 1 GB): distinct Flow series one request may read (each is one
    computeFlow per picked stock over its whole broker history). */
export const DEFAULT_MAX_FLOW_SERIES = 8;
export const KEY_MIN_LENGTH = 32;                   // edge-bff config.py: BACKTEST_WORKER_KEY must be at least 32 characters
export const FLOW_OFF_REASON = 'The flow and broker conditions are switched off on this worker (BACKTEST_FLOW_ENABLED is not 1).';

/** ERRORS M463 (user 2026-11-16 "Go untuk opsi 1"): the memory the container may use (cgroup v2 memory.max, else v1
    memory.limit_in_bytes), or null when it is unlimited or cannot be read (a laptop: no cap is derived). */
export function containerMemoryBytes(read: (path: string) => string = p => fs.readFileSync(p, 'utf8')): number | null {
  for (const p of ['/sys/fs/cgroup/memory.max', '/sys/fs/cgroup/memory/memory.limit_in_bytes']) {
    let t: string;
    try { t = read(p).trim() } catch { continue }
    if (t === 'max') return null;
    const n = Number(t);
    return /^\d+$/.test(t) && n > 0 && n < 2 ** 50 ? n : null;      // v1 writes a huge number for "no limit"
  }
  return null;
}
/** The HTTP thread's share of the container (its own heap, the jobs' results kept for edge-bff, Node itself): measured
    107-135 MB at start and up to 187-360 MB after tasks (2026-11-16, ERRORS M463). */
export const MAIN_RESERVE_BYTES = 256 * 2 ** 20;
/** Each compute thread's V8 heap limit in MB: the container's memory less the HTTP thread's reserve, shared by the two
    compute threads (a preview and a job may run at once), and half of a thread's share for its heap: the other half is
    memory outside the heap (the decoded files' buffers, the broker columns' typed arrays), which a heap limit does not
    bound (measured 2026-11-16: a thread capped at 300 MB used up to about 640 MB). A thread over its limit ends with
    ERR_WORKER_OUT_OF_MEMORY and only its task fails (server.ts answerError: OUT_OF_MEMORY), instead of the container
    killing every task. The container's limit changes it without a code change; null: no limit (none known). */
export function threadHeapMb(memory: number | null): number | null {
  if (memory === null) return null;
  return Math.max(64, Math.floor((memory - MAIN_RESERVE_BYTES) / 2 / 2 / 2 ** 20));
}

export interface Config {
  port: number;
  workerKey: string;
  terminal: TerminalOptions;
  limits: Limits;
  maxResultBytes: number;            // BACKTEST_MAX_RESULT_BYTES (not a catalog limit: the page cannot act on it)
  flow: { enabled: boolean; reason: string | null };
  /** M463: the container's memory (null: unknown) and each compute thread's heap limit in MB (null: none) */
  memory: { container_bytes: number | null; thread_heap_mb: number | null };
}

type Env = Record<string, string | undefined>;

/** The configuration, or an Error naming the first variable that is missing or invalid. */
export function loadConfig(env: Env = process.env, container: number | null = containerMemoryBytes()): Config {
  const raw = (k: string) => (env[k] ?? '').trim();
  const need = (k: string) => { const v = raw(k); if (!v) throw new Error(`${k} is required.`); return v };
  const whole = (k: string, min: number, max = Number.MAX_SAFE_INTEGER, def?: number) => {
    const s = raw(k);
    if (!s) { if (def === undefined) throw new Error(`${k} is required.`); return def }
    const v = Number(s);
    if (!/^\d+$/.test(s) || !Number.isSafeInteger(v) || v < min || v > max) throw new Error(`${k} must be a whole number from ${min}${max < Number.MAX_SAFE_INTEGER ? ` to ${max}` : ''}.`);
    return v;
  };
  const port = whole('PORT', 1, 65535, DEFAULT_PORT);
  const workerKey = need('BACKTEST_WORKER_KEY');
  if (workerKey.length < KEY_MIN_LENGTH) throw new Error(`BACKTEST_WORKER_KEY must be at least ${KEY_MIN_LENGTH} characters.`);
  const terminal = optionsFromEnv(env);
  const flowRaw = raw('BACKTEST_FLOW_ENABLED');
  if (!['', '0', '1'].includes(flowRaw)) throw new Error('BACKTEST_FLOW_ENABLED must be 1 (on) or 0 (off).');
  const enabled = flowRaw === '1';
  const limits: Limits = {
    max_positions: whole('BACKTEST_MAX_POSITIONS', 1, MAX_POSITIONS, MAX_POSITIONS),
    window_bars: { min: WINDOW_BARS.min, max: WINDOW_BARS.max },
    monte_carlo_runs: whole('BACKTEST_MONTE_CARLO_RUNS', 1, Number.MAX_SAFE_INTEGER, DEFAULT_MONTE_CARLO_RUNS),
    max_portfolio_tickers: whole('BACKTEST_MAX_PORTFOLIO_TICKERS', 1, MAX_PORTFOLIO_TICKERS, MAX_PORTFOLIO_TICKERS),
    max_download_bytes: whole('BACKTEST_MAX_DOWNLOAD_BYTES', 1),
    max_broker_rows: whole('BACKTEST_MAX_BROKER_ROWS', 0),
    timeout_seconds: whole('BACKTEST_TIMEOUT_SECONDS', 1),
    queued_per_owner: whole('BACKTEST_QUEUED_PER_OWNER', 1, Number.MAX_SAFE_INTEGER, DEFAULT_QUEUED_PER_OWNER),
    max_conditions: whole('BACKTEST_MAX_CONDITIONS', 1),
    max_flow_series: whole('BACKTEST_MAX_FLOW_SERIES', 1, Number.MAX_SAFE_INTEGER, DEFAULT_MAX_FLOW_SERIES),
  };
  const maxResultBytes = whole('BACKTEST_MAX_RESULT_BYTES', 1);
  const heapSet = raw('BACKTEST_THREAD_HEAP_MB') !== '';
  const heap = heapSet ? whole('BACKTEST_THREAD_HEAP_MB', 0) : threadHeapMb(container);
  return { port, workerKey, terminal, limits, maxResultBytes, flow: { enabled, reason: enabled ? null : FLOW_OFF_REASON },
    memory: { container_bytes: container, thread_heap_mb: heap ? heap : null } };
}

/** What may be logged of a configuration: no key, no URL credentials. */
export function describeConfig(c: Config): Record<string, unknown> {
  const t = c.terminal;
  return {
    port: c.port, limits: c.limits, max_result_bytes: c.maxResultBytes, flow_enabled: c.flow.enabled, memory: c.memory,
    terminal: { origin: new URL(t.url).origin, file_origin: t.fileOrigin, max_file_bytes: t.maxFileBytes, cache_bytes: t.cacheBytes, cache_dir: !!t.cacheDir, cache_dir_bytes: t.cacheDirBytes ?? null,
      concurrency: t.concurrency, retries: t.retries, retry_base_ms: t.retryBaseMs, timeout_ms: t.timeoutMs },
  };
}
