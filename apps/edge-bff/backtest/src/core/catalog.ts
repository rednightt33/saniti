/* The backtest page's condition catalog as version-controlled configuration, and the one mapping from the page's
   condition cards to the wire conditions of contract.ts. The page renders the cards (labels, operators, units as on
   backtest.html); the worker only ever receives wire conditions, so the legacy cards run on the Terminal's verified
   indicator outputs (registry I01/I07/I13/I15/I27) instead of the mock-up's demo formulas.
   Pure module: no DOM and no Node API (the page and the worker import it). */
import type { Condition, IndicatorCondition, Op, ParamMap } from './contract.ts';
import { BY_ID, ValidationError } from './registry.ts';

/* ---- display scale: wire value = display value x scale ------------------------------------------------------ */
/* The page shows a dip in percent (-3 %) and flow in Rp B (1 = Rp 1 miliar); the wire carries a fraction and IDR
   (contract.ts header). Everything else is shown in its own unit. The sensitivity grid steps in display units
   (page: step = max(1, |base| x 0.2)), so the worker converts with the same table. */
export const DISPLAY: Record<'indicator' | 'dip' | 'breakout' | 'volspike' | 'macross' | 'macd' | 'fnet' | 'broker' | 'top5', number> = {
  indicator: 1, dip: 0.01, breakout: 1, volspike: 1, macross: 1, macd: 1, fnet: 1e9, broker: 1e9, top5: 1e9,
};
/** The display scale of a wire condition's threshold (null when the condition has no numeric threshold). */
export function displayScale(c: Condition): number | null {
  if (c.kind === 'indicator') return c.rhs.type === 'value' ? DISPLAY.indicator : null;
  if (c.kind === 'flow') return DISPLAY[c.type];
  return c.type === 'dip' || c.type === 'volspike' ? DISPLAY[c.type] : null;
}
/** The numeric threshold of a wire condition in wire units, or null. */
export function threshold(c: Condition): number | null {
  if (c.kind === 'indicator') return c.rhs.type === 'value' ? c.rhs.value : null;
  if (c.kind === 'flow') return c.value;
  return c.type === 'dip' || c.type === 'volspike' ? (c.value ?? null) : null;
}
/** The same condition with another threshold (wire units). */
export function withThreshold<T extends Condition>(c: T, value: number): T {
  if (c.kind === 'indicator') return { ...c, rhs: { type: 'value', value } } as T;
  return { ...c, value } as T;
}

