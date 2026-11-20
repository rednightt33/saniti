/* EXEC-WATCHLIST L5 (user go 2026-11-16): the Watchlist page, ported from the approved light mockup
   (watchlist_light_mockup.html, its logic wl_mock.js) with the account's lists from edge-bff in place of the browser's
   and the publisher's watchlist-stocks file in place of the dev snapshot. Every figure is the file's (src/model.ts only
   formats and arranges); every limit is the one edge-bff publishes; every refusal shows edge-bff's message, which names
   the fix. The open list and the Table/Cards choice are this browser's convenience (localStorage). */
import { WatchlistError, cached } from './api.ts';
import * as M from './model.ts';
import type { RadarFile, StocksFile, WList, WatchlistApi, WatchlistIndex } from './types.ts';

const FILE = 'watchlist-stocks';
// Phase 3d (ERRORS M476): the Radar's screens, listed and served only with radar.view (app/pages.py carried)
const RADAR_FILE = 'watchlist-radar';
const FIRST_LIST = 'Watchlist';                    // the list a first visit creates (app/watchlist.py FIRST_LIST)
const VIEW_KEY = 'edge.watchlist.view';
const { DOT, CARD_IND } = M;
const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string);
const ic = (n: string) => `<svg class="ic ic-sm"><use href="#i-${n}"/></svg>`;
const reduceMotion = () => !!window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
const msg = (e: unknown, dflt: string) => (e instanceof WatchlistError ? e.message : dflt);

type View = 'cards' | 'table';
interface Menu extends HTMLDivElement { _for?: HTMLElement }
interface Dlg { bd: HTMLElement; opener: Element | null; onKey?: (e: KeyboardEvent) => void; onClose?: () => void }

