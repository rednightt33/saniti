/* The page: boot() runs the load sequence of report PAGE LOAD SEQUENCE 6c.4, and refresh() is the prototype's refresh
   orchestration (which cards re-render after an edit), with the table brought to the definition by run.ts.
   S1  the frame's static markup is the first paint (index.html: the layout with a ring in each data area,
       data-boot="skeleton" on the page root);
   S2  boot() reads scr.* and the boot pointer and sends at once: session, catalog and universe (If-None-Match from
       the pointer), saved screens, My metrics, watchlist;
   S3  after the session answers (an authenticated answer), the cached catalog, universe and last result are drawn from
       the browser's file cache when the pointer names them for this login; the data line says "Updating…";
   S4  304 confirms them, 200 replaces them (and stores the new bytes when they hash to the ETag);
   S5  first results: an empty screen from the universe rows (no run); a remembered screen from its cached result when
       its versions are confirmed, else POST run;
   S6  saved screens and the watchlist fill in when they answer, never blocking S5;
   S7  preview, Stock vs IHSG, counts and CSV wait until asked; S8 edits are debounced (run.ts).
   ?perf=1 shows the stage marks (the Terminal's perf.ts; performance marks 'terminal:<stage>'). */
import type { CatalogResponse, RunResponse, UniverseResponse, Versions } from './core/contract.ts';
import type { FileCache } from '../../terminal/src/data/rack.ts';
import { fileCache } from '../../terminal/src/data/rack.ts';
import { mark } from '../../terminal/src/app/perf.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { ApiFailure, type Conditional, type ScreenerApi } from './api/types.ts';
import { BootCache, sameVersions } from './api/boot-cache.ts';
import { esc } from './format.ts';
import { IC, ico } from './icons.ts';
import { canonical, ctx, definitionOf, freshUniverse, presetOf, S, stateOfDefinition, ui } from './state.ts';
import { entriesOf } from './entries.ts';
import { applyTheme, followTheme, lastScreen, panelPrefs, saveLast, savePanel } from './storage.ts';
import { dataLine, T } from './texts.ts';
import { closeDialog, dialogOpen, openMenu, openSave, toast } from './dialogs.ts';
import { closePop, onUniverseClick, onUniverseField, openDrawer, placePop, renderUniverse, updateUniverseLight, uCountTxt } from './universe-ui.ts';
import { fitPresets, loadDefinition, onPresetClick, openSource, renderPresets } from './presets-ui.ts';
import { hideSuggest, onAdderInput, onAdderKey, onBuilderClick, onBuilderField, renderConds, updateCondsLight, drawSuggest, bSum } from './builder.ts';
import { exportCsv, onResultsChange, onResultsClick, onResultsKey, renderResults, sizePreview } from './results.ts';
import { bindPreview, pickStock, renderDetails, resetPreview, togglePreview } from './preview.ts';
import { cancelRun, resultOf, runHooks, schedule } from './run.ts';

const $ = (id: string) => document.getElementById(id)!;
let boot!: BootCache;
const tags = { catalog:null as string | null, universe:null as string | null };
let confirmed = false;

