/* EXEC-SCREENER-FLOW-CANDLES P5a (verification/screener/P5_FLOW.md section 5): the Terminal's 48 flow indicators in the
   Screener. A fixture of several stocks over a 60-session broker window (P4's store layout: per ticker, rows ordered by
   date then broker, investor type and board; investor types Domestic=0, Foreign=1; boards Regular, Nego, Tunai), with a
   Nego-only day, a broker day without a price bar, a stock without broker data and price bars after the last broker
   day. Every value is compared, bit for bit, with flow.ts computeFlow called the Terminal's way: flow.ts flowRows on
   the same rows as objects with their names, the Terminal's context (close, volume, dates of the candles, the
   classification), the anchor and Broker Inventory's start set to the first candle as the Terminal sets them. */
import { describe, expect, it } from 'vitest';
import { computeFlow, flowDefaults, flowRows } from '../../../terminal/src/calc/flow.ts';
import type { FlowContext } from '../../../terminal/src/calc/flow.ts';
import REG from '../../../terminal/src/data/flowRegistry.json' with { type: 'json' };
import KINDS from '../../src/core/flow-kinds.json' with { type: 'json' };
import * as G from '../../scripts/build-screener-registry.mjs';
import type { Definition, Test } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { evaluationBar, round12 } from '../../src/core/evaluate.ts';
import { FLOWS, FLOW_BY_ID, brokerFlowRows, indicatorDepth, producedOutputs, resolveFlow, resolveFlowParams } from '../../src/core/flowmetrics.ts';
import type { BrokerRowsLike, FlowBindContext, TickerFlow } from '../../src/core/flowmetrics.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import type { TickerBars } from '../../src/core/metrics.ts';
import { runScreen } from '../../src/core/screen.ts';
import { percentileOwn } from '../../src/core/transforms.ts';
import { availabilityMap, validateDefinition } from '../../src/core/validate.ts';
import { percentRank } from '../../src/core/xsection.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rng, rowOf, synth, vctx } from './helpers.ts';

/* ---- the fixture ---------------------------------------------------------------------------------------------- */

const BROKERS = ['AK', 'BK', 'CC', 'DX', 'KK', 'LG', 'MG', 'NI', 'PD', 'RX', 'XC', 'XL', 'YP', 'ZP'];
const INVESTORS = ['Domestic', 'Foreign'] as const, BOARDS = ['Regular', 'Nego', 'Tunai'] as const;   // the P4 file's tables
const CLASS: Record<string, string> = Object.fromEntries(BROKERS.map((b, k) => [b, k % 3 === 0 ? 'Institutional-heavy' : k % 3 === 1 ? 'Retail-heavy' : 'Mixed']));
const PRICE_BARS = 84, LEAD = 22;                  // 84 weekday bars: 22 before the window, 60 in it, 2 after it
const MARKET = synth('MKT', 1, PRICE_BARS, '2026-07-01').dates as string[];
const WINDOW = MARKET.slice(LEAD, LEAD + 60);      // the 60 loaded broker dates
const FIRST = WINDOW[0], LAST = WINDOW[59];
const FLOW_CTX: FlowBindContext = { sessions: 60, first: FIRST, last: LAST, complete: true, classification: true };
const E = MARKET[PRICE_BARS - 1];                  // price_through: two sessions after the last broker day

interface Row { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf: number | null; sf: number | null }
/** Deterministic broker rows of one stock on its broker dates: 6 to 10 brokers, both investor types, the Regular board
    and now and then Nego and Tunai, whole and odd lots, a missing transaction count now and then. `negoOnly`: that date
    holds Nego rows only. */
function rowsOf(seed: number, dates: readonly string[], negoOnly?: string): Row[] {
  const r = rng(seed), out: Row[] = [];
  for (const d of dates) {
    const n = 6 + Math.floor(r() * 5), picked = [...BROKERS].sort(() => r() - 0.5).slice(0, n);
    for (const b of picked) for (const i of INVESTORS) {
      const boards = d === negoOnly ? ['Nego'] : r() < 0.25 ? ['Regular', 'Nego'] : r() < 0.1 ? ['Regular', 'Tunai'] : ['Regular'];
      for (const m of boards) {
        const bl = r() < 0.2 ? Math.round(r() * 5e4) / 100 : Math.round(r() * 5e3), sl = r() < 0.2 ? Math.round(r() * 5e4) / 100 : Math.round(r() * 5e3);
        const px = 900 + 200 * r();
        out.push({ d, b, i, m, bv: Math.round(bl * 100 * px), sv: Math.round(sl * 100 * (px + 10 * r())), bl, sl,
          bf: r() < 0.03 ? null : 1 + Math.floor(r() * 300), sf: r() < 0.03 ? null : 1 + Math.floor(r() * 300) });
      }
    }
  }
  return out;
}
/** P4's store for one ticker (broker.ts BrokerRows): every row of the window's dates, ordered by date, then broker,
    investor type and board in text order (the files' primary key order); D into WINDOW, B into the union of brokers. */
