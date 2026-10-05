"""Benchmark the later-message (conversation) router with the instructions and schema in the code, on
apps/market-ai-orc/tests/fixtures/turn_router_cases.json (each message with a conversation context and the acceptable
classes), twice per case. Prints correct classes, read requests (expected CLARIFY) sent to a research class, unstable
answers and cost. Needs OPENROUTER_API_KEY (e.g. `railway run --service market-ai-orc --environment dev --
<venv python> scripts/benchmark_turn_router.py`); prints no secret."""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/market-ai-orc"))
from app import conversation_router as router  # noqa: E402
from app.compaction import dumps  # noqa: E402

MODEL = os.environ.get("AI_MODEL", "deepseek/deepseek-v4.1-flash")


def classify(case: dict) -> tuple[str | None, float]:
    body = {"model": MODEL, "instructions": router.ROUTER_INSTRUCTIONS,
            "input": [{"role": "user", "content": dumps({"conversation": case["context"],
                                                          "user_message": case["message"][:4000]})}],
            "reasoning": {"effort": "low"}, "max_output_tokens": 2000, "store": False,
            "text": {"format": {"type": "json_schema", "name": "conversation_turn", "strict": True,
                                "schema": router.ROUTER_SCHEMA}}}
    request = urllib.request.Request("https://openrouter.ai/api/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                              "Content-Type": "application/json"})
    try:
        data = json.load(urllib.request.urlopen(request, timeout=120))
        text = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                       for c in item.get("content") or [])
        parsed = router.TurnClassification.model_validate_json(text.strip() or "{}")
        pending = case["context"].get("pending_suggestion") is not None
        kind = router.apply_rules(parsed.turn_kind, pending, case["context"].get("results_after_pending_suggestion"),
                                  parsed.referent)
        return kind, float((data.get("usage") or {}).get("cost") or 0)
    except Exception:  # noqa: BLE001 - a failed call (the backend's fallback class)
        return None, 0.0


def main() -> None:
    cases = json.loads((ROOT / "apps/market-ai-orc/tests/fixtures/turn_router_cases.json").read_text())["cases"]
    with cf.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(classify, [c for c in cases for _ in range(2)]))
    rows = [(cases[i // 2], results[i]) for i in range(len(results))]
    correct = sum(1 for case, (kind, _) in rows if kind in case["kinds"])
    research = [case["message"][:50] for case, (kind, _) in rows
                if case["kinds"] == ["CLARIFY"] and kind in router.RESEARCH_KINDS]
    unstable = sum(1 for i in range(0, len(results), 2) if results[i][0] != results[i + 1][0])
    print(f"correct {correct}/{len(rows)}, read->research {len(research)}, unstable {unstable}/{len(cases)}, "
          f"cost {sum(c for _, (_, c) in rows):.5f}")
    for case, (kind, _) in rows:
        if kind not in case["kinds"]:
            print(f"   wrong: {case['message'][:60]!r} pending={case['context'].get('pending_suggestion') is not None}"
                  f" -> {kind} (expected {'/'.join(case['kinds'])})")


if __name__ == "__main__":
    main()
