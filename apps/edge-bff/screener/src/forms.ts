/* A condition card as the page keeps it, and its wire form (report API CONTRACT 8.5 tests and metric references;
   contract.ts TestForm, the 14 forms of report 6.9.1). toWire builds the ConditionDef the worker validates; fromWire
   maps a wire condition (a preset's, a saved screen's, a My metric's) back onto a card. A wire condition the page
   cannot map is kept as it is (a "raw" card): it runs, it can be switched off or removed, never edited or changed
   silently (report 9.5 "nothing is adjusted silently"). Pure: no DOM, no formula. */
import type {
  ConditionDef, IndicatorRef, MetricRef, ParamMap, ParamValue, Side, Test, TestOp, ValueTest,
} from './core/contract.ts';
import { defaultParams, isDefP, OPLABEL, optionText, type Entry, type Opt } from './entries.ts';

export interface Card {
  id: string;                  // ^[0-9a-z]{1,6}$, unique in the screen
  on: boolean;
  entry: string | null;        // Entry.key; null = a raw card (wire kept as is)
  params: ParamMap;            // the entry's parameters, every key present
  opt: string;                 // Opt.key
  value: number | ''; value2: number | ''; within: number | '';
  second: ParamMap;            // the second instance's parameters (state_instance / event_instance)
  label?: string;
  metric?: { item_id: string; name: string; params: ParamMap };   // a My metric link (prototype c.m / mName / mp)
  raw?: Test;                  // a raw card's wire test
  rawName?: string;            // a raw card's name: the catalog's name of what its test reads (fromWire; never on the wire)
  review?: string[];           // needs_review fields of a loaded saved screen (report 9.5), shown, never adjusted
}

/** Display scale of a value field by unit: IDR values are typed in Rp B, as the prototype's money fields. */
export const displayScale = (unit: string | null | undefined) => (unit || '').toUpperCase() === 'IDR' ? 1e9 : 1;
export const displayUnit = (unit: string | null | undefined) => {
  const u = (unit || '').toLowerCase();
  return u === 'idr' ? 'Rp B' : u === '%' || u === 'percent' || u === 'pct' ? '%' : u === 'x' || u === 'ratio' || u === 'multiple' ? '×' : u === 'days' || u === 'sessions' ? 'sessions' : '';
};

let uid = 0;
/** a fresh condition id not used by `taken` (base 36 of a counter: '1', '2', ... 'a', ...; contract CONDITION_ID) */
export function newCardId(taken: Iterable<string>): string {
  const used = new Set(taken);
  let id: string;
  do id = (++uid).toString(36); while (used.has(id) || id.length > 6);
  return id;
}

/** A new card on an entry, at its default test (the overlay's default_test) and default parameters. */
export function newCard(e: Entry, taken: Iterable<string>, over: Partial<Card> = {}): Card {
  const opt = e.opts.find(o => o.key === (over.opt ?? e.def.opt)) || e.opts.find(o => !o.disabled) || e.opts[0];
  return {
    id:newCardId(taken), on:true, entry:e.key, params:{ ...defaultParams(e), ...(over.params || {}) }, opt:opt?.key || '',
    value:over.value ?? e.def.value, value2:over.value2 ?? e.def.value2, within:over.within ?? e.def.within,
    second:{ ...defaultParams(e), ...(opt?.defaults ? pick(opt.defaults, e) : {}), ...(over.second || {}) },
    ...(over.metric ? { metric:over.metric } : {}),
  };
}
/** the defaults of a form that are the second instance's parameters (keys that are entry parameters) */
const pick = (d: Record<string, ParamValue>, e: Entry) => Object.fromEntries(Object.entries(d).filter(([k]) => e.params.some(p => p.key === k)));

export const optOf = (e: Entry, c: Card): Opt | undefined => e.opts.find(o => o.key === c.opt);
/** The entry's registry defaults are offered (catalog default_offered; P17 a: false for I43, whose registry default
    anchor Session the screener does not offer, so its card has no Default chip and its params' `default` is the value a
    card opens with, not the registry default). Metrics and indicators of an older catalog without the field: true. */
export const defaultOffered = (e: Entry | undefined) => (e?.indicator as { default_offered?: boolean } | undefined)?.default_offered !== false;
/** Custom = some parameter differs from its default (the prototype's isCustom), or the registry defaults are not
    offered (P17 consequence: such a card is always Custom) */
