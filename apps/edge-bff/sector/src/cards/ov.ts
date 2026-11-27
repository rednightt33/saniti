/* EXEC-SECTOR-ANALYSIS S4, the Overview tab (final/click_inventory.md section 5; formulas.md section 2): Cumulative Return,
   Momentum, Sector x Horizon and the market map of one sector. */
import * as M from '../model.ts';
import { calc, shown, type Card, type Ctx, type Detail } from '../ctx.ts';
import { cumChart, cumHover, type Geo, type Line } from '../charts.ts';
import { $, $$, DOT, H3, SEG, STEPS, esc, footNow, footSet, heat, msNote, msTh, msWire, na, onSeg, openRange, stockPop, textW } from '../ui.ts';
import { W } from '../words.ts';

const PAL = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--c6)'];
const HZ = ['1D', '1W', '1M', '3M', '6M', 'YTD', '1Y'];
const AXES = ['1W', '1M', '3M', 'YTD'];
export const periodOpts = (keys: string[]): [string, string][] => keys.map(k => [k, k === 'C' ? W.range.custom : k]);
/** opens the Custom popover of a card's period and stores the range in its state keys. The popover refuses a date
    outside the data (as the Overview's) and prints the range the way the card will print it (check 1 RP-1, OR-6, BD-7):
    a return card from the base close, a level card (`level`, the breadth line) from its first session. */
export function customRange(c: Ctx, btn: HTMLElement, cur: M.Range | null, set: (r: M.Range) => void, o: M.RangeOpts & { note?: string; dflt?: number } = {}) {
  const D = c.D, s = calc(D).span('3M', null), lo = o.level ? Math.max(0, o.first ?? 0) : Math.max(1, (o.first ?? 0) + 1);
  openRange(btn, {
    title: W.range.title, min: D.dates[lo], max: D.dates[D.E], note: o.note ?? (o.level ? undefined : W.range.returnNote),
    cur: cur || { a: D.dates[Math.max(lo, D.E - (o.dflt ?? (s.e - s.b)) + 1)], b: D.dates[D.E] },
    check: (a, b) => M.checkRange(D.dates, D.E, a, b, o),
    noteOf: o.level || o.label || o.note ? undefined : r => (r.ok && r.span ? W.range.fromClose(M.dateIn(D.dates[r.span.base], D.ref), M.dateIn(D.dates[r.span.first], D.ref)) : W.range.returnNote),
    apply: r => { set(r); c.redraw() },
  });
}
/** the warning a card shows when its stored Custom range was clamped or could not be shown (check 1 RP-1) */
export const rangeNote = (note: string | null) => (note ? `<span class="warnx">${esc(note)}</span>` : '');
/** a line colour per sector: the six chart colours, then the same colours dashed (check 1 OR-10: 11 sectors, 6 colours) */
export const lineStyle = (k: number) => ({ c: PAL[k % PAL.length], dash: k >= PAL.length });
/** the legend's sector rows of a detail: IHSG first when given */
const secRows = (c: Ctx, fn: (nm: string) => any, ih?: () => any) => [...(ih ? [{ nm: c.D.market, name: c.D.market, ...ih() }] : []), ...c.D.names.map(nm => ({ nm, name: c.D.short(nm), ...fn(nm) }))];

