FROM python:3.12-slim
WORKDIR /job
RUN pip install --no-cache-dir "psycopg[binary]==3.2.3" "pandas==2.2.3" "numpy==2.1.3"
COPY job.py check_feature_06_sample.py ./
COPY sql/ ./sql/
CMD ["python", "-u", "job.py"]
