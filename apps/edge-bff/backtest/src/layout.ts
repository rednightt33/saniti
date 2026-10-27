/* Layout modes of the reference (backtest.html section 5): the resizable builder (ml.bw), the hidden setup panel
   (body.bcol, ml.panel), results full screen (body.mainfs), the builder in focus mode (body.bx), the keyboard
   shortcuts [ (panel), F (full screen) and Escape, and the theme button. */
import { $, setPal } from './format.ts';
import { S } from './state.ts';
import { renderNav } from './builder.ts';
import { refreshSignals, themeChart } from './signals.ts';
import { renderTab } from './results/index.ts';
import { getEqc } from './results/overview.ts';

/* the builder's width: drag the edge, double-click to reset; kept in ml.bw */
export const initResize = () => { const app = document.querySelector('.app') as HTMLElement, h = $('bResize'); let bw = 396; try{ bw = +localStorage.getItem('ml.bw') || 396 }catch(e){}
  const set = (w: number) => { bw = Math.round(Math.max(320, Math.min(720, w))); app.style.setProperty('--bw', bw+'px') }; set(bw);
  h.addEventListener('pointerdown', (e: PointerEvent) => { if(BX()) return; e.preventDefault(); h.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const x0 = e.clientX, w0 = bw, mv = (ev: PointerEvent) => set(w0 + ev.clientX - x0), up = () => { h.removeEventListener('pointermove', mv); h.removeEventListener('pointerup', up); document.body.classList.remove('resizing'); try{ localStorage.setItem('ml.bw', String(bw)) }catch(e){} };
    h.addEventListener('pointermove', mv); h.addEventListener('pointerup', up) });
  h.addEventListener('dblclick', () => { set(396); try{ localStorage.setItem('ml.bw', '396') }catch(e){} });
};
/* layout modes: setup panel collapsed (bcol) and results full screen (mainfs) */
export const setPanel = (on: boolean) => { if(BX()) setExpanded(false); document.body.classList.toggle('bcol', !on); renderNav(); try{ localStorage.setItem('ml.panel', on?'1':'0') }catch(e){} requestAnimationFrame(() => { window.dispatchEvent(new Event('resize')); setTimeout(() => { const eqc = getEqc(); if(eqc) eqc.timeScale().fitContent() }, 60) }) };
export const setFS = (on: boolean) => { document.body.classList.toggle('mainfs', on); $('fsBtn').innerHTML = on ? '<svg class="ico" viewBox="0 0 24 24"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg><span>Exit full screen</span>' : '<svg class="ico" viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg><span>Full screen</span>'; window.dispatchEvent(new Event('resize')); setTimeout(() => { const eqc = getEqc(); if(eqc) eqc.timeScale().fitContent() }, 60) };
/* the full-screen button and the keyboard shortcuts (not while typing, not while the workspace is open) */
export const bindLayout = () => {
  $('fsBtn').onclick = () => setFS(!document.body.classList.contains('mainfs'));
  document.addEventListener('keydown', e => { const t = e.target as HTMLElement; if(t.closest && t.closest('input,select,textarea')) return; if(!$('ews').hidden) return;
    if(e.key==='Escape' && document.body.classList.contains('mainfs')){ setFS(false); e.stopImmediatePropagation() }
    else if(e.key==='f' || e.key==='F'){ setFS(!document.body.classList.contains('mainfs')) }
    else if(e.key==='['){ setPanel(document.body.classList.contains('bcol')) } }, true);
};
/** the setup panel as the user left it (ml.panel) */
export const restorePanel = () => { try{ if(localStorage.getItem('ml.panel')==='0') document.body.classList.add('bcol') }catch(e){} };
export const BX = () => document.body.classList.contains('bx');
export const setExpanded = (on: boolean) => { document.body.classList.toggle('bx', on); renderNav(); };
export const bindFocusEscape = () => document.addEventListener('keydown', e => { if(e.key==='Escape' && BX() && $('menu').hidden) setExpanded(false) });

/* ---- theme ---- */
export const bindTheme = () => { $('themeBtn').onclick = () => { const r = document.documentElement; r.dataset.theme = r.dataset.theme==='dark' ? 'light' : 'dark'; setPal(); themeChart(); refreshSignals(); if(S.result && S.tab==='overview') renderTab() } };
