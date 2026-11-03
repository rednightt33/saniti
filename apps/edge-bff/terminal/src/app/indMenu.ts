/* EXEC-IND-CARDS IC1 (user go 2026-11-01: "jalankan TERMINAL-IND-CARDS as well"; mockup
   verification/terminal_api/indicator_cards/indicator_cards_review.html, approved 2026-11-01 with the bigger star): the
   indicator menu as TradingView's "Indicators, metrics, and strategies": groups on the left (Favorites, All, the
   technical categories, the Flow families), a list with a favourite star, name and code, group, place and unit, a short
   tooltip on hover (decision "1A"), and the info button that opens the indicator's card (IC2). Live page only; the
   fixture keeps the reference's popover (1:1 check). Nothing is listed by hand: the rows come from the Terminal's
   registries (indRegistry.json, flowRegistry.json). */
import type { Ctx } from './context';
import { $, store } from './context';
import { draggable, fitInView, shiftOf } from './draggable';
import { FLOW_REG, SINGLE_SECURITY } from './flowIndicators';
import { ALL_INPUTS, fits, inputsOf, needsOf, type Input } from '../data/inputs';

export interface MenuItem { id: string; name: string; group: string; kind: 'Technical' | 'Flow' | 'Base'; place: string; unit: string; tip: string }

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const FAV_KEY = 'ml.ind.favs', KIND_KEY = 'ml.ind.kind', SIZE_KEY = 'ml.ind.box', NAV_KEY = 'ml.ind.navw';

/** where a Flow indicator is drawn (flowRegistry `place`): its own pane, the price axis, or a mark under the candles */
export const flowPlace = (place: string) => place === 'pane' ? 'Panel' : 'Overlay';

/** the menu's rows from the registries: the technical indicators by category, the base volume histogram, and the Flow
    indicators by family, in the registries' order */
/** the menu's rows for a ticker with the inputs `have` (ERRORS M332: an indicator the ticker cannot feed is not offered,
    data/inputs.ts; a bond: no Flow, no volume) */
export function menuItems(indReg: any[], flowReg: { families: string[]; indicators: any[] }, have: ReadonlySet<Input> = ALL_INPUTS): MenuItem[] {
  const group = (cat: string) => cat === 'PriceVolume' ? 'Price & Volume' : cat.replace(/([a-z])([A-Z])/g, '$1 & $2');
  const out: MenuItem[] = indReg.filter(r => fits(needsOf({ reg:r }), have)).map(r => ({ id:r.id, name:r.name, group:group(r.cat), kind:'Technical', place:r.zone === 'overlay' ? 'Overlay' : 'Panel',
    unit:r.unit || '', tip:r.tip || '' }));
  const vol = out.findIndex(i => i.group === 'Volume');
  if (have.has('V')) out.splice(vol < 0 ? out.length : vol, 0, { id:'VOL', name:'Volume', group:'Volume', kind:'Base', place:'Panel', unit:'shares',
    tip:'Batang volume transaksi harian di bagian bawah chart harga.' });
  if (have.has('flow')) for (const f of flowReg.families) for (const r of flowReg.indicators.filter(x => x.family === f))
    if (fits(needsOf({ flow:true, single:SINGLE_SECURITY.has(r.id) }), have)) out.push({ id:r.id, name:r.name, group:f, kind:'Flow', place:flowPlace(r.place), unit:r.unit || '', tip:r.tip || '' });
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
  if (q) return items.filter(i => `${i.name} ${i.id} ${i.group} ${i.kind}`.toLowerCase().includes(q));
  if (group === 'fav') return items.filter(i => favs.has(i.id));
  if (group === 'all') return items;
  const [k, g] = [group.slice(0, 1), group.slice(2)];
  return items.filter(i => (k === 'f' ? i.kind === 'Flow' : i.kind !== 'Flow') && i.group === g);
}