/* ---- the page's legacy condition cards (backtest.html CATALOG, without its demo `eval`) ---------------------- */
export type LegacyType = 'adx' | 'dmi' | 'stoch' | 'rsi' | 'macd' | 'ma' | 'macross' | 'volspike' | 'breakout' | 'bb' | 'dip' | 'fnet' | 'broker' | 'top5';
export interface LegacySpec {
  group: 'tech' | 'price' | 'flow'; label: string; desc: string;
  params: [key: string, label: string, def: number | string][];
  ops: string[]; opLabels?: Record<string, string>; val?: number; unit?: string; noVal?: boolean;
}
export const LEGACY: Record<LegacyType, LegacySpec> = {
  adx: { group: 'tech', label: 'ADX', desc: 'Trend strength', params: [['len', 'Length', 14]], ops: ['gt', 'lt', 'ca'], val: 30, unit: '' },
  dmi: { group: 'tech', label: 'DMI direction', desc: '+DI above −DI (uptrend)', params: [['len', 'Length', 14]], ops: ['plus', 'pcross'], opLabels: { plus: '+DI above −DI', pcross: '+DI crosses above −DI' }, noVal: true },
  stoch: { group: 'tech', label: 'Stochastic %K', desc: 'Momentum oscillator 0–100', params: [['len', 'Length', 14], ['smooth', 'Smooth', 3]], ops: ['lt', 'gt', 'ca', 'cb'], val: 20 },
  rsi: { group: 'tech', label: 'RSI', desc: 'Relative strength 0–100', params: [['len', 'Length', 14]], ops: ['lt', 'gt', 'ca', 'cb'], val: 30 },
  macd: { group: 'tech', label: 'MACD', desc: 'Divergence, signal cross, histogram', params: [['fast', 'Fast', 12], ['slow', 'Slow', 26], ['sig', 'Signal', 9]], ops: ['bdiv', 'xsig', 'hpos'], opLabels: { bdiv: 'Bullish divergence', xsig: 'Crosses above signal', hpos: 'Histogram > 0' }, noVal: true },
  ma: { group: 'tech', label: 'Price vs MA', desc: 'Close relative to a moving average', params: [['len', 'MA length', 50]], ops: ['above', 'below', 'xab'], opLabels: { above: 'Close above MA', below: 'Close below MA', xab: 'Close crosses above MA' }, noVal: true },
  macross: { group: 'tech', label: 'MA cross', desc: 'Fast MA vs slow MA', params: [['fast', 'Fast', 20], ['slow', 'Slow', 50]], ops: ['golden', 'fabove'], opLabels: { golden: 'Golden cross', fabove: 'Fast above slow' }, noVal: true },
  volspike: { group: 'tech', label: 'Volume spike', desc: 'Volume ÷ average volume', params: [['len', 'Avg length', 20]], ops: ['gt'], val: 2, unit: '×' },
  breakout: { group: 'tech', label: 'Breakout', desc: 'Close above the highest high of N days', params: [['len', 'Days', 20]], ops: ['brk'], opLabels: { brk: 'Close > N-day high' }, noVal: true },
  bb: { group: 'tech', label: 'Bollinger Bands', desc: 'Close vs lower band', params: [['len', 'Length', 20], ['k', 'Std dev', 2]], ops: ['blow', 'bxin'], opLabels: { blow: 'Close below lower band', bxin: 'Close back inside lower band' }, noVal: true },
  dip: { group: 'price', label: 'Daily drop', desc: 'One-day return at or below −X%', params: [], ops: ['lt'], val: -3, unit: '%' },
  fnet: { group: 'flow', label: 'Foreign net flow', desc: 'Sum of foreign net buy over N days', params: [['len', 'Days', 5]], ops: ['gt', 'lt'], val: 0, unit: 'Rp B' },
  broker: { group: 'flow', label: 'Broker net buy', desc: 'A chosen broker’s net buy over N days', params: [['broker', 'Broker', 'YU'], ['len', 'Days', 5]], ops: ['gt'], val: 5, unit: 'Rp B' },
  top5: { group: 'flow', label: 'Top-5 broker accumulation', desc: 'Net buy of the 5 biggest buyers minus 5 biggest sellers', params: [['len', 'Days', 10]], ops: ['gt'], val: 0, unit: 'Rp B' },
};
/** The page's "Add condition" groups for registry-external conditions (backtest.html EXTRA_GROUPS). */
export const EXTRA_GROUPS: [string, LegacyType[]][] = [['Flow & bandarmology', ['fnet', 'broker', 'top5']], ['Price action & patterns', ['dip', 'breakout', 'volspike', 'macross', 'macd']]];

/** A legacy card as the page keeps it: the card's operator, value (display units) and its parameters by key. */
export interface LegacyCard { id: string; type: LegacyType; on: boolean; op: string; val?: number; [param: string]: unknown }

/** A legacy card with its catalog defaults, then `over` (the page's mkCond, without the random id). */
export function legacyCard(type: LegacyType, id: string, over: Partial<LegacyCard> = {}): LegacyCard {
  const s = LEGACY[type], p: Record<string, unknown> = {};
  for (const [k, , d] of s.params) p[k] = d;
  return { id, type, on: true, op: s.ops[0], val: s.val, ...p, ...over } as LegacyCard;
}

const OP: Record<string, Op> = { gt: 'gt', lt: 'lt', ca: 'crosses_above', cb: 'crosses_below' };
const whole = (c: LegacyCard, key: string): number => {
  const v = c[key];
  if (typeof v !== 'number' || !Number.isInteger(v)) throw new ValidationError('INVALID_PARAM', `${c.id}.${key}`, `${LEGACY[c.type].label}: ${key} must be a whole number.`);
  return v;
};
const value = (c: LegacyCard): number => {
  if (typeof c.val !== 'number' || !Number.isFinite(c.val)) throw new ValidationError('INVALID_CONDITION', `${c.id}.val`, `${LEGACY[c.type].label}: the value must be a number.`);
  return c.val;
};
const op = (c: LegacyCard): string => {
  if (!LEGACY[c.type].ops.includes(c.op)) throw new ValidationError('INVALID_CONDITION', `${c.id}.op`, `${LEGACY[c.type].label}: unknown condition ${c.op}.`);
  return c.op;
};
const ind = (c: LegacyCard, indicator: string, params: ParamMap, lhs: IndicatorCondition['lhs'], o: Op, rhs: IndicatorCondition['rhs']): IndicatorCondition =>
  ({ id: c.id, enabled: c.on, kind: 'indicator', indicator, params, lhs, op: o, rhs });

