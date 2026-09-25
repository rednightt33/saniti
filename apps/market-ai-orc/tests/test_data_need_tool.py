"""submit_data_need_spec: the model-facing DataNeedSpec (scope tree unrolled to depth 4), its contract with the
sandbox's DataNeedValidator, structured argument errors, and the flag that registers it."""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from typing import Any

import httpx
import pytest

from app.tools import build_default_registry
from app.tools.analysis import SandboxClient, current_run_context, run_context
from app.tools.data_need import (DataRequest, Relationship, ResearchGovernance, ScopeNode, SubmitDataNeedSpecArgs,
                                 argument_issues)
from app.tools.registry import strict_parameters_schema
from app.tools.request_data import current_request_id
from conftest import make_settings
from test_analysis_tools import SANDBOX_KEY, sandbox_module

REFERENCE = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)


def ytd_arguments(**overrides: Any) -> dict[str, Any]:
    prices = {"data_request_id": "data_request_1_A", "logical_name": "prices",
              "source_table": "Price_Stock_Indonesia_IDX", "entity_column": "ticker", "time_column": "date",
              "columns": ["ticker", "date", "close", "volume"], "scope": node("ALL"),
              "time_ranges": [{"range_id": "current_ytd", "start": "2026-01-01", "end": "2026-09-25"},
                              {"range_id": "previous_comparable", "start": "2025-01-01", "end": "2025-09-25"}],
              "source_frequency": "1D", "analysis_frequency": "1D", "resample": None,
              "history_buffer": {"value": 1, "unit": "TRADING_OBSERVATIONS"}, "future_buffer": None,
              "ordering": [{"column": "ticker", "direction": "ASC"}, {"column": "date", "direction": "ASC"}],
              "sampling_allowed": False}
    banks = {"data_request_id": "data_request_1_B", "logical_name": "stock_classification",
             "source_table": "IDX_Stock_Universe", "entity_column": "Ticker", "time_column": None,
             "columns": ["Ticker", "Sector", "Industry"], "scope": node("PREDICATE", "Industry", "EQ", "Banks"),
             "time_ranges": [], "source_frequency": "STATIC", "analysis_frequency": "STATIC", "resample": None,
             "history_buffer": None, "future_buffer": None, "ordering": [], "sampling_allowed": False}
    arguments = {"spec_version": "data_need_spec/v1", "request_group_id": "data_request_1", "revision": 1,
                 "mode": "ANALYSIS", "question": "Bandingkan performa YTD saham bank dengan periode sama tahun lalu.",
                 "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"},
                 "data_requests": [prices, banks],
                 "relationships": [{"relationship_id": 2, "left_request_id": "data_request_1_A", "left_column": "ticker",
                                    "right_request_id": "data_request_1_B", "right_column": "Ticker",
                                    "join_type": "INNER", "join_semantics": "CURRENT_STATE", "left_time_column": None,
                                    "right_time_column": None, "as_of_direction": None, "effective_from_column": None,
                                    "effective_to_column": None}],
                 "research_governance": None}
    arguments.update(overrides)
    return arguments


def node(kind: str, column: str | None = None, operator: str | None = None, value: Any = None,
         children: list | None = None, child: dict | None = None) -> dict[str, Any]:
    return {"type": kind, "column": column, "operator": operator, "value": value, "children": children,
            "child": child}


def leaf(column: str, operator: str, value: Any) -> dict[str, Any]:
    return {"type": "PREDICATE", "column": column, "operator": operator, "value": value}