function storeOf(rows: readonly Row[]): BrokerRowsLike {
  const sorted = [...rows].sort((x, y) => x.d < y.d ? -1 : x.d > y.d ? 1 : x.b < y.b ? -1 : x.b > y.b ? 1 : x.i < y.i ? -1 : x.i > y.i ? 1 : x.m < y.m ? -1 : x.m > y.m ? 1 : 0);
  const brokers = [...BROKERS].sort(), nan = (v: number | null) => v === null ? NaN : v;
  return {
    rows: sorted.length, dates: WINDOW, brokers, investor_types: INVESTORS, boards: BOARDS,
    D: Uint16Array.from(sorted, x => WINDOW.indexOf(x.d)), B: Uint16Array.from(sorted, x => brokers.indexOf(x.b)),
    I: Uint8Array.from(sorted, x => INVESTORS.indexOf(x.i as never)), M: Uint8Array.from(sorted, x => BOARDS.indexOf(x.m as never)),
    BV: Float64Array.from(sorted, x => x.bv), SV: Float64Array.from(sorted, x => x.sv), BL: Float64Array.from(sorted, x => x.bl), SL: Float64Array.from(sorted, x => x.sl),
    BF: Float64Array.from(sorted, x => nan(x.bf)), SF: Float64Array.from(sorted, x => nan(x.sf)),
  };
}
/** A stock's price bars without the bars of `drop` (a broker day without a price bar). */
function without(t: TickerBars, drop: readonly string[]): TickerBars {
  const keep = t.dates.map((d, k) => drop.includes(d) ? -1 : k).filter(k => k >= 0), cut = (a: ArrayLike<unknown>) => keep.map(k => a[k]) as any;
  return { ticker: t.ticker, dates: keep.map(k => t.dates[k]), bars: { O: cut(t.bars.O), H: cut(t.bars.H), L: cut(t.bars.L), C: cut(t.bars.C), V: cut(t.bars.V), T: keep.map(k => t.dates[k]) } };
}
interface Stock { t: TickerBars; rows: Row[]; store: BrokerRowsLike }
const PK = (x: Row, y: Row) => x.d < y.d ? -1 : x.d > y.d ? 1 : x.b < y.b ? -1 : x.b > y.b ? 1 : x.i < y.i ? -1 : x.i > y.i ? 1 : x.m < y.m ? -1 : x.m > y.m ? 1 : 0;
/** A stock: its price bars (without `drop`), its broker rows in the files' order (date, then the primary key: broker,
    investor type, board) as the Terminal's files and the Screener's store hold them, and the store. */
const stock = (ticker: string, seed: number, unsorted: Row[], drop: string[] = []): Stock => {
  const rows = [...unsorted].sort(PK);
  const t = without(synth(ticker, seed, PRICE_BARS, '2026-07-01'), drop), store = storeOf(rows);
  const flow: TickerFlow = { first: FIRST, last: LAST, rows: () => store, classification: CLASS, memo: new Map() };
  return { t: { ...t, flow }, rows, store };
};
/** AAAA: every window date; BBBB: broker rows on its last broker day, which has no price bar; CCCC: a Nego-only day;
    DDDD: no broker data; EEEE: broker data on the last 30 dates only. */
const NEGO_DAY = WINDOW[37];
const STOCKS: Record<string, Stock> = {
  AAAA: stock('AAAA', 11, rowsOf(101, WINDOW)),
  BBBB: stock('BBBB', 12, rowsOf(102, WINDOW), [LAST]),
  CCCC: stock('CCCC', 13, rowsOf(103, WINDOW, NEGO_DAY)),
  DDDD: stock('DDDD', 14, []),
  EEEE: stock('EEEE', 15, rowsOf(105, WINDOW.slice(30))),
};
const WITH_DATA = ['AAAA', 'BBBB', 'CCCC', 'EEEE'];

/** The Terminal's way: flow.ts flowRows on the rows as objects (names, a missing count null), the candles the stock's
    price bars inside the window, its context, and the anchor and start of the first visible candle. */