/** The wire condition of a legacy card. The mock-up's demo formulas are replaced by the registry indicators they
    approximate, with the card's parameters mapped one to one:
    adx -> I07 adx (DI length = ADX smoothing = Length); dmi -> I07 plus_di vs minus_di; stoch -> I15 k (Length,
    Smooth; %D keeps its default and is not compared); rsi -> I13; ma -> close vs I01 sma; bb -> close vs I27 lower
    (bxin = crosses above: the page's `c[i-1] < lb[i-1] && c[i] >= lb[i]` differs only when a close equals the band
    exactly); macd, macross, volspike, breakout, dip -> price_action; fnet, broker, top5 -> flow. */
export function legacyToCondition(c: LegacyCard): Condition {
  if (!LEGACY[c.type]) throw new ValidationError('UNKNOWN_CONDITION', `${c.id}.type`, `Unknown condition type ${String(c.type)}.`);
  const o = op(c), enabled = c.on;
  switch (c.type) {
    case 'adx': { const n = whole(c, 'len'); return ind(c, 'I07', { di_length: n, adx_smoothing: n }, { type: 'output', output: 'adx' }, OP[o], { type: 'value', value: value(c) }) }
    case 'dmi': { const n = whole(c, 'len'); return ind(c, 'I07', { di_length: n, adx_smoothing: n }, { type: 'output', output: 'plus_di' }, o === 'plus' ? 'gt' : 'crosses_above', { type: 'output', output: 'minus_di' }) }
    case 'stoch': return ind(c, 'I15', { k_length: whole(c, 'len'), smooth_k: whole(c, 'smooth') }, { type: 'output', output: 'k' }, OP[o], { type: 'value', value: value(c) });
    case 'rsi': return ind(c, 'I13', { length: whole(c, 'len'), source: 'close' }, { type: 'output', output: 'rsi' }, OP[o], { type: 'value', value: value(c) });
    case 'ma': return ind(c, 'I01', { length: whole(c, 'len'), source: 'close' }, { type: 'price' }, o === 'above' ? 'gt' : o === 'below' ? 'lt' : 'crosses_above', { type: 'output', output: 'sma' });
    case 'bb': {
      const k = c.k;
      if (typeof k !== 'number' || !Number.isFinite(k)) throw new ValidationError('INVALID_PARAM', `${c.id}.k`, 'Bollinger Bands: Std dev must be a number.');
      return ind(c, 'I27', { length: whole(c, 'len'), std_dev: k, source: 'close' }, { type: 'price' }, o === 'blow' ? 'lt' : 'crosses_above', { type: 'output', output: 'lower' });
    }
    case 'macd': return { id: c.id, enabled, kind: 'price_action', type: 'macd', params: { fast_length: whole(c, 'fast'), slow_length: whole(c, 'slow'), signal_length: whole(c, 'sig') },
      op: o === 'bdiv' ? 'bullish_divergence' : o === 'xsig' ? 'crosses_above_signal' : 'histogram_positive' };
    case 'macross': return { id: c.id, enabled, kind: 'price_action', type: 'macross', params: { fast_length: whole(c, 'fast'), slow_length: whole(c, 'slow') }, op: o === 'golden' ? 'golden_cross' : 'fast_above_slow' };
    case 'volspike': return { id: c.id, enabled, kind: 'price_action', type: 'volspike', params: { length: whole(c, 'len') }, op: 'gt', value: value(c) * DISPLAY.volspike };
    case 'breakout': return { id: c.id, enabled, kind: 'price_action', type: 'breakout', params: { length: whole(c, 'len') }, op: 'close_above_high' };
    case 'dip': return { id: c.id, enabled, kind: 'price_action', type: 'dip', op: 'lte', value: value(c) * DISPLAY.dip };
    case 'fnet': return { id: c.id, enabled, kind: 'flow', type: 'fnet', params: { length: whole(c, 'len') }, op: o as 'gt' | 'lt', value: value(c) * DISPLAY.fnet };
    case 'broker': {
      if (typeof c.broker !== 'string' || !c.broker) throw new ValidationError('INVALID_PARAM', `${c.id}.broker`, 'Broker net buy: choose a broker.');
      return { id: c.id, enabled, kind: 'flow', type: 'broker', params: { length: whole(c, 'len'), broker: c.broker }, op: 'gt', value: value(c) * DISPLAY.broker };
    }
    case 'top5': return { id: c.id, enabled, kind: 'flow', type: 'top5', params: { length: whole(c, 'len') }, op: 'gt', value: value(c) * DISPLAY.top5 };
  }
}

