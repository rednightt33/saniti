/* EXEC-BROKER-INV-PANEL (user 2026-11-06: "tambahkan juga 2x domestic foreign map (terlampir)", "1B" own panel, "2A"
   English labels; design verification/terminal_api/top_broker_clarity/user_design/peta_asing_domestik.html): the Foreign ×
   Domestic map. x = the Top N groups' foreign net ÷ the period's total buy value, y = the same for domestic transactions,
   so x + y = the Bandar verdict's ratio (Top brokers). The verdict's ±6%/±10% lines are not drawn (user 2026-11-06); the
   verdict tag above the map carries them. Values are percent. */
import { FD_DP, FD_QUADRANTS, fdQuadrant, fdShown } from '../data/brokerAgg';

export interface MapPoint { label: string; x: number; y: number; r: number; cur: boolean; tip: string; empty?: boolean }

/** the axis half-range: the largest |value| (at least `min`) with 15% room, rounded up to 5 (10 above 40) */
export const mapLimit = (vals: number[], min = 12) => {
  const m = Math.max(min, ...vals.filter(Number.isFinite).map(Math.abs)) * 1.15, st = m > 40 ? 10 : 5;
  return Math.ceil(m / st) * st;
};

const esc = (s: string) => s.replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
/** a shown figure (already rounded, fdShown) with its sign: never "−0.00%" */
export const fdPct = (v: number) => { const r = +v.toFixed(FD_DP); return `${r > 0 ? '+' : r < 0 ? '−' : ''}${Math.abs(r).toFixed(FD_DP)}%` };
const pct = fdPct;
/** green, red or neither from the figure as shown (QA F3: "0.00%" is never coloured) */
export const fdCls = (v: number) => { const r = +v.toFixed(FD_DP); return r > 0 ? 'up' : r < 0 ? 'down' : '' };

/** the map as SVG: quadrant shading and names, a light grid at half range, tick labels (−lim, −lim/2, 0, +lim/2, +lim),
    the points (current one larger) and a trail through them; axis titles say what the % is of */