function terminal(s: Stock): { ctx: FlowContext; lo: number; candles: string[] } {
  const D = s.t.dates, lo = D.findIndex(d => d >= FIRST), candles = D.filter(d => d >= FIRST && d <= LAST) as string[];
  const at = new Map(candles.map((d, k) => [d, k]));
  const rows = flowRows(s.rows, candles.length, d => at.get(d) ?? -1);
  const num = (x: unknown) => typeof x === 'number' && Number.isFinite(x) ? x : null;
  const close = candles.map((_, k) => num(s.t.bars.C[lo + k])), volume = candles.map((_, k) => num(s.t.bars.V[lo + k]));
  return { ctx: { rows, dates: candles, close, volume, insider: [], classification: CLASS }, lo, candles };
}
const terminalParams = (id: string, p: Record<string, unknown>, first: string) => {
  const q: Record<string, unknown> = { ...p };
  for (const k of Object.keys(q)) if (FLOW_BY_ID[id].params.find(x => x.key === k)?.kind === 'date' && q[k] === 'view') q[k] = first;
  if (id === 'FL23') q.start = first;
  return q;
};
const code = (f: () => unknown) => { try { f(); return null } catch (e) { const x = e as ScreenerError; return { code: x.code, field: x.field, message: x.message, details: x.details } } };
const same = (a: ArrayLike<unknown>, b: ArrayLike<unknown>) => a.length === b.length && Array.from(a).every((v, k) => Object.is(v, b[k]));

/* ---- the catalog ---------------------------------------------------------------------------------------------- */

