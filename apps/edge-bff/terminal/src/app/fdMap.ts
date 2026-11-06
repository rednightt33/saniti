/* EXEC-BROKER-INV-PANEL (user 2026-11-06: "tambahkan juga 2x domestic foreign map (terlampir)", "1B" own panel, "2A"
   English labels; design verification/terminal_api/top_broker_clarity/user_design/peta_asing_domestik.html): the Foreign ×
   Domestic map. x = the Top N groups' foreign net ÷ the period's total buy value, y = the same for domestic transactions,
   so x + y = the Bandar verdict's ratio (Top brokers). The dashed diagonals are the verdict's ±6% lines, the solid ones
   ±10%: a point between them has that verdict. Values are percent. */
import { FD_QUADRANTS, fdQuadrant } from '../data/brokerAgg';

export interface MapPoint { label: string; x: number; y: number; r: number; cur: boolean; tip: string; empty?: boolean }

/** the axis half-range: the largest |value| (at least `min`) with 15% room, rounded up to 5 (10 above 40) */
export const mapLimit = (vals: number[], min = 12) => {
  const m = Math.max(min, ...vals.filter(Number.isFinite).map(Math.abs)) * 1.15, st = m > 40 ? 10 : 5;
  return Math.ceil(m / st) * st;
};

const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const pct = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v).toFixed(1)}%`;

/** the map as SVG: quadrant shading and names, a light grid at half range, tick labels (−lim, −lim/2, 0, +lim/2, +lim),
    verdict diagonals, the points (current one larger) and a trail through them; axis titles say what the % is of */
export function mapSvg(pts: MapPoint[], lim: number): string {
  const S = 236, L = 30, T = 8, B = 16, P = (v: number) => (Math.max(-lim, Math.min(lim, v)) + lim) / (2 * lim) * S, X = P, Y = (v: number) => S - P(v);
  const out = (v: number) => Math.abs(v) > lim, ticks = [-lim, -lim / 2, 0, lim / 2, lim];
  const tick = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}%`;
  let g = `<svg class="fdm-svg" viewBox="0 0 ${L + S + 6} ${T + S + B}" role="img" aria-label="Foreign against domestic contribution to the verdict">`;
  for (const v of ticks) {
    g += `<text x="${L - 4}" y="${(T + Y(v) + 3).toFixed(1)}" class="fdm-tk" text-anchor="end">${tick(v)}</text>`;
    g += `<text x="${(L + X(v)).toFixed(1)}" y="${T + S + 12}" class="fdm-tk" text-anchor="${v === -lim ? 'start' : v === lim ? 'end' : 'middle'}">${tick(v)}</text>`;
  }
  g += `<g transform="translate(${L} ${T})"><g clip-path="inset(0 round 6px)">`;
  g += `<rect x="0" y="0" width="${S}" height="${S}" fill="var(--surface)"/>`;
  g += `<rect x="${S / 2}" y="0" width="${S / 2}" height="${S / 2}" fill="rgba(8,153,129,.08)"/><rect x="0" y="${S / 2}" width="${S / 2}" height="${S / 2}" fill="rgba(242,54,69,.07)"/>`;
  for (const v of [-lim / 2, lim / 2]) g += `<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${S}" stroke="var(--border)" stroke-dasharray="2 3"/><line x1="0" y1="${Y(v)}" x2="${S}" y2="${Y(v)}" stroke="var(--border)" stroke-dasharray="2 3"/>`;
  for (const c of [6, 10, -6, -10])             // the verdict's lines: foreign + domestic = c
    g += `<line x1="${X(-lim) - S}" y1="${Y(c + lim) - S}" x2="${X(lim) + S}" y2="${Y(c - lim) + S}" stroke="${c > 0 ? 'var(--up)' : 'var(--down)'}" stroke-width="1" ${Math.abs(c) === 10 ? '' : 'stroke-dasharray="3 3"'} opacity=".5"/>`;
  g += `<line x1="${S / 2}" y1="0" x2="${S / 2}" y2="${S}" stroke="var(--text-3)" stroke-width="1"/><line x1="0" y1="${S / 2}" x2="${S}" y2="${S / 2}" stroke="var(--text-3)" stroke-width="1"/>`;
  // the corner names fit inside their quadrant (half the map); the full name is the tag above the map
  g += `<text x="${S - 6}" y="12" class="fdm-q" text-anchor="end">Both accumulate</text><text x="6" y="12" class="fdm-q">Domestic absorbs</text>`;
  g += `<text x="${S - 6}" y="${S - 6}" class="fdm-q" text-anchor="end">Foreign absorbs</text><text x="6" y="${S - 6}" class="fdm-q">Both distribute</text>`;
  const ok = pts.filter(p => !p.empty && Number.isFinite(p.x) && Number.isFinite(p.y));
  if (ok.length > 1) g += `<polyline points="${ok.map(p => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--text-3)" stroke-width="1" opacity=".8"/>`;
  for (const p of ok) {
    const cx = X(p.x), cy = Y(p.y), r = p.cur ? 6 : 4, hollow = out(p.x) || out(p.y), right = cx > S - 40;
    g += `<g><title>${esc(p.tip)}</title>${p.cur ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="11" fill="var(--text)" opacity=".12"/>` : ''}`
      + `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${hollow ? 'var(--surface)' : 'var(--text)'}" stroke="var(--text)" stroke-width="${hollow ? 1.2 : 0}"/></g>`
      + `<text x="${(cx + (right ? -9 : 9)).toFixed(1)}" y="${(cy + 3.5).toFixed(1)}" class="fdm-p${p.cur ? ' cur' : ''}" text-anchor="${right ? 'end' : 'start'}">${esc(p.label)}</text>`;
  }
  g += `</g><rect x="0" y="0" width="${S}" height="${S}" rx="6" fill="none" stroke="var(--border)"/></g></svg>`;
  return `<div class="fdm-wrap"><span class="fdm-ax fdm-y">Y · Domestic (% of total buy)</span>${g}<span class="fdm-ax fdm-x">X · Foreign (% of total buy)</span></div>`;
}

