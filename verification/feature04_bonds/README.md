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