export function initIndMenu(ctx: Ctx, openCard: (item: MenuItem) => void) {
  const { IND_REG, Ind, volCtl } = ctx;
  const items = menuItems(IND_REG as any[], FLOW_REG as any, inputsOf(ctx.M));
  const groupsOf = (kind: 'Technical' | 'Flow') => [...new Set(items.filter(i => kind === 'Flow' ? i.kind === 'Flow' : i.kind !== 'Flow').map(i => i.group))];
  let favs = new Set<string>();
  try { favs = new Set(JSON.parse(store.get(FAV_KEY) || '[]')) } catch { /* none saved */ }
  const saveFavs = () => store.set(FAV_KEY, JSON.stringify([...favs]));
  let group = favs.size ? 'fav' : 'all', query = '';
  const hasFlow = items.some(i => i.kind === 'Flow');
  let kind = (store.get(KIND_KEY) as KindFilter) || 'all';
  if (!['all', 'Technical', 'Flow'].includes(kind) || (kind === 'Flow' && !hasFlow)) kind = 'all';

  const btn = $('indBtn'), old = $('indPop');
  old.hidden = true;
  const dlg = document.createElement('div');
  dlg.className = 'im'; dlg.id = 'indMenu'; dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true');
  dlg.setAttribute('aria-label', 'Indicators'); dlg.hidden = true;
  dlg.innerHTML = `<div class="im-box">
      <div class="im-head"><h3>Indicators</h3><button type="button" class="im-x" aria-label="Close indicators">×</button></div>
      <div class="im-search"><svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2 17 17"/></svg>
        <input type="search" id="imSearch" placeholder="Search indicators" autocomplete="off" aria-label="Search indicators">
        <div class="im-seg" role="group" aria-label="Group type">${(['all', 'Technical', 'Flow'] as KindFilter[]).filter(k => k !== 'Flow' || hasFlow).map(k => `<button type="button" data-kind="${k}">${k === 'all' ? 'All types' : k}</button>`).join('')}</div></div>
      <div class="im-body"><nav class="im-nav" aria-label="Indicator groups"></nav><div class="im-split" role="separator" aria-orientation="vertical" aria-label="Resize the group list" tabindex="0"></div><div class="im-list" role="list"></div></div>
      <div class="im-rz im-rz-r" aria-hidden="true"></div><div class="im-rz im-rz-b" aria-hidden="true"></div>
      <div class="im-rz im-rz-c" role="button" tabindex="0" aria-label="Resize the indicators box; double-click to fill the window" title="Drag to resize · double-click to fill the window"></div>
      <aside class="im-detail" aria-label="Indicator card" hidden><div class="im-detail-h"><span class="grow">Indicator card</span>
        <button type="button" class="im-dx" aria-label="Close the card">×</button></div><div class="im-detail-b"></div></aside>
    </div>`;
  draggable(dlg.querySelector('.im-box'), dlg.querySelector('.im-head'));      // user 2026-11-01: moved by its header
  document.body.appendChild(dlg);
  const nav = dlg.querySelector('.im-nav') as HTMLElement, list = dlg.querySelector('.im-list') as HTMLElement;
  const search = dlg.querySelector('#imSearch') as HTMLInputElement, detail = dlg.querySelector('.im-detail') as HTMLElement;
  const tip = document.createElement('div'); tip.className = 'im-tip'; tip.hidden = true; document.body.appendChild(tip);

  const onChart = (i: MenuItem) => i.kind === 'Base' ? !volCtl.removed : Ind.byName[i.name] ? Ind.countOf(Ind.byName[i.name]) : 0;
  const navHtml = () => {
    const b = (id: string, label: string, n: number) =>
      `<button type="button" data-g="${esc(id)}" class="${group === id && !query ? 'on' : ''}">${label}<span class="cnt">${n}</span></button>`;
    const count = (k: string, g: string) => visibleItems(items, `${k}:${g}`, '', favs).length;
    // user 2026-11-01: the group types as badges (Personal, Technical, Flow); the type filter hides the other type
    const title = (t: string) => `<div class="im-title"><span class="im-badge">${t}</span></div>`;
    return `${title('Personal')}${b('fav', '<span class="im-star-ico">★</span> Favorites', visibleItems(items, 'fav', '', favs, kind).length)}${b('all', 'All', visibleItems(items, 'all', '', favs, kind).length)}`
      + (kind !== 'Flow' ? `${title('Technical')}${groupsOf('Technical').map(g => b(`t:${g}`, esc(g), count('t', g))).join('')}` : '')
      + (kind !== 'Technical' && groupsOf('Flow').length ? `${title('Flow')}${groupsOf('Flow').map(g => b(`f:${g}`, esc(g), count('f', g))).join('')}` : '');
  };
  const render = () => {
    if ((kind === 'Flow' && group.startsWith('t:')) || (kind === 'Technical' && group.startsWith('f:'))) group = 'all';
    nav.innerHTML = navHtml();
    dlg.querySelectorAll<HTMLElement>('[data-kind]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.kind === kind)));
    const rows = visibleItems(items, group, query, favs, kind);
    list.innerHTML = `<div class="im-row hd" role="presentation"><span></span><span>Name</span><span>Group</span><span>Place</span><span>Unit</span><span></span></div>`
      + (rows.length ? rows.map(i => {
        const n = onChart(i), fav = favs.has(i.id);
        return `<div class="im-row" role="listitem" tabindex="0" data-id="${esc(i.id)}"><button type="button" class="im-star${fav ? ' on' : ''}" data-star="${esc(i.id)}" aria-pressed="${fav}" aria-label="${fav ? 'Remove from' : 'Add to'} favorites">${fav ? '★' : '☆'}</button>`
          + `<span class="nm">${esc(i.name)}<small>${esc(i.kind === 'Base' ? '' : i.id)}</small>${n ? `<em>${i.kind === 'Base' ? 'On chart' : `${n} on chart`}</em>` : ''}</span>`
          + `<span class="gr">${i.kind === 'Flow' ? 'Flow · ' : ''}${esc(i.group)}</span><span class="pl">${esc(i.place)}</span><span class="un">${esc(unitText(i.unit))}</span>`
          + `<button type="button" class="im-info" data-info="${esc(i.id)}" aria-label="How ${esc(i.name)} works">i</button></div>`;
      }).join('') : `<div class="im-empty">${group === 'fav' && !query ? 'No favorites yet: star an indicator to keep it here.' : 'No indicators match.'}</div>`);
  };
  const byId = (id: string) => items.find(i => i.id === id)!;
  const add = (i: MenuItem) => {
    if (i.kind === 'Base') { if (volCtl.removed) volCtl.setRemoved(false) }
    else if (Ind.byName[i.name]) Ind.add(Ind.byName[i.name]);
    render();
    (list.querySelector(`.im-row[data-id="${CSS.escape(i.id)}"]`) as HTMLElement | null)?.focus();
  };
  const showTip = (row: HTMLElement) => {
    const i = byId(row.dataset.id as string);
    tip.innerHTML = `<b>${esc(i.name)}</b>${esc(i.tip)}<div class="hint">Click <span class="im-i">i</span> for how it works, with an example.</div>`;
    tip.hidden = false;
    const r = (row.querySelector('.nm') as HTMLElement).getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    let l = r.left + 40; if (l + w > innerWidth - 8) l = innerWidth - w - 8;
    let t = r.bottom + 6; if (t + h > innerHeight - 8) t = r.top - h - 6;
    tip.style.left = Math.max(8, l) + 'px'; tip.style.top = Math.max(8, t) + 'px';
  };
  const hideTip = () => { tip.hidden = true };
  const open = (o: boolean) => {
    dlg.hidden = !o; btn.setAttribute('aria-expanded', String(o)); hideTip();
    if (o) { query = ''; search.value = ''; render(); fitInView(dlg.querySelector('.im-box')); search.focus() } else { detail.hidden = true; btn.focus() }
  };

  btn.addEventListener('click', (e: Event) => { e.stopImmediatePropagation(); open(dlg.hidden) }, true);
  (dlg.querySelector('.im-x') as HTMLElement).onclick = () => open(false);
  (dlg.querySelector('.im-dx') as HTMLElement).onclick = () => { detail.hidden = true };
  dlg.addEventListener('pointerdown', (e: any) => { if (e.target === dlg) open(false) });   // the backdrop
  nav.addEventListener('click', (e: any) => {
    const b = e.target.closest('[data-g]'); if (!b) return;
    group = b.dataset.g; query = ''; search.value = ''; render();
  });
  search.addEventListener('input', () => { query = search.value; render() });
  dlg.querySelectorAll<HTMLElement>('[data-kind]').forEach(b => b.onclick = () => { kind = b.dataset.kind as KindFilter; store.set(KIND_KEY, kind); render() });
  initResize(dlg.querySelector('.im-box') as HTMLElement, dlg.querySelector('.im-body') as HTMLElement);
  search.addEventListener('keydown', (e: KeyboardEvent) => {
    const first = list.querySelector('.im-row[data-id]') as HTMLElement | null;
    if (e.key === 'Enter' && first) { e.preventDefault(); add(byId(first.dataset.id as string)); search.focus() }
    else if (e.key === 'ArrowDown' && first) { e.preventDefault(); first.focus() }
  });
  list.addEventListener('click', (e: any) => {
    const s = e.target.closest('[data-star]');
    if (s) { const id = s.dataset.star; favs.has(id) ? favs.delete(id) : favs.add(id); saveFavs(); render(); return }
    const inf = e.target.closest('[data-info]');
    if (inf) { hideTip(); openCard(byId(inf.dataset.info)); return }
    const r = e.target.closest('.im-row[data-id]'); if (r) add(byId(r.dataset.id));
  });
  list.addEventListener('keydown', (e: any) => {
    const r = e.target.closest('.im-row[data-id]'); if (!r) return;
    if (e.key === 'Enter' || e.key === ' ') { if (e.target.closest('button')) return; e.preventDefault(); add(byId(r.dataset.id)) }
    else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      const all = [...list.querySelectorAll('.im-row[data-id]')] as HTMLElement[], k = all.indexOf(r);
      if (e.key === 'ArrowUp' && k === 0) search.focus(); else all[Math.max(0, Math.min(all.length - 1, k + (e.key === 'ArrowDown' ? 1 : -1)))]?.focus();
    }
  });
  list.addEventListener('pointerover', (e: any) => {
    const r = e.target.closest('.im-row[data-id]');
    !r || e.target.closest('.im-star') ? hideTip() : showTip(r);
  });
  list.addEventListener('pointerleave', hideTip); list.addEventListener('scroll', hideTip, { passive:true });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || dlg.hidden) return;
    if (!detail.hidden) { detail.hidden = true; return }
    open(false);
  });
  volCtl.onChange = () => { if (!dlg.hidden) render() };
  Ind.onChange = () => { if (!dlg.hidden) render() };
  return { dlg, detail, detailBody:dlg.querySelector('.im-detail-b') as HTMLElement, items };
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
