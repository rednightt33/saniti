/* Card 1: the universe (the prototype's renderUniverse, scopeChips, QF, usec, renderPop, renderDrawer), on the wire
   universe of report 8.5. Kept: Sector and Industry (lists and counts from catalog.groupings, unclassified stocks
   counted apart, P15), Liquidity (ADV20 ≥ Rp B and price ≥ Rp; defaults 1 B and 50). Shown disabled with their reason
   (P11 a): Index, Board, Market cap, Free float, Special notation (off, its chip removed). New (P4): the chips
   "Traded on E" and "No unadjusted price break", on by default, each naming how many tickers it hides. One rule for
   "Clear all" and both liquidity clears: back to the documented defaults (report 9.2). */
import { UNIVERSE_DEFAULTS, type Grouping } from './core/contract.ts';
import { esc, nf } from './format.ts';
import { IC, ico } from './icons.ts';
import { ctx, freshUniverse, S, ui, type UState } from './state.ts';
import { chipNoBreak, chipTraded, T } from './texts.ts';
import { condText, displayUnit, newCard, optOf, type Card } from './forms.ts';
import { byGroup, OPLABEL } from './entries.ts';
import { hiddenCounts } from './universe-view.ts';

const $ = (id: string) => document.getElementById(id)!;
const FRESH = freshUniverse();
let pendingFilter = false;

const grouping = (key: string): Grouping | undefined => ctx.catalog?.groupings.find(g => g.key === key);
const advB = (u: UState) => u.adv20_min_idr == null ? null : u.adv20_min_idr / 1e9;
const isDefaultLiq = (u: UState) => u.adv20_min_idr === UNIVERSE_DEFAULTS.adv20_min_idr && u.price_min === UNIVERSE_DEFAULTS.price_min;
const hidden = () => ctx.universe ? hiddenCounts(ctx.universe.rows) : null;

/** whether the universe differs from the documented defaults (Clear all is shown then) */
export function universeEdited(u = S.universe): boolean {
  return !!(u.sectors_in?.length || u.sectors_out?.length || u.industries_in?.length || u.industries_out?.length || u.include_unclassified
    || !isDefaultLiq(u) || u.min_history_bars != null || u.tickers?.length || u.filters.length || !u.traded_on_eval_date || !u.exclude_price_breaks);
}

/** the active-filter chips (scopeChips) */
function scopeChips(): { html: string; removable: number } {
  const U = S.universe, out: string[] = []; let n = 0;
  const add = (label: string, val: string, clear: string | null, title = '') => {
    if (clear && clear !== 'traded' && clear !== 'breaks') n++;     // the P4 chips are on by default: not an edit
    out.push(`<span class="fchip ${clear ? '' : 'fixed'}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)} <b>${esc(val)}</b>${clear ? `<button data-uclear="${clear}" title="Remove filter" aria-label="Remove ${esc(label)} filter">${ico(IC.x, 's')}</button>` : ''}</span>`);
  };
  const list = (a: string[], one: string, many: string) => a.length > 2 ? `${a.length} ${many}` : a.join(', ') || one;
  if (U.sectors_in?.length) add('Sector', list(U.sectors_in, '', 'sectors'), 'sectors_in');
  if (U.sectors_out?.length) add('Excluding', list(U.sectors_out, '', 'sectors'), 'sectors_out');
  if (U.industries_in?.length) add('Industry', list(U.industries_in, '', 'industries'), 'industries_in');
  if (U.industries_out?.length) add('Excluding industry', list(U.industries_out, '', 'industries'), 'industries_out');
  if (U.include_unclassified) add('Keeps', 'unclassified', 'include_unclassified', 'Stocks without a sector or industry are kept by the include filters (P15).');
  const ab = advB(U);
  if (ab != null) add('Avg value ≥', `Rp ${nf(ab, ab % 1 ? 1 : 0)}B`, U.adv20_min_idr === UNIVERSE_DEFAULTS.adv20_min_idr ? null : 'adv', 'Average daily traded value over 20 sessions (close × volume). Default Rp 1B.');
  if (U.price_min != null) add('Price ≥', `Rp ${nf(U.price_min)}`, U.price_min === UNIVERSE_DEFAULTS.price_min ? null : 'price', 'Last close. Default Rp 50.');
  if (U.min_history_bars != null) add('History ≥', `${nf(U.min_history_bars)} sessions`, 'min_history_bars');
  if (U.tickers?.length) add('Tickers', U.tickers.length > 3 ? `${U.tickers.length} stocks` : U.tickers.join(', '), 'tickers');
  U.filters.forEach((f, i) => add('Filter', condText(ctx.byKey.get(f.entry || ''), f), 'f' + i));
  const h = hidden(), E = ctx.catalog?.data.evaluation_date || null;
  if (U.traded_on_eval_date) add(chipTraded(E), h ? `hides ${h.stale}` : '', 'traded', 'Hides stale stocks (no trade on the evaluation date). Remove to list them with a remark.');
  else out.push(`<span class="fchip off" title="Stale stocks are listed with a remark">Stale shown <b>${h ? h.stale : ''}</b><button class="link" data-uhide="traded" style="margin-left:4px">Hide</button></span>`);
  if (U.exclude_price_breaks) add(chipNoBreak, h ? `hides ${h.breaks}` : '', 'breaks', 'Hides stocks whose price history crosses an unadjusted corporate action (TEMPORARY until the data layer adjusts history). Remove to list them with a remark.');
  else out.push(`<span class="fchip off" title="Stocks with a price break are listed with a remark; their values are shown and marked">Price breaks shown <b>${h ? h.breaks : ''}</b><button class="link" data-uhide="breaks" style="margin-left:4px">Hide</button></span>`);
  return { html:out.join(''), removable:n };
}

