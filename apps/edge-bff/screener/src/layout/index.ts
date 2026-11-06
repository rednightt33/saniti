/* EXEC-SCREENER-V21: the "Type A three-panel v21" layout of the Screener (the user's design reference
   edge-screener-typeA-3panel-v21.html, its layout.js read for behaviour only). One entry, initLayout(), called once by
   app.ts bootPage after the page's own listeners are bound. The layout works on the page's own state (state.ts S,
   ctx) and renderers: the renderers call the hooks in prefs.ts at their end, so nothing observes the document and
   nothing polls. It sends no request of its own: the chart pane's first stock goes through ui.pickStock, the
   page's preview path (run lane rules in preview.ts / run.ts).
     panes.ts        pane borders, rails, the folded filter bar
     filters.ts      More filters group list and industry narrowing, Not available yet, popover resize
     table.ts        pinned columns, header drag to reorder, compact density
     columns.ts      the Add column picker (data: extra-columns.ts)
     header-edit.ts  parameters edited from a column header (through builder.ts onBuilderField)
     perf.ts         Stock vs IHSG axes and hover */
import { S, ui } from '../state.ts';
import { panelPrefs } from '../storage.ts';
import { toggleRow, renderConds } from '../builder.ts';
import { openAddCondition } from '../add-condition.ts';
import { bindUniverseLayout } from '../universe-ui.ts';
import { dialogOpen } from '../dialogs.ts';
import { layoutHooks, wide } from './prefs.ts';
import { initPanes, schedulePlace, setFiltersFolded, syncRails } from './panes.ts';
import { bindNa } from './filters.ts';
import { bindTableDrag, moveColumn } from './table.ts';
import { bindColumns } from './columns.ts';
import { bindHeaderEdit, placeEditor } from './header-edit.ts';
import { bindPerf } from './perf.ts';

const $ = (id: string) => document.getElementById(id)!;
const INTERACTIVE = 'button,a,input,select,textarea,label,summary,[role="button"],[role="tab"],[role="radio"],[tabindex]:not([tabindex="-1"]),.fchip,.pchip,.qf,.seg,.chip,.suggest,[data-act],[data-qf],[data-open],[data-uclear]';

/** the chart pane shows the top result until the user picks a stock (reference layout.js 1343-1345) */
let pickQueued = false;
function autoPick() {
  if (!S.preview || S.pick || pickQueued) return;
  pickQueued = true;
  setTimeout(() => {
    pickQueued = false;
    if (!S.preview || S.pick) return;
    const tr = $('resPane').querySelector('tr[data-tk]') as HTMLElement | null;
    if (tr) ui.pickStock(tr.dataset.tk!);
  }, 0);
}

/** near misses: an info mark beside the toggle with the definition in a tooltip (reference layout.js 141-158) */
function nearTip() {
  const tip = document.createElement('div'); tip.className = 'nm-tip'; tip.id = 'nmTip'; tip.setAttribute('role', 'tooltip'); tip.hidden = true;
  tip.innerHTML = '<b>Near misses</b> are stocks that pass all but one of the conditions the screen needs. They are shown when the screen needs at least 2 conditions, and are listed after the matches when the toggle is on.';
  document.body.appendChild(tip);
  const show = (b: HTMLElement) => {
    const r = b.getBoundingClientRect(); tip.hidden = false; const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 8)) + 'px';
    tip.style.top = (r.bottom + 8 + h > innerHeight - 8 ? Math.max(8, r.top - 8 - h) : r.bottom + 8) + 'px';
  };
  const tools = $('resTools');
  tools.addEventListener('pointerover', e => { const b = (e.target as HTMLElement).closest('.nm-info') as HTMLElement | null; b ? show(b) : (tip.hidden = true) });
  tools.addEventListener('pointerleave', () => { tip.hidden = true });
  tools.addEventListener('focusin', e => { const b = (e.target as HTMLElement).closest('.nm-info') as HTMLElement | null; b ? show(b) : (tip.hidden = true) });
  tools.addEventListener('focusout', () => { tip.hidden = true });
  tools.addEventListener('keydown', e => { if (e.key === 'Escape' && !tip.hidden) { e.stopPropagation(); tip.hidden = true } });
  addEventListener('scroll', () => { tip.hidden = true }, { capture:true, passive:true });
}

export function initLayout() {
  // the chart pane is open by default where it takes a column of its own (above 1100 px; below, it slides over the
  // table), until the user closes it (panel preference kept per browser)
  if (panelPrefs().preview === undefined && innerWidth > 1100) S.preview = true;
  initPanes();
  bindUniverseLayout(); bindNa();
  bindTableDrag($('resPane')); bindColumns(); bindHeaderEdit(); bindPerf(); nearTip();

  layoutHooks.afterConds = () => { syncRails(); schedulePlace() };
  layoutHooks.afterUniverse = () => schedulePlace();
  layoutHooks.afterDetails = () => syncRails();
  layoutHooks.afterResults = () => { syncRails(); placeEditor(); autoPick(); schedulePlace() };

  // builder pane: a click on a compact condition row (not on one of its controls) opens it to edit
  $('cardC').addEventListener('click', e => {
    if (!wide()) return;
    const t = e.target as HTMLElement, mc = t.closest('.mc[data-card]') as HTMLElement | null;
    if (!mc || t.closest('input,select,button,label,a,.sw,.seg,textarea')) return;
    toggleRow(mc.dataset.card!);
  });
  $('cardC').addEventListener('keydown', e => {
    const t = e.target as HTMLElement;
    if (wide() && t.matches?.('.mc[data-card]') && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); toggleRow(t.dataset.card!) }
  });
  // filter bar: a click on its empty space folds it (wide layout; text selection and controls keep their action)
  $('cardU').addEventListener('click', e => {
    if (!wide() || document.body.classList.contains('ucol')) return;
    if ((e.target as HTMLElement).closest(INTERACTIVE) || String(getSelection?.() || '').trim()) return;
    setFiltersFolded(true);
  });
  // results header: Alt+Shift+Left/Right moves the focused column (the keyboard way of the header drag)
  $('resPane').addEventListener('keydown', e => {
    if (!e.altKey || !e.shiftKey || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
    const th = (e.target as HTMLElement).closest('thead th') as HTMLElement | null; if (!th) return;
    e.preventDefault(); const key = (e.target as HTMLElement).dataset.sort;
    moveColumn(th, e.key === 'ArrowLeft' ? -1 : 1); ui.renderResults();
    if (key) (document.querySelector(`#resPane thead [data-sort="${CSS.escape(key)}"]`) as HTMLElement | null)?.focus();
  });
  // Alt+A opens Add a condition from anywhere (the physical key, so any keyboard layout works; EXEC-SCREENER-ADD)
  addEventListener('keydown', e => {
    if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && e.code === 'KeyA' && !dialogOpen()) { e.preventDefault(); openAddCondition() }
  });
  // crossing the 900 px line changes the builder (tabs, compact rows) and the filter bar (fold): draw them again
  const mq = matchMedia('(min-width: 901px)');
  mq.addEventListener('change', () => { renderConds(); ui.renderUniverse(); ui.renderResults() });
}
