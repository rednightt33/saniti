/* EXEC-SCREENER-V21 layout: the filter side of the three-panel page (reference layout.js 44-82, 223-280, 301-324,
   616-637, 797-824, 1347-1373).
   - More filters is a centred dialog with a group list on the left that follows the scrolling panel ("Set only" hides
     the groups that are not set); the industry list can be narrowed to the included sectors, the mapping read from the
     universe rows (ctx.universe; no request);
   - the filter + presets bar folds to one summary line;
   - "Not available yet" lists what has no data, derived from the catalog's availability and the universe fields the
     page shows disabled (their reasons are texts.ts T);
   - a popover can be enlarged from its corner (sizes kept per browser).
   Rendering stays in universe-ui.ts; this module gives it the pieces and wires their events. */
import { esc, nf } from '../format.ts';
import { ctx, S, type UState } from '../state.ts';
import { LIST_TEXT, T } from '../texts.ts';
import { store } from '../storage.ts';
import { LKEYS } from './prefs.ts';

/* ---- More filters: group list ---------------------------------------------------------------------------- */
// EXEC-SCREENER-STOCK-LISTS: Index and Group follow Sector and Industry (universe-ui.ts listSec)
export const FKEYS = ['sector', 'industry', 'index', 'group', 'liq', 'metric', 'quality'] as const;
export type FKey = typeof FKEYS[number];
/** the groups More filters shows: Index and Group only with the catalog's lists, or while a list filter is set (a saved
    screen's, to be removed); without data they are under "Not available yet" like the other groups without data */
export const shownFKeys = (u: UState = S.universe): FKey[] => FKEYS.filter(k => (k !== 'index' && k !== 'group') || ctx.catalog?.stock_lists?.availability === 'AVAILABLE'
  || !!(u.indices_in?.length || u.indices_out?.length || u.groups_in?.length || u.groups_out?.length));
const FICON: Record<FKey, string> = {
  sector:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v9l7.8 4.5A9 9 0 1 1 12 3Z"/><path d="M15 3.5A9 9 0 0 1 20.5 12H15Z"/></svg>',
  industry:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 21V10l6 3V10l6 3V6l6-3v18Z"/></svg>',
  index:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V4M4 20h16M8 16l4-5 3 3 5-7"/></svg>',
  group:'<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="6" r="3"/><circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/><path d="M10.5 8.6 7.5 14.4M13.5 8.6l3 5.8M9 17h6"/></svg>',
  liq:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c3 4 6 7 6 11a6 6 0 0 1-12 0c0-4 3-7 6-11Z"/></svg>',
  metric:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 19h16M7 15l3-4 3 2 4-6"/></svg>',
  quality:'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 4 6v6c0 4.4 3.4 8 8 9 4.6-1 8-4.6 8-9V6Z"/><path d="m9 12 2 2 4-4"/></svg>',
};
const rpB = (v: number) => `Rp ${nf(v / 1e9, v % 1e9 ? 1 : 0)}B`;
/** a group's name, how many settings it holds and what they are (the left list of More filters) */
export function fsum(k: FKey, u: UState = S.universe): { l: string; n: number; d: string } {
  if (k === 'sector') { const a = u.sectors_in || [], b = u.sectors_out || []; return { l:'Sectors', n:a.length + b.length, d:[...a, ...b.map(x => 'not ' + x)].join(', ') || 'All sectors' } }
  if (k === 'industry') { const a = u.industries_in || [], b = u.industries_out || []; return { l:'Industries', n:a.length + b.length, d:[...a, ...b.map(x => 'not ' + x)].join(', ') || 'All industries' } }
  if (k === 'index' || k === 'group') {
    const kind = k === 'index' ? 'INDEX' : 'KONGLO', a = (k === 'index' ? u.indices_in : u.groups_in) || [], b = (k === 'index' ? u.indices_out : u.groups_out) || [];
    const name = (c: string) => ctx.catalog?.stock_lists?.lists.find(l => l.kind === kind && l.code === c)?.name || c;
    return { l:LIST_TEXT[kind].title, n:a.length + b.length, d:[...a.map(name), ...b.map(x => 'not ' + name(x))].join(', ') || `All ${LIST_TEXT[kind].many}` };
  }
  if (k === 'liq') {
    const p = [u.adv20_min_idr != null ? 'Avg value ≥ ' + rpB(u.adv20_min_idr) : null, u.price_min != null ? 'Price ≥ Rp ' + nf(u.price_min) : null].filter(Boolean) as string[];
    return { l:'Liquidity & price', n:p.length, d:p.join(' · ') || 'No floor' };
  }
  if (k === 'metric') { const m = u.filters.length; return { l:'Metric filters', n:m, d:m ? `${m} filter${m > 1 ? 's' : ''}` : 'None' } }
  const q = [u.traded_on_eval_date ? 'Hides stale' : null, u.exclude_price_breaks ? 'Hides price breaks' : null].filter(Boolean) as string[];
  return { l:'Stale stocks and price breaks', n:q.length, d:q.join(' · ') || 'Shows all, with remarks' };
}
let setOnly = false;
export function fnavHtml(): string {
  const items = shownFKeys().map(k => ({ k, ...fsum(k) }));
  return `<nav class="fnav" aria-label="Filter groups"><div class="navtop"><span>Groups</span><label><input type="checkbox" data-fonly ${setOnly ? 'checked' : ''}> Set only</label></div>`
    + items.map(t => `<a href="#f-${t.k}" data-fk="${t.k}" class="${t.n ? '' : 'unset'}" title="${esc(t.d)}"><span class="ic">${FICON[t.k]}</span><b>${esc(t.l)}</b><small>${esc(t.d)}</small><i class="n ${t.n ? '' : 'z'}" aria-label="${t.n} set">${t.n}</i></a>`).join('')
    + '<span class="mini" aria-hidden="true"><i></i></span></nav>';
}
export const drawerClass = () => setOnly ? 'only' : '';
export const unsetClass = (k: FKey) => fsum(k).n ? '' : 'unset';

