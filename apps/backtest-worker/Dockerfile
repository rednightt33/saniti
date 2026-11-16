# The EDGE backtest worker (apps/backtest-worker/README.md): Node 22 with type stripping, no npm dependency.
# Build context: the repository root (as apps/feature-04-worker), e.g.
#   docker build -f apps/backtest-worker/Dockerfile -t backtest-worker .
# The image keeps the repository layout under /app: the worker imports the shared core and the Terminal's calculation
# module by relative path, and engine_version (src/version.ts) hashes those files by their path from the repository
# root, so the same files give the same version in the repository and in the image. Only what the server reads is
# copied: the worker's package.json (ES modules), src, the registry script (the start-up registry check) and the module
# loader, the shared core, the Screener core (its condition grammar), the indicator and Flow formulas, and the registries they
# are described by.
FROM node:22-slim

ENV NODE_ENV=production
WORKDIR /app
COPY apps/backtest-worker/package.json ./apps/backtest-worker/package.json
COPY apps/backtest-worker/src ./apps/backtest-worker/src
COPY apps/backtest-worker/scripts ./apps/backtest-worker/scripts
COPY apps/backtest-worker/loader ./apps/backtest-worker/loader
COPY apps/edge-bff/backtest/src/core ./apps/edge-bff/backtest/src/core
COPY apps/edge-bff/terminal/src/calc ./apps/edge-bff/terminal/src/calc
COPY apps/edge-bff/terminal/src/data/indRegistry.json ./apps/edge-bff/terminal/src/data/indRegistry.json
# EXEC-BACKTEST-REVAMP P0.3 (ERRORS M453): calc/flow.ts reads its defaults from the flow registry, and engine_version
# hashes it (src/version.ts SOURCES)
COPY apps/edge-bff/terminal/src/data/flowRegistry.json ./apps/edge-bff/terminal/src/data/flowRegistry.json
# EXEC-BACKTEST-REVAMP P1: conditions in the Screener's grammar are computed by the Screener core (src/grammar.ts); the
# start-up check reads its registry's source files, the registry generator among them (grammar.ts grammarProblems)
COPY apps/edge-bff/screener/src/core ./apps/edge-bff/screener/src/core
COPY apps/edge-bff/screener/scripts/build-screener-registry.mjs ./apps/edge-bff/screener/scripts/build-screener-registry.mjs

WORKDIR /app/apps/backtest-worker
# the base image's unprivileged user; BACKTEST_CACHE_DIR, when set, must be writable by it (uid 1000)
USER node
EXPOSE 8080
# loader/register.mjs: the Terminal's sources resolve under Node as under Vite (loader/resolve.mjs, ERRORS M249)
CMD ["node", "--experimental-strip-types", "--import", "./loader/register.mjs", "src/server.ts"]
