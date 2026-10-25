/* Volume: eye = hide/show, X = remove from chart (re-add from the Indicators picker), reference lines 1657-1680;
   and the one undo / redo timeline for drawings and indicators (lines 1686-1701). */
import type { Ctx, HistEntry } from './context';
import { $, store } from './context';

export function initVolume(ctx: Ctx) {
  const volCtl = ctx.volCtl = { removed: store.get('ml.vol.removed') === '1', on: store.get('ml.vol.on') !== '0', apply:null as any, setRemoved:null as any, onChange:null as (() => void) | null, relabel:undefined as (() => void) | undefined };
  {
    const eye = $('volEye'), row = $('indRow'), x = $('volX');
    volCtl.apply = () => {
      const show = volCtl.on && !volCtl.removed;
      ctx.volumeSeries.applyOptions({ visible:show });
      eye.setAttribute('aria-pressed', String(volCtl.on)); eye.dataset.label = volCtl.on ? 'Hide' : 'Show'; eye.setAttribute('aria-label', (volCtl.on ? 'Hide' : 'Show') + ' Volume');
      row.classList.toggle('off', !volCtl.on); row.style.display = volCtl.removed ? 'none' : '';
    };
    volCtl.setRemoved = (r: boolean) => {
      volCtl.removed = r; if(!r) volCtl.on = true;
      store.set('ml.vol.removed', r ? '1' : '0'); store.set('ml.vol.on', volCtl.on ? '1' : '0');
      volCtl.apply(); if(volCtl.relabel) volCtl.relabel(); if(volCtl.onChange) volCtl.onChange();
    };
    eye.addEventListener('click', () => { volCtl.on = !volCtl.on; store.set('ml.vol.on', volCtl.on ? '1' : '0'); volCtl.apply() });
    x.addEventListener('click', () => volCtl.setRemoved(true));
    volCtl.apply();
  }

  /* shared surface between the Indicators picker, the right-click menu and the indicator engine (filled in by the engine) */
  ctx.Ind = { byName:{}, tips:{}, countOf:() => 0, count:() => 0, add:() => {}, removeAll:() => {}, onChange:null };

  /* ---- one undo / redo timeline for the chart (drawings and indicators): Ctrl/Cmd+Z, Ctrl+Shift+Z, Ctrl+Y ----
     Each entry is { undo(), redo() }; a new action clears the redo side. */
  ctx.Hist = (() => {
    const past: HistEntry[] = [], future: HistEntry[] = [];
    const run = (from: HistEntry[], to: HistEntry[], act: 'undo' | 'redo') => { const e = from.pop(); if(!e) return; e[act](); to.push(e) };
    document.addEventListener('keydown', (e: any) => {
      if(/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable || !(e.ctrlKey || e.metaKey) || e.altKey) return;
      if(document.querySelector('.idlg-back:not([hidden]), .gp-backdrop')) return;          // a dialog is open
      const k = e.key.toLowerCase();
      if(k === 'z'){ e.preventDefault(); e.shiftKey ? run(future, past, 'redo') : run(past, future, 'undo') }
      else if(k === 'y'){ e.preventDefault(); run(future, past, 'redo') }
    });
    return { push:(e: HistEntry) => { past.push(e); if(past.length > 200) past.shift(); future.length = 0 } };
  })();
}
