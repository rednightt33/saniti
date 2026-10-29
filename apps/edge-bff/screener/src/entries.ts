/* The catalog as the builder offers it (report 9.2 "Adder", "Indicator browser", "Condition card"): one Entry per
   registry indicator (catalog.indicators, I01-I53 today) and per non-indicator metric (catalog.metrics, fundamentals),
   each with its parameters and the choices of its operator select. Everything comes from the catalog answer; the page
   holds no indicator list, no synonym table and no default of its own (report 6.9, 9.2 P6). Pure: no DOM. */
import type {
  Availability, CatalogIndicator, CatalogMetric, CatalogOutput, CatalogParam, CatalogResponse, MetricKind, ParamMap,
  ParamValue, TestForm, TestFormSpec, TestKind, TestOp,
} from './core/contract.ts';

/** The prototype's group order (GORD): the 53-indicator catalogue first, then technical, flow and fundamental metrics. */
export const GORD = ['Trend', 'Momentum', 'Volatility', 'Volume', 'PriceVolume', 'Technical', 'Flow', 'Fundamental'];
export const GL = (g: string) => ({ Fundamental:'Fund', PriceVolume:'Price·Vol' } as Record<string, string>)[g] || g;
export const GHEAD = (g: string) => ({ Flow:'Flow & bandarmology', PriceVolume:'Price & volume', 'My metrics':'My metrics · your saved parameters' } as Record<string, string>)[g] || g;
export const OPLABEL: Record<string, string> = { gt:'greater than', lt:'less than', between:'between', crosses_above:'crosses above', crosses_below:'crosses below' };
const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s;

/** One choice of a card's operator select. */
export interface Opt {
  key: string;                 // unique in its entry: `${form}|${output}|${op}`
  label: string;
  kind: TestKind;
  form: TestForm | 'metric';
  output?: string;             // indicator output the test reads
  with_output?: string;        // state_output / event_output: the other output
  op: TestOp;
  value: 'input' | 'fixed' | 'none';   // input: the card shows value fields; fixed: defaults.value; none: no value
  between: boolean;
  within: boolean;
  unit: string | null;         // unit of the value fields
  defaults: Record<string, ParamValue>;
  disabled?: string;           // a form shown disabled with its reason (raw cumulative levels)
}
export interface Entry {
  key: string;                 // indicator id ('I13') or metric id
  kind: 'indicator' | 'metric' | 'fundamental';
  group: string;
  label: string; short: string; desc: string; xid?: string;
  params: EntryParam[];
  opts: Opt[];
  def: { opt: string; value: number | ''; value2: number | ''; within: number };
  available: boolean; availability: Availability; reason: string | null;
  synonyms: string[];
  history: string | null;      // history_class note ("level depends on history start" for cumulative)
  indicator?: CatalogIndicator; metric?: CatalogMetric; metricKind?: MetricKind;
}

const GROUP_OF_METRIC = (g: string, kind: string) => GORD.includes(g) ? g
  : /fund/i.test(g) ? 'Fundamental' : /flow|bandar|broker|foreign/i.test(g) || kind === 'flow' ? 'Flow' : 'Technical';
const PCT_FORMS: TestForm[] = ['value_pct_distance', 'value_band_position'];

function outLabel(ind: CatalogIndicator, o: CatalogOutput | undefined, key: string) {
  return o?.label || (ind.outputs.length === 1 ? shortOf(ind) : key.replace(/_/g, ' '));
}
/** the indicator's short name: the catalog's `short` (additive, the generated registry's), else its first upper-case
    synonym, else its key */
export const shortOf = (ind: CatalogIndicator) => (ind as any).short || (ind.synonyms || []).find(s => /^[A-Z%][A-Za-z0-9 %/+()-]{0,11}$/.test(s)) || ind.key.replace(/_/g, ' ').toUpperCase();

/** A catalog parameter as the page holds it: option_labels, the words of the options whose wire value is no word (a
    line of another indicator, 'I40.obv', in a pattern's "Line" select; a value with an underscore, Keltner's
    'HL_RANGE'), derived from the catalog. */
export type EntryParam = CatalogParam & { option_labels?: Record<string, string> };
/** an option (or any parameter value) as the page shows it: its label, else the value itself */
export const optionText = (p: EntryParam, x: unknown): string => p.option_labels?.[String(x)] ?? String(x);
/** option_labels of an entry's parameters: an option '<indicator id>.<output>' is named by that indicator (and the
    output, for one of several), as the catalog's indicators name them; an option with underscores by its words (the
    first as written, the others in lower case: 'HL_RANGE' is "HL range") */
function withOptionLabels(params: CatalogParam[], indicators: readonly CatalogIndicator[]): EntryParam[] {
  return params.map(p => {
    const labels: Record<string, string> = {};
    for (const o of p.options || []) {
      const m = /^(I\d+)\.(\w+)$/.exec(o), ind = m ? indicators.find(i => i.id === m[1]) : undefined;
      if (ind) {
        const out = ind.outputs.find(x => x.key === m![2]);
        labels[o] = ind.outputs.length > 1 && out?.label ? `${ind.name}, ${out.label}` : ind.name;
      } else if (o.includes('_')) labels[o] = o.split('_').filter(Boolean).map((w, i) => i ? w.toLowerCase() : w).join(' ');
    }
    return Object.keys(labels).length ? { ...p, option_labels:labels } : p;
  });
}

