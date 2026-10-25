FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --uid 10001 --create-home terminal && chmod -R a+rX /app/app
USER terminal
# Railway's edge sets X-Forwarded-For; the app reads the client from it (app/security.py client_ip).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--no-access-log", "--no-proxy-headers"]