/** mark the group under the scroll in the list (and the small scroll gauge) */
export function spy(dr: Element) {
  const b = dr.querySelector('.drawer-b') as HTMLElement | null, nav = dr.querySelector('.fnav'); if (!b || !nav) return;
  const secs = [...b.querySelectorAll<HTMLElement>(':scope>.dsec')].filter(s => s.offsetParent !== null); if (!secs.length) return;
  const top = b.getBoundingClientRect().top + 32;
  let c = secs[0]; for (const s of secs) if (s.getBoundingClientRect().top <= top) c = s;
  if (b.scrollTop + b.clientHeight >= b.scrollHeight - 2) c = secs[secs.length - 1];
  nav.querySelectorAll<HTMLElement>('a').forEach(a => { const on = a.dataset.fk === c.dataset.k; a.classList.toggle('on', on); on ? a.setAttribute('aria-current', 'true') : a.removeAttribute('aria-current') });
  (nav.querySelector('a.on') as HTMLElement | null)?.scrollIntoView({ block:'nearest' });
  const mi = nav.querySelector('.mini i') as HTMLElement | null;
  if (mi) { const tr = mi.parentElement!.clientHeight, h = Math.max(16, tr * b.clientHeight / Math.max(1, b.scrollHeight)), f = b.scrollTop / Math.max(1, b.scrollHeight - b.clientHeight); mi.style.height = h + 'px'; mi.style.transform = `translateY(${f * (tr - h)}px)` }
}
const smooth = () => matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
/** scroll the dialog's panel to a group */
export function jumpTo(dr: Element, k: string) {
  const b = dr.querySelector('.drawer-b') as HTMLElement | null, s = b?.querySelector(`.dsec[data-k="${CSS.escape(k)}"]`) as HTMLElement | null;
  if (b && s) b.scrollTo({ top:s.offsetTop, behavior:smooth() as ScrollBehavior });
}

/* ---- industries narrowed to the included sectors (the mapping read from the universe rows) ------------------- */
let indScope = true;
function sectorsOf(): Map<string, Set<string>> {
  const m = new Map<string, Set<string>>();
  for (const r of ctx.universe?.rows || []) { if (!r.industry) continue; if (!m.has(r.industry)) m.set(r.industry, new Set()); if (r.sector) m.get(r.industry)!.add(r.sector) }
  return m;
}
export const indScopeHtml = () => {
  const u = S.universe, any = !!(u.sectors_in?.length || u.sectors_out?.length);
  return `<label class="ind-scope ${any ? '' : 'off'}" title="${any ? 'Show only industries that belong to the included sectors' : 'Pick a sector above to narrow this list'}"><span class="sw"><input type="checkbox" data-indscope ${indScope ? 'checked' : ''}><span></span></span>Only in selected sectors</label>`;
};
/** hide the industries outside the included (or inside the excluded) sectors; a checked industry always stays */
export function scopeIndustries(root: Element) {
  const sec = root.querySelector('.dsec[data-k="industry"]'); if (!sec) return;
  const u = S.universe, inc = u.sectors_in || [], exc = u.sectors_out || [], map = sectorsOf();
  const active = indScope && (inc.length > 0 || exc.length > 0);
  let shown = 0, total = 0;
  sec.querySelectorAll<HTMLLabelElement>('.indlist label').forEach(l => {
    const inp = l.querySelector('input[data-v]') as HTMLInputElement | null; if (!inp) return; total++;
    const ss = [...(map.get(inp.dataset.v!) || [])];
    const ok = !active || inp.checked || ((!inc.length || ss.some(x => inc.includes(x))) && !(ss.length && ss.every(x => exc.includes(x))));
    l.hidden = !ok; if (ok) shown++;
  });
  let note = sec.querySelector('.ind-note') as HTMLElement | null;
  if (!note) { note = document.createElement('p'); note.className = 'ind-note'; note.setAttribute('role', 'status'); sec.querySelector('.indlist')?.before(note) }
  note.hidden = !active;
  note.textContent = active ? `Showing ${shown} of ${total} industries${inc.length ? ' in ' + inc.join(', ') : ''}${exc.length ? (inc.length ? ',' : '') + ' outside ' + exc.join(', ') : ''}.` : '';
}

