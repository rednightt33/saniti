/* The page's own logic outside the DOM: the request built from the builder state (api/request.ts), the adapter from
   the server's result to the renderers' shape (api/adapt.ts) and the preview calculations (api/compute.ts). */
import { describe, expect, it } from 'vitest';
import type { BacktestRequest } from '../src/core/contract.ts';
import { legacyCard, legacyToCondition, type RegCard } from '../src/core/catalog.ts';
import { Calc, conditionSeries } from '../src/core/conditions.ts';
import { buildRequest, ARA_GAP, MC_SEED } from '../src/api/request.ts';
import { adaptResult, WHY } from '../src/api/adapt.ts';
import { Compute, toBars } from '../src/api/compute.ts';
import type { Card } from '../src/api/types.ts';
import { S, type State } from '../src/state.ts';
import { resultOf, stubApi } from './smoke/stub.ts';

const clone = (): State => JSON.parse(JSON.stringify(S));
const ready = (c: Card) => c.type === 'reg' || !['fnet', 'broker', 'top5'].includes(c.type);

describe('request (api/request.ts)', () => {
  it('maps the builder state to the wire units', () => {
    const s = clone(); s.ticker = 'MAPI'; s.from = '2019-06-03'; s.to = '2022-12-30';
    const q = buildRequest(s, { ready, monteCarloRuns:1000 });
    expect(q.mode).toBe('single');
    expect(q.single).toEqual({ ticker:'MAPI', benchmark:'buy_and_hold' });
    expect(q.portfolio).toBeUndefined();
    expect(q.period).toEqual({ from:'2019-06-03', to:'2022-12-30', oos_fraction:.3 });
    expect(q.entry.logic).toBe('at_least');
    expect(q.entry.at_least).toBe(3); expect(q.entry.window_bars).toBe(5);
    // the two flow cards of the default entry are left out (not calculated), the three others go as wire conditions
    expect(q.entry.conditions.map(c => c.kind)).toEqual(['indicator', 'indicator', 'price_action']);
    expect(q.exit.stop).toMatchObject({ mode:'pct', pct:.07, atr_mult:2, reward_risk_x:2, line:{ indicator:'I09', output:'supertrend' } });
    expect(q.exit.take_profit).toMatchObject({ mode:'pct', pct:.15 });
    expect(q.exit.trailing.mode).toBe('none');
    expect(q.exit.max_hold_bars).toBe(20);
    expect(q.sizing).toEqual({ capital_idr:100e6, allocation_fraction:1 });
    expect(q.costs).toEqual({ buy_fee:.0015, sell_fee:.0025, slippage:.0005, skip_ara_open_gap:true, ara_gap_fraction:ARA_GAP });
    expect(q.robustness).toEqual({ monte_carlo_runs:1000, seed:MC_SEED, sensitivity:true });
  });
  it('portfolio, IHSG benchmark and the chandelier trail', () => {
    const s = clone(); s.mode = 'portfolio'; s.tickers = ['BBRI', 'BBCA']; s.maxPos = 3; s.rankBy = 'rsi'; s.cost.minVal = 2.5;
    s.exit.trailMode = 'chand'; s.logic = 'any'; s.bench = 'ihsg';
    const q = buildRequest(s, { ready, monteCarloRuns:0 });
    expect(q.single).toBeUndefined();
    // the picked stocks in the order they were picked (PF1; the worker sorts them, PF3), never a universe
    expect(q.portfolio).toEqual({ tickers:['BBRI', 'BBCA'], max_positions:3, rank_by:'rsi', min_avg_value_20d_idr:2.5e9 });
    expect(q.portfolio!.tickers).not.toBe(s.tickers);
    expect(q.exit.trailing.mode).toBe('chandelier');
    expect(q.entry.logic).toBe('any');
    const s2 = clone(); s2.bench = 'ihsg';
    expect(buildRequest(s2, { ready, monteCarloRuns:0 }).single!.benchmark).toBe('ihsg');
  });
});

