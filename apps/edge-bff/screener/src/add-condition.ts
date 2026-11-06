/* EXEC-SCREENER-ADD (user 2026-11-06: "saya mau cukup ada screenshot B saja, tapi di screenshot B tanpa ada tulisan open
   in detailed browser"): the one way to add a condition, the "Add a condition" window of the v21 reference (layout.js
   636-763 the window, 1004-1101 the rule and the "on the screen" test, 1206-1293 the picker), without the reference's
   "Open the detailed browser" button: the detailed Indicators window is gone from the page.
   Every door opens this window: the page action "Add indicator", Alt+A, "/", the builder's search box, its "+" and
   "Add indicator" tile, the quick chips of an empty builder (searched for that indicator) and the Add of the My metrics
   tab (opened on My metrics).
   Everything is read from the catalog: the indicators, their groups and counts, the conditions an indicator offers (its
   test forms: the card's own list), the threshold fields a condition needs with their defaults, units and limits
   (within_max), and why an indicator has no data. Validation is the card's (forms.ts cardErrors). A row is "on the
   screen" when a card produces the same wire test (forms.ts toWire), never by id (ERRORS M358). Adding is an edit like
   any other: a new card, the table out of date, no run until Screen now. The timeframe is shown as in the reference
   but cannot be chosen: the data is daily (product decisions 2-3; user 2026-11-06 "tetap di show saja, tapi dibuat
   unclickable"); 5m to 4h are greyed with their reason.
   The indicator's parameters (Length, Source, ...) are set in the row too, as on the card (user 2026-11-06, option A of
   the audit: "Seharusnya ini cukup konsisten"): the fields, their limits and their checks are the catalog's and the
   card's (entries.ts paramError), and the card added carries them. A condition on two lines of the indicator (a cross
   of two moving averages) shows the second line's parameters too ("2nd"), as the card does. */
import type { ConditionDef, ParamValue, SavedItem } from './core/contract.ts';
import { esc } from './format.ts';
import { IC, ico } from './icons.ts';
import { canonical, ctx, entryOf, S, ui } from './state.ts';
import { defaultParams, GHEAD, GORD, matches, optionText, paramError, rangeText, type Entry, type EntryParam, type Opt } from './entries.ts';
import { cardErrors, displayUnit, fromWire, newCard, newCardId, optOf, toWire, type Card } from './forms.ts';
import { closeDialog, dialog, toast, toastAction } from './dialogs.ts';

export const MY = 'My metrics', ON_SCREEN = '__on', ALL = 'All';
export type Sort = 'group' | 'az' | 'za';
const TIMEFRAMES = ['5m', '15m', '1h', '4h', 'Daily'];
export const NO_INTRADAY = 'No data yet: intraday bars are not in the market database.';

/* ---- the rule chosen per indicator before adding (the reference's RULE); defaults from the catalog --------------- */
type Params = Record<string, ParamValue>;
export interface Rule { opt: string; value: number | ''; value2: number | ''; within: number | ''; params: Params; second?: Params }
const RULE = new Map<string, Rule>();
export function ruleOf(e: Entry): Rule {
  let r = RULE.get(e.key);
  if (!r) { r = { opt:e.def.opt, value:e.def.value, value2:e.def.value2, within:e.def.within, params:defaultParams(e) as Params }; RULE.set(e.key, r) }
  return r;
}
/** tests and a new catalog: forget the rules chosen so far */
export function resetRules() { RULE.clear() }
/** a new rule option, with the value fields it needs filled from the catalog default when empty (as the card does) */
export function setOpt(e: Entry, opt: string) {
  const r = ruleOf(e);
  if (r.opt !== opt) delete r.second;             // the second line's defaults belong to the condition (its form's defaults)
  r.opt = opt;
  const o = e.opts.find(x => x.key === opt);
  if (o?.value === 'input' && r.value === '') r.value = e.def.value;
  if (o?.between && r.value2 === '') r.value2 = e.def.value2 === '' ? (typeof r.value === 'number' ? r.value : 0) : e.def.value2;
}
const withinMax = () => ctx.catalog?.limits.find(l => l.name === 'within_max')?.value ?? 130;
/** the card this rule adds (fresh id among the page's cards) */
export function cardOfRule(e: Entry, r = ruleOf(e)): Card {
  return newCard(e, S.cards.map(x => x.id), { opt:r.opt, value:r.value, value2:r.value2, within:r.within, params:{ ...r.params } as Card['params'], ...(r.second ? { second:{ ...r.second } as Card['second'] } : {}) });
}
/** the condition reads two lines of the indicator, the second with its own parameters (as the card shows "2nd") */
const twoLines = (o: Opt | undefined) => !!o && (o.form === 'state_instance' || o.form === 'event_instance');
/** the rule's problems, field -> message: the card's own validation (forms.ts cardErrors) and each parameter's
    (entries.ts paramError, the card's check), keyed 'p.<key>' and 'p2.<key>' */
