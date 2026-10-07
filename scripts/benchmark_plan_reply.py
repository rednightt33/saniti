"""Benchmark the plan-reply reader (research_plan.CLASSIFIER_INSTRUCTIONS) with the instructions and schema in the code,
on apps/market-ai-orc/tests/fixtures/plan_reply_cases.json (each reply with the plan digest it answers and the accepted
actions), twice per case. EXEC-D P-c (user decision 2026-10-07): CANCEL only for a clear refusal; an unclear reply or a
question is UNRELATED, which asks the user. Prints correct answers, the costly errors (APPROVE for a reply that does not
approve, CANCEL for an unclear reply or a question), clear cancels read as CANCEL, unstable answers, failed calls and
cost. With --ask-back (AI_ENABLE_ASK_BACK, as on dev): the reading rule and schema of that switch (P3b). Needs
OPENROUTER_API_KEY (e.g. `railway run --service market-ai-orc --environment dev -- <venv python>
scripts/benchmark_plan_reply.py --ask-back`); prints no secret. Exit code 1 when the pass criteria fail."""
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
from app.research_plan import CLASSIFIER_INSTRUCTIONS, CLASSIFIER_SCHEMA  # noqa: E402

MODEL = os.environ.get("AI_MODEL", "deepseek/deepseek-v4.1-flash")
FIXTURE = ROOT / "apps/market-ai-orc/tests/fixtures/plan_reply_cases.json"
ASK_BACK = False  # --ask-back


def classify(job: tuple[dict, dict]) -> tuple[str | None, float]:
    case, plans = job
    body = {"model": MODEL, "instructions": CLASSIFIER_INSTRUCTIONS + (router.REPLY_READING_RULE if ASK_BACK else ""),
            "input": [{"role": "user", "content": dumps({"research_plan": plans[case["plan"]],
                                                          "user_reply": case["message"][:4000]})}],
            "reasoning": {"effort": "low"}, "max_output_tokens": router.router_max_output_tokens(ASK_BACK),
            "store": False,
            "text": {"format": {"type": "json_schema", "name": "research_plan_reply", "strict": True,
                                "schema": router.reply_schema(CLASSIFIER_SCHEMA) if ASK_BACK else CLASSIFIER_SCHEMA}}}
    request = urllib.request.Request("https://openrouter.ai/api/v1/responses", data=json.dumps(body).encode(),
                                     headers={"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
                                              "Content-Type": "application/json"})
    try:
        data = json.load(urllib.request.urlopen(request, timeout=120))
        text = "".join(c.get("text", "") for item in data.get("output", []) if item.get("type") == "message"
                       for c in item.get("content", []))
        cost = float((data.get("usage") or {}).get("cost") or 0)
        return json.loads(text).get("action"), cost
    except Exception as exc:  # a failed call is counted, never retried
        print(f"   failed: {case['message'][:50]!r}: {type(exc).__name__}")
        return None, 0.0


def main() -> None:
    global ASK_BACK
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask-back", action="store_true", help="the reading rule and schema of AI_ENABLE_ASK_BACK")
    ASK_BACK = parser.parse_args().ask_back
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cases, plans = fixture["cases"], fixture["plans"]
    with cf.ThreadPoolExecutor(8) as pool:
        results = list(pool.map(classify, [(c, plans) for c in cases for _ in range(2)]))
    rows = [(cases[i // 2], results[i]) for i in range(len(results))]
    correct = sum(1 for case, (action, _) in rows if action in case["actions"])
    wrong_approve = [case["message"] for case, (action, _) in rows
                     if action == "APPROVE" and "APPROVE" not in case["actions"]]
    wrong_cancel = [case["message"] for case, (action, _) in rows
                    if action == "CANCEL" and case["kind"] in ("unclear", "question")]
    cancels = [action for case, (action, _) in rows if case["kind"] == "cancel"]
    cancel_rate = sum(a == "CANCEL" for a in cancels) / len(cancels) if cancels else 1.0
    failed = sum(1 for _, (action, _) in rows if action is None)
    unstable = sum(1 for i in range(0, len(results), 2) if results[i][0] != results[i + 1][0])
    print(f"correct {correct}/{len(rows)}, APPROVE for a non-approval {len(wrong_approve)}, CANCEL for an unclear "
          f"reply or a question {len(wrong_cancel)}, clear cancels read as CANCEL {cancel_rate:.0%}, failed {failed}, "
          f"unstable {unstable}/{len(cases)}, cost {sum(c for _, (_, c) in rows):.5f}")
    for case, (action, _) in rows:
        if action not in case["actions"]:
            print(f"   wrong: {case['message'][:60]!r} -> {action} (expected {'/'.join(case['actions'])})")
    passed = not wrong_approve and not wrong_cancel and cancel_rate >= 0.9 and failed == 0
    print("PASS" if passed else "FAIL")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
