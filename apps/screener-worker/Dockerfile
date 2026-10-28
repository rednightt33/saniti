# The EDGE screener-worker (apps/screener-worker/README.md): Node 22 with type stripping, no npm dependency.
# Build context: the repository root (as apps/backtest-worker and apps/feature-04-worker), e.g.
#   docker build -f apps/screener-worker/Dockerfile -t screener-worker .
# The image keeps the repository layout under /app: the worker imports the screener core, the backtest core, the
# Terminal's calculation module and the backtest worker's terminal-api client by relative path, and screener_engine
# (src/version.ts) hashes those files by their path from the repository root, so the same files give the same version
# in the repository and in the image. Only what the server reads is copied (report 07 section 7.1): the worker's
# package.json (ES modules) and src; the screener core (with its generated registry, metric catalog and presets) and the
# registry generator (its sha256 is a source the start-up check compares); the backtest core; the indicator formulas and
# the indicator registry they are described by; from the backtest worker the terminal-api client, the module loader and
# the registry script (the start-up registry check). Never copied: tests, node_modules, the page, any key.
FROM node:22-slim

ENV NODE_ENV=production
WORKDIR /app
COPY apps/screener-worker/package.json ./apps/screener-worker/package.json
COPY apps/screener-worker/src ./apps/screener-worker/src
COPY apps/edge-bff/screener/src/core ./apps/edge-bff/screener/src/core
COPY apps/edge-bff/screener/scripts/build-screener-registry.mjs ./apps/edge-bff/screener/scripts/build-screener-registry.mjs
COPY apps/edge-bff/backtest/src/core ./apps/edge-bff/backtest/src/core
COPY apps/edge-bff/terminal/src/calc ./apps/edge-bff/terminal/src/calc
COPY apps/edge-bff/terminal/src/data/indRegistry.json ./apps/edge-bff/terminal/src/data/indRegistry.json
COPY apps/backtest-worker/src/terminal.ts ./apps/backtest-worker/src/terminal.ts
COPY apps/backtest-worker/loader ./apps/backtest-worker/loader
COPY apps/backtest-worker/scripts/build-registry.mjs ./apps/backtest-worker/scripts/build-registry.mjs

WORKDIR /app/apps/screener-worker
# the base image's unprivileged user; SCREENER_CACHE_DIR, when set, must be writable by it (uid 1000), e.g. /tmp/screener-cache
USER node
EXPOSE 8080
# the backtest worker's loader (imported, not copied): the Terminal's sources resolve under Node as under Vite (ERRORS M249)
CMD ["node", "--experimental-strip-types", "--no-warnings=ExperimentalWarning", "--import", "../backtest-worker/loader/register.mjs", "src/server.ts"]
