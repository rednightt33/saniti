/* EXEC-SCREENER-FLOW-CANDLES P5b (verification/screener/P5_FLOW.md section 3): the Screener's versions of flow
   indicators and its own flow entries, on the fixture of tests/core/flow-fixture.ts, each against the Terminal's way or
   a brute-force recomputation from the raw rows:
   - the anchor N sessions back (FL18, FL19, FL20, FL44, FL45; decisions D, E): at every candle s, computeFlow on the
     Terminal's context of the candles up to s (flowRows of the rows on those dates) with the anchor date of candle s - N;
   - FL23's series a, b, c, Top-K holders, lookback L and the count of holders that moved (decision B): FL23 computeFlow
     on the same context per broker with its start at candle s - L + 1, ranked, summed and counted by hand; the traded
     value from the raw rows;
   - fnet (old FL01): the foreign rows summed by hand; FL34's point-in-time guard; ksei_net REQUIRES_DATA. */
import { describe, expect, it } from 'vitest';
import { computeFlow, flowRows } from '../../../terminal/src/calc/flow.ts';
import type { FlowContext } from '../../../terminal/src/calc/flow.ts';
import type { Definition, Test } from '../../src/core/contract.ts';
import { FLOW_REASONS } from '../../src/core/catalog.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { round12 } from '../../src/core/evaluate.ts';
import { FLOW_BY_ID, resolveFlow } from '../../src/core/flowmetrics.ts';
import { sliceContext, topHolders } from '../../src/core/flowscreener.ts';
import { tickerCalc } from '../../src/core/metrics.ts';
import { runScreen } from '../../src/core/screen.ts';
import { CLASS, E, FLOW_CTX, LAST, PRICE_BARS, STOCKS, WITH_DATA, code, same, stock, terminal } from './flow-fixture.ts';
import type { Stock } from './flow-fixture.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rowOf, synth } from './helpers.ts';

type S = (number | null)[];
/** The Terminal's context of a stock's candles 0..s (its price bars inside the window up to s): flowRows on the rows of
    those dates only, as the Terminal builds it when its last candle is s. */
function upTo(st: Stock, s: number): FlowContext {
  const T = terminal(st), cs = T.candles.slice(0, s + 1), at = new Map(cs.map((d, k) => [d, k]));
  return { rows: flowRows(st.rows, cs.length, d => at.get(d) ?? -1), dates: cs, close: T.ctx.close.slice(0, s + 1), volume: T.ctx.volume.slice(0, s + 1), insider: [], classification: CLASS };
}
/** The screener's series of a reference on a stock's window candles (resolveFlow on its bars, cut to the window). */
function mine(st: Stock, ref: Record<string, unknown>): S {
  const T = terminal(st), r = resolveFlow({ kind: 'flow', ...ref } as never, 'f', { flow: FLOW_CTX });
  return Array.from(r.full(tickerCalc(st.t))).slice(T.lo, T.lo + T.candles.length) as S;
}
const firstWithData = (st: Stock) => { const R = terminal(st).ctx.rows; for (let t = 0; t < R.N; t++) if (R.has[t]) return t; return R.N };
const near = (a: number | null, b: number | null) => a === b || (a !== null && b !== null && Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(a), Math.abs(b)));

