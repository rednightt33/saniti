from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..compaction import dumps
from .registry import ToolError, ToolSpec
from .rows import CursorCodec
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
SUBJECT_VALUE = re.compile(r"^[A-Z][A-Z0-9_]{1,39}$")

# Discovery v2 (AI_ENABLE_CATALOG_DISCOVERY_V2): filters, paging, formula search, complete join/resample contracts.
DISCOVER_PAGE_DEFAULT = 20
FORMULA_SEARCH_LIMIT = 20
DISCOVER_FORMULA_MATCHES = 5          # formulas matching a discover_catalog query, listed with the tables
MAX_QUERY_CHARS = 100
SHORT_TEXT_CHARS = 160
DISCOVER_KEY_LENGTH = 2              # keyset (matched keyword count, table_name)
MAX_QUERY_WORDS = 8
MIN_QUERY_WORD = 3
# words that would match almost every table or formula; they are dropped from a keyword query
QUERY_STOPWORDS = frozenset({
    "the", "and", "for", "per", "with", "from", "are", "was", "all", "any", "each", "every", "data", "table", "tables",
    "tabel", "kolom", "column", "columns", "value", "values", "nilai", "dan", "yang", "dari", "untuk", "atau", "pada",
    "dengan", "setiap", "semua"})
NULL_WORDS = frozenset({"null", "none", "nil", "n/a"})

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

# Discovery v2: the same columns over the visible tables that pass the subject filters and match at least one query
# keyword (none given: all), one keyset page ordered by matched keywords then table_name, and the number of matching
# tables before paging. A keyword matches the table name, description, category, grain, or a visible column's name or
# description. Keywords are lower-case letters and digits only, so they carry no LIKE wildcard. Subject filters read
# to_jsonb so the query stays valid before migration 20260925_001 (then no table matches a subject filter).
DISCOVER_V2_SQL = f'''
WITH visible AS ({VISIBLE_TABLES}),
scored AS (
    SELECT t.*, m.matched_words, cardinality(m.matched_words) AS query_hits
    FROM public."AI_table_catalog" t
    CROSS JOIN LATERAL (
        SELECT lower(concat_ws(' ', t.table_name, t.description, t.category, t.grain,
               (SELECT string_agg(concat_ws(' ', c.column_name, c.description), ' ')
                FROM public."AI_column_catalog" c
                WHERE c.table_name = t.table_name AND c.ai_allowed AND NOT c.is_sensitive))) AS haystack
    ) h
    CROSS JOIN LATERAL (
        SELECT coalesce(array_agg(w.word ORDER BY w.ord), '{{}}'::text[]) AS matched_words
        FROM unnest(%s::text[]) WITH ORDINALITY AS w(word, ord)
        WHERE h.haystack LIKE '%%' || w.word || '%%'
    ) m
    WHERE t.table_name IN (SELECT table_name FROM visible)
      AND (%s::text IS NULL OR to_jsonb(t) ->> 'data_domain' = %s)
      AND (%s::text IS NULL OR to_jsonb(t) ->> 'entity_type' = %s)
      AND (%s::text IS NULL OR to_jsonb(t) ->> 'asset_type' = %s)
),
filtered AS (SELECT * FROM scored WHERE cardinality(%s::text[]) = 0 OR query_hits > 0)
SELECT t.table_name, t.description, t.category, t.grain, t.primary_key_columns,
       t.time_column, t.entity_column, t.documentation_status, t.coverage_enabled,
       t.freshness_sla::text AS freshness_sla,
       to_jsonb(t) ->> 'data_domain' AS data_domain, to_jsonb(t) ->> 'entity_type' AS entity_type,
       to_jsonb(t) ->> 'asset_type' AS asset_type, to_jsonb(t) -> 'supported_frequencies' AS supported_frequencies,
       to_jsonb(t) ->> 'time_semantics' AS time_semantics,
       to_jsonb(t) ->> 'subject_metadata_status' AS subject_metadata_status,
       t.matched_words, t.query_hits,
       (SELECT count(*) FROM public."AI_column_catalog" c
         WHERE c.table_name = t.table_name AND c.ai_allowed AND NOT c.is_sensitive) AS column_count,
       (SELECT count(*) FROM public."AI_calculation_catalog" k
         WHERE k.target_table = t.table_name AND k.status = 'ACTIVE') AS calculation_count,
       (SELECT count(*) FROM public."AI_catalog_relationships" r
         WHERE r.is_allowed AND t.table_name IN (r.left_table, r.right_table)
           AND r.left_table IN (SELECT table_name FROM visible)
           AND r.right_table IN (SELECT table_name FROM visible)) AS relationship_count,
       (SELECT count(*) FROM filtered) AS total_matching
FROM filtered t
WHERE %s::int IS NULL OR t.query_hits < %s OR (t.query_hits = %s AND t.table_name > %s)
ORDER BY t.query_hits DESC, t.table_name
LIMIT %s
'''

