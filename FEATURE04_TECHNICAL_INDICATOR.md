# Feature04 technical indicators

User execution instruction received 2026-10-11: create `Feature04_Technical_Indicator`,
implement and validate a reusable engine, without source changes, full historical backfill,
model training, new services/databases, permissions changes, or automatic scheduling.

Subsequent user instruction on 2026-10-11 authorized the reviewed four-column extension
and full historical backfill for every ticker actually present in the price table, one
ticker at a time, from its earliest observation through its latest available date.
The v2 table had 46 columns. A separate monitoring table stores atomic per-ticker load
metadata; source prices, grants, deployments and schedules are unchanged.

The next user instruction authorized SMI and the eight swing-state variables from
the supplied HH Pine script, starting with BBCA only, followed by "Sure" and a request
for Markdown definitions of every column. `break_swing_high` is INTEGER 1/0 as requested.
The v3 schema had 55 columns. After the BBCA checkpoint, user authorized
"Alright, proceeed untuk semua ticker." The serial v3 replay now covers every actual
price-source ticker: 844 tickers / 1,318,633 Daily rows. Existing indicator values and
BBCA payload/timestamps are preserved. See [all column definitions](FEATURE04_COLUMN_DEFINITIONS.md),
[full SMI validation](verification/feature04/SMI_ALL_TICKERS.md), and
[initial BBCA SMI checkpoint](verification/feature04/SMI_BBCA.md).

The next approved extension makes the same Feature04 formulas available for fixed-income
price candles. Migration `20261011_006_extend_feature04_to_bonds.sql` appends
`asset_type`, making 56 physical columns, and changes the identity to
`(ticker, trade_date, timeframe, asset_type)`. Classification is data-driven on every
enqueue/load: membership in `IDX_Stock_Universe` means `equity`; membership in
`Universe_Fixed_income` means `bonds`; absent or ambiguous membership fails closed.
No ticker list is embedded in Python or SQL.

## Verified source and mapping

Inspection: `verification/feature04/inspection.json`, read-only live `lucid-patience / dev / Postgres`.
Equity source: `public."Price_Stock_Indonesia_IDX"`, owner `postgres`, primary key `(ticker,date)`.
Bond source: `public."Price_Fixed_Income"`, restricted to `metric_type='price'` and
`"Timeframe"='1D'`, with primary key `(tradingview_symbol,date,metric_type,"Timeframe")`.

| Target / input | Verified source | PostgreSQL type | Meaning |
|---|---|---|---|
| ticker | ticker | varchar(4), NOT NULL | Trimmed upper-case IDX code; one exchange-qualified symbol per ticker |
| trade_date | date | date, NOT NULL | Observed daily candle date, Asia/Jakarta exchange date |
| timeframe | timeframe | varchar(32), NOT NULL | Actual value `Daily`; copied, never synthesized |
| OHLC | open, high, low, close | numeric(24,8), NOT NULL | Source price inputs, converted to float64 for calculation |
| Volume | volume | numeric(30,8), NOT NULL | Source volume used for input QC; not an indicator input in this feature set |
| Symbol / exchange | tradingview_symbol | varchar(32), NOT NULL | Actual exchange `IDX`; verify `IDX:` + ticker |
| Provider | source | varchar(64), NOT NULL | Actual value `TradingView` |
| Source last write | ingestion_time | timestamptz, nullable | Last database insert/upsert time; not an immutable revision ID |
| Query date | query_date | date, NOT NULL | Source query date, not historical publication proof |
| Asset class | universe membership | text, NOT NULL | `equity` from `IDX_Stock_Universe`; `bonds` from `Universe_Fixed_income` |

There were 1,318,633 rows, 844 securities, 2018-01-02 through 2026-10-09,
238,436,352 bytes including indexes, and 62–2,113 observations per ticker.
There were zero duplicate ticker/date/timeframe combinations, missing OHLCV, invalid
OHLC relationships, nonfinite inputs, weekend rows, or noncanonical ticker strings.
There were 40 zero-volume bars (valid and retained), no zero closes, and 1,303,726
rows without ingestion timestamps. The per-security counts and dates are in the inspection.

The source has nonnegative and OHLC-range checks, a ticker/date primary key,
a date index, and existing price-change/Feature01 tracking triggers. They are untouched.
Current price ingestion explicitly requests TradingView `1D`, regular session,
and split adjustment (`apps/idx-price-cron/price_update.py`). This is verified code intent;
there is no per-bar adjustment vintage or independently verified consistency for older
imports. No dividend/total-return adjustment is claimed. Only observed dates are used;
weekend absence is verified, while completeness against an authoritative IDX holiday calendar
is NOT VERIFIED. Source selection can carry survivorship bias.

