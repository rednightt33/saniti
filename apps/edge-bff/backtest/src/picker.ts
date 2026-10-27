/* The portfolio's stock picker in step 1 (user N 2026-10-27, CONTRACT.md PF7; the one approved departure from the
   reference, which has a Universe select here): a search box (a combobox over the catalog's stocks), one select per
   catalog grouping whose chosen groups list their stocks with an add control, and the picked stocks as removable
   chips with their count against catalog.limits.max_portfolio_tickers. The looks are the reference's: its field,
   select, chip, pill, button and menu styles (backtest.css, the picker block beside them). The rules are picked.ts;
   every catalog string goes into the markup through esc(). */
import type { Grouping } from './core/contract.ts';
import { CAT } from './env.ts';
import { $, esc, ico, toast } from './format.ts';
import { S } from './state.ts';
import { addTickers, filtering, groupLabel, groupStocks, limitText, searchMatches, stocksOf, stocksText, type Stock } from './picked.ts';
import { markStale, renderNav, updateViewbar } from './builder.ts';
import { refreshSignals } from './signals.ts';

/** the note of a portfolio without a picked stock (the picker, the signal table) */
export const NO_STOCK = 'No stock picked yet. Search for a stock or filter by a group to add one.';
const PLUS = '<path d="M12 5v14M5 12h14"/>', CROSS = '<path d="M6 6l12 12M18 6 6 18"/>';
const max = () => CAT.limits.max_portfolio_tickers;
const stocks = () => stocksOf(CAT);
const nameOf = (s: Stock) => s.name || '';

/* a grouping's select: "Any <Grouping>", each value with its number of stocks, then the unclassified ones (never a
   value of their own: the catalog counts them apart, PF6). Option values are positions, so no catalog string goes
   into an attribute. */
const optionsOf = (g: Grouping) => {
  const cur = S.pick.f[g.key];
  return `<option value="" ${cur===undefined?'selected':''}>Any ${esc(groupLabel(g.key))}</option>`
    + g.values.map((v,k) => `<option value="v${k}" ${cur===v.value?'selected':''}>${esc(v.value)} (${v.tickers})</option>`).join('')
    + (g.unclassified > 0 ? `<option value="u" ${cur===null?'selected':''}>Unclassified (${g.unclassified})</option>` : '');
};

/** the picker's markup (builder.ts step 1, portfolio mode) */
export const pickerHtml = () => `<div class="row pk" id="pk">
      <div class="fld pk-s"><span class="pk-h"><span id="pkLbl">Stocks</span><span class="pill neu" id="pkN"></span></span>
        <input class="inp" id="pkQ" type="text" role="combobox" aria-labelledby="pkLbl" aria-describedby="pkN" aria-autocomplete="list" aria-expanded="false" aria-controls="pkList" autocomplete="off" spellcheck="false" placeholder="Search ticker or name" value="${esc(S.pick.q)}">
        <div class="pk-list" id="pkList" role="listbox" aria-label="Matching stocks" hidden></div></div>
      <div class="chips pk-chips" id="pkChips" role="list" aria-label="Picked stocks"></div>
      ${CAT.groupings.length ? `<div class="pk-f">${CAT.groupings.map((g,k) => `<label class="fld"><span>${esc(groupLabel(g.key))}</span><select class="sel" data-g="${k}">${optionsOf(g)}</select></label>`).join('')}</div><div class="pk-g" id="pkG"></div>` : ''}
    </div>`;

/* ---- what the picked stocks show: the count, the chips, the group list, the search's marks ---- */
const renderChips = (focus = -1) => {
  $('pkN').textContent = `${S.tickers.length} / ${max()}`;
  const names = new Map(stocks().map(s => [s.ticker, nameOf(s)]));
  $('pkChips').innerHTML = S.tickers.length ? S.tickers.map(t => `<span class="chip" role="listitem" title="${esc(names.get(t))}"><b>${esc(t)}</b><button data-pk-del="${esc(t)}" aria-label="Remove ${esc(t)}" title="Remove ${esc(t)}">${ico(CROSS)}</button></span>`).join('')
    : `<div class="exempty">${NO_STOCK}</div>`;
  $('pkChips').querySelectorAll('[data-pk-del]').forEach((b: HTMLButtonElement) => b.onclick = () => {
    const k = S.tickers.indexOf(b.dataset.pkDel); setPicked(S.tickers.filter(t => t !== b.dataset.pkDel), k) });
  // a chip removed from the keyboard hands the focus to the next chip, or to the search box when none is left
  if (focus >= 0) { const bs = $('pkChips').querySelectorAll('[data-pk-del]'); (bs[Math.min(focus, bs.length - 1)] as HTMLElement || $('pkQ')).focus() }
};
/* the visible part of the builder's scroll box: the most the group's list takes, so it never reaches past what can be
   seen of the panel */
