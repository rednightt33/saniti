/* EXEC-IND-CARDS IC1 (user go 2026-11-01: "jalankan TERMINAL-IND-CARDS as well"; mockup
   verification/terminal_api/indicator_cards/indicator_cards_review.html, approved 2026-11-01 with the bigger star): the
   indicator menu as TradingView's "Indicators, metrics, and strategies": groups on the left (Favorites, All, the
   technical categories, the Flow families), a list with a favourite star, name and code, group, place and unit, a short
   tooltip on hover (decision "1A"), and the info button that opens the indicator's card (IC2). Live page only; the
   fixture keeps the reference's popover (1:1 check). Nothing is listed by hand: the rows come from the Terminal's
   registries (indRegistry.json, flowRegistry.json). */
import type { Ctx } from './context';
import { $, store } from './context';
import { FLOW_REG } from './flowIndicators';

export interface MenuItem { id: string; name: string; group: string; kind: 'Technical' | 'Flow' | 'Base'; place: string; unit: string; tip: string }

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const FAV_KEY = 'ml.ind.favs';

/** where a Flow indicator is drawn (flowRegistry `place`): its own pane, the price axis, or a mark under the candles */
export const flowPlace = (place: string) => place === 'pane' ? 'Panel' : 'Overlay';

/** the menu's rows from the registries: the technical indicators by category, the base volume histogram, and (not on a
    bond's page: no broker data) the Flow indicators by family, in the registries' order */
export function menuItems(indReg: any[], flowReg: { families: string[]; indicators: any[] }, withFlow: boolean): MenuItem[] {
  const group = (cat: string) => cat === 'PriceVolume' ? 'Price & Volume' : cat.replace(/([a-z])([A-Z])/g, '$1 & $2');
  const out: MenuItem[] = indReg.map(r => ({ id:r.id, name:r.name, group:group(r.cat), kind:'Technical', place:r.zone === 'overlay' ? 'Overlay' : 'Panel',
    unit:r.unit || '', tip:r.tip || '' }));
  const vol = out.findIndex(i => i.group === 'Volume');
  out.splice(vol < 0 ? out.length : vol, 0, { id:'VOL', name:'Volume', group:'Volume', kind:'Base', place:'Panel', unit:'shares',
    tip:'Batang volume transaksi harian di bagian bawah chart harga.' });
  if (withFlow) for (const f of flowReg.families) for (const r of flowReg.indicators.filter(x => x.family === f))
    out.push({ id:r.id, name:r.name, group:f, kind:'Flow', place:flowPlace(r.place), unit:r.unit || '', tip:r.tip || '' });
  return out;
}

/** the rows a group (or a search) shows: a search looks at the name, code, group and kind of every row */
export function visibleItems(items: MenuItem[], group: string, query: string, favs: Set<string>): MenuItem[] {
  const q = query.trim().toLowerCase();
  if (q) return items.filter(i => `${i.name} ${i.id} ${i.group} ${i.kind}`.toLowerCase().includes(q));
  if (group === 'fav') return items.filter(i => favs.has(i.id));
  if (group === 'all') return items;
  const [k, g] = [group.slice(0, 1), group.slice(2)];
  return items.filter(i => (k === 'f' ? i.kind === 'Flow' : i.kind !== 'Flow') && i.group === g);
}

