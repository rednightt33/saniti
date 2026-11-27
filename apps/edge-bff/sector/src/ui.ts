/* EXEC-SECTOR-ANALYSIS S4: the DOM helpers every card shares: card header, segmented controls, the shared multi-column
   sort headers, the floating read-out (one element for the page and its windows), the date tag under a chart's hover
   line, the Custom range popover and colour scales. A card never uses an element id: a card is drawn on the page and in
   its floating window at the same time, so it finds its parts by data attributes inside its own element. */
import * as M from './model.ts';
import { W } from './words.ts';

export const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
export const $ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => r.querySelector(s) as T;
export const $$ = <T extends Element = HTMLElement>(s: string, r: ParentNode = document) => [...r.querySelectorAll(s)] as T[];
export const DOT = ' · ';

/** a card header: title (with its expand button), subtitle, controls on the right */
export function H3(title: string, sub: string, ctl = '', expand: string | null = null) {
  const x = expand ? `<button class="fwx" type="button" data-fw="${esc(expand)}" aria-label="${esc(W.win.expand(title))}" title="${esc(W.win.expandTip)}"><svg class="ic ic-sm"><use href="#i-expand"/></svg></button>` : '';
  return `<div class="card-h"><div class="ttl"><h3><span class="h3t">${esc(title)}</span>${x}</h3><span class="ttl-s">${esc(sub)}</span></div>${ctl ? `<span class="pctl">${ctl}</span>` : ''}</div>`;
}
/** a segmented control: data-seg names it inside the card; options [value, label]; disabled options with a reason */
export function SEG(key: string, label: string, opts: [string | number, string][], on: string | number, dis: Record<string, string> = {}) {
  return `${label ? `<span class="plab">${esc(label)}</span>` : ''}<div class="seg sm" data-seg="${esc(key)}" role="group" aria-label="${esc(label || key)}">${opts.map(([v, l]) => {
    const sel = String(v) === String(on), d = dis[String(v)];
    return `<button type="button" data-v="${esc(v)}" class="${sel ? 'on' : ''}" aria-pressed="${sel}"${d ? ` disabled title="${esc(d)}"` : ''}>${esc(l)}</button>`;
  }).join('')}</div>`;
}
/** the click of a segmented control's option (a Custom option is handled by its own popover, `custom`) */
export function onSeg(el: HTMLElement, key: string, fn: (v: string, b: HTMLElement, e: MouseEvent) => void) {
  $$(`[data-seg="${key}"] button`, el).forEach(b => (b.onclick = e => fn(b.dataset.v as string, b, e)));
}
/** a select of sectors (names shown short) */
export const SELECT = (key: string, label: string, opts: [string, string][], on: string, dis: Record<string, string> = {}) =>
  `<select class="sx-sel" data-sel="${esc(key)}" aria-label="${esc(label)}">${opts.map(([v, l]) => `<option value="${esc(v)}"${v === on ? ' selected' : ''}${dis[v] ? ` disabled title="${esc(dis[v])}"` : ''}>${esc(l)}</option>`).join('')}</select>`;

/** a legend text known only once the chart is drawn (labels hidden, dots beyond the axis): the card prints the one it
    drew last before it draws, so the legend's height, and the chart's box with it, does not change after the draw
    (check 1 BD-1, RP-5: a legend that wrapped after the draw pushed the axis title onto the card's border) */
export const footNow = (el: HTMLElement, fallback: string) => esc(el.dataset.foot ?? fallback);
export function footSet(el: HTMLElement, text: string) {
  const f = $('[data-foot]', el); if (!f) return;
  el.dataset.foot = text; if (f.textContent !== text) f.textContent = text;
}
/** a dash with its reason, read by hover, by a tap and by a screen reader (check 1 BD-11, RP-8: no "—" without a reason) */
export const na = (why: string) => `<span class="na" data-tip="${esc(esc(why))}" role="img" aria-label="${esc(why)}">—</span>`;

/* ---------- Esc closes the newest popover first (check 1 OR-4): every popover a card opens registers its closer ---------- */
const escStack: (() => boolean)[] = [];
/** registers a closer (it returns whether it closed something); the returned function removes it */
export function escPush(close: () => boolean) { escStack.push(close); return () => { const i = escStack.indexOf(close); if (i >= 0) escStack.splice(i, 1) } }
/** closes the newest open popover; false when none was open */
export function escTop(): boolean {
  while (escStack.length) { const f = escStack.pop() as () => boolean; if (f()) return true }
  return false;
}

