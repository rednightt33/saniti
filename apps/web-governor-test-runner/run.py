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
import re
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
    t6_body = t6_request(rid)
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
        ("results-31-schema", {"max_results_per_search": 31}),
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
    fast = dict(t4_body, request_id=rid("t8-fast-evidence-41"),
                budget={"max_searches": 1, "max_evidence_items": 41})
    record("T8 budget fast search evidence-41", "POST /v1/search", fast["request_id"], call("POST", "/v1/search", fast))
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


def t6_request(rid, results: int = 5) -> dict:
    return {
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
        "budget": {"max_searches": 5, "max_results_per_search": results, "max_evidence_items": 20,
                   "max_output_characters": 32000},
        "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": False},
        "locale": "id-ID", "timezone": "Asia/Jakarta",
    },
}


def webneed(prefix: str, results: int) -> None:
    """T6 only: the multi-criterion WebNeed, with a chosen results-per-search budget."""
    body = t6_request(lambda name: f"{prefix}{name}", results)
    plan = record("T6 create plan", "POST /v1/web-needs", body["request_id"], call("POST", "/v1/web-needs", body))
    need_id = (plan.get("body") or {}).get("web_need_id")
    record("T6 execute", "POST /v1/web-needs/{id}/execute", body["request_id"], call(
        "POST", f"/v1/web-needs/{need_id}/execute", {"contract_version": "v1", "request_id": body["request_id"]}))


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


def ultj_request(prefix: str, slot: int) -> dict:
    window = {"start": "2025-09-28", "end": "2026-09-28", "as_of": "2026-09-28"}
    return {
        "contract_version": "v1", "request_id": f"{prefix}ultj-ffi-slot{slot}", "conversation_id": f"{prefix}ultj",
        "web_need": {
            "objective": ("Collect public indications, from 2025-09-28 to 2026-09-28 and earlier if they are the first "
                          "signal, that point to an acquisition of PT Frisian Flag Indonesia by PT Ultrajaya Milk "
                          "Industry & Trading Company Tbk (ULTJ), and establish when this was first publicly known."),
            "hypothesis": {
                "hypothesis_id": "hyp-ultj-acquires-ffi",
                "statement": "ULTJ is acquiring or has agreed to acquire PT Frisian Flag Indonesia.",
                "falsification_test": ("No ULTJ, IDX or FrieslandCampina source mentions such a transaction, or the "
                                       "parties deny it, or the reports concern a different buyer or asset."),
            },
            "entities": [
                {"entity_type": "ISSUER", "entity_id": "ULTJ",
                 "aliases": ["PT Ultrajaya Milk Industry & Trading Company Tbk", "Ultrajaya"]},
                {"entity_type": "COMPANY", "entity_id": "PT Frisian Flag Indonesia",
                 "aliases": ["Frisian Flag", "FrieslandCampina Indonesia"]},
                {"entity_type": "COMPANY", "entity_id": "Royal FrieslandCampina N.V.", "aliases": ["FrieslandCampina"]},
            ],
            "time_window": window,
            "evidence_standard": "CORROBORATED",
            "criteria": [
                {"criterion_id": "latest_status", "required": True, "direction": "BOTH", "minimum_sources": 1,
                 "question": ("What is the latest reported status of any plan, negotiation or agreement for ULTJ "
                              "(Ultrajaya) to acquire PT Frisian Flag Indonesia, and on what date was it reported?"),
                 "document_types": ["news", "keterbukaan informasi", "press release"]},
                {"criterion_id": "earliest_signal", "required": True, "direction": "SUPPORT", "minimum_sources": 1,
                 "question": ("What is the earliest public report, rumour, statement or disclosure linking Ultrajaya "
                              "(ULTJ) to an acquisition of Frisian Flag Indonesia? Give its publication date and "
                              "source."),
                 "document_types": ["news", "analyst report"]},
                {"criterion_id": "official_disclosure", "required": True, "direction": "SUPPORT", "minimum_sources": 1,
                 "question": ("Is there an official ULTJ or IDX disclosure (keterbukaan informasi, RUPS material, "
                              "public expose) about acquiring Frisian Flag Indonesia? Give its date."),
                 "preferred_source_tiers": ["PRIMARY"], "document_types": ["keterbukaan informasi"]},
                {"criterion_id": "counterparty_view", "required": False, "direction": "BOTH", "minimum_sources": 1,
                 "question": ("What has Royal FrieslandCampina said about selling or divesting Frisian Flag "
                              "Indonesia, and does it name Ultrajaya as the buyer?")},
                {"criterion_id": "contradicting", "required": True, "direction": "REFUTE", "minimum_sources": 1,
                 "question": ("Find denials, clarifications or reports that contradict or weaken an ULTJ acquisition "
                              "of Frisian Flag Indonesia (for example a different buyer, a stalled deal, or a denial "
                              "to IDX).")},
            ],
            "source_policy": {"profile": "FINANCIAL_PRIMARY", "minimum_primary_sources": 0,
                              "minimum_independent_sources": 1,
                              "primary_domains": ["ultrajaya.co.id", "idx.co.id", "frieslandcampina.com",
                                                  "frisianflag.com"],
                              "trusted_secondary_domains": ["reuters.com", "bloomberg.com", "kontan.co.id",
                                                            "bisnis.com", "cnbcindonesia.com", "kompas.com",
                                                            "idnfinancials.com", "investor.id"]},
            "budget": {"max_searches": 5, "max_results_per_search": 10, "max_evidence_items": 40,
                       "max_output_characters": 64000},
            "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": False},
            "locale": "id-ID", "timezone": "Asia/Jakarta",
            "model_slot": slot,
        },
    }


