/* A noisy clock for the reproducibility tests (registry-cost.test.mjs, registry-check.test.mjs), preloaded with
   `--import` through NODE_OPTIONS so that the generator and the cost probe's child process both get it: every clock a
   script can read jumps by a random 0-50 ms (wall time, CPU time, high-resolution time), far more than one indicator
   run takes, as a machine under heavy load can make a measured interval look. A generator field that depended on any
   of them would come out different from run to run. Each process that loads it appends its pid to the file named by
   NOISY_CLOCK_LOG, so a test can see that the clock was really in place. */
import fs from 'node:fs';

const jitterMs = () => Math.random() * 50;
const hrtime = process.hrtime, bigint = process.hrtime.bigint, now = performance.now.bind(performance), dateNow = Date.now;
process.hrtime = Object.assign(prev => {
  const [s, ns] = hrtime(), t = s * 1e9 + ns + jitterMs() * 1e6, out = [Math.floor(t / 1e9), Math.floor(t % 1e9)];
  if (!prev) return out;
  const d = (out[0] - prev[0]) * 1e9 + (out[1] - prev[1]);
  return [Math.floor(d / 1e9), d % 1e9];
}, { bigint: () => bigint() + BigInt(Math.floor(jitterMs() * 1e6)) });
performance.now = () => now() + jitterMs();
Date.now = () => dateNow() + Math.floor(jitterMs());
for (const k of ['cpuUsage', 'threadCpuUsage']) {
  const f = process[k];
  if (typeof f === 'function') process[k] = (...a) => { const u = f.apply(process, a); return { user: u.user + Math.floor(jitterMs() * 1e3), system: u.system } };
}
if (process.env.NOISY_CLOCK_LOG) fs.appendFileSync(process.env.NOISY_CLOCK_LOG, `${process.pid}\n`);
