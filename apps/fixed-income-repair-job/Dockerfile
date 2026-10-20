FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/feature-04-worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt websocket-client==1.9.0
COPY features/feature04/engine.py features/feature04/swing.py features/feature04/incremental.py features/feature04/pipeline.py ./features/feature04/
COPY apps/fixed-income-price-cron/fixed_income_update.py ./apps/fixed-income-price-cron/
COPY scripts/repair_fixed_income_dates.py scripts/run_fixed_income_repair_job.py ./scripts/
COPY verification/fixed_income_session_repair/SESSION_POLICY.json ./verification/fixed_income_session_repair/
COPY database/migrations/20261013_011_verify_fixed_income_sessions.sql ./database/migrations/
CMD ["python", "scripts/run_fixed_income_repair_job.py"]