export function ruleErrors(e: Entry): Record<string, string> {
  const c = cardOfRule(e), out = cardErrors(e, c, withinMax());
  const lines: [string, Params][] = [['p', c.params as Params], ...(twoLines(optOf(e, c)) ? [['p2', c.second as Params] as [string, Params]] : [])];
  for (const [k, vals] of lines) for (const p of e.params) {
    const msg = paramError(p, vals[p.key]);
    if (msg) out[`${k}.${p.key}`] = `${k === 'p2' ? '2nd ' : ''}${p.label || p.key}: ${msg}`;
  }
  return out;
}

/* ---- rows ------------------------------------------------------------------------------------------------------ */
export interface AddItem {
  kind: 'ind' | 'metric'; key: string; label: string; group: string; sub: string; ok: boolean; why: string | null;
  entry: Entry | null; metric: SavedItem | null;
}
const paramsText = (e: Entry) => e.params.length ? e.params.map(p => `${p.label || p.key} ${optionText(p, p.default)}`).join(' · ') : 'No parameters';
/** a saved metric's card: its own test on its catalog entry (null when the entry is not in this catalog) */
function metricCard(m: SavedItem): { c: Card; e: Entry | null } | null {
  const test = (m.definition as { test?: unknown }).test; if (!test) return null;
  const c = fromWire({ id:newCardId(S.cards.map(x => x.id)), enabled:true, test } as ConditionDef, ctx.byKey);
  return { c, e:c.entry ? ctx.byKey.get(c.entry) ?? null : null };
}
function itemsAll(): AddItem[] {
  const ms: AddItem[] = (ctx.metrics || []).map(m => {
    const x = metricCard(m), ok = !!x?.e?.available;
    return { kind:'metric', key:'m:' + m.item_id, label:m.name, group:MY, sub:'Saved parameters', ok, why:ok ? null : (x?.e?.reason || 'Its indicator is not in this catalog.'), entry:x?.e ?? null, metric:m };
  });
  const es: AddItem[] = ctx.entries.map(e => ({ kind:'ind', key:e.key, label:e.label, group:e.group, sub:e.available ? paramsText(e) : (e.reason || 'No data'), ok:e.available, why:e.available ? null : e.reason, entry:e, metric:null }));
  return [...ms, ...es];
}
/** the wire test a row adds, canonical; '' when it cannot be built */
export function itemSig(it: AddItem): string {
  try {
    if (it.kind === 'metric') return it.metric ? canonical((it.metric.definition as { test?: unknown }).test) : '';
    return it.entry ? canonical(toWire(it.entry, cardOfRule(it.entry)).test) : '';
  } catch { return '' }
}
/** the wire tests of the page's cards (switched off ones too: they are on the screen) */
export function screenSigs(): Set<string> {
  const out = new Set<string>();
  for (const c of S.cards) { try { out.add(canonical(toWire(entryOf(c), c).test)) } catch { /* a card the page cannot write */ } }
  return out;
}
/** the catalog's groups in the page's order, with their counts (counts ignore the search) */
export function groupsOf(): { g: string; label: string; n: number }[] {
  const seen = [...new Set(ctx.entries.map(e => e.group))];
  const order = [...GORD.filter(g => seen.includes(g)), ...seen.filter(g => !GORD.includes(g))];
  return order.map(g => ({ g, label:GHEAD(g), n:ctx.entries.filter(e => e.group === g).length }));
}
/** the rows shown: searched, filtered by the left panel's choice (On the screen, My metrics, or every indicator),
    sorted (by group in the catalog's order, or by name), the ones without data last */