export function mapSvg(pts: MapPoint[], lim: number): string {
  const S = 236, L = 46, T = 8, B = 16,   // QA H3: room for "−17.5%" left of the plot
  P = (v: number) => (Math.max(-lim, Math.min(lim, v)) + lim) / (2 * lim) * S, X = P, Y = (v: number) => S - P(v);
  const out = (v: number) => Math.abs(v) > lim, ticks = [-lim, -lim / 2, 0, lim / 2, lim];
  const tick = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}%`;
  let g = `<svg class="fdm-svg" viewBox="0 0 ${L + S + 6} ${T + S + B}" role="img" aria-label="Foreign against domestic contribution to the verdict">`;
  for (const v of ticks) {
    g += `<text x="${L - 4}" y="${(T + Y(v) + 3).toFixed(1)}" class="fdm-tk" text-anchor="end">${tick(v)}</text>`;
    g += `<text x="${(L + X(v)).toFixed(1)}" y="${T + S + 12}" class="fdm-tk" text-anchor="${v === -lim ? 'start' : v === lim ? 'end' : 'middle'}">${tick(v)}</text>`;
  }
  g += `<g transform="translate(${L} ${T})"><defs><clipPath id="fdm-clip"><rect x="0" y="0" width="${S}" height="${S}" rx="6"/></clipPath></defs><g clip-path="url(#fdm-clip)">`;
  g += `<rect x="0" y="0" width="${S}" height="${S}" fill="var(--surface)"/>`;
  g += `<rect x="${S / 2}" y="0" width="${S / 2}" height="${S / 2}" fill="rgba(8,153,129,.08)"/><rect x="0" y="${S / 2}" width="${S / 2}" height="${S / 2}" fill="rgba(242,54,69,.07)"/>`;
  for (const v of [-lim / 2, lim / 2]) g += `<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${S}" stroke="var(--border)" stroke-dasharray="2 3"/><line x1="0" y1="${Y(v)}" x2="${S}" y2="${Y(v)}" stroke="var(--border)" stroke-dasharray="2 3"/>`;
  // EXEC-TERMINAL-LOOK-2 (5, user 2026-11-06: "hanya 4 garis miring yang dihapus"): no verdict diagonals
  g += `<line x1="${S / 2}" y1="0" x2="${S / 2}" y2="${S}" stroke="var(--text-3)" stroke-width="1"/><line x1="0" y1="${S / 2}" x2="${S}" y2="${S / 2}" stroke="var(--text-3)" stroke-width="1"/>`;
  // the corner names fit inside their quadrant (half the map); the full name is the tag above the map
  g += `<text x="${S - 6}" y="12" class="fdm-q" text-anchor="end">Both accumulate</text><text x="6" y="12" class="fdm-q">Domestic absorbs</text>`;
  g += `<text x="${S - 6}" y="${S - 6}" class="fdm-q" text-anchor="end">Foreign absorbs</text><text x="6" y="${S - 6}" class="fdm-q">Both distribute</text>`;
  const ok = pts.filter(p => !p.empty && Number.isFinite(p.x) && Number.isFinite(p.y));
  if (ok.length > 1) g += `<polyline points="${ok.map(p => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(' ')}" fill="none" stroke="var(--text-3)" stroke-width="1" opacity=".8"/>`;
  /* QA M4 (2026-11-06): the current (larger) dot is drawn first so a smaller dot near it stays on top and can be pointed
     at; the hit area is a little larger than the dot, and every dot takes keyboard focus with its tooltip as its name */
  /* QA round 4 (L3): points at the same place ("5D" and "1D" both at 0, 0) put their labels one under the other */
  const placed: [number, number][] = [];
  for (const p of [...ok].sort((a, b) => Number(b.cur) - Number(a.cur))) {
    const cx = X(p.x), cy0 = Y(p.y), r = p.cur ? 6 : 4, hollow = out(p.x) || out(p.y), right = cx > S - 40;
    let ly = cy0; while (placed.some(([x, y]) => Math.abs(x - cx) < 18 && Math.abs(y - ly) < 10)) ly += 11;
    placed.push([cx, ly]); const cy = cy0;
    /* EXEC-TERMINAL-LOOK-2 (5): a dot grows under the pointer and the panel's tooltip names its period and figures */
    /* EXEC-RP-LOOK R7 (user 2026-11-07: "kalau hover ke dot tidak usah muncul tool tip, hapus"): no tooltip on a point; a
       screen reader still reads its period and figures */
    g += `<g class="fdm-pt" role="img" aria-label="${esc(p.tip.replace('|', ': '))}">${p.cur ? `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="11" fill="var(--text)" opacity=".12"/>` : ''}`
      + `<circle class="dot" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r}" fill="${hollow ? 'var(--surface)' : 'var(--text)'}" stroke="var(--text)" stroke-width="${hollow ? 1.2 : 0}"/>`
      + `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${r + 3}" fill="transparent"/></g>`
      + `<text x="${(cx + (right ? -9 : 9)).toFixed(1)}" y="${(ly + 3.5).toFixed(1)}" class="fdm-p${p.cur ? ' cur' : ''}" text-anchor="${right ? 'end' : 'start'}">${esc(p.label)}</text>`;
  }
  g += `</g><rect x="0" y="0" width="${S}" height="${S}" rx="6" fill="none" stroke="var(--border)"/></g></svg>`;
  // QA M3: the axes are the investor types of the trades of the Top N brokers, as a share of the period's total buy value
  // EXEC-QA5-FIX (QA F8): the axis titles as the window's (R1 dropped "X ·", "Y ·" and "Top N" from the panel's words)
  return `<div class="fdm-wrap"><span class="fdm-ax fdm-y">Domestic (% of total buy)</span>${g}<span class="fdm-ax fdm-x">Foreign (% of total buy)</span></div>`;
}

/** the quadrant's name and its tag colour */
export const quadrantTag = (x: number, y: number, empty = false, n?: number) => {
  if (empty) return '<span class="tag neu">No buy value in this period</span>';     // reviewer 1: 0 is not "both accumulating"
  const q = fdQuadrant(x, y);
  // QA M3: the reading holds for the Top N brokers' trades, not the whole stock's foreign flow
  return `<span class="tag fdm-t${q}">${FD_QUADRANTS[q]}${n ? ` · Top ${n}` : ''}</span>`;
};