export const isCustom = (e: Entry, c: Card) => !defaultOffered(e) || e.params.some(p => !isDefP(p, c.params[p.key]));
/** the parameters the wire needs: those that differ from the registry default (missing ones take it). Where the
    registry default is not offered (default_offered false) every parameter is sent, because a missing one would take
    the registry default the worker refuses (registry.ts resolveScreenerParams, P17 a). */
const changed = (e: Entry, p: ParamMap): ParamMap => Object.fromEntries(e.params.filter(x => !defaultOffered(e) || !isDefP(x, p[x.key])).map(x => [x.key, p[x.key]]));

const ind = (e: Entry, params: ParamMap, output: string): IndicatorRef => {
  const ch = changed(e, params);
  return Object.keys(ch).length ? { kind:'indicator', indicator:e.key, params:ch, output } : { kind:'indicator', indicator:e.key, output };
};
/** the metric reference of a non-indicator entry: its catalog template (an additive `ref` field) when the catalog
    gives one, else the reference of its kind named by its id (report 8.5 MetricRef) */
export function metricRef(e: Entry, params: ParamMap): MetricRef {
  const m = e.metric!, tmpl = (m as any).ref as MetricRef | undefined, ch = changed(e, params);
  const withParams = (r: any) => Object.keys(ch).length || r.params ? { ...r, params:{ ...(r.params || {}), ...ch } } : r;
  if (tmpl) {
    if (tmpl.kind === 'transform') { const args = { ...(tmpl.args || {}), ...ch }; return Object.keys(args).length ? { ...tmpl, args } : tmpl }
    return tmpl.kind === 'universe' || tmpl.kind === 'price' ? tmpl : withParams(tmpl);
  }
  switch (m.kind) {
    case 'pattern': return withParams({ kind:'pattern', type:m.id });
    case 'xsection': return withParams({ kind:'xsection', metric:m.id });
    case 'flow': return { kind:'flow', metric:m.id, params:{ window:Number(params.window ?? 5), ...ch } as any };
    case 'universe': return { kind:'universe', attr:m.id };
    case 'price': return { kind:'price', field:m.id as any };
    case 'transform': return Object.keys(ch).length ? { kind:'transform', fn:m.id, of:{ kind:'price', field:'close' }, args:ch } : { kind:'transform', fn:m.id, of:{ kind:'price', field:'close' } };
    default: return { kind:'indicator', indicator:m.id, output:m.id };
  }
}

const num = (v: number | '' | undefined, scale = 1) => v === '' || v == null ? NaN : Number(v) * scale;

/** The problems of a card before it is sent (report 9.2: refused in place, never rounded): field -> message. */
export function cardErrors(e: Entry | undefined, c: Card, withinMax = 130): Record<string, string> {
  const out: Record<string, string> = {};
  if (!e || c.raw) return out;
  const o = optOf(e, c);
  if (!o) { out.op = 'Pick a condition.'; return out }
  if (o.disabled) out.op = o.disabled;
  if (o.value === 'input') {
    if (!Number.isFinite(num(c.value))) out.value = 'Enter a value.';
    if (o.between) {
      if (!Number.isFinite(num(c.value2))) out.value2 = 'Enter the upper value.';
      else if (Number.isFinite(num(c.value)) && num(c.value) > num(c.value2)) out.value2 = 'The upper value must be at least the lower value.';
    }
  }
  if (o.within) {
    const w = num(c.within);
    if (!Number.isInteger(w) || w < 1 || w > withinMax) out.within = `Enter whole sessions from 1 to ${withinMax}.`;
  }
  return out;
}

