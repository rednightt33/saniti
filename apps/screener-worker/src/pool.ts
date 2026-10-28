/* The compute threads and who runs next (report MULTI-USER SCALE AND COST 6d.6; TARGET ARCHITECTURE 6.4, 6.10, 6.16;
   API CONTRACT 8.9; P33, user 2026-10-28: per-owner compute limits built in Phase 1).

   Admission, in this order (server.ts calls them before a request reaches a lane):
   1. cache hits (result cache, counts, catalog, universe) are answered at once, outside every queue and budget;
   2. the per-request budget: a request whose worst case (run.ts estimateCost) is above SCREENER_MAX_CPU_MS is refused
      with 422 LIMIT_EXCEEDED {limit: 'compute_budget', allowed, needed, costliest}, never cut short;
   3. the per-owner budget (P33): thread milliseconds an owner tag may use per minute on this replica
      (SCREENER_OWNER_CPU_MS), counting what it used in the last 60 s plus the predicted cost of what it has waiting or
      running; a request that would pass it is refused with 422 LIMIT_EXCEEDED {limit: 'owner_cpu_budget', allowed,
      needed, retry_after_seconds} (the wait until enough of the minute has passed);
   4. the queue: at most SCREENER_QUEUE requests wait on this replica, every owner together; beyond it 409 BUSY.
   Lanes: each owner tag (x-screener-owner, an opaque HMAC edge-bff computes) has its own lane; at most
   SCREENER_OWNER_INFLIGHT of its requests run at once, the rest wait in its lane, where a newer request of the same page
   (client_order.page) replaces a waiting older one, which answers 409 SCREEN_REPLACED / PREVIEW_REPLACED. A free
   thread takes the next request by deficit round robin across the lanes, weighted by the predicted cost: each visit
   gives a lane a quantum of SCREENER_MAX_CPU_MS / 4 ms, and a request starts when its lane has saved its predicted cost
   (at least 1 ms), so a lane of costly screens takes turns with lanes of cheap ones and a heavy user slows only
   themself. The publication's own work (the presets' pre-warm) runs in a system lane, outside the queue and budgets.
   Deadline: SCREENER_DEADLINE_MS from arrival (queue included): a waiting request is dropped and a running one is asked
   to stop (the shared cancel flag), both answering 504 TIMEOUT; a thread that does not stop within KILL_GRACE_MS is
   terminated and started again (its snapshots installed again before it takes work). A caller that leaves is treated
   the same way, without an answer. */
import { Worker } from 'node:worker_threads';
import type { SnapshotDesc } from './snapshot.ts';
import { fromSerial, refuse } from './errors.ts';
import type { SerialError } from './errors.ts';
import { errorFields, log, writeLine } from './log.ts';
import type { FromThread, Task, ThreadData, ToThread } from './thread.ts';

export const KILL_GRACE_MS = 1000;      // a running task asked to stop has this long before its thread is terminated
export const OWNER_WINDOW_MS = 60_000;  // P33: SCREENER_OWNER_CPU_MS is per minute
export const SYSTEM = '~system';        // the publication's own lane (never an owner tag: tags are 16 hex)

/** The thread is gone: terminated by the pool, or it crashed (out of memory, an exception outside a task). */
export class ThreadStopped extends Error {
  reason: 'killed' | 'crashed'; code: string | null;
  constructor(reason: 'killed' | 'crashed', code: string | null = null) { super(`compute thread ${reason}${code ? ` (${code})` : ''}`); this.name = 'ThreadStopped'; this.reason = reason; this.code = code }
}

/* ---- one thread ------------------------------------------------------------------------------------------------- */
interface Pending { resolve(o: unknown): void; reject(e: unknown): void }
export class ComputeThread {
  name: string;
  private script: URL; private data: Omit<ThreadData, 'flag' | 'name'>;
  private flag = new Int32Array(new SharedArrayBuffer(4));
  private worker: Worker | null = null;
  private seq = 0;
  private pending = new Map<number, Pending>();
  private installs: Map<string, { desc: SnapshotDesc; lruBytes: number }>;   // the pool's: what every thread must hold
  private installing: Promise<void> | null = null;
  private acks = new Map<string, { resolve(): void; reject(e: unknown): void }>();
  busy = false;

