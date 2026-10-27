/* The fixture's way back from the wire to the reference: a BacktestRequest (what the page sends, src/api/request.ts)
   as the reference's state S (backtest.html section 4), so the mock-up engine of mockup.js runs on exactly the settings
   the page sent. Display units come back from the wire's fractions and IDR with the inverse of the page's scale,
   rounded to 12 significant digits (0.07 x 100 is 7.000000000000001 in floating point; the page's own S holds 7).
   Conditions come back as the cards the reference evaluates:
   - price-action and flow conditions as their legacy cards (CATALOG dip, breakout, volspike, macross, macd, fnet,
     broker, top5);
   - an indicator condition with exactly the shape core/catalog.ts legacyToCondition gives a legacy card (adx, dmi,
     stoch, rsi, ma, bb) as that card, so the reference's own CATALOG formula runs;
   - any other indicator condition as a registry card (type 'reg', the reference's regEval), its parameters completed
     with the registry defaults (regDefaults).
   A registry card of the same shape as a legacy one (e.g. RSI from the workspace) becomes the legacy card: the two
   formulas give the same series (rsi(c) vs I13 on close, sma vs I01, adx vs I07); only bb's "back inside" (close >=
   band) and a registry I27 "crosses above lower" (close > band) differ, on a close exactly equal to the band. */
import type { BacktestRequest, Condition, LineRef, SignalsPreviewRequest } from '../../src/core/contract.ts';
import { DISPLAY } from '../../src/core/catalog.ts';
import type { Card } from '../../src/api/types.ts';
import { REG_BY } from '../../src/reg.ts';
import * as M from './mockup.js';

/** a wire number in the page's display unit (wire = display x scale) */
const disp = (v: number, scale: number) => +(v / scale).toPrecision(12);
const OP_BACK: Record<string, string> = { gt:'gt', lt:'lt', crosses_above:'ca', crosses_below:'cb' };
const keys = (p: object | undefined, want: string[]) => !!p && Object.keys(p).length === want.length && want.every(k => k in p);

/** the reference's card for a wire condition */
export function cardOf(c: Condition): Card {
  const id = c.id, on = c.enabled !== false;
  const card = (type: string, over: Record<string, unknown>) => ({ id, type, on, ...over }) as unknown as Card;
  if (c.kind === 'price_action') {
    const p = (c.params || {}) as Record<string, number>;
    switch (c.type) {
      case 'dip': return card('dip', { op:'lt', val:disp(c.value as number, DISPLAY.dip) });
      case 'breakout': return card('breakout', { op:'brk', len:p.length });
      case 'volspike': return card('volspike', { op:'gt', len:p.length, val:disp(c.value as number, DISPLAY.volspike) });
      case 'macross': return card('macross', { op:c.op === 'golden_cross' ? 'golden' : 'fabove', fast:p.fast_length, slow:p.slow_length });
      case 'macd': return card('macd', { op:c.op === 'bullish_divergence' ? 'bdiv' : c.op === 'crosses_above_signal' ? 'xsig' : 'hpos', fast:p.fast_length, slow:p.slow_length, sig:p.signal_length });
    }
  }
  if (c.kind === 'flow') {
    const val = disp(c.value, DISPLAY[c.type]);
    if (c.type === 'fnet') return card('fnet', { op:c.op, len:c.params.length, val });
    if (c.type === 'broker') return card('broker', { op:'gt', broker:c.params.broker, len:c.params.length, val });
    return card('top5', { op:'gt', len:c.params.length, val });
  }
  if (c.kind !== 'indicator') throw new Error(`fixture: unknown condition kind ${(c as Condition).kind}`);
  const p = (c.params || {}) as Record<string, any>, op = OP_BACK[c.op];
  const lhs = c.lhs.type === 'price' ? 'price' : c.lhs.output, rhs = c.rhs.type === 'value' ? 'value' : c.rhs.output;
  const v = c.rhs.type === 'value' ? c.rhs.value : undefined;
  if (c.indicator === 'I07' && keys(p, ['di_length', 'adx_smoothing']) && p.di_length === p.adx_smoothing) {
    if (lhs === 'adx' && rhs === 'value' && ['gt', 'lt', 'ca'].includes(op)) return card('adx', { op, len:p.di_length, val:v });
    if (lhs === 'plus_di' && rhs === 'minus_di' && (op === 'gt' || op === 'ca')) return card('dmi', { op:op === 'gt' ? 'plus' : 'pcross', len:p.di_length });
  }
  if (c.indicator === 'I15' && keys(p, ['k_length', 'smooth_k']) && lhs === 'k' && rhs === 'value') return card('stoch', { op, len:p.k_length, smooth:p.smooth_k, val:v });
  if (c.indicator === 'I13' && keys(p, ['length', 'source']) && p.source === 'close' && lhs === 'rsi' && rhs === 'value') return card('rsi', { op, len:p.length, val:v });
  if (c.indicator === 'I01' && keys(p, ['length', 'source']) && p.source === 'close' && lhs === 'price' && rhs === 'sma' && op !== 'cb')
    return card('ma', { op:op === 'gt' ? 'above' : op === 'lt' ? 'below' : 'xab', len:p.length });
  if (c.indicator === 'I27' && keys(p, ['length', 'std_dev', 'source']) && p.source === 'close' && lhs === 'price' && rhs === 'lower' && (op === 'lt' || op === 'ca'))
    return card('bb', { op:op === 'lt' ? 'blow' : 'bxin', len:p.length, k:p.std_dev });
  return card('reg', {
    ind:c.indicator, p:{ ...M.regDefaults(REG_BY[c.indicator]), ...p },
    lhs:c.lhs.type === 'price' ? { t:'price' } : { t:'out', o:c.lhs.output }, op,
    rhs:c.rhs.type === 'value' ? { t:'val', v:c.rhs.value } : { t:'out', o:c.rhs.output },
  });
}

