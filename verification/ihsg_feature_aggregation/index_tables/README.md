# Dedicated INDEX features — single-date initialization

User approved creation of six _INDEX tables, IHSG 2026-08-31 only, followed by deletion of IHSG from
shared non-index feature tables. Bulk and automatic update logic remain unapproved. Prices and universe
are retained. All new outputs, lossless archive and legacy deletion commit in one transaction; dry run
rolls back schema/catalog/data/cleanup together.

## Tables and formulas

| Table | Grain | Calculation |
|---|---|---|
| Feature_01_Stock_Daily_INDEX | date × ticker | Existing Feature01 SQL from actual index prices, unchanged formulas |
| Feature_02_Broker_Rolling_INDEX | date × ticker × broker × investor type × board | Aggregate source daily flows, then canonical 5/20/60 rolling and 252-value baselines |
| Feature_03_Stock_Broker_Daily_INDEX | date × ticker × board | Existing broker breadth/ranking logic after cross-symbol netting; HHI NULL by user policy |
| Feature_04_Technical_Indicator_INDEX | date × ticker × Daily × asset_type=index | Existing price indicator/pattern/SMI/swing formulas; actual index OHLC, unchanged numerical results |
| Feature_05_Foreign_Domestic_Broker_Detail_INDEX | date × ticker × broker × investor type × board | Additive raw value/lots and SUM of available frequency, with separate coverage |
| Feature_06_Foreign_Domestic_INDEX | date × ticker × board | Aggregate historical daily flows, full cumulative since 2016, common-market rolling periods, aggregate ratios |

Universe Security Type=index determines eligible target identity. A database trigger rejects non-index
or ambiguous fixed-income identity. The target ticker is a CLI parameter; there is no ticker membership
list in the engine. Source transaction scope stays all declared raw symbols (including warrants/rights),
a market-wide flow proxy rather than official historical index constituents. The previously audited
MAPADRCU6A source imbalance is preserved, not corrected by this initialization.

Only 2026-08-31 is written to public INDEX outputs. Earlier dates exist solely in temporary calculation
context. Feature02 needs only 312 preceding market sessions plus the output date for exact 60D/252
baselines; Feature06 cumulative reads the complete canonical broker history. Feature01 and Feature04
use the actual available index price history beginning 2018-01-02.

## Refined frequency and coverage

Feature05 buy_freq/sell_freq SUM the available inputs; unknown contributions do not erase known ones.
All inputs unknown -> NULL; known zero stays zero. Feature06's four daily frequency totals use the
same refined additive values. Both tables add five coverage columns:

- frequency_source_rows: raw broker source rows contributing to the group.
- buy_freq_known_rows / sell_freq_known_rows: source rows with a known frequency on that side.
- buy_freq_missing_rows / sell_freq_missing_rows: source rows whose frequency remains unknown.

Known + missing = source rows, separately for each side. These are coverage counts, not trade counts.
Value-per-frequency and other derived frequency ratios remain NULL when their required input/window
is incomplete. This avoids dividing full-scope cash value by a partial-scope frequency count. Monetary
net, cumulative, rolling and turnover ratios retain their independently audited formulas.

## Safety, validation and cleanup

`initialize_index_feature_sample.py` reuses the existing sample reference checks (60 Feature03 and
249 Feature06 comparisons), independently checks Feature02 rolling outputs and raw daily aggregates,
compares all Feature01/04 sample values with previously verified legacy outputs, and compares every
stored INDEX payload column with staging. Coverage is constrained and read back separately.

Before deleting any legacy row, it is copied as typed JSONB into
`migration_archive.index_feature_rows`, keyed by snapshot_id/source_table/row_hash. Both row counts
and every JSON payload/hash are verified. Archive is in a private schema, not an analytical table or
an AI-visible data source. Restoring old features is possible using jsonb_populate_record into the
original typed tables, but restoration is not executed automatically.

