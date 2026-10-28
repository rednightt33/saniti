/* Card 2: the Screen builder (the prototype's renderConds, condRow, drawSuggest, addCond, addMetric, applyField for
   cards), on the catalog's entries. Kept: the type-ahead adder with "/" and arrow keys, My metrics first, the quick
   rail, Default / Custom with the changed fields marked, Save as My metric, the operator select, "within N sessions",
   All / Any / At least n bounded by the active count. Changed (report 9.2): entries, synonyms and defaults come from
   the catalog; invalid input is refused in place with the field and the allowed range, never rounded or ignored;
   `between` with value > value2 is refused; each card shows its pass count from the run ("m of U pass" when exhaustive,
   else "m of n evaluated"). */
import type { SavedItem } from './core/contract.ts';
import { esc, nf } from './format.ts';
import { COLORS, IC, ico } from './icons.ts';
import { activeCards, ctx, entryOf, S, ui } from './state.ts';
import { byGroup, defaultParams, GHEAD, GL, isDefP, matches, paramError, rangeText, type Entry } from './entries.ts';
import { cardErrors, cardName, condText, displayUnit, fromWire, isCustom, newCard, newCardId, optOf, paramSummary, type Card } from './forms.ts';
import { confirmDialog, openSaveMetric, toast } from './dialogs.ts';
import { openBrowser } from './browser.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { T } from './texts.ts';
import { ApiFailure } from './api/types.ts';

const $ = (id: string) => document.getElementById(id);
const withinMax = () => ctx.catalog?.limits.find(l => l.name === 'within_max')?.value ?? 130;
const maxConds = () => ctx.catalog?.limits.find(l => l.name === 'max_conditions');
export const colorOf = (c: Card) => COLORS[Math.max(0, S.cards.indexOf(c)) % COLORS.length];

/** the card's pass count from the run that answers the current definition (report 9.2, 6.10) */
function passText(c: Card): { txt: string; title: string } | null {
  const run = ctx.R?.run; if (!run || ctx.stale || !c.on) return null;
  const s = run.conditions.find(x => x.id === c.id); if (!s) return null;
  if (s.exhaustive) return { txt:`${nf(s.passed)} of ${nf(run.universe.eligible)} pass`, title:`${nf(s.passed)} of the ${nf(run.universe.eligible)} stocks in the universe pass${s.na ? `; ${nf(s.na)} n/a` : ''}.` };
  return { txt:`${nf(s.passed)} of ${nf(s.evaluated)} evaluated`, title:'Counted on the tickers that can still match or be near; run exhaustively for the full count.' };
}

