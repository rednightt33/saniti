"""Live test harness for market-web-governor, run on the private network by web-governor-test-runner.

The service key is read from WEB_GOVERNOR_API_KEY and is never printed. Results go to stdout as short
`WGT` lines plus the full result document as gzip+base64 chunks (`WGTDUMP <i>/<n> <data>`), because Railway drops
long log lines. `plan.json` (uploaded next to this file) selects the phase and the request-ID prefix.
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("WEB_GOVERNOR_URL", "http://market-web-governor.railway.internal:8080").rstrip("/")
KEY = os.environ.get("WEB_GOVERNOR_API_KEY", "")
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS: list[dict] = []


def log(kind: str, **fields) -> None:
    line = json.dumps({"k": kind, **fields}, ensure_ascii=False, separators=(",", ":"))
    for start in range(0, len(line), 900):
        print(f"WGT {line[start:start + 900]}", flush=True)


def call(method: str, path: str, body: dict | None = None, auth: str | None = "valid", timeout: int = 900):
    headers = {"Content-Type": "application/json"}
    if auth == "valid":
        headers["Authorization"] = f"Bearer {KEY}"
    elif auth == "invalid":
        headers["Authorization"] = f"Bearer {secrets.token_hex(32)}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    except (urllib.error.URLError, socket.timeout, TimeoutError) as exc:
        return {"http": None, "error": type(exc).__name__, "seconds": round(time.monotonic() - started, 2), "body": None}
    try:
        parsed = json.loads(raw) if raw else None
    except ValueError:
        parsed = {"non_json_length": len(raw)}
    return {"http": status, "seconds": round(time.monotonic() - started, 2), "body": parsed}


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def record(test: str, endpoint: str, request_id: str | None, result: dict, note: str = "") -> dict:
    body = result.get("body") if isinstance(result.get("body"), dict) else {}
    execution = body.get("execution") or {}
    entry = {
        "test": test, "endpoint": endpoint, "request_id": request_id, "http": result.get("http"),
        "seconds": result.get("seconds"), "status": body.get("status") or body.get("code"),
        "evidence": len(body.get("evidence") or []),
        "citations": len({e.get("citation_id") for e in body.get("evidence") or []}),
        "coverage": [(c.get("criterion_id"), c.get("status"), c.get("assessment")) for c in body.get("coverage") or []],
        "provider_calls": execution.get("provider_call_count"), "next_action": body.get("next_action"),
        "body_sha256": digest(body) if body else None, "note": note,
    }
    log("result", **entry)
    RESULTS.append({**entry, "response": result.get("body")})
    return result


def wait_ready() -> None:
    for attempt in range(30):
        result = call("GET", "/health", auth=None, timeout=10)
        if result["http"] == 200:
            return
        log("wait", attempt=attempt, http=result["http"], error=result.get("error"))
        time.sleep(5)
    raise SystemExit("market-web-governor unreachable on the private network")


def window():
    return {"start": "2026-09-01", "end": "2026-09-28", "as_of": "2026-09-28"}


def pre(prefix: str) -> dict:
    rid = lambda name: f"{prefix}{name}"  # noqa: E731

    # Test 1 — authentication (key values are never logged)
    record("T1 auth: no header", "GET /v1/capabilities", None, call("GET", "/v1/capabilities", auth=None))
    record("T1 auth: invalid bearer", "GET /v1/capabilities", None, call("GET", "/v1/capabilities", auth="invalid"))
    record("T1 auth: invalid bearer (POST)", "POST /v1/search", rid("t1-invalid"), call("POST", "/v1/search", {
        "contract_version": "v1", "request_id": rid("t1-invalid"), "query": "auth probe"}, auth="invalid"))
    record("T1 auth: valid key", "GET /v1/capabilities", None, call("GET", "/v1/capabilities"))

    # Test 2 — health, readiness, capabilities
    record("T2 health", "GET /health", None, call("GET", "/health", auth=None))
    record("T2 ready", "GET /ready", None, call("GET", "/ready", auth=None))

    # Test 3 — live current-news search
    t3_body = {
        "contract_version": "v1", "request_id": rid("t3-bbca-news"), "conversation_id": rid("conv"),
        "query": (
            "Find the latest material corporate announcement or company news concerning PT Bank Central Asia Tbk "
            "(BBCA) published between 2026-09-01 and 2026-09-28. Prefer an official BCA or IDX source. State the "
            "event, publication date, source, and what is actually confirmed. Do not infer facts that are not "
            "present in the source. Include supporting and potentially contradicting information."
        ),
        "time_window": window(),
        "source_policy": {"profile": "FINANCIAL_PRIMARY", "minimum_primary_sources": 1, "minimum_independent_sources": 1,
                          "primary_domains": ["bca.co.id", "idx.co.id"], "trusted_secondary_domains": []},
        "budget": {"max_searches": 1, "max_results_per_search": 5, "max_evidence_items": 5,
                   "max_output_characters": 16000},
        "locale": "id-ID", "timezone": "Asia/Jakarta",
    }
    t3 = record("T3 live news search", "POST /v1/search", t3_body["request_id"], call("POST", "/v1/search", t3_body))

    # Test 4 — allowed-domain policy
    t4_body = {
        "contract_version": "v1", "request_id": rid("t4-bi-rate-domain"),
        "query": ("What is the latest BI policy rate published by Bank Indonesia as of 2026-09-28? Report the rate, "
                  "effective or announcement date, and the official source."),
        "time_window": {"end": "2026-09-28", "as_of": "2026-09-28"},
        "source_policy": {"profile": "OFFICIAL_ONLY", "minimum_primary_sources": 1, "minimum_independent_sources": 1,
                          "allowed_domains": ["bi.go.id"], "primary_domains": ["bi.go.id"]},
        "budget": {"max_searches": 1, "max_results_per_search": 5, "max_evidence_items": 5,
                   "max_output_characters": 16000},
        "locale": "id-ID", "timezone": "Asia/Jakarta",
    }
    record("T4 domain policy bi.go.id", "POST /v1/search", t4_body["request_id"], call("POST", "/v1/search", t4_body))

    # Test 5 — exact URL fetch
    t5_body = {
        "contract_version": "v1", "request_id": rid("t5-bi-rate-fetch"),
        "url": "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx",
        "objective": ("Retrieve the policy-rate information shown on this official Bank Indonesia page: the latest "
                      "BI-Rate value and its date."),
        "locale": "id-ID",
    }
    record("T5 exact URL fetch", "POST /v1/fetch", t5_body["request_id"], call("POST", "/v1/fetch", t5_body))

    # Test 6 — multi-criterion WebNeedSpec, plan then execute
    t6_body = {
        "contract_version": "v1", "request_id": rid("t6-bbca-webneed"), "conversation_id": rid("conv"),
        "web_need": {
            "objective": ("Determine whether recent public information between 2026-09-01 and 2026-09-28 indicates a "
                          "material new corporate development concerning BBCA."),
            "hypothesis": {
                "hypothesis_id": "hyp-bbca-material-2026-09",
                "statement": "BBCA announced a material corporate development during the defined period.",
                "falsification_test": ("No qualifying announcement is present in an official BCA or IDX source during "
                                       "the period, or available sources only repeat older information."),
            },
            "entities": [
                {"entity_type": "ISSUER", "entity_id": "PT Bank Central Asia Tbk", "aliases": ["BCA", "Bank BCA"]},
                {"entity_type": "TICKER", "entity_id": "BBCA", "aliases": ["BBCA.JK"]},
            ],
            "time_window": window(),
            "evidence_standard": "PRIMARY_REQUIRED",
            "criteria": [
                {"criterion_id": "latest_development", "required": True, "direction": "BOTH", "minimum_sources": 1,
                 "question": ("Identify the most recent potentially material BBCA corporate development published "
                              "between 2026-09-01 and 2026-09-28 and its publication date."),
                 "preferred_source_tiers": ["PRIMARY"], "document_types": ["disclosure", "press release", "news"]},
                {"criterion_id": "official_confirmation", "required": True, "direction": "SUPPORT",
                 "minimum_sources": 1,
                 "question": ("Find an official BCA (bca.co.id) or IDX (idx.co.id) source dated 2026-09-01 to "
                              "2026-09-28 confirming a material BBCA development."),
                 "preferred_source_tiers": ["PRIMARY"], "document_types": ["keterbukaan informasi", "press release"]},
                {"criterion_id": "independent_secondary", "required": False, "direction": "SUPPORT",
                 "minimum_sources": 1,
                 "question": ("Find an independent secondary news source, dated 2026-09-01 to 2026-09-28, reporting "
                              "the same BBCA development."),
                 "preferred_source_tiers": ["TRUSTED_SECONDARY", "SECONDARY"], "document_types": ["news"]},
                {"criterion_id": "contradicting_evidence", "required": True, "direction": "REFUTE",
                 "minimum_sources": 1,
                 "question": ("Look specifically for evidence that contradicts or weakens the hypothesis that BBCA "
                              "announced a material corporate development between 2026-09-01 and 2026-09-28 "
                              "(for example denials, clarifications, or no new disclosure).")},
                {"criterion_id": "new_vs_repeat", "required": True, "direction": "BOTH", "minimum_sources": 1,
                 "question": ("Is the identified BBCA development genuinely new in 2026-09-01 to 2026-09-28, or a "
                              "repetition of an event first announced earlier? Give the earliest publication date "
                              "found.")},
            ],
            "source_policy": {"profile": "FINANCIAL_PRIMARY", "minimum_primary_sources": 1,
                              "minimum_independent_sources": 1, "allowed_domains": [], "excluded_domains": [],
                              "primary_domains": ["bca.co.id", "idx.co.id"], "trusted_secondary_domains": [
                                  "reuters.com", "bloomberg.com", "kontan.co.id", "bisnis.com", "cnbcindonesia.com"]},
            "budget": {"max_searches": 5, "max_results_per_search": 5, "max_evidence_items": 20,
                       "max_output_characters": 32000},
            "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": False},
            "locale": "id-ID", "timezone": "Asia/Jakarta",
        },
    }
    plan = record("T6 create plan", "POST /v1/web-needs", t6_body["request_id"], call("POST", "/v1/web-needs", t6_body))
    need_id = (plan.get("body") or {}).get("web_need_id")
    record("T6 read plan", "GET /v1/web-needs/{id}", t6_body["request_id"], call("GET", f"/v1/web-needs/{need_id}"))
    t6 = record("T6 execute", "POST /v1/web-needs/{id}/execute", t6_body["request_id"], call(
        "POST", f"/v1/web-needs/{need_id}/execute", {"contract_version": "v1", "request_id": t6_body["request_id"]}))

    # Test 7 — idempotency on the completed T3 search and T6 need
    t3_first = t3.get("body") or {}
    replay = record("T7 identical replay (search)", "POST /v1/search", t3_body["request_id"],
                    call("POST", "/v1/search", t3_body))
    log("idempotency", same_body=digest(replay.get("body")) == digest(t3_first),
        same_web_need=(replay.get("body") or {}).get("web_need_id") == t3_first.get("web_need_id"))
    changed = dict(t3_body, query=t3_body["query"] + " Focus on dividends only.")
    record("T7 changed content same request_id", "POST /v1/search", t3_body["request_id"],
           call("POST", "/v1/search", changed))
    t6_replay = record("T7 identical replay (web-need create)", "POST /v1/web-needs", t6_body["request_id"],
                       call("POST", "/v1/web-needs", t6_body))
    t6_exec_replay = record("T7 identical replay (execute)", "POST /v1/web-needs/{id}/execute", t6_body["request_id"],
                            call("POST", f"/v1/web-needs/{need_id}/execute",
                                 {"contract_version": "v1", "request_id": t6_body["request_id"]}))
    log("idempotency_t6", create_same=digest(t6_replay.get("body")) == digest(t6.get("body")),
        execute_same=digest(t6_exec_replay.get("body")) == digest(t6.get("body")))

    # Test 8 — budgets above the hard limits (plan creation only; nothing is executed)
    base_need = json.loads(json.dumps(t6_body["web_need"]))
    for name, budget in (
        ("searches-7", {"max_searches": 7}),
        ("results-10", {"max_results_per_search": 10}),
        ("evidence-40", {"max_evidence_items": 40}),
        ("output-64000", {"max_output_characters": 64000}),
        ("searches-99-schema", {"max_searches": 99}),
    ):
        need = json.loads(json.dumps(base_need))
        need["budget"].update(budget)
        body = {"contract_version": "v1", "request_id": rid(f"t8-{name}"), "web_need": need}
        record(f"T8 budget {name}", "POST /v1/web-needs", body["request_id"], call("POST", "/v1/web-needs", body))
    too_many = json.loads(json.dumps(base_need))
    too_many["criteria"] = [dict(base_need["criteria"][0], criterion_id=f"c{i}") for i in range(7)]
    too_many["budget"]["max_searches"] = 7
    record("T8 budget criteria-7", "POST /v1/web-needs", rid("t8-criteria-7"), call(
        "POST", "/v1/web-needs", {"contract_version": "v1", "request_id": rid("t8-criteria-7"), "web_need": too_many}))
    fast = dict(t4_body, request_id=rid("t8-fast-results-10"),
                budget={"max_searches": 1, "max_results_per_search": 10})
    record("T8 budget fast search results-10", "POST /v1/search", fast["request_id"], call("POST", "/v1/search", fast))
    # A rejected request_id must not have been stored: reusing it for a valid plan must not return 409.
    reuse = {"contract_version": "v1", "request_id": rid("t8-searches-7"), "web_need": base_need}
    record("T8 rejected id not stored (plan only)", "POST /v1/web-needs", reuse["request_id"],
           call("POST", "/v1/web-needs", reuse))

    # Test 9 — snapshot before redeploy
    t6_body_resp = t6.get("body") or {}
    evidence = (t6_body_resp.get("evidence") or (t3_first.get("evidence") or []))
    evidence_id = evidence[0]["evidence_id"] if evidence else None
    need_snapshot = call("GET", f"/v1/web-needs/{need_id}")
    evidence_snapshot = call("GET", f"/v1/evidence/{evidence_id}") if evidence_id else {"http": None, "body": None}
    snapshot = {"web_need_id": need_id, "evidence_id": evidence_id,
                "web_need_sha256": digest(need_snapshot.get("body")), "web_need_http": need_snapshot.get("http"),
                "evidence_sha256": digest(evidence_snapshot.get("body")), "evidence_http": evidence_snapshot.get("http"),
                "evidence_content_sha256": (evidence_snapshot.get("body") or {}).get("content_sha256")}
    log("snapshot", **snapshot)
    return snapshot


def post(plan: dict) -> dict:
    record("T9 ready after redeploy", "GET /ready", None, call("GET", "/ready", auth=None))
    need = call("GET", f"/v1/web-needs/{plan['web_need_id']}")
    evidence = call("GET", f"/v1/evidence/{plan['evidence_id']}")
    check = {
        "web_need_http": need.get("http"), "evidence_http": evidence.get("http"),
        "web_need_match": digest(need.get("body")) == plan["web_need_sha256"],
        "evidence_match": digest(evidence.get("body")) == plan["evidence_sha256"],
        "evidence_content_sha256": (evidence.get("body") or {}).get("content_sha256"),
    }
    log("persistence", **check)
    RESULTS.append({"test": "T9 persistence", "check": check, "web_need": need.get("body"),
                    "evidence": evidence.get("body")})
    return check


def smoke(prefix: str) -> None:
    """One bounded search on the official BI domain: checks the deploy end to end, including usage totals."""
    body = {
        "contract_version": "v1", "request_id": f"{prefix}smoke-bi-rate",
        "query": "What is the latest BI-Rate published by Bank Indonesia as of 2026-09-28, and its announcement date?",
        "time_window": {"end": "2026-09-28", "as_of": "2026-09-28"},
        "source_policy": {"minimum_independent_sources": 1, "allowed_domains": ["bi.go.id"],
                          "primary_domains": ["bi.go.id"]},
        "budget": {"max_searches": 1, "max_results_per_search": 3, "max_evidence_items": 3,
                   "max_output_characters": 12000},
    }
    result = record("smoke search bi.go.id", "POST /v1/search", body["request_id"], call("POST", "/v1/search", body))
    log("usage", usage=((result.get("body") or {}).get("execution") or {}).get("usage"))


def dump() -> None:
    blob = base64.b64encode(gzip.compress(json.dumps(RESULTS, ensure_ascii=False).encode())).decode()
    size = 800
    parts = [blob[i:i + size] for i in range(0, len(blob), size)]
    for index, part in enumerate(parts, start=1):
        print(f"WGTDUMP {index}/{len(parts)} {part}", flush=True)
        if index % 50 == 0:
            time.sleep(1)


def main() -> None:
    if len(KEY) < 32:
        raise SystemExit("WEB_GOVERNOR_API_KEY is not available to the runner")
    with open(os.path.join(HERE, "plan.json")) as handle:
        plan = json.load(handle)
    log("start", phase=plan["phase"], base=BASE)
    wait_ready()
    if plan["phase"] == "pre":
        pre(plan["prefix"])
        if plan.get("check"):
            post(plan["check"])
    elif plan["phase"] == "smoke":
        smoke(plan["prefix"])
    elif plan["phase"] == "post":
        post(plan)
    else:
        raise SystemExit("unknown phase")
    dump()
    log("done", phase=plan["phase"])
    time.sleep(30)  # Railway's log pipeline drops lines from containers that exit immediately (R08).


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        log("fatal", message=str(exc))
        time.sleep(30)
        sys.exit(0)
