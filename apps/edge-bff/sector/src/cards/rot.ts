/* EXEC-SECTOR-ANALYSIS S4, the Rotation tab (final/click_inventory.md section 7; formulas.md section 4): the rotation map
   (decision A, UD67 2A: "Rotation map", "Relative strength", "Momentum"; the formula is the prototype's, D11) with its
   timeline and IHSG strip, direction and speed, rotation detail and the stock momentum quadrant of one sector. */
import * as M from '../model.ts';
import { calc, shown, type Card, type Ctx, type Detail } from '../ctx.ts';
import { $, $$, H3, SEG, esc, footNow, footSet, msNote, msTh, msWire, onSeg, stockPop, textW, tipHide, tipShow, xHide, xShow, xTag } from '../ui.ts';
import { SEL_SECTOR } from './ov.ts';
import { TOUCH, W } from '../words.ts';

/* one hue per quadrant (the prototype's Rotation colours, as tokens) */
const QC: Record<M.Quad, string> = { Leading: 'var(--up)', Weakening: 'var(--amber-400)', Lagging: 'var(--down)', Improving: 'var(--blue)' };
const QT: Record<M.Quad, string> = { Leading: 'var(--green)', Weakening: 'var(--amber)', Lagging: 'var(--red)', Improving: 'var(--blue)' };
const QB: Record<M.Quad, string> = { Leading: 'color-mix(in srgb,var(--up) 7%,transparent)', Weakening: 'color-mix(in srgb,var(--amber-400) 8%,transparent)', Lagging: 'color-mix(in srgb,var(--down) 6%,transparent)', Improving: 'color-mix(in srgb,var(--blue) 6%,transparent)' };
export const rotQ = (q: M.Quad | null) => (q ? `<span class="rq" style="--c:${QC[q]};--t:${QT[q]}">${esc(W.quad[q])}</span>` : '—');
/** the 52 weekly points of the strip and the timeline: every 5 sessions back from the date */
const weekly = (E: number) => Array.from({ length: 52 }, (_, j) => E - 5 * (51 - j)).filter(i => i >= 0);
const minK = (c: Ctx) => { const K = calc(c.D), tw = c.S.rotT, wk = weekly(c.D.E); return wk.find(i => c.D.names.every(nm => K.rot[nm].mom[i - 5 * tw] != null)) ?? c.D.E };
/** the map's date: the weekly point the viewer clicked on the IHSG strip, else the page's date */
function mapDate(c: Ctx): number {
  const D = c.D, wk = weekly(D.E), mn = minK(c);
  if (!c.S.rotK) return D.E;
  // a date before the strip's first week is its first week, never the page's date (the same "never silently replaced")
  const i = M.seriesEnd(D.dates, c.S.rotK), at = [...wk].reverse().find(x => x <= i) ?? wk[0] ?? D.E;
  return Math.max(mn, Math.min(D.E, at));
}
/** Rotation: one click = that sector only; it replaces sectors highlighted in the detail; the only one again clears both
    the highlight and the lock (logic.js L183; defect D16: the highlight and the lock end together) */
function pick(c: Ctx, nm: string) {
  const S = c.S;
  if (S.rotSel.length === 1 && S.rotSel[0] === nm) { S.rotSel = []; if (S.pin === nm) S.pin = null; c.redraw(); return }
  if (S.rotSel.length) { S.rotSel = [nm]; S.pin = nm; c.redraw(); return }
  c.lock(nm);
}
/** a click on a tile or a detail row: highlight it alone (Ctrl or Cmd: add or remove it) and lock it */
function multi(c: Ctx, nm: string, add: boolean) {
  const S = c.S, s = new Set(S.rotSel);
  if (add) s.has(nm) ? s.delete(nm) : s.add(nm);
  else if (s.size === 1 && s.has(nm)) s.clear();
  else { s.clear(); s.add(nm) }
  S.rotSel = c.D.names.filter(n => s.has(n));
  if (s.has(nm)) S.pin = nm; else if (!s.size && S.pin === nm) S.pin = null;
  c.redraw();
}
const smooth = (P: number[][]) => {
  if (P.length < 3) return P.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join('');
  let d = `M${P[0][0].toFixed(1)} ${P[0][1].toFixed(1)}`;
  for (let i = 0; i < P.length - 1; i++) {
    const p0 = P[i - 1] || P[i], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2] || p2, k = 12;
    d += `C${(p1[0] + (p2[0] - p0[0]) / k).toFixed(1)} ${(p1[1] + (p2[1] - p0[1]) / k).toFixed(1)},${(p2[0] - (p3[0] - p1[0]) / k).toFixed(1)} ${(p2[1] - (p3[1] - p1[1]) / k).toFixed(1)},${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`;
  }
  return d;
};

