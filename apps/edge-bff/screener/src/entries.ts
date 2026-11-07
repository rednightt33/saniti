/* The catalog as the builder offers it (report 9.2 "Adder", "Indicator browser", "Condition card"): one Entry per
   registry indicator (catalog.indicators, I01-I53 today) and per non-indicator metric (catalog.metrics, fundamentals),
   each with its parameters and the choices of its operator select. Everything comes from the catalog answer; the page
   holds no indicator list, no synonym table and no default of its own (report 6.9, 9.2 P6). Pure: no DOM. */
import type {
  Availability, BrokerWindow, CatalogFlow, CatalogIndicator, CatalogOperators, CatalogMetric, CatalogOutput, CatalogParam, CatalogResponse,
  MetricKind, ParamMap, ParamValue, TestForm, TestFormSpec, TestKind, TestOp,
} from './core/contract.ts';
import { formatOfMetric, formatOfOutput, type ValueFormat } from './format.ts';

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
  /** the catalog's universal operators (GET /catalog `operators`, P3) on an indicator entry and on a flow indicator
      (P5c): the measures and tests a card on it may add (operators.ts); absent from an older catalog, and on metrics */
  ops?: CatalogOperators;
  /** EXEC-SCREENER-FLOW-CANDLES P5c: one of the Terminal's flow indicators (the catalog's `flow`: its parameters,
      outputs and their kinds, the sessions it reads at its defaults) and the loaded broker window (data.broker_window) */
  flow?: CatalogFlow;
  window?: BrokerWindow | null;
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

/** The kinds of a flow indicator's parameters the page edits besides the catalog's four (EXEC-SCREENER-FLOW-CANDLES
    P5c; flowRegistry.json `multi`, `date`, `brokers`): a list of options (the boards, the investor types), kept on the
    card as its values joined by commas and sent as a list; an anchor date, 'view' (the first session of the loaded
    broker window) or YYYY-MM-DD inside it; a list of broker codes, kept joined by commas, '' meaning the Terminal's
    default (no broker, or its own token such as the top holders). */
export type FlowParamType = 'multi' | 'date' | 'brokers';
/** A catalog parameter as the page holds it: option_labels, the words of the options whose wire value is no word (a
    line of another indicator, 'I40.obv', in a pattern's "Line" select; a value with an underscore, Keltner's
    'HL_RANGE'; a flow select's own labels), derived from the catalog. A flow indicator's parameter may be one of
    FlowParamType; `sessions` marks a whole number of sessions it reads back (its depth grows with it, K1); `wire`
    the default as the Terminal states it (a list, or a broker token), `count` the brokers a list takes (min, max). */
export type EntryParam = Omit<CatalogParam, 'type'> & {
  type: CatalogParam['type'] | FlowParamType;
  option_labels?: Record<string, string>;
  sessions?: boolean; wire?: unknown; count?: { min: number; max: number | null };
  /** a date parameter: the loaded broker window it must fall in (data.broker_window) */
  dates?: { first: string | null; last: string | null };
};
export const isFlowType = (p: EntryParam): p is EntryParam & { type: FlowParamType } => p.type === 'multi' || p.type === 'date' || p.type === 'brokers';
/** the separator of a list kept on the card (multi, brokers): no option value of the registry holds it */
export const LIST_SEP = ',';
export const listOf = (v: unknown): string[] => typeof v === 'string' && v ? v.split(LIST_SEP).filter(Boolean) : [];
/** an option (or any parameter value) as the page shows it: its label, else the value itself; a list by its labels;
    an anchor at the window start and a broker list left at the default in words */
export const optionText = (p: EntryParam, x: unknown): string => {
  if (p.type === 'multi') { const l = listOf(x); return l.length ? l.map(v => p.option_labels?.[v] ?? v).join(' + ') : 'none' }
  if (p.type === 'date') return x === 'view' || x === '' || x == null ? 'start of the broker data' : String(x);
  if (p.type === 'brokers') { const l = listOf(x); return l.length ? l.join(' + ') : noBrokers(p) }
  return p.option_labels?.[String(x)] ?? String(x);
};
/** a broker list left empty in words (it is read as the Terminal's default): no broker where that default is a list
    ("none named"; it was "default brokers", so a field's default read "default default brokers": QA5 unit B item 3),
    the class of a classification token ("class:Institutional-heavy": the Institutional-heavy brokers), any other token
    as the default list */
