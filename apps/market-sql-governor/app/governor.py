"""The governed pipeline: validate -> compile -> EXPLAIN gate -> execute -> route -> snapshot."""
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
from .config import Settings
from .decisions import NEXT_ACTION, DatasetReference, GovernorResponse, GovernorStop, OutputColumn, narrowing, rejected
from .policy import Policy, ValidatedQuery, Validator
from .snapshot import ParquetBuilder, ResultStats, build_manifest, manifest_bytes
from .spec import DataRequestSpec
from .store import ObjectStore

logger = logging.getLogger("market_sql_governor")
SEQ_SCAN_NODES = {"Seq Scan", "Parallel Seq Scan", "Sample Scan"}
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

    def handle(self, request_id: str, raw_spec: Any) -> GovernorResponse:
        started = time.monotonic()
        query_id = f"qry_{uuid.uuid4().hex[:24]}"
        state: dict[str, Any] = {"source_tables": [], "requested_columns": []}
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
             dataset_id=response.dataset.dataset_id if response.dataset else None, runtime_ms=response.runtime_ms)
        return response

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
            def run(statement: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
                with connection.cursor(row_factory=dict_row) as cursor:
                    return list(cursor.execute(statement, params).fetchall())

            query = self.validator.validate(spec, Policy.load(run, spec))  # gates 1-7
            state["source_tables"] = query.source_tables
            state["warnings"] = query.warnings
            cap = s.max_dataset_rows + 1
            if spec.requested_limit is not None:
                cap = min(spec.requested_limit, cap)
            compiled = compile_query(query, cap)  # gate 8
            state["query_hash"] = compiled.query_hash
            scan_rows, cost = self._explain(connection, compiled, run)  # gate 9
            state["estimated_scan_rows"], state["estimated_plan_cost"] = scan_rows, cost
            if scan_rows > s.max_estimated_scan_rows:
                raise narrowing("ESTIMATED_SCAN_TOO_LARGE",
                                f"The planner estimates scanning {scan_rows} rows; the limit is "
                                f"{s.max_estimated_scan_rows}. Add or tighten filters.",
                                estimated_scan_rows=scan_rows, limit=s.max_estimated_scan_rows)
            if cost > s.max_plan_cost:
                raise narrowing("ESTIMATED_COST_TOO_LARGE",
                                f"The planner cost estimate {cost:.0f} exceeds the limit {s.max_plan_cost}. "
                                "Add or tighten filters.", estimated_plan_cost=cost, limit=s.max_plan_cost)
            return self._execute(connection, request_id, query_id, spec, query, compiled, scan_rows, cost)  # gate 10

    @staticmethod
    def _explain(connection: psycopg.Connection, compiled: CompiledQuery, run) -> tuple[int, float]:
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
        return largest, float(plan.get("Total Cost") or 0.0)

    def _execute(self, connection, request_id, query_id, spec, query: ValidatedQuery,
                 compiled: CompiledQuery, scan_rows: int, cost: float) -> GovernorResponse:
        s = self.settings
        names = [item.name for item in query.select]
        output_columns = [OutputColumn(name=item.name, type=item.data_type, source_table=item.table,
                                       source_column=item.column, aggregation=item.function)
                          for item in query.select]
        base = dict(request_id=request_id, query_id=query_id, query_hash=compiled.query_hash,
                    source_tables=query.source_tables, columns=output_columns, estimated_scan_rows=scan_rows,
                    estimated_plan_cost=cost, warnings=query.warnings)
        with connection.cursor(name=f"governed_{query_id}") as cursor:
            cursor.itersize = FETCH_BATCH_ROWS
            cursor.execute(compiled.statement, compiled.params)
            first = cursor.fetchmany(s.max_inline_rows + 1)
            oids = [column.type_code for column in cursor.description]
            if len(first) <= s.max_inline_rows:
                rows = [[_jsonable(value) for value in row] for row in first]
                size = len(json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                if size <= s.max_inline_output_bytes:
                    return GovernorResponse(
                        decision="INLINE_RESULT", next_action=NEXT_ACTION["INLINE_RESULT"], reason_code="OK",
                        message="Approved and executed; the observations are returned inline.",
                        returned_rows=len(rows), output_bytes=size, rows=rows, **base)
            if self.store is None:
                raise narrowing("RESULT_TOO_LARGE_FOR_INLINE",
                                "The result is too large to return inline and dataset storage is not configured. "
                                f"Narrow the request to at most {s.max_inline_rows} rows.",
                                max_inline_rows=s.max_inline_rows)
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
                batch = cursor.fetchmany(FETCH_BATCH_ROWS)
        payload = builder.finish()
        checksum = hashlib.sha256(payload).hexdigest()
        columns = [column.model_dump() for column in output_columns]
        manifest = build_manifest(
            dataset_id=dataset_id, payload=payload, checksum=checksum, columns=columns, oids=oids, stats=stats,
            source_tables=query.source_tables, query_id=query_id, query_hash=compiled.query_hash,
            request_id=request_id, spec=spec.model_dump(), requested_range=query.requested_range,
            requested_entities=query.requested_entities, retention_hours=s.dataset_retention_hours)
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


def _details(details: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(details, default=_jsonable))
