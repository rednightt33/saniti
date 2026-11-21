"""EXEC-MU-ACCOUNTS 3e, the Screener's example (ERRORS M527): prints the RUN_JOB_EXTRA_VARS of its capture, all Railway
references (never a value): terminal-api's origin and the screener-worker's proxy key, and every limit of
apps/screener-worker/src/config.ts that the screener-worker service sets (.railway/railway.ts, kept to the live project
by `railway config pull`). The capture's worker takes its keys, URL and file origin from the fake terminal and keeps no
file cache, so SCREENER_WORKER_KEY, SCREENER_FILE_ORIGIN and the cache directory are left out.
  python3 verification/edge_multiuser/example_mode/screener_vars.py      (from anywhere)"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
FAKED = {'SCREENER_WORKER_KEY', 'SCREENER_FILE_ORIGIN', 'SCREENER_CACHE_DIR', 'SCREENER_CACHE_DIR_BYTES'}

head = (ROOT / 'apps/screener-worker/src/config.ts').read_text().split('*/', 1)[0]
limits = set(re.findall(r'^\s+(SCREENER_[A-Z0-9_]+)\s', head, re.M))
railway = (ROOT / '.railway/railway.ts').read_text()
service = next(line for line in railway.splitlines() if 'SCREENER_THREADS' in line and 'SCREENER_WORKER_KEY' in line)
set_on_service = set(re.findall(r'(SCREENER_[A-Z0-9_]+):', service))
names = sorted((limits & set_on_service) - FAKED)
if not names:
    raise SystemExit('no limit of config.ts is set on the screener-worker in .railway/railway.ts')
pairs = ['TERMINAL_URL=${{screener-worker.TERMINAL_URL}}', 'TERMINAL_PROXY_KEY=${{screener-worker.TERMINAL_PROXY_KEY}}']
print(' '.join(pairs + [f'{n}=${{{{screener-worker.{n}}}}}' for n in names]))
