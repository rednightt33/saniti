#!/bin/bash
# A dev migration (EXEC-SCREENER migration 1 20261028_001_edge_bff_screener.sql, EXEC-MU-RUNTIME step 1
# 20261028_100_terminal_service_accounts.sql): DRYRUN, then APPLY, each as one job on orc-test-runner through
# scripts/onboarding/run_job.sh (the pattern of migrations 20261026_005 and 20261027_005, logs verification/backtest/jobs/).
# Prepared for the deploy runbook; run only with the user's go for this step.
#
#   verification/screener/jobs/run_migration.sh dryrun <sha256 of the migration file> [<migration file name>]
#   verification/screener/jobs/run_migration.sh apply  <the same sha256>              [<migration file name>]
#
# The migration is the file under database/migrations named by the third argument; without it, the one file there whose
# sha256 is the one given (so the runbook's step 4 lines for 20261028_001 run as written). Its jobs, beside this script,
# are named by its <date>_<nnn>: migration<date>_<nnn>_{dryrun,apply}.params.json (each naming exactly that file and its
# mode), logs migration<date>_<nnn>_{dryrun,apply}.log and .run.txt; check_migration_log.py holds its checks.
#
# Run from the repository root with a Railway project token in RAILWAY_TOKEN and the Railway CLI 5.71.0 on PATH as
# `railway` (run_job.sh calls `railway`). DATABASE_URL is set on orc-test-runner only for the run, as the reference
# ${{Postgres.DATABASE_URL}}, and removed afterwards (run_job.sh prints VAR_REMOVED or VAR_STILL_PRESENT); no value is
# printed. run_job.sh refuses while another job runs there (ERRORS M210, M227).
# Refuses, before any Railway call: an unexpected sha256 (the file must be the reviewed one), a file not committed, a
# migration without its params file or without checks in check_migration_log.py, params whose probes are not the
# reviewed ones (check_migration_log.py --params-ok: names, roles, data statements only), a job file not committed (the
# params, check_migration_log.py, this script, run_job.sh, migration_job.py, Dockerfile: what runs on dev or judges it),
# an APPLY without a passing DRYRUN log of the same sha256, an APPLY of a file APPLIED.sha256 already lists, an existing
# log. After each job it runs check_migration_log.py on the log; an APPLY is claimed only on its VERDICT PASS (AGENTS.md:
# read back, then claim). A failed APPLY may still have committed (a job that fails after the file's COMMIT keeps it):
# read the state back before anything else.
set -u
MODE=${1:-}; WANT=${2:-}; NAME=${3:-}
DIR=database/migrations
HERE=verification/screener/jobs
case "$MODE" in dryrun|apply) ;; *) echo "usage: $0 dryrun|apply <sha256> [<migration file name>]"; exit 2 ;; esac
[[ $WANT =~ ^[0-9a-f]{64}$ ]] || { echo "usage: $0 dryrun|apply <sha256> [<migration file name>]"; exit 2; }
[ -d "$DIR" ] && [ -f scripts/onboarding/run_job.sh ] || { echo "RUN_FROM_REPOSITORY_ROOT"; exit 2; }
if [ -z "$NAME" ]; then
  # the file this sha256 belongs to, when exactly one has it
  FOUND=$(sha256sum "$DIR"/*.sql | awk -v want="$WANT" '$1 == want {sub(".*/", "", $2); print $2}')
  case $(printf '%s' "$FOUND" | grep -c .) in
    1) NAME=$FOUND ;;
    0) echo "NO_MIGRATION_WITH_THIS_SHA256 $WANT (name the file as the third argument)"; exit 6 ;;
    *) echo "SEVERAL_MIGRATIONS_WITH_THIS_SHA256: $(echo $FOUND) (name the file as the third argument)"; exit 6 ;;
  esac
fi
[[ $NAME =~ ^([0-9]{8}_[0-9]{3})_[a-z0-9_]+\.sql$ ]] || { echo "NOT_A_MIGRATION_FILE_NAME $NAME"; exit 2; }
ID=${BASH_REMATCH[1]}
MIG=$DIR/$NAME
[ -f "$MIG" ] || { echo "NO_SUCH_MIGRATION $MIG"; exit 2; }
PARAMS="$HERE/migration${ID}_${MODE}.params.json"
JOBMODE=$(printf '%s' "$MODE" | tr '[:lower:]' '[:upper:]')
python3 -I -c 'import json, sys; p = json.load(open(sys.argv[1]))
sys.exit(0 if p.get("migrations") == [sys.argv[2]] and p.get("mode") == sys.argv[3] else 1)' "$PARAMS" "$NAME" "$JOBMODE" \
  2>/dev/null || { echo "NO_PARAMS_FOR_THIS_MIGRATION $PARAMS (must name $NAME, mode $JOBMODE)"; exit 2; }
