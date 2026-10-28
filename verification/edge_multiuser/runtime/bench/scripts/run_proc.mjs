/* Spawns one fresh process and measures it from outside: wall from spawn to the first stdout line whose JSON has
   event == <readyEvent> (or matches a regex), RSS sampled from /proc/<pid>/status every 20 ms (VmRSS; VmHWM = peak),
   the child's JSON lines, and the RSS some seconds after ready (idle steady). Usage:
   node run_proc.mjs <out.json> <readyEvent|re:/regex/> <idleAfterReadyMs> -- <cmd> <args...>
   Optional env RUN_PROC_CWD. Read-only on the repository. */
import { spawn } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const [out, readyArg, idleArg, dash, cmd, ...args] = process.argv.slice(2);
if (dash !== '--') throw new Error('usage');
const idleMs = Number(idleArg);
const isReady = readyArg.startsWith('re:') ? (l) => new RegExp(readyArg.slice(3)).test(l) : (l) => { try { return JSON.parse(l).event === readyArg } catch { return false } };
const status = pid => { try { const s = readFileSync(`/proc/${pid}/status`, 'utf8'); const g = k => Number((new RegExp(`^${k}:\\s+(\\d+)`, 'm').exec(s) || [])[1] || 0) / 1024; return { rss: g('VmRSS'), hwm: g('VmHWM') } } catch { return null } };
const loadavg = () => readFileSync('/proc/loadavg', 'utf8').split(' ').slice(0, 3).map(Number);
const load_start = loadavg();
const t0 = performance.now();
const child = spawn(cmd, args, { cwd: process.env.RUN_PROC_CWD || process.cwd(), env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
const samples = [], lines = [];
let readyAt = null, hwm = 0, buf = '', err = '', idleRss = null, killed = false;
const tick = setInterval(() => { const s = status(child.pid); if (s) { samples.push([Math.round(performance.now() - t0), Math.round(s.rss)]); hwm = Math.max(hwm, s.hwm) } }, 20);
child.stdout.on('data', d => {
  buf += d; let i;
  while ((i = buf.indexOf('\n')) >= 0) {
    const l = buf.slice(0, i); buf = buf.slice(i + 1);
    const at = Math.round(performance.now() - t0); lines.push({ at, l });
    if (readyAt === null && isReady(l)) {
      readyAt = at;
      if (idleMs >= 0) setTimeout(() => { const s = status(child.pid); idleRss = s && Math.round(s.rss); if (process.env.RUN_PROC_KILL) { killed = true; child.kill('SIGTERM') } }, idleMs);
    }
  }
});
child.stderr.on('data', d => { err += d });
const exit = await new Promise(ok => child.on('exit', (code, sig) => ok({ code, sig })));
clearInterval(tick);
const parsed = lines.map(x => { try { return { at: x.at, ...JSON.parse(x.l) } } catch { return { at: x.at, text: x.l.slice(0, 300) } } });
const res = { load_start, load_end: loadavg(), cmd: [cmd, ...args].join(' '), spawn_to_ready_ms: readyAt, peak_rss_mb: Math.round(hwm), idle_rss_mb: idleRss,
  max_sampled_rss_mb: samples.reduce((m, s) => Math.max(m, s[1]), 0), exit, killed, stderr_tail: err.slice(-800), lines: parsed,
  rss_curve: samples.filter((_, i) => i % 5 === 0) };
writeFileSync(out, JSON.stringify(res, null, 1));
console.log(JSON.stringify({ out, load: [res.load_start[0], res.load_end[0]], spawn_to_ready_ms: readyAt, peak_rss_mb: res.peak_rss_mb, idle_rss_mb: idleRss, exit }));
