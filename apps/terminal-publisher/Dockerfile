FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY publisher.py .
RUN useradd --uid 10001 --create-home publisher && chmod a+r /app/publisher.py
USER publisher
CMD ["python", "publisher.py"]
