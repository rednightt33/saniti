FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# every module, so a script a start command names cannot be left out of the image (M318: a cron deploy reaches
# SUCCESS without running its start command, so a missing file would surface only at the first scheduled run)
COPY *.py ./
# the build fails when a module is missing or does not import (tests excluded); imports need no variables
RUN for f in *.py; do case "$f" in test_*) ;; *) python -c "import ${f%.py}" || exit 1;; esac; done

CMD ["python", "price_update.py", "--mode", "auto"]