/** The wire condition of a card (toWire). A raw card returns its kept test. */
export function toWire(e: Entry | undefined, c: Card): ConditionDef {
  const base = { id:c.id, enabled:c.on, ...(c.label ? { label:c.label } : {}) };
  if (!e || c.raw) return { ...base, test:c.raw! };
  const o = optOf(e, c)!;
  const scale = displayScale(o.unit), v = num(c.value, scale), v2 = num(c.value2, scale), within = Number(c.within);
  if (e.kind !== 'indicator') {
    const ref = metricRef(e, c.params);
    if (o.kind === 'value') return { ...base, test:{ kind:'value', metric:ref, op:o.op as ValueTest['op'], value:v, ...(o.between ? { value2:v2 } : {}) } };
    if (ref.kind === 'pattern') return { ...base, test:o.kind === 'state' ? { kind:'state', pattern:ref } : { kind:'event', signal:{ pattern:ref }, within } };
    if (o.kind === 'state') return { ...base, test:{ kind:'state', lhs:ref, op:o.op as 'gt' | 'lt', rhs:{ value:v } } };
    return { ...base, test:{ kind:'event', within, signal:{ lhs:ref, op:o.op as 'crosses_above' | 'crosses_below', rhs:{ value:v } } } };
  }
  const out = o.output!, me = ind(e, c.params, out), field = (e.indicator!.outputs.find(x => x.key === out)?.comparable_with || 'close') as 'close' | 'volume';
  const d = o.defaults || {};
  const fixed = Number(d.value ?? 0);
  let lhs: Side, rhs: Side;
  switch (o.form) {
    case 'value': return { ...base, test:{ kind:'value', metric:me, op:o.op as ValueTest['op'], value:v, ...(o.between ? { value2:v2 } : {}) } };
    case 'value_pct_distance': case 'value_band_position':
      return { ...base, test:{ kind:'value', metric:{ kind:'transform', fn:o.form === 'value_pct_distance' ? 'pct_distance' : 'band_position', of:me }, op:o.op as ValueTest['op'], value:v, ...(o.between ? { value2:v2 } : {}) } };
    case 'state_level': case 'event_level': lhs = { kind:'price', field }; rhs = me; break;
    case 'state_value': case 'event_value': lhs = me; rhs = { value:o.value === 'fixed' ? fixed : v }; break;
    case 'state_output': case 'event_output': lhs = me; rhs = ind(e, c.params, o.with_output!); break;
    case 'state_instance': case 'event_instance': lhs = me; rhs = ind(e, c.second, out); break;
    case 'state_rising': lhs = me; rhs = { kind:'transform', fn:'lag', of:me, args:{ bars:Number(d.bars ?? 5) } }; break;
    case 'state_vs_ma': case 'event_vs_ma': lhs = me; rhs = { kind:'transform', fn:'ma', of:me, args:{ ma:String(d.ma ?? 'EMA'), length:Number(d.length ?? 20) } }; break;
    default: throw new Error(`forms: unknown form ${o.form}`);
  }
  const op = o.op;
  if (o.kind === 'state') return { ...base, test:{ kind:'state', lhs, op:op as 'gt' | 'lt', rhs } };
  return { ...base, test:{ kind:'event', within, signal:{ lhs, op:op as 'crosses_above' | 'crosses_below', rhs } } };
}

/* ---- fromWire -------------------------------------------------------------------------------------------- */
const isInd = (s: any): s is IndicatorRef => s && s.kind === 'indicator';
const isTr = (s: any, fn: string) => s && s.kind === 'transform' && s.fn === fn;
const sameParams = (e: Entry, a?: ParamMap, b?: ParamMap) => e.params.every(p => String((a || {})[p.key] ?? p.default) === String((b || {})[p.key] ?? p.default));
const full = (e: Entry, p?: ParamMap): ParamMap => ({ ...defaultParams(e), ...(p || {}) });
/** a reference without its own parameters (top-level params, a transform's top-level args): the shape a catalog
    template is matched by */
const canonicalRef = (r: any) => { if (!r || typeof r !== 'object') return ''; const { params, args, ...rest } = r; void params; void args; return JSON.stringify(sortKeys(rest)) };
const sortKeys = (v: any): any => Array.isArray(v) ? v.map(sortKeys) : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map(k => [k, sortKeys(v[k])])) : v;
const keyOfRef = (r: any): string | null => r?.kind === 'pattern' ? r.type : r?.kind === 'flow' || r?.kind === 'xsection' ? r.metric
  : r?.kind === 'universe' ? r.attr : r?.kind === 'transform' ? r.fn : r?.kind === 'price' ? r.field : null;

/** The catalog entry a metric reference names (fromWire): an entry whose catalog template (`ref`) has this shape, its own
    parameters aside; else the entry named by the id. */
function metricEntryOf(r: any, entries: Map<string, Entry>): Entry | undefined {
  const shape = canonicalRef(r);
  for (const e of entries.values()) if (e.kind !== 'indicator' && (e.metric as any)?.ref && canonicalRef((e.metric as any).ref) === shape) return e;
  const k = keyOfRef(r); const e = k ? entries.get(k) : undefined; return e && e.kind !== 'indicator' && !(e.metric as any)?.ref ? e : undefined;
}
/** The name of what a wire test reads, as the catalog names it (a raw card's header and the place of its refusals): its
    first reference that is not a bar field (close above an SMA is the SMA's card, as condition.ts names it), else the
    bar field; a transform that is a catalog metric's template (Distance from 52W high) by that metric, any other
    transform by what it is computed on; an indicator or metric by its catalog label, a bar field by its word; the id
    only when the catalog has no entry for it (an unknown indicator: the only name there is); null for no reference. */
