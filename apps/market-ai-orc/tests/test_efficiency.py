"""Run-time and cost controls from the 2026-09-26 stress test: provider routing and provider logging
(AI_PROVIDER_SORT, AI_LOG_PROVIDER), the final-response contract and Research Plan field form in the system prompt
(AI_FINAL_CONTRACT_IN_PROMPT), final-gate and re-ask logging, and the catalog summary in the prompt
(AI_CATALOG_SUMMARY_IN_PROMPT). Every flag defaults off and leaves requests byte-identical to before."""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest

from app.catalog_summary import HEADER, CatalogSummary, build_summary
from app.config import ConfigError
from app.openrouter_client import OpenRouterClient
from app.orchestrator import (FINALIZE_INSTRUCTION, PLAN_FIELD_RULES, RESPONSE_CONTRACT, STRICT_SCHEMA_LINE,
                              SYSTEM_PROMPT, build_system_prompt, schema_skeleton)
from app.provenance import parse_numbers
from app.provider_log import ProviderLogger, provider_fields
from app.research_plan import ResearchPlan
from app.schemas import AgentRunRequest
from app.tools.registry import strict_parameters_schema
from conftest import ANSWER, final_response, make_settings, tool_call_response
from test_orchestrator import ListHandler, orchestrator, request
from test_research_plan import (ON, Sandbox, classifier, continuation, first_turn, plan_response)
from test_research_plan import orchestrator as plan_orchestrator


def run_logged(agent, run_request: AgentRunRequest):
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        result = agent.run(run_request)
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    return result, [json.loads(m) for m in handler.messages]


def numbers(text: str) -> list[float]:
    return sorted(value for shown in parse_numbers(text) for value, _ in shown.candidates)


# ------------------------------------------------------------------------------------ provider routing (R1)

def test_provider_sort_is_off_by_default_and_validated() -> None:
    assert make_settings().ai_provider_sort is None
    assert make_settings(AI_PROVIDER_SORT=" Throughput ").ai_provider_sort == "throughput"
    with pytest.raises(ConfigError, match="AI_PROVIDER_SORT"):
        make_settings(AI_PROVIDER_SORT="fastest")


def test_the_default_request_keeps_openrouter_load_balancing() -> None:
    agent, client = orchestrator([final_response(ANSWER)])
    agent.run(request())
    assert client.payloads[0]["provider"] == {"require_parameters": True, "allow_fallbacks": True}


def test_provider_sort_reaches_every_model_call_including_the_reply_classifier() -> None:
    sandbox = Sandbox()
    issued = first_turn(sandbox)[0].continuation
    agent, scripted = plan_orchestrator([classifier("CANCEL"), final_response(
        {"response_type": "ANSWER", "answer": "Dibatalkan.", "clarification_question": None, "assumptions": [],
         "limitations": [], "research_plan": None})], sandbox, AI_PROVIDER_SORT="throughput")
    agent.run(AgentRunRequest(request_id="run_002", conversation_id="conv_1", message="batal saja",
                              continuation=continuation(issued)))
    assert len(scripted.payloads) == 2  # the classifier, then the cancel turn
    for payload in scripted.payloads:
        assert payload["provider"] == {"require_parameters": True, "allow_fallbacks": True, "sort": "throughput"}


# ------------------------------------------------------------------------------------ provider logging (R1)

def generation_record(**overrides: Any) -> dict[str, Any]:
    record = {"provider_name": "Together", "model": "deepseek/model-20260910", "latency": 178,
              "generation_time": 4000, "native_tokens_completion": 800, "native_tokens_cached": 45824,
              "finish_reason": "stop", "total_cost": 0.0024,
              "provider_responses": [{"provider_name": "DeepInfra", "status": 502},
                                     {"provider_name": "Together", "status": 200}]}
    record.update(overrides)
    return record


def test_provider_fields_report_routing_and_speed_without_content() -> None:
    fields = provider_fields(generation_record())
    assert fields["provider"] == "Together" and fields["output_tokens_per_second"] == 200.0
    assert fields["provider_attempts"] == 2 and fields["failed_providers"] == ["DeepInfra"]
    assert fields["first_token_ms"] == 178 and fields["native_cached_tokens"] == 45824
    assert provider_fields({"provider_name": "X", "generation_time": 0})["output_tokens_per_second"] is None


class Generations:
    def __init__(self, ready_after: dict[str, int]) -> None:
        self.ready_after = ready_after  # generation id -> lookups that return None first
        self.lookups: list[str] = []

    def generation(self, generation_id: str) -> dict[str, Any] | None:
        self.lookups.append(generation_id)
        if self.lookups.count(generation_id) <= self.ready_after.get(generation_id, 0):
            return None
        if generation_id == "gen-boom":
            raise RuntimeError("transport closed")
        return generation_record()