function condRow(c: Card): string {
  const e = entryOf(c), col = colorOf(c), errs = S.errors[c.id] || {};
  const head = `<div class="mrow"><i class="cdot" style="background:${col}"></i><b data-nm="${c.id}" title="${esc(e?.desc || '')}">${esc(cardName(e, c))}</b><span class="sw" title="Enable / disable"><input type="checkbox" data-c="${c.id}" data-k="on" ${c.on ? 'checked' : ''} aria-label="Enable condition"><span></span></span><button class="iconbtn sm mx" data-del="${c.id}" title="Remove condition" aria-label="Remove condition">${ico(IC.x, 's')}</button></div>`;
  const review = c.review?.length ? `<span class="pill t-warning" title="${esc(c.review.join('\n'))}">Needs review</span>` : '';
  const pt = passText(c), pass = `<div class="note cnt" data-pass="${c.id}" ${pt ? `title="${esc(pt.title)}"` : ''}>${pt ? esc(pt.txt) : ''}</div>`;
  if (!e || c.raw) return `<div class="mc ${c.on ? '' : 'off'}" data-card="${c.id}">${head}<div class="note msum" data-sum="${c.id}">${esc(condText(e, c))}</div>${review}${pass}</div>`;
  const o = optOf(e, c), cus = isCustom(e, c) || S.open.has(c.id);
  const u = displayUnit(o?.unit);
  const err = (k: string) => errs[k] ? `<span class="ferr" role="alert">${esc(errs[k])}</span>` : '';
  const inv = (k: string) => errs[k] ? 'aria-invalid="true"' : '';
  const vals = o && o.value === 'input' ? `<div class="vrow"><input class="inp" type="number" step="any" data-c="${c.id}" data-k="value" value="${c.value}" ${inv('value')} aria-label="${o.between ? 'From' : 'Value'}">${o.between ? `<span class="unit">–</span><input class="inp" type="number" step="any" data-c="${c.id}" data-k="value2" value="${c.value2}" ${inv('value2')} aria-label="To">` : ''}${u ? `<span class="unit">${esc(u)}</span>` : ''}</div>${err('value')}${err('value2')}` : '';
  const within = o?.within ? `<div class="vrow"><span class="unit">within</span><input class="inp" type="number" min="1" max="${withinMax()}" step="1" data-c="${c.id}" data-k="within" value="${c.within}" ${inv('within')} aria-label="Within sessions"><span class="unit">sessions</span></div>${err('within')}` : '';
  const pf = (p: Entry['params'][number], second = false) => {
    const v = second ? c.second[p.key] : c.params[p.key], k = (second ? '2.' : '') + p.key, attr = second ? 'data-p2' : 'data-p';
    const field = p.options ? `<select class="sel" data-c="${c.id}" ${attr}="${p.key}">${p.options.map(x => `<option value="${esc(x)}" ${String(x) === String(v) ? 'selected' : ''}>${esc(x)}</option>`).join('')}</select>`
      : p.type === 'boolean' ? `<select class="sel" data-c="${c.id}" ${attr}="${p.key}"><option value="true" ${v === true ? 'selected' : ''}>true</option><option value="false" ${v === false ? 'selected' : ''}>false</option></select>`
      : `<input class="inp" type="number" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="${p.step ?? (p.integer ? 1 : 'any')}" data-c="${c.id}" ${attr}="${p.key}" value="${esc(v)}" ${inv(k)} title="${esc(rangeText(p))}">`;
    return `<label class="pf ${isDefP(p, v) ? '' : 'chg'}" data-pf="${c.id}|${k}"><span>${esc((second ? '2nd ' : '') + (p.label || p.key))}</span>${field}<small>${errs[k] ? `<b class="down">${esc(errs[k])}</b>` : `default ${esc(p.default)}`}</small></label>`;
  };
  const twoLines = o && (o.form === 'state_instance' || o.form === 'event_instance');
  const mode = e.params.length ? `<span class="seg sm mseg"><button class="${cus ? '' : 'on'}" data-segd="${c.id}" title="Use the standard parameters (the registry's defaults)">Default</button><button class="${cus ? 'on' : ''}" data-segc="${c.id}" title="Set your own parameters">Custom</button></span>` : `<span class="note">No parameters</span>`;
  const grid = e.params.length && (cus || twoLines) ? `<div class="pgrid">${e.params.map(p => pf(p)).join('')}${twoLines ? e.params.map(p => pf(p, true)).join('') : ''}</div><div class="mrow"><span class="pbadge my" data-pm="${c.id}" ${c.metric ? '' : 'hidden'}>★ ${esc(c.metric?.name || '')}</span><button class="link" data-savem="${c.id}">${ico(IC.star, 's')}Save as My metric</button></div>` : '';
  const ops = `<select class="sel" data-c="${c.id}" data-k="op" aria-label="Condition">${e.opts.map(x => `<option value="${esc(x.key)}" ${x.key === c.opt ? 'selected' : ''} ${x.disabled ? `disabled title="${esc(x.disabled)}"` : ''}>${esc(x.label)}${x.disabled ? ' — not offered' : ''}</option>`).join('')}</select>${err('op')}`;
  return `<div class="mc ${c.on ? '' : 'off'} ${cus ? 'cus' : ''}" data-card="${c.id}">${head}
    <div class="note msum" data-sum="${c.id}">${esc(condText(e, c))}</div>${review}
    ${mode}${grid}${ops}${vals}${within}${pass}</div>`;
}