/** delegated events of the dialog (bound once on #drawerHost) */
export function bindFilterDialog(host: HTMLElement) {
  host.addEventListener('click', e => {
    const a = (e.target as HTMLElement).closest('.fnav a') as HTMLElement | null; if (!a) return;
    e.preventDefault(); const dr = a.closest('.drawer'); if (dr) jumpTo(dr, a.dataset.fk!);
  });
  host.addEventListener('change', e => {
    const t = e.target as HTMLInputElement, dr = t.closest('.drawer'); if (!dr) return;
    if (t.matches('[data-fonly]')) { e.stopPropagation(); setOnly = t.checked; dr.classList.toggle('only', setOnly); (dr.querySelector('.drawer-b') as HTMLElement).scrollTop = 0; spy(dr) }
    else if (t.matches('[data-indscope]')) { e.stopPropagation(); indScope = t.checked; scopeIndustries(dr); spy(dr) }
  }, true);
  host.addEventListener('scroll', e => { const t = e.target as HTMLElement; if (t.classList?.contains('drawer-b')) spy(t.closest('.drawer')!) }, { capture:true, passive:true });
  addEventListener('resize', () => { const dr = host.querySelector('.drawer'); if (dr) spy(dr) });
}

/* ---- the folded filter bar: one summary line ------------------------------------------------------------- */
export function summaryHtml(items: { label: string; value: string; on: boolean }[], chips: string[], preset: string | null, count: string): string {
  const star = '<svg class="ico s" viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9Z"/></svg>';
  const part = [...items.map(i => `<span class="us-i${i.on ? ' on' : ''}">${esc(i.label)} <b>${esc(i.value)}</b></span>`), ...chips.map(t => `<span class="us-i">${esc(t)}</span>`)];
  return `<button type="button" class="u-sum" data-act="uopen" title="Show filters and presets"><span class="us-l">Filters</span><span class="us-items">${part.join('<i class="us-dot"></i>')}</span>${preset ? `<span class="us-pre">${star}${esc(preset)}</span>` : ''}<span class="ucount us-c">${count}</span><span class="us-edit">Edit</span></button>`;
}

