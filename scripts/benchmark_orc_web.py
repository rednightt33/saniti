"""Labelled benchmark of market-web-governor POST /v1/orc/web (PLAN_2026-10-05.md item 12).

The route has no public domain, so the benchmark runs on the private network through web-governor-test-runner
(phase `orc_web`, apps/web-governor-test-runner/run.py). This script prepares that run and scores its output:

    python scripts/benchmark_orc_web.py plan --prefix orcweb-bench-20261005a- [--only q7_exports,bakrie_banks]
        writes apps/web-governor-test-runner/plan.json from apps/market-web-governor/tests/fixtures/orc_web_cases.json
    railway up apps/web-governor-test-runner --path-as-root --service web-governor-test-runner
    railway logs <deployment> > runner.log
    python scripts/benchmark_orc_web.py score runner.log
        reassembles the WGTDUMP chunks and prints each case, its label checks, time and cost

The values themselves are compared with each case's `expected` by the reader; the labels check the form (depth,
shapes, items, periods, conflicts, official sources, subjects answered).
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "apps/market-web-governor/tests/fixtures/orc_web_cases.json"
PLAN = ROOT / "apps/web-governor-test-runner/plan.json"


def write_plan(prefix: str, only: list[str], workers: int, repeat_cached: int) -> None:
    if not re.fullmatch(r"[a-z0-9-]{4,60}", prefix):
        raise SystemExit("prefix: 4 to 60 lowercase letters, digits or hyphens")
    cases = json.loads(CASES.read_text())["cases"]
    if only:
        unknown = set(only) - {case["id"] for case in cases}
        if unknown:
            raise SystemExit(f"unknown case ids: {sorted(unknown)}")
        cases = [case for case in cases if case["id"] in only]
    plan = {"phase": "orc_web", "prefix": prefix, "workers": workers, "repeat_cached": repeat_cached,
            "cases": cases}
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n")
    print(f"{PLAN.relative_to(ROOT)}: {len(cases)} cases, prefix {prefix}")


def read_dump(log: str) -> list[dict]:
    chunks: dict[int, str] = {}
    total = 0
    for match in re.finditer(r"WGTDUMP (\d+)/(\d+) (\S+)", log):
        chunks[int(match.group(1))] = match.group(3)
        total = int(match.group(2))
    if not total or len(chunks) != total:
        raise SystemExit(f"dump incomplete: {len(chunks)} of {total} chunks")
    blob = "".join(chunks[i] for i in range(1, total + 1))
    return json.loads(gzip.decompress(base64.b64decode(blob)))


def score(path: str) -> None:
    results = [r for r in read_dump(Path(path).read_text(errors="replace")) if r.get("test") == "orc_web"]
    totals: dict[str, list[int]] = {}
    cost = 0.0
    print(f"{'case':<26} {'status':<17} {'depth':<9} {'items':>5} {'sec':>6} {'usd':>7}  checks")
    for result in results:
        body = result.get("body") or {}
        checks = result.get("checks") or {}
        for name, passed in checks.items():
            totals.setdefault(name, [0, 0])
            totals[name][0] += bool(passed)
            totals[name][1] += 1
        cost += float(body.get("cost_usd") or 0)
        failed = [name for name, passed in checks.items() if not passed]
        print(f"{result['request_id'][-26:]:<26} {str(body.get('status')):<17} {str(body.get('depth')):<9} "
              f"{len(body.get('citable') or []):>5} {result.get('seconds') or 0:>6.1f} "
              f"{float(body.get('cost_usd') or 0):>7.4f}  {'ok' if not failed else 'FAIL ' + ','.join(failed)}")
    print()
    for name, (passed, count) in totals.items():
        print(f"{name:<18} {passed}/{count}")
    print(f"total cost USD {cost:.4f}; cases {len(results)}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--prefix", required=True)
    plan.add_argument("--only", default="")
    plan.add_argument("--workers", type=int, default=4)
    plan.add_argument("--repeat-cached", type=int, default=2)
    scored = sub.add_parser("score")
    scored.add_argument("log")
    args = parser.parse_args(argv)
    if args.command == "plan":
        write_plan(args.prefix, [c for c in args.only.split(",") if c], args.workers, args.repeat_cached)
    else:
        score(args.log)


if __name__ == "__main__":
    main(sys.argv[1:])
