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


ToolEffect = typing.Literal["READS", "OWN_ARTIFACT", "FETCHES_WEB", "FETCHES_DATA", "COMPUTES"]
READ_EFFECTS: frozenset[str] = frozenset({"READS", "OWN_ARTIFACT"})
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
DEFAULT_MAX_RESULT_BYTES = 32768


class ToolError(ValueError):
    """Raised by a handler for an expected, model-recoverable failure. code, when given, replaces the generic
    TOOL_ERROR so the model and the repair ledger see the specific reason."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


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
    # P10 (2026-10-01): the name a model may wrap the whole argument object under ({"data_need_spec": {...}} or the same
    # as JSON text). The object is taken out only when none of the other keys is an argument of the tool, and it is
    # then validated like any call; anything else is refused as before.
    envelope_key: str | None = None
    # O3 (PLAN_BE_OPTIMIZATION_2026-10-04.md): what calling the tool changes. READS changes nothing; OWN_ARTIFACT only
    # writes the conversation's own record (an evidence row, an export file); FETCHES_WEB reads a public web fact (no
    # warehouse data); FETCHES_DATA pulls warehouse data;
    # COMPUTES opens a session or runs code. A read-only step's tools are derived from it (READ_EFFECTS), so a new tool
    # is classed where it is defined. None (unclassed) is never read-only; every production tool is classed (contract
    # test).
    effect: ToolEffect | None = None


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


def _node_at(schema: dict[str, Any], loc: list[str]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(the schema node at a validation location, the object node that holds it)."""
    node, parent = schema, None
    for part in loc:
        objects = _branch(node, "properties") if isinstance(node, dict) else None
        if objects is not None and part in (objects.get("properties") or {}):
            parent, node = objects, objects["properties"][part]
            continue
        items = _branch(node, "items") if isinstance(node, dict) else None
        if items is not None and part.isdigit():
            node = items["items"]
            continue
        return None, None
    return node, parent


def _full_match(pattern: str, value: str) -> bool:
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return False


def _resolved(schema: dict[str, Any], node: Any) -> Any:
    """A pydantic JSON-schema node with its $ref (to $defs) followed."""
    while isinstance(node, dict) and isinstance(node.get("$ref"), str):
        node = (schema.get("$defs") or {}).get(node["$ref"].rsplit("/", 1)[-1])
    return node


def _siblings(model_schema: dict[str, Any], loc: list[str]) -> dict[str, Any]:
    """The pydantic schema properties of the object that holds loc (they keep the patterns the strict schema drops)."""
    node = model_schema
    for part in loc[:-1]:
        node = _resolved(model_schema, node)
        if not isinstance(node, dict):
            return {}
        if part.isdigit():
            node = node.get("items") or next((b.get("items") for b in node.get("anyOf") or []
                                              if isinstance(b, dict) and b.get("items")), None)
        else:
            node = (node.get("properties") or {}).get(part)
            node = next((b for b in (node or {}).get("anyOf") or [] if isinstance(b, dict) and "$ref" in b), node)
    node = _resolved(model_schema, node)
    return (node or {}).get("properties") or {} if isinstance(node, dict) else {}


def _schema_hint(schema: dict[str, Any], loc: list[str], value: Any,
                 model_schema: dict[str, Any] | None = None) -> str:
    """What the schema expects at loc, and a sibling field whose pattern the refused value matches."""
    node, parent = _node_at(schema, loc)
    if not isinstance(node, dict):
        return ""
    types = sorted(t for t in _schema_types(node) if t)
    hints = [f"expected JSON {' or '.join(types)}"] if types else []
    if isinstance(value, str) and types and "string" not in types:
        hints.append("send the value itself, not as text")
    if isinstance(value, str) and model_schema:
        for name, sibling in _siblings(model_schema, loc).items():
            if not isinstance(sibling, dict) or name == (loc[-1] if loc else None):
                continue
            patterns = [branch["pattern"] for branch in [sibling, *(sibling.get("anyOf") or [])]
                        if isinstance(branch, dict) and isinstance(branch.get("pattern"), str)]
            if any(_full_match(pattern, value) for pattern in patterns):
                hints.append(f"this value has the form of {name}: put it in {name}")
    return "; ".join(hints)


_JSON_TYPES = {type(None): "null", bool: "boolean", int: "integer", float: "number", list: "array", dict: "object",
               str: "string"}


def _schema_types(schema: dict[str, Any]) -> set[str]:
    """The JSON types a (strict) schema node allows, through anyOf."""
    if "anyOf" in schema:
        return set().union(*(_schema_types(branch) for branch in schema["anyOf"] if isinstance(branch, dict)))
    kind = schema.get("type")
    return set(kind) if isinstance(kind, list) else {kind} if isinstance(kind, str) else set()


def _fits(value: Any, types: set[str]) -> bool:
    kind = _JSON_TYPES.get(type(value))
    return kind in types or (kind == "integer" and "number" in types)


