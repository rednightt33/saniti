from __future__ import annotations

from app.config import ConfigError, Settings


def request_body(request_id="req-1"):
    return {
        "contract_version": "v1",
        "request_id": request_id,
        "conversation_id": "conv-1",
        "web_need": {
            "objective": "Verify the issuer's reported capex.",
            "hypothesis": {
                "hypothesis_id": "hyp-1",
                "statement": "Capex increased year over year.",
                "falsification_test": "The audited filing reports flat or lower capex.",
            },
            "entities": [{"entity_type": "ISSUER", "entity_id": "TEST", "aliases": []}],
            "time_window": {"start": "2025-01-01", "end": "2026-09-28", "as_of": "2026-09-28"},
            "evidence_standard": "PRIMARY_REQUIRED",
            "criteria": [{
                "criterion_id": "capex",
                "question": "What capex did the issuer report in its audited filing?",
                "required": True,
                "direction": "BOTH",
                "minimum_sources": 1,
                "preferred_source_tiers": ["PRIMARY"],
                "document_types": ["audited filing"],
                "inclusion_terms": ["capital expenditure"],
                "exclusion_terms": [],
            }],
            "source_policy": {
                "profile": "FINANCIAL_PRIMARY",
                "minimum_primary_sources": 1,
                "minimum_independent_sources": 1,
                "allowed_domains": [],
                "excluded_domains": [],
                "primary_domains": ["idx.co.id"],
                "trusted_secondary_domains": [],
            },
            "budget": {
                "max_searches": 1,
                "max_results_per_search": 5,
                "max_evidence_items": 5,
                "max_output_characters": 16000,
            },
            "stop_conditions": {"all_required_criteria_covered": True, "stop_on_primary_source": True},
            "locale": "id-ID",
            "timezone": "Asia/Jakarta",
        },
    }


def test_auth_and_capabilities(client, auth):
    assert client.get("/v1/capabilities").status_code == 401
    response = client.get("/v1/capabilities", headers=auth)
    assert response.status_code == 200
    assert response.json()["operations"] == ["PLAN_WEB_NEED", "EXECUTE_WEB_NEED", "SEARCH", "FETCH_URL"]


def test_plan_execute_and_read_evidence(client, auth):
    planned = client.post("/v1/web-needs", headers=auth, json=request_body()).json()
    assert planned["status"] == "APPROVED"
    executed = client.post(
        f"/v1/web-needs/{planned['web_need_id']}/execute",
        headers=auth,
        json={"contract_version": "v1", "request_id": "req-1"},
    )
    assert executed.status_code == 200
    body = executed.json()
    assert body["status"] == "EVIDENCE_READY"
    assert body["coverage"][0]["status"] == "SATISFIED"
    assert body["evidence"][0]["source_tier"] == "PRIMARY"
    assert body["evidence"][0]["canonical_url"] == "https://www.idx.co.id/filing.pdf"
    evidence = client.get(f"/v1/evidence/{body['evidence'][0]['evidence_id']}", headers=auth)
    assert evidence.status_code == 200
    assert evidence.json()["citation_id"] == body["evidence"][0]["citation_id"]


def test_idempotency_replays_and_rejects_changed_request(client, auth):
    first = client.post("/v1/web-needs", headers=auth, json=request_body()).json()
    replay = client.post("/v1/web-needs", headers=auth, json=request_body()).json()
    assert replay["web_need_id"] == first["web_need_id"]
    changed = request_body()
    changed["web_need"]["objective"] = "A different objective"
    conflict = client.post("/v1/web-needs", headers=auth, json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_contract_rejects_unknown_fields_and_over_budget(client, auth):
    extra = request_body()
    extra["provider"] = "exa"
    assert client.post("/v1/web-needs", headers=auth, json=extra).status_code == 422
    high = request_body("req-high")
    high["web_need"]["budget"]["max_searches"] = 7
    response = client.post("/v1/web-needs", headers=auth, json=high)
    assert response.status_code == 422
    assert response.json()["code"] == "SEARCH_BUDGET_TOO_HIGH"


def test_fetch_rejects_private_url(client, auth):
    response = client.post("/v1/fetch", headers=auth, json={
        "contract_version": "v1",
        "request_id": "req-fetch",
        "url": "https://127.0.0.1/admin",
        "objective": "Read it",
        "locale": "id-ID",
    })
    assert response.status_code == 422


def test_config_requires_strong_service_key(tmp_path):
    try:
        Settings.from_env({
            "WEB_GOVERNOR_API_KEY": "short",
            "OPENROUTER_API_KEY": "key",
            "WEB_GOVERNOR_STORE_PATH": str(tmp_path / "x.sqlite3"),
        })
    except ConfigError as exc:
        assert "at least 32" in str(exc)
    else:
        raise AssertionError("weak key was accepted")
