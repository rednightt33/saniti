/* Card 1: the universe (the prototype's renderUniverse, scopeChips, QF, usec, renderPop, renderDrawer), on the wire
   universe of report 8.5. Kept: Sector and Industry (lists and counts from catalog.groupings, unclassified stocks
   counted apart, P15), Liquidity (ADV20 ≥ Rp B and price ≥ Rp; defaults 1 B and 50). Shown disabled with their reason
   (P11 a): Board, Market cap, Free float, Special notation (off, its chip removed). New (P4): the chips
   "Traded on E" and "No unadjusted price break", on by default, each naming how many tickers it hides. One rule for
   "Clear all" and both liquidity clears: back to the documented defaults (report 9.2).
   EXEC-SCREENER-STOCK-LISTS (user 2026-11-09, option 1A): Index and Group (konglomerasi) beside Sector and Industry, from
   catalog.stock_lists: each list a chip with its name and its stocks in the universe (the definition as its tooltip),
   click to include, again to exclude, again to clear, as the sectors; a search box narrows each list; the active ones
   are chips and round icons like the other filters. While the lists are not available the pickers show the reason and
   the Index quick filter is disabled with it; a list filter already set (a saved screen) stays on its chip to be
   removed, since a run with it is refused until the lists are back. */
import { UNIVERSE_DEFAULTS, type Grouping } from './core/contract.ts';
import { esc, nf, timeText } from './format.ts';
import { IC, ico } from './icons.ts';
import { ctx, definitionOf, freshUniverse, S, ui, type UState } from './state.ts';
import { chipNoBreak, chipTraded, LIST_TEXT, T } from './texts.ts';
import type { StockListEntry, StockListKind } from './core/contract.ts';
import { condText, displayUnit, newCard, optOf, type Card } from './forms.ts';
import { byGroup, OPLABEL } from './entries.ts';
import { hiddenCounts, universeView } from './universe-view.ts';
import { bindPopResize, dressPop, drawerClass, fnavHtml, FKEYS, shownFKeys, indScopeHtml, naButtonHtml, scopeIndustries, spy, summaryHtml, toggleNa, unsetClass, jumpTo, bindFilterDialog } from './layout/filters.ts';
import { filtersFolded, setFiltersFolded, syncRails } from './layout/panes.ts';
import { layoutHooks, wide } from './layout/prefs.ts';
import { afterPress } from './press.ts';
import { keepField } from './keep-field.ts';

const $ = (id: string) => document.getElementById(id)!;
const FRESH = freshUniverse();
let pendingFilter = false;

const grouping = (key: string): Grouping | undefined => ctx.catalog?.groupings.find(g => g.key === key);
const advB = (u: UState) => u.adv20_min_idr == null ? null : u.adv20_min_idr / 1e9;
const isDefaultLiq = (u: UState) => u.adv20_min_idr === UNIVERSE_DEFAULTS.adv20_min_idr && u.price_min === UNIVERSE_DEFAULTS.price_min;
const hidden = () => ctx.universe ? hiddenCounts(ctx.universe.rows) : null;