## One physical wide table

Target: `public."Feature04_Technical_Indicator"`. Exactly 56 columns after the cross-asset extension:
4 identities, 15 floating-point indicators, 25 independent INTEGER patterns,
one INTEGER inside-bar flag, nine SMI/swing fields, and 2 calculation metadata fields. Primary key and its B-tree index:
`(ticker,trade_date,timeframe,asset_type)`. This supports asset/ticker/date-range queries filtered by the
single normalized `Daily` timeframe. No speculative extra index, foreign key into the source,
new PostgreSQL routine, or grant is added. The existing catalog-only validator
`public.validate_feature_catalog_target()` gains one exact-name exception for this table;
its physical-column and VERIFIED-table checks are unchanged. The original function is
retained in `verification/feature04/catalog_validator_before.sql`. No new source dependency constrains source writes.

| Group | Columns | Types / nullability |
|---|---|---|
| Identity | ticker, trade_date, timeframe, asset_type | TEXT, DATE, TEXT, TEXT; NOT NULL |
| Trend | sma_20, sma_50, ema_12, ema_26, ema_50, ema_200 | DOUBLE PRECISION; nullable |
| Trend strength | adx_14 | DOUBLE PRECISION; nullable; 0–100 |
| Momentum | rsi_14, macd, macd_signal, macd_histogram | DOUBLE PRECISION; nullable |
| Volatility | atr_14, bb_upper_20, bb_middle_20, bb_lower_20 | DOUBLE PRECISION; nullable |
| Patterns 1–13 | cdl_piercing, cdl_morning_star, cdl_morning_doji_star, cdl_engulfing, cdl_3_white_soldiers, cdl_hammer, cdl_inverted_hammer, cdl_3_inside, cdl_3_outside, cdl_harami, cdl_harami_cross, cdl_dark_cloud_cover, cdl_evening_star | INTEGER; nullable |
| Patterns 14–25 | cdl_evening_doji_star, cdl_3_black_crows, cdl_shooting_star, cdl_hanging_man, cdl_doji, cdl_dragonfly_doji, cdl_gravestone_doji, cdl_marubozu, cdl_kicking, cdl_rise_fall_3_methods, cdl_mat_hold, cdl_hikkake | INTEGER; nullable |
| Metadata | calculation_version, calculated_at | TEXT, TIMESTAMPTZ; NOT NULL |
| Current-candle range pattern | inside_bar | INTEGER; nullable; only 0 or 1 |
| SMI / swing prices | smi, temp_high, temp_low, last_swing_high | DOUBLE PRECISION; nullable |
| Swing states / trigger | tracking_high, tracking_low, break_swing_high | INTEGER; nullable; only 0 or 1 |
| Provisional peak/trough positions | temp_high_bar, temp_low_bar | INTEGER; nullable; zero-based source bar indices |

Complete executable DDL and per-column metadata:
`database/migrations/20261011_001_create_feature04_technical_indicator.sql`.
The applied creation migration remains immutable. Forward migration
`20261011_002_extend_feature04_and_backfill_log.sql` appends adx_14, ema_50, ema_200,
and inside_bar after the original 42 physical columns; existing columns are not reordered.
`20261011_003_add_feature04_smi_swing.sql` appends the nine SMI/swing fields after those 46.
`20261011_004_record_feature04_smi_full_coverage.sql` updates coverage/evidence metadata
only after the all-source v3 load; no formula, physical-column or permission change.
The creation migration fails if the target already exists or the verified source contract changes.
Existing `Table_Catalog`, `Column_Catalog`, and `Feature_Catalog` receive definitions
for the feature table and all 56 columns. All 56 active definitions use v4 semantics; 42 v1 and
46 v2 definitions are retained inactive. Unchanged formulas were copied to v3; the
subsequent data replay preserves old indicator values while updating new fields and
version/timestamp only where the payload changes. One exact-date ONE_TO_ONE relationship with
Feature01 is registered (Daily only; no point-in-time sector validity implied). It does not activate AI tools or alter the seven-table
AI allowlist. AI onboarding is separate; physical XGBoost-compatible layout is not training eligibility.

## Exact implementation contract