/* ---- page head (the prototype's renderHeader) ------------------------------------------------------------- */
export function renderHeader() {
  const p = S.source?.kind === 'preset' ? presetOf(S.source.id) : null;
  const cat = ctx.catalog, d = cat?.data;
  const data = !cat ? `<span class="sbox">${spin(T.loadingData)}</span>`
    : `<span>· ${esc(dataLine(ctx.universe?.rows.length ?? ctx.R?.listed ?? 0, d!.evaluation_date, d!.published_at))}</span>${!confirmed ? `<span class="sbox">${spin(T.updating)}</span>` : ''}${d!.refresh === 'failed_keeping_previous' ? `<span class="pill t-warning" title="The latest publication failed its checks; the previous one is kept.">previous publication</span>` : (d!.refresh as string) === 'refreshing' ? `<span class="pill t-info">new data loading</span>` : ''}`;
  $('pageHead').innerHTML = `<div><span class="eyebrow">Market intelligence</span><h1>Market Screener</h1>
    <p>Screen<input class="title-in" id="titleIn" value="${esc(S.name)}" size="${Math.max(8, S.name.length)}" maxlength="120" aria-label="Screen name"><span class="pill cat ${p ? 'cat-' + esc(p.category) : 'cat-Saved'} srcpill">${p ? 'Preset · ' + esc(p.category) : S.source ? 'My screen' : 'Custom screen'}${S.dirty ? ' · edited' : ''}</span><span id="dataLine" style="display:contents">${data}</span></p></div>`;
  $('pageActs').innerHTML = `<button class="btn" data-hd="reset">${ico(IC.reset, 's')}Reset</button><button class="btn" data-hd="save" ${ctx.catalog ? '' : 'disabled'}>${ico(IC.save, 's')}${S.source?.kind === 'saved' && S.dirty ? 'Save changes' : 'Save screen'}</button><button class="btn primary" data-hd="export" data-menu aria-haspopup="menu">${ico(IC.export, 's')}Export</button>`;
}
function onHeadClick(e: Event) {
  const b = (e.target as HTMLElement).closest('[data-hd]') as HTMLElement | null; if (!b) return;
  const k = b.dataset.hd;
  if (k === 'reset') { S.q = ''; ($('tq') as HTMLInputElement).value = ''; cancelRun(); loadDefinition({ universe:definitionOf({ universe:freshUniverse(), cards:[], logic:'all', atLeast:2 }).universe, conditions:[], logic:'all' }, 'Untitled screen', null); toast('Screen reset — full universe, no conditions'); return }
  if (k === 'save') { openSave(); return }
  if (k === 'export') openMenu(b, [
    ['Export results (CSV)', IC.dl, () => exportCsv()],
    ['Send to Backtest', IC.send, () => {}, T.sendPhase],
    null,
    ['Duplicate as new screen', IC.dup, () => { S.source = null; S.name += ' (copy)'; S.dirty = true; renderHeader(); renderPresets(); remember(); toast('Working on a copy — Save screen to keep it') }],
    ['Method & sources', IC.book, () => { S.dtab = 'method'; togglePreview(true); $('preview').scrollIntoView({ behavior:'smooth', block:'nearest' }) }],
  ]);
}

export function markDirty() { if (!S.dirty) { S.dirty = true; renderHeader() } }

/* ---- refresh orchestration (the prototype's refresh) ------------------------------------------------------- */
type Level = 'all' | 'universe' | 'universe-light' | 'conds' | 'conds-light' | 'results';
let inRefresh = false;
export function refresh(level: Level) {
  if (inRefresh) return; inRefresh = true;
  try {
    if (level !== 'results') schedule();      // the table follows the definition (run.ts); calls back with 'results'
    if (level === 'all' || level === 'universe') { renderUniverse(); renderConds() }
    else if (level === 'universe-light') { updateUniverseLight(); updateCondsLight() }
    else if (level === 'conds') renderConds();
    else if (level === 'conds-light') updateCondsLight();
    else if (level === 'results') { const u = document.getElementById('uCount'); if (u) u.innerHTML = uCountTxt(); document.querySelectorAll('[data-ucount]').forEach(el => { el.innerHTML = uCountTxt() }); updateCondsLight(); const s = document.getElementById('bSum'); if (s) s.textContent = bSum() }
    if (level === 'conds' || level === 'conds-light') { const u = document.getElementById('uCount'); if (u) u.innerHTML = uCountTxt() }
    renderHeader(); renderResults();
    if (S.preview) renderDetails();
    if (level !== 'results') remember();
    if (ctx.R && ctx.catalog && ctx.bootState !== 'results' && !ctx.running) { ctx.bootState = 'results'; $('app').dataset.boot = 'results' }
  } finally { inRefresh = false }
}
/** the last open screen, for the next visit (scr.last) */
let rememberT: ReturnType<typeof setTimeout> | undefined;
function remember() {
  clearTimeout(rememberT);
  rememberT = setTimeout(() => {
    if (!ctx.catalog) return;
    saveLast({ name:S.name, definition:definitionOf(), ...(S.source?.kind === 'saved' ? { item_id:S.source.item_id } : S.source?.kind === 'preset' ? { preset:S.source.id } : {}), sort:S.sort, near:S.nearMiss });
  }, 400);
}

/* ---- catalog and universe ---------------------------------------------------------------------------------- */
function useCatalog(c: CatalogResponse) {
  const changed = !ctx.catalog || !sameVersions(ctx.catalog.versions, c.versions);
  ctx.catalog = c; ctx.entries = entriesOf(c); ctx.byKey = new Map(ctx.entries.map(e => [e.key, e]));
  if (changed) { ctx.counts.clear(); if (ctx.R?.run && !sameVersions(ctx.R.run.versions, c.versions)) { ctx.R = null; resetPreview() } }
  mark('catalog');
}
function useUniverse(u: UniverseResponse) { ctx.universe = u; mark('universe') }