/* ---- EXEC-SCREENER-STOCK-LISTS: the index and group lists of the catalog ---------------------------------------- */
const LIST_KEY: Record<StockListKind, { in: 'indices_in' | 'groups_in'; out: 'indices_out' | 'groups_out' }> = {
  INDEX: { in:'indices_in', out:'indices_out' }, KONGLO: { in:'groups_in', out:'groups_out' },
};
/** the catalog's lists are available (an older worker's catalog has no block: not available, with T.noIndex) */
export const listsOn = () => ctx.catalog?.stock_lists?.availability === 'AVAILABLE';
/** why the lists are not available, as the catalog says it */
export const listsReason = () => ctx.catalog?.stock_lists?.reason || T.noIndex;
const listsOf = (kind: StockListKind): StockListEntry[] => listsOn() ? ctx.catalog!.stock_lists!.lists.filter(l => l.kind === kind) : [];
/** a list's name on the page (its code where the catalog does not name it: a saved screen's list that is gone) */
export const listName = (kind: StockListKind, code: string) => ctx.catalog?.stock_lists?.lists.find(l => l.kind === kind && l.code === code)?.name || code;
const listsSet = (u: UState) => !!(u.indices_in?.length || u.indices_out?.length || u.groups_in?.length || u.groups_out?.length);
/** what each picker's search box holds (kept across redraws; the chips it hides are hidden in place, no redraw) */
const listQuery: Record<StockListKind, string> = { INDEX:'', KONGLO:'' };
const listMatch = (l: StockListEntry, q: string) => !q || l.code.toLowerCase().includes(q) || l.name.toLowerCase().includes(q);
/** hide the chips of a picker that do not match its search (a chosen one always stays) */
function applyListQuery(root: ParentNode, kind: StockListKind) {
  const q = listQuery[kind].trim().toLowerCase();
  root.querySelectorAll(`.lchips[data-lkind="${kind}"]`).forEach(box => {
    let shown = 0;
    box.querySelectorAll<HTMLElement>('[data-list]').forEach(b => {
      const code = b.dataset.list!.slice(kind.length + 1), l = listsOf(kind).find(x => x.code === code);
      const ok = !l || b.classList.contains('on') || b.classList.contains('ex') || listMatch(l, q);
      b.hidden = !ok; if (ok) shown++;
    });
    const none = box.querySelector('.lnone') as HTMLElement | null; if (none) none.hidden = shown > 0;
  });
  root.querySelectorAll<HTMLInputElement>(`[data-lsearch="${kind}"]`).forEach(i => { if (i.value !== listQuery[kind]) i.value = listQuery[kind] });
}
/** one picker (Index or Group): the lists as chips, name and stocks in the universe, the definition as the tooltip */
function listSec(kind: StockListKind): string {
  const W = LIST_TEXT[kind], U = S.universe, k = LIST_KEY[kind], b = ctx.catalog?.stock_lists;
  if (!ctx.catalog) return `<div class="k">${esc(W.title)}</div><div class="note">${T.loadingIndicators}</div>`;
  const head = `<div class="k">${esc(W.title)} <small>· ${listsOn() ? LIST_TEXT.hint : 'no data'}</small></div>`;
  if (!listsOn()) return `${head}<div class="note">${esc(listsReason())}</div>`;
  const chips = listsOf(kind).map(l => {
    const st = U[k.in]?.includes(l.code) ? 'on' : U[k.out]?.includes(l.code) ? 'ex' : '';
    return `<button class="chip ${st}" data-list="${esc(kind + ':' + l.code)}" aria-pressed="${st ? 'true' : 'false'}" title="${esc(`${l.name}${l.name !== l.code ? ` (${l.code})` : ''}: ${l.definition} ${LIST_TEXT.count(l.tickers)}.`)}" aria-label="${esc(`${l.name}, ${LIST_TEXT.count(l.tickers)}: ${st === 'on' ? 'included' : st === 'ex' ? 'excluded' : 'no filter'}`)}">${esc(l.name)} <small>${nf(l.tickers)}</small></button>`;
  }).join('');
  const asOf = b?.as_of ? `<div class="note">${esc(LIST_TEXT.asOf(timeText(b.as_of)))}${kind === 'KONGLO' ? ' ' + esc(LIST_TEXT.groups) : ''}</div>` : kind === 'KONGLO' ? `<div class="note">${esc(LIST_TEXT.groups)}</div>` : '';
  return `${head}<input class="inp lsearch" type="search" data-lsearch="${kind}" placeholder="${esc(W.search)}" aria-label="${esc(W.search)}" value="${esc(listQuery[kind])}" autocomplete="off">
    <div class="chips lchips" data-lkind="${kind}">${chips}<span class="note lnone" hidden>${esc(W.none)}</span></div>${asOf}${kind === 'KONGLO' ? `<div class="note">${esc(LIST_TEXT.rule)}</div>` : ''}`;
}
/** the Index quick filter's value: the first chosen index or group, how many more, or All */
const listVal = (u: UState) => {
  const a = [...(u.indices_in || []).map(c => listName('INDEX', c)), ...(u.groups_in || []).map(c => listName('KONGLO', c))], x = (u.indices_out?.length || 0) + (u.groups_out?.length || 0);
  return a.length ? a[0] + (a.length > 1 ? ` +${a.length - 1}` : '') : x ? `All but ${x}` : 'All';
};

/** whether the universe differs from the documented defaults (Clear all is shown then) */
export function universeEdited(u = S.universe): boolean {
  return !!(u.sectors_in?.length || u.sectors_out?.length || u.industries_in?.length || u.industries_out?.length || listsSet(u) || u.include_unclassified
    || !isDefaultLiq(u) || u.min_history_bars != null || u.tickers?.length || u.filters.length || !u.traded_on_eval_date || !u.exclude_price_breaks);
}

/** the active-filter chips (scopeChips) */
/* user 2026-11-08 (the HTML of ten options, "Opsi 9"): each active filter is a small round icon on the bar (its short
   name, and how many stocks it hides as a count), the full wording in its tooltip; a click opens the list of every
   filter in full, with its remove (×) or Hide button. The bar stays one line. */
const ICON_OF: Record<string, string> = { sectors_in:'Sec', sectors_out:'−Sec', industries_in:'Ind', industries_out:'−Ind',
  indices_in:LIST_TEXT.INDEX.icon, indices_out:'−' + LIST_TEXT.INDEX.icon, groups_in:LIST_TEXT.KONGLO.icon, groups_out:'−' + LIST_TEXT.KONGLO.icon, include_unclassified:'Unc', adv:'Rp', price:'Px', min_history_bars:'Hist', tickers:'Tkr', traded:'Trd', breaks:'Brk' };