  constructor(name: string, script: URL, data: Omit<ThreadData, 'flag' | 'name'>, installs: Map<string, { desc: SnapshotDesc; lruBytes: number }>) {
    this.name = name; this.script = script; this.data = data; this.installs = installs;
  }
  private spawn(): Worker {
    const w = new Worker(this.script, { workerData: { ...this.data, name: this.name, flag: this.flag } satisfies ThreadData });
    w.on('message', (m: FromThread) => {
      if (m.type === 'log') { writeLine(m.line); return }
      if (m.type === 'installed' || m.type === 'install_failed') {
        const a = this.acks.get(m.sid);
        this.acks.delete(m.sid);
        if (a) { if (m.type === 'installed') a.resolve(); else a.reject(fromSerial(m.error)) }
        return;
      }
      const p = this.pending.get(m.seq);
      if (!p) return;
      this.pending.delete(m.seq);
      if (m.type === 'done') p.resolve(m.outcome); else p.reject(new TaskFailed(m.error));
    });
    w.on('error', e => { log('error', 'thread_error', { thread: this.name, ...errorFields(e, true) }); this.lost(w, new ThreadStopped('crashed', (e as { code?: string }).code ?? null)) });
    w.on('exit', code => this.lost(w, new ThreadStopped('crashed', `exit ${code}`)));
    w.unref();
    return w;
  }
  private lost(w: Worker, e: ThreadStopped): void {
    if (this.worker !== w) return;
    this.worker = null; this.installing = null;
    for (const p of this.pending.values()) p.reject(e);
    this.pending.clear();
    for (const a of this.acks.values()) a.reject(e);
    this.acks.clear();
  }
  private post(m: ToThread, transfer: ArrayBuffer[] = []): void { (this.worker as Worker).postMessage(m, transfer) }
  /** The thread running, with every snapshot of the pool installed (a new or restarted thread installs them first). */
  async ready(): Promise<void> {
    if (this.worker && !this.installing) return;
    if (!this.worker) {
      this.worker = this.spawn();
      const sids = [...this.installs.keys()];
      this.installing = Promise.all(sids.map(sid => this.installOne(sid))).then(() => { this.installing = null }, e => { this.installing = null; throw e });
    }
    await this.installing;
  }
  private installOne(sid: string): Promise<void> {
    const it = this.installs.get(sid);
    if (!it) return Promise.resolve();
    return new Promise<void>((resolve, reject) => { this.acks.set(sid, { resolve, reject }); this.post({ type: 'install', sid, desc: it.desc, lruBytes: it.lruBytes }) });
  }
  /** Installs one snapshot the pool registered (the thread must be running). */
  async install(sid: string): Promise<void> { await this.ready(); await this.installOne(sid) }
  drop(sid: string): void { if (this.worker) this.post({ type: 'drop', sid }) }
  /** One task; done rejects with TaskFailed (the thread's error) or ThreadStopped. */
  async run(task: Task): Promise<{ seq: number; done: Promise<unknown> }> {
    await this.ready();
    const seq = ++this.seq;
    const done = new Promise<unknown>((resolve, reject) => this.pending.set(seq, { resolve, reject }));
    this.post({ type: 'task', seq, task });
    return { seq, done };
  }
  cancel(seq: number): void { Atomics.store(this.flag, 0, seq) }
  async kill(): Promise<void> {
    const w = this.worker;
    if (!w) return;
    this.lost(w, new ThreadStopped('killed'));
    await w.terminate();
  }
  get alive(): boolean { return this.worker !== null }
}

/** A task the thread failed, as it reported it (its class does not cross the thread boundary). */
export class TaskFailed extends Error {
  serial: SerialError;
  constructor(s: SerialError) { super(s.error.code); this.name = 'TaskFailed'; this.serial = s }
}

