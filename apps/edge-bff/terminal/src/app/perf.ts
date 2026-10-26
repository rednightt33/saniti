/* EXEC-TERMINAL-SPEED step 1 (user 2026-10-26: "goalnya adalah kecepatan loading data"): the page marks each loading
   stage (milliseconds since the page started) and the worker reports every download (time, size, browser cache).
   /terminal-app/?perf=1 shows them in a small box, so the numbers can be read from the user's own location. */
import type { FileStat } from '../data/worker';

const marks: [string, number][] = [];
const files: FileStat[] = [];
const on = typeof location !== 'undefined' && new URLSearchParams(location.search).get('perf') === '1';
let box: HTMLElement | null = null;

function render() {
  if (!on || typeof document === 'undefined') return;
  if (!box) {
    box = document.createElement('pre');
    box.className = 'ml-perf';
    box.setAttribute('aria-label', 'Loading times');
    document.body.appendChild(box);
  }
  const kb = (n: number) => (n / 1000).toFixed(1) + ' KB';
  const net = files.filter(f => !f.cached), hit = files.length - net.length;
  box.textContent = marks.map(([name, ms]) => `${String(ms).padStart(6)} ms  ${name}`).join('\n')
    + `\n\nfiles ${files.length} (browser cache ${hit}), downloaded ${kb(net.reduce((t, f) => t + f.bytes, 0))}\n`
    + files.map(f => `${String(f.ms).padStart(6)} ms  ${kb(f.bytes).padStart(9)}  ${f.cached ? 'cache' : 'net  '}  ${f.name}`).join('\n');
}

export function mark(name: string) {
  marks.push([name, Math.round(performance.now())]);
  try { performance.mark('terminal:' + name) } catch { /* marks are optional */ }
  render();
}

export function fileStats(list: FileStat[]) {
  files.push(...list);
  render();
}
