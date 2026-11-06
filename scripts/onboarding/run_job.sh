#!/bin/bash
# NEW_TABLE_ONBOARDING_PLAN.md section 4: run one onboarding job on orc-test-runner (Railway dev) and keep its log.
#
#   scripts/onboarding/run_job.sh <job.py> <params.json> <log file> [extra file or directory ...]
#
# The job, its params.json, the extras and Dockerfile (or Dockerfile.l2 when a requirements.txt is an extra) are staged in a
# temporary directory and uploaded with `railway up`. DATABASE_URL is set on orc-test-runner only for the run, as the
# Railway reference ${{Postgres.DATABASE_URL}} (no value is written or printed), and removed afterwards; the script
# prints VAR_REMOVED or VAR_STILL_PRESENT. Run from the repository root with a Railway token for the project.
# Manual rule (ERRORS M210, user 2026-10-23): a new deployment replaces the one running, so never start a job here
# while an orc-test-runner suite runs (until its log prints OTR {"event": "done"}).
# Railway IDs: PROJECT_CONTEXT.md. A job prints OUT/ERR/VERDICT lines (JOB_DONE when it wants to say so); the
# Dockerfile's wrapper prints JOB_EXIT <exit code> after every job (ERRORS M322).
# A job that writes a lot (AGENTS.md "Postgres memory after large updates") puts "large_write": true in its params.json:
# the script then restarts Postgres afterwards through scripts/restart_postgres.py --apply (all its guards apply); every
# other job ends with a POSTGRES_MEMORY_CHECK line (EXEC-PG-MEMORY).
# Optional environment (EXEC-PRICE-GAP-0917): RUN_JOB_POLL_ROUNDS (20 s each, default 90) and RUN_JOB_LOG_LINES
# (default and most 5000: `railway logs` refuses more with "Error in limit - Invalid input") for long jobs; RUN_JOB_EXTRA_VARS, space-separated NAME=reference pairs (Railway references such as
# ${{telegram-monitor.TELEGRAM_NOTIFY_SECRET}}, never values) set like DATABASE_URL for the run and removed afterwards.
set -u
[ $# -ge 3 ] || { echo "usage: $0 <job.py> <params.json> <log> [extras...]"; exit 2; }
JOB=$1; PARAMS=$2; LOG=$3; shift 3
P=8aef1702-030b-49cb-9df7-5ac2e0a42691; E=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49; S=09358b92-09d4-4da2-b547-bf8f621e226c
HERE=$(cd "$(dirname "$0")" && pwd)
STAGE=$(mktemp -d)
cp "$JOB" "$STAGE/job.py"; cp "$PARAMS" "$STAGE/params.json"
DOCKERFILE="$HERE/Dockerfile"
for extra in "$@"; do
  cp -r "$extra" "$STAGE/"
  # a service's requirements.txt among the extras (orc for l2_tools, the Governor for governor_check) is installed
  [ "$(basename "$extra")" = requirements.txt ] && DOCKERFILE="$HERE/Dockerfile.l2"
done
cp "$DOCKERFILE" "$STAGE/Dockerfile"
EXTRA=${RUN_JOB_EXTRA_VARS:-}
NAMES="DATABASE_URL"; for pair in $EXTRA; do NAMES="$NAMES ${pair%%=*}"; done
cleanup() {
  for _ in 1 2 3; do
    for name in $NAMES; do timeout 60 railway variable delete "$name" -p $P -e $E -s $S >/dev/null 2>&1; done
    timeout 60 railway variable list -p $P -e $E -s $S --json 2>/dev/null \
      | python3 -c "import sys,json;v=json.load(sys.stdin);sys.exit(0 if not set(sys.argv[1:]) & set(v) else 1)" $NAMES \
      && { echo VAR_REMOVED; rm -rf "$STAGE"; return; }
  done
  echo VAR_STILL_PRESENT; rm -rf "$STAGE"
}
# ERRORS M210/M227/M322: the runner must be free (its latest job finished) before a new job starts; the one check is
# runner_guard.sh, shared with every script that starts a runner job.
. "$HERE/runner_guard.sh"
runner_free $P $E $S || { rm -rf "$STAGE"; exit 5; }
trap cleanup EXIT
timeout 60 railway variable set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' -p $P -e $E -s $S --skip-deploys >/dev/null 2>&1 \
  || { echo SET_FAILED; exit 3; }
for pair in $EXTRA; do
  timeout 60 railway variable set "$pair" -p $P -e $E -s $S --skip-deploys >/dev/null 2>&1 || { echo SET_FAILED; exit 3; }
done
id=$(timeout 300 railway up "$STAGE" --path-as-root -p $P --service orc-test-runner --environment dev --detach 2>&1 \
  | grep -oE "id=[0-9a-f-]+" | cut -d= -f2)
echo "JOB ${id:-NOT_STARTED}"
[ -n "${id:-}" ] || exit 4
fetch() { timeout 60 railway logs "$id" -p $P -s $S -e $E --deployment --lines "$(( ${RUN_JOB_LOG_LINES:-5000} > 5000 ? 5000 : ${RUN_JOB_LOG_LINES:-5000} ))" > "$LOG" 2>&1; }
for _ in $(seq 1 "${RUN_JOB_POLL_ROUNDS:-90}"); do
  sleep 20
  fetch
  ended "$LOG" && break
done
# ERRORS M372 (2026-11-06): the log service can hold the job's own lines back after JOB_EXIT (a DRYRUN log missed 8 of 33
# lines, JOB_DONE included); the log is read again until two reads 15 s apart hold the same lines
prev=-1
for _ in 1 2 3 4 5 6; do n=$(grep -c "" "$LOG"); [ "$n" = "$prev" ] && break; prev=$n; sleep 15; fetch; done
grep -c "^OUT \|\"OUT " "$LOG"; grep "ERR \|VERDICT\|Traceback\|JOB_DONE\|JOB_EXIT\|MIG \|READBACK" "$LOG" | cut -c1-400
# EXEC-PG-MEMORY (user 2026-11-03, AGENTS.md "Postgres memory after large updates"): a job whose params.json says
# "large_write": true restarts Postgres afterwards through scripts/restart_postgres.py --apply (every guard of that
# script applies: memory, crons, B6, running statements); every other job prints the memory check, so the agent sees it
if grep -q '"large_write": *true' "$STAGE/params.json" 2>/dev/null; then
  echo "POSTGRES_RESTART (large_write)"; python3 "$HERE/../restart_postgres.py" --apply 2>&1 | tail -2
else
  echo "POSTGRES_MEMORY_CHECK"; python3 "$HERE/../restart_postgres.py" 2>&1 | tail -1
fi
