# Feature 02 v2 — Investor-Type shadow rebuild

## Current status

`public."Feature_02_Broker_Rolling_v2"` is an unreleased shadow table. The canonical
`Feature_02_Broker_Rolling` remains production-active and unchanged. Do not use the
shadow for production AI analysis until its full backfill, validation, atomic cutover,
Feature 3 rebuild, and Feature Catalog v2 activation all pass.

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

## Shadow operation

Migration `database/migrations/20260914_034_create_feature_02_investor_type_shadow.sql`
creates the table without changing the canonical Feature 2. Migration
`database/migrations/20260914_036_register_feature_02_shadow_columns.sql` registers it
as `System` staging infrastructure with `PARTIAL` table/column documentation status.

`scripts/backfill_feature_02_v2.py` performs SQL-side, resumable per-ticker backfill.
It does not load the raw history into Python RAM. A controlled test is:

```powershell
python scripts/backfill_feature_02_v2.py --host <proxy-host> --port <proxy-port> --ticker BBCA
```

`scripts/validate_feature_02_v2_sample.py` reconciles all 1D source rows for the test
ticker and independently recalculates all 31 numeric/window fields for Domestic and
Foreign samples.

## Activation gate

Do not rename or activate the shadow until all of the following pass:

1. Full source coverage and exact 1D reconciliation.
2. Duplicate, constraint, NULL-boundary, board, and Investor Type checks.
3. Independent Domestic and Foreign samples across all boards and edge cases.
4. Full rolling-window, z-score, percentile, and performance validation.
5. Complete Feature Catalog v2 definitions for all 38 canonical columns, including
   exact formula, source columns, grain, partition keys, units, null rules, examples,
   analytical interpretation, recommended use, misuse warning, and validation evidence.
6. Reviewed atomic cutover migration and downstream Feature 3 rebuild plan.

At cutover, v1 catalog definitions are deactivated, the validated v2 definitions are
activated against the canonical table name, and the legacy table is retained temporarily
for rollback. No destructive legacy-table deletion is implicit in the cutover.
