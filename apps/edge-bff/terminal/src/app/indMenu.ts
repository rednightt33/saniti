/* EXEC-IND-CARDS IC1 (user go 2026-11-01: "jalankan TERMINAL-IND-CARDS as well"; mockup
   verification/terminal_api/indicator_cards/indicator_cards_review.html, approved 2026-11-01 with the bigger star): the
   indicator menu as TradingView's "Indicators, metrics, and strategies": groups on the left (Favorites, All, the
   technical categories, the Flow families), a list with a favourite star, name and code, group, place and unit, a short
   tooltip on hover (decision "1A"). EXEC-IND-DIALOG (2026-11-06): restyled as the Screener's "Add a condition" window and
   the card button removed with the cards (EXEC-TERMINAL-LOOK 2B). Live page only; the
   fixture keeps the reference's popover (1:1 check). Nothing is listed by hand: the rows come from the Terminal's
   registries (indRegistry.json, flowRegistry.json). */
import type { Ctx } from './context';
import { $, store } from './context';
import { draggable, fitInView, shiftOf } from './draggable';
import { FLOW_REG, SINGLE_SECURITY } from './flowIndicators';
import { ALL_INPUTS, fits, inputsOf, needsOf, type Input } from '../data/inputs';

export interface MenuItem { id: string; name: string; group: string; kind: 'Technical' | 'Flow' | 'Base'; place: string; unit: string; tip: string; short?: string }

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const FAV_KEY = 'ml.ind.favs', SIZE_KEY = 'ml.ind.box', NAV_KEY = 'ml.ind.navw';

/** where a Flow indicator is drawn (flowRegistry `place`): its own pane, the price axis, or a mark under the candles */
export const flowPlace = (place: string) => place === 'pane' ? 'Panel' : 'Overlay';

/** EXEC-TERMINAL-IND-EDIT (user 2026-11-05): indicators the menu no longer offers. Their definitions stay (calc, the
    registries, Backtest and Screener are untouched), so a chart that already has one restores and draws it
    (indicators.ts restore reads DEFS, not the menu). I37 and I41: "1A" (Terminal menu only); FL07, FL35, FL36: review A1
    ("hide"; FL07's calculation is still used by FL09). */
export const MENU_HIDDEN: ReadonlySet<string> = new Set(['I37', 'I41', 'FL07', 'FL35', 'FL36']);

/** the menu's rows from the registries: the technical indicators by category, the base volume histogram, and the Flow
    indicators by family, in the registries' order */
/** the menu's rows for a ticker with the inputs `have` (ERRORS M332: an indicator the ticker cannot feed is not offered,
    data/inputs.ts; a bond: no Flow, no volume) */
export function menuItems(indReg: any[], flowReg: { families: string[]; indicators: any[] }, have: ReadonlySet<Input> = ALL_INPUTS): MenuItem[] {
  const group = (cat: string) => cat === 'PriceVolume' ? 'Price & Volume' : cat.replace(/([a-z])([A-Z])/g, '$1 & $2');
  const out: MenuItem[] = indReg.filter(r => !MENU_HIDDEN.has(r.id) && fits(needsOf({ reg:r }), have)).map(r => ({ id:r.id, name:r.name, group:group(r.cat), kind:'Technical', place:r.zone === 'overlay' ? 'Overlay' : 'Panel',
    unit:r.unit || '', tip:r.tip || '', short:r.short || '' }));
  const vol = out.findIndex(i => i.group === 'Volume');
  if (have.has('V')) out.splice(vol < 0 ? out.length : vol, 0, { id:'VOL', name:'Volume', group:'Volume', kind:'Base', place:'Panel', unit:'shares',
    tip:'Batang volume transaksi harian di bagian bawah chart harga.' });
  if (have.has('flow')) for (const f of flowReg.families) for (const r of flowReg.indicators.filter(x => x.family === f))
    if (!MENU_HIDDEN.has(r.id) && fits(needsOf({ flow:true, single:SINGLE_SECURITY.has(r.id) }), have)) out.push({ id:r.id, name:r.name, group:f, kind:'Flow', place:flowPlace(r.place), unit:r.unit || '', tip:r.tip || '' });
  return out;
}

