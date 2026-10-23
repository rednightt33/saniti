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

Price insertion, initial index Feature04/checkpoint verification and job cleanup
are being verified; their final results will be appended after live readback.
