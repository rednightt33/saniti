# Flow indicators FL01-FL48: formulas and conventions (EXEC-TERMINAL-FLOW-IND, EXEC-TERMINAL-IND-EDIT)

The contract is `FLOW_INDICATORS_SPEC.xlsx` (names, parameters, defaults, ranges; user decisions of 2026-10-30, sheet
`Keputusan`). This file states each formula exactly, with the conventions the spreadsheet leaves to the implementation,
so that the Terminal (`apps/edge-bff/terminal/src/calc/flow.ts`) and an independent recomputation give the same numbers.
Later the Screener and the Backtest use the same module on the same raw data.

## 1. Data

- **Broker rows** (published broker files, Feature 05): per session date `d`, broker `b`, investor type `i`
  (`Foreign`/`Domestic`), board `m` (`Regular`, `Nego`, `Cash` = Feature 05 `Tunai`), buy and sell value `bv`, `sv` (IDR),
  buy and sell lots `bl`, `sl` (1 lot = 100 shares; odd lots as fractions), buy and sell transactions `bf`, `sf`.
- **Candles**: the chart's sessions (daily), or weeks or months (a weekly or monthly candle sums the rows of its
  sessions). Every "day", "session" or "N days" below means a candle of the chart's timeframe (user 2026-10-30: "2-3 OK").
- **Prices** per candle: close, volume (shares). **Insider rows**: events with `family` = `INSIDER`, `action` BUY or SELL,
  `value` (IDR), date `d`. **Broker classification**: `ref/brokers` `classification` (Institutional-heavy, Retail-heavy,
  Mixed, Niche).
- **Candle with data**: a candle with at least one broker row (any board, any investor). A candle without data (before
  the first broker date, after the last, or a session the source misses) gives null for every flow output; it is never 0.
  FL27, FL28 (prices) and FL31 (insider events) do not read broker rows: they follow the price candles.

## 2. Shared conventions

- **Filter**: a row counts when its board is in the chosen boards and its investor type in the chosen investor types
  (default: all). "All investors" denominators use the board filter only.