/** update one card in place while typing (the prototype's paramUI2) */
function paramUI(c: Card) {
  const e = entryOf(c), card = document.querySelector(`[data-card="${c.id}"]`); if (!e || !card) return;
  const cus = isCustom(e, c) || S.open.has(c.id);
  card.classList.toggle('cus', cus);
  const sum = card.querySelector('[data-sum]'); if (sum) sum.textContent = condText(e, c);
  card.querySelector('[data-segd]')?.classList.toggle('on', !cus); card.querySelector('[data-segc]')?.classList.toggle('on', cus);
  e.params.forEach(p => card.querySelector(`[data-pf="${c.id}|${p.key}"]`)?.classList.toggle('chg', !isDefP(p, c.params[p.key])));
  const pm = card.querySelector('[data-pm]') as HTMLElement | null; if (pm) { pm.hidden = !c.metric; pm.textContent = '★ ' + (c.metric?.name || '') }
  const nm = card.querySelector('[data-nm]'); if (nm) nm.textContent = cardName(e, c);
}
export const bSum = () => {
  const a = activeCards().length, R = ctx.R;
  if (!a) return 'Combine technical, fundamental and flow conditions';
  return `${a} active condition${a > 1 ? 's' : ''}${R?.run && !ctx.stale ? ` · ${nf(R.run.match_count)} of ${nf(R.eligible)} pass` : ''}`;
};
export function updateCondsLight() {
  for (const c of S.cards) { const el = document.querySelector(`[data-pass="${c.id}"]`) as HTMLElement | null; if (el) { const t = passText(c); el.textContent = t?.txt || ''; el.title = t?.title || '' } paramUI(c) }
  const s = $('bSum'); if (s) s.textContent = bSum();
}

const quick = () => {
  const ids = ['I13', 'I15', 'I06', 'I09', 'I27', 'I37'].filter(k => ctx.byKey.has(k));
  const metric = ['hi52', 'return_rank', 'volspike', 'adv20_idr'].find(k => ctx.byKey.get(k)?.available);
  const bandar = ['bandar', 'B1'].find(k => ctx.byKey.has(k));
  return [...ids, ...(metric ? [metric] : []), ...(bandar ? [bandar] : [])].map(k => ctx.byKey.get(k)!);
};
export function renderConds() {
  const el = $('cardC'); if (!el) return;
  const sl = $('condList')?.scrollLeft || 0, a = activeCards().length, n = S.cards.length;
  const lim = maxConds();
  const ready = !!ctx.catalog;
  el.innerHTML = `<div class="builder-h"><button class="tgl ${S.bOpen ? '' : 'closed'}" data-act="btoggle" aria-expanded="${S.bOpen}">${ico(IC.chev, 's')}Screen builder <small id="bSum">${bSum()}</small></button><span class="sp"></span>
      ${n > 1 ? `<span class="logic">Match <span class="seg sm" role="radiogroup" aria-label="Match"><button class="${S.logic === 'all' ? 'on' : ''}" data-logic="all" role="radio" aria-checked="${S.logic === 'all'}">All</button><button class="${S.logic === 'any' ? 'on' : ''}" data-logic="any" role="radio" aria-checked="${S.logic === 'any'}">Any</button><button class="${S.logic === 'at_least' ? 'on' : ''}" data-logic="at_least" role="radio" aria-checked="${S.logic === 'at_least'}">At least</button></span>${S.logic === 'at_least' ? `<input class="inp" type="number" min="1" max="${Math.max(1, a)}" step="1" data-s="atLeast" value="${S.atLeast}" aria-label="At least N">` : ''}<span>of ${a} active</span></span>` : ''}
      ${n ? `<button class="btn sm ghost" data-act="clearconds">Clear</button>` : ''}</div>
    ${S.bOpen ? `<div class="builder-b">${!ready ? `<div class="sbox">${spin(T.loadingIndicators)}</div>` : `<div class="adder"><label class="searchbox">${ico(IC.search, 's')}<input id="adderQ" placeholder="Add a condition — search ${ctx.catalog!.indicators.length} indicators: “RSI”, “Stochastic”, “VWAP”, “Supertrend”, or “breakout”…" autocomplete="off" aria-label="Add a condition" role="combobox" aria-expanded="false" aria-controls="suggest" aria-autocomplete="list"><kbd>/</kbd><button class="xbtn" data-act="browse" title="Browse all indicators with details" aria-label="Browse all indicators">${ico(IC.expand, 's')}Browse</button></label><div class="suggest" id="suggest" role="listbox" hidden></div></div>`}
      ${lim && a > lim.value ? `<div class="note down" role="alert">${esc(lim.rule)}: switch off or remove ${a - lim.value} condition${a - lim.value > 1 ? 's' : ''}.</div>` : ''}
      ${n ? `<div class="strip" id="condList">${S.cards.map(condRow).join('')}<button class="mc madd" data-act="focusadd">${ico(IC.plus)}<span>Add indicator</span></button></div>`
        : ready ? `<div class="bempty"><span class="muted">No conditions yet. Start from a preset, search above, or add a first condition:</span><div class="qrail"><button class="btn sm" data-act="browse">${ico(IC.expand, 's')}Browse all</button>${quick().map(e => `<button class="btn sm" data-quick="${esc(e.key)}" ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${ico(IC.plus, 's')}${esc(e.short === e.key ? e.label : e.label.length > 18 ? e.short : e.label)}</button>`).join('')}</div></div>` : ''}</div>` : ''}`;
  const cl = $('condList'); if (cl) cl.scrollLeft = sl;
}