# The subject values that exist, returned only when no table matched, so the model can correct a filter.
SUBJECT_VALUES_SQL = f'''
SELECT to_jsonb(t) ->> 'data_domain' AS data_domain, to_jsonb(t) ->> 'entity_type' AS entity_type,
       to_jsonb(t) ->> 'asset_type' AS asset_type, count(*) AS table_count
FROM public."AI_table_catalog" t
WHERE t.table_name IN ({VISIBLE_TABLES})
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3
LIMIT 30
'''

# A light fingerprint of the visible table rows only (no scan of market data or coverage rows): a cursor issued for
# one fingerprint is refused after the table catalog changed.
CATALOG_FINGERPRINT_SQL = f'''
SELECT md5(coalesce(string_agg(to_jsonb(t)::text, '|' ORDER BY t.table_name), '')) AS fingerprint
FROM public."AI_table_catalog" t
WHERE t.table_name IN ({VISIBLE_TABLES})
'''

# get_catalog_details v2: the table-level contract a DataNeedSpec copies (grain, keys, time/entity columns, subject).
TABLE_META_SQL = '''
SELECT t.table_name, t.grain, t.primary_key_columns, t.time_column, t.entity_column,
       to_jsonb(t) ->> 'data_domain' AS data_domain, to_jsonb(t) ->> 'entity_type' AS entity_type,
       to_jsonb(t) ->> 'asset_type' AS asset_type, to_jsonb(t) -> 'supported_frequencies' AS supported_frequencies,
       to_jsonb(t) ->> 'time_semantics' AS time_semantics,
       to_jsonb(t) ->> 'subject_metadata_status' AS subject_metadata_status
FROM public."AI_table_catalog" t
WHERE t.table_name = ANY(%s)
ORDER BY t.table_name
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

# v2 adds the resample rule (migration 20260925_003; to_jsonb keeps the query valid before it, and resample_recorded
# tells the two apart) and each table's own column count, which LIMIT does not cut.
COLUMNS_V2_SQL = '''
SELECT c.table_name, c.column_name, c.description, c.data_type, c.semantic_type, c.unit, c.nullable,
       c.is_primary_key, c.source_column_or_expression, c.allowed_aggregations, c.filter_allowed,
       c.group_by_allowed, c.example_value, c.documentation_status,
       to_jsonb(c) ->> 'resample_aggregation' AS resample_aggregation,
       (to_jsonb(c) ? 'resample_aggregation') AS resample_recorded,
       to_jsonb(c) ->> 'value_time_basis' AS value_time_basis,
       count(*) OVER (PARTITION BY c.table_name) AS table_total,
       count(*) OVER () AS total_matching
FROM public."AI_column_catalog" c
WHERE c.table_name = ANY(%s) AND c.ai_allowed AND NOT c.is_sensitive
  AND (%s::text[] IS NULL OR c.column_name = ANY(%s::text[]))
ORDER BY c.table_name, c.ordinal_position
LIMIT %s
'''

# IP1 Stage D (AI_ENABLE_POINT_IN_TIME): the availability contract of Table_Catalog, readable through a column-level
# grant (migration 20260927_006); information_schema lists only the columns this role may read, so the check below
# keeps get_catalog_details working before that grant
AVAILABILITY_READABLE_SQL = '''
SELECT count(*) AS readable FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'Table_Catalog'
  AND column_name IN ('table_schema', 'table_name', 'point_in_time_status', 'availability_rule')
'''
AVAILABILITY_SQL = '''
SELECT table_name, point_in_time_status, availability_rule FROM public."Table_Catalog"
WHERE table_schema = 'public' AND table_name = ANY(%s)
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

