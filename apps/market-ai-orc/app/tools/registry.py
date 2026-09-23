from __future__ import annotations

import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from ..compaction import dumps


TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_MAX_RESULT_BYTES = 32768


class ToolError(ValueError):
    """Raised by a handler for an expected, model-recoverable failure."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]
    timeout_seconds: float = 10.0
    enabled: bool = True
    max_result_bytes: int | None = None


@dataclass(frozen=True)
class ToolOutcome:
    call_id: str
    name: str
    ok: bool
    output: dict[str, Any]
    error_code: str | None = None


def strict_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive the provider schema from the same model that validates arguments."""
    if model.model_config.get("extra") != "forbid":
        raise ValueError(f"{model.__name__} must set extra='forbid'")
    optional = [name for name, field in model.model_fields.items() if not field.is_required()]
    if optional:
        raise ValueError(
            f"{model.__name__} fields must all be required for strict mode "
            f"(use a nullable type instead of a default): {optional}"
        )
    schema = model.model_json_schema()
    if "$defs" in schema:
        raise ValueError(f"{model.__name__} uses nested models; keep tool arguments flat")
    properties = {
        name: {key: value for key, value in spec.items() if key != "title"}
        for name, spec in schema.get("properties", {}).items()
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def error_outcome(call_id: str, name: str, code: str, message: str) -> ToolOutcome:
    return ToolOutcome(
        call_id=call_id,
        name=name,
        ok=False,
        output={"ok": False, "tool": name, "error": {"code": code, "message": message[:1000]}},
        error_code=code,
    )


class ToolRegistry:
    """Only explicitly registered handlers can run; everything else fails closed."""

    def __init__(self, *, max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._max_result_bytes = max_result_bytes
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="tool")

    def register(self, spec: ToolSpec) -> None:
        if not TOOL_NAME_PATTERN.fullmatch(spec.name):
            raise ValueError(f"Invalid tool name: {spec.name!r}")
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        if spec.timeout_seconds <= 0:
            raise ValueError(f"Tool timeout must be positive: {spec.name}")
        if spec.max_result_bytes is not None and spec.max_result_bytes <= 0:
            raise ValueError(f"Tool result limit must be positive: {spec.name}")
        self._schemas[spec.name] = strict_parameters_schema(spec.arguments_model)
        self._tools[spec.name] = spec

    def names(self) -> list[str]:
        return [name for name, spec in self._tools.items() if spec.enabled]

    def definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": spec.name,
                "description": spec.description,
                "parameters": self._schemas[spec.name],
                "strict": True,
            }
            for spec in self._tools.values()
            if spec.enabled
        ]

    def execute(self, call_id: str, name: str, raw_arguments: Any) -> ToolOutcome:
        spec = self._tools.get(name)
        if spec is None or not spec.enabled:
            return error_outcome(call_id, name, "UNKNOWN_TOOL",
                                 f"Tool {name!r} is not available. Use only the tools provided.")

        try:
            parsed = self._parse_arguments(raw_arguments)
            arguments = spec.arguments_model.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            return error_outcome(call_id, name, "INVALID_ARGUMENTS", self._argument_issue(exc))

        future = self._executor.submit(spec.handler, arguments)
        try:
            result = future.result(timeout=spec.timeout_seconds)
        except FutureTimeout:
            future.cancel()
            return error_outcome(call_id, name, "TOOL_TIMEOUT",
                                 f"Tool {name} exceeded its {spec.timeout_seconds:g}s time limit.")
        except ToolError as exc:
            return error_outcome(call_id, name, "TOOL_ERROR", str(exc))
        except Exception as exc:
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} failed ({type(exc).__name__}).")

        if not isinstance(result, dict):
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} returned a non-object result.")
        output = {"ok": True, "tool": name, "result": result}
        try:
            size = len(dumps(output).encode("utf-8"))
        except (TypeError, ValueError):
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} returned a non-JSON result.")
        limit = spec.max_result_bytes or self._max_result_bytes
        if size > limit:
            return error_outcome(call_id, name, "TOOL_RESULT_TOO_LARGE",
                                 f"Tool {name} result exceeded {limit} bytes.")
        return ToolOutcome(call_id=call_id, name=name, ok=True, output=output)

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _parse_arguments(raw: Any) -> dict[str, Any]:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return {}
        if isinstance(raw, dict):
            return raw
        if not isinstance(raw, str):
            raise ValueError("Tool arguments must be a JSON object")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return value

    @staticmethod
    def _argument_issue(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            details = [
                f"{'.'.join(str(part) for part in item.get('loc') or ()) or 'root'}: "
                f"{item.get('msg', 'invalid value')}"
                for item in exc.errors(include_url=False, include_input=False)[:5]
            ]
            return "Tool arguments failed validation: " + "; ".join(details)
        if isinstance(exc, json.JSONDecodeError):
            return "Tool arguments were not valid JSON. Resend one complete schema-valid call."
        return str(exc)