def contract() -> dict[str, Any]:
    """The Governor's catalog contract of the two tables (shape of POST /v1/catalog/contract, migration 20260925_003)."""
    def column(data_type: str, filterable: bool = True, rule: str | None = None) -> dict[str, Any]:
        return {"data_type": data_type, "semantic_type": None, "unit": None, "filter_allowed": filterable,
                "group_by_allowed": filterable, "allowed_aggregations": [], "resample_aggregation": rule}

    def table(name: str, entity: str, time: str | None) -> dict[str, Any]:
        return {"table_name": name, "entity_column": entity, "time_column": time,
                "primary_key_columns": [entity] + ([time] if time else []), "data_domain": "MARKET",
                "entity_type": "STOCK", "asset_type": "IDX_EQUITY",
                "supported_frequencies": ["1D"] if time else ["STATIC"], "catalog_table_sha256": "0" * 64}

    return {"catalog_version": "v1", "subject_metadata": True, "catalog_sha256": "c" * 64,
            "tables": {"Price_Stock_Indonesia_IDX": table("Price_Stock_Indonesia_IDX", "ticker", "date"),
                       "IDX_Stock_Universe": table("IDX_Stock_Universe", "Ticker", None)},
            "columns": {"Price_Stock_Indonesia_IDX": {"ticker": column("text"), "date": column("date"),
                                                      "close": column("numeric", False, "LAST"),
                                                      "volume": column("bigint", False, "SUM")},
                        "IDX_Stock_Universe": {"Ticker": column("text"), "Sector": column("text"),
                                               "Industry": column("text"), "Status": column("text"),
                                               "Country": column("text")}},
            "relationships": [{"relationship_id": 2, "left_table": "Price_Stock_Indonesia_IDX",
                               "left_columns": ["ticker"], "right_table": "IDX_Stock_Universe",
                               "right_columns": ["Ticker"], "relationship_type": "MANY_TO_ONE",
                               "temporal_rule": "Current state", "safe_output_grain": "date x ticker",
                               "requires_preaggregation": False, "is_allowed": True, "version": "v1",
                               "supported_join_semantics": ["CURRENT_STATE"], "left_time_column": None,
                               "right_time_column": None, "effective_from_column": None,
                               "effective_to_column": None}],
            "unknown_tables": []}


def wire(arguments: dict[str, Any]) -> tuple[dict[str, Any], Any]:
    """What the tool sends: the validated model's JSON, research_governance split from the spec."""
    payload = SubmitDataNeedSpecArgs.model_validate(arguments).model_dump(mode="json")
    governance = payload.pop("research_governance")
    return payload, governance


# ---------------------------------------------------------------- contract with the sandbox validator

def test_the_model_facing_fields_equal_the_validator_fields() -> None:
    validator = sandbox_module("data_need")
    governance = sandbox_module("research_governance")
    assert set(SubmitDataNeedSpecArgs.model_fields) - {"research_governance"} == validator.TOP_FIELDS
    assert set(DataRequest.model_fields) == validator.REQUEST_FIELDS
    assert set(Relationship.model_fields) == validator.RELATIONSHIP_FIELDS
    assert set(ResearchGovernance.model_fields) == governance.FIELDS
    operators = ScopeNode.model_fields["operator"].annotation.__args__[0].__args__
    assert tuple(operators) == validator.OPERATORS
    semantics = Relationship.model_fields["join_semantics"].annotation.__args__
    assert tuple(semantics) == validator.JOIN_SEMANTICS
    resample = DataRequest.model_fields["resample"].annotation.__args__[0].__args__
    assert tuple(resample) == tuple(validator.RESAMPLE)
    assert validator.Limits().max_scope_depth == 4  # the unrolled schema has exactly four levels


def test_the_documented_ytd_spec_is_approved_by_the_sandbox_validator() -> None:
    validator = sandbox_module("data_need")
    spec, governance = wire(ytd_arguments())
    assert governance is None
    outcome = validator.validate(spec, contract(), date(2026, 9, 25))
    assert outcome.status == "APPROVED", outcome.issues
    assert outcome.approved["requests"]["data_request_1_A"]["restrictions"][0]["relationship_id"] == 2


def test_a_depth_four_scope_round_trips_and_nulls_are_ignored_by_the_validator() -> None:
    validator = sandbox_module("data_need")
    tree = node("AND", children=[
        node("PREDICATE", "Country", "EQ", "Indonesia"),
        node("OR", children=[
            node("PREDICATE", "Sector", "IN", ["Energy", "Financials"]),
            node("AND", children=[leaf("Industry", "EQ", "Banks"), leaf("Status", "NEQ", "Delisted")])]),
        node("NOT", child=node("PREDICATE", "Status", "EQ", "Delisted"))])
    arguments = ytd_arguments()
    arguments["data_requests"][1]["scope"] = tree
    spec, _ = wire(arguments)
    outcome = validator.validate(spec, contract(), date(2026, 9, 25))
    assert outcome.status == "APPROVED", outcome.issues
    scope = outcome.approved["requests"]["data_request_1_B"]["scope"]
    assert scope["type"] == "AND" and len(scope["children"]) == 3


