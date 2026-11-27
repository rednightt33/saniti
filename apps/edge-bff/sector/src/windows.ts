/* EXEC-SECTOR-ANALYSIS S4: a card opened as a floating window (logic.js L1274-1726): the card with its own copy of the
   page's choices on the left (or on top), its detail table on the right (or below), and the "How to read" footer. One
   window at a time: the page behind is dimmed and a click on it closes the window (the prototype's backdrop; defect N03:
   its 3-window limit and pin could no longer be reached and are gone). A window stays inside the screen (N02) and fills it
   on a phone; a wide table card opens stacked so nothing scrolls sideways (N05); the card's legend stays (N08).
   Visual round 2 (user decisions of 2026-11-27, EXEC.md EXEC-SECTOR-ANALYSIS V1-V10, UD76-UD79):
   - `fit` (UD76 2a, the Cumulative return answer 3A): a side-by-side window is as tall as its detail table, and the
     card's chart takes that height (never under its minimum), so the two sides end level;
   - `align` (the drill-down and Beta windows, "A"): the card's table and the detail table share one column grid;
   - `layout: 'c1'` (Rotation detail, "C1"): a compact list on the left and the detail on the right on one 52 px title
     band and one 36 px row grid, the card's controls in one row above both; sector chips on a phone;
   - `hideDetail` (Rotation map, V8): the Timeline takes the whole window, the readings table and its footer hidden;
   - a detail with `limit` shows that many rows of its order (Stretched pairs' Show).
   Check 2 (2026-11-27, verification/sector_analysis/check2/FIXES.md): a stacked window grows to its tables (`widen`,
   OV2-1); a window whose detail is hidden is as tall as its card (`bare`, RP2-1); its touch areas are measured after each
   draw (touch.ts, MX2-4). */
import * as M from './model.ts';
import { cloneState, type Card, type Ctx, type Detail, type State } from './ctx.ts';
import { $, $$, esc, msNote, msTh, msWire, na, scrollCues, tipHide } from './ui.ts';
import { W } from './words.ts';
import { fitTouch } from './touch.ts';

export interface WindowHost {
  ctx(S: State, win: boolean, redraw: () => void): Ctx & { alive: boolean };
  render(card: Card, el: HTMLElement, c: Ctx): void;
}
let open: { close(): void } | null = null;
export const closeWindow = () => open?.close();
export const windowOpen = () => !!open;

