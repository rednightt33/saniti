#!/bin/bash
# EXEC-SCREENER deploy runbook steps 5 and 6: run terminal_check.py once on orc-test-runner (dev, private network) and
# keep its log. The pattern of scripts/onboarding/run_job.sh, with TERMINAL_PROXY_KEY in place of DATABASE_URL: set on
# orc-test-runner only for the run, as the Railway reference ${{terminal-api.TERMINAL_PROXY_KEY}} (no value is written or
# printed), and removed afterwards; prints VAR_REMOVED or VAR_STILL_PRESENT. Prepared, not run, by the deploy-prep step.
#
#   verification/screener/jobs/run_terminal_check.sh absent|present <log file>
#
# absent: right after the terminal-api deploy (the /state field `xsection` is null until a publication writes one);
# present: after the publisher run (every indexed file granted, downloaded and checked by sha256 and size).
# Run from the repository root with a Railway project token in RAILWAY_TOKEN and the Railway CLI 5.71.0 on PATH as
# `railway`. Railway IDs: PROJECT_CONTEXT.md. A new deployment replaces the one running, so the runner must be idle
# (ERRORS M210, M227): checked below as run_job.sh does.
set -u
EXPECT=${1:-}; LOG=${2:-}
case "$EXPECT" in absent|present) ;; *) echo "usage: $0 absent|present <log>"; exit 2 ;; esac
[ -n "$LOG" ] && [ ! -e "$LOG" ] || { echo "LOG_MISSING_OR_EXISTS $LOG"; exit 2; }
command -v railway >/dev/null || { echo "RAILWAY_CLI_NOT_ON_PATH"; exit 2; }
P=8aef1702-030b-49cb-9df7-5ac2e0a42691; E=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49; S=09358b92-09d4-4da2-b547-bf8f621e226c
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
STAGE=$(mktemp -d)
cp "$HERE/terminal_check.py" "$STAGE/job.py"
cp "$ROOT/scripts/onboarding/Dockerfile" "$STAGE/Dockerfile"
printf '{"base": "http://terminal-api.railway.internal:8080", "expect": "%s", "names": ["price", "actions"], "manifest_ticker": "BBCA"}\n' \
  "$EXPECT" > "$STAGE/params.json"
cleanup() {
  for _ in 1 2 3; do
    timeout 60 railway variable delete TERMINAL_PROXY_KEY -p $P -e $E -s $S >/dev/null 2>&1
    timeout 60 railway variable list -p $P -e $E -s $S --json 2>/dev/null \
      | python3 -c "import sys,json;sys.exit(0 if 'TERMINAL_PROXY_KEY' not in json.load(sys.stdin) else 1)" \
      && { echo VAR_REMOVED; rm -rf "$STAGE"; return; }
  done
  echo VAR_STILL_PRESENT; rm -rf "$STAGE"
}
latest=$(timeout 60 railway deployment list -p $P -e $E -s $S --json 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'],d[0]['status']) if d else print('none none')" 2>/dev/null)
[ -n "$latest" ] || { echo "DEPLOYMENT_LIST_FAILED"; rm -rf "$STAGE"; exit 5; }
set -- $latest; LAST_ID=$1; LAST_STATUS=$2
if [ "$LAST_ID" != none ]; then
  case "$LAST_STATUS" in
    SUCCESS|FAILED|CRASHED|REMOVED|SKIPPED)
      if [ "$LAST_STATUS" = SUCCESS ] && ! timeout 60 railway logs "$LAST_ID" -p $P -s $S -e $E --deployment --lines 5000 2>&1 \
           | grep -q 'JOB_DONE\|OTR {"event": "done"\|Traceback'; then
        echo "RUNNER_BUSY $LAST_ID: its job has not finished; wait for JOB_DONE (ERRORS M210/M227)"; rm -rf "$STAGE"; exit 5
      fi ;;
    *) echo "RUNNER_BUSY $LAST_ID ($LAST_STATUS): wait until it finishes (ERRORS M210/M227)"; rm -rf "$STAGE"; exit 5 ;;
  esac
fi
trap cleanup EXIT
timeout 60 railway variable set 'TERMINAL_PROXY_KEY=${{terminal-api.TERMINAL_PROXY_KEY}}' -p $P -e $E -s $S --skip-deploys \
  >/dev/null 2>&1 || { echo SET_FAILED; exit 3; }
id=$(timeout 300 railway up "$STAGE" --path-as-root -p $P --service orc-test-runner --environment dev --detach 2>&1 \
  | grep -oE "id=[0-9a-f-]+" | cut -d= -f2)
echo "JOB ${id:-NOT_STARTED}"
[ -n "${id:-}" ] || exit 4
for _ in $(seq 1 45); do
  sleep 20
  timeout 60 railway logs "$id" -p $P -s $S -e $E --deployment --lines 2000 > "$LOG" 2>&1
  grep -q "JOB_DONE\|Traceback" "$LOG" && break
done
grep "^OUT \|^ERR \|VERDICT\|Traceback\|JOB_DONE" "$LOG" | cut -c1-400
