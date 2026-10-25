# INDEX bulk / Feature vocabulary — planning evidence

User decision 2026-10-25: remaining INDEX samples accepted. Review the plan before bulk and new
vocabulary-table execution. Vocabulary includes **stock and INDEX**, Feature01/02/03/05/06 only.

Live inventory at **2026-10-25 00:57 WIB** (2026-10-24 17:57 UTC), pgweb read-only setting on.
No DDL, DROP, INSERT/UPDATE/DELETE, routine invocation, permanent service/configuration change,
frontend/API change, bulk load or catalog correction was performed by this review.

- `read_only_inventory.sql`: exact metadata/sample/price inventory SELECT.
- `live_summary.json`: availability, six one-date sample counts, column counts, read-only state,
  routine fingerprints and follow-up source/legacy counts. Broker endpoints were read with two
  ordered LIMIT 1 queries; no claim every intervening date/source row is complete.
- `column_inventory.csv`: 396 current physical columns/active versions/semantic fingerprints;
  five F05 INDEX columns marked for exclusion **after** the separately approved DROP.
  This is an inventory, not 396 reviewed frontend definitions. Expected final first-language
  vocabulary count is 391 if no further schema changes occur.
- `catalog_examples.json`: source metadata illustrating existing NULL/scope prose and the actual
  Foreign Strength 20D formula. Catalog coverage is complete; some texts still need correction.

Planning details are in root `PLAN.md`, section “INDEX bulk and shared Feature vocabulary”. No new
dated plan or executable migration is created in this review.

## Verified boundaries

Six INDEX tables still contain only IHSG 2026-08-31: 1/214/3/1/214/3 rows. The price source has
2,125 rows from 2018-01-02 to 2026-10-23; broker raw endpoints are 2016-01-04..2026-08-31.
Follow-up legacy IHSG F01/F04 counts are both zero. Future writes can still recreate legacy rows
because existing worker destinations remain unchanged; daily routing is a separate proposal.

Keep the accepted all-raw-symbol broker aggregation, each board, full broker cumulative baseline,
common aggregate sessions, HHI INDEX=NULL, F04 asset_type=index and missing-frequency rules.
INDEX bulk should aggregate staged history once, not invoke the full-history one-date helper in
a loop. F04 initial history bootstrap and later incremental updates are different operations.

## Catalog prose corrections identified, not executed

1. F01 volume null_rule allows index NULL volume; copied misuse_warning still says source volume
   must exist / never NULL. Relevant field updates: migration 20261023_007 and clone 20261024_010.
2. F06 INDEX cumulative text still describes ticker inception, whereas the validated aggregate
   uses available broker history from 2016-01-04, independent of index price history starting 2018.
3. Some cloned per-column source references retain legacy table names; migration 011 corrected
   table-level dependencies and selected column metadata, not every copied Feature_Catalog field.

These are documentation issues; this inventory does not invalidate the audited numeric sample or
claim to re-audit every historical calculation. A semantic hash detects subsequent metadata changes;
it does not replace manual/code-backed meaning verification.

## Code reviewed

- `scripts/initialize_index_feature_sample.py`: single-date, coverage-column writes, DDL/archive/cleanup.
- `scripts/upsert_index_broker_feature_sample.py`: full historical F06 context per sample and legacy
  apply destinations; not an INDEX bulk driver.
- `scripts/backfill_feature_02_v2.py`: padded sessions, rolling windows, prior-252 baseline exclusion.
- `database/migrations/20260914_047_define_feature_03_investor_type_v2.sql`: broker-net rankings.
- `database/migrations/20261022_003_create_feature_06_foreign_domestic.sql`: daily R=F/T, ratio strength.
- `scripts/check_feature_06_sample.py`: independent reference.
- `database/migrations/20261024_010_create_index_feature_tables.sql` and `20261024_011_sync_index_sample_catalog.sql`.
- `apps/feature-01-worker/worker.py`, `apps/feature-04-worker/worker.py`: legacy target/routing boundary.

Existing global *_Stock-view catalog coverage issue and source gaps remain open as recorded in
ERRORS_AND_SOLUTIONS.md. Scope completeness is not a declaration that the raw source is complete.