/* ===================== the rotation map (logic.js L378-421, timeline L443-462, IHSG strip L466-485) ===================== */
export const rotA: Card = {
  // visual round 2 (V8): in a window the Timeline takes the whole width (no readings table, as the prototype); the Map
  // keeps its readings on the right, the window as tall as they are so the plot keeps the prototype's wide proportions
  id: 'rotA', tab: 'rot', cls: 'rot-a', wide: true, fit: ['.rrg'], hideDetail: c => c.S.rotV === 'tl',
  render(el, c) {
    const D = c.D, S = c.S, Kc = calc(D), V = S.rotV, TW = S.rotT, K = mapDate(c), wk = weekly(D.E), sel = S.rotSel, dl = (i: number) => M.dateIn(D.dates[i], D.ref);
    el.classList.toggle('noih', !S.rotIh);
    el.innerHTML = H3(W.rot.title, V === 'map' ? W.rot.sub(D.market, dl(K), TW) : W.rot.subTl(M.rangeLabel(D.dates[wk[0]], D.dates[D.E], D.ref), dl(K)),
      SEG('v', '', [['map', W.rot.map], ['tl', W.rot.timeline]], V) + (V === 'map' ? SEG('t', W.rot.tail, [[4, '4W'], [8, '8W'], [12, '12W']], TW) : '')
      + `<button class="ihq${S.rotIh ? ' on' : ''}" type="button" data-ih aria-pressed="${S.rotIh}" title="${esc(W.rot.ihTip(S.rotIh, D.market))}">${esc(D.market)}</button>`, c.win ? null : 'rotA')
      + `<div class="tb"><div class="ihc" data-strip></div><div class="rrg" data-chart></div></div><div class="lgd">${V === 'map' ? `<span data-foot>${footNow(el, W.rot.foot(false))}</span>` : `<span class="qlg">${M.QUADS.map(q => `<span><i style="background:${QC[q]}"></i>${esc(W.quad[q])}</span>`).join('')}</span>`}<span class="sp"></span><button type="button" class="dchip" data-tip="${esc(esc(W.rot.formulaTip(D.market)))}" aria-label="${esc(W.rot.formula + ': ' + W.rot.formulaTip(D.market))}"><i></i>${esc(W.rot.formula)}</button></div>`;
    onSeg(el, 'v', v => { S.rotV = v; c.redraw() });
    onSeg(el, 't', v => { S.rotT = +v; c.redraw() });
    ($('[data-ih]', el) as HTMLElement).onclick = () => { S.rotIh = !S.rotIh; c.redraw() };
    const box = $('[data-chart]', el);
    if (S.rotIh) strip(c, $('[data-strip]', el), K, V === 'tl' ? (K - wk[0]) / 5 : TW, V === 'tl');
    // the formula reads by hover, tap, or the keyboard (check 1 RP-10: it was a title only)
    const chip = $('.dchip', el); chip.onfocus = chip.onclick = () => { const r = chip.getBoundingClientRect(); tipShow(chip.dataset.tip as string, { clientX: r.left, clientY: r.top - 10 }) }; chip.onblur = tipHide;
    if (V === 'tl') { requestAnimationFrame(() => timeline(c, box, K)); return }
    requestAnimationFrame(() => {
      const Wd = box.clientWidth, Hh = box.clientHeight; if (!Wd || !Hh) return;
      const T = D.names.map(nm => ({ nm, p: Array.from({ length: TW + 1 }, (_, k) => K - 5 * (TW - k)).filter(i => i >= 0 && Kc.rot[nm].mom[i] != null && Kc.rot[nm].rs[i] != null).map(i => [Kc.rot[nm].rs[i] as number, Kc.rot[nm].mom[i] as number, i]), q: Kc.q[nm][K] })).filter(t => t.p.length);
      if (!T.length) { box.innerHTML = `<div class="cv-empty">${esc(W.rot.noData)}</div>`; return }
      const LST = (t: typeof T[0]) => t.p[t.p.length - 1];
      const dx = Math.max(0.5, ...T.flatMap(t => t.p.map(p => Math.abs(p[0] - 100)))) * 1.15, dy = Math.max(0.5, ...T.flatMap(t => t.p.map(p => Math.abs(p[1] - 100)))) * 1.15;
      const L = 56, R = Wd - 10, Tp = 10, B = Hh - 42, X = (v: number) => L + ((v - (100 - dx)) / (2 * dx)) * (R - L), Y = (v: number) => B - ((v - (100 - dy)) / (2 * dy)) * (B - Tp), cx = X(100), cy = Y(100);
      let o = `<rect x="${cx}" y="${Tp}" width="${R - cx}" height="${cy - Tp}" fill="${QB.Leading}"/><rect x="${cx}" y="${cy}" width="${R - cx}" height="${B - cy}" fill="${QB.Weakening}"/><rect x="${L}" y="${cy}" width="${cx - L}" height="${B - cy}" fill="${QB.Lagging}"/><rect x="${L}" y="${Tp}" width="${cx - L}" height="${cy - Tp}" fill="${QB.Improving}"/>`
        + `<line x1="${cx}" x2="${cx}" y1="${Tp}" y2="${B}" stroke="var(--chart-base)"/><line x1="${L}" x2="${R}" y1="${cy}" y2="${cy}" stroke="var(--chart-base)"/>`
        + ([['Leading', R - 8, Tp + 16, 'end'], ['Weakening', R - 8, B - 8, 'end'], ['Lagging', L + 8, B - 8, 'start'], ['Improving', L + 8, Tp + 16, 'start']] as [M.Quad, number, number, string][]).map(([t, x, y, an]) => `<text class="qn" x="${x}" y="${y}" text-anchor="${an}" fill="${QT[t]}">${esc(W.quad[t].toUpperCase())}</text>`).join('')
        + (Wd < 420 ? [100 - dx * 0.5, 100, 100 + dx * 0.5] : [100 - dx * 0.66, 100 - dx * 0.33, 100, 100 + dx * 0.33, 100 + dx * 0.66]).map(v => `<text class="ax" x="${X(v)}" y="${B + 16}" text-anchor="middle">${v.toFixed(1)}</text>`).join('')
        + [100 - dy * 0.66, 100, 100 + dy * 0.66].map(v => `<text class="ax" x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${v.toFixed(1)}</text>`).join('')
        + `<text class="ax t" x="${(L + R) / 2}" y="${Hh - 6}" text-anchor="middle">${esc(W.rot.xAxis)} →</text><text class="ax t" transform="translate(13,${(Tp + B) / 2}) rotate(-90)" text-anchor="middle">${esc(W.rot.yAxis)} →</text>`;
      const op = TW > 4 ? 0.3 : 0.6, lk = !!S.pin && !sel.length;
      T.forEach(t => {
        const pk = t.nm === S.pin && !sel.length, q = t.q as M.Quad, col = pk ? 'var(--text)' : QC[q] || 'var(--text-3)', P = t.p.map(p => [X(p[0]), Y(p[1])]);
        o += `<g class="tl${pk ? ' pk' : ''}${sel.includes(t.nm) ? ' on2' : ''}" data-n="${esc(t.nm)}" style="--op:${pk ? 1 : op}"><path d="${smooth(P)}" fill="none" stroke="${col}" stroke-width="${pk ? 2.2 : 1.6}" stroke-linecap="round"/>`
          + t.p.slice(0, -1).map((p, j) => `<circle cx="${P[j][0].toFixed(1)}" cy="${P[j][1].toFixed(1)}" r="${pk ? 2.4 : 2}" fill="${col}" data-tip="${esc(`<b>${esc(D.short(t.nm))}</b> · ${esc(W.rot.weekEnding(dl(p[2])))}<br>${esc(W.quad[Kc.q[t.nm][p[2]] as M.Quad] || '—')}<br>${esc(W.rot.reading(p[0], p[1]))}`)}"/>`).join('') + '</g>';
      });
      const heads = T.map(t => ({ ...t, x: X(LST(t)[0]), y: Y(LST(t)[1]) })), placed: any[] = [], hidden: string[] = [], hit = (p: any, q: any) => p.l < q.r && q.l < p.r && p.t < q.b && q.t < p.b;
      const labs = heads.map(h => {
        const w = textW(D.short(h.nm), '600 11px Inter, sans-serif') + 4, hh = 13;
        for (const [l, t] of [[h.x + 8, h.y - hh / 2], [h.x - 8 - w, h.y - hh / 2], [h.x - w / 2, h.y - 9 - hh], [h.x - w / 2, h.y + 9], [h.x + 7, h.y - 7 - hh], [h.x + 7, h.y + 7], [h.x - 7 - w, h.y - 7 - hh], [h.x - 7 - w, h.y + 7]]) {
          const r = { l, t, r: l + w, b: t + hh };
          if (l < L || r.r > R || t < Tp || r.b > B) continue;
          if (placed.some(p => hit(p, r)) || heads.some(q => hit({ l: q.x - 6, r: q.x + 6, t: q.y - 6, b: q.y + 6 }, r))) continue;
          placed.push(r); return { h, r };
        }
        hidden.push(h.nm); return { h, r: null as any };
      });
      heads.forEach(h => {
        const pk = h.nm === S.pin, q = h.q as M.Quad;
        o += `<g class="pt${pk ? ' pk' : ''}${sel.includes(h.nm) ? ' on2' : ''}" data-n="${esc(h.nm)}" role="button" tabindex="0" aria-label="${esc(h.nm)}" data-tip="${esc(`<b>${esc(h.nm)}</b> · ${esc(W.quad[q] || '—')}<br>${esc(W.rot.reading(LST(h)[0], LST(h)[1]))}<br><span class="muted">${esc(W.rot.clickPin)}</span>`)}">${TOUCH ? `<circle cx="${h.x.toFixed(1)}" cy="${h.y.toFixed(1)}" r="14" fill="transparent"/>` : ''}${pk ? `<circle cx="${h.x.toFixed(1)}" cy="${h.y.toFixed(1)}" r="16" fill="${QC[q]}" fill-opacity=".18"/>` : ''}<circle cx="${h.x.toFixed(1)}" cy="${h.y.toFixed(1)}" r="${pk ? 9 : 5.5}" fill="${QC[q] || 'var(--text-3)'}" stroke="var(--surface)" stroke-width="1.5"/></g>`;
      });
      labs.forEach(({ h, r }) => { if (r) o += `<text data-n="${esc(h.nm)}" class="lb${h.nm === S.pin ? ' b' : ''}${sel.includes(h.nm) ? ' on2' : ''}" x="${(r.l + 2).toFixed(1)}" y="${(r.t + 10).toFixed(1)}">${esc(D.short(h.nm))}</text>` });
      box.innerHTML = `<svg width="${Wd}" height="${Hh}" role="img" aria-label="${esc(W.rot.aria)}">${o}</svg>`;
      box.classList.toggle('lk', lk); box.classList.toggle('sl', sel.length > 0);
      footSet(el, W.rot.foot(hidden.length > 0));
      $$('.pt', box).forEach(g => {
        g.onclick = () => pick(c, g.dataset.n as string);
        g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(c, g.dataset.n as string) } };
        g.onmouseenter = () => { box.classList.add('hv'); $$('.tl', box).forEach(t => t.classList.toggle('on', t.dataset.n === g.dataset.n)) };
        g.onmouseleave = () => { box.classList.remove('hv'); $$('.tl.on', box).forEach(t => t.classList.remove('on')) };
      });
    });
  },
  detail(c): Detail {
    const D = c.D, Kc = calc(D), K = mapDate(c), wk = weekly(D.E), jK = Math.max(0, wk.indexOf(K));
    const rows = D.names.map(nm => {
      const g = Kc.rot[nm], q = Kc.q[nm][K]; let n = 0;
      for (let j = jK; j >= 0 && Kc.q[nm][wk[j]] === q; j--) n++;
      const mv = M.move(g, K, 5);
      return { nm, name: D.short(nm), rs: g.rs[K], mom: g.mom[K], q, qh: rotQ(q), wk: n, dx: mv?.dx ?? null, dy: mv?.dy ?? null, hd: mv ? W.heading(M.heading(mv.deg)) : '—' };
    });
    return {
      title: W.rot.dTitle(M.dateIn(D.dates[K], D.ref)), sub: W.rot.dSub,
      cols: [{ k: 'name', l: W.col.sector }, { k: 'rs', l: W.rot.xAxis, num: true, f: v => v.toFixed(2) }, { k: 'mom', l: W.rot.yAxis, num: true, f: v => v.toFixed(2) }, { k: 'q', l: W.col.quadrant, html: 'qh' },
             { k: 'wk', l: W.col.weeksIn, num: true, f: v => String(v) }, { k: 'dx', l: W.col.dStrength, num: true, tone: true, f: v => M.fnum(v) }, { k: 'dy', l: W.col.dMomentum, num: true, tone: true, f: v => M.fnum(v) }, { k: 'hd', l: W.col.heading }],
      rows, sort: ['rs', 1], onRow: r => pick(c, r.nm), isSel: r => r.nm === c.S.pin,
      read: W.rot.read(D.market), ex: r => W.rot.ex(r.name, r.rs, r.mom, r.q, D.market),
    };
  },
};
/** the timeline's side margins: the sector names on the left, "in phase" on the right; the IHSG strip above the timeline
    puts its weeks on the centres of the timeline's columns with them (visual round 2, V8: the strip aligned to the weeks) */
