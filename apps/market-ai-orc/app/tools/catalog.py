from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..compaction import dumps
from .registry import ToolError, ToolSpec
from .system import NoArguments


QueryRunner = Callable[[str, tuple[Any, ...]], list[dict[str, Any]]]


class CatalogReader(Protocol):
    def read_only(self) -> AbstractContextManager[QueryRunner]: ...


Section = Literal["COLUMNS", "RELATIONSHIPS", "CALCULATIONS", "COVERAGE", "RESEARCH", "FORMULAS"]

MAX_TABLES_PER_CALL = 3
MAX_COLUMN_FILTER = 40
MAX_ENTITY_IDS = 20
MAX_METHOD_IDS = 40
MAX_FORMULA_IDS = 40
MAX_DISCOVERED_TABLES = 50
ROW_CAPS = {"COLUMNS": 150, "RELATIONSHIPS": 50, "CALCULATIONS": 100, "RESEARCH": 50,
            "FORMULAS": 50, "STATUS": 60, "ENTITIES": 60}
# Stays below the registry's 32 KB hard cap once the {"ok","tool","result"} wrapper is added.
RESULT_BUDGET_BYTES = 24000
# Small sections are filled first so large ones cannot starve them; output keeps request order.
ALLOCATION_ORDER = ("RELATIONSHIPS", "COVERAGE", "COLUMNS", "CALCULATIONS", "RESEARCH", "FORMULAS")

TABLE_NAME = re.compile(r"^[A-Za-z0-9_]{1,63}$")
COLUMN_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_ ]{0,62}$")
ENTITY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
METHOD_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
FORMULA_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")

METADATA_NOTICE = "Catalog metadata is documentation. It contains no observed market values or calculation results."
VISIBILITY_NOTE = (
    "This targeted view applies the catalog visibility flags (inactive/denied tables, disallowed or "
    "sensitive columns, disallowed relationships, inactive calculations are excluded); "
    "read_catalog_rows returns every catalog row including those."
)
ABSENT_FIELDS_NOTE = "Fields absent from an entry are NULL or empty in the catalog."

VISIBLE_TABLES = '''
    SELECT table_name FROM public."AI_table_catalog"
    WHERE is_active AND ai_access_level = 'BOUNDED_READ'
'''

DISCOVER_SQL = f'''
WITH visible AS ({VISIBLE_TABLES})
SELECT t.table_name, t.description, t.category, t.grain, t.primary_key_columns,
       t.time_column, t.entity_column, t.documentation_status, t.coverage_enabled,
       t.freshness_sla::text AS freshness_sla,
       -- subject metadata (migration 20260925_001); to_jsonb keeps this query valid before that migration
       to_jsonb(t) ->> 'data_domain' AS data_domain, to_jsonb(t) ->> 'entity_type' AS entity_type,
       to_jsonb(t) ->> 'asset_type' AS asset_type, to_jsonb(t) -> 'supported_frequencies' AS supported_frequencies,
       to_jsonb(t) ->> 'time_semantics' AS time_semantics,
       to_jsonb(t) ->> 'subject_metadata_status' AS subject_metadata_status,
       (SELECT count(*) FROM public."AI_column_catalog" c
         WHERE c.table_name = t.table_name AND c.ai_allowed AND NOT c.is_sensitive) AS column_count,
       (SELECT count(*) FROM public."AI_calculation_catalog" k
         WHERE k.target_table = t.table_name AND k.status = 'ACTIVE') AS calculation_count,
       (SELECT count(*) FROM public."AI_catalog_relationships" r
         WHERE r.is_allowed AND t.table_name IN (r.left_table, r.right_table)
           AND r.left_table IN (SELECT table_name FROM visible)
           AND r.right_table IN (SELECT table_name FROM visible)) AS relationship_count
FROM public."AI_table_catalog" t
WHERE t.table_name IN (SELECT table_name FROM visible)
ORDER BY t.table_name
LIMIT %s
'''

RESEARCH_COUNTS_SQL = '''
SELECT implementation_status, count(*) AS method_count
FROM public."AI_research_catalog"
GROUP BY implementation_status ORDER BY implementation_status
'''

