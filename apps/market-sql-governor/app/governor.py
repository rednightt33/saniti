"""The governed pipelines.

request_data: validate -> compile -> EXPLAIN gate -> execute -> immutable Parquet dataset (never rows).
lookup_fact:  the same gates on a narrow, generated request -> at most 20 source values or database
aggregates, each returned with a fact_id and logged.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pydantic import ValidationError

from .compiler import CompiledQuery, compile_query
from .catalog_contract import executed_scope, load_contract, source_contract
from .config import Settings
from .decisions import (NEXT_ACTION, DatasetReference, Fact, GovernorResponse, GovernorStop, LookupResponse,
                        OutputColumn, lookup_next_action, narrowing, rejected)
from .policy import TABLES_SQL, Policy, ValidatedQuery, Validator
from .snapshot import ParquetBuilder, ResultStats, build_manifest, manifest_bytes
from .spec import (LOOKUP_MAX_DATES, LOOKUP_MAX_VALUES, DataRequestSpec, LookupFactSpec)
from .store import ObjectStore

logger = logging.getLogger("market_sql_governor")
SEQ_SCAN_NODES = {"Seq Scan", "Parallel Seq Scan", "Sample Scan"}
TEXT_TYPES = {"text", "character varying", "character", "varchar"}
DIMENSION_VALUES_SCAN_LIMIT = 2000
DIMENSION_VALUES_RETURN_LIMIT = 200
FETCH_BATCH_ROWS = 10_000
RELTUPLES_SQL = '''
SELECT c.reltuples::bigint AS reltuples FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relname = %s
'''


class GovernorUnavailable(RuntimeError):
    """The database cannot be reached; reported as HTTP 503, never as a data decision."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def _log(event: str, **fields: Any) -> None:
    logger.info(json.dumps({"event": event, **fields}, default=str, separators=(",", ":")))


class Database:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @contextmanager
    def session(self) -> Iterator[psycopg.Connection]:
        """One read-only REPEATABLE READ transaction; policy, EXPLAIN, and data read share one snapshot."""
        s = self.settings
        try:
            connection = psycopg.connect(
                s.database_url,
                connect_timeout=s.connect_timeout_seconds,
                application_name="market-sql-governor",
                options=(
                    f"-c statement_timeout={s.statement_timeout_seconds * 1000}"
                    f" -c lock_timeout={s.lock_timeout_seconds * 1000}"
                    " -c idle_in_transaction_session_timeout=30000"
                    " -c default_transaction_read_only=on"
                ),
            )
        except psycopg.OperationalError as exc:
            raise GovernorUnavailable("The governed database is unavailable.") from exc
        try:
            connection.read_only = True
            connection.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
            yield connection
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()

    def ping(self) -> None:
        with self.session() as connection:
            connection.execute("SELECT 1")


