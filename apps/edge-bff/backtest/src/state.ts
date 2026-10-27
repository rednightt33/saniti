/* The builder state (backtest.html section 4 · STATE). The defaults are the reference's S; the ones that depend on the
   published data (ticker, period) are set from the catalog at boot (applyCatalog). The reference's session trial
   counter S.trials is gone: the server counts trials per strategy line, and S.trials shows the last run's total. */
import { DEFAULT_ENTRY, ENTRY_TEMPLATES, EXIT_TEMPLATES as CORE_EXIT_TEMPLATES, legacyCard, type LegacyCard, type LegacyType } from './core/catalog.ts';
import type { Card } from './api/types.ts';
import type { PageResult } from './api/adapt.ts';
import { STOCKS, CAT } from './env.ts';
import { mkRegWith } from './reg.ts';
import { currentRequest, publishedThrough } from './api/request.ts';

/** the card the reference's mkCond builds: catalog defaults, then `over`, a random id */
export function mkCond(type: string, over: Record<string, unknown> = {}): LegacyCard {
  return legacyCard(type as LegacyType, Math.random().toString(36).slice(2,8), over);
}

export interface State {
  mode: 'single' | 'portfolio'; ticker: string; universe: string; maxPos: number; rankBy: 'adx' | 'fnet' | 'vol' | 'rsi';
  from: string; to: string; oos: number;
  logic: 'all' | 'any' | 'n'; atLeast: number; window: number;
  conds: Card[];
  exit: { stopMode: string; sl: number; slAtr: number; slRR: number; atrLen: number; stopLine: { id: string; o: string; p?: Record<string, unknown> };
          tpMode: string; tp: number; tpR: number; tpAtr: number; trailMode: string; trail: number; chLen: number; chK: number;
          trailLine: { id: string; o: string; p?: Record<string, unknown> }; hold: number };
  exitConds: Card[]; exitLogic: 'any' | 'all';
  size: { capital: number; alloc: number };
  cost: { buy: number; sell: number; slip: number; ara: boolean; minVal: number };
  sigTicker: string; bench: 'bh' | 'ihsg'; cmp: string[]; step: number; view: 'signals' | 'results'; stale: boolean;
  hidden: Record<string, boolean>; trials: number; result: PageResult | null; tab: string; heatMetric: string; running?: boolean;
}

export const S: State = {
  mode:'single', ticker:'MAPI', universe:'all', maxPos:5, rankBy:'adx',
  from:'2019-06-03', to:'2026-10-23', oos:30,
  logic:'n', atLeast:3, window:5,
  conds:DEFAULT_ENTRY.map(([t, over]) => mkCond(t, over as Record<string, unknown>)),
  exit:{stopMode:'pct', sl:7, slAtr:2, slRR:2, atrLen:14, stopLine:{id:'I09', o:'supertrend'}, tpMode:'pct', tp:15, tpR:2, tpAtr:3, trailMode:'none', trail:5, chLen:22, chK:3, trailLine:{id:'I01', o:'sma'}, hold:20}, exitConds:[], exitLogic:'any',
  size:{capital:100e6, alloc:100},
  cost:{buy:.15,sell:.25,slip:.05,ara:true,minVal:5},
  sigTicker:'MAPI', bench:'bh', cmp:[], step:2, view:'signals', stale:false, hidden:{}, trials:0, result:null, tab:'overview', heatMetric:'sharpe'
};

/** settings changes so far (markStale); a run compares it with the count at its start */
export const edits = { n: 0 };

/** the defaults that come from the published data: the reference's ticker MAPI when it is published (else the first
    stock), its start 2019-06-03 clipped to the first published day, the first catalog universe when 'all' is not
    one, and the end at the latest day every dataset the default strategy reads is published (the To field's max stays
    catalog.data_through: a later end for a flow strategy is the server's FLOW_DATA_THROUGH, shown by the toast) */
export function applyCatalog() {
  const stocks = STOCKS();
  S.ticker = stocks.includes('MAPI') ? 'MAPI' : stocks[0];
  S.sigTicker = S.ticker;
  if (S.from < CAT.first_date) S.from = CAT.first_date;
  if (!CAT.universes.some(u => u.id === S.universe) && CAT.universes.length) S.universe = CAT.universes[0].id;
  S.to = CAT.data_through;
  S.to = publishedThrough(currentRequest(), CAT);
}

/* quick-start templates (configuration in core/catalog.ts): entry templates replace the entry conditions */
export const TEMPLATES: Record<string, () => LegacyCard[]> = Object.fromEntries(Object.entries(ENTRY_TEMPLATES).map(([k, cards]) =>
  [k, () => cards.map(([t, over]) => mkCond(t, over as Record<string, unknown>))]));
/* exit templates add one exit condition */
export const EXIT_TEMPLATES: Record<string, () => Card[]> = Object.fromEntries(Object.entries(CORE_EXIT_TEMPLATES).map(([k, x]) =>
  [k, () => [x.kind === 'reg' ? mkRegWith(x.ind, { ...(x.p ? { p:x.p } : {}), lhs:x.lhs, op:x.op, rhs:x.rhs }) : mkCond(x.type, x.over as Record<string, unknown>)]]));
