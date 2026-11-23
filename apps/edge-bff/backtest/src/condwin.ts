/* EXEC-BACKTEST-REVAMP Stage D (D5; user 2026-11-15 "1 setuju, 2a": the design file is the 1:1 reference; 2026-11-16
   "Opsi C"): the condition window ("Add a condition", the design's cw*), which replaces the entry workspace. Its rows:
   - the Backtest presets (the page's flow and price-action cards, core/catalog.ts LEGACY);
   - every entry of the Screener's catalog (grammar.ts, the rows the design's CWDATA was taken from). A registry
     indicator's choice that the page's own card writes exactly (cwMap: a value, a level or an output crossing) makes that
     card, computed on the page; every other choice makes a test card in the shared grammar, computed by the worker
     (grammar.ts). A row the Backtest cannot read says why, from the engine and the catalogs (grammar.ts refusalOf), never
     from a list here; the design's mock-up wording ("Broker-flow series are in the Screener only") is gone with it.
   Side (entry, exit), search (the label counts the real rows), sort, categories, a resizable rail, Customize (the
   popover), the strategy panel, keyboard (/, arrows, Enter, Esc) as the design. "My metrics" are kept in this browser
   (ml.my: the row and its settings), a convenience of the viewer. */
import { $, esc, ico, nf, toast } from './format.ts';
import { BROKER_CODES, CAT, DATA } from './env.ts';
import { S, mkCond } from './state.ts';
import { cwMap } from './cwmap.ts';
import { CATALOG, REG_BY, catOf, condReady, mkReg, regMedian, switchedOn, withinLimit } from './reg.ts';
import type { Card, TestCard } from './api/types.ts';
import type { LegacyCard, RegCard } from './core/catalog.ts';
import { OP_CHOICE, SC, entryOf, mkTest, opWords, refusalOf, type Entry } from './grammar.ts';
import { listOf, LIST_SEP } from '../../screener/src/entries.ts';
import { markStale, renderBuilder } from './builder.ts';
import { condName, inRange, refreshSignals, signalsFor } from './signals.ts';
import { letterOf } from './lanes.ts';

type Side = 'entry' | 'exit';
type Opt = [value: string, label: string, ok: boolean];
interface Row { kind: 'pre' | 'reg' | 'test' | 'na'; n: string; c: string; ds: string; g: string; type?: string; e?: Entry; na?: string; opts: Opt[]; cs?: string }
interface Field { k: string; l: string; t: 'enum' | 'bool' | 'num' | 'text' | 'date'; v: unknown; def: unknown; opt?: [string, string][]; min?: number; max?: number; step?: number; th?: boolean }

/** the categories in the design's order, with their rail titles (cwORD, cwG) */
const ORD = ['Backtest', 'Trend', 'Momentum', 'Volatility', 'Volume', 'PriceVolume', 'Technical', 'Candlestick', 'Flow', 'Fundamental'];
const G: Record<string, [string, string]> = { Backtest: ['Backtest', 'Backtest presets'], Trend: ['Technical', 'Trend'], Momentum: ['Technical', 'Momentum'],
  Volatility: ['Technical', 'Volatility'], Volume: ['Technical', 'Volume'], PriceVolume: ['Technical', 'Price & volume'], Technical: ['Technical', 'Technical'],
  Candlestick: ['Technical', 'Candlestick patterns'], Flow: ['Flow', 'Flow & bandarmology'], Fundamental: ['Fundamental', 'Fundamental'] };
const groupOf = (g: string) => ORD.includes(g) ? g : 'Technical';

/** the window's state; rows are kept until the catalogs change (refreshCondWin) */
const CW: { side: Side; view: string; q: string; sort: string; act: number; drafts: Record<Side, Map<number, Card>>; rows: Row[] | null } =
  { side: 'entry', view: 'all', q: '', sort: 'group', act: 0, drafts: { entry: new Map(), exit: new Map() }, rows: null };

/* ---- My metrics (this browser) ---- */
interface My { row: string; card: Card }
const MY_KEY = 'ml.my';
const myList = (): My[] => { try { return JSON.parse(localStorage.getItem(MY_KEY) || '[]') } catch { return [] } };
const mySave = (l: My[]) => { try { localStorage.setItem(MY_KEY, JSON.stringify(l.slice(-50))) } catch { /* storage off: kept for this page only */ } };

/* ---- the page's own card for a registry choice: cwmap.ts (cwMap) ---- */
/** the Screener option key of a page registry card (the inverse of cwMap) */
function csOfReg(c: RegCard): string {
  const ev = c.op === 'ca' || c.op === 'cb', K = { gt: 'gt', lt: 'lt', ca: 'crosses_above', cb: 'crosses_below' }[c.op];
  if (c.lhs.t === 'out' && c.rhs.t === 'val') return `${ev ? 'event_value' : 'value'}|${c.lhs.o}|${K}`;
  if (c.lhs.t === 'price' && c.rhs.t === 'out') return `${ev ? 'event_level' : 'state_level'}|${c.rhs.o}|${K}`;
  if (c.lhs.t === 'out' && c.rhs.t === 'out') return `${ev ? 'event_output' : 'state_output'}|${c.lhs.o}|${K}`;
  return '';
}

