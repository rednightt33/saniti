/* EXEC-SECTOR-ANALYSIS S4: the cumulative-return line chart the prototype draws twice (Cumulative Return, logic.js
   L1059-1080, and a sector's stock lines, L313-356): grey lines, the chosen lines coloured with their end labels, the
   benchmark dashed. The hovered line is found from the pointer's position, never from the element under it, so the
   read-out stays while the chart is drawn again for a new highlighted line (defect D06). */
import * as M from './model.ts';
import { esc, textW, tipHide, tipShow, xHide, xShow, xTag } from './ui.ts';

export interface Line { n: string; label: string; a: M.N[]; c?: string; on: boolean; dash?: boolean; strong?: boolean; mute?: boolean; dot?: boolean }
/** the text colour of a line's end label: the line's colour mixed with the text colour, so a dark navy or a light amber
    label stays readable on its theme (check 1 MX-5: "Financials −11.3%" in navy on the dark surface read 2.67:1) */
export const labelInk = (c: string | undefined) => (c && c !== 'var(--text)' ? `color-mix(in srgb,${c} 55%,var(--text))` : 'var(--text)');
export interface Geo { L: number; R: number; T: number; B: number; H: number; n: number; X(i: number): number; Y(v: number): number }
/** draws the chart into `box` (its size); `dates` are the dates of the points */
export function cumChart(box: HTMLElement, lines: Line[], dates: string[]): Geo | null {
  const W = box.clientWidth, H = box.clientHeight;
  if (!W || !H || dates.length < 2) { box.innerHTML = ''; return null }
  const on = lines.filter(x => x.on), vals = lines.flatMap(x => x.a).filter((v): v is number => v != null && Number.isFinite(v));
  if (!vals.length) { box.innerHTML = ''; return null }
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), pd = (hi - lo) * 0.06 || 1, tk = M.ticks(lo - pd, hi + pd, 5);
  const y0 = Math.min(lo - pd, tk[0]), y1 = Math.max(hi + pd, tk[tk.length - 1]);
  const last = (x: Line) => { for (let i = x.a.length - 1; i >= 0; i--) if (x.a[i] != null) return x.a[i] as number; return null };
  const lab = on.filter(x => last(x) != null).map(x => ({ x, t: `${x.label} ${M.pct(last(x), 1)}`, y: 0 }));
  const narrow = W < 300;
  const RW = narrow ? 8 : Math.max(40, ...lab.map(l => textW(l.t))) + 14, L = 44, T = 8, B = 24, R = W - RW, n = dates.length;
  const X = (i: number) => L + (i / (n - 1)) * (R - L), Y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let o = tk.map(t => `<line x1="${L}" x2="${R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${Math.abs(t) < 1e-9 ? 'var(--chart-base)' : 'var(--chart-grid)'}"/><text x="${L - 6}" y="${Y(t) + 3.5}" text-anchor="end" class="ax">${M.axPct(t)}</text>`).join('');
  const picks = (R - L < 170 ? [0, 1] : R - L < 260 ? [0, 0.5, 1] : R - L < 520 ? [0, 1 / 3, 2 / 3, 1] : [0, 0.25, 0.5, 0.75, 1]).map(f => Math.round(f * (n - 1)));
  M.axisDates(dates, picks).forEach((t, k) => (o += `<text x="${X(picks[k])}" y="${H - 6}" text-anchor="${k === 0 ? 'start' : k === picks.length - 1 ? 'end' : 'middle'}" class="ax">${esc(t)}</text>`));
  const P = (a: M.N[]) => { let s = '', pen = false; a.forEach((v, i) => { if (v == null) { pen = false; return } s += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true }); return s };
  lines.filter(x => !x.on).forEach(x => (o += `<path d="${P(x.a)}" fill="none" stroke="var(--sx-dim)" stroke-width="1"${x.mute ? ' stroke-opacity=".5"' : ''}/>`));
  on.forEach(x => (o += `<path d="${P(x.a)}" fill="none" stroke="${x.c || 'var(--text)'}" stroke-width="${x.dash ? 1.4 : x.strong ? 2.6 : 1.9}"${x.mute ? ' stroke-opacity=".22"' : ''}${x.dash ? ' stroke-dasharray="4 3"' : x.dot ? ' stroke-dasharray="7 3"' : ''} stroke-linejoin="round"/>`));
  if (!narrow) {
    lab.forEach(l => (l.y = Y(last(l.x) as number))); lab.sort((p, q) => p.y - q.y);
    for (let i = 1; i < lab.length; i++) if (lab[i].y - lab[i - 1].y < 13) lab[i].y = lab[i - 1].y + 13;
    const over = lab.length ? lab[lab.length - 1].y - (H - B) : 0;
    if (over > 0) lab.forEach(l => (l.y -= over));
    lab.forEach(l => (o += `<circle cx="${R}" cy="${Y(last(l.x) as number)}" r="2.5" fill="${l.x.c || 'var(--text)'}"${l.x.mute ? ' opacity=".3"' : ''}/><text x="${R + 6}" y="${l.y + 3.5}" class="dl" style="fill:${labelInk(l.x.c)}${l.x.mute ? ';opacity:.35' : ''}">${esc(l.t)}</text>`));
  }
  o += `<line class="hv" y1="${T}" y2="${H - B}" stroke="var(--text-3)" stroke-dasharray="2 3" display="none"/><circle class="hd" r="4" stroke="var(--surface)" stroke-width="1.5" display="none"/>`;
  box.innerHTML = `<svg width="${W}" height="${H}" aria-hidden="true">${o}</svg>`;
  return { L, R, T, B, H, n, X, Y };
}
/** the hover of a cumulative chart: the line nearest the pointer (within 14 px) is reported to `pick`, which may draw the
    chart again; the crosshair, its date tag, the dot and the read-out are placed after it */
