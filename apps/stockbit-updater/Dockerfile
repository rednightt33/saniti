# Built from a staging folder assembled by deploy.sh (the repository files the round needs), not from the repo root.
FROM python:3.12-slim
WORKDIR /app
COPY updater/requirements.txt /app/updater/requirements.txt
RUN pip install --no-cache-dir -r /app/updater/requirements.txt
COPY . /app
CMD ["python", "-u", "/app/updater/updater.py"]