describe('sliceContext equals flowRows on the rows of the same candles', () => {
  it('field for field, for windows across every stock (a candle without broker data inside, a Nego-only day)', () => {
    for (const id of WITH_DATA) {
      const st = STOCKS[id], T = terminal(st);
      for (const [lo, hi] of [[0, 59], [3, 17], [30, 59], [37, 37], [58, 59]] as const) {
        if (hi >= T.candles.length) continue;
        const cs = T.candles.slice(lo, hi + 1), at = new Map(cs.map((d, k) => [d, k]));
        const want = flowRows(st.rows, cs.length, d => at.get(d) ?? -1), got = sliceContext(T.ctx, lo, hi);
        expect([id, lo, got.rows.n, got.rows.N, got.rows.brokers, got.dates]).toEqual([id, lo, want.n, want.N, want.brokers, cs]);
        for (const k of ['t', 'b', 'inv', 'brd', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf', 'has'] as const) expect([id, lo, k, same(got.rows[k], want[k])]).toEqual([id, lo, k, true]);
      }
    }
  });
});

describe('the anchor N sessions back (FL18, FL19, FL20, FL44, FL45; decisions D, E)', () => {
  it('equals computeFlow on the candles up to each session with the anchor N sessions before it, bit for bit; missing before N sessions of data', () => {
    let compared = 0, values = 0;
    for (const id of ['FL18', 'FL19', 'FL20', 'FL44', 'FL45']) for (const [n, extra] of [[20, {}], [1, {}], [7, { scope: 'selected', brokers: ['YP', 'AK'] }], [12, { boards: ['Regular', 'Nego', 'Cash'], top: 2 }]] as const) {
      const ref = { metric: id, params: { anchor_sessions: n, ...extra } }, params = (resolveFlow({ kind: 'flow', ...ref } as never, 'f', { flow: FLOW_CTX }).ref as any).params;
      const { anchor_sessions: _n, ...terminalParams } = params;
      for (const sid of WITH_DATA) {
        const st = STOCKS[sid], T = terminal(st), got = mine(st, ref), first = firstWithData(st);
        for (let s = 0; s < T.candles.length; s++) {
          const want = s - n < first || !T.ctx.rows.has[s] ? null : computeFlow(id, upTo(st, s), { ...terminalParams, anchor: T.candles[s - n] }).value[s];
          expect([id, n, sid, s, Object.is(got[s], want)]).toEqual([id, n, sid, s, true]);
          compared++; if (want !== null) values++;
        }
      }
    }
    expect([compared > 4000, values > 2000]).toEqual([true, true]);
  });
  it('ranks the frozen Top-N cohort on the sessions up to the evaluated one only (no look-ahead): a later session does not change an earlier value', () => {
    const st = STOCKS.AAAA, all = mine(st, { metric: 'FL18', params: { anchor_sessions: 10 } }), T = terminal(st);
    // the Terminal's own anchored line over the whole window ranks its cohort to the last candle: it differs somewhere
    const whole = computeFlow('FL18', T.ctx, { anchor: T.candles[20] }).value;
    expect(all[30]).toBe(computeFlow('FL18', upTo(st, 30), { anchor: T.candles[20] }).value[30]);
    expect(whole.slice(21, 59).some((v, k) => v !== mine(st, { metric: 'FL18', params: { anchor_sessions: k + 1 } })[21 + k])).toBe(true);
  });
});

describe('the anchored series is computed only where a screen reads it (P5b cost)', () => {
  const ANCH = ['FL18', 'FL19', 'FL20', 'FL44', 'FL45'];
  it('resolved under a reach R, it holds the full series\' value on the last R + 1 sessions (to the last with broker data), and the full series\' first value when one of them has none', () => {
    for (const id of ANCH) for (const [n, reach, extra] of [[20, 0, {}], [5, 7, {}], [1, 30, { scope: 'selected', brokers: ['YP'] }], [12, 59, { boards: ['Nego'] }]] as const) {
      const ref = { kind: 'flow', metric: id, params: { anchor_sessions: n, ...extra } } as never;
      const full = resolveFlow(ref, 'f', { flow: FLOW_CTX }), lazy = resolveFlow(ref, 'f', { flow: FLOW_CTX, flowReach: reach });
      expect(lazy.key).not.toBe(full.key);                                   // its own cache entry
      expect(lazy.ref).toEqual(full.ref);                                    // the same condition
      for (const sid of WITH_DATA) {
        const st = STOCKS[sid], T = terminal(st), f = Array.from(full.full(tickerCalc(st.t))), z = Array.from(lazy.full(tickerCalc(st.t)));
        let last = T.candles.length - 1; while (!T.ctx.rows.has[last]) last--;
        const firstF = f.findIndex(v => typeof v === 'number'), gap = f.slice(T.lo + last - reach, T.lo + last + 1).some((v, k) => v === null && T.ctx.rows.has[last - reach + k]);
        for (let i = 0; i < f.length; i++) {
          const k = i - T.lo, read = k >= last - reach && k <= last;
          expect([id, n, reach, sid, i, z[i]]).toEqual([id, n, reach, sid, i, read || (gap && i === firstF) ? f[i] : null]);
        }
      }
    }
  });
  const fresh = () => Object.fromEntries(WITH_DATA.map(id => [id, stock(id, ({ AAAA: 11, BBBB: 12, CCCC: 13, EEEE: 15 } as Record<string, number>)[id], STOCKS[id].rows, id === 'BBBB' ? [LAST] : [])]));
  const screenOn = (stocks: Record<string, Stock>, test: Test) => runScreen({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all',
    conditions: [{ id: 'a', enabled: true, test }] } as Definition, memoryEnv(Object.values(stocks).map(s => s.t), synth('IHSG', 2, PRICE_BARS, '2026-07-01'), Object.values(stocks).map(s => rowOf(s.t, E)), E, { flow: FLOW_CTX }), { exhaustive: true });
  it('a screen\'s cells equal the full computation\'s, test by test: a value, a cross within 3, K of N, a streak, local operators, a percentile, a moving average (the whole history)', () => {
    const A = (n: number, p: Record<string, unknown> = {}) => ({ kind: 'flow', metric: 'FL20', params: { anchor_sessions: n, ...p } });
    const tests: Test[] = [
      { kind: 'value', metric: A(20) as never, op: 'gt', value: 0 },
      { kind: 'event', within: 3, signal: { lhs: A(10) as never, op: 'crosses_above', rhs: { value: 0 } } },
      { kind: 'window', mode: 'at_least', length: 8, count: 3, test: { kind: 'value', metric: A(15) as never, op: 'lt', value: 0 } },
      { kind: 'window', mode: 'streak', length: 3, test: { kind: 'value', metric: A(5, { scope: 'selected', brokers: ['YP', 'AK'] }) as never, op: 'gt', value: -5 } },
      { kind: 'value', metric: { kind: 'transform', fn: 'change', of: A(10), args: { bars: 5 } } as never, op: 'gt', value: 0 },
      { kind: 'value', metric: { kind: 'transform', fn: 'slope', of: { kind: 'transform', fn: 'lag', of: A(8), args: { bars: 2 } }, args: { length: 6 } } as never, op: 'gt', value: 0 },
      { kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: A(10), args: { length: 20 } } as never, op: 'ge', value: 50 },
      { kind: 'value', metric: { kind: 'transform', fn: 'vs_average', of: A(10), args: { ma: 'EMA', length: 5, form: 'difference' } } as never, op: 'gt', value: 0 },
      { kind: 'value', metric: { kind: 'rank', of: A(12) } as never, op: 'ge', value: 0 },
      { kind: 'state', lhs: { kind: 'price', field: 'close' } as never, op: 'gt', rhs: { kind: 'flow', metric: 'FL18', params: { anchor_sessions: 9 } } as never },
    ];
    let cells = 0;
    for (const test of tests) {
      const r = screenOn(fresh(), test), b = bindCondition({ id: 'a', enabled: true, test }, 'c', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX });
      const env = memoryEnv(Object.values(STOCKS).map(s => s.t), synth('IHSG', 2, PRICE_BARS, '2026-07-01'), Object.values(STOCKS).map(s => rowOf(s.t, E)), E, { flow: FLOW_CTX });
      for (const sid of WITH_DATA) {
        const got = r.rows.find(x => x.ticker === sid)?.cells[0];
        if (test.kind === 'value' && (test.metric as { kind: string }).kind === 'rank') { if (got) cells++; continue }   // its population: the screen's own (checked above)
        const t = env.bars(sid)!, want = b.evaluate({ ticker: sid, dates: t.dates, bars: t.bars as never, at: t.dates.length - 1, row: rowOf(t, E), ihsgCalendar: [], series: x => env.series(x, t), xsection: () => null }).cell;
        // a row is shown when it passes (the screen's ALL logic, exhaustive): its cell equals the full computation's
        if (got) { expect([JSON.stringify(test).slice(0, 60), sid, got]).toEqual([JSON.stringify(test).slice(0, 60), sid, want]); cells++ } else expect(want.status).not.toBe('pass');
      }
    }
    expect(cells).toBeGreaterThan(8);
  });
  it('a value test computes one anchored session per stock (its last with broker data); a cross within 3 four; the full series every session', () => {
    const perCandle = (stocks: Record<string, Stock>) => Object.fromEntries(Object.entries(stocks).map(([id, s]) => [id, [...(s.t.flow!.memo as Map<string, unknown>).keys()].filter(k => JSON.parse(k).length === 5).length]));
    const A = { kind: 'flow', metric: 'FL20', params: { anchor_sessions: 20 } } as never;
    const one = fresh(); screenOn(one, { kind: 'value', metric: A, op: 'gt', value: -1e12 });
    expect(perCandle(one)).toEqual({ AAAA: 1, BBBB: 1, CCCC: 1, EEEE: 1 });
    const cross = fresh(); screenOn(cross, { kind: 'event', within: 3, signal: { lhs: A, op: 'crosses_above', rhs: { value: 0 } } });
    expect(perCandle(cross)).toEqual({ AAAA: 4, BBBB: 4, CCCC: 4, EEEE: 4 });
    const all = fresh();
    for (const s of Object.values(all)) resolveFlow(A, 'f', { flow: FLOW_CTX }).full(tickerCalc(s.t));
    expect(perCandle(all)).toEqual(Object.fromEntries(WITH_DATA.map(id => [id, terminal(all[id]).candles.length])));
  });
});