const visibleHeight = () => { const r = $('builder').getBoundingClientRect(); return Math.min(r.bottom, innerHeight) - Math.max(r.top, 0) };
const renderGroup = () => {
  const el = $('pkG'); if (!el) return;
  if (!filtering(S.pick.f)) { el.innerHTML = ''; return }
  const list = groupStocks(stocks(), S.pick.f), open = list.filter(s => !S.tickers.includes(s.ticker)).length;
  const keep = (el.querySelector('.pk-rows') as HTMLElement)?.scrollTop || 0;
  el.innerHTML = `<div class="pk-gh"><span>${stocksText(list.length)} in this group</span>${list.length ? `<button class="btn sm" id="pkAll" ${open && S.tickers.length < max() ? '' : 'disabled'}>${ico(PLUS)}Add all</button>` : ''}</div>`
    + (list.length ? `<div class="pk-rows" role="list" aria-label="Stocks in this group">${list.map(s => `<div class="pk-row" role="listitem"><b>${esc(s.ticker)}</b><small>${esc(nameOf(s))}</small>${S.tickers.includes(s.ticker) ? '<span class="pill neu">Picked</span>' : `<button class="btn sm" data-pk-add="${esc(s.ticker)}" aria-label="Add ${esc(s.ticker)}">${ico(PLUS)}Add</button>`}</div>`).join('')}</div>`
      : `<div class="exempty">No stock in this group.</div>`);
  const rows = el.querySelector('.pk-rows') as HTMLElement;
  if (rows) { rows.style.maxHeight = Math.max(0, visibleHeight()) + 'px'; rows.scrollTop = keep }
  el.querySelectorAll('[data-pk-add]').forEach((b: HTMLButtonElement) => b.onclick = () => {
    const next = b.closest('.pk-row').nextElementSibling?.querySelector('[data-pk-add]')?.getAttribute('data-pk-add');
    add([b.dataset.pkAdd]);
    // the keyboard stays in the list: the next row's add control, else the group's
    if (document.activeElement === document.body) ((next && el.querySelector(`[data-pk-add="${CSS.escape(next)}"]`)) as HTMLElement || $('pkAll') || $('pkQ'))?.focus();
  });
  const all = $('pkAll'); if (all) all.onclick = () => add(list.map(s => s.ticker));
};

/* ---- the search (WAI-ARIA combobox with a listbox: aria-activedescendant moves over the options, the focus stays in
   the box) ---- */
let shown: Stock[] = [], active = -1;
const addable = (k: number) => k >= 0 && k < shown.length && !S.tickers.includes(shown[k].ticker);
const setActive = (k: number) => {
  active = addable(k) ? k : -1;
  const inp = $('pkQ');
  $('pkList').querySelectorAll('[role="option"]').forEach((o: HTMLElement, j: number) => o.setAttribute('aria-selected', String(j === active)));
  if (active >= 0) inp.setAttribute('aria-activedescendant', `pkO${active}`);
  else inp.removeAttribute('aria-activedescendant');
};
const option = (s: Stock, k: number) => { const on = S.tickers.includes(s.ticker);
  return `<div class="pk-opt" role="option" id="pkO${k}" data-i="${k}" aria-selected="false" aria-disabled="${on}"><b>${esc(s.ticker)}</b><small>${esc(nameOf(s))}</small>${on ? '<span class="pill neu">Picked</span>' : ''}</div>` };
const closeList = () => { $('pkList').hidden = true; $('pkQ').setAttribute('aria-expanded', 'false'); $('pkQ').removeAttribute('aria-activedescendant'); shown = []; active = -1 };
/* The list opens under the search box like the reference's add-condition menu (#menu: fixed to the window, under its
   button), so the builder's scroll box never cuts it, and shows the matches that fit between the search box and the
   bottom of the window (one option's height, measured), with a last line for how many more match. It follows the
   search box when the page scrolls or the window resizes (a phone's keyboard opening, the focus scrolling the box into
   view), and closes once the search box is out of the builder's sight. */