/* ---------- scroll cues (check 1 OR-2, BD-4, MX-2, MX-3): a scroller with more content past an edge fades at that edge ---------- */
const CUED = '.tbl-wrap,.hm-s,.pmg-s,.rsw-s,.fw-tw,.sx-tabs,.bxp,.cmp';
function cue(x: HTMLElement) {
  const r = x.scrollLeft + x.clientWidth < x.scrollWidth - 1, l = x.scrollLeft > 1, b = x.scrollTop + x.clientHeight < x.scrollHeight - 1;
  // a scroller with a sticky first column shows its left cue as that column's shadow (a fade would fade the column)
  x.classList.toggle('xs-r', r); x.classList.toggle('xs-l', l && !x.dataset.sticky); x.classList.toggle('xs-sl', l && !!x.dataset.sticky); x.classList.toggle('xs-b', b);
}
/** marks every scroller inside `root` (and root itself) and keeps its cue as it scrolls */
export function scrollCues(root: ParentNode) {
  const all = [...(root instanceof HTMLElement && root.matches(CUED) ? [root] : []), ...$$<HTMLElement>(CUED, root)];
  for (const x of all) { cue(x); if (!x.dataset.cueOn) { x.dataset.cueOn = '1'; x.addEventListener('scroll', () => cue(x), { passive: true }) } }
}

/* ---------- colour scales (logic.js: alpha = min(1, |v| / cap) x 0.72 + 0.06; white text over 0.5) ---------- */
export function heat(v: number | null | undefined, cap: number, centre = 0): string {
  if (v == null || !Number.isFinite(v)) return '';
  const k = Math.min(1, Math.abs(v - centre) / (cap || 1)) * 0.72 + 0.06;
  return `background:color-mix(in srgb,var(${v >= centre ? '--up' : '--down'}) ${(k * 100).toFixed(1)}%,transparent);color:${k > 0.5 ? 'var(--sx-hot)' : 'var(--text)'}`;
}

/* ---------- the shared multi-column sort (logic.js L563-576) ---------- */
export function msTh(SK: M.Level[], key: string, lab: string, cl = '', tip = '', o: { def?: M.Level | null; txt?: boolean; tag?: string } = {}) {
  const ix = SK.findIndex(x => x[0] === key), on = ix >= 0, df = !SK.length && !!o.def && o.def[0] === key;
  const dir = on ? SK[ix][1] : df ? (o.def as M.Level)[1] : 0, up = M.ascending(dir, !!o.txt), tg = o.tag || 'th';
  return `<${tg} class="${cl}${on ? ' on' : ''}${df ? ' df' : ''}" data-k="${esc(key)}" role="button" tabindex="0" title="${esc((tip ? tip + DOT : '') + W.sort.tip)}" aria-sort="${on || df ? (up ? 'ascending' : 'descending') : 'none'}">${lab}${on || df ? `<span class="sk">${up ? '↑' : '↓'}${SK.length > 1 ? `<sup>${ix + 1}</sup>` : ''}</span>` : ''}</${tg}>`;
}
/** "Sorted by X ↓, then Y ↑ · Clear sort" with 2 levels or more; the default order named when it has no column (N07) */
export function msNote(SK: M.Level[], LAB: Record<string, string>, txt: Record<string, any> = {}, defNote = '') {
  if (SK.length > 1) return `<span class="mss">${esc(W.sort.by(SK.map(([k, d]) => `${LAB[k] || k} ${M.ascending(d, !!txt[k]) ? '↑' : '↓'}`)))} · <button class="rsr" type="button">${esc(W.sort.clear)}</button></span>`;
  return !SK.length && defNote ? `<span class="mss">${esc(defNote)}</span>` : '';
}
export function msWire(root: HTMLElement, SK: M.Level[], redraw: () => void, def: M.Level | null = null, sel = '[data-k][role=button]') {
  $$(sel, root).forEach(t => {
    const go = () => { M.msClick(SK, t.dataset.k as string, def); redraw() };
    t.onclick = e => { e.stopPropagation(); go() };
    t.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); go() } };
  });
  $$('.mss .rsr', root).forEach(b => (b.onclick = e => { e.stopPropagation(); SK.length = 0; redraw() }));
}

