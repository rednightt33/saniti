/* The non-indicator metric catalog and the presets (report TARGET ARCHITECTURE 6.12; TEST PLAN 10b.10 "Derived
   availability", 10b.5 "Board, index, market cap, free float, notation"): screener-metrics.json keeps its rules and
   lists exactly what transforms.ts computes; the comparison lag of the rolling windows is the generator's lag probe
   re-derived on its fixture (a hand edit fails here); availability is derived from the published index (removing a
   file turns its metrics REQUIRES_DATA, technical metrics stay); bank metrics apply to banks only; every one of the 32
   fundamental metrics is there, unavailable with a reason; presets carry no stored availability. */
import { describe, expect, it } from 'vitest';
import * as G from '../../scripts/build-screener-registry.mjs';
import { METRICS_CATALOG, PRESETS, appliesTo, catalogProblems, resolveCatalogParams, transformSpec } from '../../src/core/catalog.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { IMPLEMENTED_PATTERNS, IMPLEMENTED_TRANSFORMS, rollingMax, rollingMin } from '../../src/core/transforms.ts';
import { availabilityMap, availabilityOf, presetAvailability } from '../../src/core/validate.ts';

const B = G.fixture();

describe('screener-metrics.json', () => {
  it('keeps its rules and lists exactly the transforms and patterns transforms.ts computes', () => {
    expect(catalogProblems({ transforms: IMPLEMENTED_TRANSFORMS, patterns: IMPLEMENTED_PATTERNS })).toEqual([]);
    expect(catalogProblems({ transforms: IMPLEMENTED_TRANSFORMS.slice(1), patterns: IMPLEMENTED_PATTERNS })[0]).toMatch(/pct_distance is in the catalog but transforms.ts does not compute it/);
    expect(METRICS_CATALOG.periods).toEqual({ '1M': 21, '3M': 63, '6M': 126, '1Y': 252 });          // P23 a
  });
  it('the comparison lag of rolling_max / rolling_min over each bar field is the lag probe\'s answer on the generator fixture', () => {
    for (const fn of ['rolling_max', 'rolling_min'] as const) {
      const spec = transformSpec(fn, 'f'), f = fn === 'rolling_max' ? rollingMax : rollingMin;
      const fields = { open: B.O, high: B.H, low: B.L, close: B.C, volume: B.V } as Record<string, number[]>;
      for (const [field, xs] of Object.entries(fields)) {
        const against = field === 'volume' ? B.V : B.C;
        expect([fn, field, spec.compare_lag![field as 'open']]).toEqual([fn, field, G.compareLag(against, f(xs, 20))]);
      }
    }
  });
  it('holds the 32 fundamental metrics of APPENDIX C.3, each unavailable with a reason; bank-only ones apply to banks only', () => {
    const fund = METRICS_CATALOG.metrics.filter(m => m.group === 'Fundamental');
    expect(fund.length).toBe(32);
    const a = availabilityMap({});
    for (const m of fund) {
      expect([m.id, m.kind, a.get(m.id)!.availability]).toEqual([m.id, 'universe', 'REQUIRES_DATA']);
      expect(a.get(m.id)!.reason).toMatch(/needs the published file/);
    }
    const banks = fund.filter(m => m.applies_to === 'Industry = Banks').map(m => m.id);
    expect(banks).toEqual(['nim', 'npl', 'car', 'casa', 'ldr']);
    const bank = { sector: 'Financials', industry: 'Banks' }, miner = { sector: 'Energy', industry: 'Coal' }, unclassified = { sector: null, industry: null };
    expect([appliesTo('Industry = Banks', bank), appliesTo('Industry = Banks', miner), appliesTo('Industry = Banks', unclassified)]).toEqual([true, false, false]);
    expect([appliesTo('Industry != Banks', bank), appliesTo('Sector != Financials', miner), appliesTo('Sector != Financials', unclassified), appliesTo(null, bank)]).toEqual([false, true, true, true]);
  });
  it('derives availability from the published index: flow needs its files, technical metrics need none, a decision wins', () => {
    const flowIds = METRICS_CATALOG.metrics.filter(m => m.kind === 'flow').map(m => m.id);
    expect(flowIds.length).toBe(20);
    const none = availabilityMap({});
    const decided = METRICS_CATALOG.metrics.filter(m => m.kind === 'flow' && !m.decision).map(m => m.fl).sort();
    expect(decided).toEqual(['FL01', 'FL02', 'FL04', 'FL06', 'FL07', 'FL08', 'FL09', 'FL10', 'FL12', 'FL16', 'FL18']);   // 16.11 D1: the first set
    for (const id of flowIds) expect(none.get(id)!.availability).not.toBe('AVAILABLE');
    for (const id of ['hi52', 'rs', 'return_rank', 'breakout', 'squeeze', 'last', 'adv20_idr']) expect(none.get(id)!.availability).toBe('AVAILABLE');
    const withFlow = availabilityMap({ broker_window: { columns: ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'buy_freq', 'sell_freq'] }, flow_series: {} });
    for (const fl of decided) expect(withFlow.get(METRICS_CATALOG.metrics.find(m => m.fl === fl)!.id)!.availability).toBe('AVAILABLE');
    expect(withFlow.get('fsurprise')!.availability).toBe('REQUIRES_DECISION');                                 // a later-list metric
    const noFreq = availabilityOf(METRICS_CATALOG.metrics.find(m => m.id === 'freq')!, { broker_window: { columns: ['d', 'b'] } });
    expect(noFreq).toEqual({ availability: 'REQUIRES_DATA', reason: expect.stringMatching(/lacks the columns i, m, bv, sv, bl, sl, buy_freq, sell_freq/) });
    expect(availabilityOf(METRICS_CATALOG.metrics.find(m => m.id === 'index_membership')!, {}).availability).toBe('REQUIRES_DATA');
  });
  it('checks catalog parameters as registry parameters are checked: defaults filled, nothing adjusted, the field named', () => {
    const spec = transformSpec('ma', 'f').args;
    expect(resolveCatalogParams(spec, undefined, 'a')).toEqual({ ma: 'EMA', length: 20 });
    expect(resolveCatalogParams(spec, { ma: 'SMA' }, 'a')).toEqual({ ma: 'SMA', length: 20 });
    const refused = (given: unknown) => { try { resolveCatalogParams(spec, given, 'a'); return null } catch (e) { return [(e as ScreenerError).code, (e as ScreenerError).field] } };
    expect(refused({ ma: 'WMA' })).toEqual(['INVALID_CONDITION', 'a.ma']);
    expect(refused({ length: 0 })).toEqual(['PARAM_OUT_OF_RANGE', 'a.length']);
    expect(refused({ length: 20.5 })).toEqual(['PARAM_OUT_OF_RANGE', 'a.length']);
    expect(refused({ length: '20' })).toEqual(['INVALID_CONDITION', 'a.length']);
    expect(refused({ window: 20 })).toEqual(['INVALID_CONDITION', 'a.window']);
  });
});