function scopeChips(): { html: string; removable: number; texts: string[] } {
  const U = S.universe, out: string[] = [], texts: string[] = [], icons: string[] = []; let n = 0;
  const icon = (key: string, full: string, count: string, cls = '') =>
    icons.push(`<button type="button" class="ficon ${cls}" data-flist title="${esc(full)}" aria-label="${esc(full)}: show the active filters">${esc(ICON_OF[key] || (key.startsWith('f') ? 'F' + (Number(key.slice(1)) + 1) : '·'))}${count ? `<em>${esc(count)}</em>` : ''}</button>`);
  const add = (label: string, val: string, clear: string | null, title = '', key = clear || '') => {
    if (clear && clear !== 'traded' && clear !== 'breaks') n++;     // the P4 chips are on by default: not an edit
    texts.push(`${label} ${val}`.trim());
    out.push(`<span class="fchip ${clear ? '' : 'fixed'}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)} <b>${esc(val)}</b>${clear ? `<button data-uclear="${clear}" title="Remove filter" aria-label="Remove ${esc(label)} filter">${ico(IC.x, 's')}</button>` : ''}</span>`);
    const hides = /^hides (\d+)$/.exec(val)?.[1] || '';
    icon(key, `${label} ${val}`.trim(), hides);
  };
  const list = (a: string[], one: string, many: string) => a.length > 2 ? `${a.length} ${many}` : a.join(', ') || one;
  if (U.sectors_in?.length) add('Sector', list(U.sectors_in, '', 'sectors'), 'sectors_in');
  if (U.sectors_out?.length) add('Excluding', list(U.sectors_out, '', 'sectors'), 'sectors_out');
  if (U.industries_in?.length) add('Industry', list(U.industries_in, '', 'industries'), 'industries_in');
  if (U.industries_out?.length) add('Excluding industry', list(U.industries_out, '', 'industries'), 'industries_out');
  // EXEC-SCREENER-STOCK-LISTS: by name (a code the catalog no longer has, by its code); while the lists are not
  // available the chip says so, so the filter a run refuses can be removed here
  const lists = (kind: StockListKind, codes: string[]) => list(codes.map(c => listName(kind, c)), '', LIST_TEXT[kind].many);
  const naTitle = listsOn() ? '' : `${listsReason()} Remove this filter to run the screen.`;
  if (U.indices_in?.length) add(LIST_TEXT.INDEX.title, lists('INDEX', U.indices_in), 'indices_in', naTitle);
  if (U.indices_out?.length) add(LIST_TEXT.INDEX.exclude, lists('INDEX', U.indices_out), 'indices_out', naTitle);
  if (U.groups_in?.length) add('Group', lists('KONGLO', U.groups_in), 'groups_in', naTitle);
  if (U.groups_out?.length) add(LIST_TEXT.KONGLO.exclude, lists('KONGLO', U.groups_out), 'groups_out', naTitle);
  if (U.include_unclassified) add('Keeps', 'unclassified', 'include_unclassified', 'Stocks without a sector or industry are kept by the include filters.');
  const ab = advB(U);
  if (ab != null) add('Avg value ≥', `Rp ${nf(ab, ab % 1 ? 1 : 0)}B`, U.adv20_min_idr === UNIVERSE_DEFAULTS.adv20_min_idr ? null : 'adv', 'Average daily traded value over 20 sessions (close × volume). Default Rp 1B.', 'adv');
  if (U.price_min != null) add('Price ≥', `Rp ${nf(U.price_min)}`, U.price_min === UNIVERSE_DEFAULTS.price_min ? null : 'price', 'Last close. Default Rp 50.', 'price');
  if (U.min_history_bars != null) add('History ≥', `${nf(U.min_history_bars)} sessions`, 'min_history_bars');
  if (U.tickers?.length) add('Tickers', U.tickers.length > 3 ? `${U.tickers.length} stocks` : U.tickers.join(', '), 'tickers');
  U.filters.forEach((f, i) => add('Filter', condText(ctx.byKey.get(f.entry || ''), f), 'f' + i));
  const h = hidden(), E = ctx.catalog?.data.evaluation_date || null;
  if (U.traded_on_eval_date) add(chipTraded(E), h ? `hides ${h.stale}` : '', 'traded', 'Hides stale stocks (no trade on the evaluation date). Remove to list them with a remark.');
  else { out.push(`<span class="fchip off" title="Stale stocks are listed with a remark">Stale shown <b>${h ? h.stale : ''}</b><button class="link" data-uhide="traded" style="margin-left:4px">Hide</button></span>`); icon('traded', `Stale stocks shown${h ? ` (${h.stale})` : ''}`, '', 'off') }
  if (U.exclude_price_breaks) add(chipNoBreak, h ? `hides ${h.breaks}` : '', 'breaks', 'Hides stocks whose price history crosses an unadjusted corporate action (temporary: until the price history is adjusted for corporate actions). Remove to list them with a remark.');
  else { out.push(`<span class="fchip off" title="Stocks with a price break are listed with a remark; their values are shown and marked">Price breaks shown <b>${h ? h.breaks : ''}</b><button class="link" data-uhide="breaks" style="margin-left:4px">Hide</button></span>`); icon('breaks', `Price breaks shown${h ? ` (${h.breaks})` : ''}`, '', 'off') }
  // the icons on the bar, and the full list they open (its open state survives a redraw)
  return { html:icons.join('') + `<div class="flist" id="uFlist" role="dialog" aria-label="Active filters"${flistOpen ? '' : ' hidden'}>${out.join('')}</div>`, removable:n, texts };
}

/** disabled: the reason the quick filter has no data (a function: the Index filter's depends on the catalog) */
type QFDef = [key: string, label: string, val: (u: UState) => string, on: (u: UState) => boolean, disabled?: string | (() => string | null)];
const disOf = (q: QFDef): string | null => typeof q[4] === 'function' ? q[4]() : q[4] ?? null;
const sectorVal = (u: UState) => u.sectors_in?.length ? u.sectors_in[0] + (u.sectors_in.length > 1 ? ` +${u.sectors_in.length - 1}` : '') : u.sectors_out?.length ? `All but ${u.sectors_out.length}` : u.industries_in?.length ? `${u.industries_in.length} industr${u.industries_in.length > 1 ? 'ies' : 'y'}` : 'All';
const QF: QFDef[] = [
  // EXEC-SCREENER-STOCK-LISTS: with data once the catalog carries the lists; disabled with the reason while it does not,
  // unless a list filter is set (it must stay reachable to be removed)
  ['index', 'Index', u => listsOn() || listsSet(u) ? listVal(u) : 'No data', listsSet, () => !ctx.catalog || listsOn() || listsSet(S.universe) ? null : listsReason()],
  ['sector', 'Sector', sectorVal, u => !!(u.sectors_in?.length || u.sectors_out?.length || u.industries_in?.length || u.industries_out?.length)],
  ['cap', 'Market Cap', () => 'No data', () => false, T.noCap],
  ['liq', 'Liquidity', u => `ADV ≥ Rp ${nf(advB(u) ?? 0, (advB(u) ?? 0) % 1 ? 1 : 0)}B`, u => !isDefaultLiq(u)],
  ['board', 'Board', () => 'No data', () => false, T.noBoard],
];

