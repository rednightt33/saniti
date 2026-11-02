# Feature 04 bonds: repair after a price correction older than the checkpoints (EXEC-F04-BONDS, ERRORS M336)

`repair_job.py` runs once on `orc-test-runner` with the deployed worker and engine (`apps/feature-04-worker/worker.py`,
`features/feature04/{engine,incremental,swing}.py`), `apps/feature-04-worker/requirements.txt`:

```
J=<staging dir with job.py = repair_job.py, worker.py, features/feature04/*.py>
bash scripts/onboarding/run_job.sh $J/job.py <params.json {}> <log> $J/worker.py $J/features apps/feature-04-worker/requirements.txt
RUN_JOB_EXTRA_VARS='MODE=write' bash scripts/onboarding/run_job.sh ...   # after a clean dry run
```

Per bond whose queue row is `FAILED` with a `dirty_from_date`:
1. the price history is calculated in memory with `engine.calculate_with_diagnostics`;
2. every stored row before the dirty date must equal the calculation, else the bond is skipped (`history_mismatch`);
3. only rows from the dirty date on are written (`upsert_columns`, `delete_missing_outputs`);
4. the recent checkpoints are rebuilt (`build_recent_checkpoints`, retention lookback + 2);
5. the queue row is closed `DONE` at its generation and re-queued through `enqueue_feature04_group` at the last price
   date, so the worker computes the last session from the checkpoint and sets the column statuses itself.

Runs 2026-11-02 (`orc-test-runner` deployments): dry `c7e584ec`; write `020c14c8` rolled back per bond (the job set the NOT NULL
`dirty_from_date` to NULL, nothing written); write `d6165d66` (24 bonds); read-only check `def3015f`.

## Check after the repair (`verify_job.py`, read-only, runner `run_job.sh` with `bootstrap_states.py` as an extra)

User 2026-11-02: "mesti ensure ya tidak di ulang dari awal ... cek ensure hasil benar". Result for all 24 bonds:
- rows written by the repair (`calculated_at` on 2026-11-02): only from each dirty date (ID 2026-10-05, ID01Y/ID25Y
  2026-10-12, US 2026-10-21); 0 rows before it; every older row keeps its `calculated_at` of 2026-10-11…10-20;
- every stored row and column equals a full calculation by the deployed engine: 0 mismatches;
- incremental from the checkpoints equals full for the last sessions (`validate_recent`): 0 drift;
- independent plain-numpy recomputation (close, SMA20/50, EMA12/26, RSI14 Wilder, Bollinger 20/2, MACD 12/26/9) of the
  written rows: 4,232 values, 0 mismatches (tolerance 1e-7).
