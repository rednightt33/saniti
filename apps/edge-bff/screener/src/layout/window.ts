/* EXEC-SCREENER-V21 layout: the Indicators window (reference layout.js 327-382) is movable (drag its header),
   resizable (drag the corner; keyboard: focus the corner and use the arrow keys, Shift for larger steps) and can be
   maximised (button or double-click on the header) or reset. Its place and size are kept per browser. The dialog
   keeps its focus trap and Escape (dialogs.ts); below 760 px it is a plain full dialog (CSS). */
import { store } from '../storage.ts';
import { LKEYS } from './prefs.ts';

interface Win { dx: number; dy: number; w: number | null; h: number | null; max: boolean }
const fresh = (): Win => ({ dx:0, dy:0, w:null, h:null, max:false });
let W: Win = { ...fresh(), ...store.get<Partial<Win>>(LKEYS.win, {}) };
const save = () => store.set(LKEYS.win, W);
const MIN_W = 640, MIN_H = 420;

function apply(d: HTMLElement) {
  d.classList.toggle('win-max', W.max);
  const max = d.querySelector('[data-winmax]');
  if (max) { max.setAttribute('aria-pressed', String(W.max)); max.setAttribute('aria-label', W.max ? 'Restore size' : 'Maximise'); (max as HTMLElement).title = W.max ? 'Restore size' : 'Maximise' }
  if (W.max) { d.style.transform = ''; d.style.width = ''; d.style.height = ''; return }
  d.style.transform = W.dx || W.dy ? `translate(${W.dx}px,${W.dy}px)` : '';
  d.style.width = W.w ? W.w + 'px' : ''; d.style.height = W.h ? W.h + 'px' : '';
}
/** keep at least 48 px of the window on screen */
function keepOnScreen(d: HTMLElement) {
  const r = d.getBoundingClientRect(), m = 48;
  if (r.right < m) W.dx += m - r.right; if (r.left > innerWidth - m) W.dx -= r.left - (innerWidth - m);
  if (r.top < 0) W.dy -= r.top; if (r.top > innerHeight - m) W.dy -= r.top - (innerHeight - m);
}

/** make the open `.dialog` a window: tools in its header, a corner grip */
export function makeWindow(d: HTMLElement) {
  if (d.dataset.win) return; d.dataset.win = '1';
  d.closest('.backdrop')?.classList.add('win-bd');
  const h = d.querySelector('.dialog-h') as HTMLElement | null, close = h?.querySelector('[data-close]');
  if (!h || !close) return;
  const tools = document.createElement('span'); tools.className = 'win-tools';
  tools.innerHTML = `<button type="button" class="iconbtn sm" data-winreset title="Reset size and position" aria-label="Reset size and position"><svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 3-6.2M4 4v4h4"/></svg></button><button type="button" class="iconbtn sm" data-winmax title="Maximise" aria-label="Maximise" aria-pressed="false"><svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>`;
  close.before(tools);
  h.title = 'Drag to move · double-click to maximise';
  apply(d);
  h.addEventListener('pointerdown', e => {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button,input,a') || W.max) return;
    e.preventDefault(); h.setPointerCapture(e.pointerId); d.classList.add('win-drag');
    const x0 = e.clientX - W.dx, y0 = e.clientY - W.dy;
    const mv = (ev: PointerEvent) => { W.dx = ev.clientX - x0; W.dy = ev.clientY - y0; apply(d) };
    const up = () => { h.removeEventListener('pointermove', mv); d.classList.remove('win-drag'); keepOnScreen(d); apply(d); save() };
    h.addEventListener('pointermove', mv); h.addEventListener('pointerup', up, { once:true }); h.addEventListener('pointercancel', up, { once:true });
  });
  h.addEventListener('dblclick', e => { if ((e.target as HTMLElement).closest('button,input')) return; W.max = !W.max; apply(d); save() });
  tools.addEventListener('click', e => {
    const t = e.target as HTMLElement;
    if (t.closest('[data-winmax]')) { W.max = !W.max; apply(d); save() }
    else if (t.closest('[data-winreset]')) { W = fresh(); apply(d); save() }
  });
  const g = document.createElement('span'); g.className = 'win-grip'; g.tabIndex = 0;
  g.setAttribute('role', 'separator'); g.setAttribute('aria-label', 'Resize window (arrow keys)'); g.title = 'Drag to resize';
  d.appendChild(g);
  g.addEventListener('pointerdown', e => {
    if (W.max) return; e.preventDefault(); g.setPointerCapture(e.pointerId); d.classList.add('win-drag');
    const r = d.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    const mv = (ev: PointerEvent) => { W.w = Math.round(Math.min(innerWidth - 16, Math.max(MIN_W, r.width + (ev.clientX - x0) * 2))); W.h = Math.round(Math.min(innerHeight - 16, Math.max(MIN_H, r.height + (ev.clientY - y0) * 2))); apply(d) };
    const up = () => { g.removeEventListener('pointermove', mv); d.classList.remove('win-drag'); save() };
    g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up, { once:true }); g.addEventListener('pointercancel', up, { once:true });
  });
  g.addEventListener('keydown', e => {
    const st = e.shiftKey ? 64 : 16, k = ({ ArrowRight:[st, 0], ArrowLeft:[-st, 0], ArrowDown:[0, st], ArrowUp:[0, -st] } as Record<string, number[]>)[e.key];
    if (!k || W.max) return; e.preventDefault(); e.stopPropagation();
    const r = d.getBoundingClientRect();
    W.w = Math.max(MIN_W, Math.min(innerWidth - 16, r.width + k[0])); W.h = Math.max(MIN_H, Math.min(innerHeight - 16, r.height + k[1])); apply(d); save();
  });
}