export const tlPad = (Wd: number, names: string[] = []) => ({ pl: Math.max(Wd < 420 ? 64 : 84, Math.ceil(Math.max(0, ...names.map(n => textW(n, '600 12px Inter, sans-serif')))) + 10), pr: Math.ceil(textW(W.rot.phase, '400 10.5px Inter, sans-serif')) + 12 });
/** the IHSG strip: the weekly closes, the tail period shaded, the map's date marked; a click sets the map's date */
function strip(c: Ctx, box: HTMLElement, K: number, TW: number, tl: boolean) {
  const D = c.D, S = c.S, IH = D.IH;
  requestAnimationFrame(() => {
    const Wd = box.clientWidth, H = box.clientHeight; if (!Wd || !H) return;
    const wk = weekly(D.E), v = wk.map(i => IH[i] as number), known = v.filter(x => x != null), lo = Math.min(...known), hi = Math.max(...known), pd = (hi - lo) * 0.08 || 1, y0 = lo - pd, y1 = hi + pd, n = wk.length;
    const { pl, pr } = tlPad(Wd, D.names.map(n => D.short(n))), cwT = (Wd - pl - pr) / n, L = tl ? pl + cwT / 2 : 44, R = tl ? Wd - pr - cwT / 2 : Wd - 10, T = 4, B = H - 18, X = (j: number) => L + (j / (n - 1)) * (R - L), Y = (x: number) => T + ((y1 - x) / (y1 - y0)) * (B - T), jx = (i: number) => (i - wk[0]) / 5;
    const k = jx(K), k0 = Math.max(0, jx(K - 5 * TW)), chg = M.retAt(IH, K - 5 * TW, K);
    const picks = (Wd < 420 ? [0, Math.round((n - 1) / 2), n - 1] : [0, Math.round((n - 1) / 4), Math.round((n - 1) / 2), Math.round((3 * (n - 1)) / 4), n - 1]).filter((x, i, a) => a.indexOf(x) === i), labs = M.axisDates(wk.map(i => D.dates[i]), picks);
    let o = `<rect x="${X(k0)}" y="${T}" width="${Math.max(0, X(k) - X(k0))}" height="${B - T}" fill="color-mix(in srgb,var(--text) 6%,transparent)"/>`
      + [hi, (hi + lo) / 2, lo].map(x => `<line x1="${L}" x2="${R}" y1="${Y(x)}" y2="${Y(x)}" stroke="var(--chart-grid)"/><text x="${L - 6}" y="${Y(x) + 3.5}" text-anchor="end" class="ax">${Math.round(x).toLocaleString('en-US')}</text>`).join('')
      + `<path d="M${X(0)} ${B}${v.map((x, j) => (x == null ? '' : 'L' + X(j).toFixed(1) + ' ' + Y(x).toFixed(1))).join('')}L${X(n - 1)} ${B}Z" fill="color-mix(in srgb,var(--navy) 6%,transparent)"/><path d="${v.map((x, j) => (x == null ? '' : (j ? 'L' : 'M') + X(j).toFixed(1) + ' ' + Y(x).toFixed(1))).join('')}" fill="none" stroke="var(--text)" stroke-width="1.5" stroke-linejoin="round"/>`
      + `<line x1="${X(k)}" x2="${X(k)}" y1="${T}" y2="${B}" stroke="var(--text)" stroke-width="1.5"/>${IH[K] != null ? `<circle cx="${X(k)}" cy="${Y(IH[K] as number)}" r="3.5" fill="var(--text)"/>` : ''}`
      + `<text x="${X(k) + (k > n * 0.7 ? -6 : 6)}" y="${T + 11}" text-anchor="${k > n * 0.7 ? 'end' : 'start'}" class="dl">${esc(W.rot.stripLabel(M.dateIn(D.dates[K], D.ref), M.level(IH[K], 0), M.pct(chg, 1), tl, Wd < 420))}</text>`
      + picks.map((j, q) => `<text x="${X(j)}" y="${H - 3}" text-anchor="${q === 0 ? 'start' : q === picks.length - 1 ? 'end' : 'middle'}" class="ax">${esc(labs[q])}</text>`).join('')
      + `<line class="hv" y1="${T}" y2="${B}" stroke="var(--text-3)" stroke-dasharray="3 3" display="none"/>`;
    box.innerHTML = `<svg width="${Wd}" height="${H}" role="img" aria-label="${esc(W.rot.stripAria(D.market))}">${o}</svg>`;
    box.dataset.ownTip = '';
    const xh = $('line.hv', box) as unknown as SVGLineElement, at = (e: PointerEvent | MouseEvent) => { const r = box.getBoundingClientRect(); return Math.round(((e.clientX - r.left - L) / (R - L)) * (n - 1)) };
    const mn = minK(c), target = (j: number) => Math.max(mn, wk[j]);     // the hover and the click set the same date
    box.onpointermove = e => {
      const j = at(e); if (j < 0 || j > n - 1) { xHide(xh); tipHide(); return }
      xShow(xh, X(j)); xTag(xh, M.tagDate(D.dates[wk[j]]));
      const i = wk[j], w1 = M.ret(IH, i, 5), to = M.dateLabel(D.dates[target(j)], false, true);
      tipShow(`<span class="d">${esc(W.rot.weekOf(D.market, M.dateLabel(D.dates[i], false, true)))}</span><div class="r"><span>${esc(W.col.close)}</span><b>${M.level(IH[i])}</b></div><div class="r"><span>${esc(W.rot.oneWeek)}</span><b class="${M.cls(w1)}">${M.pct(w1)}</b></div><div class="r"><span class="muted">${esc(i < mn ? W.rot.tooEarly(to) : W.rot.setDate(to))}</span></div>`, e);
    };
    box.onpointerleave = () => { xHide(xh); tipHide() };
    box.onclick = e => { const j = at(e); if (j < 0 || j > n - 1) return; const i = target(j); S.rotK = i >= D.E ? null : D.dates[i]; tipHide(); c.redraw() };
  });
}
/** the timeline (the user's prototype, V8): rows = sectors, columns = the 52 weeks, colour = the quadrant; weeks after the
    map's date faded. Cells are square with a gap and round corners, as wide as the column; a row is never under 16 px, so
    the 12 px names never overlap (check 1 RP-2: in a narrow card the cells are then taller than wide). The dates are under
    the grid and "in phase", each sector's weeks in its current quadrant in that quadrant's colour, closes the rows */