/* ---- rows ---- */
function rows(): Row[] {
  if (CW.rows) return CW.rows;
  const out: Row[] = Object.entries(CATALOG).map(([k, e]) => ({ kind: 'pre' as const, type: k, n: e.label, c: '', ds: e.desc, g: 'Backtest', opts: e.ops.map(o => [o, (e.opLabels || {})[o] || { gt: 'Greater than', lt: 'Less than', ca: 'Crosses above', cb: 'Crosses below' }[o] || o, true] as Opt) }));
  for (const e of SC.entries) {
    const why = refusalOf(e), base = { n: e.label, c: e.key, ds: e.desc, g: groupOf(e.group), e };
    if (why) { out.push({ ...base, kind: 'na', na: why, opts: [] }); continue }
    const opts: Opt[] = e.opts.length ? e.opts.map(o => [o.key, o.label, !o.disabled]) : e.ops ? [[OP_CHOICE, opWords(e, mkTest(e, 'probe')), true]] : [];
    const reg = e.kind === 'indicator' && !!REG_BY[e.key] && e.opts.some(o => cwMap(e.key, o));
    out.push({ ...base, kind: reg ? 'reg' : 'test', opts, cs: e.opts.length ? e.def.opt : OP_CHOICE });
  }
  CW.drafts.entry.clear(); CW.drafts.exit.clear();
  return CW.rows = out;
}
/** how many of the window's rows can be added (the builder's search label "Search N indicators to add", decision 2a:
    the real number; a row that says "Not in backtest" is not counted, Agent 10, M460 item 8) */
export const condWinCount = (): number => SC.state === 'ready' ? rows().filter(r => r.kind !== 'na').length : 0;

/** a card for row `r` at choice `cs` (a page card where the page writes it exactly, else a test card) */
function cardFor(r: Row, cs: string, id = Math.random().toString(36).slice(2, 8)): Card {
  if (r.kind === 'pre') { const c = mkCond(r.type!); c.id = id; c.op = cs || c.op; return c }
  const e = r.e!, m = r.kind === 'reg' ? cwMap(e.key, e.opts.find(o => o.key === cs)) : null;
  if (m) {
    const c = mkReg(e.key); c.id = id; c.lhs = m.lhs; c.op = m.op;
    c.rhs = m.rhs.t === 'val' ? { t: 'val', v: c.rhs.t === 'val' ? c.rhs.v : regMedian(e.key, c.p, (m.lhs as { o: string }).o) } : m.rhs;
    if (m.rhs.t === 'val' && m.lhs.t === 'out' && (c.rhs as { v: number }).v === 0) c.rhs = { t: 'val', v: regMedian(e.key, c.p, m.lhs.o) };
    return c;
  }
  const t = mkTest(e, id);
  if (cs !== OP_CHOICE) t.sc.opt = cs || t.sc.opt;
  return t;
}
const csOf = (c: Card): string => c.type === 'test' ? (c.sc.op && !c.sc.opt ? OP_CHOICE : c.sc.opt) : c.type === 'reg' ? csOfReg(c) : (c as LegacyCard).op;
const rowOf = (c: Card): number => rows().findIndex(r => c.type === 'test' ? r.e?.key === c.entry : c.type === 'reg' ? r.e?.key === c.ind && r.kind !== 'na' : r.kind === 'pre' && r.type === c.type);
const draft = (i: number): Card => {
  const d = CW.drafts[CW.side];
  let c = d.get(i);
  if (!c) { const r = rows()[i]; c = cardFor(r, r.cs ?? r.opts.find(o => o[2])?.[0] ?? ''); d.set(i, c) }
  return c;
};
const list = (side: Side = CW.side) => side === 'exit' ? S.exitConds : S.conds;
const added = (i: number, side: Side = CW.side) => { const r = rows()[i]; return list(side).filter(c => rowOf(c) === i && r.kind !== 'na') };
const find = (id: string) => S.conds.find(c => c.id === id) || S.exitConds.find(c => c.id === id);