describe('catalog (P5_FLOW.md section 2)', () => {
  it('holds 48 generated flow entries, one per FL of flowRegistry.json, with its name, family, unit, outputs, tip and parameters; FL31 REQUIRES_DATA', () => {
    const reg = (REG as any).indicators as any[];
    expect(FLOWS.map(f => f.id)).toEqual(reg.map(r => r.id));
    expect(FLOWS.length).toBe(48);
    for (const r of reg) {
      const f = FLOW_BY_ID[r.id];
      expect([f.name, f.family, f.unit, f.tip, f.outputs.map(o => o.key), f.default_output]).toEqual([r.name, r.family, r.unit, r.tip, r.outputs, r.outputs[0]]);
      expect(f.params.map(p => p.key)).toEqual(r.params.map((p: any) => p.key));
      for (const p of f.params) expect([r.id, p.key, p.condition]).toEqual([r.id, p.key, !['levels', 'button', 'fixed'].includes(p.kind)]);
      // G1: the registry's default board, Regular
      const boards = f.params.find(p => p.key === 'boards');
      if (boards) expect(boards.default).toEqual(['Regular']);
    }
    expect(G.flowEntries(REG, KINDS)).toEqual(FLOWS);                                       // the generator's own build
    const a = availabilityMap({}, METRICS_CATALOG, undefined, FLOW_CTX);
    expect(FLOWS.filter(f => a.get(f.id)!.availability !== 'AVAILABLE').map(f => f.id)).toEqual(['FL31']);
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
    expect(FLOWS.filter(f => f.requires).map(f => [f.id, f.requires])).toEqual([['FL31', 'insider']]);
    expect(FLOWS.filter(f => f.needs_classification).map(f => f.id)).toEqual(['FL34']);
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
  it('every FL at its default parameters equals computeFlow called the Terminal\'s way, bit for bit, on every candle of every stock', () => {
    let compared = 0;
    for (const f of FLOWS) {
      if (f.requires) { expect(code(() => resolveFlow({ kind: 'flow', metric: f.id }, 'f', { flow: FLOW_CTX }))!.code).toBe('METRIC_UNAVAILABLE'); continue }
      // the default parameters: the registry's (flowDefaults, the display-only levels aside), a built-in percentile
      // baseline capped to the window (K1): FL08, FL09 and FL21 at 60 - 1, FL37 at 60 - 20
      const p = resolveFlowParams(f, undefined, 'f', 60), d = flowDefaults(f.id);
      delete d.levels;
      const capped = { FL08: 59, FL09: 59, FL21: 59, FL37: 40 } as Record<string, number>;
      expect([f.id, p]).toEqual([f.id, capped[f.id] ? { ...d, baseline: capped[f.id] } : d]);
      // FL23 draws one line per broker: one broker's line, and the total of the default brokers
      // a sided indicator draws its sell line with side sell (its buy line at the default side buy)
      const refs: { output: string; params: Record<string, unknown> }[] = f.id === 'FL23' ? [{ output: 'lines', params: { brokers: ['YP'] } }, { output: 'total', params: { total: true } }]
        : f.outputs.map(o => ({ output: o.key, params: producedOutputs(f.id, p).includes(o.key) ? {} : { side: o.key } }));
      for (const x of refs) {
        const r = resolveFlow({ kind: 'flow', metric: f.id, output: x.output, params: x.params as never }, 'f', { flow: FLOW_CTX });
        const key = f.id === 'FL23' && x.output === 'lines' ? 'YP' : x.output;
        for (const id of WITH_DATA) {
          const s = STOCKS[id], T = terminal(s), want = computeFlow(f.id, T.ctx, terminalParams(f.id, (r.ref as any).params, T.candles[0]))[key];
          const got = r.full(tickerCalc(s.t));
          expect([f.id, x.output, id, want !== undefined]).toEqual([f.id, x.output, id, true]);
          const inWindow = Array.from(got).slice(T.lo, T.lo + T.candles.length), outside = [...Array.from(got).slice(0, T.lo), ...Array.from(got).slice(T.lo + T.candles.length)];
          expect([f.id, x.output, id, same(inWindow, want)]).toEqual([f.id, x.output, id, true]);
          expect(outside.every(v => v === null)).toBe(true);
          compared++;
        }
      }
    }
    expect(compared).toBeGreaterThan(47 * 4);
  });
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
    expect(R({ metric: 'FL23', output: 'total', params: { brokers: ['YP', 'AK', 'CC', 'DX', 'KK', 'LG'], total: true } })!.message).toMatch(/a list of 1 to 5 broker codes/);
    expect(R({ metric: 'FL01', params: { scope: 'selected', brokers: ['yp'] } })!.code).toBe('INVALID_CONDITION');
    expect(R({ metric: 'FL18', params: { anchor: 'last week' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.anchor' });
    expect(R({ metric: 'FL24', params: { nope: 1 } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.nope' });
  });
  it('refuses the kinds that only draw (levels, button, fixed) as condition parameters', () => {
    expect(R({ metric: 'FL24', params: { levels: '6, 10' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.levels' });
    expect(R({ metric: 'FL34', params: { reset: null } })!.message).toMatch(/only draws on the Terminal's chart/);
    expect(R({ metric: 'FL01', params: { ranking: 'daily' } })!.code).toBe('INVALID_CONDITION');
  });
  it('refuses an output the indicator does not give at its parameters (a side, FL23\'s lines and total), and selected brokers without a broker', () => {
    expect(R({ metric: 'FL24', output: 'buy' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.output', details: { allowed: ['value'] } });
    expect(R({ metric: 'FL01', output: 'sell' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.side' });
    expect(R({ metric: 'FL01', output: 'sell', params: { side: 'both' } })).toBe(null);
    expect(R({ metric: 'FL23' })!.message).toMatch(/name exactly one broker for output lines/);
    expect(R({ metric: 'FL23', output: 'total' })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.total' });
    expect(R({ metric: 'FL01', params: { scope: 'selected' } })).toMatchObject({ code: 'INVALID_CONDITION', field: 'definition.conditions[0].test.metric.params.brokers' });
    expect(R({ metric: 'FL46', params: { num_scope: 'selected' } })!.field).toBe('definition.conditions[0].test.metric.params.num_brokers');
  });
  it('an anchor date must lie inside the loaded broker window', () => {
    expect(R({ metric: 'FL18', params: { anchor: WINDOW[10] } })).toBe(null);
    expect(R({ metric: 'FL18', params: { anchor: '2026-01-02' } })!.message).toMatch(new RegExp(`outside the loaded broker window \\(${FIRST} to ${LAST}`));
  });
});

describe('depth (K1): derived from the indicator and the loaded window, never a hand list', () => {
  const at = (sessions: number): FlowBindContext => ({ ...FLOW_CTX, sessions });
  const bind = (test: Test, w = FLOW_CTX) => code(() => bindCondition({ id: 'a', enabled: true, test }, 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX, flow: w }));
  const fl24 = (window: number) => ({ kind: 'flow', metric: 'FL24', params: { window } }) as never;
  const pct = (of: unknown, length: number) => ({ kind: 'transform', fn: 'percentile', of, args: { length } }) as never;
  it('the indicator reads its window: FL24 window 10 reads 10 sessions, a percentile over a baseline window + baseline, an anchored line 1', () => {
    expect(indicatorDepth(FLOW_BY_ID.FL24, 'value', resolveFlowParams(FLOW_BY_ID.FL24, { window: 10 }, 'f'))).toBe(10);
    expect(indicatorDepth(FLOW_BY_ID.FL08, 'value', resolveFlowParams(FLOW_BY_ID.FL08, { window: 3, baseline: 30 }, 'f'))).toBe(33);
    expect(indicatorDepth(FLOW_BY_ID.FL33, 'buy', resolveFlowParams(FLOW_BY_ID.FL33, undefined, 'f'))).toBe(25);          // recent 5 + baseline 20
    expect(indicatorDepth(FLOW_BY_ID.FL18, 'value', resolveFlowParams(FLOW_BY_ID.FL18, undefined, 'f'))).toBe(1);
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
    // the retired Phase 2 entries: refused with their reason, never computed
    expect(code(() => resolveSeries({ kind: 'flow', metric: 'bandar', params: { window: 10 } } as never, 'f', { ...OPTS }))).toMatchObject({ code: 'METRIC_UNAVAILABLE', details: { metric: 'bandar' } });
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