const noBrokers = (p: EntryParam): string => {
  if (typeof p.wire !== 'string' || !p.wire) return 'none named';
  const cls = /^class:(.+)$/.exec(p.wire)?.[1];
  return cls ? `the ${cls} brokers` : 'the standard list';
};
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

/* ---- the Terminal's flow indicators (EXEC-SCREENER-FLOW-CANDLES P5c; verification/screener/P5_FLOW.md sections 1, 2
   and 4): an entry per catalog metric that carries `flow`, with the Terminal's own parameters (the catalog's flow.params,
   the kinds that only draw left out, as the core's flowmetrics.ts conditionParams), one condition per output and test
   the output's kind takes (the operators block's not_on, OPERATORS.md section 4), and the universal operators. Nothing
   here names an indicator: every rule is read from the catalog's parameters, outputs, kinds and depth. ------------ */

/** An int parameter that counts sessions read back (a window, a baseline, the recent sessions; its label or key says
    days, sessions or window): the indicator's depth grows with it, one session per session (K1; the core's depth probe
    gives exactly that for every such parameter of the registry the indicator reads at that setup). */
const SESSION_PARAM = /\b(days?|sessions?|window|baseline|recent)\b/i;
/** The kinds whose values are whole numbers, where "=" and "!=" apply (K7, user 2026-11-07: a day count, a 0/1 signal,
    a broker count): the operators block's own `whole` flag on a type where the catalog gives one, else these. */
const WHOLE_KINDS: readonly string[] = ['D', 'F', 'B'];
export const wholeKind = (ops: CatalogOperators | undefined, kind: string | null | undefined): boolean => {
  if (!kind) return false;
  const t = ops?.types?.[kind] as { whole?: boolean } | undefined;
  return typeof t?.whole === 'boolean' ? t.whole : WHOLE_KINDS.includes(kind);
};
/** Whether a test of the operators block takes a series of this output type (its not_on; not_against_value for a cross
    of a fixed value, the only cross the page builds) */
export function testTakes(ops: CatalogOperators | undefined, key: string, type: string | null | undefined, againstValue = false): boolean {
  if (!ops || !type) return true;
  const t = ops.tests.find(x => x.key === key) as (CatalogOperators['tests'][number] & { not_against_value?: string[] }) | undefined;
  if (!t) return false;
  return !(t.not_on || []).includes(type) && !(againstValue && (t.not_against_value || []).includes(type));
}

const words = (k: string) => cap(k.replace(/_/g, ' '));
/** A flow indicator's condition parameters as the page edits them (the kinds that only draw are not among them). */
function flowParamsOf(f: CatalogFlow, w: BrokerWindow | null | undefined): EntryParam[] {
  const out: EntryParam[] = [];
  for (const q of f.params) {
    if (!q.condition || q.default === undefined) continue;
    const label = q.label || q.key, base = { key:q.key, label, exclusive_min:false, integer:false };
    const opts = (q.options || []) as (string | [string, string])[];
    const values = opts.map(o => String(Array.isArray(o) ? o[0] : o));
    const labels: Record<string, string> = Object.fromEntries(opts.filter((o): o is [string, string] => Array.isArray(o)).map(o => [String(o[0]), String(o[1])]));
    const ol = Object.keys(labels).length ? { option_labels:labels } : {};
    const range = { ...(q.min != null ? { min:q.min } : {}), ...(q.max != null ? { max:q.max } : {}) };
    switch (q.kind) {
      case 'int': out.push({ ...base, type:'integer', integer:true, default:Number(q.default), step:1, ...range, sessions:SESSION_PARAM.test(`${q.key} ${label}`) }); break;
      case 'num': out.push({ ...base, type:'number', default:Number(q.default), ...range }); break;
      case 'select': out.push({ ...base, type:'enum', default:String(q.default), options:values, ...ol }); break;
      case 'bool': out.push({ ...base, type:'boolean', default:q.default === true }); break;
      case 'multi': out.push({ ...base, type:'multi', default:(Array.isArray(q.default) ? q.default : []).map(String).join(LIST_SEP), options:values, ...ol, wire:q.default }); break;
      case 'date': out.push({ ...base, type:'date', default:typeof q.default === 'string' && q.default ? q.default : 'view', dates:{ first:w?.first ?? null, last:w?.last ?? null } }); break;
      case 'brokers': out.push({ ...base, type:'brokers', default:Array.isArray(q.default) ? q.default.map(String).join(LIST_SEP) : '', wire:q.default, count:{ min:q.min ?? 0, max:q.max ?? null } }); break;
    }
  }
  return out;
}

