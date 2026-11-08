/* The 20 candlestick patterns in the Screener (EXEC-SCREENER-FLOW-CANDLES P6; verification/screener/P6_CANDLES.md
   sections 2 and 4): the catalog entries are generated from the Backtest core's candle registry (never typed), the
   Screener computes each with the core's own evaluator, validation refuses a parameter outside the core's range with
   the field and the range, and a screen tests a pattern on the evaluated bar (state) or within N sessions (event), and
   inside the operators as a 0/1 signal (ever, K of N, streak), each equal to the brute force over the core's signal. */
import { describe, expect, it } from 'vitest';
import { CANDLES, candleFormula, candleSignal } from '../../../backtest/src/core/candles.ts';
import type { Definition } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { CANDLE_GROUP, METRICS_CATALOG, catalogProblems } from '../../src/core/catalog.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { tickerCalc } from '../../src/core/metrics.ts';
import { SCREENER_REGISTRY } from '../../src/core/registry.ts';
import { runScreen } from '../../src/core/screen.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS, patternSignal, resolveSignal } from '../../src/core/transforms.ts';
import { validateDefinition, validateTest } from '../../src/core/validate.ts';
import { OPTS, memoryEnv, rowOf, synth, vctx } from './helpers.ts';

const refusal = (fn: () => unknown): ScreenerError => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e } throw new Error('expected a ScreenerError') };
const IDS = CANDLES.patterns.map(p => p.id);

describe('catalog: one pattern entry per pattern of the core candle registry', () => {
  it('generated, never typed: the core\'s names, parameters (with their ranges and meaning) and exact definition', () => {
    expect(SCREENER_REGISTRY.candles.map(c => c.id)).toEqual(IDS);
    for (const p of CANDLES.patterns) {
      const m = METRICS_CATALOG.metrics.find(x => x.id === p.id)!;
      expect([m.kind, m.group, m.label, m.tests, m.unit, m.requires, m.decision]).toEqual(['pattern', CANDLE_GROUP, p.name, ['state', 'event'], null, null, null]);
      expect(m.params.map(q => [q.key, q.type, q.default, q.min, q.max, q.options])).toEqual(p.params.map(q => [q.key, q.type, q.default, q.min, q.max, q.options]));
      expect(m.params.every(q => q.label && (q as unknown as { meaning: string }).meaning)).toBe(true);
      expect(m.formula).toBe(candleFormula(p.id));
      expect([m.interpretation, m.default_test]).toEqual([p.summary, { test: 'event', within: 3 }]);
      expect(m.misuse).toContain(p.misuse);
      expect(m.synonyms).toEqual(p.synonyms);
      expect(m.side).toBe(p.side);                                     // the side, as the registry states it (QA of unit C item 2)
      expect(IMPLEMENTED_PATTERNS).toContain(p.id);
    }
    expect(METRICS_CATALOG.metrics.filter(m => m.group === CANDLE_GROUP).length).toBe(20);
    expect(METRICS_CATALOG.metrics.filter(m => m.side !== undefined).map(m => m.id)).toEqual(IDS);   // no other entry has a side
    expect(catalogProblems({ transforms: IMPLEMENTED_TRANSFORMS, patterns: IMPLEMENTED_PATTERNS })).toEqual([]);
    // the search words the page matches: hammer, engulfing and doji find their patterns
    const find = (q: string) => METRICS_CATALOG.metrics.filter(m => m.group === CANDLE_GROUP && `${m.label} ${m.id} ${(m.synonyms || []).join(' ')}`.toLowerCase().includes(q)).map(m => m.id);
    expect(find('hammer')).toEqual(['hammer', 'inverted_hammer']);
    expect(find('engulfing')).toEqual(['bullish_engulfing', 'bearish_engulfing']);
    expect(find('doji')).toEqual(['dragonfly_doji', 'gravestone_doji']);
  });
});

/* ---- computed by the core ---------------------------------------------------------------------------------------- */

const IX = synth('IHSG', 3, 420, '2024-06-03'), E = IX.dates.at(-1)!;
const T = Array.from({ length: 16 }, (_, k) => synth(`C${String(k).padStart(2, '0')}`, 310 + k, 420, '2024-06-03'));
const rows = T.map(t => rowOf(t, E, { adv20_idr: 5e9, last: 1000 })), CTX = vctx(T.map(t => t.ticker));
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
/** loose parameters so that the synthetic stocks show the rarer patterns too */
const loose = (id: string) => {
  const p = CANDLES.patterns.find(x => x.id === id)!, keys = new Set(p.params.map(q => q.key));
  return { min_range_ticks: 1, trend_length: 2, ...(keys.has('body_avg_length') ? { body_avg_length: 3, long_body: 0 } : {}) };
};