const place = () => { const r = $('pkQ').getBoundingClientRect(), box = $('pkList'); box.style.left = r.left + 'px'; box.style.width = r.width + 'px'; box.style.top = (r.bottom + 4) + 'px' };
const openList = (keepTicker: string | null = null) => {
  const box = $('pkList'), inp = $('pkQ'), all = searchMatches(stocks(), S.pick.q, Infinity);
  if (!S.pick.q.trim()) { closeList(); return }
  box.hidden = false; inp.setAttribute('aria-expanded', 'true'); place();
  let n = all.shown.length;
  if (n) {
    box.innerHTML = option(all.shown[0], 0);
    const one = (box.firstElementChild as HTMLElement).offsetHeight, room = innerHeight - box.getBoundingClientRect().top - (box.offsetHeight - one) - 8;
    const fit = Math.max(1, Math.floor(room / one));
    n = Math.min(n, all.total > fit ? Math.max(1, fit - 1) : fit);
  }
  shown = all.shown.slice(0, n);
  box.innerHTML = shown.map(option).join('') + (all.total > n ? `<div class="pk-more">${all.total - n} more · type more of the ticker or name</div>` : '')
    + (all.total ? '' : `<div class="pk-more">No stock matches “${esc(S.pick.q.trim())}”.</div>`);
  // the active option: the first stock that can be added, from the one that was active (just added) on
  const from = Math.max(0, keepTicker ? shown.findIndex(s => s.ticker === keepTicker) : 0), n2 = shown.length;
  setActive(Array.from({ length:n2 }, (_, j) => (from + j) % n2).find(addable) ?? -1);
};
const move = (d: number) => {
  if ($('pkList').hidden) { openList(); return }
  const n = shown.length; if (!n) return;
  for (let j = 1; j <= n; j++) { const k = ((active < 0 ? (d > 0 ? -1 : 0) : active) + d * j + n) % n; if (addable(k)) { setActive(k); return } }
};

/* ---- changes ---- */
/** add stocks while room remains (never past the limit; the rest is refused with the limit toast) */
function add(list: string[]) {
  const r = addTickers(S.tickers, list, max());
  if (r.refused) toast(limitText(max()));
  if (r.picked.length !== S.tickers.length) setPicked(r.picked);
}
/* the picked stocks changed: the run's settings did (markStale), the picker, the chart and table, the summary */
function setPicked(list: string[], focusChip = -1) {
  S.tickers = list;
  markStale(); renderChips(focusChip); renderGroup();
  if (!$('pkList').hidden) openList(shown[active]?.ticker ?? null);
  refreshSignals(); renderNav(); updateViewbar();
}

let followed = false;            // the page-wide listeners that move or close the list are added once
/** the picker's listeners and its first drawing (after builder.ts put pickerHtml() into the page) */
export function bindPicker() {
  const inp = $('pkQ') as HTMLInputElement; if (!inp) return;
  renderChips(); renderGroup();
  inp.oninput = () => { S.pick.q = inp.value; openList() };
  inp.onfocus = () => { if (S.pick.q.trim()) openList() };
  inp.onblur = () => closeList();
  if (!followed) {
    followed = true;
    const follow = () => {
      const box = $('pkList'); if (!box || box.hidden) return;
      const r = $('pkQ').getBoundingClientRect(), b = $('builder').getBoundingClientRect();
      if (r.bottom <= Math.max(b.top, 0) || r.top >= Math.min(b.bottom, innerHeight)) closeList();
      else openList(shown[active]?.ticker ?? null);
    };
    document.addEventListener('scroll', follow, { capture:true, passive:true }); addEventListener('resize', follow);
  }
  inp.onkeydown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); move(e.key === 'ArrowDown' ? 1 : -1) }
    else if (e.key === 'Enter') { e.preventDefault(); if (!$('pkList').hidden && addable(active)) add([shown[active].ticker]) }
    else if (e.key === 'Escape') {
      // the list closes first, then the text clears; with neither, Escape does what it does elsewhere (focus mode)
      if (!$('pkList').hidden) { closeList(); e.stopPropagation() }
      else if (inp.value) { inp.value = S.pick.q = ''; e.stopPropagation() }
    }
  };
  const box = $('pkList');
  box.onpointerdown = (e: PointerEvent) => e.preventDefault();        // the focus stays in the search box
  box.onclick = (e: MouseEvent) => { const o = (e.target as HTMLElement).closest('[role="option"]') as HTMLElement; if (o && addable(+o.dataset.i)) { setActive(+o.dataset.i); add([shown[active].ticker]) } };
  $('pk').querySelectorAll('[data-g]').forEach((sel: HTMLSelectElement) => sel.onchange = () => {
    const g = CAT.groupings[+sel.dataset.g], v = sel.value;
    if (v === '') delete S.pick.f[g.key]; else S.pick.f[g.key] = v === 'u' ? null : g.values[+v.slice(1)].value;
    renderGroup();
  });
}
