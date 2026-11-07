/* EXEC-SCREENER-FLOW-CANDLES P5a (verification/screener/P5_FLOW.md section 5): the Terminal's 48 flow indicators in the
   Screener, on the fixture of tests/core/flow-fixture.ts (several stocks over a 60-session broker window in P4's store
   layout, with a Nego-only day, a broker day without a price bar, a stock without broker data and price bars after the
   last broker day). Every value is compared, bit for bit, with flow.ts computeFlow called the Terminal's way: flow.ts
   flowRows on the same rows as objects with their names, the Terminal's context (close, volume, dates of the candles,
   the classification). The Screener's versions of P5b (the anchor N sessions back, FL23's series, FL34's guard, fnet)
   are compared with the Terminal's way in tests/core/flow-screener.test.ts. */
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults } from '../../../terminal/src/calc/flow.ts';
import REG from '../../../terminal/src/data/flowRegistry.json' with { type: 'json' };
import KINDS from '../../src/core/flow-kinds.json' with { type: 'json' };
import * as G from '../../scripts/build-screener-registry.mjs';
import type { Definition, Test } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { evaluationBar, round12 } from '../../src/core/evaluate.ts';
import { FLOWS, FLOW_BY_ID, brokerFlowRows, indicatorDepth, producedOutputs, resolveFlow, resolveFlowParams } from '../../src/core/flowmetrics.ts';
import type { BrokerRowsLike, FlowBindContext } from '../../src/core/flowmetrics.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import { runScreen } from '../../src/core/screen.ts';
import { percentileOwn } from '../../src/core/transforms.ts';
import { probeContext } from '../../src/core/flowprobe.ts';
import { availabilityMap, validateDefinition } from '../../src/core/validate.ts';
import { percentRank } from '../../src/core/xsection.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rowOf, synth, vctx } from './helpers.ts';

import { E, FIRST, FLOW_CTX, LAST, NEGO_DAY, PRICE_BARS, STOCKS, WINDOW, WITH_DATA, code, same, stock, storeOf, terminal } from './flow-fixture.ts';
import type { Row } from './flow-fixture.ts';

/* ---- the catalog ---------------------------------------------------------------------------------------------- */

describe('catalog (P5_FLOW.md section 2)', () => {
  it('holds one generated entry per FL of flowRegistry.json (its name, family, unit, tip, outputs and parameters), the Screener\'s versions as flow-kinds.json states them, then the Screener\'s own entries; FL31 and ksei_net REQUIRES_DATA', () => {
    const reg = (REG as any).indicators as any[], k = KINDS as any, key = (x: any) => typeof x === 'string' ? x : x.key;
    expect(FLOWS.map(f => f.id)).toEqual([...reg.map(r => r.id), 'fnet', 'ksei_net']);
    for (const r of reg) {
      const f = FLOW_BY_ID[r.id], sv = k.indicators[r.id].screener;
      expect([f.name, f.family, f.unit, f.tip]).toEqual([r.name, r.family, r.unit, r.tip]);
      // the registry's outputs and parameters as they are, except where the Screener's version replaces them (P5b)
      const outputs = sv?.replace_outputs ? Object.keys(k.indicators[r.id].outputs) : r.outputs;
      const keys = [...r.params.flatMap((p: any) => sv?.replace?.[p.key] ? sv.replace[p.key].map(key) : [p.key]), ...(sv?.add || []).map(key)];
      expect([r.id, f.outputs.map(o => o.key), f.default_output, f.params.map(p => p.key)]).toEqual([r.id, outputs, outputs[0], keys]);
      for (const p of f.params) {
        expect([r.id, p.key, p.condition]).toEqual([r.id, p.key, !['levels', 'button', 'fixed'].includes(p.kind) && !p.display_only]);
        if (!p.screener) expect([r.id, p]).toEqual([r.id, { ...r.params.find((q: any) => q.key === p.key), condition: p.condition, ...(p.display_only ? { display_only: true } : {}) }]);
      }
      // G1: the registry's default board, Regular
      const boards = f.params.find(p => p.key === 'boards');
      if (boards) expect(boards.default).toEqual(['Regular']);
    }
    expect(FLOWS.filter(f => f.version === 'screener').map(f => [f.id, f.compute])).toEqual([['FL18', 'anchored'], ['FL19', 'anchored'], ['FL20', 'anchored'], ['FL23', 'inventory'],
      ['FL44', 'anchored'], ['FL45', 'anchored'], ['fnet', 'foreign_net'], ['ksei_net', 'none']]);
    expect(FLOWS.filter(f => f.current_only).map(f => f.id)).toEqual(['FL34']);
    // maxima derived from the broker window: the anchor at most the window less its own candle, a lookback the window
    expect(FLOW_BY_ID.FL18.params.find(p => p.key === 'anchor_sessions')).toMatchObject({ kind: 'int', min: 1, max: 59, default: 20, condition: true, screener: true });
    expect([FLOW_BY_ID.FL23.params.find(p => p.key === 'lookback')!.max, FLOW_BY_ID.fnet.params.find(p => p.key === 'window')!.max]).toEqual([60, 60]);
    expect(G.flowEntries(REG, KINDS)).toEqual(FLOWS);                                       // the generator's own build
    const a = availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX);
    expect(FLOWS.filter(f => a.get(f.id)!.availability !== 'AVAILABLE').map(f => f.id)).toEqual(['FL31', 'ksei_net']);
  });
  it('every FL output has its kind in flow-kinds.json (the build fails without one), with the ADV floor flags of EXEC.md', () => {
    const k = KINDS as any;
    for (const f of FLOWS) for (const o of f.outputs) expect([f.id, o.key, o.kind === null || o.kind === undefined]).toEqual([f.id, o.key, false]);
    const missing = structuredClone(k); delete missing.indicators.FL24;
    expect(() => G.flowEntries(REG, missing)).toThrow(/FL24 Bandar Balance · % has no row/);
    const noOutput = structuredClone(k); delete noOutput.indicators.FL11.outputs.change;
    expect(() => G.flowEntries(REG, noOutput)).toThrow(/FL11 output change has no kind/);
    const badKind = structuredClone(k); badKind.indicators.FL26.outputs.value = 'Z';
    expect(() => G.flowEntries(REG, badKind)).toThrow(/kind Z is not one of/);
    expect(FLOWS.filter(f => f.adv_floor).map(f => f.id)).toEqual(['FL03', 'FL04', 'FL05', 'FL06', 'FL08', 'FL10', 'FL13', 'FL14', 'FL15', 'FL36', 'FL46']);
    expect(FLOWS.filter(f => f.requires).map(f => [f.id, f.requires])).toEqual([['FL31', 'insider'], ['ksei_net', 'ksei']]);
    expect(FLOWS.filter(f => f.needs_classification).map(f => f.id)).toEqual(['FL34']);
    // a kind that follows a parameter that follows another (FL23 value by series, then by unit) is checked at each level
    const nested = structuredClone(k); nested.indicators.FL23.outputs.value.cum.lot = 'Z';
    expect(() => G.flowEntries(REG, nested)).toThrow(/FL23\.value\.cum\.lot: kind Z is not one of/);
    const noOption = structuredClone(k); delete noOption.indicators.FL23.outputs.value.norm;
    expect(() => G.flowEntries(REG, noOption)).toThrow(/FL23\.value: no kind for series = norm/);
    // a screener parameter is checked as the registry's are: its default in its range, a replaced key the registry's
    const badDefault = structuredClone(k); badDefault.screener_params.anchor_sessions.default = 60;
    expect(() => G.flowEntries(REG, badDefault)).toThrow(/anchor_sessions: default 60 is outside its own range/);
    const badKey = structuredClone(k); badKey.indicators.FL18.screener.replace.when = [];
    expect(() => G.flowEntries(REG, badKey)).toThrow(/FL18\.screener\.replace: when is not a parameter of FL18/);
    const noData = structuredClone(k); delete noData.screener_entries.ksei_net.requires;
    expect(() => G.flowEntries(REG, noData)).toThrow(/ksei_net: an entry that is never computed names the data it requires/);
  });
});