/* ---- fields ---- */
function fields(c: Card): Field[] {
  if (c.type === 'test') {
    const e = entryOf(c);
    if (!e) return [];
    const o = e.opts.find(x => x.key === c.sc.opt), out: Field[] = e.params.map(p => {
      const v = c.sc.params[p.key], base = { k: 's.' + p.key, l: p.label || p.key, v, def: p.default };
      if (p.type === 'enum' && p.options) return { ...base, t: 'enum' as const, opt: p.options.map(x => [x, p.option_labels?.[x] ?? x] as [string, string]) };
      if (p.type === 'boolean') return { ...base, t: 'bool' as const };
      if (p.type === 'integer' || p.type === 'number') return { ...base, t: 'num' as const, min: p.min, max: p.max, step: p.integer || p.type === 'integer' ? 1 : undefined };
      if (p.type === 'date') return { ...base, t: 'date' as const };
      return { ...base, t: 'text' as const, l: `${p.label || p.key} (${p.type === 'brokers' ? 'broker codes' : 'choices'}, separated by ${LIST_SEP})` };
    });
    if (o?.value === 'input') {
      out.push({ k: 'value', l: o.between ? 'From' : 'Value' + (o.unit ? ` (${o.unit})` : ''), t: 'num', v: c.sc.value, def: e.def.value, th: true });
      if (o.between) out.push({ k: 'value2', l: 'To', t: 'num', v: c.sc.value2, def: e.def.value2, th: true });
    }
    if (o?.within) out.push({ k: 'within', l: 'Within (sessions)', t: 'num', v: c.sc.within, def: e.def.within, min: 1, step: 1, th: true });
    if (c.sc.op && !o) out.push({ k: 'op.value', l: 'Value', t: 'num', v: c.sc.op.value, def: null, th: true });
    return out;
  }
  if (c.type !== 'reg') {
    const e = CATALOG[c.type], lc = c as LegacyCard, f: Field[] = e.params.map(([k, l, d]) => ({ k, l, t: k === 'broker' ? 'enum' : 'num', v: lc[k], def: d,
      opt: k === 'broker' ? (Object.keys(BROKERS())).map(x => [x, x] as [string, string]) : undefined }));
    if (!e.noVal) f.push({ k: 'val', l: 'Value' + (e.unit ? ` (${e.unit})` : ''), t: 'num', v: lc.val, def: e.val, th: true });
    return f;
  }
  const t = REG_BY[c.ind], f: Field[] = t.p.filter(p => p.t !== 'fixed').map(p => ({ k: 'p.' + p.k, l: p.l, t: p.t === 'enum' ? 'enum' : p.t === 'boolean' ? 'bool' : 'num',
    v: c.p[p.k], def: p.d, opt: p.t === 'enum' ? (p.opt || []).map((x: string) => [x, x] as [string, string]) : undefined, min: p.min, max: p.max, step: p.step }));
  if (c.rhs.t === 'val') f.push({ k: 'rhs', l: 'Value', t: 'num', v: c.rhs.v, def: null, th: true });
  return f;
}
const BROKERS = (): Record<string, true> => Object.fromEntries(BROKER_CODES().map(b => [b, true]));
function setField(c: Card, k: string, v: string) {
  const n = (x: string) => x === '' || isNaN(+x) ? x : +x;
  if (c.type === 'test') {
    const e = entryOf(c);
    if (k === 'value' || k === 'value2' || k === 'within') { (c.sc as unknown as Record<string, unknown>)[k] = v === '' ? '' : +v; return }
    if (k === 'op.value' && c.sc.op) { c.sc.op = { ...c.sc.op, value: v === '' ? '' : +v }; return }
    const p = e?.params.find(q => 's.' + q.key === k);
    if (!p) return;
    c.sc.params[p.key] = p.type === 'boolean' ? v === 'true' : p.type === 'integer' || p.type === 'number' ? n(v) as number
      : p.type === 'multi' || p.type === 'brokers' ? listOf(v.replace(/\s+/g, '')).join(LIST_SEP) : v;
    return;
  }
  if (k === 'rhs' && c.type === 'reg' && c.rhs.t === 'val') { c.rhs.v = +v; return }
  if (k === 'val') { (c as LegacyCard).val = +v; return }
  if (k.startsWith('p.') && c.type === 'reg') { const p = REG_BY[c.ind].p.find(q => q.k === k.slice(2)); c.p[k.slice(2)] = p && p.t === 'boolean' ? v === 'true' : p && p.t === 'enum' ? v : n(v); return }
  (c as LegacyCard)[k] = k === 'broker' ? v : n(v);
}
/** a card at another choice (the same card, or a new one of the other kind with its id) */
function withChoice(c: Card, cs: string): Card {
  const i = rowOf(c), r = rows()[i];
  if (!r) return c;
  if (r.kind === 'pre') { (c as LegacyCard).op = cs; return c }
  const next = cardFor(r, cs, c.id);
  next.on = c.on;
  if (next.type === 'reg' && c.type === 'reg') { next.p = { ...c.p }; if (next.rhs.t === 'val' && c.rhs.t === 'val') next.rhs = { t: 'val', v: c.rhs.v } }
  if (next.type === 'test' && c.type === 'test' && cs !== OP_CHOICE) { next.sc = { ...c.sc, opt: cs } }
  return next;
}
const replaceIn = (c: Card, next: Card) => { for (const L of [S.conds, S.exitConds]) { const k = L.indexOf(c); if (k >= 0) L[k] = next } };