- **Window** `W` (the indicator's rolling days / days / sessions parameter): the candles `t-W+1 .. t`. A value at `t`
  needs `t` to be a candle with data and `t-W+1` not before the first candle with data; otherwise null. Sums over the
  window add the rows of its candles with data.
- **Ratio**: null when the denominator is 0 or null. A sum that needs `bf`/`sf` is null when a row in it has none.
- **Cohort** (the broker group an indicator measures):
  - `Selected brokers`: the chosen broker codes.
  - `All brokers`: every broker (only where the scope offers it).
  - `Top-N cohort` (user decisions B3, B4, "Top 3 for all"): at each candle `t`, the brokers are ranked by their score
    over the indicator's window ending at `t`, with the filter; score = net buy `Σ(bv-sv)` (default), gross buy `Σbv`,
    or net sell `Σ(sv-bv)`. Only brokers with score > 0 are eligible; the N highest are taken (ties: broker code A-Z).
    The cohort is recomputed at every candle ("Hitung ulang tiap hari").
  - **Side picks the cohort** (EXEC-TERMINAL-IND-EDIT K1, K2, R1; user 2026-11-05): on an indicator with a Side (FL01-FL05,
    FL08, FL13, FL14, FL33) Rank is Net or Gross and the side says who: the Buy line's Top-N are the top buyers by
    net buy `Σ(bv-sv)` or gross buy `Σbv`, the Sell line's the top sellers by net sell `Σ(sv-bv)` or gross sell `Σsv`.
    A saved "net sell" rank reads as Net. Selected brokers and all brokers are the same on both sides. Indicators
    without a Side keep Rank = net buy, gross buy or net sell (who is ranked).
  - Frozen Top-N (FL18-FL20, user 2026-10-30: "yes pakai kelompok broker tetap untuk ketiganya"): ranked once over the
    candles from the anchor to the last candle with data, then kept for every candle. The ranking sees candles after `t`
    (it is the cohort of the whole period on the chart): a Backtest or a Screener rule must not read it as known at `t`
    (Reviewer A, A8, 2026-10-30).
- **Bandar** (user 2026-10-30): the N largest net buyers by net buy (IDR) over the indicator's window, recomputed every
  candle; the bandar sellers are the N largest net sellers by `Σ(sv-bv)` (eligible when > 0). Default N = 3.
- **Percentile** (mid-rank): `P = 100 x (count(v < x) + 0.5 x count(v = x)) / count`, over the non-null values `v` of
  the same series at the `baseline` candles before `t` (`t` itself excluded). Null when `x` is null, when fewer than
  `baseline` candles precede `t` since the series' first non-null value, or when none of them is non-null.
- **Change line** (EXEC-TERMINAL-IND-EDIT; FL11, FL34): `change_t = value_t - value_(t-lag)`, in the value's unit
  (percentage points for a %); `lag` = 1, 5 or 20 candles, or (FL11) the rolling days, so the two periods do not
  overlap. Null when either value is null.
- **Z-score** (U1, FL37): `z = (x - M) / SD` over the same non-null history as the percentile (the `baseline` candles
  before `t`, ready under the same rule); `M` its mean, `SD` its sample standard deviation (`n - 1`, as Feature_06
  `stddev_samp`); null with fewer than 2 values or `SD = 0`.
- **Default anchor** (FL18-FL20, FL23): the first visible candle; the values follow the chart's view.
- **Defaults**: a parameter the caller leaves out takes its default in the registry (`flowRegistry.json`, from
  `Parameter_Terminal`), never a fallback inside a formula (`computeFlow`; Reviewer A, A4).
- **Candles without a price**: the candles are the price dates. A broker session on a date the price table lacks is not
  on any candle, and windows that span such a date reach one session further back per missing date (Reviewer A, A1).
  The one known gap, 2026-09-17 and 2026-09-18 for almost every stock (ERRORS_AND_SOLUTIONS M238), was filled on
  2026-10-31 (EXEC-PRICE-GAP-0917); the rule stays for any later gap.
- **Default brokers of FL23** (`top3_net_buy_20`): the three largest net buyers by `Σ(bv-sv)` (all boards, all
  investors) over the last 20 candles with data, as the Broker inventory panel picks them.
- **Default lists of FL34** (`class:Institutional-heavy`, `class:Retail-heavy`): the brokers of that classification in
  `ref/brokers`.

## 3. Formulas

`C` = the cohort at `t`; `A` = every broker; sums over the window `W` ending at `t` with the filter unless stated.
`BL(X) = Σ bl`, `SL(X) = Σ sl`, `BV(X) = Σ bv`, `SV(X) = Σ sv`, `BF(X) = Σ bf`, `SF(X) = Σ sf` over the brokers `X`.
`TBV` = `BV(A)` with the board filter only (all investors) unless the denominator option says otherwise. Side `Both`
draws the Buy and the Sell line in one panel.

| Id | Name | Output(s) | Formula |
|---|---|---|---|
| FL01 | Transaction Size · Lot | buy, sell | Buy `BL(C)/BF(C)`; Sell `SL(C)/SF(C)` (lots per transaction) |
| FL02 | Transaction Size · Value | buy, sell | Buy `BV(C)/BF(C)`; Sell `SV(C)/SF(C)` (IDR per transaction) |
| FL03 | Share · Volume | buy, sell | Buy `100 BL(C)/BL(A)`; Sell `100 SL(C)/SL(A)`; `A` with the same filter |
| FL04 | Share · Transactions | buy, sell | Buy `100 BF(C)/BF(A)`; Sell `100 SF(C)/SF(A)`; `A` with the same filter |
| FL05 | Transaction Size · vs Market | buy, sell | Buy `(BL(C)/BL(A)) / (BF(C)/BF(A))`; Sell with `SL`, `SF`; `A` same filter |
| FL06 | Transaction Size · Buy/Sell Ratio | ratio | `(BL(C)/BF(C)) / (SL(C)/SF(C))` |
| FL07 | Share · Market Volume | share | `100 BL(C) / BL(A)`; `A`: board filter, all investors (default) or board and investor filter |
| FL08 | Transaction Size · Percentile | pct | percentile (baseline) of `x = BL(C)/BF(C)` (Side Buy) or `SL(C)/SF(C)` (Sell), window `W` |
| FL09 | Block Money Candidate | flag | 1 when all hold, else 0 (null when one input is null): FL08 Buy (same cohort, filter, `W`, baseline) >= pct threshold; FL05 Buy >= ratio threshold; FL07 >= participation threshold; FL11 > net-flow threshold; and, if chosen, FL10 >= imbalance threshold. Drawn as a mark under the candle where 1. Inside FL09, FL07 and FL11 always use the board-only denominator (FL09 has no denominator option) |
| FL10 | Transactions · Buy/Sell Imbalance | imbalance | `(BF(C)-SF(C)) / (BF(C)+SF(C))` |
| FL11 | Net Flow / Turnover Ratio | value, change | `100 (BV(C)-SV(C)) / TBV`, `TBV` = every investor's gross buy on the chosen boards (one denominator, to-do 7); change line (shared conventions) |
| FL12 | Net Buy Persistence · Cohort | persistence | `100 x` (candles `k` in the window with `BV_k(C)-SV_k(C) > 0`) / `W`; `C` ranked over the window; a candle without a row of `C` is not a buy candle |
| FL13 | Concentration HHI · Gross | buy, sell | Buy `Σ_(b in C) (m(b)/m(A))^2`, `m` = `BL` (unit Lot) or `BV` (Rupiah); Sell with `SL`/`SV`; `A` every broker with the filter; `C` = every broker (default), selected brokers or Top-N ranked over the window (side picks the cohort); the Top-N is ranked in Rupiah (net or gross) whatever the unit: the unit changes the measure, not who is ranked |
| FL14 | Concentration HHI · Buy − Sell | asym | FL13 Buy of the top buyers − FL13 Sell of the top sellers (same scope, unit, filter, window; K2) |
| FL15 | Concentration Top-N · Gross Buy | share | `100 x` (sum of the N largest `m(b)`) / `m(A)`, `m` = `BL` (unit Lot) or `BV` (Rupiah); with "minus the even share": `- 100 x N'/k`, `N'` = brokers taken, `k` = brokers with `m(b) > 0` |
| FL16 | Concentration Top-N · Net Buy | share | `n_b = BV(b)-SV(b)` (Rupiah) or `BL(b)-SL(b)` (Lot, its own sign); `100 x` (sum of the N largest positive `n_b`) / (sum of all positive `n_b`); with "minus the even share": `- 100 x N'/k`, `k` = brokers with `n_b > 0` |
| FL17 | Buy VWAP · Rolling | vwap | `BV(C) / (100 BL(C))` (IDR per share), on the price axis |
| FL18 | Buy VWAP · Anchored | vwap | frozen `C`; sums from the anchor to `t`: `BV(C) / (100 BL(C))`; null before the anchor |
| FL19 | Implied Cost · Anchored | cost | frozen `C`, from the anchor, `Q`, `K` start at 0; per candle `q = BL_k(C)-SL_k(C)`: if `q > 0`: if `Q <= 0` then `K = max(Q+q,0) x BV_k(C)/BL_k(C)` else `K += q x BV_k(C)/BL_k(C)`; if `q < 0` and `Q > 0`: `K = K x max(Q+q,0)/Q`; then `Q += q`. Output `K/(100 Q)` when `Q > 0`, else null (user 2026-10-30, "1 pakai A": the rule for an inventory at or below 0, which the spreadsheet leaves open) |
| FL20 | Implied Cost · Distance % | dist | `100 (close / FL19 - 1)` |
| FL21 | Flow Percentile · vs Turnover | pct | percentile (baseline 250) of `x = 100 m(C) / TBV`, `m` = net `BV-SV` (default), gross buy `BV` or gross sell `SV` (to-do 10); `TBV` = every investor's gross buy on the chosen boards |
| FL22 | Broker Buy Breadth | breadth | `n_b = BV(b)-SV(b)` over the window with the filter; active = brokers with any `bv` or `sv` > 0 in it; `100 x` (active with `n_b > 0`) / active; "Number of brokers" (U6): the count of active brokers with `n_b > 0` |
| FL23 | Broker Inventory | one line per broker, total | per chosen broker (and, when "Show cohort total", their sum): from the start candle, Lot: cumulative `Σ(bl-sl)`, Value: cumulative `Σ(bv-sv)`; Daily: the candle's own `bl-sl` or `bv-sv`; null before the start. At most 5 brokers are drawn (more are ignored); a code without rows in the data draws 0 |
| FL24 | Bandar Balance · % | balance | `100 (NB + NS) / TBV(filter)`; `NB` = sum of `BV-SV` of the N bandar buyers, `NS` = sum of `BV-SV` (negative) of the N bandar sellers, over the window; `TBV(filter) = BV(A)` with the filter; reference lines 6, 10, -6, -10 |
| FL25 | Bandar Balance · Rupiah | net | `NB + NS` (IDR) |
| FL26 | Net Flow Streak | streak | per candle net `n_k = BV_k(C)-SV_k(C)` (`C` ranked over the last `limit` candles); `s_t = s_{t-1}+1` if `n_t > 0` and `s_{t-1} > 0`, `1` if `n_t > 0` otherwise; `s_{t-1}-1` if `n_t < 0` and `s_{t-1} < 0`, `-1` if `n_t < 0` otherwise; 0 on a candle with data where `n_t = 0` (no row of the cohort or the filter); null on a candle without data, after which the count starts again; capped at `±limit` |
| FL27 | Silent Accumulation | flag | 1 when `SMA(volume,recent)_t / SMA(volume,baseline)_{t-recent} >= volume x` and `100 |close_t/close_{t-recent} - 1| <= max move`; drawn as a mark under the candle; and two optional marks (to-do 18), each candle alone, every board and investor: `net` = 1 when `Σ n_b` of the N largest net buyers / `Σ |n_b|` of the N largest net sellers `>= X`; `gross` = 1 when `Σ bv` of the N largest gross buyers / `Σ sv` of the N largest gross sellers `>= X` (N, X per trigger; null when the sellers' sum is 0); a side with fewer than N brokers adds the ones it has |
| FL28 | Average Daily Value | adv | `SMA(close x volume, sessions)` (IDR) |
| FL29 | Bandar Balance · Accumulation Days | value, balance | `100 x` (candles in the last `days` whose own one-candle FL24 (N, filter) is above the threshold) / `days`; a candle without broker data in the window counts as not above; `balance` (to-do 12) = `100 x Σ_k (NB_k + NS_k) / Σ_k TBV_k` over the days, each candle's own bandar, a candle without data adding 0 to both |
| FL30 | Crossing Share | share | `100 BV(Nego+Cash) / BV(all boards)`, investor filter on both |
| FL31 | Insider Net Change | net | sum of insider BUY `value` minus SELL `value` with `d` in the window's candles (IDR); 0 when none |
| FL32 | Activity Spike | buy, sell | `X_t(A) / mean(X_k(A), k = t-baseline .. t-1)`, `X` = transactions `BF`/`SF` (default), value `BV`/`SV` or lots `BL`/`SL` by the measure, Buy or Sell by the side (Both = two lines); filter; null without the full baseline; a candle without broker data inside the baseline adds 0 to the mean (divisor stays `baseline`); only the transactions measure needs the counts |
| FL33 | Transaction Size · Change % | buy, sell | `100 ((ΣV/ΣF over the last recent candles) / (ΣV/ΣF over the baseline candles before them) - 1)`, `V`, `F` = the value and transactions of each candle's own cohort `C_k` (every broker by default; Top-N of that candle: top buyers for Buy, top sellers for Sell, to-do 4); Buy `BV`/`BF`, Sell `SV`/`SF`; filter |
| FL34 | Institutional vs Retail Net | value, change | `100 (BV-SV of the institutional brokers − BV-SV of the retail brokers) / BV(A)`, filter; defaults: Institutional-heavy and Retail-heavy of `ref/brokers`; a broker in both lists is refused; change line (shared conventions) |
| FL35 | Net Buy Persistence · Top Buyer | persistence | the broker with the largest positive `BV-SV` over the window (frozen for that window); `100 x` (candles in the window where its `BV_k-SV_k > 0`) / `days`; a candle without data counts as not a buy candle; null when no broker has a positive net in the window |
| FL36 | Share · Market Value (Buy + Sell) | share | `100 (BV(C)+SV(C)) / (2 TBV)` |
| FL37 | Net Flow Percentile · Rupiah | pct | percentile (baseline 250) of `BV(C)-SV(C)` over the net window; or (U1) its z-score in the same history (shared conventions) |
| FL38 | Concentration HHI · Net Buy | hhi | `n_b = BV(b)-SV(b)` (Rupiah) or `BL(b)-SL(b)` (Lot); `Σ_(b in C) (max(n_b,0) / Σ positive n)^2`; `C` = every net buyer (default), selected brokers or Top-N (net buy or gross buy) over the window; the Top-N is ranked in Rupiah (net or gross) whatever the unit: the unit changes the measure, not who is ranked |
| FL39 | Buy VWAP · Rolling · Distance % | dist | `100 (close / FL17 - 1)` with FL39's cohort, filter and window; defaults as FL17 (20 candles, every board; to-do 16) |
| FL40 | Activity Spike · Balance | value | FL32 Buy spike / FL32 Sell spike, same measure (transactions, value or lots), baseline and filter (default investor Foreign: for all investors it is always 1); reference lines 0.5, 1, 2 |
| FL41 | Net Flow / Average Turnover | value | `100 (BV(C)-SV(C)) / (W x mean(TBV_k, k = t-N .. t-1))` over the window `W`, `TBV_k` = every investor's gross buy on the chosen boards on candle `k` (0 without data); null when fewer than `N` candles precede `t` since the first data |
| FL42 | Buy VWAP · Rolling · Daily Top-N | value | `Σ_k BV(C_k, k) / (100 Σ_k BL(C_k, k))` over the window, `C_k` = the N largest net buyers of candle `k` alone (candles without data skipped); null when a candle with data has fewer than N net buyers |
| FL43 | Sell VWAP · Rolling | value | `SV(C) / (100 SL(C))`, the cohort, filter and window as FL17 |
| FL44 | Sell VWAP · Anchored | value | frozen `C` as FL18; from the anchor to `t`: `SV(C) / (100 SL(C))`; null before the anchor |
| FL45 | Buy VWAP · Anchored · Distance % | value | `100 (close / FL18 - 1)` with FL18's anchor, frozen cohort and filter |
| FL46 | Flow Ratio | value | `100 N / D`; each side: its measure (gross buy `BV`, gross sell `SV`, net buy `BV-SV`, net sell `SV-BV`) of its cohort (every broker, selected brokers or Top-N ranked over the window by net buy, net sell, gross buy or gross sell) on its own board and investor filter; one unit for both (Rupiah `bv/sv`, Lot `bl/sl`, Transactions `bf/sf`) and one window; null when `D <= 0`. Refused (each with a message naming the side and the fix, and the rule with a right and a wrong example in the dialog): a net measure of every broker over both investor types (always 0); the same numerator and denominator, or gross buy against gross sell of every broker over both investor types on the same boards (always 100); selected brokers without a broker; no investor type or no board. Default: gross buy of the Top-3 (Foreign) over gross buy of every broker (the mock-up's first example) |
| FL47 | Net Buy Intensity | value | `100 Σ_b max(BV(b)-SV(b), 0) / BV(A)` over the window (default 5), every broker on the filter; or its percentile in the same history (baseline 252) |
| FL48 | Bandar Balance · Imbalance | value | each broker's net `n_b = BV(b)-SV(b)` over the window first; `B` = Σ of the N largest positive `n_b`, `S` = Σ `|n_b|` of the N largest negative; `(B - S) / (B + S)` or `B / S`; null unless N brokers on each side |