export function openWindow(card: Card, page: Ctx, host: WindowHost, from: HTMLElement | null) {
  open?.close();
  const S = cloneState(page.S); S.dS = []; S.dQ = '';
  const bd = document.createElement('div'), el = document.createElement('div');
  bd.className = 'fw-bd'; bd.setAttribute('aria-hidden', 'true');
  const c1 = card.layout === 'c1', narrow = innerWidth < 1100, stacked = !c1 && (!!card.stack || narrow || !card.detail);
  el.className = 'fw' + (card.detail ? '' : ' nod') + (stacked ? ' stk' : '') + (c1 ? ' c1' : '') + (card.align ? ' al' : '');
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.tabIndex = -1;
  el.innerHTML = `<div class="fw-h"><div class="fw-ti"><b class="fw-tt"></b><span class="fw-st"></span></div><button class="iconbtn sm fw-x" type="button" aria-label="${esc(W.win.close)}" title="${esc(W.win.close)}"><svg class="ic ic-sm"><use href="#i-x"/></svg></button></div>`
    + `<div class="fw-c"><div class="fw-l card tc ${card.cls}" data-card="${card.id}"></div>${card.detail ? '<div class="fw-r"></div>' : ''}</div>${card.detail ? '<div class="fw-f"></div>' : ''}`;
  document.body.append(bd, el);
  const left = $('.fw-l', el), right = $('.fw-r', el) as HTMLElement | null, foot = $('.fw-f', el) as HTMLElement | null, body = $('.fw-c', el);
  const vw = innerWidth, vh = innerHeight, phone = vw < 640;
  const Wd = phone ? vw : Math.min(vw - 48, c1 ? 1100 : stacked ? 1040 : card.wide ? 1440 : 1280), Hh = phone ? vh : Math.min(vh - 48, 820);
  el.style.width = Wd + 'px'; el.style.height = Hh + 'px';
  el.style.left = Math.max(0, (vw - Wd) / 2) + 'px'; el.style.top = Math.max(0, (vh - Hh) / 2) + 'px';
  let c: Ctx & { alive: boolean }, cols = '', laid = false, fitH = 0, moved = false, wideW = 0;
  const draw = () => {
    if (!c.alive) return;
    host.render(card, left, c);
    const h = $('.card-h h3 .h3t', left), s = $('.card-h .ttl-s', left);
    $('.fw-tt', el).textContent = h ? h.textContent : '';
    $('.fw-st', el).textContent = s ? s.textContent : '';
    el.setAttribute('aria-label', h ? h.textContent || '' : card.id);
    const hide = !!card.hideDetail?.(c);
    el.classList.toggle('nod', !card.detail || hide); el.classList.toggle('bare', hide);
    if (right) right.hidden = hide;
    if (foot) foot.hidden = hide;
    body.style.gridTemplateColumns = hide ? '' : cols;
    if (card.detail && right && foot && !hide) { detail(card.detail(c), c, right, foot, draw); scrollCues(right) }
    // a stacked window of a table card (or of a card that is only controls) gives the card at most half its height, so
    // the detail table below shows enough rows to use (check 1 OR-11, RP-11: two stock rows were visible under the table)
    el.classList.toggle('stk-t', !phone && el.classList.contains('stk') && !!card.detail && (!!$('.tbl-wrap', left) || left.classList.contains('ctlo')));
    if (card.detail && right && !hide && !laid) layout();
    if (card.align && right) alignTables($('table', left) as HTMLTableElement | null, $('.fw-tb', right) as HTMLTableElement | null);
    if (widen()) return;
    // the cues of the window's scrollers once their tables have their final widths (aligned, widened)
    scrollCues(el); requestAnimationFrame(() => c.alive && scrollCues(el));
    requestAnimationFrame(() => requestAnimationFrame(() => c.alive && fitTouch(el)));
    // fitted now, and again once the card's chart and legend are drawn (a card draws its chart in the next frame)
    fit(); requestAnimationFrame(() => requestAnimationFrame(() => c.alive && fit()));
  };
  /** side by side: the detail table gets its natural width beside the card; when that leaves the card too little room, the
      window shows the card above its detail (defect D15: no column cut off, no sideways scroll). Decided once, when the
      detail first shows (a Rotation map opened on its Timeline has none until the Map is chosen) */
  function layout() {
    laid = true;
    if (!right || stacked || c1) return;
    const tb = $('.fw-tb', right) as HTMLElement | null, need = tb ? tb.scrollWidth + 56 : 0, room = el.clientWidth;
    const cardTable = Math.max(0, ...$$('table', left).map(x => x.scrollWidth + 40));       // the card's own table, if any
    if (need > room * 0.58 || cardTable + need > room) { el.classList.add('stk'); el.style.width = Math.min(vw - 48, Math.max(Wd * 0.82, need + 2)) + 'px'; el.style.left = Math.max(0, (vw - el.offsetWidth) / 2) + 'px'; draw() }
    else if (need) { cols = `minmax(0,1fr) ${Math.max(need, 340)}px`; body.style.gridTemplateColumns = cols }
  }
  /** a stacked window whose tables are wider than it (the drill-down with every industry open: 13 columns and a wider
      first column) grows up to the screen less its margin, so no column is cut at its edge; on a screen still narrower the
      tables keep their sideways scroll and its cue (check 2 OV2-1: 1062 px of tables in a 1012 px scroller, capped at
      1040 px). Only grows; a window the viewer resized keeps the viewer's width. True when it grew (and drew again) */
  function widen(): boolean {
    if (phone || !el.classList.contains('stk')) return false;
    if (wideW && el.style.width !== wideW + 'px') return false;
    const over = Math.max(0, ...$$('.fw-tw, .tbl-wrap', el).filter(x => x.offsetParent !== null).map(x => x.scrollWidth - x.clientWidth));
    const w = Math.min(vw - 48, Math.ceil(el.offsetWidth + over + 2));
    if (over <= 1 || w <= el.offsetWidth + 1) return false;
    el.style.width = w + 'px'; wideW = w;
    if (!moved) el.style.left = Math.max(0, (vw - w) / 2) + 'px';
    draw();                                               // the tables laid out again on the new width
    return true;
  }
  /** `fit`: the window as tall as its detail table, and never less than the card needs with its chart at its minimum.
      A window the viewer resized keeps the viewer's height */
  function fit() {
    if (fitH && el.style.height !== fitH + 'px') return;
    // a window whose detail is hidden (the Rotation map's Timeline, `bare`) is as tall as its card's content, so its legend
    // is its bottom line (check 2 RP2-1: 108-293 px of blank under the dates, the legend 181 px above the window's edge)
    if (el.classList.contains('bare') && !phone) {
      const want = Math.round(Math.min(vh - 48, Math.max(320, el.offsetHeight - body.clientHeight + left.offsetHeight)));
      if (Math.abs(want - el.offsetHeight) > 1) { el.style.height = want + 'px'; if (!moved) el.style.top = Math.max(0, (vh - want) / 2) + 'px' }
      fitH = Math.round(parseFloat(el.style.height)); return;
    }
    if (!card.fit || phone || !right || right.hidden || el.classList.contains('stk')) return;
    const tw = $('.fw-tw', right), tb = $('.fw-tb', right), grow = $(card.fit[0], left) as HTMLElement | null;
    if (!tw || !tb || !grow) return;
    const rNeed = right.clientHeight - tw.clientHeight + tb.offsetHeight + 12;
    // the least height of the growing part: a given list's own height; a chart box's CSS minimum; else its rows' own height
    const chart = grow.matches('[data-chart]') || !!grow.querySelector('[data-chart]');
    const min = card.fit[1] ? natural($(card.fit[1], left) as HTMLElement | null) + (card.fit[2] ?? 0) : chart ? parseFloat(getComputedStyle(grow).minHeight) || 240 : natural(grow);
    const lNeed = left.scrollHeight - grow.offsetHeight + min;
    const want = Math.round(Math.min(vh - 48, Math.max(320, el.offsetHeight - body.clientHeight + Math.max(rNeed, lNeed))));
    if (Math.abs(want - el.offsetHeight) > 1) {
      el.style.height = want + 'px';
      if (!moved) el.style.top = Math.max(0, (vh - want) / 2) + 'px';
    }
    fitH = Math.round(parseFloat(el.style.height));
  }
  c = host.ctx(S, true, draw);
  const close = () => {
    if (!c.alive) return;
    c.alive = false; ro.disconnect(); el.remove(); bd.remove(); tipHide(); open = null;
    document.removeEventListener('keydown', key, true);
    from?.focus({ preventScroll: true });
  };
  open = { close };
  const key = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      const t = e.target as Element;
      if (t.closest?.('.sx-rpop,.bxp:not([hidden]),.btxp:not([hidden])') || t.tagName === 'SELECT') return;
      e.preventDefault(); close();
    } else if (e.key === 'Tab') {                         // the focus stays inside the window
      const f = $$('button:not([disabled]),select,input,[tabindex="0"]', el).filter(x => x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
    }
  };
  document.addEventListener('keydown', key, true);
  bd.onclick = close;
  ($('.fw-x', el) as HTMLElement).onclick = close;
  // drag by the title bar, kept inside the screen (not on a phone, where the window fills it)
  const head = $('.fw-h', el);
  head.addEventListener('pointerdown', e => {
    if (phone || e.button !== 0 || (e.target as Element).closest('button')) return;
    e.preventDefault(); head.setPointerCapture(e.pointerId); moved = true;
    const r0 = el.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    const mv = (ev: PointerEvent) => { el.style.left = Math.max(0, Math.min(innerWidth - r0.width, r0.left + ev.clientX - x0)) + 'px'; el.style.top = Math.max(0, Math.min(innerHeight - 44, r0.top + ev.clientY - y0)) + 'px' };
    const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up) };
    head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
  });
  let last = '', t = 0;
  const ro = new ResizeObserver(() => { const k = `${left.clientWidth}x${left.clientHeight}`; if (k === last) return; const first = !last; last = k; if (!first) { clearTimeout(t); t = window.setTimeout(draw, 100) } });
  draw();
  ro.observe(left);
  // two tables on one column grid scroll sideways together (a phone)
  if (card.align && right) syncX($('.tbl-wrap', left), right);
  el.focus();
}

