"""Analysis Spec V2: one contract for both paths (ANALYSIS and RESEARCH), bound to catalog metadata.

The model writes one spec; nothing downstream lets it restate the scope. A V2 spec names

* analysis_type ANALYSIS | RESEARCH (a research spec is the same contract plus a required research block);
* its subject (data_domain, entity_type, asset_type) and every source table, checked against the catalog
  contract the SQL Governor returns (no table, column, relationship, frequency or subject is taken on trust);
* its scope: all eligible entities, an explicit entity list, or catalog-approved attribute predicates (AND of
  bounded typed predicates, each on a filterable catalog column), with provenance;
* an optional time scope: static reference questions (a count per group) have none; dated analysis must have
  one, with a frequency the source tables support;
* calculations and outputs (the V1 rules, plus generic GROUP_AGGREGATE, PERIOD_RETURN, GROUP/GROUP_DATE
  outputs with key columns, and top-N rankings).

normalize_v2() returns the canonical spec: the V2 fields plus the V1-shaped fields (universe, analysis_period,
frequency) the reviewer and validator already understand, so both versions share one implementation. It also
returns the data-plan contract: per logical input the exact filters and joins an extraction must have, which the
sandbox compares with the Governor's executed scope before any analysis runs. The compiler (market-ai-orc) builds
its requests from the same contract; neither side can widen or narrow the approved scope.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal

from pydantic import Discriminator, Field, StringConstraints, Tag

from .spec import (COLUMN, IDENT, TABLE, AnalysisSpec, Calculation, ExclusionRule, Loose, OutputSpec, Provenance,
                   ResearchBlock, SpecInvalid, SpecRequest, normalize_raw, resolve_period, sha256_json)

SPEC_VERSION_V2 = "analysis_spec/v2"
SUBJECT_ID = r"^[A-Z][A-Z0-9_]{1,39}$"
ENTITY_VALUE = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,19}$"
MAX_PREDICATES = 8
MAX_IN_VALUES = 100
NUMERIC = ("smallint", "integer", "bigint", "numeric", "real", "double precision")
ScopeProvenance = Literal["USER_EXPLICIT", "USER_CLARIFIED", "CATALOG_RESOLVED", "APPROVED_DEFAULT", "AI_INFERRED"]
Operator = Literal["EQ", "NEQ", "IN", "GT", "GTE", "LT", "LTE", "IS_NULL", "IS_NOT_NULL"]
Ident = Annotated[str, StringConstraints(pattern=IDENT)]
Column = Annotated[str, StringConstraints(pattern=COLUMN)]
Table = Annotated[str, StringConstraints(pattern=TABLE)]
SubjectId = Annotated[str, StringConstraints(pattern=SUBJECT_ID)]


class Subject(Loose):
    data_domain: SubjectId
    entity_type: SubjectId
    asset_type: SubjectId | None = None


class InputV2(Loose):
    name: Ident
    source_table: Table
    role: Literal["PRIMARY_DATA", "UNIVERSE", "REFERENCE"] = "PRIMARY_DATA"
    entity_column: Column | None = None
    date_column: Column | None = None
    columns: list[Column] = Field(min_length=1, max_length=50)


class RelationshipRef(Loose):
    relationship_id: int = Field(ge=1)


class ScopePredicate(Loose):
    input: Ident
    table: Table
    column: Column
    operator: Operator
    value: str | int | float | bool | list[str | int | float] | None
    provenance: ScopeProvenance
    user_text: Annotated[str, StringConstraints(max_length=200)] | None = None


class Scope(Loose):
    selection_type: Literal["ALL_ELIGIBLE", "ENTITY_LIST", "ATTRIBUTE_FILTER"]
    entities: list[Annotated[str, StringConstraints(pattern=ENTITY_VALUE)]] | None = Field(default=None, max_length=200)
    predicates: list[ScopePredicate] | None = Field(default=None, max_length=MAX_PREDICATES)
    provenance: Provenance
    default_id: str | None = None


class TimeScope(Loose):
    mode: Literal["EXPLICIT_DATES", "TRAILING", "TRADING_DAYS", "LATEST"]
    start: date | None = None
    end: date | None = None
    unit: Literal["DAY", "WEEK", "MONTH", "YEAR"] | None = None
    count: int | None = Field(default=None, ge=1, le=3650)
    frequency: Literal["1D", "1W", "1M"]
    provenance: Provenance
    default_id: str | None = None


class AnalysisSpecV2(Loose):
    spec_version: Literal["2.0"]
    analysis_type: Literal["ANALYSIS", "RESEARCH"]
    question: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    subject: Subject
    inputs: list[InputV2] = Field(min_length=1, max_length=4)
    relationships: list[RelationshipRef] = Field(default_factory=list, max_length=5)
    scope: Scope
    time_scope: TimeScope | None
    calculations: list[Calculation] = Field(min_length=1, max_length=12)
    outputs: list[OutputSpec] = Field(min_length=1, max_length=8)
    exclusion_rules: list[ExclusionRule] = Field(default_factory=list, max_length=8)
    research: ResearchBlock | None = None


def _version(value: Any) -> str:
    if isinstance(value, dict):
        return "v2" if "spec_version" in value else "v1"
    return "v2" if isinstance(value, AnalysisSpecV2) else "v1"


class SpecRequestAny(SpecRequest):
    """POST /v1/specs: an Analysis Spec V2 (has spec_version) or a V1 spec (kept for stored/older callers; V1 is
    never reinterpreted as V2)."""

    spec: Annotated[Annotated[AnalysisSpec, Tag("v1")] | Annotated[AnalysisSpecV2, Tag("v2")],
                    Discriminator(_version)]


def catalog_tables(spec: AnalysisSpecV2) -> list[str]:
    tables = [i.source_table for i in spec.inputs]
    tables += [p.table for p in spec.scope.predicates or []]
    return sorted(dict.fromkeys(tables))


# ---------------------------------------------------------------- canonical values (shared with the Governor)

def canonical_value(value: Any) -> str:
    """Must equal apps/market-sql-governor/app/catalog_contract.py canonical_value (tests compare them)."""
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


def _typed(value: Any, data_type: str, label: str, problems: list[str]) -> Any:
    """Coerce a predicate value to the catalog column type the way the Governor will (invalid -> problem)."""
    kind = data_type.lower()
    try:
        if isinstance(value, bool) and kind != "boolean":
            raise ValueError
        if kind == "date":
            return date.fromisoformat(value) if isinstance(value, str) else _raise()
        if kind.startswith("timestamp"):
            return datetime.fromisoformat(value) if isinstance(value, str) else _raise()
        if kind in ("smallint", "integer", "bigint"):
            if isinstance(value, str) or (isinstance(value, float) and not value.is_integer()):
                raise ValueError
            return int(value)
        if kind in ("numeric", "real", "double precision"):
            if isinstance(value, str):
                raise ValueError
            return Decimal(str(value))
        if kind == "boolean":
            return value if isinstance(value, bool) else _raise()
        if not isinstance(value, str) or len(value) > 200:
            raise ValueError
        return value
    except (ValueError, TypeError, InvalidOperation):
        problems.append(f"{label}: value {value!r} does not match the catalog type {data_type} (INVALID_PREDICATE_VALUE)")
        return None


def _raise():
    raise ValueError


# ---------------------------------------------------------------- normalization

def _catalog_problem(problems: list[str], message: str, code: str) -> None:
    problems.append(f"{message} ({code})")


def normalize_v2(spec: AnalysisSpecV2, ref: date, catalog: dict[str, Any]) -> dict[str, Any]:
    """Validate a V2 spec against the catalog contract and return the canonical spec (V2 + V1-shaped fields).

    Raises SpecInvalid with every problem found (each names a machine-readable code in parentheses)."""
    raw = spec.model_dump(mode="json")
    problems: list[str] = []
    tables = catalog.get("tables") or {}
    columns = catalog.get("columns") or {}
    relationships = {r["relationship_id"]: r for r in catalog.get("relationships") or []}
    subject = raw["subject"]

    # analysis type and research block
    if raw["analysis_type"] == "ANALYSIS" and raw["research"] is not None:
        _catalog_problem(problems, "analysis_type ANALYSIS must have research null; use RESEARCH for a research "
                                   "question", "ANALYSIS_TYPE_RESEARCH_MISMATCH")
    if raw["analysis_type"] == "RESEARCH" and raw["research"] is None:
        _catalog_problem(problems, "analysis_type RESEARCH needs a research block", "RESEARCH_BLOCK_REQUIRED")

    # inputs: tables, subject, columns, keys
    inputs: dict[str, dict[str, Any]] = {}
    for item in raw["inputs"]:
        where = f"input {item['name']}"
        meta = tables.get(item["source_table"])
        if meta is None:
            _catalog_problem(problems, f"{where}: {item['source_table']} is not an approved catalog table",
                             "UNKNOWN_TABLE")
            inputs[item["name"]] = item
            continue
        if item["role"] != "REFERENCE":
            actual = {k: meta.get(k) for k in ("data_domain", "entity_type", "asset_type")}
            if actual != subject:
                _catalog_problem(problems, f"{where}: {item['source_table']} is {actual} in the catalog, not the spec "
                                           f"subject {subject}", "SUBJECT_TABLE_MISMATCH")
        allowed = columns.get(item["source_table"]) or {}
        unknown = [c for c in item["columns"] if c not in allowed]
        if unknown:
            _catalog_problem(problems, f"{where}: columns {unknown} are not AI-allowed columns of "
                                       f"{item['source_table']}", "UNKNOWN_COLUMN")
        for key, catalog_key in (("entity_column", "entity_column"), ("date_column", "time_column")):
            expected = meta.get(catalog_key)
            if item[key] is not None and item[key] != expected:
                _catalog_problem(problems, f"{where}: {key} {item[key]!r} is not the catalog {catalog_key} "
                                           f"{expected!r} of {item['source_table']}", "KEY_COLUMN_MISMATCH")
            item[key] = expected
            if expected and expected not in item["columns"]:
                item["columns"].append(expected)  # keys are always extracted
        item["is_static"] = meta.get("time_column") is None
        item["catalog_table_sha256"] = meta.get("catalog_table_sha256")
        inputs[item["name"]] = item
    if len(inputs) != len(raw["inputs"]):
        problems.append("inputs: names must be unique")
    scoped = [i for i in inputs.values() if i["role"] != "REFERENCE"]
    if not scoped:
        _catalog_problem(problems, "inputs: at least one input must be PRIMARY_DATA or UNIVERSE", "NO_SCOPED_INPUT")

    # time scope and frequency
    dated = [i for i in inputs.values() if i.get("is_static") is False]
    time_scope = raw["time_scope"]
    if dated and time_scope is None:
        _catalog_problem(problems, f"time_scope: inputs {[i['name'] for i in dated]} are dated; a dated analysis "
                                   f"needs a time scope and frequency", "TIME_SCOPE_REQUIRED")
    if not dated and time_scope is not None:
        _catalog_problem(problems, "time_scope: every input is static reference data; do not invent a period",
                         "TIME_SCOPE_NOT_APPLICABLE")
    if time_scope is not None:
        for item in dated:
            supported = (tables.get(item["source_table"]) or {}).get("supported_frequencies") or []
            if time_scope["frequency"] not in supported:
                _catalog_problem(problems, f"time_scope: frequency {time_scope['frequency']} is not supported by "
                                           f"{item['source_table']} ({supported})", "FREQUENCY_NOT_SUPPORTED")

    # relationships
    input_tables = {i["source_table"] for i in inputs.values()}
    declared: dict[int, dict[str, Any]] = {}
    for ref_item in raw["relationships"]:
        rel = relationships.get(ref_item["relationship_id"])
        where = f"relationship {ref_item['relationship_id']}"
        if rel is None:
            _catalog_problem(problems, f"{where} is not a catalog relationship of the spec's tables",
                             "UNKNOWN_RELATIONSHIP")
            continue
        if not rel["is_allowed"] or rel["requires_preaggregation"]:
            _catalog_problem(problems, f"{where} is not allowed for a row-level join", "RELATIONSHIP_NOT_ALLOWED")
            continue
        if not {rel["left_table"], rel["right_table"]} <= input_tables:
            _catalog_problem(problems, f"{where} joins {rel['left_table']} and {rel['right_table']}; both must be "
                                       f"input tables", "RELATIONSHIP_NOT_APPLICABLE")
            continue
        declared[rel["relationship_id"]] = rel

    # scope
    scope = raw["scope"]
    selection = scope["selection_type"]
    predicates: list[dict[str, Any]] = []
    if selection == "ALL_ELIGIBLE" and (scope["entities"] or scope["predicates"]):
        _catalog_problem(problems, "scope: ALL_ELIGIBLE takes no entities or predicates", "SCOPE_SHAPE_INVALID")
    if selection == "ENTITY_LIST" and (not scope["entities"] or scope["predicates"]):
        _catalog_problem(problems, "scope: ENTITY_LIST takes a non-empty entities list and no predicates",
                         "SCOPE_SHAPE_INVALID")
    if selection == "ATTRIBUTE_FILTER" and (not scope["predicates"] or scope["entities"]):
        _catalog_problem(problems, "scope: ATTRIBUTE_FILTER takes 1-8 predicates and no entities", "SCOPE_SHAPE_INVALID")
    for index, predicate in enumerate(scope["predicates"] or []):
        where = f"scope predicate {index + 1} ({predicate['table']}.{predicate['column']})"
        owner = inputs.get(predicate["input"])
        if owner is None or owner["source_table"] != predicate["table"]:
            _catalog_problem(problems, f"{where}: input {predicate['input']!r} must be an input reading "
                                       f"{predicate['table']}", "PREDICATE_INPUT_MISMATCH")
            continue
        meta = (columns.get(predicate["table"]) or {}).get(predicate["column"])
        if meta is None:
            _catalog_problem(problems, f"{where}: not an AI-allowed catalog column", "UNKNOWN_COLUMN")
            continue
        if not meta["filter_allowed"]:
            _catalog_problem(problems, f"{where}: the catalog does not allow filtering this column",
                             "FILTER_NOT_ALLOWED")
            continue
        if predicate["column"] not in owner["columns"]:
            owner["columns"].append(predicate["column"])  # the validator re-checks membership on this column
        values = _predicate_values(predicate, meta["data_type"], where, problems)
        if values is None:
            continue
        if predicate["provenance"] == "CATALOG_RESOLVED" and not (predicate["user_text"] or "").strip():
            _catalog_problem(problems, f"{where}: a CATALOG_RESOLVED predicate names the user's words it resolves "
                                       f"(user_text)", "PREDICATE_USER_TEXT_REQUIRED")
        predicates.append({"input": predicate["input"], "table": predicate["table"], "column": predicate["column"],
                           "operator": predicate["operator"], "values": values, "data_type": meta["data_type"],
                           "provenance": predicate["provenance"], "user_text": predicate["user_text"]})
    if selection == "ENTITY_LIST":
        for item in scoped:
            meta = tables.get(item["source_table"]) or {}
            if meta and meta.get("entity_type") != subject["entity_type"]:
                _catalog_problem(problems, f"input {item['name']}: its entities are {meta.get('entity_type')}, not "
                                           f"the listed {subject['entity_type']} entities", "ENTITY_TYPE_MISMATCH")

    plan = _data_plan(inputs, predicates, declared, scope, columns, problems)

    # V1-shaped fields for the shared rules, reviewer and validator
    legacy = dict(raw)
    legacy["inputs"] = [{k: v for k, v in i.items()} for i in inputs.values()]
    if selection == "ENTITY_LIST":
        legacy["universe"] = {"type": "TICKERS", "tickers": sorted(set(scope["entities"] or [])),
                              "provenance": scope["provenance"], "default_id": scope["default_id"]}
    else:
        legacy["universe"] = {"type": "ALL_IN_SOURCE", "tickers": None, "provenance": scope["provenance"],
                              "default_id": scope["default_id"]}
    if time_scope is None:
        legacy["analysis_period"] = {"mode": "STATIC", "start": None, "end": None, "unit": None, "count": None,
                                     "provenance": "AI_INFERRED", "default_id": None}
        legacy["frequency"] = {"value": "STATIC", "provenance": "AI_INFERRED", "default_id": None}
    else:
        legacy["analysis_period"] = {k: time_scope[k] for k in ("mode", "start", "end", "unit", "count", "provenance",
                                                                 "default_id")}
        legacy["frequency"] = {"value": time_scope["frequency"], "provenance": time_scope["provenance"],
                               "default_id": time_scope["default_id"]}
    for name in ("spec_version", "analysis_type", "subject", "relationships", "scope", "time_scope"):
        legacy.pop(name, None)
    try:
        canonical = normalize_raw(legacy, ref, problems)
    except SpecInvalid:
        canonical = None
    if canonical is not None:
        _check_group_keys(canonical, inputs, columns, problems)
    if problems:
        raise SpecInvalid(problems)
    assert canonical is not None
    canonical.update(
        spec_version="2.0", analysis_type=raw["analysis_type"], subject=subject,
        relationships=[{"relationship_id": rid, **{k: declared[rid][k] for k in (
            "left_table", "left_columns", "right_table", "right_columns", "relationship_type", "temporal_rule")}}
                       for rid in sorted(declared)],
        scope={"selection_type": selection, "entities": sorted(set(scope["entities"] or [])) or None,
               "predicates": predicates, "logic": "ALL", "provenance": scope["provenance"],
               "default_id": scope["default_id"]},
        time_scope=time_scope, data_plan=plan)
    return canonical


def _predicate_values(predicate: dict[str, Any], data_type: str, where: str, problems: list[str]) -> list[str] | None:
    operator, value = predicate["operator"], predicate["value"]
    if operator in ("IS_NULL", "IS_NOT_NULL"):
        if value is not None:
            _catalog_problem(problems, f"{where}: {operator} takes value null", "INVALID_PREDICATE_VALUE")
            return None
        return []
    if operator == "IN":
        if not isinstance(value, list) or not 1 <= len(value) <= MAX_IN_VALUES:
            _catalog_problem(problems, f"{where}: IN needs a list of 1-{MAX_IN_VALUES} values", "INVALID_PREDICATE_VALUE")
            return None
        typed = [_typed(v, data_type, where, problems) for v in value]
    else:
        if value is None or isinstance(value, list):
            _catalog_problem(problems, f"{where}: {operator} needs one scalar value", "INVALID_PREDICATE_VALUE")
            return None
        typed = [_typed(value, data_type, where, problems)]
    if any(v is None for v in typed):
        return None
    if operator in ("GT", "GTE", "LT", "LTE") and data_type.lower() not in NUMERIC + ("date",) \
            and not data_type.lower().startswith("timestamp"):
        _catalog_problem(problems, f"{where}: {operator} needs a numeric or date column", "INVALID_PREDICATE_VALUE")
        return None
    return sorted(dict.fromkeys(canonical_value(v) for v in typed))


def _data_plan(inputs: dict[str, dict[str, Any]], predicates: list[dict[str, Any]],
               declared: dict[int, dict[str, Any]], scope: dict[str, Any], columns: dict[str, Any],
               problems: list[str]) -> dict[str, Any]:
    """Per logical input: the exact filters and joins its extraction must carry (dates are added from
    required_input once the period is resolved). REFERENCE inputs are not scoped."""
    plan: dict[str, Any] = {}
    for item in inputs.values():
        entry = {"input": item["name"], "source_table": item["source_table"], "role": item["role"],
                 "entity_column": item.get("entity_column"), "time_column": item.get("date_column"),
                 "columns": list(item["columns"]), "joins": [], "filters": []}
        if item["role"] != "REFERENCE":
            for predicate in predicates:
                if predicate["table"] != item["source_table"]:
                    links = [rid for rid, rel in declared.items()
                             if {rel["left_table"], rel["right_table"]} == {item["source_table"], predicate["table"]}]
                    if len(links) != 1:
                        _catalog_problem(problems, f"input {item['name']}: predicate on {predicate['table']} cannot be "
                                                   f"applied; declare exactly one catalog relationship between "
                                                   f"{item['source_table']} and {predicate['table']}",
                                         "SCOPE_NOT_APPLICABLE_TO_INPUT")
                        continue
                    join = {"table": predicate["table"], "relationship_id": links[0]}
                    if join not in entry["joins"]:
                        entry["joins"].append(join)
                entry["filters"].append({"table": predicate["table"], "column": predicate["column"],
                                         "operator": predicate["operator"], "values": predicate["values"],
                                         "data_type": predicate["data_type"]})
            if scope["selection_type"] == "ENTITY_LIST" and item.get("entity_column"):
                meta = (columns.get(item["source_table"]) or {}).get(item["entity_column"]) or {}
                entry["filters"].append({"table": item["source_table"], "column": item["entity_column"],
                                         "operator": "IN", "values": sorted(set(scope["entities"] or [])),
                                         "data_type": meta.get("data_type", "text")})
        entry["filters"] = sorted(entry["filters"], key=lambda f: (f["table"], f["column"], f["operator"],
                                                                   f["values"]))
        plan[item["name"]] = entry
    return plan


def _check_group_keys(spec: dict[str, Any], inputs: dict[str, dict[str, Any]], columns: dict[str, Any],
                      problems: list[str]) -> None:
    for calc in spec["calculations"]:
        if calc["method"] != "GROUP_AGGREGATE":
            continue
        function = next((p["value"] for p in calc["params"] if p["name"] == "function"), None)
        for key in calc.get("group_by") or []:
            owner = inputs.get(key["input"]) or {}
            meta = (columns.get(owner.get("source_table")) or {}).get(key["column"])
            if meta is None or not meta["group_by_allowed"]:
                _catalog_problem(problems, f"calculation {calc['id']}: {owner.get('source_table')}.{key['column']} "
                                           f"cannot be a grouping key in the catalog", "GROUP_BY_NOT_ALLOWED")
            if owner and owner["name"] != calc["dataset"] and not owner.get("entity_column"):
                _catalog_problem(problems, f"calculation {calc['id']}: grouping input {owner['name']} has no entity "
                                           f"column to map entities to groups", "GROUP_KEY_NOT_MAPPABLE")
        if function in ("SUM", "AVG", "MEDIAN") and calc["columns"]:
            owner = inputs.get(calc["dataset"]) or {}
            meta = (columns.get(owner.get("source_table")) or {}).get(calc["columns"][0]) or {}
            if meta and meta.get("data_type") not in NUMERIC:
                _catalog_problem(problems, f"calculation {calc['id']}: {function} needs a numeric column",
                                 "AGGREGATION_NOT_NUMERIC")


def scope_document(spec: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    """The canonical approved scope: subject, sources, relationships, predicates, entities, and resolved time."""
    return {
        "spec_version": spec["spec_version"], "analysis_type": spec["analysis_type"], "subject": spec["subject"],
        "inputs": sorted(({"name": i["name"], "table": i["source_table"], "role": i["role"],
                           "entity_column": i.get("entity_column"), "time_column": i.get("date_column")}
                          for i in spec["inputs"]), key=lambda i: i["name"]),
        "relationships": sorted(r["relationship_id"] for r in spec["relationships"]),
        "selection_type": spec["scope"]["selection_type"], "entities": spec["scope"]["entities"],
        "predicates": sorted(({k: p[k] for k in ("input", "table", "column", "operator", "values")}
                              for p in spec["scope"]["predicates"]),
                             key=lambda p: (p["input"], p["table"], p["column"], p["operator"], p["values"])),
        "time": None if spec["time_scope"] is None else {
            "mode": resolved.get("mode"), "start": resolved.get("start"), "end": resolved.get("end"),
            "trading_days": resolved.get("trading_days"), "frequency": spec["time_scope"]["frequency"]},
    }


def scope_sha256(spec: dict[str, Any], resolved: dict[str, Any]) -> str:
    return sha256_json(scope_document(spec, resolved))


def review_scope(spec: dict[str, Any], user_text: str) -> list[tuple[str, str, Any, Any, str, str | None]]:
    """Provenance checks of the attribute predicates against the user's own words (no topic vocabulary):
    a value claimed as stated by the user must appear in the request; a catalog-resolved value must name the
    user's words it resolves, and those words must appear in the request."""
    text = user_text.lower()
    checks = []
    for predicate in spec["scope"]["predicates"]:
        name = f"scope.{predicate['table']}.{predicate['column']}"
        shown = f"{predicate['column']} {predicate['operator']} {predicate['values']}"
        provenance = predicate["provenance"]
        if provenance in ("USER_EXPLICIT", "USER_CLARIFIED"):
            stated = all(re.search(rf"(?<!\w){re.escape(v.lower())}(?!\w)", text) for v in predicate["values"])
            checks.append((name, "MATCH" if stated else "UNVERIFIED", predicate["values"] if stated else None, shown,
                           "The request states this value." if stated else
                           "Marked as stated by the user, but the value does not appear in the request.", None))
        elif provenance == "CATALOG_RESOLVED":
            words = (predicate.get("user_text") or "").strip().lower()
            if words and re.search(rf"(?<!\w){re.escape(words)}(?!\w)", text):
                checks.append((name, "UNVERIFIED", predicate["user_text"], shown,
                               f"'{predicate['user_text']}' in the request was resolved to the catalog value "
                               f"{predicate['values']}; disclose this interpretation.", None))
            else:
                checks.append((name, "MISMATCH", predicate.get("user_text"), shown,
                               "The words this predicate claims to resolve do not appear in the request.",
                               "SCOPE_PREDICATE_UNSUPPORTED"))
        else:
            checks.append((name, "UNVERIFIED", None, shown, "A scope restriction chosen by the AI, not stated by the "
                                                            "user.", None))
    return checks


def resolved_for_hash(spec: dict[str, Any], ref: date) -> dict[str, Any]:
    return resolve_period(spec["analysis_period"], ref)