/* ---- the type-ahead adder ----------------------------------------------------------------------------------- */
type Sug = { e: Entry; m?: SavedItem };
let sugIdx = 0, sugList: Sug[] = [];
const metricEntry = (m: SavedItem) => { const c = fromWire({ id:'m', enabled:true, test:(m.definition as any).test }, ctx.byKey); return c.entry ? { c, e:ctx.byKey.get(c.entry)! } : null };
export function drawSuggest(q: string) {
  const box = $('suggest'), inp = $('adderQ'); if (!box) return;
  const n = q.trim().toLowerCase();
  const mine: Sug[] = (ctx.metrics || []).map(m => ({ m, x:metricEntry(m) })).filter(({ m, x }) => x && (!n || (m.name + ' ' + x.e.label + ' ' + x.e.key).toLowerCase().includes(n))).map(({ m, x }) => ({ e:x!.e, m }));
  sugList = [...mine, ...byGroup(ctx.entries.filter(e => matches(e, n))).map(e => ({ e }))];
  if (!sugList.length) { box.innerHTML = `<div class="note" style="padding:10px">No indicator matches “${esc(q)}”.</div>`; box.hidden = false; inp?.setAttribute('aria-expanded', 'true'); return }
  sugIdx = Math.min(sugIdx, sugList.length - 1);
  let last = '';
  const emptyMine = !n && !mine.length ? `<div class="hd">My metrics</div><div class="mempty">${ctx.metrics == null ? 'Loading…' : 'None yet. Change a parameter on a condition, then press “Save as My metric” to reuse it here.'}</div>` : '';
  box.innerHTML = emptyMine + sugList.map(({ e, m }, i) => {
    const g = m ? 'My metrics' : e.group, hd = g !== last ? `<div class="hd">${esc(GHEAD(g))}</div>` : ''; last = g;
    if (m) return hd + `<div class="mrow"><button class="${i === sugIdx ? 'act' : ''}" data-addm="${esc(m.item_id)}" role="option" aria-selected="${i === sugIdx}"><span class="tag My">★ Mine</span>${esc(m.name)}<small>${esc(e.label)}</small></button><button class="mdel" data-delm="${esc(m.item_id)}" title="Delete ${esc(m.name)}" aria-label="Delete ${esc(m.name)}">${ico(IC.trash, 's')}</button></div>`;
    return hd + `<button class="sg1 ${i === sugIdx ? 'act' : ''} ${e.available ? '' : 'na'}" data-add="${esc(e.key)}" role="option" aria-selected="${i === sugIdx}" title="${esc(e.available ? e.desc : `${e.desc}\n${e.reason}`)}"><span class="tag ${esc(e.group)}">${esc(GL(e.group))}</span><span class="nm">${esc(e.label)}</span><small>${e.available ? (e.params.length ? esc(e.params.map(p => p.default).join(' · ')) : 'fixed') : 'no data'}</small></button>`;
  }).join('');
  box.innerHTML += `<button class="sgfoot" data-act="browse">${ico(IC.expand, 's')}Browse all ${ctx.entries.length} indicators with details${n ? ` for “${esc(q.trim())}”` : ''}</button>`;
  box.hidden = false; inp?.setAttribute('aria-expanded', 'true');
  box.querySelector('.act')?.scrollIntoView({ block:'nearest' });
}
const hideSuggest = () => { const s = $('suggest'); if (s) s.hidden = true; $('adderQ')?.setAttribute('aria-expanded', 'false') };