export function initIndMenu(ctx: Ctx, openCard: (item: MenuItem) => void) {
  const { IND_REG, Ind, volCtl } = ctx;
  const items = menuItems(IND_REG as any[], FLOW_REG as any, !ctx.M.fixedIncome);
  const groupsOf = (kind: 'Technical' | 'Flow') => [...new Set(items.filter(i => kind === 'Flow' ? i.kind === 'Flow' : i.kind !== 'Flow').map(i => i.group))];
  let favs = new Set<string>();
  try { favs = new Set(JSON.parse(store.get(FAV_KEY) || '[]')) } catch { /* none saved */ }
  const saveFavs = () => store.set(FAV_KEY, JSON.stringify([...favs]));
  let group = favs.size ? 'fav' : 'all', query = '';

  const btn = $('indBtn'), old = $('indPop');
  old.hidden = true;
  const dlg = document.createElement('div');
  dlg.className = 'im'; dlg.id = 'indMenu'; dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true');
  dlg.setAttribute('aria-label', 'Indicators'); dlg.hidden = true;
  dlg.innerHTML = `<div class="im-box">
      <div class="im-head"><h3>Indicators</h3><button type="button" class="im-x" aria-label="Close indicators">×</button></div>
      <div class="im-search"><svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13.2 13.2 17 17"/></svg>
        <input type="search" id="imSearch" placeholder="Search indicators" autocomplete="off" aria-label="Search indicators"></div>
      <div class="im-body"><nav class="im-nav" aria-label="Indicator groups"></nav><div class="im-list" role="list"></div></div>
      <aside class="im-detail" aria-label="Indicator card" hidden><div class="im-detail-h"><span class="grow">Indicator card</span>
        <button type="button" class="im-dx" aria-label="Close the card">×</button></div><div class="im-detail-b"></div></aside>
    </div>`;
  document.body.appendChild(dlg);
  const nav = dlg.querySelector('.im-nav') as HTMLElement, list = dlg.querySelector('.im-list') as HTMLElement;
  const search = dlg.querySelector('#imSearch') as HTMLInputElement, detail = dlg.querySelector('.im-detail') as HTMLElement;
  const tip = document.createElement('div'); tip.className = 'im-tip'; tip.hidden = true; document.body.appendChild(tip);

  const onChart = (i: MenuItem) => i.kind === 'Base' ? !volCtl.removed : Ind.byName[i.name] ? Ind.countOf(Ind.byName[i.name]) : 0;
  const navHtml = () => {
    const b = (id: string, label: string, n: number) =>
      `<button type="button" data-g="${esc(id)}" class="${group === id && !query ? 'on' : ''}">${label}<span class="cnt">${n}</span></button>`;
    const count = (k: string, g: string) => visibleItems(items, `${k}:${g}`, '', favs).length;
    return `<div class="im-title">Personal</div>${b('fav', '<span class="im-star-ico">★</span> Favorites', favs.size)}${b('all', 'All', items.length)}`
      + `<div class="im-title">Technical</div>${groupsOf('Technical').map(g => b(`t:${g}`, esc(g), count('t', g))).join('')}`
      + (groupsOf('Flow').length ? `<div class="im-title">Flow</div>${groupsOf('Flow').map(g => b(`f:${g}`, esc(g), count('f', g))).join('')}` : '');
  };
  const render = () => {
    nav.innerHTML = navHtml();
    const rows = visibleItems(items, group, query, favs);
    list.innerHTML = `<div class="im-row hd" role="presentation"><span></span><span>Name</span><span>Group</span><span>Place</span><span>Unit</span><span></span></div>`
      + (rows.length ? rows.map(i => {
        const n = onChart(i), fav = favs.has(i.id);
        return `<div class="im-row" role="listitem" tabindex="0" data-id="${esc(i.id)}"><button type="button" class="im-star${fav ? ' on' : ''}" data-star="${esc(i.id)}" aria-pressed="${fav}" aria-label="${fav ? 'Remove from' : 'Add to'} favorites">${fav ? '★' : '☆'}</button>`
          + `<span class="nm">${esc(i.name)}<small>${esc(i.kind === 'Base' ? '' : i.id)}</small>${n ? `<em>${i.kind === 'Base' ? 'On chart' : `${n} on chart`}</em>` : ''}</span>`
          + `<span class="gr">${i.kind === 'Flow' ? 'Flow · ' : ''}${esc(i.group)}</span><span class="pl">${esc(i.place)}</span><span class="un">${esc(i.unit)}</span>`
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
    if (o) { query = ''; search.value = ''; render(); search.focus() } else { detail.hidden = true; btn.focus() }
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
