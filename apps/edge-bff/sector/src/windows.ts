/* EXEC-SECTOR-ANALYSIS S4: a card opened as a floating window (logic.js L1274-1726): the card with its own copy of the
   page's choices on the left (or on top), its detail table on the right (or below), and the "How to read" footer. One
   window at a time: the page behind is dimmed and a click on it closes the window (the prototype's backdrop; defect N03:
   its 3-window limit and pin could no longer be reached and are gone). A window stays inside the screen (N02) and fills it
   on a phone; a wide table card opens stacked so nothing scrolls sideways (N05); the card's legend stays (N08). */
import * as M from './model.ts';
import { cloneState, type Card, type Ctx, type Detail, type State } from './ctx.ts';
import { $, $$, esc, msNote, msTh, msWire, tipHide } from './ui.ts';
import { W } from './words.ts';

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
  const narrow = innerWidth < 1100, stacked = !!card.stack || narrow || !card.detail;
  el.className = 'fw' + (card.detail ? '' : ' nod') + (stacked ? ' stk' : '');
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.tabIndex = -1;
  el.innerHTML = `<div class="fw-h"><div class="fw-ti"><b class="fw-tt"></b><span class="fw-st"></span></div><button class="iconbtn sm fw-x" type="button" aria-label="${esc(W.win.close)}" title="${esc(W.win.close)}"><svg class="ic ic-sm"><use href="#i-x"/></svg></button></div>`
    + `<div class="fw-c"><div class="fw-l card tc ${card.cls}" data-card="${card.id}"></div>${card.detail ? '<div class="fw-r"></div>' : ''}</div>${card.detail ? '<div class="fw-f"></div>' : ''}`;
  document.body.append(bd, el);
  const left = $('.fw-l', el), right = $('.fw-r', el) as HTMLElement | null, foot = $('.fw-f', el) as HTMLElement | null;
  const vw = innerWidth, vh = innerHeight, phone = vw < 640;
  const Wd = phone ? vw : Math.min(vw - 48, stacked ? 1040 : 1280), Hh = phone ? vh : Math.min(vh - 48, 820);
  el.style.width = Wd + 'px'; el.style.height = Hh + 'px';
  el.style.left = Math.max(0, (vw - Wd) / 2) + 'px'; el.style.top = Math.max(0, (vh - Hh) / 2) + 'px';
  let c: Ctx & { alive: boolean };
  const draw = () => {
    if (!c.alive) return;
    host.render(card, left, c);
    const h = $('.card-h h3 .h3t', left), s = $('.card-h .ttl-s', left);
    $('.fw-tt', el).textContent = h ? h.textContent : '';
    $('.fw-st', el).textContent = s ? s.textContent : '';
    el.setAttribute('aria-label', h ? h.textContent || '' : card.id);
    if (card.detail && right && foot) detail(card.detail(c), c, right, foot, draw);
  };
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
    e.preventDefault(); head.setPointerCapture(e.pointerId);
    const r0 = el.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    const mv = (ev: PointerEvent) => { el.style.left = Math.max(0, Math.min(innerWidth - r0.width, r0.left + ev.clientX - x0)) + 'px'; el.style.top = Math.max(0, Math.min(innerHeight - 44, r0.top + ev.clientY - y0)) + 'px' };
    const up = () => { head.removeEventListener('pointermove', mv); head.removeEventListener('pointerup', up) };
    head.addEventListener('pointermove', mv); head.addEventListener('pointerup', up);
  });
  let last = '', t = 0;
  const ro = new ResizeObserver(() => { const k = `${left.clientWidth}x${left.clientHeight}`; if (k === last) return; const first = !last; last = k; if (!first) { clearTimeout(t); t = window.setTimeout(draw, 100) } });
  draw();
  // the detail table gets its natural width beside the card; when that leaves the card too little room, the window shows
  // the card above its detail (defect D15: no column cut off, no sideways scroll)
  if (right && !stacked) {
    const tb = $('.fw-tb', right) as HTMLElement | null, need = tb ? tb.scrollWidth + 56 : 0, room = el.clientWidth;
    const cardTable = Math.max(0, ...$$('table', left).map(x => x.scrollWidth + 40));       // the card's own table, if any
    if (need > room * 0.58 || cardTable + need > room) { el.classList.add('stk'); el.style.width = Math.min(vw - 48, Math.max(Wd * 0.82, need + 2)) + 'px'; el.style.left = Math.max(0, (vw - el.offsetWidth) / 2) + 'px'; draw() }
    else if (need) $('.fw-c', el).style.gridTemplateColumns = `minmax(0,1fr) ${Math.max(need, 340)}px`;
  }
  ro.observe(left);
  el.focus();
}

