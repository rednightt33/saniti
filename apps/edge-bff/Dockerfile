# EXEC-TERMINAL-API T5: the terminal page (terminal/, TypeScript + Vite) is built here and copied into static/terminal-app;
# the build output is not kept in git.
# EXEC-MU-ACCOUNTS Phase 0: every page imports the shared session module (shared/edge-session.ts), so each stage copies
# shared/ beside its own folder as in the repository.
FROM node:22-slim AS terminal
WORKDIR /build/terminal
COPY terminal/package.json terminal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f (CONTRACT.md 8 "Lab code"): the page build filters the registries by release stage (shared/release-filter.mjs) and
# stops without the release file; it builds the public page and the admin's lab page (static/terminal-app-lab)
COPY catalog/releases.json /build/catalog/releases.json
COPY terminal/ ./
RUN npm run build

# EDGE backtest (CONTRACT.md section 10): the backtest page (backtest/, TypeScript + Vite) is built here into its dist/
# and copied into static/backtest-app; its shared core imports the Terminal's calculation module and indicator registry
# (terminal/src), so that source sits beside it as in the repository. The build output is not kept in git.
# EXEC-BACKTEST-REVAMP Stage D: the page's condition window and test cards read the Screener's catalog entries, forms and
# contract (screener/src), so that source sits beside it too (ERRORS M461: the 2026-11-16 build failed without it).
FROM node:22-slim AS backtest
WORKDIR /build/backtest
COPY backtest/package.json backtest/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY terminal/src /build/terminal/src
COPY screener/src /build/screener/src
# 3f round 2 (CRIT-4, ERRORS M525): each copied source folder with its tsconfig.json, which esbuild reads for the files
# under it (target ES2022: the class fields), so the page the image ships is the page CI builds and tests
COPY terminal/tsconfig.json /build/terminal/tsconfig.json
COPY screener/tsconfig.json /build/screener/tsconfig.json
COPY shared /build/shared
# 3f: the release file the page build filters by (shared/release-filter.mjs); dist/ is the public page, dist-lab/ the lab page
COPY catalog/releases.json /build/catalog/releases.json
COPY backtest/ ./
RUN npm run build

# EXEC-SCREENER (report FRONTEND INTEGRATION 9.1, 9.7): the screener page (screener/, TypeScript + Vite) is built here into
# its dist/ and copied into static/screener-app. Its build typechecks the screener core (screener/src/core) with the page;
# that core imports the Backtest core (backtest/src/core), which imports the Terminal's calculation module and indicator
# registry, and the page reuses Terminal and Backtest page helpers (the loading ring, the rack cache, the ticker search),
# so both sources sit beside it as in the repository. The page bundle carries no formula (its bundle test). The build
# output is not kept in git.
FROM node:22-slim AS screener
WORKDIR /build/screener
COPY screener/package.json screener/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY terminal/src /build/terminal/src
COPY backtest/src /build/backtest/src
# 3f round 2 (CRIT-4, ERRORS M525): each copied source folder with its tsconfig.json (the backtest stage's note)
COPY terminal/tsconfig.json /build/terminal/tsconfig.json
COPY backtest/tsconfig.json /build/backtest/tsconfig.json
COPY shared /build/shared
# 3f: the release file the page build filters the registries by (shared/release-filter.mjs, fail closed; checker B4)
COPY catalog/releases.json /build/catalog/releases.json
COPY screener/ ./
RUN npm run build

# EXEC-RADAR R7 (user go 2026-11-14): the Radar page (radar/, TypeScript + Vite, the R10 design) is built here into its
# dist/ and copied into static/radar-app. It shares no source with the other pages and carries no rule: every result is
# Feature 07's, relayed by /api/v1/radar (app/radar.py). The build output is not kept in git.
FROM node:22-slim AS radar
WORKDIR /build/radar
COPY radar/package.json radar/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f round 2: every page build applies the release filter (shared/release-filter.mjs), which stops without this file
COPY catalog/releases.json /build/catalog/releases.json
COPY radar/ ./
RUN npm run build

