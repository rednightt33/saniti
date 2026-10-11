# Feature04 v2: complete serial historical backfill

Executed 2026-10-11 on lucid-patience / dev / primary Postgres.
The user authorized all tickers actually present in Price_Stock_Indonesia_IDX,
one ticker at a time, from each ticker's earliest date through latest available date.
The reviewed additions are ADX14, close EMA50/EMA200 and strict current-candle inside bar.
Authorization wording is retained in DATABASE_CHANGELOG.md.

| Check | Verified result |
|---|---|
| Feature table | public.Feature04_Technical_Indicator |
| Physical columns / active definitions | 46 / 46 v2; 42 v1 definitions retained inactive |
| Calculation version | feature04-v2-talib0.6.8-c0.6.4 |
| Source tickers / completed atomic ticker logs | 844 / 844 |
| Persistent source / feature rows | 1,318,633 / 1,318,633 |
| Global date span | 2018-01-02 through 2026-10-09; each ticker follows its actual source span |
| Missing source keys / extra target keys / wrong-version rows | 0 / 0 / 0 |
| Failed ticker logs | 0 |
| Source before/after fingerprint | 1,318,633 rows; -2165319481806142948543; unchanged |
| Strict inside-bar detections | 145,328 |
| Target total relation size | 486,858,752 bytes at verification |
| Main-run elapsed time | 258.114 seconds; 12:14:35–12:18:53 Asia/Jakarta |
| TradingView numerical parity | NOT VERIFIED |
| Point-in-time training eligibility | NOT VERIFIED |

BBCA's entire 2,113-bar history was first committed as the controlled smoke test.
Its same-run resume verified/skipped it with zero updates and preserved every timestamp.
The main serial invocation completed 843 other tickers and verified/skipped BBCA,
covering every source observation. The preceding 22-row January BBCA v1 fixture was
upgraded during the BBCA v2 calculation; v1 numeric feature values were unchanged.

Each ticker used a repeatable-read source snapshot and Feature04 advisory lock,
full causal chronological calculation, temporary COPY staging and idempotent UPSERT.
All 45 payload columns excluding calculated_at were read back and compared before
their output and COMPLETED audit committed atomically. A source extraction SHA256
and output SHA256 live in public.feature04_backfill_log; GitHub has aggregate evidence,
not a row-by-row price/feature mirror. An error rolls back the current ticker and
leaves earlier completed tickers resumable. No error occurred in the historical run.

Final independent pgweb readback confirmed 46 physical columns, 844 ticker logs,
correct v2 versions and 1,318,633 committed records. Full key anti-joins found zero
missing/extra keys. The existing ticker/date/timeframe PK supports scoped queries;
the measured post-load EXPLAIN is in full_validation.json, with no speculative index.

## Expected initial-history NULLs

| Extension | Available rows | NULL rows | Meaning |
|---|---:|---:|---|
| ADX14 | 1,295,845 | 22,788 | First 27 observations per ticker unavailable |
| EMA50 | 1,277,277 | 41,356 | First 49 observations per ticker unavailable |
| EMA200 | 1,151,734 | 166,899 | First 199 observations, or all shorter histories unavailable |
| inside_bar | 1,317,789 | 844 | First observed candle per ticker has no predecessor |

Latest ADX is available for all 844 tickers; latest EMA200 remains NULL for 11
histories shorter than 200 observations. Inside bar uses strict original-price
high[current] < high[previous] AND low[current] > low[previous], labels the current
closed Daily candle, and excludes equal boundaries. 1 is detection, 0 is available
non-detection; it remains separate from three-candle CDL3INSIDE. No future candle,
synthetic date, price imputation or fabricated historical availability was used.

## Validation and operational scope

- 21 local Feature04 tests passed, including independent EMA/Wilder ADX references,
  flat ADX, strict/decimal inside boundaries, reset, partitioning, causality and resume hashes.
- Both standalone applied-migration immutability checks passed. Original migration
  checksum unchanged; the forward migration checksum is recorded in APPLIED.sha256.
- Successful rolled-back rehearsal: 2,113-row UPSERT, identical rerun zero, one changed
  payload update, ADX bound rejection and rollback, original v1 row payload preservation.
- Live semantic audit: 137 active/verified definitions, 4 feature tables, no incomplete
  semantics or missing physical mappings.
- Database schema exported read-only: 53 public tables, 46 target columns and 13
  monitoring-log columns; no global status reconciliation or new tracking trigger.
- No source write/request, grant change, new deployed service/database, schedule,
  automatic writer, AI onboarding or model training. Sandbox cleanup is recorded separately.

Evidence: full_manifest.json, full_validation.json, full_independent_readback.json,
v2_rehearsal.json, v2_apply.json, v2_smoke.json, v2_semantic_audit.json,
v2_schema_export.json and full_execution_cleanup.json. Source availability,
adjustment-vintage, survivor selection and TradingView initialization limits in
FEATURE04_TECHNICAL_INDICATOR.md remain applicable after successful computation.
