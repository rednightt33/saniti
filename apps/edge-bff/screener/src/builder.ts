/* Card 2: the Screen builder (the prototype's renderConds, condRow, applyField for cards), on the catalog's entries.
   Adding goes through one window only, "Add a condition" (add-condition.ts, EXEC-SCREENER-ADD): the search box, "/",
   "+", the Add indicator tile, the quick rail and My metrics' Add open it. Kept: Default / Custom with the changed fields marked, Save as My metric, the operator select, "within N sessions",
   All / Any / At least n bounded by the active count. Changed (report 9.2): entries, synonyms and defaults come from
   the catalog; invalid input is refused in place with the field and the allowed range, never rounded or ignored;
   `between` with value > value2 is refused; each card shows its pass count from the run ("m of U pass" when exhaustive,
   else "m of n evaluated"). */
import { esc, nf } from './format.ts';
import { COLORS, IC, ico } from './icons.ts';
import { activeCards, ctx, entryOf, S, ui } from './state.ts';
import { defaultParams, depthHint, flowBudget, flowSessions, isDefP, isFlowType, optionText, paramError, rangeText, type Entry } from './entries.ts';
import { flowControlHtml, paramFieldValue, paramTitle } from './param-fields.ts';
import { cardErrors, cardName, condText, defaultOffered, displayUnit, isCustom, optOf, paramSummary, type Card } from './forms.ts';
import { confirmDialog, openSaveMetric, toast, toastAction } from './dialogs.ts';
import { MY, openAddCondition } from './add-condition.ts';
import { spin } from '../../terminal/src/ui/spin.ts';
import { levelAsOfText, sideOf, T } from './texts.ts';
import { levelAtFlowDate } from './cell-text.ts';
import { ApiFailure } from './api/types.ts';
import { layoutHooks, wide } from './layout/prefs.ts';
import { afterPress } from './press.ts';
import { keepField } from './keep-field.ts';
import { pageCardOf, screenedCards } from './run.ts';

const $ = (id: string) => document.getElementById(id);
const withinMax = () => ctx.catalog?.limits.find(l => l.name === 'within_max')?.value ?? 130;
const maxConds = () => ctx.catalog?.limits.find(l => l.name === 'max_conditions');
/* EXEC-SCREENER-V21 (three-panel v21, reference layout.js 12-21, 162-221, 384-395): on a wide screen the builder is a
   pane with tabs (Conditions · My metrics · Saved), each condition is a compact row that opens to edit on a click, an
   "Add indicator" tile and a + button open the indicator window, and the header toggle collapses the pane to a rail. */
type BTab = 'cond' | 'metrics' | 'saved';
let btab: BTab = 'cond';
/** the condition rows opened to edit (wide layout); a row with an error stays open (CSS) */
const openRows = new Set<string>();
/** a condition's colour: its place on the page; a card of the screened definition (the table's columns, the preview:
    run.ts screenedCards) takes the colour of the page card it is (pageCardOf), else its place in that definition.
    Never by id alone: a preset reuses ids (QA M1, ERRORS M358). */
export const colorOf = (c: Card) => {
  let i = S.cards.indexOf(c);
  if (i < 0) { const p = pageCardOf(c); i = p ? S.cards.indexOf(p) : screenedCards(true).indexOf(c) }
  return COLORS[Math.max(0, i) % COLORS.length];
};

/** the card's pass count from the run that answers the current definition (report 9.2, 6.10) */
function passText(c: Card): { txt: string; title: string; zero: boolean } | null {
  const run = ctx.R?.run; if (!run || ctx.stale || !c.on) return null;
  const s = run.conditions.find(x => x.id === c.id); if (!s) return null;
  if (s.exhaustive) return { txt:`${nf(s.passed)} of ${nf(run.universe.eligible)} pass`, title:`${nf(s.passed)} of the ${nf(run.universe.eligible)} stocks in the universe pass${s.na ? `; ${nf(s.na)} n/a` : ''}.`, zero:s.passed === 0 };
  return { txt:`${nf(s.passed)} of ${nf(s.evaluated)} evaluated`, title:'Counted on the tickers that can still match or be near; run exhaustively for the full count.', zero:s.passed === 0 };
}

