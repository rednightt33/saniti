# P4 — broker data for the Screener, one file per trade date

EXEC-SCREENER-FLOW-CANDLES P4 under EXEC-BROKER-DELTA (user 2026-11-07: per-date files for the Screener, "hari baru = satu
file baru, tanggal berubah = file tanggal itu diganti", one active copy per stock-date; compact file code; worker limits
unchanged; K1 window 60 sessions). This file is the contract between `apps/terminal-publisher` and `apps/screener-worker`.
P5 (flow computation) reads what P4 loads; P4 computes no indicator.

## 1. The file

- Index name in state.json `xsection`: `broker-YYYY-MM-DD` (the F05 `trade_date`). It matches terminal-api's
  `XSECTION_NAME` (`^[a-z0-9][a-z0-9_-]{0,31}$`), so terminal-api needs no change. Key:
  `v1/xsection/broker-2026-11-04.<first 16 hex of sha256>.json.gz` (`content_key('xsection', None, name, sha)`).
- Index entry: `{key, sha256, bytes, rows, as_of}` exactly as every xsection entry; `as_of` = the date (`2026-11-04`).
- Body: gzip (level 9, mtime 0) of compact JSON, the publisher's `encode`:

```json
{"schema_version": 1, "dataset": "xsection", "name": "broker-2026-11-04", "date": "2026-11-04",
 "source": "Feature_05_Foreign_Domestic_Broker_Detail",
 "units": {"bv": "IDR", "sv": "IDR", "bl": "lots (100 shares; odd lots as fractions)", "sl": "lots",
           "bf": "buy transactions", "sf": "sell transactions"},
 "means": {...plain sentences for every field, as the other xsection files...},
 "brokers": ["AK", "BK", ...],
 "investor_types": ["Domestic", "Foreign"],
 "boards": ["Regular", "Nego", "Tunai"],
 "tickers": [{"t": "AALI", "rows": 41}, ...],
 "columns": ["b", "i", "m", "bv", "sv", "bl", "sl", "bf", "sf"],
 "b": [0, 0, 3, ...], "i": [0, 1, ...], "m": [0, 0, ...],
 "bv": [...], "sv": [...], "bl": [...], "sl": [...], "bf": [...], "sf": [...],
 "gap": [["AALI", "Regular"], ...],
 "check": {"rows": 24512, "bv": 1234567890123.0, "sv": 1234567890123.0}}
```

- Rows: every Feature 05 row of that date whose ticker is a **stock** of the run's universe (`kind[t] == 'stock'`), ordered
  by ticker (code point order), broker, investor_type, market_board (the primary key order). `tickers` lists the tickers
  in file order with their row count; the column arrays hold the rows of all tickers back to back.
- `b`, `i`, `m`: indices into `brokers` (the distinct broker codes of this file, sorted), `investor_types` (fixed:
  Domestic, Foreign; the table's CHECK) and `boards` (fixed: Regular, Nego, Tunai; the table's CHECK).
- Numbers: a value that is a whole number is written as an integer (`1234` not `1234.0`); others as JSON numbers.
  `bf`/`sf` are integers or `null` (the source has none; for four-letter stocks K6 found 0 nulls since 2016).
- `gap`: the `[ticker, board]` pairs whose `source_balance_gap` is true (as `broker_doc`), sorted.
- `check`: rows, sum of `bv`, sum of `sv` over the file (sums as floats); the reader recomputes them.

## 2. Publisher (`apps/terminal-publisher/publisher.py`)

- `BROKER_DAY_SESSIONS = 60` (K1). The window is the 60 newest distinct `trade_date` of Feature 05, read with an index
  skip scan on `Feature_05_Foreign_Domestic_Broker_Detail_trade_date_idx` (recursive CTE over `max(trade_date) < t`;
  never `SELECT DISTINCT` over the table).
- Modes: `daily` and `backfill` maintain the files; a new manual mode `broker-days` rebuilds every window date (first fill,
  repair). Other modes carry the entries forward unchanged.
