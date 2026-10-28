/* Presets and My screens (the prototype's presetsHtml, fitPresets, openSource), over catalog.presets and the server's
   saved screens (P12 a). Counts come with the catalog (computed once per publication by the worker, report 6.7), never
   from 26 screens in the browser. An unavailable preset stays visible, disabled, its reason naming the unavailable
   legs; it never runs with a leg removed, and "Load without the unavailable legs" is an explicit action that lists the
   dropped legs (report 9.2). My screens' counts are asked (POST counts) only while their tab is open (6c.4 S7). */
import type { CatalogPreset, Definition, ScreenItemDefinition } from './core/contract.ts';
import { esc, nf } from './format.ts';
import { IC, ico } from './icons.ts';
import { activeCards, ctx, presetOf, S, savedOf, stateOfDefinition, ui } from './state.ts';
import { confirmDialog, dialog, closeDialog, newItemId, toast } from './dialogs.ts';
import { ApiFailure } from './api/types.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { T } from './texts.ts';

const $ = (id: string) => document.getElementById(id);
const CAT_ORDER = ['Bandarmology', 'Technical', 'Fundamental', 'Combined'];
const tabLabel = (c: string) => c === 'Bandarmology' ? 'Bandar' : c;
let countsAsked = '';

const presetCats = () => { const cats = new Set((ctx.catalog?.presets || []).map(p => p.category)); return [...CAT_ORDER.filter(c => cats.has(c)), ...[...cats].filter(c => !CAT_ORDER.includes(c))] };
const legNames = (p: CatalogPreset) => p.unavailable_legs.map(id => { const c = p.definition.conditions.find(x => x.id === id); return c?.label || id });

function presetsHtml(): string {
  if (!ctx.catalog) return `<span>Presets</span><span class="sbox">${spin(T.loadingPresets)}</span>`;
  const saved = ctx.saved, cats = ['All', ...presetCats(), 'My screens'];
  const chip = (id: string, name: string, title: string, n: number | null, extra = '', disabled = '') =>
    `<span class="pchip ${S.source && srcKey() === id ? 'on' : ''} ${disabled ? 'na' : ''}" title="${esc(disabled ? `${title}\n${disabled}` : title)}"><button data-open="${esc(id)}" aria-pressed="${srcKey() === id}" ${disabled ? 'aria-disabled="true"' : ''} style="display:inline-flex;align-items:center;gap:6px">${ico(srcKey() === id ? IC.check : IC.plus, 's')}${esc(name)}<span class="n ${n ? '' : 'z'}" title="${disabled ? 'Not available' : 'Stocks that match today'}">${n == null ? '—' : nf(n)}</span></button>${extra}</span>`;
  let list: string;
  if (S.pcat === 'My screens') {
    list = saved == null ? spin('Loading your screens')
      : saved.length ? saved.map(s => {
        const c = ctx.counts.get(s.item_id), n = c && 'match' in c ? c.match : null, def = (s.definition as ScreenItemDefinition).definition;
        const conds = def?.conditions?.filter(x => x.enabled !== false).length ?? 0;
        return chip('s:' + s.item_id, s.name, `${conds} conditions · saved ${s.updated_at.slice(0, 10)}${s.needs_review.length ? ' · needs review' : ''}${c && 'error' in c ? ' · ' + c.error : ''}`, n,
          `<button class="x" data-dup-saved="${esc(s.item_id)}" title="Duplicate ${esc(s.name)}" aria-label="Duplicate ${esc(s.name)}">${ico(IC.dup, 's')}</button><button class="x" data-del-saved="${esc(s.item_id)}" title="Delete ${esc(s.name)}" aria-label="Delete ${esc(s.name)}">${ico(IC.x, 's')}</button>`);
      }).join('')
      : `<small class="muted">No saved screens yet. Build a screen, then use Save screen.</small>`;
  } else {
    list = ctx.catalog.presets.filter(p => S.pcat === 'All' || p.category === S.pcat).map(p => {
      const na = p.availability !== 'AVAILABLE', reason = na ? `${p.reason || 'Not available'}${p.unavailable_legs.length ? ` — unavailable: ${legNames(p).join(', ')}` : ''}` : '';
      const partial = na && p.unavailable_legs.length && p.unavailable_legs.length < p.definition.conditions.length
        ? `<button class="x" data-partial="${esc(p.id)}" title="Load without the unavailable legs" aria-label="Load ${esc(p.name)} without the unavailable legs">${ico(IC.more, 's')}</button>` : '';
      return chip('p:' + p.id, p.name, p.why, na ? null : p.match_count, partial, reason);
    }).join('');
  }
  const p = S.source?.kind === 'preset' ? presetOf(S.source.id) : null;
  const n = saved?.length || 0;
  return `<span>Presets</span><span class="seg sm" role="tablist" aria-label="Preset category">${cats.map(c => `<button class="${S.pcat === c ? 'on' : ''}" data-pcat="${esc(c)}" role="tab" aria-selected="${S.pcat === c}" tabindex="${S.pcat === c ? 0 : -1}">${esc(tabLabel(c))}${c === 'My screens' && n ? ` <span class="count">${n}</span>` : ''}</button>`).join('')}</span>
    <div class="prow"><div class="chips-row ${S.pexp ? '' : 'clamp'}" id="pRow">${list}</div><button class="pmore ${S.pexp ? 'open' : ''}" data-act="pexp" id="pMore" hidden title="${S.pexp ? 'Show fewer presets' : 'Show all presets'}" aria-label="${S.pexp ? 'Show fewer presets' : 'Show all presets'}" aria-expanded="${!!S.pexp}">${ico(IC.chev, 's')}</button></div>${p ? `<div class="pwhy cat-${esc(p.category)}"><b>${esc(p.name)}</b> · ${esc(p.why)}</div>` : ''}`;
}
const srcKey = () => S.source?.kind === 'preset' ? 'p:' + S.source.id : S.source?.kind === 'saved' ? 's:' + S.source.item_id : '';