RESOLVE_TABLES_SQL = f'''
SELECT t.table_name, t.coverage_enabled
FROM public."AI_table_catalog" t
WHERE t.table_name IN ({VISIBLE_TABLES}) AND t.table_name = ANY(%s)
'''

COLUMNS_SQL = '''
SELECT table_name, column_name, description, data_type, semantic_type, unit, nullable,
       is_primary_key, source_column_or_expression, allowed_aggregations, filter_allowed,
       group_by_allowed, example_value, documentation_status,
       count(*) OVER () AS total_matching
FROM public."AI_column_catalog"
WHERE table_name = ANY(%s) AND ai_allowed AND NOT is_sensitive
  AND (%s::text[] IS NULL OR column_name = ANY(%s::text[]))
ORDER BY table_name, ordinal_position
LIMIT %s
'''

FOUND_COLUMNS_SQL = '''
SELECT DISTINCT column_name FROM public."AI_column_catalog"
WHERE table_name = ANY(%s) AND ai_allowed AND NOT is_sensitive AND column_name = ANY(%s)
'''

RELATIONSHIPS_SQL = f'''
WITH visible AS ({VISIBLE_TABLES})
SELECT relationship_id, left_table, left_columns, right_table, right_columns,
       relationship_type, temporal_rule, safe_output_grain, requires_preaggregation,
       description, version, count(*) OVER () AS total_matching
FROM public."AI_catalog_relationships"
WHERE is_allowed AND (left_table = ANY(%s) OR right_table = ANY(%s))
  AND left_table IN (SELECT table_name FROM visible)
  AND right_table IN (SELECT table_name FROM visible)
ORDER BY relationship_id
LIMIT %s
'''

CALCULATIONS_SQL = '''
SELECT target_table, calculation_name, version, status, target_columns, definition, required_inputs,
       parameters, defaults, alignment_rules, missing_data_policy, output_definition, validation_evidence,
       count(*) OVER () AS total_matching
FROM public."AI_calculation_catalog"
WHERE target_table = ANY(%s) AND status = 'ACTIVE'
  AND (%s::text[] IS NULL OR target_columns && %s::text[])
ORDER BY target_table, calculation_name, version
LIMIT %s
'''

RESEARCH_SQL = '''
SELECT method_id, method_name, category, purpose, example_question, analysis_kind, input_grain,
       required_inputs_json, optional_inputs_json, future_outcome_required, supports_numeric_directly,
       preprocessing, parameter_keys_json, expected_outputs_json, validation_requirements_json,
       main_risks, compute_strategy, tool_or_library_examples, implementation_status,
       count(*) OVER () AS total_matching
FROM public."AI_research_catalog"
WHERE (%s::text[] IS NULL OR method_id = ANY(%s::text[]))
ORDER BY method_id LIMIT %s
'''

FORMULA_COUNT_SQL = 'SELECT count(*) AS formula_count FROM public."AI_formula_reference"'

FORMULAS_SQL = '''
SELECT calculation_id, calculation_name, description, required_inputs, formula_method,
       parameters, output, implementation, count(*) OVER () AS total_matching
FROM public."AI_formula_reference"
WHERE (%s::text[] IS NULL OR calculation_id = ANY(%s::text[]))
ORDER BY calculation_id LIMIT %s
'''

COVERAGE_DATASET_SQL = '''
SELECT dataset_name, coverage_mode, reference_dataset_name, actual_min_date, actual_max_date,
       expected_min_date, expected_max_date, source_row_count, source_key_count,
       pipeline_status, verification_status, quality_status, check_error,
       last_checked_at, last_full_checked_at
FROM public."AI_data_coverage"
WHERE coverage_scope = 'DATASET' AND dataset_name = ANY(%s)
ORDER BY dataset_name
'''

COVERAGE_STATUS_SQL = '''
SELECT dataset_name, pipeline_status, verification_status, quality_status,
       count(*) AS entity_count
FROM public."AI_data_coverage"
WHERE coverage_scope = 'ENTITY' AND dataset_name = ANY(%s)
GROUP BY dataset_name, pipeline_status, verification_status, quality_status
ORDER BY dataset_name, entity_count DESC, pipeline_status, verification_status, quality_status
LIMIT %s
'''

