from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

DatasetId = Annotated[str, StringConstraints(pattern=r"^ds_[0-9a-f]{24}$")]
OutputType = Literal["TABLE", "METRICS", "CHART", "ARTIFACT"]
Status = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "EXPIRED"]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "EXPIRED"}
ANALYSIS_ID = r"^ana_[0-9a-f]{24}$"
REQUEST_ID = r"^[A-Za-z0-9._:-]{1,128}$"

# Deterministic next step for the model, a pure function of status and error code.
DATA_ERRORS = {"DATASET_NOT_FOUND", "DATASET_EXPIRED"}
SERVICE_ERRORS = {"SANDBOX_RESTARTED", "SANDBOX_ISOLATION_UNAVAILABLE", "DATASET_UNAVAILABLE",
                  "DATASET_INTEGRITY_ERROR", "DATASET_STORAGE_UNAVAILABLE", "INTERNAL_ERROR"}


def next_action(status: str, error_code: str | None) -> str:
    if status == "COMPLETED":
        return "USE_ANALYSIS_RESULT"
    if status in {"QUEUED", "RUNNING"}:
        return "GET_ANALYSIS_RESULT"
    if status == "EXPIRED":
        return "RERUN_ANALYSIS_IF_NEEDED"
    if status == "CANCELLED":
        return "STOP_OR_REFORMULATE"
    if error_code in DATA_ERRORS:
        return "REQUEST_DATA_AGAIN"
    if error_code in SERVICE_ERRORS:
        return "REPORT_LIMITATION"
    if error_code == "INPUT_LIMIT_EXCEEDED":
        return "REVISE_DATA_REQUEST"
    return "REVISE_ANALYSIS"


class AnalysisRequest(BaseModel):
    """What market-ai-orc submits. Resource limits are never part of a request."""

    model_config = ConfigDict(extra="forbid")

    request_id: Annotated[str, StringConstraints(pattern=REQUEST_ID)]
    purpose: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    dataset_ids: list[DatasetId] = Field(min_length=1, max_length=8)
    python_code: Annotated[str, StringConstraints(min_length=1, max_length=20000)]
    expected_outputs: list[OutputType] = Field(min_length=1, max_length=4)

    @field_validator("dataset_ids", "expected_outputs")
    @classmethod
    def _unique(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("values must be unique")
        return values


class AnalysisError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    analysis_frames: list[dict[str, Any]] = []


class AnalysisResult(BaseModel):
    """The model-facing analysis record (bounded; no paths, URLs, or credentials)."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    status: Status
    next_action: str
    request_id: str
    purpose: str
    dataset_ids: list[str]
    expected_outputs: list[str]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    runtime_ms: int | None = None
    retry_after_seconds: int | None = None
    outputs: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    error: AnalysisError | None = None
    diagnostics: dict[str, str] | None = None
    lineage: dict[str, Any] = {}
    resource_usage: dict[str, Any] = {}
    outputs_expire_at: str | None = None
