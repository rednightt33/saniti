# EXEC-TERMINAL-API T5: the terminal page (terminal/, TypeScript + Vite) is built here and copied into static/terminal-app;
# the build output is not kept in git.
FROM node:22-slim AS terminal
WORKDIR /build/terminal
COPY terminal/package.json terminal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY terminal/ ./
RUN npm run build

# EDGE backtest (CONTRACT.md section 10): the backtest page (backtest/, TypeScript + Vite) is built here into its dist/
# and copied into static/backtest-app; its shared core imports the Terminal's calculation module and indicator registry
# (terminal/src), so that source sits beside it as in the repository. The build output is not kept in git.
FROM node:22-slim AS backtest
WORKDIR /build/backtest
COPY backtest/package.json backtest/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY terminal/src /build/terminal/src
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
COPY screener/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
# Railway accepts cache mounts only; use the image's trusted CA roots for verified package downloads.
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
COPY --from=terminal /build/static/terminal-app ./static/terminal-app
COPY --from=backtest /build/backtest/dist ./static/backtest-app
COPY --from=screener /build/screener/dist ./static/screener-app
RUN useradd --uid 10001 --create-home edge && chmod -R a+rX /app/app /app/static
USER edge
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
