FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY coverage_job.py .

CMD ["python", "coverage_job.py", "--mode", "nightly"]
