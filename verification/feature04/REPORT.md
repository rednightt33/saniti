# Feature04 execution report — 11 October 2026

Completed on `lucid-patience / dev / Postgres` with the supplied Railway project token.
Only the requested feature table and directly required metadata were changed.
No source row, source trigger, source index, role grant, existing service, deployment,
configuration, automatic price/Feature01 pipeline, or schedule was changed.
The private-network execution sandbox was temporary and is removed after verification.

| Stage | Execution status | Evidence |
|---|---|---|
| Database inspection | INSPECTED | inspection.json: live source, schema, grain, quality, per-security coverage |
| Indicator/key definition | DESIGNED | FEATURE04_TECHNICAL_INDICATOR.md; reviewed official TradingView formulas and explicit TA-Lib seeds |
| Target DDL | CREATED | apply.json; exact forward migration and SHA256 |
| Python engine | CODE IMPLEMENTED | features/feature04/engine.py, pipeline.py, specs.py |
| Unit tests | TESTED | 15 passed, 0 failed |
| Live calculation / UPSERT | TESTED | validate.json: 3,185 source bars across BBCA/GOTO; 6 real calculated bar rows inserted only inside a rolled-back transaction |
| Full historical population | NOT EXECUTED / NOT BACKFILLED | Target has 0 persistent records |
| Automated refresh | NOT EXECUTED | No service, deployment or schedule added |
| TradingView numerical parity | NOT VERIFIED | Actual matching reference outputs are unavailable |
| Point-in-time model eligibility | NOT VERIFIED | Prediction timestamp/target horizon undefined; historical availability and source vintages incomplete |

## Verified current state

Source `public."Price_Stock_Indonesia_IDX"` is owned by `postgres`, with PK `(ticker,date)`.
Mapping: `ticker -> ticker`, `date -> trade_date`, `timeframe -> timeframe` (actual `Daily`),
`open/high/low/close/volume` provide typed OHLCV inputs. Actual symbols are uniquely `IDX:ticker`.
There are 1,318,633 bars / 844 tickers, 2018-01-02 to 2026-10-09; 62–2,113 bars per ticker.
Duplicates, missing/nonfinite/invalid OHLCV, weekends and malformed tickers: all zero.
40 zero-volume bars are retained. 1,303,726 ingestion timestamps are unknown.
12 tickers have fewer than 250 available observations; first-valid does not prove recursive
stability or matching earlier chart history. The engine uses all available history.

Current ingestion requests split adjustment and regular session, 1D; per-bar historical
adjustment vintage and historical consistency are unavailable. Official holiday-calendar
completeness is not verified. Source selection can carry survivorship bias.
Existing source nonnegative/range constraints, PK/date index and two triggers are unchanged.
The all-row before/after count and aggregate row fingerprint matched exactly (apply.json).
The source fingerprint is an integrity check, not a historical source-version identifier.

## Created table and actual TOP 3

`public."Feature04_Technical_Indicator"` exists with exactly 42 columns, owner `postgres`,
PK/B-tree `(ticker,trade_date,timeframe)`, nullable 37 numerical features, required identity
and calculation metadata. No extra performance index was needed: bounded ticker/date/`Daily`
reads use the primary-key index (validate.json). No source foreign key or grants were introduced.

**Actual record count: 0. TOP 3 actual records: empty.**
The following horizontal groups show verified column names and types for the same physical
wide table. These are schema rows. No synthetic/example feature records were inserted.

### Identity and technical indicators

| ticker | trade_date | timeframe | sma_20 | sma_50 | ema_12 | ema_26 | rsi_14 | macd | macd_signal | macd_histogram | atr_14 | bb_upper_20 | bb_middle_20 | bb_lower_20 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| text NOT NULL | date NOT NULL | text NOT NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL | double precision NULL |

### Candlestick patterns 1–13

| cdl_piercing | cdl_morning_star | cdl_morning_doji_star | cdl_engulfing | cdl_3_white_soldiers | cdl_hammer | cdl_inverted_hammer | cdl_3_inside | cdl_3_outside | cdl_harami | cdl_harami_cross | cdl_dark_cloud_cover | cdl_evening_star |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL |

### Candlestick patterns 14–25 and metadata

| cdl_evening_doji_star | cdl_3_black_crows | cdl_shooting_star | cdl_hanging_man | cdl_doji | cdl_dragonfly_doji | cdl_gravestone_doji | cdl_marubozu | cdl_kicking | cdl_rise_fall_3_methods | cdl_mat_hold | cdl_hikkake | calculation_version | calculated_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | integer NULL | text NOT NULL | timestamp with time zone NOT NULL |

## DDL / catalogs / validation

Exact executed DDL: `database/migrations/20261011_001_create_feature04_technical_indicator.sql`.
One table, 42 Column_Catalog entries and 42 active calculation-verified Feature_Catalog
entries were added. A safe exact-date relationship to Feature01 is registered, with Daily
and historical-sector limitations. Physical catalog semantics remain separate from TradingView
parity and predictive validity; no AI allowlist, permission or tool activation is changed.

A pre-existing catalog name regex rejected the exact requested table name. The migration
adds only the exact-name exception in `public.validate_feature_catalog_target()`, keeps all
other physical-column/VERIFIED-table checks, guards against definition drift and registers
the routine with affected table metadata. Its original SQL is archived in catalog_validator_before.sql.
The semantic audit's fixed 91-definition count was replaced by actual schema coverage checks.

Native integer candle outputs, signed detection, zero non-detection, multi-pattern coexistence,
per-function warmup masks, NULL behavior, independent SMA/EMA/Wilder/BB calculations,
MACD consistency, chronological sorting/partitioning, invalid-input resets, no-look-ahead,
and historical-correction causal suffix behavior passed controlled tests. Live UPSERT first
insert changed 6 rows; identical recalculation changed 0; modified payload changed exactly
1 and restoration changed exactly 1. The transaction was rolled back; 0 persistent records.
A repeatable-read dry-run of BBCA/GOTO for 2026-10-01..09 produced 14 bounded output rows.

50-bar versus full-history BBCA initialization changed the last MACD signal by about 3.821
IDR and ATR by 1.768 IDR. With 250 bars, last BBCA signal difference was about 0.000007411
IDR; at 500 available bars it was zero at measured float precision. These observations justify
full-history replay, and do not claim a universal 250/500-bar parity guarantee.

See the main feature guide for exact numerical seeds, first-valid positions, function defaults,
incremental/correction design, versioned source manifests, official references, and training risks.
No reference numerical TradingView values or candlestick equivalence were assumed.