def test_a_fifth_level_cannot_be_expressed_and_is_reported_as_an_issue() -> None:
    arguments = ytd_arguments()
    deep = node("AND", children=[
        node("OR", children=[
            node("AND", children=[{"type": "OR", "column": None, "operator": None, "value": None,
                                   "children": [leaf("Sector", "EQ", "A"), leaf("Sector", "EQ", "B")], "child": None},
                                  leaf("Sector", "EQ", "C")]),
            node("PREDICATE", "Sector", "EQ", "D")]),
        node("PREDICATE", "Sector", "EQ", "E")])
    arguments["data_requests"][1]["scope"] = deep
    with pytest.raises(Exception) as caught:
        SubmitDataNeedSpecArgs.model_validate(arguments)
    rendered = argument_issues(caught.value, arguments)
    assert rendered["status"] == "REVISION_REQUIRED"
    paths = {i["field_path"] for i in rendered["issues"]}
    assert any(p.startswith("data_requests[1].scope.children[0].children[0].children[0]") for p in paths), paths
    assert {i["data_request_id"] for i in rendered["issues"]} == {"data_request_1_B"}


def test_the_provider_schema_is_strict_and_has_no_references() -> None:
    schema = strict_parameters_schema(SubmitDataNeedSpecArgs)
    text = json.dumps(schema)
    assert "$ref" not in text and "$defs" not in text
    scope = schema["properties"]["data_requests"]["items"]["properties"]["scope"]
    level2 = scope["properties"]["children"]["anyOf"][0]["items"]
    level3 = level2["properties"]["children"]["anyOf"][0]["items"]
    level4 = level3["properties"]["children"]["anyOf"][0]["items"]
    assert level4["properties"]["type"]["enum"] == ["PREDICATE"] and "children" not in level4["properties"]
    assert len(text) < 30000  # the whole tool definition stays small enough for every call's context
    # no calculation vocabulary in the contract
    lowered = text.lower()
    for word in ("formula", "indicator", "calculation\"", "output_grain", "ranking"):
        assert word not in lowered


# ---------------------------------------------------------------- structured argument errors

def test_argument_errors_use_the_validator_issue_shape() -> None:
    arguments = ytd_arguments()
    arguments["data_requests"][0]["columns"] = "close"
    arguments["data_requests"][0]["formula"] = "rsi(close, 14)"
    del arguments["data_requests"][1]["ordering"]
    arguments["relationships"][0]["join_semantics"] = "LATEST"
    with pytest.raises(Exception) as caught:
        SubmitDataNeedSpecArgs.model_validate(arguments)
    rendered = argument_issues(caught.value, arguments)
    issues = {(i["data_request_id"], i["code"], i["field_path"]) for i in rendered["issues"]}
    assert ("data_request_1_A", "INVALID_FIELD_TYPE", "data_requests[0].columns") in issues
    assert ("data_request_1_A", "UNKNOWN_FIELD", "data_requests[0].formula") in issues
    assert ("data_request_1_B", "MISSING_REQUIRED_FIELD", "data_requests[1].ordering") in issues
    assert (None, "INVALID_FIELD_VALUE", "relationships[0].join_semantics") in issues
    for entry in rendered["issues"]:
        assert set(entry) == {"data_request_id", "code", "field_path", "rejected_value"}


def test_a_union_value_error_stops_at_the_field() -> None:
    arguments = ytd_arguments()
    arguments["data_requests"][1]["scope"] = node("PREDICATE", "Industry", "EQ", {"nested": "object"})
    with pytest.raises(Exception) as caught:
        SubmitDataNeedSpecArgs.model_validate(arguments)
    rendered = argument_issues(caught.value, arguments)
    assert {i["field_path"] for i in rendered["issues"]} == {"data_requests[1].scope.value"}
    assert rendered["issues"][0]["rejected_value"] == '{"nested":"object"}'


# ---------------------------------------------------------------- the tool

class FakeSandbox:
    def __init__(self, status: int = 200, body: dict[str, Any] | None = None) -> None:
        self.status = status
        self.body = body or {"status": "APPROVED", "need_id": "need_" + "a" * 24, "issues": [], "warnings": [],
                             "extraction_allowed": True, "next_action": "PREPARE_DATA_BUNDLE"}
        self.calls: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({"path": request.url.path, "body": json.loads(request.content or b"null")})
        return httpx.Response(self.status, json=self.body)