`features/feature04/engine.py`: pure, causal calculations, no database connection.
`features/feature04/pipeline.py`: bounded read / optional idempotent UPSERT.
`features/feature04/backfill.py`: authorized serial full-history ticker loads, temporary
COPY staging, verified UPSERT and an atomic persistent per-ticker audit.
`features/feature04/specs.py`: per-column formulas, units and usage guidance.
`features/feature04/swing.py`: Pine first-input-seeded SMI and literal closed-bar state replay.
Dependencies are pinned in `requirements.txt`; exact environment lock is `dependencies.lock`.
TA-Lib Python 0.6.8 / C 0.6.4, NumPy 2.3.5, psycopg 3.2.13.
Current engine version `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`;
all source-ticker rows now use v3 (v2 is the earlier historical checkpoint). Default TA-Lib compatibility, zero unstable
periods (including ADX), and library default candle settings.

| Indicator | Definition / initialization | First valid bar (1-based) |
|---|---|---|
| SMA20 / SMA50 | Arithmetic mean of 20 / 50 valid chronological closes | 20 / 50 |
| EMA12 / EMA26 | SMA of first 12 / 26 closes seeds recurrence; alpha 2/13 or 2/27 | 12 / 26 |
| EMA50 / EMA200 | SMA of first 50 / 200 closes seeds recurrence; alpha 2/51 or 2/201 | 50 / 200 |
| ADX14 | TA-Lib Wilder directional-movement/true-range smoothing and 14-period smoothing of DX; strength, not direction; native zero-denominator convention | 28 |
| RSI14 | 14 close changes; SMA seed of gains/losses then Wilder RMA alpha 1/14; native both-zero result 0 | 15 |
| MACD line | Stored EMA12 minus stored EMA26 | 26 |
| MACD signal | EMA9 of valid MACD, SMA of first 9 valid MACD observations seeds it | 34 |
| MACD histogram | MACD line minus signal | 34 |
| ATR14 | TR=max(high-low,abs(high-prior-close),abs(low-prior-close)); initial prior close needed; 14 TRs seed Wilder RMA | 15 |
| BB20/2 | SMA20 ± 2 population stddev (`ddof=0`); middle=SMA20 | 20 |

MACD is composed from the exposed EMA columns; it intentionally avoids TA-Lib MACD's
internal fast-EMA reseeding, so `macd=ema_12-ema_26` holds at every available row.
ATR uses TA-Lib's first-TR convention, which can differ from TradingView's first-bar high-low.
EMA/MACD chart seeds can also differ. These choices are versioned and calculation-tested;
TradingView initialization and numerical parity remain NOT VERIFIED.

All 25 TA-Lib functions, actual default penetration parameters, and lookbacks are captured
in `verification/feature04/calculation_validation.json`. Morning/evening star functions use
penetration 0.3; dark-cloud cover and mat-hold use 0.5. Candlestick lookbacks range from
2 to 14 prior bars. Leading native zero output before the lookback is masked to NULL;
post-lookback zeros, signed detections, and native non-100 magnitudes are preserved.
Multiple patterns can coexist; no qualitative label, rating, probability or win rate is generated.

Inside bar is a separate two-candle range test: high[current] < high[previous] AND
low[current] > low[previous]. It labels the current closed Daily candle with 1, or 0
for an available non-detection; equal boundaries are excluded. The first valid candle
of each segment is NULL because no usable predecessor exists. Original numeric prices
are compared without float64 rounding. No later candle or breakout confirmation is read.
`cdl_3_inside` remains the independent TA-Lib three-candle reversal pattern.

Invalid or missing OHLC yields NULL features for that row and restarts all feature history
conservatively. Equity requires nonnegative volume; bond price candles permit NULL volume
because the verified fixed-income source does not publish it and none of these formulas uses
volume. Zero volume is valid. Missing dates are not inserted or forward-filled;
windows count valid observed bars, not calendar days. Each ticker is sorted and isolated.
No future price or forward target is read into an observation's calculations.

### SMI and closed-bar swing replay

SMI uses rolling high/low length 14, double EMA smoothing 5/5, and thresholds ±40.
Its internal EMAs seed with the first available input and rolling extrema use partial
windows at startup, matching the supplied Pine formula rather than TA-Lib EMA seeding.
All nine fields are the state after the current bar's blocks execute. A high is confirmed
only on SMI crossing below +40; the peak's earlier date is never retroactively marked
as a confirmed feature. Temporary prices/indices clear on confirmation; the last
confirmed high remains until replaced, including after a breakout. The original script
does not retain a last confirmed low.