def ultj(prefix: str, slots: list[int]) -> None:
    """ULTJ / Frisian Flag research on several model slots in parallel, then a governor fetch per slot."""
    from concurrent.futures import ThreadPoolExecutor

    def run(slot: int) -> dict:
        body = ultj_request(prefix, slot)
        plan = record(f"ULTJ slot {slot} plan", "POST /v1/web-needs", body["request_id"],
                      call("POST", "/v1/web-needs", body))
        need_id = (plan.get("body") or {}).get("web_need_id")
        return record(f"ULTJ slot {slot} execute", "POST /v1/web-needs/{id}/execute", body["request_id"], call(
            "POST", f"/v1/web-needs/{need_id}/execute", {"contract_version": "v1", "request_id": body["request_id"]}))

    with ThreadPoolExecutor(max_workers=len(slots)) as pool:
        results = list(pool.map(run, slots))

    # Governor-side fetch: the BI-Rate page on every slot, and the first primary or PDF source from slot 1.
    def fetch(slot: int, url: str, objective: str, name: str) -> None:
        body = {"contract_version": "v1", "request_id": f"{prefix}{name}-slot{slot}", "url": url,
                "objective": objective, "locale": "id-ID", "model_slot": slot}
        record(f"FETCH {name} slot {slot}", "POST /v1/fetch", body["request_id"], call("POST", "/v1/fetch", body))

    with ThreadPoolExecutor(max_workers=len(slots)) as pool:
        list(pool.map(lambda slot: fetch(slot, "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx",
                                         "Nilai BI-Rate terbaru dan tanggalnya.", "bi-rate"), slots))
    evidence = ((results[0].get("body") or {}).get("evidence") or [])
    pick = next((item for item in evidence if item.get("content_type") == "PDF"
                 or item.get("source_tier") == "PRIMARY"), evidence[0] if evidence else None)
    if pick:
        fetch(slots[0], pick["canonical_url"],
              "Apa yang dinyatakan dokumen ini tentang akuisisi PT Frisian Flag Indonesia oleh ULTJ (Ultrajaya), "
              "termasuk tanggal-tanggal penting?", "ultj-source")


