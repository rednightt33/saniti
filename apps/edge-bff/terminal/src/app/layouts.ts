/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06: "layout dari layout ini bisa di-save dan bisa dibuka kapanpun ... auto save,
   kemudian make a copy, rename, create layout, dan open layout. Bagian download chart data tidak usah"; "di akun edge.
   Tidak usah mengganti saham."): named chart layouts of the EDGE owner, saved on edge-bff and opened on the ticker on
   screen.

   A layout is the chart's own settings: the stored values of LAYOUT_KEYS (indicators with their settings, visibility and
   fold, timeframe, chart type, Price/Return, Volume, Events, the bond price/yield choice, the Flow Timeline's filters,
   Cumulative, open/closed and height). Drawings stay per ticker and the right panel is not part of it. Opening a layout
   writes those values (a value the layout does not hold goes back to its default) and reloads the page on the same ticker,
   so every part restores itself the way it does after any reload.

   Every stored setting of the page is either a layout setting or listed in NOT_LAYOUT (tests/data/layouts.test.ts reads the
   source): a new setting has to be placed on one side. */
import type { Ctx } from './context';
import { $, store, storeWatch } from './context';
import { LayoutApiError, layoutsApi, newLayoutId, type LayoutMeta } from '../data/layoutsApi';

export const LAYOUT_KEYS = ['ml.ind.v1', 'ml.tf', 'ml.chart.style', 'ml.chart.mode', 'ml.vol.on', 'ml.vol.removed', 'ml.events.v1',
  'ml.fi.metric', 'ml.flow.filters', 'ml.flow.cum', 'ml.flow.collapsed', 'ml.flow.h', 'ml.flow.ratio'] as const;
/** stored settings that are not part of a layout (prefixes): the ticker, per-ticker drawings, the side panels and windows,
    the compared assets, the Indicators dialog's own preferences and the layout menu's own state */
export const NOT_LAYOUT = ['ml.symbol', 'ml.tfs', 'ml.draw.', 'ml.drawings', 'ml.stats.', 'ml.broker.', 'ml.acc.', 'ml.fd.', 'ml.win.',
  'ml.winst.', 'ml.assets.', 'ml.ind.favs', 'ml.ind.box', 'ml.ind.navw', 'ml.layout.'] as const;

const ACTIVE_KEY = 'ml.layout.active', AUTO_KEY = 'ml.layout.autosave', BASE_KEY = 'ml.layout.base', REBASE_KEY = 'ml.layout.rebase';
const RECENT = 5, AUTOSAVE_MS = 1500, SETTLE_MAX_MS = 8000;
const TF_LABEL: Record<string, string> = { '5m':'5M', '15m':'15M', '1h':'1H', '4h':'4H', D:'D', W:'W', M:'M' };

/** the layout settings as stored now (absent ones left out) */
export function snapshotOf(get: (k: string) => string | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of LAYOUT_KEYS) { const v = get(k); if (v !== null && v !== '') out[k] = v }
  return out;
}
/** one text per state, whatever the order of its keys (the unsaved-changes check) */
export const canonical = (s: Record<string, string>) => JSON.stringify(Object.keys(s).filter(k => (LAYOUT_KEYS as readonly string[]).includes(k)).sort().map(k => [k, s[k]]));
/** the menu's one line: timeframe and number of indicators */
export function summaryOf(s: Record<string, string>) {
  let n = 0; try { const a = JSON.parse(s['ml.ind.v1'] || '[]'); n = Array.isArray(a) ? a.length : 0 } catch { /* none */ }
  const tf = s['ml.tf'] || 'D';
  return `${TF_LABEL[tf] || tf} · ${n} indicator${n === 1 ? '' : 's'}`;
}
/** write a layout's settings; a layout setting it does not hold goes back to its default */
export function applyState(s: Record<string, string>, set: (k: string, v: string) => void, remove: (k: string) => void) {
  for (const k of LAYOUT_KEYS) { const v = s[k]; if (typeof v === 'string' && v !== '') set(k, v); else remove(k) }
}

