# Feature04 incremental finality verification

User authorized execution on 2026-10-12 with `"Ok jalankan."`. The change preserves the
existing formulas while replacing daily full-history replay with an exact checkpoint plus
affected suffix.

The pre-change live baseline covered 844 equity tickers / 1,318,633 rows and 24 bond
tickers / 60,409 rows. Measured recent bond attempts each read 1,003–2,752 source rows and
took 0.129–0.335 seconds of worker wall time even though their UPSERT changed zero rows.

The state engine stores initialization or mature state for SMA/Bollinger, EMA12/26/50/200,
RSI14, ATR14, ADX14, MACD signal, SMI/swing, inside bar, and native candlestick lookback.
Corrections at each of the five latest positions match the full-history reference for every
Feature04 output. NULLs and integer flags compare exactly; numeric values use absolute
`1e-10` plus relative `1e-12` tolerance.

The first live shadow attempt correctly stopped before writes on ID01Y: a Bollinger value
recomputed from a short array differed from the full TA-Lib run by `2.116e-10`. State v2
therefore carries TA-Lib-compatible rolling sum and sum-of-squares order across checkpoints;
the acceptance bound was not relaxed.

Migration `20261012_003_incremental_feature04_finality.sql` completed a live transaction
ending in rollback before apply. Independent post-apply readback found the new state table,
one enabled IDX market policy, all 1,318,633 equity rows final, zero initial checkpoints,
and zero processing claims. Historical `source_bar_time` remains NULL because that evidence
was not retained; it was not synthesized.

Normal work now requires the checkpoint immediately before `dirty_from_date`, reads no more
than the market's configured correction-session count, and writes state in the same
transaction as successful output and queue completion. Missing/incompatible state,
digest mismatch, or an older correction returns `REPAIR_REQUIRED`; the worker never starts
a full-history fallback.

Machine-readable evidence is in `incremental_finality.json`. Deployment, bootstrap, and
live canary identifiers are added after rollout.