/** the height an element takes with its own content, not stretched by its box (a list of rows at their least height) */
export function natural(x: HTMLElement | null): number {
  if (!x) return 0;
  const s = x.style, keep = [s.flex, s.height, s.minHeight, s.maxHeight, s.alignSelf];
  s.flex = '0 0 auto'; s.height = 'auto'; s.minHeight = '0'; s.maxHeight = 'none'; s.alignSelf = 'start';
  const h = x.getBoundingClientRect().height;
  [s.flex, s.height, s.minHeight, s.maxHeight, s.alignSelf] = keep;
  return h;
}

/* ---------- two tables on one column grid (the drill-down and Beta windows, user 2026-11-27 "A") ----------
   Every column edge of the table with fewer columns falls on a column edge of the other: each of its columns covers one
   or more neighbouring columns (slots) of the other, chosen so that no slot has to widen beyond what the widest cell of
   either table needs, and the covered widths stay close to what each column needs; slots left over at the right end are
   an empty column. Each slot is as wide as its widest need in either table (nothing cut); spare room goes to the slots
   after the first. Both tables then have one fixed width. The scratchpad mock's alignTables (vis4/common.js) took its
   spans from screenshots; here they come from the columns themselves, so an opened industry or another column set
   (the Custom window, the stock table of another sector) takes its own spans. */