/* ---------- the floating read-out (a chart's hover, a cell's hint): one element, surface card, at the pointer ---------- */
let tipEl: HTMLDivElement | null = null;
export function tipShow(html: string, e: { clientX: number; clientY: number }) {
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'ctip sx-tip'; tipEl.setAttribute('role', 'tooltip'); tipEl.hidden = true; document.body.appendChild(tipEl) }
  if (tipEl.dataset.h !== html) { tipEl.innerHTML = html; tipEl.dataset.h = html }
  tipEl.hidden = false;
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tipEl.style.left = Math.max(4, x) + 'px'; tipEl.style.top = Math.max(4, y) + 'px';
}
export const tipHide = () => { if (tipEl) tipEl.hidden = true };
/** elements with data-tip show it on hover; on touch a tap shows it and a tap elsewhere hides it. Charts that draw their own
    read-out mark their box with data-own-tip so the pointer moving over them does not hide it */
export function initTips() {
  document.addEventListener('mousemove', e => {
    const t = (e.target as Element)?.closest?.('[data-tip]') as HTMLElement | null;
    if (t) tipShow(t.dataset.tip as string, e);
    else if (!(e.target as Element)?.closest?.('[data-own-tip]')) tipHide();
  });
  document.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse') return;
    const t = (e.target as Element)?.closest?.('[data-tip]') as HTMLElement | null;
    if (t) tipShow(t.dataset.tip as string, e); else if (!(e.target as Element)?.closest?.('[data-own-tip]')) tipHide();
  });
  document.addEventListener('scroll', tipHide, true);
}

/** the date of the hovered point, in a dark tag on the x axis under the hover line (logic.js L1642) */
export function xTag(line: SVGLineElement, label: string) {
  const sv = line.ownerSVGElement; if (!sv) return;
  let g = line.nextElementSibling as SVGGElement | null;
  if (!g || !g.classList.contains('xtg')) {
    g = document.createElementNS('http://www.w3.org/2000/svg', 'g'); g.setAttribute('class', 'xtg');
    g.innerHTML = '<rect rx="3" height="18"/><text text-anchor="middle"/>'; line.after(g);
  }
  const t = g.lastChild as SVGTextElement, r = g.firstChild as SVGRectElement, x = +(line.getAttribute('x1') || 0), y = +(line.getAttribute('y2') || 0);
  const Wd = +(sv.getAttribute('width') || 0) || sv.getBoundingClientRect().width;
  t.textContent = label;
  const w = (t.getComputedTextLength ? t.getComputedTextLength() : 80) + 14, lx = Math.max(0, Math.min(Wd - w, x - w / 2));
  r.setAttribute('x', String(lx)); r.setAttribute('y', String(y + 2)); r.setAttribute('width', String(w));
  t.setAttribute('x', String(lx + w / 2)); t.setAttribute('y', String(y + 15));
  g.removeAttribute('display');
}
export const xHide = (line: SVGLineElement | null) => { if (!line) return; line.setAttribute('display', 'none'); const g = line.nextElementSibling; if (g?.classList.contains('xtg')) g.setAttribute('display', 'none') };
export const xShow = (line: SVGLineElement, x: number) => { line.setAttribute('x1', String(x)); line.setAttribute('x2', String(x)); line.removeAttribute('display') };

/* ---------- canvas text width (label placement) ---------- */
const ctx2d = typeof document !== 'undefined' ? document.createElement('canvas').getContext('2d') : null;
export const textW = (t: string, f = '600 11px Inter, sans-serif') => { if (!ctx2d) return t.length * 6.2; ctx2d.font = f; return ctx2d.measureText(t).width };