# v2 adds the join-semantics contract of migration 20260925_003 (to_jsonb: valid before it; join_semantics_recorded
# tells a NULL apart from a catalog without those columns).
RELATIONSHIPS_V2_SQL = f'''
WITH visible AS ({VISIBLE_TABLES})
SELECT r.relationship_id, r.left_table, r.left_columns, r.right_table, r.right_columns,
       r.relationship_type, r.temporal_rule, r.safe_output_grain, r.requires_preaggregation,
       r.description, r.version,
       to_jsonb(r) -> 'supported_join_semantics' AS supported_join_semantics,
       to_jsonb(r) ->> 'left_time_column' AS left_time_column,
       to_jsonb(r) ->> 'right_time_column' AS right_time_column,
       to_jsonb(r) ->> 'effective_from_column' AS effective_from_column,
       to_jsonb(r) ->> 'effective_to_column' AS effective_to_column,
       (to_jsonb(r) ? 'supported_join_semantics') AS join_semantics_recorded,
       count(*) OVER () AS total_matching
FROM public."AI_catalog_relationships" r
WHERE r.is_allowed AND (r.left_table = ANY(%s) OR r.right_table = ANY(%s))
  AND r.left_table IN (SELECT table_name FROM visible)
  AND r.right_table IN (SELECT table_name FROM visible)
ORDER BY r.relationship_id
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

# Formula search (v2): a formula matches when a query keyword appears in its id, name or description. The whole
# query equal to an id or name comes first, then the score (a keyword equal to the id or name 3, inside it 2, only in
# the description 1), ties by calculation_id. Keywords are lower-case letters and digits only (no LIKE wildcard).
FORMULA_SEARCH_SQL = '''
SELECT f.calculation_id, f.calculation_name, f.description, f.required_inputs, m.matched_words, m.name_hit,
       (lower(f.calculation_id) = %s OR lower(f.calculation_name) = %s) AS exact,
       count(*) OVER () AS total_matching
FROM public."AI_formula_reference" f
CROSS JOIN LATERAL (
    SELECT coalesce(array_agg(w.word ORDER BY w.ord), '{}'::text[]) AS matched_words,
           coalesce(sum(CASE WHEN lower(f.calculation_id) = w.word OR lower(f.calculation_name) = w.word THEN 3
                             WHEN lower(concat_ws(' ', f.calculation_id, f.calculation_name))
                                  LIKE '%%' || w.word || '%%' THEN 2
                             ELSE 1 END), 0) AS score,
           coalesce(bool_or(lower(concat_ws(' ', f.calculation_id, f.calculation_name))
                            LIKE '%%' || w.word || '%%'), false) AS name_hit
    FROM unnest(%s::text[]) WITH ORDINALITY AS w(word, ord)
    WHERE lower(concat_ws(' ', f.calculation_id, f.calculation_name, f.description)) LIKE '%%' || w.word || '%%'
) m
WHERE lower(f.calculation_id) = %s OR lower(f.calculation_name) = %s OR cardinality(m.matched_words) > 0
ORDER BY (lower(f.calculation_id) = %s OR lower(f.calculation_name) = %s) DESC, m.score DESC, f.calculation_id
LIMIT %s
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


def _text_query(value: str | None, label: str) -> str | None:
    """Whitespace-normalized query text; empty or the word null (a model writing null as a string) means no query."""
    if value is None:
        return None
    value = " ".join(value.split())
    if not value or value.lower() in NULL_WORDS:
        return None
    if len(value) > MAX_QUERY_CHARS:
        raise ValueError(f"{label} is at most {MAX_QUERY_CHARS} characters")
    if not query_words(value):
        raise ValueError(f"{label} needs at least one keyword of {MIN_QUERY_WORD}+ letters or digits that is not a "
                         "generic word such as data or table")
    return value


def query_words(text: str | None) -> list[str]:
    """The keywords of a query: lower-case runs of letters and digits, at least MIN_QUERY_WORD long, without generic
    words, a plural s removed (a keyword matches as a substring, so "prices" becomes "price"), at most
    MAX_QUERY_WORDS, in order."""
    words: list[str] = []
    for raw in re.split(r"[^0-9a-z]+", (text or "").lower()):
        if len(raw) < MIN_QUERY_WORD or raw in QUERY_STOPWORDS:
            continue
        word = raw[:-1] if len(raw) > MIN_QUERY_WORD and raw.endswith("s") and not raw.endswith("ss") else raw
        if word not in words:
            words.append(word)
    return words[:MAX_QUERY_WORDS]


