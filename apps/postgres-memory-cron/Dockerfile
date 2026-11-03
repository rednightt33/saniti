# postgres-memory-cron (EXEC-PG-RESTART-CRON). Built from a staging folder assembled by deploy.sh: this Dockerfile,
# railway.json and scripts/restart_postgres.py. One dependency (psycopg), so the container that holds the Railway
# token runs as little third-party code as possible.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]==3.2.10"
COPY restart_postgres.py /app/restart_postgres.py
CMD ["python", "-u", "/app/restart_postgres.py", "--cron"]
