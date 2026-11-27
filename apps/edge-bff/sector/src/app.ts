/* EXEC-SECTOR-ANALYSIS S4: the Sector Analysis page. It reads the sector files of edge-bff (src/api.ts: the index, then
   sector-meta, sector-series and the chosen date's sector-day; a sector's sector-stocks-<index> only when its stock lines
   or its stocks' beta are opened) and draws the five tabs of the user's final prototype with them. The viewer's choices
   live in the address (as the Overview's); nothing is kept in the browser's storage. */
import { FILE, SectorError, cached } from './api.ts';
import { lockOnly } from '../../shared/example-view.ts';
import * as M from './model.ts';
import { calc, cloneState, DEFAULT_STATE, TABS, type Card, type Ctx, type State, type StocksState, type TabKey } from './ctx.ts';
import { $, $$, DOT, esc, escTop, initTips, scrollCues, tipHide, closeRange } from './ui.ts';
import { closeWindow, openWindow, windowOpen } from './windows.ts';
import { dayDates as pickable, open, stocksFile } from './loader.ts';
import { hxCard, mkCard, mmCard, rcCard } from './cards/ov.ts';
import { rsA, rsB, rsD, rsL, rsW } from './cards/rs.ts';
import { rotA, rotB, rotC, rotD } from './cards/rot.ts';
import { pmM, pmR, pmS, pmT } from './cards/pm.ts';
import { brA, brD, brH, brN, brT } from './cards/br.ts';
import type { Day, Meta, SectorApi, SectorIndex, Series, StocksFile } from './types.ts';
import { W } from './words.ts';

export const CARDS: Card[] = [rcCard, mmCard, hxCard, mkCard, rsD, rsB, rsL, rsW, rsA, rotA, rotD, rotB, rotC, pmM, pmR, pmT, pmS, brH, brT, brA, brN, brD];
/* the grid of each tab (final/click_inventory.md: the prototype's layout at 1440 px; one column on a phone, D01) */
const LAYOUT: Record<TabKey, string> = {
  ov: '<div class="g-ov"><div data-slot="rcCard"></div><div data-slot="mmCard"></div><div data-slot="hxCard"></div><div data-slot="mkCard"></div></div>',
  rs: '<div class="g-rs"><div data-slot="rsD"></div><div data-slot="rsB"></div><div data-slot="rsL"></div><div data-slot="rsW"></div><div data-slot="rsA"></div></div>',
  rot: '<div class="g-rot"><div class="rotL"><div data-slot="rotA"></div><div data-slot="rotD"></div></div><div data-slot="rotB"></div><div data-slot="rotC"></div></div>',
  pm: '<div class="g-pm"><div data-slot="pmM"></div><div data-slot="pmR"></div><div data-slot="pmT"></div><div data-slot="pmS"></div></div>',
  br: '<div class="g-br"><div data-slot="brH"></div><div data-slot="brT"></div><div data-slot="brA"></div><div data-slot="brN"></div><div data-slot="brD"></div></div>',
};
/* decision J (UD66): in the example every control but the five tabs asks for the shell's sign-in or upgrade box, as a click
   on a locked control of the Overview's example does; hover and scrolling stay */
const CONTROL = 'button, select, input, a[href], [role=button], [role=tab], [data-n], [data-t], [data-a], [data-k], [data-tg], [data-term], .bz, .ihc, .fwx';
export const exampleLocked = (el: Element) => !!el.closest(CONTROL) && !el.closest('#tabs [role=tab]') && !el.closest('.dchip');

