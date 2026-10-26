/* The backtest page's statistics (backtest.html section 9 STATISTICS: mean, sd, skew, kurt, quant, ncdf, ninv,
   seriesStats, tradeStats, dsr) as pure functions with the page's formulas, operation order and edge rules, so the
   worker's numbers are bit for bit the page's for the same series (tests/stats.test.ts compares them with the page's
   own code in tests/stats-oracle.mjs). The raw objects keep the page's field names; toSeriesStats / toTradeStats map
   them to the wire (contract.ts), where a number the page shows as '—' (NaN, ±Infinity) becomes null and an infinite
   profit factor 'inf'. 252 trading days a year, rf = 0.
   Pure module: no DOM and no Node API. */
import type { LedgerTrade } from './ledger.ts';
import type { ProfitFactor, SeriesStats, TradeStats } from './contract.ts';

type Nums = ArrayLike<number>;

/* ---- the page's helpers: left-to-right sums from 0 and `**` powers, exactly as written there ------------------- */
export function mean(a: Nums): number { let s = 0; for (let i = 0; i < a.length; i++) s = s + a[i]; return s / (a.length || 1) }
export function sd(a: Nums): number {
  const m = mean(a); let s = 0;
  for (let i = 0; i < a.length; i++) s = s + (a[i] - m) ** 2;
  return Math.sqrt(s / ((a.length - 1) || 1));
}
/** Skew and kurtosis as the page: population moments over the sample sd; NaN when sd is 0 (the page then shows '—'). */
export function skew(a: Nums): number { const m = mean(a), s = sd(a); let t = 0; for (let i = 0; i < a.length; i++) t = t + ((a[i] - m) / s) ** 3; return t / a.length }
export function kurt(a: Nums): number { const m = mean(a), s = sd(a); let t = 0; for (let i = 0; i < a.length; i++) t = t + ((a[i] - m) / s) ** 4; return t / a.length }
/** Lower empirical quantile (no interpolation): sorted[floor(q·(n−1))]; undefined for an empty input, as on the page. */
export function quant(a: Nums, q: number): number {
  const s = Array.from(a).sort((x, y) => x - y);
  return s[Math.min(s.length - 1, Math.max(0, Math.floor(q * (s.length - 1))))];
}
/** Normal CDF (Abramowitz-Stegun 26.2.17, the page's constants). */
export function ncdf(x: number): number {
  const t = 1 / (1 + .2316419 * Math.abs(x)), d = .3989423 * Math.exp(-x * x / 2), p = d * t * (.3193815 + t * (-.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}
/** Inverse normal CDF (Acklam's rational approximation, the page's constants and branches). */
export function ninv(p: number): number {
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239], b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572], c = [-.007784894002430293, -.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783], d = [.007784695709041462, .3224671290700398, 2.445134137142996, 3.754408661907416];
  const q = p < .02425 ? Math.sqrt(-2 * Math.log(p)) : p > 1 - .02425 ? Math.sqrt(-2 * Math.log(1 - p)) : 0;
  if (p < .02425) return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  if (p > 1 - .02425) return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  const r = p - .5, s = r * r; return (((((a[0] * s + a[1]) * s + a[2]) * s + a[3]) * s + a[4]) * s + a[5]) * r / (((((b[0] * s + b[1]) * s + b[2]) * s + b[3]) * s + b[4]) * s + 1);
}
const maxOf = (a: number[]): number => { let m = -Infinity; for (const x of a) m = Math.max(m, x); return m };   // = Math.max(...a)
const minOf = (a: number[]): number => { let m = Infinity; for (const x of a) m = Math.min(m, x); return m };

/* ---- seriesStats ------------------------------------------------------------------------------------------------ */
/** The page's seriesStats result (its field names). `psr(sr0)` is the probabilistic Sharpe against sr0 (daily units). */
export interface SeriesStatsRaw {
  r: number[]; tot: number; cagr: number; vol: number; sharpe: number; sortino: number; mdd: number; calmar: number;
  maxDur: number; ulcer: number; var95: number; cvar95: number; skew: number; kurt: number;
  beta: number | null; alpha: number | null; corr: number | null; dd: number[]; psr: (sr0: number) => number;
  srd: number; n: number; best: number; worst: number; pos: number;
}

/** Statistics of a daily value series (equity or a scaled benchmark), with beta / alpha / correlation against the
    benchmark values when given and aligned. Needs at least one value (the page's tot divides by vals[0]). */