/** the prototype's market-cap buckets (CAPB, IDR T), shown disabled: market cap has no data (EXEC-MCAP) */
const CAPB: [string, string][] = [['Mega', '≥ 200T'], ['Big', '50–200T'], ['Mid', '10–50T'], ['Small', '1–10T'], ['Micro', '< 1T']];

const metricOpts = (cur: string | null) => {
  // a flow indicator is a condition (read at its own broker data date, with its setup), not a universe filter
  const list = byGroup(ctx.entries.filter(e => e.kind !== 'indicator' && !e.flow && e.opts.some(o => o.kind === 'value')));
  const groups = [...new Set(list.map(e => e.group))];
  return `${cur ? '' : '<option value="" selected disabled>Pick a metric…</option>'}` + groups.map(g => `<optgroup label="${esc(g)}">${list.filter(e => e.group === g)
    .map(e => `<option value="${esc(e.key)}" ${e.key === cur ? 'selected' : ''} ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${esc(e.label)}${e.available ? '' : ' — no data'}</option>`).join('')}</optgroup>`).join('');
};

/** one renderer per universe setting, shared by the popover and the drawer (usec) */
function usec(k: string): string {
  const U = S.universe;
  switch (k) {
    case 'index': return listSec('INDEX');
    case 'group': return listSec('KONGLO');
    case 'board': return `<div class="k">Listing board <small>· no data</small></div><div class="chips">${['Main', 'Development'].map(b => `<button class="chip" disabled title="${esc(T.noBoard)}">${b}</button>`).join('')}</div><div class="note">${esc(T.noBoard)}</div>`;
    case 'liq': {
      const ab = advB(U);
      return `<div class="k">Liquidity & price</div><div class="mini3"><label class="fld"><span>Avg value ≥ Rp B</span><input class="inp" type="number" step="any" min="0" data-u="adv" value="${ab ?? ''}" placeholder="any"></label><label class="fld"><span>Price ≥ Rp</span><input class="inp" type="number" min="0" data-u="price" value="${U.price_min ?? ''}" placeholder="any"></label><label class="fld" title="${esc(T.noFreeFloat)}"><span>Free float ≥ %</span><input class="inp" type="number" disabled placeholder="no data" aria-label="Free float: no data"></label></div>`;
    }
    case 'sector': {
      const g = grouping('sector');
      if (!g) return `<div class="k">Sectors</div><div class="note">${T.loadingIndicators}</div>`;
      return `<div class="k">Sectors <small>· click to include, again to exclude, again to clear</small></div><div class="chips">${g.values.map(v => { const st = U.sectors_in?.includes(v.value) ? 'on' : U.sectors_out?.includes(v.value) ? 'ex' : '';
          /* audit U23: the chip's state is read out (included, excluded, or no filter), not only shown by its colour */
          return `<button class="chip ${st}" data-sector="${esc(v.value)}" aria-pressed="${st ? 'true' : 'false'}" aria-label="${esc(v.value)}: ${st === 'on' ? 'included' : st === 'ex' ? 'excluded' : 'no filter'}">${esc(v.value)} <small>${nf(v.tickers)}</small></button>`; }).join('')}</div>
        ${g.unclassified ? `<label class="chk" title="An include filter (sector or industry) keeps a stock without that classification only when this is on; an exclude filter never drops it."><input type="checkbox" data-u="include_unclassified" ${U.include_unclassified ? 'checked' : ''}>Unclassified (${nf(g.unclassified)}): keep them with an include filter</label>` : ''}`;
    }
    // the prototype's buckets (CAPB) stay visible, disabled with the reason; their bounds are still open (P11)
    case 'cap': return `<div class="k">Market cap <small>· no data</small></div><div class="mini2"><input class="inp" disabled placeholder="Min" aria-label="Min market cap: no data"><input class="inp" disabled placeholder="Max" aria-label="Max market cap: no data"></div><div class="chips">${CAPB.map(([b, r]) => `<button class="chip" disabled title="${esc(`${b} (${r}, the prototype's bounds). ${T.noCap}`)}">${b}</button>`).join('')}</div><div class="note">${esc(T.noCap)}</div>`;
    case 'industry': {
      const g = grouping('industry');
      if (!g) return '';
      return `<div class="k">Industries <small>· ${U.industries_in?.length ? U.industries_in.length + ' selected' : 'all'}</small></div><div class="indlist">${g.values.map(v => `<label class="chk"><input type="checkbox" data-tog="industries_in" data-v="${esc(v.value)}" ${U.industries_in?.includes(v.value) ? 'checked' : ''}>${esc(v.value)} <span class="muted">${nf(v.tickers)}</span></label>`).join('')}${g.unclassified ? `<span class="note">Unclassified: ${nf(g.unclassified)}</span>` : ''}</div>`;
    }
    case 'metric': {
      const rows = U.filters.map((f, i) => filterRow(f, i)).join('');
      const pend = pendingFilter ? `<div class="frow"><select class="sel" data-fnew aria-label="Metric">${metricOpts(null)}</select><span></span><span></span><button class="iconbtn sm" data-act="fcancel" title="Cancel" aria-label="Cancel">${ico(IC.x, 's')}</button></div>` : '';
      return `<div class="k">Metric filters <small>· value tests applied before any condition</small></div>${rows}${pend}<div><button class="btn sm" data-act="addfund">${ico(IC.plus, 's')}Add metric filter</button></div>`;
    }
    case 'quality': {
      const h = hidden(), E = ctx.catalog?.data.evaluation_date || null;
      return `<div class="k">Stale stocks and price breaks</div>
        <label class="chk"><input type="checkbox" data-u="traded_on_eval_date" ${U.traded_on_eval_date ? 'checked' : ''}>${esc(chipTraded(E))}${h ? ` <span class="muted">hides ${h.stale}</span>` : ''}</label>
        <label class="chk"><input type="checkbox" data-u="exclude_price_breaks" ${U.exclude_price_breaks ? 'checked' : ''}>${esc(chipNoBreak)}${h ? ` <span class="muted">hides ${h.breaks}</span>` : ''}</label>
        <div class="note">Turned off, the hidden stocks are listed with a remark: the last trade date, or the corporate action and its ex-date. Their values are shown.</div>`;
    }
    case 'notation': return `<div class="k">Special notation <small>· no data</small></div><label class="chk" title="${esc(T.noNotation)}"><input type="checkbox" disabled>Exclude special-notation / FCA stocks</label><div class="note">${esc(T.noNotation)}</div>`;
  }
  return '';
}
function filterRow(f: Card, i: number): string {
  const e = ctx.byKey.get(f.entry || ''), opts = e ? e.opts.filter(o => o.kind === 'value') : [], o = e ? optOf(e, f) : undefined;
  const u = displayUnit(o?.unit);
  return `<div class="frow ${o?.between ? 'btwn' : ''}"><select class="sel" data-f="${i}" data-fk="key" aria-label="Metric">${metricOpts(f.entry)}</select><select class="sel" data-f="${i}" data-fk="op" aria-label="Operator">${opts.map(x => `<option value="${esc(x.key)}" ${x.key === f.opt ? 'selected' : ''}>${esc(OPLABEL[x.op] || x.op)}</option>`).join('')}</select><input class="inp" type="number" step="any" data-f="${i}" data-fk="value" value="${f.value}" aria-label="Value${u ? ' (' + u + ')' : ''}">${o?.between ? `<input class="inp" type="number" step="any" data-f="${i}" data-fk="value2" value="${f.value2}" aria-label="To">` : ''}<button class="iconbtn sm" data-fdel="${i}" title="Remove filter" aria-label="Remove filter">${ico(IC.x, 's')}</button></div>`;
}