export function listItems(q: string, g: string, sort: Sort): AddItem[] {
  const n = q.trim().toLowerCase(), on = screenSigs();
  let items = itemsAll().filter(it => !n || (it.entry && it.kind === 'ind' ? matches(it.entry, n) : it.label.toLowerCase().includes(n)));
  if (g === ON_SCREEN) items = items.filter(it => it.ok && on.has(itemSig(it)));
  else if (g === MY) items = items.filter(it => it.kind === 'metric');
  else items = items.filter(it => it.kind === 'ind');
  const gi = new Map(groupsOf().map((x, i) => [x.g, i])), okFirst = (a: AddItem, b: AddItem) => Number(b.ok) - Number(a.ok);
  // a stable sort: inside a group the catalog's own order stays
  items.sort((a, b) => sort === 'group' ? ((gi.get(a.group) ?? 99) - (gi.get(b.group) ?? 99)) || okFirst(a, b)
    : okFirst(a, b) || (sort === 'za' ? b.label.localeCompare(a.label) : a.label.localeCompare(b.label)));
  return items;
}

/* ---- add and remove -------------------------------------------------------------------------------------------- */
/** add the row's condition: a new card (pending edit, no run); false with the reason when the rule is not valid */
export function addItem(it: AddItem): { ok: boolean; message: string } {
  if (!it.ok) return { ok:false, message:`${it.label}: ${it.why || 'no data'}` };
  if (it.kind === 'metric') {
    const x = it.metric && metricCard(it.metric); if (!x?.e) return { ok:false, message:`${it.label} cannot be added: its indicator is not in this catalog.` };
    x.c.metric = { item_id:it.metric!.item_id, name:it.label, params:{ ...x.c.params } };
    S.cards.push(x.c);
  } else {
    const e = it.entry!, er = Object.values(ruleErrors(e));
    if (er.length) return { ok:false, message:`${e.label}: ${er[0]}` };
    S.cards.push(cardOfRule(e));
  }
  S.bOpen = true; ui.markDirty(); ui.refresh('conds');
  return { ok:true, message:`${it.label} added${it.kind === 'ind' ? ' · ' + (it.entry!.opts.find(o => o.key === ruleOf(it.entry!).opt)?.label || '') : ''}` };
}
/** remove every card that adds this row's test; returns them with their places (for Undo) */
export function removeItem(it: AddItem): { at: number; c: Card }[] {
  const sig = itemSig(it); if (!sig) return [];
  const gone: { at: number; c: Card }[] = [];
  S.cards.forEach((c, at) => { try { if (canonical(toWire(entryOf(c), c).test) === sig) gone.push({ at, c }) } catch { /* skip */ } });
  if (!gone.length) return gone;
  S.cards = S.cards.filter(c => !gone.some(x => x.c === c));
  for (const { c } of gone) delete S.errors[c.id];
  ui.markDirty(); ui.refresh('conds');
  return gone;
}
/** put removed cards back where they were (Undo) */
export function restore(gone: { at: number; c: Card }[]) {
  for (const { at, c } of gone) {
    if (S.cards.some(x => x.id === c.id)) c.id = newCardId(S.cards.map(x => x.id));
    S.cards.splice(Math.min(at, S.cards.length), 0, c);
  }
  ui.markDirty(); ui.refresh('conds');
}

/* ---- the window -------------------------------------------------------------------------------------------------- */
const FIRST_ROWS = 20;
const W = { q:'', g:ALL as string, sort:'group' as Sort, act:0, items:[] as AddItem[], added:[] as boolean[], spyLock:0, rest:undefined as ReturnType<typeof setTimeout> | undefined, restHtml:'' };
let root: HTMLElement | null = null, drawing = false;
const $q = <T extends HTMLElement>(sel: string) => root?.querySelector<T>(sel) ?? null;

const tfHtml = () => `<span class="tf-seg tf-add" role="img" aria-label="Timeframe: Daily. 5m, 15m, 1h and 4h have no data yet.">${TIMEFRAMES.map(t => t === 'Daily'
  ? `<span class="on">Daily</span>` : `<span class="na" title="${esc(NO_INTRADAY)}">${t}</span>`).join('')}</span>`;
