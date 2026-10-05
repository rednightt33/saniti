"""The catalog discovery protocol (AI_ENABLE_CATALOG_PROTOCOL, implementation plan 2026-09-27, phase C3): the prompt
rule, reuse of successful catalog results within a run, and the metadata guard before submit_data_need_spec."""
from __future__ import annotations

from app.orchestrator import markdown_prompt  # noqa: E402 - prompt audit C (2026-10-05)

import json
import logging
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.catalog_protocol import CatalogLedger, cache_key, gaps, record
from app.config import ConfigError
from app.orchestrator import CATALOG_PROTOCOL_RULES, AgentOrchestrator, build_system_prompt
from app.provenance import parse_numbers
from app.research_plan import guard_research_submission
from app.schemas import AgentRunRequest
from app.tools import ToolRegistry, ToolSpec
from app.tools.catalog import CatalogDetailsArgumentsV2, DiscoverArguments
from app.tools.catalog_rows import ReadCatalogRowsArguments
from app.tools.data_need import SubmitDataNeedSpecArgs
from app.tools.registry import ToolError
from conftest import ScriptedClient, final_response, make_settings, tool_call_response
from test_orchestrator import ListHandler

ON = {"AI_ENABLE_DATANEED": "true", "AI_ENABLE_CATALOG_DISCOVERY_V2": "true", "AI_ENABLE_CATALOG_PROTOCOL": "true",
      "AI_MAX_TOOL_ITERATIONS": "20", "AI_MAX_TOOL_CALLS": "20"}
