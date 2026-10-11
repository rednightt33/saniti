# Feature04 governed rename and source close

On 2026-10-11 the user approved renaming the physical result table to
`public."Feature_04_Technical_Indicator"`, updating related runtime scripts, and adding
the closing price for each `trade_date`. This is a forward-only change. Applied migrations
and historical evidence keep the old name so the audit trail remains reproducible.

## Implemented contract

- The physical table and its target-specific constraints/indexes use
  `Feature_04_Technical_Indicator`. Operational queue, monitor, retry and function names
  keep the `Feature04_*` prefix because they are workflow controls.
- The table has 57 columns. `close` is `DOUBLE PRECISION NOT NULL`, finite and
  nonnegative. It is copied from `Price_Stock_Indonesia_IDX.close` for `equity`, or from
  `Price_Fixed_Income.close` where `metric_type='price'` and `Timeframe='1D'` for `bonds`,
  matched exactly on ticker and `trade_date`.
- `close` is one of 51 selectable outputs and participates in per-column failure status
  and retry. It is independent from formula warmup: a valid close remains stored when a
  different input makes derived indicators unavailable. Missing/nonfinite/negative close
  fails that ticker calculation.
- Indicator formulas and engine version
  `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4` are unchanged.
- The Feature01 relationship now explicitly requires `asset_type='equity'` before its
  exact ticker/date join. The generic Feature table-name validator no longer needs the
  legacy spelling exception.

## Migration and readback

Migration `20261011_008_rename_feature04_add_close.sql` SHA256
`66bceac194de7edc86a0e39a6c99c0fbe5af7248a1eb2902698d618cfd49babf` completed a full
rolled-back rehearsal first. The rehearsal retained 1,379,042 rows / 868 asset-ticker
partitions and the exact full-row fingerprint `2112974081807992232108` before and after
rollback. Preflight found 56 old columns, zero nonterminal queue rows and zero old-name AI
catalog references.

The same migration then committed. Live readback found:

- 1,379,042 rows unchanged: 1,318,633 equity rows / 844 tickers and 60,409 bonds rows /
  24 tickers, covering 2016-01-01 through 2026-10-09;
- 57 physical columns, 57 Column Catalog definitions and 57 active Feature definitions;
- zero NULL close values, zero equity source mismatch and zero bonds source mismatch;
- zero remaining physical, catalog, relationship, constraint or index references to the
  old table name;
- semantic audit PASS: 148/148 active definitions are calculation verified across four
  Feature tables.

The first post-commit readback exposed that queue-derived close readiness covered only 25
instruments because the current queue table has 25 rows, while the feature table has 868
asset/ticker partitions. No feature value was wrong. A separate immutable corrective
migration, `20261011_009_complete_feature04_close_status.sql` SHA256
`3d9a1debeabadf5bae40e5affc27819b87743be30f8ca5d8dc5ce48cd9d4f639`, was rehearsed with
rollback and then committed. Final readiness is 868 successful close statuses and 44,268
total statuses (`868 × 51`), with zero nonterminal queue rows.

Machine-readable aggregate evidence is in
[`rename_close_validation.json`](rename_close_validation.json). No source row, ticker list,
AI allowlist, permission, price cron, Telegram ordering rule, or indicator formula changed.
