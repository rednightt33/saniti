/* EXEC-SCREENER-V21 layout: the "Add column" picker (reference layout.js 965-1000), the UI only. Which columns
   exist, their values and their loading all come from extra-columns.ts (availableColumns, shownColumns, setColumns);
   nothing is invented here: with no column offered the picker says so. A column that cannot be offered now is listed
   greyed with its reason. Removing a column from its header (×) goes through setColumns too. */
import { esc, unitWords } from '../format.ts';
import { availableColumns, setColumns, shownColumns } from '../extra-columns.ts';

let q = '';
const pop = () => document.getElementById('colPop')!;
const btn = () => document.querySelector('#resTools [data-act="cols"]') as HTMLElement | null;

function render() {
  const all = availableColumns(), shown = shownColumns(), ql = q.trim().toLowerCase();
  const rows = all.filter(c => !ql || `${c.label} ${c.short} ${c.group}`.toLowerCase().includes(ql));
  const groups = [...new Set(rows.map(c => c.group))];
  const list = !all.length ? `<p class="colpop-e">No extra column can be added yet.</p>`
    : !rows.length ? `<p class="colpop-e">No column matches “${esc(q)}”.</p>`
    : groups.map(g => `<div class="colpop-g" role="presentation">${esc(g)}</div>` + rows.filter(c => c.group === g).map(c =>
      `<label class="colpop-i" ${c.unavailable ? `title="${esc(c.unavailable)}"` : ''}><input type="checkbox" data-col="${esc(c.id)}" ${shown.includes(c.id) ? 'checked' : ''} ${c.unavailable ? 'disabled' : ''}><span>${esc(c.label)}</span><small>${esc(c.unavailable ? 'not available' : c.paramText || unitWords(c.format))}</small></label>`).join('')).join('');
  pop().innerHTML = `<div class="colpop-h"><b>Columns</b><span>${shown.length} added</span>${shown.length ? '<button type="button" class="link" data-colclear>Remove all</button>' : ''}</div>
    ${all.length ? `<label class="searchbox"><svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6"/><path d="m16 16 4 4"/></svg><input data-colq placeholder="Search columns" aria-label="Search columns" value="${esc(q)}" autocomplete="off"></label>` : ''}<div class="colpop-l" role="group" aria-label="Columns you can add">${list}</div>`;
}
function place() {
  const b = btn(), p = pop(); if (!b || p.hidden) return;
  const r = b.getBoundingClientRect();
  p.style.left = Math.max(8, Math.min(r.right - p.offsetWidth, innerWidth - p.offsetWidth - 8)) + 'px';
  // above the button when there is room (the button sits in the table footer), else below
  const above = r.top - p.offsetHeight - 8;
  p.style.top = (above >= 8 ? above : Math.min(innerHeight - p.offsetHeight - 8, r.bottom + 8)) + 'px';
}
export function openColumns() {
  const p = pop(); render(); p.hidden = false; place();
  btn()?.setAttribute('aria-expanded', 'true');
  ((p.querySelector('[data-colq]') || p.querySelector('input,button')) as HTMLElement | null)?.focus();
}
export function closeColumns(restore = true) {
  const p = pop(); if (p.hidden) return;
  p.hidden = true; const b = btn(); b?.setAttribute('aria-expanded', 'false'); if (restore) b?.focus();
}
/** a column was added: bring its header into view */
function reveal(id: string) {
  requestAnimationFrame(() => {
    const th = document.querySelector(`#resPane th[data-xid="${CSS.escape(id)}"]`) as HTMLElement | null, w = th?.closest('.tbl-wrap') as HTMLElement | null;
    if (!th || !w) return;
    w.scrollTo({ left:th.offsetLeft - w.clientWidth / 2 + th.offsetWidth / 2, behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    th.classList.add('flash'); setTimeout(() => th.classList.remove('flash'), 1200);
  });
}
// setColumns draws the table itself: drawing it again here doubled the work of every add or remove (S4 D2)
export function removeColumn(id: string) { setColumns(shownColumns().filter(x => x !== id)); if (!pop().hidden) render() }

export function bindColumns() {
  const p = pop();
  document.getElementById('resTools')!.addEventListener('click', e => { if ((e.target as HTMLElement).closest('[data-act="cols"]')) { e.stopPropagation(); p.hidden ? openColumns() : closeColumns() } });
  document.getElementById('resPane')!.addEventListener('click', e => { const x = (e.target as HTMLElement).closest('[data-xdel]') as HTMLElement | null; if (x) { e.stopPropagation(); removeColumn(x.dataset.xdel!) } }, true);
  p.addEventListener('change', e => {
    const cb = (e.target as HTMLElement).closest('[data-col]') as HTMLInputElement | null; if (!cb) return;
    const id = cb.dataset.col!, cur = shownColumns();
    setColumns(cb.checked ? [...cur.filter(x => x !== id), id] : cur.filter(x => x !== id));
    const h = p.querySelector('.colpop-h span'); if (h) h.textContent = shownColumns().length + ' added';
    if (cb.checked) reveal(id);
  });
  p.addEventListener('click', e => { if ((e.target as HTMLElement).closest('[data-colclear]')) { setColumns([]); render(); (p.querySelector('input,button') as HTMLElement | null)?.focus() } });
  p.addEventListener('input', e => {
    const t = e.target as HTMLInputElement; if (!t.matches('[data-colq]')) return;
    q = t.value; const pos = t.selectionStart; render();
    const i = p.querySelector('[data-colq]') as HTMLInputElement; i.focus(); i.setSelectionRange(pos, pos);
  });
  p.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeColumns() } });
  document.addEventListener('pointerdown', e => { const t = e.target as HTMLElement; if (!p.hidden && !t.closest('#colPop,[data-act="cols"]')) closeColumns(false) });
  addEventListener('resize', place);
}