interface Field { f: 'value' | 'value2' | 'within'; lead: string; label: string; unit: string }
function fieldsOf(o: Opt | undefined): Field[] {
  const u = displayUnit(o?.unit), L: Field[] = [];
  if (o?.value === 'input') { if (o.between) L.push({ f:'value', lead:'from', label:'From', unit:u }, { f:'value2', lead:'to', label:'To', unit:u }); else L.push({ f:'value', lead:'value', label:'Value', unit:u }) }
  if (o?.within) L.push({ f:'within', lead:'within', label:'Within', unit:'sessions' });
  return L;
}
const fdef = (e: Entry, f: Field['f']) => f === 'value2' ? (e.def.value2 === '' ? e.def.value : e.def.value2) : f === 'within' ? e.def.within : e.def.value;
function ruleHtml(it: AddItem, i: number): [string, string] {
  if (it.kind === 'metric') {
    const x = it.metric && metricCard(it.metric), o = x?.e ? optOf(x.e, x.c) : undefined;
    return [`<span class="rr-fixed" title="Saved with this metric">${esc(o?.label || 'Saved condition')}</span>`, '<span class="rr-none">—</span>'];
  }
  const e = it.entry!, r = ruleOf(e), o = e.opts.find(x => x.key === r.opt), er = ruleErrors(e);
  const sel = `<select class="sel" data-af="opt" data-ai="${i}" aria-label="Condition for ${esc(e.label)}"${er.op ? ` aria-invalid="true" title="${esc(er.op)}"` : ''}>${e.opts.map(x => `<option value="${esc(x.key)}" ${x.key === r.opt ? 'selected' : ''} ${x.disabled ? `disabled title="${esc(x.disabled)}"` : ''}>${esc(x.label)}${x.disabled ? ' — not offered' : ''}</option>`).join('')}</select>`;
  const L = fieldsOf(o);
  const thr = L.length ? L.map(l => {
    const v = r[l.f], d = fdef(e, l.f), ch = String(v) !== String(d);
    return `<span class="ln thr"><span class="lead">${l.lead}</span><input class="inp${ch ? ' chg' : ''}" type="number" step="${l.f === 'within' ? 1 : 'any'}"${l.f === 'within' ? ` min="1" max="${withinMax()}"` : ''} data-af="${l.f}" data-ai="${i}" value="${esc(v)}" aria-label="${esc(l.label)}${l.unit ? ` (${esc(l.unit)})` : ''} for ${esc(e.label)}"${er[l.f] ? ` aria-invalid="true" title="${esc(er[l.f])}"` : ''}><span class="unit">${esc(l.unit)}<small>${ch ? 'custom · ' : ''}default ${esc(d)}</small></span></span>`;
  }).join('') : '';
  const set = (e.params.length ? paramsHtml(e, i) : '') + thr;
  return [`<span class="rr qs">${sel}</span>`, `<span class="rr qt">${set || '<span class="rr-none">—</span>'}</span>`];
}
/** a parameter field of a row: the card's field (a select for options and true/false, else a number with the
    catalog's limits), blue when it differs from its default */
function paramField(e: Entry, p: EntryParam, i: number, v: ParamValue | undefined, def: ParamValue | undefined, second: boolean, err: string | undefined): string {
  const attr = second ? 'data-ap2' : 'data-ap', name = `${second ? '2nd ' : ''}${p.label || p.key}`;
  const ch = String(v) !== String(def), common = `${attr}="${esc(p.key)}" data-ai="${i}" aria-label="${esc(name)} of ${esc(e.label)}"${err ? ` aria-invalid="true" title="${esc(err)}"` : ` title="${esc(`${rangeText(p) ? rangeText(p) + ' · ' : ''}default ${optionText(p, def as ParamValue)}`)}"`}`;
  const field = p.options ? `<select class="sel" ${common}>${p.options.map(x => `<option value="${esc(x)}" ${String(x) === String(v) ? 'selected' : ''}>${esc(optionText(p, x))}</option>`).join('')}</select>`
    : p.type === 'boolean' ? `<select class="sel" ${common}><option value="true" ${v === true ? 'selected' : ''}>true</option><option value="false" ${v === false ? 'selected' : ''}>false</option></select>`
    : `<input class="inp" type="number" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="${p.step ?? (p.integer ? 1 : 'any')}" value="${esc(Number.isFinite(v as number) ? v : '')}" ${common}>`;
  return `<label class="ln qp${ch ? ' chg' : ''}"><span class="lead" title="${esc(name)}">${esc(name)}</span>${field}</label>`;
}
/** the row's parameters, editable (option A, user 2026-11-06), one per line in the settings column with the threshold
    under them (user 2026-11-06: "Semua sifatnya custom. Seharusnya ada di bagian yang garis merah"); the second line's
    too for a two-line condition */