/** the rows a group (or a search) shows: a search looks at the name, code, group and kind of every row */
export type KindFilter = 'all' | 'Technical' | 'Flow';
/** user 2026-11-01 ("tambahkan opsi untuk filter by indicator group type"): the group type, Technical (with the base
    volume) or Flow, narrows every view, a search included */
export const ofKind = (i: MenuItem, kind: KindFilter) => kind === 'all' || (kind === 'Flow' ? i.kind === 'Flow' : i.kind !== 'Flow');
export function visibleItems(items: MenuItem[], group: string, query: string, favs: Set<string>, kind: KindFilter = 'all'): MenuItem[] {
  return visibleAll(items.filter(i => ofKind(i, kind)), group, query, favs);
}
/** user 2026-11-01: a unit as text, not as a formula ("0–100", "lot / IDR", "−1 to 1") */
export function unitText(u: string): string {
  const exact: Record<string, string> = { '0-100':'0–100', '0-1':'0–1', '-1..1':'−1 to 1', index_0_100:'0–100', index_minus100_0:'−100–0',
    index_minus100_100:'−100–100', price_times_volume:'IDR', diff:'difference' };
  if (exact[u]) return exact[u];
  if (/^percent/.test(u)) return '%';
  if (/^price_difference/.test(u)) return 'price change';
  if (/^ratio/.test(u)) return 'ratio';
  if (/^formula_defined/.test(u)) return 'as the formula';
  if (/price_weighted_volume|volume_weighted/.test(u)) return 'volume × price';
  if (/volume|^shares$/.test(u)) return 'volume';
  if (u === 'range_per_volume') return 'range / volume';
  if (u === 'index_cumulative') return 'cumulative';
  return u.replace('|', ' / ').replace(/_/g, ' ');
}
function visibleAll(items: MenuItem[], group: string, query: string, favs: Set<string>): MenuItem[] {
  const q = query.trim().toLowerCase();
  // QA M9 (2026-11-06): the short name too ("RSI", "SMA", "ATR"), as the search box's own example reads; an exact short
  // name or code comes first
  if (q) return items.filter(i => `${i.name} ${i.id} ${i.short || ''} ${i.group} ${i.kind}`.toLowerCase().includes(q))
    .sort((a, b) => Number((b.short || '').toLowerCase() === q || b.id.toLowerCase() === q) - Number((a.short || '').toLowerCase() === q || a.id.toLowerCase() === q));
  if (group === 'fav') return items.filter(i => favs.has(i.id));
  if (group === 'all') return items;
  const [k, g] = [group.slice(0, 1), group.slice(2)];
  return items.filter(i => (k === 'f' ? i.kind === 'Flow' : i.kind !== 'Flow') && i.group === g);
}

/** a row's grey line: the indicator's default settings from its registry ("Length 20 · Source close"); a select shows its
    option label, a list of every option "All", a token default its plain words */
export function defaultsText(id: string, indReg: any[], flowReg: { indicators: any[] }): string {
  const tech = indReg.find(r => r.id === id);
  if (tech) return (tech.params || []).filter((q: any) => q.type !== 'fixed').map((q: any) => `${q.label} ${Array.isArray(q.def) ? q.def.join(', ') : q.def}`).join(' · ');
  const flow = flowReg.indicators.find(r => r.id === id);
  if (!flow) return '';
  return (flow.params || []).filter((q: any) => q.kind !== 'fixed' && q.default !== undefined && q.default !== '' && q.default !== '-').map((q: any) => {
    let v = q.default;
    if (Array.isArray(v)) v = q.options && v.length === q.options.length ? 'All' : v.join(', ');
    else if (q.options) { const o = q.options.find((x: any) => Array.isArray(x) ? x[0] === v : x === v); if (Array.isArray(o)) v = o[1] }
    if (typeof v === 'boolean') v = v ? 'On' : 'Off';
    if (v === 'top3_net_buy_20') v = 'Top 3 net buyers';
    if (v === 'auto_c') v = 'Auto (2 net buyers, 1 net seller)';
    return `${q.label} ${v}`;
  }).join(' · ');
}

