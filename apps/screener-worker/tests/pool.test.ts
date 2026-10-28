/* Lanes, budgets, queue and deadlines (pool.ts; report 6d.6, 8.9; P33; TEST PLAN 10b.11 "Owner lanes"), on a fake
   thread (tests/fake-thread.mjs) so the scheduling is tested apart from the screen it runs. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import { OwnerBudget, Pool, SYSTEM } from '../src/pool.ts';
import type { JobSpec } from '../src/pool.ts';
import { captureLogs, sleep, until } from './helpers.ts';

const logs = captureLogs();
const script = new URL('./fake-thread.mjs', import.meta.url);
const pools: Pool[] = [];
after(async () => { await Promise.all(pools.map(p => p.close())) });

function pool(o: { threads?: number; queue?: number; inflight?: number; quantum?: number; ownerMs?: number; now?: () => number } = {}) {
  const p = new Pool({ threads: o.threads ?? 2, queue: o.queue ?? 10, ownerInflight: o.inflight ?? 2, quantumMs: o.quantum ?? 100,
    script, data: { env: { capBudgetMs: 1, withinMax: 1, maxResponseBytes: 1 }, terminal: null }, budget: new OwnerBudget(o.ownerMs ?? 1e9, o.now) });
  pools.push(p);
  return p;
}
const job = (owner: string, tag: string, ms: number, extra: Partial<JobSpec> = {}): JobSpec =>
  ({ owner, kind: 'run', page: null, order: null, cost: ms, deadlineAt: performance.now() + 60_000, task: { kind: 'sleep', ms, tag } as never, ...extra });
const order = () => logs.events('fake_start').map(l => l.tag);
const reset = () => { logs.lines.length = 0 };

test('an owner never runs more than SCREENER_OWNER_INFLIGHT at once; the rest wait in its lane', async () => {
  reset();
  const p = pool({ threads: 3, inflight: 2 });
  const runs = ['a1', 'a2', 'a3', 'a4'].map(t => p.submit(job('A', t, 150)));
  await sleep(60);
  assert.deepEqual(p.lanesView().A, { waiting: 2, running: 2 }, 'two run, two wait though a thread is free');
  await Promise.all(runs.map(r => r.promise));
  // a1 and a2 start on two threads at once, so their start lines may arrive in either order; a3 and a4 likewise
  const o = order();
  assert.deepEqual([o.slice(0, 2).sort(), o.slice(2).sort()], [['a1', 'a2'], ['a3', 'a4']], `the lane keeps its order: ${o}`);
});

test('round robin: a light owner starts within one turn while a heavy owner loops costly requests', async () => {
  reset();
  const p = pool({ threads: 1, inflight: 1, quantum: 100 });
  const heavy = ['h1', 'h2', 'h3', 'h4'].map(t => p.submit(job('H', t, 60, { cost: 100 })));
  await sleep(10);                                    // h1 runs; h2..h4 wait
  const light = p.submit(job('L', 'l1', 10, { cost: 10 }));
  await Promise.all([...heavy, light].map(r => r.promise));
  const o = order();
  assert.equal(o.indexOf('l1'), 1, `the light request runs right after the heavy one already running: ${o}`);
});

test('deficit round robin weights by cost: cheap requests of one owner take turns with a costly one', async () => {
  reset();
  const p = pool({ threads: 1, inflight: 1, quantum: 50 });
  const block = p.submit(job('X', 'x0', 40, { cost: 1 }));     // occupies the thread while the lanes fill
  await sleep(5);
  const costly = p.submit(job('C', 'c1', 5, { cost: 200 }));
  const cheap = ['k1', 'k2', 'k3', 'k4'].map(t => p.submit(job('K', t, 5, { cost: 50 })));
  await Promise.all([block, costly, ...cheap].map(r => r.promise));
  const o = order(), at = o.indexOf('c1');
  assert.ok(at > o.indexOf('k1'), `the costly request (4 quanta) does not jump the cheap ones: ${o}`);
  assert.ok(at < o.indexOf('k4') || o.indexOf('k4') === -1 || at <= 4, `it is not starved either: ${o}`);
});

test('the queue is bounded: beyond SCREENER_QUEUE waiting requests the answer is 409 BUSY', async () => {
  const p = pool({ threads: 1, queue: 2, inflight: 4 });
  const running = p.submit(job('A', 'r', 100));
  await sleep(10);
  const w1 = p.submit(job('B', 'w1', 10)), w2 = p.submit(job('C', 'w2', 10));
  const refused = p.submit(job('D', 'w3', 10));
  await assert.rejects(refused.promise, (e: unknown) => e instanceof ScreenerError && e.code === 'BUSY' && e.status === 409 && (e.details as any).limit === 'queue');
  await Promise.all([running, w1, w2].map(r => r.promise));
  // the system lane (the presets' pre-warm) is never refused
  const s = p.submit(job(SYSTEM, 's', 1));
  await s.promise;
});

test('a newer request of the same page replaces its waiting older one (409 SCREEN_REPLACED); another page is kept', async () => {
  const p = pool({ threads: 1, inflight: 1 });
  const busy = p.submit(job('A', 'b', 80));
  await sleep(10);
  const old = p.submit(job('A', 'p1-1', 5, { page: 'p1', order: 1 }));
  const other = p.submit(job('A', 'p2-1', 5, { page: 'p2', order: 1 }));
  const newer = p.submit(job('A', 'p1-2', 5, { page: 'p1', order: 2 }));
  await assert.rejects(old.promise, (e: unknown) => e instanceof ScreenerError && e.code === 'SCREEN_REPLACED');
  await Promise.all([busy, other, newer].map(r => r.promise));
  const preview = p.submit(job('A', 'v1', 50, { kind: 'preview', page: 'p1', order: 1 }));
  const preview2 = p.submit(job('A', 'v2', 5, { kind: 'preview', page: 'p1', order: 2 }));
  await Promise.all([preview.promise.catch(e => e), preview2.promise]);
});

test('the deadline answers 504 TIMEOUT: a waiting request is dropped, a running one is asked to stop', async () => {
  reset();
  const p = pool({ threads: 1, inflight: 2 });
  const r = p.submit(job('A', 'slow', 2000, { deadlineAt: performance.now() + 100, task: { kind: 'sleep', ms: 2000, busy: true, tag: 'slow' } as never }));
  const w = p.submit(job('A', 'waits', 10, { deadlineAt: performance.now() + 50 }));
  await assert.rejects(w.promise, (e: unknown) => e instanceof ScreenerError && e.code === 'TIMEOUT' && e.status === 504);
  await assert.rejects(r.promise, (e: unknown) => e instanceof ScreenerError && e.code === 'TIMEOUT');
  await until(() => logs.events('fake_cancelled').some(l => l.tag === 'slow'), 3000);
  assert.ok(!logs.events('fake_start').some(l => l.tag === 'waits'), 'the dropped request never started');
  const next = p.submit(job('A', 'next', 1));                 // the thread serves the next one
  await next.promise;
});

test('a thread that does not stop is terminated after the grace and started again with the snapshots installed', async () => {
  reset();
  const p = pool({ threads: 1 });
  await p.install('sid-1', {} as never, 0);
  const r = p.submit(job('A', 'stuck', 3000, { deadlineAt: performance.now() + 100, task: { kind: 'sleep', ms: 3000, stuck: true, tag: 'stuck' } as never }));
  await assert.rejects(r.promise, (e: unknown) => e instanceof ScreenerError && e.code === 'TIMEOUT');
  await until(() => logs.events('thread_killed').length > 0, 5000);
  assert.equal(p.stats.killed, 1);
  const again = await p.submit(job('A', 'after', 1)).promise;
  assert.equal((again.outcome as { tag: string }).tag, 'after');
  assert.ok(p.threads[0].alive);
});

test('a caller that leaves: its waiting request is removed and never runs', async () => {
  reset();
  const p = pool({ threads: 1 });
  const busy = p.submit(job('A', 'busy', 60));
  await sleep(5);
  const gone = p.submit(job('B', 'gone', 10));
  gone.cancel();
  await assert.rejects(gone.promise, (e: unknown) => (e as Error).name === 'CallerLeft');
  await busy.promise;
  await sleep(30);
  assert.ok(!order().includes('gone'));
  assert.equal(p.queued, 0);
});

test('P33: an owner over SCREENER_OWNER_CPU_MS in the last minute is refused with the wait; others are not', () => {
  let t = 1_000_000;
  const b = new OwnerBudget(1000, () => t);
  b.record('A', 700);
  b.check('A', 0, 300);                                         // exactly the budget passes
  assert.throws(() => b.check('A', 0, 301), (e: unknown) => e instanceof ScreenerError && e.code === 'LIMIT_EXCEEDED'
    && (e.details as any).limit === 'owner_cpu_budget' && (e.details as any).allowed === 1000 && (e.details as any).needed === 1001 && (e.details as any).retry_after_seconds === 60);
  assert.throws(() => b.check('A', 400, 0), /used 700 ms/, 'waiting work counts');
  b.check('B', 0, 1000);                                        // another owner has its own minute
  b.check(SYSTEM, 0, 1e9);                                      // the publication's own work is never refused
  t += 30_000; b.record('A', 200);
  t += 30_001;                                                  // the 700 ms are now older than a minute
  b.check('A', 0, 800);
  assert.equal(b.spent('A'), 200);
});