function paramsHtml(e: Entry, i: number): string {
  const r = ruleOf(e), c = cardOfRule(e), er = ruleErrors(e), two = twoLines(optOf(e, c));
  const d2 = two ? newCard(e, [], { opt:r.opt }).second : {};
  return e.params.map(p => paramField(e, p, i, c.params[p.key], p.default, false, er[`p.${p.key}`])).join('') + (two ? e.params.map(p => paramField(e, p, i, c.second[p.key], d2[p.key], true, er[`p2.${p.key}`])).join('') : '');
}
function rowHtml(it: AddItem, i: number, added: boolean): string {
  const [cond, thr] = it.ok ? ruleHtml(it, i) : ['<span></span>', '<span></span>'];
  const act = !it.ok ? `<span class="qadd">No data</span>`
    : added ? `<button type="button" class="qact on" data-qact="${i}" tabindex="-1" aria-label="Remove ${esc(it.label)}"><span class="q-on">Added ${ico(IC.check, 's')}</span><span class="q-rm">Remove</span></button>`
    : `<button type="button" class="qact" data-qact="${i}" tabindex="-1" aria-label="Add ${esc(it.label)}">Add</button>`;
  const title = added ? 'On the screen with this condition. Click to remove it.' : it.ok ? 'Click to add with the condition shown' : (it.why || 'No data');
  const editable = it.ok && it.kind === 'ind' && !!it.entry?.params.length;   // its parameters are in the settings column
  return `<div role="option" id="aco${i}" class="qrow${i === W.act ? ' act' : ''}${it.ok ? '' : ' na'}${added ? ' isadd' : ''}" data-ai="${i}" data-rg="${esc(it.group)}" aria-selected="${i === W.act}"${it.ok ? '' : ' aria-disabled="true"'} title="${esc(title)}"><span class="qnm"><b>${esc(it.label)}</b>${editable ? '' : `<small>${esc(it.sub)}</small>`}</span>${it.ok ? tfHtml() : '<span></span>'}${cond}${thr}${act}</div>`;
}
function railHtml(): string {
  const btn = (g: string, inner: string, cls = '') => `<button type="button" class="qri ${cls}${W.g === g ? ' on' : ''}" data-ag="${esc(g)}" aria-pressed="${W.g === g}">${inner}</button>`;
  return btn(ON_SCREEN, `${ico(IC.check, 's')}<span class="lab">On the screen</span><span class="c">${S.cards.length}</span>`, 'q-on')
    + btn(MY, `${ico(IC.star, 's')}<span class="lab">My metrics</span><span class="c">${(ctx.metrics || []).length}</span>`, 'q-my')
    + `<div class="qrsep"></div><div class="qrtitle">Groups</div>`
    + btn(ALL, `<span class="lab">All indicators</span><span class="c">${ctx.entries.length}</span>`)
    + groupsOf().map(x => btn(x.g, `<span class="lab">${esc(x.label)}</span><span class="c">${x.n}</span>`)).join('');
}
function footHtml(): string {
  const n = S.cards.length, lim = ctx.catalog?.limits.find(l => l.name === 'max_conditions'), on = S.cards.filter(c => c.on).length;
  const over = lim && on > lim.value ? ` <b class="down">${esc(lim.rule)}: switch off or remove ${on - lim.value} before Screen now.</b>` : '';
  return `<span>Alt+A or / to open · ↑ ↓ to move · Enter to add or remove · Esc to close</span><span class="qcount">${n} condition${n === 1 ? '' : 's'} on the screen${over}</span>`;
}
/** draw the rows (keeps the list's scroll and the focused field) */
function drawList() {
  if (drawing) return;
  const l = $q<HTMLElement>('#acl'); if (!l) return;
  const fa = document.activeElement as HTMLElement | null, fs = root?.contains(fa) ? fieldSel(fa) : null, fk = fs ? `${fa!.dataset.ai}|${fs}` : null;
  const st = l.scrollTop;
  W.items = listItems(W.q, W.g, W.sort); W.act = Math.min(W.act, Math.max(0, W.items.length - 1));
  const on = S.cards.length ? screenSigs() : null;                   // nothing on the screen: no row is added
  W.added = W.items.map(it => !!on && it.ok && on.has(itemSig(it)));
  // the first rows at once, the rest in the next task: every row holds a select and its fields, and drawing a hundred of
  // them in one task went over 50 ms on a busy page (report 6c.9; the smoke's long-task check)
  clearTimeout(W.rest); W.restHtml = '';
  const rows = W.items.map((it, i) => rowHtml(it, i, W.added[i]));
  drawing = true;
  try { l.innerHTML = W.items.length
    ? `<div class="qcols" aria-hidden="true"><span>Indicator</span><span>Timeframe</span><span>Condition</span><span>Parameters &amp; threshold<em>blue = you can change it</em></span><span></span></div>` + rows.slice(0, FIRST_ROWS).join('')
    : `<p class="qwin-empty">Nothing matches “${esc(W.q)}”. Try another name, or what it measures (for example “momentum” or “volume”).</p>` } finally { drawing = false }
  if (rows.length > FIRST_ROWS) { W.restHtml = rows.slice(FIRST_ROWS).join(''); W.rest = setTimeout(drawRest, 0) }
  $q('#acq')?.setAttribute('aria-activedescendant', W.items.length ? 'aco' + W.act : '');
  l.scrollTop = st;
  if (fk) { const [i, f] = fk.split('|'); l.querySelector<HTMLElement>(`[data-ai="${i}"]${f}`)?.focus() }
  const r = $q('#acg'); if (r) r.innerHTML = railHtml();
  const ft = $q('#acf'); if (ft) ft.innerHTML = footHtml();
}
/** the rows not drawn yet (drawList): now, before anything needs every row (a group scroll, the arrow keys) */
function drawRest() {
  clearTimeout(W.rest);
  if (!W.restHtml) return;
  $q<HTMLElement>('#acl')?.insertAdjacentHTML('beforeend', W.restHtml); W.restHtml = '';
}
/** the highlighted row (arrow keys): only the two rows change */
function moveAct(i: number) {
  $q(`#aco${W.act}`)?.classList.remove('act'); $q(`#aco${W.act}`)?.setAttribute('aria-selected', 'false');
  W.act = i;
  const r = $q<HTMLElement>(`#aco${i}`); r?.classList.add('act'); r?.setAttribute('aria-selected', 'true');
  $q('#acq')?.setAttribute('aria-activedescendant', 'aco' + i);
  r?.scrollIntoView({ block:'nearest' });
}
const spyMode = () => W.g !== ON_SCREEN && W.g !== MY;
function railMark(g: string) {
  W.g = g;
  root?.querySelectorAll<HTMLElement>('#acg [data-ag]').forEach(b => { const on = b.dataset.ag === g; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)) });
}
function scrollToGroup(g: string) {
  drawRest();
  const l = $q<HTMLElement>('#acl'); if (!l) return;
  const hd = l.querySelector<HTMLElement>('.qcols')?.offsetHeight || 0, r = g === ALL ? null : l.querySelector<HTMLElement>(`.qrow[data-rg="${CSS.escape(g)}"]`);
  W.spyLock = Date.now() + 700;
  l.scrollTop = r ? r.getBoundingClientRect().top - l.getBoundingClientRect().top + l.scrollTop - hd : 0;
}
function spy() {
  if (!spyMode() || Date.now() < W.spyLock) return;
  const l = $q<HTMLElement>('#acl'); if (!l) return;
  const hd = l.querySelector<HTMLElement>('.qcols')?.offsetHeight || 0, top = l.getBoundingClientRect().top;
  let cur = ALL;
  if (l.scrollTop > 8) for (const r of l.querySelectorAll<HTMLElement>('.qrow[data-rg]')) { if (r.getBoundingClientRect().bottom - top > hd + 4) { cur = r.dataset.rg!; break } }
  if (cur !== W.g) railMark(cur);
}
function toggle(i: number) {
  const it = W.items[i]; if (!it || !it.ok) return;
  W.act = i;
  if (W.added[i]) {
    const gone = removeItem(it);
    if (gone.length) toastAction(`${it.label} removed`, 'Undo', () => { restore(gone); drawList(); toast(`${it.label} restored`) });
  } else {
    const r = addItem(it); toast(r.message);
    if (!r.ok) { const f = Object.keys(it.entry ? ruleErrors(it.entry) : {})[0]; if (f) root?.querySelector<HTMLElement>(`[data-ai="${i}"]${errSel(f)}`)?.focus(); return }
  }
  const keep = (document.activeElement as HTMLElement | null)?.closest?.('.rr');
  drawRow(i);
  if (!keep) $q<HTMLInputElement>('#acq')?.focus({ preventScroll:true });   // several in a row: back to the search
}
/** a row's field as a selector (its data-af, data-ap or data-ap2), to find it again after a redraw */
function fieldSel(el: HTMLElement | null): string | null {
  const d = el?.dataset; if (!d) return null;
  return d.af ? `[data-af="${d.af}"]` : d.ap ? `[data-ap="${CSS.escape(d.ap)}"]` : d.ap2 ? `[data-ap2="${CSS.escape(d.ap2)}"]` : null;
}
/** the field of an error key of ruleErrors */
const errSel = (k: string) => k === 'op' ? '[data-af="opt"]' : k.startsWith('p2.') ? `[data-ap2="${CSS.escape(k.slice(3))}"]` : k.startsWith('p.') ? `[data-ap="${CSS.escape(k.slice(2))}"]` : `[data-af="${k}"]`;
/** after an add or a remove only this row and the counts change (a whole redraw with the page's own draw in one task
    went over 50 ms) */