/** the quadrant's name and its tag colour */
export const quadrantTag = (x: number, y: number, empty = false) => {
  if (empty) return '<span class="tag neu">No buy value in this period</span>';     // reviewer 1: 0 is not "both accumulating"
  const q = fdQuadrant(x, y);
  return `<span class="tag fdm-t${q}">${FD_QUADRANTS[q]}</span>`;
};

/** the equation under the map and one row per period */
export function mapReadout(cur: MapPoint, all: MapPoint[]): string {
  const cls = (v: number) => v > 0 ? 'up' : v < 0 ? 'down' : '';
  const row = (p: MapPoint) => p.empty ? `<div class="fdm-row${p.cur ? ' on' : ''}"><span>${esc(p.label)}</span><span>—</span><span>—</span><span>—</span><span></span></div>`
    : `<div class="fdm-row${p.cur ? ' on' : ''}"><span>${esc(p.label)}</span><span class="${cls(p.x)}">${pct(p.x)}</span><span class="${cls(p.y)}">${pct(p.y)}</span><span class="${cls(p.r)}">${pct(p.r)}</span><span class="fdm-dot fdm-t${fdQuadrant(p.x, p.y)}" title="${FD_QUADRANTS[fdQuadrant(p.x, p.y)]}"></span></div>`;
  return `<div class="fdm-eq"><div><span>X · Foreign</span><b class="${cls(cur.x)}">${pct(cur.x)}</b></div><i>+</i><div><span>Y · Domestic</span><b class="${cls(cur.y)}">${pct(cur.y)}</b></div><i>=</i><div><span>Verdict ${esc(cur.label)}</span><b class="${cls(cur.r)}">${pct(cur.r)}</b></div></div>`
    + `<div class="fdm-tbl"><div class="fdm-row h"><span>Period</span><span>X foreign</span><span>Y dom.</span><span>Verdict</span><span></span></div>${all.map(row).join('')}</div>`;
}
