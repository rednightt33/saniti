/* EXEC-PRICE-DISTORTION (user 2026-11-24; ERRORS M559-M562): one rule for "is this stock's price history distorted, and
   where", read by the Screener (row and cell badges) and the Backtest (trade badges, warnings). Nothing is hidden by it:
   a detection only adds a badge (the user: "value harus tetap ditampilkan as is dengan badge").

   Two checks, both from the data, no list of tickers:
   1. The daily limit (UD44, user: "Batasnya buat tetap saja, cap 35% atas bawah"; "Ok untuk UD44"): a stock's one-session
      move beyond 35 % either way is a price anomaly (the exchange's widest daily limit; a move of one Rp1 tick of a stock
      at Rp10 or below is never one). It catches a wrong bar with no corporate action (WGSH 2026-03-31: -48 % then +97 %,
      ERRORS M562). A session that is the ex-date of a recorded action is judged by check 2 only (D-2: one badge).
   2. The ex-date jump (ERRORS M560): for a split, reverse split, bonus share, stock dividend or rights issue, the close of
      the last session before the ex-date over the close of the first session on or after it, against the action's
      factor (the price before over the theoretical price after): nearer the factor in log terms = the history before
      is on the old scale (raw); nearer 1 = adjusted. One session, so a later trend cannot imitate the action (the
      15-session medians read VKTR, AHAP, BUVA, pulled again, as raw). An action whose effect is under 10 % cannot be
      told from a session's own move: `small` (UD43: a badge naming its size). No close either side: `unknown`.
   The factor: split and reverse split new/old; bonus share and stock dividend (old + new)/old; rights issue P/TERP with
   TERP = (old P + new X)/(old + new), X the exercise price. TERP is read as the close of the ex-date session and P solved
   from it, so the factor is the same whether the history before is adjusted or not (from the close before, an adjusted
   close near X gives FORU 1.04 for a real 19.5); a day's move on the ex-date only moves it a little (VKTR 1.24 against
   1.23 from the raw close). The publisher's Python twin (`price_check_side`) follows the same rule; a test holds the two
   on the same cases. */

export const CAP = 0.35;                  // UD44: the fixed cap, up and down (IDX equities)
export const TICK_PRICE = 10;             // UD44 detail: at Rp10 or below a move of one Rp1 tick is never an anomaly
export const SMALL = 0.10;                // under this effect an action cannot be measured (publisher BASIS_PRICE_MIN)
export const PRICE_ACTIONS = ['STOCK_SPLIT', 'REVERSE_SPLIT', 'BONUS_SHARE', 'RIGHT_ISSUE', 'STOCK_DIVIDEND'] as const;

export type Verdict = 'adjusted' | 'raw' | 'small' | 'unknown';
export interface ActionTerms { ex: string; type: string; ratio_old: number | null; ratio_new: number | null; exercise?: number | null }
export interface ActionCheck { ex: string; type: string; factor: number | null; verdict: Verdict; jump: number | null }
export interface Anomaly { date: string; prev: number; close: number; pct: number }

const pos = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x) && x > 0;

/** The action's factor (the price before over the theoretical price after), or null when a term is missing. A rights
    issue's is solved from `after`, the close of its ex-date session taken as the theoretical price. */
export function termsFactor(type: string, old: number | null, nw: number | null, after: number | null, exercise?: number | null): number | null {
  if (!pos(old) || !pos(nw)) return null;
  if (type === 'STOCK_SPLIT' || type === 'REVERSE_SPLIT') return nw / old;
  if (type === 'BONUS_SHARE' || type === 'STOCK_DIVIDEND') return (old + nw) / old;
  if (type !== 'RIGHT_ISSUE' || !pos(after) || !pos(exercise)) return null;
  const before = (after * (old + nw) - nw * exercise) / old;   // TERP = (old P + new X)/(old + new), solved for P
  return pos(before) ? before / after : null;
}

/** Whether an action's factor can show in a session's move (re-check 2026-11-25, finding A): a rights issue priced
    above the market (factor below 1) moves no price, raw or adjusted, since nobody takes it up; every other factor can.
    The publisher's twin returns no side for it (price_check_side). */
export const measurable = (type: string, factor: number | null): boolean => !(type === 'RIGHT_ISSUE' && factor !== null && factor < 1);

/** Check 2 on one action from the closes either side of its ex-date and its factor. */
export function verdictOf(before: number | null, onEx: number | null, factor: number | null): { verdict: Verdict; jump: number | null } {
  if (!pos(factor)) return { verdict: 'unknown', jump: null };
  if (Math.abs(factor - 1) < SMALL) return { verdict: 'small', jump: pos(before) && pos(onEx) ? before / onEx : null };
  if (!pos(before) || !pos(onEx)) return { verdict: 'unknown', jump: null };
  const jump = before / onEx;
  return { verdict: Math.abs(Math.log(jump) - Math.log(factor)) < Math.abs(Math.log(jump)) ? 'raw' : 'adjusted', jump };
}

/** The first index with dates[i] >= d (dates ascending), dates.length when none. */
function firstOnOrAfter(dates: readonly string[], d: string): number {
  let lo = 0, hi = dates.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < d) lo = m + 1; else hi = m }
  return lo;
}

/** Check 2 for every price action of a ticker, on its daily closes (the Screener: the actions file's terms; the Backtest
    reads the publisher's verdict from the events file's basis block, written by the Python twin of this rule). */
export function checkActions(dates: readonly string[], closes: ArrayLike<number | null | undefined>, actions: readonly ActionTerms[]): ActionCheck[] {
  const out: ActionCheck[] = [];
  for (const a of actions) {
    if (!(PRICE_ACTIONS as readonly string[]).includes(a.type)) continue;
    const i = firstOnOrAfter(dates, a.ex);
    const before = i > 0 ? closes[i - 1] ?? null : null, onEx = i < dates.length ? closes[i] ?? null : null;
    const factor = termsFactor(a.type, a.ratio_old, a.ratio_new, onEx as number | null, a.exercise ?? null);
    // a rights issue above the market cannot be told (no factor, so no size is named for it)
    if (!measurable(a.type, factor)) { out.push({ ex: a.ex, type: a.type, factor: null, verdict: 'small', jump: null }); continue }
    const v = verdictOf(before as number | null, onEx as number | null, factor);
    out.push({ ex: a.ex, type: a.type, factor, ...v });
  }
  return out;
}

/** Check 1: the sessions whose move from the session before is beyond the cap, except a recorded action's ex-date
    (judged by check 2) and a one-tick move of a stock at Rp10 or below. */
export function capAnomalies(dates: readonly string[], closes: ArrayLike<number | null | undefined>, exDates: Iterable<string> = []): Anomaly[] {
  // an ex-date on a day without a session counts on the first session after it
  const ex = new Set([...exDates].map(d => dates[firstOnOrAfter(dates, d)]).filter(Boolean)), out: Anomaly[] = [];
  let prev: number | null = null;
  for (let i = 0; i < dates.length; i++) {
    const c = closes[i];
    if (!pos(c)) continue;
    if (prev !== null && !ex.has(dates[i])) {
      const pct = c / prev - 1;
      const tick = prev <= TICK_PRICE && Math.abs(c - prev) <= 1;
      if (Math.abs(pct) > CAP + 1e-9 && !tick) out.push({ date: dates[i], prev, close: c, pct });   // a limit hit exactly is legitimate
    }
    prev = c;
  }
  return out;
}