/* ---- the per-owner budget (P33) ---------------------------------------------------------------------------------- */
export class OwnerBudget {
  private used = new Map<string, { at: number; ms: number }[]>();
  private limit: number; private now: () => number;
  constructor(limitMs: number, now: () => number = Date.now) { this.limit = limitMs; this.now = now }
  private window(owner: string): { at: number; ms: number }[] {
    const t = this.now() - OWNER_WINDOW_MS, list = (this.used.get(owner) ?? []).filter(x => x.at > t);
    if (list.length) this.used.set(owner, list); else this.used.delete(owner);
    return list;
  }
  spent(owner: string): number { return this.window(owner).reduce((s, x) => s + x.ms, 0) }
  record(owner: string, ms: number): void {
    if (owner === SYSTEM || !(ms > 0)) return;
    const list = this.window(owner);
    list.push({ at: this.now(), ms });
    this.used.set(owner, list);
  }
  /** Refuses (LIMIT_EXCEEDED owner_cpu_budget) when spent + reserved + predicted would pass the limit. */
  check(owner: string, reserved: number, predicted: number): void {
    if (owner === SYSTEM) return;
    const list = this.window(owner), spent = list.reduce((s, x) => s + x.ms, 0), needed = Math.ceil(spent + reserved + predicted);
    if (needed <= this.limit) return;
    // the wait until enough of the window has passed for this request (never less than one second)
    let free = spent + reserved + predicted - this.limit, wait = OWNER_WINDOW_MS;
    for (const x of [...list].sort((a, b) => a.at - b.at)) { free -= x.ms; if (free <= 0) { wait = x.at + OWNER_WINDOW_MS - this.now(); break } }
    const retry = Math.max(1, Math.ceil(wait / 1000));
    throw refuse('LIMIT_EXCEEDED', `This user's screens used ${Math.round(spent)} ms of compute in the last minute and have ${Math.round(reserved)} ms waiting; with this one (about ${Math.round(predicted)} ms) that is above the ${this.limit} ms a user may use per minute. Wait ${retry} s, or use fewer custom conditions.`,
      undefined, { limit: 'owner_cpu_budget', allowed: this.limit, needed, retry_after_seconds: retry });
  }
}

/* ---- jobs and lanes --------------------------------------------------------------------------------------------- */
export interface JobSpec {
  owner: string;
  kind: 'run' | 'preview' | 'counts' | 'system';
  page: string | null; order: number | null;   // client_order: a newer one of the same page replaces a waiting one
  cost: number;                                  // predicted ms (run.ts estimateCost)
  deadlineAt: number;                            // performance.now() ms
  task: Task;
}
interface Job extends JobSpec {
  state: 'waiting' | 'running' | 'ended';
  enqueuedAt: number; startedAt: number | null;
  thread: ComputeThread | null; seq: number | null;
  timer: NodeJS.Timeout | null; killTimer: NodeJS.Timeout | null; stopping: boolean;
  resolve(o: { outcome: unknown; queue_ms: number }): void; reject(e: unknown): void;
}
export interface PoolOptions { threads: number; queue: number; ownerInflight: number; quantumMs: number; script: URL; data: Omit<ThreadData, 'flag' | 'name' | 'role'>; budget: OwnerBudget }
const REPLACED = { run: 'SCREEN_REPLACED', counts: 'SCREEN_REPLACED', preview: 'PREVIEW_REPLACED', system: 'SCREEN_REPLACED' } as const;

export class Pool {
  threads: ComputeThread[];
  installs = new Map<string, { desc: SnapshotDesc; lruBytes: number }>();
  private o: PoolOptions;
  private lanes = new Map<string, Job[]>();
  private ring: string[] = [];
  private ptr = 0;
  private deficit = new Map<string, number>();
  private running = new Map<string, number>();
  private reservedMs = new Map<string, number>();
  private waiting = 0;
  stats = { started: 0, replaced: 0, busy: 0, timeouts: 0, killed: 0 };

  constructor(o: PoolOptions) {
    this.o = o;
    this.threads = Array.from({ length: o.threads }, (_, k) => new ComputeThread(`compute-${k + 1}`, o.script, { ...o.data, role: 'compute' }, this.installs));
  }
  /** A thread for one refresh (the builder), outside the pool's scheduling; the caller kills it when done. */
  builder(name: string, data: Omit<ThreadData, 'flag' | 'name'>): ComputeThread { return new ComputeThread(name, this.o.script, data, new Map()) }

  /** Registers a snapshot and installs it on every thread; all-or-nothing (a failure removes it everywhere). */
  async install(sid: string, desc: SnapshotDesc, lruBytes: number): Promise<number> {
    const t0 = performance.now();
    this.installs.set(sid, { desc, lruBytes });
    try { await Promise.all(this.threads.map(t => t.install(sid))) }
    catch (e) { this.drop(sid); throw e }
    return Math.round(performance.now() - t0);
  }
  drop(sid: string): void { this.installs.delete(sid); for (const t of this.threads) t.drop(sid) }