/** "In universe X of N", computed in the page from /universe on every edit with the worker's own function (report
    9.2), so it follows an edit at once, before the run answers; a metric filter that needs a formula leaves it to the
    run's count */
export const uCountTxt = () => {
  const R = ctx.R, listed = ctx.universe?.rows.length ?? R?.listed ?? 0;
  if (!ctx.universe && !R) return `In universe <b>…</b>`;
  const v = ctx.universe ? universeView(ctx.universe.rows, definitionOf().universe) : null;
  // the run's count only while the table answers the page: a pending edit is counted by Screen now, not shown with the
  // previous screen's number (S2 data audit 1a; the same class as ERRORS M358)
  const n = v?.exact ? v.counts.eligible : R && !ctx.stale ? R.eligible : null;
  return `In universe <b>${n == null ? '…' : nf(n)}</b> of ${nf(listed)}`;
};
/** EXEC-SCREENER-V21 product decision 2026-11-06: screener data is daily; the timeframe is shown as "Daily" only,
    as a label (no 5m / 15m / 1h / 4h choice) */
const TF_STATIC = `<span class="qf qf-static" title="Screener data is daily: every condition is calculated on daily bars."><span>Timeframe</span><b>Daily</b></span>`;
const qfHtml = () => QF.map(q => [q[0], q[1], q[2], q[3], disOf(q)] as const).map(([k, label, val, on, dis]) => dis
  ? `<button class="qf" disabled title="${esc(dis)}" aria-disabled="true"><span>${label}</span><b>${esc(val(S.universe))}</b>${ico(IC.chev, 's')}</button>`
  : `<button class="qf ${on(S.universe) ? 'on' : ''} ${S.pop === k ? 'open' : ''}" data-qf="${k}" aria-expanded="${S.pop === k}" aria-haspopup="dialog" ${ctx.catalog ? '' : 'disabled title="Loading…"'}><span>${label}</span><b>${esc(val(S.universe))}</b>${ico(IC.chev, 's')}</button>${k === 'liq' ? TF_STATIC : ''}`).join('');

export function renderUniverse() {
  if (afterPress('universe', renderUniverse)) return;   // never under a pressed pointer (press.ts, ERRORS M357)
  const c = scopeChips(), n = c.removable;
  const p = S.source?.kind === 'preset' ? ctx.catalog?.presets.find(x => x.id === (S.source as { id: string }).id) : null;
  const sum = filtersFolded() ? summaryHtml(summaryItems(), c.texts, p?.name ?? null, uCountTxt()) : '';
  keepField($('cardU'), () => {   // typed text survives the redraw (keep-field.ts, ERRORS M373)
    $('cardU').innerHTML = `${sum}<div class="toolbar">
        <span id="uQf" style="display:contents">${qfHtml()}</span><button class="btn" data-act="drawer" ${ctx.catalog ? '' : 'disabled'}>${ico(IC.filter, 's')}More filters<span id="uN">${n ? `<span class="count">${n}</span>` : ''}</span></button>${ctx.catalog ? naButtonHtml() : ''}</div>
      <div class="chipbar"><span>Active filters</span><span id="uChips" style="display:contents">${c.html}</span>${universeEdited() ? `<button class="link" data-act="resetU">Clear all</button>` : ''}<span class="ucount" id="uCount">${uCountTxt()}</span></div>
      <div class="presets" id="uPresets"></div>`;
  });
  ui.renderPresets(); renderPop(); renderDrawer();
  syncRails(); layoutHooks.afterUniverse();
}
/** the quick filters that can be set, as the folded bar's summary line shows them */
const summaryItems = () => QF.filter(q => !disOf(q)).map(([, label, val, on]) => ({ label, value:val(S.universe), on:on(S.universe) }));
export function updateUniverseLight() {
  const c = scopeChips(), n = c.removable;
  $('uQf').innerHTML = qfHtml(); $('uChips').innerHTML = c.html; $('uCount').innerHTML = uCountTxt();
  $('uN').innerHTML = n ? `<span class="count">${n}</span>` : '';
  const uc = uCountTxt(); document.querySelectorAll('[data-ucount]').forEach(el => { el.innerHTML = uc });
  // the open popover's Clear follows an edit made in it (the prototype left it as it was when the popover opened)
  const qc = document.querySelector('#pop [data-uqclear]') as HTMLButtonElement | null, q = QF.find(x => x[0] === S.pop);
  if (qc && q) qc.disabled = !q[3](S.universe);
  // the dialog's group list follows the edit; the industry list follows the sectors
  const dr = $('drawerHost').querySelector('.drawer');
  if (dr) { const nav = dr.querySelector('.fnav'); if (nav) nav.outerHTML = fnavHtml(); FKEYS.forEach(k => dr.querySelector(`.dsec[data-k="${k}"]`)?.classList.toggle('unset', !!unsetClass(k))); scopeIndustries(dr); spy(dr) }
  syncRails();
}

