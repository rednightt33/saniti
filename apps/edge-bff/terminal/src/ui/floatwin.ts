/* EXEC-TERMINAL-POPOUT W1 (user 2026-10-27: "Jendela di dalam halaman terminal"): a window that floats over the
   terminal page. It moves by its title bar, resizes from its corner, comes to the front when pressed, and stays
   inside the page. Pinned, it can be neither moved nor resized and stays above the others. Its place, size and pin
   are remembered per window (`ml.win.<id>`). */
import { store } from '../app/context';

export interface WinTool { act: string; label: string; icon: string }
export interface WinOptions {
  id: string; title: string;
  w: number; h: number; x: number; y: number;           // the first place and size (a remembered one wins)
  minW?: number; minH?: number;
  tools?: WinTool[];                                    // extra title-bar buttons, before pin, dock and close
  onTool?: (act: string, btn: HTMLElement) => void;
  onDock?: () => void;                                  // "Back to panel"
  onClose?: () => void;                                 // after the window is gone (closed or docked)
  onResize?: () => void;                                // after its size changed
}
export interface Win { el: HTMLElement; body: HTMLElement; setSub(html: string): void; close(): void; front(): void }

const BASE_Z = 50, PIN_Z = 59, KEEP = 48;               // KEEP: px of the title bar that stays inside the page
const open = new Map<string, Win>();
let order: string[] = [];                               // back to front

const ICON = {
  pin:'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 2.5h4M7 2.5v4L4.5 9h7L9 6.5v-4M8 9v4.5"/></svg>',
  dock:'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4l8 8M12 6.5V12H6.5"/></svg>',
  close:'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>'
};

const restack = () => order.forEach((id, k) => {
  const w = open.get(id)!; w.el.style.zIndex = String(w.el.classList.contains('pinned') ? PIN_Z : BASE_Z + Math.min(k, 8));
});

export const isWinOpen = (id: string) => open.has(id);
export const getWin = (id: string) => open.get(id) || null;

/** the box kept inside the page: no larger than the page, the title bar reachable */
export function clampBox(b: { x: number; y: number; w: number; h: number }, vw: number, vh: number, minW = 320, minH = 200) {
  const w = Math.max(Math.min(minW, vw), Math.min(b.w, vw)), h = Math.max(Math.min(minH, vh), Math.min(b.h, vh));
  const x = Math.max(KEEP - w, Math.min(vw - KEEP, b.x)), y = Math.max(0, Math.min(vh - 32, b.y));
  return { x:Math.round(x), y:Math.round(y), w:Math.round(w), h:Math.round(h) };
}

