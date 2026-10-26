/* The synchronous half of a BacktestApi: calculations on the bars a ticker has loaded, with the shared core (the same
   registry formulas and condition semantics the worker runs). A card goes through the one card -> condition mapping
   (core/catalog.ts legacyToCondition / regToCondition), then conditions.ts on the ticker's Calc. The page's preview
   therefore draws the markers the run will execute (CONTRACT.md section 10). Pure: no DOM, no network. */
import type { Catalog, Condition } from '../core/contract.ts';
import type { FlowData } from '../core/flow.ts';
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import { isN } from '../../../terminal/src/calc/indicators.ts';
import { LEGACY, legacyToCondition, regToCondition, type LegacyCard, type RegCard } from '../core/catalog.ts';
import { Calc, conditionSeries } from '../core/conditions.ts';
import { BY_ID, ValidationError, resolveParams } from '../core/registry.ts';
import type { Card, Outputs, TickerBars } from './types.ts';

/** a card as the wire condition a run sends (the one mapping of core/catalog.ts) */
export const toWire = (c: Card): Condition => c.type === 'reg' ? regToCondition(c as RegCard) : legacyToCondition(c as LegacyCard);

interface Loaded { bars: TickerBars; calc: Calc; flow: FlowData | undefined; memo: Map<string, Uint8Array | null>; outs: Map<string, Outputs | null> }

/** the bars of the indicators module (bars.T = dates) from a ticker's TickerBars */
export const toBars = (b: TickerBars): Bars => ({ O:Array.from(b.o), H:Array.from(b.h), L:Array.from(b.l), C:Array.from(b.c), V:Array.from(b.v), T:b.dates });

export class Compute {
  private tickers = new Map<string, Loaded>();
  /** `catalog` is read for flow availability (flow cards are ready only while the catalog says the data is verified) */
  constructor(private catalog: () => Catalog | null) {}

  /** a ticker's bars as loaded (again: the Calc and the memos start over); flow when its broker data came with it */
  put(bars: TickerBars, flow?: FlowData, calcBars: Bars = toBars(bars)) {
    const prev = this.tickers.get(bars.ticker);
    const f = flow ?? (prev && prev.bars.dates.length === bars.dates.length ? prev.flow : undefined);
    this.tickers.set(bars.ticker, { bars, calc:new Calc(calcBars, f), flow:f, memo:new Map(), outs:new Map() });
  }
  has(ticker: string, flow = false) { const t = this.tickers.get(ticker); return !!t && (!flow || !!t.flow) }
  get(ticker: string) { return this.tickers.get(ticker)?.bars }

  ready(card: Card): boolean {
    if (card.type === 'reg') { const r = BY_ID[(card as RegCard).ind]; return !!r && r.available_for_backtest }
    const spec = LEGACY[card.type];
    if (!spec) return false;
    return spec.group !== 'flow' || !!this.catalog()?.flow.available;
  }

  indicatorOutputs(ticker: string, id: string, params: Record<string, unknown>): Outputs | null {
    const t = this.tickers.get(ticker), r = BY_ID[id];
    if (!t || !r || !r.available_for_backtest) return null;
    const key = id + JSON.stringify(params);
    if (t.outs.has(key)) return t.outs.get(key)!;
    let res: Outputs | null = null;
    try {
      // the card's parameters as a run sends them (not-accepted workbook fields dropped or refused), then the registry's
      const probe: RegCard = { id:'probe', type:'reg', on:true, ind:id, p:params, lhs:{ t:'price' }, op:'gt', rhs:{ t:'val', v:0 } };
      const out = t.calc.out(r.key, resolveParams(r, regToCondition(probe).params));
      res = {};
      for (const o of r.outputs) { const s = out[o] || [], a = new Float64Array(t.bars.dates.length); for (let i = 0; i < a.length; i++) a[i] = isN(s[i]) ? s[i] as number : NaN; res[o] = a }
    } catch (e) { if (!(e instanceof ValidationError)) throw e }
    t.outs.set(key, res);
    return res;
  }

  conditionSeries(ticker: string, card: Card): Uint8Array | null {
    const t = this.tickers.get(ticker);
    if (!t || !this.ready(card)) return null;
    const spec = card.type === 'reg' ? null : LEGACY[card.type];
    if (spec && spec.group === 'flow' && !t.flow) return null;
    let cond;
    try { cond = { ...toWire(card), enabled:true } } catch (e) { if (e instanceof ValidationError) return new Uint8Array(t.bars.dates.length); throw e }
    const key = JSON.stringify({ ...cond, id:'' });
    if (t.memo.has(key)) return t.memo.get(key)!;
    let s: Uint8Array;
    // conditions.ts names its own Condition union (page shapes); the wire conditions of contract.ts are the same objects
    try { s = conditionSeries(t.calc, cond as Parameters<typeof conditionSeries>[1], card.id) }
    catch (e) { if (!(e instanceof ValidationError)) throw e; s = new Uint8Array(t.bars.dates.length) }
    t.memo.set(key, s);
    return s;
  }
}
