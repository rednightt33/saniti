FROM python:3.12-slim
WORKDIR /job
RUN pip install --no-cache-dir "psycopg[binary]==3.2.3"
COPY job.py ./
COPY sql/ ./sql/
CMD ["python", "-u", "job.py"]
