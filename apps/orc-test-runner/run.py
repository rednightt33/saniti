"""Multi-Angle Research golden questions against market-ai-orc on the private network (orc-test-runner).

MARKET_AI_ORC_API_KEY is read from the environment and never printed. Every item is a new SERVER-mode conversation;
a RESEARCH_PLAN_CONFIRMATION is approved once with plan_reply APPROVE. Output: short `OTR {json}` lines per turn and
the full responses as gzip+base64 chunks (`OTRDUMP i/n data`), because Railway drops long log lines."""
import base64, gzip, json, os, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://market-ai-orc.railway.internal:8080"
KEY = os.environ["MARKET_AI_ORC_API_KEY"]
HERE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()


def log(event, **fields):
    with LOCK:
        print("OTR " + json.dumps({"event": event, **fields}, ensure_ascii=False)[:3500], flush=True)


def post(body):
    request = urllib.request.Request(BASE + "/v1/agent/run", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json",
                                              "X-Saniti-Owner": "golden-multi-angle"})
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=2400) as response:
            return response.status, json.loads(response.read()), time.time() - started
    except urllib.error.HTTPError as error:
        return error.code, {"http_error": error.read().decode()[:2000]}, time.time() - started
    except Exception as error:  # noqa: BLE001
        return 0, {"client_error": f"{type(error).__name__}: {error}"[:500]}, time.time() - started


def summary(item_id, turn, code, body, seconds):
    response = body.get("response") or {}
    execution = body.get("execution") or {}
    plan = response.get("research_plan") or {}
    plan_exec = execution.get("research_plan") or {}
    final = execution.get("analysis_final_status") or {}
    findings = response.get("research_findings") or []
    experiments = (execution.get("research") or {}).get("experiments") or []
    return {"item": item_id, "turn": turn, "http": code, "seconds": round(seconds, 1), "status": body.get("status"),
            "response_type": response.get("response_type"), "error": body.get("error") or body.get("http_error")
            or body.get("client_error"),
            "plan_version": plan.get("plan_version") or plan_exec.get("plan_version"),
            "angles": [(a.get("angle_id"), a.get("method_id")) for a in plan.get("angles") or []],
            "plan_turn": plan_exec.get("turn"), "research_submitted": plan_exec.get("research_submitted"),
            "research_run_id": plan_exec.get("research_run_id"),
            "run_status": final.get("status"), "calculation_validation": final.get("calculation_validation"),
            "angle_completion": final.get("angle_completion"),
            "angle_status": [(e.get("angle_id"), e.get("status"), e.get("status_reason"), e.get("validation_level"),
                              e.get("bundle_group_id")) for e in experiments if e.get("payload_version")],
            "reported": [(f.get("angle_id") or f.get("hypothesis_id"), f.get("status") or f.get("verdict"))
                         for f in findings],
            "validation_gate": execution.get("validation_gate"), "evidence_label": body.get("evidence_label"),
            "tool_calls": execution.get("tool_call_count"), "iterations": execution.get("iterations"),
            "cost": execution.get("cost"), "unsupported": (execution.get("number_provenance") or {}).get("unsupported"),
            "limitations": (response.get("limitations") or [])[:6]}


def run_item(item, prefix, results):
    base = {"message": item["message"], "history_mode": "SERVER"}
    if item.get("analysis_path"):
        base["analysis_path"] = item["analysis_path"]
    code, body, seconds = post({**base, "request_id": f"{prefix}-{item['id']}-1"})
    log("turn", **summary(item["id"], 1, code, body, seconds))
    results.append({"item": item["id"], "turn": 1, "body": body})
    conversation = (body.get("conversation") or {}).get("conversation_id")
    if body.get("status") == "AWAITING_CONFIRMATION" and conversation:
        plan_id = (body.get("continuation") or {}).get("plan_id")
        reply = {"request_id": f"{prefix}-{item['id']}-2", "conversation_id": conversation, "history_mode": "SERVER",
                 "message": "Setuju, jalankan rencana ini.", "plan_reply": {"plan_id": plan_id, "action": "APPROVE"}}
        code, body, seconds = post(reply)
        log("turn", **summary(item["id"], 2, code, body, seconds))
        results.append({"item": item["id"], "turn": 2, "body": body})


def main():
    with open(os.path.join(HERE, "suite.json")) as handle:
        suite = json.load(handle)
    log("start", items=len(suite["items"]), prefix=suite["prefix"], workers=suite.get("workers", 2))
    results = []
    with ThreadPoolExecutor(max_workers=suite.get("workers", 2)) as pool:
        for future in [pool.submit(run_item, item, suite["prefix"], results) for item in suite["items"]]:
            future.result()
    blob = base64.b64encode(gzip.compress(json.dumps(results, ensure_ascii=False).encode())).decode()
    parts = [blob[i:i + 800] for i in range(0, len(blob), 800)]
    for index, part in enumerate(parts, start=1):
        print(f"OTRDUMP {index}/{len(parts)} {part}", flush=True)
        if index % 50 == 0:
            time.sleep(1)
    log("done", turns=len(results))
    time.sleep(30)


if __name__ == "__main__":
    main()