/** One output of a flow indicator at a setup: its key and words, its kind of OPERATORS.md section 4 (the catalog's
    kind: a letter, {kind, unit}, or following a select parameter), its unit as the core names the series' unit (a
    price level is 'price', comparable with the close; else the kind's or the indicator's unit), and whether the setup
    draws it (why not, in words, when it does not). */
export interface FlowOutput { key: string; label: string; kind: string; unit: string; comparable: 'close' | null; drawn: boolean; why: string | null }
/** an output's kind and unit at a setup (the core's flowmetrics.ts outputKind, on the catalog's kind spec) */
export function flowKindAt(f: CatalogFlow, spec: unknown, params: ParamMap): { kind: string; unit: string } | null {
  let s = spec as any;
  for (let i = 0; i < 3 && s && typeof s === 'object' && typeof s.by === 'string'; i++) s = s[String(params[s.by])];
  if (typeof s === 'string') return { kind:s, unit:f.unit };
  if (s && typeof s === 'object' && typeof s.kind === 'string') return { kind:s.kind, unit:String(s.unit ?? f.unit) };
  return null;
}
/** Why a setup does not draw an output, or null when it does (the Terminal's own rules, as the core's flowmetrics.ts
    seriesKeyOf refuses them, read from the catalog's parameters): a select whose options name two or more of the
    outputs (Side: Buy, Sell, Both) draws the one it names, or all of them for an option that names none (Both); a
    switch named as an output (the cohort total) draws it when on; one line per broker (an output named lines) is one
    series only with exactly one broker named. */
function notDrawn(e: Entry, key: string, params: ParamMap): string | null {
  const keys = e.flow!.outputs.map(o => o.key);
  for (const p of e.params) {
    const opts = p.options || [];
    if (p.type === 'enum' && opts.filter(o => keys.includes(o)).length >= 2 && opts.includes(key)) {
      const v = String(params[p.key]);
      if (v !== key && keys.includes(v)) {
        const all = opts.filter(o => !keys.includes(o)).map(o => optionText(p, o));
        return `${words(key)} is drawn only with ${p.label || p.key} ${[optionText(p, key), ...all].join(' or ')}: set it, or read ${words(v)}.`;
      }
    }
    if (p.type === 'boolean' && p.key === key && params[p.key] !== true) return `${words(key)} is drawn only with ${p.label || p.key} on: switch it on, or read another line.`;
  }
  if (key === 'lines') {
    const b = e.params.find(p => p.type === 'brokers');
    if (b && listOf(params[b.key]).length !== 1) return `${words(key)} draws one line per broker and a condition reads one: name exactly one broker in ${b.label || b.key} (right: YP; wrong: none, or YP, AK).`;
  }
  return null;
}
/** The outputs of a flow entry at a setup (the card's parameters; the catalog defaults when none are given). */
export function flowOutputs(e: Entry, params: ParamMap = defaultParams(e)): FlowOutput[] {
  const f = e.flow; if (!f) return [];
  const multi = f.outputs.length > 1;
  return f.outputs.map(o => {
    const k = flowKindAt(f, o.kind, params), why = k ? notDrawn(e, o.key, params) : `${words(o.key)} has no series at this setup.`;
    const level = k?.kind === 'H';
    return { key:o.key, label:multi ? words(o.key) : e.short || e.label, kind:k?.kind ?? '', unit:level ? 'price' : k?.unit ?? f.unit, comparable:level ? 'close' : null, drawn:!why, why };
  });
}
/** The sessions of broker data a flow indicator reads back at a setup (K1), as a hint: the catalog's depth at its
    defaults (the worker's own figure), plus the change of each session-count parameter, which a select, a capped
    baseline or a run limit can make wrong; null when the catalog does not know it. The worker is the one authority
    (its refusal LIMIT_EXCEEDED broker_depth is shown on the card that reads too far): the page never refuses by it. */