const lineOf = (l: LineRef) => ({ id:l.indicator, o:l.output, ...(l.params ? { p:l.params } : {}) });
/** the reference's "Demo 10" (its ten tickers, universe ALL) and "Banks" (BANK) as picked stocks: the fixture's default
    portfolio and the set the visual harness picks for the reference's Banks */
export const DEMO_10: string[] = M.TICKERS.map((t: [string]) => t[0]);
export const BANKS: string[] = ['BBCA', 'BBRI', 'BMRI'];
/** the reference's universe for picked stocks: ALL for the Demo 10 set, BANK for the Banks set, in any order, so those
    two run exactly as the reference runs its universes; any other set as its list, in the reference's ticker order
    (the order the stocks were picked in does not matter, PF3) */
export const universeOf = (tickers: readonly string[]) => {
  const set = new Set(tickers), is = (l: string[]) => l.length === set.size && l.every(t => set.has(t));
  if (is(DEMO_10)) return 'ALL';
  if (is(BANKS)) return 'BANK';
  const unknown = tickers.filter(t => !DEMO_10.includes(t));
  if (unknown.length) throw new Error(`fixture: ${unknown.join(', ')} is not a ticker of the reference`);
  return DEMO_10.filter(t => set.has(t));
};

/** The reference's S for a request; `trials` = its session counter before the run (S.trials). */
export function stateOf(q: BacktestRequest, trials = 0): any {
  const e = q.exit, pf = q.portfolio;
  return {
    mode:q.mode, ticker:q.single ? q.single.ticker : 'MAPI', universe:pf ? universeOf(pf.tickers) : 'ALL', maxPos:pf ? pf.max_positions : 5, rankBy:pf ? pf.rank_by : 'adx',
    from:q.period.from, to:q.period.to, oos:Math.round(q.period.oos_fraction * 100),
    logic:q.entry.logic === 'at_least' ? 'n' : q.entry.logic, atLeast:q.entry.at_least, window:q.entry.window_bars,
    conds:q.entry.conditions.map(cardOf),
    exit:{ stopMode:e.stop.mode, sl:disp(e.stop.pct, .01), slAtr:e.stop.atr_mult, slRR:e.stop.reward_risk_x, atrLen:e.atr_length, stopLine:lineOf(e.stop.line),
      tpMode:e.take_profit.mode, tp:disp(e.take_profit.pct, .01), tpR:e.take_profit.r_multiple, tpAtr:e.take_profit.atr_mult,
      trailMode:e.trailing.mode === 'chandelier' ? 'chand' : e.trailing.mode, trail:disp(e.trailing.pct, .01), chLen:e.trailing.chandelier_length, chK:e.trailing.chandelier_mult,
      trailLine:lineOf(e.trailing.line), hold:e.max_hold_bars },
    exitConds:e.signals.conditions.map(cardOf), exitLogic:e.signals.logic,
    size:{ capital:q.sizing.capital_idr, alloc:disp(q.sizing.allocation_fraction, .01) },
    cost:{ buy:disp(q.costs.buy_fee, .01), sell:disp(q.costs.sell_fee, .01), slip:disp(q.costs.slippage, .01), ara:q.costs.skip_ara_open_gap,
      minVal:pf ? disp(pf.min_avg_value_20d_idr, 1e9) : 5 },
    sigTicker:q.single ? q.single.ticker : 'MAPI', bench:q.single && q.single.benchmark === 'ihsg' ? 'ihsg' : 'bh', cmp:[], hidden:{}, trials,
  };
}

/** The reference's S for the portfolio table's signal preview (only what signalsFor, inRange and universe read). */
export function previewStateOf(q: SignalsPreviewRequest): any {
  return { mode:'portfolio', universe:universeOf(q.tickers), from:q.period.from, to:q.period.to,
    logic:q.entry.logic === 'at_least' ? 'n' : q.entry.logic, atLeast:q.entry.at_least, window:q.entry.window_bars, conds:q.entry.conditions.map(cardOf), exitConds:[] };
}