class CatalogDetailsArgumentsV2(CatalogDetailsArguments):
    """get_catalog_details with discovery v2: formula search, and FORMULAS named in the sections description."""

    sections: list[Section] = Field(
        description="Metadata sections, every one you need in one call: COLUMNS (types, units, permissions, resample "
                    "rules), COVERAGE (recorded date coverage), RELATIONSHIPS (join keys and join semantics), "
                    "CALCULATIONS, RESEARCH, FORMULAS."
    )
    formula_query: str | None = Field(
        description=f"FORMULAS only: keywords to search formula ids, names and descriptions, for example 'rsi relative "
                    f"strength'. A formula matches when any keyword appears; an exact id or name comes first, then "
                    f"formulas matching more keywords in their name. Returns up to {FORMULA_SEARCH_LIMIT} matches with "
                    "their ids; then pass formula_ids for full definitions. Null when not searching; never together "
                    "with formula_ids."
    )

    @model_validator(mode="before")
    @classmethod
    def _legacy_query(cls, value: Any) -> Any:
        return {"formula_query": None, **value} if isinstance(value, dict) else value

    @field_validator("formula_query")
    @classmethod
    def _query(cls, value: str | None) -> str | None:
        return _text_query(value, "formula_query")

    @model_validator(mode="after")
    def _search_rules(self) -> "CatalogDetailsArgumentsV2":
        if self.formula_query is not None and self.formula_ids is not None:
            raise ValueError("formula_query and formula_ids are exclusive: search with formula_query, then read the "
                             "chosen definitions with formula_ids")
        if self.formula_query is not None and "FORMULAS" not in self.sections:
            raise ValueError("formula_query applies to the FORMULAS section; add FORMULAS to sections")
        return self


