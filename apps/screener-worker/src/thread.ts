/* A compute or builder thread (worker_threads; report TARGET ARCHITECTURE 6.4 "Threads"): every screen, preview, counts
   entry and pre-warm chunk runs off the HTTP thread, so /health, /ready, the catalog and cache hits stay answered
   while a screen computes. The builder is a thread of the same module started for one refresh: it downloads (or reads
   from the disk cache by sha256), verifies (inflateVerified: sha256 and size) and decodes the files, builds the next
   snapshot and pre-warms it while the compute threads keep serving the current one (6.4); at a cold start the compute
   threads pre-warm with it (6d.4: "split over the K threads").

   Messages (main -> thread): install {sid, desc, lruBytes} (a snapshot this thread serves; its pinned tails become
   views into the shared buffers); drop {sid}; task {seq, task} -> done {seq, outcome} | failed {seq, error}. A task's
   cancel flag is a shared Int32Array the main thread sets to the task's seq (the caller left, or its deadline passed);
   plan.ts checks it between tickers. A thread that does not stop is terminated (pool.ts) and a new one is started. */
import { isMainThread, parentPort, workerData } from 'node:worker_threads';
import type { PresetDefinition } from '../../edge-bff/screener/src/core/catalog.ts';
import { TerminalClient } from '../../backtest-worker/src/terminal.ts';
import type { TerminalOptions, TickerReference } from '../../backtest-worker/src/terminal.ts';
import type { FileEntry } from '../../edge-bff/backtest/src/core/datafile.ts';
import { serialError } from './errors.ts';
import { errorFields, log, setLogSink } from './log.ts';
import { runPreview } from './preview.ts';
import type { PreviewTask } from './preview.ts';
import { CancelledRun, isCancelled, runTask } from './run.ts';
import type { CountsEntryOut, CountsTask, RunTask, ThreadEnv } from './run.ts';
import { ThreadSnapshot, buildSnapshot, prewarmChunk, snapshotDigest } from './snapshot.ts';
import type { PublicationState, SnapshotDesc } from './snapshot.ts';

export interface BuildTask {
  kind: 'build';
  files: { price: FileEntry; actions: FileEntry };
  ref: TickerReference; state: PublicationState;
  engine: { screener_engine: string; registry: string; screener_registry: string };
  tailLength: number; presets: PresetDefinition[];
}
export interface PrewarmTask { kind: 'prewarm'; desc: SnapshotDesc; from: number; to: number }
export interface DigestTask { kind: 'digest'; desc: SnapshotDesc }
export type Task = RunTask | CountsTask | PreviewTask | BuildTask | PrewarmTask | DigestTask;

/** engine: an optional module URL whose runTask / runPreview replace run.ts's and preview.ts's (the worker's tests
    of lanes, budgets and versions run on it; production never sets it). */
export interface ThreadData { role: 'compute' | 'builder'; name: string; env: ThreadEnv; terminal: Omit<TerminalOptions, 'fetch' | 'log'> | null; flag: Int32Array; engine?: string }
export type ToThread =
  | { type: 'install'; sid: string; desc: SnapshotDesc; lruBytes: number }
  | { type: 'drop'; sid: string }
  | { type: 'task'; seq: number; task: Task };
export type FromThread =
  | { type: 'installed'; sid: string; ms: number }
  | { type: 'install_failed'; sid: string; error: ReturnType<typeof serialError> }
  | { type: 'done'; seq: number; outcome: unknown }
  | { type: 'failed'; seq: number; error: ReturnType<typeof serialError> }
  | { type: 'log'; line: string };

