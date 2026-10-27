/* The condition catalog and the indicator registry as the page shows them (backtest.html sections 3 and 8, without the
   demo formulas): the legacy cards are core/catalog.ts LEGACY (equal to the reference's CATALOG without `eval`), the
   registry is the Terminal's indRegistry.json (the reference's REG: 53 indicators, 126 parameters, the same values under
   the Terminal's field names, mapped here to the names the page reads). Every series comes from the BacktestApi. */
import IND_REG from '../../terminal/src/data/indRegistry.json' with { type: 'json' };
import { EXTRA_GROUPS as CORE_EXTRA, LEGACY, type LegacySpec, type RegCard } from './core/catalog.ts';
import type { Card } from './api/types.ts';
import { API, CAT, DATA } from './env.ts';
import { nf, OPS, toast } from './format.ts';
import { S } from './state.ts';

/* ---- INDICATOR REGISTRY (the reference's REG) ---- */
export interface RegParam { k: string; l: string; cls: string; t: string; ev: string; min?: number; max?: number; step?: number; m?: string; d?: any; opt?: string[]; note?: string }
export interface RegRow { id: string; cat: string; name: string; key: string; data: string; zone: string; out: string[]; short: string; detail: string; disp: string; p: RegParam[] }

/* indRegistry.json → the reference's REG: req → data, outs[].k → out, tip → short, info → detail, display → disp;
   per parameter label → l, type → t, hint → m, def → d, opts → opt, and cls 'Fixed' for a fixed parameter (else
   'Calculation'), which is what the reference's 02_PARAMETERS class column holds */
export const REG: RegRow[] = (IND_REG as any[]).map(r => ({
  id:r.id, cat:r.cat, name:r.name, key:r.key, data:r.req, zone:r.zone, out:r.outs.map((o: any) => o.k), short:r.tip, detail:r.info, disp:r.display,
  p:r.params.map((q: any) => ({ k:q.k, l:q.label, cls:q.type==='fixed'?'Fixed':'Calculation', t:q.type, ev:q.ev, min:q.min, max:q.max, step:q.step, m:q.hint, d:q.def, opt:q.opts }))
}));
export const REG_BY: Record<string, RegRow> = Object.fromEntries(REG.map(r => [r.id, r]));
export const REG_CATS = [...new Set(REG.map(r => r.cat))];
export const CAT_LABEL: Record<string, string> = {PriceVolume:'Price-Volume'};
export const ZONE_LABEL: Record<string, string> = {overlay:'Price overlay', panel:'Own panel', volume:'Volume pane'};
export const EV_LABEL: Record<string, [string, string]> = {VERIFIED_DEFAULT:['Verified default','pos'], PROPOSED_DEFAULT:['Proposed default','neu'], REFERENCE_PROFILE_NOT_UI_DEFAULT:['Reference profile','warn'], REFERENCE_FORMULA_NOT_UI_DEFAULT:['Reference formula','warn'], NOT_APPLICABLE:['No input','neu']};
export const OUT_LABEL = (k: string) => k.replace(/_/g,' ').replace(/\b(di|pct|roc|obv|sma|ema|vwap|kvo|adx|rsi|atr|natr|adl|cmf|mfi|eom|nvi|pvi|pvt|ppo|pvo|tsi|uo|ao|bop|cmo|cci|kama|hma|wma|vwma)\b/g, m => m.toUpperCase()).replace(/^./, m => m.toUpperCase());

/* ---- CONDITION CATALOG (the reference's CATALOG) ---- */
export const CATALOG: Record<string, LegacySpec> = LEGACY;
export const EXTRA_GROUPS = CORE_EXTRA;

/* readiness: the API decides (production: registry available_for_backtest, flow data published) */
export const regReady = (id: string) => API.ready({ type:'reg', ind:id } as RegCard);
export const condReady = (c: Card) => API.ready(c);
export const regDefaults = (r: RegRow) => Object.fromEntries(r.p.filter(x=>x.t!=='fixed').map(x => [x.k, x.d ?? (x.t==='boolean'?false:x.t==='enum'?(x.opt||[''])[0]:'')]));
/* condition shape is derived from where the indicator is drawn: overlays compare price to the line, panels compare the line to a value */
/* default threshold for panel indicators = the output's own median on the selected stock (derived from data, never a per-indicator constant) */
export const regMedian = (id: string, p: Record<string, unknown>, o: string) => { if(!regReady(id)) return 0; const outs = API.indicatorOutputs(S.sigTicker, id, p); if(!outs) return 0;
  const v = Array.from(outs[o]||[]).filter(isFinite).sort((a,b)=>a-b); if(!v.length) return 0; const m = v[Math.floor(v.length/2)], mag = Math.pow(10, Math.floor(Math.log10(Math.abs(m)||1))-1); return Math.round(m/mag)*mag };