export function refName(t: any, entries: Map<string, Entry>): string | null {
  const isRef = (r: any) => !!r && typeof r === 'object' && typeof r.kind === 'string';
  const refs = [t?.metric, t?.pattern, t?.lhs, t?.rhs, t?.signal?.pattern, t?.signal?.lhs, t?.signal?.rhs].filter(isRef);
  let r = refs.find(x => x.kind !== 'price') ?? refs[0];
  while (r?.kind === 'transform' && isRef(r.of) && !metricEntryOf(r, entries)) r = r.of;
  if (!r) return null;
  if (r.kind === 'price') return typeof r.field === 'string' ? r.field.charAt(0).toUpperCase() + r.field.slice(1) : null;
  if (r.kind !== 'indicator') { const m = metricEntryOf(r, entries); if (m?.label) return m.label }
  const id = r.kind === 'indicator' ? r.indicator : keyOfRef(r);
  return typeof id === 'string' && id ? entries.get(id)?.label || id : null;
}
/** A wire condition as a card on `entries` (by key); an unmapped one becomes a raw card. */
export function fromWire(cd: ConditionDef, entries: Map<string, Entry>): Card {
  const raw = (): Card => {
    const name = refName(cd.test, entries);
    return { id:cd.id, on:cd.enabled !== false, entry:null, params:{}, opt:'', value:'', value2:'', within:'', second:{}, raw:cd.test, ...(name ? { rawName:name } : {}), ...(cd.label ? { label:cd.label } : {}) };
  };
  const t = cd.test as any;
  const kind = t?.kind as 'value' | 'state' | 'event';
  const mk = (e: Entry, form: string, output: string | undefined, op: TestOp, params: ParamMap | undefined, extra: Partial<Card> = {}, withOut?: string): Card | null => {
    const o = e.opts.find(x => x.form === form && x.kind === kind && (output === undefined || x.output === output) && (form === 'metric' && x.value === 'none' || x.op === op) && (withOut === undefined || x.with_output === withOut) && !x.disabled);
    if (!o) return null;
    const scale = displayScale(o.unit);
    const sv = (v: unknown) => typeof v === 'number' ? v / scale : '' as const;
    return { id:cd.id, on:cd.enabled !== false, entry:e.key, params:full(e, params), opt:o.key, value:sv(t.value), value2:sv(t.value2),
      within:typeof t.within === 'number' ? t.within : e.def.within, second:full(e), ...(cd.label ? { label:cd.label } : {}), ...extra };
  };
  const metricEntry = (r: any) => metricEntryOf(r, entries);
  try {
    if (t?.kind === 'value') {
      const m = t.metric;
      if (isInd(m)) { const e = entries.get(m.indicator); return (e && mk(e, 'value', m.output, t.op, m.params)) || raw() }
      if ((isTr(m, 'pct_distance') || isTr(m, 'band_position')) && isInd(m.of)) {
        const e = entries.get(m.of.indicator); const form = m.fn === 'pct_distance' ? 'value_pct_distance' : 'value_band_position';
        return (e && mk(e, form, m.of.output, t.op, m.of.params)) || raw();
      }
      const e = metricEntry(m);
      if (e) return mk(e, 'metric', undefined, t.op, { ...(m.params || {}), ...(m.kind === 'transform' ? m.args || {} : {}) }) || raw();
      return raw();
    }
    if (t?.kind === 'state' && t.pattern) { const e = metricEntry(t.pattern); return (e && mk(e, 'metric', undefined, 'gt', t.pattern.params, {})) || raw() }
    if (t?.kind === 'event' && t.signal?.pattern) { const e = metricEntry(t.signal.pattern); return (e && mk(e, 'metric', undefined, 'gt', t.signal.pattern.params)) || raw() }
    const s = t?.kind === 'state' ? t : t?.kind === 'event' ? t.signal : null;
    if (!s) return raw();
    const pre = t.kind === 'state' ? 'state' : 'event', { lhs, rhs, op } = s;
    if (lhs?.kind === 'price' && isInd(rhs)) { const e = entries.get(rhs.indicator); return (e && mk(e, pre + '_level', rhs.output, op, rhs.params)) || raw() }
    if (isInd(lhs)) {
      const e = entries.get(lhs.indicator);
      if (!e) return raw();
      if (rhs && typeof rhs.value === 'number' && !rhs.kind) {
        const c = mk(e, pre + '_value', lhs.output, op, lhs.params, { value:rhs.value });
        if (c) { const o = optOf(e, c)!; if (o.value === 'fixed' && Number(o.defaults.value ?? 0) !== rhs.value) return raw(); return c }
        return raw();
      }
      if (isInd(rhs) && rhs.indicator === lhs.indicator) {
        if (sameParams(e, lhs.params, rhs.params) && rhs.output !== lhs.output) return mk(e, pre + '_output', lhs.output, op, lhs.params, {}, rhs.output) || raw();
        if (rhs.output === lhs.output) return mk(e, pre + '_instance', lhs.output, op, lhs.params, { second:full(e, rhs.params) }) || raw();
      }
      if (isTr(rhs, 'lag') && isInd(rhs.of) && rhs.of.indicator === lhs.indicator && pre === 'state') {
        const c = mk(e, 'state_rising', lhs.output, op, lhs.params);
        return c && Number(optOf(e, c)!.defaults.bars ?? 5) === Number(rhs.args?.bars) ? c : raw();
      }
      if (isTr(rhs, 'ma') && isInd(rhs.of) && rhs.of.indicator === lhs.indicator) {
        const c = mk(e, pre + '_vs_ma', lhs.output, op, lhs.params);
        const d = c && optOf(e, c)!.defaults;
        return c && d && String(d.ma ?? 'EMA') === String(rhs.args?.ma) && Number(d.length ?? 20) === Number(rhs.args?.length) ? c : raw();
      }
      return raw();
    }
    const e = metricEntry(lhs);
    if (e && rhs && typeof rhs.value === 'number') return mk(e, 'metric', undefined, op, lhs.params, { value:rhs.value }) || raw();
    return raw();
  } catch { return raw() }
}