python3 -I "$HERE/check_migration_log.py" --covers "$NAME" \
  || { echo "NO_LOG_CHECKS_FOR_THIS_MIGRATION $NAME (add them to $HERE/check_migration_log.py)"; exit 2; }
python3 -I "$HERE/check_migration_log.py" --params-ok "$PARAMS" \
  || { echo "PARAMS_NOT_AS_REVIEWED $PARAMS (each probe as in check_migration_log.py's list for $NAME)"; exit 2; }
command -v railway >/dev/null || { echo "RAILWAY_CLI_NOT_ON_PATH"; exit 2; }
HAVE=$(sha256sum "$MIG" | cut -d' ' -f1)
[ "$HAVE" = "$WANT" ] || { echo "SHA_MISMATCH have=$HAVE want=$WANT"; exit 6; }
git diff --quiet HEAD -- "$MIG" && git ls-files --error-unmatch "$MIG" >/dev/null 2>&1 \
  || { echo "MIGRATION_NOT_COMMITTED"; exit 6; }
# what else runs on dev or judges it is the committed version too: an edited params file reaches the database as SQL
JOBFILES=$(printf '%s\n' "$PARAMS" "$HERE/migration${ID}_dryrun.params.json" "$HERE/check_migration_log.py" \
  "$HERE/run_migration.sh" scripts/onboarding/run_job.sh scripts/onboarding/migration_job.py scripts/onboarding/Dockerfile \
  | sort -u)
UNCOMMITTED=$(for f in $JOBFILES; do git diff --quiet HEAD -- "$f" && git ls-files --error-unmatch "$f" >/dev/null 2>&1 \
  || echo "$f"; done)
[ -z "$UNCOMMITTED" ] || { echo "JOB_FILES_NOT_COMMITTED $(echo $UNCOMMITTED) (commit them, then run again)"; exit 6; }
LOG="$HERE/migration${ID}_${MODE}.log"
if [ "$MODE" = apply ]; then
  ! awk '{print $2}' "$DIR/APPLIED.sha256" | grep -qxF "$NAME" || { echo "ALREADY_IN_APPLIED_SHA256"; exit 8; }
  python3 -I "$HERE/check_migration_log.py" "$HERE/migration${ID}_dryrun.log" \
    "$HERE/migration${ID}_dryrun.params.json" "$WANT" >/dev/null \
    || { echo "NO_PASSING_DRYRUN_FOR_THIS_SHA256"; exit 7; }
fi
[ ! -e "$LOG" ] || { echo "LOG_EXISTS $LOG (keep it; move it aside to run again)"; exit 9; }
{ echo "MIGRATION $NAME $MODE sha256=$WANT commit=$(git rev-parse --short=12 HEAD)"
  scripts/onboarding/run_job.sh scripts/onboarding/migration_job.py "$PARAMS" "$LOG" "$MIG"; } 2>&1 \
  | tee "$HERE/migration${ID}_${MODE}.run.txt"
echo "RUN_JOB_EXIT ${PIPESTATUS[0]}"
grep -q '^VAR_REMOVED$' "$HERE/migration${ID}_${MODE}.run.txt" \
  || echo "WARNING: VAR_REMOVED not printed: remove DATABASE_URL from orc-test-runner and check it is gone before anything else"
UNVERIFIED="APPLY_NOT_VERIFIED: the file may still have committed (a job that fails after its COMMIT keeps it):"
UNVERIFIED+=" read the state back before anything else"
[ -s "$LOG" ] || { echo "NO_LOG"; [ "$MODE" = dryrun ] || echo "$UNVERIFIED"; exit 4; }
python3 -I "$HERE/check_migration_log.py" "$LOG" "$PARAMS" "$WANT"; RC=$?
[ "$RC" = 0 ] || [ "$MODE" = dryrun ] || echo "$UNVERIFIED"
exit "$RC"
