#!/bin/bash
# Upload postgres-memory-cron (EXEC-PG-RESTART-CRON). The service is not GitHub-connected (a push to main never deploys
# or restarts anything). A Railway service with a cronSchedule does not run on deploy, only on its schedule or Run Now
# (ERRORS M229); a new upload is also how a variable change (PG_RESTART_TIMES_WIB, PG_RESTART_MODE) takes effect.
# Run from the repository root with the project token in RAILWAY_TOKEN:
#   apps/postgres-memory-cron/deploy.sh
set -eu
P=8aef1702-030b-49cb-9df7-5ac2e0a42691; E=4d3e5af2-302b-4a2e-84e2-7d7476d6ff49
STAGE=$(mktemp -d); trap 'rm -rf "$STAGE"' EXIT
cp apps/postgres-memory-cron/Dockerfile apps/postgres-memory-cron/railway.json scripts/restart_postgres.py "$STAGE/"
railway up "$STAGE" --path-as-root -p $P -e $E --service postgres-memory-cron --detach
