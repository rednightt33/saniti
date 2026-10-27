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
   The entry window (1-20 bars) is not configurable: it is the page's "within N bars" input, which conditions.ts enforces. */
import type { Limits } from '../../edge-bff/backtest/src/core/contract.ts';
import { WINDOW_BARS } from '../../edge-bff/backtest/src/core/conditions.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from '../../edge-bff/backtest/src/core/engine.ts';
import { optionsFromEnv } from './terminal.ts';
import type { TerminalOptions } from './terminal.ts';

export const DEFAULT_PORT = 8080;
export const DEFAULT_MONTE_CARLO_RUNS = 1000;       // backtest.html monteCarlo(T, cap0, runs = 1000)
export const DEFAULT_QUEUED_PER_OWNER = 3;          // edge-bff config.py backtest_queued_per_owner
export const KEY_MIN_LENGTH = 32;                   // edge-bff config.py: BACKTEST_WORKER_KEY must be at least 32 characters
export const FLOW_OFF_REASON = 'The flow and broker conditions are switched off on this worker (BACKTEST_FLOW_ENABLED is not 1).';

export interface Config {
  port: number;
  workerKey: string;
  terminal: TerminalOptions;
  limits: Limits;
  maxResultBytes: number;            // BACKTEST_MAX_RESULT_BYTES (not a catalog limit: the page cannot act on it)
  flow: { enabled: boolean; reason: string | null };
}

type Env = Record<string, string | undefined>;

/** The configuration, or an Error naming the first variable that is missing or invalid. */
export function loadConfig(env: Env = process.env): Config {
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
  };
  const maxResultBytes = whole('BACKTEST_MAX_RESULT_BYTES', 1);
  return { port, workerKey, terminal, limits, maxResultBytes, flow: { enabled, reason: enabled ? null : FLOW_OFF_REASON } };
}

/** What may be logged of a configuration: no key, no URL credentials. */
export function describeConfig(c: Config): Record<string, unknown> {
  const t = c.terminal;
  return {
    port: c.port, limits: c.limits, max_result_bytes: c.maxResultBytes, flow_enabled: c.flow.enabled,
    terminal: { origin: new URL(t.url).origin, file_origin: t.fileOrigin, max_file_bytes: t.maxFileBytes, cache_bytes: t.cacheBytes, cache_dir: !!t.cacheDir, cache_dir_bytes: t.cacheDirBytes ?? null,
      concurrency: t.concurrency, retries: t.retries, retry_base_ms: t.retryBaseMs, timeout_ms: t.timeoutMs },
  };
}