/* ---- FL23 screener version ------------------------------------------------------------------------------------------ */

/** The Terminal's FL23 cumulative line of each broker from candle a to s (start = the date of candle a), on the
    Terminal's context up to s, read at s; and its daily net at s. */
function terminalInventory(st: Stock, s: number, a: number, codes: readonly string[], p: { unit: string; boards: string[]; investors: string[] }) {
  const ctx = upTo(st, s), base = { unit: p.unit, boards: p.boards, investors: p.investors, total: false };
  const cum = (b: string) => computeFlow('FL23', ctx, { ...base, brokers: [b], view: 'cum', start: ctx.dates[a] })[b][s] as number;
  const daily = (b: string) => computeFlow('FL23', ctx, { ...base, brokers: [b], view: 'daily' })[b][s] as number;
  return codes.map(b => ({ b, a: cum(b), d: daily(b) }));
}
/** Every investor's traded value (or lots) on the boards over candles a..s, summed from the raw rows. */
function tradedRaw(st: Stock, a: number, s: number, boards: string[], unit: string): number {
  const T = terminal(st), dates = new Set(T.candles.slice(a, s + 1)), ok = new Set(boards.map(b => b === 'Cash' ? 'Tunai' : b));
  let x = 0;
  for (const r of st.rows) if (dates.has(r.d) && ok.has(r.m)) x += unit === 'value' ? r.bv : r.bl;
  return x;
}