export function start(api0: WatchlistApi, PAGE: HTMLElement) {
  const api = cached(api0);
  let index: WatchlistIndex, F: StocksFile, CAT: M.Catalog, BY = new Map<string, M.Stock>(), UL: M.Stock[] = [];
  let RN: Record<string, string> = {}, LISTS: WList[] = [], LIM: M.Limits = M.limitsOf([]), LOGOS: Record<string, string> = {};
  let PD = '', BD = '', RD = '';
  let HAS_RADAR = false;                  // Phase 3d: this account reads the Radar's screens (else no badge, no filter)
  let FILE_ERR: string | null = null;     // M466 (a): the figures could not be read; the lists are shown without them
  const st: { active: string; view: View } = { active: '', view: 'cards' };
  try { const s = JSON.parse(localStorage.getItem(VIEW_KEY) || 'null'); if (s) { st.active = String(s.active || ''); st.view = s.view === 'table' ? 'table' : 'cards' } } catch { /* storage off */ }
  const persist = () => { try { localStorage.setItem(VIEW_KEY, JSON.stringify(st)) } catch { /* storage off */ } };

  const L = (id?: string) => LISTS.find(l => l.id === (id || st.active)) as WList;
  const S = (t: string) => BY.get(t) || M.unknownStock(t, FILE_ERR ? '' : undefined);
  const tk = (l: WList) => M.tickersOf(l);
  const ind = (l: WList) => M.indicatorsOf(l, CAT, LIM.indicators);
  const INFO = (k: string) => CAT.by[k];
  const asOf = (k: string) => (M.brokerDated(INFO(k)) ? BD : PD);
  const put = (l: WList) => { const i = LISTS.findIndex(x => x.id === l.id); if (i < 0) LISTS.push(l); else LISTS[i] = l };
  const max = (n: number) => (Number.isFinite(n) ? String(n) : '');

  /* ---------- toast ---------- */
  const TOAST = document.getElementById('toast') as HTMLElement & { _undo?: (() => void) | null };
  let toastT = 0;
  function toast(m: string, undo?: () => void) {
    clearTimeout(toastT);
    TOAST.innerHTML = `<span>${m}</span>${undo ? '<button class="tbtn" data-act="undo">Undo</button>' : ''}`;
    TOAST._undo = undo || null; TOAST.classList.add('show');
    toastT = window.setTimeout(() => TOAST.classList.remove('show'), undo ? 6000 : 3200);
  }

  /* ---------- the Terminal and the Radar (the shell's edge-nav, as the Overview's and the Radar's, ERRORS M425) ---------- */
  function nav(route: 'terminal' | 'radar') {
    try { parent.postMessage({ type: 'edge-nav', route }, location.origin) } catch { /* not framed */ }
  }
  function openTerminal(t: string) {
    try { localStorage.setItem('ml.symbol', t) } catch { /* storage off: the Terminal opens on its own symbol */ }
    nav('terminal');
    if (parent === window) toast(`<b>${esc(t)}</b> is set for the Terminal. Open the Terminal page to see it.`);
  }
  function openRadar() {
    nav('radar');
    if (parent === window) toast(`The Radar of ${esc(RD)} is a page of EDGE. Open it from the menu.`);
  }

  /* ---------- logos (the Terminal's; a stock without one, or whose image fails, shows its first letter) ---------- */
  const mono = (t: string, size: number) => `<span class="lg mono" style="width:${size}px;height:${size}px">${esc(t[0] || '?')}</span>`;
  const logo = (t: string, size: number) => LOGOS[t] ? `<img class="lg" src="${esc(api.logoSrc(t, LOGOS[t]))}" alt="" width="${size}" height="${size}" data-t="${esc(t)}">` : mono(t, size);
  document.addEventListener('error', e => {
    const img = e.target as HTMLImageElement;
    if (img?.tagName === 'IMG' && img.classList.contains('lg')) img.outerHTML = mono(img.dataset.t || '?', img.width || 18);
  }, true);

  /* ---------- badges ---------- */
  function badges(s: M.Stock, compact = false) {
    const out: string[] = [], eb = M.eventBadge(s), rb = M.radarBadge(s, compact);
    if (eb) out.push(`<span class="pill info" title="${esc(`Upcoming corporate actions (loaded ${M.dateLabel(F.events_loaded)}):\n${eb.all.join('\n')}`)}">${ic('cal')}${esc(eb.label)}${eb.more ? ` <span class="muted">+${eb.more}</span>` : ''}</span>`);
    if (rb) out.push(`<button class="pill radar" data-act="radar" data-t="${esc(s.t)}" title="${esc(`Radar screens met on ${RD}:\n${s.rd.map(f => `${f} ${RN[f] || ''}`).join('\n')}`)}">${ic('radar')}${esc(rb)}</button>`);
    return out.join('');
  }

  /* ---------- filters (view only) ---------- */
  let FILT: M.Filter = { radar: false, ev: false };
  const filtered = (l: WList) => tk(l).filter(t => M.passes(S(t), FILT));

  /* ---------- page ---------- */
  let FLASH: string | null = null;
  const pills = () => {
    if (FILE_ERR) return `<span class="pill warn" title="${esc(FILE_ERR)}"><span class="dot"></span>Figures unavailable</span>`;
    const lag = !F.broker_through || F.broker_through < F.prices_through;
    return `<span class="pill pos" title="Daily closes, Feature 01 and Feature 04"><span class="dot"></span>Prices to ${M.dateLabel(F.prices_through, true)}</span>` +
      `<span class="pill ${lag ? 'warn' : 'pos'}" title="Foreign flow (broker summary, Regular board) and Radar"><span class="dot"></span>${F.broker_through ? `Broker data to ${M.dateLabel(F.broker_through, true)}` : 'No broker data yet'}</span>`;
  };
  function head(l: WList) {
    const ks = ind(l), n = ks.length, rest = ks.slice(CARD_IND).map(k => INFO(k).short), sess = F.dates.length;
    const sub = FILE_ERR ? 'Your lists are shown without figures until they can be read again.' : st.view === 'cards'
      ? `One card per stock: price, ${sess}-session line and the first ${Math.min(CARD_IND, n)} indicators${rest.length ? ` (${rest.join(', ')} in Table only)` : ''}.`
      : `One row per stock: price, ${sess}-session line and ${n} indicators.`;
    return `<div class="wlh"><div><h1>Watchlist</h1><p class="muted">${esc(sub)}</p></div><div class="act"><span class="pills">${pills()}</span><button class="btn" data-act="open-ind" ${FILE_ERR ? 'disabled title="Indicators come with the figures"' : ''}>${ic('cols')}Indicators <span class="muted">${n}</span></button><button class="btn primary" data-act="open-add" aria-keyshortcuts="Alt+A" title="Add stocks to this list (Alt+A)">${ic('plus')}Add ticker<kbd>Alt+A</kbd></button></div></div>`;
  }
  function bar(l: WList) {
    const n = tk(l).length;
    return `<div class="bar1"><div class="tabs" role="tablist" aria-label="Watchlists">${LISTS.map(x => `<button role="tab" aria-selected="${x.id === l.id}" class="${x.id === l.id ? 'on' : ''}" data-act="list" data-id="${esc(x.id)}">${esc(x.name)}<span class="cnt">${x.tickers.length}</span></button>`).join('')}</div>` +
      `<button class="iconbtn sm lmenu" data-act="list-menu" aria-label="Actions for list ${esc(l.name)}" aria-haspopup="menu" title="List actions">${ic('more')}</button>` +
      `<button class="btn sm" data-act="open-new" ${LISTS.length >= LIM.lists ? 'disabled' : ''}>${ic('plus')}New list</button><span class="sp"></span>` +
      `<span class="filt" role="group" aria-label="Filter this list">${HAS_RADAR ? `<button class="tog ${FILT.radar ? 'on' : ''}" data-act="f-radar" aria-pressed="${FILT.radar}">${ic('radar')}Radar</button>` : ''}<button class="tog ${FILT.ev ? 'on' : ''}" data-act="f-ev" aria-pressed="${FILT.ev}">${ic('cal')}Corporate action</button>${FILT.radar || FILT.ev ? `<span class="meta">${filtered(l).length} of ${n}</span>` : ''}</span>` +
      (st.view === 'table' ? `<span class="meta">${TSORT ? 'Sorted by <b>' + esc(TSORT.label) + '</b>' : 'In <b>list order</b>'}</span>` : '') +
      `<div class="seg" role="group" aria-label="View"><button data-act="view" data-v="table" class="${st.view === 'table' ? 'on' : ''}" aria-pressed="${st.view === 'table'}">${ic('table')}Table</button><button data-act="view" data-v="cards" class="${st.view === 'cards' ? 'on' : ''}" aria-pressed="${st.view === 'cards'}">${ic('grid')}Cards</button></div></div>`;
  }
  const symBtn = (t: string) => `<button class="symb" data-act="detail" data-t="${esc(t)}" title="Open ${esc(t)} in Terminal">${esc(t)}</button>`;
  const menuBtn = (t: string) => `<button class="iconbtn sm mbtn" data-act="menu" data-t="${esc(t)}" aria-label="Actions for ${esc(t)}" aria-haspopup="menu">${ic('more')}</button>`;
  function card(t: string, l: WList) {
    const s = S(t), shown = ind(l).slice(0, CARD_IND);
    const chips = shown.map(k => { const it = INFO(k), x = M.indVal(F, it, s); return `<span class="chip" title="${esc(it.name)} (${asOf(k)})"><span>${esc(it.short)}</span><b class="${x.k}${x.na ? ' na' : ''}">${esc(x.v)}</b></span>` }).join('');
    const flowNote = shown.some(k => M.brokerDated(INFO(k))) ? `<div class="fnote">Foreign flow as of ${BD}</div>` : '';
    const sp = M.spark(s.trend, 300, 40, true), bg = badges(s);
    return `<div class="card wc${FLASH === t ? ' enter' : ''}" data-t="${esc(t)}"><div class="hd">${logo(t, 28)}<div class="id">${symBtn(t)}<span class="nm">${esc(s.n)}</span></div>${menuBtn(t)}</div>
  <div class="px"><b>${M.fPx(s.last) || '—'}</b><span class="chg ${M.cls(s.r1d)}">${M.fPct(s.r1d) || ''}</span><span class="m1">1M <span class="${M.cls(s.r1m)}">${M.fPct(s.r1m, 1) || '—'}</span></span></div>
  ${sp || '<div class="nospark">No price line</div>'}<div class="chips">${chips}</div>${flowNote}${bg ? `<div class="ftag">${bg}</div>` : ''}</div>`;
  }
  const noMatch = (l: WList) => `<strong>No stock in ${esc(l.name)} matches the filter</strong>${FILT.radar ? `Only stocks in Radar on ${RD}. ` : ''}${FILT.ev ? `Only stocks with a corporate action in the next ${F.event_days} days. ` : ''}<button class="lnk" data-act="f-clear">Clear filters</button>`;
  function cardsView(l: WList) {
    const n = tk(l).length, ts = filtered(l), full = n >= LIM.tickers;
    const empty = !n ? `<div class="card empty emptyc"><strong>${esc(l.name)} is empty</strong>Add stocks with <b>Add ticker</b>.</div>` : !ts.length ? `<div class="card empty emptyc">${noMatch(l)}</div>` : '';
    return `<div class="cg">${ts.map(t => card(t, l)).join('')}
  <button class="card wc addc" data-act="open-add" ${full ? 'disabled' : ''}>${ic('plus')}<span>${full ? 'List is full' : 'Add stock'}</span><span style="font-size:var(--fs-xs)">${n}${Number.isFinite(LIM.tickers) ? ` of ${LIM.tickers}` : ''}</span></button>${empty}</div>`;
  }
  /* the table (sorting changes the view only, not the list order) */
  let TSORT: M.Sort | null = null;
  function sth(k: string, label: string, unit: string, cl = '') {
    const on = TSORT && TSORT.k === k;
    return `<th class="sort ${cl}${on ? ' on' : ''}" data-act="tsort" data-k="${esc(k)}" data-label="${esc(label)}" aria-sort="${on ? (TSORT!.dir < 0 ? 'descending' : 'ascending') : 'none'}" tabindex="0"><span class="thl"><span class="arr">${on ? (TSORT!.dir < 0 ? '↓' : '↑') : ''}</span>${esc(label)}${unit ? ` <small>${unit}</small>` : ''}</span></th>`;
  }
  function tableView(l: WList) {
    const ks = ind(l), miss = '<td class="miss">—</td>';
    const rows = M.sortStocks(filtered(l).map(S), TSORT, F).map(s => {
      const sp = M.spark(s.trend, 84, 22), t = s.t;
      return `<tr data-t="${esc(t)}" class="${FLASH === t ? 'enter' : ''}"><td class="stk">${logo(t, 18)}${symBtn(t)}<span class="sub">${esc(s.n)}</span></td>${sp ? `<td class="l spk">${sp}</td>` : '<td class="l miss">—</td>'}` +
        `${s.last != null ? `<td class="strong">${M.fPx(s.last)}</td>` : miss}${s.r1d != null ? `<td class="${M.cls(s.r1d)}">${M.fPct(s.r1d)}</td>` : miss}${s.r1m != null ? `<td class="${M.cls(s.r1m)}">${M.fPct(s.r1m, 1)}</td>` : miss}` +
        ks.map(k => { const it = INFO(k), x = M.indVal(F, it, s); if (x.na) return miss; if (M.flowPill(it)) return `<td><span class="vp ${x.k || 'z'}">${esc(x.v)}</span></td>`; return `<td class="${x.k}">${esc(x.v)}</td>` }).join('') +
        `<td class="l bdg">${badges(s, true)}</td><td class="act">${menuBtn(t)}</td></tr>`;
    }).join('');
    const cols = 7 + ks.length;
    const empty = tk(l).length ? `<tr class="norow"><td colspan="${cols}" class="empty">${noMatch(l)}</td></tr>` : `<tr class="norow"><td colspan="${cols}" class="empty"><strong>${esc(l.name)} is empty</strong><button class="btn sm" data-act="open-add" style="margin-left:8px">${ic('plus')}Add stock</button></td></tr>`;
    const asof = BD === RD ? `<span>Foreign flow and Radar as of ${BD} (broker data)</span>` : `<span>Foreign flow as of ${BD} (broker data)${DOT}Radar as of ${RD}</span>`;
    return `<div class="card tcard"><div class="tbl-wrap"><table class="tbl o1 padat"><thead><tr>${sth('t', 'Stock', '', 'l')}<th class="l" title="Last ${F.dates.length} closes">Trend</th>${sth('last', 'Last', '')}${sth('r1d', '1D', '')}${sth('r1m', '1M', '')}${ks.map(k => sth(k, INFO(k).short, M.brokerDated(INFO(k)) ? BD : '')).join('')}<th class="l">Events · Radar</th><th class="act"></th></tr></thead><tbody>${rows || empty}</tbody></table></div>
  <div class="lgd"><span><span class="lg2"></span>No value on that date</span>${asof}${TSORT ? '<button class="lnk" data-act="tsort-reset">Back to list order</button>' : ''}<span class="sp"></span><span>Prices to ${PD}${DOT}corporate actions loaded ${M.dateLabel(F.events_loaded)}</span></div></div>`;
  }
  function render() {
    closeMenu(); hideTip();
    if (!L()) st.active = LISTS[0]?.id || '';
    const l = L();
    PAGE.removeAttribute('aria-busy');
    const warn = FILE_ERR ? `<div class="card fileerr" role="status"><strong>Figures unavailable</strong><span>${esc(FILE_ERR)}</span><button class="btn sm" data-act="retry-file">Try again</button></div>` : '';
    PAGE.innerHTML = head(l) + warn + bar(l) + (st.view === 'cards' ? cardsView(l) : tableView(l));
    if (FLASH) { const el = PAGE.querySelector(`[data-t="${CSS.escape(FLASH)}"]`); if (el && !reduceMotion()) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); FLASH = null }
  }
  function renderFailure(text: string) {
    PAGE.removeAttribute('aria-busy');
    PAGE.innerHTML = `<div class="wlh"><div><h1>Watchlist</h1></div></div><div class="card empty"><strong>The watchlist could not be shown</strong><p>${esc(text)}</p><p style="margin-top:var(--s-6)"><button class="btn" data-act="retry">Try again</button></p></div>`;
  }

  /* ---------- menus (placed from their measured size) ---------- */
  let MENU: Menu | null = null;
  function closeMenu() { if (MENU) { MENU.remove(); MENU = null } }
  function openMenu(btn: HTMLElement, items: [string, string, string?][]) {
    closeMenu();
    const r = btn.getBoundingClientRect(), m = document.createElement('div') as Menu;
    m.className = 'pop wlmenu'; m.setAttribute('role', 'menu');
    m.innerHTML = items.map(([act, label, attrs]) => label === '-' ? '<div class="msep"></div>' : `<button class="menu-item${/data-danger/.test(attrs || '') ? ' danger' : ''}" role="menuitem" data-act="${act}" ${attrs || ''}>${label}</button>`).join('');
    document.body.appendChild(m);
    const w = m.offsetWidth, h = m.offsetHeight;
    let y = r.bottom + 4; if (y + h > innerHeight - 8) y = r.top - h - 4;
    m.style.left = Math.min(Math.max(8, r.right - w), innerWidth - w - 8) + 'px'; m.style.top = Math.max(8, y) + 'px';
    MENU = m; m._for = btn; btn.setAttribute('aria-expanded', 'true');
    (m.querySelector('button:not([disabled])') as HTMLElement | null)?.focus();
  }
  const closeMenuOf = () => { MENU?._for?.removeAttribute('aria-expanded'); closeMenu() };

  /* ---------- dialogs ---------- */
  let DLG: Dlg | null = null;
  function openDialog(html: string, o: { onKey?: (e: KeyboardEvent) => void; onClose?: () => void } = {}) {
    closeDialog(true); closeMenuOf();
    const opener = document.activeElement, bd = document.createElement('div');
    bd.className = 'backdrop'; bd.innerHTML = html; document.body.appendChild(bd);
    DLG = { bd, opener, ...o };
    const coarse = matchMedia('(pointer: coarse)').matches;
    ((coarse ? null : bd.querySelector('[data-autofocus]')) as HTMLElement | null || bd.querySelector('button') as HTMLElement | null)?.focus();
    return bd;
  }
  function closeDialog(instant = false) {
    if (!DLG) return;
    const { bd, opener, onClose } = DLG; DLG = null; onClose?.();
    if (instant || reduceMotion()) bd.remove(); else { bd.classList.add('out'); setTimeout(() => bd.remove(), 150) }
    if (opener instanceof HTMLElement && document.contains(opener)) opener.focus();
  }
  const q$ = <T extends HTMLElement = HTMLElement>(s: string) => DLG!.bd.querySelector(s) as T;
  const dhead = (title: string, sub: string) => `<div class="dialog-head"><div><strong>${title}</strong><span class="dsub">${sub}</span></div><button class="iconbtn sm" data-act="close" aria-label="Close">${ic('x')}</button></div>`;

  /* delete list (confirm + undo) */
  let DELID: string | null = null;
  function openDelList(id: string) {
    const l = L(id); if (!l) return;
    if (LISTS.length <= 1) { toast('The last list cannot be deleted. Create another list first.'); return }
    DELID = id; const ts = tk(l), n = ts.length;
    const others = ts.filter(t => LISTS.some(x => x.id !== id && tk(x).includes(t))).length;
    openDialog(`<div class="dialog dell" role="alertdialog" aria-modal="true" aria-label="Delete list ${esc(l.name)}">${dhead(`Delete “${esc(l.name)}”?`, `${n} stocks${DOT}${ind(l).length} indicators`)}
  <div class="dialog-body"><p>The list and its indicator choice are deleted.${n ? ` ${n - others} of its ${n} stocks are in no other list.` : ''} Other lists are not changed.</p>${LISTS[0].id === id ? `<p>The Screener’s star adds stocks to this list. After deleting, it adds them to “${esc(LISTS[1].name)}”.</p>` : ''}<p class="note">You can undo right after deleting.</p></div>
  <div class="dialog-foot"><button class="btn" data-act="close" data-autofocus>Cancel</button><button class="btn danger" data-act="del-list-go">Delete list</button></div></div>`, { onClose: () => { DELID = null } });
  }
  async function delListGo(btn: HTMLButtonElement) {
    if (!DELID || btn.disabled) return;
    btn.disabled = true;
    const id = DELID, idx = LISTS.findIndex(l => l.id === id), wasActive = st.active === id;
    let snap: WList;
    try { snap = await api.remove(id) } catch (e) { btn.disabled = false; toast(esc(msg(e, 'The list was not deleted. Try again.'))); return }
    LISTS.splice(idx, 1);
    if (wasActive) { st.active = LISTS[Math.max(0, idx - 1)].id; persist(); FILT = { radar: false, ev: false }; TSORT = null }
    closeDialog(true); render();
    toast(`<b>${esc(snap.name)}</b> deleted`, async () => {
      try {
        const made = await api.create(M.restoreListBody(snap));
        LISTS = (await api.lists()).lists;
        if (wasActive) { st.active = made.id; persist() }
        render(); toast(`<b>${esc(snap.name)}</b> restored`);
      } catch (e) { toast(esc(msg(e, 'The list could not be restored.'))) }
    });
  }
  /* rename list */
  function openRename(id: string) {
    const l = L(id);
    const bd = openDialog(`<div class="dialog dell" role="dialog" aria-modal="true" aria-label="Rename list">${dhead('Rename list', `${l.tickers.length} stocks`)}
  <div class="dialog-body"><label class="field"><span>List name</span><input class="inp" id="rnName" data-autofocus maxlength="${max(LIM.name)}" value="${esc(l.name)}" autocomplete="off"><small class="ferr" id="rnErr"></small></label></div>
  <div class="dialog-foot"><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="rn-go" data-id="${esc(id)}">Save name</button></div></div>`,
      { onKey: e => { if ((e.target as HTMLElement).id === 'rnName' && e.key === 'Enter') { e.preventDefault(); void renameGo(id) } } });
    const i = bd.querySelector('#rnName') as HTMLInputElement; i.select();
    i.addEventListener('input', () => { (bd.querySelector('#rnErr') as HTMLElement).textContent = ''; i.classList.remove('is-err') });
  }
  let renaming = false;
  async function renameGo(id: string) {
    if (renaming || !DLG) return;
    const i = q$<HTMLInputElement>('#rnName'), nm = i.value.trim();
    const fail = (t: string) => { if (!DLG) return; q$('#rnErr').textContent = t; i.classList.add('is-err'); i.focus() };
    if (!nm) return fail('Enter a name.');
    if (M.dupName(LISTS, nm, id)) return fail(`“${nm}” is already a list name. Pick another.`);
    if (nm === L(id).name) { closeDialog(true); return }
    renaming = true;
    try { put(await api.rename(id, nm)) } catch (e) { renaming = false; return fail(msg(e, 'The name was not saved. Try again.')) }
    renaming = false; closeDialog(true); render(); toast(`List renamed to <b>${esc(L(id).name)}</b>`);
  }

  /* add ticker */
  let AD: { target: string; q: string; hi: number; added: Set<string>; busy: Set<string>; recent: string[] } | null = null;
  function openAdd(target?: string) {
    const tg = target || st.active;
    AD = { target: tg, q: '', hi: 0, added: new Set(), busy: new Set(), recent: M.suggestions(LISTS, L(tg), BY, F) };
    const bd = openDialog(`<div class="dialog addd" role="dialog" aria-modal="true" aria-label="Add stocks">${dhead('Add stocks', '<span id="adSub"></span>')}
  <div class="addh"><div class="find2">${ic('search')}<input class="inp" id="adQ" data-autofocus placeholder="Search code or name, e.g. AD" aria-label="Search stocks" autocomplete="off"></div>
  <div class="row tgtrow"><span class="muted">Add to</span><button class="btn sm" id="adTgt" data-act="ad-target" aria-haspopup="menu" style="gap:6px"></button><span class="muted kbdh" style="margin-left:auto">↑↓ choose · Enter add</span></div></div>
  <div id="adRes"></div>
  <div class="eyebrow pad sepT" id="adRecentH">Suggestions</div><div id="adRecent" class="recent"></div>
  <div class="dialog-foot split"><span class="note">Paste several codes at once, e.g. <b>${esc(exampleCodes())}</b></span><button class="btn" data-act="close">Done</button></div></div>`, { onKey: adKey, onClose: () => { AD = null } });
    (bd.querySelector('#adQ') as HTMLInputElement).addEventListener('input', e => { AD!.q = (e.target as HTMLInputElement).value; AD!.hi = 0; renderAdd() });
    renderAdd();
  }
  const exampleCodes = () => UL.filter(s => s.last != null).slice(0, 3).map(s => s.t).join(', ');
  const adMatches = () => (AD ? M.search(UL, BY, AD.q) : []);
  function adState(t: string) {
    const l = L(AD!.target), have = tk(l).includes(t);
    if (AD!.added.has(t) && have) return 'added';
    if (have) return 'in';
    if (l.tickers.length >= LIM.tickers) return 'full';
    return 'can';
  }
  function renderAdd() {
    if (!AD || !DLG) return;
    const l = L(AD.target), n = l.tickers.length;
    q$('#adSub').textContent = `To ${l.name}${DOT}${n}${Number.isFinite(LIM.tickers) ? ` of ${LIM.tickers}` : ''} used`;
    q$('#adTgt').innerHTML = `${esc(l.name)} <span class="muted">${n}</span>${ic('chev')}`;
    const res = adMatches(), shown = res.slice(0, 6), multi = M.isMulti(AD.q);
    let h = '';
    if (FILE_ERR) h = `<div class="note pad-note">Stock search needs today’s figures, which cannot be read right now. Try again later.</div>`;
    else if (!AD.q.trim()) h = `<div class="eyebrow pad">Type a stock code or name${DOT}${UL.length} stocks</div>`;
    else {
      h = `<div class="eyebrow pad">Results${DOT}${res.length}</div>`;
      if (multi) {
        const unk = M.parseCodes(AD.q).filter(c => !BY.has(c)), can = res.filter(u => adState(u.t) === 'can');
        h += `<div class="ar multi"><div><b>${can.length} codes can be added</b><span class="sub">${unk.length ? `Unknown: ${esc(unk.join(', '))}` : 'Every code is known'}</span></div><div></div>${can.length ? `<button class="btn sm primary" data-act="ad-many">${ic('plus')}Add ${can.length}</button>` : '<span class="pill">Nothing new</span>'}</div>`;
      }
      if (!res.length && !multi) h += `<div class="ar"><div><span class="muted">No stock matches “${esc(AD.q)}”.</span></div><div></div><div></div></div>`;
      AD.hi = Math.min(AD.hi, Math.max(0, shown.length - 1));
      h += shown.map((u, i) => {
        const sx = adState(u.t), busy = AD!.busy.has(u.t);
        return `<div class="ar ${i === AD!.hi ? 'on' : ''}" data-row="${esc(u.t)}"><div class="arid">${logo(u.t, 28)}<div><b>${esc(u.t)}</b><span class="sub">${esc(u.n)}${u.sec && u.sec !== 'Undefined' ? DOT + esc(u.sec) : ''}</span></div></div><div class="r"><span>${M.fPx(u.last) || '<span class="na">No price</span>'}</span><span class="${M.cls(u.r1d)}">${u.last != null ? M.fPct(u.r1d) || '' : ''}</span></div>` +
          (sx === 'added' ? '<span class="pill pos">✓ Added</span>' : sx === 'in' ? `<span class="pill">✓ In ${esc(l.name)}</span>` : sx === 'full' ? '<button class="btn sm" disabled>List is full</button>' : `<button class="btn sm" data-act="ad-one" data-t="${esc(u.t)}" ${busy ? 'disabled aria-busy="true"' : ''}>${ic('plus')}Add</button>`) + '</div>';
      }).join('');
      if (res.length > shown.length) h += `<div class="note morex">+${res.length - shown.length} more: refine the search</div>`;
    }
    q$('#adRes').innerHTML = h;
    q$('#adRecentH').hidden = q$('#adRecent').hidden = !AD.recent.length;
    q$('#adRecent').innerHTML = AD.recent.map(t => { const sx = adState(t); return `<button class="tog ${sx !== 'can' ? 'done' : ''}" data-act="ad-one" data-t="${esc(t)}" ${sx !== 'can' ? 'disabled' : ''} title="${esc(S(t).n)}">${logo(t, 16)}<b>${esc(t)}</b>${sx === 'can' ? ic('plus') : '✓'}</button>` }).join('');
  }
  async function adAdd(ts: string[], quiet = false): Promise<string[]> {
    if (!AD) return [];
    const ad = AD, target = ad.target, l = L(target);
    ts = ts.filter(t => !ad.busy.has(t));
    if (!ts.length) return [];
    ts.forEach(t => ad.busy.add(t)); renderAdd();
    try {
      const r = await api.addTickers(target, ts);
      put(r.list); r.added.forEach(t => ad.added.add(t));
      if (target === st.active) { FLASH = r.added[r.added.length - 1] || null; render() }
      if (!quiet) {
        const n = L(target).tickers.length;
        if (r.added.length) toast(`<b>${esc(r.added[0])}</b> added to ${esc(l.name)}${DOT}${n} stocks`);
        else toast(`${esc(ts[0])} is already in ${esc(l.name)}`);
      }
      return r.added;
    } catch (e) {
      toast(esc(msg(e, 'The stock was not added. Try again.')));
      return [];
    } finally { ts.forEach(t => ad.busy.delete(t)); renderAdd() }
  }
  function adKey(e: KeyboardEvent) {
    if (!AD || (e.target as HTMLElement).id !== 'adQ') return;
    const rows = [...DLG!.bd.querySelectorAll<HTMLElement>('.ar[data-row]')];
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (!rows.length) return; AD.hi = (AD.hi + (e.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length; renderAdd() }
    else if (e.key === 'Enter') {
      e.preventDefault();
      if (M.isMulti(AD.q)) { void adMany(); return }
      const r = rows[AD.hi]; if (r && adState(r.dataset.row!) === 'can') void adAdd([r.dataset.row!]);
    }
  }
  async function adMany() {
    if (!AD) return;
    const can = adMatches().filter(u => adState(u.t) === 'can').map(u => u.t), l = L(AD.target);
    if (!can.length) { toast('No new stock added'); return }
    const ok = await adAdd(can, true);
    toast(ok.length ? `${ok.length} stocks added to ${esc(l.name)}: <b>${esc(ok.join(', '))}</b>` : 'No new stock added');
  }

  /* new list */
  let NL: { name: string; tickers: string[]; q: string; from: string; custom: boolean; busy: boolean; err: string } | null = null;
  function openNew() {
    if (LISTS.length >= LIM.lists) { toast(`At most ${LIM.lists} lists. Delete one first.`); return }
    NL = { name: '', tickers: [], q: '', from: st.active, custom: false, busy: false, err: '' };
    const lim = Number.isFinite(LIM.lists) ? `List ${LISTS.length + 1} of at most ${LIM.lists}` : `List ${LISTS.length + 1}`;
    const each = Number.isFinite(LIM.tickers) ? `${DOT}up to ${LIM.tickers} stocks each` : '';
    const bd = openDialog(`<div class="dialog nl" role="dialog" aria-modal="true" aria-label="New list">${dhead('New list', lim + each)}
  <div class="dialog-body">
   <label class="field"><span>List name</span><input class="inp" id="nlName" data-autofocus maxlength="${max(LIM.name)}" placeholder="e.g. Commodity swing" autocomplete="off"><small class="ferr" id="nlErr"></small></label>
   <div class="field"><div class="lbl2"><span>Stocks</span><span id="nlCnt"></span></div>
    <div class="tkbox" id="nlBox"><span id="nlChips" style="display:contents"></span><input id="nlQ" placeholder="Type a code, e.g. ${esc(UL[0]?.t || 'BBCA')}" aria-label="Search stocks" autocomplete="off"></div>
    <div class="sug" id="nlSug"></div></div>
   <div class="field"><div class="lbl2"><span>Indicators shown</span><button class="lnk" data-act="nl-custom" id="nlCustom"></button></div>
    <select class="sel" id="nlFrom" aria-label="Copy indicators from">${LISTS.map(l => `<option value="${esc(l.id)}" ${l.id === st.active ? 'selected' : ''}>Same as ${esc(l.name)}</option>`).join('')}<option value="__def">EDGE default</option></select>
    <div class="ftag" id="nlTags" style="margin-top:var(--s-3)"></div></div>
  </div>
  <div class="dialog-foot split"><span class="note">Stocks and indicators can be changed later</span><span class="row"><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="nl-create" id="nlGo">Create list</button></span></div></div>`, { onKey: nlKey, onClose: () => { NL = null } });
    bd.querySelector('#nlName')!.addEventListener('input', e => { NL!.name = (e.target as HTMLInputElement).value; if (NL!.err) { NL!.err = ''; renderNew() } });
    bd.querySelector('#nlQ')!.addEventListener('input', e => { NL!.q = (e.target as HTMLInputElement).value; renderNew() });
    bd.querySelector('#nlFrom')!.addEventListener('change', e => { NL!.from = (e.target as HTMLSelectElement).value; renderNew() });
    bd.querySelector('#nlBox')!.addEventListener('click', e => { if ((e.target as HTMLElement).id === 'nlBox') (bd.querySelector('#nlQ') as HTMLElement).focus() });
    renderNew();
  }
  /** the new list's indicators: copied from a list as it holds them (null: it follows the default), or the default */
  const nlRaw = () => (NL!.from === '__def' ? null : L(NL!.from)?.indicators ?? null);
  const nlInd = () => M.indicatorsOf({ indicators: nlRaw() }, CAT, LIM.indicators);
  const nlSug = () => (NL!.q.trim() ? M.search(UL, BY, NL!.q.split(/[\s,;]+/)[0] || '').filter(u => !NL!.tickers.includes(u.t)).slice(0, 4) : []);
  function renderNew() {
    if (!NL || !DLG) return;
    q$('#nlChips').innerHTML = NL.tickers.map(t => `<span class="pill ch">${esc(t)}<button class="chx" data-act="nl-rm" data-t="${esc(t)}" aria-label="Remove ${esc(t)}">${ic('x')}</button></span>`).join('');
    q$('#nlCnt').textContent = `${NL.tickers.length} chosen`;
    const sg = nlSug(), q = NL.q.trim();
    q$('#nlSug').innerHTML = q ? (sg.length ? sg.map(u => `<button class="sgi" data-act="nl-add" data-t="${esc(u.t)}"><b style="font-weight:var(--fw-semibold)">${esc(u.t)}</b><span>${esc(u.n)}</span><span class="muted">${u.last != null ? M.fPx(u.last) : 'no price'}</span></button>`).join('') : `<div class="sgi empty"><span class="muted">No stock matches “${esc(q)}”</span></div>`) : '';
    q$('#nlSug').style.display = q ? '' : 'none';
    q$('#nlTags').innerHTML = nlInd().map(k => `<span class="pill">${esc(INFO(k).name)}</span>`).join('');
    q$('#nlCustom').textContent = NL.custom ? '✓ Choose after creating' : 'Choose my own';
    q$('#nlErr').textContent = NL.err; q$('#nlName').classList.toggle('is-err', !!NL.err);
  }
  function nlAdd(t: string) {
    if (!NL || !BY.has(t) || NL.tickers.includes(t)) return;
    if (NL.tickers.length >= LIM.tickers) { toast(`At most ${LIM.tickers} stocks per list`); return }
    NL.tickers.push(t); NL.q = ''; q$<HTMLInputElement>('#nlQ').value = ''; renderNew(); q$('#nlQ').focus();
  }
  function nlKey(e: KeyboardEvent) {
    if (!NL) return;
    const id = (e.target as HTMLElement).id;
    if (id === 'nlQ') {
      if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); const sg = nlSug(); if (sg[0]) nlAdd(sg[0].t) }
      else if (e.key === 'Backspace' && !(e.target as HTMLInputElement).value && NL.tickers.length) { NL.tickers.pop(); renderNew() }
    } else if (id === 'nlName' && e.key === 'Enter') { e.preventDefault(); void nlCreate() }
  }
  async function nlCreate() {
    if (!NL || NL.busy) return;
    const nm = NL.name.trim(), focusName = () => q$('#nlName')?.focus();
    if (!nm) { NL.err = 'Enter a list name.'; renderNew(); focusName(); return }
    if (M.dupName(LISTS, nm)) { NL.err = `“${nm}” is already a list name. Pick another.`; renderNew(); focusName(); return }
    NL.busy = true; q$<HTMLButtonElement>('#nlGo').disabled = true;
    const custom = NL.custom;
    let made: WList;
    try { made = await api.create({ name: nm, tickers: NL.tickers, indicators: nlRaw() }) }
    catch (e) {
      if (!NL) return;
      NL.busy = false; NL.err = msg(e, 'The list was not created. Try again.'); renderNew(); q$<HTMLButtonElement>('#nlGo').disabled = false; focusName(); return;
    }
    LISTS.push(made); st.active = made.id; persist(); FILT = { radar: false, ev: false }; TSORT = null;
    closeDialog(true); render();
    toast(`<b>${esc(nm)}</b> created${DOT}${made.tickers.length} stocks`);
    const tab = PAGE.querySelector<HTMLElement>(`[data-act="list"][data-id="${CSS.escape(made.id)}"]`);
    if (tab) { tab.classList.add('enter'); tab.focus() }
    if (custom) openInd();
  }

  /* indicators (draft, then Save / Cancel / Reset) */
  let IND: { keys: string[]; scope: 'list' | 'all'; q: string; closed: Set<string>; drag: string | null; note: string; busy: boolean } | null = null;
  function openInd() {
    IND = { keys: [...ind(L())], scope: 'list', q: '', closed: new Set(), drag: null, note: '', busy: false };
    const bd = openDialog(`<div class="dialog indd" role="dialog" aria-modal="true" aria-label="Indicators">
   ${dhead('Indicators', 'Choose what is shown for every stock in this list. Every value is read as stored; nothing is recalculated.')}
   <div class="db3"><div class="colL" id="indL"></div>
    <div class="colR"><div class="find2" style="margin:0 0 var(--s-4)">${ic('search')}<input class="inp" id="indQ" aria-label="Search indicators" autocomplete="off"></div><div id="indR"></div></div></div>
   <div class="dialog-foot split"><span class="row"><button class="btn ghost" data-act="ind-reset">Reset to default</button><span class="note" id="indNote"></span></span><span class="row"><span class="scopef" id="indScope"></span><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="ind-save" id="indGo">Save</button></span></div></div>`, { onKey: indKey, onClose: () => { IND = null } });
    bd.querySelector('#indQ')!.addEventListener('input', e => { IND!.q = (e.target as HTMLInputElement).value; renderInd() });
    const box = bd.querySelector('#indL') as HTMLElement;
    const row = (e: Event) => (e.target as HTMLElement).closest?.('.si2') as HTMLElement | null;
    box.addEventListener('dragstart', e => { const r = row(e); if (!r || !IND) return; IND.drag = r.dataset.k!; r.classList.add('dragging'); e.dataTransfer!.effectAllowed = 'move'; try { e.dataTransfer!.setData('text/plain', r.dataset.k!) } catch { /* some browsers refuse */ } });
    box.addEventListener('dragover', e => { const r = row(e); if (!r || !IND?.drag) return; e.preventDefault(); box.querySelectorAll('.si2').forEach(x => x.classList.remove('dropb', 'dropa')); const b = r.getBoundingClientRect(); r.classList.add(e.clientY < b.top + b.height / 2 ? 'dropb' : 'dropa') });
    box.addEventListener('drop', e => { const r = row(e); if (!r || !IND?.drag) return; e.preventDefault(); const b = r.getBoundingClientRect(); indMove(IND.drag, r.dataset.k!, e.clientY < b.top + b.height / 2) });
    box.addEventListener('dragend', () => { if (IND) { IND.drag = null; renderInd() } });
    renderInd();
  }
  function indMove(k: string, target: string, before: boolean) {
    const a = IND!.keys.filter(x => x !== k); let i = a.indexOf(target); if (i < 0) return; if (!before) i++;
    a.splice(i, 0, k); IND!.keys = a; IND!.note = 'Order changed · not saved'; renderInd();
  }
  function renderInd() {
    if (!IND || !DLG) return;
    const l = L(), k = IND.keys, n = k.length, mx = LIM.indicators, free = Number.isFinite(mx) ? mx - n : Infinity;
    const ps = tk(l).map(S).find(s => s.last != null) || null;
    q$<HTMLInputElement>('#indQ').placeholder = `Search ${CAT.items.length - n} more indicators`;
    const slots = free > 0 ? (Number.isFinite(free) ? `<span class="sx-plus">${ic('plus')}</span><b>${free} slot${free > 1 ? 's' : ''} left</b><span>Pick indicators from the list</span>` : `<span class="sx-plus">${ic('plus')}</span><b>Add more</b><span>Pick indicators from the list</span>`) : `<b>All ${mx} slots used</b><span>Remove one to add another</span>`;
    q$('#indL').innerHTML = `
   <div class="lbl2"><span>Chosen</span><span>${n}${Number.isFinite(mx) ? ` of ${mx}` : ''}</span></div>
   <div class="sel2l">${k.map((x, i) => { const it = INFO(x), v = M.indVal(F, it, ps); return `<div class="si2 ${i >= CARD_IND ? 'off' : ''}" data-k="${esc(x)}" draggable="true" tabindex="0" aria-label="${esc(it.name)}, position ${i + 1}. Alt+arrow keys move it."><svg class="ic ic-sm gr"><use href="#i-grip"/></svg><span class="no">${i + 1}</span><div class="nm"><b>${esc(it.name)}</b><small>${esc(it.note)}${ps ? `${DOT}${esc(ps.t)} ${esc(v.v)}` : ''}</small></div><span class="pill">${esc(it.family.split(' ')[0])}</span><button class="iconbtn sm" data-act="ind-rm" data-k="${esc(x)}" aria-label="Remove ${esc(it.name)}">${ic('x')}</button></div>${i === CARD_IND - 1 && n > CARD_IND ? `<div class="cut"><span>Cards show the first ${CARD_IND}${DOT}Table shows all</span></div>` : ''}` }).join('')}</div>
   <div class="slotx${free > 0 ? '' : ' full'}">${slots}</div>`;
    const q = IND.q.trim().toLowerCase();
    q$('#indR').innerHTML = CAT.families.map(([f, a]) => {
      const items = a.filter(c => !q || c.name.toLowerCase().includes(q) || c.note.toLowerCase().includes(q));
      if (q && !items.length) return '';
      const open = q || !IND!.closed.has(f);
      return `<div class="fam2"><button class="fh" data-act="ind-fam" data-f="${esc(f)}" aria-expanded="${!!open}">${ic(open ? 'chev' : 'chevr')}<span class="fpill">${esc(f)}<span class="fc">${a.length}</span></span></button>${open ? items.map(c => { const on = k.includes(c.key); return `<div class="fi ${on ? 'fon' : ''}"><span>${esc(c.name)} <span class="muted">${esc(c.note)}</span></span>${on ? `<span class="chk" role="img" aria-label="Chosen" title="Chosen">${ic('check')}</span>` : `<button class="iconbtn sm add" data-act="ind-add" data-k="${esc(c.key)}" ${free > 0 ? '' : 'disabled'} aria-label="Add ${esc(c.name)}">${ic('plus')}</button>`}</div>` }).join('') : ''}</div>`;
    }).join('') || `<div class="note" style="padding:var(--s-6) 0">No indicator matches “${esc(IND.q)}”.</div>`;
    q$('#indScope').innerHTML = `<span class="sl">Save to</span><div class="seg sm" role="group" aria-label="Save to"><button data-act="ind-scope" data-v="list" class="${IND.scope === 'list' ? 'on' : ''}" aria-pressed="${IND.scope === 'list'}">${esc(l.name)} only</button><button data-act="ind-scope" data-v="all" class="${IND.scope === 'all' ? 'on' : ''}" aria-pressed="${IND.scope === 'all'}">All ${LISTS.length} lists</button></div>`;
    q$('#indNote').textContent = IND.note;
  }
  function indKey(e: KeyboardEvent) {
    if (!IND) return;
    const r = (e.target as HTMLElement).closest?.('.si2') as HTMLElement | null;
    if (r && e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
      e.preventDefault();
      const i = IND.keys.indexOf(r.dataset.k!), j = i + (e.key === 'ArrowUp' ? -1 : 1);
      if (j < 0 || j >= IND.keys.length) return;
      const a = [...IND.keys];[a[i], a[j]] = [a[j], a[i]]; IND.keys = a; IND.note = 'Order changed · not saved'; renderInd();
      q$(`.si2[data-k="${CSS.escape(a[j])}"]`)?.focus();
    }
  }
  async function indSave() {
    if (!IND || IND.busy) return;
    if (!IND.keys.length) { IND.note = 'Choose at least 1 indicator.'; renderInd(); return }
    const sc = IND.scope, keys = [...IND.keys], l = L(), nm = l.name;
    IND.busy = true; q$<HTMLButtonElement>('#indGo').disabled = true;
    try {
      if (sc === 'all') LISTS = await api.setIndicatorsAll(keys);
      else put(await api.setIndicators(l.id, keys));
    } catch (e) {
      if (!IND) return;
      IND.busy = false; IND.note = msg(e, 'The indicators were not saved. Try again.'); renderInd(); q$<HTMLButtonElement>('#indGo').disabled = false; return;
    }
    closeDialog(); render();
    toast(`Indicators saved for ${sc === 'all' ? 'all lists' : esc(nm)}${DOT}${keys.length} indicators`);
  }

  /* remove a stock (undo puts it back at its place) */
  function removeStock(t: string) {
    const lid = st.active, l = L(), body = M.restoreTickerBody(l, t), el = PAGE.querySelector(`[data-t="${CSS.escape(t)}"]`);
    const doIt = async () => {
      try { await api.removeTicker(lid, t) } catch (e) { render(); toast(esc(msg(e, 'The stock was not removed. Try again.'))); return }
      const cur = L(lid); if (cur) { cur.tickers = cur.tickers.filter(x => x.ticker !== t); }
      render();
      toast(`<b>${esc(t)}</b> removed from ${esc(l.name)}`, async () => {
        if (!body) return;
        try {
          const r = await api.addTickers(lid, body.tickers, body.position); put(r.list);
          if (lid === st.active) FLASH = t;
          render(); toast(`<b>${esc(t)}</b> back in ${esc(l.name)}`);
        } catch (e) { toast(esc(msg(e, 'The stock could not be put back.'))) }
      });
    };
    if (el && !reduceMotion()) { el.classList.add('leaving'); setTimeout(() => void doIt(), 150) } else void doIt();
  }

  /* ---------- events ---------- */
  document.addEventListener('click', e => {
    const target = e.target as HTMLElement;
    if (MENU && !target.closest('.wlmenu') && !target.closest('[data-act="menu"]') && !target.closest('[data-act="ad-target"]') && !target.closest('[data-act="list-menu"]')) closeMenuOf();
    if (DLG && target === DLG.bd) { closeDialog(); return }
    const b = target.closest('[data-act]') as HTMLButtonElement | null;
    if (!b || b.disabled) return;
    const a = b.dataset.act, t = b.dataset.t || '';
    switch (a) {
      case 'retry': void boot(); break;
      case 'retry-file': void loadFile().then(() => render()); break;
      case 'list': if (b.dataset.id !== st.active) { TSORT = null; st.active = b.dataset.id!; persist(); render() } break;
      case 'f-radar': case 'f-ev': {
        const k = a === 'f-radar' ? 'radar' : 'ev'; FILT[k] = !FILT[k]; render();
        const l = L(), n = filtered(l).length, all = tk(l).length;
        const what = k === 'radar' ? `only stocks in Radar (${RD})` : `only stocks with a corporate action in the next ${F.event_days} days`;
        toast(FILT[k] ? `Filtered: ${what}${DOT}${n} of ${all}` : `${k === 'radar' ? 'Radar' : 'Corporate action'} filter off${DOT}${n} of ${all}`);
        PAGE.querySelector<HTMLElement>(`[data-act="${a}"]`)?.focus(); break;
      }
      case 'f-clear': FILT = { radar: false, ev: false }; render(); toast('Filters off'); break;
      case 'view': if (b.dataset.v !== st.view) { st.view = b.dataset.v === 'table' ? 'table' : 'cards'; persist(); render() } break;
      case 'tsort': { const k = b.dataset.k!; TSORT = M.nextSort(TSORT, k, b.dataset.label!); render(); PAGE.querySelector<HTMLElement>(`th[data-k="${CSS.escape(k)}"]`)?.focus(); break }
      case 'tsort-reset': TSORT = null; render(); break;
      case 'open-add': openAdd(); break;
      case 'open-new': openNew(); break;
      case 'open-ind': openInd(); break;
      case 'close': closeDialog(); break;
      case 'detail': closeMenuOf(); openTerminal(t); break;
      case 'radar': hideTip(); openRadar(); break;
      case 'menu': {
        if (MENU && MENU._for === b) { closeMenuOf(); break }
        const l = L();
        openMenu(b, [['detail', `${ic('terminal')}Open in Terminal`, `data-t="${esc(t)}"`], ['', '-'], ['remove', `Remove from ${esc(l.name)}`, `data-t="${esc(t)}" data-danger`]]);
        break;
      }
      case 'list-menu': {
        if (MENU && MENU._for === b) { closeMenuOf(); break }
        const l = L(), last = LISTS.length <= 1;
        openMenu(b, [['rename', `Rename ${esc(l.name)}`, `data-id="${esc(l.id)}"`], ['', '-'],
          ['del-list', last ? `Delete ${esc(l.name)} <span class="muted" style="margin-left:auto;padding-left:var(--s-6);font-size:var(--fs-xs)">last list</span>` : `Delete ${esc(l.name)}`, `data-id="${esc(l.id)}" ${last ? 'disabled' : 'data-danger'}`]]);
        break;
      }
      case 'rename': closeMenuOf(); openRename(b.dataset.id!); break;
      case 'rn-go': void renameGo(b.dataset.id!); break;
      case 'del-list': closeMenuOf(); openDelList(b.dataset.id!); break;
      case 'del-list-go': void delListGo(b); break;
      case 'remove': closeMenuOf(); removeStock(t); break;
      case 'undo': { const u = TOAST._undo; TOAST._undo = null; TOAST.classList.remove('show'); u?.(); break }
      case 'ad-one': void adAdd([t]); break;
      case 'ad-many': void adMany(); break;
      case 'ad-target': {
        if (MENU && MENU._for === b) { closeMenuOf(); break }
        openMenu(b, LISTS.map(l => ['ad-pick', `${esc(l.name)} <span class="muted" style="margin-left:auto">${l.tickers.length}</span>${l.id === AD!.target ? ' ✓' : ''}`, `data-id="${esc(l.id)}"`] as [string, string, string]));
        break;
      }
      case 'ad-pick': closeMenuOf(); if (AD) { AD.target = b.dataset.id!; AD.added.clear(); AD.recent = M.suggestions(LISTS, L(AD.target), BY, F); renderAdd(); q$('#adQ').focus() } break;
      case 'nl-add': nlAdd(t); break;
      case 'nl-rm': if (NL) { NL.tickers = NL.tickers.filter(x => x !== t); renderNew(); q$('#nlQ').focus() } break;
      case 'nl-custom': if (NL) { NL.custom = !NL.custom; renderNew() } break;
      case 'nl-create': void nlCreate(); break;
      case 'ind-scope': if (IND) { IND.scope = b.dataset.v === 'all' ? 'all' : 'list'; renderInd() } break;
      case 'ind-rm': if (IND) { IND.keys = IND.keys.filter(x => x !== b.dataset.k); IND.note = 'Not saved'; renderInd() } break;
      case 'ind-add': if (IND && IND.keys.length < LIM.indicators && !IND.keys.includes(b.dataset.k!)) { IND.keys.push(b.dataset.k!); IND.note = 'Not saved'; renderInd() } break;
      case 'ind-fam': if (IND) { const f = b.dataset.f!; if (IND.closed.has(f)) IND.closed.delete(f); else IND.closed.add(f); renderInd() } break;
      case 'ind-reset': if (IND) { IND.keys = [...CAT.def].slice(0, LIM.indicators); IND.note = 'Default restored · not saved'; renderInd() } break;
      case 'ind-save': void indSave(); break;
    }
  });
  document.addEventListener('keydown', e => {
    const tg = e.target as HTMLElement;
    // Alt+A opens Add stocks, as Alt+S runs the Screener (screener/src/screen-gate.ts): left alone inside a text field
    // (on some keyboards Alt+A types a character), while a dialog or menu is open, and before the lists are read
    if (M.isAltA(e) && !M.typingTarget(tg) && !DLG && !MENU && LISTS.length && L()) { e.preventDefault(); openAdd(); return }
    if ((e.key === 'Enter' || e.key === ' ') && tg.matches?.('th[data-act="tsort"]') && !DLG) { e.preventDefault(); tg.click(); return }
    if (e.key === 'Escape') {
      if (MENU) { const f = MENU._for; closeMenuOf(); f?.focus(); e.preventDefault(); return }
      if (DLG) { closeDialog(); e.preventDefault(); return }
      hideTip();
    }
    if (MENU && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      const it = [...MENU.querySelectorAll<HTMLElement>('.menu-item:not([disabled])')], i = it.indexOf(document.activeElement as HTMLElement);
      if (it.length) it[(i + (e.key === 'ArrowDown' ? 1 : -1) + it.length) % it.length].focus();
      e.preventDefault(); return;
    }
    if (DLG) {
      if (e.key === 'Tab') {
        const f = [...DLG.bd.querySelectorAll<HTMLElement>('button:not([disabled]),input,select,[tabindex="0"]')].filter(x => x.offsetParent);
        if (!f.length) return;
        const i = f.indexOf(document.activeElement as HTMLElement);
        if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus() } else if (!e.shiftKey && i === f.length - 1) { e.preventDefault(); f[0].focus() }
      } else DLG.onKey?.(e);
    }
  });
  /* the Radar badge's popover: each screen the stock met, with the Radar's date */
  let TIP: (HTMLDivElement & { _for?: HTMLElement }) | null = null;
  function hideTip() { if (TIP) { TIP.remove(); TIP = null } }
  function showTip(b: HTMLElement) {
    if (TIP && TIP._for === b) return;
    hideTip();
    const s = BY.get(b.dataset.t || ''); if (!s || !s.rd.length) return;
    b.removeAttribute('title');
    const d = document.createElement('div') as HTMLDivElement & { _for?: HTMLElement };
    d.className = 'rtip'; d.setAttribute('role', 'tooltip');
    d.innerHTML = `<div class="rh">${ic('radar')}<b>${esc(s.t)}</b> met ${s.rd.length} Radar screen${s.rd.length > 1 ? 's' : ''}<span class="muted">${RD}</span></div>` + s.rd.map(f => `<div class="rr"><span class="rid">${esc(f)}</span>${esc(RN[f] || '')}</div>`).join('') + '<div class="rf">Click to open Radar</div>';
    document.body.appendChild(d);
    const r = b.getBoundingClientRect(), w = d.offsetWidth, h = d.offsetHeight;
    let y = r.bottom + 6; if (y + h > innerHeight - 8) y = r.top - h - 6;
    d.style.left = Math.min(Math.max(8, r.left), innerWidth - w - 8) + 'px'; d.style.top = Math.max(8, y) + 'px'; d._for = b; TIP = d;
  }
  document.addEventListener('mouseover', e => {
    const b = (e.target as HTMLElement).closest?.('.pill.radar') as HTMLElement | null;
    if (!b) { if (TIP) hideTip(); return }
    showTip(b);
  });
  document.addEventListener('focusin', e => { const b = (e.target as HTMLElement).closest?.('.pill.radar') as HTMLElement | null; if (b) showTip(b); else hideTip() });
  window.addEventListener('resize', () => { closeMenuOf(); hideTip() });
  window.addEventListener('scroll', () => { closeMenuOf(); hideTip() }, true);

  /* ---------- boot ---------- */
  async function readFile(again = true): Promise<StocksFile> {
    const e = index.files[FILE];
    try {
      if (!e) throw new WatchlistError('WATCHLIST_FILE_NOT_PUBLISHED', 'The watchlist figures are not published yet. They come with the next daily publication; try again later.', 404);
      return await api.file<StocksFile>(FILE, e.sha256);
    } catch (err) {
      // a newer publication replaced the file (409) or it is not in this index (404): read the index again once
      if (again && err instanceof WatchlistError && (err.status === 409 || err.status === 404) && e) { index = await api.index(); return readFile(false) }
      throw err;
    }
  }
  /** Phase 3d: the Radar's file when the index lists it (only with radar.view); any refusal or failure leaves the page
      without Radar badges, never without its figures */
  async function readRadar(): Promise<RadarFile | null> {
    const e = index.files[RADAR_FILE];
    if (!e) return null;
    try { return await api.file<RadarFile>(RADAR_FILE, e.sha256) } catch { return null }
  }
  /** the figures; when they cannot be read the lists are still shown, with "—" and the reason (M466 (a)) */
  async function loadFile() {
    try {
      index = await api.index(); const base = await readFile();
      const merged = M.withRadar(base, await readRadar()); F = merged.file; HAS_RADAR = merged.radar; FILE_ERR = null;
    }
    catch (e) { F = M.emptyFile(); HAS_RADAR = false; FILE_ERR = msg(e, 'The figures could not be read. Try again in a minute.') }
    CAT = M.catalog(F); BY = M.stocks(F); UL = [...BY.values()]; RN = M.radarNames(F);
    PD = M.dateLabel(F.prices_through); BD = M.dateLabel(F.broker_through); RD = M.dateLabel(F.radar_date);
  }
  async function boot() {
    PAGE.setAttribute('aria-busy', 'true');
    try {
      const lp = api.lists();
      await loadFile();
      const got = await lp;
      LIM = M.limitsOf(got.limits); LISTS = got.lists;
      if (!LISTS.length) {                                   // a first visit: one list to start from
        try { LISTS = [await api.create({ name: FIRST_LIST })] }
        catch (e) { if (e instanceof WatchlistError && e.code === 'NAME_TAKEN') LISTS = (await api.lists()).lists; else throw e }
      }
      if (!L()) { st.active = LISTS[0].id; persist() }
      render();
      void api.logos().then(m => { LOGOS = m || {}; if (!Object.keys(LOGOS).length) return; if (!DLG && !MENU) render(); else renderAdd() });
    } catch (e) {
      renderFailure(msg(e, 'The watchlist could not be read. Try again in a minute.'));
    }
  }
  return { boot, rerender: () => { if (F && LISTS.length) render() } };
}