/** a worker answer at another price_data than the catalog: ask catalog and universe again (6c.5 item 3) */
let reasking = false;
async function versionSeen(v: Versions) {
  if (!ctx.catalog || v.price_data === ctx.catalog.versions.price_data || reasking) return;
  reasking = true;
  try {
    const [c, u] = await Promise.all([ctx.api.catalog(tags.catalog), ctx.api.universe(tags.universe)]);
    if (c.status === 200) { tags.catalog = c.etag; useCatalog(c.body); boot.putCatalog(ctx.login, c.bytes, c.etag, c.body) }
    if (u.status === 200) { tags.universe = u.etag; useUniverse(u.body); boot.putUniverse(ctx.login, u.bytes, u.etag, u.body) }
    refresh('all');
  } catch { /* the next answer asks again */ } finally { reasking = false }
}

/** restore the last open screen once the catalog is known (its cards are mapped on the catalog's entries) */
let restored = false;
function restoreLast(cachedResult: RunResponse | null) {
  if (restored || !ctx.catalog) return; restored = true;
  const last = lastScreen();
  if (!last) { refresh('all'); return }
  const src = last.item_id ? { kind:'saved' as const, item_id:last.item_id, revision:0 } : last.preset ? { kind:'preset' as const, id:last.preset } : null;
  const st = stateOfDefinition(last.definition);
  S.universe = st.universe; S.cards = st.cards; S.logic = st.logic; S.atLeast = st.atLeast; S.name = last.name || 'Untitled screen';
  S.source = src; S.dirty = false;
  if (last.sort) S.sort = { key:last.sort.key as typeof S.sort.key, dir:last.sort.dir };
  S.nearMiss = !!last.near;
  // the cached result of this definition, when its versions equal the catalog's (6c.4 S5): no run
  const key = canonical(definitionOf());
  const p = boot.pointer();
  if (cachedResult && p?.last && canonical(p.last.definition) === key && sameVersions(cachedResult.versions, ctx.catalog.versions)) {
    ctx.R = resultOf(cachedResult, key); mark('results from cache');
  }
  refresh('all');
}

/* ---- boot (6c.4) ------------------------------------------------------------------------------------------- */
const failMsg = (e: unknown) => e instanceof ApiFailure ? e.message : T.unreachable;
async function withRetry<T>(fn: () => Promise<T>, onWait: (msg: string) => void): Promise<T> {
  for (let k = 0; ; k++) {
    try { return await fn() }
    catch (e) {
      const f = e instanceof ApiFailure ? e : null;
      if (f?.code === 'SCREENER_NOT_READY') { onWait(f.message); await sleep(Math.max(1, f.retryAfter ?? 5) * 1000); continue }
      if (f?.code === 'BUSY' && k < 2) { onWait(f.message); await sleep(1000 * (k + 1)); continue }
      if ((f?.code === 'SCREENER_UNAVAILABLE' || f?.code === 'NETWORK') && k < 1) { onWait(f.message); await sleep(2000); continue }
      throw e;
    }
  }
}
const sleep = (ms: number) => new Promise(ok => setTimeout(ok, ms));

function bootFailed(msg: string, retry: boolean) {
  ctx.runError = msg; ctx.running = false;
  $('resPane').innerHTML = `<div class="empty" role="alert"><strong>The screener could not load</strong>${esc(msg)}${retry ? `<div class="acts"><button class="btn sm" data-act="reboot">${ico(IC.reset, 's')}${T.retry}</button></div>` : ''}</div>`;
  const dl = document.getElementById('dataLine'); if (dl) dl.innerHTML = `<span class="note down">${esc(msg)}</span>`;
}

