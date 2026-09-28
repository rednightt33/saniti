FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]==3.2.10"
COPY . ./
USER 65532:65532
CMD ["python", "run.py"]