export function tlGeom(Wd: number, H: number, names: string[], n = 52) {
  const rows = names.length;
  const { pl, pr } = tlPad(Wd, names), pt = 2, pb = 22, cw = (Wd - pl - pr) / n, rh = Math.max(16, Math.min(cw, (H - pt - pb) / rows));
  return { pl, pr, pt, pb, cw, rh, gap: cw >= 12 ? 3 : 2 };
}
function timeline(c: Ctx, box: HTMLElement, K: number) {
  const D = c.D, S = c.S, Kc = calc(D), Wd = box.clientWidth, H = box.clientHeight; if (!Wd || !H) return;
  const wk = weekly(D.E), n = wk.length, jK = Math.max(0, wk.indexOf(K)), QO = M.QUADS;
  const run = (nm: string) => { let k = 0; for (let j = jK; j >= 0 && Kc.q[nm][wk[j]] === Kc.q[nm][K]; j--) k++; return k };
  const rows = [...D.names].sort((p, q) => QO.indexOf(Kc.q[p][K] as M.Quad) - QO.indexOf(Kc.q[q][K] as M.Quad) || (Kc.rot[q].rs[K] ?? 0) - (Kc.rot[p].rs[K] ?? 0));
  // a wide timeline (a window) has square cells; a narrow one (a card) fills its 16 px rows, so its cells do not shrink to dots
  const { pl, pt, cw, rh, gap } = tlGeom(Wd, H, rows.map(n => D.short(n)), n), ch = (cw >= 12 ? Math.min(rh, cw) : rh) - gap, sel = S.rotSel;
  let o = '';
  rows.forEach((nm, r) => {
    const y = pt + r * rh, q = Kc.q[nm][K] as M.Quad, k = run(nm), pk = nm === S.pin;
    o += `<text class="tn${pk ? ' b' : ''}${sel.includes(nm) ? ' on2' : ''}" data-n="${esc(nm)}" x="${pl - 8}" y="${y + rh / 2 + 4}" text-anchor="end">${esc(D.short(nm))}</text><g class="tlr${pk ? ' pk' : ''}${sel.includes(nm) ? ' on2' : ''}" data-n="${esc(nm)}">`;
    wk.forEach((i, j) => {
      const qq = Kc.q[nm][i] as M.Quad | null, g = Kc.rot[nm];
      o += `<rect x="${(pl + j * cw + gap / 2).toFixed(1)}" y="${(y + (rh - ch) / 2).toFixed(1)}" width="${Math.max(0, cw - gap).toFixed(1)}" height="${Math.max(0, ch).toFixed(1)}" rx="${cw >= 12 ? 3 : 2}" fill="${qq ? QC[qq] : 'var(--sel)'}"${j > jK ? ' fill-opacity=".35"' : ''} data-tip="${esc(`<b>${esc(D.short(nm))}</b> · ${esc(W.rot.weekEnding(M.dateIn(D.dates[i], D.ref)))}<br>${esc(qq ? W.quad[qq] : '—')}${g.mom[i] != null ? `<br>${esc(W.rot.reading(g.rs[i] as number, g.mom[i] as number))}` : ''}`)}"/>`;
    });
    o += `</g><text class="tw" x="${Wd - 2}" y="${y + rh / 2 + 4}" text-anchor="end" fill="${QT[q] || 'var(--text-3)'}" data-tip="${esc(W.rot.inPhase(D.short(nm), k > jK ? k + '+' : String(k), W.quad[q] || '—', M.dateIn(D.dates[K], D.ref)))}">${k > jK ? k + '+' : k}w</text>`;
  });
  o += `<rect x="${(pl + jK * cw + gap / 4).toFixed(1)}" y="${pt}" width="${(cw - gap / 2).toFixed(1)}" height="${(rows.length * rh).toFixed(1)}" fill="none" stroke="var(--text)" stroke-width="1.5" rx="3" pointer-events="none"/>`;
  const yb = pt + rows.length * rh + 14, picks = Wd < 420 ? [0, Math.round((n - 1) / 2), n - 1] : [0, Math.round((n - 1) / 4), Math.round((n - 1) / 2), Math.round((3 * (n - 1)) / 4), n - 1], labs = M.axisDates(wk.map(i => D.dates[i]), picks);
  // the dates under the grid (the prototype's), the last one ending at the grid's right edge; "in phase" under its column
  picks.forEach((j, q) => (o += `<text class="ax" x="${q === picks.length - 1 ? pl + n * cw : pl + j * cw + (q ? cw / 2 : 0)}" y="${yb}" text-anchor="${q ? (q === picks.length - 1 ? 'end' : 'middle') : 'start'}">${esc(labs[q])}</text>`));
  o += `<text class="ax" x="${Wd - 2}" y="${yb}" text-anchor="end">${esc(W.rot.phase)}</text>`;
  box.innerHTML = `<svg width="${Wd}" height="${Math.min(H, yb + 6)}" role="img" aria-label="${esc(W.rot.tlAria)}">${o}</svg>`;
  box.classList.toggle('lk', !!S.pin && !sel.length); box.classList.toggle('sl', sel.length > 0);
  $$('.tn,.tlr', box).forEach(t => (t.onclick = () => pick(c, t.dataset.n as string)));
}