type PageCtx = Ctx & { alive: boolean };
export function start(api: SectorApi, view: HTMLElement, opts: { example?: boolean } = {}) {
  const files = cached(api), example = !!opts.example;
  let index: SectorIndex, meta: Meta, series: Series, day: Day, D: M.Data;
  const S: State = cloneState(DEFAULT_STATE);
  if (!example) readHash(S);
  if (example) lockOnly({ source: 'sector', name: W.page.title, locked: exampleLocked });

  let toastT = 0;
  const toast = (m: string) => { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toastT); toastT = window.setTimeout(() => (t.hidden = true), 3200) };
  const persist = () => { if (!example) history.replaceState(null, '', '#' + encodeURIComponent(JSON.stringify(diffState(S)))) };

  /* ---------- files ---------- */
  const get = async <T>(name: string, again = true): Promise<T> => {
    const e = index.files[name];
    try {
      if (!e) throw new SectorError('SECTOR_FILE_NOT_PUBLISHED', W.err.notPublished, 404);
      return await files.file<T>(name, e.sha256);
    } catch (err) {
      // a newer publication replaced the file (409) or dropped the date (404): read the index again once, as the Overview
      if (again && err instanceof SectorError && (err.status === 409 || err.status === 404)) { index = await files.index(); return get<T>(name, false) }
      throw err;
    }
  };
  const stocksState = new Map<string, StocksState>(), waiting = new Set<PageCtx>();
  function stocks(sector: string, who: PageCtx): StocksState {
    const name = stocksFile(meta, sector), e = name ? index.files[name] : null;
    if (!name || !e) return { state: 'missing' };
    const k = `${name}@${e.sha256}`, have = stocksState.get(k);
    if (have) { if (have.state === 'loading') waiting.add(who); return have }
    stocksState.set(k, { state: 'loading' }); waiting.add(who);
    get<StocksFile>(name).then(f => stocksState.set(k, { state: 'ready', file: f }), () => stocksState.set(k, { state: 'error' }))
      .finally(() => { const w = [...waiting]; waiting.clear(); w.forEach(x => x.alive && x.redraw()) });
    return { state: 'loading' };
  }

  /* ---------- the Terminal (decision G, UD67 1A: the locked sector's index, else the market; a stock opens that stock) ---------- */
  function terminal(t: string) {
    try { localStorage.setItem('ml.symbol', t) } catch { /* storage off: the Terminal opens on its own symbol */ }
    try { parent.postMessage({ type: 'edge-nav', route: 'terminal' }, location.origin) } catch { /* not framed */ }
    if (parent === window) toast(W.term.set(t));
  }
  const headTarget = () => (S.pin && D.info[S.pin]?.index ? D.info[S.pin].index : D.market);

  /* ---------- contexts: the page's, and one per floating window ---------- */
  function makeCtx(St: State, win: boolean, redraw: () => void): PageCtx {
    const c: PageCtx = {
      get D() { return D }, S: St, win, example, alive: true,
      lock(name, toggle = true) { St.pin = toggle && name === St.pin ? null : name; c.redraw() },
      redraw, terminal,
      stocks: (sector: string) => stocks(sector, c),
    } as PageCtx;
    return c;
  }
  const page = makeCtx(S, false, () => redraw());

  /** draws a card into its element, keeping the scroll of its lists and the keyboard focus (a choice redraws the card).
      A list keeps its scroll only while it shows the same columns (its data-scroll-key; check 1 OR-3: a Custom range of
      25 weeks opened scrolled to the oldest week); one that was at its right end stays at the end. */
  function renderCard(card: Card, el: HTMLElement, c: Ctx) {
    el.classList.add('card', 'tc', ...card.cls.split(' ')); el.dataset.card = card.id;
    const scroll = $$('[data-scroll]', el).map(x => ({ t: x.scrollTop, l: x.scrollLeft, k: x.dataset.scrollKey || '', end: x.scrollWidth > x.clientWidth + 1 && x.scrollLeft + x.clientWidth >= x.scrollWidth - 1 }));
    const a = document.activeElement as HTMLElement | null, focus = a && el.contains(a) ? focusKey(a) : null;
    try { card.render(el, c) } catch (e) { console.error(e); el.innerHTML = `<div class="cv-empty pad">${esc(W.err.card)}</div>` }
    $$('[data-scroll]', el).forEach((x, i) => {
      const s = scroll[i]; if (!s || s.k !== (x.dataset.scrollKey || '')) return;
      x.scrollTop = s.t; x.scrollLeft = s.l; x.dataset.kept = '1'; if (s.end) x.dataset.atEnd = '1';
    });
    if (focus) { const f = el.querySelector(focus) as HTMLElement | null; f?.focus({ preventScroll: true }) }
    watchSize(card, el, c);
    scrollCues(el);
    requestAnimationFrame(() => scrollCues(el));
  }
  /* a chart is drawn for the size of its box; when the box changes size afterwards (the header wraps to two rows once the
     font arrives, a scrollbar appears) the card is drawn again (check 1 BD-1: the svg kept its first height and its axis
     printed over the legend; RP-5) */
  const sizeRO = new WeakMap<HTMLElement, ResizeObserver>(), redrawn = new WeakMap<HTMLElement, number[]>();
  function watchSize(card: Card, el: HTMLElement, c: Ctx) {
    sizeRO.get(el)?.disconnect();
    const seen = new WeakMap<Element, string>(), boxes = $$('[data-chart],[data-map],[data-strip]', el);
    let t = 0;
    const again = () => {
      const now = performance.now(), log = (redrawn.get(el) || []).filter(x => now - x < 2000);
      if (log.length >= 3) return;                    // a card that keeps changing its own size stays as drawn
      log.push(now); redrawn.set(el, log);
      clearTimeout(t);
      t = window.setTimeout(() => { if ((c as PageCtx).alive === false || !el.isConnected) return; renderCard(card, el, c) }, 60);
    };
    const ro = new ResizeObserver(es => {
      let changed = false;
      for (const e of es) {
        const k = `${Math.round(e.contentRect.width)}x${Math.round(e.contentRect.height)}`, was = seen.get(e.target);
        seen.set(e.target, k); if (was != null && was !== k) changed = true;
      }
      if (changed) again();
    });
    boxes.forEach(b => ro.observe(b));
    sizeRO.set(el, ro);
    // a chart drawn before its box took its final size overflows the box: it is drawn again
    requestAnimationFrame(() => requestAnimationFrame(() => {
      if (!el.isConnected) return;
      if (boxes.some(b => { const s = b.querySelector(':scope > svg'); return !!s && s.getBoundingClientRect().bottom > b.getBoundingClientRect().bottom + 1 })) again();
    }));
  }
  const slots = new Map<string, HTMLElement>();
  function redraw() {
    if (!D) return;
    tipHide();
    renderHead();
    const t = S.tab;
    $$('.tabp', view).forEach(p => (p.hidden = p.dataset.tab !== t));
    $('#kpis').hidden = t !== 'ov';
    if (t === 'ov') kpis();
    for (const card of CARDS) if (card.tab === t) { const el = slots.get(card.id); if (el) renderCard(card, el, page) }
    persist();
  }
  /* ---------- the KPI row (logic.js L67-77) ---------- */
  function kpis() {
    const K = calc(D), w = D.P('1W'), E = D.E, N = D.names.length;
    const ex = D.names.map(n => ({ n, v: K.rr(n, w) })).filter(x => x.v != null) as { n: string; v: number }[];
    const beat = ex.filter(x => x.v > 0).length, best = [...ex].sort((a, b) => b.v - a.v)[0];
    const r0 = K.rankAt(w, E - w), r1 = K.rankAt(w, E), gain = D.names.map(n => ({ n, d: r0[n] - r1[n] })).sort((a, b) => b.d - a.d)[0];
    const imp = D.names.filter(n => K.q[n][E] === 'Improving').length, ih = D.IH, ihd = M.minus(ih[E], ih[E - w]), ihr = M.ret(ih, E, w);
    const sp = ih.slice(Math.max(0, E - 29), E + 1).filter((x): x is number => x != null), mn = Math.min(...sp), mx = Math.max(...sp);
    const spark = sp.length > 1 ? `<svg class="sp" width="64" height="26" aria-hidden="true"><polyline points="${sp.map((x, i) => `${((i * 64) / (sp.length - 1)).toFixed(1)},${(24 - ((x - mn) / (mx - mn || 1)) * 22).toFixed(1)}`).join(' ')}" fill="none" stroke="${(ihd ?? 0) >= 0 ? 'var(--up)' : 'var(--down)'}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/></svg>` : '';
    const tile = (lt: string, tf: string, sub: string, v: string, s: string, extra = '') => `<div class="card ktile"><div class="lb"><span>${esc(lt)} <span class="tf">${esc(tf)}</span></span></div><div class="ksub">${esc(sub)}</div><div><div class="v">${v}</div><div class="s">${s}</div></div>${extra}</div>`;
    $('#kpis').innerHTML =
      tile(D.market, '5D', W.kpi.ihSub, M.level(ih[E]), `<b class="${M.cls(ihd)}">${ihd == null ? '—' : M.sign(ihd) + M.level(Math.abs(ihd))}${DOT}${M.pct(ihr)}</b>`, spark)
      + tile(W.kpi.beat(D.market), '5D', W.kpi.beatSub, `${beat} / ${N}`, `<span class="adbar" style="width:120px"><i style="flex:${beat};background:var(--up)"></i><i style="flex:${N - beat};background:var(--gray-300)"></i></span>`)
      + tile(W.kpi.best, '5D', W.kpi.bestSub(D.market), best ? esc(D.short(best.n)) : '—', best ? `<b class="${M.cls(best.v)}">${M.pp(best.v)}</b>${DOT}${esc(W.kpi.rank1(N))}` : '')
      + tile(W.kpi.imp, W.kpi.impTf, W.kpi.impSub(D.market), `${imp} / ${N}`, gain && gain.d > 0 ? `${esc(W.kpi.gain)} <b>${esc(D.short(gain.n))}</b> <span class="up">▲${gain.d}</span>` : esc(W.kpi.noGain));
  }
  /* ---------- header: the data dates, the date picker, Open in Terminal, the tabs ---------- */
  const dayDates = () => pickable(meta, index);
  function renderHead() {
    const bt = meta.breadth_through;
    $('#pills').innerHTML = `<span class="pill pos" title="${esc(W.head.pricesTip)}"><span class="dot"></span>${esc(W.head.prices(M.dateIn(day.date, meta.prices_through, true)))}</span>`
      + (bt && bt < day.date ? `<span class="pill warn" title="${esc(W.head.breadthTip)}"><span class="dot"></span>${esc(W.head.breadth(M.dateLabel(bt, true)))}</span>` : '');
    $('#dlab').textContent = M.dateIn(day.date, meta.prices_through, true) + DOT + W.head.close;
    const t = headTarget();
    $('#termbtn').title = W.term.headTip(t);
    $('#termbtn').setAttribute('aria-label', W.term.headTip(t));
    $('#tabmeta').innerHTML = esc(W.head.meta(D.names.length)) + ` <b>${esc(D.market)}</b>`;
    $$('#tabs [role=tab]').forEach(b => { const on = b.dataset.t === S.tab; b.classList.toggle('on', on); b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1 });
  }
  function dateMenu(open: boolean) {
    const pop = $('#datepop'), btn = $('#datebtn');
    pop.hidden = !open; btn.setAttribute('aria-expanded', String(open));
    if (!open) return;
    const ds = dayDates().slice().reverse();
    pop.innerHTML = `<div class="menu-title">${esc(W.head.asOf)}</div>` + ds.map((d, i) => `<button class="menu-item${d === day.date ? ' on' : ''}" role="menuitemradio" aria-checked="${d === day.date}" data-d="${d}" type="button"><span class="l"><svg class="ic ic-sm ck">${d === day.date ? '<use href="#i-check"/>' : ''}</svg>${esc(M.dateLabel(d, true, true))}</span><span class="n">${esc(i === 0 ? W.head.latest : W.head.close)}</span></button>`).join('');
    const a = btn.getBoundingClientRect(), G = 8;
    pop.style.left = pop.style.right = '';
    if (a.right - pop.offsetWidth < G) { pop.style.right = 'auto'; pop.style.left = '0' }
    pop.style.maxHeight = Math.max(160, innerHeight - a.bottom - 6 - G) + 'px';
    ($('.menu-item.on', pop) as HTMLElement | null)?.focus();
  }
  /* the last pick wins: an older date's file that arrives later is dropped (check 1 BD-5) */
  const latestPick = M.lastWins();
  async function pickDate(d: string) {
    const btn = $('#datebtn'); btn.setAttribute('aria-busy', 'true');
    const r = await latestPick(d === day.date ? Promise.resolve(day) : get<Day>(FILE.day(d)));
    if (r.stale) return;
    btn.removeAttribute('aria-busy');
    if (r.error) { toast(r.error instanceof SectorError ? r.error.message : W.err.date); return }
    if (r.value === day) return;
    day = r.value as Day; D = M.makeData(meta, series, day); S.rotK = null; S.rqT = null;
    const ds = dayDates(); S.date = day.date === ds[ds.length - 1] ? null : day.date;   // kept in the address (check 1 BD-10)
    closeWindow(); redraw();
  }
  function showTab(t: TabKey, focus = false) {
    if (t === S.tab) return;
    S.tab = t; closeWindow(); closeRange(); redraw();
    const tb = $(`#tabs [data-t="${t}"]`) as HTMLElement;
    if (focus) tb.focus();
    tb.scrollIntoView({ block: 'nearest', inline: 'nearest' });                // a phone's tab bar scrolls (check 1 MX-3)
    // the tab bar stays at the top while the page scrolls: a new tab starts right under it
    const bar = $('.bar1'), pn = t === 'ov' ? $('#kpis') : $(`.tabp[data-tab="${t}"]`);
    const top = pn.getBoundingClientRect().top, bb = bar.getBoundingClientRect().bottom;
    if (top < bb + 8) view.scrollBy(0, top - bb - 12);
  }

  /* ---------- events, bound once ---------- */
  function bind() {
    $('#tabs').innerHTML = TABS.map(t => `<button role="tab" type="button" data-t="${t}" aria-selected="${t === S.tab}" aria-controls="tab-${t}" id="tabbtn-${t}" class="${t === S.tab ? 'on' : ''}">${esc(W.tabs[t])}</button>`).join('');
    $$('.tabp', view).forEach(p => { const t = p.dataset.tab as TabKey; p.setAttribute('role', 'tabpanel'); p.setAttribute('aria-labelledby', `tabbtn-${t}`); p.innerHTML = LAYOUT[t]; $$('[data-slot]', p).forEach(s => slots.set(s.dataset.slot as string, s)) });
    $('#tabs').addEventListener('click', e => { const b = (e.target as Element).closest('[role=tab]') as HTMLElement | null; if (b) showTab(b.dataset.t as TabKey) });
    $('#tabs').addEventListener('keydown', e => {                      // arrow keys move between the tabs
      const i = TABS.indexOf(S.tab), to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1 }[e.key];
      if (to == null) return; e.preventDefault(); showTab(TABS[(to + TABS.length) % TABS.length], true);
    });
    $('#datebtn').addEventListener('click', e => { e.stopPropagation(); dateMenu($('#datepop').hidden) });
    $('#datepop').addEventListener('click', e => { const b = (e.target as Element).closest('.menu-item') as HTMLElement | null; if (!b) return; dateMenu(false); void pickDate(b.dataset.d as string) });
    // the menu pattern: the arrow keys, Home and End move between the dates (check 1 BD-9, MX-6)
    $('#datepop').addEventListener('keydown', e => {
      const items = $$('.menu-item', $('#datepop')), i = items.indexOf(document.activeElement as HTMLElement), to = M.menuStep(items.length, Math.max(0, i), e.key);
      if (to == null) return; e.preventDefault(); items[i < 0 && e.key === 'ArrowDown' ? 0 : to].focus();
    });
    $('#termbtn').addEventListener('click', () => terminal(headTarget()));
    document.addEventListener('click', e => { if (!$('#datepop').hidden && !$('.dd').contains(e.target as Node)) dateMenu(false) });
    // Esc closes the newest popover a card opened before anything else (a window registers its own key handler later)
    document.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (escTop()) { e.preventDefault(); e.stopImmediatePropagation(); return }
      if (!$('#datepop').hidden) { dateMenu(false); $('#datebtn').focus() }
    }, true);
    // the expand button of a card opens it as a floating window (any card on the page)
    view.addEventListener('click', e => {
      const b = (e.target as Element).closest('.fwx') as HTMLElement | null; if (!b || windowOpen()) return;
      const card = CARDS.find(x => x.id === b.dataset.fw); if (!card) return;
      e.stopPropagation(); tipHide();
      openWindow(card, page, { ctx: makeCtx, render: renderCard }, b);
    });
    // a tap in the shell around this frame closes the page's popovers (as the Overview)
    if (parent !== window) {
      try {
        const close = () => { dateMenu(false); closeRange(); tipHide() };
        parent.document.addEventListener('pointerdown', close);
        addEventListener('pagehide', () => { try { parent.document.removeEventListener('pointerdown', close) } catch { /* the shell is gone */ } });
      } catch { /* another origin */ }
    }
    initTips();
    scrollCues($('.bar1'));
    // the cards follow their box (every width): drawn again when the page's width changes
    let w0 = view.clientWidth, rt = 0;
    new ResizeObserver(() => { const w = view.clientWidth; if (Math.abs(w - w0) < 2) return; w0 = w; clearTimeout(rt); rt = window.setTimeout(() => { redraw(); scrollCues($('.bar1')) }, 120) }).observe(view);
  }

  function renderError(e: unknown) {
    const m = e instanceof SectorError ? e.message : W.err.boot;
    $('#body').hidden = true;
    const boot = $('#boot'); boot.hidden = false;
    boot.innerHTML = `<span class="err" aria-hidden="true">!</span><span>${esc(m)}</span><button class="btn sm" type="button" data-act="retry">${esc(W.err.retry)}</button>`;
    $('#dlab').textContent = W.head.none;
    ($('[data-act=retry]', boot) as HTMLElement).onclick = () => void boot_();
  }
  let bound = false;
  /* the header's date and Terminal buttons act on the data: off until it is in, and while only an error shows (check 1 MX-7) */
  const headLive = (on: boolean) => ['#datebtn', '#termbtn'].forEach(s => { ($(s) as HTMLButtonElement).disabled = !on });
  async function boot_() {
    const boot = $('#boot');
    boot.hidden = false; $('#body').hidden = true; headLive(false);
    boot.innerHTML = `<span class="ml-loading" role="status"><span class="ml-spin" aria-hidden="true"></span>${esc(W.page.loading)}</span>`;
    $('#ppurpose').textContent = W.page.purpose;
    try {
      const o = await open(files, S.date || undefined);
      index = o.index; meta = o.meta; series = o.series;
      if (!o.day) { boot.innerHTML = `<span>${esc(W.err.noDate)}</span>`; $('#dlab').textContent = W.head.none; return }
      day = o.day;
    } catch (e) { renderError(e); return }
    D = M.makeData(meta, series, day);
    { const ds = dayDates(); S.date = day.date === ds[ds.length - 1] ? null : day.date }   // a date no longer listed: the newest
    if (S.pin && !D.names.includes(S.pin)) S.pin = null;
    boot.hidden = true; $('#body').hidden = false; headLive(true);
    if (!bound) { bind(); bound = true }
    redraw();
    document.body.dataset.ready = '1';
  }
  return { boot: boot_, rerender: () => (D ? redraw() : undefined), state: S };
}