export function flowOwnDepth(e: Entry, params: ParamMap = defaultParams(e)): number | null {
  const f = e.flow; if (!f || typeof f.depth !== 'number') return null;
  let d = f.depth;
  for (const p of e.params) if (p.sessions) { const v = params[p.key], d0 = p.default; if (typeof v === 'number' && Number.isFinite(v) && typeof d0 === 'number') d += v - d0 }
  return Math.max(1, d);
}
/** The sessions an operator and its test may still read on a flow series at this setup (K1, OPERATORS.md section 3:
    the indicator's own sessions plus the operator's N, length or within are at most the loaded broker sessions), as a
    hint (flowOwnDepth); null when not known or not a flow entry. */
export function flowBudget(e: Entry, params: ParamMap = defaultParams(e)): number | null {
  const own = flowOwnDepth(e, params);
  return own == null || !e.flow ? null : e.flow.sessions - own;
}
/** The sessions left at the catalog's own setup, where the depth is the worker's figure: what the page may leave out of
    its lists (a measure or a test over sessions that cannot fit); null at any other setup (the worker judges it). */
export function flowExactBudget(e: Entry, params: ParamMap = defaultParams(e)): number | null {
  return e.flow && e.params.every(p => isDefP(p, params[p.key])) ? flowBudget(e, params) : null;
}
/** The broker sessions the Screener holds: the hard maximum of a session field on a flow series (none fits beyond it). */
export const flowSessions = (e: Entry): number | null => e.flow ? e.flow.sessions : null;
/** The hint of a session field on a flow series (OPERATORS.md section 5: the field shows its maximum for that
    indicator): about how many sessions of broker data the setup leaves; the worker refuses beyond what it reads. */
export function depthHint(left: number | null): string {
  return left == null ? '' : left < 1 ? 'about no session of broker data left at this setup' : `about ${left} session${left === 1 ? '' : 's'} of broker data left at this setup`;
}
/** The words of a flow entry's broker choice rule (the core's flowmetrics.ts emptyChoice: a scope of selected brokers
    names at least one), where the entry has that scope: param key -> message. */
export function flowSetupErrors(e: Entry, params: ParamMap): Record<string, string> {
  const out: Record<string, string> = {};
  for (const p of e.params) {
    if (p.type !== 'brokers') continue;
    // the scope beside the list (its own prefix: brokers and scope, num_brokers and num_scope); without one the core
    // judges the list itself
    const scope = p.key.endsWith('brokers') ? e.params.find(x => x.key === `${p.key.slice(0, -'brokers'.length)}scope` && x.type === 'enum') : undefined;
    // an empty list: none typed where the Terminal's default is a list (a default token such as the top holders is not one)
    const empty = !listOf(params[p.key]).length && (params[p.key] !== p.default || Array.isArray(p.wire));
    if (scope && empty && params[scope.key] === 'selected')
      out[p.key] = `${p.label || p.key}: ${scope.label || scope.key} is ${optionText(scope, 'selected')}, so name at least one broker, or choose another scope (right: YP; wrong: none).`;
  }
  return out;
}

