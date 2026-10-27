/* The backtest worker's private HTTP API (CONTRACT.md section 8; edge-bff app/backtest.py WorkerClient is its only
   caller). JSON in and out; every route except /health needs x-backtest-worker-key = BACKTEST_WORKER_KEY, else 401
   {"error":{"code":"UNAUTHORIZED"}}.

   GET  /health                   {ok: true, engine_version, registry_version}
   GET  /v1/catalog               Catalog (catalog.ts)
   POST /v1/validate {request}    200 {ok: true, lineage_key, variant_hash, tickers} | 422 (validate.ts on the reference
                                  ticker and broker lists, then run.ts checkPublished on terminal-api's manifests:
                                  FLOW_DATA_THROUGH, PERIOD_AFTER_DATA; no /bundle, no file)
   POST /v1/signals               SignalsPreviewRequest -> SignalsPreview, computed on the preview thread while the
                                  caller waits; one preview at a time, the next ones wait in arrival order
   POST /v1/jobs {job_id, request, context}
                                  202 {job_id} once the request passed validate.ts; the job starts at once on the job
                                  thread. 409 BUSY while another job runs; the same job_id again is 202 (edge-bff retries
                                  a POST whose answer it lost). A refused request is 422 and never becomes a job.
   GET  /v1/jobs/{id}             JobStatus; 404 UNKNOWN_JOB for any job but the latest (the worker keeps one job, and
                                  none after a restart)
   GET  /v1/jobs/{id}/result      200 gzip of the BacktestResult JSON (Content-Encoding gzip), as often as it is asked
                                  (a caller that lost an answer asks again); 409 NOT_FINISHED; kept until the next job
                                  starts (lead decision 2026-10-26), then 410 RESULT_GONE for the job it replaced; 404
                                  UNKNOWN_JOB for any older job
   POST /v1/jobs/{id}/cancel      202 JobStatus; a running job stops at its next check and ends CANCELLED (a result
                                  that completes after the cancel is dropped); an ended job is left as it is
   Errors: {"error": {code, field?, message?, details?}} with errors.ts statuses (validation 422, data 424, BUSY and
   NOT_FINISHED 409, UNKNOWN_JOB 404, TIMEOUT 504). A job, a preview, a validation and a catalog each get
   limits.timeout_seconds; a job or preview over it has its thread terminated (FAILED TIMEOUT / 504 TIMEOUT).
   Start: the registry artifact must match the files in the image (version.ts checkRegistry), else exit 1. Logs are
   JSON lines without secrets (no header, body, key or presigned URL). */
import crypto from 'node:crypto';
import http from 'node:http';
import { pathToFileURL } from 'node:url';
import type { JobState, JobStatus } from '../../edge-bff/backtest/src/core/contract.ts';
import { lineageKey, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import { buildCatalog } from './catalog.ts';
import { ComputeThread, TaskFailed, ThreadStopped, threadConfig } from './compute.ts';
import type { Outcome, Task } from './compute.ts';
import { describeConfig, loadConfig } from './config.ts';
import type { Config } from './config.ts';
import { WorkerError, invalid, toApiError } from './errors.ts';
import type { ErrorBody } from './errors.ts';
import { errorFields, log } from './log.ts';
import { checkPublished } from './run.ts';
import { TerminalClient } from './terminal.ts';
import { checkRequest } from './validate.ts';
import type { References } from './validate.ts';
import { ENGINE_VERSION, REGISTRY_VERSION, checkRegistry } from './version.ts';

export const KEY_HEADER = 'x-backtest-worker-key';
export const JOB_ID = /^bt_[0-9a-f]{32}$/;            // edge-bff backtest.py JOB_ID ('bt_' + secrets.token_hex(16))
const HEX64 = /^[0-9a-f]{64}$/;
const ENDED: JobState[] = ['FINISHED', 'FAILED', 'CANCELLED'];

interface Job {
  id: string; status: JobStatus; gzip: Uint8Array | null; seq: number; t0: number;
  cancel: boolean; timer: NodeJS.Timeout | null; json_bytes: number | null;
}

export interface WorkerApp {
  server: http.Server;
  listen(port?: number, host?: string): Promise<number>;
  close(): Promise<void>;
  /** for tests: the threads and the current job */
  threads: { jobs: ComputeThread; previews: ComputeThread };
}

const send = (res: http.ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}) => {
  const b = Buffer.from(JSON.stringify(body));
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': String(b.length), 'cache-control': 'no-store', ...headers });
  res.end(b);
};
const fail = (res: http.ServerResponse, status: number, error: ErrorBody) => send(res, status, { error });