/** the detail table (logic.js L1606-1629): the shared sort, the search, the rows' actions and the "How to read" footer */
function detail(D: Detail, c: Ctx, box: HTMLElement, foot: HTMLElement, redraw: () => void) {
  const S = c.S, SK = M.msKeep(S.dS, k => D.cols.some(x => x.k === k)), TXT = Object.fromEntries(D.cols.filter(x => !x.num).map(x => [x.k, 1]));
  const LAB = Object.fromEntries(D.cols.map(x => [x.k, x.l])), rows = M.msSort([...D.rows], SK, TXT, D.sort);
  const q = D.search ? S.dQ.trim().toUpperCase() : '', text = (r: any) => Object.values(r).filter(v => typeof v === 'string' && v.indexOf('<') < 0).join(' ').toUpperCase();
  const keep = box.querySelector('.fw-tw') as HTMLElement | null, top = keep ? keep.scrollTop : 0;
  box.innerHTML = `<div class="fw-dh"><div class="fw-dt"><b>${esc(D.title)}</b><span>${esc(D.sub || '')}</span>${SK.length > 1 ? msNote(SK, LAB, TXT) : ''}</div>${D.search ? `<label class="fw-q"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-search"/></svg><input type="search" placeholder="${esc(D.search)}" aria-label="${esc(D.search)}" value="${esc(S.dQ)}"></label>` : ''}${D.ctl || ''}</div>`
    + (D.note ? `<div class="fw-note">${esc(D.note)}</div>` : '')
    + `<div class="fw-tw"><table class="tbl padat fw-tb${D.center ? ' ctr' : ''}"><thead><tr>${D.cols.map(x => msTh(SK, x.k, esc(x.l), `${x.num ? '' : 'l'}${x.hl ? ' hc' : ''}`, x.tip || '', { def: D.sort, txt: !x.num })).join('')}</tr></thead><tbody>`
    + (rows.length ? rows.map((r, i) => {
      const cells = D.cols.map(x => {
        const v = r[x.k], t = x.html ? r[x.html] ?? '—' : x.f ? (v == null ? '—' : x.f(v, r)) : esc(v ?? '—');
        const inner = x.term && r.t ? `<button type="button" class="tk" data-term="${esc(r.t)}" title="${esc(W.term.rowTip(r.t))}">${esc(r.t)}</button>` : x.b ? `<b>${t}</b>` : t;
        return `<td class="${x.num ? '' : 'l'}${x.tone && typeof v === 'number' ? ' ' + M.cls(v) : ''}${x.hl ? ' hc' : ''}">${inner}</td>`;
      }).join('');
      return `<tr class="${r.nm === c.D.market ? 'ih' : ''}${D.onRow ? ' ck' : ''}${D.isSel && D.isSel(r) ? ' on' : ''}"${D.onRow ? ` data-i="${i}" tabindex="0" role="button"` : ''}${q && !text(r).includes(q) ? ' hidden' : ''}>${cells}</tr>`;
    }).join('') : `<tr><td class="l" colspan="${D.cols.length}">${esc(W.win.noRows)}</td></tr>`)
    + `<tr class="fw-qn"${!q || rows.some(r => text(r).includes(q)) ? ' hidden' : ''}><td class="l" colspan="${D.cols.length}">${esc(W.search.none(S.dQ))}</td></tr></tbody></table></div>`;
  const tw = $('.fw-tw', box); tw.scrollTop = top;
  // How to read, then an example sentence built from the first row shown (logic.js L1618-1622)
  const ex = rows.find(r => r.nm !== c.D.market && !(q && !text(r).includes(q))) || rows[0];
  let eg = '';
  try { eg = ex && D.ex ? D.ex(ex) : '' } catch { eg = '' }
  foot.innerHTML = `<b>${esc(W.win.howTo)}</b> · ${esc(D.read)}${eg ? ` <b>${esc(W.win.example)}</b> · ${esc(eg.charAt(0).toUpperCase() + eg.slice(1))}${/[.?!]$/.test(eg) ? '' : '.'}` : ''}`;
  const qi = $('.fw-q input', box) as HTMLInputElement | null;
  if (qi) qi.oninput = () => {
    S.dQ = qi.value; const v = qi.value.trim().toUpperCase(); let n = 0;
    $$('tbody tr:not(.fw-qn)', box).forEach((tr, i) => { const r = rows[i]; if (!r) return; const on = !v || text(r).includes(v); tr.hidden = !on; if (on) n++ });
    const nn = $('tr.fw-qn', box); nn.hidden = n > 0; nn.firstElementChild!.textContent = W.search.none(qi.value);
  };
  if (D.onRow) $$('tbody tr[data-i]', box).forEach(tr => {
    const go = () => D.onRow!(rows[+(tr.dataset.i as string)]);
    tr.onclick = e => { if ((e.target as Element).closest('[data-term]')) return; go() };
    tr.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === tr) { e.preventDefault(); go() } };
  });
  $$('[data-term]', box).forEach(b => (b.onclick = e => { e.stopPropagation(); c.terminal(b.dataset.term as string) }));
  msWire(box, SK, redraw, D.sort, 'th[data-k]');
  const sel = $('[data-fwsel]', box) as HTMLSelectElement | null;
  if (sel && D.onSel) sel.onchange = () => D.onSel!(sel.value);
}