function flowEntry(m: CatalogMetric, cat: CatalogResponse): Entry {
  const f = m.flow!, w = cat.data.broker_window ?? null, ops = cat.operators;
  const base: Entry = { ...metricEntry(m, 'metric', cat.indicators), params:flowParamsOf(f, w), flow:f, window:w, opts:[], ...(ops ? { ops } : {}) };
  const budget = flowBudget(base), outs = flowOutputs(base), multi = outs.length > 1;
  const opts: Opt[] = [];
  for (const o of outs) {
    // a price level (its kind compares with the close): the close above or below it, as an indicator's level is offered
    // ("Close above SMA"), where the catalog's operators compare the output with the close (a measure with a second
    // series that its kind takes); read at the stock's broker data date, both sides (P10 a; the card says so)
    if (o.comparable && ops?.measures.some(m => m.second && !m.not_on.includes(o.kind))) for (const op of ['gt', 'lt'] as TestOp[])
      opts.push({ key:`flow_level|${o.key}|state|${op}`, label:`${cap(o.comparable)} ${op === 'gt' ? 'above' : 'below'} ${o.label}`, kind:'state', form:'state_level', output:o.key, op,
        value:'none', between:false, within:false, unit:o.unit, defaults:{} });
    const label = (op: TestOp) => multi ? `${o.label} ${OPLABEL[op]}` : cap(OPLABEL[op]);
    const add = (kind: TestKind, op: TestOp) => opts.push({ key:`flow|${o.key}|${kind}|${op}`, label:label(op), kind, form:'metric', output:o.key, op, value:'input',
      between:op === 'between', within:kind === 'event', unit:o.unit, defaults:{} });
    if (testTakes(ops, 'value', o.kind)) { add('value', 'gt'); add('value', 'lt') }
    if (testTakes(ops, 'range', o.kind)) add('value', 'between');
    // a cross reads the session before as well, and at least one session of `within` (K1)
    if (testTakes(ops, 'cross', o.kind, true) && (budget == null || budget >= 1)) { add('event', 'crosses_above'); add('event', 'crosses_below') }
  }
  const first = opts.find(x => outs.find(o => o.key === x.output)?.drawn) ?? opts[0];
  const usable = opts.length > 0 || (!!ops && outs.some(o => o.drawn));
  return { ...base, opts, def:{ opt:first?.key || '', value:0, value2:'', within:budget == null ? 5 : Math.max(1, Math.min(5, budget)) },
    ...(base.available && !usable ? { available:false, availability:'REQUIRES_DATA' as Availability, reason:'No test is offered on this flow indicator here yet.' } : {}) };
}