/** the control a re-render replaces, found again by its data attributes (focus stays on it for keyboard users) */
const FOCUS_KEYS = ['u', 'sector', 'list', 'lsearch', 'tog', 'f', 'fdel', 'uqclear', 'act'] as const;
function focusSel(a: Element | null): string | null {
  if (!(a instanceof HTMLElement)) return null;
  const d = a.dataset, k = FOCUS_KEYS.find(x => d[x] != null);
  if (!k) return null;
  const attr = (n: string, v: string) => `[data-${n}="${CSS.escape(v)}"]`;
  return attr(k, d[k]!) + (d.fk != null ? attr('fk', d.fk) : '') + (d.v != null ? attr('v', d.v) : '');
}
const keepScroll = (el: HTMLElement, fn: () => void) => {
  const s = [...el.querySelectorAll<HTMLElement>('.drawer-b,.indlist,.lchips')].map(x => x.scrollTop), top = el.scrollTop;
  const a = document.activeElement, sel = a && el.contains(a) ? focusSel(a) : null;
  keepField(el, fn); el.scrollTop = top;
  [...el.querySelectorAll<HTMLElement>('.drawer-b,.indlist,.lchips')].forEach((x, i) => { x.scrollTop = s[i] || 0 });
  if (sel) (el.querySelector(sel) as HTMLElement | null)?.focus({ preventScroll:true });
};
/** the drawer is modal (aria-modal): Tab and Shift+Tab stay inside it (report 9.2 accessibility, as the dialogs) */
const FOCUSABLE = 'button:not([disabled]),input:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex="-1"])';
function trapDrawer(e: KeyboardEvent) {
  if (e.key !== 'Tab' || !S.drawer || !$('overlay').hidden) return;      // a dialog above keeps its own trap
  const box = $('drawerHost').querySelector('.drawer'); if (!box) return;
  const list = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(x => x.offsetParent !== null);
  if (!list.length) return;
  const first = list[0], last = list[list.length - 1], a = document.activeElement;
  if (!box.contains(a)) { e.preventDefault(); (e.shiftKey ? last : first).focus() }
  else if (e.shiftKey && a === first) { e.preventDefault(); last.focus() }
  else if (!e.shiftKey && a === last) { e.preventDefault(); first.focus() }
}
let trapBound = false;
const QCLEAR: Record<string, (u: UState) => void> = {
  sector:u => { u.sectors_in = []; u.sectors_out = []; u.industries_in = []; u.industries_out = []; u.include_unclassified = false },
  liq:u => { u.adv20_min_idr = FRESH.adv20_min_idr; u.price_min = FRESH.price_min },
  index:u => { u.indices_in = []; u.indices_out = []; u.groups_in = []; u.groups_out = [] },
};
export function renderPop() {
  const el = $('pop');
  if (!S.pop) { el.hidden = true; el.innerHTML = ''; return }
  const q = QF.find(x => x[0] === S.pop)!, extra = S.pop === 'sector' ? 'industry' : S.pop === 'index' ? 'group' : null;
  keepScroll(el, () => { el.innerHTML = `<div class="dsec" style="padding:0;border:0">${usec(S.pop!)}</div>${extra ? `<div class="dsec" style="padding:8px 0 0;border-bottom:0;border-top:1px solid var(--border)">${usec(extra)}</div>` : ''}
    <div class="pf"><span class="note" data-ucount>${uCountTxt()}</span><span class="acts" style="gap:6px"><button class="btn sm" data-uqclear="${S.pop}" ${q[3](S.universe) ? '' : 'disabled'}>Clear</button><button class="btn sm primary" data-act="popclose">Done</button></span></div>` });
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', q[1]);
  el.hidden = false; dressPop(el, S.pop); placePop();
  for (const kind of ['INDEX', 'KONGLO'] as const) applyListQuery(el, kind);
}
export function placePop() {
  const el = $('pop'), t = document.querySelector(`[data-qf="${S.pop}"]`);
  if (!t || el.hidden) return;
  const r = t.getBoundingClientRect(), w = el.offsetWidth;
  el.style.top = r.bottom + 6 + 'px'; el.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + 'px';
}
export function openPop(k: string) {
  S.pop = S.pop === k ? null : k;
  $('uQf').innerHTML = qfHtml(); renderPop();
  ($('pop').querySelector('input:not([type=checkbox]),button') as HTMLElement | null)?.focus({ preventScroll:true });
}
export function closePop() {
  if (!S.pop) return;
  const k = S.pop; S.pop = null; renderPop(); $('uQf').innerHTML = qfHtml();
  (document.querySelector(`[data-qf="${k}"]`) as HTMLElement | null)?.focus({ preventScroll:true });
}
let drawerOpener: HTMLElement | null = null;
export function renderDrawer() {
  const h = $('drawerHost');
  if (!S.drawer) { h.innerHTML = ''; return }
  // EXEC-SCREENER-V21: a centred dialog; the groups with data, in the reference order, with a group list that follows the
  // scroll (layout/filters.ts). Index, board, market cap, free float and special notation have no data: they are listed
  // with their reasons under "Not available yet" in the filter bar.
  const body = () => `<div class="drawer-wrap" data-dwrap><aside class="drawer ${drawerClass()}" role="dialog" aria-modal="true" aria-label="More filters"><div class="drawer-h"><div style="flex:1"><strong>More filters</strong><small>Who is eligible before any condition runs. Indicator tests live in the Screen builder.</small></div><button class="iconbtn sm" data-act="drawerclose" title="Close" aria-label="Close">${ico(IC.x)}</button></div>
    ${fnavHtml()}<div class="drawer-b">${shownFKeys().map(k => `<div class="dsec ${unsetClass(k)}" data-k="${k}" id="f-${k}">${k === 'industry' ? usec(k).replace('</small></div>', `</small>${indScopeHtml()}</div>`) : usec(k)}</div>`).join('')}</div>
    <div class="drawer-f"><button class="btn" data-act="resetU">${ico(IC.reset, 's')}Reset universe</button><span class="note" style="align-self:center" data-ucount>${uCountTxt()}</span><button class="btn primary" data-act="drawerclose">Done</button></div></aside></div>`;
  if (h.firstChild) keepScroll(h, () => { h.innerHTML = body() }); else h.innerHTML = body();
  const dr = h.querySelector('.drawer'); if (dr) { scopeIndustries(dr); for (const kind of ['INDEX', 'KONGLO'] as const) applyListQuery(dr, kind); requestAnimationFrame(() => spy(dr)) }
}
/** open More filters scrolled to a group (the quick filters on a wide screen) */
export function openDrawerAt(group: string) {
  if (!S.drawer) openDrawer(true);
  const dr = $('drawerHost').querySelector('.drawer'); if (!dr) return;
  requestAnimationFrame(() => { jumpTo(dr, group); (dr.querySelector(`.fnav [data-fk="${CSS.escape(group)}"]`) as HTMLElement | null)?.focus({ preventScroll:true }) });
}
let filterDialogBound = false;
/** the layout's events on the filter bar, popover and dialog (bound once by layout/index.ts) */
export function bindUniverseLayout() {
  if (filterDialogBound) return; filterDialogBound = true;
  bindFilterDialog($('drawerHost')); bindPopResize($('pop'), () => S.pop);
  // EXEC-SCREENER-STOCK-LISTS: a picker's search narrows its chips in place (no redraw, no edit of the screen)
  for (const host of [$('pop'), $('drawerHost')]) host.addEventListener('input', e => {
    const t = e.target as HTMLInputElement, kind = t.dataset?.lsearch as StockListKind | undefined;
    if (kind !== 'INDEX' && kind !== 'KONGLO') return;
    listQuery[kind] = t.value; applyListQuery(host, kind);
  });
  layoutHooks.openFiltersAt = g => { if (!ctx.catalog) return false; openDrawerAt(g); return true };
}
export function openDrawer(on: boolean) {
  if (on && !trapBound) { document.addEventListener('keydown', trapDrawer); trapBound = true }
  if (on) drawerOpener = document.activeElement as HTMLElement | null;
  S.drawer = on;
  if (on) { S.pop = null; renderPop(); $('uQf').innerHTML = qfHtml() }
  renderDrawer();
  if (on) ($('drawerHost').querySelector('.drawer .iconbtn') as HTMLElement | null)?.focus();
  /* audit U23: the focus goes back to what opened the drawer, or to its button when the page drew that one again */
  else { const back = drawerOpener && document.contains(drawerOpener) ? drawerOpener : document.querySelector<HTMLElement>('[data-act="drawer"]');
    back?.focus({ preventScroll:true }); drawerOpener = null }
}