export function openWin(o: WinOptions): Win {
  const had = open.get(o.id);
  if (had) { had.front(); return had }
  const minW = o.minW ?? 360, minH = o.minH ?? 240;
  let saved: any = {};
  try { saved = JSON.parse(store.get('ml.win.' + o.id) || '{}') || {} } catch { /* a broken entry is the first place */ }
  let box = clampBox({ x:saved.x ?? o.x, y:saved.y ?? o.y, w:saved.w ?? o.w, h:saved.h ?? o.h }, innerWidth, innerHeight, minW, minH);
  const el = document.createElement('section');
  el.className = 'fw'; el.dataset.win = o.id; el.setAttribute('role', 'region'); el.setAttribute('aria-label', o.title + ' window');
  const tools = (o.tools || []).map(t => `<button type="button" class="fw-btn" data-tool="${t.act}" title="${t.label}" aria-label="${t.label}">${t.icon}</button>`).join('');
  el.innerHTML = `<header class="fw-head"><strong>${o.title}</strong><span class="fw-sub"></span><span class="fw-tools">${tools}
      <button type="button" class="fw-btn" data-act="pin" aria-pressed="false">${ICON.pin}</button>
      ${o.onDock ? `<button type="button" class="fw-btn" data-act="dock" title="Back to panel" aria-label="Back to panel">${ICON.dock}</button>` : ''}
      <button type="button" class="fw-btn" data-act="close" title="Close" aria-label="Close ${o.title} window">${ICON.close}</button></span></header>
    <div class="fw-body"></div><div class="fw-grip" aria-hidden="true"></div>`;
  document.body.appendChild(el);
  const head = el.querySelector('.fw-head') as HTMLElement, body = el.querySelector('.fw-body') as HTMLElement;
  const pinBtn = el.querySelector('[data-act=pin]') as HTMLElement;
  const place = () => { el.style.left = box.x + 'px'; el.style.top = box.y + 'px'; el.style.width = box.w + 'px'; el.style.height = box.h + 'px' };
  const save = () => store.set('ml.win.' + o.id, JSON.stringify({ ...box, pin:el.classList.contains('pinned') }));
  const setPin = (p: boolean) => {
    el.classList.toggle('pinned', p); pinBtn.setAttribute('aria-pressed', String(p));
    const t = p ? 'Unpin (move and resize again)' : 'Pin (keep in place, on top)'; pinBtn.title = t; pinBtn.setAttribute('aria-label', t);
    restack();
  };
  const front = () => { order = [...order.filter(x => x !== o.id), o.id]; restack() };
  let gone = false;
  const close = () => {
    if (gone) return; gone = true;
    el.remove(); open.delete(o.id); order = order.filter(x => x !== o.id); removeEventListener('resize', onViewport); ro.disconnect();
    o.onClose?.();
  };
  const onViewport = () => { box = clampBox(box, innerWidth, innerHeight, minW, minH); place() };
  // the page reports a size change once the window has settled (a drag of the grip, a page resize)
  let lastW = 0, lastH = 0;
  const ro = new ResizeObserver(() => { const w = el.clientWidth, h = el.clientHeight; if (w !== lastW || h !== lastH) { lastW = w; lastH = h; o.onResize?.() } });

  el.addEventListener('pointerdown', front, true);
  /* drag (title bar) and resize (corner): listened on the document, so a fast pointer that leaves the window keeps it */
  const track = (e: PointerEvent, kind: 'move' | 'size') => {
    if (e.button !== 0 || el.classList.contains('pinned')) return;
    if (kind === 'move' && (e.target as HTMLElement).closest('button')) return;
    e.preventDefault();
    const x0 = e.clientX, y0 = e.clientY, b0 = { ...box };
    el.classList.add('fw-moving'); document.body.classList.add('fw-dragging');
    const mv = (ev: PointerEvent) => {
      const dx = ev.clientX - x0, dy = ev.clientY - y0;
      box = clampBox(kind === 'move' ? { ...b0, x:b0.x + dx, y:b0.y + dy } : { ...b0, w:Math.max(minW, b0.w + dx), h:Math.max(minH, b0.h + dy) }, innerWidth, innerHeight, minW, minH);
      place();
    };
    const up = () => {
      document.removeEventListener('pointermove', mv); document.removeEventListener('pointerup', up); document.removeEventListener('pointercancel', up);
      el.classList.remove('fw-moving'); document.body.classList.remove('fw-dragging'); save();
    };
    document.addEventListener('pointermove', mv); document.addEventListener('pointerup', up); document.addEventListener('pointercancel', up);
  };
  head.addEventListener('pointerdown', e => track(e, 'move'));
  (el.querySelector('.fw-grip') as HTMLElement).addEventListener('pointerdown', e => track(e, 'size'));
  head.addEventListener('click', e => {
    const b = (e.target as HTMLElement).closest('button') as HTMLElement | null;
    if (!b) return;
    if (b.dataset.act === 'pin') { setPin(!el.classList.contains('pinned')); save() }
    else if (b.dataset.act === 'dock') { close(); o.onDock?.() }
    else if (b.dataset.act === 'close') close();
    else if (b.dataset.tool) o.onTool?.(b.dataset.tool, b);
  });
  addEventListener('resize', onViewport);

  const win: Win = { el, body, close, front, setSub:html => { (el.querySelector('.fw-sub') as HTMLElement).innerHTML = html } };
  open.set(o.id, win);
  place(); setPin(!!saved.pin); front();
  ro.observe(el);
  return win;
}
