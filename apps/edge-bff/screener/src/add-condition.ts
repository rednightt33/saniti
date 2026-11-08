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
import { defaultParams, depthHint, flowBudget, flowSessions, GHEAD, GORD, isFlowType, matches, optionText, paramError, rangeText, type Entry, type EntryParam, type Opt } from './entries.ts';
import { cardErrors, displayUnit, fromWire, newCard, newCardId, optOf, toWire, type Card } from './forms.ts';
import { closeDialog, dialog, toast, toastAction } from './dialogs.ts';
import { defaultOp, fieldHint, fieldMax, isSignal, measureOf, measuresFor, offersOperators, OP_WORDS, opFieldUnit, operatorTitle, opsFor, opText, plainOffered, secondOptions, seriesList, signalText, testOf, testsFor, withCmp, withMeasure, withTest, type OpState } from './operators.ts';
import { sideOf } from './texts.ts';
import { flowControlHtml, paramFieldValue, paramTitle } from './param-fields.ts';

export const MY = 'My metrics', ON_SCREEN = '__on', ALL = 'All';
export type Sort = 'group' | 'az' | 'za';
const TIMEFRAMES = ['5m', '15m', '1h', '4h', 'Daily'];
export const NO_INTRADAY = 'No data yet: intraday bars are not in the market database.';

/* ---- the rule chosen per indicator before adding (the reference's RULE); defaults from the catalog --------------- */
type Params = Record<string, ParamValue>;
export interface Rule { opt: string; value: number | ''; value2: number | ''; within: number | ''; params: Params; second?: Params; op?: OpState }
/** the condition select's choice that opens the universal operators (operators.ts; P3): the row's test is then the
    operator's, set in the Customize panel */
export const OP_OPT = '__op';
const RULE = new Map<string, Rule>();
export function ruleOf(e: Entry): Rule {
  let r = RULE.get(e.key);
  if (!r) {
    r = { opt:e.def.opt, value:e.def.value, value2:e.def.value2, within:e.def.within, params:defaultParams(e) as Params };
    // an indicator with no condition of its own (a flow output of lots per transaction, P5c) opens on the operator
    if (!e.opts.some(o => !o.disabled) && offersOperators(e.ops, e)) { r.op = defaultOp(e.ops!, e, undefined, r.params); r.opt = OP_OPT }
    RULE.set(e.key, r);
  }
  return r;
}
/** tests and a new catalog: forget the rules chosen so far */
export function resetRules() { RULE.clear() }
/** a new rule option, with the value fields it needs filled from the catalog default when empty (as the card does) */
export function setOpt(e: Entry, opt: string) {
  const r = ruleOf(e);
  if (opt === OP_OPT) { if (offersOperators(e.ops, e)) { r.op ??= defaultOp(e.ops!, e, undefined, r.params); r.opt = OP_OPT } return }
  delete r.op;
  if (r.opt !== opt) delete r.second;             // the second line's defaults belong to the condition (its form's defaults)
  r.opt = opt;
  const o = e.opts.find(x => x.key === opt);
  if (o?.value === 'input' && r.value === '') r.value = e.def.value;
  if (o?.between && r.value2 === '') r.value2 = e.def.value2 === '' ? (typeof r.value === 'number' ? r.value : 0) : e.def.value2;
}
const withinMax = () => ctx.catalog?.limits.find(l => l.name === 'within_max')?.value ?? 130;
/** the most "within" takes on this row: within_max, and on a flow indicator the broker sessions held (K1) */
const withinOf = (e: Entry) => { const S0 = flowSessions(e); return S0 == null ? withinMax() : Math.min(withinMax(), S0) };
/** on a flow indicator, the hint of a "within": about how many broker sessions the setup leaves (the worker judges) */
const withinHint = (e: Entry, params: Params) => e.flow ? depthHint(flowBudget(e, params)) : '';
/** the card this rule adds (fresh id among the page's cards) */
export function cardOfRule(e: Entry, r = ruleOf(e)): Card {
  return newCard(e, S.cards.map(x => x.id), { opt:r.op ? e.def.opt : r.opt, value:r.value, value2:r.value2, within:r.within, params:{ ...r.params } as Card['params'],
    ...(r.second && !r.op ? { second:{ ...r.second } as Card['second'] } : {}), ...(r.op ? { op:r.op } : {}) });
}
/** the condition reads two lines of the indicator, the second with its own parameters (as the card shows "2nd") */
const twoLines = (o: Opt | undefined) => !!o && (o.form === 'state_instance' || o.form === 'event_instance');
/** the rule's problems, field -> message: the card's own validation (forms.ts cardErrors) and each parameter's
    (entries.ts paramError, the card's check), keyed 'p.<key>' and 'p2.<key>' */
export function ruleErrors(e: Entry): Record<string, string> {
  const c = cardOfRule(e), out = cardErrors(e, c, withinMax());
  // a card's error under a parameter (a flow indicator's broker choice) is the row's p.<key>
  for (const k of Object.keys(out)) if (e.params.some(p => p.key === k)) { out[`p.${k}`] = `${e.params.find(p => p.key === k)!.label || k}: ${out[k].replace(/^[^:]*:\s*/, '')}`; delete out[k] }
  const lines: [string, Params][] = [['p', c.params as Params], ...(!c.op && twoLines(optOf(e, c)) ? [['p2', c.second as Params] as [string, Params]] : [])];
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
  return { ok:true, message:`${it.label} added${it.kind === 'ind' ? addedRule(it.entry!) : ''}` };
}
/** what the toast says after "added": the row's condition, or the operator's rule when the row adds an operator (its
    condition select reads "Operator…", which names nothing: the 20-question test, item E); '' when there is none */
