"""Regressions from the 2026-09-28 live test (see ERRORS_AND_SOLUTIONS.md W01-W04)."""
from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import EvidenceCriterion, SourcePolicy, WebNeedSpec
from app.provider import OpenRouterProvider
from app.store import SqliteStore

from conftest import API_KEY, make_settings
from test_api import request_body

FETCH_URL = "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx"


def response_json(text, annotations=(), status="completed", incomplete=None, items=("web_search_call",)):
    body = {
        "id": "resp-1",
        "model": "test/model",
        "status": status,
        "output": [{"type": item} for item in items] + [{
            "type": "message",
            "content": [{"type": "output_text", "text": text, "annotations": list(annotations)}],
        }],
        "usage": {"input_tokens": 10, "output_tokens": 1800, "total_tokens": 1810},
    }
    if incomplete:
        body["incomplete_details"] = {"reason": incomplete}
    return body


def citation(url, content="Source excerpt."):
    return {"type": "url_citation", "url": url, "title": "Title", "content": content}


def provider_for(tmp_path, responses):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json=queue.pop(0))

    settings = make_settings(str(tmp_path / "web.sqlite3"))
    return settings, OpenRouterProvider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def auth():
    return {"Authorization": f"Bearer {API_KEY}"}


def client_for(tmp_path, responses):
    settings, provider = provider_for(tmp_path, responses)
    return TestClient(create_app(settings=settings, store=SqliteStore(settings.store_path), provider=provider))


def spec_one():
    return WebNeedSpec(objective="o", criteria=[EvidenceCriterion(criterion_id="c1", question="q")])


def test_truncated_response_is_incomplete_not_a_verdict(tmp_path):
    # Live T6 `new_vs_repeat`: the text stopped after the labels and was read as CONTRADICTED.
    _, provider = provider_for(tmp_path, [
        response_json("ASSESSMENT: CONTRADICTED\nSUMMARY:", [citation("https://www.idx.co.id/a.pdf")]),
        response_json("", status="incomplete", incomplete="max_output_tokens"),
    ])
    spec = spec_one()
    truncated = provider.research_criterion("wn", spec, spec.criteria[0], "pc-1")
    assert truncated.output_complete is False
    assert truncated.assessment == "INSUFFICIENT"
    assert truncated.provider_call["status"] == "INCOMPLETE"
    empty = provider.research_criterion("wn", spec, spec.criteria[0], "pc-2")
    assert empty.output_complete is False
    assert empty.provider_call["diagnostics"]["incomplete_reason"] == "max_output_tokens"
    assert empty.provider_call["diagnostics"]["response_status"] == "incomplete"


def test_markdown_labels_still_parse(tmp_path):
    _, provider = provider_for(tmp_path, [
        response_json("**ASSESSMENT:** x\nASSESSMENT: SUPPORTED\n**SUMMARY:** Found it.", [citation("https://x.co/a")]),
    ])
    spec = spec_one()
    result = provider.research_criterion("wn", spec, spec.criteria[0], "pc-1")
    assert result.output_complete is True
    assert (result.assessment, result.summary) == ("SUPPORTED", "Found it.")
    assert result.applied_policy["search_tool_observed"] is True


def test_incomplete_criterion_is_blocked_and_asks_for_retry(tmp_path, auth):
    # Live T6: two required criteria with empty provider output were reported as NOT_FOUND.
    body = request_body("req-incomplete")
    body["web_need"]["criteria"].append(dict(body["web_need"]["criteria"][0], criterion_id="second"))
    body["web_need"]["budget"]["max_searches"] = 2
    responses = [
        response_json("ASSESSMENT: SUPPORTED\nSUMMARY: Filing found.", [citation("https://www.idx.co.id/f.pdf")]),
        response_json("", status="incomplete", incomplete="max_output_tokens"),
    ]
    with client_for(tmp_path, responses) as client:
        planned = client.post("/v1/web-needs", headers=auth, json=body).json()
        result = client.post(f"/v1/web-needs/{planned['web_need_id']}/execute", headers=auth,
                             json={"contract_version": "v1", "request_id": "req-incomplete"}).json()
    by_id = {row["criterion_id"]: row for row in result["coverage"]}
    assert by_id["capex"]["status"] == "SATISFIED"
    assert by_id["second"]["status"] == "BLOCKED"
    assert "PROVIDER_OUTPUT_INCOMPLETE" in by_id["second"]["gaps"]
    assert result["status"] == "PARTIAL"
    assert result["next_action"] == "RETRY_PROVIDER"
    assert "PROVIDER_OUTPUT_INCOMPLETE" in {w["code"] for w in result["warnings"]}
    calls = result["execution"]["provider_calls"]
    assert [call["status"] for call in calls] == ["SUCCEEDED", "INCOMPLETE"]
    assert "Filing found." not in json.dumps(calls)


def test_fetch_uses_the_requested_url_citation_even_if_not_first(tmp_path, auth):
    # Live T5: only the first annotation was considered, so the exact URL's citation could be dropped.
    responses = [response_json(
        "ASSESSMENT: SUPPORTED\nSUMMARY: BI-Rate 5.75%.",
        [citation("https://www.bi.go.id/id/default.aspx"), citation(FETCH_URL, "BI-Rate 5,75%")],
        items=("openrouter:web_fetch",),
    )]
    with client_for(tmp_path, responses) as client:
        result = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "req-fetch-1", "url": FETCH_URL, "objective": "rate"}).json()
    assert result["status"] == "EVIDENCE_READY"
    assert [e["canonical_url"] for e in result["evidence"]] == [FETCH_URL]
    assert result["applied_policy"][0]["fetch_tool_observed"] is True


def test_fetch_without_exact_citation_withholds_the_uncited_summary(tmp_path, auth):
    responses = [response_json("ASSESSMENT: SUPPORTED\nSUMMARY: BI-Rate 5.75% on 19 August 2026.", [],
                               items=())]
    with client_for(tmp_path, responses) as client:
        result = client.post("/v1/fetch", headers=auth, json={
            "contract_version": "v1", "request_id": "req-fetch-2", "url": FETCH_URL, "objective": "rate"}).json()
    coverage = result["coverage"][0]
    assert result["evidence"] == []
    assert coverage["status"] == "NOT_FOUND"
    assert "NO_USABLE_CITATION" in coverage["gaps"]
    assert "5.75" not in coverage["summary"]
    codes = {w["code"] for w in result["warnings"]}
    assert {"EXACT_URL_NOT_CITED", "EXACT_FETCH_NOT_OBSERVED"} <= codes
    assert result["next_action"] == "REVIEW_FETCH"


def test_policy_rejected_citations_are_reported(tmp_path, auth):
    responses = [response_json(
        "ASSESSMENT: SUPPORTED\nSUMMARY: Rate found.",
        [citation("https://www.bi.go.id/a"), citation("https://news.example.com/b")],
    )]
    with client_for(tmp_path, responses) as client:
        result = client.post("/v1/search", headers=auth, json={
            "contract_version": "v1", "request_id": "req-domain", "query": "BI rate",
            "source_policy": {"allowed_domains": ["bi.go.id"]},
            "budget": {"max_searches": 1, "max_results_per_search": 5}}).json()
    assert {e["domain"] for e in result["evidence"]} == {"www.bi.go.id"}
    assert "CITATIONS_REJECTED_BY_POLICY" in {w["code"] for w in result["warnings"]}
    assert result["execution"]["usage"]["tool_calls_observed"] == 1
