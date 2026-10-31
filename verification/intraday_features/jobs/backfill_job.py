"""EXEC-INTRADAY-FEATURES S3: backfill Feature 01 and Feature 04 of every intraday stock series (orc-test-runner,
scripts/onboarding/run_job.sh; extras: apps/idx-price-cron/intraday_features.py, features/feature04, requirements.txt).

params.json: {"timeframes": ["4h", "1h", "15m", "5m"], "tickers": [] (all), "workers": 0 (= os.cpu_count())}
Prints the module's JSON events as OUT lines, then a VERDICT and JOB_DONE. No secret is printed.
"""
import json
import os

import intraday_features as f

P = json.load(open("params.json"))


def main():
    workers = P.get("workers") or os.cpu_count() or 2
    print("OUT " + json.dumps({"event": "job_started", "cpu": os.cpu_count(), "workers": workers, **P}), flush=True)
    failures = f.backfill(os.environ["DATABASE_URL"], P["timeframes"], set(P.get("tickers") or []) or None, workers)
    print("VERDICT " + json.dumps({"failures": failures}), flush=True)


if __name__ == "__main__":
    try:
        main()
    finally:
        print("JOB_DONE", flush=True)
