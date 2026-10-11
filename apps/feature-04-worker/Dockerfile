FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/feature-04-worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY features/feature04/engine.py features/feature04/swing.py ./features/feature04/
COPY apps/feature-04-worker/worker.py ./worker.py
CMD ["python", "worker.py"]