/* ---------- the Custom range popover: one element, placed under the Custom button that opened it ---------- */
let pop: HTMLDivElement | null = null, popFor: { btn: HTMLElement; apply: (r: M.Range) => void; check: (a: string, b: string) => M.RangeCheck; single?: boolean } | null = null;
const closeOut = (e: Event) => { if (pop && !pop.hidden && !pop.contains(e.target as Node) && e.target !== popFor?.btn && !popFor?.btn.contains(e.target as Node)) closeRange() };
export function closeRange(focus = false) {
  if (!pop || pop.hidden) return;
  pop.hidden = true; popFor?.btn.setAttribute('aria-expanded', 'false');
  if (focus) popFor?.btn.focus();
  document.removeEventListener('pointerdown', closeOut, true);
  popFor = null;
}
/** opens the popover for `btn`. `single`: one date (Rank change's compare date). `cur`: the range shown first */
export function openRange(btn: HTMLElement, o: { title: string; cur: M.Range; min: string; max: string; note?: string; single?: boolean; check: (a: string, b: string) => M.RangeCheck; apply: (r: M.Range) => void }) {
  if (popFor?.btn === btn && pop && !pop.hidden) { closeRange(true); return }
  if (!pop) {
    pop = document.createElement('div'); pop.className = 'pop sx-rpop'; pop.setAttribute('role', 'dialog'); pop.hidden = true; document.body.appendChild(pop);
    pop.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeRange(true) } else if (e.key === 'Enter' && (e.target as HTMLElement).tagName === 'INPUT') { e.preventDefault(); apply() } });
  }
  closeRange();
  popFor = { btn, apply: o.apply, check: o.check, single: o.single };
  pop.setAttribute('aria-label', o.title);
  pop.innerHTML = `<div class="ph"><b>${esc(o.title)}</b></div><div class="rp-f${o.single ? ' one' : ''}">${o.single ? '' : `<label>${esc(W.range.from)}<input type="date" data-r="a" min="${o.min}" max="${o.max}" value="${o.cur.a}"></label>`}<label>${esc(o.single ? W.range.compare : W.range.to)}<input type="date" data-r="b" min="${o.min}" max="${o.max}" value="${o.cur.b}"></label></div>`
    + `<div class="rp-n" aria-live="polite"></div>${o.note ? `<div class="rp-x">${esc(o.note)}</div>` : ''}<div class="btns"><button type="button" class="btn sm" data-r="cancel">${esc(W.range.cancel)}</button><button type="button" class="btn sm primary" data-r="apply">${esc(W.range.apply)}</button></div>`;
  pop.hidden = false; btn.setAttribute('aria-haspopup', 'dialog'); btn.setAttribute('aria-expanded', 'true');
  const b = btn.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight, G = 8;
  pop.style.left = Math.max(G, Math.min(innerWidth - w - G, b.right - w)) + 'px';
  pop.style.top = Math.max(G, b.bottom + 6 + h > innerHeight - G ? b.top - h - 6 : b.bottom + 6) + 'px';
  $$('input', pop).forEach(i => (i.oninput = check));
  ($('[data-r=cancel]', pop) as HTMLElement).onclick = () => closeRange(true);
  ($('[data-r=apply]', pop) as HTMLElement).onclick = apply;
  check();
  if (!matchMedia('(pointer: coarse)').matches) (($('input', pop) as HTMLInputElement)).focus();
  setTimeout(() => document.addEventListener('pointerdown', closeOut, true));
}
function vals() { const a = $<HTMLInputElement>('[data-r=a]', pop as HTMLElement)?.value, b = $<HTMLInputElement>('[data-r=b]', pop as HTMLElement).value; return { a: popFor?.single ? b : a, b } }
function check(): M.RangeCheck | null {
  if (!pop || !popFor) return null;
  const v = vals(), r = popFor.check(v.a as string, v.b), n = $('.rp-n', pop);
  n.textContent = r.msg; n.classList.toggle('err', !r.ok);
  ($('[data-r=apply]', pop) as HTMLButtonElement).disabled = !r.ok;
  $$('input', pop).forEach(i => i.classList.toggle('bad', !r.ok));
  return r;
}
function apply() {
  const r = check(); if (!r || !r.ok || !popFor) return;
  const v = vals(), fn = popFor.apply;
  closeRange(true); fn({ a: v.a as string, b: v.b });
}

/* ---------- a small popover over a chart: a stock's figures and "Open in Terminal" (the Overview's tile popover) ---------- */
/** opens it at (x, y) inside `box`; Esc closes it (check 1 OR-4) and calls `onClose`, then the focus returns to `from` */
export function stockPop(box: HTMLElement, x: number, y: number, html: string, o: { onClose?: () => void; from?: HTMLElement | SVGElement | null } = {}) {
  let p = $('.sx-spop', box) as HTMLElement | null;
  if (!p) { p = document.createElement('div'); p.className = 'pop sx-spop'; p.setAttribute('role', 'dialog'); box.appendChild(p) }
  p.innerHTML = html; p.hidden = false;
  const el = p, off = escPush(() => {
    if (!el.isConnected || el.hidden) return false;
    el.hidden = true; off(); o.onClose?.();
    (o.from as HTMLElement | null)?.focus?.({ preventScroll: true });
    return true;
  });
  const W2 = box.clientWidth, H2 = box.clientHeight, pw = p.offsetWidth, ph = p.offsetHeight, G = 4;
  let top = y + 12; if (top + ph > H2 - G) top = y - ph - 12;
  p.style.left = Math.max(G, Math.min(x - pw / 2, W2 - pw - G)) + 'px';
  p.style.top = Math.max(G, Math.min(top, H2 - ph - G)) + 'px';
  return p;
}