describe('the Screener computes each pattern with the core\'s evaluator', () => {
  it('patternSignal is the core\'s candleSignal (bar 0 never), at the defaults and at other parameters', () => {
    let ones = 0;
    for (const t of T.slice(0, 6)) for (const id of IDS) for (const params of [undefined, loose(id)]) {
      const ref = { kind: 'pattern' as const, type: id, ...(params ? { params } : {}) };
      const s = Array.from(patternSignal(tickerCalc(t), ref, 'p', OPTS)), core = Array.from(candleSignal(t.bars, id, params));
      expect([id, params, s]).toEqual([id, params, core]);
      ones += s.reduce((a, b) => a + b, 0);
    }
    expect(ones).toBeGreaterThan(100);
    // the window a remark reads is the core's lookback; every bar field is an input (the volume decides a day without trades)
    const r = resolveSignal({ kind: 'pattern', type: 'morning_star' }, 'p', OPTS);
    expect([r.window, r.inputs, r.historyClass]).toEqual([13, ['O', 'H', 'L', 'C', 'V'], 'window']);
  });
});

describe('validation: the core\'s ranges, refused with the field and the range', () => {
  const at = (pattern: unknown) => ({ kind: 'event', signal: { pattern }, within: 3 });
  it('accepts a pattern on the bar, within N sessions, and inside the operators', () => {
    expect(() => validateTest({ kind: 'state', pattern: { kind: 'pattern', type: 'hammer' } }, 'c', CTX)).not.toThrow();
    expect(() => validateTest(at({ kind: 'pattern', type: 'morning_star', params: { star_overlap_pct: -5, penetration_pct: 30 } }), 'c', CTX)).not.toThrow();
    expect(() => validateTest({ kind: 'window', mode: 'at_least', length: 20, count: 2, test: { kind: 'state', pattern: { kind: 'pattern', type: 'tweezer_bottom' } } }, 'c', CTX)).not.toThrow();
  });
  it('refuses a value outside the range, an option not offered, an unknown parameter and a value test of a pattern', () => {
    let e = refusal(() => validateTest(at({ kind: 'pattern', type: 'hammer', params: { body_max_pct: 150 } }), 'c', CTX));
    expect([e.code, e.field]).toEqual(['PARAM_OUT_OF_RANGE', 'c.signal.pattern.params.body_max_pct']);
    expect(e.message).toMatch(/at least 0 and at most 100/);
    e = refusal(() => validateTest(at({ kind: 'pattern', type: 'hammer', params: { trend: 'none' } }), 'c', CTX));
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'c.signal.pattern.params.trend']);
    expect(e.message).toMatch(/must be one of average, change/);
    e = refusal(() => validateTest(at({ kind: 'pattern', type: 'doji' }), 'c', CTX));
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'c.signal.pattern.type']);
    expect(e.message).toMatch(/dragonfly_doji/);
    e = refusal(() => validateTest(at({ kind: 'pattern', type: 'bullish_engulfing', params: { penetration_pct: 50 } }), 'c', CTX));
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'c.signal.pattern.params.penetration_pct']);
    e = refusal(() => validateTest({ kind: 'value', metric: { kind: 'pattern', type: 'hammer' }, op: 'gt', value: 0 }, 'c', CTX));
    expect(e.message).toMatch(/a pattern is a signal, not a value/);
  });
});

describe('a screen tests a pattern on the bar, within N sessions, and inside the operators, as the core\'s signal says', () => {
  const sig = (id: string, t: (typeof T)[number], params?: Record<string, unknown>) => Array.from(candleSignal(t.bars, id, params));
  const screen = (test: unknown) => runScreen(validateDefinition({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] }, CTX), memoryEnv(T, IX, rows, E)).rows.map(r => r.ticker).sort();
  it('state (on the evaluated bar) and event within N sessions', () => {
    let matched = 0;
    for (const id of IDS) {
      const p = { kind: 'pattern', type: id, params: loose(id) }, at = T[0].dates.length - 1;
      const onBar = T.filter(t => sig(id, t, p.params)[at] === 1).map(t => t.ticker).sort();
      expect([id, 'state', screen({ kind: 'state', pattern: p })]).toEqual([id, 'state', onBar]);
      for (const W of [1, 5, 30]) {
        const want = T.filter(t => sig(id, t, p.params).slice(at - W + 1, at + 1).includes(1)).map(t => t.ticker).sort();
        expect([id, W, screen({ kind: 'event', signal: { pattern: p }, within: W })]).toEqual([id, W, want]);
        matched += want.length;
      }
    }
    expect(matched).toBeGreaterThan(40);
  });
  it('the operators on a pattern as a 0/1 signal: ever in N, K of N, N in a row', () => {
    let matched = 0;
    for (const id of ['hammer', 'bullish_engulfing', 'tweezer_top', 'bearish_marubozu', 'morning_star']) {
      const p = { kind: 'pattern', type: id, params: loose(id) }, at = T[0].dates.length - 1, inner = { kind: 'event', signal: { pattern: p }, within: 1 };
      for (const [mode, length, count] of [['ever', 15, undefined], ['at_least', 40, 3], ['streak', 2, undefined]] as const) {
        const want = T.filter(t => {
          const w = sig(id, t, p.params).slice(at - length + 1, at + 1), n = w.reduce((a, b) => a + b, 0);
          return mode === 'ever' ? n >= 1 : mode === 'at_least' ? n >= (count as number) : w.every(x => x === 1);
        }).map(t => t.ticker).sort();
        const got = screen({ kind: 'window', mode, length, ...(count ? { count } : {}), test: inner });
        expect([id, mode, got]).toEqual([id, mode, want]);
        matched += want.length;
      }
    }
    expect(matched).toBeGreaterThan(10);
  });
});