/** the label of an indicator test option when the overlay gives none (the prototype's words where it had them) */
function optLabel(ind: CatalogIndicator, o: CatalogOutput, spec: TestFormSpec, op: TestOp, valueOuts: number): string {
  const s = shortOf(ind), out = outLabel(ind, o, o.key), other = spec.with_output ? outLabel(ind, ind.outputs.find(x => x.key === spec.with_output), spec.with_output) : '';
  const up = op === 'gt' || op === 'crosses_above', word = op === 'gt' ? 'above' : op === 'lt' ? 'below' : OPLABEL[op];
  const d = spec.defaults || {};
  const level = o.comparable_with === 'volume' ? 'Volume' : 'Close';
  switch (spec.form) {
    case 'value': case 'event_value': return valueOuts > 1 ? `${out} ${OPLABEL[op]}` : cap(OPLABEL[op]);
    case 'value_pct_distance': case 'value_band_position': return cap(OPLABEL[op]);
    case 'state_level': return `${level} ${word} ${out}`;
    case 'event_level': return `${level} ${OPLABEL[op]} ${out}`;
    case 'state_value': return `${out} ${word} ${d.value ?? 0}`;
    case 'state_output': return `${out} ${word} ${other}`;
    case 'event_output': return `${out} ${OPLABEL[op]} ${other}`;
    case 'state_instance': return `${s} ${word} ${s} (second)`;
    case 'event_instance': return `${s} ${OPLABEL[op]} ${s} (second)`;
    case 'state_rising': return `${s} ${up ? 'rising' : 'falling'} (vs ${d.bars ?? 5} sessions ago)`;
    case 'state_vs_ma': return `${up ? 'Above' : 'Below'} its ${d.length ?? 20}-session ${d.ma ?? 'EMA'}`;
    case 'event_vs_ma': return `${OPLABEL[op] === 'crosses above' ? 'Crosses above' : 'Crosses below'} its ${d.length ?? 20}-session ${d.ma ?? 'EMA'}`;
  }
  return cap(OPLABEL[op] || op);
}
const kindOf = (f: TestForm): TestKind => f.startsWith('value') ? 'value' : f.startsWith('state') ? 'state' : 'event';

function indicatorEntry(ind: CatalogIndicator, indicators: readonly CatalogIndicator[] = []): Entry {
  const opts: Opt[] = [];
  const valueOuts = ind.outputs.filter(o => o.tests.some(t => t.form === 'value' || t.form === 'event_value')).length;
  for (const o of ind.outputs) {
    for (const spec of o.tests) for (const op of spec.ops) {
      const kind = kindOf(spec.form), given = spec.labels?.[op], labelled = !!given;
      const label = given || optLabel(ind, o, spec, op, valueOuts);
      const valued = spec.form === 'value' || PCT_FORMS.includes(spec.form) || spec.form === 'event_value' || spec.form === 'state_value';
      opts.push({
        key:`${spec.form}|${o.key}|${op}`, label, kind, form:spec.form, output:o.key, with_output:spec.with_output, op,
        value:!valued ? 'none' : (spec.form === 'state_value' || spec.form === 'event_value') && (labelled || spec.defaults?.value != null) ? 'fixed' : 'input',
        between:op === 'between', within:kind === 'event',
        unit:PCT_FORMS.includes(spec.form) ? '%' : o.unit || null, defaults:spec.defaults || {},
      });
    }
    for (const d of o.disabled_tests || []) for (const op of ['gt', 'lt'] as TestOp[])
      opts.push({ key:`${d.form}|${o.key}|${op}`, label:cap(OPLABEL[op]), kind:kindOf(d.form), form:d.form, output:o.key, op, value:'input', between:false, within:false, unit:o.unit, defaults:{}, disabled:d.reason });
  }
  const dt = ind.overlay?.default_test;
  const defOpt = (dt && opts.find(x => x.form === dt.form && x.output === dt.output && x.op === dt.op && !x.disabled)) || opts.find(x => !x.disabled);
  const short = shortOf(ind);
  return {
    key:ind.id, kind:'indicator', group:ind.category, label:ind.name, short, xid:ind.id,
    desc:(ind as any).description || `${ind.name} (${ind.id}).`,
    params:withOptionLabels(ind.params, indicators), opts,
    def:{ opt:defOpt?.key || '', value:dt?.value ?? 0, value2:dt?.value2 ?? '', within:dt?.within ?? 5 },
    available:opts.some(o => !o.disabled), availability:'AVAILABLE', reason:opts.some(o => !o.disabled) ? null : 'No test is offered for this indicator.',
    synonyms:ind.synonyms || [],
    history:ind.history_class === 'cumulative' ? 'Level depends on where history starts; only relative tests are offered.' : null,
    indicator:ind,
  };
}