export function renderPresets() {
  const el = $('uPresets'); if (!el) return;
  el.innerHTML = presetsHtml(); fitPresets();
  if (S.pcat === 'My screens') askCounts();
}
/** one row of presets until the round button expands them; the active preset moves to the front while collapsed */
/** fit the preset chips to one row (the prototype's fitPresets). It reads the layout, so it runs once per frame, after
    the frame's DOM writes, instead of forcing a layout inside every render. */
let fitFrame = 0;
export function fitPresets() {
  if (fitFrame) return;
  fitFrame = requestAnimationFrame(() => { fitFrame = 0; fitNow() });
}
function fitNow() {
  const row = $('pRow'), btn = $('pMore'); if (!row || !btn) return;
  if (!S.pexp) { const on = row.querySelector('.pchip.on') as HTMLElement | null; if (on && row.firstElementChild && on.offsetTop > (row.firstElementChild as HTMLElement).offsetTop) row.prepend(on) }
  btn.hidden = !S.pexp && row.scrollHeight <= row.clientHeight + 2;
}

/** POST counts for the saved screens, once per publication while the My screens tab is open (6c.4 S7) */
async function askCounts() {
  const saved = ctx.saved, v = ctx.catalog?.versions.price_data;
  if (!saved?.length || !v) return;
  const max = ctx.catalog?.limits.find(l => l.name === 'max_counts')?.value ?? 50;
  const todo = saved.filter(s => !ctx.counts.has(s.item_id)).slice(0, max);
  const key = v + '|' + todo.map(s => s.item_id + ':' + s.definition_hash).join(',');
  if (!todo.length || key === countsAsked) return;
  countsAsked = key;
  try {
    const r = await ctx.api.counts({ schema_version:1, definitions:todo.map(s => ({ item_id:s.item_id, definition:(s.definition as ScreenItemDefinition).definition })) });
    for (const c of r.counts) ctx.counts.set(c.item_id, 'error' in c ? { error:c.error.message || c.error.code } : { match:c.match_count, near:c.near_count });
    if (S.pcat === 'My screens') { const el = $('uPresets'); if (el) { el.innerHTML = presetsHtml(); fitPresets() } }
  } catch { countsAsked = '' }
}

