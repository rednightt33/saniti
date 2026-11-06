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
const RECENT = 5, AUTOSAVE_MS = 1500;
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
  let base = store.get(BASE_KEY) || '';
  let rebasing = store.get(REBASE_KEY) === '1', switching = false;
  const setActive = (a: Active | null) => { active = a; a ? store.set(ACTIVE_KEY, JSON.stringify(a)) : store.remove(ACTIVE_KEY); paint() };
  const setBase = (s: Record<string, string>) => { base = canonical(s); store.set(BASE_KEY, base); paint() };
  const now = () => snapshotOf(k => store.get(k));
  const dirty = () => !!active && !rebasing && canonical(now()) !== base;

  /* ---- the toolbar button, after Price / Return (the user's red box) ---- */
  const btn = document.createElement('button');
  btn.type = 'button'; btn.id = 'layoutBtn'; btn.className = 'lay-btn'; btn.setAttribute('aria-haspopup', 'menu'); btn.setAttribute('aria-expanded', 'false');
  const anchor = $('modeGroup') as HTMLElement;
  const sep = document.createElement('div'); sep.className = 'divider lay-div';
  anchor.after(sep, btn);
  const toast = document.createElement('div'); toast.className = 'lay-toast'; toast.setAttribute('role', 'status'); toast.setAttribute('aria-live', 'polite');
  document.body.appendChild(toast);
  let toastTimer: any = 0;
  const say = (t: string) => { toast.textContent = t; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2600) };
  function paint() {
    const d = dirty();
    btn.innerHTML = `<span class="lay-name">${esc(active ? active.name : 'Layout')}</span>${d ? '<i class="lay-dirty" title="Unsaved changes"></i>' : ''}${ICON.chev}`;
    btn.title = active ? `Layout: ${active.name}${d ? ' (unsaved changes)' : autosave ? ' (saved automatically)' : ''}` : 'Save or open a chart layout';
    btn.setAttribute('aria-label', btn.title);
  }

  /* ---- saving ---- */
  let chain: Promise<unknown> = Promise.resolve(), timer: any = 0;
  const create = async (name: string, state: Record<string, string>) => {
    const r = await layoutsApi.put(newLayoutId(), { name, state, summary:summaryOf(state) });
    return r;
  };
  /** save the chart into the active layout (none: ask for a name first). Last write wins: a newer revision saved from
      another tab or device is read and replaced, since the chart on screen is what the user asked to keep */
  const save = (loud: boolean) => chain = chain.then(async () => {
    clearTimeout(timer); timer = 0;
    if (!active) { await saveAs('Save layout', 'My layout'); return }
    const state = now(), body = { name:active.name, state, summary:summaryOf(state) };
    try {
      let r;
      try { r = await layoutsApi.put(active.id, { ...body, revision:active.revision }) }
      catch (e) {
        if (!(e instanceof LayoutApiError) || e.code !== 'REVISION_CONFLICT') throw e;
        const cur = await layoutsApi.get(active.id);
        r = await layoutsApi.put(active.id, { ...body, revision:cur.revision });
      }
      setActive({ id:r.layout_id, name:r.name, revision:r.revision }); setBase(state);
      if (loud) say(`Saved “${r.name}”`);
    } catch (e: any) {
      if (e instanceof LayoutApiError && e.status === 404) { setActive(null); say('This layout was deleted elsewhere: save it again to keep it.') }
      else say(e?.message || 'The layout could not be saved.');
    }
  }).catch(() => {});
  const saveAs = async (title: string, suggest: string) => {
    const name = await askName(title, suggest, async n => {
      const state = now(), r = await create(n, state);
      setActive({ id:r.layout_id, name:r.name, revision:r.revision }); setBase(state);
    });
    if (name) say(`Saved “${active!.name}”`);
  };
  storeWatch.add(k => {
    if (!(LAYOUT_KEYS as readonly string[]).includes(k) || switching) return;
    paint();
    if (autosave && active && !rebasing) { clearTimeout(timer); timer = setTimeout(() => save(false), AUTOSAVE_MS) }
  });
  /* after a layout is opened, the page settles (each part writes its settings as it restores them) before the opened state
     becomes the saved one */
  if (rebasing) {
    const done = () => { if (!rebasing) return; rebasing = false; store.remove(REBASE_KEY); setBase(now()) };
    const t0 = Date.now(), wait = () => (window as any).__flowAll || Date.now() - t0 > 8000 ? setTimeout(done, 600) : setTimeout(wait, 250);
    setTimeout(wait, 1500);
  }

  /* ---- switching layouts: the page reloads on the same ticker with the layout's settings ---- */
  const flush = async () => { if (timer) { clearTimeout(timer); timer = 0; await save(false) } else await chain };
  const okToLeave = async () => !dirty() || autosave || await confirmBox(`“${active!.name}” has unsaved changes. Leave them?`, 'Leave without saving');
  const load = async (state: Record<string, string>, a: Active) => {
    switching = true;
    applyState(state, (k, v) => store.set(k, v), k => store.remove(k));
    store.set(ACTIVE_KEY, JSON.stringify(a)); store.set(BASE_KEY, canonical(state)); store.set(REBASE_KEY, '1');
    location.reload();
  };
  const openLayout = async (id: string) => {
    if (active && id === active.id && !dirty()) { closeMenu(); return }
    await flush(); if (!(await okToLeave())) return;
    try {
      const l = await layoutsApi.get(id);
      await layoutsApi.mark(id, { opened:true }).catch(() => {});
      await load(l.state, { id:l.layout_id, name:l.name, revision:l.revision });
    } catch (e: any) { say(e?.message || 'The layout could not be opened.') }
  };

  /* ---- the menu ---- */
  const menu = document.createElement('div');
  menu.className = 'lay-menu'; menu.hidden = true; menu.setAttribute('role', 'menu'); menu.setAttribute('aria-label', 'Layout');
  document.body.appendChild(menu);
  let list: LayoutMeta[] = [], listError = '';
  const fetchList = async () => { try { list = (await layoutsApi.list()).layouts; listError = '' } catch (e: any) { list = []; listError = e?.message || 'Saved layouts could not be read.' } };
  const recentRow = (l: LayoutMeta) => `<div class="lay-item${active && l.layout_id === active.id ? ' on' : ''}" role="menuitem" tabindex="-1" data-open="${l.layout_id}">
      <span class="lay-iname"><b>${esc(l.name)}</b><small>${esc(l.summary || '')}</small></span>
      <button type="button" class="lay-star${l.favorite ? ' fav' : ''}" data-star="${l.layout_id}" aria-pressed="${l.favorite}" aria-label="${l.favorite ? 'Remove from favourites' : 'Add to favourites'}">${ICON.star}</button></div>`;
  function renderMenu() {
    const recent = list.slice(0, RECENT);
    menu.innerHTML = `<button type="button" class="lay-mi" role="menuitem" data-act="save"${active && !dirty() && autosave ? ' aria-disabled="true"' : ''}><span>Save layout</span><kbd>Ctrl + S</kbd></button>
      <label class="lay-mi lay-switch"><span>Autosave</span><input type="checkbox" role="switch" ${autosave ? 'checked' : ''} aria-label="Autosave"><i></i></label>
      <div class="lay-sep"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="copy">${ICON.copy}<span>Make a copy…</span></button>
      <button type="button" class="lay-mi" role="menuitem" data-act="rename">${ICON.pen}<span>Rename…</span></button>
      <div class="lay-sep"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="new">${ICON.plus}<span>Create new layout…</span></button>
      <div class="lay-sep"></div>
      <div class="lay-head">Recently used</div>
      ${listError ? `<div class="lay-msg">${esc(listError)}</div>` : recent.length ? recent.map(recentRow).join('') : '<div class="lay-msg">No saved layouts yet.</div>'}
      <div class="lay-sep"></div>
      <button type="button" class="lay-mi" role="menuitem" data-act="open">${ICON.folder}<span>Open layout…</span><kbd>.</kbd></button>`;
  }
  const place = () => { const r = btn.getBoundingClientRect(), w = menu.offsetWidth;
    menu.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + 'px'; menu.style.top = (r.bottom + 6) + 'px';
    menu.style.maxHeight = Math.max(200, innerHeight - r.bottom - 16) + 'px' };
  async function openMenu() {
    renderMenu(); menu.hidden = false; btn.setAttribute('aria-expanded', 'true'); place();
    await fetchList(); if (!menu.hidden) { renderMenu(); place() }
    (menu.querySelector('.lay-mi') as HTMLElement | null)?.focus();
  }
  function closeMenu(focus = false) { if (menu.hidden) return; menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); if (focus) btn.focus() }
  btn.addEventListener('click', () => menu.hidden ? openMenu() : closeMenu());
  document.addEventListener('pointerdown', e => { const t = e.target as Node; if (!menu.hidden && !menu.contains(t) && !btn.contains(t)) closeMenu() }, true);
  addEventListener('resize', () => { if (!menu.hidden) place() });
  // Escape closes the menu wherever the focus is (a star click redraws the menu and leaves the focus on the page)
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden && !document.querySelector('.lay-back')) { closeMenu(true) } });
  menu.addEventListener('keydown', e => {
    if (e.key === 'Escape') { e.stopPropagation(); closeMenu(true); return }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    const items = [...menu.querySelectorAll<HTMLElement>('.lay-mi,.lay-item')], k = items.indexOf(document.activeElement as HTMLElement);
    e.preventDefault(); items[(k + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
  });
  menu.addEventListener('change', e => {
    const box = e.target as HTMLInputElement; if (box.type !== 'checkbox') return;
    autosave = box.checked; store.set(AUTO_KEY, autosave ? '1' : '0'); paint();
    if (autosave && dirty()) save(false);
  });
  menu.addEventListener('click', async e => {
    const t = e.target as HTMLElement, star = t.closest('[data-star]') as HTMLElement | null;
    if (star) {
      e.stopPropagation(); const id = star.dataset.star!, l = list.find(x => x.layout_id === id); if (!l) return;
      try { const r = await layoutsApi.mark(id, { favorite:!l.favorite }); l.favorite = r.favorite; renderMenu(); (menu.querySelector(`[data-star="${id}"]`) as HTMLElement | null)?.focus() } catch (er: any) { say(er?.message || 'Not changed.') }
      return;
    }
    const row = t.closest('[data-open]') as HTMLElement | null;
    if (row) { closeMenu(); openLayout(row.dataset.open!); return }
    const act = (t.closest('[data-act]') as HTMLElement | null)?.dataset.act; if (!act) return;
    closeMenu();
    if (act === 'save') save(true);
    else if (act === 'copy') copyLayout();
    else if (act === 'rename') renameLayout();
    else if (act === 'new') newLayout();
    else if (act === 'open') openDialog();
  });
  menu.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.target as HTMLElement).matches('.lay-item')) { e.preventDefault(); (e.target as HTMLElement).click() } });

  async function copyLayout() {
    await saveAs('Make a copy', active ? `${active.name} copy` : 'My layout');
  }
  async function renameLayout() {
    if (!active) { await saveAs('Save layout', 'My layout'); return }
    const was = active;
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

  /* ---- dialogs ---- */
  const modal = (inner: string, label: string) => {
    const back = document.createElement('div'); back.className = 'lay-back';
    back.innerHTML = `<div class="lay-dlg" role="dialog" aria-modal="true" aria-label="${esc(label)}">${inner}</div>`;
    document.body.appendChild(back);
    const opener = document.activeElement as HTMLElement | null;
    const close = () => { back.remove(); opener?.focus?.() };
    back.addEventListener('pointerdown', e => { if (e.target === back) close() });
    return { back, dlg:back.firstElementChild as HTMLElement, close };
  };
  /** a name, sent through `commit` (its refusal is shown under the field); resolves to the name, or null when cancelled */
  function askName(title: string, suggest: string, commit: (name: string) => Promise<void>) {
    return new Promise<string | null>(resolve => {
      const { dlg, close } = modal(`<h3>${esc(title)}</h3><input class="lay-in" type="text" maxlength="120" value="${esc(suggest)}" aria-label="Layout name">
        <div class="lay-err" role="alert"></div><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1" data-ok>Save</button></div>`, title);
      const input = dlg.querySelector('input') as HTMLInputElement, err = dlg.querySelector('.lay-err') as HTMLElement, ok = dlg.querySelector('[data-ok]') as HTMLButtonElement;
      const done = (v: string | null) => { close(); resolve(v) };
      const go = async () => {
        const n = input.value.replace(/\s+/g, ' ').trim();
        if (!n) { err.textContent = 'Give the layout a name.'; input.focus(); return }
        ok.disabled = true; err.textContent = '';
        try { await commit(n); done(n) } catch (e: any) { err.textContent = e?.message || 'Not saved.'; ok.disabled = false; input.focus() }
      };
      ok.onclick = go; (dlg.querySelector('[data-x]') as HTMLElement).onclick = () => done(null);
      dlg.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); go() } else if (e.key === 'Escape') { e.stopPropagation(); done(null) } });
      input.focus(); input.select();
    });
  }
  function confirmBox(text: string, yes: string) {
    return new Promise<boolean>(resolve => {
      const { dlg, close } = modal(`<p>${esc(text)}</p><div class="lay-btns"><button type="button" class="lay-b2" data-x>Cancel</button><button type="button" class="lay-b1 warn" data-ok>${esc(yes)}</button></div>`, 'Confirm');
      const done = (v: boolean) => { close(); resolve(v) };
      (dlg.querySelector('[data-ok]') as HTMLElement).onclick = () => done(true);
      (dlg.querySelector('[data-x]') as HTMLElement).onclick = () => done(false);
      dlg.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); done(false) } });
      (dlg.querySelector('[data-x]') as HTMLElement).focus();
    });
  }
  async function openDialog() {
    if (document.querySelector('.lay-back')) return;
    const { dlg, close } = modal(`<h3>Open layout</h3><input class="lay-in" type="search" placeholder="Search layouts" aria-label="Search layouts">
      <div class="lay-list" role="listbox" aria-label="Saved layouts"><div class="lay-msg">Loading…</div></div>
      <div class="lay-btns"><button type="button" class="lay-b2" data-x>Close</button></div>`, 'Open layout');
    dlg.classList.add('wide');
    const q = dlg.querySelector('input') as HTMLInputElement, box = dlg.querySelector('.lay-list') as HTMLElement;
    let armed = '';
    const day = (t: string) => new Date(t).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' }).replace('Sept', 'Sep');
    const draw = () => {
      if (listError) { box.innerHTML = `<div class="lay-msg">${esc(listError)}</div>`; return }
      const f = q.value.trim().toLowerCase();
      const rows = [...list].sort((a, b) => Number(b.favorite) - Number(a.favorite) || (a.opened_at < b.opened_at ? 1 : -1)).filter(l => !f || l.name.toLowerCase().includes(f));
      box.innerHTML = rows.length ? rows.map(l => `<div class="lay-orow${active && l.layout_id === active.id ? ' on' : ''}" role="option" tabindex="0" data-open="${l.layout_id}" aria-selected="${!!active && l.layout_id === active.id}">
          <button type="button" class="lay-star${l.favorite ? ' fav' : ''}" data-star="${l.layout_id}" aria-pressed="${l.favorite}" aria-label="${l.favorite ? 'Remove from favourites' : 'Add to favourites'}">${ICON.star}</button>
          <span class="lay-iname"><b>${esc(l.name)}</b><small>${esc(l.summary || '')} · saved ${day(l.updated_at)}</small></span>
          <button type="button" class="lay-del${armed === l.layout_id ? ' armed' : ''}" data-del="${l.layout_id}" aria-label="${armed === l.layout_id ? 'Click again to delete' : 'Delete layout'}">${armed === l.layout_id ? 'Delete?' : ICON.trash}</button></div>`).join('')
        : `<div class="lay-msg">${list.length ? 'No layout matches.' : 'No saved layouts yet. Use Save layout to keep this chart.'}</div>`;
    };
    q.addEventListener('input', () => { armed = ''; draw() });
    (dlg.querySelector('[data-x]') as HTMLElement).onclick = close;
    dlg.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.stopPropagation(); close() }
      else if (e.key === 'Enter' && (e.target as HTMLElement).matches('.lay-orow')) { e.preventDefault(); (e.target as HTMLElement).click() }
    });
    box.addEventListener('click', async e => {
      const t = e.target as HTMLElement, star = t.closest('[data-star]') as HTMLElement | null, del = t.closest('[data-del]') as HTMLElement | null;
      if (star) {
        const l = list.find(x => x.layout_id === star.dataset.star); if (!l) return;
        try { const r = await layoutsApi.mark(l.layout_id, { favorite:!l.favorite }); l.favorite = r.favorite; draw() } catch (er: any) { say(er?.message || 'Not changed.') }
        return;
      }
      if (del) {
        const id = del.dataset.del!;
        if (armed !== id) { armed = id; draw(); (box.querySelector(`[data-del="${id}"]`) as HTMLElement | null)?.focus(); return }
        try {
          await layoutsApi.remove(id); list = list.filter(l => l.layout_id !== id); armed = '';
          if (active && active.id === id) { setActive(null); store.remove(BASE_KEY); base = '' }
          draw(); say('Layout deleted');
        } catch (er: any) { say(er?.message || 'Not deleted.') }
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
