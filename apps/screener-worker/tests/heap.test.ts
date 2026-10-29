/* Each thread's V8 heap limit (SCREENER_THREAD_HEAP_MB, pool.ts ComputeThread; performance review 2026-10-29,
   verification/screener/BENCHMARK_LOCAL.md): without it V8 let every compute thread's heap grow towards its default
   limit (about 2 GB per thread on the 16 GB host) with the garbage of the screens, and the replica's memory with it.
   With it a thread keeps its heap under the limit, and a thread that needs more stops alone: its request is answered
   with the thread's out-of-memory stop and the pool starts the thread again, while the other threads keep serving. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { loadConfig } from '../src/config.ts';
import { OwnerBudget, Pool, ThreadStopped } from '../src/pool.ts';
import type { JobSpec } from '../src/pool.ts';
import { captureLogs, envFor } from './helpers.ts';

captureLogs();
const script = new URL('./fake-thread.mjs', import.meta.url);
const pools: Pool[] = [];
// an idle thread does not hold the process (pool.ts hold); a timer does, while a test awaits a thread's heap statistics
const alive = setInterval(() => {}, 1000);
after(async () => { clearInterval(alive); await Promise.all(pools.map(p => p.close())) });
const pool = (heapMb: number | null, threads = 2) => {
  const p = new Pool({ threads, queue: 10, ownerInflight: 2, quantumMs: 100, script, data: { env: { capBudgetMs: 1, withinMax: 1, maxResponseBytes: 1 }, terminal: null },
    budget: new OwnerBudget(1e9), heapMb });
  pools.push(p);
  return p;
};
const job = (owner: string, task: object): JobSpec => ({ owner, kind: 'run', page: null, order: null, cost: 1, deadlineAt: performance.now() + 60_000, task: task as never });

test('SCREENER_THREAD_HEAP_MB is required (no default) and at least 64', () => {
  loadConfig(envFor('http://127.0.0.1:9'));
  assert.throws(() => loadConfig(envFor('http://127.0.0.1:9', { SCREENER_THREAD_HEAP_MB: '32' })), /SCREENER_THREAD_HEAP_MB must be a whole number of at least 64/);
  const env = envFor('http://127.0.0.1:9'); delete env.SCREENER_THREAD_HEAP_MB;
  assert.throws(() => loadConfig(env), /SCREENER_THREAD_HEAP_MB is required/);
});

test('a compute thread and a builder run under the configured heap limit; without one V8 keeps its own, far larger', async () => {
  const p = pool(96), q = pool(null, 1);
  await p.submit(job('A', { kind: 'sleep', ms: 1, tag: 'x' })).promise;
  await q.submit(job('A', { kind: 'sleep', ms: 1, tag: 'y' })).promise;
  const h = await p.threads[0].heap(), d = await q.threads[0].heap();
  assert.ok(h && h.limit_mb >= 96 && h.limit_mb <= 96 + 64, `limited: ${JSON.stringify(h)}`);
  assert.ok(d && d.limit_mb > 4 * 96, `V8's own: ${JSON.stringify(d)}`);
  const b = p.builder('builder', { role: 'builder', env: { capBudgetMs: 1, withinMax: 1, maxResponseBytes: 1 }, terminal: null });
  await (await b.run({ kind: 'sleep', ms: 1, tag: 'b' } as never)).done;
  const bh = await b.heap();
  assert.ok(bh && bh.limit_mb <= 96 + 64, `the builder too: ${JSON.stringify(bh)}`);
  await b.kill();
});

test('a thread that needs more than its limit stops alone: its request fails with the out-of-memory stop, the other thread serves, the thread starts again', async () => {
  const p = pool(96);
  const big = p.submit(job('A', { kind: 'alloc', mb: 400, tag: 'big' }));
  const small = p.submit(job('B', { kind: 'sleep', ms: 50, tag: 'small' }));
  await assert.rejects(big.promise, (e: unknown) => e instanceof ThreadStopped && e.code === 'ERR_WORKER_OUT_OF_MEMORY', 'the request sees the thread\'s out-of-memory stop');
  assert.equal(((await small.promise).outcome as { tag: string }).tag, 'small', 'the other thread served its request');
  for (let i = 0; i < 4; i++) assert.equal(((await p.submit(job('A', { kind: 'sleep', ms: 1, tag: `after${i}` })).promise).outcome as { tag: string }).tag, `after${i}`, 'every thread serves again');
});