/** Every entry of the catalog, indicators first (registry order), then metrics, then fundamentals. */
export function entriesOf(cat: CatalogResponse): Entry[] {
  return [
    ...cat.indicators.map(ind => { const e = indicatorEntry(ind, cat.indicators); if (cat.operators) e.ops = cat.operators; return e }),
    ...cat.metrics.map(m => m.flow ? flowEntry(m, cat) : metricEntry(m, 'metric', cat.indicators)),
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
export const isDefP = (p: EntryParam | CatalogParam, v: ParamValue | undefined) => v === undefined || String(v) === String(p.default);

const BROKER_CODE = /^[A-Z0-9]{1,6}$/, ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const isIsoDate = (s: string) => ISO_DATE.test(s) && !Number.isNaN(Date.parse(s + 'T00:00:00Z')) && new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) === s;
/** Check one parameter value against the catalog (report 9.2: invalid input is refused in place with the field and
    the allowed range, never rounded or ignored). Returns the error text or null. A flow indicator's list, anchor date
    and broker codes by the Terminal's rules (flowRegistry.json; the core's flowmetrics.ts checkParam), each message
    with a right and a wrong example. */
export function paramError(p: EntryParam, v: ParamValue): string | null {
  if (p.type === 'multi') {
    const l = listOf(v), all = p.options || [];
    if (!l.length) return `Pick at least one of ${all.map(x => optionText(p, x)).join(', ')}.`;
    if (l.some(x => !all.includes(x)) || new Set(l).size !== l.length) return `Pick each of ${all.map(x => optionText(p, x)).join(', ')} at most once.`;
    return null;
  }
  if (p.type === 'date') {
    if (v === 'view') return null;
    const w = p.dates;
    if (typeof v !== 'string' || !isIsoDate(v)) return `Enter a date (YYYY-MM-DD), or leave it empty for the first session of the broker data${w?.first ? ` (right: ${w.first}; wrong: last week)` : ''}.`;
    if (w?.first && w.last && (v < w.first || v > w.last)) return `Pick a date inside the broker data the Screener holds, ${w.first} to ${w.last} (right: ${w.first}; wrong: a date before ${w.first}).`;
    return null;
  }
  if (p.type === 'brokers') {
    const l = listOf(v);
    if (!l.length) return null;                                     // the Terminal's default
    if (l.some(x => !BROKER_CODE.test(x))) return 'Enter broker codes of up to 6 letters or digits, separated by commas (right: YP, AK; wrong: Mirae).';
    if (new Set(l).size !== l.length) return 'Name each broker once (right: YP, AK; wrong: YP, YP).';
    const c = p.count;
    if (c && l.length < c.min) return `Name at least ${c.min} broker${c.min === 1 ? '' : 's'}.`;
    if (c?.max != null && l.length > c.max) return `Name at most ${c.max} brokers (right: ${['YP', 'AK', 'CC', 'PD', 'XL', 'NI'].slice(0, c.max).join(', ')}; wrong: one more).`;
    return null;
  }
  if (p.type === 'enum') return (p.options || []).includes(String(v)) ? null : `Pick one of ${(p.options || []).map(x => optionText(p, x)).join(', ')}.`;
  if (p.type === 'boolean') return typeof v === 'boolean' ? null : 'Pick true or false.';
  if (typeof v !== 'number' || !Number.isFinite(v)) return 'Enter a number.';
  if ((p.integer || p.type === 'integer') && !Number.isInteger(v)) return 'Enter a whole number.';
  if (p.min != null && (p.exclusive_min ? v <= p.min : v < p.min)) return p.exclusive_min ? `Must be above ${p.min}.` : `Must be at least ${p.min}.`;
  if (p.max != null && v > p.max) return `Must be at most ${p.max}.`;
  return null;
}
export const rangeText = (p: EntryParam | CatalogParam) => p.type === 'date' ? ((p as EntryParam).dates?.first ? `${(p as EntryParam).dates!.first} to ${(p as EntryParam).dates!.last}` : '')
  : p.type === 'enum' || p.type === 'boolean' || p.type === 'multi' || p.type === 'brokers' ? ''
  : `${p.min != null ? (p.exclusive_min ? `> ${p.min}` : `≥ ${p.min}`) : ''}${p.min != null && p.max != null ? ', ' : ''}${p.max != null ? `≤ ${p.max}` : ''}`;

/* EXEC-SCREENER-V21 (integration, data audit D-1): how a value of an entry's test is written, from the catalog (the
   output's unit and display_unit, the test form, a metric's unit), never from the wire's coarse Cell.unit, which says
   'dimensionless' for a percent distance, ROC, ATR % and historical volatility (core transforms.ts pct_distance). */
/** The format of the value an option reads (`form` value / value_pct_distance / value_band_position / metric). */
export function formatOfOpt(e: Entry | undefined, o: Opt | undefined): ValueFormat {
  if (!e) return formatOfMetric(o?.unit);
  // a flow output: its own unit at the catalog's setup (an amount in rupiah, a percent, a day count, a price level)
  if (e.flow) return formatOfMetric(o?.unit ?? flowOutputs(e)[0]?.unit ?? e.metric?.unit);
  if (e.kind === 'indicator') {
    const out = e.indicator?.outputs.find(x => x.key === o?.output) ?? e.indicator?.outputs[0];
    return formatOfOutput(out?.unit, out?.display_unit, o?.form);
  }
  return formatOfMetric(e.metric?.unit ?? o?.unit);
}
/** The format of a STATE side: the series the option compares (a price level for a moving average or a band). */
export function formatOfSide(e: Entry | undefined, o: Opt | undefined): ValueFormat {
  if (e?.kind !== 'indicator') return formatOfMetric(e?.metric?.unit ?? o?.unit);
  const out = e.indicator?.outputs.find(x => x.key === o?.output) ?? e.indicator?.outputs[0];
  return formatOfOutput(out?.unit, out?.display_unit, null);
}
