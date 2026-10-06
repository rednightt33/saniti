"""Benchmark the later-message (conversation) router with the instructions and schema in the code, on
apps/market-ai-orc/tests/fixtures/turn_router_cases.json (each message with a conversation context and the acceptable
classes), twice per case. Prints correct classes, read requests (expected CLARIFY) sent to a research class, unstable
answers and cost; for cases with "horizons" (M82), the outcome horizons read into design_value_changes (values and an
accepted action; empty values: the message states no horizon). With --ask-back (EXEC-3, AI_ENABLE_ASK_BACK): the
instructions and schema of that switch, the "variant_cases" (expect_changes: changes the reading must contain), and how
many messages were asked back (none should be). Needs OPENROUTER_API_KEY (e.g. `railway run --service market-ai-orc --environment dev --
<venv python> scripts/benchmark_turn_router.py`); prints no secret."""
from __future__ import annotations

import argparse
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
ASK_BACK = False  # --ask-back


def classify(case: dict) -> tuple[str | None, float, list[dict] | None]:
    body = {"model": MODEL, "instructions": router.router_instructions(ASK_BACK),
            "input": [{"role": "user", "content": dumps({"conversation": case["context"],
                                                          "user_message": case["message"][:4000]})}],
            "reasoning": {"effort": "low"}, "max_output_tokens": router.router_max_output_tokens(ASK_BACK), "store": False,
            "text": {"format": {"type": "json_schema", "name": "conversation_turn", "strict": True,
                                "schema": router.router_schema(ASK_BACK)}}}
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
        changes = [c.model_dump() for c in parsed.design_value_changes]
        return kind, float((data.get("usage") or {}).get("cost") or 0), changes
    except Exception:  # noqa: BLE001 - a failed call (the backend's fallback class)
        return None, 0.0, None


def horizon_ok(expected: dict, changes: list[dict] | None) -> bool:
    """The horizons read match the expected values, each with an accepted action."""
    if changes is None:
        return False
    read = [c for c in changes if c["name"] == "OUTCOME_HORIZON"]
    values = sorted((c["value"], c["unit"]) for c in read)
    return values == sorted(tuple(v) for v in expected["values"]) and all(
        c["action"] in expected["actions"] for c in read)


def changes_ok(expected: list[dict], changes: list[dict] | None) -> bool:
    """Every expected change (name, value, action) is in the reading."""
    return changes is not None and all(any(c["name"] == e["name"] and c["action"] == e["action"]
                                           and c.get("value") is not None and abs(c["value"] - e["value"]) < 1e-9
                                           for c in changes) for e in expected)


def main() -> None:
    global ASK_BACK
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask-back", action="store_true", help="the instructions and schema of AI_ENABLE_ASK_BACK")
    ASK_BACK = parser.parse_args().ask_back
    fixture = json.loads((ROOT / "apps/market-ai-orc/tests/fixtures/turn_router_cases.json").read_text())
    cases = fixture["cases"] + (fixture.get("variant_cases") or [] if ASK_BACK else [])
    with cf.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(classify, [c for c in cases for _ in range(2)]))
    rows = [(cases[i // 2], results[i]) for i in range(len(results))]
    correct = sum(1 for case, (kind, _, _) in rows if kind in case["kinds"])
    research = [case["message"][:50] for case, (kind, _, _) in rows
                if case["kinds"] == ["CLARIFY"] and kind in router.RESEARCH_KINDS]
    unstable = sum(1 for i in range(0, len(results), 2) if results[i][0] != results[i + 1][0])
    horizon_rows = [(case, changes) for case, (_, _, changes) in rows if "horizons" in case]
    horizons = sum(1 for case, changes in horizon_rows if horizon_ok(case["horizons"], changes))
    print(f"correct {correct}/{len(rows)}, read->research {len(research)}, unstable {unstable}/{len(cases)}, "
          f"horizons {horizons}/{len(horizon_rows)}, cost {sum(c for _, (_, c, _) in rows):.5f}")
    for case, changes in horizon_rows:
        if not horizon_ok(case["horizons"], changes):
            print(f"   horizon wrong: {case['message'][:60]!r} -> {changes} (expected {case['horizons']})")
    if ASK_BACK:
        variant_rows = [(case, changes) for case, (_, _, changes) in rows if "expect_changes" in case]
        print(f"asked back {sum(1 for _, (kind, _, _) in rows if kind == router.ASK_BACK)}/{len(rows)}, variant "
              f"readings {sum(1 for c, ch in variant_rows if changes_ok(c['expect_changes'], ch))}/{len(variant_rows)}")
        for case, changes in variant_rows:
            if not changes_ok(case["expect_changes"], changes):
                print(f"   variant wrong: {case['message'][:60]!r} -> {changes}")
    for case, (kind, _, _) in rows:
        if kind not in case["kinds"]:
            print(f"   wrong: {case['message'][:60]!r} pending={case['context'].get('pending_suggestion') is not None}"
                  f" -> {kind} (expected {'/'.join(case['kinds'])})")


if __name__ == "__main__":
    main()