describe('FL23 screener version (decision B): series a, b, c, Top-K holders, lookback, the count of holders that moved', () => {
  it('series a and b of named brokers equal the Terminal\'s Broker Inventory (cumulative from the lookback\'s first session, and daily) summed in their order, bit for bit', () => {
    let values = 0;
    for (const [unit, L, boards] of [['lot', 20, ['Regular']], ['value', 5, ['Regular', 'Nego', 'Cash']], ['lot', 1, ['Nego']]] as const) {
      const p = { holders: 'selected', brokers: ['YP', 'AK', 'MG'], unit, lookback: L, boards: [...boards] };
      for (const sid of WITH_DATA) {
        const st = STOCKS[sid], T = terminal(st), first = firstWithData(st), a = mine(st, { metric: 'FL23', params: { ...p, series: 'cum' } }), b = mine(st, { metric: 'FL23', params: { ...p, series: 'daily' } });
        for (let s = 0; s < T.candles.length; s++) {
          const has = !!T.ctx.rows.has[s], from = s - L + 1;
          const inv = has ? terminalInventory(st, s, Math.max(from, 0), p.brokers, { unit, boards: [...boards], investors: ['Foreign', 'Domestic'] }) : [];
          const wantA = !has || from < first ? null : inv.reduce((x, y) => x + y.a, 0), wantB = has ? inv.reduce((x, y) => x + y.d, 0) : null;
          expect([unit, L, sid, s, Object.is(a[s], wantA), Object.is(b[s], wantB)]).toEqual([unit, L, sid, s, true, true]);
          if (wantA !== null) values++;
        }
      }
    }
    expect(values).toBeGreaterThan(300);
  });
  it('Top-K holders: the K brokers with the largest positive inventory over the lookback (ties by code); series c the holders\' inventory as a percent of the lookback\'s traded value; the count of holders that rose or fell by at least the amount', () => {
    let checked = 0, counted = 0;
    for (const [unit, L, K, series, move, X] of [['value', 10, 3, 'cum', 'up', 5e8], ['lot', 20, 5, 'norm', 'up', 2], ['value', 15, 2, 'daily', 'down', 0], ['lot', 8, 4, 'cum', 'up', 0]] as const) {
      const p = { holders: 'top', top: K, unit, lookback: L, series, move, move_min: X, boards: ['Regular'] };
      for (const sid of WITH_DATA) {
        const st = STOCKS[sid], T = terminal(st), first = firstWithData(st), v = mine(st, { metric: 'FL23', params: p }), c = mine(st, { metric: 'FL23', output: 'count', params: p });
        for (let s = 0; s < T.candles.length; s++) {
          const from = s - L + 1;
          if (!T.ctx.rows.has[s] || from < first) { expect([sid, s, v[s], c[s]]).toEqual([sid, s, null, null]); continue }
          const inv = terminalInventory(st, s, from, T.ctx.rows.brokers, { unit, boards: ['Regular'], investors: ['Foreign', 'Domestic'] });
          const H = inv.filter(x => x.a > 0).sort((x, y) => y.a - x.a || (x.b < y.b ? -1 : 1)).slice(0, K);
          const TV = tradedRaw(st, from, s, ['Regular'], unit);
          const x = (h: { a: number; d: number }) => series === 'daily' ? h.d : series === 'cum' ? h.a : 100 * h.a / TV;
          const sum = H.reduce((z, h) => z + (series === 'daily' ? h.d : h.a), 0), want = !H.length ? null : series === 'norm' ? 100 * sum / TV : sum;
          const n = H.filter(h => move === 'up' ? x(h) > 0 && x(h) >= X : x(h) < 0 && x(h) <= -X).length;
          // a and b bit for bit (the same nets added in the same order); c within rounding (the traded value summed row by row here)
          expect([sid, s, series === 'norm' ? near(v[s], want) : Object.is(v[s], want), H.length ? c[s] : null]).toEqual([sid, s, true, H.length ? n : null]);
          checked++; if (n > 0) counted++;
        }
      }
    }
    expect([checked > 600, counted > 50]).toEqual([true, true]);
    expect(topHolders(['BK', 'AK', 'CC', 'DX'], [5, 5, -1, 7], 3)).toEqual([3, 1, 0]);     // 7 first, the tie 5 by code AK before BK, no negative
  });
  it('holders all: every broker of the window, the count of brokers whose net over the lookback rose (fell) by at least the amount; "=" is offered on the count (K7, a number of brokers)', () => {
    const p = { holders: 'all', unit: 'value', lookback: 5, series: 'cum', move: 'down', move_min: 1e8, boards: ['Regular', 'Nego', 'Cash'] };
    let seen = 0;
    for (const sid of WITH_DATA) {
      const st = STOCKS[sid], T = terminal(st), first = firstWithData(st), c = mine(st, { metric: 'FL23', output: 'count', params: p });
      for (let s = 0; s < T.candles.length; s++) {
        const from = s - 4;
        if (!T.ctx.rows.has[s] || from < first) continue;
        const inv = terminalInventory(st, s, from, T.ctx.rows.brokers, { unit: 'value', boards: p.boards, investors: ['Foreign', 'Domestic'] });
        expect([sid, s, c[s]]).toEqual([sid, s, inv.filter(x => x.a < 0 && x.a <= -1e8).length]);
        seen++;
      }
    }
    expect(seen).toBeGreaterThan(150);
    const bind = (test: Test) => code(() => bindCondition({ id: 'a', enabled: true, test }, 'definition.conditions[0]', { ...OPTS, withinMax: WITHIN_MAX, flow: FLOW_CTX }));
    expect(bind({ kind: 'value', metric: { kind: 'flow', metric: 'FL23', output: 'count', params: p } as never, op: 'ge', value: 3 })).toBe(null);
    expect(bind({ kind: 'value', metric: { kind: 'flow', metric: 'FL23', output: 'count', params: p } as never, op: 'eq', value: 3 })).toBe(null);
    expect(bind({ kind: 'value', metric: { kind: 'flow', metric: 'FL23', params: p } as never, op: 'eq', value: 3 })!.code).toBe('INVALID_CONDITION');
    // the series take the operators of their kind: a rupiah amount a percentile of its own history, series c a rank
    expect(bind({ kind: 'value', metric: { kind: 'transform', fn: 'percentile', of: { kind: 'flow', metric: 'FL23', params: { lookback: 10 } }, args: { length: 20 } } as never, op: 'ge', value: 90 })).toBe(null);
    expect(bind({ kind: 'value', metric: { kind: 'rank', of: { kind: 'flow', metric: 'FL23', params: { series: 'norm' } } } as never, op: 'ge', value: 90 })).toBe(null);
  });
  it('the unit and kind follow the series and the unit: lots or rupiah (an amount) for a and b, a percent for c, a broker count for the count', () => {
    const at = (params: Record<string, unknown>, output = 'value') => { const r = resolveFlow({ kind: 'flow', metric: 'FL23', output, params } as never, 'f', { flow: FLOW_CTX }); return [r.unit, r.outputKind, !!r.integer] };
    expect(at({})).toEqual(['lot', 'Rp', false]);
    expect(at({ unit: 'value', series: 'daily' })).toEqual(['IDR', 'Rp', false]);
    expect(at({ series: 'norm' })).toEqual(['%', 'K', false]);
    expect(at({}, 'count')).toEqual(['brokers', 'B', true]);
  });
});

