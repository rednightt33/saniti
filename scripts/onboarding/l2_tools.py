"""NEW_TABLE_ONBOARDING_PLAN.md validation L1/L2 (no model): run the coverage job once, then market-ai-orc's own tool
code against the live catalog as the role `market_ai_orc` (the service's privileges), and print what the AI would see.
The pattern of EXEC-ONBOARD-1 (Feature 04).

Stage with run_job.sh extras: apps/market-ai-orc/app, apps/market-ai-orc/requirements.txt and
apps/ai-data-coverage/coverage_job.py (Dockerfile.l2 is picked automatically).

params.json:
  {"coverage": true, "coverage_datasets": ["Feature_06_Foreign_Domestic"],
   "calls": [["discover_words", "discover_catalog", {"query": "net beli asing per saham"}],
             ["details", "get_catalog_details", {"table_names": ["Feature_06_Foreign_Domestic"],
                                                 "sections": ["COLUMNS", "RELATIONSHIPS", "COVERAGE"],
                                                 "column_names": null, "entity_ids": ["BBCA"]}],
             ["preview", "preview_table_rows", {"table_name": "Feature_06_Foreign_Domestic"}]]}
  coverage   run coverage_job.py --mode full first (it writes only AI_data_coverage, its normal job);
  calls      [key, tool name, arguments] as the model would send them (the user's own words for discovery).

Pass when (section 5, L2): the table is found by the user's words; COLUMNS show units and summaries and no hidden
column; COVERAGE shows the date range; a Feature formula shows stored_in; the preview returns rows.
Prints COVERAGE, `OUT <key> <part> <json>` chunks, then JOB_DONE. No secret is printed.
"""
import hashlib
import json
import os
import subprocess
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

p = json.load(open("params.json"))
if p.get("coverage"):
    done = subprocess.run([sys.executable, "coverage_job.py", "--mode", "full"], capture_output=True, text=True)
    try:
        summary = json.loads(done.stdout.strip().splitlines()[-1])
        wanted = set(p.get("coverage_datasets") or [])
        rows = [r for r in summary.get("coverage_summary", []) if not wanted or r.get("dataset_name") in wanted]
        print("COVERAGE " + json.dumps({"rc": done.returncode, "status": summary.get("status"), "rows": rows},
                                       default=str), flush=True)
    except Exception:  # noqa: BLE001
        print("COVERAGE_ERR " + json.dumps({"rc": done.returncode, "out": done.stdout[-600:],
                                            "err": done.stderr[-800:]}), flush=True)

from app.catalog_store import CatalogStore  # noqa: E402 - the staged orc app
from app.tools import build_default_registry  # noqa: E402

parts = urlsplit(os.environ["DATABASE_URL"])
query = dict(parse_qsl(parts.query))
query["options"] = "-c role=market_ai_orc"
url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
store = CatalogStore(url, connect_timeout_seconds=10, statement_timeout_ms=15000)
registry = build_default_registry(store, cursor_secret=hashlib.sha256(b"onboarding-l2").digest(),
                                  catalog_discovery_v2=True)
for key, name, arguments in p["calls"]:
    outcome = registry.execute("onboarding-l2", name, json.dumps(arguments))
    text = json.dumps({"q": key, "ok": outcome.ok, "output": outcome.output}, default=str, ensure_ascii=False)
    for i in range(0, len(text), 3500):
        print(f"OUT {key} {i // 3500} {text[i:i + 3500]}", flush=True)
print("JOB_DONE L2", flush=True)
