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
import type { Card, Outputs, TestCard, TickerBars } from './types.ts';
import type { PreviewDetail, SignalTrack } from '../core/contract.ts';
import { testReady, testWire } from '../grammar.ts';

/** a card as the wire condition a run sends (the one mapping of core/catalog.ts; a test card's is the Screener's) */
export const toWire = (c: Card): Condition => c.type === 'test' ? testWire(c as TestCard) : c.type === 'reg' ? regToCondition(c as RegCard) : legacyToCondition(c as LegacyCard);

/** Stage D (D6): the worker's tracks of one ticker (a preview's detail), as 0/1 series on its bars: each condition by
    its id, '__entry' and '__exit' the combined states */
type Tracks = Map<string, Uint8Array>;
interface Loaded { bars: TickerBars; calc: Calc; flow: FlowData | undefined; memo: Map<string, Uint8Array | null>; outs: Map<string, Outputs | null>; tracks?: Tracks }

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
  /** Stage D (D6): a preview's detail for the ticker (null forgets its tracks) */
  tracks(ticker: string, detail: PreviewDetail | null) {
    const t = this.tickers.get(ticker);
    if (!t) return;
    if (!detail || detail.ticker !== ticker || detail.error) { t.tracks = undefined; return }
    const N = t.bars.dates.length, at = detail.from === null ? -1 : t.bars.dates.indexOf(detail.from), m: Tracks = new Map();
    const series = (tr: SignalTrack) => { const s = new Uint8Array(N); if (at >= 0) for (let k = 0; k + 1 < tr.runs.length; k += 2) for (let j = tr.runs[k]; j <= tr.runs[k + 1]; j++) if (at + j < N) s[at + j] = 1; return s };
    for (const c of [...detail.conditions, ...detail.exit_conditions]) m.set(c.condition_id, series(c.track));
    m.set('__entry', series(detail.entry)); m.set('__exit', series(detail.exit));
    t.tracks = m;
  }
  /** the worker's combined entry or exit state for the ticker (null: no detail) */
  tracked(ticker: string, which: '__entry' | '__exit'): Uint8Array | null { return this.tickers.get(ticker)?.tracks?.get(which) ?? null }
  has(ticker: string, flow = false) { const t = this.tickers.get(ticker); return !!t && (!flow || !!t.flow) }
  get(ticker: string) { return this.tickers.get(ticker)?.bars }

  ready(card: Card): boolean {
    if (card.type === 'test') return testReady(card as TestCard);
    if (card.type === 'reg') { const r = BY_ID[(card as RegCard).ind]; return !!r && r.available_for_backtest }
    const spec = LEGACY[card.type];
    if (!spec) return false;
    // EXEC-BACKTEST-LOAD: before the catalog answers, a flow card counts as ready (its series waits for the broker data)
    return spec.group !== 'flow' || (this.catalog()?.flow.available ?? true);
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
    if (card.type === 'test') return t.tracks?.get(card.id) ?? null;     // the worker's (tracks), null until they are there
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