def migrate_event_store() -> None:
    """Apply the event-store migration to Postgres-E8GM and set the role passwords. Uses a temporary admin URL."""
    import psycopg
    from psycopg import sql

    admin = os.environ["EVENT_STORE_ADMIN_URL"]
    with open(os.path.join(HERE, "001_web_event_item.sql")) as handle:
        script = handle.read()
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(script)
        for role, variable in (("web_event_writer", "EVENT_STORE_WRITER_PASSWORD"),
                               ("web_event_reader", "EVENT_STORE_READER_PASSWORD")):
            connection.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(os.environ[variable])))
        columns = connection.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'web_event_item'").fetchone()[0]
        grants = connection.execute(
            "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
            "WHERE table_name = 'web_event_item' AND grantee LIKE 'web_event_%' ORDER BY 1, 2").fetchall()
    log("migrated", columns=columns, grants=[list(grant) for grant in grants])


def migrate_sql(name: str) -> None:
    """Apply one idempotent event-store migration file (copied next to run.py) with a temporary admin URL."""
    import psycopg

    if not re.fullmatch(r"\d{3}_[a-z_]+\.sql", name):
        raise SystemExit("invalid migration name")
    with open(os.path.join(HERE, name)) as handle:
        script = handle.read()
    with psycopg.connect(os.environ["EVENT_STORE_ADMIN_URL"], autocommit=True) as connection:
        connection.execute(script)
        tables = connection.execute(
            "SELECT table_name, count(*) FROM information_schema.columns WHERE table_schema = 'public' "
            "GROUP BY 1 ORDER BY 1").fetchall()
        grants = connection.execute(
            "SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) "
            "FROM information_schema.role_table_grants WHERE grantee LIKE 'web_event_%' GROUP BY 1, 2 ORDER BY 1, 2"
        ).fetchall()
    log("migrated", file=name, tables=[list(t) for t in tables], grants=[list(g) for g in grants])


def ask(prefix: str, questions: list[str]) -> None:
    """Lean POST /v1/ask: one request per question, in parallel; then read the stored rows back."""
    from concurrent.futures import ThreadPoolExecutor

    def one(pair):
        index, question = pair
        request_id = f"{prefix}q{index}"
        return request_id, call("POST", "/v1/ask", {"request_id": request_id, "question": question}, timeout=900)

    with ThreadPoolExecutor(max_workers=len(questions)) as pool:
        for request_id, result in pool.map(one, enumerate(questions, 1)):
            body = result.get("body") or {}
            log("ask", request_id=request_id, http=result.get("http"), status=body.get("status"),
                sources=len(body.get("sources") or []), citations=len(body.get("citations") or []),
                seconds=body.get("seconds"), cost=(body.get("usage") or {}).get("cost_usd"), stored=body.get("stored"),
                warnings=sorted({w.get("code") for w in body.get("warnings") or []}))
            RESULTS.append({"test": "ASK", "request_id": request_id, "http": result.get("http"), "response": body})
    if os.environ.get("EVENT_STORE_READER_URL"):
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(os.environ["EVENT_STORE_READER_URL"], row_factory=dict_row) as connection:
            rows = connection.execute(
                "SELECT request_id, status, jsonb_array_length(citations) AS citations, "
                "jsonb_array_length(sources) AS sources, created_at, expires_at FROM web_ask "
                "WHERE request_id LIKE %s ORDER BY request_id", (prefix + "%",)).fetchall()
        log("ask_rows", count=len(rows))
        RESULTS.append({"test": "ASK rows", "rows": [{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                                                      for k, v in row.items()} for row in rows]})


def read_event_store(card_id: str | None = None, limit: int = 100) -> list[dict]:
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(os.environ["EVENT_STORE_READER_URL"], row_factory=dict_row) as connection:
        if card_id:
            rows = connection.execute("SELECT * FROM web_event_item WHERE card_id = %s ORDER BY card_rank",
                                      (card_id,)).fetchall()
        else:
            rows = connection.execute("SELECT * FROM web_event_item ORDER BY created_at DESC LIMIT %s",
                                      (limit,)).fetchall()
    return [{key: (value.isoformat() if hasattr(value, "isoformat") else
                   float(value) if type(value).__name__ == "Decimal" else value)
             for key, value in row.items()} for row in rows]


