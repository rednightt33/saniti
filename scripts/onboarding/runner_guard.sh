# The one check that orc-test-runner is free before a job starts (ERRORS M210, M227, M322). Sourced by every script that
# starts a runner job: scripts/onboarding/run_job.sh and verification/screener/jobs/run_terminal_check.sh. It defines
# functions only.
#
# A new deployment replaces the one running, so a job starts only when the latest deployment has finished:
#   - its log, from its latest container start, holds JOB_EXIT <code>, which the Dockerfiles' wrapper prints after every
#     job whatever the job prints (M322, user go 2026-11-01). Since 2026-11-01 the runner never restarts a job (restart
#     policy NEVER, user "OK"), so a failed job (JOB_EXIT non-zero) has finished too;
#   - or, for a job started before the wrapper, JOB_DONE, a Traceback or an orc-test-runner suite's OTR "done";
#   - or its deployment ended (FAILED, CRASHED, REMOVED, SKIPPED).

# the log lines from the latest "Starting Container" on (the whole log when there is none)
last_start() { awk '/Starting Container/{n=0; delete l} {l[++n]=$0} END{for(i=1;i<=n;i++) print l[i]}'; }
# stdin is a job's log: has its latest start finished?
finished() { last_start | grep -q 'JOB_EXIT [0-9]*$\|JOB_DONE\|Traceback\|OTR {"event": "done"'; }
# a job log file has an end line (the poll's stop condition: success or failure)
ended() { grep -q 'JOB_EXIT\|JOB_DONE\|Traceback' "$1"; }

# runner_free <project> <environment> <service>: returns 0 when a job may start, else prints RUNNER_BUSY (or
# DEPLOYMENT_LIST_FAILED) and returns 5
runner_free() {
  local latest last_id last_status
  latest=$(timeout 60 railway deployment list -p "$1" -e "$2" -s "$3" --json 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'],d[0]['status']) if d else print('none none')" 2>/dev/null)
  [ -n "$latest" ] || { echo "DEPLOYMENT_LIST_FAILED"; return 5; }
  last_id=${latest% *}; last_status=${latest#* }
  [ "$last_id" = none ] && return 0
  case "$last_status" in
    FAILED|CRASHED|REMOVED|SKIPPED) return 0 ;;
    SUCCESS)
      timeout 60 railway logs "$last_id" -p "$1" -s "$3" -e "$2" --deployment --lines 5000 2>&1 | finished && return 0
      echo "RUNNER_BUSY $last_id: its job has not finished; wait for JOB_EXIT (ERRORS M210/M227/M322)"; return 5 ;;
    *) echo "RUNNER_BUSY $last_id ($last_status): wait until it finishes (ERRORS M210/M227)"; return 5 ;;
  esac
}
