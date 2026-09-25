"""POST /v1/extract: one physical extraction of one approved DataNeedSpec data request (backend callers only).

market-ai-orc's Execution Planner sends an ExtractionSpec it derived from an approved DataNeedSpec (the model never
writes one). The spec is catalog identifiers and canonical values only, never SQL:

- source_table and the columns to extract (the planner has pruned them to the request's columns plus its keys);
- scope: the approved canonical scope tree (ALL, PREDICATE, AND, OR, NOT; values in canonical text form);
- restrictions: INNER relationships of the DataNeedSpec, each a semi-join on a catalog relationship with its join
  semantics, evaluated per observation date:
    CURRENT_STATE    a right row with the key exists and satisfies the right scope;
    EXACT_DATE       ... on the same date (catalog left/right time columns);
    AS_OF            the latest right row at or before the observation date (BACKWARD) satisfies the right scope;
    EFFECTIVE_DATED  a right row valid on the observation date, effective_from <= date < effective_to (NULL = open);
- window: the physical date window of a dated table (an envelope of approved ranges, or a date partition of it);
- entity_partition: optional {modulus, remainder}: rows whose entity hashes to the remainder (a complete, disjoint
  split of the entities);
- order_by: requested ordering; the table's key columns are appended so the order is total and deterministic.

The Governor re-validates everything against the catalog (tables, columns, filter permissions, value types,
relationship ids, supported join semantics, time and effective columns, temporal direction), compiles parameterized
SQL (identifiers via psycopg.sql.Identifier, every value bound), EXPLAINs it, and answers with one status:

    APPROVED                    extracted: an immutable Parquet dataset with lineage and the executed scope
    APPROVED_WITH_PARTITIONING  not extracted: the plan fits only as {kind DATE|ENTITY, parts}; resubmit the parts
    REJECTED_COMPUTE_COST / REJECTED_SCAN_SIZE / REJECTED_ROW_LIMIT / REJECTED_JOIN_COST / REJECTED_TIMEOUT_RISK
                                no semantics-preserving partitioning fits the limits
    REJECTED_POLICY             the spec breaks catalog policy (the DataNeedSpec itself must change)

Nothing is ever sampled or truncated: a result over the row cap is refused, not cut. The executed scope is derived
from what was compiled, in the same canonical form and hashes the sandbox approved, so the sandbox can prove the
dataset is exactly the approved request.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from psycopg import sql
from pydantic import BaseModel, ConfigDict, Field

from .catalog_contract import canonical_json, canonical_value, sha256_json
from .compiler import CompiledQuery

EXTRACTION_VERSION = "extraction_spec/v1"
EXECUTED_SCOPE_VERSION = "extract/v1"
TABLE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]{0,62}$"
COLUMN_PATTERN = r"^[A-Za-z_][A-Za-z0-9_ ]{0,62}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
MAX_SCOPE_DEPTH = 4
MAX_SCOPE_NODES = 40
NUMERIC = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
INTEGER = ("smallint", "integer", "bigint")
OPERATORS = {"EQ": "=", "NEQ": "<>", "GT": ">", "GTE": ">=", "LT": "<", "LTE": "<="}
ORDERED = ("GT", "GTE", "LT", "LTE", "BETWEEN")
# PostgreSQL hashtextextended() is stable for a given server version; masking the sign bit keeps the modulus
# non-negative without abs() overflow on the minimum bigint.
HASH_MASK = 9223372036854775807

STATUSES = ("APPROVED", "APPROVED_WITH_PARTITIONING", "REJECTED_COMPUTE_COST", "REJECTED_SCAN_SIZE",
            "REJECTED_ROW_LIMIT", "REJECTED_JOIN_COST", "REJECTED_TIMEOUT_RISK", "REJECTED_POLICY")
NEXT_ACTION = {"APPROVED": "ADD_TO_BUNDLE", "APPROVED_WITH_PARTITIONING": "PARTITION_AND_RESUBMIT",
               "REJECTED_POLICY": "REVISE_DATA_NEED_SPEC"}
RESOURCE_NEXT_ACTION = "REPLAN_OR_REVISE_DATA_NEED_SPEC"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopeNode(Strict):
    """Canonical scope tree (the sandbox's approved form): NOT has exactly one child in `children`."""

    type: Literal["ALL", "PREDICATE", "AND", "OR", "NOT"]
    column: str | None = Field(default=None, pattern=COLUMN_PATTERN)
    operator: Literal["EQ", "NEQ", "GT", "GTE", "LT", "LTE", "IN", "NOT_IN", "BETWEEN", "IS_NULL",
                      "IS_NOT_NULL"] | None = None
    values: list[str] | None = Field(default=None, max_length=1000)
    children: list["ScopeNode"] | None = Field(default=None, max_length=MAX_SCOPE_NODES)


class Restriction(Strict):
    relationship_id: int = Field(ge=1)
    join_semantics: Literal["CURRENT_STATE", "EXACT_DATE", "AS_OF", "EFFECTIVE_DATED"]
    left_column: str = Field(pattern=COLUMN_PATTERN)
    right_column: str = Field(pattern=COLUMN_PATTERN)
    left_time_column: str | None = Field(pattern=COLUMN_PATTERN)
    right_time_column: str | None = Field(pattern=COLUMN_PATTERN)
    as_of_direction: Literal["BACKWARD"] | None
    effective_from_column: str | None = Field(pattern=COLUMN_PATTERN)
    effective_to_column: str | None = Field(pattern=COLUMN_PATTERN)
    right_table: str = Field(pattern=TABLE_PATTERN)
    right_scope: ScopeNode
    right_scope_sha256: str = Field(pattern=SHA256_PATTERN)


class Window(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: str = Field(alias="from", pattern=DATE_PATTERN)
    end: str = Field(alias="to", pattern=DATE_PATTERN)


class EntityPartition(Strict):
    modulus: int = Field(ge=2, le=4096)
    remainder: int = Field(ge=0)


class OrderKey(Strict):
    column: str = Field(pattern=COLUMN_PATTERN)
    direction: Literal["ASC", "DESC"]


class ExtractionSpec(Strict):
    extraction_version: Literal["extraction_spec/v1"]
    data_request_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}_[A-Za-z0-9]{1,12}$")
    source_table: str = Field(pattern=TABLE_PATTERN)
    columns: list[str] = Field(min_length=1, max_length=60)
    scope: ScopeNode
    restrictions: list[Restriction] = Field(max_length=8)
    window: Window | None
    entity_partition: EntityPartition | None
    order_by: list[OrderKey] = Field(max_length=12)


class Envelope(Strict):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: str = Field(alias="from", pattern=DATE_PATTERN)
    end: str = Field(alias="to", pattern=DATE_PATTERN)
    range_ids: list[str] = Field(min_length=1, max_length=12)


class ExtractionLineage(Strict):
    """Sent by the planner next to the spec; recorded in the dataset manifest and returned only to the sandbox.
    The Governor checks that extraction_sha256 and part_key describe the spec it compiled."""

    need_id: str = Field(pattern=r"^need_[0-9a-f]{24}$")
    spec_sha256: str = Field(pattern=SHA256_PATTERN)
    request_group_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    revision: int = Field(ge=1)
    data_request_id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}_[A-Za-z0-9]{1,12}$")
    logical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    scope_sha256: str = Field(pattern=SHA256_PATTERN)
    restriction_sha256: str = Field(pattern=SHA256_PATTERN)
    plan_id: str = Field(pattern=r"^plan_[0-9a-f]{24}$")
    part_key: str = Field(pattern=SHA256_PATTERN)
    envelope: Envelope | None
    catalog_sha256: str | None = Field(pattern=SHA256_PATTERN)
    extraction_sha256: str = Field(pattern=SHA256_PATTERN)