/* ---- Not available yet ------------------------------------------------------------------------------------ */
type NaGroup = [title: string, rows: [name: string, reason: string][]];
function naGroups(): NaGroup[] {
  // the universe fields the page shows without data (universe-ui.ts quick filters and More filters), with their reason
  // EXEC-SCREENER-STOCK-LISTS: index and group membership only while the catalog's lists are not available (its reason)
  const lists = ctx.catalog?.stock_lists, listsNa: [string, string][] = lists?.availability === 'AVAILABLE' ? [] : [[LIST_TEXT.na, lists?.reason || T.noIndex]];
  const out: NaGroup[] = [['Universe filters', [...listsNa, ['Listing board', T.noBoard], ['Market cap', T.noCap], ['Free float', T.noFreeFloat], ['Special notation', T.noNotation]]]];
  const by = new Map<string, { group: string; reason: string; names: string[] }>();
  for (const e of ctx.entries) {
    if (e.available) continue;
    const k = e.group + '|' + (e.reason || '');
    if (!by.has(k)) by.set(k, { group:e.group, reason:e.reason || 'Not available.', names:[] });
    by.get(k)!.names.push(e.label);
  }
  const rows: [string, string][] = [...by.values()].map(g => [`${g.group === 'Fundamental' ? 'Fundamentals' : g.group === 'PriceVolume' ? 'Price & volume' : g.group} · ${g.names.length} indicator${g.names.length > 1 ? 's' : ''}`, `${g.reason} (${g.names.slice(0, 5).join(', ')}${g.names.length > 5 ? ', …' : ''})`]);
  if (rows.length) out.push(['Conditions', rows]);
  return out;
}
export const naCount = () => naGroups().reduce((n, g) => n + g[1].length, 0);
export const naButtonHtml = () => `<button type="button" class="btn ghost na-btn" data-na aria-haspopup="dialog" aria-controls="naPop" aria-expanded="${!(document.getElementById('naPop')?.hidden ?? true)}">Not available yet <span class="count">${naCount()}</span></button>`;
let naOpener: HTMLElement | null = null;
export function toggleNa(anchor: HTMLElement) {
  const pop = document.getElementById('naPop')!;
  if (!pop.hidden) { closeNa(); return }
  pop.innerHTML = naGroups().map(([h, rows]) => `<h6>${esc(h)}</h6><div>${rows.map(([n, r]) => `<div class="na-row"><b>${esc(n)}</b><span>${esc(r)}</span></div>`).join('')}</div>`).join('');
  pop.tabIndex = -1; pop.hidden = false; naOpener = anchor; anchor.setAttribute('aria-expanded', 'true');
  const r = anchor.getBoundingClientRect();
  pop.style.top = r.bottom + 6 + 'px'; pop.style.left = Math.max(8, Math.min(r.left, innerWidth - pop.offsetWidth - 8)) + 'px';
  pop.focus({ preventScroll:true });
}
export function closeNa(restore = true) {
  const pop = document.getElementById('naPop'); if (!pop || pop.hidden) return;
  pop.hidden = true; naOpener?.setAttribute('aria-expanded', 'false');
  if (restore && naOpener && document.contains(naOpener)) naOpener.focus({ preventScroll:true });
  naOpener = null;
}
export function bindNa() {
  document.addEventListener('pointerdown', e => { const t = e.target as HTMLElement; if (!t.closest('#naPop,[data-na]')) closeNa(false) });
  document.getElementById('naPop')!.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); closeNa() } });
  addEventListener('scroll', () => closeNa(false), { passive:true });
}

/* ---- popover: enlarge from the corner (Sector, Liquidity) -------------------------------------------------- */
let PS: Record<string, { w: number; h: number }> = store.get(LKEYS.pops, {});
const savePS = () => store.set(LKEYS.pops, PS);
/** size the open popover as kept for its kind and give it a corner grip; called after renderPop */
export function dressPop(pop: HTMLElement, kind: string | null) {
  if (pop.hidden || !kind) return;
  const sz = PS[kind];
  pop.classList.toggle('sized', !!sz);
  pop.style.width = sz ? sz.w + 'px' : ''; pop.style.height = sz ? sz.h + 'px' : ''; pop.style.maxHeight = sz ? 'none' : '';
  if (!pop.querySelector('.pop-grip')) {
    const g = document.createElement('span'); g.className = 'pop-grip'; g.tabIndex = 0;
    g.setAttribute('role', 'separator'); g.setAttribute('aria-label', 'Resize this menu (arrow keys)'); g.title = 'Drag to resize · double-click to reset';
    pop.appendChild(g);
  }
}
export function bindPopResize(pop: HTMLElement, kind: () => string | null) {
  pop.addEventListener('pointerdown', e => {
    const g = (e.target as HTMLElement).closest('.pop-grip') as HTMLElement | null, k = kind(); if (!g || !k) return;
    e.preventDefault(); e.stopPropagation(); g.setPointerCapture(e.pointerId);
    const r = pop.getBoundingClientRect(), x0 = e.clientX, y0 = e.clientY;
    const mv = (ev: PointerEvent) => { PS[k] = { w:Math.round(Math.min(innerWidth - r.left - 8, Math.max(320, r.width + ev.clientX - x0))), h:Math.round(Math.min(innerHeight - r.top - 8, Math.max(240, r.height + ev.clientY - y0))) }; dressPop(pop, k) };
    const up = () => { g.removeEventListener('pointermove', mv); savePS() };
    g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up, { once:true }); g.addEventListener('pointercancel', up, { once:true });
  }, true);
  pop.addEventListener('dblclick', e => { const k = kind(); if (k && (e.target as HTMLElement).closest('.pop-grip')) { delete PS[k]; savePS(); dressPop(pop, k) } });
  pop.addEventListener('keydown', e => {
    const k = kind(); if (!k || !(e.target as HTMLElement).closest('.pop-grip')) return;
    const d = ({ ArrowRight:[24, 0], ArrowLeft:[-24, 0], ArrowDown:[0, 24], ArrowUp:[0, -24] } as Record<string, number[]>)[e.key]; if (!d) return;
    e.preventDefault(); e.stopPropagation();
    const r = pop.getBoundingClientRect(); PS[k] = { w:Math.max(320, r.width + d[0]), h:Math.max(240, r.height + d[1]) }; dressPop(pop, k); savePS();
  });
}