`break_swing_high` is 1 when today's close exceeds today's confirmed high and yesterday's
close was at or below yesterday's confirmed high; both levels must exist. Otherwise
it is 0 on a valid processed bar. Before the first confirmation it is 0, not NULL;
uncomputed tickers/invalid OHLCV remain NULL. A changing level can contribute to a
cross, and multiple triggers of the same level are allowed. No additional SMI filter
at breakout or one-shot lock is added. The trigger date is the existing trade_date.
Intrabar alert behavior cannot be reconstructed from closed Daily OHLC.

Full definitions, threshold-equality behavior, zero-based source index meaning and
null rules: `FEATURE04_COLUMN_DEFINITIONS.md`. The initial BBCA-only execution was followed
by the authorized full-source-ticker v3 replay; see `verification/feature04/SMI_ALL_TICKERS.md`.

## Incremental / correction design

Every refresh reads all available history for each requested ticker through output end,
calculates once in chronological order, and writes only the explicit output range.
This avoids unverified fixed-window recursive state and supports exact reproducibility
relative to the available source snapshot. No cached recursive state is stored.
An old correction requires output refresh from its earliest changed bar through the latest
wanted bar because EMA, RSI, ATR and MACD can affect every later value. There is no automatic
correction detection or scheduled writer. The subsequently authorized all-source-ticker
historical load uses full-history replay, with one atomic ticker commit.

A repeatable-read transaction supplies one consistent source snapshot. The writer takes
an advisory lock specific to Feature04; it never locks or rewrites source pipelines.
UPSERT updates values/version/timestamp only when the feature payload changes. An identical
rerun preserves `calculated_at`. A source revision yielding identical features is recorded in
the external manifest, without manufacturing a version in the table. The manifest contains
actual source-row serialization SHA256, ticker/range/row counts, versions and statuses;
it is an extraction fingerprint, not an immutable historical source-vintage claim.
Concurrent source correction after the snapshot needs a subsequent refresh.

The bounded refresh CLI defaults to dry-run and requires 1–10 explicit tickers, start/end dates (output
range <=366 days), and a manifest path. At most 5,000 output rows; no all-universe option.
An example dry-run (credentials held only in the environment):

```bash
python features/feature04/pipeline.py --tickers BBCA GOTO \
  --start 2026-10-01 --end 2026-10-09 --manifest /tmp/feature04-run.json
```

`--write` is an explicit bounded write mode for an authorized refresh. No scheduler,
service deployment or source-price request is required to calculate existing observations.

### First committed bounded backfill test

User approved one ticker and one month on 2026-10-11, starting from the oldest source data.
BBCA January 2018 produced 22 committed Daily rows, 2018-01-02 through 2018-01-31;
all stored values were read back and an identical rerun changed 0 rows, preserving timestamps.
There is no source history before this month in the database: SMA50, EMA26 and MACD
remain NULL, while SMA20/Bollinger first become available on January 29. Warmup NULLs
are expected availability markers, not a failed backfill. Later authorized months must
continue reading full available history through their end while writing only their own range.
At that first-test checkpoint no later month, other ticker or full-universe backfill had executed. Source rows and all
unrelated target rows were preserved. Evidence: `verification/feature04/BACKFILL_BBCA_201801.md`.

### Authorized full historical load and resume

The separate backfill command accepts explicit --tickers (1–10 canonical source codes)
or discovers all actual tickers with --all-source-tickers, never from current listed-universe
membership. The two scope options are mutually exclusive. Within each ticker it reads every available
observation in ascending date order, calculates once, and writes at most 5,000 rows in one
repeatable-read transaction. Only one ticker is processed at a time; an advisory lock
coordinates Feature04 writers. The ordinary refresh command retains its existing limits.

`public.feature04_backfill_log` is monitoring metadata, not an additional feature layout.
Its primary key is (run_id,ticker), with source date span/count/hash, output hash excluding
calculated_at, version, timestamps, changed-row count and COMPLETED/FAILED status.
Outputs are read back column by column before their COMPLETED log commits in the same
transaction. A failed ticker rolls back; prior ticker commits remain intact. No source
ingestion timestamp is fabricated to fit the Feature01 calculation log's timestamp contract.

Resume with the same run UUID. A completed ticker is skipped only when its source hash,
current computed payload and actual target readback still match its audit. A changed source
snapshot is recalculated; identical payloads preserve calculated_at. The source SHA is an
extraction fingerprint, not proof of historical publication or an immutable revision vintage.

```bash
python features/feature04/backfill.py --all-source-tickers \
  --run-id 96ffcd2f-74f7-4437-a002-15a6aeb4b1f9 \
  --manifest /tmp/feature04-full-backfill.json --write
```