class DiscoverArguments(BaseModel):
    """discover_catalog with discovery v2. Every field is optional: discover_catalog({}) lists the first page."""

    model_config = ConfigDict(extra="forbid")

    query: str | None = Field(
        description="Optional keywords, for example 'daily price volume'. A table matches when any keyword appears in "
                    "its name, description or column names and descriptions; tables matching more keywords come "
                    "first. Null for every table.")
    data_domain: str | None = Field(description="Optional exact subject data_domain, for example MARKET; null for any.")
    entity_type: str | None = Field(description="Optional exact subject entity_type, for example STOCK; null for any.")
    asset_type: str | None = Field(description="Optional exact subject asset_type; null for any.")
    page_size: int | None = Field(
        description=f"Tables per page, 1-{MAX_DISCOVERED_TABLES}; null for {DISCOVER_PAGE_DEFAULT}. A page may hold "
                    "fewer when the byte budget is reached; has_more and next_cursor tell.")
    cursor: str | None = Field(
        description="Null for the first page, or the exact next_cursor of the previous page with the same filters.")

    @model_validator(mode="before")
    @classmethod
    def _defaults(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {name: None for name in ("query", "data_domain", "entity_type", "asset_type", "page_size",
                                            "cursor")} | value
        return value

    @field_validator("query")
    @classmethod
    def _query(cls, value: str | None) -> str | None:
        return _text_query(value, "query")

    @field_validator("data_domain", "entity_type", "asset_type")
    @classmethod
    def _subject(cls, value: str | None) -> str | None:
        if value is None or value.strip().lower() in NULL_WORDS or not value.strip():
            return None
        value = value.strip().upper()
        if not SUBJECT_VALUE.fullmatch(value):
            raise ValueError("a subject filter is an upper-case catalog identifier such as MARKET or STOCK")
        return value

    @field_validator("page_size")
    @classmethod
    def _page(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= MAX_DISCOVERED_TABLES:
            raise ValueError(f"page_size must be between 1 and {MAX_DISCOVERED_TABLES}")
        return value

    @field_validator("cursor")
    @classmethod
    def _cursor(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or len(value) > 2048):
            raise ValueError("cursor must be the exact next_cursor value")
        return value

    def filters(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in ("query", "data_domain", "entity_type", "asset_type")
                if getattr(self, name) is not None}


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
# v2 tiers: prose is shortened, then dropped, before any identifier, permission, unit or resample rule is.
COLUMN_FULL_V2 = (*COLUMN_FULL, "resample_aggregation")
COLUMN_COMPACT_V2 = (
    "table_name", "column_name", "description", "data_type", "semantic_type", "unit", "nullable", "is_primary_key",
    "allowed_aggregations", "filter_allowed", "group_by_allowed", "resample_aggregation",
)
COLUMN_MINIMAL_V2 = (
    "table_name", "column_name", "data_type", "unit", "is_primary_key", "allowed_aggregations", "filter_allowed",
    "group_by_allowed", "resample_aggregation",
)
COLUMN_NULLS_V2 = ("description", "unit", "resample_aggregation")
JOIN_FIELDS_V2 = ("left_time_column", "right_time_column", "effective_from_column", "effective_to_column")
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


def _short(value: Any) -> Any:
    if not isinstance(value, str) or len(value) <= SHORT_TEXT_CHARS:
        return value
    return value[:SHORT_TEXT_CHARS - 1].rstrip() + "…"


def _column_entry_v2(row: dict[str, Any], fields: tuple[str, ...], shorten: bool) -> dict[str, Any]:
    entry = _entry(row, fields, keep_null=COLUMN_NULLS_V2)
    if shorten and "description" in entry:
        entry["description"] = _short(entry["description"])
    return entry


def _columns_v2(rows: list[dict[str, Any]], tables: list[str], column_filter: list[str] | None,
                budget: int, current_state: bool = False) -> dict[str, Any]:
    """COLUMNS with discovery v2: the FULL, COMPACT or MINIMAL tier that fits (all keep names, types, units,
    permissions and resample rules), per-table completeness, and the exact call that fetches what was cut."""
    total = int(rows[0]["total_matching"]) if rows else 0
    table_totals = {row["table_name"]: int(row["table_total"]) for row in rows}
    rows = rows[:ROW_CAPS["COLUMNS"]]
    detail, entries = "FULL", []
    for detail, fields in (("FULL", COLUMN_FULL_V2), ("COMPACT", COLUMN_COMPACT_V2), ("MINIMAL", COLUMN_MINIMAL_V2)):
        # IP1 Stage D: a column holding today's reference value on every historical row says so
        entries = [_column_entry_v2(row, fields, shorten=detail != "FULL")
                   | ({"value_time_basis": "CURRENT_STATE"} if current_state
                      and row.get("value_time_basis") == "CURRENT_STATE" else {}) for row in rows]
        if _size(entries) <= budget:
            break
    kept, _ = _fit(entries, budget)
    by_table = _group(kept, "table_name")
    fetched: dict[str, list[str]] = {}
    for row in rows:
        fetched.setdefault(row["table_name"], []).append(row["column_name"])
    completeness: dict[str, Any] = {}
    recovery = []
    for table in tables:
        returned = [entry["column_name"] for entry in by_table.get(table, [])]
        known_total = table_totals.get(table)
        complete = known_total is not None and len(returned) == known_total
        completeness[table] = {"columns_returned": len(returned), "columns_total": known_total, "complete": complete}
        if not complete and (known_total is None or known_total > 0):
            missing = [name for name in fetched.get(table, []) if name not in returned][:MAX_COLUMN_FILTER]
            recovery.append({"table_names": [table], "sections": ["COLUMNS"],
                             "column_names": missing or None, "entity_ids": None})
    section: dict[str, Any] = {
        "detail": detail,
        "by_table": by_table,
        "returned": len(kept),
        "total_matching": total,
        "completeness": completeness,
        "null_meaning": "A null unit, description or resample_aggregation is not recorded in the catalog. A null "
                        "resample_aggregation means no established rule: never assume LAST or any other default.",
    }
    if detail != "FULL":
        section["detail_note"] = ("Descriptions were shortened (COMPACT) or left out (MINIMAL) to fit; names, types, "
                                  "units, permissions and resample rules are complete for every returned column.")
    if recovery:
        section["incomplete"] = True
        section["recovery_calls"] = recovery[:MAX_TABLES_PER_CALL]
        section["hint"] = "Call get_catalog_details with each recovery_calls entry to read the columns that were cut."
    if rows and not any(row.get("resample_recorded") for row in rows):
        section["resample_rules_recorded"] = False
    if not kept:
        section["note"] = "No matching catalog records."
    return section


def _relationships_v2(rows: list[dict[str, Any]], budget: int) -> dict[str, Any]:
    total = int(rows[0]["total_matching"]) if rows else 0
    recorded = any(row.get("join_semantics_recorded") for row in rows)
    entries = []
    for row in rows[: ROW_CAPS["RELATIONSHIPS"]]:
        entry = _entry(row, RELATIONSHIP_FIELDS)
        if recorded:
            entry["supported_join_semantics"] = list(row.get("supported_join_semantics") or [])
            entry.update({name: row.get(name) for name in JOIN_FIELDS_V2})
        entries.append(entry)
    kept, _ = _fit(entries, budget)
    result: dict[str, Any] = {
        "entries": kept,
        "returned": len(kept),
        "total_matching": total,
        "join_rule": "left_columns[i] joins right_columns[i]; safe_output_grain is the documented result grain.",
    }
    if recorded:
        result["join_semantics_note"] = (
            "A data need may use only a relationship's supported_join_semantics (empty: not joinable). EXACT_DATE and "
            "AS_OF use left_time_column/right_time_column; EFFECTIVE_DATED uses effective_from_column/"
            "effective_to_column. A null field is not recorded in the catalog, not a default.")
    elif rows:
        result["join_semantics_recorded"] = False
    if len(kept) < total:
        result["truncated"] = True
    if not kept:
        result["note"] = "No documented relationships for the requested tables."
    return result


def _table_entry(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **_entry(row, ("table_name", "description", "category", "grain", "primary_key_columns", "time_column",
                       "entity_column", "documentation_status", "freshness_sla", "coverage_enabled"),
                 keep_null=("description",)),
        **({"subject": _entry(row, ("data_domain", "entity_type", "asset_type", "supported_frequencies",
                                    "time_semantics", "subject_metadata_status"), keep_null=("asset_type",))}
           if row.get("data_domain") else {}),
        "available_metadata": {
            "columns": int(row["column_count"]),
            "calculations": int(row["calculation_count"]),
            "relationships": int(row["relationship_count"]),
        },
    }


class CatalogTools:
    def __init__(self, reader: CatalogReader, *, discovery_v2: bool = False,
                 codec: CursorCodec | None = None, point_in_time: bool = False) -> None:
        self.reader = reader
        self.discovery_v2 = discovery_v2
        self.point_in_time = point_in_time and discovery_v2
        self.codec = codec
        if discovery_v2 and codec is None:
            raise ValueError("discovery v2 needs a cursor codec")

    def discover(self, arguments: BaseModel) -> dict[str, Any]:
        if self.discovery_v2 and isinstance(arguments, DiscoverArguments):
            return self._discover_v2(arguments)
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

    def _discover_v2(self, arguments: DiscoverArguments) -> dict[str, Any]:
        assert self.codec is not None
        filters = arguments.filters()
        binding = dumps(filters)
        page_size = arguments.page_size or DISCOVER_PAGE_DEFAULT
        words = query_words(arguments.query)
        with self.reader.read_only() as run:
            fingerprint = str(run(CATALOG_FINGERPRINT_SQL, ())[0]["fingerprint"])[:16]
            after_hits, after_name = None, None
            if arguments.cursor is not None:
                key = self.codec.decode_bound(arguments.cursor, "discover_catalog", binding, fingerprint,
                                              DISCOVER_KEY_LENGTH)
                if not isinstance(key[0], int) or not isinstance(key[1], str):
                    raise ToolError("The cursor is invalid for this tool and these filters. Use the exact next_cursor "
                                    "returned with the same filters, or pass cursor null to start from the first "
                                    "page.", code="CURSOR_INVALID")
                after_hits, after_name = key
            rows = run(DISCOVER_V2_SQL, (
                words,
                arguments.data_domain, arguments.data_domain, arguments.entity_type, arguments.entity_type,
                arguments.asset_type, arguments.asset_type, words,
                after_hits, after_hits, after_hits, after_name, page_size + 1))
            research = run(RESEARCH_COUNTS_SQL, ())
            formulas = run(FORMULA_COUNT_SQL, ())
            subjects = run(SUBJECT_VALUES_SQL, ()) if not rows and filters else []
            query = (arguments.query or "").lower()
            formula_rows = run(FORMULA_SEARCH_SQL, (query, query, words, query, query, query, query,
                                                    DISCOVER_FORMULA_MATCHES)) if words else []
        total = int(rows[0]["total_matching"]) if rows else 0
        base: dict[str, Any] = {
            "research_catalog": {
                "catalog_name": "AI_research_catalog",
                "method_count": sum(int(row["method_count"]) for row in research),
                "implementation_status_counts": {row["implementation_status"]: int(row["method_count"])
                                                 for row in research},
                "scope": "GLOBAL_METHOD_REFERENCE",
            },
            "formula_catalog": {
                "catalog_name": "AI_formula_reference",
                "formula_count": int(formulas[0]["formula_count"]) if formulas else 0,
                "scope": "GLOBAL_FORMULA_REFERENCE",
                "note": "Documented formula definitions, not verified or executable implementations. Search them with "
                        "get_catalog_details sections [FORMULAS] and formula_query.",
            },
            "applied_filters": filters,
            "catalog_fingerprint": fingerprint,
            "notice": METADATA_NOTICE + " Use get_catalog_details for columns, relationships, calculations, "
                      "coverage, research methods, and formulas. " + VISIBILITY_NOTE,
        }
        if words:
            base["query_words"] = words
            base["formula_catalog"]["matches"] = [
                {"calculation_id": row["calculation_id"], "calculation_name": row.get("calculation_name"),
                 "match": "EXACT" if row["exact"] else "NAME" if row["name_hit"] else "DESCRIPTION",
                 "matched_words": list(row["matched_words"])} for row in formula_rows]
            base["formula_catalog"]["note"] = (
                "Documented formula definitions, not verified or executable implementations. matches lists the "
                "formulas matching the query keywords, best first; read full definitions with get_catalog_details "
                "sections [FORMULAS] and formula_ids, in the same call as the tables.")
        entries = [{**_table_entry(row), **({"matched_words": list(row["matched_words"])} if words else {})}
                   for row in rows[:page_size]]
        kept, cut = _fit(entries, RESULT_BUDGET_BYTES - _size(base) - 1200)
        has_more = cut or len(rows) > page_size
        hits = {row["table_name"]: int(row["query_hits"]) for row in rows}
        last = [hits[kept[-1]["table_name"]], kept[-1]["table_name"]] if kept else None
        if has_more and not kept:
            raise ToolError("A single catalog table entry exceeds the result budget; narrow the filters.")
        result = {
            "tables": kept,
            "table_count": len(kept),
            "returned_count": len(kept),
            "total_matching": total,
            "has_more": has_more,
            "next_cursor": self.codec.encode_bound("discover_catalog", binding, fingerprint, last)
            if has_more and last else None,
            "truncated": has_more,
            **base,
        }
        if not kept and filters:
            result["note"] = ("No table matches these filters. Use other keywords or drop the query, or use a subject "
                              "value exactly as listed in available_subjects.")
            result["available_subjects"] = [
                {key: row[key] for key in ("data_domain", "entity_type", "asset_type") if row.get(key)}
                | {"tables": int(row["table_count"])} for row in subjects]
        elif not kept:
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
            if self.discovery_v2 and tables:
                # the table-level contract a data need copies: grain, keys, time/entity columns, subject values
                base["table_metadata"] = {
                    row["table_name"]: {
                        **_entry(row, ("grain", "primary_key_columns", "time_column", "entity_column"),
                                 keep_null=("time_column", "entity_column")),
                        **({"subject": _entry(row, ("data_domain", "entity_type", "asset_type",
                                                    "supported_frequencies", "time_semantics",
                                                    "subject_metadata_status"), keep_null=("asset_type",))}
                           if row.get("data_domain") else {}),
                    }
                    for row in run(TABLE_META_SQL, (tables,))
                }
                if self.point_in_time and int(run(AVAILABILITY_READABLE_SQL, ())[0]["readable"]) == 4:
                    for row in run(AVAILABILITY_SQL, (tables,)):
                        if row["table_name"] in base["table_metadata"]:
                            base["table_metadata"][row["table_name"]]["availability"] = _entry(
                                row, ("point_in_time_status", "availability_rule"))
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
        if section == "COLUMNS" and self.discovery_v2:
            rows = run(COLUMNS_V2_SQL, (tables, columns, columns, ROW_CAPS["COLUMNS"] + 1))
            result = _columns_v2(rows, tables, columns, budget, current_state=self.point_in_time)
            if columns:
                present = {row["column_name"] for row in run(FOUND_COLUMNS_SQL, (tables, columns))}
                missing = [name for name in columns if name not in present]
                if missing:
                    result["unknown_columns"] = missing
            return result

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

        if section == "FORMULAS" and getattr(arguments, "formula_query", None):
            return self._formula_search(run, str(getattr(arguments, "formula_query")), budget)

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

        if section == "RELATIONSHIPS" and self.discovery_v2:
            return _relationships_v2(run(RELATIONSHIPS_V2_SQL, (tables, tables, ROW_CAPS["RELATIONSHIPS"] + 1)), budget)

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
    def _formula_search(run: QueryRunner, query: str, budget: int) -> dict[str, Any]:
        exact, words = query.lower(), query_words(query)
        rows = run(FORMULA_SEARCH_SQL, (exact, exact, words, exact, exact, exact, exact, FORMULA_SEARCH_LIMIT + 1))
        total = int(rows[0]["total_matching"]) if rows else 0
        entries = [{
            "calculation_id": row["calculation_id"],
            "calculation_name": row.get("calculation_name"),
            "description": _short(row.get("description")),
            "required_inputs": _short(row.get("required_inputs")),
            "match": "EXACT" if row["exact"] else "NAME" if row["name_hit"] else "DESCRIPTION",
            "matched_words": list(row["matched_words"]),
        } for row in rows[:FORMULA_SEARCH_LIMIT]]
        kept, _ = _fit(entries, budget)
        result: dict[str, Any] = {
            "mode": "SEARCH", "query": query, "query_words": words, "entries": kept, "returned": len(kept),
            "total_matching": total,
            "note": "Documented formula definitions, not verified or executable implementations. Pass the chosen "
                    "calculation_id values as formula_ids for full definitions.",
        }
        if len(kept) < total:
            result["truncated"] = True
            result["hint"] = ("More formulas match: make formula_query more specific, or page through "
                              "AI_formula_reference with read_catalog_rows.")
        if not kept:
            result["note"] = ("No formula matches. The search compares text only, not synonyms (for example "
                              "'Wilder' does not find 'RSI'): try another term, or ask the user which formula is "
                              "meant. Never substitute a similar formula.")
        return result

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


def catalog_specs(reader: CatalogReader, *, timeout_seconds: float, discovery_v2: bool = False,
                  codec: CursorCodec | None = None, point_in_time: bool = False) -> list[ToolSpec]:
    tools = CatalogTools(reader, discovery_v2=discovery_v2, codec=codec, point_in_time=point_in_time)
    if discovery_v2:
        return [
            ToolSpec(
                name="discover_catalog",
                description=(
                    "Find data tables in Saniti's AI catalog. Each entry gives the description, category, grain, "
                    "keys, time and entity columns, subject values (data_domain, entity_type, asset_type, "
                    "supported_frequencies, time_semantics), documentation status and how much column, calculation "
                    "and relationship metadata exists; plus the research-method and formula catalog counts. Filter "
                    "with query keywords and the subject fields; with a query the result also lists the documented "
                    "formulas matching the keywords. Page with next_cursor while has_more is true. Returns catalog "
                    "metadata only, never data rows."
                ),
                arguments_model=DiscoverArguments,
                handler=tools.discover,
                timeout_seconds=timeout_seconds,
            ),
            ToolSpec(
                name="get_catalog_details",
                description=(
                    f"Retrieve catalog metadata for up to {MAX_TABLES_PER_CALL} tables returned by discover_catalog, "
                    "with every section you need in one call. The result starts with table_metadata (grain, keys, "
                    "time/entity columns, subject values). COLUMNS: meanings, types, units, allowed aggregations, "
                    "filter/group permissions and resample rules, with per-table completeness and recovery_calls "
                    "when cut. RELATIONSHIPS: join keys, temporal rules, supported join semantics and their time or "
                    "validity columns, output grain. CALCULATIONS: documented calculation definitions. COVERAGE: "
                    "recorded date coverage and verification status. RESEARCH: global reference methods (table_names "
                    "[] for RESEARCH only; method_ids to narrow). FORMULAS: global documented formulas (table_names [] "
                    "for FORMULAS only); search them by name or description with formula_query, then read chosen ones "
                    "with formula_ids. Documented definitions are not verified or executable implementations. Large "
                    "sections are shortened or truncated and say so. Returns documentation only, never observed "
                    "values."
                ),
                arguments_model=CatalogDetailsArgumentsV2,
                handler=tools.details,
                timeout_seconds=timeout_seconds,
            ),
        ]
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
