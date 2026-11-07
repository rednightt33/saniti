# Screener flow entries vs Terminal FL01-FL48 (EXEC-SCREENER-FLOW-CANDLES, P0; 2026-11-07)

Read-only inspection (one agent, spot-checked). Sources: S = `apps/edge-bff/screener/src/core/screener-metrics.json`,
A = `verification/screener/AUDIT.md` (old FL numbers are defined in section 16.5, lines 2544-2842; decisions D1-D14 in
16.11, lines 3072-3091), F = `verification/terminal_api/flow_indicators/FORMULAS.md`,
R = `apps/edge-bff/terminal/src/data/flowRegistry.json`, T = `apps/edge-bff/terminal/src/calc/flow.ts`,
P = `apps/edge-bff/screener/src/core/presets.json`.

## Three rules that apply to every broker-based entry

- **G1, default board.** The registry defaults `boards` to `["Regular"]` on every FL with a board parameter (R; checked
  in a dump of R on 2026-11-07); `computeFlow` fills an omitted parameter from R (T:777-786). P8 b says all boards. A
  screener entry derived from R must therefore set boards = Regular, Nego, Cash by default. F:24-25 ("default: all")
  and F:119 / T:689 (FL39 "every board") disagree with R.
- **G2, calendar.** Terminal candles are price dates; broker rows on dates without a price bar are dropped (F:60-61,
  T:57). D12 (A:3089) chose market sessions. They differ on Nego-only days (81 stock-days of 15 stocks in 20 sessions)
  and on days without trades. Needs a user decision before P5.
- **G3, depth.** The screener's broker data holds 60 sessions (K1). A 252-session baseline (old FL05) cannot be
  computed; built-in baselines are capped (OPERATORS.md section 3).

## Screener entry -> Terminal FL

| Screener id (S line) | Old FL (A line) | Terminal FL | Match | What differs |
|---|---|---|---|---|
| silent (902) | – | FL27 | SAME | Terminal adds optional net/gross marks |
| adv20_idr (1111) | – | FL28 | SAME | — |
| fnet (1231) | FL01 (2549) | none | NONE | Rupiah foreign net exists only inside FL37 before the percentile (T671); its sign equals FL11 {all, Foreign, 20} |
| fpct (1289) | FL02 (2564) | FL11 | DEFAULTS | scope all, investors Foreign, window 20, boards all |
| fpart (1342) | FL03 (2579) | FL36 | DEFAULTS | scope all, boards all |
| fstreak (1398) | FL04 (2594) | FL26 | DEFAULTS | boards all; G2 (a no-trade day breaks the old run) |
| fsurprise (1454) | FL05 (2609) | FL37 | DEFAULTS | scope all, baseline 252 (capped by G3), boards; FL37 divides by the non-missing count |
| broker (1504) | FL06 (2624) | FL23 | PARTIAL | FL23 is cumulative from an anchor or daily, not a rolling D-session sum |
| topacc (1575) | FL07 (2639) | FL25 | DEFAULTS | top 5, boards all |
| buy_intensity (1644) | FL08 (2654) | FL11 (or FL46) | DEFAULTS | window 10, boards all |
| bandar (1711) | FL09 (2669) | FL24 | DEFAULTS | boards all; Terminal has reference lines, not named states |
| net_buy_hhi (1786) | FL10 (2684) | FL38 | DEFAULTS | boards all |
| conc_gap (1842) | FL11 (2699) | FL14 | DEFAULTS | unit value, window 20, boards all |
| breadth (1898) | FL12 (2714) | FL22 | PARTIAL | Terminal counts active brokers with net 0 and reports %; old rule excludes zero nets, 0-1 |
| bavg (1955) | FL13 (2729) | FL39 | DEFAULTS | window 10 (Regular matches D7) |
| dominant_persistence (2022) | FL14 (2744) | FL35 | DEFAULTS x100 | boards all; % instead of 0-1 |
| acc_days (2078) | FL15 (2759) | FL29 | DEFAULTS x100 | boards all; % instead of 0-1 |
| freq (2145) | FL16 (2774) | FL32 | DEFAULTS | boards all; G2 |
| trade_size_change (2210) | FL17 (2789) | FL33 | SAME | — |
| crossing_share (2268) | FL18 (2804) | FL30 | SAME | — |
| inst_retail (2308) | FL19 (2819) | FL34 | DEFAULTS | boards all; T646 uses today's classification (no point-in-time guard) |
| insider_net (2347) | FL20 (2834) | FL31 | SAME (insider part) | the major-holder part is lost |

So 21 of the 22 entries have a Terminal equivalent: 5 the same (silent, adv20_idr, trade_size_change, crossing_share,
insider_net for its insider part), 14 the same formula with other defaults, 2 partial (`broker` -> FL23, `breadth` ->
FL22); `fnet` has none. Counted from the Terminal side: 18 FL have a screener entry with the same formula (FL11 twice:
`fpct` and `buy_intensity`), 2 only a partial one (FL22, FL23), and 28 none: FL01-FL10, FL12, FL13, FL15-FL21,
FL40-FL48. (Corrected 2026-11-07: the first draft said 20 of 22 and named `broker` as having none, against its own
table.)

## Presets that use flow entries (P)

| Preset (line) | Condition | Terminal reproduction |
|---|---|---|
| bigacc (703) | bandar between 10 and 100 | FL24 {top 3, window 10, boards all} |
| fstreak (767) | fstreak > 4; fnet > 0 | FL26 {all, Foreign, 60, all boards} > 4; FL11 {all, Foreign, 20} > 0 (same sign) |
| silent (828) | silent (1.3, 4); bandar > 0 | FL27 {5, 20, 1.3, 4} = 1; FL24 > 0 |
| freq (885) | freq crosses above 2.5 within 3 | FL32 {tx, buy, 20, all boards} |
| bavg (952) | bavg between -3 and 3; bandar between 6 and 100 | FL39 {top 3, window 10, Regular}; FL24 |
| follow (1011) | broker {5, YP} > 1e9 | no exact FL; closest FL23 {[YP], value, start t-4} |
| qflow (1712) | fnet > 0 | FL11 as above |
| vacc (1797) | bandar between 6 and 100 | FL24 |

25 presets set `adv20_min_idr` = 1e9 (FL28).

## Formulas that have no Terminal equivalent (lost if the old entries are only replaced)

1. `fnet`: foreign net in Rupiah over D sessions (old FL01).
2. `broker`: one broker's net over a rolling D-session window (old FL06).
3. Old FL12 breadth with zero nets excluded (0-1) and its event FL12(5) - FL12(20).
4. Old FL15's distribution-day count (b_s < -x).
5. Old FL20's major-holder net (KSEI `pct_change`) with its origin and role filters.
6. Old FL10's effective number of buyers (1/H).
7. Old FL09's named states (Big Acc / Acc / Neutral / Dist / Big Dist) as a STATE test.
8. Old FL19's point-in-time n/a for past dates.
9. The D12 market-session calendar (G2).
10. Old FL05's 252-session baseline (G3).

Decisions needed before P5: G1 (override to all boards: follows P8 b), G2 (calendar), and what to do with items 1-8
(keep as screener-own entries, rebuild with the operators, or drop).