def lookup_logged(source, calls) -> tuple[list[float], list[dict[str, Any]]]:
    waits: list[float] = []
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        logger = ProviderLogger(source, delays=(1.0, 2.0, 4.0), sleep=waits.append)
        logger.lookup("req-9", calls)
        logger.close()
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    return waits, [json.loads(m) for m in handler.messages]


def test_lookups_retry_until_the_record_exists_and_log_each_call_once() -> None:
    source = Generations({"gen-b": 1})
    waits, logs = lookup_logged(source, [{"iteration": 1, "provider_response_id": "gen-a", "latency_ms": 900},
                                         {"iteration": 2, "provider_response_id": "gen-b", "latency_ms": 700}])
    assert waits == [1.0, 2.0] and source.lookups == ["gen-a", "gen-b", "gen-b"]
    assert [(e["event"], e["iteration"], e["provider"]) for e in logs] == [
        ("ai_model_call_provider", 1, "Together"), ("ai_model_call_provider", 2, "Together")]
    assert logs[0]["request_id"] == "req-9" and logs[0]["latency_ms"] == 900


def test_a_record_that_never_appears_or_fails_is_logged_as_not_found() -> None:
    source = Generations({"gen-x": 99, "gen-boom": 99})
    waits, logs = lookup_logged(source, [{"iteration": 1, "provider_response_id": "gen-x"},
                                         {"iteration": 2, "provider_response_id": "gen-boom"}])
    assert waits == [1.0, 2.0, 4.0]
    assert [(e["iteration"], e["provider"], e["lookup"]) for e in logs] == [(1, None, "NOT_FOUND"),
                                                                         (2, None, "NOT_FOUND")]


class RecordingLogger:
    def __init__(self) -> None:
        self.submitted: list[tuple[str, list[dict[str, Any]]]] = []

    def submit(self, request_id: str, calls: list[dict[str, Any]]) -> None:
        self.submitted.append((request_id, calls))

    def close(self) -> None:
        pass


def test_the_run_hands_every_generation_id_to_the_provider_logger_after_responding() -> None:
    agent, _ = orchestrator([tool_call_response("get_system_capabilities", response_id="gen-1"),
                             final_response(ANSWER, response_id="gen-2")])
    agent.provider_logger = RecordingLogger()
    result = agent.run(request())
    assert result.status == "COMPLETED"
    [(request_id, calls)] = agent.provider_logger.submitted
    assert request_id == "req-1"
    assert [(c["iteration"], c["provider_response_id"]) for c in calls] == [(1, "gen-1"), (2, "gen-2")]


def test_the_client_reads_one_generation_record_and_never_raises() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        generation_id = req.url.params["id"]
        if generation_id == "gen-ok":
            return httpx.Response(200, json={"data": generation_record()})
        if generation_id == "gen-net":
            raise httpx.ConnectError("down")
        return httpx.Response(404, json={"error": {"message": "not found"}})

    client = OpenRouterClient("sk-or-test", 30, transport=httpx.MockTransport(handler))
    assert client.generation("gen-ok")["provider_name"] == "Together"
    assert client.generation("gen-missing") is None and client.generation("gen-net") is None
    assert seen[0].url.path == "/api/v1/generation" and seen[0].method == "GET"
    assert seen[0].headers["authorization"] == "Bearer sk-or-test"


# --------------------------------------------------------------- final contract and plan form in the prompt (R2/R4)

def test_the_final_contract_flag_is_off_by_default_and_the_prompt_is_unchanged() -> None:
    assert make_settings().ai_final_contract_in_prompt is False
    assert build_system_prompt(True) == SYSTEM_PROMPT and STRICT_SCHEMA_LINE in SYSTEM_PROMPT
    agent, client = orchestrator([final_response(ANSWER)])
    agent.run(request())
    assert client.payloads[0]["instructions"] == SYSTEM_PROMPT


def test_the_final_contract_replaces_the_schema_line_and_adds_no_numbers() -> None:
    for dataneed, plan in ((False, False), (True, False), (True, True)):
        before = build_system_prompt(False, dataneed, plan, True)
        after = build_system_prompt(False, dataneed, plan, True, final_contract=True)
        assert STRICT_SCHEMA_LINE not in after and "one JSON object and nothing else" in after
        assert numbers(before) == numbers(after)  # numbers in the prompt count as provenance sources
        assert ("research_plan has exactly this form" in after) is plan
    assert RESPONSE_CONTRACT in build_system_prompt(False, True, False, False, final_contract=True)


