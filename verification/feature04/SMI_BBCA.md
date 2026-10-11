# Feature04 SMI and swing state — BBCA

Executed 2026-10-11 in `lucid-patience / dev / Postgres`.
Target `public."Feature04_Technical_Indicator"`; source `public."Price_Stock_Indonesia_IDX"`.
User requested the SMI/swing components from HH.txt, starting with BBCA only, confirmed
with "Sure", and requested Markdown definitions of every column. Encoding correction:
"Buat 1 saja atau 0 kalau false". Complete definitions: [55-column guide](../../FEATURE04_COLUMN_DEFINITIONS.md).

## Result

- Schema: 55 columns, with nine appended fields; prior 46 physical columns retain order.
- BBCA: 2,113 Daily rows, 2018-01-02 through 2026-10-09, chronologically replayed.
- SMI available on all 2,113 BBCA bars; first confirmed high available 2018-02-06.
- `break_swing_high`: INTEGER 1 on 47 trigger dates, INTEGER 0 on 2,066 other dates.
- First trigger: 2018-07-18. Latest trigger: 2026-09-08.
- All original numeric/pattern/inside-bar values for BBCA are unchanged. Only the nine
  new fields, calculation_version and calculated_at change in its 2,113 rows.
- Other 843 tickers / 1,316,520 rows preserve every original field and timestamp;
  all nine added fields remain NULL. Total table rows remain 1,318,633.
- Source rows and original other-ticker payload fingerprints match before/after.
- An identical resumed run is SKIPPED_VERIFIED, changed 0 rows, preserving timestamps.

Version: `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4` for BBCA.
Other rows retain `feature04-v2-talib0.6.8-c0.6.4`.
Atomic log run UUID: `c0157d46-7f54-477b-af7a-5b9bf63d161f`, one COMPLETED BBCA entry.
The earlier all-source v2 log run is preserved. No per-price/feature row mirror is committed.

## Definition and validation

Source script preserved as [HH.pine](../../features/feature04/reference/HH.pine),
with uploaded CRLF line endings normalized to LF; both checksums are recorded in local checks.
SMI uses rolling extrema 14, double EMA 5/5, first-input EMA seed, partial extrema
windows at startup, and thresholds ±40. It deliberately does not use the existing
TA-Lib SMA-seeded EMA columns to calculate SMI.

The nine stored fields are post-bar state. Peak confirmation is available on its
SMI-downcross date, never backdated to the earlier peak bar. Peak/trough bar indices
are zero-based relative to this ticker's available source history. Temporary values
clear on confirmation, and the last confirmed high remains after a breakout.

The literal script crossover checks current close against current confirmed high
and previous close against previous confirmed high. Both levels must exist. Changed
levels, threshold equality/recross resets, repeated breakouts and absence of an SMI
filter at breakout are preserved. A wick alone does not constitute a closed-bar signal.

Checks:

1. **27 feature tests passed**, including independent first-seeded EMA weighted-sum
   reference, partial windows, flat zero denominator, threshold touches/recrosses,
   tied peaks/troughs, confirmation-bar exclusion, first confirmation with prior NULL,
   changed swing level, wick versus close, repeat triggers, ticker isolation, invalid
   input reset and causal-prefix equality.
2. Rolled-back live rehearsal: 2,113 computed/stored rows match, identical UPSERT changes
   0 rows, timestamps unchanged, binary constraint rejects 2 and rolls back its savepoint.
   Source/other ticker fingerprints and original BBCA rows preserved after rollback.
3. Applied forward migration is hash-recorded. All three Feature04 migration generators
   reproduce their SQL; two standalone frozen-migration checks pass.
4. Every committed BBCA payload read back and compared with calculation before its atomic
   COMPLETED audit log commits. Independent SQL window reference finds 0 trigger mismatches.
5. Separate read-only Pgweb connection verifies physical columns, BBCA coverage/triggers,
   latest state, other-ticker NULLs and atomic log. Its independent closed-form EMA
   convolution reference compares all 2,113 stored SMI values with error below 1e-10.
6. Semantic audit: 146 active definitions across four Feature tables, all calculation-verified,
   0 incomplete; Feature04 has 55 active v3 definitions, 42 inactive v1 and 46 inactive v2.
7. Measured ticker/date-range query uses the existing primary-key index (7 rows,
   approximately 0.045 ms scan in rehearsal). No extra index is added.
8. Schema export uses only read-only helpers. No global status/catalog synchronizer,
   tracking trigger, permission, service deployment, source fetch, AI allowlist or schedule changes.

Evidence: [rehearsal](smi_rehearsal.json), [migration](smi_apply.json),
[committed backfill](smi_backfill.json), [independent readback](smi_independent_readback.json),
[local checks](smi_local_checks.json), [semantic audit](smi_semantic_audit.json),
[read-only schema export](smi_schema_export.json), [sandbox cleanup](smi_execution_cleanup.json).

## Reproduction and limits

The scoped runner reads full source history, defaults to dry-run, and limits explicit scope
lists to 1–10 distinct canonical source tickers. Use write only under authorized scope:

```bash
python features/feature04/backfill.py --tickers BBCA \
  --run-id c0157d46-7f54-477b-af7a-5b9bf63d161f \
  --manifest /tmp/feature04-smi-bbca.json --write
```

Scope options `--tickers` and `--all-source-tickers` are mutually exclusive. The existing
bounded-refresh limits remain intact. This execution invokes only BBCA.

These are closed Daily triggers, not reconstructed intrabar alerts. Formula/code validation
against the supplied script is established; matching a TradingView chart export is still
NOT VERIFIED because chart history, adjustments and initialization must match. Historical
source revision/availability and point-in-time training eligibility remain NOT VERIFIED.
No automatic refresh or notification is created.