interface Active { id: string; name: string; revision: number }
const esc = (t: string) => t.replace(/[&<>"]/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;' } as Record<string, string>)[c]);
const ICON = {
  chev:'<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8l4 4 4-4"/></svg>',
  copy:'<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><rect x="6.5" y="6.5" width="10" height="10" rx="1.6"/><path d="M13.5 6.5V4.6c0-.9-.7-1.6-1.6-1.6H4.6C3.7 3 3 3.7 3 4.6v7.3c0 .9.7 1.6 1.6 1.6h1.9"/></svg>',
  pen:'<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 16.5l1-4L13 4a1.8 1.8 0 0 1 2.6 0l.4.4a1.8 1.8 0 0 1 0 2.6l-8.5 8.5z"/><path d="M11.5 5.5l3 3"/></svg>',
  plus:'<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M10 3.5v13M3.5 10h13"/></svg>',
  folder:'<svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true"><path d="M2.8 5.2c0-.9.7-1.6 1.6-1.6h3.3l1.7 1.9h6.2c.9 0 1.6.7 1.6 1.6v7.6c0 .9-.7 1.6-1.6 1.6H4.4c-.9 0-1.6-.7-1.6-1.6z"/></svg>',
  star:'<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M10 2.6l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5L2.8 7.9l5-.7z"/></svg>',
  trash:'<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3.5 5.5h13M8 5.5V4h4v1.5M5.5 5.5l.8 10.2c.1.8.7 1.3 1.5 1.3h4.4c.8 0 1.4-.5 1.5-1.3l.8-10.2"/></svg>'
};

export function initLayouts(ctx: Ctx) {
  if (ctx.M.mode !== 'live' || $('layoutBtn')) return;
  const read = <T>(k: string, d: T): T => { try { return JSON.parse(store.get(k) || 'null') ?? d } catch { return d } };
  let active: Active | null = read<Active | null>(ACTIVE_KEY, null);
  if (active && (typeof active.id !== 'string' || typeof active.name !== 'string')) active = null;
  let autosave = store.get(AUTO_KEY) !== '0';
  /* base: the saved state of the open layout. QA round 3 (M3): after a layout is opened it is the layout's own state, never
     what the page holds once it settles, so a change made while the page restores itself still counts as a change */
  let base = store.get(BASE_KEY) || '';
  let settling = store.get(REBASE_KEY) === '1', switching = false;
  const setActive = (a: Active | null) => { active = a; a ? store.set(ACTIVE_KEY, JSON.stringify(a)) : store.remove(ACTIVE_KEY); paint() };
  const setBase = (s: Record<string, string>) => { base = canonical(s); store.set(BASE_KEY, base); paint() };
  const now = () => snapshotOf(k => store.get(k));
  /* QA round 4 (M1, M2): while an opened layout restores itself, the page writes its own settings (defaults, a normalised
     list); only a setting the user changed counts then. A write within GESTURE_MS of the user's pointer or key is the
     user's (touched); at settle every untouched setting is taken as the page wrote it */
  const GESTURE_MS = 1500, touched = new Set<string>(); let gestureAt = 0;
  addEventListener('pointerdown', () => { gestureAt = Date.now() }, true); addEventListener('keydown', () => { gestureAt = Date.now() }, true);
  const baseObj = (): Record<string, string> => { try { return Object.fromEntries(JSON.parse(base || '[]')) } catch { return {} } };
  const changed = () => { const n = now(), b = baseObj(); return LAYOUT_KEYS.filter(k => (n[k] ?? null) !== (b[k] ?? null)) };
  const dirty = () => !!active && (settling ? changed().some(k => touched.has(k)) : canonical(now()) !== base);
  /* QA round 4 (M4): another tab of this browser may open another layout (the settings are shared by the tabs); this tab
     then stops saving instead of writing that tab's chart into its own layout */
  let stale = false;
  const owns = () => { const a = read<Active | null>(ACTIVE_KEY, null); return !!active && !!a && a.id === active.id };
  /** QA round 3 (M4): with no layout open, a chart worth keeping (indicators, or a chart type or mode of its own) */
  const unsavedWork = () => { const s = now(); let n = 0; try { const a = JSON.parse(s['ml.ind.v1'] || '[]'); n = Array.isArray(a) ? a.length : 0 } catch { /* none */ }
    return n > 0 || (s['ml.chart.style'] || 'candle') !== 'candle' || (s['ml.chart.mode'] || 'price') !== 'price' };
  const MAC = /Mac|iPhone|iPad/.test(navigator.platform || '');

  /* ---- the toolbar button, after Price / Return (the user's red box) ---- */
  const btn = document.createElement('button');
  btn.type = 'button'; btn.id = 'layoutBtn'; btn.className = 'lay-btn'; btn.setAttribute('aria-haspopup', 'menu'); btn.setAttribute('aria-expanded', 'false');
  const anchor = $('modeGroup') as HTMLElement;
  const sep = document.createElement('div'); sep.className = 'divider lay-div';
  anchor.after(sep, btn);
  /* QA round 3 (M6, L6): a message wraps and sits at the bottom (never over the menu); a failure stays until it is closed */
  const toast = document.createElement('div'); toast.className = 'lay-toast'; toast.setAttribute('role', 'status'); toast.setAttribute('aria-live', 'polite');
  document.body.appendChild(toast);
  let toastTimer: any = 0;
  const say = (t: string, error = false) => {
    toast.innerHTML = `<span>${esc(t)}</span>${error ? '<button type="button" class="lay-tx" aria-label="Close message">×</button>' : ''}`;
    toast.classList.toggle('err', error); toast.classList.add('show'); clearTimeout(toastTimer);
    if (!error) toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
  };
  const fail = (e: any, what: string) => say(e?.message || what, true);
  toast.addEventListener('click', e => { if ((e.target as HTMLElement).closest('.lay-tx')) toast.classList.remove('show') });
  function paint() {
    const d = dirty();
    btn.innerHTML = `<span class="lay-name">${esc(active ? active.name : 'Layout')}</span>${d ? '<i class="lay-dirty" title="Unsaved changes"></i>' : ''}${ICON.chev}`;
    btn.title = active ? `Layout: ${active.name}${stale ? ' (another tab opened a different layout: reload this tab)' : d ? ' (unsaved changes)' : autosave ? ' (saved automatically)' : ''}` : 'Save or open a chart layout';
    btn.setAttribute('aria-label', btn.title);
  }

  /* ---- saving ---- */
  let chain: Promise<unknown> = Promise.resolve(), timer: any = 0;
  let list: LayoutMeta[] = [], listError = '', listing = false;
  const fetchList = async () => { listing = true; try { list = (await layoutsApi.list()).layouts; listError = '' } catch (e: any) { list = []; listError = e?.message || 'Saved layouts could not be read.' } finally { listing = false } };
  const freeName = (want: string) => { const names = new Set(list.map(l => l.name)); if (!names.has(want)) return want; let k = 2; while (names.has(`${want} ${k}`)) k++; return `${want} ${k}` };
  const create = (name: string, state: Record<string, string>) => layoutsApi.put(newLayoutId(), { name, state, summary:summaryOf(state) });
  /** save the chart into the open layout (none: ask for a name first). The chart wins over a newer revision saved from
      another tab or device, since it is what the user asked to keep; the stored name stays (QA round 3, M5) */
  const save = (loud: boolean) => chain = chain.then(async () => {
    clearTimeout(timer); timer = 0;
    if (!active) { await saveAs('Save layout', 'My layout'); return }
    if (stale || !owns()) { stale = true; paint(); say('Another tab opened a different layout. Reload this tab to work on it here; this tab no longer saves.', true); return }
    if (!dirty()) { if (loud) say(`“${active.name}” is already saved`); return }      // QA round 3 (L5): no write without a change
    const state = now(), summary = summaryOf(state);
    try {
      let r;
      try { r = await layoutsApi.put(active.id, { name:active.name, state, summary, revision:active.revision }) }
      catch (e) {
        if (!(e instanceof LayoutApiError) || e.code !== 'REVISION_CONFLICT') throw e;
        const cur = await layoutsApi.get(active.id);
        r = await layoutsApi.put(active.id, { name:cur.name, state, summary, revision:cur.revision });
      }
      setActive({ id:r.layout_id, name:r.name, revision:r.revision }); setBase(state);
      if (loud) say(`Saved “${r.name}”`);
    } catch (e: any) {
      if (e instanceof LayoutApiError && e.status === 404) { setActive(null); store.remove(BASE_KEY); base = ''; say('This layout was deleted on another device or tab. Use Save layout to keep this chart.', true) }
      else fail(e, 'The layout could not be saved. Try again in a minute; your chart is unchanged.');
    }
  }).catch(() => {});
  const saveAs = async (title: string, suggest: string) => {
    await fetchList();
    const name = await askName(title, freeName(suggest), async n => {
      const state = now(), r = await create(n, state);
      setActive({ id:r.layout_id, name:r.name, revision:r.revision }); setBase(state);
    });
    if (name) say(`Saved “${active!.name}”`);
  };
  const schedule = () => { if (autosave && active && !stale && dirty()) { clearTimeout(timer); timer = setTimeout(() => save(false), AUTOSAVE_MS) } };
  storeWatch.add(k => { if (!(LAYOUT_KEYS as readonly string[]).includes(k) || switching) return; if (Date.now() - gestureAt < GESTURE_MS) touched.add(k); paint(); schedule() });
  addEventListener('storage', e => {
    if (e.key !== ACTIVE_KEY || !active || owns() || stale) return;
    stale = true; clearTimeout(timer); timer = 0; paint();
    say('Another tab opened a different layout. Reload this tab to work on it here; this tab no longer saves.', true);
  });
  /* after a layout is opened the page restores itself (each part writes its settings again); once it has settled, a
     difference from the layout is a change: shown, and saved when Autosave is on */
  const settled = () => {
    const n = now(), b = baseObj(), merged: Record<string, string> = {};
    for (const k of LAYOUT_KEYS) { const v = touched.has(k) ? b[k] : n[k]; if (v !== undefined) merged[k] = v }
    settling = false; store.remove(REBASE_KEY); setBase(merged); schedule();
  };
  if (settling) { const t0 = Date.now(), wait = () => (window as any).__flowAll || Date.now() - t0 > SETTLE_MAX_MS ? setTimeout(settled, 600) : setTimeout(wait, 250); setTimeout(wait, 1500) }
  else if (dirty()) schedule();                                  // QA round 3 (L2): a change left unsaved by a reload
  /* a change still waiting for its autosave when the page goes away is sent on the way out */
  addEventListener('pagehide', () => {
    if (!timer || !active || stale || !owns() || !dirty()) return;
    const state = now(); layoutsApi.putOnLeave(active.id, { name:active.name, state, summary:summaryOf(state), revision:active.revision });
  });

  if (active) layoutsApi.prime();                                 // QA round 4 (L1): the token is there for a save on leave
  /* ---- switching layouts: the page reloads on the same ticker with the layout's settings ---- */
  /* QA round 4 (M3): before leaving, a change is saved when Autosave is on; one still unsaved (Autosave off, or a save
     that failed) is never dropped without asking */
  const flush = async () => { clearTimeout(timer); timer = 0; await chain; if (autosave && !stale && dirty()) await save(false) };
  const okToLeave = async () => {
    if (active) return stale || !dirty() || await confirmBox(`Discard the unsaved changes to “${active.name}”?`, 'Discard changes');
    return !unsavedWork() || await confirmBox('This chart is not saved as a layout. Discard it? (Save layout keeps it.)', 'Discard chart');
  };
  const load = async (state: Record<string, string>, a: Active) => {
    switching = true; clearTimeout(timer); timer = 0;
    applyState(state, (k, v) => store.set(k, v), k => store.remove(k));
    store.set(ACTIVE_KEY, JSON.stringify(a)); store.set(BASE_KEY, canonical(state)); store.set(REBASE_KEY, '1');
    location.reload();
  };
  const openLayout = async (id: string) => {
    if (active && id === active.id && !dirty()) { closeMenu(true); return }
    await flush(); if (!(await okToLeave())) return;
    try {
      const l = await layoutsApi.get(id);
      await layoutsApi.mark(id, { opened:true }).catch(() => {});
      await load(l.state, { id:l.layout_id, name:l.name, revision:l.revision });
    } catch (e: any) {
      if (e instanceof LayoutApiError && e.status === 404) { await fetchList(); redrawOpen(); say('That layout no longer exists (deleted on another device or tab). The list is updated.', true) }
      else fail(e, 'The layout could not be opened. Try again in a minute.');
    }
  };

  /* ---- the menu ---- */
  const menu = document.createElement('div');
  menu.className = 'lay-menu'; menu.hidden = true; menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Layout');
  document.body.appendChild(menu);
  const ordered = () => [...list].sort((a, b) => Number(b.favorite) - Number(a.favorite) || (a.opened_at < b.opened_at ? 1 : a.opened_at > b.opened_at ? -1 : 0));
  const starBtn = (l: LayoutMeta, role = '') => `<button type="button" class="lay-star${l.favorite ? ' fav' : ''}"${role} data-star="${l.layout_id}" aria-pressed="${l.favorite}" aria-label="${esc(`${l.favorite ? 'Remove' : 'Add'} “${l.name}” ${l.favorite ? 'from' : 'to'} favourites`)}">${ICON.star}</button>`;
  /* QA round 3 (L3): the row is a group of two controls (open, star), the open layout marked with aria-current */
  const recentRow = (l: LayoutMeta) => { const on = !!active && l.layout_id === active.id;
    return `<div class="lay-item${on ? ' on' : ''}" role="none"><button type="button" class="lay-open" role="menuitem" data-open="${l.layout_id}"${on ? ' aria-current="true"' : ''}>
      <span class="lay-iname"><b>${esc(l.name)}</b><small>${esc(l.summary || '')}</small></span></button>${starBtn(l)}</div>` };
  const kbd = (t: string) => `<kbd>${t}</kbd>`;
  function renderMenu() {
    const recent = ordered().slice(0, RECENT), same = active && !dirty();
    menu.innerHTML = `<button type="button" class="lay-mi" role="menuitem" data-act="save"${same ? ' aria-disabled="true" title="No unsaved changes"' : ''}><span>Save layout</span>${kbd(MAC ? '⌘ S' : 'Ctrl + S')}</button>
      <label class="lay-mi lay-switch"><span>Autosave</span><input type="checkbox" role="menuitemcheckbox" ${autosave ? 'checked aria-checked="true"' : 'aria-checked="false"'} aria-label="Autosave"><i></i></label>
      <div class="lay-sep" role="separator"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="copy">${ICON.copy}<span>Make a copy…</span></button>
      <button type="button" class="lay-mi" role="menuitem" data-act="rename"${active ? '' : ' aria-disabled="true" title="Save the chart as a layout first"'}>${ICON.pen}<span>Rename…</span></button>
      <div class="lay-sep" role="separator"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="new">${ICON.plus}<span>Create new layout…</span></button>
      <div class="lay-sep" role="separator"></div>
      <div class="lay-head" role="presentation">Recently used</div>
      ${listing && !list.length ? '<div class="lay-msg">Loading…</div>' : listError ? `<div class="lay-msg">${esc(listError)}</div>` : recent.length ? recent.map(recentRow).join('') : '<div class="lay-msg">No saved layouts yet.</div>'}
      <div class="lay-sep" role="separator"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="open">${ICON.folder}<span>Open layout…</span>${kbd('.')}</button>`;
  }
  const place = () => { const r = btn.getBoundingClientRect(), w = menu.offsetWidth;
    menu.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + 'px'; menu.style.top = (r.bottom + 6) + 'px';
    menu.style.maxHeight = Math.max(200, innerHeight - r.bottom - 16) + 'px' };
  /* the menu's focus order for the arrow keys (QA round 3, M1: the Autosave switch is its input) */
  const navItems = () => [...menu.querySelectorAll<HTMLElement>('.lay-mi:not(.lay-switch), .lay-switch input, .lay-open')];
  const keepFocus = (sel: string | null) => { if (sel) (menu.querySelector(sel) as HTMLElement | null)?.focus() };
  async function openMenu() {
    toast.classList.remove('show');
    listing = true; renderMenu();                                 // QA round 4 (L3): "Loading…" until the list is read
    menu.hidden = false; btn.setAttribute('aria-expanded', 'true'); place();
    navItems()[0]?.focus();
    await fetchList();
    if (menu.hidden) return;
    const f = document.activeElement as HTMLElement | null, sel = f && menu.contains(f) ? (f.dataset.act ? `[data-act="${f.dataset.act}"]` : f.dataset.open ? `[data-open="${f.dataset.open}"]` : f.dataset.star ? `[data-star="${f.dataset.star}"]` : f.matches('input') ? '.lay-switch input' : null) : null;
    renderMenu(); place(); keepFocus(sel);
  }
  function closeMenu(focus = false) { if (menu.hidden) return; menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); if (focus) btn.focus() }
  btn.addEventListener('click', () => menu.hidden ? openMenu() : closeMenu());
  document.addEventListener('pointerdown', e => { const t = e.target as Node; if (!menu.hidden && !menu.contains(t) && !btn.contains(t)) closeMenu() }, true);
  addEventListener('resize', () => { if (!menu.hidden) place() });
  // Escape closes the menu wherever the focus is (a star click redraws the menu)
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden && !document.querySelector('.lay-back')) closeMenu(true) });
  menu.addEventListener('keydown', e => {
    const t = e.target as HTMLElement;
    if (e.key === 'ArrowRight' && t.matches('.lay-open')) { e.preventDefault(); (t.parentElement?.querySelector('.lay-star') as HTMLElement | null)?.focus(); return }
    if (e.key === 'ArrowLeft' && t.matches('.lay-star')) { e.preventDefault(); (t.parentElement?.querySelector('.lay-open') as HTMLElement | null)?.focus(); return }
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
    const items = navItems(), at = t.matches('.lay-star') ? t.parentElement?.querySelector('.lay-open') : t, k = items.indexOf(at as HTMLElement);
    e.preventDefault();
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1 : (k + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[k < 0 && e.key === 'ArrowUp' ? items.length - 1 : k < 0 && e.key === 'ArrowDown' ? 0 : next]?.focus();
  });
  menu.addEventListener('change', e => {
    const box = e.target as HTMLInputElement; if (box.type !== 'checkbox') return;
    autosave = box.checked; box.setAttribute('aria-checked', String(autosave)); store.set(AUTO_KEY, autosave ? '1' : '0'); paint();
    if (autosave && dirty()) save(false);
  });
  const toggleStar = async (id: string, redraw: () => void, focusSel: string) => {
    const l = list.find(x => x.layout_id === id); if (!l) return;
    try { const r = await layoutsApi.mark(id, { favorite:!l.favorite }); l.favorite = r.favorite; redraw(); (document.querySelector(focusSel) as HTMLElement | null)?.focus() }
    catch (er: any) { if (er instanceof LayoutApiError && er.status === 404) { await fetchList(); redraw() } fail(er, 'The star could not be changed. Try again in a minute.') }
  };
  menu.addEventListener('click', async e => {
    const t = e.target as HTMLElement, star = t.closest('[data-star]') as HTMLElement | null;
    if (star) { e.stopPropagation(); const id = star.dataset.star!; toggleStar(id, renderMenu, `.lay-menu [data-star="${id}"]`); return }
    const row = t.closest('[data-open]') as HTMLElement | null;
    if (row) { closeMenu(); openLayout(row.dataset.open!); return }
    const item = t.closest('[data-act]') as HTMLElement | null, act = item?.dataset.act; if (!act) return;
    if (act === 'rename' && !active) { say('Save the chart as a layout first (Save layout), then it can be renamed.'); return }
    closeMenu();
    if (act === 'save') save(true);
    else if (act === 'copy') saveAs('Make a copy', active ? `${active.name} copy` : 'My layout');
    else if (act === 'rename') renameLayout();
    else if (act === 'new') newLayout();
    else if (act === 'open') openDialog();
  });

  async function renameLayout() {
    const was = active!;
    const name = await askName('Rename layout', was.name, async n => {
      const cur = await layoutsApi.get(was.id);
      const r = await layoutsApi.put(was.id, { name:n, state:cur.state, summary:cur.summary, revision:cur.revision });
      setActive({ id:r.layout_id, name:r.name, revision:r.revision });
    });
    if (name) say(`Renamed to “${active!.name}”`);
  }
  async function newLayout() {
    await flush(); if (!(await okToLeave())) return;
    await fetchList();
    let k = 1; const names = new Set(list.map(l => l.name)); while (names.has(`Untitled ${k}`)) k++;
    await askName('Create new layout', `Untitled ${k}`, async n => {
      const r = await create(n, {});
      await load({}, { id:r.layout_id, name:r.name, revision:r.revision });
    });
  }

  /* ---- dialogs (QA round 3, M2): Escape closes them wherever the focus is, Tab stays inside, and the focus goes back to
     the Layout button (or what opened them, when it is still on screen) ---- */
  const modal = (inner: string, label: string, onClose?: () => void) => {
    const back = document.createElement('div'); back.className = 'lay-back';
    back.innerHTML = `<div class="lay-dlg" role="dialog" aria-modal="true" aria-label="${esc(label)}">${inner}</div>`;
    document.body.appendChild(back);
    const was = document.activeElement as HTMLElement | null;
    const opener = was && was !== document.body && was.isConnected && was.offsetParent !== null && !menu.contains(was) ? was : btn;
    const dlg = back.firstElementChild as HTMLElement;
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return }
      if (e.key !== 'Tab') return;
      const f = [...dlg.querySelectorAll<HTMLElement>('button:not([disabled]),input,[tabindex="0"]')].filter(x => x.offsetParent !== null);
      if (!f.length) return;
      const i = f.indexOf(document.activeElement as HTMLElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus() } else if (!e.shiftKey && (i === f.length - 1 || i < 0)) { e.preventDefault(); f[0].focus() }
    };
    const close = () => { document.removeEventListener('keydown', key, true); back.remove(); onClose?.(); opener.focus?.() };
    document.addEventListener('keydown', key, true);
    back.addEventListener('pointerdown', e => { if (e.target === back) close() });
    return { back, dlg, close };
  };
  /** a name, sent through `commit` (its refusal is shown under the field); resolves to the name, or null when cancelled */
  function askName(title: string, suggest: string, commit: (name: string) => Promise<void>) {
    return new Promise<string | null>(resolve => {
      let result: string | null = null;
      const { dlg, close } = modal(`<h3>${esc(title)}</h3><input class="lay-in" type="text" maxlength="120" value="${esc(suggest)}" aria-label="Layout name">
        <div class="lay-err" role="alert"></div><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1" data-ok>Save</button></div>`, title, () => resolve(result));
      const input = dlg.querySelector('input') as HTMLInputElement, err = dlg.querySelector('.lay-err') as HTMLElement, ok = dlg.querySelector('[data-ok]') as HTMLButtonElement;
      const go = async () => {
        const n = input.value.replace(/\s+/g, ' ').trim();
        if (!n) { err.textContent = 'Give the layout a name.'; input.focus(); return }
        ok.disabled = true; err.textContent = '';
        try { await commit(n); result = n; close() } catch (e: any) { err.textContent = e?.message || 'Not saved. Try again in a minute.'; ok.disabled = false; input.focus() }
      };
      ok.onclick = go; (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
      input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go() } });
      input.focus(); input.select();
    });
  }
  function confirmBox(text: string, yes: string) {
    return new Promise<boolean>(resolve => {
      let result = false;
      const { dlg, close } = modal(`<p>${esc(text)}</p><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1 warn" data-ok>${esc(yes)}</button></div>`, 'Confirm', () => resolve(result));
      (dlg.querySelector('[data-ok]') as HTMLElement).onclick = () => { result = true; close() };
      (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
      (dlg.querySelector('[data-x]') as HTMLElement).focus();
    });
  }
  let redrawOpen = () => {};
  async function openDialog() {
    if (document.querySelector('.lay-back')) return;
    const { dlg, close } = modal(`<h3>Open layout</h3><input class="lay-in" type="search" placeholder="Search layouts" aria-label="Search layouts">
      <div class="lay-list" role="listbox" aria-label="Saved layouts"><div class="lay-msg">Loading…</div></div>
      <div class="lay-btns"><button type="button" class="lay-b2" data-x>Close</button></div>`, 'Open layout', () => { redrawOpen = () => {} });
    dlg.classList.add('wide');
    const q = dlg.querySelector('input') as HTMLInputElement, box = dlg.querySelector('.lay-list') as HTMLElement;
    let armed = '';
    const day = (t: string) => new Date(t).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' }).replace('Sept', 'Sep');
    const draw = (focus?: string) => {
      if (listError) { box.innerHTML = `<div class="lay-msg">${esc(listError)}</div>`; return }
      const f = q.value.trim().toLowerCase(), rows = ordered().filter(l => !f || l.name.toLowerCase().includes(f));
      box.innerHTML = rows.length ? rows.map(l => { const on = !!active && l.layout_id === active.id;
        return `<div class="lay-orow${on ? ' on' : ''}" role="option" tabindex="0" data-open="${l.layout_id}" aria-selected="${on}">
          ${starBtn(l)}
          <span class="lay-iname"><b title="${esc(l.name)}">${esc(l.name)}</b><small>${esc(l.summary || '')} · saved ${day(l.updated_at)}</small></span>
          <button type="button" class="lay-del${armed === l.layout_id ? ' armed' : ''}" data-del="${l.layout_id}" aria-label="${esc(armed === l.layout_id ? `Click again to delete “${l.name}”` : `Delete “${l.name}”`)}">${armed === l.layout_id ? 'Delete?' : ICON.trash}</button></div>` }).join('')
        : `<div class="lay-msg">${list.length ? 'No layout matches.' : 'No saved layouts yet. Use Save layout to keep this chart.'}</div>`;
      if (focus) (box.querySelector(focus) as HTMLElement | null)?.focus();
    };
    redrawOpen = () => draw();
    q.addEventListener('input', () => { armed = ''; draw() });
    (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
    dlg.addEventListener('keydown', e => {
      const t = e.target as HTMLElement;
      if (e.key === 'Enter' && t.matches('.lay-orow')) { e.preventDefault(); t.click(); return }
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      const rows = [...box.querySelectorAll<HTMLElement>('.lay-orow')]; if (!rows.length) return;
      const at = rows.indexOf(t.closest('.lay-orow') as HTMLElement);
      e.preventDefault(); rows[at < 0 ? (e.key === 'ArrowDown' ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, at + (e.key === 'ArrowDown' ? 1 : -1)))].focus();
    });
    box.addEventListener('click', async e => {
      const t = e.target as HTMLElement, star = t.closest('[data-star]') as HTMLElement | null, del = t.closest('[data-del]') as HTMLElement | null;
      if (star) { const id = star.dataset.star!; toggleStar(id, () => draw(), `.lay-list [data-star="${id}"]`); return }
      if (del) {
        const id = del.dataset.del!;
        if (armed !== id) { armed = id; draw(`[data-del="${id}"]`); return }
        try {
          const at = [...box.querySelectorAll('.lay-orow')].findIndex(r => (r as HTMLElement).dataset.open === id);
          await layoutsApi.remove(id); list = list.filter(l => l.layout_id !== id); armed = '';
          if (active && active.id === id) { setActive(null); store.remove(BASE_KEY); base = '' }
          draw(); say('Layout deleted');
          const rows = box.querySelectorAll<HTMLElement>('.lay-orow'); (rows[Math.min(at, rows.length - 1)] || q).focus();
        } catch (er: any) { if (er instanceof LayoutApiError && er.status === 404) { await fetchList(); draw() } fail(er, 'The layout could not be deleted. Try again in a minute.') }
        return;
      }
      const row = t.closest('[data-open]') as HTMLElement | null;
      if (row) { close(); openLayout(row.dataset.open!) }
    });
    q.focus();
    await fetchList(); draw();
  }

  /* ---- keys: Ctrl/Cmd + S saves; "." opens the list (not while typing or with a dialog open) ---- */
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') { e.preventDefault(); if (!document.querySelector('.lay-back')) save(true); return }
    if (e.key !== '.' || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
    const t = e.target as HTMLElement;
    if (/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName) || t.isContentEditable || t.closest('[role=dialog],.fl-pop,.cs-pop,.dr-menu')) return;
    if (document.querySelector('.idlg-back:not([hidden]),.lay-back')) return;
    e.preventDefault(); closeMenu(); openDialog();
  });
  paint();
  (window as any).marketLabLayouts = { snapshot:now, active:() => active, dirty };    // for the checks (verification/terminal_api/terminal_look)
}