COVERAGE_ENTITIES_SQL = '''
SELECT dataset_name, entity_id, coverage_mode, reference_dataset_name, actual_min_date,
       actual_max_date, expected_min_date, expected_max_date, source_row_count,
       source_key_count, pipeline_status, verification_status, quality_status, check_error,
       last_checked_at
FROM public."AI_data_coverage"
WHERE coverage_scope = 'ENTITY' AND dataset_name = ANY(%s) AND entity_id = ANY(%s)
ORDER BY dataset_name, entity_id
LIMIT %s
'''


def _availability(row: dict[str, Any]) -> str:
    """Plain reading of coverage_mode x verification_status; an expected range is never confirmation."""
    mode, verification = row.get("coverage_mode"), row.get("verification_status")
    if mode == "ACTUAL_SOURCE" and verification == "VERIFIED":
        return "CONFIRMED_SOURCE_RANGE: actual_min_date..actual_max_date was observed in the source table."
    if mode == "SNAPSHOT":
        return "SNAPSHOT: current-state reference data; no historical date range."
    if mode == "EXPECTED_DERIVED" and verification == "PIPELINE_CONFIRMED":
        return "PIPELINE_CONFIRMED: the derivation pipeline reported success for the expected range."
    if mode == "EXPECTED_DERIVED":
        return ("EXPECTED_NOT_CONFIRMED: expected_min_date..expected_max_date is derived from the source and is "
                "not confirmed physical availability.")
    return f"UNCLASSIFIED: coverage_mode={mode}, verification_status={verification}."


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _checked(values: list[str], pattern: re.Pattern[str], label: str, limit: int) -> list[str]:
    values = _unique([value.strip() for value in values])
    if not values:
        raise ValueError(f"at least one {label} is required")
    if len(values) > limit:
        raise ValueError(f"at most {limit} {label}s are allowed per call")
    invalid = [value for value in values if not pattern.fullmatch(value)]
    if invalid:
        raise ValueError(f"invalid {label}: {invalid[:3]}")
    return values


class CatalogDetailsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_names: list[str] = Field(
        description=f"1-{MAX_TABLES_PER_CALL} exact market table names, or [] for RESEARCH only."
    )
    sections: list[Section] = Field(
        description="Metadata sections: COLUMNS, RELATIONSHIPS, CALCULATIONS, COVERAGE, RESEARCH."
    )
    column_names: list[str] | None = Field(
        description=(
            f"Optional 1-{MAX_COLUMN_FILTER} exact column names that narrow COLUMNS and "
            "CALCULATIONS. Use null for all columns."
        )
    )
    entity_ids: list[str] | None = Field(
        description=(
            f"Optional 1-{MAX_ENTITY_IDS} exact entity identifiers such as tickers, adding "
            "per-entity rows to COVERAGE. Use null for dataset-level coverage only."
        )
    )
    method_ids: list[str] | None = Field(
        description=f"Optional 1-{MAX_METHOD_IDS} exact research method_id values; null lists all methods."
    )
    formula_ids: list[str] | None = Field(
        description=f"Optional 1-{MAX_FORMULA_IDS} exact formula calculation_id values; null lists all formulas."
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_args(cls, value: Any) -> Any:
        # Existing internal callers may omit newer fields; provider strict schemas require them.
        return {"method_ids": None, "formula_ids": None, **value} if isinstance(value, dict) else value

    @field_validator("table_names")
    @classmethod
    def _tables(cls, value: list[str]) -> list[str]:
        return _checked(value, TABLE_NAME, "table name", MAX_TABLES_PER_CALL) if value else []

    @model_validator(mode="after")
    def _required_tables(self) -> "CatalogDetailsArguments":
        table_free_sections = {"RESEARCH", "FORMULAS"}
        if not self.table_names and any(section not in table_free_sections for section in self.sections):
            raise ValueError("table_names are required for market-table metadata sections")
        return self

    @field_validator("sections")
    @classmethod
    def _sections(cls, value: list[str]) -> list[str]:
        value = _unique(value)
        if not value:
            raise ValueError("at least one section is required")
        return value

    @field_validator("column_names")
    @classmethod
    def _columns(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _checked(value, COLUMN_NAME, "column name", MAX_COLUMN_FILTER)

    @field_validator("entity_ids")
    @classmethod
    def _entities(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _checked(value, ENTITY_ID, "entity id", MAX_ENTITY_IDS)

    @field_validator("method_ids")
    @classmethod
    def _methods(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _checked(value, METHOD_ID, "method id", MAX_METHOD_IDS)

    @field_validator("formula_ids")
    @classmethod
    def _formulas(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _checked(value, FORMULA_ID, "formula id", MAX_FORMULA_IDS)


def _plain(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _entry(row: dict[str, Any], fields: tuple[str, ...], keep_null: tuple[str, ...] = ()) -> dict[str, Any]:
    """Copy catalog fields verbatim; omit NULL/empty values except explicitly meaningful ones."""
    entry: dict[str, Any] = {}
    for name in fields:
        value = _plain(row.get(name))
        if value is None or value == [] or value == {}:
            if name in keep_null:
                entry[name] = None
            continue
        entry[name] = value
    return entry


def _size(value: Any) -> int:
    return len(dumps(value).encode("utf-8"))


def _fit(entries: list[dict[str, Any]], budget: int) -> tuple[list[dict[str, Any]], bool]:
    kept: list[dict[str, Any]] = []
    used = 2
    for entry in entries:
        cost = _size(entry) + 1
        if used + cost > budget:
            return kept, True
        kept.append(entry)
        used += cost
    return kept, False


def _group(entries: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        entry = dict(entry)
        grouped.setdefault(entry.pop(key), []).append(entry)
    return grouped


COLUMN_FULL = (
    "table_name", "column_name", "description", "data_type", "semantic_type", "unit", "nullable",
    "is_primary_key", "source_column_or_expression", "allowed_aggregations", "filter_allowed",
    "group_by_allowed", "example_value", "documentation_status",
)
COLUMN_SUMMARY = ("table_name", "column_name", "description", "data_type", "semantic_type", "unit")
CALCULATION_FULL = (
    "target_table", "calculation_name", "version", "status", "target_columns", "definition",
    "required_inputs", "parameters", "defaults", "alignment_rules", "missing_data_policy",
    "output_definition", "validation_evidence",
)
CALCULATION_SUMMARY = ("target_table", "calculation_name", "version", "target_columns", "definition")
RESEARCH_FULL = (
    "method_id", "method_name", "category", "purpose", "example_question", "analysis_kind", "input_grain",
    "required_inputs_json", "optional_inputs_json", "future_outcome_required", "supports_numeric_directly",
    "preprocessing", "parameter_keys_json", "expected_outputs_json", "validation_requirements_json",
    "main_risks", "compute_strategy", "tool_or_library_examples", "implementation_status",
)
RESEARCH_SUMMARY = ("method_id", "method_name", "category", "purpose", "implementation_status")
FORMULA_FULL = (
    "calculation_id", "calculation_name", "description", "required_inputs", "formula_method",
    "parameters", "output", "implementation",
)
FORMULA_SUMMARY = ("calculation_id", "calculation_name", "output")
RELATIONSHIP_FIELDS = (
    "relationship_id", "left_table", "left_columns", "right_table", "right_columns",
    "relationship_type", "temporal_rule", "safe_output_grain", "requires_preaggregation",
    "description", "version",
)
COVERAGE_FIELDS = (
    "coverage_mode", "reference_dataset_name", "actual_min_date", "actual_max_date",
    "expected_min_date", "expected_max_date", "source_row_count", "source_key_count",
    "pipeline_status", "verification_status", "quality_status", "check_error",
    "last_checked_at", "last_full_checked_at",
)


def _tiered_section(
    rows: list[dict[str, Any]],
    *,
    cap: int,
    full: tuple[str, ...],
    summary: tuple[str, ...],
    keep_null: tuple[str, ...],
    group_key: str,
    budget: int,
    narrow_hint: str,
) -> dict[str, Any]:
    total = int(rows[0]["total_matching"]) if rows else 0
    rows = rows[:cap]
    detail = "FULL"
    entries = [_entry(row, full, keep_null) for row in rows]
    if _size(entries) > budget:
        detail = "SUMMARY"
        entries = [_entry(row, summary, keep_null) for row in rows]
    kept, cut = _fit(entries, budget)
    section: dict[str, Any] = {
        "detail": detail,
        "by_table": _group(kept, group_key),
        "returned": len(kept),
        "total_matching": total,
    }
    if detail == "SUMMARY" or cut or len(kept) < total:
        section["truncated"] = len(kept) < total
        section["hint"] = narrow_hint
    if not kept:
        section["note"] = "No matching catalog records."
    return section


class CatalogTools:
    def __init__(self, reader: CatalogReader) -> None:
        self.reader = reader

    def discover(self, _: BaseModel) -> dict[str, Any]:
        with self.reader.read_only() as run:
            rows = run(DISCOVER_SQL, (MAX_DISCOVERED_TABLES + 1,))
            research = run(RESEARCH_COUNTS_SQL, ())
            formulas = run(FORMULA_COUNT_SQL, ())
        tables = [
            {
                **_entry(row, (
                    "table_name", "description", "category", "grain", "primary_key_columns",
                    "time_column", "entity_column", "documentation_status", "freshness_sla",
                    "coverage_enabled",
                ), keep_null=("description",)),
                **({"subject": _entry(row, ("data_domain", "entity_type", "asset_type", "supported_frequencies",
                                            "time_semantics", "subject_metadata_status"), keep_null=("asset_type",))}
                   if row.get("data_domain") else {}),
                "available_metadata": {
                    "columns": int(row["column_count"]),
                    "calculations": int(row["calculation_count"]),
                    "relationships": int(row["relationship_count"]),
                },
            }
            for row in rows[:MAX_DISCOVERED_TABLES]
        ]
        result: dict[str, Any] = {
            "tables": tables,
            "table_count": len(tables),
            "truncated": len(rows) > MAX_DISCOVERED_TABLES,
            "research_catalog": {
                "catalog_name": "AI_research_catalog",
                "method_count": sum(int(row["method_count"]) for row in research),
                "implementation_status_counts": {
                    row["implementation_status"]: int(row["method_count"]) for row in research
                },
                "scope": "GLOBAL_METHOD_REFERENCE",
            },
            "formula_catalog": {
                "catalog_name": "AI_formula_reference",
                "formula_count": int(formulas[0]["formula_count"]) if formulas else 0,
                "scope": "GLOBAL_FORMULA_REFERENCE",
                "note": "Documented formula definitions, not verified or executable implementations.",
            },
            "notice": METADATA_NOTICE + " Use get_catalog_details for columns, relationships, "
                      "calculations, coverage, research methods, and formulas. " + VISIBILITY_NOTE,
        }
        if not tables:
            result["note"] = "The AI catalog currently exposes no tables."
        return result

    def details(self, arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, CatalogDetailsArguments)
        with self.reader.read_only() as run:
            resolved = run(RESOLVE_TABLES_SQL, (arguments.table_names,)) if arguments.table_names else []
            found = {row["table_name"]: row for row in resolved}
            tables = [name for name in arguments.table_names if name in found]
            unknown = [name for name in arguments.table_names if name not in found]
            if arguments.table_names and not tables:
                raise ToolError(
                    f"None of the requested tables are available in the AI catalog: {unknown}. "
                    "Call discover_catalog for valid table_name values."
                )

            base: dict[str, Any] = {
                "tables": tables,
                "notice": " ".join((METADATA_NOTICE, ABSENT_FIELDS_NOTE, VISIBILITY_NOTE)),
            }
            if unknown:
                base["unknown_tables"] = unknown
            remaining = RESULT_BUDGET_BYTES - _size(base) - 200
            built: dict[str, Any] = {}
            ordered = [section for section in ALLOCATION_ORDER if section in arguments.sections]
            for index, section in enumerate(ordered):
                share = max(remaining // (len(ordered) - index), 0)
                built[section] = self._section(run, section, tables, found, arguments, share)
                remaining -= _size(built[section])

        return {**base, "sections": {section: built[section] for section in arguments.sections}}

    def _section(
        self,
        run: QueryRunner,
        section: str,
        tables: list[str],
        found: dict[str, dict[str, Any]],
        arguments: CatalogDetailsArguments,
        budget: int,
    ) -> dict[str, Any]:
        columns = arguments.column_names
        if section == "COLUMNS":
            rows = run(COLUMNS_SQL, (tables, columns, columns, ROW_CAPS["COLUMNS"] + 1))
            result = _tiered_section(
                rows, cap=ROW_CAPS["COLUMNS"], full=COLUMN_FULL, summary=COLUMN_SUMMARY,
                keep_null=("description",), group_key="table_name", budget=budget,
                narrow_hint="Pass column_names to receive full metadata for specific columns.",
            )
            if columns:
                present = {row["column_name"] for row in run(FOUND_COLUMNS_SQL, (tables, columns))}
                missing = [name for name in columns if name not in present]
                if missing:
                    result["unknown_columns"] = missing
            return result

        if section == "CALCULATIONS":
            rows = run(CALCULATIONS_SQL, (tables, columns, columns, ROW_CAPS["CALCULATIONS"] + 1))
            return _tiered_section(
                rows, cap=ROW_CAPS["CALCULATIONS"], full=CALCULATION_FULL,
                summary=CALCULATION_SUMMARY, keep_null=("definition",),
                group_key="target_table", budget=budget,
                narrow_hint="Pass column_names to receive full calculation contracts for specific columns.",
            )

        if section == "RESEARCH":
            rows = run(RESEARCH_SQL, (arguments.method_ids, arguments.method_ids, ROW_CAPS["RESEARCH"] + 1))
            total = int(rows[0]["total_matching"]) if rows else 0
            entries = [_entry(row, RESEARCH_FULL) for row in rows[: ROW_CAPS["RESEARCH"]]]
            detail = "FULL"
            if _size(entries) > budget:
                detail = "SUMMARY"
                entries = [_entry(row, RESEARCH_SUMMARY) for row in rows[: ROW_CAPS["RESEARCH"]]]
            kept, _ = _fit(entries, budget)
            result = {"detail": detail, "entries": kept, "returned": len(kept), "total_matching": total,
                      "note": "REFERENCE_ONLY does not indicate an installed or validated sandbox method."}
            if detail == "SUMMARY" or len(kept) < total:
                result["truncated"] = len(kept) < total
                result["hint"] = "Pass method_ids to retrieve full definitions for specific research methods."
            return result

        if section == "FORMULAS":
            rows = run(FORMULAS_SQL, (arguments.formula_ids, arguments.formula_ids, ROW_CAPS["FORMULAS"] + 1))
            total = int(rows[0]["total_matching"]) if rows else 0
            entries = [_entry(row, FORMULA_FULL) for row in rows[: ROW_CAPS["FORMULAS"]]]
            detail = "FULL"
            if _size(entries) > budget:
                detail = "SUMMARY"
                entries = [_entry(row, FORMULA_SUMMARY) for row in rows[: ROW_CAPS["FORMULAS"]]]
            kept, _ = _fit(entries, budget)
            result = {"detail": detail, "entries": kept, "returned": len(kept), "total_matching": total,
                      "note": "Documented formula definitions, not verified or executable implementations."}
            if detail == "SUMMARY" or len(kept) < total:
                result["truncated"] = len(kept) < total
                result["hint"] = "Pass formula_ids to retrieve full definitions for specific formulas."
            return result

        if section == "RELATIONSHIPS":
            rows = run(RELATIONSHIPS_SQL, (tables, tables, ROW_CAPS["RELATIONSHIPS"] + 1))
            total = int(rows[0]["total_matching"]) if rows else 0
            entries = [_entry(row, RELATIONSHIP_FIELDS) for row in rows[: ROW_CAPS["RELATIONSHIPS"]]]
            kept, _ = _fit(entries, budget)
            result: dict[str, Any] = {
                "entries": kept,
                "returned": len(kept),
                "total_matching": total,
                "join_rule": "left_columns[i] joins right_columns[i]; safe_output_grain is the documented result grain.",
            }
            if len(kept) < total:
                result["truncated"] = True
            if not kept:
                result["note"] = "No documented relationships for the requested tables."
            return result

        return self._coverage(run, tables, found, arguments.entity_ids, budget)

    @staticmethod
    def _coverage(
        run: QueryRunner,
        tables: list[str],
        found: dict[str, dict[str, Any]],
        entity_ids: list[str] | None,
        budget: int,
    ) -> dict[str, Any]:
        enabled = [name for name in tables if found[name]["coverage_enabled"]]
        result: dict[str, Any] = {}
        disabled = [name for name in tables if name not in enabled]
        if disabled:
            result["coverage_disabled_tables"] = disabled
        if not enabled:
            result["note"] = "Coverage tracking is disabled for the requested tables."
            return result

        datasets = run(COVERAGE_DATASET_SQL, (enabled,))
        by_dataset = {
            row["dataset_name"]: {**_entry(row, COVERAGE_FIELDS), "availability_interpretation": _availability(row)}
            for row in datasets
        }
        result["datasets"] = by_dataset
        without = [name for name in enabled if name not in by_dataset]
        if without:
            result["no_coverage_record"] = without

        statuses = run(COVERAGE_STATUS_SQL, (enabled, ROW_CAPS["STATUS"] + 1))
        status_entries = [
            _entry(row, ("dataset_name", "pipeline_status", "verification_status", "quality_status", "entity_count"))
            for row in statuses[: ROW_CAPS["STATUS"]]
        ]
        result["entity_status_counts"] = _group(status_entries, "dataset_name")
        if len(statuses) > ROW_CAPS["STATUS"]:
            result["entity_status_counts_truncated"] = True

        if entity_ids:
            rows = run(COVERAGE_ENTITIES_SQL, (enabled, entity_ids, ROW_CAPS["ENTITIES"] + 1))
            entries = [
                _entry(row, ("dataset_name", "entity_id", *COVERAGE_FIELDS[:-1]))
                for row in rows[: ROW_CAPS["ENTITIES"]]
            ]
            spare = budget - _size(result) - 100
            kept, cut = _fit(entries, max(spare, 0))
            result["entities"] = _group(kept, "dataset_name")
            seen = {row["entity_id"] for row in rows}
            missing = [entity for entity in entity_ids if entity not in seen]
            if missing:
                result["unknown_entities"] = missing
            if cut or len(rows) > ROW_CAPS["ENTITIES"]:
                result["entities_truncated"] = True
        return result


def catalog_specs(reader: CatalogReader, *, timeout_seconds: float) -> list[ToolSpec]:
    tools = CatalogTools(reader)
    return [
        ToolSpec(
            name="discover_catalog",
            description=(
                "List the data tables available in Saniti's AI catalog with their descriptions, "
                "category, grain, keys, documentation status, and how much column, calculation, "
                "and relationship metadata each has, plus the global research-method and "
                "formula-reference catalog counts. Returns catalog metadata only, never data rows."
            ),
            arguments_model=NoArguments,
            handler=tools.discover,
            timeout_seconds=timeout_seconds,
        ),
        ToolSpec(
            name="get_catalog_details",
            description=(
                f"Retrieve catalog metadata for up to {MAX_TABLES_PER_CALL} tables returned by "
                "discover_catalog. COLUMNS: column meanings, types, units, and allowed "
                "aggregations. RELATIONSHIPS: documented join keys, temporal rules, and output "
                "grain. CALCULATIONS: documented calculation definitions, required inputs, "
                "alignment and missing-data rules. COVERAGE: recorded date coverage and "
                "verification status. RESEARCH: global reference methods, independent of market tables; "
                "use table_names=[] for RESEARCH only and method_ids to narrow. FORMULAS: global "
                "documented calculation formulas, independent of market tables; use table_names=[] for "
                "FORMULAS only and formula_ids to narrow; these are documented definitions, not verified "
                "or executable implementations. Large sections are summarized or truncated and say so. "
                "Returns documentation only, never observed values."
            ),
            arguments_model=CatalogDetailsArguments,
            handler=tools.details,
            timeout_seconds=timeout_seconds,
        ),
    ]
