FROM python:3.12-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.2.10"
WORKDIR /job
COPY . /job
CMD ["python", "-u", "job.py"]
