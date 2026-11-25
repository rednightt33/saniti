/* The bars a look-ahead check cuts the data at, derived from the series it checks (re-check of ERRORS M558,
   wf_c2fe2424-bf4/screener:recheck2/NEW-1, 2026-11-25: with four fixed cuts, 150, 260, 390 and 520, a series that reads
   the next bar passed the Backtest worker's gate wherever it is sparse: a read of bar i+1 inside in_categories or
   category_change, and every candlestick pattern shifted one bar ahead but one of 20; the Screener's gate, cut at 60,
   151, 263 and 400, caught 3 of the 20). Both gates read their cuts here: the worker's look-ahead files
   (apps/backtest-worker/tests/lookahead.test.ts, pit, flow-grammar and grammar) and the Screener's asof.test.ts.
   Why the cuts must sit where the series changes. A value on bar i that reads bar i+1 differs, on the data cut at c
   (bars 0..c), only on the cut's last bar c, and only by what bar c+1 would have given:
   - read clamped to the data (the value at c reads bar c itself when c+1 is not there): the cut gives the full series'
     value of bar c-1 on bar c, so the read shows exactly when the full series changes at c (its value on c differs from
     its value on c-1). A fixed cut between two changes of a flag shows nothing;
   - read filled (a shifted array, empty or 0 where c+1 is missing): the cut gives that fill F on bar c, so the read
     shows exactly when the full series is not F on c. Cuts on bars with two different full values hold one that is
     not F, whatever F is (a number, 0 or none);
   - a read two bars ahead shows at c when the full series changes at c or at c-1, so a change bar shows it too.
   So for every output the cuts hold at least PER of its change bars (all of them when it changes fewer times: a flag
   that fires once), and bars with two different values of it. A continuous series changes on nearly every bar: the
   fixed cuts are change bars of it already and add nothing; a sparse one (a 0/1 flag, a category, a pattern) gets cuts
   on its own changes, spread over the history, and the bar before one of them when its changes all lead to one value.
   Cuts below the first fixed cut are not taken (a cut that short can refuse a setting the full data computes, which is
   no look-ahead), nor after total - 2 (the cut must leave a later bar out). Pure functions of the series. */

/** At least this many change bars of each output are cuts (all of them when it has fewer). */
export const PER = 4;

/** A value as the gate compares it: a finite number, else none (null). */
const val = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null;

/** The bars j (1 <= j < total) where an output's value differs from the one on bar j - 1 (a value against none counts). */
export function changeBars(s: ArrayLike<unknown>, total = s.length): number[] {
  const out: number[] = [], n = Math.min(total, s.length);
  for (let j = 1; j < n; j++) if (val(s[j]) !== val(s[j - 1])) out.push(j);
  return out;
}

/** `per` of the bars, spread evenly from the first to the last, then the others in order. */
function spread(bars: readonly number[], per: number): number[] {
  if (bars.length <= per) return [...bars];
  const pick = new Set(Array.from({ length: per }, (_, k) => bars[Math.round(k * (bars.length - 1) / (per - 1))]));
  return [...pick, ...bars.filter(j => !pick.has(j))];
}

/** The cuts for a run's outputs (`full`: the outputs of the run on all `total` bars; keys starting with `_` are not
    series): the fixed `base` cuts, then for each output its change bars, spread over its history, until `per` of them
    are cuts (the fixed cuts count when they are change bars of it), and, when the cuts hold one value of it only, a
    change bar and the bar before it (the two hold different values). Sorted, each once. */
export function cutsFor(full: Record<string, unknown> | null, total: number, base: readonly number[], per = PER): number[] {
  const lo = Math.min(...base), hi = total - 2, cuts = new Set(base.filter(c => c <= hi));
  for (const [k, raw] of Object.entries(full ?? {})) {
    const s = raw as ArrayLike<unknown> | null | undefined;
    if (k.startsWith('_') || !s || typeof s.length !== 'number') continue;
    const J = changeBars(s, total).filter(j => j >= lo && j <= hi);
    if (!J.length) continue;
    const want = Math.min(per, J.length);
    let have = J.filter(j => cuts.has(j)).length;
    for (const j of spread(J, per)) { if (have >= want) break; if (!cuts.has(j)) { cuts.add(j); have++ } }
    // two different values of it among the cuts: a change bar's own value and the one before it differ
    const values = new Set([...cuts].filter(c => c < s.length).map(c => val(s[c])));
    if (values.size < 2) { const j = J.find(x => x - 1 >= lo); if (j !== undefined) { cuts.add(j); cuts.add(j - 1) } }
  }
  return [...cuts].sort((a, b) => a - b);
}

/** The cuts for one series (cutsFor with a single output). */
export const cutsOf = (s: ArrayLike<unknown>, total: number, base: readonly number[], per = PER): number[] => cutsFor({ s }, total, base, per);
