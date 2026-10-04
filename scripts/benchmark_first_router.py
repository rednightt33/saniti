"""Benchmark the first-message router with the instructions and schema in the code (AGENTS.md, AI router rule: re-run
after any change to the routing criteria, before deploying).

Reads apps/market-ai-orc/tests/fixtures/first_message_router_cases.json, sends each message twice with the same call the
orchestrator makes (AI_MODEL, reasoning low, strict JSON schema, no tools) and prints, per set: correct routes, data
questions routed to CHAT or FACT (the costliest error), non-data messages routed to a data route, unstable answers,
cost and median seconds. Needs OPENROUTER_API_KEY (for example `railway run --service market-ai-orc --environment dev
-- python3 scripts/benchmark_first_router.py`); prints no key or other secret.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
from app import conversation_router as router  # noqa: E402

MODEL = os.environ.get("AI_MODEL", "deepseek/deepseek-v4.1-flash")
REPEATS = 2


def route(message: str) -> tuple[str | None, float, float]:
    body = {"model": MODEL, "instructions": router.FIRST_INSTRUCTIONS,
            "input": [{"role": "user", "content": message[:4000]}], "reasoning": {"effort": "low"},
            "max_output_tokens": 2000, "store": False,
            "text": {"format": {"type": "json_schema", "name": "first_message_route", "strict": True,
                                "schema": router.FIRST_SCHEMA}}}
    request = urllib.request.Request("https://openrouter.ai/api/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                              "Content-Type": "application/json"})
    started = time.time()
    try:
        data = json.load(urllib.request.urlopen(request, timeout=120))
        text = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                       for c in item.get("content") or [])
        parsed = router.FirstRoute.model_validate_json(text.strip() or "{}")
        return parsed.route, float((data.get("usage") or {}).get("cost") or 0), time.time() - started
    except Exception:  # noqa: BLE001 - counted as a failed call (the backend's fallback)
        return None, 0.0, time.time() - started


def main() -> None:
    cases = json.loads((ROOT / "apps/market-ai-orc/tests/fixtures/first_message_router_cases.json").read_text())
    data_routes = set(router.DATA_ROUTES)
    for name in ("development", "heldout"):
        items = cases[name]
        with cf.ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda job: route(job[0]["message"]),
                                    [(item, n) for item in items for n in range(REPEATS)]))
        rows = [(items[i // REPEATS], results[i]) for i in range(len(results))]
        correct = sum(1 for item, (got, _, _) in rows if got in item["routes"])
        costly = [item["message"][:50] for item, (got, _, _) in rows
                  if set(item["routes"]) <= data_routes and got in ("CHAT", "FACT")]
        waste = [item["message"][:50] for item, (got, _, _) in rows
                 if set(item["routes"]) <= {"CHAT", "FACT"} and got in data_routes]
        unstable = sum(1 for i in range(0, len(results), REPEATS) if len({r[0] for r in results[i:i + REPEATS]}) > 1)
        failed = sum(1 for _, (got, _, _) in rows if got is None)
        seconds = sorted(s for _, (_, _, s) in rows)
        print(f"{name}: correct {correct}/{len(rows)}, data->CHAT/FACT {len(costly)}, non-data->data {len(waste)}, "
              f"unstable {unstable}/{len(items)}, failed calls {failed}, cost {sum(c for _, (_, c, _) in rows):.5f}, "
              f"median_s {seconds[len(seconds) // 2]:.1f}")
        for item, (got, _, _) in rows:
            if got not in item["routes"]:
                print(f"   wrong: {item['message'][:70]!r} -> {got} (expected {'/'.join(item['routes'])})")


if __name__ == "__main__":
    main()