LIMITATION = {"response_type": "LIMITATION", "answer": "Not answered in this test.", "clarification_question": None,
              "assumptions": [], "limitations": ["test"]}


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class Counting:
    """Catalog and data-need handlers with fixed results; counts every real execution."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.fail_details_once = False

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def discover(self, _: BaseModel) -> dict[str, Any]:
        self._count("discover_catalog")
        return {"tables": [{"table_name": "Price_Stock_Indonesia_IDX", "time_column": "date", "entity_column": "ticker",
                            "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"}}],
                "has_more": False}

    def details(self, arguments: BaseModel) -> dict[str, Any]:
        self._count("get_catalog_details")
        if self.fail_details_once:
            self.fail_details_once = False
            raise ToolError("catalog timed out")
        tables = list(getattr(arguments, "table_names", []) or [])
        sections = list(getattr(arguments, "sections", []) or [])
        result: dict[str, Any] = {"tables": tables, "sections": {}, "table_metadata": {
            t: {"time_column": "date", "entity_column": "ticker", "subject": {"data_domain": "MARKET"}} for t in tables}}
        if "COLUMNS" in sections:
            result["sections"]["COLUMNS"] = {"by_table": {t: [
                {"column_name": "close", "filter_allowed": True}, {"column_name": "volume", "filter_allowed": True},
                {"column_name": "date"}, {"column_name": "ticker"}] for t in tables}}
        if "RELATIONSHIPS" in sections:
            result["sections"]["RELATIONSHIPS"] = {"entries": [{"relationship_id": 7}]}
        return result

    def rows(self, _: BaseModel) -> dict[str, Any]:
        self._count("read_catalog_rows")
        return {"catalog_name": "AI_column_catalog", "columns": [{"name": "table_name"}, {"name": "column_name"}],
                "rows": [["Price_Stock_Indonesia_IDX", "high"]], "has_more": False}

    def submit(self, arguments: BaseModel) -> dict[str, Any]:
        self._count("submit_data_need_spec")
        if getattr(arguments, "mode", None) == "RESEARCH":  # what the real handler does first
            refused = guard_research_submission(None)
            if refused is not None:
                return refused
        return {"status": "REVISION_REQUIRED", "issues": []}


def registry(handlers: Counting) -> ToolRegistry:
    reg = ToolRegistry()
    for name, handler, model in (("discover_catalog", handlers.discover, DiscoverArguments),
                                 ("get_catalog_details", handlers.details, CatalogDetailsArgumentsV2),
                                 ("read_catalog_rows", handlers.rows, ReadCatalogRowsArguments),
                                 ("submit_data_need_spec", handlers.submit, SubmitDataNeedSpecArgs)):
        reg.register(ToolSpec(name=name, description=name, arguments_model=model, handler=handler))
    return reg


def spec(columns=("close",), scope_column=None, ordering=None, relationship=False) -> dict[str, Any]:
    scope = {"type": "ALL", "column": None, "operator": None, "value": None, "children": None, "child": None} \
        if scope_column is None else {"type": "PREDICATE", "column": scope_column, "operator": "EQ", "value": "BBCA",
                                      "children": None, "child": None}
    requests = [{"data_request_id": "data_request_1_A", "logical_name": "prices",
                 "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker", "time_column": "date",
                 "columns": list(columns), "scope": scope,
                 "time_ranges": [{"range_id": "sep", "start": "2026-09-01", "end": "2026-09-25"}],
                 "source_frequency": "1D", "analysis_frequency": "1D", "resample": None, "history_buffer": None,
                 "future_buffer": None,
                 "ordering": [{"column": ordering, "direction": "ASC"}] if ordering else [],
                 "sampling_allowed": False}]
    relationships = [{"relationship_id": 7, "left_request_id": "data_request_1_A", "left_column": "ticker",
                      "right_request_id": "data_request_1_A", "right_column": "ticker", "join_type": "LEFT",
                      "join_semantics": "EXACT_DATE", "left_time_column": "date", "right_time_column": "date",
                      "as_of_direction": None, "effective_from_column": None, "effective_to_column": None}] \
        if relationship else []
    return {"spec_version": "data_need_spec/v1", "request_group_id": "data_request_1", "revision": 1,
            "mode": "ANALYSIS", "question": "q", "subject": {"data_domain": "MARKET", "entity_type": "STOCK",
                                                            "asset_type": "IDX_EQUITY"},
            "data_requests": requests, "relationships": relationships, "research_governance": None}


def call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return tool_call_response(name, json.dumps(arguments), call_id=call_id, response_id=f"resp_{call_id}")


def run(script: list, handlers: Counting | None = None, final: dict[str, Any] | None = None, **env: str):
    handlers = handlers or Counting()
    client = ScriptedClient(script + [final_response(final or LIMITATION)])
    agent = AgentOrchestrator(make_settings(**{**ON, **env}), client, registry(handlers))
    service_logger = logging.getLogger("market_ai_orc")
    handler, previous = ListHandler(), service_logger.level
    service_logger.addHandler(handler)
    service_logger.setLevel(logging.INFO)
    try:
        result = agent.run(AgentRunRequest(request_id="run-1", message="Berapa close BBCA?"))
    finally:
        service_logger.removeHandler(handler)
        service_logger.setLevel(previous)
    outputs = [json.loads(item["output"]) for item in client.payloads[-1]["input"]
               if item.get("type") == "function_call_output"]
    return result, handlers, outputs, [json.loads(m) for m in handler.messages], client


DETAILS = {"table_names": ["Price_Stock_Indonesia_IDX"], "sections": ["COLUMNS", "COVERAGE"], "column_names": None,
           "entity_ids": None}


# ------------------------------------------------------------------------------------------------ config and prompt

def test_the_protocol_needs_discovery_v2_and_the_dataneed_flow() -> None:
    with pytest.raises(ConfigError, match="AI_ENABLE_CATALOG_DISCOVERY_V2"):
        make_settings(AI_ENABLE_CATALOG_PROTOCOL="true")
    settings = make_settings(AI_ENABLE_CATALOG_DISCOVERY_V2="true", AI_ENABLE_CATALOG_PROTOCOL="true")
    agent = AgentOrchestrator(settings, ScriptedClient([]), ToolRegistry())
    assert agent.catalog_protocol is False and "CATALOG DISCOVERY PROTOCOL" not in agent.system_prompt


def test_the_prompt_rule_is_fixed_size_lists_no_tables_and_adds_no_numbers() -> None:
    def numbers(text: str) -> list[float]:
        return sorted(v for shown in parse_numbers(text) for v, _ in shown.candidates)

    without = build_system_prompt(False, True, True, True, True)
    with_rule = build_system_prompt(False, True, True, True, True, catalog_protocol=True)
    assert markdown_prompt(CATALOG_PROTOCOL_RULES) in with_rule
    assert numbers(with_rule) == numbers(without)
    assert "Price_Stock" not in CATALOG_PROTOCOL_RULES and "IDX_" not in CATALOG_PROTOCOL_RULES
    assert build_system_prompt(False, True) == build_system_prompt(False, True, catalog_protocol=False)


# ---------------------------------------------------------------------------------------------------- result reuse

def test_an_identical_catalog_call_reuses_the_result_but_still_counts_and_stays_bounded() -> None:
    reordered = {**DETAILS, "sections": ["COVERAGE", "COLUMNS"], "entity_ids": None, "formula_query": None}
    result, handlers, outputs, logs, _ = run([call("get_catalog_details", DETAILS, "c1"),
                                              call("get_catalog_details", reordered, "c2"),
                                              call("get_catalog_details", DETAILS, "c3"),
                                              call("get_catalog_details", DETAILS, "c4")])
    assert handlers.calls["get_catalog_details"] == 1  # one database read for four calls
    assert "cache_hit" not in outputs[0] and outputs[1]["cache_hit"] is True and outputs[2]["cache_hit"] is True
    assert outputs[1]["result"] == outputs[0]["result"]
    assert outputs[3]["error"]["code"] == "REPEATED_TOOL_CALL"  # the repeat guard still bounds identical calls
    assert result.execution.tool_call_count == 4
    usage = next(e for e in logs if e["event"] == "ai_catalog_usage")
    assert usage["calls"] == {"get_catalog_details": 3} and usage["cache_hits"] == 2 and usage["catalog_queries"] == 1


def test_different_filters_or_sections_are_never_merged_and_errors_are_not_cached() -> None:
    handlers = Counting()
    handlers.fail_details_once = True
    _, handlers, outputs, _, _ = run([call("get_catalog_details", DETAILS, "c1"),
                                      call("get_catalog_details", DETAILS, "c2"),
                                      call("get_catalog_details", {**DETAILS, "sections": ["COLUMNS"]}, "c3")],
                                     handlers)
    assert outputs[0]["ok"] is False and outputs[1]["ok"] is True and "cache_hit" not in outputs[1]
    assert "cache_hit" not in outputs[2] and handlers.calls["get_catalog_details"] == 3


def test_cache_keys_ignore_order_whitespace_and_nulls_only() -> None:
    assert cache_key("x", {"table_names": ["B", "A"], "query": " bank  stocks ", "cursor": None}) == \
        cache_key("x", {"table_names": ["A", "B"], "query": "bank stocks"})
    assert cache_key("x", {"table_names": ["A"]}) != cache_key("x", {"table_names": ["A"], "query": "bank"})
    assert cache_key("x", {"sections": ["COLUMNS"]}) != cache_key("y", {"sections": ["COLUMNS"]})


# -------------------------------------------------------------------------------------------------- metadata guard

def test_a_data_need_on_unread_metadata_is_refused_before_the_sandbox_with_the_call_to_make() -> None:
    _, handlers, outputs, logs, _ = run([call("submit_data_need_spec", spec(), "c1")])
    error = outputs[0]["error"]
    assert error["code"] == "CATALOG_DETAILS_REQUIRED" and "submit_data_need_spec" not in handlers.calls
    assert error["missing"] == [{"table": "Price_Stock_Indonesia_IDX",
                                 "needs": ["table contract (subject, grain, time and entity columns)"],
                                 "columns": ["close", "date", "ticker"]}]  # time/entity columns unread too
    assert error["suggested_calls"] == [{"tool": "get_catalog_details", "arguments": {
        "table_names": ["Price_Stock_Indonesia_IDX"], "sections": ["COLUMNS"], "column_names": None,
        "entity_ids": None}}]
    assert any(e["event"] == "catalog_details_required" for e in logs)


def test_after_the_details_call_the_same_data_need_reaches_the_validator() -> None:
    _, handlers, outputs, _, _ = run([call("get_catalog_details", DETAILS, "c1"),
                                      call("submit_data_need_spec", spec(columns=("close", "volume"),
                                                                         scope_column="ticker", ordering="date"),
                                           "c2")])
    assert outputs[1]["ok"] is True and handlers.calls["submit_data_need_spec"] == 1


def test_scope_and_ordering_columns_and_relationships_must_be_read_too() -> None:
    _, _, outputs, _, _ = run([
        call("get_catalog_details", DETAILS, "c1"),
        call("submit_data_need_spec", spec(scope_column="board", ordering="high", relationship=True), "c2")])
    error = outputs[1]["error"]
    assert error["missing"] == [{"table": "Price_Stock_Indonesia_IDX", "columns": ["board", "high"]}]
    assert error["missing_relationship_ids"] == [7]
    assert error["suggested_calls"][0]["arguments"]["sections"] == ["COLUMNS", "RELATIONSHIPS"]
    assert error["suggested_calls"][0]["arguments"]["column_names"] == ["board", "high"]


def test_exact_catalog_rows_count_as_metadata_read() -> None:
    ledger = CatalogLedger()
    record(ledger, "discover_catalog", Counting().discover(Loose()))
    record(ledger, "read_catalog_rows", Counting().rows(Loose()))
    assert gaps(ledger, spec(columns=("high",))) is None
    assert gaps(ledger, spec(columns=("high", "low")))["tables"][0]["columns"] == ["low"]


def test_the_research_plan_refusal_comes_before_the_catalog_guard() -> None:
    plan_on = {"AI_REQUIRE_RESEARCH_PLAN_CONFIRMATION": "true", "AI_RESEARCH_PLAN_SIGNING_KEY": "0123456789abcdef" * 4}
    final = {**LIMITATION, "research_plan": None}
    _, handlers, outputs, logs, _ = run([call("submit_data_need_spec", {**spec(), "mode": "RESEARCH"}, "c1"),
                                         call("submit_data_need_spec", {**spec(), "revision": 2}, "c2")],
                                        final=final, **plan_on)
    # RESEARCH without an approved plan: the tool's plan guard answers, the model is not sent to read the catalog
    assert outputs[0]["result"]["error"]["code"] == "RESEARCH_PLAN_REQUIRED"
    assert handlers.calls["submit_data_need_spec"] == 1
    # ANALYSIS is not subject to the plan guard, so the catalog guard still applies
    assert outputs[1]["error"]["code"] == "CATALOG_DETAILS_REQUIRED"
    assert [e["tables"] for e in logs if e["event"] == "catalog_details_required"] == [["Price_Stock_Indonesia_IDX"]]


def test_repeated_refusals_are_bounded_by_the_repair_budget() -> None:
    _, _, outputs, _, _ = run([call("submit_data_need_spec", {**spec(), "revision": n}, f"c{n}") for n in range(1, 5)],
                              AI_MAX_REPAIR_ATTEMPTS="2")
    assert [o["error"]["code"] for o in outputs] == ["CATALOG_DETAILS_REQUIRED", "CATALOG_DETAILS_REQUIRED",
                                                    "REPAIR_BUDGET_EXHAUSTED", "REPAIR_BUDGET_EXHAUSTED"]


def test_without_the_protocol_nothing_is_cached_or_guarded() -> None:
    _, handlers, outputs, logs, client = run([call("get_catalog_details", DETAILS, "c1"),
                                              call("get_catalog_details", DETAILS, "c2"),
                                              call("submit_data_need_spec", spec(), "c3")],
                                             AI_ENABLE_CATALOG_PROTOCOL="false")
    assert handlers.calls == {"get_catalog_details": 2, "submit_data_need_spec": 1}
    assert all("cache_hit" not in o for o in outputs)
    assert not [e for e in logs if e["event"] == "ai_catalog_usage"]
    assert "CATALOG DISCOVERY PROTOCOL" not in client.payloads[0]["instructions"]