def test_the_plan_form_names_every_field_and_enum_of_the_research_plan_model() -> None:
    schema = strict_parameters_schema(ResearchPlan)
    form = schema_skeleton(schema)
    experiment = schema["properties"]["experiments"]["items"]
    for name in [*schema["properties"], *experiment["properties"]]:
        assert f'"{name}":' in form
    for value in ("research_plan/v1", "BENJAMINI_HOCHBERG", "OBSERVATIONS"):
        assert f'"{value}"' in form
    assert '"analysis_frequency": string | null' in form and '"holdout_required": boolean' in form
    prompt = build_system_prompt(False, True, True, True, final_contract=True)
    assert form in prompt and PLAN_FIELD_RULES in prompt


def test_with_the_contract_a_json_final_on_a_tool_turn_needs_one_call() -> None:
    agent, client = orchestrator([final_response(ANSWER)], AI_FINAL_CONTRACT_IN_PROMPT="true")
    result, logs = run_logged(agent, request())
    assert result.status == "COMPLETED" and len(client.payloads) == 1 and "tools" in client.payloads[0]
    assert "one JSON object and nothing else" in client.payloads[0]["instructions"]
    assert not [e for e in logs if e["event"] == "ai_final_reask"]


def test_a_prose_draft_is_logged_when_it_is_re_asked_then_forced_to_the_strict_turn() -> None:
    agent, client = orchestrator([final_response("Here is my answer in prose."),
                                  final_response("Still prose."), final_response(ANSWER)])
    result, logs = run_logged(agent, request())
    assert result.status == "COMPLETED" and len(client.payloads) == 3
    reasks = [e for e in logs if e["event"] == "ai_final_reask"]
    assert [(e["iteration"], e["next_turn"], e["looked_like_json"]) for e in reasks] == [
        (1, "SAME_PREFIX", False), (2, "STRICT_SCHEMA", False)]
    assert client.payloads[1]["input"][-1]["content"] == FINALIZE_INSTRUCTION
    assert "tools" not in client.payloads[2] and "text" in client.payloads[2]


def test_gate_rejections_are_logged_with_their_kind_and_outcome() -> None:
    unsupported = {**ANSWER, "answer": "The total is 98765."}
    agent, _ = orchestrator([final_response(unsupported), final_response(unsupported)])
    result, logs = run_logged(agent, request())
    gates = [e for e in logs if e["event"] == "ai_final_gate"]
    assert [(e["iteration"], e["kind"], e["outcome"], e["reason"]) for e in gates] == [
        (1, "PROVENANCE", "REJECTED_FOR_REPAIR", None), (2, "PROVENANCE", "FORCED_LIMITATION", "already_rejected")]
    assert "98765" in gates[0]["detail"] and result.response.response_type == "LIMITATION"


# ------------------------------------------------------------------------------------- catalog summary (R3)

class FakeCatalog:
    """discover and details with the shapes of CatalogTools; counts calls."""

    def __init__(self, tables: int = 4, description: str = "Daily closing prices per stock") -> None:
        self.names = [f"Table_{chr(65 + i)}" for i in range(tables)]
        self.description = description
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.fail = False

    def discover(self, _: Any) -> dict[str, Any]:
        if self.fail:
            raise TimeoutError("catalog timed out")
        self.calls.append(("discover", ()))
        return {"tables": [{"table_name": n, "description": f"{n} description", "grain": "stock x date",
                            "time_column": "date", "entity_column": "symbol",
                            "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": None,
                                        "supported_frequencies": ["DAILY"],
                                        "time_semantics": "exchange trading date"}} for n in self.names],
                "truncated": False, "research_catalog": {"method_count": 7}, "formula_catalog": {"formula_count": 3}}

    def details(self, arguments: Any) -> dict[str, Any]:
        tables = tuple(arguments.table_names)
        self.calls.append(("details", tables))
        sections: dict[str, Any] = {}
        if "COLUMNS" in arguments.sections:
            sections["COLUMNS"] = {"by_table": {t: [
                {"column_name": "close", "data_type": "numeric", "unit": "IDR", "description": self.description},
                {"column_name": "symbol", "data_type": "text", "description": None}] for t in tables}}
        if "RELATIONSHIPS" in arguments.sections:
            sections["RELATIONSHIPS"] = {"entries": [] if "Table_A" not in tables else [
                {"relationship_id": 11, "left_table": tables[0], "left_columns": ["symbol"],
                 "right_table": "Table_Z", "right_columns": ["symbol"], "relationship_type": "MANY_TO_ONE",
                 "temporal_rule": "AS_OF", "safe_output_grain": "stock x date"}]}
        if "COVERAGE" in arguments.sections:
            sections["COVERAGE"] = {"datasets": {t: {"actual_min_date": "2021-01-04", "actual_max_date": "2026-09-25",
                                                     "verification_status": "VERIFIED"} for t in tables}}
        return {"sections": sections}


