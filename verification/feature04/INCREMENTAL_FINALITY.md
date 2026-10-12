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

The next shadow exposed a separate TA-Lib edge on BBHI: full-array `CDLHARAMI` returned
`-80`, while the same final candle from the bounded checkpoint returned `0`. TA-Lib's candle
setting total had accumulated floating history from an unrelated old prefix. State v3 makes
both full repair and incremental execution evaluate the exact same fixed 15-bar TA-Lib
window. The full 868-instrument shadow then completed with zero formula mismatches in
311.724 seconds. It identified three old suffix flags for one-time repair: BBHI Harami,
MTWI Hammer, and SQMI Marubozu.

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

Bootstrap deployment `30f3e66b-3a67-4843-9497-a6625cb0dcad` wrote exactly 6,076 state
rows: seven retained checkpoints for each of 868 instruments. The table-driven activation
queued the latest five sessions for all eligible universe members. Worker deployment
`c6abb05e-4341-4b6f-a060-2ef8962238d9` completed 868/868 jobs with zero failures and
exactly five source rows per attempt. That first normalization changed 2,533 recent rows,
including the three integer flags; most other writes removed small historical floating-order
differences while staying within the strict shadow tolerance.

The identical table-driven request was run again as the acceptance test. It completed
868/868 jobs, zero failures, exactly five source rows per job, and total `changed_rows=0`.
The queue ended with 868 `DONE` rows and the state table returned to 6,076 rows. This proves
the live stored suffix equals the checkpoint calculation; together with the all-instrument
incremental/full shadow, it proves the stored result matches the full formula reference.

Machine-readable evidence and all deployment identifiers are in `incremental_finality.json`.
