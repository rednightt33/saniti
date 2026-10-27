/* The compute threads (worker_threads, CONTRACT.md section 8): every job and every signals preview runs off the HTTP
   thread, so status, cancel and health stay answered while a backtest computes. Each thread is long-lived and keeps its
   own terminal-api client, so its memory cache (BACKTEST_CACHE_BYTES per thread) serves the next run of the same
   tickers; the server runs one task at a time per thread (one job thread, one preview thread).

   main thread  ComputeThread.run(task, onProgress) -> { seq, done }  (done resolves with the outcome or rejects with
                TaskFailed / ThreadStopped); cancel(seq) sets the shared flag (SharedArrayBuffer) to that task's number,
                which run.ts reads through hooks.shouldStop and answers with Cancelled; kill() terminates the thread
                (the next task starts a new one), for a task over its time.
   thread       runs the task (run.ts runJob / runSignals), posts progress, and for a job the result as gzip JSON (the
                serialisation and packing happen here, not on the HTTP thread; packResult: at most
                BACKTEST_MAX_RESULT_BYTES of JSON, LIMIT_EXCEEDED otherwise); an error crosses as errors.ts
                SerialError (its class does not survive the message). */
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import zlib from 'node:zlib';
import type { BacktestResult, JobContext, JobProgress, SignalsPreview } from '../../edge-bff/backtest/src/core/contract.ts';
import { Cancelled } from '../../edge-bff/backtest/src/core/engine.ts';
import type { Config } from './config.ts';
import { WorkerError, serialError } from './errors.ts';
import type { SerialError } from './errors.ts';
import { PlannedClient } from './load.ts';
import { errorFields, log, setLogSink, writeLine } from './log.ts';
import { runJob, runSignals } from './run.ts';
import type { References } from './validate.ts';

export type Task =
  | { kind: 'job'; request: unknown; context: Pick<JobContext, 'prior_trials'>; refs: References }
  | { kind: 'signals'; request: unknown; refs: References };
export type Outcome =
  | { kind: 'job'; gzip: Uint8Array; json_bytes: number; duration_ms: number }
  | { kind: 'signals'; preview: SignalsPreview };

/** What a thread needs: the configuration without functions (they cannot cross), the versions. */
export interface ThreadConfig { limits: Config['limits']; maxResultBytes: Config['maxResultBytes']; flow: Config['flow']; terminal: Omit<Config['terminal'], 'fetch' | 'log'> }
interface ThreadData { role: 'compute'; name: string; config: ThreadConfig; versions: { engine_version: string; registry_version: string }; flag: Int32Array }
type FromThread = { seq: number } & ({ type: 'progress'; progress: JobProgress } | { type: 'done'; outcome: Outcome } | { type: 'failed'; error: SerialError } | { type: 'log'; line: string });

/** The task ended with an error the thread reported (validation, data, cancellation, or an unexpected one). */
export class TaskFailed extends Error {
  serial: SerialError;
  constructor(serial: SerialError) { super(serial.error.code); this.name = 'TaskFailed'; this.serial = serial }
}
/** The thread is gone: killed by the server, or it crashed (e.g. ERR_WORKER_OUT_OF_MEMORY). */
export class ThreadStopped extends Error {
  reason: 'killed' | 'crashed'; code: string | null;
  constructor(reason: 'killed' | 'crashed', code: string | null = null) { super(`compute thread ${reason}${code ? ` (${code})` : ''}`); this.name = 'ThreadStopped'; this.reason = reason; this.code = code }
}

/** A job's result as gzip JSON in its own buffer (so it can be transferred). Over maxBytes of JSON (BACKTEST_MAX_RESULT_BYTES,
    edge-bff's measure: the bytes of the JSON text) it is refused before it is packed, LIMIT_EXCEEDED: edge-bff would
    not store it either. */
export function packResult(result: BacktestResult, maxBytes: number): { gzip: Uint8Array; json_bytes: number } {
  const text = JSON.stringify(result), json_bytes = Buffer.byteLength(text);
  if (json_bytes > maxBytes)
    throw new WorkerError(422, 'LIMIT_EXCEEDED', `The backtest result has ${json_bytes} bytes of JSON; the limit is ${maxBytes} (BACKTEST_MAX_RESULT_BYTES). Choose fewer stocks, a shorter period or fewer conditions.`,
      undefined, { limit: 'max_result_bytes', allowed: maxBytes, needed: json_bytes });
  const packed = zlib.gzipSync(text), gzip = new Uint8Array(packed.byteLength);
  gzip.set(packed);
  return { gzip, json_bytes };
}