/** the equation under the map and one row per period */
export function mapReadout(cur0: MapPoint, all0: MapPoint[], open = true): string {
  /* EXEC-QA5-FIX (QA F1-F3): the figures as shown, two decimals, Foreign + Domestic = Verdict exactly, colour from them */
  const shown = (p: MapPoint): MapPoint => ({ ...p, ...fdShown(p.x, p.y, p.r) }), cur = shown(cur0), all = all0.map(shown), cls = fdCls;
  const row = (p: MapPoint) => p.empty ? `<div class="fdm-row${p.cur ? ' on' : ''}"><span>${esc(p.label)}</span><span>—</span><span>—</span><span>—</span><span></span></div>`
    : `<div class="fdm-row${p.cur ? ' on' : ''}"><span>${esc(p.label)}</span><span class="${cls(p.x)}">${pct(p.x)}</span><span class="${cls(p.y)}">${pct(p.y)}</span><span class="${cls(p.r)}">${pct(p.r)}</span><span class="fdm-dot fdm-t${fdQuadrant(p.x, p.y)}" title="${FD_QUADRANTS[fdQuadrant(p.x, p.y)]}"></span></div>`;
  /* EXEC-RP-LOOK R1 (user 2026-11-07: "cukup hilangkan "X" & "Y" dan" (Top N)""): plain Foreign and Domestic; R2 ("opsi untuk
     collapse dan expand"): the equation and the table fold under one button, which keeps the verdict when folded */
  return `<div class="fdm-read${open ? '' : ' folded'}"><button type="button" class="fdm-fold" aria-expanded="${open}" aria-controls="fdmDetail"><span class="fdm-ft">Foreign + Domestic = Verdict ${esc(cur.label)}</span><span class="fdm-fv ${cls(cur.r)}">${pct(cur.r)}</span><svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></button>`
    + `<div id="fdmDetail"${open ? '' : ' hidden'}><div class="fdm-eq"><div><span>Foreign</span><b class="${cls(cur.x)}">${pct(cur.x)}</b></div><i>+</i><div><span>Domestic</span><b class="${cls(cur.y)}">${pct(cur.y)}</b></div><i>=</i><div><span>Verdict ${esc(cur.label)}</span><b class="${cls(cur.r)}">${pct(cur.r)}</b></div></div>`
    + `<div class="fdm-tbl"><div class="fdm-row h"><span>Period</span><span>Foreign</span><span>Domestic</span><span>Verdict</span><span></span></div>${all.map(row).join('')}</div></div></div>`;
}

/* ---- EXEC-FD-WINDOW (user 2026-11-07: "Peta + jejak 20 sesi (opsi 2) dan ada toggle untuk switch it ke Tabel penggerak
   per sesi (opsi A)"; "pake seperti HTML terlampir", verification/terminal_api/fd_map_expand/aaaa.html): the window's
   map with one point per session, a line through them, older points fainter, the newest larger and named "now" ---- */
export interface TrailPoint { d: string; x: number; y: number; r: number; empty?: boolean }
const dayOf = (d: string) => new Date(d + 'T00:00:00Z').toLocaleDateString('en-GB', { day:'2-digit', month:'short', timeZone:'UTC' }).replace('Sept', 'Sep');

/** each session's change from the session before, in percentage points, on the figures as shown (fdShown), so
    Δ verdict = Δ foreign + Δ domestic on screen too; the driver is the side that moved more (Foreign on a tie), none when
    the verdict did not move. A session without buy value, or one after it, has no change (EXEC-QA5-FIX F4: a change is
    never taken across a skipped session). Newest first, as the table reads. */
export interface TrailDelta { i: number; d: string; r: number | null; dr: number | null; dx: number | null; dy: number | null; driver: 'fx' | 'dm' | null }
export const trailDeltas = (T: TrailPoint[]): TrailDelta[] => {
  const S = T.map(p => p.empty ? null : fdShown(p.x, p.y, p.r));
  return T.slice(1).map((p, k): TrailDelta => {
    const a = S[k], b = S[k + 1];
    if (!a || !b) return { i:k + 1, d:p.d, r:b ? b.r : null, dr:null, dx:null, dy:null, driver:null };
    const q = (v: number) => +v.toFixed(FD_DP) || 0, dx = q(b.x - a.x), dy = q(b.y - a.y), dr = q(b.r - a.r);
    return { i:k + 1, d:p.d, r:b.r, dr, dx, dy, driver:(dr === 0 ? null : Math.abs(dx) >= Math.abs(dy) ? 'fx' : 'dm') as TrailDelta['driver'] };
  }).reverse();
};

