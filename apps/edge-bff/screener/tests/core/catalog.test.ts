/* The non-indicator metric catalog and the presets (report TARGET ARCHITECTURE 6.12; TEST PLAN 10b.10 "Derived
   availability", 10b.5 "Board, index, market cap, free float, notation"): screener-metrics.json keeps its rules and
   lists exactly what transforms.ts computes; the comparison lag of the rolling windows is the generator's lag probe
   re-derived on its fixture (a hand edit fails here); availability is derived from the published index (removing a
   file turns its metrics REQUIRES_DATA, technical metrics stay; a file counts only when the reader reads it); bank
   metrics apply to banks only; every fundamental metric of the prototype's catalogue (APPENDIX C.3) is there,
   unavailable with a reason; presets carry no stored availability. */
import { describe, expect, it } from 'vitest';
import prototypeText from '../../../../../verification/screener/evidence/html_ui/catalog.json?raw';
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
  it('holds every fundamental metric of the prototype\'s catalogue (APPENDIX C.3), each unavailable with a reason; bank-only ones apply to banks only', () => {
    const fund = METRICS_CATALOG.metrics.filter(m => m.group === 'Fundamental');
    // derived from the prototype's catalogue (verification/screener/evidence/html_ui/catalog.json byGroup), never a count
    // kept here: a new fundamental beyond it is allowed, a missing one fails
    const prototype = (JSON.parse(prototypeText as unknown as string).byGroup as Record<string, string[]>).Fundamental;
    expect(prototype.length).toBeGreaterThan(0);
    expect(prototype.filter(id => !fund.some(m => m.id === id))).toEqual([]);
    // the import check holds the rule of a fundamental, not their number: one more passes, one of another kind fails
    const extra = { ...fund[0], id: 'evSales' }, pe = fund.find(m => m.id === 'pe')!;
    try {
      METRICS_CATALOG.metrics.push(extra);
      expect(catalogProblems()).toEqual([]);
      pe.kind = 'xsection';
      expect(catalogProblems()).toEqual(['metric pe: a fundamental is kind universe and requires its file']);
    } finally { METRICS_CATALOG.metrics.splice(METRICS_CATALOG.metrics.indexOf(extra), 1); pe.kind = 'universe' }
    expect(catalogProblems()).toEqual([]);
    const a = availabilityMap({});
    for (const m of fund) {
      expect([m.id, m.kind, a.get(m.id)!.availability]).toEqual([m.id, 'universe', 'REQUIRES_DATA']);
      expect(a.get(m.id)!.reason).toMatch(/It needs data that this publication does not carry\.$/);
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
    // i, m, bv, sv, bl, sl, buy_freq and sell_freq are missing: counted in words, never named (the page shows the reason)
    expect(noFreq).toEqual({ availability: 'REQUIRES_DATA', reason: expect.stringMatching(/carries only part of its data: 8 of the 10 columns it needs are missing\.$/) });
    // a file without any of the columns carries none of the data, never "part of it" ("1 of the 1 columns"); one
    // missing column is singular; a file that lists them all is available
    const pe = METRICS_CATALOG.metrics.find(m => m.id === 'pe')!, fnet = METRICS_CATALOG.metrics.find(m => m.id === 'fnet')!;
    expect(availabilityOf(pe, { [pe.requires!.file]: { columns: ['d'] } }).reason).toMatch(/\. It needs data that this publication does not carry\.$/);
    expect(availabilityOf(fnet, { [fnet.requires!.file]: { columns: ['x'] } }).reason).toMatch(/\. It needs data that this publication does not carry\.$/);
    expect(availabilityOf(fnet, { [fnet.requires!.file]: { columns: [fnet.requires!.columns[0]] } }).reason).toMatch(/carries only part of its data: 1 of the 2 columns it needs is missing\.$/);
    expect(availabilityOf(fnet, { [fnet.requires!.file]: { columns: [...fnet.requires!.columns] } })).toEqual({ availability: 'AVAILABLE', reason: null });
    expect(availabilityOf(METRICS_CATALOG.metrics.find(m => m.id === 'index_membership')!, {}).availability).toBe('REQUIRES_DATA');
  });
  it('counts a published file only when the reader reads it: indexed but not read is REQUIRES_DATA in plain words, a missing file keeps its reason, a decision still wins (ERRORS M299)', () => {
    const files = [...new Set(METRICS_CATALOG.metrics.flatMap(m => m.requires ? [m.requires.file] : []))];
    const all = Object.fromEntries(files.map(f => [f, {}]));
    const readsNone = availabilityMap(all, METRICS_CATALOG, new Set()), readsAll = availabilityMap(all, METRICS_CATALOG, new Set(files));
    for (const m of METRICS_CATALOG.metrics) {
      if (m.decision) { expect([m.id, readsNone.get(m.id)!.availability]).toEqual([m.id, 'REQUIRES_DECISION']); continue }
      if (!m.requires) { expect([m.id, readsNone.get(m.id)!.availability]).toEqual([m.id, 'AVAILABLE']); continue }
      expect([m.id, readsNone.get(m.id)]).toEqual([m.id, { availability: 'REQUIRES_DATA', reason: `${m.unavailable_reason} It needs data that the Screener does not read yet.` }]);
      expect([m.id, readsAll.get(m.id)!.availability]).toEqual([m.id, 'AVAILABLE']);
      // read but not published: what the publication lacks comes first; omitted reads (core tests) count every indexed file
      expect(availabilityOf(m, {}, new Set(files)).reason).toMatch(/It needs data that this publication does not carry\.$/);
      expect(availabilityOf(m, all).availability).toBe('AVAILABLE');
    }
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
    // the legs named as the page numbers its cards, one sentence per reason
    expect(status.ichi).toEqual({ availability: 'REQUIRES_DECISION', unavailable_legs: ['a', 'b'],
      reason: 'Not available: condition 1 (Close above the Ichimoku cloud), condition 2 (Tenkan crosses above Kijun): Ichimoku is not among the 53 indicators yet: it comes with a later release of the indicator list.' });
    expect(status.magic.reason).toMatch(/^Not available: condition 1 \(Magic Formula rank\): No fundamental data source .* universe filter 1 \(Market cap\): Market cap waits /);
    expect(status.qflow.reason).toMatch(/^Not available: condition 1 \(ROE\), condition 2 \(Debt \/ equity\): No fundamental .* condition 3 \(Foreign net value\): Flow metrics /);
    expect([status.fstreak.availability, status.fstreak.unavailable_legs]).toEqual(['REQUIRES_DATA', ['a', 'b']]);
    expect([status.qflow.availability, status.qflow.unavailable_legs]).toEqual(['REQUIRES_DATA', ['a', 'b', 'c']]);      // the MA50 leg is available
    expect([status.bavg.availability, status.bavg.unavailable_legs]).toEqual(['REQUIRES_DECISION', ['a', 'b']]);
    expect(status.magic.unavailable_legs).toEqual(['a', 'metric_filters[0]']);
    for (const p of PRESETS.presets) expect(Object.keys(p).filter(k => k !== 'view').sort()).toEqual(['category', 'definition', 'id', 'name', 'why']);
  });
  it('carries the prototype\'s default sort of the eight presets that had one (page O2), as a sort the page offers', () => {
    const sorts = Object.fromEntries(PRESETS.presets.filter(p => p.view).map(p => [p.id, p.view!.sort]));
    expect(sorts).toEqual({
      bigacc: { key: 'c:a', dir: 'desc' }, fstreak: { key: 'c:a', dir: 'desc' }, freq: { key: 'c:a', dir: 'desc' }, follow: { key: 'c:a', dir: 'desc' },
      oversold: { key: 'c:b', dir: 'asc' }, piotroski: { key: 'c:a', dir: 'desc' }, magic: { key: 'c:a', dir: 'asc' }, dividend: { key: 'c:a', dir: 'desc' },
    });
    // oversold sorts by its RSI leg (the prototype's c1), the lowest RSI first
    const oversold = PRESETS.presets.find(p => p.id === 'oversold')!;
    expect((oversold.definition.conditions.find(c => c.id === 'b')!.test as { metric: { indicator: string } }).metric.indicator).toBe('I13');
    // a sort on a condition the preset does not have, or another direction, is refused at import
    const keep = oversold.view;
    try {
      oversold.view = { sort: { key: 'c:z', dir: 'asc' } };
      expect(catalogProblems().join()).toMatch(/preset oversold: view.sort must be \{key, dir\} with key one of match, sym, last, d1, adv, c:a, c:b/);
      oversold.view = { sort: { key: 'c:a', dir: 'up' as 'asc' } };
      expect(catalogProblems().join()).toMatch(/preset oversold: view.sort/);
    } finally { oversold.view = keep }
    expect(catalogProblems()).toEqual([]);
  });
});