/* A redraw removes the focused field; a field whose value changed then fires "change" while it is being removed, and
   that event would redraw again in the middle of the first redraw (Chrome: "The node to be removed is no longer a child
   of this node"). The rule was already updated from that value, so a redraw asked during a redraw is skipped
   (`drawing`, declared with the window state). */
function drawRow(i: number) {
  if (drawing) return;
  drawRest();
  const it = W.items[i], el = $q<HTMLElement>(`#aco${i}`); if (!it || !el) return drawList();
  const fa = document.activeElement as HTMLElement | null, ff = el.contains(fa) ? fieldSel(fa) : null;
  W.added[i] = it.ok && screenSigs().has(itemSig(it));
  drawing = true; try { el.outerHTML = rowHtml(it, i, W.added[i]) } finally { drawing = false }
  if (ff) $q<HTMLElement>(`#aco${i} ${ff}`)?.focus();
  const r = $q('#acg'); if (r) r.innerHTML = railHtml();
  const ft = $q('#acf'); if (ft) ft.innerHTML = footHtml();
}

/** Open the window. `q` searches at once (a quick chip, the builder's search box); `g` opens on a panel (My metrics). */
export function openAddCondition(q = '', g: string = ALL) {
  if (!ctx.catalog) return;
  W.q = q; W.g = g; W.act = 0;
  dialog(`<div class="dialog qwin" role="dialog" aria-label="Add a condition">
    <div class="qwin-h"><div><strong>Add a condition</strong><small>Pick the condition next to an indicator, then click the row to add it. Click an added row to remove it. The window stays open until you close it.</small></div><button type="button" class="iconbtn sm" data-close aria-label="Close">${ico(IC.x)}</button></div>
    <div class="qwin-t"><label class="searchbox">${ico(IC.search, 's')}<input id="acq" placeholder="RSI, Stochastic, VWAP, Supertrend, breakout…" autocomplete="off" aria-label="Search indicators" role="combobox" aria-controls="acl" aria-expanded="true" value="${esc(q)}"></label>
      <label class="qwin-sort">Sort <select class="sel sm" id="acs" aria-label="Sort"><option value="group">Group</option><option value="az">Name A–Z</option><option value="za">Name Z–A</option></select></label></div>
    <div class="qwin-b"><nav class="qwin-g qrail" id="acg" aria-label="Groups"></nav><div class="qwin-l" id="acl" role="listbox" aria-label="Indicators"></div></div>
    <div class="qwin-f" id="acf"></div></div>`, o => {
    root = o.querySelector<HTMLElement>('.qwin');
    const sort = root!.querySelector<HTMLSelectElement>('#acs')!; sort.value = W.sort;
    sort.addEventListener('change', () => { W.sort = sort.value as Sort; drawList() });
    root!.querySelector<HTMLInputElement>('#acq')!.addEventListener('input', e => { W.q = (e.target as HTMLInputElement).value; W.act = 0; drawList(); const l = $q<HTMLElement>('#acl'); if (l) l.scrollTop = 0 });
    root!.querySelector('#acl')!.addEventListener('scroll', spy, { passive:true });
    root!.addEventListener('click', onClick);
    root!.addEventListener('change', onField);
    root!.addEventListener('input', onInput);
    root!.addEventListener('keydown', onKey);
  });
  drawList();
  if (spyMode() && g !== ALL) { railMark(g); scrollToGroup(g) }
  $q<HTMLInputElement>('#acq')?.focus();
}
function onClick(e: Event) {
  const t = e.target as HTMLElement;
  const g = t.closest<HTMLElement>('[data-ag]');
  if (g) {
    const to = g.dataset.ag!, was = spyMode(); W.g = to; W.act = 0;
    if (to === ON_SCREEN || to === MY || !was) { drawList(); const l = $q<HTMLElement>('#acl'); if (l) l.scrollTop = 0 }
    if (spyMode()) { railMark(to); scrollToGroup(to) }
    root?.querySelector<HTMLElement>(`[data-ag="${CSS.escape(to)}"]`)?.focus({ preventScroll:true });
    return;
  }
  if (t.closest('select,input,.rr')) return;              // the row's own controls (a parameter's label too)
  const r = t.closest<HTMLElement>('.qrow[data-ai]'); if (r) toggle(Number(r.dataset.ai));
}
/** a rule or a threshold changed: kept per indicator; the row's "added" state follows (it compares the wire test) */
/** a parameter field's value as the card reads it (builder.ts onBuilderField): an option, true/false, or a number (NaN
    when empty, so the check names it) */