  /** Reserved (waiting or running) predicted ms of an owner's requests: counted by the owner budget. */
  reserved(owner: string): number { return this.reservedMs.get(owner) ?? 0 }
  get queued(): number { return this.waiting }

  /** Runs a job in its owner's lane; resolves with the thread's outcome and the time it waited. */
  submit(spec: JobSpec): { promise: Promise<{ outcome: unknown; queue_ms: number }>; cancel(): void } {
    const now = performance.now();
    let job!: Job;
    const promise = new Promise<{ outcome: unknown; queue_ms: number }>((resolve, reject) => {
      job = { ...spec, state: 'waiting', enqueuedAt: now, startedAt: null, thread: null, seq: null, timer: null, killTimer: null, stopping: false, resolve, reject };
    });
    const lane = this.lanes.get(spec.owner) ?? [];
    // a newer request of the same page replaces its waiting older ones (6d.6)
    if (spec.page !== null && spec.order !== null) {
      for (const w of lane.filter(x => x.kind === spec.kind && x.page === spec.page && x.order !== null && (x.order as number) < (spec.order as number))) {
        this.remove(w);
        this.stats.replaced++;
        w.reject(refuse(REPLACED[w.kind], 'A newer request of the same page replaced this one.'));
      }
    }
    const startsNow = !!this.idleThread() && (this.running.get(spec.owner) ?? 0) < this.o.ownerInflight && !lane.length;
    if (spec.owner !== SYSTEM && this.waiting >= this.o.queue && !startsNow) {
      this.stats.busy++;
      job.reject(refuse('BUSY', `The screener is busy: ${this.waiting} screens are waiting on this replica, the most it holds (SCREENER_QUEUE ${this.o.queue}). Retry in a few seconds.`, undefined, { limit: 'queue', allowed: this.o.queue }));
      return { promise, cancel: () => {} };
    }
    if (!this.lanes.has(spec.owner)) { this.lanes.set(spec.owner, lane); this.ring.push(spec.owner) }
    lane.push(job);
    this.waiting++;
    this.reservedMs.set(spec.owner, this.reserved(spec.owner) + spec.cost);
    const left = spec.deadlineAt - now;
    job.timer = setTimeout(() => this.expire(job), Math.max(0, left));
    job.timer.unref?.();
    this.schedule();
    return { promise, cancel: () => this.stop(job, null) };
  }

  private idleThread(): ComputeThread | null { return this.threads.find(t => !t.busy) ?? null }
  private remove(job: Job): void {
    const lane = this.lanes.get(job.owner);
    const k = lane ? lane.indexOf(job) : -1;
    if (k >= 0) { lane!.splice(k, 1); this.waiting-- }
    if (job.timer) clearTimeout(job.timer);
    job.state = 'ended';
    this.unreserve(job);
    this.forget(job.owner);
  }
  /** An owner with nothing waiting or running leaves the ring (owner tags are many over time). */
  private forget(owner: string): void {
    if ((this.lanes.get(owner)?.length ?? 0) > 0 || (this.running.get(owner) ?? 0) > 0) return;
    const k = this.ring.indexOf(owner);
    if (k >= 0) { this.ring.splice(k, 1); if (this.ptr > k) this.ptr-- }
    this.lanes.delete(owner); this.deficit.delete(owner); this.running.delete(owner);
  }
  private unreserve(job: Job): void {
    const left = this.reserved(job.owner) - job.cost;
    if (left > 0.0001) this.reservedMs.set(job.owner, left); else this.reservedMs.delete(job.owner);
  }
  private expire(job: Job): void {
    if (job.state === 'ended') return;
    this.stats.timeouts++;
    const ms = Math.round(performance.now() - job.enqueuedAt);
    this.stop(job, refuse('TIMEOUT', `The request took longer than the ${Math.round(job.deadlineAt - job.enqueuedAt)} ms limit (SCREENER_DEADLINE_MS) after ${ms} ms: use fewer custom conditions or shorter lengths.`));
  }
  /** Stops a job: removed while waiting; asked to stop while running (terminated after KILL_GRACE_MS). error null =
      the caller left (nothing is answered). */
  private stop(job: Job, error: unknown): void {
    if (job.state === 'ended') return;
    if (job.state === 'waiting') { this.remove(job); this.schedule() }
    else { job.stopping = true; this.halt(job) }
    if (error) job.reject(error); else job.reject(Object.assign(new Error('caller left'), { name: 'CallerLeft' }));
    job.resolve = () => {}; job.reject = () => {};
  }

