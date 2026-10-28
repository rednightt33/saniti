#!/bin/bash
# EXEC-SCREENER migration 1 on dev (20261028_001_edge_bff_screener.sql): DRYRUN, then APPLY, each as one job on
# orc-test-runner through scripts/onboarding/run_job.sh (the pattern of migrations 20261026_005 and 20261027_005,
# logs verification/backtest/jobs/). Prepared for the deploy runbook; run only with the user's go for this step.
#
#   verification/screener/jobs/run_migration.sh dryrun <sha256 of the migration file>
#   verification/screener/jobs/run_migration.sh apply  <the same sha256>
#
# Run from the repository root with a Railway project token in RAILWAY_TOKEN and the Railway CLI 5.71.0 on PATH as
# `railway` (run_job.sh calls `railway`). DATABASE_URL is set on orc-test-runner only for the run, as the reference
# ${{Postgres.DATABASE_URL}}, and removed afterwards (run_job.sh prints VAR_REMOVED or VAR_STILL_PRESENT); no value is
# printed. run_job.sh refuses while another job runs there (ERRORS M210, M227).
# Refuses: an unexpected sha256 (the file must be the reviewed one), a file not committed, an APPLY without a passing
# DRYRUN log of the same sha256, an APPLY of a file APPLIED.sha256 already lists. After each job it runs
# check_migration_log.py on the log; an APPLY is claimed only on its VERDICT PASS (AGENTS.md: read back, then claim).
set -u
MODE=${1:-}; WANT=${2:-}
MIG=database/migrations/20261028_001_edge_bff_screener.sql
HERE=verification/screener/jobs
case "$MODE" in dryrun|apply) ;; *) echo "usage: $0 dryrun|apply <sha256>"; exit 2 ;; esac
[ -f "$MIG" ] && [ -f scripts/onboarding/run_job.sh ] || { echo "RUN_FROM_REPOSITORY_ROOT"; exit 2; }
command -v railway >/dev/null || { echo "RAILWAY_CLI_NOT_ON_PATH"; exit 2; }
HAVE=$(sha256sum "$MIG" | cut -d' ' -f1)
[ "$HAVE" = "$WANT" ] || { echo "SHA_MISMATCH have=$HAVE want=$WANT"; exit 6; }
git diff --quiet HEAD -- "$MIG" && git ls-files --error-unmatch "$MIG" >/dev/null 2>&1 \
  || { echo "MIGRATION_NOT_COMMITTED"; exit 6; }
LOG="$HERE/migration20261028_001_${MODE}.log"
if [ "$MODE" = apply ]; then
  ! grep -q " 20261028_001_edge_bff_screener.sql$" database/migrations/APPLIED.sha256 \
    || { echo "ALREADY_IN_APPLIED_SHA256"; exit 8; }
  python3 -I "$HERE/check_migration_log.py" "$HERE/migration20261028_001_dryrun.log" \
    "$HERE/migration20261028_001_dryrun.params.json" "$WANT" >/dev/null \
    || { echo "NO_PASSING_DRYRUN_FOR_THIS_SHA256"; exit 7; }
fi
[ ! -e "$LOG" ] || { echo "LOG_EXISTS $LOG (keep it; move it aside to run again)"; exit 9; }
scripts/onboarding/run_job.sh scripts/onboarding/migration_job.py "$HERE/migration20261028_001_${MODE}.params.json" \
  "$LOG" "$MIG" 2>&1 | tee "$HERE/migration20261028_001_${MODE}.run.txt"
echo "RUN_JOB_EXIT ${PIPESTATUS[0]}"
grep -q '^VAR_REMOVED$' "$HERE/migration20261028_001_${MODE}.run.txt" \
  || echo "WARNING: VAR_REMOVED not printed: remove DATABASE_URL from orc-test-runner and check it is gone before anything else"
[ -s "$LOG" ] || { echo "NO_LOG"; exit 4; }
python3 -I "$HERE/check_migration_log.py" "$LOG" "$HERE/migration20261028_001_${MODE}.params.json" "$WANT"