Use --write only within an authorized execution. Default mode is read-only dry-run.
Full execution completed for 844 tickers and 1,318,633 observations, with zero missing/extra source keys.
Evidence is in `verification/feature04/FULL_BACKFILL.md`.

## Automatic calculation and failure-only retry

Migration `20261011_005_automate_feature04.sql` adds a transactional price trigger,
coalesced per-ticker queue, per-column readiness, immutable attempt log, execution/ticker
monitoring, Telegram retry audit, and notification outbox. The existing scheduled price
services remain the clock. The new always-on `feature-04-worker` has no cron and never
queries TradingView.

Every relevant committed price change increments the ticker's source generation and keeps
the earliest dirty date. The worker replays the ticker's complete available history because
recursive indicators and swing state can propagate an old correction through the latest
bar. A generation/revision check immediately before UPSERT prevents a stale calculation
from becoming current. One ticker failure is retried and reported independently while other
tickers continue.

Formula groups expose diagnostic outcomes. MACD, Bollinger, and the complete SMI/swing state
are indivisible dependency bundles. A Telegram column retry therefore recalculates the
dependency closure; full-ticker retry is used for script/worker failure. Retry controls only
appear for `FAILED`/`BLOCKED` state. Expected NULLs remain `SUCCESS`. User clarification:
"Termasuk NULL yang seharusnya sudah tersedia". Availability validation checks every bar in
the selected output, using each indicator's warmup, the native candlestick lookback, and the
conditional Pine state. A missing required historical value is also a failure. Warmup resets
after invalid OHLCV; zero-range SMI and absent provisional/confirmed swing levels stay valid
NULLs. Any failing member withholds its entire dependency bundle from the write.

Price monitoring commits before its event is sent to `telegram-monitor`. Feature04 can
calculate concurrently, but its outbox is deliverable only after the price notification is
recorded sent. The second message is emitted after all eligible tickers are terminal.
Delivery errors retry outside the calculation transaction.

Fixed income keeps its independent Railway schedules: `fixed-income-daily` runs at
`0 10 * * *`, and `fixed-income-recovery` runs at `0 23 * * *`. Their source code is not
coupled to Feature04. A row trigger on relevant `Price_Fixed_Income` price/1D changes
coalesces the affected bond ticker into the same worker queue. A separate trigger on the
committed `Monitoring_Fixed_Income` record opens and seals the corresponding Feature04 run,
attaches only price series written during that source execution, and creates a durable
`PRICE_FIXED_INCOME` notification event. The worker dispatches that price event to
`telegram-monitor`; only after Telegram records it as sent may the related Feature04
completion event be dispatched. Thus each fixed-income cron is tracked in this order:
source monitor committed, fixed-income price Telegram sent, eligible bond calculations
terminal, Feature04 Telegram sent. Price or Telegram failure never rolls back committed
source data, and one bond failure does not block other tickers.

## TradingView reference and current limitations

Official definitions reviewed 2026-10-11:
[SMA](https://www.tradingview.com/support/solutions/43000696841-simple-moving-average/),
[EMA](https://www.tradingview.com/support/solutions/43000592270-exponential-moving-average/),
[RSI](https://www.tradingview.com/support/solutions/43000502338-relative-strength-index-rsi/),
[MACD](https://www.tradingview.com/support/solutions/43000502344-moving-average-convergence-divergence-macd-indicator/),
[ATR](https://www.tradingview.com/support/solutions/43000501823-average-true-range-atr/),
[BB](https://www.tradingview.com/support/solutions/43000501840-bollinger-bands-bb/),
and [TA-Lib functions](https://ta-lib.org/functions/).

Intended chart benchmark: exact `IDX:ticker`, regular session, 1D closed bars,
matching price adjustment/history, close input, SMA20/50, EMA12/26, RSI14,
EMA/EMA MACD12/26/9, RMA ATR14, SMA/population-standard-deviation BB20/2,
no plot offset or additional smoothing. No reference chart/export values were supplied.
The Python SMA20 was independently checked against 20 actual source closes; this does
not prove TradingView equality. TA-Lib pattern recognition is a separate definition family.

**TradingView numerical parity: NOT VERIFIED.**
**Final point-in-time XGBoost training eligibility: NOT VERIFIED.**
Prediction timestamp and target horizon are undefined; historic source availability,
corporate-action vintages, and survivor coverage are incomplete. No labels or model
training are produced. Peer scaling, collinearity (SMA20/BB middle), missing-value treatment,
walk-forward splits and target design remain future training decisions.