function addedRule(e: Entry): string {
  const r = ruleOf(e), what = r.op && e.ops ? opText(e.ops, e, r.op, r.params as Params) : e.opts.find(o => o.key === r.opt)?.label || '';
  return what ? ` · ${what}` : '';
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
const W = { q:'', g:ALL as string, sort:'group' as Sort, act:0, pop:null as number | null, items:[] as AddItem[], added:[] as boolean[], spyLock:0, rest:undefined as ReturnType<typeof setTimeout> | undefined, restFrom:0,
  /* user 2026-11-08 ("ketika kita klik customize ... muncul boxnya di tengah, bisa digedein, bisa dikecilin"): the Customize
     box's size and its shift from the middle, kept while the window is open (a row redraw draws the box again) */
  popBox:{ w:0, h:0, dx:0, dy:0 } };
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
  const opOpt = offersOperators(e.ops, e) ? `<option value="${OP_OPT}" ${r.op ? 'selected' : ''} title="${esc(operatorTitle(e.ops!, e, r.params))}">Operator…</option>` : '';
  const sel = `<select class="sel" data-af="opt" data-ai="${i}" aria-label="Condition for ${esc(e.label)}"${er.op ? ` aria-invalid="true" title="${esc(er.op)}"` : ''}>${e.opts.map(x => `<option value="${esc(x.key)}" ${!r.op && x.key === r.opt ? 'selected' : ''} ${x.disabled ? `disabled title="${esc(x.disabled)}"` : ''}>${esc(x.label)}${x.disabled ? ' — not offered' : ''}</option>`).join('')}${opOpt}</select>`;
  return [`<span class="rr qs">${sel}</span>`, `<span class="rr qt${W.pop === i ? ' open' : ''}">${settingsHtml(e, i)}</span>`];
}

/* ---- the settings column: every blue box of the row (user 2026-11-06, the HTML of ten options, then "Pokoknya kalau
   ada kotak biru lebih dari 2, berarti masuk customizable ... tinggi kolom setiap indikator harusnya sama ... tambahin
   juga parameter yang customizable ada berapa"): a box is a parameter of the indicator (and of its second line for a
   two-line condition) or a threshold field of the condition. Two boxes or fewer are shown in the row, on one line;
   more go behind a "Customize" button that shows how many there are and opens a panel (parameters, then the threshold
   under a thin rule, each with its default; Reset to default, Done; Escape closes it). The fields, their limits and
   checks are the card's either way. */
interface Box { name: string; control: string; unit: string; def: string; changed: boolean; thr: boolean; hint?: string; group?: boolean }
/** a parameter's control: the card's field (a select for options and true/false, else a number with the catalog's
    limits) */
function paramControl(e: Entry, p: EntryParam, i: number, v: ParamValue | undefined, def: ParamValue | undefined, second: boolean, err: string | undefined): string {
  const attr = second ? 'data-ap2' : 'data-ap', name = `${second ? '2nd ' : ''}${p.label || p.key}`;
  // a flow indicator's list, anchor date or broker codes (param-fields.ts)
  if (isFlowType(p)) return flowControlHtml(p, v, `${attr}="${esc(p.key)}" data-ai="${i}"`, `${name} of ${e.label}`, err || paramTitle(p, def), !!err)!;
  const common = `${attr}="${esc(p.key)}" data-ai="${i}" aria-label="${esc(name)} of ${esc(e.label)}"${err ? ` aria-invalid="true" title="${esc(err)}"` : ` title="${esc(`${rangeText(p) ? rangeText(p) + ' · ' : ''}default ${optionText(p, def as ParamValue)}`)}"`}`;
  return p.options ? `<select class="sel" ${common}>${p.options.map(x => `<option value="${esc(x)}" ${String(x) === String(v) ? 'selected' : ''}>${esc(optionText(p, x))}</option>`).join('')}</select>`
    : p.type === 'boolean' ? `<select class="sel" ${common}><option value="true" ${v === true ? 'selected' : ''}>true</option><option value="false" ${v === false ? 'selected' : ''}>false</option></select>`
    : `<input class="inp" type="number" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="${p.step ?? (p.integer ? 1 : 'any')}" value="${esc(Number.isFinite(v as number) ? v : '')}" style="--n:${String(v ?? '').length}" ${common}>`;
}
/** the blue boxes of a row, in order: its parameters, the second line's, then the threshold fields */
function boxesOf(e: Entry, i: number): Box[] {
  const r = ruleOf(e), c = cardOfRule(e), o = optOf(e, c), er = ruleErrors(e), out: Box[] = [];
  const d2 = !r.op && twoLines(o) ? newCard(e, [], { opt:r.opt }).second : null;
  // a list's checkbox group is a group of its own labels, never inside one label (a label names one control)
  for (const p of e.params) out.push({ name:p.label || p.key, control:paramControl(e, p, i, c.params[p.key], p.default, false, er[`p.${p.key}`]), unit:'', def:optionText(p, p.default), changed:String(c.params[p.key]) !== String(p.default), thr:false, group:p.type === 'multi' });
  if (d2) for (const p of e.params) out.push({ name:`2nd ${p.label || p.key}`, control:paramControl(e, p, i, c.second[p.key], d2[p.key], true, er[`p2.${p.key}`]), unit:'', def:optionText(p, d2[p.key]), changed:String(c.second[p.key]) !== String(d2[p.key]), thr:false });
  if (r.op && e.ops) { out.push(...opBoxes(e, r.op, i, er, c.params as Params)); return out }
  for (const l of fieldsOf(o)) {
    const v = r[l.f], d = fdef(e, l.f);
    const hint = l.f === 'within' ? withinHint(e, c.params as Params) : '';
    out.push({ name:l.lead, unit:l.unit, def:hint ? `${d} · ${hint}` : String(d), changed:String(v) !== String(d), thr:true,
      control:`<input class="inp" type="number" step="${l.f === 'within' ? 1 : 'any'}"${l.f === 'within' ? ` min="1" max="${withinOf(e)}"` : ''} data-af="${l.f}" data-ai="${i}" value="${esc(v)}" style="--n:${String(v).length}" aria-label="${esc(l.label)}${l.unit ? ` (${esc(l.unit)})` : ''} for ${esc(e.label)}"${er[l.f] ? ` aria-invalid="true" title="${esc(er[l.f])}"` : ` title="default ${esc(d)}"`}>` });
  }
  return out;
}
/** The operator's boxes (operators.ts; every list from the catalog's operators block): the line of the indicator (when
    it has several), the measure and its arguments, the second series of a relative comparison, the test, how it
    compares, the value or range, and the sessions of a cross or window test. */