export function cumHover(box: HTMLElement, o: { geo(): Geo | null; lines(): Line[]; dates(): string[]; pick(n: string | null): void; tip(n: string, i: number, v: number): string; candidates?(): Line[] }) {
  box.dataset.ownTip = '';
  const leave = () => { o.pick(null); tipHide(); xHide(box.querySelector('line.hv')); box.querySelector('circle.hd')?.setAttribute('display', 'none') };
  box.onpointerleave = e => { if (e.pointerType === 'mouse') leave() };
  box.onpointermove = box.onpointerdown = e => {
    const g = o.geo(); if (!g) return;
    const r = box.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (mx < g.L || mx > g.R || my < g.T || my > g.H - g.B) { leave(); return }
    const i = Math.max(0, Math.min(g.n - 1, Math.round(((mx - g.L) / (g.R - g.L)) * (g.n - 1))));
    let best: Line | null = null, bd = 1e9;
    for (const x of (o.candidates ? o.candidates() : o.lines())) { const v = x.a[i]; if (v == null) continue; const d = Math.abs(g.Y(v) - my); if (d < bd) { bd = d; best = x } }
    const hit = best && bd < 14 ? best : null;
    o.pick(hit ? hit.n : null);
    const g2 = o.geo(), vx = box.querySelector('line.hv') as SVGLineElement | null, vd = box.querySelector('circle.hd') as SVGCircleElement | null;
    if (!hit || !g2 || !vx || !vd) { tipHide(); xHide(vx); vd?.setAttribute('display', 'none'); return }
    const v = hit.a[i] as number;
    xShow(vx, g2.X(i)); xTag(vx, M.tagDate(o.dates()[i]));
    vd.setAttribute('cx', String(g2.X(i))); vd.setAttribute('cy', String(g2.Y(v))); vd.setAttribute('fill', hit.c || 'var(--text)'); vd.removeAttribute('display');
    tipShow(o.tip(hit.n, i, v), e);
  };
}