/* ---- markup ---- */
const fieldHTML = (f: Field, cls: string, tag: string) => {
  const chg = f.def != null && String(f.v) !== String(f.def) ? 'chg' : '', at = `data-cwk="${esc(f.k)}" data-cwt="${tag}" aria-label="${esc(f.l)}"`;
  const inp = f.t === 'enum' ? `<select class="sel ${chg}" ${at}>${(f.opt || []).map(([a, b]) => `<option value="${esc(a)}" ${String(a) === String(f.v) ? 'selected' : ''}>${esc(b)}</option>`).join('')}</select>`
    : f.t === 'bool' ? `<select class="sel ${chg}" ${at}><option value="true" ${f.v ? 'selected' : ''}>Yes</option><option value="false" ${f.v ? '' : 'selected'}>No</option></select>`
    : f.t === 'text' || f.t === 'date' ? `<input class="inp ${chg}" type="${f.t === 'date' ? 'date' : 'text'}" value="${esc(f.v)}" ${at}>`
    : `<input class="inp ${chg}" type="number" ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} step="${f.step || 'any'}" value="${esc(f.v)}" style="--n:${String(f.v ?? '').length}" ${at}>`;
  return `<label class="${cls}"><span class="lab">${esc(f.l)}</span>${inp}${cls.startsWith('qpl') ? `<span class="def">${f.def != null && f.def !== '' ? 'default ' + esc(f.def) : ''}</span>` : ''}</label>`;
};
const optsOf = (c: Card): Opt[] => { const r = rows()[rowOf(c)]; return r ? r.opts : [] };
function visible(): number[] {
  const R = rows(), q = CW.q.trim().toLowerCase(), my = myList();
  let ids = R.map((_, i) => i);
  if (CW.view === 'on') ids = ids.filter(i => added(i).length);
  else if (CW.view === 'my') ids = [...new Set(my.map(x => R.findIndex(r => (r.e?.key ?? r.type) === x.row)).filter(i => i >= 0))];
  else if (CW.view !== 'all') ids = ids.filter(i => R[i].g === CW.view);
  if (q) ids = ids.filter(i => { const r = R[i]; return [r.n, r.c, r.ds, ...r.opts.map(x => x[1]), ...(r.e?.synonyms ?? [])].join(' ').toLowerCase().includes(q) });
  if (CW.sort !== 'group') ids.sort((a, b) => R[a].n.localeCompare(R[b].n) * (CW.sort === 'az' ? 1 : -1));
  else ids.sort((a, b) => ORD.indexOf(R[a].g) - ORD.indexOf(R[b].g) || a - b);
  return ids;
}
function rowHTML(i: number, k: number): string {
  const r = rows()[i], act = k === CW.act ? 'act' : '';
  const name = `<span class="qnl"><b>${esc(r.n)}</b>${r.c ? `<small class="qcode">${esc(r.c)}</small>` : ''}`;
  if (r.kind === 'na') return `<div class="qrow na ${act}" data-ai="${i}" role="option" aria-disabled="true" aria-selected="${k === CW.act}"><span class="qnm">${name}</span><small class="qdesc">${esc(r.na)}</small></span><span class="qna"><span class="pill warn">Not in backtest</span></span></div>`;
  const d = draft(i), n = added(i).length, fs = fields(d), cs = csOf(d), ready = condReady(d);
  const prm = fs.length > 2 ? `<button type="button" class="qcus ${fs.some(f => f.def != null && String(f.v) !== String(f.def)) ? 'chg' : ''}" data-cwcus="${i}" aria-haspopup="dialog" title="${fs.length} fields you can change">${ico('<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>')}<span class="t">Customize</span><span class="n">${fs.length}</span></button>`
    : fs.map(f => fieldHTML(f, 'qbox', 'd' + i)).join('');
  // why a row's card would be left out of a run (compute.ts ready): a test card's fields not valid yet, any other card's
  // indicator not calculated on this page (the builder card's and the design's "Not calculated"; Agent 10, M460 item 7)
  const why = ready ? '' : d.type === 'test' ? '<span class="pill warn" title="Its fields are not valid yet: it is kept but left out of a run">Check fields</span>'
    : `<span class="pill warn" title="${esc((CATALOG as Record<string, { group?: string }>)[d.type]?.group === 'flow' && CAT.flow.reason ? CAT.flow.reason : 'Not calculated on this page: it is kept but left out of a run')}">Not calculated</span>`;
  return `<div class="qrow ${n ? 'isadd' : ''} ${act}" data-ai="${i}" role="option" aria-selected="${k === CW.act}"><span class="qnm">${name}${why}</span><small class="qdesc" title="${esc(r.ds)}">${esc(r.ds)}</small></span>
  <span class="qs"><select class="sel" data-cwcs="${i}" aria-label="Condition for ${esc(r.n)}">${r.opts.map(([v, l, ok]) => `<option value="${esc(v)}" ${v === cs ? 'selected' : ''} ${ok ? '' : 'disabled'}>${esc(l)}${ok ? '' : ' · not offered'}</option>`).join('')}</select></span>
  <span class="qt">${prm}</span><button type="button" class="qact ${n ? 'on' : ''}" data-cwadd="${i}" tabindex="-1" title="${n ? 'Remove from ' + CW.side : 'Add to ' + CW.side}">${n ? `<span class="q-on">${ico('<path d="M5 12.5l4.5 4.5L19 7.5"/>')}Added</span><span class="q-rm">Remove</span>` : 'Add'}</button></div>`;
}
function railHTML(): string {
  const R = rows(), on = R.filter((_, i) => added(i).length).length;
  let h = `<button class="qri q-on ${CW.view === 'on' ? 'on' : ''}" data-cwv="on">${ico('<path d="M5 12.5l4.5 4.5L19 7.5"/>')}<span class="lab">On the strategy</span><span class="c">${on}</span></button><button class="qri q-my ${CW.view === 'my' ? 'on' : ''}" data-cwv="my">${ico('<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/>')}<span class="lab">My metrics</span><span class="c">${myList().length}</span></button><span class="qrsep"></span><button class="qri ${CW.view === 'all' ? 'on' : ''}" data-cwv="all"><span class="lab">All indicators</span><span class="c">${R.length}</span></button>`;
  let last = '';
  for (const g of ORD) {
    const [t, l] = G[g], n = R.filter(r => r.g === g).length;
    if (!n) continue;
    if (t !== last) { h += `<span class="qrtitle">${t}</span>`; last = t }
    h += `<button class="qri ${CW.view === g ? 'on' : ''}" data-cwv="${g}"><span class="lab">${l}</span><span class="c">${n}</span></button>`;
  }
  return h;
}
/** how often a strategy card is true on the chart's stock inside the period (the design's ld) */
function stat(c: Card): { txt: string; cls: string } {
  if (!condReady(c)) return { txt: 'Check fields', cls: 'warn' };
  if (!c.on) return { txt: 'Off', cls: 'neu' };
  const tk = S.sigTicker, t = DATA[tk] ? DATA[tk].dates : [];
  const s = signalsFor(tk).series.find(x => x.c === c)?.s;
  if (!s) return { txt: c.type === 'test' ? 'computed on the server' : '—', cls: 'neu' };
  let on = 0, n = 0;
  for (let a = 1; a < t.length; a++) if (inRange(t, a)) { n++; if (s[a]) on++ }
  return { txt: `${nf(n ? on / n * 100 : 0, 1)}% of days`, cls: 'pos' };
}
function stratHTML(): string {
  const L = list(), ex = CW.side === 'exit';
  const rule = ex ? `<div class="sp-rule"><span>Exit when</span><span class="seg sm">${([['any', 'Any'], ['all', 'All']] as const).map(([v, l]) => `<button class="${S.exitLogic === v ? 'on' : ''}" data-cwxl="${v}">${l}</button>`).join('')}</span><span class="muted">of the exit conditions is true, together with the stop, target, trailing and time rules in step 3</span></div>`
    : `<div class="sp-rule"><span>Enter when</span><span class="seg sm">${([['all', 'All'], ['any', 'Any'], ['n', 'At least']] as const).map(([v, l]) => `<button class="${S.logic === v ? 'on' : ''}" data-cwlg="${v}">${l}</button>`).join('')}</span>${S.logic === 'n' ? `<input class="inp nn" type="number" min="1" value="${S.atLeast}" data-cwrk="atLeast" aria-label="At least">` : ''}<span>met within</span><input class="inp nn" type="number" min="1" max="20" value="${S.window}" data-cwrk="window" aria-label="Window in bars"><span>bars</span></div>`;
  return `<div class="sp-h"><b>${ex ? 'Exit' : 'Entry'} conditions</b><span class="muted">${L.filter(c => c.on).length} of ${L.length} on</span><button type="button" class="qs-col" data-cwcol title="Hide this panel to give the list more room">Hide <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button></div>${rule}<div class="sp-l">${L.length ? L.map((c, k) => {
    const s = stat(c), label = catOf(c).label;
    return `<div class="spc ${c.on ? '' : 'off'}" data-cwcard="${c.id}"><div class="spc-t"><span class="bd">${letterOf(k)}</span><b title="${esc(label)}">${esc(label)}</b><span class="sw ${c.on ? 'on' : ''}" role="switch" tabindex="0" aria-checked="${c.on}" data-cwsw="${c.id}" title="Turn on or off"><i></i></span><button class="ib" data-cwdup="${c.id}" title="Copy to ${ex ? 'entry' : 'exit'}" aria-label="Copy to ${ex ? 'entry' : 'exit'}">${ico('<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>')}</button><button class="ib rm" data-cwrm="${c.id}" title="Remove" aria-label="Remove ${esc(label)}">${ico('<path d="M6 6l12 12M18 6 6 18"/>')}</button></div>
   <div class="spc-s">${esc(condName(c))}</div><div class="spc-f"><span class="pill ${s.cls}">${s.cls === 'pos' ? 'true on ' + s.txt : esc(s.txt)}</span><button class="btn sm" data-cwedit="${c.id}" title="Open Customize">${ico('<path d="M4 20h4L18.5 9.5a2.1 2.1 0 0 0-3-3L5 17v3z"/>')}Edit</button></div></div>`;
  }).join('') : `<div class="sp-empty">No ${ex ? 'exit' : 'entry'} condition yet.<br>Select a row on the left and press Add.</div>`}</div>`;
}

