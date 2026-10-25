# EXEC-TERMINAL-API T5: the terminal page (terminal/, TypeScript + Vite) is built here and copied into static/terminal-app;
# the build output is not kept in git.
FROM node:22-slim AS terminal
WORKDIR /build/terminal
COPY terminal/package.json terminal/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY terminal/ ./
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
RUN useradd --uid 10001 --create-home edge && chmod -R a+rX /app/app /app/static
USER edge
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers"]