/** The body as JSON (null when empty), or 422 INVALID_JSON. */
function parseJson(body: Buffer | null): unknown {
  const text = body ? body.toString('utf8') : '';
  try { return text ? JSON.parse(text) : null } catch { throw new WorkerError(422, 'INVALID_JSON', 'The request body is not JSON.') }
}
const sameKey = (given: string | string[] | undefined, key: Buffer) => {
  if (typeof given !== 'string') return false;
  const g = Buffer.from(given);
  return g.length === key.length && crypto.timingSafeEqual(g, key);
};
/** A promise that rejects with 504 TIMEOUT after `seconds` (and its timer, to clear). */
function deadline(seconds: number, what: string): { promise: Promise<never>; clear(): void } {
  let t: NodeJS.Timeout;
  const promise = new Promise<never>((_, no) => { t = setTimeout(() => no(new WorkerError(504, 'TIMEOUT', `${what} took longer than ${seconds} s.`)), seconds * 1000) });
  promise.catch(() => {});
  return { promise, clear: () => clearTimeout(t) };
}

export function createApp(cfg: Config): WorkerApp {
  const versions = { engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION };
  const tc = threadConfig(cfg);
  const threads = { jobs: new ComputeThread('jobs', tc, versions), previews: new ComputeThread('previews', tc, versions) };
  // the HTTP thread's own client: reference lists, and IHSG's files for the catalog
  const client = new TerminalClient({ ...cfg.terminal, log: (event, fields) => log('info', event, { thread: 'http', ...fields }) });
  const key = Buffer.from(cfg.workerKey);
  const timeout = cfg.limits.timeout_seconds;
  let job: Job | null = null, starting = false;
  let replaced: string | null = null;                   // the FINISHED job the current one replaced: its result is gone

  const refs = async (): Promise<References> => {
    const [tickers, brokers] = await Promise.all([client.reference('tickers'), client.reference('brokers')]);
    return { tickers, brokers };
  };
  const within = async <T>(what: string, work: Promise<T>): Promise<T> => {
    const d = deadline(timeout, what);
    try { return await Promise.race([work, d.promise]) } finally { d.clear() }
  };

  /* ---- jobs ---- */
  const running = (j: Job) => !ENDED.includes(j.status.state);
  function end(j: Job, state: JobState, error: ErrorBody | null): void {
    if (!running(j)) return;
    if (j.timer) clearTimeout(j.timer);
    Object.assign(j.status, { state, error, finished_at: new Date().toISOString(), duration_ms: Math.round(performance.now() - j.t0) });
    log(state === 'FAILED' ? 'warn' : 'info', 'job_end', { job_id: j.id, state, code: error?.code ?? null, ms: j.status.duration_ms, result_bytes: j.status.result_bytes, json_bytes: j.json_bytes });
  }
  function settle(j: Job, e: unknown): void {
    if (e instanceof TaskFailed) {
      if (e.serial.cancelled) end(j, 'CANCELLED', null);
      else end(j, 'FAILED', e.serial.error);
    } else if (e instanceof ThreadStopped && e.reason === 'killed') {
      // the server killed the thread for this job's time; the state was set there
    } else if (e instanceof ThreadStopped) {
      end(j, 'FAILED', answerError(e).error);
    } else {
      log('error', 'job_settle_failed', errorFields(e, true));
      end(j, 'FAILED', { code: 'INTERNAL_ERROR', message: 'The worker failed; the error is in its log.' });
    }
  }
  function startJob(id: string, task: Extract<Task, { kind: 'job' }>): Job {
    const at = new Date().toISOString();
    const j: Job = {
      id, gzip: null, seq: 0, t0: performance.now(), cancel: false, timer: null, json_bytes: null,
      status: { request_id: id, state: 'RUNNING', progress: { phase: 'queued', done: 0, total: 0 }, error: null, created_at: at, started_at: at, finished_at: null, duration_ms: null, result_bytes: null },
    };
    const { seq, done } = threads.jobs.run(task, p => { if (running(j)) j.status.progress = p });
    j.seq = seq;
    j.timer = setTimeout(() => {
      if (!running(j)) return;
      end(j, j.cancel ? 'CANCELLED' : 'FAILED', j.cancel ? null : { code: 'TIMEOUT', message: `The backtest took longer than ${timeout} s.` });
      threads.jobs.kill().catch(e => log('error', 'thread_kill_failed', errorFields(e)));
    }, timeout * 1000);
    j.timer.unref();
    done.then((o: Outcome) => {
      if (!running(j) || o.kind !== 'job') return;
      if (j.cancel) { end(j, 'CANCELLED', null); return }               // asked to stop: the late result is dropped
      j.gzip = o.gzip; j.json_bytes = o.json_bytes;
      j.status.result_bytes = o.gzip.byteLength;
      j.status.progress = { phase: 'finalizing', done: 1, total: 1 };
      end(j, 'FINISHED', null);
    }, e => settle(j, e));
    log('info', 'job_start', { job_id: id, prior_trials: task.context.prior_trials.length });
    return j;
  }

  function checkJobBody(b: unknown): { job_id: string; request: unknown; prior_trials: { variant_hash: string; sharpe_daily: number }[] } {
    if (!b || typeof b !== 'object' || Array.isArray(b)) throw invalid('INVALID_REQUEST', 'body', 'The body must be {job_id, request, context}.');
    const { job_id, request, context, ...rest } = b as Record<string, unknown>;
    const extra = Object.keys(rest)[0];
    if (extra) throw invalid('UNKNOWN_FIELD', extra, `${extra} is not a field of a job.`);
    if (typeof job_id !== 'string' || !JOB_ID.test(job_id)) throw invalid('INVALID_JOB_ID', 'job_id', 'job_id must be bt_ followed by 32 lowercase hex characters.');
    if (!context || typeof context !== 'object' || Array.isArray(context)) throw invalid('INVALID_CONTEXT', 'context', 'context is required.');
    const c = context as Record<string, unknown>;
    for (const k of Object.keys(c)) if (k !== 'job_id' && k !== 'prior_trials') throw invalid('UNKNOWN_FIELD', `context.${k}`, `context.${k} is not a field of the job context.`);
    if (c.job_id !== job_id) throw invalid('INVALID_CONTEXT', 'context.job_id', 'context.job_id must equal job_id.');
    if (!Array.isArray(c.prior_trials)) throw invalid('INVALID_CONTEXT', 'context.prior_trials', 'context.prior_trials must be a list.');
    const prior_trials = c.prior_trials.map((t: unknown, k: number) => {
      const f = `context.prior_trials[${k}]`, x = t as Record<string, unknown>;
      if (!t || typeof t !== 'object' || Array.isArray(t) || Object.keys(x).some(n => n !== 'variant_hash' && n !== 'sharpe_daily'))
        throw invalid('INVALID_CONTEXT', f, `${f} must be {variant_hash, sharpe_daily}.`);
      if (typeof x.variant_hash !== 'string' || !HEX64.test(x.variant_hash)) throw invalid('INVALID_CONTEXT', `${f}.variant_hash`, `${f}.variant_hash must be a sha256 hex string.`);
      if (typeof x.sharpe_daily !== 'number' || !Number.isFinite(x.sharpe_daily)) throw invalid('INVALID_CONTEXT', `${f}.sharpe_daily`, `${f}.sharpe_daily must be a finite number.`);
      return { variant_hash: x.variant_hash, sharpe_daily: x.sharpe_daily };
    });
    return { job_id, request, prior_trials };
  }

  /* ---- previews: one at a time on the preview thread, the next ones wait in arrival order ---- */
  interface Waiting { task: Task; ok(o: Outcome): void; no(e: unknown): void; gone: boolean; seq: number | null }
  const queue: Waiting[] = [];
  let previewing: Waiting | null = null;
  function nextPreview(): void {
    if (previewing) return;
    const w = queue.shift();
    if (!w) return;
    previewing = w;
    const { seq, done } = threads.previews.run(w.task);
    w.seq = seq;
    done.then(w.ok, w.no).finally(() => { previewing = null; nextPreview() });
  }
  function preview(task: Task, res: http.ServerResponse): Promise<Outcome> {
    return new Promise<Outcome>((ok, no) => {
      const w: Waiting = { task, ok, no, gone: false, seq: null };
      const d = deadline(timeout, 'The signals preview');
      d.promise.catch(e => {
        if (w.gone) return;
        w.gone = true;
        const k = queue.indexOf(w);
        if (k >= 0) queue.splice(k, 1);
        else if (previewing === w) threads.previews.kill().catch(err => log('error', 'thread_kill_failed', errorFields(err)));
        no(e);
      });
      // the caller gave up (edge-bff's own timeout): stop computing for nobody
      res.on('close', () => {
        if (w.gone || res.writableFinished) return;
        w.gone = true;
        const k = queue.indexOf(w);
        if (k >= 0) queue.splice(k, 1);
        else if (previewing === w && w.seq !== null) threads.previews.cancel(w.seq);
      });
      w.ok = o => { d.clear(); if (!w.gone) { w.gone = true; ok(o) } };
      w.no = e => { d.clear(); if (!w.gone) { w.gone = true; no(e) } };
      queue.push(w);
      nextPreview();
    });
  }

  /* ---- routes ---- */
  async function route(req: http.IncomingMessage, res: http.ServerResponse, path: string, raw: Buffer | null): Promise<void> {
    const method = req.method ?? 'GET';
    const allow = (m: string) => { if (method !== m) throw new WorkerError(405, 'METHOD_NOT_ALLOWED', `Use ${m}.`) };
    if (path === '/health') { allow('GET'); return send(res, 200, { ok: true, ...versions }) }
    if (!sameKey(req.headers[KEY_HEADER], key)) return fail(res, 401, { code: 'UNAUTHORIZED' });

    if (path === '/v1/catalog') { allow('GET'); return send(res, 200, await within('The catalog', buildCatalog(client, cfg, versions))) }
    if (path === '/v1/validate') {
      allow('POST');
      const body = parseJson(raw) as { request?: unknown } | null;
      if (!body || typeof body !== 'object' || Array.isArray(body) || Object.keys(body).some(k => k !== 'request')) throw invalid('INVALID_REQUEST', 'body', 'The body must be {request}.');
      const out = await within('The validation', (async () => {
        const list = await refs(), checked = checkRequest(body.request, list, cfg);
        const q = body.request as Parameters<typeof variantHash>[0];
        await checkPublished(q, checked, list, { client, config: cfg });
        const [lineage_key, variant_hash] = await Promise.all([lineageKey(q), variantHash(q)]);
        return { ok: true, lineage_key, variant_hash, tickers: checked.tickers };
      })());
      return send(res, 200, out);
    }
    if (path === '/v1/signals') {
      allow('POST');
      const body = parseJson(raw);
      const o = await preview({ kind: 'signals', request: body, refs: await within('The reference list', refs()) }, res);
      return send(res, 200, o.kind === 'signals' ? o.preview : null);
    }
    if (path === '/v1/jobs') {
      allow('POST');
      const b = checkJobBody(parseJson(raw));
      if (job && job.id === b.job_id) return send(res, 202, { job_id: b.job_id });
      if (starting || (job && running(job))) return fail(res, 409, { code: 'BUSY', message: 'Another backtest is running.' });
      starting = true;
      let list: References;
      try { list = await within('The validation', refs()); checkRequest(b.request, list, cfg) }
      finally { starting = false }
      if (job && running(job)) return fail(res, 409, { code: 'BUSY', message: 'Another backtest is running.' });
      replaced = job && job.status.state === 'FINISHED' ? job.id : null;
      job = startJob(b.job_id, { kind: 'job', request: b.request, context: { prior_trials: b.prior_trials }, refs: list });   // the previous job and its result are dropped
      return send(res, 202, { job_id: b.job_id });
    }
    const m = /^\/v1\/jobs\/([^/]+)(\/result|\/cancel)?$/.exec(path);
    if (m) {
      const [, id, sub] = m;
      allow(sub === '/cancel' ? 'POST' : 'GET');
      const j = job && job.id === id ? job : null;
      if (!j && sub === '/result' && id === replaced) return fail(res, 410, { code: 'RESULT_GONE', message: 'A newer backtest has started on the worker; this result is no longer kept.' });
      if (!j) return fail(res, 404, { code: 'UNKNOWN_JOB' });
      if (!sub) return send(res, 200, j.status);
      if (sub === '/cancel') {
        if (running(j)) { j.cancel = true; threads.jobs.cancel(j.seq); log('info', 'job_cancel', { job_id: j.id }) }
        return send(res, 202, j.status);
      }
      if (j.status.state !== 'FINISHED') return fail(res, 409, { code: 'NOT_FINISHED' });
      const gz = j.gzip as Uint8Array;                                   // a FINISHED job has its result until it is replaced
      res.writeHead(200, { 'content-type': 'application/json', 'content-encoding': 'gzip', 'content-length': String(gz.byteLength), 'cache-control': 'no-store' });
      res.end(gz);
      return;
    }
    throw new WorkerError(404, 'NOT_FOUND', 'No such route.');
  }

  /** The answer of a failed request: a compute thread's error as the thread gave it, else errors.ts. */
  function answerError(e: unknown): { status: number; error: ErrorBody; known: boolean } {
    if (e instanceof TaskFailed) return e.serial;
    if (e instanceof ThreadStopped) return { status: 500, known: true, error: e.code === 'ERR_WORKER_OUT_OF_MEMORY'
      ? { code: 'OUT_OF_MEMORY', message: 'The computation ran out of memory; choose a smaller universe or period.' }
      : { code: 'INTERNAL_ERROR', message: 'The compute thread stopped; the error is in the worker log.' } };
    return toApiError(e);
  }

  const server = http.createServer((req, res) => {
    const t0 = performance.now(), path = (req.url ?? '/').split('?')[0];
    if (path !== '/health') res.once('close', () => log('info', 'http', { method: req.method, path, status: res.statusCode, ms: Math.round(performance.now() - t0) }));
    const failed = (e: unknown) => {
      const a = answerError(e);
      if (!a.known) log('error', 'request_failed', { path, ...errorFields(e, true) });
      if (res.destroyed) return;                                         // the caller is gone (a cancelled preview)
      if (!res.headersSent) fail(res, a.status, a.error); else res.destroy();
    };
    // the answer goes out once the request has been read to its end, so its connection stays usable for the caller's
    // pool (Node closes a connection whose request body was left unread); the body of a caller without the key, and
    // of /health, is read and dropped.
    const keep = path !== '/health' && sameKey(req.headers[KEY_HEADER], key), parts: Buffer[] = [];
    if (keep) req.on('data', (c: Buffer) => parts.push(c)); else req.resume();
    req.on('end', () => route(req, res, path, keep && parts.length ? Buffer.concat(parts) : null).catch(failed));
    req.on('error', () => res.destroy());
  });
  server.keepAliveTimeout = 5000;

  return {
    server, threads,
    listen: (port = cfg.port, host = '0.0.0.0') => new Promise((ok, no) => {
      server.once('error', no);
      server.listen(port, host, () => { server.off('error', no); ok((server.address() as { port: number }).port) });
    }),
    close: async () => {
      await new Promise<void>(ok => { server.close(() => ok()); server.closeAllConnections() });
      await Promise.all([threads.jobs.kill(), threads.previews.kill()]);
    },
  };
}

async function main(): Promise<void> {
  let cfg: Config;
  try { cfg = loadConfig() } catch (e) { log('error', 'config_invalid', { message: (e as Error).message }); process.exit(1) }
  const reg = await checkRegistry();
  if (!reg.ok) { log('error', 'registry_mismatch', { registry_version: reg.expected, sources_hash: reg.found }); process.exit(1) }
  const app = createApp(cfg);
  const port = await app.listen();
  log('info', 'start', { ...describeConfig(cfg), port, engine_version: ENGINE_VERSION, registry_version: REGISTRY_VERSION, node: process.version });
  const stop = (signal: string) => { log('info', 'stop', { signal }); app.close().finally(() => process.exit(0)) };
  process.once('SIGTERM', () => stop('SIGTERM'));
  process.once('SIGINT', () => stop('SIGINT'));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
