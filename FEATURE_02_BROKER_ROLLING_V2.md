# Feature 02 v2 — canonical Investor-Type broker rolling signals

## Current status

`public."Feature_02_Broker_Rolling"` is the fully backfilled, source-reconciled
canonical v2 table. Migration `20260914_043_cutover_feature_02_investor_type.sql`
promoted the shadow transactionally, activated all 38 Feature Catalog v2 definitions,
deactivated v1, and dropped the redundant v1 heap without `CASCADE`. The old shadow
name no longer exists. `market_ai_reader` has SELECT on the canonical v2 table.
Feature 3 still has its old broker-domicile meaning; a source-Investor-Type Feature 3
redesign and full rebuild are explicitly a later stage.

## Corrected semantic grain

One row represents:

```text
date × ticker × broker × investor_type × market_board
```

`investor_type` is copied from `IDX_Broker_Summary."Investor Type"` and means the
investor represented by that source row (`Domestic` or `Foreign`). It is not inferred
from the broker and must not be replaced by `IDX_Broker_Profile.broker_type`.

`broker_classification` remains current metadata from `IDX_Broker_Profile`. It is not
point-in-time history. Regular, Nego, and Tunai remain separate calculation partitions.

## Rolling calendar and partitions

The date calendar is the ordered set of transaction dates observed for the ticker
across all brokers, investor types, and boards. A missing broker/investor-type/board
observation contributes zero as the divisor day but does not create an output row.

All 5/20/60-date rolling fields partition by:

```text
broker × investor_type × market_board
```

The 20D and 60D z-scores and empirical-midrank percentiles use the preceding 252
complete rolling observations in the same partition and exclude the current date.
For example, a Domestic AK flow and a Foreign AK flow for BBCA are separate histories.

## Current operation and migration history

Migration `database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql`
created the original shadow without changing the former canonical Feature 2. Migration
`database/migrations/20260914_036_register_feature_02_shadow_columns.sql` registers it
as `System` staging infrastructure with `PARTIAL` table/column documentation status.
The cutover migration `20260914_043_cutover_feature_02_investor_type.sql` retired that
staging identity and registered canonical v2 as `Feature`/`VERIFIED`. The follow-up
`20260914_044_clarify_feature_02_v2_catalog.sql` sharpened signed-net and timestamp
definitions; no formula or stored row changed.
`20260914_045_index_feature_02_v2_daily_reads.sql` restores the daily cross-ticker
`(date, market_board, ticker)` index. A bounded Regular-board date query improved
from a 2,136.7 ms parallel heap scan to a 67.0 ms index-only scan; its index is 378 MB.

`scripts/backfill_feature_02_v2.py` now targets the canonical table and performs SQL-side,
resumable per-ticker backfill. For an existing ticker corrected upstream, use
`--ticker SYMBOL --rebuild-ticker`; a plain rerun skips already-loaded tickers. This
is not an automatic refresh worker. Do not run retired `scripts/backfill_feature_02.py`.
It does not load the raw history into Python RAM. A controlled test is:

```powershell
python scripts/backfill_feature_02_v2.py --host <proxy-host> --port <proxy-port> --ticker BBCA
```

`scripts/validate_feature_02_v2_sample.py` targets the canonical table and reconciles all 1D source rows for the test
ticker and independently recalculates all 31 numeric/window fields for Domestic and
Foreign samples.

## Full backfill result

The four disjoint half-open ticker ranges completed successfully on 2026-09-14:

| Range | Tickers | Rows |
| --- | ---: | ---: |
| ticker below `CBPE` | 1,262 | 11,446,792 |
| `CBPE` through below `JIHD` | 965 | 11,292,326 |
| `JIHD` through below `PSAB` | 940 | 11,117,923 |
| `PSAB` onward | 958 | 11,372,632 |
| **Total** | **4,125** | **45,229,673** |

Full ticker-by-ticker source reconciliation returned 45,229,673 source groups and
45,229,673 v2 rows, with zero missing rows, zero extra rows, and zero 1D value or
lot mismatches. The table covers 2016-01-04 through 2026-08-31, contains 40,737,689
Domestic and 4,491,984 Foreign rows, and preserves Regular, Nego, and Tunai separately.

All constraints are validated; global checks found zero invalid investor types,
boards, negative gross values, incorrect 1D net identities, blank identities,
rolling-window boundary violations, or invalid day-count relationships. The 216,085
20D and 194,369 60D rows with a percentile but no z-score are expected zero-standard-
deviation cases, not invalid values. The physical table and `Column_Catalog` both have
38 columns. Independent BBCA recalculation remains PASS for all 31 calculated fields
for both Domestic and Foreign samples.

An additional deterministic cross-range sample checked 12 ticker/broker/date keys:
one key for every combination of the four worker ranges and the three Market Boards.
Both Domestic and Foreign were recalculated from `IDX_Broker_Summary` for each key,
covering BBTN, ADRO, BNBR-R, GOTO, COCO-R, LSIP, KOTA, PADI-R, YULE, SWID, and
RMKO-R. All 744 numeric comparisons and all 24 current broker-classification joins
passed; the largest floating-point difference was `8.88e-16`.

Four targeted edge samples added 124 independent numeric comparisons, all PASS:

- AADI/AI/Foreign/Regular had only 2 active days in a complete 20-ticker-date
  window. Its independently recalculated `net_value_20d` was `-509582500`, matching
  storage and confirming that the other ticker transaction dates contribute zero.
- AADI/DP/Domestic/Nego had zero historical standard deviation: the expected and
  stored 20D/60D z-scores were `NULL` and their empirical-midrank percentiles were
  `50`.
- NSSS/TP/Domestic/Regular independently passed a complete 60-date calculation,
  including rolling value, z-score, percentile, activity-day, and concentration fields.
- The Tunai samples with fewer than 20 ticker transaction dates correctly retained
  `NULL` 20D/60D fields while their available 5D and 1D values matched raw data.

One initial monolithic reconciliation query exhausted PostgreSQL temporary space and
was cancelled without changing data. Re-running the same logical validation in four
disjoint, read-only, per-ticker streams completed in about seven minutes without temp-
disk pressure and produced the zero-difference result above.

## Cutover verification and downstream boundary

The pre-cutover full source reconciliation, independent sampling, constraints, and
rolling-boundary checks above passed. The cutover migration was executed once in a
rollback-only dry run before permanent application. Post-cutover readback found
45,229,673 canonical rows, the five-column primary key including `investor_type`,
38 active v2 definitions, 38 inactive historical v1 definitions, and no shadow table.
PostgreSQL database size fell from approximately 36 GB to 23 GB. A transactionally
rolled-back BBCA/2026-08-31 Feature 3 refresh reproduced both existing board rows
exactly, confirming compatibility with its old broker-level semantics. Feature 3
data were not rebuilt and its Domestic/Foreign columns remain broker-profile-based,
not source-Investor-Type-based; that redesign is separate.
