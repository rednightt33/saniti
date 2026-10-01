"""Catalog contracts and executed-scope lineage.

A catalog contract is the metadata an Analysis Spec V2 is checked against: for each named table its subject
(data_domain, entity_type, asset_type), keys, time semantics and supported frequencies, the AI-allowed columns
with their types, units and permissions, and the approved relationships that touch it. It is metadata only,
never rows. Each table gets its own content hash (catalog_table_sha256) over exactly these fields, so the
sandbox can prove that a dataset was extracted under the same catalog version its spec was approved against.

The executed scope is what the Governor actually compiled for a dataset (tables, joins with relationship ids,
every filter with its type-coerced values, grouping and aggregations), derived from the validated query, not
from anything the caller claimed. The sandbox compares it with the approved spec before any analysis runs.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

CATALOG_VERSION = "ai_catalog_contract/v1"
SUBJECT_COLUMNS = ("data_domain", "entity_type", "asset_type", "supported_frequencies", "time_semantics",
                   "subject_metadata_status")
MAX_CONTRACT_TABLES = 10
# P14 (2026-10-01): the stored values of a text column, so a filter value is matched to its stored spelling at approval;
# a column with more distinct values than this is not a category list (the same bound the value dictionary plans)
VALUE_DOMAIN_MAX = 1024
VALUE_TEXT_TYPES = {"text", "character varying", "character", "varchar"}
CHECK_SQL = """
SELECT t.relname AS table_name, pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'public' AND c.contype = 'c' AND t.relname = ANY(%s)
"""
# CHECK ((("Market Board")::text = ANY ((ARRAY['Regular'::character varying, ...])::text[])))
# CHECK ((market_board = ANY (ARRAY['Regular'::text, 'Nego'::text, 'Tunai'::text])))
CHECK_IN_RE = re.compile(r'^CHECK \(+\s*"?(?P<column>[^"()]+?)"?\)?(?:::[a-z ]+)?\s*=\s*ANY\s*'
                         r'\(+ARRAY\[(?P<values>.*)\](?:\)?::[a-z \[\]]+)?\)+$')
CHECK_VALUE_RE = re.compile(r"'((?:[^']|'')*)'::")

Runner = Callable[[str, tuple[Any, ...]], list[dict[str, Any]]]

JOIN_COLUMNS = ("supported_join_semantics", "left_time_column", "right_time_column", "effective_from_column",
                "effective_to_column")
SUBJECT_AVAILABLE_SQL = '''
SELECT count(*) AS present FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'AI_table_catalog' AND column_name = ANY(%s)
'''
COLUMN_PRESENT_SQL = '''
SELECT count(*) AS present FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = %s AND column_name = ANY(%s)
'''
TABLES_SQL = '''
SELECT table_name, description, grain, primary_key_columns, time_column, entity_column, is_active,
       ai_access_level {subject}
FROM public."AI_table_catalog" WHERE table_name = ANY(%s)
'''
COLUMNS_SQL = '''
SELECT table_name, column_name, data_type, semantic_type, unit, ai_allowed, is_sensitive, filter_allowed,
       group_by_allowed, allowed_aggregations {resample}
FROM public."AI_column_catalog" WHERE table_name = ANY(%s)
ORDER BY table_name, ordinal_position
'''
RELATIONSHIPS_SQL = '''
SELECT relationship_id, left_table, left_columns, right_table, right_columns, relationship_type,
       temporal_rule, safe_output_grain, requires_preaggregation, is_allowed, version {join}
FROM public."AI_catalog_relationships"
WHERE left_table = ANY(%s) OR right_table = ANY(%s)
ORDER BY relationship_id
'''
# IP1 Stage D (migration 20260927_006): the availability metadata of Table_Catalog (column-level SELECT for the
# Governor's reader) and the first date a point-in-time history can answer
AVAILABILITY_COLUMNS = ("observation_date_column", "data_available_at_column", "availability_rule",
                        "point_in_time_status", "historical_metadata_method")
AVAILABILITY_READABLE_SQL = '''
SELECT bool_and(has_column_privilege('public."Table_Catalog"', name, 'SELECT')) AS readable
FROM unnest(%s::text[]) AS name
'''
AVAILABILITY_SQL = '''
SELECT table_name, observation_date_column, data_available_at_column, availability_rule, point_in_time_status,
       historical_metadata_method
FROM public."Table_Catalog" WHERE table_schema = 'public' AND table_name = ANY(%s)
'''
TABLE_READABLE_SQL = '''
SELECT CASE WHEN to_regclass(%s) IS NULL THEN false ELSE has_table_privilege(to_regclass(%s), 'SELECT') END AS readable
'''
HISTORY_FROM_SQL = '''
SELECT min({start}) AS history_available_from FROM public.{table}
WHERE {end} IS NULL OR {end} > {start}
'''


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def canonical_value(value: Any) -> str:
    """One text form per typed filter value, shared by the Governor (executed scope) and the sandbox (approved
    scope): dates ISO, numbers as plain decimals without trailing zeros, booleans lower case."""
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


def _subject_available(run: Runner) -> bool:
    rows = run(SUBJECT_AVAILABLE_SQL, (list(SUBJECT_COLUMNS),))
    return bool(rows) and int(rows[0]["present"]) == len(SUBJECT_COLUMNS)


def _present(run: Runner, table: str, names: tuple[str, ...]) -> bool:
    """Whether a later catalog migration (20260925_003) is applied; older catalogs simply lack the columns."""
    rows = run(COLUMN_PRESENT_SQL, (table, list(names)))
    return bool(rows) and int(rows[0]["present"]) == len(names)


def relationships_sql(run: Runner) -> str:
    joins = _present(run, "AI_catalog_relationships", JOIN_COLUMNS)
    return RELATIONSHIPS_SQL.format(join=", " + ", ".join(JOIN_COLUMNS) if joins else "")


def _availability(run: Runner, names: list[str]) -> dict[str, dict[str, Any]] | None:
    """Table_Catalog availability metadata per table, or None where the Governor cannot read it (before migration
    20260927_006): a point-in-time spec then fails closed in the sandbox."""
    if not _present(run, "Table_Catalog", AVAILABILITY_COLUMNS):
        return None
    rows = run(AVAILABILITY_READABLE_SQL, (list(AVAILABILITY_COLUMNS) + ["table_name", "table_schema"],))
    if not rows or not rows[0]["readable"]:
        return None
    return {row["table_name"]: {key: row[key] for key in AVAILABILITY_COLUMNS}
            for row in run(AVAILABILITY_SQL, (names,))}


def _history_available_from(run: Runner, relationship: dict[str, Any]) -> str | None:
    """The first observation date an EFFECTIVE_DATED relationship can answer: the earliest non-empty validity start of
    its right (history) table, or None while that history is empty. Identifiers come from the catalog and are quoted."""
    from psycopg import sql

    relation = sql.SQL("public.{}").format(sql.Identifier(relationship["right_table"])).as_string(None)
    readable = run(TABLE_READABLE_SQL, (relation, relation))
    if not readable or not readable[0]["readable"]:
        return None  # an unreadable history answers no date (never an aborted catalog read for every table)
    query = sql.SQL(HISTORY_FROM_SQL).format(
        start=sql.Identifier(relationship["effective_from_column"]),
        end=sql.Identifier(relationship["effective_to_column"]), table=sql.Identifier(relationship["right_table"]))
    rows = run(query.as_string(None), ())
    value = rows[0]["history_available_from"] if rows else None
    return value.isoformat() if isinstance(value, date) else value


def check_value_lists(definitions: list[tuple[str, str]]) -> dict[str, dict[str, list[str]]]:
    """table -> column -> the values a single-column `column = ANY (ARRAY[...])` CHECK constraint allows. Any other
    constraint shape (several columns, ranges, expressions) is not a value list and is skipped."""
    found: dict[str, dict[str, list[str]]] = {}
    for table, definition in definitions:
        match = CHECK_IN_RE.match(definition.strip())
        if not match or " AND " in definition or " OR " in definition:
            continue
        values = [v.replace("''", "'") for v in CHECK_VALUE_RE.findall(match.group("values"))]
        if values:
            found.setdefault(table, {})[match.group("column").strip()] = sorted(dict.fromkeys(values))
    return found


def value_domains(run: Runner, tables: dict[str, dict[str, Any]], columns: dict[str, dict[str, Any]]
                  ) -> dict[str, dict[str, Any]]:
    """P14: the stored values of filterable text columns, derived from the database itself: a single-column CHECK list
    (complete by construction), else, for a groupable category column of a static table (no time column, not its
    entity column), its distinct values up to VALUE_DOMAIN_MAX. A dated column without a CHECK list and an entity
    column have no domain (entity codes are normalized by the sandbox under Part A A1.2: upper-case and trimmed)."""
    from psycopg import sql

    checks = check_value_lists([(r["table_name"], r["definition"]) for r in run(CHECK_SQL, (sorted(tables),))])
    domains: dict[str, dict[str, Any]] = {}
    for name, meta in tables.items():
        for column, info in (columns.get(name) or {}).items():
            if str(info.get("data_type") or "").lower() not in VALUE_TEXT_TYPES or not info.get("filter_allowed"):
                continue
            listed = (checks.get(name) or {}).get(column)
            if listed is not None:
                domains.setdefault(name, {})[column] = {"values": listed, "source": "CHECK_CONSTRAINT",
                                                        "complete": True}
                continue
            # rows never travel in the contract: a static table lists only its category columns (the same columns
            # get_dimension_values serves), never its entity codes
            if meta.get("time_column") or column == meta.get("entity_column") or not info.get("group_by_allowed"):
                continue
            query = sql.SQL("SELECT DISTINCT {c} AS value FROM public.{t} WHERE {c} IS NOT NULL LIMIT {n}").format(
                c=sql.Identifier(column), t=sql.Identifier(name), n=sql.Literal(VALUE_DOMAIN_MAX + 1))
            values = sorted(str(row["value"]) for row in run(query.as_string(None), ()))
            domains.setdefault(name, {})[column] = (
                {"values": values, "source": "STATIC_TABLE", "complete": True} if len(values) <= VALUE_DOMAIN_MAX
                else {"values": [], "source": "STATIC_TABLE", "complete": False})
    return domains


def load_contract(run: Runner, tables: list[str]) -> dict[str, Any]:
    """The catalog contract of the named tables (active, AI-readable tables only)."""
    names = sorted(dict.fromkeys(tables))[:MAX_CONTRACT_TABLES]
    subject = _subject_available(run)
    rows = run(TABLES_SQL.format(subject=", " + ", ".join(SUBJECT_COLUMNS) if subject else ""), (names,))
    found = {row["table_name"]: row for row in rows if row["is_active"] and row["ai_access_level"] == "BOUNDED_READ"}
    columns: dict[str, dict[str, Any]] = {name: {} for name in found}
    resample = _present(run, "AI_column_catalog", ("resample_aggregation",))
    # IP1 Stage C (migration 20260927_005): the rule for aggregating a column across entities of a finer grain (for
    # example brokers into a ticker-date-board row); absent before that migration
    cross = _present(run, "AI_column_catalog", ("cross_entity_aggregation",))
    # IP1 Stage D: HISTORICAL (the value belongs to its row's date) or CURRENT_STATE (today's value on every row)
    basis = _present(run, "AI_column_catalog", ("value_time_basis",))
    extra = (", resample_aggregation" if resample else "") + (", cross_entity_aggregation" if cross else "") + (
        ", value_time_basis" if basis else "")
    for row in run(COLUMNS_SQL.format(resample=extra), (sorted(found),)):
        if row["ai_allowed"] and not row["is_sensitive"]:
            columns[row["table_name"]][row["column_name"]] = {
                "data_type": row["data_type"], "semantic_type": row["semantic_type"], "unit": row["unit"],
                "filter_allowed": bool(row["filter_allowed"]), "group_by_allowed": bool(row["group_by_allowed"]),
                "allowed_aggregations": sorted(row["allowed_aggregations"] or []),
                **({"resample_aggregation": row["resample_aggregation"]} if resample else {}),
                **({"cross_entity_aggregation": row["cross_entity_aggregation"]} if cross else {}),
                **({"value_time_basis": row["value_time_basis"]} if basis else {})}
    relationships = [_relationship(row) for row in run(relationships_sql(run), (sorted(found), sorted(found)))]
    for rel in relationships:
        if "EFFECTIVE_DATED" in (rel.get("supported_join_semantics") or []) and rel.get("effective_from_column"):
            rel["history_available_from"] = _history_available_from(run, rel)
    availability = _availability(run, sorted(found)) if basis else None
    described: dict[str, Any] = {}
    for name, row in found.items():
        meta = {
            "table_name": name, "description": row["description"], "grain": row["grain"],
            "primary_key_columns": list(row["primary_key_columns"] or []), "entity_column": row["entity_column"],
            "time_column": row["time_column"],
            **{key: (list(row[key]) if key == "supported_frequencies" and row.get(key) is not None else row.get(key))
               for key in SUBJECT_COLUMNS},
            **({"availability": availability.get(name)} if availability is not None else {}),
        }
        touching = [rel for rel in relationships if name in (rel["left_table"], rel["right_table"])]
        meta["catalog_table_sha256"] = sha256_json({"table": {k: v for k, v in meta.items()},
                                                    "columns": columns[name], "relationships": touching})
        described[name] = meta
    contract = {"catalog_version": CATALOG_VERSION, "subject_metadata": subject,
                # IP1 Stage D: whether the contract can support a point-in-time spec (value_time_basis and the
                # Table_Catalog availability metadata are both readable); the sandbox fails closed otherwise
                **({"point_in_time_metadata": True} if availability is not None else {}),
                "tables": described,
                "columns": columns, "relationships": relationships,
                "unknown_tables": [name for name in names if name not in found]}
    contract["catalog_sha256"] = sha256_json({k: contract[k] for k in ("tables", "columns", "relationships")})
    # P14: outside the catalog hash on purpose; a static table's values change with its data, not with the catalog
    contract["value_domains"] = value_domains(run, found, columns)
    return contract


def _relationship(row: dict[str, Any]) -> dict[str, Any]:
    return {"relationship_id": row["relationship_id"], "left_table": row["left_table"],
            "left_columns": list(row["left_columns"]), "right_table": row["right_table"],
            "right_columns": list(row["right_columns"]), "relationship_type": row["relationship_type"],
            "temporal_rule": row["temporal_rule"], "safe_output_grain": row["safe_output_grain"],
            "requires_preaggregation": bool(row["requires_preaggregation"]), "is_allowed": bool(row["is_allowed"]),
            "version": row["version"],
            **({"supported_join_semantics": list(row["supported_join_semantics"] or []),
                **{key: row[key] for key in JOIN_COLUMNS[1:]}} if "supported_join_semantics" in row else {})}


def source_contract(meta: dict[str, Any]) -> dict[str, Any]:
    """The semantic contract of one source table, as the sandbox needs it to bind a logical input."""
    frequencies = meta.get("supported_frequencies")
    return {"table": meta["table_name"], "grain": list(meta.get("primary_key_columns") or []),
            "grain_description": meta.get("grain"), "entity_column": meta.get("entity_column"),
            "time_column": meta.get("time_column"), "supported_frequencies": frequencies,
            "frequency": (frequencies[0] if frequencies and len(frequencies) == 1 else None),
            "time_semantics": meta.get("time_semantics"), "data_domain": meta.get("data_domain"),
            "entity_type": meta.get("entity_type"), "asset_type": meta.get("asset_type"),
            "subject_metadata_status": meta.get("subject_metadata_status"),
            "catalog_table_sha256": meta.get("catalog_table_sha256")}


def executed_scope(query: Any) -> dict[str, Any]:
    """What the Governor compiled for one dataset, in canonical form (policy.ValidatedQuery input)."""
    table_of = {table.alias: table.name for table in query.tables}
    filters = sorted(({"table": table_of[plan.alias], "column": plan.column, "operator": plan.operator,
                       "values": [canonical_value(v) for v in plan.values]} for plan in query.filters),
                     key=canonical_json)
    return {
        "source_table": query.tables[0].name,
        "tables": [table.name for table in query.tables],
        "joins": [{"table": join.table.name, "relationship_id": join.relationship["relationship_id"]}
                  for join in query.joins],
        "filters": filters,
        "columns": [{"name": item.name, "table": item.table, "column": item.column, "aggregation": item.function}
                    for item in query.select],
        "group_by": [{"table": table_of[alias], "column": column} for alias, column in query.group_by],
        "requested_range": query.requested_range,
        "requested_entities_count": len(query.requested_entities) if query.requested_entities is not None else None,
        "limit": query.limit,
    }
