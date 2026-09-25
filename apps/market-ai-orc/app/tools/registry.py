from __future__ import annotations

import contextvars
import copy
import json
import logging
import re
import typing
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
    # Renders an argument error (ValidationError or bad JSON, plus the raw arguments) as structured fields merged into
    # the INVALID_ARGUMENTS error, for tools whose results use their own issue shape (submit_data_need_spec).
    argument_errors: Callable[[Exception, Any], dict[str, Any]] | None = None


@dataclass(frozen=True)
class ToolOutcome:
    call_id: str
    name: str
    ok: bool
    output: dict[str, Any]
    error_code: str | None = None


# Keywords sent to the provider. These are the keywords verified live with OpenRouter strict tools;
# value constraints (pattern, lengths, ranges) are still enforced by the Pydantic model on every call.
# A single-value Literal is written by Pydantic as `const`, which is sent as a one-value `enum` so the model sees the
# only allowed value. The provider does not always enforce the schema, so validation stays authoritative.
PROVIDER_SCHEMA_KEYWORDS = {"type", "properties", "required", "additionalProperties", "items", "anyOf", "enum", "description"}
logger = logging.getLogger("market_ai_orc")


def _provider_schema(node: Any, defs: dict[str, Any], owner: str) -> Any:
    if isinstance(node, list):
        return [_provider_schema(item, defs, owner) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        target = defs[node["$ref"].rsplit("/", 1)[-1]]
        resolved = _provider_schema(target, defs, owner)
        if "description" in node:
            resolved = {**resolved, "description": node["description"]}
        return resolved
    result: dict[str, Any] = {}
    if "const" in node and "enum" not in node:
        result["enum"] = [node["const"]]
    for key, value in node.items():
        if key not in PROVIDER_SCHEMA_KEYWORDS:
            continue
        if key == "properties":
            result[key] = {name: _provider_schema(spec, defs, owner) for name, spec in value.items()}
        elif key in ("items", "anyOf"):
            result[key] = _provider_schema(value, defs, owner)
        else:
            result[key] = value
    if result.get("type") == "object" and "properties" in result:
        if node.get("additionalProperties") is not False:
            raise ValueError(f"{owner}: every nested model must set extra='forbid'")
        if set(node.get("required", [])) != set(result["properties"]):
            raise ValueError(f"{owner}: every nested model field must be required (use a nullable type)")
        result["required"] = list(result["properties"])
    return result


def strict_parameters_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Derive the provider schema from the same model that validates arguments.

    Nested models are inlined and must follow the same strict rules (extra='forbid', every
    field required). Only structural keywords reach the provider.
    """
    if model.model_config.get("extra") != "forbid":
        raise ValueError(f"{model.__name__} must set extra='forbid'")
    optional = [name for name, field in model.model_fields.items() if not field.is_required()]
    if optional:
        raise ValueError(
            f"{model.__name__} fields must all be required for strict mode "
            f"(use a nullable type instead of a default): {optional}"
        )
    schema = model.model_json_schema()
    defs = schema.get("$defs", {})
    properties = {
        name: _provider_schema(spec, defs, model.__name__)
        for name, spec in schema.get("properties", {}).items()
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _nullable(annotation: Any) -> bool:
    return any(arg is type(None) for arg in typing.get_args(annotation))


def _models_in(annotation: Any) -> list[type[BaseModel]]:
    """Pydantic models reachable in an annotation (Optional[X], list[X], X | None, Annotated[...])."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    found: list[type[BaseModel]] = []
    for arg in typing.get_args(annotation):
        found.extend(_models_in(arg))
    return found


def fill_omitted_nulls(model: type[BaseModel], data: Any, path: str = "") -> list[str]:
    """Strict tool schemas require every field, but a provider that does not enforce the schema lets the model omit
    nullable ones. An omitted nullable field means null, so it is set to null (reported back to the model); a missing
    non-nullable field is still a validation error. Returns the filled paths."""
    if not isinstance(data, dict):
        return []
    filled: list[str] = []
    for name, field in model.model_fields.items():
        where = f"{path}.{name}" if path else name
        if name not in data:
            if field.is_required() and _nullable(field.annotation):
                data[name] = None
                filled.append(where)
            continue
        nested = _models_in(field.annotation)
        if len(nested) != 1:
            continue
        value = data[name]
        if isinstance(value, dict):
            filled += fill_omitted_nulls(nested[0], value, where)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                filled += fill_omitted_nulls(nested[0], item, f"{where}.{index}")
    return filled


def _current_request_id() -> str | None:
    try:
        from .request_data import current_request_id

        return current_request_id.get()
    except (ImportError, LookupError):
        return None


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

        ignored: list[str] = []
        assumed_null: list[str] = []
        parsed: Any = None
        try:
            parsed = self._parse_arguments(raw_arguments)
            if not spec.arguments_model.model_fields and isinstance(parsed, dict) and parsed:
                # A zero-argument tool cannot be influenced by input. Some models invent a
                # placeholder key (e.g. "request", "_dummy") for empty schemas; rejecting it only
                # burns the tool-call budget, so the keys are ignored and reported back.
                ignored, parsed = sorted(str(key) for key in parsed)[:20], {}
            assumed_null = fill_omitted_nulls(spec.arguments_model, parsed)
            arguments = spec.arguments_model.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            # Only field paths and error types are logged (never values), so rejections can be diagnosed from logs.
            logger.info(dumps({"event": "ai_tool_arguments_rejected", "tool": name,
                               "request_id": _current_request_id(),
                               "errors": self._argument_locations(exc)}))
            outcome = error_outcome(call_id, name, "INVALID_ARGUMENTS", self._argument_issue(exc))
            if spec.argument_errors is not None:
                try:
                    outcome.output["error"].update(spec.argument_errors(exc, parsed))
                except Exception:  # the plain message stays; a renderer bug never hides the rejection
                    pass
            return outcome

        future = self._executor.submit(contextvars.copy_context().run, spec.handler, arguments)
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
        if ignored:
            output["ignored_arguments"] = ignored
        if assumed_null:
            output["omitted_fields_set_to_null"] = assumed_null[:20]
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
            return copy.deepcopy(raw)  # omitted nullable fields are filled in place; never mutate the caller's object
        if not isinstance(raw, str):
            raise ValueError("Tool arguments must be a JSON object")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("Tool arguments must be a JSON object")
        return value

    @staticmethod
    def _argument_locations(exc: Exception) -> list[dict[str, str]]:
        if isinstance(exc, ValidationError):
            return [{"loc": ".".join(str(part) for part in item.get("loc") or ()) or "root",
                     "type": str(item.get("type") or "")}
                    for item in exc.errors(include_url=False, include_input=False)[:10]]
        return [{"loc": "root", "type": type(exc).__name__}]

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