/** Load a preset ('p:<id>') or a saved screen ('s:<item_id>') into the page (the prototype's openSource). */
export function openSource(id: string, opts: { partial?: boolean } = {}) {
  if (id.startsWith('p:')) {
    const p = presetOf(id.slice(2)); if (!p) return;
    let def: Definition = p.definition;
    if (p.availability !== 'AVAILABLE') {
      if (!opts.partial) { toast(`${p.name}: ${p.reason || 'not available'}`); return }
      def = { ...def, conditions:def.conditions.filter(c => !p.unavailable_legs.includes(c.id)) };
    }
    loadDefinition(def, p.name, { kind:'preset', id:p.id });
    toast(opts.partial ? `${p.name} loaded without: ${legNames(p).join(', ')}` : `${p.name} loaded`);
    return;
  }
  const s = savedOf(id.slice(2)); if (!s) return;
  const d = s.definition as ScreenItemDefinition;
  loadDefinition(d.definition, s.name, { kind:'saved', item_id:s.item_id, revision:s.revision }, d.view);
  // needs_review fields are highlighted on their cards; nothing is adjusted (report 9.5)
  for (const r of s.needs_review) {
    const m = /^conditions\[(\d+)\]\.?(.*)$/.exec(r.field) || /^conditions\.(\d+)\.?(.*)$/.exec(r.field);
    const c = m ? S.cards[+m[1]] : undefined;
    if (c) (c.review ||= []).push(`${m![2] || 'condition'}: ${r.reason}`);
  }
  ui.renderConds();
  toast(`${s.name} loaded${s.needs_review.length ? ` · ${s.needs_review.length} field${s.needs_review.length > 1 ? 's' : ''} to review` : ''}`);
}
export function loadDefinition(def: Definition, name: string, source: typeof S.source, view?: ScreenItemDefinition['view']) {
  const st = stateOfDefinition(def);
  S.universe = st.universe; S.cards = st.cards; S.logic = st.logic; S.atLeast = st.atLeast;
  S.name = name; S.source = source; S.dirty = false; S.sel.clear(); S.open.clear(); S.errors = {};
  S.sort = view?.sort ? { key:view.sort.key as typeof S.sort.key, dir:view.sort.dir } : { key:'match', dir:'desc' };
  S.nearMiss = !!view?.show_near; S.page = 1;
  ui.refresh('all');
}

/** clicks on preset chips, tabs and My screens' buttons */
export function onPresetClick(b: HTMLElement): boolean {
  const d = b.dataset;
  if (d.pcat) { S.pcat = d.pcat; renderPresets(); ($('uPresets')?.querySelector(`[data-pcat="${CSS.escape(d.pcat)}"]`) as HTMLElement | null)?.focus(); return true }
  if (d.partial) {
    const p = presetOf(d.partial); if (!p) return true;
    dialog(`<div class="dialog" role="dialog" aria-label="Load without the unavailable legs"><div class="dialog-h"><div style="flex:1"><strong>${esc(p.name)}</strong><small>${esc(p.reason || 'Some conditions have no data yet.')}</small></div><button class="iconbtn sm" data-close>${ico(IC.x)}</button></div>
      <div class="dialog-b"><p class="note" style="margin:0">Loading it without these conditions changes what the preset means:</p><ul class="ib-ops">${legNames(p).map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>
      <div class="dialog-f"><button class="btn" data-close>Cancel</button><button class="btn dark" id="ppGo">Load without them</button></div></div>`, () => {
      $('ppGo')!.onclick = () => { closeDialog(); openSource('p:' + p.id, { partial:true }) };
    });
    return true;
  }
  if (d.open) {
    if (srcKey() === d.open) {
      // clicking the active preset again clears its conditions and keeps the universe (the prototype)
      S.cards = []; S.logic = 'all'; S.atLeast = 2; S.name = 'Untitled screen'; S.source = null; S.dirty = false; S.sel.clear(); S.open.clear(); S.errors = {};
      S.sort = { key:'match', dir:'desc' }; ui.refresh('all'); toast('Preset cleared'); return true;
    }
    openSource(d.open); return true;
  }
  if (d.delSaved) {
    const s = savedOf(d.delSaved); if (!s) return true;
    confirmDialog(`Delete ${s.name}?`, 'The saved screen is removed from your EDGE account. This cannot be undone.', 'Delete', async () => {
      try {
        await ctx.api.deleteItem(s.item_id);
        ctx.saved = (ctx.saved || []).filter(x => x.item_id !== s.item_id); ctx.counts.delete(s.item_id);
        if (S.source?.kind === 'saved' && S.source.item_id === s.item_id) { S.source = null; S.dirty = true }
        renderPresets(); ui.renderHeader(); toast(`${s.name} deleted`);
      } catch (e) { toast(e instanceof ApiFailure ? e.message : String(e)) }
    });
    return true;
  }
  if (d.dupSaved) {
    const s = savedOf(d.dupSaved); if (!s) return true;
    const all = new Set((ctx.saved || []).map(x => x.name)); let nm = s.name + ' copy'; while (all.has(nm)) nm += '′';
    ctx.api.putItem(newItemId(), { kind:'screen', name:nm, definition:s.definition as ScreenItemDefinition })
      .then(it => { ctx.saved = [...(ctx.saved || []), it]; renderPresets(); toast(`Duplicated as ${nm}`) })
      .catch(e => toast(e instanceof ApiFailure ? e.message : String(e)));
    return true;
  }
  if (d.act === 'pexp') { S.pexp = !S.pexp; renderPresets(); return true }
  return false;
}
export const presetCount = () => activeCards().length;