type QFDef = [key: string, label: string, val: (u: UState) => string, on: (u: UState) => boolean, disabled?: string];
const sectorVal = (u: UState) => u.sectors_in?.length ? u.sectors_in[0] + (u.sectors_in.length > 1 ? ` +${u.sectors_in.length - 1}` : '') : u.sectors_out?.length ? `All but ${u.sectors_out.length}` : u.industries_in?.length ? `${u.industries_in.length} industr${u.industries_in.length > 1 ? 'ies' : 'y'}` : 'All';
const QF: QFDef[] = [
  ['index', 'Index', () => 'No data', () => false, T.noIndex],
  ['sector', 'Sector', sectorVal, u => !!(u.sectors_in?.length || u.sectors_out?.length || u.industries_in?.length || u.industries_out?.length)],
  ['cap', 'Market Cap', () => 'No data', () => false, T.noCap],
  ['liq', 'Liquidity', u => `ADV ≥ Rp ${nf(advB(u) ?? 0, (advB(u) ?? 0) % 1 ? 1 : 0)}B`, u => !isDefaultLiq(u)],
  ['board', 'Board', () => 'No data', () => false, T.noBoard],
];

const metricOpts = (cur: string | null) => {
  const list = byGroup(ctx.entries.filter(e => e.kind !== 'indicator' && e.opts.some(o => o.kind === 'value')));
  const groups = [...new Set(list.map(e => e.group))];
  return `${cur ? '' : '<option value="" selected disabled>Pick a metric…</option>'}` + groups.map(g => `<optgroup label="${esc(g)}">${list.filter(e => e.group === g)
    .map(e => `<option value="${esc(e.key)}" ${e.key === cur ? 'selected' : ''} ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${esc(e.label)}${e.available ? '' : ' — no data'}</option>`).join('')}</optgroup>`).join('');
};

