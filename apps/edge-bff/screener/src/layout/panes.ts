/* EXEC-SCREENER-V21 layout: the three panes (reference layout.js 24-139). The borders between Screen builder |
   Results | Display chart are dragged to resize (keyboard: arrows, Shift for larger steps, Home resets, Enter on the
   left border collapses), each with limits so the table keeps at least 480 px; the side panes collapse to a 40 px rail
   that names them and reopens them; the filter + presets bar folds to one summary line from its own rail. Widths and
   folds are kept per browser (prefs.ts). Below 900 px the page stacks and none of this applies (CSS). */
import { esc } from '../format.ts';
import { activeCards, S, ui } from '../state.ts';
import { layoutHooks, panes, savePanes, wide } from './prefs.ts';

const $ = (id: string) => document.getElementById(id);
const LIM = { lw:[220, 520], rw:[300, 640] } as const;
type Side = keyof typeof LIM;
const ico = (d: string) => `<svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;

let app: HTMLElement, cardC: HTMLElement, pv: HTMLElement;
let lRail: HTMLButtonElement, rRail: HTMLButtonElement, uRail: HTMLButtonElement;
const gutters: Record<Side, HTMLElement> = {} as Record<Side, HTMLElement>;

/** room a side pane may take: the table keeps 480 px beside the other pane */
function room(k: Side): number {
  const other = k === 'lw' ? (document.body.classList.contains('has-pv') ? pv.getBoundingClientRect().width : 40)
    : (document.body.classList.contains('lcol') ? 40 : cardC.getBoundingClientRect().width);
  return app.clientWidth - 80 - other - 480;
}
const clamp = (k: Side, v: number) => Math.round(Math.max(LIM[k][0], Math.min(LIM[k][1], room(k), v)));
const width = (k: Side) => (k === 'lw' ? cardC : pv).getBoundingClientRect().width;

export function applyPanes() {
  panes.lw != null ? app.style.setProperty('--lw', panes.lw + 'px') : app.style.removeProperty('--lw');
  panes.rw != null ? app.style.setProperty('--rw', panes.rw + 'px') : app.style.removeProperty('--rw');
  document.body.classList.toggle('lcol', panes.lcol && wide());
  document.body.classList.toggle('ucol', panes.ucol && wide());
  syncRails(); placeGutters();
}
function setWidth(k: Side, v: number | null) { panes[k] = v == null ? null : clamp(k, v); savePanes(); applyPanes(); dispatchEvent(new Event('resize')) }

/** collapse or reopen the builder pane (its header toggle, the rail, Enter on the border) */
export function setBuilderCollapsed(on: boolean, focus = true) {
  panes.lcol = on; savePanes(); applyPanes();
  if (!focus) return;
  if (on) lRail.focus();
  else (cardC.querySelector('[data-act="btoggle"]') as HTMLElement | null)?.focus();
}
/** fold or open the filter + presets bar */
export function setFiltersFolded(on: boolean) {
  panes.ucol = on; savePanes(); applyPanes();
  ui.renderUniverse();
  if (!on) (document.querySelector('#cardU .toolbar .qf:not([disabled]),#cardU .toolbar .btn') as HTMLElement | null)?.focus();
  else uRail.focus();
}
export const filtersFolded = () => panes.ucol && wide();

/** the rails' labels and counts, from the page state */
export function syncRails() {
  if (!lRail) return;
  const n = activeCards().length;
  lRail.innerHTML = `${ico('m9 6 6 6-6 6')}<span>Screen builder</span>${n ? `<b class="count">${n}</b>` : ''}`;
  lRail.title = 'Show the screen builder';
  lRail.setAttribute('aria-label', `Show the screen builder${n ? `, ${n} active condition${n > 1 ? 's' : ''}` : ''}`);
  rRail.innerHTML = `${ico('m15 6-6 6 6 6')}<span class="rail-t rail-l">Display chart</span>${S.pick ? `<span class="rail-l">${esc(S.pick)}</span>` : ''}`;
  rRail.title = 'Display chart';
  rRail.setAttribute('aria-label', `Display chart${S.pick ? ' for ' + S.pick : ''}`);
  const folded = panes.ucol, nf = document.querySelectorAll('#cardU #uChips .fchip:not(.fixed)').length + document.querySelectorAll('#cardU .toolbar .qf.on').length;
  uRail.innerHTML = `${ico(folded ? 'm6 9 6 6 6-6' : 'm18 15-6-6-6 6')}<span class="rail-t">Filters</span>${nf ? `<b class="count">${nf}</b>` : ''}`;
  uRail.title = folded ? 'Show filters and presets' : 'Fold filters and presets to one line';
  uRail.setAttribute('aria-label', (folded ? 'Show filters and presets' : 'Fold filters and presets') + (nf ? `, ${nf} active filter${nf > 1 ? 's' : ''}` : ''));
  uRail.setAttribute('aria-expanded', String(!folded));
}

const fixedPreview = () => getComputedStyle(pv).position === 'fixed';
function placeGutters() {
  if (!app) return;
  const showL = wide() && !document.body.classList.contains('lcol');
  const showR = wide() && document.body.classList.contains('has-pv') && !pv.hidden && !fixedPreview();
  gutters.lw.classList.toggle('on', showL); gutters.rw.classList.toggle('on', showR);
  const a = app.getBoundingClientRect(), gap = parseFloat(getComputedStyle(app).columnGap) || 12;
  const put = (g: HTMLElement, left: number, r: DOMRect) => { g.style.left = left + 'px'; g.style.top = (r.top - a.top) + 'px'; g.style.height = r.height + 'px'; g.setAttribute('aria-valuenow', String(Math.round(r.width))) };
  if (showL) { const r = cardC.getBoundingClientRect(); put(gutters.lw, r.right - a.left + gap / 2, r) }
  if (showR) { const r = pv.getBoundingClientRect(); put(gutters.rw, r.left - a.left - gap / 2, r) }
}
let placeFrame = 0;
export const schedulePlace = () => { if (!placeFrame) placeFrame = requestAnimationFrame(() => { placeFrame = 0; placeGutters() }) };

function makeGutter(k: Side, label: string): HTMLElement {
  const g = document.createElement('div');
  g.className = 'gutter'; g.dataset.k = k; g.tabIndex = 0;
  g.setAttribute('role', 'separator'); g.setAttribute('aria-orientation', 'vertical'); g.setAttribute('aria-label', label);
  g.setAttribute('aria-valuemin', String(LIM[k][0])); g.setAttribute('aria-valuemax', String(LIM[k][1]));
  g.title = label + ' · double-click to reset';
  g.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault(); g.setPointerCapture(e.pointerId);
    const x0 = e.clientX, w0 = width(k); g.classList.add('drag'); document.body.classList.add('resizing');
    const mv = (ev: PointerEvent) => { const dx = ev.clientX - x0; panes[k] = clamp(k, k === 'lw' ? w0 + dx : w0 - dx); applyPanes() };
    const up = () => { g.removeEventListener('pointermove', mv); g.classList.remove('drag'); document.body.classList.remove('resizing'); savePanes(); dispatchEvent(new Event('resize')) };
    g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up, { once:true }); g.addEventListener('pointercancel', up, { once:true });
  });
  g.addEventListener('dblclick', () => setWidth(k, null));
  g.addEventListener('keydown', e => {
    const step = e.shiftKey ? 64 : 16, dir = k === 'lw' ? 1 : -1;
    if (e.key === 'ArrowRight') { e.preventDefault(); setWidth(k, width(k) + step * dir) }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); setWidth(k, width(k) - step * dir) }
    else if (e.key === 'Home') { e.preventDefault(); setWidth(k, null) }
    else if (e.key === 'Enter' && k === 'lw') { e.preventDefault(); setBuilderCollapsed(true) }
  });
  app.appendChild(g);
  return g;
}

export function initPanes() {
  app = $('app')!; cardC = $('cardC')!; pv = $('preview')!;
  const rail = (id: string) => { const b = document.createElement('button'); b.type = 'button'; b.id = id; b.className = 'rail'; app.appendChild(b); return b };
  lRail = rail('lRail'); rRail = rail('rRail'); uRail = rail('uRail');
  uRail.setAttribute('aria-controls', 'cardU');
  lRail.addEventListener('click', () => setBuilderCollapsed(false));
  rRail.addEventListener('click', () => ui.togglePreview(true));
  uRail.addEventListener('click', () => setFiltersFolded(!panes.ucol));
  gutters.lw = makeGutter('lw', 'Resize the screen builder');
  gutters.rw = makeGutter('rw', 'Resize the chart panel');
  layoutHooks.collapseBuilder = () => { if (!wide()) return false; S.bOpen = true; setBuilderCollapsed(true); return true };
  const ro = new ResizeObserver(schedulePlace);
  for (const el of [app, cardC, pv]) ro.observe(el);
  addEventListener('resize', () => { applyPanes(); if (wide() && !S.bOpen) { S.bOpen = true; ui.renderConds() } });
  applyPanes();
}