export function addCond(key: string) {
  const e = ctx.byKey.get(key); if (!e) return;
  if (!e.available) { toast(`${e.label}: ${e.reason}`); return }
  const c = newCard(e, S.cards.map(x => x.id));
  S.cards.push(c); S.bOpen = true; ui.markDirty(); ui.refresh('conds');
  setTimeout(() => document.querySelector(`[data-card="${c.id}"]`)?.scrollIntoView({ behavior:'smooth', block:'nearest', inline:'nearest' }), 30);
  toast(`${e.label} added`);
}
export function addMetric(itemId: string) {
  const m = (ctx.metrics || []).find(x => x.item_id === itemId); if (!m) return;
  const c = fromWire({ id:newCardId(S.cards.map(x => x.id)), enabled:true, test:(m.definition as any).test }, ctx.byKey);
  if (!c.entry) { toast(`${m.name} cannot be added: its indicator is not in this catalog`); return }
  c.metric = { item_id:m.item_id, name:m.name, params:{ ...c.params } };
  S.cards.push(c); S.bOpen = true; ui.markDirty(); ui.refresh('conds');
  setTimeout(() => document.querySelector(`[data-card="${c.id}"]`)?.scrollIntoView({ behavior:'smooth', block:'nearest', inline:'nearest' }), 30);
  toast(`${m.name} added`);
}
function deleteMetric(itemId: string) {
  const m = (ctx.metrics || []).find(x => x.item_id === itemId); if (!m) return;
  confirmDialog(`Delete ${m.name}?`, 'The metric is removed from your EDGE account. Conditions already using it keep their settings.', 'Delete', async () => {
    try {
      await ctx.api.deleteItem(itemId);
      ctx.metrics = (ctx.metrics || []).filter(x => x.item_id !== itemId);
      for (const c of S.cards) if (c.metric?.item_id === itemId) delete c.metric;
      ui.renderConds(); toast(`${m.name} removed from My metrics — conditions already using it keep their settings`);
    } catch (e) { toast(e instanceof ApiFailure ? e.message : String(e)) }
  });
}
const resetParams = (c: Card) => {
  const e = entryOf(c)!; c.params = defaultParams(e); syncMetric(c); delete S.errors[c.id];
  ui.markDirty(); ui.refresh('conds'); toast(`${e.label} back to default (${e.params.map(p => p.default).join(', ')})`);
};
const syncMetric = (c: Card) => { if (c.metric && JSON.stringify(c.metric.params) !== JSON.stringify(c.params)) delete c.metric };

/** the card's errors after an edit (report 9.2: refused in place) */
export function checkCard(c: Card) {
  const errs = { ...cardErrors(entryOf(c), c, withinMax()) };
  for (const [k, v] of Object.entries(S.errors[c.id] || {})) if (k.startsWith('2.') || entryOf(c)?.params.some(p => p.key === k)) errs[k] = v;
  if (Object.keys(errs).length) S.errors[c.id] = errs; else delete S.errors[c.id];
}

export function onBuilderClick(b: HTMLElement): boolean {
  const d = b.dataset;
  if (d.delm) { deleteMetric(d.delm); return true }
  if (d.addm) { hideSuggest(); const q = $('adderQ') as HTMLInputElement | null; if (q) q.value = ''; addMetric(d.addm); return true }
  if (d.segd) { const c = S.cards.find(x => x.id === d.segd)!; S.open.delete(c.id); const e = entryOf(c); if (e && isCustom(e, c)) resetParams(c); else renderConds(); return true }
  if (d.segc) { S.open.add(d.segc); renderConds(); return true }
  if (d.savem) { const c = S.cards.find(x => x.id === d.savem); if (c) openSaveMetric(c); return true }
  if (d.add) { hideSuggest(); const q = $('adderQ') as HTMLInputElement | null; if (q) q.value = ''; addCond(d.add); return true }
  if (d.quick) { addCond(d.quick); return true }
  if (d.del) { S.cards = S.cards.filter(c => c.id !== d.del); delete S.errors[d.del]; ui.markDirty(); ui.refresh('conds'); return true }
  if (d.logic) { S.logic = d.logic as typeof S.logic; ui.markDirty(); ui.refresh('conds'); return true }
  switch (d.act) {
    case 'focusadd': ($('adderQ') as HTMLInputElement | null)?.focus(); return true;
    case 'browse': hideSuggest(); openBrowser(($('adderQ') as HTMLInputElement | null)?.value || '', { addCond, addMetric }); return true;
    case 'btoggle': S.bOpen = !S.bOpen; renderConds(); return true;
    case 'clearconds': S.cards = []; S.errors = {}; ui.markDirty(); toast('Conditions cleared'); ui.refresh('conds'); return true;
  }
  return false;
}

