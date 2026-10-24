# IHSG one-date Feature 3/5/6 validation

Authorized 2026-10-24: IHSG, **2026-08-31**, Features 3, 5 and 6 only. No bulk writes,
Feature02/04 writes, source changes, schema changes or permanent-service rollout.
Prior dry run completed with committed=false; sample had 3 F03, 214 F05 and 3 F06 rows.

Implementation: `scripts/upsert_index_broker_feature_sample.py`.

- `prepare` contains the aggregation/calculation/NULL policy to reuse for subsequent approved bulk.
  The helper deliberately accepts one output date; no bulk execution is enabled by this task.
- Feature05: SUM raw daily fields by broker/investor type/board across source symbols. Frequency
  requires every contributing source row; source-symbol balance flags are ORed before summing symbols.
- Feature03: the existing live v2 SQL runs against temporary daily broker inputs. No Feature02 rolling
  fields are dependencies. Investor flows use source investor identity; rankings/counts first combine
  investor types per broker. HHI is forcibly NULL for the index aggregate by user policy.
- Feature06: canonical non-index Feature05 historical details are summed to daily board/investor context;
  the sample date uses the fresh raw aggregate. Existing live Feature06 SQL computes cumulative,
  rolling, persistence, strength, z-score and percentile metrics. Unknown frequency in a required input
  window invalidates all frequency-dependent outputs for that board/window. The conservative missingness
  policy is identical to the previous dry-run proposal and must remain the same in bulk.
- Temporary historical rows use an internal context identity and are never inserted into public tables.
  Only the 214 real aggregate broker/investor/board identities are public Feature05 output candidates.
- Independent Python references validate every Feature03 analytical output and all Feature06 analytical
  outputs, including source gaps and the frequency mask. SQL upsert readback compares every stored
  column against staging. Transaction isolation is REPEATABLE READ; any mismatch rolls everything back.
- Existing runtime SQL routine hashes are emitted so later bulk can detect formula changes explicitly.
- Expected source scope includes warrants/rights present in raw Broker Summary: this is a market-flow
  proxy labelled IHSG, not an official historical IHSG constituent basket. Boards are never combined.
- No change to stock-only AI views or index worker/Telegram classification is included. That broader
  rollout was held by automatic approval review and remains separate from this explicit data write.

Run with DATABASE_URL configured inside Railway private network:

    python scripts/upsert_index_broker_feature_sample.py --ticker IHSG --date 2026-08-31
    python scripts/upsert_index_broker_feature_sample.py --ticker IHSG --date 2026-08-31 --apply

The first command rolls back after validation. The second validates again and then atomically upserts.
Live result and independent readback will be recorded here after completion.
