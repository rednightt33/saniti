"""Logical datasets: many approved physical Parquet snapshots mapped to one named input.

An analysis names logical inputs (for example "prices") in its spec and binds each to one or more
SQL Governor dataset_ids. The harness, not the model, resolves a logical dataset to local files
and records the mapping in the workspace manifest. Files are combined only when they are
semantically the same thing:

* every file comes from the same approved source table as the spec input;
* every file has the identical column contract (name, type, source table, source column,
  aggregation), so no two columns with different meanings are ever merged by name;
* the grain comes from the source contract (or the group-by columns of an aggregated extract),
  never from similar-looking column names.

Different grains or meanings (daily prices, broker summaries, broker profiles) stay separate
logical datasets. Overlapping rows are handled by an explicit duplicate policy, checked on the
actual rows before execution (runtime/validator.py). The SQL Governor allowlist is unchanged; this
module only describes what the Governor already approved.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Source semantics (grain, entity/time columns, frequency, units) come from the catalog: the SQL Governor carries
# each source table's contract in the internal validator manifest of every dataset, and a V2 spec keeps the
# contracts of its approved catalog snapshot. No table name is hardcoded here.
DATE_TYPES = {"date", "timestamp", "timestamp_utc"}
NUMERIC_TYPES = {"float64", "float32", "int64", "int32", "int16"}
DUPLICATE_POLICIES = ("ERROR_ON_CONFLICT", "PREFER_LATEST_SNAPSHOT")


class BindingError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class GrantedFile:
    dataset_id: str
    manifest: dict[str, Any]
    local_name: str


def _signature(columns: list[dict[str, Any]]) -> dict[str, tuple]:
    return {c["name"]: (c.get("type"), c.get("source_table"), c.get("source_column"), c.get("aggregation"))
            for c in columns}


PARTITION_INCOMPLETE = {"PARTITION_MISSING", "PARTITION_GAP", "DATE_RANGE_NOT_COVERED"}


def _source_contract(member: GrantedFile, table: str, analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    internal = member.manifest.get("validator_manifest") or {}
    contract = (internal.get("source_contracts") or {}).get(table)
    if contract is None and analysis:
        contract = ((analysis.get("catalog") or {}).get("source_contracts") or {}).get(table)
    return contract


def bind(spec: dict[str, Any], bindings: list[dict[str, Any]], files: dict[str, GrantedFile],
         max_files: int, analysis: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Validate the dataset bindings against the approved spec and return the logical-dataset manifest.

    analysis is the stored approved contract ({spec_id, spec_sha256, ...}); for an Analysis Spec V2 every bound
    dataset must prove, through the Governor's internal validator manifest, that it was extracted for this spec
    with exactly the approved scope (verify_scope)."""
    inputs = {i["name"]: i for i in spec["inputs"]}
    names = [b["name"] for b in bindings]
    if sorted(names) != sorted(inputs) or len(set(names)) != len(names):
        raise BindingError("INPUT_BINDING_MISMATCH", f"Bind every spec input exactly once: {sorted(inputs)} "
                                                     f"(got {names}).")
    all_ids = [ds for b in bindings for ds in b["dataset_ids"]]
    if len(set(all_ids)) != len(all_ids):
        raise BindingError("INPUT_BINDING_MISMATCH", "A dataset_id may be bound to only one logical input.")
    if len(all_ids) > max_files:
        raise BindingError("INPUT_LIMIT_EXCEEDED", f"At most {max_files} input files per analysis.")
    uses = _column_uses(spec)
    logical: dict[str, dict[str, Any]] = {}
    for binding in bindings:
        spec_input = inputs[binding["name"]]
        table = spec_input["source_table"]
        members = [files[ds] for ds in binding["dataset_ids"]]
        contract = _source_contract(members[0], table, analysis)
        scope_evidence = verify_scope(binding["name"], members, analysis) \
            if analysis and analysis.get("spec_version") == "analysis_spec/v2" else None
        signature = None
        for member in members:
            manifest = member.manifest
            sources = manifest.get("source_tables") or []
            if table not in sources:
                raise BindingError("SOURCE_TABLE_MISMATCH", f"{member.dataset_id} comes from {sources}, not from "
                                                            f"{table} as the spec requires for input {binding['name']}.")
            current = _signature(manifest.get("columns") or [])
            if signature is None:
                signature, first = current, member.dataset_id
            elif current != signature:
                differing = sorted(k for k in set(current) | set(signature) if current.get(k) != signature.get(k))
                raise BindingError(
                    "INCOMPATIBLE_LOGICAL_DATASET",
                    f"{member.dataset_id} and {first} cannot form one logical dataset: columns {differing[:10]} differ "
                    f"in name, type, source, or aggregation. Bind them as separate inputs.",
                    {"differing_columns": differing[:20]})
        assert signature is not None
        missing = [c for c in spec_input["columns"] if c not in signature]
        if missing:
            raise BindingError("REQUIRED_COLUMNS_MISSING", f"Input {binding['name']} needs columns {missing}, which "
                                                           f"the bound dataset(s) do not contain.")
        aggregated = any(v[3] for v in signature.values())
        entity = spec_input.get("entity_column") or (contract or {}).get("entity_column")
        time = spec_input.get("date_column") or (contract or {}).get("time_column")
        entity = entity if entity in signature else None
        time = time if time in signature else None
        if aggregated:
            grain = sorted(k for k, v in signature.items() if not v[3])
        else:
            grain = [c for c in (contract or {}).get("grain", []) if c in signature]
        grain_complete = aggregated or bool(contract) and len(grain) == len(contract["grain"])
        if time and signature[time][0] not in DATE_TYPES:
            raise BindingError("COLUMN_TYPE_MISMATCH", f"Input {binding['name']}: {time} is {signature[time][0]}, "
                                                       f"not a date.")
        for column in uses.get(binding["name"], set()):
            if column in signature and signature[column][0] not in NUMERIC_TYPES:
                raise BindingError("COLUMN_TYPE_MISMATCH", f"Input {binding['name']}: {column} is "
                                                           f"{signature[column][0]}, not numeric.")
        policy = binding.get("duplicate_policy") or "ERROR_ON_CONFLICT"
        # AI_column_catalog units, as the Governor recorded them in the first dataset's manifest
        units = {c.get("name"): c.get("unit") for c in members[0].manifest.get("columns") or []}
        series_key = [entity, time] if entity and time else []
        # Rows are the same observation when they agree on the full grain; without a complete grain,
        # only whole-row identity is safe.
        key = grain if grain_complete and grain else sorted(signature)
        logical[binding["name"]] = {
            "name": binding["name"], "source_table": table,
            "contract": contract or {"meaning": "no semantic contract recorded", "grain": [], "frequency": None},
            "grain": grain, "grain_complete": grain_complete, "aggregated": aggregated,
            "entity_column": entity, "date_column": time, "key_columns": key, "series_key": series_key,
            "columns": [{"name": k, "type": v[0], "source_table": v[1], "source_column": v[2], "aggregation": v[3],
                         "unit": units.get(k)} for k, v in sorted(signature.items())],
            "required_columns": spec_input["columns"],
            "duplicate_policy": policy,
            "scope_evidence": scope_evidence,
            "database_features": sorted(k for k, v in signature.items() if (v[1] or "").startswith("Feature_")
                                        and k in spec_input["columns"]),
            "files": [{
                "dataset_id": m.dataset_id, "local_path": f"input/{m.local_name}",
                "checksum_sha256": m.manifest.get("checksum_sha256"), "source_tables": m.manifest.get("source_tables"),
                "query_id": m.manifest.get("query_id"), "row_count": m.manifest.get("row_count"),
                "byte_count": m.manifest.get("byte_count"), "requested_scope": m.manifest.get("requested_scope"),
                "actual_date_range": m.manifest.get("actual_date_range"),
                "entities_present_count": m.manifest.get("entities_present_count"),
                "missing_entities": m.manifest.get("missing_entities") or [],
                "missing_entities_count": m.manifest.get("missing_entities_count") or 0,
                "completeness_status": m.manifest.get("completeness_status"),
                "created_at": m.manifest.get("created_at"), "expires_at": m.manifest.get("expires_at"),
            } for m in members],
        }
    return logical