const STAR = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="m12 2.8 2.8 5.8 6.4.9-4.6 4.5 1.1 6.3L12 17.3l-5.7 3 1.1-6.3-4.6-4.5 6.4-.9z"/></svg>';
const CHECK = '<svg class="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m3 8.5 3 3 7-7"/></svg>';

/* EXEC-IND-DIALOG (user go 2026-11-06: "Klik selalu menambah. Kalau klik kasih semacam notifikasi saja bahwa indikator
   added"): the Screener's "Add a condition" layout without condition, threshold or card; groups On the chart, Favorites,
   All indicators, then Technical and Flow; a click on a row or Add always adds and shows "<name> added" */
export function initIndMenu(ctx: Ctx) {
  const { IND_REG, Ind, volCtl } = ctx;
  const items = menuItems(IND_REG as any[], FLOW_REG as any, inputsOf(ctx.M));
  const groupsOf = (kind: 'Technical' | 'Flow') => [...new Set(items.filter(i => kind === 'Flow' ? i.kind === 'Flow' : i.kind !== 'Flow').map(i => i.group))];
  const defaults = new Map(items.map(i => [i.id, i.kind === 'Base' ? '' : defaultsText(i.id, IND_REG as any[], FLOW_REG as any)]));
  let favs = new Set<string>();
  try { favs = new Set(JSON.parse(store.get(FAV_KEY) || '[]')) } catch { /* none saved */ }
  const saveFavs = () => store.set(FAV_KEY, JSON.stringify([...favs]));
  // a favourite the menu no longer lists (MENU_HIDDEN, or not available for this ticker) does not count: the menu opens on
  // All rather than on an empty Favorites view
  let group = items.some(i => favs.has(i.id)) ? 'fav' : 'all', query = '';

  const btn = $('indBtn'), old = $('indPop');
  old.hidden = true;
  const dlg = document.createElement('div');
  dlg.className = 'im'; dlg.id = 'indMenu'; dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true');
  dlg.setAttribute('aria-label', 'Indicators'); dlg.hidden = true;
  dlg.innerHTML = `<div class="im-box">
      <div class="im-head"><div class="t"><h3>Indicators</h3><p>Click a row to add it to the chart. Remove an indicator from its line on the chart. The window stays open until you close it.</p></div>
        <button type="button" class="im-x" aria-label="Close indicators">×</button></div>
      <label class="im-search"><svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2 17 17"/></svg>
        <input type="search" id="imSearch" placeholder="RSI, MACD, Bandar Balance, Broker Inventory…" autocomplete="off" aria-label="Search indicators"></label>
      <div class="im-body"><nav class="im-nav" aria-label="Indicator groups"></nav><div class="im-split" role="separator" aria-orientation="vertical" aria-label="Resize the group list" tabindex="0"></div>
        <div class="im-main"><div class="im-cols" aria-hidden="true"><span></span><span>Indicator</span><span>Place · Unit</span><span></span></div><div class="im-list" role="list"></div></div></div>
      <div class="im-foot"><span>/ to search · ↑ ↓ to move · Enter to add · Esc to close</span><b class="im-count"></b></div>
      <div class="im-toast" role="status" aria-live="polite"></div>
      <div class="im-rz im-rz-r" aria-hidden="true"></div><div class="im-rz im-rz-b" aria-hidden="true"></div>
      <div class="im-rz im-rz-c" role="button" tabindex="0" aria-label="Resize the indicators box; double-click to fill the window" title="Drag to resize · double-click to fill the window"></div>
    </div>`;
  draggable(dlg.querySelector('.im-box'), dlg.querySelector('.im-head'));      // user 2026-11-01: moved by its header
  document.body.appendChild(dlg);
  const nav = dlg.querySelector('.im-nav') as HTMLElement, list = dlg.querySelector('.im-list') as HTMLElement;
  const search = dlg.querySelector('#imSearch') as HTMLInputElement, toast = dlg.querySelector('.im-toast') as HTMLElement;
  const countEl = dlg.querySelector('.im-count') as HTMLElement;
  const tip = document.createElement('div'); tip.className = 'im-tip'; tip.hidden = true; document.body.appendChild(tip);

  const onChart = (i: MenuItem) => i.kind === 'Base' ? (volCtl.removed ? 0 : 1) : Ind.byName[i.name] ? Ind.countOf(Ind.byName[i.name]) : 0;
  const view = (g: string, q: string) => g === 'chart' && !q.trim() ? items.filter(i => onChart(i) > 0) : visibleItems(items, g, q, favs);
  const navHtml = () => {
    const b = (id: string, label: string, n: number, cls = '', ico = '') =>
      `<button type="button" data-g="${esc(id)}" class="${cls}${group === id && !query ? ' on' : ''}">${ico}<span class="lab">${label}</span><span class="cnt">${n}</span></button>`;
    const flow = groupsOf('Flow');
    return b('chart', 'On the chart', items.reduce((t, i) => t + onChart(i), 0), 'q-on', CHECK)
      + b('fav', 'Favorites', view('fav', '').length, 'q-my', STAR.replace('<svg ', '<svg class="ico" '))
      + `<div class="im-sep"></div>${b('all', 'All indicators', items.length)}`
      + `<div class="im-title">Technical</div>${groupsOf('Technical').map(g => b(`t:${g}`, esc(g), view(`t:${g}`, '').length)).join('')}`
      + (flow.length ? `<div class="im-title">Flow</div>${flow.map(g => b(`f:${g}`, esc(g), view(`f:${g}`, '').length)).join('')}` : '');
  };
  /* EXEC-TERMINAL-LOOK-2 (user 2026-11-06: "kalau di HTML contoh maka dia bisa scroll semua indikator, dan panel disebelah
     kiri tetap mengikuti"): outside On the chart, Favorites and a search the list holds every indicator under its group's
     heading; a group on the left jumps to its heading and the group in view is marked on the left (Screener v16 qSpyMode) */
  const spyMode = () => group !== 'chart' && group !== 'fav' && !query.trim();
  const keyOf = (i: MenuItem) => `${i.kind === 'Flow' ? 'f' : 't'}:${i.group}`;
  const ordered = () => [...groupsOf('Technical').map(g => `t:${g}`), ...groupsOf('Flow').map(g => `f:${g}`)]
    .flatMap(k => items.filter(i => keyOf(i) === k));
  let spyLock = 0;
  const mark = (g: string) => {
    group = g;
    nav.querySelectorAll<HTMLElement>('[data-g]').forEach(b => { const on = b.dataset.g === g; b.classList.toggle('on', on); if (on) b.scrollIntoView({ block:'nearest', inline:'nearest' }) });
  };
  const secTop = (h: HTMLElement) => { const r = h.nextElementSibling as HTMLElement | null; return r ? Math.max(0, r.offsetTop - list.offsetTop - h.offsetHeight - 6) : 0 };
  const spy = () => {
    if (!spyMode() || Date.now() < spyLock) return;
    const top = list.scrollTop + 2; let cur = '';
    // a sticky heading reports where it is stuck, so each group's place is read from its first row
    list.querySelectorAll<HTMLElement>('.im-sec').forEach(h => { if (secTop(h) <= top) cur = h.dataset.sec as string });
    if (list.scrollTop < 2 && group === 'all') return;            // "All indicators" stays marked at the top
    /* QA (2026-11-06): at the end of the list the last short groups never reach the top; the group clicked stays marked,
       else the last group */
    if (list.scrollTop + list.clientHeight >= list.scrollHeight - 2) { const secs = [...list.querySelectorAll<HTMLElement>('.im-sec')].map(h => h.dataset.sec as string);
      const last = secs[secs.length - 1]; if (secs.indexOf(group) > secs.indexOf(cur)) return; if (last) { mark(last); return } }
    if (cur && cur !== group) mark(cur);
  };
  const scrollToGroup = (g: string) => {
    spyLock = Date.now() + 400;
    const h = g === 'all' ? null : list.querySelector<HTMLElement>(`.im-sec[data-sec="${CSS.escape(g)}"]`);
    list.scrollTop = h ? secTop(h) : 0;
  };
  const render = () => {
    const keep = nav.scrollTop;
    nav.innerHTML = navHtml(); nav.scrollTop = keep;
    const spying = spyMode(), rows = spying ? ordered() : view(group, query), wide = !spying;
    let last = '';
    list.innerHTML = rows.length ? rows.map(i => {
      const k = keyOf(i), head = spying && k !== last ? `<div class="im-sec" data-sec="${esc(k)}" role="presentation">${i.kind === 'Flow' ? 'Flow · ' : ''}${esc(i.group)}</div>` : '';
      last = k;
      return head + rowHtml(i, wide);
    }).join('') : `<div class="im-empty">${group === 'fav' && !query ? 'No favorites yet: star an indicator to keep it here.' : group === 'chart' && !query ? 'No indicator on the chart yet.' : 'No indicators match.'}</div>`;
    const n = items.reduce((t, i) => t + onChart(i), 0);
    countEl.textContent = `${n} indicator${n === 1 ? '' : 's'} on the chart`;
  };
  const rowHtml = (i: MenuItem, wide: boolean) => {
      const n = onChart(i), fav = favs.has(i.id), d = defaults.get(i.id) || '';
      const where = wide ? ` · ${i.kind === 'Flow' ? 'Flow · ' : ''}${esc(i.group)}` : '';
      return `<div class="im-row" role="listitem" tabindex="0" data-id="${esc(i.id)}"><button type="button" class="im-star${fav ? ' on' : ''}" data-star="${esc(i.id)}" aria-pressed="${fav}" aria-label="${fav ? 'Remove from' : 'Add to'} favorites">${STAR}</button>`
        + `<div><div class="nm"><span class="nmt">${esc(i.name)}</span>${i.kind === 'Base' ? '' : `<small>${esc(i.id)}</small>`}${n ? `<em>${i.kind === 'Base' ? 'On chart' : `${n} on chart`}</em>` : ''}</div>`
        + `<div class="pa">${esc(d || (i.kind === 'Base' ? 'Volume bars under the price chart' : 'No settings'))}</div></div>`
        + `<div class="mt">${esc(i.place)}<span>${esc(unitText(i.unit))}${where}</span></div>`
        + `<button type="button" class="im-add" data-add="${esc(i.id)}" aria-label="Add ${esc(i.name)}">Add</button></div>`;
  };
  const byId = (id: string) => items.find(i => i.id === id)!;
  let toastTimer: any = 0;
  const note = (text: string) => {
    toast.textContent = text; toast.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 1600);
  };
  const add = (i: MenuItem) => {
    if (i.kind === 'Base') { if (volCtl.removed) volCtl.setRemoved(false); note(volCtl.removed ? `${i.name} could not be added` : `${i.name} is on the chart`) }
    else if (Ind.byName[i.name]) { const before = Ind.countOf(Ind.byName[i.name]); Ind.add(Ind.byName[i.name]);
      note(Ind.countOf(Ind.byName[i.name]) > before ? `${i.name} added` : `${i.name} could not be added`) }
    render();
    (list.querySelector(`.im-row[data-id="${CSS.escape(i.id)}"]`) as HTMLElement | null)?.focus({ preventScroll:true });
  };
  const showTip = (row: HTMLElement) => {
    const i = byId(row.dataset.id as string);
    if (!i.tip) { hideTip(); return }
    tip.innerHTML = `<b>${esc(i.name)}</b>${esc(i.tip)}`;
    tip.hidden = false;
    const r = (row.querySelector('.nmt') as HTMLElement).getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let l = r.left; if (l + w > innerWidth - 8) l = innerWidth - w - 8;
    let t = r.bottom + 6; if (t + h > innerHeight - 8) t = r.top - h - 6;
    tip.style.left = Math.max(8, l) + 'px'; tip.style.top = Math.max(8, t) + 'px';
  };
  const hideTip = () => { tip.hidden = true };
  const open = (o: boolean) => {
    dlg.hidden = !o; btn.setAttribute('aria-expanded', String(o)); hideTip();
    if (o) { query = ''; search.value = ''; render(); fitInView(dlg.querySelector('.im-box')); search.focus() } else btn.focus();
  };

  btn.addEventListener('click', (e: Event) => { e.stopImmediatePropagation(); open(dlg.hidden) }, true);
  (dlg.querySelector('.im-x') as HTMLElement).onclick = () => open(false);
  dlg.addEventListener('pointerdown', (e: any) => { if (e.target === dlg) open(false) });   // the backdrop
  nav.addEventListener('click', (e: any) => {
    const b = e.target.closest('[data-g]'); if (!b) return;
    const to = b.dataset.g, wasSpy = spyMode();
    query = ''; search.value = '';
    if (to === 'chart' || to === 'fav') { group = to; render(); list.scrollTop = 0; return }
    group = to;
    if (!wasSpy) render();                    // from a filtered view back to the full list
    mark(to); scrollToGroup(to);
  });
  list.addEventListener('scroll', spy, { passive:true });
  search.addEventListener('input', () => { query = search.value; render(); list.scrollTop = 0 });
  initResize(dlg.querySelector('.im-box') as HTMLElement, dlg.querySelector('.im-body') as HTMLElement);
  search.addEventListener('keydown', (e: KeyboardEvent) => {
    const first = list.querySelector('.im-row[data-id]') as HTMLElement | null;
    if (e.key === 'Enter' && first) { e.preventDefault(); add(byId(first.dataset.id as string)); search.focus() }
    else if (e.key === 'ArrowDown' && first) { e.preventDefault(); first.focus() }
  });
  list.addEventListener('click', (e: any) => {
    const s = e.target.closest('[data-star]');
    if (s) { const id = s.dataset.star; favs.has(id) ? favs.delete(id) : favs.add(id); saveFavs(); render(); return }
    const r = e.target.closest('.im-row[data-id]'); if (r) add(byId(r.dataset.id));
  });
  list.addEventListener('keydown', (e: any) => {
    const r = e.target.closest('.im-row[data-id]'); if (!r) return;
    if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest('button') && e.target.closest('[data-star]')) return; e.preventDefault(); add(byId(r.dataset.id)) }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const all = [...list.querySelectorAll('.im-row[data-id]')] as HTMLElement[], k = all.indexOf(r);
      if (e.key === 'ArrowUp' && k === 0) search.focus(); else all[Math.max(0, Math.min(all.length - 1, k + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus();
    }
  });
  list.addEventListener('pointerover', (e: any) => {
    const n = e.target.closest('.im-row[data-id] .nm');
    n ? showTip(n.closest('.im-row')) : hideTip();
  });
  list.addEventListener('pointerleave', hideTip); list.addEventListener('scroll', hideTip, { passive:true });
  document.addEventListener('keydown', e => {
    if (dlg.hidden) return;
    if (e.key === 'Escape') { open(false); return }
    if (e.key === '/' && document.activeElement !== search && !(e.target as HTMLElement).closest?.('input,textarea,select')) { e.preventDefault(); search.focus() }
  });
  volCtl.onChange = () => { if (!dlg.hidden) render() };
  Ind.onChange = () => { if (!dlg.hidden) render() };
  return { dlg, items };
}

