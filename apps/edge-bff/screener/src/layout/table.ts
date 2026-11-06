/* EXEC-SCREENER-V21 layout: the results table's layout (reference layout.js 909-963). The identity columns (select,
   watch, symbol) stay pinned on the left while the table scrolls sideways; any other header is dragged to move its
   column (the order is kept per browser by column key: a sort key, an extra column id or the header text); a table
   wider than its pane switches to a compact density first. Only the DOM order of the cells changes: the rows, values,
   sort and selection are the page's own (results.ts). */
import { store } from '../storage.ts';
import { LKEYS } from './prefs.ts';

const PIN = 3;   // select, watch, symbol
let ORD: string[] = (() => { const v = store.get<unknown>(LKEYS.order, []); return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [] })();
const thKey = (th: HTMLElement) => th.dataset.xid ? 'x:' + th.dataset.xid : (th.querySelector('[data-sort]') as HTMLElement | null)?.dataset.sort || ('t:' + (th.textContent || '').trim());

function applyOrder(tbl: HTMLTableElement) {
  const ths = [...tbl.querySelectorAll<HTMLElement>('thead tr th')]; if (ths.length <= PIN) return;
  const keys = ths.map(thKey), movable = keys.slice(PIN);
  const known = ORD.filter(k => movable.includes(k)); if (!known.length) return;
  // the kept order first; a column not ordered yet stays after the column it followed in the page's own order
  const res = [...known];
  for (const k of movable.filter(x => !known.includes(x))) {
    const nat = movable.indexOf(k); let after = -1;
    for (let i = nat - 1; i >= 0; i--) { const j = res.indexOf(movable[i]); if (j >= 0) { after = j; break } }
    res.splice(after + 1, 0, k);
  }
  const perm = [...Array(PIN).keys(), ...res.map(k => keys.indexOf(k))];
  if (perm.every((v, i) => v === i)) return;
  tbl.querySelectorAll('tr').forEach(tr => { const cells = [...tr.children]; if (cells.length !== keys.length) return; perm.forEach(i => tr.appendChild(cells[i])) });
}
function applyPins(tbl: HTMLTableElement) {
  const head = [...tbl.querySelectorAll<HTMLElement>('thead tr th')].slice(0, PIN);
  let left = 0; const lefts = head.map(th => { const l = left; left += th.offsetWidth; return l });
  tbl.querySelectorAll('tr').forEach(tr => {
    [...tr.children].forEach((c, i) => {
      const el = c as HTMLElement;
      if (i < PIN) { el.classList.add('pin'); el.style.left = lefts[i] + 'px'; el.classList.toggle('pin-last', i === PIN - 1) }
      else if (el.classList.contains('pin')) { el.classList.remove('pin', 'pin-last'); el.style.left = '' }
    });
  });
}
function applyDense(tbl: HTMLTableElement) {
  const wrap = tbl.closest('.tbl-wrap') as HTMLElement | null; if (!wrap) return;
  tbl.classList.remove('dense');
  tbl.classList.toggle('dense', wrap.scrollWidth > wrap.clientWidth + 2);
  wrap.classList.toggle('scrolled-x', wrap.scrollLeft > 0);
  if (!wrap.dataset.sx) { wrap.dataset.sx = '1'; wrap.addEventListener('scroll', () => wrap.classList.toggle('scrolled-x', wrap.scrollLeft > 0), { passive:true }) }
}
/** order, density, pins: after every table render (results.ts) and on resize */
export function applyTable(tbl: HTMLTableElement) {
  applyOrder(tbl);
  // density and pins read the layout: once per frame, after the frame's writes
  requestAnimationFrame(() => { if (!tbl.isConnected) return; applyDense(tbl); applyPins(tbl) });
}
const current = () => document.querySelector('#resPane table.res') as HTMLTableElement | null;

/* ---- drag a header to move its column (the pinned ones stay) ----------------------------------------------- */
export function bindTableDrag(pane: HTMLElement) {
  let drag: { th: HTMLElement; x0: number; on: boolean; tgt: number; mark?: HTMLElement } | null = null;
  pane.addEventListener('pointerdown', e => {
    const t = e.target as HTMLElement, th = t.closest('thead th') as HTMLElement | null;
    if (!th || e.button !== 0 || th.classList.contains('pin') || t.closest('.xcol-x,input,.pvchip')) return;
    drag = { th, x0:e.clientX, on:false, tgt:-1 };
  });
  addEventListener('pointermove', e => {
    if (!drag) return;
    if (!drag.on) {
      if (Math.abs(e.clientX - drag.x0) < 6) return;
      drag.on = true; drag.th.classList.add('dragging'); document.body.classList.add('col-dragging');
      drag.mark = document.createElement('i'); drag.mark.className = 'col-drop'; drag.th.closest('.tbl-wrap')!.appendChild(drag.mark);
    }
    const tbl = drag.th.closest('table')!, wrap = tbl.closest('.tbl-wrap') as HTMLElement;
    const ths = [...tbl.querySelectorAll<HTMLElement>('thead th')].filter(x => !x.classList.contains('pin'));
    let tgt = ths.length; for (let i = 0; i < ths.length; i++) { const r = ths[i].getBoundingClientRect(); if (e.clientX < r.left + r.width / 2) { tgt = i; break } }
    drag.tgt = tgt;
    const ref = ths[tgt] || ths[ths.length - 1], rr = ref.getBoundingClientRect(), wr = wrap.getBoundingClientRect();
    drag.mark!.style.left = ((tgt < ths.length ? rr.left : rr.right) - wr.left + wrap.scrollLeft - 1) + 'px';
    if (e.clientX > wr.right - 40) wrap.scrollLeft += 12; else if (e.clientX < wr.left + PIN * 60) wrap.scrollLeft -= 12;
  });
  addEventListener('pointerup', () => {
    if (!drag) return; const d = drag; drag = null; if (!d.on) return;
    d.th.classList.remove('dragging'); document.body.classList.remove('col-dragging'); d.mark?.remove();
    const tbl = d.th.closest('table') as HTMLTableElement;
    const keys = [...tbl.querySelectorAll<HTMLElement>('thead th')].filter(x => !x.classList.contains('pin')).map(thKey);
    const k = thKey(d.th), from = keys.indexOf(k); keys.splice(from, 1); keys.splice(d.tgt > from ? d.tgt - 1 : d.tgt, 0, k);
    ORD = keys; store.set(LKEYS.order, ORD);
    applyTable(tbl);
    // the drag is not a sort click: swallow the click that follows this pointerup, and only that one
    const swallow = (ev: Event) => { ev.stopPropagation(); ev.preventDefault() };
    addEventListener('click', swallow, { capture:true, once:true }); setTimeout(() => removeEventListener('click', swallow, true), 0);
  });
  addEventListener('resize', () => { const t = current(); if (t) requestAnimationFrame(() => { applyDense(t); applyPins(t) }) });
}
/** move the keyboard focus' column one place left or right (Alt+Shift+arrow on a header button) */
export function moveColumn(th: HTMLElement, dir: -1 | 1) {
  const tbl = th.closest('table') as HTMLTableElement | null; if (!tbl || th.classList.contains('pin')) return;
  const keys = [...tbl.querySelectorAll<HTMLElement>('thead th')].filter(x => !x.classList.contains('pin')).map(thKey);
  const k = thKey(th), i = keys.indexOf(k), j = i + dir; if (i < 0 || j < 0 || j >= keys.length) return;
  keys.splice(i, 1); keys.splice(j, 0, k); ORD = keys; store.set(LKEYS.order, ORD);
}
