#!/bin/bash
# Upload idx-intraday-cron from HEAD. The service is a CLI upload (serviceConnect is refused for the project token,
# RAILWAY_CHANGELOG 2026-10-31): the tree holds apps/idx-price-cron and features/feature04, with Dockerfile.intraday
# as its Dockerfile. Run from the repository root with RAILWAY_TOKEN set; Railway IDs: PROJECT_CONTEXT.md.
set -eu
T=$(mktemp -d)
git archive HEAD apps/idx-price-cron features/feature04 | tar -x -C "$T"
cp "$T/apps/idx-price-cron/Dockerfile.intraday" "$T/Dockerfile"
railway up "$T" --path-as-root -p 8aef1702-030b-49cb-9df7-5ac2e0a42691 --service idx-intraday-cron --environment dev --detach