- In `daily`, a date is (re)built when:
  1. it is in the window and has no index entry (a new date, or the first fill);
  2. it is in `changed_dates` of a finished broker round: `Monitoring_Stockbit_Update` rows with `mode = 'APPLY'`,
     `status = 'SUCCESS'` and `finished_at` after state.json `broker_days_checked_at` (`features->'changed_dates'`, the
     dates `refresh.py` refreshed in Feature 05);
  3. on the daily sweep run (the existing `sweep` flag, 07:30 WIB), the per-date stamp (count, sum buy_value, sum
     sell_value of stock rows) differs from state.json `broker_day_stamps[date]` (the safety net for a Feature 05 change
     outside a round). Only that run aggregates the window.
- A built file whose sha256 equals the current entry is not put again (`store`). An entry outside the window is dropped
  from the index; `delete_replaced` deletes its object after the usual wait. One date failing keeps its previous entry and
  logs `broker_day_failed` (the class only); the run goes on.
- state.json gets two publisher-private fields: `broker_days_checked_at` (the newest round `finished_at` taken into
  account) and `broker_day_stamps` ({date: "rows=..;bv=..;sv=.."} for the dates built or checked). terminal-api's
  `STATE_FIELDS` does not serve them.
- One log line `broker_days` per run: window first/last, built (dates), carried, dropped, bytes, seconds, reasons.
- `verify` also checks every broker day file against SQL (rows and the decoded columns), like `verify_xsection`.
- Reading cost: a new date is one statement of about 24,500 rows; the first fill reads 60 dates (about 1.47 M rows, K6),
  a large read: run `scripts/restart_postgres.py` after it (AGENTS.md).

## 3. Worker (`apps/screener-worker`)

- The Phase 1 files (`price`, `actions`) stay required and unchanged. Broker day files are optional: the index entries
  named `broker-YYYY-MM-DD`, the newest 60 by date.
- Limits stay as they are (user 2026-11-07). A refresh downloads at most `SCREENER_MAX_REFRESH_BYTES` in total and every
  file at most `SCREENER_MAX_FILE_BYTES`: the Phase 1 files first, then the missing broker days newest first while they
  fit. Days that do not fit wait for the next refresh, which starts at once (not after the 60 s poll) until the window is
  complete. A file above the per-file cap fails the refresh as today.
- `/xsection` grants at most 16 names per call (terminal-api `MAX_XSECTION_NAMES`): the worker asks in batches of 16.
- Integrity: sha256 and size as every file; then the document: name and date equal the index name, `columns` as above,
  every column array the same length, the sum of `tickers[].rows` equal to it and to `check.rows`, indices inside their
  tables, the recomputed `check.bv`/`check.sv` equal within 1e-6 relative. A failure is the refresh's failure as for a
  Phase 1 file (keep the previous snapshot, `REFRESH_FAILED` with the code).
- A ticker of a broker file that the price snapshot does not have is not loaded (counted in the refresh log).
- Store, once per replica: per ticker its rows of every loaded date, ordered by date then the file order, in
  `SharedArrayBuffer` columns: date index (into the sorted broker date table), broker index (into one broker table, the
  union of the files' `brokers`), investor type and board (Uint8), `bv`, `sv`, `bl`, `sl` (Float64), `bf`, `sf` (Float64,
  `null` as NaN); one offset per ticker. Threads get typed views; a later P5 module reads a ticker's rows through one
  accessor on `ThreadSnapshot` (rows of a ticker in a date range).
- Skip-unchanged compares the Phase 1 files and the set of broker day names and sha256 together.
- Versions and data: `versions.flow_data` = sha256 over the sorted `name:sha256` of the loaded broker days (null when none);
  `data.flow_through` = the newest loaded broker date (null when none); `data.broker_window` =
  `{first, last, sessions, complete}` (`complete` false while days are still missing). The result cache key includes
  `flow_data`.
- Memory: about 1.47 M rows x 45 bytes, about 66 MB per replica (INFERENCE, measured after the build).
- Logs: the refresh line gains `broker_days` (loaded, cached, granted, missing, bytes).

## 4. Tests

- Publisher: window from the skip scan; new date built; changed round date rebuilt; unchanged date not put again; stamp
  check on the sweep run only; entry outside the window dropped; one failing date keeps its entry; encoding of whole
  numbers; verify catches a changed row.
- Worker: decode and integrity refusals (each rule); budget fill newest first and the follow-up refresh; batches of 16;
  skip-unchanged with broker days; flow_data/flow_through/broker_window; a ticker without price dropped; result cache
  key changes when a day changes.
- Local end to end: publisher-format files through the fake terminal (`tests/fake-terminal.mjs`).