/** the spans: how many consecutive slots of `base` each column of `other` covers (the rest of the slots trail empty) */
export function spans(base: number[], other: number[]): number[] {
  const m = base.length, k = other.length, sum = (a: number, z: number) => base.slice(a, z).reduce((s, v) => s + v, 0);
  if (!k || k > m) return other.map(() => 1);
  // cost of a group: the width it adds beyond the slots (a primary cost), then how far its width is from its need
  const cost = (a: number, z: number, need: number) => { const have = sum(a, z); return [Math.max(0, need - have), (Math.max(have, need) - need) ** 2] as const };
  type Best = { add: number; sq: number; cut: number[] } | null;
  const f: Best[][] = Array.from({ length: k + 1 }, () => Array(m + 1).fill(null));
  f[0][0] = { add: 0, sq: 0, cut: [] };
  const better = (a: Best, b: { add: number; sq: number }) => !a || b.add < a.add - 1e-6 || (Math.abs(b.add - a.add) <= 1e-6 && b.sq < a.sq);
  for (let j = 1; j <= k; j++) for (let i = j; i <= m - (k - j); i++) for (let p = j - 1; p < i; p++) {
    const prev = f[j - 1][p]; if (!prev) continue;
    const [add, sq] = cost(p, i, other[j - 1]), cand = { add: prev.add + add, sq: prev.sq + sq, cut: [...prev.cut, i - p] };
    if (better(f[j][i], cand)) f[j][i] = cand;
  }
  let best: Best = null;
  for (let i = k; i <= m; i++) {
    const x = f[k][i]; if (!x) continue;
    const tail = sum(i, m), cand = { add: x.add, sq: x.sq + tail ** 2, cut: x.cut };      // trailing slots: an empty column
    if (better(best, cand)) best = cand;
  }
  return best ? best.cut : other.map(() => 1);
}
/** the widths of each column of a table at its natural size (its colspan-1 cells) */
function naturalCols(t: HTMLTableElement): number[] {
  t.querySelector('colgroup[data-al]')?.remove(); $$('.al-fill', t).forEach(x => x.remove());
  t.style.tableLayout = 'auto'; t.style.width = 'max-content'; t.style.minWidth = '0';
  const n = t.querySelector('thead tr')?.children.length ?? 0, w = Array(n).fill(0);
  $$('tr', t).forEach(r => { if ((r as HTMLElement).hidden) return; let i = 0; [...r.children].forEach(x => { const s = (x as HTMLTableCellElement).colSpan || 1; if (s === 1 && i < n) w[i] = Math.max(w[i], x.getBoundingClientRect().width); i += s }) });
  return w.map(x => Math.ceil(x));
}
export function alignTables(top: HTMLTableElement | null, bot: HTMLTableElement | null) {
  if (!top || !bot || !top.offsetParent || !bot.offsetParent) return;
  const wt = naturalCols(top), wb = naturalCols(bot), [B, O, wB, wO] = wt.length >= wb.length ? [top, bot, wt, wb] : [bot, top, wb, wt];
  const sp = spans(wB, wO), slots = [...wB];
  let at = 0;
  const ranges = sp.map(n => { const r = [at, at + n]; at += n; return r });
  ranges.forEach(([a, z], j) => { const have = slots.slice(a, z).reduce((s, v) => s + v, 0), need = wO[j] || 0; if (need > have) for (let i = a; i < z; i++) slots[i] += (need - have) / (z - a) });
  const box = Math.min((B.parentElement as HTMLElement).clientWidth, (O.parentElement as HTMLElement).clientWidth), sum = slots.reduce((s, v) => s + v, 0);
  if (sum < box && slots.length > 1) { const extra = box - sum; for (let i = 1; i < slots.length; i++) slots[i] += extra / (slots.length - 1) }
  const total = Math.floor(Math.max(box, sum));
  const set = (t: HTMLTableElement, widths: number[]) => {
    const cg = document.createElement('colgroup'); cg.dataset.al = '1';
    widths.forEach(w => { const x = document.createElement('col'); x.style.width = w.toFixed(2) + 'px'; cg.appendChild(x) });
    t.prepend(cg); t.style.tableLayout = 'fixed'; t.style.width = total + 'px';
  };
  set(B, slots);
  const wo = ranges.map(([a, z]) => slots.slice(a, z).reduce((s, v) => s + v, 0));
  if (at < slots.length) wo.push(slots.slice(at).reduce((s, v) => s + v, 0));
  set(O, wo);
  // the empty column under the trailing slots keeps the rows' lines whole
  if (at < slots.length) $$('tr', O).forEach(r => { const x = document.createElement(r.parentElement?.tagName === 'THEAD' ? 'th' : 'td'); x.className = 'al-fill'; x.setAttribute('aria-hidden', 'true'); r.appendChild(x) });
}
/** two scrollers that move sideways together */
function syncX(a: HTMLElement | null, box: HTMLElement) {
  if (!a) return;
  let busy = false;
  const go = (from: HTMLElement, to: HTMLElement | null) => { if (busy || !to) return; busy = true; to.scrollLeft = from.scrollLeft; requestAnimationFrame(() => (busy = false)) };
  a.addEventListener('scroll', () => go(a, $('.fw-tw', box)), { passive: true });
  box.addEventListener('scroll', e => { const t = e.target as HTMLElement; if (t.classList?.contains('fw-tw')) go(t, a) }, { passive: true, capture: true });
}