/* ---- render and actions ---- */
const commit = () => { markStale(); renderBuilder(); refreshSignals(); render() };
export function render(keep = true) {
  const W = $('cw');
  if (!W || W.hidden) return;
  const L = $('cwList'), top = L.scrollTop;
  $('cwSide').innerHTML = (['entry', 'exit'] as const).map(s => `<button class="${CW.side === s ? 'on' : ''}" data-cwside="${s}">${s === 'entry' ? 'Entry' : 'Exit'}<span class="n">${list(s).length}</span></button>`).join('');
  $('cwQ').placeholder = SC.state === 'ready' ? 'RSI, Stochastic, VWAP, Supertrend, foreign flow, breakout…' : SC.state === 'failed' ? 'The catalog could not be read' : 'Loading the catalog…';
  $('cwRail').innerHTML = railHTML();
  const ids = visible(), R = rows();
  let h = '', last: string | null = null;
  ids.forEach((i, k) => {
    const g = R[i].g;
    if (CW.sort === 'group' && CW.view !== 'on' && g !== last) { h += `<div class="qsec">${G[g][1]}<span>${ids.filter(j => R[j].g === g).length}</span></div>`; last = g }
    h += rowHTML(i, k);
  });
  L.innerHTML = h || `<div class="qwin-empty">${SC.state === 'failed' ? esc('The catalog could not be read: ' + SC.reason) : CW.view === 'on' ? 'Nothing from the catalog on this side yet.' : CW.view === 'my' ? 'No saved metrics yet. Open Customize on a row and choose “Save as My metric”.' : 'No indicator matches “' + esc(CW.q) + '”.'}</div>`;
  if (keep) L.scrollTop = top;
  $('cwStrat').innerHTML = stratHTML();
  const n = list().length, tb = $('cwStab');
  if (tb) tb.innerHTML = `<i>${n}</i><span>${CW.side === 'exit' ? 'Exit' : 'Entry'} conditions</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 6-6 6 6 6"/></svg>`;
  const tk = S.sigTicker, D = DATA[tk] ? DATA[tk].dates : [], sig = DATA[tk] ? signalsFor(tk) : null;
  let ns = 0;
  if (sig) for (let a = 1; a < D.length; a++) if (inRange(D, a) && sig.entry[a] && !sig.entry[a - 1]) ns++;
  $('cwSig').innerHTML = `Entry signals <b>${ns}</b> <span class="muted">· ${esc(tk)}</span>`;
  $('cwCount').textContent = `${S.conds.length} entry · ${S.exitConds.length} exit conditions`;
  bind();
}
function toggle(i: number) {
  const r = rows()[i];
  if (!r || r.kind === 'na') return;
  const L = list(), a = added(i);
  if (a.length) { const c = a[a.length - 1]; L.splice(L.indexOf(c), 1); toast(`${r.n} removed from ${CW.side}`) }
  else {
    const c = JSON.parse(JSON.stringify(draft(i))) as Card;
    c.id = Math.random().toString(36).slice(2, 8); c.on = true;
    if (c.type === 'test') c.sc.id = c.id;
    if (!withinLimit(L, [...L, c])) return;
    L.push(c); toast(`${r.n} added to ${CW.side}`);
  }
  commit();
}
function bind() {
  const W = $('cw') as HTMLElement;
  W.querySelectorAll<HTMLElement>('[data-cwside]').forEach(b => b.onclick = () => { CW.side = b.dataset.cwside as Side; CW.act = 0; $('cwPop').hidden = true; render() });
  W.querySelectorAll<HTMLElement>('[data-cwv]').forEach(b => b.onclick = () => { CW.view = b.dataset.cwv!; CW.act = 0; render(false) });
  W.querySelectorAll<HTMLElement>('#cwList .qrow').forEach(r => r.onclick = (e: MouseEvent) => {
    if ((e.target as HTMLElement).closest('select,input,label,.qcus,.qact')) return;
    const all = [...r.parentNode!.querySelectorAll('.qrow')];
    CW.act = all.indexOf(r);
    all.forEach((x, k) => { x.classList.toggle('act', k === CW.act); x.setAttribute('aria-selected', String(k === CW.act)) });
  });
  W.querySelectorAll<HTMLElement>('[data-cwadd]').forEach(b => b.onclick = (e: MouseEvent) => { e.stopPropagation(); toggle(+b.dataset.cwadd!) });
  W.querySelectorAll<HTMLSelectElement>('[data-cwcs]').forEach(s => s.onchange = () => { const i = +s.dataset.cwcs!; CW.drafts[CW.side].set(i, withChoice(draft(i), s.value)); render() });
  W.querySelectorAll<HTMLInputElement>('#cwList [data-cwk]').forEach(x => x.onchange = () => { setField(draft(+x.dataset.cwt!.slice(1)), x.dataset.cwk!, x.value); render() });
  W.querySelectorAll<HTMLElement>('[data-cwcus]').forEach(b => b.onclick = (e: MouseEvent) => { e.stopPropagation(); const i = +b.dataset.cwcus!; pop(draft(i), b, rows()[i].n, i) });
  W.querySelectorAll<HTMLElement>('[data-cwlg]').forEach(b => b.onclick = () => { S.logic = b.dataset.cwlg as typeof S.logic; commit() });
  W.querySelectorAll<HTMLElement>('[data-cwxl]').forEach(b => b.onclick = () => { S.exitLogic = b.dataset.cwxl as typeof S.exitLogic; commit() });
  W.querySelectorAll<HTMLInputElement>('[data-cwrk]').forEach(b => b.onchange = () => { (S as unknown as Record<string, number>)[b.dataset.cwrk!] = Math.max(1, Math.round(+b.value || 1)); commit() });
  W.querySelectorAll<HTMLElement>('[data-cwsw]').forEach(b => {
    const f = () => { const c = find(b.dataset.cwsw!), L = list(); if (!c) return; if (!c.on && !withinLimit(L, switchedOn(L, c))) return; c.on = !c.on; commit() };
    b.onclick = f; b.onkeydown = (e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); f() } };
  });
  W.querySelectorAll<HTMLElement>('[data-cwrm]').forEach(b => b.onclick = () => { const L = list(), c = find(b.dataset.cwrm!); if (!c) return; L.splice(L.indexOf(c), 1); $('cwPop').hidden = true; toast(`${catOf(c).label} removed`); commit() });
  W.querySelectorAll<HTMLElement>('[data-cwdup]').forEach(b => b.onclick = () => {
    const c = find(b.dataset.cwdup!), O = CW.side === 'entry' ? S.exitConds : S.conds;
    if (!c) return;
    const n = JSON.parse(JSON.stringify(c)) as Card; n.id = Math.random().toString(36).slice(2, 8); if (n.type === 'test') n.sc.id = n.id;
    if (!withinLimit(O, [...O, n])) return;
    O.push(n); toast(`Copied to ${CW.side === 'entry' ? 'exit' : 'entry'}`); commit();
  });
  W.querySelectorAll<HTMLElement>('[data-cwedit]').forEach(b => b.onclick = () => { const c = find(b.dataset.cwedit!); if (c) pop(c, b, catOf(c).label, null, true) });
}
/** Customize: every field of a card (a draft row's, or a strategy card's live) */
function pop(c0: Card, anchor: HTMLElement, title: string, rowI: number | null, live = false, keep = false) {
  let c = c0;
  const P = $('cwPop') as HTMLElement, fs = fields(c), ps = fs.filter(f => !f.th), ts = fs.filter(f => f.th), cs = csOf(c), opts = optsOf(c);
  P.innerHTML = `<strong>${esc(title)}<span class="muted">${live ? 'On the ' + CW.side + ' side' : 'Not added yet'}</span><button type="button" class="ib" data-cwpx aria-label="Close" title="Close (Esc)">${ico('<path d="M6 6l12 12M18 6 6 18"/>')}</button></strong>
  <label class="qpl"><span class="lab">Condition</span><select class="sel" data-cwpcs aria-label="Condition">${opts.map(([v, l, ok]) => `<option value="${esc(v)}" ${v === cs ? 'selected' : ''} ${ok ? '' : 'disabled'}>${esc(l)}${ok ? '' : ' · not offered'}</option>`).join('')}</select><span class="def"></span></label>
  ${ps.map(f => fieldHTML(f, 'qpl', 'p')).join('')}${ts.length ? '<span class="qsep"></span>' : ''}${ts.map(f => fieldHTML(f, 'qpl thr', 'p')).join('')}
  <span class="qpf"><button type="button" class="link" data-cwpr>Reset to default</button>${rowI != null ? '<button type="button" class="link" data-cwpm>Save as My metric</button>' : ''}<span class="sp"></span><button type="button" class="btn sm dark" data-cwpd>Done</button></span>`;
  P.hidden = false;
  if (!keep) { P.style.left = Math.max(12, Math.round((innerWidth - P.offsetWidth) / 2)) + 'px'; P.style.top = Math.max(12, Math.round((innerHeight - P.offsetHeight) / 2)) + 'px' }
  const again = () => { if (live) commit(); else render(); pop(c, anchor, title, rowI, live, true) };
  (P.querySelector('[data-cwpx]') as HTMLElement).onclick = (P.querySelector('[data-cwpd]') as HTMLElement).onclick = () => { P.hidden = true; anchor.focus?.() };
  (P.querySelector('[data-cwpcs]') as HTMLSelectElement).onchange = (e: Event) => {
    const next = withChoice(c, (e.target as HTMLSelectElement).value);
    if (live) replaceIn(c, next); else if (rowI != null) CW.drafts[CW.side].set(rowI, next);
    c = next; again();
  };
  P.querySelectorAll<HTMLInputElement>('[data-cwk]').forEach(x => x.onchange = () => { setField(c, x.dataset.cwk!, x.value); again() });
  (P.querySelector('[data-cwpr]') as HTMLElement).onclick = () => { fs.forEach(f => { if (f.def != null) setField(c, f.k, String(f.def)) }); again() };
  const sm = P.querySelector('[data-cwpm]') as HTMLElement | null;
  if (sm && rowI != null) sm.onclick = () => { const r = rows()[rowI]; mySave([...myList(), { row: r.e?.key ?? r.type ?? '', card: JSON.parse(JSON.stringify(c)) }]); toast(`Saved “${title}” in My metrics`); render() };
  const hd = P.querySelector('strong') as HTMLElement;
  hd.onpointerdown = (e: PointerEvent) => {
    if ((e.target as HTMLElement).closest('button')) return;
    const x0 = e.clientX - P.offsetLeft, y0 = e.clientY - P.offsetTop;
    hd.setPointerCapture(e.pointerId);
    hd.onpointermove = (v: PointerEvent) => { P.style.left = v.clientX - x0 + 'px'; P.style.top = v.clientY - y0 + 'px' };
    hd.onpointerup = () => { hd.onpointermove = null };
  };
  (P.querySelector('select,input') as HTMLElement | null)?.focus();
}
let lastFocus: HTMLElement | null = null;
/** open the window on a side; `sel` a card of the strategy: its Customize at once */
export function openCondWin(sel: { kind: string; id: string } | null, side: Side = 'entry') {
  init();
  const W = $('cw') as HTMLElement;
  lastFocus = document.activeElement as HTMLElement | null;
  if (side) CW.side = side;
  W.hidden = false; document.body.classList.add('cwopen');
  render(false);
  if (sel && sel.kind === 'cond') {
    const c = find(sel.id);
    if (c) { CW.side = S.exitConds.includes(c) ? 'exit' : 'entry'; render(false);
      setTimeout(() => { const b = W.querySelector<HTMLElement>(`[data-cwedit="${c.id}"]`); if (b) { b.scrollIntoView({ block: 'nearest' }); pop(c, b, catOf(c).label, null, true) } }, 30) }
  } else setTimeout(() => ($('cwQ') as HTMLInputElement).focus(), 30);
}
export function closeCondWin() {
  ($('cw') as HTMLElement).hidden = true; ($('cwPop') as HTMLElement).hidden = true; document.body.classList.remove('cwopen');
  // the focus goes back to what opened the window; an add or a remove draws the builder again, so that element may be
  // gone: its new copy (the same id), else the builder's search box
  const back = lastFocus?.isConnected ? lastFocus : (lastFocus?.id && document.getElementById(lastFocus.id)) || document.getElementById('wsOpen');
  back?.focus?.();
}
let ready = false;
function init() {
  if (ready) return;
  ready = true;
  const W = $('cw') as HTMLElement;
  ($('cwQ') as HTMLInputElement).oninput = (e: Event) => { CW.q = (e.target as HTMLInputElement).value; CW.act = 0; if (CW.q && !['all', 'on', 'my'].includes(CW.view)) CW.view = 'all'; render(false) };
  ($('cwSort') as HTMLSelectElement).onchange = (e: Event) => { CW.sort = (e.target as HTMLSelectElement).value; render(false) };
  W.querySelectorAll<HTMLElement>('[data-cwclose]').forEach(b => b.onclick = closeCondWin);
  W.onclick = (e: MouseEvent) => { if (e.target === W) closeCondWin() };
  // the strategy panel on a phone: a tab shows it, Hide closes it (the design's own script, here in source)
  W.addEventListener('click', (e: MouseEvent) => {
    const t = e.target as HTMLElement, win = $('cwWin') as HTMLElement;
    if (t.closest('#cwStab')) { win.classList.remove('xs-sc'); t.closest('#cwStab')!.setAttribute('aria-expanded', 'true'); (win.querySelector('.qs-col') as HTMLElement | null)?.focus() }
    else if (t.closest('[data-cwcol]')) { win.classList.add('xs-sc'); const tab = $('cwStab'); if (tab) { tab.setAttribute('aria-expanded', 'false'); tab.focus() } }
  });
  const sp = $('cwSplit') as HTMLElement;
  sp.onpointerdown = (e: PointerEvent) => {
    sp.setPointerCapture(e.pointerId);
    const x0 = e.clientX, w0 = ($('cwRail') as HTMLElement).offsetWidth;
    sp.onpointermove = (v: PointerEvent) => { ($('cwWin') as HTMLElement).style.setProperty('--qnav', Math.max(160, Math.min(320, w0 + v.clientX - x0)) + 'px') };
    sp.onpointerup = () => { sp.onpointermove = null };
  };
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (W.hidden) return;
    const t = e.target as HTMLElement;
    if (e.key === 'Escape') { e.stopPropagation(); e.preventDefault(); if (($('cwPop') as HTMLElement).hidden) closeCondWin(); else ($('cwPop') as HTMLElement).hidden = true; return }
    if (t.closest('#cwPop')) return;
    // focus stays inside the window (a modal dialog): Tab from its last control goes to its first
    if (e.key === 'Tab') {
      const f = [...($('cwWin') as HTMLElement).querySelectorAll<HTMLElement>('button,select,input,[tabindex="0"]')].filter(x => !x.hidden && x.offsetParent !== null);
      if (f.length && e.shiftKey && t === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
      else if (f.length && !e.shiftKey && t === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
      return;
    }
    const R = [...($('cwList') as HTMLElement).querySelectorAll<HTMLElement>('.qrow')];
    if (e.key === '/' && !t.closest('input,select')) { e.preventDefault(); ($('cwQ') as HTMLInputElement).focus(); return }
    if (!R.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (t.closest('select')) return;
      e.preventDefault();
      CW.act = Math.max(0, Math.min(R.length - 1, CW.act + (e.key === 'ArrowDown' ? 1 : -1)));
      R.forEach((r, k) => { r.classList.toggle('act', k === CW.act); r.setAttribute('aria-selected', String(k === CW.act)) });
      R[CW.act].scrollIntoView({ block: 'nearest' });
    }
    if (e.key === 'Enter' && !t.closest('select,button,.sw,input')) {
      e.preventDefault();
      const r = R[CW.act];
      if (r && !r.classList.contains('na')) toggle(+r.dataset.ai!);
    }
  }, true);
}
/** the window's rows again (the catalog answered, or the backtest catalog changed what it can read) */
export const refreshCondWin = () => { CW.rows = null; render() };
