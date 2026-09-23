from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Decision = Literal["INLINE_RESULT", "DATASET_READY", "NEEDS_NARROWING", "REJECTED", "SANDBOX_REQUIRED"]

# Deterministic: the next action is a pure function of the decision.
NEXT_ACTION: dict[str, str] = {
    "INLINE_RESULT": "USE_INLINE_RESULT",
    "DATASET_READY": "RUN_ANALYSIS",
    "NEEDS_NARROWING": "REVISE_DATA_REQUEST",
    "REJECTED": "STOP_OR_REFORMULATE",
    "SANDBOX_REQUIRED": "USE_ANALYSIS_SANDBOX",  # reserved; not produced in this milestone
}


class GovernorStop(Exception):
    """A deterministic non-execution outcome of a gate (NEEDS_NARROWING or REJECTED)."""

    def __init__(self, decision: Decision, reason_code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.decision = decision
        self.reason_code = reason_code
        self.message = message
        self.details = details


def rejected(reason_code: str, message: str, **details: Any) -> GovernorStop:
    return GovernorStop("REJECTED", reason_code, message, **details)


def narrowing(reason_code: str, message: str, **details: Any) -> GovernorStop:
    return GovernorStop("NEEDS_NARROWING", reason_code, message, **details)


class OutputColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    source_table: str
    source_column: str
    aggregation: str | None


class DatasetReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    format: Literal["PARQUET"]
    row_count: int
    column_count: int
    byte_count: int
    checksum_sha256: str
    actual_date_range: dict[str, str | None] | None
    entities_present_count: int | None
    missing_entities: list[str] | None
    completeness_status: str
    created_at: str
    expires_at: str


class GovernorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Decision
    next_action: str
    reason_code: str
    message: str
    request_id: str
    query_id: str
    query_hash: str | None = None
    source_tables: list[str] = []
    columns: list[OutputColumn] = []
    estimated_scan_rows: int | None = None
    estimated_plan_cost: float | None = None
    returned_rows: int | None = None
    output_bytes: int | None = None
    rows: list[list[Any]] | None = None
    dataset: DatasetReference | None = None
    details: dict[str, Any] = {}
    warnings: list[str] = []
    runtime_ms: int = 0