const edit = (level: 'universe' | 'universe-light' = 'universe') => { ui.markDirty(); ui.refresh(level) };
/** delegated clicks of the universe card, popover and drawer (the universe part of the prototype's onClick) */
let flistOpen = false;
/** the active filters' list (option 9): opened by any icon, closed by another click on one, Escape or a click outside */
export function setFlist(open: boolean) { flistOpen = open; const l = document.getElementById('uFlist'); if (l) l.hidden = !open }
if (typeof document !== 'undefined') {
  document.addEventListener('pointerdown', e => { const t = e.target as HTMLElement; if (flistOpen && !t.closest('#uFlist, [data-flist]')) setFlist(false) }, true);
  document.addEventListener('keydown', e => { if (flistOpen && e.key === 'Escape') { setFlist(false); (document.querySelector('[data-flist]') as HTMLElement | null)?.focus() } });
}
export function onUniverseClick(b: HTMLElement): boolean {
  const U = S.universe, d = b.dataset;
  if (d.flist !== undefined) { setFlist(!flistOpen); return true }
  // EXEC-SCREENER-V21: on a wide screen a quick filter opens More filters at its group (reference layout.js 616-626)
  if (d.qf) { if (wide() && (d.qf === 'sector' || d.qf === 'liq' || d.qf === 'index') && layoutHooks.openFiltersAt(d.qf)) return true; openPop(d.qf); return true }
  if (d.na != null) { toggleNa(b); return true }
  if (d.act === 'uopen') { setFiltersFolded(false); return true }
  if (d.uqclear) { QCLEAR[d.uqclear]?.(U); edit(); return true }
  if (d.sector) {
    const s = d.sector; U.sectors_in ||= []; U.sectors_out ||= [];
    if (U.sectors_in.includes(s)) { U.sectors_in = U.sectors_in.filter(x => x !== s); U.sectors_out.push(s) }
    else if (U.sectors_out.includes(s)) U.sectors_out = U.sectors_out.filter(x => x !== s);
    else U.sectors_in.push(s);
    edit(); return true;
  }
  if (d.list) {
    // EXEC-SCREENER-STOCK-LISTS: no filter -> included -> excluded -> no filter, as a sector chip
    const i = d.list.indexOf(':'), kind = d.list.slice(0, i) as StockListKind, code = d.list.slice(i + 1), k = LIST_KEY[kind];
    if (!k) return true;
    const inc = U[k.in] ||= [], exc = U[k.out] ||= [];
    if (inc.includes(code)) { U[k.in] = inc.filter(x => x !== code); exc.push(code) }
    else if (exc.includes(code)) U[k.out] = exc.filter(x => x !== code);
    else inc.push(code);
    edit(); return true;
  }
  if (d.fdel != null) { U.filters.splice(+d.fdel, 1); edit(); return true }
  if (d.uhide) { if (d.uhide === 'traded') U.traded_on_eval_date = true; else U.exclude_price_breaks = true; edit(); return true }
  if (d.uclear) {
    const k = d.uclear;
    if (k === 'adv') U.adv20_min_idr = FRESH.adv20_min_idr;
    else if (k === 'price') U.price_min = FRESH.price_min;
    else if (k === 'traded') U.traded_on_eval_date = false;
    else if (k === 'breaks') U.exclude_price_breaks = false;
    else if (k === 'include_unclassified') U.include_unclassified = false;
    else if (k === 'min_history_bars') U.min_history_bars = null;
    else if (k === 'tickers') U.tickers = null;
    else if (/^f\d+$/.test(k)) U.filters.splice(+k.slice(1), 1);
    else if (k in U) (U as any)[k] = [];
    edit(); return true;
  }
  switch (d.act) {
    case 'drawer': openDrawer(true); return true;
    case 'drawerclose': openDrawer(false); return true;
    case 'popclose': closePop(); return true;
    case 'addfund': pendingFilter = true; renderDrawer(); renderPop(); ($('drawerHost').querySelector('[data-fnew]') as HTMLElement | null)?.focus(); return true;
    case 'fcancel': pendingFilter = false; renderDrawer(); return true;
    case 'resetU': S.universe = freshUniverse(); pendingFilter = false; ui.markDirty(); ui.toast('Universe reset'); ui.refresh('universe'); return true;
  }
  return false;
}
/** field edits of the universe (the universe part of the prototype's applyField); invalid numbers are refused in place */
export function onUniverseField(el: HTMLInputElement | HTMLSelectElement): boolean {
  const U = S.universe, d = el.dataset;
  if (d.lsearch) return true;                     // a picker's search box edits no filter (bindUniverseLayout)
  if (d.tog) {
    const key = d.tog as 'industries_in', arr = U[key] || [], v = d.v!;
    U[key] = (el as HTMLInputElement).checked ? [...new Set([...arr, v])] : arr.filter(x => x !== v);
    edit('universe-light'); return true;
  }
  if (d.u) {
    if (el.type === 'checkbox') { (U as any)[d.u] = (el as HTMLInputElement).checked; edit(); return true }
    const raw = el.value.trim(), v = raw === '' ? null : Number(raw);
    if (v != null && (!Number.isFinite(v) || v < 0)) { el.setCustomValidity('Enter a number ≥ 0, or leave empty for any.'); el.reportValidity(); return true }
    el.setCustomValidity('');
    if (d.u === 'adv') { const idr = v == null ? null : Math.round(v * 1e9); if (U.adv20_min_idr === idr) return true; U.adv20_min_idr = idr }
    else if (d.u === 'price') { if (U.price_min === v) return true; U.price_min = v }
    edit('universe-light'); return true;
  }
  if (d.fnew != null) {
    const e = ctx.byKey.get(el.value); if (!e) return true;
    const vo = e.opts.find(o => o.kind === 'value') || e.opts[0];
    U.filters.push(newCard(e, U.filters.map(f => f.id), { opt:vo.key }));
    pendingFilter = false; edit(); return true;
  }
  if (d.f != null) {
    const i = +d.f, f = U.filters[i]; if (!f) return true;
    const k = d.fk!;
    if (k === 'key') {
      const e = ctx.byKey.get(el.value); if (!e || e.key === f.entry) return true;
      const vo = e.opts.find(o => o.kind === 'value') || e.opts[0];
      U.filters[i] = newCard(e, U.filters.map(x => x.id), { opt:vo.key, value:f.value, value2:f.value2 });
      edit(); return true;
    }
    if (k === 'op') { f.opt = el.value; edit(); return true }
    const v = el.value === '' ? '' : Number(el.value);
    if (v === '' || !Number.isFinite(v)) { el.setCustomValidity('Enter a number.'); el.reportValidity(); return true }
    el.setCustomValidity('');
    if ((f as any)[k] === v) return true;
    (f as any)[k] = v; edit('universe-light'); return true;
  }
  return false;
}