# EXEC-OVERVIEW O5 (user go 2026-11-15): the Market Overview page (overview/, TypeScript + Vite, the design
# market-overview-target-c-ihsg-flow.html) is built here into its dist/ and copied into static/overview-app. It shares no
# source with the other pages and computes no figure: every number is the publisher's (overview/*.json.gz), relayed by
# /api/v1/overview (app/overview.py). The build output is not kept in git.
FROM node:22-slim AS overview
WORKDIR /build/overview
COPY overview/package.json overview/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f round 2: every page build applies the release filter (shared/release-filter.mjs), which stops without this file
COPY catalog/releases.json /build/catalog/releases.json
COPY overview/ ./
RUN npm run build

# EXEC-SECTOR-ANALYSIS S3/S4 (the user's go 2026-11-26: "1A 2A 3 go"): the Sector Analysis page (sector/, TypeScript +
# Vite, the port of the user's final prototype; verification/sector_analysis/CONTRACT.md 5) is built here into its dist/
# and copied into static/sector-app, as the Overview's. Its figures are the publisher's family sector/ relayed by
# /api/v1/sector (app/sector.py); what depends on the user's choice it computes in the browser. The build output is not
# kept in git.
FROM node:22-slim AS sector
WORKDIR /build/sector
COPY sector/package.json sector/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f round 2: every page build applies the release filter (shared/release-filter.mjs), which stops without this file
COPY catalog/releases.json /build/catalog/releases.json
COPY sector/ ./
RUN npm run build

# EXEC-WATCHLIST L5 (user go 2026-11-16): the Watchlist page (watchlist/, TypeScript + Vite, the approved light mockup
# watchlist_light_mockup.html) is built here into its dist/ and copied into static/watchlist-app. It shares no source with
# the other pages and computes no figure: every number is the publisher's (watchlist/watchlist-stocks.*.json.gz), relayed
# by /api/v1/watchlist (app/watchlist.py), which also keeps the account's lists. The build output is not kept in git.
FROM node:22-slim AS watchlist
WORKDIR /build/watchlist
COPY watchlist/package.json watchlist/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f round 2: every page build applies the release filter (shared/release-filter.mjs), which stops without this file
COPY catalog/releases.json /build/catalog/releases.json
COPY watchlist/ ./
RUN npm run build

# EXEC-MU-ACCOUNTS Phase 4 (the user, 2026-11-22: "1A, 2B, 3A"): the admin page of the beta (admin/, TypeScript + Vite)
# is built here into its dist/ and copied into static/admin-app; edge-bff serves its files to the beta's admin only
# (app/main.py page_app admin_only) and its data from /api/v1/admin/* (app/admin.py). The build output is not kept in git.
FROM node:22-slim AS admin
WORKDIR /build/admin
COPY admin/package.json admin/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY shared /build/shared
# 3f round 2: every page build applies the release filter (shared/release-filter.mjs), which stops without this file
COPY catalog/releases.json /build/catalog/releases.json
COPY admin/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
# Railway accepts cache mounts only; use the image's trusted CA roots for verified package downloads.
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# EXEC-MU-ACCOUNTS Phase 2 (CONTRACT.md 8a): the release stage of every catalog item, read by app/releases.py at start
COPY catalog ./catalog
# EXEC-MU-ACCOUNTS re-check R1-35 (user 2026-11-19, "1a"): the Screener catalog, at its repository place beside app/, whose
# universe entries naming their row field are allowed to every principal (app/catalog.py shown_attributes, read at start)
COPY screener/src/core/screener-metrics.json ./screener/src/core/screener-metrics.json
COPY static ./static
COPY --from=terminal /build/static/terminal-app ./static/terminal-app
COPY --from=terminal /build/static/terminal-app-lab ./static/terminal-app-lab
COPY --from=backtest /build/backtest/dist ./static/backtest-app
COPY --from=backtest /build/backtest/dist-lab ./static/backtest-app-lab
COPY --from=screener /build/screener/dist ./static/screener-app
COPY --from=radar /build/radar/dist ./static/radar-app
COPY --from=overview /build/overview/dist ./static/overview-app
COPY --from=sector /build/sector/dist ./static/sector-app
COPY --from=watchlist /build/watchlist/dist ./static/watchlist-app
COPY --from=admin /build/admin/dist ./static/admin-app
RUN useradd --uid 10001 --create-home edge && chmod -R a+rX /app/app /app/catalog /app/screener /app/static
USER edge
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