function opBoxes(e: Entry, op: OpState, i: number, er: Record<string, string>, params: Params): Box[] {
  const ops = e.ops!, out: Box[] = [], m = op.measure === 'none' ? undefined : measureOf(ops, op.measure), t = testOf(ops, op.test);
  const bad = (k: string) => er[k] ? ` aria-invalid="true" title="${esc(er[k])}"` : '';
  const sel = (f: string, label: string, list: { v: string; t: string }[], cur: string, help = '') => `<select class="sel qop" data-ao="${f}" data-ai="${i}" aria-label="${esc(label)} of ${esc(e.label)}"${er['o.' + f] ? bad('o.' + f) : help ? ` title="${esc(help)}"` : ''}>${list.map(x => `<option value="${esc(x.v)}" ${x.v === cur ? 'selected' : ''}>${esc(x.t)}</option>`).join('')}</select>`;
  const numIn = (f: string, label: string, v: number | '', attrs = '') => `<input class="inp" type="number" step="any" ${attrs} data-ao="${f}" data-ai="${i}" value="${esc(v)}" style="--n:${String(v).length}" aria-label="${esc(label)} for ${esc(e.label)}"${bad('o.' + f)}>`;
  // the lines the setup draws (a flow indicator's Buy and Sell follow its Side), and the one chosen
  const outs = seriesList(e, params).filter(x => x.drawn || x.key === op.output);
  if (seriesList(e, params).length > 1) out.push({ name:'Line', control:sel('output', 'Line', outs.map(x => ({ v:x.key, t:x.label })), op.output), unit:'', def:'', changed:false, thr:true, hint:'' });
  // a pattern's 0/1 signal takes no measure (OPERATORS.md section 4, type F): no Measure box with one choice in it
  const signal = isSignal(e);
  if (!signal) out.push({ name:'Measure', control:sel('measure', 'Measure', [...(plainOffered(ops, e, op.output, params) ? [{ v:'none', t:'The value itself' }] : []), ...measuresFor(ops, e, op.output, params).map(x => ({ v:x.fn, t:x.label }))], op.measure, m?.help), unit:'', def:'', changed:false, thr:true, hint:'' });
  // on a flow series a session field takes at most the broker sessions held, and shows as a hint about how many the
  // setup leaves (K1: the worker judges the setup; its refusal is shown on the card)
  const argMax = fieldMax(ops, e, op, 'arg', withinMax(), params), nMax = fieldMax(ops, e, op, 'n', withinMax(), params) ?? withinMax();
  const argHint = e.flow ? depthHint(fieldHint(ops, e, op, 'arg', params)) : '', nHint = e.flow ? depthHint(fieldHint(ops, e, op, 'n', params)) : '';
  /** a measure argument counting sessions with a broker-data hint (a flow series) */
  const sessionsLeft = (key: string) => !!argHint && (key === 'length' || key === 'bars');
  for (const a of m?.args || []) {
    const lim = (a.key === 'length' || a.key === 'bars') && argMax != null ? { ...a, max:a.max != null ? Math.min(a.max, argMax) : argMax } : a;
    const p = lim as EntryParam, v = op.margs[a.key], msg = er[`o.a.${a.key}`], range = rangeText(p);
    const ctl = p.options ? `<select class="sel" data-aoa="${esc(a.key)}" data-ai="${i}" aria-label="${esc(a.label || a.key)} of ${esc(e.label)}"${msg ? ` aria-invalid="true" title="${esc(msg)}"` : ''}>${p.options.map(x => `<option value="${esc(x)}" ${String(x) === String(v) ? 'selected' : ''}>${esc(optionText(p, x))}</option>`).join('')}</select>`
      : `<input class="inp" type="number" ${p.min != null ? `min="${p.min}"` : ''} ${p.max != null ? `max="${p.max}"` : ''} step="1" data-aoa="${esc(a.key)}" data-ai="${i}" value="${esc(Number.isFinite(v as number) ? v : '')}" style="--n:${String(v ?? '').length}" aria-label="${esc(a.label || a.key)} of ${esc(e.label)}"${msg ? ` aria-invalid="true" title="${esc(msg)}"` : ` title="${esc(sessionsLeft(a.key) ? [rangeText(p), argHint].filter(Boolean).join(' · ') : `${rangeText(p) ? rangeText(p) + ' · ' : ''}default ${optionText(p, a.default as ParamValue)}`)}"`}>`;
    // the field shows its range beside its default (OPERATORS.md section 5: "the field shows its range"); on a flow series
    // the sessions the setup leaves instead of the default, which it may not open at (the 20-question test, item D: "default
    // 60" with about 50 sessions left)
    const left = sessionsLeft(a.key);
    out.push({ name:a.label || a.key, control:ctl, unit:'', def:`${optionText(p, a.default as ParamValue)}${range ? ` · ${range}` : ''}`, changed:String(v) !== String(a.default), thr:true,
      ...(left ? { hint:[range, argHint].filter(Boolean).join(' · ') } : {}) });
  }
  if (m?.second) out.push({ name:'Compared with', control:sel('by', 'Compared with', secondOptions(e, op.output, params).map(x => ({ v:x.key, t:x.label })), op.by), unit:'', def:'', changed:false, thr:true, hint:'' });
  // a pattern's tests in its own words ("Detected on at least K of the last N sessions"), the catalog's label as the option
  out.push({ name:signal ? 'Detected' : 'Test', control:sel('test', signal ? 'Detected' : 'Test', testsFor(ops, e, op, params).map(x => ({ v:x.key, t:x.label })), op.test, signal ? signalText(op.test, 'N', 'K') : t?.help), unit:'', def:'', changed:false, thr:true, hint:'' });
  if (t && !signal) {
    // what the defaults of this measure and test would be: a field set otherwise counts as changed on the Customize button
    const d0 = withTest(ops, e, { ...op, cmp:m ? m.default.cmp : op.cmp }, op.test, params);
    out.push({ name:'Condition', control:sel('cmp', 'Condition', opsFor(e, op, t, params).map(x => ({ v:x, t:OP_WORDS[x] || x })), op.cmp), unit:'', def:'', changed:op.cmp !== d0.cmp, thr:true, hint:'' });
    const u = opFieldUnit(ops, e, op, params), two = op.cmp === 'between' || op.cmp === 'outside';
    out.push({ name:two ? 'From' : 'Value', control:numIn('value', two ? 'From' : 'Value', op.value), unit:u, def:'', changed:String(op.value) !== String(d0.value), thr:true, hint:u });
    if (two) out.push({ name:'To', control:numIn('value2', 'To', op.value2), unit:u, def:'', changed:String(op.value2) !== String(d0.value2), thr:true, hint:u });
  }
  // the sessions of a cross or a window: a pattern's too (its comparison is always "detected": no Condition, no Value)
  if (t) {
    // "on at least K of the last N sessions": K first, as it reads (QA5 D4)
    if (t.count) out.push({ name:'On at least', control:numIn('k', 'Sessions passing', op.k, 'min="1" step="1"'), unit:'sessions', def:String(t.default?.k ?? ''), changed:String(op.k) !== String(t.default?.k ?? ''), thr:true });
    if (t.within || t.length) out.push({ name:t.count ? 'Of the last' : t.within ? 'Within' : t.key === 'streak' ? 'In a row' : 'In the last', control:numIn('n', 'Sessions', op.n, `min="1" max="${nMax}" step="1"`), unit:'sessions', def:`${t.default?.n ?? ''} · 1 to ${nMax}`, changed:String(op.n) !== String(t.default?.n ?? ''), thr:true,
      ...(nHint ? { hint:`1 to ${nMax} · ${nHint}` } : {}) });
  }
  return out;
}
/** an operator field changed (data-ao, data-aoa): kept in the rule's operator; a new measure or test takes its defaults */
function setOpField(el: HTMLInputElement | HTMLSelectElement): boolean {
  const f = el.dataset.ao, a = el.dataset.aoa, it = W.items[Number(el.dataset.ai)];
  if ((f == null && a == null) || !it?.entry || it.kind !== 'ind') return false;
  const e = it.entry, r = ruleOf(e); if (!r.op || !e.ops) return false;
  const n = (x: string): number | '' => x.trim() === '' ? '' : Number(x);
  if (a != null) { const p = measureOf(e.ops, r.op.measure)?.args.find(x => x.key === a); r.op = { ...r.op, margs:{ ...r.op.margs, [a]:p?.type === 'enum' ? el.value : el.value.trim() === '' ? NaN : Number(el.value) } }; return true }
  const P = r.params;
  switch (f) {
    case 'measure': r.op = withMeasure(e.ops, e, r.op, el.value, P); break;
    case 'test': r.op = withTest(e.ops, e, r.op, el.value, P); break;
    case 'output': { const next = { ...r.op, output:el.value }; if (!secondOptions(e, el.value, P).some(x => x.key === next.by)) next.by = secondOptions(e, el.value, P)[0]?.key ?? ''; r.op = withMeasure(e.ops, e, next, measuresFor(e.ops, e, el.value, P).some(x => x.fn === next.measure) ? next.measure : plainOffered(e.ops, e, el.value, P) ? 'none' : measuresFor(e.ops, e, el.value, P)[0]?.fn ?? 'none', P); break }
    case 'by': r.op = { ...r.op, by:el.value }; break;
    case 'cmp': r.op = withCmp(e.ops, e, r.op, el.value); break;
    case 'value': case 'value2': case 'n': case 'k': r.op = { ...r.op, [f]:n(el.value) }; break;
    default: return false;
  }
  return true;
}
/** at most this many boxes are shown in the row; more go behind "Customize" */
export const INLINE_BOXES = 2;
function settingsHtml(e: Entry, i: number): string {
  const B = boxesOf(e, i);
  if (!B.length) return '<span class="rr-none">—</span>';
  const tag = (b: Box) => b.group ? 'span' : 'label';
  if (B.length <= INLINE_BOXES) return B.map(b => `<${tag(b)} class="qbox${b.changed ? ' chg' : ''}${b.thr ? ' thr' : ' qp'}"><span class="lab" title="${esc(b.name)}">${esc(b.name)}</span>${b.control}${b.unit ? `<span class="unit">${esc(b.unit)}</span>` : ''}</${tag(b)}>`).join('');
  const n = B.filter(b => b.changed).length, open = W.pop === i;
  const btn = `<button type="button" class="qcus${n ? ' chg' : ''}" data-cus="${i}" aria-expanded="${open}" aria-haspopup="dialog" title="${n ? `${n} of ${B.length} fields changed` : `${B.length} fields you can change`}">${ico(IC.gear, 's')}<span class="t">${n ? 'Custom' : 'Customize'}</span><span class="n">${n ? `${n} of ${B.length} changed` : B.length}</span></button>`;
  if (!open) return btn;
  // an operator's line has no catalog default of its own to show: its unit, if any, instead (the select's title explains it)
  const line = (b: Box) => `<${tag(b)} class="qpl${b.changed ? ' chg' : ''}${b.thr ? ' thr' : ' qp'}"><span class="lab" title="${esc(b.name)}">${esc(b.name)}</span>${b.control}<span class="def">${b.hint !== undefined ? esc(b.hint) : `${b.unit ? esc(b.unit) + ' · ' : ''}default ${esc(b.def)}`}</span></${tag(b)}>`;
  const ps = B.filter(b => !b.thr), ts = B.filter(b => b.thr);
  const side = sideOf(e);
  return btn + `<span class="qpop" role="dialog" aria-label="Customize ${esc(e.label)}"><strong>${esc(e.label)}${side ? ` <small class="qside s-${side.side}" title="${esc(side.title)}">${esc(side.word)}</small>` : ''}</strong>${ps.map(line).join('')}${ps.length && ts.length ? '<span class="qsep"></span>' : ''}${ts.map(line).join('')}<span class="qpf"><button type="button" class="link" data-cusreset="${i}">Reset to default</button><button type="button" class="link" data-cusdone="${i}">Done</button></span></span>`;
}
/** Reset to default: the row's parameters and threshold back to the catalog's defaults (its condition stays) */
export function resetRule(e: Entry) {
  const r = ruleOf(e); r.params = defaultParams(e) as Params; delete r.second;
  r.value = e.def.value; r.value2 = e.def.value2; r.within = e.def.within;
  if (r.op && e.ops) r.op = defaultOp(e.ops, e, undefined, r.params);
}
const firstSentence = (t: string) => (t.match(/^.*?[.!?](\s|$)/)?.[0] ?? t).trim();
/** a group's heading before its first row when the list is sorted by group (the Terminal's "TREND 12") */
function bandHtml(i: number): string {
  const it = W.items[i]; if (!it || W.sort !== 'group' || W.g === ON_SCREEN || W.g === MY) return '';
  if (i > 0 && W.items[i - 1].group === it.group) return '';
  const n = W.items.filter(x => x.group === it.group).length;
  return `<div class="qsec" data-sec="${esc(it.group)}" aria-hidden="true">${esc(GHEAD(it.group))}<span>${n}</span></div>`;
}
function rowHtml(it: AddItem, i: number, added: boolean): string {
  const [cond, thr] = it.ok ? ruleHtml(it, i) : ['<span></span>', '<span></span>'];
  const act = !it.ok ? `<span class="qadd">No data</span>`
    : added ? `<button type="button" class="qact on" data-qact="${i}" tabindex="-1" aria-label="Remove ${esc(it.label)}"><span class="q-on">Added ${ico(IC.check, 's')}</span><span class="q-rm">Remove</span></button>`
    : `<button type="button" class="qact" data-qact="${i}" tabindex="-1" aria-label="Add ${esc(it.label)}">Add</button>`;
  const title = added ? 'On the screen with this condition. Click to remove it.' : it.ok ? 'Click to add with the condition shown' : (it.why || 'No data');
  const editable = it.ok && it.kind === 'ind' && !!it.entry?.params.length;   // its parameters are in the settings column (no grey line)
  // a pattern's side under its name (QA of unit C item 2), in place of the grey line (a row without data keeps its reason)
  const side = it.kind === 'ind' && it.ok ? sideOf(it.entry) : null;
  /* user 2026-11-08 (the Terminal's Indicators window): the indicator's code beside its name and one sentence of what it
     is under it; a pattern keeps its side, a row without data its reason, a saved metric its note */
  const code = it.kind === 'ind' && it.entry && /^(I|FL)\d+$/.test(it.entry.key) ? `<small class="qcode">${esc(it.entry.key)}</small>` : '';
  const desc = it.kind === 'ind' && it.ok && it.entry?.desc ? firstSentence(it.entry.desc) : '';
  const sub = side ? `<small class="qside s-${side.side}" title="${esc(side.title)}">${esc(side.line)}</small>` : desc ? `<small class="qdesc" title="${esc(it.entry!.desc)}">${esc(desc)}</small>` : editable ? '' : `<small>${esc(it.sub)}</small>`;
  return `<div role="option" id="aco${i}" class="qrow${i === W.act ? ' act' : ''}${it.ok ? '' : ' na'}${added ? ' isadd' : ''}" data-ai="${i}" data-rg="${esc(it.group)}" aria-selected="${i === W.act}"${it.ok ? '' : ' aria-disabled="true"'} title="${esc(title)}"><span class="qnm"><span class="qnl"><b>${esc(it.label)}</b>${code}</span>${sub}</span>${it.ok ? tfHtml() : '<span></span>'}${cond}${thr}${act}</div>`;
}
/** a group's section, from its entries: Fundamental when every entry is a fundamental, Flow when one reads the broker
    flow (a Terminal flow indicator, or a metric of the Flow group), Technical otherwise */
