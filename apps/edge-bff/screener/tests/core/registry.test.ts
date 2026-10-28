/* The Screener's indicator contract (report TARGET ARCHITECTURE 6.8; TEST PLAN 10b.10 "Contract drift"): the
   generated screener-registry.json is current (the generator's --check re-derives every probe field), covers the 53
   base indicators and their 76 outputs, the overlay keeps its rules, the probes give the documented answers on the
   synthetic series (cases where a rule applies, and one where it must not), and registry.ts refuses and accepts what
   the narrowing says (each refusal naming the field and the fix). */
import { describe, expect, it } from 'vitest';
import overlayDoc from '../../src/core/screener-overlay.json';
import baseDoc from '../../../backtest/src/core/backtest-registry.json';
import engineSource from '../../../../../features/feature04/engine.py?raw';
import schemaDoc from '../../../../../DATABASE_SCHEMA.md?raw';
import { F, DEFAULTS } from '../../../terminal/src/calc/indicators.ts';
import { BY_ID, REGISTRY_VERSION } from '../../../backtest/src/core/registry.ts';
import * as G from '../../scripts/build-screener-registry.mjs';      // plain JavaScript: typed any
import {
  INDICATORS, SBY_ID, SCREENER_REGISTRY, SCREENER_REGISTRY_VERSION, capOf, capProblems, catalogIndicators, defaultParams,
  isDefaultParams, maxOf, registryProblems, resolveScreenerParams, screenerIndicator, screenerOutput,
} from '../../src/core/registry.ts';
import { ScreenerError } from '../../src/core/errors.ts';

const OPTS = { capBudgetMs: 2000 };
const refusal = (fn: () => unknown): ScreenerError => {
  try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e }
  throw new Error('expected a ScreenerError');
};

describe('generated file', () => {
  // the generator's --check itself runs in registry-check.test.mjs (it needs node:child_process)
  it('holds every one of the 53 base indicators and 76 outputs, from the running base registry', () => {
    expect(INDICATORS.length).toBe(53);
    expect(Object.keys(SBY_ID).sort()).toEqual(Object.keys(BY_ID).sort());
    expect(INDICATORS.reduce((n, r) => n + r.outputs.length, 0)).toBe(76);
    for (const r of INDICATORS) expect(r.outputs.map(o => o.key)).toEqual(BY_ID[r.id].outputs);
    expect(SCREENER_REGISTRY.registry_version).toBe(REGISTRY_VERSION);
    expect(registryProblems()).toEqual([]);
    expect(SCREENER_REGISTRY_VERSION).toMatch(/^[0-9a-f]{16}$/);
    for (const r of INDICATORS) expect(r.formula_version).toBe(REGISTRY_VERSION);
  });

  it('records the hash of every source it was built from', () => {
    const roles = SCREENER_REGISTRY.sources.map(s => s.role).sort();
    expect(roles).toEqual(['base', 'calc', 'generator', 'oracle', 'overlay', 'terminal']);
    for (const s of SCREENER_REGISTRY.sources) expect(s.sha256).toMatch(/^[0-9a-f]{64}$/);
  });

  it('only narrows the base: same keys, types, defaults, min and max; base integers stay integers', () => {
    for (const r of INDICATORS) for (const p of r.params) {
      const b = BY_ID[r.id].params.find(x => x.key === p.key)!;
      expect([p.type, p.default, p.min, p.max]).toEqual([b.type, b.default, b.min, b.max]);
      if (b.type === 'integer') expect(p.integer).toBe(true);
      if (p.exclusive_min || (p.integer && b.type !== 'integer')) expect(p.narrowing.length).toBeGreaterThan(0);
    }
  });
});

