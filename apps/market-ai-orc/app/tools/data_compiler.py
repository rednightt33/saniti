"""prepare_analysis_data: the backend DataRequestCompiler between an approved Analysis Spec V2 and the SQL Governor.

The model writes one spec. After the sandbox approves it (spec_id, immutable contract with a data plan per logical
input), the model only names the spec_id; this module

1. reads the approved contract from the sandbox (same request only);
2. compiles each logical input's plan into a Data Request Spec: the input's columns, the catalog relationship joins
   and attribute/entity filters of the approved scope, and the warm-up date range the spec resolved;
3. submits each request to the SQL Governor with data-plan lineage (spec_id, spec_sha256, scope_sha256,
   data_plan_id, input name, part i of n, request_sha256);
4. when the Governor asks for a narrower request because of size (date range, scan, result rows), splits the date
   range into contiguous partitions and resubmits; this never changes the entities, predicates, metric or period;
5. returns an input bundle (bundle id -> dataset ids per input) that run_python_analysis binds server-side.

The sandbox independently proves each bound dataset's executed scope equals the approved plan, so a compiler bug
cannot silently widen or narrow the analysed population. No SQL text exists here, and the Governor stays
authoritative for every physical check.
"""
from __future__ import annotations

import hashlib
import json
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .registry import ToolSpec
from .request_data import DataRequestSpec, GovernorClient, current_request_id

SPEC_ID_PATTERN = r"^spec_[0-9a-f]{24}$"
MAX_PARTS = 16
BUNDLE_TTL_SECONDS = 4 * 3600
MAX_BUNDLES = 500
# Governor reasons a smaller physical extraction can satisfy without changing the scope
PARTITIONABLE = {"DATE_RANGE_TOO_LARGE", "ESTIMATED_SCAN_TOO_LARGE", "ESTIMATED_RESULT_TOO_LARGE",
                 "DATASET_TOO_LARGE", "QUERY_TIMEOUT", "ESTIMATED_COST_TOO_LARGE"}
NUMERIC_INT = ("smallint", "integer", "bigint")
NUMERIC_FLOAT = ("numeric", "real", "double precision")
FORBIDDEN_ACTIONS = ["CHANGE_USER_SCOPE", "SAMPLE_WITHOUT_PERMISSION", "DROP_ENTITIES", "SHORTEN_PERIOD",
                     "CHANGE_METRIC"]


class PrepareAnalysisDataArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec_id: str = Field(pattern=SPEC_ID_PATTERN, description="spec_id of an approved Analysis Spec V2.")


def canonical_json(value: Any) -> str:
    """Byte-identical to the Governor's catalog_contract.canonical_json (request_sha256 lineage)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _typed(value: str, data_type: str) -> Any:
    kind = (data_type or "text").lower()
    if kind in NUMERIC_INT:
        return int(value)
    if kind in NUMERIC_FLOAT:
        return float(value) if any(c in value for c in ".eE") else int(value)
    if kind == "boolean":
        return value == "true"
    return value


def _filter(item: dict[str, Any]) -> dict[str, Any]:
    values = [_typed(v, item.get("data_type", "text")) for v in item["values"]]
    operator = item["operator"]
    value: Any = None if operator in ("IS_NULL", "IS_NOT_NULL") else values if operator == "IN" else values[0]
    return {"table": item["table"], "column": item["column"], "operator": operator, "value": value}


def compile_request(entry: dict[str, Any], window: tuple[str, str] | None, purpose: str) -> dict[str, Any]:
    """One Data Request Spec for one logical input (and one date partition)."""
    filters = [_filter(item) for item in entry["filters"]]
    if window is not None:
        filters.append({"table": entry["source_table"], "column": entry["time_column"], "operator": "BETWEEN",
                        "value": [window[0], window[1]]})
    spec = DataRequestSpec.model_validate({
        "purpose": purpose[:500], "from_table": entry["source_table"],
        "columns": [{"table": entry["source_table"], "column": c} for c in dict.fromkeys(entry["columns"])],
        "joins": [{"table": j["table"], "relationship_id": j["relationship_id"]} for j in entry["joins"]],
        "filters": filters, "group_by": [], "aggregations": [], "order_by": [], "requested_limit": None})
    return spec.model_dump()


def split_range(start: str, end: str, parts: int) -> list[tuple[str, str]]:
    """Contiguous, non-overlapping partitions covering [start, end] exactly."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    days = (last - first).days + 1
    parts = max(1, min(parts, days))
    size = math.ceil(days / parts)
    windows, cursor = [], first
    while cursor <= last:
        stop = min(last, cursor + timedelta(days=size - 1))
        windows.append((cursor.isoformat(), stop.isoformat()))
        cursor = stop + timedelta(days=1)
    return windows