/* ===================== Cumulative Return (logic.js L979-1080) ===================== */
function rcSel(c: Ctx): string[] {
  if (c.S.rcSel) return c.S.rcSel.filter(n => c.D.names.includes(n));
  const K = calc(c.D), s = c.D.names.filter(n => K.retP(c.D.sec(n), c.S.rcW, c.S.rcR) != null)
    .sort((a, b) => (K.retP(c.D.sec(b), c.S.rcW, c.S.rcR) as number) - (K.retP(c.D.sec(a), c.S.rcW, c.S.rcR) as number));
  return [...new Set([s[0], s[1], s[s.length - 2], s[s.length - 1]].filter(Boolean))];
}
export const rcCard: Card = {
  id: 'rcCard', tab: 'ov', cls: 'ov-wide', fit: ['.ovx-cr', '.ovx-bl'],
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D), sp = K.span(S.rcW, S.rcR), sel = rcSel(c), dates = D.dates.slice(sp.b, sp.e + 1);
    const col: Record<string, string> = {}, dashed = new Set<string>(); let ci = 0;
    D.names.forEach(n => { if (sel.includes(n)) { const st = lineStyle(ci++); col[n] = st.c; if (st.dash) dashed.add(n) } });
    const rows = D.names.map(n => ({ n, v: M.retAt(D.sec(n), sp.b, sp.e) })).filter(r => r.v != null).sort((p, q) => (q.v as number) - (p.v as number));
    const mx = Math.max(...rows.map(r => Math.abs(r.v as number))) || 1;
    el.innerHTML = H3(W.rc.title, W.rc.sub, SEG('w', '', periodOpts(['1M', '3M', 'YTD', 'C']), sp.key), c.win ? null : 'rcCard')
      + `<div class="ovx-b"><div class="ovx-lg">${D.names.map(n => `<button type="button" class="ovx-tog${sel.includes(n) ? ' on' : ''}${dashed.has(n) ? ' dsh' : ''}" data-tg="${esc(n)}" aria-pressed="${sel.includes(n)}"${col[n] ? ` style="--c:${col[n]}"` : ''} title="${esc(W.rc.togTip(sel.includes(n)))}"><i></i>${esc(D.short(n))}</button>`).join('')}`
      + `<button type="button" class="ovx-tog ihx${S.rcIh ? ' on' : ''}" data-tg="__ih" aria-pressed="${S.rcIh}" title="${esc(W.rc.ihTip(S.rcIh, D.market))}"><i></i>${esc(D.market)}</button></div>`
      + `<div class="ovx-cr" style="--n:${rows.length}"><div class="ovx-cv" data-chart></div><div class="ovx-bl">${rows.map(r => `<div class="r${r.n === S.pin ? ' on' : ''}" data-n="${esc(r.n)}" role="button" tabindex="0" aria-pressed="${r.n === S.pin}"><span title="${esc(r.n)}">${esc(D.short(r.n))}</span><div class="tr"><i style="${(r.v as number) >= 0 ? 'left:50%' : 'right:50%'};width:${(Math.abs(r.v as number) / mx) * 50}%;background:${(r.v as number) >= 0 ? 'var(--up)' : 'var(--down)'}"></i></div><b class="${M.cls(r.v, 1)}">${M.pct(r.v, 1)}</b></div>`).join('')}</div></div></div>`
      + `<div class="lgd"><span>${esc(M.rangeLabel(dates[0], dates[dates.length - 1], D.ref))}${DOT}${esc(W.sessions(sp.e - sp.b))}${DOT}${esc(W.rc.sectors(D.names.length))}</span>${rangeNote(sp.note)}<span class="sp"></span><span>${esc(dashed.size ? W.rc.many : W.rc.hint)}</span></div>`;
    onSeg(el, 'w', (v, b) => {
      if (v === 'C') { customRange(c, b, S.rcR, r => { S.rcW = 'C'; S.rcR = r; S.rcSel = null }); return }
      S.rcW = v; S.rcSel = null; c.redraw();
    });
    $$('[data-tg]', el).forEach(b => (b.onclick = () => {
      const n = b.dataset.tg as string;
      if (n === '__ih') S.rcIh = !S.rcIh;
      else { const s = new Set(sel); s.has(n) ? s.delete(n) : s.add(n); S.rcSel = D.names.filter(x => s.has(x)) }
      c.redraw();
    }));
    const box = $('[data-chart]', el);
    let hover: string | null = null, geo: Geo | null = null, lines: Line[] = [];
    const draw = () => {
      const hl = hover || (S.pin && D.names.includes(S.pin) ? S.pin : null);
      lines = D.names.map(n => ({ n, label: D.short(n), a: M.path(D.sec(n), sp.b, sp.e), c: hl ? (n === hl ? col[n] || 'var(--text)' : undefined) : col[n], on: hl ? n === hl : sel.includes(n), strong: n === hl, dot: dashed.has(n) }));
      lines.push({ n: '__ih', label: D.market, a: M.path(D.IH, sp.b, sp.e), c: 'var(--text)', on: S.rcIh, dash: true });
      geo = cumChart(box, lines, dates);
      $$('.ovx-bl .r', el).forEach(r => r.classList.toggle('on', r.dataset.n === hl));
    };
    cumHover(box, {
      geo: () => geo, lines: () => lines, dates: () => dates, candidates: () => lines.filter(x => x.n !== '__ih'),
      pick: n => { if (n !== hover) { hover = n; draw() } },
      tip: (n, i, v) => `<span class="d">${esc(M.dateLabel(dates[i], true, dates[0].slice(0, 4) !== dates[dates.length - 1].slice(0, 4) || dates[i].slice(0, 4) !== D.ref.slice(0, 4)))}</span><div class="r"><i style="background:${col[n] || 'var(--text)'}"></i><span>${esc(D.short(n))}</span><b class="${M.cls(v)}">${M.pct(v)}</b></div><div class="r"><i style="background:var(--text)"></i><span>${esc(D.market)}</span><b class="${M.cls(M.retAt(D.IH, sp.b, sp.b + i))}">${M.pct(M.retAt(D.IH, sp.b, sp.b + i))}</b></div>`,
    });
    $$('.ovx-bl .r', el).forEach(r => {
      r.onmouseenter = () => { hover = r.dataset.n as string; draw() };
      r.onmouseleave = () => { hover = null; draw() };
      r.onclick = () => c.lock(r.dataset.n as string);
      r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); c.lock(r.dataset.n as string) } };
    });
    requestAnimationFrame(draw);
  },
  detail(c): Detail {
    const D = c.D, sp = calc(D).span(c.S.rcW, c.S.rcR), b0 = sp.b, e1 = sp.e, ihr = M.retAt(D.IH, b0, e1);
    const one = (a: M.N[]) => {
      let up = 0, n = 0, bd = -Infinity, wd = Infinity;
      for (let i = b0 + 1; i <= e1; i++) { const r = M.retAt(a, i - 1, i); if (r == null) continue; n++; if (r > 0) up++; bd = Math.max(bd, r); wd = Math.min(wd, r) }
      return { r: M.retAt(a, b0, e1), dd: M.maxDrawdown(a, b0, e1), bd: n ? bd : null, wd: n ? wd : null, up: n ? (up / n) * 100 : null };
    };
    return {
      title: W.rc.dTitle, sub: `${M.rangeLabel(D.dates[b0], D.dates[e1], D.ref)}${DOT}${W.sessions(e1 - b0)}`,
      cols: [{ k: 'name', l: W.col.sector }, { k: 'r', l: W.col.ret, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'x', l: W.col.vs(D.market), num: true, tone: true, f: v => M.pp(v) },
             { k: 'dd', l: W.col.maxdd, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'bd', l: W.col.best, num: true, tone: true, f: v => M.pct(v, 1) },
             { k: 'wd', l: W.col.worst, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'up', l: W.col.updays, num: true, f: v => v.toFixed(0) + '%' }],
      rows: secRows(c, nm => { const o = one(D.sec(nm)); return { ...o, x: M.minus(o.r, ihr) } }, () => ({ ...one(D.IH), x: null })),
      sort: ['r', 1], onRow: r => { if (r.nm !== D.market) c.lock(r.nm) }, isSel: r => r.nm === c.S.pin,
      read: W.rc.read(D.market), ex: r => W.rc.ex(r.name, r.r, r.x, r.dd, D.market),
    };
  },
};