/* user 2026-11-01 (Opsi A): the box is resized by its right edge, its bottom edge and its bottom-right corner (a
   double-click on the corner fills the window, again restores it), and the group list by the divider beside it. The
   sizes are kept in the browser. The left edge stays where it is while the right side grows. */
function initResize(box: HTMLElement, body: HTMLElement) {
  const MIN_W = 560, MIN_H = 380, NAV_MIN = 140, NAV_MAX = 360;
  const read = (k: string) => { try { return JSON.parse(store.get(k) || 'null') } catch { return null } };
  const apply = (w: number, h: number) => {
    box.style.width = Math.round(Math.max(MIN_W, Math.min(innerWidth - 16, w))) + 'px';
    box.style.height = Math.round(Math.max(MIN_H, Math.min(innerHeight - 16, h))) + 'px';
  };
  const saved = read(SIZE_KEY);
  if (saved && saved.w && saved.h) apply(saved.w, saved.h);
  const navW = read(NAV_KEY);
  if (typeof navW === 'number') body.style.setProperty('--im-nav', Math.max(NAV_MIN, Math.min(NAV_MAX, navW)) + 'px');
  const shift = () => shiftOf(box);
  let before: { w: number; h: number; t: string } | null = null;
  const drag = (el: HTMLElement, onMove: (dx: number, dy: number, r0: DOMRect) => void, done: () => void) =>
    el.addEventListener('pointerdown', (e: PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault(); e.stopPropagation(); el.setPointerCapture(e.pointerId);
      const r0 = box.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
      const move = (ev: PointerEvent) => onMove(ev.clientX - x0, ev.clientY - y0, r0);
      const up = () => { el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); done() };
      el.addEventListener('pointermove', move); el.addEventListener('pointerup', up);
    });
  const save = () => { const r = box.getBoundingClientRect(); store.set(SIZE_KEY, JSON.stringify({ w:r.width, h:r.height })) };
  /* the box is centred: growing by d moves both edges d/2, so it is shifted d/2 to keep its left and top edges */
  const resizeBy = (r0: DOMRect, dw: number, dh: number, t0: number[]) => {
    apply(r0.width + dw, r0.height + dh);
    const r = box.getBoundingClientRect();
    box.style.translate = `${t0[0] + (r.width - r0.width) / 2}px ${t0[1] + (r.height - r0.height) / 2}px`;
  };
  for (const [sel, wx, hy] of [['.im-rz-r', 1, 0], ['.im-rz-b', 0, 1], ['.im-rz-c', 1, 1]] as const) {
    const el = box.querySelector(sel) as HTMLElement; let t0 = [0, 0];
    el.addEventListener('pointerdown', () => { t0 = shift() }, true);
    drag(el, (dx, dy, r0) => resizeBy(r0, dx * wx, dy * hy, t0), save);
  }
  const corner = box.querySelector('.im-rz-c') as HTMLElement;
  const toggleFull = () => {
    if (before) { box.style.width = before.w + 'px'; box.style.height = before.h + 'px'; box.style.translate = before.t; before = null }
    else { const r = box.getBoundingClientRect(); before = { w:r.width, h:r.height, t:box.style.translate }; box.style.translate = ''; apply(innerWidth - 16, innerHeight - 16) }
    save();
  };
  corner.addEventListener('dblclick', toggleFull);
  corner.addEventListener('keydown', (e: KeyboardEvent) => { if (e.key === 'Enter') toggleFull() });
  const split = body.querySelector('.im-split') as HTMLElement; let n0 = 0;
  split.addEventListener('pointerdown', () => { n0 = (body.querySelector('.im-nav') as HTMLElement).getBoundingClientRect().width }, true);
  const setNav = (w: number) => { const v = Math.round(Math.max(NAV_MIN, Math.min(NAV_MAX, w))); body.style.setProperty('--im-nav', v + 'px'); store.set(NAV_KEY, String(v)) };
  drag(split, dx => setNav(n0 + dx), () => {});
  split.addEventListener('keydown', (e: KeyboardEvent) => {
    const w = (body.querySelector('.im-nav') as HTMLElement).getBoundingClientRect().width;
    if (e.key === 'ArrowLeft') setNav(w - 16); else if (e.key === 'ArrowRight') setNav(w + 16);
  });
}
