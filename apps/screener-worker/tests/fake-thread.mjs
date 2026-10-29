/* A compute thread for the pool's tests (pool.ts protocol, thread.ts): install / drop are acknowledged; a task
   {kind: 'sleep', ms, busy?, stuck?, tag} waits `ms` (busy: spins the CPU, checking the cancel flag between slices;
   stuck: spins without checking, so only termination stops it) and answers {tag, busy_ms}; {kind: 'fail'} answers a
   contract error; {kind: 'alloc', mb} keeps about `mb` MB of heap alive (the thread heap limit's test). Each task's start and end are posted as log lines ({event: 'fake_start' | 'fake_end', tag}). */
import { parentPort, workerData } from 'node:worker_threads';

const port = parentPort;
const flag = workerData.flag;
const line = (event, fields) => port.postMessage({ type: 'log', line: JSON.stringify({ ts: new Date().toISOString(), level: 'info', event, thread: workerData.name, ...fields }) });
let chain = Promise.resolve();
port.on('message', m => { chain = chain.then(() => handle(m)) });

async function handle(m) {
  if (m.type === 'install') { port.postMessage({ type: 'installed', sid: m.sid, ms: 0 }); return }
  if (m.type === 'drop') return;
  const { seq, task } = m, t0 = performance.now();
  line('fake_start', { tag: task.tag, seq });
  try {
    if (task.kind === 'fail') throw Object.assign(new Error('refused'), { code: 'INVALID_CONDITION' });
    if (task.kind === 'alloc') { const keep = []; for (let i = 0; i < task.mb; i++) keep.push(new Array(131072).fill(i)); line('fake_alloc', { tag: task.tag, arrays: keep.length }) }
    const end = performance.now() + (task.ms ?? 0);
    if (task.stuck) { while (performance.now() < end) { /* no cancel check */ } }
    else if (task.busy) {
      while (performance.now() < end) {
        if (Atomics.load(flag, 0) === seq) { line('fake_cancelled', { tag: task.tag }); port.postMessage({ type: 'failed', seq, error: { status: 409, error: { code: 'CANCELLED' }, known: true, cancelled: true } }); return }
        const slice = performance.now() + 2; while (performance.now() < slice) { /* spin */ }
      }
    } else await new Promise(r => setTimeout(r, task.ms ?? 0));
    line('fake_end', { tag: task.tag, seq });
    port.postMessage({ type: 'done', seq, outcome: { tag: task.tag, busy_ms: Math.round(performance.now() - t0) } });
  } catch (e) {
    port.postMessage({ type: 'failed', seq, error: { status: 422, error: { code: e.code ?? 'INTERNAL_ERROR', message: e.message }, known: true, cancelled: false } });
  }
}