def registry_with(fake: FakeSandbox, enabled: bool = True):
    client = SandboxClient("http://sandbox.test", SANDBOX_KEY, 10, 0, transport=httpx.MockTransport(fake.handler))
    return build_default_registry(sandbox_client=client, dataneed_enabled=enabled)


def call(registry, arguments: Any):
    tokens = (current_request_id.set("run-dn-1"),
              current_run_context.set(run_context(REFERENCE, "Asia/Jakarta", [], "Bandingkan YTD bank")))
    try:
        return registry.execute("call-1", "submit_data_need_spec", arguments)
    finally:
        current_request_id.reset(tokens[0])
        current_run_context.reset(tokens[1])


def test_the_tool_exists_only_behind_the_flag() -> None:
    assert "submit_data_need_spec" not in registry_with(FakeSandbox(), enabled=False).names()
    assert "submit_data_need_spec" in registry_with(FakeSandbox()).names()
    assert make_settings().ai_enable_dataneed is False
    assert make_settings(AI_ENABLE_DATANEED="true").ai_enable_dataneed is True


def test_the_tool_sends_the_spec_with_the_run_reference_and_splits_governance() -> None:
    fake = FakeSandbox()
    governance = {"hypothesis_id": "rsi_candles", "hypothesis": "h", "objective": "o", "candidate_count": 1,
                  "pairwise_comparisons": 0, "holdout": None, "minimum_sample": None,
                  "multiple_testing_policy": "NONE", "followup_of": None}
    outcome = call(registry_with(fake), json.dumps(ytd_arguments(mode="RESEARCH", research_governance=governance)))
    assert outcome.ok and outcome.output["result"]["need_id"] == "need_" + "a" * 24
    sent = fake.calls[0]
    assert sent["path"] == "/v1/data-needs"
    assert sent["body"]["request_id"] == "run-dn-1" and sent["body"]["timezone"] == "Asia/Jakarta"
    assert sent["body"]["reference_time"] == REFERENCE.isoformat()
    assert sent["body"]["research_governance"] == governance
    assert "research_governance" not in sent["body"]["spec"]
    assert sent["body"]["spec"]["data_requests"][1]["scope"]["column"] == "Industry"


def test_an_analysis_spec_sends_no_governance_and_revision_issues_pass_through() -> None:
    issues = [{"data_request_id": "data_request_1_A", "code": "UNKNOWN_COLUMN",
               "field_path": "data_requests[0].columns[3]", "rejected_value": "adj_clsoe"}]
    fake = FakeSandbox(body={"status": "REVISION_REQUIRED", "need_id": None, "issues": issues, "warnings": [],
                             "extraction_allowed": False, "next_action": "REVISE_DATA_NEED_SPEC"})
    outcome = call(registry_with(fake), ytd_arguments())
    assert "research_governance" not in fake.calls[0]["body"]
    assert outcome.ok and outcome.output["result"]["issues"] == issues


def test_invalid_arguments_come_back_as_issues_without_calling_the_sandbox() -> None:
    fake = FakeSandbox()
    arguments = ytd_arguments()
    arguments["data_requests"][0]["columns"] = "close"
    outcome = call(registry_with(fake), arguments)
    assert not outcome.ok and outcome.error_code == "INVALID_ARGUMENTS"
    error = outcome.output["error"]
    assert error["status"] == "REVISION_REQUIRED" and error["next_action"] == "REVISE_DATA_NEED_SPEC"
    assert error["issues"][0]["field_path"] == "data_requests[0].columns"
    assert fake.calls == []


def test_a_sandbox_without_the_flag_is_reported_as_unavailable() -> None:
    outcome = call(registry_with(FakeSandbox(status=404, body={"detail": "Not Found"})), ytd_arguments())
    assert not outcome.ok and outcome.error_code == "TOOL_ERROR"
    assert "unavailable" in outcome.output["error"]["message"]


def test_omitted_nullable_fields_are_filled_before_validation() -> None:
    fake = FakeSandbox()
    arguments = copy.deepcopy(ytd_arguments())
    for key in ("children", "child", "column", "operator", "value"):
        arguments["data_requests"][0]["scope"].pop(key)
    outcome = call(registry_with(fake), arguments)
    assert outcome.ok, outcome.output
    assert fake.calls[0]["body"]["spec"]["data_requests"][0]["scope"]["type"] == "ALL"
