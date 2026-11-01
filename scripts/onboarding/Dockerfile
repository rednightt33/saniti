FROM python:3.12-slim
RUN pip install --no-cache-dir "psycopg[binary]==3.2.10"
WORKDIR /job
COPY . /job
# ERRORS M322 (user go 2026-11-01): the wrapper, not the job, prints the finish marker: JOB_EXIT <exit code> after
# job.py ends, whatever the job prints. The exit code is kept, so the runner's restart policy (ON_FAILURE) is unchanged.
CMD ["sh", "-c", "python -u job.py; code=$?; echo \"JOB_EXIT $code\"; exit $code"]