function sectionOf(g: string): string {
  const es = ctx.entries.filter(e => e.group === g);
  return es.length && es.every(e => e.kind === 'fundamental') ? 'Fundamental' : es.some(e => !!e.flow) ? 'Flow' : 'Technical';
}
function railHtml(): string {
  const btn = (g: string, inner: string, cls = '') => `<button type="button" class="qri ${cls}${W.g === g ? ' on' : ''}" data-ag="${esc(g)}" aria-pressed="${W.g === g}">${inner}</button>`;
  return btn(ON_SCREEN, `${ico(IC.check, 's')}<span class="lab">On the screen</span><span class="c">${S.cards.length}</span>`, 'q-on')
    + btn(MY, `${ico(IC.star, 's')}<span class="lab">My metrics</span><span class="c">${(ctx.metrics || []).length}</span>`, 'q-my')
    + `<div class="qrsep"></div>`
    + btn(ALL, `<span class="lab">All indicators</span><span class="c">${ctx.entries.length}</span>`)
    /* user 2026-11-08 (the Terminal's Indicators window): the groups under their section's title */
    + groupsOf().map((x, k, a) => (k === 0 || sectionOf(a[k - 1].g) !== sectionOf(x.g) ? `<div class="qrtitle">${sectionOf(x.g)}</div>` : '')
      + btn(x.g, `<span class="lab">${esc(x.label)}</span><span class="c">${x.n}</span>`)).join('');
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
  W.items = listItems(W.q, W.g, W.sort); W.act = Math.min(W.act, Math.max(0, W.items.length - 1)); W.pop = null;
  const on = S.cards.length ? screenSigs() : null;                   // nothing on the screen: no row is added
  W.added = W.items.map(it => !!on && it.ok && on.has(itemSig(it)));
  // the first rows at once, the rest in later tasks, a few dozen at a time, each written when it is drawn: every row
  // holds a select and its fields, and drawing a hundred of them in one task went over 50 ms on a busy page (report
  // 6c.9; the smoke's long-task check); the flow indicators (P5c) made the list some fifty rows longer
  clearTimeout(W.rest); W.restFrom = W.items.length;
  const rows = W.items.slice(0, FIRST_ROWS).map((it, i) => bandHtml(i) + rowHtml(it, i, W.added[i]));
  drawing = true;
  try { l.innerHTML = W.items.length
    ? `<div class="qcols" aria-hidden="true"><span>Indicator</span><span>Timeframe</span><span>Condition</span><span>Parameters &amp; threshold<em>blue = you can change it</em></span><span></span></div>` + rows.join('')
    : `<p class="qwin-empty">Nothing matches “${esc(W.q)}”. Try another name, or what it measures (for example “momentum” or “volume”).</p>` } finally { drawing = false }
  if (W.items.length > FIRST_ROWS) { W.restFrom = FIRST_ROWS; W.rest = setTimeout(drawRestStep, 0) }
  $q('#acq')?.setAttribute('aria-activedescendant', W.items.length ? 'aco' + W.act : '');
  l.style.setProperty('--qcols-h', `${l.querySelector<HTMLElement>('.qcols')?.offsetHeight || 0}px`);   // a group heading sits under the column titles
  l.scrollTop = st;
  if (fk) { const [i, f] = fk.split('|'); l.querySelector<HTMLElement>(`[data-ai="${i}"]${f}`)?.focus() }
  const r = $q('#acg'); if (r) r.innerHTML = railHtml();
  const ft = $q('#acf'); if (ft) ft.innerHTML = footHtml();
}
/** the markup of the next `n` rows not drawn yet */
function restHtml(n: number): string {
  const from = W.restFrom, to = Math.min(W.items.length, from + n);
  W.restFrom = to;
  return W.items.slice(from, to).map((it, k) => bandHtml(from + k) + rowHtml(it, from + k, W.added[from + k])).join('');
}
/** rows drawn per later task (drawList) */
const REST_ROWS = 40;
function drawRestStep() {
  if (W.restFrom >= W.items.length) return;
  $q<HTMLElement>('#acl')?.insertAdjacentHTML('beforeend', restHtml(REST_ROWS));
  if (W.restFrom < W.items.length) W.rest = setTimeout(drawRestStep, 0);
}
/** the rows not drawn yet (drawList): now, before anything needs every row (a group scroll, the arrow keys) */
function drawRest() {
  clearTimeout(W.rest);
  if (W.restFrom >= W.items.length) return;
  $q<HTMLElement>('#acl')?.insertAdjacentHTML('beforeend', restHtml(Infinity));
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
  const hd = l.querySelector<HTMLElement>('.qcols')?.offsetHeight || 0, r = g === ALL ? null : l.querySelector<HTMLElement>(`.qsec[data-sec="${CSS.escape(g)}"]`) || l.querySelector<HTMLElement>(`.qrow[data-rg="${CSS.escape(g)}"]`);
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
  const mv = d.mv != null ? `[data-mv="${CSS.escape(d.mv)}"]` : '';    // one box of a list's checkbox group
  return d.af ? `[data-af="${d.af}"]` : d.ap ? `[data-ap="${CSS.escape(d.ap)}"]${mv}` : d.ap2 ? `[data-ap2="${CSS.escape(d.ap2)}"]${mv}`
    : d.ao ? `[data-ao="${CSS.escape(d.ao)}"]` : d.aoa ? `[data-aoa="${CSS.escape(d.aoa)}"]` : null;
}
/** the field of an error key of ruleErrors */
const errSel = (k: string) => k === 'op' ? '[data-af="opt"]' : k.startsWith('o.a.') ? `[data-aoa="${CSS.escape(k.slice(4))}"]` : k.startsWith('o.') ? `[data-ao="${CSS.escape(k.slice(2))}"]` : k.startsWith('p2.') ? `[data-ap2="${CSS.escape(k.slice(3))}"]` : k.startsWith('p.') ? `[data-ap="${CSS.escape(k.slice(2))}"]` : `[data-af="${k}"]`;
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
  if (W.pop === i) fitPop(i);
  if (ff) $q<HTMLElement>(`#aco${i} ${ff}`)?.focus();
  const r = $q('#acg'); if (r) r.innerHTML = railHtml();
  const ft = $q('#acf'); if (ft) ft.innerHTML = footHtml();
}