export async function bootPage(api: ScreenerApi, opts: { cache?: FileCache } = {}) {
  ctx.api = api;
  mark('page script');
  applyTheme(); followTheme(() => { if (S.preview) renderDetails() });
  const pp = panelPrefs();
  S.preview = !!pp.preview; S.bOpen = pp.bOpen ?? true; S.perPage = [10, 25, 50, 100].includes(pp.perPage!) ? pp.perPage! : 25;
  S.pvView = pp.pvView === 'perf' ? 'perf' : 'chart'; S.perf = pp.perf || '6M';
  Object.assign(ui, { refresh, renderHeader, renderUniverse, renderPresets, renderConds, renderResults, renderDetails, togglePreview, pickStock, openSource, toast, markDirty, schedule, versionSeen });
  runHooks.mark = mark;
  runHooks.answered = (def, bytes, r) => { if (ctx.login) boot.putResult(ctx.login, def, bytes, r) };
  bind();
  boot = new BootCache(opts.cache ?? fileCache());
  const et = boot.etags();
  tags.catalog = et.catalog; tags.universe = et.universe;
  renderHeader(); renderUniverse(); renderConds(); renderResults();

  // S2: everything at once
  const sessionP = api.session().then(s => { ctx.login = s.login; mark('session'); return s });
  const catP = withRetry(() => api.catalog(et.catalog), m => { const dl = document.getElementById('dataLine'); if (dl) dl.innerHTML = `<span class="sbox">${spin(esc(m))}</span>` });
  const uniP = withRetry(() => api.universe(et.universe), () => {});
  const itemsP = api.items('screen'), metricsP = api.items('metric'), watchP = api.watchlist();
  // S6: saved screens, My metrics and the watchlist fill in whenever they answer
  itemsP.then(r => { ctx.saved = r.items; renderPresets(); if (S.source?.kind === 'saved') { const s = ctx.saved.find(x => x.item_id === (S.source as any).item_id); if (s) S.source = { kind:'saved', item_id:s.item_id, revision:s.revision }; else { S.source = null; S.dirty = true } renderHeader() } })
    .catch(e => { ctx.saved = []; renderPresets(); if (!(e instanceof ApiFailure && e.status === 401)) toast(`Saved screens: ${failMsg(e)}`) });
  metricsP.then(r => { ctx.metrics = r.items }).catch(() => { ctx.metrics = [] });
  watchP.then(r => { ctx.watch = new Set(r.tickers.map(t => t.ticker)); renderResults() }).catch(() => { ctx.watch = null });

  let session;
  try { session = await sessionP }
  catch (e) { bootFailed(failMsg(e), !(e instanceof ApiFailure && e.status === 401)); return }

  // S3: cached paint, only after an authenticated answer, only for this login
  const cached = await boot.read(session.login).catch(() => ({ catalog:null, universe:null, result:null }));
  if (cached.catalog && !ctx.catalog) {
    useCatalog(cached.catalog); if (cached.universe) useUniverse(cached.universe);
    ctx.bootState = 'cached'; $('app').dataset.boot = 'cached';
    restoreLast(cached.result);
  }

  // S4: confirm or replace
  let cat: Conditional<CatalogResponse>, uni: Conditional<UniverseResponse>;
  try { [cat, uni] = await Promise.all([catP, uniP]) }
  catch (e) { if (!ctx.catalog) bootFailed(failMsg(e), true); else { confirmed = true; ctx.runError = failMsg(e); refresh('results') } return }
  if (cat.status === 304 && !cached.catalog) cat = await api.catalog(null).catch(() => cat);     // 304 without the bytes: ask again in full
  if (uni.status === 304 && !cached.universe) uni = await api.universe(null).catch(() => uni);
  if (cat.status === 200) { tags.catalog = cat.etag; useCatalog(cat.body); boot.putCatalog(session.login, cat.bytes, cat.etag, cat.body).catch(() => {}) }
  if (uni.status === 200) { tags.universe = uni.etag; useUniverse(uni.body); boot.putUniverse(session.login, uni.bytes, uni.etag, uni.body).catch(() => {}) }
  if (!ctx.catalog) { bootFailed(T.unreachable, true); return }
  confirmed = true;
  if (!restored) restoreLast(cached.catalog && cat.status === 304 ? cached.result : null);
  else refresh('all');
}

