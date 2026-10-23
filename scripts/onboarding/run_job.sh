#!/bin/bash
# NEW_TABLE_ONBOARDING_PLAN.md section 4: run one onboarding job on orc-test-runner (Railway dev) and keep its log.
#
#   scripts/onboarding/run_job.sh <job.py> <params.json> <log file> [extra file or directory ...]
#
# The job, its params.json, the extras and Dockerfile (or Dockerfile.l2 when a requirements.txt is an extra) are staged in a
# temporary directory and uploaded with `railway up`. DATABASE_URL is set on orc-test-runner only for the run, as the
# Railway reference ${{Postgres.DATABASE_URL}} (no value is written or printed), and removed afterwards; the script
# prints VAR_REMOVED or VAR_STILL_PRESENT. Run from the repository root with a Railway token for the project.
# Railway IDs: PROJECT_CONTEXT.md. A job prints OUT/ERR/VERDICT lines and ends with JOB_DONE.
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
cleanup() {
  for _ in 1 2 3; do
    timeout 60 railway variable delete DATABASE_URL -p $P -e $E -s $S >/dev/null 2>&1
    timeout 60 railway variable list -p $P -e $E -s $S --json 2>/dev/null \
      | python3 -c "import sys,json;sys.exit(0 if 'DATABASE_URL' not in json.load(sys.stdin) else 1)" \
      && { echo VAR_REMOVED; rm -rf "$STAGE"; return; }
  done
  echo VAR_STILL_PRESENT; rm -rf "$STAGE"
}
trap cleanup EXIT
timeout 60 railway variable set 'DATABASE_URL=${{Postgres.DATABASE_URL}}' -p $P -e $E -s $S --skip-deploys >/dev/null 2>&1 \
  || { echo SET_FAILED; exit 3; }
id=$(timeout 300 railway up "$STAGE" --path-as-root -p $P --service orc-test-runner --environment dev --detach 2>&1 \
  | grep -oE "id=[0-9a-f-]+" | cut -d= -f2)
echo "JOB ${id:-NOT_STARTED}"
[ -n "${id:-}" ] || exit 4
for _ in $(seq 1 90); do
  sleep 20
  timeout 60 railway logs "$id" -p $P -s $S -e $E --deployment --lines 5000 > "$LOG" 2>&1
  grep -q "JOB_DONE\|Traceback" "$LOG" && break
done
grep -c "^OUT \|\"OUT " "$LOG"; grep "ERR \|VERDICT\|Traceback\|JOB_DONE\|MIG \|READBACK" "$LOG" | cut -c1-400