describe('adapter (api/adapt.ts)', () => {
  const s = clone(); s.from = '2019-06-03'; s.to = '2022-12-30';
  const q: BacktestRequest = buildRequest(s, { ready, monteCarloRuns:1000 });
  const res = resultOf(q, 3), R = adaptResult('job-1', res, q, s.conds);
  it('keeps the calendar and puts trades on it', () => {
    expect(R.days).toBe(res.dates);
    expect(R.eq.length).toBe(res.dates.length);
    expect(R.eq[5]).toEqual([5, res.equity[5]]);
    R.trades.forEach((t, k) => {
      const w = res.trades[k];
      expect(R.days[t.ei]).toBe(w.entry_date); expect(R.days[t.xi]).toBe(w.exit_date);
      expect(t.why).toBe(WHY[w.exit_reason]); expect(t.sh).toBe(w.shares);
    });
  });
  it('maps the statistics, the grid and the run meta', () => {
    expect(R.st.tot).toBe(res.stats.all.total_return);
    expect(R.st.r).toBe(res.daily_returns); expect(R.st.dd).toBe(res.drawdown);
    expect(R.st.psr(0)).toBe(res.stats.all.psr_0);
    expect(R.cap0).toBe(100e6);
    expect(R.ms).toBe(res.meta.duration_ms); expect(R.trials).toBe(res.meta.trials.total);
    expect(R.cut).toBe(res.oos.cut); expect(R.cutDay).toBe(res.oos.cut - 1);
    expect(R.grid && R.grid.yk.k).toBe('sl');
    expect(R.grid!.cells.length).toBe(5);
    expect(R.grid!.xs).toEqual(res.robustness.sensitivity!.xs_display);
    expect((R.grid!.cond as any).val).toBe(25);                 // the ADX card's own value, display units
    expect(R.ev.entries.MAPI).toBe(res.events.entries.MAPI);
    expect(R.ev.cond.get('MAPI')!.size).toBe(3);
  });
  it('reads an infinite profit factor and a null deflated Sharpe as the reference does', () => {
    const r2 = JSON.parse(JSON.stringify(res));
    r2.trade_stats.all.profit_factor = 'inf'; r2.robustness.deflated.dsr = null;
    const A = adaptResult('job-2', r2, q, s.conds);
    expect(A.ts.pf).toBe(Infinity); expect(Number.isNaN(A.ds.dsr)).toBe(true);
  });
});

describe('preview calculations (api/compute.ts)', () => {
  const api = stubApi();
  it('gives the core condition series for a card, null where it cannot be calculated', async () => {
    const b = await api.bars('MAPI');
    const card = legacyCard('rsi', 'r1', { op:'lt', val:40 });
    const want = conditionSeries(new Calc(toBars(b)), legacyToCondition(card) as Parameters<typeof conditionSeries>[1]);
    expect(Array.from(api.conditionSeries('MAPI', card)!)).toEqual(Array.from(want));
    expect(api.conditionSeries('MAPI', legacyCard('fnet', 'f1'))).toBeNull();          // flow not available in the catalog
    expect(api.ready(legacyCard('fnet', 'f1'))).toBe(false);
    expect(api.conditionSeries('BBCA', card)).toBeNull();                              // not loaded
    const bad = legacyCard('rsi', 'r2', { len:0 });                                    // refused input: an empty series
    expect(Array.from(api.conditionSeries('MAPI', bad)!).every(x => x === 0)).toBe(true);
  });
  it('gives registry outputs with NaN for missing values', async () => {
    const n = (await api.bars('MAPI')).dates.length;
    const o = api.indicatorOutputs('MAPI', 'I13', { length:14, source:'close' })!;
    expect(o.rsi.length).toBe(n);
    expect(Number.isNaN(o.rsi[0])).toBe(true);
    expect(o.rsi[100]).toBeGreaterThan(0);
    const reg: RegCard = { id:'g1', type:'reg', on:true, ind:'I13', p:{ length:14, source:'close' }, lhs:{ t:'out', o:'rsi' }, op:'lt', rhs:{ t:'val', v:30 } };
    expect(api.ready(reg)).toBe(true);
    expect(api.conditionSeries('MAPI', reg)!.length).toBe(o.rsi.length);
  });
  it('does not need the page state', () => {
    const c = new Compute(() => null);
    // EXEC-BACKTEST-LOAD: before the catalog answers a flow card counts as ready (its series waits for the broker data);
    // a catalog that turns flow off makes it not ready
    expect(c.ready(legacyCard('broker', 'b1'))).toBe(true);
    expect(c.ready(legacyCard('adx', 'a1'))).toBe(true);
    const off = new Compute(() => ({ flow: { available: false } }) as any);
    expect(off.ready(legacyCard('broker', 'b1'))).toBe(false);
  });
});
