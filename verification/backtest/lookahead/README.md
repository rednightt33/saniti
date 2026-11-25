# Look-ahead check on real data (EXEC-BACKTEST-REVAMP P6.4)

The CI gate (`.github/workflows/backtest-lookahead.yml`: `apps/backtest-worker/tests/lookahead.test.ts`, `pit.test.ts`,
`flow-grammar.test.ts`, `grammar.test.ts`) runs on synthetic data. This folder runs the same rule on dev's data: a value
on day t may use only data up to t, so every series the Backtest reads is computed on the whole data and on the data
cut at four days t, and every value on a day up to t must be equal. Since the re-check of 2026-11-25
(`wf_c2fe2424-bf4/screener:recheck2/NEW-1`) each series is also cut on days where it changes, the CI gate's rule
(`apps/edge-bff/screener/tests/core/cuts.ts`: a read of the next bar in a sparse series, a flag, a candle, a category,
shows only there); a derived cut's data is built for its series and dropped. The report adds `derived_cuts` (how many
such cuts were read) and `unchanged` (the series that never change after the first cut on that stock: the check cannot
see a read of a later bar in them; not a leak). On the gate's synthetic AAAA and BBBB exported this way, with every
candle shifted one bar ahead: 4 of 20 caught on the four days, 18 with the derived cuts (the other two fire on neither
at their defaults, `unchanged`).

1. `export.sh TICKER FROM TO OUTDIR`: the ticker's daily prices (`Price_Stock_Indonesia_IDX`, timeframe Daily) and broker
   rows (`IDX_Broker_Summary`, year by year) through the pgweb service's HTTP API (read-only role). `PGWEB_HOST` and
   `PGWEB_AUTH` come from the environment (the pgweb service's variables on Railway) and are never written.
2. `real_data.ts DIR...` (from this folder, with the worker's loader): the 53 indicators at their defaults, the
   price-action types, the 20 candles, four grammar tests, the clean Flow indicators at their defaults and the eight
   point-in-time ones (anchor 60 sessions after the first broker day). It prints a JSON report and exits 1 on a leak.

## 2026-11-15

`results_2026-11-15.json`: BBRI (large bank), GOTO (technology, listed 2022), COCO (small, a rights issue on
2026-07-09), ALKA (thinly traded), 2023-01-02 to 2026-11-13, 889 to 920 bars and 14,380 to 89,483 broker rows each:
168 series per stock (76 indicator outputs, 8 price action, 20 candles, 4 grammar tests, 44 Flow A-C series, 16
point-in-time series), **0 leaks**. The 10 refusals per stock are the `sell` lines of the Flow indicators whose default
side is buy (the line is drawn only with side sell or both), as expected.

## With the broker basis (2026-11-16, EXEC-BACKTEST-REVAMP P9)

`../basis/basis_from_export.py out/BBRI out/GOTO out/COCO out/ALKA` writes each ticker's `basis.json` (the publisher's
rule on the exported rows and the ticker's actions); `real_data.ts` then puts the lots on the price basis, keeps the
basis whole at every cut, and reports the sessions still off the price basis with and without the factors.
`results_2026-11-16.json`: 168 series each, 0 leaks on the four; COCO 799 sessions off without the factors, 0 with
them (rights issues 2025-10-09 factor 2.7097 and 2026-07-09 factor 1.7429); BBRI, GOTO, ALKA 0. Actions before the
export's first date read as unresolved (no sessions measured) and mask only the windows across them.

## 2026-11-23 (EXEC-PINE-INDICATORS, before the beta release of the seven lab indicators)

`results_2026-11-23.json`: BBRI, BBCA, GOTO, COCO, 2023-01-02 to 2026-11-23 (895 to 926 bars, 24,509 to 89,483 broker
rows), with the broker basis: 214 series per stock (122 indicator outputs, among them every output of the lab
indicators I54 to I60 through the worker's '@edge-lab' registration, 8 price action, 20 candles, 4 grammar tests, 44 Flow
A-C, 16 point-in-time), **0 leaks** on the four. The 10 refusals per stock are the same as on 2026-11-16 (the eight
`sell` lines of buy-side Flow indicators and FL34's two metrics). COCO 799 sessions off the price basis without the
factors, 0 with them; the other three 0.

## 2026-11-25 (EXEC-PRICE-DISTORTION and EXEC-SENSITIVITY-FLAGS, before their release)

`results_2026-11-25.json`: BBRI, BBCA, GOTO, COCO, 2023-01-02 to 2026-11-25 (897 to 928 bars, 24,509 to 89,483 broker
rows), with the broker basis from the publisher's rule as changed by EXEC-PRICE-DISTORTION (`price_check_side`; COCO's
two rights issues read `adjusted`, as before), on the branch head where every Flow value is kept and only marked
(`basis.ts basisDistorted`): 214 series per stock, **0 leaks** on the four. The 10 refusals per stock are the same as on
2026-11-23. COCO 799 sessions off the price basis without the factors, 0 with them; the other three 0.

## 2026-11-25, the release head (after re-check round 1, UD52 and UD55)

`results_2026-11-25_release.json`: the same four stocks and dates, on the head that goes to the beta: the R3 rule (a
point-in-time or window value on a bar before an action's `decided` date reads the traded lots, `grammar.ts`
pointInTime, `pit/series.ts`), the publisher's closes either side of the ex date (`basis_from_export.py` passes them as
`sides`, as `BASIS_SIDES_SQL` reads them), the cuts derived where each series changes (`derived_cuts` 305 to 356 per
stock) and the history class per setting (UD52) with the effective window (UD55): 214 series per stock, **0 leaks** on
the four. The 10 refusals per stock are the same as on 2026-11-23; `unchanged` 2 (GOTO 5). COCO's two rights issues read
`terms` and `adjusted` (factors 2.7097, 1.7429); COCO 799 sessions off the price basis without the factors, 0 with them;
the other three 0.

## 2026-11-26, after re-check round 2 (M566)

`results_2026-11-26_round2.json`: the same four stocks and dates on the head with round 2's fixes (a trade's flags on
the stock's own bar, B2-1; the windows measured on breaks of every size the data holds, H2-1; the side read as the
publisher wrote it, P2-2): 214 series per stock, **0 leaks** on the four; the 10 refusals per stock as before. The
fixes change marks and flags only, never a value, so the series equal those of `results_2026-11-25_release.json`.