/** the trail map as SVG; `hover` is the index of a point to mark (a table row under the pointer), −1 for none */
export function trailSvg(T: TrailPoint[], lim: number, hover = -1): string {
  const S = 270, P = 38, W = S + P * 2, cl = (v: number) => Math.max(-lim, Math.min(lim, v));
  const sx = (v: number) => P + (cl(v) + lim) / (2 * lim) * S, sy = (v: number) => P + (lim - cl(v)) / (2 * lim) * S;
  const tick = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)}%`, h = S / 2;
  let g = `<svg class="fdw-svg" viewBox="0 0 ${W} ${W}" role="img" aria-label="Foreign against domestic, one point per session">`
    + `<rect x="${P + h}" y="${P}" width="${h}" height="${h}" fill="rgba(8,153,129,.08)"/><rect x="${P}" y="${P + h}" width="${h}" height="${h}" fill="rgba(242,54,69,.07)"/>`
    + `<rect x="${P}" y="${P}" width="${S}" height="${S}" rx="6" fill="none" stroke="var(--border)"/>`
    + `<line x1="${P + h}" y1="${P}" x2="${P + h}" y2="${P + S}" stroke="var(--text-3)" stroke-width=".8"/><line x1="${P}" y1="${P + h}" x2="${P + S}" y2="${P + h}" stroke="var(--text-3)" stroke-width=".8"/>`;
  for (const [t, x, y, a] of [['Domestic absorbs', P + 6, P + 14, 'start'], ['Both accumulate', P + S - 6, P + 14, 'end'], ['Both distribute', P + 6, P + S - 6, 'start'], ['Foreign absorbs', P + S - 6, P + S - 6, 'end']] as const)
    g += `<text x="${x}" y="${y}" class="fdm-q" text-anchor="${a}">${t}</text>`;
  for (const v of [-lim, 0, lim]) g += `<text x="${sx(v)}" y="${P + S + 14}" class="fdm-tk" text-anchor="middle">${tick(v)}</text><text x="${P - 4}" y="${sy(v) + 3}" class="fdm-tk" text-anchor="end">${tick(v)}</text>`;
  g += `<text x="${P + h}" y="${P + S + 30}" class="fdw-ax" text-anchor="middle">Foreign (% of total buy)</text><text x="10" y="${P + h}" class="fdw-ax" text-anchor="middle" transform="rotate(-90 10 ${P + h})">Domestic (% of total buy)</text>`;
  /* EXEC-QA5-FIX (QA F4): a session without buy value has no point and breaks the line; "now" names the last session only
     when it has a point, else the newest point carries its date */
  const ok = T.map((p, i) => ({ p, i })).filter(o => !o.p.empty);
  if (!ok.length) return g + '</svg>';
  let run: string[] = [];
  const flush = () => { if (run.length > 1) g += `<polyline fill="none" stroke="var(--text-3)" stroke-width="1" points="${run.join(' ')}"/>`; run = [] };
  T.forEach(p => { if (p.empty) flush(); else run.push(sx(p.x).toFixed(1) + ',' + sy(p.y).toFixed(1)) }); flush();
  const last = T.length - 1, out = (p: TrailPoint) => Math.abs(p.x) > lim || Math.abs(p.y) > lim;
  T.forEach((p, i) => {
    if (p.empty) return;
    const o = i === hover ? 1 : .25 + .75 * i / Math.max(last, 1), r = i === last ? 7 : i === hover ? 6 : 3.5;
    // a point beyond the range sits on the edge, hollow (as the panel's map)
    g += `<circle class="fdw-pt${i === hover ? ' hl' : ''}" cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="${r}" fill="${out(p) ? 'var(--surface)' : 'var(--text)'}" stroke="var(--text)" stroke-width="${out(p) ? 1.2 : 0}" opacity="${o.toFixed(2)}"/>`;
  });
  const f = ok[0], l = ok[ok.length - 1], lab = (p: TrailPoint, dx: number, dy: number, t: string, c: string) => {
    const right = sx(p.x) > P + S - 44;
    return `<text x="${(sx(p.x) + (right ? -dx : dx)).toFixed(1)}" y="${(sy(p.y) + dy).toFixed(1)}" class="${c}" text-anchor="${right ? 'end' : 'start'}">${t}</text>`;
  };
  // the first point's date unless it would sit on the newest point's label (QA F4: "now" over "20 Oct" at 0, 0)
  const near = Math.hypot(sx(f.p.x) - sx(l.p.x), sy(f.p.y) - sy(l.p.y)) < 16;
  if (ok.length > 1 && !near) g += lab(f.p, 7, 3.5, dayOf(f.p.d), 'fdw-l');
  g += lab(l.p, 10, 3.5, l.i === last ? 'now' : dayOf(l.p.d), 'fdw-l now');
  if (hover >= 0 && hover !== l.i && !T[hover]?.empty && (hover !== f.i || near)) g += lab(T[hover], 9, -6, dayOf(T[hover].d), 'fdw-l hl');
  return g + '</svg>';
}
export { dayOf as trailDay };
