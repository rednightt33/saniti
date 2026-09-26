"""DataNeedSpec (data_need_spec/v1) and the DataNeedValidator.

A DataNeedSpec says only which data an answer needs: logical data requests (source table, columns, database scope,
time ranges, frequencies, buffers, ordering) and the catalog relationships between them. It has no formula,
calculation, indicator, method, ranking or output grain: all analytical logic is written later in the sandbox.

The validator checks technical validity only, in four layers, and never guesses a correction:

1. schema: required fields, types, identifier formats, duplicates, limits, unique range ids;
2. catalog binding: table, columns, subject, entity and time columns, filter columns, frequencies, join semantics;
3. cross-request: relationships, join keys, referenced request ids, temporal-join columns, restriction chains;
4. planning feasibility: time ranges, buffers, resampling, ordering, sampling policy, translatability.

Statuses are APPROVED, REVISION_REQUIRED and CATALOG_UNAVAILABLE only; clarification is the orchestrator's decision
before a spec is written. Every issue names the data_request_id, a stable code, the field path and the rejected
value; there are no catalog candidates or suggested replacements.

Codes are those of the architecture document, plus UNSUPPORTED_SPEC_VERSION, INVALID_FIELD_TYPE, INVALID_FIELD_VALUE,
UNKNOWN_FIELD, TOO_MANY_ITEMS (schema errors the document names without a code), REVISION_CONFLICT (revision
sequencing) and MODE_MISMATCH (a research-governance request that does not match the mode).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

SPEC_VERSION = "data_need_spec/v1"
GROUP_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
REQUEST_SUFFIX = re.compile(r"^[A-Za-z0-9]{1,12}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
TABLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$")
FREQUENCY = re.compile(r"^(STATIC|([1-9][0-9]{0,2})(MIN|H|D|W|M|Q|Y))$")
IDENT = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MODES = ("ANALYSIS", "RESEARCH")
OPERATORS = ("EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "NOT_IN", "BETWEEN", "IS_NULL", "IS_NOT_NULL")
ORDERED_OPERATORS = ("GT", "GTE", "LT", "LTE", "BETWEEN")
NODE_TYPES = ("ALL", "PREDICATE", "AND", "OR", "NOT")
JOIN_TYPES = ("INNER", "LEFT")
JOIN_SEMANTICS = ("CURRENT_STATE", "EXACT_DATE", "AS_OF", "EFFECTIVE_DATED")
AS_OF_DIRECTIONS = ("BACKWARD",)
BUFFER_UNITS = ("TRADING_OBSERVATIONS", "CALENDAR_DAYS")
RESAMPLE = {"DAILY": "1D", "WEEKLY": "1W", "MONTHLY": "1M", "QUARTERLY": "1Q", "YEARLY": "1Y"}
DIRECTIONS = ("ASC", "DESC")
UNIT_MINUTES = {"MIN": 1, "H": 60, "D": 1440, "W": 10080, "M": 43200, "Q": 129600, "Y": 525600}
NUMERIC = ("smallint", "integer", "bigint", "numeric", "real", "double precision")

TOP_FIELDS = {"spec_version", "request_group_id", "revision", "mode", "question", "subject", "data_requests",
              "relationships"}
SUBJECT_FIELDS = {"data_domain", "entity_type", "asset_type"}
REQUEST_FIELDS = {"data_request_id", "logical_name", "source_table", "entity_column", "time_column", "columns", "scope",
                  "time_ranges", "source_frequency", "analysis_frequency", "resample", "history_buffer",
                  "future_buffer", "ordering", "sampling_allowed"}
RANGE_FIELDS = {"range_id", "start", "end"}
BUFFER_FIELDS = {"value", "unit"}
ORDER_FIELDS = {"column", "direction"}
RELATIONSHIP_FIELDS = {"relationship_id", "left_request_id", "left_column", "right_request_id", "right_column",
                       "join_type", "join_semantics", "left_time_column", "right_time_column", "as_of_direction",
                       "effective_from_column", "effective_to_column"}
NULLABLE_RELATIONSHIP = {"left_time_column", "right_time_column", "as_of_direction", "effective_from_column",
                         "effective_to_column"}


@dataclass(frozen=True)
class Limits:
    max_requests: int = 8
    max_relationships: int = 8
    max_columns: int = 50
    max_ranges: int = 12
    max_scope_depth: int = 4
    max_scope_nodes: int = 40
    max_in_values: int = 500
    max_range_days: int = 7305
    max_buffer_observations: int = 5000
    max_buffer_days: int = 3660
    max_ordering: int = 6
    max_question_chars: int = 2000


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_value(value: Any) -> str:
    """Must equal apps/market-sql-governor/app/catalog_contract.py canonical_value (a contract test compares them)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value)).normalize()
        text = format(number, "f")
        return "0" if text in ("-0", "") else text
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def calendar_days_for(observations: int) -> int:
    """Conservative calendar span holding N trading observations (weekends, ~10% holidays, a fixed margin); the same
    rule the Analysis Spec warm-up used, so buffers behave as before."""
    return 0 if observations <= 0 else math.ceil(observations * 7 / 5 * 1.1) + 10


def buffer_days(buffer: dict[str, Any] | None) -> int:
    if not buffer:
        return 0
    return calendar_days_for(int(buffer["value"])) if buffer["unit"] == "TRADING_OBSERVATIONS" else int(buffer["value"])


def frequency_minutes(value: str) -> int | None:
    match = FREQUENCY.fullmatch(value or "")
    if not match or value == "STATIC":
        return None
    return int(match.group(2)) * UNIT_MINUTES[match.group(3)]


