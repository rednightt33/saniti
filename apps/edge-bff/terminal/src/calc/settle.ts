/* EXEC-PINE-INDICATORS UD33 option B (user 2026-11-24: "UD33: Alpha KAMA --> ok pakai opsi B", then "Untuk 2-5 bisa go"):
   a recursive indicator carries the start of its data for a long while (Alpha KAMA: its T3 and its KAMA start from 0, as
   the Pine), so its first bars are not the values a longer history would give. The Terminal draws such an indicator only
   from the bar where the start of the data no longer matters. The formula (F), the Screener and the Backtest are
   unchanged (option C was not chosen): this lives beside F, as DRAWINGS does, and only the Terminal reads it
   (app/indicators.ts). Pure, and in calc/ because the lab module that registers a rule is loaded by the workers too, whose
   images copy calc/ and lab/ only (ERRORS M405).

   The point is measured on the chart's own bars and parameters, never a fixed count: the rule's output is computed on
   every bar and again on the same bars without their first `cut`; from the bar after which the two agree within
   `tolerance` x the close on every later bar, the start no longer matters (the method of the UD33 measurement). A run of
   bars the formula computes in one go (def() restarts after a bar without the inputs the registry's `req` names) is
   measured from its own start. Where the two never agree for good (a history too short: the monthly chart since 2018),
   the run is not drawn at all.

   Keyed by the registry entry's `key`; empty in the public build: the lab module registers its own. Releasing such an
   indicator moves its rule into SETTLE here with its formula (INDICATOR_BETA_TO_LIVE.md Part B step 2). */
import { isN, type Bars, type IndicatorFn, type Out, type Params } from './indicators';

export interface Settle {
  /** the output computed twice and compared */
  measure: string;
  /** the outputs the Terminal leaves empty before the point: the measured one and those read from it */
  hides: string[];
  /** the largest difference between the two, as a share of the bar's close, that still counts as agreement */
  tolerance: number;
  /** the bars the second computation leaves out: `default`, or the chart's timeframe's own ('M', ...) */
  cut: { default: number; [timeframe: string]: number };
}
export const SETTLE: Record<string, Settle> = {};
// Alpha Kama (I58, released 2026-11-26 from src/lab/index.ts)
SETTLE.alpha_kama = { measure: 'kama', hides: ['kama', 'color_index', 'color_state', 'long', 'short'], tolerance: 0.005, cut: { default: 50, M: 12 } };

/** a run of bars [from, to) the formula computes in one go, drawn from `at` (`at` = `to`: not in this run) */
export interface SettleRun { from: number; at: number; to: number }

export const cutOf = (s: Settle, timeframe: string) => Math.max(1, Math.floor(s.cut[timeframe] ?? s.cut.default));

/** where each run of `B` (bars with every input `need` names) settles; `full` is the measured output on all of `B` */
export function settleRuns(fn: IndicatorFn, B: Bars, p: Params, s: Settle, need: string, cut: number, full: ReadonlyArray<number | null> = fn(B, p)[s.measure]): SettleRun[] {
  const n = B.C.length, cols = (['O', 'H', 'L', 'C', 'V'] as const).filter(f => need.includes(f));
  const ok = (i: number) => cols.every(f => isN(B[f][i]));
  const runs: SettleRun[] = [];
  for(let from = 0; from < n;) {
    while(from < n && !ok(from)) from++;
    let to = from; while(to < n && ok(to)) to++;
    if(to === from) break;
    const start = from + cut;
    if(to - start < 1) runs.push({ from, at:to, to });
    else {
      const sl = <T>(a: ReadonlyArray<T> | undefined) => (a ? a.slice(start, to) : a) as T[];
      const part = fn({ O:sl(B.O), H:sl(B.H), L:sl(B.L), C:sl(B.C), V:sl(B.V), ...(B.T ? { T:sl(B.T) } : {}) }, p)[s.measure];
      let at = start;
      for(let t = to - 1; t >= start; t--) {
        const a = full[t], b = part[t - start], c = B.C[t] as number;
        if(!isN(a) || !isN(b) || Math.abs(a - b) > s.tolerance * Math.abs(c)) { at = t + 1; break }
      }
      runs.push({ from, at, to });
    }
    from = to;
  }
  return runs;
}

/** the formula's outputs with `s.hides` empty before each run's point, and the runs (the legend says why it is empty) */
export function settled(fn: IndicatorFn, B: Bars, p: Params, s: Settle, need: string, cut: number): { out: Out; runs: SettleRun[] } {
  const out = fn(B, p), runs = settleRuns(fn, B, p, s, need, cut, out[s.measure]);
  for(const k of s.hides) {
    const a = out[k]; if(!a) continue;
    const o = a.slice();
    for(const r of runs) for(let t = r.from; t < r.at; t++) o[t] = null;
    out[k] = o;
  }
  return { out, runs };
}

/** the run that holds bar `i`, while `i` is before its point (the bar is not drawn); else null */
export const unsettledAt = (runs: ReadonlyArray<SettleRun> | undefined, i: number) =>
  runs?.find(r => i >= r.from && i < r.at) ?? null;