describe('overlay', () => {
  const overlay = structuredClone(overlayDoc) as any, base = baseDoc as any;
  it('has one entry per base id and vice versa, and every entry keeps its rules', () => {
    expect(Object.keys(overlay.indicators).sort()).toEqual(base.indicators.map((r: { id: string }) => r.id).sort());
    expect(G.overlayProblems(overlay, base)).toEqual([]);
  });
  it('refuses an unknown form, an operator outside the form, a label for another operator and a missing entry', () => {
    const broken = structuredClone(overlay);
    broken.indicators.I13.outputs.rsi.tests[0] = { form: 'value_magic', ops: ['gt'] };
    broken.indicators.I01.outputs.sma.tests[1].ops = ['crosses_above'];
    broken.indicators.I06.outputs.macd.tests[2].labels = { lt: 'below' };
    delete broken.indicators.I53;
    const problems: string[] = G.overlayProblems(broken, base);
    expect(problems.some(p => p.includes('I13.rsi value_magic: not a test form'))).toBe(true);
    expect(problems.some(p => p.includes('I01.sma state_level: ops must be'))).toBe(true);
    expect(problems.some(p => p.includes('I06.macd state_output: label for lt'))).toBe(true);
    expect(problems.some(p => p.includes('I53 has no entry'))).toBe(true);
  });
  it('keeps the shapes of report 6.9.1', () => {
    const count: Record<string, number> = {};
    for (const r of INDICATORS) count[r.overlay.shape] = (count[r.overlay.shape] || 0) + 1;
    expect(count).toEqual({ line: 6, band: 4, dir: 2, osc: 25, pair: 8, adx: 1, vol: 2, cum: 5 });
  });
  it('offers no raw level test on a cumulative line, and says why', () => {
    for (const id of ['I40', 'I41', 'I44', 'I50', 'I51']) {
      const o = SBY_ID[id].outputs[0];
      expect(o.tests.map(t => t.form)).not.toContain('value');
      expect(o.disabled_tests[0].form).toBe('value');
      expect(o.disabled_tests[0].reason).toMatch(/depends on where its history starts/);
    }
  });
});