/* ---- fnet, FL34's guard, ksei_net ---------------------------------------------------------------------------------- */

describe('fnet (old FL01): the foreign net in rupiah over D sessions, from the broker rows', () => {
  it('equals the brute-force sum of buy minus sell value of the Foreign rows on the boards over the D sessions, bit for bit; missing before D sessions of data', () => {
    let values = 0;
    for (const [D, boards] of [[20, ['Regular', 'Nego', 'Cash']], [1, ['Regular', 'Nego', 'Cash']], [7, ['Regular']], [60, ['Nego', 'Cash']]] as const) {
      for (const sid of WITH_DATA) {
        const st = STOCKS[sid], T = terminal(st), first = firstWithData(st), got = mine(st, { metric: 'fnet', params: { window: D, boards: [...boards] } });
        const ok = new Set(boards.map(b => b === 'Cash' ? 'Tunai' : b));
        for (let s = 0; s < T.candles.length; s++) {
          let want: number | null = null;
          if (T.ctx.rows.has[s] && s - D + 1 >= first) {
            const dates = new Set(T.candles.slice(s - D + 1, s + 1));
            let buy = 0, sell = 0;
            for (const r of st.rows) if (dates.has(r.d) && r.i === 'Foreign' && ok.has(r.m)) { buy += r.bv; sell += r.sv }
            want = buy - sell;
          }
          expect([D, sid, s, got[s]]).toEqual([D, sid, s, want]);
          if (want !== null) values++;
        }
      }
    }
    expect(values).toBeGreaterThan(300);
    expect(resolveFlow({ kind: 'flow', metric: 'fnet' }, 'f', { flow: FLOW_CTX }).ref).toEqual({ kind: 'flow', metric: 'fnet', output: 'value', params: { window: 20, boards: ['Regular', 'Nego', 'Cash'] } });
  });
});

