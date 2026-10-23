# IHSG OHLC history: execution and compatibility verification

User approval, 2026-10-23: "Ok, masukan saja ke price ya."

- Target: IHSG mapped by the universe to IDX:COMPOSITE; 2018-01-02..2026-10-23.
- Provider: 2,125 valid OHLC-only daily observations, all source volume absent.
  All 2,123 stored BBCA dates are present. Extra source dates 2026-09-17/18
  are weekdays and are absent from the provider's published session-holiday list.
  Those dates do not exist in the stored price table for any ticker. Accepting
  provider index candles does not rewrite any stock or the historical calendar.
- Forward migration 20261023_007_idx_index_optional_volume.sql was verified with
  rollback, then applied. SHA256:
  0360513b65a3a0846247bd9e233d00876a99856cb934f1255965c1253de455b9.
  Both source/Feature01 volume columns accept NULL, while guard triggers still
  reject missing ordinary-stock volume (SQLSTATE 23514, tested on BBCA in a
  rolled-back savepoint). Volume-dependent Feature01 formulas remain NULL;
  no source volume or price is synthesized.
- Daily ingest and Feature04 readers use the live universe's security type and
  provider mapping. Stock/bond formulas and checkpoint versions are unchanged.
  Feature04 is price-only; absent index volume does not invalidate OHLC.
- Local checks: 71 passed, 11 database-dependent tests skipped. Live migration
  rollback/apply provide database evidence. See apply/tests.txt and the logs.
- The scoped price job is insert-only, checks the accepted date comparison and
  source fingerprint, verifies stored/source values in the same transaction,
  and leaves normal source-change triggers enabled.

## Live results

- Price APPLY committed 2,125 inserted rows, 0 existing rows overwritten,
  0 source/stored mismatches. Fingerprint:
  1ee8023032bbea8a361b6017412f993f5694de19ebe619a3957e4bb3a63e4afd.
- Independent pgweb readback: 2,125 final IHSG rows, 2018-01-02..2026-10-23,
  all volume NULL; other price tickers still total 1,326,939 rows. No stock row
  has NULL volume. Source date counts: 2018 240; 2019 245; 2020 242; 2021 247;
  2022 246; 2023 239; 2024 237; 2025 236; 2026 193.
- Explicit initial Feature04 backfill stored and verified all 2,125 index rows.
  Seven recent checkpoints were stored (2026-10-15..23); the last-five-session
  incremental/full comparison had zero drift across all output fields. EMA200
  is available on 1,926 rows, following its normal 199-row warmup.
- The old routine worker had correctly stopped at REPAIR_REQUIRED because a new
  ticker had no initial checkpoint. Its queue/column statuses were NOT manually
  changed to SUCCESS. The explicit initial history has its own verified backfill
  log; ordinary-worker retry remains pending the approved application release.
- Feature01 is being populated by its existing worker. At the captured snapshot,
  2,024 feature rows existed, zero volume/volume-average values were synthesized,
  1,904 queue items were DONE, 221 PENDING and none FAILED. Its existing forward
  suffix refresh can populate more feature dates than completed queue items.
- Required global semantic audit was run. It failed on absent active definitions
  for pre-existing Feature05/Feature06 stock views, outside this change. Scoped
  Feature01/Feature04 checks passed: zero missing definitions, incomplete semantic
  rows or nullable-volume metadata mismatches. No unrelated catalog was rewritten.
- Temporary service 382ad4cc-7275-4dee-9a4c-fa18cfe73771 was deleted, with no
  volumes created. No permanent service variables, schedules or deployments changed.

## Remaining application release

Automatic review rejected a direct main push of a0aded1 because explicit approval
for this new shared-branch commit was absent. The code/evidence are saved on
codex/ihsg-price-ingest. Until release, the old daily parser still drops index
candles without volume; the historical data above are already safely stored.
After the main release reaches SUCCESS for idx-price-cron, idx-price-recovery-cron
and feature-04-worker, retry IHSG with a dirty date equal to the source's latest-five
session boundary (2026-10-19 for this snapshot). Let the actual worker compute,
validate and finalize its queue/column statuses. Do not mark those statuses as
successful without that calculation. No other ticker repair/replay is needed.