/* ===================== Momentum: horizon vs horizon (logic.js L1081-1105) ===================== */
export const mmCard: Card = {
  id: 'mmCard', tab: 'ov', cls: 'ov-narrow', fit: ['.ovx-cv'],
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D);
    const opts = (v: string, other: string) => `${AXES.map(h => `<option value="${h}"${h === v ? ' selected' : ''}${h === other ? ` disabled` : ''}>${h}</option>`).join('')}`;
    el.innerHTML = H3(W.mm.title, W.mm.sub, `<span class="sgrp"><span class="sxw"><select class="sx-sel" data-sel="x" aria-label="${esc(W.mm.xAxis)}">${opts(S.mmX, S.mmY)}</select></span><span class="plab">${esc(W.mm.vs)}</span><span class="sxw"><select class="sx-sel" data-sel="y" aria-label="${esc(W.mm.yAxis)}">${opts(S.mmY, S.mmX)}</select></span></span>`, c.win ? null : 'mmCard')
      + `<div class="ovx-b"><div class="ovx-cv mm" data-chart></div></div><div class="lgd"><span data-foot>${footNow(el, W.mm.foot(mmReading(c, S.mmX, S.mmY).corner, false))}</span></div>`;
    ($('[data-sel=x]', el) as HTMLSelectElement).onchange = e => { S.mmX = (e.target as HTMLSelectElement).value; c.redraw() };
    ($('[data-sel=y]', el) as HTMLSelectElement).onchange = e => { S.mmY = (e.target as HTMLSelectElement).value; c.redraw() };
    const box = $('[data-chart]', el), rd = mmReading(c, S.mmX, S.mmY);
    requestAnimationFrame(() => {
      const Wd = box.clientWidth, H = box.clientHeight; if (!Wd || !H) return;
      const xl = W.mm.axis(S.mmX), yl = W.mm.axis(S.mmY);
      const pts = D.names.map(n => ({ n: D.short(n), f: n, x: K.retP(D.sec(n), S.mmX, null), y: K.retP(D.sec(n), S.mmY, null) })).filter(p => p.x != null && p.y != null) as { n: string; f: string; x: number; y: number }[];
      const L = 60, T = 10, B = 48, R = Wd - 8, rng = (a: number[]) => { const lo = Math.min(0, ...a), hi = Math.max(0, ...a), p = (hi - lo) * 0.12 || 1; return [lo - p, hi + p] };
      const [x0, x1] = rng(pts.map(p => p.x)), [y0, y1] = rng(pts.map(p => p.y));
      const X = (v: number) => L + ((v - x0) / (x1 - x0)) * (R - L), Y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
      let o = M.ticks(y0, y1, 5).map(t => `<line x1="${L}" x2="${R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${Math.abs(t) < 1e-9 ? 'var(--chart-base)' : 'var(--chart-grid)'}"/><text x="${L - 6}" y="${Y(t) + 3.5}" text-anchor="end" class="ax">${M.axPct(t)}</text>`).join('');
      o += M.ticks(x0, x1, Wd < 360 ? 3 : 5).map(t => `<line x1="${X(t)}" x2="${X(t)}" y1="${T}" y2="${H - B}" stroke="${Math.abs(t) < 1e-9 ? 'var(--chart-base)' : 'var(--chart-grid)'}"/><text x="${X(t)}" y="${H - B + 14}" text-anchor="middle" class="ax">${M.axPct(t)}</text>`).join('');
      o += `<text x="${(L + R) / 2}" y="${H - 6}" text-anchor="middle" class="ax t">${esc(xl)} →</text><text transform="translate(13,${(T + H - B) / 2}) rotate(-90)" text-anchor="middle" class="ax t">${esc(yl)} →</text>`;
      const qf = '600 10px Inter, sans-serif', boxes: number[][] = [], dots = pts.map(p => [X(p.x) - 6, Y(p.y) - 6, X(p.x) + 6, Y(p.y) + 6]);
      const hit = (b: number[], z: number[]) => b[0] < z[2] && z[0] < b[2] && b[1] < z[3] && z[1] < b[3];
      // a quadrant's name sits in its corner of the plot, drawn only where its own quadrant reaches that corner and no dot
      // is under it (defect D07: the zero line ran through the names; a quadrant without room had its name dropped elsewhere)
      const cx = X(0), cy = Y(0);
      const quad = (t: string, x: number, y: number, an: string, ok: boolean) => {
        const w = textW(t.toUpperCase(), qf) * 1.08, l = an === 'end' ? x - w : x, b = [l, y - 10, l + w, y + 2];
        if (!ok || dots.some(d => hit(b, d)) || b[0] < L || b[2] > R) return; boxes.push(b);
        o += `<text x="${x}" y="${y}" text-anchor="${an}" class="qd">${esc(t)}</text>`;
      };
      quad(W.mm.q.both, R - 4, T + 12, 'end', cx < R - 60 && cy > T + 14);
      quad(rd.name(-1, 1), L + 6, T + 12, 'start', cx > L + 60 && cy > T + 14);
      quad(W.mm.q.down, L + 6, H - B - 6, 'start', cx > L + 60 && cy < H - B - 14);
      quad(rd.name(1, -1), R - 4, H - B - 6, 'end', cx < R - 60 && cy < H - B - 14);
      boxes.push(...dots);
      let hid = 0;
      pts.sort((p, q) => Y(p.y) - Y(q.y)).forEach(p => {
        const x = X(p.x), y = Y(p.y), col = p.x >= 0 && p.y >= 0 ? 'var(--green)' : p.x < 0 && p.y < 0 ? 'var(--red)' : 'var(--amber)', w = textW(p.n, '600 10.5px Inter, sans-serif');
        let pick: (string | number)[] | null = null;
        for (const k of [[x + 8, y + 3.5, 'start'], [x - 8, y + 3.5, 'end'], [x, y - 9, 'middle'], [x, y + 16, 'middle'], [x + 8, y - 7, 'start'], [x - 8, y - 7, 'end'], [x + 8, y + 13, 'start'], [x - 8, y + 13, 'end']] as [number, number, string][]) {
          const bx = k[2] === 'start' ? k[0] : k[2] === 'end' ? k[0] - w : k[0] - w / 2, b = [bx, k[1] - 10, bx + w, k[1] + 2];
          if (bx >= L && bx + w <= R && b[1] >= T && b[3] <= H - B && !boxes.some(z => hit(b, z))) { pick = k; boxes.push(b); break }
        }
        if (!pick) hid++;
        const pk = p.f === S.pin;
        o += `<g class="ovx-dot${pk ? ' pk' : ''}" role="button" tabindex="0" aria-label="${esc(p.n)}" aria-pressed="${pk}" data-n="${esc(p.f)}" data-tip="${esc(`<b>${esc(p.f)}</b><br>${esc(xl)} ${M.pct(p.x, 1)}<br>${esc(yl)} ${M.pct(p.y, 1)}`)}"><circle class="hal" cx="${x}" cy="${y}" r="14" fill="${col}" fill-opacity=".18"/><circle class="dot" cx="${x}" cy="${y}" r="${pk ? 8 : 5}" fill="${col}" fill-opacity=".85" stroke="var(--surface)" stroke-width="1.5"/>${pick ? `<text x="${pick[0]}" y="${pick[1]}" text-anchor="${pick[2]}" class="dl${pk ? ' b' : ''}" style="fill:var(--text)">${esc(p.n)}</text>` : ''}</g>`;
      });
      box.innerHTML = `<svg width="${Wd}" height="${H}">${o}</svg>`;
      box.classList.toggle('pk', !!S.pin);
      footSet(el, W.mm.foot(rd.corner, hid > 0));
      $$('.ovx-dot', box).forEach(g => {
        g.onclick = () => c.lock(g.dataset.n as string);
        g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); c.lock(g.dataset.n as string) } };
        g.onmouseenter = () => box.classList.add('hv'); g.onmouseleave = () => box.classList.remove('hv');
      });
    });
  },
  detail(c): Detail {
    const D = c.D, K = calc(D), X = c.S.mmX, Y = c.S.mmY, rx = (a: M.N[]) => K.retP(a, X, null), ry = (a: M.N[]) => K.retP(a, Y, null), rd = mmReading(c, X, Y);
    const reading = (x: M.N, y: M.N) => rd.name(x, y);
    const rows = secRows(c, nm => { const x = rx(D.sec(nm)), y = ry(D.sec(nm)); return { x, y, d: M.minus(y, x), q: reading(x, y) } }, () => { const x = rx(D.IH), y = ry(D.IH); return { x, y, d: M.minus(y, x), q: '' } });
    const rk = (k: string) => { const o = rows.filter(r => r.nm !== D.market && r[k] != null).sort((p, q) => q[k] - p[k]); o.forEach((r, i) => (r['r' + k] = i + 1)) };
    rk('x'); rk('y');
    return {
      title: W.mm.dTitle(X, Y), sub: W.mm.dSub(X, Y),
      cols: [{ k: 'name', l: W.col.sector }, { k: 'x', l: X, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'y', l: Y, num: true, tone: true, f: v => M.pct(v, 1) },
             { k: 'd', l: `${Y} − ${X}`, num: true, tone: true, f: v => M.pp(v) }, { k: 'q', l: W.col.reading }, { k: 'rx', l: W.col.rank(X), num: true, f: v => String(v) }, { k: 'ry', l: W.col.rank(Y), num: true, f: v => String(v) }],
      rows, sort: ['d', 1], onRow: r => { if (r.nm !== D.market) c.lock(r.nm) }, isSel: r => r.nm === c.S.pin,
      read: W.mm.read(rd.corner), ex: r => W.mm.ex(r.name, r.x, r.y, X, Y, r.q),
    };
  },
};

