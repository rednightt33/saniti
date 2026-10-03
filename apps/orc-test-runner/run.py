"""Multi-Angle Research golden questions against market-ai-orc on the private network (orc-test-runner).

MARKET_AI_ORC_API_KEY is read from the environment and never printed. Every item is a new SERVER-mode conversation;
a RESEARCH_PLAN_CONFIRMATION is approved once with plan_reply APPROVE. An item with "turns" is one conversation of
free-text messages instead (mode 4: no analysis_path, no plan_reply; the reply classifier reads each reply). Output: a short `OTR {json}` line per turn, then
that turn's full response as gzip+base64 chunks (`OTRDUMP <item>:<turn> i/n data`), because Railway drops long log
lines."""
import base64, gzip, json, os, re, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://market-ai-orc.railway.internal:8080"
KEY = os.environ["MARKET_AI_ORC_API_KEY"]
AUDIT = "http://market-audit-store.railway.internal:8080"
READER = os.environ.get("AUDIT_STORE_READER_KEY")
AUDIT_KINDS = ("final.rejected", "final.forced", "final.unrendered")
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
        with urllib.request.urlopen(request, timeout=3900) as response:
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
            "limitations": (response.get("limitations") or [])[:6],
            "mode": execution.get("mode"),
            # round 2026-10-03: the kejedot index, checked claims, exports and their download check
            "friction": execution.get("friction"),
            "evidence": [(e.get("status"), e.get("kind")) for e in body.get("evidence") or []] or None,
            "artifacts": [(a.get("file_name"), a.get("size_bytes"), download_check(a)) for a in body.get("artifacts")
                          or []] or None,
            "data_as_of": (body.get("data_record") or {}).get("answers", [{}])[-1].get("data_as_of")
            if (body.get("data_record") or {}).get("answers") else None,
            "mode4": [(s.get("step"), s.get("status"), s.get("turn"), s.get("angles"), s.get("cost"),
                       s.get("duration_ms")) for s in (body.get("mode4") or {}).get("steps") or []] or None}


def download_check(artifact):
    """D4: the export downloads for its owner with the sha256 it was listed with, and not for another owner."""
    import hashlib

    def get(owner):
        request = urllib.request.Request(BASE + artifact["download_path"], headers={
            "Authorization": f"Bearer {KEY}", "X-Saniti-Owner": owner})
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, b""
        except Exception:  # noqa: BLE001
            return 0, b""

    code, data = get("golden-multi-angle")
    other, _ = get("someone-else")
    return {"http": code, "sha_ok": hashlib.sha256(data).hexdigest() == artifact.get("sha256"),
            "xlsx": data[:2] == b"PK", "other_owner_http": other}


def dump(tag, payload):
    """One turn's full response as gzip+base64 chunks, printed as soon as the turn ends so a crash later loses
    nothing: `OTRDUMP <tag> i/n data`."""
    blob = base64.b64encode(gzip.compress(json.dumps(payload, ensure_ascii=False).encode())).decode()
    parts = [blob[i:i + 800] for i in range(0, len(blob), 800)]
    with LOCK:
        for index, part in enumerate(parts, start=1):
            print(f"OTRDUMP {tag} {index}/{len(parts)} {part}", flush=True)
            if index % 50 == 0:
                time.sleep(1)


def run_turns(item, prefix, results):
    """Mode 4: the item's messages in one SERVER conversation, each sent as plain text."""
    conversation = None
    turn = 0
    for message in item["turns"]:
        if isinstance(message, dict) and message.get("wait_seconds"):
            # round 2026-10-03 GT: let the sandbox copies (1-hour retention during the test) and the plan expire
            log("wait", item=item["id"], seconds=message["wait_seconds"])
            time.sleep(int(message["wait_seconds"]))
            continue
        turn += 1
        body = {"request_id": f"{prefix}-{item['id']}-{turn}", "conversation_id": conversation,
                "history_mode": "SERVER", "message": message}
        code, body, seconds = post(body)
        log("turn", **summary(item["id"], turn, code, body, seconds))
        results.append({"item": item["id"], "turn": turn, "body": body})
        dump(f"{item['id']}:{turn}", {"item": item["id"], "turn": turn, "seconds": round(seconds, 1), "body": body})
        conversation = (body.get("conversation") or {}).get("conversation_id") or conversation
        if code != 200:
            return