/* ---- events (the prototype's delegated listeners) ---------------------------------------------------------- */
let typingT: ReturnType<typeof setTimeout> | undefined;
function bind() {
  $('pageHead').addEventListener('click', onHeadClick); $('pageActs').addEventListener('click', onHeadClick);
  $('pageHead').addEventListener('change', e => {
    const t = e.target as HTMLInputElement; if (t.id !== 'titleIn') return;
    const v = t.value.trim() || 'Untitled screen';
    if (v !== S.name) { S.name = v; markDirty(); remember() } else t.value = v;
  });
  $('pageHead').addEventListener('keydown', e => { const t = e.target as HTMLInputElement; if (t.id === 'titleIn' && e.key === 'Enter') t.blur() });
  $('pageHead').addEventListener('input', e => { const t = e.target as HTMLInputElement; if (t.id === 'titleIn') t.size = Math.max(8, t.value.length) });
  const onClick = (e: Event) => {
    const b = (e.target as HTMLElement).closest('button,[data-tgl]') as HTMLElement | null; if (!b) return;
    if (onUniverseClick(b) || onPresetClick(b) || onBuilderClick(b)) return;
  };
  for (const id of ['cardU', 'cardC', 'pop', 'drawerHost']) {
    const el = $(id);
    el.addEventListener('click', onClick);
    el.addEventListener('change', e => { const t = e.target as HTMLInputElement; if (t.id === 'adderQ' || t.id === 'tq' || t.id === 'pvq') return; clearTimeout(typingT); onUniverseField(t) || onBuilderField(t) });
    el.addEventListener('input', e => {
      const t = e.target as HTMLInputElement; if (t.type !== 'number') return;
      clearTimeout(typingT); typingT = setTimeout(() => { onUniverseField(t) || onBuilderField(t) }, 350);
    });
  }
  $('cardC').addEventListener('input', e => { const t = e.target as HTMLInputElement; if (t.id === 'adderQ') onAdderInput(t.value) });
  $('cardC').addEventListener('focusin', e => { const t = e.target as HTMLInputElement; if (t.id === 'adderQ') drawSuggest(t.value) });
  $('cardC').addEventListener('keydown', onAdderKey);
  $('drawerHost').addEventListener('mousedown', e => { if ((e.target as HTMLElement).matches('[data-dwrap]')) openDrawer(false) });
  // role=tab segments: arrow keys move between the preset category tabs (report 9.2 accessibility)
  $('cardU').addEventListener('keydown', e => {
    const t = e.target as HTMLElement; if (t.getAttribute('role') !== 'tab' || !(e.key === 'ArrowRight' || e.key === 'ArrowLeft')) return;
    const tabs = [...t.parentElement!.querySelectorAll<HTMLElement>('[role="tab"]')], i = tabs.indexOf(t) + (e.key === 'ArrowRight' ? 1 : -1);
    const n = tabs[(i + tabs.length) % tabs.length]; e.preventDefault(); n.click();
  });
  document.addEventListener('pointerdown', e => {
    const t = e.target as HTMLElement;
    if (!t.closest('.adder')) hideSuggest();
    if (!t.closest('#menu') && !t.closest('[data-menu]')) $('menu').hidden = true;
    if (S.pop && !t.closest('#pop') && !t.closest('[data-qf]')) closePop();
  });
  document.addEventListener('keydown', e => {
    const tag = (document.activeElement as HTMLElement | null)?.tagName || '';
    if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(tag) && !dialogOpen()) { e.preventDefault(); if (!S.bOpen) { S.bOpen = true; renderConds() } ($('adderQ') as HTMLInputElement | null)?.focus() }
    if (e.key === 'Escape') {
      if (!$('menu').hidden) { $('menu').hidden = true; return }
      if (dialogOpen()) { closeDialog(); return }
      if (S.pop) { closePop(); return }
      if (S.drawer) { openDrawer(false); return }
      if (S.preview && !/INPUT|TEXTAREA|SELECT/.test(tag)) togglePreview(false);
    }
  });
  addEventListener('resize', () => { fitPresets(); if (S.pop) placePop(); sizePreview() });
  addEventListener('scroll', () => { if (S.pop) placePop(); sizePreview() }, { passive:true });
  for (const id of ['resPane', 'resTools', 'bulk']) $(id).addEventListener('click', onResultsClick);
  for (const id of ['resPane', 'resTools']) $(id).addEventListener('change', onResultsChange);
  $('resPane').addEventListener('keydown', onResultsKey);
  $('resPane').addEventListener('click', e => { if ((e.target as HTMLElement).closest('[data-act="reboot"]')) location.reload() });
  const tq = $('tq') as HTMLInputElement;
  tq.addEventListener('input', () => { S.q = tq.value; renderResults() });
  tq.addEventListener('keydown', e => { if (e.key === 'Escape' && S.q) { S.q = ''; tq.value = ''; renderResults() } });
  $('tqClear').onclick = () => { S.q = ''; tq.value = ''; renderResults(); tq.focus() };
  $('cardC').addEventListener('click', e => { if ((e.target as HTMLElement).closest('[data-act="btoggle"]')) savePanel({ bOpen:S.bOpen }) });
  $('resPane').addEventListener('change', e => { if ((e.target as HTMLElement).id === 'perPage') savePanel({ perPage:S.perPage }) });
  bindPreview();
}