function condRow(c: Card): string {
  const e = entryOf(c), col = colorOf(c), errs = S.errors[c.id] || {};
  // a pattern's side beside its name, and in the name's tooltip (QA of unit C item 2)
  const side = sideOf(e), sideTag = side ? `<span class="pill qside s-${side.side}" data-side="${c.id}" title="${esc(side.title)}">${esc(side.word)}</span>` : '';
  const head = `<div class="mrow"><i class="cdot" style="background:${col}"></i><b data-nm="${c.id}" title="${esc([side?.title, e?.desc].filter(Boolean).join(' '))}">${esc(cardName(e, c))}</b>${sideTag}<span class="sw" title="Enable / disable"><input type="checkbox" data-c="${c.id}" data-k="on" ${c.on ? 'checked' : ''} aria-label="Enable condition"><span></span></span><button class="iconbtn sm mx" data-del="${c.id}" title="Remove condition" aria-label="Remove condition">${ico(IC.x, 's')}</button></div>`;
  const review = c.review?.length ? `<span class="pill t-warning" title="${esc(c.review.join('\n'))}">Needs review</span>` : '';
  const pt = passText(c), pass = `<div class="note cnt" data-pass="${c.id}" ${pt ? `title="${esc(pt.title)}"` : ''} ${pt?.zero ? 'data-z="1"' : ''}>${pt ? esc(pt.txt) : ''}</div>`
    + (ctx.refused?.id === c.id ? `<span class="ferr" role="alert" data-refused="${c.id}">${esc(ctx.refused.message)}</span>` : '');
  const x = openRows.has(c.id) ? 'x' : '', tip = wide() ? ` tabindex="0" role="group" aria-label="${esc(cardName(e, c))}${x ? '' : ', press Enter to edit'}"${x ? '' : ' title="Click to edit"'}` : '';
  // a raw card, and a card with a universal operator (P3: set and changed in the Add a condition window), show their rule
  // an operator card says where it is changed (QA5 D7): in the Add a condition window, as a new card
  const opNote = c.op && e ? `<div class="note" data-opnote="${c.id}">${esc(T.operatorCardNote)}</div>` : '';
  // the close against a flow price level: both read at the broker data date (P10 a)
  const asOf = levelAtFlowDate(c, e) ? `<div class="note" data-asof="${c.id}">${esc(levelAsOfText(ctx.catalog?.data))}</div>` : '';
  if (!e || c.raw || c.op) return `<div class="mc ${c.on ? '' : 'off'} ${x}" data-card="${c.id}"${tip}>${head}<div class="note msum" data-sum="${c.id}">${esc(condText(e, c))}</div>${asOf}${opNote}${review}${pass}</div>`;
  const o = optOf(e, c), cus = isCustom(e, c) || S.open.has(c.id);
  const u = displayUnit(o?.unit);
  const err = (k: string) => errs[k] ? `<span class="ferr" role="alert">${esc(errs[k])}</span>` : '';
  const inv = (k: string) => errs[k] ? 'aria-invalid="true"' : '';
  const vals = o && o.value === 'input' ? `<div class="vrow"><input class="inp" type="number" step="any" data-c="${c.id}" data-k="value" value="${c.value}" ${inv('value')} aria-label="${o.between ? 'From' : 'Value'}">${o.between ? `<span class="unit">–</span><input class="inp" type="number" step="any" data-c="${c.id}" data-k="value2" value="${c.value2}" ${inv('value2')} aria-label="To">` : ''}${u ? `<span class="unit">${esc(u)}</span>` : ''}</div>${err('value')}${err('value2')}` : '';
  // a flow indicator's "within": at most the broker sessions held, with about how many the setup leaves as a hint (K1:
  // the worker judges the setup, its refusal shown on this card)
  const S0 = e.flow ? flowSessions(e) : null, wmax = S0 == null ? withinMax() : Math.min(withinMax(), S0), wh = e.flow ? depthHint(flowBudget(e, c.params)) : '';
  const within = o?.within ? `<div class="vrow"><span class="unit">within</span><input class="inp" type="number" min="1" max="${wmax}" step="1" data-c="${c.id}" data-k="within" value="${c.within}" ${inv('within')} aria-label="Within sessions"${wh ? ` title="${esc(wh)}"` : ''}><span class="unit">sessions${wh ? ` · ${esc(wh)}` : ''}</span></div>${err('within')}` : '';
  const pf = (p: Entry['params'][number], second = false) => {
    const v = second ? c.second[p.key] : c.params[p.key], k = (second ? '2.' : '') + p.key, attr = second ? 'data-p2' : 'data-p';
    // a flow indicator's list, anchor date or broker codes (param-fields.ts)
    const field = isFlowType(p) ? flowControlHtml(p, v, `data-c="${c.id}" ${attr}="${esc(p.key)}"`, (second ? '2nd ' : '') + (p.label || p.key), errs[k] || paramTitle(p, p.default), !!errs[k])
      : p.options ? `<select class="sel" data-c="${c.id}" ${attr}="${p.key}">${p.options.map(x => `<option value="${esc(x)}" ${String(x) === String(v) ? 'selected' : ''}>${esc(optionText(p, x))}</option>`).join('')}</select>`
      : p.type === 'boolean' ? `<select class="sel" data-c="${c.id}" ${attr}="${p.key}"><option value="true" ${v === true ? 'selected' : ''}>true</option><option value="false" ${v === false ? 'selected' : ''}>false</option></select>`
      : `<input class="inp" type="number" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="${p.step ?? (p.integer ? 1 : 'any')}" data-c="${c.id}" ${attr}="${p.key}" value="${esc(v)}" ${inv(k)} title="${esc(rangeText(p))}">`;
    const tag = p.type === 'multi' ? 'div' : 'label';            // a checkbox group is not one labelled control
    return `<${tag} class="pf ${isDefP(p, v) ? '' : 'chg'}" data-pf="${c.id}|${k}"><span>${esc((second ? '2nd ' : '') + (p.label || p.key))}</span>${field}<small>${errs[k] ? `<b class="down">${esc(errs[k])}</b>` : `${defaultOffered(e) ? 'default' : 'opens at'} ${esc(optionText(p, p.default))}`}</small></${tag}>`;
  };
  const twoLines = o && (o.form === 'state_instance' || o.form === 'event_instance');
  // P17 consequence (catalog default_offered false, I43): no Default chip, the card is Custom with its reason
  const mode = !e.params.length ? `<span class="note">No parameters</span>`
    : !defaultOffered(e) ? `<span class="seg sm mseg"><button class="on" data-segc="${c.id}" title="${esc(T.noDefault)}">Custom</button></span>`
    : `<span class="seg sm mseg"><button class="${cus ? '' : 'on'}" data-segd="${c.id}" title="Use the standard parameters (the defaults shown under each field)">Default</button><button class="${cus ? 'on' : ''}" data-segc="${c.id}" title="Set your own parameters">Custom</button></span>`;
  const grid = e.params.length && (cus || twoLines) ? `<div class="pgrid">${e.params.map(p => pf(p)).join('')}${twoLines ? e.params.map(p => pf(p, true)).join('') : ''}</div><div class="mrow"><span class="pbadge my" data-pm="${c.id}" ${c.metric ? '' : 'hidden'}>★ ${esc(c.metric?.name || '')}</span><button class="link" data-savem="${c.id}">${ico(IC.star, 's')}Save as My metric</button></div>` : '';
  const ops = `<select class="sel" data-c="${c.id}" data-k="op" aria-label="Condition">${e.opts.map(x => `<option value="${esc(x.key)}" ${x.key === c.opt ? 'selected' : ''} ${x.disabled ? `disabled title="${esc(x.disabled)}"` : ''}>${esc(x.label)}${x.disabled ? ' — not offered' : ''}</option>`).join('')}</select>${err('op')}`;
  return `<div class="mc ${c.on ? '' : 'off'} ${cus ? 'cus' : ''} ${x}" data-card="${c.id}"${tip}>${head}
    <div class="note msum" data-sum="${c.id}">${esc(condText(e, c))}</div>${asOf}${review}
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
  for (const c of S.cards) { const el = document.querySelector(`[data-pass="${c.id}"]`) as HTMLElement | null; if (el) { const t = passText(c); el.textContent = t?.txt || ''; el.title = t?.title || ''; t?.zero ? el.dataset.z = '1' : delete el.dataset.z } paramUI(c) }
  const s = $('bSum'); if (s) s.textContent = bSum();
}

const quick = () => {
  const ids = ['I13', 'I15', 'I06', 'I09', 'I27', 'I37'].filter(k => ctx.byKey.has(k));
  const metric = ['hi52', 'return_rank', 'volspike', 'adv20_idr'].find(k => ctx.byKey.get(k)?.available);
  const bandar = ['bandar', 'B1'].find(k => ctx.byKey.has(k));
  return [...ids, ...(metric ? [metric] : []), ...(bandar ? [bandar] : [])].map(k => ctx.byKey.get(k)!);
};
export function renderConds() {
  if (afterPress('conds', renderConds)) return;   // never under a pressed pointer (press.ts, ERRORS M357)
  const el = $('condHost'), card = $('cardC'); if (!el || !card) return;
  const sl = $('condList')?.scrollLeft || 0, a = activeCards().length, n = S.cards.length;
  const lim = maxConds();
  const ready = !!ctx.catalog, W = wide();
  if (W) S.bOpen = true;                       // the pane always shows its body on a wide screen (it collapses to a rail)
  const tgl = W ? `<button class="tgl" data-act="btoggle" aria-expanded="true" aria-controls="cardC" title="Collapse the screen builder">`
    : `<button class="tgl ${S.bOpen ? '' : 'closed'}" data-act="btoggle" aria-expanded="${S.bOpen}">`;
  keepField(el, () => {   // typed text survives the redraw (keep-field.ts, ERRORS M373)
    el.innerHTML = `<div class="builder-h">${tgl}${ico(IC.chev, 's')}Screen builder <small id="bSum">${bSum()}</small></button><span class="sp"></span>
        <div class="btabs" role="tablist" aria-label="Screen builder sections">${btabsHtml()}</div>
        ${n > 1 ? `<span class="logic">Match <span class="seg sm" role="radiogroup" aria-label="Match"><button class="${S.logic === 'all' ? 'on' : ''}" data-logic="all" role="radio" aria-checked="${S.logic === 'all'}">All</button><button class="${S.logic === 'any' ? 'on' : ''}" data-logic="any" role="radio" aria-checked="${S.logic === 'any'}">Any</button><button class="${S.logic === 'at_least' ? 'on' : ''}" data-logic="at_least" role="radio" aria-checked="${S.logic === 'at_least'}">At least</button></span>${S.logic === 'at_least' ? `<input class="inp" type="number" min="1" max="${Math.max(1, a)}" step="1" data-s="atLeast" value="${S.atLeast}" aria-label="At least N">` : ''}<span>of ${a} active</span></span>` : ''}
        ${n ? `<button class="btn sm ghost" data-act="clearconds">Clear</button>` : ''}</div>
      <div class="bt-view" id="btView" role="tabpanel" aria-label="${btab === 'metrics' ? 'My metrics' : 'Saved screens'}">${btab === 'cond' ? '' : btView()}</div>
      ${S.bOpen ? `<div class="builder-b" role="tabpanel" aria-label="Conditions">${!ready ? `<div class="sbox">${spin(T.loadingIndicators)}</div>` : `<div class="adder"><button type="button" class="searchbox adder-open" data-act="addwin" aria-haspopup="dialog" title="Add a condition (Alt+A or /)">${ico(IC.search, 's')}<span class="ph">${W ? 'Search indicators to add' : `Add a condition — search ${ctx.catalog!.indicators.length} indicators: “RSI”, “Stochastic”, “VWAP”, “Supertrend”, or “breakout”…`}</span><kbd>/</kbd></button><button type="button" class="bh-add" data-act="addwin" aria-haspopup="dialog" title="Add a condition (Alt+A)" aria-label="Add a condition">${ico(IC.plus)}</button></div>`}
        ${lim && a > lim.value ? `<div class="note down" role="alert">${esc(lim.rule)}: switch off or remove ${a - lim.value} condition${a - lim.value > 1 ? 's' : ''}.</div>` : ''}
        ${n ? `<div class="strip" id="condList">${S.cards.map(condRow).join('')}<button class="mc madd" data-act="addwin" aria-haspopup="dialog">${ico(IC.plus)}<span>Add indicator</span></button></div>`
          : ready ? `<div class="bempty"><span class="muted">No conditions yet. Start from a preset, or open Add a condition:</span><div class="qrail">${quick().map(e => `<button class="btn sm" data-quick="${esc(e.key)}" ${e.available ? '' : `disabled title="${esc(e.reason || '')}"`}>${ico(IC.plus, 's')}${esc(e.short === e.key ? e.label : e.label.length > 18 ? e.short : e.label)}</button>`).join('')}</div></div>` : ''}</div>` : ''}`;
  });
  card.classList.toggle('bt-alt', W && btab !== 'cond');
  const cl = $('condList'); if (cl) cl.scrollLeft = sl;
  layoutHooks.afterConds();
}

/* ---- builder tabs: Conditions · My metrics · Saved (reference layout.js 179-221), from the page's own lists ---- */
const dateText = (iso: string | null | undefined) => { if (!iso) return ''; const d = new Date(iso); return isNaN(+d) ? '' : d.toLocaleDateString('en-GB', { day:'numeric', month:'short', year:'numeric' }) };
function btabsHtml(): string {
  const nc = activeCards().length, nm = ctx.metrics?.length ?? 0, ns = ctx.saved?.length ?? 0;
  const t = (k: BTab, l: string, n: number) => `<button type="button" role="tab" data-btab="${k}" aria-selected="${btab === k}" tabindex="${btab === k ? 0 : -1}">${l}<span class="n">${n}</span></button>`;
  return t('cond', 'Conditions', nc) + t('metrics', 'My metrics', nm) + t('saved', 'Saved', ns);
}
function btView(): string {
  if (btab === 'metrics') {
    const ms = ctx.metrics;
    if (ms == null) return `<p class="bt-note">${spin('Loading your metrics')}</p>`;
    return ms.length ? `<p class="bt-note">Indicators saved with your own parameters. Add one as a condition.</p>` + ms.map(m => `<div class="bt-item"><b title="${esc(m.name)}">${esc(m.name)}</b><small>${esc(m.updated_at ? 'Saved ' + dateText(m.updated_at) : 'Saved metric')}</small><button type="button" class="btn sm" data-addmetric="${esc(m.item_id)}" aria-label="Add ${esc(m.name)} as a condition">Add</button></div>`).join('')
      : `<p class="bt-note">No saved metrics yet. Change a condition's parameters, then use Save as My metric on its card.</p>`;
  }
  const sv = ctx.saved, cur = S.source?.kind === 'saved' ? S.source.item_id : null;
  if (sv == null) return `<p class="bt-note">${spin('Loading your screens')}</p>`;
  return sv.length ? `<p class="bt-note">Your saved screens. Opening one replaces the current conditions.</p>` + sv.map(x => {
    const def = (x.definition as { definition?: { conditions?: { enabled?: boolean }[] } }).definition;
    const k = def?.conditions?.filter(c => c.enabled !== false).length ?? 0, on = x.item_id === cur;
    return `<div class="bt-item ${on ? 'cur' : ''}"><b title="${esc(x.name)}">${esc(x.name)}</b><small>${k} condition${k === 1 ? '' : 's'}${x.updated_at ? ' · saved ' + esc(dateText(x.updated_at)) : ''}${x.needs_review?.length ? ' · needs review' : ''}</small><button type="button" class="btn sm" data-opensaved="${esc(x.item_id)}" ${on ? 'disabled title="Open now"' : `aria-label="Open ${esc(x.name)}"`}>Open</button></div>`;
  }).join('') : `<p class="bt-note">No saved screens yet. Build a screen, then use Save screen at the top of the page.</p>`;
}
function setBtab(k: BTab) {
  btab = k; renderConds();
  ($('cardC')?.querySelector(`[data-btab="${k}"]`) as HTMLElement | null)?.focus();
  const c = $('cardC'); if (c) c.scrollTop = 0;
}
/** a click on a compact condition row (not on one of its controls) opens it to edit, or closes it (wide layout) */
export function toggleRow(id: string) {
  if (!S.cards.some(c => c.id === id)) return;
  openRows.has(id) ? openRows.delete(id) : openRows.add(id);
  renderConds();
  ($('condList')?.querySelector(`[data-card="${CSS.escape(id)}"]`) as HTMLElement | null)?.focus?.();
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
  ui.markDirty(); ui.refresh('conds'); toast(`${e.label} back to default (${e.params.map(p => optionText(p, p.default)).join(', ')})`);
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
  if (d.segd) { const c = S.cards.find(x => x.id === d.segd)!; S.open.delete(c.id); const e = entryOf(c); if (e && isCustom(e, c)) resetParams(c); else renderConds(); return true }
  if (d.segc) { S.open.add(d.segc); renderConds(); return true }
  if (d.savem) { const c = S.cards.find(x => x.id === d.savem); if (c) openSaveMetric(c); return true }
  if (d.quick) { const e = ctx.byKey.get(d.quick); openAddCondition(e ? e.label : ''); return true }   // the window, searched for it
  /* audit U24: a removed condition says so and can be brought back, as in the Add a condition window */
  if (d.del) { const at = S.cards.findIndex(c => c.id === d.del), gone = S.cards[at];
    S.cards = S.cards.filter(c => c.id !== d.del); delete S.errors[d.del]; openRows.delete(d.del); ui.markDirty(); ui.refresh('conds');
    if (gone) { const name = cardName(entryOf(gone) ?? undefined, gone);
      toastAction(`${name} removed`, 'Undo', () => { if (S.cards.some(c => c.id === gone.id)) return; S.cards.splice(Math.min(at, S.cards.length), 0, gone); ui.markDirty(); ui.refresh('conds'); toast(`${name} restored`) }) }
    return true }
  if (d.logic) { S.logic = d.logic as typeof S.logic; ui.markDirty(); ui.refresh('conds'); return true }
  if (d.btab) { setBtab(d.btab as BTab); return true }
  if (d.addmetric) { openAddCondition('', MY); return true }                     // the window, on My metrics
  if (d.opensaved) { btab = 'cond'; ui.openSource('s:' + d.opensaved); return true }
  switch (d.act) {
    case 'addwin': openAddCondition(); return true;                              // the one way to add (EXEC-SCREENER-ADD)
    case 'btoggle': if (layoutHooks.collapseBuilder()) return true; S.bOpen = !S.bOpen; renderConds(); return true;
    case 'clearconds': S.cards = []; S.errors = {}; openRows.clear(); ui.markDirty(); toast('Conditions cleared'); ui.refresh('conds'); return true;
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
    const v = paramFieldValue(p, el);
    const errKey = (d.p2 ? '2.' : '') + key, msg = paramError(p, v as any);
    const errs = S.errors[c.id] ||= {};
    if (msg) { errs[errKey] = `${p.label || p.key}: ${msg}`; renderConds(); ui.schedule(); return true }
    delete errs[errKey];
    const target = d.p2 ? c.second : c.params;
    if (target[key] === v) { checkCard(c); return true }
    target[key] = v as any; if (!d.p2) syncMetric(c);
    // a choice (a select, a list's box) redraws the card: its lines, conditions and limits may follow it
    checkCard(c); ui.markDirty(); ui.refresh(el.tagName === 'SELECT' || (el as HTMLInputElement).type === 'checkbox' || isFlowType(p) ? 'conds' : 'conds-light'); return true;
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

export { paramSummary };