/** one renderer per universe setting, shared by the popover and the drawer (usec) */
function usec(k: string): string {
  const U = S.universe;
  switch (k) {
    case 'index': return `<div class="k">Index <small>· no data</small></div><div class="chips">${['LQ45', 'IDX30', 'IDX80', 'ISSI'].map(i => `<button class="chip" disabled title="${esc(T.noIndex)}">${i}</button>`).join('')}</div><div class="note">${esc(T.noIndex)}</div>`;
    case 'board': return `<div class="k">Listing board <small>· no data</small></div><div class="chips">${['Main', 'Development'].map(b => `<button class="chip" disabled title="${esc(T.noBoard)}">${b}</button>`).join('')}</div><div class="note">${esc(T.noBoard)}</div>`;
    case 'liq': {
      const ab = advB(U);
      return `<div class="k">Liquidity & price</div><div class="mini3"><label class="fld"><span>Avg value ≥ Rp B</span><input class="inp" type="number" step="any" min="0" data-u="adv" value="${ab ?? ''}" placeholder="any"></label><label class="fld"><span>Price ≥ Rp</span><input class="inp" type="number" min="0" data-u="price" value="${U.price_min ?? ''}" placeholder="any"></label><label class="fld" title="${esc(T.noFreeFloat)}"><span>Free float ≥ %</span><input class="inp" type="number" disabled placeholder="no data" aria-label="Free float: no data"></label></div>`;
    }
    case 'sector': {
      const g = grouping('sector');
      if (!g) return `<div class="k">Sectors</div><div class="note">${T.loadingIndicators}</div>`;
      return `<div class="k">Sectors <small>· click to include, again to exclude, again to clear</small></div><div class="chips">${g.values.map(v => `<button class="chip ${U.sectors_in?.includes(v.value) ? 'on' : U.sectors_out?.includes(v.value) ? 'ex' : ''}" data-sector="${esc(v.value)}">${esc(v.value)} <small>${nf(v.tickers)}</small></button>`).join('')}</div>
        ${g.unclassified ? `<label class="chk" title="An include filter (sector or industry) keeps a stock without that classification only when this is on; an exclude filter never drops it."><input type="checkbox" data-u="include_unclassified" ${U.include_unclassified ? 'checked' : ''}>Unclassified (${nf(g.unclassified)}): keep them with an include filter</label>` : ''}`;
    }
    case 'cap': return `<div class="k">Market cap <small>· no data</small></div><div class="mini2"><input class="inp" disabled placeholder="Min" aria-label="Min market cap: no data"><input class="inp" disabled placeholder="Max" aria-label="Max market cap: no data"></div><div class="note">${esc(T.noCap)}</div>`;
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
        <div class="note">Turned off, the hidden stocks are listed with a remark: the last trade date, or the corporate action and its ex-date. Their values are shown (P4).</div>`;
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

export const uCountTxt = () => {
  const R = ctx.R, listed = ctx.universe?.rows.length ?? R?.listed ?? 0;
  if (!ctx.universe && !R) return `In universe <b>…</b>`;
  return `In universe <b>${nf(R ? R.eligible : 0)}</b> of ${nf(listed)}`;
};
const qfHtml = () => QF.map(([k, label, val, on, dis]) => dis
  ? `<button class="qf" disabled title="${esc(dis)}" aria-disabled="true"><span>${label}</span><b>${esc(val(S.universe))}</b>${ico(IC.chev, 's')}</button>`
  : `<button class="qf ${on(S.universe) ? 'on' : ''} ${S.pop === k ? 'open' : ''}" data-qf="${k}" aria-expanded="${S.pop === k}" aria-haspopup="dialog" ${ctx.catalog ? '' : 'disabled title="Loading…"'}><span>${label}</span><b>${esc(val(S.universe))}</b>${ico(IC.chev, 's')}</button>`).join('');

export function renderUniverse() {
  const c = scopeChips(), n = c.removable;
  $('cardU').innerHTML = `<div class="toolbar">
      <span id="uQf" style="display:contents">${qfHtml()}</span><button class="btn" data-act="drawer" ${ctx.catalog ? '' : 'disabled'}>${ico(IC.filter, 's')}More filters<span id="uN">${n ? `<span class="count">${n}</span>` : ''}</span></button></div>
    <div class="chipbar"><span>Active filters</span><span id="uChips" style="display:contents">${c.html}</span>${universeEdited() ? `<button class="link" data-act="resetU">Clear all</button>` : ''}<span class="ucount" id="uCount">${uCountTxt()}</span></div>
    <div class="presets" id="uPresets"></div>`;
  ui.renderPresets(); renderPop(); renderDrawer();
}
export function updateUniverseLight() {
  const c = scopeChips(), n = c.removable;
  $('uQf').innerHTML = qfHtml(); $('uChips').innerHTML = c.html; $('uCount').innerHTML = uCountTxt();
  $('uN').innerHTML = n ? `<span class="count">${n}</span>` : '';
  document.querySelectorAll('[data-ucount]').forEach(el => { el.innerHTML = uCountTxt() });
}

const keepScroll = (el: HTMLElement, fn: () => void) => {
  const s = [...el.querySelectorAll<HTMLElement>('.drawer-b,.indlist')].map(x => x.scrollTop), top = el.scrollTop;
  fn(); el.scrollTop = top;
  [...el.querySelectorAll<HTMLElement>('.drawer-b,.indlist')].forEach((x, i) => { x.scrollTop = s[i] || 0 });
};
const QCLEAR: Record<string, (u: UState) => void> = {
  sector:u => { u.sectors_in = []; u.sectors_out = []; u.industries_in = []; u.industries_out = []; u.include_unclassified = false },
  liq:u => { u.adv20_min_idr = FRESH.adv20_min_idr; u.price_min = FRESH.price_min },
};
export function renderPop() {
  const el = $('pop');
  if (!S.pop) { el.hidden = true; el.innerHTML = ''; return }
  const q = QF.find(x => x[0] === S.pop)!, extra = S.pop === 'sector' ? 'industry' : null;
  keepScroll(el, () => { el.innerHTML = `<div class="dsec" style="padding:0;border:0">${usec(S.pop!)}</div>${extra ? `<div class="dsec" style="padding:8px 0 0;border-bottom:0;border-top:1px solid var(--border)">${usec(extra)}</div>` : ''}
    <div class="pf"><span class="note" data-ucount>${uCountTxt()}</span><span class="acts" style="gap:6px"><button class="btn sm" data-uqclear="${S.pop}" ${q[3](S.universe) ? '' : 'disabled'}>Clear</button><button class="btn sm primary" data-act="popclose">Done</button></span></div>` });
  el.setAttribute('role', 'dialog'); el.setAttribute('aria-label', q[1]);
  el.hidden = false; placePop();
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
  const body = () => `<div class="drawer-wrap" data-dwrap><aside class="drawer" role="dialog" aria-modal="true" aria-label="More filters"><div class="drawer-h"><div style="flex:1"><strong>More filters</strong><small>Who is eligible before any condition runs. Indicator tests live in the Screen builder.</small></div><button class="iconbtn sm" data-act="drawerclose" title="Close" aria-label="Close">${ico(IC.x)}</button></div>
    <div class="drawer-b">${['index', 'board', 'liq', 'sector', 'cap', 'industry', 'metric', 'quality', 'notation'].map(k => `<div class="dsec">${usec(k)}</div>`).join('')}</div>
    <div class="drawer-f"><button class="btn" data-act="resetU">${ico(IC.reset, 's')}Reset universe</button><span class="note" style="align-self:center" data-ucount>${uCountTxt()}</span><button class="btn primary" data-act="drawerclose">Done</button></div></aside></div>`;
  if (h.firstChild) keepScroll(h, () => { h.innerHTML = body() }); else h.innerHTML = body();
}
export function openDrawer(on: boolean) {
  if (on) drawerOpener = document.activeElement as HTMLElement | null;
  S.drawer = on;
  if (on) { S.pop = null; renderPop(); $('uQf').innerHTML = qfHtml() }
  renderDrawer();
  if (on) ($('drawerHost').querySelector('.drawer .iconbtn') as HTMLElement | null)?.focus();
  else if (drawerOpener && document.contains(drawerOpener)) { drawerOpener.focus({ preventScroll:true }); drawerOpener = null }
}

const edit = (level: 'universe' | 'universe-light' = 'universe') => { ui.markDirty(); ui.refresh(level) };
/** delegated clicks of the universe card, popover and drawer (the universe part of the prototype's onClick) */
export function onUniverseClick(b: HTMLElement): boolean {
  const U = S.universe, d = b.dataset;
  if (d.qf) { openPop(d.qf); return true }
  if (d.uqclear) { QCLEAR[d.uqclear]?.(U); edit(); return true }
  if (d.sector) {
    const s = d.sector; U.sectors_in ||= []; U.sectors_out ||= [];
    if (U.sectors_in.includes(s)) { U.sectors_in = U.sectors_in.filter(x => x !== s); U.sectors_out.push(s) }
    else if (U.sectors_out.includes(s)) U.sectors_out = U.sectors_out.filter(x => x !== s);
    else U.sectors_in.push(s);
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