/* ---------- the address keeps the viewer's choices (the Overview's way); a value of the wrong kind is dropped ---------- */
const NOT_KEPT = new Set(['dS', 'dQ']);
function diffState(S: State) {
  const o: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(S)) if (!NOT_KEPT.has(k) && JSON.stringify(v) !== JSON.stringify((DEFAULT_STATE as any)[k])) o[k] = v;
  return o;
}
export function readHash(S: State, hash = typeof location === 'undefined' ? '' : location.hash) {
  let o: any = null;
  try { o = JSON.parse(decodeURIComponent(hash.replace(/^#/, '')) || 'null') } catch { o = null }
  if (!o || typeof o !== 'object') return;
  for (const [k, v] of Object.entries(o)) {
    if (!(k in DEFAULT_STATE) || NOT_KEPT.has(k)) continue;
    const d = (DEFAULT_STATE as any)[k];
    const same = d === null ? v === null || typeof v === 'string' || (typeof v === 'object' && v !== null) : Array.isArray(d) ? Array.isArray(v) : typeof v === typeof d;
    if (same) (S as any)[k] = v;
  }
  if (!TABS.includes(S.tab)) S.tab = 'ov';
}
/** a selector that finds the same control after the card is drawn again */
function focusKey(a: HTMLElement): string | null {
  const seg = (a.closest('[data-seg]') as HTMLElement | null)?.dataset.seg;
  if (seg && a.dataset.v != null) return `[data-seg="${seg}"] [data-v="${a.dataset.v}"]`;
  for (const k of ['k', 'n', 't', 'x', 'tg', 'sel', 'ab', 'i']) { const v = a.dataset[k]; if (v != null) return `[data-${k}="${CSS.escape(v)}"]` }
  if (a.dataset.a != null && a.dataset.b != null) return `[data-a="${CSS.escape(a.dataset.a)}"][data-b="${CSS.escape(a.dataset.b)}"]`;
  return null;
}