/* ---- parity ---------------------------------------------------------------------------------------------------- */

describe('parity with the Terminal (P5_FLOW.md section 5)', () => {
  it('FlowRows from the store equal flow.ts flowRows on the same rows, field for field (a broker day without a price bar is not counted)', () => {
    for (const id of WITH_DATA) {
      const s = STOCKS[id], T = terminal(s), mine = brokerFlowRows(s.store, T.candles);
      expect([id, mine.n, mine.N, mine.brokers]).toEqual([id, T.ctx.rows.n, T.ctx.rows.N, T.ctx.rows.brokers]);
      for (const k of ['t', 'b', 'inv', 'brd', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf', 'has'] as const) expect([id, k, same(mine[k], T.ctx.rows[k])]).toEqual([id, k, true]);
    }
    // BBBB's last broker day has no price bar: its rows are left out, as the Terminal leaves them out
    const b = STOCKS.BBBB, rowsOnLast = b.rows.filter(r => r.d === LAST).length;
    expect(rowsOnLast).toBeGreaterThan(0);
    expect(brokerFlowRows(b.store, terminal(b).candles).n).toBe(b.rows.length - rowsOnLast);
  });
  it('investor types and boards are converted by name: Domestic 0 -> 1, Foreign 1 -> 0 (flow.ts INVESTORS), Tunai -> Cash 2; a Nego-only day is a candle with Nego rows only', () => {
    const v = (rows: Row[]): BrokerRowsLike => ({ ...storeOf(rows) });
    const one = (i: string, m: string) => brokerFlowRows(v([{ d: FIRST, b: 'AK', i, m, bv: 1, sv: 1, bl: 1, sl: 1, bf: 1, sf: 1 }]), [FIRST]);
    expect([one('Domestic', 'Regular').inv[0], one('Foreign', 'Regular').inv[0]]).toEqual([1, 0]);
    expect([one('Domestic', 'Regular').brd[0], one('Domestic', 'Nego').brd[0], one('Domestic', 'Tunai').brd[0]]).toEqual([0, 1, 2]);
    expect(storeOf([{ d: FIRST, b: 'AK', i: 'Domestic', m: 'Tunai', bv: 1, sv: 1, bl: 1, sl: 1, bf: 1, sf: 1 }]).I[0]).toBe(0);    // the file's codes
    const c = STOCKS.CCCC, T = terminal(c), R = brokerFlowRows(c.store, T.candles), k = T.candles.indexOf(NEGO_DAY);
    const onDay = [...R.t].map((t, j) => t === k ? R.brd[j] : -1).filter(x => x >= 0);
    expect(onDay.length).toBeGreaterThan(0);
    expect(new Set(onDay)).toEqual(new Set([1]));
    // the regular board (G1 default) has no value on the Nego-only day; every board has one
    const reg = resolveFlow({ kind: 'flow', metric: 'FL24', params: { window: 1 } }, 'f', { flow: FLOW_CTX }).full(tickerCalc(c.t));
    const all = resolveFlow({ kind: 'flow', metric: 'FL24', params: { window: 1, boards: ['Regular', 'Nego', 'Cash'] } }, 'f', { flow: FLOW_CTX }).full(tickerCalc(c.t));
    expect([reg[T.lo + k], typeof all[T.lo + k]]).toEqual([null, 'number']);
  });
  it('every FL the Terminal computes as it is, at its default parameters, equals computeFlow called the Terminal\'s way, bit for bit, on every candle of every stock (FL34 at the last broker date only, its guard)', () => {
    let compared = 0;
    for (const f of FLOWS) {
      if (f.requires) { expect(code(() => resolveFlow({ kind: 'flow', metric: f.id }, 'f', { flow: FLOW_CTX }))!.code).toBe('METRIC_UNAVAILABLE'); continue }
      if (f.compute !== 'terminal') continue;                       // the Screener's versions: tests/core/flow-screener.test.ts
      // the default parameters: the registry's (flowDefaults, the parameters a condition does not take aside: the
      // levels that only draw and a display-only "Plot"), a built-in percentile baseline capped to the window (K1):
      // FL08, FL09 and FL21 at 60 - 1, FL37 at 60 - 20
      const p = resolveFlowParams(f, undefined, 'f', 60), d = flowDefaults(f.id);
      for (const q of f.params) if (!q.condition) delete d[q.key];
      const capped = { FL08: 59, FL09: 59, FL21: 59, FL37: 40 } as Record<string, number>;
      expect([f.id, p]).toEqual([f.id, capped[f.id] ? { ...d, baseline: capped[f.id] } : d]);
      // a sided indicator draws its sell line with side sell (its buy line at the default side buy)
      const refs = f.outputs.map(o => ({ output: o.key, params: producedOutputs(f.id, p).includes(o.key) ? {} : { side: o.key } }));
      for (const x of refs) {
        const r = resolveFlow({ kind: 'flow', metric: f.id, output: x.output, params: x.params as never }, 'f', { flow: FLOW_CTX });
        for (const id of WITH_DATA) {
          const s = STOCKS[id], T = terminal(s), all = computeFlow(f.id, T.ctx, (r.ref as any).params)[x.output];
          const want = f.current_only ? all.map((v, k) => T.candles[k] === LAST ? v : null) : all;
          const got = r.full(tickerCalc(s.t));
          expect([f.id, x.output, id, want !== undefined]).toEqual([f.id, x.output, id, true]);
          const inWindow = Array.from(got).slice(T.lo, T.lo + T.candles.length), outside = [...Array.from(got).slice(0, T.lo), ...Array.from(got).slice(T.lo + T.candles.length)];
          expect([f.id, x.output, id, same(inWindow, want)]).toEqual([f.id, x.output, id, true]);
          expect(outside.every(v => v === null)).toBe(true);
          compared++;
        }
      }
    }
    expect(compared).toBeGreaterThan(40 * 4);
  }, 60_000);   // about 0.5 s alone (48 FL x every stock): a heavy test's own timeout under a full parallel run
  it('one computeFlow per (ticker, id, parameters): the outputs of one call share it through the memo', () => {
    const s = stock('MEMO', 11, STOCKS.AAAA.rows), memo = s.t.flow!.memo as Map<string, unknown>;
    resolveFlow({ kind: 'flow', metric: 'FL11', output: 'value' }, 'f', { flow: FLOW_CTX }).full(tickerCalc(s.t));
    resolveFlow({ kind: 'flow', metric: 'FL11', output: 'change' }, 'f', { flow: FLOW_CTX }).full(tickerCalc(s.t));
    expect(memo.size).toBe(1);
  });
});

/* ---- validation ---------------------------------------------------------------------------------------------------- */

describe('parameter refusals (P5_FLOW.md section 1)', () => {
  const R = (ref: Record<string, unknown>) => code(() => resolveFlow({ kind: 'flow', ...ref } as never, 'definition.conditions[0].test.metric', { flow: FLOW_CTX }));
  it('checks every parameter against the registry: kind, range, options; names the field, the rule and a right and a wrong value', () => {
    expect(R({ metric: 'FL99' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.metric' });
    expect(R({ metric: 'FL24', params: { window: 0 } })).toMatchObject({ code: 'PARAM_OUT_OF_RANGE', field: 'definition.conditions[0].test.metric.params.window', details: { min: 1, max: 250, integer: true } });
    expect(R({ metric: 'FL24', params: { window: 251 } })!.message).toMatch(/must be a whole number from 1 to 250 \(right: 10; wrong: 251\)/);
    expect(R({ metric: 'FL24', params: { window: 2.5 } })!.code).toBe('PARAM_OUT_OF_RANGE');
    expect(R({ metric: 'FL24', params: { window: '10' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.window' });
    expect(R({ metric: 'FL09', params: { pct_min: 101 } })).toMatchObject({ code: 'PARAM_OUT_OF_RANGE', details: { min: 0, max: 100, integer: false } });
    expect(R({ metric: 'FL09', params: { use_imb: 'yes' } })).toMatchObject({ code: 'INVALID_CONDITION', details: { allowed: [true, false] } });
    expect(R({ metric: 'FL01', params: { scope: 'all' } })).toMatchObject({ code: 'INVALID_CONDITION', details: { allowed: ['selected', 'topn'] } });
    expect(R({ metric: 'FL24', params: { boards: [] } })!.message).toMatch(/is a list of at least one of Regular, Nego, Cash, each once/);
    expect(R({ metric: 'FL24', params: { boards: ['Regular', 'Regular'] } })!.code).toBe('INVALID_CONDITION');
    expect(R({ metric: 'FL24', params: { boards: ['Tunai'] } })).toMatchObject({ code: 'INVALID_CONDITION', details: { allowed: ['Regular', 'Nego', 'Cash'] } });
    expect(R({ metric: 'FL23', params: { holders: 'selected', brokers: ['YP', 'AK', 'CC', 'DX', 'KK', 'LG'] } })!.message).toMatch(/a list of at most 5 broker codes/);
    expect(R({ metric: 'FL11', params: { scope: 'selected', brokers: ['YP', 'YP'] } })!.message).toMatch(/is a list of broker codes, each once/);
    expect(R({ metric: 'FL01', params: { scope: 'selected', brokers: ['yp'] } })!.code).toBe('INVALID_CONDITION');
    expect(R({ metric: 'FL18', params: { anchor_sessions: 60 } })).toMatchObject({ code: 'PARAM_OUT_OF_RANGE', field: 'definition.conditions[0].test.metric.params.anchor_sessions', details: { min: 1, max: 59, integer: true } });
    expect(R({ metric: 'FL24', params: { nope: 1 } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.nope' });
  });
  it('refuses the kinds that only draw (levels, button, fixed) as condition parameters', () => {
    expect(R({ metric: 'FL24', params: { levels: '6, 10' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.levels' });
    expect(R({ metric: 'FL34', params: { reset: null } })!.message).toMatch(/only draws on the Terminal's chart/);
    expect(R({ metric: 'FL01', params: { ranking: 'daily' } })!.code).toBe('INVALID_CONDITION');
  });
  it('a select or switch whose every option gives the same values (the Terminal\'s "Plot") is display-only, derived by the generator\'s probe: not a condition parameter, refused if sent, its default used; one that changes a value (FL34 "Change line vs") stays (QA unit B, QA5)', () => {
    const reg = (REG as any).indicators as any[];
    // derived on the probe, never listed: the generator's answer is the registry's, entry by entry
    for (const r of reg) expect([r.id, FLOW_BY_ID[r.id].params.filter(p => p.display_only).map(p => p.key)]).toEqual([r.id, G.displayOnlyParams(r).filter((k: string) => FLOW_BY_ID[r.id].params.some(p => p.key === k))]);
    expect(FLOWS.flatMap(f => f.params.filter(p => p.display_only).map(p => `${f.id}.${p.key}`))).toEqual(expect.arrayContaining(['FL26.plot', 'FL34.plot']));
    for (const id of ['FL26', 'FL34']) {
      const p = FLOW_BY_ID[id].params.find(q => q.key === 'plot')!;
      expect([id, p.condition, p.display_only]).toEqual([id, false, true]);
      const r = R({ metric: id, params: { plot: 'line' } })!;
      expect([id, r.code, r.field]).toEqual([id, 'INVALID_CONDITION', 'definition.conditions[0].test.metric.params.plot']);
      expect(r.message).toMatch(/"Plot" of FL\d\d .* only changes how the Terminal draws the indicator \(each of its options gives the same values\); a condition does not take it, so remove it \(the parameters a condition takes: .*; right: .*; wrong: \{"plot": \.\.\.\}\)\./);
      // its options give the same values on the real fixture too, and left out the default is what computeFlow takes
      const T = terminal(STOCKS.AAAA), at = (plot: string) => computeFlow(id, T.ctx, { ...flowDefaults(id), plot });
      expect([id, JSON.stringify(at('hist')) === JSON.stringify(at('line'))]).toEqual([id, true]);
      const params = (resolveFlow({ kind: 'flow', metric: id } as never, 'f', { flow: FLOW_CTX }).ref as any).params;
      expect([id, 'plot' in params]).toEqual([id, false]);
    }
    // a choice that changes a value keeps its place: FL34's change line reads 1, 5 or 20 sessions back
    const lag = FLOW_BY_ID.FL34.params.find(q => q.key === 'lag')!;
    expect([lag.condition, lag.display_only]).toEqual([true, undefined]);
    expect(R({ metric: 'FL34', output: 'change', params: { lag: '5' } })).toBe(null);
    const ctx = probeContext(80), change = (l: string) => computeFlow('FL34', ctx, { ...flowDefaults('FL34'), lag: l }).change;
    expect(JSON.stringify(change('1')) === JSON.stringify(change('5'))).toBe(false);
    // a choice that matters only beside another is not display-only: FL07's denominator under one investor type
    expect(FLOW_BY_ID.FL07.params.find(q => q.key === 'denom')!.condition).toBe(true);
  });
  it('refuses an output the indicator does not give at its parameters (a side; the Terminal\'s FL23 lines), and selected brokers without a broker (FL23\'s holders too)', () => {
    expect(R({ metric: 'FL24', output: 'buy' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.output', details: { allowed: ['value'] } });
    expect(R({ metric: 'FL01', output: 'sell' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.side' });
    expect(R({ metric: 'FL01', output: 'sell', params: { side: 'both' } })).toBe(null);
    expect(R({ metric: 'FL23' })).toBe(null);
    expect(R({ metric: 'FL23', output: 'lines' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.output', details: { allowed: ['value', 'count'] } });
    expect(R({ metric: 'FL23', params: { total: true } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.total' });
    const none = R({ metric: 'FL23', params: { holders: 'selected' } })!;
    expect([none.code, none.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.params.brokers']);
    expect(none.message).toMatch(/reads the selected brokers, and none is named: name at least one broker, or choose another holders setting \(right: \["YP"\]; wrong: \[\]\)/);
    expect(R({ metric: 'FL23', params: { holders: 'top', brokers: [] } })).toBe(null);
    expect(R({ metric: 'FL01', params: { scope: 'selected' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.brokers' });
    expect(R({ metric: 'FL46', params: { num_scope: 'selected' } })!.field).toBe('definition.conditions[0].test.metric.params.num_brokers');
  });
  it('the anchored indicators take the anchor N sessions back instead of a date (decisions D, E): a date is not one of their parameters', () => {
    for (const id of ['FL18', 'FL19', 'FL20', 'FL44', 'FL45']) {
      expect(R({ metric: id, params: { anchor_sessions: 5 } })).toBe(null);
      const r = R({ metric: id, params: { anchor: WINDOW[10] } })!;
      expect([id, r.code, r.field, r.message]).toEqual([id, 'INVALID_CONDITION', 'definition.conditions[0].test.metric.params.anchor', expect.stringMatching(/not a parameter of .*; use only .*anchor_sessions/)]);
      expect(R({ metric: id, params: { anchor_sessions: 0 } })!.code).toBe('PARAM_OUT_OF_RANGE');
    }
  });
});

describe('depth (K1): derived from the indicator and the loaded window, never a hand list', () => {
  const at = (sessions: number): FlowBindContext => ({ ...FLOW_CTX, sessions });
  const bind = (test: Test, w = FLOW_CTX) => code(() => bindCondition({ id: 'a', enabled: true, test }, 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX, flow: w }));
  const fl24 = (window: number) => ({ kind: 'flow', metric: 'FL24', params: { window } }) as never;
  const pct = (of: unknown, length: number) => ({ kind: 'transform', fn: 'percentile', of, args: { length } }) as never;
  it('the indicator reads its window: FL24 window 10 reads 10 sessions, a percentile over a baseline window + baseline, an anchor N sessions back N + 1, FL23 its lookback', () => {
    expect(indicatorDepth(FLOW_BY_ID.FL24, 'value', resolveFlowParams(FLOW_BY_ID.FL24, { window: 10 }, 'f'))).toBe(10);
    expect(indicatorDepth(FLOW_BY_ID.FL08, 'value', resolveFlowParams(FLOW_BY_ID.FL08, { window: 3, baseline: 30 }, 'f'))).toBe(33);
    expect(indicatorDepth(FLOW_BY_ID.FL33, 'buy', resolveFlowParams(FLOW_BY_ID.FL33, undefined, 'f'))).toBe(25);          // recent 5 + baseline 20
    expect(indicatorDepth(FLOW_BY_ID.FL18, 'value', resolveFlowParams(FLOW_BY_ID.FL18, undefined, 'f'))).toBe(21);
    expect(indicatorDepth(FLOW_BY_ID.FL20, 'value', resolveFlowParams(FLOW_BY_ID.FL20, { anchor_sessions: 7 }, 'f'))).toBe(8);
    expect(indicatorDepth(FLOW_BY_ID.FL23, 'value', resolveFlowParams(FLOW_BY_ID.FL23, { lookback: 12 }, 'f'))).toBe(12);
    expect(indicatorDepth(FLOW_BY_ID.FL23, 'count', resolveFlowParams(FLOW_BY_ID.FL23, { holders: 'all', series: 'daily' }, 'f'))).toBe(1);
    expect(indicatorDepth(FLOW_BY_ID.fnet, 'value', resolveFlowParams(FLOW_BY_ID.fnet, { window: 15 }, 'f'))).toBe(15);
    // with the operator's N: an anchor 40 back with a change over 20 reads 61 sessions, beyond the window
    const bind = (test: Test) => code(() => bindCondition({ id: 'a', enabled: true, test }, 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX }));
    const fl20 = (n: number) => ({ kind: 'transform', fn: 'change', of: { kind: 'flow', metric: 'FL20', params: { anchor_sessions: n } }, args: { bars: 20 } }) as never;
    expect(bind({ kind: 'value', metric: fl20(39), op: 'gt', value: 0 })).toBe(null);
    expect(bind({ kind: 'value', metric: fl20(40), op: 'gt', value: 0 })!.details).toMatchObject({ limit: 'broker_depth', allowed: 60, needed: 61 });
  });
  it('the operators add their N: FL24 window 10 with a percentile over 40 reads 50 (passes), over 55 reads 65 (refused with both numbers and the window)', () => {
    expect(bind({ kind: 'value', metric: pct(fl24(10), 40), op: 'ge', value: 90 })).toBe(null);
    const r = bind({ kind: 'value', metric: pct(fl24(10), 55), op: 'ge', value: 90 })!;
    expect(r).toMatchObject({ code: 'LIMIT_EXCEEDED', field: 'definition.conditions[0].test', details: { limit: 'broker_depth', allowed: 60, needed: 65 } });
    expect(r.message).toMatch(/reads 10 sessions of broker data and its operators 55 more, 65 in all; the Screener holds the last 60 sessions/);
    // acceleration reads 2N; a window test its length, an event its within
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'acceleration', of: fl24(10), args: { length: 25 } } as never, op: 'gt', value: 0 })).toBe(null);
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'acceleration', of: fl24(10), args: { length: 26 } } as never, op: 'gt', value: 0 })!.details).toMatchObject({ needed: 62 });
    expect(bind({ kind: 'window', mode: 'at_least', length: 51, count: 3, test: { kind: 'value', metric: fl24(10), op: 'gt', value: 0 } })!.details).toMatchObject({ limit: 'broker_depth', needed: 61 });
    expect(bind({ kind: 'event', within: 50, signal: { lhs: fl24(10), op: 'crosses_above', rhs: { value: 0 } } })).toBe(null);
    expect(bind({ kind: 'event', within: 51, signal: { lhs: fl24(10), op: 'crosses_above', rhs: { value: 0 } } })!.details).toMatchObject({ needed: 61 });
    expect(bind({ kind: 'value', metric: fl24(61), op: 'gt', value: 0 })!.details).toMatchObject({ limit: 'broker_depth', allowed: 60, needed: 61 });
  });
  it('the limit is the loaded window: with 40 sessions the same percentile over 35 is refused (45 > 40); a built-in baseline left out is capped to the window less the indicator\'s own, one stated is not', () => {
    expect(bind({ kind: 'value', metric: pct(fl24(10), 35), op: 'ge', value: 90 }, at(40))!.details).toMatchObject({ allowed: 40, needed: 45 });
    const r = resolveFlow({ kind: 'flow', metric: 'FL37' }, 'f', { flow: at(40) });
    expect([(r.ref as any).params.baseline, r.flowDepth]).toEqual([20, 40]);
    expect(bind({ kind: 'value', metric: { kind: 'flow', metric: 'FL37', params: { baseline: 250 } } as never, op: 'ge', value: 90 })!.details).toMatchObject({ limit: 'broker_depth', needed: 270 });
  });
});

describe('availability (P5_FLOW.md section 1)', () => {
  const R = (w: FlowBindContext, metric = 'FL24') => code(() => resolveFlow({ kind: 'flow', metric }, 'f', { flow: w }));
  it('a window still loading is refused FLOW_UNAVAILABLE in words; no broker days REQUIRES_DATA; FL31 (no insider data) and FL34 without the classification REQUIRES_DATA', () => {
    expect(R({ ...FLOW_CTX, sessions: 38, complete: false })).toMatchObject({ code: 'METRIC_UNAVAILABLE', details: { metric: 'FL24', availability: 'REQUIRES_DATA', reason_code: 'FLOW_UNAVAILABLE', reason: expect.stringMatching(/^The broker data is still loading \(38 sessions loaded so far\)/) } });
    expect(R({ ...FLOW_CTX, sessions: 0, first: null, last: null })!.details).toMatchObject({ availability: 'REQUIRES_DATA', reason: 'It needs the broker data, which this publication does not carry yet.' });
    expect(R(FLOW_CTX, 'FL31')!.details).toMatchObject({ metric: 'FL31', availability: 'REQUIRES_DATA' });
    expect(R({ ...FLOW_CTX, classification: false }, 'FL34')!.code).toBe('METRIC_UNAVAILABLE');
    expect(code(() => resolveFlow({ kind: 'flow', metric: 'FL34', params: { inst: ['AK'], retail: ['BK'] } }, 'f', { flow: { ...FLOW_CTX, classification: false } }))).toBe(null);
  });
  it('validation refuses a flow condition while the window loads, with the catalog\'s reason; a switched-off one is normalized', () => {
    const def = (enabled: boolean): unknown => ({ universe: { security_types: ['stock'] }, logic: 'all', conditions: [{ id: 'a', enabled, test: { kind: 'value', metric: { kind: 'flow', metric: 'FL24' }, op: 'gt', value: 0 } }] });
    const loading = { ...FLOW_CTX, sessions: 38, complete: false };
    const ctx = { ...vctx(Object.keys(STOCKS)), availability: availabilityMap({}, METRICS_CATALOG, undefined, loading), flow: loading };
    expect(code(() => validateDefinition(def(true), ctx))).toMatchObject({ code: 'METRIC_UNAVAILABLE', field: 'definition.conditions[0].test.metric', details: { reason_code: 'FLOW_UNAVAILABLE', reason: availabilityMap({}, METRICS_CATALOG, undefined, loading).get('FL24')!.reason } });
    const off = validateDefinition(def(false), ctx);
    expect(off.conditions[0].test).toEqual({ kind: 'value', metric: { kind: 'flow', metric: 'FL24', output: 'value', params: { top: 3, boards: ['Regular'], investors: ['Foreign', 'Domestic'], window: 10 } }, op: 'gt', value: 0 });
    // an id that is no flow entry is refused naming the entries
    expect(code(() => resolveSeries({ kind: 'flow', metric: 'FL49' } as never, 'f', { ...OPTS }))).toMatchObject({ code: 'INVALID_CONDITION', details: { allowed: FLOWS.map(f => f.id) } });
  });
});

/* ---- the screen --------------------------------------------------------------------------------------------------- */

const INDEX = synth('IHSG', 2, PRICE_BARS, '2026-07-01');
const ROWS = Object.values(STOCKS).map(s => rowOf(s.t, E));
const env = () => memoryEnv(Object.values(STOCKS).map(s => s.t), INDEX, ROWS, E, { flow: FLOW_CTX });
const screen = (tests: Test[]) => runScreen({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'any',
  conditions: tests.map((test, k) => ({ id: `c${k}`, enabled: true, test })) } as Definition, env(), { exhaustive: true });
const FL24 = { kind: 'flow', metric: 'FL24' } as never;
/** a stock's FL24 at defaults the Terminal's way, on its bars (null outside the window) */
function fl24Bars(id: string): (number | null)[] {
  const s = STOCKS[id], T = terminal(s), v = computeFlow('FL24', T.ctx, flowDefaults('FL24')).value, out: (number | null)[] = new Array(s.t.dates.length).fill(null);
  v.forEach((x, k) => { out[T.lo + k] = x });
  return out;
}
const flowBar = (id: string): number => { const s = STOCKS[id], T = terminal(s); for (let k = T.candles.length - 1; k >= 0; k--) if (T.ctx.rows.has[k]) return T.lo + k; return -1 };

describe('evaluation date (P10 a) and the condition summary', () => {
  it('reads each stock at its last candle with broker data on or before E: eval_date that date, source flow; no broker data in the window is NA FLOW_UNAVAILABLE', () => {
    const r = screen([{ kind: 'value', metric: FL24, op: 'gt', value: -1000 }]);
    const cell = (t: string) => r.rows.find(x => x.ticker === t)?.cells[0];
    for (const id of WITH_DATA) {
      const s = STOCKS[id], at = flowBar(id);
      expect(evaluationBar(s.t.dates, E)).toBeGreaterThan(at);                                   // the price runs ahead of the broker data
      expect([id, cell(id)!.status, cell(id)!.eval_date, cell(id)!.value]).toEqual([id, 'pass', s.t.dates[at], round12(fl24Bars(id)[at])]);
    }
    expect(cell('AAAA')!.eval_date).toBe(LAST);
    expect(cell('BBBB')!.eval_date).toBe(WINDOW[58]);                                           // its last broker day has no price bar
    expect(r.conditions[0]).toMatchObject({ source: 'flow', eval_date_basis: 'flow_date', metric: 'FL24.value — Bandar Balance · %', is_default: true, unit: '%',
      params_resolved: { top: 3, boards: ['Regular'], investors: ['Foreign', 'Domestic'], window: 10 } });
    const none = runScreen({ universe: { security_types: ['stock'], tickers: ['DDDD'], price_min: null, adv20_min_idr: null }, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: FL24, op: 'gt', value: -1000 } }] } as Definition, env(), { exhaustive: true });
    expect(none.conditions[0]).toMatchObject({ evaluated: 1, passed: 0, na: 1 });
    // an NA cell is not a displayed row; the cell itself, through the bound condition
    const b = bindCondition({ id: 'a', enabled: true, test: { kind: 'value', metric: FL24, op: 'gt', value: -1000 } }, 'c', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX });
    const e = env(), t = e.bars('DDDD')!;
    const c = b.evaluate({ ticker: 'DDDD', dates: t.dates, bars: t.bars as never, at: evaluationBar(t.dates, E), row: ROWS.find(x => x.ticker === 'DDDD')!, ihsgCalendar: INDEX.dates, series: r2 => e.series(r2, t), xsection: () => null }).cell;
    expect([c.status, c.reason, c.eval_date, c.value]).toEqual(['na', 'FLOW_UNAVAILABLE', null, null]);
  });
});

describe('operators on a flow series (OPERATORS.md; P5_FLOW.md section 1 Series)', () => {
  it('percentile of its own history: equals a brute-force mid-rank of the Terminal\'s FL24 at the flow bar', () => {
    const r = screen([{ kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: FL24, args: { length: 20 } } as never, op: 'ge', value: 0 }]);
    for (const id of WITH_DATA) {
      const want = percentileOwn(fl24Bars(id), 20)[flowBar(id)], cell = r.rows.find(x => x.ticker === id)?.cells[0];
      if (want === null) { expect(cell).toBeUndefined(); continue }
      expect([id, cell!.value, cell!.eval_date]).toEqual([id, round12(want), STOCKS[id].t.dates[flowBar(id)]]);
    }
  });
  it('K of N: FL24 > 0 on at least 3 of the last 10 sessions ending at the flow bar (a session without broker data counts as not passing)', () => {
    const r = screen([{ kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'value', metric: FL24, op: 'gt', value: 0 } }]);
    for (const id of WITH_DATA) {
      const v = fl24Bars(id), at = flowBar(id);
      let n = 0; for (let i = at - 9; i <= at; i++) if (typeof v[i] === 'number' && (v[i] as number) > 0) n++;
      const cell = r.rows.find(x => x.ticker === id)?.cells[0];
      if (n >= 3) expect([id, cell!.status, cell!.value]).toEqual([id, 'pass', n]); else expect(cell === undefined || cell.status !== 'pass').toBe(true);
    }
  });
  it('rank across the screened stocks: percentRank of each stock\'s FL24 at its flow bar against the filtered universe (decision C)', () => {
    const r = screen([{ kind: 'value', metric: { kind: 'rank', of: FL24 } as never, op: 'ge', value: 0 }]);
    const values = new Map<string, number | null>(), members = new Set<string>();
    for (const id of Object.keys(STOCKS)) { const at = flowBar(id), v = at >= 0 ? fl24Bars(id)[at] : null; values.set(id, v); if (v !== null) members.add(id) }
    const ranks = percentRank(values, members);
    for (const id of WITH_DATA) expect([id, r.rows.find(x => x.ticker === id)!.cells[0].value]).toEqual([id, round12(ranks.get(id)!)]);
    expect(r.conditions[0]).toMatchObject({ source: 'flow', eval_date_basis: 'flow_date' });
  });
});

describe('output types (OPERATORS.md section 4) and K7', () => {
  const bind = (test: Test) => code(() => bindCondition({ id: 'a', enabled: true, test }, 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX }));
  const F = (metric: string, params: Record<string, unknown> = {}, output?: string) => ({ kind: 'flow', metric, params, ...(output ? { output } : {}) }) as never;
  it('"=" and "!=" only on D, F and B outputs: FL26 (days), FL09 (flag), FL22 count (brokers); refused on FL24 (%) and FL22 pct', () => {
    expect(bind({ kind: 'value', metric: F('FL26'), op: 'eq', value: 3 })).toBe(null);
    expect(bind({ kind: 'value', metric: F('FL09'), op: 'eq', value: 1 })).toBe(null);
    expect(bind({ kind: 'value', metric: F('FL22', { measure: 'count' }), op: 'ne', value: 5 })).toBe(null);
    expect(bind({ kind: 'value', metric: F('FL24'), op: 'eq', value: 6 })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.op' });
    expect(bind({ kind: 'value', metric: F('FL22'), op: 'eq', value: 50 })!.message).toMatch(/"=" and "!=" are offered only on whole-number values/);
    expect(bind({ kind: 'value', metric: F('FL24'), op: 'ge', value: 6 })).toBe(null);
  });
  it('lots per transaction and price levels take no fixed value, range or rank; a 0/1 signal no range, no measure and no cross; a percentile no own-history measure', () => {
    const r = bind({ kind: 'value', metric: F('FL01'), op: 'gt', value: 5 })!;
    expect(r).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.op' });
    expect(r.message).toMatch(/FL01\.buy is lots per transaction, .* so "Above or below a value" is not offered on it\. It takes the measures /);
    expect(bind({ kind: 'value', metric: F('FL17'), op: 'between', value: 900, value2: 1000 })!.message).toMatch(/is a price level/);
    expect(bind({ kind: 'value', metric: { kind: 'rank', of: F('FL01') } as never, op: 'ge', value: 90 })!.code).toBe('INVALID_CONDITION');
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: F('FL01'), args: { length: 20 } } as never, op: 'ge', value: 90 })).toBe(null);
    expect(bind({ kind: 'value', metric: { kind: 'rank', of: { kind: 'transform', fn: 'change_pct', of: F('FL17'), args: { bars: 5 } } } as never, op: 'ge', value: 90 })).toBe(null);
    expect(bind({ kind: 'value', metric: F('FL09'), op: 'between', value: 0, value2: 1 })!.code).toBe('INVALID_CONDITION');
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'zscore', of: F('FL09'), args: { length: 20 } } as never, op: 'gt', value: 1 })!.code).toBe('INVALID_CONDITION');
    expect(bind({ kind: 'event', within: 3, signal: { lhs: F('FL09'), op: 'crosses_above', rhs: { value: 0.5 } } })!.code).toBe('INVALID_CONDITION');
    expect(bind({ kind: 'window', mode: 'streak', length: 3, test: { kind: 'value', metric: F('FL27'), op: 'eq', value: 1 } })).toBe(null);
    // FL09 reads its whole capped baseline (60 sessions), so even a streak of 3 does not fit the window (K1)
    expect(bind({ kind: 'window', mode: 'streak', length: 3, test: { kind: 'value', metric: F('FL09'), op: 'eq', value: 1 } })!.details).toMatchObject({ limit: 'broker_depth', needed: 63 });
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: F('FL08'), args: { length: 20 } } as never, op: 'ge', value: 90 })!.code).toBe('INVALID_CONDITION');
    expect(bind({ kind: 'window', mode: 'streak', length: 3, test: { kind: 'value', metric: F('FL26'), op: 'ge', value: 1 } })!.code).toBe('INVALID_CONDITION');     // a run is already a run
    // lots per transaction cross a series, not a fixed number
    expect(bind({ kind: 'event', within: 3, signal: { lhs: F('FL01'), op: 'crosses_above', rhs: { value: 5 } } })!.message).toMatch(/against a fixed value is not offered/);
    expect(bind({ kind: 'event', within: 3, signal: { lhs: F('FL01'), op: 'crosses_above', rhs: { kind: 'transform', fn: 'ma', of: F('FL01'), args: { ma: 'SMA', length: 10 } } as never } })).toBe(null);
  });
  it('a 0/1 signal (type F of flow-kinds.json: FL27, FL09) takes no comparison with another series, no state against another series and no average, wherever it stands; the tests it takes still pass (OPERATORS.md section 4, QA3 D2)', () => {
    const T = (fn: string, of: unknown, args: Record<string, unknown> = {}) => ({ kind: 'transform', fn, of, args }) as never;
    const v = (metric: unknown, op = 'ge', value = 0) => ({ kind: 'value', metric, op, value }) as never;
    // every F output of the generated entries is one the rules below apply to (derived from the kinds, no FL list)
    const signals = FLOWS.flatMap(e => e.outputs.filter(o => o.kind === 'F').map(o => [e.id, o.key] as const)).filter(([id]) => FLOW_BY_ID[id].compute !== 'none');
    expect(signals.map(([id]) => id)).toEqual(expect.arrayContaining(['FL09', 'FL27']));
    const refusals: [string, Test, string, RegExp][] = [
      ['relative, the signal as the series', v(T('relative', F('FL27'), { by: F('FL09'), form: 'difference' })), 'definition.conditions[0].test.metric.of', /FL27\.value is a 0\/1 signal, which has no magnitude, so Compared with another series is not offered on it; it takes no measure, only the tests /],
      ['relative, the signal as the second series', v(T('relative', F('FL24'), { by: F('FL27'), form: 'difference' })), 'definition.conditions[0].test.metric.args.by', /FL27\.value is a 0\/1 signal/],
      ['a state against another series, the signal on the left', { kind: 'state', lhs: F('FL27'), op: 'gt', rhs: F('FL09') } as never, 'definition.conditions[0].test.lhs', /so Compared with another series is not offered on it/],
      ['a state against another series, the signal on the right', { kind: 'state', lhs: F('FL24'), op: 'gt', rhs: F('FL27') } as never, 'definition.conditions[0].test.rhs', /FL27\.value is a 0\/1 signal/],
      ['a moving average of the signal (the series another one is compared with)', v(T('ma', F('FL27'), { ma: 'SMA', length: 5 }), 'ge', 0.5), 'definition.conditions[0].test.metric.of', /so Moving average of a series, like Compared with another series, is not offered on it/],
      ['its own average', v(T('vs_average', F('FL09'), { ma: 'SMA', form: 'difference', length: 5 })), 'definition.conditions[0].test.metric.of', /FL09\.value is a 0\/1 signal/],
      ['a ratio of the signal (operator 7 in its ratio form)', v(T('ratio', F('FL27'), { by: F('FL09') })), 'definition.conditions[0].test.metric.of', /so Ratio of two series, like Compared with another series, is not offered on it/],
      ['the signal against its own moving average', { kind: 'state', lhs: F('FL27'), op: 'gt', rhs: T('ma', F('FL27'), { ma: 'SMA', length: 5 }) } as never, 'definition.conditions[0].test.rhs.of', /FL27\.value is a 0\/1 signal/],
      ['a change of the signal in its own unit', v(T('change', F('FL27'), { bars: 3 })), 'definition.conditions[0].test.metric.of', /so Change, in its own unit is not offered on it/],
    ];
    for (const [what, test, field, message] of refusals) {
      const r = bind(test);
      expect([what, r?.code, r?.field]).toEqual([what, 'INVALID_CONDITION', field]);
      expect([what, r!.message]).toEqual([what, expect.stringMatching(message)]);
      expect([what, r!.message]).toEqual([what, expect.stringMatching(/\(right: .* of RSI; wrong: .* of FL\d\d\.value\)\.$/)]);
    }
    // the rule follows the type, not the id: every F output is refused the same way
    for (const [id, out] of signals) expect([id, bind({ kind: 'state', lhs: F(id, {}, out), op: 'gt', rhs: F(id, {}, out) } as never)?.code]).toEqual([id, 'INVALID_CONDITION']);
    // what section 4 offers a 0/1 signal: "= 1", ever, K of N, in a row; and a lag of it stays a signal
    expect(bind(v(F('FL27'), 'eq', 1))).toBe(null);
    expect(bind({ kind: 'window', mode: 'ever', length: 5, test: v(F('FL27'), 'eq', 1) } as never)).toBe(null);
    expect(bind({ kind: 'window', mode: 'at_least', length: 5, count: 2, test: v(F('FL27'), 'eq', 1) } as never)).toBe(null);
    expect(bind({ kind: 'state', lhs: F('FL27'), op: 'gt', rhs: { value: 0.5 } } as never)).toBe(null);
    expect(bind(v(T('lag', F('FL27'), { bars: 1 }), 'eq', 1))).toBe(null);
    // a series of a type that takes them keeps them: a relative comparison and a state of two % series, an average of lots,
    // a percentile or a run against its own moving average (operators 7 and 8 are offered on P and D)
    expect(bind(v(T('relative', F('FL24'), { by: F('FL07'), form: 'difference' }), 'ge', -1e9))).toBe(null);
    expect(bind({ kind: 'state', lhs: F('FL24'), op: 'gt', rhs: F('FL07') } as never)).toBe(null);
    for (const m of [F('FL21', { baseline: 20 }), F('FL26', { window: 30 })]) expect(bind({ kind: 'state', lhs: m, op: 'gt', rhs: T('ma', m, { ma: 'SMA', length: 5 }) } as never)).toBe(null);
    expect(bind({ kind: 'event', within: 3, signal: { lhs: F('FL01'), op: 'crosses_above', rhs: T('ma', F('FL01'), { ma: 'SMA', length: 10 }) } } as never)).toBe(null);
  });
  it('two series of one unit: the close against Buy VWAP · Rolling (both price levels) is a state and a cross; Bandar Balance · % against the close is refused naming both units', () => {
    const close = { kind: 'price', field: 'close' } as never;
    expect(bind({ kind: 'state', lhs: close, op: 'gt', rhs: F('FL17') })).toBe(null);
    expect(bind({ kind: 'event', within: 5, signal: { lhs: close, op: 'crosses_above', rhs: F('FL17') } })).toBe(null);
    expect(bind({ kind: 'state', lhs: F('FL24'), op: 'gt', rhs: close })!.message).toMatch(/FL24\.value is in % and close is a price level; a comparison of two series needs the same unit/);
    const r = screen([{ kind: 'state', lhs: close, op: 'gt', rhs: F('FL17') }]);
    for (const id of WITH_DATA) {
      const s = STOCKS[id], T = terminal(s), v = computeFlow('FL17', T.ctx, flowDefaults('FL17')).value, at = flowBar(id), x = v[at - T.lo];
      const cell = r.rows.find(z => z.ticker === id)?.cells[0];
      if (x === null) continue;
      const pass = (s.t.bars.C[at] as number) > x;
      expect([id, pass ? cell?.status : 'skip', pass ? cell?.rhs : null]).toEqual([id, pass ? 'pass' : 'skip', pass ? round12(x) : null]);
    }
  });
});