export function seriesStats(vals: Nums, benchVals?: Nums | null): SeriesStatsRaw {
  const r: number[] = []; for (let k = 1; k < vals.length; k++) r.push(vals[k] / vals[k - 1] - 1);
  const br: number[] = []; if (benchVals) for (let k = 1; k < benchVals.length; k++) br.push(benchVals[k] / benchVals[k - 1] - 1);
  const years = vals.length / 252, tot = vals[vals.length - 1] / vals[0] - 1, cagr = Math.pow(1 + tot, 1 / Math.max(years, .01)) - 1;
  const vol = sd(r) * Math.sqrt(252), down = Math.sqrt(mean(r.map(x => Math.min(0, x) ** 2))) * Math.sqrt(252);
  let peak = vals[0], mdd = 0, curDur = 0, maxDur = 0, ulc = 0; const dd: number[] = [];
  for (let k = 0; k < vals.length; k++) { const v = vals[k]; peak = Math.max(peak, v); const d = v / peak - 1; dd.push(d); mdd = Math.min(mdd, d); ulc += d * d; curDur = d < 0 ? curDur + 1 : 0; maxDur = Math.max(maxDur, curDur) }
  const sharpe = sd(r) ? mean(r) / sd(r) * Math.sqrt(252) : 0, srd = sd(r) ? mean(r) / sd(r) : 0;
  const sk = r.length > 3 ? skew(r) : 0, ku = r.length > 3 ? kurt(r) : 3, n = r.length;
  const psr = (sr0: number) => ncdf(((srd - sr0) * Math.sqrt(n - 1)) / Math.sqrt(Math.max(1e-9, 1 - sk * srd + (ku - 1) / 4 * srd * srd)));
  let beta: number | null = null, alpha: number | null = null, corr: number | null = null;
  if (br.length === r.length && br.length > 2) {
    const mb = mean(br), mr = mean(r); let cov = 0, vb = 0, vr = 0;
    for (let k = 0; k < r.length; k++) { cov += (r[k] - mr) * (br[k] - mb); vb += (br[k] - mb) ** 2; vr += (r[k] - mr) ** 2 }
    beta = cov / (vb || 1); corr = cov / Math.sqrt((vb || 1) * (vr || 1)); alpha = (mr - beta * mb) * 252;
  }
  const var95 = r.length ? quant(r, .05) : 0, tail = r.filter(x => x <= var95);
  return { r, tot, cagr, vol, sharpe, sortino: down ? mean(r) * 252 / down : 0, mdd, calmar: mdd ? cagr / Math.abs(mdd) : 0, maxDur, ulcer: Math.sqrt(ulc / vals.length), var95, cvar95: tail.length ? mean(tail) : 0, skew: sk, kurt: ku, beta, alpha, corr, dd, psr, srd, n,
    best: r.length ? maxOf(r) : 0, worst: r.length ? minOf(r) : 0, pos: r.filter(x => x > 0).length / (r.length || 1) };
}

/* ---- tradeStats ------------------------------------------------------------------------------------------------- */
/** The trade fields the page's tradeStats reads (ret, pnl, riskPct, bars, mae, mfe), with the ledger's names. */
export type StatTrade = Pick<LedgerTrade, 'return' | 'pnl_idr' | 'initial_risk_pct' | 'bars_held' | 'mae' | 'mfe'>;
export interface TradeStatsRaw {
  n: number; wins: number; losses: number; wr: number; aw: number; al: number; payoff: number; pf: number; gp: number; gl: number; net: number;
  exp: number; expRp: number; sqn: number; expR: number; mw: number; ml: number; best: number; worst: number;
  hold: number; holdW: number; holdL: number; kelly: number; mae: number; mfe: number;
}
/** A win is a return above 0 (a zero return is a loss, as on the page). R multiples divide by the initial risk as a
    fraction of the entry, or, without a stop, by the page's fallbackRisk = max(1 %, sd of the returns or 1 %). */