/* ===================== Sector x Horizon (logic.js L1106-1118) ===================== */
export const hxCard: Card = {
  id: 'hxCard', tab: 'ov', cls: 'ov-narrow', fit: ['.hm-s'],
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D), rows = D.names.map(n => ({ n, sn: D.short(n), v: HZ.map(h => K.retP(D.sec(n), h, null)) } as any)), ih = HZ.map(h => K.retP(D.IH, h, null));
    const cap = HZ.map((_, i) => Math.max(...rows.map(r => Math.abs(r.v[i] ?? 0))) || 1);
    const SK = M.msKeep(S.hxS, k => k === 'sn' || /^h\d$/.test(k)), DEF: M.Level = ['h2', 1], LAB = { sn: W.col.sector, ...Object.fromEntries(HZ.map((h, i) => ['h' + i, h])) };
    rows.forEach(r => r.v.forEach((v: M.N, i: number) => (r['h' + i] = v)));
    M.msSort(rows, SK, { sn: 1 }, DEF);
    el.innerHTML = H3(W.hx.title, W.hx.sub, '', c.win ? null : 'hxCard')
      + `<div class="hm-s" data-scroll="x"><div class="ovx-hm" data-hm>${msTh(SK, 'sn', esc(W.col.sector), 'hd l', W.sort.byName, { tag: 'div', def: DEF, txt: true })}${HZ.map((h, i) => msTh(SK, 'h' + i, h, 'hd', W.sort.byCol(h), { tag: 'div', def: DEF })).join('')}`
      + rows.map(r => `<div class="nm${r.n === S.pin ? ' hl' : ''}" data-n="${esc(r.n)}" role="button" tabindex="0" aria-pressed="${r.n === S.pin}" title="${esc(r.n)}"><span>${esc(r.sn)}</span></div>` + r.v.map((v: M.N, i: number) => (v == null ? `<div>${na(W.hx.na(HZ[i]))}</div>` : `<div class="c${r.n === S.pin ? ' hl' : ''}" data-n="${esc(r.n)}" data-tip="${esc(`<b>${esc(r.sn)}</b><br>${HZ[i]} ${M.pct(v)}`)}" style="${heat(v, cap[i], 0, 1)}">${M.pct(v, 1)}</div>`)).join('')).join('')
      + `<div class="nm ih">${esc(D.market)}</div>` + ih.map((v, i) => `<div class="ih">${v == null ? na(W.hx.na(HZ[i])) : M.pct(v, 1)}</div>`).join('') + `</div></div>`
      + `<div class="lgd">${msNote(SK, LAB, { sn: 1 })}<span>${esc(W.hx.foot(D.market))}</span></div>`;
    msWire(el, SK, () => c.redraw(), DEF, '.hd[data-k]');
    $$('[data-hm] [data-n]', el).forEach(x => {
      x.onclick = () => c.lock(x.dataset.n as string);
      x.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); c.lock(x.dataset.n as string) } };
    });
  },
  detail(c): Detail {
    const D = c.D, K = calc(D), ih = Object.fromEntries(HZ.map(h => [h, K.retP(D.IH, h, null)]));
    const rows = D.names.map(nm => { const o: any = { nm, name: D.short(nm) }; HZ.forEach(h => (o[h] = M.minus(K.retP(D.sec(nm), h, null), ih[h]))); return o });
    HZ.forEach(h => [...rows].filter(r => r[h] != null).sort((p, q) => q[h] - p[h]).forEach((r, i) => (r['k' + h] = i + 1)));
    rows.forEach(r => { const ks = HZ.map(h => r['k' + h]).filter(v => v != null); r.ar = ks.length ? ks.reduce((s, v) => s + v, 0) / ks.length : null });
    return {
      title: W.hx.dTitle(D.market), sub: W.hx.dSub(D.market),
      cols: [{ k: 'name', l: W.col.sector }, ...HZ.map(h => ({ k: h, l: h, num: true, tone: true, f: (v: number) => M.pp(v, 1) })), { k: 'ar', l: W.col.avgRank, num: true, f: v => v.toFixed(1) }],
      rows, sort: ['ar', -1], onRow: r => c.lock(r.nm), isSel: r => r.nm === c.S.pin,
      read: W.hx.read(D.market), ex: r => W.hx.ex(r.name, r['1M'], r.ar, D.market),
    };
  },
};

