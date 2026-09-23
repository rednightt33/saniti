from __future__ import annotations

import time
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.tools import ToolError, ToolRegistry, ToolSpec, build_default_registry
from app.tools.system import NoArguments


class TickerArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    limit: int | None


def spec(name: str, handler, model: type[BaseModel] = NoArguments, **kwargs: Any) -> ToolSpec:
    return ToolSpec(name=name, description=f"{name} test tool", arguments_model=model, handler=handler, **kwargs)


def test_default_registry_exposes_only_capabilities_tool() -> None:
    registry = build_default_registry()
    assert registry.names() == ["get_system_capabilities"]
    [definition] = registry.definitions()
    assert definition["type"] == "function" and definition["strict"] is True
    assert definition["parameters"] == {
        "type": "object", "properties": {}, "required": [], "additionalProperties": False,
    }


def test_known_tool_executes_with_phase_one_result() -> None:
    outcome = build_default_registry().execute("call_abc", "get_system_capabilities", "{}")
    assert outcome.ok and outcome.call_id == "call_abc" and outcome.name == "get_system_capabilities"
    assert outcome.output == {
        "ok": True,
        "tool": "get_system_capabilities",
        "result": {
            "catalog_discovery": False,
            "full_catalog_read": False,
            "market_data_preview": False,
            "database_query": False,
            "python_analysis": False,
            "web_search": False,
            "available_tools": ["get_system_capabilities"],
        },
    }


@pytest.mark.parametrize("raw", ["", None, {}])
def test_empty_arguments_are_accepted_for_no_argument_tool(raw: Any) -> None:
    assert build_default_registry().execute("c", "get_system_capabilities", raw).ok


def test_unknown_tool_fails_closed() -> None:
    outcome = build_default_registry().execute("call_x", "os.system", '{"cmd": "rm -rf /"}')
    assert not outcome.ok and outcome.error_code == "UNKNOWN_TOOL" and outcome.call_id == "call_x"


def test_disabled_tool_fails_closed() -> None:
    registry = ToolRegistry()
    registry.register(spec("hidden", lambda _args: {"x": 1}, enabled=False))
    assert registry.definitions() == []
    assert registry.execute("c", "hidden", "{}").error_code == "UNKNOWN_TOOL"


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("{not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
    ],
)
def test_invalid_arguments_are_rejected(raw: str, fragment: str) -> None:
    outcome = build_default_registry().execute("c", "get_system_capabilities", raw)
    assert outcome.error_code == "INVALID_ARGUMENTS"
    assert fragment in outcome.output["error"]["message"]


def test_zero_argument_tools_ignore_and_report_placeholder_keys() -> None:
    outcome = build_default_registry().execute("c", "get_system_capabilities", '{"_dummy": 1, "request": "x"}')
    assert outcome.ok and outcome.output["ignored_arguments"] == ["_dummy", "request"]
    assert "ignored_arguments" not in build_default_registry().execute("c", "get_system_capabilities", "{}").output
    strict = ToolRegistry()
    strict.register(spec("lookup", lambda args: {"seen": args.ticker}, model=TickerArguments))
    rejected = strict.execute("c", "lookup", '{"ticker": "BBCA", "unexpected": 1}')
    assert rejected.error_code == "INVALID_ARGUMENTS" and "failed validation" in rejected.output["error"]["message"]


def test_arguments_are_validated_against_the_model() -> None:
    received: list[TickerArguments] = []
    registry = ToolRegistry()
    registry.register(spec("lookup", lambda args: received.append(args) or {"seen": args.ticker},
                           model=TickerArguments))
    assert registry.definitions()[0]["parameters"]["required"] == ["ticker", "limit"]
    assert registry.execute("c1", "lookup", '{"ticker": "BBCA", "limit": null}').ok
    bad = registry.execute("c2", "lookup", '{"ticker": 5, "limit": null}')
    assert bad.error_code == "INVALID_ARGUMENTS" and "ticker" in bad.output["error"]["message"]
    assert len(received) == 1


def test_results_keep_their_call_id() -> None:
    registry = build_default_registry()
    outcomes = [registry.execute(call_id, "get_system_capabilities", "{}") for call_id in ("a", "b")]
    assert [outcome.call_id for outcome in outcomes] == ["a", "b"]


def test_handler_tool_error_is_returned_to_model() -> None:
    def handler(_args):
        raise ToolError("ticker not supported")

    registry = ToolRegistry()
    registry.register(spec("fails", handler))
    outcome = registry.execute("c", "fails", "{}")
    assert outcome.error_code == "TOOL_ERROR" and "ticker not supported" in outcome.output["error"]["message"]


def test_unexpected_handler_error_hides_internal_detail() -> None:
    def handler(_args):
        raise RuntimeError("postgres://user:password@host/db")

    registry = ToolRegistry()
    registry.register(spec("crashes", handler))
    outcome = registry.execute("c", "crashes", "{}")
    assert outcome.error_code == "TOOL_FAILED"
    assert "password" not in outcome.output["error"]["message"]


def test_handler_timeout_is_enforced() -> None:
    registry = ToolRegistry()
    registry.register(spec("slow", lambda _args: time.sleep(1) or {}, timeout_seconds=0.05))
    assert registry.execute("c", "slow", "{}").error_code == "TOOL_TIMEOUT"


def test_oversized_result_is_rejected_not_truncated() -> None:
    registry = ToolRegistry(max_result_bytes=100)
    registry.register(spec("big", lambda _args: {"blob": "x" * 500}))
    assert registry.execute("c", "big", "{}").error_code == "TOOL_RESULT_TOO_LARGE"


def test_non_object_result_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(spec("listy", lambda _args: [1, 2]))
    assert registry.execute("c", "listy", "{}").error_code == "TOOL_FAILED"


class LooseArguments(BaseModel):
    ticker: str


class DefaultedArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = "BBCA"


@pytest.mark.parametrize(
    ("bad_spec", "message"),
    [
        (spec("bad name!", lambda _a: {}), "Invalid tool name"),
        (spec("loose", lambda _a: {}, model=LooseArguments), "extra='forbid'"),
        (spec("defaulted", lambda _a: {}, model=DefaultedArguments), "must all be required"),
        (spec("instant", lambda _a: {}, timeout_seconds=0), "timeout must be positive"),
    ],
)
def test_registration_rejects_unsafe_specs(bad_spec: ToolSpec, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ToolRegistry().register(bad_spec)


def test_duplicate_registration_is_rejected() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError, match="already registered"):
        registry.register(spec("get_system_capabilities", lambda _a: {}))


def test_capabilities_reflect_future_registered_tools() -> None:
    registry = build_default_registry()
    registry.register(spec("request_data", lambda _a: {}))
    result = registry.execute("c", "get_system_capabilities", "{}").output["result"]
    assert result["database_query"] is True
    assert result["python_analysis"] is False
    assert result["available_tools"] == ["get_system_capabilities", "request_data"]