export const mkReg = (id: string): RegCard => { const r = REG_BY[id], p0 = regDefaults(r), base = r.zone==='panel' ? {lhs:{t:'out',o:r.out[0]}, op:'gt', rhs:{t:'val',v:regMedian(id, p0, r.out[0])}} : {lhs:{t:'price'}, op:'ca', rhs:{t:'out',o:r.out[0]}};
  return {id:Math.random().toString(36).slice(2,8), type:'reg', on:true, ind:id, p:regDefaults(r), ...base} as RegCard };
export const priceLbl = (r: RegRow) => r.zone==='volume' ? 'Volume' : 'Close';
export const sideLbl = (r: RegRow, s: any) => s.t==='price' ? priceLbl(r) : s.t==='out' ? OUT_LABEL(s.o) : nf(+s.v, (+s.v)%1?2:0);
export interface CatView { group: string; reg?: boolean; label: string; desc: string; params: LegacySpec['params']; ops: string[]; opLabels?: Record<string, string>; noVal?: boolean; unit?: string; val?: number }
export const catOf = (c: any): CatView => c.type!=='reg' ? CATALOG[c.type] : { group:'tech', reg:true, label:REG_BY[c.ind].name, desc:REG_BY[c.ind].short, params:[], ops:[], noVal:true, unit:'' };
export const opLabel = (c: Card, op: string) => (catOf(c).opLabels||{})[op] || OPS[op] || op;
export const regName = (c: RegCard) => { const r = REG_BY[c.ind], vals = r.p.filter(x=>x.t!=='fixed'&&x.t!=='enum'&&x.t!=='boolean').map(x=>c.p[x.k]).join(',');
  return `${r.name}${vals?` (${vals})`:''} · ${sideLbl(r,c.lhs)} ${OPS[c.op]} ${sideLbl(r,c.rhs)}` };

/** a card's 0/1 series on a loaded ticker (the reference's catOf(c).eval(tk, c)); all false when it has none */
export const evalCond = (tk: string, c: Card): Uint8Array => API.conditionSeries(tk, c) ?? new Uint8Array(DATA[tk] ? DATA[tk].dates.length : 0);

/* price-level lines a stop can sit on = overlay outputs of the registry (derived, not listed by hand) */
export const LEVEL_LINES = () => REG.filter(r => r.zone==='overlay').flatMap(r => r.out.filter(o => o!=='direction').map(o => ({id:r.id, o, label:`${r.name} · ${OUT_LABEL(o)}`, ready:regReady(r.id)})));
export const mkRegWith = (id: string, over: Record<string, any>) => { const c = mkReg(id); const {p, ...rest} = over; Object.assign(c, rest); if(p) c.p = {...c.p, ...p}; return c };

/** whether a change from `before` to `after` keeps a condition list within limits.max_conditions: the worker counts the
    enabled conditions of each list of a request (LIMIT_EXCEEDED max_conditions) and the page sends the enabled cards it
    can calculate (condReady). A change that brings a list above the limit is refused with the page's toast; one that
    does not add an active card (removing, switching off, a card that is not calculated) is always made. */
export const withinLimit = (before: Card[], after: Card[]) => { const max = CAT.limits.max_conditions, n = (l: Card[]) => l.filter(c=>c.on&&condReady(c)).length, k = n(after);
  if(k <= max || k <= n(before)) return true; toast(`Limit reached: at most ${max} active conditions per list.`); return false };
/** a list with one card switched on (the change withinLimit checks before the switch) */
export const switchedOn = (list: Card[], c: Card) => list.map(x => x===c ? {...x, on:true} as Card : x);

/** whether any active card needs the broker data (flow cards; the reference's rank by foreign net is the server's) */
export const needsFlow = () => !!CAT?.flow.available && [...S.conds, ...S.exitConds].some(c => c.type!=='reg' && CATALOG[c.type].group==='flow');
