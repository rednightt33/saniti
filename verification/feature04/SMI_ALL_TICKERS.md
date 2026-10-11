# Feature04 SMI/swing — full source-ticker rollout

User instruction 2026-10-11: **"Alright, proceeed untuk semua ticker."**
Executed in Railway `lucid-patience / dev / Postgres`, target
`public."Feature04_Technical_Indicator"`, source `public."Price_Stock_Indonesia_IDX"`.

## Result

- **844 actual source tickers / 1,318,633 Daily observations**,
  2018-01-02 through 2026-10-09, with one ticker per transaction and its own full
  available history in ascending date order. No current-universe membership filter.
- Every row uses `feature04-v3-smi14-5-5-th40-talib0.6.8-c0.6.4`.
- **16,344 Break Swing High trigger bars** across
  824 tickers; remaining 1,302,289 flags are 0.
  Integer 1/0 flags are available on every observation. The 20 tickers without a trigger
  are completed calculations, not failed or skipped ticker coverage.
- First trigger across the source: 2018-01-08; latest: 2026-10-09.
  On each ticker's latest observation, 12 flags are 1.
- SMI available on 1,317,585 bars; 1,048 early values remain
  NULL because initial flat-price ranges make the double-smoothed denominator zero.
  No latest ticker SMI is NULL. Temporary peak/trough fields remain NULL outside tracking
  as defined, and last_swing_high remains NULL until the first confirmation.
- Original 46-column indicator/identity payload excluding version/timestamp is unchanged
  across all 1,318,633 rows; its fingerprint matches before/after.
- All BBCA fields and timestamps are identical to the verified BBCA checkpoint.
  Source data and its 1,318,633-row fingerprint are unchanged.
- Source/target keys: **0 missing, 0 extra**; non-v3 rows: **0**. No failed ticker logs.

## Execution and audit

Continued the existing v3 audit run UUID `c0157d46-7f54-477b-af7a-5b9bf63d161f` from the BBCA-only checkpoint.
The full invocation newly completed **843 tickers**, verified/skipped **1 BBCA**,
and changed **1,316,520 rows**. BBCA's earlier 2,113-row log stays intact;
the run now has 844 COMPLETED audit rows, source_rows sum 1,318,633, and historical
changed_rows sum 1,318,633 including that earlier checkpoint. Full invocation statistics
therefore differ from the entire extended run's historical changed-row sum.

Full invocation: `2026-10-11T06:19:28.865140+00:00` through `2026-10-11T06:25:12.810188+00:00` UTC
(13:19:28–13:25:12 Asia/Jakarta), **343.945 seconds**.
Last processed ticker ZYRX. No formula or engine changes were needed after the
27-test BBCA validation. Existing TA-Lib/NumPy/psycopg versions are pinned and unchanged.

The existing serial backfill runner is used with an execution-only pre-UPSERT guard:
compare every pre-existing original feature column with the computed row and stop before
mutation if any original indicator differs. Each ticker's full computed v3 payload is
then read back and compared before its COMPLETED audit log commits in the same transaction.
The runner stops on a failure, rolling back only that ticker and retaining earlier commits;
there were no failures in this execution. No copied price/feature rows are committed to Git.

```bash
python features/feature04/backfill.py --all-source-tickers \
  --run-id c0157d46-7f54-477b-af7a-5b9bf63d161f \
  --manifest /tmp/feature04-smi-full.json --write
```

An authorized rerun uses the same run UUID. A completed ticker skips only after its source
fingerprint, computed payload, actual stored values and audit hash agree. The initial BBCA
rerun and its unchanged full-rollout fingerprint establish that path here. Default CLI mode
is dry-run; no automatic job or notification is installed.

## Independent verification

- Full committed data verified by the per-ticker readback and read-only global validation.
- Independent PostgreSQL window reference checks **all 1,318,633 observations** against
  the supplied Pine's one-bar state transitions: high/low tracking flags, temporary
  prices and bar indices, last confirmed high and close-crossover trigger.
  **0 mismatches in all eight columns**. Observed high confirmations:
  18,188; low confirmations:
  29,494.
- Separate Pgweb read-only connection independently verifies target totals, flags, versions
  and atomic log coverage. SMI is recalculated via first-input-seeded closed-form EMA
  convolution and independent partial rolling extrema on **9,649 bars**
  across ADRO, BBCA, BBRI, BMRI, GOTO, PRDL and RANS (including the two shortest histories).
  Largest absolute discrepancy: **1.85e-13 points**;
  NULL positions match, tolerance 1e-10.
- A separate full-source cumulative-range review confirms all SMI NULLs occur before the
  ticker has any nonzero price range, rather than representing uncomputed tickers.
- Source, original-indicator and full BBCA fingerprints match the preflight exactly.
- Coverage metadata migration `20261011_004_record_feature04_smi_full_coverage.sql`
  first rehearsed/rolled back, then applied. It updates current scope/evidence metadata
  only; formulas/version v3, physical 55 columns, grants, routines and safe joins unchanged.
  Semantic audit: 146 active calculation-verified definitions, 0 incomplete, Feature04 55.
- Schema exported with read-only helpers only. Global status/catalog synchronizers and
  source tracking triggers are not executed or modified. The temporary private execution
  sandbox is explicitly destroyed after verification.

Evidence: [preflight](smi_full_preflight.json), [full invocation manifest](smi_full_manifest.json),
[global validation](smi_full_validation.json), [independent readback](smi_full_independent_readback.json),
[NULL review](smi_full_null_review.json), [coverage migration](smi_full_metadata.json),
[semantic audit](smi_full_semantic_audit.json), [read-only schema export](smi_full_schema_export.json),
[local migration checks](smi_full_local_checks.json), [sandbox cleanup](smi_full_execution_cleanup.json).

Definitions of all 55 columns: [FEATURE04_COLUMN_DEFINITIONS.md](../../FEATURE04_COLUMN_DEFINITIONS.md).
The [BBCA checkpoint](SMI_BBCA.md) and [previous v2 source-universe backfill](FULL_BACKFILL.md)
remain historical evidence.

## Interpretation limits

Signals label closed Daily bars; their date is trade_date. Provisional peaks are never
retroactively marked confirmed. Current/prior swing levels, threshold recross resets,
repeat triggers and absence of an SMI-at-break filter follow the supplied script.
No intrabar alert reconstruction, source request, service deployment, schedule, model
training or AI onboarding was added. TradingView chart/export parity and historical
point-in-time training eligibility remain NOT VERIFIED.

SMI's theoretical bounds are ±100; double-precision rounding in the stored full dataset
can exceed a bound by approximately 1.8e-12 points. Values are preserved without clamping
or changing the supplied formula, and this is numerical precision rather than invalid data.
