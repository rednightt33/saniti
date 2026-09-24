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

# Semantic contracts of the approved source tables (grain, entity/time columns, frequency, units).
SOURCE_CONTRACTS: dict[str, dict[str, Any]] = {
    "Price_Stock_Indonesia_IDX": {
        "meaning": "Daily IDX OHLCV price bars per ticker", "grain": ["ticker", "date"], "entity_column": "ticker",
        "time_column": "date", "frequency": "1D", "time_zone": "Asia/Jakarta exchange trading date",
        "units": {"open": "IDR per share", "high": "IDR per share", "low": "IDR per share", "close": "IDR per share",
                  "volume": "volume as reported by the source"}},
    "Feature_01_Stock_Daily": {
        "meaning": "Daily per-ticker price features derived in PostgreSQL", "grain": ["ticker", "date"],
        "entity_column": "ticker", "time_column": "date", "frequency": "1D",
        "time_zone": "Asia/Jakarta exchange trading date", "units": {}},
    "Feature_02_Broker_Rolling": {
        "meaning": "Daily broker flow and rolling signals per ticker, board, broker, and investor type",
        "grain": ["ticker", "market_board", "broker", "investor_type", "date"], "entity_column": "ticker",
        "time_column": "date", "frequency": "1D", "time_zone": "Asia/Jakarta exchange trading date", "units": {}},
    "Feature_03_Stock_Broker_Daily": {
        "meaning": "Daily stock-level broker breadth and flows per ticker and board",
        "grain": ["ticker", "market_board", "date"], "entity_column": "ticker", "time_column": "date",
        "frequency": "1D", "time_zone": "Asia/Jakarta exchange trading date", "units": {}},
    "IDX_Broker_Summary": {
        "meaning": "Daily broker activity per symbol, broker, investor type, and market board",
        "grain": ["Date", "Symbol", "Broker", "Investor Type", "Market Board"], "entity_column": "Symbol",
        "time_column": "Date", "frequency": "1D", "time_zone": "Asia/Jakarta exchange trading date",
        "units": {"Buy Value": "IDR", "Sell Value": "IDR", "Net Value": "IDR", "Buy Lots": "lots",
                  "Sell Lots": "lots", "Net Lots": "lots"}},
    "IDX_Stock_Universe": {
        "meaning": "Current IDX listed-security reference data", "grain": ["Ticker"], "entity_column": "Ticker",
        "time_column": None, "frequency": "STATIC", "time_zone": None, "units": {}},
    "IDX_Broker_Profile": {
        "meaning": "Broker reference data", "grain": ["broker_code"], "entity_column": "broker_code",
        "time_column": None, "frequency": "STATIC", "time_zone": None, "units": {}},
}
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


def bind(spec: dict[str, Any], bindings: list[dict[str, Any]], files: dict[str, GrantedFile],
         max_files: int) -> dict[str, dict[str, Any]]:
    """Validate the dataset bindings against the approved spec and return the logical-dataset manifest."""
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
        contract = SOURCE_CONTRACTS.get(table)
        members = [files[ds] for ds in binding["dataset_ids"]]
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


def _column_uses(spec: dict[str, Any]) -> dict[str, set[str]]:
    """Columns that verified calculations read as numbers, per logical input."""
    uses: dict[str, set[str]] = {}
    for calc in spec["calculations"]:
        if calc["method"] != "CUSTOM":
            uses.setdefault(calc["dataset"], set()).update(calc["columns"])
    return uses