/** the detail table (logic.js L1606-1629): the shared sort, the search, the rows' actions and the "How to read" footer */
function detail(D: Detail, c: Ctx, box: HTMLElement, foot: HTMLElement, redraw: () => void) {
  const S = c.S, SK = M.msKeep(S.dS, k => D.cols.some(x => x.k === k)), TXT = Object.fromEntries(D.cols.filter(x => !x.num).map(x => [x.k, 1]));
  const LAB = Object.fromEntries(D.cols.map(x => [x.k, x.l])), sorted = M.msSort([...D.rows], SK, TXT, D.sort), rows = D.limit ? sorted.slice(0, D.limit) : sorted;
  const q = D.search ? S.dQ.trim().toUpperCase() : '', text = (r: any) => Object.values(r).filter(v => typeof v === 'string' && v.indexOf('<') < 0).join(' ').toUpperCase();
  const none = (s: string) => (D.limit && sorted.length > rows.length && D.limitNone ? D.limitNone(s) : W.search.none(s));
  const keep = box.querySelector('.fw-tw') as HTMLElement | null, top = keep ? keep.scrollTop : 0, left = keep ? keep.scrollLeft : 0;
  box.innerHTML = `<div class="fw-dh"><div class="fw-dt"><b>${esc(D.title)}</b><span>${esc(D.sub || '')}</span>${SK.length > 1 ? msNote(SK, LAB, TXT) : ''}</div>${D.search ? `<label class="fw-q"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-search"/></svg><input type="search" placeholder="${esc(D.search)}" aria-label="${esc(D.search)}" value="${esc(S.dQ)}"></label>` : ''}${D.ctl || ''}</div>`
    + (D.note ? `<div class="fw-note">${esc(D.note)}</div>` : '')
    + `<div class="fw-tw"><table class="tbl padat fw-tb${D.center ? ' ctr' : ''}"><thead><tr>${D.cols.map(x => msTh(SK, x.k, esc(x.l), `${x.num ? '' : 'l'}${x.hl ? ' hc' : ''}`, x.tip || '', { def: D.sort, txt: !x.num })).join('')}</tr></thead><tbody>`
    + (rows.length ? rows.map((r, i) => {
      const cells = D.cols.map(x => {
        // a dash says why (check 1 BD-11: the same mechanism in the windows' tables)
        const v = r[x.k], NA = na(W.win.na), t = x.html ? (r[x.html] == null || r[x.html] === '—' ? NA : r[x.html]) : v == null || v === '—' ? NA : x.f ? x.f(v, r) : esc(v);
        const inner = x.term && r.t ? `<button type="button" class="tk" data-term="${esc(r.t)}" title="${esc(W.term.rowTip(r.t))}">${esc(r.t)}</button>` : x.b ? `<b>${t}</b>` : t;
        // a toned figure takes the colour of its printed sign (check 2 BD2-4: "0.0 pp" was green from an unrounded +0.03)
        return `<td class="${x.num ? '' : 'l'}${x.tone && typeof v === 'number' ? ' ' + (x.f ? M.clsText(v, x.f(v, r)) : M.cls(v)) : ''}${x.hl ? ' hc' : ''}">${inner}</td>`;
      }).join('');
      const on = !!(D.isSel && D.isSel(r));
      return `<tr class="${r.nm === c.D.market ? 'ih' : ''}${D.onRow ? ' ck' : ''}${on ? ' on' : ''}"${D.onRow ? ` data-i="${i}" tabindex="0" role="button" aria-pressed="${on}"` : ''}${q && !text(r).includes(q) ? ' hidden' : ''}>${cells}</tr>`;
    }).join('') : `<tr><td class="l" colspan="${D.cols.length}">${esc(D.empty || W.win.noRows)}</td></tr>`)
    + `<tr class="fw-qn"${!q || rows.some(r => text(r).includes(q)) ? ' hidden' : ''}><td class="l" colspan="${D.cols.length}">${esc(none(S.dQ))}</td></tr></tbody></table></div>`;
  const tw = $('.fw-tw', box); tw.scrollTop = top; tw.scrollLeft = left;
  // How to read, then an example sentence built from the first row shown (logic.js L1618-1622)
  const ex = rows.find(r => r.nm !== c.D.market && !(q && !text(r).includes(q))) || rows[0];
  let eg = '';
  try { eg = ex && D.ex ? D.ex(ex) : '' } catch { eg = '' }
  foot.innerHTML = `<b>${esc(W.win.howTo)}</b> · ${esc(D.read)}${eg ? ` <b>${esc(W.win.example)}</b> · ${esc(eg.charAt(0).toUpperCase() + eg.slice(1))}${/[.?!]$/.test(eg) ? '' : '.'}` : ''}`;
  const qi = $('.fw-q input', box) as HTMLInputElement | null;
  if (qi) qi.oninput = () => {
    S.dQ = qi.value; const v = qi.value.trim().toUpperCase(); let n = 0;
    $$('tbody tr:not(.fw-qn)', box).forEach((tr, i) => { const r = rows[i]; if (!r) return; const on = !v || text(r).includes(v); tr.hidden = !on; if (on) n++ });
    const nn = $('tr.fw-qn', box); nn.hidden = n > 0; nn.firstElementChild!.textContent = none(qi.value);
  };
  if (D.onRow) $$('tbody tr[data-i]', box).forEach(tr => {
    const go = (e: MouseEvent | KeyboardEvent) => D.onRow!(rows[+(tr.dataset.i as string)], e);
    tr.onclick = e => { if ((e.target as Element).closest('[data-term]')) return; go(e) };
    tr.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === tr) { e.preventDefault(); go(e) } };
  });
  $$('[data-term]', box).forEach(b => (b.onclick = e => { e.stopPropagation(); c.terminal(b.dataset.term as string) }));
  msWire(box, SK, redraw, D.sort, 'th[data-k]');
  const sel = $('[data-fwsel]', box) as HTMLSelectElement | null;
  if (sel && D.onSel) sel.onchange = () => D.onSel!(sel.value);
  if (D.wire) D.wire(box);
}
