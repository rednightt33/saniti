# EXEC-INDEX-GROUP-HISTORY stage 4: the entity script, tested locally (2026-11-15)

Scripts: `scripts/backfill_index_entities.py` (new: indexes, sectors and groups) and `scripts/backfill_index_features.py`
(IHSG; options with defaults that keep its SQL: `stage2(whole=)`, `stage6(collapsed=, seed=)`, `create_stages`,
`apply_chunks(features=, all_features=, catalog=)`). Dev was not changed: the fixture was read from dev and loaded into a
local PostgreSQL 16 database.

## Fixture (`load_fixture.py`, `synthetic_members.sql`)

- Read-only from dev: `IDX_Broker_Summary` and stock `Feature_05_Foreign_Domestic_Broker_Detail` for nine member stocks
  of four small groups, 2024-01-02..2025-10-31 (±180 thousand rows each); member lists, universe history, prices of IHSG,
  LQ45 and IDXBASIC; the live functions and table definitions.
- Entities: groups GAGOES (AMMN, BRMS), GCTCORP (BBHI, MEGA), GHARITA (CITA, NCKL, TIRT: TIRT is not in the universe),
  GRAJAWALI (ARCI, BWPT); LQ45 and IDXBASIC (priced). Local `rows_from` 2025-07-01 (dev: 2024-01-02).
- Synthetic member changes (local only), to test "recorded on day d, counted from d + 1":
  - LQ45: first record 2025-03-03 (AMMN, BRMS, MEGA); NCKL recorded 2025-07-14 (counted from 2025-07-15);
    MEGA leaves, recorded 2025-09-01 (out from 2025-09-02).
  - Sector Basic Materials: BWPT moves in, recorded 2025-08-04 (from 2025-08-05).
  - CITA first enters the universe 2025-06-02: under the sector rule its first row also holds before it.

## Results

| Check | Result |
|---|---|
| IHSG, full rebuild: old script vs branch script, same data (`regress_ihsg.py`, `compare_ihsg.sql`) | F01-F06: 2,140 / 41,636 / 885 / 2,140 / 41,636 / 885 rows, 0 differing |
| IHSG, incremental from 2025-10-01: old vs branch | 2,140 / 34,857 / 724 / 2,140 / 34,857 / 726 rows, 0 differing |
| Feature 02 in one statement per entity vs one per broker/investor/board (`equivalence.py`) | 6 entities, 0 differing |
| Feature 06 from rows summed over brokers vs from broker rows, same window | 6 entities, 0 differing |
| Built-in checks on every entity (Feature 05 of the members, window consistency, independent F02/F03/F06) | pass (`logs/ent_dry.log`) |
| Stored entity Feature 05 vs raw with the members written out by hand (`members_check.sql`) | 42,216 rows, 0 differing; day boundaries of LQ45 (NCKL 2025-07-15, MEGA 2025-09-02) and IDXBASIC (BWPT 2025-08-05) as expected |
| First fill to 2025-09-30, then continuation to 2025-10-31, vs one first fill to 2025-10-31 (`compare_continuation.sh`) | all six tables, 0 differing |
| Recompute from 2025-10-15 (`--since`) of stored rows | 32 chunks, 0 rows changed |
| Board traded in the window without a stored row (GCTCORP `Tunai`, row deleted): full history fallback | 0 differing from the first fill (`logs/fallback.log`) |
| One stock Feature 05 row changed by 1 | refused before writing: "members raw/Feature 05 mismatch", 0 chunks (`logs/negative.log`) |
| `scripts/tests/test_backfill_index_entities.py` (the entity read keeps IHSG's sums; a removed lots net fails it) | 4 passed |

## Defect found and fixed during the test

The first continuation failed its own Feature 06 check: the cumulative foreign net was off by 1% on 2025-10-01 (Nego).
Root cause: `refresh_feature_06` continues from the stored row before its range start, and IHSG has stored rows back to
2016, but an entity's stored rows start at its `rows_from`, so there was no such row and the cumulative restarted at 0.
Fix (`backfill_index_entities.seed_anchors`): the anchor is derived. It equals the stored cumulative of the last row
before the run, minus the daily nets from the range start. A board traded in the window with no stored row makes the
entity's Feature 06 read its whole history instead. The check that caught it stays in the code path (`validate6`).