/** Open the window. `q` searches at once (a quick chip, the builder's search box); `g` opens on a panel (My metrics). */
export function openAddCondition(q = '', g: string = ALL) {
  if (!ctx.catalog) return;
  W.q = q; W.g = g; W.act = 0; W.pop = null; W.popBox = { w:0, h:0, dx:0, dy:0 };
  dialog(`<div class="dialog qwin" role="dialog" aria-label="Add a condition">
    <div class="qwin-h"><div><strong>Add a condition</strong><small>Pick the condition next to an indicator, then click the row to add it. Click an added row to remove it. The window stays open until you close it.</small></div><button type="button" class="iconbtn sm" data-close aria-label="Close">${ico(IC.x)}</button></div>
    <div class="qwin-t"><label class="searchbox">${ico(IC.search, 's')}<input id="acq" placeholder="RSI, Stochastic, VWAP, Supertrend, breakout…" autocomplete="off" aria-label="Search indicators" role="combobox" aria-controls="acl" aria-expanded="true" value="${esc(q)}"></label>
      <label class="qwin-sort">Sort <select class="sel sm" id="acs" aria-label="Sort"><option value="group">Group</option><option value="az">Name A–Z</option><option value="za">Name Z–A</option></select></label></div>
    <div class="qwin-b"><nav class="qwin-g qrail" id="acg" aria-label="Groups"></nav><div class="qwin-split" data-wrz="split" aria-hidden="true"></div><div class="qwin-l" id="acl" role="listbox" aria-label="Indicators"></div></div>
    <div class="qwin-f" id="acf"></div>
    <span class="qwin-rz rz-l" data-wrz="l" aria-hidden="true"></span><span class="qwin-rz rz-r" data-wrz="r" aria-hidden="true"></span><span class="qwin-rz rz-b" data-wrz="b" aria-hidden="true"></span><span class="qwin-rz rz-c" data-wrz="c" aria-hidden="true"></span></div>`, o => {
    root = o.querySelector<HTMLElement>('.qwin');
    const sort = root!.querySelector<HTMLSelectElement>('#acs')!; sort.value = W.sort;
    sort.addEventListener('change', () => { W.sort = sort.value as Sort; drawList() });
    root!.querySelector<HTMLInputElement>('#acq')!.addEventListener('input', e => { W.q = (e.target as HTMLInputElement).value; W.act = 0; drawList(); const l = $q<HTMLElement>('#acl'); if (l) l.scrollTop = 0 });
    root!.querySelector('#acl')!.addEventListener('scroll', spy, { passive:true });
    root!.addEventListener('click', onClick);
    root!.addEventListener('change', onField);
    root!.addEventListener('input', onInput);
    root!.addEventListener('keydown', onKey);
    root!.addEventListener('pointerdown', onResize);
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
  const cus = t.closest<HTMLElement>('[data-cus]'), done = t.closest<HTMLElement>('[data-cusdone]'), reset = t.closest<HTMLElement>('[data-cusreset]');
  if (cus) { setPop(W.pop === Number(cus.dataset.cus) ? null : Number(cus.dataset.cus)); return }
  if (done) { setPop(null, true); return }
  if (reset) { const it = W.items[Number(reset.dataset.cusreset)]; if (it?.entry) { resetRule(it.entry); drawRow(Number(reset.dataset.cusreset)) } return }
  /* a click outside the Customize box applies it (its values are kept as they are typed) and closes it; the click does
     nothing else, as the box stands over the list (user 2026-11-08) */
  if (W.pop != null && !t.closest('.qpop')) { setPop(null); return }
  if (t.closest('select,input,.rr')) return;              // the row's own controls (a parameter's label too)
  const r = t.closest<HTMLElement>('.qrow[data-ai]'); if (r) toggle(Number(r.dataset.ai));
}
/** a rule or a threshold changed: kept per indicator; the row's "added" state follows (it compares the wire test) */
/** a parameter field's value as the card reads it (builder.ts onBuilderField): an option, true/false, or a number (NaN
    when empty, so the check names it) */
const paramValue = (p: EntryParam, el: HTMLInputElement | HTMLSelectElement): ParamValue => paramFieldValue(p, el);
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
  if (setParam(el) || setOpField(el)) { drawRow(Number(el.dataset.ai)); return }
  if (!f || !it?.entry || it.kind !== 'ind') return;
  if (f === 'opt') setOpt(it.entry, el.value);
  else { const r = ruleOf(it.entry); (r as unknown as Record<string, number | ''>)[f] = el.value.trim() === '' ? '' : Number(el.value) }
  // an operator is set in the Customize panel: it opens at once
  if (f === 'opt' && el.value === OP_OPT && ruleOf(it.entry).op) { setPop(Number(el.dataset.ai)); return }
  drawRow(Number(el.dataset.ai));
}
function onInput(e: Event) {
  const el = e.target as HTMLInputElement, f = el.dataset.af, it = W.items[Number(el.dataset.ai)];
  if (el.tagName === 'INPUT' && (setParam(el) || setOpField(el))) return;
  if (!f || f === 'opt' || !it?.entry) return;
  const r = ruleOf(it.entry); (r as unknown as Record<string, number | ''>)[f] = el.value.trim() === '' ? '' : Number(el.value);
}
/** The open Customize panel of row `i` in the middle of the screen (user 2026-11-08: "muncul di center", "bisa dibesarkan,
    dikecilkan"), at the size the user gave it and moved by what the user dragged, kept inside the screen. It replaces
    the panel under its button, which was small and could pass the list's edge (QA of unit C item 4). */
function fitPop(i: number) {
  const pop = $q<HTMLElement>(`#aco${i} .qpop`); if (!pop) return;
  if (!pop.querySelector('[data-prz]')) pop.insertAdjacentHTML('beforeend', ['l', 'r', 'b', 'c'].map(k => `<span class="qpop-rz rz-${k}" data-prz="${k}" aria-hidden="true"></span>`).join(''));
  const B = W.popBox, M = 8;
  pop.style.width = B.w ? `${Math.min(B.w, innerWidth - 2 * M)}px` : '';
  pop.style.height = B.h ? `${Math.min(B.h, innerHeight - 2 * M)}px` : '';
  const w = pop.offsetWidth, h = pop.offsetHeight;
  pop.style.left = `${Math.round(Math.min(Math.max(M, (innerWidth - w) / 2 + B.dx), innerWidth - w - M))}px`;
  pop.style.top = `${Math.round(Math.min(Math.max(M, (innerHeight - h) / 2 + B.dy), Math.max(M, innerHeight - h - M)))}px`;
}
/** the Customize box moved by its title or resized from its edges and corner; the window resized from its own edges and
    corner, and its group list's border moved (the Terminal's Indicators window) */
function onResize(e: PointerEvent) {
  const t = e.target as HTMLElement, prz = t.closest<HTMLElement>('[data-prz]')?.dataset.prz, wrz = t.closest<HTMLElement>('[data-wrz]')?.dataset.wrz;
  const head = !prz && !wrz && W.pop != null && t.closest('.qpop>strong') && !t.closest('button,select,input');
  if (e.button !== 0 || (!prz && !wrz && !head)) return;
  e.preventDefault(); t.setPointerCapture(e.pointerId);
  const x0 = e.clientX, y0 = e.clientY, pop = W.pop != null ? $q<HTMLElement>(`#aco${W.pop} .qpop`) : null, B0 = { ...W.popBox };
  const pw = pop?.offsetWidth || 0, ph = pop?.offsetHeight || 0, win = root!, ww = win.offsetWidth, wh = win.offsetHeight;
  const nav = $q<HTMLElement>('#acg'), nw = nav?.offsetWidth || 210;
  const move = (ev: PointerEvent) => {
    const dx = ev.clientX - x0, dy = ev.clientY - y0;
    if (head) W.popBox = { ...B0, w:B0.w || 0, h:B0.h || 0, dx:B0.dx + dx, dy:B0.dy + dy };
    else if (prz) {                                     // grows from the middle on the side dragged: the opposite edge stays
      const w = prz === 'b' ? pw : Math.max(300, pw + (prz === 'l' ? -dx : dx)), h = prz === 'l' || prz === 'r' ? ph : Math.max(160, ph + dy);
      W.popBox = { w, h:prz === 'l' || prz === 'r' ? (B0.h || 0) : h, dx:B0.dx + (prz === 'l' ? -(w - pw) / 2 : (w - pw) / 2) * (prz === 'b' ? 0 : 1), dy:B0.dy + (prz === 'l' || prz === 'r' ? 0 : (h - ph) / 2) };
    } else if (wrz === 'split') win.style.setProperty('--qnav', `${Math.max(160, Math.min(340, nw + dx))}px`);
    else {
      if (wrz !== 'b') win.style.width = `${Math.max(640, Math.min(innerWidth - 16, ww + 2 * (wrz === 'l' ? -dx : dx)))}px`;
      if (wrz === 'b' || wrz === 'c') win.style.height = `${Math.max(420, Math.min(innerHeight - 16, wh + 2 * dy))}px`;
    }
    if (W.pop != null) fitPop(W.pop);
  };
  const up = () => { t.removeEventListener('pointermove', move); t.removeEventListener('pointerup', up); t.removeEventListener('pointercancel', up) };
  t.addEventListener('pointermove', move); t.addEventListener('pointerup', up); t.addEventListener('pointercancel', up);
}
/** open the Customize panel of row `i` (null closes it); the panel's first field takes the focus, and closing gives it
    back to the button when `back` */
function setPop(i: number | null, back = false) {
  const was = W.pop; W.pop = i;
  if (was != null && was !== i) drawRow(was);
  if (i != null) {
    drawRow(i);
    const pop = $q<HTMLElement>(`#aco${i} .qpop`);
    pop?.querySelector<HTMLElement>('input,select')?.focus({ preventScroll:true });
    pop?.scrollIntoView({ block:'nearest' });
  } else if (back && was != null) $q<HTMLElement>(`#aco${was} [data-cus]`)?.focus();
}
function onKey(e: KeyboardEvent) {
  const t = e.target as HTMLElement, n = W.items.length;
  // Escape closes the Customize panel only, never the window behind it (the page's own Escape closes dialogs)
  if (e.key === 'Escape' && W.pop != null) { e.preventDefault(); e.stopPropagation(); setPop(null, true); return }
  if ((t.dataset.af || t.dataset.ap != null || t.dataset.ap2 != null || t.dataset.ao != null || t.dataset.aoa != null) && e.key === 'Enter' && t.tagName === 'INPUT') {
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