function metricEntry(m: CatalogMetric, kind: 'metric' | 'fundamental', indicators: readonly CatalogIndicator[] = []): Entry {
  const opts: Opt[] = [];
  const pattern = m.kind === 'pattern';
  for (const t of m.tests) {
    if (t === 'value') for (const op of ['gt', 'lt', 'between'] as TestOp[])
      opts.push({ key:`metric|value|${op}`, label:cap(OPLABEL[op]), kind:'value', form:'metric', op, value:'input', between:op === 'between', within:false, unit:m.unit, defaults:{} });
    else if (pattern) opts.push({ key:`metric|${t}|on`, label:t === 'event' ? 'Detected (event)' : 'Detected', kind:t, form:'metric', op:'gt', value:'none', between:false, within:t === 'event', unit:null, defaults:{} });
    else for (const op of (t === 'event' ? ['crosses_above', 'crosses_below'] : ['gt', 'lt']) as TestOp[])
      opts.push({ key:`metric|${t}|${op}`, label:cap(OPLABEL[op] || op), kind:t, form:'metric', op, value:'input', between:false, within:t === 'event', unit:m.unit, defaults:{} });
  }
  const available = m.availability === 'AVAILABLE';
  const def = (m as any).default_test as { op?: string; test?: string; value?: number; value2?: number; within?: number } | undefined;
  const defOpt = (def && opts.find(o => o.op === def.op && (!def.test || o.kind === def.test))) || opts[0];
  return {
    key:m.id, kind, group:kind === 'fundamental' ? 'Fundamental' : GROUP_OF_METRIC(m.group, m.kind),
    label:(m as any).label || (m as any).name || m.id, short:(m as any).short || (m as any).label || m.id,
    desc:m.interpretation || m.formula || '',
    params:withOptionLabels(m.params || [], indicators), opts,
    def:{ opt:defOpt?.key || '', value:def?.value ?? 0, value2:def?.value2 ?? '', within:def?.within ?? 5 },
    available, availability:m.availability, reason:available ? null : (m.reason || 'Not available.'),
    synonyms:(m as any).synonyms || [], history:null, metric:m, metricKind:m.kind,
  };
}

/** Every entry of the catalog, indicators first (registry order), then metrics, then fundamentals. */
export function entriesOf(cat: CatalogResponse): Entry[] {
  return [
    ...cat.indicators.map(ind => indicatorEntry(ind, cat.indicators)),
    ...cat.metrics.map(m => metricEntry(m, 'metric', cat.indicators)),
    ...cat.fundamentals.map(m => metricEntry(m, 'fundamental', cat.indicators)),
  ];
}
export const byGroup = <T extends { group: string }>(list: T[]) => [...list].sort((x, y) => GORD.indexOf(x.group) - GORD.indexOf(y.group));

/** The adder's and browser's search (prototype drawSuggest): label, short name, description, key and the catalog's
    synonyms (a synonym matches when it starts with the query). */
export function matches(e: Entry, q: string): boolean {
  const n = q.trim().toLowerCase();
  if (!n) return true;
  if ((e.label + ' ' + e.short + ' ' + e.desc + ' ' + e.key).toLowerCase().includes(n)) return true;
  return e.synonyms.some(s => s.toLowerCase().startsWith(n));
}

/** Default parameters of an entry, as a full map. */
export const defaultParams = (e: Entry): ParamMap => Object.fromEntries(e.params.map(p => [p.key, p.default])) as ParamMap;
/** A parameter equals its default (the prototype's isDefP, by value, not by string). */
export const isDefP = (p: CatalogParam, v: ParamValue | undefined) => v === undefined || String(v) === String(p.default);

/** Check one parameter value against the catalog (report 9.2: invalid input is refused in place with the field and
    the allowed range, never rounded or ignored). Returns the error text or null. */
export function paramError(p: EntryParam, v: ParamValue): string | null {
  if (p.type === 'enum') return (p.options || []).includes(String(v)) ? null : `Pick one of ${(p.options || []).map(x => optionText(p, x)).join(', ')}.`;
  if (p.type === 'boolean') return typeof v === 'boolean' ? null : 'Pick true or false.';
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'Enter a number.';
  if ((p.integer || p.type === 'integer') && !Number.isInteger(v)) return 'Enter a whole number.';
  if (p.min != null && (p.exclusive_min ? v <= p.min : v < p.min)) return p.exclusive_min ? `Must be above ${p.min}.` : `Must be at least ${p.min}.`;
  if (p.max != null && v > p.max) return `Must be at most ${p.max}.`;
  return null;
}
export const rangeText = (p: CatalogParam) => p.type === 'enum' || p.type === 'boolean' ? ''
  : `${p.min != null ? (p.exclusive_min ? `> ${p.min}` : `≥ ${p.min}`) : ''}${p.min != null && p.max != null ? ', ' : ''}${p.max != null ? `≤ ${p.max}` : ''}`;
