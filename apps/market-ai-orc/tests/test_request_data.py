"""request_data: strict schema, Governor contract, decision pass-through, and an end-to-end run."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import ConfigError
from app.orchestrator import AgentOrchestrator
from app.schemas import AgentRunRequest
from app.tools import build_default_registry
from app.tools.request_data import DataRequestSpec, GovernorClient
from conftest import ScriptedClient, final_response, make_settings, tool_call_response

GOVERNOR_ROOT = Path(__file__).resolve().parents[2] / "market-sql-governor"
PRICE = "Price_Stock_Indonesia_IDX"


def governor_package():
    """Import apps/market-sql-governor/app as 'governor_app' (both services name their package 'app')."""
    if "governor_app" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "governor_app", GOVERNOR_ROOT / "app/__init__.py", submodule_search_locations=[str(GOVERNOR_ROOT / "app")])
        module = importlib.util.module_from_spec(spec)
        sys.modules["governor_app"] = module
        spec.loader.exec_module(module)
    return sys.modules["governor_app"]


def price_spec(**overrides: Any) -> dict[str, Any]:
    body = {
        "purpose": "20 latest BBCA closes", "from_table": PRICE,
        "columns": [{"table": PRICE, "column": c} for c in ("ticker", "date", "close")], "joins": [],
        "filters": [{"table": PRICE, "column": "ticker", "operator": "EQ", "value": "BBCA"}],
        "group_by": [], "aggregations": [],
        "order_by": [{"table": PRICE, "column": "date", "function": None, "direction": "DESC"}],
        "requested_limit": 20,
    }
    body.update(overrides)
    return body


def mock_governor(response: dict[str, Any] | int, seen: list[dict] | None = None) -> GovernorClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append({"auth": request.headers.get("Authorization"), "body": json.loads(request.content)})
        if isinstance(response, int):
            return httpx.Response(response, json={"detail": "x"})
        return httpx.Response(200, json=response)
    return GovernorClient("http://governor.test", "g" * 40, 5, transport=httpx.MockTransport(handler))


def registry_with(client: GovernorClient):
    return build_default_registry(None, governor_client=client, governor_timeout_seconds=5)


# --- schema ------------------------------------------------------------------------------------------

def test_request_data_schema_is_strict_at_every_level_and_has_no_sql_or_delivery_mode() -> None:
    [definition] = [d for d in registry_with(mock_governor({})).definitions() if d["name"] == "request_data"]
    params = definition["parameters"]
    assert definition["strict"] is True
    assert set(params["properties"]) == {"purpose", "from_table", "columns", "joins", "filters", "group_by",
                                         "aggregations", "order_by", "requested_limit"}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            assert not {"$ref", "$defs", "pattern", "maxLength", "title", "default"} & set(node)
            if node.get("type") == "object":
                assert node["additionalProperties"] is False and node["required"] == list(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(params)
    text = json.dumps(params)
    for forbidden in ("return_as", "delivery_mode", "PARQUET", "\"sql\"", "SQL_MAX"):
        assert forbidden not in text


def test_existing_tool_schemas_use_only_provider_verified_keywords() -> None:
    class Reader:
        def read_only(self):  # pragma: no cover - never called
            raise AssertionError
    allowed = {"type", "properties", "required", "additionalProperties", "items", "anyOf", "enum", "description"}
    registry = build_default_registry(Reader(), governor_client=mock_governor({}))

    def keys(node: Any, inside_properties: bool = False) -> set[str]:
        found: set[str] = set()
        if isinstance(node, dict):
            if not inside_properties:
                found |= set(node)
            for key, value in node.items():
                found |= keys(value, key == "properties")
        elif isinstance(node, list):
            for value in node:
                found |= keys(value)
        return found
    for definition in registry.definitions():
        assert keys(definition["parameters"]) <= allowed, definition["name"]


def test_orc_and_governor_request_specs_are_identical() -> None:
    governor_package()
    governor_spec = importlib.import_module("governor_app.spec")
    assert DataRequestSpec.model_json_schema() == governor_spec.DataRequestSpec.model_json_schema()


@pytest.mark.parametrize(
    "arguments",
    [
        price_spec(sql="SELECT 1"),
        price_spec(return_as="PARQUET"),
        price_spec(delivery_mode="INLINE"),
        price_spec(columns=[{"table": PRICE, "column": "close); DROP TABLE x; --"}]),
        price_spec(from_table="Price\" UNION SELECT"),
        price_spec(filters=[{"table": PRICE, "column": "ticker", "operator": "LIKE", "value": "B%"}]),
        price_spec(joins=[{"table": "Feature_01_Stock_Daily", "relationship_id": None, "on": "a=b"}]),
    ],
)
def test_raw_sql_and_delivery_choices_never_reach_the_governor(arguments) -> None:
    seen: list[dict] = []
    outcome = registry_with(mock_governor({"decision": "INLINE_RESULT", "next_action": "USE_INLINE_RESULT"}, seen)) \
        .execute("c1", "request_data", json.dumps(arguments))
    assert outcome.error_code == "INVALID_ARGUMENTS" and seen == []


# --- pass-through ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("decision", "next_action"),
    [("INLINE_RESULT", "USE_INLINE_RESULT"), ("DATASET_READY", "RUN_ANALYSIS"),
     ("NEEDS_NARROWING", "REVISE_DATA_REQUEST"), ("REJECTED", "STOP_OR_REFORMULATE")],
)
def test_handler_returns_the_governor_decision_unchanged(decision, next_action) -> None:
    body = {"decision": decision, "next_action": next_action, "reason_code": "R", "message": "m",
            "query_id": "qry_1", "details": {"k": 1}}
    seen: list[dict] = []
    outcome = registry_with(mock_governor(body, seen)).execute("c1", "request_data", json.dumps(price_spec()))
    assert outcome.ok and outcome.output["result"] == body
    assert seen[0]["auth"] == "Bearer " + "g" * 40 and set(seen[0]["body"]) == {"request_id", "spec"}
    assert seen[0]["body"]["spec"] == DataRequestSpec.model_validate(price_spec()).model_dump()


@pytest.mark.parametrize("status", [401, 422, 500, 503])
def test_governor_http_errors_are_tool_errors_without_details(status) -> None:
    outcome = registry_with(mock_governor(status)).execute("c1", "request_data", json.dumps(price_spec()))
    assert outcome.error_code == "TOOL_ERROR" and f"HTTP {status}" in outcome.output["error"]["message"]


def test_capability_flag_follows_the_registered_tool() -> None:
    caps = registry_with(mock_governor({})).execute("c", "get_system_capabilities", "{}").output["result"]
    assert caps["database_query"] is True and caps["python_analysis"] is False
    assert "request_data" in caps["available_tools"] and "run_python_analysis" not in caps["available_tools"]
    caps = build_default_registry(None).execute("c", "get_system_capabilities", "{}").output["result"]
    assert caps["database_query"] is False


def test_agent_run_request_id_reaches_the_governor() -> None:
    seen: list[dict] = []
    client = mock_governor({"decision": "INLINE_RESULT", "next_action": "USE_INLINE_RESULT", "rows": [["BBCA"]]}, seen)
    answer = {"response_type": "ANSWER", "answer": "ok", "clarification_question": None, "assumptions": [],
              "limitations": []}
    agent = AgentOrchestrator(make_settings(), ScriptedClient([
        tool_call_response("request_data", json.dumps(price_spec())), final_response(answer)]), registry_with(client))
    result = agent.run(AgentRunRequest(request_id="run-42", message="Ambil 20 latest daily close BBCA."))
    assert result.status == "COMPLETED" and seen[0]["body"]["request_id"] == "run-42"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [({"SQL_GOVERNOR_URL": "ftp://x"}, "http"), ({"SQL_GOVERNOR_URL": "http://g:8080"}, "SQL_GOVERNOR_API_KEY"),
     ({"SQL_GOVERNOR_URL": "http://g:8080", "SQL_GOVERNOR_API_KEY": "short"}, "SQL_GOVERNOR_API_KEY"),
     ({"SQL_GOVERNOR_TIMEOUT_SECONDS": "301"}, "300")],
)
def test_governor_settings_are_validated(overrides, message) -> None:
    with pytest.raises(ConfigError, match=message):
        make_settings(**overrides)


def test_governor_settings_default_to_disabled_and_hide_the_key() -> None:
    settings = make_settings(SQL_GOVERNOR_URL="http://market-sql-governor.railway.internal:8080",
                             SQL_GOVERNOR_API_KEY="s" * 40)
    assert settings.sql_governor_timeout_seconds == 90 and settings.request_data_max_result_bytes == 40000
    assert "s" * 40 not in repr(settings)
    assert make_settings().sql_governor_url is None


# --- end to end: agent loop -> request_data -> real Governor -> PostgreSQL ------------------------------------

ADMIN_URL = os.environ.get("GOVERNOR_TEST_POSTGRES_URL") or os.environ.get("ORC_TEST_POSTGRES_URL", "")


@pytest.fixture(scope="module")
def live_governor(tmp_path_factory):
    if not ADMIN_URL:
        pytest.skip("ORC_TEST_POSTGRES_URL not set")
    governor_package()
    sys.path.insert(0, str(GOVERNOR_ROOT / "tests"))
    try:
        spec = importlib.util.spec_from_file_location("governor_tests_conftest", GOVERNOR_ROOT / "tests/conftest.py")
        governor_conftest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(governor_conftest)
        generator = governor_conftest.governed_db.__wrapped__()
        db = next(generator)
        config = importlib.import_module("governor_app.config")
        governor_module = importlib.import_module("governor_app.governor")
        store_module = importlib.import_module("governor_app.store")
        directory = tmp_path_factory.mktemp("datasets")
        settings = config.Settings.from_env(governor_conftest.base_env(
            GOVERNOR_DATABASE_URL=db["login"], SQL_DATASET_LOCAL_DIR=str(directory)))
        governor = governor_module.Governor(settings, governor_module.Database(settings),
                                            store_module.LocalStore(str(directory)))

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            return httpx.Response(200, json=governor.handle(body["request_id"], body["spec"]).model_dump(mode="json"))
        yield GovernorClient("http://governor.test", "g" * 40, 30, transport=httpx.MockTransport(handler)), directory
        try:
            next(generator)
        except StopIteration:
            pass
    finally:
        sys.path.remove(str(GOVERNOR_ROOT / "tests"))


def test_small_request_returns_inline_rows_to_the_model(live_governor) -> None:
    client, _ = live_governor
    answer = {"response_type": "ANSWER", "answer": "BBCA closes listed.", "clarification_question": None,
              "assumptions": [], "limitations": []}
    scripted = ScriptedClient([tool_call_response("request_data", json.dumps(price_spec())), final_response(answer)])
    result = AgentOrchestrator(make_settings(), scripted, registry_with(client)).run(
        AgentRunRequest(request_id="acc-1", message="Ambil 20 latest daily close BBCA."))
    output = json.loads([i for i in scripted.payloads[1]["input"] if i.get("type") == "function_call_output"][0]["output"])
    assert result.status == "COMPLETED"
    assert output["result"]["decision"] == "INLINE_RESULT" and output["result"]["returned_rows"] == 20
    assert all(row[0] == "BBCA" for row in output["result"]["rows"])


def test_large_request_sends_only_a_dataset_reference_to_the_model(live_governor) -> None:
    client, directory = live_governor
    universe = price_spec(purpose="Price universe for rolling correlation", order_by=[], requested_limit=None,
                          filters=[{"table": PRICE, "column": "date", "operator": "BETWEEN",
                                    "value": ["2025-09-01", "2026-08-31"]}])
    limitation = {"response_type": "LIMITATION", "answer": "The approved dataset is ready.",
                  "clarification_question": None, "assumptions": [],
                  "limitations": ["No analysis tool is available, so rolling correlation was not calculated."]}
    scripted = ScriptedClient([tool_call_response("request_data", json.dumps(universe)), final_response(limitation)])
    result = AgentOrchestrator(make_settings(), scripted, registry_with(client)).run(
        AgentRunRequest(request_id="acc-2", message="Ambil historical price universe IDX untuk rolling correlation."))
    raw = [i for i in scripted.payloads[1]["input"] if i.get("type") == "function_call_output"][0]["output"]
    output = json.loads(raw)["result"]
    assert result.status == "LIMITED"
    assert output["decision"] == "DATASET_READY" and output["next_action"] == "RUN_ANALYSIS"
    assert output["rows"] is None and output["dataset"]["row_count"] > 7000 and len(raw) < 6000
    assert (directory / "datasets" / output["dataset"]["dataset_id"] / "data.parquet").exists()
    assert str(directory) not in raw
