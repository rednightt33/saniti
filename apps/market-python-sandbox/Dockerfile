ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1

# One dedicated non-root user per concurrent analysis slot (PY_SANDBOX_SLOT_UID_BASE + slot).
RUN for i in 1 2 3 4; do \
      groupadd --system --gid "2000$i" "sandbox$i" && \
      useradd --system --uid "2000$i" --gid "2000$i" --no-create-home --home-dir /nonexistent \
              --shell /usr/sbin/nologin "sandbox$i"; \
    done

WORKDIR /app
COPY requirements.txt requirements-analysis.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-analysis.txt \
 && MPLCONFIGDIR=/opt/mplcache python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot" \
 && python -m pip uninstall -y pip \
 && rm -rf /root/.cache

COPY app ./app
COPY runtime ./runtime
# Harness code is root-only; runtime code is world-readable; shared temp directories are not
# writable by analysis users (each analysis gets its own private TMPDIR).
RUN chmod -R go-rwx /app/app \
 && chmod 0755 /app /app/runtime && chmod 0644 /app/runtime/*.py \
 && chmod -R a+rX /opt/mplcache \
 && chmod 0755 /tmp /var/tmp

# The service runs as root only so it can start each analysis as a separate non-root user.
# It holds two service keys and no database or bucket credential.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