def _branch(schema: dict[str, Any], key: str) -> dict[str, Any] | None:
    """The object or array branch of a node (the one that has key: properties or items)."""
    if key in schema:
        return schema
    for branch in schema.get("anyOf") or []:
        if isinstance(branch, dict) and key in branch:
            return branch
    return None


def decode_text_values(schema: dict[str, Any], data: Any, path: str = "") -> list[str]:
    """EXEC-W A4 (M122 item 1, user decision 2026-10-08): a value the model wrote as text where the schema expects
    another JSON type ("null", "[\"a\"]", "20") is decoded in place when the decoded value fits that type; the text
    "null" in a nullable field means null (an opaque token or name is never the word null). Derived from each tool's
    schema, so every tool is covered without a list. Returns the decoded paths (reported to the model and logged)."""
    decoded: list[str] = []
    objects = _branch(schema, "properties")
    if isinstance(data, dict) and objects is not None:
        for name, node in (objects.get("properties") or {}).items():
            if name not in data or not isinstance(node, dict):
                continue
            where = f"{path}.{name}" if path else name
            value = data[name]
            types = _schema_types(node)
            if isinstance(value, str) and types and "string" not in types:
                try:
                    candidate = json.loads(value)
                except ValueError:
                    candidate = value
                if candidate is not value and _fits(candidate, types):
                    data[name] = value = candidate
                    decoded.append(where)
            elif isinstance(value, str) and "null" in types and value.strip().casefold() == "null":
                data[name] = value = None
                decoded.append(where)
            decoded += decode_text_values(node, value, where)
    items = _branch(schema, "items")
    if isinstance(data, list) and items is not None and isinstance(items.get("items"), dict):
        for index, item in enumerate(data):
            decoded += decode_text_values(items["items"], item, f"{path}.{index}")
    return decoded


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

    def disable(self, name: str) -> bool:
        """Withdraw a registered tool whose prerequisite turned out inactive at startup; True when it was offered."""
        import dataclasses

        spec = self._tools.get(name)
        if spec is None or not spec.enabled:
            return False
        self._tools[name] = dataclasses.replace(spec, enabled=False)
        return True

    def names(self) -> list[str]:
        return [name for name, spec in self._tools.items() if spec.enabled]

    def effect_of(self, name: str) -> str | None:
        """The effect class of one tool (None when unknown or unclassed)."""
        spec = self._tools.get(name)
        return spec.effect if spec is not None else None

    def names_with_effect(self, effects: frozenset[str] = READ_EFFECTS) -> frozenset[str]:
        """The offered tools whose effect is one of effects (by default the read-only ones)."""
        return frozenset(name for name, spec in self._tools.items() if spec.enabled and spec.effect in effects)

    def get(self, name: str) -> ToolSpec | None:
        """The registered spec of a tool, or None."""
        return self._tools.get(name)

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
        decoded: list[str] = []
        parsed: Any = None
        try:
            parsed = self._parse_arguments(raw_arguments)
            if not spec.arguments_model.model_fields and isinstance(parsed, dict) and parsed:
                # A zero-argument tool cannot be influenced by input. Some models invent a
                # placeholder key (e.g. "request", "_dummy") for empty schemas; rejecting it only
                # burns the tool-call budget, so the keys are ignored and reported back.
                ignored, parsed = sorted(str(key) for key in parsed)[:20], {}
            parsed, unwrapped = self._unwrap(spec, parsed)
            decoded = decode_text_values(self._schemas.get(name) or {}, parsed)
            if decoded:
                logger.info(dumps({"event": "ai_tool_arguments_decoded", "tool": name,
                                   "request_id": _current_request_id(), "paths": decoded[:20]}))
            assumed_null = fill_omitted_nulls(spec.arguments_model, parsed)
            arguments = spec.arguments_model.model_validate(parsed)
        except (ValueError, ValidationError) as exc:
            # Only field paths and error types are logged (never values), so rejections can be diagnosed from logs.
            logger.info(dumps({"event": "ai_tool_arguments_rejected", "tool": name,
                               "request_id": _current_request_id(),
                               "errors": self._argument_locations(exc)}))
            outcome = error_outcome(call_id, name, "INVALID_ARGUMENTS",
                                    self._argument_issue(exc, self._schemas.get(name) or {}, spec.arguments_model))
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
            return error_outcome(call_id, name, exc.code or "TOOL_ERROR", str(exc))
        except Exception as exc:
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} failed ({type(exc).__name__}).")

        if not isinstance(result, dict):
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} returned a non-object result.")
        output = {"ok": True, "tool": name, "result": result}
        if ignored:
            output["ignored_arguments"] = ignored
        if unwrapped:
            output["unwrapped_arguments"] = unwrapped
        if assumed_null:
            output["omitted_fields_set_to_null"] = assumed_null[:20]
        if decoded:
            # EXEC-W A4 (M122): the model learns its text was read as the JSON value the schema expects
            output["text_values_decoded"] = decoded[:20]
        try:
            size = len(dumps(output).encode("utf-8"))
        except (TypeError, ValueError):
            return error_outcome(call_id, name, "TOOL_FAILED", f"Tool {name} returned a non-JSON result.")
        limit = spec.max_result_bytes or self._max_result_bytes
        if size > limit:
            shrunk = self._shrink(output, limit)
            if shrunk is None:
                return error_outcome(call_id, name, "TOOL_RESULT_TOO_LARGE",
                                     f"Tool {name} result exceeded {limit} bytes ({size}); largest parts: "
                                     f"{self._largest(output.get('result'))}.")
            logger.info(dumps({"event": "ai_tool_result_shrunk", "tool": name, "request_id": _current_request_id(),
                               "bytes": size, "limit": limit, "kept_rows": shrunk[1]}))
            output = shrunk[0]
        return ToolOutcome(call_id=call_id, name=name, ok=True, output=output)

    @staticmethod
    def _shrink(output: dict[str, Any], limit: int) -> tuple[dict[str, Any], int] | None:
        """P6 (2026-10-01, ma-steps 2-m4c): complete_research_run exceeded its limit as a whole and the model called it
        again. Table rows inside a result (`rows` next to an `output_id`) are a preview the run can read again page by
        page (get_session_output; value references fetch further pages themselves), so they are cut to fewer rows,
        marked rows_truncated, before the result is refused. Nothing else (findings, statuses, estimates) is cut."""
        def cut(node: Any, keep: int) -> Any:
            if isinstance(node, dict):
                out = {k: cut(v, keep) for k, v in node.items()}
                if node.get("output_id") and isinstance(node.get("rows"), list) and len(node["rows"]) > keep:
                    out["rows"] = node["rows"][:keep]
                    out["rows_truncated"] = True
                    out["read_more"] = "get_session_output"
                return out
            if isinstance(node, list):
                return [cut(v, keep) for v in node]
            return node

        for keep in (20, 5, 0):
            candidate = cut(output, keep)
            if len(dumps(candidate).encode("utf-8")) <= limit:
                return candidate, keep
        return None

    @staticmethod
    def _largest(result: Any) -> str:
        if not isinstance(result, dict):
            return "the result"
        sizes = sorted(((len(dumps(v).encode("utf-8")), k) for k, v in result.items()), reverse=True)[:3]
        return ", ".join(f"{k} {n} bytes" for n, k in sizes)

    def arguments_of(self, name: str, parsed: Any) -> Any:
        """The arguments a tool validates, for a caller that inspects them before the call (an envelope taken out
        exactly as execute does), so a guard never reads a different object than the tool receives."""
        spec = self._tools.get(name)
        return self._unwrap(spec, parsed)[0] if spec is not None else parsed

    @staticmethod
    def _unwrap(spec: ToolSpec, parsed: Any) -> tuple[Any, dict[str, Any] | None]:
        key = spec.envelope_key
        if not key or not isinstance(parsed, dict) or key not in parsed or key in spec.arguments_model.model_fields:
            return parsed, None
        others = sorted(k for k in parsed if k != key)
        if any(k in spec.arguments_model.model_fields for k in others):
            return parsed, None
        inner = parsed[key]
        if isinstance(inner, str):
            try:
                inner = json.loads(inner)
            except ValueError:
                return parsed, None
        if not isinstance(inner, dict):
            return parsed, None
        logger.info(dumps({"event": "ai_tool_arguments_unwrapped", "tool": spec.name,
                           "request_id": _current_request_id(), "envelope": key, "ignored": others[:20]}))
        return inner, {"envelope": key, "ignored": others[:20]}

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
    def _argument_issue(exc: Exception, schema: dict[str, Any] | None = None,
                        model: type[BaseModel] | None = None) -> str:
        """The refusal the model reads. EXEC-W A4 (M122 item 3): each failing field also names, from the tool's
        schema, the JSON type it expects and, for a value written in the form of a sibling field, that field."""
        if isinstance(exc, ValidationError):
            details = []
            for item in exc.errors(include_url=False)[:5]:
                loc = [str(part) for part in item.get("loc") or ()]
                text = f"{'.'.join(loc) or 'root'}: {item.get('msg', 'invalid value')}"
                try:
                    model_schema = model.model_json_schema() if model is not None else None
                except Exception:  # noqa: BLE001 - a hint never hides the refusal
                    model_schema = None
                hint = _schema_hint(schema or {}, loc, item.get("input"), model_schema)
                details.append(text + (f" ({hint})" if hint else ""))
            return "Tool arguments failed validation: " + "; ".join(details)
        if isinstance(exc, json.JSONDecodeError):
            return "Tool arguments were not valid JSON. Resend one complete schema-valid call."
        return str(exc)