/* ---- the page's registry cards (backtest.html mkReg: type 'reg', ind, p, lhs, op, rhs) ----------------------- */
export interface RegCard {
  id: string; type: 'reg'; on: boolean; ind: string; p: Record<string, unknown>;
  lhs: { t: 'price' } | { t: 'out'; o: string }; op: 'gt' | 'lt' | 'ca' | 'cb';
  rhs: { t: 'out'; o: string } | { t: 'val'; v: number };
}
/** The wire condition of a registry card. The page's form shows every non-fixed workbook parameter; the ones the
    calculation module does not read (registry `not_accepted`, e.g. I37 include_current_bar) are sent only when they
    hold the value the module implements, and then left out; any other value is refused, never ignored. */
export function regToCondition(c: RegCard): IndicatorCondition {
  const r = BY_ID[c.ind];
  if (!r) throw new ValidationError('UNKNOWN_INDICATOR', `${c.id}.ind`, `${String(c.ind)} is not an indicator of the registry.`);
  const accepted = new Set(r.params.map(p => p.key)), params: ParamMap = {};
  for (const [k, v] of Object.entries(c.p || {})) {
    if (accepted.has(k)) { params[k] = v as ParamMap[string]; continue }
    const na = r.not_accepted.find(n => n.key === k);
    if (na && JSON.stringify(na.value) === JSON.stringify(v)) continue;
    throw new ValidationError('PARAM_NOT_ACCEPTED', `${c.id}.p.${k}`, `${r.name}: ${k} = ${JSON.stringify(v)} is not supported by the backtest${na ? ` (${na.reason})` : ''}.`);
  }
  const lhs: IndicatorCondition['lhs'] = c.lhs.t === 'price' ? { type: 'price' } : { type: 'output', output: c.lhs.o };
  const rhs: IndicatorCondition['rhs'] = c.rhs.t === 'val' ? { type: 'value', value: +c.rhs.v } : { type: 'output', output: c.rhs.o };
  return { id: c.id, enabled: c.on, kind: 'indicator', indicator: r.id, params, lhs, op: OP[c.op], rhs };
}

/* ---- quick-start templates (backtest.html TEMPLATES and EXIT_TEMPLATES), as configuration -------------------- */
/* Entry templates replace the entry conditions; exit templates add one exit condition. Cards are built with the
   catalog defaults; registry cards name only what differs from the registry defaults (the page's mkRegWith). */
export const ENTRY_TEMPLATES: Record<string, [LegacyType, Partial<LegacyCard>][]> = {
  'Trend + pullback': [['adx', { val: 25 }], ['dmi', {}], ['stoch', { op: 'lt', val: 30 }]],
  'Divergence + flow': [['macd', { op: 'bdiv' }], ['fnet', { len: 5, val: 0 }], ['broker', { broker: 'YU', len: 5, val: 1 }]],
  'Breakout + volume': [['breakout', { len: 20 }], ['volspike', { val: 2 }], ['ma', { op: 'above', len: 50 }]],
  'Bandar accumulation': [['top5', { len: 10, val: 2 }], ['ma', { op: 'above', len: 20 }]],
};
export type ExitTemplate =
  | { kind: 'reg'; ind: string; p?: Record<string, unknown>; lhs: RegCard['lhs']; op: RegCard['op']; rhs: RegCard['rhs'] }
  | { kind: 'legacy'; type: LegacyType; over: Partial<LegacyCard> };
export const EXIT_TEMPLATES: Record<string, ExitTemplate> = {
  'RSI > 70': { kind: 'reg', ind: 'I13', lhs: { t: 'out', o: 'rsi' }, op: 'gt', rhs: { t: 'val', v: 70 } },
  'Stoch %K > 80': { kind: 'reg', ind: 'I15', lhs: { t: 'out', o: 'k' }, op: 'gt', rhs: { t: 'val', v: 80 } },
  'Close < MA20': { kind: 'reg', ind: 'I01', p: { length: 20 }, lhs: { t: 'price' }, op: 'lt', rhs: { t: 'out', o: 'sma' } },
  'MACD crosses below signal': { kind: 'reg', ind: 'I06', lhs: { t: 'out', o: 'macd' }, op: 'cb', rhs: { t: 'out', o: 'signal' } },
  'Foreign net 5D < 0': { kind: 'legacy', type: 'fnet', over: { op: 'lt', val: 0, len: 5 } },
};

/** The page's default entry conditions (S.conds at boot). */
export const DEFAULT_ENTRY: [LegacyType, Partial<LegacyCard>][] = [
  ['adx', { val: 25 }], ['stoch', { op: 'lt', val: 30 }], ['macd', { op: 'bdiv' }], ['fnet', { len: 5, val: 0 }], ['broker', { broker: 'YU', len: 5, val: 1 }],
];

/** Whether a wire condition needs the broker files (flow conditions and the 'fnet' portfolio ranking). */
export const needsFlow = (c: Condition): boolean => c.kind === 'flow';