/* ===================== direction and speed (logic.js L425-438): every tile shown (defect D05) ===================== */
export const rotD: Card = {
  id: 'rotD', tab: 'rot', cls: 'rot-d',
  render(el, c) {
    const D = c.D, S = c.S, Kc = calc(D), K = mapDate(c), NW = S.cmpW, LB = 5 * NW, sel = S.rotSel;
    const v = D.names.map(nm => ({ nm, m: M.move(Kc.rot[nm], K, LB), q: Kc.q[nm][K] as M.Quad })).filter(x => x.m) as { nm: string; m: NonNullable<ReturnType<typeof M.move>>; q: M.Quad }[];
    const mx = Math.max(...v.map(x => x.m.sp)) || 1;
    v.sort((p, q) => (S.cmpS === 'sp' ? q.m.sp - p.m.sp : p.m.deg - q.m.deg));
    const CMPC = (deg: number) => (deg < 90 ? 'var(--up)' : deg < 180 ? 'var(--blue)' : deg < 270 ? 'var(--down)' : 'var(--amber-400)');
    el.innerHTML = H3(W.rotD.title, W.rotD.sub(NW, M.dateIn(D.dates[K], D.ref)), SEG('w', W.rotD.window, [[1, '1W'], [2, '2W'], [4, '4W']], NW) + SEG('s', W.rotD.sort, [['ang', W.rotD.angle], ['sp', W.rotD.speed]], S.cmpS), c.win ? null : 'rotD')
      + `<div class="cmp">${v.map(x => {
        const L2 = 10 + (22 * x.m.sp) / mx, col = CMPC(x.m.deg), a0 = (x.m.deg * Math.PI) / 180, ex = 40 + L2 * Math.cos(a0), ey = 40 - L2 * Math.sin(a0);
        return `<div class="cpi${sel.includes(x.nm) ? ' on2' : ''}" data-n="${esc(x.nm)}" role="button" tabindex="0" aria-pressed="${sel.includes(x.nm)}" data-tip="${esc(`<b>${esc(D.short(x.nm))}</b> · ${esc(W.quad[x.q] || '—')}<br>${esc(W.rotD.tip(x.m.deg.toFixed(0), x.m.sp.toFixed(2), NW))}<br>${esc(W.rotD.deltas(M.ppx(x.m.dx, 2), M.ppx(x.m.dy, 2)))}<br><span class="muted">${esc(W.rotD.click)}</span>`)}"><svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="34" fill="var(--surface-2)" stroke="var(--border)"/><line x1="6" x2="74" y1="40" y2="40" stroke="var(--border)"/><line x1="40" x2="40" y1="6" y2="74" stroke="var(--border)"/><line x1="40" y1="40" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${col}" stroke-width="3" stroke-linecap="round"/><circle cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="4" fill="${col}"/></svg><b title="${esc(x.nm)}">${esc(D.short(x.nm))}</b><span style="color:${QT[x.q] || 'var(--text-3)'}">${x.m.deg.toFixed(0)}°</span></div>`;
      }).join('')}</div><div class="lgd"><span>${esc(W.rotD.foot)}</span>${sel.length ? `<span class="sp"></span><span>${esc(W.rotB.highlighted(sel.length))} · <button class="clr" type="button" data-clear>${esc(W.rotB.clear)}</button></span>` : ''}</div>`;
    onSeg(el, 'w', x => { S.cmpW = +x; c.redraw() });
    onSeg(el, 's', x => { S.cmpS = x; c.redraw() });
    $$('.cpi', el).forEach(t => {
      t.onclick = e => multi(c, t.dataset.n as string, e.ctrlKey || e.metaKey);
      t.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); multi(c, t.dataset.n as string, e.ctrlKey || e.metaKey) } };
    });
    clearButton(el, c);
  },
  detail(c): Detail {
    const D = c.D, Kc = calc(D), K = mapDate(c), NW = c.S.cmpW, LB = 5 * NW;
    const rows = D.names.map(nm => { const m = M.move(Kc.rot[nm], K, LB), q = Kc.q[nm][K]; return { nm, name: D.short(nm), deg: m?.deg ?? null, sp: m?.sp ?? null, dx: m?.dx ?? null, dy: m?.dy ?? null, hd: m ? W.heading(M.heading(m.deg)) : '—', q, qh: rotQ(q) } });
    return {
      title: W.rotD.dTitle, sub: W.rotD.dSub(NW, M.dateIn(D.dates[K], D.ref)),
      cols: [{ k: 'name', l: W.col.sector }, { k: 'deg', l: W.col.direction, num: true, f: v => v.toFixed(0) + '°' }, { k: 'hd', l: W.col.heading }, { k: 'sp', l: W.rotD.speed, num: true, f: v => v.toFixed(2) },
             { k: 'dx', l: W.col.dStrength, num: true, tone: true, f: v => M.fnum(v) }, { k: 'dy', l: W.col.dMomentum, num: true, tone: true, f: v => M.fnum(v) }, { k: 'q', l: W.col.quadrant, html: 'qh' }],
      rows, sort: ['sp', 1], onRow: r => multi(c, r.nm, false), isSel: r => c.S.rotSel.includes(r.nm),
      read: W.rotD.read, ex: r => W.rotD.ex(r.name, r.deg, r.sp, r.hd),
    };
  },
};
function clearButton(el: HTMLElement, c: Ctx) {
  const b = $('[data-clear]', el) as HTMLElement | null;
  if (b) b.onclick = e => { e.stopPropagation(); if (c.S.pin && c.S.rotSel.includes(c.S.pin)) c.S.pin = null; c.S.rotSel = []; c.redraw() };
}

/* ===================== rotation detail (logic.js L487-515; the speed over the chosen window, defect N01) ===================== */
/** the sectors' rows: quadrant now and the chosen sessions before, speed, last change; ordered by the card's sort */
function rbRows(c: Ctx) {
  const D = c.D, S = c.S, Kc = calc(D), E = mapDate(c), pk = S.rotP, mo = D.P('1M'), pl = pk === mo ? '1M' : pk + 'D';
  const QO: Record<string, number> = { Leading: 4, Improving: 3, Weakening: 2, Lagging: 1 };
  const rows = D.names.map(nm => {
    const q = Kc.q[nm]; let li: number | null = null;
    for (let i = E; i > 0; i--) if (q[i] && q[i - 1] && q[i] !== q[i - 1]) { li = i; break }
    const mv = M.move(Kc.rot[nm], E, pk), m3 = M.minus(Kc.rot[nm].mom[E], Kc.rot[nm].mom[E - 3]), pq = q[E - pk] ?? null;
    return { nm, sn: D.short(nm), name: D.short(nm), q: q[E], qo: q[E] ? QO[q[E] as string] : 0, pq, po: pq ? QO[pq] : 0, dm: m3, sp: mv ? mv.sp : null, li, from: li ? q[li - 1] : null };
  });
  const SK = M.msKeep(S.rotS, k => ['sn', 'qo', 'po', 'sp', 'li'].includes(k)), DEF: M.Level = ['dm', 1];
  M.msSort(rows, SK, { sn: 1 }, DEF);
  return { rows, SK, DEF, E, pk, pl, mo };
}
type RbRow = ReturnType<typeof rbRows>['rows'][number];
const prevCell = (r: RbRow) => (r.pq ? `${rotQ(r.pq)}${r.pq !== r.q ? '' : ` <span class="muted" title="${esc(W.rotB.same)}">=</span>`}` : '—');
const lastCell = (c: Ctx, r: RbRow) => (r.li ? `<span class="muted">${esc(W.rotB.from)}</span> ${esc(W.quad[r.from as M.Quad] || '—')} <span class="muted">· ${esc(M.dateIn(c.D.dates[r.li], c.D.ref))}</span>` : '—');
/** the window's sectors (C1, user 2026-11-27): the ones chosen, else the locked sector, else the first of the list, so the
    right side always shows the changes of at least one */
function rbSel(c: Ctx, rows: RbRow[]): string[] {
  const s = c.S.rotSel.filter(n => c.D.names.includes(n));
  if (s.length) return s;
  return [c.S.pin && c.D.names.includes(c.S.pin) ? c.S.pin : rows[0]?.nm].filter(Boolean) as string[];
}
/** a click in the window's list: that sector alone; Ctrl or Cmd: add it, or remove it while another stays */
function c1Pick(c: Ctx, nm: string, add: boolean, cur: string[]) {
  const s = new Set(cur);
  if (!add) { s.clear(); s.add(nm) } else if (!s.has(nm)) s.add(nm); else if (s.size > 1) s.delete(nm);
  c.S.rotSel = c.D.names.filter(n => s.has(n));
  c.S.pin = s.has(nm) ? nm : c.S.rotSel[0] ?? null;
  c.redraw();
}
export const rotB: Card = {
  id: 'rotB', tab: 'rot', cls: 'rot-b', layout: 'c1',
  render(el, c) {
    const D = c.D, S = c.S, { rows, SK, DEF, E, pk, pl, mo } = rbRows(c), sel = S.rotSel;
    const LAB = { sn: W.col.sector, qo: W.rotB.now, po: W.rotB.prev(pl), sp: W.rotD.speed, li: W.rotB.last };
    const th = (k: string, l: string, cl = '', tip = '') => msTh(SK, k, esc(l), cl, tip, { def: DEF, txt: k === 'sn' });
    const prev = SEG('p', W.rotB.previous, [[5, W.rotB.ago('5D')], [10, W.rotB.ago('10D')], [mo, W.rotB.ago('1M')]], pk);
    if (c.win) { rbWindow(el, c, rows, prev); return }
    el.innerHTML = H3(W.rotB.title, W.rotB.sub(pl, pk, E === D.E ? null : M.dateIn(D.dates[E], D.ref)), prev, 'rotB')
      + `<div class="tbl-wrap" data-scroll="y"><table class="tbl padat"><thead><tr>${th('sn', LAB.sn, 'l')}${th('qo', LAB.qo, 'l', W.rotB.qoTip)}${th('po', LAB.po, 'l', W.rotB.poTip(M.dateLabel(D.dates[E - pk], false, true)))}${th('sp', LAB.sp, '', W.rotB.spTip(pk))}${th('li', LAB.li, 'l', W.rotB.liTip)}</tr></thead><tbody>`
      + rows.map(r => `<tr class="${sel.includes(r.nm) ? 'on' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" aria-pressed="${sel.includes(r.nm)}" title="${esc(W.rotB.rowTip)}"><td class="l"><span class="sym">${esc(r.sn)}</span></td><td class="l">${rotQ(r.q)}</td><td class="l">${prevCell(r)}</td><td>${r.sp == null ? '—' : r.sp.toFixed(2)}</td><td class="l">${lastCell(c, r)}</td></tr>`).join('')
      + `</tbody></table></div><div class="lgd">${msNote(SK, LAB, { sn: 1 }, W.rotB.defOrder)}<span>${sel.length ? `${esc(W.rotB.highlighted(sel.length))} · <button class="clr" type="button" data-clear>${esc(W.rotB.clear)}</button> · ` : esc(W.rotB.hint) + ' · '}${esc(W.rotB.speedFoot(pk))}</span></div>`;
    onSeg(el, 'p', v => { S.rotP = +v; c.redraw() });
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
    $$('tbody tr', el).forEach(r => {
      r.onclick = e => multi(c, r.dataset.n as string, e.ctrlKey || e.metaKey);
      r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); multi(c, r.dataset.n as string, e.ctrlKey || e.metaKey) } };
    });
    clearButton(el, c);
  },
  /** C1: "Changes" = the quadrant changes of the chosen sector(s); "All columns" = the card's own table, every column */
  detail(c): Detail {
    const D = c.D, S = c.S, Kc = calc(D), wk = weekly(D.E), { rows: secs, pl, pk } = rbRows(c), sel = rbSel(c, secs);
    const seg = SEG('rv', '', [['ch', W.rotB.changes], ['all', W.rotB.allCols]], S.rbV === 'all' ? 'all' : 'ch');
    const wire = (box: HTMLElement) => onSeg(box, 'rv', v => { S.rbV = v; S.dS = []; c.redraw() });
    if (S.rbV === 'all') return {
      title: W.rotB.allTitle, sub: W.rotB.allSub(pl, pk), ctl: seg, wire,
      cols: [{ k: 'sn', l: W.col.sector, b: true }, { k: 'qo', l: W.rotB.now, html: 'qh' }, { k: 'po', l: W.rotB.prev(pl), html: 'ph' }, { k: 'sp', l: W.rotD.speed, num: true, f: v => v.toFixed(2) }, { k: 'li', l: W.rotB.last, html: 'lh' }],
      rows: secs.map(r => ({ ...r, qh: rotQ(r.q), ph: prevCell(r), lh: lastCell(c, r) })), sort: ['dm', 1],
      onRow: (r, e) => { const add = !!(e && (e.ctrlKey || e.metaKey)); if (!add) S.rbV = 'ch'; c1Pick(c, r.nm, add, sel) }, isSel: r => sel.includes(r.nm),
      read: W.rotB.readAll(pk), ex: r => W.rotB.exAll(r.sn, W.quad[r.q as M.Quad] || '—', r.sp),
    };
    const rows: any[] = [];
    sel.forEach(nm => { for (let j = 1; j < wk.length; j++) { const a = Kc.q[nm][wk[j - 1]], b = Kc.q[nm][wk[j]]; if (a && b && a !== b) rows.push({ nm, name: D.short(nm), i: wk[j], d: M.dateLabel(D.dates[wk[j]], false, true), f: a, fh: rotQ(a), t: b, th: rotQ(b), dir: M.clockwise(a, b) ? W.rotB.cw : W.rotB.skip }) } });
    return {
      title: W.rotB.dTitle, sub: W.rotB.dSubC1(rows.length, wk.length, sel.map(n => D.short(n))), ctl: seg, wire, empty: W.rotB.noChange(wk.length),
      cols: [{ k: 'i', l: W.col.weekEnding, num: true, f: (_v, r) => r.d }, { k: 'name', l: W.col.sector }, { k: 'f', l: W.col.from, html: 'fh' }, { k: 't', l: W.col.to, html: 'th' }, { k: 'dir', l: W.col.path }],
      rows, sort: ['i', 1],
      read: W.rotB.read, ex: r => W.rotB.ex(r.d, r.name, W.quad[r.f as M.Quad], W.quad[r.t as M.Quad], r.dir === W.rotB.cw),
    };
  },
};
/** Rotation detail in a window (C1, user 2026-11-27): the card's control row above both sides; on the left a compact list
    (sector, quadrant now, speed) on the same 52 px band and 36 px rows as the detail on the right; sector chips on a phone */
function rbWindow(el: HTMLElement, c: Ctx, rows: RbRow[], prev: string) {
  const D = c.D, S = c.S, sel = rbSel(c, rows), E = mapDate(c), { pl, pk } = rbRows(c);
  el.innerHTML = H3(W.rotB.title, W.rotB.sub(pl, pk, E === D.E ? null : M.dateIn(D.dates[E], D.ref)), prev
      + `<span class="lgd c1-hint">${esc(W.rotB.hintC1)}${sel.length > 1 ? ` · ${esc(W.rotB.selected(sel.length))} <button class="btn sm" type="button" data-clear>${esc(W.rotB.clear)}</button>` : ''}</span>`, null)
    + `<div class="c1-chips" role="group" aria-label="${esc(W.rotB.sectors)}">${rows.map(r => `<button type="button" class="c1-chip${sel.includes(r.nm) ? ' on' : ''}" data-n="${esc(r.nm)}" aria-pressed="${sel.includes(r.nm)}">${esc(r.sn)}</button>`).join('')}</div>`
    + `<div class="c1-l"><div class="c1-band"><b>${esc(W.rotB.sectors)}</b><span>${rows.length}</span></div><div class="tbl-wrap c1-list" data-scroll="y"><table class="tbl padat"><thead><tr><th class="l">${esc(W.col.sector)}</th><th class="l">${esc(W.rotB.nowShort)}</th><th>${esc(W.rotD.speed)}</th></tr></thead><tbody>`
    + rows.map(r => `<tr class="${sel.includes(r.nm) ? 'on' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" aria-pressed="${sel.includes(r.nm)}" title="${esc(W.rotB.rowTipWin)}"><td class="l"><span class="sym">${esc(r.sn)}</span></td><td class="l">${rotQ(r.q)}</td><td>${r.sp == null ? '—' : r.sp.toFixed(2)}</td></tr>`).join('')
    + `</tbody></table></div></div>`;
  onSeg(el, 'p', v => { S.rotP = +v; c.redraw() });
  $$('.c1-list tbody tr, .c1-chip', el).forEach(r => {
    r.onclick = e => c1Pick(c, r.dataset.n as string, e.ctrlKey || e.metaKey, sel);
    r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r && r.tagName === 'TR') { e.preventDefault(); c1Pick(c, r.dataset.n as string, e.ctrlKey || e.metaKey, sel) } };
  });
  const b = $('[data-clear]', el) as HTMLElement | null;
  if (b) b.onclick = e => { e.stopPropagation(); c.S.rotSel = [sel[0]]; c.S.pin = sel[0]; c.redraw() };
}

/* ===================== the stock momentum quadrant of one sector (logic.js L520-551) ===================== */
function quadStocks(c: Ctx) {
  const D = c.D, nm = shown(c), bm = c.S.rotBm, mo = D.P('1M'), w = D.P('1W');
  const bench = bm === 'ih' ? D.IH : D.sec(nm), b1 = M.ret(bench, D.E, mo), b5 = M.ret(bench, D.E, w), bn = bm === 'ih' ? D.market : W.rotC.index(D.short(nm));
  const st = D.members(nm).filter(x => x.r1m != null && x.r5d != null && b1 != null && b5 != null).map(x => {
    const a = (x.r1m as number) - (b1 as number), b = (x.r5d as number) - (b5 as number);
    return { ...x, x: a, y: b, q: (a >= 0 ? (b >= 0 ? 'Leading' : 'Weakening') : b >= 0 ? 'Improving' : 'Lagging') as M.Quad };
  });
  return { nm, st, bn };
}
export const rotC: Card = {
  id: 'rotC', tab: 'rot', cls: 'rot-c',
  render(el, c) {
    const D = c.D, S = c.S, { nm, st, bn } = quadStocks(c);
    el.innerHTML = H3(W.rotC.title(D.short(nm)), W.rotC.sub(bn, mapDate(c) === D.E ? null : M.dateIn(D.dates[D.E], D.ref)), SEG('b', W.rotC.rel, [['ih', D.market], ['sec', W.rotC.secIndex]], S.rotBm), c.win ? null : 'rotC')
      // user 2026-11-27 (V9): the two legend lines under the chart are gone; the counts are in the window's table, the dot's
      // size and colour in the subtitle and each dot's hint
      + `<div class="tb"><div class="qdp" data-chart></div></div>`;
    onSeg(el, 'b', v => { S.rotBm = v; c.redraw() });
    const box = $('[data-chart]', el);
    requestAnimationFrame(() => {
      const Wd = box.clientWidth, H = box.clientHeight;
      if (!Wd || !H) return;
      if (!st.length) { box.innerHTML = `<div class="cv-empty">${esc(W.rotC.none(D.short(nm)))}</div>`; return }
      const [xl, xh] = M.axisRange(st.map(s => s.x)), [yl, yh] = M.axisRange(st.map(s => s.y));
      const px = (xh - xl) * 0.04, py = (yh - yl) * 0.05, x0 = xl - px, x1 = xh + px, y0 = yl - py, y1 = yh + py;
      const L = 60, R = Wd - 12, T = 8, B = H - 52, cl = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
      const X = (v: number) => L + ((cl(v, x0, x1) - x0) / (x1 - x0)) * (R - L), Y = (v: number) => B - ((cl(v, y0, y1) - y0) / (y1 - y0)) * (B - T), cx = X(0), cy = Y(0);
      const QN = ([['Leading', R - 4, T + 12, 'end'], ['Weakening', R - 4, B - 6, 'end'], ['Lagging', L + 4, B - 6, 'start'], ['Improving', L + 4, T + 12, 'start']] as [M.Quad, number, number, string][]).map(([t, x, y, an]) => {
        const w = textW(W.quad[t].toUpperCase(), '600 10.5px Inter, sans-serif') * 1.08, l = an === 'end' ? x - w : x;
        return { t, x, y, an, box: { l: l - 2, t: y - 11, r: l + w + 2, b: y + 3 } };
      });
      let o = `<line x1="${cx}" x2="${cx}" y1="${T}" y2="${B}" stroke="var(--chart-base)"/><line x1="${L}" x2="${R}" y1="${cy}" y2="${cy}" stroke="var(--chart-base)"/>`
        + M.ticks(x0, x1, Wd < 420 ? 3 : 6).filter(v => X(v) > L + 14 && X(v) < R - 18).map(v => `<line x1="${X(v)}" x2="${X(v)}" y1="${B}" y2="${B + 4}" stroke="var(--border-2)"/><text class="ax" x="${X(v)}" y="${B + 18}" text-anchor="middle">${M.axPct(v)}</text>`).join('') + `<line x1="${L}" x2="${R}" y1="${B}" y2="${B}" stroke="var(--border)"/>`
        + M.ticks(y0, y1, 4).map(v => `<text class="ax" x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${M.axPct(v)}</text>`).join('')
        + `<text class="ax t" x="${(L + R) / 2}" y="${B + 36}" text-anchor="middle">${esc(W.rotC.xAxis(bn))} →</text><text class="ax t" transform="translate(13,${(T + B) / 2}) rotate(-90)" text-anchor="middle">${esc(W.rotC.yAxis(bn))} →</text>`;
      const gw = Math.max(...st.map(s => s.w ?? 0)) || 1, rr = (s: typeof st[0]) => 2.5 + 7 * Math.sqrt(Math.max(0, s.w ?? 0) / gw);
      const out = (s: typeof st[0]) => s.x < x0 || s.x > x1 || s.y < y0 || s.y > y1;
      [...st].sort((p, q) => (q.w ?? 0) - (p.w ?? 0)).forEach(s => {
        const ob = out(s);
        const tip = `<b>${esc(s.t)}</b> · ${esc(W.quad[s.q])}<br>${esc(s.n || '')}<br>1M ${M.pct(s.r1m)} · ${esc(W.vs(bn))} ${M.pp(s.x)}<br>5D ${M.pct(s.r5d)} · ${esc(W.vs(bn))} ${M.pp(s.y)}<br>${esc(W.cap(D.weightLabel))} ${esc(M.weightText(D.weightBasis, s.w))}${ob ? `<br><span class="muted">${esc(W.rotC.beyond)}</span>` : ''}`;
        // a dot beyond the axis range is drawn hollow at the edge (defect: outliers clamped without a marker)
        o += `<circle cx="${X(s.x).toFixed(1)}" cy="${Y(s.y).toFixed(1)}" r="${rr(s).toFixed(1)}" class="dt${s.t === S.rqT ? ' on' : ''}" data-t="${esc(s.t)}" role="button" tabindex="0" aria-label="${esc(s.t)}" ${ob ? `fill="var(--surface)" stroke="${s.y >= 0 ? 'var(--up)' : 'var(--down)'}" stroke-width="1.6"` : `fill="${s.y >= 0 ? 'var(--up)' : 'var(--down)'}" fill-opacity=".88" stroke="var(--surface)" stroke-width="1"`} data-tip="${esc(tip)}"/>`;
      });
      // the quadrant names are drawn over the dots with a halo, and the stock names keep clear of them
      o += QN.map(q => `<text class="qn" x="${q.x}" y="${q.y}" text-anchor="${q.an}">${esc(W.quad[q.t].toUpperCase())}</text>`).join('');
      const boxes: any[] = QN.map(q => q.box);
      [...st].sort((p, q) => (q.w ?? 0) - (p.w ?? 0)).slice(0, 8).filter(s => s.t !== S.rqT).forEach(s => {
        const x = X(s.x), y = Y(s.y), r = rr(s), w = textW(s.t, '600 11px Inter, sans-serif') + 4, h = 13;
        for (const [dx, dy] of [[r + 3, -h / 2], [-r - 3 - w, -h / 2], [-w / 2, -r - 2 - h], [-w / 2, r + 2], [r + 2, -r - h], [r + 2, r], [-r - 2 - w, -r - h], [-r - 2 - w, r]]) {
          const b = { l: x + dx, t: y + dy, r: x + dx + w, b: y + dy + h };
          if (b.l < L || b.r > R || b.t < T || b.b > B || boxes.some(o2 => b.l < o2.r && o2.l < b.r && b.t < o2.b && o2.t < b.b)) continue;
          boxes.push(b); o += `<text class="lb" x="${(b.l + 2).toFixed(1)}" y="${(b.t + 10).toFixed(1)}">${esc(s.t)}</text>`; return;
        }
      });
      const hs = S.rqT ? st.find(s => s.t === S.rqT) : null;
      if (hs) {
        const x = X(hs.x), y = Y(hs.y), r = rr(hs) + 3, col = hs.y >= 0 ? 'var(--up)' : 'var(--down)', lw = textW(hs.t, '700 12px Inter, sans-serif'), lft = x + r + 10 + lw > R;
        o += `<circle cx="${x}" cy="${y}" r="${r + 7}" fill="${col}" fill-opacity=".18" pointer-events="none"/><circle class="dt sel" data-t="${esc(hs.t)}" cx="${x}" cy="${y}" r="${r}" fill="${col}" stroke="var(--surface)" stroke-width="1.2"/><text class="lb b" pointer-events="none" text-anchor="${lft ? 'end' : 'start'}" x="${lft ? x - r - 10 : x + r + 10}" y="${y + 4}">${esc(hs.t)}</text>`;
      }
      box.innerHTML = `<svg width="${Wd}" height="${H}" role="img" aria-label="${esc(W.rotC.aria(D.short(nm)))}">${o}</svg>`;
      const choose = (t: string) => {
        S.rqT = S.rqT === t ? null : t; c.redraw();
      };
      $$('circle.dt', box).forEach(d => {
        d.onclick = (e: MouseEvent) => { e.stopPropagation(); choose(d.dataset.t as string) };
        d.onkeydown = (e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(d.dataset.t as string) } };
      });
      // the chosen stock: its figures and "Open in Terminal" (decision G: a dot opens that stock)
      if (hs) {
        const p = stockPop(box, X(hs.x), Y(hs.y), `<div class="ph"><b>${esc(hs.t)}</b><span class="muted">${esc(W.quad[hs.q])}</span></div><div class="kv"><span>1M ${esc(W.vs(bn))}</span><b class="${M.cls(hs.x)}">${M.pp(hs.x)}</b></div><div class="kv"><span>5D ${esc(W.vs(bn))}</span><b class="${M.cls(hs.y)}">${M.pp(hs.y)}</b></div><div class="btns"><button type="button" class="btn sm" data-close>${esc(W.close)}</button><button type="button" class="btn sm primary" data-term>${esc(W.term.open)}</button></div>`, { onClose: () => { S.rqT = null; c.redraw() } });
        ($('[data-term]', p) as HTMLElement).onclick = e => { e.stopPropagation(); c.terminal(hs.t) };
        ($('[data-close]', p) as HTMLElement).onclick = e => { e.stopPropagation(); S.rqT = null; c.redraw() };
      }
    });
  },
  detail(c): Detail {
    const D = c.D, { nm, st, bn } = quadStocks(c);
    const rows = st.map(x => ({ ...x, name: x.t, a: x.x, b: x.y, qh: rotQ(x.q) }));
    return {
      title: W.rotC.dTitle(D.short(nm)), sub: W.vs(bn), ctl: SEL_SECTOR(c, nm), onSel: v => { c.S.rqT = null; c.lock(v, false) }, search: W.search.stock,
      cols: [{ k: 'name', l: W.col.ticker, b: true, term: true }, { k: 'ind', l: W.col.industry }, { k: 'a', l: `1M ${W.vs(bn)}`, num: true, tone: true, f: v => M.pp(v) }, { k: 'b', l: `5D ${W.vs(bn)}`, num: true, tone: true, f: v => M.pp(v) },
             { k: 'q', l: W.col.quadrant, html: 'qh' }, { k: 'w', l: W.col.weight, num: true, f: v => M.weightText(D.weightBasis, v), tip: D.weightLabel }],
      rows, sort: ['a', 1], onRow: r => { c.S.rqT = c.S.rqT === r.t ? null : r.t; c.redraw() }, isSel: r => r.t === c.S.rqT,
      read: W.rotC.read, ex: r => W.rotC.ex(r.name, r.a, r.b, W.quad[r.q as M.Quad]),
    };
  },
};