Expected prior legacy rows to archive/remove: Feature01=2125, Feature02=0, Feature03=3, Feature04=2125,
Feature05=214, Feature06=3 (4,470 total). The source Price_Stock_Indonesia_IDX rows are not deleted.
No old price/queue/worker configuration is changed in this task. Existing legacy automation can later
recreate index rows if new prices arrive; index exclusion/routing must be reviewed as a separate daily
update proposal before that next automatic cycle. This dependency is deliberately not hidden by an
unapproved runtime change.

Run inside Railway private network:

    python scripts/initialize_index_feature_sample.py --ticker IHSG --date 2026-08-31 --snapshot-id UUID --cleanup-legacy
    python scripts/initialize_index_feature_sample.py --ticker IHSG --date 2026-08-31 --snapshot-id UUID --cleanup-legacy --apply

The first command rolls back everything after validation. The second commits only if all checks pass.
No bulk/date-range option or scheduler is enabled. AI onboarding/access is deferred; pgweb gets SELECT
for user inspection. Table/column/feature metadata and index-only safe joins are registered.

## Sequence after this sample

1. User validates 2026-08-31 in all six INDEX tables and the refined frequency/coverage semantics.
2. A separately approved bulk fills history into INDEX outputs from retained price/broker sources.
3. Propose the daily update design and obtain approval before implementing its routing, queues,
   correction propagation, monitoring or schedule changes. Price and broker feeds are distinct triggers;
   no design should infer broker freshness merely because prices updated.

## Dry-run evidence

- Structure/catalog rollback test passed with existing catalog guards retained. New definitions start
  inactive and activate only after full sample/archive verification; catalog versions use the required v1 format.
- Full dry run passed: Feature02 independent rolling 5,350 comparisons plus raw daily reconciliation;
  Feature03 60 and Feature06 249 comparisons; Feature01 29 payload columns and Feature04 51 numerical
  outputs unchanged; all six staged-vs-stored payload comparisons had zero mismatches.
- Archive/delete dry run verified 4,470 complete legacy payloads and rolled the whole transaction back.
- Local regression checks: 71 passed, 11 DB-dependent tests skipped. No daily-update application code changed.

## Applied and independently verified

Committed at 2026-10-24 23:11 WIB (16:11 UTC). New INDEX counts: F01=1, F02=214, F03=3, F04=1,
F05=214, F06=3, all IHSG 2026-08-31. Separate pgweb readback confirms all six legacy IHSG counts=0
and all 2,125 original source price rows remain. Archive snapshot
293f4c52-0fd2-4d43-b02e-e0c6dba94f30 holds 4,470 original rows; independent admin readback found
zero archive hash mismatches. No bulk/date-range, daily worker, queue, scheduler, Telegram or AI
onboarding logic was enabled.

Regular known buy/sell frequencies now reconcile to raw source 2,372,642/2,372,642; Nego 859/859;
Tunai 4/4. Missing input rows remain flagged (Regular 1,715 per side, Nego/Tunai 1 per side).
F03 HHI is NULL; F04 asset_type=index; cumulative/rolling cash values retain the prior audited
semantics. Refined F05 frequency/coverage mismatches=0; F06 daily frequency comparisons=12, all pass.

A forward metadata-only migration 20261024_011 synchronizes Column_Catalog with the final refined
Feature_Catalog definitions and actual source dependencies. Scoped validation passes: 260 physical
INDEX columns, 0 missing Feature/Column definitions, 0 metadata drift, 0 incomplete semantic guidance.
The global catalog audit still fails on the pre-existing Feature05/06 *_Stock view definitions; no
INDEX column appears in that failure. This unrelated baseline issue is not silently fixed here.

CSV export bundle: /workspace/artifacts/index-six-tables/IHSG_2026-08-31_INDEX_features.zip.
Full local readback: /workspace/artifacts/index-six-tables/readback.json. Git keeps small summaries.

Temporary validation service 106547df-4649-4896-984f-5fedad63571a was deleted after verification;
permanent database/archive retained. APPLY deployment 71ee86d3-177f-4953-8772-8b22d536ea14 was
retired by subsequent postchecks; metadata sync deployment 2d6b05db-60be-40b6-a2ac-467bda2a91c7 was
observed SUCCESS. Commit/readback evidence, not a running temporary container, establishes data persistence.
