# Broker summary for codes that are not four letters (EXEC-UNIVERSE-BROKER S3, stage 1)

`longcode_broker.py` fetches the `IDX_Broker_Summary` rows of warrants, structured warrants and other codes that are not
four letters, for the dates in `dates.json` (2026-09-01 … 2026-11-03, the dates the Railway loader skipped). It needs
Python 3.10+ and nothing else, and never touches the database. The upload is a separate step after S2.

## Run on a PC (Windows)

```
cd <repository>\scripts\broker_longcodes
set OUT=C:\Users\PC\Documents\claude\broker_longcodes
python longcode_broker.py probe    --out %OUT% --broker-list ZP,DR --codes 3
python longcode_broker.py discover --out %OUT%
python longcode_broker.py fetch    --out %OUT%
python longcode_broker.py check    --out %OUT%
python longcode_broker.py status   --out %OUT%
```

Each step asks for the Stockbit token with a hidden prompt (or reads `STOCKBIT_TOKEN`). It is never printed or saved.
A step that stops (network, a closed window, an expired token) continues where it stopped when it is run again.

## What each step does

| Step | Requests | What it gives |
|---|---|---|
| `discover` | 112 brokers × 6 filters × 46 dates ≈ 31 thousand | every code that is not four letters and traded that day, from each broker's own activity, with its buy/sell value and frequency |
| `fetch` | 6 per traded code-day (≈ 365 code-days on 2026-11-03) | the 15 table columns through the loader's own fetch (`broker_import.fetch_symbol_once`) |
| `check` | none | `rows/<date>.csv.gz` and `check_report.json` |

`check` holds back a code-day when it was not fetched, a required column is empty, the row date differs, a table key
repeats, or the two Stockbit sources (broker-first and ticker-first) disagree on any key's value or frequency.

## Measured (2026-11-05, from the cloud session through its proxy)

- 6 workers: `discover` 672 requests for one date in 85 s; `fetch` 12 code-days (72 requests) in 10 s.
- 2026-11-03: 365 codes found; the 12 fetched agreed with the broker-first source on every key.
- 2026-08-31, INET-W2 and PJHB-W: the same keys and the same values, lots and average prices as the table. Only
  `buy_freq`/`sell_freq` differ: the table holds NULL for these codes before 2026-09-01 (the former frequency staging
  table took four-letter codes only), the fetch gives the numbers.