def run_item(item, prefix, results):
    if item.get("turns"):
        return run_turns(item, prefix, results)
    base = {"message": item["message"], "history_mode": "SERVER"}
    if item.get("analysis_path"):
        base["analysis_path"] = item["analysis_path"]
    code, body, seconds = post({**base, "request_id": f"{prefix}-{item['id']}-1"})
    log("turn", **summary(item["id"], 1, code, body, seconds))
    results.append({"item": item["id"], "turn": 1, "body": body})
    dump(f"{item['id']}:1", {"item": item["id"], "turn": 1, "seconds": round(seconds, 1), "body": body})
    conversation = (body.get("conversation") or {}).get("conversation_id")
    if body.get("status") == "AWAITING_CONFIRMATION" and conversation:
        plan_id = (body.get("continuation") or {}).get("plan_id")
        reply = {"request_id": f"{prefix}-{item['id']}-2", "conversation_id": conversation, "history_mode": "SERVER",
                 "message": "Setuju, jalankan rencana ini.", "plan_reply": {"plan_id": plan_id, "action": "APPROVE"}}
        code, body, seconds = post(reply)
        log("turn", **summary(item["id"], 2, code, body, seconds))
        results.append({"item": item["id"], "turn": 2, "body": body})
        dump(f"{item['id']}:2", {"item": item["id"], "turn": 2, "seconds": round(seconds, 1), "body": body})


