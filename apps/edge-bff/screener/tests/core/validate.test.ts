/* Refusals and normalization of a definition (report TARGET ARCHITECTURE 6.1 I7, 6.9, 6.12; API CONTRACT 8.5, 8.8,
   8.9; TEST PLAN 10b.3 "between", "within boundaries", 10b.5 "Board, index, market cap, free float, notation", 10b.11
   "Refusal messages and limits"): every refusal carries the report 8.8 code, the field in the request body and the fix;
   nothing is clamped, rounded or reordered; the normalized definition states every default, so its hash does not
   depend on whether a default was sent; labels never change the hash; every technical preset validates. */
import { describe, expect, it } from 'vitest';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import type { Definition } from '../../src/core/contract.ts';
import { PRESETS } from '../../src/core/catalog.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { definitionHash, validateDefinition, validateTest, validateUniverse } from '../../src/core/validate.ts';
import { vctx } from './helpers.ts';

const CTX = vctx(['BBCA', 'BBRI', 'TLKM', 'ASII']);
const U = { ...UNIVERSE_DEFAULTS } as any;
const close = { kind: 'price', field: 'close' };
const ind = (indicator: string, output: string, params?: Record<string, unknown>) => ({ kind: 'indicator', indicator, output, ...(params ? { params } : {}) });
const def = (conditions: unknown[], o: Record<string, unknown> = {}) => ({ universe: U, conditions, logic: 'all', ...o });
const c = (test: unknown, id = 'a', enabled = true) => ({ id, enabled, test });
function refusal(fn: () => unknown): ScreenerError {
  try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e }
  throw new Error('expected a ScreenerError');
}
const why = (x: unknown) => { const e = refusal(() => validateDefinition(x, CTX)); return [e.code, e.field] };

describe('normalization and the definition hash', () => {
  it('states every default: a request that leaves defaults out hashes as one that states them; labels never change it', async () => {
    const short = validateDefinition({ universe: { security_types: ['stock'] }, conditions: [c({ kind: 'value', op: 'lt', value: 30, metric: ind('I13', 'rsi') })], logic: 'all' }, CTX);
    const long = validateDefinition({
      universe: { security_types: ['stock'], sectors_in: [], include_unclassified: false, price_min: null, adv20_min_idr: null, min_history_bars: null, traded_on_eval_date: true, exclude_price_breaks: true, tickers: null, metric_filters: [] },
      conditions: [{ ...c({ kind: 'value', op: 'lt', value: 30, metric: ind('I13', 'rsi', { length: 14, source: 'close' }) }), label: 'RSI oversold' }], logic: 'all' }, CTX);
    expect(short.conditions[0].test).toEqual({ kind: 'value', metric: { kind: 'indicator', indicator: 'I13', params: { length: 14, source: 'close' }, output: 'rsi' }, op: 'lt', value: 30 });
    expect(short.universe).toEqual({ security_types: ['stock'], include_unclassified: false, price_min: null, adv20_min_idr: null, min_history_bars: null, traded_on_eval_date: true, exclude_price_breaks: true, tickers: null });
    expect(await definitionHash(short)).toBe(await definitionHash(long));
    expect(long.conditions[0].label).toBe('RSI oversold');
    const other = validateDefinition(def([c({ kind: 'value', op: 'lt', value: 30, metric: ind('I13', 'rsi', { length: 7 }) })]), CTX);
    expect(await definitionHash(other)).not.toBe(await definitionHash(validateDefinition(def([c({ kind: 'value', op: 'lt', value: 30, metric: ind('I13', 'rsi') })]), CTX)));
  });
  it('normalizes transforms and patterns with every argument and parameter, and never reorders a side', () => {
    const d = validateDefinition(def([
      c({ kind: 'state', lhs: ind('I40', 'obv'), op: 'gt', rhs: { kind: 'transform', fn: 'ma', of: ind('I40', 'obv') } }),
      c({ kind: 'event', within: 3, signal: { pattern: { kind: 'pattern', type: 'breakout' } } }, 'b'),
    ]), CTX);
    expect(d.conditions[0].test).toEqual({ kind: 'state', lhs: { kind: 'indicator', indicator: 'I40', params: {}, output: 'obv' }, op: 'gt',
      rhs: { kind: 'transform', fn: 'ma', of: { kind: 'indicator', indicator: 'I40', params: {}, output: 'obv' }, args: { ma: 'EMA', length: 20 } } });
    expect(d.conditions[1].test).toEqual({ kind: 'event', signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: 20 } } }, within: 3 });
  });
  it('every preset of presets.json whose legs are available validates, and is stable under normalization', async () => {
    for (const p of PRESETS.presets.filter(x => ['Technical'].includes(x.category) && x.id !== 'ichi')) {
      const n = validateDefinition(p.definition, CTX);
      expect(validateDefinition(n, CTX)).toEqual(n);
      expect(await definitionHash(validateDefinition(n, CTX))).toBe(await definitionHash(n));
    }
  });
});

