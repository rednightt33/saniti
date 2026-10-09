"""Benchmark the first-message router with the instructions and schema in the code (AGENTS.md, AI router rule: re-run
after any change to the routing criteria, before deploying).

Reads apps/market-ai-orc/tests/fixtures/first_message_router_cases.json, sends each message twice with the same call the
orchestrator makes (AI_MODEL, reasoning low, strict JSON schema, no tools) and prints, per set: correct routes, data
questions routed to CHAT or FACT (the costliest error), non-data messages routed to a data route, unstable answers,
cost and median seconds. With --ask-back (EXEC-3, AI_ENABLE_ASK_BACK) it sends the instructions and schema the router
uses when that switch is on, also runs the "ask_back" set and prints how many must-ask messages were asked back and
how many no-ask messages (the ask_back NEVER cases and every development and heldout message) were. Needs
OPENROUTER_API_KEY (for example `railway run --service market-ai-orc --environment dev
-- python3 scripts/benchmark_first_router.py`); prints no key or other secret.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
from app import conversation_router as router  # noqa: E402

MODEL = os.environ.get("AI_MODEL", "deepseek/deepseek-v4.1-flash")
REPEATS = 2
ASK_BACK = False  # --ask-back
# M130: the router reads today's date in the analysis timezone, as the orchestrator sends it (--today to replay a day)
TODAY = datetime.now(ZoneInfo(os.environ.get("ANALYSIS_TIMEZONE", "Asia/Jakarta"))).date()


def route(message: str) -> tuple[str | None, float, float]:
    body = {"model": MODEL, "instructions": router.first_instructions(ASK_BACK),
            "input": [{"role": "user", "content": router.dated(message[:4000], TODAY)}], "reasoning": {"effort": "low"},
            "max_output_tokens": router.router_max_output_tokens(ASK_BACK), "store": False,
            "text": {"format": {"type": "json_schema", "name": "first_message_route", "strict": True,
                                "schema": router.first_schema(ASK_BACK)}}}
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
    global ASK_BACK, TODAY
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask-back", action="store_true", help="the instructions and schema of AI_ENABLE_ASK_BACK")
    parser.add_argument("--today", help="the date the router is told (YYYY-MM-DD; default: today in Asia/Jakarta)")
    args = parser.parse_args()
    ASK_BACK = args.ask_back
    if args.today:
        TODAY = date.fromisoformat(args.today)
    cases = json.loads((ROOT / "apps/market-ai-orc/tests/fixtures/first_message_router_cases.json").read_text())
    data_routes = set(router.DATA_ROUTES)
    must = never = asked_must = asked_never = costly_total = failed_total = 0
    for name in ("development", "heldout", *(("ask_back", "time") if ASK_BACK else ())):
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
        costly_total, failed_total = costly_total + len(costly), failed_total + failed
        seconds = sorted(s for _, (_, _, s) in rows)
        print(f"{name}: correct {correct}/{len(rows)}, data->CHAT/FACT {len(costly)}, non-data->data {len(waste)}, "
              f"unstable {unstable}/{len(items)}, failed calls {failed}, cost {sum(c for _, (_, c, _) in rows):.5f}, "
              f"median_s {seconds[len(seconds) // 2]:.1f}")
        for item, (got, _, _) in rows:
            if got not in item["routes"]:
                print(f"   wrong: {item['message'][:70]!r} -> {got} (expected {'/'.join(item['routes'])})")
            if item.get("ask") == "MUST":
                must, asked_must = must + 1, asked_must + (got == router.ASK_BACK)
            elif "ASK_BACK" not in item["routes"]:
                never, asked_never = never + 1, asked_never + (got == router.ASK_BACK)
    if ASK_BACK:
        print(f"ask back: must-ask asked {asked_must}/{must} ({100 * asked_must / max(must, 1):.0f}%), "
              f"no-ask asked {asked_never}/{never}")
    # user decision 2026-10-06: the hard criteria are the costly errors; route accuracy is reported, not a gate
    hard = costly_total == 0 and failed_total == 0 and (not ASK_BACK or (asked_never == 0
                                                                          and asked_must >= 0.9 * max(must, 1)))
    print(f"hard criteria: data->CHAT/FACT {costly_total}, failed calls {failed_total}"
          + (f", must-ask {asked_must}/{must}, no-ask asked {asked_never}" if ASK_BACK else "")
          + (" -> PASS" if hard else " -> FAIL"))


if __name__ == "__main__":
    main()
