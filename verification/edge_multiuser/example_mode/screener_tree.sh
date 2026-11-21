#!/bin/bash
# EXEC-MU-ACCOUNTS 3e, the Screener's example (ERRORS M527): stages in <target>, at their repository paths, the files the
# capture job's node part needs (screener_capture.ts), so its relative imports resolve as in the repository: every path
# the screener-worker's own image copies (apps/screener-worker/Dockerfile, read from it), the worker tests' fake terminal
# and helpers with the capture module, the capture script. run_job.sh takes <target> as one extra (RUN_JOB_IMAGE=node).
#   verification/edge_multiuser/example_mode/screener_tree.sh <target>      (from anywhere; <target> is replaced)
set -eu
T=$1; R=$(cd "$(dirname "$0")/../../.." && pwd)
rm -rf "$T"; mkdir -p "$T"
paths=$(sed -n 's/^COPY \(apps\/[^ ]*\) .*/\1/p' "$R/apps/screener-worker/Dockerfile")
[ -n "$paths" ] || { echo "no COPY line read from apps/screener-worker/Dockerfile" >&2; exit 1; }
for p in $paths apps/screener-worker/tests/example-capture.ts apps/screener-worker/tests/fake-terminal.mjs \
         apps/screener-worker/tests/helpers.ts apps/backtest-worker/tests/fake-terminal.mjs \
         verification/edge_multiuser/example_mode/screener_capture.ts; do
  mkdir -p "$T/$(dirname "$p")"; cp -r "$R/$p" "$T/$p"
done
echo "TREE $(find "$T" -type f | wc -l) files"
