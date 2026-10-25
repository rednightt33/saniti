#!/bin/bash
# Run the Stockbit event load (job.py) or the read-only export (export_job.py) on orc-test-runner.
#
#   apps/stockbit-event-annotation/run_on_railway.sh load   <params.json> <log>   # token on stdin (one line)
#   apps/stockbit-event-annotation/run_on_railway.sh export <log>
#
# load: STOCKBIT_TOKEN is read from stdin and set on orc-test-runner with `railway variable set --stdin` (never on the
# command line, never printed), then scripts/onboarding/run_job.sh sets DATABASE_URL, uploads and waits; both
# variables are removed afterwards and the script prints TOKEN_REMOVED or TOKEN_STILL_PRESENT.
# Rule M210: orc-test-runner runs one deployment at a time; check that no suite or job runs there first
# (UPDATE_TABLE.md, section 2). Railway IDs: PROJECT_CONTEXT.md. Run from the repository root.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
P=8aef1702-030b-49cb-9df7-5ac2e0a42691; E=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49; S=09358b92-09d4-4da2-b547-bf8f621e226c
MODE=${1:-}
case "$MODE" in
  export)
    [ $# -eq 2 ] || { echo "usage: $0 export <log>"; exit 2; }
    EMPTY=$(mktemp); echo '{}' > "$EMPTY"
    bash "$ROOT/scripts/onboarding/run_job.sh" "$HERE/export_job.py" "$EMPTY" "$2"
    rc=$?; rm -f "$EMPTY"; exit $rc ;;
  load)
    [ $# -eq 3 ] || { echo "usage: $0 load <params.json> <log>  (token on stdin)"; exit 2; }
    IFS= read -r TOKEN || true
    [ "$(printf '%s' "$TOKEN" | tr -cd '.' | wc -c)" -eq 2 ] || { echo "stdin is not a JWT"; exit 2; }
    remove_token() {
      for _ in 1 2 3; do
        timeout 60 railway variable delete STOCKBIT_TOKEN -p $P -e $E -s $S >/dev/null 2>&1
        timeout 60 railway variable list -p $P -e $E -s $S --json 2>/dev/null \
          | python3 -c "import sys,json;sys.exit(0 if 'STOCKBIT_TOKEN' not in json.load(sys.stdin) else 1)" \
          && { echo TOKEN_REMOVED; return; }
      done
      echo TOKEN_STILL_PRESENT
    }
    trap remove_token EXIT
    printf '%s' "$TOKEN" | timeout 60 railway variable set STOCKBIT_TOKEN --stdin -p $P -e $E -s $S --skip-deploys \
      >/dev/null 2>&1 || { echo TOKEN_SET_FAILED; exit 3; }
    unset TOKEN
    bash "$ROOT/scripts/onboarding/run_job.sh" "$HERE/job.py" "$2" "$3" "$HERE/stockbit_events.py" ;;
  *) echo "usage: $0 load <params.json> <log> | export <log>"; exit 2 ;;
esac