describe('probes on the synthetic series (report 6.8)', () => {
  const B = G.fixture();
  const run = (key: string, over: Record<string, unknown> = {}) => (b = B, more: Record<string, unknown> = {}) => F[key](b, { ...DEFAULTS[key], ...over, ...more });

  it('lag: Donchian upper and lower read the previous bar; Bollinger and Keltner upper do not', () => {
    const d = F.donchian(B, {}), bb = F.bollinger(B, {}), kc = F.keltner(B, {});
    expect(G.compareLag(B.C, d.upper)).toEqual({ gt: 1, lt: 0 });
    expect(G.compareLag(B.C, d.lower)).toEqual({ gt: 0, lt: 1 });
    expect(G.compareLag(B.C, d.basis)).toEqual({ gt: 0, lt: 0 });
    expect(G.compareLag(B.C, bb.upper)).toEqual({ gt: 0, lt: 0 });
    expect(G.compareLag(B.C, kc.upper)).toEqual({ gt: 0, lt: 0 });
    expect(SBY_ID.I10.outputs.find(o => o.key === 'upper')!.price_compare_lag).toEqual({ gt: 1, lt: 0 });
    expect(SBY_ID.I27.outputs.find(o => o.key === 'upper')!.price_compare_lag).toEqual({ gt: 0, lt: 0 });
  });

  it('cut: SMA and Donchian are window, EMA, RSI and ATR recursive, OBV, A/D and NVI cumulative, VWAP calendar', () => {
    const cut = (b: typeof B) => ({ O: b.O.slice(1000), H: b.H.slice(1000), L: b.L.slice(1000), C: b.C.slice(1000), V: b.V.slice(1000), T: b.T.slice(1000) });
    const cls = (key: string, out: string) => G.historyClass(F[key](B, {})[out], F[key](cut(B), {})[out], 1000, false);
    expect(cls('sma', 'sma')).toBe('window');
    expect(cls('donchian', 'upper')).toBe('window');
    expect(cls('ema', 'ema')).toBe('recursive');
    expect(cls('rsi', 'rsi')).toBe('recursive');
    expect(cls('atr', 'atr')).toBe('recursive');
    expect(cls('obv', 'obv')).toBe('cumulative');
    expect(cls('adl', 'adl')).toBe('cumulative');
    expect(cls('nvi', 'nvi')).toBe('cumulative');
    expect(SBY_ID.I43.outputs.every(o => o.history_class === 'calendar')).toBe(true);
  });

  it('scaling: price levels, price changes, volume levels and quantities, products and dimensionless outputs', () => {
    const u = (key: string) => G.unitProbe(run(key), B);
    expect(u('sma').sma).toEqual({ unit: 'price', comparable_with: 'close' });
    expect(u('bollinger').upper).toEqual({ unit: 'price', comparable_with: 'close' });
    expect(u('atr').atr).toEqual({ unit: 'price_change', comparable_with: null });
    expect(u('macd').macd).toEqual({ unit: 'price_change', comparable_with: null });
    expect(u('rsi').rsi).toEqual({ unit: 'dimensionless', comparable_with: null });
    expect(u('supertrend').direction).toEqual({ unit: 'dimensionless', comparable_with: null });
    expect(u('volume_sma').volume_sma).toEqual({ unit: 'volume', comparable_with: 'volume' });
    expect(u('obv').obv).toEqual({ unit: 'volume', comparable_with: null });
    expect(u('force_index').force_index).toEqual({ unit: 'price_x_volume', comparable_with: null });
    expect(u('eom').eom.unit).toBe('other');
  });

  it('poison: inputs follow the chosen source; a source-free indicator keeps its own fields', () => {
    const at = (key: string, over: Record<string, unknown>, outs: string[]) => G.inputsProbe(run(key, over), B, outs);
    for (const key of ['bollinger_pctb', 'bollinger_width', 'stddev', 'hist_vol']) {
      const out = F[key](B, {}), o = Object.keys(out).find(k => !k.startsWith('_'))!;
      expect(at(key, { source: 'hl2' }, [o])[o]).toEqual(['H', 'L']);
      expect(at(key, {}, [o])[o]).toEqual(['C']);
    }
    expect(at('obv', {}, ['obv']).obv).toEqual(['C', 'V']);
    expect(at('bollinger', { basis_ma_type: 'VWMA' }, ['basis']).basis).toEqual(['C', 'V']);
    expect(SBY_ID.I27.outputs[0].inputs_by_source.basis_ma_type.VWMA).toEqual(['C', 'V']);
    expect(SBY_ID.I27.outputs[0].inputs_by_source.basis_ma_type.SMA).toEqual(['C']);
  });

  it('degeneracy: I19 constant 0, I50 initial_value 0 and I11 multiplier 0 are degenerate; I23 weight 0 and I09 factor 0 are not', () => {
    const outs = (key: string) => Object.keys(F[key](B, {})).filter(k => !k.startsWith('_'));
    const deg = (key: string, over: Record<string, unknown>, band = false) => G.degenerate(run(key, over)(), outs(key), band ? outs(key) : []);
    expect(deg('cci', { constant: 0 })).not.toBeNull();
    expect(deg('nvi', { initial_value: 0 })).not.toBeNull();
    expect(deg('keltner', { multiplier: 0 }, true)).toMatch(/equals/);
    expect(deg('ultimate_osc', { weight_fast: 0 })).toBeNull();
    expect(deg('supertrend', { factor: 0 })).toBeNull();                  // hence the overlay override (ERRORS M257)
    expect(deg('sma', { length: 20 })).toBeNull();
  });

  it('floor: annualization_periods is floored by F, Supertrend factor is not', () => {
    expect(G.floored(run('hist_vol'), B, 'annualization_periods', 252)).toBe(true);
    expect(G.floored(run('supertrend'), B, 'factor', 3)).toBe(false);
    expect(G.floored(run('sma'), B, 'length', 20)).toBe(true);         // def() floors every LENGTH_KEYS key
  });

  it('the generated fields carry those answers', () => {
    const p = (id: string, key: string) => SBY_ID[id].params.find(x => x.key === key)!;
    expect(p('I19', 'constant').exclusive_min).toBe(true);
    expect(p('I50', 'initial_value').exclusive_min).toBe(true);
    expect(p('I11', 'multiplier').exclusive_min).toBe(true);
    expect(p('I23', 'weight_fast').exclusive_min).toBe(false);
    expect(p('I09', 'factor').narrowing).toEqual([expect.objectContaining({ rule: 'exclusive_min', source: 'override' })]);
    expect(p('I33', 'annualization_periods').integer).toBe(true);
    expect(p('I33', 'annualization_periods').narrowing[0].source).toBe('floor_probe');
    expect(SBY_ID.I37.hidden_params.map(h => h.key)).toEqual(['reference_method', 'include_current_bar']);
    expect(SBY_ID.I34.hidden_params.map(h => h.key)).toEqual(['timeframe']);
    expect(SBY_ID.I37.params.map(x => x.key)).toEqual(['length']);
    expect(SBY_ID.I19.cost_class).toBe('O(N·n)');
    expect(SBY_ID.I01.cost_class).toBe('O(N)');
    expect(p('I32', 'length').cost_class).toBe('O(N·n)');            // the 'sample' method loops over its window
  });

  it('maps the parity oracle onto Feature 04 and Feature 01 columns that exist', () => {
    const engine = engineSource, schema = schemaDoc;
    const rows = INDICATORS.flatMap(r => r.oracle.map(o => ({ id: r.id, ...o })));
    expect(rows.length).toBe(25);
    for (const o of rows) for (const c of o.column ? [o.column] : o.columns!) {
      if (o.table === 'Feature_04_Technical_Indicator') expect(engine.includes(`'${c}'`), `${o.id} ${c}`).toBe(true);
      else expect(schema.includes(`\`${c}\``), `${o.id} ${c}`).toBe(true);
    }
    expect(SBY_ID.I01.oracle).toContainEqual(expect.objectContaining({ column: 'sma_50', params: { length: 50, source: 'close' } }));
    expect(SBY_ID.I33.oracle).toEqual([]);
    expect(SBY_ID.I33.oracle_note).toMatch(/No oracle/);
  });
});