def audit_call(path, body=None):
    request = urllib.request.Request(AUDIT + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {READER}", "Content-Type": "application/json",
                                              "X-Audit-Accessor": "orc-test-runner"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, {"http_error": error.read().decode()[:500]}
    except Exception as error:  # noqa: BLE001
        return 0, {"client_error": f"{type(error).__name__}: {error}"[:300]}


def audit_run(request_id, wait_seconds):
    """The audit store's view of one run, polled until COMPLETE (INCOMPLETE runs are re-evaluated when a late
    execution or artifact arrives)."""
    deadline = time.time() + wait_seconds
    while True:
        code, run = audit_call(f"/v1/requests/{request_id}/run")
        if code == 404 or (code == 200 and run.get("status") == "COMPLETE") or time.time() > deadline:
            return code, run
        time.sleep(20)


def audit_item(item_id, turn, request_id, wait_seconds, full_trace=False):
    """AUDIT_STORE_READER_KEY only: the run's status and event counts as an `OTR audit` line, then the drafts the
    gates refused (final.rejected / final.forced / final.unrendered, read in full from the TOOL_TRACE artifact) as
    `OTRDUMP audit:<item>:<turn>` chunks. full_trace: every TOOL_TRACE event (tool results included) as
    `OTRDUMP trace:<item>:<turn>` chunks."""
    code, run = audit_run(request_id, wait_seconds)
    if code == 404:
        return
    if code != 200:
        log("audit", item=item_id, turn=turn, request_id=request_id, http=code, error=run)
        return
    types, after = {}, 0
    rejected = []
    while after is not None:
        code, page = audit_call(f"/v1/runs/{run['run_id']}/events?after_seq={after}&limit=500")
        if code != 200:
            break
        for event in page["events"]:
            types[event["event_type"]] = types.get(event["event_type"], 0) + 1
            if event["event_type"] in AUDIT_KINDS[:2]:
                payload = event.get("payload") or {}
                rejected.append((event["event_type"], payload.get("stage"), payload.get("iteration"),
                                 payload.get("draft_chars"), str(payload.get("detail") or payload.get("preview"))[:300]))
        after = page.get("next_after_seq")
    log("audit", item=item_id, turn=turn, request_id=request_id, run_id=run["run_id"], status=run["status"],
        missing=run.get("missing"), counts=run.get("counts"), event_types=types, rejected=rejected)
    code, links = audit_call(f"/v1/runs/{run['run_id']}/artifacts")
    trace = [a for a in (links.get("artifacts") or []) if a.get("role") == "TOOL_TRACE"] if code == 200 else []
    if not trace:
        log("audit", item=item_id, turn=turn, error="no TOOL_TRACE artifact", http=code)
        return
    code, grant = audit_call(f"/v1/artifacts/{trace[0]['artifact_id']}/access",
                             {"purpose": "orc-test-runner: read refused final drafts", "run_id": run["run_id"]})
    if code != 200:
        log("audit", item=item_id, turn=turn, error="access refused", http=code, detail=grant)
        return
    try:
        with urllib.request.urlopen(grant["url"], timeout=120) as response:
            events = json.loads(response.read()).get("events") or []
    except Exception as error:  # noqa: BLE001
        log("audit", item=item_id, turn=turn, error=f"trace download: {type(error).__name__}")
        return
    # the timeline of the turn: every model call (latency) and tool call (duration), in order
    timeline = [{k: e.get(k) for k in ("type", "occurred_at", "iteration", "latency_ms", "tool", "duration_ms", "ok",
                                       "error_code", "stage")}
                for e in events if e.get("type") in ("model.call", "tool.call", *AUDIT_KINDS)]
    dump(f"audit:{item_id}:{turn}", {"item": item_id, "turn": turn, "run_id": run["run_id"], "timeline": timeline,
                                     "events": [e for e in events if e.get("type") in AUDIT_KINDS]})
    if full_trace:
        dump(f"trace:{item_id}:{turn}", {"item": item_id, "turn": turn, "run_id": run["run_id"], "events": events})


POSITIONAL_REF = re.compile(r"\{\{[^{}]*?out\.(out_[0-9a-f]+)\.rows(?:\[(-?\d+)\]|\.(\d+))\.([A-Za-z0-9_.]+)[^{}]*\}\}")


def trace_events(run_id):
    code, links = audit_call(f"/v1/runs/{run_id}/artifacts")
    trace = [a for a in (links.get("artifacts") or []) if a.get("role") == "TOOL_TRACE"] if code == 200 else []
    if not trace:
        return None
    code, grant = audit_call(f"/v1/artifacts/{trace[0]['artifact_id']}/access",
                             {"purpose": "orc-test-runner: M44 scan", "run_id": run_id})
    if code != 200:
        return None
    with urllib.request.urlopen(grant["url"], timeout=120) as response:
        return json.loads(response.read()).get("events") or []


def _identity(rows):
    """The first text column whose values are unique in these rows (broker, ticker, series code)."""
    for column in (rows[0] if rows else {}):
        values = [row.get(column) for row in rows if isinstance(row, dict)]
        if all(isinstance(v, str) for v in values) and len(set(values)) == len(values):
            return column
    return None


def scan_m44(request_id):
    """M44: a positional row reference ({{out.<id>.rows[i]...}}) in the final answer to an output the run read with
    get_session_output at an offset > 0 resolved against that page, not the table. One `OTR m44` line per finding:
    the referenced position, the row it really took (absolute index and identity) and the text just before it."""
    code, run = audit_call(f"/v1/requests/{request_id}/run")
    if code != 200:
        return
    events = trace_events(run["run_id"]) or []
    pages = {}
    for event in events:
        if event.get("type") == "tool.call" and event.get("tool") == "get_session_output" and event.get("ok"):
            result = (event.get("result") or {}).get("result") or {}
            if isinstance(result, dict) and result.get("output_id") and isinstance(result.get("rows"), list):
                pages[result["output_id"]] = (int(result.get("offset") or 0), result["rows"])
    finals = [e for e in events if e.get("type") == "final.unrendered"]
    response = finals[-1].get("response") if finals else None
    text = response if isinstance(response, str) else json.dumps(response or {}, ensure_ascii=False)
    refs = list(POSITIONAL_REF.finditer(text))
    hits = []
    for match in refs:
        output_id, index = match.group(1), int(match.group(2) or match.group(3))
        offset, rows = pages.get(output_id, (0, None))
        if rows is None or offset == 0:
            continue
        key = _identity(rows)
        row = rows[index] if -len(rows) <= index < len(rows) else None
        hits.append({"output": output_id[:16], "ref_row": index, "page_offset": offset,
                     "took_row": offset + index if row is not None else None,
                     "took": (row or {}).get(key) if key else None, "identity_column": key,
                     "field": match.group(4), "before": text[max(0, match.start() - 140):match.start()][-140:]})
    grouped = {}
    for hit in hits:  # one line per referenced row: its fields, and the text before its first reference
        entry = grouped.setdefault((hit["output"], hit["ref_row"]), {**hit, "fields": []})
        entry["fields"].append(hit.pop("field"))
    log("m44", request_id=request_id, positional_refs=len(refs), paged_outputs=len(pages), rows_hit=len(grouped))
    for entry in grouped.values():
        entry.pop("field", None)
        log("m44_hit", request_id=request_id, **entry)


def audit(suite):
    if suite.get("scan_m44_request_ids"):
        for request_id in suite["scan_m44_request_ids"]:
            try:
                scan_m44(request_id)
            except Exception as error:  # noqa: BLE001 - one unreadable run must not stop the scan
                log("m44", request_id=request_id, error=f"{type(error).__name__}: {error}"[:300])
        return
    if suite.get("audit_request_ids"):
        # explicit request ids, e.g. the sub-runs of a mode 4 turn (<request_id>-m4a), which the item/turn naming
        # below cannot reach
        for request_id in suite["audit_request_ids"]:
            audit_item(request_id, 0, request_id, suite.get("audit_wait_seconds", 300), suite.get("audit_full_trace"))
        return
    prefix = suite["prefix"]
    for item in suite["items"]:
        for turn in (1, 2):
            audit_item(item["id"], turn, f"{prefix}-{item['id']}-{turn}", suite.get("audit_wait_seconds", 300))


def main():
    with open(os.path.join(HERE, "suite.json")) as handle:
        suite = json.load(handle)
    log("start", items=len(suite["items"]), prefix=suite["prefix"], workers=suite.get("workers", 2),
        audit=bool(READER), audit_only=bool(suite.get("audit_only")))
    results = []
    if not suite.get("audit_only"):
        with ThreadPoolExecutor(max_workers=suite.get("workers", 2)) as pool:
            for future in [pool.submit(run_item, item, suite["prefix"], results) for item in suite["items"]]:
                future.result()
        log("done", turns=len(results))
    if READER:
        time.sleep(60)  # the outbox consumer and the producers' spools post on their own intervals
        audit(suite)
        log("audit_done")
    time.sleep(30)


if __name__ == "__main__":
    main()