class Governor:
    def __init__(self, settings: Settings, database: Database, store: ObjectStore | None) -> None:
        self.settings = settings
        self.database = database
        self.store = store
        self.validator = Validator(settings)

    def handle(self, request_id: str, raw_spec: Any, lineage: dict[str, Any] | None = None) -> GovernorResponse:
        started = time.monotonic()
        query_id = f"qry_{uuid.uuid4().hex[:24]}"
        state: dict[str, Any] = {"source_tables": [], "requested_columns": [], "lineage": lineage}
        try:
            try:
                spec = DataRequestSpec.model_validate(raw_spec)
            except ValidationError as exc:
                issues = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc']) or 'spec'}: {e['msg']}"
                    for e in exc.errors(include_url=False, include_input=False)[:8]
                )
                raise rejected("INVALID_REQUEST_SPEC", f"The data request spec is invalid: {issues}") from exc
            state["requested_columns"] = [f"{c.table}.{c.column}" for c in spec.columns] + [
                f"{a.function}({a.table}.{a.column})" for a in spec.aggregations]
            response = self._run(request_id, query_id, spec, state)
        except GovernorStop as stop:
            response = self._stop(request_id, query_id, stop, state)
        except psycopg.errors.QueryCanceled:
            response = self._stop(request_id, query_id, narrowing(
                "QUERY_TIMEOUT", "The query exceeded the statement timeout. Narrow the request."), state)
        except psycopg.errors.InsufficientPrivilege:
            response = self._stop(request_id, query_id, rejected(
                "DATABASE_PERMISSION_DENIED",
                "The governed database role is not permitted to read a requested table."), state)
        except psycopg.OperationalError as exc:
            raise GovernorUnavailable("The governed database is unavailable.") from exc
        except psycopg.Error:
            response = self._stop(request_id, query_id, rejected(
                "QUERY_FAILED", "The database rejected the compiled query."), state)
        response.runtime_ms = int((time.monotonic() - started) * 1000)
        _log("sql_governor_query", request_id=request_id, query_id=query_id, query_hash=response.query_hash,
             source_tables=response.source_tables or state["source_tables"],
             requested_columns=state["requested_columns"], decision=response.decision,
             reason_code=response.reason_code, next_action=response.next_action,
             estimated_scan_rows=response.estimated_scan_rows, estimated_plan_cost=response.estimated_plan_cost,
             returned_rows=response.returned_rows, output_bytes=response.output_bytes,
             dataset_id=response.dataset.dataset_id if response.dataset else None, runtime_ms=response.runtime_ms,
             data_plan_id=(lineage or {}).get("data_plan_id"), spec_id=(lineage or {}).get("spec_id"),
             logical_input=(lineage or {}).get("logical_input_name"), part=(lineage or {}).get("part_index"))
        return response

    def catalog_contract(self, request_id: str, tables: list[str]) -> dict[str, Any]:
        """Catalog metadata of the named tables (no rows), for Analysis Spec V2 approval."""
        started = time.monotonic()
        with self.database.session() as connection:
            def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
                with connection.cursor(row_factory=dict_row) as cursor:
                    return list(cursor.execute(statement, params).fetchall())
            try:
                contract = load_contract(run, tables)
            except psycopg.OperationalError as exc:
                raise GovernorUnavailable("The governed database is unavailable.") from exc
        _log("sql_governor_catalog_contract", request_id=request_id, tables=sorted(contract["tables"]),
             unknown_tables=contract["unknown_tables"], catalog_sha256=contract["catalog_sha256"],
             runtime_ms=int((time.monotonic() - started) * 1000))
        return contract

    def dimension_values(self, request_id: str, table: str, column: str, match: str | None) -> dict[str, Any]:
        """Exact category values of one catalog dimension (a groupable text column of a static table), for scope
        predicates and grouping keys. Values only: no counts, no measures, so it cannot answer an analytical question.
        The request runs through the same catalog, compile and EXPLAIN gates as any extraction."""
        started = time.monotonic()
        query_id = f"qry_{uuid.uuid4().hex[:24]}"
        state: dict[str, Any] = {"source_tables": []}
        outcome: dict[str, Any]
        try:
            with self.database.session() as connection:
                with connection.cursor(row_factory=dict_row) as cursor:
                    meta = cursor.execute(TABLES_SQL, ([table],)).fetchone()
                    column_meta = cursor.execute(
                        'SELECT data_type, group_by_allowed, ai_allowed, is_sensitive FROM public."AI_column_catalog" '
                        'WHERE table_name = %s AND column_name = %s', (table, column)).fetchone()
                if meta is None or not meta["is_active"] or meta["ai_access_level"] != "BOUNDED_READ":
                    raise rejected("TABLE_NOT_APPROVED", f"{table} is not an approved AI catalog table.")
                if column_meta is None or not column_meta["ai_allowed"] or column_meta["is_sensitive"]:
                    raise rejected("UNKNOWN_COLUMN", f"{table}.{column} is not an AI-allowed catalog column.")
                if meta["time_column"]:
                    raise rejected("DIMENSION_VALUES_STATIC_ONLY",
                                   f"{table} is dated; dimension values come from static reference tables.")
                if column == meta["entity_column"]:
                    raise rejected("DIMENSION_IS_ENTITY", f"{column} identifies entities; list them in an "
                                   "ENTITY_LIST scope instead.")
                if not column_meta["group_by_allowed"] or str(column_meta["data_type"]).lower() not in TEXT_TYPES:
                    raise rejected("NOT_A_DIMENSION", f"{table}.{column} is not a groupable text column.")
                cap = DIMENSION_VALUES_SCAN_LIMIT + 1
                spec = DataRequestSpec.model_validate({
                    "purpose": "Dimension values", "from_table": table, "columns": [{"table": table, "column": column}],
                    "joins": [], "filters": [], "group_by": [{"table": table, "column": column}], "aggregations": [],
                    "order_by": [{"table": table, "column": column, "function": None, "direction": "ASC"}],
                    "requested_limit": cap})
                _, compiled, _, _ = self._prepare(connection, spec, state, cap)
                with connection.cursor() as cursor:
                    cursor.execute(compiled.statement, compiled.params)
                    rows = cursor.fetchmany(cap)
            if len(rows) > DIMENSION_VALUES_SCAN_LIMIT:
                raise narrowing("HIGH_CARDINALITY", f"{table}.{column} has more than {DIMENSION_VALUES_SCAN_LIMIT} "
                                "distinct values; it is not a category dimension.",
                                limit=DIMENSION_VALUES_SCAN_LIMIT)
            values = [str(row[0]) if row[0] is not None else None for row in rows]
            if match:
                needle = match.casefold()
                values = [v for v in values if v is not None and needle in v.casefold()]
            outcome = {"status": "VALUES_READY", "table": table, "column": column, "match": match,
                       "values": values[:DIMENSION_VALUES_RETURN_LIMIT],
                       "truncated": len(values) > DIMENSION_VALUES_RETURN_LIMIT,
                       "note": "Exact stored values for scope predicates and grouping keys; not counts or facts."}
        except GovernorStop as stop:
            outcome = {"status": stop.decision, "reason_code": stop.reason_code, "message": stop.message,
                       "table": table, "column": column, "details": _details(stop.details)}
        except psycopg.OperationalError as exc:
            raise GovernorUnavailable("The governed database is unavailable.") from exc
        except psycopg.Error:
            outcome = {"status": "REJECTED", "reason_code": "QUERY_FAILED", "table": table, "column": column,
                       "message": "The database rejected the compiled query."}
        _log("sql_governor_dimension_values", request_id=request_id, query_id=query_id, table=table, column=column,
             status=outcome["status"], reason_code=outcome.get("reason_code"), returned=len(outcome.get("values") or []),
             values_sha256=hashlib.sha256(json.dumps(outcome.get("values") or []).encode()).hexdigest(),
             runtime_ms=int((time.monotonic() - started) * 1000))
        return outcome

    def _stop(self, request_id: str, query_id: str, stop: GovernorStop, state: dict[str, Any]) -> GovernorResponse:
        return GovernorResponse(
            decision=stop.decision, next_action=NEXT_ACTION[stop.decision], reason_code=stop.reason_code,
            message=stop.message, request_id=request_id, query_id=query_id,
            query_hash=state.get("query_hash"), source_tables=state["source_tables"],
            estimated_scan_rows=state.get("estimated_scan_rows"),
            estimated_plan_cost=state.get("estimated_plan_cost"), details=_details(stop.details),
            warnings=state.get("warnings", []),
        )

    def _run(self, request_id: str, query_id: str, spec: DataRequestSpec, state: dict[str, Any]) -> GovernorResponse:
        s = self.settings
        with self.database.session() as connection:
            cap = s.max_dataset_rows + 1
            if spec.requested_limit is not None:
                cap = min(spec.requested_limit, cap)
            query, compiled, scan_rows, cost = self._prepare(connection, spec, state, cap)
            if self.store is None:
                raise rejected("DATASET_STORAGE_UNAVAILABLE",
                               "Approved data requests are delivered only as datasets, and dataset storage is not "
                               "configured. Use lookup_fact for specific source values.")
            return self._execute(connection, request_id, query_id, spec, query, compiled, scan_rows, cost,
                                 state.get("lineage"))  # gate 10

    def _prepare(self, connection: psycopg.Connection, spec: DataRequestSpec, state: dict[str, Any],
                 cap: int) -> tuple[ValidatedQuery, CompiledQuery, int, float]:
        """Gates 1-9, shared by request_data and lookup_fact."""
        s = self.settings

        def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(statement, params).fetchall())

        query = self.validator.validate(spec, Policy.load(run, spec))  # gates 1-7
        state["source_tables"] = query.source_tables
        state["warnings"] = query.warnings
        compiled = compile_query(query, cap)  # gate 8
        state["query_hash"] = compiled.query_hash
        scan_rows, cost, result_rows = self._explain(connection, compiled, run)  # gate 9
        state["estimated_scan_rows"], state["estimated_plan_cost"] = scan_rows, cost
        if scan_rows > s.max_estimated_scan_rows:
            raise narrowing("ESTIMATED_SCAN_TOO_LARGE",
                            f"The planner estimates scanning {scan_rows} rows; the limit is "
                            f"{s.max_estimated_scan_rows}. Add or tighten filters.",
                            estimated_scan_rows=scan_rows, limit=s.max_estimated_scan_rows)
        if result_rows > s.max_dataset_rows:
            raise narrowing("ESTIMATED_RESULT_TOO_LARGE",
                            f"The planner estimates more than {s.max_dataset_rows} result rows, above the dataset "
                            "limit. Add or tighten filters, or aggregate.",
                            estimated_result_rows=result_rows, limit=s.max_dataset_rows)
        if cost > s.max_plan_cost:
            raise narrowing("ESTIMATED_COST_TOO_LARGE",
                            f"The planner cost estimate {cost:.0f} exceeds the limit {s.max_plan_cost}. "
                            "Add or tighten filters.", estimated_plan_cost=cost, limit=s.max_plan_cost)
        return query, compiled, scan_rows, cost

    @staticmethod
    def _explain(connection: psycopg.Connection, compiled: CompiledQuery, run) -> tuple[int, float, int]:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("EXPLAIN (FORMAT JSON) {}").format(compiled.statement), compiled.params)
            plan = cursor.fetchone()[0][0]["Plan"]
        largest = 0
        stack = [plan]
        while stack:
            node = stack.pop()
            rows = int(node.get("Plan Rows") or 0)
            if node.get("Node Type") in SEQ_SCAN_NODES and node.get("Relation Name"):
                found = run(RELTUPLES_SQL, (node["Relation Name"],))
                if found and int(found[0]["reltuples"]) > rows:
                    rows = int(found[0]["reltuples"])  # a sequential scan reads the whole relation
            largest = max(largest, rows)
            stack.extend(node.get("Plans") or [])
        # The root estimate is the result size; the compiled LIMIT caps it at SQL_MAX_DATASET_ROWS + 1.
        return largest, float(plan.get("Total Cost") or 0.0), int(plan.get("Plan Rows") or 0)

    def _execute(self, connection, request_id, query_id, spec, query: ValidatedQuery,
                 compiled: CompiledQuery, scan_rows: int, cost: float,
                 lineage: dict[str, Any] | None = None) -> GovernorResponse:
        s = self.settings

        def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
            with connection.cursor(row_factory=dict_row) as cursor:
                return list(cursor.execute(statement, params).fetchall())

        # the catalog version and source semantics this extraction ran under (same snapshot as the data)
        contract = load_contract(run, query.source_tables)
        names = [item.name for item in query.select]
        output_columns = [OutputColumn(name=item.name, type=item.data_type, source_table=item.table,
                                       source_column=item.column, aggregation=item.function, unit=item.unit)
                          for item in query.select]
        base = dict(request_id=request_id, query_id=query_id, query_hash=compiled.query_hash,
                    source_tables=query.source_tables, columns=output_columns, estimated_scan_rows=scan_rows,
                    estimated_plan_cost=cost, warnings=query.warnings)
        deadline = time.monotonic() + s.max_execution_seconds
        with connection.cursor(name=f"governed_{query_id}") as cursor:
            cursor.itersize = FETCH_BATCH_ROWS
            cursor.execute(compiled.statement, compiled.params)
            first = cursor.fetchmany(FETCH_BATCH_ROWS)
            oids = [column.type_code for column in cursor.description]
            dataset_id = f"ds_{uuid.uuid4().hex[:24]}"
            index = {name: position for position, name in enumerate(names)}
            stats = ResultStats(index.get(query.time_output), index.get(query.entity_output))
            builder = ParquetBuilder(names, oids, s.max_dataset_bytes,
                                     {"dataset_id": dataset_id, "query_hash": compiled.query_hash})
            batch = first
            while batch:
                stats.add(batch)
                if stats.rows > s.max_dataset_rows:
                    raise narrowing("DATASET_TOO_LARGE",
                                    f"The approved result exceeds {s.max_dataset_rows} rows. Narrow the request.",
                                    limit_rows=s.max_dataset_rows)
                builder.write(batch)
                if time.monotonic() > deadline:
                    # statement_timeout bounds each FETCH; this bounds the whole extraction.
                    raise narrowing("QUERY_TIMEOUT",
                                    f"The extraction exceeded {s.max_execution_seconds} seconds. Narrow the request.",
                                    limit_seconds=s.max_execution_seconds)
                batch = cursor.fetchmany(FETCH_BATCH_ROWS)
        payload = builder.finish()
        checksum = hashlib.sha256(payload).hexdigest()
        columns = [column.model_dump() for column in output_columns]
        manifest = build_manifest(
            dataset_id=dataset_id, payload=payload, checksum=checksum, columns=columns, oids=oids, stats=stats,
            source_tables=query.source_tables, query_id=query_id, query_hash=compiled.query_hash,
            request_id=request_id, spec=spec.model_dump(), requested_range=query.requested_range,
            requested_entities=query.requested_entities, retention_hours=s.dataset_retention_hours,
            lineage=lineage, executed=executed_scope(query),
            source_contracts={name: source_contract(meta) for name, meta in contract["tables"].items()})
        manifest_raw, manifest_checksum = manifest_bytes(manifest)
        self.store.put_immutable(f"datasets/{dataset_id}/data.parquet", payload,
                                 "application/vnd.apache.parquet", checksum)
        self.store.put_immutable(f"datasets/{dataset_id}/manifest.json", manifest_raw,
                                 "application/json", manifest_checksum)
        dataset = DatasetReference(
            dataset_id=dataset_id, format="PARQUET", row_count=manifest["row_count"],
            column_count=manifest["column_count"], byte_count=manifest["byte_count"], checksum_sha256=checksum,
            actual_date_range=manifest["actual_date_range"],
            entities_present_count=manifest["entities_present_count"],
            missing_entities=(manifest["missing_entities"] or [])[:100] if manifest["missing_entities"] is not None
            else None,
            completeness_status=manifest["completeness_status"], created_at=manifest["created_at"],
            expires_at=manifest["expires_at"])
        return GovernorResponse(
            decision="DATASET_READY", next_action=NEXT_ACTION["DATASET_READY"], reason_code="OK",
            message="Approved and extracted as an immutable Parquet snapshot; only its reference is returned.",
            returned_rows=0, output_bytes=0, dataset=dataset, **base)


    # ------------------------------------------------------------------ lookup_fact

    def lookup(self, request_id: str, raw_spec: Any) -> LookupResponse:
        started = time.monotonic()
        query_id = f"qry_{uuid.uuid4().hex[:24]}"
        state: dict[str, Any] = {"source_tables": []}
        spec: LookupFactSpec | None = None
        try:
            try:
                spec = LookupFactSpec.model_validate(raw_spec)
            except ValidationError as exc:
                errors = exc.errors(include_url=False, include_input=False)
                issues = "; ".join(f"{'.'.join(str(p) for p in e['loc']) or 'spec'}: {e['msg']}" for e in errors[:8])
                shape = any(e["type"] in ("extra_forbidden", "literal_error", "too_long") for e in errors)
                raise rejected("LOOKUP_NOT_ALLOWED" if shape else "INVALID_LOOKUP_SPEC",
                               f"The lookup is outside the lookup_fact contract: {issues}. Rankings, statistics, "
                               "and larger requests belong to request_data plus a Python analysis." if shape else
                               f"The lookup spec is invalid: {issues}") from exc
            response = self._lookup(request_id, query_id, spec, state)
        except GovernorStop as stop:
            response = LookupResponse(
                decision=stop.decision, next_action=lookup_next_action(stop.decision, stop.reason_code),
                reason_code=stop.reason_code, message=stop.message, request_id=request_id, query_id=query_id,
                query_hash=state.get("query_hash"), mode=spec.mode if spec else None,
                table=spec.table if spec else None, details=_details(stop.details), warnings=state.get("warnings", []))
        except psycopg.errors.QueryCanceled:
            response = LookupResponse(decision="NEEDS_NARROWING", next_action="REVISE_LOOKUP",
                                      reason_code="QUERY_TIMEOUT", message="The lookup exceeded the statement timeout.",
                                      request_id=request_id, query_id=query_id)
        except psycopg.errors.InsufficientPrivilege:
            response = LookupResponse(decision="REJECTED", next_action="STOP_OR_REFORMULATE",
                                      reason_code="DATABASE_PERMISSION_DENIED",
                                      message="The governed database role is not permitted to read this table.",
                                      request_id=request_id, query_id=query_id)
        except psycopg.OperationalError as exc:
            raise GovernorUnavailable("The governed database is unavailable.") from exc
        except psycopg.Error:
            response = LookupResponse(decision="REJECTED", next_action="STOP_OR_REFORMULATE",
                                      reason_code="QUERY_FAILED", message="The database rejected the compiled query.",
                                      request_id=request_id, query_id=query_id)
        response.runtime_ms = int((time.monotonic() - started) * 1000)
        _log("sql_governor_lookup", request_id=request_id, query_id=query_id, query_hash=response.query_hash,
             mode=response.mode, table=response.table, decision=response.decision, reason_code=response.reason_code,
             next_action=response.next_action, fact_count=len(response.facts),
             facts=[{"fact_id": f.fact_id, "column": f.column, "aggregation": f.aggregation, "entity": f.entity,
                     "date": f.date} for f in response.facts],
             values_sha256=hashlib.sha256(json.dumps([f.value for f in response.facts], default=str)
                                          .encode()).hexdigest() if response.facts else None,
             runtime_ms=response.runtime_ms)
        return response

    def _lookup(self, request_id: str, query_id: str, spec: LookupFactSpec,
                state: dict[str, Any]) -> LookupResponse:
        if spec.dates and spec.date_range:
            raise rejected("INVALID_LOOKUP_SPEC", "Give either dates or date_range, not both.")
        if spec.mode == "VALUE" and (not spec.columns or spec.aggregations or spec.per_entity is not None):
            raise rejected("LOOKUP_NOT_ALLOWED", "VALUE lookups take 1-4 columns, no aggregations, and per_entity "
                           "null. Aggregates use mode AGGREGATE; statistics use request_data plus a Python analysis.")
        if spec.mode == "AGGREGATE" and (spec.columns or not spec.aggregations or spec.per_entity is None):
            raise rejected("INVALID_LOOKUP_SPEC", "AGGREGATE lookups take 1-4 aggregations, columns null, and "
                           "per_entity true or false.")
        entities = list(dict.fromkeys(spec.entities))
        with self.database.session() as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                meta = cursor.execute(TABLES_SQL, ([spec.table],)).fetchone()
            if meta is None:
                raise rejected("TABLE_NOT_APPROVED", f"{spec.table} is not an approved AI catalog table.")
            entity, time_column = meta["entity_column"], meta["time_column"]
            if not entity:
                raise rejected("LOOKUP_NOT_ALLOWED", f"{spec.table} has no entity column to look up by.")
            if not time_column and (spec.dates or spec.date_range):
                raise rejected("INVALID_LOOKUP_SPEC", f"{spec.table} has no date column; dates must be null.")
            if time_column and not (spec.dates or spec.date_range):
                raise rejected("INVALID_LOOKUP_SPEC", f"{spec.table} is dated; give dates or date_range.")
            filters: list[dict[str, Any]] = [{"table": spec.table, "column": entity, "operator": "IN",
                                              "value": entities}]
            scope: dict[str, Any] = {"entities": entities}
            if spec.dates:
                dates = sorted(set(spec.dates))
                filters.append({"table": spec.table, "column": time_column, "operator": "IN", "value": dates})
                scope["dates"] = dates
            elif spec.date_range:
                filters.append({"table": spec.table, "column": time_column, "operator": "BETWEEN",
                                "value": [spec.date_range.start, spec.date_range.end]})
                scope.update({"from": spec.date_range.start, "to": spec.date_range.end})
            keys = [entity] + ([time_column] if time_column else [])
            if spec.mode == "VALUE":
                value_columns = [c for c in dict.fromkeys(spec.columns) if c not in keys]
                scope["columns"] = value_columns
                if not value_columns:
                    raise rejected("INVALID_LOOKUP_SPEC", "Name at least one value column besides the key columns.")
                request = {"columns": [{"table": spec.table, "column": c} for c in keys + value_columns],
                           "group_by": [], "aggregations": [],
                           "order_by": [{"table": spec.table, "column": c, "function": None, "direction": "ASC"}
                                        for c in keys]}
                cap = LOOKUP_MAX_VALUES // len(value_columns) + 1
            else:
                scope["aggregations"] = [f"{a.function}({a.column})" for a in spec.aggregations]
                scope["per_entity"] = spec.per_entity
                grouped = [{"table": spec.table, "column": entity}] if spec.per_entity else []
                request = {"columns": grouped, "group_by": grouped,
                           "aggregations": [{"table": spec.table, "column": a.column, "function": a.function}
                                            for a in spec.aggregations],
                           "order_by": [{"table": spec.table, "column": entity, "function": None, "direction": "ASC"}]
                           if spec.per_entity else []}
                cap = LOOKUP_MAX_VALUES // len(spec.aggregations) + 1
            data_spec = DataRequestSpec.model_validate({
                "purpose": spec.purpose, "from_table": spec.table, "joins": [], "filters": filters,
                "requested_limit": cap, **request})
            query, compiled, _, _ = self._prepare(connection, data_spec, state, cap)
            state["query_hash"] = compiled.query_hash
            with connection.cursor() as cursor:
                cursor.execute(compiled.statement, compiled.params)
                rows = cursor.fetchmany(cap)
        names = [item.name for item in query.select]
        facts: list[Fact] = []
        if spec.mode == "VALUE":
            if len(rows) * len(value_columns) > LOOKUP_MAX_VALUES or len(rows) >= cap:
                raise rejected("LOOKUP_TOO_LARGE", f"The lookup matches more than {LOOKUP_MAX_VALUES} values. Narrow "
                               "the entities, dates, or columns, or use request_data plus a Python analysis.",
                               max_values=LOOKUP_MAX_VALUES)
            date_index = names.index(time_column) if time_column else None
            if date_index is not None and len({row[date_index] for row in rows}) > LOOKUP_MAX_DATES:
                raise rejected("LOOKUP_TOO_LARGE", f"The date range covers more than {LOOKUP_MAX_DATES} dates. Narrow "
                               "it, or use request_data plus a Python analysis.", max_dates=LOOKUP_MAX_DATES)
            for row in rows:
                for column in value_columns:
                    facts.append(Fact(fact_id=f"fct_{uuid.uuid4().hex[:24]}", kind="VALUE", table=spec.table,
                                      column=column, aggregation=None, entity=str(row[0]),
                                      date=_jsonable(row[date_index]) if date_index is not None else None, scope=None,
                                      value=_jsonable(row[names.index(column)]), query_id=query_id))
            if spec.dates:  # explicit keys: report every (entity, date) the source has no row for
                found = {(str(row[0]), _jsonable(row[date_index])) for row in rows}
                missing = [{"entity": e, "date": d} for e in entities for d in scope["dates"] if (e, d) not in found]
            else:
                present = {str(row[0]) for row in rows}
                missing = [{"entity": e} for e in entities if e not in present]
        else:
            if len(rows) >= cap:
                raise rejected("LOOKUP_TOO_LARGE", f"The lookup returns more than {LOOKUP_MAX_VALUES} values.",
                               max_values=LOOKUP_MAX_VALUES)
            offset = 1 if spec.per_entity else 0
            for row in rows:
                ent = str(row[0]) if spec.per_entity else None
                fact_scope = {k: v for k, v in scope.items() if k in ("entities", "dates", "from", "to")}
                if ent is not None:
                    fact_scope["entities"] = [ent]
                for index, agg in enumerate(spec.aggregations):
                    facts.append(Fact(fact_id=f"fct_{uuid.uuid4().hex[:24]}", kind="AGGREGATE", table=spec.table,
                                      column=agg.column, aggregation=agg.function, entity=ent, date=None,
                                      scope=fact_scope, value=_jsonable(row[offset + index]), query_id=query_id))
            present = {str(row[0]) for row in rows} if spec.per_entity else set(entities)
            missing = [{"entity": e} for e in entities if e not in present]
        return LookupResponse(
            decision="FACTS_READY", next_action="USE_FACTS", reason_code="OK",
            message="Approved; each value is a governed fact with its own fact_id.", request_id=request_id,
            query_id=query_id, query_hash=compiled.query_hash, mode=spec.mode, table=spec.table, scope=scope,
            facts=facts, missing=missing, warnings=query.warnings)


def _details(details: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(details, default=_jsonable))