class ExtractStop(Exception):
    """A deterministic non-extraction outcome (a REJECTED_* status or APPROVED_WITH_PARTITIONING)."""

    def __init__(self, status: str, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def policy(code: str, message: str, **details: Any) -> ExtractStop:
    return ExtractStop("REJECTED_POLICY", code, message, **details)


def part_key(window: dict[str, str] | None, entity_partition: dict[str, int] | None) -> str:
    """Identity of one physical part (shared with the planner and the sandbox)."""
    return sha256_json({"window": window, "entity_partition": entity_partition})


def extraction_sha256(raw: Any) -> str:
    """Hash of the extraction body exactly as sent (the planner hashes the same JSON)."""
    return sha256_json(raw)


# ---------------------------------------------------------------- typed values

def from_canonical(text: str, data_type: str, label: str) -> Any:
    """The typed value of a canonical text value; it must render back to exactly the same text."""
    kind = (data_type or "text").lower()
    try:
        if kind == "date":
            value: Any = date.fromisoformat(text)
        elif kind.startswith("timestamp"):
            value = datetime.fromisoformat(text)
        elif kind in INTEGER:
            value = int(text)
        elif kind in NUMERIC:
            value = Decimal(text)
            if not value.is_finite():
                raise ValueError
        elif kind == "boolean":
            if text not in ("true", "false"):
                raise ValueError
            value = text == "true"
        else:
            if len(text) > 200:
                raise ValueError
            value = text
    except (ValueError, InvalidOperation) as exc:
        raise policy("INVALID_FILTER_VALUE", f"{label}: {text!r} is not a {data_type} value.") from exc
    if canonical_value(value) != text:
        raise policy("NON_CANONICAL_VALUE", f"{label}: {text!r} is not in canonical form.")
    return value


# ---------------------------------------------------------------- binding (pure: no database access)

@dataclass
class BoundPredicate:
    column: str
    operator: str
    values: list[Any]
    data_type: str


@dataclass
class BoundNode:
    type: str
    predicate: BoundPredicate | None = None
    children: list["BoundNode"] = field(default_factory=list)


@dataclass
class BoundRestriction:
    index: int
    spec: Restriction
    right_table: str
    right_scope: BoundNode
    canonical: dict[str, Any]


@dataclass
class BoundExtraction:
    spec: ExtractionSpec
    table: dict[str, Any]
    columns: list[dict[str, Any]]            # {name, data_type, unit}
    scope: BoundNode
    canonical_scope: dict[str, Any]
    restrictions: list[BoundRestriction]
    window: tuple[date, date] | None
    order_by: list[tuple[str, str]]
    warnings: list[str] = field(default_factory=list)

    @property
    def time_column(self) -> str | None:
        return self.table.get("time_column")

    @property
    def entity_column(self) -> str | None:
        return self.table.get("entity_column")

    @property
    def source_tables(self) -> list[str]:
        return list(dict.fromkeys([self.spec.source_table, *(r.right_table for r in self.restrictions)]))

    def window_days(self) -> int:
        return (self.window[1] - self.window[0]).days + 1 if self.window else 0


def canonical(node: BoundNode) -> dict[str, Any]:
    """Canonical form of a bound scope; identical to the sandbox's app/data_need.py canonical_scope."""
    if node.type == "ALL":
        return {"type": "ALL"}
    if node.type == "PREDICATE":
        p = node.predicate
        values = [canonical_value(v) for v in p.values]
        if p.operator in ("IN", "NOT_IN"):
            values = sorted(set(values))
        return {"type": "PREDICATE", "column": p.column, "operator": p.operator, "values": values}
    children = [canonical(child) for child in node.children]
    if node.type in ("AND", "OR"):
        children = sorted(children, key=canonical_json)
    return {"type": node.type, "children": children}


def _bind_scope(node: ScopeNode, columns: dict[str, dict[str, Any]], table: str, max_in: int,
                depth: int = 1, counter: list[int] | None = None) -> BoundNode:
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if depth > MAX_SCOPE_DEPTH or counter[0] > MAX_SCOPE_NODES:
        raise policy("INVALID_SCOPE", f"{table}: the scope exceeds depth {MAX_SCOPE_DEPTH} or {MAX_SCOPE_NODES} "
                                      "nodes.")
    if node.type == "ALL":
        if depth > 1 or node.column or node.operator or node.values or node.children:
            raise policy("INVALID_SCOPE", f"{table}: ALL is only a whole scope and takes no fields.")
        return BoundNode("ALL")
    if node.type == "PREDICATE":
        if node.children or node.column is None or node.operator is None:
            raise policy("INVALID_SCOPE", f"{table}: a PREDICATE has column, operator and values only.")
        meta = columns.get(node.column)
        label = f"{table}.{node.column} {node.operator}"
        if meta is None:
            raise policy("COLUMN_NOT_ALLOWED", f"{table}.{node.column} is not an AI-allowed catalog column.")
        if not meta.get("filter_allowed"):
            raise policy("FILTER_NOT_ALLOWED", f"{table}.{node.column} cannot be filtered.")
        kind = str(meta.get("data_type") or "text").lower()
        if node.operator in ORDERED and not (kind in NUMERIC or kind == "date" or kind.startswith("timestamp")):
            raise policy("INVALID_FILTER_OPERATOR", f"{label}: {node.operator} needs an ordered column type.")
        texts = list(node.values or [])
        expected = {"IS_NULL": 0, "IS_NOT_NULL": 0, "BETWEEN": 2}.get(node.operator, None if node.operator in (
            "IN", "NOT_IN") else 1)
        if (expected is not None and len(texts) != expected) or (expected is None and not texts):
            raise policy("INVALID_FILTER_VALUE", f"{label}: wrong number of values ({len(texts)}).")
        if len(texts) > max_in:
            raise ExtractStop("REJECTED_POLICY", "TOO_MANY_IN_VALUES", f"{label}: at most {max_in} values.",
                              limit=max_in)
        values = [from_canonical(text, kind, label) for text in texts]
        if node.operator == "BETWEEN" and values[0] > values[1]:
            raise policy("INVALID_FILTER_VALUE", f"{label}: the low bound is above the high bound.")
        return BoundNode("PREDICATE", BoundPredicate(node.column, node.operator, values, kind))
    if node.column or node.operator or node.values:
        raise policy("INVALID_SCOPE", f"{table}: {node.type} takes children only.")
    children = node.children or []
    if (node.type == "NOT" and len(children) != 1) or (node.type in ("AND", "OR") and len(children) < 2):
        raise policy("INVALID_SCOPE", f"{table}: {node.type} has the wrong number of children.")
    return BoundNode(node.type, children=[_bind_scope(child, columns, table, max_in, depth + 1, counter)
                                          for child in children])


def _relationship_orientation(rel: dict[str, Any], source: str, right: str) -> bool | None:
    if (rel["left_table"], rel["right_table"]) == (source, right):
        return True
    if (rel["right_table"], rel["left_table"]) == (source, right):
        return False
    return None


def _bind_restriction(index: int, item: Restriction, source_meta: dict[str, Any], contract: dict[str, Any],
                      max_in: int) -> BoundRestriction:
    source = source_meta["table_name"]
    rel = next((r for r in contract.get("relationships") or [] if r["relationship_id"] == item.relationship_id), None)
    label = f"restriction {item.relationship_id}"
    if rel is None:
        raise policy("UNKNOWN_RELATIONSHIP", f"{label}: relationship {item.relationship_id} does not touch {source}.")
    forward = _relationship_orientation(rel, source, item.right_table)
    if forward is None:
        raise policy("RELATIONSHIP_KEY_MISMATCH", f"{label} does not join {source} to {item.right_table}.")
    if not rel.get("is_allowed") or rel.get("requires_preaggregation"):
        raise policy("RELATIONSHIP_NOT_ALLOWED", f"{label} is not approved for row-level restriction.")
    semantics = item.join_semantics
    if semantics not in (rel.get("supported_join_semantics") or []):
        raise policy("JOIN_SEMANTICS_UNAVAILABLE", f"{label} does not support {semantics}.")
    right_meta = (contract.get("tables") or {}).get(item.right_table)
    right_columns = (contract.get("columns") or {}).get(item.right_table) or {}
    if right_meta is None:
        raise policy("TABLE_NOT_APPROVED", f"{item.right_table} is not an approved AI catalog table.")
    lcols, rcols = (rel["left_columns"], rel["right_columns"]) if forward else (rel["right_columns"],
                                                                                rel["left_columns"])
    ltime, rtime = (rel.get("left_time_column"), rel.get("right_time_column")) if forward else (
        rel.get("right_time_column"), rel.get("left_time_column"))
    pairs = [(lc, rc) for lc, rc in zip(lcols, rcols) if not (lc == ltime and rc == rtime)]
    if pairs != [(item.left_column, item.right_column)]:
        raise policy("RELATIONSHIP_KEY_MISMATCH", f"{label}: the key pair is {pairs}, not "
                                                  f"{(item.left_column, item.right_column)}.")
    source_time = source_meta.get("time_column")
    if semantics in ("AS_OF", "EFFECTIVE_DATED") and not forward:
        raise policy("TEMPORAL_DIRECTION_NOT_ALLOWED", f"{label}: point-in-time reference data must be the "
                                                       "catalog relationship's right table.")
    if semantics in ("EXACT_DATE", "AS_OF"):
        if (item.left_time_column, item.right_time_column) != (ltime, rtime) or ltime is None:
            raise policy("TIME_COLUMN_MISMATCH", f"{label}: time columns must be the catalog's ({ltime}, {rtime}).")
        if ltime != source_time:
            raise policy("TIME_COLUMN_MISMATCH", f"{label}: {ltime} is not the time column of {source}.")
        if semantics == "AS_OF" and item.as_of_direction != "BACKWARD":
            raise policy("TEMPORAL_DIRECTION_NOT_ALLOWED", f"{label}: AS_OF joins look backward only.")
    elif item.right_time_column is not None or item.as_of_direction is not None:
        raise policy("TIME_COLUMN_MISMATCH", f"{label}: {semantics} takes no right time column or direction.")
    if semantics == "EFFECTIVE_DATED":
        expected = (rel.get("effective_from_column"), rel.get("effective_to_column"))
        if (item.effective_from_column, item.effective_to_column) != expected or None in expected:
            raise policy("EFFECTIVE_DATE_COLUMNS_REQUIRED", f"{label}: effective columns must be the catalog's "
                                                            f"{expected}.")
        if source_time is None or item.left_time_column != source_time:
            raise policy("TIME_COLUMN_MISMATCH", f"{label}: EFFECTIVE_DATED needs {source}'s time column.")
    else:
        if item.effective_from_column is not None or item.effective_to_column is not None:
            raise policy("EFFECTIVE_DATE_COLUMNS_REQUIRED", f"{label}: {semantics} takes no effective columns.")
        if semantics == "CURRENT_STATE" and item.left_time_column is not None:
            raise policy("TIME_COLUMN_MISMATCH", f"{label}: CURRENT_STATE takes no time columns.")
    scope = _bind_scope(item.right_scope, right_columns, item.right_table, max_in)
    right_canonical = canonical(scope)
    if sha256_json(right_canonical) != item.right_scope_sha256:
        raise policy("SCOPE_HASH_MISMATCH", f"{label}: right_scope_sha256 does not match the right scope.")
    entry = {"relationship_id": item.relationship_id, "join_semantics": semantics,
             "left_column": item.left_column, "right_column": item.right_column,
             "left_time_column": item.left_time_column, "right_time_column": item.right_time_column,
             "as_of_direction": item.as_of_direction, "effective_from_column": item.effective_from_column,
             "effective_to_column": item.effective_to_column, "right_table": item.right_table,
             "right_scope": right_canonical, "right_scope_sha256": item.right_scope_sha256}
    return BoundRestriction(index, item, item.right_table, scope, entry)


def bind(spec: ExtractionSpec, contract: dict[str, Any], *, max_in_values: int, max_columns: int) -> BoundExtraction:
    """Validate an ExtractionSpec against the catalog contract of its tables (pure)."""
    tables = contract.get("tables") or {}
    meta = tables.get(spec.source_table)
    if meta is None:
        raise policy("TABLE_NOT_APPROVED", f"{spec.source_table} is not an active, AI-readable catalog table.")
    known = (contract.get("columns") or {}).get(spec.source_table) or {}
    if len(spec.columns) > max_columns:
        raise policy("TOO_MANY_COLUMNS", f"At most {max_columns} columns per extraction.", limit=max_columns)
    if len(set(spec.columns)) != len(spec.columns):
        raise policy("DUPLICATE_COLUMN", "Each column may be extracted once.")
    columns = []
    for name in spec.columns:
        info = known.get(name)
        if info is None:
            raise policy("COLUMN_NOT_ALLOWED", f"{spec.source_table}.{name} is not an AI-allowed catalog column.")
        columns.append({"name": name, "data_type": info.get("data_type") or "text", "unit": info.get("unit")})
    keys = [c for c in (meta.get("entity_column"), meta.get("time_column")) if c]
    missing = [c for c in keys if c not in spec.columns]
    if missing:
        raise policy("KEY_COLUMNS_REQUIRED", f"The extraction must include the key columns {missing}.")
    scope = _bind_scope(spec.scope, known, spec.source_table, max_in_values)
    restrictions = [_bind_restriction(i, item, meta, contract, max_in_values)
                    for i, item in enumerate(spec.restrictions)]
    time_column = meta.get("time_column")
    window = None
    if time_column:
        if spec.window is None:
            raise policy("TIME_WINDOW_REQUIRED", f"{spec.source_table} is dated; the extraction needs a window.")
        start, end = date.fromisoformat(spec.window.start), date.fromisoformat(spec.window.end)
        if start > end:
            raise policy("INVALID_TIME_WINDOW", "The window starts after it ends.")
        window = (start, end)
    elif spec.window is not None:
        raise policy("INVALID_TIME_WINDOW", f"{spec.source_table} has no time column; the window must be null.")
    if spec.entity_partition is not None:
        if not meta.get("entity_column"):
            raise policy("ENTITY_PARTITION_NOT_POSSIBLE", f"{spec.source_table} has no entity column.")
        if spec.entity_partition.remainder >= spec.entity_partition.modulus:
            raise policy("INVALID_ENTITY_PARTITION", "remainder must be below modulus.")
    ordered: list[tuple[str, str]] = []
    for key in spec.order_by:
        if key.column not in spec.columns or key.column in {c for c, _ in ordered}:
            raise policy("ORDERING_COLUMN_INVALID", f"{key.column} is not an extracted column (or is repeated).")
        ordered.append((key.column, key.direction))
    # the table's keys complete the order, so equal checksums mean equal rows in equal order
    for column in [*keys, *(meta.get("primary_key_columns") or [])]:
        if column in spec.columns and column not in {c for c, _ in ordered}:
            ordered.append((column, "ASC"))
    return BoundExtraction(spec, meta, columns, scope, canonical(scope), restrictions, window, ordered)


# ---------------------------------------------------------------- compilation

def _column(alias: str, column: str) -> sql.Composable:
    return sql.Identifier(alias, column)


def _scope_sql(node: BoundNode, alias: str, params: list[Any]) -> sql.Composable:
    if node.type == "ALL":
        return sql.SQL("TRUE")
    if node.type == "PREDICATE":
        p = node.predicate
        ref = _column(alias, p.column)
        if p.operator == "IS_NULL":
            return sql.SQL("{} IS NULL").format(ref)
        if p.operator == "IS_NOT_NULL":
            return sql.SQL("{} IS NOT NULL").format(ref)
        if p.operator == "IN":
            params.append(list(p.values))
            return sql.SQL("{} = ANY({})").format(ref, sql.Placeholder())
        if p.operator == "NOT_IN":
            params.append(list(p.values))
            return sql.SQL("{} <> ALL({})").format(ref, sql.Placeholder())
        if p.operator == "BETWEEN":
            params.extend(p.values)
            return sql.SQL("{} BETWEEN {} AND {}").format(ref, sql.Placeholder(), sql.Placeholder())
        params.append(p.values[0])
        return sql.SQL("{} {} {}").format(ref, sql.SQL(OPERATORS[p.operator]), sql.Placeholder())
    if node.type == "NOT":
        return sql.SQL("NOT ({})").format(_scope_sql(node.children[0], alias, params))
    joiner = sql.SQL(" AND " if node.type == "AND" else " OR ")
    return sql.SQL("({})").format(joiner.join(_scope_sql(child, alias, params) for child in node.children))


def _restriction_sql(r: BoundRestriction, base: str, time_column: str | None, params: list[Any]) -> sql.Composable:
    item = r.spec
    alias = f"r{r.index}"
    table = sql.Identifier("public", r.right_table)
    key = sql.SQL("{} = {}").format(_column(alias, item.right_column), _column(base, item.left_column))
    semantics = item.join_semantics
    if semantics == "AS_OF":
        # the latest reference row at or before the observation date must satisfy the reference scope
        inner = sql.SQL("SELECT {cols} FROM {table} AS {alias} WHERE {key} AND {rt} <= {lt} "
                        "ORDER BY {rt} DESC LIMIT 1").format(
            cols=sql.SQL("{}.*").format(sql.Identifier(alias)), table=table, alias=sql.Identifier(alias), key=key,
            rt=_column(alias, item.right_time_column), lt=_column(base, item.left_time_column))
        latest = f"a{r.index}"
        condition = _scope_sql(r.right_scope, latest, params)
        return sql.SQL("EXISTS (SELECT 1 FROM ({inner}) AS {latest} WHERE {condition})").format(
            inner=inner, latest=sql.Identifier(latest), condition=condition)
    parts: list[sql.Composable] = [key]
    if semantics == "EXACT_DATE":
        parts.append(sql.SQL("{} = {}").format(_column(alias, item.right_time_column),
                                               _column(base, item.left_time_column)))
    elif semantics == "EFFECTIVE_DATED":
        parts.append(sql.SQL("{} <= {}").format(_column(alias, item.effective_from_column),
                                                _column(base, time_column)))
        parts.append(sql.SQL("({to} IS NULL OR {t} < {to})").format(
            to=_column(alias, item.effective_to_column), t=_column(base, time_column)))
    parts.append(_scope_sql(r.right_scope, alias, params))
    return sql.SQL("EXISTS (SELECT 1 FROM {table} AS {alias} WHERE {conditions})").format(
        table=table, alias=sql.Identifier(alias), conditions=sql.SQL(" AND ").join(parts))


def compile_extraction(bound: BoundExtraction, row_cap: int | None) -> CompiledQuery:
    """Parameterized SQL of a bound extraction; row_cap None compiles the EXPLAIN form (no LIMIT)."""
    base = "t0"
    params: list[Any] = []
    select = sql.SQL(", ").join(sql.SQL("{} AS {}").format(_column(base, c["name"]), sql.Identifier(c["name"]))
                                for c in bound.columns)
    conditions: list[sql.Composable] = []
    if bound.window is not None:
        conditions.append(sql.SQL("{} BETWEEN {} AND {}").format(
            _column(base, bound.time_column), sql.Placeholder(), sql.Placeholder()))
        params.extend(bound.window)
    if bound.scope.type != "ALL":
        conditions.append(_scope_sql(bound.scope, base, params))
    for restriction in bound.restrictions:
        conditions.append(_restriction_sql(restriction, base, bound.time_column, params))
    if bound.spec.entity_partition is not None:
        conditions.append(sql.SQL("mod(hashtextextended({}::text, 0) & {}, {}) = {}").format(
            _column(base, bound.entity_column), sql.Literal(HASH_MASK), sql.Placeholder(), sql.Placeholder()))
        params.extend([bound.spec.entity_partition.modulus, bound.spec.entity_partition.remainder])
    parts: list[sql.Composable] = [sql.SQL("SELECT "), select, sql.SQL(" FROM {} AS {}").format(
        sql.Identifier("public", bound.spec.source_table), sql.Identifier(base))]
    if conditions:
        parts += [sql.SQL(" WHERE "), sql.SQL(" AND ").join(conditions)]
    if bound.order_by:
        parts += [sql.SQL(" ORDER BY "), sql.SQL(", ").join(
            sql.SQL("{} {}").format(_column(base, c), sql.SQL("ASC" if d == "ASC" else "DESC"))
            for c, d in bound.order_by)]
    if row_cap is not None:
        parts += [sql.SQL(" LIMIT "), sql.Placeholder()]
        params.append(row_cap)
    statement = sql.Composed(parts)
    return CompiledQuery(statement, tuple(params), statement.as_string(None))


def executed_scope(bound: BoundExtraction) -> dict[str, Any]:
    """What was compiled, in the sandbox's canonical form and hashes (scope_sha256, restriction_sha256)."""
    restrictions = [r.canonical for r in bound.restrictions]
    window = {"column": bound.time_column, "from": bound.window[0].isoformat(), "to": bound.window[1].isoformat()} \
        if bound.window else None
    partition = bound.spec.entity_partition.model_dump() if bound.spec.entity_partition else None
    return {"version": EXECUTED_SCOPE_VERSION, "data_request_id": bound.spec.data_request_id,
            "source_table": bound.spec.source_table, "columns": [c["name"] for c in bound.columns],
            "scope": bound.canonical_scope, "scope_sha256": sha256_json(bound.canonical_scope),
            "restrictions": restrictions, "restriction_sha256": sha256_json(restrictions), "window": window,
            "entity_partition": partition,
            "part_key": part_key({"from": window["from"], "to": window["to"]} if window else None, partition),
            "order_by": [{"column": c, "direction": d} for c, d in bound.order_by],
            "sampling": False, "truncation": False}


# ---------------------------------------------------------------- partitioning decisions (pure)

@dataclass(frozen=True)
class Limits:
    max_scan_rows: int
    max_result_rows: int
    max_plan_cost: float
    max_window_days: int
    max_parts: int


@dataclass(frozen=True)
class Estimates:
    scan_rows: int
    result_rows: int
    plan_cost: float


def _stop_for(violation: str, restricted: bool) -> str:
    return {"SCAN": "REJECTED_SCAN_SIZE", "ROWS": "REJECTED_ROW_LIMIT", "WINDOW": "REJECTED_SCAN_SIZE",
            "COST": "REJECTED_JOIN_COST" if restricted else "REJECTED_COMPUTE_COST",
            "TIME": "REJECTED_TIMEOUT_RISK"}[violation]


def partitioning(bound: BoundExtraction, estimates: Estimates | None, limits: Limits, index_columns: set[str],
                 *, part_count: int = 1, runtime_violation: str | None = None) -> ExtractStop | None:
    """None when the extraction fits as it is; otherwise APPROVED_WITH_PARTITIONING with {kind, parts}, or the
    REJECTED_* status of the first limit no semantics-preserving split can meet.

    A DATE split narrows the window, so it reduces scanned rows only when an index leads with the time column; it
    always reduces result rows and sort cost. An ENTITY split reduces result rows and cost but never scanned rows.
    """
    days = bound.window_days()
    dated = bound.window is not None and days > 1
    has_entity = bool(bound.entity_column)
    time_indexed = bool(bound.time_column) and bound.time_column in index_columns
    restricted = bool(bound.restrictions)
    need: dict[str, int] = {}
    if bound.window is not None and days > limits.max_window_days:
        need["WINDOW"] = math.ceil(days / limits.max_window_days)
    if estimates is not None:
        if estimates.result_rows > limits.max_result_rows:
            need["ROWS"] = math.ceil(estimates.result_rows / (0.8 * limits.max_result_rows))
        if estimates.scan_rows > limits.max_scan_rows:
            need["SCAN"] = math.ceil(estimates.scan_rows / (0.8 * limits.max_scan_rows))
        if estimates.plan_cost > limits.max_plan_cost:
            need["COST"] = math.ceil(estimates.plan_cost / (0.8 * limits.max_plan_cost))
    if runtime_violation is not None:
        need[runtime_violation] = max(need.get(runtime_violation, 0), 2)
    if not need:
        return None
    details = {"estimates": estimates.__dict__ if estimates else None, "window_days": days,
               "time_index_available": time_indexed, "needed": need, "part_count": part_count}
    # which split can serve every violated limit
    kinds = []
    if dated and ("SCAN" not in need or time_indexed):
        kinds.append("DATE")
    if has_entity and "SCAN" not in need and "WINDOW" not in need:
        kinds.append("ENTITY")
    for violation in ("WINDOW", "SCAN", "ROWS", "COST", "TIME"):
        if violation in need and not kinds:
            reason = {"SCAN": "the planner estimates a scan above the limit and no index leads with the time "
                              "column, so no partition reduces it",
                      "WINDOW": "the window is longer than the limit and cannot be split"}.get(
                violation, "no date or entity split applies")
            return ExtractStop(_stop_for(violation, restricted), f"{violation}_LIMIT", f"The extraction {reason}.",
                               **details)
    kind = kinds[0]
    parts = max(need.values())
    if kind == "DATE" and parts > days:
        if has_entity and "SCAN" not in need and "WINDOW" not in need:
            kind = "ENTITY"
        else:
            parts = days
    if part_count * parts > limits.max_parts:
        worst = max(need, key=lambda k: need[k])
        return ExtractStop(_stop_for(worst, restricted), f"{worst}_LIMIT",
                           f"The extraction needs {part_count * parts} parts; the limit is {limits.max_parts}.",
                           **details, max_parts=limits.max_parts)
    return ExtractStop("APPROVED_WITH_PARTITIONING", f"{max(need, key=lambda k: need[k])}_LIMIT",
                       f"Split this extraction into {parts} {kind.lower()} partitions and submit each.",
                       partitioning={"kind": kind, "parts": parts}, **details)


def split_window(start: date, end: date, parts: int) -> list[tuple[date, date]]:
    """Contiguous, non-overlapping date windows covering [start, end] exactly (shared with the planner)."""
    days = (end - start).days + 1
    parts = max(1, min(parts, days))
    size = math.ceil(days / parts)
    windows, cursor = [], start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=size - 1))
        windows.append((cursor, stop))
        cursor = stop + timedelta(days=1)
    return windows