def _next_parts(response: dict[str, Any], window: tuple[str, str] | None, parts: int) -> int | None:
    """How many partitions a size refusal needs, or None when partitioning cannot help."""
    if window is None or response.get("reason_code") not in PARTITIONABLE:
        return None
    details = response.get("details") or {}
    if response.get("reason_code") == "DATE_RANGE_TOO_LARGE" and details.get("max_days"):
        span = (date.fromisoformat(window[1]) - date.fromisoformat(window[0])).days + 1
        needed = parts * math.ceil(span / max(1, int(details["max_days"])))
        return needed if needed > parts else parts * 2
    return parts * 2


def rejection(stage: str, response: dict[str, Any], *, input_name: str, parts: int, retryable: bool) -> dict[str, Any]:
    """A machine-readable refusal: what failed, the observed value and limit, and what may or may not be done."""
    details = dict(response.get("details") or {})
    reason = response.get("reason_code") or response.get("decision")
    limit = {k: v for k, v in details.items() if k in ("limit", "max_days", "limit_rows", "limit_bytes",
                                                       "limit_seconds")}
    observed = {k: v for k, v in details.items() if k in ("estimated_scan_rows", "estimated_result_rows",
                                                          "estimated_plan_cost", "effective_range")}
    field_name = "time_scope" if reason in ("DATE_RANGE_TOO_LARGE", "TIME_FILTER_REQUIRED",
                                           "OUTSIDE_VERIFIED_COVERAGE") else "scope"
    allowed = ["REPORT_LIMITATION"]
    if reason in ("OUTSIDE_VERIFIED_COVERAGE",):
        allowed = ["REPORT_MISSING_SCOPE", "ASK_USER_FOR_A_COVERED_PERIOD"]
    elif reason in ("UNKNOWN_COLUMN", "TABLE_NOT_APPROVED", "RELATIONSHIP_NOT_ALLOWED", "FILTER_NOT_ALLOWED",
                    "COLUMN_NOT_ALLOWED", "INVALID_FILTER_VALUE", "UNKNOWN_RELATIONSHIP"):
        allowed = ["REVISE_SPEC_FROM_CATALOG"]
    elif reason in PARTITIONABLE:
        # the backend already partitioned up to its limit: nothing semantics-preserving is left to try
        allowed = ["REPORT_LIMITATION", "ASK_USER_TO_NARROW_THE_SCOPE"]
    return {"stage": stage, "status": response.get("decision"), "reason_code": reason, "input": input_name,
            "field": field_name, "message": str(response.get("message") or "")[:400], "observed": observed,
            "limit": limit, "partitions_tried": parts, "allowed_actions": allowed,
            "forbidden_actions": FORBIDDEN_ACTIONS, "retryable": retryable}


@dataclass
class Bundle:
    bundle_id: str
    request_id: str
    spec_id: str
    data_plan_id: str
    inputs: dict[str, list[str]]
    created: float = field(default_factory=time.monotonic)


class BundleStore:
    """Prepared input bundles of recent runs (memory only; a bundle is valid for its own request and spec)."""

    def __init__(self) -> None:
        self._items: dict[str, Bundle] = {}
        self._lock = threading.Lock()

    def put(self, bundle: Bundle) -> None:
        with self._lock:
            now = time.monotonic()
            for key in [k for k, b in self._items.items() if now - b.created > BUNDLE_TTL_SECONDS]:
                del self._items[key]
            while len(self._items) >= MAX_BUNDLES:
                del self._items[next(iter(self._items))]
            self._items[bundle.bundle_id] = bundle

    def get(self, bundle_id: str) -> Bundle | None:
        with self._lock:
            return self._items.get(bundle_id)

    def resolve(self, bundle_id: str, request_id: str, spec_id: str) -> Bundle | None:
        """The bundle, only for the request and spec it was prepared for."""
        bundle = self.get(bundle_id)
        if bundle is None or bundle.request_id != request_id or bundle.spec_id != spec_id:
            return None
        return bundle