export const threadConfig = (c: Config): ThreadConfig => {
  const { fetch: _f, log: _l, ...terminal } = c.terminal;
  return { limits: c.limits, maxResultBytes: c.maxResultBytes, flow: c.flow, terminal };
};

/* ---- main thread ------------------------------------------------------------------------------------------------ */
interface Pending { resolve(o: Outcome): void; reject(e: Error): void; progress?(p: JobProgress): void }

export class ComputeThread {
  name: string;
  private data: Omit<ThreadData, 'role' | 'name' | 'flag'>;
  private flag = new Int32Array(new SharedArrayBuffer(4));
  private worker: Worker | null = null;
  private seq = 0;
  private pending = new Map<number, Pending>();

  constructor(name: string, config: ThreadConfig, versions: ThreadData['versions']) { this.name = name; this.data = { config, versions } }

  private spawn(): Worker {
    const w = new Worker(new URL(import.meta.url), { workerData: { role: 'compute', name: this.name, flag: this.flag, ...this.data } satisfies ThreadData });
    w.on('message', (m: FromThread) => {
      if (m.type === 'log') { writeLine(m.line); return }
      const p = this.pending.get(m.seq);
      if (!p) return;
      if (m.type === 'progress') { p.progress?.(m.progress); return }
      this.pending.delete(m.seq);
      if (m.type === 'done') p.resolve(m.outcome); else p.reject(new TaskFailed(m.error));
    });
    w.on('error', e => { log('error', 'compute_thread_error', { thread: this.name, ...errorFields(e, true) }); this.lost(w, new ThreadStopped('crashed', (e as { code?: string }).code ?? null)) });
    w.on('exit', code => this.lost(w, new ThreadStopped('crashed', `exit ${code}`)));
    w.unref();
    return w;
  }
  /** Every task of a thread that is gone fails with the reason; the next task starts a new thread. */
  private lost(w: Worker, e: ThreadStopped): void {
    if (this.worker !== w) return;
    this.worker = null;
    for (const p of this.pending.values()) p.reject(e);
    this.pending.clear();
  }

  run(task: Task, progress?: (p: JobProgress) => void): { seq: number; done: Promise<Outcome> } {
    const seq = ++this.seq, w = this.worker ??= this.spawn();
    const done = new Promise<Outcome>((resolve, reject) => this.pending.set(seq, { resolve, reject, progress }));
    w.postMessage({ seq, task });
    return { seq, done };
  }
  /** Asks task `seq` to stop at its next check (run.ts hooks.shouldStop). */
  cancel(seq: number): void { Atomics.store(this.flag, 0, seq) }
  /** Terminates the thread now; its tasks fail with ThreadStopped('killed'). */
  async kill(): Promise<void> {
    const w = this.worker;
    if (!w) return;
    this.lost(w, new ThreadStopped('killed'));
    await w.terminate();
  }
  get busy(): boolean { return this.pending.size > 0 }
}

/* ---- the thread ------------------------------------------------------------------------------------------------- */
function startThread(d: ThreadData): void {
  const port = parentPort!;
  setLogSink(line => port.postMessage({ seq: -1, type: 'log', line }));
  const client = new PlannedClient({ ...d.config.terminal, log: (event, fields) => log('info', event, { thread: d.name, ...fields }) });
  const env = { client, config: d.config, versions: d.versions };
  let chain: Promise<void> = Promise.resolve();
  port.on('message', (m: { seq: number; task: Task }) => { chain = chain.then(() => handle(m.seq, m.task)) });

  async function handle(seq: number, task: Task): Promise<void> {
    const hooks = { shouldStop: () => Atomics.load(d.flag, 0) === seq, progress: (p: JobProgress) => port.postMessage({ seq, type: 'progress', progress: p }) };
    try {
      if (task.kind === 'job') {
        const result = await runJob(task.request, task.context, task.refs, env, hooks);
        const { gzip, json_bytes } = packResult(result, d.config.maxResultBytes);
        if (hooks.shouldStop()) throw new Cancelled();             // a cancel that came while the result was packed
        port.postMessage({ seq, type: 'done', outcome: { kind: 'job', gzip, json_bytes, duration_ms: result.meta.duration_ms } }, [gzip.buffer]);
      } else {
        port.postMessage({ seq, type: 'done', outcome: { kind: 'signals', preview: await runSignals(task.request, task.refs, env, hooks) } });
      }
    } catch (e) {
      const s = serialError(e);
      if (!s.known) log('error', 'compute_failed', { thread: d.name, task: task.kind, ...errorFields(e, true) });
      port.postMessage({ seq, type: 'failed', error: s });
    }
  }
}

if (!isMainThread && (workerData as ThreadData | null)?.role === 'compute') startThread(workerData as ThreadData);
