/* EXEC-TERMINAL-FULL (user 2026-10-27: "tambahkan opsi full screen di kotak hitam terlampir, ketika fullscreen maka
   tampilan akan seperti screenshot B"), live: a button right of Search markets. Full screen folds Statistics, Broker
   activity and the Flow Timeline (their own buttons do it, so widths, renders and the shared time range follow) and asks
   the browser for full screen; leaving (the button, Esc, the browser) opens again what was open. The folding is not
   remembered: the stored panel choices are put back as they were. When the browser refuses full screen (a frame
   without permission), the panels still fold and the button still brings them back. */
import { $, store } from '../app/context';

const KEYS = ['ml.stats.collapsed', 'ml.broker.collapsed', 'ml.flow.collapsed'];
const ICON_IN = '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 7.5v-4h4M12.5 3.5h4v4M16.5 12.5v4h-4M7.5 16.5h-4v-4"/></svg>';
const ICON_OUT = '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 3.5v4h-4M16.5 7.5h-4v-4M12.5 16.5v-4h4M3.5 12.5h4v4"/></svg>';

export function initFullscreen() {
  const search = $('symSearch') as HTMLElement | null;
  if (!search) return;
  const btn = document.createElement('button');
  btn.type = 'button'; btn.className = 'icon-btn ml-full-btn'; btn.id = 'fullBtn';
  search.after(btn);
  const ws = $('workspace') as HTMLElement, main = document.querySelector('.main-col') as HTMLElement;
  let on = false, was: { left: boolean; right: boolean; flow: boolean } | null = null, stored: (string | null)[] = [];
  const paint = () => {
    btn.innerHTML = on ? ICON_OUT : ICON_IN;
    const t = on ? 'Exit full screen' : 'Full screen';
    btn.title = t; btn.setAttribute('aria-label', t); btn.setAttribute('aria-pressed', String(on));
  };
  const keepStored = () => KEYS.forEach((k, i) => { const v = stored[i]; if (v === null) localStorage.removeItem(k); else store.set(k, v) });
  function enter() {
    if (on) return;
    on = true; stored = KEYS.map(k => store.get(k));
    was = { left: !ws.classList.contains('left-collapsed'), right: !ws.classList.contains('right-collapsed'), flow: !main.classList.contains('flow-collapsed') };
    if (was.left) $('statsCollapse').click();
    if (was.right) $('rpCollapse').click();
    if (was.flow) $('flowCollapse').click();
    try { keepStored() } catch { /* storage off: nothing was stored either */ }
    document.documentElement.classList.add('ml-full');
    const root = document.documentElement as any;
    if (!document.fullscreenElement && root.requestFullscreen) root.requestFullscreen().catch(() => { /* a frame without permission */ });
    paint();
  }
  function leave() {
    if (!on) return;
    on = false;
    if (was?.left) $('statsExpand').click();
    if (was?.right) $('rpExpand').click();
    if (was?.flow) $('flowCollapse').click();
    try { keepStored() } catch { /* as above */ }
    document.documentElement.classList.remove('ml-full');
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
    paint();
  }
  btn.addEventListener('click', () => on ? leave() : enter());
  // Esc or the browser's own control ends full screen: the panels come back too
  document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && on) leave() });
  paint();
}