describe('VALUE tests', () => {
  it('between needs value <= value2 (field value2, never swapped); value = value2 is accepted; value2 is only for between', () => {
    const rsi = ind('I13', 'rsi');
    expect(why(def([c({ kind: 'value', op: 'between', value: 50, value2: 30, metric: rsi })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.value2']);
    expect(validateDefinition(def([c({ kind: 'value', op: 'between', value: 30, value2: 30, metric: rsi })]), CTX).conditions[0].test).toMatchObject({ value: 30, value2: 30 });
    expect(validateDefinition(def([c({ kind: 'value', op: 'between', value: -10, value2: -5, metric: { kind: 'transform', fn: 'pct_distance', of: ind('I01', 'sma') } })]), CTX).conditions.length).toBe(1);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 30, value2: 50, metric: rsi })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.value2']);
    expect(why(def([c({ kind: 'value', op: 'gte', value: 30, metric: rsi })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.op']);
    expect(why(def([c({ kind: 'value', op: 'gt', value: '30', metric: rsi })]))).toEqual(['INVALID_INPUT', 'definition.conditions[0].test.value']);
  });
  it('allows only the forms the output offers: no raw SMA value, no RSI distance, no raw cumulative level (with its reason)', () => {
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1000, metric: ind('I01', 'sma') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric']);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: { kind: 'transform', fn: 'pct_distance', of: ind('I13', 'rsi') } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric']);
    const obv = refusal(() => validateDefinition(def([c({ kind: 'value', op: 'gt', value: 1, metric: ind('I40', 'obv') })]), CTX));
    expect(obv.message).toMatch(/depends on where its history starts/);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 0.5, metric: { kind: 'pattern', type: 'breakout' } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric']);
  });
});

describe('STATE and EVENT tests', () => {
  it('a price is compared only with a level of its own kind, on the left; a value goes on the right', () => {
    expect(why(def([c({ kind: 'state', lhs: close, op: 'gt', rhs: ind('I13', 'rsi') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs']);
    expect(why(def([c({ kind: 'state', lhs: { kind: 'price', field: 'volume' }, op: 'gt', rhs: ind('I01', 'sma') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.lhs.field']);
    expect(why(def([c({ kind: 'state', lhs: ind('I01', 'sma'), op: 'lt', rhs: close })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test']);
    expect(why(def([c({ kind: 'state', lhs: { value: 30 }, op: 'gt', rhs: ind('I13', 'rsi') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.lhs']);
    expect(validateDefinition(def([c({ kind: 'state', lhs: { kind: 'price', field: 'volume' }, op: 'gt', rhs: ind('I35', 'volume_sma') })]), CTX).conditions.length).toBe(1);
  });
  it('allows the operators of each form only: the Donchian upper band is crossed upwards, the lower downwards', () => {
    expect(validateDefinition(def([c({ kind: 'event', within: 5, signal: { lhs: close, op: 'crosses_above', rhs: ind('I10', 'upper') } })]), CTX).conditions.length).toBe(1);
    expect(why(def([c({ kind: 'state', lhs: close, op: 'lt', rhs: ind('I10', 'upper') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test']);
    expect(why(def([c({ kind: 'event', within: 5, signal: { lhs: close, op: 'crosses_below', rhs: ind('I10', 'upper') } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.signal']);
  });
  it('outputs of one instance, a second instance, rising and vs its MA are the forms of report 6.9.1', () => {
    const ok = (t: unknown) => validateDefinition(def([c(t)]), CTX).conditions[0].test;
    expect(ok({ kind: 'event', within: 5, signal: { lhs: ind('I06', 'macd'), op: 'crosses_above', rhs: ind('I06', 'signal') } })).toBeTruthy();
    expect(ok({ kind: 'event', within: 20, signal: { lhs: ind('I01', 'sma', { length: 50 }), op: 'crosses_above', rhs: ind('I01', 'sma', { length: 200 }) } })).toBeTruthy();
    expect(ok({ kind: 'state', lhs: ind('I01', 'sma', { length: 200 }), op: 'gt', rhs: { kind: 'transform', fn: 'lag', of: ind('I01', 'sma', { length: 200 }), args: { bars: 21 } } })).toBeTruthy();
    expect(why(def([c({ kind: 'state', lhs: ind('I06', 'macd'), op: 'gt', rhs: ind('I06', 'signal', { fast_length: 5 }) })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs.params']);
    expect(why(def([c({ kind: 'state', lhs: ind('I01', 'sma'), op: 'gt', rhs: { kind: 'transform', fn: 'lag', of: ind('I01', 'sma', { length: 50 }), args: { bars: 5 } } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs.of']);
    expect(why(def([c({ kind: 'state', lhs: ind('I13', 'rsi'), op: 'gt', rhs: ind('I15', 'k') })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs']);
  });
  it('a price against a transform level: close above the 252-session high of the high reads its previous bar; a volume level is refused for close', () => {
    expect(validateDefinition(def([c({ kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } } })]), CTX).conditions.length).toBe(1);
    expect(why(def([c({ kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'volume' }, args: { length: 20 } } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs']);
  });
  it('within is 1 to within_max: N = within_max accepted, within_max + 1 is LIMIT_EXCEEDED, 0 or 2.5 INVALID_CONDITION', () => {
    const ev = (within: unknown) => def([c({ kind: 'event', within, signal: { lhs: close, op: 'crosses_above', rhs: ind('I01', 'sma') } })]);
    expect(validateDefinition(ev(130), CTX).conditions.length).toBe(1);
    const e = refusal(() => validateDefinition(ev(131), CTX));
    expect([e.code, e.field, e.details]).toEqual(['LIMIT_EXCEEDED', 'definition.conditions[0].test.within', { limit: 'within_max', allowed: 130, needed: 131 }]);
    expect(why(ev(0))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.within']);
    expect(why(ev(2.5))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.within']);
  });
  it('a pattern is tested on its own, as the catalog offers it (Ichimoku waits for a registry release)', () => {
    expect(why(def([c({ kind: 'state', lhs: { kind: 'pattern', type: 'breakout' }, op: 'gt', rhs: { value: 0 } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test']);
    const e = refusal(() => validateDefinition(def([c({ kind: 'state', pattern: { kind: 'pattern', type: 'ichimoku_above' } })]), CTX));
    expect([e.code, (e.details as any).availability]).toEqual(['METRIC_UNAVAILABLE', 'REQUIRES_DECISION']);
    expect(why(def([c({ kind: 'event', within: 5, signal: { pattern: { kind: 'pattern', type: 'ichimoku_above' } } })]))[0]).toBe('METRIC_UNAVAILABLE');
  });
});

describe('parameters through the registry', () => {
  it('UNKNOWN_INDICATOR, PARAM_OUT_OF_RANGE, an option not offered (P17 a) and an output left without values name their field', () => {
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: ind('I99', 'x') })]))).toEqual(['UNKNOWN_INDICATOR', 'definition.conditions[0].test.metric.indicator']);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: ind('I13', 'rsi', { length: 0 }) })]))).toEqual(['PARAM_OUT_OF_RANGE', 'definition.conditions[0].test.metric.params.length']);
    expect(why(def([c({ kind: 'state', lhs: close, op: 'gt', rhs: ind('I43', 'vwap', { anchor: 'Session' }) })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs.params.anchor']);
    const none = refusal(() => validateDefinition(def([c({ kind: 'state', lhs: close, op: 'gt', rhs: ind('I43', 'upper1', { anchor: 'Week', bands_mode: 'None' }) })]), CTX));
    expect([none.code, none.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.rhs.params.bands_mode']);
    expect((none.details as any).allowed).not.toContain('None');
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: ind('I13', 'rsi', { lenght: 7 }) })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.params.lenght']);
  });
});

describe('metrics without data (report 6.12; TEST PLAN 10b.5)', () => {
  it('market cap, free float, index, board and notation, fundamentals and flow are METRIC_UNAVAILABLE with the reason', () => {
    for (const attr of ['cap', 'freeFloat', 'index_membership', 'listing_board', 'special_notation', 'pe', 'npl']) {
      const e = refusal(() => validateDefinition(def([c({ kind: 'value', op: 'gt', value: 1, metric: { kind: 'universe', attr } })]), CTX));
      expect([attr, e.code, e.field, (e.details as any).availability]).toEqual([attr, 'METRIC_UNAVAILABLE', 'definition.conditions[0].test.metric', 'REQUIRES_DATA']);
      expect((e.details as any).reason).toMatch(/needs the published file/);
    }
    const f = refusal(() => validateDefinition(def([c({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'flow', metric: 'fnet', params: { window: 20 } } })]), CTX));
    expect([f.code, (f.details as any).metric, (f.details as any).availability]).toEqual(['METRIC_UNAVAILABLE', 'fnet', 'REQUIRES_DATA']);
    const mf = refusal(() => validateDefinition({ ...def([]), universe: { ...U, metric_filters: [{ kind: 'value', op: 'gt', value: 5e12, metric: { kind: 'universe', attr: 'cap' } }] } }, CTX));
    expect([mf.code, mf.field]).toEqual(['METRIC_UNAVAILABLE', 'definition.universe.metric_filters[0].metric']);
  });
  it('a switched-off condition on such a metric is kept (checked for shape only)', () => {
    const d = validateDefinition(def([c({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'flow', metric: 'fnet', params: { window: 20 } } }, 'a', false)]), CTX);
    expect(d.conditions[0].enabled).toBe(false);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'flow', metric: 'nope', params: { window: 20 } } }, 'a', false)]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.metric']);
  });
});

describe('the definition, its conditions and limits', () => {
  it('every object is closed: an unknown field is INVALID_INPUT naming it', () => {
    expect(why({ ...def([]), sort: 'adv' })).toEqual(['INVALID_INPUT', 'definition.sort']);
    expect(why({ ...def([]), universe: { ...U, capMin: 5 } })).toEqual(['INVALID_INPUT', 'definition.universe.capMin']);
    expect(why(def([{ ...c({ kind: 'value', op: 'gt', value: 1, metric: ind('I13', 'rsi') }), weight: 2 }]))).toEqual(['INVALID_INPUT', 'definition.conditions[0].weight']);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: { ...ind('I13', 'rsi'), offset: 1 } })]))).toEqual(['INVALID_INPUT', 'definition.conditions[0].test.metric.offset']);
    expect(why(def([c({ kind: 'value', op: 'gt', value: 1, metric: { kind: 'formula', expr: 'c' } })]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.kind']);
  });
  it('condition ids are 1-6 of 0-9a-z and unique; enabled is a boolean; a label is at most 120 characters', () => {
    const t = { kind: 'value', op: 'gt', value: 1, metric: ind('I13', 'rsi') };
    expect(why(def([c(t, 'A')]))).toEqual(['INVALID_CONDITION', 'definition.conditions[0].id']);
    expect(why(def([c(t, 'a'), c(t, 'a')]))).toEqual(['INVALID_CONDITION', 'definition.conditions[1].id']);
    expect(why(def([{ id: 'a', enabled: 'yes', test: t }]))).toEqual(['INVALID_INPUT', 'definition.conditions[0].enabled']);
    expect(why(def([{ id: 'a', enabled: true, label: 'x'.repeat(121), test: t }]))).toEqual(['INVALID_INPUT', 'definition.conditions[0].label']);
  });
  it('logic all, any or at_least; at_least is a whole number of at least 1 with at_least and absent otherwise', () => {
    expect(why({ ...def([]), logic: 'most' })).toEqual(['INVALID_CONDITION', 'definition.logic']);
    expect(why({ ...def([]), logic: 'at_least' })).toEqual(['INVALID_CONDITION', 'definition.at_least']);
    expect(why({ ...def([]), logic: 'at_least', at_least: 0 })).toEqual(['INVALID_CONDITION', 'definition.at_least']);
    expect(why({ ...def([]), logic: 'all', at_least: 2 })).toEqual(['INVALID_CONDITION', 'definition.at_least']);
    expect(validateDefinition({ ...def([]), logic: 'at_least', at_least: 5 }, CTX).at_least).toBe(5);       // above the active count: all
  });
  it('max_conditions counts enabled conditions; max_metric_filters counts filters; both are LIMIT_EXCEEDED with the numbers', () => {
    const t = { kind: 'value', op: 'gt', value: 1, metric: ind('I13', 'rsi') };
    const many = (n: number, off = 0) => Array.from({ length: n }, (_, i) => c(t, i.toString(36), i >= n - off ? false : true));
    const e = refusal(() => validateDefinition(def(many(21)), CTX));
    expect([e.code, e.field, e.details]).toEqual(['LIMIT_EXCEEDED', 'definition.conditions', { limit: 'max_conditions', allowed: 20, needed: 21 }]);
    expect(validateDefinition(def(many(21, 1)), CTX).conditions.length).toBe(21);                              // one switched off
    const f = refusal(() => validateDefinition({ ...def([]), universe: { ...U, metric_filters: Array(9).fill(t) } }, CTX));
    expect([f.code, f.details]).toEqual(['LIMIT_EXCEEDED', { limit: 'max_metric_filters', allowed: 8, needed: 9 }]);
    expect(why({ ...def([]), universe: { ...U, metric_filters: [{ kind: 'state', pattern: { kind: 'pattern', type: 'breakout' } }] } })).toEqual(['INVALID_CONDITION', 'definition.universe.metric_filters[0].kind']);
  });
});

describe('the universe', () => {
  it('refuses an unknown sector, industry or ticker by name with the allowed values; "Undefined" is not a value (P15)', () => {
    const e = refusal(() => validateUniverse({ ...U, sectors_in: ['Financials', 'Undefined'] }, 'definition.universe', CTX));
    expect([e.code, e.field, (e.details as any).allowed]).toEqual(['INVALID_CONDITION', 'definition.universe.sectors_in[1]', ['Financials', 'Industrials', 'Energy']]);
    expect(refusal(() => validateUniverse({ ...U, industries_out: ['Bank'] }, 'u', CTX)).field).toBe('u.industries_out[0]');
    const t = refusal(() => validateUniverse({ ...U, tickers: ['BBCA', 'GOTO'] }, 'u', CTX));
    expect([t.code, t.field, t.message]).toEqual(['INVALID_CONDITION', 'u.tickers[1]', expect.stringContaining('"GOTO"')]);
    expect(refusal(() => validateUniverse({ ...U, tickers: ['BBCA', 'BBCA'] }, 'u', CTX)).field).toBe('u.tickers[1]');
  });
  it('bounds are numbers of at least 0 (history: a whole number of at least 1) or null; never adjusted', () => {
    expect(refusal(() => validateUniverse({ ...U, price_min: -1 }, 'u', CTX)).code).toBe('PARAM_OUT_OF_RANGE');
    expect(refusal(() => validateUniverse({ ...U, min_history_bars: 1.5 }, 'u', CTX)).code).toBe('PARAM_OUT_OF_RANGE');
    expect(refusal(() => validateUniverse({ ...U, adv20_min_idr: '1e9' }, 'u', CTX)).code).toBe('INVALID_INPUT');
    expect(validateUniverse({ ...U, price_min: 0, min_history_bars: 1 }, 'u', CTX)).toMatchObject({ price_min: 0, min_history_bars: 1 });
  });
  it('security types are ["stock"] only; the P4 chips are booleans, true when absent', () => {
    expect(refusal(() => validateUniverse({ ...U, security_types: ['etf'] }, 'u', CTX)).field).toBe('u.security_types');
    expect(refusal(() => validateUniverse({ ...U, traded_on_eval_date: 'yes' }, 'u', CTX)).code).toBe('INVALID_INPUT');
    expect(validateUniverse({ security_types: ['stock'] }, 'u', CTX)).toMatchObject({ traded_on_eval_date: true, exclude_price_breaks: true, include_unclassified: false });
    expect(validateUniverse({ security_types: ['stock'], exclude_price_breaks: false }, 'u', CTX).exclude_price_breaks).toBe(false);
  });
  it('a metric filter is a value test, normalized like a condition', () => {
    const u = validateUniverse({ ...U, metric_filters: [{ kind: 'value', op: 'gt', value: 1e10, metric: { kind: 'universe', attr: 'adv20_idr' } }] }, 'u', CTX);
    expect(u.metric_filters).toEqual([{ kind: 'value', metric: { kind: 'universe', attr: 'adv20_idr' }, op: 'gt', value: 1e10 }]);
    const e = refusal(() => validateTest({ kind: 'value', op: 'gt', value: 1, metric: { kind: 'universe', attr: 'nope' } }, 't', CTX));
    expect([e.code, e.field, (e.details as any).allowed]).toEqual(['INVALID_CONDITION', 't.metric.attr', expect.arrayContaining(['last', 'adv20_idr'])]);
  });
});

describe('a switched-off condition normalizes as an enabled one', () => {
  it('the same test gives the same normalized test whether the condition is on or off (only `enabled` differs)', () => {
    for (const p of PRESETS.presets.filter(x => x.category === 'Technical' && x.id !== 'ichi')) for (const cd of p.definition.conditions) {
      const on = validateTest(cd.test, 't', CTX, true), off = validateTest(cd.test, 't', CTX, false);
      expect([p.id, cd.id, off]).toEqual([p.id, cd.id, on]);
    }
  });
});