describe('registry.ts parameters (report 6.8 narrowing, I7)', () => {
  const ind = (id: string) => screenerIndicator(id);
  it('refuses the narrowed minimums, a floored fraction and an unknown indicator, naming the field', () => {
    for (const [id, params, field] of [['I19', { constant: 0 }, 'p.constant'], ['I50', { initial_value: 0 }, 'p.initial_value'],
      ['I11', { multiplier: 0 }, 'p.multiplier'], ['I09', { factor: 0 }, 'p.factor']] as const) {
      const e = refusal(() => resolveScreenerParams(ind(id), params, 'p', OPTS));
      expect([e.code, e.field, e.status]).toEqual(['PARAM_OUT_OF_RANGE', field, 422]);
      expect(e.details).toMatchObject({ field, exclusive_min: true });
      expect(e.message).toMatch(/must be .*above 0/);
    }
    const f = refusal(() => resolveScreenerParams(ind('I33'), { annualization_periods: 252.5 }, 'p', OPTS));
    expect([f.code, f.details?.integer]).toEqual(['PARAM_OUT_OF_RANGE', true]);
    const u = refusal(() => screenerIndicator('I99', 'x.indicator'));
    expect([u.code, u.field, (u.details?.allowed as string[]).length]).toEqual(['UNKNOWN_INDICATOR', 'x.indicator', 53]);
  });
  it('accepts a valid minimum, the defaults and whole numbers', () => {
    expect(resolveScreenerParams(ind('I23'), { weight_fast: 0 }, 'p', OPTS).weight_fast).toBe(0);
    expect(resolveScreenerParams(ind('I01'), { length: 20 }, 'p', OPTS)).toEqual({ length: 20, source: 'close' });
    expect(resolveScreenerParams(ind('I33'), { annualization_periods: 252 }, 'p', OPTS).annualization_periods).toBe(252);
    for (const r of INDICATORS) expect(() => resolveScreenerParams(r, {}, 'p', OPTS)).not.toThrow();
  });
  it('maps the backtest core refusals: a hidden parameter, an option, a type, a range', () => {
    const h = refusal(() => resolveScreenerParams(ind('I37'), { include_current_bar: false }, 'p', OPTS));
    expect([h.code, h.field]).toEqual(['INVALID_CONDITION', 'p.include_current_bar']);
    expect(h.message).toMatch(/not read by the calculation module/);
    const o = refusal(() => resolveScreenerParams(ind('I27'), { basis_ma_type: 'HULL' }, 'p', OPTS));
    expect([o.code, o.details?.allowed]).toEqual(['INVALID_CONDITION', ['SMA', 'EMA', 'WMA', 'RMA', 'VWMA']]);
    const t = refusal(() => resolveScreenerParams(ind('I01'), { length: '20' }, 'p', OPTS));
    expect(t.code).toBe('INVALID_CONDITION');
    const w = refusal(() => resolveScreenerParams(ind('I01'), { length: 20.5 }, 'p', OPTS));
    expect([w.code, w.details?.integer]).toEqual(['PARAM_OUT_OF_RANGE', true]);
    const m = refusal(() => resolveScreenerParams(ind('I27'), { std_dev: 51 }, 'p', OPTS));
    expect([m.code, m.details?.max]).toEqual(['PARAM_OUT_OF_RANGE', 50]);
    const out = refusal(() => screenerOutput(ind('I06'), 'line', 'x.output'));
    expect([out.code, out.details?.allowed]).toEqual(['INVALID_CONDITION', ['macd', 'signal', 'histogram']]);
  });
  it('caps an O(N·n) length by the budget (provisional cost model, P5), and never an O(N) one', () => {
    const cci = ind('I19').params.find(p => p.key === 'length')!, sma = ind('I01').params.find(p => p.key === 'length')!;
    const cap = capOf(cci, OPTS.capBudgetMs)!;
    expect(cap).toBe(Math.floor(2000 * 1e6 / (SCREENER_REGISTRY.cost_model.ns_per_bar_length * SCREENER_REGISTRY.cost_model.reference_bars)));
    expect(capOf(sma, OPTS.capBudgetMs)).toBeUndefined();
    expect(maxOf(cci, OPTS.capBudgetMs)).toBe(cap);
    expect(() => resolveScreenerParams(ind('I19'), { length: cap }, 'p', OPTS)).not.toThrow();
    const e = refusal(() => resolveScreenerParams(ind('I19'), { length: cap + 1 }, 'p', OPTS));
    expect([e.code, e.details?.max]).toEqual(['PARAM_OUT_OF_RANGE', cap]);
    expect(capProblems(OPTS.capBudgetMs)).toEqual([]);
    expect(capProblems(1).length).toBeGreaterThan(0);                // a budget that would refuse the defaults
  });
  it('knows the defaults and serves the catalog view (report 8.4)', () => {
    expect(isDefaultParams(ind('I13'), defaultParams(ind('I13')))).toBe(true);
    expect(isDefaultParams(ind('I13'), resolveScreenerParams(ind('I13'), { length: 7 }, 'p', OPTS))).toBe(false);
    const cat = catalogIndicators(OPTS);
    expect(cat.length).toBe(53);
    const cci = cat.find(c => c.id === 'I19')!;
    expect(cci.params.find(p => p.key === 'length')).toMatchObject({ max: capOf(ind('I19').params[0], OPTS.capBudgetMs), integer: true });
    expect(cci.params.find(p => p.key === 'constant')).toMatchObject({ min: 0, exclusive_min: true });
    expect(cat.find(c => c.id === 'I37')!.params.map(p => p.key)).toEqual(['length']);
  });
});