/* ---- words ---------------------------------------------------------------------------------------------- */
const pv = (e: Entry, c: Card) => e.params.map(p => optionText(p, c.params[p.key])).join(', ');
/** the card's name (a My metric's name, else the entry's label) */
export const cardName = (e: Entry | undefined, c: Card) => c.metric?.name || c.label || e?.label || c.rawName || 'Condition';
const vtxt = (v: number | '' | undefined) => v === '' || v == null ? '…' : String(v);
/** The card's rule in words (the prototype's condText). */
export function condText(e: Entry | undefined, c: Card): string {
  if (!e || c.raw) return `${cardName(e, c)}: ${rawText(c.raw)} (kept as saved; not editable here)`;
  const o = optOf(e, c); const p = pv(e, c), name = `${cardName(e, c)}${p ? ` (${p})` : ''}`;
  if (!o) return name;
  const u = displayUnit(o.unit), us = u === '%' || u === '×' ? u : u ? ' ' + u : '';
  const w = o.within ? ` · within ${vtxt(c.within)}d` : '';
  if (o.value !== 'input') return `${name}: ${o.label}${w}`;
  if (o.between) return `${name} ${vtxt(c.value)}–${vtxt(c.value2)}${us}`;
  if (o.kind === 'event' || o.kind === 'state') return `${name} ${o.label.toLowerCase()} ${vtxt(c.value)}${us}${w}`;
  return `${name} ${o.op === 'gt' ? '>' : o.op === 'lt' ? '<' : OPLABEL[o.op]} ${vtxt(c.value)}${us}`;
}
function rawText(t: any): string {
  if (!t) return '';
  if (t.kind === 'value') return `${OPLABEL[t.op] || t.op} ${t.value}${t.op === 'between' ? `–${t.value2}` : ''}`;
  if (t.kind === 'event') return `event within ${t.within} sessions`;
  return 'state';
}
/** "Rule only" (the prototype's condRule): the text after the name. */
export function condRule(e: Entry | undefined, c: Card): string {
  const full = condText(e, c), p = e ? pv(e, c) : '', pre = `${cardName(e, c)}${p ? ` (${p})` : ''}`;
  return full.slice(pre.length).replace(/^:\s*/, '').trim();
}
/** parameter summary (the prototype's paramSummary) */
export const paramSummary = (e: Entry, p: ParamMap) => e.params.map(x => `${x.label || x.key} ${optionText(x, p[x.key])}${String(p[x.key]) !== String(x.default) ? ` (default ${optionText(x, x.default)})` : ''}`).join(' · ');
/** the column header's short name and its parameter pill (the prototype's shortName, shortPv) */
export const shortName = (e: Entry | undefined, c: Card) => c.metric?.name || (e ? e.short : cardName(e, c));
export const shortPv = (e: Entry | undefined, c: Card) => e ? e.params.filter(p => p.type !== 'enum' && p.type !== 'boolean').map(p => c.params[p.key]).join('/') : '';