function paramValue(p: EntryParam, el: HTMLInputElement | HTMLSelectElement): ParamValue {
  return p.type === 'boolean' ? el.value === 'true' : p.options || p.type === 'enum' ? el.value : el.value.trim() === '' ? NaN : Number(el.value);
}
/** a parameter changed: kept in the rule (the first line's or the second's) */
function setParam(el: HTMLInputElement | HTMLSelectElement): boolean {
  const key = el.dataset.ap ?? el.dataset.ap2, it = W.items[Number(el.dataset.ai)];
  if (key == null || !it?.entry || it.kind !== 'ind') return false;
  const e = it.entry, p = e.params.find(x => x.key === key); if (!p) return false;
  const r = ruleOf(e);
  if (el.dataset.ap2 != null) r.second = { ...(r.second || cardOfRule(e).second), [key]:paramValue(p, el) } as Params;
  else r.params = { ...r.params, [key]:paramValue(p, el) };
  return true;
}
function onField(e: Event) {
  const el = e.target as HTMLInputElement | HTMLSelectElement, f = el.dataset.af, it = W.items[Number(el.dataset.ai)];
  if (setParam(el)) { drawRow(Number(el.dataset.ai)); return }
  if (!f || !it?.entry || it.kind !== 'ind') return;
  if (f === 'opt') setOpt(it.entry, el.value);
  else { const r = ruleOf(it.entry); (r as unknown as Record<string, number | ''>)[f] = el.value.trim() === '' ? '' : Number(el.value) }
  drawRow(Number(el.dataset.ai));
}
function onInput(e: Event) {
  const el = e.target as HTMLInputElement, f = el.dataset.af, it = W.items[Number(el.dataset.ai)];
  if (el.tagName === 'INPUT' && setParam(el)) return;
  if (!f || f === 'opt' || !it?.entry) return;
  const r = ruleOf(it.entry); (r as unknown as Record<string, number | ''>)[f] = el.value.trim() === '' ? '' : Number(el.value);
}
function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement, n = W.items.length;
  if ((t.dataset.af || t.dataset.ap != null || t.dataset.ap2 != null) && e.key === 'Enter' && t.tagName === 'INPUT') {
    // Enter in a field adds; it never removes. The value just typed can make the row the same test as a card already on
    // the screen (Length 50 + Close above SMA, in Minervini), a state the row shows only once the field is applied: a
    // toggle then removed that card unseen (ERRORS M378, live 2026-11-06). Removing stays a click on the row or Remove.
    e.preventDefault(); onField(e);
    const i = Number(t.dataset.ai);
    if (W.added[i]) { toast(`${W.items[i]?.label}: already on the screen with this condition.`); return }
    toggle(i); return;
  }
  if (t.closest('.rr')) return;
  if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && n && (t.id === 'acq' || t.closest('#acl'))) {
    e.preventDefault(); drawRest(); moveAct((W.act + (e.key === 'ArrowDown' ? 1 : -1) + n) % n);
  } else if (e.key === 'Enter' && t.id === 'acq') { e.preventDefault(); toggle(W.act) }
}
/** the window is closed by dialogs.ts (Escape, the close button, the backdrop); forget its root then */
export const addConditionOpen = () => !!root && document.contains(root);
export function closeAddCondition() { if (addConditionOpen()) closeDialog(); root = null }