def test_the_summary_lists_tables_columns_coverage_and_relationships_in_bounded_calls() -> None:
    catalog = FakeCatalog(tables=4)
    text = build_summary(catalog, ["submit_data_need_spec", "discover_catalog"])
    assert text.startswith(HEADER)
    assert "Available tools: discover_catalog, submit_data_need_spec." in text
    assert ("- Table_A: Table_A description; grain stock x date; time column date; entity column symbol; "
            "subject data_domain MARKET, entity_type STOCK, asset_type null; frequencies DAILY; time semantics: "
            "exchange trading date; data 2021-01-04 to 2026-09-25 (VERIFIED). Columns: close (numeric, IDR; Daily "
            "closing prices per stock), symbol (text).") in text
    assert "- 11: Table_A(symbol) -> Table_Z(symbol), MANY_TO_ONE, AS_OF, output grain stock x date." in text
    assert "Documented research methods: 7; documented formulas: 3" in text
    # one COLUMNS call per table, relationships and coverage three tables per call
    assert [c for c in catalog.calls if c[0] == "details"] == [
        ("details", ("Table_A",)), ("details", ("Table_B",)), ("details", ("Table_C",)), ("details", ("Table_D",)),
        ("details", ("Table_A", "Table_B", "Table_C")), ("details", ("Table_D",))]


def test_an_oversized_summary_drops_column_descriptions_then_is_left_out() -> None:
    catalog = FakeCatalog(tables=4, description="x" * 80)
    full = build_summary(catalog, [])
    compact = build_summary(catalog, [], max_chars=len(full) - 1)
    assert "close (numeric, IDR)" in compact and "xxxx" not in compact
    assert build_summary(catalog, [], max_chars=200) == ""


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_stale_summary_is_served_while_it_refreshes_and_a_failure_keeps_the_last_text() -> None:
    catalog, clock, queued, events = FakeCatalog(tables=1), Clock(), [], []
    summary = CatalogSummary(catalog, lambda: ["discover_catalog"], 900, retry_seconds=60, clock=clock,
                             background=queued.append, on_refresh=lambda **f: events.append(f))
    first = summary.text()
    assert "Table_A" in first and events[-1]["ok"] and events[-1]["changed"] and not queued
    clock.now = 100
    assert summary.text() == first and not queued  # fresh: no rebuild
    clock.now = 901
    catalog.names = ["Table_A", "Table_B"]
    assert summary.text() == first and len(queued) == 1  # stale: served while the refresh is queued
    assert summary.text() == first and len(queued) == 1  # one refresh at a time
    queued.pop()()
    assert "Table_B" in summary.text() and events[-1]["changed"]
    clock.now = 2000
    catalog.fail = True
    summary.text()
    queued.pop()()
    assert events[-1] == {"ok": False, "error": "TimeoutError"} and "Table_B" in summary.text()
    clock.now = 2061  # a failed refresh is retried after retry_seconds, not after the TTL
    summary.text()
    assert len(queued) == 1


class FixedSummary:
    def __init__(self, text: str) -> None:
        self.value = text

    def text(self) -> str:
        return self.value


class ChangingSummary:
    """A different text on every call, as if the catalog changed during the run."""

    def __init__(self) -> None:
        self.calls = 0

    def text(self) -> str:
        self.calls += 1
        return f"CATALOG SUMMARY\n- Table_A: data 2021-01-04 to 2026-09-25; 4321 entities (version {self.calls})."


def test_the_summary_is_fixed_per_run_and_its_numbers_are_not_answer_sources() -> None:
    agent, client = orchestrator([tool_call_response("get_system_capabilities"),
                                  final_response({**ANSWER, "answer": "There are 4321 entities."}),
                                  final_response({**ANSWER, "answer": "There are 4321 entities."})])
    agent.catalog_summary = ChangingSummary()
    result = agent.run(request())
    assert len(client.payloads) == 3 and agent.catalog_summary.calls == 1
    assert {p["instructions"] for p in client.payloads} == {
        SYSTEM_PROMPT + "\n\nCATALOG SUMMARY\n- Table_A: data 2021-01-04 to 2026-09-25; 4321 entities (version 1)."}
    # 4321 appears only in the summary, which is documentation: it is not a governed source for an answer
    assert result.response.response_type == "LIMITATION"
    assert any("4321" in value for value in result.execution.number_provenance.unsupported)


def test_without_a_summary_the_instructions_are_the_system_prompt() -> None:
    agent, client = orchestrator([final_response(ANSWER)])
    agent.catalog_summary = FixedSummary("")
    agent.run(request())
    assert client.payloads[0]["instructions"] == SYSTEM_PROMPT


def test_the_summary_flag_needs_the_catalog_database() -> None:
    with pytest.raises(ConfigError, match="CATALOG_DATABASE_URL"):
        make_settings(AI_CATALOG_SUMMARY_IN_PROMPT="true")
    assert make_settings().ai_catalog_summary_in_prompt is False
    assert make_settings().ai_catalog_summary_ttl_seconds == 900
