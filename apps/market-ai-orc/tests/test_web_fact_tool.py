"""find_web_fact (S4b, PLAN_FINAL_2026-10-04.md Fase 4): the tool exists only with its switch and the web governor's
address and key; the model reads the status, value and quotes; the system writes the fact as a web source."""
from __future__ import annotations

import json

import httpx

from app.orchestrator import AgentOrchestrator, RunState
from app.schemas import FinalResponse
from app.tools import ToolOutcome, build_default_registry
from app.tools.web_fact import WebFactClient, model_view
from conftest import ScriptedClient, make_settings

CONFIRMED = {"status": "CONFIRMED", "subject": "BBCA", "attribute": "BUMN atau swasta", "value": "swasta",
             "as_of": "2026-10-04", "cached": False,
             "versions": [{"value": "swasta", "domains": ["bisnis.com", "kontan.co.id"], "official": False,
                           "quotes": [{"quote": "bank swasta milik Grup Djarum", "url": "https://bisnis.com/a",
                                       "date": None}]}],
             "sources": [{"n": 1}, {"n": 2}], "warnings": [], "cost_usd": 0.004}


def client(handler) -> WebFactClient:
    return WebFactClient("http://web", "w" * 40, transport=httpx.MockTransport(handler))


def test_the_tool_is_registered_only_with_a_client() -> None:
    assert "find_web_fact" not in build_default_registry().names()
    registry = build_default_registry(web_fact_client=client(lambda r: httpx.Response(200, json=CONFIRMED)))
    assert "find_web_fact" in registry.names()


def test_the_call_reaches_v1_fact_and_the_model_reads_no_excerpts() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content), request.headers["Authorization"]))
        return httpx.Response(200, json=CONFIRMED)

    registry = build_default_registry(web_fact_client=client(handler))
    outcome = registry.execute("c1", "find_web_fact", json.dumps({"subject": "BBCA", "attribute": "BUMN atau swasta"}))
    assert outcome.ok and seen[0][0] == "/v1/fact" and seen[0][2] == "Bearer " + "w" * 40
    result = outcome.output["result"]
    assert result["status"] == "CONFIRMED" and result["value"] == "swasta" and result["sources_read"] == 2
    assert "sources" not in result


def test_an_unreachable_web_governor_is_a_named_error() -> None:
    registry = build_default_registry(web_fact_client=client(lambda r: httpx.Response(503)))
    outcome = registry.execute("c1", "find_web_fact", json.dumps({"subject": "BBCA", "attribute": "status"}))
    assert not outcome.ok and outcome.output["error"]["code"] == "WEB_FACT_UNAVAILABLE"


def test_the_fact_is_written_as_a_web_source_by_the_system() -> None:
    orc = AgentOrchestrator(make_settings(), ScriptedClient([]), build_default_registry())
    state = RunState(request_id="r1", started=0.0, input_items=[])
    orc._track_choices(state, "find_web_fact", {"subject": "BBCA"},
                       ToolOutcome(call_id="c1", name="find_web_fact", ok=True,
                                   output={"result": model_view(CONFIRMED)}))
    final = FinalResponse(response_type="ANSWER", answer="BBCA bank swasta.", clarification_question=None,
                          assumptions=[], limitations=[])
    line = orc._with_ai_choices(state, final).assumptions[0]
    assert line.startswith("Fakta web") and "swasta (bisnis.com, kontan.co.id) (terkonfirmasi)" in line


def test_a_conflict_shows_every_version() -> None:
    from app.ai_choices import describe_web
    conflict = {**CONFIRMED, "status": "CONFLICTING", "value": None,
                "versions": [{"value": "swasta", "domains": ["a.com"]}, {"value": "BUMN", "domains": ["b.com"]}]}
    assert "swasta (a.com) vs BUMN (b.com) (sumbernya berbeda)" in describe_web([conflict])


def test_settings() -> None:
    settings = make_settings(AI_ENABLE_WEB_FACT="true", WEB_GOVERNOR_URL="http://web", WEB_GOVERNOR_API_KEY="k" * 40)
    assert settings.ai_enable_web_fact and settings.web_governor_url == "http://web"
    assert "k" * 40 not in repr(settings)