function start(d: ThreadData): void {
  const port = parentPort!;
  setLogSink(line => port.postMessage({ type: 'log', line } satisfies FromThread));
  const snapshots = new Map<string, ThreadSnapshot>();
  const client = d.terminal ? new TerminalClient({ ...d.terminal, log: (event, fields) => log('info', event, { thread: d.name, ...fields }) }) : null;
  let engine = { runTask, runPreview };
  let chain: Promise<void> = d.engine
    ? import(d.engine).then((m: Partial<typeof engine>) => { engine = { runTask: m.runTask ?? runTask, runPreview: m.runPreview ?? runPreview } })
    : Promise.resolve();
  port.on('message', (m: ToThread) => { chain = chain.then(() => handle(m)) });

  async function handle(m: ToThread): Promise<void> {
    if (m.type === 'install') {
      try {
        const t0 = performance.now();
        snapshots.set(m.sid, new ThreadSnapshot(m.desc, m.lruBytes));
        port.postMessage({ type: 'installed', sid: m.sid, ms: Math.round(performance.now() - t0) } satisfies FromThread);
      } catch (e) {
        log('error', 'install_failed', { thread: d.name, ...errorFields(e, true) });
        port.postMessage({ type: 'install_failed', sid: m.sid, error: serialError(e) } satisfies FromThread);
      }
      return;
    }
    if (m.type === 'drop') { snapshots.delete(m.sid); return }
    const { seq, task } = m;
    const cancelled = () => Atomics.load(d.flag, 0) === seq;
    try {
      const outcome = await perform(task, cancelled);
      const transfer = outcome && typeof outcome === 'object' && (outcome as { gzip?: unknown }).gzip instanceof Uint8Array ? [((outcome as { gzip: Uint8Array }).gzip).buffer as ArrayBuffer] : [];
      port.postMessage({ type: 'done', seq, outcome } satisfies FromThread, transfer);
    } catch (e) {
      const stopped = cancelled() || e instanceof CancelledRun || isCancelled(e);
      const s = serialError(e, stopped);
      if (!s.known && !stopped) log('error', 'task_failed', { thread: d.name, task: task.kind, ...errorFields(e, true) });
      port.postMessage({ type: 'failed', seq, error: s } satisfies FromThread);
    }
  }

  async function perform(task: Task, cancelled: () => boolean): Promise<unknown> {
    switch (task.kind) {
      case 'build': {
        if (!client) throw new Error('build: this thread has no terminal client');
        const t0 = performance.now();
        const what = (n: string) => `The ${n} cross-sectional file`;
        const [price, actions] = await Promise.all([client.file(task.files.price, what('price'), 'price'), client.file(task.files.actions, what('actions'), 'actions')]);
        const t1 = performance.now();
        const built = await buildSnapshot({ price: price.doc, actions: actions.doc, ref: task.ref, state: task.state, engine: task.engine,
          tailLength: task.tailLength, capBudgetMs: d.env.capBudgetMs, withinMax: d.env.withinMax, presets: task.presets });
        return { ...built, cached: { price: price.cached, actions: actions.cached }, download_ms: Math.round(t1 - t0), decode_ms: Math.round(performance.now() - t1), downloads: client.stats.downloads, download_bytes: client.stats.download_bytes };
      }
      case 'prewarm': return prewarmChunk(task.desc, task.from, task.to, d.env.capBudgetMs);
      case 'digest': return { digest: snapshotDigest(task.desc) };
      case 'run': case 'counts': return engine.runTask(task, snapshot(task.sid), d.env, cancelled);
      case 'preview': return engine.runPreview(task, snapshot(task.sid), d.env);
      case 'counts_list': {
        // each definition on its own; a failure is that entry's error, the others are still counted (8.6)
        const snap = snapshot(task.sid), out: CountsEntryOut[] = [];
        for (const item of task.items) {
          if (cancelled()) throw new CancelledRun();
          try {
            const o = engine.runTask({ ...item, kind: 'counts', sid: task.sid, options: { exhaustive: false, explain: false }, queue_ms: 0, s0_ms: 0, versions: snap.desc.versions, data: snap.desc.data }, snap, d.env, cancelled);
            out.push({ item_id: item.item_id, match_count: o.match_count, near_count: o.near_count, busy_ms: o.busy_ms });
          } catch (e) {
            if (cancelled() || isCancelled(e)) throw e;
            const s = serialError(e);
            if (!s.known) log('error', 'counts_entry_failed', { thread: d.name, item_id: item.item_id, ...errorFields(e, true) });
            out.push({ item_id: item.item_id, error: s.error });
          }
        }
        return { kind: 'counts_list', counts: out };
      }
    }
  }
  function snapshot(sid: string): ThreadSnapshot {
    const s = snapshots.get(sid);
    if (!s) throw new Error(`thread ${d.name}: snapshot ${sid} is not installed`);
    return s;
  }
}

if (!isMainThread && (workerData as ThreadData | null)?.role) start(workerData as ThreadData);
