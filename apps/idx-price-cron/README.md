# IDX daily price cron

This short-lived Railway service updates `public."Price_Stock_Indonesia_IDX"` from TradingView without creating a local CSV.

## Schedule

Railway evaluates cron schedules in UTC. The service uses `0 10,23 * * *`:

- `10:00 UTC` = `17:00 Asia/Jakarta`: query every ticker in `public."IDX_Stock_Universe"` (`DAILY`).
- `23:00 UTC` = `06:00 Asia/Jakarta` on the following day: query only the prior run's missing tickers (`RECOVERY`).

The same command runs at both times. `--mode auto` chooses the phase from the current Asia/Jakarta hour.

## Data rules

- Ticker, TradingView symbol, exchange, and asset type come from `IDX_Stock_Universe`.
- Asset type is the live `Security Type` value; it is not hard-coded.
- Prices are deduplicated in memory and bulk-upserted through a temporary PostgreSQL staging table.
- The `Price_Stock_Indonesia_IDX` primary key `(ticker, date)` is the final duplicate guard.
- Run results are upserted into `Monitoring_Price_ALL` per exchange, asset type, target date, and run type.
- There is no automatic third TradingView query. Missing symbols after recovery are marked `NEEDS_REVIEW`.
- Weekend runs are recorded as `SKIPPED` without querying TradingView.
- If a weekday `DAILY` run dies before writing monitoring, the 06:00 recovery derives its scope from universe tickers still absent from the price table for that date.

## Runtime

Production command:

```text
python price_update.py --mode auto
```

Required variable:

```text
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

The script must exit after each run so Railway can start the next cron execution.