class Issues:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, request_id: str | None, code: str, path: str, value: Any) -> None:
        if isinstance(value, (dict, list)):
            rendered = canonical_json(value)
            value = rendered if len(rendered) <= 200 else rendered[:197] + "..."
        elif isinstance(value, str) and len(value) > 200:
            value = value[:197] + "..."
        entry = {"data_request_id": request_id, "code": code, "field_path": path, "rejected_value": value}
        if entry not in self.items:
            self.items.append(entry)

    def __bool__(self) -> bool:
        return bool(self.items)


# ---------------------------------------------------------------------------------------------- layer 1: schema

def _fields(obj: dict[str, Any], allowed: set[str], nullable: set[str], path: str, rid: str | None,
            issues: Issues) -> bool:
    ok = True
    for key in obj:
        if key not in allowed:
            issues.add(rid, "UNKNOWN_FIELD", f"{path}.{key}" if path else key, obj[key])
            ok = False
    for key in sorted(allowed - nullable):
        if key not in obj:
            issues.add(rid, "MISSING_REQUIRED_FIELD", f"{path}.{key}" if path else key, None)
            ok = False
    return ok


def _string(value: Any, path: str, rid: str | None, issues: Issues, *, required: bool = True) -> bool:
    if value is None and not required:
        return True
    if not isinstance(value, str) or not value.strip():
        issues.add(rid, "MISSING_REQUIRED_FIELD" if value in (None, "") else "INVALID_FIELD_TYPE", path, value)
        return False
    return True


def _scope_schema(node: Any, path: str, rid: str, depth: int, limits: Limits, issues: Issues,
                  counter: list[int]) -> None:
    counter[0] += 1
    if depth > limits.max_scope_depth:
        issues.add(rid, "INVALID_SCOPE", path, f"depth exceeds {limits.max_scope_depth}")
        return
    if not isinstance(node, dict) or node.get("type") not in NODE_TYPES:
        issues.add(rid, "INVALID_SCOPE", f"{path}.type" if isinstance(node, dict) else path,
                   node.get("type") if isinstance(node, dict) else node)
        return
    kind = node["type"]
    allowed = {"ALL": {"type"}, "PREDICATE": {"type", "column", "operator", "value"},
               "AND": {"type", "children"}, "OR": {"type", "children"}, "NOT": {"type", "child"}}[kind]
    present = {k for k, v in node.items() if v is not None}
    extra = present - allowed
    if extra:
        for key in sorted(extra):
            issues.add(rid, "INVALID_SCOPE", f"{path}.{key}", node[key])
        return
    if kind == "ALL":
        if depth > 1:
            issues.add(rid, "INVALID_SCOPE", f"{path}.type", "ALL")  # ALL selects everything: only a whole scope
        return
    if kind == "PREDICATE":
        if not isinstance(node.get("column"), str) or not COLUMN.fullmatch(node["column"]):
            issues.add(rid, "INVALID_FILTER_COLUMN", f"{path}.column", node.get("column"))
        operator = node.get("operator")
        if operator not in OPERATORS:
            issues.add(rid, "INVALID_SCOPE_OPERATOR", f"{path}.operator", operator)
            return
        value = node.get("value")
        if operator in ("IS_NULL", "IS_NOT_NULL"):
            if value is not None:
                issues.add(rid, "INVALID_FILTER_VALUE", f"{path}.value", value)
        elif operator in ("IN", "NOT_IN"):
            if not isinstance(value, list) or not value or any(isinstance(v, (list, dict)) or v is None for v in value):
                issues.add(rid, "INVALID_FILTER_VALUE", f"{path}.value", value)
            elif len(value) > limits.max_in_values:
                issues.add(rid, "INVALID_FILTER_VALUE", f"{path}.value", f"{len(value)} values")
        elif operator == "BETWEEN":
            if not isinstance(value, list) or len(value) != 2 or any(v is None or isinstance(v, (list, dict))
                                                                      for v in value):
                issues.add(rid, "INVALID_FILTER_VALUE", f"{path}.value", value)
        elif value is None or isinstance(value, (list, dict)):
            issues.add(rid, "INVALID_FILTER_VALUE", f"{path}.value", value)
        return
    if kind == "NOT":
        _scope_schema(node.get("child"), f"{path}.child", rid, depth + 1, limits, issues, counter)
        return
    children = node.get("children")
    if not isinstance(children, list) or len(children) < 2:
        issues.add(rid, "INVALID_SCOPE", f"{path}.children", children)
        return
    for index, child in enumerate(children):
        _scope_schema(child, f"{path}.children[{index}]", rid, depth + 1, limits, issues, counter)


def _buffer_schema(value: Any, path: str, rid: str, limits: Limits, issues: Issues) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != BUFFER_FIELDS or value.get("unit") not in BUFFER_UNITS \
            or isinstance(value.get("value"), bool) or not isinstance(value.get("value"), int) or value["value"] < 1:
        issues.add(rid, "BUFFER_INVALID", path, value)
        return
    cap = limits.max_buffer_observations if value["unit"] == "TRADING_OBSERVATIONS" else limits.max_buffer_days
    if value["value"] > cap:
        issues.add(rid, "BUFFER_INVALID", f"{path}.value", value["value"])


