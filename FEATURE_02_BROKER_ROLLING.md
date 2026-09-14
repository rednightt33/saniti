# Feature 02 — broker rolling signals

> Correction in progress (2026-09-14): the production table documented below combines
> source Investor Types. The unreleased `Feature_02_Broker_Rolling_v2` shadow preserves
> Domestic and Foreign Investor Type as separate rows. The canonical table remains v1
> until the shadow passes full validation and atomic cutover. See
> [`FEATURE_02_BROKER_ROLLING_V2.md`](FEATURE_02_BROKER_ROLLING_V2.md).

`Feature_02_Broker_Rolling` uses every symbol present in `IDX_Broker_Summary`, including warrants and other instruments absent from the current `IDX_Stock_Universe`. The physical key is `(ticker, market_board, broker, date)`. `Regular`, `Nego`, and `Tunai` are separate market-board partitions; values never combine boards. To analyze regular-market flows, filter `market_board = 'Regular'` explicitly.

The primary key supports ticker/broker history queries. A separate `(date, market_board, ticker)` index supports daily cross-ticker consumers.

## Transaction-date calendar

For each ticker, the calendar is the ordered set of dates with at least one `IDX_Broker_Summary` row on **any** board. A 5D/20D/60D window means 5/20/60 such ticker transaction dates, not calendar days and not that broker's own active dates. A broker-board pair with no activity on a ticker transaction date contributes zero to rolling sums and activity counts. It does **not** create a Feature row on that date: output rows exist only where that ticker, broker, and board had a source row. A new ticker has `NULL` rolling values until the complete calendar window exists.

Domestic and Foreign `Investor Type` source rows are summed into one daily broker-board grain. `broker_type` and `broker_classification` come from the **current** `IDX_Broker_Profile`; they are not point-in-time classifications. A missing current profile leaves those metadata fields `NULL`, without dropping the source flow row.

The four abnormality fields compare today's rolling 20D/60D net value with the preceding 252 **complete rolling observations**, excluding today. Z-score uses sample standard deviation and is `NULL` if it is zero. Percentile is the exact empirical midrank `100 × (count(prior < current) + 0.5 × count(prior = current)) / 252`. Thus a 20D abnormality value first becomes eligible on ticker transaction date 272, and a 60D value on date 312. Complete definitions for all 38 columns are active in `Feature_Catalog` version `v1`; they were activated only after the full backfill passed validation.

## Validated historical coverage

The production backfill contains 42,598,713 rows across 4,125 source symbols, 111 brokers, and 2016-01-04 through 2026-08-31. Board counts are Regular 41,903,954, Nego 636,808, and Tunai 57,951. Exact source reconciliation found zero extra, missing, or mismatched 1D rows. Independent 31-field samples passed on all three boards, and a BBCA resume test inserted zero duplicate rows. See `DATABASE_CHANGELOG.md` for NULL rates, timings, catalog counts, and query-plan evidence.

## Refresh state and operation

The initial historical load uses `scripts/backfill_feature_02.py`. It aggregates source rows in PostgreSQL, creates a temporary daily stage, and inserts one ticker per transaction. A failed ticker rolls back, while prior completed tickers remain. Re-running the script skips tickers that already have Feature rows; this is **resume behavior, not incremental refresh**. A new load or correction for an already-loaded ticker, or a Broker Profile classification change, requires `--ticker SYMBOL --rebuild-ticker`, which transactionally replaces that ticker's rows from its current source history. Do not run a rebuild concurrently with the full backfill. No Feature 02 queue trigger or worker is deployed in v1; the existing Feature 01 price worker does not calculate Feature 02.

For a fresh table or interrupted initial load, obtain the Railway PostgreSQL TCP proxy host/port through the authenticated Railway CLI and keep `PGDATABASE`, `PGUSER`, and `PGPASSWORD` in the process environment only. Then run:

```powershell
python scripts/backfill_feature_02.py --host <proxy-host> --port <proxy-port>
```

`--ticker BBCA` is a controlled one-ticker test, `--ticker BBCA --rebuild-ticker` is a manual full-ticker refresh, and `--max-tickers N` caps newly populated tickers in a run. Do not use these options for a claimed full backfill. Do not edit raw broker tables or launch price ingestion to refresh this Feature.

For downstream use, check `Feature_02_Broker_Rolling` coverage and latest date against `IDX_Broker_Summary`. Broker-derived features can be newer or older than price-derived Feature 01. Cross-source analysis must use the minimum ready date of the broker and price sources.

`scripts/validate_feature_02.py --host <proxy-host> --port <proxy-port>` performs read-only source-versus-Feature board totals, coverage, sanity, and every calculated field's `NULL` rate. It scans the large tables and should be run after the backfill, not concurrently with a production ingest. Independent ticker examples and window boundaries must also be checked before recording a PASS.

`scripts/check_feature_02_sample.py --host <proxy-host> --port <proxy-port> --ticker BBCA --broker AK --board Regular --date 2026-08-31` independently recalculates all 31 numeric/window fields from at most 312 raw-source ticker dates. Change the key to test Nego, Tunai, illiquid symbols, and early listing boundaries. It reports expected, stored, difference, and PASS/FAIL for every field.