  /** A running job asked to stop: its cancel flag now, its thread terminated after KILL_GRACE_MS if it is still on it. */
  private halt(job: Job): void {
    const t = job.thread, seq = job.seq;
    if (!t || seq === null || job.killTimer) return;          // not started on its thread yet: start() halts it
    t.cancel(seq);
    job.killTimer = setTimeout(() => {
      if (job.state !== 'running' || job.thread !== t) return;
      this.stats.killed++;
      log('warn', 'thread_killed', { thread: t.name, kind: job.kind, after_ms: KILL_GRACE_MS });
      t.kill().catch(e => log('error', 'thread_kill_failed', errorFields(e)));
    }, KILL_GRACE_MS);
    job.killTimer.unref?.();
  }

  /** Starts waiting jobs on idle threads: deficit round robin across lanes (header). */
  private schedule(): void {
    for (;;) {
      const thread = this.idleThread();
      if (!thread) return;
      const job = this.pick();
      if (!job) return;
      this.start(job, thread);
    }
  }
  private pick(): Job | null {
    const quantum = Math.max(1, this.o.quantumMs);
    const eligible = () => this.ring.filter(o => (this.lanes.get(o)?.length ?? 0) > 0 && (this.running.get(o) ?? 0) < (o === SYSTEM ? this.threads.length : this.o.ownerInflight));
    if (!eligible().length) return null;
    // at most enough rounds for the most expensive head to save its cost
    for (let guard = 0; guard < 1e6; guard++) {
      if (!this.ring.length) return null;
      this.ptr %= this.ring.length;
      const owner = this.ring[this.ptr], lane = this.lanes.get(owner) ?? [];
      const can = lane.length > 0 && (this.running.get(owner) ?? 0) < (owner === SYSTEM ? this.threads.length : this.o.ownerInflight);
      if (!can) { if (!lane.length) this.deficit.set(owner, 0); this.ptr++; continue }
      const head = lane[0], cost = Math.max(1, head.cost);
      const d = (this.deficit.get(owner) ?? 0);
      if (d >= cost) {
        this.deficit.set(owner, d - cost);
        lane.shift(); this.waiting--;
        if (!lane.length) this.deficit.set(owner, 0);
        this.ptr++;
        return head;
      }
      this.deficit.set(owner, d + quantum);
      this.ptr++;
    }
    return null;
  }
  private start(job: Job, thread: ComputeThread): void {
    job.state = 'running'; job.startedAt = performance.now(); job.thread = thread; thread.busy = true;
    this.running.set(job.owner, (this.running.get(job.owner) ?? 0) + 1);
    this.stats.started++;
    const queue_ms = job.startedAt - job.enqueuedAt;
    const finish = () => {
      if (job.timer) clearTimeout(job.timer);
      if (job.killTimer) clearTimeout(job.killTimer);
      thread.busy = false;
      this.running.set(job.owner, (this.running.get(job.owner) ?? 1) - 1);
      if (job.state !== 'ended') this.unreserve(job);
      job.state = 'ended';
      this.forget(job.owner);
      setImmediate(() => this.schedule());
    };
    (async () => {
      try {
        const { seq, done } = await thread.run({ ...job.task, ...(job.task.kind === 'run' || job.task.kind === 'counts' ? { queue_ms } : {}) } as Task);
        job.seq = seq;
        if (job.stopping) this.halt(job);
        const outcome = await done;
        finish();
        job.resolve({ outcome, queue_ms });
      } catch (e) {
        finish();
        job.reject(e instanceof TaskFailed ? fromSerial(e.serial) : e);
      }
    })();
  }
  /** Lane sizes for /health and tests. */
  lanesView(): Record<string, { waiting: number; running: number }> {
    const out: Record<string, { waiting: number; running: number }> = {};
    for (const o of this.ring) out[o] = { waiting: this.lanes.get(o)?.length ?? 0, running: this.running.get(o) ?? 0 };
    return out;
  }
  async close(): Promise<void> { await Promise.all(this.threads.map(t => t.kill())) }
}