def check_schema(raw: Any, limits: Limits, issues: Issues) -> bool:
    """Layer 1. True when the spec is structurally sound enough for the catalog layers."""
    if not isinstance(raw, dict):
        issues.add(None, "INVALID_FIELD_TYPE", "", "spec must be an object")
        return False
    if raw.get("spec_version") != SPEC_VERSION:
        issues.add(None, "UNSUPPORTED_SPEC_VERSION" if "spec_version" in raw else "MISSING_REQUIRED_FIELD",
                   "spec_version", raw.get("spec_version"))
    _fields(raw, TOP_FIELDS, {"relationships"}, "", None, issues)
    group = raw.get("request_group_id")
    if not isinstance(group, str) or not GROUP_ID.fullmatch(group):
        issues.add(None, "INVALID_REQUEST_ID", "request_group_id", group)
        group = None
    revision = raw.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        issues.add(None, "INVALID_FIELD_VALUE", "revision", revision)
    if raw.get("mode") not in MODES:
        issues.add(None, "INVALID_FIELD_VALUE", "mode", raw.get("mode"))
    question = raw.get("question")
    if _string(question, "question", None, issues) and len(question) > limits.max_question_chars:
        issues.add(None, "INVALID_FIELD_VALUE", "question", f"{len(question)} characters")
    subject = raw.get("subject")
    if not isinstance(subject, dict):
        issues.add(None, "MISSING_REQUIRED_FIELD" if subject is None else "INVALID_FIELD_TYPE", "subject", subject)
    else:
        _fields(subject, SUBJECT_FIELDS, {"asset_type"}, "subject", None, issues)
        for key in ("data_domain", "entity_type"):
            if not isinstance(subject.get(key), str) or not IDENT.fullmatch(subject[key]):
                issues.add(None, "INVALID_FIELD_VALUE", f"subject.{key}", subject.get(key))
        if subject.get("asset_type") is not None and (not isinstance(subject["asset_type"], str)
                                                       or not IDENT.fullmatch(subject["asset_type"])):
            issues.add(None, "INVALID_FIELD_VALUE", "subject.asset_type", subject["asset_type"])

    requests = raw.get("data_requests")
    if not isinstance(requests, list) or not requests:
        issues.add(None, "MISSING_REQUIRED_FIELD" if not requests else "INVALID_FIELD_TYPE", "data_requests", requests)
        return False
    if len(requests) > limits.max_requests:
        issues.add(None, "TOO_MANY_ITEMS", "data_requests", f"{len(requests)} requests")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, request in enumerate(requests):
        path = f"data_requests[{index}]"
        if not isinstance(request, dict):
            issues.add(None, "INVALID_FIELD_TYPE", path, request)
            continue
        rid = request.get("data_request_id")
        valid_id = isinstance(rid, str) and group is not None and rid.startswith(group + "_") \
            and REQUEST_SUFFIX.fullmatch(rid[len(group) + 1:]) is not None
        if not valid_id:
            issues.add(rid if isinstance(rid, str) else None, "INVALID_REQUEST_ID", f"{path}.data_request_id", rid)
        elif rid in seen_ids:
            issues.add(rid, "DUPLICATE_REQUEST_ID", f"{path}.data_request_id", rid)
        if isinstance(rid, str):
            seen_ids.add(rid)
        rid = rid if isinstance(rid, str) else None
        _fields(request, REQUEST_FIELDS, {"entity_column", "time_column", "resample", "history_buffer",
                                          "future_buffer"}, path, rid, issues)
        name = request.get("logical_name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            issues.add(rid, "INVALID_FIELD_VALUE", f"{path}.logical_name", name)
        elif name in seen_names:
            issues.add(rid, "DUPLICATE_REQUEST_ID", f"{path}.logical_name", name)
        else:
            seen_names.add(name)
        table = request.get("source_table")
        if not isinstance(table, str) or not TABLE.fullmatch(table):
            issues.add(rid, "UNKNOWN_TABLE", f"{path}.source_table", table)
        for key in ("entity_column", "time_column"):
            value = request.get(key)
            if value is not None and (not isinstance(value, str) or not COLUMN.fullmatch(value)):
                issues.add(rid, "ENTITY_COLUMN_MISMATCH" if key == "entity_column" else "TIME_COLUMN_MISMATCH",
                           f"{path}.{key}", value)
        columns = request.get("columns")
        if not isinstance(columns, list) or not columns:
            issues.add(rid, "MISSING_REQUIRED_FIELD" if not columns else "INVALID_FIELD_TYPE", f"{path}.columns",
                       columns)
        else:
            if len(columns) > limits.max_columns:
                issues.add(rid, "TOO_MANY_ITEMS", f"{path}.columns", f"{len(columns)} columns")
            listed: set[str] = set()
            for position, column in enumerate(columns):
                if not isinstance(column, str) or not COLUMN.fullmatch(column):
                    issues.add(rid, "UNKNOWN_COLUMN", f"{path}.columns[{position}]", column)
                elif column in listed:
                    issues.add(rid, "INVALID_FIELD_VALUE", f"{path}.columns[{position}]", column)
                else:
                    listed.add(column)
        if "scope" in request:
            counter = [0]
            _scope_schema(request["scope"], f"{path}.scope", rid or "", 1, limits, issues, counter)
            if counter[0] > limits.max_scope_nodes:
                issues.add(rid, "INVALID_SCOPE", f"{path}.scope", f"{counter[0]} nodes")
        ranges = request.get("time_ranges")
        if not isinstance(ranges, list):
            issues.add(rid, "INVALID_FIELD_TYPE" if ranges is not None else "MISSING_REQUIRED_FIELD",
                       f"{path}.time_ranges", ranges)
        else:
            if len(ranges) > limits.max_ranges:
                issues.add(rid, "TOO_MANY_ITEMS", f"{path}.time_ranges", f"{len(ranges)} ranges")
            range_ids: set[str] = set()
            for position, item in enumerate(ranges):
                where = f"{path}.time_ranges[{position}]"
                if not isinstance(item, dict) or set(item) != RANGE_FIELDS:
                    issues.add(rid, "INVALID_TIME_RANGE", where, item)
                    continue
                if not isinstance(item["range_id"], str) or not NAME.fullmatch(item["range_id"]):
                    issues.add(rid, "INVALID_TIME_RANGE", f"{where}.range_id", item["range_id"])
                elif item["range_id"] in range_ids:
                    issues.add(rid, "DUPLICATE_RANGE_ID", f"{where}.range_id", item["range_id"])
                else:
                    range_ids.add(item["range_id"])
                for key in ("start", "end"):
                    if not isinstance(item[key], str) or not DATE.fullmatch(item[key]) or _date(item[key]) is None:
                        issues.add(rid, "INVALID_TIME_RANGE", f"{where}.{key}", item[key])
        for key, code in (("source_frequency", "SOURCE_FREQUENCY_UNAVAILABLE"),
                          ("analysis_frequency", "ANALYSIS_FREQUENCY_INVALID")):
            value = request.get(key)
            if not isinstance(value, str) or not FREQUENCY.fullmatch(value):
                issues.add(rid, code, f"{path}.{key}", value)
        if request.get("resample") is not None and request["resample"] not in RESAMPLE:
            issues.add(rid, "RESAMPLE_INVALID", f"{path}.resample", request["resample"])
        for key in ("history_buffer", "future_buffer"):
            _buffer_schema(request.get(key), f"{path}.{key}", rid or "", limits, issues)
        ordering = request.get("ordering")
        if not isinstance(ordering, list):
            issues.add(rid, "INVALID_FIELD_TYPE" if ordering is not None else "MISSING_REQUIRED_FIELD",
                       f"{path}.ordering", ordering)
        else:
            if len(ordering) > limits.max_ordering:
                issues.add(rid, "TOO_MANY_ITEMS", f"{path}.ordering", f"{len(ordering)} keys")
            ordered: set[str] = set()
            for position, item in enumerate(ordering):
                where = f"{path}.ordering[{position}]"
                if not isinstance(item, dict) or set(item) != ORDER_FIELDS or item.get("direction") not in DIRECTIONS \
                        or not isinstance(item.get("column"), str) or item["column"] in ordered:
                    issues.add(rid, "ORDERING_COLUMN_INVALID", where, item)
                else:
                    ordered.add(item["column"])
        if not isinstance(request.get("sampling_allowed"), bool):
            issues.add(rid, "INVALID_FIELD_TYPE" if "sampling_allowed" in request else "MISSING_REQUIRED_FIELD",
                       f"{path}.sampling_allowed", request.get("sampling_allowed"))

    relationships = raw.get("relationships")
    if relationships is None:
        relationships = []
    if not isinstance(relationships, list):
        issues.add(None, "INVALID_FIELD_TYPE", "relationships", relationships)
    else:
        if len(relationships) > limits.max_relationships:
            issues.add(None, "TOO_MANY_ITEMS", "relationships", f"{len(relationships)} relationships")
        for index, rel in enumerate(relationships):
            path = f"relationships[{index}]"
            if not isinstance(rel, dict):
                issues.add(None, "INVALID_FIELD_TYPE", path, rel)
                continue
            rid = rel.get("left_request_id") if isinstance(rel.get("left_request_id"), str) else None
            _fields(rel, RELATIONSHIP_FIELDS, NULLABLE_RELATIONSHIP, path, rid, issues)
            if isinstance(rel.get("relationship_id"), bool) or not isinstance(rel.get("relationship_id"), int) \
                    or rel["relationship_id"] < 1:
                issues.add(rid, "UNKNOWN_RELATIONSHIP", f"{path}.relationship_id", rel.get("relationship_id"))
            for key in ("left_request_id", "right_request_id"):
                if rel.get(key) not in seen_ids:
                    issues.add(rid, "INVALID_REQUEST_ID", f"{path}.{key}", rel.get(key))
            for key in ("left_column", "right_column"):
                if not isinstance(rel.get(key), str) or not COLUMN.fullmatch(rel[key]):
                    issues.add(rid, "RELATIONSHIP_KEY_MISMATCH", f"{path}.{key}", rel.get(key))
            if rel.get("join_type") not in JOIN_TYPES:
                issues.add(rid, "INVALID_FIELD_VALUE", f"{path}.join_type", rel.get("join_type"))
            if rel.get("join_semantics") not in JOIN_SEMANTICS:
                issues.add(rid, "JOIN_SEMANTICS_UNAVAILABLE", f"{path}.join_semantics", rel.get("join_semantics"))
            if rel.get("as_of_direction") is not None and rel["as_of_direction"] not in AS_OF_DIRECTIONS:
                issues.add(rid, "AS_OF_COLUMN_REQUIRED", f"{path}.as_of_direction", rel["as_of_direction"])
            for key in ("left_time_column", "right_time_column", "effective_from_column", "effective_to_column"):
                value = rel.get(key)
                if value is not None and (not isinstance(value, str) or not COLUMN.fullmatch(value)):
                    issues.add(rid, "TIME_COLUMN_MISMATCH", f"{path}.{key}", value)
    return not issues


def _date(text: str) -> date | None:
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------- scope typing and canonical form

def coerce(value: Any, data_type: str) -> Any:
    """The typed value the Governor will bind (raises ValueError when the value does not match the column type)."""
    kind = (data_type or "text").lower()
    if isinstance(value, bool) and kind != "boolean":
        raise ValueError
    if kind == "date":
        if not isinstance(value, str) or not DATE.fullmatch(value):
            raise ValueError
        return date.fromisoformat(value)
    if kind.startswith("timestamp"):
        if not isinstance(value, str):
            raise ValueError
        return datetime.fromisoformat(value)
    if kind in ("smallint", "integer", "bigint"):
        if isinstance(value, str) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError
        return int(value)
    if kind in ("numeric", "real", "double precision"):
        if isinstance(value, str):
            raise ValueError
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError from exc
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError
        return value
    if not isinstance(value, str) or len(value) > 200:
        raise ValueError
    return value


def _values(node: dict[str, Any]) -> list[Any]:
    operator, value = node["operator"], node.get("value")
    if operator in ("IS_NULL", "IS_NOT_NULL"):
        return []
    if operator in ("IN", "NOT_IN", "BETWEEN"):
        return list(value)
    return [value]


def canonical_scope(node: dict[str, Any], types: dict[str, str]) -> dict[str, Any]:
    """Canonical, typed form of a validated scope: children ordered, IN lists sorted and unique, values in the shared
    text form. The SQL Governor computes the same form from what it compiled (a contract test compares them)."""
    kind = node["type"]
    if kind == "ALL":
        return {"type": "ALL"}
    if kind == "PREDICATE":
        values = [canonical_value(coerce(v, types[node["column"]])) for v in _values(node)]
        if node["operator"] in ("IN", "NOT_IN"):
            values = sorted(set(values))
        return {"type": "PREDICATE", "column": node["column"], "operator": node["operator"], "values": values}
    if kind == "NOT":
        return {"type": "NOT", "children": [canonical_scope(node["child"], types)]}
    children = sorted((canonical_scope(child, types) for child in node["children"]), key=canonical_json)
    return {"type": kind, "children": children}


def scope_predicates(node: dict[str, Any], path: str):
    """(path, predicate node) for every predicate of a scope tree."""
    kind = node["type"]
    if kind == "PREDICATE":
        yield path, node
    elif kind == "NOT":
        yield from scope_predicates(node["child"], f"{path}.child")
    elif kind in ("AND", "OR"):
        for index, child in enumerate(node["children"]):
            yield from scope_predicates(child, f"{path}.children[{index}]")


# ---------------------------------------------------------------------------------------- layer 2: catalog binding

def contract_tables(raw: dict[str, Any]) -> list[str]:
    return sorted({r["source_table"] for r in raw.get("data_requests") or []
                   if isinstance(r, dict) and isinstance(r.get("source_table"), str)})


def _subject_of(meta: dict[str, Any]) -> tuple[Any, Any, Any]:
    return meta.get("data_domain"), meta.get("entity_type"), meta.get("asset_type")


def bind_catalog(spec: dict[str, Any], contract: dict[str, Any], limits: Limits, issues: Issues) -> None:
    tables, columns = contract.get("tables") or {}, contract.get("columns") or {}
    subjects = []
    for index, request in enumerate(spec["data_requests"]):
        rid, path = request["data_request_id"], f"data_requests[{index}]"
        meta = tables.get(request["source_table"])
        if meta is None:
            issues.add(rid, "UNKNOWN_TABLE", f"{path}.source_table", request["source_table"])
            continue
        subjects.append(_subject_of(meta))
        known = columns.get(request["source_table"]) or {}
        if request.get("entity_column") != meta.get("entity_column"):
            issues.add(rid, "ENTITY_COLUMN_MISMATCH", f"{path}.entity_column", request.get("entity_column"))
        if request.get("time_column") != meta.get("time_column"):
            issues.add(rid, "TIME_COLUMN_MISMATCH", f"{path}.time_column", request.get("time_column"))
        for position, column in enumerate(request["columns"]):
            if column not in known:
                issues.add(rid, "UNKNOWN_COLUMN", f"{path}.columns[{position}]", column)
        for where, predicate in scope_predicates(request["scope"], f"{path}.scope"):
            column_meta = known.get(predicate["column"])
            if column_meta is None or not column_meta.get("filter_allowed"):
                issues.add(rid, "INVALID_FILTER_COLUMN", f"{where}.column", predicate["column"])
                continue
            kind = str(column_meta.get("data_type") or "text").lower()
            ordered = kind in NUMERIC or kind == "date" or kind.startswith("timestamp")
            if predicate["operator"] in ORDERED_OPERATORS and not ordered:
                issues.add(rid, "INVALID_FILTER_OPERATOR", f"{where}.operator", predicate["operator"])
                continue
            try:
                typed = [coerce(v, kind) for v in _values(predicate)]
            except ValueError:
                issues.add(rid, "INVALID_FILTER_VALUE", f"{where}.value", predicate.get("value"))
                continue
            if predicate["operator"] == "BETWEEN" and typed[0] > typed[1]:
                issues.add(rid, "INVALID_FILTER_VALUE", f"{where}.value", predicate.get("value"))
        frequencies = meta.get("supported_frequencies")
        static = meta.get("time_column") is None
        if frequencies:
            if request["source_frequency"] not in frequencies:
                issues.add(rid, "SOURCE_FREQUENCY_UNAVAILABLE", f"{path}.source_frequency", request["source_frequency"])
        elif (request["source_frequency"] == "STATIC") != static:
            issues.add(rid, "SOURCE_FREQUENCY_UNAVAILABLE", f"{path}.source_frequency", request["source_frequency"])
        keys = {meta.get("entity_column"), meta.get("time_column")} - {None}
        for position, item in enumerate(request["ordering"]):
            if item["column"] not in set(request["columns"]) | keys:
                issues.add(rid, "ORDERING_COLUMN_INVALID", f"{path}.ordering[{position}].column", item["column"])
    subject = spec["subject"]
    wanted = (subject["data_domain"], subject["entity_type"], subject.get("asset_type"))
    if contract.get("subject_metadata", True) and subjects and wanted not in subjects:
        issues.add(None, "SUBJECT_TABLE_MISMATCH", "subject", subject)


# ---------------------------------------------------------------------------------------- layer 3: cross-request

@dataclass
class BoundRelationship:
    index: int
    relationship_id: int
    left: str
    right: str
    join_type: str
    semantics: str
    left_column: str
    right_column: str
    left_time_column: str | None
    right_time_column: str | None
    effective_from_column: str | None
    effective_to_column: str | None
    catalog_left_is_spec_left: bool


def cross_request(spec: dict[str, Any], contract: dict[str, Any], issues: Issues,
                  warnings: list[dict[str, Any]]) -> list[BoundRelationship]:
    requests = {r["data_request_id"]: r for r in spec["data_requests"]}
    catalog = {rel["relationship_id"]: rel for rel in contract.get("relationships") or []}
    tables = contract.get("tables") or {}
    bound: list[BoundRelationship] = []
    seen: set[tuple[int, str, str]] = set()
    for index, rel in enumerate(spec.get("relationships") or []):
        path = f"relationships[{index}]"
        left, right = requests.get(rel["left_request_id"]), requests.get(rel["right_request_id"])
        rid = rel["left_request_id"]
        if left is None or right is None:
            continue  # reported by the schema layer
        if left is right:
            issues.add(rid, "RELATIONSHIP_KEY_MISMATCH", f"{path}.right_request_id", rel["right_request_id"])
            continue
        key = (rel["relationship_id"], rel["left_request_id"], rel["right_request_id"])
        if key in seen:
            issues.add(rid, "RELATIONSHIP_NOT_ALLOWED", f"{path}.relationship_id", rel["relationship_id"])
            continue
        seen.add(key)
        entry = catalog.get(rel["relationship_id"])
        if entry is None:
            issues.add(rid, "UNKNOWN_RELATIONSHIP", f"{path}.relationship_id", rel["relationship_id"])
            continue
        if (entry["left_table"], entry["right_table"]) == (left["source_table"], right["source_table"]):
            forward = True
        elif (entry["right_table"], entry["left_table"]) == (left["source_table"], right["source_table"]):
            forward = False
        else:
            issues.add(rid, "RELATIONSHIP_KEY_MISMATCH", f"{path}.relationship_id", rel["relationship_id"])
            continue
        if not entry.get("is_allowed") or entry.get("requires_preaggregation"):
            issues.add(rid, "RELATIONSHIP_NOT_ALLOWED", f"{path}.relationship_id", rel["relationship_id"])
            continue
        supported = entry.get("supported_join_semantics") or []
        if rel["join_semantics"] not in supported:
            issues.add(rid, "JOIN_SEMANTICS_UNAVAILABLE", f"{path}.join_semantics", rel["join_semantics"])
            continue
        # catalog columns in the spec's orientation
        lcols, rcols = (entry["left_columns"], entry["right_columns"]) if forward else \
            (entry["right_columns"], entry["left_columns"])
        ltime, rtime = (entry.get("left_time_column"), entry.get("right_time_column")) if forward else \
            (entry.get("right_time_column"), entry.get("left_time_column"))
        pairs = [(lc, rc) for lc, rc in zip(lcols, rcols) if not (lc == ltime and rc == rtime)]
        if pairs != [(rel["left_column"], rel["right_column"])]:
            issues.add(rid, "RELATIONSHIP_KEY_MISMATCH", f"{path}.left_column",
                       f"{rel['left_column']} = {rel['right_column']}")
            continue
        semantics = rel["join_semantics"]
        left_timed = tables.get(left["source_table"], {}).get("time_column")
        if semantics in ("AS_OF", "EFFECTIVE_DATED") and not forward:
            # point-in-time reference data is the catalog relationship's right table (migration 20260925_003)
            issues.add(rid, "RELATIONSHIP_KEY_MISMATCH", f"{path}.right_request_id", rel["right_request_id"])
            continue
        if semantics in ("EXACT_DATE", "AS_OF"):
            code = "AS_OF_COLUMN_REQUIRED" if semantics == "AS_OF" else "TIME_COLUMN_MISMATCH"
            for side, expected in (("left_time_column", ltime), ("right_time_column", rtime)):
                if rel.get(side) is None:
                    issues.add(rid, code, f"{path}.{side}", None)
                elif rel[side] != expected:
                    issues.add(rid, "TIME_COLUMN_MISMATCH", f"{path}.{side}", rel[side])
            if semantics == "AS_OF" and rel.get("as_of_direction") is None:
                issues.add(rid, "AS_OF_COLUMN_REQUIRED", f"{path}.as_of_direction", None)
        else:
            for side in ("left_time_column", "right_time_column", "as_of_direction"):
                if rel.get(side) is not None:
                    issues.add(rid, "TIME_COLUMN_MISMATCH", f"{path}.{side}", rel[side])
        if semantics == "EFFECTIVE_DATED":
            for side, expected in (("effective_from_column", entry.get("effective_from_column")),
                                   ("effective_to_column", entry.get("effective_to_column"))):
                if rel.get(side) != expected or expected is None:
                    issues.add(rid, "EFFECTIVE_DATE_COLUMNS_REQUIRED", f"{path}.{side}", rel.get(side))
            if left_timed is None:
                issues.add(rid, "TIME_COLUMN_MISMATCH", f"{path}.left_request_id", rel["left_request_id"])
        else:
            for side in ("effective_from_column", "effective_to_column"):
                if rel.get(side) is not None:
                    issues.add(rid, "EFFECTIVE_DATE_COLUMNS_REQUIRED", f"{path}.{side}", rel[side])
        right_timed = tables.get(right["source_table"], {}).get("time_column")
        if semantics == "CURRENT_STATE" and (left_timed is not None or right_timed is not None):
            # whichever side holds the historical observations is joined to today's reference values
            warnings.append({"code": "HISTORICAL_REFERENCE_USES_CURRENT_STATE", "relationship_id": rel["relationship_id"],
                             "data_request_id": rel["left_request_id"] if left_timed is not None
                             else rel["right_request_id"],
                             "message": "Historical observations are joined to the current state of the reference "
                                        "table; past classifications may have differed."})
        bound.append(BoundRelationship(
            index=index, relationship_id=rel["relationship_id"], left=rel["left_request_id"],
            right=rel["right_request_id"], join_type=rel["join_type"], semantics=semantics,
            left_column=rel["left_column"], right_column=rel["right_column"],
            left_time_column=rel.get("left_time_column") or (left_timed if semantics == "EFFECTIVE_DATED" else None),
            right_time_column=rel.get("right_time_column"),
            effective_from_column=rel.get("effective_from_column"), effective_to_column=rel.get("effective_to_column"),
            catalog_left_is_spec_left=forward))
    return bound


# ------------------------------------------------------------------------------------ layer 4: planning feasibility

def feasibility(spec: dict[str, Any], contract: dict[str, Any], reference: date, limits: Limits,
                issues: Issues) -> None:
    tables = contract.get("tables") or {}
    for index, request in enumerate(spec["data_requests"]):
        rid, path = request["data_request_id"], f"data_requests[{index}]"
        meta = tables.get(request["source_table"]) or {}
        static = meta.get("time_column") is None if meta else request.get("time_column") is None
        ranges = request["time_ranges"]
        if static:
            if ranges:
                issues.add(rid, "INVALID_TIME_RANGE", f"{path}.time_ranges", ranges)
            for key in ("history_buffer", "future_buffer"):
                if request.get(key) is not None:
                    issues.add(rid, "BUFFER_INVALID", f"{path}.{key}", request[key])
            for key in ("source_frequency", "analysis_frequency"):
                if request[key] != "STATIC":
                    issues.add(rid, "ANALYSIS_FREQUENCY_INVALID" if key == "analysis_frequency"
                               else "SOURCE_FREQUENCY_UNAVAILABLE", f"{path}.{key}", request[key])
            if request.get("resample") is not None:
                issues.add(rid, "RESAMPLE_INVALID", f"{path}.resample", request["resample"])
        else:
            if not ranges:
                issues.add(rid, "TIME_RANGE_REQUIRED", f"{path}.time_ranges", ranges)
            for position, item in enumerate(ranges):
                start, end = _date(item["start"]), _date(item["end"])
                where = f"{path}.time_ranges[{position}]"
                if start is None or end is None:
                    continue
                if start > end:
                    issues.add(rid, "INVALID_TIME_RANGE", where, item)
                elif end > reference:
                    issues.add(rid, "INVALID_TIME_RANGE", f"{where}.end", item["end"])
                elif (end - start).days + 1 > limits.max_range_days:
                    issues.add(rid, "INVALID_TIME_RANGE", where, item)
            source, target = request["source_frequency"], request["analysis_frequency"]
            src, dst = frequency_minutes(source), frequency_minutes(target)
            if src is None:
                issues.add(rid, "SOURCE_FREQUENCY_UNAVAILABLE", f"{path}.source_frequency", source)
            elif dst is None or dst < src:
                issues.add(rid, "ANALYSIS_FREQUENCY_INVALID", f"{path}.analysis_frequency", target)
            elif dst == src:
                if request.get("resample") is not None:
                    issues.add(rid, "RESAMPLE_INVALID", f"{path}.resample", request["resample"])
            elif target not in RESAMPLE.values():
                issues.add(rid, "ANALYSIS_FREQUENCY_INVALID", f"{path}.analysis_frequency", target)
            elif request.get("resample") is None:
                issues.add(rid, "RESAMPLE_REQUIRED", f"{path}.resample", None)
            elif RESAMPLE[request["resample"]] != target:
                issues.add(rid, "RESAMPLE_INVALID", f"{path}.resample", request["resample"])
        if request["sampling_allowed"]:
            issues.add(rid, "SAMPLING_NOT_ALLOWED", f"{path}.sampling_allowed", True)
        known = contract.get("columns", {}).get(request["source_table"]) or {}
        keys = {c for c in (meta.get("entity_column"), meta.get("time_column"),
                            *(meta.get("primary_key_columns") or [])) if c and c in known}
        if len(set(request["columns"]) | keys) > limits.max_columns:
            issues.add(rid, "TOO_MANY_ITEMS", f"{path}.columns", f"{len(set(request['columns']) | keys)} columns")


def extraction_windows(request: dict[str, Any], reference: date) -> list[dict[str, Any]]:
    """The approved window of every requested range: the range widened by its history and future buffers (future
    capped at the reference date). The planner extracts at least these windows; the coverage check proves it did."""
    back, ahead = buffer_days(request.get("history_buffer")), buffer_days(request.get("future_buffer"))
    windows = []
    for item in request["time_ranges"]:
        start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        windows.append({"range_id": item["range_id"], "start": item["start"], "end": item["end"],
                        "extract_from": (start - timedelta(days=back)).isoformat(),
                        "extract_to": min(reference, end + timedelta(days=ahead)).isoformat()})
    return windows


# ----------------------------------------------------------------------------------------------------- validator

@dataclass
class Validation:
    status: str
    issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    approved: dict[str, Any] | None = None

    def body(self) -> dict[str, Any]:
        return {"status": self.status, "issues": self.issues, "warnings": self.warnings}


def validate(raw: Any, contract: dict[str, Any] | None, reference: date, limits: Limits = Limits()) -> Validation:
    """All four layers. `contract` is the Governor's catalog contract of the spec's tables, or None when the catalog
    could not be read (CATALOG_UNAVAILABLE). Approval is atomic: one issue anywhere refuses the whole spec."""
    issues = Issues()
    if not check_schema(raw, limits, issues):
        return Validation("REVISION_REQUIRED", issues.items)
    if contract is None:
        return Validation("CATALOG_UNAVAILABLE", [{"data_request_id": None, "code": "CATALOG_UNAVAILABLE",
                                                   "field_path": "", "rejected_value": None}])
    warnings: list[dict[str, Any]] = []
    bind_catalog(raw, contract, limits, issues)
    bound = cross_request(raw, contract, issues, warnings)
    feasibility(raw, contract, reference, limits, issues)
    if issues:
        return Validation("REVISION_REQUIRED", issues.items, warnings)
    return Validation("APPROVED", [], warnings, approved_contract(raw, contract, bound, reference))


def approved_contract(spec: dict[str, Any], contract: dict[str, Any], bound: list[BoundRelationship],
                      reference: date) -> dict[str, Any]:
    """What extraction, profiling and coverage are checked against: the spec, per-request canonical scopes and
    extraction windows, restrictions derived from INNER relationships, and the catalog version it was bound to."""
    tables, columns = contract.get("tables") or {}, contract.get("columns") or {}
    requests: dict[str, Any] = {}
    for request in spec["data_requests"]:
        meta = tables[request["source_table"]]
        types = {name: str(info.get("data_type") or "text") for name, info in (columns[request["source_table"]]).items()}
        scope = canonical_scope(request["scope"], types)
        # the table's grain always travels with the data: entity, time and every other primary-key column the
        # catalog exposes, so rows stay identifiable (duplicate keys can be checked) whatever columns were asked for
        keys = list(dict.fromkeys(c for c in (meta.get("entity_column"), meta.get("time_column"),
                                              *(meta.get("primary_key_columns") or [])) if c and c in types))
        extract_columns = list(dict.fromkeys(keys + list(request["columns"])))
        resample_rules = {c: (columns[request["source_table"]].get(c) or {}).get("resample_aggregation")
                          for c in request["columns"] if c not in keys}
        requests[request["data_request_id"]] = {
            "data_request_id": request["data_request_id"], "logical_name": request["logical_name"],
            "source_table": request["source_table"], "entity_column": meta.get("entity_column"),
            "time_column": meta.get("time_column"), "primary_key_columns": list(meta.get("primary_key_columns") or []),
            "columns": list(request["columns"]), "key_columns": keys, "extract_columns": extract_columns,
            "column_types": {c: types.get(c) for c in extract_columns},
            "scope": scope, "scope_sha256": sha256_json(scope),
            "windows": extraction_windows(request, reference) if meta.get("time_column") else [],
            "source_frequency": request["source_frequency"], "analysis_frequency": request["analysis_frequency"],
            "resample": request.get("resample"), "resample_rules": resample_rules,
            "history_buffer": request.get("history_buffer"), "future_buffer": request.get("future_buffer"),
            "ordering": list(request["ordering"]), "sampling_allowed": False,
            "catalog_table_sha256": meta.get("catalog_table_sha256"), "restrictions": []}
    relationships = []
    for b in bound:
        right = requests[b.right]
        entry = {"relationship_id": b.relationship_id, "left_request_id": b.left, "right_request_id": b.right,
                 "join_type": b.join_type, "join_semantics": b.semantics, "left_column": b.left_column,
                 "right_column": b.right_column, "left_time_column": b.left_time_column,
                 "right_time_column": b.right_time_column, "as_of_direction": "BACKWARD" if b.semantics == "AS_OF"
                 else None, "effective_from_column": b.effective_from_column,
                 "effective_to_column": b.effective_to_column}
        relationships.append(entry)
        if b.join_type == "INNER":
            # An INNER join keeps only rows with a match on the other side, so the restriction is pushed down on
            # both sides, each selected by the other request's own scope. Restrictions are one level deep (a
            # superset of the exact join, which saniti.join performs in the session). The reference side of a
            # point-in-time join (AS_OF, EFFECTIVE_DATED) is delivered by its own scope only.
            requests[b.left]["restrictions"].append({
                **{k: entry[k] for k in ("relationship_id", "join_semantics", "left_column", "right_column",
                                         "left_time_column", "right_time_column", "as_of_direction",
                                         "effective_from_column", "effective_to_column")},
                "right_table": right["source_table"], "right_scope": right["scope"],
                "right_scope_sha256": right["scope_sha256"]})
            if b.semantics in ("CURRENT_STATE", "EXACT_DATE"):
                left = requests[b.left]
                requests[b.right]["restrictions"].append({
                    "relationship_id": b.relationship_id, "join_semantics": b.semantics,
                    "left_column": b.right_column, "right_column": b.left_column,
                    "left_time_column": b.right_time_column, "right_time_column": b.left_time_column,
                    "as_of_direction": None, "effective_from_column": None, "effective_to_column": None,
                    "right_table": left["source_table"], "right_scope": left["scope"],
                    "right_scope_sha256": left["scope_sha256"]})
    for entry in requests.values():
        entry["restriction_sha256"] = sha256_json(entry["restrictions"])
    normalized = {**spec, "relationships": list(spec.get("relationships") or [])}
    return {"spec_version": SPEC_VERSION, "spec": normalized, "spec_sha256": sha256_json(normalized),
            "request_group_id": spec["request_group_id"], "revision": spec["revision"], "mode": spec["mode"],
            "requests": requests, "relationships": relationships, "reference_date": reference.isoformat(),
            "catalog_sha256": contract.get("catalog_sha256"), "catalog_version": contract.get("catalog_version")}
