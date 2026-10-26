#!/bin/bash
# Upload the stockbit-updater code to its Railway service (EXEC-STOCKBIT-UPDATER). Every deployment runs one round, so
# deploy a code change only when a round may run (the current STOCKBIT_TOKEN is used). Run from the repository root.
#   apps/stockbit-updater/deploy.sh
set -eu
P=8aef1702-030b-49cb-9df7-5ac2e0a42691; E=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/updater" "$STAGE/events" "$STAGE/scripts" "$STAGE/features"
cp apps/stockbit-updater/*.py apps/stockbit-updater/requirements.txt "$STAGE/updater/"
cp apps/stockbit-updater/Dockerfile apps/stockbit-updater/railway.json "$STAGE/"
cp apps/stockbit-event-annotation/job.py apps/stockbit-event-annotation/stockbit_events.py "$STAGE/events/"
cp scripts/*.py "$STAGE/scripts/"
cp -r features/feature04 "$STAGE/features/feature04"
mkdir -p "$STAGE/database/migrations" && cp database/migrations/20261025_001_index_feature05_remove_frequency_coverage.sql "$STAGE/database/migrations/"
rm -rf "$STAGE"/features/feature04/__pycache__ "$STAGE"/scripts/__pycache__
railway up "$STAGE" --path-as-root -p $P -e $E --service stockbit-updater --detach