def precursor(prefix: str, slot: int, results: int) -> None:
    """Pre-event indicators for ULTJ / Frisian Flag Indonesia, anchored on the 18 Sep 2026 announcement."""
    body = {
        "contract_version": "v1", "request_id": f"{prefix}ultj-precursor-slot{slot}",
        "web_need": {
            "objective": ("Find indications, published before ULTJ announced the acquisition of PT Frisian Flag "
                          "Indonesia on 18 September 2026, that pointed to this event, and when they first appeared."),
            "analysis_mode": "EVENT_PRECURSOR",
            "anchor_event": {
                "description": ("PT Ultrajaya Milk Industry & Trading Company Tbk (ULTJ) announced it will acquire "
                                "100% of PT Frisian Flag Indonesia from FrieslandCampina through an inbreng and a "
                                "rights issue, making FrieslandCampina ULTJ's controlling shareholder"),
                "event_date": "2026-09-18", "tickers": ["ULTJ"]},
            "lookback_months": 12,
            "entities": [
                {"entity_type": "ISSUER", "entity_id": "PT Ultrajaya Milk Industry & Trading Company Tbk",
                 "aliases": ["ULTJ", "Ultrajaya"]},
                {"entity_type": "COMPANY", "entity_id": "PT Frisian Flag Indonesia", "aliases": ["Frisian Flag"]},
                {"entity_type": "COMPANY", "entity_id": "Royal FrieslandCampina N.V.", "aliases": ["FrieslandCampina"]},
            ],
            "evidence_standard": "SINGLE_SOURCE",
            "source_policy": {"minimum_independent_sources": 1,
                              "primary_domains": ["ultrajaya.co.id", "frieslandcampina.com", "frisianflag.com"]},
            "budget": {"max_searches": 6, "max_results_per_search": results, "max_evidence_items": 40,
                       "max_output_characters": 64000},
            "locale": "id-ID", "timezone": "Asia/Jakarta", "model_slot": slot,
        },
    }
    plan = record(f"PRECURSOR slot {slot} plan", "POST /v1/web-needs", body["request_id"],
                  call("POST", "/v1/web-needs", body))
    need_id = (plan.get("body") or {}).get("web_need_id")
    result = record(f"PRECURSOR slot {slot} execute", "POST /v1/web-needs/{id}/execute", body["request_id"], call(
        "POST", f"/v1/web-needs/{need_id}/execute", {"contract_version": "v1", "request_id": body["request_id"]},
        timeout=1800))
    card_id = ((result.get("body") or {}).get("event_store") or {}).get("card_id")
    if card_id and os.environ.get("EVENT_STORE_READER_URL"):
        rows = read_event_store(card_id)
        log("event_store_rows", card_id=card_id, count=len(rows))
        RESULTS.append({"test": "EVENT_STORE rows", "rows": rows})


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
    with open(os.path.join(HERE, "plan.json")) as handle:
        plan = json.load(handle)
    log("start", phase=plan["phase"], base=BASE)
    if plan["phase"] in ("migrate_event_store", "migrate_sql"):
        migrate_event_store() if plan["phase"] == "migrate_event_store" else migrate_sql(plan["file"])
        log("done", phase=plan["phase"])
        time.sleep(30)
        return
    if len(KEY) < 32:
        raise SystemExit("WEB_GOVERNOR_API_KEY is not available to the runner")
    wait_ready()
    if plan["phase"] == "pre":
        pre(plan["prefix"])
        if plan.get("check"):
            post(plan["check"])
    elif plan["phase"] == "migrate_event_store":
        migrate_event_store()
    elif plan["phase"] == "precursor":
        precursor(plan["prefix"], int(plan.get("slot", 1)), int(plan.get("results", 10)))
    elif plan["phase"] == "ultj":
        ultj(plan["prefix"], [int(slot) for slot in plan.get("slots", [1])])
    elif plan["phase"] == "webneed":
        webneed(plan["prefix"], int(plan.get("results", 5)))
    elif plan["phase"] == "ask":
        ask(plan["prefix"], plan["questions"])
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