/** field edits of the cards and the match control */
export function onBuilderField(el: HTMLInputElement | HTMLSelectElement): boolean {
  const d = el.dataset;
  if (d.s === 'atLeast') {
    const v = Number(el.value), a = activeCards().length;
    if (!Number.isInteger(v) || v < 1 || v > Math.max(1, a)) { el.setCustomValidity(`Enter a whole number from 1 to ${Math.max(1, a)}.`); el.reportValidity(); return true }
    el.setCustomValidity('');
    if (S.atLeast === v) return true;
    S.atLeast = v; ui.markDirty(); ui.refresh('conds-light'); return true;
  }
  if (!d.c) return false;
  const c = S.cards.find(x => x.id === d.c); if (!c) return true;
  const e = entryOf(c);
  if (d.p || d.p2) {
    const key = (d.p || d.p2)!, p = e?.params.find(x => x.key === key); if (!e || !p) return true;
    const v = p.type === 'boolean' ? el.value === 'true' : p.type === 'enum' ? el.value : el.value.trim() === '' ? NaN : Number(el.value);
    const errKey = (d.p2 ? '2.' : '') + key, msg = paramError(p, v as any);
    const errs = S.errors[c.id] ||= {};
    if (msg) { errs[errKey] = `${p.label || p.key}: ${msg}`; renderConds(); ui.schedule(); return true }
    delete errs[errKey];
    const target = d.p2 ? c.second : c.params;
    if (target[key] === v) { checkCard(c); return true }
    target[key] = v as any; if (!d.p2) syncMetric(c);
    checkCard(c); ui.markDirty(); ui.refresh(el.tagName === 'SELECT' ? 'conds' : 'conds-light'); return true;
  }
  const k = d.k!;
  if (k === 'on') { c.on = (el as HTMLInputElement).checked; ui.markDirty(); ui.refresh('conds'); return true }
  if (k === 'op') {
    if (c.opt === el.value) return true;
    c.opt = el.value;
    const o = e && optOf(e, c);
    if (o?.value === 'input' && c.value === '') c.value = e!.def.value;
    if (o?.between && c.value2 === '') c.value2 = e!.def.value2 === '' ? (typeof c.value === 'number' ? c.value : 0) : e!.def.value2;
    checkCard(c); ui.markDirty(); ui.refresh('conds'); return true;
  }
  const v = el.value.trim() === '' ? '' : Number(el.value);
  (c as any)[k] = v === '' || Number.isFinite(v) ? v : '';
  checkCard(c); ui.markDirty();
  const card = document.querySelector(`[data-card="${c.id}"]`);
  if (S.errors[c.id] || card?.querySelector('.ferr')) ui.refresh('conds'); else ui.refresh('conds-light');
  return true;
}

/** keyboard of the adder: arrows move, Enter adds, Escape closes (the prototype) */
export function onAdderKey(e: KeyboardEvent) {
  const t = e.target as HTMLInputElement;
  if (t.id !== 'adderQ') return;
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && sugList.length) { e.preventDefault(); sugIdx = (sugIdx + (e.key === 'ArrowDown' ? 1 : -1) + sugList.length) % sugList.length; drawSuggest(t.value) }
  else if (e.key === 'Enter' && sugList[sugIdx]) { e.preventDefault(); hideSuggest(); t.value = ''; const it = sugList[sugIdx]; it.m ? addMetric(it.m.item_id) : addCond(it.e.key) }
  else if (e.key === 'Escape') { hideSuggest(); t.blur() }
}
export const onAdderInput = (q: string) => { sugIdx = 0; drawSuggest(q) };
export { hideSuggest, paramSummary };