/* ===================== the market map of one sector (logic.js L1191-1234) ===================== */
const fitW = (t: string) => textW(t, '600 11px Inter, sans-serif') + 6;
/** the lines a group's label takes in `w` px, its words wrapped as the browser wraps them (10 px semibold) */
export function lines(text: string, w: number): number {
  let n = 1, cur = '';
  for (const word of text.split(' ')) {
    const t = cur ? cur + ' ' + word : word;
    if (cur && textW(t, '600 10px Inter, sans-serif') > w) { n++; cur = word } else cur = t;
  }
  return n;
}
const GROUP_FLOOR = 0.012;                // an industry under 1.2% of the sector's weight is drawn at 1.2%, so it has a tile (D08)
export const mkCard: Card = {
  id: 'mkCard', tab: 'ov', cls: 'ov-wide',
  render(el, c) {
    const D = c.D, S = c.S, n = shown(c), ih5 = M.ret(D.IH, D.E, D.P('1W')), locked = !!S.pin && D.names.includes(S.pin);
    const ms = D.members(n).filter(x => x.r5d != null && x.w != null && x.w > 0).map(x => ({ ...x, ind: x.ind || W.mk.unclassified, v5: M.minus(x.r5d, ih5) as number }));
    const g = new Map<string, typeof ms>();
    ms.forEach(x => { const a = g.get(x.ind) || []; a.push(x); g.set(x.ind, a) });
    const subs = [...g.entries()].map(([ind, s]) => { s.sort((p, q) => (q.w as number) - (p.w as number)); const w = s.reduce((p, x) => p + (x.w as number), 0); return { ind, s, w, v5: s.reduce((p, x) => p + (x.w as number) * x.v5, 0) / w } }).sort((p, q) => q.w - p.w);
    const tot = subs.reduce((p, s) => p + s.w, 0), floored = subs.filter(s => s.w < tot * GROUP_FLOOR).length;
    if (S.mkSub && !g.has(S.mkSub)) S.mkSub = null;
    el.innerHTML = H3(W.mk.title(D.short(n)), W.mk.sub(D.weightLabel, D.market, locked), '', c.win ? null : 'mkCard')
      + `<div class="ovx-b"><div class="ovx-mk${S.mkSub ? ' sub' : ''}" data-map></div></div>`
      + `<div class="lgd"><span>${esc(W.mk.foot(ms.length, subs.length, floored))}</span><span class="sp"></span><span class="ovx-scl" aria-hidden="true"><span>−</span>${STEPS.map(([bg]) => `<i style="background:${bg}"></i>`).join('')}<span>+</span></span></div>`;
    const box = $('[data-map]', el);
    requestAnimationFrame(() => {
      const Wd = box.clientWidth, H = box.clientHeight; if (!Wd || !H) return;
      if (!ms.length) { box.innerHTML = `<div class="cv-empty">${esc(W.mk.empty(D.short(n)))}</div>`; return }
      const cap = Math.max(...ms.map(x => Math.abs(x.v5))) || 1;
      let h = '';
      M.squarify(subs.map(s => ({ v: Math.max(s.w, tot * GROUP_FLOOR), o: s })), 0, 0, Wd, H).forEach(r => {
        const s = r.o, gx = r.x + 1, gy = r.y + 1, gw = Math.max(0, r.w - 2), gh = Math.max(0, r.h - 2), lab = gw > 44 && gh > 30;
        // a name wider than its group wraps onto up to three 14 px lines while the group keeps most of its height for its
        // stocks, and only then ends in "…" (check 2 MX2-9: "Healthcare Equipment & Su…" in a 93 px group at 360 px)
        const need = lab ? lines(`${s.ind} ${M.ppx(s.v5)}`, gw - 6) : 1, nl = Math.max(1, Math.min(need, 3, Math.floor((gh * 0.45) / 14))), top = nl > 1 ? nl * 14 : Math.min(14, gh * 0.3);
        const gtip = `<b>${esc(s.ind)}</b><br>${esc(W.mk.gTip(s.s.length, M.weightText(D.weightBasis, s.w), M.ppx(s.v5) + ' pp', D.market))}`;
        h += `<div class="mk-g${s.ind === S.mkSub ? ' on' : ''}" data-ind="${esc(s.ind)}" style="left:${gx}px;top:${gy}px;width:${gw}px;height:${gh}px"><span class="mk-gl${nl > 1 ? ' wr' : ''}"${nl > 1 ? ` style="height:${nl * 14}px;-webkit-line-clamp:${nl}"` : ''} data-tip="${esc(gtip)}">${lab ? `${esc(s.ind)} <span class="${M.cls(s.v5, 1)}">${M.ppx(s.v5)}</span>` : ''}</span>`
          + M.squarify(s.s.slice(0, 10).map(x => ({ v: x.w as number, o: x })), 0, top, gw, gh - top).map(k => {
            const x = k.o, tip = `<b>${esc(x.t)}</b> ${esc(x.n || '')}<br>${esc(s.ind)}<br>5D ${M.pct(x.r5d)} · ${esc(W.vs(D.market))} ${M.pp(x.v5)}<br>${esc(W.cap(D.weightLabel))} ${esc(M.weightText(D.weightBasis, x.w))}`;
            return `<div class="mk-t" data-t="${esc(x.t)}" role="button" tabindex="0" aria-label="${esc(x.t)}" data-tip="${esc(tip)}" style="left:${k.x + 1}px;top:${k.y + 1}px;width:${Math.max(0, k.w - 2)}px;height:${Math.max(0, k.h - 2)}px;${heat(x.v5, cap, 0, 1)}">${k.w > fitW(x.t) && k.h > 24 ? `<b>${esc(x.t)}</b><span>${M.ppx(x.v5)}</span>` : k.w > fitW(x.t) && k.h > 13 ? `<b>${esc(x.t)}</b>` : ''}</div>`;
          }).join('') + '</div>';
      });
      box.innerHTML = h;
      // defect D08: a tile opens its stock (a small window with its figures and "Open in Terminal")
      const open = (t: HTMLElement) => {
        const x = ms.find(m => m.t === t.dataset.t); if (!x) return;
        const r = t.getBoundingClientRect(), b = box.getBoundingClientRect();
        const p = stockPop(box, r.left - b.left + r.width / 2, r.top - b.top + Math.min(r.height, 28), `<div class="ph"><b>${esc(x.t)}</b><span class="muted">${esc(x.ind)}</span></div><div class="kv"><span>5D</span><b class="${M.cls(x.r5d)}">${M.pct(x.r5d)}</b></div><div class="kv"><span>${esc(W.vs(D.market))}</span><b class="${M.cls(x.v5)}">${M.pp(x.v5)}</b></div><div class="kv"><span>${esc(W.cap(D.weightLabel))}</span><b>${esc(M.weightText(D.weightBasis, x.w))}</b></div><div class="btns"><button type="button" class="btn sm primary" data-term="${esc(x.t)}">${esc(W.term.open)}</button></div>`, { from: t });
        ($('[data-term]', p) as HTMLElement).onclick = ev => { ev.stopPropagation(); c.terminal(x.t) };
      };
      $$('.mk-t', box).forEach(t => {
        t.onclick = e => { e.stopPropagation(); open(t) };
        t.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(t) } };
      });
      box.onclick = e => { if (!(e.target as Element).closest('.sx-spop')) $$('.sx-spop', box).forEach(p => (p.hidden = true)) };
    });
  },
  detail(c): Detail {
    const D = c.D, nm = shown(c), ms = D.members(nm), ih5 = M.ret(D.IH, D.E, D.P('1W')), g = new Map<string, M.Row[]>();
    ms.forEach(x => { const k = x.ind || W.mk.unclassified, a = g.get(k) || []; a.push(x); g.set(k, a) });
    const tot = ms.reduce((s, x) => s + (x.w ?? 0), 0);
    const rows = [...g.entries()].map(([ind, s]) => {
      const w = s.reduce((p, x) => p + (x.w ?? 0), 0), k = s.filter(x => x.r5d != null && (x.w ?? 0) > 0), kw = k.reduce((p, x) => p + (x.w as number), 0);
      const r5 = kw ? k.reduce((p, x) => p + (x.w as number) * (x.r5d as number), 0) / kw : null, top = [...s].filter(x => x.r5d != null).sort((p, q) => (q.r5d as number) - (p.r5d as number))[0];
      return { name: ind, n: s.length, sh: tot ? (w / tot) * 100 : null, r5, x: M.minus(r5, ih5), up: M.share(s.filter(x => (x.r5d ?? 0) > 0).length, s.filter(x => x.r5d != null).length), top: top ? top.t : '—', tr: top ? top.r5d : null };
    });
    return {
      title: W.mk.dTitle(D.short(nm)), sub: W.mk.dSub(ms.length), ctl: SEL_SECTOR(c, nm), onSel: v => c.lock(v, false),
      cols: [{ k: 'name', l: W.col.industry }, { k: 'n', l: W.col.stocks, num: true, f: v => String(v) }, { k: 'sh', l: W.col.wshare, num: true, f: v => v.toFixed(1) + '%', tip: D.weightLabel },
             { k: 'r5', l: '5D', num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'x', l: W.col.vs(D.market), num: true, tone: true, f: v => M.pp(v) },
             { k: 'up', l: W.col.up('5D'), num: true, f: v => v.toFixed(0) + '%' }, { k: 'top', l: W.col.leader }, { k: 'tr', l: W.col.leader5, num: true, tone: true, f: v => M.pct(v, 1) }],
      rows, sort: ['sh', 1], onRow: r => { c.S.mkSub = c.S.mkSub === r.name ? null : r.name; c.redraw() }, isSel: r => r.name === c.S.mkSub,
      read: W.mk.read(D.weightLabel, D.market), ex: r => W.mk.ex(r.name, r.sh, r.r5, r.x, r.top, r.tr, D.market),
    };
  },
};
/** the sector select of a window (logic.js fwSecSel): it locks the sector for the window */
export function SEL_SECTOR(c: Ctx, cur: string, withMarket = false) {
  return `<label class="fw-sel"><span class="plab">${esc(W.col.sector)}</span><select class="sx-sel" data-fwsel aria-label="${esc(W.col.sector)}">${withMarket ? `<option value="${esc(c.D.market)}"${cur === c.D.market ? ' selected' : ''}>${esc(W.all(c.D.market))}</option>` : ''}${c.D.names.map(n => `<option value="${esc(n)}"${n === cur ? ' selected' : ''}>${esc(c.D.short(n))}</option>`).join('')}</select></label>`;
}
export function wireSectorSelect(el: HTMLElement, c: Ctx, set?: (v: string) => void) {
  const s = $('[data-fwsel]', el) as HTMLSelectElement | null;
  if (s) s.onchange = () => (set ? set(s.value) : c.lock(s.value, false));
}

/** the readings of the Momentum card for its two horizons (check 1 OR-1): which corner is "turning up" follows the axis
    that holds the shorter horizon; horizons of the same length name their corners by the horizon that is up */
export function mmReading(c: Ctx, X: string, Y: string) {
  const D = c.D, nx = M.hzSessions(D.dates, D.E, X, D.P), ny = M.hzSessions(D.dates, D.E, Y, D.P);
  const name = (x: M.N, y: M.N) => { const q = M.hzRead(x, y, nx, ny); return q == null ? '' : q === 'xonly' ? W.mm.only(X) : q === 'yonly' ? W.mm.only(Y) : W.mm.q[q] };
  const corner = nx === ny ? null : nx > ny ? W.mm.topLeft : W.mm.bottomRight;
  return { nx, ny, name, corner };
}