def _filter_key(item: dict[str, Any]) -> tuple:
    return (item["table"], item["column"], item["operator"], tuple(item["values"]))


def _time_ranges(filters: list[dict[str, Any]], table: str, column: str) -> list[tuple[str, str]]:
    low, high = None, None
    for item in filters:
        if (item["table"], item["column"]) != (table, column):
            continue
        values = item["values"]
        if item["operator"] == "BETWEEN":
            low, high = max(filter(None, [low, values[0]])), min(filter(None, [high, values[1]]))
        elif item["operator"] in ("GT", "GTE"):
            low = max(filter(None, [low, values[0]]))
        elif item["operator"] in ("LT", "LTE"):
            high = min(filter(None, [high, values[0]]))
        elif item["operator"] in ("EQ", "IN"):
            low, high = min(values), max(values)
    return [(low, high)] if low or high else []


def verify_scope(name: str, members: list[GrantedFile], analysis: dict[str, Any]) -> dict[str, Any]:
    """Prove that the datasets bound to one logical input are exactly the approved data plan of this spec.

    The executed scope is the Governor's own record of what it compiled; the approved plan is part of the
    immutable spec contract. Removing, changing or adding a filter or join, binding another spec's dataset,
    a different catalog version, or a missing/overlapping partition refuses the binding."""
    plan = (analysis.get("data_plan") or {}).get(name)
    if plan is None:
        raise BindingError("SCOPE_LINEAGE_MISMATCH", f"Input {name} has no approved data plan.")
    manifests = [m.manifest.get("validator_manifest") or {} for m in members]
    lineages = [v.get("lineage") for v in manifests]
    if any(not lineage for lineage in lineages) or any(not v.get("executed_scope") for v in manifests):
        raise BindingError("SCOPE_LINEAGE_MISSING", f"Input {name}: a bound dataset was not prepared from this spec "
                           f"(no data-plan lineage). Prepare the data with prepare_analysis_data.",
                           {"datasets": [m.dataset_id for m, lin in zip(members, lineages) if not lin]})
    for member, lineage in zip(members, lineages):
        expected = {"spec_id": analysis.get("spec_id"), "spec_sha256": analysis.get("spec_sha256"),
                    "scope_sha256": analysis.get("scope_sha256"), "logical_input_name": name}
        wrong = sorted(k for k, v in expected.items() if lineage.get(k) != v)
        if wrong:
            raise BindingError("SCOPE_LINEAGE_MISMATCH", f"Input {name}: dataset {member.dataset_id} was prepared for "
                               f"a different spec, scope or input ({', '.join(wrong)}).",
                               {"dataset_id": member.dataset_id, "fields": wrong})
    plans = {lin["data_plan_id"] for lin in lineages}
    counts = {lin["part_count"] for lin in lineages}
    if len(plans) != 1 or len(counts) != 1:
        raise BindingError("SCOPE_LINEAGE_MISMATCH", f"Input {name}: datasets come from different data plans.")
    parts = sorted(lin["part_index"] for lin in lineages)
    if len(set(parts)) != len(parts):
        raise BindingError("PARTITION_DUPLICATE", f"Input {name}: a partition is bound twice.")
    count = counts.pop()
    missing = sorted(set(range(1, count + 1)) - set(parts))
    if missing:
        raise BindingError("PARTITION_MISSING", f"Input {name}: partitions {missing} of {count} are not bound; the "
                           f"extracted data does not cover the approved scope.", {"missing_parts": missing})
    expected_filters = {_filter_key(f) for f in plan["filters"]}
    expected_joins = {(j["table"], j["relationship_id"]) for j in plan["joins"]}
    catalog = (analysis.get("catalog") or {}).get("tables") or {}
    time_column = plan.get("time_column")
    ranges = []
    for member, internal, lineage in zip(members, manifests, lineages):
        if internal.get("request_sha256") and lineage.get("request_sha256") != internal["request_sha256"]:
            raise BindingError("SCOPE_LINEAGE_MISMATCH", f"Input {name}: dataset {member.dataset_id} was not "
                               f"extracted from the request its data plan recorded.", {"dataset_id": member.dataset_id})
        executed = internal["executed_scope"]
        if executed.get("source_table") != plan["source_table"]:
            raise BindingError("EXECUTED_SCOPE_MISMATCH", f"Input {name}: dataset {member.dataset_id} was extracted "
                               f"from {executed.get('source_table')}, not {plan['source_table']}.")
        joins = {(j["table"], j["relationship_id"]) for j in executed.get("joins") or []}
        filters = [f for f in executed.get("filters") or []]
        scope_filters = {_filter_key(f) for f in filters
                         if not (time_column and (f["table"], f["column"]) == (plan["source_table"], time_column))}
        if joins != expected_joins or scope_filters != expected_filters or executed.get("group_by"):
            raise BindingError("EXECUTED_SCOPE_MISMATCH", f"Input {name}: dataset {member.dataset_id} was not "
                               f"extracted with the approved scope.", {
                                   "dataset_id": member.dataset_id,
                                   "missing_filters": sorted(map(list, expected_filters - scope_filters))[:10],
                                   "unexpected_filters": sorted(map(list, scope_filters - expected_filters))[:10],
                                   "missing_joins": sorted(map(list, expected_joins - joins)),
                                   "unexpected_joins": sorted(map(list, joins - expected_joins)),
                                   "grouped": bool(executed.get("group_by"))})
        for table in executed.get("tables") or []:
            actual = ((internal.get("source_contracts") or {}).get(table) or {}).get("catalog_table_sha256")
            if table in catalog and actual != catalog[table]:
                raise BindingError("CATALOG_VERSION_MISMATCH", f"Input {name}: {table} was extracted under a "
                                   f"different catalog version than the spec was approved against. Create the spec "
                                   f"again.", {"table": table})
        if time_column:
            ranges += _time_ranges(filters, plan["source_table"], time_column)
        elif _time_ranges(filters, plan["source_table"], time_column or ""):
            raise BindingError("EXECUTED_SCOPE_MISMATCH", f"Input {name}: a static input was filtered by date.")
    coverage = None
    if plan.get("date_range"):
        want = plan["date_range"]
        if len(ranges) != len(members) or any(low is None or high is None for low, high in ranges):
            raise BindingError("EXECUTED_SCOPE_MISMATCH", f"Input {name}: every part must be bounded by "
                               f"{time_column}.")
        ranges.sort()
        from datetime import date as _date, timedelta as _td
        for (low_a, high_a), (low_b, _) in zip(ranges, ranges[1:]):
            if low_b <= high_a:
                raise BindingError("PARTITION_OVERLAP", f"Input {name}: partitions overlap at {low_b}.")
            if _date.fromisoformat(low_b) != _date.fromisoformat(high_a) + _td(days=1):
                raise BindingError("PARTITION_GAP", f"Input {name}: no data was extracted between {high_a} and "
                                   f"{low_b}.", {"after": high_a, "before": low_b})
        if ranges[0][0] > want["from"] or ranges[-1][1] < want["to"]:
            raise BindingError("DATE_RANGE_NOT_COVERED", f"Input {name}: the extraction covers {ranges[0][0]} to "
                               f"{ranges[-1][1]}; the approved plan needs {want['from']} to {want['to']}.")
        coverage = {"from": ranges[0][0], "to": ranges[-1][1]}
    return {"check": f"scope.lineage.{name}", "result": "PASS", "data_plan_id": next(iter(plans)),
            "spec_id": analysis.get("spec_id"), "scope_sha256": analysis.get("scope_sha256"), "parts": count,
            "source_table": plan["source_table"], "joins": sorted(map(list, expected_joins)),
            "filters": [f for f in plan["filters"]], "date_coverage": coverage,
            "detail": "The Governor's executed scope equals the approved data plan of this spec."}


def _column_uses(spec: dict[str, Any]) -> dict[str, set[str]]:
    """Columns that verified calculations read as numbers, per logical input."""
    uses: dict[str, set[str]] = {}
    for calc in spec["calculations"]:
        function = next((p["value"] for p in calc["params"] if p["name"] == "function"), None)
        if calc["method"] == "GROUP_AGGREGATE" and function not in ("SUM", "AVG", "MEDIAN"):
            continue  # counts and extremes accept any column type; sums and averages need numbers
        if calc["method"] == "PERIOD_STAT" and function == "COUNT":
            continue
        if calc["method"] != "CUSTOM":
            uses.setdefault(calc["dataset"], set()).update(calc["columns"])
    return uses