export function tradeStats(T: readonly StatTrade[]): TradeStatsRaw {
  const w = T.filter(t => t.return > 0), l = T.filter(t => t.return <= 0);
  let gp = 0; for (const t of w) gp = gp + t.pnl_idr;
  let ls = 0; for (const t of l) ls = ls + t.pnl_idr;
  const gl = -ls;
  const fallbackRisk = Math.max(.01, sd(T.map(x => x.return)) || .01), R = T.map(t => t.return / (t.initial_risk_pct || fallbackRisk));
  let cw = 0, cl = 0, mw = 0, ml = 0;
  for (const t of T) { if (t.return > 0) { cw++; cl = 0 } else { cl++; cw = 0 } mw = Math.max(mw, cw); ml = Math.max(ml, cl) }
  const wr = T.length ? w.length / T.length : 0, aw = w.length ? mean(w.map(t => t.return)) : 0, al = l.length ? mean(l.map(t => t.return)) : 0;
  return { n: T.length, wins: w.length, losses: l.length, wr, aw, al, payoff: al ? aw / Math.abs(al) : 0, pf: gl ? gp / gl : (gp ? Infinity : 0), gp, gl, net: gp - gl,
    exp: T.length ? mean(T.map(t => t.return)) : 0, expRp: T.length ? (gp - gl) / T.length : 0, sqn: R.length > 1 ? Math.sqrt(Math.min(R.length, 100)) * mean(R) / (sd(R) || 1) : 0, expR: R.length ? mean(R) : 0,
    mw, ml, best: T.length ? maxOf(T.map(t => t.return)) : 0, worst: T.length ? minOf(T.map(t => t.return)) : 0,
    hold: T.length ? mean(T.map(t => t.bars_held)) : 0, holdW: w.length ? mean(w.map(t => t.bars_held)) : 0, holdL: l.length ? mean(l.map(t => t.bars_held)) : 0,
    kelly: al && aw ? wr - (1 - wr) / (aw / Math.abs(al)) : 0, mae: T.length ? mean(T.map(t => t.mae)) : 0, mfe: T.length ? mean(T.map(t => t.mfe)) : 0 };
}

/* ---- deflated Sharpe ------------------------------------------------------------------------------------------- */
/** The page's dsr (Bailey & López de Prado): PSR against the expected maximum daily Sharpe of `trials` attempts, with
    the variance of the trials' daily Sharpes `srs` when there are at least 2, else 1 / n (the sample rule).
    sr0 is returned annualised (× √252), as the page shows it. */
export function dsr(st: SeriesStatsRaw, trials: number, srs: readonly number[]): { sr0: number; dsr: number } {
  const N_ = Math.max(2, trials), v = srs.length > 1 ? sd(srs) ** 2 : (1 / st.n), g = .5772156649;
  const sr0 = Math.sqrt(v) * ((1 - g) * ninv(1 - 1 / N_) + g * ninv(1 - 1 / (N_ * Math.E)));
  return { sr0: sr0 * Math.sqrt(252), dsr: st.psr(sr0) };
}

/* ---- wire mapping ------------------------------------------------------------------------------------------------ */
/** A number for the wire: NaN and ±Infinity (shown as '—' by the page's num/pct/pctu) become null. */
export const finiteOrNull = (x: number | null | undefined): number | null => typeof x === 'number' && Number.isFinite(x) ? x : null;
export const profitFactor = (pf: number): ProfitFactor => pf === Infinity ? 'inf' : pf;

/** Skew, kurtosis and PSR are NaN on a series without volatility (flat equity: no trade) and PSR also without any
    return; they go out as null. The other fields are finite for every finite series of at least one value. */
export function toSeriesStats(s: SeriesStatsRaw): SeriesStats {
  return {
    n_returns: s.n, total_return: s.tot, cagr: s.cagr, volatility: s.vol, sharpe: s.sharpe, sharpe_daily: s.srd,
    sortino: s.sortino, max_drawdown: s.mdd, calmar: s.calmar, longest_drawdown_bars: s.maxDur, ulcer_index: s.ulcer,
    var_95: s.var95, cvar_95: s.cvar95, skew: finiteOrNull(s.skew), kurtosis: finiteOrNull(s.kurt),
    beta: s.beta, alpha: s.alpha, correlation: s.corr, best_day: s.best, worst_day: s.worst, positive_days: s.pos,
    psr_0: finiteOrNull(s.psr(0)),
  };
}
export function toTradeStats(t: TradeStatsRaw): TradeStats {
  return {
    n: t.n, wins: t.wins, losses: t.losses, win_rate: t.wr, avg_win: t.aw, avg_loss: t.al, payoff: t.payoff,
    profit_factor: profitFactor(t.pf), gross_profit_idr: t.gp, gross_loss_idr: t.gl, net_idr: t.net,
    expectancy: t.exp, expectancy_idr: t.expRp, sqn: t.sqn, expectancy_r: t.expR,
    max_consecutive_wins: t.mw, max_consecutive_losses: t.ml, best: t.best, worst: t.worst,
    avg_hold_bars: t.hold, avg_hold_bars_winners: t.holdW, avg_hold_bars_losers: t.holdL, kelly: t.kelly,
    avg_mae: t.mae, avg_mfe: t.mfe,
  };
}