describe('FL34\'s point-in-time guard (old FL19): today\'s classification, so read at the last broker date only', () => {
  const INDEX = synth('IHSG', 2, PRICE_BARS, '2026-07-01'), ROWS = Object.values(STOCKS).map(s => rowOf(s.t, E));
  const screen = (test: Test) => runScreen({ universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null, traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all',
    conditions: [{ id: 'a', enabled: true, test }] } as Definition, memoryEnv(Object.values(STOCKS).map(s => s.t), INDEX, ROWS, E, { flow: FLOW_CTX }), { exhaustive: true });
  it('the value is the Terminal\'s on the last date of the loaded window, missing on every earlier one; a stock whose last broker session is earlier is n/a; an operator over its history is n/a', () => {
    for (const sid of WITH_DATA) {
      const st = STOCKS[sid], T = terminal(st), got = mine(st, { metric: 'FL34' }), want = computeFlow('FL34', T.ctx, { inst: 'class:Institutional-heavy', retail: 'class:Retail-heavy' }).value;
      for (let s = 0; s < T.candles.length; s++) expect([sid, s, got[s]]).toEqual([sid, s, T.candles[s] === LAST ? want[s] : null]);
    }
    const r = screen({ kind: 'value', metric: { kind: 'flow', metric: 'FL34' } as never, op: 'gt', value: -1e9 });
    const cell = (t: string) => r.rows.find(x => x.ticker === t)?.cells[0];
    expect([cell('AAAA')?.status, cell('AAAA')?.eval_date]).toEqual(['pass', LAST]);
    expect(cell('BBBB')).toBeUndefined();                                             // its last broker day has no price bar
    expect(r.conditions[0].na).toBeGreaterThanOrEqual(2);
    const ch = screen({ kind: 'value', metric: { kind: 'transform', fn: 'change', of: { kind: 'flow', metric: 'FL34' }, args: { bars: 5 } } as never, op: 'gt', value: -1e9 });
    expect(ch.rows.length).toBe(0);
    expect(FLOW_BY_ID.FL34.misuse).toMatch(/read only at the latest broker date, and is n\/a on any earlier session/);
  });
});

describe('ksei_net (old FL20\'s major-holder part): REQUIRES_DATA until a KSEI file is published', () => {
  it('is refused with its reason, never computed', () => {
    const r = code(() => resolveFlow({ kind: 'flow', metric: 'ksei_net' }, 'f', { flow: FLOW_CTX }))!;
    expect([r.code, (r.details as any).availability, (r.details as any).reason]).toEqual(['METRIC_UNAVAILABLE', 'REQUIRES_DATA', FLOW_REASONS.ksei]);
  });
});