describe('presets.json', () => {
  it('holds the 26 presets of APPENDIX A.2; the technical ones are available on a Phase 1 publication, the others name their legs', () => {
    expect(PRESETS.presets.length).toBe(26);
    const a = availabilityMap({});
    const status = Object.fromEntries(PRESETS.presets.map(p => [p.id, presetAvailability(p, a)]));
    for (const id of ['brk52', 'oversold', 'golden', 'macddiv', 'rebound', 'squeeze', 'stflip', 'minervini']) expect([id, status[id].availability]).toEqual([id, 'AVAILABLE']);
    expect(status.ichi).toEqual({ availability: 'REQUIRES_DECISION', reason: expect.stringMatching(/registry release \(P6/), unavailable_legs: ['a', 'b'] });
    expect([status.fstreak.availability, status.fstreak.unavailable_legs]).toEqual(['REQUIRES_DATA', ['a', 'b']]);
    expect([status.qflow.availability, status.qflow.unavailable_legs]).toEqual(['REQUIRES_DATA', ['a', 'b', 'c']]);      // the MA50 leg is available
    expect([status.bavg.availability, status.bavg.unavailable_legs]).toEqual(['REQUIRES_DECISION', ['a', 'b']]);
    expect(status.magic.unavailable_legs).toEqual(['a', 'metric_filters[0]']);
    for (const p of PRESETS.presets) expect(Object.keys(p).sort()).toEqual(['category', 'definition', 'id', 'name', 'why']);
  });
});