class DataRequestCompiler:
    def __init__(self, sandbox: Any, governor: GovernorClient, bundles: BundleStore) -> None:
        self.sandbox = sandbox
        self.governor = governor
        self.bundles = bundles

    def prepare(self, spec_id: str) -> dict[str, Any]:
        request_id = current_request_id.get()
        contract = self.sandbox.get_spec(spec_id)
        if contract is None or contract.get("request_id") != request_id or \
                contract.get("status") not in ("APPROVED", "APPROVED_WITH_UNVERIFIED"):
            return {"status": "REJECTED", "next_action": "CREATE_ANALYSIS_SPEC", "rejection": {
                "stage": "SPEC", "status": "REJECTED", "reason_code": "SPEC_NOT_FOUND", "retryable": False,
                "message": "No approved spec with this spec_id exists for this request.",
                "allowed_actions": ["CREATE_ANALYSIS_SPEC"], "forbidden_actions": FORBIDDEN_ACTIONS}}
        if contract.get("spec_version") != "analysis_spec/v2" or not contract.get("data_plan"):
            return {"status": "REJECTED", "next_action": "CREATE_ANALYSIS_SPEC", "rejection": {
                "stage": "SPEC", "status": "REJECTED", "reason_code": "SPEC_VERSION_NOT_SUPPORTED", "retryable": False,
                "message": "prepare_analysis_data needs an Analysis Spec V2 (spec_version 2.0).",
                "allowed_actions": ["CREATE_ANALYSIS_SPEC"], "forbidden_actions": FORBIDDEN_ACTIONS}}
        plan_id = f"plan_{secrets.token_hex(12)}"
        purpose = f"Analysis input for {spec_id}: {contract['spec']['question']}"
        prepared: list[dict[str, Any]] = []
        inputs: dict[str, list[str]] = {}
        for name in sorted(contract["data_plan"]):
            entry = contract["data_plan"][name]
            outcome = self._prepare_input(contract, spec_id, plan_id, name, entry, purpose)
            if outcome["status"] != "READY":
                return {"status": outcome["status"], "spec_id": spec_id, "data_plan_id": plan_id,
                        "prepared_inputs": prepared, "rejection": outcome["rejection"],
                        "next_action": "REVISE_SPEC" if outcome["rejection"]["allowed_actions"] == [
                            "REVISE_SPEC_FROM_CATALOG"] else "REPORT_LIMITATION"}
            inputs[name] = [d["dataset_id"] for d in outcome["datasets"]]
            prepared.append({"input": name, "source_table": entry["source_table"], "role": entry["role"],
                             "parts": len(outcome["datasets"]), "datasets": outcome["datasets"],
                             "rows": sum(d["row_count"] or 0 for d in outcome["datasets"])})
        bundle = Bundle(f"bundle_{secrets.token_hex(12)}", request_id or "", spec_id, plan_id, inputs)
        self.bundles.put(bundle)
        return {"status": "READY", "spec_id": spec_id, "input_bundle_id": bundle.bundle_id, "data_plan_id": plan_id,
                "scope_sha256": contract.get("scope_sha256"), "inputs": prepared,
                "next_action": "RUN_PYTHON_ANALYSIS"}

    def _prepare_input(self, contract: dict[str, Any], spec_id: str, plan_id: str, name: str, entry: dict[str, Any],
                       purpose: str) -> dict[str, Any]:
        date_range = entry.get("date_range")
        full = (date_range["from"], date_range["to"]) if date_range else None
        parts = 1
        while True:
            windows = split_range(full[0], full[1], parts) if full else [None]
            datasets, refusal, refused_window = [], None, None
            for index, window in enumerate(windows, start=1):
                request = compile_request(entry, window, purpose)
                lineage = {"spec_id": spec_id, "spec_sha256": contract["spec_sha256"],
                           "scope_sha256": contract["scope_sha256"], "data_plan_id": plan_id,
                           "logical_input_name": name, "part_index": index, "part_count": len(windows),
                           "request_sha256": sha256_json(request),
                           "catalog_sha256": (contract.get("catalog") or {}).get("catalog_sha256"),
                           "partition": {"column": entry["time_column"], "from": window[0], "to": window[1]}
                           if window else None}
                response = self.governor.submit(request, lineage)
                if response.get("decision") != "DATASET_READY":
                    refusal, refused_window = response, window
                    break
                dataset = response.get("dataset") or {}
                datasets.append({k: dataset.get(k) for k in (
                    "dataset_id", "row_count", "completeness_status", "actual_date_range", "entities_present_count",
                    "missing_entities")} | {"part": index})
            if refusal is None:
                return {"status": "READY", "datasets": datasets}
            wanted = _next_parts(refusal, refused_window, len(windows))
            if wanted is None or wanted > MAX_PARTS:
                # the compiler has used every semantics-preserving option; the model must not retry the same spec
                return {"status": refusal.get("decision") or "REJECTED",
                        "rejection": rejection("SQL_GOVERNOR", refusal, input_name=name, parts=len(windows),
                                               retryable=False)}
            parts = wanted


def prepare_spec(compiler: DataRequestCompiler, *, timeout_seconds: float, max_result_bytes: int) -> ToolSpec:
    from .analysis import PREPARE_DESCRIPTION

    def handler(arguments: BaseModel) -> dict[str, Any]:
        assert isinstance(arguments, PrepareAnalysisDataArgs)
        return compiler.prepare(arguments.spec_id)

    return ToolSpec(name="prepare_analysis_data", description=PREPARE_DESCRIPTION,
                    arguments_model=PrepareAnalysisDataArgs, handler=handler, timeout_seconds=timeout_seconds,
                    max_result_bytes=max_result_bytes)


__all__ = ["BundleStore", "DataRequestCompiler", "PrepareAnalysisDataArgs", "compile_request", "prepare_spec",
           "split_range"]
