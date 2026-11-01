# Fixed-income data audit (2026-11-01)

User 2026-11-01: "bisa dilakukan audit dulu, to ensure data quality-nya benar, dan bisa dilakukan sampling, gunakan script
yang digunakan untuk ingest baik price dan yield ke database ... price dan yield itu tidak semuanya tanggalnya ada ...
Siapkan mitigasinya apabila this is the case."

Method: `audit.py` (read-only).
- Every series of `Universe_Fixed_income` (48 = 24 instruments x price and yield; Indonesia 11, United States 13) is
  pulled again from TradingView with the ingest's own client (`apps/fixed-income-price-cron/fixed_income_update.py`
  `request_series`, up to 5000 daily bars).
- Each is compared date by date with `Price_Fixed_Income` (1D) through pgweb.
- Output: `audit_run.log`, `out/*.json`, `out/summary.json`.

## The source's daily label

A TradingView fixed-income daily bar is labelled with its session start in New York (`Fixed_Income_Market_Schedule.
provider_session`):

| Market | Session start | Label in EDT | Label in EST |
|---|---|---|---|
| US | 19:00 the evening before | 23:00 UTC the day before | 00:00 UTC of the trading day itself |
| ID | 17:00 the evening before | 21:00 UTC the day before | 22:00 UTC the day before |

Verified on US10Y around the switches of 2025-11-02 and 2026-03-08:
- labels move from 23:00 to 00:00 UTC;
- the database holds Monday 2025-11-03 = 4.108, the value of the bar labelled 2025-11-03 00:00 UTC.

`session_date()` in `audit.py` reads the label in the provider's zone against the session start. It does not depend on
daylight saving.

## Results (dates by `session_date`)

| Check | Indonesia (22 series) | United States (26 series) |
|---|---|---|
| Database dates equal to source | all | all, but US10Y yield 5 extra |
| Values equal | all but 2026-10-05..09 and 2026-10-26..28 (0-8 dates a series) | all 25, US10Y yield: 610 dates differ |
| Source dates missing in the database | 2026-10-12 (all 22) | 2026-10-21 (all 26) |
| Live loader date rule (`resolve_bar_date`, `NEXT_BUSINESS_DAY`) vs session date | equal on every bar | differs on every EST bar (343-1715 a series), 4-19 collisions a series |

Findings:
1. **Live loader date rule wrong in EST (US)** — ERRORS M323.
   - "UTC calendar date + 1 business day" is right only in EDT.
   - EST started 2026-11-01. From the first Monday session, the US crons would not find the target bar, then write
     each bar one business day late.
   - The stored history is right: it was loaded on 2026-10-11 by another path.
2. **Indonesia 2026-10-05..09** — ERRORS M324.
   - Written on 2026-10-12 under the old `CURRENT_OR_PREVIOUS_BUSINESS_DAY` rule, so each holds the previous session's
     bar, one business day early.
   - 2026-10-12 (ID) and 2026-10-21 (US) are missing.
3. **Late source revisions** — ERRORS M324.
   - Indonesia short tenors on 2026-10-26..28 differ from the source today, e.g. ID01MY yield 10-26: database 6.454,
     source 6.354.
   - The recovery window (5 sessions) will no longer cover 10-26 after the next run.
4. **US10Y yield 2016, 2018, 2021** — ERRORS M324.
   - 610 closes differ by 0.2 bp (median) to 1.8 bp (max).
   - 5 rows on US holidays that the source does not have: 2016-01-01, 2016-11-24, 2021-01-01, 2021-04-02, 2021-05-26.
   - Every other US series matches exactly.

## Price-only and yield-only dates

Price and yield are separate TradingView symbols with different calendars. The gaps are the SOURCE's: for every series
the database holds exactly the source's dates (finding 2 aside).

| Group | Dates only in yield | Dates only in price |
|---|---|---|
| ID 1Y-30Y | 110-118 | 11-21 |
| ID 1M, 3M, 6M | 25-39 | 4-17 |
| US | 0-37 | 1-37 |

Price and yield move opposite ways on most days with both, e.g. ID10Y 2,266 opposite vs 98 the same way. US bill
"price" is a discount quote (`value_unit` PCTDY), not percent of par.

Mitigation (proposed, for the Terminal plan):
- Each metric is its own series on its own dates. A missing date is never filled with an invented value, and yield is
  never computed from price or the reverse (no coupon or maturity data).
- Where both are shown for one date, the missing side reads "No price quote on this date" (or yield).
- As an overlay on another chart, the last value is carried for at most a few business days and marked as carried; a
  longer gap breaks the line.
- The rack carries per series its first and last date, rows, and the count of dates the other metric lacks, so the page
  can say so.
