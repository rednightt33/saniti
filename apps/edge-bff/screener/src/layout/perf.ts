/* EXEC-SCREENER-V21 layout: "Stock vs IHSG" as a chart like the main one (reference layout.js 283-299, 645-662):
   % change on the right axis (graduations of the drawn scale, not a stock's figure), months below, and a hover
   crosshair with the date and both closes. The lines are the ones preview.ts already draws from the preview answer
   (closes rebased to 100 at the period start). The hover shows the answer's own closes of that date (integration of
   the data audit: a return at an intermediate date is not a number the worker gave, so it is not shown); the period
   totals stay the worker's perf figures in the legend. */
import { esc, fmtValue } from '../format.ts';

interface Plot { s: number[]; i: number[]; dates: string[]; tk: string; cs: (number | null)[]; ci: (number | null)[] }
let cur: Plot | null = null;
const H = 120;

function niceStep(range: number) { const raw = range / 4, p = Math.pow(10, Math.floor(Math.log10(raw || 1))); for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= raw) return m * p; return 10 * p }
const monthOf = (d: string) => { const t = new Date(d + 'T00:00:00Z'); return isNaN(+t) ? null : t };

/** the plot of the two rebased lines: `svg` is preview.ts's drawing; the axes are added around it */
export function perfPlot(svg: string, s: number[], i: number[], dates: string[], tk: string, cs: (number | null)[], ci: (number | null)[]): string {
  cur = { s, i, dates, tk, cs, ci };
  const all = [...s, ...i].filter(v => Number.isFinite(v)); if (!all.length) return svg;
  const lo = Math.min(...all), hi = Math.max(...all), r = (hi - lo) || 1, st = niceStep(hi - lo || 1);
  let ya = '';
  for (let v = Math.ceil((lo - 100) / st) * st; v <= hi - 100 + 1e-9; v += st) {
    const y = H - 3 - ((v + 100) - lo) / r * (H - 6);
    ya += `<span style="top:${y.toFixed(1)}px">${v > 0 ? '+' : ''}${+v.toFixed(1)}%</span><i style="top:${y.toFixed(1)}px"></i>`;
  }
  const n = s.length, marks: [number, Date][] = []; let last = '';
  for (let k = 0; k < n; k++) { const t = dates[k] ? monthOf(dates[k]) : null; if (!t) continue; const key = t.getUTCFullYear() + '-' + t.getUTCMonth(); if (key !== last) { last = key; if (k > n * 0.04 && k < n * 0.96) marks.push([k, t]) } }
  const keep = marks.filter((_, k) => marks.length <= 6 || k % Math.ceil(marks.length / 6) === 0);
  const xa = keep.map(([k, t]) => `<span style="left:${(k / Math.max(1, n - 1) * 100).toFixed(2)}%">${t.toLocaleDateString('en-GB', { month:'short', timeZone:'UTC' })}${t.getUTCMonth() === 0 ? ' ' + String(t.getUTCFullYear()).slice(2) : ''}</span>`).join('');
  return `<div class="pplot">${svg}<div class="pax-y" aria-hidden="true">${ya}</div></div><div class="pax-x" aria-hidden="true">${xa}</div>`;
}

let tipEl: HTMLElement | null = null;
function move(e: PointerEvent) {
  const svg = (e.target as Element).closest?.('.pcard svg') as SVGElement | null;
  if (!cur || !svg) { out(); return }
  const card = svg.closest('.pcard') as HTMLElement, r = svg.getBoundingClientRect(), n = cur.s.length; if (n < 2) return;
  const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), k = Math.round(f * (n - 1)), x = r.left + k / (n - 1) * r.width;
  let ln = card.querySelector('.perf-x') as HTMLElement | null; if (!ln) { ln = document.createElement('i'); ln.className = 'perf-x'; card.appendChild(ln) }
  const cr = card.getBoundingClientRect(); ln.style.left = (x - cr.left) + 'px'; ln.style.top = (r.top - cr.top) + 'px'; ln.style.height = r.height + 'px'; ln.hidden = false;
  const d = cur.dates[k], t = d ? monthOf(d) : null;
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'perf-tip'; tipEl.setAttribute('role', 'tooltip'); document.body.appendChild(tipEl) }
  const close = (v: number | null | undefined, f: 'price' | 'index') => v == null || !Number.isFinite(v) ? 'no close' : fmtValue(v, f === 'price' ? 'price' : 'fraction');
  tipEl.innerHTML = `<b>${t ? t.toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric', timeZone:'UTC' }) : ''}</b><span><i class="pt-s"></i>${esc(cur.tk)} close <em>${esc(close(cur.cs[k], 'price'))}</em></span><span><i class="pt-i"></i>IHSG close <em>${esc(close(cur.ci[k], 'index'))}</em></span>`;
  tipEl.hidden = false;
  const w = tipEl.offsetWidth;
  tipEl.style.left = Math.max(8, Math.min(x - w / 2, innerWidth - w - 8)) + 'px'; tipEl.style.top = Math.max(8, r.top - tipEl.offsetHeight - 6) + 'px';
}
function out() { if (tipEl) tipEl.hidden = true; document.querySelectorAll<HTMLElement>('#dtb .perf-x').forEach(l => { l.hidden = true }) }
export function bindPerf() {
  const dtb = document.getElementById('dtb')!;
  dtb.addEventListener('pointermove', move, { passive:true });
  dtb.addEventListener('pointerleave', out);
  addEventListener('scroll', out, { capture:true, passive:true });
}
