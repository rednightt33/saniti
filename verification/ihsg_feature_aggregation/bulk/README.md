# Approved INDEX bootstrap and shared vocabulary

User approved 2026-10-25: execute the reviewed INDEX bulk plan, remove five Feature05 INDEX
coverage columns, then create the stock+INDEX Feature01/02/03/05/06 presentation vocabulary.
Feature04 is included in INDEX numerical bootstrap, excluded from the vocabulary. No daily routing,
frontend/API, permanent Railway configuration, stock/bond numeric data or source repair is included.

## Execution evidence

- `attempt1_deployment.json`, `attempt1_logs.jsonl`: all monthly raw/canonical monetary checks
  succeeded, then a duplicate temporary calc2 CREATE stopped the transaction before public writes.
- `smoke_deployment.json`, `smoke_logs.jsonl`: corrected writer, rollback-only 330-session fixture;
  F02=5,000, F03=19,800 and F06=82,170 independent comparisons pass, plus 85 accepted F01/F04 sample
  cells. Temporary fixture values were never written to public tables.
- `apply_deployment.json`: corrected full-history execution. Final status/counts belong in the
  completion readback; deployment SUCCESS alone is not proof that the bootstrap completed.
- `catalog_snapshot_manifest.json`: pre-change metadata fingerprint/counts. The full metadata
  snapshot is retained privately, not embedded as a row mirror in Git.
- `schema_readback.sql`: bounded schema/catalog/constraints/index/trigger readback for seven targets.

## Calculation contract

Raw history is read in monthly date-indexed slices, grouped across all symbols by broker, source
Investor Type and market board. Before cross-symbol netting, source buy/sell gaps are identified
per date/symbol/board; opposite gaps cannot hide each other. Monthly monetary/lot/gap aggregates
are reconciled to existing canonical detail, without inheriting its old whole-group-NULL frequency
policy. Available raw frequencies are summed; all-unknown remains NULL, and coverage is retained
in temporary calculation context and persisted in Feature06 INDEX.

The shared aggregate calendar is preserved while F02 rolling/statistics calculate one broker/
investor/board pair at a time. F03 uses netted broker ranks. F06 calculates the entire staged
aggregate once, including cumulative from the first broker source session and windows/baselines;
an independent pandas implementation checks every F06 row. F03 is independently checked in a
streaming broker aggregation. F02 boundary/last/year-transition observations are independently
checked. All accepted 2026-08-31 analytical values must match before public writes begin.

F01/F04 use actual final index OHLC history. The existing Feature04 engine's equity input class
is only a validation adapter for universe-classified index OHLC, as in the accepted sample;
the destination's asset_type is index and its numerical formulas are unchanged. There is no
full-history replay added to daily workers and no checkpoint or queue rekey.

After dry validation the old INDEX sample is losslessly archived, the forward F05 cleanup runs,
and outputs are upserted by year. Every chunk is compared completely against its staged payload
and immediately rerun: unchanged analytical rows must produce zero updates. No shared legacy
Feature table is a write destination. Existing legacy writer recreation risk remains a separate
daily-routing design item. Original archive 293f4c52-0fd2-4d43-b02e-e0c6dba94f30 remains retained.

The new execution archive snapshot is dc859a6a-04f3-4af4-8876-4e61e5212a6e. Restoring the pre-bulk
state is a separately authorized operation: preserve current INDEX output first, restore the old
sample from this snapshot, and restore the five old F05 columns/constraints/catalog records before
replaying their saved values. Do not rerun applied creation migration 010 as a restore shortcut.
Never delete source prices, source transactions or the older legacy archive during restoration.


## Final verified result — 2026-10-25

Bulk complete at 02:13:43 WIB: F01 2,125; F02 576,648; F03 7,128; F04 2,125;
F05 576,648; F06 7,128. Total 1,171,802 rows. Price range 2018-01-02..2026-10-23,
broker range 2016-01-04..2026-08-31. 128 source slices cover 45,229,673 raw rows. Independent
F02=77,700/F03=142,560/F06=591,624 comparisons plus 11,326 accepted sample cells pass.
All 62 committed year chunks have mismatches=0 and rerun_modified=0.

Vocabulary complete at 02:29:04 WIB: 391 entries, 193 non-INDEX +198 INDEX, all VERIFIED;
exact public payload equals reviewed seed, rerun_modified=0. Scoped schema has 279 documented
columns: 255 INDEX +24 dictionary. F05 removed columns=0 present; F06 coverage columns=5;
HHI nonnull=0, wrong F04 asset_type=0, source close mismatches=0, legacy IHSG rows=0.
Full public checks: final_readback.json, post_bulk_readback.json, schema_readback.json.

Pre-change private archive: 436 INDEX sample rows +585 original catalog rows, hash mismatches=0.
Applied source bundle is reproducible: applied_code_proof.json verifies the exact deployment hash;
post_apply_hardening.diff records only immutable resume-snapshot retention / metadata-array dedup
added afterward, with no numerical change. SQL migration files are not edited after application.

Global semantic audit still fails for **100 pre-existing columns in the two *_Stock views only**,
not any new scoped object; global_audit_baseline.json records that boundary. No guard was relaxed.
No daily update, UI/API, source repair or permanent service change is included. Existing source gaps
and current-state broker profiles remain explicitly documented limitations.
